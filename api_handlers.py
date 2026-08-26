"""Shared API logic for the DPDP scanner (used by Flask API server)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from config import (
    ANONYMOUS_FREE_SCANS,
    FREE_SCANS_PER_USER,
    PREMIUM_CURRENCY,
    PREMIUM_ENABLED,
    PREMIUM_FREE_ACCESS,
    PREMIUM_PREVIEW_MISSING_INDICATORS,
    PREMIUM_PRICE_PAISE,
    RULES_VERSION,
    SCANNER_VERSION,
)
from report_generator import (
    MANDATORY_INDICATORS,
    build_indicator_rows,
    generate_pdf_report,
    resolve_policy_texts_for_report,
)
from scan_runner import ai_engine_label, load_report_by_id

logger = logging.getLogger(__name__)

MIN_STORED_POLICY_CHARS = 50

# Bulky fields kept on disk for PDF generation but omitted from JSON API responses.
_API_STRIP_ANALYSIS_KEYS = (
    "stored_policy_text",
    "stored_terms_text",
    "stored_cookie_text",
    "uploaded_files",
    "sample_chunks",
    "all_ai_scores",
    "keyword_matches",
    "gemini_analysis",
    "llm_analysis",
)

_REPORT_UI_KEYS = (
    "url",
    "timestamp",
    "scraping_method",
    "privacy_policy_found",
    "cookie_banner_found",
    "grievance_officer_contact",
    "errors",
    "score",
    "verdict",
    "scanner_version",
    "rules_version",
    "confidence_label",
    "average_confidence",
)


def slim_analysis_details(details: Dict[str, Any]) -> Dict[str, Any]:
    """Drop large scan artifacts not needed by the web UI."""
    slim = dict(details or {})
    for key in _API_STRIP_ANALYSIS_KEYS:
        slim.pop(key, None)
    return slim


def slim_report_for_ui(report: dict) -> Dict[str, Any]:
    """Return only report fields rendered by the Next.js report page."""
    slim = {key: report[key] for key in _REPORT_UI_KEYS if key in report}
    slim["analysis_details"] = slim_analysis_details(report.get("analysis_details") or {})
    return slim


def history_summary_item(report: dict) -> Dict[str, Any]:
    """Minimal fields for the recent-assessments sidebar and trend charts."""
    return {
        "_report_id": report.get("_report_id", ""),
        "url": report.get("url", ""),
        "score": int(report.get("score", 0)),
        "verdict": report.get("verdict", "Unknown"),
        "timestamp": report.get("timestamp", ""),
    }


def find_previous_scan_summary(
    reports: list[dict],
    *,
    current_id: str,
    url: str,
    timestamp: str,
) -> Optional[Dict[str, Any]]:
    """Most recent scan of the same site before the current report."""

    def normalize(u: str) -> str:
        return (u or "").strip().lower().rstrip("/")

    key = normalize(url)
    earlier = [
        history_summary_item(item)
        for item in reports
        if item.get("_report_id") != current_id
        and normalize(item.get("url", "")) == key
        and (item.get("timestamp") or "") < (timestamp or "")
    ]
    if not earlier:
        return None
    earlier.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    prev = earlier[0]
    return {"score": prev["score"], "timestamp": prev["timestamp"]}


def verdict_class(verdict: str) -> str:
    mapping = {
        "Likely Compliant": "verdict-compliant",
        "Partially Compliant": "verdict-partial",
        "Likely Non-Compliant": "verdict-noncompliant",
    }
    return mapping.get(verdict, "verdict-unknown")


def score_class(score: int) -> str:
    if score > 60:
        return "score-high"
    if score >= 30:
        return "score-mid"
    return "score-low"


def policy_extraction_warning(report: dict) -> bool:
    if report.get("scraping_method") == "pdf_upload":
        return False
    details = report.get("analysis_details") or {}
    if details.get("policy_text_extracted"):
        return False
    return int(details.get("policy_text_length") or 0) < MIN_STORED_POLICY_CHARS


def prompt_injection_phrases(report: dict) -> list:
    """Suspicious instruction-like phrases detected in scraped text (if any)."""
    details = report.get("analysis_details") or {}
    hits = details.get("prompt_injection_detected") or []
    return [str(h) for h in hits if str(h).strip()]


def build_results_context(
    report: dict,
    policy_text: str = "",
    terms_text: str = "",
    cookie_text: str = "",
) -> Dict[str, Any]:
    score = int(report.get("score", 0))
    rows = build_indicator_rows(report)
    llm = (report.get("analysis_details") or {}).get("llm_analysis") or {}
    indicators = llm.get("indicators") or {}

    findings = []
    for row in rows:
        key = row["key"]
        entry = indicators.get(key, {})
        findings.append({
            **row,
            "analysis": (entry.get("analysis") or "").strip(),
            "recommendation": (entry.get("recommendation") or "").strip(),
            "excerpt": (entry.get("excerpt") or "").strip(),
        })

    return {
        "report": slim_report_for_ui(report),
        "score": score,
        "verdict": report.get("verdict", "Unknown"),
        "verdict_class": verdict_class(report.get("verdict", "")),
        "score_class": score_class(score),
        "rows": rows,
        "findings": findings,
        "score_breakdown": report.get("score_breakdown") or {},
        "rule_citations": report.get("rule_citations") or {},
        "analysis_details": slim_analysis_details(report.get("analysis_details") or {}),
        "ai_engine": ai_engine_label(),
        "policy_extraction_warning": policy_extraction_warning(report),
        "prompt_injection_detected": prompt_injection_phrases(report),
        "access_tier": "full",
        "confidence_label": report.get("confidence_label"),
        "average_confidence": report.get("average_confidence"),
    }


def _top_missing_indicators(rows: list, limit: int = PREMIUM_PREVIEW_MISSING_INDICATORS) -> list:
    """Most important missing/partial indicators for the free preview."""
    missing = [r for r in rows if r.get("status") in ("Missing", "Partial")]

    def sort_key(row: dict) -> tuple:
        mandatory_rank = 0 if row.get("key") in MANDATORY_INDICATORS else 1
        return (mandatory_rank, -int(row.get("max_points") or 0))

    missing.sort(key=sort_key)
    return missing[:limit]


def _discovered_policy_pages(report: dict) -> dict:
    details = report.get("analysis_details") or {}
    return dict(details.get("policy_urls") or {})


def build_preview_context(report: dict) -> Dict[str, Any]:
    """
    Preview payload: score, verdict, metadata, top missing indicators, and
    discovered policy pages. Protected fields are omitted server-side.
    """
    full = build_results_context(report)
    all_rows = full["rows"]
    missing_preview = _top_missing_indicators(all_rows)
    policy_pages = _discovered_policy_pages(report)

    return {
        "report": full["report"],
        "score": full["score"],
        "verdict": full["verdict"],
        "verdict_class": full["verdict_class"],
        "score_class": full["score_class"],
        "rows": [],
        "missing_indicators": missing_preview,
        "discovered_policy_pages": policy_pages,
        "findings": [],
        "score_breakdown": {},
        "rule_citations": {},
        "analysis_details": {
            "policy_urls": policy_pages,
            "scan_steps": [],
            "policy_text_length": 0,
            "chunks_analyzed": 0,
        },
        "ai_engine": full["ai_engine"],
        "policy_extraction_warning": full["policy_extraction_warning"],
        "prompt_injection_detected": full.get("prompt_injection_detected", []),
        "confidence_label": full.get("confidence_label"),
        "average_confidence": full.get("average_confidence"),
        "access_tier": "preview",
        "premium": {
            "indicators_total": len(all_rows),
            "indicators_locked": len(all_rows),
            "missing_preview_count": len(missing_preview),
            "findings_total": len(full["findings"]),
            "pdf_locked": True,
            "price_display": PREMIUM_PRICE_PAISE / 100,
            "currency": PREMIUM_CURRENCY,
        },
    }


def _resolve_policy_texts_for_pdf(report: dict) -> tuple[str, str, str]:
    """
    Load policy texts for PDF generation.

    Prefer text stored at scan time so PDF download does not re-scrape the site
    (which can take minutes and cause HTTP timeouts).
    """
    policy_text, terms_text, cookie_text = resolve_policy_texts_for_report(report)
    if len((policy_text or "").strip()) >= MIN_STORED_POLICY_CHARS:
        return policy_text, terms_text, cookie_text

    analysis = report.get("analysis_details") or {}
    uploaded_files = analysis.get("uploaded_files") or {}

    if uploaded_files:
        from document_ingest import extract_text_from_pdf

        if uploaded_files.get("privacy") and len((policy_text or "").strip()) < MIN_STORED_POLICY_CHARS:
            policy_text = extract_text_from_pdf(uploaded_files["privacy"]) or policy_text
        if uploaded_files.get("terms") and not (terms_text or "").strip():
            terms_text = extract_text_from_pdf(uploaded_files["terms"]) or ""
        if uploaded_files.get("cookie") and not (cookie_text or "").strip():
            cookie_text = extract_text_from_pdf(uploaded_files["cookie"]) or ""
        return resolve_policy_texts_for_report(report, policy_text, terms_text, cookie_text)

    policy_urls = analysis.get("policy_urls") or {}
    from scraper import fetch_policy_text

    if len((policy_text or "").strip()) < MIN_STORED_POLICY_CHARS:
        privacy_url = policy_urls.get("privacy")
        if privacy_url and not str(privacy_url).startswith("Uploaded:"):
            logger.info("PDF: re-fetching privacy policy (no stored text): %s", privacy_url)
            policy_text = fetch_policy_text(privacy_url) or policy_text

    if not (terms_text or "").strip():
        terms_url = policy_urls.get("terms")
        if terms_url and not str(terms_url).startswith("Uploaded:"):
            terms_text = fetch_policy_text(terms_url) or ""

    if not (cookie_text or "").strip():
        cookie_url = policy_urls.get("cookie")
        if cookie_url and not str(cookie_url).startswith("Uploaded:"):
            cookie_text = fetch_policy_text(cookie_url) or ""

    return resolve_policy_texts_for_report(report, policy_text, terms_text, cookie_text)


def generate_report_pdf(report_id: str) -> tuple[bytes, str]:
    """Build PDF bytes and download filename for a saved report."""
    report = load_report_by_id(report_id)
    if not report:
        raise FileNotFoundError("Report not found.")

    policy_text, terms_text, cookie_text = _resolve_policy_texts_for_pdf(report)

    pdf_bytes = generate_pdf_report(
        scan_result=report,
        policy_text=policy_text,
        terms_text=terms_text,
        cookie_text=cookie_text,
    )

    domain = urlparse(report.get("url", "")).netloc.replace(".", "_") or "site"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"DPDP_Report_{domain}_{ts}.pdf"
    return pdf_bytes, filename


def meta_payload() -> Dict[str, Any]:
    return {
        "ai_engine": ai_engine_label(),
        "scanner_version": SCANNER_VERSION,
        "rules_version": RULES_VERSION,
        "premium_enabled": PREMIUM_ENABLED,
        "premium_free_access": PREMIUM_FREE_ACCESS,
        "premium_price_paise": PREMIUM_PRICE_PAISE,
        "premium_price_display": PREMIUM_PRICE_PAISE / 100,
        "premium_currency": PREMIUM_CURRENCY,
        "free_scans_per_user": FREE_SCANS_PER_USER,
        "anonymous_free_scans": ANONYMOUS_FREE_SCANS,
    }
