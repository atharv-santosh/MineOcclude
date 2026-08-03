"""Additive preparation package for the implemented Step 4.1 comparison."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mineocclude.analysis.step4_1_final_comparison_runtime_v0_1 import (
    FINAL_OUTPUT_ROOT,
    PERSON_B_PREDICTION_PATH,
    PERSON_D_ROOT,
    POST_REVEAL_PATH,
    exact_execution_command,
)
from mineocclude.analysis.step4_1_final_comparison_v0_1 import (
    BOUNDED_REVEAL_CONTRACT_COMMIT,
    BOUNDED_REVEAL_PREDICTION_COUNT,
    BOUNDED_REVEAL_PREDICTIONS_SHA256,
    COMPARISON_CONTRACT_COMMIT,
    E_COMPARISON_RATIFICATION_COMMIT,
    FINAL_OUTPUT_FILENAMES,
    PERSON_B_PREDICTIONS_SHA256,
    PERSON_D_COMPLETION_COMMIT,
    PERSON_D_COMPLETION_SHA256,
    frozen_method_configuration,
)
from mineocclude.experiments.registry import canonical_json_bytes

IMPLEMENTATION_COMMIT = "0a73caf2b74221c5f934b95ae39ac825748e2942"
IMPLEMENTATION_SUBJECT = "Implement Person B Step 4.1 final comparison entrypoint"
PREPARATION_SUBJECT = "Prepare Person B Step 4.1 final comparison execution"
IMPLEMENTATION_PATHS = {
    "cli": "scripts/run_person_b_step4_1_final_comparison.py",
    "runtime_library": (
        "src/mineocclude/analysis/step4_1_final_comparison_runtime_v0_1.py"
    ),
    "scientific_library": (
        "src/mineocclude/analysis/step4_1_final_comparison_v0_1.py"
    ),
    "focused_tests": (
        "tests/analysis/"
        "test_person_b_step4_1_final_comparison_entrypoint_v0_1.py"
    ),
}


class FinalComparisonPreparationError(ValueError):
    """Raised when preparation no longer binds the exact implementation."""


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
        raise FinalComparisonPreparationError(f"Git validation failed: {error}") from error
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
        raise FinalComparisonPreparationError(
            f"Exact implementation read failed for {path}: {error}"
        ) from error
    return result.stdout


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_authority_binding() -> dict[str, Any]:
    return {
        "comparison_contract_commit": COMPARISON_CONTRACT_COMMIT,
        "comparison_ratification_commit": E_COMPARISON_RATIFICATION_COMMIT,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "implementation_parent_commit": BOUNDED_REVEAL_CONTRACT_COMMIT,
        "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
        "preparation_commit_semantics": (
            "The Git commit containing this package must be the direct child of "
            "implementation_commit and is the Person B execution-preparation authority."
        ),
        "schema_id": "person-b-step4-1-final-comparison-preparation-authority-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }


def build_implementation_binding(repository: Path) -> dict[str, Any]:
    files = {}
    for role, path in sorted(IMPLEMENTATION_PATHS.items()):
        payload = _git_bytes(repository, IMPLEMENTATION_COMMIT, path)
        files[role] = {
            "byte_size": len(payload),
            "path": path,
            "sha256": _sha256(payload),
        }
    return {
        "entrypoint": IMPLEMENTATION_PATHS["cli"],
        "files": files,
        "frozen_method_configuration_sha256": _sha256(
            canonical_json_bytes(frozen_method_configuration())
        ),
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "implementation_subject": IMPLEMENTATION_SUBJECT,
        "library_dispatch": [
            IMPLEMENTATION_PATHS["runtime_library"],
            IMPLEMENTATION_PATHS["scientific_library"],
        ],
        "no_new_scientific_choice": True,
        "schema_id": "person-b-step4-1-final-comparison-implementation-binding-v0-1",
        "schema_version": "1.0",
        "scientific_contract_unchanged": True,
        "u4_output_inspected": False,
    }


def build_input_contract() -> dict[str, Any]:
    return {
        "authorities": {
            "comparison_contract_commit": COMPARISON_CONTRACT_COMMIT,
            "comparison_ratification_commit": E_COMPARISON_RATIFICATION_COMMIT,
            "implementation_commit": IMPLEMENTATION_COMMIT,
            "person_b_bounded_reveal_contract_commit": (
                BOUNDED_REVEAL_CONTRACT_COMMIT
            ),
            "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
        },
        "bounded_reveal": {
            "additional_person_a_extraction_authorized": False,
            "path": POST_REVEAL_PATH.as_posix(),
            "prediction_count": BOUNDED_REVEAL_PREDICTION_COUNT,
            "probe_refitting_authorized": False,
            "rerun_authorized": False,
            "reuse_required": True,
            "schema_id": "person-b-step4-1-bounded-reveal-predictions-v0-1",
            "sha256": BOUNDED_REVEAL_PREDICTIONS_SHA256,
        },
        "local_frozen_inputs": {
            "analysis_config_sha256": (
                "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
            ),
            "applicability_contract_sha256": (
                "3ee4991589b828007091811823cb6e26fbfecc14a2c0331629cf6a014b131103"
            ),
            "fold_manifest_sha256": (
                "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71"
            ),
            "oracle_target_sha256": (
                "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282"
            ),
        },
        "person_b_predictions": {
            "byte_size": 84257218,
            "path": PERSON_B_PREDICTION_PATH.as_posix(),
            "prediction_count": 27800,
            "probe_matrix_count": 40,
            "sha256": PERSON_B_PREDICTIONS_SHA256,
        },
        "person_d": {
            "completion_manifest_sha256": PERSON_D_COMPLETION_SHA256,
            "prediction_count": 10776,
            "prediction_document_count": 9,
            "root": PERSON_D_ROOT.as_posix(),
        },
        "prohibited_actions": [
            "bounded reveal rerun",
            "probe refit",
            "additional Person A extraction",
            "manual U4 inspection",
            "broad hidden-state interpretation",
            "exploratory metric request",
            "post-hoc layer selection",
            "post-hoc test selection",
            "changed method, threshold, seed, schema, or hash",
        ],
        "schema_id": "person-b-step4-1-final-comparison-execution-input-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }


def build_execution_command() -> dict[str, Any]:
    command = exact_execution_command()
    return {
        "authorized_environment": "AWS SageMaker Linux",
        "command": command,
        "command_sha256": _sha256(canonical_json_bytes(command)),
        "entrypoint": IMPLEMENTATION_PATHS["cli"],
        "non_placeholder": not any("<" in token or ">" in token for token in command),
        "output_root": FINAL_OUTPUT_ROOT.as_posix(),
        "resume": "validate-complete-no-write",
        "schema_id": "person-b-step4-1-final-comparison-execution-command-v0-1",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "u4_output_inspected": False,
    }


def build_output_requirements() -> dict[str, Any]:
    return {
        "atomic_publication": (
            "Build a complete sibling staging directory and atomically rename it "
            "to the absent exact output root; overwrite and partial resume are forbidden."
        ),
        "final_decision_vocabulary": ["PASS", "FAIL", "INCONCLUSIVE"],
        "output_files": list(FINAL_OUTPUT_FILENAMES),
        "output_root": FINAL_OUTPUT_ROOT.as_posix(),
        "output_schema_id": "person-b-step4-1-final-comparison-output-v0-1",
        "person_e_closure_required": True,
        "person_e_implementation_ratification_required": True,
        "person_e_superseding_execution_authorization_required": True,
        "registry_generation": "v2",
        "resume_behavior": (
            "Return ALREADY_COMPLETE_NO_WRITE only after exact file-set, inventory, "
            "schema, and cross-document validation; otherwise fail closed."
        ),
        "schema_id": "person-b-step4-1-final-comparison-output-requirements-v0-1",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "step4_1_complete": False,
        "u4_output_inspected": False,
    }


def build_preparation_documents(repository: Path) -> dict[str, dict[str, Any]]:
    return {
        "authority_binding.json": build_authority_binding(),
        "execution_command.json": build_execution_command(),
        "execution_input_contract.json": build_input_contract(),
        "implementation_binding.json": build_implementation_binding(repository),
        "output_and_closure_requirements.json": build_output_requirements(),
        "validation_receipt.json": {
            "bounded_reveal_artifact_reuse_required": True,
            "entrypoint_implemented": True,
            "focused_tests_passed": True,
            "frozen_scientific_contract_unchanged": True,
            "implementation_commit": IMPLEMENTATION_COMMIT,
            "person_e_ratification_pending": True,
            "schema_id": "person-b-step4-1-final-comparison-preparation-validation-v0-1",
            "schema_version": "1.0",
            "scientific_execution_performed": False,
            "u4_output_inspected": False,
        },
    }


def validate_preparation_documents(
    repository: Path, documents: Mapping[str, Any]
) -> None:
    expected = build_preparation_documents(repository)
    if documents != expected:
        raise FinalComparisonPreparationError("Preparation documents differ.")
    if _git(repository, "show", "-s", "--format=%P", IMPLEMENTATION_COMMIT) != (
        BOUNDED_REVEAL_CONTRACT_COMMIT
    ):
        raise FinalComparisonPreparationError("Implementation parent differs.")
    if _git(repository, "show", "-s", "--format=%s", IMPLEMENTATION_COMMIT) != (
        IMPLEMENTATION_SUBJECT
    ):
        raise FinalComparisonPreparationError("Implementation subject differs.")
    command = documents["execution_command.json"]
    if command["non_placeholder"] is not True or command["command"] != (
        exact_execution_command()
    ):
        raise FinalComparisonPreparationError("Execution command differs.")
    restrictions = documents["execution_input_contract.json"]["prohibited_actions"]
    if len(restrictions) != 9:
        raise FinalComparisonPreparationError("Execution restrictions differ.")
    if any(
        document.get("u4_output_inspected") is not False
        or document.get("scientific_execution_performed", False) is not False
        for document in documents.values()
    ):
        raise FinalComparisonPreparationError("Preparation falsely expands execution.")


__all__ = [
    "IMPLEMENTATION_COMMIT",
    "IMPLEMENTATION_PATHS",
    "IMPLEMENTATION_SUBJECT",
    "PREPARATION_SUBJECT",
    "FinalComparisonPreparationError",
    "build_authority_binding",
    "build_execution_command",
    "build_implementation_binding",
    "build_input_contract",
    "build_output_requirements",
    "build_preparation_documents",
    "validate_preparation_documents",
]
