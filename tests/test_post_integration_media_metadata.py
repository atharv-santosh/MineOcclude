from __future__ import annotations

import hashlib
import json

from scripts.build_post_integration_media_metadata_receipt import (
    OUTPUT,
    build_receipt,
    canonical_json,
)


def test_selected_trajectory_media_receipt_matches_immutable_sources() -> None:
    payload = OUTPUT.read_bytes()
    receipt = json.loads(payload)
    assert payload == canonical_json(receipt)
    assert payload == canonical_json(build_receipt())
    assert receipt["status"] == "PASS"
    assert receipt["media_contract"] == "PNG_SEQUENCE"
    assert receipt["selected_trajectory_media_valid"] is True
    assert receipt["trajectory_count"] == 5
    assert receipt["total_source_frame_count"] == 300
    assert receipt["canonical_normalization_verified_for_all_source_frames"] is True
    assert receipt["ffprobe_applicable"] is False
    assert {row["frame_count"] for row in receipt["trajectories"]} == {60}
    assert {
        (row["source_width_pixels"], row["source_height_pixels"])
        for row in receipt["trajectories"]
    } == {(1920, 1046)}
    assert {
        (
            row["canonical_normalized_frame_count"],
            row["canonical_normalized_width_pixels"],
            row["canonical_normalized_height_pixels"],
        )
        for row in receipt["trajectories"]
    } == {(60, 640, 360)}
    assert len(hashlib.sha256(payload).hexdigest()) == 64
