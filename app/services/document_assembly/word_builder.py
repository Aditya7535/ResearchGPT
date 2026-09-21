"""
Word document builder using python-docx.

Applies the university template config (margins, fonts, spacing) and
generates a properly structured .docx file with:

  - Title page (title, author, institution, date)
  - Table of Contents placeholder (Word auto-generates on open)
  - Each thesis section as a Heading 1/2/3 with body paragraphs
  - Data tables formatted with header shading
  - Charts embedded as inline images (from BytesIO)
  - Formatted bibliography at the end
  - Page numbers in the footer
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from app.services.document_assembly.models import ThesisContent, Section, DataTable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template helper
# ---------------------------------------------------------------------------

def _load_template(name: str) -> dict[str, Any]:
    import json
    tmpl_dir = Path(__file__).parent / "templates"
    path = tmpl_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Template '{name}' not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# python-docx helpers
# ---------------------------------------------------------------------------

def _apply_page_setup(doc: Any, tmpl: dict) -> None:
    """Set page margins from template config."""
    from docx.shared import Inches
    page_cfg = tmpl.get("page", {})
    for section in doc.sections:
        section.top_margin    = Inches(page_cfg.get("margin_top_inches",    1.0))
        section.bottom_margin = Inches(page_cfg.get("margin_bottom_inches", 1.0))
        section.left_margin   = Inches(page_cfg.get("margin_left_inches",   1.5))
        section.right_margin  = Inches(page_cfg.get("margin_right_inches",  1.0))


def _set_paragraph_format(para: Any, tmpl: dict) -> None:
    """Apply body paragraph line spacing and spacing after."""
    from docx.shared import Pt
    from docx.enum.text import WD_LINE_SPACING
    spacing = tmpl.get("spacing", {})
    pf = para.paragraph_format
    pf.space_before = Pt(spacing.get("paragraph_space_before_pt", 0))
    pf.space_after  = Pt(spacing.get("paragraph_space_after_pt",  12))
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = spacing.get("line_spacing", 2.0)


def _set_run_font(run: Any, family: str, size_pt: float, bold: bool = False) -> None:
    from docx.shared import Pt
    run.font.name = family
    run.font.size = Pt(size_pt)
    run.bold = bold


def _add_title_page(doc: Any, content: ThesisContent, tmpl: dict) -> None:
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    font_cfg = tmpl.get("fonts", {})

    doc.add_paragraph()  # top spacing
    doc.add_paragraph()

    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(content.title)
    title_run.font.name = font_cfg.get("heading1_family", "Times New Roman")
    title_run.font.size = Pt(20)
    title_run.bold = True

    for _ in range(6):
        doc.add_paragraph()

    for line in [content.author, content.institution, content.date]:
        if line:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(line)
            r.font.name = font_cfg.get("body_family", "Times New Roman")
            r.font.size = Pt(font_cfg.get("body_size_pt", 12))

    doc.add_page_break()


def _add_toc_placeholder(doc: Any) -> None:
    """Insert a TOC placeholder field — Word updates it on first open."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    para = doc.add_paragraph()
    run = para.add_run()
    fld_char = OxmlElement("w:fldChar")
    fld_char.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = ' TOC \\o "1-3" \\h \\z \\u '
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "separate")
    fld_char3 = OxmlElement("w:fldChar")
    fld_char3.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char)
    run._r.append(instr_text)
    run._r.append(fld_char2)
    run._r.append(fld_char3)
    doc.add_page_break()


def _shade_cell(cell: Any, hex_color: str) -> None:
    """Apply background shading to a table cell."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  hex_color.lstrip("#"))
    tcPr.append(shd)


def _add_footer_page_numbers(doc: Any) -> None:
    """Add centre-aligned page number to the footer of every section."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    for section in doc.sections:
        footer = section.footer
        para   = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.clear()

        run = para.add_run()
        fld = OxmlElement("w:fldChar")
        fld.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.text = "PAGE"
        fld2 = OxmlElement("w:fldChar")
        fld2.set(qn("w:fldCharType"), "end")
        run._r.append(fld)
        run._r.append(instr)
        run._r.append(fld2)


