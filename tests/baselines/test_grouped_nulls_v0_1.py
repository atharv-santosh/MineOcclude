"""Tests for grouped nulls and paired comparison rows (Step 6.3).

The invariants under test are the ones that make a comparison
interpretable at all: the published null must be the seeded, explicit-
donor null the floor already uses; the two sides of a comparison must
score the identical requested rows; a non-applicable or missing side
stays visible and unscored rather than becoming zero; and regenerating
either document from the same inputs must be byte-identical.

Every fixture here is synthetic and labeled as such.
"""

from __future__ import annotations

import pytest

from mineocclude.baselines.grouped_nulls_v0_1 import (
    FROZEN_PERMUTATION_COUNT,
    FROZEN_PERMUTATION_SEED,
    FROZEN_RESAMPLING_UNIT,
    FROZEN_ROW_LEVEL_PAIRING_KEYS,
    GROUPED_NULLS_SCHEMA_ID,
    PAIRED_COMPARISONS_SCHEMA_ID,
    GroupedNullError,
    build_grouped_null_document,
    build_paired_comparison_document,
    build_paired_rows,
    dump_document,
    validate_grouped_null_document,
    validate_paired_comparison_document,
)
from mineocclude.baselines.interface import TrajectoryContext, make_baseline_row
from mineocclude.baselines.shuffled import apply_grouped_shuffle

SEED = FROZEN_PERMUTATION_SEED


def _context(trajectory_id, layout_id, frame_idx, fold):
    return TrajectoryContext(
        trajectory_id=trajectory_id,
        layout_id=layout_id,
        model_frame_idx=frame_idx,
        fold=fold,
        regime="A",
        tau_seconds=0.05 * frame_idx,
        visibility=False,
        last_seen_position_blocks=float(frame_idx),
        last_seen_velocity_blocks_per_s=1.0,
        v_scripted_blocks_per_s=None,
        q_scripted_blocks2_per_s=None,
        duration_seconds=0.8,
        config_hash="cfg-test",
        seed=7,
    )


def _fixture():
    contexts = []
    targets = {}
    for index in range(4):
        trajectory_id = f"traj-{index}"
        contexts.extend(
            _context(trajectory_id, f"layout-{index}", frame_idx, fold=index)
            for frame_idx in range(3)
        )
        targets[trajectory_id] = {
            "mu_oracle_blocks": {f: 10.0 * index + f for f in range(3)},
            "log_sigma_oracle": {f: -1.0 * index - f for f in range(3)},
        }
    return contexts, targets


def _method_rows(contexts, method, *, applicable=True, reason="method defines no value"):
    return [
        make_baseline_row(
            ctx,
            baseline_name=method,
            target_name="mu_oracle_blocks",
            prediction=float(ctx.model_frame_idx) if applicable else None,
            applicable=applicable,
            fit_metadata={} if applicable else {"reason": reason},
        )
        for ctx in contexts
    ]


def _requested_keys(contexts, target="mu_oracle_blocks"):
    return [(ctx.trajectory_id, ctx.model_frame_idx, target) for ctx in contexts]


# --------------------------------------------------------------------------
# Grouped nulls
# --------------------------------------------------------------------------


def test_grouped_null_document_binds_person_b_frozen_specification():
    contexts, targets = _fixture()
    null_rows = apply_grouped_shuffle(contexts, targets, SEED)
    document = build_grouped_null_document(
        contexts=contexts,
        trajectory_targets=targets,
        null_rows=null_rows,
        seed=SEED,
        run_id="synthetic-null-v0-1",
    )
    validate_grouped_null_document(document)
    assert document["schema_id"] == GROUPED_NULLS_SCHEMA_ID
    assert document["resampling_unit"] == FROZEN_RESAMPLING_UNIT
    assert document["permutation_count"] == FROZEN_PERMUTATION_COUNT
    assert document["grouping_unit"] == "trajectory_id"
    assert document["alignment_key"] == "model_frame_idx"
    assert document["requires_derangement"] is True


