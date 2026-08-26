"""
DPDP Act Compliance Scanner — JSON API for the Next.js frontend.
Run via `npm run dev` from the web/ folder (starts this + Next.js together).
"""

from __future__ import annotations

import logging
import secrets
from logging.handlers import RotatingFileHandler
from io import BytesIO
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, abort, jsonify, request, send_file

from api_handlers import (
    build_preview_context,
    build_results_context,
    find_previous_scan_summary,
    generate_report_pdf,
    history_summary_item,
    meta_payload,
)
from api_validation import ValidationError, validate_pdf_reference, validate_scan_json_payload
from auth import verify_api_key
from auth_user import resolve_authenticated_user_id
from captcha import captcha_enforced, turnstile_configured, verify_turnstile_token
from entitlements import (
    assign_report_owner,
    has_premium_access,
    report_view_denied,
    resolve_report_owner,
)
from razorpay_payments import create_checkout_order, create_paid_scan_order, razorpay_configured, verify_payment
from razorpay_webhooks import handle_webhook_event, verify_webhook_signature, webhook_configured
from config import (
    DATA_DIR,
    FLASK_DEBUG,
    LOG_BACKUP_COUNT,
    LOG_FILE,
    LOG_MAX_BYTES,
    PORT,
    PREMIUM_COOKIE_MAX_AGE,
    PREMIUM_CURRENCY,
    PREMIUM_ENABLED,
    PREMIUM_FREE_ACCESS,
    PREMIUM_PRICE_PAISE,
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_SCANS_PER_HOUR,
    VISITOR_COOKIE_NAME,
    get_secret_key,
    is_production,
)
from payment_ledger import (
    mark_payment_processed,
    payment_already_processed,
    release_payment_claim,
    try_claim_payment,
)
from supabase_entitlements import check_supabase_tables, report_id_for_payment
from user_reconcile import reconcile_user_account
from scan_quota import (
    claim_anonymous_scan_for_user,
    complete_report_unlock,
    confirm_prepaid_scan_payment,
    is_premium_user,
    quota_snapshot,
    reserve_scan,
    user_has_premium_nav_access,
)
from scan_runner import (
    get_job,
    load_recent_reports,
    load_report_by_id,
    normalize_optional_url,
    normalize_site_url,
    start_pdf_scan,
    start_scan,
)
from security import RateLimiter, SSRFError, get_client_ip, validate_scan_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
_log_path = Path(LOG_FILE)
_log_path.parent.mkdir(parents=True, exist_ok=True)
_file_handler = RotatingFileHandler(
    _log_path,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding="utf-8",
)
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logging.getLogger().addHandler(_file_handler)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = get_secret_key()
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

_scan_rate_limiter = RateLimiter(
    max_requests=RATE_LIMIT_SCANS_PER_HOUR,
    window_seconds=3600,
)


def _visitor_id() -> str:
    existing = request.cookies.get(VISITOR_COOKIE_NAME, "").strip()
    if len(existing) >= 8:
        return existing
    return secrets.token_urlsafe(16)


def _extract_user_id_from_jwt(token: str) -> str:
    """Decode JWT locally (no network call) to extract user id (sub claim)."""
    try:
        import base64
        import json as _json
        parts = token.split(".")
        if len(parts) != 3:
            return ""
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
        return str(payload.get("sub") or "").strip()
    except Exception:
        return ""


def _truststack_proxy() -> bool:
    """True when TrustStack is driving the scan engine (quota handled upstream)."""
    return (request.headers.get("X-TrustStack-Proxy") or "").strip() == "1"


def _user_id() -> str:
    """Verified Supabase user id. For TrustStack proxy calls decode JWT locally
    (avoids Supabase round-trip failures). For direct calls verify against Supabase Auth."""
    if _truststack_proxy():
        from auth_user import extract_bearer_token
        token = extract_bearer_token(request)
        if token:
            uid = _extract_user_id_from_jwt(token)
            if uid:
                return uid
        return resolve_authenticated_user_id(request)
    return resolve_authenticated_user_id(request)


def _require_signed_in():
    """Assessments and reports require an authenticated account."""
    # TrustStack proxy: API key already validated by before_request — trust the caller.
    if _truststack_proxy():
        return None
    if not _user_id():
        return (
            jsonify({"error": "Sign in to run an assessment.", "code": "SIGN_IN_REQUIRED"}),
            401,
        )
    return None


