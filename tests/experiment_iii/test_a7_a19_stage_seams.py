"""The real CLI/driver seams for the terminal III-A stages A7-A19.

These stages were unreachable before this checkpoint: A7 and A9 refused
unconditionally, A8 and A11 had no entrypoint file at all, and A15, A16, A17 and
A19 were named as *stages of* existing drivers that had exactly one mode. The
engines beneath them were largely fine, which is the trap: a suite that only
exercised helper modules reported healthy coverage over a pipeline that could
not be run end to end.

So these tests drive the **actual argv seams** -- ``main(argv)`` and subprocess
invocations of the committed entrypoints -- and assert on the printed contract,
not on internal call results. Everything here is admission, counts, ordering and
refusal; no production scientific outcome exists and none is produced.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mineocclude.experiment_iii.a7_production import (
    EXPECTED_CAPTURES,
    EXPECTED_FRAMES,
    EXPECTED_TARGET_ROWS,
    admit_production,
    production_specs,
    verify_no_pilot_identity,
)
from mineocclude.experiment_iii.a9_production_extraction import (
    PRODUCTION_ARRAYS,
    PRODUCTION_FORWARDS,
    assert_production_identity,
    expected_extraction_counts,
)
from mineocclude.experiment_iii.authority import (
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_IDS,
    verify_authority_binding,
)
from mineocclude.experiment_iii.cohort_closure import (
    MINIMUM_FOR_GRADED_INFERENCE,
    attrition_branch,
    close_cohort,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.p0_analysis import load_selected_ladder
from mineocclude.experiment_iii.schema import read_jsonl

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPOSITORY_ROOT / "scripts" / "experiment_iii"
DOCS = REPOSITORY_ROOT / "docs" / "experiment_iii"
SUPERSEDED_P2 = (
    DOCS
    / "superseded_evidence"
    / "p2_a2734b31_superseded_before_production"
    / "P2_FREEZE_PACKAGE.json"
)


def run_cli(script: str, *argv: str) -> subprocess.CompletedProcess:
    """Invoke a committed entrypoint exactly as an operator would."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *argv],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        env={**__import__("os").environ,
             "PYTHONPATH": str(REPOSITORY_ROOT / "src")},
    )


# --------------------------------------------------------------------------
# A7 admission
# --------------------------------------------------------------------------


def test_a7_refuses_a_missing_p2(tmp_path: Path) -> None:
    with pytest.raises(ExperimentIIIError) as error:
        admit_production(tmp_path / "absent.json")
    assert error.value.blocker == "P2_PREREQUISITE_NOT_PASSED"


@pytest.mark.skipif(not SUPERSEDED_P2.is_file(), reason="no superseded P2 banked")
def test_a7_refuses_the_superseded_p2_that_froze_a_placeholder() -> None:
    """The specific package that must never authorize production again.

    ``a2734b31`` reported PASS while binding ``bootstrap_seed = "FROZEN_IN_P2"``.
    It is retained as historical evidence and is exactly the artifact an operator
    might reach for by habit, so its refusal is pinned by digest.
    """
    body = json.loads(SUPERSEDED_P2.read_text(encoding="utf-8"))
    assert body["package_sha256"] == (
        "a2734b31fb8ac5b4987f2ce13a3ff11328b8589fb93a65d1b702b400eb739687"
    )
    with pytest.raises(ExperimentIIIError) as error:
        admit_production(SUPERSEDED_P2)
    assert error.value.blocker in {
        "P2_BINDING_MISMATCH",
        "P2_PREREQUISITE_NOT_PASSED",
        "PROVENANCE_AUTHORITY_DRIFT",
    }


def test_a7_execute_seam_refuses_and_says_so(tmp_path: Path) -> None:
    """The driver's own argv path, not the helper: it once always refused."""
    result = run_cli(
        "run_production_capture.py", "--execute", "--p2", str(tmp_path / "no.json")
    )
    assert result.returncode == 1
    assert "BLOCKER_CODE=P2_PREREQUISITE_NOT_PASSED" in result.stderr
    assert "A7_EXECUTED=false" in result.stderr


def test_a7_execute_is_no_longer_an_unconditional_refusal() -> None:
    """It must refuse for a *reason*, not because --execute is unimplemented."""
    source = (SCRIPTS / "run_production_capture.py").read_text(encoding="utf-8")
    assert "production capture is stage A7; it requires PRODUCTION_AUTHORIZED" not in source
    assert "_execute(args)" in source


