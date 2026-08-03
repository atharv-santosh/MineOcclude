"""Superseding Person E authorization for the frozen Step 4.1 comparison.

The builder validates the exact preceding E ratification commit and emits only
an execution authority.  It never imports or executes Person B's comparison
implementation, predictions, probes, metrics, confidence intervals, or U4.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mineocclude.experiments.step4_1_implementation_review_v0_1 import (
    BOUNDED_REVEAL_COUNT,
    BOUNDED_REVEAL_SHA256,
    EXACT_COMMAND,
    PERSON_B_IMPLEMENTATION_COMMIT,
    PERSON_B_PREPARATION_COMMIT,
    build_ratification_documents,
    validate_ratification_documents,
)

PERSON_E_IMPLEMENTATION_RATIFICATION_COMMIT = (
    "fb10af5cff3ba91657caab7864a2c9365756ba56"
)
PERSON_E_STARTING_AUTHORITY = "d2a82a09b2f0acf73c9c7d95c1ea2e382a6cc4f7"
PERSON_B_COMPARISON_CONTRACT_COMMIT = "4da02023a376df77eacb48084b1406ec1accfcb1"
PERSON_B_BOUNDED_REVEAL_CONTRACT_COMMIT = (
    "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4"
)
PERSON_E_BOUNDED_REVEAL_AUTHORIZATION_COMMIT = (
    "99fb896ed8e6a3b187272fe078706bc7b17666d8"
)
PERSON_E_COMPARISON_RATIFICATION_COMMIT = (
    "d2a82a09b2f0acf73c9c7d95c1ea2e382a6cc4f7"
)
PERSON_D_COMPLETION_COMMIT = "f89b142a6fdb52c2d238669af8df14061cee5896"
PERSON_D_COMPLETION_MANIFEST_SHA256 = (
    "79c49e7c794f37c4a574dfef365b8183ddb443b246adbe94743dfdf1ff1f4cf5"
)
PERSON_B_PREDICTIONS_SHA256 = (
    "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba"
)
PERSON_B_PREDICTION_COUNT = 27800
FINAL_OUTPUT_ROOT = (
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-final-comparison-v0-1"
)
RATIFICATION_PACKAGE = (
    "docs/status/"
    "person_e_phase4_step4_1_final_comparison_implementation_ratification_v0_1"
)
FINAL_OUTPUT_FILES = [
    "comparison_metric_table.json",
    "paired_test_results.json",
    "confidence_intervals.json",
    "layer_band_decision.json",
    "registry_v2_import_package.json",
    "execution_receipt.json",
    "sha256_inventory.json",
]


class ExecutionAuthorizationError(ValueError):
    """Raised when the exact ratification or authorization differs."""


def _git(repository: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExecutionAuthorizationError(f"Git validation failed: {error}") from error
    return result.stdout.strip()


def _git_bytes(repository: Path, revision: str, path: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=repository,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExecutionAuthorizationError(
            f"Exact Git-object validation failed for {path}: {error}"
        ) from error
    return result.stdout


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_constant(value: str) -> None:
        raise ExecutionAuthorizationError(f"{label} contains {value}.")

    def unique(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ExecutionAuthorizationError(f"{label} repeats {key}.")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=unique,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExecutionAuthorizationError(f"Could not decode {label}: {error}") from error
    if not isinstance(document, Mapping):
        raise ExecutionAuthorizationError(f"{label} is not a JSON object.")
    return document


def validate_implementation_ratification_commit(
    repository: Path,
) -> dict[str, Mapping[str, Any]]:
    """Validate the preceding E ratification only through its exact Git object."""

    parent = _git(
        repository,
        "show",
        "-s",
        "--format=%P",
        PERSON_E_IMPLEMENTATION_RATIFICATION_COMMIT,
    )
    subject = _git(
        repository,
        "show",
        "-s",
        "--format=%s",
        PERSON_E_IMPLEMENTATION_RATIFICATION_COMMIT,
    )
    if parent != PERSON_E_STARTING_AUTHORITY:
        raise ExecutionAuthorizationError("Implementation ratification parent differs.")
    if subject != "Ratify Person B Step 4.1 final comparison implementation":
        raise ExecutionAuthorizationError("Implementation ratification subject differs.")

    inventory = _decode(
        _git_bytes(
            repository,
            PERSON_E_IMPLEMENTATION_RATIFICATION_COMMIT,
            f"{RATIFICATION_PACKAGE}/sha256_inventory.json",
        ),
        label="implementation ratification inventory",
    )
    references = inventory.get("files")
    expected_names = set(build_ratification_documents(repository))
    if (
        inventory.get("inventory_excludes_self") is not True
        or not isinstance(references, Mapping)
        or set(references) != expected_names
    ):
        raise ExecutionAuthorizationError("Implementation ratification inventory differs.")
    documents = {}
    for name in sorted(expected_names):
        reference = references[name]
        payload = _git_bytes(
            repository,
            PERSON_E_IMPLEMENTATION_RATIFICATION_COMMIT,
            f"{RATIFICATION_PACKAGE}/{name}",
        )
        if (
            not isinstance(reference, Mapping)
            or reference.get("byte_size") != len(payload)
            or reference.get("sha256") != _sha256(payload)
        ):
            raise ExecutionAuthorizationError(
                f"Implementation ratification bytes differ at {name}."
            )
        documents[name] = _decode(payload, label=f"ratification {name}")
    try:
        validate_ratification_documents(repository, documents)
    except ValueError as error:
        raise ExecutionAuthorizationError(str(error)) from error
    return documents


def build_execution_authorization(repository: Path) -> dict[str, Any]:
    ratification = validate_implementation_ratification_commit(repository)
    decision = ratification["implementation_ratification.json"]
    if decision.get("final_comparison_implementation_ratified") is not True:
        raise ExecutionAuthorizationError("Implementation ratification decision differs.")
    return {
        "additional_person_a_extraction_authorized": False,
        "authorization_decision": "AUTHORIZE_EXACT_FROZEN_FINAL_COMPARISON_EXECUTION",
        "authorized_command": list(EXACT_COMMAND),
        "authorized_execution_count": 1,
        "authorized_output_root": FINAL_OUTPUT_ROOT,
        "authorized_resume_behavior": "validate-complete-no-write",
        "bounded_reveal_artifact_sha256": BOUNDED_REVEAL_SHA256,
        "bounded_reveal_prediction_count": BOUNDED_REVEAL_COUNT,
        "bounded_reveal_rerun_authorized": False,
        "bounded_reveal_reuse_authorized": True,
        "broad_hidden_state_interpretation_authorized": False,
        "comparison_contract_commit": PERSON_B_COMPARISON_CONTRACT_COMMIT,
        "comparison_ratification_commit": PERSON_E_COMPARISON_RATIFICATION_COMMIT,
        "exact_output_files": list(FINAL_OUTPUT_FILES),
        "exploratory_metrics_authorized": False,
        "final_comparison_implementation_ratified": True,
        "frozen_scientific_contract_unchanged": True,
        "implementation_ratification_commit": (
            PERSON_E_IMPLEMENTATION_RATIFICATION_COMMIT
        ),
        "manual_u4_inspection_authorized": False,
        "person_b_bounded_reveal_contract_commit": (
            PERSON_B_BOUNDED_REVEAL_CONTRACT_COMMIT
        ),
        "person_b_comparison_implementation_commit": PERSON_B_IMPLEMENTATION_COMMIT,
        "person_b_execution_preparation_commit": PERSON_B_PREPARATION_COMMIT,
        "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
        "probe_refitting_authorized": False,
        "schema_id": "person-e-step4-1-final-comparison-execution-authorization-v0-1",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "step4_1_complete": False,
        "supersedes_incomplete_command_interface_at_commit": (
            PERSON_E_COMPARISON_RATIFICATION_COMMIT
        ),
        "supersedes_only_incomplete_command_interface": True,
        "u4_output_inspected": False,
    }


def build_authorization_documents(repository: Path) -> dict[str, dict[str, Any]]:
    authorization = build_execution_authorization(repository)
    return {
        "authority_binding.json": {
            "authorization_commit_semantics": (
                "The Git commit containing this package is the execution authorization "
                "and must directly descend from implementation_ratification_commit."
            ),
            "implementation_ratification_commit": (
                PERSON_E_IMPLEMENTATION_RATIFICATION_COMMIT
            ),
            "person_b_comparison_implementation_commit": (
                PERSON_B_IMPLEMENTATION_COMMIT
            ),
            "person_b_execution_preparation_commit": PERSON_B_PREPARATION_COMMIT,
            "schema_id": "person-e-step4-1-execution-authorization-authority-v0-1",
            "schema_version": "1.0",
            "u4_output_inspected": False,
        },
        "closure_requirements.json": {
            "authorization_does_not_complete_step4_1": True,
            "authorized_output_root": FINAL_OUTPUT_ROOT,
            "decision_vocabulary": ["PASS", "FAIL", "INCONCLUSIVE"],
            "exact_output_files": list(FINAL_OUTPUT_FILES),
            "output_publication": "single_atomic_directory_rename_after_validation",
            "registry_generation": "v2",
            "required_execution_receipt_values": {
                "additional_person_a_extraction_performed": False,
                "bounded_reveal_prediction_count": BOUNDED_REVEAL_COUNT,
                "bounded_reveal_prediction_sha256": BOUNDED_REVEAL_SHA256,
                "bounded_reveal_rerun_performed": False,
                "broad_hidden_state_interpretation": False,
                "exploratory_metrics_computed": False,
                "manual_u4_inspection": False,
                "post_hoc_layer_selection_performed": False,
                "post_hoc_test_selection_performed": False,
                "probe_refit_performed": False,
                "u4_output_inspected": False,
            },
            "resume_behavior": "validate-complete-no-write",
            "schema_id": "person-e-step4-1-final-comparison-closure-requirements-v0-1",
            "schema_version": "1.0",
            "step4_1_complete": False,
            "u4_output_inspected": False,
        },
        "exact_input_bindings.json": {
            "bounded_reveal": {
                "path": (
                    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
                    "person-b-step4-1-bounded-reveal-v0-1/"
                    "post_reveal_predictions.json"
                ),
                "prediction_count": BOUNDED_REVEAL_COUNT,
                "reuse_required": True,
                "sha256": BOUNDED_REVEAL_SHA256,
            },
            "comparison_contract_commit": PERSON_B_COMPARISON_CONTRACT_COMMIT,
            "person_b_bounded_reveal_contract_commit": (
                PERSON_B_BOUNDED_REVEAL_CONTRACT_COMMIT
            ),
            "person_b_predictions": {
                "path": (
                    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
                    "person-b-step4-1-production-v0-1/"
                    "fitted_probes_and_predictions.json"
                ),
                "prediction_count": PERSON_B_PREDICTION_COUNT,
                "sha256": PERSON_B_PREDICTIONS_SHA256,
            },
            "person_d_completion": {
                "commit": PERSON_D_COMPLETION_COMMIT,
                "manifest_sha256": PERSON_D_COMPLETION_MANIFEST_SHA256,
                "root": (
                    "/home/sagemaker-user/person-d-step4-1-approved-outputs/"
                    "person-d-step4-1-production-v0-1"
                ),
            },
            "person_e_bounded_reveal_authorization_commit": (
                PERSON_E_BOUNDED_REVEAL_AUTHORIZATION_COMMIT
            ),
            "person_e_comparison_ratification_commit": (
                PERSON_E_COMPARISON_RATIFICATION_COMMIT
            ),
            "schema_id": "person-e-step4-1-final-comparison-input-bindings-v0-1",
            "schema_version": "1.0",
            "validation_behavior": "fail_closed_on_missing_or_changed_bytes",
        },
        "execution_authorization.json": authorization,
        "validation_receipt.json": {
            "authorization_is_additive": True,
            "bounded_reveal_reuse_binding_exact": True,
            "exact_command_non_placeholder": True,
            "implementation_ratification_exact_git_object_validated": True,
            "schema_id": "person-e-step4-1-execution-authorization-validation-v0-1",
            "schema_version": "1.0",
            "scientific_execution_performed": False,
            "u4_output_inspected": False,
        },
    }


def validate_authorization_documents(
    repository: Path, documents: Mapping[str, Any]
) -> None:
    expected = build_authorization_documents(repository)
    if documents != expected:
        raise ExecutionAuthorizationError("Execution authorization differs.")
    authorization = documents["execution_authorization.json"]
    required_false = (
        "additional_person_a_extraction_authorized",
        "bounded_reveal_rerun_authorized",
        "broad_hidden_state_interpretation_authorized",
        "exploratory_metrics_authorized",
        "manual_u4_inspection_authorized",
        "probe_refitting_authorized",
        "scientific_execution_performed",
        "step4_1_complete",
        "u4_output_inspected",
    )
    if any(authorization[field] is not False for field in required_false):
        raise ExecutionAuthorizationError("A prohibited authorization differs.")
    if (
        authorization["bounded_reveal_reuse_authorized"] is not True
        or authorization["final_comparison_implementation_ratified"] is not True
        or authorization["frozen_scientific_contract_unchanged"] is not True
        or authorization["authorized_command"] != EXACT_COMMAND
    ):
        raise ExecutionAuthorizationError("Required execution authority differs.")


__all__ = [
    "FINAL_OUTPUT_FILES",
    "FINAL_OUTPUT_ROOT",
    "PERSON_E_IMPLEMENTATION_RATIFICATION_COMMIT",
    "ExecutionAuthorizationError",
    "build_authorization_documents",
    "build_execution_authorization",
    "validate_authorization_documents",
    "validate_implementation_ratification_commit",
]