def _scan_quota_gate():
    """
    Reserve one scan slot before starting a job.
    Returns (error_response_or_none, slot_type) where slot_type is 'free' or 'prepaid'.
    """
    # TrustStack already reserved/consumed its own entitlement — do not double-charge
    # the shared user_entitlements row. Force full unlock so PDF/report match a paid scan.
    if _truststack_proxy():
        return None, "prepaid"
    if not PREMIUM_ENABLED or PREMIUM_FREE_ACCESS:
        return None, "free"
    allowed, message, code, slot_type = reserve_scan(_user_id() or None, _visitor_id())
    if allowed:
        return None, slot_type
    status = 401 if code == "SIGN_IN_REQUIRED" else 403
    return jsonify({"error": message, "code": code}), status


def _attach_visitor_cookie(response):
    if not request.path.startswith("/api"):
        return response
    visitor_id = _visitor_id()
    if request.cookies.get(VISITOR_COOKIE_NAME) != visitor_id:
        response.set_cookie(
            VISITOR_COOKIE_NAME,
            visitor_id,
            httponly=True,
            samesite="Lax",
            secure=request.is_secure,
            max_age=PREMIUM_COOKIE_MAX_AGE,
        )
    return response


def _apply_rate_limit() -> Optional[tuple]:
    if not RATE_LIMIT_ENABLED:
        return None
    client_ip = get_client_ip(request)
    allowed, retry_after = _scan_rate_limiter.is_allowed(client_ip)
    if allowed:
        return None
    response = jsonify({
        "error": "Rate limit exceeded. Too many scans from your IP address.",
        "retry_after_seconds": retry_after,
    })
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after)
    return response, 429


@app.before_request
def require_api_key():
    if request.path == "/health" or not request.path.startswith("/api"):
        return None
    # Razorpay webhooks authenticate via X-Razorpay-Signature, not X-API-Key.
    if request.path == "/api/webhooks/razorpay":
        return None
    if not verify_api_key(request):
        return jsonify({"error": "Unauthorized."}), 401


@app.after_request
def ensure_visitor_cookie(response):
    return _attach_visitor_cookie(response)


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if is_production():
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.route("/health")
def health():
    payload = meta_payload()
    payload["status"] = "ok"
    return jsonify(payload)


@app.route("/api/health/supabase")
def health_supabase():
    payload = check_supabase_tables()
    payload["status"] = "ok" if payload.get("ok") else "degraded"
    return jsonify(payload)


@app.route("/api/quota")
def api_quota():
    user_id = _user_id() or None
    snap = quota_snapshot(user_id, _visitor_id())
    snap["premium_enabled"] = PREMIUM_ENABLED
    snap["premium_free_access"] = PREMIUM_FREE_ACCESS
    snap["premium_price_display"] = PREMIUM_PRICE_PAISE / 100
    snap["premium_currency"] = PREMIUM_CURRENCY
    snap["is_premium_user"] = user_has_premium_nav_access(user_id, request)
    return jsonify(snap)


@app.route("/api/user/nav-status")
def api_user_nav_status():
    """Premium nav badge: any paid unlock, global bypass, or current report access."""
    user_id = _user_id() or None
    report_id = (request.args.get("report_id") or "").strip()
    premium = user_has_premium_nav_access(user_id, request, report_id=report_id or None)
    return jsonify({"is_premium_user": premium})


@app.route("/api/user/scans", methods=["GET", "POST"])
def api_user_scans():
    """List or save scan history for the signed-in user (server-side Supabase)."""
    block = _require_signed_in()
    if block:
        return block

    user_id = _user_id()
    from supabase_entitlements import list_user_scans_history, record_user_scan

    if request.method == "GET":
        rows = list_user_scans_history(user_id)
        items = [
            {
                "_report_id": row.get("report_id"),
                "url": row.get("url") or "",
                "score": int(row.get("score") or 0),
                "verdict": row.get("verdict") or "",
                "timestamp": row.get("scanned_at") or "",
                "access_tier": row.get("access_tier") or "preview",
            }
            for row in rows
            if row.get("report_id")
        ]
        return jsonify({"items": items})

    body = request.get_json(silent=True) or {}
    report_id = str(body.get("report_id") or "").strip()
    if not report_id:
        return jsonify({"error": "report_id is required."}), 400

    # Only the canonical owner may attach a history row — prevents ownership hijack.
    report = load_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found."}), 404
    owner = resolve_report_owner(report_id, report)
    if not owner or owner != user_id:
        return jsonify(
            {
                "error": "You do not have access to save this assessment.",
                "code": "ACCESS_DENIED",
            }
        ), 403

    record_user_scan(
        user_id,
        report_id,
        url=str(body.get("url") or report.get("url") or ""),
        score=int(body.get("score") if body.get("score") is not None else report.get("score") or 0),
        verdict=str(body.get("verdict") or report.get("verdict") or ""),
    )
    return jsonify({"ok": True})


