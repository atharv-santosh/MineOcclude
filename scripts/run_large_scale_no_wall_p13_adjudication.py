#!/usr/bin/env python3
"""CPU-only P13 adjudication from validated compact P8-P12 authorities.

This module deliberately has no model-fitting, activation, GPU, or cloud path.
All continuous evidence is assembled once in ``build_canonical_summary`` and
every classification, JSON document, figure, and receipt is derived from that
single structure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "exploratory_large_scale_no_wall_scaling_best_k_v0_1"
DEFAULT_STATUS_ROOT = REPO_ROOT / "docs" / "status" / "integration" / EXPERIMENT_ID
DEFAULT_P11_ROOT = Path(
    "/home/sagemaker-user/mineocclude_p11_owner_runtime/canonical_aggregation"
)
AUTHORITY_NAME = "p13_adjudication_authority.json"
LOCK_NAME = "p13_adjudication_authority.lock.json"

CORE = ("GLOBAL_MEAN", "FULL_TOKEN_GRID", "BEST_K_TOKENS")
TOKEN_PRESERVING = ("FULL_TOKEN_GRID", "BEST_K_TOKENS")
READINESS_ELIGIBLE = (*CORE, "COARSE_2x6")
ANCHORS = (5, 15, 40, 70, 100)
HIGH_N = (70, 100)
TOKEN_REPLICATION_ANCHORS = (40, 70, 100)
COMPLETE_MASTERS = tuple(f"master_{index:02d}" for index in range(6))

EXPECTED_OUTPUTS = (
    "learning_curve_summary.json",
    "representation_comparison.json",
    "diagnostic_adjudication.json",
    "p13_learning_curve_decision.png",
    "p13_representation_comparison_decision.png",
    "p13_null_layout_profile_decision.png",
    "p13_receipt.json",
)

EXPECTED_RECEIPT_STATUSES = {
    "P8_VALIDATION": "PASS_P8_COMPLETE_VALIDATED",
    "P9_RECEIPT": "PASS_P9_COMPLETE_VALIDATED",
    "P10_VALIDATION": "PASS_P10_COMPLETE_VALIDATED",
    "P11_AGGREGATION_RECEIPT": "PASS_CANONICAL_DISTRIBUTED_AGGREGATION_B49",
    "P11_PACKAGE_RECEIPT": "PASS_CANONICAL_DISTRIBUTED_PACKAGE_DURABLE",
    "P11_MERGE_VALIDATION": "PASS_49_SEEDS_196_JOBS_SAFE_FOR_CANONICAL_AGGREGATION",
    "P12_STATUS": "DEFERRED_BY_DESIGN",
}


class P13Error(RuntimeError):
    """Raised when frozen authority or a P13 execution invariant fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P13Error(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=False, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def validate_authority(status_root: Path) -> dict[str, Any]:
    """Validate the operator-approved authority and its byte lock."""

    authority_path = status_root / AUTHORITY_NAME
    lock_path = status_root / LOCK_NAME
    require(authority_path.is_file(), f"missing P13 authority: {authority_path}")
    require(lock_path.is_file(), f"missing P13 authority lock: {lock_path}")
    lock = read_json(lock_path)
    expected_suffix = Path("docs/status/integration") / EXPERIMENT_ID / AUTHORITY_NAME
    require(lock.get("artifact_id") == "large-scale-no-wall-p13-adjudication-authority-lock-v1.0", "authority lock artifact_id mismatch")
    require(lock.get("status") == "LOCKED", "authority lock is not LOCKED")
    require(lock.get("operator_approval") == "APPROVED", "operator approval missing")
    require(lock.get("scientific_outcomes_used_to_choose_rules") is False, "authority rules were outcome-selected")
    require(lock.get("post_outcome_rule_change_allowed") is False, "post-outcome rule changes are allowed")
    require(Path(str(lock.get("source_path"))) == expected_suffix, "authority lock source_path mismatch")
    require(authority_path.stat().st_size == lock.get("source_byte_size"), "authority byte-size mismatch")
    require(sha256_file(authority_path) == lock.get("source_sha256"), "authority SHA256 mismatch")
    authority = read_json(authority_path)
    require(authority.get("status") == "LOCKED_OPERATOR_APPROVED", "authority is not operator-approved and locked")
    require(authority.get("authority_base_commit") == lock.get("authority_base_commit"), "authority base commit mismatch")
    require(authority.get("experiment_id") == EXPERIMENT_ID, "experiment ID mismatch")
    policy = authority.get("execution_policy", {})
    expected_policy = {
        "CPU_ONLY": True,
        "NEW_EXPERIMENT": False,
        "UPSTREAM_REFIT_ALLOWED": False,
        "BEST_K_RESELECTION_ALLOWED": False,
        "P11_NULL_GENERATION_ALLOWED": False,
        "ACTIVATION_OR_CACHE_RECONSTRUCTION_ALLOWED": False,
        "POST_OUTCOME_RULE_CHANGE_ALLOWED": False,
        "CONTINUOUS_EVIDENCE_BEFORE_CLASSIFICATIONS": True,
        "FAIL_CLOSED_ON_HASH_MISMATCH": True,
    }
    require(all(policy.get(key) is value for key, value in expected_policy.items()), "execution policy mismatch")
    return authority


def resolve_input_paths(
    authority: Mapping[str, Any], status_root: Path, p11_root: Path
) -> dict[str, Path]:
    roots = {"STATUS_ROOT": status_root, "P11_ROOT": p11_root}
    paths: dict[str, Path] = {}
    entries = authority.get("allowed_inputs")
    require(isinstance(entries, list) and entries, "allowed input authority is empty")
    for entry in entries:
        require(isinstance(entry, dict), "allowed input entry must be an object")
        identity = entry.get("id")
        root_name = entry.get("root")
        relative = entry.get("path")
        require(isinstance(identity, str) and identity not in paths, "duplicate or invalid input ID")
        require(root_name in roots, f"invalid input root for {identity}")
        require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), f"invalid relative path for {identity}")
        paths[identity] = roots[str(root_name)] / relative
    return paths


