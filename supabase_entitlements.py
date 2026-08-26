"""Supabase tables for scan quotas and per-report unlocks."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from config import FREE_SCANS_PER_USER, SUPABASE_SERVICE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

_client = None


def supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _get_client():
    global _client
    if not supabase_configured():
        return None
    if _client is None:
        from supabase import create_client

        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


def _default_entitlements(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "free_scans_used": 0,
        "scan_credits": 0,
        "pro_scans_used": 0,
        "pro_scans_reset_at": None,
    }


def get_user_entitlements(user_id: str) -> Dict[str, Any]:
    client = _get_client()
    if not client or not user_id:
        return _default_entitlements(user_id or "")
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            result = (
                client.table("user_entitlements")
                .select("user_id, free_scans_used, scan_credits, pro_scans_used, pro_scans_reset_at")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if rows:
                return rows[0]
            client.table("user_entitlements").insert(_default_entitlements(user_id)).execute()
            return _default_entitlements(user_id)
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                import time

                time.sleep(0.15 * (attempt + 1))
    logger.warning("user_entitlements read failed: %s", last_exc)
    return _default_entitlements(user_id)


def consume_user_scan(user_id: str) -> Optional[str]:
    """
    Consume one scan slot for a signed-in user.
    Returns 'free', 'prepaid', or 'pro' when successful, None when quota is exhausted.
    
    Priority order:
    1. Pro subscription scans (if active Pro subscription exists)
    2. Free scans (lifetime quota)
    3. Prepaid scans (pay-before-scan ₹299 credits)
    
    scan_credits column stores prepaid one-time scan slots (pay ₹299 before scanning).
    """
    if not supabase_configured():
        # Fail closed in production — never grant unlimited free scans when DB is down.
        from config import is_production

        if is_production():
            logger.error("consume_user_scan refused: Supabase not configured in production")
            return None
        return "free"
    client = _get_client()
    if not client or not user_id:
        return None
    
    # Check Pro subscription first
    from supabase_subscriptions import (
        consume_pro_scan,
        get_pro_scans_remaining,
        user_has_active_pro,
    )

    if user_has_active_pro(user_id):
        if get_pro_scans_remaining(user_id) > 0:
            if consume_pro_scan(user_id):
                return "pro"
            return None
    
    # Fall back to free/prepaid scans
    ent = get_user_entitlements(user_id)
    free_used = effective_free_scans_used(user_id)
    prepaid = int(ent.get("scan_credits") or 0)
    pro_used = int(ent.get("pro_scans_used") or 0)
    pro_reset = ent.get("pro_scans_reset_at")

    if free_used < FREE_SCANS_PER_USER:
        try:
            client.table("user_entitlements").upsert(
                {
                    "user_id": user_id,
                    "free_scans_used": free_used + 1,
                    "scan_credits": prepaid,
                    "pro_scans_used": pro_used,
                    "pro_scans_reset_at": pro_reset,
                },
                on_conflict="user_id",
            ).execute()
            return "free"
        except Exception as exc:
            logger.warning("consume free scan failed: %s", exc)
            return None

    if prepaid > 0:
        try:
            client.table("user_entitlements").upsert(
                {
                    "user_id": user_id,
                    "free_scans_used": free_used,
                    "scan_credits": prepaid - 1,
                    "pro_scans_used": pro_used,
                    "pro_scans_reset_at": pro_reset,
                },
                on_conflict="user_id",
            ).execute()
            return "prepaid"
        except Exception as exc:
            logger.warning("consume prepaid scan failed: %s", exc)
            return None

    return None


def grant_prepaid_scan(user_id: str) -> bool:
    """Grant one paid scan slot after ₹299 pay-before-scan checkout (not report unlock)."""
    client = _get_client()
    if not client or not user_id:
        return False
    ent = get_user_entitlements(user_id)
    prepaid = int(ent.get("scan_credits") or 0)
    try:
        # Only update scan_credits — never touch free_scans_used on this path.
        client.table("user_entitlements").upsert(
            {
                "user_id": user_id,
                "scan_credits": prepaid + 1,
            },
            on_conflict="user_id",
        ).execute()
        return True
    except Exception as exc:
        logger.warning("grant_prepaid_scan failed: %s", exc)
        return False


def restore_scan_slot(user_id: str, slot_type: str) -> bool:
    """
    Refund a consumed scan slot after a failed/interrupted job.
    slot_type: 'free' | 'prepaid' | 'pro' | 'pilot_daily'
    """
    if not user_id or slot_type not in ("free", "prepaid", "pro", "pilot_daily"):
        return False
    if slot_type == "prepaid":
        return grant_prepaid_scan(user_id)
    if slot_type == "pilot_daily":
        from truststack_tiers import restore_pilot_scan
        return restore_pilot_scan(user_id)

    client = _get_client()
    if not client:
        return False
    ent = get_user_entitlements(user_id)
    try:
        if slot_type == "free":
            used = max(0, int(ent.get("free_scans_used") or 0) - 1)
            client.table("user_entitlements").upsert(
                {
                    "user_id": user_id,
                    "free_scans_used": used,
                    "scan_credits": int(ent.get("scan_credits") or 0),
                    "pro_scans_used": int(ent.get("pro_scans_used") or 0),
                    "pro_scans_reset_at": ent.get("pro_scans_reset_at"),
                },
                on_conflict="user_id",
            ).execute()
            return True
        # pro
        used = max(0, int(ent.get("pro_scans_used") or 0) - 1)
        client.table("user_entitlements").upsert(
            {
                "user_id": user_id,
                "free_scans_used": int(ent.get("free_scans_used") or 0),
                "scan_credits": int(ent.get("scan_credits") or 0),
                "pro_scans_used": used,
                "pro_scans_reset_at": ent.get("pro_scans_reset_at"),
            },
            on_conflict="user_id",
        ).execute()
        return True
    except Exception as exc:
        logger.warning("restore_scan_slot(%s) failed: %s", slot_type, exc)
        return False


def get_visitor_scan_count(visitor_id: str) -> int:
    client = _get_client()
    if not client or not visitor_id:
        return 0
    try:
        result = (
            client.table("visitor_scans")
            .select("scan_count")
            .eq("visitor_id", visitor_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return 0
        return int(rows[0].get("scan_count") or 0)
    except Exception as exc:
        logger.warning("visitor_scans read failed: %s", exc)
        return 0


def increment_visitor_scan(visitor_id: str) -> None:
    client = _get_client()
    if not client or not visitor_id:
        return
    count = get_visitor_scan_count(visitor_id)
    try:
        client.table("visitor_scans").upsert(
            {"visitor_id": visitor_id, "scan_count": count + 1},
            on_conflict="visitor_id",
        ).execute()
    except Exception as exc:
        logger.warning("visitor_scans increment failed: %s", exc)


def claim_visitor_for_user(user_id: str, visitor_id: str) -> Dict[str, Any]:
    """Count a prior anonymous scan toward the user's free allowance."""
    client = _get_client()
    if not client:
        return {"claimed": False}
    count = get_visitor_scan_count(visitor_id)
    if count < 1:
        return {"claimed": False, "reason": "no_visitor_scans"}

    try:
        result = (
            client.table("visitor_scans")
            .select("claimed_by_user_id")
            .eq("visitor_id", visitor_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if rows and rows[0].get("claimed_by_user_id"):
            return {"claimed": False, "reason": "already_claimed"}

        ent = get_user_entitlements(user_id)
        free_used = int(ent.get("free_scans_used") or 0)
        if free_used >= FREE_SCANS_PER_USER:
            client.table("visitor_scans").upsert(
                {"visitor_id": visitor_id, "scan_count": count, "claimed_by_user_id": user_id},
                on_conflict="visitor_id",
            ).execute()
            return {"claimed": False, "reason": "free_quota_full"}

        client.table("user_entitlements").upsert(
            {
                "user_id": user_id,
                "free_scans_used": min(FREE_SCANS_PER_USER, free_used + 1),
            },
            on_conflict="user_id",
        ).execute()
        client.table("visitor_scans").upsert(
            {"visitor_id": visitor_id, "scan_count": count, "claimed_by_user_id": user_id},
            on_conflict="visitor_id",
        ).execute()
        return {"claimed": True, "free_scans_used": min(FREE_SCANS_PER_USER, free_used + 1)}
    except Exception as exc:
        logger.warning("claim_visitor_for_user failed: %s", exc)
        return {"claimed": False, "reason": "error"}


def _db_has_report_unlock(user_id: str, report_id: str) -> bool:
    client = _get_client()
    if not client or not user_id or not report_id:
        return False
    try:
        result = (
            client.table("report_unlocks")
            .select("id")
            .eq("user_id", user_id)
            .eq("report_id", report_id)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception as exc:
        logger.warning("report_unlocks lookup failed: %s", exc)
        return False


def is_report_unlocked(user_id: str, report_id: str) -> bool:
    if not user_id or not report_id:
        return False
    return _db_has_report_unlock(user_id, report_id)


def user_has_any_report_unlock(user_id: str) -> bool:
    client = _get_client()
    if not client or not user_id:
        return False
    try:
        result = (
            client.table("report_unlocks")
            .select("id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception as exc:
        logger.warning("report_unlocks any lookup failed: %s", exc)
        return False


def list_db_unlocked_report_ids(user_id: str, limit: int = 64) -> list[str]:
    client = _get_client()
    if not client or not user_id:
        return []
    try:
        result = (
            client.table("report_unlocks")
            .select("report_id")
            .eq("user_id", user_id)
            .order("unlocked_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [str(row.get("report_id") or "") for row in (result.data or []) if row.get("report_id")]
    except Exception as exc:
        logger.warning("report_unlocks list failed: %s", exc)
        return []


def sync_file_unlock_to_db(user_id: str, report_id: str, report: dict) -> bool:
    """Backfill Supabase when a paid unlock exists on the report JSON file only."""
    if not user_id or not report_id or _db_has_report_unlock(user_id, report_id):
        return _db_has_report_unlock(user_id, report_id)
    payment_id = str(report.get("premium_payment_id") or "synced-from-file").strip() or "synced-from-file"
    order_id = str(report.get("premium_order_id") or "synced-from-file").strip() or "synced-from-file"
    return record_report_unlock(
        user_id,
        report_id,
        payment_id=payment_id,
        order_id=order_id,
        amount_paise=0,
        currency="INR",
    )


def get_report_owner_user_id(report_id: str) -> Optional[str]:
    """First user who saved this report (scanned_at ASC) — first-writer-wins."""
    client = _get_client()
    if not client or not report_id:
        return None
    try:
        result = (
            client.table("user_scans")
            .select("user_id")
            .eq("report_id", report_id)
            .order("scanned_at", desc=False)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        owner = str(rows[0].get("user_id") or "").strip()
        return owner or None
    except Exception as exc:
        logger.warning("user_scans owner lookup failed: %s", exc)
        return None


def record_user_scan(
    user_id: str,
    report_id: str,
    *,
    url: str,
    score: int,
    verdict: str,
) -> None:
    client = _get_client()
    if not client or not user_id or not report_id:
        return
    try:
        client.table("user_scans").upsert(
            {
                "user_id": user_id,
                "report_id": report_id,
                "url": url,
                "score": score,
                "verdict": verdict,
            },
            on_conflict="user_id,report_id",
        ).execute()
    except Exception as exc:
        logger.warning("record_user_scan failed: %s", exc)


def list_user_scans_history(user_id: str, limit: int = 50) -> list[dict]:
    """Full scan rows for the signed-in user's history panel, with per-report unlock status."""
    client = _get_client()
    if not client or not user_id:
        return []
    try:
        result = (
            client.table("user_scans")
            .select("report_id, url, score, verdict, scanned_at")
            .eq("user_id", user_id)
            .order("scanned_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = result.data or []

        # Fetch unlocked report IDs for this user in one query
        unlocked_ids: set[str] = set()
        try:
            report_ids = [str(row.get("report_id") or "") for row in rows if row.get("report_id")]
            if report_ids:
                unlocks_result = (
                    client.table("report_unlocks")
                    .select("report_id")
                    .eq("user_id", user_id)
                    .in_("report_id", report_ids)
                    .execute()
                )
                unlocked_ids = {
                    str(r.get("report_id") or "")
                    for r in (unlocks_result.data or [])
                    if r.get("report_id")
                }
        except Exception as exc:
            logger.warning("report_unlocks batch lookup failed: %s", exc)

        # Annotate each row with access_tier
        for row in rows:
            rid = str(row.get("report_id") or "")
            row["access_tier"] = "full" if rid in unlocked_ids else "preview"

        return rows
    except Exception as exc:
        logger.warning("user_scans history list failed: %s", exc)
        return []


def list_user_report_ids(user_id: str, limit: int = 24) -> list[str]:
    client = _get_client()
    if not client or not user_id:
        return []
    try:
        result = (
            client.table("user_scans")
            .select("report_id")
            .eq("user_id", user_id)
            .order("scanned_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [str(row.get("report_id") or "") for row in (result.data or []) if row.get("report_id")]
    except Exception as exc:
        logger.warning("user_scans list failed: %s", exc)
        return []


def count_user_scans(user_id: str) -> int:
    client = _get_client()
    if not client or not user_id:
        return 0
    try:
        result = (
            client.table("user_scans")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        return int(result.count or 0)
    except Exception as exc:
        logger.warning("user_scans count failed: %s", exc)
        return 0


def effective_free_scans_used(user_id: str) -> int:
    """Quota used — at least as high as saved scans when entitlements are missing/stale."""
    ent = get_user_entitlements(user_id)
    recorded = int(ent.get("free_scans_used") or 0)
    from supabase_subscriptions import user_has_active_pro

    if user_has_active_pro(user_id):
        return recorded

    saved = count_user_scans(user_id)
    return max(recorded, min(saved, FREE_SCANS_PER_USER))


def sync_entitlements_from_scans(user_id: str) -> None:
    """Align free_scans_used with saved scan rows when entitlements are stale."""
    from supabase_subscriptions import user_has_active_pro

    if user_has_active_pro(user_id):
        return

    client = _get_client()
    if not client or not user_id:
        return
    saved = count_user_scans(user_id)
    ent = get_user_entitlements(user_id)
    recorded = int(ent.get("free_scans_used") or 0)
    target = max(recorded, min(saved, FREE_SCANS_PER_USER))
    if target == recorded:
        return
    try:
        # Only sync free_scans_used — never overwrite prepaid scan_credits.
        client.table("user_entitlements").upsert(
            {
                "user_id": user_id,
                "free_scans_used": target,
            },
            on_conflict="user_id",
        ).execute()
    except Exception as exc:
        logger.warning("sync_entitlements_from_scans failed: %s", exc)


def check_supabase_tables() -> Dict[str, Any]:
    """Verify required Supabase tables exist (for ops / demo readiness)."""
    client = _get_client()
    if not client:
        return {"configured": False, "ok": False, "tables": {}}

    tables = ("user_entitlements", "user_scans", "report_unlocks", "visitor_scans")
    status: Dict[str, bool] = {}
    for name in tables:
        try:
            client.table(name).select("*").limit(1).execute()
            status[name] = True
        except Exception:
            status[name] = False

    return {
        "configured": True,
        "ok": all(status.values()),
        "tables": status,
    }


def report_id_for_payment(payment_id: str) -> Optional[str]:
    """Report already unlocked by this Razorpay payment_id, if any."""
    client = _get_client()
    if not client or not payment_id:
        return None
    try:
        result = (
            client.table("report_unlocks")
            .select("report_id")
            .eq("payment_id", payment_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        rid = str(rows[0].get("report_id") or "").strip()
        return rid or None
    except Exception as exc:
        logger.warning("report_unlocks payment_id lookup failed: %s", exc)
        return None


def payment_id_in_report_unlocks(payment_id: str) -> bool:
    """True when this Razorpay payment already unlocked a report (webhook idempotency)."""
    return bool(report_id_for_payment(payment_id))


def record_report_unlock(
    user_id: str,
    report_id: str,
    *,
    payment_id: str,
    order_id: str,
    amount_paise: int,
    currency: str,
) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        client.table("report_unlocks").upsert(
            {
                "user_id": user_id,
                "report_id": report_id,
                "payment_id": payment_id,
                "order_id": order_id,
                "amount_paise": amount_paise,
                "currency": currency,
            },
            on_conflict="user_id,report_id",
        ).execute()
        return True
    except Exception as exc:
        logger.warning("record_report_unlock failed: %s", exc)
        return False
