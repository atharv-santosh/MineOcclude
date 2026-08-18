"""Terminal verification of fold discipline, bootstrap, self-grade, and metadata.

Five findings, all of the same shape: the Stage-2 terminal *recorded* a fact and
never established it, so a decision that looked complete could rest on evidence
nothing had checked.

B001 -- fold and model-selection discipline were unverified
    Evidence carried ``training_trajectory_ids``, ``test_trajectory_ids``,
    ``selected_k`` and ``selected_alpha``, and the evaluator judged none of them.
    A terminal PASS could therefore have survived train == test == all 25
    identities, ``K = 999``, ``alpha = 1e-9``, one trajectory held out in every
    outer fold, or a training identity that does not exist. The honest
    implementation did none of those; the defect is that the terminal could not
    tell. Every one of those attacks is driven below and must BLOCK.

B004 -- bootstrap verification was tautological
    The evidence builder read ``bootstrap_configuration`` out of the decision
    authority and the evaluator compared it back to the same authority, proving
    only that the authority equals itself. The producing readout now records what
    it actually resampled under, evidence consumes that record, and the evaluator
    compares the two.

B005 -- the claim overstated the time baseline
    Under the frozen thresholds neither time-baseline gate can bind
    independently of the RMSE ceiling, so a PASS may not be described as having
    beaten a time or motion baseline. The gates themselves are unchanged, which
    is asserted here as strictly as the language is.

B007 -- the recorded self-grade was never compared
    ``readout_claimed_qualification_status`` could disagree with the re-derived
    status unchallenged.

B008 -- activation shape and episode identity were never verified
    ``[19, 336, 4096]`` or ``episode_id = null`` could reach a PASS.

Every case is fixture-driven. No scientific Stage-2 outcome exists, none is
read, and nothing here writes into an evidence directory or authorizes anything.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mineocclude.prospective.development_workflow import (
    EvidenceError, canonical_payload_sha256, load_json,
)
from mineocclude.prospective.fold_discipline import (
    FoldDisciplineError, expected_row_keys, row_key_digest,
    verify_selection_discipline,
)
from mineocclude.prospective.stage2_decision import BLOCKED, FAIL, PASS
from mineocclude.regime_a_first25_analysis import ALPHAS, K_GRID, inner_fold_assignment

from tests.prospective.test_stage2_terminal_authority import (  # noqa: F401
    AUTHORITY_PATH, DECISION_AUTHORITY_PATH, STAGE2_PATH, Campaign, HONEST_BOOTSTRAP,
    SELECTION_TAU_MAXIMUM, authority, campaign, decision_authority, real_manifest,
)

ROOT = Path(__file__).resolve().parents[2]


def mutate(campaign, stage, scene, fold, **changes):
    """Edit one outer fold's selection record in one readout receipt."""
    unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                if item["pipeline_stage"] == stage)
    entry = campaign.documents[unit["receipt_path"]]["scenes"][scene][
        "selection_by_outer_fold"][str(fold)]
    for key, value in changes.items():
        if value is _ABSENT:
            entry.pop(key, None)
        else:
            entry[key] = value
    return entry


class _Absent:
    def __repr__(self):
        return "<absent>"


_ABSENT = _Absent()


# ======================================================================
# B001 -- the defect, reproduced
# ======================================================================


class TestTheFoldDefectItself:
    def test_the_superseded_evidence_shape_carried_no_verifiable_fold_facts(self):
        """What the evidence used to record, and why it proved nothing.

        The three keys below are the whole of what a fold used to contribute.
        Given only these, no consumer can tell an honest fold from one that
        trained on its own test set: the lists could say anything and there was
        nothing to check them against.
        """
        superseded = {"selected_alpha", "training_trajectory_ids", "test_trajectory_ids"}
        required = {"inner_fold_assignment", "predicted_row_keys_sha256",
                    "predicted_row_count", "selection_training_tau_maximum"}
        assert not (superseded & required)
        with pytest.raises(FoldDisciplineError):
            verify_selection_discipline(
                {str(fold): {"selected_alpha": 1.0, "training_trajectory_ids": [],
                             "test_trajectory_ids": []} for fold in range(5)},
                kind="FULL", identity_outer_folds={"t01": 0}, identity_directions={"t01": "X"},
                rows_per_trajectory=19, outer_fold_count=5, k_grid=None, alpha_grid=[1.0],
                training_identities_required=20, inner_fold_count=5,
                identities_per_inner_fold=4, selection_training_tau_maximum=15,
                label="superseded")

    def test_an_honest_campaign_still_passes_every_new_check(self, campaign):
        decision = campaign.decide()
        assert decision["status"] == PASS
        assert decision["reasons"] == []