def validate_inputs(
    authority: Mapping[str, Any], status_root: Path, p11_root: Path
) -> dict[str, Path]:
    """Hash every input before any scientific field is consumed."""

    paths = resolve_input_paths(authority, status_root, p11_root)
    for entry in authority["allowed_inputs"]:
        identity = entry["id"]
        path = paths[identity]
        require(path.is_file(), f"missing required input {identity}: {path}")
        require(sha256_file(path) == entry["sha256"], f"input SHA256 mismatch: {identity}")
    return paths


def load_inputs(paths: Mapping[str, Path]) -> dict[str, dict[str, Any]]:
    """Load only after all hashes have passed."""

    return {identity: read_json(path) for identity, path in paths.items()}


def validate_loaded_inputs(documents: Mapping[str, Mapping[str, Any]]) -> None:
    """Validate completeness, receipts, and fixed scientific identities."""

    for identity, expected in EXPECTED_RECEIPT_STATUSES.items():
        require(documents[identity].get("status") == expected, f"status mismatch: {identity}")

    p11 = documents["P11_CANONICAL_RESULT"]
    aggregation = documents["P11_AGGREGATION_RECEIPT"]
    package = documents["P11_PACKAGE_RECEIPT"]
    merge = documents["P11_MERGE_VALIDATION"]
    require(p11.get("status") == "PASS_P11_COMPLETE_49_OF_49", "P11 result status mismatch")
    require(p11.get("null_replicates") == 49, "P11 B is not 49")
    require(set(p11.get("representations", {})) == set(READINESS_ELIGIBLE), "P11 representation set mismatch")
    for representation in READINESS_ELIGIBLE:
        record = p11["representations"][representation]
        require(len(record.get("null_equal_layout_macro_r2", [])) == 49, f"P11 null count mismatch: {representation}")
        require(len(record.get("seed_order", [])) == 49, f"P11 seed count mismatch: {representation}")
    for receipt in (aggregation, package):
        require(receipt.get("null_replicates") == 49, "P11 receipt B mismatch")
        require(receipt.get("validated_seed_count") == 49, "P11 validated seed count mismatch")
        require(receipt.get("validated_job_count") == 196, "P11 validated job count mismatch")
        require(receipt.get("scientific_interpretation_performed") is False, "P11 already interpreted science")
    require(merge.get("validated_seed_count") == 49, "P11 merge seed count mismatch")
    require(merge.get("validated_job_count") == 196, "P11 merge job count mismatch")
    require(merge.get("representations_per_seed") == 4, "P11 merge representation count mismatch")

    p12 = documents["P12_STATUS"]
    require(p12.get("known_layout_fixed_test_is_fresh_layout_evidence") is False, "P12 relabels known layouts as fresh-layout evidence")
    require(p12.get("historical_layout_generalization") == "MIXED", "P12 historical context mismatch")

    study = documents["STUDY_DESIGN"]
    require(study.get("learning_curve", {}).get("training_sizes") == list(ANCHORS), "training anchors mismatch")
    require(tuple(study.get("representations", {}).get("core", [])) == CORE, "core representation authority mismatch")
    require(tuple(study.get("representations", {}).get("secondary", [])) == ("COARSE_2x6",), "secondary representation authority mismatch")
    require(study.get("targets_and_metrics", {}).get("primary_metric") == "equal-layout macro held-out R2", "primary metric authority mismatch")

    split = documents["SPLIT_AUTHORITY"]
    fixed = split.get("fixed_test", {})
    require(fixed.get("count") == 18, "fixed-test count mismatch")
    require(fixed.get("per_layout") == 3, "fixed-test layout balance mismatch")
    require(split.get("train_test_overlap") == 0, "train/test overlap is nonzero")
    schedule = documents["SUBSET_SCHEDULE"]
    subsets = schedule.get("subsets", [])
    require(len(subsets) == 62 and schedule.get("total_subsets") == 62, "subset count mismatch")
    expected_counts = {5: 20, 15: 16, 40: 12, 70: 8, 100: 6}
    actual_counts = {n: sum(int(record.get("training_size")) == n for record in subsets) for n in ANCHORS}
    require(actual_counts == expected_counts, "subset schedule by-N counts mismatch")
    require(documents["GROUPED_FOLDS"].get("frame_level_split_used") is False, "frame-level folds are forbidden")

    learning = documents["P8_LEARNING_RESULTS"]
    coarse = documents["P10_COARSE_RESULTS"]
    require(learning.get("status") == "PASS_COMPLETE_186_OF_186", "P8 result status mismatch")
    require(documents["P9_STABILITY"].get("status") == "PASS_P9_COMPLETE_VALIDATED", "P9 result status mismatch")
    require(coarse.get("status") == "PASS_P10_COMPLETE_62_OF_62", "P10 result status mismatch")
    require(len(learning.get("job_records", [])) == 186, "P8 job count mismatch")
    require(len(coarse.get("job_records", [])) == 62, "P10 job count mismatch")
    require(learning.get("fixed_test_hash") == fixed.get("authority_hash"), "P8 fixed-test hash mismatch")
    require(coarse.get("fixed_test_hash") == fixed.get("authority_hash"), "P10 fixed-test hash mismatch")
    require(documents["ACCEPTED_COHORT"].get("entry_count") == 120, "accepted cohort count mismatch")


def ensure_destinations_absent(output_root: Path, filenames: Sequence[str] = EXPECTED_OUTPUTS) -> None:
    existing = [name for name in filenames if (output_root / name).exists()]
    require(not existing, "P13 output destination already exists: " + ", ".join(existing))


