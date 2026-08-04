"""Focused CPU-only evidence for Person A Phase 3, Step 3.1."""

from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

import mineocclude.models.mineworld_adapter as adapter_module
from mineocclude.contracts.activation import (
    ACTIVATION_KEY_FIELDS,
    TOKENS_PER_FRAME_ACTION_PAIR,
    VISUAL_TOKENS_PER_FRAME,
)
from mineocclude.contracts.identity import FRAME_KEY, SCHEMA_VERSION
from mineocclude.models.mineworld_adapter import (
    MINEWORLD_ADAPTER_API_VERSION,
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
    FreeRolloutResult,
    MineWorldAdapter,
    MineWorldAdapterError,
    MineWorldRuntimeIdentity,
    PreprocessedFrame,
    RuntimeLoadRequest,
    TeacherForcedRequest,
    TeacherForcedResult,
    TokenizedTrajectory,
    TrajectoryTokenizationRequest,
    UnavailableMineWorldAdapter,
    ValidatedTrajectory,
    create_mineworld_adapter,
)


GIT_SHA = "a" * 40
SHA256 = "b" * 64
ACTION_TOKEN_COUNT = (
    TOKENS_PER_FRAME_ACTION_PAIR - VISUAL_TOKENS_PER_FRAME
)


def _frame_identity(frame_idx: int = 0) -> FrameIdentity:
    return FrameIdentity(
        schema_version=SCHEMA_VERSION,
        trajectory_id="trajectory-api-test",
        model_frame_idx=frame_idx,
    )


def _runtime_request() -> RuntimeLoadRequest:
    return RuntimeLoadRequest(
        schema_version=SCHEMA_VERSION,
        runtime_id="runtime-api-test",
        mineocclude_revision=GIT_SHA,
        mineworld_source_revision=GIT_SHA,
        modelscope_asset_revision=GIT_SHA,
        mineworld_source_root=Path("external/MineWorld"),
        model_config_path=Path("external/model_config.py"),
        main_checkpoint_path=Path("external/model.ckpt"),
        vae_config_path=Path("external/vae/config.json"),
        vae_checkpoint_path=Path("external/vae/vae.ckpt"),
        model_config_sha256=SHA256,
        main_checkpoint_sha256=SHA256,
        vae_config_sha256=SHA256,
        vae_checkpoint_sha256=SHA256,
        environment_report_sha256=SHA256,
        precision="bfloat16",
        device="cuda:0",
    )


def _runtime_identity() -> MineWorldRuntimeIdentity:
    return MineWorldRuntimeIdentity(
        schema_version=SCHEMA_VERSION,
        adapter_api_version=MINEWORLD_ADAPTER_API_VERSION,
        runtime_id="runtime-api-test",
        mineocclude_revision=GIT_SHA,
        mineworld_source_revision=GIT_SHA,
        modelscope_asset_revision=GIT_SHA,
        model_config_sha256=SHA256,
        main_checkpoint_sha256=SHA256,
        vae_config_sha256=SHA256,
        vae_checkpoint_sha256=SHA256,
        environment_report_sha256=SHA256,
        preprocessing_identity="mineworld-gradio-frame-v1",
        action_conversion_identity="mineworld-vpt-action-v1",
        model_class="LlamaLVM",
        transformer_class="LlamaForCausalLM",
        vae_class="VAE",
        decoder_layer_path="transformer.model.layers",
        layer_count=20,
        hidden_size=2048,
        max_position_embeddings=5552,
        visual_tokens_per_frame=336,
        action_tokens_per_frame=ACTION_TOKEN_COUNT,
        tokens_per_pair=347,
        max_context_pairs=16,
        precision="bfloat16",
        device="cuda:0",
    )


def _trajectory_input() -> AcceptedTrajectoryInput:
    return AcceptedTrajectoryInput(
        schema_version=SCHEMA_VERSION,
        trajectory_id="trajectory-api-test",
        accepted_manifest_sha256=SHA256,
        document={"schema_version": SCHEMA_VERSION},
    )


