from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from mineocclude.vision.config import DEFAULT_PERSON_E_CONFIG_PATH


TEST_CODE_SHA = "a" * 40


def write_live_config(directory: Path) -> Path:
    config = json.loads(DEFAULT_PERSON_E_CONFIG_PATH.read_text(encoding="utf-8"))
    config["status"] = "calibrated_live_ready"
    config["config_instance_version"] = "person-e-phase1-live-known-answer-v0.1"
    detector = config["detector"]
    detector.update(
        {
            "threshold_status": "frozen_calibration_only",
            "threshold_version": "magenta-known-answer-v1",
            "calibration_dataset_hash": "1" * 64,
            "heldout_report_hash": "2" * 64,
            "hsv_ranges": [
                {
                    "h_min": 280.0,
                    "h_max": 320.0,
                    "s_min": 0.5,
                    "s_max": 1.0,
                    "v_min": 0.5,
                    "v_max": 1.0,
                }
            ],
        }
    )
    detector["blob"]["min_area_pixels"] = 1
    detector["blob"]["max_area_pixels"] = 10_000
    ssim = config["ssim"]
    ssim["ssim_version"] = "global-ssim-known-answer-v1"
    ssim["background_mask_margin_pixels"] = 0
    ssim["mask_status"] = "frozen_person_b_person_e_signed"
    path = directory / "person_e_live_config.json"
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def add_person_e_run(
    registry: dict[str, Any],
    *,
    config_path: Path,
    run_id: str = "person_e_measurement_run_1",
    input_artifact_ids: list[str] | None = None,
) -> None:
    template = registry["runs"][-1]
    registry["runs"].append(
        {
            "run_id": run_id,
            "command": ["person-e-known-answer"],
            "owner": "person_e",
            "parent_run_id": template["run_id"],
            "input_artifact_ids": (
                list(template["output_artifact_ids"])
                if input_artifact_ids is None
                else input_artifact_ids
            ),
            "output_artifact_ids": [],
            "code_sha": TEST_CODE_SHA,
            "config_hash": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "model_hash": template["model_hash"],
            "preprocess_hash": template["preprocess_hash"],
            "execution_status": "completed",
            "failure_reason": None,
        }
    )


def clone_rollout(row: dict[str, Any], **updates: Any) -> dict[str, Any]:
    cloned = copy.deepcopy(row)
    cloned.update(updates)
    return cloned
