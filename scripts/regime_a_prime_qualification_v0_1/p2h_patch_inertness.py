"""STEP 5: patch-inertness gate on the CURRENT apparatus.

Replaces the impossible requirement that the rebuilt renderer reproduce
HISTORICAL pixels. Here the renderer is held constant and only the server mod
changes, so the question is exact and answerable:

    did the startspec patch alter NORMAL-scene behaviour on this apparatus?

Comparator: the pre-patch current-runtime wall replay preserved at
path_replay_prepatch/. Same two prospectively chosen wall specifications, same
seeds, same wall condition.

Requirements (no tolerance):
  A. coordinates  -- 260/260 exactly identical, max difference exactly 0
  B. decoded RGB  -- exact equality on the metadata-fixed frame subset
  C. detector     -- no status flip, no area change

Does NOT touch p2_path_equivalence_authority.json, which is frozen at 6943e04.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from p2_common import OUT, WORK, CaptureSession, read_jsonl, sha256_file, source_specs, write_json
from p2f_render_equivalence import detector, select_frames

PRE = WORK / "path_replay_prepatch"
POST = WORK / "path_replay_postpatch"
REPLAY_EPISODE_BASE = 60000
MOD_JAR = Path("/home/sagemaker-user/mineocclude-server/mods/mineocclude-0.1.1.jar")
MOD_SRC = Path("/home/sagemaker-user/MineOcclude/fabric/mineocclude-mod/src/main/java"
               "/com/mineocclude/server/MineOccludeServer.java")


def main() -> int:
    authority = json.loads((OUT / "p2_path_equivalence_authority.json").read_text())
    spec_ids = [u["trajectory_spec_id"] for u in authority["units"]]
    specs = {str(s["trajectory_spec_id"]): s for s in source_specs()}
    POST.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    with CaptureSession("normal") as session:
        for spec_id in spec_ids:
            destination = POST / spec_id
            if destination.exists():
                shutil.rmtree(destination)
            session.capture(specs[spec_id],
                            REPLAY_EPISODE_BASE + int(spec_id.rsplit("t", 1)[1]),
                            destination)
    replay_seconds = time.monotonic() - started

    units: list[dict[str, Any]] = []
    frame_rows: list[dict[str, Any]] = []
    for spec_id in spec_ids:
        pre_state = read_jsonl(PRE / spec_id / "raw/server_state.jsonl")
        post_state = read_jsonl(POST / spec_id / "raw/server_state.jsonl")
        a = np.asarray([float(r["sheep_x"]) for r in pre_state], dtype=np.float64)
        b = np.asarray([float(r["sheep_x"]) for r in post_state], dtype=np.float64)
        if len(a) != len(b):
            raise RuntimeError(f"{spec_id}: frame count changed {len(a)} -> {len(b)}")

        selection = select_frames(spec_id)
        px_identical = flips = area_changes = 0
        diffs = []
        for item in selection:
            f = item["model_frame_idx"]
            pp = PRE / spec_id / "raw/frames" / f"{f:06d}.png"
            qp = POST / spec_id / "raw/frames" / f"{f:06d}.png"
            x = np.asarray(Image.open(pp).convert("RGB"), dtype=np.int16)
            y = np.asarray(Image.open(qp).convert("RGB"), dtype=np.int16)
            d = np.abs(x - y)
            same = bool(d.max() == 0)
            px_identical += same
            ps, pa = detector(pp)
            qs, qa = detector(qp)
            flips += ps != qs
            area_changes += pa != qa
            if not same:
                diffs.append({"model_frame_idx": f,
                              "n_differing_pixels": int((d.sum(axis=2) > 0).sum()),
                              "max_abs_channel_difference": int(d.max())})
            frame_rows.append({
                "trajectory_spec_id": spec_id, "model_frame_idx": f,
                "visibility_class": item["visibility_class"],
                "decoded_pixels_identical": same,
                "detector_pre": {"status": ps, "area_pixels": pa},
                "detector_post": {"status": qs, "area_pixels": qa},
            })

        units.append({
            "trajectory_spec_id": spec_id,
            "direction": specs[spec_id]["direction"],
            "frames": int(len(a)),
            "coords_max_abs_diff_pre_vs_post": float(np.abs(a - b).max()),
            "coords_bitwise_identical": bool((a == b).all()),
            "coord_frames_identical": int((a == b).sum()),
            "scene_set": sorted({r.get("scene") for r in post_state}),
            "tick_ordering_ok": all(int(r["server_tick"]) == i
                                    for i, r in enumerate(post_state)),
            "spec_identity_ok": all(r.get("trajectory_spec_id") == spec_id
                                    and r.get("seed") == specs[spec_id]["seed"]
                                    for r in post_state),
            "frames_compared_for_pixels": len(selection),
            "frames_pixel_identical": px_identical,
            "pixel_diff_frames": diffs,
            "detector_status_flips": int(flips),
            "detector_area_changes": int(area_changes),
        })

    coords_ok = all(u["coords_bitwise_identical"] for u in units)
    pixels_ok = all(u["frames_pixel_identical"] == u["frames_compared_for_pixels"]
                    for u in units)
    detector_ok = all(u["detector_status_flips"] == 0 and u["detector_area_changes"] == 0
                      for u in units)
    semantics_ok = all(u["tick_ordering_ok"] and u["spec_identity_ok"]
                       and u["scene_set"] == ["NORMAL"] for u in units)
    passed = coords_ok and pixels_ok and detector_ok and semantics_ok

    payload = {
        "artifact_id": "regime-a-prime-p2-patch-inertness-receipt-v0.1",
        "schema_version": "1.0",
        "phase": "P2",
        "gate": "STEP5_PATCH_INERTNESS_CURRENT_APPARATUS",
        "status": "PASS" if passed else "FAIL",
        "PATCH_INERTNESS_STATUS": "PASS" if passed else "FAIL",
        "PATCH_CURRENT_PATH_EQUIVALENCE": "PASS" if coords_ok else "FAIL",
        "PATCH_CURRENT_PIXEL_EQUIVALENCE": "PASS" if (pixels_ok and detector_ok) else "FAIL",
        "comparison": "PRE-PATCH current runtime vs POST-PATCH current runtime; the "
                      "renderer is held constant, so any difference is attributable to "
                      "the server-mod patch alone",
        "distinct_from_historical_gate":
            "HISTORICAL_PIXEL_EQUIVALENCE=FAIL (cross-apparatus, unrecoverable renderer) "
            "is a separate, permanently recorded finding; it limits cross-apparatus "
            "historical causal interpretation and is NOT what this gate measures",
        "equivalence_rule": "EXACT: coordinates bit-identical, decoded pixels identical, "
                            "no detector status flip, no detector area change",
        "tolerance_invented": False,
        "scene_tested": "NORMAL",
        "no_sheep_still_refused": True,
        "units": units,
        "aggregate": {
            "coords_bitwise_identical_all": coords_ok,
            "max_coord_difference": max(u["coords_max_abs_diff_pre_vs_post"] for u in units),
            "frames_compared_for_pixels": sum(u["frames_compared_for_pixels"] for u in units),
            "frames_pixel_identical": sum(u["frames_pixel_identical"] for u in units),
            "detector_status_flips": sum(u["detector_status_flips"] for u in units),
            "detector_area_changes": sum(u["detector_area_changes"] for u in units),
        },
        "frame_comparisons": frame_rows,
        "apparatus": {
            "post_patch_source_sha256": sha256_file(MOD_SRC),
            "post_patch_mod_sha256": sha256_file(MOD_JAR),
            "java": "Amazon Corretto 17.0.20.8.1 (build 17.0.20+8-LTS)",
        },
        "replay_wall_clock_seconds": replay_seconds,
        "wall_trajectories_recollected_for_science": 0,
        "nonscientific": True,
    }
    digest = write_json(OUT / "p2_patch_inertness_receipt.json", payload)
    print(f"PATCH_INERTNESS_STATUS={payload['PATCH_INERTNESS_STATUS']}")
    print(f"PATCH_CURRENT_PATH_EQUIVALENCE={payload['PATCH_CURRENT_PATH_EQUIVALENCE']}")
    print(f"PATCH_CURRENT_PIXEL_EQUIVALENCE={payload['PATCH_CURRENT_PIXEL_EQUIVALENCE']}")
    for u in units:
        print(f"  {u['trajectory_spec_id']} {u['direction']}: coords "
              f"{u['coord_frames_identical']}/{u['frames']} exact, pixels "
              f"{u['frames_pixel_identical']}/{u['frames_compared_for_pixels']} exact, "
              f"flips={u['detector_status_flips']} areaDelta={u['detector_area_changes']}")
    print(f"RECEIPT_SHA256={digest}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
