"""
Optional API key authentication for the scanner backend.
"""

from __future__ import annotations

from flask import Request

from config import API_KEY, is_production


def api_key_configured() -> bool:
    return bool(API_KEY)


def verify_api_key(request: Request) -> bool:
    """Return True if the request is authorized (or auth is disabled in non-production)."""
    if not API_KEY:
        # Fail closed in production — never expose the API without a shared secret.
        return not is_production()

    header_key = request.headers.get("X-API-Key", "").strip()
    if header_key and header_key == API_KEY:
        return True

    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token == API_KEY:
            return True

    return False
