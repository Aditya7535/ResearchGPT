"""
Data models for the plagiarism detection service.

Model hierarchy
---------------
    SimilarityFinding          ← a single flagged passage
        ↓
    SectionReport              ← per-section aggregation
        ↓
    PlagiarismReport           ← full document report

Subscription
------------
    SubscriptionLevel.FREE       → internal check only
    SubscriptionLevel.PRO        → internal + external (Copyleaks)
    SubscriptionLevel.ENTERPRISE → PRO + priority queuing + extended retention
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------

class SubscriptionLevel(Enum):
    FREE       = "free"
    PRO        = "pro"
    ENTERPRISE = "enterprise"

    @property
    def allows_external_check(self) -> bool:
        return self in (SubscriptionLevel.PRO, SubscriptionLevel.ENTERPRISE)


class SubscriptionRequiredError(Exception):
    """Raised when a feature requires a higher subscription tier."""

    def __init__(self, feature: str, required: SubscriptionLevel) -> None:
        super().__init__(
            f"'{feature}' requires subscription level '{required.value}' or higher. "
            f"Upgrade at https://researchgpt.dev/pricing"
        )
        self.feature  = feature
        self.required = required


# ---------------------------------------------------------------------------
# Individual finding
# ---------------------------------------------------------------------------

@dataclass
class SimilarityFinding:
    """
    A single flagged passage with source attribution.

    Attributes
    ----------
    text:
        The thesis passage that was flagged.
    section:
        Thesis section where the passage appears.
    similarity_score:
        Normalised score 0.0–1.0 (1.0 = identical).
    source_type:
        ``"internal"`` (ChromaDB corpus) or ``"external"`` (web / Copyleaks).
    source_ref:
        For internal: ``"filename.pdf:section_name"``.
        For external: URL or ``"web:domain.com"``.
    source_text:
        The matching text from the source (may be None for external matches).
    chunk_index:
        0-based index of the chunk within its section.
    """

    text:             str
    section:          str
    similarity_score: float
    source_type:      str            # "internal" | "external"
    source_ref:       str
    source_text:      str | None     = None
    chunk_index:      int            = 0

    @property
    def similarity_pct(self) -> float:
        return round(self.similarity_score * 100, 1)

    @property
    def severity(self) -> str:
        """Textual severity based on similarity score."""
        if self.similarity_score >= 0.95:
            return "CRITICAL"
        if self.similarity_score >= 0.85:
            return "HIGH"
        if self.similarity_score >= 0.75:
            return "MEDIUM"
        return "LOW"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text":             self.text,
            "section":          self.section,
            "similarity_score": self.similarity_score,
            "similarity_pct":   self.similarity_pct,
            "severity":         self.severity,
            "source_type":      self.source_type,
            "source_ref":       self.source_ref,
            "source_text":      self.source_text,
            "chunk_index":      self.chunk_index,
        }


# ---------------------------------------------------------------------------
# Per-section report
# ---------------------------------------------------------------------------

@dataclass
class SectionReport:
    """
    Aggregated similarity metrics for one thesis section.

    Attributes
    ----------
    section_name:
        The section heading.
    word_count:
        Total words in this section's text.
    chunks_checked:
        Number of text chunks submitted for comparison.
    findings:
        All SimilarityFindings for this section.
    """

    section_name:   str
    word_count:     int
    chunks_checked: int
    findings:       list[SimilarityFinding] = field(default_factory=list)

    @property
    def flagged_count(self) -> int:
        return len(self.findings)

    @property
    def internal_findings(self) -> list[SimilarityFinding]:
        return [f for f in self.findings if f.source_type == "internal"]

    @property
    def external_findings(self) -> list[SimilarityFinding]:
        return [f for f in self.findings if f.source_type == "external"]

    @property
    def similarity_pct(self) -> float:
        """Average similarity across flagged chunks (0.0 if none)."""
        if not self.findings:
            return 0.0
        return round(
            sum(f.similarity_score for f in self.findings) / len(self.findings) * 100,
            1,
        )

    @property
    def flagged_word_count(self) -> int:
        """Estimated word count of flagged passages."""
        return sum(len(f.text.split()) for f in self.findings)

    @property
    def flagged_word_pct(self) -> float:
        """Percentage of section words that are in flagged passages."""
        if not self.word_count:
            return 0.0
        return round(self.flagged_word_count / self.word_count * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_name":      self.section_name,
            "word_count":        self.word_count,
            "chunks_checked":    self.chunks_checked,
            "flagged_count":     self.flagged_count,
            "similarity_pct":    self.similarity_pct,
            "flagged_word_pct":  self.flagged_word_pct,
            "findings":          [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Full document report
# ---------------------------------------------------------------------------

@dataclass
class PlagiarismReport:
    """
    Complete plagiarism detection report for an assembled thesis.

    Attributes
    ----------
    sections:
        Per-section reports (ordered as in the thesis).
    external_ran:
        True if the Copyleaks external check was executed.
    subscription_level:
        Subscription tier used.
    generated_at:
        ISO-8601 timestamp.
    external_provider:
        Name of the external API used (e.g. "copyleaks").
    errors:
        Non-fatal errors encountered during checking.
    """

    sections:              list[SectionReport]  = field(default_factory=list)
    external_ran:          bool                 = False
    subscription_level:    str                  = "free"
    generated_at:          str                  = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    external_provider:     str | None           = None
    errors:                list[str]            = field(default_factory=list)

    # ------------------------------------------------------------------
    # Aggregate properties
    # ------------------------------------------------------------------

    @property
    def all_findings(self) -> list[SimilarityFinding]:
        result: list[SimilarityFinding] = []
        for sec in self.sections:
            result.extend(sec.findings)
        return result

    @property
    def internal_findings(self) -> list[SimilarityFinding]:
        return [f for f in self.all_findings if f.source_type == "internal"]

    @property
    def external_findings(self) -> list[SimilarityFinding]:
        return [f for f in self.all_findings if f.source_type == "external"]

    @property
    def overall_similarity_pct(self) -> float:
        """
        Document-level similarity: flagged words / total words × 100.
        Counts each flagged passage once (de-duplicated by text).
        """
        total_words   = sum(s.word_count     for s in self.sections)
        flagged_words = sum(s.flagged_word_count for s in self.sections)
        if not total_words:
            return 0.0
        return round(flagged_words / total_words * 100, 1)

    @property
    def internal_similarity_pct(self) -> float:
        total_words = sum(s.word_count for s in self.sections)
        flagged     = sum(
            len(f.text.split())
            for f in self.internal_findings
        )
        if not total_words:
            return 0.0
        return round(flagged / total_words * 100, 1)

    @property
    def external_similarity_pct(self) -> float | None:
        if not self.external_ran:
            return None
        total_words = sum(s.word_count for s in self.sections)
        flagged     = sum(len(f.text.split()) for f in self.external_findings)
        if not total_words:
            return 0.0
        return round(flagged / total_words * 100, 1)

    @property
    def risk_level(self) -> str:
        pct = self.overall_similarity_pct
        if pct >= 30:
            return "HIGH RISK"
        if pct >= 15:
            return "MEDIUM RISK"
        if pct >= 5:
            return "LOW RISK"
        return "MINIMAL RISK"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_similarity_pct":  self.overall_similarity_pct,
            "internal_similarity_pct": self.internal_similarity_pct,
            "external_similarity_pct": self.external_similarity_pct,
            "risk_level":              self.risk_level,
            "external_ran":            self.external_ran,
            "external_provider":       self.external_provider,
            "subscription_level":      self.subscription_level,
            "generated_at":            self.generated_at,
            "sections":                [s.to_dict() for s in self.sections],
            "errors":                  self.errors,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Generate a human-readable Markdown similarity report."""
        from app.services.plagiarism.report_generator import render_markdown_report
        return render_markdown_report(self)
