"""
Utility functions for DPDP compliance scanner.
Includes text cleaning, User-Agent rotation, robots.txt handling, and cookie banner detection.
"""

import re
import random
import logging
import time
from typing import Optional, List
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """
    Return a random User-Agent string from a predefined list.
    
    Returns:
        str: A User-Agent string.
    """
    return random.choice(USER_AGENTS)


def clean_text(html: str) -> str:
    """
    Extract clean text from HTML, removing scripts, styles, and excessive whitespace.
    
    Args:
        html: Raw HTML string.
    
    Returns:
        str: Cleaned text content.
    """
    soup = BeautifulSoup(html, 'lxml')
    
    # Remove script and style elements
    for script_or_style in soup(['script', 'style', 'noscript']):
        script_or_style.decompose()
    
    text = soup.get_text(separator=' ', strip=True)
    # Collapse multiple whitespaces
    text = re.sub(r'\s+', ' ', text)
    return text


def is_allowed_by_robots(url: str, user_agent: str = "*") -> bool:
    """
    Check if the given URL is allowed by the site's robots.txt.
    
    Args:
        url: Target URL to check.
        user_agent: User-agent string (default: wildcard).
    
    Returns:
        bool: True if allowed, False otherwise. Returns True on errors (permissive).
    """
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        
        return rp.can_fetch(user_agent, url)
    except Exception as e:
        logger.warning(f"Could not parse robots.txt for {url}: {e}. Allowing by default.")
        return True


def _normalize_link_match(value: str) -> str:
    """Lowercase and collapse separators for fuzzy keyword matching."""
    return re.sub(r"[\s_\-/]+", " ", (value or "").lower()).strip()


def _anchor_match_blob(anchor) -> tuple[str, str]:
    """Build normalized href and combined label text from an anchor element."""
    href = anchor.get("href", "")
    text_parts = [
        anchor.get_text(" ", strip=True),
        anchor.get("title", "") or "",
        anchor.get("aria-label", "") or "",
    ]
    label = " ".join(part for part in text_parts if part)
    return _normalize_link_match(href), _normalize_link_match(label)


