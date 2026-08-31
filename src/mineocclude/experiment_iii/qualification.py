"""The twelve Experiment III qualification gates (authority 2.4).

Gates are evaluated in authority order and the **first** failing gate is
reported, because rejection logging is required evidence rather than a
convenience. Admission reads only state, geometry and timing: no rendered frame,
no activation, no decoder error, no magenta detection, no RVE score, no
MineWorld output, and no pilot or historical outcome.

Gate 12 (``ALL_Q_PROSPECTIVE_QUALIFICATION``) is the ``IB02`` primitive: a
candidate must satisfy gates 1-11 at **every** frozen ``q``, each evaluated on
that ``(identity, q)`` cell's own regenerated path. It is a III-A admission
constraint, not a III-B stage, and it is evaluated BEFORE the cohort is
materialized or frozen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    BETWEEN_IDENTITY_DIVERSITY_RMS_BLOCKS,
    BINDING_Q_SET,
    CAPTURE_HZ,
    DIAGNOSTIC_Q_FALLBACK,
    DT_SECONDS,
    FRAMES_PER_CAPTURE,
    LANE_MAX,
    LANE_MIN,
    MINIMUM_TARGET_SD_BLOCKS,
    MOTION_NOISE_Q,
    SPEED_BLOCKS_PER_SECOND,
    TARGET_ROWS_PER_CAPTURE,
)
from mineocclude.experiment_iii.cohort import (
    Candidate,
    generate_path,
    noise_sha256,
    path_sha256,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.fir import FIRST_FULLY_RESOLVED_TICK, fir_labels
from mineocclude.experiment_iii.target_manifest import (
    eligibility_mask,
    first_fully_occluded_run,
)
from mineocclude.experiment_iii.schema import ExtentClassName

__all__ = [
    "GATE_NAMES",
    "GateOutcome",
    "CellQualification",
    "AllQQualification",
    "qualifies",
    "qualifies_at_all_q",
    "evaluate_gates_1_to_11",
]

#: Authority 2.4, in evaluation order. The index is the gate number.
GATE_NAMES = (
    "FRAME_COVERAGE",
    "MOTION_IDENTITY",
    "NO_LANE_CLAMP_OVER_PROTECTED_PREFIX",
    "REPRODUCIBLE_SCHEDULES",
    "COMPLETE_CAUSAL_FIR_HISTORY",
    "COUNTERFACTUAL_OCCLUSION_RUN",
    "NONZERO_TARGET_VARIATION",
    "MINIMUM_TARGET_SD",
    "DIRECTION_DIVERSITY",
    "SEED_UNIQUENESS",
    "HISTORICAL_SEED_EXCLUSION",
    "ALL_Q_PROSPECTIVE_QUALIFICATION",
)

_GATE_NUMBER = {name: index + 1 for index, name in enumerate(GATE_NAMES)}


@dataclass(frozen=True)
class GateOutcome:
    """One gate's verdict, with the evidence that produced it."""

    number: int
    name: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate": self.number,
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CellQualification:
    """Gates 1-11 evaluated on one ``(candidate, q)`` cell's own path."""

    q: float
    passed: bool
    first_failing_gate: int | None
    first_failing_gate_name: str | None
    outcomes: tuple[GateOutcome, ...]
    path_sha256: str | None = None
    noise_schedule_sha256: str | None = None
    target_model_frame_indices: tuple[int, ...] = ()
    labels: tuple[float, ...] = ()
    target_sd_blocks: float | None = None
    tail_clamped: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "q": self.q,
            "passed": self.passed,
            "first_failing_gate": self.first_failing_gate,
            "first_failing_gate_name": self.first_failing_gate_name,
            "gates": [outcome.as_dict() for outcome in self.outcomes],
            "path_sha256": self.path_sha256,
            "noise_schedule_sha256": self.noise_schedule_sha256,
            "target_model_frame_indices": list(self.target_model_frame_indices),
            "target_sd_blocks": self.target_sd_blocks,
            "tail_clamped": self.tail_clamped,
        }


