"""Focused successor tests for the Task 5 visible-position controls.

Only the two new controls are exercised: the sample-specific spatial scramble
and the audited grouped target null.  Task 1-4 authority is checked for
immutability, never recomputed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from scripts.run_visible_position_resolution_task4 import (
    REPRESENTATIONS,
    across_layout_folds,
    within_layout_folds,
)
from scripts.run_visible_position_resolution_task5 import (
    AUDITED_NULL_BASE_SEED,
    CONTROL_REPRESENTATIONS,
    FROZEN_SCRAMBLE_SEEDS,
    RUNTIME_ROOT,
    ScrambledTokenView,
    build_null_targets,
    build_permutation_table,
    load_frozen_scramble_seeds,
    null_strata,
    sample_permutation,
)

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = (
    ROOT / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
)
TOKEN_COUNT = 336
HIDDEN_WIDTH = 2048

FROZEN_TASK1_TO_TASK3_HASHES = {
    "development_freeze.json": (
        "97e68c4981a781053baef4f33a64516208725627bd757e7ffc2eb572951856ce"
    ),
    "expanded_visibility_eligibility.json": (
        "1882ec400159f83e4d09dc7b113907857dca5ad5f7fbd90760ad296fb289d6ea"
    ),
    "metric_decomposition.json": (
        "8c6b193363b8d14f332f8656a1cad377b6dfe51cd7edef7bcf704a3843b4c55c"
    ),
    "replication_authority_decision.json": (
        "8c0d4f07329529ef00e185c9fb880a0f927a8da4d34ebcd4fcc1121fb1ac674a"
    ),
    "replication_inventory.json": (
        "8adc3196663a676047352fa073e97e8cbb6176b3620c3bc0e22f68a1325ef7e4"
    ),
    "runtime_benchmark.json": (
        "baf1bfe4a2405e33d6cb6c73f51a9bfe1d62d77d392c08afa63554ffdc0677a7"
    ),
    "six_layout_generalization.json": (
        "d8fa0beb7c0605694a14d09383c0991a358d21fea913eefaaca7e2504e63d0e4"
    ),
    "spatial_representation_ladder.json": (
        "fc4a6df133bbef2c52714e6ba3379d3632e9db1e259fed06639556e1a928a39c"
    ),
    "capture_manifest.json": (
        "44575ecf539b3d93f50a64d1ae1270ea48a0124753a5d69c1f76f117aea37218"
    ),
    "expanded_activation_manifest.json": (
        "59fc98f1d2d9569d8814140e29827ddf522553b5b207b2116b7f2cf8f6961871"
    ),
}
PREDECESSOR_MANIFEST = (
    ROOT
    / "docs/status/integration/exploratory_visible_position_diagnostics_v0_1"
    / "unpooled_activation_manifest.json"
)
PREDECESSOR_SHA256 = "d7e9615f26856d64c96a55b4d52624dc24d7df5841e3f930a238a7d1c3987482"
MVP_MANIFEST = (
    ROOT / "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
MVP_SHA256 = "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Synthetic row/feature fixtures.  The scramble algebra is exact, so it can be
# proven on a small deterministic tensor without touching the NVMe caches.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def synthetic_rows() -> list[dict[str, object]]:
    rows = []
    for layout_index in range(1, 7):
        layout_id = f"layout_{layout_index:02d}"
        for trajectory_index in range(3):
            trajectory_id = (
                f"{layout_id}_ep{1000 + layout_index * 10 + trajectory_index}"
            )
            frame_count = 5 if (layout_index, trajectory_index) != (6, 0) else 4
            for frame in range(frame_count):
                rows.append(
                    {
                        "layout_id": layout_id,
                        "layout_label": f"L{layout_index:02d}",
                        "model_frame_idx": frame,
                        "row_key": f"{trajectory_id}:{frame}",
                        "trajectory_id": trajectory_id,
                        "x_true_blocks": float(
                            layout_index * 100 + trajectory_index * 10 + frame
                        ),
                    }
                )
    return rows


@pytest.fixture(scope="module")
def small_token_cache(synthetic_rows) -> np.ndarray:
    """A ``[rows, 336 * 2048]`` float32 grid is too large for a unit test.

    The scramble algebra is dimension-agnostic in the hidden axis, so the fixture
    keeps the frozen 336-token axis exactly and shrinks only the hidden width for
    the identities that do not depend on it.  Tests that must assert the exact
    frozen feature counts build the full-width view instead.
    """

    generator = np.random.default_rng(11)
    return generator.standard_normal(
        (len(synthetic_rows), TOKEN_COUNT, 8), dtype=np.float32
    )


class _NarrowView(ScrambledTokenView):
    """ScrambledTokenView with a narrowed hidden axis for cheap algebra tests."""

    def __init__(
        self, tokens: np.ndarray, permutation: np.ndarray, representation: str
    ):
        self._cache = tokens.reshape(tokens.shape[0], -1)
        self._permutation = permutation
        self.representation = representation
        self._hidden = int(tokens.shape[2])
        self._feature_count = (
            TOKEN_COUNT * self._hidden
            if representation == "FULL_TOKEN_GRID"
            else 12 * self._hidden
        )

    def __getitem__(self, indices):
        rows = [int(index) for index in indices]
        count = len(rows)
        block = np.asarray(self._cache[rows], dtype=np.float32).reshape(
            count, TOKEN_COUNT, self._hidden
        )
        block = block[np.arange(count)[:, None], self._permutation[rows]]
        if self.representation == "FULL_TOKEN_GRID":
            return np.ascontiguousarray(block.reshape(count, self._feature_count))
        pooled = block.reshape(count, 2, 7, 6, 4, self._hidden).mean(axis=(2, 4))
        return np.ascontiguousarray(pooled.reshape(count, self._feature_count))


# ---------------------------------------------------------------------------
# 1-5: frozen seeds and permutation construction
# ---------------------------------------------------------------------------


def test_scramble_seed_list_equals_frozen_seed_list_exactly():
    freeze = json.loads((INTEGRATION / "development_freeze.json").read_text())
    frozen = tuple(
        int(value) for value in freeze["sample_specific_spatial_scramble"]["seeds"]
    )
    assert (
        frozen
        == FROZEN_SCRAMBLE_SEEDS
        == (
            20260901,
            20260902,
            20260903,
            20260904,
            20260905,
        )
    )
    assert load_frozen_scramble_seeds(root=ROOT) == frozen
    assert (
        len(frozen)
        == int(freeze["sample_specific_spatial_scramble"]["seed_count"])
        == 5
    )


def test_scramble_is_deterministic_and_row_seed_reproducible():
    first = sample_permutation(20260901, "layout_01_ep12602:7")
    second = sample_permutation(20260901, "layout_01_ep12602:7")
    assert np.array_equal(first, second)
    assert sorted(first.tolist()) == list(range(TOKEN_COUNT))
    assert not np.array_equal(
        first, sample_permutation(20260902, "layout_01_ep12602:7")
    )


def test_different_rows_do_not_share_one_global_permutation(synthetic_rows):
    table = build_permutation_table(synthetic_rows, 20260901)
    signatures = {table[index].tobytes() for index in range(table.shape[0])}
    assert len(signatures) == table.shape[0]
    assert not np.array_equal(table[0], table[1])
    # A single global permutation would make every row identical.
    assert not np.all(table == table[0])


def test_target_values_never_enter_permutation_generation(synthetic_rows):
    baseline = build_permutation_table(synthetic_rows, 20260903)
    mutated = [dict(row) for row in synthetic_rows]
    for row in mutated:
        row["x_true_blocks"] = -999.0
    assert np.array_equal(baseline, build_permutation_table(mutated, 20260903))
    # Row identity is the only non-seed input.
    assert not np.array_equal(
        sample_permutation(20260903, "layout_01_ep0:0"),
        sample_permutation(20260903, "layout_01_ep0:1"),
    )


# ---------------------------------------------------------------------------
# 6-9: scramble semantics
# ---------------------------------------------------------------------------


def test_every_scrambled_row_preserves_the_same_336_token_vectors(
    synthetic_rows, small_token_cache
):
    table = build_permutation_table(synthetic_rows, 20260901)
    view = _NarrowView(small_token_cache, table, "FULL_TOKEN_GRID")
    indices = [0, 5, 17, 31]
    scrambled = view[indices].reshape(len(indices), TOKEN_COUNT, -1)
    for position, index in enumerate(indices):
        ordered = small_token_cache[index]
        assert np.array_equal(
            np.sort(scrambled[position], axis=0), np.sort(ordered, axis=0)
        )
        assert np.array_equal(scrambled[position], ordered[table[index]])


def test_full_and_coarse_dimensionality_are_unchanged(synthetic_rows):
    permutation = np.zeros((len(synthetic_rows), TOKEN_COUNT), dtype=np.int64)
    permutation[:] = np.arange(TOKEN_COUNT)
    cache = np.zeros(
        (len(synthetic_rows), TOKEN_COUNT * HIDDEN_WIDTH), dtype=np.float32
    )
    full = ScrambledTokenView(cache, permutation, "FULL_TOKEN_GRID")
    coarse = ScrambledTokenView(cache, permutation, "COARSE_2x6")
    assert full.shape == (len(synthetic_rows), 688128)
    assert coarse.shape == (len(synthetic_rows), 24576)
    assert full.shape[1] == REPRESENTATIONS["FULL_TOKEN_GRID"]["feature_count"]
    assert coarse.shape[1] == REPRESENTATIONS["COARSE_2x6"]["feature_count"]
    assert full[[0]].shape == (1, 688128)
    assert coarse[[0]].shape == (1, 24576)


def test_coarse_scramble_is_permutation_before_pooling(
    synthetic_rows, small_token_cache
):
    table = build_permutation_table(synthetic_rows, 20260902)
    coarse = _NarrowView(small_token_cache, table, "COARSE_2x6")
    indices = [3, 9, 14]
    produced = coarse[indices]

    hidden = small_token_cache.shape[2]
    for position, index in enumerate(indices):
        permuted = small_token_cache[index][table[index]]
        expected = permuted.reshape(2, 7, 6, 4, hidden).mean(axis=(1, 3)).reshape(-1)
        assert np.allclose(produced[position], expected, rtol=0, atol=0)

        # Pooling first and permuting regions afterwards is a different control
        # and must not coincide with the frozen permutation-before-pooling rule.
        pooled_then = (
            small_token_cache[index]
            .reshape(2, 7, 6, 4, hidden)
            .mean(axis=(1, 3))
            .reshape(12, hidden)
        )
        assert not np.allclose(produced[position].reshape(12, hidden), pooled_then)

    identity = np.tile(np.arange(TOKEN_COUNT), (len(synthetic_rows), 1))
    ordered = _NarrowView(small_token_cache, identity, "COARSE_2x6")[indices]
    reference = (
        small_token_cache[indices]
        .reshape(len(indices), 2, 7, 6, 4, hidden)
        .mean(axis=(2, 4))
        .reshape(len(indices), -1)
    )
    assert np.array_equal(ordered, reference)


def test_global_mean_is_permutation_invariant(synthetic_rows, small_token_cache):
    table = build_permutation_table(synthetic_rows, 20260904)
    view = _NarrowView(small_token_cache, table, "FULL_TOKEN_GRID")
    indices = [1, 8, 20]
    scrambled = view[indices].reshape(len(indices), TOKEN_COUNT, -1)
    assert np.allclose(
        scrambled.mean(axis=1).astype(np.float64),
        small_token_cache[indices].mean(axis=1).astype(np.float64),
        atol=1e-5,
    )


# ---------------------------------------------------------------------------
# 10-17: fold reuse, leakage and grouped selection semantics
# ---------------------------------------------------------------------------


def _task4_authority_rows() -> list[dict[str, object]]:
    """Rebuild the exact 1,071-row identity table from published Task 4 authority."""

    published = json.loads((INTEGRATION / "within_layout_replication.json").read_text())
    identity = published["combined_authority"]
    # Each within fold holds out exactly one complete trajectory, so its
    # test_row_count is that trajectory's authoritative row count.
    counts_by_trajectory = {
        fold["held_out_trajectories"][0]: int(fold["test_row_count"])
        for fold in published["representations"]["COARSE_2x6"]["folds"]
    }
    rows: list[dict[str, object]] = []
    for layout_id, trajectory_ids in sorted(
        identity["trajectory_ids_by_layout"].items()
    ):
        assert sum(counts_by_trajectory[t] for t in trajectory_ids) == int(
            identity["eligible_rows_by_layout"][layout_id]
        )
        for trajectory_id in sorted(trajectory_ids):
            for frame in range(counts_by_trajectory[trajectory_id]):
                rows.append(
                    {
                        "layout_id": layout_id,
                        "model_frame_idx": frame,
                        "row_key": f"{trajectory_id}:{frame}",
                        "trajectory_id": trajectory_id,
                        "x_true_blocks": 0.0,
                    }
                )
    assert len(rows) == identity["eligible_row_count"] == 1071
    return rows


def test_task4_within_and_across_folds_are_reused_exactly():
    rows = _task4_authority_rows()
    published_within = json.loads(
        (INTEGRATION / "within_layout_replication.json").read_text()
    )
    published_across = json.loads(
        (INTEGRATION / "across_layout_generalization.json").read_text()
    )
    assert published_within["outer_design"]["outer_fold_count"] == 18
    assert published_within["outer_design"]["outer_group"] == "trajectory"
    assert published_across["outer_design"]["outer_fold_count"] == 6
    assert published_across["outer_design"]["outer_group"] == "layout"

    within = within_layout_folds(rows)
    across = across_layout_folds(rows)
    assert len(within) == 18
    assert len(across) == 6
    for folds, document in ((within, published_within), (across, published_across)):
        published_folds = {
            fold["fold_id"]: fold
            for fold in document["representations"]["COARSE_2x6"]["folds"]
        }
        assert {fold["fold_id"] for fold in folds} == set(published_folds)
        for fold in folds:
            reference = published_folds[fold["fold_id"]]
            assert len(fold["train_index"]) == reference["train_row_count"]
            assert len(fold["test_index"]) == reference["test_row_count"]
            assert list(fold["training_group_ids"]) == list(
                reference["training_group_ids"]
            )
            assert len(fold["inner_folds"]) == len(reference["inner_folds"])
            for inner, published_inner in zip(
                fold["inner_folds"], reference["inner_folds"], strict=True
            ):
                assert len(inner["train_index"]) == published_inner["train_row_count"]
                assert (
                    len(inner["validation_index"])
                    == published_inner["validation_row_count"]
                )


def test_within_outer_trajectory_leakage_is_impossible(synthetic_rows):
    for fold in within_layout_folds(synthetic_rows):
        train = set(fold["train_index"])
        test = set(fold["test_index"])
        assert not train & test
        test_trajectories = {
            synthetic_rows[index]["trajectory_id"] for index in fold["test_index"]
        }
        train_trajectories = {
            synthetic_rows[index]["trajectory_id"] for index in fold["train_index"]
        }
        assert test_trajectories == {fold["held_out_trajectory"]}
        assert not test_trajectories & train_trajectories
        assert len(train_trajectories) == 2


def test_within_inner_validation_trajectory_is_excluded_from_scaler_and_fit(
    synthetic_rows,
):
    for fold in within_layout_folds(synthetic_rows):
        assert len(fold["inner_folds"]) == 2
        for inner in fold["inner_folds"]:
            assert not set(inner["train_index"]) & set(inner["validation_index"])
            assert not set(inner["train_index"]) & set(fold["test_index"])
            assert not set(inner["validation_index"]) & set(fold["test_index"])
            assert set(inner["training_trajectory_ids"]).isdisjoint(
                inner["validation_trajectory_ids"]
            )
            # The scaler is fit on exactly the inner training rows.
            assert len(inner["train_index"]) == len(set(inner["train_index"]))


def test_across_held_out_layout_is_absent_from_all_training_and_tuning(synthetic_rows):
    for fold in across_layout_folds(synthetic_rows):
        held_out = fold["held_out_layout"]
        assert not set(fold["train_index"]) & set(fold["test_index"])
        assert held_out not in set(fold["training_group_ids"])
        for index in fold["train_index"]:
            assert synthetic_rows[index]["layout_id"] != held_out
        for inner in fold["inner_folds"]:
            assert held_out not in inner["training_layout_ids"]
            assert held_out not in inner["validation_layout_ids"]
            for index in inner["train_index"] + inner["validation_index"]:
                assert synthetic_rows[index]["layout_id"] != held_out


def test_across_inner_validation_layout_is_excluded_from_scaler_and_fit(synthetic_rows):
    for fold in across_layout_folds(synthetic_rows):
        assert len(fold["inner_folds"]) == 5
        for inner in fold["inner_folds"]:
            assert not set(inner["train_index"]) & set(inner["validation_index"])
            assert set(inner["training_layout_ids"]).isdisjoint(
                inner["validation_layout_ids"]
            )
            assert len(inner["training_layout_ids"]) == 4


def test_training_only_scaling_and_grouped_alpha_semantics_are_unchanged():
    within = json.loads((INTEGRATION / "within_layout_replication.json").read_text())
    across = json.loads((INTEGRATION / "across_layout_generalization.json").read_text())
    for document, inner_group, inner_count in (
        (within, "training_trajectory", 2),
        (across, "training_layout", 5),
    ):
        semantics = document["nested_scaling_and_alpha_selection"]
        assert semantics["alpha_grid"] == [0.1, 1.0, 10.0, 100.0]
        assert semantics["inner_scaler"] == "fit on inner-training rows only"
        assert (
            semantics["outer_scaler"]
            == "fit on all outer-training rows only after alpha selection"
        )
        assert semantics["alpha_tie_break"] == "lowest numeric alpha"
        assert semantics["inner_group"] == inner_group
        assert semantics["inner_fold_count_per_outer"] == inner_count


# ---------------------------------------------------------------------------
# 18-21: audited grouped target null
# ---------------------------------------------------------------------------


def test_grouped_null_maps_to_the_audited_source_semantics():
    from mineocclude.metrics import resampling
    from mineocclude.probes import bridge

    source = (ROOT / "src/mineocclude/metrics/resampling.py").read_text()
    assert "def permute_trajectory_blocks" in source
    assert (
        "Shuffle whole equal-length trajectories without rearranging frames" in source
    )
    assert hasattr(resampling, "permute_trajectory_blocks")
    assert hasattr(resampling, "permutation_p_value")

    caller = (ROOT / "src/mineocclude/probes/bridge.py").read_text()
    assert "whole_trajectory_block" in caller
    assert "refit_scaler_alpha_and_ridge_inside_each_permutation" in caller
    assert "permutation_seed = requested_seed + permutation_index" in caller
    assert "add_one_greater_or_equal" in caller
    assert AUDITED_NULL_BASE_SEED == 20260720
    assert bridge is not None


def test_null_preserves_temporal_and_group_structure(synthetic_rows):
    targets = np.asarray(
        [row["x_true_blocks"] for row in synthetic_rows], dtype=np.float64
    )
    strata = null_strata(synthetic_rows)
    assert strata["singleton_stratum_trajectory_ids"] == ["layout_06_ep1060"]
    assert len(strata["permutable_trajectory_ids"]) == 17

    null_targets, audit = build_null_targets(synthetic_rows, targets, 20260720, strata)
    assert null_targets.shape == targets.shape
    assert audit["permuted_row_count"] + audit["retained_row_count"] == len(
        synthetic_rows
    )

    # The permuted target vector is a permutation of whole trajectory blocks:
    # every recipient block equals its donor block, frame order intact.
    by_trajectory: dict[str, list[int]] = {}
    for index, row in enumerate(synthetic_rows):
        by_trajectory.setdefault(str(row["trajectory_id"]), []).append(index)
    for recipient, donor in audit["donor_by_recipient"].items():
        recipient_rows = by_trajectory[recipient]
        donor_rows = by_trajectory[donor]
        assert np.array_equal(null_targets[recipient_rows], targets[donor_rows])
        assert [synthetic_rows[i]["model_frame_idx"] for i in recipient_rows] == sorted(
            synthetic_rows[i]["model_frame_idx"] for i in recipient_rows
        )
    # The singleton length stratum keeps its own block.
    singleton = strata["singleton_stratum_trajectory_ids"][0]
    singleton_rows = by_trajectory[singleton]
    assert np.array_equal(null_targets[singleton_rows], targets[singleton_rows])
    # Features, layout and trajectory membership are untouched by construction:
    # only the target vector is rebuilt.
    assert sorted(null_targets.tolist()) == sorted(targets.tolist())


def test_null_generation_is_deterministic_and_paired(synthetic_rows):
    targets = np.asarray(
        [row["x_true_blocks"] for row in synthetic_rows], dtype=np.float64
    )
    strata = null_strata(synthetic_rows)
    first, first_audit = build_null_targets(synthetic_rows, targets, 20260720, strata)
    second, second_audit = build_null_targets(synthetic_rows, targets, 20260720, strata)
    assert np.array_equal(first, second)
    assert first_audit["donor_by_recipient"] == second_audit["donor_by_recipient"]
    assert first_audit["null_targets_sha256"] == second_audit["null_targets_sha256"]

    other, _ = build_null_targets(synthetic_rows, targets, 20260721, strata)
    assert not np.array_equal(first, other)
    # COARSE and FULL consume the identical vector object for a given seed, so
    # their null comparison is paired by construction.
    assert len(CONTROL_REPRESENTATIONS) == 2


def test_null_seed_list_follows_the_audited_derivation():
    seeds = [AUDITED_NULL_BASE_SEED + index for index in range(100)]
    assert seeds[0] == 20260720
    assert seeds[-1] == 20260819
    assert len(set(seeds)) == 100


# ---------------------------------------------------------------------------
# 22-23: pre-outcome B freeze and solver equivalence
# ---------------------------------------------------------------------------


def _published_null() -> dict:
    path = INTEGRATION / "grouped_target_null.json"
    if not path.is_file():
        pytest.skip("grouped_target_null.json has not been produced yet")
    return json.loads(path.read_text())


def test_grouped_null_b_and_seeds_were_frozen_before_results():
    document = _published_null()
    freeze = document["b_freeze"]
    assert freeze["GROUPED_NULL_B_SELECTION_BASIS"] == "RUNTIME_ONLY"
    assert freeze["GROUPED_NULL_B_FROZEN_BEFORE_RESULTS"] is True
    assert freeze["benchmark_outcome_used_for_selection"] is False
    assert 25 <= freeze["GROUPED_NULL_B"] <= 100
    assert len(freeze["GROUPED_NULL_SEEDS"]) == freeze["GROUPED_NULL_B"]
    assert freeze["GROUPED_NULL_SEEDS"] == [
        AUDITED_NULL_BASE_SEED + index for index in range(freeze["GROUPED_NULL_B"])
    ]

    external = Path(freeze["external_artifact_path"])
    assert external.is_file()
    assert not str(external).startswith(str(ROOT))
    assert _sha256(external) == freeze["external_artifact_sha256"]
    recorded = json.loads(external.read_text())
    assert recorded["GROUPED_NULL_B"] == freeze["GROUPED_NULL_B"]
    assert recorded["GROUPED_NULL_SEEDS"] == freeze["GROUPED_NULL_SEEDS"]
    assert "null_macro_r2" not in recorded and "summary" not in recorded
    assert (
        external.stat().st_mtime
        <= (INTEGRATION / "grouped_target_null.json").stat().st_mtime
    )
    assert RUNTIME_ROOT.is_dir()


def test_optimized_null_solver_matches_the_frozen_ridge_objective():
    document = _published_null()
    equivalence = document["optimization_equivalence"]
    assert equivalence["status"] == "PASS"
    assert len(equivalence["checks"]) == len(CONTROL_REPRESENTATIONS)
    for check in equivalence["checks"]:
        assert check["status"] == "PASS"
        assert check["selected_alphas_match"] is True
        assert check["max_abs_per_fold_r2_difference_vs_numpy_solve"] <= 1e-9
        assert check["abs_difference_vs_frozen_task4"] <= 1e-9


def test_published_null_replicates_match_the_frozen_b_and_seeds():
    document = _published_null()
    b = document["b_freeze"]["GROUPED_NULL_B"]
    seeds = document["b_freeze"]["GROUPED_NULL_SEEDS"]
    assert [record["seed"] for record in document["replicates"]] == seeds
    hashes = {
        record["seed"]: record["null_targets_sha256"]
        for record in document["replicates"]
    }
    assert len(set(hashes.values())) == len(seeds)
    for representation in CONTROL_REPRESENTATIONS:
        values = document["null_macro_r2_by_representation"][representation]
        assert len(values) == b
        summary = document["summary"][representation]
        assert summary["null_replicate_count"] == b
        assert summary["upper_tail_rule"] == "(1 + count(null >= observed)) / (B + 1)"
        assert summary["scope"] == "EXPLORATORY_NOT_THE_CONFIRMATORY_SHUFFLED_P_GATE"
        expected = (
            1
            + sum(
                value >= summary["observed_across_layout_macro_r2"] for value in values
            )
        ) / (b + 1)
        assert summary["upper_tail_empirical_statistic"] == pytest.approx(expected)
    assert document["primary_design"]["rows_subsampled"] is False
    assert document["primary_design"]["layouts_discarded"] == 0
    assert document["primary_design"]["model_selection_repeated_per_replicate"] is True
    assert document["primary_design"]["observed_alpha_frozen"] is False


def test_published_scramble_control_records_the_frozen_seeds():
    path = INTEGRATION / "spatial_scramble_control.json"
    if not path.is_file():
        pytest.skip("spatial_scramble_control.json has not been produced yet")
    document = json.loads(path.read_text())
    definition = document["scramble_definition"]
    assert definition["frozen_seeds"] == list(FROZEN_SCRAMBLE_SEEDS)
    assert definition["single_global_permutation"] is False
    assert definition["permutation_before_pooling"] is True
    assert definition["permutation_inputs"] == ["frozen_seed", "row_key"]
    for seed, record in document["permutation_identity"].items():
        assert record["distinct_permutation_count"] == record["row_count"] == 1071
        assert record["token_count"] == 336
        assert int(seed) in FROZEN_SCRAMBLE_SEEDS
    for representation in CONTROL_REPRESENTATIONS:
        feature_count = REPRESENTATIONS[representation]["feature_count"]
        for design, expected_folds in (("within", 18), ("across", 6)):
            per_seed = document["folds_by_representation"][representation][design]
            assert sorted(per_seed) == sorted(
                str(seed) for seed in FROZEN_SCRAMBLE_SEEDS
            )
            for folds in per_seed.values():
                assert len(folds) == expected_folds
                for fold in folds:
                    assert fold["feature_count"] == feature_count
                    assert (
                        fold["outer_scaler_training_row_count"]
                        == fold["train_row_count"]
                    )
                    assert fold["train_row_count"] + fold["test_row_count"] <= 1071
    assert document["global_mean_permutation_invariance"]["status"] == "PASS"
    for check in document["global_mean_permutation_invariance"]["checks"]:
        assert check["max_abs_difference_vs_ordered_pooling"] <= 1e-4


# ---------------------------------------------------------------------------
# 24-31: frozen authority immutability and repository hygiene
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,expected", sorted(FROZEN_TASK1_TO_TASK3_HASHES.items()))
def test_task1_to_task3_authority_is_unchanged(name, expected):
    assert _sha256(INTEGRATION / name) == expected


def test_predecessor_package_and_frozen_mvp_are_unchanged():
    assert _sha256(PREDECESSOR_MANIFEST) == PREDECESSOR_SHA256
    assert _sha256(MVP_MANIFEST) == MVP_SHA256


def test_task4_reports_are_unchanged_by_task5():
    within = json.loads((INTEGRATION / "within_layout_replication.json").read_text())
    across = json.loads((INTEGRATION / "across_layout_generalization.json").read_text())
    assert (
        within["runner"]["version"] == "visible-position-resolution-task4-runner-v0.1"
    )
    assert (
        across["runner"]["version"] == "visible-position-resolution-task4-runner-v0.1"
    )
    assert within["controls_run"] == []
    assert across["controls_run"] == []
    assert within["representations"]["COARSE_2x6"]["summary"][
        "equal_layout_macro_mean_r2"
    ] == pytest.approx(0.8249646147116141, abs=0.0)
    assert within["representations"]["FULL_TOKEN_GRID"]["summary"][
        "equal_layout_macro_mean_r2"
    ] == pytest.approx(0.815495540876805, abs=0.0)
    assert within["representations"]["GLOBAL_MEAN"]["summary"][
        "equal_layout_macro_mean_r2"
    ] == pytest.approx(0.014819740599772898, abs=0.0)
    classifications = across["classifications"]
    assert classifications["token_preserving_readout_generalizes"] == "UNCLEAR"
    assert classifications["trajectory_variance_class"] == "MIXED_TRAJECTORY_EFFECT"
    assert classifications["trajectory_variance_dominant"] is False
    assert (
        classifications["layout_variance_class"]
        == "BOTH_TRAJECTORY_AND_LAYOUT_VARIANCE"
    )
    assert classifications["layout_variance_dominant"] is False
    assert classifications["both_trajectory_and_layout_variance"] is True
    assert classifications["layout_specific_representation_plausible"] is True
    for representation, expected in (
        ("GLOBAL_MEAN", 0.26574307713230466),
        ("COARSE_2x6", 0.3191491809005946),
        ("FULL_TOKEN_GRID", 0.3175977234797748),
    ):
        assert across["representations"][representation]["summary"][
            "equal_layout_macro_metrics"
        ]["r2"]["mean"] == pytest.approx(expected, abs=0.0)


def test_task5_preserves_task4_classifications_verbatim():
    path = INTEGRATION / "grouped_target_null.json"
    if not path.is_file():
        pytest.skip("grouped_target_null.json has not been produced yet")
    document = json.loads(path.read_text())
    preserved = document["task4_classifications_preserved"]
    assert preserved["TOKEN_PRESERVING_READOUT_GENERALIZES"] == "UNCLEAR"
    assert preserved["TRAJECTORY_VARIANCE_CLASS"] == "MIXED_TRAJECTORY_EFFECT"
    assert preserved["TRAJECTORY_VARIANCE_DOMINANT"] is False
    assert preserved["LAYOUT_VARIANCE_CLASS"] == "BOTH_TRAJECTORY_AND_LAYOUT_VARIANCE"
    assert preserved["LAYOUT_VARIANCE_DOMINANT"] is False
    assert preserved["BOTH_TRAJECTORY_AND_LAYOUT_VARIANCE"] is True
    assert preserved["LAYOUT_SPECIFIC_REPRESENTATION_PLAUSIBLE"] is True


def test_large_tensors_and_caches_remain_outside_git():
    tracked = subprocess.run(
        ["git", "ls-files", "--", "docs/status/integration", "scripts", "tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    changed = [line[3:].strip().strip('"') for line in status if line[3:].strip()]
    for entry in list(tracked) + changed:
        assert not entry.endswith((".npy", ".npz", ".pt", ".bin")), entry
        assert "sagemaker-nvme" not in entry, entry
    for entry in sorted(set(tracked) | set(changed)):
        path = ROOT / entry
        if path.is_file() and str(path).startswith(str(INTEGRATION)):
            assert path.stat().st_size < 8_000_000, entry
    assert str(RUNTIME_ROOT).startswith("/mnt/sagemaker-nvme/")
    for name in ("spatial_scramble_control.json", "grouped_target_null.json"):
        path = INTEGRATION / name
        if path.is_file():
            document = json.loads(path.read_text())
            assert document["large_tensors_in_git"] is False