def test_grouped_null_document_records_explicit_donor_identity_per_trajectory():
    contexts, targets = _fixture()
    null_rows = apply_grouped_shuffle(contexts, targets, SEED)
    document = build_grouped_null_document(
        contexts=contexts,
        trajectory_targets=targets,
        null_rows=null_rows,
        seed=SEED,
        run_id="synthetic-null-v0-1",
    )
    assignments = document["donor_assignments"]
    assert len(assignments) == 4
    for entry in assignments:
        assert entry["recipient_trajectory_id"] != entry["donor_trajectory_id"]
        assert entry["recipient_layout_id"]
        assert entry["recipient_fold_idx"] is not None


def test_grouped_null_document_is_deterministic():
    contexts, targets = _fixture()
    null_rows = apply_grouped_shuffle(contexts, targets, SEED)
    kwargs = dict(
        contexts=contexts,
        trajectory_targets=targets,
        null_rows=null_rows,
        seed=SEED,
        run_id="synthetic-null-v0-1",
    )
    assert dump_document(build_grouped_null_document(**kwargs)) == dump_document(
        build_grouped_null_document(**kwargs)
    )


def test_grouped_null_document_rejects_rows_from_a_different_seed():
    contexts, targets = _fixture()
    null_rows = apply_grouped_shuffle(contexts, targets, seed=11)
    with pytest.raises(GroupedNullError, match="records seed|assigns"):
        build_grouped_null_document(
            contexts=contexts,
            trajectory_targets=targets,
            null_rows=null_rows,
            seed=SEED,
            run_id="synthetic-null-v0-1",
        )


def test_validator_rejects_a_reused_donor():
    contexts, targets = _fixture()
    null_rows = apply_grouped_shuffle(contexts, targets, SEED)
    document = build_grouped_null_document(
        contexts=contexts,
        trajectory_targets=targets,
        null_rows=null_rows,
        seed=SEED,
        run_id="synthetic-null-v0-1",
    )
    tampered = dict(document)
    assignments = [dict(entry) for entry in document["donor_assignments"]]
    assignments[1]["donor_trajectory_id"] = assignments[0]["donor_trajectory_id"]
    tampered["donor_assignments"] = tuple(assignments)
    with pytest.raises(GroupedNullError, match="donor trajectory is reused"):
        validate_grouped_null_document(tampered)


def test_validator_rejects_a_substituted_resampling_unit():
    contexts, targets = _fixture()
    null_rows = apply_grouped_shuffle(contexts, targets, SEED)
    document = dict(
        build_grouped_null_document(
            contexts=contexts,
            trajectory_targets=targets,
            null_rows=null_rows,
            seed=SEED,
            run_id="synthetic-null-v0-1",
        )
    )
    document["resampling_unit"] = "per_row_bootstrap"
    with pytest.raises(GroupedNullError, match="frozen"):
        validate_grouped_null_document(document)


# --------------------------------------------------------------------------
# Paired comparisons
# --------------------------------------------------------------------------


def test_paired_rows_cover_the_exact_requested_row_set():
    contexts, _ = _fixture()
    rows_a = _method_rows(contexts, "last_seen")
    rows_b = _method_rows(contexts, "constant_velocity")
    requested = _requested_keys(contexts)

    paired = build_paired_rows(
        rows_a=rows_a,
        rows_b=rows_b,
        method_a="last_seen",
        method_b="constant_velocity",
        requested_keys=requested,
    )
    assert len(paired) == len(requested)
    assert all(row.scored for row in paired)


def test_a_row_present_on_only_one_side_is_unscored_not_dropped():
    contexts, _ = _fixture()
    rows_a = _method_rows(contexts, "last_seen")
    rows_b = _method_rows(contexts, "constant_velocity")[:-2]  # two rows missing
    requested = _requested_keys(contexts)

    paired = build_paired_rows(
        rows_a=rows_a,
        rows_b=rows_b,
        method_a="last_seen",
        method_b="constant_velocity",
        requested_keys=requested,
    )
    assert len(paired) == len(requested)
    unscored = [row for row in paired if not row.scored]
    assert len(unscored) == 2
    for row in unscored:
        assert row.status_b == "missing"
        assert row.prediction_b is None  # never 0.0
        assert row.unscored_reason


