"""Direct tensor proofs for the scoped residual injector (Steps 8.1-8.4).

These tests use real tensors and a fake 20-layer decoder. They never load model
weights and never inspect a rollout outcome.
"""

from __future__ import annotations

import unittest

import torch

from mineocclude.activations.hooks import (
    CONCEPTUAL_HOOK_SITE,
    EXPECTED_DECODER_LAYER_COUNT,
    discover_decoder_hook_site,
)
from mineocclude.contracts.activation import VISUAL_TOKENS_PER_FRAME
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.intervention.inject import (
    MAX_RELATIVE_ACTIVATION_NORM,
    InjectionError,
    InjectionErrorCode,
    InjectionPlan,
    ScopedInjectionHook,
    audit_cap,
    audit_pooled_change_identity,
    build_injection_plan,
    changed_positions,
    enforce_cap,
    relative_perturbation_norm,
    validate_request,
)
from mineocclude.models.mineworld_adapter import (
    FrameIdentity,
    FrameTokenMap,
    FrameTokenSpan,
)

HIDDEN = 2048
ACTION_TOKENS = 11
PAIR = VISUAL_TOKENS_PER_FRAME + ACTION_TOKENS


class _Handle:
    def __init__(self, layer, key):
        self._layer = layer
        self._key = key
        self.remove_calls = 0

    def remove(self):
        self.remove_calls += 1
        self._layer.hooks.pop(self._key, None)


class _Layer:
    """A minimal module that honours forward-hook return-value replacement."""

    def __init__(self):
        self.hooks = {}
        self._next = 0
        self.handles = []

    def register_forward_hook(self, callback):
        key = self._next
        self._next += 1
        self.hooks[key] = callback
        handle = _Handle(self, key)
        self.handles.append(handle)
        return handle

    def forward(self, output):
        result = output
        for callback in tuple(self.hooks.values()):
            replacement = callback(self, (), result)
            if replacement is not None:
                result = replacement
        return result


class _Model:
    """A fake model exposing exactly twenty indexed decoder layers."""

    def __init__(self, layers):
        self._entries = [("", object())] + [
            (f"transformer.model.layers.{index}", layer)
            for index, layer in enumerate(layers)
        ]

    def named_modules(self):
        return iter(self._entries)


def _discovery():
    modules = tuple(_Layer() for _ in range(EXPECTED_DECODER_LAYER_COUNT))
    return discover_decoder_hook_site(_Model(modules)), modules


def _frame_token_map(frame_count=3, trajectory_id="layout_01_ep12602"):
    spans = []
    for index in range(frame_count):
        base = index * PAIR
        spans.append(
            FrameTokenSpan(
                identity=FrameIdentity(
                    schema_version=SCHEMA_VERSION,
                    trajectory_id=trajectory_id,
                    model_frame_idx=index,
                ),
                pair_index=index,
                visual_positions=tuple(
                    range(base, base + VISUAL_TOKENS_PER_FRAME)
                ),
                action_positions=tuple(
                    range(base + VISUAL_TOKENS_PER_FRAME, base + PAIR)
                ),
                pair_start=base,
                pair_end_exclusive=base + PAIR,
            )
        )
    return FrameTokenMap(
        schema_version=SCHEMA_VERSION,
        trajectory_id=trajectory_id,
        sequence_length=frame_count * PAIR,
        spans=tuple(spans),
    )


def _plan(alpha=0.5, frame_count=3, layer_idx=12, timestep_idx=0):
    token_map = _frame_token_map(frame_count)
    return build_injection_plan(
        token_map,
        trajectory_id=token_map.trajectory_id,
        layer_idx=layer_idx,
        timestep_idx=timestep_idx,
        hook_site=CONCEPTUAL_HOOK_SITE,
        alpha=alpha,
        hooked_sequence_length=token_map.sequence_length,
    )


def _direction(seed=7):
    generator = torch.Generator().manual_seed(seed)
    vector = torch.randn(HIDDEN, generator=generator, dtype=torch.float64)
    return vector / vector.norm()


def _residual(sequence_length, *, dtype=torch.float32, seed=3):
    generator = torch.Generator().manual_seed(seed)
    return torch.randn(
        1, sequence_length, HIDDEN, generator=generator, dtype=dtype
    )


