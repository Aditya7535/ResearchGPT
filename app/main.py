"""
ResearchGPT FastAPI Backend Application.

Provides RESTful API endpoints for:
- Document ingestion & ChromaDB vector storage
- Multi-agent LangGraph pipeline execution (Structuring, Citation, Formatting)
- Guided interview question generation & source-tagged prose synthesis
- Plagiarism checking (cosine similarity against ChromaDB)
- Document assembly & export (DOCX & WeasyPrint PDF)
- System health checks
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("researchgpt.api")

# Configuration from environment
CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_data")
COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION", "researchgpt_documents")
EXPORT_DIR = os.environ.get("EXPORT_DIR", "./exports")
Path(EXPORT_DIR).mkdir(parents=True, exist_ok=True)
Path(CHROMA_PATH).mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="ResearchGPT API",
    version="1.0.0",
    description="Multi-Agent Academic Paper Analysis and Document Generation API",
)

# Enable CORS for local dev and container networking
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class PipelineRunRequest(BaseModel):
    document_ids: List[str] = Field(default_factory=list)
    citation_style: str = "apa"
    template_name: str = "default"
    n_chunks: int = 20
    extra_state: Optional[Dict[str, Any]] = None


class InterviewGenerateRequest(BaseModel):
    section_name: str
    partial_content: str = ""
    domain: str = "General Academic"
    num_questions: int = 4


class InterviewAnswerRequest(BaseModel):
    section_name: str
    qna_pairs: List[Dict[str, Any]]
    partial_content: str = ""


class PlagiarismCheckRequest(BaseModel):
    sections: Dict[str, str]
    threshold: float = 0.80
    document_ids: List[str] = Field(default_factory=list)
    run_external: bool = False


class CitationFormatRequest(BaseModel):
    citations: List[Dict[str, Any]]
    style: str = "apa"


class ExportRequest(BaseModel):
    title: str = "Research Paper"
    authors: List[str] = Field(default_factory=lambda: ["ResearchGPT Author"])
    abstract: str = ""
    sections: Dict[str, str] = Field(default_factory=dict)
    bibliography: List[str] = Field(default_factory=list)
    template_name: str = "default"


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["System"])
async def health_check():
    """System health check and provider status."""
    llm_provider = os.environ.get("LLM_PROVIDER", "groq")
    groq_key_set = bool(os.environ.get("GROQ_API_KEY"))

    chroma_ok = False
    try:
        from app.services.ingestion.embedder import EmbeddingStore
        store = EmbeddingStore(persist_path=CHROMA_PATH, collection_name=COLLECTION_NAME)
        chroma_ok = True
        doc_count = store.count()
    except Exception as exc:
        logger.warning("ChromaDB probe error: %s", exc)
        doc_count = 0

    return {
        "status": "healthy",
        "version": "1.0.0",
        "llm_provider": llm_provider,
        "groq_configured": groq_key_set,
        "chroma_connected": chroma_ok,
        "chroma_chunk_count": doc_count,
    }


# ---------------------------------------------------------------------------
# Ingestion & Document Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/ingest", tags=["Ingestion"])
async def ingest_document(file: UploadFile = File(...)):
    """
    Ingest a research document (.pdf, .docx, .txt), extract sections,
    compute embeddings, and store in ChromaDB.
    """
    allowed_extensions = {".pdf", ".docx", ".doc", ".txt"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(allowed_extensions)}"
        )

    # Save uploaded bytes to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        from app.services.ingestion import IngestionPipeline
        pipeline = IngestionPipeline(
            chroma_path=CHROMA_PATH,
            collection_name=COLLECTION_NAME
        )
        result = pipeline.ingest(tmp_path)

        return {
            "status": "success",
            "filename": file.filename,
            "document_id": result.document_id,
            "chunks_stored": result.chunks_stored,
            "sections_found": result.sections,
            "char_count": result.char_count,
        }
    except Exception as exc:
        logger.error("Ingestion failed for %s: %s", file.filename, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest file: {str(exc)}"
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@app.get("/api/documents", tags=["Ingestion"])
async def list_documents():
    """List ingested documents and chunk totals from ChromaDB."""
    try:
        from app.services.ingestion.embedder import EmbeddingStore
        store = EmbeddingStore(persist_path=CHROMA_PATH, collection_name=COLLECTION_NAME)
        count = store.count()

        # Query all metadata to group by document_id and filename
        if count == 0:
            return {"total_chunks": 0, "documents": []}

        # Chroma query for metadata
        raw = store._collection.get(include=["metadatas"])
        metadatas = raw.get("metadatas", []) or []

        docs_map: Dict[str, Dict[str, Any]] = {}
        for m in metadatas:
            doc_id = m.get("document_id", "unknown")
            if doc_id not in docs_map:
                docs_map[doc_id] = {
                    "document_id": doc_id,
                    "filename": m.get("filename", "unknown"),
                    "sections": set(),
                    "chunk_count": 0,
                }
            docs_map[doc_id]["chunk_count"] += 1
            if m.get("section"):
                docs_map[doc_id]["sections"].add(m["section"])

        docs_list = [
            {
                "document_id": d["document_id"],
                "filename": d["filename"],
                "chunk_count": d["chunk_count"],
                "sections": sorted(list(d["sections"]))
            }
            for d in docs_map.values()
        ]

        return {"total_chunks": count, "documents": docs_list}
    except Exception as exc:
        logger.error("Failed to query documents: %s", exc)
        return {"total_chunks": 0, "documents": [], "error": str(exc)}


@app.get("/api/chunks", tags=["Ingestion"])
async def query_chunks(
    query: str = "",
    document_id: Optional[str] = None,
    section: Optional[str] = None,
    limit: int = 10,
):
    """Query semantic chunks from ChromaDB."""
    try:
        from app.services.ingestion.embedder import EmbeddingStore
        store = EmbeddingStore(persist_path=CHROMA_PATH, collection_name=COLLECTION_NAME)

        where: Optional[Dict[str, Any]] = None
        conditions = []
        if document_id:
            conditions.append({"document_id": document_id})
        if section:
            conditions.append({"section": section})

        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

        search_query = query if query.strip() else (section or "academic research")
        chunks = store.query(query_text=search_query, n_results=limit, where=where)

        return {"chunks": chunks, "count": len(chunks)}
    except Exception as exc:
        logger.error("Chunk query error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying chunks: {str(exc)}"
        )


# ---------------------------------------------------------------------------
# Multi-Agent Pipeline Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/pipeline/run", tags=["Agents"])
async def run_agent_pipeline(req: PipelineRunRequest):
    """
    Trigger the multi-agent LangGraph workflow:
    1. Retrieve relevant chunks from ChromaDB
    2. Structuring Agent generates outline & drafts
    3. Citation Agent verifies claims & builds bibliography
    4. Formatting Agent validates template & prepares final document
    """
    try:
        from app.agents.graph import build_graph, run_pipeline
        result = run_pipeline(
            graph=None,
            document_ids=req.document_ids,
            citation_style=req.citation_style,
            template_name=req.template_name,
            chroma_path=CHROMA_PATH,
            collection_name=COLLECTION_NAME,
            n_chunks=req.n_chunks,
            extra_state=req.extra_state,
        )

        return {
            "status": "success",
            "outline": result.get("outline", {}),
            "draft_sections": result.get("draft_sections", {}),
            "citation_report": result.get("citation_report", []),
            "formatted_bibliography": result.get("formatted_bibliography", []),
            "formatting_report": result.get("formatting_report", []),
            "final_draft": result.get("final_draft", ""),
            "completed_agents": result.get("completed_agents", []),
            "errors": result.get("errors", []),
        }
    except Exception as exc:
        logger.error("Pipeline run error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent pipeline execution failed: {str(exc)}"
        )


# ---------------------------------------------------------------------------
# Guided Interview Agent Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/interview/generate", tags=["Interview"])
async def generate_questions(req: InterviewGenerateRequest):
    """Generate dynamic follow-up questions for a thin/missing section."""
    try:
        from app.agents.interview import generate_interview_questions
        questions = generate_interview_questions(
            section_name=req.section_name,
            partial_content=req.partial_content,
            domain=req.domain,
            num_questions=req.num_questions,
        )
        return {
            "section_name": req.section_name,
            "questions": questions,
        }
    except Exception as exc:
        logger.error("Question generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate questions: {str(exc)}"
        )


@app.post("/api/interview/answer", tags=["Interview"])
async def answer_interview(req: InterviewAnswerRequest):
    """
    Synthesize user answers and uploaded text into academic prose,
    tagging every sentence with its source.
    """
    try:
        from app.agents.interview import synthesize_interview_section
        result = synthesize_interview_section(
            section_name=req.section_name,
            qna_pairs=req.qna_pairs,
            partial_content=req.partial_content,
        )
        return result
    except Exception as exc:
        logger.error("Answer synthesis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to synthesize answers: {str(exc)}"
        )


# ---------------------------------------------------------------------------
# Plagiarism & Citation Formatting Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/plagiarism/check", tags=["Plagiarism"])
async def check_plagiarism(req: PlagiarismCheckRequest):
    """Run cosine similarity plagiarism check against ChromaDB source corpus."""
    try:
        from app.services.plagiarism import PlagiarismChecker, SubscriptionLevel
        checker = PlagiarismChecker(
            chroma_path=CHROMA_PATH,
            collection_name=COLLECTION_NAME,
            subscription_level=SubscriptionLevel.FREE,
        )

        report = checker.check(
            sections=req.sections,
            run_external=req.run_external,
            threshold=req.threshold,
            document_ids=req.document_ids if req.document_ids else None,
        )

        return {
            "overall_similarity_pct": report.overall_similarity_pct,
            "verdict": report.verdict,
            "section_reports": [
                {
                    "section_name": s.section_name,
                    "max_similarity_pct": s.max_similarity_pct,
                    "flagged_matches_count": len(s.flagged_matches),
                    "matches": [
                        {
                            "suspect_text": m.suspect_text,
                            "source_text": m.source_text,
                            "similarity_pct": m.similarity_pct,
                            "document_id": m.document_id,
                            "source_section": m.source_section,
                        }
                        for m in s.flagged_matches
                    ],
                }
                for s in report.section_reports
            ],
            "markdown_summary": report.to_markdown(),
        }
    except Exception as exc:
        logger.error("Plagiarism check error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Plagiarism check failed: {str(exc)}"
        )


@app.post("/api/citation/format", tags=["Citation"])
async def format_citations(req: CitationFormatRequest):
    """Format bibliography and in-text citations using citeproc-py."""
    try:
        from app.services.citation import format_citations as run_format_citations
        output = run_format_citations(req.citations, style=req.style)
        return {
            "in_text": output.in_text,
            "bibliography": output.bibliography,
            "style": req.style,
        }
    except Exception as exc:
        logger.error("Citation formatting error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Citation formatting failed: {str(exc)}"
        )


# ---------------------------------------------------------------------------
# Document Assembly & Export Endpoints (DOCX & PDF)
# ---------------------------------------------------------------------------

@app.post("/api/export/docx", tags=["Export"])
async def export_word_document(req: ExportRequest):
    """Assemble and download a Microsoft Word (.docx) thesis document."""
    try:
        from app.services.document_assembly import DocumentAssembler, ThesisContent

        content_dict = {
            "title": req.title,
            "authors": req.authors,
            "abstract": req.abstract,
            "sections": [
                {"name": name, "content": text}
                for name, text in req.sections.items()
            ],
            "bibliography": req.bibliography,
        }

        content = ThesisContent.from_dict(content_dict)
        assembler = DocumentAssembler(template_name=req.template_name)

        out_dir = Path(EXPORT_DIR) / "docx"
        out_dir.mkdir(parents=True, exist_ok=True)
        result = assembler.assemble(content, output_dir=out_dir)

        if not result.word_path or not Path(result.word_path).exists():
            raise RuntimeError("Word document generation failed to produce a file.")

        safe_filename = f"{req.title.replace(' ', '_')}.docx"
        return FileResponse(
            path=str(result.word_path),
            filename=safe_filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as exc:
        logger.error("DOCX assembly failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DOCX generation failed: {str(exc)}"
        )


@app.post("/api/export/pdf", tags=["Export"])
async def export_pdf_document(req: ExportRequest):
    """Assemble and download a print-ready PDF thesis document."""
    try:
        from app.services.document_assembly import DocumentAssembler, ThesisContent

        content_dict = {
            "title": req.title,
            "authors": req.authors,
            "abstract": req.abstract,
            "sections": [
                {"name": name, "content": text}
                for name, text in req.sections.items()
            ],
            "bibliography": req.bibliography,
        }

        content = ThesisContent.from_dict(content_dict)
        assembler = DocumentAssembler(template_name=req.template_name)

        out_dir = Path(EXPORT_DIR) / "pdf"
        out_dir.mkdir(parents=True, exist_ok=True)
        result = assembler.assemble(content, output_dir=out_dir)

        if not result.pdf_path or not Path(result.pdf_path).exists():
            # If PDF engine failed (e.g. WeasyPrint GTK runtime missing on host), return warning info
            warning_msg = "; ".join(result.warnings) if result.warnings else "PDF compiler unavailable."
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"PDF generation failed: {warning_msg}"
            )

        safe_filename = f"{req.title.replace(' ', '_')}.pdf"
        return FileResponse(
            path=str(result.pdf_path),
            filename=safe_filename,
            media_type="application/pdf",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("PDF assembly failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {str(exc)}"
        )
