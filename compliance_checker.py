"""
Hybrid compliance checking engine combining AI analysis and rule-based checks.
Implements the scoring logic and verdict generation.

OVERHAULED based on Digital Personal Data Protection Rules, 2025
All indicators, keyword gates, and scoring weights are directly rooted in
the actual legal requirements from the DPDP Rules.
"""

import logging
import os
import re
from typing import Dict, List, Optional

from config import RULES_VERSION, SCANNER_VERSION
from llm_analyzer import (
    analyze_with_deepseek_expert,
    detect_injection_phrases,
    get_last_deepseek_error,
    llm_indicators_to_ai_scores,
)
from utils import find_grievance_officer_contact

logger = logging.getLogger(__name__)


# =============================================================================
# DPDP RULES 2025 - RULE CITATIONS MAPPING
# Maps each compliance indicator to its corresponding DPDP Rule section
# =============================================================================
RULE_CITATIONS = {
    "notice_consent_purpose": "Rule 3 - Notice by Data Fiduciary",
    "data_principal_rights": "Rule 14 - Rights of Data Principals",
    "grievance_officer_contact": "Rule 9 + Rule 14(3) - Grievance Redressal",
    "parental_consent_children": "Rule 10 - Verifiable Parental Consent",
    "consent_manager_mentioned": "First Schedule Part B - Consent Manager",
    "cross_border_transfer": "Rule 15 - Transfer Outside India",
    "data_retention_period": "Third Schedule - Retention Periods",
    "dpdp_act_reference": "Act/Rules Reference",
    "privacy_policy_exists": "General Requirement",
    "cookie_banner": "Consent Mechanism (Optional)",
}

# =============================================================================
# SCORING WEIGHTS - Reflect Legal Importance from DPDP Rules 2025
# Total = 100 points; genuinely compliant sites should score 80+
# =============================================================================
SCORING_WEIGHTS = {
    "notice_consent_purpose": 25,      # Core mandatory requirement (Rule 3)
    "data_principal_rights": 20,       # Mandatory (Rule 14)
    "grievance_officer_contact": 20,   # Mandatory (Rule 9 + Rule 14(3))
    "parental_consent_children": 10,   # Required if processing child data (Rule 10)
    "consent_manager_mentioned": 5,    # If using Consent Manager (First Schedule)
    "cross_border_transfer": 5,        # If transferring outside India (Rule 15)
    "data_retention_period": 5,        # Retention disclosure (Third Schedule)
    "dpdp_act_reference": 5,           # Explicit Act/Rules reference
    "privacy_policy_exists": 5,        # Baseline requirement
    "cookie_banner": 5,                # Optional consent mechanism indicator
}

# =============================================================================
# KEYWORD GATES - Based on Exact Legal Language from DPDP Rules 2025
# Simple single-keyword lists for highlighting / fallback; strict multi-phrase
# validation for Rule 3, Rule 14, and retention is enforced in apply_keyword_gates.
# =============================================================================
KEYWORD_GATES = {
    # Rule 3: Strict gate requires 2+ phrases + mandatory "consent" (see _passes_rule3_notice_gate)
    "notice_consent_purpose": [
        "itemised description", "specified purpose", "withdraw", "data principal", "consent",
    ],
    
    # Rule 14: Strict gate requires 2+ exact phrases (see _passes_rule14_rights_gate)
    "data_principal_rights": [
        "right to access", "right to correction", "right to erasure",
        "grievance redressal", "nominate",
    ],
    
    # Rule 9 + 14(3): Must publish contact of DPO or person who answers questions
    "grievance_officer_contact": [
        "grievance officer", "data protection officer", "person who is able to answer",
        "grievance", "officer", "grievance redressal system", "ninety days", "90 days"
    ],
    
    # Rule 10: Verifiable consent of parent for child's data
    "parental_consent_children": [
        "verifiable consent of the parent", "verifiable consent", "child",
        "children", "parental consent", "parent", "guardian", "minor"
    ],
    
    # First Schedule Part B: Consent Manager obligations
    "consent_manager_mentioned": [
        "consent manager", "Consent Manager"
    ],
    
    # Rule 15: Transfer outside India conditions
    "cross_border_transfer": [
        "transfer outside india", "cross border", "outside the territory of india",
        "transfer outside", "international transfer", "cross-border"
    ],
    
    # Third Schedule / Rule 8: Strict gate requires time frame near retention language
    "data_retention_period": [
        "retention", "erased", "retain", "erase", "retention period", "data retention",
    ],
    
    # Act/Rules reference
    "dpdp_act_reference": [
        "digital personal data protection act", "dpdp act", "dpdp",
        "digital personal data protection rules", "act 2023", "act 2025", "rules 2025"
    ],
}

