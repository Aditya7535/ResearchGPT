"""
PDF text extractor using PyMuPDF (fitz).

PyMuPDF preserves layout information and handles complex multi-column
academic papers better than pdfminer or PyPDF2.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.ingestion.extractors.base import ExtractedDocument

logger = logging.getLogger(__name__)


def extract_pdf(file_path: str | Path) -> ExtractedDocument:
    """
    Extract text from a PDF file page-by-page using PyMuPDF.

    Parameters
    ----------
    file_path:
        Path to the PDF file.

    Returns
    -------
    ExtractedDocument
        ``raw_text`` is the full concatenated text.
        ``pages`` contains per-page text (useful for page-level metadata).

    Raises
    ------
    ImportError
        If PyMuPDF (``fitz``) is not installed.
    FileNotFoundError
        If *file_path* does not exist.
    RuntimeError
        If PyMuPDF cannot open or parse the file.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF is required for PDF extraction. "
            "Install with: pip install pymupdf"
        ) from exc

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    logger.info("Extracting PDF: %s", path.name)

    pages: list[str] = []
    try:
        doc = fitz.open(str(path))
        for page in doc:
            # "text" mode preserves line breaks; "blocks" mode groups paragraphs
            text = page.get_text("text")
            pages.append(text)
        doc.close()
    except Exception as exc:
        raise RuntimeError(f"Failed to parse PDF '{path.name}': {exc}") from exc

    raw_text = "\n".join(pages)
    word_count = len(raw_text.split())

    logger.info(
        "PDF extracted: %d pages, ~%d words — %s",
        len(pages), word_count, path.name,
    )

    return ExtractedDocument(
        filename=path.name,
        file_type="pdf",
        raw_text=raw_text,
        pages=pages,
        metadata={
            "page_count": len(pages),
            "word_count": word_count,
            "source_path": str(path),
        },
    )
