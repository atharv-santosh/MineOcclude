"""Independent Person E review of exact Person B Step 4.1 Git objects."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PERSON_B_STARTING_AUTHORITY = "2a23c84995fea4e15293039063e60e9535fd2ee2"
PERSON_B_COMPARISON_COMMIT = "4da02023a376df77eacb48084b1406ec1accfcb1"
PERSON_B_POST_REVEAL_COMMIT = "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4"
PERSON_D_COMPLETION_COMMIT = "f89b142a6fdb52c2d238669af8df14061cee5896"
PERSON_E_STARTING_AUTHORITY = "21d83c19c9d8f36c4dbeeaf45d4626eaf082e7a7"
COMPARISON_PACKAGE = (
    "docs/status/person_b_phase4_step4_1_final_comparison_contract_v0_1"
)
POST_REVEAL_PACKAGE = (
    "docs/status/person_b_phase4_step4_1_bounded_reveal_contract_v0_1"
)


class Step41ContractReviewError(ValueError):
    """Raised when Person E cannot ratify exact Person B objects."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise Step41ContractReviewError(f"Git-object read failed: {error}") from error


def _git_text(repository: Path, *arguments: str) -> str:
    try:
        return _git(repository, *arguments).decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise Step41ContractReviewError("Git metadata is not UTF-8.") from error


