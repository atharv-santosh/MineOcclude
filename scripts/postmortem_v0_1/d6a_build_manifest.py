"""D6 step A/B (EXPLORATORY): mechanically select and freeze visible control rows.

Selection uses METADATA ONLY (raw/visibility.jsonl + coordinates.jsonl). No
activation value is read, computed, or inspected here. The manifest this writes
is committed BEFORE any visible activation is extracted.

Row-selection rule (frozen here, applied without discretion):
  * A frame is eligible iff visibility_class == VISIBLE_AGREEMENT, i.e. the
    geometric ray test and the rendered magenta detector BOTH say visible.
  * The entry transition region is the maximal run of non-OCCLUDED_AGREEMENT
    frames immediately preceding tau=1 (the first stable-hidden frame).
  * Candidate window = the contiguous run of eligible frames ending at the last
    eligible frame strictly before the entry transition region.
  * Take the LAST L frames of that run, so the window sits immediately before
    the transition, matching the primary evaluation's proximity to occlusion.
  * L is the largest common count available across all 25 trajectories, capped
    at 15 to match the tau1..15 primary temporal span.
  * Every selected frame additionally requires a full 16-frame causal context
    (target - 15 >= 0), matching the frozen extractor.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/sagemaker-user/MineOcclude/scripts/postmortem_v0_1")

from pm_common import (  # noqa: E402
    CONF,
    EFFECTIVE_PRECEDING,
    META,
    OUT,
    read_jsonl,
    s3_roots,
    trajectory_ids,
    write_json,
)

TARGET_LENGTH = 15


def main() -> int:
    preds = pd.read_parquet(CONF / "slice_predictions.parquet")
    meta = (
        preds[["trajectory_id", "direction", "outer_fold"]]
        .drop_duplicates()
        .set_index("trajectory_id")
    )

    candidates = {}
    for traj in trajectory_ids():
        vis = read_jsonl(META / traj / "visibility.jsonl")
        by_idx = {int(r["model_frame_idx"]): r for r in vis}
        order = sorted(by_idx)

        tau1 = next(i for i in order if by_idx[i].get("tau") == 1)

        # Entry transition = maximal non-OCCLUDED_AGREEMENT run immediately before tau1.
        transition_start = tau1
        while (
            transition_start - 1 in by_idx
            and by_idx[transition_start - 1]["visibility_class"]
            != "OCCLUDED_AGREEMENT"
            and by_idx[transition_start - 1]["visibility_class"] != "VISIBLE_AGREEMENT"
        ):
            transition_start -= 1

        # Last clean-visible frame strictly before the transition region.
        last_visible = max(
            i
            for i in order
            if i < transition_start
            and by_idx[i]["visibility_class"] == "VISIBLE_AGREEMENT"
        )
        # Contiguous clean-visible run ending there.
        run_start = last_visible
        while (
            run_start - 1 in by_idx
            and by_idx[run_start - 1]["visibility_class"] == "VISIBLE_AGREEMENT"
        ):
            run_start -= 1
        # Full-context requirement, matching the frozen extractor.
        run_start = max(run_start, EFFECTIVE_PRECEDING)

        available = last_visible - run_start + 1
        candidates[traj] = {
            "tau1_frame": tau1,
            "entry_transition_start": transition_start,
            "entry_transition_length": tau1 - transition_start,
            "last_clean_visible_frame": last_visible,
            "clean_visible_run_start_with_full_context": run_start,
            "available_clean_visible_frames": int(available),
        }

    available_counts = [c["available_clean_visible_frames"] for c in candidates.values()]
    length = int(min(min(available_counts), TARGET_LENGTH))

    rows = []
    for traj, info in candidates.items():
        last = info["last_clean_visible_frame"]
        frames = list(range(last - length + 1, last + 1))
        coords = {
            int(r["model_frame_idx"]): r
            for r in read_jsonl(META / traj / "coordinates.jsonl")
        }
        vis = {
            int(r["model_frame_idx"]): r
            for r in read_jsonl(META / traj / "visibility.jsonl")
        }
        for position, frame in enumerate(frames, start=1):
            assert vis[frame]["visibility_class"] == "VISIBLE_AGREEMENT", (traj, frame)
            assert frame - EFFECTIVE_PRECEDING >= 0
            coordinate = coords[frame]
            rows.append(
                {
                    "trajectory_id": traj,
                    "direction": str(meta.loc[traj, "direction"]),
                    "outer_fold": int(meta.loc[traj, "outer_fold"]),
                    "visible_index": position,
                    "model_frame_idx": frame,
                    "world_x": float(coordinate["world_x"]),
                    "token_row": float(coordinate["token_row"]),
                    "token_col": float(coordinate["token_col"]),
                    "context_first_frame": frame - EFFECTIVE_PRECEDING,
                    "context_last_frame": frame,
                    "visibility_class": vis[frame]["visibility_class"],
                    "magenta_area_pixels": vis[frame]["magenta_area_pixels"],
                }
            )

    frame_table = pd.DataFrame(rows)
    # Positive within-trajectory target variance is required for macro R2.
    tss = frame_table.groupby("trajectory_id")["world_x"].apply(
        lambda s: float(((s - s.mean()) ** 2).sum())
    )

    manifest = {
        "artifact_id": "regime-a-postmortem-d6-visible-positive-control-manifest-v0.1",
        "status": "EXPLORATORY_VISIBLE_POSITIVE_CONTROL",
        "frozen_before_any_visible_activation_extraction": True,
        "selection_inputs": "raw/visibility.jsonl and coordinates.jsonl metadata only",
        "selection_rule": {
            "eligible_frame": "visibility_class == VISIBLE_AGREEMENT (dual-detector)",
            "window": (
                "last L contiguous eligible frames ending at the last eligible frame "
                "strictly before the entry transition region"
            ),
            "L_target": TARGET_LENGTH,
            "L_frozen": length,
            "L_rule": "min(min available across all 25 trajectories, 15)",
            "full_context_required": "model_frame_idx - 15 >= 0",
            "no_selection_used_activation_values_or_decoding_performance": True,
        },
        "visible_rows_per_trajectory": length,
        "total_visible_rows": int(len(frame_table)),
        "trajectory_count": int(frame_table["trajectory_id"].nunique()),
        "direction_balance": frame_table.drop_duplicates("trajectory_id")[
            "direction"
        ].value_counts().to_dict(),
        "outer_folds_preserved": sorted(frame_table["outer_fold"].unique().tolist()),
        "all_trajectories_positive_tss": bool((tss > 0).all()),
        "min_trajectory_tss": float(tss.min()),
        "per_trajectory_candidates": candidates,
        "s3_roots": s3_roots(),
        "rows": rows,
    }
    digest = write_json(OUT / "visible_positive_control_manifest.json", manifest)

    print("=== D6 manifest ===")
    print("  available clean-visible frames per trajectory:",
          f"min={min(available_counts)} max={max(available_counts)}")
    print("  frozen L (rows per trajectory):", length)
    print("  total visible rows:", len(frame_table))
    print("  direction balance:", manifest["direction_balance"])
    print("  all positive TSS:", manifest["all_trajectories_positive_tss"],
          "| min TSS:", round(manifest["min_trajectory_tss"], 6))
    span = frame_table.groupby("trajectory_id")["world_x"].agg(lambda s: s.max() - s.min())
    print(f"  visible target range blocks: min={span.min():.4f} "
          f"med={span.median():.4f} max={span.max():.4f}")
    print("  sha256:", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
