"""Materialize and validate Person B's frozen Step 4.1 input package.

The command reads A/C/E authorities through exact Git objects.  It never reads
activation vectors, fits a probe, computes production metrics, or touches U4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.coordinates_v2 import (
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE,
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT,
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_DIGEST_DOMAIN,
    PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
    build_state_input_v2_from_capture_bytes,
)
from mineocclude.analysis.positive_control_v2 import (
    ALL_PILOT_IDS,
    validate_ten_pilot_authority_documents,
)
from mineocclude.analysis.production_v2 import (
    COMBINED_ACTIVATION_INDEX_BYTE_SIZE,
    COMBINED_ACTIVATION_INDEX_PATH,
    COMBINED_ACTIVATION_INDEX_SHA256,
    EXPECTED_ADMITTED_FRAME_COUNT,
    EXPECTED_EXCLUDED_FRAME_COUNT,
    EXPECTED_HIDDEN_PRODUCTION_ROWS,
    EXPECTED_SOURCE_FRAME_COUNT,
    PERSON_B_SOURCE_ROW_RATIFICATION_COMMIT,
    PERSON_B_STEP6_6_PASS_COMMIT,
    PERSON_D_RECORDED_AUTHORITY_COMMIT,
    PERSON_E_HANDOFF_COMMIT,
    build_production_oracle_target_document,
    build_ten_pilot_frame_fold_manifest,
)
from mineocclude.experiments.registry import (
    formatted_json_bytes,
    write_json_exclusive,
)
from mineocclude.oracle.schema import validate_oracle_target_document
from mineocclude.probes.splits import validate_fold_manifest

PERSON_A_COMMIT = "55776dc88302b89b52eef483a710fbf6811cf536"
PERSON_C_COMMIT = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"
PERSON_E_PHASE6_ACCEPTANCE_COMMIT = "5bbe7c7021fe3b1c4c35c78fadfbd92ab51484e8"
STARTING_AUTHORITY = "e39fef4a59142a84dfb5991d51deeb506eb23a7b"
A_RUNTIME_ROOT = (
    "docs/status/phase6_runtime/"
    "person-a-phase6-ten-pilot-expansion-seed-20260725"
)
C_ACCEPTANCE_PATH = (
    "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/"
    "accepted_pilot_manifest.json"
)
E_HANDOFF_ROOT = "docs/status/person_e_phase6_to_step4_1_handoff_v0_1"
DEFAULT_OUTPUT_ROOT = (
    ROOT / "docs/status/person_b_phase4_step4_1_production_handoff_v0_1"
)
IMPLEMENTATION_PATHS = (
    "scripts/prepare_person_b_step4_1_production_inputs.py",
    "scripts/run_person_b_step4_1_production_sagemaker.py",
    "src/mineocclude/analysis/production_v2.py",
    "src/mineocclude/oracle/schema.py",
    "src/mineocclude/probes/splits.py",
    "tests/analysis/test_person_b_step4_1_production_v2.py",
)
PACKAGE_FILES = (
    "activation_evidence_manifest.json",
    "authority_binding.json",
    "owner_ratification.json",
    "person_d_readiness_request.json",
    "preparation_runner_authorization.json",
    "production_oracle_target_manifest.json",
    "scientific_contract_binding.json",
    "sha256_inventory.json",
    "ten_pilot_frame_fold_manifest.json",
    "validation_receipt.json",
)


class PreparationError(RuntimeError):
    """Fail-closed preparation or authority error."""


def _fail(message: str) -> None:
    raise PreparationError(message)


def _git(repository: Path, *arguments: str, text: bool = False) -> bytes | str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=text,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        _fail(f"Git authority read failed: {error}")
    return completed.stdout


def _git_bytes(repository: Path, commit: str, path: str) -> bytes:
    value = _git(repository, "show", f"{commit}:{path}")
    if not isinstance(value, bytes):
        _fail("Internal Git byte read returned text.")
    return value


def _git_json(repository: Path, commit: str, path: str) -> Mapping[str, Any]:
    payload = _git_bytes(repository, commit, path)
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"Exact Git object {commit}:{path} is invalid JSON: {error}")
    if not isinstance(document, Mapping):
        _fail(f"Exact Git object {commit}:{path} must be an object.")
    return document


def _git_blob_by_suffix(repository: Path, commit: str, suffix: str) -> bytes:
    listing = _git(repository, "ls-tree", "-r", commit, text=True)
    if not isinstance(listing, str):
        _fail("Internal Git tree read returned bytes.")
    matches: list[str] = []
    for line in listing.splitlines():
        metadata, path = line.split("\t", 1)
        if path.endswith(suffix):
            matches.append(metadata.split()[2])
    if len(matches) != 1:
        _fail(f"Expected one Git blob ending {suffix!r}, found {len(matches)}.")
    payload = _git(repository, "cat-file", "blob", matches[0])
    if not isinstance(payload, bytes):
        _fail("Internal Git blob read returned text.")
    return payload


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_local_json(path: Path) -> tuple[Mapping[str, Any], str, int]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"Could not load local authority {path}: {error}")
    if not isinstance(document, Mapping):
        _fail(f"Local authority {path} must be an object.")
    return document, _sha256(payload), len(payload)


def _require_commits(repository: Path, commits: tuple[str, ...]) -> None:
    for commit in commits:
        kind = _git(repository, "cat-file", "-t", commit, text=True)
        if not isinstance(kind, str) or kind.strip() != "commit":
            _fail(f"Required authority commit is unavailable: {commit}")


def _validate_e_handoff_inventory(repository: Path) -> dict[str, str]:
    inventory = _git_json(
        repository,
        PERSON_E_HANDOFF_COMMIT,
        f"{E_HANDOFF_ROOT}/sha256_inventory.json",
    )
    files = inventory.get("files")
    if (
        inventory.get("inventory_excludes_self") is not True
        or not isinstance(files, Mapping)
    ):
        _fail("Person E handoff inventory is malformed.")
    for name, expected in files.items():
        payload = _git_bytes(
            repository,
            PERSON_E_HANDOFF_COMMIT,
            f"{E_HANDOFF_ROOT}/{name}",
        )
        if _sha256(payload) != expected:
            _fail(f"Person E handoff inventory mismatch at {name}.")
    return dict(files)


def _source_model_identity(repository: Path) -> tuple[str, str, str]:
    suffix = (
        "index-82dc0e18607a1a89135a1a88cbec5d53531682db970e9a1323672e7f4d28677b.json"
    )
    payload = _git_blob_by_suffix(repository, PERSON_A_COMMIT, suffix)
    try:
        index = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"Exact Person A index Git blob is invalid: {error}")
    store = index.get("store_identity")
    if not isinstance(store, Mapping):
        _fail("Exact Person A index lacks store identity.")
    model_hash = store.get("model_hash")
    preprocess_hash = store.get("preprocess_hash")
    if not isinstance(model_hash, str) or not isinstance(preprocess_hash, str):
        _fail("Exact Person A model/preprocess identity is malformed.")
    return model_hash, preprocess_hash, _sha256(payload)


def _canonical_file(path: Path) -> tuple[Mapping[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"Could not validate package file {path}: {error}")
    if not isinstance(document, Mapping) or payload != formatted_json_bytes(document):
        _fail(f"Package file is not canonical formatted JSON: {path.name}")
    return document, payload


def validate_package(
    repository: Path,
    output_root: Path,
    *,
    expected_implementation_commit: str,
) -> dict[str, Any]:
    """Validate one prepared package without reading external activation bytes."""

    actual_files = tuple(sorted(path.name for path in output_root.glob("*.json")))
    if actual_files != tuple(sorted(PACKAGE_FILES)):
        _fail("Prepared package file set is incomplete or contains extras.")
    documents: dict[str, Mapping[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    for name in PACKAGE_FILES:
        document, payload = _canonical_file(output_root / name)
        documents[name] = document
        payloads[name] = payload
    inventory = documents["sha256_inventory.json"]
    declared = inventory.get("files")
    if (
        inventory.get("inventory_excludes_self") is not True
        or not isinstance(declared, Mapping)
        or set(declared) != set(PACKAGE_FILES) - {"sha256_inventory.json"}
    ):
        _fail("Prepared package SHA-256 inventory is malformed.")
    for name, expected in declared.items():
        if _sha256(payloads[name]) != expected:
            _fail(f"Prepared package inventory mismatch at {name}.")
    fold = documents["ten_pilot_frame_fold_manifest.json"]
    target = documents["production_oracle_target_manifest.json"]
    validate_fold_manifest(fold)
    validate_oracle_target_document(
        target,
        analysis_config_path=repository / "configs/analysis/core.yaml",
    )
    if (
        target.get("input_manifest_hash") != fold.get("artifact_hash")
        or len(fold["memberships"]) != len(target["rows"])
        or {
            (row["trajectory_id"], row["model_frame_idx"])
            for row in fold["memberships"]
        }
        != {
            (row["trajectory_id"], row["model_frame_idx"])
            for row in target["rows"]
        }
    ):
        _fail("Prepared fold and oracle target identities do not match.")
    owner = documents["owner_ratification.json"]
    authorization = documents["preparation_runner_authorization.json"]
    if (
        owner.get("implementation_commit") != expected_implementation_commit
        or owner.get("decision")
        != "RATIFY_PERSON_B_STEP4_1_PRODUCTION_INPUTS_AND_EXECUTION"
        or owner.get("scientific_execution_performed") is not False
        or owner.get("u4_output_inspected") is not False
        or authorization.get("implementation_commit")
        != expected_implementation_commit
        or authorization.get("production_probe_execution_authorized") is not True
        or authorization.get("production_probe_executed") is not False
        or authorization.get("production_metrics_authorized") is not False
        or authorization.get("person_d_baseline_execution_authorized_by_b")
        is not False
        or authorization.get("u4_output_inspected") is not False
    ):
        _fail("Prepared owner/execution boundary is invalid.")
    implementation_files = owner.get("implementation_files")
    if not isinstance(implementation_files, list):
        _fail("Owner ratification lacks implementation file identities.")
    for row in implementation_files:
        if not isinstance(row, Mapping):
            _fail("Implementation identity row is malformed.")
        payload = _git_bytes(
            repository,
            expected_implementation_commit,
            row["path"],
        )
        if _sha256(payload) != row.get("sha256"):
            _fail("Implementation source hash does not match its commit.")
    if documents["validation_receipt.json"].get("status") != "PASS":
        _fail("Prepared validation receipt is not PASS.")
    return {
        "fold_sha256": _sha256(
            payloads["ten_pilot_frame_fold_manifest.json"]
        ),
        "target_sha256": _sha256(
            payloads["production_oracle_target_manifest.json"]
        ),
    }


def build_package(
    repository: Path,
    output_root: Path,
    *,
    implementation_commit: str,
) -> dict[str, Any]:
    """Build exact production inputs from committed authorities, no activations."""

    _require_commits(
        repository,
        (
            PERSON_E_HANDOFF_COMMIT,
            PERSON_E_PHASE6_ACCEPTANCE_COMMIT,
            PERSON_A_COMMIT,
            PERSON_C_COMMIT,
            PERSON_B_STEP6_6_PASS_COMMIT,
            PERSON_B_SOURCE_ROW_RATIFICATION_COMMIT,
            PERSON_D_RECORDED_AUTHORITY_COMMIT,
            implementation_commit,
        ),
    )
    e_inventory = _validate_e_handoff_inventory(repository)
    e_handoff = _git_json(
        repository,
        PERSON_E_HANDOFF_COMMIT,
        f"{E_HANDOFF_ROOT}/phase6_artifact_handoff.json",
    )
    if (
        e_handoff.get("accepted_pilot_count") != 10
        or e_handoff.get("activation_row_count") != 37_480
        or e_handoff.get("activation_chunk_count") != 200
        or e_handoff.get("accepted_placeholder_count") != 0
        or e_handoff.get("accepted_activation_index")
        != {
            "accepted_by_commit": PERSON_A_COMMIT,
            "byte_size": COMBINED_ACTIVATION_INDEX_BYTE_SIZE,
            "path": COMBINED_ACTIVATION_INDEX_PATH,
            "producing_commit": PERSON_A_COMMIT,
            "producing_role": "person_a",
            "schema_version": "person-a-combined-activation-index-v2",
            "sha256": COMBINED_ACTIVATION_INDEX_SHA256,
        }
    ):
        _fail("Person E handoff conflicts with the frozen Phase 6 evidence.")
    e_contract = _git_json(
        repository,
        PERSON_E_HANDOFF_COMMIT,
        f"{E_HANDOFF_ROOT}/step4_1_execution_contract.json",
    )
    completion = _git_json(
        repository,
        PERSON_A_COMMIT,
        f"{A_RUNTIME_ROOT}/completion_report.json",
    )
    artifact_manifest = _git_json(
        repository,
        PERSON_A_COMMIT,
        f"{A_RUNTIME_ROOT}/artifact_manifest.json",
    )
    positive_handoff = _git_json(
        repository,
        PERSON_A_COMMIT,
        f"{A_RUNTIME_ROOT}/person_b_step6_6_positive_control_handoff.json",
    )
    inventories = {
        trajectory_id: _git_json(
            repository,
            PERSON_A_COMMIT,
            f"{A_RUNTIME_ROOT}/per_pilot_inventories/{trajectory_id}.json",
        )
        for trajectory_id in ALL_PILOT_IDS
    }
    c_manifest_payload = _git_bytes(repository, PERSON_C_COMMIT, C_ACCEPTANCE_PATH)
    c_manifest = _git_json(repository, PERSON_C_COMMIT, C_ACCEPTANCE_PATH)
    authority = validate_ten_pilot_authority_documents(
        completion_report=completion,
        artifact_manifest=artifact_manifest,
        positive_control_handoff=positive_handoff,
        per_pilot_inventories=inventories,
        c_accepted_manifest=c_manifest,
    )
    selection, selection_hash, selection_size = _load_local_json(
        repository / "data/person_b/phase6_c_intake/condition_selection_source.json"
    )
    fold_plan, fold_plan_hash, fold_plan_size = _load_local_json(
        repository / "data/person_b/phase6_c_intake/layout_fold_plan.json"
    )
    config_payload = (repository / "configs/analysis/core.yaml").read_bytes()
    config_hash = _sha256(config_payload)
    frame_fold = build_ten_pilot_frame_fold_manifest(
        condition_selection=selection,
        frozen_layout_plan=fold_plan,
        c_accepted_manifest=c_manifest,
        per_pilot_inventories=inventories,
        authority=authority,
        code_sha=implementation_commit,
        condition_selection_sha256=selection_hash,
        condition_selection_byte_size=selection_size,
        frozen_layout_plan_sha256=fold_plan_hash,
        frozen_layout_plan_byte_size=fold_plan_size,
        c_accepted_manifest_sha256=_sha256(c_manifest_payload),
        c_accepted_manifest_byte_size=len(c_manifest_payload),
    )
    model_hash, preprocess_hash, source_index_blob_hash = _source_model_identity(
        repository
    )
    c_by_id = {row["trajectory_id"]: row for row in c_manifest["intake_rows"]}
    state_inputs: dict[str, Mapping[str, Any]] = {}
    coordinate_bindings: list[dict[str, Any]] = []
    for trajectory_id in ALL_PILOT_IDS:
        c_row = c_by_id[trajectory_id]
        capture_bytes = _git_bytes(
            repository,
            PERSON_C_COMMIT,
            c_row["capture_package_path"],
        )
        if (
            len(capture_bytes) != c_row["capture_package_byte_size"]
            or _sha256(capture_bytes) != c_row["capture_package_sha256"]
        ):
            _fail("Exact Person C capture bytes do not match accepted authority.")
        coordinate_path = (
            repository
            / "data/person_b/phase6_c_intake/coordinate_frames"
            / f"{trajectory_id}.json"
        )
        coordinate, coordinate_hash, coordinate_size = _load_local_json(
            coordinate_path
        )
        state_inputs[trajectory_id] = build_state_input_v2_from_capture_bytes(
            capture_bytes,
            expected_literal_capture_package_sha256=c_row[
                "capture_package_sha256"
            ],
            coordinate_frame=coordinate,
            model_hash=model_hash,
            preprocess_hash=preprocess_hash,
            source_row_artifact_type=(
                PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE
            ),
            source_row_producer_commit=(
                PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT
            ),
            source_row_canonicalization_contract=(
                PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT
            ),
            source_row_digest_domain=(
                PERSON_A_ACTIVATION_SOURCE_ROW_V2_DIGEST_DOMAIN
            ),
        )
        coordinate_bindings.append(
            {
                "byte_size": coordinate_size,
                "path": coordinate_path.relative_to(repository).as_posix(),
                "sha256": coordinate_hash,
                "trajectory_id": trajectory_id,
            }
        )
    oracle_target = build_production_oracle_target_document(
        state_inputs,
        fold_manifest=frame_fold,
        code_sha=implementation_commit,
        oracle_run_id="person_b_step4_1_production_inputs_v0_1",
        analysis_config_path=repository / "configs/analysis/core.yaml",
    )
    implementation_files = [
        {
            "path": path,
            "sha256": _sha256(
                _git_bytes(repository, implementation_commit, path)
            ),
        }
        for path in IMPLEMENTATION_PATHS
    ]
    activation_pilots = []
    for trajectory_id in ALL_PILOT_IDS:
        inventory = inventories[trajectory_id]
        activation_pilots.append(
            {
                "activation_index": dict(inventory["activation_index"]),
                "activation_row_count": inventory["activation_row_count"],
                "chunks": [dict(chunk) for chunk in inventory["chunks"]],
                "condition_role": inventory["condition_role"],
                "fold_idx": inventory["fold_idx"],
                "frame_count": inventory["frame_count"],
                "layout_id": inventory["layout_id"],
                "trajectory_id": trajectory_id,
            }
        )
    activation_evidence = {
        "accepted_activation_index": {
            "byte_size": COMBINED_ACTIVATION_INDEX_BYTE_SIZE,
            "path": COMBINED_ACTIVATION_INDEX_PATH,
            "schema_version": "person-a-combined-activation-index-v2",
            "sha256": COMBINED_ACTIVATION_INDEX_SHA256,
        },
        "accepted_pilot_count": 10,
        "activation_chunk_count": 200,
        "activation_row_count": 37480,
        "placeholders_created": False,
        "person_a_commit": PERSON_A_COMMIT,
        "pilots": activation_pilots,
        "schema_id": (
            "person-b-phase4-step4-1-production-handoff-v0-1-"
            "activation-evidence-manifest"
        ),
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "u4_output_inspected": False,
    }
    authority_binding = {
        "implementation_commit": implementation_commit,
        "person_a_activation_store_v2_commit": PERSON_A_COMMIT,
        "person_b_source_row_ratification_commit": (
            PERSON_B_SOURCE_ROW_RATIFICATION_COMMIT
        ),
        "person_b_starting_authority": STARTING_AUTHORITY,
        "person_b_step6_6_pass_commit": PERSON_B_STEP6_6_PASS_COMMIT,
        "person_c_expansion_acceptance_commit": PERSON_C_COMMIT,
        "person_d_recorded_authority_commit": PERSON_D_RECORDED_AUTHORITY_COMMIT,
        "person_e_handoff_commit": PERSON_E_HANDOFF_COMMIT,
        "person_e_phase6_acceptance_commit": PERSON_E_PHASE6_ACCEPTANCE_COMMIT,
        "schema_id": (
            "person-b-phase4-step4-1-production-handoff-v0-1-authority-binding"
        ),
        "schema_version": "1.0",
    }
    scientific_contract = {
        "analysis_config": {
            "byte_size": len(config_payload),
            "path": "configs/analysis/core.yaml",
            "sha256": config_hash,
        },
        "condition_selection": {
            "byte_size": selection_size,
            "path": "data/person_b/phase6_c_intake/condition_selection_source.json",
            "sha256": selection_hash,
        },
        "fitted_probe": {
            "alpha_grid": [0.1, 1.0, 10.0, 100.0],
            "analysis_dtype": "float64",
            "feature_width": 2048,
            "inner_fold_count": 4,
            "model_family": "ridge",
            "outer_fold_count": 5,
            "scaler_fit_scope": "outer_training_rows_only",
        },
        "fold_plan": {
            "byte_size": fold_plan_size,
            "path": "data/person_b/phase6_c_intake/layout_fold_plan.json",
            "sha256": fold_plan_hash,
        },
        "frozen_mvp_criteria": e_contract["comparison_and_acceptance"][
            "frozen_mvp_criteria"
        ],
        "metric_families": e_contract["comparison_and_acceptance"][
            "metric_families"
        ],
        "metric_rules": e_contract["comparison_and_acceptance"]["metric_rules"],
        "oracle_method": "primary_scalar_kalman_crosschecked_closed_form",
        "oracle_targets": [
            "mu_oracle_blocks",
            "var_oracle_blocks2",
            "sigma_oracle_blocks",
            "log_sigma_oracle",
            "x_true_blocks",
        ],
        "production_probe_targets": [
            "mu_oracle_blocks",
            "log_sigma_oracle",
        ],
        "random_split_used": False,
        "resampling_rules": e_contract["comparison_and_acceptance"][
            "resampling_rules"
        ],
        "schema_id": (
            "person-b-phase4-step4-1-production-handoff-v0-1-"
            "scientific-contract-binding"
        ),
        "schema_version": "1.0",
        "threshold_criteria": e_contract["comparison_and_acceptance"][
            "frozen_mvp_criteria"
        ],
        "u4_output_inspected": False,
    }
    runner_authorization = {
        "authorized_environment": "AWS SageMaker Linux GPU",
        "authorized_output_root": (
            "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
            "person-b-step4-1-production-v0-1"
        ),
        "authorized_targets": ["mu_oracle_blocks", "log_sigma_oracle"],
        "combined_activation_index": activation_evidence[
            "accepted_activation_index"
        ],
        "command_template": (
            "python scripts/run_person_b_step4_1_production_sagemaker.py "
            "--repository-root \"$PWD\" --ratification-commit "
            "<RATIFICATION_COMMIT> --output-root /home/sagemaker-user/"
            "person-b-step4-1-approved-outputs/"
            "person-b-step4-1-production-v0-1"
        ),
        "implementation_commit": implementation_commit,
        "person_d_baseline_execution_authorized_by_b": False,
        "production_metrics_authorized": False,
        "production_probe_executed": False,
        "production_probe_execution_authorized": True,
        "required_device": "cuda:0",
        "schema_id": (
            "person-b-phase4-step4-1-production-handoff-v0-1-"
            "preparation-runner-authorization"
        ),
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    person_d_request = {
        "activation_artifacts_consumed_directly_by_person_d": False,
        "baseline_execution_performed": False,
        "b_prerequisite_inputs_ready": True,
        "config_sha256": config_hash,
        "fold_artifact_hash": frame_fold["artifact_hash"],
        "oracle_target_artifact_hash": oracle_target["artifact_hash"],
        "required_person_d_action": (
            "Run the frozen scientific readiness gate and require READY with "
            "zero blocked reasons before fitting any baseline."
        ),
        "schema_id": (
            "person-b-phase4-step4-1-production-handoff-v0-1-"
            "person-d-readiness-request"
        ),
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    owner_ratification = {
        "accepted_activation_index_sha256": COMBINED_ACTIVATION_INDEX_SHA256,
        "accepted_pilot_count": 10,
        "activation_chunk_count": 200,
        "activation_row_count": 37480,
        "decision": "RATIFY_PERSON_B_STEP4_1_PRODUCTION_INPUTS_AND_EXECUTION",
        "fold_artifact_hash": frame_fold["artifact_hash"],
        "frozen_folds_preserved": True,
        "frozen_metrics_preserved": True,
        "frozen_target_preserved": True,
        "frozen_threshold_preserved": True,
        "implementation_commit": implementation_commit,
        "implementation_files": implementation_files,
        "oracle_target_artifact_hash": oracle_target["artifact_hash"],
        "owner": "person_b",
        "person_d_handoff_inputs_ready": True,
        "production_v2_consumer_ready": True,
        "scientific_execution_performed": False,
        "schema_id": (
            "person-b-phase4-step4-1-production-handoff-v0-1-owner-ratification"
        ),
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    validation_receipt = {
        "accepted_pilot_count": 10,
        "activation_chunk_count": 200,
        "activation_row_count": 37480,
        "admitted_frame_count": EXPECTED_ADMITTED_FRAME_COUNT,
        "c_git_object_hashes_verified": True,
        "coordinate_bindings": coordinate_bindings,
        "e_handoff_inventory_entry_count": len(e_inventory),
        "excluded_frame_count": EXPECTED_EXCLUDED_FRAME_COUNT,
        "hidden_production_row_count": EXPECTED_HIDDEN_PRODUCTION_ROWS,
        "model_hash": model_hash,
        "person_a_source_index_git_blob_sha256": source_index_blob_hash,
        "preprocess_hash": preprocess_hash,
        "production_metrics_executed": False,
        "production_probe_executed": False,
        "schema_id": (
            "person-b-phase4-step4-1-production-handoff-v0-1-validation-receipt"
        ),
        "schema_version": "1.0",
        "source_frame_count": EXPECTED_SOURCE_FRAME_COUNT,
        "status": "PASS",
        "u4_output_inspected": False,
    }
    documents = {
        "activation_evidence_manifest.json": activation_evidence,
        "authority_binding.json": authority_binding,
        "owner_ratification.json": owner_ratification,
        "person_d_readiness_request.json": person_d_request,
        "preparation_runner_authorization.json": runner_authorization,
        "production_oracle_target_manifest.json": oracle_target,
        "scientific_contract_binding.json": scientific_contract,
        "ten_pilot_frame_fold_manifest.json": frame_fold,
        "validation_receipt.json": validation_receipt,
    }
    if output_root.exists() or output_root.is_symlink():
        _fail(f"Refusing to overwrite existing output root: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    for name, document in documents.items():
        write_json_exclusive(output_root / name, document)
    inventory = {
        "files": {
            name: _sha256((output_root / name).read_bytes())
            for name in sorted(documents)
        },
        "inventory_excludes_self": True,
        "schema_id": (
            "person-b-phase4-step4-1-production-handoff-v0-1-sha256-inventory"
        ),
        "schema_version": "1.0",
    }
    write_json_exclusive(output_root / "sha256_inventory.json", inventory)
    return validate_package(
        repository,
        output_root,
        expected_implementation_commit=implementation_commit,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or validate frozen Person B Step 4.1 production inputs."
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--implementation-commit", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository = args.repository_root.resolve()
    output_root = args.output_root.resolve()
    if args.validate_only:
        result = validate_package(
            repository,
            output_root,
            expected_implementation_commit=args.implementation_commit,
        )
    else:
        head = _git(repository, "rev-parse", "HEAD", text=True)
        if not isinstance(head, str) or head.strip() != args.implementation_commit:
            _fail("Preparation must run at the exact implementation commit.")
        if _git(repository, "status", "--porcelain", text=True).strip():
            _fail("Preparation requires a clean implementation worktree.")
        result = build_package(
            repository,
            output_root,
            implementation_commit=args.implementation_commit,
        )
    print(f"PERSON_B_STEP4_1_FOLD_SHA256={result['fold_sha256']}")
    print(f"PERSON_B_STEP4_1_TARGET_SHA256={result['target_sha256']}")


if __name__ == "__main__":
    main()
