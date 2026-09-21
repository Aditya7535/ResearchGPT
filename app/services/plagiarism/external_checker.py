"""
External plagiarism checker — Copyleaks API integration.

Gated by SubscriptionLevel.PRO or higher.

Copyleaks API v3 flow
---------------------
  1. Login  → POST https://id.copyleaks.com/v3/account/login/api
             Returns: access_token (valid ~24 hours)

  2. Submit → PUT https://api.copyleaks.com/v3/{email}/submit/file/{scan_id}
             Body: base64-encoded text file + scan properties
             Returns: 204 (accepted, asynchronous)

  3. Poll   → GET https://api.copyleaks.com/v3/{email}/scans/status
             Repeat until scan_id status is "Finished" or "Error"

  4. Result → GET https://api.copyleaks.com/v3/{email}/downloads/{scan_id}/result
             Returns: matched sources, similarity %, flagged passages

Required environment variables
-------------------------------
    COPYLEAKS_API_KEY      : API key from console.copyleaks.com
    COPYLEAKS_EMAIL        : Account email used to register API key
    COPYLEAKS_POLL_SECS    : Seconds between status polls (default: 10)
    COPYLEAKS_TIMEOUT_SECS : Maximum wait for scan completion (default: 300)

Alternative: PlagiarismCheck.org
---------------------------------
Set EXTERNAL_PLAGIARISM_PROVIDER=plagiarismcheck to use PlagiarismCheck.org:
    PLAGIARISMCHECK_API_KEY : API key from plagiarismcheck.org
    API endpoint: POST https://api.plagiarismcheck.org/v1/check
"""

from __future__ import annotations

import base64
import logging
import os
import time
import uuid
from typing import Any

import requests

