"""Alpha-to-block mapping and activation-norm cap enforcement."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .directions import DirectionError, dot, _finite_vector


@dataclass(frozen=True)
class Dose:
    dose_id: str
    alpha_requested: float
    alpha_applied: float
    intended_block_shift: float
    cap_reduced: bool


def decoded_blocks_per_alpha(
    raw_probe_coefficients: Sequence[float],
    unit_intervention_direction: Sequence[float],
    *,
    near_zero_threshold: float = 1e-12,
) -> float:
    if (
        isinstance(near_zero_threshold, bool)
        or not isinstance(near_zero_threshold, (int, float))
        or not math.isfinite(float(near_zero_threshold))
        or near_zero_threshold <= 0.0
    ):
        raise DirectionError("near_zero_threshold must be finite and positive.")
    effect = dot(raw_probe_coefficients, unit_intervention_direction)
    if abs(effect) <= near_zero_threshold:
        raise DirectionError(
            "Selected direction has near-zero decoded block effect per alpha."
        )
    return effect


def build_alpha_table(
    intended_block_shifts: Sequence[float],
    *,
    blocks_per_alpha: float,
    typical_activation_norm: float,
    max_relative_activation_norm: float = 0.25,
) -> tuple[Dose, ...]:
    """Map signed intended shifts to alpha and transparently apply the cap."""

    shifts = _finite_vector("intended_block_shifts", intended_block_shifts)
    if (
        isinstance(blocks_per_alpha, bool)
        or not isinstance(blocks_per_alpha, (int, float))
        or not math.isfinite(float(blocks_per_alpha))
        or float(blocks_per_alpha) == 0.0
    ):
        raise DirectionError("blocks_per_alpha must be finite and nonzero.")
    for name, value in (
        ("typical_activation_norm", typical_activation_norm),
        ("max_relative_activation_norm", max_relative_activation_norm),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0.0
        ):
            raise DirectionError(f"{name} must be finite and positive.")
    maximum_alpha = float(typical_activation_norm) * float(
        max_relative_activation_norm
    )
    if not math.isfinite(maximum_alpha):
        raise DirectionError("Activation-norm cap overflowed.")
    rows: list[Dose] = []
    for index, shift in enumerate(shifts):
        requested = shift / float(blocks_per_alpha)
        if not math.isfinite(requested):
            raise DirectionError("Requested alpha overflowed.")
        applied = math.copysign(min(abs(requested), maximum_alpha), requested)
        cap_reduced = abs(applied) < abs(requested)
        rows.append(
            Dose(
                dose_id=f"dose_{index:03d}",
                alpha_requested=requested,
                alpha_applied=applied,
                intended_block_shift=shift,
                cap_reduced=cap_reduced,
            )
        )
    return tuple(rows)
