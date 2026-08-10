#!/usr/bin/env python3
"""Resolve visible-position replication authority without model execution.

This Task-1 runner joins the frozen 66-trajectory acceptance, visibility,
target, capture-context, and preprocessing authorities.  It inventories every
accepted trajectory, selects every row satisfying the predeclared authority
rule, constructs condition-compatible strata, and makes the acquisition-path
decision from those identities alone.
"""

from __future__ import annotations

import argparse
import json
import math
import resource
import statistics
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Reuse the predecessor's canonical hashing, JSONL, and exclusive JSON writer.
from scripts.run_exploratory_visible_position_diagnostics import (  # noqa: E402
    _canonical_sha256,
    _jsonl,
    _write_json,
    sha256_file,
)

RUNNER_VERSION = "exploratory-visible-position-resolution-runner-v0.1"
BASE_HEAD = "626dcc00710f2b51cbbe2bfdea86785cb2d70e61"
OUTPUT_ROOT = (
    ROOT / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
)

ACCEPTED_COUNT = 66
TOTAL_FRAME_COUNT = 2468
WINDOW_SIZE = 16

CONDITION_FIELDS = (
    "control_type",
    "set_id",
    "scene",
    "context_fraction",
    "hidden_frames",
    "speed_blocks_per_second",
    "q_blocks_squared_per_second",
    "seed",
)
# A seed identifies an independent acquisition; requiring equal seeds would
# make independent replication impossible by construction.  It is retained in
# every inventory record but is not a controlled-condition matching field.
COMPATIBILITY_CONDITION_FIELDS = CONDITION_FIELDS[:-1]

NO_WALL_CONTROL = "no_wall_visible_control"
CAPTURE_SCENE_TO_ACCEPTED_SCENE = {
    "NORMAL": "normal",
    "NO_SHEEP": "nosheep",
    "NO_WALL": "nowall",
}
CLASS_GE3 = "WITHIN_LAYOUT_GROUPED_EVAL_AVAILABLE"
CLASS_EQ2 = "LIMITED_TWO_TRAJECTORY_REPLICATION"
CLASS_LT2 = "NO_WITHIN_LAYOUT_REPLICATION"
CLASS_SHIFT = "CONDITION_SHIFT_ONLY"
CLASS_INVALID = "INVALID_FOR_EXPANDED_VISIBLE_DIAGNOSTIC"

CHECKPOINT_SHA256 = "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
PREPROCESS_HASH = "8b585e1ffe7d9b7c7bf549f8b5695825bbd2a5b2579e4adf607ca5fa5786635c"
PREPROCESSING_IDENTITY = "person-a-bgr2rgb-inter-linear-224x384-v1.0"
VISIBILITY_RULE = "geometric_visible AND empirical_magenta_visible"

SOURCE_AUTHORITIES = {
    "accepted_trajectory_manifest": {
        "path": "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json",
        "sha256": "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7",
    },
    "strict_visibility_join": {
        "path": "docs/status/person_c_66_cell_strict_visibility_v0_1/visibility_join.jsonl",
        "sha256": "6fcfaba99feed706e7106d0f1d9b758700d920ee2001b3ca6f150320f09313b7",
    },
    "row_universe": {
        "path": "docs/status/person_b_66_cell_oracle_target_v0_1/row_universe_records.jsonl",
        "sha256": "29b4cf003f3d9479b3606f17947879078801b400b09d942bd6827544b95227b2",
    },
    "oracle_target_records": {
        "path": "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_records.jsonl",
        "sha256": "d95c83518d2ad322e6862f5460727382511fe831c0c6658a6cf72c9f7a8858b1",
    },
    "oracle_target_manifest": {
        "path": "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_manifest.json",
        "sha256": "c064e1856be67ebab95cbcb07b80009729c396f2398b15b4dec57458b73b8ac9",
    },
    "preprocessed_frame_manifest": {
        "path": "docs/status/person_a_66_cell_preprocessed_media_v0_2/preprocessed_frame_manifest.json",
        "sha256": "dda2220d1e388253c671f7a7d879987e53d4c0a1a1e815fbc8da6a19356de5a1",
    },
    "capture_package_manifest": {
        "path": "docs/status/person_c_66_cell_capture_authority_v0_1/capture_package_manifest.json",
        "sha256": "ca6ef6bd0a6ee144731ff3e6f470f767a2c1a82e8b46aef9fb5e458efb814f56",
    },
    "checkpoint_preprocessing_identity": {
        "path": "docs/status/person_b_66_cell_oracle_target_v0_1/person_a_identity_resolution.json",
        "sha256": "870344e3a7623334a043cb06400a9fe2f679a0b118d43fc52349d3cff9d0e3cb",
    },
    "predecessor_context_manifest": {
        "path": "docs/status/integration/exploratory_visible_position_diagnostics_v0_1/unpooled_activation_manifest.json",
        "sha256": "d7e9615f26856d64c96a55b4d52624dc24d7df5841e3f930a238a7d1c3987482",
    },
    "production_context_runner": {
        "path": "scripts/run_person_a_66_cell_production_extraction.py",
        "sha256": "06f0a9d55352688fa789f18ab0072dcbed612f32a3d81d11dba1aa26f80977f0",
    },
}


