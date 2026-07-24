"""Person B producer-side preparation for roadmap Step 6.6 handoffs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mineocclude.analysis.config import hash_core_analysis_config
from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    is_hex_digest,
    seal_artifact,
    sha256_file,
    sha256_value,
    validate_sealed_artifact,
)
from mineocclude.analysis.selection import (
    SCOPE_HIDDEN_MEAN,
    selected_frame_keys,
    validate_analysis_selection_manifest,
)
from mineocclude.experiments.registry import formatted_json_bytes
from mineocclude.probes.bridge import derive_probe_code_sha, validate_joined_frame_table
from mineocclude.probes.splits import GroupedSplitError, validate_fold_manifest


D_REQUEST_SCHEMA_VERSION = "person-b-to-d-baseline-request-v0.1"
E_REGISTRATION_REQUEST_SCHEMA_VERSION = (
    "person-b-to-e-registration-request-v0.1"
)
PHASE6_HANDOFF_REPORT_SCHEMA_VERSION = "person-b-phase6-handoff-report-v0.1"


class AnalysisHandoffError(ValueError):
    """Raised when an outgoing B handoff is incomplete or unauthenticated."""


def build_d_baseline_request(
    frame_table: Mapping[str, Any],
    fold_manifest: Mapping[str, Any],
    selection_manifest: Mapping[str, Any],
    *,
    artifact_id: str,
) -> dict[str, Any]:
    """Publish D's exact hidden-mean rows, targets, legal inputs, and folds."""

    validate_joined_frame_table(frame_table)
    try:
        validate_fold_manifest(fold_manifest)
    except GroupedSplitError as error:
        raise AnalysisHandoffError(f"Invalid fold manifest: {error}") from error
    if fold_manifest.get("input_manifest_hash") != frame_table.get(
        "artifact_hash"
    ):
        raise AnalysisHandoffError("Fold manifest belongs to another frame table.")
    validate_analysis_selection_manifest(
        selection_manifest,
        frame_table=frame_table,
    )
    keys = set(
        selected_frame_keys(
            selection_manifest,
            scope=SCOPE_HIDDEN_MEAN,
            frame_table=frame_table,
        )
    )
    memberships = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in fold_manifest["memberships"]
    }
    frames = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in frame_table["rows"]
    }
    if not keys <= memberships.keys():
        raise AnalysisHandoffError(
            "D request rows are not completely covered by the fold manifest."
        )

    rows: list[dict[str, Any]] = []
    for key in sorted(keys):
        frame = frames[key]
        membership = memberships[key]
        if membership["layout_id"] != frame["layout_id"]:
            raise AnalysisHandoffError(
                f"Fold and frame layouts disagree for {key!r}."
            )
        rows.append(
            {
                "trajectory_id": key[0],
                "model_frame_idx": key[1],
                "layout_id": frame["layout_id"],
                "fold_idx": membership["fold_idx"],
                "target_name": "mu_oracle_blocks",
                "target_value": frame["mu_oracle_blocks"],
                "target_unit": "blocks",
                "last_visible_position_blocks": frame[
                    "last_visible_position_blocks"
                ],
                "tau_seconds": frame["tau"],
                "visibility": frame["visibility"],
                "duration_seconds": frame["duration"],
                "accepted_manifest_hash": frame["accepted_manifest_hash"],
            }
        )
    try:
        return seal_artifact(
            {
                "artifact_type": "baseline_request_manifest",
                "artifact_id": artifact_id,
                "code_sha": derive_probe_code_sha(),
                "config_hash": hash_core_analysis_config(),
                "input_manifest_hash": frame_table["artifact_hash"],
                "baseline_request_schema_version": D_REQUEST_SCHEMA_VERSION,
                "producer_role": "person_b",
                "consumer_role": "person_d",
                "selection_manifest_hash": selection_manifest["artifact_hash"],
                "fold_manifest_hash": fold_manifest["artifact_hash"],
                "target_name": "mu_oracle_blocks",
                "target_unit": "blocks",
                "requested_baseline_families": [
                    "time_only",
                    "last_seen",
                    "shuffled",
                ],
                "legal_feature_fields": [
                    "last_visible_position_blocks",
                    "tau_seconds",
                    "visibility",
                    "duration_seconds",
                ],
                "forbidden_feature_fields": ["x_true_blocks"],
                "required_prediction_scope": "out_of_fold",
                "required_key_coverage": "exact",
                "rows": rows,
                "synthetic": frame_table["synthetic"],
                "scientific_use": frame_table["scientific_use"],
            }
        )
    except (AnalysisArtifactError, KeyError, TypeError) as error:
        raise AnalysisHandoffError(f"Could not build D request: {error}") from error


