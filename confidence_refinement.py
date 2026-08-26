"""
Confidence refinement module for paid scans.

Automatically fetches additional pages from the same domain and re-runs
AI analysis when initial confidence is below 80%.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from scraper import fetch_policy_text

logger = logging.getLogger(__name__)


def fetch_additional_context_pages(
    base_url: str,
    max_pages: int = 3,
    driver = None,
) -> str:
    """
    Fetch up to max_pages additional pages from the same domain for context refinement.
    
    Targets common pages: /about, /contact, /legal, /disclaimer, homepage.
    Returns combined text from all successfully fetched pages.
    
    Args:
        base_url: The original website URL to extract domain from.
        max_pages: Maximum number of additional pages to fetch (default 3).
        driver: Optional Selenium driver to reuse.
    
    Returns:
        str: Combined text from all fetched pages, or empty string if none succeed.
    """
    parsed = urlparse(base_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    
    # Common paths that might contain useful privacy/compliance information
    candidate_paths = [
        "/about",
        "/about-us",
        "/contact",
        "/contact-us",
        "/legal",
        "/disclaimer",
        "/terms",
        "/",  # Homepage as fallback
    ]
    
    combined_text = []
    pages_fetched = 0
    
    for path in candidate_paths:
        if pages_fetched >= max_pages:
            break
            
        url = f"{domain}{path}"
        if url == base_url:
            # Skip if it's the same as the original URL
            continue
            
        try:
            logger.info(f"Fetching additional context from: {url}")
            text = fetch_policy_text(url, driver=driver)
            if text and len(text.strip()) > 100:
                combined_text.append(text)
                pages_fetched += 1
                logger.info(f"Successfully fetched {len(text)} chars from {url}")
        except Exception as exc:
            logger.warning(f"Failed to fetch additional page {url}: {exc}")
            continue
    
    if combined_text:
        result = "\n\n--- Additional Context from Related Pages ---\n\n" + "\n\n".join(combined_text)
        logger.info(f"Fetched {pages_fetched} additional pages, total {len(result)} additional chars")
        return result
    return ""


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