@dataclass(frozen=True)
class AllQQualification:
    """Gate 12: gates 1-11 at every binding ``q``, plus the non-binding diagnostic."""

    passed: bool
    per_q: dict[float, CellQualification] = field(default_factory=dict)
    diagnostic_q: float = DIAGNOSTIC_Q_FALLBACK
    diagnostic_passed: bool | None = None
    diagnostic_first_failing_gate: int | None = None

    def first_failing_sub_gate_per_q(self) -> dict[str, int | None]:
        return {
            f"{q:.4f}": cell.first_failing_gate for q, cell in sorted(self.per_q.items())
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "binding_q_set": list(BINDING_Q_SET),
            "per_q": {f"{q:.4f}": cell.as_dict() for q, cell in sorted(self.per_q.items())},
            "first_failing_sub_gate_per_q": self.first_failing_sub_gate_per_q(),
            "diagnostic_q": self.diagnostic_q,
            "diagnostic_q_passed": self.diagnostic_passed,
            "diagnostic_q_first_failing_gate": self.diagnostic_first_failing_gate,
            "diagnostic_q_is_binding": False,
            "diagnostic_q_failure_rejects_candidate": False,
            "diagnostic_q_failure_regenerates_cohort": False,
        }


def _scientific_outcome_guard(value: object, label: str) -> None:
    """Gate 12 reads seeds, geometry and timing only (test D.31 item 3)."""
    if value is not None:
        raise ExperimentIIIError(
            "B_III_A_DEPENDENCY_DETECTED",
            f"qualification refuses {label}: admission reads no rendered frame, "
            "activation, prediction, RVE score or MineWorld output",
        )


