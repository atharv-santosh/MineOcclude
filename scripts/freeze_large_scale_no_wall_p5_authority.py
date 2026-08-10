#!/usr/bin/env python3
"""Freeze P5 split, subset, grouped-fold, guard, and null authority.

This program is metadata-only and outcome-blind.  It reads the accepted V2
cohort lock and frozen P1 algorithms; it does not read raw frames, activations,
hidden states, probe results, or fixed-test performance.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
P4C_HEAD = "9f2ba9c5796cd022c6efd83bba500f14c452f58f"
PRIMARY_LOCK_NAME = "accepted_cohort_v2.lock.json"
LAYOUTS = ("L01", "L02", "L03", "L04", "L05", "L06")
TRAINING_SIZES = (5, 15, 40, 70, 100)
SUBSET_REPLICATES = (20, 16, 12, 8, 6)
SELECTION_FOLD_COUNT = 5
BEST_K_CANDIDATES = (1, 4, 8, 16, 32, 64, 128)
ALPHA_GRID = (0.1, 1.0, 10.0, 100.0)
OUTPUT_NAMES = (
    "split_authority.json",
    "subset_schedule.json",
    "grouped_fold_authority.json",
    "test_guard.lock",
    "canonical_null_authority.json",
    "p5_balance_audit.json",
    "p5_receipt.json",
)
PROTECTED_HASHES = {
    "capture_campaign.json": (
        "1605f4738840ea531e73fdcee19536d55652a1a05ddef704304adcb1bc41cdd6"
    ),
    "capture_campaign.lock.json": (
        "479471d468598d93d861767ffa83b3e0bd1c401dbd3310cfcb509ecf7ced22aa"
    ),
    "study_design.json": (
        "08d77261f70a3d7e554ce6f8fe4a565fa09591ae793a87efd60e4a742c016502"
    ),
    "study_design.lock.json": (
        "05b337e81ffea6c6d3bb3f92ca76b7774c980f9c462565f5c50a71ad9f629f41"
    ),
    "seed_manifest.json": (
        "d84df8833f8c16497e8ca5f3fcf58142ec1770fa8f3da1d61fc81b320b098d8f"
    ),
    "split_algorithm.json": (
        "abce2236e6544356f2cb5d8913a8f29b03bb481487a89be548cf6f27e5f26b81"
    ),
    "p4_receipt.json": (
        "91642203ff2b4d4318d953e1d97b44ccf82049c257fe4d2e6025fd31519a942e"
    ),
    "p4b_receipt.json": (
        "e8c3919cb9773cc08ff36638f0ea052985ef73a45131afc94a0414fde0acee65"
    ),
    "capture_campaign_v2.json": (
        "adb1eb0611d9cf05d221db6d2040eb65f50a0d5fb4dab32f6bdd3d585484ef9f"
    ),
    "capture_campaign_v2.lock.json": (
        "1acdc0fdd593c5f6f90f2d5dd2173f0d1db2199bff6e4741c3a3c019bec0b759"
    ),
    "accepted_cohort_v2.lock.json": (
        "b73d1b6bbedc1ca72dab480ba6f4bafb22aa7c6675bc7a2f0dabf33fff2d8501"
    ),
    "p4c_receipt.json": (
        "11358dd7fc1c882c7407c582e17222092f2111b48fbc2c4c8d6339d8ac8358e2"
    ),
}


class P5Error(RuntimeError):
    """Raised when frozen P5 authority cannot be applied exactly."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P5Error(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON authority is not an object: {path}")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def write_json_new(path: Path, value: Any) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def blocked_hash(seed: int, *parts: object) -> str:
    joined = "|".join([str(seed), *(str(part) for part in parts)])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def verify_git_ancestor(commit: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def verify_protected_authority() -> None:
    for name, expected in PROTECTED_HASHES.items():
        require(sha256_file(PACKAGE / name) == expected, f"authority changed: {name}")
    study = read_json(PACKAGE / "study_design.json")
    lineage = study["lineage"]
    require(
        verify_git_ancestor(lineage["predecessor_sha"]),
        "predecessor is not an ancestor",
    )
    require(
        verify_git_ancestor(lineage["frozen_mvp_sha"]),
        "frozen MVP is not an ancestor",
    )
    p4c = read_json(PACKAGE / "p4c_receipt.json")
    require(
        p4c["fresh_activations_extracted"] == 0
        and p4c["fresh_r2_computed"] is False
        and p4c["p5_started"] is False,
        "P4C phase boundary changed",
    )
    require(not list(PACKAGE.glob("p6*")), "P6 artifact exists before P5 freeze")


def load_primary_cohort() -> list[dict[str, Any]]:
    lock = read_json(PACKAGE / PRIMARY_LOCK_NAME)
    entries = lock["entries"]
    require(lock["entry_count"] == len(entries) == 120, "V2 lock count mismatch")
    require(lock["v1_entries_included"] == 0, "V1 included in V2 lock")
    require(
        lock["contains_train_test_assignments"] is False,
        "P4C lock already contains a split",
    )
    required = {
        "trajectory_spec_id",
        "spec_hash",
        "accepted_attempt",
        "layout_id",
        "direction",
        "trajectory_shape_class",
        "reporting_stratum",
        "repeat_id",
        "capture_seed",
        "target_authority",
    }
    for row in entries:
        require(required <= row.keys(), f"V2 lock metadata incomplete: {row}")
        require(
            row["trajectory_spec_id"].startswith("fresh_vp_v2_"),
            "non-V2 trajectory in primary lock",
        )
        require(
            row["target_authority"]["row_count"] == 60
            and len(row["target_authority"]["x_true_blocks"]) == 60,
            f"target authority is not 60 rows: {row['trajectory_spec_id']}",
        )
    require(
        Counter(row["layout_id"] for row in entries)
        == Counter({layout: 20 for layout in LAYOUTS}),
        "primary layout balance changed",
    )
    return entries


def split_metadata(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Apply the committed P4B compatibility mapping for P1 split semantics."""
    return [
        {
            **dict(row),
            "profile_family": row["reporting_stratum"],
        }
        for row in entries
    ]


def choose_fixed_test(
    metadata: Sequence[Mapping[str, Any]], seed: int
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Literal P1 exhaustive blocked-hash test allocation."""
    selected = []
    for layout in LAYOUTS:
        rows = [row for row in metadata if row["layout_id"] == layout]
        require(len(rows) == 20, f"expected 20 primary rows for {layout}")

        def score(group: tuple[Mapping[str, Any], ...]) -> tuple[Any, ...]:
            directions = Counter(row["direction"] for row in group)
            repeats = Counter(row["repeat_id"] for row in group)
            profile_duplicate_penalty = 3 - len(
                {row["profile_family"] for row in group}
            )
            direction_imbalance = abs(
                directions["LEFT_TO_RIGHT"] - directions["RIGHT_TO_LEFT"]
            )
            repeat_imbalance = abs(repeats[1] - repeats[2])
            identity = ",".join(sorted(str(row["trajectory_spec_id"]) for row in group))
            return (
                profile_duplicate_penalty,
                direction_imbalance,
                repeat_imbalance,
                blocked_hash(seed, layout, identity),
            )

        selected.extend(min(itertools.combinations(rows, 3), key=score))
    selected_ids = {row["trajectory_spec_id"] for row in selected}
    training = [
        row for row in metadata if row["trajectory_spec_id"] not in selected_ids
    ]
    return selected, training


def master_ordering(
    training: Sequence[Mapping[str, Any]],
    master_index: int,
    rank_seed: int,
    rotation: int,
) -> list[Mapping[str, Any]]:
    """Literal P1 blocked rank, cyclic rotation, interleave, and tail rule."""
    queues: dict[str, list[Mapping[str, Any]]] = {}
    for layout in LAYOUTS:
        rows = [row for row in training if row["layout_id"] == layout]
        require(len(rows) == 17, f"training pool is not 17 for {layout}")
        queues[layout] = sorted(
            rows,
            key=lambda row: blocked_hash(
                rank_seed, "training-rank", layout, row["trajectory_spec_id"]
            ),
        )
        shift = (rotation + 3 * LAYOUTS.index(layout)) % len(rows)
        queues[layout] = queues[layout][shift:] + queues[layout][:shift]
    omitted_at_five = LAYOUTS[master_index % len(LAYOUTS)]
    other_layouts = [layout for layout in LAYOUTS if layout != omitted_at_five]
    shift = master_index % len(other_layouts)
    layout_order = other_layouts[shift:] + other_layouts[:shift] + [omitted_at_five]
    tail_pair = (LAYOUTS[master_index % 6], LAYOUTS[(master_index + 1) % 6])
    reserved = [queues[layout].pop() for layout in tail_pair]
    result = []
    while any(queues.values()):
        for layout in layout_order:
            if queues[layout]:
                result.append(queues[layout].pop(0))
    result.extend(reserved)
    require(len(result) == 102, "master ordering length differs")
    return result


def build_split(
    metadata: Sequence[Mapping[str, Any]],
    split_seed: int,
    master_seeds: Sequence[int],
) -> dict[str, Any]:
    """Literal P1 exposure-aware selection of 20 master rotations."""
    test, training = choose_fixed_test(metadata, split_seed)
    training_ids = [str(row["trajectory_spec_id"]) for row in training]
    exposure: Counter[str] = Counter({identity: 0 for identity in training_ids})
    masters = []
    rotations = []
    for index in range(20):
        active_sizes = [
            size
            for size, replicate_count in zip(
                TRAINING_SIZES, SUBSET_REPLICATES, strict=True
            )
            if index < replicate_count
        ]
        candidates = []
        for rotation in range(17):
            ordering = master_ordering(training, index, split_seed, rotation)
            contribution: Counter[str] = Counter()
            for size in active_sizes:
                contribution.update(
                    str(row["trajectory_spec_id"]) for row in ordering[:size]
                )
            projected = [
                exposure[identity] + contribution[identity] for identity in training_ids
            ]
            total = sum(projected)
            score = (
                max(projected) - min(projected),
                sum((value * len(projected) - total) ** 2 for value in projected),
                blocked_hash(master_seeds[index], "rotation", rotation),
            )
            candidates.append((score, rotation, ordering, contribution))
        _, selected_rotation, selected_ordering, contribution = min(
            candidates, key=lambda row: row[0]
        )
        rotations.append(selected_rotation)
        masters.append(selected_ordering)
        exposure.update(contribution)
    schedules = []
    for size, replicate_count in zip(TRAINING_SIZES, SUBSET_REPLICATES, strict=True):
        for replicate in range(replicate_count):
            schedules.append(
                {
                    "size": size,
                    "replicate": replicate,
                    "master_id": f"master_{replicate:02d}",
                    "members": masters[replicate][:size],
                }
            )
    return {
        "test": test,
        "training": training,
        "masters": masters,
        "master_rotations": rotations,
        "training_exposure": dict(exposure),
        "schedules": schedules,
    }


def compact_member(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "trajectory_spec_id": row["trajectory_spec_id"],
        "spec_hash": row["spec_hash"],
        "accepted_attempt": row["accepted_attempt"],
        "layout_id": row["layout_id"],
        "direction": row["direction"],
        "reporting_stratum": row["reporting_stratum"],
        "trajectory_shape_class": row["trajectory_shape_class"],
        "repeat_id": row["repeat_id"],
    }


def member_authority_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    return canonical_sha256(
        [
            {
                "trajectory_spec_id": row["trajectory_spec_id"],
                "spec_hash": row["spec_hash"],
                "accepted_attempt": row["accepted_attempt"],
            }
            for row in rows
        ]
    )


def subset_id(size: int, replicate: int) -> str:
    return f"n{size:03d}_r{replicate:02d}"


def exposure_by_size(
    schedules: Sequence[Mapping[str, Any]], training: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, int]]:
    result = {}
    training_ids = [row["trajectory_spec_id"] for row in training]
    for size in TRAINING_SIZES:
        counts: Counter[str] = Counter()
        for schedule in schedules:
            if schedule["size"] == size:
                counts.update(row["trajectory_spec_id"] for row in schedule["members"])
        values = [counts[identity] for identity in training_ids]
        result[str(size)] = {
            "minimum": min(values),
            "maximum": max(values),
            "range": max(values) - min(values),
        }
    return result


def grouped_fold_document(
    subset_rows: Sequence[Mapping[str, Any]], row_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    subsets = []
    for subset in subset_rows:
        members = subset["trajectory_spec_ids"]
        folds = []
        for fold_index in range(SELECTION_FOLD_COUNT):
            validation_ids = [
                identity
                for position, identity in enumerate(members)
                if position % SELECTION_FOLD_COUNT == fold_index
            ]
            validation_rows = [row_by_id[identity] for identity in validation_ids]
            folds.append(
                {
                    "fold_id": f"selection_fold_{fold_index}",
                    "validation_trajectory_ids": validation_ids,
                    "validation_count": len(validation_ids),
                    "validation_balance": {
                        "layout": dict(
                            sorted(
                                Counter(
                                    row["layout_id"] for row in validation_rows
                                ).items()
                            )
                        ),
                        "direction": dict(
                            sorted(
                                Counter(
                                    row["direction"] for row in validation_rows
                                ).items()
                            )
                        ),
                        "reporting_stratum": dict(
                            sorted(
                                Counter(
                                    row["reporting_stratum"] for row in validation_rows
                                ).items()
                            )
                        ),
                    },
                    "selection_training_fold_ids": [
                        f"selection_fold_{other}"
                        for other in range(SELECTION_FOLD_COUNT)
                        if other != fold_index
                    ],
                }
            )
        ranking = {}
        for outer_index in range(SELECTION_FOLD_COUNT):
            inner_indices = [
                index for index in range(SELECTION_FOLD_COUNT) if index != outer_index
            ]
            ranking[f"selection_fold_{outer_index}"] = [
                {
                    "ranking_subfold_id": f"ranking_subfold_{rank_index}",
                    "validation_selection_fold_id": f"selection_fold_{inner}",
                    "ranking_training_selection_fold_ids": [
                        f"selection_fold_{other}"
                        for other in inner_indices
                        if other != inner
                    ],
                }
                for rank_index, inner in enumerate(inner_indices)
            ]
        subsets.append(
            {
                "subset_id": subset["subset_id"],
                "training_size": subset["training_size"],
                "selection_folds": folds,
                "best_k_ranking_subfolds_by_outer_selection_fold": ranking,
            }
        )
    return {
        "schema_version": "large-scale-no-wall-p5-grouped-fold-authority-v0.1",
        "status": "FROZEN_PROSPECTIVE_NO_ACTIVATIONS",
        "group_unit": "whole_trajectory_spec_id",
        "frame_level_split_used": False,
        "selection_fold_count": SELECTION_FOLD_COUNT,
        "selection_fold_assignment": (
            "Within each frozen master-prefix subset, prefix position modulo 5; "
            "no additional seed or outcome-dependent optimization."
        ),
        "expected_validation_trajectories_per_fold": {
            str(size): size // SELECTION_FOLD_COUNT for size in TRAINING_SIZES
        },
        "best_k_ranking_subfold_count_per_outer_fold": 4,
        "best_k_ranking_subfold_rule": (
            "For each outer selection fold, the other four whole-trajectory "
            "selection folds are the four ranking subfolds."
        ),
        "best_k_candidates": list(BEST_K_CANDIDATES),
        "alpha_grid": list(ALPHA_GRID),
        "subsets": subsets,
    }


def validate_documents(documents: Mapping[str, Mapping[str, Any]]) -> None:
    split = documents["split_authority.json"]
    schedule = documents["subset_schedule.json"]
    grouped = documents["grouped_fold_authority.json"]
    guard = documents["test_guard.lock"]
    null = documents["canonical_null_authority.json"]
    audit = documents["p5_balance_audit.json"]
    test_ids = {row["trajectory_spec_id"] for row in split["fixed_test"]["members"]}
    train_ids = {row["trajectory_spec_id"] for row in split["training_pool"]["members"]}
    require(len(test_ids) == 18 and len(train_ids) == 102, "split counts differ")
    require(not test_ids & train_ids, "train/test overlap")
    require(len(test_ids | train_ids) == 120, "primary split total differs")
    require(
        Counter(row["layout_id"] for row in split["fixed_test"]["members"])
        == Counter({layout: 3 for layout in LAYOUTS}),
        "fixed test per-layout count differs",
    )
    require(
        Counter(row["layout_id"] for row in split["training_pool"]["members"])
        == Counter({layout: 17 for layout in LAYOUTS}),
        "training per-layout count differs",
    )
    masters = schedule["master_orderings"]
    require(len(masters) == 20, "master count differs")
    require(
        all(
            len(row["trajectory_spec_ids"])
            == len(set(row["trajectory_spec_ids"]))
            == 102
            and set(row["trajectory_spec_ids"]) == train_ids
            for row in masters
        ),
        "master is not a training-pool permutation",
    )
    subsets = schedule["subsets"]
    require(len(subsets) == 62, "subset count differs")
    require(
        Counter(row["training_size"] for row in subsets)
        == Counter(dict(zip(TRAINING_SIZES, SUBSET_REPLICATES, strict=True))),
        "subset replicate counts differ",
    )
    master_by_id = {row["master_id"]: row for row in masters}
    omitted_layouts: Counter[str] = Counter()
    omitted_pairs = []
    for subset in subsets:
        members = subset["trajectory_spec_ids"]
        require(
            members
            == master_by_id[subset["master_id"]]["trajectory_spec_ids"][
                : subset["training_size"]
            ],
            f"subset is not a master prefix: {subset['subset_id']}",
        )
        layouts = {split["member_index"][identity]["layout_id"] for identity in members}
        if subset["training_size"] == 5:
            require(len(layouts) == 5, "N5 does not cover exactly five layouts")
            omitted_layouts.update(set(LAYOUTS) - layouts)
        else:
            require(layouts == set(LAYOUTS), "N>=15 does not cover all layouts")
        if subset["training_size"] == 100:
            omitted = frozenset(train_ids - set(members))
            require(len(omitted) == 2, "N100 does not omit exactly two")
            omitted_pairs.append(omitted)
    require(
        max(omitted_layouts.values()) - min(omitted_layouts.values()) <= 1,
        "N5 omission balance differs",
    )
    require(len(omitted_pairs) == len(set(omitted_pairs)) == 6, "N100 pairs differ")
    require(len(grouped["subsets"]) == 62, "grouped subset authority count differs")
    for subset in grouped["subsets"]:
        source = next(row for row in subsets if row["subset_id"] == subset["subset_id"])
        folds = subset["selection_folds"]
        require(len(folds) == 5, "selection fold count differs")
        validation = [
            identity for fold in folds for identity in fold["validation_trajectory_ids"]
        ]
        require(
            len(validation) == len(set(validation)) == source["training_size"]
            and set(validation) == set(source["trajectory_spec_ids"]),
            "fold validation groups do not partition subset",
        )
        expected = source["training_size"] // 5
        require(
            {fold["validation_count"] for fold in folds} == {expected},
            "fold size differs",
        )
        ranking = subset["best_k_ranking_subfolds_by_outer_selection_fold"]
        require(
            len(ranking) == 5 and {len(value) for value in ranking.values()} == {4},
            "ranking subfold authority differs",
        )
    require(
        guard["test_count"] == len(guard["test_trajectory_ids"]) == 18, "guard count"
    )
    require(set(guard["test_trajectory_ids"]) == test_ids, "guard membership differs")
    require(null["canonical_n"] == 100, "canonical null N differs")
    canonical = next(row for row in subsets if row["subset_id"] == "n100_r00")
    require(
        null["canonical_training_trajectory_ids"] == canonical["trajectory_spec_ids"],
        "canonical null is not master_00 N100",
    )
    require(
        min(null["within_layout_counts"].values()) >= 2, "null derangement impossible"
    )
    require(
        null["target_null_b"] == len(null["prospective_null_seeds"]) == 49,
        "null seeds differ",
    )
    require(audit["v1_primary_intersection"] == 0, "V1 entered primary split")
    require(audit["primary_split_total"] == 120, "primary split is not 120")


def build_documents() -> dict[str, dict[str, Any]]:
    verify_protected_authority()
    entries = load_primary_cohort()
    metadata = split_metadata(entries)
    algorithm = read_json(PACKAGE / "split_algorithm.json")
    seeds = read_json(PACKAGE / "seed_manifest.json")
    require(
        algorithm["fixed_test"]["seed"] == seeds["split_fixed_test_seed"],
        "split seed authorities disagree",
    )
    require(
        algorithm["master_orderings"]["seeds"] == seeds["split_master_seeds"],
        "master seed authorities disagree",
    )
    result = build_split(
        metadata,
        seeds["split_fixed_test_seed"],
        seeds["split_master_seeds"],
    )
    fixed_test = sorted(result["test"], key=lambda row: row["trajectory_spec_id"])
    training = sorted(result["training"], key=lambda row: row["trajectory_spec_id"])
    test_ids = {row["trajectory_spec_id"] for row in fixed_test}
    train_ids = {row["trajectory_spec_id"] for row in training}
    v1_campaign = read_json(PACKAGE / "capture_campaign.json")
    v1_ids = {row["trajectory_spec_id"] for row in v1_campaign["trajectory_specs"]}
    require(not (v1_ids & (test_ids | train_ids)), "V1 entered primary split")
    compact_test = [compact_member(row) for row in fixed_test]
    compact_training = [compact_member(row) for row in training]
    member_index = {row["trajectory_spec_id"]: compact_member(row) for row in metadata}
    split = {
        "schema_version": "large-scale-no-wall-p5-split-authority-v0.1",
        "status": "FROZEN_PROSPECTIVE_BEFORE_ACTIVATIONS",
        "primary_cohort_version": "V2_ACCEPTED_REPAIRED_PRIMARY",
        "primary_cohort_lock": PRIMARY_LOCK_NAME,
        "primary_cohort_lock_sha256": PROTECTED_HASHES[PRIMARY_LOCK_NAME],
        "source_split_algorithm_sha256": PROTECTED_HASHES["split_algorithm.json"],
        "compatibility_mapping": {
            "p1_split_field": "profile_family",
            "v2_source_field": "reporting_stratum",
            "mapping": "identity over the five committed P4B reporting strata",
            "detailed_shape_classes_used_as_selection_criterion": False,
        },
        "fixed_test": {
            "count": 18,
            "per_layout": 3,
            "seed": seeds["split_fixed_test_seed"],
            "authority_hash": member_authority_hash(fixed_test),
            "members": compact_test,
        },
        "training_pool": {
            "count": 102,
            "per_layout": 17,
            "authority_hash": member_authority_hash(training),
            "members": compact_training,
        },
        "member_index": dict(sorted(member_index.items())),
        "train_test_overlap": 0,
        "primary_split_total": 120,
        "v1_primary_intersection": 0,
        "contains_activation_model_probe_or_r2_outcomes": False,
    }
    masters = []
    for index, rows in enumerate(result["masters"]):
        identities = [row["trajectory_spec_id"] for row in rows]
        masters.append(
            {
                "master_id": f"master_{index:02d}",
                "master_seed": seeds["split_master_seeds"][index],
                "selected_rotation": result["master_rotations"][index],
                "trajectory_spec_ids": identities,
                "ordering_hash": canonical_sha256(identities),
            }
        )
    subset_rows = []
    for row in result["schedules"]:
        identities = [member["trajectory_spec_id"] for member in row["members"]]
        subset_rows.append(
            {
                "subset_id": subset_id(row["size"], row["replicate"]),
                "training_size": row["size"],
                "replicate": row["replicate"],
                "master_id": row["master_id"],
                "membership_rule": "nested prefix of referenced master ordering",
                "trajectory_spec_ids": identities,
                "subset_hash": canonical_sha256(identities),
            }
        )
    exposure = exposure_by_size(result["schedules"], training)
    schedule = {
        "schema_version": "large-scale-no-wall-p5-subset-schedule-v0.1",
        "status": "FROZEN_PROSPECTIVE_BEFORE_ACTIVATIONS",
        "training_pool_authority_hash": split["training_pool"]["authority_hash"],
        "training_sizes": list(TRAINING_SIZES),
        "subset_replicates": list(SUBSET_REPLICATES),
        "total_subsets": len(subset_rows),
        "membership_rule": "nested prefixes of frozen master orderings",
        "master_orderings": masters,
        "subsets": subset_rows,
        "training_exposure_by_n": exposure,
    }
    grouped = grouped_fold_document(subset_rows, member_index)
    guard = {
        "schema_version": "large-scale-no-wall-p5-test-guard-v0.1",
        "status": "LOCKED_UNTOUCHED_FIXED_TEST",
        "test_authority_hash": split["fixed_test"]["authority_hash"],
        "test_count": 18,
        "test_trajectory_ids": sorted(test_ids),
        "prohibited_uses": [
            "training",
            "scaler_fitting",
            "feature_preprocessing_fitting",
            "alpha_selection",
            "token_ranking",
            "k_selection",
            "model_selection",
        ],
        "permitted_future_p6_use": (
            "Target-independent activation extraction under one uniform 120-trajectory "
            "authority; no test target or activation may enter training/tuning."
        ),
        "enforcement_unit": "trajectory_spec_id",
    }
    canonical = next(row for row in subset_rows if row["subset_id"] == "n100_r00")
    canonical_rows = [
        member_index[identity] for identity in canonical["trajectory_spec_ids"]
    ]
    within_layout = Counter(row["layout_id"] for row in canonical_rows)
    null = {
        "schema_version": "large-scale-no-wall-p5-canonical-null-authority-v0.1",
        "status": "FROZEN_NOT_EXECUTED",
        "source_prospective_null_authority_sha256": sha256_file(
            PACKAGE / "prospective_null_authority.json"
        ),
        "canonical_n": 100,
        "canonical_subset_id": "n100_r00",
        "canonical_master_id": "master_00",
        "canonical_rule": "master_00 first 100 trajectories",
        "canonical_training_trajectory_ids": canonical["trajectory_spec_ids"],
        "canonical_subset_hash": canonical["subset_hash"],
        "within_layout_counts": dict(sorted(within_layout.items())),
        "within_layout_derangement_feasible": min(within_layout.values()) >= 2,
        "minimum_layout_count_required": 2,
        "target_null_b": 49,
        "prospective_null_seeds": seeds["prospective_null_seeds"],
        "null_executed": False,
    }
    test_direction = Counter(row["direction"] for row in fixed_test)
    test_stratum = Counter(row["reporting_stratum"] for row in fixed_test)
    omitted_layouts: Counter[str] = Counter()
    omitted_pairs = []
    for subset in subset_rows:
        subset_layouts = {
            member_index[identity]["layout_id"]
            for identity in subset["trajectory_spec_ids"]
        }
        if subset["training_size"] == 5:
            omitted_layouts.update(set(LAYOUTS) - subset_layouts)
        if subset["training_size"] == 100:
            omitted_pairs.append(sorted(train_ids - set(subset["trajectory_spec_ids"])))
    audit = {
        "schema_version": "large-scale-no-wall-p5-balance-audit-v0.1",
        "status": "PASS",
        "primary_cohort_count": 120,
        "v1_primary_intersection": len(v1_ids & (test_ids | train_ids)),
        "primary_split_total": len(test_ids | train_ids),
        "fixed_test": {
            "count": len(fixed_test),
            "per_layout": dict(
                sorted(Counter(row["layout_id"] for row in fixed_test).items())
            ),
            "direction": dict(sorted(test_direction.items())),
            "reporting_stratum": dict(sorted(test_stratum.items())),
        },
        "training_pool": {
            "count": len(training),
            "per_layout": dict(
                sorted(Counter(row["layout_id"] for row in training).items())
            ),
        },
        "master_ordering_count": len(masters),
        "total_subsets": len(subset_rows),
        "n5_omitted_layout_counts": dict(sorted(omitted_layouts.items())),
        "n5_omission_balance_valid": (
            max(omitted_layouts.values()) - min(omitted_layouts.values()) <= 1
        ),
        "n_ge_15_all_layouts": all(
            {
                member_index[identity]["layout_id"]
                for identity in subset["trajectory_spec_ids"]
            }
            == set(LAYOUTS)
            for subset in subset_rows
            if subset["training_size"] >= 15
        ),
        "n100_omitted_pairs": omitted_pairs,
        "n100_distinct_omitted_pair_count": len(
            {tuple(pair) for pair in omitted_pairs}
        ),
        "training_exposure_by_n": exposure,
        "grouped_selection_folds_frozen": True,
        "best_k_ranking_subfolds_frozen": True,
        "whole_trajectory_grouping_only": True,
        "frame_level_split_used": False,
        "shape_classes_recorded_descriptively_not_optimized": True,
        "train_test_overlap": len(test_ids & train_ids),
        "canonical_null_derangement_feasible": min(within_layout.values()) >= 2,
        "activation_model_probe_or_r2_inputs_used": False,
    }
    documents: dict[str, dict[str, Any]] = {
        "split_authority.json": split,
        "subset_schedule.json": schedule,
        "grouped_fold_authority.json": grouped,
        "test_guard.lock": guard,
        "canonical_null_authority.json": null,
        "p5_balance_audit.json": audit,
    }
    artifact_sha256 = {
        name: hashlib.sha256(json_bytes(value)).hexdigest()
        for name, value in documents.items()
    }
    receipt = {
        "schema_version": "large-scale-no-wall-p5-receipt-v0.1",
        "status": "PASS_SPLIT_AND_LEARNING_CURVE_AUTHORITY_FROZEN",
        "p4c_head": P4C_HEAD,
        "protected_authority_sha256": dict(sorted(PROTECTED_HASHES.items())),
        "primary_cohort_version": "V2_ACCEPTED_REPAIRED_PRIMARY",
        "primary_cohort_count": 120,
        "fixed_test_count": 18,
        "training_pool_count": 102,
        "master_ordering_count": 20,
        "total_subsets": 62,
        "grouped_selection_folds_frozen": True,
        "best_k_ranking_subfolds_frozen": True,
        "test_guard_created": True,
        "canonical_null_authority_frozen_not_executed": True,
        "fresh_activations_extracted": 0,
        "fresh_r2_computed": False,
        "p6_started": False,
        "safe_for_p6": True,
        "blocker": None,
        "artifact_paths": list(OUTPUT_NAMES),
        "artifact_sha256": dict(sorted(artifact_sha256.items())),
    }
    documents["p5_receipt.json"] = receipt
    validate_documents(documents)
    return documents


def load_primary_split(path: Path | None = None) -> dict[str, Any]:
    """Load only an exact 120-entry V2 split authority."""
    split = read_json(path or PACKAGE / "split_authority.json")
    require(split["primary_cohort_lock"] == PRIMARY_LOCK_NAME, "not V2 primary")
    require(
        split["primary_cohort_lock_sha256"] == PROTECTED_HASHES[PRIMARY_LOCK_NAME],
        "V2 lock hash mismatch",
    )
    require(split["v1_primary_intersection"] == 0, "V1 in primary split")
    require(split["primary_split_total"] == 120, "primary split total differs")
    return split


def enforce_test_guard(
    candidate_training_ids: Sequence[str], guard_path: Path | None = None
) -> None:
    guard = read_json(guard_path or PACKAGE / "test_guard.lock")
    overlap = set(candidate_training_ids) & set(guard["test_trajectory_ids"])
    require(
        not overlap, f"fixed-test IDs used for training/selection: {sorted(overlap)}"
    )


def main() -> int:
    for name in OUTPUT_NAMES:
        require(not (PACKAGE / name).exists(), f"refusing to overwrite {name}")
    documents = build_documents()
    for name in OUTPUT_NAMES:
        write_json_new(PACKAGE / name, documents[name])
    load_primary_split()
    split = documents["split_authority.json"]
    enforce_test_guard(
        [row["trajectory_spec_id"] for row in split["training_pool"]["members"]]
    )
    print(
        "P5_STATUS=PASS_SPLIT_AND_LEARNING_CURVE_AUTHORITY_FROZEN "
        "test=18 training=102 subsets=62"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
