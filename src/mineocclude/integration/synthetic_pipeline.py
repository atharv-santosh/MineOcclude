"""CPU-only Phase 1 Step 1.7 synthetic cross-role integration pipeline."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    seal_artifact,
    sha256_value,
    validate_sealed_artifact,
)
from mineocclude.contracts.activation import validate_activation_handoff
from mineocclude.contracts.identity import REQUIRED_FIELDS
from mineocclude.contracts.intervention_request import validate_intervention_request
from mineocclude.contracts.rollout_registry import validate_rollout_registry_bundle
from mineocclude.contracts.trajectory import validate_trajectory_package
from mineocclude.oracle.schema import OracleValidationError
from mineocclude.oracle.targets import build_regime_a_target_document
from mineocclude.probes.bridge import (
    ProbeBridgeError,
    build_frame_fold_manifest,
    build_joined_frame_table,
    build_probe_ready_matrices,
    run_ridge_oof_probe,
)


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

AUTHENTICATED_BRIDGE_SPEC = {
    "activation_source": "activation_handoff",
    "activation_chunk_source": "activation_chunk",
    "layout_count": 5,
    "fold_count": 5,
    "target_name": "mu_oracle_blocks",
    "fixture_metadata": FIXTURE_MARKER,
}

AUTHENTICATED_BRIDGE_VERSION = "step-1.7-authenticated-a-b-bridge-v0.1"

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


def deterministic_json_bytes(value: Any) -> bytes:
    """Serialize synthetic evidence exactly as the fixture writers do."""

    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


class AuthenticatedBridgeInputError(ValueError):
    """One stable rejection at the Step 1.7 authenticated-bridge boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


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


def _authenticate_loaded_source(
    source_name: str,
    document: Any,
    source_hashes: Mapping[str, str],
) -> str:
    """Bind an in-memory source document back to its exact fixture hash."""

    if not isinstance(document, Mapping):
        raise AuthenticatedBridgeInputError(
            "invalid_bridge_source",
            f"Authenticated bridge source {source_name!r} must be a mapping.",
        )
    declared_hash = source_hashes.get(source_name)
    if not isinstance(declared_hash, str):
        raise AuthenticatedBridgeInputError(
            "missing_bridge_source_hash",
            f"Authenticated bridge source {source_name!r} has no loaded hash.",
        )
    actual_hash = sha256_bytes(deterministic_json_bytes(document))
    if actual_hash != declared_hash:
        raise AuthenticatedBridgeInputError(
            "stale_bridge_source_hash",
            f"Authenticated bridge source {source_name!r} differs from its loaded bytes.",
        )
    return actual_hash


