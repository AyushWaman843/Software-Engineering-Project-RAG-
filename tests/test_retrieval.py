"""Tests for retrieval.py: chunking, indicator retrieval, evidence selection, excerpt location."""

import re
import time
from pathlib import Path

import pytest

import retrieval
from retrieval import (
    ADDITIONAL_CONTEXT_MARKER,
    INDICATOR_PROFILES,
    MAX_OVERLAP_CHARS,
    MIN_ENGLISH_SHARE,
    RETRIEVAL_INDICATORS,
    EvidenceRetriever,
    TextLocator,
    chunk_text_with_offsets,
    english_share,
    format_passages,
    normalize_with_map,
    select_evidence,
    sentence_spans,
    split_documents,
    tokenize,
)

RULES_PATH = Path(__file__).resolve().parent.parent / "dpdp_rules.txt"


def _sentences(text):
    return [text[s:e] for s, e in sentence_spans(text)]


class TestSentenceSpans:
    def test_splits_flat_text(self):
        text = "We collect data. We use it to serve you! Do you agree? Yes."
        assert _sentences(text) == [
            "We collect data.",
            "We use it to serve you!",
            "Do you agree?",
            "Yes.",
        ]

    def test_does_not_split_on_abbreviations(self):
        text = "Acme Pvt. Ltd. is the fiduciary. Dr. Rao is our officer, e.g. for complaints."
        assert _sentences(text) == [
            "Acme Pvt. Ltd. is the fiduciary.",
            "Dr. Rao is our officer, e.g. for complaints.",
        ]

    def test_does_not_split_on_initials(self):
        text = "Contact A. K. Sharma for help. He replies quickly."
        assert _sentences(text) == ["Contact A. K. Sharma for help.", "He replies quickly."]

    def test_newline_ends_sentence(self):
        text = "Privacy Policy\nWe collect data\nWe share data."
        assert _sentences(text) == ["Privacy Policy", "We collect data", "We share data."]

    def test_text_without_terminal_punctuation(self):
        assert _sentences("  no punctuation here  ") == ["no punctuation here"]

    def test_empty(self):
        assert sentence_spans("") == []
        assert sentence_spans("   \n ") == []

    def test_sentence_ending_in_an_email_or_url_still_splits(self):
        text = "Write to dpo@example.in. We reply within 90 days. See https://example.com/privacy. Thank you."
        assert _sentences(text) == [
            "Write to dpo@example.in.",
            "We reply within 90 days.",
            "See https://example.com/privacy.",
            "Thank you.",
        ]

    def test_dotted_abbreviations_do_not_split(self):
        text = "Use a service, e.g. Google Drive. It is used in the U.S. Market data is not shared."
        assert _sentences(text) == [
            "Use a service, e.g. Google Drive.",
            "It is used in the U.S. Market data is not shared.",
        ]


class TestChunking:
    def _doc(self, n=80):
        return " ".join(
            f"Sentence number {i} explains how we handle your personal data for purpose {i}."
            for i in range(n)
        )

    def test_chunks_are_exact_slices(self):
        text = self._doc()
        chunks = chunk_text_with_offsets(text, "privacy", max_chars=400)
        assert len(chunks) > 5
        for chunk in chunks:
            assert chunk.text == text[chunk.start:chunk.end]
            assert chunk.source == "privacy"

    def test_every_sentence_is_covered(self):
        text = self._doc()
        chunks = chunk_text_with_offsets(text, "privacy", max_chars=400)
        for start, end in sentence_spans(text):
            assert any(c.start <= start and end <= c.end for c in chunks), text[start:end]

    def test_chunk_size_is_bounded(self):
        text = self._doc()
        for chunk in chunk_text_with_offsets(text, max_chars=400):
            assert len(chunk.text) <= 400 + MAX_OVERLAP_CHARS

    def test_consecutive_chunks_overlap_by_a_sentence(self):
        chunks = chunk_text_with_offsets(self._doc(), max_chars=400, overlap_sentences=1)
        assert all(a.end > b.start for a, b in zip(chunks, chunks[1:]))

    def test_no_overlap_when_disabled(self):
        chunks = chunk_text_with_offsets(self._doc(), max_chars=400, overlap_sentences=0)
        assert all(a.end <= b.start for a, b in zip(chunks, chunks[1:]))

    def test_unpunctuated_run_is_hard_wrapped(self):
        text = " ".join(["menu"] * 1000)
        chunks = chunk_text_with_offsets(text, max_chars=300)
        assert len(chunks) > 10
        assert all(len(c.text) <= 300 + MAX_OVERLAP_CHARS for c in chunks)
        assert all(c.text == text[c.start:c.end] for c in chunks)

    def test_ids_and_indexes_are_sequential(self):
        chunks = chunk_text_with_offsets(self._doc(), "terms", max_chars=400)
        assert [c.index for c in chunks] == list(range(len(chunks)))
        assert chunks[0].id == "terms-0"

    def test_empty_text(self):
        assert chunk_text_with_offsets("") == []
        assert chunk_text_with_offsets("   ") == []