# ======================================================================
# B001 -- the adversarial cases the finding enumerates
# ======================================================================


class TestFoldLeakage:
    def test_train_equals_test_blocks(self, campaign):
        everything = sorted(item["trajectory_id"]
                            for item in campaign.manifest["trajectory_identities"])
        mutate(campaign, "best_k", "WALL", 0,
               training_trajectory_ids=everything, test_trajectory_ids=everything)
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "training and test overlap" in decision["reasons"][0]

    def test_a_single_leaked_identity_blocks(self, campaign):
        entry = mutate(campaign, "best_k", "WALL", 0)
        entry["training_trajectory_ids"] = sorted(
            set(entry["training_trajectory_ids"]) | {entry["test_trajectory_ids"][0]})
        assert campaign.decide()["status"] == BLOCKED

    def test_an_unknown_training_identity_blocks(self, campaign):
        entry = mutate(campaign, "best_k", "WALL", 1)
        entry["training_trajectory_ids"] = entry["training_trajectory_ids"][:-1] + ["a2y_t99"]
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "unknown trajectory identities" in decision["reasons"][0]

    def test_an_unknown_test_identity_blocks(self, campaign):
        mutate(campaign, "best_k", "WALL", 2, test_trajectory_ids=["a2y_t99"])
        assert campaign.decide()["status"] == BLOCKED

    def test_a_duplicated_held_out_identity_within_a_fold_blocks(self, campaign):
        entry = mutate(campaign, "best_k", "WALL", 3)
        entry["test_trajectory_ids"] = entry["test_trajectory_ids"] + [
            entry["test_trajectory_ids"][0]]
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "twice in one fold" in decision["reasons"][0]

    def test_the_same_trajectory_held_out_in_every_outer_fold_blocks(self, campaign):
        """The attack the finding names explicitly: one fold's test set, five times."""
        identities = campaign.manifest["trajectory_identities"]
        folds = {item["trajectory_id"]: item["outer_fold"] for item in identities}
        directions = {item["trajectory_id"]: item["direction"] for item in identities}
        borrowed = sorted(name for name, value in folds.items() if value == 0)
        for fold in range(5):
            training = sorted(set(folds) - set(borrowed))
            mutate(campaign, "best_k", "WALL", fold,
                   training_trajectory_ids=training, test_trajectory_ids=borrowed,
                   inner_fold_assignment={
                       name: int(value) for name, value in sorted(inner_fold_assignment(
                           training, {name: directions[name] for name in training}, fold
                       ).items())},
                   predicted_row_count=len(borrowed) * 19,
                   predicted_row_keys_sha256=row_key_digest(expected_row_keys(borrowed, 19)))
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "held-out identities are not the frozen outer fold" in decision["reasons"][0]

    def test_a_missing_held_out_identity_blocks(self, campaign):
        entry = mutate(campaign, "best_k", "WALL", 4)
        dropped = entry["test_trajectory_ids"][0]
        entry["test_trajectory_ids"] = entry["test_trajectory_ids"][1:]
        entry["training_trajectory_ids"] = sorted(entry["training_trajectory_ids"] + [dropped])
        assert campaign.decide()["status"] == BLOCKED

    def test_a_fold_that_does_not_partition_the_inventory_blocks(self, campaign):
        entry = mutate(campaign, "best_k", "WALL", 0)
        entry["training_trajectory_ids"] = entry["training_trajectory_ids"][:-1]
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "do not partition" in decision["reasons"][0] \
            or "training identities" in decision["reasons"][0]

    def test_a_missing_outer_fold_blocks(self, campaign):
        unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                    if item["pipeline_stage"] == "best_k")
        campaign.documents[unit["receipt_path"]]["scenes"]["WALL"][
            "selection_by_outer_fold"].pop("4")
        with pytest.raises(EvidenceError, match="all five outer folds"):
            campaign.evidence()


