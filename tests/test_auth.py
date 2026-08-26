"""Tests for API key authentication."""

from auth import api_key_configured, verify_api_key


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


def test_auth_disabled_when_no_key(monkeypatch):
    monkeypatch.setattr("auth.API_KEY", "")
    monkeypatch.setattr("auth.is_production", lambda: False)
    assert api_key_configured() is False
    req = _FakeRequest({"X-API-Key": "anything"})
    assert verify_api_key(req) is True


def test_auth_fails_closed_in_production_without_key(monkeypatch):
    monkeypatch.setattr("auth.API_KEY", "")
    monkeypatch.setattr("auth.is_production", lambda: True)
    req = _FakeRequest()
    assert verify_api_key(req) is False


def test_rejects_missing_key(monkeypatch):
    monkeypatch.setattr("auth.API_KEY", "secret")
    monkeypatch.setattr("auth.is_production", lambda: False)
    req = _FakeRequest()
    assert verify_api_key(req) is False


def test_accepts_header_key(monkeypatch):
    monkeypatch.setattr("auth.API_KEY", "secret")
    monkeypatch.setattr("auth.is_production", lambda: False)
    req = _FakeRequest({"X-API-Key": "secret"})
    assert verify_api_key(req) is True


def test_accepts_bearer_token(monkeypatch):
    monkeypatch.setattr("auth.API_KEY", "secret")
    monkeypatch.setattr("auth.is_production", lambda: False)
    req = _FakeRequest({"Authorization": "Bearer secret"})
    assert verify_api_key(req) is True
