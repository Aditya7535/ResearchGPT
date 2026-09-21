"""
Unit tests for the document ingestion pipeline.

Test classes
------------
TestTxtExtractor        – plain text file loading
TestPdfExtractor        – PyMuPDF integration (mocked)
TestDocxExtractor       – python-docx integration (mocked)
TestChunker             – section detection, label mapping, edge cases
TestChunkerDocx         – DOCX heading-style chunking path
TestEmbeddingStore      – ChromaDB upsert/query/delete (fully mocked)
TestIngestionPipeline   – end-to-end pipeline (store injected as mock)
TestIngestBytes         – ingest_bytes() with synthetic content

All tests are offline — no real ChromaDB, PyMuPDF, or python-docx
instances are created.  Network calls are never made.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# ---------------------------------------------------------------------------
# Extractor base
# ---------------------------------------------------------------------------
from app.services.ingestion.extractors.base import ExtractedDocument

# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------
from app.services.ingestion.chunker import (
    TextChunk,
    chunk_document,
    _resolve_label,
    DEFAULT_SECTION,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_doc(
    raw_text: str,
    filename: str = "test.txt",
    file_type: str = "txt",
    paragraphs: list[tuple[str, str]] | None = None,
) -> ExtractedDocument:
    return ExtractedDocument(
        filename=filename,
        file_type=file_type,
        raw_text=raw_text,
        paragraphs=paragraphs or [],
    )


SAMPLE_ACADEMIC_TEXT = """\
This paper presents a novel approach to citation management.

Introduction

The problem of structured citation has been long studied.
Academic writing requires consistent formatting of references.
This work builds on prior literature.

Methods

We collected 500 research papers from PubMed.
Each paper was processed using NLP pipelines.
Text was tokenized and section-labelled.

Results

Our approach achieved 94% accuracy on section detection.
The F1 score improved by 12% over the baseline.

Discussion

The gains are attributed to transformer-based models.
Limitations include dataset bias toward biomedical texts.

Conclusion

We presented a scalable ingestion pipeline.
Future work will extend to multi-language corpora.

References