def test_non_applicable_side_preserves_its_reason():
    contexts, _ = _fixture()
    rows_a = _method_rows(contexts, "last_seen")
    rows_b = _method_rows(
        contexts, "visible_history_q", applicable=False, reason="no spread for visible row"
    )
    paired = build_paired_rows(
        rows_a=rows_a,
        rows_b=rows_b,
        method_a="last_seen",
        method_b="visible_history_q",
        requested_keys=_requested_keys(contexts),
    )
    assert all(not row.scored for row in paired)
    assert all(row.reason_b == "no spread for visible row" for row in paired)


def test_paired_document_validates_and_records_frozen_identities():
    contexts, _ = _fixture()
    paired = build_paired_rows(
        rows_a=_method_rows(contexts, "last_seen"),
        rows_b=_method_rows(contexts, "grouped_shuffled"),
        method_a="last_seen",
        method_b="grouped_shuffled",
        requested_keys=_requested_keys(contexts),
    )
    document = build_paired_comparison_document(
        paired_rows=paired,
        objective="U1",
        run_id="synthetic-paired-v0-1",
        metric_id="layout_macro_paired_loss_improvement",
    )
    validate_paired_comparison_document(document)
    assert document["schema_id"] == PAIRED_COMPARISONS_SCHEMA_ID
    assert tuple(document["row_level_pairing_keys"]) == FROZEN_ROW_LEVEL_PAIRING_KEYS
    assert document["resampling_unit"] == FROZEN_RESAMPLING_UNIT
    assert document["loss_identity"] == "squared_error_in_blocks"
    assert document["comparison_class_a"] == "memory_heuristic"
    assert document["comparison_class_b"] == "chance_floor"
    assert document["sample_unit"] == "whole_trajectory"


def test_paired_document_is_deterministic_and_order_independent():
    contexts, _ = _fixture()
    rows_a = _method_rows(contexts, "last_seen")
    rows_b = _method_rows(contexts, "grouped_shuffled")
    requested = _requested_keys(contexts)

    def build(order_a, order_b, keys):
        paired = build_paired_rows(
            rows_a=order_a,
            rows_b=order_b,
            method_a="last_seen",
            method_b="grouped_shuffled",
            requested_keys=keys,
        )
        return dump_document(
            build_paired_comparison_document(
                paired_rows=paired,
                objective="U1",
                run_id="synthetic-paired-v0-1",
                metric_id="layout_macro_paired_loss_improvement",
            )
        )

    assert build(rows_a, rows_b, requested) == build(
        list(reversed(rows_a)), list(reversed(rows_b)), list(reversed(requested))
    )


def test_mixing_mu_and_log_sigma_in_one_document_is_rejected():
    contexts, _ = _fixture()
    rows_a = _method_rows(contexts, "last_seen")
    rows_b = _method_rows(contexts, "grouped_shuffled")
    mu_pairs = build_paired_rows(
        rows_a=rows_a,
        rows_b=rows_b,
        method_a="last_seen",
        method_b="grouped_shuffled",
        requested_keys=_requested_keys(contexts),
    )
    log_sigma_rows_a = [
        make_baseline_row(
            ctx,
            baseline_name="last_seen",
            target_name="log_sigma_oracle",
            prediction=1.0,
            applicable=True,
        )
        for ctx in contexts
    ]
    log_sigma_rows_b = [
        make_baseline_row(
            ctx,
            baseline_name="grouped_shuffled",
            target_name="log_sigma_oracle",
            prediction=1.0,
            applicable=True,
        )
        for ctx in contexts
    ]
    log_sigma_pairs = build_paired_rows(
        rows_a=log_sigma_rows_a,
        rows_b=log_sigma_rows_b,
        method_a="last_seen",
        method_b="grouped_shuffled",
        requested_keys=_requested_keys(contexts, "log_sigma_oracle"),
    )
    with pytest.raises(GroupedNullError, match="one loss identity"):
        build_paired_comparison_document(
            paired_rows=mu_pairs + log_sigma_pairs,
            objective="U1",
            run_id="synthetic-paired-v0-1",
            metric_id="layout_macro_paired_loss_improvement",
        )


def test_duplicate_prediction_rows_are_rejected():
    contexts, _ = _fixture()
    rows_a = _method_rows(contexts, "last_seen")
    with pytest.raises(GroupedNullError, match="duplicate prediction row"):
        build_paired_rows(
            rows_a=rows_a + [rows_a[0]],
            rows_b=_method_rows(contexts, "grouped_shuffled"),
            method_a="last_seen",
            method_b="grouped_shuffled",
            requested_keys=_requested_keys(contexts),
        )


