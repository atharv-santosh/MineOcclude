from __future__ import annotations

import inspect
import subprocess
from pathlib import Path
from unittest.mock import call, patch

import pytest

from scripts import run_large_scale_no_wall_campaign as campaign
from scripts import run_regime_a


WINDOW_ID = "4194311"
WINDOW_TITLE = "Minecraft* 1.16.5 - Multiplayer (3rd-party Server)"
GEOMETRY = "\n".join(
    [
        f"WINDOW={WINDOW_ID}",
        "X=1",
        "Y=20",
        "WIDTH=640",
        "HEIGHT=360",
        "SCREEN=0",
    ]
)


def successful_xdotool(*arguments: str) -> str:
    responses = {
        ("search", "--onlyvisible", "--class", campaign.MINECRAFT_WINDOW_CLASS): WINDOW_ID,
        ("getwindowname", WINDOW_ID): WINDOW_TITLE,
        ("getwindowpid", WINDOW_ID): "12741",
        ("getwindowgeometry", "--shell", WINDOW_ID): GEOMETRY,
        ("windowactivate", "--sync", WINDOW_ID): "",
        ("getactivewindow",): WINDOW_ID,
        ("getwindowfocus",): WINDOW_ID,
    }
    return responses[arguments]


def test_exact_minecraft_client_selected_among_other_x11_windows() -> None:
    with patch.object(campaign, "_xdotool", side_effect=successful_xdotool) as xdotool, patch.object(
        campaign, "_expected_client_process", return_value=True
    ):
        assert campaign._focus_client_once()
    assert xdotool.call_args_list[0] == call(
        "search", "--onlyvisible", "--class", r"^Minecraft\* 1\.16\.5$"
    )


def test_wrong_non_minecraft_window_is_rejected() -> None:
    def wrong_title(*arguments: str) -> str:
        if arguments[0] == "search":
            return WINDOW_ID
        if arguments[0] == "getwindowname":
            return "Minecraft Launcher"
        raise AssertionError(arguments)

    with patch.object(campaign, "_xdotool", side_effect=wrong_title):
        assert not campaign._focus_client_once()


def test_ambiguous_or_absent_window_fails_closed() -> None:
    with patch.object(campaign, "_xdotool", return_value=f"{WINDOW_ID}\n4194312"):
        assert not campaign._focus_client_once()
    with patch.object(
        campaign,
        "_xdotool",
        side_effect=subprocess.CalledProcessError(1, ["xdotool", "search"]),
    ):
        assert not campaign._focus_client_once()


def test_focus_command_success_with_wrong_active_window_is_rejected() -> None:
    def wrong_active(*arguments: str) -> str:
        if arguments == ("getactivewindow",):
            return "4194312"
        return successful_xdotool(*arguments)

    with patch.object(campaign, "_xdotool", side_effect=wrong_active), patch.object(
        campaign, "_expected_client_process", return_value=True
    ):
        assert not campaign._focus_client_once()


def test_focus_command_success_with_wrong_input_focus_is_rejected() -> None:
    def wrong_focus(*arguments: str) -> str:
        if arguments == ("getwindowfocus",):
            return "4194312"
        return successful_xdotool(*arguments)

    with patch.object(campaign, "_xdotool", side_effect=wrong_focus), patch.object(
        campaign, "_expected_client_process", return_value=True
    ):
        assert not campaign._focus_client_once()


@pytest.mark.parametrize(
    "output",
    ["not-a-window", "0", f"{WINDOW_ID}\nmalformed"],
)
def test_malformed_window_search_output_fails_closed(output: str) -> None:
    assert campaign._parse_window_ids(output) == []


def test_wrong_or_malformed_render_geometry_fails_closed() -> None:
    assert not campaign._parse_window_geometry(
        GEOMETRY.replace("WIDTH=640", "WIDTH=641"), WINDOW_ID
    )
    assert not campaign._parse_window_geometry("malformed", WINDOW_ID)


def test_timeout_fails_closed() -> None:
    with patch.object(campaign, "_focus_client_once", return_value=False), patch.object(
        campaign.time, "monotonic", side_effect=[0.0, 10.0]
    ):
        assert not campaign.focus_client(timeout_seconds=10.0)


def test_bounded_delayed_window_readiness_succeeds() -> None:
    with patch.object(
        campaign, "_focus_client_once", side_effect=[False, False, True]
    ), patch.object(
        campaign.time, "monotonic", side_effect=[0.0, 1.0, 2.0]
    ), patch.object(campaign.time, "sleep") as sleep:
        assert campaign.focus_client(timeout_seconds=10.0, poll_interval=0.1)
    assert sleep.call_count == 2


def test_client_process_identity_mismatch_fails_closed() -> None:
    with patch.object(campaign, "_xdotool", side_effect=successful_xdotool), patch.object(
        campaign, "_expected_client_process", return_value=False
    ):
        assert not campaign._focus_client_once()


def test_precheck_focus_failure_remains_fail_closed(tmp_path: Path) -> None:
    server = tmp_path / "server"
    client = tmp_path / "client"
    server.joinpath("logs").mkdir(parents=True)
    client.mkdir()
    server.joinpath("logs/latest.log").write_text(
        "server ready\nC1Observer joined the game\n", encoding="utf-8"
    )
    required_files = [tmp_path / name for name in ("java", "Xvfb", "xdotool", "fifo")]
    for path in required_files:
        path.touch()
    runtime = campaign.LiveRuntime()
    runtime.server_root = server
    runtime.client_root = client
    with patch.multiple(
        campaign,
        JAVA_PATH=required_files[0],
        XVFB_PATH=required_files[1],
        XDOTOOL_PATH=required_files[2],
        FIFO=required_files[3],
    ), patch.object(campaign, "focus_client", return_value=False):
        with pytest.raises(campaign.CampaignError, match="client focus failed"):
            runtime.precheck()


def test_precheck_rejects_frozen_camera_authority_drift(tmp_path: Path) -> None:
    server = tmp_path / "server"
    client = tmp_path / "client"
    server.joinpath("logs").mkdir(parents=True)
    client.joinpath("mineocclude_client_authority").mkdir(parents=True)
    server.joinpath("logs/latest.log").write_text(
        "server ready\nC1Observer joined the game\n"
        f"{campaign.FIXED_CAMERA_LOG_MARKER}\n",
        encoding="utf-8",
    )
    client.joinpath("mineocclude_client_authority/fov_receipt.json").write_text(
        '{"status":"PINNED","fov_degrees":71.0,"fov_effect_scale":0.0}\n',
        encoding="utf-8",
    )
    required_files = [tmp_path / name for name in ("java", "Xvfb", "xdotool", "fifo")]
    for path in required_files:
        path.touch()
    runtime = campaign.LiveRuntime()
    runtime.server_root = server
    runtime.client_root = client
    with patch.multiple(
        campaign,
        JAVA_PATH=required_files[0],
        XVFB_PATH=required_files[1],
        XDOTOOL_PATH=required_files[2],
        FIFO=required_files[3],
    ), patch.object(campaign, "focus_client", return_value=True):
        with pytest.raises(campaign.CampaignError, match="frozen FOV/fixed camera mismatch"):
            runtime.precheck()


def test_camera_precheck_precedes_startspec_in_regime_a() -> None:
    ensure_source = inspect.getsource(run_regime_a.ProductionCaptureWorker._ensure_started)
    capture_source = inspect.getsource(run_regime_a.ProductionCaptureWorker.capture)
    assert "self.runtime.precheck()" in ensure_source
    assert capture_source.index("self._ensure_started()") < capture_source.index(
        "mineocclude startspec"
    )
