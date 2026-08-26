"""
PDF report generator for DPDP compliance scans.
Renders HTML → PDF via WeasyPrint (preferred) or xhtml2pdf (Windows fallback).
"""

from __future__ import annotations

import html
import logging
import base64
import re
from datetime import datetime
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from compliance_checker import (
    AI_LABEL_MAPPING,
    KEYWORD_GATES,
    RULE_CITATIONS,
    SCORING_WEIGHTS,
)

logger = logging.getLogger(__name__)

NO_POLICY_TEXT_MSG = (
    "No policy text was extracted from this website. This may be due to scraping "
    "restrictions or missing policy links. Try using the Advanced input to paste "
    "direct privacy policy URLs."
)

# xhtml2pdf on Windows struggles with full Turnitin span markup on very long policies
PDF_EVIDENCE_CHAR_LIMIT = 10_000

# Lazy-loaded PDF backends (WeasyPrint needs GTK on Windows; xhtml2pdf is pure Python)
_weasyprint_available: Optional[bool] = None

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_LETTERHEAD_REL = "pdf_assets/letterhead.png"
_CONSULT_EMAIL = "contact@dpdpscanner.in"


def _templates_dir() -> Path:
    return _TEMPLATES_DIR


def _letterhead_src() -> str:
    """Return a data URI or relative path for the letterhead image."""
    path = _TEMPLATES_DIR / _LETTERHEAD_REL
    if not path.is_file():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _build_letterhead_html(kind: str = "cover") -> str:
    """Render letterhead image: cover (in flow), running (WeasyPrint), or frame (xhtml2pdf)."""
    src = _letterhead_src()
    if not src:
        return ""
    cls = {
        "cover": "letterhead",
        "running": "letterhead-running",
        "frame": "letterhead-frame-img",
    }.get(kind, "letterhead")
    width_attr = ' width="480"' if kind == "frame" else ""
    return f'<img class="{cls}" src="{src}" alt="DPDP Scanner"{width_attr}/>'


def _format_scan_date(ts: str) -> str:
    """Human-readable scan timestamp for the cover page."""
    if not ts:
        return datetime.now().strftime("%d %B %Y, %H:%M")
    try:
        normalized = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%d %B %Y, %H:%M")
    except ValueError:
        return ts[:19].replace("T", ", ")


def _status_css_class(status: str) -> str:
    normalized = str(status).strip().lower()
    if normalized == "found":
        return "found"
    if normalized == "partial":
        return "partial"
    return "missing"


def resolve_policy_texts_for_report(
    scan_result: Dict[str, Any],
    policy_text: str = "",
    terms_text: str = "",
    cookie_text: str = "",
) -> Tuple[str, str, str]:
    """
    Prefer caller-supplied text, then text stored at scan time in analysis_details.
    Used so PDF regeneration works when live re-scraping fails (e.g. DigiLocker).
    """
    details = scan_result.get("analysis_details") or {}
    if not (policy_text or "").strip():
        policy_text = details.get("stored_policy_text") or ""
    if not (terms_text or "").strip():
        terms_text = details.get("stored_terms_text") or ""
    if not (cookie_text or "").strip():
        cookie_text = details.get("stored_cookie_text") or ""
    return policy_text or "", terms_text or "", cookie_text or ""


def _policy_html_is_empty(policy_html: str) -> bool:
    """True when rendered policy HTML has no visible text content."""
    text_only = re.sub(r"<[^>]+>", "", policy_html or "")
    return not text_only.strip()


def _build_turnitin_evidence_section(
    scan_result: Dict[str, Any],
    policy_text: str,
) -> str:
    """
    Turnitin-style evidence block: legend + highlighted policy, or a clear missing-text notice.
    Large policies use plain text in the PDF to avoid multi-minute xhtml2pdf render times.
    """
    if not (policy_text or "").strip():
        return (
            f'<div class="policy-missing-notice">'
            f'<strong>No policy text available</strong>'
            f'{html.escape(NO_POLICY_TEXT_MSG)}</div>'
        )

    total_len = len(policy_text)
    if total_len > PDF_EVIDENCE_CHAR_LIMIT:
        excerpt = policy_text[:PDF_EVIDENCE_CHAR_LIMIT]
        policy_html = _wrap_doc_text(html.escape(excerpt))
        truncation_note = (
            f'<p class="policy-truncate-note"><em>'
            f"Policy excerpt shown ({PDF_EVIDENCE_CHAR_LIMIT:,} of {total_len:,} characters). "
            f"Colour highlights are omitted for large documents; the full text was analyzed "
            f"during the scan. See Detailed Findings below for indicator excerpts."
            f"</em></p>"
        )
        return f"""
    <h3>Turnitin-Style Compliance Evidence</h3>
    <p class="section-lead">Privacy policy text analyzed for this assessment.</p>
    {truncation_note}
    {policy_html}"""

    indicators = _get_indicators_for_highlight(scan_result, policy_text)
    policy_html, highlighted_keys = highlight_text(policy_text, indicators)

    if _policy_html_is_empty(policy_html):
        policy_html = _wrap_doc_text(html.escape(policy_text))
        highlighted_keys = set()

    legend = _build_legend(highlighted_keys) if highlighted_keys else ""
    return f"""
    <h3>Turnitin-Style Compliance Evidence</h3>
    <p class="section-lead">Full privacy policy text with colour-coded highlights showing where each DPDP indicator appears.</p>
    {legend}
    {policy_html}"""