class ScopedInjectionMaskTests(unittest.TestCase):
    """Step 8.2 — the nonzero difference mask equals exactly the intended set."""

    def test_only_final_context_frame_visual_positions_change(self):
        plan = _plan(alpha=0.25)
        discovery, modules = _discovery()
        before = _residual(plan.sequence_length)
        direction = _direction()

        with ScopedInjectionHook(discovery, plan, direction) as hook:
            after = modules[plan.layer_idx].forward(before)
            audit = hook.audit()

        self.assertEqual(changed_positions(before, after), plan.positions)
        self.assertEqual(len(plan.positions), VISUAL_TOKENS_PER_FRAME)
        self.assertTrue(audit["applied"])

    def test_action_and_earlier_frame_positions_are_untouched(self):
        plan = _plan(alpha=0.25, frame_count=3)
        discovery, modules = _discovery()
        before = _residual(plan.sequence_length)
        selected = set(plan.positions)

        with ScopedInjectionHook(discovery, plan, _direction()):
            after = modules[plan.layer_idx].forward(before)

        untouched = [
            index for index in range(plan.sequence_length) if index not in selected
        ]
        self.assertTrue(
            torch.equal(before[:, untouched, :], after[:, untouched, :])
        )
        # The final context frame is frame 2; frames 0 and 1 must be identical.
        self.assertTrue(torch.equal(before[:, : 2 * PAIR, :], after[:, : 2 * PAIR, :]))

    def test_other_layers_are_never_modified(self):
        plan = _plan(alpha=0.25, layer_idx=12)
        discovery, modules = _discovery()
        before = _residual(plan.sequence_length)

        with ScopedInjectionHook(discovery, plan, _direction()):
            other = modules[3].forward(before)

        self.assertTrue(torch.equal(before, other))

    def test_other_timesteps_are_never_modified(self):
        plan = _plan(alpha=0.25, timestep_idx=1)
        discovery, modules = _discovery()
        before = _residual(plan.sequence_length)

        with ScopedInjectionHook(discovery, plan, _direction()) as hook:
            first = modules[plan.layer_idx].forward(before)
            second = modules[plan.layer_idx].forward(before)
            audit = hook.audit()

        self.assertTrue(torch.equal(before, first))
        self.assertEqual(changed_positions(before, second), plan.positions)
        self.assertEqual(audit["applied_call_index"], 1)


class AlphaIdentityTests(unittest.TestCase):
    """Step 8.4 — alpha zero, sign reversal, and the pooled-change identity."""

    def test_alpha_zero_matches_the_unmodified_path_exactly(self):
        plan = _plan(alpha=0.0)
        discovery, modules = _discovery()
        before = _residual(plan.sequence_length)

        with ScopedInjectionHook(discovery, plan, _direction()):
            after = modules[plan.layer_idx].forward(before)

        self.assertTrue(torch.equal(before, after))
        self.assertEqual(changed_positions(before, after), ())

    def test_positive_and_negative_alpha_reverse_the_difference(self):
        direction = _direction()
        before = _residual(_plan().sequence_length)

        deltas = {}
        for alpha in (0.3, -0.3):
            plan = _plan(alpha=alpha)
            discovery, modules = _discovery()
            with ScopedInjectionHook(discovery, plan, direction):
                after = modules[plan.layer_idx].forward(before)
            deltas[alpha] = (after - before)[0, plan.positions[0], :]

        self.assertTrue(
            torch.allclose(deltas[0.3], -deltas[-0.3], rtol=1e-5, atol=1e-6)
        )

    def test_pooled_change_equals_alpha_times_direction(self):
        alpha = 0.4
        plan = _plan(alpha=alpha)
        discovery, modules = _discovery()
        before = _residual(plan.sequence_length, dtype=torch.float32)
        direction = _direction()

        with ScopedInjectionHook(discovery, plan, direction):
            after = modules[plan.layer_idx].forward(before)

        report = audit_pooled_change_identity(
            before, after, plan.positions, direction, alpha
        )
        self.assertTrue(report["identity_holds"], report)
        self.assertLess(report["max_absolute_difference"], 1e-3)

    def test_zero_alpha_pooled_change_is_zero(self):
        plan = _plan(alpha=0.0)
        discovery, modules = _discovery()
        before = _residual(plan.sequence_length)
        direction = _direction()

        with ScopedInjectionHook(discovery, plan, direction):
            after = modules[plan.layer_idx].forward(before)

        report = audit_pooled_change_identity(
            before, after, plan.positions, direction, 0.0
        )
        self.assertTrue(report["identity_holds"])
        self.assertEqual(report["observed_l2_norm"], 0.0)


