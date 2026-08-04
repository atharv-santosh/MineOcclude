"""Render a validated Person E figure input as a dependency-free SVG."""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.figure_inputs import (  # noqa: E402
    validate_figure_input,
)
from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_bytes_exclusive,
    write_json_exclusive,
)
from mineocclude.vision.config import DEFAULT_PERSON_E_CONFIG_PATH  # noqa: E402


COLORS = (
    "#2563eb",
    "#dc2626",
    "#059669",
    "#7c3aed",
    "#d97706",
    "#0891b2",
    "#be185d",
    "#4b5563",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render validated, provenance-complete figure rows to an immutable SVG."
        )
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest_output", type=Path)
    parser.add_argument("--caption-file", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_PERSON_E_CONFIG_PATH)
    return parser.parse_args()


def _number(value: float) -> str:
    if math.isclose(value, round(value), rel_tol=0.0, abs_tol=1e-10):
        return str(int(round(value)))
    return f"{value:.4g}"


def _scale(value: float, minimum: float, maximum: float, start: float, size: float) -> float:
    if math.isclose(minimum, maximum):
        return start + size / 2.0
    return start + (value - minimum) * size / (maximum - minimum)


def _text(x: float, y: float, value: object, *, css: str = "detail") -> str:
    return (
        f'<text class="{css}" x="{x:.1f}" y="{y:.1f}">'
        f"{escape(str(value))}</text>"
    )


