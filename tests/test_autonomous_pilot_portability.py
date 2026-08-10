"""Focused platform-orchestration tests for the autonomous capture driver."""
from types import SimpleNamespace
from unittest.mock import patch

import scripts.run_autonomous_pilot as pilot


def test_linux_focus_targets_unique_minecraft_window():
    results = [
        SimpleNamespace(stdout="4194307\n"),
        SimpleNamespace(stdout=""),
        SimpleNamespace(stdout="4194307\n"),
    ]
    with patch.object(pilot.sys, "platform", "linux"), \
            patch.dict(pilot.os.environ, {"DISPLAY": ":99"}), \
            patch.object(pilot.subprocess, "run", side_effect=results) as run:
        assert pilot.focus_client()
    assert run.call_args_list[0].args[0] == [
        "xdotool", "search", "--onlyvisible", "--name", r"^Minecraft"
    ]
    assert run.call_args_list[1].args[0] == [
        "xdotool", "windowactivate", "--sync", "4194307"
    ]
    assert run.call_args_list[2].args[0] == ["xdotool", "getwindowfocus"]


def test_linux_focus_fails_closed_without_display():
    with patch.object(pilot.sys, "platform", "linux"), \
            patch.dict(pilot.os.environ, {}, clear=True), \
            patch.object(pilot.subprocess, "run") as run:
        assert not pilot.focus_client()
    run.assert_not_called()


def test_linux_focus_rejects_ambiguous_clients():
    result = SimpleNamespace(stdout="4194307\n4194308\n")
    with patch.object(pilot.sys, "platform", "linux"), \
            patch.dict(pilot.os.environ, {"DISPLAY": ":99"}), \
            patch.object(pilot.subprocess, "run", return_value=result) as run:
        assert not pilot.focus_client()
    assert run.call_count == 1


def test_capturing_jar_prefers_accepted_runtime_artifact(tmp_path):
    mods = tmp_path / "mods"
    mods.mkdir()
    accepted = mods / "mineocclude-0.1.1.jar"
    accepted.write_bytes(b"accepted")
    with patch.object(pilot, "SRV", str(tmp_path)), \
            patch.dict(pilot.os.environ, {}, clear=True):
        assert pilot._capturing_jar_path() == str(accepted)