_REGISTRY_TYPE_BY_B_ARTIFACT_TYPE = {
    "oracle_target_document": "oracle_target",
    "joined_frame_table": "model_input",
    "pilot_intake_receipt": "diagnostic_log",
    "oracle_audit": "diagnostic_log",
    "filter_audit": "diagnostic_log",
    "analysis_selection_manifest": "model_input",
    "fold_manifest": "model_input",
    "probe_matrix_manifest": "model_input",
    "scaler_manifest": "fitted_probe",
    "ridge_fit_manifest": "fitted_probe",
    "prediction_manifest": "prediction",
    "result_manifest": "metric_table",
    "probe_scope_bundle": "metric_table",
    "u2_calibration_bundle": "metric_table",
    "positive_control_gate": "diagnostic_log",
    "pilot_plumbing_smoke": "diagnostic_log",
    "pilot_failure": "diagnostic_log",
    "baseline_request_manifest": "model_input",
    "cross_role_schema_report": "diagnostic_log",
}


def _artifact_dependencies(
    artifact: Mapping[str, Any],
    artifact_id_by_hash: Mapping[str, str],
    external_artifact_ids_by_hash: Mapping[str, str],
) -> list[str]:
    dependencies: set[str] = set()

    def visit(value: Any, field: str | None = None) -> None:
        if (
            field is not None
            and field.endswith("_hash")
            and is_hex_digest(value, 64)
        ):
            dependency_id = artifact_id_by_hash.get(value)
            if dependency_id is None:
                dependency_id = external_artifact_ids_by_hash.get(value)
            if (
                dependency_id is not None
                and dependency_id != artifact.get("artifact_id")
            ):
                dependencies.add(dependency_id)
            return
        if isinstance(value, Mapping):
            for nested_field, nested_value in value.items():
                visit(nested_value, str(nested_field))
        elif isinstance(value, Sequence) and not isinstance(
            value,
            (str, bytes, bytearray),
        ):
            for nested_value in value:
                visit(nested_value)

    visit(artifact)
    return sorted(dependencies)


def _artifact_schema_version(artifact: Mapping[str, Any]) -> str:
    versions = [
        str(value)
        for field, value in artifact.items()
        if field != "schema_version"
        and field.endswith("_schema_version")
        and isinstance(value, str)
        and value
    ]
    return sorted(versions)[0] if versions else str(artifact["artifact_type"])


