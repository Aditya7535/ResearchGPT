"""
Report generator — renders PlagiarismReport to Markdown and JSON.

The Markdown report follows a standard academic similarity report layout:

    ─────────────────────────────────────────────────────────────
    RESEARCHGPT — PLAGIARISM DETECTION REPORT
    ─────────────────────────────────────────────────────────────
    Overall Similarity:  12.4%   [LOW RISK]
    Internal (corpus):   8.1%
    External (web):      4.3%
    ...
    ─────────────────────────────────────────────────────────────
    SECTION BREAKDOWN
    ─────────────────────────────────────────────────────────────
    Introduction      ████░░░░░░  18.2%   (3 flagged passages)
    Methods           ██░░░░░░░░   5.3%   (1 flagged passage)
    ...
    ─────────────────────────────────────────────────────────────
    FLAGGED PASSAGES
    ─────────────────────────────────────────────────────────────
    [HIGH] Introduction — 91.2% similarity
    Source: paper.pdf:Introduction
    Passage: "The use of transformer models has become…"
    Match:   "The use of transformer models has become…"
    ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.plagiarism.models import PlagiarismReport


# ---------------------------------------------------------------------------
# Progress bar helper
# ---------------------------------------------------------------------------

def _progress_bar(pct: float, width: int = 10) -> str:
    """ASCII progress bar: ████░░░░░░ 42.0%"""
    filled = round(pct / 100 * width)
    bar    = "█" * filled + "░" * (width - filled)
    return f"{bar}  {pct:5.1f}%"


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_markdown_report(report: "PlagiarismReport") -> str:
    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────────────
    lines += [
        "# ResearchGPT — Plagiarism Detection Report",
        "",
        f"**Generated:** {report.generated_at}",
        f"**Subscription:** {report.subscription_level.upper()}",
        "",
        "---",
        "",
    ]

    # ── Summary ───────────────────────────────────────────────────────────────
    lines += [
        "## Overall Similarity",
        "",
        f"| Metric | Score |",
        f"|--------|-------|",
        f"| **Overall**          | **{report.overall_similarity_pct:.1f}%**  `{report.risk_level}` |",
        f"| Internal (corpus)    | {report.internal_similarity_pct:.1f}% |",
    ]

    ext_pct = report.external_similarity_pct
    if report.external_ran and ext_pct is not None:
        provider = report.external_provider or "Copyleaks"
        lines.append(f"| External ({provider}) | {ext_pct:.1f}% |")
    else:
        lines.append(f"| External (web) | *Not run* {'(upgrade to PRO)' if report.subscription_level == 'free' else ''} |")

    lines += ["", "---", "", "## Section Breakdown", ""]
    lines.append("| Section | Similarity | Flagged Passages | Risk |")
    lines.append("|---------|-----------|-------------------|------|")

    for sec in report.sections:
        risk = (
            "🔴 HIGH"   if sec.similarity_pct >= 30 else
            "🟡 MEDIUM" if sec.similarity_pct >= 15 else
            "🟢 LOW"
        )
        lines.append(
            f"| {sec.section_name} "
            f"| {_progress_bar(sec.similarity_pct)} "
            f"| {sec.flagged_count} passage(s) "
            f"| {risk} |"
        )

    # ── Flagged passages ──────────────────────────────────────────────────────
    all_findings = report.all_findings
    if all_findings:
        lines += ["", "---", "", "## Flagged Passages", ""]
        # Sort: highest similarity first
        sorted_findings = sorted(all_findings, key=lambda f: f.similarity_score, reverse=True)
        for f in sorted_findings:
            tag  = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}.get(f.severity, "⚪")
            src_label = "📖 Corpus" if f.source_type == "internal" else "🌐 Web"
            lines += [
                f"### {tag} {f.severity} — {f.section} ({f.similarity_pct:.1f}% similarity)",
                "",
                f"- **Source type:** {src_label}",
                f"- **Source:**       `{f.source_ref}`",
                "",
                f"> **Flagged text:** \"{f.text[:300]}{'…' if len(f.text) > 300 else ''}\"",
            ]
            if f.source_text:
                lines += [
                    "",
                    f"> **Matched text:** \"{f.source_text[:300]}{'…' if len(f.source_text) > 300 else ''}\"",
                ]
            lines.append("")
    else:
        lines += ["", "---", "", "## Flagged Passages", "", "✅ No passages flagged above the similarity threshold.", ""]

    # ── Errors ────────────────────────────────────────────────────────────────
    if report.errors:
        lines += ["", "---", "", "## Errors & Warnings", ""]
        for err in report.errors:
            lines.append(f"- ⚠️ {err}")
        lines.append("")

    # ── Footer ────────────────────────────────────────────────────────────────
    lines += [
        "---",
        "",
        "_Report generated by ResearchGPT Plagiarism Detection Service._",
        "_Internal check compares against your uploaded source corpus._",
    ]
    if not report.external_ran:
        lines.append(
            "_External web check not performed. "
            "Upgrade to **PRO** at https://researchgpt.dev/pricing_"
        )

    return "\n".join(lines)
