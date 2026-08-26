"""Razorpay webhook verification and payment.captured + subscription.* event handling."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any

from config import PREMIUM_CURRENCY, PREMIUM_PRICE_PAISE, RAZORPAY_WEBHOOK_SECRET
from payment_ledger import mark_payment_processed, payment_already_processed
from razorpay_payments import _client_instance, razorpay_configured
from scan_quota import complete_report_unlock, confirm_prepaid_scan_payment
from supabase_entitlements import payment_id_in_report_unlocks
from supabase_subscriptions import initialize_pro_subscription_scans, upsert_subscription
from user_reconcile import user_has_report_access

logger = logging.getLogger(__name__)


def webhook_configured() -> bool:
    return bool(RAZORPAY_WEBHOOK_SECRET and razorpay_configured())


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify X-Razorpay-Signature using the webhook secret."""
    secret = (RAZORPAY_WEBHOOK_SECRET or "").strip()
    sig = (signature or "").strip()
    if not secret or not sig or not body:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _order_notes(order_id: str) -> dict[str, str]:
    client = _client_instance()
    order = client.order.fetch(order_id)
    raw = order.get("notes") or {}
    return {str(k): str(v) for k, v in raw.items() if v is not None}


def process_payment_captured(payment_entity: dict[str, Any]) -> dict[str, Any]:
    """
    Apply unlock or prepaid scan credit for a captured payment.
    Idempotent — safe to retry on webhook delivery.
    """
    payment_id = str(payment_entity.get("id") or "").strip()
    order_id = str(payment_entity.get("order_id") or "").strip()
    status = str(payment_entity.get("status") or "").strip()

    if not payment_id or not order_id:
        return {"status": "ignored", "reason": "missing_payment_or_order_id"}
    if status != "captured":
        return {"status": "ignored", "reason": f"status_{status or 'unknown'}"}

    if payment_already_processed(payment_id) or payment_id_in_report_unlocks(payment_id):
        logger.info("Webhook payment already processed: %s", payment_id)
        return {"status": "already_processed", "payment_id": payment_id}

    notes = _order_notes(order_id)
    scope = notes.get("scope") or "report"
    user_id = notes.get("user_id", "").strip()

    if scope == "report":
        report_id = notes.get("report_id", "").strip()
        if not report_id or not user_id:
            logger.warning(
                "Webhook report unlock missing notes (payment=%s order=%s notes=%s)",
                payment_id,
                order_id,
                notes,
            )
            return {"status": "error", "reason": "missing_report_or_user_notes"}

        if user_has_report_access(user_id, report_id):
            mark_payment_processed(payment_id)
            return {"status": "already_unlocked", "report_id": report_id, "payment_id": payment_id}

        complete_report_unlock(
            user_id,
            report_id,
            payment_id=payment_id,
            order_id=order_id,
            amount_paise=PREMIUM_PRICE_PAISE,
            currency=PREMIUM_CURRENCY,
        )
        mark_payment_processed(payment_id)
        logger.info("Webhook unlocked report %s for user %s (payment %s)", report_id, user_id, payment_id)
        return {"status": "unlocked", "report_id": report_id, "payment_id": payment_id}

    if scope == "paid_scan":
        if not user_id:
            logger.warning("Webhook paid_scan missing user_id (payment=%s)", payment_id)
            return {"status": "error", "reason": "missing_user_id"}

        if payment_already_processed(payment_id):
            return {"status": "already_processed", "payment_id": payment_id}

        ok = confirm_prepaid_scan_payment(user_id)
        if not ok:
            logger.error("Webhook prepaid grant failed for user %s payment %s", user_id, payment_id)
            return {"status": "error", "reason": "prepaid_grant_failed", "payment_id": payment_id}

        mark_payment_processed(payment_id)
        logger.info("Webhook granted prepaid scan for user %s (payment %s)", user_id, payment_id)
        return {"status": "prepaid_granted", "payment_id": payment_id, "user_id": user_id}

    if scope == "pro_monthly_pass":
        if not user_id:
            logger.warning("Webhook pro_monthly_pass missing user_id (payment=%s)", payment_id)
            return {"status": "error", "reason": "missing_user_id"}

        from config import PRO_PRICE_PAISE
        from supabase_subscriptions import activate_pro_monthly_pass, user_has_active_pro

        if user_has_active_pro(user_id) and payment_already_processed(payment_id):
            return {"status": "already_processed", "payment_id": payment_id}

        ok = activate_pro_monthly_pass(user_id, payment_id=payment_id, order_id=order_id)
        if not ok:
            logger.error("Webhook Pro monthly pass failed for user %s payment %s", user_id, payment_id)
            return {"status": "error", "reason": "pro_activation_failed", "payment_id": payment_id}

        mark_payment_processed(payment_id)
        logger.info("Webhook activated Pro monthly pass for user %s (payment %s)", user_id, payment_id)
        return {"status": "pro_activated", "payment_id": payment_id, "user_id": user_id}

    logger.warning("Webhook unknown scope %r for payment %s", scope, payment_id)
    return {"status": "ignored", "reason": f"unknown_scope_{scope}"}


