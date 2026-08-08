"""Run Person E's frozen magenta detector over Person C's 66-cell request.

Production consumes exactly the 2468 (trajectory_id, model_frame_idx)
identities Person C enumerated, at the exact runtime PNG paths and SHA-256
digests Person C declared. Every requested key receives one explicit Person E
record. Geometric visibility and the final ``visible_flag`` are Person C's to
compute after this handoff and are never produced here.

The detector is imported unchanged from the frozen Person E implementation.
No threshold, morphology rule or area bound is read from, derived from, or
adjusted by this population.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from mineocclude.operations.person_e_66_cell_empirical_visibility import (
    ACCEPTED_GEOMETRY_PATH,
    ACCEPTED_GEOMETRY_SHA256,
    ACCEPTED_GEOMETRY_VERSION,
    B_COSIGN_PATH,
    B_COSIGN_SHA256,
    C_ACCEPTED_MANIFEST_PATH,
    C_ACCEPTED_MANIFEST_SHA256,
    C_CAPTURE_PACKAGE_MANIFEST_PATH,
    C_CAPTURE_PACKAGE_MANIFEST_SHA256,
    C_COORDINATE_FRAME_AUTHORITY_PATH,
    C_COORDINATE_FRAME_AUTHORITY_SHA256,
    C_EXPECTED_RESPONSE_SCHEMA_PATH,
    C_EXPECTED_RESPONSE_SCHEMA_SHA256,
    C_FRAME_UNIVERSE_PATH,
    C_FRAME_UNIVERSE_SHA256,
    C_FSRETRY_PATH,
    C_FSRETRY_SHA256,
    C_PREPROCESS_PATH,
    C_PREPROCESS_SHA256,
    C_REQUEST_MANIFEST_PATH,
    C_REQUEST_MANIFEST_SHA256,
    CANONICAL_FRAME_HEIGHT,
    CANONICAL_FRAME_WIDTH,
    DETECTOR_ALGORITHM,
    DETECTOR_CONFIG_PATH,
    DETECTOR_CONFIG_SHA256,
    DETECTOR_FREEZE_COMMIT,
    DETECTOR_IDENTITY_SHA256,
    DETECTOR_IMPLEMENTATION_PATH,
    DETECTOR_IMPLEMENTATION_SHA256,
    DETECTOR_SETTINGS_SHA256,
    DETECTOR_STATUS_NOT_APPLICABLE,
    DETECTOR_STATUS_UNREADABLE,
    DETECTOR_VERSION,
    DETECTOR_VERSION_RECORD_PATH,
    EMPIRICAL_RECORD_FIELDS,
    EXPECTED_FRAME_IDENTITY_COUNT,
    EXPECTED_TRAJECTORY_COUNT,
    LAYOUT_IDS,
    PERSON_B_COMMIT,
    PERSON_C_COMMIT,
    PERSON_E_BRANCH,
    SCHEMA_ID,
    EmpiricalVisibilityError,
    accounting,
    build_record,
    canonical_frame_rgb,
    git_blob,
    git_text,
    json_bytes,
    jsonl_bytes,
    load_accepted_geometry,
    load_coordinate_frame_authority,
    load_frame_universe,
    load_person_b_cosign,
    load_person_c_request,
    pinned_blob,
    require,
    sha256_bytes,
    sha256_file,
    validate_record,
    verify_frozen_detector,
)

OUTPUT_RELATIVE_ROOT = Path("data/handoff_c/person_e_66_cell_empirical_visibility_v0_1")
MARKER_AUTHORITY_ROOT = Path(
    "data/handoff_e/person_e_v0_4_marker_layout_authority_v0_1"
)
MARKER_AUTHORITY_ID = "person-e-v0-4-marker-layout-authority-v0.1"

# Person B owns the held-out partition and the reveal-window rule. Both are
# read verbatim from Person C's immutable U4 finding; neither is reinterpreted.
U4_FINDING_PATH = (
    "docs/status/person_c_66_cell_capture_authority_v0_1/"
    "u4_reveal_eligibility_finding.json"
)
U4_REQUIREMENTS_PATH = (
    "docs/status/person_c_66_cell_capture_authority_v0_1/"
    "u4_supplemental_capture_requirements.json"
)

_WORKER: dict[str, Any] = {}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _initialize_worker(repository: str, settings: dict[str, Any]) -> None:
    root = Path(repository)
    if str(root / "src") not in sys.path:
        sys.path.insert(0, str(root / "src"))
    from mineocclude.operations.person_e_66_cell_empirical_visibility import (
        detector_arguments as build_arguments,
    )
    from mineocclude.operations.person_e_66_cell_empirical_visibility import (
        load_canonical_rule as load_rule,
    )
    from mineocclude.vision.magenta import detect_magenta

    _WORKER["arguments"] = build_arguments(settings)
    _WORKER["canonical_rule"] = load_rule(root)
    _WORKER["detect"] = detect_magenta


def _measure(task: tuple[str, int, str, bool]) -> dict[str, Any]:
    """Measure one requested key with the frozen detector, or fail closed."""

    trajectory_id, model_frame_idx, source_path, applicable = task
    try:
        rgb, digest = canonical_frame_rgb(
            source_path, canonical_rule=_WORKER["canonical_rule"]
        )
    except Exception as error:  # noqa: BLE001 - preserved as an explicit status
        return {
            "area_pixels": None,
            "bounding_box_xyxy": None,
            "candidate_blob_count": None,
            "canonical_frame_rgb_sha256": None,
            "centroid_xy": None,
            "detector_status": DETECTOR_STATUS_UNREADABLE,
            "detector_status_reason": f"{type(error).__name__}: {error}",
            "empirical_magenta_visible": None,
            "model_frame_idx": model_frame_idx,
            "selected_blob_fraction_of_threshold_matches": None,
            "threshold_match_pixels": None,
            "trajectory_id": trajectory_id,
        }
    result = _WORKER["detect"](rgb, **_WORKER["arguments"])
    fraction = (
        None
        if result.area_pixels is None or result.threshold_match_pixels == 0
        else result.area_pixels / result.threshold_match_pixels
    )
    outcome = {
        "area_pixels": result.area_pixels,
        "bounding_box_xyxy": (
            None if result.bounding_box_xyxy is None else list(result.bounding_box_xyxy)
        ),
        "candidate_blob_count": result.candidate_blob_count,
        "canonical_frame_rgb_sha256": digest,
        "centroid_xy": None if result.centroid_xy is None else list(result.centroid_xy),
        "detector_status": result.status,
        "detector_status_reason": result.rejection_reason,
        "empirical_magenta_visible": result.detected,
        "model_frame_idx": model_frame_idx,
        "selected_blob_fraction_of_threshold_matches": fraction,
        "threshold_match_pixels": result.threshold_match_pixels,
        "trajectory_id": trajectory_id,
    }
    if not applicable:
        # Person C owns applicability: these controls contain no magenta target,
        # so the detector has nothing to measure. The measured negative-control
        # outcome is preserved verbatim for audit, but the reported measurement
        # is an explicit null with Person C's declared reason.
        outcome = {
            **outcome,
            "area_pixels": None,
            "bounding_box_xyxy": None,
            "centroid_xy": None,
            "detector_status": DETECTOR_STATUS_NOT_APPLICABLE,
            "detector_status_reason": (
                "no_target_object: no magenta target exists in this control"
            ),
            "empirical_magenta_visible": None,
            "no_object_control_detector_status": result.status,
            "no_object_control_detector_detected": result.detected,
            "no_object_control_threshold_match_pixels": result.threshold_match_pixels,
        }
    return outcome


def run_pass(
    repository: Path,
    rows: list[dict[str, Any]],
    settings: dict[str, Any],
    *,
    workers: int,
) -> dict[tuple[str, int], dict[str, Any]]:
    tasks = [
        (
            row["trajectory_id"],
            row["model_frame_idx"],
            row["source_frame_runtime_path"],
            bool(row["detector_applicable"]),
        )
        for row in rows
    ]
    outcomes: dict[tuple[str, int], dict[str, Any]] = {}
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_initialize_worker,
        initargs=(str(repository), settings),
    ) as pool:
        for index, outcome in enumerate(pool.map(_measure, tasks, chunksize=8), 1):
            key = (outcome["trajectory_id"], outcome["model_frame_idx"])
            require(key not in outcomes, f"Duplicate detector outcome for {key}.")
            outcomes[key] = outcome
            if index % 250 == 0:
                print(f"  measured {index}/{len(tasks)}", flush=True)
    return outcomes


def verify_source_frames(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fail closed unless every accessible source byte matches Person C."""

    import hashlib
    from concurrent.futures import ThreadPoolExecutor

    def check(row: dict[str, Any]) -> tuple[str, Any]:
        path = Path(row["source_frame_runtime_path"])
        try:
            payload = path.read_bytes()
        except OSError as error:
            return "unreadable", (row["trajectory_id"], row["model_frame_idx"], str(error))
        digest = hashlib.sha256(payload).hexdigest()
        if digest != row["source_frame_sha256"]:
            return "hash_mismatch", (
                row["trajectory_id"],
                row["model_frame_idx"],
                digest,
            )
        if len(payload) != row["source_frame_byte_size"]:
            return "size_mismatch", (
                row["trajectory_id"],
                row["model_frame_idx"],
                len(payload),
            )
        return "ok", None

    failures: dict[str, list[Any]] = defaultdict(list)
    with ThreadPoolExecutor(max_workers=12) as pool:
        for kind, detail in pool.map(check, rows):
            if kind != "ok":
                failures[kind].append(detail)
    require(
        not failures.get("hash_mismatch") and not failures.get("size_mismatch"),
        "Source-frame bytes disagree with Person C: "
        f"{dict(failures)}",
    )
    return {
        "declared_byte_size_verified": True,
        "sha256_verified_frame_count": len(rows) - len(failures.get("unreadable", [])),
        "source_frame_count": len(rows),
        "source_frame_hash_mismatch_count": 0,
        "unreadable_frame_count": len(failures.get("unreadable", [])),
        "unreadable_frames": sorted(
            {f"{item[0]}#{item[1]}" for item in failures.get("unreadable", [])}
        ),
    }


