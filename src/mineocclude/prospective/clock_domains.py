"""Explicit clock domains for capture pipelines.

The P3 terminal forensic audit and the P2 temporal-alignment audit both found
that the historical pipeline treated ``server_tick``, ``render_frame_idx``,
``action_idx`` and ``model_frame_idx`` as one interchangeable integer.  They are
not.  A rendered frame carries entity geometry that is a *causally smoothed*
function of earlier server states, so "the frame with index i" and "the server
state with index i" denote different physical instants.

This module makes the domains nominal, so that a conversion is a visible,
auditable act rather than an implicit identity.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass


class UnresolvedAlignment(RuntimeError):
    """Raised when a cross-domain conversion is attempted without evidence.

    Fail-closed by design: a prospective pipeline must refuse to emit
    scientific rows whose clock domain it cannot justify.
    """


class ClockDomain(enum.Enum):
    """Physically distinct time bases in the capture chain.

    Ordered along the causal chain.  ``SERVER_ENTITY_STATE`` is the authoritative
    simulation clock; every later domain is downstream of it and may lag.
    """

    SERVER_TICK = "server_tick"
    SERVER_ENTITY_STATE = "server_entity_state"
    NETWORK_UPDATE = "network_update"
    CLIENT_ENTITY_STATE = "client_entity_state"
    CLIENT_RENDER = "client_render"
    CAPTURE_FRAME = "capture_frame"
    VIDEO_FRAME = "video_frame"
    MODEL_FRAME = "model_frame"
    ACTIVATION_ROW = "activation_row"
    GROUND_TRUTH_TARGET = "ground_truth_target"

    @property
    def is_downstream_of_render(self) -> bool:
        return self in {
            ClockDomain.CAPTURE_FRAME,
            ClockDomain.VIDEO_FRAME,
            ClockDomain.MODEL_FRAME,
            ClockDomain.ACTIVATION_ROW,
        }


@dataclass(frozen=True)
class DomainIndex:
    """An integer index that knows which clock it is counted on."""

    domain: ClockDomain
    index: int

    def __post_init__(self) -> None:
        if not isinstance(self.domain, ClockDomain):
            raise TypeError("domain must be a ClockDomain")
        if not isinstance(self.index, int) or isinstance(self.index, bool):
            raise TypeError("index must be a plain int")
        if self.index < 0:
            raise ValueError("index must be non-negative")

    def same_domain(self, other: "DomainIndex") -> bool:
        return self.domain is other.domain


@dataclass(frozen=True)
class TimebaseSpec:
    """Cadence of one capture configuration.

    ``server_ticks_per_model_frame`` records the subsampling factor between the
    simulation clock and the model's input cadence.  It is 1 for the historical
    Regime A / P2 / P3 apparatus (20 Hz lockstep, one action / one frame / one
    server tick), but must never be *assumed* to be 1.
    """

    seconds_per_server_tick: float
    server_ticks_per_model_frame: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.seconds_per_server_tick, bool)
            or not isinstance(self.seconds_per_server_tick, (int, float))
            or not math.isfinite(float(self.seconds_per_server_tick))
            or self.seconds_per_server_tick <= 0
        ):
            raise ValueError("seconds_per_server_tick must be a finite positive number")
        if (
            not isinstance(self.server_ticks_per_model_frame, int)
            or isinstance(self.server_ticks_per_model_frame, bool)
            or self.server_ticks_per_model_frame < 1
        ):
            raise ValueError("server_ticks_per_model_frame must be a positive plain int")

    @property
    def seconds_per_model_frame(self) -> float:
        return self.seconds_per_server_tick * self.server_ticks_per_model_frame

    def ticks_to_seconds(self, ticks: float) -> float:
        return self._finite(ticks, "ticks") * self.seconds_per_server_tick

    def seconds_to_ticks(self, seconds: float) -> float:
        return self._finite(seconds, "seconds") / self.seconds_per_server_tick

    def ticks_to_model_frames(self, ticks: float) -> float:
        return self._finite(ticks, "ticks") / self.server_ticks_per_model_frame

    def model_frames_to_ticks(self, frames: float) -> float:
        return self._finite(frames, "frames") * self.server_ticks_per_model_frame

    def blocks_per_tick(self, blocks_per_second: float) -> float:
        speed = self._finite(blocks_per_second, "blocks_per_second")
        if speed <= 0:
            raise ValueError("blocks_per_second must be positive")
        return speed * self.seconds_per_server_tick

    def lag_ticks_to_blocks(self, lag_ticks: float, blocks_per_second: float) -> float:
        """World displacement corresponding to a temporal lag at a given speed."""
        return self._finite(lag_ticks, "lag_ticks") * self.blocks_per_tick(
            blocks_per_second
        )

    @staticmethod
    def _finite(value: float, name: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError(f"{name} must be a finite number")
        return float(value)


def require_same_domain(a: DomainIndex, b: DomainIndex) -> None:
    """Guard for code that would otherwise silently equate two clocks."""
    if not a.same_domain(b):
        raise UnresolvedAlignment(
            f"refusing to combine {a.domain.value} index {a.index} with "
            f"{b.domain.value} index {b.index} without an explicit alignment"
        )