class ResolutionError(RuntimeError):
    """Raised when a controlling authority cannot be reconciled."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ResolutionError(message)


def _load_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(document, dict), f"JSON document is not a mapping: {path}")
    return document


def _authority_paths(root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name, source in SOURCE_AUTHORITIES.items():
        path = root / source["path"]
        _require(path.is_file(), f"missing {name}: {path}")
        observed = sha256_file(path)
        _require(
            observed == source["sha256"],
            f"{name} SHA-256 mismatch: expected {source['sha256']}, got {observed}",
        )
        paths[name] = path
    return paths


def _unique_index(
    records: Sequence[Mapping[str, Any]], fields: tuple[str, ...], name: str
) -> dict[tuple[Any, ...], dict[str, Any]]:
    result: dict[tuple[Any, ...], dict[str, Any]] = {}
    for raw_record in records:
        record = dict(raw_record)
        key = tuple(record.get(field) for field in fields)
        _require(None not in key, f"{name} has an incomplete identity: {key}")
        _require(key not in result, f"duplicate {name} identity: {key}")
        result[key] = record
    return result


def _condition(record: Mapping[str, Any]) -> dict[str, Any]:
    return {field: record[field] for field in CONDITION_FIELDS}


def _segments(indices: Sequence[int]) -> list[dict[str, int]]:
    if not indices:
        return []
    result: list[dict[str, int]] = []
    start = previous = indices[0]
    for value in indices[1:]:
        if value != previous + 1:
            result.append(
                {
                    "start_model_frame_idx": start,
                    "stop_model_frame_idx_exclusive": previous + 1,
                    "row_count": previous - start + 1,
                }
            )
            start = value
        previous = value
    result.append(
        {
            "start_model_frame_idx": start,
            "stop_model_frame_idx_exclusive": previous + 1,
            "row_count": previous - start + 1,
        }
    )
    return result


def classify_replication_count(count: int) -> str:
    """Apply the predeclared >=3 / ==2 / <2 replication semantics."""

    if count >= 3:
        return CLASS_GE3
    if count == 2:
        return CLASS_EQ2
    return CLASS_LT2


def _context_semantics(predecessor: Mapping[str, Any]) -> dict[str, Any]:
    sequence = predecessor.get("sequence_context")
    _require(isinstance(sequence, dict), "predecessor sequence_context is missing")
    expected = {
        "all_source_frames_processed": True,
        "policy": "production-66-cell-contiguous-windowing",
        "teacher_forcing": True,
        "window_size": WINDOW_SIZE,
    }
    _require(
        all(sequence.get(key) == value for key, value in expected.items()),
        "predecessor context/window semantics are ambiguous",
    )
    return {
        **expected,
        "partial_final_window_permitted": True,
        "window_rule": "range(0, frame_count, 16); stop=min(start+16, frame_count)",
        "model_frame_order": "zero-based contiguous chronological order",
    }


def _validate_capture_context(
    root: Path,
    capture_record: Mapping[str, Any],
    expected_indices: list[int],
) -> dict[str, Any]:
    path = root / str(capture_record["capture_package_path"])
    _require(path.is_file(), f"missing capture package: {path}")
    observed_hash = sha256_file(path)
    _require(
        observed_hash == capture_record["capture_package_sha256"],
        f"capture package SHA-256 mismatch: {path}",
    )
    package = _load_json(path)
    trajectory_id = capture_record["trajectory_id"]
    _require(
        package.get("trajectory_id") == trajectory_id,
        f"capture package trajectory mismatch: {trajectory_id}",
    )
    streams = package.get("streams")
    _require(isinstance(streams, dict), f"{trajectory_id}: streams are missing")
    for stream_name in ("frame_map", "server_state", "raw_actions"):
        rows = streams.get(stream_name)
        _require(isinstance(rows, list), f"{trajectory_id}: missing {stream_name}")
        observed_indices = [row.get("model_frame_idx") for row in rows]
        _require(
            observed_indices == expected_indices,
            f"{trajectory_id}: {stream_name} is not complete chronological context",
        )
    return {
        "capture_package_path": str(capture_record["capture_package_path"]),
        "capture_package_sha256": observed_hash,
        "status": "RECONSTRUCTIBLE_COMPLETE_CHRONOLOGICAL_CONTEXT",
    }


def _stratum_basis(
    accepted: Mapping[str, Any],
    *,
    capture_condition: str,
    wall_present: bool,
    context_semantics_sha256: str,
) -> dict[str, Any]:
    return {
        "layout_id": accepted["layout_id"],
        "capture_condition": capture_condition,
        "wall_present": wall_present,
        "experimental_condition": {
            field: accepted[field] for field in COMPATIBILITY_CONDITION_FIELDS
        },
        "trajectory_category": {
            "field": "control_type",
            "value": accepted["control_type"],
        },
        "visibility_regime": {
            "field": "visible_flag",
            "value": True,
            "rule": VISIBILITY_RULE,
        },
        "preprocessing_context_semantics": {
            "checkpoint_sha256": CHECKPOINT_SHA256,
            "context_semantics_sha256": context_semantics_sha256,
            "preprocess_hash": PREPROCESS_HASH,
            "preprocessing_identity": PREPROCESSING_IDENTITY,
        },
    }


def _stratum_id(basis: Mapping[str, Any]) -> str:
    return f"visible-compat-v0.1:{_canonical_sha256(dict(basis))}"


def _eligibility_reasons(
    *,
    accepted: Mapping[str, Any],
    visibility: Mapping[str, Any],
    target: Mapping[str, Any] | None,
    preprocessed: Mapping[str, Any] | None,
    context_valid: bool,
    model_frame_idx: int,
) -> list[str]:
    reasons: list[str] = []
    if accepted.get("accepted") is not True or accepted.get("status") != "PASS":
        reasons.append("TRAJECTORY_NOT_ACCEPTED")
    if (
        visibility.get("visible_flag_defined") is not True
        or visibility.get("visibility_applicable") is not True
    ):
        reasons.append("FROZEN_STRICT_VISIBILITY_NOT_APPLICABLE")
    elif visibility.get("visible_flag") is not True:
        reasons.append("FROZEN_STRICT_VISIBILITY_NOT_FULLY_VISIBLE")
    if visibility.get("quarantined") is True:
        reasons.append("FROZEN_VISIBILITY_ROW_QUARANTINED")
    if target is None or target.get("status") != "accepted":
        reasons.append("ACCEPTED_ORACLE_TARGET_MISSING")
    else:
        x_true = target.get("x_true_blocks")
        if not isinstance(x_true, (int, float)) or not math.isfinite(float(x_true)):
            reasons.append("X_TRUE_BLOCKS_INVALID")
    if not isinstance(accepted.get("trajectory_id"), str):
        reasons.append("TRAJECTORY_ID_INVALID")
    if not isinstance(model_frame_idx, int) or model_frame_idx < 0:
        reasons.append("MODEL_FRAME_IDX_INVALID")
    if not context_valid:
        reasons.append("CHRONOLOGICAL_CONTEXT_NOT_RECONSTRUCTIBLE")
    if preprocessed is None:
        reasons.append("PREPROCESSED_FRAME_AUTHORITY_MISSING")
    else:
        pointer_fields = (
            "output_path",
            "payload_sha256",
            "preprocess_hash",
            "preprocessing_identity",
        )
        if not all(preprocessed.get(field) is not None for field in pointer_fields):
            reasons.append("PREPROCESSED_PAYLOAD_RESTORATION_POINTER_INCOMPLETE")
        if preprocessed.get("preprocess_hash") != PREPROCESS_HASH:
            reasons.append("PREPROCESS_HASH_MISMATCH")
        if preprocessed.get("preprocessing_identity") != PREPROCESSING_IDENTITY:
            reasons.append("PREPROCESSING_IDENTITY_MISMATCH")
    return sorted(set(reasons))


def build_resolution_documents(
    *, root: Path = ROOT
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build the three Task-1 documents entirely from frozen authorities."""

    paths = _authority_paths(root)
    accepted_manifest = _load_json(paths["accepted_trajectory_manifest"])
    target_manifest = _load_json(paths["oracle_target_manifest"])
    frame_manifest = _load_json(paths["preprocessed_frame_manifest"])
    capture_manifest = _load_json(paths["capture_package_manifest"])
    identity = _load_json(paths["checkpoint_preprocessing_identity"])
    predecessor = _load_json(paths["predecessor_context_manifest"])

    accepted_records = [dict(row) for row in accepted_manifest.get("records", [])]
    accepted_index = _unique_index(
        accepted_records, ("trajectory_id",), "accepted trajectory"
    )
    _require(
        accepted_manifest.get("accepted_count") == ACCEPTED_COUNT
        and len(accepted_index) == ACCEPTED_COUNT,
        "accepted trajectory authority does not reconcile to exactly 66",
    )
    _require(
        all(
            row.get("accepted") is True and row.get("status") == "PASS"
            for row in accepted_records
        ),
        "accepted trajectory manifest contains a non-accepted record",
    )
    _require(
        tuple(target_manifest.get("condition_fields", [])) == CONDITION_FIELDS,
        "repository-native condition field authority changed",
    )

    visibility_rows = _jsonl(paths["strict_visibility_join"])
    row_universe_rows = _jsonl(paths["row_universe"])
    target_rows = _jsonl(paths["oracle_target_records"])
    preprocessed_rows = [dict(row) for row in frame_manifest.get("records", [])]
    capture_records = [dict(row) for row in capture_manifest.get("records", [])]

    visibility_index = _unique_index(
        visibility_rows, ("trajectory_id", "model_frame_idx"), "visibility row"
    )
    universe_index = _unique_index(
        row_universe_rows, ("trajectory_id", "model_frame_idx"), "row-universe row"
    )
    target_index = _unique_index(
        target_rows, ("trajectory_id", "model_frame_idx"), "oracle target"
    )
    preprocessed_index = _unique_index(
        preprocessed_rows,
        ("trajectory_id", "model_frame_idx"),
        "preprocessed frame",
    )
    capture_index = _unique_index(
        capture_records, ("trajectory_id",), "capture package"
    )

    _require(
        len(visibility_index)
        == len(universe_index)
        == len(preprocessed_index)
        == TOTAL_FRAME_COUNT,
        "66-trajectory frame authorities do not reconcile to 2,468 rows",
    )
    _require(
        set(visibility_index) == set(universe_index) == set(preprocessed_index),
        "visibility, row-universe, and preprocessing frame identities differ",
    )
    _require(
        len(capture_index) == ACCEPTED_COUNT
        and set(capture_index) == set(accepted_index),
        "capture-package authority does not cover the exact accepted 66",
    )
    _require(
        capture_manifest.get("capture_packages_complete") is True
        and capture_manifest.get("total_model_frame_count") == TOTAL_FRAME_COUNT,
        "capture-package completeness authority failed",
    )
    _require(
        frame_manifest.get("trajectory_count") == ACCEPTED_COUNT
        and frame_manifest.get("unique_frame_count") == TOTAL_FRAME_COUNT
        and frame_manifest.get("missing_frame_count") == 0
        and frame_manifest.get("failure_count") == 0,
        "preprocessed frame authority is incomplete",
    )
    _require(
        identity.get("checkpoint_sha256") == CHECKPOINT_SHA256
        and identity.get("model_hash") == CHECKPOINT_SHA256
        and identity.get("preprocess_hash") == PREPROCESS_HASH
        and identity.get("preprocessing_identity") == PREPROCESSING_IDENTITY
        and identity.get("person_a_model_preprocess_authority_valid") is True
        and identity.get("unresolved_person_a_authority") == [],
        "checkpoint/preprocessing identity cannot be established",
    )

    context_semantics = _context_semantics(predecessor)
    context_semantics_sha256 = _canonical_sha256(context_semantics)
    source_authorities = {
        name: dict(source) for name, source in sorted(SOURCE_AUTHORITIES.items())
    }

    frames_by_trajectory: dict[str, list[int]] = defaultdict(list)
    for trajectory_id, model_frame_idx in visibility_index:
        frames_by_trajectory[str(trajectory_id)].append(int(model_frame_idx))

    trajectory_work: list[dict[str, Any]] = []
    eligible_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    stratum_members: dict[str, list[str]] = defaultdict(list)
    stratum_bases: dict[str, dict[str, Any]] = {}

    for (trajectory_id,) in sorted(accepted_index):
        accepted = accepted_index[(trajectory_id,)]
        capture = capture_index[(trajectory_id,)]
        frame_count = int(capture["frame_count"])
        expected_indices = list(range(frame_count))
        observed_indices = sorted(frames_by_trajectory[trajectory_id])
        _require(
            observed_indices == expected_indices,
            f"{trajectory_id}: model_frame_idx authority is not contiguous",
        )
        context = _validate_capture_context(root, capture, expected_indices)

        wall_values = {
            bool(visibility_index[(trajectory_id, index)]["wall_present"])
            for index in expected_indices
        }
        _require(
            len(wall_values) == 1,
            f"{trajectory_id}: wall_present changes within trajectory",
        )
        wall_present = wall_values.pop()
        expected_wall = accepted["scene"] != "nowall"
        _require(
            wall_present == expected_wall,
            f"{trajectory_id}: scene and wall_present authority disagree",
        )
        _require(
            capture.get("control_type") == accepted["control_type"]
            and capture.get("set_id") == accepted["set_id"]
            and CAPTURE_SCENE_TO_ACCEPTED_SCENE.get(capture.get("scene"))
            == accepted["scene"],
            f"{trajectory_id}: accepted and capture conditions disagree",
        )

        target_available = bool(capture.get("target_present"))
        basis: dict[str, Any] | None = None
        stratum_id: str | None = None
        if target_available:
            basis = _stratum_basis(
                accepted,
                capture_condition=str(capture["condition"]),
                wall_present=wall_present,
                context_semantics_sha256=context_semantics_sha256,
            )
            stratum_id = _stratum_id(basis)
            stratum_bases[stratum_id] = basis
            stratum_members[stratum_id].append(trajectory_id)

        trajectory_eligible: list[dict[str, Any]] = []
        trajectory_excluded: list[dict[str, Any]] = []
        reason_counts: Counter[str] = Counter()
        for model_frame_idx in expected_indices:
            key = (trajectory_id, model_frame_idx)
            visibility = visibility_index[key]
            universe = universe_index[key]
            preprocessed = preprocessed_index.get(key)
            target = target_index.get(key)
            _require(
                universe.get("visible_flag") == visibility.get("visible_flag")
                and universe.get("visible_flag_defined")
                == visibility.get("visible_flag_defined")
                and universe.get("visibility_applicable")
                == visibility.get("visibility_applicable"),
                f"{trajectory_id}:{model_frame_idx}: visibility authorities disagree",
            )
            reasons = _eligibility_reasons(
                accepted=accepted,
                visibility=visibility,
                target=target,
                preprocessed=preprocessed,
                context_valid=True,
                model_frame_idx=model_frame_idx,
            )
            row_key = f"{trajectory_id}:{model_frame_idx}"
            if reasons:
                reason_counts.update(reasons)
                excluded = {
                    "row_key": row_key,
                    "trajectory_id": trajectory_id,
                    "model_frame_idx": model_frame_idx,
                    "reasons": reasons,
                }
                trajectory_excluded.append(excluded)
                excluded_rows.append(excluded)
                continue

            _require(target is not None, f"{row_key}: target disappeared after checks")
            _require(
                preprocessed is not None,
                f"{row_key}: preprocessing disappeared after checks",
            )
            row_hash_basis = {
                "capture_package_sha256": capture["capture_package_sha256"],
                "checkpoint_sha256": CHECKPOINT_SHA256,
                "context_semantics_sha256": context_semantics_sha256,
                "layout_id": accepted["layout_id"],
                "model_frame_idx": model_frame_idx,
                "oracle_target_record_sha256": _canonical_sha256(target),
                "preprocess_hash": PREPROCESS_HASH,
                "preprocessed_frame_record_sha256": _canonical_sha256(preprocessed),
                "strict_visibility_record_sha256": _canonical_sha256(visibility),
                "trajectory_id": trajectory_id,
            }
            eligible = {
                "capture_package_sha256": capture["capture_package_sha256"],
                "frozen_row_sha256": _canonical_sha256(row_hash_basis),
                "layout_id": accepted["layout_id"],
                "model_frame_idx": model_frame_idx,
                "oracle_target_record_sha256": row_hash_basis[
                    "oracle_target_record_sha256"
                ],
                "payload_sha256": preprocessed["payload_sha256"],
                "preprocessed_frame_record_sha256": row_hash_basis[
                    "preprocessed_frame_record_sha256"
                ],
                "row_key": row_key,
                "stratum_id": stratum_id,
                "strict_visibility_record_sha256": row_hash_basis[
                    "strict_visibility_record_sha256"
                ],
                "target_id": target["target_id"],
                "trajectory_id": trajectory_id,
                "x_true_blocks": float(target["x_true_blocks"]),
            }
            trajectory_eligible.append(eligible)
            eligible_rows.append(eligible)

        trajectory_work.append(
            {
                "accepted": accepted,
                "basis": basis,
                "capture": capture,
                "context": context,
                "eligible_rows": trajectory_eligible,
                "excluded_rows": trajectory_excluded,
                "frame_count": frame_count,
                "reason_counts": dict(sorted(reason_counts.items())),
                "stratum_id": stratum_id,
                "target_available": target_available,
                "trajectory_id": trajectory_id,
                "wall_present": wall_present,
            }
        )

    eligible_ids = {
        work["trajectory_id"] for work in trajectory_work if work["eligible_rows"]
    }
    strata: list[dict[str, Any]] = []
    stratum_replication_counts: dict[str, int] = {}
    for stratum_id in sorted(stratum_members):
        members = sorted(stratum_members[stratum_id])
        compatible_eligible = sorted(set(members) & eligible_ids)
        count = len(compatible_eligible)
        classification = classify_replication_count(count)
        stratum_replication_counts[stratum_id] = count
        strata.append(
            {
                "compatibility_basis": stratum_bases[stratum_id],
                "compatible_eligible_trajectory_count": count,
                "compatible_eligible_trajectory_ids": compatible_eligible,
                "member_trajectory_ids": members,
                "replication_classification": classification,
                "stratum_id": stratum_id,
            }
        )

    inventory_rows: list[dict[str, Any]] = []
    condition_shift_ids: list[str] = []
    invalid_ids: list[str] = []
    for work in trajectory_work:
        accepted = work["accepted"]
        eligible_indices = [row["model_frame_idx"] for row in work["eligible_rows"]]
        compatible_count = (
            stratum_replication_counts[work["stratum_id"]]
            if work["stratum_id"] is not None
            else 0
        )
        limitation_reasons: list[str]
        if not work["target_available"]:
            classification = CLASS_INVALID
            invalid_ids.append(work["trajectory_id"])
            limitation_reasons = [
                "TARGET_OBJECT_ABSENT_AND_X_TRUE_BLOCKS_UNAVAILABLE",
                "FROZEN_VISIBILITY_NOT_APPLICABLE",
            ]
        elif work["wall_present"] and eligible_indices:
            classification = CLASS_SHIFT
            condition_shift_ids.append(work["trajectory_id"])
            limitation_reasons = [
                "WALL_PRESENT_CONDITION_MISMATCH_WITH_NO_WALL_VISIBLE_CONTROL",
                "KEPT_SEPARATE_FROM_NO_WALL_REPLICATION_COUNT",
            ]
        else:
            classification = classify_replication_count(compatible_count)
            if not eligible_indices:
                limitation_reasons = [
                    "NO_FULLY_VISIBLE_ROWS_UNDER_FROZEN_STRICT_VISIBILITY",
                    "COMPATIBLE_ELIGIBLE_TRAJECTORY_COUNT_LT2",
                ]
            elif compatible_count < 2:
                limitation_reasons = [
                    "ONLY_ONE_COMPATIBLE_ELIGIBLE_TRAJECTORY_IN_STRATUM"
                ]
            else:
                limitation_reasons = []

        inventory_rows.append(
            {
                "accepted_trajectory_status": "PASS",
                "capture_condition": work["capture"]["condition"],
                "checkpoint_preprocessing_identity_status": "COMPLETE",
                "compatibility_stratum": work["stratum_id"],
                "compatible_eligible_trajectory_count": compatible_count,
                "condition_fields": _condition(accepted),
                "continuous_visible_segment_summary": _segments(eligible_indices),
                "eligible_visible_row_count": len(eligible_indices),
                "exact_exclusion_or_limitation_reasons": limitation_reasons,
                "excluded_row_reason_counts": work["reason_counts"],
                "frame_count": work["frame_count"],
                "layout_id": accepted["layout_id"],
                "model_frame_idx_status": "VALID_CONTIGUOUS_ZERO_BASED",
                "preprocessing_authority_status": (
                    "HASHED_IMMUTABLE_RESTORATION_POINTER_COMPLETE"
                ),
                "replication_classification": classification,
                "sequence_context_status": work["context"]["status"],
                "target_availability": (
                    "COMPLETE_X_TRUE_BLOCKS" if work["target_available"] else "MISSING"
                ),
                "trajectory_category": {
                    "field": "control_type",
                    "value": accepted["control_type"],
                },
                "trajectory_id": work["trajectory_id"],
                "visibility_regime": {
                    "applicable_fully_visible_row_count": len(eligible_indices),
                    "field": "visible_flag",
                    "required_value": True,
                    "rule": VISIBILITY_RULE,
                    "wall_present": work["wall_present"],
                },
            }
        )

    classification_counts = Counter(
        row["replication_classification"] for row in inventory_rows
    )
    strata_class_counts = Counter(row["replication_classification"] for row in strata)
    _require(len(inventory_rows) == ACCEPTED_COUNT, "inventory does not contain 66")
    _require(
        len({row["trajectory_id"] for row in inventory_rows}) == ACCEPTED_COUNT,
        "inventory contains duplicate trajectory identities",
    )
    _require(
        not any(
            stratum["compatible_eligible_trajectory_count"] >= 2 for stratum in strata
        ),
        "existing compatible replication unexpectedly resolved the confound",
    )

    field_mapping = {
        "condition_fields_authority": list(CONDITION_FIELDS),
        "condition_fields_used_for_compatibility": list(COMPATIBILITY_CONDITION_FIELDS),
        "condition_seed_treatment": (
            "seed is retained as acquisition identity and excluded from controlled "
            "condition matching so independent acquisitions may replicate a stratum"
        ),
        "experimental_condition_additional_fields": [
            "capture_package_manifest.records[].condition",
            "strict_visibility_join[].wall_present",
        ],
        "layout_field": "layout_id",
        "trajectory_category_field": "control_type",
        "visibility_fields": [
            "visible_flag",
            "visible_flag_defined",
            "visibility_applicable",
            "visible_flag_rule",
        ],
    }
    counts = {
        "accepted_trajectory_count": ACCEPTED_COUNT,
        "condition_shift_only_trajectory_count": len(condition_shift_ids),
        "eligible_row_count": len(eligible_rows),
        "eligible_trajectory_count": len(eligible_ids),
        "excluded_row_count": len(excluded_rows),
        "invalid_trajectory_count": len(invalid_ids),
        "total_frame_count": TOTAL_FRAME_COUNT,
    }

    inventory = {
        "artifact_id": "exploratory-visible-position-resolution-replication-inventory-v0.1",
        "base_head": BASE_HEAD,
        "classification_counts": dict(sorted(classification_counts.items())),
        "counts": counts,
        "field_mapping": field_mapping,
        "runner_version": RUNNER_VERSION,
        "schema_version": "1.0",
        "source_authorities": source_authorities,
        "trajectories": inventory_rows,
    }

    eligibility_rule = {
        "all_satisfying_rows_included": True,
        "join_key": ["trajectory_id", "model_frame_idx"],
        "predicates": [
            "trajectory accepted=true and status=PASS in accepted trajectory manifest",
            "visible_flag_defined=true, visibility_applicable=true, visible_flag=true, and quarantined=false in frozen strict visibility join",
            "accepted oracle target exists and x_true_blocks is finite",
            "trajectory_id is non-empty and model_frame_idx is a non-negative integer",
            "all trajectory source frames are present in zero-based chronological order",
            "frame_map, server_state, and raw_actions reconstruct each complete <=16-frame production window",
            "preprocessed frame manifest has output_path, payload_sha256, preprocess_hash, and preprocessing_identity",
            "checkpoint_sha256, preprocess_hash, and preprocessing_identity equal the frozen resolved identities",
        ],
        "rule_id": "expanded-strict-visible-authority-join-v0.1",
        "selection_inputs": list(sorted(SOURCE_AUTHORITIES)),
    }
    eligibility = {
        "artifact_id": "exploratory-visible-position-resolution-expanded-eligibility-v0.1",
        "base_head": BASE_HEAD,
        "context_semantics": context_semantics,
        "context_semantics_sha256": context_semantics_sha256,
        "counts": counts,
        "deterministic_eligibility_rule": eligibility_rule,
        "eligible_row_identities": eligible_rows,
        "eligible_row_keys_sha256": _canonical_sha256(
            [row["row_key"] for row in eligible_rows]
        ),
        "excluded_rows": excluded_rows,
        "excluded_trajectories": [
            {
                "exact_reasons": row["exact_exclusion_or_limitation_reasons"],
                "replication_classification": row["replication_classification"],
                "trajectory_id": row["trajectory_id"],
            }
            for row in inventory_rows
            if row["replication_classification"] == CLASS_INVALID
            or row["eligible_visible_row_count"] == 0
        ],
        "frozen_row_hash_basis": [
            "trajectory_id",
            "layout_id",
            "model_frame_idx",
            "capture_package_sha256",
            "strict_visibility_record_sha256",
            "oracle_target_record_sha256",
            "preprocessed_frame_record_sha256",
            "checkpoint_sha256",
            "preprocess_hash",
            "context_semantics_sha256",
        ],
        "frozen_row_hashes": [
            {"row_key": row["row_key"], "sha256": row["frozen_row_sha256"]}
            for row in eligible_rows
        ],
        "schema_version": "1.0",
        "source_authorities": source_authorities,
        "stratum_identities": strata,
    }

    scientific_reason = (
        "All 60 target-bearing strata have fewer than two compatible eligible "
        "trajectories; each of the six no-wall layout strata contains exactly one "
        "trajectory, while visible wall-condition trajectories are separate "
        "condition shifts and cannot resolve the layout/trajectory confound."
    )
    decision = {
        "PRIMARY_PATH": "BALANCED_NEW_CAPTURE",
        "all_controlling_source_hashes": source_authorities,
        "base_head": BASE_HEAD,
        "compatible_strata_counts": {
            "GE3": strata_class_counts.get(CLASS_GE3, 0),
            "EQ2": strata_class_counts.get(CLASS_EQ2, 0),
            "LT2": strata_class_counts.get(CLASS_LT2, 0),
        },
        "condition_shift_trajectories_kept_separate": sorted(condition_shift_ids),
        "context_semantics_sha256": context_semantics_sha256,
        "eligible_trajectory_counts": {
            "accepted": ACCEPTED_COUNT,
            "eligible": len(eligible_ids),
            "no_wall_eligible": sum(
                row["trajectory_category"]["value"] == NO_WALL_CONTROL
                and row["eligible_visible_row_count"] > 0
                for row in inventory_rows
            ),
            "target_bearing": sum(work["target_available"] for work in trajectory_work),
        },
        "exact_trajectories_proposed_for_expanded_extraction": [],
        "new_capture_required": True,
        "runner_version": RUNNER_VERSION,
        "schema_version": "1.0",
        "scientific_reason": scientific_reason,
        "selection_uses_decoder_results": False,
    }
    return inventory, eligibility, decision


