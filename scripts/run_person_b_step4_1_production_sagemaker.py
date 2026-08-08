"""Run the ratified Person B Step 4.1 production probe on SageMaker only.

The preparation task never executes this module.  A later owner-approved run
uses it to authenticate the immutable ten-pilot Activation Store v2 evidence,
join the sealed frame-fold and oracle manifests by exact identity, and fit only
the frozen grouped ridge probes.  It deliberately does not compute metrics or
run Person D baselines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.positive_control_v2 import (
    ALL_PILOT_IDS,
    CORE_PILOT_IDS,
    PERSON_A_TEN_PILOT_COMMIT,
    PERSON_C_ACCEPTANCE_COMMIT,
    validate_ten_pilot_authority_documents,
)
from mineocclude.analysis.production_v2 import (
    COMBINED_ACTIVATION_INDEX_BYTE_SIZE,
    COMBINED_ACTIVATION_INDEX_PATH,
    COMBINED_ACTIVATION_INDEX_SHA256,
    PERSON_B_STEP6_6_PASS_COMMIT,
    PERSON_E_HANDOFF_COMMIT,
    build_production_probe_bridge_v2,
    validate_combined_against_loaded_indices,
    validate_production_activation_store_v2,
)
from mineocclude.contracts.activation_v2 import (
    PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT,
    external_chunk_bindings,
    load_activation_index_v2,
)
from mineocclude.experiments.registry import (
    formatted_json_bytes,
    write_json_exclusive,
)
from mineocclude.oracle.schema import validate_oracle_target_document
from mineocclude.probes.ridge import fit_ridge_oof
from mineocclude.probes.splits import validate_fold_manifest

A_RUNTIME_ROOT = (
    "docs/status/phase6_runtime/"
    "person-a-phase6-ten-pilot-expansion-seed-20260725"
)
C_ACCEPTANCE_PATH = (
    "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/"
    "accepted_pilot_manifest.json"
)
PACKAGE_ROOT = "docs/status/person_b_phase4_step4_1_production_handoff_v0_1"
DEFAULT_OUTPUT_ROOT = Path(
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-production-v0-1"
)


class Step41ProductionRunnerError(RuntimeError):
    """Raised when runtime evidence or authorization fails closed."""


def _fail(message: str) -> None:
    raise Step41ProductionRunnerError(message)


def _git(repository: Path, *arguments: str, text: bool = False) -> bytes | str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=text,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        _fail(f"Git authority read failed: {error}")
    return result.stdout


def _git_bytes(repository: Path, commit: str, path: str) -> bytes:
    payload = _git(repository, "show", f"{commit}:{path}")
    if not isinstance(payload, bytes):
        _fail("Internal Git-object read returned text.")
    return payload


def _decode_object(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{label} is not valid UTF-8 JSON: {error}")
    if not isinstance(document, Mapping):
        _fail(f"{label} must be a JSON object.")
    return document


def _git_json(repository: Path, commit: str, path: str) -> Mapping[str, Any]:
    return _decode_object(
        _git_bytes(repository, commit, path),
        label=f"{commit}:{path}",
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_runtime(repository: Path, ratification_commit: str) -> None:
    if platform.system() != "Linux":
        _fail("Production Step 4.1 is authorized only on the SageMaker Linux host.")
    if not (
        os.environ.get("SM_MODEL_DIR")
        or os.environ.get("SM_NUM_GPUS")
        or Path("/opt/ml").exists()
        or Path("/home/sagemaker-user").exists()
    ):
        _fail("AWS SageMaker runtime identity was not detected.")
    try:
        import torch
    except ImportError as error:
        _fail(f"PyTorch is required for the frozen CUDA precondition: {error}")
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        _fail("cuda:0 is unavailable; local CPU-only execution is forbidden.")
    if _git(repository, "status", "--porcelain", text=True).strip():
        _fail("The Person B SageMaker worktree must be clean.")
    if _git(repository, "branch", "--show-current", text=True).strip() != (
        "role/person-b-analysis"
    ):
        _fail("Production execution must remain on role/person-b-analysis.")
    kind = _git(repository, "cat-file", "-t", ratification_commit, text=True)
    if kind.strip() != "commit":
        _fail("The requested Person B ratification commit is unavailable.")
    head = _git(repository, "rev-parse", "HEAD", text=True).strip()
    if head != ratification_commit:
        _fail("Production execution requires HEAD at the exact ratification commit.")


def _load_ratified_package(
    repository: Path,
    ratification_commit: str,
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any],
]:
    inventory = _git_json(
        repository,
        ratification_commit,
        f"{PACKAGE_ROOT}/sha256_inventory.json",
    )
    declared = inventory.get("files")
    if inventory.get("inventory_excludes_self") is not True or not isinstance(
        declared, Mapping
    ):
        _fail("The ratified package inventory is malformed.")
    documents: dict[str, Mapping[str, Any]] = {}
    for name, expected_hash in declared.items():
        if not isinstance(name, str) or not isinstance(expected_hash, str):
            _fail("The ratified package inventory contains a malformed row.")
        payload = _git_bytes(
            repository,
            ratification_commit,
            f"{PACKAGE_ROOT}/{name}",
        )
        if _sha256(payload) != expected_hash:
            _fail(f"The ratified package hash differs at {name}.")
        document = _decode_object(payload, label=f"ratified package {name}")
        if payload != formatted_json_bytes(document):
            _fail(f"The ratified package is not canonical at {name}.")
        documents[name] = document
    owner = documents.get("owner_ratification.json")
    binding = documents.get("authority_binding.json")
    authorization = documents.get("preparation_runner_authorization.json")
    fold = documents.get("ten_pilot_frame_fold_manifest.json")
    target = documents.get("production_oracle_target_manifest.json")
    if not all(
        isinstance(item, Mapping)
        for item in (owner, binding, authorization, fold, target)
    ):
        _fail("The ratified package lacks required production records.")
    if (
        owner.get("decision")
        != "RATIFY_PERSON_B_STEP4_1_PRODUCTION_INPUTS_AND_EXECUTION"
        or owner.get("production_v2_consumer_ready") is not True
        or owner.get("scientific_execution_performed") is not False
        or owner.get("u4_output_inspected") is not False
        or authorization.get("production_probe_execution_authorized") is not True
        or authorization.get("production_probe_executed") is not False
        or authorization.get("production_metrics_authorized") is not False
        or authorization.get("person_d_baseline_execution_authorized_by_b")
        is not False
        or authorization.get("u4_output_inspected") is not False
        or authorization.get("authorized_environment")
        != "AWS SageMaker Linux GPU"
        or authorization.get("required_device") != "cuda:0"
        or authorization.get("authorized_targets")
        != ["mu_oracle_blocks", "log_sigma_oracle"]
        or authorization.get("combined_activation_index")
        != {
            "byte_size": COMBINED_ACTIVATION_INDEX_BYTE_SIZE,
            "path": COMBINED_ACTIVATION_INDEX_PATH,
            "schema_version": "person-a-combined-activation-index-v2",
            "sha256": COMBINED_ACTIVATION_INDEX_SHA256,
        }
        or binding.get("person_a_activation_store_v2_commit")
        != PERSON_A_TEN_PILOT_COMMIT
        or binding.get("person_b_step6_6_pass_commit")
        != PERSON_B_STEP6_6_PASS_COMMIT
        or binding.get("person_c_expansion_acceptance_commit")
        != PERSON_C_ACCEPTANCE_COMMIT
        or binding.get("person_e_handoff_commit") != PERSON_E_HANDOFF_COMMIT
    ):
        _fail("The ratified execution boundary is missing or expanded.")
    implementation_commit = owner.get("implementation_commit")
    parents = _git(
        repository,
        "show",
        "-s",
        "--format=%P",
        ratification_commit,
        text=True,
    ).strip()
    if parents != implementation_commit:
        _fail("The ratification is not the direct child of its implementation.")
    implementation_files = owner.get("implementation_files")
    if not isinstance(implementation_files, list) or not implementation_files:
        _fail("The ratification does not bind implementation source files.")
    for item in implementation_files:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("sha256"), str)
        ):
            _fail("An implementation source binding is malformed.")
        payload = _git_bytes(
            repository,
            implementation_commit,
            item.get("path"),
        )
        if _sha256(payload) != item.get("sha256"):
            _fail("An implementation source hash differs from ratification.")
    validate_fold_manifest(fold)
    validate_oracle_target_document(
        target,
        analysis_config_path=repository / "configs/analysis/core.yaml",
    )
    return owner, authorization, fold, target


def _load_authority_documents(repository: Path) -> tuple[Any, ...]:
    completion = _git_json(
        repository,
        PERSON_A_TEN_PILOT_COMMIT,
        f"{A_RUNTIME_ROOT}/completion_report.json",
    )
    artifact_manifest = _git_json(
        repository,
        PERSON_A_TEN_PILOT_COMMIT,
        f"{A_RUNTIME_ROOT}/artifact_manifest.json",
    )
    handoff = _git_json(
        repository,
        PERSON_A_TEN_PILOT_COMMIT,
        f"{A_RUNTIME_ROOT}/person_b_step6_6_positive_control_handoff.json",
    )
    inventories = {
        trajectory_id: _git_json(
            repository,
            PERSON_A_TEN_PILOT_COMMIT,
            f"{A_RUNTIME_ROOT}/per_pilot_inventories/{trajectory_id}.json",
        )
        for trajectory_id in ALL_PILOT_IDS
    }
    c_acceptance = _git_json(
        repository,
        PERSON_C_ACCEPTANCE_COMMIT,
        C_ACCEPTANCE_PATH,
    )
    return completion, artifact_manifest, handoff, inventories, c_acceptance


def _load_external_activation_evidence(
    inventories: Mapping[str, Mapping[str, Any]],
    *,
    accepted_manifest_by_trajectory: Mapping[str, str],
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    combined_path = Path(COMBINED_ACTIVATION_INDEX_PATH)
    try:
        combined_payload = combined_path.read_bytes()
    except OSError as error:
        _fail(f"Could not read the accepted combined activation index: {error}")
    combined = validate_production_activation_store_v2(
        combined_payload,
        production_input_format_version=(
            "person-b-step4-1-production-input-v0.1"
        ),
        expected_sha256=COMBINED_ACTIVATION_INDEX_SHA256,
        expected_byte_size=COMBINED_ACTIVATION_INDEX_BYTE_SIZE,
        per_pilot_inventories=inventories,
        accepted_manifest_by_trajectory=accepted_manifest_by_trajectory,
    )
    indices = {}
    for trajectory_id in ALL_PILOT_IDS:
        inventory = inventories[trajectory_id]
        index = inventory["activation_index"]
        indices[trajectory_id] = load_activation_index_v2(
            index["path"],
            canonicalization_contract=(
                PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
            ),
            expected_index_sha256=index["sha256"],
            expected_index_byte_size=index["byte_size"],
            expected_trajectory_id=trajectory_id,
            expected_manifest_sha256=accepted_manifest_by_trajectory[trajectory_id],
            chunk_bindings=external_chunk_bindings(inventory["chunks"]),
            retain_vectors=trajectory_id in CORE_PILOT_IDS,
        )
    validate_combined_against_loaded_indices(combined, indices)
    return combined, indices


def _fit_frozen_probes(bridge: Any, implementation_commit: str) -> list[dict[str, Any]]:
    """Fit only frozen OOF ridge probes; intentionally produce no metrics."""

    outputs = []
    for matrix in bridge.matrices:
        fitted = fit_ridge_oof(
            matrix.features,
            matrix.targets,
            matrix.outer_folds,
            matrix.layout_ids,
            alpha_grid=(0.1, 1.0, 10.0, 100.0),
            inner_fold_count=4,
            seed=20260719,
        )
        outputs.append(
            {
                "code_sha": implementation_commit,
                "fold_fits": [
                    {
                        "constant_feature_indices": list(
                            fit.model.scaler.constant_feature_indices
                        ),
                        "inner_fold_count": fit.alpha_selection.inner_fold_count,
                        "outer_fold_idx": fit.outer_fold_idx,
                        "raw_coefficients": list(fit.model.raw_coefficients),
                        "raw_intercept": fit.model.raw_intercept,
                        "scaler_mean": list(fit.model.scaler.mean),
                        "scaler_scale": list(fit.model.scaler.scale),
                        "selected_alpha": fit.alpha_selection.selected_alpha,
                        "test_indices": list(fit.test_indices),
                        "training_indices": list(fit.training_indices),
                        "validation_mse_by_alpha": [
                            {"alpha": alpha, "mse": mse}
                            for alpha, mse in sorted(
                                fit.alpha_selection.mean_mse_by_alpha.items()
                            )
                        ],
                    }
                    for fit in fitted.fits
                ],
                "hook_site": matrix.hook_site,
                "layer_idx": matrix.layer_idx,
                "matrix_hash": matrix.matrix_hash,
                "oof_prediction_rows": [
                    {**dict(metadata), "prediction": prediction}
                    for metadata, prediction in zip(
                        matrix.metadata_rows,
                        fitted.predictions,
                        strict=True,
                    )
                ],
                "target_name": matrix.target_name,
            }
        )
    return outputs


def _write_outputs(
    output_root: Path,
    *,
    ratification_commit: str,
    implementation_commit: str,
    bridge: Any,
    probe_outputs: list[dict[str, Any]],
) -> None:
    if output_root.exists() or output_root.is_symlink():
        _fail(f"No-overwrite output root already exists: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    prediction_document = {
        "fitted_probe_count": len(probe_outputs),
        "implementation_commit": implementation_commit,
        "input_hash": bridge.input_hash,
        "metrics_computed": False,
        "person_b_owner_ratification_commit": ratification_commit,
        "probe_outputs": probe_outputs,
        "schema_id": "person-b-step4-1-production-ridge-oof-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    write_json_exclusive(
        output_root / "fitted_probes_and_predictions.json",
        prediction_document,
    )
    prediction_payload = (output_root / "fitted_probes_and_predictions.json").read_bytes()
    receipt = {
        "activation_chunk_count_verified": bridge.activation_chunk_count_verified,
        "activation_row_count_verified": bridge.activation_row_count_verified,
        "fitted_probe_sha256": _sha256(prediction_payload),
        "hidden_frame_count": bridge.hidden_frame_count,
        "metrics_computed": False,
        "person_d_baselines_executed": False,
        "production_probe_executed": True,
        "schema_id": "person-b-step4-1-production-execution-receipt-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    write_json_exclusive(output_root / "execution_receipt.json", receipt)
    inventory = {
        "files": {
            name: _sha256((output_root / name).read_bytes())
            for name in (
                "execution_receipt.json",
                "fitted_probes_and_predictions.json",
            )
        },
        "inventory_excludes_self": True,
        "schema_id": "person-b-step4-1-production-output-inventory-v0-1",
        "schema_version": "1.0",
    }
    write_json_exclusive(output_root / "sha256_inventory.json", inventory)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ratified Person B Step 4.1 production ridge probes."
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--ratification-commit", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository = args.repository_root.resolve()
    _require_runtime(repository, args.ratification_commit)
    owner, authorization, fold, target = _load_ratified_package(
        repository,
        args.ratification_commit,
    )
    if args.output_root != Path(authorization["authorized_output_root"]):
        _fail("The requested output root differs from the ratified no-overwrite root.")
    implementation_commit = owner["implementation_commit"]
    completion, artifact_manifest, handoff, inventories, c_acceptance = (
        _load_authority_documents(repository)
    )
    authority = validate_ten_pilot_authority_documents(
        completion_report=completion,
        artifact_manifest=artifact_manifest,
        positive_control_handoff=handoff,
        per_pilot_inventories=inventories,
        c_accepted_manifest=c_acceptance,
    )
    _, indices = _load_external_activation_evidence(
        inventories,
        accepted_manifest_by_trajectory=authority.accepted_c_manifest_by_trajectory,
    )
    bridge = build_production_probe_bridge_v2(
        indices,
        authority=authority,
        fold_manifest=fold,
        oracle_target_document=target,
    )
    probe_outputs = _fit_frozen_probes(bridge, implementation_commit)
    _write_outputs(
        args.output_root,
        ratification_commit=args.ratification_commit,
        implementation_commit=implementation_commit,
        bridge=bridge,
        probe_outputs=probe_outputs,
    )
    print(f"PERSON_B_STEP4_1_OUTPUT={args.output_root}")


if __name__ == "__main__":
    main()
