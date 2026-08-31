"""Direction-specific causal FIR kernels and label construction (authority 5.2, 5.3).

The kernel diagnostics and ``causal_fir_targets`` are ported line-for-line from
the A-prime v0.3 sources bound in authority 5.1; only the error type differs, so
every raise carries an Experiment III blocker code.

The literal taps are **recovered**, not invented: :func:`recover_fir_kernels`
reproduces the least-squares recovery of authority 5.3 from the bound ``v0_4``
manifest and refuses unless all five acceptance gates hold.

Normalization is frozen once, here, for every consumer. :func:`frozen_kernel`
returns taps already divided by ``math.fsum(taps)``. The published taps are
rounded to 10 decimals, so ``fsum(LEFT_TO_RIGHT) = 0.9999999999`` — enough to
pass the ``1e-9`` label tolerance but to FAIL the ``1e-12`` oracle tolerance.
Using unnormalized taps anywhere is ``FIR_KERNEL_NOT_NORMALIZED``.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.aprime_reference import (
    AprimeUnit,
    aprime_generate_path,
    aprime_materialized_units,
    path_sha256,
)
from mineocclude.experiment_iii.authority import (
    FIR_RECOVERY_COMMIT,
    FIR_RECOVERY_PATH,
    FIR_RECOVERY_SHA256,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "KERNEL_LENGTH",
    "KERNEL_LAGS",
    "FIRST_FULLY_RESOLVED_TICK",
    "RECOVERED_TAPS",
    "PURE_DELAY_OFF_PEAK_MASS_TOLERANCE",
    "ACCEPTANCE_GATES",
    "normalized_kernel",
    "kernel_off_peak_mass",
    "kernel_group_delay_ticks",
    "kernel_mode_lag",
    "kernel_positive_mass_support",
    "kernel_is_effectively_pure_delay",
    "causal_fir_targets",
    "frozen_kernel",
    "frozen_kernels",
    "fir_labels",
    "recover_fir_kernels",
    "fir_recovery_receipt",
]


KERNEL_LENGTH = 9
KERNEL_LAGS = tuple(range(KERNEL_LENGTH))
#: A row at index ``t`` needs ``t - len(taps) + 1 >= 0``, so ``t >= 8``.
FIRST_FULLY_RESOLVED_TICK = KERNEL_LENGTH - 1

#: Authority 5.3, recovered and verified at authority construction. RAW taps:
#: every consumer must go through :func:`frozen_kernel`, which normalizes.
RECOVERED_TAPS: dict[str, tuple[float, ...]] = {
    "LEFT_TO_RIGHT": (
        0.0552210582,
        0.0955547802,
        0.1729033607,
        0.2562377030,
        0.1725945773,
        0.1502955787,
        0.0283805770,
        0.0327627758,
        0.0360495890,
    ),
    "RIGHT_TO_LEFT": (
        0.0155128136,
        0.1420986717,
        0.3819949723,
        0.2529919934,
        0.1314006058,
        0.0092585384,
        0.0336603539,
        0.0330820509,
        # The recovered value is the exact float -0.0; treated as +0.0, which
        # does not violate the nonnegativity acceptance gate.
        0.0,
    ),
}

#: Authority 5.3 step 4.
ACCEPTANCE_GATES = {
    "design_rank": 9,
    "min_tap": -1e-9,
    "tap_sum_tolerance": 1e-9,
    "max_abs_residual_blocks": 1e-12,
    "aggregate_mode_lag": 2,
    "positive_support_within": (0, 8),
    "path_hashes_reproduced": 50,
    "labels_reproduced": 950,
}

EXPECTED_DIAGNOSTICS = {
    "LEFT_TO_RIGHT": {"mode_lag": 3, "positive_support": (0, 8)},
    "RIGHT_TO_LEFT": {"mode_lag": 2, "positive_support": (0, 7)},
}


# --------------------------------------------------------------------------
# Ported A-prime kernel primitives (authority 5.1, temporal_alignment.py)
# --------------------------------------------------------------------------

#: Numerical tolerance only. A normalized causal FIR kernel carrying all but this
#: fraction of its mass on a single tap is not numerically separable from a bare
#: integer-tick delay in binary64, so counting positive taps is not a usable
#: pure-delay test. This is a float64 round-off allowance, NOT a scientific
#: threshold.
PURE_DELAY_OFF_PEAK_MASS_TOLERANCE = 1e-9


def _finite(value: object, name: str) -> float:
    from numbers import Real

    if isinstance(value, bool) or not isinstance(value, Real):
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED", f"{name} must be a real number"
        )
    result = float(value)
    if not math.isfinite(result):
        raise ExperimentIIIError("FIR_KERNEL_RECOVERY_FAILED", f"{name} must be finite")
    return result


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentIIIError(
            "FIR_INCOMPLETE_HISTORY", f"{name} must be a plain number"
        )
    result = float(value)
    if not math.isfinite(result):
        raise ExperimentIIIError("FIR_INCOMPLETE_HISTORY", f"{name} must be finite")
    return result


def _integer(value: Any, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExperimentIIIError(
            "FIR_INCOMPLETE_HISTORY", f"{name} must be a plain integer"
        )
    if minimum is not None and value < minimum:
        raise ExperimentIIIError(
            "FIR_INCOMPLETE_HISTORY", f"{name} must be >= {minimum}"
        )
    return value


def normalized_kernel(taps: Sequence[float]) -> list[float]:
    """Return a nonnegative causal kernel rescaled to unit mass with ``fsum``."""
    values = [_finite(tap, "FIR coefficient") for tap in taps]
    if len(values) < 2:
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED",
            "a causal FIR kernel requires at least two taps",
        )
    if any(value < 0 for value in values):
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED", "a causal FIR kernel must be nonnegative"
        )
    total = math.fsum(values)
    if not total > 0 or not math.isfinite(total):
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED", "a causal FIR kernel must carry positive mass"
        )
    return [value / total for value in values]


def kernel_off_peak_mass(taps: Sequence[float]) -> float:
    """Normalized mass lying off the single largest tap."""
    kernel = normalized_kernel(taps)
    return 1.0 - max(kernel)


def kernel_group_delay_ticks(taps: Sequence[float]) -> float:
    """First moment of the normalized kernel, in ticks."""
    kernel = normalized_kernel(taps)
    return math.fsum(lag * tap for lag, tap in enumerate(kernel))


def kernel_mode_lag(taps: Sequence[float]) -> int:
    """Lag index carrying the largest mass; lowest index wins a tie."""
    kernel = normalized_kernel(taps)
    return max(range(len(kernel)), key=lambda lag: (kernel[lag], -lag))


def kernel_positive_mass_support(taps: Sequence[float]) -> tuple[int, int]:
    """Lowest and highest lag index carrying non-zero mass."""
    kernel = normalized_kernel(taps)
    carried = [lag for lag, tap in enumerate(kernel) if tap > 0.0]
    if not carried:
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED", "a causal FIR kernel must carry positive mass"
        )
    return carried[0], carried[-1]


def kernel_is_effectively_pure_delay(
    taps: Sequence[float],
    *,
    tolerance: float = PURE_DELAY_OFF_PEAK_MASS_TOLERANCE,
) -> bool:
    """Whether the kernel is numerically indistinguishable from a bare delay."""
    allowance = _finite(tolerance, "pure-delay off-peak mass tolerance")
    if allowance < 0:
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED",
            "pure-delay off-peak mass tolerance must be non-negative",
        )
    return kernel_off_peak_mass(taps) <= allowance


def causal_fir_targets(
    server_positions: Sequence[float],
    model_frame_indices: Sequence[int],
    kernel: Sequence[float],
    *,
    pure_delay_tolerance: float = PURE_DELAY_OFF_PEAK_MASS_TOLERANCE,
) -> list[float]:
    """Construct labels from the qualified causal state-to-render FIR mapping.

    Ported from A-prime ``development_workflow.causal_fir_targets``. Uses the
    single authority-bound pure-delay definition; counting positive taps admits
    kernels such as ``[1e-300, 0, 0, 1, 0, ...]`` that are a bare 3-tick delay in
    binary64.
    """
    positions = [_number(value, "server position") for value in server_positions]
    for value in kernel if isinstance(kernel, (list, tuple)) else ():
        _number(value, "FIR coefficient")
    taps = normalized_kernel(kernel)
    if kernel_is_effectively_pure_delay(taps, tolerance=pure_delay_tolerance):
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED",
            "pure-delay kernel is forbidden: off-peak mass "
            f"{kernel_off_peak_mass(taps):.3e} is within the numerical tolerance "
            f"{pure_delay_tolerance:.3e} of a bare integer-tick delay",
        )
    targets: list[float] = []
    for raw_index in model_frame_indices:
        index = _integer(raw_index, "model frame index", minimum=0)
        if index >= len(positions) or index - len(taps) + 1 < 0:
            raise ExperimentIIIError(
                "FIR_INCOMPLETE_HISTORY",
                "model frame lacks complete causal FIR state history",
            )
        targets.append(sum(tap * positions[index - lag] for lag, tap in enumerate(taps)))
    return targets


# --------------------------------------------------------------------------
# The frozen, normalized kernels (authority 5.3)
# --------------------------------------------------------------------------

@lru_cache(maxsize=None)
def frozen_kernel(direction: str) -> tuple[float, ...]:
    """The frozen direction kernel, fsum-normalized once at load.

    Every downstream consumer — labels, ``H(m)``, ``S(tau)``, ``gbar``,
    ``c_direction`` and every oracle quantity — must read the kernel through
    here, never through :data:`RECOVERED_TAPS`.
    """
    if direction not in RECOVERED_TAPS:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", f"unknown direction {direction!r}"
        )
    return tuple(normalized_kernel(RECOVERED_TAPS[direction]))


def frozen_kernels() -> dict[str, tuple[float, ...]]:
    return {direction: frozen_kernel(direction) for direction in RECOVERED_TAPS}


def assert_normalized(taps: Sequence[float]) -> None:
    """Refuse taps that were not fsum-normalized at load."""
    total = math.fsum(taps)
    if abs(total - 1.0) > 0.0:
        raise ExperimentIIIError(
            "FIR_KERNEL_NOT_NORMALIZED",
            f"kernel mass is {total!r}; taps must be divided by math.fsum(taps) "
            "once at load before any consumer reads them",
        )


def fir_labels(positions: Sequence[float], indices: Sequence[int], direction: str):
    """The 19 frozen labels for one identity, from the normalized kernel."""
    taps = frozen_kernel(direction)
    assert_normalized(taps)
    return causal_fir_targets(positions, indices, list(taps))


# --------------------------------------------------------------------------
# Recovery (authority 5.3) — reproduced at A1, never refitted
# --------------------------------------------------------------------------

def _design_for(units: Sequence[AprimeUnit], direction: str):
    rows: list[list[float]] = []
    labels: list[float] = []
    for unit in units:
        if unit.direction != direction:
            continue
        positions, _ = aprime_generate_path(
            noise_seed=unit.noise_seed,
            start_world_x=unit.start_world_x,
            direction=unit.direction,
            q=unit.motion_noise_q,
            speed=unit.speed_blocks_per_second,
            frames=unit.expected_frames,
        )
        for index, label in zip(
            unit.target_model_frame_indices,
            unit.expected_causal_fir_target_world_x_blocks,
            strict=True,
        ):
            if index - KERNEL_LENGTH + 1 < 0:
                raise ExperimentIIIError(
                    "FIR_INCOMPLETE_HISTORY",
                    f"{unit.unit_id} row {index} lacks complete causal history",
                )
            rows.append([float(positions[index - lag]) for lag in KERNEL_LAGS])
            labels.append(float(label))
    return np.asarray(rows, dtype=np.float64), np.asarray(labels, dtype=np.float64)


def recover_fir_kernels() -> dict[str, Any]:
    """Reproduce the authority 5.3 recovery and refuse unless every gate holds.

    Deterministic and outcome-blind: it reads regenerated paths and the
    materialized labels of the bound manifest, and nothing else. The result is a
    measurement calibration inherited from the same speed-2.0 apparatus; it may
    never be refitted from Experiment III data.
    """
    units = aprime_materialized_units()

    # Step 1 - refuse the entire recovery if any unit's path fails to reproduce.
    path_hashes_reproduced = 0
    for unit in units:
        positions, _ = aprime_generate_path(
            noise_seed=unit.noise_seed,
            start_world_x=unit.start_world_x,
            direction=unit.direction,
            q=unit.motion_noise_q,
            speed=unit.speed_blocks_per_second,
            frames=unit.expected_frames,
        )
        if path_sha256(positions) != unit.expected_path_sha256:
            raise ExperimentIIIError(
                "FIR_KERNEL_RECOVERY_FAILED",
                f"{unit.unit_id} path hash does not reproduce; recovery refused",
            )
        path_hashes_reproduced += 1
    if path_hashes_reproduced != ACCEPTANCE_GATES["path_hashes_reproduced"]:
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED",
            f"reproduced {path_hashes_reproduced} path hashes, expected "
            f"{ACCEPTANCE_GATES['path_hashes_reproduced']}",
        )

    diagnostics: dict[str, Any] = {}
    recovered: dict[str, list[float]] = {}
    labels_reproduced = 0
    max_abs_label_error = 0.0

    for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
        design, targets = _design_for(units, direction)
        # Steps 2-3: least squares over all units of that direction.
        solution, _residuals, rank, _singular = np.linalg.lstsq(
            design, targets, rcond=None
        )
        residual = float(np.abs(design @ solution - targets).max())
        tap_sum = math.fsum(solution)
        min_tap = float(solution.min())

        # Step 4: acceptance gates.
        if int(rank) != ACCEPTANCE_GATES["design_rank"]:
            raise ExperimentIIIError(
                "FIR_KERNEL_RECOVERY_FAILED",
                f"{direction} design rank is {int(rank)}, expected "
                f"{ACCEPTANCE_GATES['design_rank']}",
            )
        if min_tap < ACCEPTANCE_GATES["min_tap"]:
            raise ExperimentIIIError(
                "FIR_KERNEL_RECOVERY_FAILED",
                f"{direction} has a negative tap: {min_tap!r}",
            )
        if abs(tap_sum - 1.0) > ACCEPTANCE_GATES["tap_sum_tolerance"]:
            raise ExperimentIIIError(
                "FIR_KERNEL_RECOVERY_FAILED",
                f"{direction} tap sum is {tap_sum!r}, expected 1 within "
                f"{ACCEPTANCE_GATES['tap_sum_tolerance']}",
            )
        if residual > ACCEPTANCE_GATES["max_abs_residual_blocks"]:
            raise ExperimentIIIError(
                "FIR_KERNEL_RECOVERY_FAILED",
                f"{direction} max abs residual is {residual!r} blocks, exceeding "
                f"{ACCEPTANCE_GATES['max_abs_residual_blocks']}",
            )

        rounded = [round(float(value), 10) for value in solution]
        # A recovered tap may be the exact float -0.0; +0.0 is the same value and
        # keeps the nonnegativity gate of ``normalized_kernel`` satisfied.
        rounded = [0.0 if value == 0.0 else value for value in rounded]
        recovered[direction] = rounded

        support = kernel_positive_mass_support(rounded)
        low, high = ACCEPTANCE_GATES["positive_support_within"]
        if not (low <= support[0] and support[1] <= high):
            raise ExperimentIIIError(
                "FIR_KERNEL_RECOVERY_FAILED",
                f"{direction} positive support {support} escapes [{low},{high}]",
            )
        diagnostics[direction] = {
            "design_rows": int(design.shape[0]),
            "design_rank": int(rank),
            "max_abs_residual_exact_solution": residual,
            "tap_sum_exact_solution": tap_sum,
            "min_tap_exact_solution": min_tap,
            "group_delay_ticks": kernel_group_delay_ticks(rounded),
            "mode_lag": kernel_mode_lag(rounded),
            "positive_mass_support": list(support),
            "off_peak_mass": kernel_off_peak_mass(rounded),
        }

    # Aggregate diagnostics must match A-prime's own frozen forensic reference.
    aggregate = [
        math.fsum(
            normalized_kernel(recovered[direction])[lag]
            for direction in recovered
        )
        / len(recovered)
        for lag in KERNEL_LAGS
    ]
    aggregate_mode_lag = kernel_mode_lag(aggregate)
    if aggregate_mode_lag != ACCEPTANCE_GATES["aggregate_mode_lag"]:
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED",
            f"aggregate mode lag is {aggregate_mode_lag}, expected "
            f"{ACCEPTANCE_GATES['aggregate_mode_lag']}",
        )

    # Step 5: re-derive every materialized label from the recovered taps.
    for unit in units:
        positions, _ = aprime_generate_path(
            noise_seed=unit.noise_seed,
            start_world_x=unit.start_world_x,
            direction=unit.direction,
            q=unit.motion_noise_q,
            speed=unit.speed_blocks_per_second,
            frames=unit.expected_frames,
        )
        derived = causal_fir_targets(
            [float(value) for value in positions],
            list(unit.target_model_frame_indices),
            recovered[unit.direction],
        )
        for observed, expected in zip(
            derived, unit.expected_causal_fir_target_world_x_blocks, strict=True
        ):
            error = abs(observed - expected)
            max_abs_label_error = max(max_abs_label_error, error)
            if error > 1e-9:
                raise ExperimentIIIError(
                    "FIR_KERNEL_RECOVERY_FAILED",
                    f"{unit.unit_id} label error {error!r} exceeds 1e-9",
                )
            labels_reproduced += 1
    if labels_reproduced != ACCEPTANCE_GATES["labels_reproduced"]:
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED",
            f"reproduced {labels_reproduced} labels, expected "
            f"{ACCEPTANCE_GATES['labels_reproduced']}",
        )

    for direction, taps in recovered.items():
        frozen = list(RECOVERED_TAPS[direction])
        if taps != frozen:
            raise ExperimentIIIError(
                "FIR_KERNEL_RECOVERY_FAILED",
                f"{direction} recovered taps differ from the authority values: "
                f"{taps} vs {frozen}",
            )

    return {
        "recovered_kernels": recovered,
        "diagnostics": diagnostics,
        "aggregate_diagnostics": {
            "mode_lag": aggregate_mode_lag,
            "positive_mass_support": list(kernel_positive_mass_support(aggregate)),
            "group_delay_ticks": kernel_group_delay_ticks(aggregate),
        },
        "verification": {
            "path_hashes_checked": len(units),
            "path_hashes_reproduced": path_hashes_reproduced,
            "labels_checked": labels_reproduced,
            "labels_reproduced": labels_reproduced,
            "max_abs_label_error_rounded_10dp": max_abs_label_error,
        },
        "acceptance_gates_all_passed": True,
        "result": "RECOVERED_AND_VERIFIED",
    }


def fir_recovery_receipt() -> dict[str, Any]:
    """The A1 ``fir_kernel_recovery_receipt.json`` body."""
    recovery = recover_fir_kernels()
    normalized = {
        direction: list(frozen_kernel(direction)) for direction in RECOVERED_TAPS
    }
    return {
        "schema_version": "mineocclude-experiment-iii-fir-kernel-recovery-v1",
        "produced_by": "A1_IMPLEMENTATION",
        "authority_section": "5.3",
        "recovery_source": {
            "commit": FIR_RECOVERY_COMMIT,
            "path": FIR_RECOVERY_PATH,
            "bytes_sha256": FIR_RECOVERY_SHA256,
            "capture_units": 50,
        },
        "kernel_length": KERNEL_LENGTH,
        "kernel_lags": list(KERNEL_LAGS),
        "first_fully_resolved_tick": FIRST_FULLY_RESOLVED_TICK,
        "normalization": {
            "rule": "normalized[k] = taps[k] / math.fsum(taps); accumulate with math.fsum",
            "applied_once_at_load": True,
            "raw_tap_fsum": {
                direction: math.fsum(taps)
                for direction, taps in RECOVERED_TAPS.items()
            },
            "normalized_kernels": normalized,
        },
        "acceptance_gates": ACCEPTANCE_GATES
        | {"positive_support_within": list(ACCEPTANCE_GATES["positive_support_within"])},
        **recovery,
        "constraints": {
            "refit_from_experiment_iii_data_allowed": False,
            "failure_blocker": "FIR_KERNEL_RECOVERY_FAILED",
        },
    }
