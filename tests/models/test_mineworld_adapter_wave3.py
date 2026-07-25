"""CPU-only tests for Person A Phase 3 Wave 3 (Steps 3.6-3.7)."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import subprocess
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import numpy as np

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models import _mineworld_adapter_wave2 as wave2
from mineocclude.models import _mineworld_adapter_wave3 as wave3
from mineocclude.models.mineworld_adapter import (
    AcceptedTrajectoryInput,
    ActionConversionRequest,
    AdapterFailureCode,
    AdapterOperation,
    ConvertedAction,
    FrameIdentity,
    FramePreprocessRequest,
    FrameTokenMap,
    FrameTokenSpan,
    FreeRolloutRequest,
    MineWorldAdapterError,
    MineWorldRuntimeIdentity,
    PreprocessedFrame,
    TeacherForcedRequest,
    TrajectoryTokenizationRequest,
    ValidatedTrajectory,
)
from mineocclude.models.phase2_evidence import canonical_json_bytes

REPO_ROOT = Path(__file__).resolve().parents[2]
TRAJECTORY_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "trajectory" / "accepted_package.json"
)
WAVE3_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "models" / "phase3_wave3_token_map.json"
)
EXTERNAL_SOURCE = Path(r"C:\Users\lollo\MineWorld-Upstream")
SHA256 = "a" * 64
GIT_SHA = "b" * 40


def _runtime_identity(**changes) -> MineWorldRuntimeIdentity:
    values = {
        "schema_version": SCHEMA_VERSION,
        "adapter_api_version": "person-a-mineworld-adapter-v1.0",
        "runtime_id": "phase3-wave3-cpu-fake",
        "mineocclude_revision": GIT_SHA,
        "mineworld_source_revision": wave2.PINNED_SOURCE_REVISION,
        "modelscope_asset_revision": wave2.PINNED_ASSET_REVISION,
        "model_config_sha256": wave2.PINNED_MODEL_CONFIG_SHA256,
        "main_checkpoint_sha256": wave2.PINNED_MAIN_CHECKPOINT_SHA256,
        "vae_config_sha256": wave2.PINNED_VAE_CONFIG_SHA256,
        "vae_checkpoint_sha256": wave2.PINNED_VAE_CHECKPOINT_SHA256,
        "environment_report_sha256": SHA256,
        "preprocessing_identity": wave2.PREPROCESSING_PROFILE,
        "action_conversion_identity": wave2.ACTION_CONVERTER_IDENTITY,
        "model_class": wave2.PINNED_MODEL_CLASS,
        "transformer_class": wave2.PINNED_TRANSFORMER_CLASS,
        "vae_class": wave2.PINNED_VAE_CLASS,
        "decoder_layer_path": wave2.PINNED_DECODER_PATH,
        "layer_count": 20,
        "hidden_size": 2048,
        "max_position_embeddings": 5552,
        "visual_tokens_per_frame": 336,
        "action_tokens_per_frame": 11,
        "tokens_per_pair": 347,
        "max_context_pairs": 16,
        "precision": "float16",
        "device": "cuda:0",
    }
    values.update(changes)
    return MineWorldRuntimeIdentity(**values)


class _HookHandle:
    def __init__(self, module, identifier):
        self.module = module
        self.identifier = identifier

    def remove(self):
        self.module.hooks.pop(self.identifier, None)


class _FakeDecoder:
    def __init__(self):
        self.hooks = {}
        self.next_identifier = 0

    def register_forward_hook(self, hook):
        identifier = self.next_identifier
        self.next_identifier += 1
        self.hooks[identifier] = hook
        return _HookHandle(self, identifier)

    def emit(self, output):
        for hook in tuple(self.hooks.values()):
            hook(self, (), output)


class _FakeTransformer:
    def __init__(self, layers):
        self.layers = layers
        self.calls = 0
        self.refresh_calls = 0

    def refresh_kvcache(self):
        self.refresh_calls += 1

    def __call__(self, *, input_ids, position_ids):
        self.calls += 1
        output = {
            "input_ids": tuple(input_ids),
            "position_ids": tuple(position_ids),
        }
        for layer in self.layers:
            layer.emit(output)
        return output


class _EvalObject:
    def __init__(self):
        self.training = False

    def eval(self):
        self.training = False
        return self


class _FakeModel(_EvalObject):
    def __init__(self):
        super().__init__()
        self.layers = tuple(_FakeDecoder() for _ in range(20))
        self.transformer = _FakeTransformer(self.layers)

    def named_modules(self):
        yield "", self
        for index, layer in enumerate(self.layers):
            yield f"transformer.model.layers.{index}", layer


class _FakeVae(_EvalObject):
    pass


class _VisualTokenizer:
    def __init__(self, *, count=336, value_offset=0, nondeterministic=False):
        self.count = count
        self.value_offset = value_offset
        self.nondeterministic = nondeterministic
        self.calls = 0
        self.frame_keys = []

    def __call__(self, _runtime, frames, _identity):
        self.calls += 1
        self.frame_keys.append(tuple(frame.identity.key for frame in frames))
        offset = self.calls - 1 if self.nondeterministic else 0
        return tuple(
            tuple(
                self.value_offset + offset + frame_index + token
                for token in range(self.count)
            )
            for frame_index, _frame in enumerate(frames)
        )


class _TeacherExecutor:
    def __init__(self, *, error=None):
        self.calls = 0
        self.error = error
        self.observed = []

    def __call__(self, runtime, trajectory, request):
        self.calls += 1
        self.observed.append(
            {
                "token_ids": trajectory.token_ids,
                "attention_mask": trajectory.attention_mask,
                "position_ids": trajectory.position_ids,
                "seed": request.seed,
                "precision": request.precision,
                "batch_size": request.batch_size,
            }
        )
        if self.error is not None:
            raise self.error
        runtime.model.transformer(
            input_ids=trajectory.token_ids,
            position_ids=trajectory.position_ids,
        )
        return wave3._TeacherExecution(
            output={"recorded_history_only": True},
            output_shape=(1, len(trajectory.token_ids), 8262),
            dtype=request.precision,
            device=request.runtime_identity.device,
            output_sha256="c" * 64,
            elapsed_seconds=0.25,
            output_statistics=(
                ("minimum", 0.0),
                ("maximum", 1.0),
                ("mean", 0.5),
                ("standard_deviation", 0.25),
            ),
            inference_mode_applied=True,
        )


def _identity(index, *, trajectory_id="wave3-trajectory"):
    return FrameIdentity(SCHEMA_VERSION, trajectory_id, index)


def _validated(count, *, start=0, trajectory_id="wave3-trajectory"):
    return ValidatedTrajectory(
        schema_version=SCHEMA_VERSION,
        trajectory_id=trajectory_id,
        accepted_manifest_sha256=SHA256,
        source_document_sha256="d" * 64,
        frame_identities=tuple(
            _identity(start + index, trajectory_id=trajectory_id)
            for index in range(count)
        ),
    )


def _preprocessed(identity):
    array = np.full(
        (3, 224, 384),
        identity.model_frame_idx % 13,
        dtype=np.float32,
    )
    return PreprocessedFrame(
        identity=identity,
        source_frame_idx=identity.model_frame_idx,
        shape=(3, 224, 384),
        dtype="float32",
        color_order="RGB",
        content_sha256=hashlib.sha256(array.tobytes(order="C")).hexdigest(),
        frame=array,
        preprocessing_profile=wave2.PREPROCESSING_PROFILE,
    )


def _action(identity):
    token_ids = tuple(range(8192, 8203))
    content = {
        "normalized_action": {},
        "token_ids": list(token_ids),
        "positional_roles": list(wave2.ACTION_POSITIONAL_ROLES),
        "vocabulary_offset": 8192,
    }
    return ConvertedAction(
        identity=identity,
        action_idx=identity.model_frame_idx,
        token_ids=token_ids,
        converter_identity=wave2.ACTION_CONVERTER_IDENTITY,
        content_sha256=hashlib.sha256(
            canonical_json_bytes(content)
        ).hexdigest(),
        raw_action_sha256="f" * 64,
        normalized_action=MappingProxyType({}),
        vocabulary_offset=8192,
        positional_roles=wave2.ACTION_POSITIONAL_ROLES,
        converter_source_revision=wave2.PINNED_SOURCE_REVISION,
        is_noop=True,
    )


def _request(validated):
    return TrajectoryTokenizationRequest(
        runtime_identity=_runtime_identity(),
        trajectory=validated,
        frames=tuple(_preprocessed(identity) for identity in validated.frame_identities),
        actions=tuple(_action(identity) for identity in validated.frame_identities),
    )


def _seed_adapter(adapter, validated, identity=None):
    identity = identity or _runtime_identity()
    model = _FakeModel()
    runtime = wave2._LoadedRuntime(
        model=model,
        vae=_FakeVae(),
        config={"pinned": True},
        load_state={},
        architecture={},
    )
    adapter._runtime = runtime
    adapter._runtime_identity_record = identity
    adapter._source_root = Path("controlled-test-source")
    adapter._accepted_frames = {
        item.key: wave2._AcceptedFrame(
            identity=item,
            render_frame_idx=item.model_frame_idx,
            action_idx=item.model_frame_idx,
            raw_action=MappingProxyType({}),
            raw_action_sha256=SHA256,
        )
        for item in validated.frame_identities
    }
    return runtime


class Wave3TokenizationTests(unittest.TestCase):
    def adapter(self, validated, tokenizer=None, *, identity=None, executor=None):
        tokenizer = tokenizer or _VisualTokenizer()
        executor = executor or _TeacherExecutor()
        adapter = wave3._Wave3MineWorldAdapter(
            visual_tokenizer=tokenizer,
            teacher_executor=executor,
        )
        runtime = _seed_adapter(adapter, validated, identity)
        return adapter, tokenizer, executor, runtime

    def test_one_and_multiple_frames_build_exact_pairs_and_positions(self):
        for count in (1, 3):
            with self.subTest(count=count):
                validated = _validated(count, start=40)
                adapter, tokenizer, _executor, _runtime = self.adapter(validated)
                result = adapter.tokenize_trajectory(_request(validated))
                self.assertEqual(tokenizer.calls, 2)
                self.assertEqual(len(result.token_ids), count * 347)
                self.assertEqual(result.attention_mask, (1,) * (count * 347))
                self.assertEqual(result.position_ids, tuple(range(count * 347)))
                self.assertEqual(
                    tuple(item.model_frame_idx for item in result.included_frame_identities),
                    tuple(range(40, 40 + count)),
                )
                for pair_index, span in enumerate(result.frame_token_map.spans):
                    start = pair_index * 347
                    self.assertEqual(span.pair_start, start)
                    self.assertEqual(span.pair_end_exclusive, start + 347)
                    self.assertEqual(span.visual_positions, tuple(range(start, start + 336)))
                    self.assertEqual(
                        span.action_positions,
                        tuple(range(start + 336, start + 347)),
                    )
                    self.assertTrue(
                        set(span.visual_positions).isdisjoint(span.action_positions)
                    )
                self.assertEqual(
                    result.token_sha256,
                    wave3._token_sha256(result.token_ids),
                )
                self.assertEqual(
                    result.frame_token_map_sha256,
                    wave3._frame_token_map_sha256(result.frame_token_map),
                )

    def test_seventeen_frames_truncate_only_old_complete_pairs(self):
        validated = _validated(17, start=100)
        adapter, _tokenizer, _executor, _runtime = self.adapter(validated)
        result = adapter.tokenize_trajectory(_request(validated))
        self.assertEqual(result.context_pair_count, 16)
        self.assertEqual(result.accepted_frame_count, 17)
        self.assertEqual(len(result.token_ids), 5552)
        self.assertEqual(
            tuple(item.model_frame_idx for item in result.excluded_frame_identities),
            (100,),
        )
        self.assertEqual(
            tuple(item.model_frame_idx for item in result.included_frame_identities),
            tuple(range(101, 117)),
        )
        first = result.frame_token_map.spans[0]
        last = result.frame_token_map.spans[-1]
        self.assertEqual(first.accepted_pair_index, 1)
        self.assertEqual(first.causal_predecessor.model_frame_idx, 100)
        self.assertEqual(last.identity.model_frame_idx, 116)
        self.assertIsNone(last.causal_successor)
        self.assertEqual(
            result.token_ids[-11:],
            _action(_identity(116)).token_ids,
        )

    def test_visual_token_failures_prevent_teacher_execution(self):
        validated = _validated(2)
        cases = {
            "wrong-count": _VisualTokenizer(count=335),
            "out-of-range": _VisualTokenizer(value_offset=8192),
            "nondeterministic": _VisualTokenizer(nondeterministic=True),
            "malformed": lambda _runtime, _frames, _identity: object(),
        }
        for label, tokenizer in cases.items():
            with self.subTest(label=label):
                executor = _TeacherExecutor()
                adapter, _tokenizer, _executor, _runtime = self.adapter(
                    validated, tokenizer, executor=executor
                )
                with self.assertRaises(MineWorldAdapterError):
                    adapter.tokenize_trajectory(_request(validated))
                self.assertEqual(executor.calls, 0)

    def test_preprocessing_action_and_identity_failures_are_before_vae(self):
        validated = _validated(2)
        cases = []
        wrong_profile = list(_request(validated).frames)
        wrong_profile[0] = replace(
            wrong_profile[0], preprocessing_profile="wrong"
        )
        cases.append(("profile", tuple(wrong_profile), _request(validated).actions))
        mutated = list(_request(validated).frames)
        mutated_array = mutated[0].frame.copy()
        mutated_array[0, 0, 0] = 100
        object.__setattr__(mutated[0], "frame", mutated_array)
        cases.append(("hash", tuple(mutated), _request(validated).actions))
        wrong_actions = list(_request(validated).actions)
        wrong_actions[0] = replace(
            wrong_actions[0], converter_identity="wrong"
        )
        cases.append(("action", _request(validated).frames, tuple(wrong_actions)))
        wrong_content = list(_request(validated).actions)
        wrong_content[0] = replace(
            wrong_content[0], content_sha256="0" * 64
        )
        cases.append(
            ("action-content", _request(validated).frames, tuple(wrong_content))
        )
        for label, frames, actions in cases:
            with self.subTest(label=label):
                tokenizer = _VisualTokenizer()
                adapter, _tokenizer, _executor, _runtime = self.adapter(
                    validated, tokenizer
                )
                request = TrajectoryTokenizationRequest(
                    _runtime_identity(), validated, frames, actions
                )
                with self.assertRaises(MineWorldAdapterError):
                    adapter.tokenize_trajectory(request)
                self.assertEqual(tokenizer.calls, 0)

    def test_missing_vae_and_wrong_action_count_fail_closed(self):
        validated = _validated(1)
        tokenizer = _VisualTokenizer()
        adapter, _tokenizer, _executor, runtime = self.adapter(
            validated, tokenizer
        )
        runtime.vae = None
        with self.assertRaises(MineWorldAdapterError) as caught:
            adapter.tokenize_trajectory(_request(validated))
        self.assertIs(
            caught.exception.code,
            AdapterFailureCode.OPERATION_UNAVAILABLE,
        )
        self.assertEqual(tokenizer.calls, 0)

        valid = _action(validated.frame_identities[0])
        with self.assertRaises(MineWorldAdapterError):
            replace(valid, token_ids=valid.token_ids[:-1])

    def test_missing_or_reordered_components_fail_at_request_boundary(self):
        validated = _validated(2)
        valid = _request(validated)
        cases = (
            (valid.frames[:-1], valid.actions),
            (valid.frames, valid.actions[:-1]),
            (tuple(reversed(valid.frames)), valid.actions),
            (valid.frames, tuple(reversed(valid.actions))),
        )
        for frames, actions in cases:
            with (
                self.subTest(
                    frame_count=len(frames), action_count=len(actions)
                ),
                self.assertRaises(MineWorldAdapterError),
            ):
                TrajectoryTokenizationRequest(
                    _runtime_identity(), validated, frames, actions
                )

    def test_impossible_position_budget_fails_closed(self):
        validated = _validated(1)
        small = _runtime_identity(max_position_embeddings=346)
        request = _request(validated)
        request = replace(request, runtime_identity=small)
        adapter, _tokenizer, _executor, _runtime = self.adapter(
            validated, identity=small
        )
        with self.assertRaises(MineWorldAdapterError) as caught:
            adapter.tokenize_trajectory(request)
        self.assertIn("position budget", str(caught.exception))

    def test_frame_token_map_rejects_split_overlap_or_duplicate_semantics(self):
        identity = _identity(0)
        valid = FrameTokenSpan(
            identity,
            0,
            tuple(range(336)),
            tuple(range(336, 347)),
        )
        with self.assertRaises(MineWorldAdapterError):
            FrameTokenSpan(
                identity,
                0,
                tuple(range(1, 337)),
                tuple(range(337, 348)),
            )
        with self.assertRaises(MineWorldAdapterError):
            FrameTokenMap(
                SCHEMA_VERSION,
                identity.trajectory_id,
                694,
                (valid, replace(valid, pair_index=1)),
            )

    def test_machine_readable_pilot_fixture_matches_constructed_map(self):
        fixture = json.loads(WAVE3_FIXTURE.read_text(encoding="utf-8"))
        validated = _validated(3, start=40)
        adapter, _tokenizer, _executor, _runtime = self.adapter(validated)
        result = adapter.tokenize_trajectory(_request(validated))
        self.assertEqual(fixture["schema_version"], SCHEMA_VERSION)
        self.assertEqual(fixture["fixture_version"], "person-a-phase3-wave3-v1.0")
        self.assertEqual(
            fixture["expected"]["frame_token_map"],
            wave3._compact_map_payload(result.frame_token_map),
        )
        self.assertEqual(
            fixture["expected"]["token_sha256"], result.token_sha256
        )
        self.assertEqual(
            fixture["expected"]["frame_token_map_sha256"],
            result.frame_token_map_sha256,
        )


class Wave3TeacherForcedTests(unittest.TestCase):
    def setUp(self):
        self.validated = _validated(3, start=40)
        self.executor = _TeacherExecutor()
        self.adapter = wave3._Wave3MineWorldAdapter(
            visual_tokenizer=_VisualTokenizer(),
            teacher_executor=self.executor,
        )
        self.runtime = _seed_adapter(self.adapter, self.validated)
        self.tokenized = self.adapter.tokenize_trajectory(
            _request(self.validated)
        )

    def teacher_request(self, **changes):
        values = {
            "runtime_identity": _runtime_identity(),
            "trajectory": self.tokenized,
            "seed": 17,
            "precision": "float16",
            "batch_size": 1,
        }
        values.update(changes)
        return TeacherForcedRequest(**values)

    def test_exact_recorded_sequence_mask_positions_and_metadata_reach_model(self):
        result = self.adapter.teacher_forced(self.teacher_request())
        observed = self.executor.observed[0]
        self.assertEqual(observed["token_ids"], self.tokenized.token_ids)
        self.assertEqual(observed["attention_mask"], self.tokenized.attention_mask)
        self.assertEqual(observed["position_ids"], self.tokenized.position_ids)
        self.assertEqual(observed["seed"], 17)
        self.assertEqual(observed["batch_size"], 1)
        self.assertEqual(self.runtime.model.transformer.calls, 1)
        self.assertEqual(result.token_sha256, self.tokenized.token_sha256)
        self.assertEqual(result.input_sequence_length, 3 * 347)
        self.assertEqual(result.output_shape, (1, 3 * 347, 8262))
        self.assertEqual(result.output, {"recorded_history_only": True})
        self.assertEqual(result.seed, 17)
        self.assertEqual(result.output_statistics[2], ("mean", 0.5))

    def test_external_hook_context_observes_all_layers_and_cleans_up(self):
        observed = []
        received_names = []

        @contextmanager
        def hooks(modules):
            received_names.extend(name for name, _module in modules)
            handles = []
            try:
                for name, module in modules:
                    handles.append(
                        module.register_forward_hook(
                            lambda _module, _inputs, output, name=name: observed.append(
                                (name, output)
                            )
                        )
                    )
                yield
            finally:
                for handle in reversed(handles):
                    handle.remove()

        self.adapter.teacher_forced(
            self.teacher_request(hook_context_factory=hooks)
        )
        self.assertEqual(len(received_names), 20)
        self.assertEqual(len(observed), 20)
        self.assertEqual(
            received_names,
            [
                f"transformer.model.layers.{index}"
                for index in range(20)
            ],
        )
        self.assertTrue(
            all(not layer.hooks for layer in self.runtime.model.layers)
        )

    def test_corruption_and_runtime_mismatches_reject_before_forward(self):
        cases = []
        bad_hash = copy.copy(self.tokenized)
        object.__setattr__(bad_hash, "token_sha256", "0" * 64)
        cases.append(("sequence-hash", self.teacher_request(trajectory=bad_hash)))
        bad_map = copy.copy(self.tokenized)
        object.__setattr__(bad_map, "frame_token_map_sha256", "0" * 64)
        cases.append(("map-hash", self.teacher_request(trajectory=bad_map)))
        bad_mask = copy.copy(self.tokenized)
        object.__setattr__(bad_mask, "attention_mask", ())
        cases.append(("mask", self.teacher_request(trajectory=bad_mask)))
        bad_positions = copy.copy(self.tokenized)
        object.__setattr__(
            bad_positions,
            "position_ids",
            tuple(reversed(self.tokenized.position_ids)),
        )
        cases.append(("positions", self.teacher_request(trajectory=bad_positions)))
        cases.append(("batch", self.teacher_request(batch_size=2)))
        cases.append(("precision", self.teacher_request(precision="bfloat16")))
        for label, request in cases:
            with self.subTest(label=label):
                before = self.executor.calls
                with self.assertRaises(MineWorldAdapterError):
                    self.adapter.teacher_forced(request)
                self.assertEqual(self.executor.calls, before)

    def test_missing_or_training_model_rejects_before_forward(self):
        for label, value in (("missing", None), ("training", self.runtime.model)):
            with self.subTest(label=label):
                original = self.runtime.model
                if label == "training":
                    original.training = True
                else:
                    self.runtime.model = value
                try:
                    with self.assertRaises(MineWorldAdapterError):
                        self.adapter.teacher_forced(self.teacher_request())
                    self.assertEqual(self.executor.calls, 0)
                finally:
                    self.runtime.model = original
                    original.training = False

    def test_model_error_is_structured_and_preserves_type_and_message(self):
        failing = _TeacherExecutor(error=ValueError("controlled forward failure"))
        adapter = wave3._Wave3MineWorldAdapter(
            visual_tokenizer=_VisualTokenizer(),
            teacher_executor=failing,
        )
        _seed_adapter(adapter, self.validated)
        tokenized = adapter.tokenize_trajectory(_request(self.validated))
        with self.assertRaises(MineWorldAdapterError) as caught:
            adapter.teacher_forced(
                TeacherForcedRequest(
                    _runtime_identity(), tokenized, 1, "float16"
                )
            )
        self.assertIs(
            caught.exception.code,
            AdapterFailureCode.RUNTIME_EXECUTION_FAILED,
        )
        self.assertIs(caught.exception.operation, AdapterOperation.TEACHER_FORCED)
        self.assertIn("controlled forward failure", str(caught.exception))
        self.assertIn(("exception_type", "ValueError"), caught.exception.details)

    def test_repeated_fake_forward_is_exact_and_rollout_remains_unavailable(self):
        first = self.adapter.teacher_forced(self.teacher_request())
        second = self.adapter.teacher_forced(self.teacher_request())
        self.assertEqual(first.output_sha256, second.output_sha256)
        self.assertEqual(first.output_statistics, second.output_statistics)
        self.assertEqual(self.runtime.model.transformer.calls, 2)
        rollout = FreeRolloutRequest(
            runtime_identity=_runtime_identity(),
            context=self.tokenized,
            run_id="wave3-rollout-unavailable",
            seed=1,
            generated_frame_count=1,
            output_directory=Path("outside-git"),
            generation_config_sha256=SHA256,
        )
        with self.assertRaises(MineWorldAdapterError) as caught:
            self.adapter.free_rollout(rollout)
        self.assertIs(
            caught.exception.code,
            AdapterFailureCode.OPERATION_UNAVAILABLE,
        )

    def test_default_executor_source_uses_inference_mode_and_no_generation(self):
        source = inspect.getsource(wave3._official_teacher_executor)
        self.assertIn("torch.inference_mode()", source)
        self.assertIn("refresh_kvcache", source)
        self.assertNotIn("generate(", source)
        self.assertNotIn("free_rollout", source)


class Wave3IntegratedBoundaryTests(unittest.TestCase):
    def test_accepted_to_teacher_path_preserves_identity_and_failure_order(self):
        package = json.loads(TRAJECTORY_FIXTURE.read_text(encoding="utf-8"))
        tokenizer = _VisualTokenizer()
        executor = _TeacherExecutor()
        adapter = wave3._Wave3MineWorldAdapter(
            visual_tokenizer=tokenizer,
            teacher_executor=executor,
        )
        runtime_identity = _runtime_identity()
        runtime = _seed_adapter(adapter, _validated(1), runtime_identity)
        adapter._accepted_frames = {}
        validated = adapter.validate_trajectory(
            AcceptedTrajectoryInput(
                schema_version=SCHEMA_VERSION,
                trajectory_id=package["trajectory_id"],
                accepted_manifest_sha256=SHA256,
                document=package,
            )
        )
        frames = []
        actions = []
        for index, identity in enumerate(validated.frame_identities):
            source = np.full((360, 640, 3), index, dtype=np.uint8)
            frames.append(
                adapter.preprocess_frame(
                    FramePreprocessRequest(identity, index, source)
                )
            )
            accepted = adapter._accepted_frames[identity.key]

            class Converter:
                def convert(self, raw_action, index=index):
                    return {}, tuple(range(8192, 8203)), True

            adapter._converter = Converter()
            actions.append(
                adapter.convert_action(
                    ActionConversionRequest(
                        identity,
                        accepted.action_idx,
                        accepted.raw_action,
                    )
                )
            )
        tokenized = adapter.tokenize_trajectory(
            TrajectoryTokenizationRequest(
                runtime_identity,
                validated,
                tuple(frames),
                tuple(actions),
            )
        )
        result = adapter.teacher_forced(
            TeacherForcedRequest(
                runtime_identity, tokenized, 23, "float16"
            )
        )
        expected_keys = tuple(identity.key for identity in validated.frame_identities)
        self.assertEqual(
            tuple(identity.key for identity in tokenized.included_frame_identities),
            expected_keys,
        )
        self.assertEqual(
            tuple(span.identity.key for span in result.frame_token_map.spans),
            expected_keys,
        )
        self.assertEqual(runtime.model.transformer.calls, 1)
        self.assertEqual(result.output, {"recorded_history_only": True})
        self.assertNotIn("generated", repr(tokenized).lower())
        self.assertNotIn("mineocclude.activations", inspect.getsource(wave3))

        corrupted = copy.copy(tokenized)
        object.__setattr__(corrupted, "token_sha256", "0" * 64)
        with self.assertRaises(MineWorldAdapterError):
            adapter.teacher_forced(
                TeacherForcedRequest(
                    runtime_identity, corrupted, 23, "float16"
                )
            )
        self.assertEqual(runtime.model.transformer.calls, 1)


class Wave3OwnershipTests(unittest.TestCase):
    def test_public_exports_and_frozen_contracts_remain_unchanged(self):
        import mineocclude.models.mineworld_adapter as public
        from mineocclude.contracts.activation import ACTIVATION_KEY_FIELDS
        from mineocclude.contracts.identity import FRAME_KEY

        self.assertEqual(len(public.__all__), 24)
        self.assertEqual(SCHEMA_VERSION, "1.0")
        self.assertEqual(FRAME_KEY, ("trajectory_id", "model_frame_idx"))
        self.assertEqual(
            ACTIVATION_KEY_FIELDS,
            ("trajectory_id", "model_frame_idx", "layer_idx", "hook_site"),
        )
        source = inspect.getsource(wave3)
        self.assertNotIn("mineocclude.activations.hooks", source)
        self.assertNotIn("mineocclude.activations.pool", source)
        self.assertNotIn("mineocclude.activations.store", source)

    def test_injected_token_fixture_identity_is_deterministic(self):
        validated = _validated(3, start=40)
        tokenizer = _VisualTokenizer()
        adapter = wave3._Wave3MineWorldAdapter(
            visual_tokenizer=tokenizer,
            teacher_executor=_TeacherExecutor(),
        )
        _seed_adapter(adapter, validated)
        first = adapter.tokenize_trajectory(_request(validated))
        second = adapter.tokenize_trajectory(_request(validated))
        self.assertEqual(first.token_ids, second.token_ids)
        self.assertEqual(first.token_sha256, second.token_sha256)
        payload = {
            "token_ids": list(first.token_ids),
            "frame_token_map": wave3._map_payload(first.frame_token_map),
        }
        self.assertEqual(
            hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
            hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        )

    @unittest.skipUnless(
        EXTERNAL_SOURCE.is_dir(),
        "Pinned MineWorld source is required for direct Wave 3 parity",
    )
    def test_direct_pinned_source_parity_for_wave3_boundaries(self):
        revision = subprocess.run(
            ["git", "-C", str(EXTERNAL_SOURCE), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(EXTERNAL_SOURCE), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertEqual(revision, wave2.PINNED_SOURCE_REVISION)
        self.assertEqual(status, "")
        vae_source = (EXTERNAL_SOURCE / "vae.py").read_text(encoding="utf-8")
        lvm_source = (EXTERNAL_SOURCE / "lvm.py").read_text(encoding="utf-8")
        gradio_source = (EXTERNAL_SOURCE / "mineworld.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def tokenize_images(", vae_source)
        self.assertIn("return min_encoding_indices", vae_source)
        self.assertIn(
            "attention_mask = self._create_attention_mask(input_pos=position_ids)",
            lvm_source,
        )
        self.assertIn("def refresh_kvcache(", lvm_source)
        self.assertIn("action_cache.pop()", gradio_source)
        phase2_source = inspect.getsource(wave3._official_teacher_executor)
        self.assertIn("runtime.vae.tokenize_images", inspect.getsource(wave3))
        self.assertIn("trajectory.position_ids", phase2_source)
        self.assertIn("transformer(", phase2_source)


if __name__ == "__main__":
    unittest.main()
