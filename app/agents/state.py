"""
Shared LangGraph state for the ResearchGPT multi-agent pipeline.

The state dict flows through every node in the graph.
Each agent reads what it needs and writes its own output keys —
no agent ever mutates another agent's output keys.

State key ownership
-------------------
Input (supplied by caller):
    document_ids       : list of ChromaDB document_ids to scope retrieval
    citation_style     : "apa" | "vancouver"
    template_name      : university template identifier
    retrieved_chunks   : raw chunks from ChromaDB (populated by graph entry)

Structuring Agent writes:
    outline            : proposed thesis outline dict
    draft_sections     : dict[section_name → section_text]
    structuring_status : "ok" | "error"
    structuring_error  : error message if status == "error"

Citation Agent writes:
    citation_report    : list of CitationFinding (supported/flagged)
    formatted_bibliography : list[str]
    citation_status    : "ok" | "error"
    citation_error     : error message

Formatting Agent writes:
    formatting_report  : list of FormattingIssue
    final_draft        : assembled final markdown document
    formatting_status  : "ok" | "error"
    formatting_error   : error message

Pipeline metadata:
    errors             : accumulated error strings from any agent
    completed_agents   : list of agent names that ran successfully
"""

from __future__ import annotations

from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    # ── Input ────────────────────────────────────────────────────────────────
    document_ids:           list[str]         # filter ChromaDB by document_id
    citation_style:         str               # "apa" | "vancouver"
    template_name:          str               # key into templates dir
    retrieved_chunks:       list[dict]        # raw {text, metadata, distance}

    # ── Structuring Agent ────────────────────────────────────────────────────
    outline:                dict[str, Any]    # {section: description, ...}
    draft_sections:         dict[str, str]    # {section: text, ...}
    structuring_status:     str
    structuring_error:      str

    # ── Citation Agent ────────────────────────────────────────────────────────
    citation_report:        list[dict]        # list of CitationFinding dicts
    formatted_bibliography: list[str]
    citation_status:        str
    citation_error:         str

    # ── Formatting Agent ─────────────────────────────────────────────────────
    formatting_report:      list[dict]        # list of FormattingIssue dicts
    final_draft:            str               # assembled markdown
    formatting_status:      str
    formatting_error:       str

    # ── Guided Interview Agent ───────────────────────────────────────────────
    interview_history:      dict[str, list[dict]] # {section: list of Q&A dicts}
    interview_gaps:         dict[str, list[dict]] # {section: list of open gaps}
    tagged_sections:        dict[str, list[dict]] # {section: list of tagged sentence dicts}
    interview_status:       str
    interview_error:        str

    # ── Pipeline meta ─────────────────────────────────────────────────────────
    errors:                 list[str]
    completed_agents:       list[str]
