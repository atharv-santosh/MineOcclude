"""Frozen contract and pure helpers for bounded reveal prediction production."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

COMPARISON_CONTRACT_COMMIT = "4da02023a376df77eacb48084b1406ec1accfcb1"
PERSON_B_STARTING_AUTHORITY = "2a23c84995fea4e15293039063e60e9535fd2ee2"
PERSON_E_STARTING_AUTHORITY = "21d83c19c9d8f36c4dbeeaf45d4626eaf082e7a7"
CONTRACT_VERSION = "person-b-step4-1-bounded-reveal-v0.1"
HOOK_SITE = "decoder_layer_output_residual_stream"
LAYERS = tuple(range(20))


class BoundedRevealContractError(ValueError):
    """Raised when bounded reveal inputs or contract values expand scope."""


def _event(
    trajectory_id: str,
    layout_id: str,
    fold_idx: int,
    episode_id: str,
    pre_idx: int,
    post_idx: int,
    capture_commit: str,
    capture_sha256: str,
    activation_index_path: str,
    activation_index_sha256: str,
    activation_index_byte_size: int,
    inventory_path: str,
    inventory_sha256: str,
    inventory_byte_size: int,
) -> dict[str, Any]:
    return {
        "activation_index": {
            "byte_size": activation_index_byte_size,
            "path": activation_index_path,
            "sha256": activation_index_sha256,
        },
        "capture_package": {
            "git_commit": capture_commit,
            "path": f"data/autonomous/{trajectory_id}/capture_package_v0_1.json",
            "sha256": capture_sha256,
        },
        "episode_id": episode_id,
        "event_id": f"{trajectory_id}:reveal:{post_idx}",
        "fold_idx": fold_idx,
        "layout_id": layout_id,
        "person_a_inventory": {
            "byte_size": inventory_byte_size,
            "git_commit": "55776dc88302b89b52eef483a710fbf6811cf536",
            "path": inventory_path,
            "sha256": inventory_sha256,
        },
        "post_identity": {
            "action_idx": post_idx,
            "model_frame_idx": post_idx,
            "render_frame_idx": post_idx,
            "server_tick": post_idx,
            "visibility": "visible",
        },
        "pre_identity": {
            "action_idx": pre_idx,
            "model_frame_idx": pre_idx,
            "render_frame_idx": pre_idx,
            "server_tick": pre_idx,
            "visibility": "occluded",
        },
        "relative_time_seconds": {"post": 0.0, "pre": -0.05},
        "trajectory_id": trajectory_id,
    }


def reveal_events() -> list[dict[str, Any]]:
    root = (
        "/home/sagemaker-user/person-a-phase6-approved-outputs/"
        "person-a-phase6-ten-pilot-expansion-seed-20260725"
    )
    return [
        _event(
            "layout_00_ep9403",
            "layout_00",
            1,
            "9403",
            227,
            228,
            "bf09c23bb12f59acae724811eed6b82bab17c0ed",
            "21ea1dba91cf92ad82080088f70905fba053557392437b19591cad1333667213",
            "/home/sagemaker-user/person-a-phase6-approved-outputs/"
            "person-a-phase6-step6-3-continuation-a102aa4d1ca5d4760e9c9997-"
            "activation-store-v2/indexes/"
            "index-82dc0e18607a1a89135a1a88cbec5d53531682db970e9a1323672e7f4d28677b.json",
            "473efef1eb52514c097051ec8f4501cb621f92c9ceaeb847249c7e3ae042ad55",
            32502224,
            f"{root.replace('/home/sagemaker-user/person-a-phase6-approved-outputs/', 'docs/status/phase6_runtime/')}/per_pilot_inventories/layout_00_ep9403.json",
            "31d352d51804dac1708527b5b24e27aa9bc952912ce1fc7e8c93de791dc97cbd",
            9175,
        ),
        _event(
            "layout_01_ep9405", "layout_01", 2, "9405", 209, 210,
            "f0d4e895b56fc4ca3f4805aa13b73545744af1b0",
            "c139247e3be9132ddf2781f6d8abbe7d4498fa158464e3f47c534cf19b5c614f",
            f"{root}-layout_01_ep9405-activation-store-v2/indexes/index-0ceffdaab158e7edec75816bc1958922531fe2baa7c2189b558153de4f3ad7b9.json",
            "023786fd7fb3002e5acebcddd82e8f1e7ddb597138820c9401bd5dd7af5f10e6", 30164409,
            "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725/per_pilot_inventories/layout_01_ep9405.json",
            "c96e918631b9d2e8d751744f2cf019caac3e523635d32a66b4dc74c22e261b3f", 9214,
        ),
        _event(
            "layout_02_ep9407", "layout_02", 4, "9407", 137, 138,
            "f0d4e895b56fc4ca3f4805aa13b73545744af1b0",
            "ed7884bcc5e72db1d8b1c642f0ce668544c7cb348567b0ec820d69db6016004f",
            f"{root}-layout_02_ep9407-activation-store-v2/indexes/index-e6ede10a3d0f2115275a5e287acea472785fde798da0820935117bc0ba5fba81.json",
            "c76bf46818c70a798276d52d1d46a4f27aee255e44e0bd20fa1a583f23c3c467", 20734849,
            "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725/per_pilot_inventories/layout_02_ep9407.json",
            "0f05f649750f8f8c0328e6b270d0bb23347c844f7c214e6ad66ed3d9347ccc68", 9214,
        ),
        _event(
            "layout_03_ep9404", "layout_03", 0, "9404", 105, 106,
            "f0d4e895b56fc4ca3f4805aa13b73545744af1b0",
            "c9bc91d934643a53c5b3c39d519e5b3533788021adac57373af5edea12795ac7",
            f"{root}-layout_03_ep9404-activation-store-v2/indexes/index-b4b5232cb549a41882998312071b88200ff7c047ab9c045b89d4e9a6ad0b6cbf.json",
            "66b162bb09a170d82563838cf5ebc1eea4e7e9c6fe0f10927e155d1e765633fe", 16406599,
            "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725/per_pilot_inventories/layout_03_ep9404.json",
            "b24b8a49c836722f9b30f0f57ba9aa291d162327d1a7794e36d4f4bdb058039a", 9214,
        ),
        _event(
            "layout_04_ep9406", "layout_04", 3, "9406", 92, 93,
            "f0d4e895b56fc4ca3f4805aa13b73545744af1b0",
            "3cc2917fb0698d83d4ec12aa7cd7288e4a929dd5f13e810d303fbd1cc348f021",
            f"{root}-layout_04_ep9406-activation-store-v2/indexes/index-3e8d24985d51b9ffbaf81f8b0e8be6bedc8b082c6e2dda721b6e14961ff20e47.json",
            "df8f0541c872e3d6daf7a6a1165e6deafe6256ec745ffb5329befe0e3c697a78", 14829719,
            "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725/per_pilot_inventories/layout_04_ep9406.json",
            "618aaae8dfdcd39cd013491b18c10e99e74981c7d707b93f12363728d636cb9c", 9194,
        ),
    ]


def build_bounded_reveal_contract() -> dict[str, Any]:
    """Return the exact five-event, one-target, twenty-layer contract."""

    return {
        "authorities": {
            "comparison_contract_commit": COMPARISON_CONTRACT_COMMIT,
            "person_a_activation_authority_commit": (
                "55776dc88302b89b52eef483a710fbf6811cf536"
            ),
            "person_b_prediction_artifact": {
                "byte_size": 84257218,
                "path": (
                    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
                    "person-b-step4-1-production-v0-1/"
                    "fitted_probes_and_predictions.json"
                ),
                "prediction_count": 27800,
                "sha256": (
                    "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba"
                ),
            },
            "person_b_starting_authority": PERSON_B_STARTING_AUTHORITY,
            "person_e_authorization_required": True,
            "person_e_starting_authority": PERSON_E_STARTING_AUTHORITY,
            "this_contract_authority": (
                "The Git commit containing this package; it must be the direct child "
                "of comparison_contract_commit."
            ),
        },
        "availability_decision": {
            "PERSON_A_ADDITIONAL_EXTRACTION_REQUIRED": False,
            "PERSON_B_PROBE_REFIT_REQUIRED": False,
            "POST_REVEAL_INPUTS_AVAILABLE": True,
            "basis": (
                "The accepted immutable Activation Store v2 indexes cover every source "
                "frame for the five core pilots at all 20 layers. The five exact first-"
                "visible post-reveal frames are among those 874 core source frames but "
                "were intentionally excluded from the 695 hidden fit/prediction rows."
            ),
            "core_activation_row_count": 17480,
            "core_source_frame_count": 874,
            "post_reveal_activation_row_count": 100,
        },
        "execution_contract": {
            "authorized_environment": "AWS SageMaker Linux",
            "command": [
                "python",
                "scripts/run_person_b_step4_1_bounded_reveal.py",
                "--repository-root",
                "$PWD",
                "--person-b-contract-commit",
                "<PERSON_B_POST_REVEAL_CONTRACT_COMMIT>",
                "--person-e-authorization-commit",
                "<PERSON_E_BOUNDED_REVEAL_AUTHORIZATION_COMMIT>",
                "--output-root",
                (
                    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
                    "person-b-step4-1-bounded-reveal-v0-1"
                ),
            ],
            "execution_count": 1,
            "fail_closed_gates": [
                "exact clean role/person-b-analysis checkout at contract commit",
                "exact Person E authorization Git object binding both B commits",
                "exact prediction artifact size, SHA-256, schema, fits, and row count",
                "exact five Person A index and transitive chunk inventories",
                "exact capture Git objects and occluded-to-visible transitions",
                "exact model/preprocess identity and 2048-wide finite float32 vectors",
                "one exact post row for every event-layer and one matching held-out fold fit",
                "no target access, no refit, no metric, no U4 artifact access",
                "output root absent or exact complete no-write receipt",
            ],
            "output_root": (
                "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
                "person-b-step4-1-bounded-reveal-v0-1"
            ),
            "resume_behavior": (
                "Validate and return ALREADY_COMPLETE_NO_WRITE only for an exact complete "
                "inventory; fail on partial, changed, symlinked, or unknown output."
            ),
        },
        "fold_contract": {
            "fold_count": 5,
            "fold_mapping": {
                "layout_00": 1,
                "layout_01": 2,
                "layout_02": 4,
                "layout_03": 0,
                "layout_04": 3,
            },
            "probe_fit_rule": (
                "For each event and layer, reuse only the log_sigma_oracle fold_fit "
                "whose outer_fold_idx equals the event fold_idx."
            ),
        },
        "input_contract": {
            "combined_activation_index": {
                "byte_size": 245491346,
                "path": (
                    "/home/sagemaker-user/person-a-phase6-approved-outputs/"
                    "person-a-phase6-ten-pilot-expansion-seed-20260725/"
                    "combined_activation_index.json"
                ),
                "sha256": (
                    "1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9"
                ),
            },
            "events": reveal_events(),
            "model_hash": (
                "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
            ),
            "preprocess_hash": (
                "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
            ),
        },
        "output_contract": {
            "canonicalization": (
                "UTF-8 JSON sorted keys indent=2 newline; predictions rounded to 12 "
                "decimal places; finite values only"
            ),
            "expected_event_count": 5,
            "expected_prediction_count": 100,
            "files": [
                "post_reveal_predictions.json",
                "execution_receipt.json",
                "sha256_inventory.json",
            ],
            "prediction_row_fields": [
                "event_id",
                "trajectory_id",
                "episode_id",
                "layout_id",
                "model_frame_idx",
                "server_tick",
                "render_frame_idx",
                "action_idx",
                "fold_idx",
                "layer_idx",
                "hook_site",
                "target_name",
                "prediction",
                "prediction_scope",
                "fit_id",
                "activation_index_sha256",
                "activation_row_identity_sha256",
                "model_hash",
                "preprocess_hash",
                "relative_time_seconds",
                "visibility",
            ],
            "schema_id": "person-b-step4-1-bounded-reveal-predictions-v0-1",
        },
        "prediction_contract": {
            "analysis_dtype": "float64",
            "fitted_probe_reuse": "required_without_refit",
            "hook_site": HOOK_SITE,
            "layers": list(LAYERS),
            "operation": (
                "Promote the exact float32 activation vector to float64 and calculate "
                "math.fsum(vector_i * raw_coefficient_i) + raw_intercept; round only "
                "the serialized prediction to 12 decimals."
            ),
            "prediction_scope": "held_out",
            "preprocessing": (
                "Use the stored raw_coefficients and raw_intercept, which already encode "
                "the training-fold scaler; do not fit, alter, or reapply a scaler."
            ),
            "target": "log_sigma_oracle",
        },
        "reveal_contract": {
            "event_definition": (
                "The sole occluded-to-visible transition in each exact core capture."
            ),
            "post_condition": (
                "The first visible model frame immediately following the last occluded "
                "frame; relative_time_seconds=0.0."
            ),
            "pre_condition": (
                "The last occluded model frame immediately before reveal; its existing "
                "OOF prediction is paired at relative_time_seconds=-0.05."
            ),
            "reveal_operation": (
                "Machine-mediated read of only the 100 indexed activation rows named by "
                "the five post identities and 20 frozen layers, followed by prediction "
                "with the already fitted held-out-fold spread probes."
            ),
        },
        "schema_id": "person-b-step4-1-bounded-reveal-contract-v0-1",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "seeds": {
            "probe_fit_seed_reused_not_rerun": 20260719,
            "production_has_no_random_operation": True,
        },
        "state": {
            "manual_u4_inspection_authorized": False,
            "person_a_additional_extraction_required": False,
            "person_b_probe_refit_required": False,
            "post_reveal_inputs_available": True,
            "post_reveal_predictions_produced": False,
            "u4_output_inspected": False,
        },
        "version": CONTRACT_VERSION,
    }


def validate_bounded_reveal_contract(document: Any) -> None:
    if document != build_bounded_reveal_contract():
        raise BoundedRevealContractError("Bounded reveal contract differs from v0.1.")
    state = document["state"]
    if (
        state["manual_u4_inspection_authorized"] is not False
        or state["u4_output_inspected"] is not False
        or state["person_a_additional_extraction_required"] is not False
        or state["person_b_probe_refit_required"] is not False
        or state["post_reveal_inputs_available"] is not True
    ):
        raise BoundedRevealContractError("Bounded reveal state expands authority.")
    if len(document["input_contract"]["events"]) != 5:
        raise BoundedRevealContractError("Exactly five reveal events are required.")


def predict_with_raw_probe(
    vector: Sequence[float] | np.ndarray,
    raw_coefficients: Sequence[float],
    raw_intercept: float,
) -> float:
    """Deterministic prediction primitive used by later authorized production."""

    if len(vector) != 2048 or len(raw_coefficients) != 2048:
        raise BoundedRevealContractError("Reveal vectors and probes must be 2048-wide.")
    values = [float(value) for value in vector]
    weights = [float(value) for value in raw_coefficients]
    intercept = float(raw_intercept)
    if any(not math.isfinite(value) for value in (*values, *weights, intercept)):
        raise BoundedRevealContractError("Reveal prediction inputs must be finite.")
    return round(math.fsum(value * weight for value, weight in zip(values, weights)) + intercept, 12)


def validate_prediction_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    """Validate exact event-layer output coverage without calculating a metric."""

    expected = {
        (event["event_id"], layer)
        for event in reveal_events()
        for layer in LAYERS
    }
    observed: set[tuple[str, int]] = set()
    for row in rows:
        key = (row.get("event_id"), row.get("layer_idx"))
        if key in observed:
            raise BoundedRevealContractError("Duplicate reveal prediction identity.")
        observed.add(key)
        prediction = row.get("prediction")
        if (
            key not in expected
            or row.get("hook_site") != HOOK_SITE
            or row.get("target_name") != "log_sigma_oracle"
            or row.get("prediction_scope") != "held_out"
            or isinstance(prediction, bool)
            or not isinstance(prediction, (int, float))
            or not math.isfinite(float(prediction))
            or row.get("visibility") != "visible"
            or row.get("relative_time_seconds") != 0.0
        ):
            raise BoundedRevealContractError("Reveal prediction row is out of scope.")
    if observed != expected:
        raise BoundedRevealContractError("Reveal prediction coverage is incomplete.")


__all__ = [
    "BoundedRevealContractError",
    "build_bounded_reveal_contract",
    "predict_with_raw_probe",
    "reveal_events",
    "validate_bounded_reveal_contract",
    "validate_prediction_rows",
]
