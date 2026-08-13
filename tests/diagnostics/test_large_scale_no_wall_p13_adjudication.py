"""Synthetic-only boundary and provenance tests for the P13 layer."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import run_large_scale_no_wall_p13_adjudication as p13


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _minimal_authority() -> dict:
    return {
        "allowed_inputs": [],
        "artifact_id": "large-scale-no-wall-p13-adjudication-authority-v1.0",
        "authority_base_commit": "ebe9826c6345ea67896faf9efaba9b0df66bf354",
        "execution_policy": {
            "ACTIVATION_OR_CACHE_RECONSTRUCTION_ALLOWED": False,
            "BEST_K_RESELECTION_ALLOWED": False,
            "CONTINUOUS_EVIDENCE_BEFORE_CLASSIFICATIONS": True,
            "CPU_ONLY": True,
            "FAIL_CLOSED_ON_HASH_MISMATCH": True,
            "NEW_EXPERIMENT": False,
            "P11_NULL_GENERATION_ALLOWED": False,
            "POST_OUTCOME_RULE_CHANGE_ALLOWED": False,
            "UPSTREAM_REFIT_ALLOWED": False,
        },
        "experiment_id": p13.EXPERIMENT_ID,
        "status": "LOCKED_OPERATOR_APPROVED",
    }


def _write_authority_pair(status_root: Path, *, corrupt_lock_sha: bool = False) -> dict:
    authority = _minimal_authority()
    authority_path = status_root / p13.AUTHORITY_NAME
    _write_json(authority_path, authority)
    digest = hashlib.sha256(authority_path.read_bytes()).hexdigest()
    lock = {
        "artifact_id": "large-scale-no-wall-p13-adjudication-authority-lock-v1.0",
        "authority_base_commit": authority["authority_base_commit"],
        "operator_approval": "APPROVED",
        "post_outcome_rule_change_allowed": False,
        "scientific_outcomes_used_to_choose_rules": False,
        "source_byte_size": authority_path.stat().st_size,
        "source_path": str(Path("docs/status/integration") / p13.EXPERIMENT_ID / p13.AUTHORITY_NAME),
        "source_sha256": "0" * 64 if corrupt_lock_sha else digest,
        "status": "LOCKED",
    }
    _write_json(status_root / p13.LOCK_NAME, lock)
    return authority


def _comparison(median: float = 0.02, win_rate: float = 0.6, lower: float = -0.01) -> dict:
    return {
        "interval": [lower, lower + 0.1],
        "median": median,
        "paired_deltas": [median] * 4,
        "subset_ids": [f"s{i}" for i in range(4)],
        "win_rate": win_rate,
    }


def synthetic_summary() -> dict:
    learning = {}
    for representation in p13.READINESS_ELIGIBLE:
        learning[representation] = {
            "by_n": {
                str(n): {
                    "layout_medians": {f"L{i}": 0.02 for i in range(1, 7)},
                    "macro_r2": {"median": 0.12, "sd_ddof1": 0.03},
                    "trajectory_bootstrap_95_interval": [-0.01, 0.2],
                }
                for n in p13.ANCHORS
            }
        }
    comparisons = {
        name: {str(n): _comparison() for n in p13.ANCHORS}
        for name in (
            "FULL_MINUS_GLOBAL",
            "BEST_K_MINUS_GLOBAL",
            "BEST_K_MINUS_FULL",
            "FULL_MINUS_BEST_K",
            "FULL_MINUS_COARSE",
            "BEST_K_MINUS_COARSE",
            "COARSE_MINUS_FULL",
            "COARSE_MINUS_BEST_K",
        )
    }
    scaling = {
        representation: {
            "gain_interval": [-0.01, 0.3],
            "gain_summary": {"median": 0.12},
            "spearman_rho": 0.5,
        }
        for representation in p13.CORE
    }
    prospective_null = {
        representation: {
            "observed": float(index),
            "positive_layout_count": 5,
            "separates": False,
        }
        for index, representation in enumerate(p13.READINESS_ELIGIBLE)
    }
    return {
        "adjudications": {},
        "artifact_id": "synthetic-canonical-summary",
        "authority": {"artifact_id": "synthetic-authority"},
        "comparisons": comparisons,
        "layout_generalization": {
            "historical_context": "MIXED",
            "known_layout_fixed_test_is_fresh_layout_evidence": False,
            "p12": "DEFERRED_BY_DESIGN",
            "primary_study": "NOT_ADJUDICATED_IN_PRIMARY_STUDY",
        },
        "learning": {"representations": learning},
        "profile_control": {
            "component_gates": {"synthetic_gate": True},
            "trajectory_profile_confound_controlled": True,
        },
        "prospective_null": prospective_null,
        "scaling": scaling,
        "stability": {
            str(n): {
                "median_chance_adjusted_overlap": 0.2,
                "median_jaccard": 0.3,
                "median_rank_spearman": 0.4,
            }
            for n in p13.ANCHORS
        },
    }


def set_comparison(summary: dict, first: str, second: str, n: int, **values: float) -> None:
    summary["comparisons"][p13._comparison_key(first, second)][str(n)].update(values)


def test_authority_lock_sha_mismatch_fails_closed(tmp_path: Path) -> None:
    status = tmp_path / "status"
    _write_authority_pair(status, corrupt_lock_sha=True)
    with pytest.raises(p13.P13Error, match="authority SHA256 mismatch"):
        p13.validate_authority(status)


def test_valid_synthetic_authority_lock_passes(tmp_path: Path) -> None:
    status = tmp_path / "status"
    _write_authority_pair(status)
    assert p13.validate_authority(status)["status"] == "LOCKED_OPERATOR_APPROVED"


def test_upstream_input_sha_mismatch_fails_closed(tmp_path: Path) -> None:
    status = tmp_path / "status"
    p11_root = tmp_path / "p11"
    input_path = status / "input.json"
    _write_json(input_path, {"synthetic": True})
    authority = _minimal_authority()
    authority["allowed_inputs"] = [
        {"id": "SYNTHETIC", "path": "input.json", "root": "STATUS_ROOT", "sha256": "f" * 64}
    ]
    with pytest.raises(p13.P13Error, match="input SHA256 mismatch"):
        p13.validate_inputs(authority, status, p11_root)


def test_existing_output_destination_fails_closed(tmp_path: Path) -> None:
    (tmp_path / p13.EXPECTED_OUTPUTS[0]).write_text("occupied", encoding="utf-8")
    with pytest.raises(p13.P13Error, match="already exists"):
        p13.ensure_destinations_absent(tmp_path)


def test_b_must_equal_49() -> None:
    with pytest.raises(p13.P13Error, match="B must equal 49"):
        p13.empirical_null_evidence(1.0, list(range(48)))


def test_empirical_q95_is_zero_based_index_46() -> None:
    evidence = p13.empirical_null_evidence(100.0, list(reversed(range(49))))
    assert evidence["q95_empirical_nearest_rank"] == 46.0


def test_add_one_p_is_exact_and_inclusive_rule_accepts_finest_passing_value() -> None:
    null = [float(i) for i in range(49)]
    evidence = p13.empirical_null_evidence(47.5, null)
    assert evidence["count_null_greater_equal_observed"] == 1
    assert evidence["empirical_p"] == 0.04
    assert evidence["empirical_p"] <= 0.05
    assert evidence["separates"] is True


def test_target_specific_requires_two_core_and_coarse_never_counts() -> None:
    summary = synthetic_summary()
    summary["prospective_null"]["GLOBAL_MEAN"].update(separates=True, positive_layout_count=5, observed=9.0)
    summary["prospective_null"]["COARSE_2x6"].update(separates=True, positive_layout_count=6, observed=10.0)
    result = p13.adjudicate(summary)["TARGET_SPECIFIC_DECODING_ESTABLISHED"]
    assert result["classification"] == "Unclear"
    assert result["qualifying_core_representations"] == ["GLOBAL_MEAN"]


def test_target_specific_requires_best_observed_core() -> None:
    summary = synthetic_summary()
    summary["prospective_null"]["GLOBAL_MEAN"].update(separates=True, observed=1.0)
    summary["prospective_null"]["FULL_TOKEN_GRID"].update(separates=True, observed=2.0)
    summary["prospective_null"]["BEST_K_TOKENS"].update(separates=False, observed=3.0)
    result = p13.adjudicate(summary)["TARGET_SPECIFIC_DECODING_ESTABLISHED"]
    assert result["classification"] == "Unclear"
    assert result["best_observed_core_set"] == ["BEST_K_TOKENS"]


def test_tied_best_core_set_has_no_posthoc_tie_break() -> None:
    summary = synthetic_summary()
    for representation in p13.CORE:
        summary["prospective_null"][representation].update(separates=True, positive_layout_count=5)
    summary["prospective_null"]["GLOBAL_MEAN"]["observed"] = 5.0
    summary["prospective_null"]["FULL_TOKEN_GRID"]["observed"] = 5.0
    summary["prospective_null"]["BEST_K_TOKENS"]["observed"] = 4.0
    result = p13.adjudicate(summary)["TARGET_SPECIFIC_DECODING_ESTABLISHED"]
    assert result["classification"] == "True"
    assert result["best_observed_core_set"] == ["FULL_TOKEN_GRID", "GLOBAL_MEAN"]


@pytest.mark.parametrize("positive_count,expected", [(5, "True"), (6, "True"), (4, "Unclear")])
def test_target_specific_layout_count_boundary(positive_count: int, expected: str) -> None:
    summary = synthetic_summary()
    for representation, observed in (("GLOBAL_MEAN", 3.0), ("FULL_TOKEN_GRID", 2.0)):
        summary["prospective_null"][representation].update(
            separates=True, positive_layout_count=positive_count, observed=observed
        )
    summary["prospective_null"]["BEST_K_TOKENS"].update(separates=False, observed=1.0)
    assert p13.adjudicate(summary)["TARGET_SPECIFIC_DECODING_ESTABLISHED"]["classification"] == expected


def test_layout_positivity_is_strictly_greater_than_zero() -> None:
    summary = synthetic_summary()
    layout_values = summary["learning"]["representations"]["COARSE_2x6"]["by_n"]["100"]["layout_medians"]
    layout_values.update({"L1": 1.0, "L2": 1.0, "L3": 1.0, "L4": 1.0, "L5": 0.0, "L6": 1.0})
    summary["prospective_null"]["GLOBAL_MEAN"].update(separates=True, observed=3.0)
    summary["prospective_null"]["FULL_TOKEN_GRID"].update(separates=True, observed=2.0)
    for representation in p13.READINESS_ELIGIBLE:
        summary["learning"]["representations"][representation]["by_n"]["100"]["macro_r2"]["median"] = 0.6
        summary["learning"]["representations"][representation]["by_n"]["100"]["trajectory_bootstrap_95_interval"] = [0.01, 0.2]
    result = p13.adjudicate(summary)["VISIBLE_POSITION_MEASUREMENT_PATH_READY_FOR_OCCLUDED_EXPERIMENT"]
    assert result["components"]["COARSE_2x6"]["positive_layout_count"] == 5


def test_token_win_rate_is_checked_at_each_anchor_and_equality_passes() -> None:
    summary = synthetic_summary()
    for n in p13.TOKEN_REPLICATION_ANCHORS:
        set_comparison(summary, "FULL_TOKEN_GRID", "GLOBAL_MEAN", n, win_rate=0.75)
    set_comparison(summary, "FULL_TOKEN_GRID", "GLOBAL_MEAN", 100, median=0.10)
    assert p13.adjudicate(summary)["TOKEN_PRESERVING_ADVANTAGE_REPLICATED"]["classification"] == "True"
    set_comparison(summary, "FULL_TOKEN_GRID", "GLOBAL_MEAN", 70, win_rate=0.749)
    assert p13.adjudicate(summary)["TOKEN_PRESERVING_ADVANTAGE_REPLICATED"]["classification"] == "Unclear"


def test_best_k_threshold_equalities_pass_but_interval_zero_does_not() -> None:
    summary = synthetic_summary()
    for n in p13.HIGH_N:
        set_comparison(summary, "BEST_K_TOKENS", "FULL_TOKEN_GRID", n, median=0.05, win_rate=0.75)
    set_comparison(summary, "BEST_K_TOKENS", "FULL_TOKEN_GRID", 100, lower=0.001, interval=[0.001, 0.2])
    assert p13.adjudicate(summary)["BEST_K_ADVANTAGE"]["classification"] == "True"
    set_comparison(summary, "BEST_K_TOKENS", "FULL_TOKEN_GRID", 100, interval=[0.0, 0.2])
    assert p13.adjudicate(summary)["BEST_K_ADVANTAGE"]["classification"] == "Unclear"


def test_coarse_strict_lower_margin_and_undefined_predicate() -> None:
    summary = synthetic_summary()
    summary["learning"]["representations"]["FULL_TOKEN_GRID"]["by_n"]["100"]["macro_r2"]["median"] = 0.5
    summary["learning"]["representations"]["BEST_K_TOKENS"]["by_n"]["100"]["macro_r2"]["median"] = 0.5
    summary["learning"]["representations"]["COARSE_2x6"]["by_n"]["100"]["macro_r2"]["median"] = 0.47
    for representation in ("FULL_TOKEN_GRID", "BEST_K_TOKENS"):
        set_comparison(summary, "COARSE_2x6", representation, 100, interval=[-0.05, 0.1])
    result = p13.adjudicate(summary)["COARSE_SPATIAL_READOUT_SUFFICIENT"]
    assert result["classification"] == "Unclear"
    assert result["qualitative_predicate"] == "UNRESOLVED"


def test_data_scale_true_and_false_boundaries() -> None:
    true_summary = synthetic_summary()
    for representation in ("GLOBAL_MEAN", "FULL_TOKEN_GRID"):
        true_summary["scaling"][representation].update(
            gain_interval=[0.001, 0.4], gain_summary={"median": 0.20}, spearman_rho=0.70
        )
        true_summary["learning"]["representations"][representation]["by_n"]["5"]["macro_r2"]["median"] = 0.0
        true_summary["learning"]["representations"][representation]["by_n"]["70"]["macro_r2"]["median"] = 0.15
        true_summary["learning"]["representations"][representation]["by_n"]["100"]["macro_r2"]["median"] = 0.15
    assert p13.adjudicate(true_summary)["DATA_SCALE_LIMITATION_PLAUSIBLE"]["classification"] == "True"

    false_summary = synthetic_summary()
    for representation in p13.CORE:
        false_summary["scaling"][representation].update(gain_summary={"median": 0.099}, spearman_rho=0.30)
    assert p13.adjudicate(false_summary)["DATA_SCALE_LIMITATION_PLAUSIBLE"]["classification"] == "False"


def test_mean_pooling_true_and_undefined_false_branch() -> None:
    summary = synthetic_summary()
    for n in p13.HIGH_N:
        set_comparison(summary, "FULL_TOKEN_GRID", "GLOBAL_MEAN", n, median=0.10)
    set_comparison(summary, "FULL_TOKEN_GRID", "GLOBAL_MEAN", 100, interval=[0.001, 0.2])
    assert p13.adjudicate(summary)["MEAN_POOLING_BOTTLENECK_PLAUSIBLE"]["classification"] == "True"
    unresolved = synthetic_summary()
    for representation in p13.TOKEN_PRESERVING:
        for n in p13.HIGH_N:
            set_comparison(unresolved, representation, "GLOBAL_MEAN", n, median=0.0)
    result = p13.adjudicate(unresolved)["MEAN_POOLING_BOTTLENECK_PLAUSIBLE"]
    assert result["classification"] == "Unclear"
    assert result["qualitative_predicate"] == "UNRESOLVED"


def test_token_replicated_false_requires_both_representations() -> None:
    summary = synthetic_summary()
    for representation in p13.TOKEN_PRESERVING:
        set_comparison(summary, representation, "GLOBAL_MEAN", 100, median=0.0, win_rate=0.50)
    assert p13.adjudicate(summary)["TOKEN_PRESERVING_ADVANTAGE_REPLICATED"]["classification"] == "False"


def test_best_k_false_boundary() -> None:
    summary = synthetic_summary()
    set_comparison(summary, "BEST_K_TOKENS", "FULL_TOKEN_GRID", 100, median=0.0, win_rate=0.50)
    assert p13.adjudicate(summary)["BEST_K_ADVANTAGE"]["classification"] == "False"


def test_stability_true_false_and_unclear_precedence() -> None:
    true_summary = synthetic_summary()
    for n in p13.HIGH_N:
        true_summary["stability"][str(n)].update(
            median_jaccard=0.50,
            median_rank_spearman=0.50,
            median_chance_adjusted_overlap=0.001,
        )
    assert p13.adjudicate(true_summary)["BEST_K_TOKEN_SELECTION_STABLE"]["classification"] == "True"
    false_summary = synthetic_summary()
    false_summary["stability"]["100"]["median_jaccard"] = 0.20
    assert p13.adjudicate(false_summary)["BEST_K_TOKEN_SELECTION_STABLE"]["classification"] == "False"
    assert p13.adjudicate(synthetic_summary())["BEST_K_TOKEN_SELECTION_STABLE"]["classification"] == "Unclear"


def test_full_grid_true_and_undefined_false_branch() -> None:
    summary = synthetic_summary()
    for reduced in ("BEST_K_TOKENS", "COARSE_2x6"):
        for n in p13.HIGH_N:
            set_comparison(summary, "FULL_TOKEN_GRID", reduced, n, median=0.05)
        set_comparison(summary, "FULL_TOKEN_GRID", reduced, 100, interval=[0.001, 0.2])
    assert p13.adjudicate(summary)["FULL_TOKEN_GRID_NEEDED"]["classification"] == "True"
    unresolved = synthetic_summary()
    set_comparison(unresolved, "FULL_TOKEN_GRID", "COARSE_2x6", 100, median=0.03)
    result = p13.adjudicate(unresolved)["FULL_TOKEN_GRID_NEEDED"]
    assert result["classification"] == "Unclear"
    assert result["qualitative_predicate"] == "UNRESOLVED"


def test_coarse_false_deficit_inclusive_boundary() -> None:
    summary = synthetic_summary()
    summary["learning"]["representations"]["FULL_TOKEN_GRID"]["by_n"]["100"]["macro_r2"]["median"] = 0.5
    summary["learning"]["representations"]["BEST_K_TOKENS"]["by_n"]["100"]["macro_r2"]["median"] = 0.4
    summary["learning"]["representations"]["COARSE_2x6"]["by_n"]["100"]["macro_r2"]["median"] = 0.4
    assert p13.adjudicate(summary)["COARSE_SPATIAL_READOUT_SUFFICIENT"]["classification"] == "False"


def test_profile_control_is_only_frozen_gate() -> None:
    summary = synthetic_summary()
    assert p13.adjudicate(summary)["TRAJECTORY_PROFILE_CONFOUND_CONTROLLED"]["classification"] == "True"
    summary["profile_control"]["trajectory_profile_confound_controlled"] = False
    assert p13.adjudicate(summary)["TRAJECTORY_PROFILE_CONFOUND_CONTROLLED"]["classification"] == "False"


def test_default_synthetic_case_exercises_unclear_and_true_precedes_false() -> None:
    result = p13.adjudicate(synthetic_summary())
    for field in (
        "DATA_SCALE_LIMITATION_PLAUSIBLE",
        "MEAN_POOLING_BOTTLENECK_PLAUSIBLE",
        "TOKEN_PRESERVING_ADVANTAGE_REPLICATED",
        "BEST_K_ADVANTAGE",
        "BEST_K_TOKEN_SELECTION_STABLE",
        "FULL_TOKEN_GRID_NEEDED",
        "COARSE_SPATIAL_READOUT_SUFFICIENT",
    ):
        assert result[field]["classification"] == "Unclear"
    assert p13._classify(True, True) == "True"


def _make_target_true(summary: dict) -> None:
    summary["prospective_null"]["GLOBAL_MEAN"].update(separates=True, positive_layout_count=5, observed=3.0)
    summary["prospective_null"]["FULL_TOKEN_GRID"].update(separates=True, positive_layout_count=5, observed=2.0)
    summary["prospective_null"]["BEST_K_TOKENS"].update(separates=False, observed=1.0)


def test_readiness_is_existential_over_all_four_predeclared_representations() -> None:
    summary = synthetic_summary()
    _make_target_true(summary)
    coarse = summary["learning"]["representations"]["COARSE_2x6"]["by_n"]["100"]
    coarse["macro_r2"]["median"] = 0.50
    coarse["trajectory_bootstrap_95_interval"] = [0.001, 0.2]
    coarse["layout_medians"] = {f"L{i}": 0.1 for i in range(1, 7)}
    result = p13.adjudicate(summary)["VISIBLE_POSITION_MEASUREMENT_PATH_READY_FOR_OCCLUDED_EXPERIMENT"]
    assert result["classification"] == "True"
    assert result["components"]["COARSE_2x6"]["ready"] is True


def test_target_specific_false_forces_readiness_false() -> None:
    summary = synthetic_summary()
    for representation in p13.READINESS_ELIGIBLE:
        n100 = summary["learning"]["representations"][representation]["by_n"]["100"]
        n100["macro_r2"]["median"] = 0.8
        n100["trajectory_bootstrap_95_interval"] = [0.1, 0.9]
    result = p13.adjudicate(summary)["VISIBLE_POSITION_MEASUREMENT_PATH_READY_FOR_OCCLUDED_EXPERIMENT"]
    assert result["classification"] == "False"


def test_max_high_n_median_at_point_one_forces_readiness_false() -> None:
    summary = synthetic_summary()
    _make_target_true(summary)
    for representation in p13.READINESS_ELIGIBLE:
        summary["learning"]["representations"][representation]["by_n"]["100"]["macro_r2"]["median"] = 0.10
    result = p13.adjudicate(summary)["VISIBLE_POSITION_MEASUREMENT_PATH_READY_FOR_OCCLUDED_EXPERIMENT"]
    assert result["classification"] == "False"


def test_layout_generalization_is_literal_p12_deferred_structure() -> None:
    result = p13.adjudicate(synthetic_summary())["LAYOUT_GENERALIZATION"]
    assert result == {
        "historical_context": "MIXED",
        "known_layout_fixed_test_is_fresh_layout_evidence": False,
        "p12": "DEFERRED_BY_DESIGN",
        "primary_study": "NOT_ADJUDICATED_IN_PRIMARY_STUDY",
    }


def test_six_chain_gain_bootstrap_is_deterministic_and_requires_six_units() -> None:
    units = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
    assert p13.paired_mean_bootstrap_interval(units) == p13.paired_mean_bootstrap_interval(units)
    with pytest.raises(p13.P13Error, match="six complete chain units"):
        p13.paired_mean_bootstrap_interval(units[:5])


def _trajectory_records() -> list[dict]:
    records = []
    for subset in range(2):
        per_trajectory = {}
        per_layout = {}
        for layout_index in range(6):
            layout = f"L{layout_index + 1}"
            per_layout[layout] = {"r2": 0.1}
            for trajectory_index in range(3):
                identity = f"s{subset}-{layout}-{trajectory_index}"
                per_trajectory[identity] = {"layout": layout, "r2": float(subset + layout_index + trajectory_index)}
        records.append({"metrics": {"per_layout": per_layout, "per_trajectory": per_trajectory}})
    return records


def test_trajectory_bootstrap_uses_whole_trajectory_layout_units_not_frames() -> None:
    records = _trajectory_records()
    assert p13.trajectory_bootstrap_interval(records, seed=7, replicates=50) == p13.trajectory_bootstrap_interval(records, seed=7, replicates=50)
    broken = copy.deepcopy(records)
    broken[0]["metrics"]["per_trajectory"].pop(next(iter(broken[0]["metrics"]["per_trajectory"])))
    with pytest.raises(p13.P13Error, match="three trajectories per layout"):
        p13.trajectory_bootstrap_interval(broken, seed=7, replicates=10)


def test_output_documents_are_projections_of_one_canonical_summary() -> None:
    summary = synthetic_summary()
    summary["adjudications"] = p13.adjudicate(summary)
    documents = p13.build_output_documents(summary)
    assert all(document["source_canonical_summary_artifact_id"] == summary["artifact_id"] for document in documents.values())
    assert documents["diagnostic_adjudication.json"]["continuous_evidence_precedes_categories"] is True
    assert documents["diagnostic_adjudication.json"]["categorical_adjudications"] is summary["adjudications"]
    serialized = p13.canonical_json_bytes(documents["diagnostic_adjudication.json"])
    assert serialized.index(b'"continuous_evidence"') < serialized.index(b'"categorical_adjudications"')


def test_deterministic_synthetic_replay() -> None:
    first = synthetic_summary()
    first["adjudications"] = p13.adjudicate(first)
    second = synthetic_summary()
    second["adjudications"] = p13.adjudicate(second)
    assert p13.canonical_json_bytes(p13.build_output_documents(first)["diagnostic_adjudication.json"]) == p13.canonical_json_bytes(p13.build_output_documents(second)["diagnostic_adjudication.json"])


def test_runner_has_no_model_fit_gpu_activation_or_cloud_import_path() -> None:
    source_path = Path(p13.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots.isdisjoint({"torch", "boto3", "sagemaker", "mineocclude", "cupy"})
    function_names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not any(name.startswith(("fit", "train", "extract", "rerank", "reconstruct", "upload", "download")) for name in function_names)
