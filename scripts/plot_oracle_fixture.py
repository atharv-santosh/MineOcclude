"""Render a dependency-free SVG audit plot for one Person B trajectory."""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.contracts.identity import FRAME_KEY, SCHEMA_VERSION  # noqa: E402
from mineocclude.oracle.schema import (  # noqa: E402
    ORACLE_TARGET_SCHEMA_VERSION,
    OracleValidationError,
    validate_oracle_target,
)


def _validated_rows(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise OracleValidationError("Plot input has the wrong schema_version.")
    if document.get("target_schema_version") != ORACLE_TARGET_SCHEMA_VERSION:
        raise OracleValidationError("Plot input has the wrong target_schema_version.")
    if document.get("join_key") != list(FRAME_KEY):
        raise OracleValidationError("Plot input has the wrong join_key.")

    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise OracleValidationError("Plot input requires at least one target row.")
    for row in rows:
        validate_oracle_target(row)

    trajectory_ids = {row["trajectory_id"] for row in rows}
    if len(trajectory_ids) != 1:
        raise OracleValidationError("One audit plot may contain only one trajectory.")
    return sorted(rows, key=lambda row: row["model_frame_idx"])


def _points(
    rows: list[dict[str, Any]],
    y_px: Callable[[float], float],
    field: str,
) -> str:
    return " ".join(
        f"{row['_x']:.2f},{y_px(float(row[field])):.2f}" for row in rows
    )


def _circles(
    rows: list[dict[str, Any]],
    y_px: Callable[[float], float],
    field: str,
    radius: float,
) -> str:
    return "".join(
        f'<circle cx="{row["_x"]:.2f}" cy="{y_px(float(row[field])):.2f}" '
        f'r="{radius}"/>'
        for row in rows
    )


def build_svg(document: Mapping[str, Any]) -> str:
    rows = _validated_rows(document)
    width, height = 840, 540
    left, right, top, bottom = 80, 40, 135, 70
    plot_width = width - left - right
    plot_height = height - top - bottom

    x_values = [float(row["model_frame_idx"]) for row in rows]
    y_candidates: list[float] = []
    for row in rows:
        mean = float(row["mu_oracle_blocks"])
        sigma = float(row["sigma_oracle_blocks"])
        y_candidates.extend(
            (
                float(row["x_true_blocks"]),
                float(row["last_visible_position_blocks"]),
                mean - 2 * sigma,
                mean + 2 * sigma,
            )
        )

    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_candidates), max(y_candidates)
    x_span = max(x_max - x_min, 1.0)
    y_span = max(y_max - y_min, 1.0)
    y_min -= 0.08 * y_span
    y_max += 0.08 * y_span
    y_span = y_max - y_min

    def x_px(value: float) -> float:
        return left + (value - x_min) / x_span * plot_width

    def y_px(value: float) -> float:
        return top + (y_max - value) / y_span * plot_height

    prepared = [
        {**row, "_x": x_px(float(row["model_frame_idx"]))} for row in rows
    ]

    def band(multiplier: float) -> str:
        upper = [
            (
                row["_x"],
                y_px(
                    float(row["mu_oracle_blocks"])
                    + multiplier * float(row["sigma_oracle_blocks"])
                ),
            )
            for row in prepared
        ]
        lower = [
            (
                row["_x"],
                y_px(
                    float(row["mu_oracle_blocks"])
                    - multiplier * float(row["sigma_oracle_blocks"])
                ),
            )
            for row in reversed(prepared)
        ]
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in upper + lower)

    x_ticks = "".join(
        f'<text x="{x_px(value):.2f}" y="{height - 35}" text-anchor="middle">'
        f"{value:g}</text>"
        for value in x_values
    )
    y_ticks = ""
    for index in range(5):
        value = y_min + index * y_span / 4
        y = y_px(value)
        y_ticks += (
            f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" '
            'class="grid"/>'
            f'<text x="{left-12}" y="{y+5:.2f}" text-anchor="end">{value:.2f}</text>'
        )

    trajectory_id = html.escape(str(rows[0]["trajectory_id"]))
    mean_points = _points(prepared, y_px, "mu_oracle_blocks")
    truth_points = _points(prepared, y_px, "x_true_blocks")
    last_seen_points = _points(prepared, y_px, "last_visible_position_blocks")

    return f'''<svg xmlns="http://www.w3.org/2000/svg"
  width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    text {{ font-family: Arial, sans-serif; font-size: 13px; fill: #1f2937; }}
    .title {{ font-size: 22px; font-weight: 700; }}
    .subtitle {{ font-size: 12px; fill: #4b5563; }}
    .axis {{ stroke: #374151; stroke-width: 1.5; }}
    .grid {{ stroke: #e5e7eb; stroke-width: 1; }}
  </style>
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{left}" y="28" class="title">Regime A synthetic oracle validation</text>
  <text x="{left}" y="47" class="subtitle">trajectory: {trajectory_id}</text>
  {y_ticks}
  <polygon points="{band(2.0)}" fill="#bfdbfe" opacity="0.55"/>
  <polygon points="{band(1.0)}" fill="#60a5fa" opacity="0.45"/>
  <line x1="{left}" y1="{top+plot_height}"
    x2="{width-right}" y2="{top+plot_height}" class="axis"/>
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_height}" class="axis"/>
  {x_ticks}
  <polyline points="{last_seen_points}" fill="none" stroke="#6b7280"
    stroke-width="2" stroke-dasharray="2 5"/>
  <polyline points="{mean_points}" fill="none" stroke="#1d4ed8" stroke-width="3"/>
  <polyline points="{truth_points}" fill="none" stroke="#dc2626"
    stroke-width="2.5" stroke-dasharray="7 5"/>
  <g fill="#1d4ed8">{_circles(prepared, y_px, "mu_oracle_blocks", 4)}</g>
  <g fill="#dc2626">{_circles(prepared, y_px, "x_true_blocks", 3.5)}</g>
  <text x="{left + plot_width/2:.2f}" y="{height-8}"
    text-anchor="middle">model frame index</text>
  <text x="18" y="{top + plot_height/2:.2f}" text-anchor="middle"
    transform="rotate(-90 18 {top + plot_height/2:.2f})">
    wall-parallel position (blocks)
  </text>
  <g transform="translate({width-290},20)">
    <rect x="0" y="0" width="250" height="100" rx="6"
      fill="#ffffff" stroke="#d1d5db"/>
    <line x1="14" y1="19" x2="48" y2="19"
      stroke="#1d4ed8" stroke-width="3"/>
    <text x="58" y="24">posterior mean</text>
    <line x1="14" y1="41" x2="48" y2="41"
      stroke="#6b7280" stroke-width="2" stroke-dasharray="2 5"/>
    <text x="58" y="46">last visible position</text>
    <line x1="14" y1="63" x2="48" y2="63"
      stroke="#dc2626" stroke-width="2.5" stroke-dasharray="7 5"/>
    <text x="58" y="68">truth (scoring only)</text>
    <rect x="14" y="79" width="34" height="12"
      fill="#60a5fa" opacity="0.45"/>
    <text x="58" y="90">+/-1 sigma (outer: +/-2)</text>
  </g>
</svg>
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot one validated Person B oracle-target trajectory."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_svg(document), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
