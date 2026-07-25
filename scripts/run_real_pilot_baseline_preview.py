"""Preview: run last-seen/constant-velocity on Person C's real pilot data.

This is explicitly a PREVIEW, not a scored scientific result: every
context built here carries ``fold = mineocclude.baselines
.capture_ingest.UNASSIGNED_FOLD`` because no real, sealed Person B fold
manifest exists yet. Once one does, re-run through
``mineocclude.baselines.export.attach_b_fold_assignments`` and
``build_baseline_document`` before treating any of this as B-scored.

Usage:
    python scripts/run_real_pilot_baseline_preview.py <data_root> [--out report.json]

``<data_root>`` is expected to contain one directory per accepted
episode, each with ``capture_package_v0_1.json`` and a
``package_v0_1/`` subdirectory holding ``server_state.jsonl``,
``visibility.jsonl``, and ``frame_map.jsonl`` -- Person C's real
trajectory contract layout
(docs/contracts/trajectory_v1.md).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.baselines.capture_ingest import (  # noqa: E402
    CaptureIngestError,
    build_contexts_from_capture,
)
from mineocclude.baselines.constant_velocity import predict_constant_velocity  # noqa: E402
from mineocclude.baselines.last_seen import predict_last_seen  # noqa: E402


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _find_episode_dirs(data_root: Path) -> list[Path]:
    return sorted(
        path.parent
        for path in data_root.glob("*/capture_package_v0_1.json")
        if (path.parent / "package_v0_1" / "server_state.jsonl").exists()
    )


def _ingest_episode(episode_dir: Path):
    package = json.loads(
        (episode_dir / "capture_package_v0_1.json").read_text(encoding="utf-8")
    )
    manifest = package["episode_manifest"]
    package_dir = episode_dir / "package_v0_1"

    contexts = build_contexts_from_capture(
        _load_jsonl(package_dir / "frame_map.jsonl"),
        _load_jsonl(package_dir / "server_state.jsonl"),
        _load_jsonl(package_dir / "visibility.jsonl"),
        layout_id=manifest["layout_id"],
        config_hash=manifest["config_hash"],
        regime="A" if manifest.get("regime") == "regime_a" else "B",
        v_scripted_blocks_per_s=manifest.get("v"),
        q_scripted_blocks2_per_s=manifest.get("q"),
        duration_seconds=manifest.get("duration"),
        seed=manifest.get("seed"),
        dt_seconds=manifest.get("dt_seconds", 0.05),
    )
    return manifest["trajectory_id"], manifest["layout_id"], contexts


def _summarize(rows) -> dict[str, Any]:
    applicable = [row for row in rows if row.target_name == "mu_oracle_blocks" and row.applicable]
    predictions = [row.prediction for row in applicable]
    summary: dict[str, Any] = {
        "total_rows": sum(1 for row in rows if row.target_name == "mu_oracle_blocks"),
        "applicable_rows": len(applicable),
    }
    if predictions:
        summary["prediction_mean"] = statistics.fmean(predictions)
        summary["prediction_min"] = min(predictions)
        summary["prediction_max"] = max(predictions)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    episode_dirs = _find_episode_dirs(args.data_root)
    if not episode_dirs:
        print(f"No real episode packages found under {args.data_root}", file=sys.stderr)
        raise SystemExit(1)

    per_episode: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for episode_dir in episode_dirs:
        try:
            trajectory_id, layout_id, contexts = _ingest_episode(episode_dir)
        except (CaptureIngestError, KeyError, OSError) as error:
            skipped.append({"episode_dir": episode_dir.name, "reason": str(error)})
            continue

        last_seen_rows = predict_last_seen(contexts)
        velocity_rows = predict_constant_velocity(contexts)

        per_episode.append(
            {
                "trajectory_id": trajectory_id,
                "layout_id": layout_id,
                "frame_count": len(contexts),
                "last_seen": _summarize(last_seen_rows),
                "constant_velocity": _summarize(velocity_rows),
            }
        )

    report = {
        "report_type": "person_d_real_pilot_baseline_preview",
        "scientific_use": "forbidden",
        "reason": "no real sealed B fold_manifest attached; every context uses UNASSIGNED_FOLD",
        "episodes_processed": len(per_episode),
        "episodes_skipped": skipped,
        "per_episode": per_episode,
    }

    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)

    print(
        f"\n{len(per_episode)} real episode(s) processed, "
        f"{len(skipped)} skipped.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
