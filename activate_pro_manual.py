"""Manual Pro activation script - run after Supabase migration."""
import os
import sys
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

# Load environment
from dotenv import load_dotenv
load_dotenv()

from supabase_subscriptions import _get_client

def activate_pro_for_user(user_id: str):
    """Manually activate Pro for a user who already paid."""
    client = _get_client()
    if not client:
        print("ERROR: Supabase not configured")
        return False
    
    now = datetime.now(timezone.utc)
    end = now + relativedelta(months=1)
    
    # Create subscription record
    try:
        result = client.table("subscriptions").upsert({
            "user_id": user_id,
            "tier": "pro",
            "status": "active",
            "current_start": now.isoformat(),
            "current_end": end.isoformat(),
            "updated_at": now.isoformat(),
        }, on_conflict="user_id,tier").execute()
        
        print(f"[OK] Subscription created: {result.data}")
    except Exception as exc:
        print(f"ERROR creating subscription: {exc}")
        return False
    
    # Initialize entitlements
    try:
        result = client.table("user_entitlements").upsert({
            "user_id": user_id,
            "pro_scans_used": 0,
            "pro_scans_reset_at": end.isoformat(),
        }, on_conflict="user_id").execute()
        
        print(f"[OK] Entitlements initialized: {result.data}")
    except Exception as exc:
        print(f"ERROR updating entitlements: {exc}")
        return False
    
    print(f"\n[SUCCESS] Pro activated for user {user_id}")
    print(f"  Valid until: {end.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Scans: 5 available")
    return True

if __name__ == "__main__":
    # Default user ID from logs (user who just paid)
    default_user_id = "be406f75-4ac6-471c-88d2-475894bff85c"
    
    if len(sys.argv) < 2:
        user_id = default_user_id
        print(f"Using default user ID from logs: {user_id}")
    else:
        user_id = sys.argv[1]
    
    print(f"\nActivating Pro for user: {user_id}\n")
    
    success = activate_pro_for_user(user_id)
    
    if success:
        print("\n" + "="*60)
        print("[SUCCESS] PRO ACTIVATED!")
        print("="*60)
        print("\nRefresh http://localhost:3001 to see your Pro subscription.")
        print("You should see: '5 of 5 Pro scans available'")
        print("="*60)
    
    sys.exit(0 if success else 1)
