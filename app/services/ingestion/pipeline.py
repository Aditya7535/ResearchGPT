"""
Ingestion pipeline orchestrator.

Ties together file extraction → section chunking → ChromaDB embedding.

Usage
-----
    from app.services.ingestion import IngestionPipeline

    pipeline = IngestionPipeline()                     # uses local ChromaDB
    result   = pipeline.ingest("path/to/paper.pdf")
    print(result)
    # IngestionResult(filename='paper.pdf', chunks_stored=7,
    #                 sections=['Abstract','Introduction','Methods',...])

Re-ingesting the same file is safe (upsert semantics).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.ingestion.chunker import TextChunk, chunk_document
from app.services.ingestion.embedder import DEFAULT_CHROMA_PATH, DEFAULT_COLLECTION, EmbeddingStore
from app.services.ingestion.extractors.base import ExtractedDocument

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported file types → extractor functions (lazy imports to avoid hard deps)
# ---------------------------------------------------------------------------

def _get_extractor(suffix: str):
    suffix = suffix.lower().lstrip(".")
    if suffix == "pdf":
        from app.services.ingestion.extractors.pdf import extract_pdf
        return extract_pdf
    if suffix in ("docx", "doc"):
        from app.services.ingestion.extractors.docx import extract_docx
        return extract_docx
    if suffix == "txt":
        from app.services.ingestion.extractors.txt import extract_txt
        return extract_txt
    raise ValueError(
        f"Unsupported file type '.{suffix}'. "
        "Supported: .pdf, .docx, .txt"
    )


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class IngestionResult:
    """Summary of a completed ingestion run."""

    filename:      str
    file_type:     str
    chunks_stored: int
    sections:      list[str]               = field(default_factory=list)
    document_id:   str | None              = None
    extractor_meta: dict                   = field(default_factory=dict)
    chunks:        list[TextChunk]         = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"IngestionResult("
            f"filename={self.filename!r}, "
            f"chunks_stored={self.chunks_stored}, "
            f"sections={self.sections})"
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class IngestionPipeline:
    """
    End-to-end document ingestion pipeline.

    Steps
    -----
    1. **Extract** — detect file type, call the appropriate extractor.
    2. **Chunk**   — split extracted content by section headers.
    3. **Embed**   — generate embeddings and upsert to ChromaDB.

    Parameters
    ----------
    chroma_path:
        Local filesystem path for the ChromaDB persistent store.
    collection_name:
        ChromaDB collection name.
    embedding_function:
        Optional custom ChromaDB EmbeddingFunction. Defaults to
        ``DefaultEmbeddingFunction`` (all-MiniLM-L6-v2 / ONNX).
    store:
        Inject a pre-built ``EmbeddingStore`` (mainly for testing).
    """

    def __init__(
        self,
        chroma_path: str = DEFAULT_CHROMA_PATH,
        collection_name: str = DEFAULT_COLLECTION,
        embedding_function: Any = None,
        store: EmbeddingStore | None = None,
    ) -> None:
        self._store = store or EmbeddingStore(
            persist_path=chroma_path,
            collection_name=collection_name,
            embedding_function=embedding_function,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        file_path: str | Path,
        document_id: str | None = None,
    ) -> IngestionResult:
        """
        Ingest a single file into ChromaDB.

        Parameters
        ----------
        file_path:
            Path to a ``.pdf``, ``.docx``, or ``.txt`` file.
        document_id:
            Optional logical ID (e.g. a database UUID). Stored in chunk
            metadata for cross-referencing with the main Postgres DB.

        Returns
        -------
        IngestionResult
        """
        path = Path(file_path)
        logger.info("▶  Ingesting: %s", path.name)

        # 1. Extract
        extractor = _get_extractor(path.suffix)
        doc: ExtractedDocument = extractor(path)

        # 2. Chunk
        chunks = chunk_document(doc)

        # 3. Embed + store
        stored = self._store.upsert_chunks(chunks, document_id=document_id)

        sections = list(dict.fromkeys(c.section for c in chunks))  # preserve order, dedupe

        result = IngestionResult(
            filename=doc.filename,
            file_type=doc.file_type,
            chunks_stored=stored,
            sections=sections,
            document_id=document_id,
            extractor_meta=doc.metadata,
            chunks=chunks,
        )
        logger.info("✔  %s", result)
        return result

    def ingest_bytes(
        self,
        content: bytes,
        filename: str,
        document_id: str | None = None,
    ) -> IngestionResult:
        """
        Ingest raw file bytes (e.g. from a FastAPI ``UploadFile``).

        Writes a temporary file, ingests it, then removes the temp file.

        Parameters
        ----------
        content:
            Raw file bytes.
        filename:
            Original filename including extension (determines extractor).
        document_id:
            Optional logical document ID.

        Returns
        -------
        IngestionResult
        """
        import tempfile, os

        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            result = self.ingest(tmp_path, document_id=document_id)
            # Override filename to use the original name, not the temp path
            result.filename = filename
            for chunk in result.chunks:
                chunk.filename = filename
            return result
        finally:
            os.unlink(tmp_path)

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        section_filter: str | None = None,
        filename_filter: str | None = None,
    ) -> list[dict]:
        """
        Semantic search over all ingested chunks.

        Parameters
        ----------
        query_text:
            Free-text query.
        n_results:
            Max results to return.
        section_filter:
            Restrict to a specific canonical section, e.g. ``"Methods"``.
        filename_filter:
            Restrict to a specific source file, e.g. ``"paper.pdf"``.

        Returns
        -------
        list[dict]
            Each item: ``{id, text, metadata, distance}``.
        """
        where: dict | None = None
        if section_filter and filename_filter:
            where = {"$and": [
                {"section": section_filter},
                {"source_filename": filename_filter},
            ]}
        elif section_filter:
            where = {"section": section_filter}
        elif filename_filter:
            where = {"source_filename": filename_filter}

        return self._store.query(query_text, n_results=n_results, where=where)

    @property
    def store(self) -> EmbeddingStore:
        """Direct access to the underlying EmbeddingStore."""
        return self._store