class TestNormalizeWithMap:
    def test_maps_back_to_source_characters(self):
        text = "We \u201ccollect\u201d  your\n\tData \u2014 safely."
        norm, origin = normalize_with_map(text)
        assert norm == 'we "collect" your data - safely.'
        assert len(norm) == len(origin)
        for ch, idx in zip(norm, origin):
            if ch != " ":
                assert text[idx].lower() in (ch, "\u201c", "\u201d", "\u2014")

    def test_trims_edges_and_collapses_whitespace(self):
        assert normalize_with_map("  a \n b  ")[0] == "a b"


class TestTokenize:
    def test_stems_align_across_forms(self):
        assert tokenize("retained") == tokenize("retain")
        assert tokenize("rights") == tokenize("right")
        assert tokenize("purposes") == tokenize("purpose")
        assert tokenize("queries") == tokenize("query")

    def test_drops_stopwords_and_keeps_numbers(self):
        assert tokenize("the age of 18") == ["age", "18"]


class TestTextLocator:
    POLICY = (
        "Privacy Policy. We collect your name and email address when you register. "
        "You may withdraw your consent at any time by writing to our Grievance Officer. "
        "We retain personal data for three years after your last interaction."
    )

    def test_exact_match_is_returned_verbatim(self):
        match = TextLocator(self.POLICY).find("We collect your name and email address when you register.")
        assert match and match.exact
        assert match.text == "We collect your name and email address when you register."

    def test_a_quote_without_its_final_period_matches_without_it(self):
        match = TextLocator(self.POLICY).find("We collect your name and email address when you register")
        assert match and match.exact
        assert match.text == "We collect your name and email address when you register"

    def test_closing_punctuation_is_only_added_when_the_source_has_it(self):
        locator = TextLocator("You may withdraw your consent at any time, by writing to us.")
        match = locator.find("You may withdraw your consent at any time.")
        assert match and match.text == "You may withdraw your consent at any time"
        closing_quote = TextLocator('The notice says "we retain data for a year." Then more text follows.')
        match = closing_quote.find('we retain data for a year."')
        assert match and match.text == 'we retain data for a year."'

    def test_a_trailing_ellipsis_is_not_mistaken_for_closing_punctuation(self):
        locator = TextLocator("You may withdraw your consent at any time... but see the terms. Another sentence.")
        match = locator.find("You may withdraw your consent at any time...")
        assert match and match.text == "You may withdraw your consent at any time"

    def test_tolerates_case_whitespace_and_quote_style(self):
        policy = "You may \u201cwithdraw\u201d your   consent\nat any time."
        match = TextLocator(policy).find('you may "withdraw" your consent at any time')
        assert match and match.exact
        assert match.text == policy[:-1]

    def test_returns_original_casing(self):
        match = TextLocator(self.POLICY).find("contact our GRIEVANCE OFFICER".replace("contact our", "writing to our"))
        assert match and "Grievance Officer" in match.text

    def test_tolerates_ellipsis_and_trailing_period(self):
        match = TextLocator(self.POLICY).find("...withdraw your consent at any time...")
        assert match and match.exact

    def test_fuzzy_match_for_lightly_reworded_quote(self):
        quote = "We retain your personal data for three years after your last interaction with us."
        match = TextLocator(self.POLICY).find(quote)
        assert match and not match.exact
        assert match.text == "We retain personal data for three years after your last interaction."

    def test_fabricated_quote_is_rejected(self):
        quote = "We never sell personal data and delete everything within thirty days of a request."
        assert TextLocator(self.POLICY).find(quote) is None

    def test_unrelated_text_is_rejected(self):
        assert TextLocator(self.POLICY).find("The quick brown fox jumps over the lazy dog today") is None

    def test_empty_inputs(self):
        assert TextLocator("").find("anything here") is None
        assert TextLocator(self.POLICY).find("") is None

    def test_fast_on_large_text_with_unmatched_excerpts(self):
        big = " ".join(
            f"Paragraph {i} describes cookies, analytics and security safeguards for visitors."
            for i in range(4000)
        )
        locator = TextLocator(big)
        started = time.perf_counter()
        for i in range(9):
            assert locator.find(f"We promise never to disclose anything, ever, number {i}, to anyone at all.") is None
        assert time.perf_counter() - started < 5.0