@app.route("/api/quota/claim", methods=["POST"])
def api_quota_claim():
    user_id = _user_id()
    if not user_id:
        return jsonify({"error": "Sign in required.", "code": "SIGN_IN_REQUIRED"}), 401
    result = claim_anonymous_scan_for_user(user_id, _visitor_id())
    snap = quota_snapshot(user_id, _visitor_id())
    return jsonify({**result, "quota": snap})


@app.route("/api/scan/checkout", methods=["POST"])
def create_paid_scan_checkout():
    """Pay ₹299 for one full scan when Free preview / Pilot daily is exhausted."""
    sign_in_block = _require_signed_in()
    if sign_in_block:
        return sign_in_block

    user_id = _user_id()
    snap = quota_snapshot(user_id, _visitor_id())
    if snap.get("free_scans_remaining", 0) > 0:
        return jsonify(
            {
                "ok": True,
                "already_has_quota": True,
                "message": "You still have a free preview scan remaining.",
                "quota": snap,
            }
        )
    if snap.get("has_pilot") and int(snap.get("pilot_scans_remaining") or 0) > 0:
        return jsonify(
            {
                "ok": True,
                "already_has_quota": True,
                "message": "You still have today's Pilot full scan remaining.",
                "quota": snap,
            }
        )
    if int(snap.get("prepaid_scans") or snap.get("scan_credits") or 0) > 0:
        return jsonify(
            {
                "ok": True,
                "already_has_quota": True,
                "message": "You already have a paid full-scan credit. Run a scan.",
                "quota": snap,
            }
        )

    if not razorpay_configured():
        return jsonify({"error": "Payment provider is not configured.", "code": "PAYMENTS_UNAVAILABLE"}), 503

    try:
        checkout = create_paid_scan_order(user_id=user_id)
    except Exception:
        logger.exception("Razorpay paid-scan order creation failed")
        return jsonify({"error": "Could not start checkout.", "code": "CHECKOUT_FAILED"}), 502

    checkout["price_display"] = PREMIUM_PRICE_PAISE / 100
    checkout["currency"] = PREMIUM_CURRENCY
    return jsonify(checkout)


@app.route("/api/subscription/pro/create", methods=["POST"])
def create_pro_subscription_api():
    """Legacy Pro create — disabled. Pilot is purchased on TrustStack."""
    return jsonify(
        {
            "error": (
                "Pro has been replaced by Pilot. "
                "Subscribe to Pilot on TrustStack (/subscribe)."
            ),
            "code": "PRO_REPLACED_BY_PILOT",
        }
    ), 410


