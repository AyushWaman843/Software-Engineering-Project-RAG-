"""Quota writes use the database RPC and fail closed on database errors."""

from types import SimpleNamespace

import supabase_entitlements as entitlements


class FakeClient:
    def __init__(self):
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=True))


def test_legacy_pro_reservation_uses_atomic_limit(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(entitlements, "_get_client", lambda: client)

    assert entitlements.reserve_scan_slot_atomic("user-id", "pro") is True
    assert client.calls == [
        ("reserve_scan_slot", {"p_user_id": "user-id", "p_slot": "pro", "p_limit": 5})
    ]


def test_missing_quota_rpc_fails_closed(monkeypatch):
    class BrokenClient:
        def rpc(self, *_args):
            raise RuntimeError("missing RPC")

    monkeypatch.setattr(entitlements, "_get_client", lambda: BrokenClient())
    assert entitlements.reserve_scan_slot_atomic("user-id", "free") is False
