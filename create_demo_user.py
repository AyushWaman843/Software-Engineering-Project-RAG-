"""Create or update the public demo account for Cloudflare demos."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@anixai.io")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "DemoAnix2026!")


def main() -> int:
    url = os.getenv("SUPABASE_URL", "").strip()
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not service_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY required in .env")
        return 1

    from supabase import create_client

    client = create_client(url, service_key)
    user_id = None

    try:
        created = client.auth.admin.create_user(
            {
                "email": DEMO_EMAIL,
                "password": DEMO_PASSWORD,
                "email_confirm": True,
            }
        )
        user_id = created.user.id
        print(f"[OK] Created demo user {DEMO_EMAIL} ({user_id})")
    except Exception as exc:
        msg = str(exc).lower()
        if "already" in msg or "registered" in msg or "exists" in msg:
            anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
            if not anon_key:
                print("ERROR: demo user exists but SUPABASE_ANON_KEY missing for lookup")
                return 1
            anon = create_client(url, anon_key)
            try:
                signed_in = anon.auth.sign_in_with_password(
                    {"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
                )
                user_id = signed_in.user.id
                print(f"[OK] Demo user already exists ({user_id})")
            except Exception as sign_in_exc:
                print(f"ERROR: demo user exists but sign-in failed: {sign_in_exc}")
                return 1
        else:
            print(f"ERROR creating demo user: {exc}")
            return 1

    from dateutil.relativedelta import relativedelta

    now = datetime.now(timezone.utc)
    end = now + relativedelta(months=1)

    try:
        client.table("subscriptions").upsert(
            {
                "user_id": user_id,
                "tier": "pro",
                "status": "active",
                "current_start": now.isoformat(),
                "current_end": end.isoformat(),
                "updated_at": now.isoformat(),
            },
            on_conflict="user_id,tier",
        ).execute()
        print("[OK] Pro subscription active for demo user")
    except Exception as exc:
        print(f"WARN: Pro subscription setup failed (run migration?): {exc}")

    try:
        client.table("user_entitlements").upsert(
            {
                "user_id": user_id,
                "pro_scans_used": 0,
                "pro_scans_reset_at": end.isoformat(),
            },
            on_conflict="user_id",
        ).execute()
        print("[OK] Demo entitlements initialized (5 Pro scans)")
    except Exception as exc:
        print(f"WARN: entitlements setup failed: {exc}")

    print(f"\nDemo login:\n  Email:    {DEMO_EMAIL}\n  Password: {DEMO_PASSWORD}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
