"""Build the selected-C6A numbered-frame media metadata receipt.

The selected handoff bundles retain the immutable Retina-framebuffer PNGs.
Person A's already-frozen runtime performs the canonical 640x360 normalization;
the normalized frames and an encoded container are not repository artifacts.
This receipt records that actual two-stage contract without manufacturing video
metadata or rewriting either stage.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import struct
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "docs/status/post_integration_reproducibility_closure_v0_1"
    / "selected_trajectory_media_metadata_receipt.json"
)
TRAJECTORIES = {
    "layout_01_ep12602": ROOT
    / "data/handoff_a/person_a_canonical_c6a_sagemaker_input_v0_1",
    **{
        trajectory_id: ROOT
        / "data/handoff_a/person_a_canonical_c6a_multilayout_sagemaker_input_v0_1"
        / "trajectories"
        / trajectory_id
        for trajectory_id in (
            "layout_02_ep12610",
            "layout_03_ep12645",
            "layout_04_ep12626",
            "layout_05_ep12634",
        )
    },
}
ENVIRONMENT_AUTHORITY = ROOT / "configs/scenes/environment_lock.observed_dev_v0_1.json"
NORMALIZATION_AUTHORITY = ROOT / "scripts/run_person_a_phase6_single_pilot_sagemaker.py"
TRAJECTORY_CONTRACT = ROOT / "docs/contracts/trajectory_v1.md"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _identity(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
    }


def _json_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _png_dimensions(payload: bytes) -> tuple[int, int]:
    if payload[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
        raise ValueError("not a canonical PNG IHDR")
    return struct.unpack(">II", payload[16:24])


def _trajectory_receipt(trajectory_id: str, bundle_root: Path) -> dict[str, Any]:
    episode_id = int(trajectory_id.rsplit("ep", 1)[1])
    manifest_path = bundle_root / "bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["trajectory_id"] != trajectory_id or manifest["episode_id"] != episode_id:
        raise ValueError(f"bundle identity mismatch: {trajectory_id}")

    frame_root = bundle_root / "episode/client/frames"
    frames = sorted(frame_root.glob("*.png"))
    expected_names = [f"{index:06d}.png" for index in range(60)]
    if [path.name for path in frames] != expected_names:
        raise ValueError(f"non-consecutive frame sequence: {trajectory_id}")
    manifest_by_path = {row["path"]: row for row in manifest["files"]}
    source_by_path = {row["bundle_path"]: row["source"] for row in manifest["direct_artifacts"]}

    frame_rows = []
    image_module = importlib.import_module("PIL.Image")
    for index, path in enumerate(frames):
        relative = f"episode/client/frames/{path.name}"
        payload = path.read_bytes()
        width, height = _png_dimensions(payload)
        recorded = manifest_by_path[relative]
        source = source_by_path[relative]
        if (width, height) != (1920, 1046):
            raise ValueError(f"unexpected source dimensions: {path}")
        if recorded["sha256"] != _sha256(payload) or recorded["size_bytes"] != len(payload):
            raise ValueError(f"bundle frame identity mismatch: {path}")
        if source["expected_schema_id"] != "image-png-1920x1046-v0.1":
            raise ValueError(f"source schema mismatch: {path}")
        with image_module.open(path) as opened:
            image = opened.convert("RGB")
            source_width, source_height = image.size
            target_aspect = 640.0 / 360.0
            aspect = source_width / source_height
            if aspect > target_aspect:
                new_width = round(source_height * target_aspect)
                left = (source_width - new_width) // 2
                image = image.crop((left, 0, left + new_width, source_height))
            elif aspect < target_aspect:
                new_height = round(source_width / target_aspect)
                top = (source_height - new_height) // 2
                image = image.crop((0, top, source_width, top + new_height))
            normalized = image.resize((640, 360), image_module.Resampling.BILINEAR)
            if normalized.size != (640, 360):
                raise ValueError(f"canonical normalization dimensions mismatch: {path}")
        frame_rows.append(
            {
                "frame_index": index,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": recorded["sha256"],
                "size_bytes": recorded["size_bytes"],
                "width_pixels": width,
                "height_pixels": height,
            }
        )

    tick_path = bundle_root / "episode/client/client_tick.jsonl"
    ticks = _json_lines(tick_path)
    if len(ticks) != 60:
        raise ValueError(f"client tick count mismatch: {trajectory_id}")
    if [row["render_frame_idx"] for row in ticks] != list(range(60)):
        raise ValueError(f"client frame identity sequence mismatch: {trajectory_id}")
    if [row["frame_path"] for row in ticks] != [f"frames/{name}" for name in expected_names]:
        raise ValueError(f"client frame path sequence mismatch: {trajectory_id}")
    if {row["episode_id"] for row in ticks} != {episode_id}:
        raise ValueError(f"client episode identity mismatch: {trajectory_id}")

    schedule_path = ROOT / f"configs/collection/person_c_c6a_v0_1/schedules/episode_{episode_id}.jsonl"
    schedule = _json_lines(schedule_path)
    header, draws = schedule[0], schedule[1:]
    if header["n_draws"] != 60 or header["dt_seconds"] != 0.05:
        raise ValueError(f"schedule cadence mismatch: {trajectory_id}")
    if [row["draw_idx"] for row in draws] != list(range(60)):
        raise ValueError(f"schedule draw sequence mismatch: {trajectory_id}")
    if {row["dt_seconds"] for row in draws} != {0.05}:
        raise ValueError(f"schedule draw cadence mismatch: {trajectory_id}")

    collection_material = "".join(
        f"{row['frame_index']}\0{row['size_bytes']}\0{row['sha256']}\n" for row in frame_rows
    ).encode("utf-8")
    return {
        "trajectory_id": trajectory_id,
        "episode_id": episode_id,
        "bundle_manifest": _identity(manifest_path),
        "client_tick_identity": _identity(tick_path),
        "schedule_identity": _identity(schedule_path),
        "media_mode": "numbered_frames",
        "encoded_video_present": False,
        "declared_frame_rate": "20/1",
        "declared_frame_interval_seconds": 0.05,
        "frame_count": 60,
        "frame_indexes_consecutive": True,
        "frame_paths_match_client_tick_authority": True,
        "source_schema_id": "image-png-1920x1046-v0.1",
        "source_width_pixels": 1920,
        "source_height_pixels": 1046,
        "canonical_normalized_frame_count": 60,
        "canonical_normalized_width_pixels": 640,
        "canonical_normalized_height_pixels": 360,
        "source_frame_collection_sha256": _sha256(collection_material),
        "frames": frame_rows,
    }


def build_receipt() -> dict[str, Any]:
    environment = json.loads(ENVIRONMENT_AUTHORITY.read_text(encoding="utf-8"))
    discrepancy = next(
        row
        for row in environment["discrepancies_vs_approved_lock"]
        if "640x360 canonical source" in row
    )
    normalization_source = NORMALIZATION_AUTHORITY.read_text(encoding="utf-8")
    required_fragments = (
        "target_aspect = 640.0 / 360.0",
        "image.resize((640, 360), image_module.Resampling.BILINEAR)",
    )
    if not all(fragment in normalization_source for fragment in required_fragments):
        raise ValueError("canonical normalization authority drift")
    contract = TRAJECTORY_CONTRACT.read_text(encoding="utf-8")
    if "one authoritative numbered-frame sequence" not in contract:
        raise ValueError("trajectory numbered-frame contract drift")

    trajectories = [
        _trajectory_receipt(trajectory_id, path)
        for trajectory_id, path in TRAJECTORIES.items()
    ]
    return {
        "schema_version": "post-integration-selected-media-metadata-v0.1",
        "status": "PASS",
        "media_contract": "PNG_SEQUENCE",
        "selected_trajectory_media_valid": True,
        "trajectory_count": 5,
        "total_source_frame_count": 300,
        "source_representation": "AUTHORITATIVE_NUMBERED_PNG_FRAME_SEQUENCE",
        "source_framebuffer_dimensions": {"width_pixels": 1920, "height_pixels": 1046},
        "declared_capture_rate": "20/1",
        "capture_rate_authority": "immutable C6A schedules with dt_seconds=0.05",
        "canonical_model_input_dimensions": {"width_pixels": 640, "height_pixels": 360},
        "canonical_normalization_verified_for_all_source_frames": True,
        "canonical_model_input_relationship": "DETERMINISTIC_CROP_AND_BILINEAR_RESIZE_FROM_IMMUTABLE_SOURCE_PNGS",
        "canonical_derivative_retained_in_repository": False,
        "encoded_video_retained_in_repository": False,
        "ffprobe_applicable": False,
        "ffprobe_reason": "The authoritative retained media is a PNG sequence; no encoded selected-trajectory container exists.",
        "contract_resolution": (
            "Selected C6A bundle media are immutable 1920x1046 source-framebuffer PNGs. "
            "The repository-authoritative 640x360 requirement is satisfied at the unchanged Person A "
            "normalization boundary, not by relabeling or modifying the source PNG bytes."
        ),
        "environment_authority": {**_identity(ENVIRONMENT_AUTHORITY), "statement": discrepancy},
        "normalization_authority": {
            **_identity(NORMALIZATION_AUTHORITY),
            "required_source_fragments": list(required_fragments),
        },
        "trajectory_contract": _identity(TRAJECTORY_CONTRACT),
        "trajectories": trajectories,
        "scientific_artifacts_changed": False,
    }


def canonical_json(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(document, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(canonical_json(build_receipt()))
    print(OUTPUT)


if __name__ == "__main__":
    main()