@app.route("/api/subscription/pro/confirm", methods=["POST"])
def confirm_pro_subscription_api():
    """Verify Razorpay subscription payment and activate Pro tier."""
    sign_in_block = _require_signed_in()
    if sign_in_block:
        return sign_in_block

    user_id = _user_id()
    body = request.get_json(silent=True) or {}
    payment_id = str(body.get("razorpay_payment_id", "")).strip()
    order_id = str(body.get("razorpay_order_id", "")).strip()
    subscription_id = str(body.get("razorpay_subscription_id", "")).strip()
    signature = str(body.get("razorpay_signature", "")).strip()

    if not razorpay_configured():
        return jsonify({"error": "Payment provider is not configured.", "code": "PAYMENTS_UNAVAILABLE"}), 503

    # Monthly pass (one-time ₹999 order — no Razorpay Plan)
    if order_id:
        from razorpay_payments import verify_payment
        from supabase_subscriptions import activate_pro_monthly_pass

        try:
            verify_payment(
                payment_id=payment_id,
                order_id=order_id,
                signature=signature,
                expected_scope="pro_monthly_pass",
                expected_user_id=user_id,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "PAYMENT_INVALID"}), 402
        except Exception:
            logger.exception("Pro monthly pass payment verification failed")
            return jsonify({"error": "Payment verification failed.", "code": "PAYMENT_FAILED"}), 502

        if not try_claim_payment(payment_id):
            snap = quota_snapshot(user_id, _visitor_id())
            return jsonify({"ok": True, "scope": "pro_monthly_pass", "quota": snap, "already_processed": True})

        if not activate_pro_monthly_pass(user_id, payment_id=payment_id, order_id=order_id):
            release_payment_claim(payment_id)
            return jsonify({"error": "Could not activate Pro.", "code": "PRO_ACTIVATION_FAILED"}), 500

        snap = quota_snapshot(user_id, _visitor_id())
        return jsonify({"ok": True, "scope": "pro_monthly_pass", "quota": snap})

    # Razorpay Subscription (recurring — requires plan_id)
    from datetime import datetime, timezone
    from razorpay_subscriptions import verify_subscription_payment, fetch_subscription
    from supabase_subscriptions import initialize_pro_subscription_scans, upsert_subscription

    if not subscription_id:
        return jsonify({"error": "Missing payment details.", "code": "PAYMENT_INVALID"}), 400

    try:
        verify_subscription_payment(
            payment_id=payment_id,
            subscription_id=subscription_id,
            signature=signature,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "PAYMENT_INVALID"}), 402
    except Exception:
        logger.exception("Pro subscription payment verification failed")
        return jsonify({"error": "Payment verification failed.", "code": "PAYMENT_FAILED"}), 502

    try:
        subscription = fetch_subscription(subscription_id)
    except Exception:
        logger.exception("Failed to fetch subscription %s", subscription_id)
        return jsonify({"error": "Could not load subscription.", "code": "SUBSCRIPTION_LOOKUP_FAILED"}), 502

    notes = subscription.get("notes") or {}
    owner_id = str(notes.get("user_id") or "").strip()
    if not owner_id:
        return jsonify(
            {
                "error": "Subscription is missing an owner binding.",
                "code": "SUBSCRIPTION_USER_MISMATCH",
            }
        ), 403
    if owner_id != user_id:
        return jsonify({"error": "Subscription does not belong to this account.", "code": "SUBSCRIPTION_USER_MISMATCH"}), 403

    def _to_datetime(ts):
        if not ts:
            return None
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            return None

    status = str(subscription.get("status") or "active").strip()
    if status not in ("active", "authenticated", "created"):
        status = "active"

    upsert_subscription(
        user_id,
        subscription_id,
        str(subscription.get("plan_id") or ""),
        status if status in ("active", "authenticated") else "active",
        current_start=_to_datetime(subscription.get("current_start")),
        current_end=_to_datetime(subscription.get("current_end")),
        charge_at=_to_datetime(subscription.get("charge_at")),
    )
    initialize_pro_subscription_scans(user_id)

    if payment_id:
        mark_payment_processed(payment_id)

    snap = quota_snapshot(user_id, _visitor_id())
    return jsonify({
        "ok": True,
        "scope": "pro_subscription",
        "subscription_id": subscription_id,
        "quota": snap,
    })


@app.route("/api/subscription/status")
def get_subscription_status():
    """Get user's current subscription status (Pilot + legacy Pro)."""
    sign_in_block = _require_signed_in()
    if sign_in_block:
        return sign_in_block

    user_id = _user_id()

    from supabase_subscriptions import get_active_subscription, get_pro_scans_remaining
    from truststack_tiers import get_pilot_scans_remaining, get_user_tier, user_has_pilot

    has_pilot = user_has_pilot(user_id)
    pro_sub = get_active_subscription(user_id, tier="pro")
    tier = get_user_tier(user_id)

    return jsonify({
        "tier": tier,
        "has_pilot": has_pilot,
        "pilot_scans_remaining": get_pilot_scans_remaining(user_id) if has_pilot else 0,
        "has_pro": pro_sub is not None,
        "pro_subscription": pro_sub,
        "pro_scans_remaining": get_pro_scans_remaining(user_id) if pro_sub else 0,
    })


@app.route("/api/subscription/cancel", methods=["POST"])
def cancel_subscription_api():
    """Cancel user's legacy Pro subscription (Pilot cancel is on TrustStack)."""
    sign_in_block = _require_signed_in()
    if sign_in_block:
        return sign_in_block

    user_id = _user_id()
    
    from razorpay_subscriptions import cancel_subscription, subscriptions_enabled
    from supabase_subscriptions import get_active_subscription
    
    if not subscriptions_enabled():
        return jsonify({"error": "Subscriptions are not available.", "code": "SUBSCRIPTIONS_UNAVAILABLE"}), 503
    
    pro_sub = get_active_subscription(user_id, tier="pro")
    if not pro_sub:
        return jsonify({"error": "No active legacy subscription found.", "code": "NO_SUBSCRIPTION"}), 404
    
    razorpay_sub_id = pro_sub.get("razorpay_subscription_id")
    if not razorpay_sub_id:
        return jsonify({"error": "Subscription ID not found.", "code": "INVALID_SUBSCRIPTION"}), 400
    
    try:
        result = cancel_subscription(razorpay_sub_id)
        return jsonify({
            "ok": True,
            "message": "Subscription cancelled successfully.",
            "subscription": result,
        })
    except Exception:
        logger.exception("Subscription cancellation failed")
        return jsonify({"error": "Could not cancel subscription.", "code": "CANCELLATION_FAILED"}), 502