# =============================================================================
# AI LABEL MAPPING - Maps DPDP indicators to AI model labels
# =============================================================================
AI_LABEL_MAPPING = {
    "notice_consent_purpose": ["data collection with consent", "purpose specification"],
    "data_principal_rights": ["user right to access", "user right to correction", "user right to erasure"],
    "grievance_officer_contact": ["grievance officer contact details"],
    "parental_consent_children": ["parental consent for children's data"],
    "consent_manager_mentioned": ["consent manager mentioned"],
    "cross_border_transfer": ["cross-border data transfer"],
    "data_retention_period": ["data retention period"],
    "dpdp_act_reference": ["DPDP Act reference", "data fiduciary mentioned"],
}


def find_grievance_officer_contact_improved(text: str) -> Optional[str]:
    """
    Improved grievance officer detection per Rule 9 and Rule 14(3).
    Search for contact details within 300 characters of "grievance" or 
    "Data Protection Officer" (case-insensitive).
    
    Rule 9 states: prominently publish business contact information of
    Data Protection Officer or person who is able to answer questions.
    
    Rule 14(3) requires: grievance redressal system responding within 90 days.
    
    Args:
        text: Policy text to search.
    
    Returns:
        str or None: Contact detail if found, else None.
    """
    # Keywords from Rule 9 and Rule 14(3)
    search_terms = [
        r'grievance',
        r'data\s+protection\s+officer',
        r'person\s+who\s+is\s+able\s+to\s+answer',
        r'grievance\s+redressal'
    ]
    
    for term in search_terms:
        pattern = re.compile(term, re.IGNORECASE)
        
        for match in pattern.finditer(text):
            # Extract 300 characters around the match (150 before, 150 after)
            start = max(0, match.start() - 150)
            end = min(len(text), match.end() + 150)
            snippet = text[start:end]
            
            # Look for email
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            email_match = re.search(email_pattern, snippet)
            if email_match:
                logger.info(f"Grievance/DPO contact email found: {email_match.group(0)}")
                return email_match.group(0)
            
            # Look for phone number (Indian and international formats)
            phone_pattern = r'\+?\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}'
            phone_match = re.search(phone_pattern, snippet)
            if phone_match:
                logger.info(f"Grievance/DPO contact phone found: {phone_match.group(0)}")
                return phone_match.group(0)
    
    return None


# Retention gate: time period must appear near retain/retention/erased (Rule 8 / Third Schedule)
_RETENTION_ANCHORS = ("retain", "retention", "erased", "erase")
_TIME_PERIOD_PATTERN = re.compile(
    r"(\d+\s*(?:year|years|month|months|day|days|week|weeks|hour|hours)"
    r"|one\s+year|three\s+years|six\s+months|twelve\s+months|ninety\s+days|90\s+days"
    r"|\b(?:year|years|month|months|day|days|weeks)\b)",
    re.IGNORECASE,
)


def _passes_rule3_notice_gate(text_lower: str) -> bool:
    """
    Rule 3 (Notice): require mandatory 'consent' plus at least TWO of:
    itemised description, specified purpose, withdraw (with consent), data principal.
    """
    if "consent" not in text_lower:
        return False

    conditions_met = 0
    if "itemised description" in text_lower:
        conditions_met += 1
    if "specified purpose" in text_lower:
        conditions_met += 1
    # 'withdraw' counts only when consent is also present (already enforced above)
    if "withdraw" in text_lower:
        conditions_met += 1
    if "data principal" in text_lower:
        conditions_met += 1

    return conditions_met >= 2


def _passes_rule14_rights_gate(text_lower: str) -> bool:
    """
    Rule 14 (Rights): require at least TWO exact statutory phrases.
    """
    rule14_phrases = [
        "right to access",
        "right to correction",
        "right to erasure",
        "grievance redressal",
        "nominate",
    ]
    matches = sum(1 for phrase in rule14_phrases if phrase in text_lower)
    return matches >= 2


def _passes_retention_period_gate(text_lower: str) -> bool:
    """
    Rule 8 / Third Schedule: retention claims must cite a specific time frame
    near retain/retention/erased language.
    """
    for anchor in _RETENTION_ANCHORS:
        start = 0
        while True:
            pos = text_lower.find(anchor, start)
            if pos == -1:
                break
            window_start = max(0, pos - 100)
            window_end = min(len(text_lower), pos + len(anchor) + 100)
            window = text_lower[window_start:window_end]
            if _TIME_PERIOD_PATTERN.search(window):
                return True
            start = pos + 1
    return False


