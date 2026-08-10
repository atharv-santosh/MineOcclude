"""Focused validation for the visible-position resolution closeout package.

Checks only the three closeout artifacts and their agreement with the sealed
Task 1-5 outputs.  Nothing here refits, recaptures, or recomputes any scientific
result; every assertion reads frozen JSON.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
MVP_MANIFEST = (
    ROOT / "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)

TASK_FILES = (
    "development_freeze.json",
    "expanded_visibility_eligibility.json",
    "replication_inventory.json",
    "replication_authority_decision.json",
    "spatial_representation_ladder.json",
    "metric_decomposition.json",
    "six_layout_generalization.json",
    "runtime_benchmark.json",
    "capture_manifest.json",
    "expanded_activation_manifest.json",
    "within_layout_replication.json",
    "across_layout_generalization.json",
    "spatial_scramble_control.json",
    "grouped_target_null.json",
)
CLOSEOUT_FILES = (
    "final_adjudication.json",
    "provenance.json",
    "diagnostic_receipt.json",
)

FORBIDDEN_CLAIMS = (
    "uncertainty-aware belief",
    "hypothesis passed",
    "hypothesis failed",
    "retrospectively passed",
    "causal localization was established",
    "attention explains",
    "proven overfit",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _load(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def adjudication() -> dict:
    return _load("final_adjudication.json")


@pytest.fixture(scope="module")
def provenance() -> dict:
    return _load("provenance.json")


@pytest.fixture(scope="module")
def receipt() -> dict:
    return _load("diagnostic_receipt.json")


# ---------------------------------------------------------------------------
# Package completeness and parseability
# ---------------------------------------------------------------------------


def test_every_required_package_file_exists_and_parses():
    for name in TASK_FILES + CLOSEOUT_FILES:
        path = PACKAGE / name
        assert path.is_file(), name
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict), name


def test_package_contains_no_unexpected_or_large_files():
    present = {p.name for p in PACKAGE.iterdir() if p.is_file()}
    assert present == set(TASK_FILES) | set(CLOSEOUT_FILES), sorted(
        present.symmetric_difference(set(TASK_FILES) | set(CLOSEOUT_FILES))
    )
    for path in PACKAGE.iterdir():
        assert path.is_file()
        assert path.suffix == ".json", path.name
        assert path.stat().st_size < 8_000_000, path.name


def test_closeout_artifacts_are_compact():
    for name in CLOSEOUT_FILES:
        assert (PACKAGE / name).stat().st_size < 200_000, name


# ---------------------------------------------------------------------------
# Recorded hashes match current files
# ---------------------------------------------------------------------------


def test_provenance_package_hashes_match_current_files(provenance):
    recorded = provenance["package_file_identities"]
    assert set(recorded) == set(TASK_FILES)
    for name, entry in recorded.items():
        path = PACKAGE / name
        assert entry["sha256"] == _sha256(path), name
        assert entry["byte_size"] == path.stat().st_size, name
        assert entry["path"] == str(path.relative_to(ROOT))


def test_provenance_cites_final_adjudication_by_hash(provenance):
    entry = provenance["final_adjudication"]
    assert entry["sha256"] == _sha256(PACKAGE / "final_adjudication.json")
    assert entry["byte_size"] == (PACKAGE / "final_adjudication.json").stat().st_size


def test_receipt_cites_adjudication_and_provenance_by_hash(receipt):
    artifacts = receipt["artifacts"]
    assert artifacts["final_adjudication"]["sha256"] == _sha256(
        PACKAGE / "final_adjudication.json"
    )
    assert artifacts["provenance"]["sha256"] == _sha256(PACKAGE / "provenance.json")
    assert sorted(artifacts["package_files"]) == sorted(TASK_FILES)


def test_provenance_cites_predecessor_and_mvp_by_hash(provenance):
    predecessor = provenance["predecessor_activation_authority"]["artifacts"][0]
    assert predecessor["sha256"] == _sha256(ROOT / predecessor["path"])
    assert provenance["predecessor_activation_authority"]["unchanged"] is True
    mvp = provenance["original_mvp_frozen_status"]["mvp_manifest"]
    assert mvp["sha256"] == _sha256(MVP_MANIFEST)


# ---------------------------------------------------------------------------
# Adjudication faithfully cites the frozen results
# ---------------------------------------------------------------------------


def test_adjudication_within_layout_numbers_match_task4(adjudication):
    within = _load("within_layout_replication.json")
    cited = adjudication["evidence_synthesis"]["E_high_dimensionality"][
        "within_layout_macro_r2"
    ]
    for name in ("COARSE_2x6", "FULL_TOKEN_GRID"):
        assert (
            cited[name]
            == within["representations"][name]["summary"]["equal_layout_macro_mean_r2"]
        )
    scramble_block = adjudication["control_a_spatial_scramble"]["within"]
    for name in ("COARSE_2x6", "FULL_TOKEN_GRID"):
        assert (
            scramble_block[name]["ordered_macro_r2"]
            == within["representations"][name]["summary"]["equal_layout_macro_mean_r2"]
        )


def test_adjudication_across_layout_numbers_match_task4(adjudication):
    across = _load("across_layout_generalization.json")
    cited = adjudication["evidence_synthesis"]["C_generalization"][
        "across_layout_macro_r2"
    ]
    for name in ("GLOBAL_MEAN", "COARSE_2x6", "FULL_TOKEN_GRID"):
        assert (
            cited[name]
            == across["representations"][name]["summary"]["equal_layout_macro_metrics"][
                "r2"
            ]["mean"]
        )


def test_adjudication_scramble_numbers_match_task5(adjudication):
    scramble = _load("spatial_scramble_control.json")
    for design in ("within", "across"):
        for name in ("COARSE_2x6", "FULL_TOKEN_GRID"):
            source = scramble["summary"][name][design]
            cited = adjudication["control_a_spatial_scramble"][design][name]
            assert cited["ordered_macro_r2"] == source["ordered_macro_r2"]
            assert (
                cited["scrambled_macro_r2_by_seed"]
                == source["scrambled_macro_r2_by_seed"]
            )
            assert (
                cited["ordered_minus_scrambled_by_seed"]
                == source["ordered_minus_scrambled_by_seed"]
            )
            # Every frozen seed must show a positive ordered advantage.
            assert all(
                value > 0.0
                for value in cited["ordered_minus_scrambled_by_seed"].values()
            )
    assert adjudication["control_a_spatial_scramble"]["frozen_seeds"] == [
        20260901,
        20260902,
        20260903,
        20260904,
        20260905,
    ]


def test_adjudication_null_numbers_match_task5(adjudication):
    null = _load("grouped_target_null.json")
    for name in ("COARSE_2x6", "FULL_TOKEN_GRID"):
        cited = adjudication["control_b_grouped_target_null"][name]
        source = null["summary"][name]
        for key, value in cited.items():
            assert value == source[key], (name, key)
        assert cited["null_replicate_count"] == 100
    assert adjudication["control_b_grouped_target_null"]["GROUPED_NULL_B"] == 100
    assert (
        adjudication["control_b_grouped_target_null"]["GROUPED_NULL_B_SELECTION_BASIS"]
        == "RUNTIME_ONLY"
    )
    assert (
        adjudication["control_b_grouped_target_null"][
            "GROUPED_NULL_B_FROZEN_BEFORE_RESULTS"
        ]
        is True
    )


def test_null_separation_conclusion_follows_from_the_recorded_distribution(
    adjudication,
):
    """The NOT_ESTABLISHED verdict must be entailed by the numbers, not asserted."""

    null = _load("grouped_target_null.json")
    for name in ("COARSE_2x6", "FULL_TOKEN_GRID"):
        summary = null["summary"][name]
        # Observed sits inside the null body, below q95 and below the maximum.
        assert summary["observed_across_layout_macro_r2"] < summary["null_q95"]
        assert summary["observed_across_layout_macro_r2"] < summary["null_maximum"]
        assert summary["upper_tail_empirical_statistic"] > 0.05
    assert adjudication["GROUPED_TARGET_NULL_SEPARATION"] == "NOT_ESTABLISHED"
    assert (
        adjudication["TARGET_SPECIFIC_VISIBLE_POSITION_DECODING"] == "NOT_ESTABLISHED"
    )
    assert (
        adjudication["CONFIRMATORY_VISIBLE_POSITION_SENSITIVITY"] == "NOT_ESTABLISHED"
    )


def test_spatial_identity_verdict_matches_task5_artifact(adjudication):
    scramble = _load("spatial_scramble_control.json")
    source = scramble["spatial_identity_classification"]
    assert (
        adjudication["STABLE_SPATIAL_IDENTITY_MATTERS"]
        == source["STABLE_SPATIAL_IDENTITY_MATTERS"]
    )
    assert (
        adjudication["STABLE_SPATIAL_IDENTITY_WITHIN_LAYOUT"]
        == source["STABLE_SPATIAL_IDENTITY_WITHIN_LAYOUT"]
    )
    assert (
        adjudication["STABLE_SPATIAL_IDENTITY_ACROSS_LAYOUT"]
        == source["STABLE_SPATIAL_IDENTITY_ACROSS_LAYOUT"]
    )


def test_task4_classifications_are_carried_through_unchanged(adjudication):
    across = _load("across_layout_generalization.json")
    classifications = across["classifications"]
    assert (
        adjudication["TOKEN_PRESERVING_READOUT_GENERALIZES"]
        == classifications["token_preserving_readout_generalizes"]
    )
    assert (
        adjudication["TRAJECTORY_VARIANCE_CLASS"]
        == classifications["trajectory_variance_class"]
    )
    assert (
        adjudication["TRAJECTORY_VARIANCE_DOMINANT"]
        == classifications["trajectory_variance_dominant"]
    )
    assert (
        adjudication["LAYOUT_VARIANCE_CLASS"]
        == classifications["layout_variance_class"]
    )
    assert (
        adjudication["LAYOUT_VARIANCE_DOMINANT"]
        == classifications["layout_variance_dominant"]
    )
    assert (
        adjudication["BOTH_TRAJECTORY_AND_LAYOUT_VARIANCE"]
        == classifications["both_trajectory_and_layout_variance"]
    )
    assert (
        adjudication["LAYOUT_SPECIFIC_REPRESENTATION_PLAUSIBLE"]
        == classifications["layout_specific_representation_plausible"]
    )


def test_required_adjudication_fields_have_the_declared_values(adjudication):
    expected = {
        "PROGRAM_STATUS": "EXPLORATORY_VISIBLE_POSITION_RESOLUTION_COMPLETE",
        "ORIGINAL_MVP_STATUS": (
            "INCONCLUSIVE_DUE_TO_UNESTABLISHED_MEASUREMENT_SENSITIVITY"
        ),
        "ORIGINAL_MVP_REINTERPRETED": False,
        "VISIBLE_POSITION_MEASUREMENT_SENSITIVITY": (
            "SUPPORTED_FOR_SPATIALLY_PRESERVING_EXPLORATORY_READOUT"
        ),
        "STABLE_SPATIAL_IDENTITY_MATTERS": True,
        "WITHIN_LAYOUT_REPLICATION": "STRONG",
        "ACROSS_LAYOUT_GENERALIZATION": "MIXED",
        "TOKEN_PRESERVING_READOUT_GENERALIZES": "UNCLEAR",
        "TARGET_METRIC_INSTABILITY_CONTRIBUTES": False,
        "TRAJECTORY_VARIANCE_CLASS": "MIXED_TRAJECTORY_EFFECT",
        "TRAJECTORY_VARIANCE_DOMINANT": False,
        "LAYOUT_VARIANCE_CLASS": "BOTH_TRAJECTORY_AND_LAYOUT_VARIANCE",
        "LAYOUT_VARIANCE_DOMINANT": False,
        "BOTH_TRAJECTORY_AND_LAYOUT_VARIANCE": True,
        "LAYOUT_SPECIFIC_REPRESENTATION_PLAUSIBLE": True,
        "SPATIAL_REPRESENTATION_BOTTLENECK_PLAUSIBLE": "Unclear",
        "HIGH_DIMENSIONAL_OVERFIT_PLAUSIBLE": "Unclear",
        "GROUPED_TARGET_NULL_SEPARATION": "NOT_ESTABLISHED",
        "TARGET_SPECIFIC_VISIBLE_POSITION_DECODING": "NOT_ESTABLISHED",
        "CONFIRMATORY_VISIBLE_POSITION_SENSITIVITY": "NOT_ESTABLISHED",
        "ORIGINAL_UNCERTAINTY_HYPOTHESIS_RESOLVED": False,
        "U1_U2_INTERPRETABLE": False,
        "STILL_INSUFFICIENT_EVIDENCE": True,
    }
    for key, value in expected.items():
        assert adjudication[key] == value, key
    assert receipt_fields_agree(adjudication)


def receipt_fields_agree(adjudication: dict) -> bool:
    receipt = _load("diagnostic_receipt.json")
    for key, value in receipt["adjudication"].items():
        assert adjudication[key] == value, key
    return True


# ---------------------------------------------------------------------------
# Interpretation boundaries
# ---------------------------------------------------------------------------


def test_closeout_makes_no_forbidden_claim():
    for name in CLOSEOUT_FILES:
        text = (PACKAGE / name).read_text(encoding="utf-8").lower()
        for phrase in FORBIDDEN_CLAIMS:
            # The explicit "statements_explicitly_not_made" list is the one
            # place these strings are permitted, as disavowals.
            occurrences = text.count(phrase.lower())
            if occurrences:
                document = _load(name)
                disavowed = json.dumps(
                    document.get("statements_explicitly_not_made", [])
                ).lower()
                assert disavowed.count(phrase.lower()) == occurrences, (name, phrase)


def test_original_mvp_status_is_preserved_not_rewritten(adjudication, provenance):
    assert adjudication["ORIGINAL_MVP_REINTERPRETED"] is False
    frozen = provenance["original_mvp_frozen_status"]
    assert (
        frozen["SCIENTIFIC_INTERPRETATION_STATUS"]
        == "NOT_INTERPRETABLE_POSITIVE_CONTROL_FAILED"
    )
    assert frozen["modified_by_this_program"] is False
    assert frozen["reinterpreted_by_this_program"] is False


def test_layer_selection_limitation_is_disclosed(adjudication, provenance):
    assert (
        adjudication["LAYER_SELECTION_STATUS"]
        == "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
    )
    assert (
        provenance["layer_selection_limitation"]["status"]
        == "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
    )


def test_major_null_limitation_is_stated_prominently(adjudication):
    block = adjudication["evidence_synthesis"]["D_target_specificity_and_null"]
    assert block["prominence"] == "MAJOR_LIMITATION"
    assert block["verdict"].startswith("The experiment does NOT establish")
    joined = " ".join(adjudication["limitations"]).lower()
    assert "not clearly separated from the" in joined
    assert "audited grouped target null" in joined


def test_null_conservatism_and_fixed_points_are_disclosed(adjudication, provenance):
    conservatism = adjudication["control_b_grouped_target_null"]["conservatism"]
    assert "51" in conservatism and "1,071" in conservatism
    joined = " ".join(provenance["limitations"]).lower()
    assert "fixed points" in joined
    assert "singleton audited length stratum" in joined


# ---------------------------------------------------------------------------
# Predeclared-criterion provenance
# ---------------------------------------------------------------------------


def test_predeclared_criterion_clarification_is_disclosed_with_counterfactual(
    provenance,
):
    note = provenance["predeclared_criterion_clarification"]
    assert note["classification"] == "PRE_OUTCOME_INTERPRETATION_CLARIFICATION"
    assert note["timing_substantiated"] is True
    assert len(note["timing_evidence"]) >= 3
    qualifications = " ".join(note["qualifications_disclosed"]).lower()
    # The material consequence of the change must be stated, not hidden.
    assert "unclear rather than true" in qualifications
    assert "macro scramble outcomes were already known" in qualifications
    assert note["both_criteria_reported"]


def test_both_consistency_criteria_remain_recomputable_from_task5():
    scramble = _load("spatial_scramble_control.json")
    evidence = scramble["spatial_identity_classification"]["evidence"]
    for design in ("within", "across"):
        entry = evidence[design]
        assert set(entry["layout_majority_consistent_by_representation"]) == {
            "COARSE_2x6",
            "FULL_TOKEN_GRID",
        }
        assert set(entry["every_fold_directionally_consistent_by_representation"]) == {
            "COARSE_2x6",
            "FULL_TOKEN_GRID",
        }
    # Applied rule holds; the stricter original rule does not. Both are visible.
    assert all(
        all(evidence[d]["layout_majority_consistent_by_representation"].values())
        for d in ("within", "across")
    )
    assert not all(
        all(
            evidence[d][
                "every_fold_directionally_consistent_by_representation"
            ].values()
        )
        for d in ("within", "across")
    )


# ---------------------------------------------------------------------------
# Next direction
# ---------------------------------------------------------------------------


def test_next_direction_is_the_two_component_combination(adjudication, receipt):
    direction = adjudication["next_project_direction"]
    assert direction["selection"] == "E_COMBINATION"
    components = {entry["component"] for entry in direction["components"]}
    assert components == {"MEASUREMENT_PATH", "TARGET_TRAJECTORY_DESIGN"}
    joined = json.dumps(direction).lower()
    assert "coarse_2x6" in joined
    assert "direction, timing, speed, starting point" in joined
    assert "do not collect more trajectories that merely repeat" in joined
    assert receipt["next_project_direction"] == "E_COMBINATION"


# ---------------------------------------------------------------------------
# Repository hygiene
# ---------------------------------------------------------------------------


def test_no_large_or_binary_artifacts_are_in_the_worktree():
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    entries = [line[3:].strip().strip('"') for line in status if line[3:].strip()]
    for entry in entries:
        assert not entry.endswith(
            (".npy", ".npz", ".pt", ".ckpt", ".jar", ".mp4")
        ), entry
        assert "sagemaker-nvme" not in entry, entry
        path = ROOT / entry
        if path.is_file():
            assert path.stat().st_size < 8_000_000, entry


def test_provenance_records_external_tensor_roots_outside_git(provenance):
    roots = provenance["external_tensor_roots"]
    for key in (
        "task3_activation_root",
        "original_six_activation_root",
        "task4_feature_cache_root",
        "task5_runtime_root",
    ):
        assert roots[key].startswith("/mnt/sagemaker-nvme/"), key
    assert provenance["large_tensors_in_git"] is False
    for entry in roots["feature_cache_identities"].values():
        assert entry["path"].startswith("/mnt/sagemaker-nvme/")
        assert len(entry["sha256"]) == 64