def _strict_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise Step41ContractReviewError(f"{label} repeats JSON key {key!r}.")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs_hook,
            parse_constant=lambda value: (_ for _ in ()).throw(
                Step41ContractReviewError(
                    f"{label} contains nonfinite constant {value!r}."
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Step41ContractReviewError(f"{label} is not strict JSON: {error}") from error
    if not isinstance(document, Mapping):
        raise Step41ContractReviewError(f"{label} root is not an object.")
    return document


def _load_package(
    repository: Path,
    *,
    commit: str,
    package: str,
) -> dict[str, Mapping[str, Any]]:
    inventory_payload = _git(
        repository, "show", f"{commit}:{package}/sha256_inventory.json"
    )
    inventory = _strict_json(inventory_payload, label=f"{package} inventory")
    files = inventory.get("files")
    if inventory.get("inventory_excludes_self") is not True or not isinstance(
        files, Mapping
    ):
        raise Step41ContractReviewError(f"{package} inventory is malformed.")
    documents = {"sha256_inventory.json": inventory}
    for name, reference in files.items():
        if not isinstance(name, str) or not isinstance(reference, Mapping):
            raise Step41ContractReviewError(f"{package} inventory row is malformed.")
        payload = _git(repository, "show", f"{commit}:{package}/{name}")
        document = _strict_json(payload, label=f"{package}/{name}")
        if payload != canonical_bytes(document):
            raise Step41ContractReviewError(f"{package}/{name} is not canonical.")
        if (
            len(payload) != reference.get("byte_size")
            or hashlib.sha256(payload).hexdigest() != reference.get("sha256")
        ):
            raise Step41ContractReviewError(f"{package}/{name} hash differs.")
        documents[name] = document
    return documents


def review_person_b_contracts(repository: Path) -> dict[str, Any]:
    """Independently review the two exact B commits; return signed check facts."""

    if _git_text(repository, "show", "-s", "--format=%P", PERSON_B_COMPARISON_COMMIT) != (
        PERSON_B_STARTING_AUTHORITY
    ):
        raise Step41ContractReviewError("Comparison commit parent differs.")
    if _git_text(repository, "show", "-s", "--format=%P", PERSON_B_POST_REVEAL_COMMIT) != (
        PERSON_B_COMPARISON_COMMIT
    ):
        raise Step41ContractReviewError("Post-reveal commit parent differs.")
    comparison_docs = _load_package(
        repository,
        commit=PERSON_B_COMPARISON_COMMIT,
        package=COMPARISON_PACKAGE,
    )
    reveal_docs = _load_package(
        repository,
        commit=PERSON_B_POST_REVEAL_COMMIT,
        package=POST_REVEAL_PACKAGE,
    )
    comparison = comparison_docs.get("final_comparison_contract.json")
    reveal = reveal_docs.get("bounded_reveal_contract.json")
    if not isinstance(comparison, Mapping) or not isinstance(reveal, Mapping):
        raise Step41ContractReviewError("Required B contracts are missing.")

    checks = {
        "acceptance_decisions_closed": (
            comparison.get("acceptance_contract", {}).get("status_vocabulary")
            == ["PASS", "FAIL", "INCONCLUSIVE"]
        ),
        "aggregation_closed": set(comparison.get("aggregation_contract", {}))
        >= {
            "row_level_pairing_keys",
            "fold_aggregation",
            "pilot_aggregation",
            "baseline_family_aggregation",
            "macro_micro_policy",
            "missing_data_policy",
            "weighting_rule",
        },
        "all_layers_fixed": comparison.get("layer_contract")
        == {
            "hook_site": "decoder_layer_output_residual_stream",
            "layer_indices": list(range(20)),
            "selection_mode": "none_all_layers_fixed_before_runtime",
            "test_data_may_select_layer": False,
        },
        "ci_closed": comparison.get("confidence_interval_contract")
        == {
            "bootstrap_count": 2000,
            "coverage": 0.95,
            "hierarchy": ["layout_id", "trajectory_id", "all_paired_rows"],
            "interval": "equal_tailed_percentile_linear_quantiles",
            "seed": 20260721,
            "unit": "whole_layout_then_whole_trajectory",
        },
        "controls_closed": set(comparison.get("control_contract", {}))
        == {"negative_control", "no_object_control", "positive_control"},
        "e_ratification_gate_present": comparison.get("execution_interface", {}).get(
            "person_e_ratification_required"
        )
        is True,
        "exact_prediction_authority": reveal.get("authorities", {})
        .get("person_b_prediction_artifact", {})
        .get("sha256")
        == "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba",
        "multiplicity_closed": comparison.get("multiplicity_contract", {}).get(
            "adjustment"
        )
        == "single_step_shared_sign_flip_maxT",
        "no_open_choices": comparison.get("unresolved_scientific_choices") == [],
        "no_probe_refit": reveal.get("availability_decision", {}).get(
            "PERSON_B_PROBE_REFIT_REQUIRED"
        )
        is False,
        "no_u4_access": not any(comparison.get("u4_restrictions", {}).values())
        and reveal.get("state", {}).get("manual_u4_inspection_authorized") is False
        and reveal.get("state", {}).get("u4_output_inspected") is False,
        "post_inputs_available": reveal.get("availability_decision", {}).get(
            "POST_REVEAL_INPUTS_AVAILABLE"
        )
        is True,
        "post_output_closed": reveal.get("output_contract", {}).get(
            "expected_prediction_count"
        )
        == 100,
        "reveal_events_closed": len(reveal.get("input_contract", {}).get("events", ()))
        == 5,
        "significance_closed": comparison.get("multiplicity_contract", {}).get(
            "permutation_count"
        )
        == 999,
    }
    failed = sorted(name for name, passed in checks.items() if passed is not True)
    if failed:
        raise Step41ContractReviewError(
            "Person B contracts retain unresolved scope: " + ", ".join(failed)
        )
    comparison_inventory = comparison_docs["sha256_inventory.json"]["files"]
    reveal_inventory = reveal_docs["sha256_inventory.json"]["files"]
    return {
        "all_checks_passed": True,
        "check_count": len(checks),
        "checks": checks,
        "comparison_contract_file": comparison_inventory["final_comparison_contract.json"],
        "comparison_package_file_count": len(comparison_inventory),
        "post_reveal_contract_file": reveal_inventory["bounded_reveal_contract.json"],
        "post_reveal_package_file_count": len(reveal_inventory),
        "review_mode": "independent_exact_git_object_reads_no_merge",
        "unresolved_scientific_choices": [],
    }


def build_bounded_reveal_authorization(repository: Path) -> dict[str, Any]:
    review = review_person_b_contracts(repository)
    reveal_docs = _load_package(
        repository,
        commit=PERSON_B_POST_REVEAL_COMMIT,
        package=POST_REVEAL_PACKAGE,
    )
    reveal = reveal_docs["bounded_reveal_contract.json"]
    events = [
        {
            "activation_index_sha256": event["activation_index"]["sha256"],
            "event_id": event["event_id"],
            "fold_idx": event["fold_idx"],
            "layer_indices": list(range(20)),
            "post_model_frame_idx": event["post_identity"]["model_frame_idx"],
            "trajectory_id": event["trajectory_id"],
        }
        for event in reveal["input_contract"]["events"]
    ]
    return {
        "authorization_decision": "AUTHORIZED_EXACT_MACHINE_MEDIATED_BOUNDED_REVEAL",
        "authorized_command": reveal["execution_contract"]["command"],
        "authorized_event_and_row_identities": events,
        "authorized_execution_count": 1,
        "authorized_fitted_probes": {
            "artifact_sha256": (
                "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba"
            ),
            "fold_fit_rule": reveal["fold_contract"]["probe_fit_rule"],
            "hook_site": "decoder_layer_output_residual_stream",
            "layer_indices": list(range(20)),
            "reuse_without_refit": True,
            "target": "log_sigma_oracle",
        },
        "authorized_output_root": reveal["execution_contract"]["output_root"],
        "authorized_resume_behavior": reveal["execution_contract"]["resume_behavior"],
        "authorized_scope": (
            "Read only the 100 exact Person A activation rows named by the five event "
            "identities and 20 layers, then apply the matching already fitted held-out "
            "fold log_sigma probe and write the exact ratified output package."
        ),
        "bounded_reveal_authorized": True,
        "broad_hidden_state_interpretation_authorized": False,
        "comparison_contract_file": review["comparison_contract_file"],
        "exact_combined_activation_index": reveal["input_contract"][
            "combined_activation_index"
        ],
        "expected_prediction_count": 100,
        "exploratory_metrics_authorized": False,
        "manual_u4_inspection_authorized": False,
        "output_schema_id": "person-b-step4-1-bounded-reveal-predictions-v0-1",
        "person_b_comparison_contract_commit": PERSON_B_COMPARISON_COMMIT,
        "person_b_post_reveal_contract_commit": PERSON_B_POST_REVEAL_COMMIT,
        "person_b_prediction_artifact": {
            "byte_size": 84257218,
            "path": (
                "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
                "person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json"
            ),
            "prediction_count": 27800,
            "sha256": (
                "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba"
            ),
        },
        "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
        "person_d_completion_manifest_sha256": (
            "79c49e7c794f37c4a574dfef365b8183ddb443b246adbe94743dfdf1ff1f4cf5"
        ),
        "post_hoc_layer_selection_authorized": False,
        "post_hoc_test_selection_authorized": False,
        "post_reveal_contract_file": review["post_reveal_contract_file"],
        "post_reveal_probe_predictions_authorized": True,
        "probe_refitting_authorized": False,
        "prohibited_actions": [
            "manual browsing or exploratory inspection of any hidden-state or U4 artifact",
            "reading any activation row outside the exact five events and 20 layers",
            "probe fitting, target changes, fold changes, or preprocessing changes",
            "metric calculation, layer selection, test selection, or scientific interpretation",
            "overwrite, partial resume, schema substitution, or unknown-version execution",
        ],
        "required_audit_receipts": [
            "post_reveal_predictions.json",
            "execution_receipt.json",
            "sha256_inventory.json",
            "exact Person E authorization commit",
            "all direct input byte sizes and SHA-256 identities",
            "probe_refit_performed=false",
            "additional_person_a_extraction_performed=false",
            "metrics_computed=false",
            "u4_output_inspected=false",
        ],
        "schema_id": "person-e-step4-1-bounded-reveal-authorization-v0-1",
        "schema_version": "1.0",
        "step4_1_complete": False,
        "supersedes_incomplete_step4_1_state_at_commit": PERSON_E_STARTING_AUTHORITY,
        "u4_output_inspected": False,
    }


def validate_bounded_reveal_authorization(
    document: Any,
    *,
    repository: Path,
) -> None:
    if document != build_bounded_reveal_authorization(repository):
        raise Step41ContractReviewError("Person E authorization differs from v0.1.")


__all__ = [
    "Step41ContractReviewError",
    "build_bounded_reveal_authorization",
    "canonical_bytes",
    "review_person_b_contracts",
    "validate_bounded_reveal_authorization",
]
