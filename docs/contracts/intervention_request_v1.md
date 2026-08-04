# MineOcclude B→A Intervention Request Contract

Current implementation version: `1.0`

Status: frozen for Phase 1 by the Step 1.8 internal schema sign-off.

## Purpose

This contract defines what Person B must provide before Person A applies an intervention to MineWorld generation.

Every intervention request must be scientifically traceable, expressed in raw activation space, applied at an exact model location, accompanied by explicit dose and cap metadata, and independent of test or held-out outcomes.

Person A validates requests but never repairs them.

## Required request fields

Every request contains:

* `schema_version`
* `request_id`
* `direction`
* `intervention_location`
* `alpha_table`
* `cap`
* `direction_metadata`
* `scaler_metadata`
* `selection_policy`
* `fit_manifest`
* `validation_manifest`
* `heldout_events`
* `validation_flags`

## Direction requirements

The intervention direction must:

* use `space = "raw_activation"`
* contain exactly 2,048 finite numeric values
* have `dimension = 2048`
* have approximately unit L2 norm

Person A does not automatically convert or normalize the supplied direction.

The validator computes the L2 norm using overflow-safe logic. Extremely large but individually finite direction values must produce a structured rejection rather than an uncaught numerical exception.

## Near-zero residual protection

`direction_metadata` records:

* `direction_version`
* `direction_hash`
* `source_run_id`
* `residual_norm_before_normalization`
* `near_zero_threshold`

The original residual must satisfy:

`residual_norm_before_normalization > near_zero_threshold`

A zero or near-zero residual direction cannot be normalized and sent into generation.

## Intervention location

Every request identifies:

* `layer_idx`
* `hook_site`
* `timestep_idx`

For the current MineWorld configuration:

* layer indices are `0–19`
* timestep indices are `0–15`

The hook site must be explicitly named.

## Alpha table

Every dose contains:

* `dose_id`
* `alpha_requested`
* `alpha_applied`
* `intended_block_shift`
* `cap_reduced`

All alpha and intended-shift values must be finite numeric values.

### No unflagged alpha changes

When:

`cap_reduced = false`

the following must hold:

`alpha_requested = alpha_applied`

within numerical tolerance.

Person A must reject a request where an alpha was silently changed without the corresponding cap-reduction flag.

### Flagged cap reduction

When:

`cap_reduced = true`

the magnitude of the applied alpha must be strictly smaller than the magnitude of the requested alpha:

`abs(alpha_applied) < abs(alpha_requested)`

### Sign preservation

Cap application may reduce intervention magnitude.

It may not reverse intervention direction.

When both requested and applied alpha values are nonzero, they must have the same sign.

For example:

`requested = +6, applied = +5`

is allowed if all cap requirements are satisfied.

The following is rejected:

`requested = +6, applied = -5`

because the intervention direction was reversed.

## Declared activation-norm cap

The request contains:

* `max_relative_activation_norm`
* `typical_activation_norm`

The maximum legal applied alpha magnitude is:

`max_relative_activation_norm × typical_activation_norm`

Every dose must satisfy:

`abs(alpha_applied) <= max_relative_activation_norm × typical_activation_norm`

For example, if:

`max_relative_activation_norm = 0.25`

and:

`typical_activation_norm = 20`

then the maximum legal applied magnitude is:

`5`

An applied alpha of `5` is allowed.

An applied alpha of `6` is rejected.

## Scaler metadata

If standardized features were used while fitting the direction, the request must include:

* `used_during_fit`
* `scaler_id`
* `scaler_hash`
* `inverse_transformed_before_export`

When standardized fitting was used, the final exported direction must already have been converted back to raw activation space.

The request must also have:

`raw_space_equivalence_verified = true`

Person A does not perform this conversion automatically.

## Direction-selection policy

The request records:

* `used_test_data_to_select_direction`
* `used_heldout_outcomes_to_select_direction`
* `description`

For acceptance:

* test data must not select the direction
* held-out intervention outcomes must not select the direction

## Fit and validation manifests

Both manifests contain:

* `manifest_id`
* `manifest_hash`
* `event_ids`

Manifest hashes must be valid SHA-256 values.

Event IDs must be non-empty and unique within each manifest.

## Held-out events

Each held-out event contains:

* `event_id`
* `trajectory_id`
* `layout_id`

Fit, validation, and held-out event sets must be mutually disjoint.

Any overlap causes rejection.

## Validation flags

Every request records:

* `time_orthogonalization_checked`
* `raw_space_equivalence_verified`
* `near_zero_residual_detected`
* `contains_cap_reduced_doses`

All flags must be boolean.

For the current contract:

* `raw_space_equivalence_verified` must be true
* `near_zero_residual_detected` must be false
* `contains_cap_reduced_doses` must exactly match the alpha table

Schema v1.0 requires `time_orthogonalization_checked = true`. An unchecked
request is rejected before generation rather than repaired or interpreted.

## No automatic repair

Person A must not automatically:

* convert standardized directions
* normalize non-unit directions
* normalize zero or near-zero residuals
* alter intervention locations
* silently change alpha values
* reverse alpha signs
* allow applied alpha beyond the declared cap
* remove overlapping events
* invent missing provenance

Invalid requests must be corrected upstream and resubmitted.

## Rejection codes

The contract uses machine-readable rejection codes including:

* `missing_required_field`
* `invalid_schema_version`
* `invalid_direction`
* `direction_not_raw_space`
* `direction_not_unit_norm`
* `near_zero_residual_direction`
* `invalid_intervention_location`
* `invalid_alpha_table`
* `invalid_cap`
* `cap_reduction_mismatch`
* `alpha_exceeds_cap`
* `alpha_sign_reversal`
* `invalid_direction_metadata`
* `invalid_scaler_metadata`
* `raw_space_equivalence_unverified`
* `invalid_selection_policy`
* `test_selected_direction`
* `invalid_manifest`
* `data_split_overlap`
* `invalid_heldout_events`
* `invalid_validation_flags`

## Synthetic fixtures

The accepted fixture is:

`tests/fixtures/intervention/accepted_intervention_request.json`

Rejected fixtures cover:

* standardized-space direction
* test-selected direction
* near-zero residual direction
* non-unit direction
* incomplete requests
* split overlap
* invalid cap-reduction semantics
* incorrect cap summary flags
* unflagged alpha reduction
* applied alpha exceeding the declared cap
* alpha sign reversal
* extreme finite direction values

## Pass condition

Step 1.5 passes when:

1. A valid raw-space unit-direction request is accepted.
2. Standardized-space requests are rejected.
3. Test-selected directions are rejected.
4. Zero and near-zero residual directions are rejected.
5. Non-unit directions are rejected.
6. Incomplete requests are rejected.
7. Overlapping data splits are rejected.
8. Unflagged alpha changes are rejected.
9. Applied alpha values beyond the declared cap are rejected.
10. Cap reduction cannot reverse alpha sign.
11. Extreme finite vectors reject without crashing.
12. Validation never mutates or repairs the submitted request.

## Versioning status

The current implementation is frozen schema `1.0`. Result-changing changes to
direction space, intervention location, alpha/cap semantics, validation flags,
split rules, or manifest meaning require a versioned migration and a new run
identity.