@app.route("/api/scan/confirm-payment", methods=["POST"])
def confirm_paid_scan_payment_route():
    """Verify Razorpay payment and grant one prepaid scan slot."""
    sign_in_block = _require_signed_in()
    if sign_in_block:
        return sign_in_block

    user_id = _user_id()
    body = request.get_json(silent=True) or {}
    payment_id = str(body.get("razorpay_payment_id", "")).strip()
    order_id = str(body.get("razorpay_order_id", "")).strip()
    signature = str(body.get("razorpay_signature", "")).strip()

    if not razorpay_configured():
        return jsonify({"error": "Payment provider is not configured.", "code": "PAYMENTS_UNAVAILABLE"}), 503

    try:
        verify_payment(
            payment_id=payment_id,
            order_id=order_id,
            signature=signature,
            expected_scope="paid_scan",
            expected_user_id=user_id,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "PAYMENT_INVALID"}), 402
    except Exception:
        logger.exception("Paid scan payment verification failed")
        return jsonify({"error": "Payment verification failed.", "code": "PAYMENT_FAILED"}), 502

    if not try_claim_payment(payment_id):
        snap = quota_snapshot(user_id, _visitor_id())
        return jsonify({"ok": True, "scope": "paid_scan", "quota": snap, "already_processed": True})

    if not confirm_prepaid_scan_payment(user_id):
        release_payment_claim(payment_id)
        return jsonify({"error": "Could not grant prepaid scan.", "code": "QUOTA_ERROR"}), 500

    snap = quota_snapshot(user_id, _visitor_id())
    return jsonify({"ok": True, "scope": "paid_scan", "quota": snap})


@app.route("/api/webhooks/razorpay", methods=["POST"])
def razorpay_webhook():
    """
    Primary payment confirmation path — Razorpay calls this on payment.captured.
    Authenticated via X-Razorpay-Signature (not X-API-Key).
    """
    if not webhook_configured():
        logger.warning("Razorpay webhook received but RAZORPAY_WEBHOOK_SECRET is not set")
        return jsonify({"error": "Webhooks not configured."}), 503

    raw_body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not verify_webhook_signature(raw_body, signature):
        logger.warning("Razorpay webhook rejected: invalid signature")
        return jsonify({"error": "Invalid signature."}), 400

    try:
        payload = request.get_json(force=True, silent=False)
    except Exception:
        logger.warning("Razorpay webhook rejected: invalid JSON body")
        return jsonify({"error": "Invalid JSON."}), 400

    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload."}), 400

    try:
        result = handle_webhook_event(payload)
        logger.info("Razorpay webhook handled: %s", result)
    except Exception:
        logger.exception("Razorpay webhook handler error")
        # Return 200 so Razorpay does not retry indefinitely on our bugs; check logs.
        return jsonify({"ok": True, "warning": "handler_error_logged"}), 200

    return jsonify({"ok": True, "result": result}), 200


def _require_scan_captcha(scan_slot_type: str):
    """
    Require Cloudflare Turnstile on free-tier scans when configured / enforced.
    Paid/pro slots skip CAPTCHA so paying customers aren't blocked twice.
    """
    if scan_slot_type in ("prepaid", "pro", "pilot_daily"):
        return None
    if not turnstile_configured():
        if captcha_enforced():
            return jsonify(
                {
                    "error": "CAPTCHA is required but not configured on the server.",
                    "code": "CAPTCHA_REQUIRED",
                }
            ), 403
        return None

    token = ""
    if request.content_type and "multipart/form-data" in (request.content_type or ""):
        token = (request.form.get("captcha_token") or "").strip()
    else:
        data = request.get_json(silent=True) or {}
        token = str(data.get("captcha_token") or request.form.get("captcha_token") or "").strip()

    ok, message = verify_turnstile_token(token, get_client_ip(request))
    if not ok:
        return jsonify({"error": message, "code": "CAPTCHA_REQUIRED"}), 403
    return None