def _validated_trajectory() -> ValidatedTrajectory:
    return ValidatedTrajectory(
        schema_version=SCHEMA_VERSION,
        trajectory_id="trajectory-api-test",
        accepted_manifest_sha256=SHA256,
        source_document_sha256=SHA256,
        frame_identities=(_frame_identity(),),
    )


def _preprocess_request() -> FramePreprocessRequest:
    return FramePreprocessRequest(
        identity=_frame_identity(),
        source_frame_idx=0,
        frame=object(),
    )


def _preprocessed_frame() -> PreprocessedFrame:
    return PreprocessedFrame(
        identity=_frame_identity(),
        source_frame_idx=0,
        shape=(224, 384, 3),
        dtype="uint8",
        color_order="RGB",
        content_sha256=SHA256,
        frame=object(),
    )


def _action_request() -> ActionConversionRequest:
    return ActionConversionRequest(
        identity=_frame_identity(),
        action_idx=0,
        raw_action={"camera": [0.0, 0.0]},
    )


def _converted_action() -> ConvertedAction:
    return ConvertedAction(
        identity=_frame_identity(),
        action_idx=0,
        token_ids=tuple(range(ACTION_TOKEN_COUNT)),
        converter_identity="mineworld-vpt-action-v1",
        content_sha256=SHA256,
    )


def _frame_token_map() -> FrameTokenMap:
    return FrameTokenMap(
        schema_version=SCHEMA_VERSION,
        trajectory_id="trajectory-api-test",
        sequence_length=347,
        spans=(
            FrameTokenSpan(
                identity=_frame_identity(),
                pair_index=0,
                visual_positions=tuple(range(336)),
                action_positions=tuple(range(336, 347)),
            ),
        ),
    )


def _tokenization_request() -> TrajectoryTokenizationRequest:
    return TrajectoryTokenizationRequest(
        runtime_identity=_runtime_identity(),
        trajectory=_validated_trajectory(),
        frames=(_preprocessed_frame(),),
        actions=(_converted_action(),),
    )


def _tokenized_trajectory() -> TokenizedTrajectory:
    return TokenizedTrajectory(
        runtime_identity=_runtime_identity(),
        trajectory_id="trajectory-api-test",
        token_ids=tuple(range(347)),
        frame_token_map=_frame_token_map(),
        token_sha256=SHA256,
    )


def _teacher_request(batch_size: int = 1) -> TeacherForcedRequest:
    return TeacherForcedRequest(
        runtime_identity=_runtime_identity(),
        trajectory=_tokenized_trajectory(),
        seed=7,
        precision="bfloat16",
        batch_size=batch_size,
    )


def _rollout_request() -> FreeRolloutRequest:
    return FreeRolloutRequest(
        runtime_identity=_runtime_identity(),
        context=_tokenized_trajectory(),
        run_id="rollout-api-test",
        seed=7,
        generated_frame_count=1,
        output_directory=Path("external/evidence"),
        generation_config_sha256=SHA256,
    )


