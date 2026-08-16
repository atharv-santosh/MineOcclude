from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from mineocclude.prospective.development_workflow import (
    RUNTIME_CRITICAL_SOURCE_PATHS, DurableController, EvidenceError, Stage1Evaluator,
    canonical_payload_sha256,
    causal_fir_targets, derive_projection_validity, load_json, probe_evidence_digest,
    require_stage2_authorization, require_stage_manifest_binding,
    runtime_probe_identity_tokens, sha256_file,
    mean_student_t_interval, validate_stage2_manifest_design, verify_probe_execution,
    verify_receipt_payload_digest, verify_runtime_identity,
    verify_remote_durable_objects, verify_runtime_source_hashes,
)
from scripts.regime_a_prime_qualification_v0_2.stage2_backend import (
    best_k_qualification_checks, bound_capture_artifact, require_backend_authorization,
    require_durable_unit_receipt,
    validate_physical_gate_receipts, verify_local_capture_inventory,
)
from scripts.regime_a_prime_qualification_v0_2.stage_unit_driver import require_capture_authorization


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1/prospective_development_authority_v0_2"
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"
STAGE1_PATH = PACKAGE / "stage1_manifest.json"
STAGE2_PATH = PACKAGE / "stage2_locked_manifest.json"


@pytest.fixture
def authority():
    return load_json(AUTHORITY_PATH)


@pytest.fixture
def stage1():
    return load_json(STAGE1_PATH)


def signed_probe(**fields) -> dict:
    value = {"status": "PASS", "independently_derived": True,
             "asserted_by_evidence_builder": False, **fields}
    value["payload_sha256"] = canonical_payload_sha256(value)
    return value


def probe_execution_record(authority: dict) -> dict:
    """A structurally genuine probe-execution record for the current tree.

    The verifier rehashes the probe source, each probed executable, and each
    pinned apparatus artefact from disk, so this cannot be a bag of literals: it
    is assembled from files that really exist and from output text that really
    carries the authority's identity tokens. The JDK is the authority's pinned
    Corretto, invoked by absolute path. The renderer and Xvfb probes are
    recorded against a real executable without requiring a live X server, since
    what is under test here is the verification path rather than the display.
    """
    policy = authority["runtime_identity_policy"]
    reconstruction = policy["runtime_reconstruction"]
    java = Path(reconstruction["java_home"]) / reconstruction["java_executable_relative_path"]
    if not java.is_file():
        pytest.skip(f"qualified JDK is absent from its pinned location: {java}")
    tokens = runtime_probe_identity_tokens(policy["required_fields"])
    executables = {"java_version": str(java), "renderer": sys.executable,
                   "xvfb": sys.executable}
    invocations = []
    for command_id, required in tokens.items():
        output = "\n".join(required) + "\n"
        invocations.append({"command_id": command_id,
            "argv": [executables[command_id], f"--{command_id}"],
            "executable_path": executables[command_id],
            "executable_sha256": sha256_file(Path(executables[command_id])),
            "working_directory": str(ROOT), "exit_status": 0,
            "normalized_output": output,
            "normalized_output_sha256": hashlib.sha256(output.encode()).hexdigest()})
    fields = policy["required_fields"]
    return {"producer": policy["probe_evidence_policy"]["independent_probe_producers"][0],
            "probe_source_path": "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py",
            "probe_source_sha256": sha256_file(
                ROOT / "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py"),
            "java_home": reconstruction["java_home"], "display": reconstruction["display"],
            "invocations": invocations, "measurements": dict(fields),
            "apparatus_file_sha256": dict(policy["critical_file_sha256"]),
            "runtime_source_sha256": {path: sha256_file(ROOT / path)
                                      for path in RUNTIME_CRITICAL_SOURCE_PATHS}}


def valid_unit_probes(authority: dict, manifest: dict, unit: dict) -> tuple[dict, dict, dict]:
    apparatus_policy = authority["apparatus_observation_policy"]
    apparatus = signed_probe(camera_feet_world_xyz=apparatus_policy["camera_feet_world_xyz"],
        camera_eye_world_xyz=apparatus_policy["camera_eye_world_xyz"],
        yaw_pitch_degrees=apparatus_policy["yaw_pitch_degrees"], fov_degrees=apparatus_policy["fov_degrees"],
        canonical_frame_pixels=apparatus_policy["canonical_frame_pixels"], target_entity_uuid="uuid-1",
        target_respawn_count=0, scene=unit["scene"], wall_layout_physical_evidence="PASS")
    apparatus_without_hash = {key: value for key, value in apparatus.items() if key != "payload_sha256"}
    apparatus = signed_probe(**apparatus_without_hash, layout_id=authority["apparatus"]["layout_id"],
        camera_authority=authority["apparatus"]["camera_authority"],
        wall_authority=authority["apparatus"]["wall_authority"])
    runtime_fields = authority["runtime_identity_policy"]["required_fields"]
    execution = probe_execution_record(authority)
    by_id = {item["command_id"]: item for item in execution["invocations"]}
    runtime = signed_probe(**runtime_fields,
        critical_file_sha256=authority["runtime_identity_policy"]["critical_file_sha256"],
        java_version_probe_sha256=by_id["java_version"]["normalized_output_sha256"],
        renderer_probe_sha256=by_id["renderer"]["normalized_output_sha256"],
        xvfb_probe_sha256=by_id["xvfb"]["normalized_output_sha256"],
        runtime_source_sha256={path: sha256_file(ROOT / path)
                               for path in RUNTIME_CRITICAL_SOURCE_PATHS},
        probe_execution=execution,
        probe_evidence_sha256=probe_evidence_digest(execution),
        captured_apparatus_receipt=apparatus)
    path_hash = (unit["unit_id"].encode().hex() + "0" * 64)[:64]
    path = signed_probe(unit_id=unit["unit_id"], frame_count=unit["expected_frames"],
        exact_binary64_path_match=True, captured_path_sha256=path_hash, expected_path_sha256=path_hash)
    durability = signed_probe(unit_id=unit["unit_id"],
        durable_uri=manifest["durable_prefix"].rstrip("/") + "/" + unit["unit_id"],
        remote_object_count=1, remote_checksum_manifest_sha256="d" * 64)
    return runtime, path, durability


