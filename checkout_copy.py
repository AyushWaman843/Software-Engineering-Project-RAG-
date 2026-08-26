"""Copy and metadata for Razorpay checkout (report unlock + paid scan)."""

from __future__ import annotations

from typing import Any

from config import PREMIUM_CURRENCY, PREMIUM_PRICE_PAISE, PRO_ORIGINAL_PRICE_PAISE, PRO_PRICE_PAISE

# Shown in our pre-payment summary modal (and returned by checkout APIs).
REPORT_UNLOCK_INCLUDES = [
    "All 10 DPDP compliance indicators with confidence scores",
    "Detailed AI analysis and actual policy excerpts",
    "Prioritized remediation plan for this site",
    "Professional PDF download for this assessment",
    "Permanent unlock — revisit this report anytime while signed in",
    "One-time payment for this report only — not a subscription",
]

# Legacy scope — Pro create is disabled; Pilot is purchased on TrustStack.
PRO_SUBSCRIPTION_INCLUDES = [
    "Pilot replaces Pro — subscribe on TrustStack",
    "1 full-report scan per day (does not stack)",
    "Extra same-day scans are ₹299 each",
    "TrustStack templates, certs, and tools included",
    "Cancel anytime — no long-term lock-in",
]

PRO_RAZORPAY_DESCRIPTION = (
    "TrustStack Pilot: subscribe on TrustStack (Pro is no longer available)"
)


def _pro_price_display() -> float:
    return PRO_PRICE_PAISE / 100


def _pro_original_price_display() -> float:
    return PRO_ORIGINAL_PRICE_PAISE / 100


PAID_SCAN_INCLUDES = [
    "Run one new site assessment (full report included)",
    "Use after your free preview or today's Pilot scan is used",
    "All 10 indicators, AI analysis, and policy excerpts",
    "Remediation plan and downloadable PDF included",
    "One-time ₹299 payment — not a subscription",
]

# Single line shown on Razorpay's checkout form (Standard Checkout).
REPORT_RAZORPAY_DESCRIPTION = (
    "One-Time Full Report: all indicators, AI analysis, remediation plan and PDF"
)
PAID_SCAN_RAZORPAY_DESCRIPTION = (
    "New site scan plus full report: indicators, AI analysis, PDF (one-time)"
)


def _price_display() -> float:
    return PREMIUM_PRICE_PAISE / 100


def checkout_summary(scope: str) -> dict[str, Any]:
    """UI + Razorpay metadata for a checkout scope."""
    price = _price_display()
    if scope == "pro_subscription":
        # Dead path — API returns 410; copy kept only for any stale clients.
        pro_price = _pro_price_display()
        return {
            "checkout_title": "Get Pilot on TrustStack",
            "checkout_subtitle": "Pro is gone — Pilot is 1 full scan/day",
            "checkout_includes": list(PRO_SUBSCRIPTION_INCLUDES),
            "description": PRO_RAZORPAY_DESCRIPTION,
            "razorpay_notes": {
                "product": "TrustStack Pilot",
                "includes": "1 full scan/day",
                "billing": "Monthly subscription via TrustStack",
            },
            "price_display": pro_price,
            "original_price_display": _pro_original_price_display(),
            "discount_percent": 0,
            "currency": PREMIUM_CURRENCY,
            "scope": scope,
        }
    if scope == "paid_scan":
        return {
            "checkout_title": "Pay to scan a new site",
            "checkout_subtitle": "Includes a full DPDP report when the scan finishes",
            "checkout_includes": list(PAID_SCAN_INCLUDES),
            "description": PAID_SCAN_RAZORPAY_DESCRIPTION,
            "razorpay_notes": {
                "product": "DPDP New Scan + Full Report",
                "includes": "Scan, full report, PDF",
                "billing": "One-time, not subscription",
            },
            "price_display": price,
            "currency": PREMIUM_CURRENCY,
            "scope": scope,
        }
    return {
        "checkout_title": "Unlock full DPDP report",
        "checkout_subtitle": "One-time payment for this assessment only",
        "checkout_includes": list(REPORT_UNLOCK_INCLUDES),
        "description": REPORT_RAZORPAY_DESCRIPTION,
        "razorpay_notes": {
            "product": "DPDP Full Report Unlock",
            "includes": "Indicators, AI, PDF",
            "billing": "One-time, not subscription",
        },
        "price_display": price,
        "currency": PREMIUM_CURRENCY,
        "scope": "report",
    }
