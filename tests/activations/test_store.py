"""Focused CPU tests for complete extraction and limited unpooled storage."""

from __future__ import annotations

import copy
import gc
import hashlib
import json
import tempfile
import unittest
import weakref
from pathlib import Path
from unittest import mock

import numpy
import torch

import mineocclude.activations.store as activation_store
from mineocclude.activations.hooks import (
    CONCEPTUAL_HOOK_SITE,
    HOOK_DISCOVERY_VERSION,
    FrozenHookDiscovery,
    HookCapture,
    HookLayerMetadata,
    NormalizedHookOutput,
    ScopedHookManager,
)
from mineocclude.activations.pool import (
    VisualPoolingError,
    select_visual_token_positions,
)
from mineocclude.activations.store import (
    LIMITED_UNPOOLED_CLASSIFICATION,
    MAX_UNPOOLED_ARTIFACT_SIZE_BYTES,
    ActivationExtractionError,
    ExtractionErrorCode,
    UnpooledPilotIdentity,
    _deterministic_npz,
    extract_complete_pooled_context,
    validate_limited_unpooled_pilot,
    write_limited_unpooled_pilot,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models.mineworld_adapter import (
    FrameIdentity,
    FrameTokenMap,
    FrameTokenSpan,
)

TRAJECTORY_ID = "phase4-wave3-trajectory"


def _token_map(frame_count: int = 2) -> FrameTokenMap:
    identities = tuple(
        FrameIdentity(SCHEMA_VERSION, TRAJECTORY_ID, index)
        for index in range(frame_count)
    )
    spans = []
    for index, identity in enumerate(identities):
        start = index * 347
        spans.append(
            FrameTokenSpan(
                identity=identity,
                pair_index=index,
                visual_positions=tuple(range(start, start + 336)),
                action_positions=tuple(range(start + 336, start + 347)),
                accepted_pair_index=index,
                pair_start=start,
                pair_end_exclusive=start + 347,
                causal_predecessor=identities[index - 1] if index else None,
                causal_successor=(
                    identities[index + 1]
                    if index + 1 < frame_count
                    else None
                ),
            )
        )
    return FrameTokenMap(
        schema_version=SCHEMA_VERSION,
        trajectory_id=TRAJECTORY_ID,
        sequence_length=frame_count * 347,
        spans=tuple(spans),
    )


def _captures(
    frame_count: int = 2,
    hidden_size: int = 4,
    *,
    dtype: torch.dtype = torch.float16,
    requires_grad: bool = False,
) -> dict[int, HookCapture]:
    sequence_length = frame_count * 347
    captures = {}
    for layer_idx in range(20):
        values = (
            torch.arange(
                sequence_length * hidden_size,
                dtype=torch.float32,
            )
            .reshape(1, sequence_length, hidden_size)
            .add(layer_idx)
            .to(dtype=dtype)
        )
        values.requires_grad_(requires_grad)
        metadata = HookLayerMetadata(
            layer_idx=layer_idx,
            module_name=f"model.layers.{layer_idx}",
            module_type="tests.FakeLayer",
            conceptual_site=CONCEPTUAL_HOOK_SITE,
            discovery_version=HOOK_DISCOVERY_VERSION,
        )
        captures[layer_idx] = HookCapture(
            layer=metadata,
            output=NormalizedHookOutput(
                tensor=values,
                shape=(1, sequence_length, hidden_size),
                batch_size=1,
                sequence_length=sequence_length,
                hidden_size=hidden_size,
                container_kind="direct_tensor",
                tuple_index=None,
                structured_field=None,
            ),
        )
    return captures


def _identity(model_frame_idx: int = 0) -> UnpooledPilotIdentity:
    return UnpooledPilotIdentity(
        session_id="person-a-phase4-wave3-controlled",
        trajectory_id=TRAJECTORY_ID,
        model_frame_idx=model_frame_idx,
        hook_site=CONCEPTUAL_HOOK_SITE,
        frame_token_map_sha256="1" * 64,
        mineocclude_revision="2" * 40,
        mineworld_revision="3" * 40,
        asset_revision="4" * 40,
        model_config_sha256="5" * 64,
        main_checkpoint_sha256="6" * 64,
        vae_config_sha256="7" * 64,
        vae_checkpoint_sha256="8" * 64,
        environment_report_sha256="9" * 64,
        preprocessing_profile="preprocess-v1",
        action_conversion_profile="actions-v1",
        tokenization_profile="tokens-v1",
        accepted_trajectory_package_sha256="a" * 64,
        input_mp4_sha256="b" * 64,
    )


def _write_pilot(
    directory: Path,
    *,
    captures: dict[int, HookCapture] | None = None,
    frame_count: int = 2,
):
    captures = captures or _captures(frame_count=frame_count)
    frame_map = _token_map(frame_count)
    candidates = extract_complete_pooled_context(
        captures=captures,
        frame_token_map=frame_map,
        hook_site=CONCEPTUAL_HOOK_SITE,
    )
    selection = select_visual_token_positions(
        frame_map,
        trajectory_id=TRAJECTORY_ID,
        model_frame_idx=0,
        hooked_sequence_length=frame_map.sequence_length,
    )
    result = write_limited_unpooled_pilot(
        captures=captures,
        frame_token_map=frame_map,
        selection=selection,
        pooled_candidates=candidates,
        identity=_identity(),
        output_directory=directory,
        enabled=True,
    )
    return result, captures, candidates, frame_map


def _pilot_write_arguments(
    directory: Path,
    *,
    frame_count: int = 1,
) -> tuple[dict[str, object], dict[int, HookCapture], tuple, FrameTokenMap]:
    captures = _captures(frame_count=frame_count)
    frame_map = _token_map(frame_count)
    candidates = extract_complete_pooled_context(
        captures=captures,
        frame_token_map=frame_map,
        hook_site=CONCEPTUAL_HOOK_SITE,
    )
    selection = select_visual_token_positions(
        frame_map,
        trajectory_id=TRAJECTORY_ID,
        model_frame_idx=0,
        hooked_sequence_length=frame_map.sequence_length,
    )
    arguments: dict[str, object] = {
        "captures": captures,
        "frame_token_map": frame_map,
        "selection": selection,
        "pooled_candidates": candidates,
        "identity": _identity(),
        "output_directory": directory,
        "enabled": True,
    }
    return arguments, captures, candidates, frame_map


def _replace_npz(
    artifact: Path,
    manifest: Path,
    arrays: dict[str, numpy.ndarray],
) -> None:
    payload = _deterministic_npz(arrays)
    artifact.write_bytes(payload)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["artifact"]["size_bytes"] = len(payload)
    document["artifact"]["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class CompleteContextExtractionTests(unittest.TestCase):
    def test_two_extractions_are_identical_complete_and_ordered(self):
        frame_map = _token_map(2)
        captures = _captures(2, requires_grad=True)

        first = extract_complete_pooled_context(
            captures=captures,
            frame_token_map=frame_map,
            hook_site=CONCEPTUAL_HOOK_SITE,
        )
        second = extract_complete_pooled_context(
            captures=captures,
            frame_token_map=frame_map,
            hook_site=CONCEPTUAL_HOOK_SITE,
        )

        expected_keys = tuple(
            (TRAJECTORY_ID, frame_idx, layer_idx, CONCEPTUAL_HOOK_SITE)
            for frame_idx in range(2)
            for layer_idx in range(20)
        )
        self.assertEqual(tuple(item.key for item in first), expected_keys)
        self.assertEqual(
            tuple(item.key for item in second),
            expected_keys,
        )
        self.assertEqual(len(first), 40)
        for left, right in zip(first, second, strict=True):
            self.assertTrue(torch.equal(left.vector, right.vector))
            self.assertEqual(left.vector.shape, (4,))
            self.assertEqual(left.vector.dtype, torch.float32)
            self.assertEqual(left.vector.device.type, "cpu")
            self.assertTrue(left.vector.is_contiguous())
            self.assertFalse(left.vector.requires_grad)
            self.assertIsNone(left.vector.grad_fn)

    def test_returned_candidates_do_not_retain_capture_tensors(self):
        captures = _captures(1, requires_grad=True)
        references = [
            weakref.ref(capture.output.tensor)
            for capture in captures.values()
        ]
        candidates = extract_complete_pooled_context(
            captures=captures,
            frame_token_map=_token_map(1),
            hook_site=CONCEPTUAL_HOOK_SITE,
        )

        captures.clear()
        gc.collect()

        self.assertTrue(all(reference() is None for reference in references))
        self.assertTrue(all(item.vector.grad_fn is None for item in candidates))

    def test_capture_and_map_inconsistencies_fail_closed(self):
        cases = []
        missing = _captures(1)
        missing.pop(19)
        cases.append((missing, _token_map(1), ExtractionErrorCode.INCOMPLETE_LAYERS))

        wrong_shape = _captures(1)
        object.__setattr__(
            wrong_shape[7].output,
            "tensor",
            torch.zeros((1, 347, 5), dtype=torch.float16),
        )
        cases.append(
            (
                wrong_shape,
                _token_map(1),
                ExtractionErrorCode.INCONSISTENT_CAPTURE,
            )
        )

        wrong_dtype = _captures(1)
        object.__setattr__(
            wrong_dtype[8].output,
            "tensor",
            wrong_dtype[8].output.tensor.to(torch.float32),
        )
        cases.append(
            (
                wrong_dtype,
                _token_map(1),
                ExtractionErrorCode.INCONSISTENT_CAPTURE,
            )
        )

        wrong_normalization = _captures(1)
        object.__setattr__(
            wrong_normalization[9].output,
            "container_kind",
            "tuple",
        )
        cases.append(
            (
                wrong_normalization,
                _token_map(1),
                ExtractionErrorCode.INCONSISTENT_CAPTURE,
            )
        )

        wrong_device = _captures(1)
        meta_tensor = torch.empty(
            (1, 347, 4),
            dtype=torch.float16,
            device="meta",
        )
        object.__setattr__(wrong_device[10].output, "tensor", meta_tensor)
        cases.append(
            (
                wrong_device,
                _token_map(1),
                ExtractionErrorCode.INCONSISTENT_CAPTURE,
            )
        )

        wrong_map = copy.copy(_token_map(1))
        object.__setattr__(wrong_map, "sequence_length", 346)
        cases.append(
            (
                _captures(1),
                wrong_map,
                ExtractionErrorCode.INVALID_FRAME_TOKEN_MAP,
            )
        )

        for captures, frame_map, code in cases:
            with self.subTest(code=code), self.assertRaises(
                ActivationExtractionError
            ) as caught:
                extract_complete_pooled_context(
                    captures=captures,
                    frame_token_map=frame_map,
                    hook_site=CONCEPTUAL_HOOK_SITE,
                )
            self.assertIs(caught.exception.code, code)

    def test_mapping_key_mismatch_and_duplicate_scientific_identity_reject(self):
        captures = _captures(1)
        captures[1] = captures[0]
        with self.assertRaises(ActivationExtractionError) as caught:
            extract_complete_pooled_context(
                captures=captures,
                frame_token_map=_token_map(1),
                hook_site=CONCEPTUAL_HOOK_SITE,
            )
        self.assertIs(
            caught.exception.code,
            ExtractionErrorCode.INCONSISTENT_CAPTURE,
        )

    def test_nonfinite_selected_values_are_pooling_candidate_failures(self):
        captures = _captures(1)
        captures[0].output.tensor[0, 0, 0] = torch.nan

        with self.assertRaises(ActivationExtractionError) as caught:
            extract_complete_pooled_context(
                captures=captures,
                frame_token_map=_token_map(1),
                hook_site=CONCEPTUAL_HOOK_SITE,
            )

        self.assertIs(
            caught.exception.code,
            ExtractionErrorCode.INVALID_CANDIDATES,
        )
        self.assertIsInstance(caught.exception.__cause__, VisualPoolingError)
        self.assertIn("nonfinite_selected_value", str(caught.exception))


class _Handle:
    def __init__(self, module, key):
        self.module = module
        self.key = key

    def remove(self):
        self.module.callbacks.pop(self.key, None)


class _Layer:
    def __init__(self):
        self.callbacks = {}
        self.next_key = 0

    def register_forward_hook(self, callback):
        key = self.next_key
        self.next_key += 1
        self.callbacks[key] = callback
        return _Handle(self, key)

    def emit(self, value):
        for callback in tuple(self.callbacks.values()):
            callback(self, (), value)


def _discovery():
    layers = tuple(_Layer() for _ in range(20))
    metadata = tuple(
        HookLayerMetadata(
            layer_idx=index,
            module_name=f"decoder.layers.{index}",
            module_type=f"{_Layer.__module__}.{_Layer.__qualname__}",
            conceptual_site=CONCEPTUAL_HOOK_SITE,
            discovery_version=HOOK_DISCOVERY_VERSION,
        )
        for index in range(20)
    )
    return (
        FrozenHookDiscovery(
            layers=metadata,
            module_name_pattern="decoder.layers.{layer_idx}",
            conceptual_site=CONCEPTUAL_HOOK_SITE,
            discovery_version=HOOK_DISCOVERY_VERSION,
            _modules=layers,
        ),
        layers,
    )


class ConsecutiveManagerSafetyTests(unittest.TestCase):
    def _attempt(self, *, fail_at=None):
        discovery, layers = _discovery()
        callback_layers = []

        def callback(capture):
            callback_layers.append(capture.layer.layer_idx)
            if capture.layer.layer_idx == fail_at:
                raise RuntimeError("controlled wave3 failure")

        manager = ScopedHookManager(
            discovery,
            capture_callback=callback,
        )
        accepted = ()
        with self.assertRaises(RuntimeError) if fail_at is not None else _null():
            with manager:
                self.assertEqual(sum(len(layer.callbacks) for layer in layers), 20)
                for layer in layers:
                    layer.emit(torch.zeros((1, 347, 4)))
            accepted = extract_complete_pooled_context(
                captures=manager.captures,
                frame_token_map=_token_map(1),
                hook_site=CONCEPTUAL_HOOK_SITE,
            )
        self.assertTrue(manager.closed)
        self.assertEqual(sum(len(layer.callbacks) for layer in layers), 0)
        return accepted, callback_layers

    def test_success_failure_success_cleans_hooks_and_stale_captures(self):
        first, first_callbacks = self._attempt()
        failed, failed_callbacks = self._attempt(fail_at=10)
        second, second_callbacks = self._attempt()

        self.assertEqual(first_callbacks, list(range(20)))
        self.assertEqual(failed_callbacks, list(range(11)))
        self.assertEqual(second_callbacks, list(range(20)))
        self.assertEqual(failed, ())
        self.assertEqual(
            tuple(item.key for item in first),
            tuple(item.key for item in second),
        )
        self.assertTrue(
            all(
                torch.equal(left.vector, right.vector)
                for left, right in zip(first, second, strict=True)
            )
        )


class _null:
    def __enter__(self):
        return None

    def __exit__(self, *_args):
        return False


class LimitedUnpooledPilotTests(unittest.TestCase):
    def test_round_trip_is_no_pickle_exact_scope_and_reproduces_pooling(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            result, captures, candidates, _frame_map = _write_pilot(directory)

            self.assertEqual(
                result.token_shape,
                (20, 336, 4),
            )
            self.assertEqual(result.token_dtype, "float16")
            self.assertEqual(result.layer_indices, tuple(range(20)))
            self.assertEqual(result.visual_positions, tuple(range(336)))
            self.assertLess(
                result.artifact_size_bytes,
                MAX_UNPOOLED_ARTIFACT_SIZE_BYTES,
            )
            with numpy.load(result.artifact_path, allow_pickle=False) as arrays:
                self.assertEqual(
                    set(arrays.files),
                    {"token_values", "layer_indices", "visual_positions"},
                )
                self.assertEqual(arrays["token_values"].dtype, numpy.float16)
                before = arrays["token_values"].copy()
            captures[0].output.tensor.fill_(999)
            with numpy.load(result.artifact_path, allow_pickle=False) as arrays:
                self.assertTrue(numpy.array_equal(arrays["token_values"], before))
            selected = [
                item
                for item in candidates
                if item.model_frame_idx == 0
            ]
            self.assertEqual(len(selected), 20)
            self.assertTrue(
                all(record["torch_equal"] for record in result.pooling_audit)
            )
            document = json.loads(
                result.manifest_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                document["classification"],
                LIMITED_UNPOOLED_CLASSIFICATION,
            )
            self.assertFalse(
                document["scope"]["dataset_wide_unpooled_storage_enabled"]
            )
            self.assertEqual(
                sorted(path.suffix for path in directory.iterdir()),
                [".json", ".npz"],
            )

    def test_default_pooled_extraction_writes_nothing_and_opt_in_is_required(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            captures = _captures(1)
            frame_map = _token_map(1)
            candidates = extract_complete_pooled_context(
                captures=captures,
                frame_token_map=frame_map,
                hook_site=CONCEPTUAL_HOOK_SITE,
            )
            self.assertEqual(tuple(directory.iterdir()), ())
            selection = select_visual_token_positions(
                frame_map,
                trajectory_id=TRAJECTORY_ID,
                model_frame_idx=0,
                hooked_sequence_length=347,
            )
            with self.assertRaises(ActivationExtractionError) as caught:
                write_limited_unpooled_pilot(
                    captures=captures,
                    frame_token_map=frame_map,
                    selection=selection,
                    pooled_candidates=candidates,
                    identity=_identity(),
                    output_directory=directory,
                )
            self.assertIs(
                caught.exception.code,
                ExtractionErrorCode.UNPOOLED_DISABLED,
            )
            self.assertEqual(tuple(directory.iterdir()), ())

    def test_overwrite_and_extra_tensor_artifact_reject(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            result, captures, candidates, frame_map = _write_pilot(directory)
            selection = select_visual_token_positions(
                frame_map,
                trajectory_id=TRAJECTORY_ID,
                model_frame_idx=0,
                hooked_sequence_length=frame_map.sequence_length,
            )
            artifact_before = result.artifact_path.read_bytes()
            manifest_before = result.manifest_path.read_bytes()
            with self.assertRaises(ActivationExtractionError) as caught:
                write_limited_unpooled_pilot(
                    captures=captures,
                    frame_token_map=frame_map,
                    selection=selection,
                    pooled_candidates=candidates,
                    identity=_identity(),
                    output_directory=directory,
                    enabled=True,
                )
            self.assertIs(caught.exception.code, ExtractionErrorCode.OUTPUT_EXISTS)
            self.assertEqual(result.artifact_path.read_bytes(), artifact_before)
            self.assertEqual(result.manifest_path.read_bytes(), manifest_before)

            (directory / "second.npy").write_bytes(b"not-approved")
            with self.assertRaises(ActivationExtractionError) as caught:
                validate_limited_unpooled_pilot(
                    result.manifest_path,
                    expected_hidden_size=4,
                )
            self.assertIs(caught.exception.code, ExtractionErrorCode.EXTRA_ARTIFACT)

    def test_wrong_dtype_action_positions_and_size_bound_reject(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            captures = _captures(1, dtype=torch.float32)
            frame_map = _token_map(1)
            candidates = extract_complete_pooled_context(
                captures=captures,
                frame_token_map=frame_map,
                hook_site=CONCEPTUAL_HOOK_SITE,
            )
            selection = select_visual_token_positions(
                frame_map,
                trajectory_id=TRAJECTORY_ID,
                model_frame_idx=0,
                hooked_sequence_length=347,
            )
            with self.assertRaises(ActivationExtractionError) as caught:
                write_limited_unpooled_pilot(
                    captures=captures,
                    frame_token_map=frame_map,
                    selection=selection,
                    pooled_candidates=candidates,
                    identity=_identity(),
                    output_directory=directory,
                    enabled=True,
                )
            self.assertIs(caught.exception.code, ExtractionErrorCode.UNSAFE_ARRAY)

            action_selection = copy.copy(selection)
            object.__setattr__(
                action_selection,
                "positions",
                tuple(range(11, 347)),
            )
            with self.assertRaises(ActivationExtractionError) as caught:
                write_limited_unpooled_pilot(
                    captures=_captures(1),
                    frame_token_map=frame_map,
                    selection=action_selection,
                    pooled_candidates=extract_complete_pooled_context(
                        captures=_captures(1),
                        frame_token_map=frame_map,
                        hook_site=CONCEPTUAL_HOOK_SITE,
                    ),
                    identity=_identity(),
                    output_directory=directory,
                    enabled=True,
                )
            self.assertIs(
                caught.exception.code,
                ExtractionErrorCode.INVALID_FRAME_TOKEN_MAP,
            )

            with self.assertRaises(ActivationExtractionError) as caught:
                write_limited_unpooled_pilot(
                    captures=_captures(1),
                    frame_token_map=frame_map,
                    selection=selection,
                    pooled_candidates=extract_complete_pooled_context(
                        captures=_captures(1),
                        frame_token_map=frame_map,
                        hook_site=CONCEPTUAL_HOOK_SITE,
                    ),
                    identity=_identity(),
                    output_directory=directory,
                    enabled=True,
                    maximum_size_bytes=1024,
                )
            self.assertIs(
                caught.exception.code,
                ExtractionErrorCode.SIZE_LIMIT_EXCEEDED,
            )

            class OversizedPayload:
                def __len__(self):
                    return MAX_UNPOOLED_ARTIFACT_SIZE_BYTES + 1

            with mock.patch(
                "mineocclude.activations.store._deterministic_npz",
                return_value=OversizedPayload(),
            ), self.assertRaises(ActivationExtractionError) as caught:
                write_limited_unpooled_pilot(
                    captures=_captures(1),
                    frame_token_map=frame_map,
                    selection=selection,
                    pooled_candidates=extract_complete_pooled_context(
                        captures=_captures(1),
                        frame_token_map=frame_map,
                        hook_site=CONCEPTUAL_HOOK_SITE,
                    ),
                    identity=_identity(),
                    output_directory=directory,
                    enabled=True,
                )
            self.assertIs(
                caught.exception.code,
                ExtractionErrorCode.SIZE_LIMIT_EXCEEDED,
            )

    def test_duplicate_pilot_candidates_reject_before_layer_mapping(self):
        variants = ("same_object", "conflicting_metadata")
        for variant in variants:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as raw:
                directory = Path(raw)
                arguments, _captures_value, candidates, _map = (
                    _pilot_write_arguments(directory, frame_count=2)
                )
                duplicate = candidates[0]
                if variant == "conflicting_metadata":
                    duplicate = copy.copy(duplicate)
                    object.__setattr__(
                        duplicate,
                        "selected_visual_token_count",
                        335,
                    )
                arguments["pooled_candidates"] = candidates + (duplicate,)

                with self.assertRaises(ActivationExtractionError) as caught:
                    write_limited_unpooled_pilot(**arguments)

                self.assertIs(
                    caught.exception.code,
                    ExtractionErrorCode.INVALID_CANDIDATES,
                )
                self.assertEqual(tuple(directory.iterdir()), ())

    def test_manifest_write_failure_is_all_or_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            arguments, _captures_value, _candidates, _map = (
                _pilot_write_arguments(directory)
            )
            original_atomic_write = activation_store._atomic_write

            def controlled_write(path, payload):
                if path.name.endswith(".manifest.json"):
                    raise ActivationExtractionError(
                        ExtractionErrorCode.SERIALIZATION_FAILED,
                        "controlled manifest-write failure",
                    )
                original_atomic_write(path, payload)

            with mock.patch.object(
                activation_store,
                "_atomic_write",
                side_effect=controlled_write,
            ), self.assertRaises(ActivationExtractionError) as caught:
                write_limited_unpooled_pilot(**arguments)

            self.assertIs(
                caught.exception.code,
                ExtractionErrorCode.SERIALIZATION_FAILED,
            )
            self.assertEqual(tuple(directory.iterdir()), ())

    def test_final_validation_failure_is_all_or_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            arguments, _captures_value, _candidates, _map = (
                _pilot_write_arguments(directory)
            )
            failure = ActivationExtractionError(
                ExtractionErrorCode.POOLING_AUDIT_FAILED,
                "controlled final-validation failure",
            )

            with mock.patch.object(
                activation_store,
                "validate_limited_unpooled_pilot",
                side_effect=failure,
            ), self.assertRaises(ActivationExtractionError) as caught:
                write_limited_unpooled_pilot(**arguments)

            self.assertIs(caught.exception, failure)
            self.assertEqual(tuple(directory.iterdir()), ())

    def test_cleanup_failure_keeps_primary_exception_authoritative(self):
        primary = ActivationExtractionError(
            ExtractionErrorCode.INVALID_MANIFEST,
            "controlled primary failure",
        )
        with tempfile.TemporaryDirectory() as raw:
            created = Path(raw) / "created.npz"
            created.write_bytes(b"controlled")

            with mock.patch.object(
                Path,
                "unlink",
                side_effect=OSError("controlled cleanup failure"),
            ), self.assertRaises(ActivationExtractionError) as caught:
                activation_store._raise_primary_after_output_cleanup(
                    primary,
                    (created,),
                )

            self.assertIs(caught.exception, primary)
            self.assertIsInstance(
                caught.exception.__cause__,
                ActivationExtractionError,
            )
            self.assertIs(
                caught.exception.__cause__.code,
                ExtractionErrorCode.SERIALIZATION_FAILED,
            )
            self.assertIsInstance(
                caught.exception.__cause__.__cause__,
                OSError,
            )

    def test_validator_rejects_shape_layers_positions_hash_and_object_arrays(self):
        mutations = ("shape", "layers", "positions", "object", "hash")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as raw:
                directory = Path(raw)
                result, _captures_value, _candidates, _map = _write_pilot(directory)
                with numpy.load(result.artifact_path, allow_pickle=False) as source:
                    arrays = {
                        name: source[name].copy()
                        for name in source.files
                    }
                if mutation == "shape":
                    arrays["token_values"] = arrays["token_values"][:, :-1, :]
                    _replace_npz(result.artifact_path, result.manifest_path, arrays)
                elif mutation == "layers":
                    arrays["layer_indices"][0] = 1
                    _replace_npz(result.artifact_path, result.manifest_path, arrays)
                elif mutation == "positions":
                    arrays["visual_positions"][0] = 336
                    _replace_npz(result.artifact_path, result.manifest_path, arrays)
                elif mutation == "object":
                    arrays["token_values"] = numpy.array(
                        [object()],
                        dtype=object,
                    )
                    numpy.savez(result.artifact_path, **arrays)
                    payload = result.artifact_path.read_bytes()
                    document = json.loads(
                        result.manifest_path.read_text(encoding="utf-8")
                    )
                    document["artifact"]["size_bytes"] = len(payload)
                    document["artifact"]["sha256"] = hashlib.sha256(
                        payload
                    ).hexdigest()
                    result.manifest_path.write_text(
                        json.dumps(document, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                else:
                    document = json.loads(
                        result.manifest_path.read_text(encoding="utf-8")
                    )
                    document["artifact"]["sha256"] = "0" * 64
                    result.manifest_path.write_text(
                        json.dumps(document, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                with self.assertRaises(ActivationExtractionError):
                    validate_limited_unpooled_pilot(
                        result.manifest_path,
                        expected_hidden_size=4,
                    )


if __name__ == "__main__":
    unittest.main()
