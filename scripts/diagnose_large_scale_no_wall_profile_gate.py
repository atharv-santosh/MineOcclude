#!/usr/bin/env python3
"""Diagnose the failed P4 profile-similarity gate without model outcomes."""

from __future__ import annotations

import importlib.util
import json
import os
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
P4_SCRIPT = ROOT / "scripts/audit_large_scale_no_wall_profiles.py"
AMENDMENT_NAME = "PROFILE_DIVERSITY_GATE_AMENDMENT_V1"


def load_p4_module():
    spec = importlib.util.spec_from_file_location("p4_profile_audit", P4_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load P4 audit implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def signed_summary(values: list[float], threshold: float = 0.95) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    absolute = np.abs(array)
    high_positive = int(np.sum(array >= threshold))
    high_negative = int(np.sum(array <= -threshold))
    high_absolute = int(np.sum(absolute >= threshold))
    return {
        "pair_count": int(array.size),
        "mean_r": float(np.mean(array)),
        "median_r": float(np.median(array)),
        "mean_abs_r": float(np.mean(absolute)),
        "median_abs_r": float(np.median(absolute)),
        "p95_abs_r": float(np.quantile(absolute, 0.95, method="linear")),
        "r_ge_positive_0_95_count": high_positive,
        "r_ge_positive_0_95_proportion": float(high_positive / array.size),
        "r_le_negative_0_95_count": high_negative,
        "r_le_negative_0_95_proportion": float(high_negative / array.size),
        "abs_r_ge_0_95_count": high_absolute,
        "abs_r_ge_0_95_proportion": float(high_absolute / array.size),
    }


def compute_diagnosis() -> dict[str, Any]:
    p4 = load_p4_module()
    result = p4.compute_audit()
    profiles = result["profiles"]
    predicates: dict[str, Callable[[dict[str, Any], dict[str, Any]], bool]] = {
        "all_pairs": lambda left, right: True,
        "same_direction": lambda left, right: left["direction"] == right["direction"],
        "opposite_direction": lambda left, right: left["direction"]
        != right["direction"],
        "same_direction_same_profile_family": lambda left, right: (
            left["direction"] == right["direction"]
            and left["profile_family"] == right["profile_family"]
        ),
        "same_direction_different_profile_family": lambda left, right: (
            left["direction"] == right["direction"]
            and left["profile_family"] != right["profile_family"]
        ),
        "opposite_direction_same_profile_family": lambda left, right: (
            left["direction"] != right["direction"]
            and left["profile_family"] == right["profile_family"]
        ),
        "opposite_direction_different_profile_family": lambda left, right: (
            left["direction"] != right["direction"]
            and left["profile_family"] != right["profile_family"]
        ),
        "same_layout": lambda left, right: left["layout_id"] == right["layout_id"],
        "different_layout": lambda left, right: left["layout_id"] != right["layout_id"],
        "same_layout_same_direction": lambda left, right: (
            left["layout_id"] == right["layout_id"]
            and left["direction"] == right["direction"]
        ),
        "same_layout_opposite_direction": lambda left, right: (
            left["layout_id"] == right["layout_id"]
            and left["direction"] != right["direction"]
        ),
        "same_repeat_index_descriptive_only": lambda left, right: left["repeat_id"]
        == right["repeat_id"],
        "different_repeat_index_descriptive_only": lambda left, right: left["repeat_id"]
        != right["repeat_id"],
    }
    values = {name: [] for name in predicates}
    pair_rows = []
    for left, right in combinations(profiles, 2):
        correlation = p4.pearson(left["profile"], right["profile"])
        row = {
            "left_spec_id": left["trajectory_spec_id"],
            "right_spec_id": right["trajectory_spec_id"],
            "signed_pearson_r": correlation,
            "absolute_pearson_r": abs(correlation),
            "same_direction": left["direction"] == right["direction"],
            "same_profile_family": left["profile_family"] == right["profile_family"],
            "same_layout": left["layout_id"] == right["layout_id"],
            "same_repeat_index": left["repeat_id"] == right["repeat_id"],
        }
        pair_rows.append(row)
        for name, predicate in predicates.items():
            if predicate(left, right):
                values[name].append(correlation)
    strata = {name: signed_summary(rows) for name, rows in values.items()}
    same_high = strata["same_direction"]["abs_r_ge_0_95_count"]
    opposite_high = strata["opposite_direction"]["abs_r_ge_0_95_count"]
    total_high = strata["all_pairs"]["abs_r_ge_0_95_count"]
    same_direction_amended_rule_result = strata["same_direction"][
        "r_ge_positive_0_95_proportion"
    ]
    same_direction_rule_pass = same_direction_amended_rule_result <= 0.20
    if same_direction_rule_pass:
        raise RuntimeError(
            "diagnosis assumptions changed: same-direction proposed rule now passes"
        )
    diagnosis = {
        "schema_version": "large-scale-no-wall-p4a-profile-gate-diagnosis-v0.1",
        "status": "STOP_AND_REPORT",
        "analysis_inputs": "existing P4 target/server-state authority only",
        "model_outcomes_available": False,
        "fresh_activations_extracted": 0,
        "fresh_r2_computed": False,
        "train_test_split_created": False,
        "capture_cohort_changed": False,
        "trajectory_specs_changed": False,
        "total_pairs": strata["all_pairs"]["pair_count"],
        "pair_strata": strata,
        "high_abs_r_total": total_high,
        "high_abs_r_same_direction": same_high,
        "high_abs_r_opposite_direction": opposite_high,
        "high_abs_r_share_same_direction": float(same_high / total_high),
        "high_abs_r_share_opposite_direction": float(opposite_high / total_high),
        "original_gate": {
            "rule": (
                "all unordered profile pairs with abs(Pearson r) >= 0.95; "
                "maximum fraction 0.20"
            ),
            "result": "3644/7140 = 0.5103641456582633",
            "status": "FAIL",
        },
        "direction_conflation_hypothesis": {
            "supported_as_primary_explanation": False,
            "opposite_direction_negative_mirrors_exist": True,
            "opposite_direction_high_negative_count": strata["opposite_direction"][
                "r_le_negative_0_95_count"
            ],
            "but_same_direction_high_positive_count": strata["same_direction"][
                "r_ge_positive_0_95_count"
            ],
            "conclusion": (
                "Opposite-direction mirrors account for only 50.47% of failed "
                "pairs. The remaining 49.53% are same-direction, and 50.99% of "
                "all same-direction pairs are themselves high-positive."
            ),
        },
        "plausible_amended_rule_diagnostic": {
            "candidate_rule": (
                "within same movement direction, signed Pearson r >= +0.95; "
                "maximum fraction 0.20"
            ),
            "result_fraction": same_direction_amended_rule_result,
            "result_count": strata["same_direction"]["r_ge_positive_0_95_count"],
            "pair_count": strata["same_direction"]["pair_count"],
            "status": "PASS" if same_direction_rule_pass else "FAIL",
            "amendment_not_justified": True,
        },
        "scientific_intent_assessment": {
            "intended_problem": (
                "prevent recurrence of stereotyped monotonic target ramps and "
                "generic time-to-position alignment"
            ),
            "direction_reversal_is_not_duplicate_in_isolation": True,
            "real_same_direction_shape_redundancy_present": True,
            "same_direction_same_family_high_positive_fraction": strata[
                "same_direction_same_profile_family"
            ]["r_ge_positive_0_95_proportion"],
            "same_direction_different_family_high_positive_fraction": strata[
                "same_direction_different_profile_family"
            ]["r_ge_positive_0_95_proportion"],
            "five_families_remain_too_stereotyped_within_direction": True,
        },
        "prospective_derangement_null_assessment": {
            "bidirectionality_breaks_single_global_time_position_alignment": True,
            "overall_time_position_r": result["audit"]["time_position_correlation"][
                "overall"
            ],
            "direction_stratified_alignment_remains_strong": True,
            "left_to_right_time_position_r": result["audit"][
                "time_position_correlation"
            ]["by_direction"]["LEFT_TO_RIGHT"],
            "right_to_left_time_position_r": result["audit"][
                "time_position_correlation"
            ]["by_direction"]["RIGHT_TO_LEFT"],
            "assessment": (
                "The within-layout N=100 derangement null remains a prospective "
                "outcome null, but it cannot substitute for the failed profile-"
                "diversity gate: aggregate direction cancellation coexists with "
                "strong within-direction temporal shape redundancy."
            ),
        },
        "selected_response": "ORIGINAL_GATE_VALID_REAL_DIVERSITY_FAILURE",
        "genuine_profile_diversity_failure": True,
        "abs_correlation_direction_conflation": "PRESENT_BUT_NOT_GATE_DECISIVE",
        "amendment_created": False,
        "amendment_name": None,
        "accepted_cohort_lock_created": False,
        "safe_for_p5": False,
        "recapture_required": False,
        "recapture_reason": (
            "Same-spec recapture deterministically reproduces the locked profiles; "
            "a protocol-level trajectory-shape redesign is required first."
        ),
        "blocker": (
            "The plausible same-direction signed-r repair still fails: "
            "1805/3540 = 0.5098870056497176 > 0.20."
        ),
        "pair_rows_sha256": p4.canonical_sha256(pair_rows),
    }
    return {"diagnosis": diagnosis, "signed_pair_rows": pair_rows}


def write_figure(pair_rows: list[dict[str, Any]]) -> str:
    same = [row["signed_pearson_r"] for row in pair_rows if row["same_direction"]]
    opposite = [
        row["signed_pearson_r"] for row in pair_rows if not row["same_direction"]
    ]
    bins = np.linspace(-1, 1, 61)
    fig, axis = plt.subplots(figsize=(8, 4.8))
    axis.hist(
        opposite, bins=bins, alpha=0.72, label="opposite direction", color="#e45756"
    )
    axis.hist(same, bins=bins, alpha=0.72, label="same direction", color="#4c78a8")
    axis.axvline(-0.95, color="black", linestyle="--", linewidth=1)
    axis.axvline(0.95, color="black", linestyle="--", linewidth=1)
    axis.set_xlabel("Signed pairwise Pearson r")
    axis.set_ylabel("Unordered trajectory pairs")
    axis.set_title("P4A direction decomposition of profile similarity")
    axis.legend()
    fig.tight_layout()
    path = PACKAGE / "p4a_signed_similarity_by_direction.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path.name


def main() -> int:
    result = compute_diagnosis()
    diagnosis = result["diagnosis"]
    figure = write_figure(result["signed_pair_rows"])
    original_artifacts = [
        "pre_extraction_profile_audit.json",
        "p4_profile_statistics.json",
        "p4_retry_audit.json",
        "p4_receipt.json",
        "time_position_association.png",
        "profile_similarity_distribution.png",
    ]
    diagnosis["original_p4_result_preserved"] = True
    diagnosis["original_p4_artifact_sha256"] = {
        name: load_p4_module().sha256_file(PACKAGE / name)
        for name in original_artifacts
    }
    write_json(PACKAGE / "p4a_profile_gate_diagnosis.json", diagnosis)
    receipt = {
        "schema_version": "large-scale-no-wall-p4a-receipt-v0.1",
        "status": "STOP_AND_REPORT",
        "selected_response": diagnosis["selected_response"],
        "genuine_profile_diversity_failure": True,
        "abs_correlation_direction_conflation": "PRESENT_BUT_NOT_GATE_DECISIVE",
        "amendment_created": False,
        "amendment_name": None,
        "original_p4_result_preserved": True,
        "p1_original_lock_preserved": True,
        "capture_cohort_changed": False,
        "trajectory_specs_changed": False,
        "model_outcomes_available": False,
        "fresh_activations_extracted": 0,
        "fresh_r2_computed": False,
        "train_test_split_created": False,
        "accepted_cohort_lock_created": False,
        "accepted_cohort_lock_count": 0,
        "safe_for_p5": False,
        "recapture_required": False,
        "blocker": diagnosis["blocker"],
        "artifacts": ["p4a_profile_gate_diagnosis.json", figure, "p4a_receipt.json"],
    }
    write_json(PACKAGE / "p4a_receipt.json", receipt)
    print(
        "P4A_STATUS=STOP_AND_REPORT "
        "same_direction_high_positive=1805/3540 "
        "opposite_direction_high_negative=1839/3600"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
