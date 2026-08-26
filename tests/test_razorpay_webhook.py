"""Tests for Razorpay webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac

import pytest


def test_verify_webhook_signature_valid(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

    import importlib
    import razorpay_webhooks

    importlib.reload(razorpay_webhooks)

    body = b'{"event":"payment.captured"}'
    sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    assert razorpay_webhooks.verify_webhook_signature(body, sig) is True


def test_verify_webhook_signature_invalid(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

    import importlib
    import razorpay_webhooks

    importlib.reload(razorpay_webhooks)

    assert razorpay_webhooks.verify_webhook_signature(b"{}", "bad") is False
