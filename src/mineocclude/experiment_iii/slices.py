"""Frozen token-slice arithmetic (authority 8.4).

Every position here is **derived** from the enforced span contract
(``expected_start = pair_index * 347``; visual ``[start, start+336)``; action
``[start+336, start+347)``) rather than transcribed, so a layout change fails
closed instead of silently mismatching. The derived values are then asserted
against the authority's frozen literals.

    context   = 16 complete visual/action pairs for model frames [t-15, ..., t]
    per pair  = 336 visual tokens then 11 action tokens = 347 tokens
    sequence  = 16 x 347 = 5,552 tokens

    PREVIOUS  pair 14  inclusive 4,858-5,193  python [4858:5194]
    CURRENT   pair 15  inclusive 5,205-5,540  python [5205:5541]

Pair-14 action tokens occupy 5,194-5,204 and pair-15's occupy 5,541-5,551; both
are excluded. Decoder causality means the pair-14 residual cannot attend to pair
15, so both slices are harvested from the SAME teacher-forced call.
"""

from __future__ import annotations

from dataclasses import dataclass

from mineocclude.experiment_iii.authority import CONTEXT_PAIRS
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.schema import TemporalSlice

__all__ = [
    "VISUAL_TOKENS_PER_PAIR",
    "ACTION_TOKENS_PER_PAIR",
    "TOKENS_PER_PAIR",
    "SEQUENCE_LENGTH",
    "HIDDEN_WIDTH",
    "HOOKED_SHAPE",
    "PREVIOUS_PAIR_INDEX",
    "CURRENT_PAIR_INDEX",
    "SliceSpec",
    "SLICE_SPECS",
    "slice_spec",
    "visual_positions",
    "action_positions",
    "verify_slice_arithmetic",
]

VISUAL_TOKENS_PER_PAIR = 336
ACTION_TOKENS_PER_PAIR = 11
TOKENS_PER_PAIR = VISUAL_TOKENS_PER_PAIR + ACTION_TOKENS_PER_PAIR  # 347
SEQUENCE_LENGTH = CONTEXT_PAIRS * TOKENS_PER_PAIR  # 5552
HIDDEN_WIDTH = 2048
HOOKED_SHAPE = (1, SEQUENCE_LENGTH, HIDDEN_WIDTH)

#: The last two pairs of the 16-pair context.
PREVIOUS_PAIR_INDEX = CONTEXT_PAIRS - 2  # 14
CURRENT_PAIR_INDEX = CONTEXT_PAIRS - 1  # 15


def _pair_start(pair_index: int) -> int:
    return pair_index * TOKENS_PER_PAIR


def visual_positions(pair_index: int) -> tuple[int, ...]:
    start = _pair_start(pair_index)
    return tuple(range(start, start + VISUAL_TOKENS_PER_PAIR))


def action_positions(pair_index: int) -> tuple[int, ...]:
    start = _pair_start(pair_index) + VISUAL_TOKENS_PER_PAIR
    return tuple(range(start, start + ACTION_TOKENS_PER_PAIR))


@dataclass(frozen=True)
class SliceSpec:
    """One frozen temporal slice, derived from the span contract."""

    name: TemporalSlice
    pair_index: int
    start: int
    stop_exclusive: int
    excluded_action_start: int
    excluded_action_stop_exclusive: int
    #: 0 for CURRENT, 1 for PREVIOUS: the target row's frame index minus this.
    model_frame_offset: int

    @property
    def python_slice(self) -> slice:
        return slice(self.start, self.stop_exclusive)

    @property
    def inclusive_end(self) -> int:
        return self.stop_exclusive - 1

    @property
    def token_count(self) -> int:
        return self.stop_exclusive - self.start

    def model_frame_idx(self, target_row: int) -> int:
        return target_row - self.model_frame_offset

    def as_dict(self) -> dict[str, object]:
        return {
            "temporal_slice": self.name.value,
            "pair_index": self.pair_index,
            "inclusive_start": self.start,
            "inclusive_end": self.inclusive_end,
            "python_start": self.start,
            "python_stop_exclusive": self.stop_exclusive,
            "excluded_action_inclusive_start": self.excluded_action_start,
            "excluded_action_inclusive_end": self.excluded_action_stop_exclusive - 1,
            "shape": [1, VISUAL_TOKENS_PER_PAIR, HIDDEN_WIDTH],
        }


