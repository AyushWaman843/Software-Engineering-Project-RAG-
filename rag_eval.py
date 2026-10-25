"""
Measure and inspect the RAG pipeline.

    python rag_eval.py                        retrieval recall over the gold fixtures (no API calls)
    python rag_eval.py --live                 also run the LLM on the first 2 fixtures and compare statuses
                                              with the gold labels (at most --max-calls real API calls)
    python rag_eval.py --inspect policy.txt   show what the pipeline would send for any policy text

Fixtures live in tests/fixtures/rag_eval: cases.json plus one .txt per policy, and
distractors.txt (unrelated policy paragraphs, several of them deliberate near-misses for an
indicator, used to bury the gold evidence). They are synthetic and the labels are not legal
advice: add real policies there to measure the pipeline on real wording.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from dotenv import load_dotenv

from retrieval import RETRIEVAL_INDICATORS, EvidenceRetriever, select_evidence, split_documents

FIXTURE_DIR = Path(__file__).resolve().parent / "tests" / "fixtures" / "rag_eval"
DISTRACTORS_FILE = FIXTURE_DIR / "distractors.txt"
DEFAULT_K = 4
DEFAULT_PAD_CHARS = 15_000
# Real API requests a --live run may make. Each case needs at least one, so this also caps the cases run.
DEFAULT_MAX_CALLS = 2


def _flatten(text: str) -> str:
    """Single-line text, the shape the scraper produces."""
    return re.sub(r"\s+", " ", text).strip()


def _squash(text: str) -> str:
    return _flatten(text).lower()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Case:
    id: str
    description: str
    text: str
    gold: Mapping[str, Mapping[str, str]]


def load_cases(directory: Path = FIXTURE_DIR) -> List[Case]:
    """Cases from cases.json; each entry names its policy text file and gold labels."""
    entries = json.loads((directory / "cases.json").read_text(encoding="utf-8"))
    return [
        Case(
            id=entry["id"],
            description=entry.get("description", ""),
            text=(directory / entry["file"]).read_text(encoding="utf-8"),
            gold=entry["gold"],
        )
        for entry in entries
    ]


@lru_cache(maxsize=None)
def load_distractors(path: Path = DISTRACTORS_FILE) -> Tuple[str, ...]:
    """
    The distractor paragraphs in a fixed, scattered order.

    Ordered by content hash so that look-alikes for one indicator, which sit together in the
    file, do not end up in the same chunk (in a real policy they would be far apart).
    """
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return tuple(sorted(lines, key=lambda line: hashlib.sha256(line.encode("utf-8")).hexdigest()))


def pad_with_distractors(text: str, target_chars: int) -> str:
    """
    Surround ``text`` with distractor paragraphs up to about ``target_chars``.

    Deterministic. The case text stays in one piece near the middle, so its evidence
    has to be found among unrelated passages, as in a long real policy.
    """
    body = _flatten(text)
    if target_chars <= len(body):
        return body
    distractors = load_distractors()
    paragraphs: List[str] = []
    size = 0
    index = 0
    while size < target_chars - len(body):
        cycle, position = divmod(index, len(distractors))
        paragraph = f"{cycle + 1}.{position + 1} {distractors[position]}"
        paragraphs.append(paragraph)
        size += len(paragraph) + 1
        index += 1
    half = len(paragraphs) // 2
    return " ".join(paragraphs[:half] + [body] + paragraphs[half:])


# ---------------------------------------------------------------------------
# Retrieval evaluation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetrievalRow:
    case: str
    indicator: str
    status: str  # gold status
    rank: Optional[int]  # 1-based rank of the first top-k chunk holding the evidence; None = missed
    selected: Optional[bool]  # evidence survives evidence selection (what the model would see)
    support: str  # strong | weak | none


@dataclass
class RetrievalReport:
    k: int
    pad_chars: int
    cases: int
    rows: List[RetrievalRow]

    def evidence_rows(self, indicator: Optional[str] = None) -> List[RetrievalRow]:
        return [
            r for r in self.rows
            if r.selected is not None and (indicator is None or r.indicator == indicator)
        ]

    @staticmethod
    def _mean(values: Sequence[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def recall(self, indicator: Optional[str] = None) -> float:
        return self._mean([1.0 if r.rank else 0.0 for r in self.evidence_rows(indicator)])

    def mrr(self, indicator: Optional[str] = None) -> float:
        return self._mean([1.0 / r.rank if r.rank else 0.0 for r in self.evidence_rows(indicator)])

    def selection_recall(self, indicator: Optional[str] = None) -> float:
        return self._mean([1.0 if r.selected else 0.0 for r in self.evidence_rows(indicator)])

    @property
    def misses(self) -> List[RetrievalRow]:
        return [r for r in self.evidence_rows() if not r.rank or not r.selected]

    @property
    def missing_but_strong(self) -> List[RetrievalRow]:
        """Gold says Missing yet a statutory phrase is present: check the label or the phrase."""
        return [r for r in self.rows if r.status == "Missing" and r.support == "strong"]


def evaluate_retrieval(
    cases: Sequence[Case],
    k: int = DEFAULT_K,
    pad_chars: int = DEFAULT_PAD_CHARS,
) -> RetrievalReport:
    rows: List[RetrievalRow] = []
    for case in cases:
        text = pad_with_distractors(case.text, pad_chars) if pad_chars else _flatten(case.text)
        retriever = EvidenceRetriever(split_documents(text))
        selection = select_evidence(retriever, top_k=k)
        shown = _squash(" ".join(p.text for group in selection.passages.values() for p in group))

        for key in RETRIEVAL_INDICATORS:
            gold = case.gold[key]
            evidence = _squash(gold.get("evidence", ""))
            support = retriever.support(key)
            if gold["status"] == "Missing" or not evidence:
                rows.append(RetrievalRow(case.id, key, gold["status"], None, None, support))
                continue
            hits = retriever.search(key, top_k=k)
            rank = next((i for i, hit in enumerate(hits, 1) if evidence in _squash(hit.chunk.text)), None)
            rows.append(RetrievalRow(case.id, key, gold["status"], rank, evidence in shown, support))
    return RetrievalReport(k=k, pad_chars=pad_chars, cases=len(cases), rows=rows)


def format_retrieval_report(report: RetrievalReport) -> str:
    lines = [
        f"Retrieval eval: {report.cases} cases, k={report.k}, padded to {report.pad_chars:,} characters",
        "",
        f"{'indicator':28s} {'n':>3s} {'recall@k':>9s} {'MRR':>6s} {'in prompt':>10s}",
    ]
    for key in RETRIEVAL_INDICATORS:
        n = len(report.evidence_rows(key))
        if n:
            lines.append(
                f"{key:28s} {n:3d} {report.recall(key):9.2f} {report.mrr(key):6.2f} {report.selection_recall(key):10.2f}"
            )
    lines.append(
        f"{'OVERALL':28s} {len(report.evidence_rows()):3d} {report.recall():9.2f} "
        f"{report.mrr():6.2f} {report.selection_recall():10.2f}"
    )
    if report.misses:
        lines += ["", "Evidence not retrieved or not shown to the model:"]
        lines += [
            f"  {r.case} / {r.indicator}: rank={r.rank or 'not in top-k'}, in prompt={r.selected}"
            for r in report.misses
        ]
    if report.missing_but_strong:
        lines += ["", "Gold says Missing but a statutory phrase is present (check label or phrase):"]
        lines += [f"  {r.case} / {r.indicator}" for r in report.missing_but_strong]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Live evaluation (calls the LLM)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LiveRow:
    case: str
    indicator: str
    expected: str
    got: str
    confidence: float
    flags: List[str]

    @property
    def severe(self) -> bool:
        """Found vs Missing: the errors that move a score most."""
        return {self.expected, self.got} == {"Found", "Missing"}


@dataclass
class LiveReport:
    rows: List[LiveRow]
    tokens: int
    error: str = ""
    calls: int = 0

    def accuracy(self, indicator: Optional[str] = None) -> float:
        rows = [r for r in self.rows if indicator is None or r.indicator == indicator]
        return sum(r.expected == r.got for r in rows) / len(rows) if rows else 0.0

    @property
    def severe_errors(self) -> List[LiveRow]:
        return [r for r in self.rows if r.severe]


class BudgetExhausted(BaseException):
    """
    The live run reached its API-call limit.

    Deliberately not an Exception: the analyzer retries on ``except Exception``, and a retry
    is exactly the spending this must stop.
    """


class CallBudget:
    """Counts requests to the LLM and refuses the first one past the limit."""

    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    def spend(self) -> None:
        if self.used >= self.limit:
            raise BudgetExhausted(f"stopped: the budget of {self.limit} API call(s) is used up")
        self.used += 1


@contextmanager
def limit_api_calls(budget: CallBudget) -> Iterator[None]:
    """Route every completion request the analyzer makes through ``budget``."""
    import llm_analyzer

    original = llm_analyzer._create_completion

    def counted(*args: Any, **kwargs: Any) -> Any:
        budget.spend()
        return original(*args, **kwargs)

    llm_analyzer._create_completion = counted
    try:
        yield
    finally:
        llm_analyzer._create_completion = original


def evaluate_live(
    cases: Sequence[Case],
    pad_chars: int = 0,
    max_calls: int = DEFAULT_MAX_CALLS,
) -> LiveReport:
    """
    Run the real analysis on each case and compare statuses with the gold labels.

    Makes at most ``max_calls`` API requests in total, retries included; a case the budget
    cannot finish is left out of the report.
    """
    from llm_analyzer import INDICATOR_KEYS, analyze_with_deepseek_expert, get_last_deepseek_error

    rows: List[LiveRow] = []
    tokens = 0
    budget = CallBudget(max_calls)
    with limit_api_calls(budget):
        for case in cases:
            text = pad_with_distractors(case.text, pad_chars) if pad_chars else _flatten(case.text)
            try:
                result = analyze_with_deepseek_expert(text, url=case.id)
            except BudgetExhausted as stop:
                last = get_last_deepseek_error()
                reason = f"{stop} (last API error: {last})" if last else str(stop)
                return LiveReport(rows, tokens, error=f"{case.id}: {reason}", calls=budget.used)
            if result is None:
                reason = get_last_deepseek_error() or "analysis unavailable (is DEEPSEEK_API_KEY set?)"
                return LiveReport(rows, tokens, error=f"{case.id}: {reason}", calls=budget.used)
            tokens += (result.get("llm_usage") or {}).get("total_tokens") or 0
            for key in INDICATOR_KEYS:
                entry = result["indicators"][key]
                flags = [f["type"] for f in result.get("quality_flags", []) if f["indicator"] == key]
                rows.append(LiveRow(case.id, key, case.gold[key]["status"], entry["status"], entry["confidence"], flags))
    return LiveReport(rows, tokens, calls=budget.used)


def format_live_report(report: LiveReport) -> str:
    lines = ["Live eval (statuses vs gold labels)", ""]
    if report.error:
        lines += [f"Stopped early: {report.error}", ""]
    if not report.rows:
        return "\n".join(lines)

    lines.append(f"{'indicator':28s} {'n':>3s} {'exact':>6s}")
    for key in dict.fromkeys(r.indicator for r in report.rows):
        n = sum(1 for r in report.rows if r.indicator == key)
        lines.append(f"{key:28s} {n:3d} {report.accuracy(key):6.2f}")
    lines.append(f"{'OVERALL':28s} {len(report.rows):3d} {report.accuracy():6.2f}")

    wrong = [r for r in report.rows if r.expected != r.got]
    if wrong:
        lines += ["", "Differences from gold:"]
        for r in wrong:
            marker = " (severe)" if r.severe else ""
            flags = f" flags={','.join(r.flags)}" if r.flags else ""
            lines.append(f"  {r.case} / {r.indicator}: expected {r.expected}, got {r.got} @ {r.confidence:.0f}{marker}{flags}")
    lines += [
        "",
        f"Severe errors (Found vs Missing): {len(report.severe_errors)}",
        f"API calls: {report.calls}",
        f"Total tokens: {report.tokens:,}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Inspector
# ---------------------------------------------------------------------------

def inspect_text(text: str, k: int = DEFAULT_K, preview_chars: int = 110) -> str:
    """What the retriever finds, and what the model would be shown, for any policy text."""
    from llm_analyzer import rag_evidence_budget_chars, rag_full_text_max_chars

    retriever = EvidenceRetriever(split_documents(text))
    budget = rag_evidence_budget_chars()
    selection = select_evidence(retriever, top_k=k, budget_chars=budget)
    sent = {cid for group in selection.passages.values() for p in group for cid in p.chunk_ids}
    limit = rag_full_text_max_chars()
    too_long = len(text) > limit
    mode = "retrieval" if too_long and retriever.mostly_english else "full_text"

    lines = [
        f"Document: {len(text):,} characters, {len(retriever.chunks)} chunks",
        f"Mode at current settings: {mode} (RAG_FULL_TEXT_MAX_CHARS={limit:,}); in retrieval mode the model "
        f"would see {selection.chunks_selected} of {selection.chunks_total} chunks, "
        f"{selection.chars_selected:,} characters (budget {budget:,})",
    ]
    if not retriever.mostly_english:
        lines.append(
            f"Not mostly English (English share {retriever.english_share:.2f}): the document is always sent whole "
            "and the evidence checks are skipped; the rankings below use English vocabulary and are not meaningful."
        )
    for key in RETRIEVAL_INDICATORS:
        lines += ["", f"{key}  [support: {retriever.support(key)}]"]
        hits = retriever.search(key, top_k=k)
        if not hits:
            lines.append("  no chunk matches")
        for rank, hit in enumerate(hits, 1):
            preview = _flatten(hit.chunk.text)[:preview_chars]
            sent_mark = "sent" if hit.chunk.id in sent else "left out"
            lines.append(f"  #{rank} score {hit.score:5.1f} {sent_mark:8s} @{hit.chunk.start:,}: {preview}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Measure and inspect the RAG pipeline.")
    parser.add_argument("--inspect", metavar="FILE", help="show retrieval for a policy text file and exit")
    parser.add_argument("--live", action="store_true", help="also run the LLM on the fixtures (needs DEEPSEEK_API_KEY; real API calls)")
    parser.add_argument(
        "--max-calls", type=int, default=DEFAULT_MAX_CALLS,
        help=f"most API requests a --live run may make, retries included, which also limits how many cases run (default {DEFAULT_MAX_CALLS})",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="chunks retrieved per indicator (default 4)")
    parser.add_argument("--pad", type=int, default=DEFAULT_PAD_CHARS, help="pad fixtures with distractors up to N characters for the retrieval eval (default 15000, 0 = none)")
    parser.add_argument("--live-pad", type=int, default=0, help="the same for --live (default 0)")
    parser.add_argument("--cases", help="comma-separated case ids to run")
    parser.add_argument("--min-recall", type=float, help="exit 1 if retrieval recall is below this value")
    parser.add_argument("--json", metavar="FILE", help="also write the raw results to a JSON file")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if args.inspect:
        path = Path(args.inspect)
        if not path.is_file():
            print(f"No such file: {path}")
            return 2
        print(inspect_text(path.read_text(encoding="utf-8", errors="replace"), k=args.k))
        return 0

    cases = load_cases()
    if args.cases:
        wanted = {name.strip() for name in args.cases.split(",")}
        cases = [c for c in cases if c.id in wanted]
    if not cases:
        print("No cases to run.")
        return 2

    report = evaluate_retrieval(cases, k=args.k, pad_chars=args.pad)
    print(format_retrieval_report(report))
    raw: Dict[str, Any] = {"retrieval": [asdict(row) for row in report.rows]}
    status = 0
    if args.min_recall is not None and report.recall() < args.min_recall:
        print(f"\nFAIL: recall {report.recall():.2f} is below --min-recall {args.min_recall:.2f}")
        status = 1

    if args.live:
        if not os.environ.get("DEEPSEEK_API_KEY"):
            print("\n--live needs DEEPSEEK_API_KEY (add it to .env)")
            return 2
        if args.max_calls < 1:
            print("\n--max-calls must be at least 1")
            return 2
        live_cases = cases[: args.max_calls]
        skipped = len(cases) - len(live_cases)
        note = f"; {skipped} other case(s) not run (raise --max-calls or choose with --cases)" if skipped else ""
        print(f"\nLive eval: at most {args.max_calls} real API call(s), on {', '.join(c.id for c in live_cases)}{note}")
        live = evaluate_live(live_cases, pad_chars=args.live_pad, max_calls=args.max_calls)
        print("\n" + format_live_report(live))
        raw["live"] = {
            "rows": [asdict(row) for row in live.rows],
            "tokens": live.tokens,
            "calls": live.calls,
            "error": live.error,
        }
        if live.error:
            status = status or 1

    if args.json:
        Path(args.json).write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return status


if __name__ == "__main__":
    sys.exit(main())
