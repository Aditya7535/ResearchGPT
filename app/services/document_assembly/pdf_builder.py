"""
PDF builder — renders ThesisContent to a PDF via WeasyPrint.

Strategy: HTML → CSS → WeasyPrint → PDF
----------------------------------------
Generating HTML from scratch gives full control over typography and layout.
WeasyPrint consumes the HTML + CSS and produces print-quality PDF.

Windows note
------------
WeasyPrint on Windows requires the GTK3 runtime:
    https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer
Install WeasyPrint itself with: pip install weasyprint

Alternatively, if WeasyPrint is unavailable, the builder raises ImportError
with a clear message so the caller can skip PDF generation gracefully.
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from app.services.document_assembly.models import ThesisContent, Section, DataTable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template loader (shared with word_builder)
# ---------------------------------------------------------------------------

def _load_template(name: str) -> dict[str, Any]:
    import json
    path = Path(__file__).parent / "templates" / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Template '{name}' not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# CSS generation from template config
# ---------------------------------------------------------------------------

def _generate_css(tmpl: dict) -> str:
    page   = tmpl.get("page", {})
    fonts  = tmpl.get("fonts", {})
    space  = tmpl.get("spacing", {})
    charts = tmpl.get("charts", {})

    top    = page.get("margin_top_inches",    1.0)
    bottom = page.get("margin_bottom_inches", 1.0)
    left   = page.get("margin_left_inches",   1.5)
    right  = page.get("margin_right_inches",  1.0)

    body_family  = fonts.get("body_family",    "Times New Roman")
    body_size    = fonts.get("body_size_pt",   12)
    h1_size      = fonts.get("heading1_size_pt", 16)
    h2_size      = fonts.get("heading2_size_pt", 14)
    h3_size      = fonts.get("heading3_size_pt", 12)
    caption_size = fonts.get("caption_size_pt", 10)

    line_spacing = space.get("line_spacing", 2.0)
    para_after   = space.get("paragraph_space_after_pt", 12)
    h1_before    = space.get("heading1_space_before_pt", 24)
    h1_after     = space.get("heading1_space_after_pt",  12)
    h2_before    = space.get("heading2_space_before_pt", 18)
    h2_after     = space.get("heading2_space_after_pt",  6)
    h3_before    = space.get("heading3_space_before_pt", 12)
    h3_after     = space.get("heading3_space_after_pt",  6)

    chart_width  = charts.get("default_width_inches", 5.5)
    chart_width_cm = chart_width * 2.54

    return f"""
@page {{
    size: A4;
    margin: {top}in {right}in {bottom}in {left}in;
    @bottom-center {{
        content: counter(page);
        font-family: '{body_family}', serif;
        font-size: {caption_size}pt;
        color: #555;
    }}
}}

* {{ box-sizing: border-box; }}

body {{
    font-family: '{body_family}', 'Georgia', serif;
    font-size: {body_size}pt;
    line-height: {line_spacing};
    color: #1a1a1a;
    margin: 0; padding: 0;
}}

p {{
    margin: 0 0 {para_after}pt 0;
    text-align: justify;
}}

h1 {{
    font-family: '{fonts.get("heading1_family", body_family)}', serif;
    font-size: {h1_size}pt;
    font-weight: {'bold' if fonts.get('heading1_bold', True) else 'normal'};
    margin: {h1_before}pt 0 {h1_after}pt 0;
    page-break-before: always;
    color: #1a1a2e;
}}

h1.no-break {{ page-break-before: avoid; }}

h2 {{
    font-family: '{fonts.get("heading2_family", body_family)}', serif;
    font-size: {h2_size}pt;
    font-weight: {'bold' if fonts.get('heading2_bold', True) else 'normal'};
    margin: {h2_before}pt 0 {h2_after}pt 0;
}}

h3 {{
    font-family: '{fonts.get("heading3_family", body_family)}', serif;
    font-size: {h3_size}pt;
    font-weight: {'bold' if fonts.get('heading3_bold', True) else 'normal'};
    margin: {h3_before}pt 0 {h3_after}pt 0;
}}

