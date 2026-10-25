"""What the JSON API exposes of a stored report."""

from api_handlers import slim_analysis_details, slim_report_for_ui


def stored_details():
    return {
        "chunks_analyzed": 12,
        "scan_steps": ["Split into 12 chunks for analysis"],
        "policy_text_length": 3400,
        "retrieval": {"mode": "full_text", "chunks_indexed": 12},
        "quality_flags": [{"indicator": "data_retention_period", "type": "excerpt_backfilled", "detail": ""}],
        "llm_usage": {"total_tokens": 2000, "latency_ms": 900, "attempts": 1},
        "llm_analysis": {"indicators": {}},
        "stored_policy_text": "full policy",
    }


class TestSlimAnalysisDetails:
    def test_operator_diagnostics_are_not_exposed(self):
        slim = slim_analysis_details(stored_details())
        for key in ("retrieval", "quality_flags", "llm_usage", "llm_analysis", "stored_policy_text"):
            assert key not in slim, key

    def test_what_the_report_page_renders_is_kept(self):
        slim = slim_analysis_details(stored_details())
        assert slim["chunks_analyzed"] == 12
        assert slim["scan_steps"] == ["Split into 12 chunks for analysis"]
        assert slim["policy_text_length"] == 3400

    def test_the_stored_report_is_not_modified(self):
        details = stored_details()
        slim_analysis_details(details)
        assert details == stored_details()

    def test_reports_without_details(self):
        assert slim_analysis_details({}) == {}
        assert slim_analysis_details(None) == {}


def test_slim_report_applies_the_same_rule():
    report = {"url": "https://x.example", "score": 71, "analysis_details": stored_details()}
    slim = slim_report_for_ui(report)
    assert slim["url"] == "https://x.example" and slim["score"] == 71
    assert "llm_usage" not in slim["analysis_details"]
    assert slim["analysis_details"]["chunks_analyzed"] == 12
