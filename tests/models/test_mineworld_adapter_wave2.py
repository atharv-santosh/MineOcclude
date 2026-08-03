"""CPU-only tests for Person A Phase 3 Wave 2 (Steps 3.2-3.5)."""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models import _mineworld_adapter_wave2 as wave2
from mineocclude.models.mineworld_adapter import (
    AcceptedTrajectoryInput,
    ActionConversionRequest,
    AdapterFailureCode,
    AdapterOperation,
    FrameIdentity,
    FramePreprocessRequest,
    FrameTokenSpan,
    MineWorldAdapterError,
    RuntimeLoadRequest,
)
from mineocclude.models.phase2_evidence import (
    EvidenceValidationError,
    canonical_json_bytes,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
TRAJECTORY_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "trajectory"
MODEL_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "models"
PHASE2_ARCHITECTURE = (
    REPO_ROOT
    / "docs"
    / "status"
    / "phase2_runtime"
    / "person-a-phase2-aws-20260725-055616"
    / "step2_7"
    / "architecture_report.json"
)
EXTERNAL_SOURCE = Path(r"C:\Users\lollo\MineWorld-Upstream")
RUNTIME_STUB = MODEL_FIXTURES / "runtime_stub"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _raw_action(
    *,
    keys=(),
    dx=0.0,
    dy=0.0,
    buttons=(),
):
    return {
        "keyboard": {"keys": list(keys)},
        "mouse": {"dx": dx, "dy": dy, "buttons": list(buttons)},
    }


def _accepted_package(raw_action=None):
    package = _json(TRAJECTORY_FIXTURES / "accepted_package.json")
    raw_action = raw_action or _raw_action()
    for row in package["streams"]["raw_actions"]:
        row["raw_action"] = copy.deepcopy(raw_action)
    return package


def _accepted_request(package):
    return AcceptedTrajectoryInput(
        schema_version=SCHEMA_VERSION,
        trajectory_id=(
            package["trajectory_id"]
            if isinstance(package.get("trajectory_id"), str)
            else "synthetic_trajectory_0001"
        ),
        accepted_manifest_sha256="d" * 64,
        document=package,
    )


class _EvalSpy:
    def __init__(self):
        self.eval_calls = 0

    def eval(self):
        self.eval_calls += 1
        return self


class _LoaderHarness:
    def __init__(self, load_state=None, architecture=None):
        report = _json(PHASE2_ARCHITECTURE)
        self.load_state = copy.deepcopy(load_state or report["load_state"])
        self.architecture = dict(architecture or wave2._EXPECTED_ARCHITECTURE)
        self.model = _EvalSpy()
        self.vae = _EvalSpy()
        self.calls = 0

    def __call__(self, prepared):
        self.calls += 1
        return wave2._LoadedRuntime(
            model=self.model,
            vae=self.vae,
            config={"target": "pinned"},
            load_state=copy.deepcopy(self.load_state),
            architecture=dict(self.architecture),
        )


class Wave2LoaderTests(unittest.TestCase):
    def setUp(self):
        self.root = RUNTIME_STUB
        self.source_root = self.root / "source"
        self.model_config = self.source_root / "configs" / "700M_16f.yaml"
        self.main_checkpoint = self.root / "main_checkpoint.test"
        self.vae_config = self.root / "vae" / "config.json"
        self.vae_checkpoint = self.root / "vae" / "vae_checkpoint.test"
        for path in (
            self.model_config,
            self.main_checkpoint,
            self.vae_config,
            self.vae_checkpoint,
        ):
            self.assertTrue(path.is_file(), path)
        self.expected_hashes = {
            self.model_config.resolve(): wave2.PINNED_MODEL_CONFIG_SHA256,
            self.main_checkpoint.resolve(): (
                wave2.PINNED_MAIN_CHECKPOINT_SHA256
            ),
            self.vae_config.resolve(): wave2.PINNED_VAE_CONFIG_SHA256,
            self.vae_checkpoint.resolve(): (
                wave2.PINNED_VAE_CHECKPOINT_SHA256
            ),
        }

    def request(self, **changes):
        values = {
            "schema_version": SCHEMA_VERSION,
            "runtime_id": "phase3-wave2-test",
            "mineocclude_revision": "a" * 40,
            "mineworld_source_revision": wave2.PINNED_SOURCE_REVISION,
            "modelscope_asset_revision": wave2.PINNED_ASSET_REVISION,
            "mineworld_source_root": self.source_root,
            "model_config_path": self.model_config,
            "main_checkpoint_path": self.main_checkpoint,
            "vae_config_path": self.vae_config,
            "vae_checkpoint_path": self.vae_checkpoint,
            "model_config_sha256": wave2.PINNED_MODEL_CONFIG_SHA256,
            "main_checkpoint_sha256": (
                wave2.PINNED_MAIN_CHECKPOINT_SHA256
            ),
            "vae_config_sha256": wave2.PINNED_VAE_CONFIG_SHA256,
            "vae_checkpoint_sha256": (
                wave2.PINNED_VAE_CHECKPOINT_SHA256
            ),
            "environment_report_sha256": "e" * 64,
            "precision": wave2.PINNED_PRECISION,
            "device": wave2.PINNED_DEVICE,
        }
        values.update(changes)
        return RuntimeLoadRequest(**values)

    def adapter(self, loader, *, hasher=None, inspector=None):
        return wave2._Wave2MineWorldAdapter(
            file_hasher=(
                hasher
                or (lambda path: self.expected_hashes[path.resolve()])
            ),
            source_inspector=(
                inspector
                or (
                    lambda _root: (
                        wave2.PINNED_SOURCE_REVISION,
                        True,
                    )
                )
            ),
            runtime_loader=loader,
            converter_factory=mock.Mock(),
        )

    def test_valid_preflight_load_state_architecture_and_eval(self):
        loader = _LoaderHarness()
        adapter = self.adapter(loader)
        identity = adapter.load_runtime(self.request())
        self.assertEqual(loader.calls, 1)
        self.assertEqual(loader.model.eval_calls, 1)
        self.assertEqual(loader.vae.eval_calls, 1)
        self.assertEqual(identity.model_class, "LlamaLVM")
        self.assertEqual(identity.decoder_layer_path, "transformer.model.layers")
        self.assertEqual(identity.layer_count, 20)
        self.assertEqual(identity.hidden_size, 2048)
        self.assertEqual(identity.precision, "float16")
        self.assertEqual(identity.schema_version, SCHEMA_VERSION)
        self.assertEqual(
            identity.mineworld_source_revision,
            wave2.PINNED_SOURCE_REVISION,
        )
        self.assertEqual(
            identity.modelscope_asset_revision,
            wave2.PINNED_ASSET_REVISION,
        )
        self.assertEqual(
            identity.main_checkpoint_sha256,
            wave2.PINNED_MAIN_CHECKPOINT_SHA256,
        )
        self.assertEqual(
            identity.vae_checkpoint_sha256,
            wave2.PINNED_VAE_CHECKPOINT_SHA256,
        )
        self.assertEqual(
            identity.preprocessing_identity,
            wave2.PREPROCESSING_PROFILE,
        )
        self.assertEqual(
            identity.action_conversion_identity,
            wave2.ACTION_CONVERTER_IDENTITY,
        )
        self.assertFalse(hasattr(identity, "model"))
        self.assertFalse(hasattr(identity, "vae"))

    def test_default_loader_delegates_to_the_exact_phase2_loading_helper(self):
        prepared = self.adapter(_LoaderHarness())._prepare_runtime(
            self.request()
        )
        transformer_config = SimpleNamespace(
            hidden_size=2048,
            intermediate_size=4096,
            vocab_size=8262,
            max_position_embeddings=5552,
            num_attention_heads=32,
            num_key_value_heads=4,
        )
        vae = type("VAE", (), {})()
        transformer = type(
            "LlamaForCausalLM",
            (),
            {"config": transformer_config},
        )()
        model = type(
            "LlamaLVM",
            (),
            {"transformer": transformer, "tokenizer": vae},
        )()
        load_state = _json(PHASE2_ARCHITECTURE)["load_state"]
        with (
            mock.patch.object(
                wave2,
                "_load_model_with_key_evidence",
                return_value=(model, {"model": "pinned"}, load_state, {}),
            ) as official_loader,
            mock.patch.object(
                wave2,
                "_decoder_layers",
                return_value=("transformer.model.layers", tuple(range(20))),
            ),
            mock.patch.object(
                wave2,
                "_parameter_distribution",
                return_value={"torch.float16": 1},
            ),
        ):
            loaded = wave2._load_official_runtime(prepared)
        self.assertIs(loaded.model, model)
        self.assertIs(loaded.vae, vae)
        official_loader.assert_called_once()
        self.assertEqual(
            official_loader.call_args.kwargs["precision"],
            wave2.PINNED_PRECISION,
        )

    def test_missing_path_fails_before_loader(self):
        loader = _LoaderHarness()
        with self.assertRaises(MineWorldAdapterError) as caught:
            self.adapter(loader).load_runtime(
                self.request(
                    main_checkpoint_path=self.root / "missing-checkpoint.test"
                )
            )
        self.assertEqual(loader.calls, 0)
        self.assertIs(caught.exception.code, AdapterFailureCode.INVALID_REQUEST)

    def test_actual_hash_mismatch_fails_before_loader(self):
        loader = _LoaderHarness()

        def hasher(path):
            if path.resolve() == self.main_checkpoint.resolve():
                return "0" * 64
            return self.expected_hashes[path.resolve()]

        with self.assertRaises(MineWorldAdapterError) as caught:
            self.adapter(loader, hasher=hasher).load_runtime(self.request())
        self.assertEqual(loader.calls, 0)
        self.assertIs(
            caught.exception.code,
            AdapterFailureCode.INVALID_PROVENANCE,
        )

    def test_malformed_hash_rejected_at_public_boundary(self):
        with self.assertRaises(MineWorldAdapterError) as caught:
            self.request(main_checkpoint_sha256="not-a-hash")
        self.assertIs(
            caught.exception.code,
            AdapterFailureCode.INVALID_PROVENANCE,
        )

    def test_wrong_pinned_request_identities_fail_before_loader(self):
        cases = {
            "source": {"mineworld_source_revision": "f" * 40},
            "assets": {"modelscope_asset_revision": "f" * 40},
            "checkpoint": {"main_checkpoint_sha256": "f" * 64},
            "vae": {"vae_checkpoint_sha256": "f" * 64},
            "config": {"model_config_sha256": "f" * 64},
            "config-path": {"model_config_path": self.vae_config},
            "precision": {"precision": "bfloat16"},
            "device": {"device": "cpu"},
        }
        for label, changes in cases.items():
            with self.subTest(label=label):
                loader = _LoaderHarness()
                with self.assertRaises(MineWorldAdapterError):
                    self.adapter(loader).load_runtime(self.request(**changes))
                self.assertEqual(loader.calls, 0)

    def test_source_revision_and_cleanliness_are_observed(self):
        cases = (
            (("f" * 40, True), "revision"),
            ((wave2.PINNED_SOURCE_REVISION, False), "dirty"),
        )
        for observation, label in cases:
            with self.subTest(label=label):
                loader = _LoaderHarness()
                with self.assertRaises(MineWorldAdapterError):
                    self.adapter(
                        loader,
                        inspector=lambda _root, value=observation: value,
                    ).load_runtime(self.request())
                self.assertEqual(loader.calls, 0)

    def test_missing_key_and_profile_drift_are_rejected(self):
        valid = _json(PHASE2_ARCHITECTURE)["load_state"]
        cases = {}
        missing = copy.deepcopy(valid)
        missing["transformer_missing_keys"] = ["required.weight"]
        cases["missing"] = missing
        drift = copy.deepcopy(valid)
        drift["transformer_unexpected_keys"][0] = "unknown.weight"
        cases["unexpected-drift"] = drift
        forged = copy.deepcopy(valid)
        forged["classification"]["final_decision"] = "PASS"
        forged["vae_unexpected_keys"].pop()
        cases["forged-pass"] = forged
        for label, load_state in cases.items():
            with self.subTest(label=label):
                loader = _LoaderHarness(load_state=load_state)
                with self.assertRaises(MineWorldAdapterError) as caught:
                    self.adapter(loader).load_runtime(self.request())
                self.assertIs(
                    caught.exception.code,
                    AdapterFailureCode.INVALID_PROVENANCE,
                )

    def test_every_architecture_mismatch_is_rejected(self):
        fields = (
            "model_class",
            "transformer_class",
            "vae_class",
            "decoder_layer_path",
            "layer_count",
            "hidden_size",
            "intermediate_size",
            "vocab_size",
            "max_position_embeddings",
            "num_attention_heads",
            "num_key_value_heads",
            "visual_tokens",
            "action_tokens",
            "tokens_per_pair",
            "context_pairs",
            "precision",
            "device",
        )
        for field in fields:
            with self.subTest(field=field):
                architecture = dict(wave2._EXPECTED_ARCHITECTURE)
                architecture[field] = "wrong"
                loader = _LoaderHarness(architecture=architecture)
                with self.assertRaises(MineWorldAdapterError):
                    self.adapter(loader).load_runtime(self.request())


class Wave2TrajectoryAndPreprocessingTests(unittest.TestCase):
    def setUp(self):
        self.adapter = wave2._Wave2MineWorldAdapter(
            runtime_loader=mock.Mock(),
            converter_factory=mock.Mock(),
        )
        self.package = _accepted_package()
        self.validated = self.adapter.validate_trajectory(
            _accepted_request(self.package)
        )
        self.identity = self.validated.frame_identities[0]

    def test_accepted_package_preserves_identity_without_mutation(self):
        original = copy.deepcopy(self.package)
        self.assertEqual(
            [item.key for item in self.validated.frame_identities],
            [
                ("synthetic_trajectory_0001", 0),
                ("synthetic_trajectory_0001", 1),
                ("synthetic_trajectory_0001", 2),
            ],
        )
        self.assertEqual(self.package, original)

    def test_every_contract_rejection_stops_before_downstream_work(self):
        fixture_names = (
            "rejected_cardinality.json",
            "rejected_duplicate_identity.json",
            "rejected_impulse_orientation.json",
            "rejected_invalid_client_tick.json",
            "rejected_invalid_identity_type.json",
            "rejected_invalid_payload.json",
            "rejected_invalid_state.json",
            "rejected_malformed_media.json",
            "rejected_mismatched_stream_identity.json",
            "rejected_nonconsecutive_tick.json",
        )
        converter_factory = mock.Mock(side_effect=AssertionError("not reached"))
        adapter = wave2._Wave2MineWorldAdapter(
            runtime_loader=mock.Mock(side_effect=AssertionError("not reached")),
            converter_factory=converter_factory,
        )
        with mock.patch.object(
            wave2,
            "_preprocess_bgr_frame",
            side_effect=AssertionError("not reached"),
        ) as preprocess:
            for filename in fixture_names:
                with self.subTest(filename=filename):
                    package = _json(TRAJECTORY_FIXTURES / filename)
                    with self.assertRaises(MineWorldAdapterError) as caught:
                        adapter.validate_trajectory(_accepted_request(package))
                    self.assertIs(
                        caught.exception.operation,
                        AdapterOperation.VALIDATE_TRAJECTORY,
                    )
                    self.assertTrue(
                        any(
                            key == "contract_rejection_code"
                            for key, _ in caught.exception.details
                        )
                    )
        preprocess.assert_not_called()
        converter_factory.assert_not_called()

    def test_additional_schema_hash_and_final_action_failures(self):
        cases = {}
        wrong_schema = _accepted_package()
        wrong_schema["schema_version"] = "2.0"
        cases["schema"] = wrong_schema
        wrong_hash = _accepted_package()
        wrong_hash["artifacts"]["frame_map"]["sha256"] = "bad"
        cases["hash"] = wrong_hash
        missing_final = _accepted_package()
        missing_final["streams"]["raw_actions"].pop()
        cases["final-action"] = missing_final
        for label, package in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(MineWorldAdapterError):
                    wave2._Wave2MineWorldAdapter().validate_trajectory(
                        _accepted_request(package)
                    )

    @staticmethod
    def golden_source_frame():
        import numpy as np

        y, x = np.indices((360, 640), dtype=np.uint16)
        return np.stack(
            (
                (x + 2 * y) % 256,
                (3 * x + y) % 256,
                np.bitwise_xor(x, y) % 256,
            ),
            axis=2,
        ).astype(np.uint8)

    def test_golden_preprocessing_matches_pinned_fixture(self):
        fixture = _json(
            MODEL_FIXTURES / "phase3_wave2_preprocessing_golden.json"
        )
        request = FramePreprocessRequest(
            identity=self.identity,
            source_frame_idx=0,
            frame=self.golden_source_frame(),
        )
        first = self.adapter.preprocess_frame(request)
        second = self.adapter.preprocess_frame(request)
        expected = fixture["expected_output"]
        self.assertEqual(list(first.shape), expected["shape"])
        self.assertEqual(first.dtype, expected["dtype"])
        self.assertEqual(first.content_sha256, expected["sha256"])
        self.assertEqual(first.content_sha256, second.content_sha256)
        self.assertEqual(first.frame.tobytes(), second.frame.tobytes())
        self.assertEqual(first.identity.key, self.identity.key)
        self.assertEqual(first.source_shape, (360, 640, 3))
        self.assertEqual(first.color_conversion, "BGR_TO_RGB")
        self.assertEqual(first.interpolation, "cv2.INTER_LINEAR")
        observed_stats = dict(first.statistics)
        for name, expected_value in expected["statistics"].items():
            self.assertAlmostEqual(observed_stats[name], expected_value, places=7)

    def test_bgr_rgb_layout_range_and_interpolation(self):
        import cv2
        import numpy as np

        frame = np.empty((360, 640, 3), dtype=np.uint8)
        frame[:] = (10, 20, 30)
        with mock.patch.object(cv2, "resize", wraps=cv2.resize) as resize:
            result = self.adapter.preprocess_frame(
                FramePreprocessRequest(self.identity, 0, frame)
            )
        self.assertEqual(
            resize.call_args.kwargs["interpolation"],
            cv2.INTER_LINEAR,
        )
        self.assertEqual(result.frame.shape, (3, 224, 384))
        self.assertEqual(result.frame.dtype, np.float32)
        expected_rgb = (np.array([30, 20, 10], dtype=np.float32) / 255 - 0.5) / 0.5
        np.testing.assert_allclose(result.frame[:, 0, 0], expected_rgb)
        self.assertGreaterEqual(float(result.frame.min()), -1.0)
        self.assertLessEqual(float(result.frame.max()), 1.0)

    def test_invalid_frame_representations_fail_closed(self):
        import numpy as np

        cases = {
            "wrong-height": np.zeros((359, 640, 3), dtype=np.uint8),
            "wrong-width": np.zeros((360, 639, 3), dtype=np.uint8),
            "wrong-channels": np.zeros((360, 640, 4), dtype=np.uint8),
            "wrong-dtype": np.zeros((360, 640, 3), dtype=np.float32),
            "empty": np.array([], dtype=np.uint8),
            "non-array": object(),
            "nonfinite": np.full((360, 640, 3), np.nan, dtype=np.float32),
        }
        for label, frame in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(MineWorldAdapterError) as caught:
                    self.adapter.preprocess_frame(
                        FramePreprocessRequest(self.identity, 0, frame)
                    )
                self.assertIs(
                    caught.exception.operation,
                    AdapterOperation.PREPROCESS_FRAME,
                )

    def test_identity_and_postcondition_mismatch_fail_closed(self):
        import numpy as np

        with self.assertRaises(MineWorldAdapterError):
            self.adapter.preprocess_frame(
                FramePreprocessRequest(self.identity, 1, self.golden_source_frame())
            )
        with mock.patch.object(
            wave2,
            "_preprocess_bgr_frame",
            side_effect=RuntimeError("unexpected output shape"),
        ):
            with self.assertRaises(MineWorldAdapterError):
                self.adapter.preprocess_frame(
                    FramePreprocessRequest(
                        self.identity,
                        0,
                        np.zeros((360, 640, 3), dtype=np.uint8),
                    )
                )
        valid_tensor = np.zeros((3, 224, 384), dtype=np.float32)
        wrong_evidence = {
            "source_shape": (360, 640, 3),
            "source_dtype": "uint8",
            "source_sha256": "a" * 64,
            "output_shape": (3, 223, 384),
            "output_dtype": "float32",
            "output_sha256": "b" * 64,
            "statistics": {},
        }
        with mock.patch.object(
            wave2,
            "_preprocess_bgr_frame",
            return_value=(valid_tensor, wrong_evidence),
        ):
            with self.assertRaises(MineWorldAdapterError):
                self.adapter.preprocess_frame(
                    FramePreprocessRequest(
                        self.identity,
                        0,
                        np.zeros((360, 640, 3), dtype=np.uint8),
                    )
                )

    def test_fake_vae_boundary_observes_expected_input_and_code_count(self):
        import numpy as np

        fixture = _json(
            MODEL_FIXTURES / "phase3_wave2_preprocessing_golden.json"
        )
        expected_codes = np.array(
            fixture["visual_code_boundary"]["cpu_fake_codes"],
            dtype=np.int64,
        ).reshape(1, 14, 24)
        self.assertEqual(
            hashlib.sha256(
                canonical_json_bytes(expected_codes.reshape(-1).tolist())
            ).hexdigest(),
            fixture["visual_code_boundary"]["cpu_fake_codes_sha256"],
        )
        processed = self.adapter.preprocess_frame(
            FramePreprocessRequest(
                self.identity, 0, self.golden_source_frame()
            )
        )

        class FakeVae:
            def tokenize_images(self, frames):
                self.observed = frames
                return expected_codes.copy()

        vae = FakeVae()
        codes = vae.tokenize_images(processed.frame[None, ...])
        self.assertEqual(vae.observed.shape, (1, 3, 224, 384))
        self.assertEqual(codes.size, 336)
        self.assertEqual(codes.reshape(-1).tolist(), list(range(336)))
        with self.assertRaises(MineWorldAdapterError):
            FrameTokenSpan(
                identity=self.identity,
                pair_index=0,
                visual_positions=tuple(range(335)),
                action_positions=tuple(range(336, 347)),
            )


@unittest.skipUnless(
    EXTERNAL_SOURCE.is_dir(),
    "Pinned MineWorld source is required for direct converter parity",
)
class Wave2ActionConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = _json(
            MODEL_FIXTURES / "phase3_wave2_action_matrix.json"
        )
        cls.converter = wave2._OfficialActionConverter(EXTERNAL_SOURCE)

    def test_every_fixture_matches_pinned_official_converter(self):
        self.assertEqual(self.fixture["schema_version"], SCHEMA_VERSION)
        self.assertEqual(
            self.fixture["fixture_version"],
            "person-a-phase3-action-matrix-v1.0",
        )
        self.assertIn(
            "no expected token ID was assigned by MineOcclude",
            self.fixture["generation_method"],
        )
        self.assertEqual(
            self.fixture["source_revision"],
            wave2.PINNED_SOURCE_REVISION,
        )
        self.assertEqual(
            self.fixture["source_blob_sha256"],
            wave2.MCDATASET_BLOB_SHA256,
        )
        self.assertEqual(
            self.fixture["vocabulary_offset"],
            wave2.ACTION_VOCABULARY_OFFSET,
        )
        self.assertEqual(
            self.fixture["positional_roles"],
            list(wave2.ACTION_POSITIONAL_ROLES),
        )
        self.assertEqual(len(self.fixture["cases"]), 19)
        for case in self.fixture["cases"]:
            with self.subTest(case=case["case_id"]):
                normalized, tokens, is_noop = self.converter.convert(
                    case["raw_action"]
                )
                self.assertEqual(normalized, case["normalized_action"])
                self.assertEqual(list(tokens), case["token_ids"])
                self.assertEqual(is_noop, case["is_noop"])

    def _loaded_adapter(self):
        root = RUNTIME_STUB
        source = root / "source"
        paths = {
            "model_config": source / "configs" / "700M_16f.yaml",
            "main": root / "main_checkpoint.test",
            "vae_config": root / "vae" / "config.json",
            "vae": root / "vae" / "vae_checkpoint.test",
        }
        for path in paths.values():
            self.assertTrue(path.is_file(), path)
        expected = {
            paths["model_config"].resolve(): wave2.PINNED_MODEL_CONFIG_SHA256,
            paths["main"].resolve(): wave2.PINNED_MAIN_CHECKPOINT_SHA256,
            paths["vae_config"].resolve(): wave2.PINNED_VAE_CONFIG_SHA256,
            paths["vae"].resolve(): wave2.PINNED_VAE_CHECKPOINT_SHA256,
        }
        loader = _LoaderHarness()
        adapter = wave2._Wave2MineWorldAdapter(
            file_hasher=lambda path: expected[path.resolve()],
            source_inspector=lambda _root: (
                wave2.PINNED_SOURCE_REVISION,
                True,
            ),
            runtime_loader=loader,
            converter_factory=lambda _root: self.converter,
        )
        request = RuntimeLoadRequest(
            schema_version=SCHEMA_VERSION,
            runtime_id="action-test",
            mineocclude_revision="a" * 40,
            mineworld_source_revision=wave2.PINNED_SOURCE_REVISION,
            modelscope_asset_revision=wave2.PINNED_ASSET_REVISION,
            mineworld_source_root=source,
            model_config_path=paths["model_config"],
            main_checkpoint_path=paths["main"],
            vae_config_path=paths["vae_config"],
            vae_checkpoint_path=paths["vae"],
            model_config_sha256=wave2.PINNED_MODEL_CONFIG_SHA256,
            main_checkpoint_sha256=wave2.PINNED_MAIN_CHECKPOINT_SHA256,
            vae_config_sha256=wave2.PINNED_VAE_CONFIG_SHA256,
            vae_checkpoint_sha256=wave2.PINNED_VAE_CHECKPOINT_SHA256,
            environment_report_sha256="e" * 64,
            precision=wave2.PINNED_PRECISION,
            device=wave2.PINNED_DEVICE,
        )
        adapter.load_runtime(request)
        return adapter

    def test_adapter_records_exact_action_provenance_and_identity(self):
        adapter = self._loaded_adapter()
        case = self.fixture["cases"][0]
        package = _accepted_package(case["raw_action"])
        validated = adapter.validate_trajectory(_accepted_request(package))
        identity = validated.frame_identities[0]
        result = adapter.convert_action(
            ActionConversionRequest(identity, 0, case["raw_action"])
        )
        self.assertEqual(list(result.token_ids), case["token_ids"])
        self.assertEqual(dict(result.normalized_action), case["normalized_action"])
        self.assertEqual(result.vocabulary_offset, 8192)
        self.assertEqual(
            result.positional_roles,
            wave2.ACTION_POSITIONAL_ROLES,
        )
        self.assertEqual(
            result.converter_source_revision,
            wave2.PINNED_SOURCE_REVISION,
        )
        self.assertTrue(result.is_noop)
        self.assertEqual(result.identity.key, identity.key)

    def test_integrated_wave2_boundary_preserves_one_scientific_identity(self):
        adapter = self._loaded_adapter()
        case = self.fixture["cases"][-1]
        package = _accepted_package(case["raw_action"])
        validated = adapter.validate_trajectory(_accepted_request(package))
        identity = validated.frame_identities[0]
        frame = adapter.preprocess_frame(
            FramePreprocessRequest(
                identity,
                0,
                Wave2TrajectoryAndPreprocessingTests.golden_source_frame(),
            )
        )
        action = adapter.convert_action(
            ActionConversionRequest(identity, 0, case["raw_action"])
        )
        self.assertEqual(frame.identity.key, identity.key)
        self.assertEqual(action.identity.key, identity.key)
        self.assertEqual(frame.source_frame_idx, 0)
        self.assertEqual(action.action_idx, 0)
        self.assertEqual(list(action.token_ids), case["token_ids"])

    def test_preprocessing_failure_does_not_initialize_action_converter(self):
        import numpy as np

        converter_factory = mock.Mock(side_effect=AssertionError("not reached"))
        adapter = self._loaded_adapter()
        adapter._converter_factory = converter_factory
        package = _accepted_package(self.fixture["cases"][0]["raw_action"])
        identity = adapter.validate_trajectory(
            _accepted_request(package)
        ).frame_identities[0]
        with self.assertRaises(MineWorldAdapterError):
            adapter.preprocess_frame(
                FramePreprocessRequest(
                    identity,
                    0,
                    np.zeros((1, 1, 3), dtype=np.uint8),
                )
            )
        converter_factory.assert_not_called()

    def test_raw_action_mismatch_and_invalid_inputs_fail_before_tokens(self):
        adapter = self._loaded_adapter()
        accepted_raw = self.fixture["cases"][0]["raw_action"]
        package = _accepted_package(accepted_raw)
        identity = adapter.validate_trajectory(
            _accepted_request(package)
        ).frame_identities[0]
        invalid = {
            "unknown-key": _raw_action(keys=("key.keyboard.unknown",)),
            "unknown-button": _raw_action(buttons=(9,)),
            "nan-camera": _raw_action(dx=float("nan")),
            "infinite-camera": _raw_action(dy=float("inf")),
            "nested-keyboard": {"keyboard": [], "mouse": {}},
            "null-keyboard": {"keyboard": None, "mouse": {}},
            "missing-mouse": {"keyboard": {"keys": []}},
        }
        for label, raw in invalid.items():
            with self.subTest(label=label):
                with self.assertRaises(EvidenceValidationError):
                    self.converter.convert(raw)
        with self.assertRaises(MineWorldAdapterError) as caught:
            adapter.convert_action(
                ActionConversionRequest(
                    identity,
                    0,
                    self.fixture["cases"][1]["raw_action"],
                )
            )
        self.assertIs(caught.exception.code, AdapterFailureCode.INVALID_IDENTITY)

    def test_converter_rejects_nondeterminism_count_offset_and_revision(self):
        case = self.fixture["cases"][0]
        valid_tokens = list(case["token_ids"])
        changed_tokens = list(valid_tokens)
        changed_tokens[4] = 8194
        with mock.patch.object(
            self.converter._converter,
            "get_action_index_from_actiondict",
            side_effect=[valid_tokens, changed_tokens],
        ):
            with self.assertRaises(RuntimeError):
                self.converter.convert(case["raw_action"])
        with mock.patch.object(
            self.converter._converter,
            "get_action_index_from_actiondict",
            return_value=valid_tokens[:-1],
        ):
            with self.assertRaises(RuntimeError):
                self.converter.convert(case["raw_action"])
        out_of_vocabulary = list(valid_tokens)
        out_of_vocabulary[4] = 9999
        with mock.patch.object(
            self.converter._converter,
            "get_action_index_from_actiondict",
            return_value=out_of_vocabulary,
        ):
            with self.assertRaises(RuntimeError):
                self.converter.convert(case["raw_action"])
        original_vocab = dict(self.converter._converter.action_vocab)
        try:
            self.converter._converter.action_vocab = {
                key: value + 1 for key, value in original_vocab.items()
            }
            with self.assertRaises(RuntimeError):
                self.converter.convert(case["raw_action"])
        finally:
            self.converter._converter.action_vocab = original_vocab
        with mock.patch.object(
            wave2,
            "_git_blob_sha256",
            return_value="0" * 64,
        ):
            with self.assertRaises(RuntimeError):
                wave2._OfficialActionConverter(EXTERNAL_SOURCE)
        for observation in (
            ("0" * 40, True),
            (wave2.PINNED_SOURCE_REVISION, False),
        ):
            with self.subTest(source_observation=observation):
                with mock.patch.object(
                    wave2,
                    "_inspect_source",
                    return_value=observation,
                ):
                    with self.assertRaises(RuntimeError):
                        wave2._OfficialActionConverter(EXTERNAL_SOURCE)

    def test_public_action_boundary_rejects_blank_and_non_object_values(self):
        identity = FrameIdentity(
            schema_version=SCHEMA_VERSION,
            trajectory_id="trajectory",
            model_frame_idx=0,
        )
        for value in ("", "not-json", None, [], 7):
            with self.subTest(value=value):
                with self.assertRaises(MineWorldAdapterError):
                    ActionConversionRequest(identity, 0, value)

    def test_incomplete_and_invalid_official_actions_fail_closed(self):
        case = self.fixture["cases"][0]
        incomplete = dict(case["normalized_action"])
        incomplete.pop("jump")
        invalid_binary = dict(case["normalized_action"])
        invalid_binary["jump"] = 2
        invalid_camera = dict(case["normalized_action"])
        invalid_camera["camera"] = [0]
        for label, normalized in (
            ("incomplete", incomplete),
            ("invalid-binary", invalid_binary),
            ("invalid-camera", invalid_camera),
        ):
            with self.subTest(label=label):
                with mock.patch.object(
                    self.converter._converter,
                    "json_action_to_env_action",
                    return_value=(normalized, False),
                ):
                    with self.assertRaises(EvidenceValidationError):
                        self.converter.convert(case["raw_action"])

    def test_noop_camera_hotbar_controls_and_impulse_are_present(self):
        by_id = {case["case_id"]: case for case in self.fixture["cases"]}
        required = {
            "no_op",
            "camera_yaw",
            "camera_pitch",
            "combined_camera",
            "hotbar_selection",
            "attack",
            "use",
            "drop",
            "pick",
            "opposing_direction",
            "one_tick_causal_impulse",
        }
        self.assertLessEqual(required, set(by_id))
        self.assertTrue(by_id["no_op"]["is_noop"])
        self.assertFalse(by_id["one_tick_causal_impulse"]["is_noop"])


if __name__ == "__main__":
    unittest.main()
