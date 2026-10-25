"""Tests for the RAG evaluation harness (rag_eval.py) and its gold fixtures."""

import hashlib
import json
import re
from types import SimpleNamespace

import openai
import pytest

import llm_analyzer
import rag_eval
import retrieval
from cache import clear_scan_cache
from llm_analyzer import INDICATOR_KEYS
from rag_eval import (
    FIXTURE_DIR,
    Case,
    evaluate_live,
    evaluate_retrieval,
    format_live_report,
    format_retrieval_report,
    inspect_text,
    load_cases,
    load_distractors,
    pad_with_distractors,
)
from tests.test_llm_analyzer_rag import USAGE, FakeCompletions
from tests.test_retrieval import HINDI_POLICY


def squash(text):
    return re.sub(r"\s+", " ", text).strip().lower()


@pytest.fixture(scope="module")
def cases():
    return load_cases()


@pytest.fixture(scope="module")
def report_15k(cases):
    return evaluate_retrieval(cases, k=4, pad_chars=15_000)


@pytest.fixture(scope="module")
def report_30k(cases):
    return evaluate_retrieval(cases, k=4, pad_chars=30_000)


class TestFixtures:
    def test_enough_cases(self, cases):
        assert len(cases) >= 8
        assert len({c.id for c in cases}) == len(cases)

    def test_every_case_labels_every_indicator(self, cases):
        for case in cases:
            assert set(case.gold) == set(INDICATOR_KEYS), case.id
            for key, gold in case.gold.items():
                assert gold["status"] in ("Found", "Partial", "Missing"), (case.id, key)

    def test_evidence_is_verbatim_in_the_policy_text(self, cases):
        for case in cases:
            text = squash(case.text)
            for key, gold in case.gold.items():
                evidence = gold.get("evidence", "")
                if gold["status"] == "Missing":
                    assert evidence == "", (case.id, key)
                elif key != "privacy_policy_exists":
                    assert evidence and squash(evidence) in text, (case.id, key)

    def test_the_set_covers_every_status_for_the_retrieval_indicators(self, cases):
        seen = {gold["status"] for case in cases for gold in case.gold.values()}
        assert seen == {"Found", "Partial", "Missing"}
        with_evidence = {
            key for case in cases for key, gold in case.gold.items() if gold.get("evidence") and key != "privacy_policy_exists"
        }
        assert with_evidence == set(retrieval.RETRIEVAL_INDICATORS)

    def test_distractors_keep_the_hard_negatives_that_make_the_benchmark_hard(self):
        text = " ".join(load_distractors()).lower()
        for decoy in (
            "account manager", "parental controls", "outside metro cities", "delete a review",
            "withdrawn only", "transfer your gift card", "minor scratches", "keep records of invoices",
        ):
            assert decoy in text, decoy
        assert len(set(load_distractors())) >= 60

    def test_distractor_order_is_deterministic_and_complete(self):
        lines = [ln.strip() for ln in (FIXTURE_DIR / "distractors.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
        loaded = load_distractors()
        assert sorted(loaded) == sorted(lines)
        assert loaded == tuple(sorted(lines, key=lambda ln: hashlib.sha256(ln.encode()).hexdigest()))


class TestPadding:
    def test_keeps_the_case_text_whole_near_the_middle(self, cases):
        case = cases[0]
        padded = pad_with_distractors(case.text, 20_000)
        body = rag_eval._flatten(case.text)
        position = padded.index(body)
        assert 0.25 < position / len(padded) < 0.75
        assert 20_000 <= len(padded) < 20_600

    def test_is_deterministic(self, cases):
        assert pad_with_distractors(cases[1].text, 12_000) == pad_with_distractors(cases[1].text, 12_000)

    def test_does_not_pad_when_already_long_enough(self, cases):
        assert pad_with_distractors(cases[0].text, 10) == rag_eval._flatten(cases[0].text)


class TestRetrievalBenchmark:
    """Regression guard: the evidence for each gold label must be found among realistic decoys."""

    @pytest.mark.parametrize("fixture", ["report_15k", "report_30k"])
    def test_recall_and_ranking_stay_high(self, request, fixture):
        report = request.getfixturevalue(fixture)
        assert len(report.evidence_rows()) >= 25
        assert report.recall() >= 0.95, [(r.case, r.indicator) for r in report.misses]
        assert report.selection_recall() >= 0.95
        assert report.mrr() >= 0.85

    def test_every_retrieval_indicator_is_exercised(self, report_15k):
        assert {r.indicator for r in report_15k.evidence_rows()} == set(retrieval.RETRIEVAL_INDICATORS)

    def test_shape_features_are_what_keep_paraphrased_rights_findable(self, cases, report_30k, monkeypatch):
        assert report_30k.recall("data_principal_rights") == 1.0

        profile = retrieval.INDICATOR_PROFILES["data_principal_rights"]
        stripped = type(profile)(
            terms=profile.terms, phrases=profile.phrases, generic_phrases=profile.generic_phrases,
            patterns=(), support_weight=profile.support_weight,
        )
        monkeypatch.setitem(retrieval.INDICATOR_PROFILES, "data_principal_rights", stripped)
        without = evaluate_retrieval(cases, k=4, pad_chars=30_000)
        assert without.recall("data_principal_rights") < report_30k.recall("data_principal_rights")

    def test_a_missing_label_with_a_statutory_phrase_present_is_reported(self):
        gold = {key: {"status": "Missing", "evidence": ""} for key in INDICATOR_KEYS}
        case = Case("x", "", "We appoint a Grievance Officer to handle every complaint.", gold)
        report = evaluate_retrieval([case], pad_chars=0)
        assert [(r.case, r.indicator) for r in report.missing_but_strong] == [("x", "grievance_officer_contact")]
        assert "Gold says Missing but a statutory phrase is present" in format_retrieval_report(report)

    def test_unfindable_evidence_is_reported_as_a_miss(self):
        gold = {key: {"status": "Missing", "evidence": ""} for key in INDICATOR_KEYS}
        gold["data_retention_period"] = {"status": "Found", "evidence": "This sentence is not in the policy at all."}
        case = Case("y", "", "We collect your name. We keep records for seven years.", gold)
        report = evaluate_retrieval([case], pad_chars=0)
        assert [(r.case, r.indicator, r.rank, r.selected) for r in report.misses] == [
            ("y", "data_retention_period", None, False)
        ]
        assert report.recall("data_retention_period") == 0.0
        assert "y / data_retention_period: rank=not in top-k, in prompt=False" in format_retrieval_report(report)

    def test_report_layout(self, report_15k):
        text = format_retrieval_report(report_15k)
        assert text.startswith("Retrieval eval: 8 cases, k=4, padded to 15,000 characters")
        assert "OVERALL" in text
        for key in retrieval.RETRIEVAL_INDICATORS:
            assert key in text


class TestInspect:
    def test_short_text_is_sent_whole(self):
        out = inspect_text("We retain personal data for three years. Contact our Grievance Officer.")
        assert "Mode at current settings: full_text" in out
        for key in retrieval.RETRIEVAL_INDICATORS:
            assert f"{key}  [support:" in out
        assert "[support: strong]" in out

    def test_long_text_is_reduced_and_a_tight_budget_shows_what_is_left_out(self, cases, monkeypatch):
        monkeypatch.setenv("RAG_FULL_TEXT_MAX_CHARS", "40000")
        long_text = pad_with_distractors(cases[0].text, 45_000)
        out = inspect_text(long_text)
        assert "Mode at current settings: retrieval" in out
        assert " sent " in out
        assert "left out" not in out  # the default budget fits every indicator's top chunks

        monkeypatch.setattr(llm_analyzer, "rag_evidence_budget_chars", lambda: 4_000)
        assert "left out" in inspect_text(long_text)

    def test_the_default_threshold_is_the_old_hard_cap(self, cases):
        out = inspect_text(pad_with_distractors(cases[0].text, 45_000))
        assert "Mode at current settings: full_text (RAG_FULL_TEXT_MAX_CHARS=100,000)" in out

    def test_non_english_text_is_always_sent_whole(self, monkeypatch):
        monkeypatch.setenv("RAG_FULL_TEXT_MAX_CHARS", "1000")
        out = inspect_text(HINDI_POLICY * 40)
        assert "Mode at current settings: full_text" in out
        assert "Not mostly English" in out
        assert "Not mostly English" not in inspect_text("We retain personal data for three years.")

    def test_nothing_matches(self):
        assert "no chunk matches" in inspect_text("The weather is lovely today.")


def gold_payload(case, status_override=None):
    indicators = {}
    for key in INDICATOR_KEYS:
        gold = case.gold[key]
        status = status_override or gold["status"]
        indicators[key] = {
            "status": status,
            "confidence": 0 if status == "Missing" else 85,
            "excerpt": "" if status == "Missing" else gold.get("evidence", ""),
            "analysis": "Per gold labels.",
            "recommendation": "" if status == "Found" else "Add the missing disclosure.",
        }
    return json.dumps({"indicators": indicators, "overall_score": 70, "verdict": "Partially Compliant"})


@pytest.fixture
def live(monkeypatch):
    clear_scan_cache()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(llm_analyzer, "_json_mode_supported", True)
    monkeypatch.setattr(llm_analyzer.time, "sleep", lambda _s: None)

    def install(*behaviours):
        completions = FakeCompletions(behaviours, USAGE)
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)
        return completions

    yield install
    clear_scan_cache()


class TestLiveEvaluation:
    def test_perfect_answers_score_perfectly(self, cases, live):
        completions = live(*[gold_payload(case) for case in cases])
        report = evaluate_live(cases, max_calls=len(cases))
        assert len(completions.calls) == len(cases)
        assert report.error == ""
        assert report.calls == len(cases)
        assert report.accuracy() == 1.0
        assert report.severe_errors == []
        assert report.tokens == 2000 * len(cases)
        assert len(report.rows) == len(cases) * len(INDICATOR_KEYS)

    def test_wrong_answers_are_counted_and_severe_ones_called_out(self, cases, live):
        live(*[gold_payload(case, status_override="Missing") for case in cases])
        report = evaluate_live(cases, max_calls=len(cases))
        assert report.accuracy() < 0.6
        assert report.severe_errors
        text = format_live_report(report)
        assert "(severe)" in text
        assert "Severe errors (Found vs Missing):" in text
        assert f"Total tokens: {report.tokens:,}" in text
        assert f"API calls: {len(cases)}" in text

    def test_stops_with_a_reason_when_the_analysis_is_unavailable(self, cases, live):
        live("not json at all")
        report = evaluate_live(cases, max_calls=10)
        assert report.rows == []
        assert report.error.startswith(f"{cases[0].id}: ")
        assert report.calls == 3  # the analyzer's three attempts
        assert "Stopped early" in format_live_report(report)

    def test_live_rows_carry_evidence_flags(self, live):
        gold = {key: {"status": "Found", "evidence": ""} for key in INDICATOR_KEYS}
        case = Case("flagged", "", "Short note.", gold)
        live(gold_payload(case))
        report = evaluate_live([case])
        row = next(r for r in report.rows if r.indicator == "data_retention_period")
        assert row.got == "Missing" and row.expected == "Found" and row.severe
        assert row.flags == ["unsupported_status_lowered"]


class TestCallBudget:
    """--live is capped at a few real API requests, whatever the analyzer's own retry logic does."""

    def test_default_is_two_calls(self):
        assert rag_eval.DEFAULT_MAX_CALLS == 2

    def test_stops_before_the_call_that_would_exceed_the_budget(self, cases, live):
        completions = live(*[gold_payload(case) for case in cases])
        report = evaluate_live(cases)
        assert len(completions.calls) == 2
        assert report.calls == 2
        assert [row.case for row in report.rows[:: len(INDICATOR_KEYS)]] == [c.id for c in cases[:2]]
        assert report.error.startswith(f"{cases[2].id}: stopped: the budget of 2 API call(s) is used up")

    def test_retries_are_calls_too(self, cases, live):
        completions = live("not json at all", gold_payload(cases[0]))
        report = evaluate_live(cases)
        assert len(completions.calls) == 2
        assert report.calls == 2
        assert {row.case for row in report.rows} == {cases[0].id}
        assert "budget of 2" in report.error

    def test_the_retry_loop_cannot_swallow_the_stop(self, cases, live):
        completions = live("not json at all")
        report = evaluate_live(cases, max_calls=1)
        assert len(completions.calls) == 1
        assert report.rows == []
        assert "budget of 1" in report.error
        assert "Unparseable LLM JSON" in report.error  # the underlying reason is kept

    def test_cached_analyses_cost_nothing(self, cases, live):
        completions = live(gold_payload(cases[0]))
        assert evaluate_live([cases[0]], max_calls=1).calls == 1
        again = evaluate_live([cases[0]], max_calls=1)
        assert again.calls == 0 and again.error == ""
        assert len(completions.calls) == 1

    def test_the_guard_is_always_removed(self, cases, live):
        original = llm_analyzer._create_completion
        live("not json at all")
        evaluate_live(cases, max_calls=1)
        assert llm_analyzer._create_completion is original

        live(gold_payload(cases[0]))
        evaluate_live([cases[0]], max_calls=1)
        assert llm_analyzer._create_completion is original


class TestCommandLine:
    @pytest.fixture(autouse=True)
    def _no_dotenv(self, monkeypatch):
        # A real .env must not leak a key into these tests.
        monkeypatch.setattr(rag_eval, "load_dotenv", lambda *a, **k: None)

    def test_default_run(self, capsys):
        assert rag_eval.main(["--cases", "compliant_enterprise,generic_startup", "--pad", "8000"]) == 0
        out = capsys.readouterr().out
        assert "Retrieval eval: 2 cases" in out and "OVERALL" in out

    def test_min_recall_gate(self, capsys):
        assert rag_eval.main(["--cases", "compliant_enterprise", "--pad", "8000", "--min-recall", "1.01"]) == 1
        assert "FAIL: recall" in capsys.readouterr().out
        assert rag_eval.main(["--cases", "compliant_enterprise", "--pad", "8000", "--min-recall", "0.5"]) == 0

    def test_unknown_case(self, capsys):
        assert rag_eval.main(["--cases", "nope"]) == 2
        assert "No cases to run." in capsys.readouterr().out

    def test_inspect_a_file(self, tmp_path, capsys):
        path = tmp_path / "policy.txt"
        path.write_text("You can ask us to delete your personal data. Our Grievance Officer replies in 90 days.", encoding="utf-8")
        assert rag_eval.main(["--inspect", str(path)]) == 0
        assert "Document:" in capsys.readouterr().out
        assert rag_eval.main(["--inspect", str(tmp_path / "absent.txt")]) == 2

    def test_live_needs_a_key(self, capsys):
        assert rag_eval.main(["--pad", "8000", "--live"]) == 2
        assert "--live needs DEEPSEEK_API_KEY" in capsys.readouterr().out

    def test_live_run_and_json_output(self, cases, live, tmp_path, capsys):
        selected = [c for c in cases if c.id in ("compliant_enterprise", "generic_startup")]
        live(*[gold_payload(case) for case in selected])
        out_file = tmp_path / "results.json"
        code = rag_eval.main(["--cases", "compliant_enterprise,generic_startup", "--pad", "8000", "--live", "--json", str(out_file)])
        assert code == 0
        assert "Live eval (statuses vs gold labels)" in capsys.readouterr().out
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert set(data) == {"retrieval", "live"}
        assert data["live"]["tokens"] == 4000
        assert data["live"]["calls"] == 2
        assert len(data["live"]["rows"]) == 2 * len(INDICATOR_KEYS)

    def test_live_runs_only_as_many_cases_as_the_budget_allows(self, cases, live, capsys):
        completions = live(*[gold_payload(case) for case in cases])
        assert rag_eval.main(["--pad", "8000", "--live"]) == 0
        out = capsys.readouterr().out
        assert len(completions.calls) == 2
        assert "at most 2 real API call(s)" in out
        assert f"{len(cases) - 2} other case(s) not run" in out
        assert "API calls: 2" in out

    def test_max_calls_raises_the_limit(self, cases, live, capsys):
        completions = live(*[gold_payload(case) for case in cases])
        assert rag_eval.main(["--pad", "8000", "--live", "--max-calls", "3"]) == 0
        assert len(completions.calls) == 3
        assert "at most 3 real API call(s)" in capsys.readouterr().out

    def test_a_budget_that_allows_no_call_is_refused(self, live, capsys):
        completions = live("unused")
        assert rag_eval.main(["--pad", "8000", "--live", "--max-calls", "0"]) == 2
        assert "--max-calls must be at least 1" in capsys.readouterr().out
        assert completions.calls == []

    def test_an_unfinished_live_run_fails_the_exit_status(self, live, capsys):
        live("not json at all")
        assert rag_eval.main(["--pad", "8000", "--live", "--max-calls", "1"]) == 1
        assert "Stopped early" in capsys.readouterr().out
