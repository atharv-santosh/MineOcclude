"""D7 (EXPLORATORY, optional): descriptive physical-scale context.

Derived entirely from existing frozen metadata (coordinates.jsonl for the frozen
world->screen->token projection, visibility.jsonl for the rendered magenta
footprint). No new capture, no new model call.

INTERPRETIVE CONSTRAINT
    Token pitch is reported as DESCRIPTIVE SCALE CONTEXT ONLY. Token activations
    are continuous high-dimensional features and can in principle encode
    sub-token position. Nothing here asserts a hard representational resolution
    bound.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/sagemaker-user/MineOcclude/scripts/postmortem_v0_1")

from pm_common import CONF, META, OUT, read_jsonl, summarize, trajectory_ids, write_json  # noqa: E402


def main() -> int:
    # Blocks per token column, from the frozen projection itself: regress
    # token_col on world_x over clean-visible frames of each trajectory.
    pitches, widths, areas = [], [], []
    per_traj = []
    for traj in trajectory_ids():
        coords = {int(r["model_frame_idx"]): r for r in read_jsonl(META / traj / "coordinates.jsonl")}
        vis = read_jsonl(META / traj / "visibility.jsonl")
        visible = [
            r for r in vis
            if r["visibility_class"] == "VISIBLE_AGREEMENT"
            and r["magenta_area_pixels"]
        ]
        if len(visible) < 3:
            continue
        idx = [int(r["model_frame_idx"]) for r in visible]
        x = np.array([coords[i]["world_x"] for i in idx], dtype=np.float64)
        col = np.array([coords[i]["token_col"] for i in idx], dtype=np.float64)
        slope = float(np.polyfit(x, col, 1)[0])  # token columns per block
        pitch = 1.0 / abs(slope) if slope != 0 else float("nan")  # blocks per column

        px = np.array([r["magenta_area_pixels"] for r in visible], dtype=np.float64)
        # Frames are 640x360 mapped onto a 24x14 token grid.
        px_per_token_cell = (640.0 / 24.0) * (360.0 / 14.0)
        per_traj.append(
            {
                "trajectory_id": traj,
                "clean_visible_frames_used": len(visible),
                "token_columns_per_block": slope,
                "blocks_per_token_column": pitch,
                "median_magenta_area_pixels": float(np.median(px)),
                "max_magenta_area_pixels": float(px.max()),
                "median_token_cell_footprint": float(np.median(px) / px_per_token_cell),
            }
        )
        pitches.append(pitch)
        areas.append(float(np.median(px)))
        widths.append(float(np.sqrt(np.median(px))))

    preds = pd.read_parquet(CONF / "slice_predictions.parquet")
    primary = preds[preds["tau"].between(1, 15)]
    disp = primary.groupby("trajectory_id")["world_x"].agg(lambda s: abs(s.iloc[-1] - s.iloc[0]))
    rng = primary.groupby("trajectory_id")["world_x"].agg(lambda s: s.max() - s.min())

    pitch_summary = summarize(pitches)
    payload = {
        "artifact_id": "regime-a-postmortem-d7-physical-scale-v0.1",
        "status": "EXPLORATORY_DESCRIPTIVE_ONLY",
        "interpretive_constraint": (
            "Token pitch is descriptive scale context. Token activations are "
            "continuous high-dimensional features and can in principle encode "
            "sub-token position. No hard representational resolution bound is claimed."
        ),
        "frame_geometry": {
            "render_resolution": [640, 360],
            "token_grid": [14, 24],
            "pixels_per_token_cell": (640.0 / 24.0) * (360.0 / 14.0),
            "pixels_per_token_column_width": 640.0 / 24.0,
        },
        "blocks_per_token_column": pitch_summary,
        "sheep_rendered_footprint": {
            "median_magenta_area_pixels": summarize(areas),
            "implied_median_square_side_pixels": summarize(widths),
            "median_token_cell_footprint": summarize(
                [r["median_token_cell_footprint"] for r in per_traj]
            ),
        },
        "primary_hidden_motion": {
            "abs_displacement_tau1_to_tau15_blocks": summarize(disp.tolist()),
            "target_range_blocks": summarize(rng.tolist()),
            "median_displacement_in_token_columns": float(
                np.median(disp.to_numpy()) / pitch_summary["median"]
            ),
        },
        "per_trajectory": per_traj,
    }
    digest = write_json(OUT / "d7_physical_scale.json", payload)

    print("=== D7 descriptive scale ===")
    print(f"  blocks per token column      : median {pitch_summary['median']:.4f} "
          f"(min {pitch_summary['min']:.4f}, max {pitch_summary['max']:.4f})")
    print(f"  sheep magenta area (px)      : median {summarize(areas)['median']:.0f}")
    print(f"  sheep token-cell footprint   : median "
          f"{summarize([r['median_token_cell_footprint'] for r in per_traj])['median']:.3f} cells")
    print(f"  hidden displacement (blocks) : median {np.median(disp.to_numpy()):.4f}")
    print(f"  hidden displacement (columns): median "
          f"{payload['primary_hidden_motion']['median_displacement_in_token_columns']:.3f}")
    print("  sha256:", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
