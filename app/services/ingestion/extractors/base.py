"""
Base dataclass shared by all extractors.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedDocument:
    """
    Output of a file extractor.

    Attributes
    ----------
    filename:
        Original filename (no path), e.g. ``"paper.pdf"``.
    file_type:
        Lower-case extension without dot: ``"pdf"``, ``"docx"``, ``"txt"``.
    raw_text:
        Full plain-text content of the document (may contain newlines).
    pages:
        For PDFs: per-page text list. Empty for other formats.
    paragraphs:
        For DOCX: structured list of (style_name, text) tuples.
        Allows the chunker to use heading styles directly.
        Empty for PDF/TXT.
    metadata:
        Extractor-level metadata (page count, word count, etc.).
    """

    filename: str
    file_type: str
    raw_text: str
    pages: list[str] = field(default_factory=list)
    paragraphs: list[tuple[str, str]] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
