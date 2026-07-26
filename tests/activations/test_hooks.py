"""Focused CPU-only tests for Phase 4 Wave 1 hook discovery and lifetime."""

from __future__ import annotations

import unittest

from mineocclude.activations.hooks import (
    CONCEPTUAL_HOOK_SITE,
    EXPECTED_DECODER_LAYER_COUNT,
    HOOK_DISCOVERY_VERSION,
    ActivationHookError,
    HookErrorCode,
    ScopedHookManager,
    discover_decoder_hook_site,
    normalize_hook_output,
)


class _FakeTensor:
    def __init__(self, shape=(1, 24, 8)):
        self.shape = shape


class _FakeHandle:
    def __init__(self, module, identifier, *, failures_before_success=0):
        self._module = module
        self._identifier = identifier
        self._failures_before_success = failures_before_success
        self.remove_calls = 0

    def remove(self):
        self.remove_calls += 1
        if self.remove_calls <= self._failures_before_success:
            raise RuntimeError("controlled remove failure")
        self._module.hooks.pop(self._identifier, None)


class _MalformedHandle:
    def __init__(self, module, identifier):
        self._module = module
        self._identifier = identifier


class _FakeDecoderLayer:
    def __init__(self):
        self.hooks = {}
        self.callback_history = []
        self.handles = []
        self._next_identifier = 0
        self.remove_failures_before_success = 0
        self.registration_error = None
        self.return_malformed_handle = False

    def register_forward_hook(self, callback):
        if self.registration_error is not None:
            raise self.registration_error
        identifier = self._next_identifier
        self._next_identifier += 1
        self.hooks[identifier] = callback
        self.callback_history.append(callback)
        if self.return_malformed_handle:
            handle = _MalformedHandle(self, identifier)
        else:
            handle = _FakeHandle(
                self,
                identifier,
                failures_before_success=self.remove_failures_before_success,
            )
        self.handles.append(handle)
        return handle

    def emit(self, output):
        for callback in tuple(self.hooks.values()):
            callback(self, (), output)


class _DifferentDecoderLayer(_FakeDecoderLayer):
    pass


class _FakeModel:
    def __init__(self, entries):
        self._entries = tuple(entries)

    def named_modules(self):
        return iter(self._entries)


def _model(
    *,
    indices=None,
    parent="runtime.decoder.blocks",
    reverse=True,
    inconsistent_type_at=None,
):
    if indices is None:
        indices = range(EXPECTED_DECODER_LAYER_COUNT)
    entries = [("", object())]
    layers = {}
    for index in indices:
        cls = (
            _DifferentDecoderLayer
            if index == inconsistent_type_at
            else _FakeDecoderLayer
        )
        layer = cls()
        layers[index] = layer
        entries.append((f"{parent}.{index}", layer))
    if reverse:
        entries = entries[:1] + list(reversed(entries[1:]))
    return _FakeModel(entries), layers


def _discovery():
    model, layers = _model()
    return discover_decoder_hook_site(model), layers


