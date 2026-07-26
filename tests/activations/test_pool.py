"""Focused FrameTokenMap-only selection tests for Phase 4 Wave 1."""

from __future__ import annotations

import copy
import unittest

from mineocclude.activations.pool import (
    VisualSelectionErrorCode,
    VisualTokenSelectionError,
    select_visual_token_positions,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models.mineworld_adapter import (
    FrameIdentity,
    FrameTokenMap,
    FrameTokenSpan,
)

TRAJECTORY_ID = "phase4-wave1-trajectory"


def _token_map(count=16, *, first_model_frame_idx=100):
    spans = []
    identities = tuple(
        FrameIdentity(
            SCHEMA_VERSION,
            TRAJECTORY_ID,
            first_model_frame_idx + index,
        )
        for index in range(count)
    )
    for pair_index, identity in enumerate(identities):
        pair_start = pair_index * 347
        spans.append(
            FrameTokenSpan(
                identity=identity,
                pair_index=pair_index,
                visual_positions=tuple(range(pair_start, pair_start + 336)),
                action_positions=tuple(
                    range(pair_start + 336, pair_start + 347)
                ),
                accepted_pair_index=pair_index,
                pair_start=pair_start,
                pair_end_exclusive=pair_start + 347,
                causal_predecessor=(
                    identities[pair_index - 1] if pair_index else None
                ),
                causal_successor=(
                    identities[pair_index + 1]
                    if pair_index + 1 < count
                    else None
                ),
            )
        )
    return FrameTokenMap(
        schema_version=SCHEMA_VERSION,
        trajectory_id=TRAJECTORY_ID,
        sequence_length=count * 347,
        spans=tuple(spans),
    )


def _corrupt_map(frame_token_map, *, spans=None, sequence_length=None):
    corrupted = copy.copy(frame_token_map)
    if spans is not None:
        object.__setattr__(corrupted, "spans", tuple(spans))
    if sequence_length is not None:
        object.__setattr__(corrupted, "sequence_length", sequence_length)
    return corrupted


class VisualTokenSelectionTests(unittest.TestCase):
    def test_first_middle_final_and_context_boundary_frames(self):
        frame_token_map = _token_map()
        for pair_index in (0, 7, 15):
            model_frame_idx = 100 + pair_index
            with self.subTest(model_frame_idx=model_frame_idx):
                selection = select_visual_token_positions(
                    frame_token_map,
                    trajectory_id=TRAJECTORY_ID,
                    model_frame_idx=model_frame_idx,
                    hooked_sequence_length=frame_token_map.sequence_length,
                )
                expected_start = pair_index * 347
                self.assertEqual(selection.trajectory_id, TRAJECTORY_ID)
                self.assertEqual(selection.model_frame_idx, model_frame_idx)
                self.assertEqual(len(selection.positions), 336)
                self.assertEqual(
                    selection.positions,
                    tuple(range(expected_start, expected_start + 336)),
                )

    def test_selection_excludes_actions_and_neighboring_visual_positions(self):
        frame_token_map = _token_map(count=3)
        selection = select_visual_token_positions(
            frame_token_map,
            trajectory_id=TRAJECTORY_ID,
            model_frame_idx=101,
            hooked_sequence_length=frame_token_map.sequence_length,
        )
        action_positions = {
            position
            for span in frame_token_map.spans
            for position in span.action_positions
        }
        neighboring_visual = {
            position
            for span in (frame_token_map.spans[0], frame_token_map.spans[2])
            for position in span.visual_positions
        }

        self.assertTrue(set(selection.positions).isdisjoint(action_positions))
        self.assertTrue(set(selection.positions).isdisjoint(neighboring_visual))

    def test_whole_pair_block_reassignment_rejects(self):
        for swap_bounds in (False, True):
            with self.subTest(swap_bounds=swap_bounds):
                frame_token_map = _token_map(count=2)
                first = copy.copy(frame_token_map.spans[0])
                second = copy.copy(frame_token_map.spans[1])
                first_visual = first.visual_positions
                first_actions = first.action_positions
                object.__setattr__(
                    first,
                    "visual_positions",
                    second.visual_positions,
                )
                object.__setattr__(
                    first,
                    "action_positions",
                    second.action_positions,
                )
                object.__setattr__(
                    second,
                    "visual_positions",
                    first_visual,
                )
                object.__setattr__(
                    second,
                    "action_positions",
                    first_actions,
                )
                if swap_bounds:
                    object.__setattr__(first, "pair_start", 347)
                    object.__setattr__(first, "pair_end_exclusive", 694)
                    object.__setattr__(second, "pair_start", 0)
                    object.__setattr__(second, "pair_end_exclusive", 347)
                corrupted = _corrupt_map(
                    frame_token_map,
                    spans=(first, second),
                )

                with self.assertRaises(VisualTokenSelectionError) as caught:
                    select_visual_token_positions(
                        corrupted,
                        trajectory_id=TRAJECTORY_ID,
                        model_frame_idx=100,
                        hooked_sequence_length=corrupted.sequence_length,
                    )

                self.assertIs(
                    caught.exception.code,
                    VisualSelectionErrorCode.MALFORMED_MAP,
                )

    def test_pair_bounds_must_match_declared_pair_index(self):
        frame_token_map = _token_map(count=2)
        cases = (
            ("pair_start", 1),
            ("pair_end_exclusive", 346),
        )
        for field, value in cases:
            with self.subTest(field=field):
                first = copy.copy(frame_token_map.spans[0])
                object.__setattr__(first, field, value)
                corrupted = _corrupt_map(
                    frame_token_map,
                    spans=(first, frame_token_map.spans[1]),
                )

                with self.assertRaises(VisualTokenSelectionError) as caught:
                    select_visual_token_positions(
                        corrupted,
                        trajectory_id=TRAJECTORY_ID,
                        model_frame_idx=100,
                        hooked_sequence_length=corrupted.sequence_length,
                    )

                self.assertIs(
                    caught.exception.code,
                    VisualSelectionErrorCode.MALFORMED_MAP,
                )

    def test_duplicate_visual_position_rejects(self):
        frame_token_map = _token_map(count=1)
        span = copy.copy(frame_token_map.spans[0])
        positions = list(span.visual_positions)
        positions[-1] = positions[-2]
        object.__setattr__(span, "visual_positions", tuple(positions))
        corrupted = _corrupt_map(frame_token_map, spans=(span,))

        with self.assertRaises(VisualTokenSelectionError) as caught:
            select_visual_token_positions(
                corrupted,
                trajectory_id=TRAJECTORY_ID,
                model_frame_idx=100,
                hooked_sequence_length=corrupted.sequence_length,
            )

        self.assertIs(
            caught.exception.code,
            VisualSelectionErrorCode.DUPLICATE_POSITION,
        )

    def test_fewer_or_more_than_336_visual_positions_reject(self):
        frame_token_map = _token_map(count=1)
        cases = (
            frame_token_map.spans[0].visual_positions[:-1],
            frame_token_map.spans[0].visual_positions + (346,),
        )
        for positions in cases:
            with self.subTest(count=len(positions)):
                span = copy.copy(frame_token_map.spans[0])
                object.__setattr__(span, "visual_positions", positions)
                corrupted = _corrupt_map(frame_token_map, spans=(span,))

                with self.assertRaises(VisualTokenSelectionError) as caught:
                    select_visual_token_positions(
                        corrupted,
                        trajectory_id=TRAJECTORY_ID,
                        model_frame_idx=100,
                        hooked_sequence_length=corrupted.sequence_length,
                    )

                self.assertIs(
                    caught.exception.code,
                    VisualSelectionErrorCode.INVALID_VISUAL_COUNT,
                )

    def test_missing_frame_rejects(self):
        frame_token_map = _token_map(count=2)

        with self.assertRaises(VisualTokenSelectionError) as caught:
            select_visual_token_positions(
                frame_token_map,
                trajectory_id=TRAJECTORY_ID,
                model_frame_idx=999,
                hooked_sequence_length=frame_token_map.sequence_length,
            )

        self.assertIs(
            caught.exception.code,
            VisualSelectionErrorCode.MISSING_FRAME,
        )

    def test_out_of_bounds_position_rejects(self):
        frame_token_map = _token_map(count=1)
        span = copy.copy(frame_token_map.spans[0])
        positions = list(span.visual_positions)
        positions[-1] = frame_token_map.sequence_length
        object.__setattr__(span, "visual_positions", tuple(positions))
        corrupted = _corrupt_map(frame_token_map, spans=(span,))

        with self.assertRaises(VisualTokenSelectionError) as caught:
            select_visual_token_positions(
                corrupted,
                trajectory_id=TRAJECTORY_ID,
                model_frame_idx=100,
                hooked_sequence_length=corrupted.sequence_length,
            )

        self.assertIs(
            caught.exception.code,
            VisualSelectionErrorCode.OUT_OF_BOUNDS,
        )

    def test_ambiguous_frame_identity_rejects(self):
        frame_token_map = _token_map(count=2)
        second = copy.copy(frame_token_map.spans[1])
        object.__setattr__(second, "identity", frame_token_map.spans[0].identity)
        corrupted = _corrupt_map(
            frame_token_map,
            spans=(frame_token_map.spans[0], second),
        )

        with self.assertRaises(VisualTokenSelectionError) as caught:
            select_visual_token_positions(
                corrupted,
                trajectory_id=TRAJECTORY_ID,
                model_frame_idx=100,
                hooked_sequence_length=corrupted.sequence_length,
            )

        self.assertIs(
            caught.exception.code,
            VisualSelectionErrorCode.AMBIGUOUS_FRAME,
        )

    def test_action_visual_overlap_rejects(self):
        frame_token_map = _token_map(count=1)
        span = copy.copy(frame_token_map.spans[0])
        actions = list(span.action_positions)
        actions[0] = span.visual_positions[-1]
        object.__setattr__(span, "action_positions", tuple(actions))
        corrupted = _corrupt_map(frame_token_map, spans=(span,))

        with self.assertRaises(VisualTokenSelectionError) as caught:
            select_visual_token_positions(
                corrupted,
                trajectory_id=TRAJECTORY_ID,
                model_frame_idx=100,
                hooked_sequence_length=corrupted.sequence_length,
            )

        self.assertIs(
            caught.exception.code,
            VisualSelectionErrorCode.ACTION_VISUAL_OVERLAP,
        )

    def test_neighboring_visual_contamination_rejects(self):
        frame_token_map = _token_map(count=2)
        second = copy.copy(frame_token_map.spans[1])
        positions = list(second.visual_positions)
        positions[0] = frame_token_map.spans[0].visual_positions[-1]
        object.__setattr__(second, "visual_positions", tuple(positions))
        corrupted = _corrupt_map(
            frame_token_map,
            spans=(frame_token_map.spans[0], second),
        )

        with self.assertRaises(VisualTokenSelectionError) as caught:
            select_visual_token_positions(
                corrupted,
                trajectory_id=TRAJECTORY_ID,
                model_frame_idx=100,
                hooked_sequence_length=corrupted.sequence_length,
            )

        self.assertIs(
            caught.exception.code,
            VisualSelectionErrorCode.NEIGHBOR_VISUAL_OVERLAP,
        )

    def test_malformed_map_and_sequence_mismatch_reject(self):
        frame_token_map = _token_map(count=1)
        cases = (
            (
                object(),
                347,
                VisualSelectionErrorCode.MALFORMED_MAP,
            ),
            (
                frame_token_map,
                348,
                VisualSelectionErrorCode.SEQUENCE_LENGTH_MISMATCH,
            ),
        )
        for value, length, expected_code in cases:
            with self.subTest(expected_code=expected_code.value):
                with self.assertRaises(VisualTokenSelectionError) as caught:
                    select_visual_token_positions(
                        value,
                        trajectory_id=TRAJECTORY_ID,
                        model_frame_idx=100,
                        hooked_sequence_length=length,
                    )
                self.assertIs(caught.exception.code, expected_code)


if __name__ == "__main__":
    unittest.main()