@app.route("/api/scan", methods=["POST"])
def api_start_scan():
    sign_in_block = _require_signed_in()
    if sign_in_block:
        return sign_in_block

    rate_limited = _apply_rate_limit()
    if rate_limited:
        return rate_limited

    quota_blocked = _scan_quota_gate()
    if quota_blocked[0]:
        return quota_blocked[0]
    scan_slot_type = quota_blocked[1]
    # Full reports: Pilot daily, prepaid ₹299, and legacy Pro
    auto_unlock = scan_slot_type in ("prepaid", "pro", "pilot_daily")

    captcha_blocked = _require_scan_captcha(scan_slot_type)
    if captcha_blocked:
        return captcha_blocked

    if request.content_type and "multipart/form-data" in request.content_type:
        return _start_pdf_scan(scan_slot_type=scan_slot_type, auto_unlock=auto_unlock)

    data = request.get_json(silent=True) or request.form
    try:
        validated = validate_scan_json_payload(dict(data) if data else {})
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    input_mode = validated.get("input_mode", "url")
    if input_mode == "pdf":
        return jsonify({"error": "PDF uploads must use multipart form data."}), 400

    url = normalize_site_url(validated["url"])
    if not url:
        return jsonify({"error": "Please enter a valid website URL."}), 400

    try:
        validate_scan_url(url)
    except SSRFError as exc:
        return jsonify({"error": str(exc)}), 400

    manual_fields = [
        ("privacy_url", "Privacy Policy URL"),
        ("terms_url", "Terms of Service URL"),
        ("cookie_url", "Cookie Policy URL"),
    ]
    manual: dict = {}
    for field, label in manual_fields:
        raw = validated.get(field, "")
        if not raw:
            continue
        normalized = normalize_optional_url(raw)
        if not normalized:
            return jsonify({"error": f"Invalid {label}."}), 400
        try:
            validate_scan_url(normalized)
        except SSRFError as exc:
            return jsonify({"error": f"{label}: {exc}"}), 400
        manual[field.replace("_url", "")] = normalized

    try:
        job_id = start_scan(
            url=url,
            privacy_url_manual=manual.get("privacy"),
            terms_url_manual=manual.get("terms"),
            cookie_url_manual=manual.get("cookie"),
            owner_user_id=_user_id() or None,
            auto_unlock_on_complete=auto_unlock,
            scan_slot_type=scan_slot_type,
        )
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    return jsonify({"job_id": job_id})


def _start_pdf_scan(scan_slot_type: str = "", auto_unlock: bool = False):
    try:
        reference = validate_pdf_reference(request.form.get("reference"))
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    pdf_files: dict = {}
    field_map = {
        "privacy_pdf": "privacy",
        "terms_pdf": "terms",
        "cookie_pdf": "cookie",
    }
    for form_field, doc_type in field_map.items():
        upload = request.files.get(form_field)
        if not upload or not upload.filename:
            continue
        if not upload.filename.lower().endswith(".pdf"):
            return jsonify({"error": f"{form_field}: only PDF files are accepted."}), 400
        data = upload.read()
        if not data:
            return jsonify({"error": f"{form_field}: uploaded file is empty."}), 400
        pdf_files[doc_type] = data

    if "privacy" not in pdf_files:
        return jsonify({"error": "Please upload a Privacy Policy PDF."}), 400

    try:
        job_id = start_pdf_scan(
            reference=reference,
            pdf_files=pdf_files,
            owner_user_id=_user_id() or None,
            auto_unlock_on_complete=auto_unlock,
            scan_slot_type=scan_slot_type or None,
        )
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    return jsonify({"job_id": job_id})


@app.route("/api/scan/<job_id>")
def api_scan_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Scan not found."}), 404

    owner_user_id = (job.get("owner_user_id") or "").strip()
    viewer = _user_id()
    if owner_user_id and viewer != owner_user_id:
        return jsonify(
            {
                "error": "You do not have access to this scan.",
                "code": "ACCESS_DENIED",
            }
        ), 403

    payload = {
        "id": job["id"],
        "status": job["status"],
        "progress": job.get("progress", 0),
        "message": job.get("message", ""),
        "log": job.get("log", []),
        "error": job.get("error"),
    }

    if job["status"] == "complete":
        report = job.get("report") or {}
        report_path = job.get("report_path", "")
        report_id = Path(report_path).stem if report_path else job_id
        if owner_user_id and report_id:
            assign_report_owner(report_id, owner_user_id, report)
        payload["redirect"] = f"/report/{report_id}"
        payload["report_id"] = report_id
        payload["score"] = report.get("score")
        payload["verdict"] = report.get("verdict")
        payload["url"] = report.get("url", "")

    return jsonify(payload)