def finite_vector(values: Sequence[float], label: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    require(array.ndim == 1 and array.size > 0, f"{label} must be a nonempty vector")
    require(bool(np.isfinite(array).all()), f"{label} contains nonfinite values")
    return array


def numeric_summary(values: Sequence[float]) -> dict[str, float | int]:
    array = finite_vector(values, "summary values")
    q25, q75 = np.quantile(array, [0.25, 0.75], method="linear")
    return {
        "count": int(array.size),
        "iqr": float(q75 - q25),
        "maximum": float(array.max()),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "minimum": float(array.min()),
        "sd_ddof1": float(array.std(ddof=1)) if array.size > 1 else 0.0,
    }


def paired_mean_bootstrap_interval(
    paired_values: Sequence[float], *, seed: int = 20260810, replicates: int = 10_000
) -> list[float]:
    """Frozen paired-summary bootstrap; each input element remains one unit."""

    values = finite_vector(paired_values, "paired bootstrap values")
    require(values.size == 6, "six complete chain units are required")
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(replicates, values.size), replace=True).mean(axis=1)
    low, high = np.quantile(draws, [0.025, 0.975], method="linear")
    return [float(low), float(high)]


def trajectory_bootstrap_interval(
    records: Sequence[Mapping[str, Any]], *, seed: int, replicates: int = 10_000
) -> list[float]:
    """Stratified whole-trajectory bootstrap retaining layouts and subsets."""

    require(bool(records), "trajectory bootstrap requires subset records")
    layouts = sorted(records[0]["metrics"]["per_layout"])
    require(len(layouts) == 6, "trajectory bootstrap requires six fixed layouts")
    values = np.empty((len(records), 6, 3), dtype=np.float64)
    for record_index, record in enumerate(records):
        grouped: dict[str, list[float]] = defaultdict(list)
        for trajectory in record["metrics"]["per_trajectory"].values():
            grouped[str(trajectory["layout"])].append(float(trajectory["r2"]))
        require(sorted(grouped) == layouts, "trajectory bootstrap layout mismatch")
        for layout_index, layout in enumerate(layouts):
            require(len(grouped[layout]) == 3, "trajectory bootstrap requires three trajectories per layout")
            values[record_index, layout_index] = grouped[layout]
    require(bool(np.isfinite(values).all()), "trajectory bootstrap values are nonfinite")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, 3, size=(replicates, len(records), 6, 3))
    sampled = np.take_along_axis(values[None, :, :, :], indices, axis=3)
    draws = sampled.mean(axis=(1, 2, 3))
    low, high = np.quantile(draws, [0.025, 0.975], method="linear")
    return [float(low), float(high)]


def _average_ranks(values: Sequence[float]) -> np.ndarray:
    array = finite_vector(values, "rank values")
    order = np.argsort(array, kind="mergesort")
    ranks = np.empty(array.size, dtype=np.float64)
    start = 0
    while start < array.size:
        stop = start + 1
        while stop < array.size and array[order[stop]] == array[order[start]]:
            stop += 1
        ranks[order[start:stop]] = (start + 1 + stop) / 2.0
        start = stop
    return ranks


def spearman_rho(x: Sequence[float], y: Sequence[float]) -> float:
    require(len(x) == len(y) and len(x) >= 2, "Spearman vectors must align")
    x_rank = _average_ranks(x)
    y_rank = _average_ranks(y)
    x_centered = x_rank - x_rank.mean()
    y_centered = y_rank - y_rank.mean()
    denominator = float(np.linalg.norm(x_centered) * np.linalg.norm(y_centered))
    require(denominator > 0.0, "Spearman rank variance is zero")
    return float((x_centered @ y_centered) / denominator)


def empirical_null_evidence(observed: float, null_values: Sequence[float]) -> dict[str, Any]:
    null = np.sort(finite_vector(null_values, "B49 null values"))
    require(null.size == 49, "B must equal 49")
    q95 = float(null[46])
    count_ge = int(np.sum(null >= float(observed)))
    empirical_p = float((1 + count_ge) / 50)
    return {
        "B": 49,
        "count_null_greater_equal_observed": count_ge,
        "empirical_p": empirical_p,
        "observed": float(observed),
        "q95_empirical_nearest_rank": q95,
        "separates": bool(float(observed) > q95 and empirical_p <= 0.05),
        "sorted_null": [float(value) for value in null],
    }


