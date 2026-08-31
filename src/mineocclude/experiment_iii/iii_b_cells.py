"""III-B cells, manifests and capture-unit binding (authority 19, 29.8 ``B-GEN``).

A III-B cell is one ``(identity, q)`` pair at condition ``L4``. The single most
important semantic in the module -- authority 19.3 -- is that **each cell derives
its own target window from its own path**, because ``q`` rescales the innovations
and therefore moves the counterfactual occlusion onset. Cells are matched across
``q`` by **occlusion age tau**, never by absolute model-frame index; matching by
frame index is ``B_TAU_ALIGNMENT_ERROR``.

Folds are inherited from III-A and ``q`` never enters fold assignment
(authority 19.5), which is what makes cross-``q`` identity leakage impossible by
construction rather than by convention.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    BINDING_Q_SET,
    DIAGNOSTIC_Q_FALLBACK,
    DT_SECONDS,
    FRAMES_PER_CAPTURE,
    MOTION_NOISE_Q,
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_IDS,
    TARGET_ROWS_PER_CAPTURE,
    canonical_sha256,
)
from mineocclude.experiment_iii.cohort import (
    Candidate,
    generate_noise_schedule,
    generate_path,
    noise_sha256,
    path_sha256,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.iii_b_vis import VisibleWindow, select_vis_window
from mineocclude.experiment_iii.qualification import evaluate_gates_1_to_11
from mineocclude.experiment_iii.schema import ConditionId, validate_identity_id
from mineocclude.experiment_iii.target_manifest import build_target_window

__all__ = [
    "III_B_CONDITION",
    "III_B_EPISODE_ID_BLOCK",
    "III_B_WALL_BLOCK_ID",
    "Q_HIGH",
    "Q_HIGH_FALLBACK",
    "Q_LEVELS",
    "Q_LOW",
    "Q_MID",
    "IIIBCell",
    "assert_no_cross_q_fold_leakage",
    "assert_tau_matched",
    "build_iii_b_cell",
    "build_iii_b_manifest",
    "capture_unit_id",
    "episode_id_for_cell",
    "innovation_pairing_receipt",
    "q_mid_capture_session_disclosure",
]

Q_LOW = 0.0125
Q_MID = MOTION_NOISE_Q
Q_HIGH = 0.2
Q_HIGH_FALLBACK = DIAGNOSTIC_Q_FALLBACK
Q_LEVELS = (Q_LOW, Q_MID, Q_HIGH)

III_B_CONDITION = ConditionId.L4
III_B_WALL_BLOCK_ID = "minecraft:stone"
III_B_EPISODE_ID_BLOCK = (87001, 87999)

_PILOT_EPISODE_BASE = 87901


def capture_unit_id(identity: str, q: float) -> str:
    """``{identity}__L4__q{q:.4f}`` (authority 19.1), and nothing else."""
    return f"{validate_identity_id(identity)}__{III_B_CONDITION.value}__q{float(q):.4f}"


def episode_id_for_cell(identity: str, q: float) -> int:
    """A deterministic episode ID inside the reserved ``87001``-``87999`` block.

    The authority fixes the block and its disjointness from III-A's
    ``86001``-``86999``; the mapping inside the block is deterministic here so
    two runs of ``B-GEN`` produce identical manifests.
    """
    identity = validate_identity_id(identity)
    levels = (Q_LOW, Q_MID, Q_HIGH, Q_HIGH_FALLBACK)
    try:
        offset = next(
            index for index, level in enumerate(levels) if math.isclose(level, float(q))
        )
    except StopIteration:
        raise ExperimentIIIError(
            "B_Q_PAIRING_MISMATCH", f"{q!r} is not a III-B q level"
        ) from None
    if identity in PRODUCTION_IDENTITY_IDS:
        ordinal = PRODUCTION_IDENTITY_IDS.index(identity)
        episode = III_B_EPISODE_ID_BLOCK[0] + ordinal * len(levels) + offset
    elif identity in PILOT_IDENTITY_IDS:
        ordinal = PILOT_IDENTITY_IDS.index(identity)
        episode = _PILOT_EPISODE_BASE + ordinal * len(levels) + offset
    else:  # pragma: no cover - validate_identity_id already refuses these
        raise ExperimentIIIError("B_Q_PAIRING_MISMATCH", f"unknown identity {identity}")
    low, high = III_B_EPISODE_ID_BLOCK
    if not low <= episode <= high:
        raise ExperimentIIIError(
            "B_Q_PAIRING_MISMATCH",
            f"episode {episode} falls outside the reserved III-B block {low}-{high}",
        )
    return episode


@dataclass(frozen=True)
class IIIBCell:
    """One ``(identity, q)`` III-B cell, with its OWN window and VIS rows."""

    identity: str
    direction: str
    q: float
    seed: int
    start_world_x: float
    capture_unit_id: str
    episode_id: int
    outer_fold: int
    inner_rotation: int
    priority_rank: int
    target_model_frame_indices: tuple[int, ...]
    tau_by_model_frame_index: dict[int, int]
    labels: tuple[float, ...]
    path_sha256: str
    noise_schedule_sha256: str
    qualified: bool
    first_failing_gate: int | None
    vis: VisibleWindow

    def as_dict(self) -> dict[str, Any]:
        body = {
            "schema_version": "mineocclude-experiment-iii-b-cell-v1",
            "identity": self.identity,
            "direction": self.direction,
            "condition_id": III_B_CONDITION.value,
            "wall_block_id": III_B_WALL_BLOCK_ID,
            "q": float(self.q),
            "seed": self.seed,
            "noise_seed": self.seed,
            "start_world_x": self.start_world_x,
            "capture_unit_id": self.capture_unit_id,
            "episode_id": self.episode_id,
            "outer_fold": self.outer_fold,
            "inner_rotation": self.inner_rotation,
            "priority_rank": self.priority_rank,
            "target_model_frame_indices": list(self.target_model_frame_indices),
            "tau_by_model_frame_index": {
                str(key): value for key, value in sorted(self.tau_by_model_frame_index.items())
            },
            "expected_causal_fir_target_world_x_blocks": list(self.labels),
            "path_sha256": self.path_sha256,
            "noise_schedule_sha256": self.noise_schedule_sha256,
            "qualified": self.qualified,
            "first_failing_gate": self.first_failing_gate,
            "matching_across_q_is_by": "OCCLUSION_AGE_TAU",
            "matching_by_absolute_frame_index": False,
        }
        body.update(self.vis.as_dict())
        body["spec_hash"] = canonical_sha256(body)
        return body


def build_iii_b_cell(
    identity_row: Mapping[str, Any],
    q: float,
    *,
    frames: int = FRAMES_PER_CAPTURE,
) -> IIIBCell:
    """Materialize one cell from the frozen III-A identity row and a ``q``.

    Gate 9 is peer-dependent and is **not** a per-candidate property, so the
    per-cell re-verification runs the per-candidate gates only, exactly as
    authority 19.4 (amended) requires.
    """
    identity = validate_identity_id(str(identity_row["identity"]))
    direction = str(identity_row["direction"])
    seed = int(identity_row["seed"])
    start_world_x = float(identity_row["start_world_x"])
    positions, noise = generate_path(
        seed, float(q), direction=direction, start_world_x=start_world_x, frames=frames
    )
    window = build_target_window(identity, direction, positions)
    indices = window.target_model_frame_indices
    if len(indices) != TARGET_ROWS_PER_CAPTURE:
        raise ExperimentIIIError(
            "B_TAU_ALIGNMENT_ERROR",
            f"{identity} at q={q} yielded {len(indices)} target rows, not "
            f"{TARGET_ROWS_PER_CAPTURE}",
        )
    cell = evaluate_gates_1_to_11(
        Candidate(
            direction=direction,
            index=int(identity_row.get("candidate_index", 0)),
            seed=seed,
            start_world_x=start_world_x,
        ),
        float(q),
        enforce_gate_9=False,
    )
    return IIIBCell(
        identity=identity,
        direction=direction,
        q=float(q),
        seed=seed,
        start_world_x=start_world_x,
        capture_unit_id=capture_unit_id(identity, q),
        episode_id=episode_id_for_cell(identity, q),
        outer_fold=int(identity_row["outer_fold"]),
        inner_rotation=int(identity_row["inner_rotation"]),
        priority_rank=int(identity_row["priority_rank"]),
        target_model_frame_indices=indices,
        tau_by_model_frame_index={
            index: age for index, age in zip(indices, range(1, len(indices) + 1))
        },
        labels=window.labels,
        path_sha256=path_sha256(positions),
        noise_schedule_sha256=noise_sha256(noise),
        qualified=cell.passed,
        first_failing_gate=cell.first_failing_gate,
        vis=select_vis_window(identity, positions, q=float(q)),
    )


def build_iii_b_manifest(
    identity_rows: Sequence[Mapping[str, Any]],
    *,
    q_levels: Sequence[float] = Q_LEVELS,
) -> dict[str, Any]:
    """``B-GEN``: every ``(identity, q)`` cell, re-verified, never regenerated.

    ``B-GEN`` re-verifies what III-A gate 12 already decided. A qualification
    disagreement here is an implementation defect and never regenerates the
    III-A cohort (authority 19.4).
    """
    cells = [
        build_iii_b_cell(row, float(q)) for row in identity_rows for q in q_levels
    ]
    unqualified = [cell.capture_unit_id for cell in cells if not cell.qualified]
    if unqualified:
        raise ExperimentIIIError(
            "B_Q_PAIRING_MISMATCH",
            "B-GEN re-verification disagrees with III-A qualification gate 12 for "
            f"{unqualified}; this is an implementation defect and never regenerates "
            "the III-A cohort",
        )
    assert_no_cross_q_fold_leakage(cells)
    body = {
        "schema_version": "mineocclude-experiment-iii-b-manifest-v1",
        "condition_id": III_B_CONDITION.value,
        "wall_block_id": III_B_WALL_BLOCK_ID,
        "q_levels": [float(q) for q in q_levels],
        "q_mid_reused_from_iii_a": True,
        "q_mid_recaptured": False,
        "identities": len(identity_rows),
        "cells": [cell.as_dict() for cell in cells],
        "capture_session_disclosure": q_mid_capture_session_disclosure(),
    }
    body["manifest_hash"] = canonical_sha256(body)
    return body


def assert_no_cross_q_fold_leakage(cells: Iterable[IIIBCell]) -> None:
    """Every ``q`` variant of one identity shares its outer fold and rotation."""
    by_identity: dict[str, set[tuple[int, int]]] = {}
    for cell in cells:
        by_identity.setdefault(cell.identity, set()).add(
            (cell.outer_fold, cell.inner_rotation)
        )
    leaking = sorted(
        identity for identity, folds in by_identity.items() if len(folds) > 1
    )
    if leaking:
        raise ExperimentIIIError(
            "B_CROSS_Q_FOLD_LEAKAGE",
            f"{leaking} carry more than one (outer fold, inner rotation) across q; "
            "q is a within-identity factor and never enters fold assignment",
        )


def assert_tau_matched(rows: Sequence[Mapping[str, Any]]) -> None:
    """Refuse a contrast aligned on absolute frame index instead of tau."""
    for row in rows:
        if "tau" not in row:
            raise ExperimentIIIError(
                "B_TAU_ALIGNMENT_ERROR",
                "III-B rows are matched by occlusion age tau; a row without tau "
                "cannot be matched across q",
            )
        tau = row["tau"]
        if isinstance(tau, bool) or not isinstance(tau, int) or not 1 <= tau <= 19:
            raise ExperimentIIIError(
                "B_TAU_ALIGNMENT_ERROR", f"tau must be an int in 1..19, got {tau!r}"
            )


def innovation_pairing_receipt(
    seed: int,
    *,
    frames: int = FRAMES_PER_CAPTURE,
    q_levels: Sequence[float] = BINDING_Q_SET,
    dt: float = DT_SECONDS,
) -> dict[str, Any]:
    """``IB04``: the innovation pairing is generator-native (authority 18.2).

    The standard-normal draw is a function of ``(seed, tick)`` alone; ``q`` only
    rescales it by ``sqrt(q*dt)``. Every ratio between two ``q`` is therefore
    exactly ``sqrt(q_a/q_b)`` at every tick.
    """
    schedules = {
        float(q): generate_noise_schedule(int(seed), frames, float(q), dt)
        for q in q_levels
    }
    draws = {
        q: np.asarray(schedule.standard_normal_draw, dtype=np.float64)
        for q, schedule in schedules.items()
    }
    reference = draws[sorted(draws)[0]]
    paired = all(np.array_equal(reference, value) for value in draws.values())

    scale_exact = True
    for q, schedule in schedules.items():
        expected = np.asarray(schedule.standard_normal_draw, dtype=np.float64) * math.sqrt(
            q * dt
        )
        scale_exact &= bool(
            np.array_equal(np.asarray(schedule.noise_draw, dtype=np.float64), expected)
        )

    ratios: dict[str, dict[str, float]] = {}
    for q_a in sorted(schedules):
        for q_b in sorted(schedules):
            if q_a <= q_b:
                continue
            a = np.asarray(schedules[q_a].noise_draw, dtype=np.float64)
            b = np.asarray(schedules[q_b].noise_draw, dtype=np.float64)
            nonzero = b != 0.0
            observed = a[nonzero] / b[nonzero]
            expected = math.sqrt(q_a / q_b)
            ratios[f"{q_a:.4f}/{q_b:.4f}"] = {
                "expected": expected,
                "max_abs_error": float(np.max(np.abs(observed - expected)))
                if observed.size
                else 0.0,
            }
    return {
        "schema_version": "mineocclude-experiment-iii-b-innovation-pairing-v1",
        "seed": int(seed),
        "frames": int(frames),
        "q_levels": [float(q) for q in q_levels],
        "standard_normal_draw_identical_across_q": paired,
        "noise_equals_draw_times_sqrt_q_dt_exactly": scale_exact,
        "ratios": ratios,
        "blocker": None if paired and scale_exact else "B_Q_PAIRING_MISMATCH",
    }


def q_mid_capture_session_disclosure() -> dict[str, Any]:
    """The mandatory authority-19.2 disclosure, carried with every manifest."""
    return {
        "fact": (
            "The reused q_mid = 0.05 occluded rows come from the III-A production "
            "capture session (A7). The q_low and q_high cells are captured in a "
            "separate, later III-B session (B-CAP)."
        ),
        "consequence": (
            "Any session-level effect is confounded with the q_mid LEVEL, not with "
            "the q_low-versus-q_high contrast."
        ),
        "u2_s1_threatened": False,
        "u3_s2_threatened": False,
        "u2_s3_may_carry_session_effect": True,
        "calibration_analyses_involving_q_mid_may_carry_session_effect": True,
        "required_action": (
            "EXPLICIT_DISCLOSURE_IN_THE_III_B_RESULT_PACKAGE_AND_THE_MANUSCRIPT"
        ),
        "declared_before_any_iii_a_outcome_existed": True,
    }