/* Title page */
.title-page {{
    text-align: center;
    page-break-after: always;
    padding-top: 120pt;
}}
.title-page h1 {{
    font-size: 22pt;
    page-break-before: avoid;
    margin-bottom: 30pt;
    color: #1a1a2e;
}}
.title-page .meta {{ font-size: {body_size}pt; line-height: 2; color: #444; }}

/* TOC */
.toc {{ page-break-after: always; }}
.toc h1 {{ page-break-before: avoid; }}
.toc-entry {{ display: flex; justify-content: space-between; margin: 4pt 0; }}
.toc-entry.indent {{ padding-left: 20pt; }}

/* Tables */
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 12pt 0 4pt 0;
    font-size: {body_size}pt;
}}
th {{
    background-color: #D9E1F2;
    font-weight: bold;
    padding: 6pt 8pt;
    border: 1px solid #BCC6DE;
    text-align: left;
}}
td {{
    padding: 5pt 8pt;
    border: 1px solid #D0D0D0;
    vertical-align: top;
}}
tr:nth-child(even) td {{ background-color: #F5F7FB; }}

/* Captions */
.caption {{
    font-size: {caption_size}pt;
    font-style: italic;
    color: #555;
    text-align: center;
    margin: 4pt 0 10pt 0;
}}

/* Charts */
.chart-container {{
    text-align: center;
    margin: 10pt 0;
}}
.chart-container img {{
    max-width: {chart_width_cm}cm;
    height: auto;
}}

/* Bibliography */
.bibliography ol {{ padding-left: 20pt; }}
.bibliography li {{ margin-bottom: 8pt; text-align: left; }}

/* Abstract */
.abstract {{ margin-bottom: 24pt; }}
"""


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def _b64_img(buf: BytesIO) -> str:
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode()


def _section_to_html(sec: Section, charts: dict[str, BytesIO], tmpl: dict) -> str:
    level = max(1, min(sec.heading_level, 3))
    parts: list[str] = [f"<h{level}>{_esc(sec.name)}</h{level}>"]

    if sec.text and sec.text.strip():
        for para in sec.text.split("\n\n"):
            para = para.strip()
            if para:
                parts.append(f"<p>{_esc(para)}</p>")

    charts_cfg = tmpl.get("charts", {})
    for table in sec.data_tables:
        # Table caption above
        parts.append(f'<p class="caption">Table: {_esc(table.caption)}</p>')

        if table.headers and table.rows:
            parts.append("<table>")
            # Header
            parts.append("<thead><tr>")
            for h in table.headers:
                parts.append(f"<th>{_esc(str(h))}</th>")
            parts.append("</tr></thead>")
            # Rows
            parts.append("<tbody>")
            for row in table.rows:
                parts.append("<tr>")
                for cell in row:
                    parts.append(f"<td>{_esc(str(cell))}</td>")
                parts.append("</tr>")
            parts.append("</tbody></table>")

        # Chart
        chart_buf = charts.get(table.id)
        if chart_buf:
            img_src = _b64_img(chart_buf)
            parts.append(
                f'<div class="chart-container">'
                f'<img src="{img_src}" alt="{_esc(table.caption)}"/>'
                f'<p class="caption">Figure: {_esc(table.caption)}</p>'
                f'</div>'
            )

    for sub in sec.subsections:
        parts.append(_section_to_html(sub, charts, tmpl))

    return "\n".join(parts)


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def generate_html(content: ThesisContent, charts: dict[str, BytesIO], tmpl: dict) -> str:
    """Build the complete HTML string for the thesis."""
    css = _generate_css(tmpl)
    parts: list[str] = [
        "<!DOCTYPE html><html lang='en'><head>",
        "<meta charset='UTF-8'>",
        f"<title>{_esc(content.title)}</title>",
        f"<style>{css}</style>",
        "</head><body>",
    ]

    # Title page
    parts.append('<div class="title-page">')
    parts.append(f"<h1>{_esc(content.title)}</h1>")
    parts.append('<div class="meta">')
    for line in [content.author, content.institution, content.date]:
        if line:
            parts.append(f"<p>{_esc(line)}</p>")
    parts.append("</div></div>")

    # Abstract
    if content.abstract:
        parts.append('<div class="abstract">')
        parts.append('<h1 class="no-break">Abstract</h1>')
        parts.append(f"<p>{_esc(content.abstract)}</p>")
        parts.append("</div>")

    # Body sections
    for sec in content.sections:
        parts.append(_section_to_html(sec, charts, tmpl))

    # Bibliography
    if content.bibliography:
        parts.append('<div class="bibliography">')
        parts.append('<h1>References</h1>')
        try:
            from app.services.citation import CitationFormatter, Reference
            refs   = [Reference.from_dict(b) for b in content.bibliography]
            output = CitationFormatter(content.citation_style).format(refs)
            parts.append("<ol>")
            for entry in output.bibliography:
                parts.append(f"<li>{_esc(entry)}</li>")
            parts.append("</ol>")
        except Exception as bib_exc:
            logger.warning("Bibliography formatting in HTML failed: %s", bib_exc)
            parts.append("<ol>")
            for b in content.bibliography:
                raw = f"{b.get('author', '')} ({b.get('year', '')}). {b.get('title', '')}."
                parts.append(f"<li>{_esc(raw)}</li>")
            parts.append("</ol>")
        parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_pdf(
    content: ThesisContent,
    charts: dict[str, BytesIO],
    template_name: str = "default",
    output_path: str | Path = "thesis.pdf",
) -> Path:
    """
    Build a PDF from ThesisContent using WeasyPrint.

    Parameters
    ----------
    content:
        Populated ThesisContent object.
    charts:
        Mapping ``{table_id: BytesIO PNG}`` from chart_generator.
    template_name:
        Name of the JSON template in ``templates/``.
    output_path:
        Destination ``.pdf`` path.

    Returns
    -------
    Path
        Absolute path to the saved PDF.

    Raises
    ------
    ImportError
        If WeasyPrint is not installed (with installation instructions).
    """
    try:
        from weasyprint import HTML as WeasyHTML
    except ImportError as exc:
        raise ImportError(
            "WeasyPrint is required for PDF generation.\n"
            "  pip install weasyprint\n"
            "Windows also requires GTK3 runtime:\n"
            "  https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer"
        ) from exc

    tmpl        = _load_template(template_name)
    html_string = generate_html(content, charts, tmpl)
    extra_css   = tmpl.get("pdf_css_extra", "")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Rendering PDF via WeasyPrint → %s", out)
    WeasyHTML(string=html_string).write_pdf(
        str(out),
        stylesheets=[],   # CSS is already embedded in the HTML <style> block
        presentational_hints=True,
    )
    logger.info("PDF saved: %s", out)
    return out.resolve()
