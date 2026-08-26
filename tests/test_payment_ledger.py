"""Payment claim ledger + confirm binding helpers."""

from payment_ledger import (
    mark_payment_processed,
    payment_already_processed,
    release_payment_claim,
    try_claim_payment,
)


def test_try_claim_payment_is_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr("payment_ledger._LEDGER_PATH", tmp_path / "ledger.json")
    assert try_claim_payment("pay_abc") is True
    assert payment_already_processed("pay_abc") is True
    assert try_claim_payment("pay_abc") is False


def test_release_payment_claim_allows_retry(tmp_path, monkeypatch):
    monkeypatch.setattr("payment_ledger._LEDGER_PATH", tmp_path / "ledger.json")
    assert try_claim_payment("pay_xyz") is True
    release_payment_claim("pay_xyz")
    assert payment_already_processed("pay_xyz") is False
    assert try_claim_payment("pay_xyz") is True


def test_mark_payment_processed_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("payment_ledger._LEDGER_PATH", tmp_path / "ledger.json")
    mark_payment_processed("pay_1")
    mark_payment_processed("pay_1")
    assert payment_already_processed("pay_1") is True