def build_authenticated_probe_bridge_inputs(
    bundle: Mapping[str, Any],
    documents: Mapping[str, Any],
    source_hashes: Mapping[str, str],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, bytes],
    dict[str, Any],
]:
    """Derive the five-layout probe fixture from authenticated A evidence."""

    if bundle.get("authenticated_a_b_bridge") != AUTHENTICATED_BRIDGE_SPEC:
        raise AuthenticatedBridgeInputError(
            "invalid_bridge_spec",
            "The bundle's authenticated A+B bridge specification is missing or changed.",
        )

    activation_source_name = AUTHENTICATED_BRIDGE_SPEC["activation_source"]
    chunk_source_name = AUTHENTICATED_BRIDGE_SPEC["activation_chunk_source"]
    source_package = documents.get(activation_source_name)
    source_chunk = documents.get(chunk_source_name)
    source_activation_hash = _authenticate_loaded_source(
        activation_source_name,
        source_package,
        source_hashes,
    )
    source_chunk_hash = _authenticate_loaded_source(
        chunk_source_name,
        source_chunk,
        source_hashes,
    )

    activation_validation = validate_activation_handoff(source_package)
    if not activation_validation.accepted:
        rejection_codes = sorted(
            {rejection.code.value for rejection in activation_validation.rejections}
        )
        raise AuthenticatedBridgeInputError(
            "invalid_source_activation_handoff",
            "The A source activation handoff was rejected: "
            + ", ".join(rejection_codes),
        )

    descriptors = source_package.get("chunks")
    source_chunk_id = source_chunk.get("chunk_id")
    if not isinstance(descriptors, list) or not isinstance(source_chunk_id, str):
        raise AuthenticatedBridgeInputError(
            "invalid_source_activation_chunk",
            "The A source chunk or its descriptor list is malformed.",
        )
    matching_descriptors = [
        descriptor
        for descriptor in descriptors
        if isinstance(descriptor, Mapping)
        and descriptor.get("chunk_id") == source_chunk_id
    ]
    if len(matching_descriptors) != 1:
        raise AuthenticatedBridgeInputError(
            "invalid_source_activation_chunk",
            "The A source chunk must resolve to exactly one descriptor by chunk ID.",
        )
    source_descriptor = matching_descriptors[0]
    if source_descriptor.get("sha256") != source_chunk_hash:
        raise AuthenticatedBridgeInputError(
            "stale_source_activation_chunk",
            "The literal A chunk hash differs from its handoff descriptor.",
        )

    source_index_rows = source_package.get("index_rows")
    if not isinstance(source_index_rows, list) or not source_index_rows:
        raise AuthenticatedBridgeInputError(
            "invalid_source_activation_handoff",
            "The A source activation handoff has no index rows.",
        )
    source_frame_rows: dict[int, Mapping[str, Any]] = {}
    for row in source_index_rows:
        if not isinstance(row, Mapping):
            raise AuthenticatedBridgeInputError(
                "invalid_source_activation_handoff",
                "Every A source activation index row must be a mapping.",
            )
        model_frame_idx = row.get("model_frame_idx")
        if not isinstance(model_frame_idx, int) or isinstance(model_frame_idx, bool):
            raise AuthenticatedBridgeInputError(
                "invalid_source_activation_handoff",
                "Every A source activation row needs an integer model frame index.",
            )
        source_frame_rows.setdefault(model_frame_idx, row)

    layout_count = AUTHENTICATED_BRIDGE_SPEC["layout_count"]
    lineage_body = {
        "bridge_version": AUTHENTICATED_BRIDGE_VERSION,
        "source_activation_sha256": source_activation_hash,
        "source_chunk_sha256": source_chunk_hash,
        "layout_count": layout_count,
        "fold_count": AUTHENTICATED_BRIDGE_SPEC["fold_count"],
        "target_name": AUTHENTICATED_BRIDGE_SPEC["target_name"],
        "fixture_metadata": FIXTURE_MARKER,
    }
    lineage_hash = sha256_bytes(deterministic_json_bytes(lineage_body))
    accepted_manifest_hash = sha256_bytes(
        deterministic_json_bytes(
            {
                "artifact_type": "synthetic_probe_bridge_accepted_manifest",
                "lineage_hash": lineage_hash,
            }
        )
    )
    identity_suffix = lineage_hash[:12]

    package = deepcopy(source_package)
    package["handoff_id"] = f"synthetic_probe_bridge_handoff_{identity_suffix}"
    package["run_id"] = f"synthetic_probe_bridge_activation_run_{identity_suffix}"
    package["accepted_manifest_hash"] = accepted_manifest_hash
    package["fixture_metadata"] = deepcopy(FIXTURE_MARKER)
    package["source_fixture_lineage"] = {
        **lineage_body,
        "lineage_hash": lineage_hash,
        "source_handoff_id": source_package.get("handoff_id"),
        "source_run_id": source_package.get("run_id"),
    }

    derived_descriptors: list[dict[str, Any]] = []
    derived_index_rows: list[dict[str, Any]] = []
    chunk_payloads: dict[str, bytes] = {}
    state_rows: list[dict[str, Any]] = []

    for layout_index in range(layout_count):
        layout_id = f"synthetic_probe_layout_{layout_index:02d}"
        trajectory_id = f"synthetic_probe_trajectory_{layout_index:02d}"
        episode_id = f"synthetic_probe_episode_{layout_index:02d}"
        chunk_id = f"synthetic_probe_chunk_{identity_suffix}_{layout_index:02d}"

        chunk = deepcopy(source_chunk)
        chunk["chunk_id"] = chunk_id
        chunk["fixture_metadata"] = deepcopy(FIXTURE_MARKER)
        payload = deterministic_json_bytes(chunk)
        chunk_payloads[chunk_id] = payload

        descriptor = deepcopy(dict(source_descriptor))
        descriptor.update(
            {
                "chunk_id": chunk_id,
                "path": f"operational_locator_only_{layout_index:02d}.json",
                "sha256": sha256_bytes(payload),
            }
        )
        derived_descriptors.append(descriptor)

        for source_row in source_index_rows:
            row = deepcopy(dict(source_row))
            row.update(
                {
                    "episode_id": episode_id,
                    "trajectory_id": trajectory_id,
                    "layout_id": layout_id,
                    "run_id": package["run_id"],
                    "accepted_manifest_hash": accepted_manifest_hash,
                    "activation_chunk_id": chunk_id,
                }
            )
            derived_index_rows.append(row)

        visible_anchor = 10.0 + (2.0 * layout_index)
        for model_frame_idx, source_row in sorted(source_frame_rows.items()):
            identity = dict(source_row)
            identity.update(
                {
                    "episode_id": episode_id,
                    "trajectory_id": trajectory_id,
                    "layout_id": layout_id,
                    "run_id": f"synthetic_probe_state_run_{identity_suffix}",
                    "accepted_manifest_hash": accepted_manifest_hash,
                }
            )
            state = {field: identity[field] for field in REQUIRED_FIELDS}
            visible = source_row.get("visibility") == "visible"
            state.update(
                {
                    "accepted_manifest_hash": accepted_manifest_hash,
                    "observed_position_blocks": visible_anchor if visible else None,
                    "x_true_blocks": (
                        visible_anchor
                        if visible
                        else visible_anchor + (0.04 * model_frame_idx)
                    ),
                    "synthetic": True,
                    "scientific_use": "forbidden",
                }
            )
            state_rows.append(state)

    rows_per_layer = Counter(
        str(row["layer_idx"])
        for row in source_index_rows
        if isinstance(row, Mapping) and isinstance(row.get("layer_idx"), int)
    )
    derived_rows_by_layer = {
        layer: count * layout_count
        for layer, count in sorted(rows_per_layer.items())
    }
    activation_row_count = len(source_index_rows) * layout_count
    package["chunks"] = derived_descriptors
    package["index_rows"] = derived_index_rows
    package["cardinality_report"] = {
        "accepted_manifest_rows": len(source_frame_rows) * layout_count,
        "expected_activation_rows": activation_row_count,
        "actual_activation_rows": activation_row_count,
        "expected_rows_by_layer": derived_rows_by_layer,
        "actual_rows_by_layer": deepcopy(derived_rows_by_layer),
    }

    derived_validation = validate_activation_handoff(package)
    if not derived_validation.accepted:
        rejection_codes = sorted(
            {rejection.code.value for rejection in derived_validation.rejections}
        )
        raise AuthenticatedBridgeInputError(
            "invalid_derived_activation_handoff",
            "The derived synthetic activation handoff was rejected: "
            + ", ".join(rejection_codes),
        )

    state_document = {
        "schema_version": "1.0",
        "join_key": ["trajectory_id", "model_frame_idx"],
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "rows": state_rows,
    }
    target_code_sha = hashlib.sha1(
        (ROOT / "src" / "mineocclude" / "oracle" / "targets.py").read_bytes()
    ).hexdigest()
    target_document = build_regime_a_target_document(
        state_document,
        oracle_run_id=f"synthetic_probe_target_run_{identity_suffix}",
        oracle_code_sha=target_code_sha,
    )
    lineage = {
        **lineage_body,
        "lineage_hash": lineage_hash,
        "accepted_manifest_hash": accepted_manifest_hash,
        "source_handoff_id": source_package.get("handoff_id"),
        "source_run_id": source_package.get("run_id"),
        "derived_handoff_id": package["handoff_id"],
        "derived_run_id": package["run_id"],
        "source_chunk_id": source_chunk_id,
        "derived_chunk_hashes": {
            descriptor["chunk_id"]: descriptor["sha256"]
            for descriptor in derived_descriptors
        },
    }
    return package, target_document, chunk_payloads, lineage