# (pattern, score) — higher score wins; href matches score higher than label-only
_POLICY_PATTERNS: dict[str, list[tuple[str, int, str]]] = {
    "privacy": [
        (r"privacy[-_]?policy", 100, "href"),
        (r"privacypolicy", 100, "href"),
        (r"privacy[-_]?notice", 95, "href"),
        (r"privacy[-_]?statement", 95, "href"),
        (r"privacy[-_]?centre", 90, "href"),
        (r"privacy[-_]?center", 90, "href"),
        (r"/privacy(?:/|$|\?|#)", 90, "href"),
        (r"\bprivacy\b", 75, "href"),
        (r"data[-_]?protection[-_]?policy", 95, "href"),
        (r"dataprotection", 85, "href"),
        (r"data[-_]?protection", 80, "href"),
        (r"data[-_]?privacy", 85, "href"),
        (r"personal[-_]?data[-_]?policy", 90, "href"),
        (r"personal[-_]?information", 75, "href"),
        (r"protection[-_]?of[-_]?personal", 85, "href"),
        (r"your[-_]?privacy", 80, "href"),
        (r"legal/privacy", 90, "href"),
        (r"policies/privacy", 90, "href"),
        (r"policy/privacy", 90, "href"),
        (r"dpdp", 70, "href"),
        (r"pdpl", 65, "href"),
        (r"privacy policy", 85, "label"),
        (r"privacy notice", 80, "label"),
        (r"privacy statement", 80, "label"),
        (r"data protection policy", 90, "label"),
        (r"data protection", 75, "label"),
        (r"personal data policy", 85, "label"),
        (r"personal information policy", 80, "label"),
        (r"your privacy", 70, "label"),
        (r"^privacy$", 65, "label"),
        (r"how we use your data", 65, "label"),
        (r"how we handle your data", 65, "label"),
    ],
    "terms": [
        (r"terms[-_]?and[-_]?conditions", 100, "href"),
        (r"terms[-_]?conditions", 100, "href"),
        (r"terms[-_]?of[-_]?service", 100, "href"),
        (r"terms[-_]?of[-_]?use", 100, "href"),
        (r"termsofservice", 95, "href"),
        (r"termsandconditions", 95, "href"),
        (r"terms[-_]?of[-_]?access", 90, "href"),
        (r"terms[-_]?of[-_]?sale", 85, "href"),
        (r"user[-_]?agreement", 95, "href"),
        (r"useragreement", 95, "href"),
        (r"service[-_]?agreement", 90, "href"),
        (r"conditions[-_]?of[-_]?use", 95, "href"),
        (r"conditions[-_]?of[-_]?sale", 85, "href"),
        (r"website[-_]?terms", 90, "href"),
        (r"general[-_]?terms", 90, "href"),
        (r"legal/terms", 95, "href"),
        (r"legal/terms-of", 95, "href"),
        (r"policies/terms", 90, "href"),
        (r"/tos(?:/|$|\?|#)", 90, "href"),
        (r"/tnc(?:/|$|\?|#)", 90, "href"),
        (r"/terms(?:/|$|\?|#)", 85, "href"),
        (r"acceptable[-_]?use", 80, "href"),
        (r"end[-_]?user[-_]?license", 85, "href"),
        (r"\beula\b", 80, "href"),
        (r"terms and conditions", 95, "label"),
        (r"terms of service", 95, "label"),
        (r"terms of use", 95, "label"),
        (r"terms & conditions", 95, "label"),
        (r"terms and use", 85, "label"),
        (r"user agreement", 90, "label"),
        (r"service agreement", 85, "label"),
        (r"conditions of use", 90, "label"),
        (r"website terms", 85, "label"),
        (r"legal terms", 80, "label"),
        (r"\bt&c\b", 75, "label"),
        (r"\btos\b", 75, "label"),
    ],
    "cookie": [
        (r"cookie[-_]?policy", 100, "href"),
        (r"cookiepolicy", 100, "href"),
        (r"cookies[-_]?policy", 100, "href"),
        (r"cookie[-_]?notice", 90, "href"),
        (r"cookie[-_]?statement", 90, "href"),
        (r"cookie[-_]?information", 85, "href"),
        (r"about[-_]?cookies", 85, "href"),
        (r"use[-_]?of[-_]?cookies", 90, "href"),
        (r"how[-_]?we[-_]?use[-_]?cookies", 85, "href"),
        (r"tracking[-_]?technologies", 80, "href"),
        (r"/cookies(?:/|$|\?|#)", 85, "href"),
        (r"/cookie(?:/|$|\?|#)", 80, "href"),
        (r"legal/cookie", 95, "href"),
        (r"policies/cookie", 95, "href"),
        (r"cookie policy", 95, "label"),
        (r"cookies policy", 95, "label"),
        (r"cookie notice", 85, "label"),
        (r"cookie information", 80, "label"),
        (r"about cookies", 80, "label"),
        (r"use of cookies", 85, "label"),
        (r"how we use cookies", 85, "label"),
        (r"tracking technologies", 75, "label"),
    ],
}

# Penalize links that look like auth/account flows, tools, or marketing — not legal pages
_POLICY_LINK_EXCLUDES = re.compile(
    r"(login|signin|sign-in|signup|sign-up|register|account|checkout|cart|"
    r"newsletter|subscribe|career|job|blog|support|help(?!.*policy)|faq|"
    r"generator|checker|builder|template|pricing|features)",
    re.IGNORECASE,
)


def _score_policy_anchor(
    policy_type: str,
    href_blob: str,
    label_blob: str,
    in_footer: bool,
) -> int:
    score = 0
    href_slug = href_blob.replace(" ", "")

    for pattern, weight, match_on in _POLICY_PATTERNS[policy_type]:
        if match_on == "href":
            matched = (
                re.search(pattern, href_slug, re.IGNORECASE)
                or re.search(pattern, href_blob, re.IGNORECASE)
            )
        else:
            matched = re.search(pattern, label_blob, re.IGNORECASE)
        if matched:
            score = max(score, weight)

    if score <= 0:
        return 0

    if _POLICY_LINK_EXCLUDES.search(href_blob) or _POLICY_LINK_EXCLUDES.search(label_blob):
        score -= 40

    if in_footer:
        score += 10

    return score