class HookDiscoveryTests(unittest.TestCase):
    def test_exact_twenty_layers_are_discovered_and_sorted(self):
        discovery, layers = _discovery()

        self.assertEqual(
            tuple(layer.layer_idx for layer in discovery.layers),
            tuple(range(20)),
        )
        self.assertEqual(
            tuple(layer.module_name for layer in discovery.layers),
            tuple(f"runtime.decoder.blocks.{index}" for index in range(20)),
        )
        self.assertEqual(
            discovery.module_name_pattern,
            "runtime.decoder.blocks.{layer_idx}",
        )
        self.assertEqual(discovery.conceptual_site, CONCEPTUAL_HOOK_SITE)
        self.assertEqual(discovery.discovery_version, HOOK_DISCOVERY_VERSION)
        self.assertEqual(
            tuple(module for _metadata, module in discovery.iter_runtime_layers()),
            tuple(layers[index] for index in range(20)),
        )

    def test_fewer_or_more_than_twenty_layers_reject(self):
        for count in (19, 21):
            with self.subTest(count=count):
                model, _layers = _model(indices=range(count))

                with self.assertRaises(ActivationHookError) as caught:
                    discover_decoder_hook_site(model)

                self.assertIs(
                    caught.exception.code,
                    HookErrorCode.LAYER_COUNT_MISMATCH,
                )

    def test_duplicate_layer_index_rejects(self):
        model, _layers = _model()
        entries = list(model.named_modules())
        entries.append(entries[-1])

        with self.assertRaises(ActivationHookError) as caught:
            discover_decoder_hook_site(_FakeModel(entries))

        self.assertIs(caught.exception.code, HookErrorCode.DUPLICATE_MODULE_NAME)

    def test_noncontiguous_indices_reject(self):
        model, _layers = _model(indices=tuple(range(19)) + (20,))

        with self.assertRaises(ActivationHookError) as caught:
            discover_decoder_hook_site(model)

        self.assertIs(caught.exception.code, HookErrorCode.INVALID_LAYER_INDICES)

    def test_ambiguous_complete_groups_reject(self):
        first, _first_layers = _model(parent="model.first")
        second, _second_layers = _model(parent="model.second")
        entries = list(first.named_modules()) + list(second.named_modules())[1:]

        with self.assertRaises(ActivationHookError) as caught:
            discover_decoder_hook_site(_FakeModel(entries))

        self.assertIs(caught.exception.code, HookErrorCode.AMBIGUOUS_LAYER_GROUP)

    def test_inconsistent_module_types_reject(self):
        model, _layers = _model(inconsistent_type_at=7)

        with self.assertRaises(ActivationHookError) as caught:
            discover_decoder_hook_site(model)

        self.assertIs(
            caught.exception.code,
            HookErrorCode.INCONSISTENT_MODULE_TYPE,
        )

    def test_direct_tuple_and_structured_outputs_are_explicit(self):
        tensor = _FakeTensor()
        direct = normalize_hook_output(tensor)
        tuple_output = normalize_hook_output((tensor, None))
        structured = normalize_hook_output({"last_hidden_state": tensor})

        self.assertIs(direct.tensor, tensor)
        self.assertEqual(direct.shape, (1, 24, 8))
        self.assertEqual(direct.batch_size, 1)
        self.assertEqual(direct.sequence_length, 24)
        self.assertEqual(direct.hidden_size, 8)
        self.assertEqual(direct.container_kind, "direct_tensor")
        self.assertEqual(tuple_output.container_kind, "tuple")
        self.assertEqual(tuple_output.tuple_index, 0)
        self.assertEqual(structured.container_kind, "structured")
        self.assertEqual(structured.structured_field, "last_hidden_state")

    def test_ambiguous_or_invalid_outputs_reject(self):
        tensor = _FakeTensor()
        cases = (
            (tensor, tensor),
            (None, tensor),
            {"last_hidden_state": tensor, "attention": _FakeTensor()},
            {"unknown": tensor},
            _FakeTensor((24, 8)),
        )

        for output in cases:
            with (
                self.subTest(output_type=type(output).__name__),
                self.assertRaises(ActivationHookError),
            ):
                normalize_hook_output(output)


