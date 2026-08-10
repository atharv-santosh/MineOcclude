from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
SCRIPT = ROOT / "scripts/finalize_large_scale_no_wall_p4c.py"
SPEC = importlib.util.spec_from_file_location("p4c_actual_audit", SCRIPT)
assert SPEC and SPEC.loader
p4c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p4c)


def load(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text())


@pytest.fixture(scope="module")
def result():
    return p4c.compute()


def test_actual_capture_reconciles_exactly_to_frozen_v2(result):
    reconciliation = result["reconciliation"]
    assert reconciliation["status"] == "PASS"
    assert reconciliation["accepted"] == 120
    assert reconciliation["accepted_per_layout"] == {
        f"L{index:02d}": 20 for index in range(1, 7)
    }
    assert reconciliation["unique_spec_ids"] == 120
    assert reconciliation["unique_spec_hashes"] == 120
    assert reconciliation["unplanned_accepted_specs"] == 0
    assert reconciliation["missing_locked_specs"] == 0
    assert reconciliation["blocked_specs"] == 0
    assert reconciliation["raw_authority_durable"] is True


def test_actual_server_profiles_pass_frozen_similarity_gate(result):
    audit = result["audit"]
    similarity = audit["profile_similarity"]
    assert audit["status"] == "PASS"
    assert similarity["all_pairs"]["pair_count"] == 7140
    assert similarity["all_pairs"]["high_abs_r_ge_0_95_count"] == 130
    assert similarity["all_pairs"]["high_abs_r_ge_0_95_proportion"] == pytest.approx(
        0.018207282913165267
    )
    assert similarity["same_direction"]["pair_count"] == 3540
    assert similarity["opposite_direction"]["pair_count"] == 3600
    assert similarity["same_shape_class"]["pair_count"] == 300
    assert similarity["different_shape_class"]["pair_count"] == 6840
    assert similarity["all_pairs"]["high_abs_r_ge_0_95_proportion"] <= 0.10
    assert all(audit["component_gates"].values())


def test_simulator_live_equivalence_and_pilot_are_exact(result):
    qa = result["audit"]["simulated_vs_actual_qa"]
    pilot = result["pilot"]
    assert qa["trajectory_count"] == 120
    assert qa["row_count"] == 7200
    assert qa["maximum_absolute_error_blocks"] == 0.0
    assert qa["mean_absolute_error_blocks"] == 0.0
    assert qa["bounds_variance_similarity_or_acceptance_changed"] is False
    assert pilot["accepted"] == 12
    assert pilot["accepted_per_layout"] == {f"L{index:02d}": 2 for index in range(1, 7)}
    assert pilot["simulated_live_maximum_absolute_error_blocks"] == 0.0
    assert pilot["runtime_compatibility"] == "PASS"


def test_accepted_lock_contains_only_v2_and_no_split_authority(result):
    lock = result["lock"]
    assert lock["entry_count"] == len(lock["entries"]) == 120
    assert lock["v1_entries_included"] == 0
    assert lock["contains_train_test_assignments"] is False
    assert lock["contains_model_activation_or_probe_outcomes"] is False
    assert all(
        row["trajectory_spec_id"].startswith("fresh_vp_v2_")
        and row["target_authority"]["row_count"] == 60
        and len(row["target_authority"]["x_true_blocks"]) == 60
        for row in lock["entries"]
    )


def test_downstream_loader_refuses_v1_or_mixed_lock(tmp_path, result):
    valid = tmp_path / "valid-v2.json"
    valid.write_text(json.dumps(result["lock"]))
    assert p4c.load_accepted_cohort_v2(valid)["entry_count"] == 120
    invalid = dict(result["lock"])
    invalid["entries"] = [dict(row) for row in result["lock"]["entries"]]
    invalid["entries"][0]["trajectory_spec_id"] = "fresh_vp_l01_ltr_early_r1"
    mixed = tmp_path / "mixed.json"
    mixed.write_text(json.dumps(invalid))
    with pytest.raises(p4c.P4CError, match="non-V2 entry"):
        p4c.load_accepted_cohort_v2(mixed)


def test_materialized_p4c_authority_has_no_p5_outputs():
    receipt = load("p4c_receipt.json")
    lock = load("accepted_cohort_v2.lock.json")
    assert receipt["status"] == "PASS_REPAIRED_CAPTURE_COHORT_LOCKED"
    assert receipt["fresh_activations_extracted"] == 0
    assert receipt["fresh_r2_computed"] is False
    assert receipt["p5_started"] is False
    assert receipt["safe_for_p5"] is True
    assert lock["contains_train_test_assignments"] is False