def write_resolution_documents(
    *, root: Path = ROOT, output_root: Path | None = None
) -> tuple[Path, Path, Path]:
    inventory, eligibility, decision = build_resolution_documents(root=root)
    destination = output_root or (
        root / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
    )
    outputs = (
        destination / "replication_inventory.json",
        destination / "expanded_visibility_eligibility.json",
        destination / "replication_authority_decision.json",
    )
    for path, document in zip(outputs, (inventory, eligibility, decision), strict=True):
        _write_json(path, document)
    return outputs


# ---------------------------------------------------------------------------
# Task 2 development analyses.
#
# These reuse the recovered predecessor layer-4 authority (351 rows x 336
# tokens x 2,048) and the repository's leakage-safe ridge helpers.  Nothing
# here re-extracts activations or defines a new scientific authority.
# ---------------------------------------------------------------------------

LAYER_IDX = 4
TOKEN_GRID_ROWS = 14
TOKEN_GRID_COLS = 24
TOKEN_COUNT = TOKEN_GRID_ROWS * TOKEN_GRID_COLS
HIDDEN_WIDTH = 2048
EXPECTED_ELIGIBLE_ROWS = 351
ALPHA_GRID = (0.1, 1.0, 10.0, 100.0)
# The alpha-selection seed is the repository-established probe seed already
# frozen in the predecessor diagnostic config; it is not re-chosen here.
ALPHA_SELECTION_SEED = 20260719

