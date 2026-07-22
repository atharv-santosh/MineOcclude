"""Build traceable E-to-B U4 measurements from versioned evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import sys
from collections.abc import Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.manifests import is_hex_digest  # noqa: E402
from mineocclude.experiments.registry import (  # noqa: E402
    RegistryIndex,
    formatted_json_bytes,
    hash_file_bytes,
    hash_json_value,
    load_json_with_sha256,
    write_json_exclusive,
)
from mineocclude.vision.config import (  # noqa: E402
    DEFAULT_PERSON_E_CONFIG_PATH,
    hash_person_e_config,
    require_live_ready_person_e_config,
)
from mineocclude.vision.measurement import (  # noqa: E402
    EVIDENCE_INPUT_SCHEMA_VERSION,
    FrameLocalization,
    build_measurement_document,
    build_measurement_evidence,
    build_measurement_row,
    find_alpha_zero_matches,
    find_reappearance,
)
from mineocclude.vision.ssim import SsimResult  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure exact-coverage U4 rows from versioned E evidence."
    )
    parser.add_argument("rollout_manifest", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--evidence-output-dir",
        type=Path,
        required=True,
        help="New directory for one immutable detailed-evidence file per rollout.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_PERSON_E_CONFIG_PATH)
    parser.add_argument(
        "--run-id",
        required=True,
        help="Existing Person E producer run in the validated registry.",
    )
    return parser.parse_args()


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping.")
    return value


def _require_identifier(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ValueError(f"{name} must be a non-empty trimmed string.")
    return value


def _require_sha256(value: object, name: str) -> str:
    if not is_hex_digest(value, 64):
        raise ValueError(f"{name} must be SHA-256.")
    return str(value)


def _localizations(records: object) -> list[FrameLocalization]:
    if not isinstance(records, list) or not records:
        raise ValueError("Localization evidence must be a non-empty list.")
    localizations: list[FrameLocalization] = []
    for index, raw_record in enumerate(records):
        record = _require_mapping(raw_record, f"localizations[{index}]")
        required = {
            "frame_idx",
            "wall_parallel_blocks",
            "detection_valid",
            "bounding_box_xyxy",
            "rejection_reason",
            "source_frame_hash",
            "detector_result_hash",
        }
        missing = required - set(record)
        if missing:
            raise ValueError(
                f"localizations[{index}] is missing: {', '.join(sorted(missing))}."
            )
        _require_sha256(record["source_frame_hash"], "source_frame_hash")
        _require_sha256(record["detector_result_hash"], "detector_result_hash")
        box = record["bounding_box_xyxy"]
        localizations.append(
            FrameLocalization(
                frame_idx=record["frame_idx"],
                wall_parallel_blocks=record["wall_parallel_blocks"],
                detection_valid=record["detection_valid"],
                bounding_box_xyxy=(None if box is None else tuple(box)),
                rejection_reason=record["rejection_reason"],
            )
        )
    return localizations


def _ssim(
    raw_record: object,
    *,
    rollout: Mapping[str, object],
    baseline: Mapping[str, object],
    config: Mapping[str, object],
) -> SsimResult | None:
    if raw_record is None:
        return None
    record = _require_mapping(raw_record, "ssim evidence")
    required = {
        "comparison_id",
        "pushed_rollout_id",
        "baseline_rollout_id",
        "event_id",
        "seed",
        "rollout_frame_idx",
        "pushed_clip_hash",
        "baseline_clip_hash",
        "ssim_report_hash",
        "settings_hash",
        "ssim_version",
        "alignment_checked",
        "algorithm",
        "full_frame_ssim",
        "background_masked_ssim",
        "full_frame_pixel_count",
        "background_pixel_count",
        "data_range",
        "channel_handling",
    }
    missing = required - set(record)
    if missing:
        raise ValueError("ssim evidence is missing: " + ", ".join(sorted(missing)))
    ssim_config = _require_mapping(config["ssim"], "config.ssim")
    expected = {
        "pushed_rollout_id": rollout["rollout_id"],
        "baseline_rollout_id": baseline["rollout_id"],
        "event_id": rollout["event_id"],
        "seed": rollout["seed"],
        "pushed_clip_hash": rollout["output_hash"],
        "baseline_clip_hash": baseline["output_hash"],
        "ssim_version": ssim_config["ssim_version"],
        "algorithm": ssim_config["algorithm"],
        "data_range": ssim_config["data_range"],
        "channel_handling": ssim_config["channel_handling"],
    }
    mismatches = [field for field, value in expected.items() if record[field] != value]
    if mismatches:
        raise ValueError(
            "SSIM evidence does not match the rollout/config: "
            + ", ".join(mismatches)
        )
    if record["alignment_checked"] is not True:
        raise ValueError("SSIM evidence requires alignment_checked=true.")
    frame_idx = record["rollout_frame_idx"]
    if not isinstance(frame_idx, int) or isinstance(frame_idx, bool) or frame_idx < 0:
        raise ValueError("SSIM rollout_frame_idx must be a non-negative integer.")
    for field in ("ssim_report_hash", "settings_hash"):
        _require_sha256(record[field], field)
    _require_identifier(record["comparison_id"], "comparison_id")
    return SsimResult(
        full_frame_ssim=record["full_frame_ssim"],
        background_masked_ssim=record["background_masked_ssim"],
        full_frame_pixel_count=record["full_frame_pixel_count"],
        background_pixel_count=record["background_pixel_count"],
        data_range=record["data_range"],
        channel_handling=record["channel_handling"],
    )


def _validate_evidence_row(
    raw_evidence: object,
    rollout: Mapping[str, object],
    config: Mapping[str, object],
) -> Mapping[str, object]:
    evidence = _require_mapping(raw_evidence, "evidence row")
    required = {
        "rollout_id",
        "reveal_frame_idx",
        "layout_id",
        "canonical_camera_pose_id",
        "detector_report_hash",
        "detector_version",
        "homography_report_hash",
        "homography_version_id",
        "localizations",
        "ssim",
    }
    missing = required - set(evidence)
    if missing:
        raise ValueError("Evidence row is missing: " + ", ".join(sorted(missing)))
    if evidence["rollout_id"] != rollout["rollout_id"]:
        raise ValueError("Evidence rollout_id does not match the manifest row.")
    if evidence["layout_id"] != rollout["layout_id"]:
        raise ValueError("Evidence layout_id does not match the manifest row.")
    for field in (
        "canonical_camera_pose_id",
        "detector_version",
        "homography_version_id",
    ):
        _require_identifier(evidence[field], field)
    for field in ("detector_report_hash", "homography_report_hash"):
        _require_sha256(evidence[field], field)
    detector_config = _require_mapping(config["detector"], "config.detector")
    if evidence["detector_version"] != detector_config["threshold_version"]:
        raise ValueError("Evidence detector_version differs from the live config.")
    return evidence


def _safe_evidence_path(directory: Path, rollout_id: str) -> Path:
    suffix = hash_json_value({"rollout_id": rollout_id})[:20]
    return directory / f"measurement-evidence-{suffix}.json"


def main() -> None:
    args = parse_args()
    rollout_manifest, _ = load_json_with_sha256(args.rollout_manifest)
    registry, _ = load_json_with_sha256(args.registry)
    rollout_manifest = _require_mapping(rollout_manifest, "rollout manifest")
    registry = _require_mapping(registry, "registry")
    registry_index = RegistryIndex(rollout_manifest, registry)
    accepted_rollout_manifest_hash = hash_json_value(rollout_manifest)
    accepted_registry_hash = hash_json_value(registry)

    config = require_live_ready_person_e_config(args.config)
    config_hash = hash_person_e_config(args.config)
    producer_run = registry_index.require_completed_run(
        args.run_id,
        owner="person_e",
        config_hash=config_hash,
    )
    code_sha = str(producer_run["code_sha"])

    evidence_document, evidence_source_hash = load_json_with_sha256(args.evidence)
    evidence_document = _require_mapping(evidence_document, "evidence input")
    if (
        evidence_document.get("measurement_evidence_input_schema_version")
        != EVIDENCE_INPUT_SCHEMA_VERSION
    ):
        raise ValueError("Unknown measurement-evidence input schema version.")
    expected_evidence_hashes = {
        "accepted_rollout_manifest_hash": accepted_rollout_manifest_hash,
        "accepted_registry_hash": accepted_registry_hash,
        "config_hash": config_hash,
    }
    for field, expected in expected_evidence_hashes.items():
        if evidence_document.get(field) != expected:
            raise ValueError(f"Evidence input {field} differs from processed bytes.")
    evidence_rows = evidence_document.get("rows")
    if not isinstance(evidence_rows, list):
        raise ValueError("Evidence input requires a rows list.")
    evidence_by_rollout: dict[str, Mapping[str, object]] = {}
    for raw_evidence in evidence_rows:
        evidence = _require_mapping(raw_evidence, "evidence row")
        rollout_id = _require_identifier(evidence.get("rollout_id"), "rollout_id")
        if rollout_id in evidence_by_rollout:
            raise ValueError("Evidence rollout IDs must be unique.")
        evidence_by_rollout[rollout_id] = evidence

    rollout_rows = rollout_manifest.get("rollout_rows")
    if not isinstance(rollout_rows, list):
        raise ValueError("Validated manifest unexpectedly lacks rollout_rows.")
    rollout_by_id = {row["rollout_id"]: row for row in rollout_rows}
    unknown_evidence = set(evidence_by_rollout) - set(rollout_by_id)
    if unknown_evidence:
        raise ValueError(
            "Evidence references rollout IDs outside the manifest: "
            + ", ".join(sorted(unknown_evidence))
        )

    baseline_by_rollout = find_alpha_zero_matches(rollout_rows)
    reappearance_by_rollout = {}
    validated_evidence_by_rollout: dict[str, Mapping[str, object]] = {}
    measurement_config = _require_mapping(config["measurement"], "config.measurement")
    for rollout_id, raw_evidence in evidence_by_rollout.items():
        rollout = rollout_by_id[rollout_id]
        evidence = _validate_evidence_row(raw_evidence, rollout, config)
        validated_evidence_by_rollout[rollout_id] = evidence
        reappearance_by_rollout[rollout_id] = find_reappearance(
            _localizations(evidence["localizations"]),
            reveal_frame_idx=evidence["reveal_frame_idx"],
            required_consecutive_frames=measurement_config[
                "primary_valid_consecutive_frames"
            ],
            sensitivity_first_valid_frames=measurement_config[
                "sensitivity_first_valid_frames"
            ],
        )

    if args.output.exists() or args.evidence_output_dir.exists():
        raise FileExistsError("Output and evidence directory must both be new.")
    measurement_rows = []
    evidence_references = []
    evidence_documents: list[tuple[Path, Mapping[str, object], str]] = []
    for rollout in rollout_rows:
        rollout_id = rollout["rollout_id"]
        evidence = validated_evidence_by_rollout.get(rollout_id)
        baseline = baseline_by_rollout[rollout_id]
        baseline_id = None if baseline is None else str(baseline["rollout_id"])
        ssim_result = None
        if evidence is not None and baseline is not None:
            ssim_result = _ssim(
                evidence.get("ssim"),
                rollout=rollout,
                baseline=baseline,
                config=config,
            )
        row = build_measurement_row(
            rollout,
            measurement_id=f"measurement:{rollout_id}",
            measurement_artifact_hash="0" * 64,
            baseline_rollout_id=baseline_id,
            pushed_reappearance=reappearance_by_rollout.get(rollout_id),
            baseline_reappearance=(
                None
                if baseline_id is None
                else reappearance_by_rollout.get(baseline_id)
            ),
            ssim_result=ssim_result,
        )
        measurement_without_hash = copy.deepcopy(row)
        measurement_without_hash.pop("measurement_artifact_hash")
        detailed_payload = {
            "source_evidence": None if evidence is None else dict(evidence),
            "matched_alpha_zero_rollout_id": baseline_id,
            "pushed_reappearance": (
                None
                if rollout_id not in reappearance_by_rollout
                else reappearance_by_rollout[rollout_id].to_record()
            ),
            "baseline_reappearance": (
                None
                if baseline_id not in reappearance_by_rollout
                else reappearance_by_rollout[baseline_id].to_record()
            ),
            "measurement_without_artifact_hash": measurement_without_hash,
        }
        evidence_id = f"measurement_evidence:{rollout_id}"
        detailed_document = build_measurement_evidence(
            detailed_payload,
            evidence_id=evidence_id,
            rollout_id=rollout_id,
            producer_run_id=args.run_id,
            code_sha=code_sha,
            accepted_rollout_manifest_hash=accepted_rollout_manifest_hash,
            accepted_registry_hash=accepted_registry_hash,
            config_path=args.config,
        )
        evidence_path = _safe_evidence_path(args.evidence_output_dir, rollout_id)
        evidence_hash = hashlib.sha256(
            formatted_json_bytes(detailed_document)
        ).hexdigest()
        evidence_documents.append((evidence_path, detailed_document, evidence_hash))
        row["measurement_artifact_hash"] = evidence_hash
        measurement_rows.append(row)
        evidence_references.append(
            {
                "evidence_id": evidence_id,
                "rollout_id": rollout_id,
                "uri": evidence_path.resolve().as_uri(),
                "sha256": evidence_hash,
                "producer_run_id": args.run_id,
            }
        )

    document = build_measurement_document(
        measurement_rows,
        rollout_manifest=rollout_manifest,
        registry=registry,
        accepted_rollout_manifest_hash=accepted_rollout_manifest_hash,
        accepted_registry_hash=accepted_registry_hash,
        measurement_evidence=evidence_references,
        config_path=args.config,
    )
    document["measurement_evidence_source_hash"] = evidence_source_hash
    document["producer_run_id"] = args.run_id
    document["code_sha"] = code_sha
    for evidence_path, detailed_document, expected_hash in evidence_documents:
        write_json_exclusive(evidence_path, detailed_document)
        if hash_file_bytes(evidence_path) != expected_hash:
            raise RuntimeError("Persisted evidence checksum differs from prepared bytes.")
    write_json_exclusive(args.output, document)


if __name__ == "__main__":
    main()
