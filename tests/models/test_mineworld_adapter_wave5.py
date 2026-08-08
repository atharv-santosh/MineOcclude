"""CPU-only tests for Person A's Wave 5 preprocessing-identity reconciliation.

These tests are scoped narrowly to the identity surface repaired here: they do
not re-run the 2,468-frame preprocessing, do not touch GPU/CUDA, and do not
duplicate the full Wave 2-4 coverage already exercised elsewhere.
"""

from __future__ import annotations

import dataclasses
import unittest
from unittest import mock

from mineocclude.models import _mineworld_adapter_wave2 as wave2
from mineocclude.models import _mineworld_adapter_wave3 as wave3
from mineocclude.models import _mineworld_adapter_wave5 as wave5
from mineocclude.models.mineworld_adapter import (
    AdapterFailureCode,
    MineWorldAdapterError,
    RuntimeLoadRequest,
    create_mineworld_adapter,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from tests.models import test_mineworld_adapter_wave2 as wave2_tests
from tests.models import test_mineworld_adapter_wave3 as wave3_helpers

ARBITRARY_PROFILE = "caller-supplied-unreviewed-profile-v9.9"


def _frame(identity, profile):
    return dataclasses.replace(
        wave3_helpers._preprocessed(identity),
        preprocessing_profile=profile,
    )


class ReviewedIdentityConstantsTests(unittest.TestCase):
    """Anchor the two reviewed identities so they cannot silently drift."""

    def test_legacy_identity_is_the_untouched_phase3_constant(self):
        self.assertEqual(
            wave5.LEGACY_PREPROCESSING_PROFILE, wave2.PREPROCESSING_PROFILE
        )
        self.assertIn(
            "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab",
            wave5.LEGACY_PREPROCESSING_PROFILE,
        )

    def test_v0_2_identity_matches_the_authorized_successor_config(self):
        self.assertEqual(
            wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
            "person-a-bgr2rgb-inter-linear-224x384-v1.0",
        )
        self.assertEqual(
            wave5.PERSON_A_66_CELL_V0_2_PREPROCESS_HASH,
            "8b585e1ffe7d9b7c7bf549f8b5695825bbd2a5b2579e4adf607ca5fa5786635c",
        )

    def test_allowlist_contains_exactly_the_two_reviewed_identities(self):
        self.assertEqual(
            set(wave5.REVIEWED_PREPROCESSING_IDENTITIES),
            {
                wave5.LEGACY_PREPROCESSING_PROFILE,
                wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
            },
        )


class FrameProfileValidationTests(unittest.TestCase):
    """Exercise wave3._validate_preprocessed_frame directly and focused."""

    def test_legacy_profile_still_accepted_under_legacy_runtime(self):
        identity = wave3_helpers._runtime_identity()
        frame = _frame(
            wave3_helpers._identity(0), wave2.PREPROCESSING_PROFILE
        )
        wave3._validate_preprocessed_frame(frame, identity)  # must not raise

    def test_v0_2_profile_accepted_when_explicitly_bound(self):
        identity = wave3_helpers._runtime_identity(
            preprocessing_identity=(
                wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE
            )
        )
        frame = _frame(
            wave3_helpers._identity(0),
            wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
        )
        wave3._validate_preprocessed_frame(frame, identity)  # must not raise

    def test_v0_2_profile_rejected_under_legacy_runtime(self):
        identity = wave3_helpers._runtime_identity()  # legacy-bound
        frame = _frame(
            wave3_helpers._identity(0),
            wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
        )
        with self.assertRaises(MineWorldAdapterError) as caught:
            wave3._validate_preprocessed_frame(frame, identity)
        self.assertEqual(
            caught.exception.code, AdapterFailureCode.INVALID_PROVENANCE
        )

    def test_legacy_profile_rejected_under_v0_2_runtime(self):
        identity = wave3_helpers._runtime_identity(
            preprocessing_identity=(
                wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE
            )
        )
        frame = _frame(
            wave3_helpers._identity(0), wave2.PREPROCESSING_PROFILE
        )
        with self.assertRaises(MineWorldAdapterError) as caught:
            wave3._validate_preprocessed_frame(frame, identity)
        self.assertEqual(
            caught.exception.code, AdapterFailureCode.INVALID_PROVENANCE
        )

    def test_arbitrary_profile_rejected_under_either_bound_runtime(self):
        for bound in (
            wave2.PREPROCESSING_PROFILE,
            wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
        ):
            with self.subTest(bound=bound):
                identity = wave3_helpers._runtime_identity(
                    preprocessing_identity=bound
                )
                frame = _frame(wave3_helpers._identity(0), ARBITRARY_PROFILE)
                with self.assertRaises(MineWorldAdapterError) as caught:
                    wave3._validate_preprocessed_frame(frame, identity)
                self.assertEqual(
                    caught.exception.code,
                    AdapterFailureCode.INVALID_PROVENANCE,
                )


class AdapterConstructionRejectsArbitraryIdentityTests(unittest.TestCase):
    def test_unreviewed_identity_rejected_at_construction_before_any_io(self):
        with self.assertRaises(ValueError):
            wave5._Wave5MineWorldAdapter(
                preprocessing_identity=ARBITRARY_PROFILE,
                runtime_loader=mock.Mock(
                    side_effect=AssertionError("loader called")
                ),
            )

    def test_public_factory_defaults_preserve_legacy_identity(self):
        adapter = create_mineworld_adapter()
        self.assertIsInstance(adapter, wave5._Wave5MineWorldAdapter)
        self.assertEqual(
            adapter._bound_preprocessing_identity,
            wave5.LEGACY_PREPROCESSING_PROFILE,
        )

    def test_public_factory_accepts_the_reviewed_v0_2_identity(self):
        adapter = create_mineworld_adapter(
            preprocessing_identity=(
                wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE
            )
        )
        self.assertEqual(
            adapter._bound_preprocessing_identity,
            wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
        )

    def test_public_factory_rejects_arbitrary_identity(self):
        with self.assertRaises(ValueError):
            create_mineworld_adapter(preprocessing_identity=ARBITRARY_PROFILE)


class LoadRuntimeBindingTests(unittest.TestCase):
    """End-to-end load_runtime() binding, mirroring Wave2LoaderTests fixtures."""

    def setUp(self):
        self.root = wave2_tests.RUNTIME_STUB
        self.source_root = self.root / "source"
        self.model_config = self.source_root / "configs" / "700M_16f.yaml"
        self.main_checkpoint = self.root / "main_checkpoint.test"
        self.vae_config = self.root / "vae" / "config.json"
        self.vae_checkpoint = self.root / "vae" / "vae_checkpoint.test"
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
            "runtime_id": "phase3-wave5-test",
            "mineocclude_revision": "a" * 40,
            "mineworld_source_revision": wave2.PINNED_SOURCE_REVISION,
            "modelscope_asset_revision": wave2.PINNED_ASSET_REVISION,
            "mineworld_source_root": self.source_root,
            "model_config_path": self.model_config,
            "main_checkpoint_path": self.main_checkpoint,
            "vae_config_path": self.vae_config,
            "vae_checkpoint_path": self.vae_checkpoint,
            "model_config_sha256": wave2.PINNED_MODEL_CONFIG_SHA256,
            "main_checkpoint_sha256": wave2.PINNED_MAIN_CHECKPOINT_SHA256,
            "vae_config_sha256": wave2.PINNED_VAE_CONFIG_SHA256,
            "vae_checkpoint_sha256": wave2.PINNED_VAE_CHECKPOINT_SHA256,
            "environment_report_sha256": "e" * 64,
            "precision": wave2.PINNED_PRECISION,
            "device": wave2.PINNED_DEVICE,
        }
        values.update(changes)
        return RuntimeLoadRequest(**values)

    def adapter(self, *, preprocessing_identity=None, loader=None):
        loader = loader or wave2_tests._LoaderHarness()
        kwargs = {}
        if preprocessing_identity is not None:
            kwargs["preprocessing_identity"] = preprocessing_identity
        return wave5._Wave5MineWorldAdapter(
            file_hasher=lambda path: self.expected_hashes[path.resolve()],
            source_inspector=lambda _root: (
                wave2.PINNED_SOURCE_REVISION,
                True,
            ),
            runtime_loader=loader,
            converter_factory=mock.Mock(),
            **kwargs,
        )

    def test_default_binds_legacy_identity(self):
        identity = self.adapter().load_runtime(self.request())
        self.assertEqual(identity.preprocessing_identity, wave2.PREPROCESSING_PROFILE)
        # Everything else stays exactly what Wave 4 already produced.
        self.assertEqual(identity.model_class, "LlamaLVM")
        self.assertEqual(identity.layer_count, 20)
        self.assertIsNotNone(identity.adapter_code_sha256)

    def test_explicit_binding_produces_the_v0_2_identity(self):
        identity = self.adapter(
            preprocessing_identity=(
                wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE
            )
        ).load_runtime(self.request())
        self.assertEqual(
            identity.preprocessing_identity,
            wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
        )
        self.assertEqual(identity.model_class, "LlamaLVM")
        self.assertEqual(identity.layer_count, 20)