def _build_html_document(
    scan_result: Dict[str, Any],
    policy_text: str,
    terms_text: str,
    cookie_text: str,
    backend: str = "weasyprint",
    fast_pdf: bool = False,
) -> str:
    """Assemble full HTML document for PDF rendering."""
    score = int(scan_result.get("score", 0))
    verdict = scan_result.get("verdict", "Unknown")
    url = scan_result.get("url", "")
    ts = scan_result.get("timestamp", datetime.now().isoformat())
    scanner_version = scan_result.get("scanner_version", "unknown")
    rules_version = scan_result.get("rules_version", "DPDP Rules 2025")

    rows = build_indicator_rows(scan_result)
    missing_keys = [
        r["key"] for r in rows if r["status"] in ("Missing", "Partial")
    ]
    score_hex = _score_color(score)
    scan_date = _format_scan_date(ts)

    turnitin_section = _build_turnitin_evidence_section(scan_result, policy_text)

    detailed_analysis_section = f"""
    <h2>Detailed Analysis</h2>
    {turnitin_section}

    <h3>Detailed Findings</h3>
    {_build_detailed_findings_cards(scan_result, policy_text, fast=fast_pdf)}
"""

    running_header = _build_letterhead_html("running") if backend == "weasyprint" else ""
    frame_header = _build_letterhead_html("frame") if backend == "xhtml2pdf" else ""
    # xhtml2pdf static frame content must be a direct body child (not inside a hidden wrapper).
    frame_block = (
        f'<div id="pdf-letterhead" aria-hidden="true">{frame_header}</div>'
        if frame_header
        else ""
    )
    header_sources = ""
    if running_header:
        header_sources = (
            f'<div class="letterhead-source" aria-hidden="true">{running_header}</div>'
        )

    pdf_ns = ' xmlns:pdf="http://www.xhtmlrenderer.org/pdf"' if backend == "xhtml2pdf" else ""
    template_switch = (
        '<pdf:nexttemplate name="body-page" />' if backend == "xhtml2pdf" else ""
    )

    return f"""<!DOCTYPE html>
<html{pdf_ns}>
<head>
    <meta charset="utf-8"/>
    <title>DPDP Compliance Report</title>
    <style>{_build_css(backend)}</style>
</head>
<body>
    {frame_block}
    {header_sources}
    <div class="cover cover-page">
        {_build_letterhead_html("cover")}
        <h1>DPDP Compliance Report</h1>
        <div class="cover-meta">
            <p><span class="meta-label">Website:</span> {html.escape(url)}</p>
            <p><span class="meta-label">Scan date:</span> {html.escape(scan_date)}</p>
            <p><span class="meta-label">Scanner version:</span> DPDP Scanner v{html.escape(scanner_version)}</p>
            <p><span class="meta-label">Ruleset:</span> {html.escape(rules_version)}</p>
        </div>
        <div class="score-block">
            <div class="score-label">Compliance Score</div>
            <div class="score" style="color:{score_hex};">{score}/100</div>
            <div class="verdict" style="color:{score_hex};">{html.escape(verdict)}</div>
        </div>
        <p class="cover-disclaimer">This report is generated by an automated assessment tool and is indicative only.</p>
        {template_switch}
    </div>

    <div class="body-content">
        <h2>Compliance Summary</h2>
        {_build_summary_table(rows)}

        {detailed_analysis_section}

        {_build_recommendations(missing_keys)}

        <div class="footer-note">
            Generated by DPDP Scanner v{html.escape(scanner_version)} &nbsp;|&nbsp;
            Ruleset: {html.escape(rules_version)} &nbsp;|&nbsp;
            For expert consultation: {html.escape(_CONSULT_EMAIL)} &nbsp;|&nbsp;
            This automated assessment is indicative only and does not constitute legal advice,
            certification, or regulatory approval under the DPDP Act 2025.
        </div>
    </div>
</body>
</html>"""

# Human-readable indicator labels for the summary table
INDICATOR_LABELS = {
    "notice_consent_purpose": "Notice & Consent / Purpose",
    "data_principal_rights": "Data Principal Rights",
    "grievance_officer_contact": "Grievance Officer / DPO Contact",
    "parental_consent_children": "Parental Consent (Children)",
    "consent_manager_mentioned": "Consent Manager",
    "cross_border_transfer": "Cross-Border Transfer",
    "data_retention_period": "Data Retention Period",
    "dpdp_act_reference": "DPDP Act / Rules Reference",
    "privacy_policy_exists": "Privacy Policy Exists",
    "cookie_banner": "Cookie Consent Banner",
}

# Highlight colours (CSS class → background) — matches legend spec
# Statutory gates plus contact phrases for PDF highlight fallback (Rule 9 partial disclosure)
HIGHLIGHT_KEYWORD_GATES: Dict[str, List[str]] = {
    **KEYWORD_GATES,
    "grievance_officer_contact": list(KEYWORD_GATES.get("grievance_officer_contact", []))
    + ["how to contact", "contact us", "contact information", "contact details"],
}

HIGHLIGHT_COLORS = {
    "notice_consent_purpose": "#d4e6f1",       # light blue
    "data_principal_rights": "#d4edda",        # light green
    "grievance_officer_contact": "#fff3cd",    # light yellow
    "parental_consent_children": "#f8d7da",    # light pink
    "consent_manager_mentioned": "#e8daef",    # light purple
    "cross_border_transfer": "#ffe5b4",        # light orange
    "data_retention_period": "#fdd9b5",        # light coral
    "dpdp_act_reference": "#d1ecf1",           # light cyan
}

FUZZY_MATCH_THRESHOLD = 0.85
NOT_LOCATED_MSG = "Relevant text not located automatically"

# Broader keyword lists for excerpt fallback when exact/fuzzy matching fails
FALLBACK_KEYWORDS: Dict[str, List[str]] = {
    "notice_consent_purpose": [
        "consent", "purpose", "collect", "information", "notice", "processing",
        "withdraw", "data principal", "personal data", "specified purpose",
    ],
    "data_principal_rights": [
        "access", "correction", "erasure", "delete", "grievance", "nominate",
        "right to access", "right to correction", "right to erasure", "rights",
    ],
    "grievance_officer_contact": [
        "grievance", "officer", "dpo", "data protection", "contact", "email",
        "complaint", "redressal", "how to contact", "contact us",
    ],
    "parental_consent_children": [
        "child", "children", "parent", "parental", "minor", "guardian",
        "verifiable consent",
    ],
    "consent_manager_mentioned": [
        "consent manager", "manage consent", "consent platform",
    ],
    "cross_border_transfer": [
        "transfer", "cross border", "cross-border", "outside india",
        "international", "foreign", "overseas",
    ],
    "data_retention_period": [
        "retention", "retain", "erased", "erase", "delete", "storage", "period",
    ],
    "dpdp_act_reference": [
        "dpdp", "digital personal data protection", "act 2023", "act 2025", "rules 2025",
        "data fiduciary", "data protection act",
    ],
    "privacy_policy_exists": [
        "privacy policy", "privacy notice", "personal data",
    ],
    "cookie_banner": [
        "cookie", "cookies", "tracking", "banner",
    ],
}

MANDATORY_INDICATORS = {
    "notice_consent_purpose",
    "data_principal_rights",
    "grievance_officer_contact",
    "privacy_policy_exists",
}

RECOMMENDATIONS: Dict[str, Tuple[str, str]] = {
    "notice_consent_purpose": (
        "Mandatory",
        "Add a clear notice section with an itemised description of personal data, "
        "specified purpose(s), and an equally easy way to withdraw consent, as required "
        "by Rule 3 of the DPDP Rules, 2025.",
    ),
    "data_principal_rights": (
        "Mandatory",
        "Publish how Data Principals can exercise rights (access, correction, erasure, "
        "nomination) and reference your grievance redressal process under Rule 14.",
    ),
    "grievance_officer_contact": (
        "Mandatory",
        "Add a section titled 'Grievance Officer' or 'Data Protection Officer' with name, "
        "email, and phone number, prominently published as required by Rule 9 and Rule 14(3).",
    ),
    "privacy_policy_exists": (
        "Mandatory",
        "Publish an accessible privacy policy linked from the website footer or app settings.",
    ),
    "parental_consent_children": (
        "Best practice",
        "If you process children's data, describe verifiable parental consent and due "
        "diligence measures per Rule 10.",
    ),
    "consent_manager_mentioned": (
        "Best practice",
        "If using a Consent Manager, disclose it and explain how users can manage consent "
        "via the platform (First Schedule Part B).",
    ),
    "cross_border_transfer": (
        "Best practice",
        "Disclose if personal data is transferred outside India and the safeguards applied, "
        "as contemplated under Rule 15.",
    ),
    "data_retention_period": (
        "Best practice",
        "State retention and erasure periods for personal data, aligned with Rule 8 and "
        "the Third Schedule where applicable.",
    ),
    "dpdp_act_reference": (
        "Best practice",
        "Explicitly reference the Digital Personal Data Protection Act, 2025 and/or "
        "DPDP Rules, 2025 to demonstrate legal alignment.",
    ),
    "cookie_banner": (
        "Best practice",
        "Implement a visible cookie/consent banner on first visit to support informed consent.",
    ),
}


