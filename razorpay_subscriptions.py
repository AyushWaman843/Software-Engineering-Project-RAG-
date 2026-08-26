"""Razorpay subscription management for Pro tier (₹999/month recurring)."""

from __future__ import annotations

import logging
from typing import Any, Dict

from config import PRO_PRICE_PAISE, PREMIUM_CURRENCY, PRO_SUBSCRIPTION_ENABLED, RAZORPAY_KEY_ID
from razorpay_payments import _client_instance, razorpay_configured
from razorpay.errors import SignatureVerificationError

logger = logging.getLogger(__name__)


def subscriptions_enabled() -> bool:
    return PRO_SUBSCRIPTION_ENABLED and razorpay_configured()


def create_pro_subscription_plan() -> Dict[str, Any]:
    """
    Create or return a Razorpay Pro plan (₹999/month).
    Call this once during setup or on-demand when creating a subscription.
    """
    if not subscriptions_enabled():
        raise RuntimeError("Pro subscriptions are not enabled.")
    
    client = _client_instance()
    
    # Check if plan already exists (you can store plan_id in env or DB)
    # For simplicity, we'll create a new plan or reuse an existing one
    # In production, store the plan_id and reuse it
    
    plan_data = {
        "period": "monthly",
        "interval": 1,
        "item": {
            "name": "DPDP Scanner Pro",
            "description": "5 full-report scans per month",
            "amount": PRO_PRICE_PAISE,
            "currency": PREMIUM_CURRENCY,
        },
    }
    
    try:
        plan = client.plan.create(plan_data)
        logger.info("Created Razorpay Pro plan: %s", plan["id"])
        return plan
    except Exception as exc:
        detail = getattr(exc, "args", (str(exc),))[0] or str(exc)
        logger.error("Failed to create Razorpay Pro plan: %s", detail or exc)
        raise RuntimeError(
            "Could not create Razorpay Pro plan. Create a monthly ₹999 plan in the "
            "Razorpay Dashboard and set RAZORPAY_PRO_PLAN_ID in .env."
        ) from exc


def create_pro_subscription(user_id: str, plan_id: str) -> Dict[str, Any]:
    """
    Create a Razorpay subscription for a user.
    Returns subscription data including subscription_id for checkout.
    """
    if not subscriptions_enabled():
        raise RuntimeError("Pro subscriptions are not enabled.")
    
    client = _client_instance()
    
    subscription_data = {
        "plan_id": plan_id,
        "total_count": 12,  # 12 billing cycles (1 year), can be adjusted
        "quantity": 1,
        "customer_notify": 1,
        "notes": {
            "user_id": user_id,
            "tier": "pro",
        },
    }
    
    try:
        subscription = client.subscription.create(subscription_data)
        logger.info("Created Razorpay subscription %s for user %s", subscription["id"], user_id)
        return subscription
    except Exception as exc:
        logger.error("Failed to create subscription for user %s: %s", user_id, exc)
        raise


def fetch_subscription(subscription_id: str) -> Dict[str, Any]:
    """Fetch subscription details from Razorpay."""
    if not razorpay_configured():
        raise RuntimeError("Razorpay is not configured.")
    
    client = _client_instance()
    return client.subscription.fetch(subscription_id)


def cancel_subscription(subscription_id: str) -> Dict[str, Any]:
    """Cancel a Razorpay subscription."""
    if not razorpay_configured():
        raise RuntimeError("Razorpay is not configured.")
    
    client = _client_instance()
    return client.subscription.cancel(subscription_id)


def verify_subscription_payment(
    *,
    payment_id: str,
    subscription_id: str,
    signature: str,
) -> None:
    """Verify Razorpay subscription payment signature."""
    if not payment_id or not subscription_id or not signature:
        raise ValueError("Missing Razorpay subscription payment fields.")

    client = _client_instance()
    try:
        client.utility.verify_subscription_payment_signature(
            {
                "razorpay_payment_id": payment_id,
                "razorpay_subscription_id": subscription_id,
                "razorpay_signature": signature,
            }
        )
    except SignatureVerificationError as exc:
        logger.warning(
            "Razorpay subscription signature verification failed for %s",
            subscription_id,
        )
        raise ValueError("Invalid payment signature.") from exc


def pro_checkout_payload(subscription: Dict[str, Any]) -> Dict[str, Any]:
    """Build client checkout payload for a created Razorpay subscription."""
    from checkout_copy import checkout_summary

    summary = checkout_summary("pro_subscription")
    return {
        "ok": True,
        "subscription_id": subscription["id"],
        "status": subscription.get("status", "created"),
        "plan_id": subscription.get("plan_id", ""),
        "key_id": RAZORPAY_KEY_ID,
        "checkout_mode": "subscription",
        **summary,
    }
