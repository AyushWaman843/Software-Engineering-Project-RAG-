"""
DPDP compliance scan orchestration (shared by web UI).
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import validators

from config import MAX_CONCURRENT_SCANS, RESULTS_DIR, SCAN_JOB_TIMEOUT_SECONDS, UPLOADS_DIR
from document_ingest import extract_text_from_pdf, save_pdf_upload
from compliance_checker import ComplianceReport, run_compliance_check
from job_store import count_running_jobs, load_job, mark_stale_running_jobs, save_job
from scraper import cleanup_driver, discover_policies, fetch_policy_text

logger = logging.getLogger(__name__)

# In-memory cache of scan jobs (authoritative copy also on disk)
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()

mark_stale_running_jobs()


def normalize_optional_url(raw_url: str) -> Optional[str]:
    """Return normalized URL if valid, else None."""
    if not raw_url or not raw_url.strip():
        return None
    url = raw_url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url if validators.url(url) else None


def _slugify_reference(reference: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", reference.strip().lower())
    slug = slug.strip("_")
    return slug[:60] or "uploaded_documents"


def normalize_site_url(raw_url: str) -> Optional[str]:
    """Normalize and validate the primary site URL."""
    if not raw_url or not raw_url.strip():
        return None
    url = raw_url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url if validators.url(url) else None


def _persist_extracted_texts(
    report: ComplianceReport,
    policy_text: Optional[str],
    terms_text: str = "",
    cookie_text: str = "",
) -> None:
    """Store extracted document text on the report for PDF regeneration and UI warnings."""
    max_store = 500_000
    report.analysis_details["stored_policy_text"] = (policy_text or "")[:max_store]
    report.analysis_details["stored_terms_text"] = (terms_text or "")[:max_store]
    report.analysis_details["stored_cookie_text"] = (cookie_text or "")[:max_store]
    report.analysis_details["policy_text_extracted"] = bool(
        policy_text and len(policy_text.strip()) >= 50
    )


def save_report(report: ComplianceReport, slug: Optional[str] = None) -> str:
    """Persist scan result as JSON under results/ with an unguessable report id."""
    if slug:
        domain = slug
    else:
        parsed = urlparse(report.url)
        domain = parsed.netloc.replace(".", "_") if parsed.netloc else _slugify_reference(report.url)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Opaque id prevents IDOR via domain+timestamp guessing.
    report_id = secrets.token_urlsafe(18)
    filename = f"{report_id}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RESULTS_DIR / filename

    payload = report.to_dict()
    payload["report_slug"] = f"{domain}_{timestamp}"
    payload["_report_id"] = report_id

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    try:
        from supabase_store import upsert_scan_report

        if upsert_scan_report(report_id, payload):
            logger.info("Report mirrored to Supabase: %s", report_id)
        else:
            logger.warning("Report disk-saved but Supabase mirror failed: %s", report_id)
    except Exception as exc:
        logger.warning("Supabase report mirror skipped for %s: %s", report_id, exc)

    logger.info("Report saved to %s", filepath)
    return str(filepath)


def load_recent_reports(limit: int = 12) -> List[Dict[str, Any]]:
    """Load newest scan reports from results/."""
    reports: List[Dict[str, Any]] = []
    if not RESULTS_DIR.exists():
        return reports

    json_files = sorted(
        RESULTS_DIR.glob("*.json"),
        key=os.path.getmtime,
        reverse=True,
    )

    for filepath in json_files[:limit]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                report = json.load(f)
                report["_filepath"] = str(filepath)
                report["_report_id"] = filepath.stem
                reports.append(report)
        except Exception as exc:
            logger.error("Error loading report %s: %s", filepath, exc)

    return reports


def load_report_by_id(report_id: str) -> Optional[Dict[str, Any]]:
    """Load a saved JSON report by filename stem or full filename."""
    if not report_id:
        return None
    # Reject path traversal / absolute paths in report ids.
    if (
        ".." in report_id
        or "/" in report_id
        or "\\" in report_id
        or report_id.startswith(".")
    ):
        return None
    name = report_id if report_id.endswith(".json") else f"{report_id}.json"
    if Path(name).name != name:
        return None
    results_root = RESULTS_DIR.resolve()
    filepath = (RESULTS_DIR / name).resolve()
    try:
        filepath.relative_to(results_root)
    except ValueError:
        return None
    if not filepath.exists():
        # Missing results/ (fresh install / wiped disk) — skip glob crash and try remote.
        if RESULTS_DIR.exists():
            for path in RESULTS_DIR.glob("*.json"):
                if path.stem == report_id or path.name == name:
                    candidate = path.resolve()
                    try:
                        candidate.relative_to(results_root)
                    except ValueError:
                        continue
                    filepath = candidate
                    break
            else:
                try:
                    from supabase_store import fetch_scan_report

                    remote = fetch_scan_report(
                        report_id[:-5] if report_id.endswith(".json") else report_id
                    )
                    if remote:
                        return remote
                except Exception as exc:
                    logger.warning("Supabase report fetch failed for %s: %s", report_id, exc)
                return None
        else:
            try:
                from supabase_store import fetch_scan_report

                remote = fetch_scan_report(
                    report_id[:-5] if report_id.endswith(".json") else report_id
                )
                if remote:
                    return remote
            except Exception as exc:
                logger.warning("Supabase report fetch failed for %s: %s", report_id, exc)
            return None

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        data["_filepath"] = str(filepath)
        data["_report_id"] = filepath.stem
        return data


def _update_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        if job_id not in _jobs:
            loaded = load_job(job_id)
            if loaded:
                _jobs[job_id] = loaded
        if job_id in _jobs:
            # Never downgrade a finished job back to "running" (e.g. stray status() after complete).
            if (
                fields.get("status") == "running"
                and _jobs[job_id].get("status") in ("complete", "error")
            ):
                fields = {k: v for k, v in fields.items() if k != "status"}
            _jobs[job_id].update(fields)
            save_job(job_id, _jobs[job_id])


def _append_log(job_id: str, message: str) -> None:
    line = f"{datetime.now().strftime('%H:%M:%S')} — {message}"
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["log"].append(line)
            if len(_jobs[job_id]["log"]) > 50:
                _jobs[job_id]["log"] = _jobs[job_id]["log"][-50:]


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            return _normalize_job(dict(job))
    loaded = load_job(job_id)
    if loaded:
        with _jobs_lock:
            _jobs[job_id] = loaded
        return _normalize_job(dict(loaded))
    return None


def _normalize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Recover jobs stuck at 100% after a premature status overwrite."""
    if (
        job.get("status") == "running"
        and job.get("report_path")
        and int(job.get("progress") or 0) >= 100
    ):
        job["status"] = "complete"
        job.setdefault("message", "Scan complete")
    return job