def _score_color(score: int) -> str:
    """Cover-page score colour: green >60, orange 30-60, red <30."""
    if score > 60:
        return "#5bd6ab"
    if score >= 30:
        return "#ff9a4d"
    return "#ff8c8c"


# Normal PDF palette — light theme for traditional documents.
PDF_THEME = {
    "bg": "#ffffff",
    "surface": "#f8f9fa",
    "surface_alt": "#f1f3f5",
    "text": "#212529",
    "text_muted": "#495057",
    "text_faint": "#868e96",
    "heading": "#121a2f",
    "border": "#dee2e6",
    "border_soft": "#e9ecef",
    "footer": "#868e96",
    "found": "#12b886",
    "partial": "#fd7e14",
    "missing": "#fa5252",
    "notice_bg": "#fff3cd",
    "notice_border": "#ffeeba",
    "notice_text": "#856404",
    "notice_title": "#856404",
    "cta_bg": "#cce5ff",
    "cta_border": "#b8daff",
    "cta_text": "#004085",
    "cta_strong": "#004085",
    "rec_mandatory": "#fa5252",
    "rec_best": "#228be6",
}

PDF_HIGHLIGHT_COLORS = {
    "notice_consent_purpose": "#d4e6f1",
    "data_principal_rights": "#d4edda",
    "grievance_officer_contact": "#fff3cd",
    "parental_consent_children": "#f8d7da",
    "consent_manager_mentioned": "#e8daef",
    "cross_border_transfer": "#ffe5b4",
    "data_retention_period": "#fdd9b5",
    "dpdp_act_reference": "#d1ecf1",
}


def _highlight_span_attrs(indicator_key: str) -> str:
    """Inline + class attrs so PDF engines always paint highlights on backgrounds."""
    bg = PDF_HIGHLIGHT_COLORS.get(indicator_key, PDF_THEME["surface"])
    cls = f"highlight-{indicator_key.replace('_', '-')}"
    return (
        f'class="{cls}" '
        f'style="background-color:{bg};color:#000000;padding:1px 2px;border-radius:2px;"'
    )


def _wrap_doc_text(inner_html: str) -> str:
    return f'<div class="doc-text">{inner_html}</div>'