def test_foreign_method_rows_are_rejected():
    contexts, _ = _fixture()
    rows_a = _method_rows(contexts, "last_seen") + _method_rows(contexts[:1], "raw_pixel")
    with pytest.raises(GroupedNullError, match="foreign methods"):
        build_paired_rows(
            rows_a=rows_a,
            rows_b=_method_rows(contexts, "grouped_shuffled"),
            method_a="last_seen",
            method_b="grouped_shuffled",
            requested_keys=_requested_keys(contexts),
        )


def test_duplicate_requested_pairing_key_is_rejected():
    contexts, _ = _fixture()
    requested = _requested_keys(contexts)
    with pytest.raises(GroupedNullError, match="duplicate requested pairing key"):
        build_paired_rows(
            rows_a=_method_rows(contexts, "last_seen"),
            rows_b=_method_rows(contexts, "grouped_shuffled"),
            method_a="last_seen",
            method_b="grouped_shuffled",
            requested_keys=requested + requested[:1],
        )


def test_validator_rejects_a_number_smuggled_into_a_non_applicable_side():
    contexts, _ = _fixture()
    paired = build_paired_rows(
        rows_a=_method_rows(contexts, "last_seen"),
        rows_b=_method_rows(contexts, "visible_history_q", applicable=False),
        method_a="last_seen",
        method_b="visible_history_q",
        requested_keys=_requested_keys(contexts),
    )
    document = build_paired_comparison_document(
        paired_rows=paired,
        objective="U2",
        run_id="synthetic-paired-v0-1",
        metric_id="layout_macro_paired_loss_improvement",
    )
    tampered = dict(document)
    rows = [dict(row) for row in document["rows"]]
    rows[0]["prediction_b"] = 0.0  # the exact NA-as-zero failure mode
    tampered["rows"] = tuple(rows)
    with pytest.raises(GroupedNullError, match="NA is never a number"):
        validate_paired_comparison_document(tampered)


def test_validator_rejects_a_mismatched_scored_flag():
    contexts, _ = _fixture()
    paired = build_paired_rows(
        rows_a=_method_rows(contexts, "last_seen"),
        rows_b=_method_rows(contexts, "grouped_shuffled"),
        method_a="last_seen",
        method_b="grouped_shuffled",
        requested_keys=_requested_keys(contexts),
    )
    document = build_paired_comparison_document(
        paired_rows=paired,
        objective="U1",
        run_id="synthetic-paired-v0-1",
        metric_id="layout_macro_paired_loss_improvement",
    )
    tampered = dict(document)
    rows = [dict(row) for row in document["rows"]]
    rows[0]["scored"] = False
    rows[0]["unscored_reason"] = "looks unscored but both sides are available"
    tampered["rows"] = tuple(rows)
    # Keep the summary counts consistent with the tampered rows, so the
    # per-row consistency check is what fires rather than the tally check.
    tampered["scored_pair_count"] = document["scored_pair_count"] - 1
    tampered["unscored_pair_count"] = document["unscored_pair_count"] + 1
    with pytest.raises(GroupedNullError, match="disagrees with its own scored flag"):
        validate_paired_comparison_document(tampered)


def test_synthetic_evidence_is_labeled_and_real_is_explicit():
    contexts, _ = _fixture()
    paired = build_paired_rows(
        rows_a=_method_rows(contexts, "last_seen"),
        rows_b=_method_rows(contexts, "grouped_shuffled"),
        method_a="last_seen",
        method_b="grouped_shuffled",
        requested_keys=_requested_keys(contexts),
    )
    document = build_paired_comparison_document(
        paired_rows=paired,
        objective="U1",
        run_id="synthetic-paired-v0-1",
        metric_id="layout_macro_paired_loss_improvement",
    )
    assert document["evidence_kind"] == "synthetic"
    with pytest.raises(GroupedNullError, match="must be 'real' or 'synthetic'"):
        build_paired_comparison_document(
            paired_rows=paired,
            objective="U1",
            run_id="synthetic-paired-v0-1",
            metric_id="layout_macro_paired_loss_improvement",
            evidence_kind="probably_real",
        )
