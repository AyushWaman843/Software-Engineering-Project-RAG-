"""Tests for redirect-aware SSRF protection.

A public URL must not be able to 3xx-bounce the fetcher to an internal or
cloud-metadata address. fetch_with_requests follows redirects manually and
re-validates every hop.
"""

import pytest

import scraper
from security import SSRFError, is_safe_scan_url


class TestIsSafeScanUrl:
    def test_public_literal_ip_allowed(self):
        assert is_safe_scan_url("http://8.8.8.8/privacy") is True

    def test_loopback_blocked(self):
        assert is_safe_scan_url("http://127.0.0.1/") is False

    def test_metadata_ip_blocked(self):
        assert is_safe_scan_url("http://169.254.169.254/latest/meta-data/") is False

    def test_private_ip_blocked(self):
        assert is_safe_scan_url("http://10.0.0.5/") is False

    def test_non_http_scheme_blocked(self):
        assert is_safe_scan_url("file:///etc/passwd") is False


class _FakeResponse:
    def __init__(self, status_code=200, text="<html>ok</html>", location=None):
        self.status_code = status_code
        self.text = text
        self.headers = {"Location": location} if location else {}

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308) and "Location" in self.headers

    def raise_for_status(self):
        if self.status_code >= 400:
            raise scraper.requests.HTTPError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        return self._responses.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _fake_validate(url):
    """Block internal/metadata targets without touching the network."""
    if any(bad in url for bad in ("127.0.0.1", "169.254", "localhost", "10.0.0")):
        raise SSRFError(f"blocked {url}")
    return url


@pytest.fixture(autouse=True)
def _allow_robots(monkeypatch):
    monkeypatch.setattr(scraper, "is_allowed_by_robots", lambda url: True)
    monkeypatch.setattr(scraper, "validate_scan_url", _fake_validate)


def _install_session(monkeypatch, responses):
    session = _FakeSession(responses)
    monkeypatch.setattr(scraper.requests, "Session", lambda: session)
    return session


def test_blocks_redirect_to_metadata(monkeypatch):
    _install_session(
        monkeypatch,
        [_FakeResponse(status_code=302, location="http://169.254.169.254/latest/meta-data/")],
    )
    with pytest.raises(scraper.ScraperError):
        scraper.fetch_with_requests("https://example.com/privacy")


def test_follows_safe_redirect(monkeypatch):
    session = _install_session(
        monkeypatch,
        [
            _FakeResponse(status_code=302, location="https://www.example.com/privacy"),
            _FakeResponse(status_code=200, text="<html><body>Policy body</body></html>"),
        ],
    )
    html, _soup = scraper.fetch_with_requests("https://example.com/privacy")
    assert "Policy body" in html
    assert session.requested == [
        "https://example.com/privacy",
        "https://www.example.com/privacy",
    ]


def test_too_many_redirects(monkeypatch):
    hops = [
        _FakeResponse(status_code=302, location=f"https://example.com/hop{i}")
        for i in range(scraper.MAX_REDIRECTS + 2)
    ]
    _install_session(monkeypatch, hops)
    with pytest.raises(scraper.ScraperError):
        scraper.fetch_with_requests("https://example.com/privacy")


def test_relative_redirect_resolved_and_followed(monkeypatch):
    session = _install_session(
        monkeypatch,
        [
            _FakeResponse(status_code=301, location="/legal/privacy"),
            _FakeResponse(status_code=200, text="<html><body>Relative ok</body></html>"),
        ],
    )
    html, _soup = scraper.fetch_with_requests("https://example.com/privacy")
    assert "Relative ok" in html
    assert session.requested[-1] == "https://example.com/legal/privacy"