def _get_llm_indicators(scan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return LLM indicator dict from scan result, if DeepSeek analysis was used."""
    llm = (scan.get("analysis_details") or {}).get("llm_analysis")
    if llm and llm.get("indicators"):
        return llm["indicators"]
    return None


def _llm_indicator_points(status: str, confidence: float, weight: int) -> float:
    """Same scoring formula as compliance_checker._indicator_points_from_llm."""
    status_norm = str(status).strip().lower()
    conf_scale = max(0.0, min(100.0, confidence)) / 100.0
    if status_norm == "found":
        return round(weight * conf_scale, 1)
    if status_norm == "partial":
        return round(weight * 0.8 * conf_scale, 1)
    return 0.0


def _get_indicators_for_highlight(
    scan_result: Dict[str, Any],
    policy_text: str = "",
) -> Dict[str, Any]:
    """
    Build indicators dict for highlighting: LLM results enriched with fallback excerpts.
    """
    llm_indicators = _get_llm_indicators(scan_result)
    if llm_indicators:
        return _enrich_indicators_for_highlight(llm_indicators, policy_text)

    rows_by_key = {r["key"]: r for r in build_indicator_rows(scan_result)}
    synthetic: Dict[str, Any] = {}
    for key in HIGHLIGHT_COLORS:
        row = rows_by_key.get(key, {"status": "Missing"})
        status = row.get("status", "Missing")
        if str(status).lower() in ("found", "partial"):
            entry = _fallback_finding_for_indicator(key, row, policy_text)
            synthetic[key] = entry
    return synthetic


def _enrich_indicators_for_highlight(
    indicators: Dict[str, Any],
    policy_text: str,
) -> Dict[str, Any]:
    """
    Ensure Found/Partial indicators with unlocatable excerpts can use keyword fallback.
    Promote grievance to Partial for highlighting when only generic contact info exists.
    """
    if not policy_text.strip():
        return indicators

    enriched: Dict[str, Any] = {key: dict(entry) for key, entry in indicators.items()}

    for key in HIGHLIGHT_COLORS:
        entry = enriched.get(key)
        if not entry:
            continue

        status = str(entry.get("status", "")).strip()
        excerpt = (entry.get("excerpt") or "").strip()

        if status in ("Found", "Partial"):
            span = _find_verified_excerpt_span(policy_text, excerpt, key)
            if span:
                entry["excerpt"] = policy_text[span[0]:span[1]].strip()
            elif excerpt:
                entry["excerpt"] = NOT_LOCATED_MSG
            continue

        if key == "grievance_officer_contact" and status == "Missing":
            span = _find_verified_excerpt_span(policy_text, "", key)
            if span:
                entry["status"] = "Partial"
                entry["excerpt"] = policy_text[span[0]:span[1]].strip()

    return enriched


def _get_ai_confidence(indicator_key: str, ai_scores: Dict[str, float]) -> Optional[float]:
    """Return best AI confidence for a logical indicator."""
    if indicator_key == "notice_consent_purpose":
        c = ai_scores.get("data collection with consent", 0)
        p = ai_scores.get("purpose specification", 0)
        return (c + p) / 2 if (c or p) else None
    if indicator_key == "data_principal_rights":
        vals = [
            ai_scores.get("user right to access", 0),
            ai_scores.get("user right to correction", 0),
            ai_scores.get("user right to erasure", 0),
        ]
        return max(vals) if any(vals) else None
    if indicator_key == "dpdp_act_reference":
        return max(
            ai_scores.get("DPDP Act reference", 0),
            ai_scores.get("data fiduciary mentioned", 0),
        )
    labels = AI_LABEL_MAPPING.get(indicator_key, [])
    if not labels:
        return None
    return max(ai_scores.get(label, 0) for label in labels)


def _is_indicator_found(indicator_key: str, scan: Dict[str, Any]) -> bool:
    """Mirror compliance_checker detection rules."""
    ai_scores = scan.get("ai_indicators") or {}
    ai_available = scan.get("ai_available", True)

    if indicator_key == "privacy_policy_exists":
        return bool(scan.get("privacy_policy_found"))
    if indicator_key == "cookie_banner":
        return bool(scan.get("cookie_banner_found"))
    if indicator_key == "grievance_officer_contact":
        ai_hit = ai_scores.get("grievance officer contact details", 0) > 0.9
        regex_hit = bool(scan.get("grievance_officer_contact"))
        return ai_hit or regex_hit

    if not ai_available:
        return indicator_key in (scan.get("rule_indicators") or [])

    if indicator_key == "notice_consent_purpose":
        return (
            ai_scores.get("data collection with consent", 0) > 0.8
            and ai_scores.get("purpose specification", 0) > 0.8
        )
    if indicator_key == "data_principal_rights":
        return any(
            ai_scores.get(label, 0) > 0.8
            for label in [
                "user right to access",
                "user right to correction",
                "user right to erasure",
            ]
        )
    if indicator_key == "dpdp_act_reference":
        return max(
            ai_scores.get("DPDP Act reference", 0),
            ai_scores.get("data fiduciary mentioned", 0),
        ) > 0.8

    for label in AI_LABEL_MAPPING.get(indicator_key, []):
        if ai_scores.get(label, 0) > 0.8:
            return True
    return False


def _points_for_indicator(indicator_key: str, scan: Dict[str, Any]) -> float:
    """Compute points awarded for one indicator (matches scoring engine)."""
    llm_indicators = _get_llm_indicators(scan)
    if llm_indicators and indicator_key in llm_indicators:
        entry = llm_indicators[indicator_key]
        return _llm_indicator_points(
            entry.get("status", "Missing"),
            float(entry.get("confidence", 0)),
            SCORING_WEIGHTS[indicator_key],
        )
    if indicator_key == "cookie_banner" and scan.get("cookie_banner_found"):
        return SCORING_WEIGHTS["cookie_banner"]

    if not _is_indicator_found(indicator_key, scan):
        return 0

    weight = SCORING_WEIGHTS[indicator_key]
    ai_scores = scan.get("ai_indicators") or {}

    # Binary indicators — full weight when found
    if indicator_key in {"privacy_policy_exists", "cookie_banner", "grievance_officer_contact"}:
        return weight

    conf = _get_ai_confidence(indicator_key, ai_scores)
    if conf is None:
        return round(weight * 0.6, 1) if not scan.get("ai_available", True) else 0
    return round(weight * conf, 1)


def build_indicator_rows(scan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per SCORING_WEIGHTS entry for the summary table."""
    ai_scores = scan.get("ai_indicators") or {}
    llm_indicators = _get_llm_indicators(scan)
    rows = []
    for key in SCORING_WEIGHTS:
        if llm_indicators and key in llm_indicators:
            entry = llm_indicators[key]
            status = str(entry.get("status", "Missing"))
            conf_val = float(entry.get("confidence", 0))
            found = status.lower() in ("found", "partial")
            rows.append({
                "key": key,
                "indicator": INDICATOR_LABELS[key],
                "status": status if status in ("Found", "Partial", "Missing") else ("Found" if found else "Missing"),
                "rule": RULE_CITATIONS[key],
                "points": _points_for_indicator(key, scan),
                "max_points": SCORING_WEIGHTS[key],
            })
        elif key == "cookie_banner":
            found = bool(scan.get("cookie_banner_found"))
            rows.append({
                "key": key,
                "indicator": INDICATOR_LABELS[key],
                "status": "Found" if found else "Missing",
                "rule": RULE_CITATIONS[key],
                "points": _points_for_indicator(key, scan),
                "max_points": SCORING_WEIGHTS[key],
            })
        else:
            found = _is_indicator_found(key, scan)
            conf = _get_ai_confidence(key, ai_scores)
            rows.append({
                "key": key,
                "indicator": INDICATOR_LABELS[key],
                "status": "Found" if found else "Missing",
                "rule": RULE_CITATIONS[key],
                "points": _points_for_indicator(key, scan),
                "max_points": SCORING_WEIGHTS[key],
            })
    return rows


def _normalize_for_match(text: str) -> str:
    """Collapse whitespace and normalise punctuation for reliable excerpt matching."""
    normalized = text.replace("\u201c", '"').replace("\u201d", '"')
    normalized = normalized.replace("\u2018", "'").replace("\u2019", "'")
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = re.sub(r"[\u2022\u2023\u25E6\u2043]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized.strip())
    return normalized.rstrip(".").strip().lower()


def _excerpt_in_policy(excerpt: str, policy_text: str) -> bool:
    """True if excerpt matches the policy text (exact, normalised, or fuzzy)."""
    if not excerpt or not policy_text:
        return False
    if excerpt in policy_text:
        return True
    norm_excerpt = _normalize_for_match(excerpt)
    norm_policy = _normalize_for_match(policy_text)
    if norm_excerpt in norm_policy:
        return True
    pattern = re.escape(norm_excerpt).replace(r"\ ", r"\s+")
    if re.search(pattern, policy_text, flags=re.IGNORECASE):
        return True
    return _find_fuzzy_excerpt(policy_text, excerpt) is not None


def _get_fallback_keywords(indicator_key: str) -> List[str]:
    """Merge statutory gate keywords with broader fallback terms (deduplicated)."""
    seen: Set[str] = set()
    keywords: List[str] = []
    for kw in HIGHLIGHT_KEYWORD_GATES.get(indicator_key, []) + FALLBACK_KEYWORDS.get(indicator_key, []):
        key_lower = kw.lower()
        if key_lower not in seen:
            seen.add(key_lower)
            keywords.append(kw)
    return keywords


UNVERIFIABLE_EXCERPT_MSG = "[Excerpt not verifiable in original text]"


def _sanitize_excerpt_for_display(
    excerpt: str,
    policy_text: str,
    indicator_key: str,
    fast: bool = False,
) -> str:
    """
    Resolve a display-ready excerpt: verified policy text, keyword fallback, or a soft note.
    """
    excerpt = (excerpt or "").strip()
    if excerpt in (UNVERIFIABLE_EXCERPT_MSG, NOT_LOCATED_MSG):
        excerpt = ""

    if not (policy_text or "").strip():
        return NOT_LOCATED_MSG if excerpt else ""

    span = _find_verified_excerpt_span(policy_text, excerpt, indicator_key, fast=fast)
    if span:
        return policy_text[span[0]:span[1]].strip()

    if excerpt and not fast:
        return NOT_LOCATED_MSG
    if excerpt and fast:
        return excerpt
    return ""


def _extract_recommendation_from_analysis(analysis: str) -> Optional[str]:
    """Pull a recommendation sentence from LLM analysis if present."""
    if not analysis:
        return None
    for sentence in re.split(r"(?<=[.!?])\s+", analysis.strip()):
        s = sentence.strip()
        lower = s.lower()
        if lower.startswith("to comply"):
            return s
        if lower.startswith("recommendation:"):
            return s.split(":", 1)[-1].strip() or s
    return None


def _build_gate_keyword_recommendation(indicator_key: str, policy_text: str) -> str:
    """Construct a rule-specific recommendation from gate keywords found/missing in policy."""
    rule = RULE_CITATIONS.get(indicator_key, "the applicable DPDP Rule")
    keywords = KEYWORD_GATES.get(indicator_key, [])
    text_lower = policy_text.lower()

    found_kw = next((kw for kw in keywords if kw.lower() in text_lower), None)
    missing_kw = next((kw for kw in keywords if kw.lower() not in text_lower), keywords[0] if keywords else None)

    if found_kw and missing_kw and found_kw.lower() != missing_kw.lower():
        return (
            f"The policy mentions '{found_kw}' but does not explicitly address '{missing_kw}'. "
            f"Add a clause as required by {rule}."
        )
    if found_kw:
        return (
            f"The policy mentions '{found_kw}' but does not fully meet {rule} requirements. "
            f"Add explicit statutory language to comply."
        )
    rec = RECOMMENDATIONS.get(indicator_key)
    if rec:
        return rec[1]
    return f"Add explicit disclosure for {INDICATOR_LABELS.get(indicator_key, indicator_key)} per {rule}."


def _resolve_recommendation(
    entry: Dict[str, Any],
    indicator_key: str,
    policy_text: str,
    status_lower: str,
) -> str:
    """Prefer LLM recommendation, then analysis extraction, then gate-keyword construction."""
    if status_lower == "found":
        return ""

    explicit = (entry.get("recommendation") or "").strip()
    if explicit:
        return explicit

    from_analysis = _extract_recommendation_from_analysis(entry.get("analysis", ""))
    if from_analysis:
        return from_analysis

    return _build_gate_keyword_recommendation(indicator_key, policy_text)


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace to a single space for fuzzy matching."""
    return re.sub(r"\s+", " ", text.strip())


def _extract_sentence_bounds(
    text: str,
    match_start: int,
    match_end: int,
    min_len: int = 100,
) -> Tuple[int, int]:
    """
    Expand a match to the containing sentence(s), bounded by . ! ? or newline.
    Optionally pad to min_len (use min_len=0 for phrase expansion).
    """
    start = 0
    for i in range(match_start - 1, -1, -1):
        if text[i] in ".!?\n":
            start = i + 1
            break

    end = len(text)
    for i in range(match_end, len(text)):
        if text[i] in ".!?\n":
            end = i + 1
            break

    if min_len > 0 and end - start < min_len:
        deficit = min_len - (end - start)
        start = max(0, start - deficit // 2)
        end = min(len(text), end + (deficit - deficit // 2))

    return start, end


def _find_fuzzy_excerpt(text: str, excerpt: str) -> Optional[Tuple[int, int]]:
    """
    Locate a policy substring with SequenceMatcher similarity above FUZZY_MATCH_THRESHOLD.
    Handles minor paraphrasing, spacing, and punctuation differences.
    """
    if not excerpt or not text or excerpt in (UNVERIFIABLE_EXCERPT_MSG, NOT_LOCATED_MSG):
        return None

    norm_excerpt = _normalize_for_match(excerpt)
    if len(norm_excerpt) < 20:
        return None

    target_len = len(norm_excerpt)
    text_len = len(text)
    min_len = max(20, int(target_len * 0.80))
    max_len = min(text_len, int(target_len * 1.20))

    best_ratio = 0.0
    best_span: Optional[Tuple[int, int]] = None
    coarse_step = max(4, target_len // 12)

    def _score_window(start: int, win_len: int) -> float:
        if start < 0 or start + win_len > text_len:
            return 0.0
        window = text[start:start + win_len]
        return SequenceMatcher(None, _normalize_for_match(window), norm_excerpt).ratio()

    for start in range(0, max(1, text_len - min_len + 1), coarse_step):
        for win_len in {min_len, target_len, max_len}:
            ratio = _score_window(start, win_len)
            if ratio > best_ratio:
                best_ratio = ratio
                best_span = (start, start + win_len)

    if best_ratio < FUZZY_MATCH_THRESHOLD or not best_span:
        return None

    refine_lo = max(0, best_span[0] - coarse_step * 2)
    refine_hi = min(text_len, best_span[1] + coarse_step * 2)
    for start in range(refine_lo, refine_hi):
        for win_len in range(min_len, max_len + 1):
            ratio = _score_window(start, win_len)
            if ratio > best_ratio:
                best_ratio = ratio
                best_span = (start, start + win_len)

    if best_ratio >= FUZZY_MATCH_THRESHOLD and best_span:
        return best_span
    return None


def _find_verified_excerpt_span(
    text: str,
    excerpt: str,
    indicator_key: str,
    fast: bool = False,
) -> Optional[Tuple[int, int]]:
    """
    Resolve excerpt location: exact → phrase → fuzzy → keyword sentence fallback.
    When fast=True (PDF generation), skip fuzzy/keyword passes on large documents.
    """
    if not text:
        return None

    excerpt = (excerpt or "").strip()
    if excerpt in (UNVERIFIABLE_EXCERPT_MSG, NOT_LOCATED_MSG):
        excerpt = ""

    if excerpt:
        match = _find_exact_excerpt(text, excerpt)
        if match:
            return match

        match = _find_phrase_excerpt(text, excerpt)
        if match:
            return match

        if not fast:
            fuzzy = _find_fuzzy_excerpt(text, excerpt)
            if fuzzy:
                return _extract_sentence_bounds(text, fuzzy[0], fuzzy[1], min_len=0)

    if fast:
        return None
    return _find_keyword_sentence(text, indicator_key)


def _find_exact_excerpt(text: str, excerpt: str) -> Optional[Tuple[int, int]]:
    """
    Case-sensitive exact match with whitespace/punctuation normalisation.
    Trims trailing periods on the excerpt before comparing.
    """
    if not excerpt or excerpt in (UNVERIFIABLE_EXCERPT_MSG, NOT_LOCATED_MSG):
        return None

    trimmed = excerpt.rstrip(". ").strip()
    if trimmed in text:
        idx = text.find(trimmed)
        return idx, idx + len(trimmed)

    norm = _normalize_for_match(excerpt)
    if not norm:
        return None
    pattern = re.escape(norm).replace(r"\ ", r"\s+")
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        return match.start(), match.end()
    return None


def _find_phrase_excerpt(text: str, excerpt: str) -> Optional[Tuple[int, int]]:
    """First 10 words of excerpt, expand to full sentence boundaries."""
    words = _normalize_for_match(excerpt).split()
    if not words:
        return None
    phrase = " ".join(words[:10])
    pattern = re.escape(phrase).replace(r"\ ", r"\s+")
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None

    return _extract_sentence_bounds(text, match.start(), match.end(), min_len=0)


def _find_keyword_sentence(text: str, indicator_key: str) -> Optional[Tuple[int, int]]:
    """Fallback: earliest broad keyword hit, expand to containing sentence."""
    text_lower = text.lower()
    best_idx: Optional[int] = None
    best_kw: Optional[str] = None
    for kw in _get_fallback_keywords(indicator_key):
        idx = text_lower.find(kw.lower())
        if idx != -1 and (best_idx is None or idx < best_idx):
            best_idx = idx
            best_kw = kw
    if best_idx is not None and best_kw is not None:
        return _extract_sentence_bounds(text, best_idx, best_idx + len(best_kw))
    return None


def highlight_text(original_text: str, indicators: Dict[str, Any]) -> Tuple[str, Set[str]]:
    """
    Turnitin-style highlighting with exact → phrase → fuzzy → keyword matching.

    For each Found/Partial indicator, locate supporting text in the policy and wrap it.
    """
    if not original_text:
        return _wrap_doc_text(html.escape("")), set()

    ranges: List[Tuple[int, int, str]] = []

    for key in HIGHLIGHT_COLORS:
        entry = (indicators or {}).get(key)
        if not entry:
            continue
        status = str(entry.get("status", "")).strip()
        if status not in ("Found", "Partial"):
            continue

        excerpt = (entry.get("excerpt") or "").strip()
        if excerpt in (UNVERIFIABLE_EXCERPT_MSG, NOT_LOCATED_MSG):
            excerpt = ""

        match = _find_verified_excerpt_span(original_text, excerpt, key)

        if match:
            ranges.append((match[0], match[1], key))

    ranges.sort(key=lambda r: r[0])

    if not ranges:
        return _wrap_doc_text(html.escape(original_text)), set()

    # Character-level paint: first range in sort order wins on overlap
    keys_at: List[Optional[str]] = [None] * len(original_text)
    for start, end, key in ranges:
        for i in range(start, min(end, len(original_text))):
            if keys_at[i] is None:
                keys_at[i] = key

    highlighted_keys: Set[str] = set()
    parts: List[str] = []
    i = 0
    while i < len(original_text):
        if keys_at[i]:
            j = i + 1
            while j < len(original_text) and keys_at[j] == keys_at[i]:
                j += 1
            key = keys_at[i]
            highlighted_keys.add(key)
            parts.append(
                f"<span {_highlight_span_attrs(key)}>{html.escape(original_text[i:j])}</span>"
            )
            i = j
        else:
            j = i + 1
            while j < len(original_text) and keys_at[j] is None:
                j += 1
            parts.append(html.escape(original_text[i:j]))
            i = j

    return _wrap_doc_text("".join(parts)), highlighted_keys


def _build_css(backend: str = "weasyprint") -> str:
    """Build CSS; WeasyPrint gets @page footers, xhtml2pdf gets simplified rules."""
    t = PDF_THEME
    color_rules = "\n".join(
        f".highlight-{k.replace('_', '-')} {{ background: {v}; color: #000000; padding: 1px 2px; border-radius: 2px; font-weight: 600; }}"
        for k, v in PDF_HIGHLIGHT_COLORS.items()
    )

    footer_text = (
        f'"Generated by DPDP Scanner | For expert consultation: {_CONSULT_EMAIL} | '
        f'This is an automated assessment and not legal advice. | Page " counter(page) " of " counter(pages)'
    )

    page_rules = ""
    running_header_rules = ""
    xhtml2pdf_page_rules = ""
    if backend == "weasyprint":
        running_header_rules = """
    .letterhead-source {
        position: absolute;
        left: -9999px;
        top: 0;
        width: 0;
        height: 0;
        overflow: hidden;
    }
    .letterhead-running {
        position: running(page-header);
        width: 100%;
        max-height: 2.2cm;
        object-fit: contain;
        object-position: left top;
    }"""
        page_rules = f"""
    @page {{
        size: A4;
        margin: 3.2cm 2cm 2.5cm 2cm;
        background: {t['bg']};
        @top-left {{
            content: element(page-header);
            width: 100%;
            vertical-align: bottom;
        }}
        @bottom-center {{
            content: {footer_text};
            font-size: 8pt;
            color: {t['footer']};
        }}
    }}
    @page :first {{
        margin-top: 2cm;
        @top-left {{ content: none; }}
    }}"""
    elif backend == "xhtml2pdf":
        xhtml2pdf_page_rules = """
    /* First @page must stay unnamed — xhtml2pdf uses it as the default (cover). */
    @page {
        size: a4 portrait;
        @frame content_frame {
            left: 2cm;
            right: 2cm;
            top: 2cm;
            bottom: 2cm;
        }
    }
    @page body-page {
        size: a4 portrait;
        @frame header_frame {
            -pdf-frame-content: pdf-letterhead;
            top: 0.55cm;
            left: 2cm;
            right: 2cm;
            height: 2.3cm;
        }
        @frame content_frame {
            left: 2cm;
            right: 2cm;
            top: 3.2cm;
            bottom: 2.5cm;
        }
    }
    .cover-page {
        page-break-after: always;
    }
    #pdf-letterhead {
        position: absolute;
        left: -9999px;
        top: 0;
        width: 0;
        height: 0;
        overflow: hidden;
    }
    #pdf-letterhead .letterhead-frame-img {
        display: block;
    }
    .letterhead-source {
        position: absolute;
        left: -9999px;
        top: 0;
        width: 0;
        height: 0;
        overflow: hidden;
    }"""

    return f"""
    {running_header_rules}
    {xhtml2pdf_page_rules}
    {page_rules}
    html, body {{
        font-family: 'Segoe UI', Arial, sans-serif;
        color: {t['text']};
        background: {t['bg']};
        font-size: 11pt;
        line-height: 1.5;
        margin: 0;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }}
    .letterhead {{
        display: block;
        width: 480pt;
        max-height: 2.4cm;
        object-fit: contain;
        object-position: left top;
        margin: 0 0 24px;
    }}
    .cover {{
        page-break-after: always;
        break-after: page;
        text-align: center;
        padding-top: 12px;
        background: {t['bg']};
    }}
    .cover .letterhead {{
        margin-bottom: 32px;
    }}
    .cover h1 {{
        font-size: 22pt;
        font-weight: 700;
        color: {t['heading']};
        margin: 0 0 24px;
    }}
    .cover-meta {{
        text-align: left;
        display: inline-block;
        margin: 0 auto 28px;
        font-size: 10.5pt;
        color: {t['text_muted']};
    }}
    .cover-meta p {{ margin: 6px 0; }}
    .meta-label {{ font-weight: 600; color: {t['heading']}; }}
    .score-block {{ margin: 28px 0 20px; }}
    .score-label {{
        font-size: 9pt;
        font-weight: 700;
        text-transform: uppercase;
        color: {t['text_faint']};
        margin-bottom: 8px;
    }}
    .score {{ font-size: 56pt; font-weight: 800; margin: 8px 0; line-height: 1; }}
    .verdict {{ font-size: 18pt; font-weight: 600; margin-top: 4px; }}
    .cover-disclaimer {{
        font-size: 9pt;
        color: {t['text_faint']};
        font-style: italic;
        margin-top: 32px;
        max-width: 420px;
        margin-left: auto;
        margin-right: auto;
    }}
    .body-content {{ padding-top: 4px; background: {t['bg']}; }}
    table.summary {{ width: 100%; border-collapse: collapse; margin: 16px 0 24px; font-size: 10pt; }}
    table.summary th, table.summary td {{ border: 1px solid {t['border']}; padding: 8px 10px; text-align: left; vertical-align: top; color: {t['text']}; }}
    table.summary th {{ background: {t['surface']}; font-weight: 600; color: {t['text_muted']}; }}
    table.summary tr:nth-child(even) {{ background: {t['surface_alt']}; }}
    .found {{ color: {t['found']}; font-weight: 600; }}
    .partial {{ color: {t['partial']}; font-weight: 600; }}
    .missing {{ color: {t['missing']}; font-weight: 600; }}
    h2 {{
        color: {t['heading']};
        border-bottom: 2px solid {t['border']};
        padding-bottom: 6px;
        margin-top: 28px;
        font-size: 14pt;
        font-weight: 700;
    }}
    h3 {{
        color: {t['heading']};
        font-size: 12pt;
        font-weight: 700;
        margin-top: 22px;
        margin-bottom: 8px;
    }}
    .section-lead {{ font-size: 10pt; color: {t['text_faint']}; margin: 0 0 12px; }}
    .doc-text {{
        font-family: Georgia, 'Times New Roman', serif;
        font-size: 9.5pt;
        white-space: pre-wrap;
        word-wrap: break-word;
        background: {t['surface']};
        border: 1px solid {t['border']};
        color: {t['text']};
        padding: 16px;
        border-radius: 6px;
        line-height: 1.6;
    }}
    .doc-text span[class^="highlight-"] {{
        -webkit-box-decoration-break: clone;
        box-decoration-break: clone;
        print-color-adjust: exact;
        -webkit-print-color-adjust: exact;
    }}
    .legend {{ margin: 10px 0 14px; line-height: 1.8; }}
    .legend strong {{ font-size: 9pt; color: {t['text_muted']}; margin-right: 6px; }}
    .legend span {{ display: inline-block; padding: 3px 10px; margin: 2px 6px 2px 0; border-radius: 4px; font-size: 8.5pt; color: {t['text']}; }}
    .policy-missing-notice {{
        background: {t['notice_bg']};
        border: 1px solid {t['notice_border']};
        border-left: 4px solid {t['notice_title']};
        padding: 14px 16px;
        border-radius: 4px;
        font-size: 10pt;
        color: {t['notice_text']};
        line-height: 1.55;
    }}
    .policy-missing-notice strong {{ display: block; margin-bottom: 6px; color: {t['notice_title']}; }}
    .policy-truncate-note {{
        font-size: 9pt;
        color: {t['text_faint']};
        margin: 0 0 12px;
        line-height: 1.5;
        font-style: italic;
    }}
    .insight-card {{
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 14px 16px;
        margin: 12px 0;
        page-break-inside: avoid;
        background: {t['surface']};
    }}
    .insight-card.found {{ border-left: 4px solid {t['found']}; }}
    .insight-card.partial {{ border-left: 4px solid {t['partial']}; }}
    .insight-card.missing {{ border-left: 4px solid {t['missing']}; }}
    .insight-header {{ font-weight: 700; font-size: 11pt; margin-bottom: 6px; color: {t['heading']}; }}
    .insight-meta {{ font-size: 9pt; color: {t['text_faint']}; margin-bottom: 8px; }}
    .insight-analysis {{ font-size: 10pt; line-height: 1.55; color: {t['text']}; margin-bottom: 8px; }}
    .status-badge {{
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 8pt;
        font-weight: 700;
        text-transform: uppercase;
        color: #10162a;
        margin-left: 8px;
        vertical-align: middle;
    }}
    .status-badge.found {{ background: {t['found']}; }}
    .status-badge.partial {{ background: {t['partial']}; }}
    .status-badge.missing {{ background: {t['missing']}; }}
    .finding-blockquote {{
        border-left: 3px solid {t['text_faint']};
        margin: 10px 0;
        padding: 8px 12px;
        background: {t['surface_alt']};
        font-style: italic;
        font-size: 9.5pt;
        color: {t['text_muted']};
    }}
    .excerpt-not-located {{
        margin: 8px 0 0;
        font-size: 9pt;
        color: {t['text_faint']};
        font-style: italic;
    }}
    .finding-cta {{
        background: {t['cta_bg']};
        border: 1px solid {t['cta_border']};
        border-radius: 6px;
        padding: 10px 12px;
        margin-top: 10px;
        font-size: 9.5pt;
        color: {t['cta_text']};
    }}
    .finding-cta strong {{ color: {t['cta_strong']}; }}
    .rec-mandatory {{ border-left: 4px solid {t['rec_mandatory']}; padding-left: 12px; margin: 12px 0; font-size: 10pt; color: {t['text']}; }}
    .rec-best {{ border-left: 4px solid {t['rec_best']}; padding-left: 12px; margin: 12px 0; font-size: 10pt; color: {t['text']}; }}
    .rec-mandatory strong, .rec-best strong {{ color: {t['heading']}; }}
    .footer-note {{
        margin-top: 40px;
        padding-top: 12px;
        border-top: 1px solid {t['border']};
        font-size: 8pt;
        color: {t['footer']};
        text-align: center;
        line-height: 1.6;
    }}
    {color_rules}
    """


def _build_summary_table(rows: List[Dict[str, Any]]) -> str:
    trs = []
    for r in rows:
        status_cls = _status_css_class(r["status"])
        trs.append(f"""
        <tr>
            <td>{html.escape(r['indicator'])}</td>
            <td class="{status_cls}">{r['status']}</td>
            <td>{html.escape(r['rule'])}</td>
            <td>{r['points']} / {r['max_points']}</td>
        </tr>""")
    return f"""
    <table class="summary">
        <thead>
            <tr>
                <th>Indicator</th><th>Status</th>
                <th>DPDP Rule Reference</th><th>Points</th>
            </tr>
        </thead>
        <tbody>{''.join(trs)}</tbody>
    </table>"""


def _fallback_finding_for_indicator(
    key: str,
    row: Dict[str, Any],
    policy_text: str,
) -> Dict[str, Any]:
    """Auto-generate finding fields when DeepSeek analysis is unavailable."""
    status = row.get("status", "Missing")
    rule = RULE_CITATIONS.get(key, "")

    excerpt = ""
    text_lower = policy_text.lower()
    for kw in _get_fallback_keywords(key):
        idx = text_lower.find(kw.lower())
        if idx != -1:
            start, end = _extract_sentence_bounds(policy_text, idx, idx + len(kw))
            excerpt = policy_text[start:end].strip()
            break

    if status == "Found":
        analysis = (
            f"The policy mentions relevant language for {INDICATOR_LABELS.get(key, key)} "
            f"and appears to address {rule} requirements."
        )
        recommendation = ""
    elif status == "Partial":
        kw = KEYWORD_GATES.get(key, ["related terms"])[0]
        analysis = (
            f"The policy mentions \"{kw}\" but does not fully meet {rule} requirements."
        )
        rec_tpl = RECOMMENDATIONS.get(key)
        recommendation = rec_tpl[1] if rec_tpl else f"Strengthen disclosure for {INDICATOR_LABELS.get(key, key)}."
    else:
        analysis = (
            f"No relevant text found for {INDICATOR_LABELS.get(key, key)}. "
            f"This indicator is required under {rule}."
        )
        rec_tpl = RECOMMENDATIONS.get(key)
        recommendation = rec_tpl[1] if rec_tpl else f"Add explicit disclosure for {INDICATOR_LABELS.get(key, key)}."

    return {
        "status": status,
        "confidence": 60 if status == "Partial" else (100 if status == "Found" else 0),
        "excerpt": excerpt,
        "analysis": analysis,
        "recommendation": recommendation,
    }


def _build_detailed_findings_cards(
    scan_result: Dict[str, Any],
    policy_text: str,
    fast: bool = False,
) -> str:
    """
    Card-based deep analysis per indicator (analysis, excerpt blockquote, recommendation CTA).
    """
    llm_indicators = _get_llm_indicators(scan_result)
    rows_by_key = {r["key"]: r for r in build_indicator_rows(scan_result)}
    cards: List[str] = []

    for key in SCORING_WEIGHTS:
        if key == "cookie_banner":
            continue

        if llm_indicators and key in llm_indicators:
            entry = llm_indicators[key]
        else:
            entry = _fallback_finding_for_indicator(
                key, rows_by_key.get(key, {"status": "Missing"}), policy_text
            )

        status = str(entry.get("status", "Missing"))
        status_lower = status.lower()
        css = "found" if status_lower == "found" else ("partial" if status_lower == "partial" else "missing")

        label = INDICATOR_LABELS.get(key, key)
        rule = RULE_CITATIONS.get(key, "")
        confidence = float(entry.get("confidence", 0))
        raw_excerpt = (entry.get("excerpt") or "").strip()
        analysis = (entry.get("analysis") or "").strip()

        # Verify excerpt against policy text before display
        display_excerpt = _sanitize_excerpt_for_display(raw_excerpt, policy_text, key, fast=fast)
        recommendation = _resolve_recommendation(entry, key, policy_text, status_lower)

        excerpt_block = ""
        if display_excerpt == NOT_LOCATED_MSG:
            if raw_excerpt and status_lower in ("found", "partial"):
                excerpt_block = (
                    f'<p class="excerpt-not-located"><em>'
                    f"{html.escape(NOT_LOCATED_MSG)}</em></p>"
                )
        elif display_excerpt:
            excerpt_block = (
                f'<blockquote class="finding-blockquote">{html.escape(display_excerpt)}</blockquote>'
            )

        cta_block = ""
        if status_lower in ("missing", "partial") and recommendation:
            cta_block = (
                f'<div class="finding-cta"><strong>Recommended action:</strong> '
                f"{html.escape(recommendation)}</div>"
            )

        cards.append(f"""
        <div class="insight-card {css}">
            <div class="insight-header">
                {html.escape(label)}
                <span class="status-badge {css}">{html.escape(status)}</span>
            </div>
            <div class="insight-meta">{html.escape(rule)}</div>
            <div class="insight-analysis">{html.escape(analysis)}</div>
            {excerpt_block}
            {cta_block}
        </div>""")

    return (
        '<p class="section-lead">Indicator-by-indicator analysis with policy excerpts and actionable recommendations.</p>'
        + "".join(cards)
    )


def _build_recommendations(missing_keys: List[str]) -> str:
    mandatory, best = [], []
    for key in missing_keys:
        priority, advice = RECOMMENDATIONS.get(
            key,
            ("Best practice", f"Address: {INDICATOR_LABELS.get(key, key)}"),
        )
        css_cls = "rec-mandatory" if priority == "Mandatory" else "rec-best"
        block = (
            f"<div class='{css_cls}'>"
            f"<strong>{html.escape(INDICATOR_LABELS[key])}</strong> ({priority})<br>"
            f"{html.escape(advice)}</div>"
        )
        (mandatory if priority == "Mandatory" else best).append(block)

    parts = ["<h2>Recommendations</h2>"]
    if mandatory:
        parts.append("<h3>Mandatory Improvements</h3>" + "".join(mandatory))
    if best:
        parts.append("<h3>Best Practice Improvements</h3>" + "".join(best))
    if not mandatory and not best:
        parts.append("<p>No missing indicators — strong compliance posture.</p>")
    return "".join(parts)


def _build_legend(highlighted_keys: Set[str]) -> str:
    """Show legend entries only for indicators that have at least one highlight in the text."""
    items = []
    for key in sorted(highlighted_keys):
        if key in PDF_HIGHLIGHT_COLORS:
            cls = key.replace("_", "-")
            label = html.escape(INDICATOR_LABELS.get(key, key))
            items.append(
                f'<span {_highlight_span_attrs(key)}>{label}</span>'
            )
    if not items:
        return ""
    return "<div class='legend'><strong>Highlight legend:</strong> " + " ".join(items) + "</div>"


def generate_pdf_report(
    scan_result: Dict[str, Any],
    policy_text: str,
    terms_text: str = "",
    cookie_text: str = "",
) -> bytes:
    """
    Build a professional PDF report from scan results and extracted texts.

    Args:
        scan_result: ComplianceReport.to_dict() or equivalent.
        policy_text: Full privacy policy text.
        terms_text: Full terms of service text (optional).
        cookie_text: Full cookie policy text (optional).

    Returns:
        PDF file contents as bytes.
    """
    global _weasyprint_available

    policy_text, terms_text, cookie_text = resolve_policy_texts_for_report(
        scan_result, policy_text, terms_text, cookie_text
    )

    # Pick CSS backend based on available renderer
    backend = "weasyprint" if _weasyprint_available is not False else "xhtml2pdf"
    html_doc = _build_html_document(
        scan_result, policy_text, terms_text, cookie_text, backend=backend, fast_pdf=True
    )
    base_url = str(_templates_dir())

    if _weasyprint_available is not False:
        try:
            from weasyprint import HTML
            _weasyprint_available = True
            return HTML(string=html_doc, base_url=base_url).write_pdf()
        except (ImportError, OSError) as e:
            logger.warning("WeasyPrint unavailable (%s), using xhtml2pdf fallback", e)
            _weasyprint_available = False
            html_doc = _build_html_document(
                scan_result, policy_text, terms_text, cookie_text, backend="xhtml2pdf", fast_pdf=True
            )

    from xhtml2pdf import pisa

    result = BytesIO()
    status = pisa.CreatePDF(html_doc, dest=result, encoding="utf-8", path=base_url)
    if status.err:
        raise RuntimeError(f"xhtml2pdf failed with {status.err} error(s)")
    return result.getvalue()
