
"""
Unit tests for the citation formatting module.

Structure
---------
TestReference          – Reference.from_dict / to_csl_json
TestAuthorParsing      – various author string formats
TestCitationFormatterAPA       – APA output vs known-correct examples
TestCitationFormatterVancouver – Vancouver output vs known-correct examples
TestFormatJson         – CitationFormatter.format_json convenience method
TestCrossRefHelpers    – internal helpers (_clean_doi, _parse helpers)
TestReferenceFromDoi   – reference_from_doi with mocked HTTP calls
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

# Download CSL styles once before any test runs
from app.services.citation import ensure_styles

ensure_styles()

from app.services.citation import (
    Author,
    CitationFormatter,
    CitationOutput,
    Reference,
    SUPPORTED_STYLES,
)
from app.services.crossref_client import (
    CrossRefError,
    _clean_doi,
    _reference_from_crossref_message,
    _reference_from_csl_json,
    reference_from_doi,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_SINGLE_AUTHOR_REF = {
    "id": "jones2019",
    "title": "A Survey of Transformer Models",
    "authors": [{"family": "Jones", "given": "Robert B"}],
    "year": 2019,
    "journal": "Nature Machine Intelligence",
    "doi": "10.1038/s42256-019-0001-0",
    "volume": "1",
    "issue": "4",
    "pages": "200-210",
    "type": "article-journal",
}

_TWO_AUTHOR_REF = {
    "id": "smith2020",
    "title": "Deep Learning for Natural Language Processing",
    "authors": [
        {"family": "Smith", "given": "John A"},
        {"family": "Doe", "given": "Jane"},
    ],
    "year": 2020,
    "journal": "Journal of Artificial Intelligence Research",
    "doi": "10.1613/jair.1.11677",
    "volume": "68",
    "issue": "1",
    "pages": "1-50",
    "type": "article-journal",
}

_MANY_AUTHOR_REF = {
    "id": "multi2021",
    "title": "Federated Learning at Scale",
    "authors": [
        {"family": "Alpha", "given": "A"},
        {"family": "Beta", "given": "B"},
        {"family": "Gamma", "given": "C"},
        {"family": "Delta", "given": "D"},
        {"family": "Epsilon", "given": "E"},
        {"family": "Zeta", "given": "F"},
        {"family": "Eta", "given": "G"},
    ],
    "year": 2021,
    "journal": "Communications of the ACM",
    "doi": "10.1145/0000000",
    "volume": "64",
    "issue": "3",
    "pages": "45-55",
    "type": "article-journal",
}

_BOOK_REF = {
    "id": "russell2020",
    "title": "Artificial Intelligence: A Modern Approach",
    "authors": [
        {"family": "Russell", "given": "Stuart"},
        {"family": "Norvig", "given": "Peter"},
    ],
    "year": 2020,
    "publisher": "Pearson",
    "type": "book",
}

# CrossRef REST API mock payload
_CROSSREF_MSG = {
    "title": ["Large-Scale Machine Learning"],
    "author": [
        {"family": "Brown", "given": "Alice L"},
        {"family": "Green", "given": "Bob"},
    ],
    "published": {"date-parts": [[2022, 6, 1]]},
    "container-title": ["PLOS ONE"],
    "DOI": "10.1371/journal.pone.0000001",
    "volume": "17",
    "issue": "6",
    "page": "e0000001",
    "publisher": "Public Library of Science",
    "type": "journal-article",
}

# CSL-JSON mock payload (from doi.org content-neg)
_CSL_JSON_MSG = {
    "type": "article-journal",
    "title": "Attention Is All You Need",
    "author": [
        {"family": "Vaswani", "given": "Ashish"},
        {"family": "Shazeer", "given": "Noam"},
    ],
    "issued": {"date-parts": [[2017]]},
    "container-title": "Advances in Neural Information Processing Systems",
    "DOI": "10.48550/arXiv.1706.03762",
    "volume": "30",
    "page": "5998-6008",
}


# ===========================================================================
# 1. Reference model
# ===========================================================================

class TestReference(unittest.TestCase):

    def test_from_dict_fields(self):
        ref = Reference.from_dict(_TWO_AUTHOR_REF)
        self.assertEqual(ref.id, "smith2020")
        self.assertEqual(ref.title, "Deep Learning for Natural Language Processing")
        self.assertEqual(len(ref.authors), 2)
        self.assertEqual(ref.authors[0].family, "Smith")
        self.assertEqual(ref.authors[0].given, "John A")
        self.assertEqual(ref.year, 2020)
        self.assertEqual(ref.journal, "Journal of Artificial Intelligence Research")
        self.assertEqual(ref.doi, "10.1613/jair.1.11677")
        self.assertEqual(ref.volume, "68")
        self.assertEqual(ref.issue, "1")
        self.assertEqual(ref.pages, "1-50")
        self.assertEqual(ref.ref_type, "article-journal")

    def test_to_csl_json_structure(self):
        ref = Reference.from_dict(_SINGLE_AUTHOR_REF)
        csl = ref.to_csl_json()
        self.assertEqual(csl["id"], "jones2019")
        self.assertEqual(csl["type"], "article-journal")
        self.assertEqual(csl["title"], "A Survey of Transformer Models")
        self.assertEqual(csl["author"][0]["family"], "Jones")
        self.assertEqual(csl["issued"]["date-parts"], [[2019]])
        self.assertEqual(csl["container-title"], "Nature Machine Intelligence")
        self.assertEqual(csl["DOI"], "10.1038/s42256-019-0001-0")
        self.assertEqual(csl["volume"], "1")
        self.assertEqual(csl["issue"], "4")
        self.assertEqual(csl["page"], "200-210")

    def test_optional_fields_absent_when_none(self):
        ref = Reference.from_dict({
            "id": "minimal",
            "title": "Minimal Reference",
            "authors": [],
        })
        csl = ref.to_csl_json()
        self.assertNotIn("issued", csl)
        self.assertNotIn("container-title", csl)
        self.assertNotIn("DOI", csl)

    def test_book_type(self):
        ref = Reference.from_dict(_BOOK_REF)
        self.assertEqual(ref.ref_type, "book")
        csl = ref.to_csl_json()
        self.assertEqual(csl["type"], "book")
        self.assertEqual(csl["publisher"], "Pearson")


# ===========================================================================
# 2. Author parsing
# ===========================================================================

class TestAuthorParsing(unittest.TestCase):

    def test_dict_author(self):
        ref = Reference.from_dict({
            "id": "x", "title": "T",
            "authors": [{"family": "Turing", "given": "Alan M"}],
        })
        self.assertEqual(ref.authors[0].family, "Turing")
        self.assertEqual(ref.authors[0].given, "Alan M")

    def test_string_comma_format(self):
        ref = Reference.from_dict({
            "id": "x", "title": "T",
            "authors": ["Turing, Alan M"],
        })
        self.assertEqual(ref.authors[0].family, "Turing")
        self.assertEqual(ref.authors[0].given, "Alan M")

    def test_string_space_format(self):
        ref = Reference.from_dict({
            "id": "x", "title": "T",
            "authors": ["Alan Turing"],
        })
        self.assertEqual(ref.authors[0].family, "Turing")
        self.assertEqual(ref.authors[0].given, "Alan")

    def test_single_word_author(self):
        ref = Reference.from_dict({
            "id": "x", "title": "T",
            "authors": ["Aristotle"],
        })
        self.assertEqual(ref.authors[0].family, "Aristotle")
        self.assertEqual(ref.authors[0].given, "")

    def test_multiple_mixed_authors(self):
        ref = Reference.from_dict({
            "id": "x", "title": "T",
            "authors": [
                {"family": "Smith", "given": "J"},
                "Doe, Jane",
                "Alan Turing",
            ],
        })
        self.assertEqual(len(ref.authors), 3)
        self.assertEqual(ref.authors[0].family, "Smith")
        self.assertEqual(ref.authors[1].family, "Doe")
        self.assertEqual(ref.authors[2].family, "Turing")


# ===========================================================================
# 3. APA formatting
# ===========================================================================

class TestCitationFormatterAPA(unittest.TestCase):
    """
    Compare output against known-correct APA 7th Edition examples.

    Known-correct baselines (APA 7th Ed):
      Single author  in-text : (Jones, 2019)
      Two authors    in-text : (Smith & Doe, 2020)
      Six+ authors   in-text : (Alpha et al., 2021)
      Bibliography   pattern : Author(s). (Year). Title. Journal, Volume(Issue), Pages. DOI
    """

    def setUp(self):
        self.fmt = CitationFormatter("apa")

    def test_supported_styles_includes_apa(self):
        self.assertIn("apa", SUPPORTED_STYLES)

    def test_single_author_in_text(self):
        refs = [Reference.from_dict(_SINGLE_AUTHOR_REF)]
        result = self.fmt.format(refs)
        self.assertEqual(len(result.in_text), 1)
        text = result.in_text[0]
        # APA single author: (Jones, 2019)
        self.assertIn("Jones", text)
        self.assertIn("2019", text)

    def test_two_author_in_text(self):
        refs = [Reference.from_dict(_TWO_AUTHOR_REF)]
        result = self.fmt.format(refs)
        text = result.in_text[0]
        # APA two authors: (Smith & Doe, 2020)
        self.assertIn("Smith", text)
        self.assertIn("Doe", text)
        self.assertIn("2020", text)

    def test_et_al_for_many_authors(self):
        refs = [Reference.from_dict(_MANY_AUTHOR_REF)]
        result = self.fmt.format(refs)
        text = result.in_text[0]
        # APA 7th Ed ≥ 3 authors: first author + "et al."
        self.assertIn("Alpha", text)
        self.assertIn("et al", text.lower())

    def test_bibliography_contains_title(self):
        refs = [Reference.from_dict(_SINGLE_AUTHOR_REF)]
        result = self.fmt.format(refs)
        self.assertGreater(len(result.bibliography), 0)
        bib = result.bibliography[0]
        self.assertIn("Survey of Transformer Models", bib)

    def test_bibliography_contains_year(self):
        refs = [Reference.from_dict(_SINGLE_AUTHOR_REF)]
        result = self.fmt.format(refs)
        self.assertIn("2019", result.bibliography[0])

    def test_bibliography_contains_journal(self):
        refs = [Reference.from_dict(_SINGLE_AUTHOR_REF)]
        result = self.fmt.format(refs)
        self.assertIn("Nature Machine Intelligence", result.bibliography[0])

    def test_bibliography_contains_doi(self):
        refs = [Reference.from_dict(_SINGLE_AUTHOR_REF)]
        result = self.fmt.format(refs)
        self.assertIn("10.1038", result.bibliography[0])

    def test_book_bibliography(self):
        refs = [Reference.from_dict(_BOOK_REF)]
        result = self.fmt.format(refs)
        bib = result.bibliography[0]
        self.assertIn("Artificial Intelligence", bib)
        self.assertIn("2020", bib)

    def test_multiple_refs_returns_parallel_in_text(self):
        refs = [
            Reference.from_dict(_SINGLE_AUTHOR_REF),
            Reference.from_dict(_TWO_AUTHOR_REF),
        ]
        result = self.fmt.format(refs)
        self.assertEqual(len(result.in_text), 2)
        self.assertIn("Jones", result.in_text[0])
        self.assertIn("Smith", result.in_text[1])

    def test_empty_input(self):
        result = self.fmt.format([])
        self.assertEqual(result.in_text, [])
        self.assertEqual(result.bibliography, [])

    def test_style_name_stored(self):
        result = self.fmt.format([Reference.from_dict(_SINGLE_AUTHOR_REF)])
        self.assertEqual(result.style, "apa")


# ===========================================================================
# 4. Vancouver formatting
# ===========================================================================

class TestCitationFormatterVancouver(unittest.TestCase):
    """
    Compare output against known-correct Vancouver/PubMed examples.

    Known-correct baselines (Vancouver):
      In-text : numeric marker, e.g. [1] or superscript 1
      Bib     : 1. Jones RB. Title. Nat Mach Intell. 2019;1(4):200-210.
    """

    def setUp(self):
        self.fmt = CitationFormatter("vancouver")

    def test_supported_styles_includes_vancouver(self):
        self.assertIn("vancouver", SUPPORTED_STYLES)

    def test_in_text_is_numeric(self):
        refs = [Reference.from_dict(_SINGLE_AUTHOR_REF)]
        result = self.fmt.format(refs)
        text = result.in_text[0]
        # Vancouver in-text is numeric: (1) or [1] or superscript
        self.assertTrue(
            any(c.isdigit() for c in text),
            msg=f"Expected numeric in-text citation, got: {text!r}"
        )

    def test_bibliography_contains_author(self):
        refs = [Reference.from_dict(_SINGLE_AUTHOR_REF)]
        result = self.fmt.format(refs)
        self.assertIn("Jones", result.bibliography[0])

    def test_bibliography_contains_title(self):
        refs = [Reference.from_dict(_SINGLE_AUTHOR_REF)]
        result = self.fmt.format(refs)
        self.assertIn("Survey of Transformer Models", result.bibliography[0])

    def test_bibliography_contains_year(self):
        refs = [Reference.from_dict(_SINGLE_AUTHOR_REF)]
        result = self.fmt.format(refs)
        self.assertIn("2019", result.bibliography[0])

    def test_bibliography_contains_volume_issue(self):
        refs = [Reference.from_dict(_SINGLE_AUTHOR_REF)]
        result = self.fmt.format(refs)
        bib = result.bibliography[0]
        self.assertIn("1", bib)   # volume
        self.assertIn("4", bib)   # issue

    def test_two_refs_sequential_numbering(self):
        refs = [
            Reference.from_dict(_SINGLE_AUTHOR_REF),
            Reference.from_dict(_TWO_AUTHOR_REF),
        ]
        result = self.fmt.format(refs)
        # Both in-text markers should contain digits; second should be > first
        self.assertEqual(len(result.in_text), 2)
        # bibliography should have 2 entries
        self.assertEqual(len(result.bibliography), 2)

    def test_style_name_stored(self):
        result = self.fmt.format([Reference.from_dict(_SINGLE_AUTHOR_REF)])
        self.assertEqual(result.style, "vancouver")


# ===========================================================================
# 5. format_json convenience method
# ===========================================================================

class TestFormatJson(unittest.TestCase):

    def test_apa_format_json(self):
        result = CitationFormatter.format_json([_SINGLE_AUTHOR_REF], style="apa")
        self.assertIsInstance(result, CitationOutput)
        self.assertEqual(result.style, "apa")
        self.assertEqual(len(result.in_text), 1)

    def test_vancouver_format_json(self):
        result = CitationFormatter.format_json([_SINGLE_AUTHOR_REF], style="vancouver")
        self.assertEqual(result.style, "vancouver")

    def test_invalid_style_raises(self):
        with self.assertRaises(ValueError):
            CitationFormatter.format_json([_SINGLE_AUTHOR_REF], style="harvard")

    def test_multiple_refs_json(self):
        result = CitationFormatter.format_json(
            [_SINGLE_AUTHOR_REF, _TWO_AUTHOR_REF, _BOOK_REF],
            style="apa",
        )
        self.assertEqual(len(result.in_text), 3)


# ===========================================================================
# 6. CrossRef helper unit tests (no HTTP)
# ===========================================================================

class TestCrossRefHelpers(unittest.TestCase):

    def test_clean_doi_no_prefix(self):
        self.assertEqual(_clean_doi("10.1038/s41586"), "10.1038/s41586")

    def test_clean_doi_https_prefix(self):
        self.assertEqual(
            _clean_doi("https://doi.org/10.1038/s41586"),
            "10.1038/s41586",
        )

    def test_clean_doi_http_dx_prefix(self):
        self.assertEqual(
            _clean_doi("http://dx.doi.org/10.1038/s41586"),
            "10.1038/s41586",
        )

    def test_clean_doi_strips_whitespace(self):
        self.assertEqual(_clean_doi("  10.1038/s41586  "), "10.1038/s41586")

    def test_reference_from_crossref_message_fields(self):
        ref = _reference_from_crossref_message(_CROSSREF_MSG, ref_id="brown2022")
        self.assertEqual(ref.id, "brown2022")
        self.assertEqual(ref.title, "Large-Scale Machine Learning")
        self.assertEqual(len(ref.authors), 2)
        self.assertEqual(ref.authors[0].family, "Brown")
        self.assertEqual(ref.authors[0].given, "Alice L")
        self.assertEqual(ref.year, 2022)
        self.assertEqual(ref.journal, "PLOS ONE")
        self.assertEqual(ref.doi, "10.1371/journal.pone.0000001")
        self.assertEqual(ref.volume, "17")
        self.assertEqual(ref.issue, "6")
        self.assertEqual(ref.pages, "e0000001")
        self.assertEqual(ref.ref_type, "article-journal")

    def test_reference_from_crossref_message_type_mapping(self):
        msg = dict(_CROSSREF_MSG, type="book")
        ref = _reference_from_crossref_message(msg)
        self.assertEqual(ref.ref_type, "book")

    def test_reference_from_csl_json_fields(self):
        ref = _reference_from_csl_json(_CSL_JSON_MSG, ref_id="vaswani2017")
        self.assertEqual(ref.id, "vaswani2017")
        self.assertEqual(ref.title, "Attention Is All You Need")
        self.assertEqual(ref.year, 2017)
        self.assertEqual(ref.authors[0].family, "Vaswani")

    def test_reference_from_crossref_message_auto_id(self):
        ref = _reference_from_crossref_message(_CROSSREF_MSG)
        # id should be derived from DOI with safe chars
        self.assertFalse("/" in ref.id)
        self.assertFalse("." in ref.id)


# ===========================================================================
# 7. reference_from_doi (mocked HTTP)
# ===========================================================================

class TestReferenceFromDoi(unittest.TestCase):
    """
    Tests reference_from_doi() with mocked HTTP so no real network calls.
    """

    @patch("app.services.crossref_client._http_get")
    def test_resolves_via_content_negotiation(self, mock_get: MagicMock):
        """Should use content-neg (first strategy) when it succeeds."""
        mock_get.return_value = json.dumps(_CSL_JSON_MSG).encode()
        ref = reference_from_doi("10.48550/arXiv.1706.03762", ref_id="vaswani2017")
        self.assertEqual(ref.title, "Attention Is All You Need")
        self.assertEqual(ref.id, "vaswani2017")
        # Should only have called _http_get once (content-neg)
        mock_get.assert_called_once()

    @patch("app.services.crossref_client._http_get")
    def test_falls_back_to_crossref_rest(self, mock_get: MagicMock):
        """Should fall back to CrossRef REST API when content-neg fails."""
        crossref_response = json.dumps({"status": "ok", "message": _CROSSREF_MSG}).encode()
        mock_get.side_effect = [
            CrossRefError("content-neg failed"),   # first call → content-neg fails
            crossref_response,                      # second call → REST API succeeds
        ]
        ref = reference_from_doi("10.1371/journal.pone.0000001", ref_id="brown2022")
        self.assertEqual(ref.title, "Large-Scale Machine Learning")
        self.assertEqual(ref.id, "brown2022")
        self.assertEqual(mock_get.call_count, 2)

    @patch("app.services.crossref_client._http_get")
    def test_raises_when_both_strategies_fail(self, mock_get: MagicMock):
        """Should raise CrossRefError when both strategies fail."""
        mock_get.side_effect = CrossRefError("network down")
        with self.assertRaises(CrossRefError):
            reference_from_doi("10.9999/nonexistent")

    @patch("app.services.crossref_client._http_get")
    def test_doi_cleaned_before_request(self, mock_get: MagicMock):
        """URL prefix should be stripped before making HTTP request."""
        mock_get.return_value = json.dumps(_CSL_JSON_MSG).encode()
        reference_from_doi("https://doi.org/10.48550/arXiv.1706.03762")
        call_url = mock_get.call_args[0][0]
        # The URL should not double-embed the doi.org prefix
        self.assertNotIn("doi.org/https", call_url)

    @patch("app.services.crossref_client._http_get")
    def test_auto_id_generated_from_doi(self, mock_get: MagicMock):
        """When ref_id is omitted, id should be derived from DOI."""
        mock_get.return_value = json.dumps(_CSL_JSON_MSG).encode()
        ref = reference_from_doi("10.48550/arXiv.1706.03762")
        # id must not contain '/' or '.'
        self.assertNotIn("/", ref.id)


# ===========================================================================
# 8. End-to-end: DOI → format (mocked HTTP)
# ===========================================================================

class TestEndToEnd(unittest.TestCase):
    """Full pipeline: DOI → Reference → CitationFormatter → CitationOutput."""

    @patch("app.services.crossref_client._http_get")
    def test_doi_to_apa_bibliography(self, mock_get: MagicMock):
        mock_get.return_value = json.dumps(_CSL_JSON_MSG).encode()
        ref = reference_from_doi("10.48550/arXiv.1706.03762", ref_id="vaswani2017")
        result = CitationFormatter("apa").format([ref])
        bib = result.bibliography[0]
        self.assertIn("Vaswani", bib)
        self.assertIn("2017", bib)
        self.assertIn("Attention Is All You Need", bib)

    @patch("app.services.crossref_client._http_get")
    def test_doi_to_vancouver_bibliography(self, mock_get: MagicMock):
        mock_get.return_value = json.dumps(_CSL_JSON_MSG).encode()
        ref = reference_from_doi("10.48550/arXiv.1706.03762", ref_id="vaswani2017")
        result = CitationFormatter("vancouver").format([ref])
        bib = result.bibliography[0]
        self.assertIn("Vaswani", bib)
        self.assertIn("2017", bib)


if __name__ == "__main__":
    unittest.main(verbosity=2)