class TestModelSelectionGrids:
    @pytest.mark.parametrize("bad_k", [999, 0, -1, 3, 129, 2048])
    def test_a_k_outside_the_frozen_grid_blocks(self, campaign, bad_k):
        assert bad_k not in K_GRID
        mutate(campaign, "best_k", "WALL", 0, selected_k=bad_k,
               selected_tokens=list(range(max(bad_k, 0))))
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "selected K" in decision["reasons"][0]

    @pytest.mark.parametrize("bad_alpha", [1e-9, 0.0, 0.5, 1000.0, -1.0])
    def test_an_alpha_outside_the_frozen_grid_blocks(self, campaign, bad_alpha):
        assert bad_alpha not in ALPHAS
        mutate(campaign, "best_k", "WALL", 0, selected_alpha=bad_alpha)
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "selected alpha" in decision["reasons"][0]

    def test_every_frozen_k_and_alpha_is_accepted(self, campaign):
        for index, k in enumerate(K_GRID):
            mutate(campaign, "best_k", "WALL", index % 5, selected_k=k,
                   selected_tokens=list(range(k)), selected_alpha=ALPHAS[index % len(ALPHAS)])
        assert campaign.decide()["status"] == PASS

    def test_a_token_count_that_disagrees_with_k_blocks(self, campaign):
        mutate(campaign, "best_k", "WALL", 0, selected_k=16, selected_tokens=list(range(8)))
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "tokens were selected but K is" in decision["reasons"][0]

    def test_a_full_readout_may_not_report_a_selected_k(self, campaign):
        mutate(campaign, "full", "WALL", 0, selected_k=16)
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "FULL readout selects no token count" in decision["reasons"][0]

    def test_a_missing_selection_record_blocks(self, campaign):
        mutate(campaign, "best_k", "WALL", 0, selected_alpha=_ABSENT)
        assert campaign.decide()["status"] == BLOCKED


class TestInnerFoldDiscipline:
    def test_a_wrong_inner_fold_membership_blocks(self, campaign):
        entry = mutate(campaign, "best_k", "WALL", 0)
        rotated = {name: (value + 1) % 5
                   for name, value in entry["inner_fold_assignment"].items()}
        entry["inner_fold_assignment"] = rotated
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "not the frozen direction-stratified assignment" in decision["reasons"][0]

    def test_inner_folds_covering_a_test_identity_block(self, campaign):
        """The mechanical form of "outer-test rows entered model selection"."""
        entry = mutate(campaign, "best_k", "WALL", 0)
        inner = dict(entry["inner_fold_assignment"])
        inner.pop(sorted(inner)[0])
        inner[entry["test_trajectory_ids"][0]] = 0
        entry["inner_fold_assignment"] = inner
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "do not cover exactly the training identities" in decision["reasons"][0]

    def test_an_absent_inner_fold_assignment_is_refused_at_the_builder(self, campaign):
        mutate(campaign, "best_k", "WALL", 0, inner_fold_assignment=_ABSENT)
        with pytest.raises(EvidenceError, match="no inner-fold assignment"):
            campaign.evidence()

    @pytest.mark.parametrize("tau", [14, 16, 19, 1])
    def test_a_widened_selection_tau_scope_blocks(self, campaign, tau):
        mutate(campaign, "best_k", "WALL", 0, selection_training_tau_maximum=tau)
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "selection used tau maximum" in decision["reasons"][0]