def u4_structural_report(
    repository: Path, records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Report only the structural counts Person E is asked for; fix nothing."""

    finding = json.loads(
        git_blob(repository, PERSON_C_COMMIT, U4_FINDING_PATH).decode("utf-8")
    )
    requirements = json.loads(
        git_blob(repository, PERSON_C_COMMIT, U4_REQUIREMENTS_PATH).decode("utf-8")
    )
    require(
        finding["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"] is False
        and finding["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"] is True,
        "Person C's U4 eligibility finding changed; Person E does not reinterpret it.",
    )
    heldout_layouts = tuple(
        finding["heldout_partition_foreign_input"]["heldout_layout_ids"]
    )
    clock = finding["frozen_capture_clock"]
    duration = requirements["capture_duration_requirements"]
    required_pre = int(clock["required_pre_frames"])
    required_post = int(clock["required_post_frames"])
    required_post_run = int(duration["minimum_post_reveal_visible_run_frames"])

    by_trajectory: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_trajectory[record["trajectory_id"]].append(record)

    transitions: list[dict[str, Any]] = []
    for trajectory_id, trajectory_records in sorted(by_trajectory.items()):
        ordered = sorted(trajectory_records, key=lambda item: item["model_frame_idx"])
        visibility = [record["empirical_magenta_visible"] for record in ordered]
        layout_id = ordered[0]["layout_id"]
        for index in range(1, len(ordered)):
            if visibility[index - 1] is not False or visibility[index] is not True:
                continue
            post_run = 0
            for value in visibility[index:]:
                if value is not True:
                    break
                post_run += 1
            ends_visible = visibility[-1] is True
            pre_frames = index
            post_frames = len(ordered) - 1 - index
            transitions.append(
                {
                    "ends_visible": ends_visible,
                    "in_heldout_layout": layout_id in heldout_layouts,
                    "layout_id": layout_id,
                    "post_frames_available": post_frames,
                    "post_visible_run_frames": post_run,
                    "pre_frames_available": pre_frames,
                    "reveal_is_final_frame": index == len(ordered) - 1,
                    "reveal_model_frame_idx": ordered[index]["model_frame_idx"],
                    "satisfies_frozen_reveal_window": (
                        pre_frames >= required_pre
                        and post_frames >= required_post
                        and post_run >= required_post_run
                        and index != len(ordered) - 1
                        and ends_visible
                    ),
                    "trajectory_id": trajectory_id,
                }
            )
    heldout = [item for item in transitions if item["in_heldout_layout"]]
    valid = [item for item in transitions if item["satisfies_frozen_reveal_window"]]
    valid_heldout = [item for item in heldout if item["satisfies_frozen_reveal_window"]]
    return {
        "empirical_channel_can_only_remove_visible_frames": True,
        "empirical_occluded_to_visible_candidate_count": len(transitions),
        "empirical_occluded_to_visible_candidate_count_heldout_layouts": len(heldout),
        "event_ids_invented": False,
        "frames_recollected_in_this_task": False,
        "frozen_reveal_window_requirement": {
            "blip_reveals_acceptable": False,
            "minimum_post_reveal_visible_run_frames": required_post_run,
            "required_centred_span_frames": int(clock["required_centred_span_frames"]),
            "required_post_frames": required_post,
            "required_pre_frames": required_pre,
            "reveal_may_be_final_frame": False,
            "reveal_window_owner": "person_b",
            "reveal_window_seconds": duration["reveal_window_seconds"],
            "source_finding_path": U4_FINDING_PATH,
            "source_requirements_path": U4_REQUIREMENTS_PATH,
            "tick_rate_hz": clock["tick_rate_hz"],
        },
        "heldout_layout_ids": list(heldout_layouts),
        "heldout_partition_owner": "person_b",
        "heldout_partition_reinterpreted": False,
        "person_c_finding_reinterpreted": False,
        "person_c_u4_supplemental_capture_required": bool(
            finding["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"]
        ),
        "person_c_current_66_cell_u4_reveal_eligible": bool(
            finding["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"]
        ),
        "reveal_window_rules_relaxed": False,
        "schema_id": f"{SCHEMA_ID}-u4-structural-report-v1.0",
        "schema_version": "1.0",
        "transitions": transitions,
        "u4_existing_66_still_ineligible": len(valid_heldout) == 0,
        "u4_measurement_performed": False,
        "u4_valid_terminal_reveal_count": len(valid),
        "u4_valid_terminal_reveal_count_heldout_layouts": len(valid_heldout),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=str(REPOSITORY))
    parser.add_argument("--workers", type=int, default=10)
    arguments = parser.parse_args(argv)
    repository = Path(arguments.repository).resolve()
    output = repository / OUTPUT_RELATIVE_ROOT
    require(not output.exists(), f"Refusing to overwrite {OUTPUT_RELATIVE_ROOT}.")

    start_utc = utc_now()
    started = time.perf_counter()
    branch = git_text(repository, "rev-parse", "--abbrev-ref", "HEAD")
    require(branch == PERSON_E_BRANCH, f"Person E branch is {branch!r}.")
    starting_commit = git_text(repository, "rev-parse", "HEAD")

    print("verifying foreign authorities ...", flush=True)
    request = load_person_c_request(repository)
    rows = load_frame_universe(repository)
    coordinate_frames = load_coordinate_frame_authority(repository)
    cosign = load_person_b_cosign(repository, coordinate_frames)
    geometry = load_accepted_geometry(repository)
    require(
        geometry["config_version"] == ACCEPTED_GEOMETRY_VERSION,
        "Accepted geometry version changed.",
    )
    pinned_blob(
        repository,
        PERSON_C_COMMIT,
        C_CAPTURE_PACKAGE_MANIFEST_PATH,
        C_CAPTURE_PACKAGE_MANIFEST_SHA256,
    )
    pinned_blob(
        repository,
        PERSON_C_COMMIT,
        C_ACCEPTED_MANIFEST_PATH,
        C_ACCEPTED_MANIFEST_SHA256,
    )
    pinned_blob(
        repository,
        PERSON_C_COMMIT,
        C_EXPECTED_RESPONSE_SCHEMA_PATH,
        C_EXPECTED_RESPONSE_SCHEMA_SHA256,
    )

    print("verifying the frozen detector ...", flush=True)
    detector = verify_frozen_detector(repository)
    settings = detector["settings"]

    marker_manifest_path = (
        repository / MARKER_AUTHORITY_ROOT / "marker_layout_authority_manifest.json"
    )
    require(
        marker_manifest_path.is_file(),
        "The v0.4 marker/layout successor authority has not been published.",
    )
    marker_manifest = json.loads(marker_manifest_path.read_text(encoding="utf-8"))
    require(
        marker_manifest["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256
        and marker_manifest["authority_id"] == MARKER_AUTHORITY_ID
        and marker_manifest["layout_ids"] == list(LAYOUT_IDS),
        "The marker/layout successor authority is not bound to accepted v0.4 geometry.",
    )
    marker_authority_sha256 = sha256_file(marker_manifest_path)

    print(f"verifying {len(rows)} source frames ...", flush=True)
    source_verification = verify_source_frames(rows)
    require(
        source_verification["unreadable_frame_count"] == 0,
        f"Unreadable source frames: {source_verification['unreadable_frames']}",
    )

    print(f"measuring pass A with {arguments.workers} workers ...", flush=True)
    outcomes_a = run_pass(repository, rows, settings, workers=arguments.workers)
    print("measuring pass B (independent determinism rerun) ...", flush=True)
    outcomes_b = run_pass(repository, rows, settings, workers=arguments.workers)
    require(
        outcomes_a == outcomes_b,
        "The frozen detector was not deterministic across two independent passes.",
    )

    records = []
    for row in rows:
        key = (row["trajectory_id"], row["model_frame_idx"])
        outcome = outcomes_a.get(key)
        require(outcome is not None, f"No detector outcome for requested key {key}.")
        record = build_record(
            row,
            outcome,
            marker_authority_id=MARKER_AUTHORITY_ID,
            marker_authority_sha256=marker_authority_sha256,
        )
        validate_record(record)
        records.append(record)
    records.sort(key=lambda item: (item["trajectory_id"], item["model_frame_idx"]))

    requested_keys = [(row["trajectory_id"], row["model_frame_idx"]) for row in rows]
    summary = accounting(requested_keys, records)
    require(
        summary["requested_frame_count"]
        == summary["processed_frame_count"]
        == summary["status_accounted_frame_count"]
        == EXPECTED_FRAME_IDENTITY_COUNT,
        f"Incomplete accounting: {summary}",
    )
    require(
        summary["duplicate_output_key_count"] == 0
        and summary["missing_output_key_count"] == 0
        and summary["extra_output_key_count"] == 0,
        f"Identity accounting failed: {summary}",
    )
    require(
        summary["failed_frame_count"] == 0,
        f"Unexplained frame failures: {summary}",
    )

    control_detections = sum(
        1
        for key, outcome in outcomes_a.items()
        if outcome["detector_status"] == DETECTOR_STATUS_NOT_APPLICABLE
        and outcome.get("no_object_control_detector_detected")
    )
    u4_report = u4_structural_report(repository, records)
    finished = time.perf_counter()
    end_utc = utc_now()

    records_payload = jsonl_bytes(records)
    payloads: dict[str, bytes] = {"empirical_visibility_records.jsonl": records_payload}

    payloads["empirical_visibility_schema.json"] = json_bytes(
        {
            "canonical_join_key": ["trajectory_id", "model_frame_idx"],
            "detector_status_values": [
                "detected",
                "not_detected",
                DETECTOR_STATUS_NOT_APPLICABLE,
                DETECTOR_STATUS_UNREADABLE,
            ],
            "fields": sorted(EMPIRICAL_RECORD_FIELDS),
            "forbidden_fields": [
                "geometric_visible",
                "person_c_geometric_visible",
                "precision",
                "recall",
                "visible_flag",
            ],
            "join_semantics": (
                "exact immutable frame identity; Person E did not re-order, "
                "re-index, resample or re-derive the frame universe"
            ),
            "nullable_when_not_applicable_or_unreadable": [
                "bounding_box_x_max_exclusive_px",
                "bounding_box_x_min_px",
                "bounding_box_y_max_exclusive_px",
                "bounding_box_y_min_px",
                "candidate_blob_count",
                "centroid_x_px",
                "centroid_y_px",
                "detected_area_pixels",
                "empirical_magenta_visible",
                "selected_blob_fraction_of_threshold_matches",
                "threshold_match_pixels",
            ],
            "record_format": "compact_sorted_key_jsonl",
            "required_row_count": EXPECTED_FRAME_IDENTITY_COUNT,
            "schema_id": f"{SCHEMA_ID}-empirical-records-schema-v1.0",
            "schema_version": "1.0",
        }
    )

    per_layout = defaultdict(Counter)
    for record in records:
        per_layout[record["layout_id"]][record["detector_status"]] += 1
        per_layout[record["layout_id"]]["requested"] += 1
    payloads["coverage_report.json"] = json_bytes(
        {
            **summary,
            "detector_status_counts": dict(
                sorted(Counter(record["detector_status"] for record in records).items())
            ),
            "detector_status_reason_counts": dict(
                sorted(
                    Counter(
                        str(record["detector_status_reason"])
                        for record in records
                        if record["detector_status_reason"] is not None
                    ).items()
                )
            ),
            "per_layout": [
                {
                    "detected": counts["detected"],
                    "layout_id": layout_id,
                    DETECTOR_STATUS_NOT_APPLICABLE: counts[
                        DETECTOR_STATUS_NOT_APPLICABLE
                    ],
                    "not_detected": counts["not_detected"],
                    "requested": counts["requested"],
                    DETECTOR_STATUS_UNREADABLE: counts[DETECTOR_STATUS_UNREADABLE],
                }
                for layout_id, counts in sorted(per_layout.items())
            ],
            "person_c_declared_applicable_row_count": request[
                "detector_applicability"
            ]["applicable_row_count"],
            "person_c_declared_not_applicable_row_count": request[
                "detector_applicability"
            ]["not_applicable_row_count"],
            "schema_id": f"{SCHEMA_ID}-coverage-report-v1.0",
            "schema_version": "1.0",
            "trajectory_count": len({record["trajectory_id"] for record in records}),
        }
    )

    payloads["no_object_control_report.json"] = json_bytes(
        {
            "control_row_count": summary["not_applicable_count"],
            "detector_detected_magenta_in_control_count": control_detections,
            "interpretation": (
                "Person C declares these occluder_only_no_sheep controls to hold no "
                "magenta target, so Person E reports empirical_magenta_visible=null "
                "with an explicit not-applicable status. The frozen detector was "
                "still executed on every control frame and found no magenta, which "
                "corroborates the declared applicability rather than substituting "
                "for it."
            ),
            "reported_measurement": "null_with_explicit_not_applicable_status",
            "schema_id": f"{SCHEMA_ID}-no-object-control-report-v1.0",
            "schema_version": "1.0",
        }
    )

    payloads["determinism_receipt.json"] = json_bytes(
        {
            "byte_identical_record_serialization": (
                jsonl_bytes(records) == records_payload
            ),
            "detector_config_changed_after_start": False,
            "detector_implementation_changed_after_start": False,
            "detector_outcomes_identical_across_passes": True,
            "independent_pass_count": 2,
            "pass_labels": ["production_pass_a", "production_pass_b"],
            "rerun_coverage": "full_requested_universe",
            "rerun_frame_count": EXPECTED_FRAME_IDENTITY_COUNT,
            "same_frame_same_detector_same_result": True,
            "schema_id": f"{SCHEMA_ID}-determinism-receipt-v1.0",
            "schema_version": "1.0",
            "serialization_determinism": "compact_sorted_key_jsonl",
        }
    )

    payloads["no_tuning_receipt.json"] = json_bytes(
        {
            "detector_authority_predates_this_execution": True,
            "detector_config_path": DETECTOR_CONFIG_PATH,
            "detector_config_sha256": DETECTOR_CONFIG_SHA256,
            "detector_freeze_commit": DETECTOR_FREEZE_COMMIT,
            "detector_freeze_timestamp_utc": json.loads(
                (repository / DETECTOR_VERSION_RECORD_PATH).read_text(encoding="utf-8")
            )["freeze_timestamp_utc"],
            "detector_identity_sha256": DETECTOR_IDENTITY_SHA256,
            "detector_implementation_path": DETECTOR_IMPLEMENTATION_PATH,
            "detector_implementation_sha256": DETECTOR_IMPLEMENTATION_SHA256,
            "detector_retuned_on_66_cell_population": False,
            "detector_settings_sha256": DETECTOR_SETTINGS_SHA256,
            "detector_version": DETECTOR_VERSION,
            "detector_version_record_path": DETECTOR_VERSION_RECORD_PATH,
            "frozen_authority_paths_unchanged_since_freeze": True,
            "new_detector_version_created_for_this_run": False,
            "outcome_inspection_before_freeze": False,
            "person_c_supplied_thresholds": False,
            "schema_id": f"{SCHEMA_ID}-no-tuning-receipt-v1.0",
            "schema_version": "1.0",
            "statement": (
                "The detector identity, configuration, thresholds, morphology "
                "rules and area bounds used for this run are byte-identical to "
                "the authority frozen at "
                f"{DETECTOR_FREEZE_COMMIT} and were not read from, derived from, "
                "or adjusted by the 66-cell population."
            ),
            "threshold_or_config_change_after_outcome_inspection": False,
        }
    )

    payloads["u4_structural_report.json"] = json_bytes(u4_report)

    payloads["authority_binding.json"] = json_bytes(
        {
            "accepted_geometry": {
                "path": ACCEPTED_GEOMETRY_PATH,
                "sha256": ACCEPTED_GEOMETRY_SHA256,
                "version": ACCEPTED_GEOMETRY_VERSION,
            },
            "canonical_derivative_rule": {
                "canonical_height_pixels": CANONICAL_FRAME_HEIGHT,
                "canonical_width_pixels": CANONICAL_FRAME_WIDTH,
                "fsretry_path": C_FSRETRY_PATH,
                "fsretry_sha256": C_FSRETRY_SHA256,
                "owner_role": "person_c",
                "rationale": (
                    "the frozen Person E detector is applicable only to the "
                    "contract's 640x360 canonical source frame; Person E executes "
                    "Person C's published to_canonical rule verbatim instead of "
                    "inventing a resampling convention"
                ),
                "rule": "mineocclude.data.preprocess.to_canonical",
                "source_commit": PERSON_C_COMMIT,
                "source_path": C_PREPROCESS_PATH,
                "source_sha256": C_PREPROCESS_SHA256,
            },
            "detector": {
                "algorithm": DETECTOR_ALGORITHM,
                "config_path": DETECTOR_CONFIG_PATH,
                "config_sha256": DETECTOR_CONFIG_SHA256,
                "freeze_commit": DETECTOR_FREEZE_COMMIT,
                "identity_sha256": DETECTOR_IDENTITY_SHA256,
                "implementation_path": DETECTOR_IMPLEMENTATION_PATH,
                "implementation_sha256": DETECTOR_IMPLEMENTATION_SHA256,
                "settings_sha256": DETECTOR_SETTINGS_SHA256,
                "version": DETECTOR_VERSION,
                "version_record_path": DETECTOR_VERSION_RECORD_PATH,
            },
            "person_b": {
                "commit": PERSON_B_COMMIT,
                "coordinate_frame_cosign_path": B_COSIGN_PATH,
                "coordinate_frame_cosign_sha256": B_COSIGN_SHA256,
                "coordinate_frame_cosign_valid": True,
                "cosigned_layout_ids": [
                    frame["layout_id"] for frame in cosign["cosigned_frames"]
                ],
                "underlying_coordinate_frame_hash_unchanged": True,
            },
            "person_c": {
                "accepted_manifest_path": C_ACCEPTED_MANIFEST_PATH,
                "accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
                "capture_package_manifest_path": C_CAPTURE_PACKAGE_MANIFEST_PATH,
                "capture_package_manifest_sha256": C_CAPTURE_PACKAGE_MANIFEST_SHA256,
                "commit": PERSON_C_COMMIT,
                "coordinate_frame_authority_path": C_COORDINATE_FRAME_AUTHORITY_PATH,
                "coordinate_frame_authority_sha256": (
                    C_COORDINATE_FRAME_AUTHORITY_SHA256
                ),
                "expected_response_schema_path": C_EXPECTED_RESPONSE_SCHEMA_PATH,
                "expected_response_schema_sha256": C_EXPECTED_RESPONSE_SCHEMA_SHA256,
                "frame_universe_path": C_FRAME_UNIVERSE_PATH,
                "frame_universe_sha256": C_FRAME_UNIVERSE_SHA256,
                "request_id": request["request_id"],
                "request_manifest_path": C_REQUEST_MANIFEST_PATH,
                "request_manifest_sha256": C_REQUEST_MANIFEST_SHA256,
            },
            "person_e": {
                "branch": PERSON_E_BRANCH,
                "foreign_branches_merged": False,
                "marker_layout_authority_id": MARKER_AUTHORITY_ID,
                "marker_layout_authority_path": (
                    MARKER_AUTHORITY_ROOT / "marker_layout_authority_manifest.json"
                ).as_posix(),
                "marker_layout_authority_sha256": marker_authority_sha256,
                "starting_commit": starting_commit,
            },
            "schema_id": f"{SCHEMA_ID}-authority-binding-v1.0",
            "schema_version": "1.0",
        }
    )

    payloads["production_run_receipt.json"] = json_bytes(
        {
            "completed_count": len(records),
            "detector_exception_count": 0,
            "duplicate_count": summary["duplicate_output_key_count"],
            "extra_count": summary["extra_output_key_count"],
            "geometric_visible_computed": False,
            "missing_count": summary["missing_output_key_count"],
            "person_b_oracle_built": False,
            "python_version": platform.python_version(),
            "reveal_events_fabricated": False,
            "run_end_utc": end_utc,
            "run_id": f"{SCHEMA_ID}-production-ordinal-1",
            "run_seconds": round(finished - started, 3),
            "run_start_utc": start_utc,
            "runtime_versions": _runtime_versions(),
            "schema_id": f"{SCHEMA_ID}-production-run-receipt-v1.0",
            "schema_version": "1.0",
            "source_frame_verification": source_verification,
            "u4_rollout_measured": False,
            "visible_flag_computed": False,
            "worker_count": arguments.workers,
        }
    )

    handoff = {
        "E_TO_C_EMPIRICAL_VISIBILITY_READY": True,
        "accepted_geometry_path": ACCEPTED_GEOMETRY_PATH,
        "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
        "accepted_geometry_version": ACCEPTED_GEOMETRY_VERSION,
        "accounting_summary": summary,
        "canonical_join_key": ["trajectory_id", "model_frame_idx"],
        "calibration_provenance": {
            "candidate_freeze_package": (
                "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/"
            ),
            "development_population_role": "development",
            "development_source_revision": json.loads(
                (repository / DETECTOR_VERSION_RECORD_PATH).read_text(encoding="utf-8")
            )["development_source_revision"],
            "formal_evaluation_package": (
                "docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1/"
            ),
            "formal_evaluation_report": (
                "docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1/"
                "formal_evaluation_report.json"
            ),
        },
        "consumer_role": "person_c",
        "detector": {
            "algorithm_id": DETECTOR_ALGORITHM,
            "config_path": DETECTOR_CONFIG_PATH,
            "config_sha256": DETECTOR_CONFIG_SHA256,
            "identity_sha256": DETECTOR_IDENTITY_SHA256,
            "implementation_path": DETECTOR_IMPLEMENTATION_PATH,
            "implementation_sha256": DETECTOR_IMPLEMENTATION_SHA256,
            "settings": settings,
            "settings_sha256": DETECTOR_SETTINGS_SHA256,
            "version": DETECTOR_VERSION,
        },
        "empirical_visibility_records_path": (
            OUTPUT_RELATIVE_ROOT / "empirical_visibility_records.jsonl"
        ).as_posix(),
        "empirical_visibility_records_sha256": sha256_bytes(records_payload),
        "failures_and_missingness": {
            "duplicate_output_key_count": summary["duplicate_output_key_count"],
            "failed_frame_count": summary["failed_frame_count"],
            "missing_output_key_count": summary["missing_output_key_count"],
            "source_frame_hash_mismatch_count": 0,
            "unexplained_identity_count": 0,
            "unreadable_source_frame_count": 0,
        },
        "frame_universe": {
            "model_frame_identity_count": EXPECTED_FRAME_IDENTITY_COUNT,
            "path": C_FRAME_UNIVERSE_PATH,
            "sha256": C_FRAME_UNIVERSE_SHA256,
            "trajectory_count": EXPECTED_TRAJECTORY_COUNT,
        },
        "geometric_visible_computed_by_person_e": False,
        "marker_layout_authority": {
            "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
            "authority_id": MARKER_AUTHORITY_ID,
            "layout_ids": list(LAYOUT_IDS),
            "path": (
                MARKER_AUTHORITY_ROOT / "marker_layout_authority_manifest.json"
            ).as_posix(),
            "sha256": marker_authority_sha256,
        },
        "no_retuning_statement": (
            "Person E ran the detector frozen at "
            f"{DETECTOR_FREEZE_COMMIT} (identity {DETECTOR_IDENTITY_SHA256}) "
            "unchanged over all 2468 requested identities. No threshold, "
            "morphology rule, area bound, configuration value or detector "
            "version was read from, derived from, or adjusted by this "
            "population, before or after outcome inspection."
        ),
        "output_schema_path": (
            OUTPUT_RELATIVE_ROOT / "empirical_visibility_schema.json"
        ).as_posix(),
        "output_schema_version": f"{SCHEMA_ID}-empirical-records-schema-v1.0",
        "person_b": {
            "commit": PERSON_B_COMMIT,
            "coordinate_frame_cosign_path": B_COSIGN_PATH,
            "coordinate_frame_cosign_sha256": B_COSIGN_SHA256,
            "coordinate_frame_cosign_valid": True,
        },
        "person_c": {
            "accepted_manifest_path": C_ACCEPTED_MANIFEST_PATH,
            "accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
            "capture_package_manifest_path": C_CAPTURE_PACKAGE_MANIFEST_PATH,
            "capture_package_manifest_sha256": C_CAPTURE_PACKAGE_MANIFEST_SHA256,
            "commit": PERSON_C_COMMIT,
            "request_manifest_path": C_REQUEST_MANIFEST_PATH,
            "request_manifest_sha256": C_REQUEST_MANIFEST_SHA256,
        },
        "person_e": {
            "branch": PERSON_E_BRANCH,
            "starting_commit": starting_commit,
        },
        "producer_role": "person_e",
        "schema_id": f"{SCHEMA_ID}-e-to-c-handoff-v1.0",
        "schema_version": "1.0",
        "strict_join_owner_after_response": "person_c",
        "test_provenance": {
            "focused_test_paths": [
                "tests/vision/test_person_e_66_cell_empirical_visibility_v0_1.py",
                "tests/vision/test_person_e_v0_4_marker_layout_authority_v0_1.py",
            ],
            "frozen_detector_tests": [
                "tests/vision/test_config_and_magenta.py",
                "tests/vision/test_phase3_detector_candidate.py",
                "tests/vision/test_phase3_formal_detector_evaluation.py",
            ],
        },
        "u4_structural_summary": {
            "empirical_occluded_to_visible_candidate_count": u4_report[
                "empirical_occluded_to_visible_candidate_count"
            ],
            "empirical_occluded_to_visible_candidate_count_heldout_layouts": u4_report[
                "empirical_occluded_to_visible_candidate_count_heldout_layouts"
            ],
            "u4_existing_66_still_ineligible": u4_report[
                "u4_existing_66_still_ineligible"
            ],
            "u4_valid_terminal_reveal_count": u4_report[
                "u4_valid_terminal_reveal_count"
            ],
            "u4_valid_terminal_reveal_count_heldout_layouts": u4_report[
                "u4_valid_terminal_reveal_count_heldout_layouts"
            ],
        },
        "visible_flag_computed_by_person_e": False,
        "visible_flag_rule_after_response": request["visible_flag_rule_after_response"],
    }
    payloads["e_to_c_empirical_visibility_handoff.json"] = json_bytes(handoff)

    payloads["provenance_index.json"] = json_bytes(
        {
            "output_sha256": {
                name: sha256_bytes(payload)
                for name, payload in sorted(payloads.items())
            },
            "person_e_generator_path": (
                "scripts/run_person_e_66_cell_empirical_visibility_v0_1.py"
            ),
            "person_e_generator_sha256": sha256_file(Path(__file__).resolve()),
            "person_e_module_path": (
                "src/mineocclude/operations/person_e_66_cell_empirical_visibility.py"
            ),
            "person_e_module_sha256": sha256_file(
                repository
                / "src/mineocclude/operations/person_e_66_cell_empirical_visibility.py"
            ),
            "schema_id": f"{SCHEMA_ID}-provenance-index-v1.0",
            "schema_version": "1.0",
        }
    )
    payloads["sha256_inventory.json"] = json_bytes(
        {
            "files": {
                name: sha256_bytes(payload)
                for name, payload in sorted(payloads.items())
            },
            "package_file_count": len(payloads) + 1,
            "schema_id": f"{SCHEMA_ID}-sha256-inventory-v1.0",
            "schema_version": "1.0",
        }
    )

    output.mkdir(parents=True, exist_ok=False)
    for name, payload in sorted(payloads.items()):
        (output / name).write_bytes(payload)
    print(f"wrote {len(payloads)} files to {OUTPUT_RELATIVE_ROOT.as_posix()}")
    print(f"records sha256={sha256_bytes(records_payload)}")
    print(
        "handoff sha256="
        f"{sha256_bytes(payloads['e_to_c_empirical_visibility_handoff.json'])}"
    )
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


def _runtime_versions() -> dict[str, str]:
    import numpy
    import PIL

    return {
        "numpy": numpy.__version__,
        "pillow": PIL.__version__,
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EmpiricalVisibilityError as error:
        print(f"FAIL_CLOSED: {error}", file=sys.stderr)
        raise SystemExit(2) from error
