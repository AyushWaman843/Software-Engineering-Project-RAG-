"""Tests for Cloudflare Turnstile verification helper."""

from captcha import verify_turnstile_token


def test_skips_when_secret_unset(monkeypatch):
    monkeypatch.setattr("captcha.TURNSTILE_SECRET_KEY", "")
    monkeypatch.setattr("captcha.TURNSTILE_REQUIRED", False)
    ok, msg = verify_turnstile_token("")
    assert ok is True
    assert msg == ""


def test_requires_token_when_configured(monkeypatch):
    monkeypatch.setattr("captcha.TURNSTILE_SECRET_KEY", "test-secret")
    ok, msg = verify_turnstile_token("")
    assert ok is False
    assert "CAPTCHA" in msg


def test_accepts_valid_token(monkeypatch):
    monkeypatch.setattr("captcha.TURNSTILE_SECRET_KEY", "test-secret")

    class _Resp:
        def json(self):
            return {"success": True}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr("captcha.httpx.Client", lambda timeout=8.0: _Client())
    ok, msg = verify_turnstile_token("tok")
    assert ok is True
    assert msg == ""