def _iter_policy_anchors(soup: BeautifulSoup):
    """Yield anchors with footer/legal section priority."""
    footer_anchors: list = []
    legal_anchors: list = []
    other_anchors: list = []

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        in_footer = False
        in_legal = False
        for parent in anchor.parents:
            if parent.name == "footer":
                in_footer = True
                break
            parent_class = " ".join(parent.get("class") or []).lower()
            parent_id = (parent.get("id") or "").lower()
            legal_markers = ("legal", "policy", "policies", "compliance", "privacy", "footer")
            if any(marker in parent_class or marker in parent_id for marker in legal_markers):
                in_legal = True
                break

        if in_footer:
            footer_anchors.append((anchor, True))
        elif in_legal:
            legal_anchors.append((anchor, False))
        else:
            other_anchors.append((anchor, False))

    yield from footer_anchors
    yield from legal_anchors
    yield from other_anchors


def find_policy_links(soup: BeautifulSoup, base_url: str) -> dict[str, Optional[str]]:
    """
    Find links to privacy policy, terms of service, and cookie policy pages.

    Uses scored pattern matching on href paths and link labels, prioritizing
    footer and legal sections to reduce misses and false positives.

    Args:
        soup: BeautifulSoup object of the homepage.
        base_url: Base URL for resolving relative links.

    Returns:
        dict: Keys are 'privacy', 'terms', 'cookie'. Values are absolute URLs or None.
    """
    links: dict[str, Optional[str]] = {
        "privacy": None,
        "terms": None,
        "cookie": None,
    }
    best_scores = {key: 0 for key in links}

    for anchor, in_footer in _iter_policy_anchors(soup):
        href_blob, label_blob = _anchor_match_blob(anchor)
        if not href_blob and not label_blob:
            continue

        for policy_type in links:
            score = _score_policy_anchor(policy_type, href_blob, label_blob, in_footer)
            if score > best_scores[policy_type]:
                absolute_url = urljoin(base_url, anchor["href"])
                best_scores[policy_type] = score
                links[policy_type] = absolute_url

    for policy_type, url in links.items():
        if url:
            logger.info(
                "Found %s policy link (score=%s): %s",
                policy_type,
                best_scores[policy_type],
                url,
            )

    return links


# ---------------------------------------------------------------------------
# Cookie consent banner detection
# Multi-strategy: known CMPs → broad CSS → consent-button / aria cues →
# visible copy heuristics → iframes → light shadow-DOM pierce (JS).
# ---------------------------------------------------------------------------