class MineWorldAdapterApiTests(unittest.TestCase):
    def test_public_adapter_symbols_import_and_protocol_is_satisfied(self):
        expected = {
            "MINEWORLD_ADAPTER_API_VERSION",
            "AcceptedTrajectoryInput",
            "ActionConversionRequest",
            "AdapterFailureCode",
            "AdapterOperation",
            "ConvertedAction",
            "FrameIdentity",
            "FramePreprocessRequest",
            "FrameTokenMap",
            "FrameTokenSpan",
            "FreeRolloutRequest",
            "FreeRolloutResult",
            "MineWorldAdapter",
            "MineWorldAdapterError",
            "MineWorldRuntimeIdentity",
            "PreprocessedFrame",
            "RuntimeLoadRequest",
            "TeacherForcedRequest",
            "TeacherForcedResult",
            "TokenizedTrajectory",
            "TrajectoryTokenizationRequest",
            "UnavailableMineWorldAdapter",
            "ValidatedTrajectory",
            "create_mineworld_adapter",
        }
        self.assertEqual(expected, set(adapter_module.__all__))
        self.assertIsInstance(UnavailableMineWorldAdapter(), MineWorldAdapter)
        self.assertIsInstance(create_mineworld_adapter(), MineWorldAdapter)

    def test_typed_request_and_result_records_validate_and_are_frozen(self):
        self.assertEqual(_runtime_request().schema_version, SCHEMA_VERSION)
        self.assertEqual(_runtime_identity().tokens_per_pair, 347)
        self.assertEqual(_trajectory_input().trajectory_id, "trajectory-api-test")
        self.assertEqual(
            _validated_trajectory().frame_identities[0].key,
            ("trajectory-api-test", 0),
        )
        self.assertEqual(_preprocessed_frame().shape, (224, 384, 3))
        self.assertEqual(len(_converted_action().token_ids), 11)
        self.assertEqual(
            _tokenization_request().trajectory.trajectory_id,
            "trajectory-api-test",
        )
        self.assertEqual(_tokenized_trajectory().frame_token_map.sequence_length, 347)

        teacher_result = TeacherForcedResult(
            runtime_identity=_runtime_identity(),
            trajectory_id="trajectory-api-test",
            frame_token_map=_frame_token_map(),
            output_shape=(1, 347, 2048),
            dtype="bfloat16",
            device="cuda:0",
            output_sha256=SHA256,
            elapsed_seconds=1.0,
            output=object(),
        )
        rollout_result = FreeRolloutResult(
            runtime_identity=_runtime_identity(),
            trajectory_id="trajectory-api-test",
            run_id="rollout-api-test",
            generated_frame_count=1,
            video_path=Path("external/output.mp4"),
            video_sha256=SHA256,
            metadata_path=Path("external/output.jsonl"),
            metadata_sha256=SHA256,
            elapsed_seconds=1.0,
        )
        self.assertEqual(teacher_result.output_shape, (1, 347, 2048))
        self.assertEqual(rollout_result.generated_frame_count, 1)
        with self.assertRaises(FrozenInstanceError):
            teacher_result.trajectory_id = "changed"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            FrameIdentity(  # type: ignore[call-arg]
                schema_version=SCHEMA_VERSION,
                trajectory_id="trajectory-api-test",
            )

    def test_invalid_frame_identity_fails_closed(self):
        cases = (
            (
                {
                    "schema_version": "2.0",
                    "trajectory_id": "trajectory-api-test",
                    "model_frame_idx": 0,
                },
                AdapterFailureCode.INVALID_SCHEMA_VERSION,
            ),
            (
                {
                    "schema_version": SCHEMA_VERSION,
                    "trajectory_id": "",
                    "model_frame_idx": 0,
                },
                AdapterFailureCode.INVALID_REQUEST,
            ),
            (
                {
                    "schema_version": SCHEMA_VERSION,
                    "trajectory_id": "trajectory-api-test",
                    "model_frame_idx": -1,
                },
                AdapterFailureCode.INVALID_REQUEST,
            ),
        )
        for kwargs, code in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(MineWorldAdapterError) as caught:
                    FrameIdentity(**kwargs)
                self.assertIs(caught.exception.code, code)

    def test_cross_record_identity_mismatch_is_rejected(self):
        with self.assertRaises(MineWorldAdapterError) as caught:
            ValidatedTrajectory(
                schema_version=SCHEMA_VERSION,
                trajectory_id="trajectory-api-test",
                accepted_manifest_sha256=SHA256,
                source_document_sha256=SHA256,
                frame_identities=(
                    FrameIdentity(SCHEMA_VERSION, "different-trajectory", 0),
                ),
            )
        self.assertIs(caught.exception.code, AdapterFailureCode.INVALID_IDENTITY)

    def test_teacher_forced_and_rollout_are_distinct(self):
        self.assertIsNot(TeacherForcedRequest, FreeRolloutRequest)
        self.assertNotIsInstance(_teacher_request(), FreeRolloutRequest)
        self.assertNotIsInstance(_rollout_request(), TeacherForcedRequest)
        self.assertEqual(_teacher_request(batch_size=2).batch_size, 2)
        with self.assertRaises(MineWorldAdapterError):
            _teacher_request(batch_size=0)
        self.assertNotEqual(
            AdapterOperation.TEACHER_FORCED,
            AdapterOperation.FREE_ROLLOUT,
        )
        self.assertIsNot(
            MineWorldAdapter.teacher_forced,
            MineWorldAdapter.free_rollout,
        )

    def test_structured_failure_preserves_actionable_fields(self):
        with self.assertRaises(MineWorldAdapterError) as caught:
            UnavailableMineWorldAdapter().teacher_forced(_teacher_request())
        error = caught.exception
        self.assertIs(error.code, AdapterFailureCode.OPERATION_UNAVAILABLE)
        self.assertIs(error.operation, AdapterOperation.TEACHER_FORCED)
        self.assertEqual(error.details, (("roadmap_step", "Step 3.7"),))
        self.assertIn("Step 3.7", str(error))

    def test_no_private_mineworld_or_activation_implementation_imports(self):
        tree = ast.parse(inspect.getsource(adapter_module))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertFalse(
            any(
                name == "mineworld" or name.startswith("mineworld.")
                for name in imported_modules
            )
        )
        self.assertTrue(
            {
                "mineocclude.activations.hooks",
                "mineocclude.activations.pool",
                "mineocclude.activations.store",
            }.isdisjoint(imported_modules)
        )
        public_operations = {
            name
            for name, value in inspect.getmembers(
                MineWorldAdapter, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        self.assertEqual(
            public_operations,
            {
                "load_runtime",
                "validate_trajectory",
                "preprocess_frame",
                "convert_action",
                "tokenize_trajectory",
                "teacher_forced",
                "free_rollout",
            },
        )

    def test_placeholder_operations_fail_explicitly(self):
        cases = (
            (
                "load_runtime",
                _runtime_request(),
                AdapterOperation.LOAD_RUNTIME,
                "Step 3.2",
            ),
            (
                "validate_trajectory",
                _trajectory_input(),
                AdapterOperation.VALIDATE_TRAJECTORY,
                "Step 3.3",
            ),
            (
                "preprocess_frame",
                _preprocess_request(),
                AdapterOperation.PREPROCESS_FRAME,
                "Step 3.4",
            ),
            (
                "convert_action",
                _action_request(),
                AdapterOperation.CONVERT_ACTION,
                "Step 3.5",
            ),
            (
                "tokenize_trajectory",
                _tokenization_request(),
                AdapterOperation.TOKENIZE_TRAJECTORY,
                "Step 3.6",
            ),
            (
                "teacher_forced",
                _teacher_request(),
                AdapterOperation.TEACHER_FORCED,
                "Step 3.7",
            ),
            (
                "free_rollout",
                _rollout_request(),
                AdapterOperation.FREE_ROLLOUT,
                "Step 3.8",
            ),
        )
        adapter = UnavailableMineWorldAdapter()
        for method_name, request, operation, step in cases:
            with self.subTest(method=method_name):
                with self.assertRaises(MineWorldAdapterError) as caught:
                    getattr(adapter, method_name)(request)
                self.assertIs(
                    caught.exception.code,
                    AdapterFailureCode.OPERATION_UNAVAILABLE,
                )
                self.assertIs(caught.exception.operation, operation)
                self.assertIn(("roadmap_step", step), caught.exception.details)

    def test_wrong_request_type_is_rejected_before_unavailable(self):
        with self.assertRaises(MineWorldAdapterError) as caught:
            UnavailableMineWorldAdapter().teacher_forced(  # type: ignore[arg-type]
                _rollout_request()
            )
        self.assertIs(caught.exception.code, AdapterFailureCode.INVALID_REQUEST)
        self.assertIs(caught.exception.operation, AdapterOperation.TEACHER_FORCED)

    def test_frozen_identity_and_schema_semantics_remain_unchanged(self):
        self.assertEqual(SCHEMA_VERSION, "1.0")
        self.assertEqual(FRAME_KEY, ("trajectory_id", "model_frame_idx"))
        self.assertEqual(
            ACTIVATION_KEY_FIELDS,
            (
                "trajectory_id",
                "model_frame_idx",
                "layer_idx",
                "hook_site",
            ),
        )
        identity = _frame_identity()
        self.assertEqual(
            identity.key,
            tuple(getattr(identity, field) for field in FRAME_KEY),
        )
        self.assertEqual(_runtime_identity().schema_version, "1.0")


if __name__ == "__main__":
    unittest.main()
