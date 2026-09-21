"""
Citation formatting module using citeproc-py and CSL style files.

Supported styles (initially):
  - apa        : American Psychological Association 7th Edition
  - vancouver  : Vancouver / PubMed numeric style

Input schema (JSON / dict):
    {
        "id":      str,               # unique key, e.g. "smith2020"
        "title":   str,
        "authors": list[str | dict],  # "Last, First" | {"family":..,"given":..}
        "year":    int,
        "journal": str,               # container-title
        "doi":     str,
        "volume":  str | int,
        "issue":   str | int,
        "pages":   str,               # "1--10" or "1-10"
        "type":    str,               # CSL type, default "article-journal"
    }

Output:
    CitationOutput.in_text       : list[str]  – parallel to input list
    CitationOutput.bibliography  : list[str]  – full formatted entries
"""

from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle
from citeproc import formatter
from citeproc.source.json import CiteProcJSON

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSL style management
# ---------------------------------------------------------------------------

STYLES_DIR = Path(__file__).parent / "csl_styles"

_CSL_URLS: dict[str, str] = {
    "apa": (
        "https://raw.githubusercontent.com/citation-style-language"
        "/styles/master/apa.csl"
    ),
    "vancouver": (
        "https://raw.githubusercontent.com/citation-style-language"
        "/styles/master/vancouver.csl"
    ),
}

SUPPORTED_STYLES: list[str] = list(_CSL_URLS.keys())


def ensure_styles() -> None:
    """Download any missing CSL files from the official CSL repository."""
    STYLES_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in _CSL_URLS.items():
        dest = STYLES_DIR / f"{name}.csl"
        if not dest.exists():
            logger.info("Downloading CSL style '%s' …", name)
            urllib.request.urlretrieve(url, dest)  # noqa: S310
            logger.info("Saved: %s", dest)


def get_style_path(style: str) -> Path:
    """Return path to a CSL file, downloading it if necessary."""
    style = style.lower()
    if style not in _CSL_URLS:
        raise ValueError(
            f"Unsupported style '{style}'. Supported: {SUPPORTED_STYLES}"
        )
    path = STYLES_DIR / f"{style}.csl"
    if not path.exists():
        ensure_styles()
    return path


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Author:
    family: str
    given: str = ""

    def to_csl(self) -> dict[str, str]:
        d: dict[str, str] = {"family": self.family}
        if self.given:
            d["given"] = self.given
        return d


@dataclass
class Reference:
    """Canonical input reference model."""

    id: str
    title: str
    authors: list[Author]
    year: int | None = None
    journal: str | None = None
    doi: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    publisher: str | None = None
    ref_type: str = "article-journal"

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reference":
        """Parse a user-supplied dict into a Reference."""
        authors = _parse_authors(data.get("authors", []))
        return cls(
            id=data["id"],
            title=data["title"],
            authors=authors,
            year=data.get("year"),
            journal=data.get("journal"),
            doi=data.get("doi"),
            volume=str(data["volume"]) if data.get("volume") is not None else None,
            issue=str(data["issue"]) if data.get("issue") is not None else None,
            pages=data.get("pages"),
            publisher=data.get("publisher"),
            ref_type=data.get("type", "article-journal"),
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_csl_json(self) -> dict[str, Any]:
        """Convert to a CSL-JSON dict understood by citeproc-py."""
        entry: dict[str, Any] = {
            "id": self.id,
            "type": self.ref_type,
            "title": self.title,
            "author": [a.to_csl() for a in self.authors],
        }
        if self.year:
            entry["issued"] = {"date-parts": [[self.year]]}
        if self.journal:
            entry["container-title"] = self.journal
        if self.doi:
            entry["DOI"] = self.doi
        if self.volume:
            entry["volume"] = self.volume
        if self.issue:
            entry["issue"] = self.issue
        if self.pages:
            entry["page"] = self.pages
        if self.publisher:
            entry["publisher"] = self.publisher
        return entry


def _parse_authors(raw: list[Any]) -> list[Author]:
    """Handle string ('Last, First' / 'First Last') or dict authors."""
    authors: list[Author] = []
    for a in raw:
        if isinstance(a, dict):
            authors.append(Author(family=a.get("family", ""), given=a.get("given", "")))
        elif isinstance(a, str):
            if "," in a:
                parts = a.split(",", 1)
                authors.append(Author(family=parts[0].strip(), given=parts[1].strip()))
            else:
                parts2 = a.rsplit(" ", 1)
                if len(parts2) == 2:
                    authors.append(Author(family=parts2[1], given=parts2[0]))
                else:
                    authors.append(Author(family=a))
    return authors


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

@dataclass
class CitationOutput:
    """Formatted result for a list of references."""

    style: str
    in_text: list[str]     # one entry per input reference (parallel list)
    bibliography: list[str]  # full bibliography entries (same order as citeproc)


# ---------------------------------------------------------------------------
# Core formatter
# ---------------------------------------------------------------------------

class CitationFormatter:
    """
    Format academic references using citeproc-py + CSL styles.

    Examples
    --------
    >>> fmt = CitationFormatter("apa")
    >>> result = fmt.format(refs)
    >>> print(result.in_text[0])       # (Smith & Doe, 2020)
    >>> print(result.bibliography[0])  # Smith, J. A., & Doe, J. (2020). ...
    """

    def __init__(self, style: str = "apa") -> None:
        self.style_name = style.lower()
        self._style_path = get_style_path(self.style_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format(self, references: list[Reference]) -> CitationOutput:
        """
        Format a list of Reference objects.

        Parameters
        ----------
        references:
            Ordered list of references to format.

        Returns
        -------
        CitationOutput
            `in_text`     – parallel to *references*
            `bibliography`– sorted/ordered by the CSL style
        """
        if not references:
            return CitationOutput(style=self.style_name, in_text=[], bibliography=[])

        csl_data = [r.to_csl_json() for r in references]
        bib_source = CiteProcJSON(csl_data)
        style = CitationStylesStyle(str(self._style_path), validate=False)
        bib_proc = CitationStylesBibliography(style, bib_source, formatter.plain)

        warn_messages: list[str] = []

        def _warn(citation_item: Any) -> None:  # noqa: ANN401
            warn_messages.append(f"Key not found: '{citation_item.key}'")

        # Register every citation before calling .cite()
        citation_objs: list[Citation] = []
        for ref in references:
            c = Citation([CitationItem(ref.id)])
            bib_proc.register(c)
            citation_objs.append(c)

        in_text: list[str] = [str(bib_proc.cite(c, _warn)) for c in citation_objs]

        for msg in warn_messages:
            logger.warning(msg)

        bibliography = [str(entry) for entry in bib_proc.bibliography()]

        return CitationOutput(
            style=self.style_name,
            in_text=in_text,
            bibliography=bibliography,
        )

    @classmethod
    def format_json(
        cls,
        references_json: list[dict[str, Any]],
        style: str = "apa",
    ) -> CitationOutput:
        """
        Convenience method: parse raw dicts and format in one call.

        Parameters
        ----------
        references_json:
            List of reference dicts matching the module's input schema.
        style:
            ``'apa'`` or ``'vancouver'``.

        Returns
        -------
        CitationOutput
        """
        refs = [Reference.from_dict(d) for d in references_json]
        return cls(style).format(refs)
