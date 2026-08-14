"""D6 step C (EXPLORATORY): extract layer-4 activations at the frozen visible rows.

Reuses the EXACT validated production path that produced the confirmatory hidden
activations (adapter.validate_trajectory / preprocess_frame / convert_action /
tokenize_trajectory, then production._teacher_capture). The only change is that
target frame indices come from the frozen visible manifest instead of the
tau in 1..19 filter, so an equivalence test is run first.

EQUIVALENCE TEST
    Re-extracts one KNOWN hidden target (t01, tau=1, model frame 43) through this
    generalized path and compares it against the frozen, hash-verified
    layer_04.npy row 0. This is the smallest focused check that the generalized
    target selection did not perturb the extraction semantics.

Nothing here recomputes any hidden scientific outcome, and no confirmatory
artifact is written.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path("/home/sagemaker-user/MineOcclude")
# Mirrors scripts/run_person_a_66_cell_production_extraction.py: src/ must be
# importable for `mineocclude`, and the repo root for the `scripts` package.
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts/postmortem_v0_1"))

from pm_common import OUT, WORK, write_json  # noqa: E402

LAYER = 4
D6 = WORK / "d6"
ACT_OUT = WORK / "d6_activations"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_targets(adapter, runtime, api, production, traj: str, targets: list[int]):
    """Layer-4 visual tokens of each target frame, teacher-forced, 16-pair window."""
    from mineocclude.contracts.identity import SCHEMA_VERSION

    root = D6 / traj
    package_bytes = (root / "capture_package_v0_1.json").read_bytes()
    package_hash = hashlib.sha256(package_bytes).hexdigest()
    document = json.loads(package_bytes)
    validated = adapter.validate_trajectory(
        api.AcceptedTrajectoryInput(
            schema_version=SCHEMA_VERSION,
            trajectory_id=document["trajectory_id"],
            accepted_manifest_sha256=package_hash,
            document=document,
        )
    )
    identities = {i.model_frame_idx: i for i in validated.frame_identities}
    required = sorted({i for t in targets for i in range(t - 15, t + 1)})

    frames = {}
    for index in required:
        rgb = np.asarray(
            Image.open(root / f"frames/{index:06d}.png").convert("RGB")
        )
        processed = adapter.preprocess_frame(
            api.FramePreprocessRequest(identities[index], index, rgb)
        )
        frames[index] = dataclasses.replace(
            processed, preprocessing_profile=runtime.preprocessing_identity
        )
    raw_actions = {r["model_frame_idx"]: r for r in document["streams"]["raw_actions"]}
    actions = {
        index: adapter.convert_action(
            api.ActionConversionRequest(
                identities[index],
                int(raw_actions[index]["action_idx"]),
                raw_actions[index]["raw_action"],
            )
        )
        for index in required
    }

    out = np.empty((len(targets), 336, 2048), dtype=np.float16)
    for position, target in enumerate(targets):
        indices = list(range(target - 15, target + 1))
        window = dataclasses.replace(
            validated, frame_identities=tuple(identities[i] for i in indices)
        )
        tokenized = adapter.tokenize_trajectory(
            api.TrajectoryTokenizationRequest(
                runtime_identity=runtime,
                trajectory=window,
                frames=tuple(frames[i] for i in indices),
                actions=tuple(actions[i] for i in indices),
            )
        )
        _result, captures = production._teacher_capture(
            adapter, runtime, tokenized, package_hash
        )
        span = tokenized.frame_token_map.spans[-1]
        for capture in captures:
            if int(capture.layer.layer_idx) != LAYER:
                continue
            tensor = capture.output.tensor[:, span.visual_positions, :]
            out[position] = tensor[0].detach().cpu().numpy().astype(np.float16, copy=False)
        del captures, _result
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--equivalence-only", action="store_true")
    args = parser.parse_args()

    from mineocclude.models import mineworld_adapter as api
    from scripts import run_person_a_66_cell_production_extraction as production

    production._RUNTIME.ensure_loaded()
    adapter = production._RUNTIME.adapter
    runtime = production._RUNTIME.runtime_identity
    print("checkpoint runtime loaded", flush=True)

    # ---------- equivalence test against a frozen hidden activation ----------
    frozen = np.load(WORK / "act4/regime_a_v2_t01.layer_04.npy", mmap_mode="r")
    reference = np.asarray(frozen[0], dtype=np.float16)  # tau=1 -> model frame 43
    replay = extract_targets(adapter, runtime, api, production, "regime_a_v2_t01", [43])[0]

    identical = bool(np.array_equal(replay, reference))
    finite = np.isfinite(replay.astype(np.float32)) & np.isfinite(
        reference.astype(np.float32)
    )
    diff = np.abs(replay.astype(np.float64) - reference.astype(np.float64))
    equivalence = {
        "trajectory_id": "regime_a_v2_t01",
        "tau": 1,
        "model_frame_idx": 43,
        "layer": LAYER,
        "bitwise_identical": identical,
        "max_abs_diff": float(diff.max()),
        "mean_abs_diff": float(diff.mean()),
        "reference_abs_mean": float(np.abs(reference.astype(np.float64)).mean()),
        "all_finite": bool(finite.all()),
        "shape_match": bool(replay.shape == reference.shape),
    }
    print("=== D6 equivalence test ===")
    print(json.dumps(equivalence, indent=2), flush=True)
    write_json(OUT / "d6_equivalence_receipt.json", {
        "artifact_id": "regime-a-postmortem-d6-extraction-equivalence-v0.1",
        "status": "EXPLORATORY",
        "purpose": (
            "Confirms the generalized arbitrary-target extraction path reproduces a "
            "known frozen hidden activation before any visible activation is inspected."
        ),
        "result": equivalence,
    })
    if not identical:
        print("EQUIVALENCE FAILED - not proceeding to visible extraction")
        return 1
    if args.equivalence_only:
        return 0

    # ---------- frozen visible rows ----------
    manifest = json.loads((OUT / "visible_positive_control_manifest.json").read_text())
    by_traj: dict[str, list[int]] = {}
    for row in manifest["rows"]:
        by_traj.setdefault(row["trajectory_id"], []).append(int(row["model_frame_idx"]))

    ACT_OUT.mkdir(parents=True, exist_ok=True)
    inventory = []
    for traj in sorted(by_traj):
        targets = sorted(by_traj[traj])
        path = ACT_OUT / f"{traj}.visible.layer_04.npy"
        if not path.exists():
            array = extract_targets(adapter, runtime, api, production, traj, targets)
            np.save(path, array)
        inventory.append(
            {
                "trajectory_id": traj,
                "label": "EXPLORATORY_VISIBLE_POSITIVE_CONTROL",
                "layer": LAYER,
                "path": str(path),
                "target_model_frame_indices": targets,
                "shape": [len(targets), 336, 2048],
                "dtype": "float16",
                "byte_size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
        print(f"  extracted {traj} ({len(targets)} rows)", flush=True)

    write_json(OUT / "d6_visible_activation_inventory.json", {
        "artifact_id": "regime-a-postmortem-d6-visible-activation-inventory-v0.1",
        "status": "EXPLORATORY_VISIBLE_POSITIVE_CONTROL",
        "layer": LAYER,
        "checkpoint_sha256": production.wave2.PINNED_MAIN_CHECKPOINT_SHA256,
        "manifest_sha256": hashlib.sha256(
            (OUT / "visible_positive_control_manifest.json").read_bytes()
        ).hexdigest(),
        "equivalence": equivalence,
        "artifacts": inventory,
    })
    print("visible extraction complete:", len(inventory), "trajectories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