def _reject_ai_labels(
    filtered_scores: Dict[str, float],
    labels: List[str],
    reason: str,
    status_callback=None,
) -> None:
    """Zero out AI label scores and log rejection."""
    for label in labels:
        if label in filtered_scores and filtered_scores[label] > 0:
            original_score = filtered_scores[label]
            filtered_scores[label] = 0.0
            logger.warning(f"{reason} (confidence {original_score:.2f})")
    if status_callback:
        status_callback(reason)


def apply_keyword_gates(
    ai_scores: Dict[str, float], 
    policy_text: str, 
    status_callback=None
) -> Dict[str, float]:
    """
    Apply keyword gates to prevent AI hallucinations.
    Based on exact legal language from DPDP Rules 2025.

    Rule 3, Rule 14, and retention use strict multi-phrase validation.
    Other indicators require at least one statutory phrase in the policy text.

    Args:
        ai_scores: Dictionary of AI confidence scores.
        policy_text: Full policy text to search for keywords.
        status_callback: Optional callback for status updates.

    Returns:
        dict: Filtered AI scores with hallucinations removed.
    """
    text_lower = policy_text.lower()
    filtered_scores = ai_scores.copy()

    # -------------------------------------------------------------------------
    # STRICT GATE: Rule 3 — Notice & Consent / Purpose
    # Maps to AI labels: data collection with consent, purpose specification
    # -------------------------------------------------------------------------
    notice_labels = ["data collection with consent", "purpose specification"]
    notice_detected = any(filtered_scores.get(l, 0) > 0 for l in notice_labels)
    if notice_detected and not _passes_rule3_notice_gate(text_lower):
        _reject_ai_labels(
            filtered_scores,
            notice_labels,
            "⚠️ Rejected AI hallucination: Notice & Consent (insufficient Rule 3 language)",
            status_callback,
        )

    # -------------------------------------------------------------------------
    # STRICT GATE: Rule 14 — Data Principal Rights
    # Maps to AI labels: user right to access/correction/erasure
    # -------------------------------------------------------------------------
    rights_labels = [
        "user right to access",
        "user right to correction",
        "user right to erasure",
    ]
    rights_detected = any(filtered_scores.get(l, 0) > 0 for l in rights_labels)
    if rights_detected and not _passes_rule14_rights_gate(text_lower):
        _reject_ai_labels(
            filtered_scores,
            rights_labels,
            "⚠️ Rejected AI hallucination: Data Principal Rights (insufficient Rule 14 language)",
            status_callback,
        )

    # -------------------------------------------------------------------------
    # STRICT GATE: Rule 8 / Third Schedule — Data Retention Period
    # -------------------------------------------------------------------------
    if (
        filtered_scores.get("data retention period", 0) > 0
        and not _passes_retention_period_gate(text_lower)
    ):
        _reject_ai_labels(
            filtered_scores,
            ["data retention period"],
            "⚠️ Rejected AI hallucination: Data Retention Period (no specific time frame)",
            status_callback,
        )

    # -------------------------------------------------------------------------
    # STANDARD GATES: all other AI-detected indicators (unchanged)
    # -------------------------------------------------------------------------
    gates_to_apply = [
        ("consent manager mentioned", KEYWORD_GATES["consent_manager_mentioned"], "consent manager"),
        ("data fiduciary mentioned", ["fiduciary", "data fiduciary"], "data fiduciary"),
        ("DPDP Act reference", KEYWORD_GATES["dpdp_act_reference"], "DPDP Act reference"),
        ("parental consent for children's data", KEYWORD_GATES["parental_consent_children"], "parental consent"),
        ("cross-border data transfer", KEYWORD_GATES["cross_border_transfer"], "cross-border transfer"),
        ("grievance officer contact details", KEYWORD_GATES["grievance_officer_contact"], "grievance officer"),
    ]

    for ai_label, keywords, display_name in gates_to_apply:
        if ai_label in filtered_scores and filtered_scores[ai_label] > 0:
            keyword_found = any(kw.lower() in text_lower for kw in keywords)

            if not keyword_found:
                original_score = filtered_scores[ai_label]
                filtered_scores[ai_label] = 0.0
                logger.warning(
                    f"AI hallucination rejected: '{display_name}' "
                    f"(confidence {original_score:.2f}) - no statutory keywords found"
                )
                if status_callback:
                    status_callback(f"⚠️ Rejected hallucination: {display_name}")

    return filtered_scores


