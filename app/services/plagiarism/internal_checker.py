"""
Internal plagiarism checker — compares thesis text against the user's own
ChromaDB source corpus.

Mechanism
---------
  1. Split each thesis section into overlapping text chunks (by paragraph,
     then by sentence window if paragraphs are too long).
  2. For each chunk, query ChromaDB for the top-k most similar stored source
     chunks using cosine similarity.
  3. Convert ChromaDB cosine distance → similarity score:
         similarity = 1.0 - distance
     (ChromaDB HNSW with cosine space returns distance ∈ [0, 1] where
      0 = identical embeddings.)
  4. Flag chunks where similarity ≥ SIMILARITY_THRESHOLD.
  5. Attribute each flagged chunk to the source file + section.

Tuning constants
----------------
  SIMILARITY_THRESHOLD : float  (default 0.85) — minimum score to flag
  MIN_CHUNK_WORDS      : int    (default 15)  — ignore very short fragments
  MAX_CHUNK_WORDS      : int    (default 80)  — split long paragraphs
  TOP_K                : int    (default 3)   — ChromaDB results per chunk query
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.services.plagiarism.models import SimilarityFinding, SectionReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD: float = 0.85   # flag at 85%+ similarity
MIN_CHUNK_WORDS:      int   = 15     # skip very short phrases
MAX_CHUNK_WORDS:      int   = 80     # split longer paragraphs
TOP_K:                int   = 3      # top ChromaDB matches per chunk


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """
    Split text into sentences using punctuation boundaries.
    Avoids NLTK dependency — handles the vast majority of academic text.
    """
    # Abbreviation-safe split: require uppercase after period
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", text)
    return [p.strip() for p in parts if p.strip()]


def split_into_chunks(
    text: str,
    min_words: int = MIN_CHUNK_WORDS,
    max_words: int = MAX_CHUNK_WORDS,
) -> list[str]:
    """
    Produce overlapping text chunks suitable for embedding-based comparison.

    Strategy:
      - Primary split: double-newline (paragraph boundaries).
      - If a paragraph exceeds max_words, split by sentences and accumulate
        into sliding windows of ≤ max_words.
      - Skip chunks below min_words (too short to be meaningful).
    """
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []

    for para in paragraphs:
        words = para.split()
        if len(words) < min_words:
            continue
        if len(words) <= max_words:
            chunks.append(para)
            continue

        # Long paragraph → sentence-windowed chunks
        sentences = _split_sentences(para)
        window: list[str] = []
        window_words = 0

        for sent in sentences:
            sent_words = len(sent.split())
            if window_words + sent_words > max_words and window:
                chunk = " ".join(window)
                if len(chunk.split()) >= min_words:
                    chunks.append(chunk)
                # Overlap: keep last sentence for context continuity
                window      = [window[-1], sent] if window else [sent]
                window_words = len(" ".join(window).split())
            else:
                window.append(sent)
                window_words += sent_words

        if window:
            chunk = " ".join(window)
            if len(chunk.split()) >= min_words:
                chunks.append(chunk)

    return chunks


# ---------------------------------------------------------------------------
# Similarity computation
# ---------------------------------------------------------------------------

def _distance_to_similarity(distance: float) -> float:
    """
    Convert ChromaDB HNSW cosine distance to a 0–1 similarity score.

    ChromaDB with space='cosine' reports: distance = 1 − cosine_similarity,
    so: similarity = 1 − distance, clamped to [0, 1].
    """
    return max(0.0, min(1.0, 1.0 - float(distance)))


def _best_match(
    results: list[dict],
    threshold: float,
) -> dict[str, Any] | None:
    """Return the highest-similarity result above threshold, or None."""
    best: dict | None = None
    best_sim = -1.0
    for r in results:
        sim = _distance_to_similarity(r["distance"])
        if sim >= threshold and sim > best_sim:
            best    = r
            best_sim = sim
    return best


# ---------------------------------------------------------------------------
# Section-level internal check
# ---------------------------------------------------------------------------

def check_section_internal(
    section_name: str,
    text: str,
    embedding_store: Any,                    # EmbeddingStore instance
    threshold: float = SIMILARITY_THRESHOLD,
    top_k: int = TOP_K,
    document_ids: list[str] | None = None,   # restrict to specific docs
) -> SectionReport:
    """
    Compare one thesis section's text against the ChromaDB source corpus.

    Parameters
    ----------
    section_name:
        Name of the thesis section (for labelling findings).
    text:
        Full text of the section.
    embedding_store:
        An initialised EmbeddingStore instance.
    threshold:
        Minimum similarity score to flag (0–1).
    top_k:
        Number of ChromaDB results to retrieve per chunk.
    document_ids:
        If provided, restrict comparison to only these document IDs.

    Returns
    -------
    SectionReport
    """
    chunks     = split_into_chunks(text)
    word_count = len(text.split())
    findings:  list[SimilarityFinding] = []

    for chunk_idx, chunk in enumerate(chunks):
        try:
            where: dict | None = None
            if document_ids and len(document_ids) == 1:
                where = {"document_id": document_ids[0]}
            elif document_ids:
                where = {"document_id": {"$in": document_ids}}

            results = embedding_store.query(
                query_text=chunk,
                n_results=top_k,
                where=where,
            )
        except Exception as exc:
            logger.warning("ChromaDB query failed for chunk %d: %s", chunk_idx, exc)
            continue

        best = _best_match(results, threshold)
        if best is None:
            continue

        sim  = _distance_to_similarity(best["distance"])
        meta = best.get("metadata", {})
        src  = "{}:{}".format(
            meta.get("source_filename", "unknown"),
            meta.get("section", "?"),
        )

        findings.append(
            SimilarityFinding(
                text=chunk,
                section=section_name,
                similarity_score=sim,
                source_type="internal",
                source_ref=src,
                source_text=best.get("text"),
                chunk_index=chunk_idx,
            )
        )
        logger.debug(
            "INTERNAL FLAG  section=%r  score=%.2f  source=%r  chunk[%d]=%r…",
            section_name, sim, src, chunk_idx, chunk[:60],
        )

    logger.info(
        "Internal check: section=%r  chunks=%d  flagged=%d",
        section_name, len(chunks), len(findings),
    )
    return SectionReport(
        section_name=section_name,
        word_count=word_count,
        chunks_checked=len(chunks),
        findings=findings,
    )


# ---------------------------------------------------------------------------
# Document-level internal check
# ---------------------------------------------------------------------------

def run_internal_check(
    sections: dict[str, str],
    embedding_store: Any,
    threshold: float = SIMILARITY_THRESHOLD,
    top_k: int = TOP_K,
    document_ids: list[str] | None = None,
) -> list[SectionReport]:
    """
    Run internal similarity check across all thesis sections.

    Parameters
    ----------
    sections:
        Ordered dict of ``{section_name: section_text}``.
    embedding_store:
        Initialised EmbeddingStore.
    threshold / top_k / document_ids:
        Forwarded to ``check_section_internal``.

    Returns
    -------
    list[SectionReport]
        One report per section, in the same order as ``sections``.
    """
    reports: list[SectionReport] = []
    for name, text in sections.items():
        if not text or text.strip() == "[NO_CONTENT]":
            reports.append(
                SectionReport(
                    section_name=name,
                    word_count=0,
                    chunks_checked=0,
                    findings=[],
                )
            )
            continue
        reports.append(
            check_section_internal(
                section_name=name,
                text=text,
                embedding_store=embedding_store,
                threshold=threshold,
                top_k=top_k,
                document_ids=document_ids,
            )
        )
    return reports