def _build(name: TemporalSlice, pair_index: int, offset: int) -> SliceSpec:
    visual = visual_positions(pair_index)
    actions = action_positions(pair_index)
    return SliceSpec(
        name=name,
        pair_index=pair_index,
        start=visual[0],
        stop_exclusive=visual[-1] + 1,
        excluded_action_start=actions[0],
        excluded_action_stop_exclusive=actions[-1] + 1,
        model_frame_offset=offset,
    )


SLICE_SPECS: dict[TemporalSlice, SliceSpec] = {
    TemporalSlice.PREVIOUS: _build(TemporalSlice.PREVIOUS, PREVIOUS_PAIR_INDEX, 1),
    TemporalSlice.CURRENT: _build(TemporalSlice.CURRENT, CURRENT_PAIR_INDEX, 0),
}


def slice_spec(name: TemporalSlice | str) -> SliceSpec:
    return SLICE_SPECS[TemporalSlice(name)]


def verify_slice_arithmetic() -> dict[str, object]:
    """Assert the derived positions equal the authority's frozen literals."""
    previous = SLICE_SPECS[TemporalSlice.PREVIOUS]
    current = SLICE_SPECS[TemporalSlice.CURRENT]
    expected = {
        "14 * 347": (_pair_start(14), 4858),
        "15 * 347": (_pair_start(15), 5205),
        "16 * 347": (_pair_start(16), 5552),
        "PREVIOUS.start": (previous.start, 4858),
        "PREVIOUS.stop": (previous.stop_exclusive, 5194),
        "CURRENT.start": (current.start, 5205),
        "CURRENT.stop": (current.stop_exclusive, 5541),
        "PREVIOUS excluded action start": (previous.excluded_action_start, 5194),
        "PREVIOUS excluded action end": (
            previous.excluded_action_stop_exclusive - 1,
            5204,
        ),
        "CURRENT excluded action start": (current.excluded_action_start, 5541),
        "CURRENT excluded action end": (
            current.excluded_action_stop_exclusive - 1,
            5551,
        ),
        "sequence length": (SEQUENCE_LENGTH, 5552),
    }
    drift = {
        name: {"derived": derived, "authority": frozen}
        for name, (derived, frozen) in expected.items()
        if derived != frozen
    }
    if drift:
        raise ExperimentIIIError(
            "TOKEN_SPAN_MISMATCH",
            f"derived token arithmetic disagrees with the authority: {drift}",
        )
    if set(previous.python_slice.indices(SEQUENCE_LENGTH)[:2]) & set(
        range(current.excluded_action_start, SEQUENCE_LENGTH)
    ):
        raise ExperimentIIIError(
            "TOKEN_ACTION_CONTAMINATION", "PREVIOUS overlaps an action range"
        )
    selected = set(visual_positions(PREVIOUS_PAIR_INDEX)) | set(
        visual_positions(CURRENT_PAIR_INDEX)
    )
    every_action = {
        position
        for pair in range(CONTEXT_PAIRS)
        for position in action_positions(pair)
    }
    if selected & every_action:
        raise ExperimentIIIError(
            "TOKEN_ACTION_CONTAMINATION",
            "selected visual positions intersect an action position",
        )
    return {
        "sequence_length": SEQUENCE_LENGTH,
        "tokens_per_pair": TOKENS_PER_PAIR,
        "PREVIOUS": previous.as_dict(),
        "CURRENT": current.as_dict(),
        "selected_visual_disjoint_from_actions": True,
    }
