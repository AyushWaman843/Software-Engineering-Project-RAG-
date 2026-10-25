"""
In-memory cache of LLM analysis results (avoids duplicate API calls).

Entries are keyed by a hash of everything that determines the answer - policy
and terms text, cookie-banner flag, model and prompt version - not by URL. A URL
key returned a stale result whenever the same site was analysed again with more
text (confidence refinement) or after its policy changed. Entries expire after
24 hours; the cache is size-bounded (LRU), thread-safe, and clears on restart.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours
MAX_CACHE_ENTRIES = max(1, int(os.environ.get("LLM_CACHE_MAX_ENTRIES", "256")))

# key -> {"result": dict, "timestamp": float}
_scan_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_lock = threading.Lock()


def make_cache_key(*parts: object) -> str:
    """Stable digest of ``parts``; each part is length-prefixed so boundaries are unambiguous."""
    digest = hashlib.sha256()
    for part in parts:
        data = str(part).encode("utf-8", errors="replace")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def get_cached_llm_result(key: str) -> Optional[Dict[str, Any]]:
    """Return a copy of the cached analysis for ``key`` if present and younger than 24 hours."""
    if not key:
        return None
    with _lock:
        entry = _scan_cache.get(key)
        if not entry:
            return None
        age = time.time() - entry.get("timestamp", 0)
        if age > CACHE_TTL_SECONDS:
            del _scan_cache[key]
            logger.info("Scan cache expired for %s", key[:12])
            return None
        _scan_cache.move_to_end(key)
        result = copy.deepcopy(entry["result"])
    logger.info("Using cached DeepSeek result %s (age %.0f min)", key[:12], age / 60)
    return result


def set_cached_llm_result(key: str, result: Dict[str, Any]) -> None:
    """Store a copy of the analysis, evicting the least recently used entries when full."""
    if not key or not result:
        return
    with _lock:
        _scan_cache[key] = {"result": copy.deepcopy(result), "timestamp": time.time()}
        _scan_cache.move_to_end(key)
        while len(_scan_cache) > MAX_CACHE_ENTRIES:
            _scan_cache.popitem(last=False)
    logger.info("Cached DeepSeek result %s", key[:12])


def clear_scan_cache() -> None:
    """Clear all cached scan results (e.g. for testing)."""
    with _lock:
        _scan_cache.clear()
