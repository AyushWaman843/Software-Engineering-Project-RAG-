"""Unit tests for cookie-banner detection helpers (no live browser required)."""

from utils import _BANNER_COPY_RE, _COOKIE_BANNER_CMP_SELECTORS


class TestBannerCopyRegex:
    def test_matches_common_phrases(self):
        phrases = [
            "We use cookies to improve your experience.",
            "This website uses cookies.",
            "Accept all cookies",
            "Manage cookie preferences",
            "Cookie consent notice",
            "By clicking Accept you agree to our cookies",
            "Consent to the use of cookies",
        ]
        for phrase in phrases:
            assert _BANNER_COPY_RE.search(phrase), phrase

    def test_ignores_unrelated_footer_text(self):
        assert not _BANNER_COPY_RE.search("Welcome to our homepage")
        assert not _BANNER_COPY_RE.search("Contact us for support")
        assert _BANNER_COPY_RE.search("Read our Cookie Policy for details")


class TestCmpSelectorCoverage:
    def test_includes_major_cmps(self):
        blob = " ".join(_COOKIE_BANNER_CMP_SELECTORS)
        for token in (
            "onetrust",
            "Cookiebot",
            "cky-consent",
            "osano",
            "qc-cmp",
            "usercentrics",
            "didomi",
            "iubenda",
            "cmplz",
            "Borlabs",
        ):
            assert token.lower() in blob.lower(), token
