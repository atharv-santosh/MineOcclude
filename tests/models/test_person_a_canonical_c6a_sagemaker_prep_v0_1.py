from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/run_person_a_phase6_single_pilot_sagemaker.py"
PREP_PATH = ROOT / "scripts/prepare_person_a_phase6_canonical_sagemaker.py"
WRAPPER_PATH = ROOT / "scripts/run_person_a_phase6_single_pilot_sagemaker.sh"
BUNDLE_ROOT = (
    ROOT / "data/handoff_a/person_a_canonical_c6a_sagemaker_input_v0_1"
)
BUNDLE_MANIFEST = BUNDLE_ROOT / "bundle_manifest.json"
BUNDLE_SHA256 = "d79b86fe8564f4235414cda09a648df73849ec8ffe1e9c3bceb00055c19ec950"
C6A_SHA256 = "612b03fea372d10c5f5b87cb581dd5f993035112e16aa1de7341801bdc35a9ef"
REGISTRY_SHA256 = "77c105176bdb4d93382b36b3131267848acab6fbdc181f1d8272080e0ad5d588"
E_HANDOFF_SHA256 = "e2897aac65a8b51893f1ef397af26cdc7958fe89e6d2bd0159082a9547d253d1"


def _load(path: Path, name: str):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise AssertionError(f"module unavailable: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


runner = _load(RUNNER_PATH, "person_a_canonical_sagemaker_runner_test")
prep = _load(PREP_PATH, "person_a_canonical_sagemaker_prep_test")


def _staged_arguments():
    placeholder = RUNNER_PATH
    return runner.RunnerArguments(
        repository_root=ROOT,
        mineworld_root=ROOT,
        asset_root=ROOT,
        main_checkpoint=placeholder,
        vae_config=placeholder,
        vae_checkpoint=placeholder,
        approved_input_root=ROOT,
        approved_output_root=ROOT.parent,
        activation_store_v2_ratification_object="",
        session_id="test",
        seed=20260725,
        device="cuda:0",
        precision="float16",
        runtime_host="aws_sagemaker_linux_gpu",
        canonical_c6a_package_sha256=C6A_SHA256,
        trajectory_id="layout_01_ep12602",
        episode_id=12602,
        episode_artifact_manifest_sha256=REGISTRY_SHA256,
        person_e_provenance_handoff_sha256=E_HANDOFF_SHA256,
        canonical_input_bundle_manifest=BUNDLE_MANIFEST,
        canonical_input_bundle_manifest_sha256=BUNDLE_SHA256,
    )


class CanonicalC6ASageMakerPreparationTests(unittest.TestCase):
    def test_staged_manifest_is_exact_and_contains_only_selected_artifacts(self) -> None:
        self.assertEqual(
            hashlib.sha256(BUNDLE_MANIFEST.read_bytes()).hexdigest(),
            BUNDLE_SHA256,
        )
        manifest = json.loads(BUNDLE_MANIFEST.read_bytes())
        self.assertEqual(manifest["trajectory_id"], "layout_01_ep12602")
        self.assertEqual(manifest["episode_id"], 12602)
        self.assertEqual(len(manifest["direct_artifacts"]), 67)
        self.assertEqual(len(manifest["files"]), 73)
        self.assertTrue(
            all(
                row["source"]["path"].lower().find("episode_12602") >= 0
                for row in manifest["direct_artifacts"]
            )
        )
        self.assertEqual(
            manifest["authority"]["episode_registry_record"][
                "source_manifest_sha256"
            ],
            REGISTRY_SHA256,
        )

    def test_staged_bundle_hash_preflight_and_identity_join_pass(self) -> None:
        binding = runner.load_staged_canonical_pilot_binding(_staged_arguments())
        self.assertEqual(binding.trajectory_id, "layout_01_ep12602")
        self.assertEqual(binding.frame_count, 60)
        self.assertEqual(binding.expected_activation_rows, 1200)
        self.assertEqual(len(binding.direct_artifacts), 67)
        with self.assertRaises(runner.Phase6RunnerError) as caught:
            runner.load_staged_canonical_pilot_binding(
                runner.dataclasses.replace(
                    _staged_arguments(),
                    canonical_input_bundle_manifest_sha256="0" * 64,
                )
            )
        self.assertEqual(caught.exception.code, "input_bundle_hash_mismatch")

    def test_existing_sagemaker_wrapper_preserves_historical_and_adds_canonical(self) -> None:
        wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertIn("PERSON_A_CANONICAL_SAGEMAKER_BUNDLE_MANIFEST", wrapper)
        self.assertIn("--runtime-host aws_sagemaker_linux_gpu", wrapper)
        self.assertIn("--trajectory-id layout_01_ep12602", wrapper)
        self.assertIn("--episode-id 12602", wrapper)
        self.assertIn("--seed 20260725", wrapper)
        self.assertIn("--precision float16", wrapper)
        self.assertIn("collect-output", wrapper)
        self.assertIn("git push origin role/person-a-model", wrapper)
        self.assertIn("person-a-phase6-layout-00-ep9403-seed-20260725", wrapper)
        self.assertIn("PERSON_B_ACTIVATION_STORE_V2_RATIFICATION_OBJECT", wrapper)

    def test_sagemaker_create_only_guard_checks_session_and_store(self) -> None:
        arguments = runner.RunnerArguments(
            repository_root=runner.EXPECTED_SAGEMAKER_REPOSITORY_ROOT,
            mineworld_root=runner.EXPECTED_SAGEMAKER_MINEWORLD_ROOT,
            asset_root=runner.EXPECTED_SAGEMAKER_ASSET_ROOT,
            main_checkpoint=(
                runner.EXPECTED_SAGEMAKER_ASSET_ROOT / "checkpoints/700M_16f.ckpt"
            ),
            vae_config=(
                runner.EXPECTED_SAGEMAKER_ASSET_ROOT / "checkpoints/vae/config.json"
            ),
            vae_checkpoint=(
                runner.EXPECTED_SAGEMAKER_ASSET_ROOT / "checkpoints/vae/vae.ckpt"
            ),
            approved_input_root=runner.EXPECTED_SAGEMAKER_INPUT_ROOT,
            approved_output_root=runner.EXPECTED_SAGEMAKER_OUTPUT_ROOT,
            activation_store_v2_ratification_object="",
            session_id="person-a-canonical-c6a-layout-01-ep12602-seed-20260725",
            seed=20260725,
            device="cuda:0",
            precision="float16",
            ffmpeg=runner.EXPECTED_SAGEMAKER_FFMPEG,
            ffprobe=runner.EXPECTED_SAGEMAKER_FFPROBE,
        )
        with mock.patch.object(Path, "is_dir", return_value=True), mock.patch.object(
            Path, "is_symlink", return_value=False
        ), mock.patch.object(Path, "exists", return_value=False):
            runner._validate_sagemaker_canonical_paths(arguments)

    def test_output_collection_emits_complete_retrieval_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "input"
            session_root = root / "session"
            activation_root = root / "activation"
            destination = root / "retrieved"
            input_root.mkdir()
            session_root.mkdir()
            (session_root / "bounded_audit").mkdir()
            (activation_root / "chunks").mkdir(parents=True)
            (activation_root / "indexes").mkdir()
            (input_root / "accepted_pilot_manifest.json").write_text(
                json.dumps(
                    {
                        "selected_episode_id": 12610,
                        "selected_trajectory_id": "layout_02_ep12610",
                    }
                ),
                encoding="utf-8",
            )
            final_report = {"selected_pilot": "layout_02_ep12610", "status": "PASS"}
            step6_5 = {
                "result": {
                    "direct_pooling_audit": "PASS",
                    "repeatability_maximum_absolute_difference": 0.0,
                    "source_identity_join_failure_count": 0,
                    "status": "PASS",
                }
            }
            terminal_index = activation_root / "indexes/index-terminal.json"
            prior_index = activation_root / "indexes/index-prior.json"
            required = {
                "final_report.json": final_report,
                "step6_5.json": step6_5,
                "person_a_to_person_b_canonical_pilot_handoff.json": {},
                "person_a_to_person_e_canonical_provenance_handoff.json": {},
                "runtime_preflight_receipt.json": {},
                "step6_1.json": {},
                "step6_2.json": {},
                "step6_3.json": {},
                "step6_4.json": {
                    "result": {
                        "activation_index_path": str(terminal_index),
                        "chunk_count": 1,
                        "status": "PASS",
                    }
                },
                "step6_6_handoff.json": {},
            }
            for name, document in required.items():
                (session_root / name).write_text(
                    json.dumps(document), encoding="utf-8"
                )
            (session_root / "bounded_audit/audit.npz").write_bytes(b"audit")
            (session_root / "bounded_audit/audit.manifest.json").write_text(
                "{}", encoding="utf-8"
            )
            (activation_root / "chunks/chunk.npy").write_bytes(b"chunk")
            terminal_index.write_text("{}", encoding="utf-8")
            prior_index.write_text("{}", encoding="utf-8")
            namespace = mock.Mock(
                input_session_root=input_root,
                output_session_root=session_root,
                activation_store_root=activation_root,
                destination=destination,
                episode_id=12610,
                trajectory_id="layout_02_ep12610",
            )
            result = prep.collect_output(namespace)
            self.assertEqual(result["status"], "PASS")
            output_manifest = json.loads(
                (destination / "output_bundle_manifest.json").read_bytes()
            )
            self.assertEqual(output_manifest["episode_id"], 12610)
            self.assertEqual(
                output_manifest["trajectory_id"], "layout_02_ep12610"
            )
            self.assertTrue((destination / "sha256_inventory.json").is_file())
            self.assertTrue((destination / "terminal_execution_receipt.json").is_file())
            self.assertTrue((destination / "activation_store/chunks/chunk.npy").is_file())
            self.assertTrue(
                (destination / "activation_store/indexes/index-terminal.json").is_file()
            )
            self.assertFalse(
                (destination / "activation_store/indexes/index-prior.json").exists()
            )
            verified = prep.verify_output(mock.Mock(bundle_root=destination))
            self.assertEqual(verified["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