class ComplianceReport:
    """Data class for compliance scan results based on DPDP Rules 2025."""
    
    def __init__(self):
        self.url: str = ""
        self.timestamp: str = ""
        self.score: int = 0
        self.verdict: str = ""
        self.privacy_policy_found: bool = False
        self.cookie_banner_found: bool = False
        self.grievance_officer_contact: Optional[str] = None
        self.ai_indicators: Dict[str, float] = {}
        self.rule_indicators: List[str] = []
        self.score_breakdown: Dict[str, int] = {}
        self.rule_citations: Dict[str, str] = {}  # New: Rule citations for each indicator
        self.errors: List[str] = []
        self.scraping_method: str = ""
        self.ai_available: bool = True
        self.scanner_version: str = SCANNER_VERSION
        self.rules_version: str = RULES_VERSION
        # LLM-only: average confidence across non-Missing indicators (see compute_confidence_summary)
        self.confidence_label: Optional[str] = None
        self.average_confidence: Optional[float] = None
        
        # Detailed analysis information for debugging
        self.analysis_details: Dict = {
            'policy_text_length': 0,
            'chunks_analyzed': 0,
            'all_ai_scores': {},
            'sample_chunks': [],
            'keyword_matches': {},
            'policy_urls': {},
            'scan_steps': [],
        }
    
    def to_dict(self) -> dict:
        """Convert report to dictionary for JSON serialization."""
        return {
            'url': self.url,
            'timestamp': self.timestamp,
            'score': self.score,
            'verdict': self.verdict,
            'privacy_policy_found': self.privacy_policy_found,
            'cookie_banner_found': self.cookie_banner_found,
            'grievance_officer_contact': self.grievance_officer_contact,
            'ai_indicators': self.ai_indicators,
            'rule_indicators': self.rule_indicators,
            'score_breakdown': self.score_breakdown,
            'rule_citations': self.rule_citations,
            'errors': self.errors,
            'scraping_method': self.scraping_method,
            'ai_available': self.ai_available,
            'scanner_version': self.scanner_version,
            'rules_version': self.rules_version,
            'confidence_label': self.confidence_label,
            'average_confidence': self.average_confidence,
            'analysis_details': self.analysis_details,
        }