class CapAuditTests(unittest.TestCase):
    """Step 8.4 — the 0.25 relative-norm cap is audited and enforced."""

    def test_relative_norm_uses_the_typical_activation_norm(self):
        self.assertAlmostEqual(
            relative_perturbation_norm(2.0, 10.0), 0.2, places=12
        )

    def test_within_cap_is_reported_and_accepted(self):
        report = enforce_cap(2.0, 10.0)
        self.assertTrue(report["within_cap"])
        self.assertAlmostEqual(report["relative_perturbation_norm"], 0.2)
        self.assertEqual(report["cap"], MAX_RELATIVE_ACTIVATION_NORM)

    def test_exceeding_the_cap_raises_instead_of_silently_rescaling(self):
        audit = audit_cap(5.0, 10.0)
        self.assertFalse(audit["within_cap"])
        with self.assertRaises(InjectionError) as caught:
            enforce_cap(5.0, 10.0)
        self.assertIs(caught.exception.code, InjectionErrorCode.CAP_EXCEEDED)

    def test_non_positive_typical_norm_is_rejected(self):
        with self.assertRaises(InjectionError):
            relative_perturbation_norm(1.0, 0.0)


class StructureAndCleanupTests(unittest.TestCase):
    """Step 8.3 — shape, dtype, device, container, and hook lifetime."""

    def test_dtype_and_shape_are_preserved_for_float16(self):
        plan = _plan(alpha=0.1)
        discovery, modules = _discovery()
        before = _residual(plan.sequence_length, dtype=torch.float16)

        with ScopedInjectionHook(discovery, plan, _direction()):
            after = modules[plan.layer_idx].forward(before)

        self.assertEqual(after.dtype, torch.float16)
        self.assertEqual(after.shape, before.shape)
        self.assertEqual(after.device, before.device)

    def test_tuple_output_structure_is_returned_unchanged(self):
        plan = _plan(alpha=0.2)
        discovery, modules = _discovery()
        before = _residual(plan.sequence_length)
        payload = (before, "auxiliary")

        with ScopedInjectionHook(discovery, plan, _direction()):
            after = modules[plan.layer_idx].forward(payload)

        self.assertIsInstance(after, tuple)
        self.assertEqual(len(after), 2)
        self.assertEqual(after[1], "auxiliary")
        self.assertEqual(changed_positions(before, after[0]), plan.positions)

    def test_structured_output_field_is_returned_unchanged(self):
        plan = _plan(alpha=0.2)
        discovery, modules = _discovery()
        before = _residual(plan.sequence_length)
        payload = {"last_hidden_state": before}

        with ScopedInjectionHook(discovery, plan, _direction()):
            after = modules[plan.layer_idx].forward(payload)

        self.assertIsInstance(after, dict)
        self.assertEqual(
            changed_positions(before, after["last_hidden_state"]), plan.positions
        )

    def test_hook_is_removed_after_success(self):
        plan = _plan(alpha=0.2)
        discovery, modules = _discovery()
        layer = modules[plan.layer_idx]

        with ScopedInjectionHook(discovery, plan, _direction()) as hook:
            self.assertEqual(len(layer.hooks), 1)
            layer.forward(_residual(plan.sequence_length))

        self.assertEqual(len(layer.hooks), 0)
        self.assertTrue(hook.closed)

    def test_hook_is_removed_after_failure(self):
        plan = _plan(alpha=0.2)
        discovery, modules = _discovery()
        layer = modules[plan.layer_idx]

        with self.assertRaises(RuntimeError):
            with ScopedInjectionHook(discovery, plan, _direction()):
                raise RuntimeError("controlled rollout failure")

        self.assertEqual(len(layer.hooks), 0)

    def test_sequence_length_mismatch_is_refused(self):
        plan = _plan(alpha=0.2)
        discovery, modules = _discovery()
        wrong = _residual(plan.sequence_length + PAIR)

        with self.assertRaises(InjectionError) as caught:
            with ScopedInjectionHook(discovery, plan, _direction()):
                modules[plan.layer_idx].forward(wrong)
        self.assertIs(caught.exception.code, InjectionErrorCode.SHAPE_MISMATCH)

    def test_multi_item_batch_is_refused(self):
        plan = _plan(alpha=0.2)
        discovery, modules = _discovery()
        batched = torch.randn(2, plan.sequence_length, HIDDEN)

        with self.assertRaises(InjectionError) as caught:
            with ScopedInjectionHook(discovery, plan, _direction()):
                modules[plan.layer_idx].forward(batched)
        self.assertIs(caught.exception.code, InjectionErrorCode.BATCH_UNSUPPORTED)

    def test_wrong_direction_dimension_is_refused(self):
        plan = _plan(alpha=0.2)
        discovery, modules = _discovery()
        with self.assertRaises(InjectionError) as caught:
            with ScopedInjectionHook(discovery, plan, torch.zeros(16)):
                modules[plan.layer_idx].forward(_residual(plan.sequence_length))
        self.assertIs(caught.exception.code, InjectionErrorCode.INVALID_DIRECTION)

    def test_hook_is_single_use(self):
        plan = _plan(alpha=0.2)
        discovery, _ = _discovery()
        hook = ScopedInjectionHook(discovery, plan, _direction())
        with hook:
            pass
        with self.assertRaises(InjectionError) as caught:
            with hook:
                pass
        self.assertIs(caught.exception.code, InjectionErrorCode.MANAGER_STATE)