# --------------------------------------------------------------------------
# A7 contract
# --------------------------------------------------------------------------


def test_a7_resolves_the_exact_frozen_production_matrix() -> None:
    rows = read_jsonl(DOCS / "cohort" / "production_identity_manifest.jsonl")
    ladder = load_selected_ladder(DOCS / "p0" / "P0_SELECTED_LADDER.json")
    specs, schedule, report = production_specs(rows, ladder)

    assert len(specs) == EXPECTED_CAPTURES == 125
    assert len({spec.capture_unit_id for spec in specs}) == 125
    assert sum(spec.frames for spec in specs) == EXPECTED_FRAMES == 22_500
    assert (
        sum(len(spec.target_model_frame_indices) for spec in specs)
        == EXPECTED_TARGET_ROWS
        == 2_375
    )
    assert sorted({spec.identity for spec in specs}) == sorted(PRODUCTION_IDENTITY_IDS)
    assert sorted({spec.condition.condition_id.value for spec in specs}) == [
        "L0", "L1", "L2", "L3", "L4"
    ]
    assert report["balanced_per_block"] and report["balanced_per_period"]
    assert report["wall_material_transitions"] <= report["max_wall_material_transitions"]

    directions: dict[str, int] = {}
    seen: set[str] = set()
    for spec in specs:
        if spec.identity not in seen:
            seen.add(spec.identity)
            directions[spec.direction] = directions.get(spec.direction, 0) + 1
    assert directions == {"LEFT_TO_RIGHT": 13, "RIGHT_TO_LEFT": 12}


def test_a7_refuses_a_pilot_identity_in_the_production_cohort() -> None:
    rows = read_jsonl(DOCS / "cohort" / "production_identity_manifest.jsonl")
    ladder = load_selected_ladder(DOCS / "p0" / "P0_SELECTED_LADDER.json")
    specs, _schedule, _report = production_specs(rows, ladder)

    class _Pilot:
        identity = PILOT_IDENTITY_IDS[0]

    with pytest.raises(ExperimentIIIError) as error:
        verify_no_pilot_identity([*specs, _Pilot()])
    assert error.value.blocker == "COHORT_PILOT_CONTAMINATION"


def test_a7_plans_ten_sentinel_checks() -> None:
    from mineocclude.experiment_iii.a7_production import ProductionCampaign

    rows = read_jsonl(DOCS / "cohort" / "production_identity_manifest.jsonl")
    ladder = load_selected_ladder(DOCS / "p0" / "P0_SELECTED_LADDER.json")
    specs, schedule, _report = production_specs(rows, ladder)
    campaign = ProductionCampaign(
        specs,
        output_root=REPOSITORY_ROOT / "data" / "experiment_iii" / "production" / "captures",
        ledger_path=REPOSITORY_ROOT / "data" / "experiment_iii" / "production" / "l.jsonl",
    )
    counts = campaign.expected_counts()
    assert counts == {
        "captures": 125,
        "frames": 22_500,
        "target_rows": 2_375,
        "identities": 25,
        "frames_per_capture": 180,
        "target_rows_per_capture": 19,
    }


# --------------------------------------------------------------------------
# A8
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "n,branch,graded",
    [
        (25, "NORMAL", True),
        (24, "REDUCED_PRECISION_WITH_CONSPICUOUS_DISCLOSURE", True),
        (15, "REDUCED_PRECISION_WITH_CONSPICUOUS_DISCLOSURE", True),
        (14, "NO_GRADED_INFERENTIAL_CLAIM", False),
        (0, "NO_GRADED_INFERENTIAL_CLAIM", False),
    ],
)
def test_a8_attrition_rule_is_exactly_the_frozen_one(n, branch, graded) -> None:
    result = attrition_branch(n)
    assert result["branch"] == branch
    assert result["graded_inferential_claim_permitted"] is graded
    if branch != "NORMAL":
        assert result["attrition_disclosure_required"] is True


def test_a8_boundary_is_fifteen() -> None:
    assert MINIMUM_FOR_GRADED_INFERENCE == 15
    assert attrition_branch(15)["graded_inferential_claim_permitted"] is True
    assert attrition_branch(14)["graded_inferential_claim_permitted"] is False