# ---------------------------------------------------------------------------
# Retrieval quality
# ---------------------------------------------------------------------------

FILLER = [
    "We use cookies and similar technologies to remember your preferences, measure how our website performs and show relevant advertising. You can change your browser settings to refuse cookies, although some features may stop working.",
    "Our website and mobile application may contain links to third-party websites. We are not responsible for the content or privacy practices of those sites and encourage you to read their policies.",
    "We protect information using industry-standard safeguards such as encryption in transit, access controls, regular security testing and staff training. No method of transmission over the internet is completely secure.",
    "When you place an order we share your delivery address and phone number with our logistics partners so that they can deliver your package. Payment details are handled by our payment gateway and are never stored on our servers.",
    "We may send you promotional emails and text messages about new products and offers. You can unsubscribe at any time by clicking the link in the message. We may contact you by email or phone about your orders.",
    "Our service records technical information such as your IP address, browser type, device model, operating system and the pages you visit, to diagnose problems and improve performance.",
    "If you post reviews, comments or photographs on our platform, that content may be visible to other users. Please avoid posting information that you do not want others to see.",
    "We may update this policy from time to time to reflect changes in our practices or legal requirements. The date at the top of the page shows when it was last revised.",
    "If you apply for a role with us we use your resume and interview notes to evaluate your application and to communicate with you about the hiring process.",
    "We keep records of invoices and payments for tax and accounting reasons and to resolve disputes about transactions.",
    "Our customer support team uses chat transcripts and call recordings for quality assurance and training. Calls may be recorded for these purposes.",
    "Location information from your device helps us show nearby stores and estimate delivery times. You can turn off location sharing in your device settings.",
    "We use analytics providers to understand how visitors use our site. These providers may set their own cookies and receive aggregated usage statistics.",
    "We may disclose information to courts, law enforcement or regulators when required by applicable law or to protect our rights and safety.",
]

GOLD = {
    "notice_consent_purpose": "Before we collect any personal data we give you a notice that lists the data we collect, the specific purposes for which it is used, and how you can withdraw your consent at any time as easily as you gave it.",
    "data_principal_rights": "You have the right to access your personal data, the right to correct inaccurate data, the right to erase data we no longer need, and the right to nominate another person to exercise these rights on your behalf.",
    "grievance_officer_contact": "Our Grievance Officer, Ms. Anita Rao, can be reached at grievance@example.in or +91 80 4000 1234, and we resolve complaints within 90 days.",
    "parental_consent_children": "We do not knowingly collect personal data of anyone under the age of 18 unless we first obtain verifiable consent from a parent or legal guardian.",
    "consent_manager_mentioned": "You may manage your consent preferences through a Consent Manager registered with the Data Protection Board of India.",
    "cross_border_transfer": "Your personal data may be transferred outside the territory of India to our cloud hosting partners in Singapore, subject to contractual safeguards.",
    "data_retention_period": "We retain personal data for three years after your last interaction with us, after which it is permanently erased unless the law requires us to keep it longer.",
    "dpdp_act_reference": "This policy is published to comply with the Digital Personal Data Protection Act, 2023 and the Digital Personal Data Protection Rules, 2025.",
}

