"""Report ownership / IDOR hardening."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from auth_user import extract_bearer_token, resolve_authenticated_user_id, verify_supabase_access_token
from compliance_checker import ComplianceReport
from entitlements import report_view_denied
from scan_runner import load_report_by_id, save_report
from user_reconcile import user_has_report_access


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


def test_extract_bearer_token():
    req = _FakeRequest({"Authorization": "Bearer abc.def"})
    assert extract_bearer_token(req) == "abc.def"
    assert extract_bearer_token(_FakeRequest()) == ""


def test_spoofed_x_user_id_is_ignored(monkeypatch):
    monkeypatch.setattr(
        "auth_user.verify_supabase_access_token",
        lambda token: "real-user" if token == "good-jwt" else "",
    )
    spoofed = _FakeRequest({"X-User-Id": "attacker", "Authorization": "Bearer good-jwt"})
    assert resolve_authenticated_user_id(spoofed) == "real-user"

    only_header = _FakeRequest({"X-User-Id": "attacker"})
    assert resolve_authenticated_user_id(only_header) == ""


def test_verify_rejects_api_key_as_user_jwt(monkeypatch):
    monkeypatch.setattr("auth_user.API_KEY", "server-secret")
    monkeypatch.setattr("auth_user.SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr("auth_user.SUPABASE_ANON_KEY", "anon")
    assert verify_supabase_access_token("server-secret") == ""


def test_save_report_uses_opaque_id(tmp_path, monkeypatch):
    monkeypatch.setattr("scan_runner.RESULTS_DIR", tmp_path)
    report = ComplianceReport()
    report.url = "https://acme.example/privacy"
    path = Path(save_report(report))
    report_id = path.stem
    # Opaque token — not the old domain_YYYYMMDD_HHMMSS pattern.
    assert not report_id.startswith("acme_example_")
    assert len(report_id) >= 20
    loaded = load_report_by_id(report_id)
    assert loaded is not None
    assert str(loaded.get("report_slug", "")).startswith("acme_example_")


def test_report_view_denied_codes(monkeypatch):
    responses = []

    def fake_jsonify(payload):
        responses.append(payload)
        return SimpleNamespace(get_json=lambda: payload)

    monkeypatch.setattr("flask.jsonify", fake_jsonify)

    monkeypatch.setattr("entitlements._user_id_from_request", lambda req: "")
    monkeypatch.setattr("entitlements.resolve_report_owner", lambda rid, report: "owner-1")
    denied = report_view_denied("r1", {"owner_user_id": "owner-1"}, _FakeRequest())
    assert denied is not None and denied[1] == 403
    assert denied[0].get_json()["code"] == "SIGN_IN_REQUIRED"

    monkeypatch.setattr("entitlements._user_id_from_request", lambda req: "user-a")
    monkeypatch.setattr("entitlements.resolve_report_owner", lambda rid, report: "")
    denied = report_view_denied("orphan", {}, _FakeRequest())
    assert denied is not None and denied[1] == 403
    assert denied[0].get_json()["code"] == "REPORT_UNAVAILABLE"

    monkeypatch.setattr("entitlements.resolve_report_owner", lambda rid, report: "user-a")
    monkeypatch.setattr("entitlements._user_id_from_request", lambda req: "user-b")
    denied = report_view_denied("r1", {"owner_user_id": "user-a"}, _FakeRequest())
    assert denied is not None and denied[1] == 403
    assert denied[0].get_json()["code"] == "ACCESS_DENIED"

    monkeypatch.setattr("entitlements._user_id_from_request", lambda req: "user-a")
    assert report_view_denied("r1", {"owner_user_id": "user-a"}, _FakeRequest()) is None


def test_unbound_premium_unlock_is_not_global(monkeypatch):
    monkeypatch.setattr("user_reconcile.is_report_unlocked", lambda uid, rid: False)
    monkeypatch.setattr("supabase_subscriptions.user_has_active_pro", lambda uid: False)
    report = {"premium_unlocked": True, "owner_user_id": "owner-a"}
    assert user_has_report_access("attacker", "r1", report) is False
    assert (
        user_has_report_access(
            "owner-a",
            "r1",
            {**report, "premium_unlocked_user_id": "owner-a"},
        )
        is True
    )
