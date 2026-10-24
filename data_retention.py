"""Remove temporary scan data; reports remain available until account deletion."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone

from config import JOBS_DIR, UPLOADS_DIR

logger = logging.getLogger(__name__)
TEMP_DATA_DAYS = 30


def purge_expired_runtime_data(now: datetime | None = None) -> None:
    """Delete completed job details and legacy raw uploads older than 30 days."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=TEMP_DATA_DAYS)
    cutoff_ts = cutoff.timestamp()

    for path in JOBS_DIR.glob("*.json"):
        try:
            if path.stat().st_mtime >= cutoff_ts:
                continue
            job = json.loads(path.read_text(encoding="utf-8"))
            if job.get("status") != "running":
                path.unlink()
        except (OSError, ValueError) as exc:
            logger.warning("Could not inspect old job %s: %s", path, exc)

    uploads_root = UPLOADS_DIR.resolve()
    for path in UPLOADS_DIR.iterdir():
        try:
            if path.stat().st_mtime < cutoff_ts:
                if path.is_symlink():
                    path.unlink()
                elif not path.resolve().is_relative_to(uploads_root):
                    logger.warning("Old upload resolved outside uploads directory: %s", path)
                elif path.is_dir():
                    shutil.rmtree(path)
                elif path.is_file():
                    path.unlink()
        except OSError as exc:
            logger.warning("Could not remove old upload %s: %s", path, exc)

    try:
        from supabase_entitlements import _get_client

        client = _get_client()
        if client:
            client.table("scan_jobs").delete().neq("status", "running").lt(
                "updated_at", cutoff.isoformat()
            ).execute()
    except Exception as exc:
        logger.warning("Could not purge old Supabase jobs: %s", exc)
