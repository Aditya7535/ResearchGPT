"""
Section-aware text chunker for academic documents.

Strategy
--------
1. For DOCX: use Word heading styles (Heading 1, Heading 2, …) directly.
2. For PDF/TXT: apply regex patterns to detect section headers in the
   raw text (case-insensitive, handles numbered headings like "1. Introduction").

Section taxonomy (canonical labels)
------------------------------------
  Abstract · Introduction · Background · Literature Review
  Methods · Results · Discussion · Conclusion · References · Appendix

Each chunk produced carries:
    section      : canonical section label (str)
    section_raw  : original header text as found in the document
    chunk_index  : 0-based position within the document
    char_start   : character offset of chunk start in raw_text
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

from app.services.ingestion.extractors.base import ExtractedDocument

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section taxonomy
# ---------------------------------------------------------------------------

# Maps lower-case keyword → canonical label
_KEYWORD_TO_LABEL: dict[str, str] = {
    "abstract":          "Abstract",
    "introduction":      "Introduction",
    "background":        "Background",
    "literature":        "Literature Review",
    "related work":      "Literature Review",
    "method":            "Methods",
    "methodology":       "Methods",
    "material":          "Methods",
    "experiment":        "Results",
    "result":            "Results",
    "finding":           "Results",
    "evaluation":        "Results",
    "discussion":        "Discussion",
    "analysis":          "Discussion",
    "conclusion":        "Conclusion",
    "concluding":        "Conclusion",
    "future work":       "Conclusion",
    "limitation":        "Conclusion",
    "acknowledgement":   "Acknowledgements",
    "acknowledgment":    "Acknowledgements",
    "reference":         "References",
    "bibliography":      "References",
    "appendix":          "Appendix",
    "supplement":        "Appendix",
}

# Ordered by keyword length (longest first) avoids prefix shadowing
_SORTED_KEYWORDS = sorted(_KEYWORD_TO_LABEL.keys(), key=len, reverse=True)

# Header line pattern for raw text:
#   optional leading number+dot/paren  → "1.", "2.1", "(III)"
#   followed by one of our keywords
_HEADER_RE = re.compile(
    r"^(?:[\d]+(?:\.[\d]+)*\.?\s+|[IVXLC]+\.\s+|\([IVXLC]+\)\s+)?"
    r"(" + "|".join(re.escape(k) for k in _SORTED_KEYWORDS) + r")",
    re.IGNORECASE | re.MULTILINE,
)

# Word heading style prefix
_WORD_HEADING_RE = re.compile(r"^Heading\s+\d+$", re.IGNORECASE)

DEFAULT_SECTION = "Preamble"


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

@dataclass
class TextChunk:
    """A single section chunk ready for embedding."""

    text: str
    section: str             # canonical label
    section_raw: str         # text of the header line
    chunk_index: int         # 0-based within document
    char_start: int          # offset in raw_text
    filename: str
    file_type: str
    extra_metadata: dict = field(default_factory=dict)

    def to_metadata(self) -> dict:
        """Flat metadata dict suitable for ChromaDB."""
        return {
            "source_filename": self.filename,
            "file_type":       self.file_type,
            "section":         self.section,
            "section_raw":     self.section_raw,
            "chunk_index":     self.chunk_index,
            "char_start":      self.char_start,
            **self.extra_metadata,
        }


# ---------------------------------------------------------------------------
# Keyword → canonical label
# ---------------------------------------------------------------------------

def _resolve_label(header_text: str) -> str:
    """Map a raw header string to the nearest canonical section label."""
    lower = header_text.lower()
    for keyword in _SORTED_KEYWORDS:
        if keyword in lower:
            return _KEYWORD_TO_LABEL[keyword]
    return header_text.strip().title()


# ---------------------------------------------------------------------------
# DOCX-structured chunking (uses paragraph styles)
# ---------------------------------------------------------------------------

def _chunk_from_paragraphs(doc: ExtractedDocument) -> list[TextChunk]:
    """Split a DOCX document into chunks using Word heading styles."""
    chunks: list[TextChunk] = []
    current_section_raw = DEFAULT_SECTION
    current_label = DEFAULT_SECTION
    buffer: list[str] = []
    char_start = 0

    def _flush(idx: int) -> TextChunk | None:
        text = "\n".join(buffer).strip()
        if not text:
            return None
        return TextChunk(
            text=text,
            section=current_label,
            section_raw=current_section_raw,
            chunk_index=idx,
            char_start=char_start,
            filename=doc.filename,
            file_type=doc.file_type,
        )

    para_char = 0
    for style, text in doc.paragraphs:
        is_heading = bool(_WORD_HEADING_RE.match(style)) or style.lower() == "title"
        if is_heading:
            chunk = _flush(len(chunks))
            if chunk:
                chunks.append(chunk)
            current_section_raw = text
            current_label = _resolve_label(text)
            char_start = para_char
            buffer = []
        else:
            buffer.append(text)
        para_char += len(text) + 1  # +1 for newline

    chunk = _flush(len(chunks))
    if chunk:
        chunks.append(chunk)

    return chunks


# ---------------------------------------------------------------------------
# Raw-text regex chunking (PDF / TXT)
# ---------------------------------------------------------------------------

def _chunk_from_raw_text(doc: ExtractedDocument) -> list[TextChunk]:
    """Split raw text into chunks by regex-detected section headers."""
    text = doc.raw_text

    # Find all header matches
    splits: list[tuple[int, int, str]] = []  # (start, end, matched_text)
    for m in _HEADER_RE.finditer(text):
        # Only treat as heading if the line is short (< 120 chars)
        line_end = text.find("\n", m.start())
        if line_end == -1:
            line_end = len(text)
        line = text[m.start():line_end].strip()
        if len(line) <= 120:
            splits.append((m.start(), line_end, line))

    if not splits:
        # No headers found: return entire doc as one chunk
        logger.warning("No section headers detected in '%s'; treating as single chunk.", doc.filename)
        return [
            TextChunk(
                text=text.strip(),
                section=DEFAULT_SECTION,
                section_raw="",
                chunk_index=0,
                char_start=0,
                filename=doc.filename,
                file_type=doc.file_type,
            )
        ]

    chunks: list[TextChunk] = []

    # Preamble before first header
    preamble = text[: splits[0][0]].strip()
    if preamble:
        chunks.append(
            TextChunk(
                text=preamble,
                section=DEFAULT_SECTION,
                section_raw="",
                chunk_index=0,
                char_start=0,
                filename=doc.filename,
                file_type=doc.file_type,
            )
        )

    for i, (hdr_start, hdr_end, hdr_text) in enumerate(splits):
        body_start = hdr_end
        body_end = splits[i + 1][0] if i + 1 < len(splits) else len(text)
        body = text[body_start:body_end].strip()

        chunks.append(
            TextChunk(
                text=body,
                section=_resolve_label(hdr_text),
                section_raw=hdr_text,
                chunk_index=len(chunks),
                char_start=hdr_start,
                filename=doc.filename,
                file_type=doc.file_type,
            )
        )

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_document(doc: ExtractedDocument) -> list[TextChunk]:
    """
    Split an ExtractedDocument into section-labelled TextChunks.

    Uses DOCX paragraph styles when available; falls back to regex
    header detection for PDF and plain-text.

    Parameters
    ----------
    doc:
        Output of one of the extractor functions.

    Returns
    -------
    list[TextChunk]
        Ordered list of chunks. Each carries ``section``, ``section_raw``,
        ``chunk_index``, ``char_start``, ``filename``, and ``file_type``.
    """
    if doc.paragraphs:
        logger.debug("Chunking '%s' via DOCX paragraph styles.", doc.filename)
        chunks = _chunk_from_paragraphs(doc)
    else:
        logger.debug("Chunking '%s' via regex header detection.", doc.filename)
        chunks = _chunk_from_raw_text(doc)

    # Re-index to guarantee contiguous 0-based indices
    for idx, chunk in enumerate(chunks):
        chunk.chunk_index = idx

    logger.info(
        "Chunked '%s' → %d section chunks: %s",
        doc.filename,
        len(chunks),
        [c.section for c in chunks],
    )
    return chunks
