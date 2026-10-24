#!/usr/bin/env python3
"""Remove one user's scanner data; optionally delete their Supabase Auth account.

Usage: python scripts/clear_user_data.py user@example.com [--delete-account]
Run only after verifying the account holder's request. Safe to retry after an error.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from config import JOBS_DIR, RESULTS_DIR, SUPABASE_SERVICE_KEY, SUPABASE_URL, UPLOADS_DIR


def headers() -> dict[str, str]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_KEY are required")
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }


def rows(http: httpx.Client, table: str, column: str, owner_filter: str, user_id: str) -> list[dict]:
    found = []
    offset = 0
    while True:
        response = http.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}",
            headers=headers(),
            params={"select": column, owner_filter: f"eq.{user_id}", "limit": 1000, "offset": offset},
        )
        response.raise_for_status()
        page = response.json()
        found.extend(page)
        if len(page) < 1000:
            return found
        offset += 1000


def find_user(http: httpx.Client, email: str) -> dict:
    page = 1
    while True:
        response = http.get(
            f"{SUPABASE_URL.rstrip('/')}/auth/v1/admin/users",
            headers=headers(), params={"page": page, "per_page": 200},
        )
        response.raise_for_status()
        users = response.json().get("users", [])
        for user in users:
            if str(user.get("email") or "").lower() == email.lower():
                return user
        if len(users) < 200:
            raise SystemExit("User not found")
        page += 1


def local_report_ids(user_id: str) -> set[str]:
    found = set()
    for path in RESULTS_DIR.glob("*.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if user_id in (report.get("owner_user_id"), report.get("premium_unlocked_user_id")):
                found.add(path.stem)
        except (OSError, ValueError):
            continue
    return found


def delete_local_data(user_id: str, report_ids: set[str]) -> None:
    for report_id in report_ids:
        if re.fullmatch(r"[A-Za-z0-9_-]+", report_id):
            (RESULTS_DIR / f"{report_id}.json").unlink(missing_ok=True)

    uploads_root = UPLOADS_DIR.resolve()
    for path in JOBS_DIR.glob("*.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if job.get("owner_user_id") != user_id:
            continue
        path.unlink()
        upload_dir = (UPLOADS_DIR / path.stem).resolve()
        if upload_dir.is_relative_to(uploads_root) and upload_dir.is_dir():
            shutil.rmtree(upload_dir)


def delete_remote_data(http: httpx.Client, user_id: str, report_ids: set[str]) -> None:
    base = SUPABASE_URL.rstrip("/")
    report_ids.update(r["report_id"] for r in rows(http, "user_scans", "report_id", "user_id", user_id))
    report_ids.update(r["report_id"] for r in rows(http, "report_unlocks", "report_id", "user_id", user_id))
    report_ids.update(r["report_id"] for r in rows(http, "scan_reports", "report_id", "payload->>owner_user_id", user_id))

    for report_id in report_ids:
        response = http.delete(
            f"{base}/rest/v1/scan_reports", headers=headers(),
            params={"report_id": f"eq.{report_id}"},
        )
        response.raise_for_status()

    targets = [
        ("scan_jobs", "payload->>owner_user_id"),
        ("report_unlocks", "user_id"),
        ("user_scans", "user_id"),
        ("user_entitlements", "user_id"),
        ("subscriptions", "user_id"),
        ("daily_scan_usage", "user_id"),
    ]
    for table, field in targets:
        response = http.delete(f"{base}/rest/v1/{table}", headers=headers(), params={field: f"eq.{user_id}"})
        response.raise_for_status()

    response = http.patch(
        f"{base}/rest/v1/visitor_scans", headers=headers(),
        params={"claimed_by_user_id": f"eq.{user_id}"}, json={"claimed_by_user_id": None},
    )
    response.raise_for_status()


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        raise SystemExit("Usage: python scripts/clear_user_data.py <email> [--delete-account]")
    delete_account = "--delete-account" in sys.argv[2:]
    with httpx.Client(timeout=30.0) as http:
        user_id = str(find_user(http, sys.argv[1].strip()).get("id") or "")
        if not user_id:
            raise SystemExit("User ID missing")
        report_ids = local_report_ids(user_id)
        delete_remote_data(http, user_id, report_ids)
        delete_local_data(user_id, report_ids)
        if delete_account:
            response = http.delete(
                f"{SUPABASE_URL.rstrip('/')}/auth/v1/admin/users/{user_id}", headers=headers()
            )
            response.raise_for_status()
    print(f"Deleted scanner data for {sys.argv[1]}; auth account {'deleted' if delete_account else 'kept'}.")


if __name__ == "__main__":
    main()