def evaluate_gates_1_to_11(
    candidate: Candidate,
    q: float,
    *,
    admitted_labels_same_direction: Sequence[Sequence[float]] = (),
    admitted_seeds: Iterable[int] = (),
    historical_seeds: Iterable[int] = (),
    frames: int = FRAMES_PER_CAPTURE,
    rendered_frame: object = None,
    activation: object = None,
    prediction: object = None,
    rve_score: object = None,
    mineworld_output: object = None,
    enforce_gate_9: bool = True,
) -> CellQualification:
    """Gates 1-11 on this cell's OWN regenerated path.

    ``enforce_gate_9`` carries the amended gate-12 scope. Gate 9 is a
    *between-identity* constraint whose verdict depends on which peers have
    already been admitted, so it is not a per-candidate property and is
    evaluated once, on the production cohort at the III-A ``q``. At the other
    binding ``q`` the peer-independent gates alone are evaluated. See the
    successor authority amendment record; this reproduces the feasibility study
    of authority section 18.4, whose 100.0% rate at ``q = 0.0125`` is only
    definable with gate 9 excluded.

    The five outcome arguments exist only so a caller that tries to feed a
    scientific outcome into admission is refused loudly rather than silently
    accepted.
    """
    for value, label in (
        (rendered_frame, "a rendered frame"),
        (activation, "an activation"),
        (prediction, "a prediction"),
        (rve_score, "an RVE score"),
        (mineworld_output, "a MineWorld output"),
    ):
        _scientific_outcome_guard(value, label)

    outcomes: list[GateOutcome] = []

    def record(name: str, passed: bool, detail: str = "") -> bool:
        outcomes.append(GateOutcome(_GATE_NUMBER[name], name, passed, detail))
        return passed

    def failed() -> CellQualification | None:
        for outcome in outcomes:
            if not outcome.passed:
                return CellQualification(
                    q=float(q),
                    passed=False,
                    first_failing_gate=outcome.number,
                    first_failing_gate_name=outcome.name,
                    outcomes=tuple(outcomes),
                )
        return None

    positions, noise = generate_path(
        candidate.seed,
        q,
        direction=candidate.direction,
        start_world_x=candidate.start_world_x,
        frames=frames,
    )

    # Gate 1 - frame coverage.
    record(
        "FRAME_COVERAGE",
        len(positions) == FRAMES_PER_CAPTURE and CAPTURE_HZ == 20,
        f"frames={len(positions)} at {CAPTURE_HZ} Hz",
    )
    # Gate 2 - motion identity. The cell's own q is the one under evaluation.
    record(
        "MOTION_IDENTITY",
        SPEED_BLOCKS_PER_SECOND == 2.0
        and DT_SECONDS == 0.05
        and math.isfinite(q)
        and q > 0.0,
        f"speed={SPEED_BLOCKS_PER_SECOND} q={q} dt={DT_SECONDS}",
    )
    if (early := failed()) is not None:
        return early

    # Gates 3 and 5 are scoped to the target window, so the window is computed
    # first and the outcomes are still REPORTED in authority order.
    mask, classes = eligibility_mask([float(value) for value in positions])
    eligible = [
        ExtentClassName.EXTENT_FULLY_OCCLUDED
        if keep
        else ExtentClassName.EXTENT_FULLY_VISIBLE
        for keep in mask
    ]
    window = first_fully_occluded_run(eligible, TARGET_ROWS_PER_CAPTURE)

    if window is None:
        # Gate 3's protected prefix and gate 5's target rows are undefined
        # without a window, so gate 6 is the first evaluable failure.
        record("NO_LANE_CLAMP_OVER_PROTECTED_PREFIX", True, "deferred: no window")
        record(
            "REPRODUCIBLE_SCHEDULES",
            True,
            "deferred: evaluated after the window exists",
        )
        record("COMPLETE_CAUSAL_FIR_HISTORY", True, "deferred: no window")
        longest = max(
            (
                stop - start
                for start, stop in _runs(eligible)
            ),
            default=0,
        )
        record(
            "COUNTERFACTUAL_OCCLUSION_RUN",
            False,
            f"longest eligible run is {longest}, need {TARGET_ROWS_PER_CAPTURE}",
        )
        return failed()

    start, stop = window
    indices = tuple(range(start, stop))
    last_target_row = indices[-1]

    # Gate 3 - no lane clamp strictly inside [0, last_target_row]. Tail clamping
    # after the window is expected and is a diagnostic, not a rejection.
    prefix = positions[: last_target_row + 1]
    clamped_prefix = bool(
        np.any(prefix <= LANE_MIN) or np.any(prefix >= LANE_MAX)
    )
    tail_clamped = bool(
        np.any(positions[last_target_row + 1 :] <= LANE_MIN)
        or np.any(positions[last_target_row + 1 :] >= LANE_MAX)
    )
    record(
        "NO_LANE_CLAMP_OVER_PROTECTED_PREFIX",
        not clamped_prefix,
        f"protected prefix [0,{last_target_row}] clamped={clamped_prefix}; "
        f"tail clamped={tail_clamped} (diagnostic)",
    )

    # Gate 4 - recomputing from the frozen seed reproduces both hashes.
    replay_positions, replay_noise = generate_path(
        candidate.seed,
        q,
        direction=candidate.direction,
        start_world_x=candidate.start_world_x,
        frames=frames,
    )
    observed_path = path_sha256(positions)
    observed_noise = noise_sha256(noise)
    record(
        "REPRODUCIBLE_SCHEDULES",
        path_sha256(replay_positions) == observed_path
        and noise_sha256(replay_noise) == observed_noise,
        "path and noise hashes reproduce from the seed",
    )

    # Gate 5 - complete causal FIR history for every target row.
    record(
        "COMPLETE_CAUSAL_FIR_HISTORY",
        indices[0] >= FIRST_FULLY_RESOLVED_TICK,
        f"first target row {indices[0]} >= {FIRST_FULLY_RESOLVED_TICK}",
    )

    # Gate 6 - the window exists, by construction of ``window``.
    record(
        "COUNTERFACTUAL_OCCLUSION_RUN",
        True,
        f"window [{start},{stop}) of {TARGET_ROWS_PER_CAPTURE} rows",
    )
    if (early := failed()) is not None:
        return early

    labels = tuple(
        fir_labels([float(value) for value in positions], indices, candidate.direction)
    )
    label_array = np.asarray(labels, dtype=np.float64)
    target_sd = float(np.std(label_array, ddof=0))

    # Gate 7 - nonzero target variation.
    record(
        "NONZERO_TARGET_VARIATION",
        len(set(labels)) > 1,
        f"distinct labels={len(set(labels))}",
    )
    # Gate 8 - within-identity spread.
    record(
        "MINIMUM_TARGET_SD",
        target_sd >= MINIMUM_TARGET_SD_BLOCKS,
        f"std(labels, ddof=0)={target_sd:.6f} >= {MINIMUM_TARGET_SD_BLOCKS}",
    )
    # Gate 9 - between-identity diversity against already-admitted same-direction
    # identities. Distinct from gate 8, which is a within-identity spread gate.
    diversity_ok = True
    worst = None
    for existing in admitted_labels_same_direction:
        rms = float(
            math.sqrt(
                float(np.mean((label_array - np.asarray(existing, dtype=np.float64)) ** 2))
            )
        )
        worst = rms if worst is None else min(worst, rms)
        if rms < BETWEEN_IDENTITY_DIVERSITY_RMS_BLOCKS:
            diversity_ok = False
    if enforce_gate_9:
        record(
            "DIRECTION_DIVERSITY",
            diversity_ok,
            f"min RMS vs admitted same-direction identities={worst}",
        )
    else:
        record(
            "DIRECTION_DIVERSITY",
            True,
            "not applicable at this q: gate 9 is peer-dependent and is "
            "evaluated once on the production cohort at the III-A q",
        )
    # Gate 10 - seed unique within Experiment III.
    admitted = set(admitted_seeds)
    record(
        "SEED_UNIQUENESS",
        candidate.seed not in admitted,
        f"seed {candidate.seed} unique within Experiment III",
    )
    # Gate 11 - historical seed exclusion.
    historical = set(historical_seeds)
    record(
        "HISTORICAL_SEED_EXCLUSION",
        candidate.seed not in historical,
        f"seed {candidate.seed} absent from the historical exclusion set",
    )

    if (failure := failed()) is not None:
        return failure
    return CellQualification(
        q=float(q),
        passed=True,
        first_failing_gate=None,
        first_failing_gate_name=None,
        outcomes=tuple(outcomes),
        path_sha256=observed_path,
        noise_schedule_sha256=observed_noise,
        target_model_frame_indices=indices,
        labels=labels,
        target_sd_blocks=target_sd,
        tail_clamped=tail_clamped,
    )


