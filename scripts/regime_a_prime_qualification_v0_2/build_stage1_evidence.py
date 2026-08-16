#!/usr/bin/env python3
"""Build Stage-1 evidence using independently measured methods and receipts."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mineocclude.prospective.clock_domains import TimebaseSpec  # noqa: E402
from mineocclude.prospective.development_workflow import (  # noqa: E402
    Stage1Evaluator, atomic_write_json, causal_fir_targets, derive_projection_validity, load_json,
    mean_student_t_interval, sha256_file,
)
from mineocclude.prospective.temporal_alignment import (  # noqa: E402
    AlignmentEvidence, AlignmentRequirements, UncertaintyRequest, estimate_alignment,
)
from mineocclude.vision.magenta import HsvRange, detect_magenta  # noqa: E402
from scripts.run_regime_a import detector_rgb_rows  # noqa: E402


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def detector():
    path = ROOT / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_config.json"
    config = load_json(path)["configuration"]["detector_settings"]
    return config, tuple(HsvRange(*values) for values in config["hsv_ranges"])


def detect_series(capture: Path, frame_pixels: list[int]) -> tuple[np.ndarray, list[bool]]:
    config, ranges = detector(); centroids, present = [], []
    for frame in sorted((capture / "raw/frames").glob("*.png")):
        result = detect_magenta(detector_rgb_rows(frame, expected_size=tuple(frame_pixels)), hsv_ranges=ranges,
            min_area_pixels=config["min_area_pixels"], max_area_pixels=config["max_area_pixels"],
            open_iterations=config["open_iterations"], close_iterations=config["close_iterations"],
            morphology_radius_pixels=config["morphology_radius_pixels"], connectivity=config["connectivity"])
        present.append(result.status == "detected")
        centroids.append(0.0 if result.centroid_xy is None else float(result.centroid_xy[0]))
    return np.asarray(centroids), present


def derivative_cross_correlation_lag(logged: np.ndarray, rendered: np.ndarray,
                                     exclude: np.ndarray, maximum_lag: int) -> float:
    """Independent integer-lag estimate; it does not call or reuse the FIR fit."""
    d_logged, d_rendered = np.diff(logged), np.diff(rendered)
    bad = exclude[:-1] | exclude[1:]
    scores: dict[int, float] = {}
    for lag in range(maximum_lag + 1):
        indices = np.arange(lag, len(d_logged))
        usable = ~(bad[indices] | bad[indices - lag])
        if usable.sum() < 30:
            continue
        value = abs(float(np.corrcoef(d_logged[indices[usable] - lag], d_rendered[indices[usable]])[0, 1]))
        if np.isfinite(value):
            scores[lag] = value
    if not scores:
        raise RuntimeError("cross-correlation lag is unresolved")
    best_lag = max(scores, key=scores.get)
    if best_lag - 1 in scores and best_lag + 1 in scores:
        left, center, right = scores[best_lag - 1], scores[best_lag], scores[best_lag + 1]
        denominator = left - 2 * center + right
        if denominator != 0:
            offset = max(-1.0, min(1.0, 0.5 * (left - right) / denominator))
            return float(best_lag + offset)
    return float(best_lag)


def intervals_for_measurement(state: list[dict], aligned_x: list[float], detected: list[bool],
                              direction: str, lane: list[float], unit_id: str) -> dict:
    geometric_hidden_x = [x for row, x in zip(state, aligned_x, strict=True)
                          if row.get("geometric_visible") is False and math.isfinite(x)]
    rendered_hidden_x = [x for x, visible in zip(aligned_x, detected, strict=True) if not visible and math.isfinite(x)]
    if not geometric_hidden_x or not rendered_hidden_x:
        raise RuntimeError(f"transition is unresolved for {unit_id}")
    geometric = [min(geometric_hidden_x), max(geometric_hidden_x)]
    rendered = [min(rendered_hidden_x), max(rendered_hidden_x)]
    hidden = [max(geometric[0], rendered[0]), min(geometric[1], rendered[1])]
    if hidden[0] >= hidden[1]:
        raise RuntimeError(f"no stable hidden interval for {unit_id}")
    partial = [[min(geometric[0], rendered[0]), hidden[0]],
               [hidden[1], max(geometric[1], rendered[1])]]
    visible = [[lane[0], partial[0][0]], [partial[1][1], lane[1]]]
    return {"status": "MEASURED", "measurement_unit_ids": [unit_id], "direction": direction,
        "geometric_point_hidden_world_x_interval": geometric,
        "rendered_detector_absent_world_x_interval": rendered,
        "stable_occluded_world_x_interval": hidden,
        "partial_transition_world_x_intervals": partial,
        "stable_visible_world_x_intervals": visible,
        "measured_transition_widths_blocks": [partial[0][1] - partial[0][0], partial[1][1] - partial[1][0]]}


def derive_unit_spacing(evidence_by_unit: dict, cadence: int) -> bool:
    """Rederive the unit-spacing property from the raw coordinate series.

    Reproduces :meth:`Stage1Evaluator._clock_coordinates_ok` so the emitted flag
    is a measurement of the series this builder actually wrote, not a claim.
    """
    for series in evidence_by_unit.values():
        ticks = series["server_state_ticks"]
        frames = series["render_model_frame_indices"]
        if len(ticks) != len(frames) or len(frames) < 2:
            return False
        if any(later - earlier != 1 for earlier, later in zip(frames, frames[1:])):
            return False
        if any(later - earlier != cadence for earlier, later in zip(ticks, ticks[1:])):
            return False
        if any(tick - ticks[0] != cadence * (frame - frames[0])
               for tick, frame in zip(ticks, frames)):
            return False
    return True


def alignment_requirements(authority: dict, direction: str) -> AlignmentRequirements:
    """Bind the authority's own temporal requirements to the FIR estimator.

    Without these the estimator returns ``MEASURED_NOT_ADJUDICATED``: it reports
    a kernel but applies no coverage rule, no per-trajectory support minimum and
    no pure-delay refusal, so an effectively-pure-delay fit would be written
    into Stage-1 evidence unchallenged. The tolerance handed over is the
    authority's, so the builder and :class:`Stage1Evaluator` decide
    ``kernel_is_pure_delay`` by exactly the same measurement.
    """
    policy = authority["stage1_policy"]["temporal_alignment"]
    fixed = authority["fixed_development_configuration"]
    return AlignmentRequirements(
        minimum_trajectories=policy["minimum_trajectories_per_direction"],
        required_directions=frozenset({direction}),
        required_speeds=frozenset({float(fixed["speed_blocks_per_second"])}),
        required_scenes=frozenset(authority["stage1_policy"]["scenes"]),
        minimum_usable_samples_per_trajectory=policy["minimum_usable_samples_per_trajectory"],
        # Not a precision gate: the authority sets prospective_ci_width
        # acceptance_threshold to null. The admissible causal lag range is
        # [0, maximum_lag_ticks_for_estimation], and an interval wider than that
        # range is unresolvable by the estimator's own search scope rather than
        # merely imprecise. Stage1Evaluator enforces the identical bound on the
        # reported interval endpoints.
        maximum_t_interval_width_ticks=float(policy["maximum_lag_ticks_for_estimation"]),
        # Unread when a pure-delay interpretation is forbidden; the requirement
        # inverts to the refusal and coverage rules below.
        maximum_pure_delay_relative_improvement=0.0,
        pure_delay_interpretation_allowed=policy["pure_delay_interpretation_allowed"],
        pure_delay_off_peak_mass_tolerance=policy["pure_delay_off_peak_mass_tolerance"])


def regime_for(sample: dict, scene: str, transition: dict, valid: bool) -> str:
    """Classify one row exactly as :meth:`Stage1Evaluator._expected_regime` does.

    Any divergence here is silent contradiction: the evaluator rederives every
    regime and fails the run when the builder's label disagrees.
    """
    required_true = ("temporal_alignment_resolved", "identity_valid", "in_support",
                     "render_frame_present", "runtime_provenance_resolved", "path_state_valid")
    if (not valid or sample["malformed_or_missing"]
            or any(sample[name] is not True for name in required_true)):
        return "unresolved"
    if sample["point_visible"] is not True and scene == "NO_WALL":
        return "unresolved"
    if sample["projected_in_frame"] is not True:
        return "unresolved"
    if scene == "NO_WALL":
        return "stable_visible"
    sample_x = sample["world_x"]
    hidden = transition["stable_occluded_world_x_interval"]
    # Closed on the measured bands' own endpoints; geometry/band disagreement is
    # a transition row, reported and never scored.
    in_hidden = hidden[0] <= sample_x <= hidden[1]
    in_partial = any(low <= sample_x <= high
                     for low, high in transition["partial_transition_world_x_intervals"])
    in_visible = any(low <= sample_x <= high
                     for low, high in transition["stable_visible_world_x_intervals"])
    if in_hidden and sample["point_visible"] is False:
        return "stable_occluded"
    if in_partial:
        return "partial_transition"
    if in_visible and sample["point_visible"] is True:
        return "stable_visible"
    if in_hidden or in_visible:
        return "partial_transition"
    return "unresolved"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path); parser.add_argument("authority", type=Path)
    parser.add_argument("output", type=Path); args = parser.parse_args()
    manifest, authority = load_json(args.manifest), load_json(args.authority)
    policy = authority["stage1_policy"]["temporal_alignment"]
    frame_pixels = authority["apparatus"]["canonical_frame_pixels"]
    stored, alignment_evidence = [], {d: [] for d in authority["stage1_policy"]["directions"]}
    cross_lags = {d: [] for d in authority["stage1_policy"]["directions"]}
    clock_coordinates: dict[str, dict[str, list[int]]] = {}
    for unit in manifest["units"]:
        receipt = load_json(Path(unit["receipt_path"]))
        capture = Path(unit["receipt_path"]).parent.parent / "captures" / unit["unit_id"]
        state = jsonl(capture / "raw/server_state.jsonl")
        coordinates = jsonl(capture / "coordinates.jsonl")
        logged = np.asarray([float(row["sheep_x"]) for row in state])
        rendered, present = detect_series(capture, frame_pixels)
        if (len(logged) != unit["expected_frames"] or len(rendered) != len(logged)
                or len(coordinates) != len(logged)):
            raise RuntimeError(f"capture coverage mismatch: {unit['unit_id']}")
        excluded = ~np.asarray(present, dtype=bool)
        server_ticks = np.asarray([row.get("server_tick") for row in state])
        model_frames = np.asarray([row.get("model_frame_idx") for row in coordinates])
        item = AlignmentEvidence(unit["unit_id"], logged, rendered, unit["direction"],
            unit["speed_blocks_per_second"], unit["scene"], excluded,
            server_ticks, model_frames)
        alignment_evidence[unit["direction"]].append(item)
        # Emit the raw coordinate identities the unit-spacing property is
        # derived from. Stage1Evaluator rebuilds the flag from these, so a bare
        # Boolean cannot be mutated without also forging the series beneath it.
        clock_coordinates[unit["unit_id"]] = {
            "server_state_ticks": [int(value) for value in item.server_state_ticks],
            "render_model_frame_indices": [int(value) for value in item.render_model_frame_indices]}
        cross_lags[unit["direction"]].append(derivative_cross_correlation_lag(
            logged, rendered, excluded, policy["maximum_lag_ticks_for_estimation"]))
        stored.append((unit, receipt, capture, state, coordinates, logged, present))

    alignments: dict[str, dict] = {}
    kernels: dict[str, list[float]] = {}
    for direction, items in alignment_evidence.items():
        estimate = estimate_alignment(items, timebase=TimebaseSpec(
            authority["apparatus"]["seconds_per_server_tick"],
            authority["apparatus"]["server_ticks_per_model_frame"]),
            max_lag_ticks=policy["maximum_lag_ticks_for_estimation"],
            requirements=alignment_requirements(authority, direction),
            # Only the Student-t interval is requested. The authority carries no
            # interval-width acceptance threshold, so a bootstrap replicate
            # count and seed would be two numbers no rule reads.
            uncertainty=UncertaintyRequest(confidence_level=policy["confidence_level"]))
        # `measured` only means a kernel came back. `resolved` additionally means
        # the authority's own requirements adjudicated PASS, which is what makes
        # kernel_is_pure_delay below a refusal rather than a label.
        if not estimate.resolved or estimate.kernel is None:
            raise RuntimeError(f"FIR alignment unresolved for {direction}: {estimate.refusal_reason}")
        cc_mean, cc_interval = mean_student_t_interval(cross_lags[direction], policy["confidence_level"])
        ids = [item.trajectory_id for item in items]
        receipts = {unit["unit_id"]: sha256_file(Path(unit["receipt_path"]))
                    for unit, *_ in stored if unit["direction"] == direction}
        fir_values = [float(row["group_delay_ticks"]) for row in estimate.per_trajectory]
        fir_mean, fir_interval = mean_student_t_interval(fir_values, policy["confidence_level"])
        fir_kernels = [row["kernel"] for row in estimate.per_trajectory]
        fir_improvements = [float(row["fir_vs_pure_delay_relative_improvement"])
                            for row in estimate.per_trajectory]
        fir_method = {"method_id": "causal_fir_group_delay", "status": "MEASURED",
            "estimate_ticks": fir_mean,
            "confidence_interval_ticks": fir_interval,
            "trajectory_count": len(estimate.per_trajectory), "trajectory_evidence_ids": ids,
            "per_trajectory_estimates_ticks": fir_values,
            "per_trajectory_kernels": fir_kernels,
            "per_trajectory_fir_vs_pure_delay_relative_improvement": fir_improvements,
            "trajectory_receipt_sha256": receipts,
            "kernel": estimate.kernel,
            # Measured from the reconstructed kernel's own mass under the
            # authority's tolerance, never asserted by this builder.
            "kernel_is_pure_delay": estimate.kernel_is_pure_delay,
            # Coverage, not central tendency: one large improvement may not
            # rescue trajectories that are worse than their own best pure delay.
            "causal_fir_beats_best_pure_delay": all(value > 0 for value in fir_improvements),
            "per_trajectory_beats_best_pure_delay": all(value > 0 for value in fir_improvements)}
        cc_method = {"method_id": "derivative_cross_correlation_lag", "status": "MEASURED",
            "estimate_ticks": cc_mean, "confidence_interval_ticks": cc_interval,
            "trajectory_count": len(cross_lags[direction]), "trajectory_evidence_ids": ids,
            "per_trajectory_estimates_ticks": cross_lags[direction],
            "trajectory_receipt_sha256": receipts}
        cadence = authority["apparatus"]["server_ticks_per_model_frame"]
        evidence_by_unit = {unit_id: clock_coordinates[unit_id] for unit_id in ids}
        alignments[direction] = {"methods": [fir_method, cc_method],
            "agreement_rule": policy["agreement_rule"],
            "clock_coordinate_evidence": evidence_by_unit,
            "unit_spaced_clock_coordinates": derive_unit_spacing(evidence_by_unit, cadence)}
        kernels[direction] = estimate.kernel

    lane = authority["apparatus"]["lane_world_x_blocks"]
    transitions: dict[str, dict] = {}
    aligned_by_unit: dict[str, list[float]] = {}
    for unit, _, _, state, _, logged, present in stored:
        taps = kernels[unit["direction"]]
        aligned = [math.nan] * (len(taps) - 1)
        indices = list(range(len(taps) - 1, len(logged)))
        aligned.extend(causal_fir_targets(logged.tolist(), indices, taps,
            pure_delay_tolerance=policy["pure_delay_off_peak_mass_tolerance"]))
        aligned_by_unit[unit["unit_id"]] = aligned
        if unit["scene"] == "WALL" and unit["design_role"] == "TRANSITION_MEASUREMENT":
            transitions[unit["direction"]] = intervals_for_measurement(
                state, aligned, present, unit["direction"], lane, unit["unit_id"])

    runs = []
    prohibited_names = Stage1Evaluator.PROHIBITED
    wall_origin = authority["apparatus"]["wall_relative_origin_world_x"]
    token_grid = authority["apparatus"]["visual_token_grid"]
    required_hidden = authority["stage1_policy"]["contamination"]["required_hidden_rows_per_wall_validation_run"]
    for unit, receipt, _, state, coordinates, logged, present in stored:
        transition = transitions[unit["direction"]]
        aligned = aligned_by_unit[unit["unit_id"]]
        samples = []
        for index, (raw_x, physical_x, detected) in enumerate(zip(logged, aligned, present, strict=True)):
            aligned_ok = math.isfinite(physical_x)
            x = float(physical_x) if aligned_ok else float(raw_x)
            point_visible = state[index].get("geometric_visible") is True
            valid = aligned_ok and lane[0] <= x <= lane[1]
            projected = coordinates[index]
            raw_projection = {"screen_x": projected.get("screen_x"),
                "screen_y": projected.get("screen_y"),
                "token_row": projected.get("token_cell_row"),
                "token_col": projected.get("token_cell_col")}
            projection_valid = derive_projection_validity(
                raw_projection, frame_pixels=frame_pixels, token_grid=token_grid)
            sample = {"world_x": x, "wall_relative_x": x - wall_origin,
                **raw_projection, "projection_frame_pixels": frame_pixels,
                "projection_token_grid": token_grid,
                "point_visible": point_visible, "detector_visible": bool(detected),
                "render_frame_present": True, "projected_in_frame": projection_valid,
                "temporal_alignment_resolved": aligned_ok, "identity_valid": True,
                "in_support": lane[0] <= x <= lane[1],
                "runtime_provenance_resolved": receipt.get("runtime_provenance_receipt", {}).get("status") == "PASS",
                "path_state_valid": receipt.get("path_state_receipt", {}).get("status") == "PASS",
                "malformed_or_missing": False}
            sample["regime"] = regime_for(sample, unit["scene"], transition, valid)
            samples.append(sample)
        designated_indices = ([index for index, row in enumerate(samples)
                               if row["regime"] == "stable_occluded"][:required_hidden]
                              if unit["scene"] == "WALL"
                              and unit["design_role"] == "HELD_OUT_VALIDATION" else [])
        designated = [samples[index] for index in designated_indices]
        # Every prohibited class the authority enumerates must be counted. Three
        # of the nine were previously absent from the emitted summary, so the
        # evaluator's set comparison rejected the enumeration as incomplete and
        # no builder-produced evidence could reach a contamination verdict.
        counts = {name: 0 for name in prohibited_names}
        for row in designated:
            counts["point_visible"] += int(row["point_visible"])
            counts["partial_transition"] += int(row["regime"] == "partial_transition")
            counts["detector_visible"] += int(row["detector_visible"])
            counts["clock_unresolved"] += int(not row["temporal_alignment_resolved"])
            counts["out_of_support"] += int(not row["in_support"])
            counts["ambiguous_or_invalid_identity"] += int(not row["identity_valid"])
            counts["runtime_or_provenance_unresolved"] += int(
                not row["runtime_provenance_resolved"])
            counts["path_state_invalid"] += int(not row["path_state_valid"])
            counts["malformed_or_missing"] += int(row["malformed_or_missing"])
        if set(counts) != set(prohibited_names):
            raise RuntimeError("prohibited-class enumeration is incomplete")
        runs.append({"unit_id": unit["unit_id"], "direction": unit["direction"], "scene": unit["scene"],
            "speed_blocks_per_second": unit["speed_blocks_per_second"], "frame_count": len(state),
            "unit_receipt_sha256": sha256_file(Path(unit["receipt_path"])),
            "runtime_provenance_receipt": receipt.get("runtime_provenance_receipt"),
            "path_state_receipt": receipt.get("path_state_receipt"),
            "durability_receipt": receipt.get("durability_receipt"),
            "designated_hidden_row_indices": designated_indices,
            "hidden_row_contamination": {"designated_hidden_row_count": len(designated),
                                         "prohibited_counts": counts},
            "visibility_samples": samples})
    atomic_write_json(args.output, {"schema_version": "1.1",
        "artifact_id": "regime-a-prime-stage1-evidence-v0.2",
        "authority_sha256": sha256_file(args.authority), "stage1_manifest_sha256": sha256_file(args.manifest),
        "runs": runs, "alignment_by_direction": alignments,
        "transition_measurement_by_direction": transitions})


if __name__ == "__main__":
    main()
