"""
ChromaDB embedding store for the ingestion pipeline.

Uses ChromaDB's local persistent client with its built-in default
embedding function (all-MiniLM-L6-v2 via ONNX — no GPU needed).
A custom ``EmbeddingFunction`` can be injected at construction time.

Collection schema
-----------------
Collection name : ``"researchgpt_documents"``  (configurable)

Per document chunk the following are stored:
    id        : ``"{filename}::{chunk_index}"``
    document  : chunk text (used for embedding + retrieval)
    metadata  : {source_filename, file_type, section, section_raw,
                 chunk_index, char_start, document_id}
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from app.services.ingestion.chunker import TextChunk

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION  = "researchgpt_documents"
DEFAULT_CHROMA_PATH = "./chroma_data"


def _make_chunk_id(filename: str, chunk_index: int) -> str:
    """Stable, collision-resistant ID for a chunk."""
    raw = f"{filename}::{chunk_index}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16] + f"_{chunk_index}"


class EmbeddingStore:
    """
    Wraps a ChromaDB persistent collection.

    Parameters
    ----------
    persist_path:
        Filesystem path where ChromaDB stores its data.
    collection_name:
        Name of the ChromaDB collection to use / create.
    embedding_function:
        Any ChromaDB-compatible ``EmbeddingFunction``.
        Defaults to ``chromadb.utils.embedding_functions.DefaultEmbeddingFunction``
        (all-MiniLM-L6-v2 via ONNXRuntime — pure Python, no GPU).
    """

    def __init__(
        self,
        persist_path: str = DEFAULT_CHROMA_PATH,
        collection_name: str = DEFAULT_COLLECTION,
        embedding_function: Any = None,
    ) -> None:
        try:
            import chromadb
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        except ImportError as exc:
            raise ImportError(
                "chromadb is required. Install with: pip install chromadb"
            ) from exc

        self._chroma = chromadb.PersistentClient(path=persist_path)
        ef = embedding_function or DefaultEmbeddingFunction()

        self._collection = self._chroma.get_or_create_collection(
            name=collection_name,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "EmbeddingStore ready — collection '%s' at '%s' (%d existing docs)",
            collection_name, persist_path, self._collection.count(),
        )

    # ------------------------------------------------------------------
    # Core write operations
    # ------------------------------------------------------------------

    def upsert_chunks(
        self,
        chunks: list[TextChunk],
        document_id: str | None = None,
    ) -> int:
        """
        Embed and upsert a list of TextChunks into ChromaDB.

        Uses ``upsert`` so re-ingesting the same file is idempotent.

        Parameters
        ----------
        chunks:
            Chunks produced by ``chunker.chunk_document()``.
        document_id:
            Optional logical document ID (e.g. a UUID from the DB).
            Stored in each chunk's metadata.

        Returns
        -------
        int
            Number of chunks upserted.
        """
        if not chunks:
            logger.warning("upsert_chunks called with empty list.")
            return 0

        ids:       list[str]        = []
        documents: list[str]        = []
        metadatas: list[dict]       = []

        for chunk in chunks:
            if not chunk.text.strip():
                continue  # skip empty sections

            chunk_id = _make_chunk_id(chunk.filename, chunk.chunk_index)
            meta = chunk.to_metadata()
            if document_id:
                meta["document_id"] = document_id

            ids.append(chunk_id)
            documents.append(chunk.text)
            metadatas.append(meta)

        if not ids:
            return 0

        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(
            "Upserted %d chunks from '%s' into collection.",
            len(ids),
            chunks[0].filename,
        )
        return len(ids)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """
        Semantic search over stored chunks.

        Parameters
        ----------
        query_text:
            Natural-language query string.
        n_results:
            Maximum number of results to return.
        where:
            Optional ChromaDB ``where`` filter, e.g.
            ``{"section": "Methods"}`` or
            ``{"source_filename": "paper.pdf"}``.

        Returns
        -------
        list[dict]
            Each dict has keys: ``id``, ``text``, ``metadata``, ``distance``.
        """
        kwargs: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": min(n_results, self._collection.count() or 1),
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        output: list[dict] = []
        for i, (doc_id, doc_text, meta, dist) in enumerate(
            zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ):
            output.append({
                "id":       doc_id,
                "text":     doc_text,
                "metadata": meta,
                "distance": dist,
            })
        return output

    def delete_by_filename(self, filename: str) -> None:
        """Remove all chunks that originated from *filename*."""
        self._collection.delete(where={"source_filename": filename})
        logger.info("Deleted all chunks for filename '%s'.", filename)

    def count(self) -> int:
        """Total number of chunks in the collection."""
        return self._collection.count()