def test_a8_excludes_a_partial_identity_whole(tmp_path: Path) -> None:
    """Four of five conditions is not four-fifths of an identity."""
    rows = read_jsonl(DOCS / "cohort" / "production_identity_manifest.jsonl")
    # The namespace guard measures against ``root``; the ledger must sit inside
    # an Experiment III artifact root even in a temporary tree, which is the
    # point of the guard and not something a test should route around.
    ledger = tmp_path / "data" / "experiment_iii" / "production" / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    from mineocclude.experiment_iii.execution import HashChainLedger

    chain = HashChainLedger(ledger, root=tmp_path)
    partial = rows[0]["identity"]
    for condition in ("L0", "L1", "L2", "L3"):  # deliberately not L4
        chain.append(f"{partial}__{condition}", "COMPLETE")

    receipt = close_cohort(
        ledger_path=ledger,
        capture_root=tmp_path,
        identity_rows=rows,
        require_durable_receipt=False,
    )
    assert receipt["N_complete"] == 0
    assert receipt["partial_identities"] == [partial]
    assert receipt["partial_conditions_used"] is False
    assert receipt["analysable_units"] == 0
    assert receipt["imputed_cells"] == 0


def test_a8_refuses_a_pilot_unit_in_the_ledger(tmp_path: Path) -> None:
    rows = read_jsonl(DOCS / "cohort" / "production_identity_manifest.jsonl")
    ledger = tmp_path / "data" / "experiment_iii" / "production" / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    from mineocclude.experiment_iii.execution import HashChainLedger

    chain = HashChainLedger(ledger, root=tmp_path)
    chain.append(f"{PILOT_IDENTITY_IDS[0]}__L0", "COMPLETE")
    with pytest.raises(ExperimentIIIError) as error:
        close_cohort(
            ledger_path=ledger,
            capture_root=tmp_path,
            identity_rows=rows,
            require_durable_receipt=False,
        )
    assert error.value.blocker == "COHORT_PILOT_CONTAMINATION"


def test_a8_cli_seam_reports_its_verdict() -> None:
    result = run_cli("validate_capture_cohort.py")
    assert "A8_STATUS=" in result.stdout
    assert "N_COMPLETE=" in result.stdout
    assert "ATTRITION_BRANCH=" in result.stdout
    assert "MODEL_OUTCOME_CONSULTED=false" in result.stdout


# --------------------------------------------------------------------------
# A9
# --------------------------------------------------------------------------


def test_a9_runs_one_forward_per_target_row_not_six() -> None:
    counts = expected_extraction_counts()
    assert counts["forwards"] == PRODUCTION_FORWARDS == 2_375
    assert counts["arrays"] == PRODUCTION_ARRAYS == 750
    assert counts["one_forward_per_target_row"] is True
    # The mistake this guards: one forward per persisted array.
    assert counts["forwards"] * counts["units_per_capture"] == 14_250
    assert counts["forwards"] != 14_250


def test_a9_refuses_a_pilot_identity() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        assert_production_identity(PILOT_IDENTITY_IDS[0])
    assert error.value.blocker == "COHORT_PILOT_CONTAMINATION"
    assert_production_identity(PRODUCTION_IDENTITY_IDS[0])


def test_a9_forward_budget_refuses_an_excess() -> None:
    from mineocclude.experiment_iii.a9_production_extraction import (
        ProductionExtractionCampaign,
    )
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "data" / "experiment_iii" / "production").mkdir(parents=True)
        campaign = ProductionExtractionCampaign(
            [
                {
                    "capture_unit_id": f"{PRODUCTION_IDENTITY_IDS[0]}__L0",
                    "identity": PRODUCTION_IDENTITY_IDS[0],
                    "condition_id": "L0",
                    "unit_dir": root,
                    "seed": 1,
                    "source_capture_hash": "0" * 64,
                    "target_model_frame_indices": list(range(19)),
                }
            ],
            output_root=root,
            ledger_path=root / "data" / "experiment_iii" / "production" / "l.jsonl",
            extraction_spec_hash="0" * 64,
            namespace_root=root,
        )
        campaign.forwards = 19
        assert campaign.assert_forward_budget()["expected_forwards"] == 19
        campaign.forwards = 19 * 6
        with pytest.raises(ExperimentIIIError) as error:
            campaign.assert_forward_budget()
        assert error.value.blocker == "EXTRACTION_FORWARD_COUNT_EXCESS"


