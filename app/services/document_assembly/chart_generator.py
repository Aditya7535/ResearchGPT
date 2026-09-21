"""
Chart generator — converts DataTable objects into matplotlib figures.

Supported chart types
---------------------
  bar        : vertical bar chart (x_col labels, y_col values)
  line       : line chart with markers
  scatter    : scatter plot
  pie        : pie chart (x_col labels, y_col values)
  histogram  : frequency histogram of y_col values

All charts are returned as in-memory PNG ``BytesIO`` objects so they
can be embedded directly into Word or base64-encoded for HTML/PDF —
no temporary files needed.

Styling follows a clean academic look:
  - White background, light grey grid
  - Configurable primary colour (hex)
  - 150 DPI by default (scalable via ChartConfig.dpi)
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

from app.services.document_assembly.models import DataTable, ChartConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _setup_axes(ax: Any, title: str, xlabel: str, ylabel: str) -> None:
    """Apply consistent academic styling to a matplotlib Axes object."""
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_facecolor("#FAFAFA")
    ax.grid(axis="y", color="#E0E0E0", linestyle="--", linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _to_png(fig: Any) -> BytesIO:
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _bar_chart(table: DataTable, cfg: ChartConfig, plt: Any) -> BytesIO:
    x_col = cfg.x_col or table.headers[0]
    y_col = cfg.y_col or (table.headers[1] if len(table.headers) > 1 else table.headers[0])

    labels = table.col_values(x_col)
    values = table.numeric_col(y_col)

    fig, ax = plt.subplots(figsize=cfg.figsize)
    bars = ax.bar(labels, values, color=cfg.color, edgecolor="white", linewidth=0.6)
    ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=9)
    _setup_axes(ax, cfg.title or f"{y_col} by {x_col}", x_col, y_col)
    plt.xticks(rotation=30, ha="right", fontsize=9)
    plt.tight_layout()
    result = _to_png(fig)
    plt.close(fig)
    return result


def _line_chart(table: DataTable, cfg: ChartConfig, plt: Any) -> BytesIO:
    x_col = cfg.x_col or table.headers[0]
    y_col = cfg.y_col or (table.headers[1] if len(table.headers) > 1 else table.headers[0])

    x_vals = table.col_values(x_col)
    y_vals = table.numeric_col(y_col)

    fig, ax = plt.subplots(figsize=cfg.figsize)
    ax.plot(x_vals, y_vals, color=cfg.color, linewidth=2, marker="o", markersize=5)
    ax.fill_between(range(len(x_vals)), y_vals, alpha=0.08, color=cfg.color)
    _setup_axes(ax, cfg.title or f"{y_col} over {x_col}", x_col, y_col)
    ax.set_xticks(range(len(x_vals)))
    ax.set_xticklabels(x_vals, rotation=30, ha="right", fontsize=9)
    plt.tight_layout()
    result = _to_png(fig)
    plt.close(fig)
    return result


def _scatter_chart(table: DataTable, cfg: ChartConfig, plt: Any) -> BytesIO:
    x_col = cfg.x_col or table.headers[0]
    y_col = cfg.y_col or (table.headers[1] if len(table.headers) > 1 else table.headers[0])

    x_vals = table.numeric_col(x_col)
    y_vals = table.numeric_col(y_col)

    fig, ax = plt.subplots(figsize=cfg.figsize)
    ax.scatter(x_vals, y_vals, color=cfg.color, alpha=0.7, edgecolors="white", s=60)
    _setup_axes(ax, cfg.title or f"{y_col} vs {x_col}", x_col, y_col)
    plt.tight_layout()
    result = _to_png(fig)
    plt.close(fig)
    return result


def _pie_chart(table: DataTable, cfg: ChartConfig, plt: Any) -> BytesIO:
    label_col = cfg.x_col or table.headers[0]
    value_col = cfg.y_col or (table.headers[1] if len(table.headers) > 1 else table.headers[0])

    labels = table.col_values(label_col)
    values = table.numeric_col(value_col)

    # Generate colour palette from the primary colour
    import colorsys, re
    hex_c = cfg.color.lstrip("#")
    r, g, b = (int(hex_c[i:i+2], 16) / 255 for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    colours = [
        "#{:02x}{:02x}{:02x}".format(
            *[int(c * 255) for c in colorsys.hsv_to_rgb((h + i / len(values)) % 1, s, v)]
        )
        for i in range(len(values))
    ]

    fig, ax = plt.subplots(figsize=cfg.figsize)
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=colours,
        autopct="%1.1f%%", startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5},
    )
    for t in autotexts:
        t.set_fontsize(9)
    ax.set_title(cfg.title or f"Distribution of {value_col}", fontsize=13, fontweight="bold")
    plt.tight_layout()
    result = _to_png(fig)
    plt.close(fig)
    return result


def _histogram(table: DataTable, cfg: ChartConfig, plt: Any) -> BytesIO:
    y_col = cfg.y_col or table.headers[-1]
    values = table.numeric_col(y_col)

    fig, ax = plt.subplots(figsize=cfg.figsize)
    ax.hist(values, bins="auto", color=cfg.color, edgecolor="white", linewidth=0.6)
    _setup_axes(ax, cfg.title or f"Distribution of {y_col}", y_col, "Frequency")
    plt.tight_layout()
    result = _to_png(fig)
    plt.close(fig)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_CHART_BUILDERS = {
    "bar":       _bar_chart,
    "line":      _line_chart,
    "scatter":   _scatter_chart,
    "pie":       _pie_chart,
    "histogram": _histogram,
}


def generate_chart(table: DataTable) -> BytesIO:
    """
    Generate a matplotlib chart from a DataTable and return it as a PNG BytesIO.

    Parameters
    ----------
    table:
        A DataTable with a non-None ``chart`` ChartConfig.

    Returns
    -------
    BytesIO
        In-memory PNG image, seeked to position 0.

    Raises
    ------
    ValueError
        If ``table.chart`` is None or the chart type is unsupported.
    KeyError
        If a referenced column name does not exist in the table headers.
    ImportError
        If matplotlib is not installed.
    """
    if table.chart is None:
        raise ValueError(f"DataTable '{table.id}' has no chart configuration.")

    try:
        import matplotlib
        matplotlib.use("Agg")   # non-interactive backend — safe for servers
        import matplotlib.pyplot as plt
        plt.rcParams.update({
            "font.family":  "DejaVu Sans",
            "font.size":    10,
            "figure.dpi":   table.chart.dpi,
        })
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for chart generation. "
            "Install with: pip install matplotlib"
        ) from exc

    chart_type = table.chart.type.lower()
    builder = _CHART_BUILDERS.get(chart_type)
    if builder is None:
        raise ValueError(
            f"Unsupported chart type '{chart_type}'. "
            f"Supported: {list(_CHART_BUILDERS)}"
        )

    logger.info(
        "Generating %s chart for table '%s' (title=%r)",
        chart_type, table.id, table.chart.title,
    )
    return builder(table, table.chart, plt)
