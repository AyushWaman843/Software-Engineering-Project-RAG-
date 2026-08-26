"""Payment binding and ownership-hijack defenses."""

from __future__ import annotations

import pytest

from entitlements import resolve_report_owner
from razorpay_payments import verify_payment


def _patch_razorpay(monkeypatch, notes: dict):
    class Nested:
        class utility:
            @staticmethod
            def verify_payment_signature(_payload):
                return True

        class payment:
            @staticmethod
            def fetch(_pid):
                return {"order_id": "order_1", "status": "captured"}

        class order:
            @staticmethod
            def fetch(_oid):
                return {"notes": notes}

    monkeypatch.setattr("razorpay_payments._client_instance", lambda: Nested())


def test_verify_payment_rejects_report_mismatch(monkeypatch):
    _patch_razorpay(
        monkeypatch,
        {"scope": "report", "report_id": "R1", "user_id": "U1"},
    )
    with pytest.raises(ValueError, match="different report"):
        verify_payment(
            payment_id="pay_1",
            order_id="order_1",
            signature="sig",
            expected_scope="report",
            expected_report_id="R2",
            expected_user_id="U1",
        )


def test_verify_payment_rejects_user_mismatch(monkeypatch):
    _patch_razorpay(
        monkeypatch,
        {"scope": "report", "report_id": "R1", "user_id": "U1"},
    )
    with pytest.raises(ValueError, match="different account"):
        verify_payment(
            payment_id="pay_1",
            order_id="order_1",
            signature="sig",
            expected_scope="report",
            expected_report_id="R1",
            expected_user_id="U2",
        )


def test_verify_payment_accepts_matching_bindings(monkeypatch):
    _patch_razorpay(
        monkeypatch,
        {"scope": "report", "report_id": "R1", "user_id": "U1"},
    )
    scope = verify_payment(
        payment_id="pay_1",
        order_id="order_1",
        signature="sig",
        expected_scope="report",
        expected_report_id="R1",
        expected_user_id="U1",
    )
    assert scope == "report"


def test_file_owner_wins_over_db_hijack(monkeypatch):
    monkeypatch.setattr(
        "supabase_entitlements.get_report_owner_user_id",
        lambda rid: "attacker",
    )
    owner = resolve_report_owner("R1", {"owner_user_id": "victim"})
    assert owner == "victim"


def test_db_owner_used_when_file_has_none(monkeypatch):
    monkeypatch.setattr(
        "supabase_entitlements.get_report_owner_user_id",
        lambda rid: "owner-from-db",
    )
    owner = resolve_report_owner("R1", {})
    assert owner == "owner-from-db"