def calculate_compliance_score(
    report: ComplianceReport,
    ai_scores: Dict[str, float],
    policy_text: Optional[str],
    ai_available: bool,
) -> None:
    """
    Calculate compliance score based on DPDP Rules 2025.
    All weights and indicators are directly rooted in the legal requirements.
    
    Scoring weights (Total = 100):
    - notice_consent_purpose: 25 pts (Rule 3 - core mandatory)
    - data_principal_rights: 20 pts (Rule 14)
    - grievance_officer_contact: 20 pts (Rule 9 + 14(3))
    - parental_consent_children: 10 pts (Rule 10)
    - consent_manager_mentioned: 5 pts (First Schedule)
    - cross_border_transfer: 5 pts (Rule 15)
    - data_retention_period: 5 pts (Third Schedule)
    - dpdp_act_reference: 5 pts (Act/Rules)
    - privacy_policy_exists: 5 pts (Baseline)
    - cookie_banner: 5 pts (Optional consent mechanism)
    
    Args:
        report: ComplianceReport object to update.
        ai_scores: Dictionary of AI-detected indicators and their confidence scores.
        policy_text: Full policy text for fallback rule checks.
        ai_available: Whether AI model was available for analysis.
    """
    score = 0
    breakdown = {}
    citations = {}
    
    # ==========================================================================
    # BINARY INDICATORS (no AI confidence weighting)
    # ==========================================================================
    
    # Privacy policy exists (5 pts) - General Requirement
    if report.privacy_policy_found:
        points = SCORING_WEIGHTS["privacy_policy_exists"]
        score += points
        breakdown["Privacy Policy Exists"] = points
        citations["Privacy Policy Exists"] = RULE_CITATIONS["privacy_policy_exists"]
        logger.info(f"Privacy policy found: +{points} points")
    
    # Cookie consent banner (5 pts) - Consent Mechanism (Optional)
    if report.cookie_banner_found:
        points = SCORING_WEIGHTS["cookie_banner"]
        score += points
        breakdown["Cookie Consent Banner"] = points
        citations["Cookie Consent Banner"] = RULE_CITATIONS["cookie_banner"]
        logger.info(f"Cookie banner detected: +{points} points")
    
    # ==========================================================================
    # GRIEVANCE OFFICER CONTACT (Rule 9 + Rule 14(3))
    # Award if EITHER AI detects (>0.9 confidence) OR regex finds contact
    # ==========================================================================
    grievance_ai_score = ai_scores.get("grievance officer contact details", 0)
    grievance_detected_by_regex = report.grievance_officer_contact is not None

    if grievance_detected_by_regex or grievance_ai_score > 0.9:
        points = SCORING_WEIGHTS["grievance_officer_contact"]
        score += points
        detection = []
        if grievance_ai_score > 0.9:
            detection.append(f"AI:{grievance_ai_score:.0%}")
        if grievance_detected_by_regex:
            detection.append("regex")
        label = f"✅ Grievance Officer ({', '.join(detection)})"
        breakdown[label] = points
        citations[label] = RULE_CITATIONS["grievance_officer_contact"]
        logger.info(f"Grievance officer contact found: +{points} points")
    elif grievance_ai_score >= 0.6:
        points = _points_from_ai_confidence(
            SCORING_WEIGHTS["grievance_officer_contact"], grievance_ai_score
        )
        if points > 0:
            score += points
            label = f"Grievance Officer Partial (conf: {grievance_ai_score:.0%})"
            breakdown[label] = points
            citations[label] = RULE_CITATIONS["grievance_officer_contact"]
            logger.info(f"Grievance officer partial credit: +{points} points")
    
    # ==========================================================================
    # AI-BASED INDICATORS WITH CONFIDENCE WEIGHTING
    # ==========================================================================
    if ai_available and ai_scores:
        
        # Notice and Consent (Rule 3) - 25 pts
        # Check for data collection with consent + purpose specification
        consent_score = ai_scores.get("data collection with consent", 0)
        purpose_score = ai_scores.get("purpose specification", 0)
        if consent_score >= 0.6 and purpose_score >= 0.6:
            avg_confidence = (consent_score + purpose_score) / 2
            points = _points_from_ai_confidence(
                SCORING_WEIGHTS["notice_consent_purpose"], avg_confidence
            )
            if points > 0:
                score += points
                tier = "Partial" if avg_confidence <= 0.8 else "Found"
                label = f"Notice & Consent {tier} (conf: {avg_confidence:.0%})"
                breakdown[label] = points
                citations[label] = RULE_CITATIONS["notice_consent_purpose"]
                logger.info(f"Notice and consent: +{points} points")
        
        rights_labels = ["user right to access", "user right to correction", "user right to erasure"]
        rights_scores = [ai_scores.get(label, 0) for label in rights_labels]
        max_rights_score = max(rights_scores) if rights_scores else 0
        points = _points_from_ai_confidence(
            SCORING_WEIGHTS["data_principal_rights"], max_rights_score
        )
        if points > 0:
            score += points
            tier = "Partial" if max_rights_score <= 0.8 else "Found"
            label = f"Data Principal Rights {tier} (conf: {max_rights_score:.0%})"
            breakdown[label] = points
            citations[label] = RULE_CITATIONS["data_principal_rights"]
            logger.info(f"Data principal rights: +{points} points")
        
        parental_score = ai_scores.get("parental consent for children's data", 0)
        points = _points_from_ai_confidence(
            SCORING_WEIGHTS["parental_consent_children"], parental_score
        )
        if points > 0:
            score += points
            label = f"Parental Consent (conf: {parental_score:.0%})"
            breakdown[label] = points
            citations[label] = RULE_CITATIONS["parental_consent_children"]
            logger.info(f"Parental consent: +{points} points")
        
        cm_score = ai_scores.get("consent manager mentioned", 0)
        points = _points_from_ai_confidence(
            SCORING_WEIGHTS["consent_manager_mentioned"], cm_score
        )
        if points > 0:
            score += points
            label = f"Consent Manager (conf: {cm_score:.0%})"
            breakdown[label] = points
            citations[label] = RULE_CITATIONS["consent_manager_mentioned"]
            logger.info(f"Consent manager: +{points} points")
        
        xb_score = ai_scores.get("cross-border data transfer", 0)
        points = _points_from_ai_confidence(
            SCORING_WEIGHTS["cross_border_transfer"], xb_score
        )
        if points > 0:
            score += points
            label = f"Cross-Border Transfer (conf: {xb_score:.0%})"
            breakdown[label] = points
            citations[label] = RULE_CITATIONS["cross_border_transfer"]
            logger.info(f"Cross-border transfer: +{points} points")
        
        retention_score = ai_scores.get("data retention period", 0)
        points = _points_from_ai_confidence(
            SCORING_WEIGHTS["data_retention_period"], retention_score
        )
        if points > 0:
            score += points
            label = f"Data Retention Disclosure (conf: {retention_score:.0%})"
            breakdown[label] = points
            citations[label] = RULE_CITATIONS["data_retention_period"]
            logger.info(f"Data retention disclosed: +{points} points")
        
        dpdp_score = ai_scores.get("DPDP Act reference", 0)
        fiduciary_score = ai_scores.get("data fiduciary mentioned", 0)
        combined_dpdp = max(dpdp_score, fiduciary_score)
        points = _points_from_ai_confidence(
            SCORING_WEIGHTS["dpdp_act_reference"], combined_dpdp
        )
        if points > 0:
            score += points
            label = f"DPDP Act/Fiduciary Reference (conf: {combined_dpdp:.0%})"
            breakdown[label] = points
            citations[label] = RULE_CITATIONS["dpdp_act_reference"]
            logger.info(f"DPDP Act reference: +{points} points")
    
    else:
        # =======================================================================
        # FALLBACK: Rule-based keyword scoring (max ~60 points)
        # Used when AI model is unavailable
        # =======================================================================
        logger.warning("AI unavailable. Using rule-based scoring.")
        
        if policy_text:
            text_lower = policy_text.lower()
            
            # Check each indicator using keyword gates
            for indicator, keywords in KEYWORD_GATES.items():
                if any(kw.lower() in text_lower for kw in keywords):
                    # Award reduced points (60% of full weight)
                    points = int(SCORING_WEIGHTS[indicator] * 0.6)
                    score += points
                    label = f"{indicator.replace('_', ' ').title()} (keyword match)"
                    breakdown[label] = points
                    citations[label] = RULE_CITATIONS[indicator]
                    report.rule_indicators.append(indicator)
    
    # Cap score at 100
    score = min(score, 100)
    
    # Determine verdict based on DPDP compliance thresholds
    if score >= 80:
        verdict = "Likely Compliant"
    elif score >= 50:
        verdict = "Partially Compliant"
    else:
        verdict = "Likely Non-Compliant"
    
    report.score = score
    report.verdict = verdict
    report.score_breakdown = breakdown
    report.rule_citations = citations
    report.ai_available = ai_available
    
    logger.info(f"Final score: {score}/100 - Verdict: {verdict}")


