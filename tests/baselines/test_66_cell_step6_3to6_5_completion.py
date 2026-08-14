"""Tests for wiring the real 66-cell execution through Steps 4.5/6.3-6.5.

Like ``test_mvp_identity_v0_1.py`` and ``test_production_fold_contract_v0_1.py``,
this reads Person B's real row-universe and oracle-target records directly
via ``git show <commit>:<path>`` -- the same commit
(``pu66.PERSON_B_66_CELL_COMMIT``) every frozen hash constant in
``production_universe_66_cell_v0_1`` was already derived from -- never a
checkout, merge, or copy of that branch. The already-published real
prediction/metric package
(``docs/status/person_d_66_cell_production_baselines_v0_1/``) is read
directly from disk since it is already committed on this branch.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "docs" / "status" / "person_d_66_cell_production_baselines_v0_1"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "run_person_d_66_cell_step6_3to6_5_completion",
        REPO_ROOT / "scripts" / "run_person_d_66_cell_step6_3to6_5_completion.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()
pu66 = pytest.importorskip("mineocclude.baselines.production_universe_66_cell_v0_1")


def _read_git_blob(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=REPO_ROOT, capture_output=True, check=True,
    )
    return result.stdout


@pytest.fixture(scope="module")
def authority_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("authority66")
    (root / "row_universe_records.jsonl").write_bytes(
        _read_git_blob(pu66.PERSON_B_66_CELL_COMMIT, pu66.PERSON_B_ROW_UNIVERSE_RECORDS_PATH)
    )
    (root / "oracle_target_records.jsonl").write_bytes(
        _read_git_blob(pu66.PERSON_B_66_CELL_COMMIT, pu66.PERSON_B_ORACLE_TARGET_RECORDS_PATH)
    )
    return root


@pytest.fixture(scope="module")
def built(authority_root, tmp_path_factory) -> dict:
    output_root = tmp_path_factory.mktemp("step6_3to6_5_output")
    inventory = SCRIPT.build_all(output_root, authority_root, PACKAGE_ROOT)
    return {"output_root": output_root, "inventory": inventory}


def _artifact(built, name: str) -> dict:
    return json.loads((built["output_root"] / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Real-execution regression
# --------------------------------------------------------------------------


def test_inventory_declares_real_execution(built):
    inventory = built["inventory"]
    assert inventory["evidence_kind"] == "real"
    assert inventory["real_execution_performed"] is True
    assert inventory["cross_checked_against_published_predictions"] is True
    assert inventory["artifact_count"] == 6


def test_grouped_nulls_reconciles_to_published_family_status(built):
    document = _artifact(built, "step6_3_grouped_nulls.json")
    published = json.loads((PACKAGE_ROOT / "prediction_manifest.json").read_text(encoding="utf-8"))
    grouped_shuffled_status = published["family_status"]["grouped_shuffled"]

    assert document["evidence_kind"] == "real"
    assert document["null_row_count"] == grouped_shuffled_status["emitted_row_count"]
    assert (
        document["row_status_counts"]["available"]
        == grouped_shuffled_status["applicable_row_count"]
    )
    assert (
        document["row_status_counts"]["non_applicable"]
        == grouped_shuffled_status["non_applicable_row_count"]
    )
    universe = json.loads((PACKAGE_ROOT / "execution_universe.json").read_text(encoding="utf-8"))
    assert document["trajectory_count"] == universe["admitted_trajectory_count"]


def test_paired_comparisons_are_real_and_use_frozen_objective_pairs(built):
    u1 = _artifact(built, "step6_3_paired_comparisons_u1.json")
    u2 = _artifact(built, "step6_3_paired_comparisons_u2.json")

    assert u1["evidence_kind"] == "real"
    assert (u1["method_a"], u1["method_b"]) == ("last_seen", "grouped_shuffled")
    assert u1["objective"] == "U1"
    assert u1["requested_pair_count"] == 662

    assert u2["evidence_kind"] == "real"
    assert (u2["method_a"], u2["method_b"]) == ("time_only", "visible_history_q")
    assert u2["objective"] == "U2"
    assert u2["requested_pair_count"] == 662


def test_missingness_audit_passes_and_reconciles(built):
    document = _artifact(built, "step4_5_missingness_exclusion_report.json")
    published = json.loads((PACKAGE_ROOT / "prediction_manifest.json").read_text(encoding="utf-8"))

    assert document["evidence_kind"] == "real"
    assert document["audit_passed"] is True
    assert document["rows_missing_reason_code"] == []
    assert document["duplicate_emitted_rows"] == []
    assert document["totals"]["requested_predictions"] == published["prediction_row_count"]
    assert document["totals"]["available_predictions"] == published["applicable_prediction_count"]
    assert (
        document["totals"]["non_applicable_predictions"]
        == published["non_applicable_prediction_count"]
    )


def test_preliminary_report_real_sections_match_published_metrics(built):
    document = _artifact(built, "step6_4_preliminary_comparison_report.json")
    metrics = json.loads((PACKAGE_ROOT / "baseline_metrics.json").read_text(encoding="utf-8"))
    r2_by_family_target = {
        (entry["family_id"], entry["target_name"]): entry["aggregate"]["regression"]["r2"]
        for entry in metrics["family_metrics"]
    }

    assert document["evidence_kind"] == "real"
    sections_by_id = {s["section_id"]: s for s in document["sections"]}

    rendered_expectations = {
        "u1_vs_last_seen": ("last_seen", "mu_oracle_blocks"),
        "u1_vs_grouped_shuffled_floor": ("grouped_shuffled", "mu_oracle_blocks"),
        "u2_vs_time_only": ("time_only", "log_sigma_oracle"),
        "u2_vs_visible_history_spread": ("visible_history_q", "log_sigma_oracle"),
        "raw_pixel_comparison": ("raw_pixel", "mu_oracle_blocks"),
        "known_q_oracle_ceiling": ("known_q_analytic", "log_sigma_oracle"),
    }
    for section_id, (family, target) in rendered_expectations.items():
        section = sections_by_id[section_id]
        assert section["status"] == "rendered"
        assert section["values"][0]["value"] == pytest.approx(r2_by_family_target[(family, target)])
        assert section["values"][0]["source_sha256"]

    for section_id in ("visible_positive_control", "no_object_negative_control"):
        section = sections_by_id[section_id]
        assert section["status"] == "blocked"
        assert section["values"] == []
        assert section["blockers"]

    assert document["report_complete"] is False  # honest: two sections genuinely blocked


def test_result_lock_facts_match_published_manifest(built):
    document = _artifact(built, "step6_5_result_lock.json")
    published = json.loads((PACKAGE_ROOT / "prediction_manifest.json").read_text(encoding="utf-8"))
    universe = json.loads((PACKAGE_ROOT / "execution_universe.json").read_text(encoding="utf-8"))

    assert document["evidence_kind"] == "real"
    facts = document["facts"]
    assert facts["prediction_row_count"] == published["prediction_row_count"]
    assert facts["scored_row_count"] == published["applicable_prediction_count"]
    assert facts["non_applicable_row_count"] == published["non_applicable_prediction_count"]
    assert facts["missing_row_count"] == 0
    assert facts["accepted_trajectory_count"] == universe["admitted_trajectory_count"]
    assert (
        facts["excluded_trajectory_count"]
        == universe["trajectory_count"] - universe["admitted_trajectory_count"]
    )


def test_regeneration_is_byte_identical(authority_root, tmp_path_factory):
    first_root = tmp_path_factory.mktemp("first")
    second_root = tmp_path_factory.mktemp("second")
    SCRIPT.build_all(first_root, authority_root, PACKAGE_ROOT)
    SCRIPT.build_all(second_root, authority_root, PACKAGE_ROOT)

    first_files = sorted(p.name for p in first_root.iterdir())
    second_files = sorted(p.name for p in second_root.iterdir())
    assert first_files == second_files
    for name in first_files:
        assert (first_root / name).read_bytes() == (second_root / name).read_bytes(), name


# --------------------------------------------------------------------------
# Fail-closed cross-check
# --------------------------------------------------------------------------


def test_cross_check_rejects_a_real_applicability_divergence():
    from mineocclude.baselines.interface import BaselineRow

    fabricated_row = BaselineRow(
        trajectory_id="layout_01_ep12602",
        layout_id="layout_01",
        model_frame_idx=0,
        fold=3,
        regime="A",
        target_name="mu_oracle_blocks",
        baseline_name="last_seen",
        prediction=999.0,
        applicable=True,
        visibility=True,
        tau_seconds=0.0,
        v_scripted_blocks_per_s=1.0,
        q_scripted_blocks2_per_s=0.05,
        duration_seconds=3.0,
        config_hash="test",
        seed=1,
    )
    published_manifest = {
        "records": [
            {
                "baseline_family": "last_seen",
                "trajectory_id": "layout_01_ep12602",
                "model_frame_idx": 0,
                "target_name": "mu_oracle_blocks",
                "applicable": False,
                "prediction": None,
            }
        ]
    }
    with pytest.raises(ValueError, match="diverge"):
        SCRIPT._cross_check_against_published_predictions(
            {"last_seen": [fabricated_row]}, published_manifest
        )


def test_cross_check_tolerates_tiny_float_noise_across_environments():
    from mineocclude.baselines.interface import BaselineRow

    row = BaselineRow(
        trajectory_id="layout_01_ep12602",
        layout_id="layout_01",
        model_frame_idx=0,
        fold=3,
        regime="A",
        target_name="mu_oracle_blocks",
        baseline_name="last_seen",
        prediction=-1.9960816968767163,
        applicable=True,
        visibility=True,
        tau_seconds=0.0,
        v_scripted_blocks_per_s=1.0,
        q_scripted_blocks2_per_s=0.05,
        duration_seconds=3.0,
        config_hash="test",
        seed=1,
    )
    published_manifest = {
        "records": [
            {
                "baseline_family": "last_seen",
                "trajectory_id": "layout_01_ep12602",
                "model_frame_idx": 0,
                "target_name": "mu_oracle_blocks",
                "applicable": True,
                "prediction": -1.9960816968767132,
            }
        ]
    }
    SCRIPT._cross_check_against_published_predictions(
        {"last_seen": [row]}, published_manifest
    )  # must not raise