class TestRowCoverage:
    def test_a_row_predicted_zero_times_blocks(self, campaign):
        entry = mutate(campaign, "best_k", "WALL", 0)
        short = expected_row_keys(entry["test_trajectory_ids"], 19)[:-1]
        entry["predicted_row_count"] = len(short)
        entry["predicted_row_keys_sha256"] = row_key_digest(short)
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "rows were predicted" in decision["reasons"][0]

    def test_a_row_predicted_twice_blocks(self, campaign):
        entry = mutate(campaign, "best_k", "WALL", 0)
        keys = expected_row_keys(entry["test_trajectory_ids"], 19)
        doubled = keys[:-1] + [keys[0]]
        assert len(doubled) == len(keys)
        entry["predicted_row_keys_sha256"] = row_key_digest(doubled)
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "not the frozen held-out row set" in decision["reasons"][0]

    def test_predicting_another_folds_rows_blocks(self, campaign):
        entry = mutate(campaign, "best_k", "WALL", 0)
        other = next(item["trajectory_id"] for item in campaign.manifest["trajectory_identities"]
                     if item["outer_fold"] == 1)
        entry["predicted_row_keys_sha256"] = row_key_digest(expected_row_keys([other], 19))
        entry["predicted_row_count"] = 19
        assert campaign.decide()["status"] == BLOCKED

    def test_an_absent_row_digest_is_refused_at_the_builder(self, campaign):
        mutate(campaign, "best_k", "WALL", 0, predicted_row_keys_sha256=_ABSENT)
        with pytest.raises(EvidenceError, match="no held-out row inventory digest"):
            campaign.evidence()

    def test_the_verified_coverage_is_the_complete_frozen_inventory(self, campaign):
        evidence = campaign.evidence()
        selection = evidence["readouts"]["best_k"]["scenes"]["WALL"]["selection_by_outer_fold"]
        assert sum(entry["predicted_row_count"] for entry in selection.values()) == 25 * 19
        held_out = [name for entry in selection.values()
                    for name in entry["test_trajectory_ids"]]
        assert len(held_out) == len(set(held_out)) == 25

    def test_row_key_digest_is_order_independent_but_multiplicity_sensitive(self):
        keys = expected_row_keys(["b", "a"], 3)
        assert row_key_digest(keys) == row_key_digest(list(reversed(keys)))
        assert row_key_digest(keys) != row_key_digest(keys + [keys[0]])


class TestEveryReadoutAndSceneIsVerified:
    @pytest.mark.parametrize("stage", ["best_k", "full"])
    @pytest.mark.parametrize("scene", ["WALL", "NO_WALL"])
    def test_leakage_anywhere_blocks(self, campaign, stage, scene):
        entry = mutate(campaign, stage, scene, 2)
        entry["training_trajectory_ids"] = sorted(
            set(entry["training_trajectory_ids"]) | set(entry["test_trajectory_ids"]))
        assert campaign.decide()["status"] == BLOCKED


# ======================================================================
# B001 -- the honest producer, driven for real
# ======================================================================


def _cuda_available():
    try:
        import torch
    except ImportError:
        return False
    return torch.cuda.is_available()


@pytest.mark.skipif(not _cuda_available(), reason="the readout kernels require CUDA")
def test_the_real_readout_functions_satisfy_the_new_verification(real_manifest,
                                                                 decision_authority):
    """The other half of B001: the honest implementation must still pass.

    Every other test here attacks the verifier. This one drives the REAL
    ``best_k_readout`` and ``full_readout`` over the frozen 25-identity /
    5-fold design with synthetic activations, routes their selections through the
    REAL evidence builder, and requires the REAL verifier to accept them -- so a
    verification that is merely strict, rather than correct, fails here.

    The activations are noise plus a weak injected signal. No scientific outcome
    is produced or read: only the fold structure is asserted.
    """
    import sys

    import numpy as np

    sys.path.insert(0, str(ROOT / "scripts/regime_a_prime_qualification_v0_1"))
    from p2e_analyze import best_k_readout, full_readout

    from mineocclude.prospective.stage2_evidence import _selection

    identities = real_manifest["trajectory_identities"]
    folds = {item["trajectory_id"]: item["outer_fold"] for item in identities}
    directions = {item["trajectory_id"]: item["direction"] for item in identities}
    order = [item["trajectory_id"] for item in identities]
    procedure = decision_authority["readout_procedure"]
    inner = procedure["inner_fold_rule"]
    taus, tokens, hidden = 19, 136, 32

    generator = np.random.default_rng(7)
    rows, blocks = [], []
    for identity in order:
        sign = 1.0 if directions[identity] == "LEFT_TO_RIGHT" else -1.0
        for tau in range(1, taus + 1):
            rows.append({"trajectory_id": identity, "tau": tau,
                         "outer_fold": folds[identity], "direction": directions[identity],
                         "world_x": float(tau) * sign})
        blocks.append(generator.standard_normal((taus, tokens, hidden)).astype(np.float16))
    features = np.concatenate(blocks, axis=0)
    target = np.asarray([row["world_x"] for row in rows], dtype=np.float64)
    features[:, 0, 0] += (target / 20.0).astype(np.float16)

    for kind, readout in (("BEST_K", best_k_readout), ("FULL", full_readout)):
        predictions, selection, _ = readout(features, target, rows, order, folds, directions)
        assert set(predictions) == set(range(len(rows)))
        facts = verify_selection_discipline(
            _selection(selection, f"{kind} audit", kind), kind=kind,
            identity_outer_folds=folds, identity_directions=directions,
            rows_per_trajectory=taus, outer_fold_count=5,
            k_grid=procedure["k_grid"] if kind == "BEST_K" else None,
            alpha_grid=procedure["alpha_grid"],
            training_identities_required=inner["training_identities_required"],
            inner_fold_count=inner["inner_fold_count"],
            identities_per_inner_fold=inner["identities_per_inner_fold"],
            selection_training_tau_maximum=procedure["selection_rule"][
                "selection_training_tau_maximum"],
            label=kind)
        assert facts["identities_held_out_exactly_once"] == 25
        assert facts["pooled_predicted_row_count"] == 25 * taus
        assert facts["each_row_predicted_exactly_once"] is True