_COOKIE_BANNER_CMP_SELECTORS = [
    # OneTrust
    "#onetrust-consent-sdk",
    "#onetrust-banner-sdk",
    ".ot-sdk-container",
    "#onetrust-pc-sdk",
    # Cookiebot
    "#CybotCookiebotDialog",
    "#Cookiebanner",
    ".CookiebotWidget",
    # CookieYes
    ".cky-consent-container",
    "#cky-consent",
    "[class*='cky-consent']",
    "[id*='cky-consent']",
    ".cky-btn-accept",
    # Cookie Law Info / GDPR Cookie Consent (WP)
    "#cookie-law-info-bar",
    "#cliSettingsPopup",
    ".cli-modal",
    # Osano
    ".osano-cm-window",
    ".osano-cm-dialog",
    # Termly
    "#termly-code-snippet-support",
    ".termly-styles",
    "[class*='termly-consent']",
    # Quantcast
    ".qc-cmp2-container",
    "#qc-cmp2-container",
    ".qc-cmp-ui",
    # TrustArc / Truste
    "#truste-consent-track",
    ".truste_box_overlay",
    "#consent_blackbar",
    # Usercentrics
    "#usercentrics-root",
    "[id*='usercentrics']",
    # Didomi
    "#didomi-host",
    ".didomi-notice",
    "#didomi-popup",
    # Iubenda
    "#iubenda-cs-banner",
    ".iubenda-cs-container",
    # Complianz
    "#cmplz-cookiebanner-container",
    ".cmplz-cookiebanner",
    ".cc-window",
    # Borlabs
    "#BorlabsCookieBox",
    ".BorlabsCookie",
    # ConsentManager / Sourcepoint-ish
    "#cmpbox",
    ".sp_veil",
    "#sp_message_container",
    "[id*='sp_message']",
    # Axeptio / HubSpot / others
    "#axeptio_overlay",
    "#hs-eu-cookie-confirmation",
    "#hs-banner-parent",
    ".js-cookie-consent",
    ".cc-banner",
    ".cc-revoke",
    "#moove_gdpr_cookie_info_bar",
    ".gdpr-cookie-notice",
    "#gdpr-cookie-message",
    ".cookie-consent",
    "#cookie-notice",
    ".cookie-notification",
    ".cookie-banner",
    "#cookie-banner",
    ".cookies-banner",
    "#cookies-banner",
    ".consent-banner",
    "#consent-banner",
]

_COOKIE_BANNER_BROAD_SELECTORS = [
    "[id*='cookie'][class*='banner']",
    "[id*='cookie'][class*='consent']",
    "[class*='cookie'][class*='banner']",
    "[class*='cookie'][class*='consent']",
    "[class*='cookie-banner']",
    "[class*='cookie_banner']",
    "[class*='cookieconsent']",
    "[class*='CookieConsent']",
    "[aria-label*='cookie' i]",
    "[aria-label*='consent' i]",
    "[aria-describedby*='cookie' i]",
]

_CONSENT_BUTTON_XPATH = (
    "//*[self::button or self::a or @role='button']"
    "[contains(translate(normalize-space(.),"
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')"
    " or contains(translate(normalize-space(.),"
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'reject')"
    " or contains(translate(normalize-space(.),"
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'decline')"
    " or contains(translate(normalize-space(.),"
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'allow cookie')"
    " or contains(translate(normalize-space(.),"
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'manage cookie')"
    " or contains(translate(normalize-space(.),"
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cookie setting')"
    " or contains(translate(normalize-space(.),"
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'preferenc')"
    "]"
)

_BANNER_COPY_RE = re.compile(
    r"(we\s+use\s+cookies|"
    r"this\s+(?:website|site)\s+uses?\s+cookies|"
    r"cookies?\s+(?:help|help\s+us|are\s+used)|"
    r"accept\s+(?:all\s+)?cookies?|"
    r"manage\s+(?:cookie|consent)\s+preferences|"
    r"cookie\s+(?:preferences|settings|consent|notice|policy)|"
    r"privacy\s+preferences|"
    r"by\s+clicking\s+(?:['\"]?accept|['\"]?agree)|"
    r"consent\s+to\s+(?:the\s+)?(?:use\s+of\s+)?cookies)",
    re.IGNORECASE,
)

