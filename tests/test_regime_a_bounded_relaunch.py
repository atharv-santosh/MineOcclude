from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

from mineocclude.regime_a import RegimeAError
from scripts.run_regime_a import ProductionCaptureWorker


IDENTITY = {
    "trajectory_spec_id": "regime_a_integration_rehearsal_v1_ltr",
    "spec_hash": "a" * 64,
    "seed": 700001,
}


def worker(tmp_path: Path, *, launch: Mock, runtimes: list[Mock]) -> ProductionCaptureWorker:
    value = object.__new__(ProductionCaptureWorker)
    value.runtime_root = tmp_path
    value.runtime = None
    value.processes = []
    value.launch_attempts = 0
    value.launch_failures = []
    value.launch_attempt_history = []
    value.startspec_dispatch_attempted = False
    value.live = SimpleNamespace(
        DISPLAY=":99",
        launch_runtime=launch,
        LiveRuntime=Mock(side_effect=runtimes),
        stop_runtime=Mock(),
    )
    return value


def attempt_rows(tmp_path: Path) -> list[dict[str, object]]:
    path = tmp_path / "runtime_logs/pre_scientific_launch_attempts.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def ready_runtime() -> Mock:
    runtime = Mock()
    runtime.precheck.return_value = None
    return runtime


def test_first_attempt_success_records_readiness_and_identity(tmp_path: Path) -> None:
    processes = [Mock()]
    value = worker(
        tmp_path,
        launch=Mock(return_value=(processes, 1.25)),
        runtimes=[ready_runtime()],
    )

    observed_processes, attempts = value._launch_with_bounded_retry(IDENTITY)

    assert observed_processes is processes
    assert attempts == 1
    rows = attempt_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "READY"
    assert {key: rows[0][key] for key in IDENTITY} == IDENTITY
    assert rows[0]["startspec_dispatch_attempted"] is False


def test_first_failure_then_success_preserves_identity_and_reason(tmp_path: Path) -> None:
    processes = [Mock()]
    launch = Mock(side_effect=[RuntimeError("synthetic cold-start failure"), (processes, 2.0)])
    value = worker(tmp_path, launch=launch, runtimes=[ready_runtime()])

    with patch.object(value, "_teardown_failed_launch") as cleanup:
        observed_processes, attempts = value._launch_with_bounded_retry(IDENTITY)

    assert observed_processes is processes
    assert attempts == 2
    assert cleanup.call_args_list == [call([])]
    rows = attempt_rows(tmp_path)
    assert [row["outcome"] for row in rows] == ["FAILED", "READY"]
    assert "synthetic cold-start failure" in rows[0]["reason"]
    assert all({key: row[key] for key in IDENTITY} == IDENTITY for row in rows)


def test_repeated_failures_exhaust_three_attempt_bound(tmp_path: Path) -> None:
    launch = Mock(side_effect=RuntimeError("still unavailable"))
    value = worker(tmp_path, launch=launch, runtimes=[])

    with patch.object(value, "_teardown_failed_launch") as cleanup, pytest.raises(
        RegimeAError, match="failed on all 3 attempts"
    ):
        value._launch_with_bounded_retry(IDENTITY)

    assert launch.call_count == 3
    assert cleanup.call_count == 3
    rows = attempt_rows(tmp_path)
    assert len(rows) == 3
    assert all(row["outcome"] == "FAILED" for row in rows)
    assert all("still unavailable" in row["reason"] for row in rows)


def test_precheck_failure_sends_no_startspec_before_second_attempt_ready(
    tmp_path: Path,
) -> None:
    not_ready = Mock()
    not_ready.precheck.side_effect = RuntimeError("window not focused")
    not_ready.send = Mock()
    ready = ready_runtime()
    ready.send = Mock()
    first_processes, second_processes = [Mock()], [Mock()]
    value = worker(
        tmp_path,
        launch=Mock(side_effect=[(first_processes, 1.0), (second_processes, 1.0)]),
        runtimes=[not_ready, ready],
    )

    with patch.object(value, "_teardown_failed_launch") as cleanup:
        observed_processes, attempts = value._launch_with_bounded_retry(IDENTITY)

    assert observed_processes is second_processes
    assert attempts == 2
    assert cleanup.call_args_list == [call(first_processes)]
    not_ready.send.assert_not_called()
    ready.send.assert_not_called()
    assert [row["stage"] for row in attempt_rows(tmp_path)] == ["precheck", "precheck"]


def test_failed_launch_cleanup_stops_processes_kills_stale_runtime_and_waits(
    tmp_path: Path,
) -> None:
    processes = [Mock()]
    value = worker(tmp_path, launch=Mock(), runtimes=[])

    with patch("scripts.run_regime_a.subprocess.run") as run, patch(
        "scripts.run_regime_a.time.sleep"
    ) as sleep:
        value._teardown_failed_launch(processes)

    value.live.stop_runtime.assert_called_once_with(processes)
    assert run.call_args_list == [
        call(
            [
                "pkill",
                "-9",
                "-f",
                "provision_capture_runtime_sagemaker.sh start-display",
            ],
            check=False,
            capture_output=True,
        ),
        call(
            [
                "pkill",
                "-9",
                "-f",
                "provision_capture_runtime_sagemaker.sh start-server",
            ],
            check=False,
            capture_output=True,
        ),
        call(
            [
                "pkill",
                "-9",
                "-f",
                "provision_capture_runtime_sagemaker.sh start-client",
            ],
            check=False,
            capture_output=True,
        ),
        call(["pkill", "-9", "-f", "KnotClient"], check=False, capture_output=True),
        call(
            ["pkill", "-9", "-f", "fabric-server-launch"],
            check=False,
            capture_output=True,
        ),
        call(["pkill", "-9", "-x", "Xvfb"], check=False, capture_output=True),
        call(["pkill", "-9", "-x", "openbox"], check=False, capture_output=True),
    ]
    sleep.assert_called_once_with(3)


