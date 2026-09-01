"""A12/A13/A14-A16 driver conformance, and the A11 -> A19 dataflow seam.

These stages were shipped with their heads amputated: A12 implemented only
``HASH_AND_SEAL`` and demanded a hand-written predictions file, A13 had no
driver at all, and A14 read an ``--estimands`` file instead of deriving the
estimands from the lock. Every test here exists so that specific defect cannot
come back.

Nothing here touches production data. The fixture is a complete synthetic world
-- captures, manifest, folds, feature blocks -- with the frozen *shapes* reduced
so the suite stays fast; every recipe, refusal and stage boundary under test is
the real one.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPOSITORY_ROOT / "scripts" / "experiment_iii"
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii import a12_predictions, feature_store, namespace  # noqa: E402
from mineocclude.experiment_iii.artifact_inventory import stage_exit_check_fs  # noqa: E402
from mineocclude.experiment_iii.authority import TARGET_ROWS_PER_CAPTURE  # noqa: E402
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.prediction_lock import (  # noqa: E402
    PredictionCell,
    PredictionLock,
)
from mineocclude.experiment_iii.readout import FoldData, fit_outer_fold  # noqa: E402
from mineocclude.experiment_iii.schema import ConditionId  # noqa: E402

CONDITIONS = [c.value for c in ConditionId]
IDENTITIES = [f"e3_t{index:02d}" for index in range(1, 11)]
FRAMES = 120
FIRST_TARGET_ROW = 60

#: Reduced only in width. Every count that carries scientific meaning -- 19 rows,
#: 5 conditions, 5 outer folds, 4 inner rotations, 5 alphas -- is the real one.
FIXTURE_DIMENSIONS = {
    "CURRENT": 8,
    "CURRENT_MINUS_PREVIOUS": 8,
    "TWO_FRAME_CONCAT": 16,
    "CURRENT_L04": 8,
    "CURRENT_L10": 8,
    feature_store.PIXEL_BLOCK: 6,
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_e3_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def drivers():
    return {
        name: _load(name)
        for name in ("lock_predictions", "run_primary_analysis", "build_scientific_package")
    }


@pytest.fixture
def narrow_blocks(monkeypatch):
    monkeypatch.setattr(feature_store, "BLOCK_DIMENSIONS", dict(FIXTURE_DIMENSIONS))
    return FIXTURE_DIMENSIONS


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Relocate the guarded namespace root, rather than disarming the guard.

    Authority 0.4 refuses any write outside ``docs/experiment_iii`` or
    ``data/experiment_iii``. The fixture therefore builds those two roots inside
    ``tmp_path`` and points the guard at it, so the tests exercise the same
    refusal path production does.
    """
    monkeypatch.setattr(namespace, "REPOSITORY_ROOT", tmp_path)
    (tmp_path / "docs" / "experiment_iii").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "experiment_iii").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _folds() -> dict:
    """Five outer folds, two held-out identities each, four inner rotations."""
    folds = []
    for outer in range(5):
        held = [IDENTITIES[outer * 2], IDENTITIES[outer * 2 + 1]]
        training = [name for name in IDENTITIES if name not in held]
        rotations = {str(r): training[r * 2 : r * 2 + 2] for r in range(4)}
        folds.append(
            {
                "outer_fold": outer,
                "held_out_identities": held,
                "training_identities": training,
                "inner_rotations": rotations,
            }
        )
    return {"schema_version": "fixture", "outer_folds": 5, "folds": folds}