# In-page JS: scan light DOM + open shadow roots for consent copy on
# fixed/sticky overlays (catches custom / shadow-wrapped CMPs).
_SHADOW_CONSENT_JS = r"""
const phrases = [
  /we use cookies/i,
  /this (?:website|site) uses? cookies/i,
  /accept(?: all)? cookies/i,
  /manage (?:cookie|consent) preferences/i,
  /cookie (?:preferences|settings|consent|notice)/i,
  /privacy preferences/i,
  /consent to (?:the )?use of cookies/i,
];
function visible(el) {
  if (!el || el.nodeType !== 1) return false;
  const s = window.getComputedStyle(el);
  if (!s || s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) return false;
  const r = el.getBoundingClientRect();
  return r.width > 40 && r.height > 20;
}
function isOverlayish(el) {
  const s = window.getComputedStyle(el);
  if (!s) return false;
  const pos = s.position;
  if (pos === 'fixed' || pos === 'sticky') return true;
  const z = parseInt(s.zIndex || '0', 10);
  return Number.isFinite(z) && z >= 1000;
}
function textOf(el) {
  return (el.innerText || el.textContent || '').slice(0, 1200);
}
function matchPhrases(text) {
  return phrases.some((re) => re.test(text));
}
function walk(root, depth) {
  if (!root || depth > 6) return false;
  const nodes = root.querySelectorAll ? root.querySelectorAll('*') : [];
  for (const el of nodes) {
    if (el.shadowRoot && walk(el.shadowRoot, depth + 1)) return true;
    if (!visible(el)) continue;
    if (!(isOverlayish(el) || el.getAttribute('role') === 'dialog' || el.getAttribute('aria-modal') === 'true')) {
      continue;
    }
    if (matchPhrases(textOf(el))) return true;
  }
  return false;
}
return walk(document, 0);
"""


def _element_is_visible(element) -> bool:
    try:
        return bool(element.is_displayed())
    except Exception:
        return False


def _any_visible(driver, css_selector: str) -> bool:
    try:
        for element in driver.find_elements(By.CSS_SELECTOR, css_selector):
            if _element_is_visible(element):
                return True
    except Exception:
        return False
    return False


def _detect_via_consent_controls(driver) -> bool:
    """True if a visible Accept/Reject/Preferences control sits inside cookie-ish copy."""
    try:
        buttons = driver.find_elements(By.XPATH, _CONSENT_BUTTON_XPATH)
    except Exception:
        return False

    for button in buttons[:40]:
        if not _element_is_visible(button):
            continue
        try:
            # Walk up a few ancestors looking for banner-like consent copy.
            ancestor = button
            for _ in range(6):
                ancestor = ancestor.find_element(By.XPATH, "..")
                text = (ancestor.text or "")[:1500]
                if _BANNER_COPY_RE.search(text):
                    return True
                # Also credit known floating dialog roles.
                role = (ancestor.get_attribute("role") or "").lower()
                aria_modal = (ancestor.get_attribute("aria-modal") or "").lower()
                if role == "dialog" or aria_modal == "true":
                    lower = text.lower()
                    if "cookie" in lower or "consent" in lower or "preferenc" in lower:
                        return True
        except Exception:
            continue
    return False


def _detect_via_visible_banner_copy(driver) -> bool:
    """Scan fixed/sticky / dialog-ish nodes for classic consent copy."""
    try:
        candidates = driver.find_elements(
            By.CSS_SELECTOR,
            "[role='dialog'], [aria-modal='true'], body > div, body > section, body > aside",
        )
    except Exception:
        return False

    checked = 0
    for el in candidates:
        if checked >= 80:
            break
        if not _element_is_visible(el):
            continue
        checked += 1
        try:
            # Prefer overlays — avoid matching footer "cookie policy" links alone.
            position = (el.value_of_css_property("position") or "").lower()
            z_raw = el.value_of_css_property("z-index") or "0"
            try:
                z_index = int(float(z_raw))
            except ValueError:
                z_index = 0
            role = (el.get_attribute("role") or "").lower()
            aria_modal = (el.get_attribute("aria-modal") or "").lower()
            overlayish = (
                position in ("fixed", "sticky")
                or z_index >= 1000
                or role == "dialog"
                or aria_modal == "true"
            )
            if not overlayish:
                continue
            text = (el.text or "")[:1500]
            if _BANNER_COPY_RE.search(text):
                return True
        except Exception:
            continue
    return False


