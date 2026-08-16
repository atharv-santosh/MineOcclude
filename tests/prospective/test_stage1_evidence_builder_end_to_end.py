"""End-to-end regression for the real Stage-1 evidence builder (D-A4).

The unit suite in ``test_development_authority_v0_2_repair`` hand-builds an
evidence document, so it can only prove that :class:`Stage1Evaluator` accepts a
well-formed document. It cannot prove that the artefact the *builder* actually
writes is one the evaluator accepts, and it cannot prove that the temporal
fields were measured rather than asserted. That gap is exactly how
``build_stage1_evidence.py`` came to call ``estimate_alignment`` with no
authority requirements at all: the estimator returned
``MEASURED_NOT_ADJUDICATED``, applied no pure-delay refusal, and nothing in the
suite noticed.

So this module drives the real path:

    synthetic raw capture -> scripts/.../build_stage1_evidence.py main()
    -> real evidence document -> Stage1Evaluator -> PASS

Nothing here writes ``kernel``, ``kernel_is_pure_delay``, ``estimate_ticks``,
``confidence_interval_ticks`` or any other temporal PASS field. Those are
reconstructed by the builder from the rendered frames, and the test asserts the
reconstruction recovers the smoothing kernel the synthetic renderer actually
used. The negative case renders a bare integer-tick delay instead and requires
the builder to refuse it.

Both cases render 1440 frames through the pure-Python detector, so this
module takes around 80 seconds.

Only one authority value is altered: the canonical frame is reduced from
640x360 so the deliberately dependency-light pure-Python HSV detector can scan
1440 frames inside a test. Every scientific policy -- temporal, visibility,
contamination, completeness -- is the frozen authority's own.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mineocclude.prospective.development_workflow import (
    RUNTIME_CRITICAL_SOURCE_PATHS, Stage1Evaluator, canonical_payload_sha256,
    kernel_group_delay_ticks, load_json, normalized_kernel, probe_evidence_digest,
    sha256_file,
)
from scripts.regime_a_prime_qualification_v0_2 import build_stage1_evidence
# The runtime receipt must now carry real probe-execution evidence (A4); the
# builder-facing capture is synthetic, but the runtime identity it declares is
# verified against this tree exactly as it will be at launch.
from tests.prospective.test_development_authority_v0_2_repair import probe_execution_record


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1"
                  "/prospective_development_authority_v0_2")

# Reduced canonical frame: detect_magenta is pure Python and scans every pixel
# of every frame, so the authority's own 640x360 costs ~0.6s per frame and ~15
# minutes per run. This is an exact 1/4-scale reduction of it, so the aspect
# ratio -- and with it the projection geometry the evaluator reasons about -- is
# the authority's own 16:9 rather than the distorted 10:1 strip used before.
# The full-fidelity 640x360 run is a separate required pre-freeze check; see
# ``docs/.../FULL_FIDELITY_E2E.md``.
#
# ``MINEOCCLUDE_FULL_FIDELITY_E2E=1`` selects the authority's native 640x360
# instead. That is the one-time freeze-boundary check documented in
# ``FULL_FIDELITY_E2E.md``; it costs ~12x more and is deliberately not run by
# the acceptance harness.
FRAME_PIXELS = ([640, 360] if os.environ.get("MINEOCCLUDE_FULL_FIDELITY_E2E") == "1"
                else [160, 90])
# Lane-to-screen margin, so world x = +-8 projects strictly inside [0, width).
SCREEN_MARGIN_PIXELS = 8
# Inside the frozen detector's inclusive [19, 5000] area range. The height also sets the
# sub-pixel centroid resolution of the rasterised silhouette: partial-coverage
# edge columns are drawn at proportional height, so a taller blob resolves the
# rendered position more finely, exactly as a real anti-aliased render does.
# Halving the width to 160 halves the pixels-per-block, so the blob is made
# correspondingly taller to keep the centroid resolution ahead of where it was.
# The original native fixture scaled the fast blob in both dimensions and
# accidentally produced 28*244=6832 pixels, so the real detector correctly
# rejected every frame at 640x360. Width is not a scientific parameter here;
# 15*244=3660 exercises the same native raster/centroid path, remains qualified,
# and fits inside the eight-pixel lane margin. The latter is essential for the
# pure-delay control: a clipped edge blob shifts its centroid nonlinearly and is
# no longer an exact delayed rendering even when its source state is exact.
BLOB_WIDTH_PIXELS, BLOB_HEIGHT_PIXELS = (15, 244) if FRAME_PIXELS[0] == 640 else (7, 61)
# The synthetic renderer's true state-to-render map: a causal two-tap average
# at lags 3 and 4, so the true group delay is exactly 3.5 ticks. This is what
# the builder must independently reconstruct.
RENDER_SMOOTHING = {3: 0.5, 4: 0.5}
TRUE_GROUP_DELAY_TICKS = 3.5
# The silhouette has extent, so the rendered target is fully hidden over a
# strictly narrower band than the server-side point. The 1.0-block margin keeps
# detector-absence nested inside point-hiddenness despite motion noise and the
# 0.35-block displacement the 3.5-tick render lag introduces; the generator
# asserts the nesting rather than assuming it.
POINT_HIDDEN_HALF_BLOCKS = 4.5
RENDER_HIDDEN_HALF_BLOCKS = 3.5
PURE_DELAY_TICKS = 3


def _signed_probe(**fields: object) -> dict:
    value = {"status": "PASS", "independently_derived": True,
             "asserted_by_evidence_builder": False, **fields}
    value["payload_sha256"] = canonical_payload_sha256(value)
    return value


def _screen_x(world_x: float, width: int) -> float:
    span = width - 2 * SCREEN_MARGIN_PIXELS
    return SCREEN_MARGIN_PIXELS + (world_x + 8.0) / 16.0 * span


def _world_x(screen_x: float, width: int) -> float:
    span = width - 2 * SCREEN_MARGIN_PIXELS
    return (screen_x - SCREEN_MARGIN_PIXELS) / span * 16.0 - 8.0


def _render_frame(width: int, height: int, centre_x: float, present: bool) -> np.ndarray:
    """Rasterise the magenta silhouette with proportional-coverage edges."""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[..., 1] = 90  # non-magenta background the frozen HSV ranges reject
    if not present:
        return image
    low, high = centre_x - BLOB_WIDTH_PIXELS / 2.0, centre_x + BLOB_WIDTH_PIXELS / 2.0
    top = height // 2 - BLOB_HEIGHT_PIXELS // 2
    for column in range(max(0, int(math.floor(low))), min(width, int(math.ceil(high)))):
        coverage = max(0.0, min(column + 1.0, high) - max(float(column), low))
        rows = int(round(BLOB_HEIGHT_PIXELS * coverage))
        if rows <= 0:
            continue
        offset = (BLOB_HEIGHT_PIXELS - rows) // 2
        image[top + offset:top + offset + rows, column] = (255, 0, 255)
    return image


def _synthetic_path(unit: dict, seconds_per_tick: float, lane: list[float]) -> list[float]:
    """The authority's own motion model: fixed drift plus frozen motion noise."""
    rng = np.random.default_rng(unit["noise_seed"])
    noise = rng.standard_normal(unit["expected_frames"]) * math.sqrt(
        unit["motion_noise_q"] * seconds_per_tick)
    step = unit["speed_blocks_per_second"] * seconds_per_tick * (
        1 if unit["direction"] == "LEFT_TO_RIGHT" else -1)
    position, values = unit["start_world_x"], []
    for draw in noise:
        position = min(lane[1], max(lane[0], position + step + float(draw)))
        values.append(position)
    return values