def compact_sealed_artifact(
    artifact: Mapping[str, Any],
    *,
    prediction_manifest_hashes: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compact one valid artifact and seal the exact saved representation."""

    validate_sealed_artifact(artifact)
    original_artifact_hash = artifact["artifact_hash"]
    compact = {
        key: deepcopy(value)
        for key, value in artifact.items()
        if key not in {"artifact_hash", "fold_fit_records"}
    }
    fold_fit_records = artifact.get("fold_fit_records")
    if isinstance(fold_fit_records, list):
        fold_summaries: list[dict[str, Any]] = []
        for record in fold_fit_records:
            if not isinstance(record, Mapping):
                raise AnalysisArtifactError(
                    "fold_fit_records must contain only mappings."
                )
            training_membership = record.get("training_membership")
            test_membership = record.get("test_membership")
            training_indices = record.get("training_indices")
            test_indices = record.get("test_indices")
            scaler = record.get("scaler")
            if (
                not isinstance(training_membership, list)
                or not isinstance(test_membership, list)
                or not isinstance(training_indices, list)
                or not isinstance(test_indices, list)
                or not isinstance(scaler, Mapping)
            ):
                raise AnalysisArtifactError(
                    "Fold-fit records require memberships, indices, and scaler metadata."
                )
            fold_summaries.append(
                {
                    "outer_fold_idx": record.get("outer_fold_idx"),
                    "selected_alpha": record.get("selected_alpha"),
                    "mean_mse_by_alpha": deepcopy(record.get("mean_mse_by_alpha")),
                    "inner_fold_count": record.get("inner_fold_count"),
                    "training_row_count": len(training_membership),
                    "test_row_count": len(test_membership),
                    "training_indices_hash": sha256_value(training_indices),
                    "test_indices_hash": sha256_value(test_indices),
                    "training_membership_hash": sha256_value(training_membership),
                    "test_membership_hash": sha256_value(test_membership),
                    "scaler": deepcopy(dict(scaler)),
                }
            )
        compact["fold_fit_records_count"] = len(fold_fit_records)
        compact["fold_fit_records_hash"] = sha256_value(fold_fit_records)
        compact["fold_fit_summaries"] = fold_summaries
    compact["uncompacted_artifact_hash"] = original_artifact_hash
    compact["compaction_version"] = "step-1.7-artifact-compaction-v0.1"
    if prediction_manifest_hashes is not None:
        original_prediction_hashes = compact.get("prediction_manifest_hashes")
        if original_prediction_hashes != list(prediction_manifest_hashes):
            compact["uncompacted_prediction_manifest_hashes"] = deepcopy(
                original_prediction_hashes
            )
        compact["prediction_manifest_hashes"] = list(prediction_manifest_hashes)
    return seal_artifact(compact)


def run_authenticated_a_b_probe_bridge(
    bundle: Mapping[str, Any],
    documents: Mapping[str, Any],
    source_hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Run and serialize the authenticated A-to-B OOF ridge proof."""

    try:
        package, target_document, chunk_payloads, lineage = (
            build_authenticated_probe_bridge_inputs(
                bundle,
                documents,
                source_hashes,
            )
        )
        frame_table = build_joined_frame_table(package, target_document)
        fold_manifest = build_frame_fold_manifest(
            frame_table,
            artifact_id="synthetic_step_1_7_frame_folds_001",
            n_splits=AUTHENTICATED_BRIDGE_SPEC["fold_count"],
        )
        matrices = build_probe_ready_matrices(
            package,
            target_document,
            frame_table,
            fold_manifest,
            chunk_payloads,
            target_name=AUTHENTICATED_BRIDGE_SPEC["target_name"],
        )
        probe_runs = []
        for matrix in matrices:
            artifact_prefix = (
                "synthetic_step_1_7_ridge_"
                f"layer_{matrix.layer_idx}_{matrix.hook_site}"
            )
            execution = run_ridge_oof_probe(
                matrix,
                artifact_id_prefix=artifact_prefix,
            )
            prediction_artifact = compact_sealed_artifact(
                execution.prediction_artifact
            )
            u1_result_artifact = compact_sealed_artifact(
                execution.u1_result_artifact,
                prediction_manifest_hashes=[prediction_artifact["artifact_hash"]],
            )
            probe_runs.append(
                {
                    "layer_idx": matrix.layer_idx,
                    "hook_site": matrix.hook_site,
                    "target_name": matrix.target_name,
                    "matrix_hash": matrix.matrix_hash,
                    "row_count": len(matrix.metadata_rows),
                    "feature_count": len(matrix.features[0]),
                    "folds": sorted(set(matrix.outer_folds)),
                    "activation_chunk_hashes": [
                        {"chunk_id": chunk_id, "sha256": chunk_hash}
                        for chunk_id, chunk_hash in matrix.activation_chunk_hashes
                    ],
                    "prediction_artifact": prediction_artifact,
                    "u1_result_artifact": u1_result_artifact,
                    "synthetic": True,
                    "scientific_use": "forbidden",
                }
            )
    except (AuthenticatedBridgeInputError, ProbeBridgeError, OracleValidationError) as error:
        code = getattr(error, "code", "invalid_authenticated_bridge_input")
        if hasattr(code, "value"):
            code = code.value
        return {
            "bridge_version": AUTHENTICATED_BRIDGE_VERSION,
            "status": "failed",
            "fixture_metadata": deepcopy(FIXTURE_MARKER),
            "rejections": [{"code": str(code), "message": str(error)}],
        }
    except (KeyError, IndexError, TypeError, ValueError, OSError) as error:
        return {
            "bridge_version": AUTHENTICATED_BRIDGE_VERSION,
            "status": "failed",
            "fixture_metadata": deepcopy(FIXTURE_MARKER),
            "rejections": [
                {
                    "code": "invalid_authenticated_bridge_input",
                    "message": str(error),
                }
            ],
        }

    return {
        "bridge_version": AUTHENTICATED_BRIDGE_VERSION,
        "status": "passed",
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "rejections": [],
        "lineage": lineage,
        "frame_table": frame_table,
        "fold_manifest": fold_manifest,
        "probe_runs": probe_runs,
        "summary": {
            "frame_rows": len(frame_table["rows"]),
            "fold_count": fold_manifest["n_splits"],
            "matrix_count": len(matrices),
            "prediction_rows": sum(
                len(run["prediction_artifact"]["rows"])
                for run in probe_runs
            ),
            "sealed_prediction_artifacts": len(probe_runs),
            "sealed_u1_result_artifacts": len(probe_runs),
        },
    }


def check_authenticated_a_b_probe_bridge(
    bridge_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Turn the authenticated probe execution into a required report check."""

    passed = bridge_report.get("status") == "passed"
    summary = bridge_report.get("summary")
    return integrity_check(
        "authenticated_a_b_probe_bridge",
        passed,
        {
            "bridge_version": bridge_report.get("bridge_version"),
            "rejections": bridge_report.get("rejections", []),
            "summary": summary if isinstance(summary, Mapping) else {},
        },
    )


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

    bridge_spec = bundle.get("authenticated_a_b_bridge")
    if (
        not isinstance(bridge_spec, Mapping)
        or bridge_spec.get("fixture_metadata") != FIXTURE_MARKER
    ):
        mismatches.append("bundle.authenticated_a_b_bridge.fixture_metadata")

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
        "authenticated_a_b_probe_bridge",
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
    authenticated_bridge_report = run_authenticated_a_b_probe_bridge(
        bundle,
        documents,
        source_hashes,
    )

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
        check_authenticated_a_b_probe_bridge(authenticated_bridge_report),
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
        "authenticated_a_b_probe_bridge": authenticated_bridge_report,
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
