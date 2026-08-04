"""Tests for the strict equality join (C4.1-C4.3) on file-based episodes."""

import json
import os

from mineocclude.data.align import align_episode

from tests.data.synthetic_episode import make_episode, write_jsonl


def _read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def test_valid_episode_accepts(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=8)
    frame_map, report = align_episode(server_dir, client_dir)
    assert report.accepted, report.problems
    assert len(frame_map) == 8
    assert list(frame_map["model_frame_idx"]) == list(range(8))
    assert frame_map["trajectory_id"].iloc[0] == "layout_01_ep1"
    assert all(os.path.isfile(p) for p in frame_map["frame_abspath"])


def test_missing_action_rejects(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=8)
    path = os.path.join(client_dir, "raw_actions.jsonl")
    rows = _read_jsonl(path)
    write_jsonl(path, rows[:-1])
    frame_map, report = align_episode(server_dir, client_dir)
    assert not report.accepted
    assert frame_map is None
    assert any("cardinality" in p for p in report.problems)


def test_skipped_tick_rejects(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=8)
    path = os.path.join(server_dir, "server_state.jsonl")
    rows = _read_jsonl(path)
    rows[4]["server_tick"] = 9  # gap: ...,3,9,5,...
    write_jsonl(path, rows)
    frame_map, report = align_episode(server_dir, client_dir)
    assert not report.accepted
    assert any("consecutive" in p for p in report.problems)


def test_duplicate_frame_identity_rejects(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=8)
    path = os.path.join(client_dir, "client_tick.jsonl")
    rows = _read_jsonl(path)
    rows[5]["render_frame_idx"] = rows[4]["render_frame_idx"]
    write_jsonl(path, rows)
    frame_map, report = align_episode(server_dir, client_dir)
    assert not report.accepted
    assert any("duplicate" in p for p in report.problems)


def test_mixed_episode_id_rejects(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=8)
    path = os.path.join(client_dir, "raw_actions.jsonl")
    rows = _read_jsonl(path)
    rows[3]["episode_id"] = 999
    write_jsonl(path, rows)
    frame_map, report = align_episode(server_dir, client_dir)
    assert not report.accepted
    assert any("mixed episode" in p for p in report.problems)


def test_missing_frame_file_rejects(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=8)
    os.remove(os.path.join(client_dir, "frames", "000004.png"))
    frame_map, report = align_episode(server_dir, client_dir)
    assert not report.accepted
    # Both the count mismatch and the referenced-file check may fire; at
    # least one must name the problem explicitly.
    assert any(
        "missing frame" in p or "cardinality" in p for p in report.problems
    )


def test_shifted_action_rejects(tmp_path):
    """An action stream shifted by one tick must not silently join."""
    server_dir, client_dir = make_episode(str(tmp_path), n=8)
    path = os.path.join(client_dir, "raw_actions.jsonl")
    rows = _read_jsonl(path)
    for row in rows:
        row["server_tick"] = row["server_tick"] + 1  # shift the join identity
    write_jsonl(path, rows)
    frame_map, report = align_episode(server_dir, client_dir)
    assert not report.accepted


def test_unreadable_source_rejects(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=4)
    os.remove(os.path.join(server_dir, "server_state.jsonl"))
    frame_map, report = align_episode(server_dir, client_dir)
    assert not report.accepted
    assert any("unreadable source" in p for p in report.problems)
