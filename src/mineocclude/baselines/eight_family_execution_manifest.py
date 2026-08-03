"""Pre-execution eight-family manifest for Person D Step 4.1 (runner preparation).

This binds every frozen identity a Step 4.1 production run depends on
*before* any baseline is fit -- the artifact the frozen production CLI
(``scripts/run_person_d_step4_1_eight_family_production.py``) validates
at preflight, per Person B's own ``baseline_family_inputs
.validate_eight_family_input_manifest`` at commit
``265cbbb394ee481439397879ad9a99c9038bf4cd`` (read directly, not
imported -- that branch is not merged here). Building or validating
this manifest never fits a baseline, computes a metric, or reads a U4
artifact.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mineocclude.analysis.manifests import sha256_file
from mineocclude.baselines.baseline_family_input_v0_2 import (
    BASELINE_FAMILY_CONTRACTS_V0_2,
    BASELINE_INPUT_SCHEMA_VERSION_V0_2,
    FROZEN_BASELINE_FAMILY_IDS,
    FROZEN_DIRECT_INPUTS,
    FROZEN_PILOT_IDS,
    PERSON_B_PREDICTION_RESERVATION,
    is_valid_artifact_reference,
)

BASELINE_FAMILY_MANIFEST_SCHEMA_ID = (
    "person-b-step4-1-eight-family-baseline-input-manifest-v0.2"
)

#: Copied verbatim from ``baseline_family_inputs.FROZEN_SOURCE_CONTEXTS``
#: at commit 265cbbb.
FROZEN_SOURCE_CONTEXTS: tuple[Mapping[str, Any], ...] = (
    {
        "trajectory_id": "layout_00_ep9403",
        "capture_package": {
            "path": "data/autonomous/layout_00_ep9403/capture_package_v0_1.json",
            "sha256": "21ea1dba91cf92ad82080088f70905fba053557392437b19591cad1333667213",
            "byte_size": 662116,
        },
    },
    {
        "trajectory_id": "layout_00_ep9441",
        "capture_package": {
            "path": "data/autonomous/layout_00_ep9441/capture_package_v0_1.json",
            "sha256": "5e5d5d8cbeecaa07bd93af1faab23d6bdd0643df4f59e9b72397842efc3d3664",
            "byte_size": 531375,
        },
    },
    {
        "trajectory_id": "layout_01_ep9405",
        "capture_package": {
            "path": "data/autonomous/layout_01_ep9405/capture_package_v0_1.json",
            "sha256": "c139247e3be9132ddf2781f6d8abbe7d4498fa158464e3f47c534cf19b5c614f",
            "byte_size": 610140,
        },
    },
    {
        "trajectory_id": "layout_01_ep9442",
        "capture_package": {
            "path": "data/autonomous/layout_01_ep9442/capture_package_v0_1.json",
            "sha256": "4cb40c2b8b62268fba0556ed38f25644710dede5c1be9cf579e3aea445ab4096",
            "byte_size": 531371,
        },
    },
    {
        "trajectory_id": "layout_02_ep9407",
        "capture_package": {
            "path": "data/autonomous/layout_02_ep9407/capture_package_v0_1.json",
            "sha256": "ed7884bcc5e72db1d8b1c642f0ce668544c7cb348567b0ec820d69db6016004f",
            "byte_size": 422479,
        },
    },
    {
        "trajectory_id": "layout_02_ep9432",
        "capture_package": {
            "path": "data/autonomous/layout_02_ep9432/capture_package_v0_1.json",
            "sha256": "fae0107e2ceb60e62dbc5a89fe459b4d7a952ce8c28cb97faa490d3fde4d4d0c",
            "byte_size": 531379,
        },
    },
    {
        "trajectory_id": "layout_03_ep9404",
        "capture_package": {
            "path": "data/autonomous/layout_03_ep9404/capture_package_v0_1.json",
            "sha256": "c9bc91d934643a53c5b3c39d519e5b3533788021adac57373af5edea12795ac7",
            "byte_size": 332665,
        },
    },
    {
        "trajectory_id": "layout_03_ep9443",
        "capture_package": {
            "path": "data/autonomous/layout_03_ep9443/capture_package_v0_1.json",
            "sha256": "affb4273939c84a869548633f51888a8c2e429466360d906049b63e9e0f6bb83",
            "byte_size": 531261,
        },
    },
    {
        "trajectory_id": "layout_04_ep9406",
        "capture_package": {
            "path": "data/autonomous/layout_04_ep9406/capture_package_v0_1.json",
            "sha256": "3cc2917fb0698d83d4ec12aa7cd7288e4a929dd5f13e810d303fbd1cc348f021",
            "byte_size": 302914,
        },
    },
    {
        "trajectory_id": "layout_04_ep9444",
        "capture_package": {
            "path": "data/autonomous/layout_04_ep9444/capture_package_v0_1.json",
            "sha256": "4fe5bd8bedfdb78be17c580662dda5511b1314d7ee522c64db529d50dfc7c0a0",
            "byte_size": 531250,
        },
    },
)

#: Copied verbatim from ``baseline_family_inputs.FROZEN_TARGET_IDENTITY_BINDINGS``.
FROZEN_TARGET_IDENTITY_BINDINGS: Mapping[str, Mapping[str, Any]] = {
    "log_sigma_oracle": {
        "candidate_row_count": 695,
        "identity_sha256": "1643d851e04a80ce3101f1764c24897d9401594c218d28b20a00484704da0fee",
    },
    "mu_oracle_blocks": {
        "candidate_row_count": 1695,
        "identity_sha256": "78f58f622002b30681f1f2c13dbc67f653920b01c9aa88b106c7bcba1a5681f9",
    },
}

#: Person D's own family-module files, hashed at build time (never
#: hardcoded) -- these are D-owned and locally present, unlike Person
#: B/A's artifacts above, which D cannot recompute without merging
#: another role's branch.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FAMILY_MODULE_PATHS: Mapping[str, str] = {
    "last_seen": "src/mineocclude/baselines/last_seen.py",
    "constant_velocity": "src/mineocclude/baselines/constant_velocity.py",
    "grouped_shuffled": "src/mineocclude/baselines/shuffled.py",
    "time_only": "src/mineocclude/baselines/time_only.py",
    "explicit_feature": "src/mineocclude/baselines/explicit_feature.py",
    "raw_pixel": "src/mineocclude/baselines/raw_pixel.py",
    "visible_history_q": "src/mineocclude/baselines/visible_history_q.py",
    "known_q_analytic": "src/mineocclude/baselines/known_q_analytic.py",
}


def current_person_d_family_modules() -> dict:
    """Hash Person D's own eight family-implementation files right now."""

    return {
        family_id: {
            "path": relative_path,
            "sha256": sha256_file(_REPO_ROOT / relative_path),
            "byte_size": (_REPO_ROOT / relative_path).stat().st_size,
        }
        for family_id, relative_path in _FAMILY_MODULE_PATHS.items()
    }