# A privacy policy in Hindi: none of the English indicator vocabulary appears in it.
HINDI_POLICY = (
    "\u0917\u094b\u092a\u0928\u0940\u092f\u0924\u093e \u0928\u0940\u0924\u093f\u0964 "
    "\u0939\u092e \u0906\u092a\u0915\u093e \u0935\u094d\u092f\u0915\u094d\u0924\u093f\u0917\u0924 "
    "\u0921\u0947\u091f\u093e \u0938\u0941\u0930\u0915\u094d\u0937\u093f\u0924 \u0930\u0916\u0924\u0947 "
    "\u0939\u0948\u0902 \u0914\u0930 \u0906\u092a\u0915\u0940 \u0938\u0939\u092e\u0924\u093f \u0915\u0947 "
    "\u092c\u093f\u0928\u093e \u0938\u093e\u091d\u093e \u0928\u0939\u0940\u0902 \u0915\u0930\u0924\u0947\u0964 "
)


def build_long_policy(cycles=22):
    paragraphs = []
    for cycle in range(cycles):
        for number, text in enumerate(FILLER):
            paragraphs.append(f"{cycle + 1}.{number + 1} {text}")
    gold_positions = {
        key: int(len(paragraphs) * fraction)
        for key, fraction in zip(GOLD, (0.08, 0.2, 0.33, 0.47, 0.6, 0.72, 0.85, 0.93))
    }
    for key, position in sorted(gold_positions.items(), key=lambda kv: -kv[1]):
        paragraphs.insert(position, GOLD[key])
    return " ".join(paragraphs)


@pytest.fixture(scope="module")
def long_policy():
    return build_long_policy()


@pytest.fixture(scope="module")
def long_retriever(long_policy):
    return EvidenceRetriever({"privacy": long_policy})


class TestIndicatorRetrieval:
    def test_policy_is_actually_long(self, long_policy):
        assert len(long_policy) > 50_000

    @pytest.mark.parametrize("key", list(GOLD))
    def test_gold_passage_ranks_in_top_three(self, long_retriever, key):
        hits = long_retriever.search(key, top_k=3)
        assert any(GOLD[key] in hit.chunk.text for hit in hits), (
            key,
            [round(h.score, 2) for h in hits],
        )

    @pytest.mark.parametrize("key", list(GOLD))
    def test_gold_passage_ranks_first_for_distinctive_indicators(self, long_retriever, key):
        hits = long_retriever.search(key, top_k=1)
        assert hits and GOLD[key] in hits[0].chunk.text

    def test_every_gate_indicator_has_a_profile(self):
        from compliance_checker import KEYWORD_GATES

        assert set(KEYWORD_GATES) <= set(INDICATOR_PROFILES)

    def test_best_sentence_is_verbatim_and_relevant(self, long_retriever, long_policy):
        sentence = long_retriever.best_sentence("grievance_officer_contact")
        assert sentence in long_policy
        assert "Grievance Officer" in sentence

    @pytest.mark.parametrize("key", list(GOLD))
    def test_best_sentence_finds_the_gold_sentence_when_the_text_states_it(self, long_retriever, key):
        assert long_retriever.best_sentence(key) == GOLD[key]


