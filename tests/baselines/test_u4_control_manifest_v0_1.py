"""Tests for the pre-outcome U4 control manifest (Step 7.1).

Persons A and E generate and measure against the clip IDs and pair keys
this builder emits, so determinism and completeness are the headline
properties. The rest of the file is about the two ways a control matrix
stops being a control matrix: a row selected using an outcome, and a row
added after rollouts began.

Every fixture is synthetic; no real direction, event, or rollout is read.
"""

from __future__ import annotations

import json

import pytest

from mineocclude.baselines.u4_control_manifest_v0_1 import (
    FROZEN_HOOK_SITE,
    ControlManifestError,
    ControlType,
    DirectionRef,
    DoseSpec,
    HeldOutEvent,
    assert_no_post_rollout_addition,
    build_control_manifest,
    build_control_manifest_rows,
    build_person_d_to_a_and_e_handoff,
    compute_manifest_checksum,
    dump_control_manifest,
    expected_row_count,
    freeze_control_manifest,
    make_clip_id,
    make_pair_key,
    reconcile_planned_versus_available,
    validate_control_manifest,
)

SHA = "d" * 64

EVENTS = (
    HeldOutEvent("layout_00_ep9403:reveal:228", "layout_00_ep9403", "layout_00"),
    HeldOutEvent("layout_01_ep9405:reveal:210", "layout_01_ep9405", "layout_01"),
)
SEEDS = (11, 22)
DOSES = (
    DoseSpec("pos_1", 4.0, 4.0, False),
    DoseSpec("neg_1", -4.0, -4.0, False),
)
PRIMARY = DirectionRef("u4_primary", "v1", SHA)
RANDOMS = (DirectionRef("rand_a", "v1", "e" * 64, seed=101),)
ORTHOGONALS = (DirectionRef("orth_a", "v1", "f" * 64, seed=202),)

BUILD_KWARGS = dict(
    held_out_events=EVENTS,
    rollout_seeds=SEEDS,
    doses=DOSES,
    primary_direction=PRIMARY,
    random_directions=RANDOMS,
    orthogonal_directions=ORTHOGONALS,
    target_layer_idx=12,
    target_timestep_idx=7,
    wrong_layer_idx=3,
    wrong_timestep_idx=1,
)


def _rows():
    return build_control_manifest_rows(**BUILD_KWARGS)


def _manifest(**overrides):
    kwargs = dict(BUILD_KWARGS)
    kwargs.update(
        manifest_id="person-d-u4-control-manifest-synthetic",
        manifest_version="0.1.0",
        rows=_rows(),
        source_authorities={
            "person_b_direction_commit": "SYNTHETIC_NOT_REAL",
            "person_a_rollout_contract": "docs/contracts/rollout_registry_v1.md",
        },
    )
    kwargs.update(overrides)
    return build_control_manifest(**kwargs)


# --------------------------------------------------------------------------
# Completeness and determinism
# --------------------------------------------------------------------------


def test_row_count_matches_the_independently_stated_expectation():
    rows = _rows()
    expected = expected_row_count(
        event_count=len(EVENTS),
        seed_count=len(SEEDS),
        dose_count=len(DOSES),
        random_direction_count=len(RANDOMS),
        orthogonal_direction_count=len(ORTHOGONALS),
    )
    assert len(rows) == expected
    # 2 events x 2 seeds x (1 alpha-zero + 2 doses x (1 primary + 1 random
    # + 1 orthogonal + wrong-layer + wrong-timestep)) = 4 x (1 + 2 x 5) = 44
    assert expected == 44


def test_every_control_type_is_present_for_every_event_and_seed():
    rows = _rows()
    for event in EVENTS:
        for seed in SEEDS:
            present = {
                row.control_type
                for row in rows
                if row.event_id == event.event_id and row.rollout_seed == seed
            }
            assert present == {member.value for member in ControlType}


def test_clip_ids_are_unique_and_deterministic():
    first = [row.clip_id for row in _rows()]
    second = [row.clip_id for row in _rows()]
    assert first == second
    assert len(set(first)) == len(first)


def test_manifest_serialization_is_byte_stable():
    assert dump_control_manifest(_manifest()) == dump_control_manifest(_manifest())


def test_clip_id_and_pair_key_are_built_from_identity_not_position():
    clip_id = make_clip_id(
        event_id="e1",
        rollout_seed=5,
        control_type="alpha_zero",
        dose_id=None,
        target_layer_idx=12,
        target_timestep_idx=7,
    )
    assert clip_id == "e1|seed5|alpha_zero|dosenone|L12|T7"
    assert make_pair_key(event_id="e1", rollout_seed=5, dose_id="pos_1") == (
        "e1|seed5|dosepos_1"
    )


