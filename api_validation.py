"""
Server-side input validation for Flask API endpoints.

Mirrors Zod schemas in web/src/lib/security/schemas.ts. Keeps validation
in Python because scan/auth APIs are served by Flask, not Next.js routes.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


class ValidationError(ValueError):
    """Raised when user input fails schema checks."""


def sanitize_text(value: Any, *, max_len: int = 256, field: str = "Input") -> str:
    """Strip control characters and enforce length."""
    if value is None:
        text = ""
    elif not isinstance(value, str):
        raise ValidationError(f"{field} must be a string.")
    else:
        text = value

    cleaned = CONTROL_CHARS.sub("", text.strip())
    if len(cleaned) > max_len:
        raise ValidationError(f"{field} exceeds maximum length of {max_len} characters.")
    return cleaned


def validate_pdf_reference(value: Any) -> str:
    """Organisation name or reference label for PDF upload scans."""
    ref = sanitize_text(value, max_len=200, field="Reference")
    if len(ref) < 2:
        raise ValidationError("Please enter an organisation name or reference URL.")
    return ref


def validate_scan_json_payload(data: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Validate JSON body for POST /api/scan (URL mode).
    Returns normalized string fields; URL SSRF checks run separately.
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")

    url = sanitize_text(data.get("url"), max_len=2048, field="URL")
    if not url:
        raise ValidationError("Please enter a valid website URL.")

    payload: Dict[str, str] = {"url": url}

    for key, label in (
        ("privacy_url", "Privacy Policy URL"),
        ("terms_url", "Terms of Service URL"),
        ("cookie_url", "Cookie Policy URL"),
    ):
        raw = data.get(key)
        if raw is None or str(raw).strip() == "":
            continue
        payload[key] = sanitize_text(raw, max_len=2048, field=label)

    input_mode = sanitize_text(data.get("input_mode") or "url", max_len=16, field="input_mode").lower()
    if input_mode not in ("url", "pdf"):
        raise ValidationError("Invalid input mode.")
    payload["input_mode"] = input_mode

    return payload
