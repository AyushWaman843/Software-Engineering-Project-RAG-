"""Tests for homepage policy link discovery."""

from bs4 import BeautifulSoup

from utils import find_policy_links


def _find(html: str, base: str = "https://example.com"):
    soup = BeautifulSoup(html, "lxml")
    return find_policy_links(soup, base)


class TestFindPolicyLinks:
    def test_finds_standard_footer_links(self):
        html = """
        <footer>
          <a href="/privacy-policy">Privacy Policy</a>
          <a href="/terms-and-conditions">Terms &amp; Conditions</a>
          <a href="/cookie-policy">Cookie Policy</a>
        </footer>
        """
        links = _find(html)
        assert links["privacy"] == "https://example.com/privacy-policy"
        assert links["terms"] == "https://example.com/terms-and-conditions"
        assert links["cookie"] == "https://example.com/cookie-policy"

    def test_finds_alternate_url_patterns(self):
        html = """
        <div class="legal-links">
          <a href="/legal/privacy-notice">Privacy Notice</a>
          <a href="/legal/terms-of-use">Terms of Use</a>
          <a href="/legal/cookies">About Cookies</a>
        </div>
        """
        links = _find(html)
        assert links["privacy"].endswith("/legal/privacy-notice")
        assert links["terms"].endswith("/legal/terms-of-use")
        assert links["cookie"].endswith("/legal/cookies")

    def test_prefers_footer_over_nav_noise(self):
        html = """
        <nav><a href="/login?terms=1">Login</a></nav>
        <footer>
          <a href="/terms-of-service">Terms of Service</a>
          <a href="/privacy">Privacy</a>
        </footer>
        """
        links = _find(html)
        assert links["terms"] == "https://example.com/terms-of-service"
        assert links["privacy"] == "https://example.com/privacy"

    def test_finds_user_agreement_and_data_protection(self):
        html = """
        <footer>
          <a href="/data-protection-policy">Data Protection</a>
          <a href="/user-agreement">User Agreement</a>
          <a href="/use-of-cookies">Use of Cookies</a>
        </footer>
        """
        links = _find(html)
        assert "data-protection-policy" in links["privacy"]
        assert "user-agreement" in links["terms"]
        assert "use-of-cookies" in links["cookie"]

    def test_uses_title_and_aria_label(self):
        html = """
        <a href="/p" title="Privacy Policy" aria-label="Read our privacy policy">Policy</a>
        <a href="/t" title="Terms of Use">Legal</a>
        <a href="/c" aria-label="Cookie Policy">Cookies</a>
        """
        links = _find(html)
        assert links["privacy"] == "https://example.com/p"
        assert links["terms"] == "https://example.com/t"
        assert links["cookie"] == "https://example.com/c"

    def test_does_not_match_terminal_or_login(self):
        html = """
        <a href="/terminal">Terminal</a>
        <a href="/login">Sign in</a>
        <a href="/blog/terms-of-art">Blog</a>
        """
        links = _find(html)
        assert links["privacy"] is None
        assert links["terms"] is None
        assert links["cookie"] is None

    def test_picks_higher_scored_href_over_weak_text(self):
        html = """
        <a href="/about">Privacy</a>
        <footer><a href="/privacy-policy">Privacy Policy</a></footer>
        """
        links = _find(html)
        assert links["privacy"] == "https://example.com/privacy-policy"