def _write_capture(root: Path, identity: str, condition: str, seed: int) -> None:
    """A capture with a real occlusion onset and enough pre-occlusion history."""
    unit = root / f"{identity}__{condition}"
    (unit / "raw").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    start = -8.0 + 0.1 * seed
    with (unit / "coordinates.jsonl").open("w", encoding="utf-8") as handle:
        for tick in range(FRAMES):
            position = start + 0.12 * tick + 0.001 * rng.normal()
            handle.write(
                json.dumps(
                    {
                        "server_tick": tick,
                        "axis_pos": float(position),
                        "sheep_x": float(position),
                    }
                )
                + "\n"
            )
    with (unit / "raw" / "visibility.jsonl").open("w", encoding="utf-8") as handle:
        for frame in range(FRAMES):
            occluded = frame >= FIRST_TARGET_ROW
            handle.write(
                json.dumps(
                    {
                        "model_frame_idx": frame,
                        "condition_id": condition,
                        "counterfactual_extent_class": (
                            "EXTENT_FULLY_OCCLUDED" if occluded else "EXTENT_FULLY_VISIBLE"
                        ),
                    }
                )
                + "\n"
            )


@pytest.fixture
def world(sandbox, narrow_blocks):
    """A complete synthetic A11 hand-off: captures, manifest, folds, blocks."""
    tmp_path = sandbox
    docs = tmp_path / "docs" / "experiment_iii"
    data = tmp_path / "data" / "experiment_iii"
    captures = data / "production" / "captures"
    features = data / "features"
    results = docs / "results"
    results.mkdir(parents=True, exist_ok=True)

    target_rows = list(range(FIRST_TARGET_ROW, FIRST_TARGET_ROW + TARGET_ROWS_PER_CAPTURE))
    manifest_path = docs / "manifest.jsonl"
    rng = np.random.default_rng(20260901)
    targets: dict[str, np.ndarray] = {}
    with manifest_path.open("w", encoding="utf-8") as handle:
        for index, identity in enumerate(IDENTITIES):
            # A target series with real spread, so R^2 has a nonzero TSS.
            labels = np.linspace(-4.0, 4.0, TARGET_ROWS_PER_CAPTURE) + rng.normal(
                scale=0.05, size=TARGET_ROWS_PER_CAPTURE
            )
            targets[identity] = labels
            handle.write(
                json.dumps(
                    {
                        "identity": identity,
                        "direction": "LEFT_TO_RIGHT" if index % 2 == 0 else "RIGHT_TO_LEFT",
                        "target_model_frame_indices": target_rows,
                        "expected_causal_fir_target_world_x_blocks": [
                            float(v) for v in labels
                        ],
                    }
                )
                + "\n"
            )
            for condition in CONDITIONS:
                _write_capture(captures, identity, condition, seed=index * 7 + 1)

    # Feature blocks that genuinely carry the target, degraded by condition, so
    # the ridge has something to find and the analysis is not fitting noise.
    degrade = {"L0": 0.02, "L1": 0.25, "L2": 0.5, "L3": 0.75, "L4": 1.1}
    for identity in IDENTITIES:
        for condition in CONDITIONS:
            unit = feature_store.unit_id(identity, condition)
            for block, width in FIXTURE_DIMENSIONS.items():
                noise = rng.normal(
                    scale=degrade[condition], size=(TARGET_ROWS_PER_CAPTURE, width)
                )
                signal = np.tile(
                    targets[identity].reshape(-1, 1) / 4.0, (1, width)
                )
                feature_store.write_block(features, block, unit, signal + noise)

    (docs / "folds.json").write_text(json.dumps(_folds()), encoding="utf-8")
    (docs / "a8.json").write_text(
        json.dumps(
            {
                "stage": "A8",
                "passed": True,
                "N_complete": len(IDENTITIES),
                "complete_five_way_paired_identities": IDENTITIES,
            }
        ),
        encoding="utf-8",
    )
    return {
        "root": docs,
        "captures": captures,
        "features": features,
        "results": results,
        "manifest": manifest_path,
        "folds": docs / "folds.json",
        "a8": docs / "a8.json",
        "targets": targets,
    }


def _lock_argv(world, extra=()):
    return [
        "--stage", "lock",
        "--out", str(world["results"]),
        "--features", str(world["features"]),
        "--folds", str(world["folds"]),
        "--manifest", str(world["manifest"]),
        "--captures", str(world["captures"]),
        "--a8-receipt", str(world["a8"]),
        "--allow-unhashed-features",
        *extra,
    ]