# ======================================================================
# B004 -- bootstrap configuration
# ======================================================================


class TestBootstrapBinding:
    def test_the_evidence_takes_its_configuration_from_the_producer(self, campaign):
        evidence = campaign.evidence()
        assert evidence["bootstrap_configuration"] == HONEST_BOOTSTRAP
        for stage in ("best_k", "full"):
            assert evidence["readouts"][stage]["bootstrap_configuration"] == HONEST_BOOTSTRAP

    def test_the_verification_is_not_authority_against_itself(self, campaign):
        """The producer's record is what moves; the authority stays put.

        Under the superseded builder this mutation was undetectable, because the
        field the evaluator read was copied out of the authority it was then
        compared against.
        """
        for stage in ("best_k", "full"):
            unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                        if item["pipeline_stage"] == stage)
            campaign.documents[unit["receipt_path"]]["bootstrap_configuration"]["seed"] = 1
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "recorded bootstrap seed" in decision["reasons"][0]
        # the authority on disk is untouched, which is exactly the point
        assert load_json(AUTHORITY_PATH)["stage2_policy"]["readout"]["bootstrap_seed"] == 2026081503

    @pytest.mark.parametrize("field,value", [
        ("seed", 20260815), ("seed", 0), ("resamples", 1000), ("resamples", 10001),
        ("unit", "ROW"), ("unit", "TRAJECTORY_ROW"),
        ("resample_population", "every_row"), ("resample_population_size", 475),
        ("statistic", "median_of_resampled_per_trajectory_r2"),
        ("confidence_bound_definition", "one_sided_90_normal_approximation"),
        ("generator", "numpy.random.seed"),
    ])
    def test_a_wrong_producer_configuration_blocks(self, campaign, field, value):
        for stage in ("best_k", "full"):
            unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                        if item["pipeline_stage"] == stage)
            campaign.documents[unit["receipt_path"]]["bootstrap_configuration"][field] = value
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert f"recorded bootstrap {field}" in decision["reasons"][0]

    def test_a_row_level_bootstrap_is_refused(self, campaign):
        """The specific substitution the finding names: rows, not trajectories."""
        for stage in ("best_k", "full"):
            unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                        if item["pipeline_stage"] == stage)
            campaign.documents[unit["receipt_path"]]["bootstrap_configuration"].update(
                {"unit": "ROW", "resample_population_size": 475})
        assert campaign.decide()["status"] == BLOCKED

    def test_a_missing_producer_configuration_is_refused_at_the_builder(self, campaign):
        unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                    if item["pipeline_stage"] == "best_k")
        campaign.documents[unit["receipt_path"]].pop("bootstrap_configuration")
        with pytest.raises(EvidenceError, match="recorded bootstrap configuration"):
            campaign.evidence()

    @pytest.mark.parametrize("field", ["unit", "resamples", "seed", "statistic",
                                       "confidence_bound_definition", "generator"])
    def test_a_blank_producer_field_is_refused_at_the_builder(self, campaign, field):
        unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                    if item["pipeline_stage"] == "best_k")
        campaign.documents[unit["receipt_path"]]["bootstrap_configuration"][field] = ""
        with pytest.raises(EvidenceError, match="bootstrap configuration is incomplete"):
            campaign.evidence()

    def test_two_readouts_disagreeing_are_refused_at_the_builder(self, campaign):
        unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                    if item["pipeline_stage"] == "full")
        campaign.documents[unit["receipt_path"]]["bootstrap_configuration"]["seed"] = 7
        with pytest.raises(EvidenceError, match="different bootstrap configurations"):
            campaign.evidence()