class TestBestSentencePrecision:
    """A sentence stands in for a missing quote only when it is real evidence, not a look-alike."""

    @staticmethod
    def best(text, key):
        return EvidenceRetriever({"privacy": text}).best_sentence(key)

    @pytest.mark.parametrize(
        ("key", "text"),
        [
            ("data_principal_rights", "Security We use access controls and regular audits to protect the information we hold."),
            ("data_principal_rights", "The principal of a partner school can nominate a coordinator who places bulk orders on its behalf."),
            ("parental_consent_children", "Parents can use the parental controls in the app to filter content on a shared tablet."),
            ("consent_manager_mentioned", "We ask for your consent before we send marketing messages."),
        ],
    )
    def test_look_alike_sentences_are_not_offered_as_evidence(self, key, text):
        assert self.best(text, key) == ""

    @pytest.mark.parametrize(
        ("key", "text"),
        [
            ("data_principal_rights", "You can access, correct or delete the personal data we hold about you."),
            ("data_principal_rights", "You have the right to correct and erase your data."),
            ("parental_consent_children", "We do not knowingly collect data from children without the consent of a parent."),
            ("data_retention_period", "We retain personal data for three years after your last interaction."),
        ],
    )
    def test_real_statements_are_still_offered(self, key, text):
        assert self.best(text, key) == text

    def test_data_action_pattern_needs_the_verb_close_to_the_data(self):
        pattern = retrieval._RIGHTS_DATA_ACTION_RE
        assert pattern.search("You may download your data at any time.")
        assert pattern.search("Request access to the personal data we hold about you.")
        assert not pattern.search("We use access controls and regular audits to protect the information we hold.")

    def test_absent_indicator_yields_no_confident_hit(self):
        policy = " ".join(f"{i}. {FILLER[i % len(FILLER)]}" for i in range(60))
        retriever = EvidenceRetriever({"privacy": policy})
        for hit in retriever.search("consent_manager_mentioned"):
            assert "consent manager" not in hit.chunk.text.lower()

    def test_unknown_indicator_and_empty_index(self, long_retriever):
        assert long_retriever.search("not_an_indicator") == []
        assert EvidenceRetriever({}).search("data_principal_rights") == []


class TestEvidenceSelection:
    def test_gold_passages_survive_selection_within_budget(self, long_retriever, long_policy):
        selection = select_evidence(long_retriever, budget_chars=16_000)
        shown = " ".join(p.text for p in selection.passages["privacy"])
        for key, gold in GOLD.items():
            assert gold in shown, key
        assert selection.chars_selected <= 16_000
        assert selection.chars_selected < len(long_policy) * 0.35
        assert selection.chunks_selected < selection.chunks_total

    def test_per_indicator_ids_point_at_selected_chunks(self, long_retriever):
        selection = select_evidence(long_retriever)
        selected_ids = {cid for p in selection.passages["privacy"] for cid in p.chunk_ids}
        for key in RETRIEVAL_INDICATORS:
            assert selection.per_indicator[key], key
            assert set(selection.per_indicator[key]) <= selected_ids

    def test_passages_are_in_document_order_and_non_overlapping(self, long_retriever):
        passages = select_evidence(long_retriever).passages["privacy"]
        assert all(a.end < b.start for a, b in zip(passages, passages[1:]))

    def test_passage_text_is_verbatim_slice(self, long_retriever, long_policy):
        for passage in select_evidence(long_retriever).passages["privacy"]:
            assert passage.text == long_policy[passage.start:passage.end]

    def test_head_and_tail_of_each_document_are_included(self, long_retriever, long_policy):
        passages = select_evidence(long_retriever).passages["privacy"]
        assert passages[0].start == 0
        assert passages[-1].end == len(long_policy)

    def test_tiny_budget_is_respected(self, long_retriever):
        selection = select_evidence(long_retriever, budget_chars=2_500)
        assert selection.chars_selected <= 2_500

    def test_format_passages_headers(self, long_retriever):
        selection = select_evidence(long_retriever)
        rendered = format_passages(selection.passages["privacy"])
        assert rendered.startswith("[Passage 1 | privacy policy | characters 0-")
        assert rendered.count("[Passage ") == len(selection.passages["privacy"])

    def test_multiple_sources_are_kept_separate(self, long_policy):
        terms = "Terms of Service. " + GOLD["grievance_officer_contact"] + " " + " ".join(FILLER * 6)
        retriever = EvidenceRetriever({"privacy": long_policy, "terms": terms})
        selection = select_evidence(retriever)
        assert set(selection.passages) == {"privacy", "terms"}
        assert all(p.source == "terms" for p in selection.passages["terms"])


