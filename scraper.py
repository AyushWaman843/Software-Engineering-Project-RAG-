"""
Resilient web scraping module with requests + Selenium fallback.
Includes retry logic, robots.txt respect, and link discovery.
"""

import os
import re
import time
import logging
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
import validators
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from utils import (
    get_random_user_agent,
    clean_text,
    is_allowed_by_robots,
    find_policy_links,
    detect_cookie_banner_selenium,
)
from security import SSRFError, validate_scan_url

logger = logging.getLogger(__name__)

# Cap redirect hops when following 3xx responses manually (SSRF-safe fetch).
MAX_REDIRECTS = 5

# Reliable opening phrases — trim site chrome / nav before the real policy body
POLICY_START_MARKERS = [
    "Your right to privacy is very important",
    "This Privacy Policy explains",
    "We are committed to protecting your privacy",
    "Last Updated on",
]

# Navigation / generator chrome to drop from extracted policy text
NAVIGATION_PHRASES = [
    "Privacy Notice Generator",
    "Legitimate Interest Tool",
    "Sections DPDP Rules BLOGS",
    "Table of contents",
    "Report error",
    "Submit",
]


def clean_extracted_text(raw_text: str) -> str:
    """
    Trim homepage/nav junk from scraped policy text.

    1. Start at the earliest POLICY_START_MARKERS hit (case-insensitive).
    2. Drop lines containing NAVIGATION_PHRASES.
    3. Remove HTML comments and collapse excessive blank lines / whitespace.
    """
    if not raw_text:
        return ""

    text = re.sub(r"<!--[\s\S]*?-->", "", raw_text)
    text_lower = text.lower()

    start_at: Optional[int] = None
    for marker in POLICY_START_MARKERS:
        idx = text_lower.find(marker.lower())
        if idx != -1:
            start_at = idx if start_at is None else min(start_at, idx)

    if start_at is not None:
        text = text[start_at:]
        text_lower = text.lower()

    lines = text.splitlines() if "\n" in text else [text]
    kept_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(phrase.lower() in stripped.lower() for phrase in NAVIGATION_PHRASES):
            continue
        kept_lines.append(stripped)

    if kept_lines:
        text = "\n".join(kept_lines)
    else:
        text = text.strip()

    for phrase in NAVIGATION_PHRASES:
        text = re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE)

    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


class ScraperError(Exception):
    """Custom exception for scraping errors."""
    pass


def _normalize_manual_url(manual_url: Optional[str]) -> Optional[str]:
    """
    Validate and normalize an optional manual policy URL.
    Returns None if empty, invalid, or not a proper http(s) URL.
    """
    if not manual_url or not str(manual_url).strip():
        return None
    url = str(manual_url).strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if validators.url(url):
        return url
    logger.warning("Invalid manual URL rejected: %s", manual_url)
    return None


def _merge_discovered_links(
    existing: dict,
    discovered: dict,
) -> dict:
    """Fill in only the link slots that are still empty after manual overrides."""
    merged = existing.copy()
    for key in ("privacy", "terms", "cookie"):
        if merged.get(key) is None and discovered.get(key):
            merged[key] = discovered[key]
    return merged


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.RequestException, requests.Timeout)),
    reraise=True,
)
def fetch_with_requests(url: str, timeout: int = 10) -> Tuple[str, BeautifulSoup]:
    """
    Fetch URL using requests library with retry logic.
    
    Args:
        url: Target URL.
        timeout: Request timeout in seconds.
    
    Returns:
        Tuple of (HTML content, BeautifulSoup object).
    
    Raises:
        ScraperError: If fetching fails after retries.
    """
    if not is_allowed_by_robots(url):
        raise ScraperError(f"URL blocked by robots.txt: {url}")

    # SSRF: validate the target and re-validate every redirect hop so a public
    # URL can't 3xx-bounce us to an internal / metadata address.
    current = validate_scan_url(url)

    headers = {'User-Agent': get_random_user_agent()}
    logger.info(f"Fetching {url} with requests...")

    with requests.Session() as session:
        for _ in range(MAX_REDIRECTS + 1):
            response = session.get(
                current, headers=headers, timeout=timeout, allow_redirects=False
            )
            if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    break
                next_url = urljoin(current, location)
                try:
                    current = validate_scan_url(next_url)
                except SSRFError:
                    raise ScraperError(
                        f"Blocked redirect to disallowed address: {next_url}"
                    )
                continue

            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            logger.info(f"Successfully fetched {current} with requests.")
            return response.text, soup

    raise ScraperError(f"Too many redirects while fetching {url}")


