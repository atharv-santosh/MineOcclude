from __future__ import annotations

import dataclasses
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts" / "run_person_a_phase6_single_pilot_sagemaker.py"
C_PACKAGE = (
    ROOT.parent
    / "MineOcclude-Person-C-C1-C6A"
    / "docs/status/person_c_c6a_completion_v0_1/package_manifest.json"
)
E_ROOT = (
    ROOT.parent
    / "MineOcclude-Person-E-Refit"
    / "docs/status/person_e_c6a_provenance_closure_v0_1"
)
E_HANDOFF = E_ROOT / "person_e_to_person_a_c6a_provenance_handoff.json"
E_REGISTRY = E_ROOT / "canonical_registry_records.json"


def _load_runner():
    specification = importlib.util.spec_from_file_location(
        "person_a_canonical_c6a_launcher_v0_1",
        RUNNER_PATH,
    )
    if specification is None or specification.loader is None:
        raise AssertionError("runner module specification is unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


runner = _load_runner()


def _arguments(**changes):
    defaults = {
        "repository_root": ROOT,
        "mineworld_root": ROOT.parent / "MineWorld-Upstream",
        "asset_root": ROOT.parent / "MineWorld-Assets-Pinned",
        "main_checkpoint": (
            ROOT.parent / "MineWorld-Assets-Pinned/checkpoints/700M_16f.ckpt"
        ),
        "vae_config": (
            ROOT.parent / "MineWorld-Assets-Pinned/checkpoints/vae/config.json"
        ),
        "vae_checkpoint": (
            ROOT.parent / "MineWorld-Assets-Pinned/checkpoints/vae/vae.ckpt"
        ),
        "approved_input_root": ROOT.parent / "canonical-launcher-test-input-absent",
        "approved_output_root": ROOT.parent / "canonical-launcher-test-output-absent",
        "activation_store_v2_ratification_object": "",
        "session_id": "person-a-canonical-c6a-layout-01-ep12602-seed-20260725",
        "seed": 20260725,
        "device": "cuda:0",
        "precision": "float16",
        "runtime_host": "windows_cuda",
        "canonical_c6a_package": C_PACKAGE,
        "canonical_c6a_package_sha256": (
            "612b03fea372d10c5f5b87cb581dd5f993035112e16aa1de7341801bdc35a9ef"
        ),
        "trajectory_id": "layout_01_ep12602",
        "episode_id": 12602,
        "episode_artifact_manifest": E_REGISTRY,
        "episode_artifact_manifest_sha256": (
            "77c105176bdb4d93382b36b3131267848acab6fbdc181f1d8272080e0ad5d588"
        ),
        "person_e_provenance_handoff": E_HANDOFF,
        "person_e_provenance_handoff_sha256": (
            "e2897aac65a8b51893f1ef397af26cdc7958fe89e6d2bd0159082a9547d253d1"
        ),
        "ffmpeg": Path(
            r"C:\ffmpeg-2025-11-17-git-e94439e49b-full_build\bin\ffmpeg.exe"
        ),
        "ffprobe": Path(
            r"C:\ffmpeg-2025-11-17-git-e94439e49b-full_build\bin\ffprobe.exe"
        ),
    }
    defaults.update(changes)
    return runner.RunnerArguments(**defaults)


class CanonicalC6ALauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        required = (C_PACKAGE, E_HANDOFF, E_REGISTRY)
        if not all(path.is_file() for path in required):
            raise unittest.SkipTest("canonical C6A authority worktrees are unavailable")

    def test_historical_pilot_defaults_are_preserved(self) -> None:
        plan = runner.plan_document()
        self.assertEqual(plan["selected_pilot"], "layout_00_ep9403")
        self.assertEqual(plan["global_model_frame_count"], 248)
        self.assertEqual(plan["expected_activation_rows"], 4960)
        self.assertEqual(runner.RunnerArguments.__dataclass_fields__["runtime_host"].default,
                         "aws_sagemaker_linux_gpu")
        self.assertIsNone(
            runner.RunnerArguments.__dataclass_fields__["canonical_c6a_package"].default
        )

    def test_manifest_binding_accepts_exact_selected_pilot(self) -> None:
        binding = runner.load_canonical_pilot_binding(_arguments())
        self.assertEqual(binding.trajectory_id, "layout_01_ep12602")
        self.assertEqual(binding.episode_id, 12602)
        self.assertEqual(binding.frame_count, 60)
        self.assertEqual(len(binding.direct_artifacts), 67)
        self.assertEqual(binding.expected_activation_rows, 1200)
        self.assertTrue(all(path.is_file() for path in binding.frame_paths))

    def test_parser_accepts_all_canonical_identity_parameters(self) -> None:
        namespace = runner._parser().parse_args(
            [
                "run",
                "--mineworld-root", str(ROOT.parent / "MineWorld-Upstream"),
                "--asset-root", str(ROOT.parent / "MineWorld-Assets-Pinned"),
                "--main-checkpoint", str(_arguments().main_checkpoint),
                "--vae-config", str(_arguments().vae_config),
                "--vae-checkpoint", str(_arguments().vae_checkpoint),
                "--approved-input-root", str(_arguments().approved_input_root),
                "--approved-output-root", str(_arguments().approved_output_root),
                "--runtime-host", "windows_cuda",
                "--canonical-c6a-package", str(C_PACKAGE),
                "--canonical-c6a-package-sha256",
                _arguments().canonical_c6a_package_sha256,
                "--trajectory-id", "layout_01_ep12602",
                "--episode-id", "12602",
                "--episode-artifact-manifest", str(E_REGISTRY),
                "--episode-artifact-manifest-sha256",
                _arguments().episode_artifact_manifest_sha256,
                "--person-e-provenance-handoff", str(E_HANDOFF),
                "--person-e-provenance-handoff-sha256",
                _arguments().person_e_provenance_handoff_sha256,
                "--ffmpeg", str(_arguments().ffmpeg),
                "--ffprobe", str(_arguments().ffprobe),
            ]
        )
        parsed = runner._arguments(namespace)
        self.assertTrue(parsed.canonical_mode)
        self.assertEqual(parsed.trajectory_id, "layout_01_ep12602")
        self.assertEqual(parsed.episode_id, 12602)
        self.assertEqual(parsed.expected_hook_site, runner.HOOK_SITE)
        self.assertEqual(
            parsed.expected_activation_store_format,
            runner.ACTIVATION_STORE_V2_FORMAT_VERSION,
        )

    def test_authority_hash_mismatch_is_fail_closed(self) -> None:
        arguments = dataclasses.replace(
            _arguments(),
            canonical_c6a_package_sha256="0" * 64,
        )
        with self.assertRaises(runner.Phase6RunnerError) as caught:
            runner.load_canonical_pilot_binding(arguments)
        self.assertEqual(caught.exception.code, "c6a_package_hash_mismatch")

    def test_canonical_streams_validate_without_extraction(self) -> None:
        binding = runner.load_canonical_pilot_binding(_arguments())
        streams = runner._canonical_streams(binding)
        self.assertEqual({len(rows) for rows in streams.values()}, {60})
        self.assertEqual(
            [row["model_frame_idx"] for row in streams["frame_map"]],
            list(range(60)),
        )
        self.assertTrue(
            all(row["visibility"] == "visible" for row in streams["visibility"])
        )
        self.assertTrue(
            all("source_server_state_row_sha256" in row
                for row in streams["server_state"])
        )
        contract = __import__(
            "mineocclude.contracts.trajectory",
            fromlist=["validate_trajectory_package"],
        )
        package = {
            "artifacts": {
                name: {"format": format_, "path": name, "sha256": "0" * 64}
                for name, format_ in contract.EXPECTED_ARTIFACT_FORMATS.items()
            },
            "episode_id": str(binding.episode_id),
            "impulse_orientation": runner.CANONICAL_IMPULSE_ORIENTATION,
            "media": {
                "fps": 20.0,
                "frame_count": 60,
                "height": 360,
                "mode": "mp4",
                "path": "canonical.mp4",
                "sha256": "0" * 64,
                "width": 640,
            },
            "schema_version": "1.0",
            "seed": binding.state_rows[0]["seed"],
            "streams": streams,
            "trajectory_id": binding.trajectory_id,
        }
        self.assertTrue(contract.validate_trajectory_package(package).accepted)

    def test_canonical_constant_binding_restores_historical_values(self) -> None:
        binding = runner.load_canonical_pilot_binding(_arguments())
        with runner._canonical_pilot_constants(binding):
            self.assertEqual(runner.SELECTED_PILOT, "layout_01_ep12602")
            self.assertEqual(runner.GLOBAL_MODEL_FRAME_COUNT, 60)
            self.assertEqual(runner.EXPECTED_ACTIVATION_ROW_COUNT, 1200)
        self.assertEqual(runner.SELECTED_PILOT, "layout_00_ep9403")
        self.assertEqual(runner.GLOBAL_MODEL_FRAME_COUNT, 248)
        self.assertEqual(runner.EXPECTED_ACTIVATION_ROW_COUNT, 4960)

    def test_create_only_roots_are_checked_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            missing_input = parent / "input"
            missing_output = parent / "output"
            arguments = dataclasses.replace(
                _arguments(),
                approved_input_root=missing_input,
                approved_output_root=missing_output,
            )
            runner._validate_create_only_roots(arguments)
            self.assertFalse(missing_input.exists())
            self.assertFalse(missing_output.exists())
            missing_output.mkdir()
            with self.assertRaises(runner.Phase6RunnerError) as caught:
                runner._validate_create_only_roots(arguments)
            self.assertEqual(caught.exception.code, "output_exists")

    def test_expected_scientific_identity_mismatch_fails(self) -> None:
        with self.assertRaises(runner.Phase6RunnerError) as caught:
            runner._validate_runtime_arguments(
                dataclasses.replace(
                    _arguments(),
                    expected_hook_site="different_hook",
                )
            )
        self.assertEqual(caught.exception.code, "scientific_identity_mismatch")

    def test_cuda_preflight_requires_visible_capacity(self) -> None:
        class UnavailableCuda:
            @staticmethod
            def is_available():
                return False

            @staticmethod
            def device_count():
                return 0

        class UnavailableTorch:
            cuda = UnavailableCuda()

        with self.assertRaises(runner.Phase6RunnerError) as caught:
            runner.cuda_preflight(UnavailableTorch())
        self.assertEqual(caught.exception.code, "cuda_unavailable")

        class Properties:
            name = "bounded-test-gpu"
            total_memory = runner.MINIMUM_GPU_MEMORY_BYTES

        class AvailableCuda:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def device_count():
                return 1

            @staticmethod
            def get_device_properties(_index):
                return Properties()

            @staticmethod
            def set_device(_index):
                return None

            @staticmethod
            def current_device():
                return 0

        class Version:
            cuda = "test"

        class AvailableTorch:
            cuda = AvailableCuda()
            version = Version()

        receipt = runner.cuda_preflight(AvailableTorch())
        self.assertTrue(receipt["available"])
        self.assertEqual(receipt["device"], "cuda:0")

    def test_model_asset_preflight_binds_all_four_identities(self) -> None:
        config = b"exact model config"
        arguments = dataclasses.replace(
            _arguments(),
            expected_model_config_sha256=runner._sha256_bytes(config),
        )
        hashes = {
            arguments.main_checkpoint: arguments.expected_main_checkpoint_sha256,
            arguments.vae_config: arguments.expected_vae_config_sha256,
            arguments.vae_checkpoint: arguments.expected_vae_checkpoint_sha256,
        }
        with mock.patch.object(
            runner,
            "_git_object_bytes",
            return_value=config,
        ), mock.patch.object(
            runner,
            "_sha256_file",
            side_effect=lambda path: hashes[path],
        ):
            observed_config, observed_hashes = runner.model_assets_preflight(arguments)
        self.assertEqual(observed_config, config)
        self.assertEqual(
            observed_hashes,
            {
                "main_checkpoint": arguments.expected_main_checkpoint_sha256,
                "vae_config": arguments.expected_vae_config_sha256,
                "vae_checkpoint": arguments.expected_vae_checkpoint_sha256,
            },
        )


if __name__ == "__main__":
    unittest.main()