def render_svg(document: dict[str, Any]) -> str:
    """Return a deterministic SVG with values and provenance visible."""

    rows = document["rows"]
    valid_rows = [row for row in rows if row["status"] == "valid"]
    invalid_rows = [row for row in rows if row["status"] == "invalid"]
    series = sorted({row["series_id"] for row in valid_rows})
    color_by_series = {
        name: COLORS[index % len(COLORS)] for index, name in enumerate(series)
    }

    width = 1200
    table_row_height = 22
    height = max(720, 620 + table_row_height * len(rows))
    plot_left = 90.0
    plot_top = 105.0
    plot_width = 720.0
    plot_height = 390.0

    if valid_rows:
        x_values = [float(row["x"]) for row in valid_rows]
        y_values = [float(row["y"]) for row in valid_rows]
        y_values.extend(
            float(row[field])
            for row in valid_rows
            for field in ("lower", "upper")
            if row[field] is not None
        )
        x_min, x_max = min(x_values), max(x_values)
        y_min, y_max = min(y_values), max(y_values)
    else:
        x_min, x_max, y_min, y_max = 0.0, 1.0, 0.0, 1.0

    def x_position(value: float) -> float:
        return _scale(value, x_min, x_max, plot_left, plot_width)

    def y_position(value: float) -> float:
        return _scale(value, y_min, y_max, plot_top + plot_height, -plot_height)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" role="img">'
        ),
        f"<title>{escape(document['figure_id'])}</title>",
        (
            "<desc>Validated machine-rendered figure. Units, sample counts, "
            "uncertainty types, and source run IDs are shown below the plot.</desc>"
        ),
        "<style>",
        "text { font-family: Arial, sans-serif; fill: #111827; }",
        ".title { font-size: 24px; font-weight: 700; }",
        ".subtitle { font-size: 13px; fill: #4b5563; }",
        ".axis { stroke: #111827; stroke-width: 1.3; }",
        ".grid { stroke: #d1d5db; stroke-width: 0.8; }",
        ".tick { font-size: 11px; fill: #4b5563; }",
        ".detail { font-size: 12px; }",
        ".header { font-size: 12px; font-weight: 700; }",
        ".invalid { font-size: 12px; fill: #b91c1c; }",
        "</style>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        _text(45, 38, document["figure_id"], css="title"),
        _text(
            45,
            62,
            (
                f"family={document['figure_family']} | "
                f"figure_input_hash={document['figure_input_hash'][:16]}…"
            ),
            css="subtitle",
        ),
    ]

    for index in range(6):
        fraction = index / 5.0
        x = plot_left + fraction * plot_width
        y = plot_top + plot_height - fraction * plot_height
        x_value = x_min + fraction * (x_max - x_min)
        y_value = y_min + fraction * (y_max - y_min)
        lines.extend(
            [
                f'<line class="grid" x1="{x:.1f}" y1="{plot_top:.1f}" '
                f'x2="{x:.1f}" y2="{plot_top + plot_height:.1f}"/>',
                f'<line class="grid" x1="{plot_left:.1f}" y1="{y:.1f}" '
                f'x2="{plot_left + plot_width:.1f}" y2="{y:.1f}"/>',
                _text(x - 10, plot_top + plot_height + 19, _number(x_value), css="tick"),
                _text(plot_left - 55, y + 4, _number(y_value), css="tick"),
            ]
        )
    lines.extend(
        [
            f'<line class="axis" x1="{plot_left:.1f}" '
            f'y1="{plot_top + plot_height:.1f}" '
            f'x2="{plot_left + plot_width:.1f}" '
            f'y2="{plot_top + plot_height:.1f}"/>',
            f'<line class="axis" x1="{plot_left:.1f}" y1="{plot_top:.1f}" '
            f'x2="{plot_left:.1f}" y2="{plot_top + plot_height:.1f}"/>',
        ]
    )

    rows_by_series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in valid_rows:
        rows_by_series[row["series_id"]].append(row)
    for series_id in series:
        series_rows = rows_by_series[series_id]
        color = color_by_series[series_id]
        points = " ".join(
            f"{x_position(float(row['x'])):.1f},{y_position(float(row['y'])):.1f}"
            for row in series_rows
        )
        if len(series_rows) > 1:
            lines.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" '
                'stroke-width="2"/>'
            )
        for row in series_rows:
            x = x_position(float(row["x"]))
            y = y_position(float(row["y"]))
            if row["lower"] is not None:
                lower = y_position(float(row["lower"]))
                upper = y_position(float(row["upper"]))
                lines.extend(
                    [
                        f'<line x1="{x:.1f}" y1="{lower:.1f}" x2="{x:.1f}" '
                        f'y2="{upper:.1f}" stroke="{color}"/>',
                        f'<line x1="{x - 4:.1f}" y1="{lower:.1f}" '
                        f'x2="{x + 4:.1f}" y2="{lower:.1f}" stroke="{color}"/>',
                        f'<line x1="{x - 4:.1f}" y1="{upper:.1f}" '
                        f'x2="{x + 4:.1f}" y2="{upper:.1f}" stroke="{color}"/>',
                    ]
                )
            lines.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>'
            )

    x_units = ", ".join(sorted({row["x_unit"] for row in rows}))
    y_units = ", ".join(sorted({row["y_unit"] for row in rows}))
    lines.extend(
        [
            _text(plot_left + plot_width / 2 - 50, 535, f"x unit: {x_units}"),
            _text(plot_left, 558, f"y unit: {y_units}"),
            _text(850, 105, "Series", css="header"),
        ]
    )
    for index, series_id in enumerate(series):
        y = 130 + index * 22
        color = color_by_series[series_id]
        lines.append(
            f'<rect x="850" y="{y - 11}" width="12" height="12" fill="{color}"/>'
        )
        lines.append(_text(870, y, series_id))

    table_y = 600.0
    lines.append(
        _text(
            45,
            table_y,
            "source result | n | uncertainty | units | source run | lifecycle",
            css="header",
        )
    )
    for index, row in enumerate(rows):
        y = table_y + (index + 1) * table_row_height
        if row["status"] == "valid":
            detail = (
                f"{row['source_result_id']} | n={row['sample_count']} | "
                f"{row['uncertainty_type']} | {row['x_unit']} → {row['y_unit']} | "
                f"run={row['source_run_id']} | {row['source_lifecycle']}"
            )
            lines.append(_text(45, y, detail))
        else:
            detail = (
                f"{row['source_result_id']} | INVALID | run={row['source_run_id']} | "
                f"{row['source_lifecycle']} | {row['diagnostic']}"
            )
            lines.append(_text(45, y, detail, css="invalid"))

    if invalid_rows:
        lines.append(
            _text(
                850,
                470,
                f"Invalid rows retained: {len(invalid_rows)}",
                css="invalid",
            )
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    document, input_file_hash = load_json_with_sha256(args.input)
    if not isinstance(document, dict):
        raise ValueError("Figure input must be a JSON mapping.")
    validate_figure_input(document, config_path=args.config)
    try:
        caption_bytes = args.caption_file.read_bytes()
        caption = caption_bytes.decode("utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"Could not read UTF-8 caption: {error}") from error
    if not caption:
        raise ValueError("Caption file must contain non-empty text.")
    if args.output.exists() or args.manifest_output.exists():
        raise FileExistsError("SVG and manifest outputs must both be new.")
    svg_bytes = render_svg(document).encode("utf-8")
    write_bytes_exclusive(args.output, svg_bytes)
    write_json_exclusive(
        args.manifest_output,
        {
            "rendered_figure_manifest_schema_version": (
                "person-e-rendered-figure-manifest-v0.1"
            ),
            "figure_id": document["figure_id"],
            "figure_family": document["figure_family"],
            "result_scope": document["result_scope"],
            "figure_input_file_hash": input_file_hash,
            "figure_input_hash": document["figure_input_hash"],
            "code_sha": document["code_sha"],
            "config_hash": document["config_hash"],
            "source_artifact_hashes": document["source_artifact_hashes"],
            "source_run_ids": document["source_run_ids"],
            "accepted_manifest_hashes": document["accepted_manifest_hashes"],
            "fold_manifest_hashes": document["fold_manifest_hashes"],
            "renderer_id": "scripts/render_figure_svg.py:v0.1",
            "media_type": "image/svg+xml",
            "caption": caption,
            "caption_hash": hashlib.sha256(caption_bytes).hexdigest(),
            "output_sha256": hashlib.sha256(svg_bytes).hexdigest(),
        },
    )


if __name__ == "__main__":
    main()
