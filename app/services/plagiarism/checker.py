"""
PlagiarismChecker — top-level orchestrator.

Ties together:
  1. Internal check (ChromaDB cosine similarity)      — FREE tier
  2. External check (Copyleaks / PlagiarismCheck.org) — PRO+ tier
  3. PlagiarismReport assembly

Usage
-----
    from app.services.plagiarism import PlagiarismChecker, SubscriptionLevel

    checker = PlagiarismChecker(
        chroma_path        = "./chroma_data",
        collection_name    = "researchgpt_documents",
        subscription_level = SubscriptionLevel.PRO,
        copyleaks_api_key  = "...",
        copyleaks_email    = "user@example.com",
    )

    # From a dict of {section_name: text}
    report = checker.check(
        sections     = {"Introduction": "...", "Methods": "..."},
        run_external = True,
        threshold    = 0.85,
        document_ids = ["uuid-1", "uuid-2"],  # restrict to specific docs
    )

    print(report.overall_similarity_pct)
    print(report.to_markdown())
    report_path = checker.save_report(report, "./output", formats=["markdown", "json"])
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.services.plagiarism.models import (
    PlagiarismReport,
    SectionReport,
    SubscriptionLevel,
    SubscriptionRequiredError,
)
from app.services.plagiarism.internal_checker import (
    run_internal_check,
    SIMILARITY_THRESHOLD,
)
from app.services.plagiarism.external_checker import run_external_check

logger = logging.getLogger(__name__)


class PlagiarismChecker:
    """
    Two-tier plagiarism detection service.

    Parameters
    ----------
    chroma_path:
        Filesystem path of the ChromaDB persistent store.
    collection_name:
        ChromaDB collection name.
    subscription_level:
        User's current tier — controls external check access.
    copyleaks_api_key:
        Copyleaks API key (required only when run_external=True and PRO+).
    copyleaks_email:
        Copyleaks account email.
    copyleaks_poll_secs:
        Seconds between Copyleaks status polls.
    copyleaks_timeout_secs:
        Max seconds to wait for Copyleaks scan completion.
    """

    def __init__(
        self,
        chroma_path:            str  = "./chroma_data",
        collection_name:        str  = "researchgpt_documents",
        subscription_level:     SubscriptionLevel = SubscriptionLevel.FREE,
        copyleaks_api_key:      str | None = None,
        copyleaks_email:        str | None = None,
        copyleaks_poll_secs:    int = 10,
        copyleaks_timeout_secs: int = 300,
    ) -> None:
        self._chroma_path       = chroma_path
        self._collection_name   = collection_name
        self._subscription      = subscription_level
        self._copyleaks_env: dict[str, str] = {}
        if copyleaks_api_key:
            self._copyleaks_env["COPYLEAKS_API_KEY"]      = copyleaks_api_key
        if copyleaks_email:
            self._copyleaks_env["COPYLEAKS_EMAIL"]        = copyleaks_email
        self._copyleaks_env["COPYLEAKS_POLL_SECS"]        = str(copyleaks_poll_secs)
        self._copyleaks_env["COPYLEAKS_TIMEOUT_SECS"]     = str(copyleaks_timeout_secs)

    # ------------------------------------------------------------------
    # ChromaDB access
    # ------------------------------------------------------------------

    def _get_store(self) -> Any:
        from app.services.ingestion.embedder import (
            EmbeddingStore,
            DEFAULT_COLLECTION,
        )
        return EmbeddingStore(
            persist_path=self._chroma_path,
            collection_name=self._collection_name or DEFAULT_COLLECTION,
        )

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def check(
        self,
        sections:     dict[str, str],
        run_external: bool  = False,
        threshold:    float = SIMILARITY_THRESHOLD,
        top_k:        int   = 3,
        document_ids: list[str] | None = None,
        _store:       Any   = None,     # injectable for testing
        _ext_client:  Any   = None,     # injectable for testing
    ) -> PlagiarismReport:
        """
        Run plagiarism detection across all thesis sections.

        Parameters
        ----------
        sections:
            Ordered ``{section_name: section_text}`` dict.
        run_external:
            If True, also run the Copyleaks external check (PRO+ required).
        threshold:
            Cosine similarity threshold for internal flagging (0–1).
        top_k:
            ChromaDB results per chunk in the internal check.
        document_ids:
            Restrict internal check to specific document IDs.
        _store / _ext_client:
            Injectable for unit testing (bypass real I/O).

        Returns
        -------
        PlagiarismReport
        """
        errors:        list[str] = []
        section_rpts:  list[SectionReport] = []
        external_ran   = False
        ext_provider:  str | None = None

        # ── 1. Internal check ────────────────────────────────────────────────
        logger.info(
            "PlagiarismChecker: starting internal check (%d sections)", len(sections)
        )
        try:
            store = _store or self._get_store()
            section_rpts = run_internal_check(
                sections=sections,
                embedding_store=store,
                threshold=threshold,
                top_k=top_k,
                document_ids=document_ids,
            )
        except Exception as exc:
            logger.error("Internal check failed: %s", exc, exc_info=True)
            errors.append(f"Internal check failed: {exc}")
            # Fall back to empty section reports so the pipeline can continue
            section_rpts = [
                SectionReport(
                    section_name=name,
                    word_count=len(text.split()),
                    chunks_checked=0,
                    findings=[],
                )
                for name, text in sections.items()
            ]

        # ── 2. External check (subscription gate) ────────────────────────────
        if run_external:
            if not self._subscription.allows_external_check:
                msg = (
                    "External plagiarism check is a PRO feature. "
                    "Upgrade at https://researchgpt.dev/pricing"
                )
                logger.warning(msg)
                errors.append(msg)
            else:
                logger.info("PlagiarismChecker: starting external check (Copyleaks)")
                try:
                    provider_env = {
                        **self._copyleaks_env,
                        # Allow override from process environment
                        **{
                            k: os.environ[k]
                            for k in (
                                "COPYLEAKS_API_KEY", "COPYLEAKS_EMAIL",
                                "EXTERNAL_PLAGIARISM_PROVIDER",
                                "PLAGIARISMCHECK_API_KEY",
                            )
                            if k in os.environ
                        },
                    }
                    section_rpts = run_external_check(
                        sections=sections,
                        subscription_level=self._subscription,
                        section_reports=section_rpts,
                        env=provider_env,
                        _client=_ext_client,
                    )
                    external_ran = True
                    ext_provider = provider_env.get(
                        "EXTERNAL_PLAGIARISM_PROVIDER", "copyleaks"
                    )
                except SubscriptionRequiredError as exc:
                    errors.append(str(exc))
                except Exception as exc:
                    logger.error("External check failed: %s", exc, exc_info=True)
                    errors.append(f"External check failed: {exc}")

        # ── 3. Build report ──────────────────────────────────────────────────
        report = PlagiarismReport(
            sections=section_rpts,
            external_ran=external_ran,
            subscription_level=self._subscription.value,
            external_provider=ext_provider,
            errors=errors,
        )

        logger.info(
            "PlagiarismChecker: overall=%.1f%%  internal=%.1f%%  external=%s  risk=%s",
            report.overall_similarity_pct,
            report.internal_similarity_pct,
            f"{report.external_similarity_pct:.1f}%" if report.external_ran else "N/A",
            report.risk_level,
        )
        return report

    # ------------------------------------------------------------------
    # Report saving
    # ------------------------------------------------------------------

    def save_report(
        self,
        report:     PlagiarismReport,
        output_dir: str | Path = "./output",
        formats:    list[str] | None = None,
        stem:       str = "plagiarism_report",
    ) -> dict[str, Path]:
        """
        Save the report to disk in the requested formats.

        Parameters
        ----------
        report:
            The PlagiarismReport to save.
        output_dir:
            Directory to write files into.
        formats:
            ``["markdown", "json"]`` — defaults to both.
        stem:
            Base filename without extension.

        Returns
        -------
        dict[str, Path]
            ``{"markdown": Path(...), "json": Path(...)}``
        """
        if formats is None:
            formats = ["markdown", "json"]
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        saved: dict[str, Path] = {}

        if "markdown" in formats:
            md_path = out_dir / f"{stem}.md"
            md_path.write_text(report.to_markdown(), encoding="utf-8")
            saved["markdown"] = md_path
            logger.info("Report saved (markdown): %s", md_path)

        if "json" in formats:
            json_path = out_dir / f"{stem}.json"
            json_path.write_text(report.to_json(), encoding="utf-8")
            saved["json"] = json_path
            logger.info("Report saved (JSON): %s", json_path)

        return saved