def _active_scan_count() -> int:
    return count_running_jobs()


def _check_scan_capacity() -> Optional[str]:
    if _active_scan_count() >= MAX_CONCURRENT_SCANS:
        return (
            f"Too many scans in progress (limit: {MAX_CONCURRENT_SCANS}). "
            "Please wait for an active scan to finish."
        )
    return None


class ScanTimeoutError(TimeoutError):
    """Raised when a background scan exceeds the configured timeout."""


def _timeout_guard(started_at: float) -> None:
    elapsed = time.monotonic() - started_at
    if elapsed > SCAN_JOB_TIMEOUT_SECONDS:
        raise ScanTimeoutError(
            f"Scan timed out after {SCAN_JOB_TIMEOUT_SECONDS} seconds. "
            "Try again with manual policy URLs or a PDF upload."
        )


def run_scan_job(
    job_id: str,
    url: str,
    privacy_url_manual: Optional[str] = None,
    terms_url_manual: Optional[str] = None,
    cookie_url_manual: Optional[str] = None,
) -> None:
    """Execute a full compliance scan in a background thread."""
    driver = None
    progress = 5
    started_at = time.monotonic()

    def status(message: str, pct: Optional[int] = None) -> None:
        nonlocal progress
        _timeout_guard(started_at)
        _append_log(job_id, message)
        if pct is not None:
            progress = pct
        _update_job(job_id, status="running", progress=progress, message=message)

    try:
        status("Initializing scan…", 5)

        all_manual = privacy_url_manual and terms_url_manual and cookie_url_manual
        if all_manual:
            status("Using provided policy links — skipping homepage discovery", 10)
        else:
            status("Discovering policy pages on the target website", 10)

        if privacy_url_manual:
            status(f"Manual privacy policy: {privacy_url_manual}")
        if terms_url_manual:
            status(f"Manual terms URL: {terms_url_manual}")
        if cookie_url_manual:
            status(f"Manual cookie policy: {cookie_url_manual}")

        if not all_manual:
            status(f"Fetching homepage: {url}")

        discovery_result = discover_policies(
            url,
            privacy_url_manual=privacy_url_manual,
            terms_url_manual=terms_url_manual,
            cookie_url_manual=cookie_url_manual,
        )
        driver = discovery_result.get("driver")

        status(f"Scraping method: {discovery_result['method']}", 25)

        links = discovery_result["links"]
        for policy_type, link_url in links.items():
            if link_url:
                source = "manual" if (
                    (policy_type == "privacy" and privacy_url_manual)
                    or (policy_type == "terms" and terms_url_manual)
                    or (policy_type == "cookie" and cookie_url_manual)
                ) else "discovered"
                status(f"{policy_type.title()} policy ({source}): {link_url}", 28)
            else:
                status(f"{policy_type.title()} policy not found", 28)

        if discovery_result["error"] and not links.get("privacy"):
            _update_job(
                job_id,
                status="error",
                error=f"Failed to access website: {discovery_result['error']}",
                progress=100,
            )
            return

        privacy_url = links.get("privacy")
        status("Extracting text from policy pages", 40)

        policy_text = None
        terms_text = ""
        cookie_text = ""

        if privacy_url:
            status(f"Fetching privacy policy: {privacy_url}")
            policy_text = fetch_policy_text(privacy_url, driver=driver)
            if policy_text:
                status(f"Extracted {len(policy_text):,} characters from privacy policy", 50)
            else:
                status("Failed to extract privacy policy text", 50)
                logger.warning(
                    "Text extraction returned empty for privacy policy URL: %s",
                    privacy_url,
                )

        terms_url = links.get("terms")
        if terms_url:
            terms_text = fetch_policy_text(terms_url, driver=driver) or ""
            if terms_text:
                status(f"Extracted {len(terms_text):,} characters from terms of service", 55)

        cookie_url = links.get("cookie")
        if cookie_url:
            cookie_text = fetch_policy_text(cookie_url, driver=driver) or ""
            if cookie_text:
                status(f"Extracted {len(cookie_text):,} characters from cookie policy", 58)

        status("Running DPDP compliance analysis", 65)

        def analysis_callback(step: str) -> None:
            status(step, 75)

        report = run_compliance_check(
            url=url,
            privacy_policy_url=privacy_url,
            policy_text=policy_text,
            cookie_banner=discovery_result.get("cookie_banner", False),
            scraping_method=discovery_result["method"],
            policy_links=discovery_result["links"],
            status_callback=analysis_callback,
            terms_text=terms_text,
        )

        if privacy_url and not (policy_text or "").strip():
            report.errors.append(
                "Could not extract text from the privacy policy URL. "
                "Paste the direct policy link in Advanced input and scan again."
            )

        # Check if confidence refinement is needed for paid scans
        job = get_job(job_id) or {}
        is_paid_scan = job.get("auto_unlock_on_complete", False)
        
        if is_paid_scan and policy_text:
            from confidence_refinement import should_refine_confidence, fetch_additional_context_pages
            
            llm_analysis = report.analysis_details.get("llm_analysis")
            should_refine, avg_confidence = should_refine_confidence(llm_analysis, is_paid_scan)
            
            if should_refine:
                status(f"Initial confidence {avg_confidence:.0f}% — Refining analysis with additional site context…", 78)
                logger.info(f"Refinement triggered for paid scan (avg confidence: {avg_confidence:.0f}%)")
                
                # Fetch up to 3 additional pages from the same domain
                additional_text = fetch_additional_context_pages(url, max_pages=3, driver=driver)
                
                if additional_text:
                    status(f"Fetched additional context — Re-running AI analysis…", 82)
                    
                    # Combine original and additional text
                    combined_policy_text = f"{policy_text}\n\n{additional_text}"
                    
                    # Re-run analysis with combined text
                    def refinement_callback(step: str) -> None:
                        status(f"[Refinement] {step}", 85)
                    
                    report = run_compliance_check(
                        url=url,
                        privacy_policy_url=privacy_url,
                        policy_text=combined_policy_text,
                        cookie_banner=discovery_result.get("cookie_banner", False),
                        scraping_method=discovery_result["method"],
                        policy_links=discovery_result["links"],
                        status_callback=refinement_callback,
                        terms_text=terms_text,
                    )
                    
                    refined_llm = report.analysis_details.get("llm_analysis")
                    if refined_llm:
                        _, final_confidence = should_refine_confidence(refined_llm, True)
                        if final_confidence:
                            status(f"Refinement complete — Final confidence: {final_confidence:.0f}%", 89)
                            logger.info(f"Refinement complete: {avg_confidence:.0f}% → {final_confidence:.0f}%")
                else:
                    logger.warning("Could not fetch additional pages for refinement")
                    status("Refinement skipped — continuing with initial analysis", 82)

        _persist_extracted_texts(report, policy_text, terms_text, cookie_text)

        status("Saving report", 92)
        filepath = save_report(report)

        _update_job(
            job_id,
            status="complete",
            progress=100,
            message="Scan complete",
            report=report.to_dict(),
            policy_text=policy_text or "",
            terms_text=terms_text,
            cookie_text=cookie_text,
            report_path=filepath,
        )
        _finalize_scan_access(job_id, filepath, report.to_dict())

    except ScanTimeoutError as exc:
        logger.warning("Scan job %s timed out", job_id)
        _update_job(job_id, status="error", error=str(exc), progress=100)
    except Exception as exc:
        logger.exception("Scan job %s failed", job_id)
        _update_job(job_id, status="error", error=str(exc), progress=100)
    finally:
        if driver:
            cleanup_driver(driver)


