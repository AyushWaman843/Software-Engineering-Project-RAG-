"""
TrustStack Unified Subscription Tiers for Scanner.

This module integrates the scanner with TrustStack's unified subscription system,
replacing the old Pro tier with the new Pilot tier.

Tiers:
  - Free: 1 lifetime preview scan, then ₹299/scan for full reports
  - Pilot: 1 scan/day with full reports, non-stackable daily limit

The daily_scan_usage table tracks Pilot users' daily scans.
The truststack_subscriptions table stores subscription status.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, date
from typing import Any, Dict, Optional

from supabase_entitlements import _get_client, supabase_configured

logger = logging.getLogger(__name__)

PILOT_SCANS_PER_DAY = 1


def get_truststack_subscription(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch the active TrustStack subscription for a user."""
    client = _get_client()
    if not client or not user_id:
        return None

    try:
        result = (
            client.table("truststack_subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .in_("status", ["active", "trialing"])
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        
        sub = rows[0]
        
        # Check if subscription has expired
        end_raw = sub.get("current_period_end")
        if end_raw:
            try:
                end_dt = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) >= end_dt:
                    return None
            except Exception:
                pass
        
        return sub
    except Exception as exc:
        logger.warning("get_truststack_subscription failed: %s", exc)
        return None


def get_user_tier(user_id: str) -> str:
    """
    Get the effective subscription tier for a user.
    Returns 'pilot' or 'free'.
    
    Also checks organization memberships for inherited subscriptions.
    """
    if not user_id:
        return "free"
    
    # Check personal subscription
    sub = get_truststack_subscription(user_id)
    if sub and sub.get("tier") == "pilot":
        return "pilot"
    
    # Check organization subscriptions
    client = _get_client()
    if client:
        try:
            # Get user's org memberships
            result = (
                client.table("organization_members")
                .select("org_id")
                .eq("user_id", user_id)
                .execute()
            )
            org_ids = [str(r.get("org_id")) for r in (result.data or []) if r.get("org_id")]
            
            if org_ids:
                # Check if any org has pilot subscription
                sub_result = (
                    client.table("truststack_subscriptions")
                    .select("tier")
                    .in_("org_id", org_ids)
                    .eq("tier", "pilot")
                    .in_("status", ["active", "trialing"])
                    .limit(1)
                    .execute()
                )
                if sub_result.data:
                    return "pilot"
        except Exception as exc:
            logger.warning("org subscription check failed: %s", exc)
    
    return "free"


def user_has_pilot(user_id: str) -> bool:
    """Check if user has an active Pilot subscription."""
    return get_user_tier(user_id) == "pilot"


def get_pilot_scans_today(user_id: str) -> int:
    """Get number of scans used today by a Pilot user."""
    client = _get_client()
    if not client or not user_id:
        return 0
    
    today = date.today().isoformat()
    
    try:
        result = (
            client.table("daily_scan_usage")
            .select("scans_used")
            .eq("user_id", user_id)
            .eq("scan_date", today)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return 0
        return int(rows[0].get("scans_used") or 0)
    except Exception as exc:
        logger.warning("get_pilot_scans_today failed: %s", exc)
        return 0


def get_pilot_scans_remaining(user_id: str) -> int:
    """Get remaining daily scans for a Pilot user. Returns 0 if not Pilot."""
    if not user_has_pilot(user_id):
        return 0
    used = get_pilot_scans_today(user_id)
    return max(0, PILOT_SCANS_PER_DAY - used)


def consume_pilot_scan(user_id: str) -> bool:
    """
    Consume one daily Pilot scan slot.
    Returns True if successful, False if daily limit reached or not Pilot.
    """
    if not user_has_pilot(user_id):
        return False
    
    if get_pilot_scans_remaining(user_id) <= 0:
        return False
    
    client = _get_client()
    if not client:
        return False
    
    today = date.today().isoformat()
    used = get_pilot_scans_today(user_id)
    
    try:
        client.table("daily_scan_usage").upsert(
            {
                "user_id": user_id,
                "scan_date": today,
                "scans_used": used + 1,
            },
            on_conflict="user_id,scan_date",
        ).execute()
        logger.info("Consumed Pilot scan for user %s (day %s, %d/%d used)", 
                   user_id, today, used + 1, PILOT_SCANS_PER_DAY)
        return True
    except Exception as exc:
        logger.warning("consume_pilot_scan failed: %s", exc)
        return False


def restore_pilot_scan(user_id: str) -> bool:
    """
    Restore a consumed Pilot scan (e.g., after failed scan).
    Only restores for today's date.
    """
    if not user_id:
        return False
    
    client = _get_client()
    if not client:
        return False
    
    today = date.today().isoformat()
    used = get_pilot_scans_today(user_id)
    
    if used <= 0:
        return True  # Nothing to restore
    
    try:
        client.table("daily_scan_usage").upsert(
            {
                "user_id": user_id,
                "scan_date": today,
                "scans_used": max(0, used - 1),
            },
            on_conflict="user_id,scan_date",
        ).execute()
        logger.info("Restored Pilot scan for user %s (day %s)", user_id, today)
        return True
    except Exception as exc:
        logger.warning("restore_pilot_scan failed: %s", exc)
        return False


def can_user_scan(user_id: str) -> Dict[str, Any]:
    """
    Check if user can perform a scan and return detailed status.
    
    Returns a dict with:
      - can_scan: bool
      - tier: 'free' | 'pilot'
      - scan_type: 'pilot_daily' | 'free_preview' | 'prepaid' | None
      - reason: string if can_scan is False
      - message: user-friendly message
      - scans_remaining: int
    """
    from supabase_entitlements import get_user_entitlements
    from config import FREE_SCANS_PER_USER
    
    if not user_id:
        return {
            "can_scan": False,
            "tier": "free",
            "scan_type": None,
            "reason": "sign_in_required",
            "message": "Sign in to run an assessment.",
            "scans_remaining": 0,
        }
    
    tier = get_user_tier(user_id)
    
    ent = get_user_entitlements(user_id)
    prepaid = int(ent.get("scan_credits") or 0)

    if tier == "pilot":
        remaining = get_pilot_scans_remaining(user_id)
        if remaining > 0:
            return {
                "can_scan": True,
                "tier": "pilot",
                "scan_type": "pilot_daily",
                "scans_remaining": remaining,
                "message": "Pilot: 1 full scan per day (does not stack).",
            }
        # Daily used — allow ₹299 prepaid full scans the same day
        if prepaid > 0:
            return {
                "can_scan": True,
                "tier": "pilot",
                "scan_type": "prepaid",
                "scans_remaining": prepaid,
                "message": "Daily Pilot scan used. Using a paid full-scan credit.",
            }
        return {
            "can_scan": False,
            "tier": "pilot",
            "scan_type": None,
            "reason": "daily_limit_reached",
            "message": (
                "You've used today's Pilot scan. "
                "Pay ₹299 for another full scan, or come back tomorrow."
            ),
            "scans_remaining": 0,
        }

    # Free tier
    free_used = int(ent.get("free_scans_used") or 0)

    # 1 lifetime preview scan
    if free_used < FREE_SCANS_PER_USER:
        return {
            "can_scan": True,
            "tier": "free",
            "scan_type": "free_preview",
            "message": "This is your free preview scan. Unlock the full report for ₹299.",
            "scans_remaining": FREE_SCANS_PER_USER - free_used,
        }

    # ₹299 pay-before-scan credits → full report
    if prepaid > 0:
        return {
            "can_scan": True,
            "tier": "free",
            "scan_type": "prepaid",
            "scans_remaining": prepaid,
        }

    return {
        "can_scan": False,
        "tier": "free",
        "scan_type": None,
        "reason": "payment_required",
        "message": (
            "Free preview used. Pay ₹299 for a full scan, "
            "unlock an existing report for ₹299, or upgrade to Pilot."
        ),
        "scans_remaining": 0,
    }


def quota_snapshot_unified(user_id: Optional[str]) -> Dict[str, Any]:
    """
    Unified quota snapshot that includes both old Pro and new Pilot tiers.
    This provides backward compatibility with existing UI while supporting new system.
    """
    from supabase_entitlements import get_user_entitlements
    from config import FREE_SCANS_PER_USER
    from user_reconcile import list_unlocked_report_ids_for_user, reconcile_user_account
    from supabase_subscriptions import get_pro_scans_remaining, user_has_active_pro
    
    if not user_id:
        return {
            "signed_in": False,
            "tier": "free",
            "free_scans_limit": FREE_SCANS_PER_USER,
            "free_scans_used": 0,
            "free_scans_remaining": 0,
            "prepaid_scans": 0,
            "scan_credits": 0,
            "pro_scans_remaining": 0,
            "pilot_scans_remaining": 0,
            "has_pro": False,
            "has_pilot": False,
            "can_scan": False,
            "requires_sign_in": True,
            "message": "Sign in to run an assessment.",
        }
    
    reconcile_user_account(user_id)
    
    tier = get_user_tier(user_id)
    has_pilot = tier == "pilot"
    pilot_remaining = get_pilot_scans_remaining(user_id) if has_pilot else 0
    
    # Also check legacy Pro for backward compat
    has_pro = user_has_active_pro(user_id)
    pro_remaining = get_pro_scans_remaining(user_id) if has_pro else 0
    
    ent = get_user_entitlements(user_id)
    free_used = int(ent.get("free_scans_used") or 0)
    prepaid = int(ent.get("scan_credits") or 0)
    free_remaining = max(0, FREE_SCANS_PER_USER - free_used)
    
    # Can scan if Pilot daily, free preview, prepaid credit, or legacy Pro remain
    can_scan = pilot_remaining > 0 or pro_remaining > 0 or free_remaining > 0 or prepaid > 0

    message = ""
    if not can_scan:
        if has_pilot:
            message = (
                "You've used today's Pilot scan. "
                "Pay ₹299 for another full scan, or come back tomorrow."
            )
        else:
            message = (
                "Free preview used. Pay ₹299 for a full scan, "
                "or unlock a past report for ₹299."
            )
    elif has_pilot and pilot_remaining > 0:
        message = "Pilot: 1 full scan remaining today."
    elif has_pilot and prepaid > 0:
        message = "Daily Pilot scan used. You have paid full-scan credits ready."
    elif free_remaining > 0:
        message = "1 free preview scan remaining."

    return {
        "signed_in": True,
        "tier": "pilot" if has_pilot else ("pro" if has_pro else "free"),
        "free_scans_limit": FREE_SCANS_PER_USER,
        "free_scans_used": free_used,
        "free_scans_remaining": free_remaining,
        "prepaid_scans": prepaid,
        "scan_credits": prepaid,
        "pro_scans_remaining": pro_remaining,
        "pilot_scans_remaining": pilot_remaining,
        "has_pro": has_pro,
        "has_pilot": has_pilot,
        "can_scan": can_scan,
        "requires_sign_in": False,
        "message": message,
        "unlocked_report_ids": list_unlocked_report_ids_for_user(user_id),
    }