class ScopedHookManagerTests(unittest.TestCase):
    def test_exact_registration_capture_and_success_cleanup(self):
        discovery, layers = _discovery()
        manager = ScopedHookManager(discovery)

        with manager:
            self.assertEqual(manager.registered_hook_count, 20)
            self.assertTrue(all(len(layer.hooks) == 1 for layer in layers.values()))
            for index in reversed(range(20)):
                layers[index].emit(_FakeTensor())

        self.assertTrue(manager.closed)
        self.assertEqual(manager.registered_hook_count, 0)
        self.assertTrue(all(not layer.hooks for layer in layers.values()))
        self.assertEqual(tuple(manager.captures), tuple(range(20)))
        self.assertTrue(
            all(capture.layer.layer_idx == index for index, capture in manager.captures.items())
        )
        self.assertTrue(
            all(handle.remove_calls == 1 for layer in layers.values() for handle in layer.handles)
        )

    def test_forward_exception_removes_all_handles(self):
        discovery, layers = _discovery()
        manager = ScopedHookManager(discovery)

        with self.assertRaisesRegex(RuntimeError, "controlled forward"), manager:
            raise RuntimeError("controlled forward")

        self.assertTrue(all(not layer.hooks for layer in layers.values()))

    def test_capture_callback_exception_removes_all_handles(self):
        discovery, layers = _discovery()

        def fail(_capture):
            raise ValueError("controlled storage failure")

        manager = ScopedHookManager(discovery, capture_callback=fail)
        with self.assertRaisesRegex(ValueError, "controlled storage"), manager:
            layers[0].emit(_FakeTensor())

        self.assertTrue(manager.closed)
        self.assertTrue(all(not layer.hooks for layer in layers.values()))

    def test_cleanup_is_idempotent_and_reentry_fails(self):
        discovery, layers = _discovery()
        manager = ScopedHookManager(discovery)
        manager.__enter__()
        manager.close()
        manager.close()

        self.assertTrue(all(not layer.hooks for layer in layers.values()))
        with self.assertRaises(ActivationHookError) as caught:
            manager.__enter__()
        self.assertIs(
            caught.exception.code,
            HookErrorCode.INVALID_MANAGER_STATE,
        )

    def test_cleanup_failure_retains_only_unresolved_handle_for_retry(self):
        discovery, layers = _discovery()
        layers[0].remove_failures_before_success = 1
        manager = ScopedHookManager(discovery)
        manager.__enter__()

        with self.assertRaises(ActivationHookError) as caught:
            manager.close()

        self.assertIs(caught.exception.code, HookErrorCode.CLEANUP_FAILED)
        self.assertFalse(manager.closed)
        self.assertEqual(manager.registered_hook_count, 1)
        self.assertEqual(len(layers[0].hooks), 1)
        self.assertTrue(
            all(
                handle.remove_calls == 1
                for index, layer in layers.items()
                if index != 0
                for handle in layer.handles
            )
        )

        manager.close()

        self.assertTrue(manager.closed)
        self.assertEqual(manager.registered_hook_count, 0)
        self.assertTrue(all(not layer.hooks for layer in layers.values()))
        self.assertEqual(layers[0].handles[0].remove_calls, 2)
        self.assertTrue(
            all(
                handle.remove_calls == 1
                for index, layer in layers.items()
                if index != 0
                for handle in layer.handles
            )
        )

    def test_forward_exception_remains_primary_when_cleanup_fails(self):
        discovery, layers = _discovery()
        layers[0].remove_failures_before_success = 1
        manager = ScopedHookManager(discovery)

        with (
            self.assertRaisesRegex(
                RuntimeError, "controlled forward"
            ) as caught,
            manager,
        ):
            raise RuntimeError("controlled forward")

        cleanup_error = caught.exception.__cause__
        self.assertIsInstance(cleanup_error, ActivationHookError)
        self.assertIs(cleanup_error.code, HookErrorCode.CLEANUP_FAILED)
        self.assertFalse(manager.closed)
        self.assertEqual(manager.registered_hook_count, 1)

        manager.close()
        self.assertTrue(manager.closed)

    def test_callback_exception_remains_primary_when_cleanup_fails(self):
        discovery, layers = _discovery()
        layers[0].remove_failures_before_success = 1

        def fail(_capture):
            raise ValueError("controlled callback failure")

        manager = ScopedHookManager(discovery, capture_callback=fail)
        with self.assertRaisesRegex(
            ValueError, "controlled callback failure"
        ) as caught, manager:
            layers[0].emit(_FakeTensor())

        cleanup_error = caught.exception.__cause__
        self.assertIsInstance(cleanup_error, ActivationHookError)
        self.assertIs(cleanup_error.code, HookErrorCode.CLEANUP_FAILED)
        self.assertTrue(manager.closed)
        self.assertEqual(manager.registered_hook_count, 0)
        self.assertTrue(all(not layer.hooks for layer in layers.values()))

    def test_partial_registration_attempts_every_obtained_handle(self):
        discovery, layers = _discovery()
        layers[0].remove_failures_before_success = 1
        layers[2].registration_error = RuntimeError(
            "controlled registration failure"
        )
        manager = ScopedHookManager(discovery)

        with self.assertRaisesRegex(
            RuntimeError, "controlled registration failure"
        ) as caught:
            manager.__enter__()

        cleanup_error = caught.exception.__cause__
        self.assertIsInstance(cleanup_error, ActivationHookError)
        self.assertIs(cleanup_error.code, HookErrorCode.CLEANUP_FAILED)
        self.assertEqual(layers[0].handles[0].remove_calls, 1)
        self.assertEqual(layers[1].handles[0].remove_calls, 1)
        self.assertEqual(manager.registered_hook_count, 1)
        self.assertFalse(manager.closed)
        self.assertEqual(len(layers[0].hooks), 1)
        self.assertFalse(layers[1].hooks)

        manager.close()
        self.assertTrue(manager.closed)

    def test_malformed_registration_handle_remains_observable(self):
        discovery, layers = _discovery()
        layers[0].return_malformed_handle = True
        manager = ScopedHookManager(discovery)

        with self.assertRaises(ActivationHookError) as caught:
            manager.__enter__()

        self.assertIs(caught.exception.code, HookErrorCode.REGISTRATION_FAILED)
        cleanup_error = caught.exception.__cause__
        self.assertIsInstance(cleanup_error, ActivationHookError)
        self.assertIs(cleanup_error.code, HookErrorCode.CLEANUP_FAILED)
        self.assertFalse(manager.closed)
        self.assertEqual(manager.registered_hook_count, 1)
        self.assertEqual(len(layers[0].hooks), 1)

        stale_callback = layers[0].callback_history[0]
        with self.assertRaises(ActivationHookError) as callback_error:
            stale_callback(layers[0], (), _FakeTensor())
        self.assertIs(
            callback_error.exception.code,
            HookErrorCode.CALLBACK_AFTER_CLOSE,
        )

        with self.assertRaises(ActivationHookError) as retry_error:
            manager.close()
        self.assertIs(retry_error.exception.code, HookErrorCode.CLEANUP_FAILED)
        self.assertEqual(manager.registered_hook_count, 1)
        self.assertFalse(manager.closed)

    def test_second_independent_run_has_no_stale_capture_or_hooks(self):
        discovery, layers = _discovery()
        first = ScopedHookManager(discovery)
        with first:
            for index in range(20):
                layers[index].emit(_FakeTensor())

        second = ScopedHookManager(discovery)
        self.assertEqual(dict(second.captures), {})
        self.assertTrue(all(not layer.hooks for layer in layers.values()))
        with second:
            self.assertEqual(dict(second.captures), {})
            for index in range(20):
                layers[index].emit(_FakeTensor())

        self.assertEqual(tuple(second.captures), tuple(range(20)))
        self.assertTrue(all(not layer.hooks for layer in layers.values()))

    def test_missing_callback_rejects_and_cleans_up(self):
        discovery, layers = _discovery()
        manager = ScopedHookManager(discovery)

        with self.assertRaises(ActivationHookError) as caught, manager:
            for index in range(19):
                layers[index].emit(_FakeTensor())

        self.assertIs(caught.exception.code, HookErrorCode.MISSING_CALLBACK)
        self.assertTrue(all(not layer.hooks for layer in layers.values()))

    def test_duplicate_callback_rejects_and_cleans_up(self):
        discovery, layers = _discovery()
        manager = ScopedHookManager(discovery)

        with self.assertRaises(ActivationHookError) as caught, manager:
            layers[0].emit(_FakeTensor())
            layers[0].emit(_FakeTensor())

        self.assertIs(caught.exception.code, HookErrorCode.DUPLICATE_CALLBACK)
        self.assertTrue(all(not layer.hooks for layer in layers.values()))

    def test_inconsistent_shape_rejects_and_cleans_up(self):
        discovery, layers = _discovery()
        manager = ScopedHookManager(discovery)

        with self.assertRaises(ActivationHookError) as caught, manager:
            layers[0].emit(_FakeTensor((1, 24, 8)))
            layers[1].emit(_FakeTensor((1, 25, 8)))

        self.assertIs(
            caught.exception.code,
            HookErrorCode.INCONSISTENT_CAPTURE,
        )
        self.assertTrue(all(not layer.hooks for layer in layers.values()))

    def test_callback_after_closure_rejects(self):
        discovery, layers = _discovery()
        manager = ScopedHookManager(discovery)
        with manager:
            for index in range(20):
                layers[index].emit(_FakeTensor())
        stale_callback = layers[0].callback_history[-1]

        with self.assertRaises(ActivationHookError) as caught:
            stale_callback(layers[0], (), _FakeTensor())

        self.assertIs(
            caught.exception.code,
            HookErrorCode.CALLBACK_AFTER_CLOSE,
        )


if __name__ == "__main__":
    unittest.main()
