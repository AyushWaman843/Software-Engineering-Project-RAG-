"""Razorpay checkout and payment verification for one-time report unlocks and paid scans."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Literal

import razorpay
from razorpay.errors import SignatureVerificationError

from config import (
    PREMIUM_CURRENCY,
    PREMIUM_PRICE_PAISE,
    PRO_PRICE_PAISE,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
)
from checkout_copy import checkout_summary

logger = logging.getLogger(__name__)

PaymentScope = Literal["report", "paid_scan", "pro_monthly_pass"]

_client: razorpay.Client | None = None


def razorpay_configured() -> bool:
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


def _client_instance() -> razorpay.Client:
    global _client
    if not razorpay_configured():
        raise RuntimeError("Razorpay keys are not configured.")
    if _client is None:
        _client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    return _client


def create_checkout_order(report_id: str, *, user_id: str = "") -> Dict[str, Any]:
    """Create a Razorpay order to unlock one full report (₹299 one-time)."""
    return _create_order(
        scope="report",
        receipt_prefix=f"rpt_{report_id[:20]}",
        description="DPDP Full Report — One-Time Report Unlock",
        notes={"report_id": report_id, "user_id": user_id} if user_id else {"report_id": report_id},
    )


def create_paid_scan_order(*, user_id: str) -> Dict[str, Any]:
    """Create a Razorpay order to run one new scan when free quota is exhausted."""
    return _create_order(
        scope="paid_scan",
        receipt_prefix=f"scan_{user_id[:12]}",
        description="DPDP Assessment — New Site Scan + Full Report",
        notes={"user_id": user_id},
    )


def create_pro_monthly_pass_order(*, user_id: str) -> Dict[str, Any]:
    """
    Pro tier via one-time order (₹999) — works without Razorpay Subscriptions/Plans.
    Grants 5 full scans for 30 days; renew by paying again next month.
    """
    return _create_order(
        scope="pro_monthly_pass",
        receipt_prefix=f"pro_{user_id[:12]}",
        description="DPDP Scanner Pro — 5 full scans for 30 days",
        notes={"user_id": user_id, "tier": "pro"},
        amount_paise=PRO_PRICE_PAISE,
        summary_scope="pro_subscription",
    )


def _create_order(
    *,
    scope: PaymentScope,
    receipt_prefix: str,
    description: str,
    notes: Dict[str, str],
    amount_paise: int = PREMIUM_PRICE_PAISE,
    summary_scope: str | None = None,
) -> Dict[str, Any]:
    client = _client_instance()
    receipt = f"{receipt_prefix}_{int(time.time())}"[:40]
    order_notes: Dict[str, str] = {"scope": scope, **notes}
    order = client.order.create(
        {
            "amount": amount_paise,
            "currency": PREMIUM_CURRENCY,
            "receipt": receipt,
            "notes": order_notes,
        }
    )
    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "key_id": RAZORPAY_KEY_ID,
        "name": "DPDP Scanner",
        "description": description,
        "scope": scope,
        "checkout_mode": "order",
        **checkout_summary(summary_scope or scope),
    }


def fetch_order_notes(order_id: str) -> dict:
    """Return Razorpay order notes for binding checks (report_id / user_id / scope)."""
    if not order_id:
        return {}
    client = _client_instance()
    order = client.order.fetch(order_id)
    notes = order.get("notes") or {}
    return notes if isinstance(notes, dict) else {}


def verify_payment(
    *,
    payment_id: str,
    order_id: str,
    signature: str,
    expected_scope: PaymentScope | None = None,
    expected_report_id: str | None = None,
    expected_user_id: str | None = None,
) -> PaymentScope:
    """Verify Razorpay signature, capture status, scope, and optional order-note bindings."""
    if not payment_id or not order_id or not signature:
        raise ValueError("Missing Razorpay payment fields.")

    client = _client_instance()
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
        )
    except SignatureVerificationError as exc:
        logger.warning("Razorpay signature verification failed for order %s", order_id)
        raise ValueError("Invalid payment signature.") from exc

    payment = client.payment.fetch(payment_id)
    if payment.get("order_id") != order_id:
        raise ValueError("Payment does not match order.")
    if payment.get("status") != "captured":
        raise ValueError("Payment was not captured.")

    notes = fetch_order_notes(order_id)
    scope = str(notes.get("scope") or "report")
    if scope not in ("report", "paid_scan", "pro_monthly_pass"):
        scope = "report"
    if expected_scope and scope != expected_scope:
        raise ValueError(f"Payment scope mismatch (expected {expected_scope}, got {scope}).")

    if expected_report_id is not None:
        note_report = str(notes.get("report_id") or "").strip()
        if not note_report or note_report != expected_report_id:
            raise ValueError("Payment was created for a different report.")

    if expected_user_id is not None:
        note_user = str(notes.get("user_id") or "").strip()
        if not note_user or note_user != expected_user_id:
            raise ValueError("Payment was created for a different account.")

    return scope  # type: ignore[return-value]
