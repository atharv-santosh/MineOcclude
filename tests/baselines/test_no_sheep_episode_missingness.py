"""Regression test for the real occluder-only/no-sheep episode
(layout_05_ep9422) that reported 0/200 applicable rows in the real pilot
baseline preview -- see tests/fixtures/person_d/real_capture_no_sheep_excerpt
/README.md for provenance.

This confirms the zero-applicable-row outcome is LEGITIMATE (the episode
genuinely never has a visible target) rather than a silent ingest defect:
every non-applicable row must still carry an explicit reason code.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from mineocclude.baselines.capture_ingest import build_contexts_from_capture
from mineocclude.baselines.constant_velocity import predict_constant_velocity
from mineocclude.baselines.last_seen import predict_last_seen
from mineocclude.baselines.missingness import (
    build_missingness_exclusion_report,
    summarize_non_applicable_reasons,
)

FIXTURE_DIR = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "person_d"
    / "real_capture_no_sheep_excerpt"
)


def _load_jsonl(name: str) -> list[dict]:
    path = FIXTURE_DIR / f"{name}.jsonl"
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _real_no_sheep_contexts():
    return build_contexts_from_capture(
        _load_jsonl("frame_map"),
        _load_jsonl("server_state"),
        _load_jsonl("visibility"),
        layout_id="layout_05",
        config_hash="real_no_sheep_preview_v1",
        v_scripted_blocks_per_s=1.0,
        q_scripted_blocks2_per_s=0.05,
        duration_seconds=10.0,
        seed=94873544,
    )


def test_no_sheep_episode_is_all_occluded_with_no_target_present():
    # Confirms this is genuinely a no-sheep condition in the raw stream,
    # not just an artifact of ingest -- line-level evidence for the (a)
    # LEGITIMATE classification.
    visibility_rows = _load_jsonl("visibility")
    state_rows = _load_jsonl("server_state")
    assert len(visibility_rows) == 20
    assert all(row["visibility"] == "occluded" for row in visibility_rows)
    assert all(row["state"]["target_present"] is False for row in state_rows)


def test_build_contexts_from_capture_never_fabricates_a_position():
    contexts = _real_no_sheep_contexts()

    assert len(contexts) == 20
    # Line-level evidence: because visibility is never True, the
    # is_visible branch in build_contexts_from_capture that sets
    # last_seen_position is never taken, so it stays at its initial
    # None for every single frame.
    assert all(ctx.last_seen_position_blocks is None for ctx in contexts)
    assert all(ctx.last_seen_velocity_blocks_per_s is None for ctx in contexts)
    assert all(ctx.visibility is False for ctx in contexts)
    # tau climbs every hidden frame, starting from dt on frame 0.
    assert math.isclose(contexts[0].tau_seconds, 0.05, rel_tol=1e-9)
    assert contexts[-1].tau_seconds > contexts[0].tau_seconds


def test_last_seen_and_constant_velocity_are_wholly_non_applicable_but_explained():
    contexts = _real_no_sheep_contexts()

    last_seen_rows = predict_last_seen(contexts)
    velocity_rows = predict_constant_velocity(contexts)

    mu_last_seen = [row for row in last_seen_rows if row.target_name == "mu_oracle_blocks"]
    mu_velocity = [row for row in velocity_rows if row.target_name == "mu_oracle_blocks"]

    assert mu_last_seen and all(not row.applicable for row in mu_last_seen)
    assert mu_velocity and all(not row.applicable for row in mu_velocity)
    # BaselineRow's own invariant: non-applicable never carries a
    # fabricated numeric prediction.
    assert all(row.prediction is None for row in mu_last_seen + mu_velocity)

    # The key regression check: a wholly non-applicable episode must
    # still be legible, not a silent zero. Every row already carries a
    # reason via last_seen.py/constant_velocity.py's fit_metadata, and
    # the consolidated missingness audit (Step 4.5) must agree there is
    # no silent (reason-less) exclusion hiding here.
    all_rows = mu_last_seen + mu_velocity
    report = build_missingness_exclusion_report(all_rows)
    assert not report.has_silent_missingness, report.rows_missing_reason_code

    reasons = summarize_non_applicable_reasons(all_rows)
    assert reasons == {
        "target not yet seen": len(mu_last_seen),
        "missing last-seen position or estimated velocity": len(mu_velocity),
    }
