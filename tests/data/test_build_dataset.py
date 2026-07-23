"""End-to-end C4 pipeline tests: strict join -> visibility -> conversion ->
frame_map.parquet (C4.6) -> immutable QA (C4.8)."""

import json
import os

import pandas as pd
import pytest

import mineocclude.contracts  # noqa: F401  (pre-existing import-order cycle)
from mineocclude.data.build_dataset import build_dataset, process_episode
from mineocclude.data.qa_report import QAReport, write_report

from tests.data.synthetic_episode import make_episode, write_jsonl


def test_valid_episode_end_to_end(tmp_path):
    server_dir, client_dir = make_episode(
        str(tmp_path), n=12,
        visible_pattern=[True] * 4 + [False] * 4 + [True] * 4,
        yaw_impulses={2: 6.0, 9: 6.0, 11: 6.0},
    )
    out_root = str(tmp_path / "out")
    summary = process_episode(server_dir, client_dir, out_root)
    assert summary["accepted"], summary["problems"]
    assert summary["n_frames"] == 12
    assert summary["n_visible"] == 8
    assert summary["n_hidden"] == 4
    assert summary["impulse_passed"] is True

    # C4.6: the parquet frame map exists and reconstructs identity.
    frame_map = pd.read_parquet(summary["frame_map"])
    assert len(frame_map) == 12
    for column in ("episode_id", "trajectory_id", "server_tick",
                   "render_frame_idx", "action_idx", "model_frame_idx",
                   "frame_abspath", "visible_flag", "quarantine_category"):
        assert column in frame_map.columns, column
    assert list(frame_map["server_tick"]) == list(range(12))
    key = frame_map[["server_tick", "render_frame_idx", "action_idx",
                     "model_frame_idx"]]
    assert not key.duplicated().any()

    # Actions: one 11-token row per accepted frame.
    actions_path = os.path.join(os.path.dirname(summary["frame_map"]),
                                "mineworld_actions.jsonl")
    rows = [json.loads(line) for line in open(actions_path)]
    assert len(rows) == 12
    assert all(len(row["tokens"]) == 11 for row in rows)

    # C4.8: the QA report exists, is accepted, and has a hash sidecar.
    qa = json.load(open(summary["qa_report"]))
    assert qa["accepted"] is True
    assert qa["status"] == "accepted"
    assert os.path.isfile(summary["qa_report"] + ".sha256")
    check_names = {check["name"] for check in qa["checks"]}
    assert {"alignment", "cardinality", "consecutive_ticks",
            "impulse_orientation"} <= check_names


def test_corrupted_episode_is_excluded_not_repaired(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=8)
    # Remove one action row -> cardinality break.
    path = os.path.join(client_dir, "raw_actions.jsonl")
    rows = [json.loads(line) for line in open(path)]
    write_jsonl(path, rows[:-1])

    out_root = str(tmp_path / "out")
    ledger = build_dataset([(server_dir, client_dir)], out_root)
    assert ledger["n_accepted"] == 0
    assert ledger["n_excluded"] == 1
    assert ledger["excluded"][0]["problems"]
    # No manifest is written for an empty accepted set.
    assert not os.path.exists(os.path.join(out_root, "trajectories_mvp.parquet"))
    # The ledger itself is preserved on disk.
    assert os.path.isfile(os.path.join(out_root, "ledger.json"))


def test_sheep_never_seen_is_rejected(tmp_path):
    server_dir, client_dir = make_episode(
        str(tmp_path), n=6, visible_pattern=[False] * 6
    )
    summary = process_episode(server_dir, client_dir, str(tmp_path / "out"))
    assert not summary["accepted"]
    assert any("never seen" in p for p in summary["problems"])


def test_manifest_aggregates_accepted_only(tmp_path):
    ok_server, ok_client = make_episode(
        str(tmp_path / "a"), episode_id=1, n=12,
        visible_pattern=[True] * 4 + [False] * 4 + [True] * 4,
        yaw_impulses={2: 6.0, 9: 6.0, 11: 6.0},
    )
    bad_server, bad_client = make_episode(
        str(tmp_path / "b"), episode_id=2, n=6,
        visible_pattern=[False] * 6,
    )
    out_root = str(tmp_path / "out")
    ledger = build_dataset(
        [(ok_server, ok_client), (bad_server, bad_client)], out_root
    )
    assert ledger["n_accepted"] == 1
    assert ledger["n_excluded"] == 1
    manifest = pd.read_parquet(os.path.join(out_root, "trajectories_mvp.parquet"))
    assert list(manifest["trajectory_id"]) == ["layout_01_ep1"]


def test_qa_report_is_immutable(tmp_path):
    report = QAReport(episode_id="7", trajectory_id="layout_01_ep7")
    report.add("alignment", True)
    write_report(report, str(tmp_path))
    with pytest.raises(FileExistsError, match="new episode identity"):
        write_report(report, str(tmp_path))