# --------------------------------------------------------------------------
# A12 — the driver computes its own predictions
# --------------------------------------------------------------------------


def test_a12_generates_predictions_from_feature_blocks(world, drivers, capsys):
    """A12 fits and emits. It requires no investigator-authored file."""
    rc = drivers["lock_predictions"].main(_lock_argv(world))
    assert rc == 0, capsys.readouterr().err
    out = capsys.readouterr().out
    assert "A12_STATUS=PASS" in out
    assert "A12_EXTERNAL_PREDICTIONS_REQUIRED=false" in out
    assert "PREDICTION_LOCK_SEALED_BEFORE_STATISTICS=true" in out

    lock = json.loads((world["results"] / "PREDICTION_LOCK.json").read_text())
    expected = (
        len(IDENTITIES)
        * len(CONDITIONS)
        * TARGET_ROWS_PER_CAPTURE
        * len(a12_predictions.ALL_MODELS)
    )
    assert lock["cell_count"] == expected
    assert sorted(lock["models"]) == sorted(a12_predictions.ALL_MODELS)
    assert sorted(lock["conditions"]) == sorted(CONDITIONS)
    assert (world["results"] / "PREDICTION_LOCK.sha256").is_file()


def test_a12_takes_no_predictions_argument(drivers):
    """The false scientific dependency is gone, not merely defaulted."""
    parser_source = (SCRIPTS / "lock_predictions.py").read_text()
    assert "a12_preregistered_predictions" not in parser_source
    assert '"--predictions"' not in parser_source


def test_a12_alpha_comes_from_the_frozen_five_value_grid(world, drivers, capsys):
    drivers["lock_predictions"].main(_lock_argv(world))
    capsys.readouterr()
    receipt = json.loads((world["results"] / "prediction_fit_receipt.json").read_text())
    assert receipt["alpha_grid"] == [0.1, 1.0, 10.0, 100.0, 1000.0]
    assert receipt["alpha_tie_break"] == "SMALLEST_ALPHA"
    assert receipt["alpha_selection_criterion"] == "IDENTITY_MACRO_INNER_VALIDATION_MEAN_RMSE"
    assert receipt["held_out_tuning_performed"] is False
    for condition in CONDITIONS:
        for selection in receipt["alpha_selections"]["MW_CURRENT"][condition].values():
            assert selection["selected_alpha"] in (0.1, 1.0, 10.0, 100.0, 1000.0)
            assert selection["inner_rotations"] == 4


def test_a12_refuses_to_relock_over_an_existing_lock(world, drivers, capsys):
    """The lock is the irreversible boundary; re-locking is not a retry."""
    assert drivers["lock_predictions"].main(_lock_argv(world)) == 0
    capsys.readouterr()
    assert drivers["lock_predictions"].main(_lock_argv(world)) == 1
    assert "PREDICTION_LOCK_AFTER_STATISTICS" in capsys.readouterr().err


def test_a12_refuses_a_feature_block_that_moved_after_a11_hashed_it(world, drivers, capsys):
    config = world["root"] / "feature_config.json"
    config.write_text(
        json.dumps(
            {
                "feature_block_hashes": {
                    feature_store.unit_id(identity, condition): {
                        block: "0" * 64 for block in FIXTURE_DIMENSIONS
                    }
                    for identity in IDENTITIES
                    for condition in CONDITIONS
                }
            }
        ),
        encoding="utf-8",
    )
    argv = [a for a in _lock_argv(world) if a != "--allow-unhashed-features"]
    argv += ["--feature-config", str(config)]
    assert drivers["lock_predictions"].main(argv) == 1
    assert "PREDICTION_LOCK_AFTER_STATISTICS" in capsys.readouterr().err


# --------------------------------------------------------------------------
# The prediction-lock firewall
# --------------------------------------------------------------------------


