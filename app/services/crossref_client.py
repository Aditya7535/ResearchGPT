"""
CrossRef API client — auto-fill Reference metadata from a DOI.

Two strategies are used:
  1. Content-negotiation via doi.org  →  returns CSL-JSON directly.
  2. CrossRef REST API                →  full metadata as fallback / enrichment.

Both are available as standalone functions and the high-level
`reference_from_doi()` combines them transparently.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.services.citation import Author, Reference

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DOI_CONTENT_NEG = "https://doi.org/{doi}"
_CROSSREF_WORKS  = "https://api.crossref.org/works/{doi}"

# CrossRef polite pool requires a contact address in the User-Agent.
_USER_AGENT = "ResearchGPT/1.0 (mailto:research@researchgpt.dev; Python)"

# CSL type → citeproc-py type mapping
_TYPE_MAP: dict[str, str] = {
    "journal-article":     "article-journal",
    "book":                "book",
    "book-chapter":        "chapter",
    "proceedings-article": "paper-conference",
    "posted-content":      "manuscript",
    "report":              "report",
    "dataset":             "dataset",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CrossRefError(Exception):
    """Raised when the CrossRef / DOI endpoint returns an error."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean_doi(doi: str) -> str:
    """Strip any URL prefix from a DOI string."""
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi


def _http_get(url: str, accept: str | None = None) -> bytes:
    """Perform a GET request and return the raw response body."""
    headers: dict[str, str] = {"User-Agent": _USER_AGENT}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise CrossRefError(
            f"HTTP {exc.code} for URL '{url}': {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise CrossRefError(
            f"Network error for URL '{url}': {exc.reason}"
        ) from exc


# ---------------------------------------------------------------------------
# Public fetchers
# ---------------------------------------------------------------------------

def fetch_csl_json(doi: str) -> dict[str, Any]:
    """
    Fetch CSL-JSON metadata for *doi* via content negotiation (doi.org).

    This is the preferred method — doi.org returns a CSL-JSON object
    directly when the ``Accept`` header requests it.

    Parameters
    ----------
    doi:
        DOI string, with or without ``https://doi.org/`` prefix.

    Returns
    -------
    dict
        CSL-JSON metadata dict (usable directly by citeproc-py).

    Raises
    ------
    CrossRefError
        On HTTP or network failure.
    """
    doi = _clean_doi(doi)
    url = _DOI_CONTENT_NEG.format(doi=doi)
    raw = _http_get(url, accept="application/vnd.citationstyles.csl+json")
    return json.loads(raw.decode("utf-8"))


def fetch_crossref_message(doi: str) -> dict[str, Any]:
    """
    Fetch the full CrossRef ``/works/{doi}`` response message dict.

    Parameters
    ----------
    doi:
        DOI string.

    Returns
    -------
    dict
        The ``message`` sub-object from the CrossRef REST response.

    Raises
    ------
    CrossRefError
        On HTTP/network failure or unexpected API status.
    """
    doi = _clean_doi(doi)
    encoded = urllib.parse.quote(doi, safe="")
    url = _CROSSREF_WORKS.format(doi=encoded)
    raw = _http_get(url)
    data: dict[str, Any] = json.loads(raw.decode("utf-8"))
    if data.get("status") != "ok":
        raise CrossRefError(
            f"CrossRef status '{data.get('status')}' for DOI '{doi}'"
        )
    return data["message"]


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _authors_from_csl(raw: list[dict[str, Any]]) -> list[Author]:
    return [Author(family=a.get("family", ""), given=a.get("given", "")) for a in raw]


def _year_from_date_parts(date_parts: list[list[int]]) -> int | None:
    try:
        return int(date_parts[0][0])
    except (IndexError, TypeError, ValueError):
        return None


