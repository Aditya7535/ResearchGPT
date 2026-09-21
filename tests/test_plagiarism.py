"""
Unit tests for the plagiarism detection service.

Test classes
------------
TestSubscriptionLevel     – enum behaviour and external check gate
TestSimilarityFinding     – severity, similarity_pct, to_dict
TestSectionReport         – aggregation properties
TestPlagiarismReport      – overall stats, to_json, to_markdown routing
TestSplitIntoChunks       – chunker correctness
TestDistanceConversion    – cosine distance → similarity
TestInternalCheckerUnit   – check_section_internal with mocked EmbeddingStore
TestInternalCheckerFull   – run_internal_check document-level
TestCopyleaksClient       – submit/poll/parse with mocked HTTP
TestExternalCheckGate     – subscription enforcement
TestPlagiarismChecker     – orchestrator: internal only, with external, error paths
TestReportGenerator       – Markdown rendering correctness
TestSaveReport            – file I/O for markdown + JSON

All HTTP calls and ChromaDB queries are mocked — fully offline.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from app.services.plagiarism.models import (
    PlagiarismReport,
    SectionReport,
    SimilarityFinding,
    SubscriptionLevel,
    SubscriptionRequiredError,
)
from app.services.plagiarism.internal_checker import (
    split_into_chunks,
    _distance_to_similarity,
    check_section_internal,
    run_internal_check,
    SIMILARITY_THRESHOLD,
)
from app.services.plagiarism.external_checker import (
    CopyleaksClient,
    run_external_check,
)
from app.services.plagiarism.report_generator import render_markdown_report
from app.services.plagiarism.checker import PlagiarismChecker


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _finding(
    text="Transformers have revolutionised NLP.",
    section="Introduction",
    score=0.92,
    source_type="internal",
    source_ref="paper.pdf:Introduction",
) -> SimilarityFinding:
    return SimilarityFinding(
        text=text, section=section,
        similarity_score=score,
        source_type=source_type,
        source_ref=source_ref,
        source_text="Transformers have revolutionised natural language processing.",
    )


def _section_report(
    name: str = "Introduction",
    word_count: int = 500,
    chunks: int = 8,
    findings: list[SimilarityFinding] | None = None,
) -> SectionReport:
    return SectionReport(
        section_name=name,
        word_count=word_count,
        chunks_checked=chunks,
        findings=findings or [],
    )


def _mock_store(results: list[dict]) -> MagicMock:
    store = MagicMock()
    store.query.return_value = results
    return store


SAMPLE_SECTIONS = {
    "Introduction": (
        "Citation management is a critical aspect of academic writing. "
        "Proper citation ensures academic integrity and allows readers to trace claims.\n\n"
        "Transformer models have revolutionised natural language processing. "
        "They form the backbone of modern large language models like GPT and BERT."
    ),
    "Methods": (
        "We collected 500 papers from PubMed and annotated them manually.\n\n"
        "Each paper was processed using our custom NLP pipeline."
    ),
}


# ===========================================================================
# 1. SubscriptionLevel
# ===========================================================================

class TestSubscriptionLevel(unittest.TestCase):

    def test_free_does_not_allow_external(self):
        self.assertFalse(SubscriptionLevel.FREE.allows_external_check)

    def test_pro_allows_external(self):
        self.assertTrue(SubscriptionLevel.PRO.allows_external_check)

    def test_enterprise_allows_external(self):
        self.assertTrue(SubscriptionLevel.ENTERPRISE.allows_external_check)

    def test_subscription_required_error_message(self):
        err = SubscriptionRequiredError("External check", SubscriptionLevel.PRO)
        self.assertIn("pro", str(err).lower())
        self.assertIn("External check", str(err))
        self.assertEqual(err.required, SubscriptionLevel.PRO)


# ===========================================================================
# 2. SimilarityFinding
# ===========================================================================

class TestSimilarityFinding(unittest.TestCase):

    def test_similarity_pct_rounds(self):
        f = _finding(score=0.9175)
        self.assertEqual(f.similarity_pct, 91.8)

    def test_severity_critical(self):
        f = _finding(score=0.98)
        self.assertEqual(f.severity, "CRITICAL")

    def test_severity_high(self):
        f = _finding(score=0.88)
        self.assertEqual(f.severity, "HIGH")

    def test_severity_medium(self):
        f = _finding(score=0.78)
        self.assertEqual(f.severity, "MEDIUM")

    def test_severity_low(self):
        f = _finding(score=0.70)
        self.assertEqual(f.severity, "LOW")

    def test_to_dict_keys(self):
        d = _finding().to_dict()
        for key in ("text", "section", "similarity_score", "severity", "source_type", "source_ref"):
            self.assertIn(key, d)


# ===========================================================================
# 3. SectionReport
# ===========================================================================

class TestSectionReport(unittest.TestCase):

    def test_flagged_count(self):
        rpt = _section_report(findings=[_finding(), _finding()])
        self.assertEqual(rpt.flagged_count, 2)

    def test_similarity_pct_average(self):
        findings = [_finding(score=0.90), _finding(score=0.80)]
        rpt = _section_report(findings=findings)
        self.assertAlmostEqual(rpt.similarity_pct, 85.0, places=1)

    def test_similarity_pct_zero_when_no_findings(self):
        rpt = _section_report()
        self.assertEqual(rpt.similarity_pct, 0.0)

    def test_internal_vs_external_split(self):
        f_int = _finding(source_type="internal")
        f_ext = _finding(source_type="external")
        rpt   = _section_report(findings=[f_int, f_ext])
        self.assertEqual(len(rpt.internal_findings), 1)
        self.assertEqual(len(rpt.external_findings), 1)

    def test_flagged_word_pct(self):
        # 5 flagged words / 100 total = 5%
        f   = SimilarityFinding("One two three four five", "Methods", 0.9, "internal", "x")
        rpt = SectionReport("Methods", word_count=100, chunks_checked=5, findings=[f])
        self.assertAlmostEqual(rpt.flagged_word_pct, 5.0, places=1)

    def test_to_dict_structure(self):
        rpt = _section_report(findings=[_finding()])
        d   = rpt.to_dict()
        self.assertIn("section_name",  d)
        self.assertIn("findings",      d)
        self.assertIn("similarity_pct", d)
        self.assertIsInstance(d["findings"], list)


# ===========================================================================
# 4. PlagiarismReport
# ===========================================================================

class TestPlagiarismReport(unittest.TestCase):

    def _report(self, findings: list[SimilarityFinding]) -> PlagiarismReport:
        rpt = SectionReport("Introduction", word_count=200, chunks_checked=4, findings=findings)
        return PlagiarismReport(sections=[rpt])

    def test_overall_similarity_pct(self):
        # Flagged text has 5 words; total = 200 → 2.5%
        f   = SimilarityFinding("One two three four five", "Introduction", 0.9, "internal", "x")
        rpt = self._report([f])
        self.assertAlmostEqual(rpt.overall_similarity_pct, 2.5, places=1)

    def test_internal_similarity_pct(self):
        f   = SimilarityFinding("One two three four five", "Introduction", 0.9, "internal", "x")
        rpt = self._report([f])
        self.assertGreater(rpt.internal_similarity_pct, 0)

    def test_external_similarity_pct_none_when_not_ran(self):
        rpt = self._report([])
        self.assertIsNone(rpt.external_similarity_pct)

    def test_risk_level_high(self):
        rpt = PlagiarismReport(sections=[
            SectionReport("Intro", word_count=100, chunks_checked=5,
                          findings=[SimilarityFinding(" ".join(["word"]*35), "Intro", 0.95, "internal", "x")])
        ])
        self.assertEqual(rpt.risk_level, "HIGH RISK")

    def test_risk_level_minimal(self):
        rpt = PlagiarismReport(sections=[_section_report()])
        self.assertEqual(rpt.risk_level, "MINIMAL RISK")

    def test_to_json_is_valid(self):
        rpt  = self._report([_finding()])
        data = json.loads(rpt.to_json())
        self.assertIn("overall_similarity_pct", data)
        self.assertIn("sections", data)

    def test_all_findings_aggregated(self):
        f1  = _finding(section="Introduction")
        f2  = _finding(section="Methods")
        s1  = SectionReport("Introduction", 200, 5, [f1])
        s2  = SectionReport("Methods",      150, 4, [f2])
        rpt = PlagiarismReport(sections=[s1, s2])
        self.assertEqual(len(rpt.all_findings), 2)


# ===========================================================================
# 5. split_into_chunks
# ===========================================================================

class TestSplitIntoChunks(unittest.TestCase):

    def test_short_paragraph_excluded(self):
        text   = "Too short."
        chunks = split_into_chunks(text, min_words=15)
        self.assertEqual(chunks, [])

    def test_single_valid_paragraph(self):
        text   = " ".join(["word"] * 30)
        chunks = split_into_chunks(text)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_multiple_paragraphs(self):
        para1  = " ".join(["word"] * 20)
        para2  = " ".join(["word"] * 20)
        text   = f"{para1}\n\n{para2}"
        chunks = split_into_chunks(text)
        self.assertEqual(len(chunks), 2)

    def test_long_paragraph_split_into_windows(self):
        # 200 words → should be split into multiple chunks of ≤80 words
        text   = " ".join([f"word{i}" for i in range(200)])
        chunks = split_into_chunks(text, max_words=80)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.split()), 80 + 30)  # allow some overlap

    def test_no_chunks_when_all_too_short(self):
        text   = "Short.\n\nAlso short.\n\nVery brief."
        chunks = split_into_chunks(text, min_words=15)
        self.assertEqual(chunks, [])


# ===========================================================================
# 6. Distance conversion
# ===========================================================================

class TestDistanceConversion(unittest.TestCase):

    def test_zero_distance_is_one(self):
        self.assertEqual(_distance_to_similarity(0.0), 1.0)

    def test_one_distance_is_zero(self):
        self.assertEqual(_distance_to_similarity(1.0), 0.0)

    def test_midpoint(self):
        self.assertAlmostEqual(_distance_to_similarity(0.15), 0.85, places=5)

    def test_clamped_above_one(self):
        self.assertEqual(_distance_to_similarity(-0.1), 1.0)

    def test_clamped_below_zero(self):
        self.assertEqual(_distance_to_similarity(1.5), 0.0)


# ===========================================================================
# 7. Internal checker — unit
# ===========================================================================

class TestInternalCheckerUnit(unittest.TestCase):

    def _make_chroma_result(self, text: str, filename: str, section: str, distance: float) -> dict:
        return {
            "id":       "abc123",
            "text":     text,
            "metadata": {"source_filename": filename, "section": section, "document_id": "doc1"},
            "distance": distance,
        }

    def test_above_threshold_creates_finding(self):
        store = _mock_store([
            self._make_chroma_result("Transformers revolutionised NLP.", "paper.pdf", "Introduction", 0.05)
        ])
        text = (
            "Transformer models have revolutionised natural language processing. "
            "They are used in many downstream tasks."
        )
        rpt = check_section_internal("Introduction", text * 5, store, threshold=0.85)
        self.assertGreater(rpt.flagged_count, 0)
        self.assertEqual(rpt.findings[0].source_type, "internal")

    def test_below_threshold_no_findings(self):
        store = _mock_store([
            self._make_chroma_result("Completely unrelated content.", "paper.pdf", "Results", 0.60)
        ])
        text = " ".join(["word"] * 40)
        rpt  = check_section_internal("Methods", text, store, threshold=0.85)
        self.assertEqual(rpt.flagged_count, 0)

    def test_source_ref_formatted_correctly(self):
        store = _mock_store([
            self._make_chroma_result("Source passage.", "thesis.pdf", "Methods", 0.05)
        ])
        text  = " ".join(["source", "passage"] * 20)
        rpt   = check_section_internal("Methods", text, store, threshold=0.5)
        if rpt.findings:
            self.assertIn("thesis.pdf", rpt.findings[0].source_ref)
            self.assertIn("Methods",    rpt.findings[0].source_ref)

    def test_chromadb_error_caught_gracefully(self):
        store = MagicMock()
        store.query.side_effect = RuntimeError("ChromaDB down")
        text  = " ".join(["word"] * 20)
        # Should not raise — returns empty findings
        rpt = check_section_internal("Introduction", text, store)
        self.assertEqual(rpt.findings, [])

    def test_section_report_counts(self):
        store = _mock_store([
            self._make_chroma_result("Exact match passage.", "f.pdf", "S", 0.01)
        ])
        text = ("Exact match passage repeated. " * 3).strip()
        rpt  = check_section_internal("Section", text, store, threshold=0.9)
        self.assertGreater(rpt.chunks_checked, 0)
        self.assertGreater(rpt.word_count, 0)

    def test_no_content_skipped(self):
        store = _mock_store([])
        rpt   = run_internal_check(
            sections={"Abstract": "[NO_CONTENT]"},
            embedding_store=store,
        )
        self.assertEqual(len(rpt), 1)
        self.assertEqual(rpt[0].chunks_checked, 0)
        store.query.assert_not_called()


# ===========================================================================
# 8. Internal checker — document-level
# ===========================================================================

class TestInternalCheckerFull(unittest.TestCase):

    def test_returns_one_report_per_section(self):
        store = _mock_store([])
        rpts  = run_internal_check(SAMPLE_SECTIONS, store, threshold=0.99)
        self.assertEqual(len(rpts), 2)
        names = [r.section_name for r in rpts]
        self.assertIn("Introduction", names)
        self.assertIn("Methods",      names)

    def test_order_preserved(self):
        store = _mock_store([])
        rpts  = run_internal_check(SAMPLE_SECTIONS, store, threshold=0.99)
        self.assertEqual(rpts[0].section_name, "Introduction")
        self.assertEqual(rpts[1].section_name, "Methods")


# ===========================================================================
# 9. CopyleaksClient — mocked HTTP
# ===========================================================================

class TestCopyleaksClient(unittest.TestCase):

    def _client(self) -> CopyleaksClient:
        return CopyleaksClient(
            api_key="test_key",
            email="test@example.com",
            poll_interval_secs=0,
            timeout_secs=5,
        )

    @patch("app.services.plagiarism.external_checker.requests.post")
    @patch("app.services.plagiarism.external_checker.requests.put")
    @patch("app.services.plagiarism.external_checker.requests.get")
    def test_full_scan_flow(self, mock_get, mock_put, mock_post):
        # Login
        mock_post.return_value.json.return_value = {"access_token": "tok123"}
        mock_post.return_value.raise_for_status = MagicMock()

        # Submit (204)
        mock_put.return_value.raise_for_status = MagicMock()

        # Poll → Finished
        mock_get.return_value.json.side_effect = [
            {"scans": [{"id": "scan123", "status": "Finished"}]},  # status poll
            {  # result
                "internet": [{
                    "url": "https://example.com/paper",
                    "statistics": {"identical": 0.25, "similar": 0.10},
                    "comparison": [{"text": "Transformer models have revolutionised NLP.", "type": 1}],
                }]
            }
        ]
        mock_get.return_value.raise_for_status = MagicMock()

        client   = self._client()
        client._token = "tok123"  # pre-set to skip real login
        findings = client.scan_section("Introduction", "Transformer models have revolutionised NLP.")

        self.assertIsInstance(findings, list)
        self.assertGreater(len(findings), 0)
        self.assertEqual(findings[0].source_type,  "external")
        self.assertEqual(findings[0].source_ref,   "https://example.com/paper")
        self.assertEqual(findings[0].section,       "Introduction")

    @patch("app.services.plagiarism.external_checker.requests.get")
    @patch("app.services.plagiarism.external_checker.requests.put")
    def test_poll_timeout_raises(self, mock_put, mock_get):
        mock_put.return_value.raise_for_status = MagicMock()
        # Always return "Processing" → timeout
        mock_get.return_value.json.return_value = {"scans": [{"id": "scanX", "status": "Processing"}]}
        mock_get.return_value.raise_for_status   = MagicMock()

        client        = self._client()
        client._token = "tok"
        with self.assertRaises(TimeoutError):
            client._poll_until_done("scanX")

    def test_parse_result_no_comparison(self):
        result = {
            "internet": [{
                "url": "https://example.com",
                "statistics": {"identical": 0.3, "similar": 0.1},
                "comparison": [],
            }]
        }
        findings = CopyleaksClient._parse_result(result, "Methods", "Some text here.")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].source_ref, "https://example.com")

    def test_parse_result_empty(self):
        findings = CopyleaksClient._parse_result({}, "Methods", "text")
        self.assertEqual(findings, [])


# ===========================================================================
# 10. External check — subscription gate
# ===========================================================================

class TestExternalCheckGate(unittest.TestCase):

    def test_free_tier_raises(self):
        with self.assertRaises(SubscriptionRequiredError):
            run_external_check(
                sections=SAMPLE_SECTIONS,
                subscription_level=SubscriptionLevel.FREE,
                section_reports=[],
            )

    def test_pro_tier_proceeds(self):
        mock_client = MagicMock()
        mock_client.scan_section.return_value = [
            SimilarityFinding(
                text="Matched text.", section="Introduction",
                similarity_score=0.87, source_type="external",
                source_ref="https://example.com",
            )
        ]
        existing_rpts = [
            SectionReport("Introduction", 500, 8, []),
            SectionReport("Methods",      200, 4, []),
        ]
        updated = run_external_check(
            sections=SAMPLE_SECTIONS,
            subscription_level=SubscriptionLevel.PRO,
            section_reports=existing_rpts,
            _client=mock_client,
        )
        intro_rpt = next(r for r in updated if r.section_name == "Introduction")
        self.assertEqual(len(intro_rpt.external_findings), 1)

    def test_external_findings_appended_to_existing_section(self):
        internal_finding = _finding(source_type="internal")
        existing_rpts    = [SectionReport("Introduction", 500, 8, [internal_finding])]
        mock_client      = MagicMock()
        mock_client.scan_section.return_value = [
            SimilarityFinding("Web match.", "Introduction", 0.88, "external", "https://web.com"),
        ]
        updated     = run_external_check(
            sections={"Introduction": SAMPLE_SECTIONS["Introduction"]},
            subscription_level=SubscriptionLevel.PRO,
            section_reports=existing_rpts,
            _client=mock_client,
        )
        intro = next(r for r in updated if r.section_name == "Introduction")
        self.assertEqual(len(intro.findings), 2)


# ===========================================================================
# 11. PlagiarismChecker — orchestrator
# ===========================================================================

class TestPlagiarismChecker(unittest.TestCase):

    def _checker(self, level: SubscriptionLevel = SubscriptionLevel.FREE) -> PlagiarismChecker:
        return PlagiarismChecker(
            chroma_path="./fake",
            subscription_level=level,
        )

    def _mock_store_no_matches(self) -> MagicMock:
        return _mock_store([])

    def test_internal_only_check(self):
        checker = self._checker()
        report  = checker.check(SAMPLE_SECTIONS, run_external=False, _store=self._mock_store_no_matches())
        self.assertIsInstance(report, PlagiarismReport)
        self.assertFalse(report.external_ran)
        self.assertEqual(len(report.sections), 2)

    def test_external_gated_for_free(self):
        checker = self._checker(SubscriptionLevel.FREE)
        report  = checker.check(
            SAMPLE_SECTIONS, run_external=True,
            _store=self._mock_store_no_matches(),
        )
        self.assertFalse(report.external_ran)
        self.assertTrue(any("PRO" in e for e in report.errors))

    def test_external_runs_for_pro(self):
        checker     = self._checker(SubscriptionLevel.PRO)
        mock_client = MagicMock()
        mock_client.scan_section.return_value = []

        report = checker.check(
            SAMPLE_SECTIONS, run_external=True,
            _store=self._mock_store_no_matches(),
            _ext_client=mock_client,
        )
        self.assertTrue(report.external_ran)

    def test_chromadb_failure_does_not_crash(self):
        store = MagicMock()
        store.query.side_effect = Exception("ChromaDB unavailable")
        checker = self._checker()
        report  = checker.check(SAMPLE_SECTIONS, run_external=False, _store=store)
        # Should return a report (possibly with errors)
        self.assertIsInstance(report, PlagiarismReport)

    def test_report_has_generated_at(self):
        checker = self._checker()
        report  = checker.check(SAMPLE_SECTIONS, _store=self._mock_store_no_matches())
        self.assertTrue(len(report.generated_at) > 0)

    def test_subscription_level_in_report(self):
        checker = self._checker(SubscriptionLevel.PRO)
        report  = checker.check(SAMPLE_SECTIONS, _store=self._mock_store_no_matches())
        self.assertEqual(report.subscription_level, "pro")


# ===========================================================================
# 12. Report generator
# ===========================================================================

class TestReportGenerator(unittest.TestCase):

    def _full_report(self) -> PlagiarismReport:
        f_int = _finding(text=" ".join(["transformer"] * 20), score=0.93, source_type="internal")
        f_ext = _finding(text=" ".join(["nlp"] * 15), score=0.87, source_type="external",
                         source_ref="https://arxiv.org/paper")
        s1 = SectionReport("Introduction", word_count=300, chunks_checked=6,
                            findings=[f_int, f_ext])
        s2 = SectionReport("Methods",      word_count=200, chunks_checked=4, findings=[])
        return PlagiarismReport(
            sections=[s1, s2],
            external_ran=True,
            subscription_level="pro",
            external_provider="copyleaks",
        )

    def test_markdown_contains_title(self):
        md = render_markdown_report(self._full_report())
        self.assertIn("Plagiarism Detection Report", md)

    def test_markdown_contains_section_names(self):
        md = render_markdown_report(self._full_report())
        self.assertIn("Introduction", md)
        self.assertIn("Methods",      md)

    def test_markdown_contains_source_type_labels(self):
        md = render_markdown_report(self._full_report())
        self.assertIn("Corpus",  md)  # internal
        self.assertIn("Web",     md)  # external

    def test_markdown_sorted_findings_highest_first(self):
        md   = render_markdown_report(self._full_report())
        pos1 = md.find("93.0%")
        pos2 = md.find("87.0%")
        self.assertGreater(pos1, -1)
        self.assertGreater(pos2, -1)
        self.assertLess(pos1, pos2)   # 93% appears before 87%

    def test_no_findings_shows_clean_message(self):
        rpt = PlagiarismReport(sections=[_section_report()])
        md  = render_markdown_report(rpt)
        self.assertIn("No passages flagged", md)

    def test_upgrade_prompt_for_free_tier(self):
        rpt = PlagiarismReport(
            sections=[_section_report()],
            external_ran=False,
            subscription_level="free",
        )
        md = render_markdown_report(rpt)
        self.assertIn("PRO", md)

    def test_progress_bar_length(self):
        from app.services.plagiarism.report_generator import _progress_bar
        bar = _progress_bar(50.0, width=10)
        self.assertEqual(bar.count("█"), 5)
        self.assertEqual(bar.count("░"), 5)


# ===========================================================================
# 13. save_report
# ===========================================================================

class TestSaveReport(unittest.TestCase):

    def _report(self) -> PlagiarismReport:
        return PlagiarismReport(sections=[_section_report(findings=[_finding()])])

    def test_saves_markdown(self):
        checker = PlagiarismChecker()
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = checker.save_report(self._report(), tmpdir, formats=["markdown"])
            self.assertIn("markdown", saved)
            self.assertTrue(saved["markdown"].exists())
            content = saved["markdown"].read_text(encoding="utf-8")
            self.assertIn("Plagiarism", content)

    def test_saves_json(self):
        checker = PlagiarismChecker()
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = checker.save_report(self._report(), tmpdir, formats=["json"])
            self.assertIn("json", saved)
            data = json.loads(saved["json"].read_text(encoding="utf-8"))
            self.assertIn("overall_similarity_pct", data)

    def test_saves_both_formats(self):
        checker = PlagiarismChecker()
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = checker.save_report(self._report(), tmpdir)
            self.assertIn("markdown", saved)
            self.assertIn("json",     saved)

    def test_output_dir_created(self):
        checker = PlagiarismChecker()
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "reports" / "plagiarism"
            checker.save_report(self._report(), new_dir, formats=["json"])
            self.assertTrue(new_dir.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
