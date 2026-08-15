"""GATE B: rendered-pixel equivalence of the rebuilt runtime against history.

Coordinate bit-exactness (GATE A / p2_path_equivalence_authority.json) proves the
SERVER-side motion recurrence is identical. It says nothing about the CLIENT-side
rasterisation that actually produces the frames MineWorld consumes. This gate
measures that directly against hash-bound historical Regime A frames.

Frame selection is metadata-only and fixed before any difference is inspected:
for each of the two prospectively chosen replay specifications (one per
direction), take the first, middle and last frame of each visibility class
(VISIBLE_AGREEMENT, VISIBILITY_DISAGREEMENT, OCCLUDED_AGREEMENT). That covers
the clearly-visible, wall-transition and fully-occluded conditions the gate
requires.

Equivalence rule: EXACT. The project has no authorised rendering tolerance, and
its own precedent for apparatus equivalence is exact
(d6_equivalence_receipt.json: bitwise_identical=true, max_abs_diff=0.0). No
tolerance is invented here after observing differences.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from p2_common import OUT, REPO, WALL_META, WORK, read_jsonl, sha256_file, write_json

HIST = WORK / "historical_frames"
REPLAY = WORK / "path_replay"
CLASSES = ("VISIBLE_AGREEMENT", "VISIBILITY_DISAGREEMENT", "OCCLUDED_AGREEMENT")


def select_frames(spec_id: str) -> list[dict[str, Any]]:
    """First / middle / last frame of each visibility class. Metadata only."""
    vis = read_jsonl(WALL_META / spec_id / "visibility.jsonl")
    by_class: dict[str, list[int]] = {}
    for row in vis:
        by_class.setdefault(row["visibility_class"], []).append(int(row["model_frame_idx"]))
    chosen: dict[int, str] = {}
    for name in CLASSES:
        frames = sorted(by_class.get(name, []))
        if not frames:
            continue
        for frame in (frames[0], frames[len(frames) // 2], frames[-1]):
            chosen[frame] = name
    return [{"model_frame_idx": f, "visibility_class": c}
            for f, c in sorted(chosen.items())]


def fetch_historical(spec_id: str, frames: list[int]) -> dict[int, Path]:
    """Retrieve the minimum historical frames and hash-bind each one."""
    receipt = json.loads((WALL_META / spec_id / "durable_receipt.json").read_text())
    index = {o["key"].split(f"/{spec_id}/", 1)[1]: o
             for o in receipt["objects"] if f"/{spec_id}/" in o["key"]}
    directory = HIST / spec_id
    directory.mkdir(parents=True, exist_ok=True)
    out: dict[int, Path] = {}
    for frame in frames:
        key = f"raw/frames/{frame:06d}.png"
        obj = index[key]
        path = directory / f"{frame:06d}.png"
        if not path.is_file():
            subprocess.run(
                ["aws", "s3", "cp", f"s3://{obj['bucket']}/{obj['key']}", str(path),
                 "--quiet"], check=True)
        if sha256_file(path) != obj["local_sha256"]:
            raise RuntimeError(f"historical frame hash mismatch: {spec_id}/{key}")
        out[frame] = path
    return out


def detector(path: Path) -> tuple[str, Any]:
    from mineocclude.vision.magenta import HsvRange, detect_magenta
    from scripts.run_regime_a import detector_rgb_rows

    cfg = json.loads((REPO / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1"
                             "/detector_candidate_config.json").read_text()
                     )["configuration"]["detector_settings"]
    result = detect_magenta(
        detector_rgb_rows(path, expected_size=(640, 360)),
        hsv_ranges=tuple(HsvRange(*v) for v in cfg["hsv_ranges"]),
        min_area_pixels=cfg["min_area_pixels"], max_area_pixels=cfg["max_area_pixels"],
        open_iterations=cfg["open_iterations"], close_iterations=cfg["close_iterations"],
        morphology_radius_pixels=cfg["morphology_radius_pixels"],
        connectivity=cfg["connectivity"])
    return result.status, result.area_pixels


def main() -> int:
    authority = json.loads((OUT / "p2_path_equivalence_authority.json").read_text())
    specs = [u["trajectory_spec_id"] for u in authority["units"]]

    comparisons: list[dict[str, Any]] = []
    for spec_id in specs:
        selection = select_frames(spec_id)
        frames = [s["model_frame_idx"] for s in selection]
        historical = fetch_historical(spec_id, frames)
        for item in selection:
            frame = item["model_frame_idx"]
            hist_path = historical[frame]
            replay_path = REPLAY / spec_id / "raw/frames" / f"{frame:06d}.png"
            if not replay_path.is_file():
                raise RuntimeError(f"replay frame missing: {replay_path}")
            a = np.asarray(Image.open(hist_path).convert("RGB"), dtype=np.int16)
            b = np.asarray(Image.open(replay_path).convert("RGB"), dtype=np.int16)
            delta = np.abs(a - b)
            hist_status, hist_area = detector(hist_path)
            replay_status, replay_area = detector(replay_path)
            comparisons.append({
                "trajectory_spec_id": spec_id,
                "model_frame_idx": frame,
                "visibility_class": item["visibility_class"],
                "historical_sha256": sha256_file(hist_path),
                "historical_hash_bound_to_durable_receipt": True,
                "file_bytes_identical": sha256_file(hist_path) == sha256_file(replay_path),
                "decoded_pixels_identical": bool(delta.max() == 0),
                "n_differing_pixels": int((delta.sum(axis=2) > 0).sum()),
                "total_pixels": int(a.shape[0] * a.shape[1]),
                "max_abs_channel_difference": int(delta.max()),
                "mean_abs_channel_difference": float(delta.mean()),
                "detector_historical": {"status": hist_status, "area_pixels": hist_area},
                "detector_replay": {"status": replay_status, "area_pixels": replay_area},
                "detector_status_changed": hist_status != replay_status,
                "detector_area_changed": hist_area != replay_area,
            })

    total = len(comparisons)
    identical = sum(c["decoded_pixels_identical"] for c in comparisons)
    status_changed = [c for c in comparisons if c["detector_status_changed"]]
    area_changed = sum(c["detector_area_changed"] for c in comparisons)

    # Any frozen Regime A target frame whose detector verdict flipped is decisive:
    # it would rewrite the visibility ground truth the closed analysis relies on.
    target_flips = []
    for c in status_changed:
        inventory = json.loads(
            (WALL_META / c["trajectory_spec_id"] / "activation_inventory.json").read_text())
        if c["model_frame_idx"] in inventory["target_model_frame_indices"]:
            tau = inventory["target_tau"][
                inventory["target_model_frame_indices"].index(c["model_frame_idx"])]
            target_flips.append({**{k: c[k] for k in
                                    ("trajectory_spec_id", "model_frame_idx",
                                     "detector_historical", "detector_replay")},
                                 "tau": tau})

    passed = identical == total
    payload = {
        "artifact_id": "regime-a-prime-p2-render-equivalence-receipt-v0.1",
        "schema_version": "1.0",
        "phase": "P2",
        "gate": "GATE_B_RENDERED_PIXEL_EQUIVALENCE",
        "status": "PASS" if passed else "FAIL",
        "PATCH_RENDER_EQUIVALENCE": "PASS" if passed else "FAIL",
        "historical_pixels_available": True,
        "historical_pixel_frame_count": total,
        "all_historical_frames_hash_verified": True,
        "equivalence_rule": "EXACT_PIXEL_EQUALITY",
        "equivalence_rule_basis":
            "no authorised rendering tolerance exists in the project; the project's own "
            "apparatus-equivalence precedent (d6_equivalence_receipt.json) is exact "
            "(bitwise_identical=true, max_abs_diff=0.0)",
        "tolerance_invented_after_seeing_differences": False,
        "frame_selection_rule":
            "metadata only: first, middle and last frame of each visibility class for "
            "each of the two prospectively chosen replay specifications",
        "frames_decoded_pixel_identical": identical,
        "frames_with_pixel_differences": total - identical,
        "max_differing_pixels_in_a_frame": max(c["n_differing_pixels"] for c in comparisons),
        "max_abs_channel_difference": max(c["max_abs_channel_difference"] for c in comparisons),
        "detector_status_changed_count": len(status_changed),
        "detector_area_changed_count": area_changed,
        "detector_status_changes": status_changed,
        "frozen_target_frame_detector_flips": target_flips,
        "materiality": (
            "MATERIAL: the rebuilt runtime changes the magenta detector verdict on "
            "frozen Regime A target frames, converting occluded frames into frames "
            "carrying rendered evidence, and alters detected area on most frames. The "
            "same pixels feed MineWorld, so P2 activations would not be comparable to "
            "the historical apparatus."
        ) if not passed else "NONE",
        "root_cause": {
            "diagnosis": "client-side software rasterisation differs; server-side motion "
                         "is unaffected, which is why coordinates are bit-exact while "
                         "pixels are not",
            "current_renderer": "Mesa 25.2.8-0ubuntu0.24.04.2, llvmpipe (LLVM 20.1.2)",
            "current_xvfb": "2:21.1.12-1ubuntu1.6",
            "original_renderer": "UNKNOWN_NOT_RECORDED",
            "original_gl_stack_location": "bundled operator-tools DRI drivers on the wiped "
                                          "NVMe (LIBGL_DRIVERS_PATH pointed into "
                                          "operator-tools/root/usr/lib/x86_64-linux-gnu/dri)",
            "operator_tools_recoverable": False,
            "searched": ["local $HOME archives", "durable S3 mineocclude prefix"],
            "provenance_gap": "mineocclude-capture-runtime-receipt.json pins Java, "
                              "Minecraft, Fabric and mod hashes but records NO renderer, "
                              "Mesa, GL, DRI or Xvfb identity, so the original rendering "
                              "stack cannot be reconstructed from frozen authority",
        },
        "consequence": "P2 no-wall scientific capture must not proceed on this runtime",
        "comparisons": comparisons,
    }
    digest = write_json(OUT / "p2_render_equivalence_receipt.json", payload)

    print(f"PATCH_RENDER_EQUIVALENCE={payload['PATCH_RENDER_EQUIVALENCE']}")
    print(f"HISTORICAL_PIXEL_FRAME_COUNT={total}")
    print(f"PIXEL_EQUIVALENCE_RULE=EXACT_PIXEL_EQUALITY")
    print(f"frames_pixel_identical={identical}/{total} "
          f"detector_status_changed={len(status_changed)} "
          f"detector_area_changed={area_changed}")
    print(f"frozen_target_frame_detector_flips={len(target_flips)}")
    print(f"RECEIPT_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
