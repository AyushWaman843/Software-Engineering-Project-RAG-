#!/usr/bin/env python3
"""
Reset all Supabase app data + auth users, and clear premium flags on local report JSON.

Usage (from dpdp_comp/):
  python scripts/reset_all_data.py

Auth user deletion uses the Supabase Auth Admin REST API (httpx) so it works with
both legacy JWT service keys and newer sb_secret_* keys.
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

from config import DATA_DIR, RESULTS_DIR, SUPABASE_SERVICE_KEY, SUPABASE_URL


def _client():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    from supabase import create_client

    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def _auth_headers() -> dict[str, str]:
    key = SUPABASE_SERVICE_KEY.strip()
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
    }


def clear_public_tables(client) -> None:
    """Delete all rows from public app tables."""
    tables_filters = [
        ("report_unlocks", "report_id", ""),
        ("user_scans", "report_id", ""),
        ("user_entitlements", "user_id", "00000000-0000-0000-0000-000000000000"),
        ("visitor_scans", "visitor_id", ""),
        ("premium_grants", "visitor_id", ""),
    ]
    for table, column, sentinel in tables_filters:
        try:
            client.table(table).delete().neq(column, sentinel).execute()
            print(f"  cleared {table}")
        except Exception as exc:
            print(f"  warn {table}: {exc}")


def delete_all_auth_users_rest() -> int:
    """Remove every Supabase Auth user via Auth Admin REST API."""
    base = SUPABASE_URL.rstrip("/")
    headers = _auth_headers()
    deleted = 0
    page = 1
    per_page = 200

    with httpx.Client(timeout=30.0) as http:
        while True:
            list_url = f"{base}/auth/v1/admin/users"
            resp = http.get(
                list_url,
                headers=headers,
                params={"page": page, "per_page": per_page},
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Auth admin list failed HTTP {resp.status_code}: {resp.text[:300]}"
                )

            payload = resp.json()
            users = payload.get("users") if isinstance(payload, dict) else payload
            if not isinstance(users, list) or not users:
                break

            for user in users:
                uid = str((user or {}).get("id") or "").strip()
                email = (user or {}).get("email") or uid[:8]
                if not uid:
                    continue
                del_resp = http.delete(f"{base}/auth/v1/admin/users/{uid}", headers=headers)
                if del_resp.status_code >= 400:
                    print(f"  warn delete {email}: HTTP {del_resp.status_code}")
                    continue
                deleted += 1
                print(f"  deleted user {email}")

            if len(users) < per_page:
                break
            page += 1

    return deleted


def delete_all_auth_users(client) -> int:
    """Try Python SDK first, then REST Admin API."""
    try:
        deleted = 0
        page = 1
        per_page = 200
        while True:
            result = client.auth.admin.list_users(page=page, per_page=per_page)
            users = []
            if isinstance(result, dict):
                users = list(result.get("users") or [])
            else:
                users = list(getattr(result, "users", None) or [])
            if not users:
                break
            for user in users:
                if isinstance(user, dict):
                    uid = str(user.get("id") or "")
                    email = user.get("email") or uid[:8]
                else:
                    uid = str(getattr(user, "id", "") or "")
                    email = getattr(user, "email", "") or uid[:8]
                if not uid:
                    continue
                client.auth.admin.delete_user(uid)
                deleted += 1
                print(f"  deleted user {email}")
            if len(users) < per_page:
                break
            page += 1
        if deleted > 0:
            return deleted
    except Exception as exc:
        print(f"  SDK auth admin unavailable ({exc}); trying REST API…")

    return delete_all_auth_users_rest()


def clear_local_report_unlocks() -> int:
    """Strip premium/owner flags from on-disk report JSON (not deleted)."""
    count = 0
    ledger = DATA_DIR / "processed_webhook_payments.json"
    if ledger.is_file():
        ledger.write_text("[]", encoding="utf-8")
        print("  cleared processed_webhook_payments.json")

    for path in RESULTS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        keys = (
            "premium_unlocked",
            "premium_unlocked_at",
            "premium_unlocked_user_id",
            "premium_payment_id",
            "premium_order_id",
            "owner_user_id",
        )
        changed = any(k in data for k in keys)
        if not changed:
            continue
        for k in keys:
            data.pop(k, None)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        count += 1
        print(f"  reset local report {path.name}")
    return count


def main() -> None:
    print("Resetting Supabase public tables…")
    client = _client()
    clear_public_tables(client)

    print("Deleting all auth users…")
    n_users = delete_all_auth_users(client)

    print("Clearing local report unlock flags…")
    n_reports = clear_local_report_unlocks()

    print(
        f"\nDone. Removed {n_users} auth user(s), "
        f"cleared public tables, reset {n_reports} local report file(s)."
    )
    print("Sign up again with a fresh account to test.")
    print("Alternative: run supabase/reset_all_data.sql in Supabase SQL Editor.")


if __name__ == "__main__":
    main()