def build_e_registration_request(
    artifacts: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    checkpoint_hash: str,
    data_identity_hash: str,
    preprocess_hash: str,
    environment_hash: str,
    command: Sequence[str],
    started_at: str,
    ended_at: str,
    uri_prefix: str,
    git_dirty: bool,
    external_artifact_ids_by_hash: Mapping[str, str] | None = None,
    artifact_bytes_by_id: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Build immutable-registry records for E to validate and append.

    This is a request, not a registry mutation or receipt. Literal JSON bytes
    are hashed exactly as the shared exclusive writer will persist them.
    """

    if not artifacts or any(not isinstance(item, Mapping) for item in artifacts):
        raise AnalysisHandoffError("Registration requires artifact mappings.")
    for name, value in (
        ("run_id", run_id),
        ("started_at", started_at),
        ("ended_at", ended_at),
        ("uri_prefix", uri_prefix),
    ):
        if not isinstance(value, str) or not value.strip():
            raise AnalysisHandoffError(f"{name} must be non-empty.")
    for name, value, length in (
        ("checkpoint_hash", checkpoint_hash, 64),
        ("data_identity_hash", data_identity_hash, 64),
        ("preprocess_hash", preprocess_hash, 64),
        ("environment_hash", environment_hash, 64),
    ):
        if not is_hex_digest(value, length):
            raise AnalysisHandoffError(f"{name} must be SHA-256.")
    if (
        not isinstance(command, Sequence)
        or isinstance(command, (str, bytes))
        or not command
        or any(not isinstance(item, str) or not item for item in command)
    ):
        raise AnalysisHandoffError("command must be a non-empty string list.")
    if not isinstance(git_dirty, bool):
        raise AnalysisHandoffError("git_dirty must be boolean.")
    if not uri_prefix.endswith("/"):
        uri_prefix += "/"
    try:
        parsed_uri = urlparse(uri_prefix)
    except ValueError as error:
        raise AnalysisHandoffError(f"uri_prefix is malformed: {error}") from error
    if (
        any(character.isspace() for character in uri_prefix)
        or (
            len(uri_prefix) >= 2
            and uri_prefix[0].isalpha()
            and uri_prefix[1] == ":"
        )
        or not parsed_uri.scheme
        or not (parsed_uri.netloc or parsed_uri.path)
    ):
        raise AnalysisHandoffError("uri_prefix must be an explicit URI.")
    external = dict(external_artifact_ids_by_hash or {})
    if any(
        not is_hex_digest(hash_value, 64)
        or not isinstance(artifact_id, str)
        or not artifact_id
        for hash_value, artifact_id in external.items()
    ):
        raise AnalysisHandoffError("External artifact hash mapping is invalid.")
    literal_bytes = dict(artifact_bytes_by_id or {})
    if any(
        not isinstance(artifact_id, str)
        or not artifact_id
        or not isinstance(payload, bytes)
        for artifact_id, payload in literal_bytes.items()
    ):
        raise AnalysisHandoffError("Literal artifact-byte mapping is invalid.")

    artifact_id_by_hash: dict[str, str] = {}
    normalized: list[Mapping[str, Any]] = []
    scientific_scopes: set[tuple[bool, str]] = set()
    for artifact in artifacts:
        try:
            validate_sealed_artifact(artifact)
        except AnalysisArtifactError as error:
            raise AnalysisHandoffError(
                f"Registration artifact is invalid: {error}"
            ) from error
        artifact_type = artifact.get("artifact_type")
        if artifact_type not in _REGISTRY_TYPE_BY_B_ARTIFACT_TYPE:
            raise AnalysisHandoffError(
                f"No E registry mapping exists for B artifact {artifact_type!r}."
            )
        artifact_id = artifact.get("artifact_id")
        artifact_hash = artifact.get("artifact_hash")
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or artifact_hash in artifact_id_by_hash
            or artifact_id in artifact_id_by_hash.values()
        ):
            raise AnalysisHandoffError(
                "Artifact IDs and hashes must be unique for registration."
            )
        artifact_id_by_hash[artifact_hash] = artifact_id
        scientific_scopes.add(
            (
                artifact.get("synthetic") is True,
                str(artifact.get("scientific_use")),
            )
        )
        normalized.append(artifact)
    if len(scientific_scopes) != 1 or next(iter(scientific_scopes)) not in {
        (True, "forbidden"),
        (False, "permitted"),
    }:
        raise AnalysisHandoffError(
            "A registration request cannot mix evidence scopes."
        )
    synthetic, scientific_use = next(iter(scientific_scopes))
    if literal_bytes and set(literal_bytes) != {
        artifact["artifact_id"] for artifact in normalized
    }:
        raise AnalysisHandoffError(
            "Literal artifact bytes must exactly cover registered artifacts."
        )

    artifact_records: list[dict[str, Any]] = []
    for artifact in sorted(normalized, key=lambda item: item["artifact_id"]):
        payload = (
            literal_bytes[artifact["artifact_id"]]
            if artifact["artifact_id"] in literal_bytes
            else formatted_json_bytes(artifact)
        )
        try:
            parsed_payload = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AnalysisHandoffError(
                f"Artifact {artifact['artifact_id']!r} bytes are not UTF-8 JSON."
            ) from error
        if parsed_payload != artifact:
            raise AnalysisHandoffError(
                f"Artifact {artifact['artifact_id']!r} bytes differ from its document."
            )
        artifact_records.append(
            {
                "schema_version": "1.0",
                "artifact_schema_version": _artifact_schema_version(artifact),
                "artifact_id": artifact["artifact_id"],
                "direct_input_artifact_ids": _artifact_dependencies(
                    artifact,
                    artifact_id_by_hash,
                    external,
                ),
                "creator_run_id": f"{run_id}:{artifact['artifact_id']}",
                "artifact_type": _REGISTRY_TYPE_BY_B_ARTIFACT_TYPE[
                    artifact["artifact_type"]
                ],
                "uri": uri_prefix + artifact["artifact_id"] + ".json",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
                "status": "accepted",
                "status_authority": "person_b",
                "status_reason": None,
                "superseded_by": None,
            }
        )
    run_records = []
    for record in artifact_records:
        run_records.append(
            {
                "schema_version": "1.0",
                "run_id": record["creator_run_id"],
                "code_sha": derive_probe_code_sha(),
                "git_dirty": git_dirty,
                "config_snapshot_hash": hash_core_analysis_config(),
                "checkpoint_hash": checkpoint_hash,
                "data_identity_hash": data_identity_hash,
                "preprocess_hash": preprocess_hash,
                "environment_hash": environment_hash,
                "seeds": {
                    "outer_split": 20260719,
                    "permutation": 20260720,
                },
                "command": list(command),
                "owner": "person_b",
                "started_at": started_at,
                "ended_at": ended_at,
                "status": "completed",
                "parent_run_id": None,
                "input_artifact_ids": list(
                    record["direct_input_artifact_ids"]
                ),
                "output_artifact_ids": [record["artifact_id"]],
                "failure_reason": None,
                "supersedes_run_id": None,
                "supersession_reason": None,
            }
        )
    request = {
        "schema_version": "1.0",
        "registration_request_schema_version": E_REGISTRATION_REQUEST_SCHEMA_VERSION,
        "producer_role": "person_b",
        "consumer_role": "person_e",
        "synthetic": synthetic,
        "scientific_use": scientific_use,
        "status": "ready_for_e_validation_and_append",
        "is_registry_receipt": False,
        "run_id_prefix": run_id,
        "run_records": run_records,
        "artifact_records": artifact_records,
    }
    request["registration_request_hash"] = sha256_value(request)
    return request


def build_phase6_handoff_report(
    d_request: Mapping[str, Any],
    e_registration_request: Mapping[str, Any],
    *,
    artifact_id: str,
    repository_root: Path | str,
) -> dict[str, Any]:
    """Record B's three outgoing Step 6.6 packets without claiming receipts."""

    try:
        validate_sealed_artifact(
            d_request,
            expected_type="baseline_request_manifest",
        )
    except AnalysisArtifactError as error:
        raise AnalysisHandoffError(f"D request is invalid: {error}") from error
    if (
        not isinstance(e_registration_request, Mapping)
        or e_registration_request.get("registration_request_schema_version")
        != E_REGISTRATION_REQUEST_SCHEMA_VERSION
        or e_registration_request.get("status")
        != "ready_for_e_validation_and_append"
    ):
        raise AnalysisHandoffError("E registration request is malformed.")
    supplied_e_hash = e_registration_request.get("registration_request_hash")
    unhashed_e = dict(e_registration_request)
    unhashed_e.pop("registration_request_hash", None)
    if supplied_e_hash != sha256_value(unhashed_e):
        raise AnalysisHandoffError("E registration request hash is stale.")

    root = Path(repository_root).resolve()
    issue_path = (root / "PERSON_B_ISSUE.md").resolve()
    a_contract_path = (
        root / "docs" / "contracts" / "intervention_request_v1.md"
    ).resolve()
    a_schema_path = (
        root / "src" / "mineocclude" / "contracts" / "intervention_request.py"
    ).resolve()
    for path in (issue_path, a_contract_path, a_schema_path):
        if root not in path.parents or not path.is_file():
            raise AnalysisHandoffError(
                f"Required Person A-readable source is unavailable: {path}."
            )
    synthetic = d_request.get("synthetic") is True
    scientific_use = d_request.get("scientific_use")
    if (
        e_registration_request.get("synthetic") != synthetic
        or e_registration_request.get("scientific_use") != scientific_use
    ):
        raise AnalysisHandoffError("D and E packets use different evidence scopes.")
    return seal_artifact(
        {
            "artifact_type": "cross_role_schema_report",
            "artifact_id": artifact_id,
            "code_sha": derive_probe_code_sha(),
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": sha256_value(
                [d_request["artifact_hash"], supplied_e_hash]
            ),
            "phase6_handoff_report_schema_version": (
                PHASE6_HANDOFF_REPORT_SCHEMA_VERSION
            ),
            "person_d": {
                "request_hash": d_request["artifact_hash"],
                "status": "prepared_awaiting_d_response",
                "required_response_families": d_request[
                    "requested_baseline_families"
                ],
            },
            "person_e": {
                "registration_request_hash": supplied_e_hash,
                "status": "prepared_awaiting_e_validation_and_receipt",
                "requested_artifact_count": len(
                    e_registration_request["artifact_records"]
                ),
            },
            "person_a": {
                "status": "schema_and_issue_sources_published_awaiting_acknowledgement",
                "issue_report": {
                    "path": "PERSON_B_ISSUE.md",
                    "sha256": sha256_file(issue_path),
                },
                "intervention_contract": {
                    "path": "docs/contracts/intervention_request_v1.md",
                    "sha256": sha256_file(a_contract_path),
                },
                "intervention_schema": {
                    "path": "src/mineocclude/contracts/intervention_request.py",
                    "sha256": sha256_file(a_schema_path),
                },
            },
            "receipts": {
                "person_a": None,
                "person_d": None,
                "person_e": None,
            },
            "synthetic": synthetic,
            "scientific_use": scientific_use,
        }
    )
