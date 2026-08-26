"""
Premium / paywall entitlements for report access.

Tiers (current):
  - Free: 1 lifetime preview scan per signed-in user.
  - One-Time Report: ₹299 permanently unlocks one report (no extra free scans).

TODO: Pro / Enterprise subscription tiers are planned but not implemented.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from flask import Request

from config import PREMIUM_ENABLED, PREMIUM_FREE_ACCESS
from user_reconcile import user_has_report_access
from scan_runner import load_report_by_id

logger = logging.getLogger(__name__)


def _user_id_from_request(req: Optional[Request]) -> str:
    if req is None:
        return ""
    from auth_user import resolve_authenticated_user_id

    return resolve_authenticated_user_id(req)


def resolve_report_owner(report_id: str, report: dict) -> str:
    """User who owns this assessment, if any (file owner wins over later DB inserts)."""
    from supabase_entitlements import get_report_owner_user_id

    # Prefer the owner stamped at scan completion — never let a later user_scans
    # insert override the canonical file owner (ownership-hijack defense).
    file_owner = str(report.get("owner_user_id") or "").strip()
    if file_owner:
        return file_owner
    return get_report_owner_user_id(report_id) or ""


def report_view_denied(report_id: str, report: dict, req: Optional[Request]):
    """
    Return a Flask (response, status) tuple when the viewer may not access this report.

    Requires a verified session user. Orphan reports (no owner) are denied so
    guessable/legacy IDs cannot leak assessments.
    """
    from flask import jsonify

    viewer = _user_id_from_request(req)
    if not viewer:
        return (
            jsonify(
                {
                    "error": "Sign in to view this assessment.",
                    "code": "SIGN_IN_REQUIRED",
                }
            ),
            403,
        )

    owner = resolve_report_owner(report_id, report)
    if not owner:
        return (
            jsonify(
                {
                    "error": "This assessment is not available.",
                    "code": "REPORT_UNAVAILABLE",
                }
            ),
            403,
        )
    if viewer != owner:
        return (
            jsonify(
                {
                    "error": "You do not have access to this assessment.",
                    "code": "ACCESS_DENIED",
                }
            ),
            403,
        )

    return None


def assign_report_owner(report_id: str, user_id: str, report: Optional[dict] = None) -> None:
    """Persist scan ownership on the report file and in Supabase."""
    if not user_id or not report_id:
        return
    from supabase_entitlements import record_user_scan

    meta = report or {}
    if not meta:
        loaded = load_report_by_id(report_id)
        meta = loaded or {}

    record_user_scan(
        user_id,
        report_id,
        url=str(meta.get("url") or ""),
        score=int(meta.get("score") or 0),
        verdict=str(meta.get("verdict") or ""),
    )

    stored = load_report_by_id(report_id)
    if not stored:
        return
    if stored.get("owner_user_id") == user_id:
        return

    filepath = stored.pop("_filepath", None)
    stored.pop("_report_id", None)
    stored["owner_user_id"] = user_id
    if filepath:
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(stored, handle, indent=2)


def has_premium_access(report_id: str, report: dict, req: Optional[Request]) -> bool:
    """True when the caller may receive full report data and PDF."""
    if not PREMIUM_ENABLED:
        return True
    if PREMIUM_FREE_ACCESS:
        return True
    user_id = _user_id_from_request(req)
    if not user_id:
        return False
    return user_has_report_access(user_id, report_id, report)


def grant_premium_access(
    report_id: str,
    *,
    payment_id: str = "",
    order_id: str = "",
    user_id: str = "",
) -> None:
    """Persist unlock on the report file."""
    report = load_report_by_id(report_id)
    if not report:
        raise FileNotFoundError("Report not found.")
    filepath = report.pop("_filepath", None)
    report.pop("_report_id", None)
    existing_user = str(report.get("premium_unlocked_user_id") or "").strip()
    if report.get("premium_unlocked") and user_id and existing_user == user_id:
        return
    if report.get("premium_unlocked") and existing_user and not user_id:
        return
    report["premium_unlocked"] = True
    report["premium_unlocked_at"] = datetime.now(timezone.utc).isoformat()
    if user_id:
        report["premium_unlocked_user_id"] = user_id
    if payment_id:
        report["premium_payment_id"] = payment_id
    if order_id:
        report["premium_order_id"] = order_id
    if not filepath:
        raise RuntimeError("Report filepath missing.")
    with open(filepath, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    logger.info("Premium unlocked for report %s", report_id)
