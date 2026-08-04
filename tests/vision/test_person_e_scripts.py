from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mineocclude.experiments.registry import hash_json_value
from tests.experiments.test_registry import registry_bundle
from tests.vision.person_e_test_helpers import (
    add_person_e_run,
    write_live_config,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


class TestPersonEScripts(unittest.TestCase):
    def test_every_person_e_cli_has_a_working_help_surface(self) -> None:
        scripts = (
            "trace_artifact.py",
            "build_artifact_index.py",
            "evaluate_magenta_detector.py",
            "fit_homographies.py",
            "measure_ssim.py",
            "localize_u4_frames.py",
            "compose_u4_evidence.py",
            "measure_u4.py",
            "build_figure_input.py",
            "render_figure_svg.py",
        )
        for script in scripts:
            with self.subTest(script=script):
                completed = subprocess.run(
                    [sys.executable, str(SCRIPTS / script), "--help"],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("usage:", completed.stdout.lower())

    def test_ssim_cli_records_alignment_and_natural_variation(self) -> None:
        image = [[[100, 100, 100] for _ in range(4)] for _ in range(4)]
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            config_path = write_live_config(temporary)
            manifest, registry = registry_bundle()
            first = manifest["rollout_rows"][0]
            second = copy.deepcopy(first)
            second.update(
                {
                    "rollout_id": "rollout_zero_2",
                    "seed": 8,
                    "dose_id": "dose_zero_2",
                    "output_artifact_id": "clip_zero_2",
                    "output_uri": "memory://rollouts/clip_zero_2",
                    "output_hash": "3" * 64,
                    "run_id": "run_rollout_2",
                }
            )
            registry["runs"].append(
                {
                    **registry["runs"][1],
                    "run_id": "run_rollout_2",
                    "command": ["generate", "--rollout", "rollout_zero_2"],
                    "output_artifact_ids": ["clip_zero_2"],
                }
            )
            registry["artifacts"].append(
                {
                    **registry["artifacts"][-1],
                    "artifact_id": "clip_zero_2",
                    "uri": "memory://rollouts/clip_zero_2",
                    "sha256": "3" * 64,
                    "producer_run_id": "run_rollout_2",
                }
            )
            manifest["rollout_rows"].append(second)
            add_person_e_run(
                registry,
                config_path=config_path,
                run_id="person_e_ssim_run_1",
                input_artifact_ids=["clip_zero", "clip_zero_2"],
            )
            first_metadata = {
                "rollout_id": "rollout_zero",
                "event_id": "event_1",
                "seed": 7,
                "layout_id": "layout_1",
                "rollout_frame_idx": 4,
                "control_type": "alpha_zero",
                "clip_hash": "1" * 64,
            }
            second_metadata = {
                **first_metadata,
                "rollout_id": "rollout_zero_2",
                "seed": 8,
                "clip_hash": "3" * 64,
            }
            document = {
                "comparisons": [
                    {
                        "comparison_id": "comparison_1",
                        "pushed_metadata": first_metadata,
                        "baseline_metadata": first_metadata,
                        "pushed_rgb": image,
                        "baseline_rgb": image,
                        "pushed_box_xyxy": [1, 1, 2, 2],
                        "baseline_box_xyxy": [1, 1, 2, 2],
                    }
                ],
                "natural_variation_pairs": [
                    {
                        "pair_id": "natural_1",
                        "first_metadata": first_metadata,
                        "second_metadata": second_metadata,
                        "first_rgb": image,
                        "second_rgb": image,
                    }
                ],
            }
            input_path = temporary / "ssim_input.json"
            manifest_path = temporary / "manifest.json"
            registry_path = temporary / "registry.json"
            output_path = temporary / "ssim_output.json"
            input_path.write_text(json.dumps(document), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "measure_ssim.py"),
                    str(input_path),
                    str(manifest_path),
                    str(registry_path),
                    str(output_path),
                    "--config",
                    str(config_path),
                    "--run-id",
                    "person_e_ssim_run_1",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(output["comparisons"][0]["full_frame_ssim"], 1.0)
            self.assertEqual(output["natural_variation_summary"]["mean"], 1.0)

    def test_measurement_cli_validates_registry_and_builds_b_handoff(self) -> None:
        manifest, registry = registry_bundle()
        evidence = {
            "measurement_evidence_input_schema_version": (
                "person-e-u4-evidence-input-v0.1"
            ),
            "rows": [
                {
                    "rollout_id": "rollout_zero",
                    "reveal_frame_idx": 1,
                    "layout_id": "layout_1",
                    "canonical_camera_pose_id": "pose_1",
                    "detector_report_hash": "4" * 64,
                    "detector_version": "magenta-known-answer-v1",
                    "homography_report_hash": "5" * 64,
                    "homography_version_id": "homography-known-answer-v1",
                    "localizations": [
                        {
                            "frame_idx": 1,
                            "wall_parallel_blocks": None,
                            "detection_valid": False,
                            "bounding_box_xyxy": None,
                            "rejection_reason": "pre_reveal",
                            "source_frame_hash": "6" * 64,
                            "detector_result_hash": "7" * 64,
                        },
                        {
                            "frame_idx": 2,
                            "wall_parallel_blocks": 4.0,
                            "detection_valid": True,
                            "bounding_box_xyxy": [1, 1, 2, 2],
                            "rejection_reason": None,
                            "source_frame_hash": "8" * 64,
                            "detector_result_hash": "9" * 64,
                        },
                        {
                            "frame_idx": 3,
                            "wall_parallel_blocks": 4.0,
                            "detection_valid": True,
                            "bounding_box_xyxy": [1, 1, 2, 2],
                            "rejection_reason": None,
                            "source_frame_hash": "a" * 64,
                            "detector_result_hash": "b" * 64,
                        },
                    ],
                    "ssim": {
                        "comparison_id": "comparison_zero",
                        "pushed_rollout_id": "rollout_zero",
                        "baseline_rollout_id": "rollout_zero",
                        "event_id": "event_1",
                        "seed": 7,
                        "rollout_frame_idx": 2,
                        "pushed_clip_hash": "1" * 64,
                        "baseline_clip_hash": "1" * 64,
                        "ssim_report_hash": "c" * 64,
                        "settings_hash": "d" * 64,
                        "ssim_version": "global-ssim-known-answer-v1",
                        "alignment_checked": True,
                        "algorithm": "global_ssim_per_channel_mean_v0.1",
                        "full_frame_ssim": 1.0,
                        "background_masked_ssim": 1.0,
                        "full_frame_pixel_count": 16,
                        "background_pixel_count": 15,
                        "data_range": 255.0,
                        "channel_handling": "rgb_per_channel_mean",
                    },
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            manifest_path = temporary / "manifest.json"
            registry_path = temporary / "registry.json"
            evidence_path = temporary / "evidence.json"
            output_path = temporary / "measurements.json"
            evidence_output_dir = temporary / "measurement_evidence"
            config_path = write_live_config(temporary)
            add_person_e_run(registry, config_path=config_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            evidence.update(
                {
                    "accepted_rollout_manifest_hash": hash_json_value(manifest),
                    "accepted_registry_hash": hash_json_value(registry),
                    "config_hash": hashlib.sha256(
                        config_path.read_bytes()
                    ).hexdigest(),
                }
            )
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "measure_u4.py"),
                    str(manifest_path),
                    str(registry_path),
                    str(evidence_path),
                    str(output_path),
                    "--evidence-output-dir",
                    str(evidence_output_dir),
                    "--config",
                    str(config_path),
                    "--run-id",
                    "person_e_measurement_run_1",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(output["producer_role"], "person_e")
            self.assertEqual(output["rows"][0]["measurement_status"], "measured")
            self.assertEqual(output["rows"][0]["displacement_blocks"], 0.0)
            evidence_files = list(evidence_output_dir.glob("*.json"))
            self.assertEqual(len(evidence_files), 1)
            self.assertEqual(
                output["rows"][0]["measurement_artifact_hash"],
                hashlib.sha256(evidence_files[0].read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
