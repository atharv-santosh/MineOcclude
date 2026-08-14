from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts/provision_capture_runtime_sagemaker.sh"
QUALIFIED_JAVA_HOME = Path(
    "/home/sagemaker-user/.local/jdks/amazon-corretto-17.0.20.8.1-linux-x64"
)


def fake_java_home(tmp_path: Path, output: str, *, exit_code: int = 0) -> Path:
    java_home = tmp_path / "jdk"
    java = java_home / "bin/java"
    java.parent.mkdir(parents=True)
    java.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' {shlex.quote(output)} >&2\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    java.chmod(0o755)
    return java_home


def verify(java_home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(LAUNCHER), "verify-java"],
        cwd=ROOT,
        env={**os.environ, "JAVA_HOME": str(java_home)},
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "output",
    [
        (
            'openjdk version "17.0.20" 2026-07-21 LTS\n'
            "OpenJDK Runtime Environment Corretto-17.0.20.8.1 "
            "(build 17.0.20+8-LTS)\n"
            "OpenJDK 64-Bit Server VM Corretto-17.0.20.8.1 "
            "(build 17.0.20+8-LTS, mixed mode, sharing)"
        ),
        (
            'openjdk version "17.0.19" 2025-04-15\n'
            "OpenJDK Runtime Environment Temurin-17.0.19+10 "
            "(build 17.0.19+10)\n"
            "OpenJDK 64-Bit Server VM Temurin-17.0.19+10 "
            "(build 17.0.19+10, mixed mode, sharing)"
        ),
    ],
    ids=["qualified-corretto-17.0.20+8", "approved-17.0.19+10"],
)
def test_exact_approved_java_outputs_are_accepted(tmp_path: Path, output: str) -> None:
    assert verify(fake_java_home(tmp_path, output)).returncode == 0


@pytest.mark.parametrize(
    "output",
    [
        (
            'openjdk version "21.0.8" 2025-07-15 LTS\n'
            "OpenJDK Runtime Environment Corretto-21.0.8.9.1 (build 21.0.8+9-LTS)"
        ),
        (
            'openjdk version "17.0.21" 2026-10-20 LTS\n'
            "OpenJDK Runtime Environment Corretto-17.0.21.9.1 (build 17.0.21+9-LTS)"
        ),
        "not java version output",
    ],
    ids=["wrong-major", "unapproved-java-17-build", "malformed"],
)
def test_unapproved_or_malformed_java_outputs_are_rejected(
    tmp_path: Path, output: str
) -> None:
    result = verify(fake_java_home(tmp_path, output))
    assert result.returncode != 0
    assert "Approved Java" in result.stderr


def test_java_version_command_failure_is_rejected(tmp_path: Path) -> None:
    result = verify(fake_java_home(tmp_path, "synthetic failure", exit_code=3))
    assert result.returncode != 0
    assert "failed version inspection" in result.stderr


def test_absent_java_fails_closed(tmp_path: Path) -> None:
    result = verify(tmp_path / "missing-jdk")
    assert result.returncode != 0
    assert "Pinned Java executable is absent" in result.stderr


def test_exact_qualified_java_home_resolves() -> None:
    assert QUALIFIED_JAVA_HOME.is_dir()
    assert verify(QUALIFIED_JAVA_HOME).returncode == 0
