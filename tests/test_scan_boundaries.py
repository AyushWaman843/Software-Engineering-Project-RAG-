"""Scan authorization and quota must survive malformed and rejected requests."""

from flask import jsonify

import app as scanner
import job_store


def test_proxy_header_requires_secret_and_verified_user(monkeypatch):
    monkeypatch.setattr(scanner, "INTERNAL_PROXY_SECRET", "internal-secret")
    monkeypatch.setattr(scanner, "resolve_authenticated_user_id", lambda request: "")

    with scanner.app.test_request_context(
        "/api/scan", headers={"X-TrustStack-Proxy": "1", "Authorization": "Bearer forged.jwt.value"}
    ):
        assert scanner._truststack_proxy() is False
        assert scanner._require_signed_in()[1] == 401

    with scanner.app.test_request_context(
        "/api/scan",
        headers={"X-TrustStack-Proxy": "1", "X-Anix-Internal-Proxy": "internal-secret"},
    ):
        assert scanner._truststack_proxy() is True
        assert scanner._require_signed_in()[1] == 401


def test_request_id_is_returned_without_echoing_client_value():
    response = scanner.app.test_client().get("/health", headers={"X-Request-ID": "client-value"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "client-value"
    assert len(response.headers["X-Request-ID"]) == 16

def test_invalid_scan_does_not_reserve_quota(monkeypatch):
    monkeypatch.setattr(scanner, "verify_api_key", lambda request: True)
    monkeypatch.setattr(scanner, "resolve_authenticated_user_id", lambda request: "user-1")
    monkeypatch.setattr(scanner, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(scanner, "_scan_quota_gate", lambda: (_ for _ in ()).throw(AssertionError("reserved")))

    response = scanner.app.test_client().post("/api/scan", json={"url": ""})
    assert response.status_code == 400


def test_captcha_rejection_does_not_reserve_quota(monkeypatch):
    monkeypatch.setattr(scanner, "verify_api_key", lambda request: True)
    monkeypatch.setattr(scanner, "resolve_authenticated_user_id", lambda request: "user-1")
    monkeypatch.setattr(scanner, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(scanner, "validate_scan_url", lambda url: url)
    monkeypatch.setattr(scanner, "_captcha_slot_type", lambda: "free")
    monkeypatch.setattr(scanner, "_require_scan_captcha", lambda slot: (jsonify({"error": "captcha"}), 403))
    monkeypatch.setattr(scanner, "_scan_quota_gate", lambda: (_ for _ in ()).throw(AssertionError("reserved")))

    response = scanner.app.test_client().post("/api/scan", json={"url": "https://example.com"})
    assert response.status_code == 403


def test_capacity_rejection_refunds_reserved_slot(monkeypatch):
    monkeypatch.setattr(scanner, "verify_api_key", lambda request: True)
    monkeypatch.setattr(scanner, "resolve_authenticated_user_id", lambda request: "user-1")
    monkeypatch.setattr(scanner, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(scanner, "validate_scan_url", lambda url: url)
    monkeypatch.setattr(scanner, "_require_scan_captcha", lambda slot: None)
    monkeypatch.setattr(scanner, "_scan_quota_gate", lambda: (None, "prepaid"))
    monkeypatch.setattr(scanner, "start_scan", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("full")))
    refunded = []
    monkeypatch.setattr(scanner, "restore_scan_slot", lambda user, slot: refunded.append((user, slot)) or True)

    response = scanner.app.test_client().post("/api/scan", json={"url": "https://example.com"})
    assert response.status_code == 503
    assert refunded == [("user-1", "prepaid")]


def test_failed_pilot_job_refunds_its_slot(monkeypatch):
    refunded = []
    monkeypatch.setattr("supabase_entitlements.restore_scan_slot", lambda *args: refunded.append(args) or True)
    job = {"id": "job-1", "status": "error", "owner_user_id": "user-1",
           "scan_slot_type": "pilot_daily", "created_at": "2026-10-22T10:00:00"}

    job_store._maybe_refund_failed_job(job)
    assert refunded == [("user-1", "pilot_daily", "2026-10-22")]
    assert job["credit_refunded"] is True
