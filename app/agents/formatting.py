"""
Formatting Agent — Node 3 of the ResearchGPT LangGraph pipeline.

Responsibility
--------------
1. Load the university template config (JSON schema).
2. Validate draft_sections against:
      a) Required sections present (not [NO_CONTENT])
      b) Per-section word count minimums
      c) No flagged (unsupported) claims in citation_report
3. Assemble the final draft markdown document with:
      - Section headings
      - Section body text
      - [CITATION FLAGGED] inline markers for unsupported claims
      - Formatted bibliography appended
4. Produce a FormattingIssue list for every violation found.

Output keys written to PipelineState
-------------------------------------
    formatting_report  : list[FormattingIssue dict]
    final_draft        : assembled markdown string
    formatting_status  : "ok" | "warnings" | "error"
    formatting_error   : str (only on hard error)

FormattingIssue schema
-----------------------
    {
        "section"  : str,
        "rule"     : str,       # which rule was violated
        "severity" : "ERROR" | "WARNING",
        "detail"   : str,
    }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.agents.state import PipelineState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template loader
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def load_template(name: str = "default") -> dict[str, Any]:
    """Load a template JSON file by name."""
    path = _TEMPLATES_DIR / f"{name}_template.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Template '{name}' not found at {path}. "
            f"Available: {[p.stem.replace('_template','') for p in _TEMPLATES_DIR.glob('*_template.json')]}"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _word_count(text: str) -> int:
    return len(text.split()) if text and text.strip() != "[NO_CONTENT]" else 0


def _check_section_presence(
    section: str,
    text: str,
    issues: list[dict],
) -> bool:
    """Return True if section has usable content."""
    if not text or text.strip() == "[NO_CONTENT]":
        issues.append({
            "section":  section,
            "rule":     "required_section_present",
            "severity": "ERROR",
            "detail":   f"Section '{section}' is required but has no content ([NO_CONTENT]).",
        })
        return False
    return True


def _check_word_count(
    section: str,
    text: str,
    rule: dict,
    issues: list[dict],
) -> None:
    wc      = _word_count(text)
    min_wc  = rule.get("min_words", 0)
    max_wc  = rule.get("max_words")

    if min_wc and wc < min_wc:
        issues.append({
            "section":  section,
            "rule":     "min_words",
            "severity": "WARNING",
            "detail":   f"Section '{section}' has {wc} words (minimum: {min_wc}).",
        })
    if max_wc and wc > max_wc:
        issues.append({
            "section":  section,
            "rule":     "max_words",
            "severity": "WARNING",
            "detail":   f"Section '{section}' has {wc} words (maximum: {max_wc}).",
        })


def _check_flagged_claims(
    section: str,
    citation_report: list[dict],
    issues: list[dict],
) -> list[str]:
    """Return list of flagged claim texts for inline markup."""
    flagged = [
        f["claim"] for f in citation_report
        if f.get("section") == section and f.get("status") == "FLAGGED"
    ]
    for claim in flagged:
        issues.append({
            "section":  section,
            "rule":     "unsupported_claim",
            "severity": "ERROR",
            "detail":   f"Unsupported claim in '{section}': \"{claim[:120]}\"",
        })
    return flagged


def _check_citation_style(
    template: dict, citation_style: str, issues: list[dict]
) -> None:
    expected = template.get("formatting_rules", {}).get("citation_style", "")
    if expected and citation_style.lower() != expected.lower():
        issues.append({
            "section":  "Global",
            "rule":     "citation_style",
            "severity": "WARNING",
            "detail":   (
                f"Template requires citation style '{expected}', "
                f"but pipeline was run with '{citation_style}'."
            ),
        })


# ---------------------------------------------------------------------------
# Draft assembler
# ---------------------------------------------------------------------------

def _assemble_draft(
    draft_sections: dict[str, str],
    required_sections: list[str],
    all_flagged_claims: dict[str, list[str]],    # section → [claim, ...]
    formatted_bibliography: list[str],
    template: dict,
) -> str:
    """Build the final Markdown document."""
    lines: list[str] = []
    display_name = template.get("display_name", "Thesis")
    lines.append(f"# {display_name}\n")

    for section in required_sections:
        text = draft_sections.get(section, "[NO_CONTENT]")
        lines.append(f"## {section}\n")

        if text.strip() == "[NO_CONTENT]":
            lines.append("_[No content available for this section]_\n")
        else:
            # Insert [CITATION FLAGGED] inline markers
            annotated = text
            for claim in all_flagged_claims.get(section, []):
                safe_claim = claim[:80]
                annotated = annotated.replace(
                    safe_claim,
                    f"{safe_claim} **[CITATION FLAGGED]**",
                    1,
                )
            lines.append(f"{annotated}\n")

    # Append bibliography
    if formatted_bibliography:
        lines.append("## References\n")
        for i, entry in enumerate(formatted_bibliography, 1):
            lines.append(f"{i}. {entry}")
        lines.append("")

    # Append formatting rules reminder
    fmt_rules = template.get("formatting_rules", {})
    if fmt_rules:
        lines.append("\n---\n_Formatting requirements:_\n")
        for key, val in fmt_rules.items():
            lines.append(f"- **{key}**: {val}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------

def formatting_agent(state: PipelineState) -> PipelineState:
    """
    LangGraph node — Formatting Agent.

    Reads:  state["draft_sections"], state["citation_report"],
            state["formatted_bibliography"], state["citation_style"],
            state["template_name"]
    Writes: state["formatting_report"], state["final_draft"],
            state["formatting_status"], state["formatting_error"]
    """
    logger.info("▶  Formatting Agent — start")

    draft_sections         = state.get("draft_sections", {})
    citation_report        = state.get("citation_report", [])
    formatted_bibliography = state.get("formatted_bibliography", [])
    citation_style         = state.get("citation_style", "apa")
    template_name          = state.get("template_name", "default")

    try:
        template          = load_template(template_name)
        required_sections = template.get("required_sections", [])
        section_rules     = template.get("section_rules", {})
        issues:  list[dict]              = []
        flagged: dict[str, list[str]]    = {}

        # Global citation style check
        _check_citation_style(template, citation_style, issues)

        # Per-section checks
        for section in required_sections:
            text = draft_sections.get(section, "")
            has_content = _check_section_presence(section, text, issues)

            if has_content and section in section_rules:
                _check_word_count(section, text, section_rules[section], issues)

            flagged[section] = _check_flagged_claims(section, citation_report, issues)

        # Assemble final draft
        final_draft = _assemble_draft(
            draft_sections=draft_sections,
            required_sections=required_sections,
            all_flagged_claims=flagged,
            formatted_bibliography=formatted_bibliography,
            template=template,
        )

        error_count   = sum(1 for i in issues if i["severity"] == "ERROR")
        warning_count = sum(1 for i in issues if i["severity"] == "WARNING")

        status = "ok" if error_count == 0 else "warnings"
        logger.info(
            "Formatting Agent: %d issues (%d errors, %d warnings).",
            len(issues), error_count, warning_count,
        )

        return {
            **state,
            "formatting_report":  issues,
            "final_draft":        final_draft,
            "formatting_status":  status,
            "completed_agents":   state.get("completed_agents", []) + ["formatting"],
        }

    except Exception as exc:
        logger.error("Formatting Agent error: %s", exc, exc_info=True)
        return {
            **state,
            "formatting_report": [],
            "final_draft":       "",
            "formatting_status": "error",
            "formatting_error":  str(exc),
            "errors":            state.get("errors", []) + [f"formatting: {exc}"],
        }