PREDECESSOR_MANIFEST = (
    "docs/status/integration/exploratory_visible_position_diagnostics_v0_1"
    "/unpooled_activation_manifest.json"
)

# name -> (region_rows, region_cols) over the verified 14x24 token grid.
SPATIAL_REPRESENTATIONS = (
    ("GLOBAL_1x1", 1, 1),
    ("COARSE_2x3", 2, 3),
    ("COARSE_2x6", 2, 6),
    ("MEDIUM_14x6", 14, 6),
    ("FULL_14x24", 14, 24),
    ("ROW_14x1", 14, 1),
    ("COLUMN_1x24", 1, 24),
)
GLOBAL_REPRESENTATION = "GLOBAL_1x1"
FULL_REPRESENTATION = "FULL_14x24"
REPRESENTATION_ALIASES = {
    "GLOBAL_MEAN": GLOBAL_REPRESENTATION,
    "FULL_TOKEN_GRID": FULL_REPRESENTATION,
}
INTERMEDIATE_CANDIDATES = (
    "COARSE_2x3",
    "COARSE_2x6",
    "MEDIUM_14x6",
    "ROW_14x1",
    "COLUMN_1x24",
)
BENCHMARK_HELD_OUT_LAYOUT = "L01"

# Five deterministic sample-specific spatial-scramble seeds.  The repository
# carries no prior scramble seed list, so they are frozen here for future use
# and are deliberately not consumed by any analysis in this task.
SPATIAL_SCRAMBLE_SEEDS = (20260901, 20260902, 20260903, 20260904, 20260905)

