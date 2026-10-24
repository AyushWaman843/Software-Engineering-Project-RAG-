import json
import os
from datetime import datetime, timezone

import data_retention


def test_purge_old_temporary_data_preserves_reports(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    uploads = tmp_path / "uploads"
    reports = tmp_path / "results"
    for folder in (jobs, uploads, reports):
        folder.mkdir()
    monkeypatch.setattr(data_retention, "JOBS_DIR", jobs)
    monkeypatch.setattr(data_retention, "UPLOADS_DIR", uploads)
    monkeypatch.setattr("supabase_entitlements._get_client", lambda: None)

    old = datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp()
    job = jobs / "old.json"
    job.write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    upload = uploads / "old-job"
    upload.mkdir()
    (upload / "privacy.pdf").write_bytes(b"legacy")
    report = reports / "paid.json"
    report.write_text("{}", encoding="utf-8")
    os.utime(job, (old, old))
    os.utime(upload, (old, old))

    data_retention.purge_expired_runtime_data(datetime(2026, 10, 22, tzinfo=timezone.utc))

    assert not job.exists()
    assert not upload.exists()
    assert report.exists()
