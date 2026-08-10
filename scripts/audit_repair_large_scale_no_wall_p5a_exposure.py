#!/usr/bin/env python3
"""Audit and, if feasible, repair P5 trajectory-exposure imbalance.

The optimization is metadata-only and outcome-blind.  It keeps the P5 split,
scientific anchors, category-balance envelopes, N=5 omission schedule, and the
six N=100 omitted pairs fixed while asking whether every exposure range can
attain its arithmetic lower bound of one.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
P5_HEAD = "e94f977e000242af055d56402aa68ba164da2982"
P5_SCRIPT = ROOT / "scripts/freeze_large_scale_no_wall_p5_authority.py"
SPEC = importlib.util.spec_from_file_location("p5_historical_generator", P5_SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load historical P5 generator")
p5 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p5)

ORIGINAL_P5_HASHES = {
    "split_authority.json": (
        "b39c81454ea18125c373fb3c777ac4c1668882c9c1ad188a7d0f20e0cab43de5"
    ),
    "subset_schedule.json": (
        "4406fc5c099cb041a5707088bc7d69ea522d605e8060477679f105a400031bd1"
    ),
    "grouped_fold_authority.json": (
        "15cd4e05f59f857afe80ec4e4b981c78cacf513a3699272a4cabc70d6b23d060"
    ),
    "test_guard.lock": (
        "0adc85a5d90eb92361ba0775d58a6ccc2eb674a8ae5ffd2e816b89d9d9b48ac5"
    ),
    "canonical_null_authority.json": (
        "11e59a2b8df90fce407d72a9f7e25549e78f240c7c49f6dd6aa0995c242182ff"
    ),
    "p5_balance_audit.json": (
        "b72273b376ad25633a6140ba003d435c69d562f11ba03477e3c10964b9f6f6b4"
    ),
    "p5_receipt.json": (
        "4da29206943e5e35204a4a96ef6d657212505765edd0e9565f9e938078e1fdfd"
    ),
}
ARITHMETIC = {
    5: {"replicates": 20, "total": 100, "low": 0, "high": 1},
    15: {"replicates": 16, "total": 240, "low": 2, "high": 3},
    40: {"replicates": 12, "total": 480, "low": 4, "high": 5},
    70: {"replicates": 8, "total": 560, "low": 5, "high": 6},
    100: {"replicates": 6, "total": 600, "low": 5, "high": 6},
}
ORIGINAL_EXPOSURE = {
    "5": {"minimum": 0, "maximum": 2, "range": 2},
    "15": {"minimum": 1, "maximum": 3, "range": 2},
    "40": {"minimum": 3, "maximum": 6, "range": 3},
    "70": {"minimum": 4, "maximum": 6, "range": 2},
    "100": {"minimum": 5, "maximum": 6, "range": 1},
}
REPLACE_NAMES = (
    "subset_schedule.json",
    "grouped_fold_authority.json",
    "p5_balance_audit.json",
    "p5_receipt.json",
)
NEW_NAMES = (
    "p5a_exposure_feasibility_audit.json",
    "p5a_receipt.json",
)


class P5AError(RuntimeError):
    """Raised when P5A authority cannot be proven or repaired safely."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P5AError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON authority is not an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return p5.json_bytes(value)


