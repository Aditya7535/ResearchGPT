"""
Document Assembly Service orchestrator.

Ties together:
  1. chart_generator  — matplotlib PNG charts for every DataTable with a chart config
  2. word_builder     — python-docx .docx generation
  3. pdf_builder      — WeasyPrint .pdf generation

Usage
-----
    from app.services.document_assembly import DocumentAssembler, ThesisContent

    content = ThesisContent.from_dict(json_data)

    assembler = DocumentAssembler(template_name="default")
    result    = assembler.assemble(content, output_dir="./output")

    print(result.word_path)         # e.g. ./output/My_Thesis.docx
    print(result.pdf_path)          # e.g. ./output/My_Thesis.pdf
    print(result.chart_count)       # number of charts generated
    print(result.warnings)          # non-fatal issues (e.g. WeasyPrint unavailable)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from app.services.document_assembly.models import ThesisContent, DataTable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AssemblyResult:
    """Output of a successful (or partial) assembly run."""

    word_path:       Path | None        = None
    pdf_path:        Path | None        = None
    plagiarism_path: Path | None        = None
    plagiarism_report: Any | None       = None
    chart_count:     int                = 0
    warnings:        list[str]          = field(default_factory=list)
    errors:          list[str]          = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True if at least the Word document was generated."""
        return self.word_path is not None

    def __str__(self) -> str:
        return (
            f"AssemblyResult(word={self.word_path}, pdf={self.pdf_path}, "
            f"plagiarism={self.plagiarism_path}, charts={self.chart_count}, "
            f"warnings={len(self.warnings)})"
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class DocumentAssembler:
    """
    Orchestrates the full document assembly pipeline.

    Parameters
    ----------
    template_name:
        Name of the JSON config in ``app/services/document_assembly/templates/``.
        Defaults to ``"default"``.
    """

    def __init__(self, template_name: str = "default") -> None:
        self.template_name = template_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assemble(
        self,
        content: ThesisContent,
        output_dir: str | Path = "./output",
        formats: list[str] | None = None,
        run_plagiarism_check: bool = False,
        plagiarism_subscription: str = "free",
        run_external_plagiarism: bool = False,
        chroma_path: str = "./chroma_data",
    ) -> AssemblyResult:
        """
        Generate Word and/or PDF documents from ThesisContent.

        Parameters
        ----------
        content:
            Populated ThesisContent object (use ThesisContent.from_dict).
        output_dir:
            Directory where output files are saved (created if absent).
        formats:
            List of formats to generate: ``["word", "pdf"]``.
            Defaults to both.
        run_plagiarism_check:
            If True, run internal and optional external plagiarism check.
        plagiarism_subscription:
            Subscription level string: ``"free"``, ``"pro"``, or ``"enterprise"``.
        run_external_plagiarism:
            If True and subscription is PRO+, run external Copyleaks check.
        chroma_path:
            Path to ChromaDB persistent store for internal corpus comparison.

        Returns
        -------
        AssemblyResult
            Paths to generated files and any warnings/errors.
        """
        if formats is None:
            formats = ["word", "pdf"]
        formats = [f.lower() for f in formats]

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_title = _safe_filename(content.title)
        result = AssemblyResult()

        # ── Step 1: Generate charts ────────────────────────────────────────
        charts = self._generate_all_charts(content, result)
        result.chart_count = len(charts)

        # ── Step 2: Word document ──────────────────────────────────────────
        if "word" in formats:
            word_path = out_dir / f"{safe_title}.docx"
            try:
                from app.services.document_assembly.word_builder import build_word_doc
                result.word_path = build_word_doc(
                    content,
                    charts=charts,
                    template_name=self.template_name,
                    output_path=word_path,
                )
                logger.info("Word document generated: %s", result.word_path)
            except ImportError as exc:
                msg = f"Word generation skipped: {exc}"
                logger.warning(msg)
                result.warnings.append(msg)
            except Exception as exc:
                msg = f"Word generation failed: {exc}"
                logger.error(msg, exc_info=True)
                result.errors.append(msg)

        # ── Step 3: PDF ────────────────────────────────────────────────────
        if "pdf" in formats:
            pdf_path = out_dir / f"{safe_title}.pdf"
            try:
                from app.services.document_assembly.pdf_builder import build_pdf
                result.pdf_path = build_pdf(
                    content,
                    charts=charts,
                    template_name=self.template_name,
                    output_path=pdf_path,
                )
                logger.info("PDF generated: %s", result.pdf_path)
            except ImportError as exc:
                msg = (
                    f"PDF generation skipped (WeasyPrint not available): {exc}. "
                    "Install with: pip install weasyprint"
                )
                logger.warning(msg)
                result.warnings.append(msg)
            except Exception as exc:
                msg = f"PDF generation failed: {exc}"
                logger.error(msg, exc_info=True)
                result.errors.append(msg)

        # ── Step 4: Plagiarism Check (Optional) ────────────────────────────
        if run_plagiarism_check:
            try:
                from app.services.plagiarism import PlagiarismChecker, SubscriptionLevel
                sub_level = SubscriptionLevel(plagiarism_subscription.lower())
                checker = PlagiarismChecker(
                    chroma_path=chroma_path,
                    subscription_level=sub_level,
                )
                sections_dict = {sec.name: sec.text for sec in content.all_sections_flat()}
                report = checker.check(
                    sections=sections_dict,
                    run_external=run_external_plagiarism,
                )
                result.plagiarism_report = report
                saved = checker.save_report(
                    report=report,
                    output_dir=out_dir,
                    stem=f"{safe_title}_plagiarism",
                )
                result.plagiarism_path = saved.get("markdown") or saved.get("json")
                logger.info("Plagiarism report generated: %s", result.plagiarism_path)
            except Exception as exc:
                msg = f"Plagiarism check failed: {exc}"
                logger.error(msg, exc_info=True)
                result.warnings.append(msg)

        logger.info("Assembly complete: %s", result)
        return result

    @classmethod
    def from_json(
        cls,
        content_dict: dict[str, Any],
        output_dir: str | Path = "./output",
        template_name: str = "default",
        formats: list[str] | None = None,
        run_plagiarism_check: bool = False,
        plagiarism_subscription: str = "free",
        run_external_plagiarism: bool = False,
        chroma_path: str = "./chroma_data",
    ) -> AssemblyResult:
        """
        Convenience class method: parse JSON dict and assemble in one call.

        Parameters
        ----------
        content_dict:
            Raw dict matching the ThesisContent JSON schema.
        output_dir:
            Output directory.
        template_name:
            Template JSON name.
        formats:
            ``["word", "pdf"]`` (default: both).
        run_plagiarism_check / plagiarism_subscription / run_external_plagiarism / chroma_path:
            Forwarded to ``assemble()``.

        Returns
        -------
        AssemblyResult
        """
        content = ThesisContent.from_dict(content_dict)
        return cls(template_name=template_name).assemble(
            content=content,
            output_dir=output_dir,
            formats=formats,
            run_plagiarism_check=run_plagiarism_check,
            plagiarism_subscription=plagiarism_subscription,
            run_external_plagiarism=run_external_plagiarism,
            chroma_path=chroma_path,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_all_charts(
        self, content: ThesisContent, result: AssemblyResult
    ) -> dict[str, BytesIO]:
        """Generate PNG charts for all DataTables that have a ChartConfig."""
        from app.services.document_assembly.chart_generator import generate_chart

        charts: dict[str, BytesIO] = {}
        for section_name, table in content.all_tables():
            if table.chart is None:
                continue
            try:
                buf = generate_chart(table)
                charts[table.id] = buf
                logger.info(
                    "Chart generated: type=%s table='%s' section='%s'",
                    table.chart.type, table.id, section_name,
                )
            except ImportError as exc:
                msg = f"Chart skipped (matplotlib unavailable): {exc}"
                logger.warning(msg)
                result.warnings.append(msg)
            except Exception as exc:
                msg = f"Chart generation failed for table '{table.id}': {exc}"
                logger.warning(msg)
                result.warnings.append(msg)

        return charts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_filename(title: str, max_len: int = 60) -> str:
    """Sanitise a title string for use as a filename."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)
    safe = re.sub(r"\s+", "_", safe).strip("_")
    return safe[:max_len] or "thesis"
