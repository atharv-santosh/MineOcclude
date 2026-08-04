"""Tests for raw-action -> env-action -> 11-token conversion (C4.4)."""

import json

import pytest

from mineocclude.data.align import align_episode
from mineocclude.data.convert_mineworld import (
    ACTION_VOCAB_OFFSET,
    CAMERA_BINS,
    N_ACTION_TOKENS,
    REFERENCE_CONVERTER_ID,
    bin_camera,
    env_action_to_tokens,
    raw_to_env_action,
    write_mineworld_actions,
)

from tests.data.synthetic_episode import make_episode

NOOP_RAW = {
    "camera_dx": 0.0, "camera_dy": 0.0, "hotbar": 0,
    "forward": False, "back": False, "left": False, "right": False,
    "sprint": False, "sneak": False, "use": False, "attack": False,
    "jump": False, "drop": False, "pick_item": False,
}


def test_noop_produces_exactly_eleven_center_tokens():
    env = raw_to_env_action(NOOP_RAW)
    tokens = env_action_to_tokens(env)
    assert len(tokens) == N_ACTION_TOKENS
    assert tokens[0] == ACTION_VOCAB_OFFSET  # act_bos
    center = CAMERA_BINS // 2
    assert tokens[1] == ACTION_VOCAB_OFFSET + 1 + center          # camera_dy
    assert tokens[2] == ACTION_VOCAB_OFFSET + 1 + CAMERA_BINS + center  # camera_dx


def test_camera_binning_is_symmetric_and_saturates():
    center = CAMERA_BINS // 2
    assert bin_camera(0.0) == center
    assert bin_camera(10.0) == CAMERA_BINS - 1
    assert bin_camera(-10.0) == 0
    assert bin_camera(999.0) == CAMERA_BINS - 1
    assert bin_camera(-999.0) == 0
    assert bin_camera(float("nan")) == center
    for deg in (1.0, 3.7, 9.9):
        assert bin_camera(deg) + bin_camera(-deg) == CAMERA_BINS - 1


def test_camera_impulse_moves_only_the_camera_token():
    base = env_action_to_tokens(raw_to_env_action(NOOP_RAW))
    flick = dict(NOOP_RAW, camera_dx=8.0)
    tokens = env_action_to_tokens(raw_to_env_action(flick))
    diffs = [i for i, (a, b) in enumerate(zip(base, tokens)) if a != b]
    assert diffs == [2]  # only the camera_dx slot changed


def test_hotbar_is_clipped_into_range():
    # Every slot value is derived defensively (clip/_tri/bool), so no public
    # input can reach the internal range assertion; the observable contract
    # is saturation.
    tokens = env_action_to_tokens(raw_to_env_action(dict(NOOP_RAW, hotbar=99)))
    base = env_action_to_tokens(raw_to_env_action(dict(NOOP_RAW, hotbar=8)))
    assert tokens == base  # out-of-range hotbar saturates to slot 8


def test_write_mineworld_actions_records_converter_identity(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=4)
    frame_map, report = align_episode(server_dir, client_dir)
    assert report.accepted
    out = tmp_path / "mineworld_actions.jsonl"
    count = write_mineworld_actions(frame_map, str(out))
    assert count == 4
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert all(len(row["tokens"]) == N_ACTION_TOKENS for row in rows)
    assert all(row["converter_id"] == REFERENCE_CONVERTER_ID for row in rows)
    assert [row["action_idx"] for row in rows] == list(range(4))


def test_pluggable_pinned_converter_is_used_and_validated(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=2)
    frame_map, _ = align_episode(server_dir, client_dir)

    def pinned(env):
        return list(range(N_ACTION_TOKENS))

    out = tmp_path / "pinned.jsonl"
    write_mineworld_actions(frame_map, str(out), tokenizer=pinned,
                            converter_id="mineworld_mcdataset_pinned_v1")
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert rows[0]["converter_id"] == "mineworld_mcdataset_pinned_v1"

    def broken(env):
        return [0] * 10  # wrong token count must fail loudly

    with pytest.raises(ValueError, match="10 tokens"):
        write_mineworld_actions(frame_map, str(tmp_path / "broken.jsonl"),
                                tokenizer=broken, converter_id="broken")
