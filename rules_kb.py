"""
Knowledge base over the DPDP Rules, 2025 gazette text (dpdp_rules.txt).

The gazette is split into rules and schedules so the pipeline can
  * check the rule numbers an LLM cites against rules that actually exist and
    correct the ones that do not, and
  * keep the hand-condensed checklist in llm_analyzer anchored to the source
    text (tests compare its rule titles and figures with the gazette).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).resolve().parent / "dpdp_rules.txt"

SCHEDULE_ORDINALS = ("FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH")
# The Rules have 23 rules; used when the gazette file cannot be read.
FALLBACK_RULE_NUMBERS = frozenset(str(n) for n in range(1, 24))
_MAX_RULE_SCAN = 30

# Rules that govern each indicator, primary rule first. Mirrors RULE_CITATIONS in
# compliance_checker (a test keeps the two consistent).
INDICATOR_RULES: Dict[str, Tuple[str, ...]] = {
    "notice_consent_purpose": ("3",),
    "data_principal_rights": ("14",),
    "grievance_officer_contact": ("9", "14"),
    "parental_consent_children": ("10",),
    "consent_manager_mentioned": ("4",),
    "cross_border_transfer": ("15",),
    "data_retention_period": ("8",),
    "dpdp_act_reference": (),
    "privacy_policy_exists": (),
}

# Page furniture repeated through the gazette ("... [PART II-SEC. 3(i)]" and its Hindi twin).
_PAGE_HEADER_RE = re.compile(r"3\(i\)\]")
_SCHEDULE_HEADING_RE = re.compile(rf"^({'|'.join(SCHEDULE_ORDINALS)}) SCHEDULE\s*$")
_DASH_RE = re.compile(r"[\u2014\u2013]")


@dataclass(frozen=True)
class RuleSection:
    kind: str  # "rule" | "schedule"
    number: str  # "14" for rules, "THIRD" for schedules
    title: str
    text: str

    @property
    def label(self) -> str:
        return f"Rule {self.number}" if self.kind == "rule" else f"{self.number.title()} Schedule"


def _rule_title(first_line: str, second_line: str) -> str:
    """Title is the heading text before the em dash; some headings wrap onto a second line."""
    heading = re.sub(r"^\d{1,2}\.\s*", "", first_line.strip())
    joined = f"{heading} {second_line.strip()}".strip()
    for candidate in (heading, joined):
        match = _DASH_RE.search(candidate)
        if match:
            return candidate[: match.start()].strip(" .")
    return heading.strip(" .")


def parse_rules(text: str) -> Tuple[Dict[str, RuleSection], Dict[str, RuleSection]]:
    """Split the gazette into ({rule number: section}, {schedule ordinal: section})."""
    lines = [line.rstrip() for line in text.splitlines() if not _PAGE_HEADER_RE.search(line)]

    schedule_starts: List[Tuple[str, int]] = []
    for index, line in enumerate(lines):
        match = _SCHEDULE_HEADING_RE.match(line.strip())
        if match:
            schedule_starts.append((match.group(1), index))
    rules_end = schedule_starts[0][1] if schedule_starts else len(lines)

    # Rule headings are "N. Title.—" (a few have no space after the dot or wrap onto a
    # second line). A missing number is skipped rather than ending the scan.
    rule_starts: List[Tuple[str, int]] = []
    position = 0
    for number in range(1, _MAX_RULE_SCAN + 1):
        heading = re.compile(rf"^{number}\.\s*[A-Z]")
        for index in range(position, rules_end):
            if heading.match(lines[index].strip()):
                rule_starts.append((str(number), index))
                position = index + 1
                break

    rules: Dict[str, RuleSection] = {}
    for n, (number, start) in enumerate(rule_starts):
        end = rule_starts[n + 1][1] if n + 1 < len(rule_starts) else rules_end
        body = lines[start:end]
        second = body[1] if len(body) > 1 else ""
        rules[number] = RuleSection("rule", number, _rule_title(body[0], second), "\n".join(body).strip())

    schedules: Dict[str, RuleSection] = {}
    for n, (ordinal, start) in enumerate(schedule_starts):
        end = schedule_starts[n + 1][1] if n + 1 < len(schedule_starts) else len(lines)
        body = lines[start:end]
        reference = next((ln.strip() for ln in body[1:3] if ln.strip().startswith("[See")), "")
        title = f"{ordinal.title()} Schedule {reference}".strip()
        schedules[ordinal] = RuleSection("schedule", ordinal, title, "\n".join(body).strip())

    return rules, schedules


class RulesKnowledgeBase:
    def __init__(self, text: str):
        self.rules, self.schedules = parse_rules(text)

    def has_rule(self, number: str) -> bool:
        return str(number) in self.rules

    def rule(self, number: str) -> Optional[RuleSection]:
        return self.rules.get(str(number))

    def schedule(self, ordinal: str) -> Optional[RuleSection]:
        return self.schedules.get(ordinal.upper())


@lru_cache(maxsize=1)
def get_rules_kb() -> Optional[RulesKnowledgeBase]:
    """The parsed gazette, or None if the file is missing or yields no rules."""
    try:
        kb = RulesKnowledgeBase(RULES_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("Rules knowledge base unavailable (%s); using the built-in rule range", exc)
        return None
    if not kb.rules:
        logger.warning("No rules could be parsed from %s", RULES_PATH)
        return None
    return kb


def valid_rule_numbers() -> frozenset:
    kb = get_rules_kb()
    return frozenset(kb.rules) if kb else FALLBACK_RULE_NUMBERS


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------

_CITE_HEAD_RE = re.compile(r"\bRules?\s+(?=\d)", re.IGNORECASE)
# One or two digits only, so "Rules 2025" is never read as rule 202.
_CITE_NUMBER_RE = re.compile(r"(\d{1,2})(?!\d)((?:\s*\(\s*[0-9A-Za-z]{1,4}\s*\))*)")
_CITE_SEPARATOR_RE = re.compile(r"\s*(?:,|;|&|\+|/|\band\b|\bor\b)\s*(?=\d)", re.IGNORECASE)


def find_rule_citations(text: str) -> List[Tuple[int, int, str]]:
    """(start, end, rule number) for each rule cited as "Rule 14(3)", "Rules 3 and 14", ..."""
    found: List[Tuple[int, int, str]] = []
    for head in _CITE_HEAD_RE.finditer(text or ""):
        position = head.end()
        while True:
            number = _CITE_NUMBER_RE.match(text, position)
            if not number:
                break
            found.append((number.start(1), number.end(), number.group(1)))
            position = number.end()
            separator = _CITE_SEPARATOR_RE.match(text, position)
            if not separator:
                break
            position = separator.end()
    return found


def fix_rule_citations(text: str, indicator_key: str) -> Tuple[str, List[str]]:
    """
    Replace citations of rules that do not exist with the indicator's primary rule.

    Returns the corrected text and a description of each problem found. When the
    indicator has no governing rule the text is left alone and only reported.
    """
    valid = valid_rule_numbers()
    primary = next(iter(INDICATOR_RULES.get(indicator_key, ())), "")
    issues: List[str] = []
    pieces: List[str] = []
    cursor = 0
    for start, end, number in find_rule_citations(text):
        if number in valid:
            continue
        if primary:
            pieces.append(text[cursor:start])
            pieces.append(primary)
            cursor = end
            issues.append(f"Rule {number} does not exist; replaced with Rule {primary}")
        else:
            issues.append(f"Rule {number} does not exist")
    pieces.append(text[cursor:])
    return "".join(pieces), issues