def _write_receipt(authority: dict, manifest: dict, unit: dict) -> None:
    policy = authority["apparatus_observation_policy"]
    apparatus = _signed_probe(
        camera_feet_world_xyz=policy["camera_feet_world_xyz"],
        camera_eye_world_xyz=policy["camera_eye_world_xyz"],
        yaw_pitch_degrees=policy["yaw_pitch_degrees"], fov_degrees=policy["fov_degrees"],
        canonical_frame_pixels=policy["canonical_frame_pixels"],
        target_entity_uuid="uuid-1", target_respawn_count=0, scene=unit["scene"],
        wall_layout_physical_evidence="PASS",
        layout_id=authority["apparatus"]["layout_id"],
        camera_authority=authority["apparatus"]["camera_authority"],
        wall_authority=authority["apparatus"]["wall_authority"])
    execution = probe_execution_record(authority)
    by_id = {item["command_id"]: item for item in execution["invocations"]}
    runtime = _signed_probe(
        **authority["runtime_identity_policy"]["required_fields"],
        critical_file_sha256=authority["runtime_identity_policy"]["critical_file_sha256"],
        java_version_probe_sha256=by_id["java_version"]["normalized_output_sha256"],
        renderer_probe_sha256=by_id["renderer"]["normalized_output_sha256"],
        xvfb_probe_sha256=by_id["xvfb"]["normalized_output_sha256"],
        runtime_source_sha256={relative: sha256_file(ROOT / relative)
                               for relative in RUNTIME_CRITICAL_SOURCE_PATHS},
        probe_execution=execution,
        probe_evidence_sha256=probe_evidence_digest(execution),
        captured_apparatus_receipt=apparatus)
    path_sha = hashlib.sha256(unit["unit_id"].encode()).hexdigest()
    path_state = _signed_probe(unit_id=unit["unit_id"], frame_count=unit["expected_frames"],
        exact_binary64_path_match=True, captured_path_sha256=path_sha,
        expected_path_sha256=path_sha)
    durability = _signed_probe(unit_id=unit["unit_id"],
        durable_uri=manifest["durable_prefix"].rstrip("/") + "/" + unit["unit_id"],
        remote_object_count=1, remote_checksum_manifest_sha256="d" * 64)
    receipt = Path(unit["receipt_path"])
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"unit_id": unit["unit_id"],
        "runtime_provenance_receipt": runtime, "path_state_receipt": path_state,
        "durability_receipt": durability}, sort_keys=True) + "\n")


