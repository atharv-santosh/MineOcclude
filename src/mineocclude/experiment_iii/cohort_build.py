"""I02 — materialize the fresh Experiment III cohort (authority 2.1-2.7).

Order is the point of this module. All twelve gates of authority 2.4 are
evaluated **before** anything is written, and gate 12 (all-``q`` prospective
qualification) is evaluated **before** ``production_identity_manifest.jsonl``
exists and before its hash is taken. The build fails CLOSED with
``COHORT_ALL_Q_PRIMITIVE_MISSING`` if the ``IB02`` primitive or the ``IB03``
regression guard is unavailable; it never materializes an ungated cohort and
never defers the gate.

Candidates are scanned in strictly ascending index to the frozen bound of 2000 per
direction. Relaxing a gate, dropping a ``q``, or changing the salt to obtain a
more convenient candidate stream are all forbidden repairs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    BINDING_Q_SET,
    CANDIDATE_INDEX_BOUND_PER_DIRECTION,
    DIAGNOSTIC_Q_FALLBACK,
    DT_SECONDS,
    FRAMES_PER_CAPTURE,
    LEFT_TO_RIGHT_COUNT,
    MOTION_NOISE_Q,
    PILOT_DIRECTIONS,
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_COUNT,
    PRODUCTION_IDENTITY_IDS,
    RIGHT_TO_LEFT_COUNT,
    RUN_NAMESPACE,
    SPEED_BLOCKS_PER_SECOND,
    authority_sha256,
    canonical_sha256,
    master_salt,
    verify_authority_binding,
)
from mineocclude.experiment_iii.cohort import Candidate, candidate_at
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.folds import build_folds, identity_priority_order
from mineocclude.experiment_iii.historical_seeds import (
    build_historical_seed_exclusion_set,
    excluded_seeds,
)
from mineocclude.experiment_iii.qualification import (
    AllQQualification,
    CellQualification,
    GATE_NAMES,
    evaluate_gates_1_to_11,
    qualifies_at_all_q,
)
from mineocclude.experiment_iii.schema import (
    episode_id_for,
    write_json_atomic,
    write_jsonl_atomic,
)

__all__ = [
    "CohortArtifacts",
    "AdmittedIdentity",
    "assert_all_q_primitive_available",
    "scan_direction",
    "build_cohort",
    "write_cohort",
]

_DIRECTION_QUOTA = {
    "LEFT_TO_RIGHT": LEFT_TO_RIGHT_COUNT,
    "RIGHT_TO_LEFT": RIGHT_TO_LEFT_COUNT,
}


@dataclass(frozen=True)
class AdmittedIdentity:
    """One admitted candidate, before an identity id and rank are assigned."""

    candidate: Candidate
    cell: CellQualification
    all_q: AllQQualification


@dataclass
class CohortArtifacts:
    """Everything I02 produces, in memory, before any file is written."""

    production: list[dict[str, Any]] = field(default_factory=list)
    pilots: list[dict[str, Any]] = field(default_factory=list)
    folds: dict[str, Any] = field(default_factory=dict)
    priority_order: dict[str, Any] = field(default_factory=dict)
    historical_seed_exclusion_set: dict[str, Any] = field(default_factory=dict)
    qualification_receipt: dict[str, Any] = field(default_factory=dict)
    all_q_receipt: dict[str, Any] = field(default_factory=dict)
    q_regression_a1_receipt: dict[str, Any] = field(default_factory=dict)


def assert_all_q_primitive_available() -> dict[str, Any]:
    """Fail CLOSED unless the ``IB02`` primitive and ``IB03`` guard are green.

    ``IB03`` is re-executed here rather than trusted: the whole point of the
    ordering repair is that a q-generalization defect must not reach gate 12
    silently.
    """
    from mineocclude.experiment_iii.authority import (
        D2_NEGATIVE_CONTROL_NOISE_FIRST_PREFIX,
        D2_NEGATIVE_CONTROL_Q_PERTURBATION,
        D2_REFERENCE_DIRECTION,
        D2_REFERENCE_PATH_SHA256,
        D2_REFERENCE_SEED,
        D2_REFERENCE_START_WORLD_X,
    )
    from mineocclude.experiment_iii.cohort import (
        generate_path,
        generate_path_noise_first_forbidden,
        path_sha256,
    )

    try:
        positions, _ = generate_path(
            D2_REFERENCE_SEED,
            0.05,
            direction=D2_REFERENCE_DIRECTION,
            start_world_x=D2_REFERENCE_START_WORLD_X,
        )
        observed = path_sha256(positions)
        perturbed, _ = generate_path(
            D2_REFERENCE_SEED,
            0.05 + D2_NEGATIVE_CONTROL_Q_PERTURBATION,
            direction=D2_REFERENCE_DIRECTION,
            start_world_x=D2_REFERENCE_START_WORLD_X,
        )
        swapped = generate_path_noise_first_forbidden(
            D2_REFERENCE_SEED,
            0.05,
            direction=D2_REFERENCE_DIRECTION,
            start_world_x=D2_REFERENCE_START_WORLD_X,
        )
    except ExperimentIIIError as error:
        raise ExperimentIIIError(
            "COHORT_ALL_Q_PRIMITIVE_MISSING",
            f"the IB02 q-generalized generator is unavailable: {error.message}",
        ) from error

    perturbed_hash = path_sha256(perturbed)
    swapped_hash = path_sha256(swapped)
    checks = {
        "reference_path_sha256_reproduced": observed == D2_REFERENCE_PATH_SHA256,
        "q_perturbation_changes_hash": perturbed_hash != observed,
        "operand_order_swap_changes_hash": swapped_hash != observed,
        "operand_order_swap_matches_frozen_prefix": swapped_hash.startswith(
            D2_NEGATIVE_CONTROL_NOISE_FIRST_PREFIX
        ),
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        raise ExperimentIIIError(
            "COHORT_ALL_Q_PRIMITIVE_MISSING",
            f"the IB03 q=0.05 bit-identity regression is failing: {failed}; "
            "I02 refuses to materialize an ungated cohort",
        )
    return {
        "schema_version": "mineocclude-experiment-iii-q-regression-a1-receipt-v1",
        "authority_section": "2.7, 18.2",
        "test": "D.2",
        "implementing_primitive_task": "IB02",
        "regression_guard_task": "IB03",
        "recorded_before": "I02",
        "reference_unit": "a2x_t01_wall",
        "reference_seed": D2_REFERENCE_SEED,
        "reference_start_world_x": D2_REFERENCE_START_WORLD_X,
        "reference_q": 0.05,
        "expected_path_sha256": D2_REFERENCE_PATH_SHA256,
        "observed_path_sha256": observed,
        "negative_control_q_perturbation_sha256": perturbed_hash,
        "negative_control_noise_first_sha256": swapped_hash,
        "checks": checks,
        "result": "PASS",
    }


def scan_direction(
    direction: str,
    *,
    historical: frozenset[int],
    admitted_seeds: set[int],
    bound: int = CANDIDATE_INDEX_BOUND_PER_DIRECTION,
    progress: Any = None,
) -> tuple[list[AdmittedIdentity], list[dict[str, Any]]]:
    """Scan candidates in strictly ascending index until the quota is filled.

    Gates are evaluated in authority order: gates 1-11 on the production ``q``
    path first, and gate 12 (all-``q``) only once gates 1-11 have passed. A
    candidate rejected at gate 9 never reaches gate 12, which is both the
    authority's ordering and the reason a large candidate ceiling is affordable.

    Returns ``(admitted, rejection_log)``. Every rejected candidate is logged
    with its index, seed and the FIRST gate it failed; for a candidate that
    reached gate 12, the first failing sub-gate at each ``q`` is recorded too.
    """
    needed = _DIRECTION_QUOTA[direction]
    admitted: list[AdmittedIdentity] = []
    rejections: list[dict[str, Any]] = []
    admitted_labels_by_q: dict[float, list[Sequence[float]]] = {
        float(q): [] for q in (*BINDING_Q_SET, DIAGNOSTIC_Q_FALLBACK)
    }

    for index in range(bound):
        if len(admitted) >= needed:
            break
        candidate = candidate_at(direction, index)

        # Gates 1-11, on the production q = 0.05 path.
        production_cell = evaluate_gates_1_to_11(
            candidate,
            MOTION_NOISE_Q,
            admitted_labels_same_direction=admitted_labels_by_q[MOTION_NOISE_Q],
            admitted_seeds=admitted_seeds,
            historical_seeds=historical,
        )
        if not production_cell.passed:
            rejections.append(
                {
                    "candidate_index": index,
                    "direction": direction,
                    "seed": candidate.seed,
                    "first_failing_gate": production_cell.first_failing_gate,
                    "first_failing_gate_name": production_cell.first_failing_gate_name,
                    "reached_gate_12": False,
                }
            )
            if progress is not None:
                progress(index, len(admitted), production_cell.first_failing_gate_name)
            continue

        # Gate 12 - all-q prospective qualification.
        all_q = qualifies_at_all_q(
            candidate,
            BINDING_Q_SET,
            admitted_labels_by_q=admitted_labels_by_q,
            precomputed={MOTION_NOISE_Q: production_cell},
            admitted_seeds=admitted_seeds,
            historical_seeds=historical,
            enforce_gate_9=False,
        )
        if not all_q.passed:
            rejections.append(
                {
                    "candidate_index": index,
                    "direction": direction,
                    "seed": candidate.seed,
                    "first_failing_gate": 12,
                    "first_failing_gate_name": GATE_NAMES[11],
                    "reached_gate_12": True,
                    "first_failing_sub_gate_per_q": all_q.first_failing_sub_gate_per_q(),
                    "diagnostic_q_passed": all_q.diagnostic_passed,
                }
            )
            if progress is not None:
                progress(index, len(admitted), GATE_NAMES[11])
            continue

        admitted.append(AdmittedIdentity(candidate, production_cell, all_q))
        admitted_seeds.add(candidate.seed)
        for q, cell in all_q.per_q.items():
            admitted_labels_by_q[float(q)].append(cell.labels)
        if progress is not None:
            progress(index, len(admitted), None)

    if len(admitted) < needed:
        raise ExperimentIIIError(
            "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE",
            f"{direction} exhausted the frozen candidate index bound of {bound} "
            f"with only {len(admitted)} of {needed} admissions",
        )
    return admitted, rejections


def _manifest_row(
    identity: str,
    admitted: AdmittedIdentity,
    *,
    outer_fold: int | None,
    priority_rank: int | None,
    confirmatory_membership: bool,
) -> dict[str, Any]:
    candidate = admitted.candidate
    cell = admitted.cell
    body: dict[str, Any] = {
        "schema_version": "mineocclude-experiment-iii-identity-spec-v1",
        "run_namespace": RUN_NAMESPACE,
        "identity": identity,
        "direction": candidate.direction,
        "candidate_index": candidate.index,
        "seed": candidate.seed,
        "noise_seed": candidate.noise_seed,
        "episode_id": episode_id_for(identity, priority_rank),
        "start_world_x": candidate.start_world_x,
        "speed_blocks_per_second": SPEED_BLOCKS_PER_SECOND,
        "motion_noise_q": MOTION_NOISE_Q,
        "dt_seconds": DT_SECONDS,
        "frames": FRAMES_PER_CAPTURE,
        "path_sha256": cell.path_sha256,
        "noise_schedule_sha256": cell.noise_schedule_sha256,
        "target_model_frame_indices": list(cell.target_model_frame_indices),
        "expected_causal_fir_target_world_x_blocks": list(cell.labels),
        "expected_target_sd_blocks": cell.target_sd_blocks,
        "tail_clamped_after_target_window": cell.tail_clamped,
        "confirmatory_membership": confirmatory_membership,
        "outer_fold": outer_fold,
        "priority_rank": priority_rank,
        "authority_sha256": authority_sha256(),
    }
    body["spec_hash"] = canonical_sha256(body)
    return body


def build_cohort(
    *,
    bound: int = CANDIDATE_INDEX_BOUND_PER_DIRECTION,
    root: Path | None = None,
) -> CohortArtifacts:
    """Evaluate all twelve gates, then materialize the cohort in memory.

    Nothing is written here. :func:`write_cohort` persists what this returns, so
    the gate-12 evaluation provably precedes materialization and freeze.
    """
    verify_authority_binding()
    q_regression_receipt = assert_all_q_primitive_available()

    exclusion_set = build_historical_seed_exclusion_set(root)
    historical = excluded_seeds(exclusion_set)

    admitted_seeds: set[int] = set()
    admitted: dict[str, list[AdmittedIdentity]] = {}
    rejections: list[dict[str, Any]] = []
    for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
        accepted, rejected = scan_direction(
            direction,
            historical=historical,
            admitted_seeds=admitted_seeds,
            bound=bound,
        )
        admitted[direction] = accepted
        rejections.extend(rejected)

    production_pool = admitted["LEFT_TO_RIGHT"] + admitted["RIGHT_TO_LEFT"]
    if len(production_pool) != PRODUCTION_IDENTITY_COUNT:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"admitted {len(production_pool)} identities, expected "
            f"{PRODUCTION_IDENTITY_COUNT}",
        )

    # Identity ids are assigned in admission order: LTR to quota, then RTL. The
    # priority order is the resulting total order e3_t01 < ... < e3_t25.
    named = [
        (PRODUCTION_IDENTITY_IDS[rank], entry, rank)
        for rank, entry in enumerate(production_pool)
    ]
    fold_input = [
        {
            "identity": identity,
            "direction": entry.candidate.direction,
            "seed": entry.candidate.seed,
        }
        for identity, entry, _rank in named
    ]
    folds = build_folds(fold_input)
    outer = folds["outer_fold_assignment"]

    production_rows = [
        _manifest_row(
            identity,
            entry,
            outer_fold=outer[identity],
            priority_rank=rank,
            confirmatory_membership=True,
        )
        for identity, entry, rank in named
    ]

    # Pilots: generated by the same rules from the same deterministic stream,
    # continuing past the production admissions, and permanently excluded from
    # every production manifest, fold, fit, metric and statistic.
    pilot_rows: list[dict[str, Any]] = []
    for pilot in PILOT_IDENTITY_IDS:
        direction = PILOT_DIRECTIONS[pilot]
        used = {entry.candidate.index for entry in admitted[direction]}
        entry = None
        for index in range(bound):
            if index in used:
                continue
            candidate = candidate_at(direction, index)
            all_q = qualifies_at_all_q(
                candidate,
                BINDING_Q_SET,
                admitted_seeds=admitted_seeds,
                historical_seeds=historical,
            )
            if all_q.passed and all_q.per_q[MOTION_NOISE_Q].passed:
                entry = AdmittedIdentity(candidate, all_q.per_q[MOTION_NOISE_Q], all_q)
                break
        if entry is None:
            raise ExperimentIIIError(
                "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE",
                f"no qualifying pilot candidate for {pilot} within the frozen bound",
            )
        admitted_seeds.add(entry.candidate.seed)
        pilot_rows.append(
            _manifest_row(
                pilot,
                entry,
                outer_fold=None,
                priority_rank=None,
                confirmatory_membership=False,
            )
        )

    qualification_receipt = {
        "schema_version": "mineocclude-experiment-iii-cohort-qualification-receipt-v1",
        "authority_section": "2.4, 2.7",
        "master_salt": master_salt(),
        "authority_sha256": authority_sha256(),
        "rng_identity": "numpy.random.Generator(PCG64) via numpy.random.default_rng",
        "gate_count": len(GATE_NAMES),
        "gate_names": list(GATE_NAMES),
        "candidate_index_bound_per_direction": bound,
        "generation_order": "STRICTLY_ASCENDING_INDEX_PER_DIRECTION_LTR_THEN_RTL",
        "admitted_counts": {
            direction: len(entries) for direction, entries in admitted.items()
        },
        "rejected_count": len(rejections),
        "rejections": rejections,
        "admissions": [
            {
                "identity": identity,
                "direction": entry.candidate.direction,
                "candidate_index": entry.candidate.index,
                "seed": entry.candidate.seed,
                "gates": [outcome.as_dict() for outcome in entry.cell.outcomes],
            }
            for identity, entry, _rank in named
        ],
        "admission_reads_rendered_frames": False,
        "admission_reads_activations": False,
        "admission_reads_outcomes": False,
    }

    all_q_receipt = {
        "schema_version": "mineocclude-experiment-iii-cohort-all-q-receipt-v1",
        "authority_section": "2.4 gate 12",
        "gate_index": 12,
        "gate_name": GATE_NAMES[11],
        "binding_q_set": list(BINDING_Q_SET),
        "diagnostic_q": DIAGNOSTIC_Q_FALLBACK,
        "diagnostic_q_is_binding": False,
        "diagnostic_q_failure_rejects_candidate": False,
        "diagnostic_q_failure_regenerates_cohort": False,
        "candidate_index_bound_per_direction": bound,
        "evaluated_before_materialization": True,
        "evaluated_before_freeze": True,
        "implementing_primitive_task": "IB02",
        "regression_guard_task": "IB03",
        "per_candidate": [
            {
                "candidate_index": entry.candidate.index,
                "direction": entry.candidate.direction,
                "seed": entry.candidate.seed,
                "admitted": True,
                "identity": identity,
                **entry.all_q.as_dict(),
            }
            for identity, entry, _rank in named
        ]
        + [
            {
                "candidate_index": rejection["candidate_index"],
                "direction": rejection["direction"],
                "seed": rejection["seed"],
                "admitted": False,
                "reached_gate_12": rejection["reached_gate_12"],
                # A candidate rejected at gates 1-11 never reaches gate 12, so it
                # has no per-q sub-gate record; its first failing gate is logged
                # in cohort_qualification_receipt.json instead.
                "first_failing_gate": rejection["first_failing_gate"],
                "first_failing_sub_gate_per_q": rejection.get(
                    "first_failing_sub_gate_per_q"
                ),
                "diagnostic_q_passed": rejection.get("diagnostic_q_passed"),
            }
            for rejection in rejections
        ],
        "assertion": (
            "gate 12 was evaluated for every candidate BEFORE the production "
            "identity manifest was written and before its hash was taken"
        ),
    }

    return CohortArtifacts(
        production=production_rows,
        pilots=pilot_rows,
        folds=folds,
        priority_order=identity_priority_order(
            [row["identity"] for row in production_rows]
        ),
        historical_seed_exclusion_set=exclusion_set,
        qualification_receipt=qualification_receipt,
        all_q_receipt=all_q_receipt,
        q_regression_a1_receipt=q_regression_receipt,
    )


def write_cohort(
    artifacts: CohortArtifacts, out_dir: Path, *, namespace_root: Path | None = None
) -> dict[str, str]:
    """Persist the cohort artifacts of authority 2.7 and return their hashes.

    ``namespace_root`` relocates the namespace guard's repository root so a CPU
    integration test can exercise the real writer against a temporary tree
    without touching the materialized cohort. It never widens what the guard
    permits -- the target must still sit inside an Experiment III root beneath
    that root.
    """
    out_dir = Path(out_dir)
    root = namespace_root
    # The A1 q-regression receipt is recorded BEFORE the manifest, matching the
    # order the authority requires of the evidence, not merely of the evaluation.
    digests = {
        "q_regression_a1_receipt.json": write_json_atomic(
            out_dir / "q_regression_a1_receipt.json",
            artifacts.q_regression_a1_receipt,
            root=root,
        ),
        "cohort_all_q_qualification_receipt.json": write_json_atomic(
            out_dir / "cohort_all_q_qualification_receipt.json",
            artifacts.all_q_receipt,
            root=root,
        ),
    }
    manifest_hash, rows = write_jsonl_atomic(
        out_dir / "production_identity_manifest.jsonl",
        artifacts.production,
        root=root,
    )
    if rows != PRODUCTION_IDENTITY_COUNT:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"production manifest holds {rows} rows, expected "
            f"{PRODUCTION_IDENTITY_COUNT}",
        )
    digests["production_identity_manifest.jsonl"] = manifest_hash
    write_json_atomic(
        out_dir / "production_identity_manifest.sha256",
        {"production_identity_manifest.jsonl": manifest_hash},
        root=root,
    )
    pilot_hash, pilot_rows = write_jsonl_atomic(
        out_dir / "pilot_identity_manifest.jsonl", artifacts.pilots, root=root
    )
    digests["pilot_identity_manifest.jsonl"] = pilot_hash
    if pilot_rows != len(PILOT_IDENTITY_IDS):
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", "pilot manifest must hold exactly two rows"
        )
    digests["folds.json"] = write_json_atomic(
        out_dir / "folds.json", artifacts.folds, root=root
    )
    digests["identity_priority_order.json"] = write_json_atomic(
        out_dir / "identity_priority_order.json", artifacts.priority_order, root=root
    )
    digests["historical_seed_exclusion_set.json"] = write_json_atomic(
        out_dir / "historical_seed_exclusion_set.json",
        artifacts.historical_seed_exclusion_set,
        root=root,
    )
    digests["cohort_qualification_receipt.json"] = write_json_atomic(
        out_dir / "cohort_qualification_receipt.json",
        artifacts.qualification_receipt,
        root=root,
    )
    return digests
