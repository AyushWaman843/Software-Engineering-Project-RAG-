"""Tests for related-page discovery, confidence refinement, and the refinement flow in scan_runner."""

import json
from types import SimpleNamespace

import openai
import pytest
from bs4 import BeautifulSoup

import confidence_refinement as cr
import llm_analyzer
import scan_runner
from cache import clear_scan_cache
from confidence_refinement import (
    candidate_context_urls,
    fetch_additional_context_pages,
    should_refine_confidence,
)
from retrieval import ADDITIONAL_CONTEXT_MARKER
from tests.test_llm_analyzer_rag import FakeCompletions, SHORT_POLICY, payload
from utils import find_related_links

HOME = "https://example.com/"

HOME_HTML = """
<html><body>
<nav>
  <a href="/products">Products</a>
  <a href="/jobs">Careers: contact our recruiters</a>
</nav>
<footer>
  <a href="/privacy-policy">Privacy Policy</a>
  <a href="/terms">Terms</a>
  <a href="/contact-us">Contact Us</a>
  <a href="/children">Children&#39;s Privacy</a>
  <a href="/your-rights#top">Your Privacy Rights</a>
  <a href="/grievance-redressal">Grievance Redressal</a>
  <a href="https://other.com/grievance">External grievance page</a>
  <a href="https://help.example.com/grievance">Help centre grievance page</a>
  <a href="mailto:dpo@example.com">Email our DPO</a>
  <a href="/files/policy.pdf">Policy PDF (grievance)</a>
  <a href="#top">Back to top</a>
</footer>
</body></html>
"""


def soup_of(html):
    return BeautifulSoup(html, "lxml")