class TestSupport:
    """Vocabulary-level backing for an indicator; must not depend on how long the document is."""

    @staticmethod
    def support(text, key):
        return EvidenceRetriever({"privacy": text}).support(key)

    def test_strong_when_a_statutory_phrase_is_present(self):
        assert self.support("We appoint a Grievance Officer for complaints.", "grievance_officer_contact") == "strong"
        assert self.support("Data is kept for three years.", "data_retention_period") == "weak"
        assert self.support("We retain personal data for three years.", "data_retention_period") == "strong"

    def test_weak_with_vocabulary_only(self):
        assert self.support("You can contact us with any questions.", "grievance_officer_contact") == "weak"

    def test_loose_wording_is_still_supported_on_a_tiny_document(self):
        assert self.support("We store your data until you close your account.", "data_retention_period") == "weak"
        assert self.support("Our servers are hosted by a cloud provider.", "cross_border_transfer") == "weak"
        assert self.support("Our servers are hosted in the United States.", "cross_border_transfer") == "strong"

    def test_none_when_the_text_is_unrelated(self):
        text = "We use cookies to remember your preferences."
        for key in ("consent_manager_mentioned", "cross_border_transfer", "parental_consent_children"):
            assert self.support(text, key) == "none", key

    def test_a_common_word_alone_is_not_enough_for_strict_indicators(self):
        text = "We ask for your consent before collecting data, and we comply with the law."
        assert self.support(text, "consent_manager_mentioned") == "none"
        assert self.support(text, "dpdp_act_reference") == "none"
        assert self.support("Our age limit is stated below.", "parental_consent_children") == "none"

    @pytest.mark.parametrize(
        "sentence",
        [
            "Our service is not available to anyone under 13.",
            "Anyone below the age of 16 needs a guardian's approval.",
            "Users must be at least 16 years of age.",
            "Persons aged 15 or older may register.",
            "Teenagers need a guardian's approval.",
        ],
    )
    def test_children_wording_without_the_word_children_is_supported(self, sentence):
        assert self.support(sentence, "parental_consent_children") != "none"

    @pytest.mark.parametrize(
        "sentence",
        [
            "Inactive accounts are closed in under 15 days.",
            "Refunds are processed in under 5 business days.",
            "We keep these logs for less than 12 months.",
            "Files must be under 10 MB.",
        ],
    )
    def test_numbers_that_are_not_ages_are_not_read_as_age_thresholds(self, sentence):
        assert self.support(sentence, "parental_consent_children") == "none"

    def test_age_thresholds_are_strong_support_for_children(self):
        assert self.support("Our service is not available to anyone under 13.", "parental_consent_children") == "strong"
        assert self.support("Users must be at least 16 years of age.", "parental_consent_children") == "strong"

    def test_cloud_hosting_is_weak_support_for_cross_border(self):
        assert self.support("Everything runs on a cloud platform.", "cross_border_transfer") == "weak"

    def test_an_email_counts_as_support_for_contact_indicators(self):
        assert self.support("Reach us: help@example.com", "grievance_officer_contact") == "weak"

    def test_generic_phrases_do_not_count_as_strong_support(self):
        assert self.support("Contact us at any time. We collect your name.", "grievance_officer_contact") == "weak"
        assert self.support("We collect your name when you register.", "notice_consent_purpose") == "weak"

    def test_generic_phrases_still_help_ranking(self):
        filler = "We use cookies to remember your preferences and measure performance. " * 20
        retriever = EvidenceRetriever({"privacy": filler + "For questions, write to us any time. " + filler})
        top = retriever.search("grievance_officer_contact", top_k=1)
        assert top and "write to us" in top[0].chunk.text

    def test_unknown_indicator_and_empty_document(self):
        assert self.support("anything", "not_an_indicator") == "none"
        assert EvidenceRetriever({}).support("grievance_officer_contact") == "none"

    def test_long_policy_agrees_with_the_gold_passages(self, long_retriever):
        for key in GOLD:
            assert long_retriever.support(key) == "strong", key


