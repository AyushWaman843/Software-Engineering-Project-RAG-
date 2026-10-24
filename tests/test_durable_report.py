"""A production scan must not claim success when its durable copy is missing."""

from types import SimpleNamespace

import pytest

import entitlements
import scan_runner


def test_production_report_requires_remote_mirror(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_runner, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr("config.is_production", lambda: True)
    monkeypatch.setattr("supabase_store.upsert_scan_report", lambda *args: False)
    report = SimpleNamespace(url="https://example.com", to_dict=lambda: {"score": 80})

    with pytest.raises(RuntimeError, match="durable storage"):
        scan_runner.save_report(report)

    assert list(tmp_path.iterdir()) == []


def test_remote_only_report_can_be_unlocked(monkeypatch):
    saved = []
    monkeypatch.setattr(
        entitlements, "load_report_by_id",
        lambda report_id: {"_report_id": report_id, "owner_user_id": "user-1"},
    )
    monkeypatch.setattr("supabase_store.upsert_scan_report", lambda report_id, data: saved.append((report_id, data)) or True)

    entitlements.grant_premium_access("report-1", user_id="user-1", payment_id="payment-1")

    assert saved[0][0] == "report-1"
    assert saved[0][1]["premium_unlocked_user_id"] == "user-1"