class InjectionPlanTests(unittest.TestCase):
    """The plan itself refuses an out-of-scope site before any tensor moves."""

    def test_plan_selects_the_final_context_frame_by_default(self):
        plan = _plan(alpha=0.1, frame_count=4)
        expected_base = 3 * PAIR
        self.assertEqual(plan.model_frame_idx, 3)
        self.assertEqual(plan.positions[0], expected_base)
        self.assertEqual(
            plan.positions[-1], expected_base + VISUAL_TOKENS_PER_FRAME - 1
        )

    def test_plan_rejects_a_wrong_position_count(self):
        with self.assertRaises(InjectionError) as caught:
            InjectionPlan(
                trajectory_id="t",
                model_frame_idx=0,
                layer_idx=1,
                timestep_idx=0,
                hook_site=CONCEPTUAL_HOOK_SITE,
                positions=(0, 1, 2),
                sequence_length=PAIR,
                alpha=0.1,
            )
        self.assertIs(caught.exception.code, InjectionErrorCode.INVALID_SITE)

    def test_plan_rejects_an_out_of_range_layer(self):
        with self.assertRaises(InjectionError):
            _plan(alpha=0.1, layer_idx=EXPECTED_DECODER_LAYER_COUNT)

    def test_plan_rejects_a_non_finite_alpha(self):
        with self.assertRaises(InjectionError):
            _plan(alpha=float("nan"))


class RequestValidationTests(unittest.TestCase):
    """Step 8.1 — the request is judged before held-out events are loaded."""

    def test_non_mapping_request_is_refused(self):
        with self.assertRaises(InjectionError):
            validate_request(["not", "a", "mapping"])

    def test_incomplete_request_is_rejected_with_reasons(self):
        report = validate_request({"schema_version": SCHEMA_VERSION})
        self.assertFalse(report.accepted)
        self.assertTrue(report.rejections)
        document = report.to_document()
        self.assertEqual(document["status"], "REJECTED")
        self.assertFalse(document["heldout_outcomes_inspected"])
        self.assertTrue(document["validated_before_loading_events"])

    def test_request_without_heldout_events_is_rejected(self):
        report = validate_request(
            {
                "schema_version": SCHEMA_VERSION,
                "intervention_location": {
                    "layer_idx": 12,
                    "timestep_idx": 0,
                    "hook_site": CONCEPTUAL_HOOK_SITE,
                },
                "heldout_events": [],
                "selection_policy": {
                    "used_heldout_outcomes_to_select_direction": False
                },
            }
        )
        self.assertFalse(report.accepted)
        codes = {item["code"] for item in report.rejections}
        self.assertIn(InjectionErrorCode.HELDOUT_SEPARATION.value, codes)

    def test_request_selected_on_heldout_outcomes_is_rejected(self):
        report = validate_request(
            {
                "schema_version": SCHEMA_VERSION,
                "intervention_location": {
                    "layer_idx": 12,
                    "timestep_idx": 0,
                    "hook_site": CONCEPTUAL_HOOK_SITE,
                },
                "heldout_events": [{"event_id": "e1"}],
                "selection_policy": {
                    "used_heldout_outcomes_to_select_direction": True
                },
            }
        )
        self.assertFalse(report.accepted)
        codes = {item["code"] for item in report.rejections}
        self.assertIn(InjectionErrorCode.HELDOUT_SEPARATION.value, codes)

    def test_cap_reduced_doses_are_reported_not_relabelled(self):
        report = validate_request(
            {
                "schema_version": SCHEMA_VERSION,
                "intervention_location": {
                    "layer_idx": 12,
                    "timestep_idx": 0,
                    "hook_site": CONCEPTUAL_HOOK_SITE,
                },
                "alpha_table": [
                    {"dose_id": "d1", "cap_reduced": True},
                    {"dose_id": "d2", "cap_reduced": False},
                ],
                "heldout_events": [{"event_id": "e1"}],
                "selection_policy": {
                    "used_heldout_outcomes_to_select_direction": False
                },
            }
        )
        self.assertEqual(report.cap_reduced_dose_ids, ("d1",))
        self.assertFalse(report.to_document()["cap_reduction_relabelled"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