def _points_from_ai_confidence(weight: int, confidence: float) -> int:
    """
    Partial credit for keyword-derived confidence scores in legacy reports:
    full weight above 0.8, 70% weight between 0.6–0.8, zero below 0.6.
    """
    if confidence < 0.6:
        return 0
    if confidence > 0.8:
        return int(weight * confidence)
    return int(weight * 0.7 * confidence)


def _indicator_points_from_llm(status: str, confidence: float, weight: int) -> float:
    """
    Map LLM indicator status to weighted points (1 decimal precision).
    Found → weight * confidence/100; Partial → weight * 0.8 * confidence/100; Missing → 0.
    """
    status_norm = status.strip().lower()
    conf_scale = max(0.0, min(100.0, confidence)) / 100.0

    if status_norm == "found":
        return round(weight * conf_scale, 1)
    if status_norm == "partial":
        return round(weight * 0.8 * conf_scale, 1)
    return 0.0


def compute_confidence_summary(llm_result: Dict) -> tuple[Optional[str], Optional[float]]:
    """
    Average LLM confidence (0–100) across indicators with a confidence value
    and status other than Missing.
    """
    indicators = llm_result.get("indicators") or {}
    confidences: list[float] = []

    for entry in indicators.values():
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "")).strip()
        if status.lower() == "missing":
            continue
        raw_conf = entry.get("confidence")
        if raw_conf is None:
            continue
        try:
            confidences.append(max(0.0, min(100.0, float(raw_conf))))
        except (TypeError, ValueError):
            continue

    if not confidences:
        return None, None

    average = sum(confidences) / len(confidences)
    if average >= 80:
        label = "high"
    elif average >= 50:
        label = "medium"
    else:
        label = "low"

    return label, round(average, 1)