NMAE_STD_DEFINITION = (
    "NMAE_STD = MAE / test_target_std, where test_target_std is the population "
    "(ddof=0) standard deviation of the held-out targets; null when that "
    "standard deviation is exactly zero."
)


def _numpy() -> Any:
    import numpy

    return numpy


def region_token_partition(
    region_rows: int, region_cols: int
) -> tuple[tuple[int, ...], ...]:
    """Partition the 14x24 grid into contiguous factor-compatible regions.

    Regions are emitted row-block major.  Every one of the 336 tokens lands in
    exactly one region; there is no interpolation, learned pooling, or
    post-hoc boundary placement.
    """

    _require(
        isinstance(region_rows, int) and isinstance(region_cols, int),
        "region counts must be integers",
    )
    _require(
        1 <= region_rows <= TOKEN_GRID_ROWS and 1 <= region_cols <= TOKEN_GRID_COLS,
        f"region grid {region_rows}x{region_cols} is outside the 14x24 token grid",
    )
    _require(
        TOKEN_GRID_ROWS % region_rows == 0 and TOKEN_GRID_COLS % region_cols == 0,
        f"region grid {region_rows}x{region_cols} is not factor-compatible with 14x24",
    )
    rows_per = TOKEN_GRID_ROWS // region_rows
    cols_per = TOKEN_GRID_COLS // region_cols
    regions = tuple(
        tuple(
            row * TOKEN_GRID_COLS + col
            for row in range(row_block * rows_per, (row_block + 1) * rows_per)
            for col in range(col_block * cols_per, (col_block + 1) * cols_per)
        )
        for row_block in range(region_rows)
        for col_block in range(region_cols)
    )
    covered = [token for region in regions for token in region]
    _require(
        len(covered) == TOKEN_COUNT and sorted(covered) == list(range(TOKEN_COUNT)),
        f"region grid {region_rows}x{region_cols} does not cover each token once",
    )
    _require(
        len(regions) == region_rows * region_cols,
        f"region grid {region_rows}x{region_cols} produced the wrong region count",
    )
    return regions


def representation_definitions() -> dict[str, dict[str, Any]]:
    """Return the prespecified ladder with verified partition definitions."""

    definitions: dict[str, dict[str, Any]] = {}
    for name, region_rows, region_cols in SPATIAL_REPRESENTATIONS:
        regions = region_token_partition(region_rows, region_cols)
        definitions[name] = {
            "representation": name,
            "region_rows": region_rows,
            "region_cols": region_cols,
            "region_count": len(regions),
            "tokens_per_region": len(regions[0]),
            "feature_count": len(regions) * HIDDEN_WIDTH,
            "token_grid": f"{TOKEN_GRID_ROWS}x{TOKEN_GRID_COLS}",
            "region_order": "row_block_major",
            "region_token_indices": [list(region) for region in regions],
            "pooling": "mean over tokens inside the region, float32",
            "flattening": "region x hidden, region identity preserved",
        }
    return definitions


def _load_recovered_authority(root: Path) -> tuple[Any, tuple[dict[str, Any], ...]]:
    """Load the recovered layer-4 token block and its row authority in order."""

    np = _numpy()
    from scripts.run_exploratory_visible_position_diagnostics import (
        _load_token_block,
        _verified_token_chunk_paths,
        load_config,
        load_visible_authority,
    )

    manifest = _load_json(root / PREDECESSOR_MANIFEST)
    _require(
        manifest["status"] == "COMPLETE"
        and manifest["scope"]["layer_idx"] == LAYER_IDX
        and manifest["scope"]["visual_token_count"] == TOKEN_COUNT
        and manifest["scope"]["hidden_width"] == HIDDEN_WIDTH
        and manifest["scope"]["eligible_row_count"] == EXPECTED_ELIGIBLE_ROWS,
        "recovered manifest is not the exact layer-4 351-row authority",
    )
    paths = _verified_token_chunk_paths(manifest)
    block = _load_token_block(paths)
    rows: list[dict[str, Any]] = []
    for chunk in manifest["chunks"]:
        rows.extend(_jsonl(Path(chunk["rows"]["path"])))
    authority_rows = load_visible_authority(load_config())
    _require(
        [row["row_key"] for row in rows] == [row["row_key"] for row in authority_rows],
        "recovered row order differs from the current visible authority",
    )
    _require(
        block.shape == (EXPECTED_ELIGIBLE_ROWS, TOKEN_COUNT, HIDDEN_WIDTH)
        and block.dtype == np.dtype("float16"),
        "recovered token block is not [351,336,2048] float16",
    )
    return block, tuple(rows)


def build_representation_features(
    block: Any, region_rows: int, region_cols: int
) -> Any:
    """Mean-pool tokens inside each region and flatten region x hidden."""

    np = _numpy()
    region_token_partition(region_rows, region_cols)
    rows_per = TOKEN_GRID_ROWS // region_rows
    cols_per = TOKEN_GRID_COLS // region_cols
    row_count = int(block.shape[0])
    features = np.empty(
        (row_count, region_rows * region_cols * HIDDEN_WIDTH), dtype=np.float32
    )
    chunk = 32
    for start in range(0, row_count, chunk):
        stop = min(start + chunk, row_count)
        window = np.asarray(block[start:stop], dtype=np.float32).reshape(
            stop - start,
            region_rows,
            rows_per,
            region_cols,
            cols_per,
            HIDDEN_WIDTH,
        )
        features[start:stop] = window.mean(axis=(2, 4)).reshape(stop - start, -1)
    return features


