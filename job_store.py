"""
Scan job persistence: local disk + Supabase (survives Render free-tier wipes).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from config import JOBS_DIR

logger = logging.getLogger(__name__)

JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _job_path(job_id: str) -> Path:
    safe_id = "".join(c for c in job_id if c.isalnum())
    return JOBS_DIR / f"{safe_id}.json"


def _serialize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Persist job metadata without embedding the full report payload."""
    payload = {k: v for k, v in job.items() if k != "report"}
    report = job.get("report")
    if isinstance(report, dict):
        payload["report_summary"] = {
            "score": report.get("score"),
            "verdict": report.get("verdict"),
        }
    return payload


def _maybe_refund_failed_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Refund consumed quota once when a job ends in error."""
    if job.get("status") != "error" or job.get("credit_refunded"):
        return job
    owner = (job.get("owner_user_id") or "").strip()
    slot = (job.get("scan_slot_type") or "").strip()
    if not owner or slot not in ("free", "prepaid", "pro"):
        return job
    try:
        from supabase_entitlements import restore_scan_slot

        if restore_scan_slot(owner, slot):
            job["credit_refunded"] = True
            logger.info(
                "Refunded %s scan slot for user %s (job %s)",
                slot,
                owner,
                job.get("id"),
            )
    except Exception as exc:
        logger.warning("credit refund failed: %s", exc)
    return job


def save_job(job_id: str, job: Dict[str, Any]) -> None:
    job = _maybe_refund_failed_job(job)
    path = _job_path(job_id)
    serialized = _serialize_job(job)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2)
    except OSError as exc:
        logger.error("Failed to persist job %s: %s", job_id, exc)
    try:
        from supabase_store import upsert_scan_job

        upsert_scan_job(job_id, serialized)
    except Exception as exc:
        logger.warning("Supabase job upsert skipped for %s: %s", job_id, exc)


def load_job(job_id: str) -> Optional[Dict[str, Any]]:
    path = _job_path(job_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            summary = data.pop("report_summary", None)
            if summary:
                data["report"] = summary
            return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load job %s: %s", job_id, exc)

    try:
        from supabase_store import fetch_scan_job

        data = fetch_scan_job(job_id)
        if not data:
            return None
        summary = data.pop("report_summary", None)
        if summary:
            data["report"] = summary
        # Cache locally for subsequent reads when disk is writable.
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(_serialize_job(data), f, indent=2)
        except OSError:
            pass
        return data
    except Exception as exc:
        logger.warning("Supabase job fetch failed for %s: %s", job_id, exc)
        return None


def mark_stale_running_jobs() -> None:
    """On startup, fail jobs left running by a previous process (local + Supabase)."""
    seen: set[str] = set()

    def _fail(job: Dict[str, Any], job_id: str) -> None:
        if job.get("status") != "running":
            return
        job["status"] = "error"
        job["error"] = "Scan interrupted by server restart. Please run a new assessment."
        job["progress"] = 100
        job["message"] = "Interrupted"
        job["updated_at"] = datetime.now().isoformat()
        save_job(job_id, job)
        logger.warning("Marked stale running job as failed: %s", job_id)

    for path in JOBS_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                job = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        job_id = str(job.get("id") or path.stem)
        seen.add(job_id)
        _fail(job, job_id)

    try:
        from supabase_store import list_running_scan_jobs

        for job in list_running_scan_jobs():
            job_id = str(job.get("id") or "").strip()
            if not job_id or job_id in seen:
                continue
            _fail(job, job_id)
    except Exception as exc:
        logger.warning("Supabase stale-job sweep failed: %s", exc)


def count_running_jobs() -> int:
    count = 0
    seen: set[str] = set()
    for path in JOBS_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                job = json.load(f)
            job_id = str(job.get("id") or path.stem)
            seen.add(job_id)
            if job.get("status") == "running":
                count += 1
        except (OSError, json.JSONDecodeError):
            continue
    try:
        from supabase_store import list_running_scan_jobs

        for job in list_running_scan_jobs():
            job_id = str(job.get("id") or "").strip()
            if not job_id or job_id in seen:
                continue
            if job.get("status") == "running":
                count += 1
    except Exception:
        pass
    return count