# ======================================================================
# B007 -- the readout self-grade
# ======================================================================


class TestSelfGrade:
    @pytest.mark.parametrize("claimed", ["FAIL", "BLOCKED", "PASSED", "pass", ""])
    def test_a_disagreeing_self_grade_blocks_a_genuine_pass(self, campaign, claimed):
        unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                    if item["pipeline_stage"] == "best_k")
        campaign.documents[unit["receipt_path"]]["qualification_status"] = claimed
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "graded itself" in decision["reasons"][0]

    def test_a_disagreeing_self_grade_blocks_a_genuine_fail_too(self, campaign):
        """A self-grade cannot rescue a failing readout any more than it can sink one."""
        campaign.set_readouts(wall=campaign._scene(rmse=0.9, baseline_rmse=1.5))
        unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                    if item["pipeline_stage"] == "best_k")
        campaign.documents[unit["receipt_path"]]["qualification_status"] = "PASS"
        assert campaign.decide()["status"] == BLOCKED

    def test_an_agreeing_self_grade_does_not_control_the_verdict(self, campaign):
        """FAIL is re-derived; the agreeing self-grade neither creates nor changes it."""
        campaign.set_readouts(wall=campaign._scene(rmse=0.9, baseline_rmse=1.5))
        decision = campaign.decide()
        assert decision["status"] == FAIL
        assert decision["gates"]["WALL_rmse"]["status"] == FAIL

    def test_an_absent_self_grade_blocks(self, campaign):
        unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                    if item["pipeline_stage"] == "best_k")
        campaign.documents[unit["receipt_path"]].pop("qualification_status")
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "recorded no qualification status" in decision["reasons"][0]


# ======================================================================
# B008 -- activation and unit metadata
# ======================================================================


class TestTerminalMetadata:
    @pytest.mark.parametrize("shape", [[19, 336, 4096], [19, 336, 2048, 1], [19, 337, 2048],
                                       [18, 336, 2048], [], [19, 336]])
    def test_a_wrong_activation_shape_blocks(self, campaign, shape):
        unit = campaign.manifest["extraction_units"][0]
        campaign.documents[unit["receipt_path"]]["shape"] = shape
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "not the frozen layer-4 contract" in decision["reasons"][0]

    def test_the_exact_frozen_shape_is_accepted(self, campaign):
        evidence = campaign.evidence()
        assert all(record["activation_shape"] == [19, 336, 2048]
                   for record in evidence["capture_inventory"])
        assert campaign.decide()["status"] == PASS

    @pytest.mark.parametrize("episode", [None, 0, 99999, 86001])
    def test_a_wrong_or_null_episode_blocks(self, campaign, episode):
        """Evidence must agree with the manifest unit, not merely carry a field."""
        evidence = campaign.evidence()
        record = next(item for item in evidence["capture_inventory"]
                      if item["episode_id"] != episode)
        record["episode_id"] = episode
        evidence["evidence_payload_sha256"] = canonical_payload_sha256(
            evidence, omit="evidence_payload_sha256")
        decision = campaign.decide(evidence)
        assert decision["status"] == BLOCKED
        assert "episode_id" in decision["reasons"][0]

    def test_an_evidence_record_naming_an_unknown_unit_blocks(self, campaign):
        evidence = campaign.evidence()
        evidence["capture_inventory"][0]["unit_id"] = "a2y_t99_wall"
        evidence["evidence_payload_sha256"] = canonical_payload_sha256(
            evidence, omit="evidence_payload_sha256")
        decision = campaign.decide(evidence)
        assert decision["status"] == BLOCKED
        assert "manifest does not declare" in decision["reasons"][0]

    @pytest.mark.parametrize("field,value", [
        ("scene", "NO_WALL"), ("direction", "RIGHT_TO_LEFT"), ("outer_fold", 4),
        ("phase_frames", 12), ("trajectory_id", "a2y_t25"),
    ])
    def test_evidence_metadata_that_contradicts_the_manifest_blocks(self, campaign, field, value):
        evidence = campaign.evidence()
        record = next(item for item in evidence["capture_inventory"]
                      if item[field] != value)
        record[field] = value
        evidence["evidence_payload_sha256"] = canonical_payload_sha256(
            evidence, omit="evidence_payload_sha256")
        assert campaign.decide(evidence)["status"] == BLOCKED

    def test_a_short_target_row_set_blocks(self, campaign):
        evidence = campaign.evidence()
        record = evidence["capture_inventory"][0]
        record["target_model_frame_indices"] = record["target_model_frame_indices"][:-1]
        evidence["evidence_payload_sha256"] = canonical_payload_sha256(
            evidence, omit="evidence_payload_sha256")
        decision = campaign.decide(evidence)
        assert decision["status"] == BLOCKED
        assert "frozen rows" in decision["reasons"][0]