def test_every_pair_key_resolves_to_exactly_one_alpha_zero_baseline():
    document = _manifest()
    validate_control_manifest(document)
    alpha_zero = [
        row
        for row in document["rows"]
        if row["control_type"] == ControlType.ALPHA_ZERO.value
    ]
    assert len(alpha_zero) == len(EVENTS) * len(SEEDS)


def test_manifest_validates_and_records_every_required_identity():
    document = _manifest()
    validate_control_manifest(document)
    required = {
        "clip_id",
        "pair_key",
        "control_type",
        "event_id",
        "trajectory_id",
        "layout_id",
        "rollout_seed",
        "alpha_requested",
        "alpha_applied",
        "cap_reduced",
        "dose_id",
        "direction_id",
        "direction_version",
        "direction_sha256",
        "direction_seed",
        "target_layer_idx",
        "target_timestep_idx",
        "hook_site",
        "owner_role",
        "status",
    }
    for row in document["rows"]:
        assert required <= set(row)
        assert row["hook_site"] == FROZEN_HOOK_SITE
    assert document["expected_clip_count"] == document["planned_clip_count"]


# --------------------------------------------------------------------------
# Pre-outcome guarantees
# --------------------------------------------------------------------------


def test_an_outcome_field_anywhere_in_the_manifest_is_rejected():
    document = json.loads(json.dumps(_manifest(), default=list))
    document["rows"][0]["masked_ssim"] = 0.91
    document["manifest_checksum"] = compute_manifest_checksum(document)
    with pytest.raises(ControlManifestError, match="outcome-derived fields"):
        validate_control_manifest(document)


def test_a_nested_outcome_field_is_also_rejected():
    document = json.loads(json.dumps(_manifest(), default=list))
    document["source_authorities"]["p_value"] = 0.03
    document["manifest_checksum"] = compute_manifest_checksum(document)
    with pytest.raises(ControlManifestError, match="outcome-derived fields"):
        validate_control_manifest(document)


def test_declaring_outcome_derived_selection_is_rejected():
    document = dict(_manifest())
    document["outcome_derived_selection"] = True
    document["manifest_checksum"] = compute_manifest_checksum(document)
    with pytest.raises(ControlManifestError, match="not a control"):
        validate_control_manifest(document)


# --------------------------------------------------------------------------
# Freezing and post-rollout addition
# --------------------------------------------------------------------------


def test_freezing_stamps_a_checksum_and_validates():
    frozen = freeze_control_manifest(_manifest())
    assert frozen["status"] == "frozen"
    validate_control_manifest(frozen)
    assert frozen["manifest_checksum"] == compute_manifest_checksum(frozen)


def test_a_manifest_with_generated_rows_cannot_be_frozen():
    document = json.loads(json.dumps(_manifest(), default=list))
    document["rows"][0]["status"] = "generated"
    document["manifest_checksum"] = compute_manifest_checksum(document)
    with pytest.raises(ControlManifestError, match="must be frozen before any rollout"):
        freeze_control_manifest(document)


def test_status_may_advance_after_freezing_but_identity_may_not():
    frozen = freeze_control_manifest(_manifest())
    executed = json.loads(json.dumps(frozen, default=list))
    for row in executed["rows"]:
        row["status"] = "generated"
    assert_no_post_rollout_addition(frozen, executed)  # status-only change is fine

    relabelled = json.loads(json.dumps(frozen, default=list))
    relabelled["rows"][0]["target_layer_idx"] = 5
    with pytest.raises(ControlManifestError, match="changed after freezing"):
        assert_no_post_rollout_addition(frozen, relabelled)


def test_a_control_added_after_freezing_is_rejected():
    frozen = freeze_control_manifest(_manifest())
    grown = json.loads(json.dumps(frozen, default=list))
    extra = dict(grown["rows"][0])
    extra["clip_id"] = extra["clip_id"] + "|late_addition"
    grown["rows"].append(extra)
    with pytest.raises(ControlManifestError, match="added after the manifest was frozen"):
        assert_no_post_rollout_addition(frozen, grown)


def test_a_control_removed_after_freezing_is_rejected():
    frozen = freeze_control_manifest(_manifest())
    shrunk = json.loads(json.dumps(frozen, default=list))
    shrunk["rows"] = shrunk["rows"][:-1]
    with pytest.raises(ControlManifestError, match="missing from the candidate"):
        assert_no_post_rollout_addition(frozen, shrunk)


# --------------------------------------------------------------------------
# Structural rejections
# --------------------------------------------------------------------------


def test_wrong_layer_control_must_differ_from_the_primary_layer():
    kwargs = dict(BUILD_KWARGS)
    kwargs["wrong_layer_idx"] = kwargs["target_layer_idx"]
    with pytest.raises(ControlManifestError, match="different layer"):
        build_control_manifest_rows(**kwargs)