def write_json_replace(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".p5a.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def write_json_new(path: Path, value: Any) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def verify_start_authority() -> None:
    for name, expected in ORIGINAL_P5_HASHES.items():
        require(
            sha256_file(PACKAGE / name) == expected, f"P5 authority changed: {name}"
        )
    receipt = read_json(PACKAGE / "p5_receipt.json")
    require(
        receipt["status"] == "PASS_SPLIT_AND_LEARNING_CURVE_AUTHORITY_FROZEN",
        "P5 did not pass",
    )
    require(
        receipt["fresh_activations_extracted"] == 0
        and receipt["fresh_r2_computed"] is False
        and receipt["p6_started"] is False,
        "model work exists before P5A",
    )
    require(not list(PACKAGE.glob("p6*")), "P6 artifact exists before P5A")
    for name in NEW_NAMES:
        require(not (PACKAGE / name).exists(), f"refusing to overwrite {name}")


def arithmetic_lower_bounds() -> dict[str, dict[str, int]]:
    result = {}
    for size, row in ARITHMETIC.items():
        low_count = 102 - (row["total"] % 102)
        high_count = row["total"] % 102
        result[str(size)] = {
            "pool_size": 102,
            "replicate_count": row["replicates"],
            "total_selections": row["total"],
            "ideal_low_exposure": row["low"],
            "ideal_high_exposure": row["high"],
            "ideal_low_exposure_trajectory_count": low_count,
            "ideal_high_exposure_trajectory_count": high_count,
            "unconstrained_minimum_range": 1,
        }
    return result


def _original_memberships(
    schedule: Mapping[str, Any],
) -> dict[tuple[int, int], set[str]]:
    result = {}
    for subset in schedule["subsets"]:
        result[(int(subset["replicate"]), int(subset["training_size"]))] = set(
            subset["trajectory_spec_ids"]
        )
    return result


def optimize_prefix_memberships(
    split: Mapping[str, Any], original_schedule: Mapping[str, Any]
) -> dict[str, Any]:
    """Solve the full frozen prefix-membership feasibility problem twice.

    Pass one maximizes original membership retention.  Pass two fixes that
    optimum and uses deterministic SHA-derived costs as a final tie-break.
    """
    training_ids = sorted(
        row["trajectory_spec_id"] for row in split["training_pool"]["members"]
    )
    index = split["member_index"]
    pairs = [
        (replicate, size)
        for size, replicate_count in zip(
            p5.TRAINING_SIZES, p5.SUBSET_REPLICATES, strict=True
        )
        for replicate in range(replicate_count)
    ]
    pair_position = {pair: position for position, pair in enumerate(pairs)}
    trajectory_position = {
        identity: position for position, identity in enumerate(training_ids)
    }
    width = len(training_ids)
    variable_count = len(pairs) * width

    def variable(pair: tuple[int, int], identity: str) -> int:
        return pair_position[pair] * width + trajectory_position[identity]

    original = _original_memberships(original_schedule)
    lower_bounds = np.zeros(variable_count, dtype=np.float64)
    upper_bounds = np.ones(variable_count, dtype=np.float64)
    for replicate in range(6):
        membership = original[(replicate, 100)]
        for identity in training_ids:
            position = variable((replicate, 100), identity)
            fixed = 1.0 if identity in membership else 0.0
            lower_bounds[position] = fixed
            upper_bounds[position] = fixed

    matrix_rows: list[int] = []
    matrix_columns: list[int] = []
    matrix_values: list[float] = []
    constraint_lower: list[float] = []
    constraint_upper: list[float] = []

    def add_constraint(
        coefficients: Mapping[int, float], lower: float, upper: float
    ) -> None:
        row_index = len(constraint_lower)
        for column, value in coefficients.items():
            matrix_rows.append(row_index)
            matrix_columns.append(column)
            matrix_values.append(value)
        constraint_lower.append(lower)
        constraint_upper.append(upper)

    for pair in pairs:
        add_constraint(
            {variable(pair, identity): 1.0 for identity in training_ids},
            pair[1],
            pair[1],
        )

    for size, row in ARITHMETIC.items():
        active = range(row["replicates"])
        for identity in training_ids:
            add_constraint(
                {variable((replicate, size), identity): 1.0 for replicate in active},
                row["low"],
                row["high"],
            )

    for replicate in range(20):
        active_sizes = [
            size
            for size, replicate_count in zip(
                p5.TRAINING_SIZES, p5.SUBSET_REPLICATES, strict=True
            )
            if replicate < replicate_count
        ]
        for smaller, larger in zip(active_sizes, active_sizes[1:]):
            for identity in training_ids:
                add_constraint(
                    {
                        variable((replicate, smaller), identity): 1.0,
                        variable((replicate, larger), identity): -1.0,
                    },
                    -np.inf,
                    0.0,
                )

    fields = ("layout_id", "direction", "reporting_stratum", "repeat_id")
    categories = {
        field: sorted({index[identity][field] for identity in training_ids}, key=str)
        for field in fields
    }
    for pair in pairs:
        original_rows = [index[identity] for identity in original[pair]]
        for field in fields:
            original_counts = Counter(row[field] for row in original_rows)
            values = [original_counts[value] for value in categories[field]]
            envelope_low, envelope_high = min(values), max(values)
            for category in categories[field]:
                category_ids = [
                    identity
                    for identity in training_ids
                    if index[identity][field] == category
                ]
                lower = envelope_low
                upper = envelope_high
                if pair[1] == 5 and field == "layout_id":
                    fixed = int(original_counts[category] == 1)
                    lower = upper = fixed
                add_constraint(
                    {variable(pair, identity): 1.0 for identity in category_ids},
                    lower,
                    upper,
                )

    matrix = coo_matrix(
        (matrix_values, (matrix_rows, matrix_columns)),
        shape=(len(constraint_lower), variable_count),
    ).tocsr()
    base_constraints = LinearConstraint(
        matrix,
        np.asarray(constraint_lower, dtype=np.float64),
        np.asarray(constraint_upper, dtype=np.float64),
    )
    original_vector = np.zeros(variable_count, dtype=np.float64)
    tie_cost = np.empty(variable_count, dtype=np.float64)
    for pair in pairs:
        for identity in training_ids:
            position = variable(pair, identity)
            original_vector[position] = float(identity in original[pair])
            digest = hashlib.sha256(
                f"p5a-exposure-v0.1|{pair[0]}|{pair[1]}|{identity}".encode()
            ).digest()
            tie_cost[position] = int.from_bytes(digest[:8], "big") / 2**64
    common = {
        "integrality": np.ones(variable_count, dtype=np.uint8),
        "bounds": Bounds(lower_bounds, upper_bounds),
        "options": {"presolve": True, "time_limit": 180.0, "mip_rel_gap": 0.0},
    }
    retention = milp(
        c=-original_vector,
        constraints=base_constraints,
        **common,
    )
    require(retention.success and retention.x is not None, "range-one MILP infeasible")
    retained = int(round(float(original_vector @ np.rint(retention.x))))
    overlap_constraint = LinearConstraint(
        original_vector.reshape(1, -1), retained, retained
    )
    tied = milp(
        c=tie_cost,
        constraints=(base_constraints, overlap_constraint),
        **common,
    )
    require(tied.success and tied.x is not None, "deterministic tie-break MILP failed")
    solution = np.rint(tied.x).astype(np.int8)
    memberships = {
        pair: {
            identity
            for identity in training_ids
            if solution[variable(pair, identity)] == 1
        }
        for pair in pairs
    }
    return {
        "memberships": memberships,
        "solver": {
            "implementation": "scipy.optimize.milp/HiGHS",
            "scipy_version": __import__("scipy").__version__,
            "variable_count": variable_count,
            "constraint_count": len(constraint_lower) + 1,
            "retained_original_memberships": retained,
            "total_anchor_memberships": int(sum(pair[1] for pair in pairs)),
            "first_pass_status": int(retention.status),
            "second_pass_status": int(tied.status),
            "first_pass_message": retention.message,
            "second_pass_message": tied.message,
            "optimal": True,
        },
    }


def build_orderings(
    split: Mapping[str, Any],
    original_schedule: Mapping[str, Any],
    memberships: Mapping[tuple[int, int], set[str]],
) -> list[dict[str, Any]]:
    training_ids = {
        row["trajectory_spec_id"] for row in split["training_pool"]["members"]
    }
    original_masters = {
        row["master_id"]: row for row in original_schedule["master_orderings"]
    }
    result = []
    for replicate in range(20):
        master_id = f"master_{replicate:02d}"
        original = original_masters[master_id]
        original_rank = {
            identity: position
            for position, identity in enumerate(original["trajectory_spec_ids"])
        }
        active_sizes = [
            size
            for size, replicate_count in zip(
                p5.TRAINING_SIZES, p5.SUBSET_REPLICATES, strict=True
            )
            if replicate < replicate_count
        ]
        ordering = []
        previous: set[str] = set()
        for size in active_sizes:
            layer = memberships[(replicate, size)] - previous
            ordering.extend(sorted(layer, key=original_rank.__getitem__))
            previous = set(memberships[(replicate, size)])
            require(
                set(ordering) == previous, f"non-nested optimized layer: {master_id}"
            )
        ordering.extend(sorted(training_ids - previous, key=original_rank.__getitem__))
        require(len(ordering) == len(set(ordering)) == 102, "optimized master differs")
        for size in active_sizes:
            require(
                set(ordering[:size]) == memberships[(replicate, size)],
                f"optimized prefix mismatch: {master_id} N={size}",
            )
        result.append(
            {
                "master_id": master_id,
                "master_seed": original["master_seed"],
                "selected_rotation": original["selected_rotation"],
                "trajectory_spec_ids": ordering,
                "ordering_hash": p5.canonical_sha256(ordering),
                "p5a_ordering_rule": (
                    "MILP-optimized nested membership layers; original master rank "
                    "is the deterministic within-layer order."
                ),
            }
        )
    return result


def build_repaired_documents() -> dict[str, dict[str, Any]]:
    historical = p5.build_documents()
    split = historical["split_authority.json"]
    original_schedule = historical["subset_schedule.json"]
    optimization = optimize_prefix_memberships(split, original_schedule)
    masters = build_orderings(split, original_schedule, optimization["memberships"])
    subsets = []
    for size, replicate_count in zip(
        p5.TRAINING_SIZES, p5.SUBSET_REPLICATES, strict=True
    ):
        for replicate in range(replicate_count):
            identities = masters[replicate]["trajectory_spec_ids"][:size]
            subsets.append(
                {
                    "subset_id": p5.subset_id(size, replicate),
                    "training_size": size,
                    "replicate": replicate,
                    "master_id": f"master_{replicate:02d}",
                    "membership_rule": "nested prefix of referenced master ordering",
                    "trajectory_spec_ids": identities,
                    "subset_hash": p5.canonical_sha256(identities),
                }
            )
    result_schedules = [
        {
            "size": row["training_size"],
            "members": [
                split["member_index"][identity]
                for identity in row["trajectory_spec_ids"]
            ],
        }
        for row in subsets
    ]
    training = split["training_pool"]["members"]
    final_exposure = p5.exposure_by_size(result_schedules, training)
    require(
        all(row["range"] <= 1 for row in final_exposure.values()),
        "optimized schedule did not attain range one",
    )
    schedule = {
        **original_schedule,
        "schema_version": "large-scale-no-wall-p5-subset-schedule-v0.2",
        "status": "FROZEN_PROSPECTIVE_AMENDED_BY_P5A_EXPOSURE_REPAIR",
        "master_orderings": masters,
        "subsets": subsets,
        "training_exposure_by_n": final_exposure,
        "p5a_amendment": {
            "reason": "Original greedy rotation schedule missed feasible arithmetic exposure lower bounds.",
            "selected_response": "CURRENT_SCHEDULE_EXPOSURE_IMBALANCE_AVOIDABLE",
            "model_outcomes_available": False,
            "activations_available": False,
            "original_subset_schedule_sha256": ORIGINAL_P5_HASHES[
                "subset_schedule.json"
            ],
        },
    }
    grouped = p5.grouped_fold_document(subsets, split["member_index"])
    grouped.update(
        {
            "schema_version": "large-scale-no-wall-p5-grouped-fold-authority-v0.2",
            "status": "FROZEN_PROSPECTIVE_AMENDED_BY_P5A_EXPOSURE_REPAIR",
            "p5a_amendment": {
                "membership_source": "subset_schedule.json v0.2",
                "original_grouped_fold_authority_sha256": ORIGINAL_P5_HASHES[
                    "grouped_fold_authority.json"
                ],
            },
        }
    )
    original_balance = historical["p5_balance_audit.json"]
    balance = {
        **original_balance,
        "schema_version": "large-scale-no-wall-p5-balance-audit-v0.2",
        "status": "PASS_P5A_EXPOSURE_REPAIRED",
        "training_exposure_by_n": final_exposure,
        "p5a_selected_response": "CURRENT_SCHEDULE_EXPOSURE_IMBALANCE_AVOIDABLE",
        "original_training_exposure_by_n": ORIGINAL_EXPOSURE,
    }
    repaired = {
        "subset_schedule.json": schedule,
        "grouped_fold_authority.json": grouped,
        "p5_balance_audit.json": balance,
    }
    canonical = historical["canonical_null_authority.json"]
    repaired_n100 = next(row for row in subsets if row["subset_id"] == "n100_r00")
    require(
        set(repaired_n100["trajectory_spec_ids"])
        == set(canonical["canonical_training_trajectory_ids"]),
        "canonical N100 membership changed",
    )
    validation_canonical = {
        **canonical,
        "canonical_training_trajectory_ids": repaired_n100["trajectory_spec_ids"],
        "canonical_subset_hash": repaired_n100["subset_hash"],
    }
    p5.validate_documents(
        {
            "split_authority.json": split,
            "subset_schedule.json": schedule,
            "grouped_fold_authority.json": grouped,
            "test_guard.lock": historical["test_guard.lock"],
            "canonical_null_authority.json": validation_canonical,
            "p5_balance_audit.json": balance,
        }
    )
    audit = {
        "schema_version": "large-scale-no-wall-p5a-exposure-feasibility-audit-v0.1",
        "status": "PASS_REPAIR_REQUIRED_AND_CONSTRUCTED",
        "p5_head": P5_HEAD,
        "outcome_blind": True,
        "model_outcomes_available": False,
        "fresh_activations_extracted": 0,
        "fresh_r2_computed": False,
        "arithmetic_lower_bounds": arithmetic_lower_bounds(),
        "original_exposure_by_n": ORIGINAL_EXPOSURE,
        "full_constraint_feasibility_result": (
            "FEASIBLE_RANGE_ONE_AT_EVERY_N_WITH_ALL_FROZEN_CONSTRAINTS"
        ),
        "selected_response": "CURRENT_SCHEDULE_EXPOSURE_IMBALANCE_AVOIDABLE",
        "repair_performed": True,
        "final_exposure_by_n": final_exposure,
        "optimization": optimization["solver"],
        "constraints_preserved": {
            "fixed_test_ids": True,
            "training_pool_ids": True,
            "nested_prefixes": True,
            "training_sizes_and_replicates": True,
            "n5_exactly_five_layouts": True,
            "n5_original_omission_sequence_and_counts": True,
            "n_ge_15_all_layouts": True,
            "original_per_subset_layout_direction_reporting_repeat_envelopes": True,
            "six_original_distinct_n100_omitted_pairs": True,
            "six_complete_chains": True,
            "whole_trajectory_grouping": True,
            "test_guard_scientific_meaning": True,
            "canonical_null_membership": True,
        },
        "original_p5_artifact_sha256": dict(sorted(ORIGINAL_P5_HASHES.items())),
    }
    repaired["p5a_exposure_feasibility_audit.json"] = audit
    artifact_sha256 = {
        name: hashlib.sha256(json_bytes(value)).hexdigest()
        for name, value in {
            "split_authority.json": split,
            **repaired,
            "test_guard.lock": historical["test_guard.lock"],
            "canonical_null_authority.json": canonical,
        }.items()
    }
    receipt = {
        **historical["p5_receipt.json"],
        "schema_version": "large-scale-no-wall-p5-receipt-v0.2",
        "status": "PASS_SPLIT_AUTHORITY_AMENDED_BY_P5A_EXPOSURE_REPAIR",
        "p5a_selected_response": "CURRENT_SCHEDULE_EXPOSURE_IMBALANCE_AVOIDABLE",
        "p5a_repair_performed": True,
        "training_exposure_by_n": final_exposure,
        "artifact_paths": [
            *historical["p5_receipt.json"]["artifact_paths"],
            "p5a_exposure_feasibility_audit.json",
            "p5a_receipt.json",
        ],
        "artifact_sha256": dict(sorted(artifact_sha256.items())),
    }
    repaired["p5_receipt.json"] = receipt
    resulting_hashes = {
        name: hashlib.sha256(json_bytes(value)).hexdigest()
        for name, value in {
            "split_authority.json": split,
            "subset_schedule.json": schedule,
            "grouped_fold_authority.json": grouped,
            "test_guard.lock": historical["test_guard.lock"],
            "canonical_null_authority.json": canonical,
            "p5_balance_audit.json": balance,
            "p5_receipt.json": receipt,
            "p5a_exposure_feasibility_audit.json": audit,
        }.items()
    }
    repaired["p5a_receipt.json"] = {
        "schema_version": "large-scale-no-wall-p5a-receipt-v0.1",
        "status": "PASS_PROSPECTIVE_EXPOSURE_SCHEDULE_REPAIRED",
        "p5_head": P5_HEAD,
        "selected_response": "CURRENT_SCHEDULE_EXPOSURE_IMBALANCE_AVOIDABLE",
        "repair_performed": True,
        "fixed_test_unchanged": True,
        "training_pool_unchanged": True,
        "original_p5_artifact_sha256": dict(sorted(ORIGINAL_P5_HASHES.items())),
        "resulting_p5_artifact_sha256": dict(sorted(resulting_hashes.items())),
        "model_outcomes_available": False,
        "fresh_activations_extracted": 0,
        "fresh_r2_computed": False,
        "p6_started": False,
        "safe_for_p6": True,
        "blocker": None,
        "artifact_paths": [
            "p5a_exposure_feasibility_audit.json",
            "p5a_receipt.json",
        ],
    }
    return repaired


def main() -> int:
    verify_start_authority()
    repaired = build_repaired_documents()
    for name in (
        "subset_schedule.json",
        "grouped_fold_authority.json",
        "p5_balance_audit.json",
        "p5a_exposure_feasibility_audit.json",
        "p5_receipt.json",
        "p5a_receipt.json",
    ):
        path = PACKAGE / name
        if name in NEW_NAMES:
            write_json_new(path, repaired[name])
        else:
            write_json_replace(path, repaired[name])
    print(
        "P5A_STATUS=PASS_PROSPECTIVE_EXPOSURE_SCHEDULE_REPAIRED "
        "selected_response=CURRENT_SCHEDULE_EXPOSURE_IMBALANCE_AVOIDABLE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
