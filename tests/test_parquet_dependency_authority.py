"""Guards for Person A's sole approved Parquet dependency."""

from __future__ import annotations

import hashlib
import runpy
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"
LOCAL_ENV = ROOT / "configs" / "environments" / "mineworld_local_cpu.yml"
AWS_ENV = ROOT / "configs" / "environments" / "mineworld_aws_l4.yml"
ENV_VALIDATOR = ROOT / "scripts" / "check_env.py"
DECISION = ROOT / "docs" / "status" / (
    "person_a_phase3_parquet_dependency_decision.md"
)
PHASE5_DECISION = ROOT / "docs" / "status" / (
    "person_a_phase5_storage_decision.md"
)
PHASE5_STORE = ROOT / "src" / "mineocclude" / "activations" / "store.py"

PYARROW_PIN = "pyarrow==25.0.0"
NUMPY_PIN = "numpy==1.26.4"
PANDAS_PIN = "pandas==2.3.3"
PHASE5_DECISION_SHA256 = (
    "d02a6be1f9346ad7ae54fea5a809ac4466d409ecbaf74e179c9849193399ae2d"
)
PHASE5_STORE_SHA256 = (
    "d27a9044b04e51c2cb74ff94c4109230a3b02fef62eb4b45c1e7cb5f2d9d00e1"
)
# The commit immediately before pyarrow was authorized. Comparing against this
# fixed point keeps the guard durable; comparing against HEAD only held while
# the pyarrow change was still uncommitted.
PRE_PYARROW_COMMIT = "f0a4fed546eb1cf19a7094e6b99399a58294726a"
MINEWORLD_REVISION = "9f49efbcc68a5f0cf60e78f0abc566eac409282f"

# Python writes bytecode caches into any package it imports, including the
# pinned external checkout. A generated cache is not a modification of the
# dependency, so it is excluded; every other status line still fails the guard.
IGNORED_EXTERNAL_STATUS_PATHS = ("__pycache__/",)
MINEWORLD_REQUIREMENTS_SHA256 = (
    "b58d7e3514e7f9787ddd428fdc755e08cb48a75dd3cd09a4e1fc8e4c210af38c"
)
PRE_PYARROW_ENVIRONMENT_REVISION = (
    "f0a4fed546eb1cf19a7094e6b99399a58294726a"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pip_dependencies(path: Path) -> list[str]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    pip_sections = [
        entry["pip"]
        for entry in document["dependencies"]
        if isinstance(entry, dict) and set(entry) == {"pip"}
    ]
    assert len(pip_sections) == 1
    return pip_sections[0]


def test_authoritative_surfaces_use_one_exact_pyarrow_pin() -> None:
    requirement_lines = [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert requirement_lines == [PYARROW_PIN]

    for environment in (LOCAL_ENV, AWS_ENV):
        dependencies = _pip_dependencies(environment)
        assert dependencies.count(PYARROW_PIN) == 1
        assert not any(item.startswith("fastparquet") for item in dependencies)

    all_authorities = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REQUIREMENTS, LOCAL_ENV, AWS_ENV, ENV_VALIDATOR)
    ).lower()
    declared_engines = {
        engine
        for engine in ("pyarrow", "fastparquet")
        if f"{engine}==" in all_authorities
    }
    assert declared_engines == {"pyarrow"}


def test_environment_validator_requires_exact_version_and_import() -> None:
    namespace = runpy.run_path(str(ENV_VALIDATOR))
    assert namespace["EXPECTED_PACKAGES"]["pyarrow"] == "25.0.0"
    assert namespace["IMPORT_CHECKS"]["pyarrow"] == "pyarrow"
    matches = namespace["package_version_matches"]
    assert matches("pyarrow", "25.0.0", "25.0.0")
    assert not matches("pyarrow", "25.0.1", "25.0.0")
    assert not matches("pyarrow", "25.0.0+local", "25.0.0")


def test_existing_numpy_and_pandas_pins_are_unchanged() -> None:
    for environment in (LOCAL_ENV, AWS_ENV):
        dependencies = _pip_dependencies(environment)
        assert dependencies.count(NUMPY_PIN) == 1
        assert dependencies.count(PANDAS_PIN) == 1


def test_every_prequalified_environment_dependency_is_preserved() -> None:
    for environment in (LOCAL_ENV, AWS_ENV):
        relative = environment.relative_to(ROOT).as_posix()
        baseline_text = subprocess.run(
            ["git", "show", f"{PRE_PYARROW_COMMIT}:{relative}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        baseline = yaml.safe_load(baseline_text)
        current = yaml.safe_load(environment.read_text(encoding="utf-8"))
        current_pip = next(
            item["pip"]
            for item in current["dependencies"]
            if isinstance(item, dict) and set(item) == {"pip"}
        )
        current_pip.remove(PYARROW_PIN)
        assert current == baseline


def test_requirements_obsolete_phase1_wording_is_removed() -> None:
    contents = REQUIREMENTS.read_text(encoding="utf-8")
    assert "before MineOcclude-specific project dependencies are added" not in contents
    assert "reserves the authoritative dependency location during Phase 1" not in contents
    assert "sole approved Parquet implementation" in contents


def test_decision_does_not_claim_person_e_byte_determinism() -> None:
    contents = DECISION.read_text(encoding="utf-8")
    assert "**APPROVED:** `pyarrow==25.0.0`" in contents
    assert "does **not** prove" in contents
    assert "No U4 pushed-result content was inspected." in contents
    assert "No GPU was used." in contents


def test_phase5_decision_and_implementation_are_unchanged() -> None:
    assert _sha256(PHASE5_DECISION) == PHASE5_DECISION_SHA256
    assert _sha256(PHASE5_STORE) == PHASE5_STORE_SHA256


def test_external_mineworld_dependency_file_is_untouched() -> None:
    mineworld = ROOT.parent / "MineWorld-Upstream"
    if not mineworld.is_dir():
        pytest.skip("External pinned MineWorld checkout is not available")

    revision = subprocess.run(
        ["git", "-C", str(mineworld), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        [
            "git",
            "-C",
            str(mineworld),
            "status",
            "--short",
            "--untracked-files=no",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tracked_changes = [
        line
        for line in status.splitlines()
        if not any(
            line.strip().endswith(ignored) or ignored in line
            for ignored in IGNORED_EXTERNAL_STATUS_PATHS
        )
    ]
    assert revision == MINEWORLD_REVISION
    assert tracked_changes == []
    assert _sha256(mineworld / "requirements.txt") == (
        MINEWORLD_REQUIREMENTS_SHA256
    )