def run_pdf_scan_job(
    job_id: str,
    reference: str,
    pdf_files: Dict[str, bytes],
) -> None:
    """
    Run compliance analysis from uploaded PDF documents (no web scraping).

    pdf_files keys: privacy (required), terms (optional), cookie (optional).
    Values are raw PDF bytes keyed by logical document type.
    """
    progress = 5
    started_at = time.monotonic()

    def status(message: str, pct: Optional[int] = None) -> None:
        nonlocal progress
        _timeout_guard(started_at)
        _append_log(job_id, message)
        if pct is not None:
            progress = pct
        _update_job(job_id, status="running", progress=progress, message=message)

    try:
        status("Reading uploaded PDF documents…", 10)

        upload_dir = UPLOADS_DIR / job_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        policy_text = None
        terms_text = ""
        cookie_text = ""
        saved_files: Dict[str, str] = {}
        display_links: Dict[str, Optional[str]] = {
            "privacy": None,
            "terms": None,
            "cookie": None,
        }

        if "privacy" not in pdf_files:
            _update_job(
                job_id,
                status="error",
                error="A Privacy Policy PDF is required.",
                progress=100,
            )
            return

        doc_labels = {
            "privacy": "Privacy Policy",
            "terms": "Terms of Service",
            "cookie": "Cookie Policy",
        }

        for doc_type, data in pdf_files.items():
            label = doc_labels.get(doc_type, doc_type.title())
            status(f"Extracting text from {label} PDF…", 30)
            path = save_pdf_upload(upload_dir, f"{doc_type}.pdf", data)
            saved_files[doc_type] = str(path)
            text = extract_text_from_pdf(data)
            display_links[doc_type] = f"Uploaded: {path.name}"

            if doc_type == "privacy":
                policy_text = text
                status(f"Extracted {len(text):,} characters from privacy policy", 45)
            elif doc_type == "terms":
                terms_text = text
                status(f"Extracted {len(text):,} characters from terms of service", 50)
            elif doc_type == "cookie":
                cookie_text = text
                status(f"Extracted {len(text):,} characters from cookie policy", 55)

        if not policy_text:
            _update_job(
                job_id,
                status="error",
                error="Could not extract text from the privacy policy PDF.",
                progress=100,
            )
            return

        status("Running DPDP compliance analysis", 65)

        def analysis_callback(step: str) -> None:
            status(step, 75)

        report = run_compliance_check(
            url=reference,
            privacy_policy_url=display_links.get("privacy"),
            policy_text=policy_text,
            cookie_banner=False,
            scraping_method="pdf_upload",
            policy_links=display_links,
            status_callback=analysis_callback,
            terms_text=terms_text,
        )
        report.analysis_details["uploaded_files"] = saved_files
        report.analysis_details["input_mode"] = "pdf"
        _persist_extracted_texts(report, policy_text, terms_text, cookie_text)

        status("Saving report", 92)
        filepath = save_report(report, slug=_slugify_reference(reference))

        _update_job(
            job_id,
            status="complete",
            progress=100,
            message="Scan complete",
            report=report.to_dict(),
            policy_text=policy_text,
            terms_text=terms_text,
            cookie_text=cookie_text,
            report_path=filepath,
        )
        _finalize_scan_access(job_id, filepath, report.to_dict())

    except ScanTimeoutError as exc:
        _update_job(job_id, status="error", error=str(exc), progress=100)
    except ValueError as exc:
        _update_job(job_id, status="error", error=str(exc), progress=100)
    except Exception as exc:
        logger.exception("PDF scan job %s failed", job_id)
        _update_job(job_id, status="error", error=str(exc), progress=100)


