"""
Confidence refinement module for paid scans.

When initial confidence is below 80%, fetches additional same-site pages that
are likely to hold the missing evidence (grievance officer / DPO, data-principal
rights, children's data, consent) and re-runs the AI analysis on the combined text.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from retrieval import ADDITIONAL_CONTEXT_MARKER
from scraper import fetch_policy_text, fetch_with_requests, fetch_with_selenium
from utils import find_related_links

logger = logging.getLogger(__name__)


def refinement_enabled() -> bool:
    """CONFIDENCE_REFINEMENT_ENABLED=0 turns the paid-scan second pass off; each pass is one more LLM call."""
    return os.environ.get("CONFIDENCE_REFINEMENT_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}

# Tried after topic links found on the homepage, for sites that do not link them.
_FALLBACK_PATHS = (
    "/grievance",
    "/grievance-redressal",
    "/grievance-officer",
    "/data-protection",
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/legal",
    "/disclaimer",
)

MIN_PAGE_CHARS = 200
_ERROR_PAGE_RE = re.compile(
    r"\b(?:404|page not found|not found|does(?:n'?t| not) exist|no longer available)\b",
    re.IGNORECASE,
)


def _looks_like_error_page(text: str) -> bool:
    """A browser renders a branded 404 page without raising, so detect it from the text."""
    return len(text) < 2500 and bool(_ERROR_PAGE_RE.search(text[:400]))


def _fingerprint(text: str) -> str:
    return re.sub(r"\W+", " ", text[:500]).strip().lower()


def _homepage_soup(base_url: str, driver=None):
    try:
        return fetch_with_requests(base_url)[1]
    except Exception as exc:
        logger.info("Homepage fetch via requests failed for link discovery: %s", exc)
    if driver is not None:
        try:
            return fetch_with_selenium(base_url, driver=driver)[1]
        except Exception as exc:
            logger.info("Homepage fetch via browser failed for link discovery: %s", exc)
    return None


def candidate_context_urls(
    base_url: str,
    exclude_urls: Iterable[Optional[str]] = (),
    driver=None,
    limit: int = 9,
) -> List[str]:
    """Topic links found on the homepage first, then common fallback paths."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    skip = {base_url, *(u for u in exclude_urls if u)}

    candidates: List[str] = []
    soup = _homepage_soup(base_url, driver)
    if soup is not None:
        candidates.extend(find_related_links(soup, base_url, exclude=skip, limit=limit))
    for path in _FALLBACK_PATHS:
        url = f"{origin}{path}"
        if url not in candidates and url not in skip:
            candidates.append(url)
    return candidates[:limit]


def fetch_additional_context_pages(
    base_url: str,
    max_pages: int = 3,
    driver=None,
    exclude_urls: Iterable[Optional[str]] = (),
) -> str:
    """
    Fetch up to max_pages additional pages from the same site for context refinement.

    Pages are chosen by topic from the homepage's links (grievance, DPO, rights,
    children, consent, contact), with common paths as a fallback. Error pages and
    pages that duplicate one already collected are skipped, as are the pages in
    ``exclude_urls`` (those were analysed in the first pass).

    Args:
        base_url: The original website URL to extract domain from.
        max_pages: Maximum number of additional pages to keep (default 3).
        driver: Optional Selenium driver to reuse.
        exclude_urls: Pages already analysed (privacy, terms, cookie).

    Returns:
        str: Combined text, starting with ADDITIONAL_CONTEXT_MARKER, or "" if no page qualified.
    """
    pages: List[str] = []
    seen: set[str] = set()

    for url in candidate_context_urls(base_url, exclude_urls, driver, limit=max_pages * 3):
        if len(pages) >= max_pages:
            break
        try:
            logger.info("Fetching additional context from: %s", url)
            text = (fetch_policy_text(url, driver=driver) or "").strip()
        except Exception as exc:
            logger.warning("Failed to fetch additional page %s: %s", url, exc)
            continue

        if len(text) < MIN_PAGE_CHARS:
            continue
        if _looks_like_error_page(text):
            logger.info("Skipping error-like page: %s", url)
            continue
        fingerprint = _fingerprint(text)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        pages.append(f"[Source: {url}]\n{text}")
        logger.info("Added %d chars from %s", len(text), url)

    if not pages:
        return ""
    result = f"\n\n{ADDITIONAL_CONTEXT_MARKER}\n\n" + "\n\n".join(pages)
    logger.info("Fetched %d additional pages, total %d additional chars", len(pages), len(result))
    return result


def should_refine_confidence(
    llm_result: Optional[Dict[str, Any]],
    is_paid_scan: bool,
) -> tuple[bool, Optional[float]]:
    """
    Determine if confidence refinement should be performed.

    Args:
        llm_result: The LLM analysis result with indicators and confidence values.
        is_paid_scan: Whether this is a paid scan (Pro or one-time unlock).

    Returns:
        Tuple of (should_refine: bool, average_confidence: float | None)
    """
    if not is_paid_scan:
        return False, None

    if not refinement_enabled():
        logger.info("Confidence refinement is disabled (CONFIDENCE_REFINEMENT_ENABLED=0)")
        return False, None

    if not llm_result or not isinstance(llm_result, dict):
        return False, None

    indicators = llm_result.get("indicators", {})
    if not indicators:
        return False, None

    # Calculate average confidence across non-Missing indicators
    confidences = []
    for entry in indicators.values():
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "")).strip().lower()
        if status == "missing":
            continue
        raw_conf = entry.get("confidence")
        if raw_conf is None:
            continue
        try:
            conf = float(raw_conf)
            confidences.append(max(0.0, min(100.0, conf)))
        except (TypeError, ValueError):
            continue

    if not confidences:
        return False, None

    average = sum(confidences) / len(confidences)

    # Refine if average confidence is below 80%
    should_refine = average < 80.0
    logger.info(f"Average confidence: {average:.1f}% - Refinement {'needed' if should_refine else 'not needed'}")

    return should_refine, average