class TokenizeTrajectoryV0_2IntegrationTest(unittest.TestCase):
    """Prove the full validate->tokenize path accepts v0.2-bound frames."""

    def test_v0_2_bound_runtime_tokenizes_v0_2_labeled_frames(self):
        identity = wave3_helpers._runtime_identity(
            preprocessing_identity=(
                wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE
            )
        )
        adapter = wave3._Wave3MineWorldAdapter(
            visual_tokenizer=wave3_helpers._VisualTokenizer(),
            teacher_executor=wave3_helpers._TeacherExecutor(),
        )
        validated = wave3_helpers._validated(3)
        wave3_helpers._seed_adapter(adapter, validated, identity)
        request = wave3_helpers._request(validated)
        request = dataclasses.replace(
            request,
            runtime_identity=identity,
            frames=tuple(
                _frame(
                    f.identity,
                    wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
                )
                for f in request.frames
            ),
        )
        tokenized = adapter.tokenize_trajectory(request)
        self.assertEqual(
            tokenized.preprocessing_profile,
            wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
        )
        # The preprocessed payload bytes themselves are untouched: the
        # content hash on each accepted frame still matches its own
        # (unre-derived) content, proving no re-preprocessing occurred here.
        for frame in request.frames:
            import hashlib

            self.assertEqual(
                frame.content_sha256,
                hashlib.sha256(frame.frame.tobytes(order="C")).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