def test_wrong_timestep_control_must_differ_from_the_primary_timestep():
    kwargs = dict(BUILD_KWARGS)
    kwargs["wrong_timestep_idx"] = kwargs["target_timestep_idx"]
    with pytest.raises(ControlManifestError, match="different timestep"):
        build_control_manifest_rows(**kwargs)


def test_an_unseeded_random_direction_is_rejected():
    kwargs = dict(BUILD_KWARGS)
    kwargs["random_directions"] = (DirectionRef("rand_a", "v1", "e" * 64),)
    with pytest.raises(ControlManifestError, match="has no seed"):
        build_control_manifest_rows(**kwargs)


def test_missing_orthogonal_controls_are_rejected_when_the_contract_requires_them():
    kwargs = dict(BUILD_KWARGS)
    kwargs["orthogonal_directions"] = ()
    with pytest.raises(ControlManifestError, match="requires orthogonal-direction"):
        build_control_manifest_rows(**kwargs)
    # Explicitly opting out is allowed and produces a smaller matrix.
    kwargs["require_orthogonal_controls"] = False
    assert build_control_manifest_rows(**kwargs)


def test_a_dose_reversing_sign_is_rejected():
    with pytest.raises(ControlManifestError, match="reverses sign"):
        DoseSpec("bad", 6.0, -5.0, True)


def test_a_zero_alpha_primary_dose_is_rejected():
    with pytest.raises(ControlManifestError, match="alpha_zero control"):
        DoseSpec("bad", 0.0, 0.0, False)


def test_an_unflagged_alpha_change_is_rejected():
    with pytest.raises(ControlManifestError, match="without the cap_reduced flag"):
        DoseSpec("bad", 6.0, 5.0, False)


def test_a_standardized_space_direction_is_rejected():
    with pytest.raises(ControlManifestError, match="raw_activation space"):
        DirectionRef("d", "v1", SHA, space="standardized")


def test_an_out_of_range_layer_is_rejected():
    kwargs = dict(BUILD_KWARGS)
    kwargs["target_layer_idx"] = 99
    with pytest.raises(ControlManifestError, match="outside the frozen range"):
        build_control_manifest_rows(**kwargs)


def test_an_omitted_row_makes_the_manifest_incomplete():
    document = json.loads(json.dumps(_manifest(), default=list))
    document["rows"] = document["rows"][:-1]
    document["planned_clip_count"] = len(document["rows"])
    document["manifest_checksum"] = compute_manifest_checksum(document)
    with pytest.raises(ControlManifestError, match="omitted or extra row"):
        validate_control_manifest(document)


def test_a_tampered_manifest_fails_its_own_checksum():
    document = json.loads(json.dumps(_manifest(), default=list))
    document["target_layer_idx"] = 13
    with pytest.raises(ControlManifestError, match="checksum does not match"):
        validate_control_manifest(document)


# --------------------------------------------------------------------------
# Reconciliation and handoff
# --------------------------------------------------------------------------


def test_reconciliation_reports_complete_coverage():
    document = _manifest()
    report = reconcile_planned_versus_available(
        document, [row["clip_id"] for row in document["rows"]]
    )
    assert report["complete"] is True
    assert report["planned_count"] == report["available_count"]


def test_reconciliation_reports_missing_duplicated_and_unexpected_clips():
    document = _manifest()
    clip_ids = [row["clip_id"] for row in document["rows"]]
    available = clip_ids[:-1] + [clip_ids[0], "an_unplanned_clip"]
    report = reconcile_planned_versus_available(document, available)
    assert report["complete"] is False
    assert report["missing_clip_ids"] == (clip_ids[-1],)
    assert report["duplicated_clip_ids"] == (clip_ids[0],)
    assert report["unexpected_clip_ids"] == ("an_unplanned_clip",)


def test_handoff_gives_a_and_e_join_keys_and_obligations():
    frozen = freeze_control_manifest(_manifest())
    handoff = build_person_d_to_a_and_e_handoff(
        frozen, manifest_path="docs/status/x/control_manifest.json", manifest_sha256=SHA
    )
    assert handoff["consumer_roles"] == ("person_a", "person_e")
    assert handoff["join_keys"] == ("clip_id", "pair_key")
    assert handoff["clip_count"] == len(frozen["rows"])
    assert set(handoff["clip_ids"]) == {row["clip_id"] for row in frozen["rows"]}
    assert handoff["post_rollout_addition_permitted"] is False
    assert "filename" in handoff["join_rule"].lower()


def test_synthetic_manifest_is_labeled_and_never_implicitly_real():
    document = _manifest()
    assert document["evidence_kind"] == "synthetic"
    real = _manifest(evidence_kind="real")
    assert real["evidence_kind"] == "real"
    with pytest.raises(ControlManifestError, match="must be 'real' or 'synthetic'"):
        _manifest(evidence_kind="probably_real")
