"""
Ingestion pipeline for ResearchGPT.

Public API
----------
    from app.services.ingestion import IngestionPipeline, IngestionResult

    pipeline = IngestionPipeline()
    result   = pipeline.ingest("paper.pdf")
    print(result.chunks_stored)
"""

from app.services.ingestion.pipeline import IngestionPipeline, IngestionResult

__all__ = ["IngestionPipeline", "IngestionResult"]
