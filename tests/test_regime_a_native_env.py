from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/provision_capture_runtime_sagemaker.sh"
REQUIRED_TOOLS = ("Xvfb", "xdpyinfo", "xdotool", "openbox")


def run(subcommand: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    """Invoke the launcher contract from a deliberately bare environment.

    PATH and LD_LIBRARY_PATH are stripped to what a non-interactive service
    would inherit, so the test proves the launcher constructs the native
    environment itself instead of depending on an operator's exported shell.
    """

    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PATH", "LD_LIBRARY_PATH", "LIBGL_DRIVERS_PATH"}
    }
    environment["PATH"] = "/usr/bin:/bin"
    environment.update(overrides)
    return subprocess.run(
        ["bash", str(SCRIPT), subcommand],
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )


class NativeDisplayEnvironmentTests(unittest.TestCase):
    def test_launcher_resolves_display_tools_without_an_exported_shell(self) -> None:
        result = run("verify-native-env")
        self.assertEqual(
            result.returncode,
            0,
            f"launcher could not resolve display tools: {result.stderr}",
        )

    def test_constructed_environment_carries_the_operator_library_roots(self) -> None:
        result = run("print-native-env")
        self.assertEqual(result.returncode, 0, result.stderr)
        values = dict(
            line.split("=", 1)
            for line in result.stdout.splitlines()
            if "=" in line
        )
        self.assertTrue(values.get("LD_LIBRARY_PATH"), "LD_LIBRARY_PATH was not established")
        for entry in values["LD_LIBRARY_PATH"].split(":"):
            self.assertTrue(Path(entry).is_dir(), f"library path does not exist: {entry}")
        for name in ("XDG_DATA_DIRS", "XDG_CONFIG_DIRS", "FONTCONFIG_PATH"):
            self.assertTrue(Path(values[name]).is_dir(), f"{name} does not exist")
        self.assertTrue(Path(values["FONTCONFIG_FILE"]).is_file())

    def test_missing_operator_tools_fails_closed_and_names_the_tools(self) -> None:
        result = run("verify-native-env", MINEOCCLUDE_OPERATOR_TOOLS="/nonexistent")
        self.assertNotEqual(result.returncode, 0)
        for tool in REQUIRED_TOOLS:
            self.assertIn(tool, result.stderr)


if __name__ == "__main__":
    unittest.main()