def page(text, length=400):
    return (text + " ") * (length // (len(text) + 1) + 1)


class TestFindRelatedLinks:
    def test_ranks_same_site_pages_by_topic(self):
        links = find_related_links(
            soup_of(HOME_HTML),
            HOME,
            exclude=["https://example.com/privacy-policy", "https://example.com/terms"],
        )
        assert links == [
            "https://example.com/grievance-redressal",
            "https://example.com/your-rights",
            "https://example.com/children",
            "https://example.com/contact-us",
        ]

    def test_ignores_external_hosts_non_html_and_non_page_links(self):
        links = " ".join(find_related_links(soup_of(HOME_HTML), HOME))
        assert "other.com" not in links
        assert "help.example.com" not in links
        assert ".pdf" not in links
        assert "mailto" not in links

    def test_skips_excluded_and_base_pages(self):
        html = '<footer><a href="/">Home contact</a><a href="/grievance">Grievance</a></footer>'
        assert find_related_links(soup_of(html), HOME, exclude=["https://example.com/grievance/"]) == []

    def test_penalises_career_and_login_pages(self):
        html = '<a href="/jobs">Careers: contact our recruiters</a><a href="/login">Login to contact support</a>'
        assert find_related_links(soup_of(html), HOME) == []

    def test_limit_is_respected(self):
        assert len(find_related_links(soup_of(HOME_HTML), HOME, limit=2)) == 2

    def test_www_prefix_does_not_change_the_host(self):
        html = '<a href="https://example.com/grievance">Grievance</a>'
        assert find_related_links(soup_of(html), "https://www.example.com/") == ["https://example.com/grievance"]

    def test_duplicates_keep_the_best_score(self):
        html = '<a href="/page">Contact</a><footer><a href="/page">Grievance officer</a></footer>'
        assert find_related_links(soup_of(html), HOME) == ["https://example.com/page"]

    def test_footer_links_win_ties(self):
        html = '<a href="/contact-a">Contact</a><footer><a href="/contact-b">Contact</a></footer>'
        assert find_related_links(soup_of(html), HOME)[0] == "https://example.com/contact-b"

    def test_no_matches(self):
        assert find_related_links(soup_of('<a href="/shop">Shop</a>'), HOME) == []


GRIEVANCE = page("Our Grievance Officer handles every complaint and replies within ninety days of receiving it.")
RIGHTS = page("You can access, correct and erase your personal data and nominate someone to act for you.")
CHILDREN = page("We obtain verifiable parental consent before processing the personal data of any child.")
CONTACT = page("Write to us at the registered office in Bengaluru or call our support line during business hours.")


@pytest.fixture
def site(monkeypatch):
    """Stub network access; returns the list of URLs fetched."""
    fetched = []
    pages = {}

    def fake_fetch(url, driver=None):
        fetched.append(url)
        return pages.get(url)

    monkeypatch.setattr(cr, "fetch_policy_text", fake_fetch)
    monkeypatch.setattr(cr, "fetch_with_requests", lambda url: (HOME_HTML, soup_of(HOME_HTML)))
    return SimpleNamespace(fetched=fetched, pages=pages)


EXCLUDED = ("https://example.com/privacy-policy", "https://example.com/terms", None)


class TestFetchAdditionalContextPages:
    def test_fetches_topic_pages_in_rank_order_and_stops_at_the_limit(self, site):
        site.pages.update(
            {
                "https://example.com/grievance-redressal": GRIEVANCE,
                "https://example.com/your-rights": RIGHTS,
                "https://example.com/children": CHILDREN,
            }
        )
        result = fetch_additional_context_pages(HOME, max_pages=2, exclude_urls=EXCLUDED)

        assert result.startswith(f"\n\n{ADDITIONAL_CONTEXT_MARKER}\n\n")
        assert "[Source: https://example.com/grievance-redressal]" in result
        assert "[Source: https://example.com/your-rights]" in result
        assert "children" not in result.lower().split("[source:")[-1][:60]
        assert site.fetched == [
            "https://example.com/grievance-redressal",
            "https://example.com/your-rights",
        ]

    def test_pages_analysed_in_the_first_pass_are_never_refetched(self, site):
        site.pages["https://example.com/grievance-redressal"] = GRIEVANCE
        fetch_additional_context_pages(
            HOME,
            max_pages=1,
            exclude_urls=("https://example.com/grievance-redressal",),
        )
        assert "https://example.com/grievance-redressal" not in site.fetched

    def test_skips_error_pages_tiny_pages_and_duplicates(self, site):
        site.pages.update(
            {
                "https://example.com/grievance-redressal": "404 Page Not Found. " + "Sorry about that. " * 20,
                "https://example.com/your-rights": "ok",
                "https://example.com/children": CHILDREN,
                "https://example.com/contact-us": CHILDREN,
                "https://example.com/grievance": GRIEVANCE,
            }
        )
        result = fetch_additional_context_pages(HOME, max_pages=2, exclude_urls=EXCLUDED)
        assert "Page Not Found" not in result
        assert result.count("[Source:") == 2
        assert "[Source: https://example.com/children]" in result
        assert "[Source: https://example.com/grievance]" in result
        assert "[Source: https://example.com/contact-us]" not in result

    def test_falls_back_to_common_paths_when_the_homepage_cannot_be_read(self, site, monkeypatch):
        def boom(url):
            raise RuntimeError("blocked")

        monkeypatch.setattr(cr, "fetch_with_requests", boom)
        site.pages["https://example.com/grievance"] = GRIEVANCE
        result = fetch_additional_context_pages(HOME, max_pages=1)
        assert "[Source: https://example.com/grievance]" in result
        assert site.fetched[0] == "https://example.com/grievance"

    def test_returns_empty_string_when_nothing_qualifies_and_bounds_attempts(self, site):
        assert fetch_additional_context_pages(HOME, max_pages=3, exclude_urls=EXCLUDED) == ""
        assert len(site.fetched) <= 9

    def test_fetch_errors_are_tolerated(self, site, monkeypatch):
        calls = []

        def flaky(url, driver=None):
            calls.append(url)
            if len(calls) == 1:
                raise RuntimeError("timeout")
            return GRIEVANCE if len(calls) == 2 else None

        monkeypatch.setattr(cr, "fetch_policy_text", flaky)
        result = fetch_additional_context_pages(HOME, max_pages=1, exclude_urls=EXCLUDED)
        assert result.count("[Source:") == 1

    def test_candidate_urls_put_topic_links_before_guesses(self, site):
        urls = candidate_context_urls(HOME, exclude_urls=EXCLUDED, limit=9)
        assert urls[:4] == [
            "https://example.com/grievance-redressal",
            "https://example.com/your-rights",
            "https://example.com/children",
            "https://example.com/contact-us",
        ]
        assert "https://example.com/grievance" in urls
        assert len(urls) == len(set(urls))


class TestShouldRefine:
    @staticmethod
    def _result(*pairs):
        return {"indicators": {f"k{i}": {"status": s, "confidence": c} for i, (s, c) in enumerate(pairs)}}

    def test_refines_below_eighty_percent(self):
        should, average = should_refine_confidence(self._result(("Found", 70), ("Partial", 60)), True)
        assert should and average == 65

    def test_does_not_refine_at_or_above_eighty(self):
        assert should_refine_confidence(self._result(("Found", 90), ("Found", 70)), True) == (False, 80.0)

    def test_missing_indicators_are_ignored(self):
        assert should_refine_confidence(self._result(("Found", 90), ("Missing", 0)), True) == (False, 90.0)

    def test_free_scans_never_refine(self):
        assert should_refine_confidence(self._result(("Found", 10)), False) == (False, None)

    def test_no_data(self):
        assert should_refine_confidence(None, True) == (False, None)
        assert should_refine_confidence({"indicators": {}}, True) == (False, None)

    @pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", " 0 "])
    def test_can_be_switched_off(self, monkeypatch, value):
        monkeypatch.setenv("CONFIDENCE_REFINEMENT_ENABLED", value)
        assert should_refine_confidence(self._result(("Found", 10)), True) == (False, None)

    @pytest.mark.parametrize("value", [None, "", "1", "true", "yes"])
    def test_is_on_unless_switched_off(self, monkeypatch, value):
        if value is not None:
            monkeypatch.setenv("CONFIDENCE_REFINEMENT_ENABLED", value)
        assert should_refine_confidence(self._result(("Found", 10)), True) == (True, 10.0)


class TestRefinementPipeline:
    """run_scan_job end to end with the network, disk and LLM stubbed."""

    @pytest.fixture
    def pipeline(self, monkeypatch):
        clear_scan_cache()
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        monkeypatch.setattr(llm_analyzer, "_json_mode_supported", True)
        monkeypatch.setattr(llm_analyzer.time, "sleep", lambda _s: None)

        completions = FakeCompletions(
            [payload("Partial", 40, analysis="First pass."), payload("Found", 95, analysis="Refined pass.")]
        )
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)

        extra_text = "[Source: https://x.example/grievance]\nOur DPO can be emailed at dpo@x.example."
        additional = f"\n\n{ADDITIONAL_CONTEXT_MARKER}\n\n{extra_text}"
        seen = {}

        def fake_additional(url, max_pages=3, driver=None, exclude_urls=()):
            seen["args"] = (url, max_pages, tuple(exclude_urls))
            return additional

        monkeypatch.setattr(cr, "fetch_additional_context_pages", fake_additional)
        monkeypatch.setattr(
            scan_runner,
            "discover_policies",
            lambda *a, **k: {
                "links": {"privacy": "https://x.example/privacy", "terms": None, "cookie": None},
                "cookie_banner": False,
                "method": "requests",
                "driver": None,
                "error": None,
            },
        )
        monkeypatch.setattr(scan_runner, "fetch_policy_text", lambda url, driver=None: SHORT_POLICY)
        monkeypatch.setattr(scan_runner, "get_job", lambda job_id: {"auto_unlock_on_complete": True})
        monkeypatch.setattr(scan_runner, "_append_log", lambda *a, **k: None)
        monkeypatch.setattr(scan_runner, "save_report", lambda report, slug=None: "report.json")
        monkeypatch.setattr(scan_runner, "_finalize_scan_access", lambda *a, **k: None)
        monkeypatch.setattr(scan_runner, "cleanup_driver", lambda driver: None)
        updates = []
        monkeypatch.setattr(scan_runner, "_update_job", lambda job_id, **fields: updates.append(fields))
        yield SimpleNamespace(completions=completions, seen=seen, updates=updates, extra_text=extra_text)
        clear_scan_cache()

    def test_refinement_really_reruns_the_analysis_with_the_extra_pages(self, pipeline):
        scan_runner.run_scan_job("job1", "https://x.example")

        final = pipeline.updates[-1]
        assert final["status"] == "complete"
        assert len(pipeline.completions.calls) == 2
        assert pipeline.extra_text in pipeline.completions.calls[1]["messages"][1]["content"]
        assert pipeline.extra_text not in pipeline.completions.calls[0]["messages"][1]["content"]

        indicators = final["report"]["analysis_details"]["llm_analysis"]["indicators"]
        assert indicators["data_principal_rights"]["status"] == "Found"
        assert indicators["data_principal_rights"]["analysis"].startswith("Refined pass.")

    def test_refinement_excludes_pages_already_analysed(self, pipeline):
        scan_runner.run_scan_job("job1", "https://x.example")
        url, max_pages, excluded = pipeline.seen["args"]
        assert (url, max_pages) == ("https://x.example", 3)
        assert "https://x.example/privacy" in excluded

    def test_persisted_text_is_the_text_that_was_analysed(self, pipeline):
        scan_runner.run_scan_job("job1", "https://x.example")
        stored = pipeline.updates[-1]["report"]["analysis_details"]["stored_policy_text"]
        assert SHORT_POLICY in stored
        assert pipeline.extra_text in stored
        assert ADDITIONAL_CONTEXT_MARKER in stored

    def test_free_scans_are_not_refined(self, pipeline, monkeypatch):
        monkeypatch.setattr(scan_runner, "get_job", lambda job_id: {"auto_unlock_on_complete": False})
        scan_runner.run_scan_job("job1", "https://x.example")
        assert len(pipeline.completions.calls) == 1
        assert "args" not in pipeline.seen
        stored = pipeline.updates[-1]["report"]["analysis_details"]["stored_policy_text"]
        assert ADDITIONAL_CONTEXT_MARKER not in stored

    def test_switching_refinement_off_keeps_a_paid_scan_to_one_llm_call(self, pipeline, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_REFINEMENT_ENABLED", "0")
        scan_runner.run_scan_job("job1", "https://x.example")
        assert pipeline.updates[-1]["status"] == "complete"
        assert len(pipeline.completions.calls) == 1
        assert "args" not in pipeline.seen
        stored = pipeline.updates[-1]["report"]["analysis_details"]["stored_policy_text"]
        assert ADDITIONAL_CONTEXT_MARKER not in stored
