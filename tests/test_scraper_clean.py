"""Tests for policy text cleaning in scraper.py."""

from scraper import (
    NAVIGATION_PHRASES,
    POLICY_START_MARKERS,
    clean_extracted_text,
)


def test_trims_content_before_start_marker():
    raw = (
        "Home Privacy Notice Generator Sections DPDP Rules BLOGS "
        "This Privacy Policy explains how we handle your data. "
        "We collect email addresses for support."
    )
    cleaned = clean_extracted_text(raw)
    assert cleaned.lower().startswith("this privacy policy explains")
    assert "privacy notice generator" not in cleaned.lower()


def test_removes_navigation_phrases_on_lines():
    raw = (
        "This Privacy Policy explains our practices.\n"
        "Table of contents\n"
        "We process personal data lawfully.\n"
        "Report error\n"
        "Contact our grievance officer at dpo@example.com."
    )
    cleaned = clean_extracted_text(raw)
    assert "table of contents" not in cleaned.lower()
    assert "report error" not in cleaned.lower()
    assert "grievance officer" in cleaned.lower()


def test_strips_html_comments():
    raw = "This Privacy Policy explains data use. <!-- sidebar nav --> We retain logs."
    cleaned = clean_extracted_text(raw)
    assert "<!--" not in cleaned
    assert "sidebar nav" not in cleaned


def test_keeps_original_when_no_marker():
    raw = "Custom policy header without standard markers. We store account data."
    cleaned = clean_extracted_text(raw)
    assert "custom policy header" in cleaned.lower()


def test_markers_constant_populated():
    assert len(POLICY_START_MARKERS) >= 4
    assert len(NAVIGATION_PHRASES) >= 5


def test_marker_near_the_end_does_not_discard_the_policy():
    """A 'last updated on' footer used to make everything before it vanish."""
    body = " ".join(f"Section {i}. We process personal data for purpose {i}." for i in range(120))
    raw = (
        body
        + " Contact our grievance officer at dpo@example.com. "
        + "This policy was last updated on 12 March 2025."
    )
    cleaned = clean_extracted_text(raw)
    assert cleaned.startswith("Section 0.")
    assert "grievance officer at dpo@example.com" in cleaned
    assert len(cleaned) > 0.9 * len(raw)


def test_menu_chrome_before_the_marker_is_still_trimmed():
    menu = " ".join(["Shop Men Women Kids Offers Stores Help Login Cart"] * 40)
    raw = menu + " This Privacy Policy explains how we use data. We collect your name."
    cleaned = clean_extracted_text(raw)
    assert cleaned.startswith("This Privacy Policy explains")
    assert "Shop Men" not in cleaned


def test_prose_before_a_marker_is_kept():
    intro = "We take privacy seriously. You control your data. Read on to learn how. " * 4
    raw = intro + "Last Updated on 1 January 2025. We collect your email address."
    cleaned = clean_extracted_text(raw)
    assert "You control your data" in cleaned
    assert "We collect your email address" in cleaned


def test_words_that_resemble_navigation_phrases_survive_in_running_text():
    raw = (
        "This Privacy Policy explains your rights. "
        "You may submit a request to our Grievance Officer. "
        "Submitted requests are answered within 90 days. "
        "Please report errors in your data to us."
    )
    cleaned = clean_extracted_text(raw)
    assert "You may submit a request to our Grievance Officer." in cleaned
    assert "Submitted requests are answered within 90 days." in cleaned
    assert "Please report errors in your data to us." in cleaned


def test_long_lines_that_mention_a_navigation_word_are_kept():
    raw = (
        "This Privacy Policy explains our practices.\n"
        "Submit\n"
        "You can submit a complaint to the grievance officer within thirty days of the incident.\n"
        "Table of contents\n"
    )
    cleaned = clean_extracted_text(raw)
    assert "You can submit a complaint to the grievance officer" in cleaned
    assert "Submit" not in cleaned.splitlines()
    assert "table of contents" not in cleaned.lower()


def test_multi_word_site_chrome_is_still_removed_inside_a_line():
    raw = "This Privacy Policy explains data use. Privacy Notice Generator We keep logs for a year."
    cleaned = clean_extracted_text(raw)
    assert "privacy notice generator" not in cleaned.lower()
    assert "We keep logs for a year." in cleaned
