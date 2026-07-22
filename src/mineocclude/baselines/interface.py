"""Shared row schema for MineOcclude non-model baselines (Person D).

``TrajectoryContext`` is Person D's own internal representation of "what a
baseline is legally allowed to see" -- it is deliberately not a copy of
Person B's universal identity row (docs/contracts/identity_v1.md), which
carries many fields (episode_id, server_tick, code/model/preprocess
hashes, lifecycle...) that are irrelevant to closed-form/fitted baseline
logic. What *does* have to match B's frozen vocabulary is the exported
handoff: ``target_name`` values (``mu_oracle_blocks`` /
``log_sigma_oracle``, matching docs/contracts/person_b_oracle_target_v0_1.md
and configs/analysis/core.yaml) and the D-to-B baseline-input document
shape validated by ``mineocclude.contracts.analysis_inputs
.validate_baseline_input`` (schema ``person-b-baseline-input-v0.1``); see
:mod:`mineocclude.baselines.export` for the document builder.

Design rule (roadmap D1/D3): a baseline must only ever see information
that is legally available to an observer at inference time. Hidden
ground truth (``x_true``) simply does not appear as a field anywhere
on ``TrajectoryContext`` -- baseline functions physically cannot read
what was never passed to them. Do not add a hidden-truth field to this
class; if a future baseline genuinely needs it (there should not be
one), it belongs on a separate oracle-only/scoring type instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Optional

Regime = Literal["A", "B"]
TargetName = Literal["mu_oracle_blocks", "log_sigma_oracle"]

#: Baseline predictions are only ever produced for these two oracle
#: targets. Adding a new target name elsewhere must extend this tuple
#: so downstream code (fold pairing, leakage audits) stays exhaustive.
TARGET_NAMES: tuple[TargetName, ...] = ("mu_oracle_blocks", "log_sigma_oracle")


@dataclass(frozen=True)
class TrajectoryContext:
    """One model frame's legally observable inputs.

    Every field here must be something a baseline is allowed to see:
    either an experimental condition (known by design, e.g. scripted
    ``v``/``q`` in Regime A) or something derived from the visible
    portion of the trajectory. There is deliberately no hidden-truth
    field on this type.
    """

    trajectory_id: str
    layout_id: str
    model_frame_idx: int
    fold: int
    regime: Regime
    tau_seconds: float
    """Elapsed hidden time; 0.0 while the target is visible."""
    visibility: bool

    last_seen_position_blocks: Optional[float]
    """Wall-parallel position at the most recent visible frame (None
    if the target has not yet been seen)."""
    last_seen_velocity_blocks_per_s: Optional[float]
    """Velocity estimated from the visible window ending at the
    last-seen frame. This is an *estimate*, never the scripted ``v``."""

    v_scripted_blocks_per_s: Optional[float]
    """Regime A only: the known experimental drift. Must only be
    consumed by an explicitly privileged/oracle-labeled baseline, never
    by last-seen / constant-velocity / time-only, which use only
    ``last_seen_velocity_blocks_per_s``."""
    q_scripted_blocks2_per_s: Optional[float]
    """Regime A only: the known experimental process noise. Same
    privilege rule as ``v_scripted_blocks_per_s``."""

    duration_seconds: Optional[float]
    config_hash: str
    seed: Optional[int]


@dataclass(frozen=True)
class BaselineRow:
    """One baseline prediction, matching the roadmap's required field
    list (D1.2): trajectory/layout/model frame/fold, target, baseline
    name, prediction, visibility, tau, v, q, duration, regime, config
    hash, seed, and fit metadata.
    """

    trajectory_id: str
    layout_id: str
    model_frame_idx: int
    fold: int
    regime: Regime
    target_name: TargetName
    baseline_name: str
    prediction: Optional[float]
    applicable: bool
    """False means "this baseline does not define a prediction for
    this target/row" (e.g. last-seen has no spread). Per D3.2, a
    non-applicable row must never be scored as if prediction == 0."""
    visibility: bool
    tau_seconds: float
    v_scripted_blocks_per_s: Optional[float]
    q_scripted_blocks2_per_s: Optional[float]
    duration_seconds: Optional[float]
    config_hash: str
    seed: Optional[int]
    fit_metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.applicable and self.prediction is not None:
            raise ValueError(
                "a non-applicable BaselineRow must not carry a numeric "
                "prediction (found "
                f"{self.prediction!r} for baseline={self.baseline_name!r} "
                f"target={self.target_name!r}); use prediction=None"
            )
        if self.applicable and self.prediction is None:
            raise ValueError(
                "an applicable BaselineRow must carry a numeric prediction "
                f"(baseline={self.baseline_name!r} target={self.target_name!r})"
            )


def make_baseline_row(
    ctx: TrajectoryContext,
    *,
    baseline_name: str,
    target_name: TargetName,
    prediction: Optional[float],
    applicable: bool,
    fit_metadata: Optional[Mapping[str, object]] = None,
) -> BaselineRow:
    """Build a :class:`BaselineRow` from a context plus baseline output.

    Centralizing this keeps every baseline module honest about copying
    the full required field list from the context, so a future new
    field only needs to be added in one place.
    """

    return BaselineRow(
        trajectory_id=ctx.trajectory_id,
        layout_id=ctx.layout_id,
        model_frame_idx=ctx.model_frame_idx,
        fold=ctx.fold,
        regime=ctx.regime,
        target_name=target_name,
        baseline_name=baseline_name,
        prediction=prediction,
        applicable=applicable,
        visibility=ctx.visibility,
        tau_seconds=ctx.tau_seconds,
        v_scripted_blocks_per_s=ctx.v_scripted_blocks_per_s,
        q_scripted_blocks2_per_s=ctx.q_scripted_blocks2_per_s,
        duration_seconds=ctx.duration_seconds,
        config_hash=ctx.config_hash,
        seed=ctx.seed,
        fit_metadata=dict(fit_metadata or {}),
    )
