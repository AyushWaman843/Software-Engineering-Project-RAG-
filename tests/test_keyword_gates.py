"""
Golden-file style tests for DPDP keyword gates and scoring anti-hallucination.

Ensures generic privacy policies (e.g. Startup Indian-style) cannot score ~50+
when AI hallucinates DPDP compliance language that is absent from the text.
"""

from compliance_checker import (
    ComplianceReport,
    apply_keyword_gates,
    calculate_compliance_score,
    _passes_rule14_rights_gate,
    _passes_rule3_notice_gate,
    _passes_retention_period_gate,
)

# Generic policy similar to weak Indian startup sites — no DPDP statutory language
STARTUP_INDIAN_STYLE_POLICY = """
Privacy Policy — Startup Indian Pvt Ltd

We collect personal information such as your name, email address, and phone number
when you register on our platform or use our services.

We use cookies and similar technologies to improve your experience on our website.
By continuing to use our site, you agree to our use of cookies.

We may share your information with trusted third-party service providers who assist
us in operating our website and delivering services to you.

We retain your personal data for as long as necessary to fulfil the purposes outlined
in this policy, unless a longer retention period is required by applicable law.

You may contact us at support@startupindian.com if you have questions about this policy.

We may update this Privacy Policy from time to time. Please review this page periodically.
"""

# Simulated AI scores that would inflate score without keyword gates
HALLUCINATED_AI_SCORES = {
    "data collection with consent": 0.95,
    "purpose specification": 0.92,
    "user right to access": 0.88,
    "user right to correction": 0.85,
    "user right to erasure": 0.90,
    "grievance officer contact details": 0.93,
    "parental consent for children's data": 0.80,
    "consent manager mentioned": 0.75,
    "cross-border data transfer": 0.70,
    "data retention period": 0.85,
    "DPDP Act reference": 0.90,
    "data fiduciary mentioned": 0.88,
}


class TestStrictKeywordGates:
    def test_rule3_gate_rejects_generic_consent_only(self):
        text = "we ask for your consent when you sign up. we collect email and name."
        assert _passes_rule3_notice_gate(text.lower()) is False

    def test_rule3_gate_accepts_statutory_language(self):
        text = (
            "consent may be withdrawn at any time. an itemised description of personal "
            "data and the specified purpose for processing are provided to each data principal."
        )
        assert _passes_rule3_notice_gate(text.lower()) is True

    def test_rule14_gate_requires_two_phrases(self):
        text = "you have the right to access your personal data upon request."
        assert _passes_rule14_rights_gate(text.lower()) is False

        text_full = (
            "data principals may exercise the right to access, right to correction, "
            "and right to erasure. grievance redressal is available within ninety days."
        )
        assert _passes_rule14_rights_gate(text_full.lower()) is True

    def test_retention_gate_requires_timeframe_near_retention(self):
        vague = "we retain data as long as necessary for our business purposes."
        assert _passes_retention_period_gate(vague.lower()) is False

        specific = "we retain personal data for 3 years after your last interaction, then erase it."
        assert _passes_retention_period_gate(specific.lower()) is True


class TestAntiHallucinationScoring:
    def test_startup_indian_style_policy_scores_below_30_with_gated_ai(self):
        """Ungated AI would score ~50+; strict gates should keep score low."""
        policy = STARTUP_INDIAN_STYLE_POLICY
        gated = apply_keyword_gates(HALLUCINATED_AI_SCORES.copy(), policy)

        # All hallucinated indicator scores should be zeroed
        assert gated["data collection with consent"] == 0.0
        assert gated["purpose specification"] == 0.0
        assert gated["user right to access"] == 0.0
        assert gated["data retention period"] == 0.0
        assert gated["DPDP Act reference"] == 0.0

        report = ComplianceReport()
        report.privacy_policy_found = True
        report.cookie_banner_found = True

        calculate_compliance_score(
            report,
            gated,
            policy,
            ai_available=True,
        )

        # Privacy policy (5) + cookie banner (5) only — no DPDP statutory matches
        assert report.score <= 25
        assert report.verdict == "Likely Non-Compliant"

    def test_without_gates_hallucinated_ai_would_score_high(self):
        """Control: ungated hallucinated scores produce inflated partial compliance."""
        report = ComplianceReport()
        report.privacy_policy_found = True
        report.cookie_banner_found = True

        calculate_compliance_score(
            report,
            HALLUCINATED_AI_SCORES.copy(),
            STARTUP_INDIAN_STYLE_POLICY,
            ai_available=True,
        )

        assert report.score >= 50
