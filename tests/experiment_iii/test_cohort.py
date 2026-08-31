"""I02 — the materialized cohort (A.1–A.6, A.19, D.31).

These run against the frozen artifacts in ``docs/experiment_iii/cohort/``. Where a
property is cheap to re-derive it is re-derived from the recorded seed rather than
read back from the manifest, so the manifest is checked rather than trusted.
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

import numpy as np
import pytest

from mineocclude.experiment_iii.authority import (
    BETWEEN_IDENTITY_DIVERSITY_RMS_BLOCKS,
    CANDIDATE_INDEX_BOUND_PER_DIRECTION,
    DT_SECONDS,
    FOLD_DIRECTION_COUNTS,
    FRAMES_PER_CAPTURE,
    INNER_ROTATIONS,
    LEFT_TO_RIGHT_COUNT,
    MINIMUM_TARGET_SD_BLOCKS,
    MOTION_NOISE_Q,
    OUTER_FOLDS,
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_IDS,
    REPOSITORY_ROOT,
    RIGHT_TO_LEFT_COUNT,
    SPEED_BLOCKS_PER_SECOND,
    canonical_sha256,
)
from mineocclude.experiment_iii.cohort import (
    candidate_at,
    generate_path,
    noise_sha256,
    path_sha256,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.fir import FIRST_FULLY_RESOLVED_TICK, fir_labels
from mineocclude.experiment_iii.folds import inner_rotation_assignment
from mineocclude.experiment_iii.schema import read_jsonl

COHORT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "cohort"

# The materialized cohort is a REQUIRED A1 artifact (authority 2.7), and group A
# must have zero skips (test plan section 0, rule 2). A missing cohort is
# therefore a hard failure here, never a skip: skipping would let ~30 named
# group-A checks vanish from an A2 run while the receipt still read "0 failures".
if not (COHORT / "production_identity_manifest.jsonl").is_file():  # pragma: no cover
    raise RuntimeError(
        "COHORT_MATRIX_INCONSISTENT: the materialized cohort is a required A1 "
        "artifact and is absent; run scripts/experiment_iii/build_cohort.py. "
        "Group A may not skip."
    )


@pytest.fixture(scope="module")
def production():
    return read_jsonl(COHORT / "production_identity_manifest.jsonl")


@pytest.fixture(scope="module")
def pilots():
    return read_jsonl(COHORT / "pilot_identity_manifest.jsonl")


@pytest.fixture(scope="module")
def folds():
    return json.loads((COHORT / "folds.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def all_q_receipt():
    return json.loads(
        (COHORT / "cohort_all_q_qualification_receipt.json").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def qualification_receipt():
    return json.loads(
        (COHORT / "cohort_qualification_receipt.json").read_text(encoding="utf-8")
    )


# --------------------------------------------------------------------------
# A.1 / A.3 — deterministic generation, re-derived from the recorded seed
# --------------------------------------------------------------------------

def test_cohort_composition(production, pilots):
    assert len(production) == 25
    assert [row["identity"] for row in production] == list(PRODUCTION_IDENTITY_IDS)
    assert [row["identity"] for row in pilots] == list(PILOT_IDENTITY_IDS)
    directions = [row["direction"] for row in production]
    assert directions.count("LEFT_TO_RIGHT") == LEFT_TO_RIGHT_COUNT == 13
    assert directions.count("RIGHT_TO_LEFT") == RIGHT_TO_LEFT_COUNT == 12


def test_every_identity_reproduces_from_its_recorded_seed(production):
    for row in production:
        positions, noise = generate_path(
            row["seed"],
            row["motion_noise_q"],
            direction=row["direction"],
            start_world_x=row["start_world_x"],
            speed=row["speed_blocks_per_second"],
            frames=row["frames"],
        )
        assert path_sha256(positions) == row["path_sha256"], row["identity"]
        assert noise_sha256(noise) == row["noise_schedule_sha256"], row["identity"]
        labels = fir_labels(
            [float(value) for value in positions],
            row["target_model_frame_indices"],
            row["direction"],
        )
        assert labels == row["expected_causal_fir_target_world_x_blocks"]


def test_candidate_stream_is_deterministic(production):
    for row in production:
        candidate = candidate_at(row["direction"], row["candidate_index"])
        assert candidate.seed == row["seed"]
        assert candidate.start_world_x == row["start_world_x"]
        assert candidate.noise_seed == row["seed"]


def test_spec_hashes_are_self_consistent(production, pilots):
    for row in production + pilots:
        body = dict(row)
        claimed = body.pop("spec_hash")
        assert canonical_sha256(body) == claimed, row["identity"]


# --------------------------------------------------------------------------
# A.4 — speed / q / dt
# --------------------------------------------------------------------------

def test_motion_identity_is_frozen(production, pilots):
    for row in production + pilots:
        assert row["speed_blocks_per_second"] == SPEED_BLOCKS_PER_SECOND == 2.0
        assert row["motion_noise_q"] == MOTION_NOISE_Q == 0.05
        assert row["dt_seconds"] == DT_SECONDS == 0.05
        assert row["frames"] == FRAMES_PER_CAPTURE == 180
        assert row["speed_blocks_per_second"] != 1.5


# --------------------------------------------------------------------------
# A.5 — fold partition and inner rotations
# --------------------------------------------------------------------------

def test_outer_folds_are_five_of_five_and_direction_balanced(folds):
    assert folds["outer_folds"] == OUTER_FOLDS == 5
    counts = []
    seen: set[str] = set()
    for fold in folds["folds"]:
        held = fold["held_out_identities"]
        assert len(held) == 5
        assert not (seen & set(held)), "outer folds must be identity-disjoint"
        seen |= set(held)
        counts.append(
            (
                fold["direction_counts"]["LEFT_TO_RIGHT"],
                fold["direction_counts"]["RIGHT_TO_LEFT"],
            )
        )
    assert seen == set(PRODUCTION_IDENTITY_IDS)
    assert counts == [tuple(pair) for pair in FOLD_DIRECTION_COUNTS]


def test_four_inner_rotations_per_outer_fold(folds):
    for fold in folds["folds"]:
        rotations = fold["inner_rotations"]
        assert sorted(rotations) == [str(k) for k in range(INNER_ROTATIONS)]
        sizes = sorted(len(members) for members in rotations.values())
        assert sizes == [5, 5, 5, 5], "20 training identities into 4 rotations"
        members = [name for group in rotations.values() for name in group]
        assert sorted(members) == sorted(fold["training_identities"])


def test_inner_rotation_is_deterministic_and_outcome_independent(folds, production):
    directions = {row["identity"]: row["direction"] for row in production}
    for fold in folds["folds"]:
        recomputed = inner_rotation_assignment(
            fold["training_identities"], directions, fold["outer_fold"]
        )
        stored = {
            identity: int(rotation)
            for rotation, members in fold["inner_rotations"].items()
            for identity in members
        }
        assert recomputed == stored, fold["outer_fold"]


def test_no_identity_is_in_its_own_training_set(folds):
    for fold in folds["folds"]:
        assert not set(fold["held_out_identities"]) & set(fold["training_identities"])


def test_legacy_five_inner_fold_shape_is_not_used(folds):
    for fold in folds["folds"]:
        assert len(fold["inner_rotations"]) == 4
        assert len(fold["inner_rotations"]) != 5


# --------------------------------------------------------------------------
# A.6 — within-identity target variance, and A.7's row/label shape
# --------------------------------------------------------------------------

def test_within_identity_target_sd_gate(production):
    for row in production:
        labels = np.asarray(row["expected_causal_fir_target_world_x_blocks"])
        assert len(labels) == 19
        assert len(set(labels.tolist())) > 1, row["identity"]
        sd = float(np.std(labels, ddof=0))
        assert sd >= MINIMUM_TARGET_SD_BLOCKS, (row["identity"], sd)
        assert sd == pytest.approx(row["expected_target_sd_blocks"], abs=1e-12)


def test_target_rows_are_nineteen_consecutive_and_fully_resolved(production):
    for row in production:
        indices = row["target_model_frame_indices"]
        assert len(indices) == 19
        assert indices == list(range(indices[0], indices[0] + 19))
        assert indices[0] >= FIRST_FULLY_RESOLVED_TICK
        assert indices[-1] < row["frames"]


def test_between_identity_diversity_gate_holds_on_the_cohort(production):
    for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
        vectors = [
            np.asarray(row["expected_causal_fir_target_world_x_blocks"])
            for row in production
            if row["direction"] == direction
        ]
        worst = min(
            math.sqrt(float(np.mean((a - b) ** 2)))
            for a, b in itertools.combinations(vectors, 2)
        )
        assert worst >= BETWEEN_IDENTITY_DIVERSITY_RMS_BLOCKS, (direction, worst)


# --------------------------------------------------------------------------
# A.19 — seed uniqueness and historical exclusion
# --------------------------------------------------------------------------

def test_seeds_are_unique_within_experiment_iii(production, pilots):
    seeds = [row["seed"] for row in production + pilots]
    assert len(set(seeds)) == len(seeds) == 27


def test_no_cohort_seed_appears_in_the_historical_exclusion_set(production, pilots):
    exclusion = json.loads(
        (COHORT / "historical_seed_exclusion_set.json").read_text(encoding="utf-8")
    )
    excluded = set(exclusion["excluded_seeds"])
    assert exclusion["excluded_seed_count"] > 0
    assert exclusion["exclusion_set_sha256"]
    assert not {row["seed"] for row in production + pilots} & excluded


# --------------------------------------------------------------------------
# Pilots are permanently excluded (authority 2.1)
# --------------------------------------------------------------------------

def test_pilots_are_excluded_from_every_production_structure(pilots, folds, production):
    pilot_ids = {row["identity"] for row in pilots}
    assert pilot_ids == set(PILOT_IDENTITY_IDS)
    for row in pilots:
        assert row["confirmatory_membership"] is False
        assert row["outer_fold"] is None
        assert row["priority_rank"] is None
    assert not pilot_ids & {row["identity"] for row in production}
    for fold in folds["folds"]:
        assert not pilot_ids & set(fold["held_out_identities"])
        assert not pilot_ids & set(fold["training_identities"])


def test_episode_ids_are_in_the_experiment_iii_block(production, pilots):
    for row in production:
        assert row["episode_id"] == 86001 + row["priority_rank"]
        assert 86001 <= row["episode_id"] <= 86999
    assert [row["episode_id"] for row in pilots] == [86901, 86902]


# --------------------------------------------------------------------------
# D.31 — gate-12 ordering and cohort-freeze precedence
# --------------------------------------------------------------------------

def test_gate_12_evaluated_before_materialization_and_freeze(all_q_receipt):
    assert all_q_receipt["evaluated_before_materialization"] is True
    assert all_q_receipt["evaluated_before_freeze"] is True
    assert all_q_receipt["gate_index"] == 12
    assert all_q_receipt["implementing_primitive_task"] == "IB02"
    assert all_q_receipt["regression_guard_task"] == "IB03"
    assert "BEFORE the production" in all_q_receipt["assertion"]


def test_every_admitted_identity_passed_gate_12(all_q_receipt, production):
    admitted = [row for row in all_q_receipt["per_candidate"] if row["admitted"]]
    assert len(admitted) == 25
    assert all(row["passed"] for row in admitted)
    assert {row["identity"] for row in admitted} == set(PRODUCTION_IDENTITY_IDS)
    recorded = {row["identity"]: row["seed"] for row in admitted}
    assert recorded == {row["identity"]: row["seed"] for row in production}


def test_diagnostic_q_is_recorded_but_never_binding(all_q_receipt):
    assert all_q_receipt["diagnostic_q"] == 0.15
    assert all_q_receipt["diagnostic_q_is_binding"] is False
    assert all_q_receipt["diagnostic_q_failure_rejects_candidate"] is False
    assert all_q_receipt["diagnostic_q_failure_regenerates_cohort"] is False
    assert all_q_receipt["binding_q_set"] == [0.0125, 0.05, 0.2]


def test_i02_fails_closed_without_the_ib02_ib03_primitive(monkeypatch):
    import mineocclude.experiment_iii.cohort_build as cohort_build

    def broken(*_args, **_kwargs):
        raise ExperimentIIIError("B_Q_PAIRING_MISMATCH", "regression fixture is red")

    monkeypatch.setattr(cohort_build, "generate_path", broken, raising=False)
    monkeypatch.setattr(
        "mineocclude.experiment_iii.cohort.generate_path", broken
    )
    with pytest.raises(ExperimentIIIError) as caught:
        cohort_build.assert_all_q_primitive_available()
    assert caught.value.blocker == "COHORT_ALL_Q_PRIMITIVE_MISSING"


def test_q_regression_a1_receipt_recorded_before_i02():
    receipt = json.loads(
        (COHORT / "q_regression_a1_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["recorded_before"] == "I02"
    assert receipt["result"] == "PASS"
    assert receipt["reference_unit"] == "a2x_t01_wall"
    assert receipt["observed_path_sha256"] == receipt["expected_path_sha256"]
    assert all(receipt["checks"].values())


# --------------------------------------------------------------------------
# Rejection logging is required evidence (authority 2.7)
# --------------------------------------------------------------------------

def test_every_rejection_logs_index_seed_and_first_failing_gate(qualification_receipt):
    assert qualification_receipt["gate_count"] == 12
    assert (
        qualification_receipt["candidate_index_bound_per_direction"]
        == CANDIDATE_INDEX_BOUND_PER_DIRECTION
        == 2000
    )
    rejections = qualification_receipt["rejections"]
    assert rejections, "rejection logging is required evidence, not a convenience"
    for rejection in rejections:
        assert isinstance(rejection["candidate_index"], int)
        assert isinstance(rejection["seed"], int)
        assert 1 <= rejection["first_failing_gate"] <= 12
        assert rejection["first_failing_gate_name"]


def test_admission_reads_no_scientific_outcome(qualification_receipt):
    assert qualification_receipt["admission_reads_rendered_frames"] is False
    assert qualification_receipt["admission_reads_activations"] is False
    assert qualification_receipt["admission_reads_outcomes"] is False
    assert (
        qualification_receipt["generation_order"]
        == "STRICTLY_ASCENDING_INDEX_PER_DIRECTION_LTR_THEN_RTL"
    )


def test_candidate_indices_are_strictly_ascending_per_direction(production):
    for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
        indices = [
            row["candidate_index"]
            for row in production
            if row["direction"] == direction
        ]
        assert indices == sorted(indices)
        assert len(set(indices)) == len(indices)
        assert max(indices) < CANDIDATE_INDEX_BOUND_PER_DIRECTION
