"""
Resolve the authenticated Supabase user from a request.

User identity MUST come from a verified access token — never from a client-supplied
X-User-Id header alone (that header is spoofable).
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Tuple

import requests
from flask import Request

from config import API_KEY, SUPABASE_ANON_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

# Short-lived cache so high-volume poll loops do not hammer Auth on every tick.
_TOKEN_CACHE: Dict[str, Tuple[float, str]] = {}
_TOKEN_CACHE_TTL_SEC = 45.0
_TOKEN_CACHE_MAX = 256


def _cache_get(token: str) -> Optional[str]:
    entry = _TOKEN_CACHE.get(token)
    if not entry:
        return None
    expires_at, user_id = entry
    if time.time() > expires_at:
        _TOKEN_CACHE.pop(token, None)
        return None
    return user_id


def _cache_set(token: str, user_id: str) -> None:
    if len(_TOKEN_CACHE) >= _TOKEN_CACHE_MAX:
        # Drop arbitrary oldest-ish entries
        for key in list(_TOKEN_CACHE.keys())[:64]:
            _TOKEN_CACHE.pop(key, None)
    _TOKEN_CACHE[token] = (time.time() + _TOKEN_CACHE_TTL_SEC, user_id)


def extract_bearer_token(request: Request) -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def verify_supabase_access_token(access_token: str) -> str:
    """
    Validate a Supabase user access token against Auth and return the user id.
    Returns "" if invalid / Auth unavailable.
    """
    token = (access_token or "").strip()
    if not token:
        return ""
    # Never treat the internal API key as a user session.
    if API_KEY and token == API_KEY:
        return ""

    cached = _cache_get(token)
    if cached is not None:
        return cached

    base = (SUPABASE_URL or "").rstrip("/")
    anon = (SUPABASE_ANON_KEY or "").strip()
    if not base or not anon:
        logger.warning("Supabase Auth not configured; cannot verify user JWT")
        return ""

    try:
        resp = requests.get(
            f"{base}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": anon,
            },
            timeout=8.0,
        )
    except Exception as exc:
        logger.warning("Supabase user verify failed: %s", exc)
        return ""

    if resp.status_code >= 400:
        return ""

    try:
        payload = resp.json()
    except Exception:
        return ""

    user_id = str((payload or {}).get("id") or "").strip()
    if user_id:
        _cache_set(token, user_id)
    return user_id


def resolve_authenticated_user_id(request: Request) -> str:
    """Authenticated user id for this request, or empty string."""
    return verify_supabase_access_token(extract_bearer_token(request))
