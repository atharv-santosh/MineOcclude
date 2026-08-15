"""Post-capture exact path/identity and current-renderer visibility gates.

Consumes only the compact autonomous capture manifest plus the persisted local
artifacts. No neural runtime is imported and no GPU can be used by this script.
"""

from __future__ import annotations

import json
from pathlib import Path

from p2_common import (
    OUT,
    WORK,
    capture_context,
    p2_episode_id,
    p2_run_id,
    read_jsonl,
    source_specs,
    wall_coordinates,
    write_json,
)

CAPTURES = WORK / "captures"


def main() -> int:
    capture = json.loads((OUT / "p2_capture_manifest.json").read_text())
    frozen = json.loads((OUT / "p2_target_row_manifest.json").read_text())
    specs = source_specs()
    if (capture.get("status") != "PASS"
            or capture.get("complete_validated_durable_count") != 25
            or capture.get("no_wall_run_count") != 25):
        raise RuntimeError("capture gate requires 25/25 COMPLETE_VALIDATED_DURABLE")

    frozen_by_spec: dict[str, list[dict]] = {}
    for row in frozen["rows"]:
        frozen_by_spec.setdefault(row["source_regime_a_spec_id"], []).append(row)

    failures: list[dict] = []
    visibility_runs: list[dict] = []
    max_difference = 0.0
    total_rows = qualified = detector_visible = geometric_visible = ambiguous = zero = 0

    for spec in specs:
        spec_id = str(spec["trajectory_spec_id"])
        run_id = p2_run_id(spec_id)
        root = CAPTURES / run_id
        state = read_jsonl(root / "raw/server_state.jsonl")
        ticks = read_jsonl(root / "raw/client_tick.jsonl")
        actions = read_jsonl(root / "raw/actions.jsonl")
        visible = read_jsonl(root / "raw/visibility.jsonl")
        wall = wall_coordinates(spec_id)
        expected_targets = sorted(frozen_by_spec[spec_id], key=lambda row: row["target_order"])
        target_frames = [int(row["target_model_frame_idx"]) for row in expected_targets]

        context = capture_context(spec, p2_episode_id(spec), Path("/nonwriting-authority-check"))
        authority_ok = (
            (root / "noise_schedule.jsonl").read_bytes() == context["noise_bytes"]
            and (root / "motion_schedule.json").read_bytes() == context["motion_bytes"]
            and all(row["p2_no_wall_run_id"] == run_id for row in expected_targets)
            and all(row["direction"] == spec["direction"] for row in expected_targets)
            and all(int(row["outer_fold"]) == int(spec["outer_fold"])
                    for row in expected_targets)
        )
        if not authority_ok:
            failures.append({"run_id": run_id, "reason": "mapping/direction/motion authority mismatch"})
            continue

        if not (len(state) == len(ticks) == len(actions) == len(visible)):
            failures.append({"run_id": run_id, "reason": "stream cardinality mismatch"})
            continue
        observed_targets = [row for row in visible if row.get("tau") is not None]
        if ([int(row["model_frame_idx"]) for row in observed_targets] != target_frames
                or [int(row["tau"]) for row in observed_targets] != list(range(1, 20))):
            failures.append({"run_id": run_id, "reason": "target ordering/tau mismatch"})
            continue

        run_max = 0.0
        identity_ok = True
        for index, row in enumerate(state):
            difference = abs(float(row["sheep_x"]) - float(wall[index]))
            run_max = max(run_max, difference)
            identity_ok &= (
                difference == 0.0
                and row.get("server_tick") == index
                and ticks[index].get("server_tick") == index
                and actions[index].get("server_tick") == index
                and row.get("trajectory_spec_id") == spec_id
                and row.get("seed") == spec["seed"]
                and row.get("scene") == "NO_WALL"
            )
        max_difference = max(max_difference, run_max)
        if not identity_ok:
            failures.append({"run_id": run_id, "reason": "exact path/spec/timing identity failed",
                             "max_difference": run_max})
            continue

        run_detector = sum(row["magenta_status"] == "detected" for row in observed_targets)
        run_geometric = sum(row["geometric_status"] == "visible" for row in observed_targets)
        run_qualified = sum(
            row["magenta_status"] == "detected" and row["geometric_status"] == "visible"
            for row in observed_targets
        )
        run_ambiguous = sum(
            (row["magenta_status"] == "detected") != (row["geometric_status"] == "visible")
            for row in observed_targets
        )
        run_zero = sum(
            row["magenta_status"] != "detected" and row["geometric_status"] != "visible"
            for row in observed_targets
        )
        total_rows += len(observed_targets)
        qualified += run_qualified
        detector_visible += run_detector
        geometric_visible += run_geometric
        ambiguous += run_ambiguous
        zero += run_zero
        visibility_runs.append({
            "p2_no_wall_run_id": run_id,
            "source_regime_a_spec_id": spec_id,
            "target_rows": len(observed_targets),
            "qualified_rendered_evidence_rows": run_qualified,
            "detector_visible_rows": run_detector,
            "geometric_visible_rows": run_geometric,
            "ambiguous_or_partial_rows": run_ambiguous,
            "zero_evidence_rows": run_zero,
        })

    path_status = "PASS" if not failures and max_difference == 0.0 else "FAIL"
    write_json(OUT / "p2_path_equivalence_receipt.json", {
        "artifact_id": "regime-a-prime-p2-path-equivalence-receipt-v0.1",
        "epsilon_path": 0.0,
        "path_equivalence_status": path_status,
        "max_path_difference": max_difference,
        "path_failure_count": len(failures),
        "path_trajectories_pass": len(specs) - len(failures),
        "path_trajectories_fail": len(failures),
        "all_capture_rows_checked": sum(len(read_jsonl(CAPTURES / p2_run_id(
            str(spec["trajectory_spec_id"])) / "raw/server_state.jsonl")) for spec in specs),
        "path_rows_checked": len(frozen["rows"]),
        "source_spec_count": len(specs),
        "exact_coordinate_identity_required": True,
        "exact_spec_seed_direction_motion_target_order_timing_required": True,
        "failures": failures,
    })
    if path_status != "PASS":
        print(f"PATH_EQUIVALENCE_STATUS=FAIL failures={len(failures)} max={max_difference}")
        return 1

    # NO_WALL is the positive control: every frozen target must carry rendered
    # detector evidence and agree with geometric visibility. This strict gate is
    # frozen here before capture outcomes and introduces no numerical tolerance.
    visibility_status = (
        "PASS" if total_rows == 475 and qualified == 475 and ambiguous == 0 and zero == 0
        else "FAIL"
    )
    write_json(OUT / "p2_visibility_qualification_receipt.json", {
        "artifact_id": "regime-a-prime-p2-current-visibility-qualification-v0.1",
        "visibility_qualification_status": visibility_status,
        "rule": "all 475 frozen NO_WALL targets must be detector-visible and geometric-visible",
        "detector_thresholds_changed": False,
        "pixel_tolerance_introduced": False,
        "total_frozen_target_rows": total_rows,
        "qualified_rendered_evidence_rows": qualified,
        "detector_visible_rows": detector_visible,
        "geometric_visible_rows": geometric_visible,
        "ambiguous_or_partial_rows": ambiguous,
        "zero_evidence_rows": zero,
        "visibility_trajectories_pass": sum(
            row["qualified_rendered_evidence_rows"] == 19 for row in visibility_runs
        ),
        "visibility_trajectories_fail": sum(
            row["qualified_rendered_evidence_rows"] != 19 for row in visibility_runs
        ),
        "runs": visibility_runs,
    })
    print(f"PATH_EQUIVALENCE_STATUS=PASS max={max_difference}")
    print(f"VISIBILITY_QUALIFICATION_STATUS={visibility_status} qualified={qualified}/475 "
          f"ambiguous={ambiguous} zero={zero}")
    return 0 if visibility_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
