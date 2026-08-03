"""Person E final Step 4.1 comparison ratification and closure contract."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mineocclude.experiments.step4_1_contract_review_v0_1 import (
    PERSON_B_COMPARISON_COMMIT,
    PERSON_B_POST_REVEAL_COMMIT,
    PERSON_D_COMPLETION_COMMIT,
    Step41ContractReviewError,
    review_person_b_contracts,
)

BOUNDED_REVEAL_AUTHORIZATION_COMMIT = "99fb896ed8e6a3b187272fe078706bc7b17666d8"
BOUNDED_REVEAL_AUTHORIZATION_PATH = (
    "docs/status/person_e_phase4_step4_1_bounded_reveal_authorization_v0_1/"
    "bounded_reveal_authorization.json"
)
BOUNDED_REVEAL_AUTHORIZATION_SHA256 = (
    "b41b98c90a89c42e3e8119999679dd35644cd277a758722438794583f86cb7a2"
)
RATIFICATION_VERSION = "person-e-step4-1-final-comparison-ratification-v0.1"


class Step41ClosureContractError(ValueError):
    """Raised when comparison ratification or closure scope differs."""


def _git_bytes(repository: Path, commit: str, path: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), "show", f"{commit}:{path}"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise Step41ClosureContractError(f"Git-object read failed: {error}") from error


def _load_authorization(repository: Path) -> Mapping[str, Any]:
    payload = _git_bytes(
        repository,
        BOUNDED_REVEAL_AUTHORIZATION_COMMIT,
        BOUNDED_REVEAL_AUTHORIZATION_PATH,
    )
    if hashlib.sha256(payload).hexdigest() != BOUNDED_REVEAL_AUTHORIZATION_SHA256:
        raise Step41ClosureContractError("Bounded reveal authorization bytes differ.")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Step41ClosureContractError("Bounded authorization is invalid JSON.") from error
    if not isinstance(document, Mapping):
        raise Step41ClosureContractError("Bounded authorization root is not an object.")
    required = {
        "bounded_reveal_authorized": True,
        "broad_hidden_state_interpretation_authorized": False,
        "manual_u4_inspection_authorized": False,
        "person_b_comparison_contract_commit": PERSON_B_COMPARISON_COMMIT,
        "person_b_post_reveal_contract_commit": PERSON_B_POST_REVEAL_COMMIT,
        "post_reveal_probe_predictions_authorized": True,
        "probe_refitting_authorized": False,
        "step4_1_complete": False,
        "u4_output_inspected": False,
    }
    if any(document.get(field) != value for field, value in required.items()):
        raise Step41ClosureContractError("Bounded reveal authorization is not narrow.")
    return document


def build_final_comparison_ratification(repository: Path) -> dict[str, Any]:
    """Bind exact B/D evidence and authorize only the frozen sequence."""

    review = review_person_b_contracts(repository)
    authorization = _load_authorization(repository)
    return {
        "bounded_reveal_authorization": {
            "commit": BOUNDED_REVEAL_AUTHORIZATION_COMMIT,
            "path": BOUNDED_REVEAL_AUTHORIZATION_PATH,
            "sha256": BOUNDED_REVEAL_AUTHORIZATION_SHA256,
        },
        "broad_hidden_state_interpretation_authorized": False,
        "comparison_contract": {
            "commit": PERSON_B_COMPARISON_COMMIT,
            "file": review["comparison_contract_file"],
            "version": "person-b-step4-1-final-comparison-v0.1",
        },
        "decision": "RATIFY_EXACT_PERSON_B_STEP4_1_FINAL_COMPARISON_INTERFACE",
        "exact_final_comparison_metrics_authorized": True,
        "exploratory_metrics_authorized": False,
        "manual_u4_inspection_authorized": False,
        "permitted_execution_sequence": [
            {
                "order": 1,
                "owner": "person_b",
                "required_input": "exact_bounded_reveal_authorization_commit",
                "required_output": "100 exact post-reveal predictions and receipts",
                "step": "BOUNDED_REVEAL_PREDICTIONS",
            },
            {
                "order": 2,
                "owner": "person_b",
                "required_input": (
                    "verified post-reveal package plus exact preserved B and D predictions"
                ),
                "required_output": "frozen comparison metric package and receipts",
                "step": "FINAL_COMPARISON_METRICS",
            },
            {
                "order": 3,
                "owner": "person_e",
                "required_input": "complete exact B and D trust packages",
                "required_output": (
                    "Registry v2 import, closure report, and PASS/FAIL/INCONCLUSIVE decision"
                ),
                "step": "VERIFY_IMPORT_AND_CLOSE",
            },
        ],
        "person_b_comparison_contract_commit": PERSON_B_COMPARISON_COMMIT,
        "person_b_post_reveal_contract_commit": PERSON_B_POST_REVEAL_COMMIT,
        "post_hoc_layer_selection_authorized": False,
        "post_hoc_test_selection_authorized": False,
        "post_reveal_contract": {
            "commit": PERSON_B_POST_REVEAL_COMMIT,
            "file": review["post_reveal_contract_file"],
            "version": "person-b-step4-1-bounded-reveal-v0.1",
        },
        "probe_refitting_authorized": False,
        "ratification_version": RATIFICATION_VERSION,
        "schema_id": "person-e-step4-1-final-comparison-ratification-v0-1",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "step4_1_complete": False,
        "u4_output_inspected": False,
        "unknown_version_or_changed_hash_policy": "FAIL_CLOSED_INCONCLUSIVE",
        "authorization_output_root": authorization["authorized_output_root"],
    }


def build_closure_contract(repository: Path) -> dict[str, Any]:
    ratification = build_final_comparison_ratification(repository)
    return {
        "acceptance_contract": {
            "decision_precedence": [
                "INCONCLUSIVE_integrity_or_control_gate",
                "PASS_all_scientific_gates",
                "FAIL_clean_scientific_miss",
            ],
            "fail": (
                "All integrity and control gates pass, all required metrics are valid, "
                "and no contiguous band of at least two layers meets every U1/U2/U3 gate."
            ),
            "inconclusive": (
                "Any unknown hash/version, missing or invalid artifact/row, leakage, "
                "failed control, nonfinite or degenerate required statistic, absent "
                "reveal pair, or unauthorized scope prevents scientific classification."
            ),
            "pass": (
                "All integrity and control gates pass and at least one contiguous band "
                "of two or more adjacent layers has every layer satisfy the exact "
                "U1_green, U2_green, and U3_green gates."
            ),
            "status_vocabulary": ["PASS", "FAIL", "INCONCLUSIVE"],
        },
        "closure_report_required_fields": [
            "schema_id",
            "schema_version",
            "person_b_comparison_contract_commit",
            "person_b_post_reveal_contract_commit",
            "person_e_bounded_reveal_authorization_commit",
            "person_e_comparison_ratification_commit",
            "person_d_completion_commit",
            "all_direct_input_paths_sizes_and_sha256s",
            "post_reveal_execution_receipt",
            "final_comparison_execution_receipt",
            "positive_control_decision",
            "negative_control_results",
            "per_layer_u1_u2_u3_results",
            "paired_tests_and_max_t_adjusted_p_values",
            "bootstrap_confidence_intervals",
            "all_qualifying_contiguous_layer_bands",
            "decision",
            "decision_rationale",
            "registry_v2_registry_id_and_sha256",
            "registry_v2_imported_artifact_ids",
            "unresolved_blockers",
            "scientific_execution_performed",
            "u4_output_inspected",
        ],
        "comparison_ratification": ratification,
        "control_requirements": {
            "negative": {
                "family": "grouped_shuffled",
                "required_targets": ["mu_oracle_blocks", "log_sigma_oracle"],
            },
            "no_object": "NOT_APPLICABLE_TO_FROZEN_TEN_PILOT_PRODUCTION_SET",
            "positive": {
                "authority_commit": "e39fef4a59142a84dfb5991d51deeb506eb23a7b",
                "decision": "PASS_FROZEN_VISIBLE_POSITION_POSITIVE_CONTROL",
                "decision_sha256": (
                    "742557b32326180003b1cd83ed5db6f1a1ebfebd692d969809698d323f239056"
                ),
            },
        },
        "person_b_required_evidence": {
            "existing_predictions": {
                "byte_size": 84257218,
                "count": 27800,
                "path": (
                    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
                    "person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json"
                ),
                "sha256": (
                    "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba"
                ),
            },
            "final_comparison": {
                "output_root": (
                    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
                    "person-b-step4-1-final-comparison-v0-1"
                ),
                "required_files": [
                    "comparison_metric_table.json",
                    "paired_test_results.json",
                    "confidence_intervals.json",
                    "layer_band_decision.json",
                    "registry_v2_import_package.json",
                    "execution_receipt.json",
                    "sha256_inventory.json",
                ],
                "schema_id": "person-b-step4-1-final-comparison-output-v0-1",
            },
            "post_reveal": {
                "count": 100,
                "output_root": ratification["authorization_output_root"],
                "required_files": [
                    "post_reveal_predictions.json",
                    "execution_receipt.json",
                    "sha256_inventory.json",
                ],
                "schema_id": "person-b-step4-1-bounded-reveal-predictions-v0-1",
            },
        },
        "person_d_required_evidence": {
            "completion_commit": PERSON_D_COMPLETION_COMMIT,
            "completion_manifest_sha256": (
                "79c49e7c794f37c4a574dfef365b8183ddb443b246adbe94743dfdf1ff1f4cf5"
            ),
            "prediction_count": 10776,
            "required_families": [
                "last_seen",
                "constant_velocity",
                "grouped_shuffled",
                "time_only",
                "explicit_feature",
                "raw_pixel",
                "visible_history_q",
                "known_q_analytic",
            ],
            "required_receipts": [
                "run_state.json",
                "preserved_output_provenance.json",
                "nine exact prediction documents",
                "fit and missingness/exclusion receipts",
                "runner and environment receipts",
            ],
        },
        "schema_id": "person-e-step4-1-final-closure-contract-v0-1",
        "schema_version": "1.0",
        "step4_1_complete": False,
        "u4_output_inspected": False,
    }


def build_registry_v2_import_contract(repository: Path) -> dict[str, Any]:
    build_final_comparison_ratification(repository)
    exact_artifact_fields = [
        "schema_version",
        "artifact_schema_version",
        "artifact_id",
        "direct_input_artifact_ids",
        "creator_run_id",
        "artifact_type",
        "uri",
        "sha256",
        "size_bytes",
        "status",
        "status_authority",
        "status_reason",
        "superseded_by",
    ]
    return {
        "accepted_artifact_types": [
            "fitted_probe",
            "prediction",
            "baseline",
            "metric_table",
        ],
        "artifact_exact_fields": exact_artifact_fields,
        "direct_input_requirements": (
            "Explicit, duplicate-free artifact IDs with verified hashes; every accepted "
            "direct input must exist and be accepted before its consumer is imported."
        ),
        "import_order": [
            "existing Person B fitted_probe and prediction",
            "nine Person D baseline prediction artifacts",
            "Person B bounded reveal prediction",
            "Person B final metric_table",
        ],
        "minimum_trust_records_per_output": [
            "trusted owner authority",
            "verified owner status record bytes",
            "trusted exact-artifact authorization",
            "verified authorization record bytes",
            "trusted manifest with exact artifact identity/type/schema/size/SHA-256",
            "verified local bytes or trusted external receipt",
            "exact direct-input artifact IDs and hashes",
        ],
        "registry_fields": [
            "immutable_registry_schema_version",
            "registry_id",
            "schema_version",
            "scientific_use",
            "synthetic",
            "owner_authorities",
            "owner_status_records",
            "trusted_artifact_authorizations",
            "trusted_authorization_record_bytes",
            "manifests",
            "byte_verifications",
            "runs",
            "artifacts",
        ],
        "registry_generation": "v2",
        "schema_id": "person-e-step4-1-registry-v2-import-contract-v0-1",
        "schema_version": "1.0",
        "unknown_or_extra_type_policy": "REJECT",
        "u4_output_inspected": False,
    }


def validate_final_ratification_package(
    ratification: Any,
    closure: Any,
    registry: Any,
    *,
    repository: Path,
) -> None:
    try:
        review_person_b_contracts(repository)
    except Step41ContractReviewError as error:
        raise Step41ClosureContractError(str(error)) from error
    if ratification != build_final_comparison_ratification(repository):
        raise Step41ClosureContractError("Final comparison ratification differs.")
    if closure != build_closure_contract(repository):
        raise Step41ClosureContractError("Closure contract differs.")
    if registry != build_registry_v2_import_contract(repository):
        raise Step41ClosureContractError("Registry v2 import contract differs.")


__all__ = [
    "BOUNDED_REVEAL_AUTHORIZATION_COMMIT",
    "Step41ClosureContractError",
    "build_closure_contract",
    "build_final_comparison_ratification",
    "build_registry_v2_import_contract",
    "validate_final_ratification_package",
]
