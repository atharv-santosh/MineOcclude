from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "person_b"


class TestPersonBScripts(unittest.TestCase):
    def test_target_builder_cli_matches_checked_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "targets.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_oracle_targets.py"),
                    str(FIXTURES / "synthetic_state_log.json"),
                    str(output),
                    "--run-id",
                    "synthetic_person_b_oracle_run_001",
                    "--code-sha",
                    "a" * 40,
                    "--config-hash",
                    "b" * 64,
                ],
                cwd=ROOT,
                check=True,
            )
            actual = json.loads(output.read_text(encoding="utf-8"))
            expected = json.loads(
                (FIXTURES / "synthetic_oracle_targets.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(actual, expected)

    def test_plot_cli_contains_every_required_series(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "oracle.svg"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "plot_oracle_fixture.py"),
                    str(FIXTURES / "synthetic_oracle_targets.json"),
                    str(output),
                ],
                cwd=ROOT,
                check=True,
            )
            svg = output.read_text(encoding="utf-8")
            for label in (
                "posterior mean",
                "last visible position",
                "truth (scoring only)",
                "+/-1 sigma (outer: +/-2)",
                "model frame index",
            ):
                with self.subTest(label=label):
                    self.assertIn(label, svg)


if __name__ == "__main__":
    unittest.main()
