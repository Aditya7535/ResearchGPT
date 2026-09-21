"""
ResearchGPT services package.
"""

from app.services import citation, crossref_client, document_assembly, ingestion, plagiarism

__all__ = [
    "citation",
    "crossref_client",
    "document_assembly",
    "ingestion",
    "plagiarism",
]