def test_startspec_send_failure_never_enters_runtime_relaunch(tmp_path: Path) -> None:
    value = worker(tmp_path, launch=Mock(), runtimes=[])
    runtime = Mock()
    runtime.log_text.return_value = ""
    runtime.send.side_effect = RuntimeError("synthetic FIFO interruption")
    value.runtime = runtime
    server_episode = tmp_path / "server/episode_41"
    client_episode = tmp_path / "client/episode_41"
    context = {
        "episode_id": 41,
        "frames": 260,
        "server_episode": server_episode,
        "client_episode": client_episode,
        "noise_path": tmp_path / "server/schedules/41.jsonl",
        "motion_path": tmp_path / "server/motion/41.json",
        "noise_bytes": b"noise\n",
        "motion_bytes": b"motion\n",
    }
    spec = {**IDENTITY, "motion_noise_q": 0.01, "start_world_x": -7.0}

    with patch.object(value, "_capture_context", return_value=context), pytest.raises(
        RuntimeError, match="FIFO interruption"
    ):
        value.capture(spec, tmp_path / "partial", validate_and_package=False)

    assert value.startspec_dispatch_attempted is True
    sent = runtime.send.call_args.args[0]
    startspec = next(command for command in sent if "mineocclude startspec" in command)
    assert IDENTITY["trajectory_spec_id"] in startspec
    assert str(IDENTITY["seed"]) in startspec
    with pytest.raises(RegimeAError, match="forbidden after startspec"):
        value._launch_with_bounded_retry(IDENTITY)
    value.live.launch_runtime.assert_not_called()


def test_resume_capture_regenerates_only_bounded_postcapture_derivatives(
    tmp_path: Path,
) -> None:
    value = object.__new__(ProductionCaptureWorker)
    partial = tmp_path / "trajectories/.rehearsal.partial"
    raw = partial / "raw"
    frames = raw / "frames"
    frames.mkdir(parents=True)
    (partial / "partial_identity.json").write_text("{}\n")
    for index in range(2):
        (frames / f"{index:06d}.png").write_bytes(f"png-{index}".encode())
    server_episode = tmp_path / "server/episode_41"
    client_episode = tmp_path / "client/episode_41"
    server_episode.mkdir(parents=True)
    client_episode.mkdir(parents=True)
    source_pairs = (
        ("server_state.jsonl", server_episode / "server_state.jsonl"),
        ("client_tick.jsonl", client_episode / "client_tick.jsonl"),
        ("actions.jsonl", client_episode / "raw_actions.jsonl"),
    )
    for relative, source in source_pairs:
        payload = f"{relative}\n".encode()
        (raw / relative).write_bytes(payload)
        source.write_bytes(payload)
    source_frames = client_episode / "frames"
    source_frames.mkdir()
    for index in range(2):
        (source_frames / f"{index:06d}.png").write_bytes(f"png-{index}".encode())
    (server_episode / "reset_result.json").write_text(
        json.dumps({"episode_id": 41, **IDENTITY}) + "\n"
    )
    (client_episode / "capture_complete.json").write_text(
        json.dumps(
            {
                "episode_id": 41,
                "frame_count": 2,
                "final_render_frame_idx": 1,
                "pending_writes": 0,
                "writer_errors": 0,
                "drained": True,
            }
        )
        + "\n"
    )
    noise_path = tmp_path / "server/noise.jsonl"
    motion_path = tmp_path / "server/motion.json"
    noise_path.write_bytes(b"noise\n")
    motion_path.write_bytes(b"motion\n")
    context = {
        "episode_id": 41,
        "frames": 2,
        "server_episode": server_episode,
        "client_episode": client_episode,
        "noise_path": noise_path,
        "motion_path": motion_path,
        "noise_bytes": b"noise\n",
        "motion_bytes": b"motion\n",
    }
    value._capture_context = Mock(return_value=context)
    (raw / "visibility.jsonl").write_text("derived\n")
    (raw / "frame_map.jsonl").write_text("derived\n")
    (partial / "coordinates.jsonl").write_text("derived\n")
    validation = partial / "capture_validation/layout_01_ep41"
    validation.mkdir(parents=True)
    (validation / "interrupted.mp4.frames.txt").write_text("derived\n")

    def assert_clean(_spec, observed_partial, _context):
        assert not (observed_partial / "raw/visibility.jsonl").exists()
        assert not (observed_partial / "raw/frame_map.jsonl").exists()
        assert not (observed_partial / "coordinates.jsonl").exists()
        assert not (observed_partial / "capture_validation").exists()

    value._validate_and_package = Mock(side_effect=assert_clean)

    assert value.resume_capture(IDENTITY, partial) is True
    value._validate_and_package.assert_called_once_with(IDENTITY, partial, context)