# ---------------------------------------------------------------------------
# Section rendering
# ---------------------------------------------------------------------------

def _render_section(doc: Any, sec: Section, tmpl: dict, charts: dict[str, BytesIO]) -> None:
    """Add a single section (heading + body + tables + charts) to the document."""
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    font_cfg    = tmpl.get("fonts", {})
    spacing_cfg = tmpl.get("spacing", {})
    tbl_cfg     = tmpl.get("tables", {})
    chart_cfg   = tmpl.get("charts", {})

    # ── Heading ──────────────────────────────────────────────────────────────
    level = max(1, min(sec.heading_level, 3))
    heading = doc.add_heading(sec.name, level=level)
    hf = heading.paragraph_format
    before_key = f"heading{level}_space_before_pt"
    after_key  = f"heading{level}_space_after_pt"
    hf.space_before = Pt(spacing_cfg.get(before_key, 18))
    hf.space_after  = Pt(spacing_cfg.get(after_key, 6))
    # Override font on all runs
    fam_key  = f"heading{level}_family"
    size_key = f"heading{level}_size_pt"
    bold_key = f"heading{level}_bold"
    for run in heading.runs:
        run.font.name = font_cfg.get(fam_key, "Times New Roman")
        run.font.size = Pt(font_cfg.get(size_key, 14))
        run.bold      = font_cfg.get(bold_key, True)

    # ── Body text ─────────────────────────────────────────────────────────────
    if sec.text and sec.text.strip():
        for para_text in sec.text.split("\n\n"):
            para_text = para_text.strip()
            if not para_text:
                continue
            para = doc.add_paragraph()
            _set_paragraph_format(para, tmpl)
            run = para.add_run(para_text)
            _set_run_font(
                run,
                font_cfg.get("body_family", "Times New Roman"),
                font_cfg.get("body_size_pt", 12),
            )

    # ── Data tables + charts ──────────────────────────────────────────────────
    for table in sec.data_tables:
        # Table caption (above)
        if tbl_cfg.get("caption_position", "above") == "above" and table.caption:
            cap_para = doc.add_paragraph(f"Table: {table.caption}")
            cap_run  = cap_para.runs[0] if cap_para.runs else cap_para.add_run(f"Table: {table.caption}")
            cap_run.font.name   = font_cfg.get("body_family", "Times New Roman")
            cap_run.font.size   = Pt(font_cfg.get("caption_size_pt", 10))
            cap_run.font.italic = font_cfg.get("caption_italic", True)

        if table.headers and table.rows:
            n_cols = len(table.headers)
            n_rows = len(table.rows) + 1  # +1 header row
            word_table = doc.add_table(rows=n_rows, cols=n_cols)
            word_table.style = tbl_cfg.get("style", "Table Grid")

            # Header row
            hdr_cells = word_table.rows[0].cells
            shading   = tbl_cfg.get("header_shading", "#D9E1F2")
            for col_idx, hdr in enumerate(table.headers):
                cell = hdr_cells[col_idx]
                cell.text = str(hdr)
                _shade_cell(cell, shading)
                if cell.paragraphs:
                    run = cell.paragraphs[0].runs[0] if cell.paragraphs[0].runs else cell.paragraphs[0].add_run(str(hdr))
                    run.bold      = tbl_cfg.get("header_bold", True)
                    run.font.name = font_cfg.get("body_family", "Times New Roman")
                    run.font.size = Pt(font_cfg.get("body_size_pt", 12))

            # Data rows
            for row_idx, row in enumerate(table.rows):
                row_cells = word_table.rows[row_idx + 1].cells
                for col_idx, val in enumerate(row):
                    cell = row_cells[col_idx]
                    cell.text = str(val)
                    if cell.paragraphs:
                        for para in cell.paragraphs:
                            for run in para.runs:
                                run.font.name = font_cfg.get("body_family", "Times New Roman")
                                run.font.size = Pt(font_cfg.get("body_size_pt", 12))

        doc.add_paragraph()  # spacing after table

        # Chart
        chart_img = charts.get(table.id)
        if chart_img:
            chart_img.seek(0)
            width = Inches(chart_cfg.get("default_width_inches", 5.5))

            if chart_cfg.get("caption_position", "below") == "above" and table.caption:
                cap = doc.add_paragraph(f"Figure: {table.caption}")
                if cap.runs:
                    cap.runs[0].font.italic = True
                    cap.runs[0].font.size   = Pt(font_cfg.get("caption_size_pt", 10))

            doc.add_picture(chart_img, width=width)
            last_para = doc.paragraphs[-1]
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

            if chart_cfg.get("caption_position", "below") == "below" and table.caption:
                cap = doc.add_paragraph(f"Figure: {table.caption}")
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if cap.runs:
                    cap.runs[0].font.italic = True
                    cap.runs[0].font.size   = Pt(font_cfg.get("caption_size_pt", 10))

            doc.add_paragraph()

    # ── Subsections (recursive) ───────────────────────────────────────────────
    for sub in sec.subsections:
        _render_section(doc, sub, tmpl, charts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_word_doc(
    content: ThesisContent,
    charts: dict[str, BytesIO],
    template_name: str = "default",
    output_path: str | Path = "thesis.docx",
) -> Path:
    """
    Build a fully formatted Word document from ThesisContent.

    Parameters
    ----------
    content:
        Populated ThesisContent object.
    charts:
        Mapping ``{table_id: BytesIO PNG}`` from chart_generator.
    template_name:
        Name of the JSON template in ``templates/``.
    output_path:
        Destination ``.docx`` path.

    Returns
    -------
    Path
        Absolute path to the saved document.
    """
    try:
        from docx import Document
    except ImportError as exc:
        raise ImportError(
            "python-docx is required. Install: pip install python-docx"
        ) from exc

    tmpl     = _load_template(template_name)
    doc_cfg  = tmpl.get("document", {})
    font_cfg = tmpl.get("fonts", {})

    doc = Document()
    _apply_page_setup(doc, tmpl)

    # Title page
    if doc_cfg.get("title_page", True):
        _add_title_page(doc, content, tmpl)

    # TOC placeholder
    if doc_cfg.get("table_of_contents", True):
        _add_toc_placeholder(doc)

    # Abstract (if provided, as its own section before body sections)
    if content.abstract:
        abs_heading = doc.add_heading("Abstract", level=1)
        from docx.shared import Pt
        for run in abs_heading.runs:
            run.font.name = font_cfg.get("heading1_family", "Times New Roman")
            run.font.size = Pt(font_cfg.get("heading1_size_pt", 16))
        abs_para = doc.add_paragraph()
        _set_paragraph_format(abs_para, tmpl)
        r = abs_para.add_run(content.abstract)
        _set_run_font(r, font_cfg.get("body_family", "Times New Roman"), font_cfg.get("body_size_pt", 12))

    # Body sections
    for sec in content.sections:
        if doc_cfg.get("chapter_break", True) and sec.heading_level == 1:
            doc.add_page_break()
        _render_section(doc, sec, tmpl, charts)

    # Bibliography
    if content.bibliography:
        from app.services.citation import CitationFormatter, Reference
        from docx.shared import Pt
        doc.add_page_break()
        doc.add_heading("References", level=1)
        try:
            refs   = [Reference.from_dict(b) for b in content.bibliography]
            output = CitationFormatter(content.citation_style).format(refs)
            for entry in output.bibliography:
                p = doc.add_paragraph(style="List Number")
                _set_paragraph_format(p, tmpl)
                r = p.add_run(entry)
                _set_run_font(r, font_cfg.get("body_family", "Times New Roman"), font_cfg.get("body_size_pt", 12))
        except Exception as bib_exc:
            logger.warning("Bibliography formatting failed: %s", bib_exc)
            for b in content.bibliography:
                p = doc.add_paragraph(f"{b.get('author', '')} ({b.get('year', '')}). {b.get('title', '')}.")
                _set_paragraph_format(p, tmpl)

    # Page numbers
    if doc_cfg.get("page_numbers", True):
        _add_footer_page_numbers(doc)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    logger.info("Word document saved: %s", out)
    return out.resolve()
