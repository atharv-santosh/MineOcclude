"""Measure config-governed U4 coherence and alpha-zero natural variation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (  # noqa: E402
    RegistryIndex,
    hash_json_value,
    load_json_with_sha256,
    write_json_exclusive,
)
from mineocclude.vision.config import (  # noqa: E402
    DEFAULT_PERSON_E_CONFIG_PATH,
    hash_person_e_config,
    require_live_ready_person_e_config,
)
from mineocclude.vision.ssim import (  # noqa: E402
    compare_frames,
    compute_ssim,
    require_frame_alignment,
    require_natural_variation_pair,
    summarize_natural_variation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure aligned SSIM using one live-ready Person E config."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("rollout_manifest", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_PERSON_E_CONFIG_PATH)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping.")
    return value


def _require_rows(document: Mapping[str, object], field: str) -> list[object]:
    rows = document.get(field)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Input requires a non-empty {field} list.")
    return rows


def _validate_frame_metadata(
    raw_metadata: object,
    rollout_by_id: Mapping[str, Mapping[str, object]],
    *,
    name: str,
) -> Mapping[str, object]:
    metadata = _require_mapping(raw_metadata, name)
    required = {
        "rollout_id",
        "event_id",
        "seed",
        "layout_id",
        "rollout_frame_idx",
        "control_type",
        "clip_hash",
    }
    missing = required - set(metadata)
    if missing:
        raise ValueError(f"{name} is missing: {', '.join(sorted(missing))}.")
    rollout_id = metadata["rollout_id"]
    if not isinstance(rollout_id, str) or rollout_id not in rollout_by_id:
        raise ValueError(f"{name}.rollout_id is outside the accepted manifest.")
    rollout = rollout_by_id[rollout_id]
    expected = {
        "event_id": rollout["event_id"],
        "seed": rollout["seed"],
        "layout_id": rollout["layout_id"],
        "control_type": rollout["control_type"],
        "clip_hash": rollout["output_hash"],
    }
    mismatches = [field for field, value in expected.items() if metadata[field] != value]
    if mismatches:
        raise ValueError(f"{name} differs from manifest: {', '.join(mismatches)}.")
    frame_idx = metadata["rollout_frame_idx"]
    if not isinstance(frame_idx, int) or isinstance(frame_idx, bool) or frame_idx < 0:
        raise ValueError(f"{name}.rollout_frame_idx must be non-negative int.")
    return metadata


def main() -> None:
    args = parse_args()
    input_document, input_hash = load_json_with_sha256(args.input)
    rollout_manifest, manifest_hash = load_json_with_sha256(args.rollout_manifest)
    registry, registry_hash = load_json_with_sha256(args.registry)
    input_document = _require_mapping(input_document, "SSIM input")
    rollout_manifest = _require_mapping(rollout_manifest, "rollout manifest")
    registry = _require_mapping(registry, "registry")
    registry_index = RegistryIndex(rollout_manifest, registry)

    config = require_live_ready_person_e_config(args.config)
    config_hash = hash_person_e_config(args.config)
    producer_run = registry_index.require_completed_run(
        args.run_id,
        owner="person_e",
        config_hash=config_hash,
    )
    code_sha = producer_run["code_sha"]
    ssim_config = _require_mapping(config["ssim"], "config.ssim")
    data_range = float(ssim_config["data_range"])
    margin = int(ssim_config["background_mask_margin_pixels"])
    algorithm = str(ssim_config["algorithm"])
    ssim_version = str(ssim_config["ssim_version"])

    rollout_rows = rollout_manifest.get("rollout_rows")
    if not isinstance(rollout_rows, list):
        raise ValueError("Validated manifest unexpectedly lacks rollout rows.")
    rollout_by_id = {row["rollout_id"]: row for row in rollout_rows}

    comparison_rows = []
    seen_ids: set[str] = set()
    for index, raw_record in enumerate(_require_rows(input_document, "comparisons")):
        record = _require_mapping(raw_record, f"comparisons[{index}]")
        comparison_id = record.get("comparison_id")
        if (
            not isinstance(comparison_id, str)
            or not comparison_id
            or comparison_id in seen_ids
        ):
            raise ValueError("comparison_id values must be unique and non-empty.")
        seen_ids.add(comparison_id)
        pushed_metadata = _validate_frame_metadata(
            record.get("pushed_metadata"), rollout_by_id, name="pushed_metadata"
        )
        baseline_metadata = _validate_frame_metadata(
            record.get("baseline_metadata"), rollout_by_id, name="baseline_metadata"
        )
        if baseline_metadata["control_type"] != "alpha_zero":
            raise ValueError("SSIM baseline must be an alpha_zero rollout.")
        require_frame_alignment(
            pushed_metadata,
            baseline_metadata,
            identity_fields=("event_id", "seed", "layout_id", "rollout_frame_idx"),
        )
        result = compare_frames(
            record.get("pushed_rgb"),
            record.get("baseline_rgb"),
            data_range=data_range,
            pushed_box_xyxy=record.get("pushed_box_xyxy"),
            baseline_box_xyxy=record.get("baseline_box_xyxy"),
            background_margin_pixels=margin,
            k1=float(ssim_config["k1"]),
            k2=float(ssim_config["k2"]),
            sample_covariance=bool(ssim_config["sample_covariance"]),
        )
        comparison_rows.append(
            {
                "comparison_id": comparison_id,
                "pushed_metadata": dict(pushed_metadata),
                "baseline_metadata": dict(baseline_metadata),
                "alignment_checked": True,
                "algorithm": algorithm,
                "ssim_version": ssim_version,
                **result.to_record(),
            }
        )

    natural_rows = []
    natural_scores = []
    seen_natural_ids: set[str] = set()
    for index, raw_record in enumerate(
        _require_rows(input_document, "natural_variation_pairs")
    ):
        record = _require_mapping(raw_record, f"natural_variation_pairs[{index}]")
        pair_id = record.get("pair_id")
        if not isinstance(pair_id, str) or not pair_id or pair_id in seen_natural_ids:
            raise ValueError("pair_id values must be unique and non-empty.")
        seen_natural_ids.add(pair_id)
        first_metadata = _validate_frame_metadata(
            record.get("first_metadata"), rollout_by_id, name="first_metadata"
        )
        second_metadata = _validate_frame_metadata(
            record.get("second_metadata"), rollout_by_id, name="second_metadata"
        )
        require_natural_variation_pair(first_metadata, second_metadata)
        score = compute_ssim(
            record.get("first_rgb"),
            record.get("second_rgb"),
            data_range=data_range,
            k1=float(ssim_config["k1"]),
            k2=float(ssim_config["k2"]),
            sample_covariance=bool(ssim_config["sample_covariance"]),
        )
        natural_scores.append(score)
        natural_rows.append(
            {
                "pair_id": pair_id,
                "first_metadata": dict(first_metadata),
                "second_metadata": dict(second_metadata),
                "alignment_checked": True,
                "algorithm": algorithm,
                "ssim_version": ssim_version,
                "ssim": score,
            }
        )

    settings = {
        "algorithm": algorithm,
        "ssim_version": ssim_version,
        "data_range": data_range,
        "channel_handling": ssim_config["channel_handling"],
        "sample_covariance": ssim_config["sample_covariance"],
        "k1": ssim_config["k1"],
        "k2": ssim_config["k2"],
        "background_margin_pixels": margin,
    }
    write_json_exclusive(
        args.output,
        {
            "ssim_report_schema_version": "person-e-ssim-report-v0.2",
            "input_hash": input_hash,
            "accepted_rollout_manifest_hash": manifest_hash,
            "registry_hash": registry_hash,
            "producer_run_id": args.run_id,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "config_instance_version": config["config_instance_version"],
            "settings_hash": hash_json_value(settings),
            **settings,
            "comparisons": comparison_rows,
            "natural_variation_pairs": natural_rows,
            "natural_variation_summary": summarize_natural_variation(natural_scores),
        },
    )


if __name__ == "__main__":
    main()