def calculate_compliance_score_from_llm(
    report: ComplianceReport,
    llm_result: Dict,
) -> None:
    """
    Apply Claude expert analysis directly — keyword gates not applied to LLM output.
    Score is computed from indicator status/confidence only (LLM overall_score is ignored).
    """
    indicators = llm_result.get("indicators", {})
    score = 0.0
    breakdown = {}
    citations = {}

    # LLM-scored indicators (includes privacy_policy_exists)
    llm_scored_keys = [
        "notice_consent_purpose",
        "data_principal_rights",
        "grievance_officer_contact",
        "parental_consent_children",
        "consent_manager_mentioned",
        "cross_border_transfer",
        "data_retention_period",
        "dpdp_act_reference",
        "privacy_policy_exists",
    ]

    display_names = {
        "notice_consent_purpose": "Notice & Consent",
        "data_principal_rights": "Data Principal Rights",
        "grievance_officer_contact": "Grievance Officer Contact",
        "parental_consent_children": "Parental Consent (Children)",
        "consent_manager_mentioned": "Consent Manager",
        "cross_border_transfer": "Cross-Border Transfer",
        "data_retention_period": "Data Retention Disclosure",
        "dpdp_act_reference": "DPDP Act Reference",
        "privacy_policy_exists": "Privacy Policy Exists",
    }

    for key in llm_scored_keys:
        entry = indicators.get(key, {})
        status = entry.get("status", "Missing")
        confidence = float(entry.get("confidence", 0))
        weight = SCORING_WEIGHTS.get(key, 0)
        points = _indicator_points_from_llm(status, confidence, weight)

        if points > 0:
            score += points
            label = f"{display_names.get(key, key)} ({status}, conf: {confidence:.0f}%)"
            breakdown[label] = points
            citations[label] = RULE_CITATIONS.get(key, "")

    # Cookie banner is not in LLM JSON — award separately if detected during scrape
    if report.cookie_banner_found:
        points = SCORING_WEIGHTS["cookie_banner"]
        score += points
        breakdown["Cookie Consent Banner"] = points
        citations["Cookie Consent Banner"] = RULE_CITATIONS["cookie_banner"]

    # Ignore LLM overall_score — sum indicator points, round to nearest integer, cap at 100
    report.score = min(100, round(score))
    report.score = max(0, report.score)

    if report.score >= 80:
        report.verdict = "Likely Compliant"
    elif report.score >= 50:
        report.verdict = "Partially Compliant"
    else:
        report.verdict = "Likely Non-Compliant"

    report.score_breakdown = breakdown
    report.rule_citations = citations
    report.ai_available = True

    # Overall AI confidence label for UI (badge + manual review upsell)
    label, avg = compute_confidence_summary(llm_result)
    report.confidence_label = label
    report.average_confidence = avg

    logger.info(
        "Claude expert score (computed from indicators): %s/100 - Verdict: %s",
        report.score,
        report.verdict,
    )
    if label is not None:
        logger.info("Assessment confidence: %s (avg %.1f%%)", label, avg)


