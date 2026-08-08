"""Focused fail-closed tests for the Week 1 closeout validator."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from mineocclude.analysis import week1_closeout_v0_1 as closeout

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / closeout.PACKAGE_DIRECTORY


def _canonical(value: Any) -> bytes:
    return closeout.canonical_json_bytes(value)


def _copy_package(tmp_path: Path) -> Path:
    destination = tmp_path / "package"
    shutil.copytree(PACKAGE_ROOT, destination)
    return destination


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _refresh_inventory(package: Path) -> None:
    inventory_path = package / "sha256_inventory.json"
    inventory = _load(inventory_path)
    files = inventory["files"]
    for name in closeout.INVENTORIED_FILES:
        raw = (package / name).read_bytes()
        files[name] = {"sha256": closeout.sha256_bytes(raw), "byte_size": len(raw)}
    inventory_path.write_bytes(_canonical(inventory))


def _mutate_json(package: Path, name: str, mutation) -> None:
    path = package / name
    document = _load(path)
    mutation(document)
    path.write_bytes(_canonical(document))
    _refresh_inventory(package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_valid_package() -> None:
    result = closeout.validate(REPOSITORY_ROOT)
    assert result["status"] == "PASS"
    assert result["step_count"] == 85
    assert result["phase_count"] == 10


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_quadratic_tau_step_has_committed_scope_evidence() -> None:
    roadmap = _load(PACKAGE_ROOT / "roadmap_completion_matrix.json")
    step = next(row for row in roadmap["steps"] if row["step_id"] == "5.5")
    assert step["status"] == "complete_current"
    assert step["evidence_paths"] == [
        "src/mineocclude/metrics/u2_calibration.py",
        "tests/metrics/test_person_b_metrics.py",
    ]
    assert "uncommitted" not in step["remaining_condition"].casefold()
    assert "concurrent" not in step["remaining_condition"].casefold()


def test_starting_authority_allows_descendants_and_rejects_unrelated_heads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closeout._require_current_head_descends_from_starting_authority(REPOSITORY_ROOT)
    monkeypatch.setattr(closeout, "_git_head", lambda _: closeout.HANDOFF_COMMIT)
    with pytest.raises(closeout.CloseoutValidationError, match="unrelated"):
        closeout._require_current_head_descends_from_starting_authority(
            REPOSITORY_ROOT
        )


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
@pytest.mark.parametrize(
    ("name", "mutation"),
    [
        ("wrong_handoff_commit", lambda d: d.__setitem__("handoff_commit", "0" * 40)),
        (
            "wrong_handoff_hash",
            lambda d: d["handoff"].__setitem__("raw_sha256", "0" * 64),
        ),
    ],
)
def test_wrong_handoff_commit_or_hash(tmp_path: Path, name: str, mutation) -> None:
    package = _copy_package(tmp_path)
    _mutate_json(package, "authority_binding.json", mutation)
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_mutated_handoff_count(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate_json(
        package,
        "scope_shortfall.json",
        lambda d: d.__setitem__("admitted_sample_count", 1694),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_wrong_source_hash_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    original = closeout._git_blob

    # Alter the first source blob returned by the exact Git-object read.
    seen = {"count": 0}

    def tamper_source(repository_root: Path, commit: str, path: str) -> bytes:
        payload = original(repository_root, commit, path)
        if commit != closeout.HANDOFF_COMMIT and seen["count"] == 0:
            seen["count"] += 1
            return payload + b"x"
        return payload

    monkeypatch.setattr(closeout, "_git_blob", tamper_source)
    with pytest.raises(closeout.CloseoutValidationError):
        closeout._validate_handoff(REPOSITORY_ROOT)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_wrong_step4_1_promotion(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        next(row for row in document["steps"] if row["step_id"] == "4.1")["status"] = (
            "complete_current"
        )
        document["status_counts"]["superseded_marker"] -= 1
        document["status_counts"]["complete_current"] += 1

    _mutate_json(package, "roadmap_completion_matrix.json", mutate)
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_missing_or_duplicate_step(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate_json(package, "roadmap_completion_matrix.json", lambda d: d["steps"].pop())
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)

    package = _copy_package(tmp_path / "duplicate")

    def duplicate(document: dict[str, Any]) -> None:
        document["steps"][-1]["step_id"] = document["steps"][0]["step_id"]

    _mutate_json(package, "roadmap_completion_matrix.json", duplicate)
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_wrong_step_or_phase_count(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate_json(
        package,
        "roadmap_completion_matrix.json",
        lambda d: d.__setitem__("roadmap_step_count", 84),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)

    package = _copy_package(tmp_path / "phase")
    _mutate_json(
        package,
        "roadmap_completion_matrix.json",
        lambda d: d.__setitem__("phase_count", 9),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)

    package = _copy_package(tmp_path / "summary")
    _mutate_json(
        package,
        "roadmap_completion_matrix.json",
        lambda d: d["phases"][5]["status_counts"].__setitem__(
            "complete_current", 0
        ),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_roadmap_u4_evidence_path_rejected(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["steps"][0]["evidence_paths"].append("docs/status/U4/inspection.json")

    _mutate_json(package, "roadmap_completion_matrix.json", mutate)
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_false_phase7_completion(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        next(row for row in document["steps"] if row["step_id"] == "7.1")["status"] = (
            "complete_scoped"
        )
        document["status_counts"]["blocked_external"] -= 1
        document["status_counts"]["complete_scoped"] += 1

    _mutate_json(package, "roadmap_completion_matrix.json", mutate)
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_wrong_shortfall(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate_json(
        package, "scope_shortfall.json", lambda d: d["missing"].__setitem__("total", 55)
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_u4_authorization_or_inspection(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate_json(
        package,
        "checkpoint_decision.json",
        lambda d: d.__setitem__("u4_authorized", True),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)

    package = _copy_package(tmp_path / "inspection")
    _mutate_json(
        package,
        "checkpoint_decision.json",
        lambda d: d.__setitem__("u4_output_inspected", True),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_science_claim_or_result_tag(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate_json(
        package,
        "reproducibility_status.json",
        lambda d: d.__setitem__("scientific_execution_performed", True),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)

    package = _copy_package(tmp_path / "tag")
    _mutate_json(
        package,
        "reproducibility_status.json",
        lambda d: d.__setitem__("result_tag", "mvp-result"),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_checkpoint_overclaim_or_belief_absence(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate_json(
        package,
        "checkpoint_decision.json",
        lambda d: d.__setitem__("decision", "GREEN"),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)

    package = _copy_package(tmp_path / "belief")
    _mutate_json(
        package,
        "checkpoint_decision.json",
        lambda d: d.__setitem__("belief_absence_proof", True),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


def test_noncanonical_json_rejected() -> None:
    value = {"schema_version": "1.0", "schema_id": closeout.SCHEMA_ID}
    raw = (
        b'{"schema_id":"'
        + closeout.SCHEMA_ID.encode()
        + b'", "schema_version":"1.0"}\n'
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.load_strict_json(raw, "test", canonical=True)
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.load_strict_json(b'{"x": 1, "x": 2}\n', "test", canonical=False)
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.load_strict_json(b'{"x": NaN}\n', "test", canonical=False)
    assert _canonical(value).endswith(b"\n")


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_inventory_mismatch(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    inventory_path = package / "sha256_inventory.json"
    inventory = _load(inventory_path)
    inventory["files"]["checkpoint_memo.md"]["byte_size"] += 1
    inventory_path.write_bytes(_canonical(inventory))
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)


@pytest.mark.skipif(
    not PACKAGE_ROOT.is_dir(),
    reason="closeout package is supplied by package-authoring agent",
)
def test_no_result_tag(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate_json(
        package,
        "validation_receipt.json",
        lambda d: d.__setitem__("result_tag", "week1-result"),
    )
    with pytest.raises(closeout.CloseoutValidationError):
        closeout.validate(REPOSITORY_ROOT, package_root=package)