def _records_by_representation(
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {name: [] for name in READINESS_ELIGIBLE}
    for record in documents["P8_LEARNING_RESULTS"]["job_records"]:
        result[str(record["representation"])].append(record)
    result["COARSE_2x6"] = list(documents["P10_COARSE_RESULTS"]["job_records"])
    require(all(result[name] for name in READINESS_ELIGIBLE), "missing representation job records")
    return result


def _normalize_comparison(record: Mapping[str, Any]) -> dict[str, Any]:
    deltas = [float(value) for value in record["paired_deltas"]]
    return {
        **numeric_summary(deltas),
        "interval": [float(value) for value in record["descriptive_mean_bootstrap_95_interval"]],
        "paired_deltas": deltas,
        "subset_ids": list(record["subset_ids"]),
        "win_count": int(sum(value > 0.0 for value in deltas)),
        "win_rate": float(np.mean(np.asarray(deltas) > 0.0)),
    }


def _invert_comparison(record: Mapping[str, Any]) -> dict[str, Any]:
    deltas = [-float(value) for value in record["paired_deltas"]]
    low, high = record["interval"]
    inverted = numeric_summary(deltas)
    return {
        **inverted,
        "interval": [-float(high), -float(low)],
        "paired_deltas": deltas,
        "subset_ids": list(record["subset_ids"]),
        "win_count": int(sum(value > 0.0 for value in deltas)),
        "win_rate": float(np.mean(np.asarray(deltas) > 0.0)),
    }


def _build_comparisons(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    comparisons: dict[str, dict[str, Any]] = {}
    for name, by_n in documents["P8_LEARNING_RESULTS"]["paired_core_comparisons"].items():
        comparisons[name] = {str(n): _normalize_comparison(record) for n, record in by_n.items()}
    coarse_names = {
        "COARSE_MINUS_GLOBAL_MEAN": "COARSE_MINUS_GLOBAL",
        "COARSE_MINUS_FULL_TOKEN_GRID": "COARSE_MINUS_FULL",
        "COARSE_MINUS_BEST_K_TOKENS": "COARSE_MINUS_BEST_K",
    }
    for name, by_n in documents["P10_COARSE_RESULTS"]["matched_p8_deltas"].items():
        canonical_name = coarse_names.get(name)
        require(canonical_name is not None, f"unexpected P10 comparison: {name}")
        comparisons[canonical_name] = {
            str(n): _normalize_comparison(record) for n, record in by_n.items()
        }
    for first, second in (
        ("GLOBAL_MEAN", "FULL_TOKEN_GRID"),
        ("GLOBAL_MEAN", "BEST_K_TOKENS"),
        ("FULL_TOKEN_GRID", "BEST_K_TOKENS"),
        ("GLOBAL_MEAN", "COARSE_2x6"),
        ("FULL_TOKEN_GRID", "COARSE_2x6"),
        ("BEST_K_TOKENS", "COARSE_2x6"),
    ):
        forward = _comparison_key(first, second)
        reverse = _comparison_key(second, first)
        if forward not in comparisons and reverse in comparisons:
            comparisons[forward] = {n: _invert_comparison(record) for n, record in comparisons[reverse].items()}
    return comparisons


def _comparison_key(first: str, second: str) -> str:
    short = {
        "GLOBAL_MEAN": "GLOBAL",
        "FULL_TOKEN_GRID": "FULL",
        "BEST_K_TOKENS": "BEST_K",
        "COARSE_2x6": "COARSE",
    }
    return f"{short[first]}_MINUS_{short[second]}"


def _comparison(summary: Mapping[str, Any], first: str, second: str, n: int) -> Mapping[str, Any]:
    return summary["comparisons"][_comparison_key(first, second)][str(n)]


def _profile_breakdown(
    records: Sequence[Mapping[str, Any]], cohort_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    by_n_and_stratum: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        per_stratum: dict[str, list[float]] = defaultdict(list)
        for identity, metric in record["metrics"]["per_trajectory"].items():
            stratum = str(cohort_by_id[identity]["reporting_stratum"])
            per_stratum[stratum].append(float(metric["r2"]))
        for stratum, values in per_stratum.items():
            by_n_and_stratum[int(record["training_size"])][stratum].append(float(np.mean(values)))
    return {
        str(n): {stratum: numeric_summary(values) for stratum, values in sorted(by_stratum.items())}
        for n, by_stratum in sorted(by_n_and_stratum.items())
    }


def build_canonical_summary(
    documents: Mapping[str, Mapping[str, Any]],
    authority: Mapping[str, Any],
    input_hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Build all continuous evidence exactly once, before adjudication."""

    records = _records_by_representation(documents)
    cohort_by_id = {
        entry["trajectory_spec_id"]: entry for entry in documents["ACCEPTED_COHORT"]["entries"]
    }
    schedule = documents["SUBSET_SCHEDULE"]
    subset_by_id = {record["subset_id"]: record for record in schedule["subsets"]}
    layout_by_id = {identity: record["layout_id"] for identity, record in cohort_by_id.items()}

    learning_representations: dict[str, Any] = {}
    for representation in READINESS_ELIGIBLE:
        source_summaries = (
            documents["P8_LEARNING_RESULTS"]["summaries"][representation]
            if representation in CORE
            else documents["P10_COARSE_RESULTS"]["summaries"]
        )
        by_n: dict[str, Any] = {}
        for anchor_index, n in enumerate(ANCHORS):
            n_records = sorted(
                (record for record in records[representation] if int(record["training_size"]) == n),
                key=lambda record: record["subset_id"],
            )
            upstream = source_summaries[str(n)]
            macro = upstream["macro_r2"]
            interval = upstream.get("mean_r2_trajectory_bootstrap_95_interval")
            if interval is None:
                interval = trajectory_bootstrap_interval(
                    n_records,
                    seed=int(authority["bootstrap"]["base_seed"]),
                    replicates=int(authority["bootstrap"]["replicates"]),
                )
            layouts = sorted(n_records[0]["metrics"]["per_layout"])
            layout_medians = {
                layout: float(
                    np.median([record["metrics"]["per_layout"][layout]["r2"] for record in n_records])
                )
                for layout in layouts
            }
            by_n[str(n)] = {
                "layout_medians": layout_medians,
                "macro_r2": {key: value for key, value in macro.items()},
                "subset_count": len(n_records),
                "subset_ids": [record["subset_id"] for record in n_records],
                "subset_points_r2": [float(record["metrics"]["equal_layout_macro"]["r2"]) for record in n_records],
                "trajectory_bootstrap_95_interval": [float(value) for value in interval],
                "training_frame_count": int(upstream["training_frame_count"]),
                "training_trajectory_count": n,
            }
        learning_representations[representation] = {
            "by_n": by_n,
            "profile_family_breakdown": _profile_breakdown(records[representation], cohort_by_id),
        }

    scaling: dict[str, Any] = {}
    index = {
        (representation, int(record["training_size"]), record["subset_id"]): record
        for representation, rep_records in records.items()
        for record in rep_records
    }
    for representation in READINESS_ELIGIBLE:
        chains = []
        changes = []
        for master_id in COMPLETE_MASTERS:
            subset_ids = {
                int(record["training_size"]): record["subset_id"]
                for record in schedule["subsets"]
                if record["master_id"] == master_id
            }
            require(set(subset_ids) == set(ANCHORS), f"incomplete master chain: {master_id}")
            r2_by_n = {
                str(n): float(index[(representation, n, subset_ids[n])]["metrics"]["equal_layout_macro"]["r2"])
                for n in ANCHORS
            }
            change = r2_by_n["100"] - r2_by_n["5"]
            changes.append(change)
            chains.append({"master_id": master_id, "n100_minus_n5": change, "r2_by_n": r2_by_n, "subset_ids_by_n": {str(n): subset_ids[n] for n in ANCHORS}})
        medians = [learning_representations[representation]["by_n"][str(n)]["macro_r2"]["median"] for n in ANCHORS]
        scaling[representation] = {
            "complete_chain_count": 6,
            "complete_chains": chains,
            "gain_interval": paired_mean_bootstrap_interval(
                changes,
                seed=int(authority["bootstrap"]["chain_gain_rule"]["seed"]),
                replicates=int(authority["bootstrap"]["replicates"]),
            ),
            "gain_summary": numeric_summary(changes),
            "spearman_rho": spearman_rho(ANCHORS, medians),
            "subset_r2_sd_by_n": {str(n): learning_representations[representation]["by_n"][str(n)]["macro_r2"]["sd_ddof1"] for n in ANCHORS},
        }

    comparisons = _build_comparisons(documents)
    p9 = documents["P9_STABILITY"]
    stability = {
        str(n): {
            "median_chance_adjusted_overlap": float(p9["per_n"][str(n)]["pairwise"]["kuncheva_realized_k"]["median"]),
            "median_jaccard": float(p9["per_n"][str(n)]["pairwise"]["jaccard"]["median"]),
            "median_rank_spearman": float(p9["per_n"][str(n)]["pairwise"]["rank_spearman"]["median"]),
            "pair_count": int(p9["per_n"][str(n)]["pairwise"]["pair_count"]),
        }
        for n in ANCHORS
    }

    p11 = documents["P11_CANONICAL_RESULT"]
    canonical_subset = str(p11["canonical_subset_id"])
    null_evidence: dict[str, Any] = {}
    for representation in READINESS_ELIGIBLE:
        null_record = p11["representations"][representation]
        evidence = empirical_null_evidence(
            float(null_record["observed_equal_layout_macro_r2"]),
            null_record["null_equal_layout_macro_r2"],
        )
        require(math.isclose(evidence["empirical_p"], float(null_record["empirical_upper_tail_p"]), rel_tol=0.0, abs_tol=1e-15), f"stored P11 empirical p mismatch: {representation}")
        observed_job = index[(representation, 100, canonical_subset)]
        require(
            math.isclose(
                evidence["observed"],
                float(observed_job["metrics"]["equal_layout_macro"]["r2"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            f"P11 observed statistic does not match canonical upstream job: {representation}",
        )
        per_layout = {
            layout: float(metric["r2"])
            for layout, metric in sorted(observed_job["metrics"]["per_layout"].items())
        }
        evidence["canonical_observed_per_layout_r2"] = per_layout
        evidence["positive_layout_count"] = sum(value > 0.0 for value in per_layout.values())
        null_evidence[representation] = evidence

    n5_omitted = dict(documents["P8_LEARNING_RESULTS"]["n5_omitted_layout_breakdown"])
    coarse_omitted: dict[str, list[float]] = defaultdict(list)
    for record in records["COARSE_2x6"]:
        if int(record["training_size"]) != 5:
            continue
        training_layouts = {layout_by_id[identity] for identity in subset_by_id[record["subset_id"]]["trajectory_spec_ids"]}
        omitted = sorted(set(layout_by_id.values()) - training_layouts)
        require(len(omitted) == 1, "N5 omitted-layout identity mismatch")
        coarse_omitted[omitted[0]].append(float(record["metrics"]["equal_layout_macro"]["r2"]))
    n5_omitted["COARSE_2x6"] = {layout: numeric_summary(values) for layout, values in sorted(coarse_omitted.items())}

    profile_audit = documents["PROFILE_AUDIT"]
    component_gates = {key: bool(value) for key, value in profile_audit["component_gates"].items()}
    profile_controlled = bool(profile_audit.get("trajectory_profile_confound_controlled")) and all(component_gates.values())

    return {
        "artifact_id": "large-scale-no-wall-p13-canonical-summary-v1.0",
        "authority": {
            "artifact_id": authority["artifact_id"],
            "authority_base_commit": authority["authority_base_commit"],
            "input_sha256": dict(sorted(input_hashes.items())),
        },
        "comparisons": comparisons,
        "learning": {
            "anchors": list(ANCHORS),
            "n5_caveat": documents["P8_LEARNING_RESULTS"]["n5_caveat"],
            "n5_omitted_layout_breakdown": n5_omitted,
            "primary_metric": authority["metrics"]["primary"],
            "representations": learning_representations,
        },
        "layout_generalization": {
            "historical_context": "MIXED",
            "known_layout_fixed_test_is_fresh_layout_evidence": False,
            "p12": "DEFERRED_BY_DESIGN",
            "primary_study": "NOT_ADJUDICATED_IN_PRIMARY_STUDY",
        },
        "profile_control": {
            "component_gates": component_gates,
            "trajectory_profile_confound_controlled": profile_controlled,
        },
        "prospective_null": null_evidence,
        "scaling": scaling,
        "schema_version": "1.0",
        "stability": stability,
    }


def _classify(true_condition: bool, false_condition: bool) -> str:
    if true_condition:
        return "True"
    if false_condition:
        return "False"
    return "Unclear"


def _ge(value: float, threshold: float) -> bool:
    """Numerically stable implementation of a frozen inclusive >= boundary."""

    return value > threshold or math.isclose(value, threshold, rel_tol=0.0, abs_tol=1e-12)


def _le(value: float, threshold: float) -> bool:
    """Numerically stable implementation of a frozen inclusive <= boundary."""

    return value < threshold or math.isclose(value, threshold, rel_tol=0.0, abs_tol=1e-12)


def adjudicate(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Apply frozen categorical rules after continuous evidence exists."""

    learning = summary["learning"]["representations"]
    scaling = summary["scaling"]

    scale_components = {}
    for representation in CORE:
        record = scaling[representation]
        by_n = learning[representation]["by_n"]
        qualifies = (
            _ge(record["gain_summary"]["median"], 0.20)
            and _ge(record["spearman_rho"], 0.70)
            and _ge(by_n["70"]["macro_r2"]["median"] - by_n["5"]["macro_r2"]["median"], 0.15)
            and _ge(by_n["100"]["macro_r2"]["median"] - by_n["5"]["macro_r2"]["median"], 0.15)
            and record["gain_interval"][0] > 0.0
        )
        scale_components[representation] = {"qualifies": bool(qualifies)}
    scale_true = sum(record["qualifies"] for record in scale_components.values()) >= 2
    scale_false = all(scaling[r]["gain_summary"]["median"] < 0.10 for r in CORE) and all(_le(scaling[r]["spearman_rho"], 0.30) for r in CORE)

    pooling_components = {}
    for representation in TOKEN_PRESERVING:
        n70 = _comparison(summary, representation, "GLOBAL_MEAN", 70)
        n100 = _comparison(summary, representation, "GLOBAL_MEAN", 100)
        pooling_components[representation] = {
            "supports": bool(_ge(n70["median"], 0.10) and _ge(n100["median"], 0.10) and n100["interval"][0] > 0.0)
        }
    pooling_true = any(record["supports"] for record in pooling_components.values())
    pooling_false_numeric = all(_le(abs(_comparison(summary, r, "GLOBAL_MEAN", n)["median"]), 0.05) for r in TOKEN_PRESERVING for n in HIGH_N)
    pooling_false = pooling_false_numeric and False

    replicated_components = {}
    for representation in TOKEN_PRESERVING:
        replicated = all(_ge(_comparison(summary, representation, "GLOBAL_MEAN", n)["win_rate"], 0.75) for n in TOKEN_REPLICATION_ANCHORS) and _ge(_comparison(summary, representation, "GLOBAL_MEAN", 100)["median"], 0.10)
        replicated_components[representation] = {"replicated": bool(replicated)}
    replicated_true = any(record["replicated"] for record in replicated_components.values())
    replicated_false = all(_le(_comparison(summary, r, "GLOBAL_MEAN", 100)["median"], 0.0) and _le(_comparison(summary, r, "GLOBAL_MEAN", 100)["win_rate"], 0.50) for r in TOKEN_PRESERVING)

    best70 = _comparison(summary, "BEST_K_TOKENS", "FULL_TOKEN_GRID", 70)
    best100 = _comparison(summary, "BEST_K_TOKENS", "FULL_TOKEN_GRID", 100)
    best_true = _ge(best70["median"], 0.05) and _ge(best100["median"], 0.05) and _ge(best70["win_rate"], 0.75) and _ge(best100["win_rate"], 0.75) and best100["interval"][0] > 0.0
    best_false = _le(best100["median"], 0.0) and _le(best100["win_rate"], 0.50)

    stability = summary["stability"]
    stable_true = all(_ge(stability[str(n)]["median_jaccard"], 0.50) and _ge(stability[str(n)]["median_rank_spearman"], 0.50) and stability[str(n)]["median_chance_adjusted_overlap"] > 0.0 for n in HIGH_N)
    stable_false = _le(stability["100"]["median_jaccard"], 0.20) or _le(stability["100"]["median_chance_adjusted_overlap"], 0.0)

    reduced = ("BEST_K_TOKENS", "COARSE_2x6")
    full_true = all(_ge(_comparison(summary, "FULL_TOKEN_GRID", r, n)["median"], 0.05) for r in reduced for n in HIGH_N) and all(_comparison(summary, "FULL_TOKEN_GRID", r, 100)["interval"][0] > 0.0 for r in reduced)
    full_false_numeric = any(_le(_comparison(summary, "FULL_TOKEN_GRID", r, 100)["median"], 0.03) for r in reduced)
    full_false = full_false_numeric and False

    token_medians = {r: learning[r]["by_n"]["100"]["macro_r2"]["median"] for r in ("FULL_TOKEN_GRID", "BEST_K_TOKENS")}
    best_token_median = max(token_medians.values())
    best_token_set = sorted(r for r, value in token_medians.items() if value == best_token_median)
    coarse_deficit = best_token_median - learning["COARSE_2x6"]["by_n"]["100"]["macro_r2"]["median"]
    coarse_numeric_true = _le(coarse_deficit, 0.03) and all(_comparison(summary, "COARSE_2x6", r, 100)["interval"][0] > -0.05 for r in best_token_set)
    coarse_true = coarse_numeric_true and False
    coarse_false = _ge(coarse_deficit, 0.10)

    null = summary["prospective_null"]
    core_observed = {r: null[r]["observed"] for r in CORE}
    best_observed = max(core_observed.values())
    best_observed_core_set = sorted(r for r, value in core_observed.items() if value == best_observed)
    null_components = {
        r: {
            "positive_layout_count": int(null[r]["positive_layout_count"]),
            "qualifies": bool(null[r]["separates"] and null[r]["positive_layout_count"] >= 5),
            "separates": bool(null[r]["separates"]),
        }
        for r in CORE
    }
    qualifying_cores = sorted(r for r in CORE if null_components[r]["qualifies"])
    target_true = len(qualifying_cores) >= 2 and all(r in qualifying_cores for r in best_observed_core_set)
    target_false = not any(null_components[r]["separates"] for r in CORE)
    target_status = _classify(target_true, target_false)

    readiness_components = {}
    for representation in READINESS_ELIGIBLE:
        n100 = learning[representation]["by_n"]["100"]
        positive_count = sum(value > 0.0 for value in n100["layout_medians"].values())
        ready = _ge(n100["macro_r2"]["median"], 0.50) and n100["trajectory_bootstrap_95_interval"][0] > 0.0 and target_status == "True" and positive_count >= 5
        readiness_components[representation] = {"positive_layout_count": positive_count, "ready": bool(ready)}
    readiness_true = any(record["ready"] for record in readiness_components.values())
    max_n100 = max(learning[r]["by_n"]["100"]["macro_r2"]["median"] for r in READINESS_ELIGIBLE)
    readiness_false = _le(max_n100, 0.10) or target_status == "False"

    return {
        "BEST_K_ADVANTAGE": {"classification": _classify(best_true, best_false)},
        "BEST_K_TOKEN_SELECTION_STABLE": {"classification": _classify(stable_true, stable_false)},
        "COARSE_SPATIAL_READOUT_SUFFICIENT": {
            "best_token_set": best_token_set,
            "classification": _classify(coarse_true, coarse_false),
            "qualitative_predicate": "UNRESOLVED",
        },
        "DATA_SCALE_LIMITATION_PLAUSIBLE": {"classification": _classify(scale_true, scale_false), "components": scale_components},
        "FULL_TOKEN_GRID_NEEDED": {"classification": _classify(full_true, full_false), "qualitative_predicate": "UNRESOLVED"},
        "LAYOUT_GENERALIZATION": dict(summary["layout_generalization"]),
        "MEAN_POOLING_BOTTLENECK_PLAUSIBLE": {"classification": _classify(pooling_true, pooling_false), "components": pooling_components, "qualitative_predicate": "UNRESOLVED"},
        "TARGET_SPECIFIC_DECODING_ESTABLISHED": {
            "best_observed_core_set": best_observed_core_set,
            "classification": target_status,
            "components": null_components,
            "qualifying_core_representations": qualifying_cores,
        },
        "TOKEN_PRESERVING_ADVANTAGE_REPLICATED": {"classification": _classify(replicated_true, replicated_false), "components": replicated_components},
        "TRAJECTORY_PROFILE_CONFOUND_CONTROLLED": {"classification": "True" if summary["profile_control"]["trajectory_profile_confound_controlled"] else "False", "components": summary["profile_control"]["component_gates"]},
        "VISIBLE_POSITION_MEASUREMENT_PATH_READY_FOR_OCCLUDED_EXPERIMENT": {"classification": _classify(readiness_true, readiness_false), "components": readiness_components},
    }


def build_output_documents(canonical_summary: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Project all JSON documents from the one canonical summary."""

    require("adjudications" in canonical_summary, "canonical summary is not adjudicated")
    common = {
        "authority": canonical_summary["authority"],
        "schema_version": "1.0",
        "source_canonical_summary_artifact_id": canonical_summary["artifact_id"],
    }
    return {
        "learning_curve_summary.json": {
            **common,
            "artifact_id": "large-scale-no-wall-p13-learning-curve-summary-v1.0",
            "continuous_evidence": {
                "learning": canonical_summary["learning"],
                "scaling": canonical_summary["scaling"],
            },
        },
        "representation_comparison.json": {
            **common,
            "artifact_id": "large-scale-no-wall-p13-representation-comparison-v1.0",
            "continuous_evidence": {
                "comparisons": canonical_summary["comparisons"],
                "stability": canonical_summary["stability"],
            },
        },
        "diagnostic_adjudication.json": {
            **common,
            "artifact_id": "large-scale-no-wall-p13-diagnostic-adjudication-v1.0",
            "continuous_evidence": {
                "layout_generalization": canonical_summary["layout_generalization"],
                "profile_control": canonical_summary["profile_control"],
                "prospective_null": canonical_summary["prospective_null"],
            },
            "categorical_adjudications": canonical_summary["adjudications"],
            "continuous_evidence_precedes_categories": True,
        },
    }


def _render_figures(canonical_summary: Mapping[str, Any], destination: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metadata = {"Software": "MineOcclude P13 deterministic CPU renderer"}
    colors = {
        "GLOBAL_MEAN": "#4C78A8",
        "FULL_TOKEN_GRID": "#F58518",
        "BEST_K_TOKENS": "#54A24B",
        "COARSE_2x6": "#B279A2",
    }
    learning = canonical_summary["learning"]["representations"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for representation in READINESS_ELIGIBLE:
        medians = [learning[representation]["by_n"][str(n)]["macro_r2"]["median"] for n in ANCHORS]
        lows = [learning[representation]["by_n"][str(n)]["trajectory_bootstrap_95_interval"][0] for n in ANCHORS]
        highs = [learning[representation]["by_n"][str(n)]["trajectory_bootstrap_95_interval"][1] for n in ANCHORS]
        axes[0].plot(ANCHORS, medians, marker="o", label=representation, color=colors[representation])
        axes[0].fill_between(ANCHORS, lows, highs, color=colors[representation], alpha=0.15)
        dispersion = [learning[representation]["by_n"][str(n)]["macro_r2"]["sd_ddof1"] for n in ANCHORS]
        axes[1].plot(ANCHORS, dispersion, marker="o", label=representation, color=colors[representation])
    axes[0].axhline(0.0, color="black", linewidth=0.8)
    axes[0].set(title="Fixed-test learning curves", xlabel="Training trajectories", ylabel="Equal-layout macro R2")
    axes[1].set(title="Frozen-subset dispersion", xlabel="Training trajectories", ylabel="Subset R2 SD")
    axes[0].legend(fontsize=8)
    fig.savefig(destination / "p13_learning_curve_decision.png", dpi=150, metadata=metadata)
    plt.close(fig)

    names = ["FULL_MINUS_GLOBAL", "BEST_K_MINUS_GLOBAL", "BEST_K_MINUS_FULL", "FULL_MINUS_COARSE", "BEST_K_MINUS_COARSE"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), constrained_layout=True)
    x = np.arange(len(names))
    for offset, n in enumerate(HIGH_N):
        medians = [canonical_summary["comparisons"][name][str(n)]["median"] for name in names]
        wins = [canonical_summary["comparisons"][name][str(n)]["win_rate"] for name in names]
        axes[0].bar(x + (offset - 0.5) * 0.36, medians, width=0.36, label=f"N={n}")
        axes[1].bar(x + (offset - 0.5) * 0.36, wins, width=0.36, label=f"N={n}")
    for axis in axes:
        axis.set_xticks(x, [name.replace("_MINUS_", " - ") for name in names], rotation=25, ha="right")
        axis.legend()
    axes[0].axhline(0.0, color="black", linewidth=0.8)
    axes[0].set(title="Matched representation deltas", ylabel="Median paired R2 delta")
    axes[1].set(title="Matched-subset win rates", ylabel="Fraction with paired delta > 0", ylim=(0, 1))
    fig.savefig(destination / "p13_representation_comparison_decision.png", dpi=150, metadata=metadata)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    null = canonical_summary["prospective_null"]
    rep_x = np.arange(len(READINESS_ELIGIBLE))
    axes[0].scatter(rep_x, [null[r]["observed"] for r in READINESS_ELIGIBLE], label="Observed", marker="o")
    axes[0].scatter(rep_x, [null[r]["q95_empirical_nearest_rank"] for r in READINESS_ELIGIBLE], label="B49 q95", marker="x")
    axes[0].set_xticks(rep_x, READINESS_ELIGIBLE, rotation=25, ha="right")
    axes[0].set(title="Prospective target-null evidence", ylabel="Equal-layout macro R2")
    axes[0].legend()
    layouts = sorted(next(iter(learning.values()))["by_n"]["100"]["layout_medians"])
    layout_x = np.arange(len(layouts))
    for representation in READINESS_ELIGIBLE:
        axes[1].plot(layout_x, [learning[representation]["by_n"]["100"]["layout_medians"][layout] for layout in layouts], marker="o", label=representation)
    axes[1].set_xticks(layout_x, layouts)
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set(title="N100 layout medians", ylabel="Per-layout R2")
    strata = sorted({stratum for representation in READINESS_ELIGIBLE for stratum in learning[representation]["profile_family_breakdown"]["100"]})
    stratum_x = np.arange(len(strata))
    for representation in READINESS_ELIGIBLE:
        values = [learning[representation]["profile_family_breakdown"]["100"].get(stratum, {}).get("median", np.nan) for stratum in strata]
        axes[2].plot(stratum_x, values, marker="o", label=representation)
    axes[2].set_xticks(stratum_x, strata, rotation=25, ha="right")
    axes[2].axhline(0.0, color="black", linewidth=0.8)
    axes[2].set(title="N100 profile-family breakdown", ylabel="Median trajectory-family R2")
    axes[1].legend(fontsize=7)
    fig.savefig(destination / "p13_null_layout_profile_decision.png", dpi=150, metadata=metadata)
    plt.close(fig)


def render_outputs(
    canonical_summary: Mapping[str, Any], output_root: Path
) -> dict[str, str]:
    """Render deterministic outputs using temp files and atomic rename."""

    output_root.mkdir(parents=True, exist_ok=True)
    ensure_destinations_absent(output_root)
    documents = build_output_documents(canonical_summary)
    with tempfile.TemporaryDirectory(prefix=".p13-staging-", dir=output_root) as staging_name:
        staging = Path(staging_name)
        for filename, document in documents.items():
            (staging / filename).write_bytes(canonical_json_bytes(document))
        _render_figures(canonical_summary, staging)
        hashes = {
            filename: sha256_file(staging / filename)
            for filename in (*documents.keys(), *EXPECTED_OUTPUTS[3:6])
        }
        receipt = {
            "artifact_id": "large-scale-no-wall-p13-receipt-v1.0",
            "authority": canonical_summary["authority"],
            "continuous_evidence_before_classifications": True,
            "cpu_only": True,
            "new_experiment": False,
            "output_sha256": dict(sorted(hashes.items())),
            "schema_version": "1.0",
            "scientific_interpretation_performed": True,
            "single_canonical_summary_artifact_id": canonical_summary["artifact_id"],
            "status": "PASS_P13_COMPLETE",
            "upstream_results_modified": False,
        }
        (staging / "p13_receipt.json").write_bytes(canonical_json_bytes(receipt))
        for filename in EXPECTED_OUTPUTS:
            os.replace(staging / filename, output_root / filename)
    return {filename: sha256_file(output_root / filename) for filename in EXPECTED_OUTPUTS}


def run(status_root: Path, p11_root: Path, output_root: Path) -> dict[str, str]:
    authority = validate_authority(status_root)
    paths = validate_inputs(authority, status_root, p11_root)
    ensure_destinations_absent(output_root)
    documents = load_inputs(paths)
    validate_loaded_inputs(documents)
    hashes = {identity: sha256_file(path) for identity, path in paths.items()}
    canonical = build_canonical_summary(documents, authority, hashes)
    canonical["adjudications"] = adjudicate(canonical)
    return render_outputs(canonical, output_root)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run CPU-only P13 adjudication from validated compact P8-P12 authorities."
    )
    parser.add_argument("--status-root", type=Path, default=DEFAULT_STATUS_ROOT)
    parser.add_argument("--p11-root", type=Path, default=DEFAULT_P11_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_STATUS_ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    hashes = run(args.status_root.resolve(), args.p11_root.resolve(), args.output_root.resolve())
    print(json.dumps({"status": "PASS_P13_COMPLETE", "output_sha256": hashes}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