def _reference_from_crossref_message(
    msg: dict[str, Any], ref_id: str | None = None
) -> Reference:
    """Convert a CrossRef message dict to a Reference object."""
    titles      = msg.get("title", [])
    title       = titles[0] if titles else "Unknown Title"
    authors     = _authors_from_csl(msg.get("author", []))

    # Year — try several date fields in priority order
    year: int | None = None
    for date_field in ("published", "published-print", "published-online", "issued"):
        field_val = msg.get(date_field)
        if field_val:
            year = _year_from_date_parts(field_val.get("date-parts", [[]]))
            if year:
                break

    container   = msg.get("container-title", [])
    journal     = container[0] if container else None
    doi         = msg.get("DOI", "")
    volume      = str(msg["volume"]) if msg.get("volume") else None
    issue       = str(msg["issue"]) if msg.get("issue") else None
    pages       = msg.get("page")
    publisher   = msg.get("publisher")
    raw_type    = msg.get("type", "journal-article")
    ref_type    = _TYPE_MAP.get(raw_type, "article-journal")

    safe_id = ref_id or re.sub(r"[^a-zA-Z0-9_]", "_", doi)

    return Reference(
        id=safe_id,
        title=title,
        authors=authors,
        year=year,
        journal=journal,
        doi=doi,
        volume=volume,
        issue=issue,
        pages=pages,
        publisher=publisher,
        ref_type=ref_type,
    )


def _reference_from_csl_json(
    csl: dict[str, Any], ref_id: str | None = None
) -> Reference:
    """Convert a raw CSL-JSON dict (from doi.org content-neg) to a Reference."""
    doi = csl.get("DOI", "")

    # Year
    year: int | None = None
    for date_field in ("issued", "published", "published-print"):
        dp = csl.get(date_field, {}).get("date-parts", [[]])
        year = _year_from_date_parts(dp)
        if year:
            break

    container = csl.get("container-title", "")
    journal = container if isinstance(container, str) else (container[0] if container else None)

    safe_id = ref_id or re.sub(r"[^a-zA-Z0-9_]", "_", doi) or "ref_1"

    return Reference(
        id=safe_id,
        title=csl.get("title", "Unknown Title"),
        authors=_authors_from_csl(csl.get("author", [])),
        year=year,
        journal=journal,
        doi=doi,
        volume=str(csl["volume"]) if csl.get("volume") else None,
        issue=str(csl["issue"]) if csl.get("issue") else None,
        pages=csl.get("page"),
        publisher=csl.get("publisher"),
        ref_type=_TYPE_MAP.get(csl.get("type", ""), "article-journal"),
    )


# ---------------------------------------------------------------------------
# High-level public API
# ---------------------------------------------------------------------------

def reference_from_doi(doi: str, ref_id: str | None = None) -> Reference:
    """
    Auto-fill a Reference by resolving a DOI via CrossRef.

    Tries content-negotiation first (faster); falls back to the
    CrossRef REST API if that fails.

    Parameters
    ----------
    doi:
        DOI string (e.g. ``"10.1038/s41586-021-03819-2"``).
    ref_id:
        Optional custom ``id`` field. Defaults to a sanitized DOI.

    Returns
    -------
    Reference
        Fully populated Reference object ready for formatting.

    Raises
    ------
    CrossRefError
        If both resolution strategies fail.
    """
    doi = _clean_doi(doi)
    logger.info("Resolving DOI: %s", doi)

    # Strategy 1 — content negotiation
    try:
        csl = fetch_csl_json(doi)
        ref = _reference_from_csl_json(csl, ref_id=ref_id)
        logger.debug("Resolved via content negotiation: %s", doi)
        return ref
    except CrossRefError as e:
        logger.warning("Content-neg failed for %s: %s. Falling back to REST API.", doi, e)

    # Strategy 2 — CrossRef REST API
    msg = fetch_crossref_message(doi)
    ref = _reference_from_crossref_message(msg, ref_id=ref_id)
    logger.debug("Resolved via CrossRef REST API: %s", doi)
    return ref
