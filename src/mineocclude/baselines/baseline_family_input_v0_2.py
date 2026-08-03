"""Person D support for the ratified Person B baseline-input v0.2 contract.

Person B's own v0.2 contract module
(``mineocclude.contracts.baseline_family_inputs``, ``analysis_inputs
._validate_baseline_input_v0_2``) lives only on ``role/person-b-analysis``
at commit ``265cbbb394ee481439397879ad9a99c9038bf4cd`` and has not been
integrated into this branch's checkout. This module does not merge or
vendor that branch's code -- it is Person D's own, independent
implementation of the *producer* side of the identical frozen contract,
built by reading that commit's Git objects directly (never executed,
never imported). Every frozen constant below is copied verbatim from
that exact commit and is cited as such; if Person B's v0.2 contract is
ever revised, these constants must be re-read from the new authoritative
commit, never edited from local judgment.

This module never fits a baseline, never computes a metric, and never
reads a U4 artifact. It only shapes and validates the D-to-B v0.2
per-document handoff -- the same role ``export.py`` already plays for
the v0.1 contract, which this module leaves entirely untouched.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from mineocclude.baselines.interface import BaselineRow, TargetName

#: Person B's v0.2 contract commit -- the sole authority for every
#: frozen constant in this module.
PERSON_B_V0_2_CONTRACT_COMMIT = "265cbbb394ee481439397879ad9a99c9038bf4cd"
PERSON_B_V0_2_PRODUCTION_RATIFICATION_COMMIT = "c9a519b42cf651e05f5b4f640fda6e1a0aed3e7c"
PERSON_A_V0_2_FRAME_HANDOFF_COMMIT = "380b9a392c7ad3a941dbdadcc777c61ed03e1206"
PERSON_E_V0_2_STEP4_1_HANDOFF_COMMIT = "21d83c19c9d8f36c4dbeeaf45d4626eaf082e7a7"

BASELINE_INPUT_SCHEMA_VERSION_V0_2 = "person-b-baseline-input-v0.2"

#: Exact frozen family order -- copied from
#: ``baseline_family_inputs.FROZEN_BASELINE_FAMILY_IDS`` at the commit above.
FROZEN_BASELINE_FAMILY_IDS: tuple[str, ...] = (
    "last_seen",
    "constant_velocity",
    "grouped_shuffled",
    "time_only",
    "explicit_feature",
    "raw_pixel",
    "visible_history_q",
    "known_q_analytic",
)

#: Exact frozen accepted-pilot order -- copied from
#: ``baseline_family_inputs.FROZEN_PILOT_IDS``.
FROZEN_PILOT_IDS: tuple[str, ...] = (
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

#: Frozen direct-input identities every v0.2 document must bind exactly
#: (``raw_pixel`` additionally requires ``preprocessed_frame_manifest``,
#: whose byte identity is not frozen here since it is verified per-run
#: against Person A's committed manifest -- see ``frame_handoff_v0_2.py``).
#: Copied verbatim from ``baseline_family_inputs.FROZEN_DIRECT_INPUTS``.
FROZEN_DIRECT_INPUTS: Mapping[str, Mapping[str, object]] = {
    "analysis_config": {
        "path": "configs/analysis/core.yaml",
        "sha256": "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab",
        "byte_size": 4881,
        "producer_role": "person_b",
    },
    "fold_manifest": {
        "path": (
            "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
            "ten_pilot_frame_fold_manifest.json"
        ),
        "sha256": "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71",
        "byte_size": 742601,
        "producer_role": "person_b",
    },
    "oracle_target": {
        "path": (
            "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
            "production_oracle_target_manifest.json"
        ),
        "sha256": "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282",
        "byte_size": 4934874,
        "producer_role": "person_b",
    },
    "source_context_manifest": {
        "path": (
            "docs/status/person_b_phase4_step4_1_baseline_family_contract_v0_2/"
            "source_context_manifest.json"
        ),
        "sha256": "ce4ba48c53ce57c6321a657e97c166772475a77d459e59ad8d20cc37b33aa74c",
        "byte_size": 4654,
        "producer_role": "person_b",
    },
}

#: Copied verbatim from ``baseline_family_inputs.PERSON_B_PREDICTION_RESERVATION``.
#: ``direct_input_to_person_d`` is the load-bearing field: Person B's
#: predictions are explicitly reserved for a later comparison and are
#: never a direct input to any Person D family.
PERSON_B_PREDICTION_RESERVATION: Mapping[str, object] = {
    "path": (
        "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
        "person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json"
    ),
    "sha256": "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba",
    "byte_size": 84257218,
    "direct_input_to_person_d": False,
    "immutable": True,
    "reserved_for_later_comparison": True,
}

#: Copied verbatim from ``baseline_family_inputs.BASELINE_FAMILY_CONTRACTS_V0_2``
#: (``feature_access``/``target_names`` as sorted tuples here, matching
#: the ``list``-typed document fields they are checked against).
BASELINE_FAMILY_CONTRACTS_V0_2: Mapping[str, Mapping[str, Any]] = {
    "last_seen": {
        "definition": "mu equals the last visible wall-parallel position",
        "role": "memory heuristic floor",
        "feature_access": ("last_visible_position_blocks", "tau", "visibility"),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "target_names": ("mu_oracle_blocks",),
        "configuration": {"fit_required": False, "randomness": "none"},
        "expected_output_type": "out_of_fold_mu_prediction",
    },
    "constant_velocity": {
        "definition": (
            "mu equals last visible position plus estimated visible-window "
            "velocity times tau"
        ),
        "role": "Regime A reference",
        "feature_access": (
            "estimated_velocity_blocks_per_s",
            "last_visible_position_blocks",
            "tau",
            "visibility",
        ),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "target_names": ("mu_oracle_blocks",),
        "configuration": {"fit_required": False, "randomness": "none"},
        "expected_output_type": "out_of_fold_mu_prediction",
    },
    "grouped_shuffled": {
        "definition": (
            "seeded trajectory derangement using the donor target at the same "
            "explicit model_frame_idx"
        ),
        "role": "trajectory-level chance floor",
        "feature_access": (
            "fold_idx",
            "layout_id",
            "model_frame_idx",
            "oracle_target_sequence",
            "trajectory_id",
        ),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "target_names": ("log_sigma_oracle", "mu_oracle_blocks"),
        "configuration": {
            "alignment_key": "model_frame_idx",
            "grouping_unit": "trajectory_id",
            "permutation_seed": 20260720,
            "requires_derangement": True,
        },
        "expected_output_type": "out_of_fold_grouped_null_prediction",
    },
    "time_only": {
        "definition": "outer-training-fold polynomial regression of log_sigma on tau only",
        "role": "clock-substitution test",
        "feature_access": ("tau", "visibility"),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "target_names": ("log_sigma_oracle",),
        "configuration": {
            "fit_scope": "outer_training_folds_only",
            "primary_polynomial_degree": 1,
            "sensitivity_polynomial_degree": 2,
        },
        "expected_output_type": "out_of_fold_log_sigma_prediction",
    },
    "explicit_feature": {
        "definition": "layout-grouped ridge on the frozen observable feature and interaction list",
        "role": "non-privileged feature ceiling",
        "feature_access": (
            "duration_seconds",
            "estimated_velocity_blocks_per_s",
            "last_seen_position_blocks",
            "tau_seconds",
            "velocity_times_duration",
            "velocity_times_tau",
        ),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "target_names": ("mu_oracle_blocks",),
        "configuration": {
            "alpha_grid": [0.1, 1.0, 10.0, 100.0],
            "inner_fold_count": 4,
            "scaler_fit_scope": "outer_training_rows_only",
            "seed": 20260719,
        },
        "expected_output_type": "out_of_fold_mu_prediction",
    },
    "raw_pixel": {
        "definition": "layout-grouped ridge on the exact current preprocessed frame only",
        "role": "visual-leakage/scene-cue check",
        "feature_access": ("current_preprocessed_frame",),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "target_names": ("mu_oracle_blocks",),
        "configuration": {
            "alpha_grid": [0.1, 1.0, 10.0, 100.0],
            "frame_scope": "exact_current_preprocessed_frame_only",
            "inner_fold_count": 4,
            "scaler_fit_scope": "outer_training_rows_only",
            "seed": 20260719,
        },
        "expected_output_type": "out_of_fold_mu_prediction",
    },
    "visible_history_q": {
        "definition": (
            "estimate q from outer-training-fold visible-history residuals, "
            "then predict ln(sqrt(q_hat * tau))"
        ),
        "role": "fair spread baseline",
        "feature_access": ("tau", "visibility", "visible_history_positions"),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": False,
        },
        "target_names": ("log_sigma_oracle",),
        "configuration": {
            "dt_seconds": 0.05,
            "fit_scope": "outer_training_folds_only",
            "q_estimator": "visible_increment_residual_variance_over_dt",
        },
        "expected_output_type": "out_of_fold_log_sigma_prediction",
    },
    "known_q_analytic": {
        "definition": "predict ln(sqrt(q_scripted * tau)) on hidden rows",
        "role": "privileged non-fair reference ceiling",
        "feature_access": ("q_scripted_blocks2_per_s", "tau", "visibility"),
        "legal_information": {
            "uses_future_information": False,
            "uses_hidden_truth": False,
            "uses_scripted_q": True,
        },
        "target_names": ("log_sigma_oracle",),
        "configuration": {
            "fair_baseline": False,
            "formula": "ln(sqrt(q_scripted_blocks2_per_s * tau))",
            "randomness": "none",
        },
        "expected_output_type": "privileged_log_sigma_reference",
    },
}


class BaselineFamilyInputV02Error(ValueError):
    """Raised when a call to build a v0.2 document is malformed."""


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def is_valid_artifact_reference(value: Any) -> bool:
    """Mirror of ``baseline_family_inputs.is_valid_artifact_reference``."""

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


def build_direct_inputs_binding(
    *,
    baseline_family: str,
    preprocessed_frame_manifest_reference: Mapping[str, object] | None = None,
) -> dict:
    """Build the exact ``direct_inputs`` mapping one v0.2 document must bind.

    ``raw_pixel`` is the only family whose frozen feature_access
    (``current_preprocessed_frame``) requires Person A's preprocessed
    frames as a direct input; every other family's frozen feature list
    never touches frame pixels. Only ``raw_pixel`` therefore requires
    ``preprocessed_frame_manifest_reference`` here.
    """

    if baseline_family not in BASELINE_FAMILY_CONTRACTS_V0_2:
        raise BaselineFamilyInputV02Error(
            f"unsupported baseline_family={baseline_family!r}"
        )
    direct_inputs = {key: dict(value) for key, value in FROZEN_DIRECT_INPUTS.items()}
    if baseline_family == "raw_pixel":
        if not is_valid_artifact_reference(preprocessed_frame_manifest_reference):
            raise BaselineFamilyInputV02Error(
                "raw_pixel requires a valid preprocessed_frame_manifest_reference "
                "(path/sha256/byte_size)"
            )
        direct_inputs["preprocessed_frame_manifest"] = dict(
            preprocessed_frame_manifest_reference
        )
    elif preprocessed_frame_manifest_reference is not None:
        raise BaselineFamilyInputV02Error(
            f"baseline_family={baseline_family!r} must not bind a "
            "preprocessed_frame_manifest -- only raw_pixel consumes frame pixels"
        )
    return direct_inputs


def build_baseline_document_v0_2(
    rows: Sequence[BaselineRow],
    *,
    baseline_id: str,
    baseline_family: str,
    target_name: TargetName,
    config_hash: str,
    input_manifest_hash: str,
    fit_manifest_hash: str,
    accepted_pilot_ids: Sequence[str] = FROZEN_PILOT_IDS,
    preprocessed_frame_manifest_reference: Mapping[str, object] | None = None,
    fit_id_by_key: Mapping[tuple[str, int], str] | None = None,
    default_fit_id: str | None = None,
) -> dict:
    """Build one ``person-b-baseline-input-v0.2`` document for one family/target.

    Same applicable-rows-only invariant as ``export.build_baseline_document``:
    a baseline that cannot define a value for a frame omits that row
    rather than fabricating a prediction. This function shapes a
    document only -- it never fits, executes, or scores a baseline.
    """

    if baseline_family not in BASELINE_FAMILY_CONTRACTS_V0_2:
        raise BaselineFamilyInputV02Error(
            f"unsupported baseline_family={baseline_family!r}"
        )
    contract = BASELINE_FAMILY_CONTRACTS_V0_2[baseline_family]
    if target_name not in contract["target_names"]:
        raise BaselineFamilyInputV02Error(
            f"target_name={target_name!r} is not allowed for {baseline_family!r}"
        )
    if fit_id_by_key is None and default_fit_id is None:
        raise BaselineFamilyInputV02Error(
            "either fit_id_by_key or default_fit_id must be supplied"
        )
    for name, value in (
        ("config_hash", config_hash),
        ("input_manifest_hash", input_manifest_hash),
        ("fit_manifest_hash", fit_manifest_hash),
    ):
        if not _valid_sha256(value):
            raise BaselineFamilyInputV02Error(f"{name} must be a SHA-256 hex digest")

    direct_inputs = build_direct_inputs_binding(
        baseline_family=baseline_family,
        preprocessed_frame_manifest_reference=preprocessed_frame_manifest_reference,
    )

    prediction_rows: list[dict] = []
    seen_keys: set[tuple[str, int]] = set()
    for row in rows:
        if row.baseline_name != baseline_family or row.target_name != target_name:
            continue
        if not row.applicable:
            continue
        key = (row.trajectory_id, row.model_frame_idx)
        if key in seen_keys:
            raise BaselineFamilyInputV02Error(f"duplicate baseline prediction for {key}")
        seen_keys.add(key)
        fit_id = (fit_id_by_key or {}).get(key, default_fit_id)
        if fit_id is None:
            raise BaselineFamilyInputV02Error(f"no fit_id available for row {key}")
        prediction_rows.append(
            {
                "trajectory_id": row.trajectory_id,
                "model_frame_idx": row.model_frame_idx,
                "fold_idx": row.fold,
                "prediction": row.prediction,
                "prediction_scope": "out_of_fold",
                "fit_id": fit_id,
            }
        )

    if not prediction_rows:
        raise BaselineFamilyInputV02Error(
            f"no applicable {target_name!r} rows for baseline_family {baseline_family!r}"
        )

    return {
        "schema_version": "1.0",
        "baseline_input_schema_version": BASELINE_INPUT_SCHEMA_VERSION_V0_2,
        "producer_role": "person_d",
        "baseline_id": baseline_id,
        "baseline_family": baseline_family,
        "target_name": target_name,
        "feature_access": sorted(contract["feature_access"]),
        "legal_information": dict(contract["legal_information"]),
        "config_hash": config_hash,
        "input_manifest_hash": input_manifest_hash,
        "fold_manifest_hash": FROZEN_DIRECT_INPUTS["fold_manifest"]["sha256"],
        "fit_manifest_hash": fit_manifest_hash,
        "direct_inputs": direct_inputs,
        "accepted_pilot_ids": list(accepted_pilot_ids),
        "person_b_prediction_reservation": dict(PERSON_B_PREDICTION_RESERVATION),
        "random_split_used": False,
        "u4_output_inspected": False,
        "rows": prediction_rows,
    }


def validate_baseline_document_v0_2(document: Any) -> tuple[str, ...]:
    """Independent (not imported) replica of Person B's per-document v0.2 checks.

    Returns a tuple of fail-closed error codes; empty means the
    document satisfies every frozen v0.2 rule this module knows about
    from reading commit ``265cbbb`` directly. This is Person D's own
    self-check before any handoff -- it does not substitute for, and is
    not identical code to, Person B's authoritative validator.
    """

    if not isinstance(document, Mapping):
        return ("document_not_mapping",)

    errors: list[str] = []
    if document.get("schema_version") != "1.0":
        errors.append("schema_version_mismatch")
    if document.get("baseline_input_schema_version") != BASELINE_INPUT_SCHEMA_VERSION_V0_2:
        errors.append("baseline_input_schema_version_mismatch")
    if document.get("producer_role") != "person_d":
        errors.append("producer_role_mismatch")

    family = document.get("baseline_family")
    contract = (
        BASELINE_FAMILY_CONTRACTS_V0_2.get(family) if isinstance(family, str) else None
    )
    if contract is None:
        errors.append("unsupported_baseline_family")

    target_name = document.get("target_name")
    if contract is not None and target_name not in contract["target_names"]:
        errors.append("target_name_not_allowed_for_family")

    feature_access = document.get("feature_access")
    if not isinstance(feature_access, list) or not feature_access:
        errors.append("feature_access_invalid")
    elif contract is not None and (
        sorted(feature_access) != sorted(contract["feature_access"])
        or len(feature_access) != len(set(feature_access))
    ):
        errors.append("feature_access_mismatch")

    if contract is not None and document.get("legal_information") != dict(
        contract["legal_information"]
    ):
        errors.append("legal_information_mismatch")

    for field in ("config_hash", "input_manifest_hash", "fold_manifest_hash", "fit_manifest_hash"):
        if not _valid_sha256(document.get(field)):
            errors.append(f"{field}_invalid")
    if document.get("config_hash") != FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"]:
        errors.append("config_hash_mismatch")
    if document.get("fold_manifest_hash") != FROZEN_DIRECT_INPUTS["fold_manifest"]["sha256"]:
        errors.append("fold_manifest_hash_mismatch")

    direct_inputs = document.get("direct_inputs")
    if not isinstance(direct_inputs, Mapping):
        errors.append("direct_inputs_not_mapping")
    else:
        required_types = set(FROZEN_DIRECT_INPUTS)
        if family == "raw_pixel":
            required_types.add("preprocessed_frame_manifest")
        if set(direct_inputs) != required_types:
            errors.append("direct_input_type_set_mismatch")
        for artifact_type, expected in FROZEN_DIRECT_INPUTS.items():
            if direct_inputs.get(artifact_type) != dict(expected):
                errors.append(f"{artifact_type}_frozen_identity_mismatch")
        if family == "raw_pixel" and not is_valid_artifact_reference(
            direct_inputs.get("preprocessed_frame_manifest")
        ):
            errors.append("preprocessed_frame_manifest_invalid")
        if any(
            str(key).startswith("person_b_prediction") for key in direct_inputs
        ):
            errors.append("person_b_predictions_used_as_direct_input")

    accepted_pilot_ids = document.get("accepted_pilot_ids")
    if not isinstance(accepted_pilot_ids, list) or tuple(accepted_pilot_ids) != FROZEN_PILOT_IDS:
        errors.append("accepted_pilot_ids_mismatch")
    if document.get("person_b_prediction_reservation") != dict(PERSON_B_PREDICTION_RESERVATION):
        errors.append("person_b_prediction_reservation_mismatch")
    if document.get("random_split_used") is not False:
        errors.append("random_split_not_forbidden")
    if document.get("u4_output_inspected") is not False:
        errors.append("u4_access_not_forbidden")

    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        errors.append("rows_not_non_empty_list")
    else:
        seen: set[tuple[str, int]] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                errors.append("row_not_mapping")
                continue
            required_row = (
                "trajectory_id",
                "model_frame_idx",
                "fold_idx",
                "prediction",
                "prediction_scope",
                "fit_id",
            )
            if any(field not in row for field in required_row):
                errors.append("row_missing_required_field")
                continue
            key = (row["trajectory_id"], row["model_frame_idx"])
            if (
                row["trajectory_id"] not in FROZEN_PILOT_IDS
                or not isinstance(row["model_frame_idx"], int)
                or isinstance(row["model_frame_idx"], bool)
                or row["model_frame_idx"] < 0
                or not isinstance(row["fold_idx"], int)
                or isinstance(row["fold_idx"], bool)
                or row["fold_idx"] < 0
                or not isinstance(row["fit_id"], str)
                or not row["fit_id"]
            ):
                errors.append("row_identity_invalid")
                continue
            if key in seen:
                errors.append("duplicate_row_identity")
            seen.add(key)
            prediction = row["prediction"]
            if isinstance(prediction, bool) or not isinstance(prediction, (int, float)):
                errors.append("row_prediction_not_numeric")
            elif not math.isfinite(prediction):
                errors.append("row_prediction_not_finite")
            if row["prediction_scope"] != "out_of_fold":
                errors.append("row_not_out_of_fold")

    return tuple(errors)