def synthesize_capture(tmp_path: Path, *, pure_delay: bool) -> tuple[Path, Path]:
    """Write a complete synthetic Stage-1 raw capture and return its bindings.

    ``pure_delay`` renders each frame at the server position from exactly
    ``PURE_DELAY_TICKS`` ticks earlier, with the server state snapped to the
    pixel grid so the rasterised centroid is an exact affine function of the
    delayed position. The causal fit then has a zero-residual single-tap
    solution: the reconstructed kernel is a bare integer-tick delay, which the
    authority forbids.
    """
    authority = load_json(PACKAGE / "authority_parameters.json")
    detector_settings = load_json(
        ROOT / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1"
        / "detector_candidate_config.json")["configuration"]["detector_settings"]
    nominal_blob_area = BLOB_WIDTH_PIXELS * BLOB_HEIGHT_PIXELS
    assert detector_settings["min_area_pixels"] <= nominal_blob_area <= detector_settings[
        "max_area_pixels"], "synthetic visible blob must qualify under the frozen detector"
    assert BLOB_WIDTH_PIXELS / 2 < SCREEN_MARGIN_PIXELS, (
        "synthetic visible blob must not clip at either qualified lane endpoint")
    authority["apparatus"]["canonical_frame_pixels"] = FRAME_PIXELS
    authority["apparatus_observation_policy"]["canonical_frame_pixels"] = FRAME_PIXELS
    authority_path = tmp_path / "authority_parameters.json"
    authority_path.write_text(json.dumps(authority, indent=2, sort_keys=True) + "\n")

    manifest = load_json(PACKAGE / "stage1_manifest.json")
    manifest["authority_binding"]["sha256"] = sha256_file(authority_path)
    for unit in manifest["units"]:
        unit["receipt_path"] = str(tmp_path / "receipts" / f"{unit['unit_id']}.json")
        unit["command"] = ["python3", "--stage", "stage1-capture",
                           "--unit-id", unit["unit_id"]]
    manifest_path = tmp_path / "stage1_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    width, height = FRAME_PIXELS
    lane = authority["apparatus"]["lane_world_x_blocks"]
    seconds_per_tick = authority["apparatus"]["seconds_per_server_tick"]
    token_grid = authority["apparatus"]["visual_token_grid"]
    for unit in manifest["units"]:
        path = _synthetic_path(unit, seconds_per_tick, lane)
        if pure_delay:
            columns = [round(_screen_x(value, width)) for value in path]
            path = [_world_x(float(column), width) for column in columns]
        capture = tmp_path / "captures" / unit["unit_id"]
        (capture / "raw/frames").mkdir(parents=True, exist_ok=True)
        state, coordinates = [], []
        for index, world_x in enumerate(path):
            if pure_delay:
                source = max(0, index - PURE_DELAY_TICKS)
                render_column = float(columns[source])
                rendered_x = path[source]
            else:
                rendered_x = sum(weight * path[max(0, index - lag)]
                                 for lag, weight in RENDER_SMOOTHING.items())
                render_column = _screen_x(rendered_x, width)
            point_hidden = (unit["scene"] == "WALL"
                            and abs(world_x) <= POINT_HIDDEN_HALF_BLOCKS)
            render_hidden = (unit["scene"] == "WALL"
                             and abs(rendered_x) <= RENDER_HIDDEN_HALF_BLOCKS)
            assert not (render_hidden and not point_hidden), (
                "synthetic apparatus is inconsistent: the rendered silhouette is "
                "fully hidden while the server-side point is not")
            state.append({"server_tick": index, "sheep_x": world_x, "sheep_z": 6.0,
                          "geometric_visible": not point_hidden})
            screen_x, screen_y = _screen_x(world_x, width), height / 2.0
            coordinates.append({"model_frame_idx": index,
                "screen_x": screen_x, "screen_y": screen_y,
                "token_cell_row": math.floor(screen_y * token_grid[0] / height),
                "token_cell_col": math.floor(screen_x * token_grid[1] / width)})
            Image.fromarray(_render_frame(width, height, render_column,
                                          not render_hidden)).save(
                capture / "raw/frames" / f"{index:06d}.png")
        (capture / "raw/server_state.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in state))
        (capture / "coordinates.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in coordinates))
        _write_receipt(authority, manifest, unit)
    return authority_path, manifest_path


def run_builder(monkeypatch, authority_path: Path, manifest_path: Path,
                output: Path) -> None:
    """Invoke the real builder exactly as its command line does."""
    monkeypatch.setattr("sys.argv", ["build_stage1_evidence.py", str(manifest_path),
                                     str(authority_path), str(output)])
    build_stage1_evidence.main()


def test_real_builder_evidence_reaches_a_legitimate_stage1_pass(tmp_path, monkeypatch):
    authority_path, manifest_path = synthesize_capture(tmp_path, pure_delay=False)
    evidence_path = tmp_path / "stage1_evidence.json"
    run_builder(monkeypatch, authority_path, manifest_path, evidence_path)
    evidence = load_json(evidence_path)

    authority, manifest = load_json(authority_path), load_json(manifest_path)
    decision = Stage1Evaluator(authority, manifest,
        authority_sha256=sha256_file(authority_path),
        manifest_sha256=sha256_file(manifest_path)).evaluate(evidence)
    assert decision.status == "PASS", decision.reasons
    assert decision.reasons == ()

    # The temporal evidence is a measurement, not a supplied constant: the
    # reconstructed kernel must recover the renderer's actual smoothing taps,
    # and every kernel-derived flag must follow from it.
    expected = normalized_kernel([RENDER_SMOOTHING.get(lag, 0.0) for lag in range(
        authority["stage1_policy"]["temporal_alignment"]["maximum_lag_ticks_for_estimation"] + 1)])
    for direction, item in evidence["alignment_by_direction"].items():
        fir = next(method for method in item["methods"]
                   if method["method_id"] == "causal_fir_group_delay")
        assert fir["kernel_is_pure_delay"] is False
        assert fir["per_trajectory_beats_best_pure_delay"] is True
        assert fir["estimate_ticks"] == pytest.approx(TRUE_GROUP_DELAY_TICKS, abs=0.05), direction
        assert kernel_group_delay_ticks(fir["kernel"]) == pytest.approx(
            fir["estimate_ticks"], abs=1e-9)
        for observed, truth in zip(fir["kernel"], expected, strict=True):
            assert observed == pytest.approx(truth, abs=0.05), direction
        # The independent method is not a copy of the FIR fit.
        lag = next(method for method in item["methods"]
                   if method["method_id"] == "derivative_cross_correlation_lag")
        assert lag["per_trajectory_estimates_ticks"] != fir["per_trajectory_estimates_ticks"]
        assert lag["estimate_ticks"] == pytest.approx(TRUE_GROUP_DELAY_TICKS, abs=0.05)


def test_effectively_pure_delay_render_is_refused_by_the_real_builder(tmp_path, monkeypatch):
    """A bare integer-tick delay cannot reach an evidence document at all."""
    authority_path, manifest_path = synthesize_capture(tmp_path, pure_delay=True)
    evidence_path = tmp_path / "stage1_evidence.json"
    with pytest.raises(RuntimeError, match="FIR alignment unresolved") as failure:
        run_builder(monkeypatch, authority_path, manifest_path, evidence_path)
    assert "pure delay" in str(failure.value)
    assert not evidence_path.exists()