@app.route("/api/history")
def api_history():
    """Return only the caller's assessments — never a global disk listing."""
    user_id = _user_id()
    if not user_id:
        return jsonify([])

    from supabase_entitlements import list_user_report_ids

    items = []
    for report_id in list_user_report_ids(user_id, limit=12):
        report = load_report_by_id(report_id)
        if not report:
            continue
        report["_report_id"] = report_id
        items.append(history_summary_item(report))
    return jsonify(items)


@app.route("/api/report/<report_id>/previous")
def api_report_previous(report_id: str):
    report = load_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found."}), 404

    denied = report_view_denied(report_id, report, request)
    if denied:
        return denied

    user_id = _user_id()
    from supabase_entitlements import list_user_report_ids

    owned_reports = []
    for rid in list_user_report_ids(user_id, limit=50):
        item = load_report_by_id(rid)
        if not item:
            continue
        item["_report_id"] = rid
        owned_reports.append(item)

    previous = find_previous_scan_summary(
        owned_reports,
        current_id=report_id,
        url=report.get("url", ""),
        timestamp=report.get("timestamp", ""),
    )
    return jsonify(previous)


@app.route("/api/meta")
def api_meta():
    return jsonify(meta_payload())


@app.route("/api/report/<report_id>/status")
def api_report_status(report_id: str):
    """Lightweight unlock status for payment polling (no full report payload)."""
    report = load_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found."}), 404

    denied = report_view_denied(report_id, report, request)
    if denied:
        return denied

    user_id = _user_id()
    if user_id:
        reconcile_user_account(user_id)
        report = load_report_by_id(report_id) or report

    tier = "full" if has_premium_access(report_id, report, request) else "preview"
    return jsonify({"report_id": report_id, "access_tier": tier})


@app.route("/api/report/<report_id>")
def api_report(report_id: str):
    report = load_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found."}), 404

    denied = report_view_denied(report_id, report, request)
    if denied:
        return denied

    user_id = _user_id()
    if user_id:
        reconcile_user_account(user_id)
        report = load_report_by_id(report_id) or report

    report.pop("_filepath", None)
    # TrustStack already billed/entitled the owner upstream. Always return the
    # full ReportContext so the same account can reopen the report on any device
    # (matches original DPDP scanner cross-device behaviour via scan_reports).
    owner = resolve_report_owner(report_id, report)
    truststack_owner = bool(
        _truststack_proxy() and user_id and owner and user_id == owner
    )
    if truststack_owner or has_premium_access(report_id, report, request):
        ctx = build_results_context(report)
    else:
        ctx = build_preview_context(report)
    ctx["report_id"] = report_id
    meta = meta_payload()
    ctx["scanner_version"] = meta["scanner_version"]
    ctx["rules_version"] = meta["rules_version"]
    return jsonify(ctx)


@app.route("/api/report/<report_id>/pdf")
def download_pdf(report_id: str):
    report = load_report_by_id(report_id)
    if not report:
        abort(404)

    denied = report_view_denied(report_id, report, request)
    if denied:
        return denied

    user_id = _user_id()
    if user_id:
        reconcile_user_account(user_id)
        report = load_report_by_id(report_id) or report

    owner = resolve_report_owner(report_id, report)
    truststack_owner = bool(
        _truststack_proxy() and user_id and owner and user_id == owner
    )
    if (
        PREMIUM_ENABLED
        and not truststack_owner
        and not has_premium_access(report_id, report, request)
    ):
        return (
            jsonify(
                {
                    "error": "Premium access required to download the PDF report.",
                    "code": "PREMIUM_REQUIRED",
                }
            ),
            402,
        )

    try:
        pdf_bytes, filename = generate_report_pdf(report_id)
    except FileNotFoundError:
        abort(404)
    except Exception as exc:
        logger.exception("PDF generation failed")
        abort(500, description=str(exc))

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/report/<report_id>/checkout", methods=["POST"])
def create_report_checkout(report_id: str):
    """Create a Razorpay order to unlock one full report."""
    report = load_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found."}), 404

    denied = report_view_denied(report_id, report, request)
    if denied:
        return denied

    user_id = _user_id()
    if user_id:
        reconcile_user_account(user_id)
        report = load_report_by_id(report_id) or report

    if has_premium_access(report_id, report, request):
        return jsonify({"ok": True, "already_unlocked": True, "access_tier": "full", "scope": "report"})
    if PREMIUM_ENABLED and not PREMIUM_FREE_ACCESS:
        user_id = _user_id()
        if not user_id:
            return jsonify(
                {"error": "Sign in to unlock the full report.", "code": "SIGN_IN_REQUIRED"}
            ), 401
    if not razorpay_configured():
        return jsonify({"error": "Payment provider is not configured.", "code": "PAYMENTS_UNAVAILABLE"}), 503

    try:
        checkout = create_checkout_order(report_id, user_id=_user_id())
    except Exception as exc:
        logger.exception("Razorpay order creation failed")
        return jsonify({"error": "Could not start checkout.", "code": "CHECKOUT_FAILED"}), 502

    checkout["price_display"] = PREMIUM_PRICE_PAISE / 100
    checkout["currency"] = PREMIUM_CURRENCY
    checkout["scope"] = "report"
    return jsonify(checkout)