def build_eight_family_execution_manifest(
    *,
    preprocessed_frame_manifest_reference: Mapping[str, object],
) -> dict:
    """Build the pre-execution manifest binding every frozen Step 4.1 identity.

    Does not fit, execute, or score anything -- purely an identity and
    configuration binding, checkable before any family is run.
    """

    if not is_valid_artifact_reference(preprocessed_frame_manifest_reference):
        raise ValueError(
            "preprocessed_frame_manifest_reference must be a valid artifact "
            "reference (path/sha256/byte_size)"
        )

    family_modules = current_person_d_family_modules()
    families = []
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        contract = BASELINE_FAMILY_CONTRACTS_V0_2[family_id]
        families.append(
            {
                "family_id": family_id,
                "definition": contract["definition"],
                "targets": sorted(contract["target_names"]),
                "target_identity_bindings": {
                    target: dict(FROZEN_TARGET_IDENTITY_BINDINGS[target])
                    for target in sorted(contract["target_names"])
                },
                "feature_access": sorted(contract["feature_access"]),
                "configuration": dict(contract["configuration"]),
                "expected_output_type": contract["expected_output_type"],
                "legal_information": dict(contract["legal_information"]),
                "source": family_modules[family_id],
            }
        )

    direct_inputs = {key: dict(value) for key, value in FROZEN_DIRECT_INPUTS.items()}
    direct_inputs["preprocessed_frame_manifest"] = dict(
        preprocessed_frame_manifest_reference
    )

    return {
        "schema_version": "1.0",
        "schema_id": BASELINE_FAMILY_MANIFEST_SCHEMA_ID,
        "baseline_input_schema_version": BASELINE_INPUT_SCHEMA_VERSION_V0_2,
        "baseline_family_count": len(FROZEN_BASELINE_FAMILY_IDS),
        "baseline_families": families,
        "accepted_pilot_ids": list(FROZEN_PILOT_IDS),
        "random_split_used": False,
        "u4_output_inspected": False,
        "direct_inputs": direct_inputs,
        "person_b_prediction_reservation": dict(PERSON_B_PREDICTION_RESERVATION),
        "source_contexts": [dict(context) for context in FROZEN_SOURCE_CONTEXTS],
        "person_d_execution_ready": True,
    }


