"""Tests for file-backed job persistence."""

import json

import job_store
from job_store import load_job, save_job


def test_save_and_load_job(tmp_path, monkeypatch):
    monkeypatch.setattr(job_store, "JOBS_DIR", tmp_path)

    job = {
        "id": "abc123",
        "status": "complete",
        "report_path": "results/abc123.json",
        "report": {"score": 72, "verdict": "Partially Compliant", "extra": "ignored"},
    }
    save_job("abc123", job)

    loaded = load_job("abc123")
    assert loaded is not None
    assert loaded["status"] == "complete"
    assert loaded["report"] == {"score": 72, "verdict": "Partially Compliant"}

    raw = json.loads((tmp_path / "abc123.json").read_text(encoding="utf-8"))
    assert "report" not in raw
    assert raw["report_summary"]["score"] == 72