@app.route("/api/report/<report_id>/unlock", methods=["POST"])
def unlock_report(report_id: str):
    """Verify Razorpay payment and unlock one report."""
    report = load_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found."}), 404

    denied = report_view_denied(report_id, report, request)
    if denied:
        return denied

    user_id = _user_id()
    if user_id:
        reconcile_user_account(user_id)
        report = load_report_by_id(report_id) or report

    if has_premium_access(report_id, report, request):
        snap = quota_snapshot(_user_id() or None, _visitor_id())
        return jsonify({"ok": True, "access_tier": "full", "scope": "report", "quota": snap})

    user_id = user_id or _user_id()
    if PREMIUM_ENABLED and not PREMIUM_FREE_ACCESS and not user_id:
        return jsonify(
            {"error": "Sign in to unlock the full report.", "code": "SIGN_IN_REQUIRED"}
        ), 401

    body = request.get_json(silent=True) or {}
    payment_id = str(body.get("razorpay_payment_id", "")).strip()
    order_id = str(body.get("razorpay_order_id", "")).strip()
    signature = str(body.get("razorpay_signature", "")).strip()

    if not user_id:
        return jsonify(
            {"error": "Sign in to unlock the full report.", "code": "SIGN_IN_REQUIRED"}
        ), 401

    if not razorpay_configured():
        return jsonify({"error": "Payment provider is not configured.", "code": "PAYMENTS_UNAVAILABLE"}), 503

    try:
        verify_payment(
            payment_id=payment_id,
            order_id=order_id,
            signature=signature,
            expected_scope="report",
            expected_report_id=report_id,
            expected_user_id=user_id,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "PAYMENT_INVALID"}), 402
    except Exception:
        logger.exception("Payment verification failed")
        return jsonify({"error": "Payment verification failed.", "code": "PAYMENT_FAILED"}), 502

    prior_report = report_id_for_payment(payment_id)
    if prior_report and prior_report != report_id:
        return jsonify(
            {
                "error": "This payment was already used for another report.",
                "code": "PAYMENT_ALREADY_USED",
            }
        ), 409
    if prior_report == report_id or payment_already_processed(payment_id):
        if has_premium_access(report_id, load_report_by_id(report_id) or report, request):
            snap = quota_snapshot(user_id, _visitor_id())
            return jsonify({"ok": True, "access_tier": "full", "scope": "report", "quota": snap})
        return jsonify(
            {
                "error": "Payment already processed. Refresh in a moment.",
                "code": "PAYMENT_ALREADY_USED",
            }
        ), 409

    if not try_claim_payment(payment_id):
        if has_premium_access(report_id, load_report_by_id(report_id) or report, request):
            snap = quota_snapshot(user_id, _visitor_id())
            return jsonify({"ok": True, "access_tier": "full", "scope": "report", "quota": snap})
        return jsonify(
            {
                "error": "Payment already processed. Refresh in a moment.",
                "code": "PAYMENT_ALREADY_USED",
            }
        ), 409

    try:
        complete_report_unlock(
            user_id,
            report_id,
            payment_id=payment_id,
            order_id=order_id,
            amount_paise=PREMIUM_PRICE_PAISE,
            currency=PREMIUM_CURRENCY,
        )
    except Exception:
        release_payment_claim(payment_id)
        logger.exception("Report unlock grant failed after payment claim")
        return jsonify({"error": "Could not unlock report.", "code": "UNLOCK_FAILED"}), 500

    logger.info("Report premium unlocked (%s, payment %s, user %s)", report_id, payment_id, user_id)
    snap = quota_snapshot(user_id or None, _visitor_id())
    return jsonify({"ok": True, "access_tier": "full", "scope": "report", "quota": snap})


@app.errorhandler(404)
def not_found(_exc):
    return jsonify({"error": "Not found."}), 404


@app.errorhandler(500)
def server_error(exc):
    return jsonify({
        "error": getattr(exc, "description", "An internal error occurred."),
    }), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=FLASK_DEBUG, use_reloader=False)
