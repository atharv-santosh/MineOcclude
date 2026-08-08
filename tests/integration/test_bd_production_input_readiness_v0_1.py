from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts/build_bd_production_input_readiness_v0_1.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("bd_readiness_builder", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


def _row_map(rows):
    return {
        (str(row["trajectory_id"]), int(row["model_frame_idx"])): row for row in rows
    }


def test_builder_is_input_only_and_has_no_scientific_execution_path() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "mineocclude.probes" not in source
    assert "fit_ridge_oof(" not in source
    assert "permutation_test(" not in source
    assert "run_person_a_66_cell_production_extraction" not in source
    assert '"probe_fitted": False' in source
    assert '"baseline_recomputed": False' in source


def test_current_b_successor_universe_and_folds_are_exact() -> None:
    b = builder.load_b_authorities()
    rows = _row_map(b["rows"])
    assert len(rows) == 2468
    assert sum(row["status"] == "accepted" for row in rows.values()) == 662
    assert len(b["targets"]) == 2108
    fold = builder.validate_fold_integrity(
        rows,
        b["fold_manifest"],
        b["documents"]["fold_leakage_audit"],
    )
    assert fold["fold_count"] == 5
    assert fold["trajectory_cross_fold_count"] == 0
    assert fold["missing_eligible_assignment_count"] == 0
    assert fold["new_random_split_generated"] is False


def test_current_d_package_matches_b_successor_universe() -> None:
    b = builder.load_b_authorities()
    rows = _row_map(b["rows"])
    fold = builder.validate_fold_integrity(
        rows,
        b["fold_manifest"],
        b["documents"]["fold_leakage_audit"],
    )
    accepted = [row for row in rows.values() if row["status"] == "accepted"]
    scopes = Counter(
        scope for row in accepted for scope in row.get("analysis_scopes", ())
    )
    folds = Counter(int(row["fold_idx"]) for row in accepted)
    d = builder.validate_d_baselines(
        {
            "eligible_by_fold": {str(key): folds[key] for key in sorted(folds)},
            "eligible_by_scope": dict(scopes),
            "row_by_key": rows,
        },
        fold,
    )
    assert d["authority_commit"] == builder.PERSON_D_AUTHORITY_COMMIT
    assert d["prediction_row_count"] == 10592
    assert d["required_comparators_ready"] is True
    assert d["comparator_status"]["raw_pixel"] == "READY_EXISTING"
    assert d["comparator_status"]["occluder_only_negative_control"] == "NOT_APPLICABLE"


def test_generated_readiness_receipt_if_present() -> None:
    if not builder.RECEIPT_PATH.is_file():
        pytest.skip("readiness receipt is generated only after builder commit")
    receipt = json.loads(builder.RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["schema_id"] == builder.SCHEMA_ID
    assert receipt["activation_validation"] == {
        "activation_chunk_count": 1320,
        "activation_frame_count": 2468,
        "activation_index_load_pass": True,
        "activation_layer_count": 20,
        "activation_row_count": 49360,
        "activation_trajectory_count": 66,
        "all_chunk_files_exist": True,
        "all_chunk_hashes_verified": True,
        "stored_dtype": "float32",
    }
    join = receipt["join_audit"]
    assert join["row_universe_frame_count"] == 2468
    assert join["target_bearing_frame_count"] == 2108
    assert join["analysis_eligible_frame_count"] == 662
    assert join["analysis_eligible_activation_row_count"] == 13240
    assert join["join_duplicate_count"] == 0
    assert join["join_missing_activation_count"] == 0
    assert join["join_unauthorized_source_count"] == 0
    assert join["quarantined_frame_count"] == 744
    assert join["eligible_quarantined_frame_count"] == 0
    assert join["quarantined_by_category"] == {
        "geometry_hidden_detector_visible": 313,
        "geometry_visible_detector_hidden": 71,
        "invalid_geometry": 360,
    }
    decision = receipt["readiness_decision"]
    assert decision["can_real_u1_fitting_begin"] is True
    assert decision["can_real_u2_fitting_begin"] is True
    assert decision["can_real_u3_analysis_begin"] is False
    assert decision["are_required_d_comparators_ready"] is True
    assert receipt["scientific_execution"] == {
        "baseline_recomputed": False,
        "final_u1_u2_u3_results_computed": False,
        "layer_selected": False,
        "permutation_executed": False,
        "probe_fitted": False,
        "scientific_claim_made": False,
    }


def test_external_analysis_ready_arrays_if_present() -> None:
    if not builder.EXTERNAL_MANIFEST_PATH.is_file():
        pytest.skip("external analysis-ready arrays are generated after builder commit")
    manifest_bytes = builder.EXTERNAL_MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["eligible_frame_count"] == 662
    assert manifest["eligible_frame_layer_row_count"] == 13240
    assert manifest["scientific_fitting_executed"] is False
    for key in ("activation_vectors", "metadata"):
        identity = manifest[key]
        path = Path(identity["path"])
        assert path.is_file()
        assert path.stat().st_size == identity["byte_size"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == identity["sha256"]
    vectors = np.load(builder.VECTOR_PATH, mmap_mode="r", allow_pickle=False)
    metadata = np.load(builder.METADATA_PATH, mmap_mode="r", allow_pickle=False)
    assert vectors.shape == (13240, 2048)
    assert vectors.dtype == np.float32
    assert metadata.shape == (13240,)
    assert metadata.dtype == builder.METADATA_DTYPE
    assert set(np.unique(metadata["layer_idx"])) == set(range(20))
    assert set(np.unique(metadata["fold_idx"])) == set(range(5))
    assert np.isfinite(vectors).all()
    hidden_spread = (metadata["scope_mask"] & builder.SCOPE_BITS["hidden_spread"]) != 0
    assert np.isfinite(metadata["log_sigma_oracle"][hidden_spread]).all()
