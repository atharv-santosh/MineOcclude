"""Build synthetic fixtures for the B→A intervention-request contract."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


OUTPUT_DIR = Path(__file__).parent

SCHEMA_VERSION = "1.0"

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def make_unit_direction() -> list[float]:
    """Create a simple 2048-dimensional unit vector."""

    return [
        1.0
    ] + [
        0.0
    ] * 2047


def make_accepted_request() -> dict:
    """Create one valid synthetic B→A intervention request."""

    return {
        "schema_version":
            SCHEMA_VERSION,

        "request_id":
            "synthetic_intervention_request_001",

        "direction": {
            "space":
                "raw_activation",

            "dimension":
                2048,

            "values":
                make_unit_direction(),
        },

        "intervention_location": {
            "layer_idx":
                12,

            "hook_site":
                "residual_stream",

            "timestep_idx":
                8,
        },

        "alpha_table": [
            {
                "dose_id":
                    "negative_low",

                "alpha_requested":
                    -0.5,

                "alpha_applied":
                    -0.5,

                "intended_block_shift":
                    -1.0,

                "cap_reduced":
                    False,
            },
            {
                "dose_id":
                    "control",

                "alpha_requested":
                    0.0,

                "alpha_applied":
                    0.0,

                "intended_block_shift":
                    0.0,

                "cap_reduced":
                    False,
            },
            {
                "dose_id":
                    "positive_low",

                "alpha_requested":
                    0.5,

                "alpha_applied":
                    0.5,

                "intended_block_shift":
                    1.0,

                "cap_reduced":
                    False,
            },
            {
                "dose_id":
                    "positive_capped",

                "alpha_requested":
                    6.0,

                "alpha_applied":
                    5.0,

                "intended_block_shift":
                    2.0,

                "cap_reduced":
                    True,
            },
        ],

        "cap": {
            "max_relative_activation_norm":
                0.25,

            "typical_activation_norm":
                20.0,
        },

        "direction_metadata": {
            "direction_version":
                "synthetic_direction_v1",

            "direction_hash":
                SHA_A,

            "source_run_id":
                "synthetic_probe_run_001",

            "residual_norm_before_normalization":
                4.0,

            "near_zero_threshold":
                1e-8,
        },

        "scaler_metadata": {
            "used_during_fit":
                True,

            "scaler_id":
                "synthetic_standard_scaler_001",

            "scaler_hash":
                SHA_B,

            "inverse_transformed_before_export":
                True,
        },

        "selection_policy": {
            "used_test_data_to_select_direction":
                False,

            "used_heldout_outcomes_to_select_direction":
                False,

            "description":
                (
                    "Synthetic direction selected only from "
                    "fit and validation data."
                ),
        },

        "fit_manifest": {
            "manifest_id":
                "synthetic_fit_manifest_001",

            "manifest_hash":
                SHA_C,

            "event_ids": [
                "fit_event_001",
                "fit_event_002",
                "fit_event_003",
            ],
        },

        "validation_manifest": {
            "manifest_id":
                "synthetic_validation_manifest_001",

            "manifest_hash":
                SHA_D,

            "event_ids": [
                "validation_event_001",
                "validation_event_002",
            ],
        },

        "heldout_events": [
            {
                "event_id":
                    "heldout_event_001",

                "trajectory_id":
                    "synthetic_heldout_trajectory_001",

                "layout_id":
                    "synthetic_layout_heldout_01",
            },
            {
                "event_id":
                    "heldout_event_002",

                "trajectory_id":
                    "synthetic_heldout_trajectory_002",

                "layout_id":
                    "synthetic_layout_heldout_02",
            },
        ],

        "validation_flags": {
            "time_orthogonalization_checked":
                True,

            "raw_space_equivalence_verified":
                True,

            "near_zero_residual_detected":
                False,

            "contains_cap_reduced_doses":
                True,
        },
    }


def write_json(
    filename: str,
    value,
) -> None:
    """Write one formatted JSON fixture."""

    path = OUTPUT_DIR / filename

    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        json.dump(
            value,
            file,
            indent=2,
            sort_keys=True,
        )

        file.write("\n")


def main() -> None:
    """Generate accepted and rejected Step 1.5 fixtures."""

    accepted = make_accepted_request()

    write_json(
        "accepted_intervention_request.json",
        accepted,
    )

    standardized = deepcopy(
        accepted
    )

    standardized[
        "direction"
    ][
        "space"
    ] = "standardized"

    standardized[
        "scaler_metadata"
    ][
        "inverse_transformed_before_export"
    ] = False

    standardized[
        "validation_flags"
    ][
        "raw_space_equivalence_verified"
    ] = False

    write_json(
        "rejected_standardized_direction.json",
        standardized,
    )

    test_selected = deepcopy(
        accepted
    )

    test_selected[
        "selection_policy"
    ][
        "used_test_data_to_select_direction"
    ] = True

    write_json(
        "rejected_test_selected_direction.json",
        test_selected,
    )

    near_zero = deepcopy(
        accepted
    )

    near_zero[
        "direction_metadata"
    ][
        "residual_norm_before_normalization"
    ] = 1e-12

    near_zero[
        "validation_flags"
    ][
        "near_zero_residual_detected"
    ] = True

    write_json(
        "rejected_near_zero_direction.json",
        near_zero,
    )

    non_unit = deepcopy(
        accepted
    )

    non_unit[
        "direction"
    ][
        "values"
    ][
        0
    ] = 2.0

    write_json(
        "rejected_non_unit_direction.json",
        non_unit,
    )

    incomplete = deepcopy(
        accepted
    )

    del incomplete[
        "direction_metadata"
    ]

    write_json(
        "rejected_incomplete_request.json",
        incomplete,
    )

    split_overlap = deepcopy(
        accepted
    )

    split_overlap[
        "heldout_events"
    ][
        0
    ][
        "event_id"
    ] = "fit_event_001"

    write_json(
        "rejected_split_overlap.json",
        split_overlap,
    )

    invalid_cap_reduction = deepcopy(
        accepted
    )

    invalid_cap_reduction[
        "alpha_table"
    ][
        3
    ][
        "alpha_applied"
    ] = 6.0

    write_json(
        "rejected_cap_reduction.json",
        invalid_cap_reduction,
    )

    cap_flag_mismatch = deepcopy(
        accepted
    )

    cap_flag_mismatch[
        "validation_flags"
    ][
        "contains_cap_reduced_doses"
    ] = False

    write_json(
        "rejected_cap_flag_mismatch.json",
        cap_flag_mismatch,
    )

    # cap_reduced=false but requested/applied differ.
    unflagged_reduction = deepcopy(
        accepted
    )

    unflagged_reduction[
        "alpha_table"
    ][
        2
    ][
        "alpha_applied"
    ] = 0.25

    write_json(
        "rejected_unflagged_alpha_reduction.json",
        unflagged_reduction,
    )

    # Declared maximum is 0.25 × 20 = 5.
    exceeds_cap = deepcopy(
        accepted
    )

    exceeds_cap[
        "alpha_table"
    ][
        2
    ][
        "alpha_requested"
    ] = 6.0

    exceeds_cap[
        "alpha_table"
    ][
        2
    ][
        "alpha_applied"
    ] = 6.0

    write_json(
        "rejected_alpha_exceeds_cap.json",
        exceeds_cap,
    )

    sign_reversal = deepcopy(
        accepted
    )

    sign_reversal[
        "alpha_table"
    ][
        3
    ][
        "alpha_applied"
    ] = -5.0

    write_json(
        "rejected_alpha_sign_reversal.json",
        sign_reversal,
    )

    extreme_direction = deepcopy(
        accepted
    )

    extreme_direction[
        "direction"
    ][
        "values"
    ] = [
        1e308
    ] * 2048

    write_json(
        "rejected_extreme_direction.json",
        extreme_direction,
    )

    print(
        "Generated Step 1.5 intervention fixtures."
    )


if __name__ == "__main__":
    main()