def test_no_identity_appears_in_its_own_training_set():
    leaking = [
        {
            "outer_fold": 0,
            "held_out_identities": ["e3_t01"],
            "training_identities": ["e3_t01", "e3_t02"],
            "inner_rotations": {"0": ["e3_t02"]},
        }
    ]
    with pytest.raises(ExperimentIIIError) as caught:
        a12_predictions.assert_no_identity_in_its_own_training_set(leaking)
    assert caught.value.blocker == "FOLD_LEAKAGE_DETECTED"


def test_alpha_may_not_be_selected_on_held_out_identities():
    """An inner rotation naming a held-out identity is refused, not scored."""
    rng = np.random.default_rng(3)
    def _entry(name):
        return FoldData(
            identity=name,
            features=rng.normal(size=(TARGET_ROWS_PER_CAPTURE, 4)),
            targets=rng.normal(size=TARGET_ROWS_PER_CAPTURE),
        )
    training = {name: _entry(name) for name in ("a", "b", "c")}
    held = {"z": _entry("z")}
    with pytest.raises(ExperimentIIIError) as caught:
        fit_outer_fold(training, held, {0: ["z"], 1: ["a"]})
    assert caught.value.blocker == "FOLD_LEAKAGE_DETECTED"


def test_a_statistic_before_the_lock_is_sealed_fails_closed():
    lock = PredictionLock()
    lock.add(PredictionCell("e3_t01", "L0", 0, "MW_CURRENT", 0.1, 0.2))
    with pytest.raises(ExperimentIIIError) as caught:
        lock.require_sealed("the primary analysis")
    assert caught.value.blocker == "PREDICTION_LOCK_MISSING"


def test_duplicate_and_missing_cells_are_both_refused():
    lock = PredictionLock()
    cell = PredictionCell("e3_t01", "L0", 0, "MW_CURRENT", 0.1, 0.2)
    lock.add(cell)
    with pytest.raises(ExperimentIIIError) as caught:
        lock.add(cell)
    assert caught.value.blocker == "PREDICTION_DUPLICATE_CELL"

    with pytest.raises(ExperimentIIIError) as caught:
        lock.assert_complete(
            identities=["e3_t01"], conditions=CONDITIONS, rows=2, models=["MW_CURRENT"]
        )
    assert caught.value.blocker == "PREDICTION_LOCK_MISSING"


def test_a14_and_a13_both_refuse_to_run_without_a_lock(world, drivers, capsys):
    assert (
        drivers["run_primary_analysis"].main(
            ["--stage", "primary", "--out", str(world["results"])]
        )
        == 1
    )
    assert "ANALYSIS_INPUT_NOT_LOCKED" in capsys.readouterr().err
    assert (
        drivers["lock_predictions"].main(
            ["--stage", "baselines", "--out", str(world["results"])]
        )
        == 1
    )
    assert "PREDICTION_LOCK_MISSING" in capsys.readouterr().err


def test_an_edited_lock_no_longer_hashes_true(world, drivers, capsys):
    drivers["lock_predictions"].main(_lock_argv(world))
    capsys.readouterr()
    path = world["results"] / "PREDICTION_LOCK.json"
    payload = json.loads(path.read_text())
    payload["cells"][0]["prediction"] += 1.0
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert (
        drivers["run_primary_analysis"].main(
            ["--stage", "primary", "--out", str(world["results"])]
        )
        == 1
    )
    assert "PREDICTION_LOCK_AFTER_STATISTICS" in capsys.readouterr().err


# --------------------------------------------------------------------------
# A13
# --------------------------------------------------------------------------