# ======================================================================
# B005 -- claim precision, with the gates asserted unchanged
# ======================================================================


class TestClaimPrecision:
    @pytest.fixture(scope="class")
    @classmethod
    def promoted(cls):
        return load_json(DECISION_AUTHORITY_PATH)

    def test_the_six_gates_and_their_thresholds_did_not_move(self, promoted):
        authority = load_json(AUTHORITY_PATH)["stage2_policy"]["readout"]
        assert authority["best_k_each_scene_rmse_maximum_blocks"] == 0.15560477763641264
        assert authority["training_only_time_baseline_macro_r2_tau_1_to_15_maximum"] == 0.1
        assert authority["training_only_time_baseline_training_tau_maximum"] == 15
        assert promoted["best_k_gates"]["names"] == [
            "NO_WALL_r2", "NO_WALL_rmse", "WALL_beats_training_time_baseline",
            "WALL_r2", "WALL_rmse", "WALL_time_confound_gate"]
        assert promoted["best_k_gates"]["count"] == 6
        assert promoted["best_k_gates"]["all_must_pass"] is True

    def test_both_time_baseline_gates_are_still_evaluated_and_can_still_fail(self, campaign):
        campaign.set_readouts(wall=campaign._scene(rmse=0.05, baseline_rmse=0.04))
        assert campaign.decide()["gates"][
            "WALL_beats_training_time_baseline"]["status"] == FAIL
        campaign.set_readouts(wall=campaign._scene(confound=0.9))
        assert campaign.decide()["gates"]["WALL_time_confound_gate"]["status"] == FAIL

    def test_the_authority_records_that_neither_gate_binds_independently(self, promoted):
        bindingness = promoted["terminal"]["time_baseline_gate_bindingness"]
        assert bindingness["gates_unchanged"] is True
        assert bindingness["gates_remain_controlling"] is True
        assert bindingness["gates_can_bind_independently"] is False
        assert bindingness["motion_baselines_tested_by_this_stage"] == []

    def test_a_pass_does_not_claim_an_independent_baseline_victory(self, campaign):
        decision = campaign.decide()
        assert decision["status"] == PASS
        assert decision["time_baseline_gates_bind_independently"] is False
        assert decision["independent_motion_baseline_tested"] is False
        assert decision["rules_out_constant_velocity_explanation"] is False
        assert decision["rules_out_last_seen_position_explanation"] is False
        assert decision["rules_out_motion_based_explanations"] is False

    def test_the_interpretation_text_makes_the_distinction_explicitly(self, campaign):
        text = campaign.decide()["interpretation"].lower()
        assert "time-baseline gates were satisfied" in text
        assert "not evidence of having independently beaten" in text
        assert "constant-velocity" in text and "last-seen-" in text
        for forbidden in ("object permanence", "belief", "causal use"):
            assert f"establishes nothing about {forbidden}" in text or forbidden in text

    def test_the_promoted_rung_language_does_not_overclaim(self, promoted):
        assert "independent_victory_over_a_time_or_motion_baseline" in \
            promoted["terminal"]["pass_does_not_establish"]
        assert "exclusion_of_motion_based_explanations_generally" in \
            promoted["terminal"]["pass_does_not_establish"]
        assert promoted["terminal"]["pass_authorizes"] == {
            **promoted["terminal"]["pass_authorizes"],
            "confirmatory_collection": False, "causal_intervention": False, "next_rung": False}


