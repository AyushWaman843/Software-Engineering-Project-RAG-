"""Tests for the DPDP Rules knowledge base and for keeping the checklist anchored to the gazette."""

import re

import pytest

import rules_kb
from rules_kb import (
    FALLBACK_RULE_NUMBERS,
    INDICATOR_RULES,
    SCHEDULE_ORDINALS,
    find_rule_citations,
    fix_rule_citations,
    get_rules_kb,
    parse_rules,
    valid_rule_numbers,
)


@pytest.fixture(scope="module")
def kb():
    knowledge_base = get_rules_kb()
    assert knowledge_base is not None
    return knowledge_base


def squash(text):
    return re.sub(r"\s+", " ", text).lower()


class TestParsingTheGazette:
    def test_finds_all_23_rules(self, kb):
        assert sorted(int(n) for n in kb.rules) == list(range(1, 24))

    @pytest.mark.parametrize(
        "number, expected",
        [
            ("3", "notice given by data fiduciary"),
            ("4", "registration and obligations of consent manager"),
            ("5", "processing of personal data for provision or issue of subsidy"),
            ("8", "time period for specified purpose"),
            ("9", "contact information of person to answer questions"),
            ("10", "verifiable consent for processing of personal data of child"),
            ("14", "rights of data principals"),
            ("15", "transfer of personal data outside the territory of india"),
            ("17", "appointment of chairperson"),
            ("18", "salary, allowances and other terms and conditions of service"),
        ],
    )
    def test_titles(self, kb, number, expected):
        assert expected in kb.rule(number).title.lower()

    def test_each_rule_starts_at_its_own_heading(self, kb):
        for number, section in kb.rules.items():
            assert re.match(rf"^{number}\.\s*[A-Z]", section.text), number

    def test_rule_text_stops_before_the_next_rule(self, kb):
        text = kb.rule("9").text
        assert "business contact information" in text
        assert "10. Verifiable consent" not in text
        assert "8. Time period" not in text

    def test_all_seven_schedules(self, kb):
        assert set(kb.schedules) == set(SCHEDULE_ORDINALS)
        assert "two crore" in squash(kb.schedule("third").text)
        assert "part b" in squash(kb.schedule("FIRST").text)

    def test_page_furniture_is_removed(self, kb):
        for section in [*kb.rules.values(), *kb.schedules.values()]:
            assert "GAZETTE OF INDIA" not in section.text
            assert "3(i)]" not in section.text

    def test_labels(self, kb):
        assert kb.rule("14").label == "Rule 14"
        assert kb.schedule("third").label == "Third Schedule"

    def test_unparseable_text(self):
        assert parse_rules("nothing to see here") == ({}, {})
        assert parse_rules("") == ({}, {})

    def test_a_missing_rule_number_does_not_stop_the_scan(self):
        text = "1. Short title.\u2014 (1) First.\n3. Notice.\u2014 (1) Third.\n4. Consent.\u2014 (1) Fourth."
        rules, _ = parse_rules(text)
        assert set(rules) == {"1", "3", "4"}

    def test_wrapped_and_unspaced_headings(self):
        text = (
            "5. Processing of personal data for\nprovision of subsidy by State. \u2014 (1) Text.\n"
            "17.Appointment of Chairperson. \u2014 (1) Text."
        )
        rules, _ = parse_rules(text)
        assert rules["5"].title == "Processing of personal data for provision of subsidy by State"
        assert rules["17"].title == "Appointment of Chairperson"

    def test_schedule_headings_are_not_confused_with_rule_text(self):
        text = "1. Title.\u2014 (1) Body.\nTHIRD SCHEDULE\n[See rule 8(1)]\n1. Class of fiduciary"
        rules, schedules = parse_rules(text)
        assert set(rules) == {"1"}
        assert "Class of fiduciary" not in rules["1"].text
        assert schedules["THIRD"].title == "Third Schedule [See rule 8(1)]"


class TestLoading:
    def test_falls_back_when_the_file_is_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rules_kb, "RULES_PATH", tmp_path / "absent.txt")
        get_rules_kb.cache_clear()
        try:
            assert get_rules_kb() is None
            assert valid_rule_numbers() == FALLBACK_RULE_NUMBERS
        finally:
            get_rules_kb.cache_clear()

    def test_falls_back_when_nothing_parses(self, monkeypatch, tmp_path):
        empty = tmp_path / "rules.txt"
        empty.write_text("not a gazette", encoding="utf-8")
        monkeypatch.setattr(rules_kb, "RULES_PATH", empty)
        get_rules_kb.cache_clear()
        try:
            assert get_rules_kb() is None
        finally:
            get_rules_kb.cache_clear()

    def test_valid_numbers_come_from_the_gazette(self):
        assert valid_rule_numbers() == frozenset(str(n) for n in range(1, 24))