def run_compliance_check(
    url: str,
    privacy_policy_url: Optional[str],
    policy_text: Optional[str],
    cookie_banner: bool,
    scraping_method: str,
    policy_links: Dict[str, Optional[str]],
    status_callback=None,
    terms_text: Optional[str] = None,
) -> ComplianceReport:
    """
    Run complete compliance check based on DPDP Rules 2025.

    Uses Claude expert analysis when configured; otherwise falls back to
    statutory keyword matching.
    """
    from datetime import datetime
    
    report = ComplianceReport()
    report.url = url
    report.timestamp = datetime.now().isoformat()
    report.privacy_policy_found = privacy_policy_url is not None or bool(
        policy_text and len((policy_text or "").strip()) >= 50
    )
    report.cookie_banner_found = cookie_banner
    report.scraping_method = scraping_method
    report.analysis_details['policy_urls'] = policy_links
    report.analysis_details['scan_steps'].append(
        f"Started DPDP Rules 2025 compliance scan at {datetime.now().strftime('%H:%M:%S')}"
    )
    report.analysis_details['scan_steps'].append(f"Scraping method: {scraping_method}")
    
    ai_available = False
    ai_scores = {}
    
    if policy_text:
        report.analysis_details['policy_text_length'] = len(policy_text)
        report.analysis_details['scan_steps'].append(
            f"Extracted {len(policy_text):,} characters from policy"
        )
        
        # Chunk text for analysis
        from utils import chunk_text
        chunks = chunk_text(policy_text, max_tokens=512, overlap=50)
        report.analysis_details['chunks_analyzed'] = len(chunks)
        report.analysis_details['sample_chunks'] = [chunks[0][:500] if chunks else ""]
        report.analysis_details['scan_steps'].append(
            f"Split into {len(chunks)} chunks for analysis"
        )
        if status_callback:
            status_callback(f"Prepared {len(chunks)} text segments for analysis")
        
        # Search for grievance officer contact (Rule 9 + Rule 14(3))
        if status_callback:
            status_callback("🔍 Searching for Grievance Officer/DPO contact (Rule 9)...")
        grievance_contact = find_grievance_officer_contact_improved(policy_text)
        report.grievance_officer_contact = grievance_contact
        if grievance_contact:
            report.analysis_details['scan_steps'].append(
                f"Found grievance officer contact: {grievance_contact}"
            )
            if status_callback:
                status_callback(f"✅ Found grievance contact: {grievance_contact}")
        
        # Prompt-injection scan (detection only — the text the AI reads is not
        # modified; scraped text is fenced as untrusted inside llm_analyzer).
        injection_hits = detect_injection_phrases(policy_text or "")
        injection_hits += [
            p for p in detect_injection_phrases(terms_text or "")
            if p.lower() not in {h.lower() for h in injection_hits}
        ]
        if injection_hits:
            report.analysis_details['prompt_injection_detected'] = injection_hits
            logger.warning(
                "Suspicious injection-like phrases detected in scraped text: %s",
                "; ".join(injection_hits),
            )
            report.analysis_details['scan_steps'].append(
                f"Security notice: {len(injection_hits)} suspicious instruction-like "
                "phrase(s) detected in scraped text (analysed as data only)"
            )

        # DeepSeek expert analysis (primary engine)
        logger.info("Attempting DeepSeek Expert AI analysis...")
        if status_callback:
            status_callback("Using DeepSeek Expert AI (DPDP Rules context)...")

        llm_result = analyze_with_deepseek_expert(
            policy_text,
            terms_text=terms_text or "",
            cookie_banner_found=cookie_banner,
            url=url,
        )

        if llm_result:
            logger.info("Using DeepSeek Expert AI")
            report.analysis_details['scan_steps'].append(
                "AI Engine: DeepSeek Expert AI (full DPDP Rules context)"
            )
            report.analysis_details['scan_steps'].append(
                f"DeepSeek expert analysis ({llm_result.get('model', 'deepseek-chat')}) complete"
            )
            report.analysis_details['llm_analysis'] = llm_result
            report.analysis_details['gemini_analysis'] = llm_result  # legacy key

            ai_scores = llm_indicators_to_ai_scores(llm_result)
            report.ai_indicators = ai_scores
            report.analysis_details['all_ai_scores'] = ai_scores
            ai_available = True

            found_count = sum(
                1 for v in llm_result.get("indicators", {}).values()
                if str(v.get("status", "")).lower() == "found"
            )
            partial_count = sum(
                1 for v in llm_result.get("indicators", {}).values()
                if str(v.get("status", "")).lower() == "partial"
            )
            report.analysis_details['scan_steps'].append(
                f"Claude indicators: {found_count} Found, {partial_count} Partial"
            )
            if status_callback:
                status_callback(
                    f"Claude Expert: {found_count} Found, {partial_count} Partial"
                )

        else:
            if not os.environ.get("DEEPSEEK_API_KEY"):
                report.errors.append(
                    "DEEPSEEK_API_KEY is not configured. Set it in .env for expert AI analysis."
                )
            else:
                last_err = get_last_deepseek_error()
                if last_err:
                    report.errors.append(f"DeepSeek analysis unavailable: {last_err}")
            report.analysis_details['scan_steps'].append(
                "DeepSeek unavailable — using statutory keyword matching"
            )
            if status_callback:
                status_callback("DeepSeek unavailable — using keyword-based analysis")

            text_lower = policy_text.lower()
            found_keywords = {}
            for indicator, keywords in KEYWORD_GATES.items():
                found = [kw for kw in keywords if kw.lower() in text_lower]
                if found:
                    found_keywords[indicator] = found
            report.analysis_details['keyword_matches'] = found_keywords
            ai_available = False
    else:
        logger.warning("No policy text available for analysis.")
        report.errors.append("No policy text could be extracted.")
        report.analysis_details['scan_steps'].append("ERROR: No policy text extracted")
    
    # Calculate DPDP compliance score
    report.analysis_details['scan_steps'].append("Calculating DPDP compliance score...")
    if status_callback:
        status_callback("📊 Calculating DPDP compliance score...")

    llm_analysis = report.analysis_details.get("llm_analysis")
    if llm_analysis:
        calculate_compliance_score_from_llm(report, llm_analysis)
    else:
        calculate_compliance_score(report, ai_scores, policy_text, ai_available)
    
    report.analysis_details['scan_steps'].append(
        f"Final score: {report.score}/100 - {report.verdict}"
    )
    if status_callback:
        status_callback(f"🎯 Final: {report.score}/100 - {report.verdict}")
    
    return report