# ======================================================================
# The promoted verification clause itself
# ======================================================================


class TestPromotedVerificationClause:
    def test_the_authority_demands_independent_verification(self):
        promoted = load_json(DECISION_AUTHORITY_PATH)
        required = promoted["terminal"]["independent_verification_required"]
        folds = required["fold_and_model_selection"]
        assert folds["self_reported_fold_validity_booleans_are_not_trusted"] is True
        for name in ("each_row_predicted_exactly_once", "selected_k_is_in_the_frozen_k_grid",
                     "training_and_test_identity_sets_are_disjoint",
                     "outer_test_identities_never_enter_model_selection",
                     "inner_fold_assignment_re_derives_from_the_frozen_rule"):
            assert name in folds["properties"]
        assert required["bootstrap_configuration"][
            "authority_compared_against_itself_is_not_verification"] is True
        assert required["readout_self_grade"]["self_grade_never_controls_the_verdict"] is True

    def test_an_authority_that_demands_no_verification_is_refused(self, campaign):
        campaign.decision_authority = copy.deepcopy(campaign.decision_authority)
        campaign.decision_authority["terminal"].pop("independent_verification_required")
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "requires no independent terminal verification" in decision["reasons"][0]

    def test_an_authority_whose_activation_contract_contradicts_the_authority_is_refused(
            self, campaign):
        campaign.decision_authority = copy.deepcopy(campaign.decision_authority)
        campaign.decision_authority["activation_contract"]["expected_shape"] = [19, 336, 4096]
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "disagrees with the authority it extends" in decision["reasons"][0]

    def test_an_authority_whose_bootstrap_contract_contradicts_the_authority_is_refused(
            self, campaign):
        campaign.decision_authority = copy.deepcopy(campaign.decision_authority)
        campaign.decision_authority["bootstrap_procedure"][
            "recorded_configuration_contract"]["seed"] = 1
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "disagrees with the authority it extends" in decision["reasons"][0]

    def test_the_promoted_grids_are_the_implementation_grids(self):
        promoted = load_json(DECISION_AUTHORITY_PATH)["readout_procedure"]
        assert promoted["k_grid"] == list(K_GRID)
        assert promoted["alpha_grid"] == list(ALPHAS)
        assert promoted["selection_rule"]["selection_training_tau_maximum"] == SELECTION_TAU_MAXIMUM

    def test_the_evidence_matches_its_versioned_schema(self, campaign):
        """The schema now requires the facts the terminal verifies.

        Without this, the schema and the evaluator could drift: a builder that
        stopped recording the fold or bootstrap facts would be caught by the
        evaluator but not by anything checking the document's declared shape.
        """
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads(
            (ROOT / "schemas/prospective/regime_a_prime_stage2_evidence_v0_4.schema.json"
             ).read_text())
        for name in ("bootstrap_configuration", "readouts", "capture_inventory"):
            assert name in schema["required"]
        selection = schema["$defs"]["readout"]["properties"]["scenes"][
            "additionalProperties"]["properties"]["selection_by_outer_fold"]
        for name in ("inner_fold_assignment", "predicted_row_keys_sha256",
                     "predicted_row_count", "selection_training_tau_maximum"):
            assert name in selection["additionalProperties"]["required"]
        errors = list(jsonschema.Draft202012Validator(schema).iter_errors(campaign.evidence()))
        assert errors == [], [error.message for error in errors[:3]]

    def test_the_decision_still_matches_its_versioned_schema(self, campaign):
        schema = json.loads(
            (ROOT / "schemas/prospective/regime_a_prime_stage2_decision_v0_4.schema.json"
             ).read_text())
        decision = campaign.decide()
        assert set(schema["required"]) <= set(decision)
        assert set(decision) <= set(schema["properties"])
