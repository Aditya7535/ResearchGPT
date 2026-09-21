"""
Citation Agent — Node 2 of the ResearchGPT LangGraph pipeline.

Responsibility
--------------
For every section in draft_sections:
  1. Extract factual claims made in the text.
  2. For each claim, search the retrieved_chunks to find supporting evidence.
  3. If supporting evidence exists, mark the claim SUPPORTED and record the
     source chunk metadata (filename, section).
  4. If no supporting evidence is found, mark the claim FLAGGED (unsupported).
  5. Collect all References-section text chunks and format them using the
     CitationFormatter from Phase 2 (app.services.citation).

Output keys written to PipelineState
-------------------------------------
    citation_report        : list[CitationFinding dict]
    formatted_bibliography : list[str] from CitationFormatter
    citation_status        : "ok" | "error"
    citation_error         : str (only on error)

CitationFinding schema
-----------------------
    {
        "claim":     str,               # the factual claim extracted
        "section":   str,               # which thesis section it appears in
        "status":    "SUPPORTED" | "FLAGGED",
        "source":    str | None,        # filename:section of supporting chunk
        "evidence":  str | None,        # verbatim snippet from chunk
    }
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
# System prompt — claim extraction + grounding check
# ---------------------------------------------------------------------------
_CLAIM_EXTRACT_PROMPT = """You are an academic fact-checker for a thesis citation tool.

Given a thesis section text and a set of source document chunks, you must:
1. Extract every distinct factual claim from the section text (statistics, named findings, methodology descriptions, attributed statements).
2. For each claim, search the source chunks for verbatim or near-verbatim supporting evidence.
3. Classify each claim as SUPPORTED (found in chunks) or FLAGGED (not found).

RULES:
- Only mark a claim SUPPORTED if you can quote specific chunk text that backs it up.
- Do not invent sources.
- Respond ONLY with valid JSON — no markdown fences.

JSON schema:
{
  "findings": [
    {
      "claim":    "<the factual claim>",
      "status":   "SUPPORTED" | "FLAGGED",
      "source":   "<filename:section>" or null,
      "evidence": "<verbatim chunk snippet>" or null
    }
  ]
}"""


# ---------------------------------------------------------------------------
# Reference chunk → citation dict converter
# ---------------------------------------------------------------------------

def _chunk_to_citation_dict(chunk: dict, idx: int) -> dict[str, Any] | None:
    """
    Try to parse a References-section chunk into a citation input dict.

    Chunks tagged with section='References' often contain numbered reference
    lines. This extracts the most basic fields for the citation formatter.
    Returns None if unparseable.
    """
    text = chunk.get("text", "").strip()
    if not text:
        return None

    meta = chunk.get("metadata", {})

    # Attempt minimal extraction: author(s) and year
    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    doi_match  = re.search(r"10\.\d{4,}/\S+", text, re.IGNORECASE)

    year  = int(year_match.group()) if year_match else None
    doi   = doi_match.group().rstrip(".,)") if doi_match else None

    return {
        "id":      f"ref_{idx}",
        "title":   text[:120],          # use first 120 chars as title placeholder
        "authors": [],
        "year":    year,
        "doi":     doi,
        "type":    "article-journal",
    }


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------

def citation_agent(state: PipelineState) -> PipelineState:
    """
    LangGraph node — Citation Agent.

    Reads:  state["draft_sections"], state["retrieved_chunks"],
            state["citation_style"]
    Writes: state["citation_report"], state["formatted_bibliography"],
            state["citation_status"], state["citation_error"]
    """
    logger.info("▶  Citation Agent — start")

    draft_sections: dict[str, str] = state.get("draft_sections", {})
    chunks:         list[dict]     = state.get("retrieved_chunks", [])
    style:          str            = state.get("citation_style", "apa")

    if not draft_sections:
        logger.warning("Citation Agent: no draft sections in state.")
        return {
            **state,
            "citation_report":        [],
            "formatted_bibliography": [],
            "citation_status":        "ok",
            "completed_agents":       state.get("completed_agents", []) + ["citation"],
        }

    # Build compact chunk context for the LLM
    chunk_context_lines = []
    for c in chunks:
        meta = c.get("metadata", {})
        src  = f"{meta.get('source_filename', '?')}:{meta.get('section', '?')}"
        chunk_context_lines.append(f"[{src}] {c.get('text', '').strip()[:400]}")
    chunk_context = "\n\n".join(chunk_context_lines)

    all_findings: list[dict] = []
    llm = get_llm(temperature=0.0)  # deterministic for fact-checking

    try:
        for section_name, section_text in draft_sections.items():
            if not section_text or section_text.strip() == "[NO_CONTENT]":
                continue

            user_msg = (
                f"=== THESIS SECTION: {section_name} ===\n\n"
                f"{section_text}\n\n"
                f"=== SOURCE CHUNKS ===\n\n"
                f"{chunk_context}"
            )

            messages = [
                make_system_message(_CLAIM_EXTRACT_PROMPT),
                make_human_message(user_msg),
            ]
            response = llm.invoke(messages)
            raw      = response.content if hasattr(response, "content") else str(response)

            # Parse JSON
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
            try:
                data     = json.loads(raw)
                findings = data.get("findings", [])
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                findings = json.loads(match.group()).get("findings", []) if match else []

            # Attach section to each finding
            for f in findings:
                f["section"] = section_name
            all_findings.extend(findings)

        # ── Format bibliography from Reference chunks ───────────────────────
        ref_chunks = [
            c for c in chunks
            if c.get("metadata", {}).get("section") == "References"
        ]
        formatted_bibliography: list[str] = []

        if ref_chunks:
            try:
                from app.services.citation import CitationFormatter, Reference
                citation_dicts = [
                    d for i, c in enumerate(ref_chunks)
                    if (d := _chunk_to_citation_dict(c, i)) is not None
                ]
                if citation_dicts:
                    refs   = [Reference.from_dict(d) for d in citation_dicts]
                    output = CitationFormatter(style).format(refs)
                    formatted_bibliography = output.bibliography
            except Exception as bib_exc:
                logger.warning("Bibliography formatting failed: %s", bib_exc)

        supported = sum(1 for f in all_findings if f.get("status") == "SUPPORTED")
        flagged   = sum(1 for f in all_findings if f.get("status") == "FLAGGED")
        logger.info(
            "Citation Agent: %d claims checked — %d SUPPORTED, %d FLAGGED.",
            len(all_findings), supported, flagged,
        )

        return {
            **state,
            "citation_report":        all_findings,
            "formatted_bibliography": formatted_bibliography,
            "citation_status":        "ok",
            "completed_agents":       state.get("completed_agents", []) + ["citation"],
        }

    except Exception as exc:
        logger.error("Citation Agent error: %s", exc, exc_info=True)
        return {
            **state,
            "citation_report":        [],
            "formatted_bibliography": [],
            "citation_status":        "error",
            "citation_error":         str(exc),
            "errors":                 state.get("errors", []) + [f"citation: {exc}"],
        }