def test_a13_reports_five_baselines_and_the_l0_control(world, drivers, capsys):
    assert drivers["lock_predictions"].main(_lock_argv(world)) == 0
    capsys.readouterr()
    rc = drivers["lock_predictions"].main(
        ["--stage", "baselines", "--out", str(world["results"])]
    )
    assert rc == 0, capsys.readouterr().err
    assert "A13_STATUS=PASS" in capsys.readouterr().out

    receipt = json.loads((world["results"] / "baselines_receipt.json").read_text())
    assert receipt["stage"] == "A13"
    assert receipt["baseline_count"] == 5
    assert sorted(receipt["baselines"]) == sorted(a12_predictions.BASELINE_MODELS)
    assert receipt["required_manuscript_language"] == "linear current-frame pixel baseline"
    assert receipt["constant_velocity_window"] == 10
    assert receipt["oracle_baselines_are_model_inputs"] is False
    assert receipt["l0_interpretability_control"]["statistic"] == (
        "L0_RMSE_IMPROVEMENT_OVER_OUTER_TRAINING_MEAN"
    )
    assert receipt["overall_pass_fail_verdict"] is None


def test_a13_refuses_a_lock_missing_a_baseline(world, drivers, capsys):
    drivers["lock_predictions"].main(_lock_argv(world))
    capsys.readouterr()
    path = world["results"] / "PREDICTION_LOCK.json"
    payload = json.loads(path.read_text())
    payload["cells"] = [c for c in payload["cells"] if c["model"] != "TIME_ONLY"]
    payload.pop("prediction_lock_sha256", None)
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert (
        drivers["lock_predictions"].main(
            ["--stage", "baselines", "--out", str(world["results"])]
        )
        == 1
    )
    assert "BASELINE_MISSING" in capsys.readouterr().err


def test_oracle_baselines_are_identical_across_conditions(world, drivers, capsys):
    """8.9.6 — last-seen and constant velocity read counterfactual state only."""
    drivers["lock_predictions"].main(_lock_argv(world))
    capsys.readouterr()
    payload = json.loads((world["results"] / "PREDICTION_LOCK.json").read_text())
    seen: dict[tuple[str, str, int], set[float]] = {}
    for cell in payload["cells"]:
        if cell["model"] in a12_predictions.ORACLE_MODELS:
            key = (cell["model"], cell["identity"], int(cell["row_index"]))
            seen.setdefault(key, set()).add(round(float(cell["prediction"]), 12))
    assert seen
    assert all(len(values) == 1 for values in seen.values())


# --------------------------------------------------------------------------
# A14 / A15 / A16
# --------------------------------------------------------------------------


@pytest.fixture
def sealed(world, drivers, capsys):
    assert drivers["lock_predictions"].main(_lock_argv(world)) == 0
    assert (
        drivers["lock_predictions"].main(
            ["--stage", "baselines", "--out", str(world["results"])]
        )
        == 0
    )
    capsys.readouterr()
    return world


def test_a14_derives_the_three_estimands_from_the_lock(sealed, drivers, capsys):
    rc = drivers["run_primary_analysis"].main(
        ["--stage", "primary", "--out", str(sealed["results"])]
    )
    assert rc == 0, capsys.readouterr().err
    out = capsys.readouterr().out
    assert "A14_STATUS=PASS" in out
    assert "A14_EXTERNAL_ESTIMANDS_REQUIRED=false" in out
    assert "PRIMARY_FAMILY_SIZE=3" in out
    assert "BOOTSTRAP_SEED=8258108568742502015" in out
    assert "BOOTSTRAP_REPLICATES=10000" in out
    assert "OVERALL_PASS_FAIL_VERDICT=none" in out

    result = json.loads((sealed["results"] / "primary_results.json").read_text())
    assert sorted(result["estimands"]) == ["Dopaque_i", "Dpartial_i", "S_i"]
    assert result["multiplicity"] == "HOLM_ACROSS_3"
    assert result["inferential_unit"] == "IDENTITY"
    assert result["estimands_derived_from_lock"] is True
    assert set(result["per_identity_estimands"]) == set(IDENTITIES)
    for entry in result["estimands"].values():
        assert entry["hypothesis"] == "POSITIVE"
        assert entry["interval"]["resampling_unit"] == "WHOLE_IDENTITY"
        assert entry["interval"]["replicates"] == 10000
        assert "holm_adjusted_p_value" in entry
    # V_c is the frozen binding, not a recomputed quantity.
    assert result["V_c"]["L0"] == 1.0
    assert result["O_c"]["L0"] == 0.0


