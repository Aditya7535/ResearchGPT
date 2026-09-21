"""
Structuring Agent — Node 1 of the ResearchGPT LangGraph pipeline.

Responsibility
--------------
Given a set of ChromaDB chunks from the user's own uploaded documents,
propose a structured thesis outline and write a first-pass draft for
each section.

STRICT GROUNDING RULE: The agent MUST use only content present in the
retrieved chunks.  The system prompt explicitly forbids inventing claims,
adding external knowledge, or hallucinating citations.  If a section has
no supporting content, it is left empty with a [NO_CONTENT] marker.

Output keys written to PipelineState
-------------------------------------
    outline           : {section_name: one_line_description, ...}
    draft_sections    : {section_name: draft_text, ...}
    structuring_status: "ok" | "error"
    structuring_error : str (only on error)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.llm import get_llm, make_human_message, make_system_message
from app.agents.state import PipelineState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical thesis sections (order matters for the outline)
# ---------------------------------------------------------------------------
THESIS_SECTIONS = [
    "Abstract",
    "Introduction",
    "Literature Review",
    "Methods",
    "Results",
    "Discussion",
    "Conclusion",
    "References",
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are an academic writing assistant for a thesis structuring tool.

CRITICAL RULES — you MUST follow these exactly:
1. Use ONLY information present in the provided document chunks.
2. NEVER invent facts, statistics, claims, author names, or citations not found in the chunks.
3. If a thesis section has no supporting content in the chunks, write exactly: [NO_CONTENT]
4. Quote or closely paraphrase the source material; do not generalise beyond what is stated.
5. Respond ONLY with valid JSON — no markdown fences, no extra commentary.

Your task:
Given the document chunks below, produce a JSON object with two top-level keys:
  "outline"        : object mapping each section name to a one-sentence description
                     of what will be covered (or null if no content).
  "draft_sections" : object mapping each section name to 2–4 paragraphs of drafted text
                     synthesised strictly from the chunks (or "[NO_CONTENT]").

Sections to populate:
  Abstract, Introduction, Literature Review, Methods, Results, Discussion, Conclusion, References

Respond with ONLY the JSON object."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_chunk_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a numbered context block for the prompt."""
    lines: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        meta     = chunk.get("metadata", {})
        filename = meta.get("source_filename", "unknown")
        section  = meta.get("section", "")
        text     = chunk.get("text", "").strip()
        lines.append(
            f"[CHUNK {i}] source={filename!r}  section={section!r}\n{text}"
        )
    return "\n\n---\n\n".join(lines)


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Extract and parse the first JSON object from LLM output."""
    # Strip markdown code fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find a JSON object by scanning for { ... }
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def _validate_structure(data: dict) -> tuple[dict, dict]:
    """Ensure outline and draft_sections have all required section keys."""
    outline        = data.get("outline", {}) or {}
    draft_sections = data.get("draft_sections", {}) or {}

    for section in THESIS_SECTIONS:
        if section not in outline:
            outline[section] = None
        if section not in draft_sections:
            draft_sections[section] = "[NO_CONTENT]"

    return outline, draft_sections


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------

def structuring_agent(state: PipelineState) -> PipelineState:
    """
    LangGraph node — Structuring Agent.

    Reads:  state["retrieved_chunks"]
    Writes: state["outline"], state["draft_sections"],
            state["structuring_status"], state["structuring_error"]
    """
    logger.info("▶  Structuring Agent — start")
    chunks: list[dict] = state.get("retrieved_chunks", [])

    if not chunks:
        logger.warning("Structuring Agent: no chunks in state, producing empty draft.")
        return {
            **state,
            "outline":            {s: None for s in THESIS_SECTIONS},
            "draft_sections":     {s: "[NO_CONTENT]" for s in THESIS_SECTIONS},
            "structuring_status": "ok",
            "completed_agents":   state.get("completed_agents", []) + ["structuring"],
        }

    context   = _build_chunk_context(chunks)
    user_msg  = f"Document chunks:\n\n{context}"

    try:
        llm      = get_llm(temperature=0.1)
        messages = [make_system_message(_SYSTEM_PROMPT), make_human_message(user_msg)]
        response = llm.invoke(messages)
        raw      = response.content if hasattr(response, "content") else str(response)

        data              = _parse_llm_json(raw)
        outline, drafts   = _validate_structure(data)

        logger.info(
            "Structuring Agent: outline generated for %d sections, %d with content.",
            len(THESIS_SECTIONS),
            sum(1 for v in drafts.values() if v != "[NO_CONTENT]"),
        )
        return {
            **state,
            "outline":            outline,
            "draft_sections":     drafts,
            "structuring_status": "ok",
            "completed_agents":   state.get("completed_agents", []) + ["structuring"],
        }

    except Exception as exc:
        logger.error("Structuring Agent error: %s", exc, exc_info=True)
        return {
            **state,
            "outline":            {},
            "draft_sections":     {s: "[NO_CONTENT]" for s in THESIS_SECTIONS},
            "structuring_status": "error",
            "structuring_error":  str(exc),
            "errors":             state.get("errors", []) + [f"structuring: {exc}"],
        }
