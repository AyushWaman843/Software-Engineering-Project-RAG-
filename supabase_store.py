"""Persist scan reports and jobs in Supabase (survives Render free-tier disk wipes)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase_entitlements import supabase_configured

logger = logging.getLogger(__name__)


def _client():
    if not supabase_configured():
        return None
    from supabase_entitlements import _get_client

    return _get_client()


def upsert_scan_report(report_id: str, payload: Dict[str, Any]) -> bool:
    client = _client()
    if not client or not report_id or not isinstance(payload, dict):
        return False
    try:
        now = datetime.now(timezone.utc).isoformat()
        client.table("scan_reports").upsert(
            {
                "report_id": report_id,
                "payload": payload,
                "updated_at": now,
            },
            on_conflict="report_id",
        ).execute()
        return True
    except Exception as exc:
        logger.warning("upsert_scan_report failed for %s: %s", report_id, exc)
        return False


def fetch_scan_report(report_id: str) -> Optional[Dict[str, Any]]:
    client = _client()
    if not client or not report_id:
        return None
    try:
        result = (
            client.table("scan_reports")
            .select("payload")
            .eq("report_id", report_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        payload = rows[0].get("payload")
        if not isinstance(payload, dict):
            return None
        data = dict(payload)
        data["_report_id"] = report_id
        return data
    except Exception as exc:
        logger.warning("fetch_scan_report failed for %s: %s", report_id, exc)
        return None


def upsert_scan_job(job_id: str, payload: Dict[str, Any]) -> bool:
    client = _client()
    if not client or not job_id or not isinstance(payload, dict):
        return False
    try:
        now = datetime.now(timezone.utc).isoformat()
        client.table("scan_jobs").upsert(
            {
                "job_id": job_id,
                "payload": payload,
                "status": str(payload.get("status") or "running"),
                "updated_at": now,
            },
            on_conflict="job_id",
        ).execute()
        return True
    except Exception as exc:
        logger.warning("upsert_scan_job failed for %s: %s", job_id, exc)
        return False


def fetch_scan_job(job_id: str) -> Optional[Dict[str, Any]]:
    client = _client()
    if not client or not job_id:
        return None
    try:
        result = (
            client.table("scan_jobs")
            .select("payload")
            .eq("job_id", job_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        payload = rows[0].get("payload")
        return dict(payload) if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("fetch_scan_job failed for %s: %s", job_id, exc)
        return None


def list_running_scan_jobs() -> List[Dict[str, Any]]:
    client = _client()
    if not client:
        return []
    try:
        result = (
            client.table("scan_jobs")
            .select("job_id, payload")
            .eq("status", "running")
            .limit(200)
            .execute()
        )
        out: List[Dict[str, Any]] = []
        for row in result.data or []:
            payload = row.get("payload")
            if isinstance(payload, dict):
                job = dict(payload)
                job.setdefault("id", row.get("job_id"))
                out.append(job)
        return out
    except Exception as exc:
        logger.warning("list_running_scan_jobs failed: %s", exc)
        return []