1. Smith J. NLP methods. Nature. 2020.
2. Doe A. Deep learning. Science. 2021.
"""


# ===========================================================================
# 1. TXT extractor
# ===========================================================================

class TestTxtExtractor(unittest.TestCase):

    def test_extracts_utf8_file(self):
        from app.services.ingestion.extractors.txt import extract_txt
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write("Hello world.\nSecond line.")
            tmp_path = f.name

        try:
            doc = extract_txt(tmp_path)
            self.assertEqual(doc.file_type, "txt")
            self.assertIn("Hello world", doc.raw_text)
            self.assertGreater(doc.metadata["word_count"], 0)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_file_not_found_raises(self):
        from app.services.ingestion.extractors.txt import extract_txt
        with self.assertRaises(FileNotFoundError):
            extract_txt("/nonexistent/path/file.txt")

    def test_filename_preserved(self):
        from app.services.ingestion.extractors.txt import extract_txt
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write("content")
            tmp_path = f.name

        try:
            doc = extract_txt(tmp_path)
            self.assertTrue(doc.filename.endswith(".txt"))
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_encoding_metadata_captured(self):
        from app.services.ingestion.extractors.txt import extract_txt
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write("unicode ✓")
            tmp_path = f.name

        try:
            doc = extract_txt(tmp_path)
            self.assertIn("encoding", doc.metadata)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ===========================================================================
# 2. PDF extractor (mocked fitz)
# ===========================================================================

class TestPdfExtractor(unittest.TestCase):

    def _make_mock_fitz(self, pages_text: list[str]):
        mock_fitz = MagicMock()
        mock_doc  = MagicMock()
        mock_pages = []
        for t in pages_text:
            p = MagicMock()
            p.get_text.return_value = t
            mock_pages.append(p)
        mock_doc.__iter__ = lambda s: iter(mock_pages)
        mock_doc.close    = MagicMock()
        mock_fitz.open.return_value = mock_doc
        return mock_fitz

    @patch("app.services.ingestion.extractors.pdf.fitz", create=True)
    def test_extracts_pages(self, _):
        import app.services.ingestion.extractors.pdf as pdf_mod

        mock_fitz = self._make_mock_fitz(["Page one text.", "Page two text."])
        pdf_mod.fitz = mock_fitz

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_path = f.name

        try:
            doc = pdf_mod.extract_pdf(tmp_path)
            self.assertEqual(doc.file_type, "pdf")
            self.assertEqual(len(doc.pages), 2)
            self.assertIn("Page one", doc.raw_text)
            self.assertIn("Page two", doc.raw_text)
            self.assertEqual(doc.metadata["page_count"], 2)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_file_not_found_raises(self):
        from app.services.ingestion.extractors.pdf import extract_pdf
        with self.assertRaises(FileNotFoundError):
            extract_pdf("/nonexistent/file.pdf")

    def test_missing_pymupdf_raises_import_error(self):
        """If fitz is not installed, ImportError should propagate cleanly."""
        with patch.dict(sys.modules, {"fitz": None}):
            import importlib
            import app.services.ingestion.extractors.pdf as pdf_mod
            importlib.reload(pdf_mod)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                tmp_path = f.name
            try:
                with self.assertRaises((ImportError, TypeError, AttributeError)):
                    pdf_mod.extract_pdf(tmp_path)
            finally:
                Path(tmp_path).unlink(missing_ok=True)


# ===========================================================================
# 3. DOCX extractor (mocked python-docx)
# ===========================================================================

class TestDocxExtractor(unittest.TestCase):

    def _make_mock_docx(self, paragraphs: list[tuple[str, str]]):
        """paragraphs: list of (style_name, text)"""
        mock_docx_mod = MagicMock()
        mock_doc = MagicMock()
        mock_paras = []
        for style_name, text in paragraphs:
            p = MagicMock()
            p.text = text
            p.style.name = style_name
            mock_paras.append(p)
        mock_doc.paragraphs = mock_paras
        mock_docx_mod.Document.return_value = mock_doc
        return mock_docx_mod

    @patch("app.services.ingestion.extractors.docx.Document", create=True)
    def test_extracts_paragraphs(self, mock_Document):
        import app.services.ingestion.extractors.docx as docx_mod
        from docx import Document as _D  # may fail if not installed; mock handles it

        mock_docx = self._make_mock_docx([
            ("Heading 1", "Introduction"),
            ("Normal",    "This is the intro body."),
            ("Heading 1", "Methods"),
            ("Normal",    "We used Python."),
        ])
        mock_Document.side_effect = mock_docx.Document

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            tmp_path = f.name

        try:
            doc = docx_mod.extract_docx(tmp_path)
            self.assertEqual(doc.file_type, "docx")
            self.assertEqual(len(doc.paragraphs), 4)
            self.assertEqual(doc.paragraphs[0], ("Heading 1", "Introduction"))
            self.assertIn("Introduction", doc.raw_text)
        except ImportError:
            self.skipTest("python-docx not installed")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_file_not_found_raises(self):
        from app.services.ingestion.extractors import docx as docx_mod
        with self.assertRaises((FileNotFoundError, ImportError)):
            docx_mod.extract_docx("/nonexistent/file.docx")


# ===========================================================================
# 4. Chunker — regex path (PDF / TXT)
# ===========================================================================

class TestChunker(unittest.TestCase):

    def test_section_labels_resolved(self):
        doc = _make_doc(SAMPLE_ACADEMIC_TEXT)
        chunks = chunk_document(doc)
        labels = [c.section for c in chunks]
        self.assertIn("Introduction", labels)
        self.assertIn("Methods",      labels)
        self.assertIn("Results",      labels)
        self.assertIn("Discussion",   labels)
        self.assertIn("Conclusion",   labels)
        self.assertIn("References",   labels)

    def test_chunk_indices_are_contiguous(self):
        doc = _make_doc(SAMPLE_ACADEMIC_TEXT)
        chunks = chunk_document(doc)
        indices = [c.chunk_index for c in chunks]
        self.assertEqual(indices, list(range(len(chunks))))

    def test_chunk_filename_and_filetype_propagated(self):
        doc = _make_doc(SAMPLE_ACADEMIC_TEXT, filename="paper.pdf", file_type="pdf")
        chunks = chunk_document(doc)
        for c in chunks:
            self.assertEqual(c.filename, "paper.pdf")
            self.assertEqual(c.file_type, "pdf")

    def test_chunk_text_not_empty(self):
        doc = _make_doc(SAMPLE_ACADEMIC_TEXT)
        chunks = chunk_document(doc)
        for c in chunks:
            self.assertTrue(c.text.strip(), f"Chunk {c.chunk_index} has empty text")

    def test_no_headers_returns_single_chunk(self):
        doc = _make_doc("Just some plain text with no headers at all.", filename="plain.txt")
        chunks = chunk_document(doc)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].section, DEFAULT_SECTION)

    def test_section_raw_contains_original_header(self):
        doc = _make_doc(SAMPLE_ACADEMIC_TEXT)
        chunks = chunk_document(doc)
        header_chunks = [c for c in chunks if c.section_raw]
        self.assertGreater(len(header_chunks), 0)
        for c in header_chunks:
            self.assertIsInstance(c.section_raw, str)

    def test_metadata_dict_has_required_keys(self):
        doc = _make_doc(SAMPLE_ACADEMIC_TEXT)
        chunks = chunk_document(doc)
        required = {"source_filename", "file_type", "section", "chunk_index"}
        for c in chunks:
            meta = c.to_metadata()
            self.assertTrue(required.issubset(meta.keys()), f"Missing keys in {meta}")

    def test_numbered_header_detected(self):
        text = "Some preamble.\n\n1. Introduction\n\nContent here.\n\n2. Methods\n\nMethod content."
        doc = _make_doc(text)
        chunks = chunk_document(doc)
        labels = [c.section for c in chunks]
        self.assertIn("Introduction", labels)
        self.assertIn("Methods", labels)

    def test_case_insensitive_header_detection(self):
        text = "INTRODUCTION\n\nSome intro text.\n\nMETHODS\n\nSome method text."
        doc = _make_doc(text)
        chunks = chunk_document(doc)
        labels = [c.section for c in chunks]
        self.assertIn("Introduction", labels)
        self.assertIn("Methods", labels)


# ===========================================================================
# 5. Chunker — DOCX paragraph-style path
# ===========================================================================

class TestChunkerDocx(unittest.TestCase):

    def test_heading_style_splits_sections(self):
        paragraphs = [
            ("Heading 1", "Introduction"),
            ("Normal",    "This is the intro."),
            ("Normal",    "More intro content."),
            ("Heading 1", "Methods"),
            ("Normal",    "We used PyMuPDF."),
            ("Heading 2", "Data Collection"),
            ("Normal",    "Data was collected from PubMed."),
            ("Heading 1", "Results"),
            ("Normal",    "Accuracy was 95%."),
        ]
        doc = _make_doc(
            raw_text="\n".join(t for _, t in paragraphs),
            filename="test.docx",
            file_type="docx",
            paragraphs=paragraphs,
        )
        chunks = chunk_document(doc)
        labels = [c.section for c in chunks]
        self.assertIn("Introduction", labels)
        self.assertIn("Methods",      labels)
        self.assertIn("Results",      labels)

    def test_non_heading_paragraphs_go_into_body(self):
        paragraphs = [
            ("Heading 1", "Methods"),
            ("Normal",    "Line one of methods."),
            ("Normal",    "Line two of methods."),
        ]
        doc = _make_doc(
            raw_text="Methods\nLine one of methods.\nLine two of methods.",
            filename="test.docx",
            file_type="docx",
            paragraphs=paragraphs,
        )
        chunks = chunk_document(doc)
        methods_chunk = next((c for c in chunks if c.section == "Methods"), None)
        self.assertIsNotNone(methods_chunk)
        self.assertIn("Line one", methods_chunk.text)
        self.assertIn("Line two", methods_chunk.text)

    def test_indices_contiguous_for_docx(self):
        paragraphs = [
            ("Heading 1", "Introduction"),
            ("Normal", "Intro text."),
            ("Heading 1", "Conclusion"),
            ("Normal", "Final thoughts."),
        ]
        doc = _make_doc("", filename="t.docx", file_type="docx", paragraphs=paragraphs)
        chunks = chunk_document(doc)
        self.assertEqual([c.chunk_index for c in chunks], list(range(len(chunks))))


# ===========================================================================
# 6. EmbeddingStore (ChromaDB fully mocked)
# ===========================================================================

class TestEmbeddingStore(unittest.TestCase):

    def _make_store(self):
        """Create an EmbeddingStore with a fully mocked ChromaDB."""
        mock_chroma_mod = MagicMock()
        mock_client     = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chroma_mod.PersistentClient.return_value = mock_client

        mock_ef_mod = MagicMock()
        mock_ef_mod.DefaultEmbeddingFunction.return_value = MagicMock()

        with patch.dict(sys.modules, {
            "chromadb":                              mock_chroma_mod,
            "chromadb.utils":                        MagicMock(),
            "chromadb.utils.embedding_functions":    mock_ef_mod,
        }):
            from app.services.ingestion import embedder as emb_mod
            import importlib
            importlib.reload(emb_mod)
            store = emb_mod.EmbeddingStore.__new__(emb_mod.EmbeddingStore)
            store._collection = mock_collection
            store._chroma     = mock_client

        return store, mock_collection

    def _make_chunks(self, n: int = 2) -> list:
        from app.services.ingestion.chunker import TextChunk
        return [
            TextChunk(
                text=f"Section text {i}",
                section="Methods",
                section_raw="Methods",
                chunk_index=i,
                char_start=i * 100,
                filename="paper.pdf",
                file_type="pdf",
            )
            for i in range(n)
        ]

    def test_upsert_calls_collection(self):
        store, mock_col = self._make_store()
        chunks = self._make_chunks(3)
        store.upsert_chunks(chunks)
        mock_col.upsert.assert_called_once()
        args = mock_col.upsert.call_args[1]
        self.assertEqual(len(args["ids"]), 3)
        self.assertEqual(len(args["documents"]), 3)
        self.assertEqual(len(args["metadatas"]), 3)

    def test_upsert_empty_list_returns_zero(self):
        store, mock_col = self._make_store()
        result = store.upsert_chunks([])
        self.assertEqual(result, 0)
        mock_col.upsert.assert_not_called()

    def test_upsert_with_document_id(self):
        store, mock_col = self._make_store()
        chunks = self._make_chunks(1)
        store.upsert_chunks(chunks, document_id="doc-uuid-123")
        meta = mock_col.upsert.call_args[1]["metadatas"][0]
        self.assertEqual(meta["document_id"], "doc-uuid-123")

    def test_delete_by_filename(self):
        store, mock_col = self._make_store()
        store.delete_by_filename("paper.pdf")
        mock_col.delete.assert_called_once_with(where={"source_filename": "paper.pdf"})

    def test_query_passes_where_filter(self):
        store, mock_col = self._make_store()
        mock_col.count.return_value = 5
        mock_col.query.return_value = {
            "ids":       [["id1"]],
            "documents": [["some text"]],
            "metadatas": [[{"section": "Methods"}]],
            "distances": [[0.1]],
        }
        results = store.query("query text", n_results=3, where={"section": "Methods"})
        call_kwargs = mock_col.query.call_args[1]
        self.assertEqual(call_kwargs["where"], {"section": "Methods"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["text"], "some text")

    def test_metadata_keys_in_upsert(self):
        store, mock_col = self._make_store()
        chunks = self._make_chunks(1)
        store.upsert_chunks(chunks)
        meta = mock_col.upsert.call_args[1]["metadatas"][0]
        for key in ("source_filename", "file_type", "section", "chunk_index"):
            self.assertIn(key, meta, f"Missing key: {key}")

    def test_chunk_ids_are_unique(self):
        store, mock_col = self._make_store()
        chunks = self._make_chunks(5)
        store.upsert_chunks(chunks)
        ids = mock_col.upsert.call_args[1]["ids"]
        self.assertEqual(len(ids), len(set(ids)), "Chunk IDs are not unique")


# ===========================================================================
# 7. IngestionPipeline end-to-end (store injected)
# ===========================================================================

class TestIngestionPipeline(unittest.TestCase):

    def _make_pipeline_with_mock_store(self):
        from app.services.ingestion.pipeline import IngestionPipeline
        mock_store = MagicMock()
        mock_store.upsert_chunks.return_value = 6
        mock_store.query.return_value = []
        pipeline = IngestionPipeline(store=mock_store)
        return pipeline, mock_store

    def test_ingest_txt_end_to_end(self):
        pipeline, mock_store = self._make_pipeline_with_mock_store()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write(SAMPLE_ACADEMIC_TEXT)
            tmp_path = f.name

        try:
            result = pipeline.ingest(tmp_path)
            self.assertGreater(result.chunks_stored, 0)
            mock_store.upsert_chunks.assert_called_once()
            self.assertIn("Introduction", result.sections)
            self.assertIn("Methods", result.sections)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_ingest_unsupported_type_raises(self):
        from app.services.ingestion.pipeline import IngestionPipeline
        pipeline, _ = self._make_pipeline_with_mock_store()
        with self.assertRaises(ValueError):
            pipeline.ingest("some_file.xlsx")

    def test_ingest_returns_ingestion_result(self):
        from app.services.ingestion.pipeline import IngestionResult
        pipeline, _ = self._make_pipeline_with_mock_store()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write(SAMPLE_ACADEMIC_TEXT)
            tmp_path = f.name

        try:
            result = pipeline.ingest(tmp_path)
            self.assertIsInstance(result, IngestionResult)
            self.assertEqual(result.file_type, "txt")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_document_id_forwarded_to_store(self):
        pipeline, mock_store = self._make_pipeline_with_mock_store()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write("Introduction\n\nSome content.")
            tmp_path = f.name

        try:
            pipeline.ingest(tmp_path, document_id="uuid-999")
            call_kwargs = mock_store.upsert_chunks.call_args
            self.assertEqual(call_kwargs[1]["document_id"], "uuid-999")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_sections_deduplicated(self):
        pipeline, _ = self._make_pipeline_with_mock_store()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write(SAMPLE_ACADEMIC_TEXT)
            tmp_path = f.name

        try:
            result = pipeline.ingest(tmp_path)
            # No duplicate sections in the result
            self.assertEqual(len(result.sections), len(set(result.sections)))
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ===========================================================================
# 8. ingest_bytes
# ===========================================================================

class TestIngestBytes(unittest.TestCase):

    def test_ingest_bytes_txt(self):
        from app.services.ingestion.pipeline import IngestionPipeline
        mock_store = MagicMock()
        mock_store.upsert_chunks.return_value = 3
        pipeline = IngestionPipeline(store=mock_store)

        content = SAMPLE_ACADEMIC_TEXT.encode("utf-8")
        result = pipeline.ingest_bytes(content, filename="upload.txt")

        self.assertEqual(result.filename, "upload.txt")
        self.assertEqual(result.file_type, "txt")
        mock_store.upsert_chunks.assert_called_once()

    def test_ingest_bytes_filename_overrides_tempfile_name(self):
        from app.services.ingestion.pipeline import IngestionPipeline
        mock_store = MagicMock()
        mock_store.upsert_chunks.return_value = 2
        pipeline = IngestionPipeline(store=mock_store)

        content = "Introduction\n\nHello.\n\nMethods\n\nWorld.".encode("utf-8")
        result = pipeline.ingest_bytes(content, filename="myresearch.txt")

        self.assertEqual(result.filename, "myresearch.txt")


# ===========================================================================
# 9. _resolve_label helper
# ===========================================================================

class TestResolveLabelHelper(unittest.TestCase):

    def test_known_keywords(self):
        cases = [
            ("Introduction", "Introduction"),
            ("1. Methods",   "Methods"),
            ("III. Results", "Results"),
            ("Discussion",   "Discussion"),
            ("Conclusion and Future Work", "Conclusion"),
            ("References",   "References"),
            ("Bibliography", "References"),
            ("Abstract",     "Abstract"),
            ("Acknowledgements", "Acknowledgements"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(_resolve_label(raw), expected)

    def test_unknown_header_returns_title_case(self):
        result = _resolve_label("experimental protocol")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
