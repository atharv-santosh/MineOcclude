from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mineocclude.experiments.registry import hash_json_value
from tests.experiments.test_registry import registry_bundle
from tests.vision.person_e_test_helpers import add_person_e_run, write_live_config


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _run(*arguments: object) -> None:
    completed = subprocess.run(
        [sys.executable, *(str(argument) for argument in arguments)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)


class TestU4Pipeline(unittest.TestCase):
    def test_detector_homography_composition_reaches_measurement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            config_path = write_live_config(temporary)
            manifest, registry = registry_bundle()
            add_person_e_run(registry, config_path=config_path)
            manifest_path = temporary / "manifest.json"
            registry_path = temporary / "registry.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            registry_path.write_text(json.dumps(registry), encoding="utf-8")

            marker_ids = ["nw", "ne", "se", "sw"]
            homography_input = {
                "homography_input_schema_version": "person-e-homography-input-v0.1",
                "layouts": [
                    {
                        "layout_id": "layout_1",
                        "canonical_camera_pose_id": "pose_1",
                        "marker_set_source_hash": "1" * 64,
                        "validation_source_hash": "2" * 64,
                        "marker_ids": marker_ids,
                        "image_points_by_marker": {
                            "nw": [0, 0],
                            "ne": [4, 0],
                            "se": [4, 4],
                            "sw": [0, 4],
                        },
                        "world_points_by_marker": {
                            "nw": [0, 0],
                            "ne": [4, 0],
                            "se": [4, 4],
                            "sw": [0, 4],
                        },
                        "validation_pairs": [
                            {
                                "image_xy": [1.5, 1.5],
                                "true_world_xz": [1.5, 1.5],
                                "image_region": "center",
                            }
                        ],
                        "wall_parallel_origin_xz": [0, 0],
                        "wall_parallel_positive_unit_xz": [1, 0],
                    }
                ],
            }
            homography_input_path = temporary / "homography_input.json"
            homography_report_path = temporary / "homography_report.json"
            homography_input_path.write_text(
                json.dumps(homography_input), encoding="utf-8"
            )
            _run(
                SCRIPTS / "fit_homographies.py",
                homography_input_path,
                homography_report_path,
                "--config",
                config_path,
                "--producer-run-id",
                "person_e_measurement_run_1",
                "--code-sha",
                "a" * 40,
            )

            black = [[[0, 0, 0] for _ in range(4)] for _ in range(4)]
            magenta = [[[0, 0, 0] for _ in range(4)] for _ in range(4)]
            for y in (1, 2):
                for x in (1, 2):
                    magenta[y][x] = [255, 0, 255]
            frames = []
            for frame_idx, rgb in ((1, black), (2, magenta), (3, magenta)):
                frames.append(
                    {
                        "rollout_id": "rollout_zero",
                        "reveal_frame_idx": 1,
                        "frame_idx": frame_idx,
                        "layout_id": "layout_1",
                        "canonical_camera_pose_id": "pose_1",
                        "source_frame_hash": f"{frame_idx}" * 64,
                        "decoded_rgb_hash": hash_json_value(rgb),
                        "rgb": rgb,
                    }
                )
            frame_input_path = temporary / "frames.json"
            localization_path = temporary / "localization.json"
            frame_input_path.write_text(
                json.dumps(
                    {
                        "u4_frame_input_schema_version": (
                            "person-e-u4-frame-input-v0.1"
                        ),
                        "frames": frames,
                    }
                ),
                encoding="utf-8",
            )
            _run(
                SCRIPTS / "localize_u4_frames.py",
                frame_input_path,
                homography_report_path,
                manifest_path,
                registry_path,
                localization_path,
                "--config",
                config_path,
                "--run-id",
                "person_e_measurement_run_1",
            )
            localization = json.loads(localization_path.read_text(encoding="utf-8"))
            self.assertEqual(
                localization["rows"][0]["localizations"][1][
                    "wall_parallel_blocks"
                ],
                1.5,
            )

            ssim_settings = {
                "algorithm": "global_ssim_per_channel_mean_v0.1",
                "ssim_version": "global-ssim-known-answer-v1",
                "data_range": 255.0,
                "channel_handling": "rgb_per_channel_mean",
                "sample_covariance": True,
                "k1": 0.01,
                "k2": 0.03,
                "background_margin_pixels": 0,
            }
            ssim_report = {
                "ssim_report_schema_version": "person-e-ssim-report-v0.2",
                "accepted_rollout_manifest_hash": localization[
                    "accepted_rollout_manifest_hash"
                ],
                "accepted_registry_hash": localization["accepted_registry_hash"],
                "config_hash": localization["config_hash"],
                "settings_hash": hash_json_value(ssim_settings),
                **ssim_settings,
                "comparisons": [
                    {
                        "comparison_id": "comparison_zero",
                        "pushed_metadata": {
                            "rollout_id": "rollout_zero",
                            "event_id": "event_1",
                            "seed": 7,
                            "rollout_frame_idx": 2,
                            "clip_hash": "1" * 64,
                        },
                        "baseline_metadata": {
                            "rollout_id": "rollout_zero",
                            "clip_hash": "1" * 64,
                        },
                        "ssim_version": "global-ssim-known-answer-v1",
                        "alignment_checked": True,
                        "algorithm": "global_ssim_per_channel_mean_v0.1",
                        "full_frame_ssim": 1.0,
                        "background_masked_ssim": 1.0,
                        "full_frame_pixel_count": 16,
                        "background_pixel_count": 12,
                        "data_range": 255.0,
                        "channel_handling": "rgb_per_channel_mean",
                    }
                ],
            }
            ssim_report_path = temporary / "ssim_report.json"
            composed_path = temporary / "composed.json"
            ssim_report_path.write_text(json.dumps(ssim_report), encoding="utf-8")
            _run(
                SCRIPTS / "compose_u4_evidence.py",
                localization_path,
                ssim_report_path,
                composed_path,
            )

            output_path = temporary / "measurements.json"
            evidence_directory = temporary / "evidence"
            _run(
                SCRIPTS / "measure_u4.py",
                manifest_path,
                registry_path,
                composed_path,
                output_path,
                "--evidence-output-dir",
                evidence_directory,
                "--config",
                config_path,
                "--run-id",
                "person_e_measurement_run_1",
            )
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(output["rows"][0]["measurement_status"], "measured")
            evidence_file = next(evidence_directory.glob("*.json"))
            self.assertEqual(
                output["rows"][0]["measurement_artifact_hash"],
                hashlib.sha256(evidence_file.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