def _resolve_chromedriver_binary(candidate: str) -> str:
    """
    webdriver-manager sometimes returns a notice file instead of the binary.
    Prefer chromedriver / chromedriver.exe under the download tree (Linux + Windows).
    """
    if not candidate:
        return candidate
    base = os.path.basename(candidate).lower()
    if base in ("chromedriver", "chromedriver.exe") and os.path.isfile(candidate):
        return candidate

    search_roots = {
        os.path.dirname(candidate),
        os.path.dirname(os.path.dirname(candidate)),
    }
    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in ("chromedriver", "chromedriver.exe"):
                if name in filenames:
                    path = os.path.join(dirpath, name)
                    if os.path.isfile(path):
                        return path
    return candidate


def create_selenium_driver() -> webdriver.Chrome:
    """
    Create a headless Selenium Chrome driver with stealth settings.
    
    Returns:
        webdriver.Chrome: Configured Chrome driver.
    """
    chrome_options = ChromeOptions()
    # Container-friendly headless (Render / Docker)
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--window-size=1280,720")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument(f"user-agent={get_random_user_agent()}")

    chrome_bin = os.getenv("CHROME_BIN", "").strip()
    if chrome_bin:
        chrome_options.binary_location = chrome_bin

    driver_path = os.getenv("CHROMEDRIVER_PATH", "").strip()
    if not driver_path:
        driver_path = ChromeDriverManager().install()
        driver_path = _resolve_chromedriver_binary(driver_path)

    logger.info("Using chromedriver at: %s (chrome_bin=%s)", driver_path, chrome_bin or "default")
    service = ChromeService(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Execute script to remove webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    logger.info("Selenium Chrome driver created.")
    return driver


def fetch_with_selenium(url: str, driver: Optional[webdriver.Chrome] = None) -> Tuple[str, BeautifulSoup, webdriver.Chrome]:
    """
    Fetch URL using Selenium (fallback for JavaScript-heavy sites).
    
    Args:
        url: Target URL.
        driver: Existing Selenium driver (optional, creates new one if None).
    
    Returns:
        Tuple of (HTML content, BeautifulSoup object, driver instance).
    
    Raises:
        ScraperError: If fetching fails.
    """
    # SSRF: validate before letting a real browser navigate anywhere.
    safe_url = validate_scan_url(url)

    own_driver = driver is None
    if own_driver:
        driver = create_selenium_driver()
    
    try:
        logger.info(f"Fetching {safe_url} with Selenium...")
        driver.get(safe_url)
        time.sleep(2)  # Allow time for JS to load

        # Re-check where the browser actually landed after any client-side
        # or HTTP redirects; discard content if it resolved to an internal host.
        landed = driver.current_url or safe_url
        try:
            validate_scan_url(landed)
        except SSRFError:
            raise ScraperError(f"Blocked redirect to disallowed address: {landed}")

        html = driver.page_source
        soup = BeautifulSoup(html, 'lxml')
        logger.info(f"Successfully fetched {landed} with Selenium.")
        
        return html, soup, driver
    except Exception as e:
        if own_driver and driver:
            driver.quit()
        raise ScraperError(f"Selenium fetch failed for {url}: {e}")


def discover_policies(
    url: str,
    privacy_url_manual: Optional[str] = None,
    terms_url_manual: Optional[str] = None,
    cookie_url_manual: Optional[str] = None,
) -> dict:
    """
    Discover privacy policy, terms, and cookie policy links from a website.
    Falls back to Selenium if requests fails.

    Cookie consent banners are JS-injected on most modern sites, so homepage
    banner detection ALWAYS uses Selenium — even when requests already found
    every policy link. Manual-only scans still open the homepage once to check
    for a banner before extraction.

    Args:
        url: Homepage URL of the website.
        privacy_url_manual: Optional direct privacy policy URL.
        terms_url_manual: Optional direct terms of service URL.
        cookie_url_manual: Optional direct cookie policy URL.

    Returns:
        dict: Contains 'links' (policy URLs), 'cookie_banner' (bool), 'method' (str), 'driver' (optional).
    """
    result = {
        'links': {'privacy': None, 'terms': None, 'cookie': None},
        'cookie_banner': False,
        'method': None,
        'driver': None,
        'error': None,
    }

    # Apply validated manual URLs first — these bypass homepage link search
    manual_applied = []
    manual_privacy = _normalize_manual_url(privacy_url_manual)
    manual_terms = _normalize_manual_url(terms_url_manual)
    manual_cookie = _normalize_manual_url(cookie_url_manual)

    if manual_privacy:
        result['links']['privacy'] = manual_privacy
        manual_applied.append('privacy')
        logger.info("Using manual privacy policy URL: %s", manual_privacy)
    if manual_terms:
        result['links']['terms'] = manual_terms
        manual_applied.append('terms')
    if manual_cookie:
        result['links']['cookie'] = manual_cookie
        manual_applied.append('cookie')

    needs_homepage_discovery = any(
        result['links'][key] is None for key in ('privacy', 'terms', 'cookie')
    )

    if manual_applied:
        logger.info(
            "Using manual URL(s) for: %s; discovering remaining links from homepage",
            ", ".join(manual_applied),
        )

    # Fast path: fill missing policy links via requests (when needed).
    requests_ok = False
    if needs_homepage_discovery:
        try:
            html, soup = fetch_with_requests(url)
            discovered = find_policy_links(soup, url)
            result['links'] = _merge_discovered_links(result['links'], discovered)
            result['method'] = 'requests' if not manual_applied else 'manual+requests'
            requests_ok = True
        except Exception as e:
            logger.warning(
                "Requests link discovery failed (%s); continuing with Selenium homepage pass.",
                e,
            )
    else:
        result['method'] = 'manual'
        logger.info(
            "All policy URLs supplied manually (%s) — still checking homepage for cookie banner",
            ", ".join(manual_applied),
        )

    # Always use Selenium for cookie-banner detection (and fill any missing links).
    try:
        html, soup, driver = fetch_with_selenium(url)
        discovered = find_policy_links(soup, url)
        result['links'] = _merge_discovered_links(result['links'], discovered)
        result['cookie_banner'] = detect_cookie_banner_selenium(driver)
        if requests_ok and manual_applied:
            result['method'] = 'manual+requests+selenium'
        elif requests_ok:
            result['method'] = 'requests+selenium'
        elif manual_applied:
            result['method'] = 'manual+selenium'
        else:
            result['method'] = 'selenium'
        result['driver'] = driver  # Keep driver alive for reuse
        return result

    except Exception as e:
        logger.error(f"Selenium homepage pass failed: {e}")
        result['error'] = str(e)
        if not result['method']:
            result['method'] = 'failed'
        # If we at least have policy URLs from requests/manual, caller can continue
        # without a banner check (cookie_banner stays False).
        if result['links'].get('privacy'):
            logger.info(
                "Banner check failed but policy URL(s) are available; continuing without banner"
            )
        return result


def fetch_policy_text(url: str, driver: Optional[webdriver.Chrome] = None) -> Optional[str]:
    """
    Fetch and extract clean text from a policy page.
    
    Args:
        url: Policy page URL.
        driver: Optional Selenium driver to reuse.
    
    Returns:
        str or None: Cleaned text content, or None on error.
    """
    try:
        if driver:
            # Reuse existing Selenium driver
            html, soup, _ = fetch_with_selenium(url, driver=driver)
        else:
            # Try requests first
            try:
                html, soup = fetch_with_requests(url)
            except Exception:
                # Fallback to Selenium
                html, soup, temp_driver = fetch_with_selenium(url)
                temp_driver.quit()
        
        text = clean_text(html)
        text = clean_extracted_text(text)
        stripped = (text or "").strip()
        if not stripped:
            logger.warning(
                "Text extraction returned empty content for policy URL: %s "
                "(HTML length: %d bytes)",
                url,
                len(html or ""),
            )
            return None
        if len(stripped) < 50:
            logger.warning(
                "Text extraction returned only %d characters for policy URL: %s",
                len(stripped),
                url,
            )
        logger.info("Extracted %d characters from %s", len(text), url)
        return text

    except Exception as e:
        logger.error("Failed to fetch policy text from %s: %s", url, e)
        return None


def cleanup_driver(driver: Optional[webdriver.Chrome]) -> None:
    """
    Safely quit a Selenium driver.
    
    Args:
        driver: Selenium driver to close.
    """
    if driver:
        try:
            driver.quit()
            logger.info("Selenium driver closed.")
        except Exception as e:
            logger.error(f"Error closing Selenium driver: {e}")
