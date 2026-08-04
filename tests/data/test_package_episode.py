"""The C0 handoff bridge: an accepted bundle must pass the FROZEN validator
chain (C capture contract + A trajectory validator) after assembly."""

import glob
import os

import mineocclude.contracts  # noqa: F401  (pre-existing import-order cycle)
from mineocclude.data.build_dataset import process_episode
from mineocclude.data.noise_schedule import generate_noise_schedule, write_schedule
from mineocclude.data.package_episode import assemble_package, package_and_validate

from tests.data.synthetic_episode import make_episode


def _build_accepted_bundle(tmp_path):
    server_dir, client_dir = make_episode(
        str(tmp_path), n=12,
        visible_pattern=[True] * 4 + [False] * 4 + [True] * 4,
        yaw_impulses={2: 6.0, 9: 6.0, 11: 6.0},
    )
    out_root = str(tmp_path / "out")
    summary = process_episode(server_dir, client_dir, out_root)
    assert summary["accepted"], summary["problems"]
    schedule = generate_noise_schedule(seed=42, n_draws=12, q=0.05)
    schedule_path = str(tmp_path / "schedule.jsonl")
    write_schedule(schedule, schedule_path)
    out_dir = os.path.dirname(summary["frame_map"])
    return out_dir, server_dir, client_dir, schedule_path


def test_assembled_package_passes_frozen_validator_chain(tmp_path):
    out_dir, server_dir, client_dir, schedule_path = _build_accepted_bundle(tmp_path)
    package, result = package_and_validate(
        out_dir, server_dir, client_dir, schedule_path,
        repo_root=os.getcwd(), run_id="synthetic_bridge_test",
    )
    assert result.accepted, [r.message for r in result.rejections]
    # The accepted package file and its hash sidecar are written.
    assert os.path.isfile(os.path.join(out_dir, "capture_package_v0_1.json"))
    assert os.path.isfile(os.path.join(out_dir, "capture_package_v0_1.json.sha256"))
    # Stream artifacts exist as JSONL with recorded hashes.
    for name in ("raw_actions", "normalized_actions", "server_state",
                 "client_tick_log", "frame_map", "visibility", "seed_noise"):
        assert package["artifacts"][name]["format"] == "jsonl"
        assert os.path.isfile(package["artifacts"][name]["path"])
    # Real pin, not the sentinel: a real package must carry the exact NumPy
    # version.
    assert package["episode_manifest"]["rng"]["numpy_version"] not in (
        "", "PIN_REQUIRED_BEFORE_RUNTIME",
    )
    assert package["synthetic"] is False


def test_wrong_schedule_seed_is_rejected(tmp_path):
    out_dir, server_dir, client_dir, _ = _build_accepted_bundle(tmp_path)
    bad = generate_noise_schedule(seed=999, n_draws=12, q=0.05)
    bad_path = str(tmp_path / "bad_schedule.jsonl")
    write_schedule(bad, bad_path)
    package = assemble_package(
        out_dir, server_dir, client_dir, bad_path,
        repo_root=os.getcwd(), run_id="synthetic_bridge_test",
    )
    from mineocclude.data.capture_contract import validate_capture_package
    result = validate_capture_package(package)
    # Package seed (42) disagrees with the schedule seed (999): the frozen
    # chain must reject, never repair.
    assert not result.accepted
    # No accepted-package file may exist for a rejected assembly via the
    # validating entry point.
    assert not glob.glob(os.path.join(out_dir, "capture_package_v0_1.json"))
