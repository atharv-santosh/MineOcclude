"""CPU-only Phase 1 Step 1.7 synthetic cross-role integration pipeline."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mineocclude.contracts.activation import validate_activation_handoff
from mineocclude.contracts.intervention_request import validate_intervention_request
from mineocclude.contracts.rollout_registry import validate_rollout_registry_bundle
from mineocclude.contracts.trajectory import validate_trajectory_package


ROOT = Path(__file__).resolve().parents[3]

DEFAULT_BUNDLE_PATH = (
    ROOT / "tests" / "fixtures" / "integration" / "synthetic_cross_role_bundle.json"
)

DEFAULT_REPORT_PATH = (
    ROOT / "tests" / "fixtures" / "integration" / "synthetic_join_report.json"
)

FIXTURE_MARKER = {
    "synthetic": True,
    "scientific_use": "forbidden",
}

JOIN_FIELD_TYPES = {
    "trajectory_id": "str",
    "model_frame_idx": "int",
    "event_id": "str",
    "dose_id": "str",
    "input_context_id": "str",
    "run_id": "str",
    "output_artifact_id": "str",
    "artifact_id": "str",
    "rollout_id": "str",
    "input_context_artifact_id": "str",
    "intervention_request_artifact_id": "str",
}


def sha256_bytes(value: bytes) -> str:
    """Return the SHA-256 digest for one byte payload."""

    return hashlib.sha256(value).hexdigest()


def parse_json_bytes(path: Path) -> tuple[dict[str, Any], str]:
    """Read once, hash those exact bytes, and parse JSON from the same bytes."""

    payload = path.read_bytes()
    return json.loads(payload.decode("utf-8")), sha256_bytes(payload)


def write_json(path: Path, value: Any) -> None:
    """Write deterministic JSON."""

    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, indent=2, sort_keys=True)
        file.write("\n")


def serialize_validation_result(result: Any) -> dict[str, Any]:
    """Convert one validation result into JSON-safe report data."""

    return {
        "accepted": bool(result.accepted),
        "rejections": [
            {
                "code": getattr(rejection.code, "value", str(rejection.code)),
                "message": rejection.message,
            }
            for rejection in result.rejections
        ],
    }


def load_pipeline_inputs(
    bundle_path: Path = DEFAULT_BUNDLE_PATH,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str]]:
    """Load the bundle and all referenced documents using single-read hashes."""

    bundle, _ = parse_json_bytes(bundle_path)

    sources = bundle.get("sources")
    if not isinstance(sources, Mapping):
        raise ValueError("Integration bundle sources must be a mapping.")

    documents: dict[str, dict[str, Any]] = {}
    source_hashes: dict[str, str] = {}

    for source_name, relative_path in sources.items():
        if not isinstance(source_name, str):
            raise ValueError("Integration source names must be strings.")

        if not isinstance(relative_path, str):
            raise ValueError(
                f"Integration source {source_name!r} must have a string path."
            )

        source_path = (bundle_path.parent / relative_path).resolve()
        document, source_hash = parse_json_bytes(source_path)

        documents[source_name] = document
        source_hashes[source_name] = source_hash

    return bundle, documents, source_hashes


def key_value_is_valid(field: str, value: Any) -> bool:
    """Return True only for exact typed join-key values."""

    expected = JOIN_FIELD_TYPES.get(field)

    if expected == "str":
        return isinstance(value, str) and bool(value.strip())

    if expected == "int":
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    return False


def make_key(row: Mapping[str, Any], fields: Sequence[str]) -> tuple[Any, ...] | None:
    """Build one exact typed join key."""

    values: list[Any] = []

    for field in fields:
        if field not in row:
            return None

        value = row[field]

        if not key_value_is_valid(field, value):
            return None

        values.append(value)

    return tuple(values)


def build_index(
    rows: Sequence[Any],
    fields: Sequence[str],
) -> tuple[dict[tuple[Any, ...], list[int]], list[int]]:
    """Index rows by exact typed join key."""

    index: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    invalid_rows: list[int] = []

    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            invalid_rows.append(row_index)
            continue

        key = make_key(row, fields)

        if key is None:
            invalid_rows.append(row_index)
            continue

        index[key].append(row_index)

    return dict(index), invalid_rows


def serialize_key(key: tuple[Any, ...]) -> list[Any]:
    """Serialize one tuple key for JSON output."""

    return list(key)


def join_report(
    *,
    name: str,
    left_name: str,
    right_name: str,
    left_rows: Sequence[Any],
    right_rows: Sequence[Any],
    left_key_fields: Sequence[str],
    relationship: str,
    right_key_fields: Sequence[str] | None = None,
    require_all_left: bool = True,
    require_all_right: bool = True,
    expected_right_per_left: int | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Produce a machine-readable exact-key join report."""

    if right_key_fields is None:
        right_key_fields = left_key_fields

    left_index, invalid_left_rows = build_index(left_rows, left_key_fields)
    right_index, invalid_right_rows = build_index(right_rows, right_key_fields)

    left_keys = set(left_index)
    right_keys = set(right_index)
    common_keys = left_keys & right_keys
    left_only = left_keys - right_keys
    right_only = right_keys - left_keys

    cardinality_mismatches: list[dict[str, Any]] = []

    for key in sorted(common_keys, key=repr):
        left_count = len(left_index[key])
        right_count = len(right_index[key])
        expected = relationship
        mismatch = False

        if relationship == "one_to_one":
            mismatch = left_count != 1 or right_count != 1

        elif relationship == "one_to_many":
            mismatch = left_count != 1 or right_count < 1

            if expected_right_per_left is not None:
                mismatch = mismatch or right_count != expected_right_per_left
                expected = f"one_to_many:{expected_right_per_left}"

        elif relationship == "many_to_one":
            mismatch = left_count < 1 or right_count != 1

        else:
            raise ValueError(f"Unsupported join relationship: {relationship!r}")

        if mismatch:
            cardinality_mismatches.append(
                {
                    "key": serialize_key(key),
                    "left_count": left_count,
                    "right_count": right_count,
                    "expected": expected,
                }
            )

    duplicate_left_keys = [
        {"key": serialize_key(key), "count": len(indices)}
        for key, indices in left_index.items()
        if len(indices) > 1
    ]

    duplicate_right_keys = [
        {"key": serialize_key(key), "count": len(indices)}
        for key, indices in right_index.items()
        if len(indices) > 1
    ]

    joined_rows = sum(
        len(left_index[key]) * len(right_index[key])
        for key in common_keys
    )

    empty_failure = not allow_empty and (not left_rows or not right_rows)
    no_common_key_failure = not allow_empty and not common_keys

    missing_key_failure = (
        (require_all_left and bool(left_only))
        or (require_all_right and bool(right_only))
    )

    passed = not (
        invalid_left_rows
        or invalid_right_rows
        or cardinality_mismatches
        or empty_failure
        or no_common_key_failure
        or missing_key_failure
    )

    return {
        "name": name,
        "left_table": left_name,
        "right_table": right_name,
        "left_join_fields": list(left_key_fields),
        "right_join_fields": list(right_key_fields),
        "relationship": relationship,
        "left_input_rows": len(left_rows),
        "right_input_rows": len(right_rows),
        "joined_rows": joined_rows,
        "common_key_count": len(common_keys),
        "missing_from_right": [
            serialize_key(key)
            for key in sorted(left_only, key=repr)
        ],
        "missing_from_left": [
            serialize_key(key)
            for key in sorted(right_only, key=repr)
        ],
        "duplicate_left_keys": duplicate_left_keys,
        "duplicate_right_keys": duplicate_right_keys,
        "invalid_left_rows": invalid_left_rows,
        "invalid_right_rows": invalid_right_rows,
        "cardinality_mismatches": cardinality_mismatches,
        "empty_input_failure": empty_failure,
        "no_common_key_failure": no_common_key_failure,
        "status": "passed" if passed else "failed",
    }