def _finalize_scan_access(job_id: str, filepath: str, report_dict: dict) -> None:
    job = get_job(job_id) or {}
    owner = (job.get("owner_user_id") or "").strip()
    report_id = Path(filepath).stem
    if not owner:
        return
    from entitlements import assign_report_owner

    assign_report_owner(report_id, owner, report_dict)

    if job.get("auto_unlock_on_complete"):
        from scan_quota import unlock_prepaid_scan_report

        try:
            unlock_prepaid_scan_report(owner, report_id)
        except Exception as exc:
            logger.error("Auto-unlock after prepaid scan failed for %s: %s", report_id, exc)


def start_scan(
    url: str,
    privacy_url_manual: Optional[str] = None,
    terms_url_manual: Optional[str] = None,
    cookie_url_manual: Optional[str] = None,
    owner_user_id: Optional[str] = None,
    auto_unlock_on_complete: bool = False,
    scan_slot_type: Optional[str] = None,
) -> str:
    """Start a background scan and return job_id."""
    capacity_error = _check_scan_capacity()
    if capacity_error:
        raise RuntimeError(capacity_error)

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "url": url,
            "status": "running",
            "progress": 0,
            "message": "Queued",
            "log": [],
            "created_at": datetime.now().isoformat(),
            "owner_user_id": (owner_user_id or "").strip() or None,
            "auto_unlock_on_complete": auto_unlock_on_complete,
            "scan_slot_type": (scan_slot_type or "").strip() or None,
            "credit_refunded": False,
        }
        save_job(job_id, _jobs[job_id])

    thread = threading.Thread(
        target=run_scan_job,
        args=(job_id, url, privacy_url_manual, terms_url_manual, cookie_url_manual),
        daemon=True,
    )
    thread.start()
    return job_id


def start_pdf_scan(
    reference: str,
    pdf_files: Dict[str, bytes],
    owner_user_id: Optional[str] = None,
    auto_unlock_on_complete: bool = False,
    scan_slot_type: Optional[str] = None,
) -> str:
    """Start a background scan from uploaded PDFs and return job_id."""
    capacity_error = _check_scan_capacity()
    if capacity_error:
        raise RuntimeError(capacity_error)

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "url": reference,
            "status": "running",
            "progress": 0,
            "message": "Queued",
            "log": [],
            "created_at": datetime.now().isoformat(),
            "input_mode": "pdf",
            "owner_user_id": (owner_user_id or "").strip() or None,
            "auto_unlock_on_complete": auto_unlock_on_complete,
            "scan_slot_type": (scan_slot_type or "").strip() or None,
            "credit_refunded": False,
        }
        save_job(job_id, _jobs[job_id])

    thread = threading.Thread(
        target=run_pdf_scan_job,
        args=(job_id, reference, pdf_files),
        daemon=True,
    )
    thread.start()
    return job_id


def ai_engine_label() -> str:
    """Human-readable label for the active AI engine."""
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "DeepSeek Expert"
    return "Keyword Analysis (DeepSeek not configured)"