def valid_evidence(authority: dict, manifest: dict) -> dict:
    # The causal FIR warmup prefix is authority-derived, never a chosen budget:
    # a model frame earlier than maximum_lag_ticks_for_estimation has no
    # complete causal state history, so its clock cannot be resolved.
    warmup = authority["stage1_policy"]["temporal_alignment"]["maximum_lag_ticks_for_estimation"]
    transitions = {}
    for direction in authority["stage1_policy"]["directions"]:
        measurement = next(unit for unit in manifest["units"] if unit["direction"] == direction
                           and unit["scene"] == "WALL" and unit["design_role"] == "TRANSITION_MEASUREMENT")
        grid = [-8.0 + 16.0 * index / 179 for index in range(180)]
        geometric = [x for x in grid if -4.0 <= x <= 4.0]
        rendered = [x for x in grid if -3.0 <= x <= 3.0]
        geometric_interval = [min(geometric), max(geometric)]
        rendered_interval = [min(rendered), max(rendered)]
        transitions[direction] = {"status": "MEASURED", "measurement_unit_ids": [measurement["unit_id"]],
            "stable_occluded_world_x_interval": rendered_interval,
            "partial_transition_world_x_intervals": [[geometric_interval[0], rendered_interval[0]],
                                                       [rendered_interval[1], geometric_interval[1]]],
            "stable_visible_world_x_intervals": [[-8.0, geometric_interval[0]],
                                                   [geometric_interval[1], 8.0]],
            "geometric_point_hidden_world_x_interval": geometric_interval,
            "rendered_detector_absent_world_x_interval": rendered_interval}
    runs = []
    prohibited = {name: 0 for name in Stage1Evaluator.PROHIBITED}
    for unit in manifest["units"]:
        runtime_probe, path_probe, durability_probe = valid_unit_probes(authority, manifest, unit)
        xs = [-8.0 + 16.0 * index / 179 for index in range(180)]
        if unit["direction"] == "RIGHT_TO_LEFT":
            xs.reverse()
        samples = []
        for index, x in enumerate(xs):
            transition = transitions[unit["direction"]]
            point_low, point_high = transition["geometric_point_hidden_world_x_interval"]
            hidden_low, hidden_high = transition["stable_occluded_world_x_interval"]
            point = unit["scene"] == "NO_WALL" or not (point_low <= x <= point_high)
            # Rows before a complete causal FIR history have no resolved clock,
            # so they carry no physical regime. This is the exact warmup prefix
            # the authority permits, not a discretionary allowance.
            aligned = index >= warmup
            if not aligned: regime = "unresolved"
            elif unit["scene"] == "NO_WALL": regime = "stable_visible"
            elif hidden_low <= x <= hidden_high: regime = "stable_occluded"
            elif any(low <= x <= high for low, high in transition["partial_transition_world_x_intervals"]):
                regime = "partial_transition"
            elif point: regime = "stable_visible"
            else: regime = "unresolved"
            samples.append({"world_x": x, "wall_relative_x": x - 0.5,
                "screen_x": 320.0, "screen_y": 180.0, "token_row": 7, "token_col": 12,
                "projection_frame_pixels": authority["apparatus"]["canonical_frame_pixels"],
                "projection_token_grid": authority["apparatus"]["visual_token_grid"],
                "point_visible": point, "detector_visible": regime != "stable_occluded",
                "render_frame_present": True, "projected_in_frame": True,
                "temporal_alignment_resolved": aligned, "identity_valid": True,
                "in_support": True, "runtime_provenance_resolved": True,
                "path_state_valid": True, "malformed_or_missing": False, "regime": regime})
        required = 19 if unit["scene"] == "WALL" and unit["design_role"] == "HELD_OUT_VALIDATION" else 0
        designated = ([index for index, sample in enumerate(samples)
                       if sample["regime"] == "stable_occluded"][:required])
        runs.append({"unit_id": unit["unit_id"], "direction": unit["direction"], "scene": unit["scene"],
            "speed_blocks_per_second": unit["speed_blocks_per_second"], "frame_count": 180,
            "unit_receipt_sha256": (unit["unit_id"].encode().hex() + "0" * 64)[:64],
            "runtime_provenance_receipt": runtime_probe, "path_state_receipt": path_probe,
            "durability_receipt": durability_probe,
            "designated_hidden_row_indices": designated,
            "hidden_row_contamination": {"designated_hidden_row_count": required,
                                          "prohibited_counts": deepcopy(prohibited)},
            "visibility_samples": samples})
    alignments = {}
    for direction in authority["stage1_policy"]["directions"]:
        ids = [unit["unit_id"] for unit in manifest["units"] if unit["direction"] == direction]
        receipt_hashes = {run["unit_id"]: run["unit_receipt_sha256"]
                          for run in runs if run["direction"] == direction}
        fir_values = [3.2, 3.2, 3.4, 3.4]
        fir_mean, fir_interval = mean_student_t_interval(fir_values, 0.95)
        fir_kernels = []
        for value in fir_values:
            kernel = [0.0] * 9
            kernel[3], kernel[4] = 4.0 - value, value - 3.0
            fir_kernels.append(kernel)
        aggregate_kernel = [sum(values) / len(values) for values in zip(*fir_kernels, strict=True)]
        # Half-integer lags are ordinary parabolic-interpolation output. These
        # must genuinely satisfy the authority's agreement rule, which is
        # mutual estimate containment inside the admissible causal lag range,
        # not bare interval overlap.
        cc_values = [3.0, 3.0, 3.5, 3.5]
        cc_mean, cc_interval = mean_student_t_interval(cc_values, 0.95)
        # The unit-spacing flag is not assertable: the evaluator rederives it
        # from these raw tick/frame identities, so the flag cannot be mutated
        # without also forging the coordinates underneath it.
        cadence = authority["apparatus"]["server_ticks_per_model_frame"]
        clock_evidence = {}
        for run in runs:
            if run["direction"] != direction:
                continue
            count = len(run["visibility_samples"])
            clock_evidence[run["unit_id"]] = {
                "server_state_ticks": [cadence * frame for frame in range(count)],
                "render_model_frame_indices": list(range(count))}
        alignments[direction] = {"unit_spaced_clock_coordinates": True,
            "clock_coordinate_evidence": clock_evidence,
            "agreement_rule": authority["stage1_policy"]["temporal_alignment"]["agreement_rule"],
            "methods": [
            {"method_id": "causal_fir_group_delay", "status": "MEASURED", "estimate_ticks": fir_mean,
             "confidence_interval_ticks": fir_interval, "trajectory_count": 4,
             "trajectory_evidence_ids": ids, "kernel": aggregate_kernel,
             "per_trajectory_estimates_ticks": fir_values, "trajectory_receipt_sha256": receipt_hashes,
             "per_trajectory_kernels": fir_kernels,
             "per_trajectory_fir_vs_pure_delay_relative_improvement": [0.1] * 4,
             "kernel_is_pure_delay": False, "causal_fir_beats_best_pure_delay": True,
             "per_trajectory_beats_best_pure_delay": True},
            {"method_id": "derivative_cross_correlation_lag", "status": "MEASURED",
             "estimate_ticks": cc_mean, "confidence_interval_ticks": cc_interval,
             "trajectory_count": 4, "trajectory_evidence_ids": ids,
             "per_trajectory_estimates_ticks": cc_values, "trajectory_receipt_sha256": receipt_hashes}]}
    return {"schema_version": "1.1", "authority_sha256": manifest["authority_binding"]["sha256"],
            "stage1_manifest_sha256": sha256_file(STAGE1_PATH),
            "runs": runs, "transition_measurement_by_direction": transitions,
            "alignment_by_direction": alignments}


def assert_gate_fails(authority, stage1, evidence, gate):
    decision = evaluator(authority, stage1).evaluate(evidence)
    assert decision.status == "FAIL"
    assert decision.gates[gate]["status"] == "FAIL"


def evaluator(authority, stage1):
    return Stage1Evaluator(authority, stage1, authority_sha256=sha256_file(AUTHORITY_PATH),
                           manifest_sha256=sha256_file(STAGE1_PATH))


def test_repaired_stage1_fixture_passes(authority, stage1):
    decision = evaluator(authority, stage1).evaluate(valid_evidence(authority, stage1))
    assert decision.status == "PASS"
    payload = decision.to_dict(authority_sha256="a" * 64, manifest_sha256="b" * 64,
                               evidence_sha256="e" * 64)
    Draft202012Validator(load_json(ROOT / "schemas/prospective/regime_a_prime_stage1_decision_v0_2.schema.json")).validate(payload)


@pytest.mark.parametrize("changes", [
    {"screen_x": -1.0}, {"screen_y": -1.0}, {"screen_x": 640.0},
    {"screen_y": 360.0}, {"screen_x": 641.0, "screen_y": 361.0},
    {"token_row": -1}, {"token_col": -1}, {"token_row": 14}, {"token_col": 24},
    {"screen_x": 100.0, "screen_y": 100.0, "token_row": 7, "token_col": 12},
    {"screen_x": float("nan")}, {"screen_y": float("inf")},
])
def test_invalid_projection_cannot_override_raw_evidence(authority, stage1, changes):
    evidence = valid_evidence(authority, stage1)
    run = next(row for row in evidence["runs"] if row["scene"] == "NO_WALL")
    run["visibility_samples"][0].update(changes)
    assert evaluator(authority, stage1).evaluate(evidence).status == "FAIL"