def process_subscription_event(event: str, subscription_entity: dict[str, Any]) -> dict[str, Any]:
    """
    Handle subscription.* events (activated, charged, cancelled, etc).
    Idempotent — safe to retry on webhook delivery.
    """
    subscription_id = str(subscription_entity.get("id") or "").strip()
    status = str(subscription_entity.get("status") or "").strip()
    plan_id = str(subscription_entity.get("plan_id") or "").strip()
    
    if not subscription_id:
        return {"status": "ignored", "reason": "missing_subscription_id"}
    
    # Fetch subscription to get notes (user_id)
    try:
        notes = subscription_entity.get("notes") or {}
        user_id = str(notes.get("user_id") or "").strip()
        tier = str(notes.get("tier") or "pro").strip()
        
        if not user_id:
            logger.warning("Subscription webhook missing user_id (subscription=%s)", subscription_id)
            return {"status": "error", "reason": "missing_user_id"}
        
        # Parse timestamps
        current_start = subscription_entity.get("current_start")
        current_end = subscription_entity.get("current_end")
        charge_at = subscription_entity.get("charge_at")
        ended_at = subscription_entity.get("ended_at")
        
        def _to_datetime(ts: Any) -> datetime | None:
            if not ts:
                return None
            try:
                return datetime.fromtimestamp(int(ts), tz=timezone.utc) if isinstance(ts, (int, str)) else None
            except Exception:
                return None
        
        current_start_dt = _to_datetime(current_start)
        current_end_dt = _to_datetime(current_end)
        charge_at_dt = _to_datetime(charge_at)
        ended_at_dt = _to_datetime(ended_at)
        
        # Update subscription in DB
        ok = upsert_subscription(
            user_id,
            subscription_id,
            plan_id,
            status,
            current_start=current_start_dt,
            current_end=current_end_dt,
            charge_at=charge_at_dt,
            ended_at=ended_at_dt,
            tier=tier,
        )
        
        if not ok:
            logger.error("Failed to upsert subscription for user %s (subscription=%s)", user_id, subscription_id)
            return {"status": "error", "reason": "upsert_failed"}
        
        # Initialize scan counter when subscription becomes active
        if event == "subscription.activated" or (event == "subscription.charged" and status == "active"):
            initialize_pro_subscription_scans(user_id)
        
        logger.info("Processed subscription event %s for user %s (subscription=%s, status=%s)", 
                   event, user_id, subscription_id, status)
        return {
            "status": "processed",
            "event": event,
            "subscription_id": subscription_id,
            "user_id": user_id,
            "subscription_status": status,
        }
    
    except Exception as exc:
        logger.error("Subscription event processing failed: %s", exc)
        return {"status": "error", "reason": str(exc)}


def handle_webhook_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a Razorpay webhook payload. Returns a result dict for logging."""
    event = str(payload.get("event") or "").strip()
    logger.info("Razorpay webhook event=%s", event)

    if event == "payment.captured":
        entity = (payload.get("payload") or {}).get("payment", {}).get("entity") or {}
        if not isinstance(entity, dict):
            return {"status": "error", "reason": "invalid_payment_entity"}
        result = process_payment_captured(entity)
        result["event"] = event
        return result
    
    if event.startswith("subscription."):
        entity = (payload.get("payload") or {}).get("subscription", {}).get("entity") or {}
        if not isinstance(entity, dict):
            return {"status": "error", "reason": "invalid_subscription_entity"}
        result = process_subscription_event(event, entity)
        return result
    
    return {"status": "ignored", "event": event}
