"""Physical temporal-alignment measurement with caller-owned adjudication."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from numbers import Real
from typing import Iterable, Sequence

import numpy as np

from mineocclude.prospective.clock_domains import TimebaseSpec, UnresolvedAlignment

__all__ = [
    "AlignmentEvidence",
    "AlignmentRequirements",
    "UncertaintyRequest",
    "AlignmentEstimate",
    "estimate_alignment",
    "EvidenceScope",
    "PURE_DELAY_OFF_PEAK_MASS_TOLERANCE",
    "canonical_fir_sum",
    "normalized_kernel",
    "kernel_off_peak_mass",
    "kernel_group_delay_ticks",
    "kernel_is_effectively_pure_delay",
]


VALID_DIRECTIONS = frozenset({"LEFT_TO_RIGHT", "RIGHT_TO_LEFT"})

# Numerical tolerance only. A normalized causal FIR kernel carrying all but this
# fraction of its mass on a single tap is not numerically separable from a bare
# integer-tick delay in binary64, so counting "how many taps are > 0" is not a
# usable pure-delay test: [1e-300, 0, 0, 1, 0, ...] has two positive taps and is
# still a 3-tick delay. This constant is a float64 round-off allowance, NOT a
# scientific threshold -- it makes no claim about how much smoothing is
# physically meaningful. The scientific requirement (that the fitted FIR
# actually beats the best pure delay on every trajectory) is enforced
# separately by the caller's authority-bound improvement-coverage rule.
PURE_DELAY_OFF_PEAK_MASS_TOLERANCE = 1e-9


def canonical_fir_sum(terms: Iterable[float]) -> float:
    """The canonical binary64 reduction for every causal-FIR quantity.

    Exactly-rounded (correctly-rounded) summation: the returned double is the
    nearest binary64 to the exact real sum of ``terms``, independently of the
    order the terms arrive in and -- critically -- independently of the CPython
    version executing it.

    The built-in ``sum()`` is NOT a substitute. It is naive left-to-right
    accumulation through CPython 3.11 and Neumaier-compensated from 3.12
    onwards, so the same frozen inputs produce different binary64 outputs on
    different qualified interpreters. Stage-2 materializes trajectory labels
    once and re-derives them at capture time under the pinned mineworld
    interpreter; an interpreter-dependent reduction makes that exact
    re-derivation unsatisfiable by construction. Every FIR reduction in this
    module already used ``math.fsum``; this function names that rule so the
    materializer and the capture-side verifier can be shown to share one
    arithmetic, rather than two implementations that happen to agree.
    """
    return math.fsum(terms)


def normalized_kernel(taps: Sequence[float]) -> list[float]:
    """Return a nonnegative causal kernel rescaled to unit mass."""
    values = [_finite(tap, "FIR coefficient") for tap in taps]
    if len(values) < 2:
        raise ValueError("a causal FIR kernel requires at least two taps")
    if any(value < 0 for value in values):
        raise ValueError("a causal FIR kernel must be nonnegative")
    total = canonical_fir_sum(values)
    if not total > 0 or not math.isfinite(total):
        raise ValueError("a causal FIR kernel must carry positive mass")
    return [value / total for value in values]


def kernel_off_peak_mass(taps: Sequence[float]) -> float:
    """Normalized mass lying off the single largest tap."""
    kernel = normalized_kernel(taps)
    return 1.0 - max(kernel)


def kernel_group_delay_ticks(taps: Sequence[float]) -> float:
    """First moment of the normalized kernel, in ticks."""
    kernel = normalized_kernel(taps)
    return canonical_fir_sum(lag * tap for lag, tap in enumerate(kernel))


def kernel_mode_lag(taps: Sequence[float]) -> int:
    """Lag index carrying the largest mass; lowest index wins a tie.

    This is the estimand of a single-tap lag search such as
    ``derivative_cross_correlation_lag``, which selects the one lag whose
    increments best explain the rendered increments. It is a different
    functional of the same kernel from :func:`kernel_group_delay_ticks`, and for
    a right-tailed causal response it is strictly smaller.
    """
    kernel = normalized_kernel(taps)
    return max(range(len(kernel)), key=lambda lag: (kernel[lag], -lag))


def kernel_positive_mass_support(taps: Sequence[float]) -> tuple[int, int]:
    """Lowest and highest lag index carrying non-zero mass."""
    kernel = normalized_kernel(taps)
    carried = [lag for lag, tap in enumerate(kernel) if tap > 0.0]
    if not carried:
        raise ValueError("a causal FIR kernel must carry positive mass")
    return carried[0], carried[-1]


def kernel_is_effectively_pure_delay(
    taps: Sequence[float],
    *,
    tolerance: float = PURE_DELAY_OFF_PEAK_MASS_TOLERANCE,
) -> bool:
    """Whether the kernel is numerically indistinguishable from a bare delay.

    Measured from kernel mass, never from decoder or Stage-1 outcomes.
    """
    allowance = _finite(tolerance, "pure-delay off-peak mass tolerance")
    if allowance < 0:
        raise ValueError("pure-delay off-peak mass tolerance must be non-negative")
    return kernel_off_peak_mass(taps) <= allowance


class EvidenceScope:
    SYNTHETIC_ACTION_CAMERA = "synthetic_action_camera_contract_only"
    REAL_ENTITY_RENDER_VS_STATE = "real_entity_render_vs_server_entity_state"


def _plain_positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive plain int")
    return value


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class AlignmentEvidence:
    """One explicitly mapped server-state/render-model trajectory."""

    trajectory_id: str
    logged_position: np.ndarray
    rendered_position: np.ndarray
    direction: str
    blocks_per_second: float
    scene: str
    exclude_mask: np.ndarray
    server_state_ticks: np.ndarray
    render_model_frame_indices: np.ndarray

    def __post_init__(self) -> None:
        if not isinstance(self.trajectory_id, str) or not self.trajectory_id:
            raise ValueError("trajectory_id must be explicit")
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(f"direction must be one of {sorted(VALID_DIRECTIONS)}")
        speed = _finite(self.blocks_per_second, "blocks_per_second")
        if speed <= 0:
            raise ValueError("blocks_per_second must be positive")
        if not isinstance(self.scene, str) or not self.scene:
            raise ValueError("scene must be explicit")

        logged = np.array(self.logged_position, dtype=np.float64, copy=True)
        rendered = np.array(self.rendered_position, dtype=np.float64, copy=True)
        if logged.ndim != 1 or rendered.ndim != 1 or logged.shape != rendered.shape:
            raise ValueError("logged and rendered series must be equal-length 1-D arrays")
        if logged.size < 3:
            raise ValueError("at least three observations are required")
        if not np.isfinite(logged).all() or not np.isfinite(rendered).all():
            raise ValueError("observation arrays must be finite; use the explicit mask")

        mask = np.array(self.exclude_mask, copy=True)
        if mask.dtype != np.bool_ or mask.ndim != 1 or mask.shape != logged.shape:
            raise ValueError("exclude_mask must be an equal-shape one-dimensional bool array")
        server_ticks = np.array(self.server_state_ticks, copy=True)
        model_frames = np.array(self.render_model_frame_indices, copy=True)
        for name, values in (
            ("server_state_ticks", server_ticks),
            ("render_model_frame_indices", model_frames),
        ):
            if values.ndim != 1 or values.shape != logged.shape or values.dtype.kind not in "iu":
                raise ValueError(f"{name} must be an equal-shape one-dimensional integer array")
            if np.any(values < 0) or len(np.unique(values)) != len(values) or np.any(np.diff(values) <= 0):
                raise ValueError(f"{name} must be non-negative, strictly ordered, and unique")
            if np.any(np.diff(values) != 1):
                raise ValueError(
                    f"{name} must have unit spacing; this estimator reports lag in ticks "
                    "and does not infer ticks from irregular array offsets"
                )

        server_ticks = server_ticks.astype(np.int64, copy=True)
        model_frames = model_frames.astype(np.int64, copy=True)
        for values in (logged, rendered, mask, server_ticks, model_frames):
            values.flags.writeable = False

        object.__setattr__(self, "blocks_per_second", speed)
        object.__setattr__(self, "logged_position", logged)
        object.__setattr__(self, "rendered_position", rendered)
        object.__setattr__(self, "exclude_mask", mask)
        object.__setattr__(self, "server_state_ticks", server_ticks)
        object.__setattr__(self, "render_model_frame_indices", model_frames)


@dataclass(frozen=True)
class UncertaintyRequest:
    """Request a Student-t interval, and optionally a trajectory bootstrap.

    The bootstrap is optional because a caller whose authority carries no
    interval-width gate has nothing to spend a replicate count and seed on.
    Requiring them anyway would force such a caller to invent two numbers that
    no authority derives and no rule reads, which is exactly the kind of
    unjustified constant this package refuses. Both must be supplied together
    or omitted together.
    """

    confidence_level: float
    bootstrap_replicates: int | None = None
    bootstrap_seed: int | None = None

    def __post_init__(self) -> None:
        confidence = _finite(self.confidence_level, "confidence_level")
        if not 0 < confidence < 1:
            raise ValueError("confidence_level must lie strictly between zero and one")
        if (self.bootstrap_replicates is None) != (self.bootstrap_seed is None):
            raise ValueError(
                "bootstrap_replicates and bootstrap_seed must be supplied together"
            )
        if self.bootstrap_replicates is None:
            return
        _plain_positive_int(self.bootstrap_replicates, "bootstrap_replicates")
        if not isinstance(self.bootstrap_seed, int) or isinstance(self.bootstrap_seed, bool):
            raise ValueError("bootstrap_seed must be a plain int")


@dataclass(frozen=True)
class AlignmentRequirements:
    """Authority-supplied evidence coverage and acceptance requirements."""

    minimum_trajectories: int
    required_directions: frozenset[str]
    required_speeds: frozenset[float]
    required_scenes: frozenset[str]
    minimum_usable_samples_per_trajectory: int
    maximum_t_interval_width_ticks: float
    maximum_pure_delay_relative_improvement: float
    # When the caller's authority forbids a pure-delay interpretation, the sign
    # of the pure-delay requirement inverts: the fit must be separable from a
    # bare delay and must beat the best pure delay on *every* trajectory, so a
    # single large-improvement trajectory cannot rescue widespread failure.
    pure_delay_interpretation_allowed: bool = True
    pure_delay_off_peak_mass_tolerance: float = PURE_DELAY_OFF_PEAK_MASS_TOLERANCE

    def __post_init__(self) -> None:
        _plain_positive_int(self.minimum_trajectories, "minimum_trajectories")
        _plain_positive_int(
            self.minimum_usable_samples_per_trajectory,
            "minimum_usable_samples_per_trajectory",
        )
        if not self.required_directions or not self.required_directions <= VALID_DIRECTIONS:
            raise ValueError("required_directions must be a non-empty valid direction set")
        if not self.required_speeds:
            raise ValueError("required_speeds must be non-empty")
        for speed in self.required_speeds:
            if _finite(speed, "required speed") <= 0:
                raise ValueError("required speeds must be positive")
        if not self.required_scenes or any(
            not isinstance(scene, str) or not scene for scene in self.required_scenes
        ):
            raise ValueError("required_scenes must be non-empty explicit labels")
        if _finite(
            self.maximum_t_interval_width_ticks,
            "maximum_t_interval_width_ticks",
        ) < 0:
            raise ValueError("maximum uncertainty width must be non-negative")
        discrepancy = _finite(
            self.maximum_pure_delay_relative_improvement,
            "maximum_pure_delay_relative_improvement",
        )
        if discrepancy < 0:
            raise ValueError("pure-delay discrepancy allowance must be non-negative")
        if not isinstance(self.pure_delay_interpretation_allowed, bool):
            raise ValueError("pure_delay_interpretation_allowed must be an explicit bool")
        if _finite(
            self.pure_delay_off_peak_mass_tolerance,
            "pure_delay_off_peak_mass_tolerance",
        ) < 0:
            raise ValueError("pure-delay off-peak mass tolerance must be non-negative")


@dataclass
class AlignmentEstimate:
    measured: bool
    resolved: bool
    adjudication: str
    group_delay_ticks: float | None
    sample_statistics: dict | None
    t_interval_ticks: tuple[float, float] | None
    trajectory_bootstrap_interval_ticks: tuple[float, float] | None
    kernel: list[float] | None
    fir_vs_pure_delay_relative_improvement: float | None
    kernel_is_pure_delay: bool | None
    per_trajectory: list[dict] = field(default_factory=list)
    refusal_reason: str | None = None
    evidence_scope: str = EvidenceScope.REAL_ENTITY_RENDER_VS_STATE
    timebase: TimebaseSpec | None = None

    @property
    def group_delay_ci95(self) -> tuple[float, float] | None:
        """Legacy alias; callers should inspect the recorded confidence level."""
        return self.t_interval_ticks

    def require_resolved(self) -> "AlignmentEstimate":
        if not self.resolved:
            raise UnresolvedAlignment(
                f"temporal alignment not authority-resolved: {self.refusal_reason}"
            )
        return self

    def group_delay_seconds(self) -> float:
        estimate = self.require_resolved()
        assert estimate.timebase is not None and estimate.group_delay_ticks is not None
        return estimate.timebase.ticks_to_seconds(estimate.group_delay_ticks)

    def group_delay_model_frames(self) -> float:
        estimate = self.require_resolved()
        assert estimate.timebase is not None and estimate.group_delay_ticks is not None
        return estimate.timebase.ticks_to_model_frames(estimate.group_delay_ticks)

    def group_delay_blocks(self, blocks_per_second: float) -> float:
        estimate = self.require_resolved()
        assert estimate.timebase is not None and estimate.group_delay_ticks is not None
        return estimate.timebase.lag_ticks_to_blocks(
            estimate.group_delay_ticks, blocks_per_second
        )

    def receipt(self) -> dict:
        return {
            "artifact_id": "prospective-temporal-alignment-receipt-v0.2",
            "evidence_scope": self.evidence_scope,
            "measured": self.measured,
            "resolved": self.resolved,
            "adjudication": self.adjudication,
            "refusal_reason": self.refusal_reason,
            "group_delay_ticks": self.group_delay_ticks,
            "sample_statistics": self.sample_statistics,
            "t_interval_ticks": None
            if self.t_interval_ticks is None
            else list(self.t_interval_ticks),
            "trajectory_bootstrap_interval_ticks": None
            if self.trajectory_bootstrap_interval_ticks is None
            else list(self.trajectory_bootstrap_interval_ticks),
            "kernel": self.kernel,
            "fir_vs_pure_delay_relative_improvement": self.fir_vs_pure_delay_relative_improvement,
            "kernel_is_pure_delay": self.kernel_is_pure_delay,
            "seconds_per_server_tick": None
            if self.timebase is None
            else self.timebase.seconds_per_server_tick,
            "server_ticks_per_model_frame": None
            if self.timebase is None
            else self.timebase.server_ticks_per_model_frame,
            "trajectory_count": len(self.per_trajectory),
            "per_trajectory": self.per_trajectory,
            "estimation_is_independent_of_decoder_performance": True,
            "scientific_requirements_are_caller_supplied": True,
        }


def _fit_one(item: AlignmentEvidence, max_lag: int) -> dict | None:
    logged = item.logged_position
    rendered = item.rendered_position
    d_logged = np.diff(logged)
    d_rendered = np.diff(rendered)
    usable = ~(item.exclude_mask[:-1] | item.exclude_mask[1:])
    idx = np.nonzero(usable)[0]
    idx = idx[idx >= max_lag]
    if idx.size < max_lag + 1:
        return None

    design = np.stack([d_logged[idx - lag] for lag in range(max_lag + 1)], axis=1)
    observed = d_rendered[idx]
    sign = -1.0 if float(np.sum(design[:, 0] * observed)) < 0 else 1.0

    from scipy.optimize import nnls

    coefficients, _ = nnls(design, sign * observed)
    total = float(coefficients.sum())
    if total <= 0 or not math.isfinite(total):
        return None
    kernel = coefficients / total
    group_delay = float(np.sum(np.arange(max_lag + 1) * kernel))
    fitted = sign * (design @ coefficients)
    filter_residual = float(np.sqrt(np.mean((observed - fitted) ** 2)))

    best_tick, pure_residual = 0, math.inf
    for lag in range(max_lag + 1):
        column = d_logged[idx - lag][:, None]
        scale, *_ = np.linalg.lstsq(column, observed, rcond=None)
        rms = float(np.sqrt(np.mean((observed - column @ scale) ** 2)))
        if rms < pure_residual:
            best_tick, pure_residual = lag, rms
    improvement = (
        (pure_residual - filter_residual) / pure_residual
        if pure_residual > 0
        else 0.0
    )
    exact_mapping = [
        {
            "render_model_frame_index": int(item.render_model_frame_indices[index + 1]),
            "server_state_ticks_in_fir": [
                int(item.server_state_ticks[index + 1 - lag])
                for lag in range(max_lag + 1)
            ],
        }
        for index in idx
    ]
    return {
        "trajectory_id": item.trajectory_id,
        "direction": item.direction,
        "scene": item.scene,
        "blocks_per_second": item.blocks_per_second,
        "kernel": kernel.tolist(),
        "group_delay_ticks": group_delay,
        "filter_residual": filter_residual,
        "pure_delay_best_ticks": best_tick,
        "pure_delay_residual": pure_residual,
        "fir_vs_pure_delay_relative_improvement": improvement,
        "sample_count": int(idx.size),
        "rendered_axis_sign": sign,
        "server_state_to_render_model_target_mapping": exact_mapping,
    }


def _unresolved(reason: str, timebase: TimebaseSpec, fits: list[dict]) -> AlignmentEstimate:
    return AlignmentEstimate(
        measured=False,
        resolved=False,
        adjudication="INVALID_EVIDENCE",
        group_delay_ticks=None,
        sample_statistics=None,
        t_interval_ticks=None,
        trajectory_bootstrap_interval_ticks=None,
        kernel=None,
        fir_vs_pure_delay_relative_improvement=None,
        kernel_is_pure_delay=None,
        per_trajectory=fits,
        refusal_reason=reason,
        timebase=timebase,
    )


def estimate_alignment(
    evidence: Sequence[AlignmentEvidence],
    *,
    timebase: TimebaseSpec,
    max_lag_ticks: int,
    requirements: AlignmentRequirements | None = None,
    uncertainty: UncertaintyRequest | None = None,
) -> AlignmentEstimate:
    """Measure alignment; only explicit requirements can resolve/adjudicate it."""
    if not isinstance(timebase, TimebaseSpec):
        raise TypeError("timebase must be explicitly supplied")
    _plain_positive_int(max_lag_ticks, "max_lag_ticks")
    if timebase.server_ticks_per_model_frame != 1:
        return _unresolved(
            "evidence has one render/model observation per server tick but the supplied "
            "timebase declares a different cadence",
            timebase,
            [],
        )
    if not evidence:
        return _unresolved("no trajectories supplied", timebase, [])
    ids = [item.trajectory_id for item in evidence]
    if len(set(ids)) != len(ids):
        return _unresolved("trajectory IDs are not unique", timebase, [])

    fits: list[dict] = []
    failed: list[str] = []
    for item in evidence:
        fit = _fit_one(item, max_lag_ticks)
        if fit is None:
            failed.append(item.trajectory_id)
        else:
            fit["group_delay_blocks"] = timebase.lag_ticks_to_blocks(
                fit["group_delay_ticks"], item.blocks_per_second
            )
            fits.append(fit)
    if not fits:
        return _unresolved("no trajectory yielded an estimable FIR fit", timebase, fits)

    delays = np.asarray([fit["group_delay_ticks"] for fit in fits], dtype=np.float64)
    mean = float(delays.mean())
    standard_deviation = float(delays.std(ddof=1)) if delays.size > 1 else None
    standard_error = (
        standard_deviation / math.sqrt(delays.size)
        if standard_deviation is not None
        else None
    )
    stats = {
        "count": int(delays.size),
        "mean": mean,
        "median": float(np.median(delays)),
        "standard_deviation": standard_deviation,
        "standard_error": standard_error,
        "minimum": float(delays.min()),
        "maximum": float(delays.max()),
    }

    t_interval = None
    bootstrap_interval = None
    if uncertainty is not None and delays.size > 1:
        from scipy.stats import t

        alpha = 1.0 - uncertainty.confidence_level
        critical = float(t.ppf(1.0 - alpha / 2.0, df=delays.size - 1))
        assert standard_error is not None
        t_interval = (mean - critical * standard_error, mean + critical * standard_error)
        if uncertainty.bootstrap_replicates is not None:
            rng = np.random.default_rng(uncertainty.bootstrap_seed)
            draws = rng.choice(
                delays,
                size=(uncertainty.bootstrap_replicates, delays.size),
                replace=True,
            ).mean(axis=1)
            bootstrap_interval = tuple(
                float(value)
                for value in np.quantile(draws, [alpha / 2.0, 1.0 - alpha / 2.0])
            )

    kernel = np.mean(np.asarray([fit["kernel"] for fit in fits]), axis=0)
    kernel /= kernel.sum()
    improvements = [fit["fir_vs_pure_delay_relative_improvement"] for fit in fits]
    improvement = float(np.mean(improvements))
    # Measured property of the fitted kernel, independent of whether the caller
    # supplied requirements and independent of any decoder outcome.
    tolerance = (
        PURE_DELAY_OFF_PEAK_MASS_TOLERANCE
        if requirements is None
        else requirements.pure_delay_off_peak_mass_tolerance
    )
    pure_delay = kernel_is_effectively_pure_delay(kernel.tolist(), tolerance=tolerance)
    for fit in fits:
        fit["kernel_off_peak_mass"] = kernel_off_peak_mass(fit["kernel"])
        fit["kernel_is_effectively_pure_delay"] = kernel_is_effectively_pure_delay(
            fit["kernel"], tolerance=tolerance
        )
    reasons: list[str] = []
    if failed:
        reasons.append(f"trajectories without estimable fits: {failed}")
    if requirements is None:
        adjudication = "MEASURED_NOT_ADJUDICATED"
        reasons.append("authority requirements were not supplied")
    else:
        if len(fits) < requirements.minimum_trajectories:
            reasons.append("usable trajectory count is below the caller-supplied minimum")
        directions = {fit["direction"] for fit in fits}
        speeds = {fit["blocks_per_second"] for fit in fits}
        scenes = {fit["scene"] for fit in fits}
        if not requirements.required_directions <= directions:
            reasons.append("required direction coverage is missing")
        if not requirements.required_speeds <= speeds:
            reasons.append("required speed coverage is missing")
        if not requirements.required_scenes <= scenes:
            reasons.append("required scene coverage is missing")
        if any(
            fit["sample_count"] < requirements.minimum_usable_samples_per_trajectory
            for fit in fits
        ):
            reasons.append("per-trajectory usable support is below the caller minimum")
        if t_interval is None:
            reasons.append("requested uncertainty evidence was not supplied or estimable")
        elif t_interval[1] - t_interval[0] > requirements.maximum_t_interval_width_ticks:
            reasons.append("t-interval width exceeds the caller-supplied maximum")
        if requirements.pure_delay_interpretation_allowed:
            if improvement > requirements.maximum_pure_delay_relative_improvement:
                reasons.append(
                    "FIR/pure-delay discrepancy exceeds the caller-supplied maximum"
                )
        else:
            if pure_delay:
                reasons.append(
                    "fitted kernel is numerically indistinguishable from a pure delay"
                )
            if any(
                fit["kernel_is_effectively_pure_delay"] for fit in fits
            ):
                reasons.append(
                    "a per-trajectory kernel is numerically indistinguishable from a pure delay"
                )
            # Coverage, not central tendency: the authority requires the causal
            # FIR to beat the best pure delay, and a mean improvement lets one
            # large trajectory rescue a majority that are worse than a delay.
            if not all(value > 0 for value in improvements):
                reasons.append(
                    "at least one trajectory does not beat its own best pure delay"
                )
        adjudication = "PASS" if not reasons else "FAIL"

    resolved = requirements is not None and not reasons
    return AlignmentEstimate(
        measured=True,
        resolved=resolved,
        adjudication=adjudication,
        group_delay_ticks=mean,
        sample_statistics=stats,
        t_interval_ticks=t_interval,
        trajectory_bootstrap_interval_ticks=bootstrap_interval,
        kernel=kernel.tolist(),
        fir_vs_pure_delay_relative_improvement=improvement,
        kernel_is_pure_delay=pure_delay,
        per_trajectory=fits,
        refusal_reason=None if resolved else "; ".join(reasons),
        timebase=timebase,
    )
