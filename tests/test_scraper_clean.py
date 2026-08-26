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
