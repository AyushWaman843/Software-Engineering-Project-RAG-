"""
Scan quota and per-user entitlements (Supabase-backed).

TrustStack Unified Tiers (new):
  - Free: 1 lifetime preview scan, then ₹299/scan for full reports
  - Pilot: 1 scan/day with full reports, non-stackable daily limit

Legacy tiers (still supported for backward compat):
  - Pro: 5 scans/month (being replaced by Pilot)
  - Pay-before-scan: ₹299 for one scan with auto-unlocked report
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from config import FREE_SCANS_PER_USER, PREMIUM_CURRENCY, PREMIUM_ENABLED, PREMIUM_FREE_ACCESS, PREMIUM_PRICE_PAISE
from supabase_entitlements import (
    claim_visitor_for_user,
    consume_user_scan,
    effective_free_scans_used,
    get_user_entitlements,
    grant_prepaid_scan,
    record_report_unlock,
    supabase_configured,
)
from user_reconcile import list_unlocked_report_ids_for_user, reconcile_user_account, user_has_report_access

logger = logging.getLogger(__name__)

# Re-export for entitlements and other modules.
__all__ = [
    "check_scan_allowed",
    "claim_anonymous_scan_for_user",
    "complete_report_unlock",
    "is_premium_user",
    "quota_snapshot",
    "reserve_scan",
    "unlock_prepaid_scan_report",
    "user_has_premium_nav_access",
    "user_has_report_access",
]


def is_premium_user(user_id: Optional[str]) -> bool:
    """True for Pilot / paid unlocks (nav styling — hide Get Pilot CTA)."""
    if not PREMIUM_ENABLED or PREMIUM_FREE_ACCESS:
        return True
    if not user_id:
        return False
    try:
        from truststack_tiers import user_has_pilot

        if user_has_pilot(user_id):
            return True
    except Exception:
        pass
    if list_unlocked_report_ids_for_user(user_id):
        return True
    return False


def user_has_premium_nav_access(
    user_id: Optional[str],
    req,
    *,
    report_id: Optional[str] = None,
) -> bool:
    """Premium nav badge — Pilot, paid unlock, global bypass, or current report access."""
    if is_premium_user(user_id):
        return True
    from entitlements import has_premium_access
    from scan_runner import load_report_by_id

    if report_id and user_id:
        report = load_report_by_id(report_id)
        if report and has_premium_access(report_id, report, req):
            return True
    return False


def _prepaid_scans(user_id: str) -> int:
    ent = get_user_entitlements(user_id)
    return int(ent.get("scan_credits") or 0)


def quota_snapshot(user_id: Optional[str], visitor_id: Optional[str]) -> Dict[str, Any]:
    """Public quota state for the UI (unified TrustStack tiers + legacy Pro)."""
    # Use the unified quota snapshot from truststack_tiers
    from truststack_tiers import quota_snapshot_unified
    return quota_snapshot_unified(user_id)


def check_scan_allowed(user_id: Optional[str], visitor_id: Optional[str]) -> Tuple[bool, str, str]:
    """Returns (allowed, error_message, error_code)."""
    from truststack_tiers import can_user_scan
    
    if not user_id:
        return False, "Sign in to run an assessment.", "SIGN_IN_REQUIRED"

    result = can_user_scan(user_id)
    if result["can_scan"]:
        return True, "", ""
    
    reason = result.get("reason", "")
    if reason == "sign_in_required":
        return False, result.get("message", "Sign in required"), "SIGN_IN_REQUIRED"
    if reason == "daily_limit_reached":
        return False, result.get("message", "Daily limit reached"), "DAILY_LIMIT_REACHED"
    if reason == "payment_required":
        return False, result.get("message", "Payment required"), "SCAN_QUOTA_EXCEEDED"
    
    return False, result.get("message", "Cannot scan"), "SCAN_QUOTA_EXCEEDED"


def _consume_prepaid_only(user_id: str) -> bool:
    """Decrement one pay-before-scan credit without touching free/Pilot quotas."""
    from supabase_entitlements import get_user_entitlements, _get_client

    client = _get_client()
    if not client or not user_id:
        return False
    ent = get_user_entitlements(user_id)
    prepaid = int(ent.get("scan_credits") or 0)
    if prepaid <= 0:
        return False
    try:
        client.table("user_entitlements").upsert(
            {"user_id": user_id, "scan_credits": prepaid - 1},
            on_conflict="user_id",
        ).execute()
        return True
    except Exception as exc:
        logger.warning("consume prepaid-only failed: %s", exc)
        return False


def reserve_scan(user_id: Optional[str], visitor_id: Optional[str]) -> Tuple[bool, str, str, str]:
    """
    Consume one scan slot when a job is accepted.
    Returns (allowed, error_message, error_code, slot_type).
    slot_type: 'pilot_daily' | 'pro' | 'free' | 'prepaid'
    """
    from truststack_tiers import can_user_scan, consume_pilot_scan

    allowed, message, code = check_scan_allowed(user_id, visitor_id)
    if not allowed:
        return False, message, code, ""

    if not user_id:
        return False, "Sign in to run an assessment.", "SIGN_IN_REQUIRED", ""

    result = can_user_scan(user_id)
    scan_type = result.get("scan_type")

    # Pilot: 1 full scan / day (non-stackable)
    if scan_type == "pilot_daily":
        if consume_pilot_scan(user_id):
            return True, "", "", "pilot_daily"
        return False, "Could not reserve Pilot scan quota.", "SCAN_QUOTA_ERROR", ""

    # ₹299 pay-before-scan (Free extras or Pilot same-day extras)
    if scan_type == "prepaid":
        if _consume_prepaid_only(user_id):
            return True, "", "", "prepaid"
        return False, "Could not reserve paid scan credit.", "SCAN_QUOTA_ERROR", ""

    # Free preview or legacy Pro
    slot_type = consume_user_scan(user_id)
    if not slot_type:
        return False, "Could not reserve scan quota.", "SCAN_QUOTA_ERROR", ""

    return True, "", "", slot_type


def complete_report_unlock(
    user_id: str,
    report_id: str,
    *,
    payment_id: str,
    order_id: str,
    amount_paise: int,
    currency: str,
) -> None:
    """Unlock one report permanently. Does not grant additional free or prepaid scans."""
    from entitlements import grant_premium_access

    try:
        grant_premium_access(
            report_id,
            payment_id=payment_id,
            order_id=order_id,
            user_id=user_id,
        )
    except Exception as exc:
        logger.error("Could not persist premium flag on report file: %s", exc)
        raise

    stored = record_report_unlock(
        user_id,
        report_id,
        payment_id=payment_id,
        order_id=order_id,
        amount_paise=amount_paise,
        currency=currency,
    )
    if not stored:
        logger.error(
            "Premium unlock saved on report file but Supabase row missing (user=%s report=%s)",
            user_id,
            report_id,
        )

    reconcile_user_account(user_id)


def unlock_prepaid_scan_report(user_id: str, report_id: str) -> None:
    """Auto-unlock a report after a pay-before-scan completes (already paid ₹299)."""
    complete_report_unlock(
        user_id,
        report_id,
        payment_id=f"prepaid-scan-{report_id[:24]}",
        order_id=f"prepaid-scan-{report_id[:24]}",
        amount_paise=PREMIUM_PRICE_PAISE,
        currency=PREMIUM_CURRENCY,
    )


def confirm_prepaid_scan_payment(user_id: str) -> bool:
    """Grant one prepaid scan slot after Razorpay verifies pay-before-scan checkout."""
    if not user_id:
        return False
    ok = grant_prepaid_scan(user_id)
    if ok:
        reconcile_user_account(user_id)
    return ok


def claim_anonymous_scan_for_user(user_id: str, visitor_id: Optional[str]) -> Dict[str, Any]:
    """Legacy: attach a prior anonymous scan to the signed-in account."""
    if not user_id or not visitor_id:
        return {"claimed": False}
    if not supabase_configured():
        return {"claimed": False}
    return claim_visitor_for_user(user_id, visitor_id)
