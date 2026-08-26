"""Cloudflare Turnstile verification for bot protection."""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
# When secret is unset, skip checks (local/dev). Set TURNSTILE_REQUIRED=1 to hard-fail.
TURNSTILE_REQUIRED = os.getenv("TURNSTILE_REQUIRED", "0").strip() == "1"


def turnstile_configured() -> bool:
    return bool(TURNSTILE_SECRET_KEY)


def captcha_enforced() -> bool:
    """True when CAPTCHA must be configured and verified (env flag or production)."""
    from config import is_production

    return TURNSTILE_REQUIRED or is_production()


def verify_turnstile_token(
    token: Optional[str],
    remote_ip: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Verify a Cloudflare Turnstile response token.

    Returns (ok, error_message). When not configured and not required, returns (True, "").
    """
    if not TURNSTILE_SECRET_KEY:
        if captcha_enforced():
            return False, "CAPTCHA is required but not configured on the server."
        return True, ""

    cleaned = (token or "").strip()
    if not cleaned:
        return False, "Please complete the CAPTCHA and try again."

    payload = {
        "secret": TURNSTILE_SECRET_KEY,
        "response": cleaned,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(TURNSTILE_VERIFY_URL, data=payload)
            data = resp.json()
    except Exception as exc:
        logger.warning("Turnstile verify request failed: %s", exc)
        return False, "CAPTCHA verification failed. Please try again."

    if data.get("success") is True:
        return True, ""

    codes = data.get("error-codes") or []
    logger.info("Turnstile rejected token: %s", codes)
    return False, "CAPTCHA check failed. Please refresh and try again."