def test_a9_cli_seam_requires_an_a3_receipt() -> None:
    result = run_cli("run_extraction.py", "--execute")
    assert result.returncode == 1
    assert "BLOCKER_CODE=ENV_GPU_UNAVAILABLE" in result.stderr
    assert "A9_EXECUTED=false" in result.stderr


def test_a9_plan_mode_still_reports_the_frozen_arithmetic() -> None:
    result = run_cli("run_extraction.py", "--plan-only")
    assert result.returncode == 0
    assert "TOTAL_FORWARDS=2375" in result.stdout
    assert "ARRAYS_PER_CAPTURE=6" in result.stdout
    assert "MINEWORLD_INFERENCE_RUN=false" in result.stdout


# --------------------------------------------------------------------------
# A11
# --------------------------------------------------------------------------


def test_a11_cli_seam_emits_the_frozen_dimensions() -> None:
    result = run_cli("build_features.py", "--config-only")
    assert result.returncode == 0, result.stderr
    assert "A11_STATUS=PASS" in result.stdout
    assert "A11_DIM_CURRENT=24576" in result.stdout
    assert "A11_DIM_CURRENT_MINUS_PREVIOUS=24576" in result.stdout
    assert "A11_DIM_TWO_FRAME_CONCAT=49152" in result.stdout
    assert "A11_COARSE_GRID=2x6" in result.stdout
    assert "A11_TWO_FRAME_ORDER=PREVIOUS_FIRST_THEN_CURRENT" in result.stdout


def test_a11_entrypoint_exists_where_the_lifecycle_names_it() -> None:
    assert (SCRIPTS / "build_features.py").is_file()


# --------------------------------------------------------------------------
# A15 / A16 / A17 / A19 seams
# --------------------------------------------------------------------------


def test_a15_a16_stages_are_selectable_on_the_named_driver() -> None:
    result = run_cli("run_primary_analysis.py", "--help")
    assert result.returncode == 0
    assert "--stage" in result.stdout
    for stage in ("primary", "temporal", "context"):
        assert stage in result.stdout


def test_a15_refuses_a_bootstrap_seed_that_is_not_the_frozen_one(tmp_path: Path) -> None:
    """The seed is frozen in P2; a per-run override is not a knob."""
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"cells": [], "feature_block_hashes": {}}), encoding="utf-8")
    estimands = tmp_path / "estimands.json"
    estimands.write_text("{}", encoding="utf-8")
    result = run_cli(
        "run_primary_analysis.py",
        "--stage", "temporal",
        "--lock", str(lock),
        "--estimands", str(estimands),
        "--bootstrap-seed", "12345",
    )
    assert result.returncode == 1
    assert "STATS_BOOTSTRAP_SEED_MISMATCH" in result.stderr
    assert "8258108568742502015" in result.stderr


def test_a17_adjudication_stage_runs_the_seventeen_row_matrix() -> None:
    result = run_cli("build_scientific_package.py", "--stage", "adjudication")
    assert result.returncode == 0, result.stderr
    assert "A17_STATUS=PASS" in result.stdout
    assert "ADJUDICATION_MATRIX_ROWS=17" in result.stdout
    assert "PROHIBITED_CLAIM_PRESENT=false" in result.stdout


def test_a17_refuses_a_claim_outside_the_matrix() -> None:
    result = run_cli(
        "build_scientific_package.py",
        "--stage", "adjudication",
        "--claim", "the model maintains a calibrated Gaussian belief state in general",
    )
    assert result.returncode == 1
    assert "BLOCKER_CODE=" in result.stderr


def test_a19_closure_evaluates_eight_conditions_and_emits_no_verdict() -> None:
    result = run_cli("build_scientific_package.py", "--stage", "closure")
    assert "A19_CLOSURE_CONDITIONS=8" in result.stdout
    assert "EXPERIMENT_III_COMPLETE=" in result.stdout
    # No production evidence exists, so closure must NOT be declared.
    assert "EXPERIMENT_III_COMPLETE=false" in result.stdout
    assert result.returncode == 1
    assert "CLOSURE_CONDITION_UNMET" in result.stderr


def test_no_production_scientific_outcome_was_produced_by_these_tests() -> None:
    """The suite must not have created a production capture or activation."""
    production = REPOSITORY_ROOT / "data" / "experiment_iii" / "production"
    captures = list((production / "captures").glob("e3_t*")) if production.is_dir() else []
    activations = (
        list((production / "activations").glob("e3_t*")) if production.is_dir() else []
    )
    assert captures == []
    assert activations == []
