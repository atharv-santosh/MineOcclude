"""Person B's frozen eight-family baseline-input v0.2 contract.

This module validates contracts and manifests only.  It never runs a baseline,
fits a probe, calculates a metric, or reads U4 outputs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

BASELINE_INPUT_SCHEMA_VERSION_V0_2 = "person-b-baseline-input-v0.2"
BASELINE_FAMILY_MANIFEST_SCHEMA_ID = (
    "person-b-step4-1-eight-family-baseline-input-manifest-v0.2"
)

AUTHORITY_COMMITS = {
    "person_a_activation_store_v2": (
        "55776dc88302b89b52eef483a710fbf6811cf536"
    ),
    "person_b_production_consumer": (
        "ca3bf19120d5553a34a5edc1bda6bfed54859127"
    ),
    "person_b_production_ratification": (
        "c9a519b42cf651e05f5b4f640fda6e1a0aed3e7c"
    ),
    "person_b_step6_6": "e39fef4a59142a84dfb5991d51deeb506eb23a7b",
    "person_c_ten_pilot_acceptance": (
        "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"
    ),
    "person_d_baselines": "853e0acadf050a0b1f318b399b524e57379d03bf",
    "person_e_phase6_acceptance": (
        "5bbe7c7021fe3b1c4c35c78fadfbd92ab51484e8"
    ),
    "person_e_step4_1_handoff": (
        "21d83c19c9d8f36c4dbeeaf45d4626eaf082e7a7"
    ),
}

PERSON_D_CONTRACT_AUTHORITIES = {
    "baseline_export": {
        "byte_size": 8772,
        "git_blob_oid": "aa25a0f6f104dc33da64e6f70ce69c1c2eb8612c",
        "path": "src/mineocclude/baselines/export.py",
        "sha256": "f0d43fa53da783899b911cada668a997c58a0ec796d2280941be8f08fde9b20c",
    },
    "execution_runbook": {
        "byte_size": 4230,
        "git_blob_oid": "f0caabc3244d6acaed04f925a7d331ad4d279305",
        "path": (
            "docs/status/person_d_phase4_step4_1_registry_v2_handoff_v0_1/"
            "execution_runbook.json"
        ),
        "sha256": "5454f0635224ff3fce667ea29f518f8e1dbda7f6dd662143cdfad89abe66dce6",
    },
    "phase0_input_audit": {
        "byte_size": 8431,
        "git_blob_oid": "b6b33fdb0ef05f2eba34eab63b8ed59ed4654089",
        "path": "docs/baselines/person_d_phase0.md",
        "sha256": "affaa628339922e73bd37ffd491b01aeaaf52f197410db60f083ffddce9851a6",
    },
    "phase1_baseline_contract": {
        "byte_size": 9617,
        "git_blob_oid": "3ff4321eeadcc1b066ebbdfcfc677be4983a6a16",
        "path": "docs/baselines/person_d_phase1.md",
        "sha256": "5961b91b057859df7e92df1494ff73b916c232bdd430d4fb213dc84089486db0",
    },
    "scientific_baseline_input_contract": {
        "byte_size": 4114,
        "git_blob_oid": "02ffe4d360279409b74e1d0372cc424cddedd3a0",
        "path": (
            "docs/status/person_d_phase4_step4_1_registry_v2_handoff_v0_1/"
            "scientific_baseline_input_contract.json"
        ),
        "sha256": "a3e823b32451ef83f6b1e4cf5c59ed26a9e480918e03016c11b1fb56948e3f07",
    },
}

FROZEN_BASELINE_FAMILY_IDS = (
    "last_seen",
    "constant_velocity",
    "grouped_shuffled",
    "time_only",
    "explicit_feature",
    "raw_pixel",
    "visible_history_q",
    "known_q_analytic",
)

FROZEN_PILOT_IDS = (
    "layout_00_ep9403",
    "layout_00_ep9441",
    "layout_01_ep9405",
    "layout_01_ep9442",
    "layout_02_ep9407",
    "layout_02_ep9432",
    "layout_03_ep9404",
    "layout_03_ep9443",
    "layout_04_ep9406",
    "layout_04_ep9444",
)

FROZEN_DIRECT_INPUTS = {
    "analysis_config": {
        "byte_size": 4881,
        "path": "configs/analysis/core.yaml",
        "producer_role": "person_b",
        "sha256": "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab",
    },
    "fold_manifest": {
        "byte_size": 742601,
        "path": (
            "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
            "ten_pilot_frame_fold_manifest.json"
        ),
        "producer_role": "person_b",
        "sha256": "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71",
    },
    "oracle_target": {
        "byte_size": 4934874,
        "path": (
            "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
            "production_oracle_target_manifest.json"
        ),
        "producer_role": "person_b",
        "sha256": "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282",
    },
    "source_context_manifest": {
        "byte_size": 4654,
        "path": (
            "docs/status/person_b_phase4_step4_1_baseline_family_contract_v0_2/"
            "source_context_manifest.json"
        ),
        "producer_role": "person_b",
        "sha256": "ce4ba48c53ce57c6321a657e97c166772475a77d459e59ad8d20cc37b33aa74c",
    },
}

FROZEN_SOURCE_CONTEXTS = (
    {
        "capture_package": {
            "byte_size": 662116,
            "path": "data/autonomous/layout_00_ep9403/capture_package_v0_1.json",
            "sha256": "21ea1dba91cf92ad82080088f70905fba053557392437b19591cad1333667213",
        },
        "trajectory_id": "layout_00_ep9403",
    },
    {
        "capture_package": {
            "byte_size": 531375,
            "path": "data/autonomous/layout_00_ep9441/capture_package_v0_1.json",
            "sha256": "5e5d5d8cbeecaa07bd93af1faab23d6bdd0643df4f59e9b72397842efc3d3664",
        },
        "trajectory_id": "layout_00_ep9441",
    },
    {
        "capture_package": {
            "byte_size": 610140,
            "path": "data/autonomous/layout_01_ep9405/capture_package_v0_1.json",
            "sha256": "c139247e3be9132ddf2781f6d8abbe7d4498fa158464e3f47c534cf19b5c614f",
        },
        "trajectory_id": "layout_01_ep9405",
    },
    {
        "capture_package": {
            "byte_size": 531371,
            "path": "data/autonomous/layout_01_ep9442/capture_package_v0_1.json",
            "sha256": "4cb40c2b8b62268fba0556ed38f25644710dede5c1be9cf579e3aea445ab4096",
        },
        "trajectory_id": "layout_01_ep9442",
    },
    {
        "capture_package": {
            "byte_size": 422479,
            "path": "data/autonomous/layout_02_ep9407/capture_package_v0_1.json",
            "sha256": "ed7884bcc5e72db1d8b1c642f0ce668544c7cb348567b0ec820d69db6016004f",
        },
        "trajectory_id": "layout_02_ep9407",
    },
    {
        "capture_package": {
            "byte_size": 531379,
            "path": "data/autonomous/layout_02_ep9432/capture_package_v0_1.json",
            "sha256": "fae0107e2ceb60e62dbc5a89fe459b4d7a952ce8c28cb97faa490d3fde4d4d0c",
        },
        "trajectory_id": "layout_02_ep9432",
    },
    {
        "capture_package": {
            "byte_size": 332665,
            "path": "data/autonomous/layout_03_ep9404/capture_package_v0_1.json",
            "sha256": "c9bc91d934643a53c5b3c39d519e5b3533788021adac57373af5edea12795ac7",
        },
        "trajectory_id": "layout_03_ep9404",
    },
    {
        "capture_package": {
            "byte_size": 531261,
            "path": "data/autonomous/layout_03_ep9443/capture_package_v0_1.json",
            "sha256": "affb4273939c84a869548633f51888a8c2e429466360d906049b63e9e0f6bb83",
        },
        "trajectory_id": "layout_03_ep9443",
    },
    {
        "capture_package": {
            "byte_size": 302914,
            "path": "data/autonomous/layout_04_ep9406/capture_package_v0_1.json",
            "sha256": "3cc2917fb0698d83d4ec12aa7cd7288e4a929dd5f13e810d303fbd1cc348f021",
        },
        "trajectory_id": "layout_04_ep9406",
    },
    {
        "capture_package": {
            "byte_size": 531250,
            "path": "data/autonomous/layout_04_ep9444/capture_package_v0_1.json",
            "sha256": "4fe5bd8bedfdb78be17c580662dda5511b1314d7ee522c64db529d50dfc7c0a0",
        },
        "trajectory_id": "layout_04_ep9444",
    },
)

PERSON_B_PREDICTION_RESERVATION = {
    "byte_size": 84257218,
    "direct_input_to_person_d": False,
    "immutable": True,
    "path": (
        "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
        "person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json"
    ),
    "reserved_for_later_comparison": True,
    "sha256": "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba",
}

FROZEN_TARGET_IDENTITY_BINDINGS = {
    "log_sigma_oracle": {
        "candidate_row_count": 695,
        "identity_sha256": (
            "1643d851e04a80ce3101f1764c24897d9401594c218d28b20a00484704da0fee"
        ),
    },
    "mu_oracle_blocks": {
        "candidate_row_count": 1695,
        "identity_sha256": (
            "78f58f622002b30681f1f2c13dbc67f653920b01c9aa88b106c7bcba1a5681f9"
        ),
    },
}

PERSON_D_FAMILY_MODULES = {
    "constant_velocity": {
        "byte_size": 2488,
        "path": "src/mineocclude/baselines/constant_velocity.py",
        "sha256": "fcf1c9276de173d6b16a38764dff176bedc7c81dc50d832f9c2d47cb10718f8d",
    },
    "explicit_feature": {
        "byte_size": 5676,
        "path": "src/mineocclude/baselines/explicit_feature.py",
        "sha256": "7357090241356663454a396277279390582a60409524e099dd1746c34f84b90d",
    },
    "grouped_shuffled": {
        "byte_size": 5732,
        "path": "src/mineocclude/baselines/shuffled.py",
        "sha256": "e4bb2f5ad3e053d77bd5f85340bd86877efb70112adaef829c2ff1a9b983d6df",
    },
    "known_q_analytic": {
        "byte_size": 3375,
        "path": "src/mineocclude/baselines/known_q_analytic.py",
        "sha256": "856c7cdd690b04513a2beb7e0b814b450343d586889081d6399fc172a36075df",
    },
    "last_seen": {
        "byte_size": 1550,
        "path": "src/mineocclude/baselines/last_seen.py",
        "sha256": "b1e7f4fc03f382bbadfd4d1f67930b8fce22cd73083f92162357c83e962f45ec",
    },
    "raw_pixel": {
        "byte_size": 4754,
        "path": "src/mineocclude/baselines/raw_pixel.py",
        "sha256": "b1602ae5acb9b2b7c88ad41f4bac5c578b7a5fcddeff2f78b1a7321724a7de94",
    },
    "time_only": {
        "byte_size": 4083,
        "path": "src/mineocclude/baselines/time_only.py",
        "sha256": "0990117c370020e96a53a9e896f58ab92f8507e1f55d979b12344274d566d5c0",
    },
    "visible_history_q": {
        "byte_size": 5991,
        "path": "src/mineocclude/baselines/visible_history_q.py",
        "sha256": "a5ade045d9c592fe34ad482d1ca92a1642439469079e9d0b1dbf37ddfb15178a",
    },
}

BASELINE_FAMILY_CONTRACTS_V0_2 = {
    "last_seen": {
        "configuration": {"fit_required": False, "randomness": "none"},
        "expected_output_type": "out_of_fold_mu_prediction",
        "definition": "mu equals the last visible wall-parallel position",
        "feature_access": frozenset(
            {"last_visible_position_blocks", "tau", "visibility"}
        ),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "role": "memory heuristic floor",
        "source": PERSON_D_FAMILY_MODULES["last_seen"],
        "target_names": frozenset({"mu_oracle_blocks"}),
    },
    "constant_velocity": {
        "configuration": {"fit_required": False, "randomness": "none"},
        "expected_output_type": "out_of_fold_mu_prediction",
        "definition": (
            "mu equals last visible position plus estimated visible-window "
            "velocity times tau"
        ),
        "feature_access": frozenset(
            {
                "estimated_velocity_blocks_per_s",
                "last_visible_position_blocks",
                "tau",
                "visibility",
            }
        ),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "role": "Regime A reference",
        "source": PERSON_D_FAMILY_MODULES["constant_velocity"],
        "target_names": frozenset({"mu_oracle_blocks"}),
    },
    "grouped_shuffled": {
        "configuration": {
            "alignment_key": "model_frame_idx",
            "grouping_unit": "trajectory_id",
            "permutation_seed": 20260720,
            "requires_derangement": True,
        },
        "expected_output_type": "out_of_fold_grouped_null_prediction",
        "definition": (
            "seeded trajectory derangement using the donor target at the same "
            "explicit model_frame_idx"
        ),
        "feature_access": frozenset(
            {
                "fold_idx",
                "layout_id",
                "model_frame_idx",
                "oracle_target_sequence",
                "trajectory_id",
            }
        ),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "role": "trajectory-level chance floor",
        "source": PERSON_D_FAMILY_MODULES["grouped_shuffled"],
        "target_names": frozenset(
            {"log_sigma_oracle", "mu_oracle_blocks"}
        ),
    },
    "time_only": {
        "configuration": {
            "fit_scope": "outer_training_folds_only",
            "primary_polynomial_degree": 1,
            "sensitivity_polynomial_degree": 2,
        },
        "expected_output_type": "out_of_fold_log_sigma_prediction",
        "definition": (
            "outer-training-fold polynomial regression of log_sigma on tau only"
        ),
        "feature_access": frozenset({"tau", "visibility"}),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "role": "clock-substitution test",
        "source": PERSON_D_FAMILY_MODULES["time_only"],
        "target_names": frozenset({"log_sigma_oracle"}),
    },
    "explicit_feature": {
        "configuration": {
            "alpha_grid": [0.1, 1.0, 10.0, 100.0],
            "inner_fold_count": 4,
            "scaler_fit_scope": "outer_training_rows_only",
            "seed": 20260719,
        },
        "expected_output_type": "out_of_fold_mu_prediction",
        "definition": (
            "layout-grouped ridge on the frozen observable feature and "
            "interaction list"
        ),
        "feature_access": frozenset(
            {
                "duration_seconds",
                "estimated_velocity_blocks_per_s",
                "last_seen_position_blocks",
                "tau_seconds",
                "velocity_times_duration",
                "velocity_times_tau",
            }
        ),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "role": "non-privileged feature ceiling",
        "source": PERSON_D_FAMILY_MODULES["explicit_feature"],
        "target_names": frozenset({"mu_oracle_blocks"}),
    },
    "raw_pixel": {
        "configuration": {
            "alpha_grid": [0.1, 1.0, 10.0, 100.0],
            "frame_scope": "exact_current_preprocessed_frame_only",
            "inner_fold_count": 4,
            "scaler_fit_scope": "outer_training_rows_only",
            "seed": 20260719,
        },
        "expected_output_type": "out_of_fold_mu_prediction",
        "definition": (
            "layout-grouped ridge on the exact current preprocessed frame only"
        ),
        "feature_access": frozenset({"current_preprocessed_frame"}),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "role": "visual-leakage/scene-cue check",
        "source": PERSON_D_FAMILY_MODULES["raw_pixel"],
        "target_names": frozenset({"mu_oracle_blocks"}),
    },
    "visible_history_q": {
        "configuration": {
            "dt_seconds": 0.05,
            "fit_scope": "outer_training_folds_only",
            "q_estimator": "visible_increment_residual_variance_over_dt",
        },
        "expected_output_type": "out_of_fold_log_sigma_prediction",
        "definition": (
            "estimate q from outer-training-fold visible-history residuals, "
            "then predict ln(sqrt(q_hat * tau))"
        ),
        "feature_access": frozenset(
            {"tau", "visibility", "visible_history_positions"}
        ),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "role": "fair spread baseline",
        "source": PERSON_D_FAMILY_MODULES["visible_history_q"],
        "target_names": frozenset({"log_sigma_oracle"}),
    },
    "known_q_analytic": {
        "configuration": {
            "fair_baseline": False,
            "formula": "ln(sqrt(q_scripted_blocks2_per_s * tau))",
            "randomness": "none",
        },
        "expected_output_type": "privileged_log_sigma_reference",
        "definition": "predict ln(sqrt(q_scripted * tau)) on hidden rows",
        "feature_access": frozenset(
            {"q_scripted_blocks2_per_s", "tau", "visibility"}
        ),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": True,
        },
        "role": "privileged non-fair reference ceiling",
        "source": PERSON_D_FAMILY_MODULES["known_q_analytic"],
        "target_names": frozenset({"log_sigma_oracle"}),
    },
}


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def is_valid_artifact_reference(value: Any) -> bool:
    """Return whether *value* is an exact, byte-sized artifact identity."""

    if not isinstance(value, Mapping):
        return False
    return (
        isinstance(value.get("path"), str)
        and bool(value["path"])
        and _valid_sha256(value.get("sha256"))
        and isinstance(value.get("byte_size"), int)
        and not isinstance(value.get("byte_size"), bool)
        and value["byte_size"] > 0
    )


def _contains_u4_path(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_u4_path(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_u4_path(item) for item in value)
    if not isinstance(value, str):
        return False
    segments = value.casefold().replace("\\", "/").split("/")
    return any(segment == "u4" or segment.startswith("u4_") for segment in segments)


def validate_eight_family_input_manifest(document: Any) -> tuple[str, ...]:
    """Return fail-closed errors for a Person D v0.2 execution manifest."""

    if not isinstance(document, Mapping):
        return ("manifest_not_mapping",)

    errors: list[str] = []
    if document.get("schema_version") != "1.0":
        errors.append("schema_version_mismatch")
    if document.get("schema_id") != BASELINE_FAMILY_MANIFEST_SCHEMA_ID:
        errors.append("schema_id_mismatch")
    if (
        document.get("baseline_input_schema_version")
        != BASELINE_INPUT_SCHEMA_VERSION_V0_2
    ):
        errors.append("baseline_input_schema_version_mismatch")

    families = document.get("baseline_families")
    if not isinstance(families, Sequence) or isinstance(families, (str, bytes)):
        errors.append("baseline_families_not_sequence")
        families = []
    family_ids = [
        family.get("family_id") if isinstance(family, Mapping) else None
        for family in families
    ]
    if document.get("baseline_family_count") != len(FROZEN_BASELINE_FAMILY_IDS):
        errors.append("baseline_family_count_mismatch")
    if any(not isinstance(family_id, str) for family_id in family_ids):
        errors.append("invalid_baseline_family_id")
    elif len(family_ids) != len(set(family_ids)):
        errors.append("duplicate_baseline_family")
    if tuple(family_ids) != FROZEN_BASELINE_FAMILY_IDS:
        errors.append("baseline_family_set_or_order_mismatch")

    for family_id, family in zip(FROZEN_BASELINE_FAMILY_IDS, families):
        if not isinstance(family, Mapping):
            errors.append(f"{family_id}:family_not_mapping")
            continue
        contract = BASELINE_FAMILY_CONTRACTS_V0_2[family_id]
        if family.get("targets") != sorted(contract["target_names"]):
            errors.append(f"{family_id}:target_binding_mismatch")
        expected_target_bindings = {
            target_name: FROZEN_TARGET_IDENTITY_BINDINGS[target_name]
            for target_name in sorted(contract["target_names"])
        }
        if family.get("target_identity_bindings") != expected_target_bindings:
            errors.append(f"{family_id}:target_identity_mismatch")
        if family.get("feature_access") != sorted(contract["feature_access"]):
            errors.append(f"{family_id}:feature_access_mismatch")
        if family.get("configuration") != contract["configuration"]:
            errors.append(f"{family_id}:configuration_mismatch")
        if family.get("expected_output_type") != contract["expected_output_type"]:
            errors.append(f"{family_id}:output_type_mismatch")
        if family.get("legal_information") != contract["legal_information"]:
            errors.append(f"{family_id}:legal_information_mismatch")
        if family.get("definition") != contract["definition"]:
            errors.append(f"{family_id}:definition_mismatch")
        if family.get("source") != contract["source"]:
            errors.append(f"{family_id}:source_authority_mismatch")

    accepted_pilot_ids = document.get("accepted_pilot_ids")
    if not isinstance(accepted_pilot_ids, list) or (
        tuple(accepted_pilot_ids) != FROZEN_PILOT_IDS
    ):
        errors.append("accepted_pilot_ids_mismatch")
    if document.get("random_split_used") is not False:
        errors.append("random_split_not_forbidden")
    if document.get("u4_output_inspected") is not False:
        errors.append("u4_access_not_forbidden")
    if _contains_u4_path(document):
        errors.append("u4_path_referenced")

    direct_inputs = document.get("direct_inputs")
    if not isinstance(direct_inputs, Mapping):
        errors.append("direct_inputs_not_mapping")
    else:
        required_direct_input_types = {
            *FROZEN_DIRECT_INPUTS,
            "preprocessed_frame_manifest",
        }
        if set(direct_inputs) != required_direct_input_types:
            errors.append("direct_input_type_set_mismatch")
        for artifact_type, expected in FROZEN_DIRECT_INPUTS.items():
            actual = direct_inputs.get(artifact_type)
            if actual != expected:
                errors.append(f"{artifact_type}:frozen_identity_mismatch")
        source_context = direct_inputs.get("source_context_manifest")
        if source_context != FROZEN_DIRECT_INPUTS["source_context_manifest"]:
            errors.append("source_context_manifest:frozen_identity_mismatch")
        preprocessed_frames = direct_inputs.get("preprocessed_frame_manifest")
        if not is_valid_artifact_reference(preprocessed_frames):
            errors.append("preprocessed_frame_manifest:invalid_identity")
        forbidden_types = {
            "person_b_prediction",
            "person_b_predictions",
            "fitted_probe",
            "probe_prediction",
        }
        if forbidden_types.intersection(direct_inputs):
            errors.append("person_b_predictions_used_as_direct_input")

    if document.get("person_b_prediction_reservation") != (
        PERSON_B_PREDICTION_RESERVATION
    ):
        errors.append("person_b_prediction_reservation_mismatch")

    source_contexts = document.get("source_contexts")
    if not isinstance(source_contexts, Sequence) or isinstance(
        source_contexts, (str, bytes)
    ):
        errors.append("source_contexts_not_sequence")
    else:
        normalized_contexts = []
        for item in source_contexts:
            if not isinstance(item, Mapping):
                errors.append("source_context_not_mapping")
                continue
            normalized_contexts.append(
                {
                    "capture_package": item.get("capture_package"),
                    "trajectory_id": item.get("trajectory_id"),
                }
            )
            if not is_valid_artifact_reference(item.get("capture_package")):
                errors.append("source_context_capture_identity_invalid")
        if tuple(normalized_contexts) != FROZEN_SOURCE_CONTEXTS:
            errors.append("source_context_pilot_binding_mismatch")

    if document.get("person_d_execution_ready") is not True:
        errors.append("person_d_execution_not_ready")
    return tuple(errors)
