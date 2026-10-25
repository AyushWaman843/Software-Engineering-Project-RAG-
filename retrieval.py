"""
Dependency-free retrieval for the DPDP scan pipeline.

Documents are split into sentence-aligned chunks that keep their source
offsets, indexed with Okapi BM25, and queried once per DPDP indicator with a
hand-built profile (weighted terms + statutory phrase anchors). The nine
indicators are a closed rubric, so the "queries" are fixed: lexical retrieval
with domain vocabulary is cheap, deterministic and needs no embedding service
or model download.

Used for:
  * long documents - send the LLM the passages relevant to each indicator
    instead of silently truncating the text;
  * excerpt verification / repair - locate an LLM quote inside the source text
    (whitespace, quote-style and case tolerant) and recover the verbatim span.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Separator between the privacy policy and extra pages fetched during refinement.
ADDITIONAL_CONTEXT_MARKER = "--- Additional Context from Related Pages ---"

DEFAULT_CHUNK_CHARS = 1000
DEFAULT_OVERLAP_SENTENCES = 1
MAX_OVERLAP_CHARS = 300
# Safety bound on indexing work; retrieval keeps prompt size bounded separately.
MAX_INDEX_CHARS = 600_000

DEFAULT_TOP_K = 4
DEFAULT_EVIDENCE_BUDGET_CHARS = 24_000
DEFAULT_MIN_SCORE = 0.3
PHRASE_BONUS = 5.0
MAX_PHRASE_HITS = 3
# Weighted-term total a sentence needs (absent a phrase anchor) to stand in for a missing excerpt,
# and how many of those terms must be distinctive (weight >= STRONG_TERM_WEIGHT): one generic
# word plus one distinctive word ("principal" + "nominate") is a coincidence, not evidence.
MIN_REPAIR_TERM_WEIGHT = 4.0
STRONG_TERM_WEIGHT = 2.0
MIN_STRONG_TERMS = 2

SOURCE_LABELS = {
    "privacy": "privacy policy",
    "terms": "terms of service",
    "additional": "related page",
}

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_CHAR_MAP: Dict[str, str] = {
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00a0": " ", "\u2009": " ", "\u202f": " ",
    "\u2022": " ", "\u2023": " ", "\u25e6": " ", "\u2043": " ", "\u25aa": " ",
    "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "", "\u00ad": "",
}


def normalize_with_map(text: str) -> Tuple[str, List[int]]:
    """
    Lowercase, unify quotes/dashes/bullets and collapse whitespace.

    Returns the normalised string and, for every character in it, the index of
    the source character it came from - so a match can be mapped back to the
    original text.
    """
    out: List[str] = []
    origin: List[int] = []
    prev_space = True
    for i, raw in enumerate(text):
        for ch in _CHAR_MAP.get(raw, raw).lower():
            if ch.isspace():
                if prev_space:
                    continue
                out.append(" ")
                origin.append(i)
                prev_space = True
            else:
                out.append(ch)
                origin.append(i)
                prev_space = False
    while out and out[-1] == " ":
        out.pop()
        origin.pop()
    return "".join(out), origin


def normalize_text(text: str) -> str:
    return normalize_with_map(text)[0]


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

_STOPWORDS = frozenset(
    """
    a an the of to and or in on for by with at from as is are be was were been it its this that
    these those we you your our us may will can any all not no if such than then also other which
    who whom their they them has have had do does shall should would could into about more most
    some per via within without under over only etc
    """.split()
)

# The indicator profiles are English, so features built on that vocabulary (evidence checks,
# retrieval over long documents) only apply to English text. English prose is roughly 35-45%
# function words (a table-heavy policy can drop to ~25%); Hindi, Romanised Hindi, French and
# Spanish score 10% or less.
MIN_ENGLISH_SHARE = 0.15
# Too few words to tell the language apart, so such text is treated as English.
MIN_TOKENS_FOR_LANGUAGE_CHECK = 30


def english_share(text: str) -> float:
    """Fraction of word tokens that are common English function words (1.0 if too short to tell)."""
    tokens = _TOKEN_RE.findall(text.lower())
    if len(tokens) < MIN_TOKENS_FOR_LANGUAGE_CHECK:
        return 1.0
    return sum(token in _STOPWORDS for token in tokens) / len(tokens)



def _stem(token: str) -> str:
    """Light suffix stripping; applied to both documents and queries so forms align."""
    if len(token) <= 3 or token.isdigit():
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) > 5:
        token = token[:-3]
    elif token.endswith("ed") and len(token) > 4:
        token = token[:-2]
    elif token.endswith("es") and len(token) > 4:
        token = token[:-2]
    elif token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    if token.endswith("e") and len(token) > 3:
        token = token[:-1]
    return token


def tokenize(text: str) -> List[str]:
    return [
        _stem(tok)
        for tok in _TOKEN_RE.findall(text.lower())
        if len(tok) > 1 and tok not in _STOPWORDS
    ]


# ---------------------------------------------------------------------------
# Sentence splitting & chunking
# ---------------------------------------------------------------------------

_SENT_END_RE = re.compile(r"[.!?][\"')\]\u201d\u2019]*(?=\s)|\n")
_SENT_START_CHARS = "\"'([\u201c\u2018\u2022"
_ABBREVIATIONS = frozenset(
    "mr mrs ms dr prof sr jr vs inc ltd pvt co corp no nos sec art cl rs approx etc fig st viz dept govt".split()
)


def _skip_ws(text: str, pos: int) -> int:
    n = len(text)
    while pos < n and text[pos].isspace():
        pos += 1
    return pos


def _is_abbreviation(text: str, dot_index: int) -> bool:
    match = re.search(r"(\S+)$", text[max(0, dot_index - 12):dot_index])
    if not match:
        return False
    word = match.group(1).strip("\"'([").lower()
    if not word:
        return False
    if word in _ABBREVIATIONS or re.fullmatch(r"[a-z](?:\.[a-z])+", word):
        return True
    return len(word) == 1 and word.isalpha()


def sentence_spans(text: str) -> List[Tuple[int, int]]:
    """
    (start, end) spans of sentences in ``text``.

    Works on single-line text (what the scraper produces) as well as text with
    newlines, which always end a sentence.
    """
    spans: List[Tuple[int, int]] = []
    n = len(text)
    start = _skip_ws(text, 0)
    for match in _SENT_END_RE.finditer(text):
        is_newline = text[match.start()] == "\n"
        end = match.start() if is_newline else match.end()
        if not is_newline:
            nxt = _skip_ws(text, match.end())
            if nxt >= n:
                continue
            ch = text[nxt]
            if not (ch.isupper() or ch.isdigit() or ch in _SENT_START_CHARS):
                continue
            if text[match.start()] == "." and _is_abbreviation(text, match.start()):
                continue
        if end > start and text[start:end].strip():
            spans.append((start, end))
        start = _skip_ws(text, match.end())
    if start < n:
        tail_end = n
        while tail_end > start and text[tail_end - 1].isspace():
            tail_end -= 1
        if tail_end > start:
            spans.append((start, tail_end))
    return spans


def _wrap_span(text: str, start: int, end: int, max_chars: int) -> List[Tuple[int, int]]:
    """Split an over-long run (e.g. a nav menu with no punctuation) at whitespace."""
    if end - start <= max_chars:
        return [(start, end)]
    pieces: List[Tuple[int, int]] = []
    pos = start
    while end - pos > max_chars:
        cut = text.rfind(" ", pos, pos + max_chars)
        if cut <= pos:
            cut = pos + max_chars
        pieces.append((pos, cut))
        pos = _skip_ws(text, cut)
    if pos < end:
        pieces.append((pos, end))
    return pieces


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    index: int
    start: int
    end: int
    text: str


def chunk_text_with_offsets(
    text: str,
    source: str = "doc",
    max_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_sentences: int = DEFAULT_OVERLAP_SENTENCES,
) -> List[Chunk]:
    """
    Pack sentences into chunks of roughly ``max_chars``.

    ``chunk.text`` is always the exact slice ``text[chunk.start:chunk.end]`` so
    evidence stays verbatim. Consecutive chunks share up to ``overlap_sentences``
    short sentences so a statement straddling a boundary is not cut in half.
    """
    if not text or not text.strip():
        return []

    spans: List[Tuple[int, int]] = []
    for start, end in sentence_spans(text):
        spans.extend(_wrap_span(text, start, end, max_chars))

    chunks: List[Chunk] = []
    window: List[Tuple[int, int]] = []
    fresh = 0

    def flush() -> None:
        if not fresh:
            return
        start, end = window[0][0], window[-1][1]
        chunks.append(
            Chunk(
                id=f"{source}-{len(chunks)}",
                source=source,
                index=len(chunks),
                start=start,
                end=end,
                text=text[start:end],
            )
        )

    for span in spans:
        if window and span[1] - window[0][0] > max_chars:
            flush()
            carry: List[Tuple[int, int]] = []
            if overlap_sentences > 0:
                carry = [s for s in window[-overlap_sentences:] if s[1] - s[0] <= MAX_OVERLAP_CHARS]
            window = carry
            fresh = 0
        window.append(span)
        fresh += 1
    flush()
    return chunks


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------

class _BM25:
    def __init__(self, docs_tokens: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.tf = [Counter(tokens) for tokens in docs_tokens]
        self.doc_len = [len(tokens) for tokens in docs_tokens]
        n = len(self.tf)
        self.avg_len = (sum(self.doc_len) / n) if n else 0.0
        df: Counter = Counter()
        for counts in self.tf:
            df.update(counts.keys())
        self.idf: Dict[str, float] = {
            term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }
        self.default_idf = math.log(1.0 + (n + 0.5) / 0.5) if n else 0.0

    def score(self, query: Mapping[str, float], doc: int) -> float:
        counts = self.tf[doc]
        length_norm = self.k1 * (
            1.0 - self.b + self.b * (self.doc_len[doc] / self.avg_len if self.avg_len else 1.0)
        )
        total = 0.0
        for term, weight in query.items():
            freq = counts.get(term)
            if freq:
                total += weight * self.idf.get(term, 0.0) * (freq * (self.k1 + 1.0)) / (freq + length_norm)
        return total


# ---------------------------------------------------------------------------
# Indicator query profiles
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"\+\d{1,3}[\s-]?\d[\d\s-]{7,}\d|\b\d{10}\b|\b1800[\s-]?\d{3}[\s-]?\d{3,4}\b")

# Shape features: what a statement of the right / the overseas hosting looks like, which a
# bag of words cannot see. They separate real statements from look-alikes such as "delete a
# review", "update your delivery address" or "hosted by a leading cloud provider".
_RIGHTS_REQUEST_RE = re.compile(
    r"\b(?:ask|request|require|instruct)(?:ing)?\b[^.\n]{0,60}?"
    r"\b(?:show|give|provide|send|access|copy|see|view|delete|erase|remove|correct|fix|update|amend|rectify|port|stop)\b",
    re.IGNORECASE,
)
_RIGHTS_DATA_ACTION_RE = re.compile(
    r"\b(?:access|see|view|obtain|download|correct|fix|update|amend|rectify|delete|erase|remove|restrict|object)\b"
    r"[^.\n]{0,30}?"
    r"\b(?:personal (?:data|information)|data we (?:hold|have)|information we (?:hold|have)|your data|your information)\b",
    re.IGNORECASE,
)
_RIGHTS_NOMINEE_RE = re.compile(
    r"\b(?:nominate|name|appoint|authori[sz]e)\b[^.\n]{0,40}?"
    r"\b(?:someone|another person|a person|an individual|a representative)\b[^.\n]{0,40}?\b(?:act|behalf|represent)",
    re.IGNORECASE,
)
_FOREIGN_PLACE = (
    r"(?:singapore|united states|usa|america|europe|european union|\beu\b|united kingdom|\buk\b|ireland|germany|"
    r"france|netherlands|canada|australia|japan|china|hong kong|uae|dubai|switzerland|israel|other countries|"
    r"abroad|overseas)"
)
_OVERSEAS_INFRA_RE = re.compile(
    r"\b(?:servers?|data ?cent(?:er|re)s?|cloud|hosted|hosting|stored|storage|processed|processing)\b"
    rf"[^.\n]{{0,80}}?{_FOREIGN_PLACE}",
    re.IGNORECASE,
)
_PROCESSED_IN_COUNTRIES_RE = re.compile(
    r"\b(?:processed|processing|stored|hosted)\b[^.\n]{0,40}?\b(?:in|at)\b[^.\n]{0,30}?"
    r"\b(?:these|other|foreign|various|different|multiple)\s+(?:countries|jurisdictions|regions)\b",
    re.IGNORECASE,
)
# Age thresholds for children's data ("under 13", "below the age of 16"). Only plausible
# thresholds (10-19, 21) match, and time/size units are excluded so "under 15 days" is not an age.
_AGE = r"(?:1[0-9]|21)"
_AGE_THRESHOLD_RE = re.compile(
    rf"\b(?:under|below|younger than|less than)\s+(?:the\s+age\s+of\s+)?{_AGE}\b"
    r"(?!\s*(?:days?|hours?|minutes?|weeks?|months?|seconds?|mb|gb|kb|%|percent))",
    re.IGNORECASE,
)
_AGE_YEARS_RE = re.compile(
    rf"\b{_AGE}\s*(?:years?\s+(?:of\s+age|old)|or\s+(?:under|younger|older|over))\b",
    re.IGNORECASE,
)
# A regex bonus at or above this weight is treated like a statutory phrase: it counts as
# strong support and qualifies a sentence to stand in for a missing excerpt.
STRONG_PATTERN_WEIGHT = 3.0


@dataclass(frozen=True)
class QueryProfile:
    """Weighted words (stemmed on build), phrase anchors, and regex bonuses."""

    terms: Mapping[str, float]
    phrases: Tuple[str, ...]
    patterns: Tuple[Tuple["re.Pattern[str]", float], ...] = ()
    # Phrases that help rank a chunk but prove nothing alone ("contact us" is in nearly
    # every policy). They never count as support for an indicator or repair an excerpt.
    generic_phrases: Tuple[str, ...] = ()
    # Lowest single-word weight that counts as vocabulary-level support for the indicator
    # (see EvidenceRetriever.support). Raised where a common word would otherwise
    # make any document look relevant, e.g. "consent" for the Consent Manager indicator.
    support_weight: float = 1.0

    @property
    def stems(self) -> Dict[str, float]:
        stems: Dict[str, float] = {}
        for word, weight in self.terms.items():
            stem = _stem(word.lower())
            stems[stem] = max(weight, stems.get(stem, 0.0))
        return stems

    @property
    def strong_patterns(self) -> Tuple["re.Pattern[str]", ...]:
        return tuple(pattern for pattern, weight in self.patterns if weight >= STRONG_PATTERN_WEIGHT)

    def bonus(self, normalized_text: str, raw_text: str) -> float:
        hits = sum(1 for phrase in (*self.phrases, *self.generic_phrases) if phrase in normalized_text)
        total = PHRASE_BONUS * min(hits, MAX_PHRASE_HITS)
        for pattern, weight in self.patterns:
            if pattern.search(raw_text):
                total += weight
        return total


INDICATOR_PROFILES: Dict[str, QueryProfile] = {
    "notice_consent_purpose": QueryProfile(
        terms={
            "consent": 2.0, "purpose": 2.0, "collect": 1.5, "collection": 1.5, "notice": 1.5,
            "withdraw": 2.0, "withdrawal": 2.0, "personal": 1.0, "information": 0.5, "process": 1.0,
            "share": 0.5, "itemised": 2.0, "itemized": 2.0, "specified": 1.5, "agree": 1.0,
            "permission": 1.0, "lawful": 1.0, "basis": 0.5, "use": 0.5,
        },
        phrases=(
            "withdraw your consent", "withdraw consent", "withdrawal of consent",
            "purposes for which", "specified purpose", "itemised description", "itemized description",
        ),
        generic_phrases=(
            "consent to", "your consent", "purpose of", "purposes of", "we collect",
            "information we collect", "data we collect", "personal data we collect", "how we use",
            "how we collect",
        ),
    ),
    "data_principal_rights": QueryProfile(
        terms={
            "right": 2.0, "access": 1.5, "correct": 2.0, "correction": 2.0, "rectify": 2.0,
            "rectification": 2.0, "erase": 2.0, "erasure": 2.0, "delete": 1.5, "deletion": 1.5,
            "nominate": 2.5, "nominee": 2.5, "withdraw": 1.0, "grievance": 1.0, "redressal": 1.0,
            "principal": 1.5, "update": 1.0, "portability": 1.0, "request": 1.0, "exercise": 1.5,
            "inaccurate": 1.0,
        },
        phrases=(
            "right to access", "right to correction", "right to erasure", "right to correct",
            "right to delete", "right to nominate", "right of access", "your rights",
            "data principal rights", "rights of the data principal", "rights of data principal",
            "exercise your rights", "exercise these rights", "request deletion", "request access",
            "correct or update", "grievance redressal",
        ),
        patterns=(
            (_RIGHTS_REQUEST_RE, 3.0),
            (_RIGHTS_DATA_ACTION_RE, 3.0),
            (_RIGHTS_NOMINEE_RE, 3.0),
        ),
    ),
    "grievance_officer_contact": QueryProfile(
        terms={
            "grievance": 3.0, "officer": 2.0, "dpo": 3.0, "protection": 1.0, "nodal": 2.0,
            "redressal": 2.0, "complaint": 2.0, "contact": 1.5, "email": 1.0, "mail": 0.5,
            "phone": 1.0, "telephone": 1.0, "address": 0.5, "query": 1.0, "concern": 1.0,
            "resolve": 0.5, "escalate": 0.5, "board": 0.5,
        },
        phrases=(
            "grievance officer", "grievance redressal", "data protection officer", "nodal officer",
            "person who is able to answer",
        ),
        generic_phrases=("contact us", "write to us", "email us", "reach out", "90 days", "ninety days"),
        patterns=((_EMAIL_RE, 1.5), (_PHONE_RE, 1.0)),
    ),
    "parental_consent_children": QueryProfile(
        terms={
            "child": 3.0, "children": 3.0, "minor": 2.5, "parent": 2.5, "parental": 2.5,
            "guardian": 2.0, "age": 1.0, "18": 1.5, "eighteen": 1.5, "verifiable": 2.0,
            "coppa": 2.0, "teen": 2.0, "teenager": 2.0, "kid": 2.0, "underage": 2.0,
            "youth": 2.0, "adolescent": 2.0,
        },
        phrases=(
            "verifiable consent", "verifiable parental consent", "parental consent",
            "consent of the parent", "consent of parent", "under the age of 18", "under 18",
            "below the age of 18", "below 18", "age of 18", "children's", "minors",
            "legal guardian", "parent or guardian", "not knowingly collect",
            "not intended for children", "not directed to children",
        ),
        patterns=((_AGE_THRESHOLD_RE, 3.0), (_AGE_YEARS_RE, 3.0)),
        support_weight=2.0,
    ),
    "consent_manager_mentioned": QueryProfile(
        terms={"consent": 1.0, "manager": 3.0},
        phrases=("consent manager", "consent managers", "registered consent manager"),
        support_weight=3.0,
    ),
    "cross_border_transfer": QueryProfile(
        terms={
            "transfer": 2.0, "outside": 1.5, "india": 1.5, "cross": 1.0, "border": 1.5,
            "overseas": 2.0, "international": 1.5, "abroad": 2.0, "foreign": 1.5, "country": 1.0,
            "server": 1.0, "located": 1.0, "jurisdiction": 1.0, "territory": 1.5, "hosted": 1.0,
            "global": 0.5, "cloud": 1.0,
        },
        phrases=(
            "outside india", "outside the territory of india", "outside of india", "cross-border",
            "cross border", "international transfer", "transfer of personal data",
            "servers located", "other countries", "third countries", "overseas",
        ),
        generic_phrases=("transfer your", "transferred to"),
        patterns=((_OVERSEAS_INFRA_RE, 3.0), (_PROCESSED_IN_COUNTRIES_RE, 3.0)),
    ),
    "data_retention_period": QueryProfile(
        terms={
            "retain": 3.0, "retention": 3.0, "erase": 2.0, "erasure": 2.0, "delete": 1.5,
            "deletion": 1.5, "period": 2.0, "year": 1.5, "month": 1.5, "day": 1.0,
            "necessary": 1.0, "duration": 1.5, "store": 1.0, "purge": 1.5, "archive": 1.0,
            "anonymise": 1.0, "anonymize": 1.0, "expire": 1.0, "inactive": 1.0, "inactivity": 1.0,
            "keep": 1.0,
        },
        phrases=(
            "retention period", "data retention", "retain your", "retain personal", "retained for",
            "retained until", "as long as necessary", "as long as needed", "years after",
            "months after", "days after", "erased after",
        ),
        generic_phrases=("for as long as", "period of", "delete your", "erase your", "we will delete", "we keep"),
    ),
    "dpdp_act_reference": QueryProfile(
        terms={
            "dpdp": 4.0, "digital": 2.0, "personal": 0.5, "protection": 1.0, "act": 1.0,
            "rules": 1.0, "fiduciary": 3.0, "principal": 1.5, "compliance": 1.0, "comply": 1.0,
            "legislation": 0.5,
        },
        phrases=(
            "digital personal data protection act", "digital personal data protection rules",
            "dpdp act", "dpdp rules", "dpdp", "data fiduciary", "data principal", "act, 2023",
            "rules, 2025", "act 2023", "rules 2025", "personal data protection",
        ),
        support_weight=3.0,
    ),
    "privacy_policy_exists": QueryProfile(
        terms={"privacy": 2.0, "policy": 2.0, "notice": 1.0, "statement": 0.5},
        phrases=("privacy policy", "privacy notice", "this policy"),
    ),
}

# privacy_policy_exists is decided by the document existing, not by a passage.
RETRIEVAL_INDICATORS: Tuple[str, ...] = tuple(
    key for key in INDICATOR_PROFILES if key != "privacy_policy_exists"
)

_PROFILE_STEMS: Dict[str, Dict[str, float]] = {
    key: profile.stems for key, profile in INDICATOR_PROFILES.items()
}


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float


class EvidenceRetriever:
    """Chunk + index one or more named documents and rank chunks per indicator."""

    def __init__(
        self,
        documents: Mapping[str, str],
        *,
        max_chars: int = DEFAULT_CHUNK_CHARS,
        overlap_sentences: int = DEFAULT_OVERLAP_SENTENCES,
        max_index_chars: int = MAX_INDEX_CHARS,
    ):
        self.documents: Dict[str, str] = {}
        self.truncated = False
        self.chunks: List[Chunk] = []
        for source, text in documents.items():
            if not text or not text.strip():
                continue
            if len(text) > max_index_chars:
                text = text[:max_index_chars]
                self.truncated = True
            self.documents[source] = text
            self.chunks.extend(chunk_text_with_offsets(text, source, max_chars, overlap_sentences))

        self._position = {chunk.id: pos for pos, chunk in enumerate(self.chunks)}
        self._normalized = [normalize_text(chunk.text) for chunk in self.chunks]
        self._index = _BM25([tokenize(chunk.text) for chunk in self.chunks])
        self._vocabulary = set().union(*(counts.keys() for counts in self._index.tf))
        self.english_share = english_share(" ".join(self.documents.values())[:200_000])

    @property
    def mostly_english(self) -> bool:
        return self.english_share >= MIN_ENGLISH_SHARE

    def position(self, chunk: Chunk) -> int:
        return self._position[chunk.id]

    def _score(self, indicator_key: str, pos: int) -> float:
        profile = INDICATOR_PROFILES[indicator_key]
        return self._index.score(_PROFILE_STEMS[indicator_key], pos) + profile.bonus(
            self._normalized[pos], self.chunks[pos].text
        )

    def search(
        self,
        indicator_key: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> List[ScoredChunk]:
        if indicator_key not in INDICATOR_PROFILES or not self.chunks:
            return []
        scored = [(self._score(indicator_key, pos), pos) for pos in range(len(self.chunks))]
        scored = [item for item in scored if item[0] >= min_score]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [ScoredChunk(self.chunks[pos], score) for score, pos in scored[:top_k]]

    def support(self, indicator_key: str) -> str:
        """
        How much of the document backs an indicator, independent of what the LLM claimed.

        "strong": some chunk contains a statutory phrase anchor; "weak": the document
        has vocabulary for the indicator (or an email/phone pattern for contact
        indicators); "none": nothing relevant at all. Based on word presence, not BM25
        scores, which are tiny on short documents.
        """
        profile = INDICATOR_PROFILES.get(indicator_key)
        if profile is None or not self.chunks:
            return "none"
        if any(phrase in normalized for normalized in self._normalized for phrase in profile.phrases):
            return "strong"
        if any(pattern.search(chunk.text) for pattern in profile.strong_patterns for chunk in self.chunks):
            return "strong"
        stems = _PROFILE_STEMS[indicator_key]
        if any(stem in self._vocabulary and weight >= profile.support_weight for stem, weight in stems.items()):
            return "weak"
        if any(pattern.search(chunk.text) for pattern, _ in profile.patterns for chunk in self.chunks):
            return "weak"
        return "none"

    def best_sentence(self, indicator_key: str, max_chars: int = 500) -> str:
        """
        Most indicator-relevant sentence among the top-ranked chunks ('' if none qualifies).

        A sentence qualifies only with a statutory phrase, a shape match, or enough weighted
        vocabulary (>= MIN_REPAIR_TERM_WEIGHT, including MIN_STRONG_TERMS distinctive terms),
        so a weak match such as a lone "consent" is never offered as evidence for another
        indicator.
        """
        profile = INDICATOR_PROFILES.get(indicator_key)
        if profile is None:
            return ""
        stems = _PROFILE_STEMS[indicator_key]
        best_text, best_score = "", 0.0
        for hit in self.search(indicator_key, top_k=3):
            for start, end in sentence_spans(hit.chunk.text):
                sentence = hit.chunk.text[start:end]
                tokens = set(tokenize(sentence))
                matched = [stem for stem in stems if stem in tokens]
                normalized = normalize_text(sentence)
                phrase_hit = any(phrase in normalized for phrase in profile.phrases)
                shape_hit = any(pattern.search(sentence) for pattern in profile.strong_patterns)
                if not (phrase_hit or shape_hit):
                    weights = [stems[s] for s in matched]
                    # "parent" and "parental" are one concept, so distinct terms are counted by word family.
                    families = {s[:5] for s in matched if stems[s] >= STRONG_TERM_WEIGHT}
                    if sum(weights) < MIN_REPAIR_TERM_WEIGHT or len(families) < MIN_STRONG_TERMS:
                        continue
                score = sum(
                    stems[s] * self._index.idf.get(s, self._index.default_idf) for s in matched
                ) + profile.bonus(normalized, sentence)
                if score > best_score:
                    best_text, best_score = sentence, score
        return best_text[:max_chars].strip()

    def stats(self) -> Dict[str, object]:
        return {
            "chunks_indexed": len(self.chunks),
            "documents": {name: len(text) for name, text in self.documents.items()},
            "indexed_chars": sum(len(text) for text in self.documents.values()),
            "truncated": self.truncated,
            "english_share": round(self.english_share, 3),
        }


# ---------------------------------------------------------------------------
# Evidence selection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Passage:
    source: str
    start: int
    end: int
    text: str
    doc_chars: int
    chunk_ids: Tuple[str, ...]


@dataclass
class EvidenceSelection:
    passages: Dict[str, List[Passage]]
    per_indicator: Dict[str, List[str]]
    chunks_total: int
    chunks_selected: int
    chars_selected: int


def _merge_passages(retriever: EvidenceRetriever, positions: Iterable[int]) -> Dict[str, List[Passage]]:
    by_source: Dict[str, List[Chunk]] = {}
    for pos in sorted(positions):
        chunk = retriever.chunks[pos]
        by_source.setdefault(chunk.source, []).append(chunk)

    merged: Dict[str, List[Passage]] = {}
    for source, chunks in by_source.items():
        doc = retriever.documents[source]
        passages: List[Passage] = []
        start, end = chunks[0].start, chunks[0].end
        ids = [chunks[0].id]
        for chunk in chunks[1:]:
            if chunk.start <= end + 2:
                end = max(end, chunk.end)
                ids.append(chunk.id)
                continue
            passages.append(Passage(source, start, end, doc[start:end], len(doc), tuple(ids)))
            start, end, ids = chunk.start, chunk.end, [chunk.id]
        passages.append(Passage(source, start, end, doc[start:end], len(doc), tuple(ids)))
        merged[source] = passages
    return merged


def select_evidence(
    retriever: EvidenceRetriever,
    indicator_keys: Sequence[str] = RETRIEVAL_INDICATORS,
    top_k: int = DEFAULT_TOP_K,
    budget_chars: int = DEFAULT_EVIDENCE_BUDGET_CHARS,
    min_score: float = DEFAULT_MIN_SCORE,
) -> EvidenceSelection:
    """
    Pick the chunks to show the LLM, within ``budget_chars``.

    Each document's first and last chunk go in first (titles, dates, and the
    "contact us" block policies end with). The rest is filled round-robin by
    rank so every indicator gets its best chunk before any gets a second one.
    Chunks scoring below ``min_score`` are never added, so an indicator that is
    genuinely absent does not pull in filler.
    """
    selected: Dict[int, None] = {}
    used = 0
    per_indicator: Dict[str, List[str]] = {key: [] for key in indicator_keys}

    def try_add(pos: int) -> bool:
        nonlocal used
        if pos in selected:
            return True
        size = len(retriever.chunks[pos].text)
        if used + size > budget_chars:
            return False
        selected[pos] = None
        used += size
        return True

    first_by_source: Dict[str, int] = {}
    last_by_source: Dict[str, int] = {}
    for pos, chunk in enumerate(retriever.chunks):
        first_by_source.setdefault(chunk.source, pos)
        last_by_source[chunk.source] = pos
    for pos in list(first_by_source.values()) + list(last_by_source.values()):
        try_add(pos)

    ranked = {key: retriever.search(key, top_k=top_k, min_score=min_score) for key in indicator_keys}
    for rank in range(top_k):
        for key in indicator_keys:
            if rank >= len(ranked[key]):
                continue
            chunk = ranked[key][rank].chunk
            if try_add(retriever.position(chunk)):
                per_indicator[key].append(chunk.id)

    passages = _merge_passages(retriever, selected)
    chars = sum(len(p.text) for group in passages.values() for p in group)
    return EvidenceSelection(
        passages=passages,
        per_indicator=per_indicator,
        chunks_total=len(retriever.chunks),
        chunks_selected=len(selected),
        chars_selected=chars,
    )


def format_passages(passages: Sequence[Passage]) -> str:
    """Render passages with a short locator header each (document order)."""
    blocks = []
    for number, passage in enumerate(passages, start=1):
        label = SOURCE_LABELS.get(passage.source, passage.source)
        header = (
            f"[Passage {number} | {label} | "
            f"characters {passage.start:,}-{passage.end:,} of {passage.doc_chars:,}]"
        )
        blocks.append(f"{header}\n{passage.text}")
    return "\n\n".join(blocks)


def split_documents(policy_text: str, terms_text: str = "") -> Dict[str, str]:
    """Name the documents; pages appended during refinement become their own source."""
    docs: Dict[str, str] = {}
    main, _, extra = (policy_text or "").partition(ADDITIONAL_CONTEXT_MARKER)
    if main.strip():
        docs["privacy"] = main.strip()
    if extra.strip():
        docs["additional"] = extra.strip()
    if terms_text and terms_text.strip():
        docs["terms"] = terms_text.strip()
    return docs


# ---------------------------------------------------------------------------
# Excerpt location
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExcerptMatch:
    start: int
    end: int
    exact: bool
    text: str


_WORD_RE = re.compile(r"\w+", re.UNICODE)
_MIN_BLOCK = 4
_CLOSING_PUNCTUATION = ".!?\"'\u201d\u2019)"


def _coverage(excerpt: str, window: str) -> float:
    """Fraction of ``excerpt`` covered by in-order common blocks of 4+ characters."""
    if not excerpt:
        return 0.0
    matcher = SequenceMatcher(None, excerpt, window, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks() if block.size >= _MIN_BLOCK)
    return matched / len(excerpt)


class TextLocator:
    """Normalise a document once, then locate many excerpts in it."""

    def __init__(self, text: str):
        self.text = text
        self._norm, self._origin = normalize_with_map(text)
        self._sentences: Optional[List[Tuple[int, int]]] = None
        self._sentence_norm: List[str] = []
        self._sentence_tokens: List[set] = []

    @staticmethod
    def _clean_excerpt(excerpt: str) -> str:
        norm = normalize_text(excerpt or "")
        norm = re.sub(r"^(?:\[\.\.\.\]|\.\.\.|\u2026)\s*|\s*(?:\[\.\.\.\]|\.\.\.|\u2026)$", "", norm)
        return norm.strip(" .\"'")

    def _with_closing_punctuation(self, excerpt: str, end: int) -> int:
        """Matching ignores a quote's final period; give it back when the source has it too."""
        tail = excerpt.rstrip()
        closing = tail[len(tail.rstrip(_CLOSING_PUNCTUATION)):]
        if closing and "..." not in closing and "\u2026" not in closing and self.text.startswith(closing, end):
            return end + len(closing)
        return end

    def _ensure_sentences(self) -> None:
        if self._sentences is not None:
            return
        self._sentences = sentence_spans(self.text)
        for start, end in self._sentences:
            norm = normalize_text(self.text[start:end])
            self._sentence_norm.append(norm)
            self._sentence_tokens.append({t for t in _WORD_RE.findall(norm) if len(t) > 1})

    def find(self, excerpt: str, min_coverage: float = 0.8) -> Optional[ExcerptMatch]:
        """
        Locate ``excerpt`` in the document.

        Exact match after normalisation (case, whitespace, quote style, bullets)
        wins; otherwise the best window of up to three sentences is accepted when
        it contains most of the excerpt's words and covers >= ``min_coverage`` of
        its characters. The returned text is always a verbatim slice of the
        original document.
        """
        needle = self._clean_excerpt(excerpt)
        if len(needle) < 4 or not self._norm:
            return None

        pos = self._norm.find(needle)
        if pos != -1:
            start = self._origin[pos]
            end = self._with_closing_punctuation(excerpt, self._origin[pos + len(needle) - 1] + 1)
            return ExcerptMatch(start, end, True, self.text[start:end])
        return self._fuzzy(needle, min_coverage)

    def _fuzzy(self, needle: str, min_coverage: float) -> Optional[ExcerptMatch]:
        needle_tokens = {t for t in _WORD_RE.findall(needle) if len(t) > 1}
        if len(needle_tokens) < 3:
            return None
        self._ensure_sentences()
        assert self._sentences is not None

        windows: List[Tuple[float, int, int, int]] = []
        for first in range(len(self._sentences)):
            union: set = set()
            for last in range(first, min(first + 3, len(self._sentences))):
                union |= self._sentence_tokens[last]
                containment = len(needle_tokens & union) / len(needle_tokens)
                windows.append((containment, last - first, first, last))
        windows.sort(key=lambda w: (-w[0], w[1], w[2]))

        best: Optional[Tuple[float, int, int]] = None
        for containment, _, first, last in windows[:4]:
            if containment < 0.6:
                break
            window = " ".join(self._sentence_norm[first:last + 1])
            coverage = _coverage(needle, window)
            if coverage >= min_coverage and (best is None or coverage > best[0]):
                best = (coverage, first, last)
        if best is None:
            return None

        _, first, last = best
        start, end = self._sentences[first][0], self._sentences[last][1]
        return ExcerptMatch(start, end, False, self.text[start:end])