def integrity_check(name: str, passed: bool, details: Any) -> dict[str, Any]:
    """Create one machine-readable integrity check."""

    return {
        "name": name,
        "passed": bool(passed),
        "details": details,
    }


def check_fixture_markers(
    bundle: dict[str, Any],
    documents: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Verify generated evidence is clearly marked synthetic."""

    generated_names = {
        "token_map",
        "oracle_targets",
        "baseline_predictions",
        "fit_manifest",
        "validation_manifest",
        "intervention_request",
        "input_contexts",
        "rollout_manifest",
        "registry",
        "measurements",
    }

    mismatches: list[str] = []

    if bundle.get("fixture_metadata") != FIXTURE_MARKER:
        mismatches.append("bundle.fixture_metadata")

    if bundle.get("synthetic_marker_scope") != "document_and_nested_records":
        mismatches.append("bundle.synthetic_marker_scope")

    for name in generated_names:
        document = documents.get(name)

        if not isinstance(document, Mapping):
            mismatches.append(name)
            continue

        if document.get("fixture_metadata") != FIXTURE_MARKER:
            mismatches.append(f"{name}.fixture_metadata")

    return integrity_check(
        "all_generated_evidence_is_explicitly_synthetic",
        not mismatches,
        {"marker_mismatches": mismatches},
    )


def expected_join_metadata() -> dict[str, list[str]]:
    """Return the complete documented join map required by Step 1.7."""

    return {
        "trajectory_to_normalized_actions": ["trajectory_id", "model_frame_idx"],
        "trajectory_to_token_map": ["trajectory_id", "model_frame_idx"],
        "trajectory_to_targets": ["trajectory_id", "model_frame_idx"],
        "targets_to_activations": ["trajectory_id", "model_frame_idx"],
        "targets_to_baselines": ["trajectory_id", "model_frame_idx"],
        "request_heldout_events_to_rollouts": ["event_id"],
        "request_alpha_table_to_rollouts": ["dose_id"],
        "contexts_to_rollouts": ["input_context_id"],
        "rollouts_to_runs": ["run_id"],
        "rollouts_to_input_context_artifacts": [
            "input_context_artifact_id",
            "artifact_id",
        ],
        "rollouts_to_intervention_request_artifacts": [
            "intervention_request_artifact_id",
            "artifact_id",
        ],
        "rollouts_to_output_artifacts": ["output_artifact_id", "artifact_id"],
        "rollouts_to_measurements": ["rollout_id"],
    }


def expected_integrity_links() -> list[str]:
    """Return the complete documented non-generic integrity-link list."""

    return [
        "expected_activation_sites_to_activation_rows",
        "token_map_positions_to_mineworld_layout",
        "fit_manifest_hash_to_file_bytes",
        "validation_manifest_hash_to_file_bytes",
        "request_manifest_metadata_to_manifest_files",
        "input_context_hash_to_file_bytes",
        "intervention_request_hash_to_file_bytes",
        "logical_input_context_rows_to_rollouts",
        "rollout_measurement_failure_semantics",
        "orphaned_claim_bearing_row_enumeration",
    ]


def check_explicit_join_metadata(bundle: dict[str, Any]) -> dict[str, Any]:
    """Verify the bundle documents every join and integrity link."""

    actual_joins = bundle.get("explicit_join_keys")
    actual_links = bundle.get("documented_integrity_links")

    passed = (
        actual_joins == expected_join_metadata()
        and actual_links == expected_integrity_links()
    )

    return integrity_check(
        "explicit_join_keys_and_integrity_links_are_documented",
        passed,
        {
            "expected_join_keys": expected_join_metadata(),
            "actual_join_keys": actual_joins,
            "expected_integrity_links": expected_integrity_links(),
            "actual_integrity_links": actual_links,
        },
    )


def read_expected_activation_sites(bundle: dict[str, Any]) -> tuple[set[tuple[int, str]], list[str]]:
    """Read expected activation sites from the independent integration spec."""

    errors: list[str] = []
    expected_sites: set[tuple[int, str]] = set()

    value = bundle.get("expected_activation_sites")

    if not isinstance(value, list) or not value:
        return set(), ["expected_activation_sites must be a non-empty list."]

    for index, site in enumerate(value):
        if not isinstance(site, Mapping):
            errors.append(f"expected_activation_sites[{index}] must be a mapping.")
            continue

        layer_idx = site.get("layer_idx")
        hook_site = site.get("hook_site")

        if not isinstance(layer_idx, int) or isinstance(layer_idx, bool) or layer_idx < 0:
            errors.append(f"expected_activation_sites[{index}].layer_idx is invalid.")
            continue

        if not isinstance(hook_site, str) or not hook_site.strip():
            errors.append(f"expected_activation_sites[{index}].hook_site is invalid.")
            continue

        pair = (layer_idx, hook_site)

        if pair in expected_sites:
            errors.append(f"Duplicate expected activation site: {pair!r}.")

        expected_sites.add(pair)

    return expected_sites, errors


def check_activation_site_coverage(
    target_rows: Sequence[Any],
    activation_rows: Sequence[Any],
    expected_sites: set[tuple[int, str]],
    site_errors: Sequence[str],
) -> dict[str, Any]:
    """Require every target frame to have exactly the expected activation sites."""

    activations_by_frame: dict[tuple[Any, ...], list[tuple[Any, Any]]] = defaultdict(list)

    for row in activation_rows:
        if not isinstance(row, Mapping):
            continue

        key = make_key(row, ("trajectory_id", "model_frame_idx"))

        if key is None:
            continue

        activations_by_frame[key].append((row.get("layer_idx"), row.get("hook_site")))

    mismatches: list[dict[str, Any]] = []

    for target in target_rows:
        if not isinstance(target, Mapping):
            continue

        key = make_key(target, ("trajectory_id", "model_frame_idx"))

        if key is None:
            continue

        actual_sites = activations_by_frame.get(key, [])
        actual_counts = Counter(actual_sites)

        missing_sites = sorted(expected_sites - set(actual_sites), key=repr)
        unexpected_sites = sorted(set(actual_sites) - expected_sites, key=repr)

        duplicate_sites = [
            {
                "layer_idx": site[0],
                "hook_site": site[1],
                "count": count,
            }
            for site, count in actual_counts.items()
            if count > 1
        ]

        if (
            missing_sites
            or unexpected_sites
            or duplicate_sites
            or len(actual_sites) != len(expected_sites)
        ):
            mismatches.append(
                {
                    "frame_key": list(key),
                    "missing_sites": [
                        {"layer_idx": site[0], "hook_site": site[1]}
                        for site in missing_sites
                    ],
                    "unexpected_sites": [
                        {"layer_idx": site[0], "hook_site": site[1]}
                        for site in unexpected_sites
                    ],
                    "duplicate_sites": duplicate_sites,
                }
            )

    return integrity_check(
        "exact_activation_site_coverage",
        not site_errors and not mismatches,
        {
            "site_errors": list(site_errors),
            "expected_sites": [
                {"layer_idx": layer_idx, "hook_site": hook_site}
                for layer_idx, hook_site in sorted(expected_sites)
            ],
            "mismatches": mismatches,
        },
    )


def check_token_map_semantics(token_map: dict[str, Any]) -> dict[str, Any]:
    """Verify stored token ranges obey the locked MineWorld 336+11 layout."""

    mismatches: list[dict[str, Any]] = []

    for row_index, row in enumerate(token_map.get("rows", [])):
        if not isinstance(row, Mapping):
            mismatches.append({"row_index": row_index, "reason": "row_not_mapping"})
            continue

        frame_idx = row.get("model_frame_idx")

        if not isinstance(frame_idx, int) or isinstance(frame_idx, bool) or frame_idx < 0:
            mismatches.append({"row_index": row_index, "reason": "bad_model_frame_idx"})
            continue

        pair_start = frame_idx * 347
        expected_visual = list(range(pair_start, pair_start + 336))
        expected_action = list(range(pair_start + 336, pair_start + 347))

        visual = row.get("frame_token_positions")
        action = row.get("action_token_positions")

        if visual != expected_visual:
            mismatches.append(
                {
                    "row_index": row_index,
                    "reason": "visual_token_positions_mismatch",
                }
            )

        if action != expected_action:
            mismatches.append(
                {
                    "row_index": row_index,
                    "reason": "action_token_positions_mismatch",
                }
            )

        if row.get("frame_token_count") != 336:
            mismatches.append({"row_index": row_index, "reason": "bad_visual_count"})

        if row.get("action_token_count") != 11:
            mismatches.append({"row_index": row_index, "reason": "bad_action_count"})

        if row.get("state_action_token_count") != 347:
            mismatches.append({"row_index": row_index, "reason": "bad_pair_count"})

        if isinstance(visual, list) and isinstance(action, list):
            if set(visual) & set(action):
                mismatches.append({"row_index": row_index, "reason": "visual_action_overlap"})

            if visual + action != list(range(pair_start, pair_start + 347)):
                mismatches.append({"row_index": row_index, "reason": "pair_gap_or_overlap"})

    return integrity_check(
        "token_map_matches_mineworld_layout",
        not mismatches,
        {"mismatches": mismatches},
    )


def compare_manifest_metadata(
    request_manifest: dict[str, Any],
    actual_manifest: dict[str, Any],
    actual_hash: str,
) -> list[str]:
    """Compare request manifest metadata to an actual manifest document."""

    mismatches: list[str] = []

    if request_manifest.get("manifest_hash") != actual_hash:
        mismatches.append("manifest_hash")

    if request_manifest.get("manifest_id") != actual_manifest.get("manifest_id"):
        mismatches.append("manifest_id")

    actual_event_ids = [
        row.get("event_id")
        for row in actual_manifest.get("events", [])
    ]

    if request_manifest.get("event_ids") != actual_event_ids:
        mismatches.append("event_ids")

    return mismatches


def check_request_manifest_metadata(
    request: dict[str, Any],
    documents: dict[str, dict[str, Any]],
    source_hashes: dict[str, str],
) -> dict[str, Any]:
    """Verify request manifest IDs, event IDs, and hashes resolve exactly."""

    mismatches = {
        "fit_manifest": compare_manifest_metadata(
            request["fit_manifest"],
            documents["fit_manifest"],
            source_hashes["fit_manifest"],
        ),
        "validation_manifest": compare_manifest_metadata(
            request["validation_manifest"],
            documents["validation_manifest"],
            source_hashes["validation_manifest"],
        ),
    }

    failed = {
        name: values
        for name, values in mismatches.items()
        if values
    }

    return integrity_check(
        "request_manifest_metadata_resolves",
        not failed,
        {"mismatches": failed},
    )


def check_registry_input_hashes(
    rollout_manifest: dict[str, Any],
    registry: dict[str, Any],
    source_hashes: dict[str, str],
) -> dict[str, Any]:
    """Verify registry hashes match the actual request/context file bytes."""

    artifacts = {
        row["artifact_id"]: row
        for row in registry.get("artifacts", [])
        if isinstance(row, Mapping) and "artifact_id" in row
    }

    request_hash = source_hashes["intervention_request"]
    context_hash = source_hashes["input_contexts"]
    mismatches: list[dict[str, Any]] = []

    for rollout in rollout_manifest["rollout_rows"]:
        request_id = rollout["intervention_request_artifact_id"]
        context_id = rollout["input_context_artifact_id"]

        request_artifact = artifacts.get(request_id)
        context_artifact = artifacts.get(context_id)

        if request_artifact is None or request_artifact.get("sha256") != request_hash:
            mismatches.append(
                {
                    "rollout_id": rollout["rollout_id"],
                    "reason": "intervention_request_file_hash_mismatch",
                }
            )

        if (
            context_artifact is None
            or context_artifact.get("sha256") != context_hash
            or rollout.get("input_context_hash") != context_hash
        ):
            mismatches.append(
                {
                    "rollout_id": rollout["rollout_id"],
                    "reason": "input_context_file_hash_mismatch",
                }
            )

    return integrity_check(
        "registry_input_hashes_match_actual_file_bytes",
        not mismatches,
        {"mismatches": mismatches},
    )


def check_intervention_rollout_alignment(
    request: dict[str, Any],
    rollout_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Verify every rollout exactly agrees with the B-to-A request."""

    heldout_by_event = {
        row["event_id"]: row
        for row in request["heldout_events"]
    }

    dose_by_id = {
        row["dose_id"]: row
        for row in request["alpha_table"]
    }

    location = request["intervention_location"]
    direction_version = request["direction_metadata"]["direction_version"]
    mismatches: list[dict[str, Any]] = []

    for rollout in rollout_manifest["rollout_rows"]:
        rollout_id = rollout["rollout_id"]
        event = heldout_by_event.get(rollout["event_id"])

        if event is None:
            mismatches.append({"rollout_id": rollout_id, "reason": "event_not_heldout"})
        elif (
            event["trajectory_id"] != rollout["trajectory_id"]
            or event["layout_id"] != rollout["layout_id"]
        ):
            mismatches.append(
                {
                    "rollout_id": rollout_id,
                    "reason": "heldout_event_identity_mismatch",
                }
            )

        dose = dose_by_id.get(rollout["dose_id"])

        if dose is None:
            mismatches.append({"rollout_id": rollout_id, "reason": "dose_missing"})
        else:
            for field in (
                "alpha_requested",
                "alpha_applied",
                "cap_reduced",
                "intended_block_shift",
            ):
                if rollout[field] != dose[field]:
                    mismatches.append(
                        {
                            "rollout_id": rollout_id,
                            "reason": "dose_metadata_mismatch",
                            "field": field,
                            "rollout_value": rollout[field],
                            "request_value": dose[field],
                        }
                    )

        for field in ("layer_idx", "hook_site", "timestep_idx"):
            if rollout[field] != location[field]:
                mismatches.append(
                    {
                        "rollout_id": rollout_id,
                        "reason": "intervention_location_mismatch",
                        "field": field,
                    }
                )

        if rollout["direction_version"] != direction_version:
            mismatches.append(
                {
                    "rollout_id": rollout_id,
                    "reason": "direction_version_mismatch",
                }
            )

    return integrity_check(
        "intervention_request_matches_rollouts",
        not mismatches,
        {"mismatches": mismatches},
    )


def check_context_resolution(
    contexts: dict[str, Any],
    rollout_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Verify every logical input context resolves exactly once."""

    context_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in contexts["rows"]:
        context_by_id[row["input_context_id"]].append(row)

    mismatches: list[dict[str, Any]] = []

    for rollout in rollout_manifest["rollout_rows"]:
        matches = context_by_id.get(rollout["input_context_id"], [])

        if len(matches) != 1:
            mismatches.append(
                {
                    "rollout_id": rollout["rollout_id"],
                    "reason": "input_context_does_not_resolve_once",
                    "match_count": len(matches),
                }
            )
            continue

        context = matches[0]

        for field in (
            "event_id",
            "episode_id",
            "trajectory_id",
            "model_frame_idx",
            "seed",
        ):
            if context[field] != rollout[field]:
                mismatches.append(
                    {
                        "rollout_id": rollout["rollout_id"],
                        "reason": "input_context_identity_mismatch",
                        "field": field,
                        "context_value": context[field],
                        "rollout_value": rollout[field],
                    }
                )

    return integrity_check(
        "logical_input_contexts_resolve_exactly",
        not mismatches,
        {"mismatches": mismatches},
    )


def check_measurement_semantics(
    rollout_manifest: dict[str, Any],
    measurements: dict[str, Any],
) -> dict[str, Any]:
    """Verify Person E placeholders preserve all outcome semantics."""

    rollout_by_id = {
        row["rollout_id"]: row
        for row in rollout_manifest["rollout_rows"]
    }

    seen_measurement_ids: set[str] = set()
    mismatches: list[dict[str, Any]] = []

    for measurement in measurements["rows"]:
        measurement_id = measurement.get("measurement_id")

        if not isinstance(measurement_id, str) or not measurement_id.strip():
            mismatches.append({"measurement_id": measurement_id, "reason": "bad_measurement_id"})
        elif measurement_id in seen_measurement_ids:
            mismatches.append({"measurement_id": measurement_id, "reason": "duplicate_measurement_id"})
        else:
            seen_measurement_ids.add(measurement_id)

        rollout = rollout_by_id.get(measurement["rollout_id"])

        if rollout is None:
            mismatches.append(
                {
                    "measurement_id": measurement_id,
                    "reason": "unknown_rollout",
                }
            )
            continue

        for field in ("event_id", "run_id", "output_artifact_id", "outcome"):
            if measurement[field] != rollout[field]:
                mismatches.append(
                    {
                        "measurement_id": measurement_id,
                        "reason": "rollout_measurement_identity_mismatch",
                        "field": field,
                    }
                )

        outcome = rollout["outcome"]
        displacement = measurement["displacement_blocks"]

        if outcome == "measurable_continuation":
            if (
                measurement["measurement_status"] != "measured"
                or not isinstance(displacement, (int, float))
                or isinstance(displacement, bool)
                or not math.isfinite(float(displacement))
            ):
                mismatches.append(
                    {
                        "measurement_id": measurement_id,
                        "reason": "measurable_continuation_not_measured",
                    }
                )

        elif outcome == "non_persistence":
            if (
                measurement["measurement_status"] != "not_measurable_non_persistence"
                or displacement is not None
            ):
                mismatches.append(
                    {
                        "measurement_id": measurement_id,
                        "reason": "non_persistence_encoded_as_measurement",
                    }
                )

        elif outcome == "generation_failure":
            if measurement["measurement_status"] != "generation_failed" or displacement is not None:
                mismatches.append(
                    {
                        "measurement_id": measurement_id,
                        "reason": "generation_failure_encoded_as_measurement",
                    }
                )

    return integrity_check(
        "measurement_failure_semantics_are_preserved",
        not mismatches,
        {"mismatches": mismatches},
    )


def collect_orphaned_claim_bearing_rows(
    documents: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Explicitly enumerate claim-bearing rows that fail key provenance links."""

    trajectory_keys = {
        make_key(row, ("trajectory_id", "model_frame_idx"))
        for row in documents["trajectory_package"]["streams"]["frame_map"]
    }

    activation_keys = {
        make_key(row, ("trajectory_id", "model_frame_idx"))
        for row in documents["activation_handoff"]["index_rows"]
    }

    target_keys = {
        make_key(row, ("trajectory_id", "model_frame_idx"))
        for row in documents["oracle_targets"]["rows"]
    }

    baseline_keys = {
        make_key(row, ("trajectory_id", "model_frame_idx"))
        for row in documents["baseline_predictions"]["rows"]
    }

    run_ids = {
        row["run_id"]
        for row in documents["registry"]["runs"]
        if isinstance(row, Mapping) and isinstance(row.get("run_id"), str)
    }

    artifact_ids = {
        row["artifact_id"]
        for row in documents["registry"]["artifacts"]
        if isinstance(row, Mapping) and isinstance(row.get("artifact_id"), str)
    }

    context_ids = {
        row["input_context_id"]
        for row in documents["input_contexts"]["rows"]
        if isinstance(row, Mapping) and isinstance(row.get("input_context_id"), str)
    }

    rollout_ids = {
        row["rollout_id"]
        for row in documents["rollout_manifest"]["rollout_rows"]
        if isinstance(row, Mapping) and isinstance(row.get("rollout_id"), str)
    }

    measurement_rollout_ids = {
        row["rollout_id"]
        for row in documents["measurements"]["rows"]
        if isinstance(row, Mapping) and isinstance(row.get("rollout_id"), str)
    }

    orphans: list[dict[str, Any]] = []

    for target in documents["oracle_targets"]["rows"]:
        key = make_key(target, ("trajectory_id", "model_frame_idx"))

        if key not in trajectory_keys:
            orphans.append({"table": "oracle_targets", "id": target.get("target_id"), "missing": "trajectory_frame"})

        if key not in activation_keys:
            orphans.append({"table": "oracle_targets", "id": target.get("target_id"), "missing": "activation_rows"})

        if key not in baseline_keys:
            orphans.append({"table": "oracle_targets", "id": target.get("target_id"), "missing": "baseline_prediction"})

    for baseline in documents["baseline_predictions"]["rows"]:
        key = make_key(baseline, ("trajectory_id", "model_frame_idx"))

        if key not in target_keys:
            orphans.append(
                {
                    "table": "baseline_predictions",
                    "id": baseline.get("baseline_prediction_id"),
                    "missing": "oracle_target",
                }
            )

    for rollout in documents["rollout_manifest"]["rollout_rows"]:
        rollout_id = rollout.get("rollout_id")

        if rollout.get("run_id") not in run_ids:
            orphans.append({"table": "rollout_rows", "id": rollout_id, "missing": "run"})

        if rollout.get("input_context_artifact_id") not in artifact_ids:
            orphans.append(
                {
                    "table": "rollout_rows",
                    "id": rollout_id,
                    "missing": "input_context_artifact",
                }
            )

        if rollout.get("intervention_request_artifact_id") not in artifact_ids:
            orphans.append(
                {
                    "table": "rollout_rows",
                    "id": rollout_id,
                    "missing": "intervention_request_artifact",
                }
            )

        if rollout.get("input_context_id") not in context_ids:
            orphans.append(
                {
                    "table": "rollout_rows",
                    "id": rollout_id,
                    "missing": "logical_input_context",
                }
            )

        if rollout.get("output_artifact_id") is not None and rollout.get("output_artifact_id") not in artifact_ids:
            orphans.append(
                {
                    "table": "rollout_rows",
                    "id": rollout_id,
                    "missing": "output_artifact",
                }
            )

        if rollout_id not in measurement_rollout_ids:
            orphans.append(
                {
                    "table": "rollout_rows",
                    "id": rollout_id,
                    "missing": "measurement",
                }
            )

    for measurement in documents["measurements"]["rows"]:
        if measurement.get("rollout_id") not in rollout_ids:
            orphans.append(
                {
                    "table": "measurements",
                    "id": measurement.get("measurement_id"),
                    "missing": "rollout",
                }
            )

    return orphans


def run_synthetic_pipeline_from_documents(
    bundle: dict[str, Any],
    documents: dict[str, dict[str, Any]],
    source_hashes: dict[str, str],
) -> dict[str, Any]:
    """Run the complete Step 1.7 proof from already loaded evidence."""

    trajectory = documents["trajectory_package"]
    activation = documents["activation_handoff"]
    request = documents["intervention_request"]
    rollout_manifest = documents["rollout_manifest"]
    registry = documents["registry"]

    contract_validations = {
        "trajectory": serialize_validation_result(validate_trajectory_package(trajectory)),
        "activation": serialize_validation_result(validate_activation_handoff(activation)),
        "intervention_request": serialize_validation_result(validate_intervention_request(request)),
        "rollout_registry": serialize_validation_result(
            validate_rollout_registry_bundle(rollout_manifest, registry)
        ),
    }

    frame_map = trajectory["streams"]["frame_map"]
    normalized_actions = trajectory["streams"]["normalized_actions"]
    token_rows = documents["token_map"]["rows"]
    target_rows = documents["oracle_targets"]["rows"]
    activation_rows = activation["index_rows"]
    baseline_rows = documents["baseline_predictions"]["rows"]
    rollout_rows = rollout_manifest["rollout_rows"]
    context_rows = documents["input_contexts"]["rows"]
    measurement_rows = documents["measurements"]["rows"]
    run_rows = registry["runs"]
    artifact_rows = registry["artifacts"]

    expected_activation_sites, activation_site_errors = read_expected_activation_sites(bundle)

    joins = [
        join_report(
            name="trajectory_to_normalized_actions",
            left_name="trajectory.frame_map",
            right_name="trajectory.normalized_actions",
            left_rows=frame_map,
            right_rows=normalized_actions,
            left_key_fields=("trajectory_id", "model_frame_idx"),
            relationship="one_to_one",
        ),
        join_report(
            name="trajectory_to_token_map",
            left_name="trajectory.frame_map",
            right_name="token_map.rows",
            left_rows=frame_map,
            right_rows=token_rows,
            left_key_fields=("trajectory_id", "model_frame_idx"),
            relationship="one_to_one",
        ),
        join_report(
            name="trajectory_to_targets",
            left_name="trajectory.frame_map",
            right_name="oracle_targets.rows",
            left_rows=frame_map,
            right_rows=target_rows,
            left_key_fields=("trajectory_id", "model_frame_idx"),
            relationship="one_to_one",
        ),
        join_report(
            name="targets_to_activations",
            left_name="oracle_targets.rows",
            right_name="activation.index_rows",
            left_rows=target_rows,
            right_rows=activation_rows,
            left_key_fields=("trajectory_id", "model_frame_idx"),
            relationship="one_to_many",
            expected_right_per_left=len(expected_activation_sites),
        ),
        join_report(
            name="targets_to_baselines",
            left_name="oracle_targets.rows",
            right_name="baseline_predictions.rows",
            left_rows=target_rows,
            right_rows=baseline_rows,
            left_key_fields=("trajectory_id", "model_frame_idx"),
            relationship="one_to_one",
        ),
        join_report(
            name="request_heldout_events_to_rollouts",
            left_name="intervention_request.heldout_events",
            right_name="rollout_manifest.rollout_rows",
            left_rows=request["heldout_events"],
            right_rows=rollout_rows,
            left_key_fields=("event_id",),
            relationship="one_to_one",
        ),
        join_report(
            name="request_alpha_table_to_rollouts",
            left_name="intervention_request.alpha_table",
            right_name="rollout_manifest.rollout_rows",
            left_rows=request["alpha_table"],
            right_rows=rollout_rows,
            left_key_fields=("dose_id",),
            relationship="one_to_many",
            require_all_left=False,
            require_all_right=True,
        ),
        join_report(
            name="contexts_to_rollouts",
            left_name="input_contexts.rows",
            right_name="rollout_manifest.rollout_rows",
            left_rows=context_rows,
            right_rows=rollout_rows,
            left_key_fields=("input_context_id",),
            relationship="one_to_one",
        ),
        join_report(
            name="rollouts_to_runs",
            left_name="rollout_manifest.rollout_rows",
            right_name="registry.runs",
            left_rows=rollout_rows,
            right_rows=run_rows,
            left_key_fields=("run_id",),
            relationship="many_to_one",
            require_all_left=True,
            require_all_right=False,
        ),
        join_report(
            name="rollouts_to_input_context_artifacts",
            left_name="rollout_manifest.rollout_rows",
            right_name="registry.artifacts",
            left_rows=rollout_rows,
            right_rows=artifact_rows,
            left_key_fields=("input_context_artifact_id",),
            right_key_fields=("artifact_id",),
            relationship="many_to_one",
            require_all_left=True,
            require_all_right=False,
        ),
        join_report(
            name="rollouts_to_intervention_request_artifacts",
            left_name="rollout_manifest.rollout_rows",
            right_name="registry.artifacts",
            left_rows=rollout_rows,
            right_rows=artifact_rows,
            left_key_fields=("intervention_request_artifact_id",),
            right_key_fields=("artifact_id",),
            relationship="many_to_one",
            require_all_left=True,
            require_all_right=False,
        ),
        join_report(
            name="rollouts_to_output_artifacts",
            left_name="output-bearing rollout rows",
            right_name="registry.artifacts",
            left_rows=[
                row
                for row in rollout_rows
                if row["output_artifact_id"] is not None
            ],
            right_rows=artifact_rows,
            left_key_fields=("output_artifact_id",),
            right_key_fields=("artifact_id",),
            relationship="one_to_one",
            require_all_left=True,
            require_all_right=False,
        ),
        join_report(
            name="rollouts_to_measurements",
            left_name="rollout_manifest.rollout_rows",
            right_name="measurements.rows",
            left_rows=rollout_rows,
            right_rows=measurement_rows,
            left_key_fields=("rollout_id",),
            relationship="one_to_one",
        ),
    ]

    integrity_checks = [
        check_fixture_markers(bundle, documents),
        check_explicit_join_metadata(bundle),
        check_activation_site_coverage(
            target_rows,
            activation_rows,
            expected_activation_sites,
            activation_site_errors,
        ),
        check_token_map_semantics(documents["token_map"]),
        check_request_manifest_metadata(request, documents, source_hashes),
        check_registry_input_hashes(rollout_manifest, registry, source_hashes),
        check_intervention_rollout_alignment(request, rollout_manifest),
        check_context_resolution(documents["input_contexts"], rollout_manifest),
        check_measurement_semantics(rollout_manifest, documents["measurements"]),
    ]

    orphaned_rows = collect_orphaned_claim_bearing_rows(documents)

    contracts_pass = all(result["accepted"] for result in contract_validations.values())
    joins_pass = all(report["status"] == "passed" for report in joins)
    integrity_pass = all(check["passed"] for check in integrity_checks)
    orphan_pass = not orphaned_rows

    overall_pass = contracts_pass and joins_pass and integrity_pass and orphan_pass

    return {
        "schema_version": bundle["schema_version"],
        "integration_id": bundle["integration_id"],
        "fixture_metadata": bundle["fixture_metadata"],
        "overall_status": "passed" if overall_pass else "failed",
        "contract_validations": contract_validations,
        "joins": joins,
        "integrity_checks": integrity_checks,
        "orphaned_claim_bearing_rows": orphaned_rows,
        "summary": {
            "contracts_passed": sum(
                1 for result in contract_validations.values() if result["accepted"]
            ),
            "contracts_total": len(contract_validations),
            "joins_passed": sum(1 for report in joins if report["status"] == "passed"),
            "joins_total": len(joins),
            "integrity_checks_passed": sum(1 for check in integrity_checks if check["passed"]),
            "integrity_checks_total": len(integrity_checks),
            "orphaned_claim_bearing_rows": len(orphaned_rows),
        },
    }


def run_synthetic_pipeline(
    bundle_path: Path = DEFAULT_BUNDLE_PATH,
) -> dict[str, Any]:
    """Run the complete CPU-only Step 1.7 integration proof."""

    bundle, documents, source_hashes = load_pipeline_inputs(bundle_path)

    return run_synthetic_pipeline_from_documents(
        bundle,
        documents,
        source_hashes,
    )


def main() -> None:
    """Run Step 1.7 and save its machine-readable join report."""

    report = run_synthetic_pipeline()

    write_json(DEFAULT_REPORT_PATH, report)

    print("Step 1.7 synthetic integration status:", report["overall_status"])
    print(
        "Contracts:",
        f"{report['summary']['contracts_passed']}/"
        f"{report['summary']['contracts_total']}",
    )
    print(
        "Joins:",
        f"{report['summary']['joins_passed']}/"
        f"{report['summary']['joins_total']}",
    )
    print(
        "Integrity checks:",
        f"{report['summary']['integrity_checks_passed']}/"
        f"{report['summary']['integrity_checks_total']}",
    )
    print("Orphaned rows:", report["summary"]["orphaned_claim_bearing_rows"])
    print("Join report:", DEFAULT_REPORT_PATH)

    if report["overall_status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()