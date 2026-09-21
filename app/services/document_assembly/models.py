"""
Input data models for the document assembly service.

All models are plain Python dataclasses — no external dependencies.

Input JSON schema
-----------------
{
    "title":          str,
    "author":         str,
    "institution":    str,
    "date":           str,
    "abstract":       str,           # optional top-level abstract
    "citation_style": "apa"|"vancouver",
    "sections": [
        {
            "name":          str,        # e.g. "Introduction"
            "heading_level": 1|2|3,     # 1 = chapter, 2 = section, 3 = sub
            "text":          str,        # body text (may include in-text markers)
            "citations":     [str],      # list of reference IDs used in this section
            "data_tables": [
                {
                    "id":       str,
                    "caption":  str,
                    "headers":  [str],
                    "rows":     [[str|num, ...]],
                    "chart": {          # optional — omit to skip chart
                        "type":  "bar"|"line"|"scatter"|"pie"|"histogram",
                        "title": str,
                        "x_col": str,   # header name for x-axis
                        "y_col": str,   # header name for y-axis (or values)
                        "color": str    # hex color, default "#4472C4"
                    }
                }
            ],
            "subsections": [...]        # recursive, same schema
        }
    ],
    "bibliography": [
        { "id": str, "title": str, "authors": [...], "year": int, ... }
    ]
}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Chart configuration
# ---------------------------------------------------------------------------

@dataclass
class ChartConfig:
    """Configuration for auto-generating a chart from a DataTable."""

    type:  str = "bar"       # bar | line | scatter | pie | histogram
    title: str = ""
    x_col: str = ""          # header name to use as x-axis / labels
    y_col: str = ""          # header name to use as y-axis / values
    color: str = "#4472C4"   # primary bar/line colour (hex)
    figsize: tuple[float, float] = (6.5, 4.0)
    dpi: int = 150

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ChartConfig":
        figsize_raw = d.get("figsize", [6.5, 4.0])
        return cls(
            type=d.get("type", "bar"),
            title=d.get("title", ""),
            x_col=d.get("x_col", ""),
            y_col=d.get("y_col", ""),
            color=d.get("color", "#4472C4"),
            figsize=tuple(figsize_raw),  # type: ignore[arg-type]
            dpi=int(d.get("dpi", 150)),
        )


# ---------------------------------------------------------------------------
# Data table
# ---------------------------------------------------------------------------

@dataclass
class DataTable:
    """A tabular dataset that can optionally generate a chart."""

    id:      str
    caption: str
    headers: list[str]
    rows:    list[list[Any]]          # each row is a list of cell values
    chart:   ChartConfig | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DataTable":
        chart_raw = d.get("chart")
        return cls(
            id=d.get("id", ""),
            caption=d.get("caption", ""),
            headers=d.get("headers", []),
            rows=d.get("rows", []),
            chart=ChartConfig.from_dict(chart_raw) if chart_raw else None,
        )

    def col_index(self, col_name: str) -> int:
        """Return 0-based index of a column by name; raises KeyError if absent."""
        try:
            return self.headers.index(col_name)
        except ValueError:
            raise KeyError(
                f"Column '{col_name}' not found in table '{self.id}'. "
                f"Available: {self.headers}"
            )

    def col_values(self, col_name: str) -> list[Any]:
        """Return all values for a given column name."""
        idx = self.col_index(col_name)
        return [row[idx] for row in self.rows]

    def numeric_col(self, col_name: str) -> list[float]:
        """Return column values coerced to float."""
        return [float(v) for v in self.col_values(col_name)]


# ---------------------------------------------------------------------------
# Section (recursive)
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """A single thesis section with optional subsections."""

    name:          str
    text:          str              = ""
    heading_level: int              = 1
    citations:     list[str]        = field(default_factory=list)
    data_tables:   list[DataTable]  = field(default_factory=list)
    subsections:   list["Section"]  = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Section":
        return cls(
            name=d.get("name", "Untitled Section"),
            text=d.get("text", ""),
            heading_level=int(d.get("heading_level", 1)),
            citations=d.get("citations", []),
            data_tables=[DataTable.from_dict(t) for t in d.get("data_tables", [])],
            subsections=[Section.from_dict(s) for s in d.get("subsections", [])],
        )

    def all_tables(self) -> list[DataTable]:
        """Flatten this section + all subsections' tables."""
        result = list(self.data_tables)
        for sub in self.subsections:
            result.extend(sub.all_tables())
        return result


# ---------------------------------------------------------------------------
# Top-level thesis content
# ---------------------------------------------------------------------------

@dataclass
class ThesisContent:
    """Complete thesis input model."""

    title:          str
    author:         str
    institution:    str              = ""
    date:           str              = ""
    abstract:       str              = ""
    citation_style: str              = "apa"
    sections:       list[Section]    = field(default_factory=list)
    bibliography:   list[dict]       = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThesisContent":
        """Parse a raw JSON-derived dict into a ThesisContent object."""
        return cls(
            title=data.get("title", "Untitled Thesis"),
            author=data.get("author", ""),
            institution=data.get("institution", ""),
            date=data.get("date", ""),
            abstract=data.get("abstract", ""),
            citation_style=data.get("citation_style", "apa"),
            sections=[Section.from_dict(s) for s in data.get("sections", [])],
            bibliography=data.get("bibliography", []),
        )

    def all_sections_flat(self) -> list[Section]:
        """Return every section + subsection in document order (DFS)."""
        result: list[Section] = []

        def _walk(sections: list[Section]) -> None:
            for sec in sections:
                result.append(sec)
                _walk(sec.subsections)

        _walk(self.sections)
        return result

    def all_tables(self) -> list[tuple[str, DataTable]]:
        """Return (section_name, table) pairs for every table in the document."""
        pairs: list[tuple[str, DataTable]] = []
        for sec in self.all_sections_flat():
            for tbl in sec.data_tables:
                pairs.append((sec.name, tbl))
        return pairs
