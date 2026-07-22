"""Join localization and SSIM reports into the strict U4 evidence input."""

from __future__ import annotations

import argparse
import copy
import sys
from collections.abc import Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (  # noqa: E402
    hash_json_value,
    load_json_with_sha256,
    write_json_exclusive,
)
from mineocclude.vision.measurement import (  # noqa: E402
    EVIDENCE_INPUT_SCHEMA_VERSION,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compose immutable localization and SSIM reports for measure_u4."
    )
    parser.add_argument("localization_report", type=Path)
    parser.add_argument("ssim_report", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping.")
    return value


def main() -> None:
    args = parse_args()
    localization, localization_hash = load_json_with_sha256(
        args.localization_report
    )
    ssim, ssim_hash = load_json_with_sha256(args.ssim_report)
    localization = _mapping(localization, "localization report")
    ssim = _mapping(ssim, "SSIM report")
    if (
        localization.get("localization_report_schema_version")
        != "person-e-localization-report-v0.1"
    ):
        raise ValueError("Unknown localization-report schema version.")
    if (
        localization.get("measurement_evidence_input_schema_version")
        != EVIDENCE_INPUT_SCHEMA_VERSION
    ):
        raise ValueError("Localization report has the wrong evidence schema.")
    if ssim.get("ssim_report_schema_version") != "person-e-ssim-report-v0.2":
        raise ValueError("Unknown SSIM-report schema version.")
    settings = {
        field: ssim.get(field)
        for field in (
            "algorithm",
            "ssim_version",
            "data_range",
            "channel_handling",
            "sample_covariance",
            "k1",
            "k2",
            "background_margin_pixels",
        )
    }
    if ssim.get("settings_hash") != hash_json_value(settings):
        raise ValueError("SSIM settings_hash does not match report settings.")
    for field in (
        "accepted_rollout_manifest_hash",
        "registry_hash",
        "config_hash",
    ):
        if localization.get(field) != ssim.get(field):
            raise ValueError(f"Localization and SSIM reports disagree on {field}.")

    comparisons = ssim.get("comparisons")
    if not isinstance(comparisons, list):
        raise ValueError("SSIM report requires comparisons.")
    comparison_by_rollout: dict[str, Mapping[str, object]] = {}
    for raw_comparison in comparisons:
        comparison = _mapping(raw_comparison, "SSIM comparison")
        pushed = _mapping(comparison.get("pushed_metadata"), "pushed metadata")
        for field in (
            "algorithm",
            "ssim_version",
            "data_range",
            "channel_handling",
        ):
            if comparison.get(field) != settings[field]:
                raise ValueError(f"SSIM comparison disagrees on {field}.")
        rollout_id = pushed.get("rollout_id")
        if not isinstance(rollout_id, str) or rollout_id in comparison_by_rollout:
            raise ValueError("SSIM comparisons require unique pushed rollout IDs.")
        comparison_by_rollout[rollout_id] = comparison

    raw_rows = localization.get("rows")
    if not isinstance(raw_rows, list):
        raise ValueError("Localization report requires rows.")
    rows = []
    localization_rollout_ids: set[str] = set()
    for raw_row in raw_rows:
        row = copy.deepcopy(dict(_mapping(raw_row, "localization row")))
        rollout_id = row.get("rollout_id")
        if not isinstance(rollout_id, str) or rollout_id in localization_rollout_ids:
            raise ValueError("Localization rollout IDs must be unique.")
        localization_rollout_ids.add(rollout_id)
        comparison = comparison_by_rollout.get(rollout_id)
        if comparison is not None:
            pushed = _mapping(comparison["pushed_metadata"], "pushed metadata")
            baseline = _mapping(comparison["baseline_metadata"], "baseline metadata")
            row["ssim"] = {
                "comparison_id": comparison["comparison_id"],
                "pushed_rollout_id": pushed["rollout_id"],
                "baseline_rollout_id": baseline["rollout_id"],
                "event_id": pushed["event_id"],
                "seed": pushed["seed"],
                "rollout_frame_idx": pushed["rollout_frame_idx"],
                "pushed_clip_hash": pushed["clip_hash"],
                "baseline_clip_hash": baseline["clip_hash"],
                "ssim_report_hash": ssim_hash,
                "settings_hash": ssim["settings_hash"],
                "ssim_version": comparison["ssim_version"],
                "alignment_checked": comparison["alignment_checked"],
                "algorithm": comparison["algorithm"],
                "full_frame_ssim": comparison["full_frame_ssim"],
                "background_masked_ssim": comparison[
                    "background_masked_ssim"
                ],
                "full_frame_pixel_count": comparison["full_frame_pixel_count"],
                "background_pixel_count": comparison["background_pixel_count"],
                "data_range": comparison["data_range"],
                "channel_handling": comparison["channel_handling"],
            }
        rows.append(row)
    unknown_comparisons = set(comparison_by_rollout) - localization_rollout_ids
    if unknown_comparisons:
        raise ValueError(
            "SSIM report contains pushed rollouts without localization rows: "
            + ", ".join(sorted(unknown_comparisons))
        )
    write_json_exclusive(
        args.output,
        {
            "measurement_evidence_input_schema_version": EVIDENCE_INPUT_SCHEMA_VERSION,
            "composed_evidence_schema_version": "person-e-composed-u4-evidence-v0.1",
            "localization_report_hash": localization_hash,
            "ssim_report_hash": ssim_hash,
            "accepted_rollout_manifest_hash": localization[
                "accepted_rollout_manifest_hash"
            ],
            "registry_hash": localization["registry_hash"],
            "config_hash": localization["config_hash"],
            "rows": rows,
        },
    )


if __name__ == "__main__":
    main()
