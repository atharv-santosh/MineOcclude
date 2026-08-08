"""Focused tests for Person D's 66-cell production path.

Covers the additive frame-handoff successor, the removal of ten-pilot
pinning from the production path, Person B-owned admission, fold
integrity, and the published production package's own integrity
(prediction/metric cardinality, deterministic regeneration, the D->B
handoff, and U4 remaining unpromoted).

The published package is real evidence produced from Person A/B/C bytes.
Where those bytes are not present on the machine running the suite, the
package-integrity tests still run -- they read the committed package --
while the tests that need the upstream artifacts skip explicitly rather
than silently passing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mineocclude.baselines import frame_handoff_v0_3 as fh3
from mineocclude.baselines import production_universe_66_cell_v0_1 as pu66
from mineocclude.baselines.baseline_family_input_v0_2 import (
    FROZEN_BASELINE_FAMILY_IDS,
    FROZEN_PILOT_IDS,
)
from mineocclude.baselines.baseline_metrics_66_cell_v0_1 import (
    COMPARISON_CLASS_BY_FAMILY,
    U1_TARGET,
    U2_TARGET,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "docs" / "status" / "person_d_66_cell_production_baselines_v0_1"

DETERMINISTIC_ARTIFACTS = (
    "authority_verification_receipt.json",
    "execution_universe.json",
    "prediction_manifest.json",
    "baseline_metrics.json",
    "d_to_b_production_baseline_handoff.json",
)


def _load(name: str) -> dict:
    return json.loads((PACKAGE_ROOT / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Ten-pilot pinning is gone from the production path
# --------------------------------------------------------------------------


def _executable_lines(path: Path) -> str:
    """Source with comments and docstrings stripped.

    The successor modules *discuss* the ten-pilot pinning in prose -- that
    is the point of an additive successor. What must not survive is any
    executable reference to it, so the check is against code, not text.
    """

    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body.pop(0)
    return ast.unparse(tree)


def test_frame_handoff_v0_3_has_no_executable_ten_pilot_pinning():
    source = _executable_lines(
        REPO_ROOT / "src" / "mineocclude" / "baselines" / "frame_handoff_v0_3.py"
    )
    assert "FROZEN_PILOT_IDS" not in source
    assert not hasattr(fh3, "FROZEN_PILOT_IDS")


def test_production_universe_has_no_executable_ten_pilot_pinning():
    source = _executable_lines(
        REPO_ROOT
        / "src"
        / "mineocclude"
        / "baselines"
        / "production_universe_66_cell_v0_1.py"
    )
    assert "FROZEN_PILOT_IDS" not in source
    assert not hasattr(pu66, "FROZEN_PILOT_IDS")


def test_production_runner_has_no_executable_ten_pilot_pinning():
    source = _executable_lines(
        REPO_ROOT / "scripts" / "run_person_d_66_cell_production_baselines.py"
    )
    assert "FROZEN_PILOT_IDS" not in source


def test_ten_pilot_authority_is_retained_unmodified_as_history():
    # The predecessor must still exist and still be pinned to its own
    # historical scope: the successor is additive, not a replacement.
    from mineocclude.baselines import frame_handoff_v0_2 as fh2

    assert fh2.REQUIRED_FRAME_ARTIFACT_COUNT == 1695
    assert len(FROZEN_PILOT_IDS) == 10
    assert fh2.PERSON_A_FRAME_HANDOFF_COMMIT != fh3.PERSON_A_66_CELL_COMMIT


def test_successor_binds_the_66_cell_scope():
    assert fh3.REQUIRED_FRAME_ARTIFACT_COUNT == 2468
    assert fh3.REQUIRED_TRAJECTORY_COUNT == 66
    assert fh3.PERSON_A_66_CELL_COMMIT == "3384cbfed92f069236d68746f2308ec76f1a4124"
    assert fh3.PERSON_C_66_CELL_COMMIT == "3846230a4f141a8a55084eeaaa040f9a10cfc408"
    assert pu66.PERSON_B_66_CELL_COMMIT == (
        "25e09cb605699cdcb00dec1fbb1726977bec55e0"
    )


# --------------------------------------------------------------------------
# Pixel-input contract
# --------------------------------------------------------------------------


def test_pixel_contract_binds_only_raw_pixel_to_person_a_payloads():
    contract = fh3.build_pixel_input_contract()
    assert contract["families_consuming_pixels"] == ["raw_pixel"]
    assert set(contract["families_consuming_no_pixels"]) == set(
        FROZEN_BASELINE_FAMILY_IDS
    ) - {"raw_pixel"}
    authority = contract["raw_pixel_input_authority"]
    assert authority["producer_role"] == "person_a"
    assert authority["shape_chw"] == [3, 224, 384]
    assert authority["dtype"] == "float32"
    assert authority["channel_order"] == "RGB"
    assert authority["layout"] == "CHW"
    assert authority["value_range_inclusive"] == [-1.0, 1.0]
    assert authority["person_d_introduces_no_further_transform"] is True


def test_canonical_png_is_the_hash_chain_head_not_the_feature_representation():
    contract = fh3.build_pixel_input_contract()
    chain = {stage["stage"]: stage for stage in contract["source_hash_chain"]}
    png = chain["person_c_canonical_png_640x360_rgb"]
    assert png["is_scientific_pixel_authority"] is True
    assert png["mp4_permitted_as_pixel_source"] is False
    model_facing = chain["person_a_model_facing_384x224_chw_float32"]
    assert model_facing["is_raw_pixel_feature_representation"] is True
    assert "person_c_canonical_png_640x360" in contract["not_used_as_raw_pixel_features"]


def test_mp4_is_never_a_permitted_pixel_source():
    assert fh3.MP4_PERMITTED_AS_PIXEL_SOURCE is False


# --------------------------------------------------------------------------
# Person B-owned admission
# --------------------------------------------------------------------------


def test_admission_selector_is_person_b_owned():
    assert pu66.ADMISSION_SELECTOR == "status == 'accepted'"
    assert pu66.REQUIRED_ADMITTED_ANALYSIS_ROW_COUNT == 662
    assert pu66.REQUIRED_EXCLUDED_ANALYSIS_ROW_COUNT == 1806
    assert pu66.REQUIRED_MODEL_FRAME_KEY_COUNT == 2468
    assert (
        pu66.REQUIRED_ADMITTED_ANALYSIS_ROW_COUNT
        + pu66.REQUIRED_EXCLUDED_ANALYSIS_ROW_COUNT
        == pu66.REQUIRED_MODEL_FRAME_KEY_COUNT
    )


def test_superseded_984_row_admission_is_never_used():
    assert pu66.SUPERSEDED_PREACTIVATION_ADMITTED_ROW_COUNT == 984
    assert (
        pu66.SUPERSEDED_PREACTIVATION_ADMITTED_ROW_COUNT
        != pu66.REQUIRED_ADMITTED_ANALYSIS_ROW_COUNT
    )


def test_every_person_b_exclusion_reason_is_declared():
    expected = {
        "no_object_control_not_oracle_eligible",
        "ambiguous_geometry_edge_convention",
        "visibility_channel_disagreement",
        "outside_frozen_condition_selection",
    }
    assert expected <= set(pu66.EXCLUSION_REASONS)


def test_x_true_is_declared_scoring_only():
    assert "x_true_blocks" in pu66.PERSON_B_SCORING_ONLY_FIELDS


def test_accounting_verifier_rejects_a_changed_admission_selector():
    handoff = {
        "eligible_baseline_universe": {
            "admitted_analysis_row_count": 1,
            "excluded_analysis_row_count": 0,
            "row_identity_source": {"eligible_rows_selector": "status != 'excluded'"},
            "join_key": ["trajectory_id", "model_frame_idx"],
        },
        "excluded_counts_by_reason": [],
    }
    rows = [
        {
            "trajectory_id": "t",
            "model_frame_idx": 0,
            "status": "accepted",
            "fold_idx": 0,
            "layout_id": "layout_01",
            "control_type": "core_regime_a",
            "geometric_ambiguous": False,
            "exclusion_reason": None,
        }
    ]
    errors = pu66.verify_person_b_accounting(
        row_universe=rows, oracle_targets=[], handoff=handoff
    )
    assert any("admission_selector_changed" in error for error in errors)


def test_fold_verifier_rejects_a_layout_spanning_two_folds():
    rows = [
        {"trajectory_id": "t1", "model_frame_idx": 0, "fold_idx": 0, "layout_id": "L"},
        {"trajectory_id": "t2", "model_frame_idx": 0, "fold_idx": 1, "layout_id": "L"},
    ]
    manifest = {
        "memberships": [
            {"trajectory_id": "t1", "model_frame_idx": 0, "fold_idx": 0},
            {"trajectory_id": "t2", "model_frame_idx": 0, "fold_idx": 1},
        ]
    }
    errors = pu66.verify_fold_manifest_agreement(
        row_universe=rows, fold_manifest=manifest
    )
    assert any("layout_spans_multiple_folds" in error for error in errors)


# --------------------------------------------------------------------------
# Published package integrity
# --------------------------------------------------------------------------


def test_package_is_published():
    assert PACKAGE_ROOT.is_dir()
    for name in DETERMINISTIC_ARTIFACTS + ("sha256_inventory.json",):
        assert (PACKAGE_ROOT / name).is_file(), name


def test_inventory_hashes_match_the_published_bytes():
    import hashlib

    inventory = _load("sha256_inventory.json")
    for name, expected in inventory["artifact_sha256"].items():
        raw = (PACKAGE_ROOT / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected, name
    assert inventory["artifact_count"] == len(inventory["artifact_sha256"])
    # Runtime-bearing artifacts must stay out of the deterministic set.
    assert "execution_receipt.json" not in inventory["artifact_sha256"]


def test_execution_universe_reconciles_exactly_to_person_b():
    universe = _load("execution_universe.json")
    assert universe["total_model_frame_key_count"] == 2468
    assert universe["trajectory_count"] == 66
    assert universe["admitted_row_count"] == 662
    assert universe["excluded_row_count"] == 1806
    assert universe["reconciliation_mismatch_count"] == 0
    assert universe["admission_authority"]["owner_role"] == "person_b"
    assert universe["admission_authority"]["person_d_infers_no_admission"] is True
    assert sum(universe["counts_by_fold"].values()) == 662
    assert sum(universe["counts_by_layout"].values()) == 662
    assert sum(universe["counts_by_control_type"].values()) == 662


def test_exclusion_reasons_are_preserved_with_their_counts():
    universe = _load("execution_universe.json")
    reasons = universe["excluded_counts_by_reason"]
    assert reasons["no_object_control_not_oracle_eligible"] == 360
    assert reasons["ambiguous_geometry_edge_convention"] == 42
    assert reasons["visibility_channel_disagreement"] == 370
    assert reasons["outside_frozen_condition_selection"] == 1034
    assert sum(reasons.values()) == 1806


def test_prediction_cardinality_is_consistent():
    manifest = _load("prediction_manifest.json")
    records = manifest["records"]
    assert manifest["prediction_row_count"] == len(records)
    assert (
        manifest["applicable_prediction_count"]
        + manifest["non_applicable_prediction_count"]
        == len(records)
    )
    executed = [
        family
        for family, status in manifest["family_status"].items()
        if status["status"] == "completed"
    ]
    # Two targets per admitted row, per executed family.
    assert len(records) == len(executed) * 2 * manifest["admitted_row_count"]


def test_every_non_applicable_prediction_carries_a_reason_and_no_number():
    manifest = _load("prediction_manifest.json")
    for record in manifest["records"]:
        if record["applicable"]:
            assert record["prediction"] is not None
            assert record["reason"] is None
        else:
            assert record["prediction"] is None
            assert record["reason"]


def test_predictions_only_ever_cover_admitted_rows():
    manifest = _load("prediction_manifest.json")
    universe = _load("execution_universe.json")
    keys = {(r["trajectory_id"], r["model_frame_idx"]) for r in manifest["records"]}
    assert len(keys) == universe["admitted_row_count"]


def test_oracle_targets_are_declared_evaluation_only():
    manifest = _load("prediction_manifest.json")
    assert manifest["oracle_targets_used_only_for_evaluation"] is True


def test_metric_cardinality_and_authority():
    metrics = _load("baseline_metrics.json")
    assert metrics["aggregate_result_count"] == metrics["family_metric_count"]
    assert metrics["fold_result_count"] == sum(
        len(entry["per_fold"]) for entry in metrics["family_metrics"]
    )
    authority = metrics["metric_authority"]
    assert authority["owner_role"] == "person_b"
    assert authority["analysis_arithmetic_dtype"] == "float64"
    assert authority["person_d_created_no_threshold"] is True
    assert authority["person_d_applied_no_threshold"] is True
    assert authority["permutation_seed"] == 20260720
    assert authority["bootstrap_seed"] == 20260721


def test_every_family_metric_declares_its_comparison_class():
    metrics = _load("baseline_metrics.json")
    for entry in metrics["family_metrics"]:
        assert entry["comparison_class"] == COMPARISON_CLASS_BY_FAMILY[
            entry["family_id"]
        ]
        assert entry["target_name"] in (U1_TARGET, U2_TARGET)


def test_unavailable_metrics_state_a_reason_rather_than_a_number():
    metrics = _load("baseline_metrics.json")
    for entry in metrics["family_metrics"]:
        for block in entry["aggregate"].values():
            if isinstance(block, dict) and block.get("available") is False:
                assert block.get("reason")


def test_privileged_ceiling_is_labeled_and_not_a_fair_competitor():
    metrics = _load("baseline_metrics.json")
    ceiling = [
        entry
        for entry in metrics["family_metrics"]
        if entry["family_id"] == "known_q_analytic"
    ]
    assert ceiling
    assert ceiling[0]["comparison_class"] == "privileged_oracle_ceiling"


def test_floor_comparisons_are_not_probe_comparisons():
    metrics = _load("baseline_metrics.json")
    assert metrics["floor_comparisons"]
    for comparison in metrics["floor_comparisons"]:
        assert comparison["is_probe_comparison"] is False
        assert comparison["floor_family_id"] == "grouped_shuffled"
    blocked = {entry["metric"] for entry in metrics["not_computed"]}
    assert any("baseline_comparison" in metric for metric in blocked)


def test_scored_rows_never_exceed_the_admitted_universe():
    metrics = _load("baseline_metrics.json")
    for entry in metrics["family_metrics"]:
        accounting = entry["row_accounting"]
        assert accounting["scored_rows"] <= 662
        assert (
            accounting["applicable_rows"] + accounting["non_applicable_rows"]
            == accounting["emitted_rows"]
        )
        assert entry["aggregate"]["scored_row_count"] == accounting["scored_rows"]


# --------------------------------------------------------------------------
# D -> B handoff and U4 status
# --------------------------------------------------------------------------


def test_d_to_b_handoff_binds_every_input_authority():
    handoff = _load("d_to_b_production_baseline_handoff.json")
    authorities = handoff["input_authorities"]
    assert authorities["person_a_commit"] == fh3.PERSON_A_66_CELL_COMMIT
    assert authorities["person_b_commit"] == pu66.PERSON_B_66_CELL_COMMIT
    assert authorities["person_c_commit"] == fh3.PERSON_C_66_CELL_COMMIT
    assert (
        authorities["person_a_frame_manifest_sha256"]
        == fh3.PERSON_A_FRAME_MANIFEST_SHA256
    )
    assert (
        authorities["person_b_to_d_handoff_sha256"] == pu66.PERSON_B_TO_D_HANDOFF_SHA256
    )
    assert handoff["row_universe"]["admitted_analysis_row_count"] == 662
    assert handoff["row_universe"]["reconciliation_mismatch_count"] == 0
    assert handoff["frame_handoff_successor"]["predecessor_retained_unmodified"] is True
    assert (
        handoff["frame_handoff_successor"]["frozen_pilot_ids_in_production_path"]
        is False
    )


def test_handoff_reports_any_family_that_did_not_execute():
    handoff = _load("d_to_b_production_baseline_handoff.json")
    executed = set(handoff["families_executed"])
    not_executed = set(handoff["families_not_executed"])
    assert executed | not_executed == set(FROZEN_BASELINE_FAMILY_IDS)
    assert not executed & not_executed
    for family, status in handoff["families_not_executed"].items():
        assert status["status"] in ("blocked", "failed", "absent")
        assert status.get("reason")
    assert handoff["consumable_without_further_person_d_implementation"] == (
        not not_executed
    )


def test_a_blocked_family_names_a_host_capacity_cause_not_a_missing_input():
    manifest = _load("prediction_manifest.json")
    for family, status in manifest["family_status"].items():
        if status["status"] != "blocked":
            continue
        assert status["blocker_kind"] == "host_capacity_not_missing_input"
        assert status["all_inputs_present"] is True
        assert status["required_free_bytes"] > 0
        assert status["remediation"]


def test_u4_control_manifest_remains_unpromoted():
    handoff = _load("d_to_b_production_baseline_handoff.json")
    u4 = handoff["u4_status"]
    assert u4["control_manifest_frozen"] is False
    assert u4["supplemental_capture_required"] is True
    assert "VALID_TERMINAL_REVEAL_COUNT = 0" in u4["reason"]


def test_the_prior_provisional_u4_manifest_is_still_synthetic():
    prior = (
        REPO_ROOT
        / "docs"
        / "status"
        / "person_d_phase6to8_completion_v0_1"
        / "step7_1_u4_control_manifest.json"
    )
    document = json.loads(prior.read_text(encoding="utf-8"))
    assert document["evidence_kind"] == "synthetic"


def test_authority_receipt_records_every_verified_artifact():
    receipt = _load("authority_verification_receipt.json")
    assert receipt["all_verified"] is True
    assert receipt["artifact_count"] == 10
    for artifact in receipt["artifacts"]:
        assert artifact["verified"] is True
        assert artifact["actual_sha256"] == artifact["expected_sha256"]
        assert artifact["owner_role"] in ("person_a", "person_b", "person_c")


def test_superseded_admission_difference_is_reported_not_hidden():
    receipt = _load("authority_verification_receipt.json")
    difference = receipt["superseded_admission_difference"]
    assert difference["person_a_frame_manifest_accepted_count"] == 984
    assert difference["person_b_row_universe_accepted_count"] == 662
    assert difference["narrowed_by"] == 322
    assert difference["disagreeing_key_count"] == 322
    assert difference["authority_used_for_admission"] == (
        "person_b_row_universe_records"
    )


# --------------------------------------------------------------------------
# Deterministic regeneration (requires the upstream authority bytes)
# --------------------------------------------------------------------------


def _authority_root() -> Path | None:
    import os

    raw = os.environ.get("PERSON_D_66_AUTHORITY_ROOT")
    if not raw:
        return None
    root = Path(raw)
    return root if root.is_dir() else None


def test_package_regenerates_byte_identically(tmp_path):
    import hashlib
    import importlib.util
    import sys as _sys

    root = _authority_root()
    if root is None:
        pytest.skip(
            "set PERSON_D_66_AUTHORITY_ROOT to the verified A/B/C artifact "
            "directory to re-run the real regeneration check"
        )
    spec = importlib.util.spec_from_file_location(
        "run_person_d_66_cell_production_baselines",
        REPO_ROOT / "scripts" / "run_person_d_66_cell_production_baselines.py",
    )
    module = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    module.run(root, Path(fh3.PERSON_A_EXTERNAL_FRAME_ROOT), tmp_path)
    for name in DETERMINISTIC_ARTIFACTS:
        published = hashlib.sha256((PACKAGE_ROOT / name).read_bytes()).hexdigest()
        regenerated = hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        assert published == regenerated, name