class TestFindCitations:
    def numbers(self, text):
        return [number for _, _, number in find_rule_citations(text)]

    def test_single_and_sub_rule_citations(self):
        assert self.numbers("Under Rule 14(3) and rule 8.") == ["14", "8"]

    def test_lists(self):
        assert self.numbers("See Rules 3 and 14, and Rules 9, 10 & 15.") == ["3", "14", "9", "10", "15"]

    def test_span_covers_the_number_and_its_sub_clause(self):
        text = "To comply with Rule 14(3): publish."
        start, end, number = find_rule_citations(text)[0]
        assert (text[start:end], number) == ("14(3)", "14")

    def test_the_rules_year_is_not_a_citation(self):
        assert self.numbers("The DPDP Rules 2025 and the Rules, 2025 apply.") == []

    def test_other_text(self):
        assert self.numbers("") == []
        assert self.numbers("No citations here, only rules of thumb.") == []
        assert self.numbers("Rule of law") == []

    def test_lookalike_words(self):
        assert self.numbers("Ruler 5 is not a rule number") == []


class TestFixCitations:
    def test_valid_citations_are_untouched(self):
        text = "Rule 14(3) requires publication; see also Rules 9 and 3."
        assert fix_rule_citations(text, "grievance_officer_contact") == (text, [])

    def test_a_nonexistent_rule_becomes_the_primary_rule(self):
        fixed, issues = fix_rule_citations("To comply with Rule 31(2): publish contacts.", "grievance_officer_contact")
        assert fixed == "To comply with Rule 9: publish contacts."
        assert issues == ["Rule 31 does not exist; replaced with Rule 9"]

    def test_rule_zero_and_large_numbers_are_invalid(self):
        _, issues = fix_rule_citations("Rule 0 and Rule 99.", "data_principal_rights")
        assert len(issues) == 2

    def test_only_the_bad_citation_in_a_list_is_replaced(self):
        fixed, _ = fix_rule_citations("Rules 3 and 77 apply.", "data_principal_rights")
        assert fixed == "Rules 3 and 14 apply."

    def test_indicator_without_a_governing_rule_is_reported_not_rewritten(self):
        text = "Rule 31 applies."
        fixed, issues = fix_rule_citations(text, "dpdp_act_reference")
        assert fixed == text
        assert issues == ["Rule 31 does not exist"]

    def test_empty_text(self):
        assert fix_rule_citations("", "data_principal_rights") == ("", [])


class TestChecklistIsAnchoredToTheGazette:
    """llm_analyzer's condensed checklist is hand-written; these tests catch drift from the source."""

    @pytest.fixture(scope="class")
    def checklist(self):
        from llm_analyzer import CONDENSED_DPDP_RULES

        return CONDENSED_DPDP_RULES

    HEADING_KEYWORDS = {
        "3": "notice",
        "8": "time period",
        "9": "contact",
        "10": "child",
        "14": "rights",
        "15": "outside",
    }

    def test_every_rule_heading_matches_the_gazette_title(self, kb, checklist):
        headings = dict(re.findall(r"^RULE (\d+) \u2014 (.+)$", checklist, flags=re.MULTILINE))
        assert set(headings) == set(self.HEADING_KEYWORDS)
        for number, keyword in self.HEADING_KEYWORDS.items():
            assert keyword in headings[number].lower(), number
            assert keyword in kb.rule(number).title.lower(), number

    def test_grievance_response_period(self, kb, checklist):
        assert "90 days" in checklist
        assert "ninety days" in squash(kb.rule("14").text)

    def test_erasure_notice_period(self, kb, checklist):
        assert "48 hours" in checklist
        assert "forty-eight hours" in squash(kb.rule("8").text)

    def test_third_schedule_thresholds_and_period(self, kb, checklist):
        assert "2 crore" in checklist and "50 lakh" in checklist and "three year" in checklist
        schedule = squash(kb.schedule("THIRD").text)
        assert "two crore" in schedule
        assert "fifty lakh" in schedule
        assert "three years" in schedule
        for entity in ("e-commerce", "online gaming", "social media"):
            assert entity in checklist.lower()
            assert entity in schedule

    def test_consent_manager_section_exists(self, kb, checklist):
        assert "FIRST SCHEDULE PART B" in checklist
        assert "part b" in squash(kb.schedule("FIRST").text)

    def test_indicator_rules_exist_in_the_gazette(self, kb):
        for key, numbers in INDICATOR_RULES.items():
            for number in numbers:
                assert kb.has_rule(number), (key, number)

    def test_indicator_rules_agree_with_the_rule_citations_shown_in_reports(self):
        from compliance_checker import RULE_CITATIONS

        for key, citation in RULE_CITATIONS.items():
            if key == "cookie_banner":
                continue
            cited = {number for _, _, number in find_rule_citations(citation)}
            assert cited <= set(INDICATOR_RULES[key]), (key, citation)
