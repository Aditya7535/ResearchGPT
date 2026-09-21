"""
Plain-text (.txt) extractor.

Handles UTF-8 with BOM, Latin-1, and falls back to cp1252.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.ingestion.extractors.base import ExtractedDocument

logger = logging.getLogger(__name__)

_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1", "cp1252")


def extract_txt(file_path: str | Path) -> ExtractedDocument:
    """
    Read a plain-text file and return an ExtractedDocument.

    Tries multiple encodings in order; raises ``UnicodeDecodeError`` only
    if none succeed.

    Parameters
    ----------
    file_path:
        Path to the ``.txt`` file.

    Returns
    -------
    ExtractedDocument
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Text file not found: {path}")

    logger.info("Extracting TXT: %s", path.name)

    raw_text: str | None = None
    used_encoding = ""
    for enc in _ENCODINGS:
        try:
            raw_text = path.read_text(encoding=enc)
            used_encoding = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if raw_text is None:
        raise UnicodeDecodeError(
            "utf-8", b"", 0, 1,
            f"Could not decode '{path.name}' with any of {_ENCODINGS}",
        )

    word_count = len(raw_text.split())
    logger.info(
        "TXT extracted: ~%d words (encoding=%s) — %s",
        word_count, used_encoding, path.name,
    )

    return ExtractedDocument(
        filename=path.name,
        file_type="txt",
        raw_text=raw_text,
        metadata={
            "word_count": word_count,
            "encoding": used_encoding,
            "source_path": str(path),
        },
    )