def test_valid_last_in_frame_pixel_and_token_cell_pass(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    for run in evidence["runs"]:
        run["visibility_samples"][0].update(
            screen_x=639.0, screen_y=359.0, token_row=13, token_col=23)
    assert evaluator(authority, stage1).evaluate(evidence).status == "PASS"


@pytest.mark.parametrize("field,value", [
    ("projected_in_frame", False),
    ("projection_frame_pixels", [641, 360]),
    ("projection_token_grid", [15, 24]),
    ("projection_frame_pixels", None),
    ("projection_token_grid", None),
])
def test_projection_summary_or_dimensions_cannot_override_bound_raw_evidence(
        authority, stage1, field, value):
    evidence = valid_evidence(authority, stage1)
    evidence["runs"][0]["visibility_samples"][0][field] = value
    assert evaluator(authority, stage1).evaluate(evidence).status == "FAIL"


def test_projection_helper_uses_half_open_bounds_and_mutual_token_mapping(authority):
    frame = authority["apparatus"]["canonical_frame_pixels"]
    grid = authority["apparatus"]["visual_token_grid"]
    assert derive_projection_validity(
        {"screen_x": 639.0, "screen_y": 359.0, "token_row": 13, "token_col": 23},
        frame_pixels=frame, token_grid=grid)
    assert not derive_projection_validity(
        {"screen_x": 639.0, "screen_y": 359.0, "token_row": 12, "token_col": 23},
        frame_pixels=frame, token_grid=grid)


def test_contradictory_temporal_methods_fail(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    method = evidence["alignment_by_direction"]["LEFT_TO_RIGHT"]["methods"][1]
    method.update(estimate_ticks=6.5, confidence_interval_ticks=[6.0, 7.0])
    assert_gate_fails(authority, stage1, evidence, "render_server_temporal_alignment")


def test_temporal_n_coverage_mismatch_fails(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    method = evidence["alignment_by_direction"]["LEFT_TO_RIGHT"]["methods"][0]
    method["trajectory_count"] = 3; method["trajectory_evidence_ids"] = method["trajectory_evidence_ids"][:3]
    assert_gate_fails(authority, stage1, evidence, "render_server_temporal_alignment")


def test_temporal_identity_coverage_mismatch_fails(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    method = evidence["alignment_by_direction"]["LEFT_TO_RIGHT"]["methods"][1]
    method["trajectory_evidence_ids"][-1] = "copied_from_other_direction"
    assert_gate_fails(authority, stage1, evidence, "render_server_temporal_alignment")


def test_fake_independent_method_count_cannot_replace_method(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    item = evidence["alignment_by_direction"]["LEFT_TO_RIGHT"]
    item["methods"] = item["methods"][:1]; item["independent_method_count"] = 99
    assert_gate_fails(authority, stage1, evidence, "render_server_temporal_alignment")


def test_stale_temporal_summary_cannot_hide_contradictory_estimates(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    method = evidence["alignment_by_direction"]["LEFT_TO_RIGHT"]["methods"][1]
    method["per_trajectory_estimates_ticks"] = [6.0, 6.0, 7.0, 7.0]
    assert_gate_fails(authority, stage1, evidence, "render_server_temporal_alignment")


def test_temporal_source_receipt_binding_mismatch_fails(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    method = evidence["alignment_by_direction"]["LEFT_TO_RIGHT"]["methods"][0]
    method["trajectory_receipt_sha256"][method["trajectory_evidence_ids"][0]] = "f" * 64
    assert_gate_fails(authority, stage1, evidence, "render_server_temporal_alignment")


def test_stale_aggregate_fir_kernel_fails(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    method = evidence["alignment_by_direction"]["LEFT_TO_RIGHT"]["methods"][0]
    method["kernel"][0] = 0.1
    assert_gate_fails(authority, stage1, evidence, "render_server_temporal_alignment")


def test_no_wall_scene_identity_alone_is_not_visibility(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    run = next(row for row in evidence["runs"] if row["scene"] == "NO_WALL")
    # Probe a row with a resolved clock: an unresolved warmup row carries no
    # regime at all, so it cannot demonstrate that scene identity is refused
    # as a substitute for measured point visibility.
    sample = next(row for row in run["visibility_samples"] if row["temporal_alignment_resolved"])
    sample["point_visible"] = False
    assert_gate_fails(authority, stage1, evidence, "calibration_world_and_wall_relative_support")


def test_measured_transition_guard_is_actually_applied(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    evidence["transition_measurement_by_direction"]["LEFT_TO_RIGHT"]["stable_occluded_world_x_interval"] = [-1.0, 1.0]
    assert_gate_fails(authority, stage1, evidence, "calibration_world_and_wall_relative_support")


def test_missing_wall_relative_calibration_fails_closed(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    evidence["runs"][0]["visibility_samples"][0].pop("wall_relative_x")
    assert evaluator(authority, stage1).evaluate(evidence).status == "FAIL"


def test_incomplete_contamination_classes_fail(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    evidence["runs"][0]["hidden_row_contamination"]["prohibited_counts"].pop("clock_unresolved")
    assert evaluator(authority, stage1).evaluate(evidence).status == "FAIL"


def test_fewer_than_required_hidden_rows_fail(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    run = next(row for row in evidence["runs"] if row["scene"] == "WALL"
               and next(unit for unit in stage1["units"] if unit["unit_id"] == row["unit_id"])["design_role"] == "HELD_OUT_VALIDATION")
    run["hidden_row_contamination"]["designated_hidden_row_count"] = 18
    assert_gate_fails(authority, stage1, evidence, "hidden_row_contamination")


def test_self_asserted_provenance_fails(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    evidence["runs"][0]["runtime_provenance_receipt"].update(
        independently_derived=False, asserted_by_evidence_builder=True)
    assert_gate_fails(authority, stage1, evidence, "unit_identity_runtime_path_durability")


def test_point_visible_stable_occluded_row_cannot_pass(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    run = next(row for row in evidence["runs"] if row["designated_hidden_row_indices"])
    index = run["designated_hidden_row_indices"][0]
    run["visibility_samples"][index]["point_visible"] = True
    decision = evaluator(authority, stage1).evaluate(evidence)
    assert decision.status == "FAIL"
    assert decision.gates["calibration_world_and_wall_relative_support"]["status"] == "FAIL"
    assert decision.gates["hidden_row_contamination"]["status"] == "FAIL"


@pytest.mark.parametrize("field,contamination", [
    ("detector_visible", "detector_visible"),
    ("temporal_alignment_resolved", "clock_unresolved"),
    ("in_support", "out_of_support"),
    ("identity_valid", "ambiguous_or_invalid_identity"),
    ("runtime_provenance_resolved", "runtime_or_provenance_unresolved"),
    ("path_state_valid", "path_state_invalid"),
    ("malformed_or_missing", "malformed_or_missing"),
])
def test_designated_hidden_row_contamination_is_derived(authority, stage1, field, contamination):
    evidence = valid_evidence(authority, stage1)
    run = next(row for row in evidence["runs"] if row["designated_hidden_row_indices"])
    index = run["designated_hidden_row_indices"][0]
    run["visibility_samples"][index][field] = (field in {"detector_visible", "malformed_or_missing"})
    decision = evaluator(authority, stage1).evaluate(evidence)
    assert decision.status == "FAIL"
    detail = decision.gates["hidden_row_contamination"]["detail"][run["unit_id"]]
    assert detail["derived_prohibited_counts"][contamination] == 1


def test_stale_clean_contamination_summary_fails(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    run = next(row for row in evidence["runs"] if row["designated_hidden_row_indices"])
    index = run["designated_hidden_row_indices"][0]
    run["visibility_samples"][index]["point_visible"] = True
    assert_gate_fails(authority, stage1, evidence, "hidden_row_contamination")


def test_geometry_band_disagreement_is_a_transition_row_not_an_unscored_hole(authority, stage1):
    """A row the measured band and point visibility disagree about is partial.

    The band is measured on the predeclared TRANSITION_MEASUREMENT replicate and
    applied unchanged to the held-out replicate, whose aligned coordinates never
    land on exactly the same edge, so such rows are unavoidable. Classifying
    them as "unresolved" made required_evidence_completeness unsatisfiable. They
    must be partial: reported, never scored, and still contaminating if someone
    designates one as a hidden row.
    """
    evidence = valid_evidence(authority, stage1)
    run = next(row for row in evidence["runs"] if row["designated_hidden_row_indices"])
    index = run["designated_hidden_row_indices"][0]
    sample = run["visibility_samples"][index]
    sample["point_visible"] = True          # inside the hidden band, but visible
    sample["regime"] = "partial_transition"
    decision = evaluator(authority, stage1).evaluate(evidence)
    ledger = decision.gates["required_evidence_completeness"]["detail"][run["unit_id"]]
    assert ledger["unexcused_unresolved_indices"] == []
    detail = decision.gates["hidden_row_contamination"]["detail"][run["unit_id"]]
    assert detail["derived_prohibited_counts"]["partial_transition"] == 1
    assert detail["stable_occluded_qualified_rows"] < detail["required"]
    assert decision.status == "FAIL"


def test_emptying_a_scored_class_by_flipping_visibility_still_fails(authority, stage1):
    """Reclassifying disagreements as partial may not become an escape hatch."""
    evidence = valid_evidence(authority, stage1)
    for run in evidence["runs"]:
        for sample in run["visibility_samples"]:
            if sample["regime"] == "stable_occluded":
                sample.update(point_visible=True, regime="partial_transition")
    decision = evaluator(authority, stage1).evaluate(evidence)
    assert decision.status == "FAIL"
    # The >=60 stable-occluded minimum per direction is what refuses it.
    assert decision.gates["stable_visibility_base_rate_robust"]["status"] == "FAIL"
    assert all(item["stable_occluded_n"] == 0 for item
               in decision.gates["stable_visibility_base_rate_robust"]["detail"].values())


def test_designated_hidden_row_identities_are_exact(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    run = next(row for row in evidence["runs"] if row["designated_hidden_row_indices"])
    run["designated_hidden_row_indices"][-1] = run["designated_hidden_row_indices"][0]
    assert evaluator(authority, stage1).evaluate(evidence).status == "FAIL"


def bound_stage2(tmp_path: Path):
    authority = tmp_path / "authority.json"; authority.write_bytes(AUTHORITY_PATH.read_bytes())
    provenance = tmp_path / "provenance.json"; provenance.write_text("{}\n")
    stage1_manifest = tmp_path / "stage1.json"; stage1_manifest.write_bytes(STAGE1_PATH.read_bytes())
    authority_value = load_json(authority)
    stage1_value = load_json(stage1_manifest)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(valid_evidence(authority_value, stage1_value),
                                        sort_keys=True) + "\n")
    decision_path = tmp_path / "decision.json"
    evaluated = Stage1Evaluator(authority_value, stage1_value,
        authority_sha256=sha256_file(authority),
        manifest_sha256=sha256_file(stage1_manifest)).evaluate(load_json(evidence_path))
    assert evaluated.status == "PASS"
    decision = evaluated.to_dict(authority_sha256=sha256_file(authority),
        manifest_sha256=sha256_file(stage1_manifest),
        evidence_sha256=sha256_file(evidence_path))
    decision_path.write_text(json.dumps(decision, sort_keys=True) + "\n")
    manifest_path = tmp_path / "stage2.json"
    manifest = load_json(STAGE2_PATH)
    for identity in manifest["trajectory_identities"]:
        identity.update(target_window_status="MATERIALIZED_FROM_STAGE1",
                        target_model_frame_indices=list(range(20, 39)),
                        expected_causal_fir_target_world_x_blocks=[float(i) for i in range(19)])
    by_id = {item["trajectory_id"]: item for item in manifest["trajectory_identities"]}
    manifest["capture_units"] = [{**unit, **by_id[unit["trajectory_id"]]}
                                 for unit in manifest["capture_units"]]
    manifest["units"] = (manifest["capture_units"] + [manifest["physical_gate_unit"]]
                         + manifest["extraction_units"] + manifest["readout_and_terminal_units"])
    manifest.update(status="POST_STAGE1_MATERIALIZED_AWAITING_SEPARATE_FREEZE_AND_AUTHORIZATION",
                    stage1_decision_sha256=sha256_file(decision_path),
                    stage1_evidence_sha256=sha256_file(evidence_path))
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    receipt = {"schema_version": "1.1",
        "artifact_id": "regime-a-prime-stage2-post-stage1-authorization-v0.2",
        "status": "FROZEN_AUTHORIZED", "STAGE_2_COLLECTION_AUTHORIZED": True,
        "confirmatory_collection_authorized": False, "authority_sha256": sha256_file(authority),
        "stage1_manifest_sha256": sha256_file(stage1_manifest),
        "stage1_decision_sha256": sha256_file(decision_path),
        "stage1_evidence_sha256": sha256_file(evidence_path),
        "stage1_status": "PASS",
        "stage2_manifest_sha256": sha256_file(manifest_path), "source_commit_sha": "c" * 40,
        "expected_run_namespace": manifest["run_namespace"],
        "preoutcome_provenance_receipt_sha256": sha256_file(provenance)}
    receipt["authorization_payload_sha256"] = canonical_payload_sha256(receipt)
    return (authority, provenance, stage1_manifest, evidence_path, decision_path, decision,
            manifest_path, manifest, receipt)


def authorize(bundle, *, decision=None, receipt=None):
    (authority, provenance, stage1_manifest, evidence_path, decision_path, actual_decision,
     manifest_path, manifest, actual_receipt) = bundle
    supplied_receipt = actual_receipt if receipt is None else receipt
    authorization_path = authority.parent / "authorization.json"
    authorization_path.write_text(json.dumps(supplied_receipt, sort_keys=True) + "\n")
    require_stage2_authorization(manifest, supplied_receipt,
        authorization_receipt_path=authorization_path,
        stage1_decision=actual_decision if decision is None else decision, authority_path=authority,
        manifest_path=manifest_path, stage1_manifest_path=stage1_manifest,
        stage1_evidence_path=evidence_path, stage1_decision_path=decision_path,
        current_source_commit="c" * 40,
        preoutcome_provenance_path=provenance)


def test_exact_separate_stage2_authorization_passes(tmp_path):
    authorize(bound_stage2(tmp_path))


@pytest.mark.parametrize("target,field,value", [
    ("identity", "outer_fold", 1),
    ("identity", "phase_frames", 3),
    ("identity", "direction", "RIGHT_TO_LEFT"),
    ("identity", "speed_blocks_per_second", 3.0),
    ("capture", "outer_fold", 1),
    ("capture", "phase_frames", 3),
])
def test_stage2_fold_phase_and_capture_allocation_cannot_override_authority(
        tmp_path, target, field, value):
    bundle = bound_stage2(tmp_path); manifest = deepcopy(bundle[7])
    item = manifest["trajectory_identities"][0] if target == "identity" else manifest["capture_units"][0]
    item[field] = value
    with pytest.raises(EvidenceError):
        validate_stage2_manifest_design(load_json(bundle[0]), manifest, require_materialized=True)


def test_fake_stage1_pass_text_is_insufficient(tmp_path):
    with pytest.raises(PermissionError):
        authorize(bound_stage2(tmp_path), decision={"status": "PASS"})


def test_edited_pass_with_failed_gate_cannot_unlock_stage2(tmp_path):
    bundle = list(bound_stage2(tmp_path))
    decision_path, decision, receipt = bundle[4], deepcopy(bundle[5]), deepcopy(bundle[8])
    decision["gates"]["render_server_temporal_alignment"]["status"] = "FAIL"
    decision_path.write_text(json.dumps(decision, sort_keys=True) + "\n")
    receipt["stage1_decision_sha256"] = sha256_file(decision_path)
    receipt["authorization_payload_sha256"] = canonical_payload_sha256(
        receipt, omit="authorization_payload_sha256")
    bundle[5], bundle[8] = decision, receipt
    with pytest.raises(PermissionError): authorize(tuple(bundle))


def test_fabricated_all_pass_decision_cannot_unlock_stage2_even_when_rebound(tmp_path):
    bundle = list(bound_stage2(tmp_path))
    decision_path, decision = bundle[4], deepcopy(bundle[5])
    manifest_path, manifest, receipt = bundle[6], deepcopy(bundle[7]), deepcopy(bundle[8])
    decision["gates"]["render_server_temporal_alignment"]["detail"] = {"fabricated": True}
    assert all(gate["status"] == "PASS" for gate in decision["gates"].values())
    decision_path.write_text(json.dumps(decision, sort_keys=True) + "\n")
    manifest["stage1_decision_sha256"] = sha256_file(decision_path)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    receipt["stage1_decision_sha256"] = sha256_file(decision_path)
    receipt["stage2_manifest_sha256"] = sha256_file(manifest_path)
    receipt["authorization_payload_sha256"] = canonical_payload_sha256(
        receipt, omit="authorization_payload_sha256")
    bundle[5], bundle[7], bundle[8] = decision, manifest, receipt
    with pytest.raises(PermissionError, match="not reproduced"):
        authorize(tuple(bundle))


def test_rebound_edited_stage1_evidence_cannot_unlock_stage2(tmp_path):
    bundle = list(bound_stage2(tmp_path))
    evidence_path, decision_path = bundle[3], bundle[4]
    decision, manifest, receipt = deepcopy(bundle[5]), deepcopy(bundle[7]), deepcopy(bundle[8])
    evidence = load_json(evidence_path)
    evidence["runs"][0]["visibility_samples"][0]["point_visible"] = False
    evidence_path.write_text(json.dumps(evidence, sort_keys=True) + "\n")
    decision["stage1_evidence_sha256"] = sha256_file(evidence_path)
    decision_path.write_text(json.dumps(decision, sort_keys=True) + "\n")
    manifest["stage1_evidence_sha256"] = sha256_file(evidence_path)
    manifest["stage1_decision_sha256"] = sha256_file(decision_path)
    bundle[6].write_text(json.dumps(manifest, sort_keys=True) + "\n")
    receipt.update(stage1_evidence_sha256=sha256_file(evidence_path),
                   stage1_decision_sha256=sha256_file(decision_path),
                   stage2_manifest_sha256=sha256_file(bundle[6]))
    receipt["authorization_payload_sha256"] = canonical_payload_sha256(
        receipt, omit="authorization_payload_sha256")
    bundle[5], bundle[7], bundle[8] = decision, manifest, receipt
    with pytest.raises(PermissionError, match="not reproduced"):
        authorize(tuple(bundle))


def test_direct_capture_command_cannot_bypass_missing_authorization(monkeypatch):
    monkeypatch.delenv("MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH", raising=False)
    with pytest.raises(PermissionError):
        require_capture_authorization("stage1-capture", load_json(STAGE1_PATH), STAGE1_PATH, AUTHORITY_PATH)


def test_direct_delegated_stage2_command_cannot_bypass_authorization(monkeypatch, tmp_path):
    from scripts.regime_a_prime_qualification_v0_2.stage_unit_driver import delegated
    monkeypatch.delenv("MINEOCCLUDE_STAGE2_AUTHORIZATION_PATH", raising=False)
    manifest = {"authority_binding": {"path": str(AUTHORITY_PATH.relative_to(ROOT))},
                "source_commit_binding": "c" * 40, "locked_stage_commands": {}}
    with pytest.raises(PermissionError):
        delegated({"unit_id": "stage2_physical_gates"}, manifest, tmp_path / "manifest.json",
                  "stage2-gates", tmp_path / "receipt.json")


def test_direct_stage2_backend_cannot_bypass_authorization(monkeypatch, tmp_path):
    for name in ("MINEOCCLUDE_STAGE2_AUTHORIZATION_PATH", "MINEOCCLUDE_STAGE1_EVIDENCE_PATH",
                 "MINEOCCLUDE_STAGE1_DECISION_PATH",
                 "MINEOCCLUDE_STAGE1_MANIFEST_PATH", "MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(PermissionError):
        require_backend_authorization(load_json(STAGE2_PATH), tmp_path / "stage2.json")


def test_generic_signed_runtime_pass_is_insufficient(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    evidence["runs"][0]["runtime_provenance_receipt"] = signed_probe()
    assert_gate_fails(authority, stage1, evidence, "unit_identity_runtime_path_durability")


@pytest.mark.parametrize("field", ["authority_sha256", "stage1_manifest_sha256", "stage1_decision_sha256",
                                    "stage1_evidence_sha256", "stage2_manifest_sha256", "source_commit_sha", "expected_run_namespace",
                                    "preoutcome_provenance_receipt_sha256"])
def test_stale_or_wrong_stage2_authorization_bindings_fail(tmp_path, field):
    bundle = bound_stage2(tmp_path); receipt = deepcopy(bundle[-1]); receipt[field] = "wrong"
    receipt["authorization_payload_sha256"] = canonical_payload_sha256(receipt, omit="authorization_payload_sha256")
    with pytest.raises(PermissionError): authorize(bundle, receipt=receipt)


def test_edited_authorization_payload_hash_fails(tmp_path):
    bundle = bound_stage2(tmp_path); receipt = deepcopy(bundle[-1]); receipt["expected_run_namespace"] = "copied"
    with pytest.raises(PermissionError): authorize(bundle, receipt=receipt)


def test_raw_same_tick_state_is_not_stage2_label():
    positions = [float(i * i) for i in range(12)]
    labels = causal_fir_targets(positions, [8, 9], [0.25, 0.75])
    assert labels != [positions[8], positions[9]]
    with pytest.raises(EvidenceError): causal_fir_targets(positions, [8], [0.0, 1.0])


def test_wall_baseline_gate_is_required():
    policy = {"best_k_each_scene_rmse_maximum_blocks": 0.2,
              "training_only_time_baseline_macro_r2_tau_1_to_15_maximum": 0.1}
    good = {"metrics": {"rmse_blocks": 0.1, "macro_r2": 0.5, "bootstrap95_macro_r2": [0.1, 0.9]},
            "training_time_baseline": {"rmse_blocks": 0.09},
            "training_time_baseline_tau1_15": {"macro_r2": 0.0}}
    checks = best_k_qualification_checks({"WALL": deepcopy(good), "NO_WALL": deepcopy(good)}, policy)
    assert checks["WALL_beats_training_time_baseline"] is False


def test_runtime_identity_mismatch_fails_closed():
    expected = {"required_fields": {"branch": "right", "java": "17"},
                "critical_file_sha256": {"mod": "a" * 64}}
    observed = {"independently_derived": True, "asserted_by_evidence_builder": False,
                "branch": "wrong", "java": "17", "critical_file_sha256": {"mod": "a" * 64}}
    with pytest.raises(EvidenceError): verify_runtime_identity(expected, observed)


def test_runtime_source_binding_covers_projection_capture_extraction_and_readout_closure():
    required = set(RUNTIME_CRITICAL_SOURCE_PATHS)
    assert {
        "src/mineocclude/regime_a.py",
        "src/mineocclude/regime_a_execution.py",
        "src/mineocclude/data/capture_contract.py",
        "src/mineocclude/data/build_dataset.py",
        "src/mineocclude/data/package_episode.py",
        "src/mineocclude/contracts/identity.py",
        "src/mineocclude/models/__init__.py",
        "src/mineocclude/probes/p7_ridge.py",
        "src/mineocclude/probes/p7a_execution.py",
    } <= required
    assert all((ROOT / relative).is_file() for relative in required)


def test_complete_looking_runtime_source_summary_cannot_override_bound_bytes():
    forged = {relative: "4" * 64 for relative in RUNTIME_CRITICAL_SOURCE_PATHS}
    with pytest.raises(EvidenceError, match="bytes mismatch"):
        verify_runtime_source_hashes(forged)


DURABLE_PREFIX = "s3://bucket/prefix"


def durable_fixture(tmp_path: Path, *, remote_ok=True):
    receipt_path = tmp_path / "receipt.json"
    # The receipt must bind the manifest's own durable prefix, not merely a URI
    # ending in the unit identity, so a foreign bucket cannot satisfy resume.
    receipt = {"unit_id": "u1", "status": "COMPLETE_VALIDATED_DURABLE",
        "manifest_sha256": "m" * 64, "authority_sha256": "a" * 64,
        "source_commit_sha": "c" * 40, "scientific_run_id": "run",
        "durable_uri": f"{DURABLE_PREFIX}/u1"}
    receipt_path.write_text(json.dumps(receipt))
    state_dir = tmp_path / "state"; state_dir.mkdir()
    state = {**receipt, "receipt_path": str(receipt_path), "receipt_sha256": sha256_file(receipt_path)}
    (state_dir / "u1.json").write_text(json.dumps(state))
    controller = DurableController({"units": [{"unit_id": "u1", "receipt_path": str(receipt_path),
            "scientific_run_id": "run", "command": ["locked-command", "--stage", "stage1-capture"]}],
        "durable_prefix": DURABLE_PREFIX},
        state_dir, tmp_path / "events", manifest_sha256="m" * 64, authority_sha256="a" * 64,
        source_commit_sha="c" * 40, run_namespace="run", stage_role="stage1",
        durable_verifier=lambda unit, value: remote_ok)
    return controller, receipt_path, state_dir / "u1.json"


def test_foreign_durable_prefix_with_matching_unit_id_is_not_reused(tmp_path):
    """Resume must bind the manifest's own prefix, not the trailing identity."""
    controller, receipt_path, state_path = durable_fixture(tmp_path)
    receipt = load_json(receipt_path)
    receipt["durable_uri"] = "s3://attacker-bucket/prefix/u1"
    receipt_path.write_text(json.dumps(receipt))
    state = load_json(state_path); state["receipt_sha256"] = sha256_file(receipt_path)
    state_path.write_text(json.dumps(state))
    assert controller.completed("u1") is False


def test_stale_local_resume_state_is_not_reused(tmp_path):
    controller, _, state_path = durable_fixture(tmp_path)
    state = load_json(state_path); state["receipt_sha256"] = "0" * 64; state_path.write_text(json.dumps(state))
    assert controller.completed("u1") is False


def test_missing_remote_durable_object_is_not_reused(tmp_path):
    controller, _, _ = durable_fixture(tmp_path, remote_ok=False)
    assert controller.completed("u1") is False


def test_direct_backend_predecessor_receipt_rechecks_bindings_and_remote_durability(tmp_path):
    manifest_path = tmp_path / "stage2.json"; manifest_path.write_text("{}\n")
    manifest = {"authority_binding": {"sha256": "a" * 64}, "run_namespace": "stage2",
                "durable_prefix": "s3://qualified-bucket/stage2", "capture_units": []}
    unit = {"unit_id": "extract_u1"}
    receipt = {"unit_id": "extract_u1", "status": "COMPLETE_VALIDATED_DURABLE",
        "authority_sha256": "a" * 64, "manifest_sha256": sha256_file(manifest_path),
        "source_commit_sha": "c" * 40, "scientific_run_id": "stage2",
        "durable_uri": "s3://qualified-bucket/stage2/derived/extract_u1"}
    require_durable_unit_receipt(manifest, manifest_path, unit, receipt,
        current_source_commit="c" * 40, durable_verifier=lambda *_: True)
    forged = deepcopy(receipt); forged["status"] = "COMPLETE_VALIDATED_DURABLE"
    forged["manifest_sha256"] = "m" * 64
    with pytest.raises(RuntimeError, match="binding mismatch"):
        require_durable_unit_receipt(manifest, manifest_path, unit, forged,
            current_source_commit="c" * 40, durable_verifier=lambda *_: True)
    with pytest.raises(RuntimeError, match="remote durability"):
        require_durable_unit_receipt(manifest, manifest_path, unit, receipt,
            current_source_commit="c" * 40, durable_verifier=lambda *_: False)


def test_direct_backend_refuses_foreign_durable_prefix_even_if_remote_bytes_verify(tmp_path):
    manifest_path = tmp_path / "stage2.json"; manifest_path.write_text("{}\n")
    manifest = {"authority_binding": {"sha256": "a" * 64}, "run_namespace": "stage2",
                "durable_prefix": "s3://qualified-bucket/stage2", "capture_units": []}
    unit = {"unit_id": "extract_u1"}
    receipt = {"unit_id": "extract_u1", "status": "COMPLETE_VALIDATED_DURABLE",
        "authority_sha256": "a" * 64, "manifest_sha256": sha256_file(manifest_path),
        "source_commit_sha": "c" * 40, "scientific_run_id": "stage2",
        "durable_uri": "s3://foreign-bucket/copied/derived/extract_u1"}
    with pytest.raises(RuntimeError, match="binding mismatch"):
        require_durable_unit_receipt(manifest, manifest_path, unit, receipt,
            current_source_commit="c" * 40, durable_verifier=lambda *_: True)


def test_local_capture_summary_cannot_rebind_raw_bytes_away_from_durable_inventory(tmp_path):
    receipt_path = tmp_path / "receipts" / "capture" / "u1.json"
    raw = tmp_path / "receipts" / "captures" / "u1" / "raw" / "server_state.jsonl"
    raw.parent.mkdir(parents=True); raw.write_text('{"sheep_x": 1.0}\n')
    unit = {"unit_id": "u1", "receipt_path": str(receipt_path)}
    original_sha = sha256_file(raw)
    receipt = {"durable_objects": {"raw/server_state.jsonl": original_sha}}
    assert bound_capture_artifact(unit, receipt, "raw/server_state.jsonl") == raw
    raw.write_text('{"sheep_x": 9.0}\n')
    with pytest.raises(RuntimeError, match="hash mismatch"):
        bound_capture_artifact(unit, receipt, "raw/server_state.jsonl")


def test_local_frame_changed_after_physical_gate_cannot_reach_extraction(tmp_path):
    receipt_path = tmp_path / "receipts" / "capture" / "u1.json"
    root = tmp_path / "receipts" / "captures" / "u1"
    frame = root / "raw" / "frames" / "000001.png"
    package = root / "capture_package_v0_1.json"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"qualified frame")
    package.write_bytes(b"qualified package")
    unit = {"unit_id": "u1", "receipt_path": str(receipt_path)}
    receipt = {"durable_objects": {
        "raw/frames/000001.png": sha256_file(frame),
        "capture_package_v0_1.json": sha256_file(package)}}
    assert verify_local_capture_inventory(unit, receipt) == root
    frame.write_bytes(b"changed after gate")
    with pytest.raises(RuntimeError, match="diverge from durable inventory"):
        verify_local_capture_inventory(unit, receipt)


def test_capture_inventory_path_traversal_is_refused(tmp_path):
    unit = {"unit_id": "u1", "receipt_path": str(tmp_path / "receipts/capture/u1.json")}
    with pytest.raises(RuntimeError, match="path is unsafe"):
        verify_local_capture_inventory(unit, {"durable_objects": {"../foreign": "0" * 64}})


def test_duplicate_durable_unit_identity_fails_closed(tmp_path):
    manifest = {"units": [{"unit_id": "u1"}, {"unit_id": "u1"}]}
    with pytest.raises(EvidenceError):
        DurableController(manifest, tmp_path / "state", tmp_path / "events")


def test_completed_verified_unit_is_not_recollected(monkeypatch, tmp_path):
    controller, _, _ = durable_fixture(tmp_path)
    monkeypatch.setattr("mineocclude.prospective.development_workflow.subprocess.run",
                        lambda *args, **kwargs: pytest.fail("verified unit was recollected"))
    controller.run(authorized=True)
    events = [json.loads(line) for line in controller.event_log.read_text().splitlines()]
    assert [event["event"] for event in events] == ["unit_reused", "stage1_units_complete"]


def test_interrupted_unit_uses_exact_bounded_retry_policy(monkeypatch, tmp_path):
    receipt_path = tmp_path / "receipt.json"
    manifest = {"units": [{"unit_id": "u1", "receipt_path": str(receipt_path),
                            "scientific_run_id": "run",
                            "command": ["locked-command", "--stage", "stage1-capture"]}],
                "durable_prefix": DURABLE_PREFIX}
    controller = DurableController(manifest, tmp_path / "state", tmp_path / "events",
        manifest_sha256="m" * 64, authority_sha256="a" * 64,
        source_commit_sha="c" * 40, run_namespace="run", maximum_attempts=3,
        stage_role="stage1", durable_verifier=lambda unit, receipt: True)
    attempts = 0
    def run_attempt(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 3:
            receipt_path.write_text(json.dumps({"unit_id": "u1", "status": controller.TERMINAL,
                "manifest_sha256": "m" * 64, "authority_sha256": "a" * 64,
                "source_commit_sha": "c" * 40, "scientific_run_id": "run",
                "durable_uri": f"{DURABLE_PREFIX}/u1"}))
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr("mineocclude.prospective.development_workflow.subprocess.run", run_attempt)
    controller.run(authorized=True)
    assert attempts == 3 and controller.completed("u1") is True


@pytest.mark.parametrize("field,value", [("manifest_sha256", "x" * 64),
                                          ("authority_sha256", "x" * 64),
                                          ("source_commit_sha", "x" * 40),
                                          ("scientific_run_id", "wrong-run")])
def test_resume_binding_mismatch_is_not_reused(tmp_path, field, value):
    controller, receipt_path, state_path = durable_fixture(tmp_path)
    receipt = load_json(receipt_path); receipt[field] = value; receipt_path.write_text(json.dumps(receipt))
    state = load_json(state_path); state["receipt_sha256"] = sha256_file(receipt_path)
    state_path.write_text(json.dumps(state))
    assert controller.completed("u1") is False


def test_remote_durable_manifest_binds_unit_authority_manifest_source_and_run(monkeypatch):
    unit = {"unit_id": "u1"}
    receipt = {"unit_id": "u1", "authority_sha256": "a" * 64,
        "manifest_sha256": "m" * 64, "source_commit_sha": "c" * 40,
        "scientific_run_id": "run", "durable_uri": "s3://bucket/prefix/u1",
        "durable_objects": {"payload.bin": sha256_file(Path(__file__))}}
    object_bytes = Path(__file__).read_bytes()
    remote_manifest = {"unit_id": "u1", "authority_sha256": "a" * 64,
        "manifest_sha256": "m" * 64, "source_commit_sha": "c" * 40,
        "scientific_run_id": "run", "files": receipt["durable_objects"]}
    manifest_bytes = (json.dumps(remote_manifest, sort_keys=True) + "\n").encode()
    receipt["remote_checksum_manifest_sha256"] = __import__("hashlib").sha256(manifest_bytes).hexdigest()
    listing = json.dumps({"Contents": [{"Key": "prefix/u1/payload.bin"},
                                        {"Key": "prefix/u1/sha256_manifest.json"}]}).encode()
    responses = iter([SimpleNamespace(returncode=0, stdout=manifest_bytes),
                      SimpleNamespace(returncode=0, stdout=listing),
                      SimpleNamespace(returncode=0, stdout=object_bytes)])
    monkeypatch.setattr("mineocclude.prospective.development_workflow.subprocess.run",
                        lambda *args, **kwargs: next(responses))
    assert verify_remote_durable_objects(unit, receipt) is True


def test_copied_remote_durable_manifest_identity_fails(monkeypatch):
    unit = {"unit_id": "u1"}
    remote_manifest = {"unit_id": "copied", "authority_sha256": "a" * 64,
        "manifest_sha256": "m" * 64, "source_commit_sha": "c" * 40,
        "scientific_run_id": "run", "files": {"payload.bin": "0" * 64}}
    data = json.dumps(remote_manifest).encode()
    receipt = {"unit_id": "u1", "authority_sha256": "a" * 64,
        "manifest_sha256": "m" * 64, "source_commit_sha": "c" * 40,
        "scientific_run_id": "run", "durable_uri": "s3://bucket/prefix/u1",
        "durable_objects": {"payload.bin": "0" * 64},
        "remote_checksum_manifest_sha256": __import__("hashlib").sha256(data).hexdigest()}
    monkeypatch.setattr("mineocclude.prospective.development_workflow.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=data))
    assert verify_remote_durable_objects(unit, receipt) is False


def valid_capture_receipts(manifest: dict, manifest_sha256: str,
                           source_commit: str = "c" * 40) -> dict[str, dict]:
    receipts = {}
    by_trajectory = {}
    authority = load_json(AUTHORITY_PATH)
    for unit in manifest["capture_units"]:
        path_hash = unit["expected_path_sha256"]
        physical = {"checks": {name: True for name in PHYSICAL_NAMES},
                    "target_row_count": 19, "contamination_rows": [],
                    "target_model_frame_indices": unit["target_model_frame_indices"],
                    "aligned_target_world_x_blocks": unit["expected_causal_fir_target_world_x_blocks"]}
        runtime, path_probe, durability = valid_unit_probes(authority, manifest, unit)
        path_probe = signed_probe(**{key: value for key, value in path_probe.items()
                                     if key not in {"payload_sha256", "captured_path_sha256", "expected_path_sha256"}},
                                  captured_path_sha256=path_hash, expected_path_sha256=path_hash)
        receipts[unit["unit_id"]] = {"unit_id": unit["unit_id"],
            "status": "COMPLETE_VALIDATED_DURABLE", "authority_sha256": manifest["authority_binding"]["sha256"],
            "manifest_sha256": manifest_sha256, "source_commit_sha": source_commit,
            "stage1_decision_sha256": manifest["stage1_decision_sha256"],
            "scientific_run_id": manifest["run_namespace"], "runtime_provenance_receipt": runtime,
            "path_state_receipt": path_probe,
            "durability_receipt": durability, "stage2_physical_evidence": physical}
        by_trajectory.setdefault(unit["trajectory_id"], path_hash)
    return receipts


PHYSICAL_NAMES = {"clock_alignment", "stable_visibility", "hidden_row_validity",
                  "physical_support", "zero_target_row_contamination"}


def test_stage2_physical_gate_requires_every_check_and_pair():
    manifest = load_json(STAGE2_PATH)
    manifest["status"] = "POST_STAGE1_MATERIALIZED_AWAITING_SEPARATE_FREEZE_AND_AUTHORIZATION"
    manifest["source_commit_binding"] = "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"
    manifest["stage1_decision_sha256"] = "d" * 64
    for unit in manifest["capture_units"]:
        unit["target_model_frame_indices"] = list(range(20, 39))
        unit["expected_causal_fir_target_world_x_blocks"] = [float(i) for i in range(19)]
    receipts = valid_capture_receipts(manifest, "m" * 64)
    assert validate_physical_gate_receipts(manifest, receipts, manifest_sha256="m" * 64,
                                           current_source_commit="c" * 40)["status"] == "PASS"
    receipts[manifest["capture_units"][0]["unit_id"]]["stage2_physical_evidence"]["checks"].pop("clock_alignment")
    with pytest.raises(RuntimeError):
        validate_physical_gate_receipts(manifest, receipts, manifest_sha256="m" * 64,
                                        current_source_commit="c" * 40)


def test_stage2_physical_gate_rejects_stale_target_summary():
    manifest = load_json(STAGE2_PATH)
    manifest["status"] = "POST_STAGE1_MATERIALIZED_AWAITING_SEPARATE_FREEZE_AND_AUTHORIZATION"
    manifest["stage1_decision_sha256"] = "d" * 64
    for unit in manifest["capture_units"]:
        unit["target_model_frame_indices"] = list(range(20, 39))
        unit["expected_causal_fir_target_world_x_blocks"] = [float(i) for i in range(19)]
    receipts = valid_capture_receipts(manifest, "m" * 64)
    receipts[manifest["capture_units"][0]["unit_id"]]["stage2_physical_evidence"][
        "target_model_frame_indices"][0] = 19
    with pytest.raises(RuntimeError):
        validate_physical_gate_receipts(manifest, receipts, manifest_sha256="m" * 64,
                                        current_source_commit="c" * 40)


def test_numeric_cleanup_and_minimal_stage1_design(authority, stage1):
    serialized = json.dumps(authority)
    assert "0.52" not in serialized and "0.4374893206596274" not in serialized
    assert authority["stage1_policy"]["run_count"] == 8 == len(stage1["units"])
    cells = {(u["direction"], u["scene"], u["design_role"]) for u in stage1["units"]}
    assert len(cells) == 8
    assert authority["stage1_policy"]["temporal_alignment"]["prospective_ci_width"]["acceptance_threshold"] is None


@pytest.mark.parametrize("field,value", [
    ("direction", "RIGHT_TO_LEFT"), ("scene", "NO_WALL"),
    ("speed_blocks_per_second", 3.0), ("start_world_x", -7.7),
    ("expected_frames", 179),
])
def test_manifest_cannot_override_stage1_authority(authority, stage1, field, value):
    tampered = deepcopy(stage1)
    tampered["units"][0][field] = value
    decision = evaluator(authority, tampered).evaluate(valid_evidence(authority, stage1))
    assert decision.status == "FAIL"


def test_stage1_evidence_manifest_hash_mismatch_fails(authority, stage1):
    evidence = valid_evidence(authority, stage1)
    evidence["stage1_manifest_sha256"] = "0" * 64
    assert evaluator(authority, stage1).evaluate(evidence).status == "FAIL"


def test_designated_hidden_row_must_positively_qualify_as_stable_occluded(authority, stage1):
    """A hidden row outside the measured stable-occluded interval scores zero on
    every prohibited class, so counting prohibited classes alone is fail-open."""
    evidence = valid_evidence(authority, stage1)
    bounds = evidence["transition_measurement_by_direction"]["LEFT_TO_RIGHT"]
    run = next(row for row in evidence["runs"] if row["unit_id"] == "a1q_ltr_wall_r02")
    sample = run["visibility_samples"][run["designated_hidden_row_indices"][0]]
    # Strictly below the lower partial bound: point-hidden and detector-absent,
    # therefore no prohibited class fires, but the row is NOT stable-occluded.
    outside = bounds["partial_transition_world_x_intervals"][0][0] - 1.0
    sample["world_x"] = outside
    sample["wall_relative_x"] = outside - authority["apparatus"]["wall_relative_origin_world_x"]
    sample["point_visible"] = False
    sample["detector_visible"] = False
    sample["regime"] = "unresolved"
    assert_gate_fails(authority, stage1, evidence, "hidden_row_contamination")


def test_hidden_row_regime_label_must_also_be_stable_occluded(authority, stage1):
    """The declared regime must agree with the derived one on designated rows."""
    evidence = valid_evidence(authority, stage1)
    run = next(row for row in evidence["runs"] if row["unit_id"] == "a1q_rtl_wall_r02")
    sample = run["visibility_samples"][run["designated_hidden_row_indices"][0]]
    sample["regime"] = "stable_visible"
    assert_gate_fails(authority, stage1, evidence, "hidden_row_contamination")


def test_valid_hidden_rows_report_full_stable_occluded_qualification(authority, stage1):
    decision = evaluator(authority, stage1).evaluate(valid_evidence(authority, stage1))
    detail = decision.gates["hidden_row_contamination"]["detail"]
    required = authority["stage1_policy"]["contamination"][
        "required_hidden_rows_per_wall_validation_run"]
    for unit_id in ("a1q_ltr_wall_r02", "a1q_rtl_wall_r02"):
        assert detail[unit_id]["stable_occluded_qualified_rows"] == required


def test_controller_cli_is_importable_and_fails_closed_on_forged_authorization(tmp_path):
    """The CLI is invoked as a script; without src on sys.path it died with
    ModuleNotFoundError before any authorization check could run."""
    import subprocess, sys as _sys
    root = Path(__file__).resolve().parents[2]
    forged = tmp_path / "auth.json"
    forged.write_text(json.dumps({
        "artifact_id": "regime-a-prime-stage1-authorization-v0.2",
        "status": "FROZEN_AUTHORIZED",
        "STAGE_1_COLLECTION_AUTHORIZED": True,
        "STAGE_2_COLLECTION_AUTHORIZED": False}))
    provenance = tmp_path / "prov.json"
    provenance.write_text(json.dumps({"artifact_id": "forged"}))
    result = subprocess.run(
        [_sys.executable, "scripts/regime_a_prime_qualification_v0_2/development_controller.py",
         "run-stage1", "--authorization", str(forged), "--provenance", str(provenance),
         "--state-dir", str(tmp_path / "s"), "--events", str(tmp_path / "e.jsonl"),
         "--evidence", str(tmp_path / "ev.json"), "--decision", str(tmp_path / "d.json")],
        cwd=root, capture_output=True, text=True)
    assert result.returncode != 0
    assert "ModuleNotFoundError" not in result.stderr
    assert "pre-outcome provenance rejects" in result.stderr
    assert not (tmp_path / "d.json").exists()


def test_controller_monitor_path_imports_cleanly(tmp_path):
    import subprocess, sys as _sys
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "state").mkdir()
    result = subprocess.run(
        [_sys.executable, "scripts/regime_a_prime_qualification_v0_2/development_controller.py",
         "monitor", str(tmp_path / "state")], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["durable_units"] == 0