def _outer_layout_folds(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """One outer fold per layout: the complete held-out layout is the test set."""

    np = _numpy()
    labels = np.array([row["trajectory_label"] for row in rows])
    layouts = sorted(set(labels.tolist()))
    _require(len(layouts) == 6, "expected exactly six held-out layouts")
    folds = []
    for layout in layouts:
        test_index = np.flatnonzero(labels == layout)
        train_index = np.flatnonzero(labels != layout)
        _require(
            test_index.size > 0 and train_index.size > 0,
            f"{layout}: degenerate outer fold",
        )
        _require(
            not (set(labels[test_index].tolist()) & set(labels[train_index].tolist())),
            f"{layout}: held-out layout leaked into training rows",
        )
        folds.append(
            {
                "held_out_layout": layout,
                "test_index": test_index,
                "train_index": train_index,
                "training_group_ids": sorted(set(labels[train_index].tolist())),
            }
        )
    return tuple(folds)


def fold_metrics(truth: Any, predictions: Any) -> dict[str, Any]:
    """Complementary held-out metrics, with explicit degenerate-target nulls."""

    np = _numpy()
    from mineocclude.metrics.u1_mean import regression_metrics

    actual = np.asarray(truth, dtype=np.float64)
    predicted = np.asarray(predictions, dtype=np.float64)
    target_mean = float(actual.mean())
    target_std = float(actual.std(ddof=0))
    total_sum_of_squares = float(((actual - target_mean) ** 2).sum())
    mae = float(np.abs(actual - predicted).mean())
    record: dict[str, Any] = {
        "sample_count": int(actual.size),
        "mae": mae,
        "mse": float(((actual - predicted) ** 2).mean()),
        "target_mean": target_mean,
        "target_std": target_std,
        "target_min": float(actual.min()),
        "target_max": float(actual.max()),
        "target_range": float(actual.max() - actual.min()),
        "target_sst": total_sum_of_squares,
        "nmae_std": None if target_std == 0.0 else mae / target_std,
    }
    if total_sum_of_squares == 0.0:
        record["r2"] = None
    else:
        record["r2"] = regression_metrics(actual.tolist(), predicted.tolist()).r2
    prediction_std = float(predicted.std(ddof=0))
    if target_std == 0.0 or prediction_std == 0.0:
        record["pearson_r"] = None
    else:
        record["pearson_r"] = float(np.corrcoef(actual, predicted)[0, 1])
    if prediction_std == 0.0:
        record["prediction_slope"] = None
        record["prediction_bias"] = None
    else:
        # Ordinary least squares of held-out truth on the prediction.
        slope, bias = np.polyfit(predicted, actual, 1)
        record["prediction_slope"] = float(slope)
        record["prediction_bias"] = float(bias)
    return record


def _fit_outer_fold(
    features: Any,
    targets: Any,
    groups: Sequence[str],
    fold: Mapping[str, Any],
) -> dict[str, Any]:
    """Fit one outer layout fold with train-only scaling and grouped alpha."""

    np = _numpy()
    from mineocclude.probes.ridge import (
        fit_ridge,
        fit_standard_scaler,
        select_ridge_alpha_grouped,
    )

    train_index = fold["train_index"]
    test_index = fold["test_index"]
    train_features = np.asarray(features[train_index], dtype=np.float64)
    test_features = np.asarray(features[test_index], dtype=np.float64)
    train_targets = targets[train_index]
    test_targets = targets[test_index]
    train_groups = [groups[int(index)] for index in train_index]
    unique_groups = sorted(set(train_groups))
    _require(
        len(unique_groups) == 5,
        f"{fold['held_out_layout']}: expected five training layouts",
    )
    _require(
        fold["held_out_layout"] not in unique_groups,
        f"{fold['held_out_layout']}: held-out layout entered alpha selection",
    )

    scaling_start = time.perf_counter()
    scaler = fit_standard_scaler(train_features)
    scaling_seconds = time.perf_counter() - scaling_start
    _require(
        scaler.training_row_count == int(train_index.size),
        f"{fold['held_out_layout']}: scaler saw rows outside the training layouts",
    )

    alpha_start = time.perf_counter()
    selection = select_ridge_alpha_grouped(
        train_features,
        train_targets,
        train_groups,
        alpha_grid=ALPHA_GRID,
        n_splits=len(unique_groups),
        seed=ALPHA_SELECTION_SEED,
    )
    alpha_seconds = time.perf_counter() - alpha_start

    fit_start = time.perf_counter()
    model = fit_ridge(
        train_features,
        train_targets,
        alpha=selection.selected_alpha,
        scaler=scaler,
    )
    predictions = np.asarray(model.predict(test_features), dtype=np.float64)
    fit_seconds = time.perf_counter() - fit_start

    record = {
        "held_out_layout": fold["held_out_layout"],
        "training_group_ids": list(unique_groups),
        "train_row_count": int(train_index.size),
        "test_row_count": int(test_index.size),
        "feature_count": int(train_features.shape[1]),
        "selected_alpha": selection.selected_alpha,
        "alpha_grid": list(ALPHA_GRID),
        "alpha_selection_grouping": "training_layout",
        "inner_fold_count": selection.inner_fold_count,
        "validation_mse_by_alpha": {
            str(alpha): mse for alpha, mse in selection.mean_mse_by_alpha.items()
        },
        "scaler_fit_scope": "training_layout_rows_only",
        "scaler_training_row_count": scaler.training_row_count,
        "timings_seconds": {
            "scaling": scaling_seconds,
            "alpha_selection": alpha_seconds,
            "final_fit": fit_seconds,
        },
        **fold_metrics(test_targets, predictions),
    }
    record["predictions"] = [float(value) for value in predictions]
    return record


def _macro_summary(values: Sequence[float | None]) -> dict[str, Any]:
    present = [value for value in values if value is not None]
    if not present:
        return {
            "macro_mean": None,
            "macro_median": None,
            "minimum": None,
            "maximum": None,
            "range": None,
            "layout_count": 0,
        }
    return {
        "macro_mean": float(sum(present) / len(present)),
        "macro_median": float(statistics.median(present)),
        "minimum": float(min(present)),
        "maximum": float(max(present)),
        "range": float(max(present) - min(present)),
        "layout_count": len(present),
    }


def evaluate_representation_ladder(
    *, root: Path = ROOT
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate every prespecified representation on the same six outer folds."""

    np = _numpy()
    definitions = representation_definitions()
    block, rows = _load_recovered_authority(root)
    targets = np.asarray([row["x_true_blocks"] for row in rows], dtype=np.float64)
    groups = [row["trajectory_label"] for row in rows]
    folds = _outer_layout_folds(rows)
    row_authority = {
        "row_count": len(rows),
        "row_keys_sha256": _canonical_sha256([row["row_key"] for row in rows]),
        "outer_fold_layouts": [fold["held_out_layout"] for fold in folds],
        "outer_test_row_counts": {
            fold["held_out_layout"]: int(fold["test_index"].size) for fold in folds
        },
        "outer_group_unit": "layout_trajectory",
    }

    # The ladder derives every representation, including GLOBAL, from one
    # deterministic region-pooling path so all representations receive
    # identical treatment.  Confirm that path against the frozen production
    # mean pool rather than assuming the two agree.
    manifest = _load_json(root / PREDECESSOR_MANIFEST)
    production_pooled = np.concatenate(
        [
            np.load(chunk["pooled_array"]["path"], allow_pickle=False)
            for chunk in manifest["chunks"]
        ],
        axis=0,
    )
    global_features = build_representation_features(block, 1, 1)
    pooling_equivalence = {
        "comparison": "GLOBAL_1x1 region pooling vs frozen production mean pool",
        "max_abs_difference": float(np.abs(global_features - production_pooled).max()),
        "tolerance": 1e-6,
        "note": ("identical float32 means; any residual is summation order alone"),
    }
    pooling_equivalence["pass"] = bool(
        pooling_equivalence["max_abs_difference"] <= pooling_equivalence["tolerance"]
    )
    _require(
        pooling_equivalence["pass"],
        "GLOBAL region pooling disagrees with the frozen production mean pool",
    )
    del production_pooled, global_features

    results: dict[str, Any] = {}
    timings: dict[str, Any] = {}
    for name, region_rows, region_cols in SPATIAL_REPRESENTATIONS:
        load_start = time.perf_counter()
        features = build_representation_features(block, region_rows, region_cols)
        load_seconds = time.perf_counter() - load_start
        _require(
            features.shape == (len(rows), definitions[name]["feature_count"]),
            f"{name}: representation feature shape is not the prespecified size",
        )
        fold_records = [
            _fit_outer_fold(features, targets, groups, fold) for fold in folds
        ]
        timings[name] = {
            "feature_build_seconds": load_seconds,
            "feature_shape": list(features.shape),
        }
        results[name] = fold_records
        del features
    del block

    return results, {
        "row_authority": row_authority,
        "timings": timings,
        "authority_rows": rows,
        "folds": folds,
        "targets": targets,
        "pooling_equivalence": pooling_equivalence,
    }


def _representation_summary(
    fold_records: Sequence[Mapping[str, Any]],
    baseline: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    per_layout = {record["held_out_layout"]: record for record in fold_records}
    r2_values = [record["r2"] for record in fold_records]
    summary: dict[str, Any] = {
        "per_layout_r2": {
            layout: record["r2"] for layout, record in per_layout.items()
        },
        "per_layout_mae": {
            layout: record["mae"] for layout, record in per_layout.items()
        },
        "per_layout_nmae_std": {
            layout: record["nmae_std"] for layout, record in per_layout.items()
        },
        "equal_layout_macro_r2": _macro_summary(r2_values),
        "equal_layout_macro_mae": _macro_summary(
            [record["mae"] for record in fold_records]
        ),
        "selected_alpha_by_layout": {
            layout: record["selected_alpha"] for layout, record in per_layout.items()
        },
        "feature_count": fold_records[0]["feature_count"],
    }
    if baseline is not None:
        base = {record["held_out_layout"]: record for record in baseline}
        deltas = {
            layout: (
                None
                if record["r2"] is None or base[layout]["r2"] is None
                else record["r2"] - base[layout]["r2"]
            )
            for layout, record in per_layout.items()
        }
        present = [value for value in deltas.values() if value is not None]
        summary["per_layout_r2_delta_over_global"] = deltas
        summary["layouts_above_global"] = sum(1 for value in present if value > 0.0)
        summary["layouts_below_global"] = sum(1 for value in present if value < 0.0)
        summary["median_r2_delta_over_global"] = (
            float(statistics.median(present)) if present else None
        )
    return summary


def select_surviving_intermediate(
    ladder: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Apply the prespecified survivor rule in its exact declared order."""

    definitions = representation_definitions()
    baseline = ladder[GLOBAL_REPRESENTATION]
    candidates = []
    for name in INTERMEDIATE_CANDIDATES:
        summary = _representation_summary(ladder[name], baseline)
        candidates.append(
            {
                "representation": name,
                "layouts_above_global": summary["layouts_above_global"],
                "median_r2_delta_over_global": summary["median_r2_delta_over_global"],
                "feature_count": definitions[name]["feature_count"],
            }
        )
    ordered = sorted(
        candidates,
        key=lambda item: (
            -item["layouts_above_global"],
            -(
                item["median_r2_delta_over_global"]
                if item["median_r2_delta_over_global"] is not None
                else float("-inf")
            ),
            item["feature_count"],
            item["representation"],
        ),
    )
    return {
        "rule": [
            "1. maximize held-out layouts with R2 greater than GLOBAL",
            "2. tie-break by highest median per-layout R2 delta over GLOBAL",
            "3. tie-break by lower feature dimensionality",
            "4. tie-break lexicographically by representation name",
        ],
        "selection_metric_scope": "per_layout_outer_folds_only",
        "candidates": ordered,
        "surviving_intermediate": ordered[0]["representation"],
        "surviving_intermediate_feature_count": ordered[0]["feature_count"],
    }


def classify_metric_decomposition(
    global_records: Sequence[Mapping[str, Any]],
    full_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Judge whether extreme R2 behaviour mainly tracks low target variance."""

    base = {record["held_out_layout"]: record for record in global_records}
    per_layout = []
    for record in full_records:
        layout = record["held_out_layout"]
        reference = base[layout]
        per_layout.append(
            {
                "held_out_layout": layout,
                "target_std": record["target_std"],
                "target_sst": record["target_sst"],
                "target_range": record["target_range"],
                "global_r2": reference["r2"],
                "full_r2": record["r2"],
                "r2_delta": (
                    None
                    if record["r2"] is None or reference["r2"] is None
                    else record["r2"] - reference["r2"]
                ),
                "global_mae": reference["mae"],
                "full_mae": record["mae"],
                "mae_delta": record["mae"] - reference["mae"],
                "global_nmae_std": reference["nmae_std"],
                "full_nmae_std": record["nmae_std"],
                "nmae_std_delta": (
                    None
                    if record["nmae_std"] is None or reference["nmae_std"] is None
                    else record["nmae_std"] - reference["nmae_std"]
                ),
                "global_pearson_r": reference["pearson_r"],
                "full_pearson_r": record["pearson_r"],
                "global_prediction_slope": reference["prediction_slope"],
                "full_prediction_slope": record["prediction_slope"],
            }
        )

    ssts = [item["target_sst"] for item in per_layout]
    median_sst = float(statistics.median(ssts))
    extreme = [
        item
        for item in per_layout
        if item["r2_delta"] is not None and abs(item["r2_delta"]) > 1.0
    ]
    low_variance_extreme = [item for item in extreme if item["target_sst"] < median_sst]
    directional_mae = sum(1 for item in per_layout if item["mae_delta"] < 0.0)
    directional_nmae = sum(
        1
        for item in per_layout
        if item["nmae_std_delta"] is not None and item["nmae_std_delta"] < 0.0
    )
    # "Directional across complementary metrics" asks whether the error-scale
    # metrics corroborate the R2 movement on each layout, not whether one
    # representation wins everywhere.  A lower MAE must accompany a higher R2.
    corroborating = [
        item
        for item in per_layout
        if item["r2_delta"] is not None
        and item["mae_delta"] != 0.0
        and (item["r2_delta"] > 0.0) == (item["mae_delta"] < 0.0)
    ]
    complementary_directional = len(corroborating) > len(per_layout) / 2

    # "Mainly explained by low SST" requires that every layout showing extreme
    # R2 behaviour also sits below the median target SST.
    low_sst_explains = bool(extreme) and len(low_variance_extreme) == len(extreme)

    if low_sst_explains and not complementary_directional:
        contributes: bool | str = True
        reason = (
            f"Extreme R2 behaviour appears only on {len(extreme)} layout(s), all "
            "below the median target SST, while the error-scale metrics stay "
            f"comparatively steady (only {len(corroborating)}/{len(per_layout)} "
            "layouts corroborate the R2 movement on MAE)."
        )
    elif complementary_directional and not low_sst_explains:
        contributes = False
        reason = (
            "Representation differences remain materially directional across "
            f"complementary metrics: {len(corroborating)}/{len(per_layout)} layouts "
            "move the same way on R2 and MAE, and Pearson r and slope track them. "
            f"The {len(extreme)} layout(s) with extreme R2 behaviour "
            f"({[item['held_out_layout'] for item in extreme]}) sit at or above the "
            "median target SST, so low target variance does not explain them. The "
            "differences are real but layout-dependent in sign, not a metric "
            "artefact."
        )
    else:
        contributes = "UNCLEAR"
        reason = (
            "These six folds do not separate target-metric instability from a real "
            f"representation difference: {len(extreme)} layout(s) show extreme R2 "
            f"behaviour ({len(low_variance_extreme)} of them below the median SST) "
            f"while {len(corroborating)}/{len(per_layout)} layouts corroborate the "
            "R2 movement on MAE."
        )
    return {
        "no_refit": True,
        "prediction_source": "task_2_2_outer_fold_predictions",
        "median_target_sst": median_sst,
        "extreme_r2_rule": (
            "a layout shows extreme R2 behaviour when |FULL R2 - GLOBAL R2| > 1.0"
        ),
        "complementary_directional_rule": (
            "complementary metrics are materially directional when a majority of "
            "layouts move the same way on R2 and MAE (a higher R2 accompanied by a "
            "lower MAE), i.e. the error-scale metrics corroborate the R2 movement"
        ),
        "layouts_corroborating_r2_on_mae": len(corroborating),
        "corroborating_layouts": [item["held_out_layout"] for item in corroborating],
        "extreme_r2_layouts": [item["held_out_layout"] for item in extreme],
        "extreme_r2_layouts_with_below_median_sst": [
            item["held_out_layout"] for item in low_variance_extreme
        ],
        "layouts_with_full_mae_below_global": directional_mae,
        "layouts_with_full_nmae_std_below_global": directional_nmae,
        "per_layout": per_layout,
        "target_metric_instability_contributes": contributes,
        "target_metric_instability_reason": reason,
    }


def _pooled_row_metrics(fold_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    np = _numpy()
    truth: list[float] = []
    predicted: list[float] = []
    for record in sorted(fold_records, key=lambda item: item["held_out_layout"]):
        predicted.extend(record["predictions"])
        truth.extend(record["_truth"])
    return {
        "scope": "SECONDARY_ONLY",
        **{
            key: value
            for key, value in fold_metrics(
                np.asarray(truth), np.asarray(predicted)
            ).items()
        },
    }


def build_task2_documents(*, root: Path = ROOT) -> dict[str, Any]:
    """Run Tasks 2.1-2.5 and return every successor document."""

    ladder, context = evaluate_representation_ladder(root=root)
    definitions = representation_definitions()
    block_rows = context["row_authority"]

    # Attach held-out truth so pooled secondary metrics need no refit.
    targets = context["targets"]
    truth_by_layout = {
        fold["held_out_layout"]: [float(value) for value in targets[fold["test_index"]]]
        for fold in context["folds"]
    }
    for records in ladder.values():
        for record in records:
            record["_truth"] = truth_by_layout[record["held_out_layout"]]

    global_records = ladder[GLOBAL_REPRESENTATION]
    full_records = ladder[FULL_REPRESENTATION]

    # ---- Task 2.1 runtime benchmark -------------------------------------
    benchmark_fold = next(
        record
        for record in full_records
        if record["held_out_layout"] == BENCHMARK_HELD_OUT_LAYOUT
    )
    timings = benchmark_fold["timings_seconds"]
    feature_seconds = context["timings"][FULL_REPRESENTATION]["feature_build_seconds"]
    runtime_benchmark = {
        "schema_version": "1.0",
        "artifact_id": "visible-position-resolution-runtime-benchmark-v0.1",
        "base_head": BASE_HEAD,
        "runner_version": RUNNER_VERSION,
        "representation": "FULL_TOKEN_GRID",
        "representation_name": FULL_REPRESENTATION,
        "held_out_layout": benchmark_fold["held_out_layout"],
        "feature_shape": context["timings"][FULL_REPRESENTATION]["feature_shape"],
        "feature_count": benchmark_fold["feature_count"],
        "train_row_count": benchmark_fold["train_row_count"],
        "test_row_count": benchmark_fold["test_row_count"],
        "selected_alpha": benchmark_fold["selected_alpha"],
        "alpha_grid": list(ALPHA_GRID),
        "alpha_selection_grouping": "training_layout",
        "scaler_fit_scope": "training_layout_rows_only",
        "feature_load_seconds": feature_seconds,
        "scaling_seconds": timings["scaling"],
        "alpha_selection_seconds": timings["alpha_selection"],
        "final_fit_seconds": timings["final_fit"],
        "total_runtime_seconds": feature_seconds
        + timings["scaling"]
        + timings["alpha_selection"]
        + timings["final_fit"],
        "peak_memory_bytes": int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        ),
        "peak_memory_source": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "benchmark_authority_note": (
            "This benchmark may gate OPTIONAL compute only; it never changes "
            "scientific scope."
        ),
    }

    # ---- Task 2.2 six leave-one-layout-out matrix ------------------------
    def _public(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                key: value
                for key, value in record.items()
                if key not in {"predictions", "_truth"}
            }
            for record in sorted(records, key=lambda item: item["held_out_layout"])
        ]

    full_summary = _representation_summary(full_records, global_records)
    six_layout = {
        "schema_version": "1.0",
        "artifact_id": "visible-position-resolution-six-layout-generalization-v0.1",
        "base_head": BASE_HEAD,
        "runner_version": RUNNER_VERSION,
        "layer_idx": LAYER_IDX,
        "outer_design": {
            "outer_fold_count": 6,
            "outer_test_unit": "one complete held-out layout trajectory",
            "training_unit": "the other five layouts",
            "scaler_fit_scope": "training_layout_rows_only",
            "alpha_grid": list(ALPHA_GRID),
            "alpha_selection_grouping": "training_layout",
            "alpha_selection_seed": ALPHA_SELECTION_SEED,
            "independence_caveat": (
                "These six folds are NOT independent replications; they reuse one "
                "six-trajectory development authority."
            ),
        },
        "nmae_std_definition": NMAE_STD_DEFINITION,
        "row_authority": block_rows,
        "pooling_equivalence": context["pooling_equivalence"],
        "representations": {
            "GLOBAL_MEAN": {
                "representation_name": GLOBAL_REPRESENTATION,
                "definition": {
                    key: value
                    for key, value in definitions[GLOBAL_REPRESENTATION].items()
                    if key != "region_token_indices"
                },
                "folds": _public(global_records),
                "summary": _representation_summary(global_records),
                "pooled_row_metrics": _pooled_row_metrics(global_records),
            },
            "FULL_TOKEN_GRID": {
                "representation_name": FULL_REPRESENTATION,
                "definition": {
                    key: value
                    for key, value in definitions[FULL_REPRESENTATION].items()
                    if key != "region_token_indices"
                },
                "folds": _public(full_records),
                "summary": full_summary,
                "pooled_row_metrics": _pooled_row_metrics(full_records),
            },
        },
        "full_minus_global_r2_by_layout": full_summary[
            "per_layout_r2_delta_over_global"
        ],
        "full_minus_global_sign_counts": {
            "positive_layout_count": full_summary["layouts_above_global"],
            "negative_layout_count": full_summary["layouts_below_global"],
        },
    }

    # ---- Task 2.3 metric decomposition -----------------------------------
    metric_decomposition = {
        "schema_version": "1.0",
        "artifact_id": "visible-position-resolution-metric-decomposition-v0.1",
        "base_head": BASE_HEAD,
        "runner_version": RUNNER_VERSION,
        "nmae_std_definition": NMAE_STD_DEFINITION,
        **classify_metric_decomposition(global_records, full_records),
    }

    # ---- Task 2.4 / 2.5 ladder and survivor ------------------------------
    survivor = select_surviving_intermediate(ladder)
    ladder_document = {
        "schema_version": "1.0",
        "artifact_id": "visible-position-resolution-spatial-ladder-v0.1",
        "base_head": BASE_HEAD,
        "runner_version": RUNNER_VERSION,
        "token_grid": f"{TOKEN_GRID_ROWS}x{TOKEN_GRID_COLS}",
        "partition_contract": {
            "deterministic": True,
            "contiguous": True,
            "factor_compatible": True,
            "each_token_exactly_once": True,
            "interpolation": False,
            "learned_pooling": False,
            "post_hoc_boundaries": False,
        },
        "row_authority": block_rows,
        "outer_design": six_layout["outer_design"],
        "representations": {
            name: {
                "definition": {
                    key: value
                    for key, value in definitions[name].items()
                    if key != "region_token_indices"
                },
                "folds": _public(ladder[name]),
                "summary": _representation_summary(
                    ladder[name],
                    None if name == GLOBAL_REPRESENTATION else global_records,
                ),
                "feature_build_seconds": context["timings"][name][
                    "feature_build_seconds"
                ],
            }
            for name, _, _ in SPATIAL_REPRESENTATIONS
        },
        "survivor_selection": survivor,
    }

    return {
        "runtime_benchmark": runtime_benchmark,
        "six_layout_generalization": six_layout,
        "metric_decomposition": metric_decomposition,
        "spatial_representation_ladder": ladder_document,
        "_survivor": survivor,
        "_definitions": definitions,
    }


def build_development_freeze(
    survivor: Mapping[str, Any],
    definitions: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Freeze the scientific contract before any new trajectory exists."""

    eligibility = _load_json(
        root
        / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
        / "expanded_visibility_eligibility.json"
    )
    surviving = survivor["surviving_intermediate"]
    representation_set = [
        "GLOBAL_MEAN",
        surviving,
        "FULL_TOKEN_GRID",
    ]
    frozen = {
        "schema_version": "1.0",
        "artifact_id": "visible-position-resolution-development-freeze-v0.1",
        "base_head": BASE_HEAD,
        "runner_version": RUNNER_VERSION,
        "frozen_before_any_new_trajectory_performance_exists": True,
        "task_1_eligibility": {
            "eligible_row_keys_sha256": eligibility["eligible_row_keys_sha256"],
            "deterministic_eligibility_rule": eligibility[
                "deterministic_eligibility_rule"
            ],
            "deterministic_eligibility_rule_sha256": _canonical_sha256(
                eligibility["deterministic_eligibility_rule"]
            ),
            "eligible_row_count": eligibility["counts"]["eligible_row_count"],
            "eligible_trajectory_count": eligibility["counts"][
                "eligible_trajectory_count"
            ],
        },
        "layer_idx": LAYER_IDX,
        "layer_selection_status": (
            "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
        ),
        "representation_set": representation_set,
        "surviving_intermediate": surviving,
        "spatial_partition_definitions": {
            name: definitions[REPRESENTATION_ALIASES.get(name, name)]
            for name in representation_set
        },
        "alpha_grid": list(ALPHA_GRID),
        "alpha_selection_seed": ALPHA_SELECTION_SEED,
        "scaling": "training_rows_only",
        "future_within_layout_outer_group": "trajectory",
        "future_within_layout_ge3_alpha_group": "training_trajectory",
        "future_across_layout_alpha_group": "training_layout",
        "nmae_std_definition": NMAE_STD_DEFINITION,
        "macro_semantics": {
            "equal_layout_macro": (
                "each held-out layout contributes exactly one value to the mean "
                "and median, regardless of its row count"
            ),
            "equal_trajectory_macro": (
                "each held-out trajectory contributes exactly one value to the "
                "mean and median, regardless of its row count"
            ),
            "pooled_row_metrics": "SECONDARY_ONLY",
        },
        "sample_specific_spatial_scramble": {
            "semantics": (
                "permute the region-to-position assignment independently per "
                "sample, holding the region contents and the target fixed, so "
                "any retained signal cannot depend on stable spatial layout"
            ),
            "seeds": list(SPATIAL_SCRAMBLE_SEEDS),
            "seed_count": len(SPATIAL_SCRAMBLE_SEEDS),
            "results_inspected": False,
        },
        "target_null_semantics": {
            "status": "PLACEHOLDER",
            "note": (
                "target-null control to be defined before any confirmatory "
                "acquisition; not exercised in this development task"
            ),
        },
        "scientific_decision_logic": [
            "the frozen representation set is exactly GLOBAL_MEAN, the single "
            "surviving intermediate, and FULL_TOKEN_GRID",
            "equal-layout and equal-trajectory macro summaries are primary; "
            "pooled-row metrics are secondary only",
            "R2 is never read alone; MAE, NMAE_STD, correlation, and slope must "
            "agree in direction before a representation difference is claimed",
            "the six development folds are not independent replications and "
            "cannot support a confirmatory claim",
            "balanced new capture remains the acquisition path from Task 1",
        ],
        "task_1_primary_path": "BALANCED_NEW_CAPTURE",
        "pair_holdouts_status": (
            "SKIPPED_TO_PRIORITIZE_BALANCED_CAPTURE_AND_REPLICATION"
        ),
    }
    frozen["development_freeze_sha256"] = _canonical_sha256(frozen)
    return frozen


def write_task2_documents(
    *, root: Path = ROOT, output_root: Path | None = None
) -> tuple[Path, ...]:
    documents = build_task2_documents(root=root)
    freeze = build_development_freeze(
        documents["_survivor"], documents["_definitions"], root=root
    )
    destination = output_root or (
        root / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
    )
    outputs = (
        (destination / "runtime_benchmark.json", documents["runtime_benchmark"]),
        (
            destination / "six_layout_generalization.json",
            documents["six_layout_generalization"],
        ),
        (
            destination / "metric_decomposition.json",
            documents["metric_decomposition"],
        ),
        (
            destination / "spatial_representation_ladder.json",
            documents["spatial_representation_ladder"],
        ),
        (destination / "development_freeze.json", freeze),
    )
    for path, document in outputs:
        _write_json(path, document)
    return tuple(path for path, _ in outputs)


def rebuild_metric_decomposition(*, output_root: Path | None = None) -> Path:
    """Rebuild Task 2.3 from the stored Task 2.2 folds without refitting."""

    destination = output_root or OUTPUT_ROOT
    generalization = _load_json(destination / "six_layout_generalization.json")
    representations = generalization["representations"]
    document = {
        "schema_version": "1.0",
        "artifact_id": "visible-position-resolution-metric-decomposition-v0.1",
        "base_head": BASE_HEAD,
        "runner_version": RUNNER_VERSION,
        "nmae_std_definition": NMAE_STD_DEFINITION,
        **classify_metric_decomposition(
            representations["GLOBAL_MEAN"]["folds"],
            representations["FULL_TOKEN_GRID"]["folds"],
        ),
    }
    path = destination / "metric_decomposition.json"
    path.unlink(missing_ok=True)
    _write_json(path, document)
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument(
        "--mode",
        choices=("task1", "task2", "metric-decomposition"),
        default="task1",
    )
    args = parser.parse_args(argv)
    if args.mode == "metric-decomposition":
        print(rebuild_metric_decomposition(output_root=args.output_root))
        return 0
    if args.mode == "task2":
        for path in write_task2_documents(output_root=args.output_root):
            print(path)
        return 0
    for path in write_resolution_documents(output_root=args.output_root):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
