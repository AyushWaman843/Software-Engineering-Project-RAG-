#!/usr/bin/env python3
"""
Clear all app data for one Supabase auth user (by email) without deleting the account.

Usage (from dpdp_comp/):
  python scripts/clear_user_data.py user@example.com
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import httpx

from config import RESULTS_DIR, SUPABASE_SERVICE_KEY, SUPABASE_URL


def _auth_headers() -> dict[str, str]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    key = SUPABASE_SERVICE_KEY.strip()
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
    }


def _rest_headers() -> dict[str, str]:
    return {**_auth_headers(), "Prefer": "return=minimal"}


def find_user_by_email(email: str) -> dict | None:
    base = SUPABASE_URL.rstrip("/")
    headers = _auth_headers()
    target = email.strip().lower()
    page = 1
    per_page = 200

    with httpx.Client(timeout=30.0) as http:
        while True:
            resp = http.get(
                f"{base}/auth/v1/admin/users",
                headers=headers,
                params={"page": page, "per_page": per_page},
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"Auth admin list failed HTTP {resp.status_code}: {resp.text[:300]}")

            payload = resp.json()
            users = payload.get("users") if isinstance(payload, dict) else payload
            if not isinstance(users, list) or not users:
                return None

            for user in users:
                user_email = str((user or {}).get("email") or "").strip().lower()
                if user_email == target:
                    return user

            if len(users) < per_page:
                return None
            page += 1


def clear_supabase_user_data(user_id: str) -> None:
    base = SUPABASE_URL.rstrip("/")
    headers = _rest_headers()

    tables = [
        ("report_unlocks", "user_id"),
        ("user_scans", "user_id"),
        ("subscriptions", "user_id"),
        ("user_entitlements", "user_id"),
    ]

    with httpx.Client(timeout=30.0) as http:
        for table, column in tables:
            try:
                resp = http.delete(
                    f"{base}/rest/v1/{table}",
                    headers=headers,
                    params={column: f"eq.{user_id}"},
                )
                if resp.status_code >= 400:
                    print(f"  warn {table}: HTTP {resp.status_code} {resp.text[:200]}")
                else:
                    print(f"  cleared {table}")
            except Exception as exc:
                print(f"  warn {table}: {exc}")

        try:
            resp = http.patch(
                f"{base}/rest/v1/visitor_scans",
                headers=headers,
                params={"claimed_by_user_id": f"eq.{user_id}"},
                json={"claimed_by_user_id": None},
            )
            if resp.status_code >= 400:
                print(f"  warn visitor_scans: HTTP {resp.status_code} {resp.text[:200]}")
            else:
                print("  cleared visitor_scans claims")
        except Exception as exc:
            print(f"  warn visitor_scans: {exc}")


def clear_local_reports_for_user(user_id: str) -> int:
    count = 0
    keys = (
        "premium_unlocked",
        "premium_unlocked_at",
        "premium_unlocked_user_id",
        "premium_payment_id",
        "premium_order_id",
        "owner_user_id",
    )
    for path in RESULTS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        owner = str(data.get("owner_user_id") or "").strip()
        premium_user = str(data.get("premium_unlocked_user_id") or "").strip()
        if owner != user_id and premium_user != user_id:
            continue

        for key in keys:
            data.pop(key, None)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        count += 1
        print(f"  reset local report {path.name}")
    return count


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/clear_user_data.py <email>")

    email = sys.argv[1].strip()
    if not email:
        raise SystemExit("Email is required")

    print(f"Looking up user {email}…")
    user = find_user_by_email(email)
    if not user:
        raise SystemExit(f"No auth user found for {email}")

    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise SystemExit("User record has no id")

    print(f"Found user id {user_id}")
    print("Clearing Supabase app data (account is kept)…")
    clear_supabase_user_data(user_id)

    print("Clearing local report ownership/unlock flags…")
    n_reports = clear_local_reports_for_user(user_id)

    print(
        f"\nDone. Cleared all app data for {email}. "
        f"Auth account preserved. Reset {n_reports} local report file(s)."
    )


if __name__ == "__main__":
    main()
