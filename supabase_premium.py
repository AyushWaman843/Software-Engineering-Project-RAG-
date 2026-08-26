"""Legacy visitor-based premium grants — superseded by report_unlocks per user.

TODO: Remove after confirming no production data depends on premium_grants.
Not used by current Free + One-Time Report tier logic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from config import SUPABASE_SERVICE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

_client = None


def supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _get_client():
    global _client
    if not supabase_configured():
        return None
    if _client is None:
        from supabase import create_client

        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


def record_premium_grant(
    visitor_id: str,
    *,
    payment_id: str,
    order_id: str,
    amount_paise: int,
    currency: str,
) -> None:
    """Store a verified payment grant linked to this browser visitor."""
    client = _get_client()
    if not client or not visitor_id:
        return
    try:
        client.table("premium_grants").upsert(
            {
                "visitor_id": visitor_id,
                "payment_id": payment_id,
                "order_id": order_id,
                "amount_paise": amount_paise,
                "currency": currency,
            },
            on_conflict="payment_id",
        ).execute()
        _has_active_grant.cache_clear()
        logger.info("Supabase premium grant saved for visitor %s", visitor_id[:8])
    except Exception as exc:
        logger.warning("Could not save premium grant to Supabase: %s", exc)


@lru_cache(maxsize=512)
def _has_active_grant(visitor_id: str) -> bool:
    client = _get_client()
    if not client or not visitor_id:
        return False
    try:
        result = (
            client.table("premium_grants")
            .select("id, expires_at")
            .eq("visitor_id", visitor_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return False
        expires_at = rows[0].get("expires_at")
        if not expires_at:
            return True
        expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        return expiry > datetime.now(timezone.utc)
    except Exception as exc:
        logger.warning("Supabase premium grant lookup failed: %s", exc)
        return False


def has_active_premium_grant(visitor_id: Optional[str]) -> bool:
    if not visitor_id or not supabase_configured():
        return False
    return _has_active_grant(visitor_id)
