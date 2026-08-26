"""Keep Supabase rows aligned with on-disk report state and quota."""

from __future__ import annotations

import logging
from typing import Optional

from supabase_entitlements import (
    is_report_unlocked,
    list_db_unlocked_report_ids,
    list_user_report_ids,
    sync_file_unlock_to_db,
)

logger = logging.getLogger(__name__)


def list_unlocked_report_ids_for_user(user_id: str) -> list[str]:
    """
    Report IDs this account has paid to unlock.
    Checks Supabase first, then owned report files (and backfills DB when needed).
    """
    if not user_id:
        return []

    unlocked: set[str] = set(list_db_unlocked_report_ids(user_id))

    for report_id in list_user_report_ids(user_id, limit=64):
        if report_id in unlocked:
            continue
        from scan_runner import load_report_by_id

        report = load_report_by_id(report_id)
        if not report or not report.get("premium_unlocked"):
            continue
        unlock_user = str(report.get("premium_unlocked_user_id") or "").strip()
        if unlock_user != user_id:
            continue
        unlocked.add(report_id)
        sync_file_unlock_to_db(user_id, report_id, report)

    # Legacy unlocks on disk not yet linked in user_scans
    from scan_runner import load_recent_reports

    for report in load_recent_reports(limit=150):
        report_id = str(report.get("_report_id") or "").strip()
        if not report_id or report_id in unlocked:
            continue
        if not report.get("premium_unlocked"):
            continue
        unlock_user = str(report.get("premium_unlocked_user_id") or "").strip()
        if unlock_user != user_id:
            continue
        unlocked.add(report_id)
        sync_file_unlock_to_db(user_id, report_id, report)

    return sorted(unlocked)


def reconcile_user_account(user_id: Optional[str]) -> None:
    """Sync premium unlocks and scan quota from authoritative sources before reads."""
    if not user_id:
        return
    try:
        from supabase_entitlements import sync_entitlements_from_scans
        from supabase_subscriptions import sync_pro_scan_usage

        list_unlocked_report_ids_for_user(user_id)
        sync_entitlements_from_scans(user_id)
        sync_pro_scan_usage(user_id)
    except Exception as exc:
        logger.warning("reconcile_user_account failed for %s: %s", user_id[:8], exc)


def user_has_report_access(user_id: Optional[str], report_id: str, report: dict) -> bool:
    """
    True when this signed-in user may view the full report.
    - Explicit ₹299 unlock
    - Pilot / legacy Pro owners of the scan (full access to their own reports)
    """
    if not user_id:
        return False

    # Check if report was explicitly unlocked (one-time ₹299 payment)
    if is_report_unlocked(user_id, report_id):
        return True

    if report.get("premium_unlocked"):
        unlock_user = str(report.get("premium_unlocked_user_id") or "").strip()
        if unlock_user == user_id:
            sync_file_unlock_to_db(user_id, report_id, report)
            return True
        # Legacy unlocks without a user binding: do not treat as global premium.
        if not unlock_user:
            return False

    owner_id = str(report.get("owner_user_id") or "").strip()
    if owner_id != user_id:
        return False

    # Pilot (TrustStack) — full access to own scans
    try:
        from truststack_tiers import user_has_pilot

        if user_has_pilot(user_id):
            return True
    except Exception:
        pass

    # Legacy Pro subscribers
    from supabase_subscriptions import user_has_active_pro

    if user_has_active_pro(user_id):
        return True

    return False