def test_a14_takes_no_estimands_argument():
    source = (SCRIPTS / "run_primary_analysis.py").read_text()
    assert "a14_estimands" not in source
    assert '"--estimands"' not in source


def test_a14_refuses_a_bootstrap_seed_that_is_not_the_frozen_one(sealed, drivers, capsys):
    rc = drivers["run_primary_analysis"].main(
        ["--stage", "primary", "--out", str(sealed["results"]), "--bootstrap-seed", "12345"]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "STATS_BOOTSTRAP_SEED_MISMATCH" in err
    assert "8258108568742502015" in err


def test_a15_computes_exactly_two_temporal_contrasts(sealed, drivers, capsys):
    rc = drivers["run_primary_analysis"].main(
        ["--stage", "temporal", "--out", str(sealed["results"])]
    )
    assert rc == 0, capsys.readouterr().err
    out = capsys.readouterr().out
    assert "TEMPORAL_CONTRASTS=2" in out
    assert "HOLM_FAMILY_SIZE=2" in out
    result = json.loads((sealed["results"] / "temporal_results.json").read_text())
    assert result["multiplicity"] == "HOLM_ACROSS_2"
    assert sorted(result["contrast_results"]) == [
        "CURRENT_MINUS_PREVIOUS_VS_CURRENT",
        "TWO_FRAME_CONCAT_VS_CURRENT",
    ]
    assert result["averaged_over_conditions"] == ["L1", "L2", "L3", "L4"]
    assert result["may_replace_primary_readout"] is False


def test_a16_reports_four_bins_and_one_boundary_interaction(sealed, drivers, capsys):
    rc = drivers["run_primary_analysis"].main(
        ["--stage", "context", "--out", str(sealed["results"])]
    )
    assert rc == 0, capsys.readouterr().err
    out = capsys.readouterr().out
    assert "CONTEXT_REPORTING_BINS=4" in out
    assert "BOUNDARY_INTERACTIONS=1" in out
    result = json.loads((sealed["results"] / "context_age_results.json").read_text())
    assert len(result["bins"]) == 4
    assert result["boundary_interaction_windows"] == [[12, 15], [16, 19]]
    assert result["inferential_role"] == "DESCRIPTIVE_ONLY"
    assert result["enters_holm_family"] is False
    assert result["causal_forgetting_claim_allowed"] is False
    assert set(result["per_identity_boundary_interaction"]) == set(IDENTITIES)
    assert result["boundary_interaction_interval"]["replicates"] == 10000


def test_bootstrap_artifacts_land_where_the_inventory_names_them(sealed, drivers, capsys):
    for stage in ("primary", "temporal", "context"):
        drivers["run_primary_analysis"].main(
            ["--stage", stage, "--out", str(sealed["results"])]
        )
    capsys.readouterr()
    written = sorted(p.name for p in (sealed["results"] / "bootstrap").glob("*.json"))
    # The estimand name is carried verbatim: S_i and Dpartial_i are the frozen
    # identifiers of 8.10.3, and case-folding them would make the artifact name
    # ambiguous about which estimand it holds.
    assert written == [
        "a14_Dopaque_i.json",
        "a14_Dpartial_i.json",
        "a14_S_i.json",
        "a15_CURRENT_MINUS_PREVIOUS_VS_CURRENT.json",
        "a15_TWO_FRAME_CONCAT_VS_CURRENT.json",
        "a16_BOUNDARY_INTERACTION.json",
    ]


# --------------------------------------------------------------------------
# A11 -> A19 dataflow
# --------------------------------------------------------------------------


def test_a11_to_a19_dataflow_integration(sealed, drivers, capsys):
    """Every stage's output is the next stage's input, at the canonical path."""
    results = sealed["results"]
    for stage in ("primary", "temporal", "context"):
        assert (
            drivers["run_primary_analysis"].main(
                ["--stage", stage, "--out", str(results)]
            )
            == 0
        )
    for stage in ("adjudication", "package"):
        rc = drivers["build_scientific_package"].main(
            ["--stage", stage, "--analysis", str(results)]
        )
        assert rc == 0, capsys.readouterr().err
    # A19 legitimately refuses to close here: this sandbox carries no real P2
    # and no real A8 cohort receipt, so conditions 1-3 cannot be met. What is
    # under test is that the conditions A13-A16 feed ARE met, and that A19
    # writes its receipt either way rather than failing silently.
    drivers["build_scientific_package"].main(
        ["--stage", "closure", "--analysis", str(results)]
    )
    capsys.readouterr()

    for name in (
        "PREDICTION_LOCK.json",
        "PREDICTION_LOCK.sha256",
        "baselines_receipt.json",
        "primary_results.json",
        "temporal_results.json",
        "context_age_results.json",
        "adjudication_receipt.json",
        "scientific_package_manifest.json",
        "STATISTICAL_REPORT.md",
        "EXPERIMENT_III_CLOSURE_RECEIPT.json",
        "FINAL_SCIENTIFIC_SUMMARY.md",
    ):
        assert (results / name).is_file(), f"{name} is missing from the results root"

    closure = json.loads((results / "EXPERIMENT_III_CLOSURE_RECEIPT.json").read_text())
    lock = json.loads((results / "PREDICTION_LOCK.json").read_text())
    primary = json.loads((results / "primary_results.json").read_text())
    baselines = json.loads((results / "baselines_receipt.json").read_text())

    # Condition 4: every number derives from the one sealed lock.
    assert primary["prediction_lock_sha256"] == lock["prediction_lock_sha256"]
    assert baselines["prediction_lock_sha256"] == lock["prediction_lock_sha256"]
    by_id = {entry["id"]: entry for entry in closure["closure_conditions"]}
    assert by_id[4]["met"] is True
    assert by_id[5]["met"] is True, "A19 must see A13's L0 control"
    assert closure["overall_pass_fail_verdict"] is None


def test_every_stage_exits_where_the_inventory_says_it_should(sealed, drivers, capsys):
    """A11-A19 canonical paths, checked against the authority's own inventory.

    ``stage_exit_check_fs`` stats the filesystem rather than comparing strings
    the caller supplied, so this is the check that would have caught the drift
    between ``analysis/primary_analysis.json`` and the inventory's
    ``results/primary_results.json``.
    """
    results = sealed["results"]
    root = sealed["root"].parents[1]          # the relocated repository root
    for stage in ("primary", "temporal", "context"):
        drivers["run_primary_analysis"].main(["--stage", stage, "--out", str(results)])
    for stage in ("adjudication", "package", "closure"):
        drivers["build_scientific_package"].main(
            ["--stage", stage, "--analysis", str(results)]
        )
    capsys.readouterr()

    # stage_exit_check_fs raises the artifact's own missing_blocker rather than
    # returning a list, so "it did not raise" is the assertion.
    for stage in ("A12", "A13", "A14", "A15", "A16", "A17"):
        report = stage_exit_check_fs(stage, root)
        assert report["present_count"] >= report["required_count"], stage
        assert report["filesystem_backed"] is True


def test_a18_traces_the_bootstrap_artifacts_it_packages(sealed, drivers, capsys):
    results = sealed["results"]
    for stage in ("primary", "temporal", "context"):
        drivers["run_primary_analysis"].main(["--stage", stage, "--out", str(results)])
    drivers["build_scientific_package"].main(["--stage", "package", "--analysis", str(results)])
    capsys.readouterr()
    package = json.loads((results / "scientific_package_manifest.json").read_text())
    traced = {entry["artifact"] for entry in package["traceability"]}
    assert any(name.startswith("bootstrap/") for name in traced), traced
    assert "primary_results.json" in traced
    assert "baselines_receipt.json" in traced
