"""
Security helpers: SSRF-safe URL validation and simple rate limiting.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Hostnames always blocked (cloud metadata, etc.)
_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "metadata.google.internal",
    "metadata.google",
})

# Private/reserved IP networks (SSRF protection)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


MAX_URL_LENGTH = 2048


class SSRFError(ValueError):
    """Raised when a URL targets a disallowed host."""


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    for network in _BLOCKED_NETWORKS:
        if addr in network:
            return True
    return False


def _resolve_host_ips(hostname: str) -> List[str]:
    """Resolve hostname to IP addresses for SSRF checks."""
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFError(f"Could not resolve hostname: {hostname}") from exc
    ips: List[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    return ips


def validate_scan_url(url: str) -> str:
    """
    Validate a user-supplied URL for scanning.
    Blocks private/internal hosts and non-http(s) schemes.

    Returns:
        Normalized URL string.

    Raises:
        SSRFError: If URL is not allowed.
    """
    cleaned = url.strip()
    if not cleaned:
        raise SSRFError("URL is required.")
    if len(cleaned) > MAX_URL_LENGTH:
        raise SSRFError(f"URL exceeds maximum length of {MAX_URL_LENGTH} characters.")

    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError("Only http and https URLs are allowed.")

    if parsed.username or parsed.password:
        raise SSRFError("URLs with embedded credentials are not allowed.")

    port = parsed.port
    if port is not None and port not in (80, 443):
        raise SSRFError("Only standard HTTP (80) and HTTPS (443) ports are allowed.")

    hostname = (parsed.hostname or "").lower().strip(".")
    if not hostname:
        raise SSRFError("URL must include a hostname.")

    if hostname in _BLOCKED_HOSTNAMES:
        raise SSRFError(f"Scanning {hostname} is not permitted.")

    if hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise SSRFError("Scanning local hostnames is not permitted.")

    # Literal IP in URL
    try:
        ipaddress.ip_address(hostname)
        if _is_blocked_ip(hostname):
            raise SSRFError("Scanning private or internal IP addresses is not permitted.")
        return cleaned
    except ValueError:
        pass

    # Resolve DNS and check all A/AAAA records
    for ip in _resolve_host_ips(hostname):
        if _is_blocked_ip(ip):
            raise SSRFError(
                f"URL resolves to a private or internal address ({ip}). Scanning is not permitted."
            )

    return cleaned


def is_safe_scan_url(url: str) -> bool:
    """Non-raising variant of validate_scan_url for redirect-hop checks."""
    try:
        validate_scan_url(url)
        return True
    except SSRFError:
        return False


def get_client_ip(request) -> str:
    """Best-effort client IP (respects X-Forwarded-For when behind one proxy)."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


class RateLimiter:
    """Thread-safe sliding-window rate limiter keyed by client IP."""

    def __init__(self, max_requests: int, window_seconds: int = 3600) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> Tuple[bool, Optional[int]]:
        """
        Check if request is allowed.

        Returns:
            (allowed, retry_after_seconds)
        """
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = [t for t in self._events[key] if t > cutoff]
            if len(timestamps) >= self.max_requests:
                oldest = min(timestamps)
                retry_after = int(self.window_seconds - (now - oldest)) + 1
                return False, retry_after
            timestamps.append(now)
            self._events[key] = timestamps
            return True, None

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)
