"""Focused FrameTokenMap-only selection tests for Phase 4 Wave 1."""

from __future__ import annotations

import copy
import gc
import unittest

import torch

from mineocclude.activations.pool import (
    MEAN_POOLING_IDENTITY,
    PooledVisualActivation,
    VisualPoolingError,
    VisualPoolingErrorCode,
    VisualSelectionErrorCode,
    VisualTokenSelection,
    VisualTokenSelectionError,
    mean_pool_visual_tokens,
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


class VisualMeanPoolingTests(unittest.TestCase):
    def _selection(self, *, pair_index=1, count=3):
        frame_token_map = _token_map(count=count)
        selection = select_visual_token_positions(
            frame_token_map,
            trajectory_id=TRAJECTORY_ID,
            model_frame_idx=100 + pair_index,
            hooked_sequence_length=frame_token_map.sequence_length,
        )
        return frame_token_map, selection

    def _pool(self, activation, selection):
        return mean_pool_visual_tokens(
            activation=activation,
            selection=selection,
            layer_idx=7,
            hook_site="decoder_layer_output_residual_stream",
        )

    def test_known_visual_mean_matches_independent_explicit_mean(self):
        frame_token_map, selection = self._selection()
        activation = torch.zeros(
            (1, frame_token_map.sequence_length, 4),
            dtype=torch.float16,
            requires_grad=True,
        )
        with torch.no_grad():
            values = torch.arange(336, dtype=torch.float16).unsqueeze(1)
            activation[0, list(selection.positions), :] = values
        original = activation.detach().clone()

        result = self._pool(activation, selection)
        direct = (
            activation.detach()[0, list(selection.positions), :]
            .to(torch.float32)
            .mean(dim=0)
        )

        self.assertIsInstance(result, PooledVisualActivation)
        self.assertTrue(torch.equal(result.vector, direct))
        self.assertTrue(torch.equal(activation.detach(), original))
        self.assertEqual(result.vector.tolist(), [167.5] * 4)
        self.assertEqual(result.vector.dtype, torch.float32)
        self.assertEqual(result.vector.device.type, "cpu")
        self.assertTrue(result.vector.is_contiguous())
        self.assertFalse(result.vector.requires_grad)
        self.assertIsNone(result.vector.grad_fn)
        self.assertEqual(
            result.key,
            (
                TRAJECTORY_ID,
                101,
                7,
                "decoder_layer_output_residual_stream",
            ),
        )
        self.assertEqual(result.hidden_size, 4)
        self.assertEqual(result.source_batch_size, 1)
        self.assertEqual(
            result.source_sequence_length,
            frame_token_map.sequence_length,
        )
        self.assertEqual(result.selected_visual_token_count, 336)
        self.assertEqual(
            result.pooling_operation_identity,
            MEAN_POOLING_IDENTITY,
        )
        self.assertEqual(result.source_dtype, "torch.float16")
        self.assertEqual(result.source_device, "cpu")
        self.assertEqual(result.returned_dtype, "torch.float32")
        self.assertEqual(result.returned_device, "cpu")
        self.assertNotIn("activation", result.__dict__)
        self.assertNotIn("selection", result.__dict__)

    def test_action_values_nonfinite_values_and_mutations_are_excluded(self):
        frame_token_map, selection = self._selection()
        span = frame_token_map.spans[1]
        baseline = torch.ones((1, frame_token_map.sequence_length, 3))
        changed = baseline.clone()
        changed[0, list(span.action_positions), 0] = 60_000
        changed[0, list(span.action_positions), 1] = -60_000
        changed[0, span.action_positions[0], 2] = torch.nan
        changed[0, span.action_positions[1], 2] = torch.inf
        changed[0, span.action_positions[2], 2] = -torch.inf

        first = self._pool(baseline, selection)
        second = self._pool(changed, selection)

        self.assertTrue(torch.equal(first.vector, second.vector))
        self.assertTrue(torch.equal(second.vector, torch.ones(3)))

    def test_visual_sensitivity_is_delta_divided_by_336(self):
        frame_token_map, selection = self._selection()
        baseline = torch.zeros((1, frame_token_map.sequence_length, 2))
        changed = baseline.clone()
        changed[0, selection.positions[10], 1] = 336.0

        first = self._pool(baseline, selection)
        second = self._pool(changed, selection)

        self.assertEqual(float(second.vector[1] - first.vector[1]), 1.0)
        self.assertEqual(float(second.vector[0]), 0.0)

    def test_neighbor_and_pair_boundary_values_are_excluded(self):
        frame_token_map, selection = self._selection()
        target = frame_token_map.spans[1]
        baseline = torch.full((1, frame_token_map.sequence_length, 2), 4.0)
        changed = baseline.clone()
        excluded = (
            frame_token_map.spans[0].visual_positions
            + frame_token_map.spans[0].action_positions
            + frame_token_map.spans[2].visual_positions
            + frame_token_map.spans[2].action_positions
            + (target.visual_positions[0] - 1, target.visual_positions[-1] + 1)
        )
        changed[0, list(set(excluded)), :] = -50_000.0

        self.assertTrue(
            torch.equal(
                self._pool(baseline, selection).vector,
                self._pool(changed, selection).vector,
            )
        )

    def test_explicit_positions_are_authoritative_not_an_arithmetic_slice(self):
        positions = tuple(range(1, 337))
        selection = VisualTokenSelection(
            trajectory_id=TRAJECTORY_ID,
            model_frame_idx=900,
            positions=positions,
            sequence_length=400,
        )
        activation = torch.zeros((1, 400, 1))
        activation[0, 0, 0] = 100_000.0
        activation[0, list(positions), 0] = torch.arange(
            336,
            dtype=torch.float32,
        )

        result = self._pool(activation, selection)
        direct = activation[0, list(positions), :].float().mean(dim=0)

        self.assertTrue(torch.equal(result.vector, direct))
        self.assertEqual(float(result.vector[0]), 167.5)

    def test_selected_nonfinite_values_reject_but_unselected_do_not(self):
        frame_token_map, selection = self._selection()
        for value in (torch.nan, torch.inf, -torch.inf):
            with self.subTest(value=value):
                activation = torch.zeros(
                    (1, frame_token_map.sequence_length, 2)
                )
                activation[0, 0, 0] = value
                self.assertTrue(
                    torch.equal(
                        self._pool(activation, selection).vector,
                        torch.zeros(2),
                    )
                )
                activation[0, selection.positions[0], 0] = value
                with self.assertRaises(VisualPoolingError) as caught:
                    self._pool(activation, selection)
                self.assertIs(
                    caught.exception.code,
                    VisualPoolingErrorCode.NONFINITE_SELECTED_VALUE,
                )

    def test_result_owns_storage_independently_in_both_directions(self):
        frame_token_map, selection = self._selection()
        source = torch.arange(
            frame_token_map.sequence_length * 2,
            dtype=torch.float32,
        ).reshape(1, frame_token_map.sequence_length, 2)
        result = self._pool(source, selection)
        saved = result.vector.clone()
        source_before_result_mutation = source.clone()

        source.add_(10_000)
        self.assertTrue(torch.equal(result.vector, saved))
        result.vector.add_(1)
        self.assertTrue(torch.equal(source, source_before_result_mutation + 10_000))
        del source
        gc.collect()
        self.assertTrue(torch.equal(result.vector, saved + 1))

    def test_invalid_activations_fail_with_project_owned_codes(self):
        _, selection = self._selection()
        cases = (
            ("not-a-tensor", VisualPoolingErrorCode.INVALID_ACTIVATION),
            (torch.zeros((347, 2)), VisualPoolingErrorCode.INVALID_SHAPE),
            (torch.zeros((1, 1, 347, 2)), VisualPoolingErrorCode.INVALID_SHAPE),
            (torch.zeros((0, 1041, 2)), VisualPoolingErrorCode.INVALID_BATCH_SIZE),
            (torch.zeros((2, 1041, 2)), VisualPoolingErrorCode.INVALID_BATCH_SIZE),
            (torch.zeros((1, 0, 2)), VisualPoolingErrorCode.INVALID_SHAPE),
            (torch.zeros((1, 1041, 0)), VisualPoolingErrorCode.INVALID_SHAPE),
            (torch.zeros((1, 1041, 2), dtype=torch.int64), VisualPoolingErrorCode.INVALID_DTYPE),
            (torch.zeros((1, 1041, 2), dtype=torch.bool), VisualPoolingErrorCode.INVALID_DTYPE),
        )
        for activation, expected in cases:
            with self.subTest(expected=expected.value):
                with self.assertRaises(VisualPoolingError) as caught:
                    self._pool(activation, selection)
                self.assertIs(caught.exception.code, expected)

    def test_invalid_selection_layer_and_hook_fail_closed(self):
        frame_token_map, selection = self._selection()
        activation = torch.zeros((1, frame_token_map.sequence_length, 2))
        cases = (
            ("positions", selection.positions[:-1]),
            (
                "positions",
                selection.positions[:-1] + (selection.positions[-2],),
            ),
            ("positions", tuple(reversed(selection.positions))),
            ("positions", (-1,) + selection.positions[1:]),
            (
                "positions",
                selection.positions[:-1] + (selection.sequence_length,),
            ),
        )
        for field, value in cases:
            with self.subTest(value=str(value[:2])):
                malformed = copy.copy(selection)
                object.__setattr__(malformed, field, value)
                with self.assertRaises(VisualPoolingError) as caught:
                    self._pool(activation, malformed)
                self.assertIs(
                    caught.exception.code,
                    VisualPoolingErrorCode.INVALID_SELECTION,
                )

        wrong_length = copy.copy(selection)
        object.__setattr__(
            wrong_length,
            "sequence_length",
            selection.sequence_length + 1,
        )
        with self.assertRaises(VisualPoolingError) as caught:
            self._pool(activation, wrong_length)
        self.assertIn(
            caught.exception.code,
            (
                VisualPoolingErrorCode.INVALID_SELECTION,
                VisualPoolingErrorCode.SEQUENCE_LENGTH_MISMATCH,
            ),
        )
        with self.assertRaises(VisualPoolingError):
            mean_pool_visual_tokens(
                activation=activation,
                selection=object(),
                layer_idx=0,
                hook_site="site",
            )
        for layer_idx in (-1, True, "0"):
            with self.assertRaises(VisualPoolingError) as caught:
                mean_pool_visual_tokens(
                    activation=activation,
                    selection=selection,
                    layer_idx=layer_idx,
                    hook_site="site",
                )
            self.assertIs(
                caught.exception.code,
                VisualPoolingErrorCode.INVALID_LAYER_INDEX,
            )
        for hook_site in ("", "   ", None):
            with self.assertRaises(VisualPoolingError) as caught:
                mean_pool_visual_tokens(
                    activation=activation,
                    selection=selection,
                    layer_idx=0,
                    hook_site=hook_site,
                )
            self.assertIs(
                caught.exception.code,
                VisualPoolingErrorCode.INVALID_HOOK_SITE,
            )


if __name__ == "__main__":
    unittest.main()
