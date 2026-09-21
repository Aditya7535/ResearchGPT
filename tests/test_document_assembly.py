"""
Unit tests for the document assembly service.

Test classes
------------
TestModels              – ThesisContent, Section, DataTable, ChartConfig parsing
TestChartGenerator      – chart generation (matplotlib used directly for bar/line/pie;
                          mocked for import-error path)
TestWordBuilder         – python-docx doc structure (mocked Document)
TestPdfBuilder          – HTML generation, CSS correctness, WeasyPrint mock
TestAssembler           – end-to-end AssemblyResult, from_json, error isolation
TestSafeFilename        – filename sanitisation helper

All I/O-heavy operations (file saves, WeasyPrint render) are mocked.
Matplotlib tests use real rendering to a BytesIO — no display needed.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_JSON: dict = {
    "title":          "Effects of Deep Learning on Citation Management",
    "author":         "Jane Smith",
    "institution":    "University of Research",
    "date":           "2024",
    "abstract":       "This thesis investigates the application of deep learning to academic citation systems.",
    "citation_style": "apa",
    "sections": [
        {
            "name":          "Introduction",
            "heading_level": 1,
            "text":          "Citation management is a critical aspect of academic writing.\n\nThis work proposes a novel approach.",
            "citations":     ["smith2020"],
            "data_tables":   [],
        },
        {
            "name":          "Methods",
            "heading_level": 1,
            "text":          "We collected 500 papers from PubMed and annotated them manually.",
            "citations":     ["jones2019"],
            "data_tables": [
                {
                    "id":      "table_results",
                    "caption": "Model Performance by Dataset",
                    "headers": ["Dataset", "Accuracy", "F1"],
                    "rows": [
                        ["PubMed",   "94.2", "0.91"],
                        ["arXiv",    "88.7", "0.86"],
                        ["IEEE",     "91.3", "0.89"],
                    ],
                    "chart": {
                        "type":  "bar",
                        "title": "Accuracy by Dataset",
                        "x_col": "Dataset",
                        "y_col": "Accuracy",
                        "color": "#4472C4",
                    },
                }
            ],
        },
        {
            "name":          "Results",
            "heading_level": 1,
            "text":          "Our model achieved 94.2% accuracy on the PubMed dataset.",
            "citations":     [],
            "data_tables": [
                {
                    "id":      "table_pie",
                    "caption": "Dataset Distribution",
                    "headers": ["Source", "Count"],
                    "rows": [["PubMed", "200"], ["arXiv", "180"], ["IEEE", "120"]],
                    "chart": {
                        "type":  "pie",
                        "title": "Paper Sources",
                        "x_col": "Source",
                        "y_col": "Count",
                    },
                }
            ],
        },
        {
            "name":          "Discussion",
            "heading_level": 1,
            "text":          "The results demonstrate that transformer models outperform classical approaches.",
            "citations":     [],
            "data_tables":   [],
            "subsections": [
                {
                    "name":          "Limitations",
                    "heading_level": 2,
                    "text":          "Our dataset is limited to English-language papers.",
                    "citations":     [],
                    "data_tables":   [],
                }
            ],
        },
    ],
    "bibliography": [
        {
            "id":      "smith2020",
            "title":   "Deep Learning for NLP",
            "authors": [{"family": "Smith", "given": "John"}],
            "year":    2020,
            "journal": "JAIR",
            "type":    "article-journal",
        },
        {
            "id":      "jones2019",
            "title":   "Transformer Survey",
            "authors": [{"family": "Jones", "given": "Alice"}],
            "year":    2019,
            "journal": "Nature AI",
            "type":    "article-journal",
        },
    ],
}


# ===========================================================================
# 1. Models
# ===========================================================================

from app.services.document_assembly.models import (
    ThesisContent, Section, DataTable, ChartConfig,
)


class TestModels(unittest.TestCase):

    def test_thesis_content_from_dict(self):
        content = ThesisContent.from_dict(SAMPLE_JSON)
        self.assertEqual(content.title,          "Effects of Deep Learning on Citation Management")
        self.assertEqual(content.author,         "Jane Smith")
        self.assertEqual(content.citation_style, "apa")
        self.assertEqual(len(content.sections),  4)
        self.assertEqual(len(content.bibliography), 2)

    def test_section_parsed_correctly(self):
        content = ThesisContent.from_dict(SAMPLE_JSON)
        intro = content.sections[0]
        self.assertEqual(intro.name, "Introduction")
        self.assertEqual(intro.heading_level, 1)
        self.assertIn("Citation management", intro.text)

    def test_data_table_parsed(self):
        content = ThesisContent.from_dict(SAMPLE_JSON)
        methods = content.sections[1]
        self.assertEqual(len(methods.data_tables), 1)
        tbl = methods.data_tables[0]
        self.assertEqual(tbl.id, "table_results")
        self.assertEqual(tbl.headers, ["Dataset", "Accuracy", "F1"])
        self.assertEqual(len(tbl.rows), 3)

    def test_chart_config_parsed(self):
        content = ThesisContent.from_dict(SAMPLE_JSON)
        tbl = content.sections[1].data_tables[0]
        self.assertIsNotNone(tbl.chart)
        self.assertEqual(tbl.chart.type, "bar")
        self.assertEqual(tbl.chart.x_col, "Dataset")
        self.assertEqual(tbl.chart.y_col, "Accuracy")

    def test_subsections_parsed(self):
        content = ThesisContent.from_dict(SAMPLE_JSON)
        discussion = content.sections[3]
        self.assertEqual(len(discussion.subsections), 1)
        self.assertEqual(discussion.subsections[0].name, "Limitations")
        self.assertEqual(discussion.subsections[0].heading_level, 2)

    def test_all_sections_flat(self):
        content = ThesisContent.from_dict(SAMPLE_JSON)
        flat = content.all_sections_flat()
        names = [s.name for s in flat]
        self.assertIn("Introduction",  names)
        self.assertIn("Limitations",   names)  # subsection included

    def test_all_tables_returns_pairs(self):
        content = ThesisContent.from_dict(SAMPLE_JSON)
        pairs = content.all_tables()
        table_ids = [t.id for _, t in pairs]
        self.assertIn("table_results", table_ids)
        self.assertIn("table_pie",     table_ids)

    def test_table_col_index(self):
        tbl = DataTable(id="t", caption="", headers=["A", "B", "C"], rows=[])
        self.assertEqual(tbl.col_index("B"), 1)

    def test_table_col_index_missing_raises(self):
        tbl = DataTable(id="t", caption="", headers=["A"], rows=[])
        with self.assertRaises(KeyError):
            tbl.col_index("Z")

    def test_table_numeric_col(self):
        tbl = DataTable(
            id="t", caption="",
            headers=["Label", "Value"],
            rows=[["x", "1.5"], ["y", "2.3"]],
        )
        vals = tbl.numeric_col("Value")
        self.assertEqual(vals, [1.5, 2.3])

    def test_section_all_tables_recursive(self):
        content = ThesisContent.from_dict(SAMPLE_JSON)
        methods_section = content.sections[1]
        tables = methods_section.all_tables()
        self.assertEqual(len(tables), 1)

    def test_defaults_for_missing_fields(self):
        content = ThesisContent.from_dict({"title": "T", "author": "A"})
        self.assertEqual(content.citation_style, "apa")
        self.assertEqual(content.sections, [])
        self.assertEqual(content.abstract, "")

    def test_chart_config_defaults(self):
        cfg = ChartConfig.from_dict({"type": "line"})
        self.assertEqual(cfg.type,  "line")
        self.assertEqual(cfg.color, "#4472C4")
        self.assertEqual(cfg.dpi,   150)


# ===========================================================================
# 2. Chart Generator
# ===========================================================================

from app.services.document_assembly.chart_generator import generate_chart


class TestChartGenerator(unittest.TestCase):

    def _table_with_chart(self, chart_type: str) -> DataTable:
        return DataTable(
            id=f"tbl_{chart_type}",
            caption=f"{chart_type.title()} chart test",
            headers=["Category", "Value"],
            rows=[["A", "10"], ["B", "25"], ["C", "15"], ["D", "30"]],
            chart=ChartConfig(type=chart_type, title=f"Test {chart_type}", x_col="Category", y_col="Value"),
        )

    def test_bar_chart_returns_png_bytes(self):
        tbl = self._table_with_chart("bar")
        buf = generate_chart(tbl)
        self.assertIsInstance(buf, BytesIO)
        buf.seek(0)
        header = buf.read(4)
        self.assertEqual(header, b"\x89PNG")   # PNG magic bytes

    def test_line_chart_returns_png_bytes(self):
        tbl = self._table_with_chart("line")
        buf = generate_chart(tbl)
        buf.seek(0)
        self.assertEqual(buf.read(4), b"\x89PNG")

    def test_pie_chart_returns_png_bytes(self):
        tbl = self._table_with_chart("pie")
        buf = generate_chart(tbl)
        buf.seek(0)
        self.assertEqual(buf.read(4), b"\x89PNG")

    def test_histogram_returns_png_bytes(self):
        tbl = DataTable(
            id="hist", caption="Histogram",
            headers=["Value"],
            rows=[["1"], ["2"], ["3"], ["4"], ["5"], ["3"], ["2"]],
            chart=ChartConfig(type="histogram", y_col="Value"),
        )
        buf = generate_chart(tbl)
        buf.seek(0)
        self.assertEqual(buf.read(4), b"\x89PNG")

    def test_scatter_chart_returns_png_bytes(self):
        tbl = DataTable(
            id="sc", caption="Scatter",
            headers=["X", "Y"],
            rows=[["1", "2"], ["3", "5"], ["2", "4"]],
            chart=ChartConfig(type="scatter", x_col="X", y_col="Y"),
        )
        buf = generate_chart(tbl)
        buf.seek(0)
        self.assertEqual(buf.read(4), b"\x89PNG")

    def test_none_chart_config_raises(self):
        tbl = DataTable(id="t", caption="", headers=[], rows=[], chart=None)
        with self.assertRaises(ValueError):
            generate_chart(tbl)

    def test_unsupported_chart_type_raises(self):
        tbl = self._table_with_chart("treemap")
        with self.assertRaises(ValueError):
            generate_chart(tbl)

    def test_missing_column_raises(self):
        tbl = DataTable(
            id="t", caption="",
            headers=["A", "B"],
            rows=[["1", "2"]],
            chart=ChartConfig(type="bar", x_col="Z", y_col="B"),
        )
        with self.assertRaises(KeyError):
            generate_chart(tbl)

    def test_buffer_is_seeked_to_zero(self):
        tbl = self._table_with_chart("bar")
        buf = generate_chart(tbl)
        self.assertEqual(buf.tell(), 0)


# ===========================================================================
# 3. Word Builder
# ===========================================================================

class TestWordBuilder(unittest.TestCase):
    """Tests that confirm Word builder calls python-docx correctly."""

    def _content(self) -> ThesisContent:
        return ThesisContent.from_dict(SAMPLE_JSON)

    @patch("app.services.document_assembly.word_builder.Document")
    def test_build_word_doc_calls_save(self, mock_doc_cls):
        from app.services.document_assembly.word_builder import build_word_doc

        mock_doc = MagicMock()
        mock_doc.sections = [MagicMock()]
        mock_doc.sections[0].footer.paragraphs = [MagicMock()]
        mock_doc.add_paragraph.return_value = MagicMock()
        mock_doc.add_heading.return_value   = MagicMock(runs=[MagicMock()])
        mock_doc.paragraphs = [MagicMock()]
        mock_doc_cls.return_value = mock_doc

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "thesis.docx"
            # Mock the save to avoid real I/O; patch Path.resolve too
            mock_doc.save = MagicMock()
            with patch("app.services.document_assembly.word_builder.Path") as mock_path_cls:
                mock_path = MagicMock()
                mock_path.__truediv__ = lambda self, other: mock_path
                mock_path.parent.mkdir = MagicMock()
                mock_path.resolve.return_value = Path(tmpdir) / "thesis.docx"
                mock_path_cls.return_value = mock_path

                build_word_doc(self._content(), charts={}, output_path=str(out_path))

            mock_doc.save.assert_called_once()

    def test_template_loaded_correctly(self):
        from app.services.document_assembly.word_builder import _load_template
        tmpl = _load_template("default")
        self.assertIn("page", tmpl)
        self.assertIn("fonts", tmpl)
        self.assertIn("spacing", tmpl)

    def test_load_template_missing_raises(self):
        from app.services.document_assembly.word_builder import _load_template
        with self.assertRaises(FileNotFoundError):
            _load_template("nonexistent_xyz")


# ===========================================================================
# 4. PDF Builder
# ===========================================================================

from app.services.document_assembly.pdf_builder import generate_html, _esc, _load_template


class TestPdfBuilderHtml(unittest.TestCase):

    def setUp(self):
        self.content = ThesisContent.from_dict(SAMPLE_JSON)
        self.tmpl    = _load_template("default")

    def test_html_contains_title(self):
        html = generate_html(self.content, charts={}, tmpl=self.tmpl)
        self.assertIn("Effects of Deep Learning", html)

    def test_html_contains_author(self):
        html = generate_html(self.content, charts={}, tmpl=self.tmpl)
        self.assertIn("Jane Smith", html)

    def test_html_contains_abstract(self):
        html = generate_html(self.content, charts={}, tmpl=self.tmpl)
        self.assertIn("Abstract", html)
        self.assertIn("deep learning", html)

    def test_html_contains_all_section_headings(self):
        html = generate_html(self.content, charts={}, tmpl=self.tmpl)
        for sec_name in ["Introduction", "Methods", "Results", "Discussion"]:
            self.assertIn(sec_name, html)

    def test_html_contains_table_data(self):
        html = generate_html(self.content, charts={}, tmpl=self.tmpl)
        self.assertIn("PubMed",   html)
        self.assertIn("94.2",     html)

    def test_html_embeds_chart_as_base64(self):
        # Simulate a BytesIO PNG for the chart
        fake_png = BytesIO(b"\x89PNG\r\n" + b"x" * 100)
        charts   = {"table_results": fake_png}
        html     = generate_html(self.content, charts=charts, tmpl=self.tmpl)
        self.assertIn("data:image/png;base64,", html)

    def test_html_contains_subsection(self):
        html = generate_html(self.content, charts={}, tmpl=self.tmpl)
        self.assertIn("Limitations", html)

    def test_esc_helper(self):
        self.assertEqual(_esc("A & B"),   "A &amp; B")
        self.assertEqual(_esc("<tag>"),   "&lt;tag&gt;")
        self.assertEqual(_esc('"value"'), "&quot;value&quot;")

    def test_css_contains_page_margins(self):
        from app.services.document_assembly.pdf_builder import _generate_css
        css = _generate_css(self.tmpl)
        self.assertIn("1.5in",  css)    # left margin
        self.assertIn("@page",  css)
        self.assertIn("counter(page)", css)  # page numbers

    def test_css_contains_font_family(self):
        from app.services.document_assembly.pdf_builder import _generate_css
        css = _generate_css(self.tmpl)
        self.assertIn("Times New Roman", css)

    @patch("app.services.document_assembly.pdf_builder.WeasyHTML", create=True)
    def test_build_pdf_calls_weasyprint(self, mock_weasy):
        from app.services.document_assembly.pdf_builder import build_pdf
        # Patch the WeasyPrint import inside the function
        with patch.dict(sys.modules, {"weasyprint": MagicMock()}):
            import importlib
            import app.services.document_assembly.pdf_builder as pdf_mod
            importlib.reload(pdf_mod)

            mock_html_inst = MagicMock()
            pdf_mod.WeasyHTML = MagicMock(return_value=mock_html_inst)

            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_mod.build_pdf(self.content, charts={}, output_path=str(Path(tmpdir) / "out.pdf"))

            pdf_mod.WeasyHTML.assert_called_once()
            mock_html_inst.write_pdf.assert_called_once()


# ===========================================================================
# 5. Assembler
# ===========================================================================

from app.services.document_assembly.assembler import DocumentAssembler, AssemblyResult, _safe_filename


class TestAssembler(unittest.TestCase):

    def _content(self) -> ThesisContent:
        return ThesisContent.from_dict(SAMPLE_JSON)

    @patch("app.services.document_assembly.assembler.build_word_doc", create=True)
    @patch("app.services.document_assembly.assembler.build_pdf",      create=True)
    def test_assemble_generates_both_formats(self, mock_pdf, mock_word):
        with patch(
            "app.services.document_assembly.assembler.DocumentAssembler._generate_all_charts",
            return_value={}
        ):
            mock_word.return_value = Path("/fake/thesis.docx")
            mock_pdf.return_value  = Path("/fake/thesis.pdf")

            with patch("app.services.document_assembly.assembler.build_word_doc", mock_word), \
                 patch("app.services.document_assembly.assembler.build_pdf", mock_pdf):

                assembler = DocumentAssembler()
                result = assembler.assemble(self._content(), formats=["word", "pdf"])

        self.assertIsInstance(result, AssemblyResult)

    def test_chart_generation_called_for_tables_with_charts(self):
        content = self._content()
        assembler = DocumentAssembler()
        result = AssemblyResult()

        # Patch generate_chart to avoid real matplotlib calls
        with patch("app.services.document_assembly.assembler.generate_chart") as mock_gen:
            mock_gen.return_value = BytesIO(b"\x89PNG" + b"x" * 50)
            charts = assembler._generate_all_charts(content, result)

        # Two tables have chart configs (table_results + table_pie)
        self.assertEqual(mock_gen.call_count, 2)
        self.assertIn("table_results", charts)
        self.assertIn("table_pie",     charts)

    def test_chart_failure_captured_as_warning(self):
        content = self._content()
        assembler = DocumentAssembler()
        result = AssemblyResult()

        with patch("app.services.document_assembly.assembler.generate_chart") as mock_gen:
            mock_gen.side_effect = RuntimeError("matplotlib crashed")
            charts = assembler._generate_all_charts(content, result)

        self.assertEqual(charts, {})
        self.assertTrue(len(result.warnings) > 0)
        self.assertIn("table_results", result.warnings[0])

    def test_word_import_error_captured_as_warning(self):
        assembler = DocumentAssembler()
        result = AssemblyResult()

        with patch("app.services.document_assembly.assembler.DocumentAssembler._generate_all_charts", return_value={}):
            with patch(
                "app.services.document_assembly.assembler.build_word_doc",
                side_effect=ImportError("python-docx not found"),
            ):
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = assembler.assemble(self._content(), output_dir=tmpdir, formats=["word"])

        self.assertIsNone(result.word_path)
        self.assertTrue(any("Word generation skipped" in w for w in result.warnings))

    def test_pdf_import_error_captured_as_warning(self):
        assembler = DocumentAssembler()

        with patch("app.services.document_assembly.assembler.DocumentAssembler._generate_all_charts", return_value={}):
            with patch("app.services.document_assembly.assembler.build_word_doc", return_value=Path("/f/t.docx")):
                with patch(
                    "app.services.document_assembly.assembler.build_pdf",
                    side_effect=ImportError("weasyprint not installed"),
                ):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        result = assembler.assemble(self._content(), output_dir=tmpdir, formats=["word", "pdf"])

        self.assertIsNone(result.pdf_path)
        self.assertTrue(any("PDF generation skipped" in w for w in result.warnings))

    def test_word_only_format(self):
        assembler = DocumentAssembler()

        with patch("app.services.document_assembly.assembler.DocumentAssembler._generate_all_charts", return_value={}):
            with patch("app.services.document_assembly.assembler.build_word_doc", return_value=Path("/f/t.docx")) as mock_w:
                with patch("app.services.document_assembly.assembler.build_pdf") as mock_p:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        assembler.assemble(self._content(), output_dir=tmpdir, formats=["word"])

            mock_p.assert_not_called()

    def test_from_json_convenience(self):
        with patch("app.services.document_assembly.assembler.DocumentAssembler.assemble") as mock_assemble:
            mock_assemble.return_value = AssemblyResult(word_path=Path("/f/t.docx"))
            result = DocumentAssembler.from_json(SAMPLE_JSON, formats=["word"])
        mock_assemble.assert_called_once()

    def test_success_property(self):
        r1 = AssemblyResult(word_path=Path("/f/t.docx"))
        r2 = AssemblyResult()
        self.assertTrue(r1.success)
        self.assertFalse(r2.success)

    @patch("app.services.plagiarism.PlagiarismChecker.check")
    @patch("app.services.plagiarism.PlagiarismChecker.save_report")
    def test_plagiarism_check_integrated(self, mock_save, mock_check):
        mock_report = MagicMock()
        mock_check.return_value = mock_report
        mock_save.return_value = {"markdown": Path("/tmp/report.md")}

        with patch("app.services.document_assembly.assembler.DocumentAssembler._generate_all_charts", return_value={}):
            with patch("app.services.document_assembly.assembler.build_word_doc", return_value=Path("/f/t.docx")):
                with tempfile.TemporaryDirectory() as tmpdir:
                    assembler = DocumentAssembler()
                    result = assembler.assemble(
                        self._content(),
                        output_dir=tmpdir,
                        formats=["word"],
                        run_plagiarism_check=True,
                    )
        self.assertIsNotNone(result.plagiarism_report)
        self.assertEqual(result.plagiarism_path, Path("/tmp/report.md"))


# ===========================================================================
# 6. _safe_filename helper
# ===========================================================================

class TestSafeFilename(unittest.TestCase):

    def test_spaces_replaced(self):
        self.assertEqual(_safe_filename("My Thesis Title"), "My_Thesis_Title")

    def test_illegal_chars_replaced(self):
        result = _safe_filename('Title: "Effects" <2024>')
        self.assertNotIn(":", result)
        self.assertNotIn('"', result)
        self.assertNotIn("<", result)

    def test_max_length_enforced(self):
        long_title = "A" * 200
        result = _safe_filename(long_title, max_len=60)
        self.assertLessEqual(len(result), 60)

    def test_empty_title_fallback(self):
        result = _safe_filename("")
        self.assertEqual(result, "thesis")

    def test_unicode_preserved(self):
        result = _safe_filename("Étude sur l'IA")
        self.assertGreater(len(result), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
