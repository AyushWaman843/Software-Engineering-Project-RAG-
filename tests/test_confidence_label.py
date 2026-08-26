"""Tests for LLM confidence label computation."""

from compliance_checker import compute_confidence_summary


def test_confidence_high():
    llm = {
        "indicators": {
            "a": {"status": "Found", "confidence": 90},
            "b": {"status": "Partial", "confidence": 85},
            "c": {"status": "Missing", "confidence": 0},
        }
    }
    label, avg = compute_confidence_summary(llm)
    assert label == "high"
    assert avg == 87.5


def test_confidence_medium():
    llm = {
        "indicators": {
            "a": {"status": "Found", "confidence": 60},
            "b": {"status": "Partial", "confidence": 70},
        }
    }
    label, avg = compute_confidence_summary(llm)
    assert label == "medium"
    assert avg == 65.0


def test_confidence_low():
    llm = {
        "indicators": {
            "a": {"status": "Partial", "confidence": 40},
            "b": {"status": "Found", "confidence": 30},
        }
    }
    label, avg = compute_confidence_summary(llm)
    assert label == "low"
    assert avg == 35.0


def test_confidence_skips_missing_and_null():
    llm = {
        "indicators": {
            "a": {"status": "Missing", "confidence": 100},
            "b": {"status": "Found", "confidence": None},
        }
    }
    label, avg = compute_confidence_summary(llm)
    assert label is None
    assert avg is None
