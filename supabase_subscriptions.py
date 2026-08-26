"""Supabase operations for Pro subscriptions and scan tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from dateutil.relativedelta import relativedelta

from config import PRO_SCANS_PER_MONTH
from supabase_entitlements import _get_client, get_user_entitlements

logger = logging.getLogger(__name__)


def get_active_subscription(user_id: str, tier: str = "pro") -> Optional[Dict[str, Any]]:
    """Fetch the active subscription for a user (status='active')."""
    client = _get_client()
    if not client or not user_id:
        return None

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            result = (
                client.table("subscriptions")
                .select("*")
                .eq("user_id", user_id)
                .eq("tier", tier)
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if not rows:
                return None
            sub = rows[0]
            end_raw = sub.get("current_end")
            if end_raw:
                try:
                    end_dt = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) >= end_dt:
                        return None
                except Exception:
                    pass
            return sub
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                import time

                time.sleep(0.15 * (attempt + 1))
    logger.warning("get_active_subscription failed: %s", last_exc)
    return None


def upsert_subscription(
    user_id: str,
    razorpay_subscription_id: str,
    razorpay_plan_id: str,
    status: str,
    current_start: Optional[datetime] = None,
    current_end: Optional[datetime] = None,
    charge_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None,
    tier: str = "pro",
) -> bool:
    """Create or update a subscription record."""
    client = _get_client()
    if not client or not user_id:
        return False
    
    data: Dict[str, Any] = {
        "user_id": user_id,
        "tier": tier,
        "razorpay_subscription_id": razorpay_subscription_id,
        "razorpay_plan_id": razorpay_plan_id,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    if current_start:
        data["current_start"] = current_start.isoformat()
    if current_end:
        data["current_end"] = current_end.isoformat()
    if charge_at:
        data["charge_at"] = charge_at.isoformat()
    if ended_at:
        data["ended_at"] = ended_at.isoformat()
    
    try:
        for attempt in range(3):
            try:
                client.table("subscriptions").upsert(
                    data,
                    on_conflict="user_id,tier",
                ).execute()
                logger.info(
                    "Upserted subscription for user %s: %s (status=%s)",
                    user_id,
                    razorpay_subscription_id,
                    status,
                )
                return True
            except Exception as exc:
                if attempt < 2:
                    import time

                    time.sleep(0.15 * (attempt + 1))
                    continue
                raise exc
    except Exception as exc:
        logger.error("upsert_subscription failed: %s", exc)
        return False


def user_has_active_pro(user_id: str) -> bool:
    """Check if user has an active Pro subscription."""
    sub = get_active_subscription(user_id, tier="pro")
    return sub is not None


def get_pro_scans_remaining(user_id: str) -> int:
    """
    Calculate remaining Pro scans for the current billing period.
    Returns 0 if no active subscription or quota exhausted.
    """
    if not user_has_active_pro(user_id):
        return 0
    
    ent = get_user_entitlements(user_id)
    if not ent.get("pro_scans_reset_at"):
        ensure_pro_reset_date(user_id)
        ent = get_user_entitlements(user_id)

    used = int(ent.get("pro_scans_used") or 0)
    reset_at = ent.get("pro_scans_reset_at")
    
    # Check if we need to reset the counter (new month)
    now = datetime.now(timezone.utc)
    if reset_at:
        try:
            reset_dt = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
            if now >= reset_dt:
                # Reset the counter
                reset_pro_scan_counter(user_id)
                return PRO_SCANS_PER_MONTH
        except Exception as exc:
            logger.warning("Failed to parse pro_scans_reset_at: %s", exc)
    
    return max(0, PRO_SCANS_PER_MONTH - used)


def ensure_pro_reset_date(user_id: str) -> bool:
    """Set pro_scans_reset_at when missing without resetting pro_scans_used."""
    ent = get_user_entitlements(user_id)
    if ent.get("pro_scans_reset_at"):
        return True

    client = _get_client()
    if not client or not user_id:
        return False

    sub = get_active_subscription(user_id)
    next_reset: Optional[datetime] = None
    if sub and sub.get("current_end"):
        try:
            next_reset = datetime.fromisoformat(str(sub["current_end"]).replace("Z", "+00:00"))
        except Exception:
            next_reset = None
    if not next_reset:
        next_reset = datetime.now(timezone.utc) + relativedelta(months=1)

    try:
        client.table("user_entitlements").upsert(
            {
                "user_id": user_id,
                "pro_scans_used": int(ent.get("pro_scans_used") or 0),
                "pro_scans_reset_at": next_reset.isoformat(),
            },
            on_conflict="user_id",
        ).execute()
        return True
    except Exception as exc:
        logger.warning("ensure_pro_reset_date failed: %s", exc)
        return False


def sync_pro_scan_usage(user_id: str) -> None:
    """
    Align pro_scans_used with scans made while Pro was active.
    Fixes cases where a Pro scan was mis-counted as a free scan.
    """
    if not user_has_active_pro(user_id):
        return

    sub = get_active_subscription(user_id)
    if not sub:
        return

    client = _get_client()
    if not client:
        return

    pro_start_raw = sub.get("current_start")
    scans_during_pro = 0
    try:
        if pro_start_raw:
            pro_start = datetime.fromisoformat(str(pro_start_raw).replace("Z", "+00:00"))
            result = (
                client.table("user_scans")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .gte("scanned_at", pro_start.isoformat())
                .execute()
            )
            scans_during_pro = int(result.count or 0)
        else:
            from supabase_entitlements import count_user_scans

            scans_during_pro = count_user_scans(user_id)
    except Exception as exc:
        logger.warning("sync_pro_scan_usage count failed: %s", exc)
        return

    ent = get_user_entitlements(user_id)
    pro_used = int(ent.get("pro_scans_used") or 0)
    target_pro = min(scans_during_pro, PRO_SCANS_PER_MONTH)
    free_used = int(ent.get("free_scans_used") or 0)

    new_pro = max(pro_used, target_pro)
    misallocated_free = free_used if target_pro > 0 and scans_during_pro > 0 else 0
    new_free = max(0, free_used - (new_pro - pro_used) - misallocated_free) if new_pro > pro_used else (
        0 if target_pro > 0 and free_used > 0 else free_used
    )

    if new_pro == pro_used and new_free == free_used:
        return

    try:
        client.table("user_entitlements").upsert(
            {
                "user_id": user_id,
                "free_scans_used": new_free,
                "pro_scans_used": new_pro,
                "pro_scans_reset_at": ent.get("pro_scans_reset_at"),
            },
            on_conflict="user_id",
        ).execute()
        logger.info(
            "Synced Pro scan usage for user %s: %d/%d used (free=%d)",
            user_id,
            new_pro,
            PRO_SCANS_PER_MONTH,
            new_free,
        )
    except Exception as exc:
        logger.warning("sync_pro_scan_usage failed: %s", exc)


def reset_pro_scan_counter(user_id: str) -> bool:
    """Reset Pro scan counter to 0 and set next reset date to subscription anniversary (1 month from now)."""
    client = _get_client()
    if not client or not user_id:
        return False
    
    ent = get_user_entitlements(user_id)
    now = datetime.now(timezone.utc)
    
    # Next reset is exactly 1 month from now (subscription anniversary model)
    # This prevents gaming the system by subscribing at month-end
    next_reset = now + relativedelta(months=1)
    
    try:
        client.table("user_entitlements").upsert(
            {
                "user_id": user_id,
                "pro_scans_used": 0,
                "pro_scans_reset_at": next_reset.isoformat(),
            },
            on_conflict="user_id",
        ).execute()
        logger.info("Reset Pro scan counter for user %s, next reset: %s", user_id, next_reset.isoformat())
        return True
    except Exception as exc:
        logger.warning("reset_pro_scan_counter failed: %s", exc)
        return False


def consume_pro_scan(user_id: str) -> bool:
    """
    Consume one Pro scan slot.
    Returns True if successful, False if quota exhausted or no active subscription.
    """
    if not user_has_active_pro(user_id):
        return False
    
    remaining = get_pro_scans_remaining(user_id)
    if remaining <= 0:
        return False
    
    client = _get_client()
    if not client:
        return False
    
    ent = get_user_entitlements(user_id)
    used = int(ent.get("pro_scans_used") or 0)
    
    try:
        client.table("user_entitlements").upsert(
            {
                "user_id": user_id,
                "pro_scans_used": used + 1,
                "pro_scans_reset_at": ent.get("pro_scans_reset_at"),
            },
            on_conflict="user_id",
        ).execute()
        logger.info("Consumed Pro scan for user %s (%d/%d used)", user_id, used + 1, PRO_SCANS_PER_MONTH)
        return True
    except Exception as exc:
        logger.warning("consume_pro_scan failed: %s", exc)
        return False


def initialize_pro_subscription_scans(user_id: str) -> bool:
    """Initialize Pro scan counter when subscription becomes active."""
    client = _get_client()
    if not client or not user_id:
        return False
    
    ent = get_user_entitlements(user_id)
    now = datetime.now(timezone.utc)
    
    # Set reset date to exactly 1 month from now (subscription anniversary)
    # User pays on subscription date, scans reset on same day next month
    next_reset = now + relativedelta(months=1)
    
    try:
        client.table("user_entitlements").upsert(
            {
                "user_id": user_id,
                "pro_scans_used": 0,
                "pro_scans_reset_at": next_reset.isoformat(),
            },
            on_conflict="user_id",
        ).execute()
        logger.info("Initialized Pro subscription scans for user %s, next reset: %s", user_id, next_reset.isoformat())
        return True
    except Exception as exc:
        logger.warning("initialize_pro_subscription_scans failed: %s", exc)
        return False


def activate_pro_monthly_pass(
    user_id: str,
    *,
    payment_id: str,
    order_id: str,
) -> bool:
    """
    Activate Pro for 30 days after a one-time ₹999 order (no Razorpay Plan needed).
    """
    now = datetime.now(timezone.utc)
    period_end = now + relativedelta(months=1)
    sub_id = f"pass_{order_id[:24]}"

    ok = upsert_subscription(
        user_id,
        sub_id,
        "monthly_pass",
        "active",
        current_start=now,
        current_end=period_end,
        charge_at=period_end,
    )
    if not ok:
        return False

    if not initialize_pro_subscription_scans(user_id):
        logger.warning("Pro monthly pass activated but scan init failed for %s", user_id)
    logger.info("Pro monthly pass activated for user %s (payment %s)", user_id, payment_id)
    return True
