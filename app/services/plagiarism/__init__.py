"""
Plagiarism check service for ResearchGPT.

Two-tier detection:
  1. Internal  — cosine similarity vs. the user's own ChromaDB source corpus (FREE)
  2. External  — Copyleaks API for broad web-based similarity (PRO+ subscription)

Public API
----------
    from app.services.plagiarism import PlagiarismChecker, SubscriptionLevel

    checker = PlagiarismChecker(
        chroma_path="./chroma_data",
        subscription_level=SubscriptionLevel.PRO,
        copyleaks_api_key="...",
        copyleaks_client_id="...",
    )

    report = checker.check(
        sections={"Introduction": "text...", "Methods": "text..."},
        run_external=True,
    )

    print(report.overall_similarity_pct)
    print(report.to_markdown())
"""

from app.services.plagiarism.checker import PlagiarismChecker
from app.services.plagiarism.models import (
    PlagiarismReport,
    SectionReport,
    SimilarityFinding,
    SubscriptionLevel,
)

__all__ = [
    "PlagiarismChecker",
    "PlagiarismReport",
    "SectionReport",
    "SimilarityFinding",
    "SubscriptionLevel",
]
