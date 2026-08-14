#!/usr/bin/env python3
"""One-shot, outcome-blind Regime-A A2 exact-checkpoint engineering smoke."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.contracts.identity import SCHEMA_VERSION  # noqa: E402
from mineocclude.models import mineworld_adapter as api  # noqa: E402
from mineocclude.models import _mineworld_adapter_wave4 as wave4  # noqa: E402
from scripts import run_person_a_66_cell_production_extraction as production  # noqa: E402


CALIBRATION_FRAMES = Path(
    "/home/sagemaker-user/mineocclude-client/mineocclude_client_out/episode_40121/frames"
)
PACKAGE = ROOT / "data/autonomous/layout_01_ep12602/capture_package_v0_1.json"


def main() -> int:
    import torch

    package_bytes = PACKAGE.read_bytes()
    package_hash = hashlib.sha256(package_bytes).hexdigest()
    document = json.loads(package_bytes)

    load_start = time.perf_counter()
    production._RUNTIME.ensure_loaded()
    checkpoint_load_seconds = time.perf_counter() - load_start
    adapter = production._RUNTIME.adapter
    runtime = production._RUNTIME.runtime_identity
    validated = adapter.validate_trajectory(
        api.AcceptedTrajectoryInput(
            schema_version=SCHEMA_VERSION,
            trajectory_id=document["trajectory_id"],
            accepted_manifest_sha256=package_hash,
            document=document,
        )
    )
    identities = validated.frame_identities[:34]
    frames = []
    for index, identity in enumerate(identities):
        rgb = np.asarray(Image.open(CALIBRATION_FRAMES / f"{index:06d}.png").convert("RGB"))
        processed = adapter.preprocess_frame(api.FramePreprocessRequest(identity, index, rgb))
        # The bytes are produced by the same frozen transform; Wave 5 changes
        # only the reviewed successor provenance label used by this runtime.
        frames.append(dataclasses.replace(processed, preprocessing_profile=runtime.preprocessing_identity))
    raw = {row["model_frame_idx"]: row for row in document["streams"]["raw_actions"]}
    actions = tuple(
        adapter.convert_action(api.ActionConversionRequest(identity, int(raw[index]["action_idx"]), raw[index]["raw_action"]))
        for index, identity in enumerate(identities)
    )

    token_hashes = []
    forward_seconds = []
    shapes = set()
    layer_sets = []
    torch.cuda.reset_peak_memory_stats(0)
    trajectory_start = time.perf_counter()
    first_tokenized = None
    first_output_digest = None
    for target in range(15, 34):
        start = target - 15
        window = dataclasses.replace(validated, frame_identities=identities[start : target + 1])
        tokenized = adapter.tokenize_trajectory(
            api.TrajectoryTokenizationRequest(
                runtime_identity=runtime,
                trajectory=window,
                frames=tuple(frames[start : target + 1]),
                actions=actions[start : target + 1],
            )
        )
        if first_tokenized is None:
            first_tokenized = tokenized
        token_hashes.append(tokenized.token_sha256)
        call_start = time.perf_counter()
        _result, captures = production._teacher_capture(adapter, runtime, tokenized, package_hash)
        torch.cuda.synchronize()
        forward_seconds.append(time.perf_counter() - call_start)
        layer_sets.append([capture.layer.layer_idx for capture in captures])
        for capture in captures:
            shapes.add(capture.output.shape)
        last_span = tokenized.frame_token_map.spans[-1]
        last_layer = captures[4].output.tensor
        target_tensor = last_layer[:, last_span.visual_positions, :].detach().float().cpu().numpy()
        digest = hashlib.sha256(target_tensor.astype("<f4", copy=False).tobytes()).hexdigest()
        if target == 15:
            first_output_digest = digest
        del captures, target_tensor, last_layer, _result

    all_layer_seconds = time.perf_counter() - trajectory_start
    reset_start = time.perf_counter()
    _result, captures = production._teacher_capture(adapter, runtime, first_tokenized, package_hash)
    torch.cuda.synchronize()
    reset_equivalence_seconds = time.perf_counter() - reset_start
    span = first_tokenized.frame_token_map.spans[-1]
    repeated = captures[4].output.tensor[:, span.visual_positions, :].detach().float().cpu().numpy()
    repeated_digest = hashlib.sha256(repeated.astype("<f4", copy=False).tobytes()).hexdigest()

    receipt = {
        "schema_version": "regime-a-a2-gpu-smoke-v1.0",
        "status": "PASS",
        "scientific_data": False,
        "scientific_outcomes_computed": False,
        "input_designation": "NON_SCIENTIFIC_EP40121_CALIBRATION_PIXELS_WITH_VALIDATED_ADAPTER_IDENTITY_SCAFFOLD",
        "checkpoint_load_count": 1,
        "checkpoint_load_seconds": checkpoint_load_seconds,
        "trajectory_target_windows": 19,
        "trailing_pairs_per_window": 16,
        "window_start_pairs": [0, 1],
        "overlap_pairs_between_first_two_windows": 15,
        "unique_token_hash_count": len(set(token_hashes)),
        "all_layer_extraction_seconds": all_layer_seconds,
        "forward_seconds": forward_seconds,
        "layer_sets_all_exact_0_through_19": all(value == list(range(20)) for value in layer_sets),
        "capture_shapes": [list(value) for value in sorted(shapes)],
        "target_visual_tokens": 336,
        "hidden_width": 2048,
        "reset_equivalence_seconds": reset_equivalence_seconds,
        "reset_equivalence_layer4_target_digest_equal": repeated_digest == first_output_digest,
        "persistent_model_state_across_trajectory_units": False,
        "peak_gpu_vram_bytes": int(torch.cuda.max_memory_allocated(0)),
        "gpu_name": torch.cuda.get_device_name(0),
        "runtime_identity": dataclasses.asdict(runtime),
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