def _contains_u4_path(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_u4_path(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_u4_path(item) for item in value)
    if not isinstance(value, str):
        return False
    segments = value.casefold().replace("\\", "/").split("/")
    return any(segment == "u4" or segment.startswith("u4_") for segment in segments)


def validate_eight_family_execution_manifest(document: Any) -> tuple[str, ...]:
    """Independent (not imported) replica of Person B's manifest-level checks."""

    if not isinstance(document, Mapping):
        return ("manifest_not_mapping",)

    errors: list[str] = []
    if document.get("schema_version") != "1.0":
        errors.append("schema_version_mismatch")
    if document.get("schema_id") != BASELINE_FAMILY_MANIFEST_SCHEMA_ID:
        errors.append("schema_id_mismatch")
    if document.get("baseline_input_schema_version") != BASELINE_INPUT_SCHEMA_VERSION_V0_2:
        errors.append("baseline_input_schema_version_mismatch")

    families = document.get("baseline_families")
    if not isinstance(families, list):
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
        expected_bindings = {
            target: dict(FROZEN_TARGET_IDENTITY_BINDINGS[target])
            for target in sorted(contract["target_names"])
        }
        if family.get("target_identity_bindings") != expected_bindings:
            errors.append(f"{family_id}:target_identity_mismatch")
        if family.get("feature_access") != sorted(contract["feature_access"]):
            errors.append(f"{family_id}:feature_access_mismatch")
        if family.get("configuration") != dict(contract["configuration"]):
            errors.append(f"{family_id}:configuration_mismatch")
        if family.get("expected_output_type") != contract["expected_output_type"]:
            errors.append(f"{family_id}:output_type_mismatch")
        if family.get("legal_information") != dict(contract["legal_information"]):
            errors.append(f"{family_id}:legal_information_mismatch")
        if family.get("definition") != contract["definition"]:
            errors.append(f"{family_id}:definition_mismatch")

    accepted_pilot_ids = document.get("accepted_pilot_ids")
    if not isinstance(accepted_pilot_ids, list) or tuple(accepted_pilot_ids) != FROZEN_PILOT_IDS:
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
        required_types = {*FROZEN_DIRECT_INPUTS, "preprocessed_frame_manifest"}
        if set(direct_inputs) != required_types:
            errors.append("direct_input_type_set_mismatch")
        for artifact_type, expected in FROZEN_DIRECT_INPUTS.items():
            if direct_inputs.get(artifact_type) != dict(expected):
                errors.append(f"{artifact_type}:frozen_identity_mismatch")
        if not is_valid_artifact_reference(direct_inputs.get("preprocessed_frame_manifest")):
            errors.append("preprocessed_frame_manifest:invalid_identity")
        forbidden_types = {
            "person_b_prediction",
            "person_b_predictions",
            "fitted_probe",
            "probe_prediction",
        }
        if forbidden_types.intersection(direct_inputs):
            errors.append("person_b_predictions_used_as_direct_input")

    if document.get("person_b_prediction_reservation") != dict(PERSON_B_PREDICTION_RESERVATION):
        errors.append("person_b_prediction_reservation_mismatch")

    source_contexts = document.get("source_contexts")
    if not isinstance(source_contexts, list):
        errors.append("source_contexts_not_sequence")
    else:
        normalized = tuple(
            {
                "trajectory_id": item.get("trajectory_id") if isinstance(item, Mapping) else None,
                "capture_package": item.get("capture_package") if isinstance(item, Mapping) else None,
            }
            for item in source_contexts
        )
        expected = tuple(dict(context) for context in FROZEN_SOURCE_CONTEXTS)
        if normalized != expected:
            errors.append("source_context_pilot_binding_mismatch")
        for item in source_contexts:
            if isinstance(item, Mapping) and not is_valid_artifact_reference(
                item.get("capture_package")
            ):
                errors.append("source_context_capture_identity_invalid")

    if document.get("person_d_execution_ready") is not True:
        errors.append("person_d_execution_not_ready")

    return tuple(errors)
