"""Tests for the real-capture ingest adapter, using a real (excerpted,
not synthetic) episode from Person C's branch -- see
tests/fixtures/person_d/real_capture_excerpt/README.md for provenance.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from mineocclude.baselines.capture_ingest import (
    UNASSIGNED_FOLD,
    CaptureIngestError,
    build_contexts_from_capture,
)
from mineocclude.baselines.constant_velocity import predict_constant_velocity
from mineocclude.baselines.last_seen import predict_last_seen

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "person_d" / "real_capture_excerpt"


def _load_jsonl(name: str) -> list[dict]:
    path = FIXTURE_DIR / f"{name}.jsonl"
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _real_contexts(**overrides):
    frame_map_rows = _load_jsonl("frame_map")
    server_state_rows = _load_jsonl("server_state")
    visibility_rows = _load_jsonl("visibility")
    kwargs = dict(
        layout_id="layout_00",
        config_hash="real_pilot_preview_v1",
        v_scripted_blocks_per_s=1.0,
        q_scripted_blocks2_per_s=0.02,
        duration_seconds=12.4,
        seed=94723083,
    )
    kwargs.update(overrides)
    return build_contexts_from_capture(
        frame_map_rows, server_state_rows, visibility_rows, **kwargs
    )


def test_build_contexts_from_capture_parses_the_real_episode():
    contexts = _real_contexts()

    # The excerpt spans frames 15-34 and 224-233 (see README).
    assert len(contexts) == 30
    assert all(ctx.trajectory_id == "layout_00_ep9403" for ctx in contexts)
    assert all(ctx.layout_id == "layout_00" for ctx in contexts)
    assert all(ctx.fold == UNASSIGNED_FOLD for ctx in contexts)


def test_build_contexts_from_capture_handles_the_real_visible_to_hidden_transition():
    contexts = _real_contexts()
    by_frame = {ctx.model_frame_idx: ctx for ctx in contexts}

    # Frame 18 is the last real visible frame before occlusion at 19.
    assert by_frame[18].visibility is True
    assert by_frame[18].tau_seconds == 0.0
    last_visible_position = by_frame[18].last_seen_position_blocks
    assert last_visible_position is not None

    # First hidden frame: tau advances by exactly one dt; last-seen
    # position is carried forward unchanged from the real visible state.
    assert by_frame[19].visibility is False
    assert math.isclose(by_frame[19].tau_seconds, 0.05, rel_tol=1e-9)
    assert by_frame[19].last_seen_position_blocks == last_visible_position

    # tau keeps climbing while hidden, still carrying the same position.
    assert by_frame[34].visibility is False
    assert by_frame[34].tau_seconds > by_frame[19].tau_seconds
    assert by_frame[34].last_seen_position_blocks == last_visible_position


def test_build_contexts_from_capture_handles_the_real_reveal():
    contexts = _real_contexts()
    by_frame = {ctx.model_frame_idx: ctx for ctx in contexts}

    # Frame 227 is still hidden (reveal happens at 228 per the README).
    assert by_frame[227].visibility is False
    # On reveal, tau resets to 0 and last-seen updates to the new
    # authoritative visible position -- never the pre-occlusion one.
    assert by_frame[228].visibility is True
    assert by_frame[228].tau_seconds == 0.0
    assert by_frame[228].last_seen_position_blocks != by_frame[227].last_seen_position_blocks


def test_build_contexts_from_capture_rejects_mismatched_frame_identity():
    frame_map_rows = _load_jsonl("frame_map")
    server_state_rows = _load_jsonl("server_state")
    visibility_rows = _load_jsonl("visibility")[:-1]  # drop one row -> mismatch

    with pytest.raises(CaptureIngestError, match="same model_frame_idx"):
        build_contexts_from_capture(
            frame_map_rows,
            server_state_rows,
            visibility_rows,
            layout_id="layout_00",
            config_hash="real_pilot_preview_v1",
        )


def test_last_seen_and_constant_velocity_run_on_the_real_ingested_contexts():
    contexts = _real_contexts()

    last_seen_rows = predict_last_seen(contexts)
    velocity_rows = predict_constant_velocity(contexts)

    applicable_last_seen = [
        row
        for row in last_seen_rows
        if row.target_name == "mu_oracle_blocks" and row.applicable
    ]
    applicable_velocity = [
        row
        for row in velocity_rows
        if row.target_name == "mu_oracle_blocks" and row.applicable
    ]
    # Every frame in the excerpt has been preceded by a real visible
    # frame at some point (frame 15 onward), so both should apply
    # everywhere except possibly the very first row.
    assert applicable_last_seen
    assert applicable_velocity
    for row in applicable_last_seen + applicable_velocity:
        assert math.isfinite(row.prediction)
