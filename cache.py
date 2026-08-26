"""
In-memory scan result cache to avoid duplicate DeepSeek API calls.
Entries expire after 24 hours; cache clears on application restart.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

# URL -> {"result": dict, "timestamp": float}
_scan_cache: Dict[str, Dict[str, Any]] = {}

CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _normalize_cache_key(url: str) -> str:
    """Normalize URL for consistent cache keys (lowercase host, no trailing slash)."""
    parsed = urlparse(url.strip())
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or ""
    return urlunparse((parsed.scheme.lower() or "https", netloc, path, "", "", ""))


def get_cached_llm_result(url: str) -> Optional[Dict[str, Any]]:
    """
    Return cached DeepSeek analysis if present and younger than 24 hours.
    """
    if not url:
        return None
    key = _normalize_cache_key(url)
    entry = _scan_cache.get(key)
    if not entry:
        return None
    age = time.time() - entry.get("timestamp", 0)
    if age > CACHE_TTL_SECONDS:
        del _scan_cache[key]
        logger.info("Scan cache expired for %s", key)
        return None
    logger.info("Using cached DeepSeek result for %s (age %.0f min)", key, age / 60)
    return entry.get("result")


def set_cached_llm_result(url: str, result: Dict[str, Any]) -> None:
    """Store DeepSeek analysis result with current timestamp."""
    if not url or not result:
        return
    key = _normalize_cache_key(url)
    _scan_cache[key] = {"result": result, "timestamp": time.time()}
    logger.info("Cached DeepSeek result for %s", key)


def clear_scan_cache() -> None:
    """Clear all cached scan results (e.g. for testing)."""
    _scan_cache.clear()