from app.services.plagiarism.models import (
    SimilarityFinding,
    SectionReport,
    SubscriptionLevel,
    SubscriptionRequiredError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Copyleaks API endpoints
# ---------------------------------------------------------------------------

_COPYLEAKS_LOGIN_URL  = "https://id.copyleaks.com/v3/account/login/api"
_COPYLEAKS_SUBMIT_URL = "https://api.copyleaks.com/v3/{email}/submit/file/{scan_id}"
_COPYLEAKS_STATUS_URL = "https://api.copyleaks.com/v3/{email}/scans/status"
_COPYLEAKS_RESULT_URL = "https://api.copyleaks.com/v3/{email}/downloads/{scan_id}/result"

# PlagiarismCheck.org endpoint
_PCHECK_URL = "https://api.plagiarismcheck.org/v1/check"

_DEFAULT_POLL_SECS    = 10
_DEFAULT_TIMEOUT_SECS = 300


# ---------------------------------------------------------------------------
# Copyleaks client
# ---------------------------------------------------------------------------

class CopyleaksClient:
    """
    Thin Copyleaks API v3 client.

    Parameters
    ----------
    api_key:
        Copyleaks API key.
    email:
        Account email (used as the "client ID" in API URLs).
    poll_interval_secs:
        Seconds between status polls.
    timeout_secs:
        Maximum total wait for scan completion.
    """

    def __init__(
        self,
        api_key:            str,
        email:              str,
        poll_interval_secs: int = _DEFAULT_POLL_SECS,
        timeout_secs:       int = _DEFAULT_TIMEOUT_SECS,
    ) -> None:
        self._api_key   = api_key
        self._email     = email
        self._poll_secs = poll_interval_secs
        self._timeout   = timeout_secs
        self._token:    str | None = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _login(self) -> str:
        """Authenticate and return an access token."""
        logger.info("Copyleaks: logging in as %s", self._email)
        resp = requests.post(
            _COPYLEAKS_LOGIN_URL,
            json={"email": self._email, "key": self._api_key},
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _auth_headers(self) -> dict[str, str]:
        if self._token is None:
            self._login()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type":  "application/json",
        }

    # ------------------------------------------------------------------
    # Submit scan
    # ------------------------------------------------------------------

    def _submit(self, text: str, scan_id: str) -> None:
        """Submit text for scanning (base64-encoded as a .txt file)."""
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        url     = _COPYLEAKS_SUBMIT_URL.format(email=self._email, scan_id=scan_id)
        payload = {
            "base64":   encoded,
            "filename": f"{scan_id}.txt",
            "properties": {
                "sensitive_data_protection": {"should_protect": False},
                "webhooks": {},
                "scanning": {
                    "internet":        True,
                    "skip_auto_bias":  True,
                    "citations":       True,
                    "references":      True,
                },
            },
        }
        resp = requests.put(url, json=payload, headers=self._auth_headers(), timeout=60)
        resp.raise_for_status()
        logger.info("Copyleaks: scan %s submitted.", scan_id)

    # ------------------------------------------------------------------
    # Poll for completion
    # ------------------------------------------------------------------

    def _poll_until_done(self, scan_id: str) -> str:
        """
        Poll the scan status endpoint until the scan finishes.

        Returns
        -------
        str
            ``"Finished"`` or ``"Error"``.

        Raises
        ------
        TimeoutError
            If the scan doesn't complete within ``timeout_secs``.
        RuntimeError
            If Copyleaks reports an error status.
        """
        url       = _COPYLEAKS_STATUS_URL.format(email=self._email)
        deadline  = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            resp  = requests.get(url, headers=self._auth_headers(), timeout=30)
            resp.raise_for_status()
            scans = resp.json().get("scans", [])
            for scan in scans:
                if scan.get("id") == scan_id:
                    status = scan.get("status", "")
                    if status == "Finished":
                        return "Finished"
                    if status == "Error":
                        raise RuntimeError(
                            f"Copyleaks scan {scan_id} failed with status 'Error'."
                        )
            logger.debug("Copyleaks: scan %s still processing…", scan_id)
            time.sleep(self._poll_secs)

        raise TimeoutError(
            f"Copyleaks scan {scan_id} did not complete within {self._timeout}s."
        )

    # ------------------------------------------------------------------
    # Fetch results
    # ------------------------------------------------------------------

    def _fetch_result(self, scan_id: str) -> dict[str, Any]:
        url  = _COPYLEAKS_RESULT_URL.format(email=self._email, scan_id=scan_id)
        resp = requests.get(url, headers=self._auth_headers(), timeout=60)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Parse Copyleaks result into SimilarityFindings
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_result(
        result: dict[str, Any],
        section_name: str,
        original_text: str,
    ) -> list[SimilarityFinding]:
        """
        Convert a Copyleaks API result dict into SimilarityFinding objects.

        Copyleaks result structure (simplified):
        {
            "internet": [
                {
                    "url": "https://example.com/paper",
                    "statistics": {"identical": 0.12, "similar": 0.05},
                    "comparison": [
                        {"text": "matched passage", "type": 1}
                    ]
                }
            ],
            "statistics": {"aggregatedScore": 0.17}
        }
        """
        findings: list[SimilarityFinding] = []
        sources = result.get("internet", []) + result.get("database", [])
        for idx, source in enumerate(sources):
            url      = source.get("url", source.get("metadata", {}).get("filename", "unknown"))
            stats    = source.get("statistics", {})
            score    = stats.get("identical", 0.0) + stats.get("similar", 0.0) / 2.0
            score    = min(1.0, float(score))

            comparisons = source.get("comparison", [])
            if comparisons:
                for comp in comparisons:
                    matched_text = comp.get("text", "")
                    if not matched_text:
                        continue
                    findings.append(
                        SimilarityFinding(
                            text=matched_text,
                            section=section_name,
                            similarity_score=score,
                            source_type="external",
                            source_ref=url,
                            source_text=None,
                            chunk_index=idx,
                        )
                    )
            else:
                # No comparison detail — report at document level
                findings.append(
                    SimilarityFinding(
                        text=original_text[:200],
                        section=section_name,
                        similarity_score=score,
                        source_type="external",
                        source_ref=url,
                        source_text=None,
                        chunk_index=idx,
                    )
                )
        return findings

    # ------------------------------------------------------------------
    # High-level: scan one section
    # ------------------------------------------------------------------

    def scan_section(
        self,
        section_name: str,
        text: str,
    ) -> list[SimilarityFinding]:
        """Submit text, wait for result, return findings for one section."""
        scan_id = str(uuid.uuid4()).replace("-", "")[:24]
        self._submit(text, scan_id)
        self._poll_until_done(scan_id)
        result = self._fetch_result(scan_id)
        return self._parse_result(result, section_name, text)


# ---------------------------------------------------------------------------
# PlagiarismCheck.org client (alternative provider)
# ---------------------------------------------------------------------------

class PlagiarismCheckOrgClient:
    """
    Thin client for PlagiarismCheck.org API.

    Environment variables
    ---------------------
    PLAGIARISMCHECK_API_KEY : API key from plagiarismcheck.org
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def scan_section(
        self,
        section_name: str,
        text: str,
    ) -> list[SimilarityFinding]:
        """Submit text to PlagiarismCheck.org and return findings."""
        resp = requests.post(
            _PCHECK_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type":  "application/json",
            },
            json={"text": text},
            timeout=120,
        )
        resp.raise_for_status()
        data     = resp.json()
        score    = float(data.get("similarity", 0.0)) / 100.0  # API returns 0-100
        sources  = data.get("sources", [])
        findings: list[SimilarityFinding] = []
        for idx, src in enumerate(sources):
            url       = src.get("url", "unknown")
            src_score = float(src.get("similarity", 0)) / 100.0
            findings.append(
                SimilarityFinding(
                    text=text[:300],
                    section=section_name,
                    similarity_score=src_score,
                    source_type="external",
                    source_ref=url,
                    source_text=None,
                    chunk_index=idx,
                )
            )
        return findings


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def _build_client(env: dict[str, str] | None = None) -> Any:
    """
    Build the appropriate external client from environment variables.

    Returns a CopyleaksClient or PlagiarismCheckOrgClient.
    Raises ValueError if required env vars are missing.
    """
    env = env or {}

    def _get(key: str) -> str:
        return env.get(key) or os.environ.get(key, "")

    provider = _get("EXTERNAL_PLAGIARISM_PROVIDER").lower() or "copyleaks"

    if provider == "plagiarismcheck":
        key = _get("PLAGIARISMCHECK_API_KEY")
        if not key:
            raise ValueError(
                "PLAGIARISMCHECK_API_KEY env var is required for PlagiarismCheck.org."
            )
        return PlagiarismCheckOrgClient(api_key=key)

    # Default: Copyleaks
    api_key = _get("COPYLEAKS_API_KEY")
    email   = _get("COPYLEAKS_EMAIL")
    if not api_key or not email:
        raise ValueError(
            "COPYLEAKS_API_KEY and COPYLEAKS_EMAIL env vars are required for Copyleaks."
        )
    return CopyleaksClient(
        api_key=api_key,
        email=email,
        poll_interval_secs=int(_get("COPYLEAKS_POLL_SECS")  or _DEFAULT_POLL_SECS),
        timeout_secs=int(_get("COPYLEAKS_TIMEOUT_SECS")     or _DEFAULT_TIMEOUT_SECS),
    )


# ---------------------------------------------------------------------------
# Public API — document-level external check
# ---------------------------------------------------------------------------

def run_external_check(
    sections: dict[str, str],
    subscription_level: SubscriptionLevel,
    section_reports: list[SectionReport],
    env: dict[str, str] | None = None,
    _client: Any = None,               # injectable for testing
) -> list[SectionReport]:
    """
    Run external similarity checks via Copyleaks (or PlagiarismCheck.org).

    Subscription gate: raises SubscriptionRequiredError for FREE tier.

    Parameters
    ----------
    sections:
        ``{section_name: section_text}`` of the thesis.
    subscription_level:
        User's current subscription level.
    section_reports:
        Existing SectionReport list (from internal check) to augment
        with external findings.
    env:
        Optional override dict for environment variables (for testing).
    _client:
        Injectable API client (for unit tests — bypasses real HTTP).

    Returns
    -------
    list[SectionReport]
        Updated section reports with external findings appended.
    """
    if not subscription_level.allows_external_check:
        raise SubscriptionRequiredError(
            feature="External plagiarism check (Copyleaks)",
            required=SubscriptionLevel.PRO,
        )

    client = _client or _build_client(env)

    # Build a lookup for fast section report access
    report_map = {r.section_name: r for r in section_reports}

    for name, text in sections.items():
        if not text or text.strip() == "[NO_CONTENT]":
            continue
        try:
            external_findings = client.scan_section(name, text)
            if name in report_map:
                report_map[name].findings.extend(external_findings)
                logger.info(
                    "External check: section=%r  new findings=%d",
                    name, len(external_findings),
                )
            else:
                report_map[name] = SectionReport(
                    section_name=name,
                    word_count=len(text.split()),
                    chunks_checked=1,
                    findings=external_findings,
                )
        except Exception as exc:
            logger.error(
                "External check failed for section %r: %s", name, exc, exc_info=True
            )

    return list(report_map.values())