def _detect_via_iframes(driver) -> bool:
    """Some CMPs mount consent UI inside iframes (TrustArc, etc.)."""
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe")
    except Exception:
        return False

    for frame in frames[:12]:
        if not _element_is_visible(frame):
            # Hidden iframes may still host the banner once switched — still try a few.
            src = (frame.get_attribute("src") or "").lower()
            name = (frame.get_attribute("name") or "").lower()
            title = (frame.get_attribute("title") or "").lower()
            hint = f"{src} {name} {title}"
            if not any(k in hint for k in ("cookie", "consent", "trust", "cmp", "privacy")):
                continue
        try:
            driver.switch_to.frame(frame)
        except Exception:
            continue
        try:
            for selector in _COOKIE_BANNER_CMP_SELECTORS[:25]:
                if _any_visible(driver, selector):
                    return True
            if _detect_via_consent_controls(driver) or _detect_via_visible_banner_copy(driver):
                return True
            body_text = ""
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text or ""
            except Exception:
                pass
            if _BANNER_COPY_RE.search(body_text[:2000]):
                return True
        finally:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
    return False


def _detect_via_shadow_dom(driver) -> bool:
    try:
        return bool(driver.execute_script(_SHADOW_CONSENT_JS))
    except Exception:
        return False


def detect_cookie_banner_selenium(driver, settle_seconds: float = 2.0) -> bool:
    """
    Detect a cookie / consent banner using stacked heuristics.

    Returns True on the first successful strategy so paid scans do not miss
    common CMPs (CookieYes, OneTrust, Cookiebot, etc.) or custom overlays.
    """
    try:
        if settle_seconds > 0:
            time.sleep(settle_seconds)

        for selector in _COOKIE_BANNER_CMP_SELECTORS:
            if _any_visible(driver, selector):
                logger.info("Cookie banner detected with CMP selector: %s", selector)
                return True

        for selector in _COOKIE_BANNER_BROAD_SELECTORS:
            if _any_visible(driver, selector):
                logger.info("Cookie banner detected with broad selector: %s", selector)
                return True

        if _detect_via_consent_controls(driver):
            logger.info("Cookie banner detected via consent controls + copy")
            return True

        if _detect_via_visible_banner_copy(driver):
            logger.info("Cookie banner detected via visible overlay copy")
            return True

        if _detect_via_iframes(driver):
            logger.info("Cookie banner detected inside iframe")
            return True

        if _detect_via_shadow_dom(driver):
            logger.info("Cookie banner detected via shadow DOM / JS scan")
            return True

        logger.info("No cookie banner detected.")
        return False
    except Exception as e:
        logger.error("Error during cookie banner detection: %s", e)
        return False


def find_grievance_officer_contact(text: str) -> Optional[str]:
    """
    Search for grievance officer contact details (email or phone) near the phrase "grievance officer".
    
    Args:
        text: Policy text to search.
    
    Returns:
        str or None: Contact detail if found, else None.
    """
    text_lower = text.lower()
    pattern = re.compile(r'grievance\s+officer', re.IGNORECASE)
    
    match = pattern.search(text)
    if not match:
        return None
    
    # Extract 200 characters around the match
    start = max(0, match.start() - 100)
    end = min(len(text), match.end() + 100)
    snippet = text[start:end]
    
    # Look for email
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    email_match = re.search(email_pattern, snippet)
    if email_match:
        return email_match.group(0)
    
    # Look for phone number (Indian format)
    phone_pattern = r'\+?\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}'
    phone_match = re.search(phone_pattern, snippet)
    if phone_match:
        return phone_match.group(0)
    
    return None


def chunk_text(text: str, max_tokens: int = 512, overlap: int = 50) -> List[str]:
    """
    Split text into overlapping chunks based on approximate token count.
    
    Args:
        text: Input text to chunk.
        max_tokens: Maximum tokens per chunk (approximate, using word count * 1.3).
        overlap: Number of tokens to overlap between chunks.
    
    Returns:
        List[str]: List of text chunks.
    """
    words = text.split()
    # Rough approximation: 1 word ≈ 1.3 tokens
    max_words = int(max_tokens / 1.3)
    overlap_words = int(overlap / 1.3)
    
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i:i + max_words]
        chunks.append(' '.join(chunk_words))
        i += max_words - overlap_words
        
        # Prevent infinite loop
        if i <= 0:
            i = max_words
    
    logger.info(f"Text split into {len(chunks)} chunks.")
    return chunks
