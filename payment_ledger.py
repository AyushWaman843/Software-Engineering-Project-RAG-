"""Idempotent ledger for processed Razorpay webhook payment IDs (single-node / DATA_DIR)."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from config import DATA_DIR

logger = logging.getLogger(__name__)

_LEDGER_PATH = DATA_DIR / "processed_webhook_payments.json"
_lock = threading.Lock()


def _read_ids() -> set[str]:
    if not _LEDGER_PATH.is_file():
        return set()
    try:
        data = json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x) for x in data if x}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read webhook payment ledger: %s", exc)
    return set()


def payment_already_processed(payment_id: str) -> bool:
    if not payment_id:
        return False
    with _lock:
        return payment_id in _read_ids()


def try_claim_payment(payment_id: str) -> bool:
    """
    Atomically claim a payment_id for processing.
    Returns True if this caller won the claim; False if already processed.
    Call before granting entitlements to prevent TOCTOU double-grants.
    """
    if not payment_id:
        return False
    with _lock:
        ids = _read_ids()
        if payment_id in ids:
            return False
        ids.add(payment_id)
        try:
            _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            _LEDGER_PATH.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")
        except OSError as exc:
            logger.error("Could not write webhook payment ledger: %s", exc)
            return False
        return True


def release_payment_claim(payment_id: str) -> None:
    """Undo a claim when entitlement grant fails after try_claim_payment."""
    if not payment_id:
        return
    with _lock:
        ids = _read_ids()
        if payment_id not in ids:
            return
        ids.discard(payment_id)
        try:
            _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            _LEDGER_PATH.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")
        except OSError as exc:
            logger.error("Could not update webhook payment ledger: %s", exc)


def mark_payment_processed(payment_id: str) -> None:
    if not payment_id:
        return
    with _lock:
        ids = _read_ids()
        if payment_id in ids:
            return
        ids.add(payment_id)
        try:
            _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            _LEDGER_PATH.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")
        except OSError as exc:
            logger.error("Could not write webhook payment ledger: %s", exc)