class TestEnglishShare:
    """Vocabulary-based features must stand down for text the English profiles cannot read."""

    ENGLISH = (
        "We collect your personal data in accordance with the law and we share it with the "
        "processors that act on our behalf. "
    ) * 3
    FRENCH = (
        "Nous collectons vos donnees personnelles conformement a la loi et nous ne les "
        "partageons pas sans votre consentement. "
    ) * 3
    HINGLISH = "Hum aapka data surakshit rakhte hain aur aapki sahmati ke bina share nahi karte hain or ye hamari niti hai. " * 3

    def test_english_text_scores_high(self):
        assert english_share(self.ENGLISH) > 0.3
        assert EvidenceRetriever({"privacy": self.ENGLISH}).mostly_english

    @pytest.mark.parametrize("text", [FRENCH, HINGLISH, HINDI_POLICY * 5])
    def test_other_languages_score_low(self, text):
        assert english_share(text) < MIN_ENGLISH_SHARE
        assert not EvidenceRetriever({"privacy": text}).mostly_english

    def test_text_too_short_to_judge_counts_as_english(self):
        assert english_share("") == 1.0
        assert english_share("Privacy Policy") == 1.0
        assert english_share("12345 67890") == 1.0

    def test_every_evaluation_fixture_is_english(self):
        for path in sorted((Path(__file__).parent / "fixtures" / "rag_eval").glob("*.txt")):
            assert EvidenceRetriever({"privacy": path.read_text(encoding="utf-8")}).mostly_english, path.name

    def test_the_share_is_reported_in_stats(self):
        stats = EvidenceRetriever({"privacy": self.ENGLISH}).stats()
        assert stats["english_share"] > 0.3


class TestSplitDocuments:
    def test_names_documents(self):
        docs = split_documents("policy body", "terms body")
        assert docs == {"privacy": "policy body", "terms": "terms body"}

    def test_refinement_pages_become_their_own_source(self):
        combined = f"main policy\n\n{ADDITIONAL_CONTEXT_MARKER}\n\nextra page text"
        docs = split_documents(combined)
        assert docs == {"privacy": "main policy", "additional": "extra page text"}

    def test_blank_inputs(self):
        assert split_documents("", "") == {}
        assert split_documents("   ", "  ") == {}


@pytest.fixture(scope="module")
def retriever():
    text = re.sub(r"\s+", " ", RULES_PATH.read_text(encoding="utf-8"))
    return EvidenceRetriever({"rules": text})


class TestRealGazetteRetrieval:
    """The DPDP Rules gazette in the repo is a real, hard long document with known rule locations."""

    def _top_text(self, retriever, key, k):
        return " ".join(h.chunk.text.lower() for h in retriever.search(key, top_k=k))

    def test_indexes_quickly(self):
        text = re.sub(r"\s+", " ", RULES_PATH.read_text(encoding="utf-8"))
        started = time.perf_counter()
        retriever = EvidenceRetriever({"rules": text})
        retriever.search("grievance_officer_contact")
        assert time.perf_counter() - started < 3.0
        assert len(retriever.chunks) > 40

    def test_cross_border_finds_rule_15(self, retriever):
        assert "outside the territory of india" in self._top_text(retriever, "cross_border_transfer", 3)

    def test_children_finds_rule_10(self, retriever):
        top = self._top_text(retriever, "parental_consent_children", 4)
        assert "verifiable consent" in top and "child" in top

    def test_consent_manager_found(self, retriever):
        assert "consent manager" in self._top_text(retriever, "consent_manager_mentioned", 2)

    def test_rights_finds_rule_14(self, retriever):
        top = self._top_text(retriever, "data_principal_rights", 4)
        assert "rights of data principals" in top or "nominate" in top

    def test_contact_finds_rule_9(self, retriever):
        assert "business contact information" in self._top_text(retriever, "grievance_officer_contact", 4)

    def test_notice_finds_rule_3(self, retriever):
        assert "itemised description" in self._top_text(retriever, "notice_consent_purpose", 4)

    def test_retention_finds_rule_8_or_third_schedule(self, retriever):
        top = self._top_text(retriever, "data_retention_period", 5)
        assert "time period for specified purpose" in top or "third schedule" in top
