"""Tests for SSRF URL validation and rate limiting."""

import pytest

from security import RateLimiter, SSRFError, validate_scan_url


class TestSSRFValidation:
    def test_blocks_localhost(self):
        with pytest.raises(SSRFError):
            validate_scan_url("http://localhost/privacy")

    def test_blocks_private_ip_literal(self):
        with pytest.raises(SSRFError):
            validate_scan_url("http://192.168.1.1/admin")

    def test_allows_public_https(self):
        url = validate_scan_url("https://example.com/privacy")
        assert url == "https://example.com/privacy"

    def test_rejects_non_http_scheme(self):
        with pytest.raises(SSRFError):
            validate_scan_url("file:///etc/passwd")


class TestRateLimiter:
    def test_allows_under_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            allowed, _ = limiter.is_allowed("127.0.0.1")
            assert allowed is True

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed("client-a")
        limiter.is_allowed("client-a")
        allowed, retry_after = limiter.is_allowed("client-a")
        assert allowed is False
        assert retry_after is not None and retry_after > 0