def _runs(classes: Sequence[ExtentClassName]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(classes):
        if value is ExtentClassName.EXTENT_FULLY_OCCLUDED:
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(classes)))
    return runs


def qualifies(candidate: Candidate, q: float = MOTION_NOISE_Q, **kwargs: Any) -> CellQualification:
    """Gates 1-11 for one ``(candidate, q)`` cell. The ``IB02`` primitive."""
    return evaluate_gates_1_to_11(candidate, q, **kwargs)


def qualifies_at_all_q(
    candidate: Candidate,
    q_set: Sequence[float] = BINDING_Q_SET,
    *,
    include_diagnostic: bool = True,
    admitted_labels_by_q: Mapping[float, Sequence[Sequence[float]]] | None = None,
    precomputed: Mapping[float, CellQualification] | None = None,
    enforce_gate_9: bool = False,
    **kwargs: Any,
) -> AllQQualification:
    """Gate 12. Each cell regenerates its OWN path from the identity seed.

    **Scope, as amended by Authority Amendment 2 (v1.5):** gate 12 evaluates the
    **per-candidate** gates -- 1-8, 10 and 11 -- at every binding ``q``. Gate 9
    is a peer-dependent *between-identity* constraint with no per-candidate rate,
    so it is **excluded here** and evaluated once on the production cohort at the
    III-A ``q = 0.05``. That is why ``enforce_gate_9`` defaults to ``False``:
    this function *is* the gate-12 primitive, and defaulting it to the superseded
    v1.4 within-``q`` interpretation would let a caller reach the wrong semantics
    without asking for them. The authority 18.4 per-``q`` rates -- 100.0% at
    ``q = 0.0125`` in both directions -- are only definable with gate 9 outside
    this scope.

    The ``q = 0.15`` fallback is recorded as a diagnostic column and is **not**
    binding: a failure there never rejects a candidate and never regenerates the
    cohort.
    """
    per_q: dict[float, CellQualification] = {}
    passed = True

    def labels_for(q: float) -> Sequence[Sequence[float]]:
        if admitted_labels_by_q is None:
            return kwargs.get("admitted_labels_same_direction", ())
        return admitted_labels_by_q.get(float(q), ())

    cell_kwargs = {
        key: value
        for key, value in kwargs.items()
        if key != "admitted_labels_same_direction"
    }
    cell_kwargs["enforce_gate_9"] = enforce_gate_9
    for q in q_set:
        # A cell already evaluated in gate order (the production q is evaluated
        # as gates 1-11 before gate 12 is reached) is reused rather than
        # recomputed; the arithmetic is deterministic, so this is identity.
        cell = (precomputed or {}).get(float(q))
        if cell is None:
            cell = evaluate_gates_1_to_11(
                candidate,
                float(q),
                admitted_labels_same_direction=labels_for(float(q)),
                **cell_kwargs,
            )
        per_q[float(q)] = cell
        passed = passed and cell.passed

    diagnostic_passed: bool | None = None
    diagnostic_gate: int | None = None
    if include_diagnostic:
        diagnostic = evaluate_gates_1_to_11(
            candidate,
            float(DIAGNOSTIC_Q_FALLBACK),
            admitted_labels_same_direction=labels_for(
                float(DIAGNOSTIC_Q_FALLBACK)
            ),
            **cell_kwargs,
        )
        diagnostic_passed = diagnostic.passed
        diagnostic_gate = diagnostic.first_failing_gate

    return AllQQualification(
        passed=passed,
        per_q=per_q,
        diagnostic_passed=diagnostic_passed,
        diagnostic_first_failing_gate=diagnostic_gate,
    )
