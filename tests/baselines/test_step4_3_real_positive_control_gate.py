"""Tests for the real Step 4.3 no-wall positive-control gate script.

Reads Person B's real row-universe/oracle-target records and real
66-cell pre-activation fold manifest directly via
``git show <commit>:<path>`` -- the same commits every frozen hash
constant these modules use was already independently derived from --
never a checkout, merge, or copy of either branch.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "run_person_d_step4_3_real_positive_control_gate",
        REPO_ROOT / "scripts" / "run_person_d_step4_3_real_positive_control_gate.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()
pu66 = pytest.importorskip("mineocclude.baselines.production_universe_66_cell_v0_1")
preactivation = pytest.importorskip(
    "mineocclude.baselines.preactivation_fold_manifest_66_cell_v0_1"
)


def _read_git_blob(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=REPO_ROOT, capture_output=True, check=True,
    )
    return result.stdout


@pytest.fixture(scope="module")
def authority_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("authority66_step4_3")
    (root / "row_universe_records.jsonl").write_bytes(
        _read_git_blob(pu66.PERSON_B_66_CELL_COMMIT, pu66.PERSON_B_ROW_UNIVERSE_RECORDS_PATH)
    )
    (root / "oracle_target_records.jsonl").write_bytes(
        _read_git_blob(pu66.PERSON_B_66_CELL_COMMIT, pu66.PERSON_B_ORACLE_TARGET_RECORDS_PATH)
    )
    (root / "fold_manifest.json").write_bytes(
        _read_git_blob(
            preactivation.PERSON_B_PREACTIVATION_COMMIT,
            preactivation.FROZEN_FOLD_MANIFEST_PATH,
        )
    )
    return root


def test_real_gate_passes_with_the_expected_shape(authority_root, tmp_path):
    document = SCRIPT.run(authority_root, tmp_path)

    assert document["evidence_kind"] == "real"
    assert document["no_wall_row_count"] == 351
    finding = document["finding"]
    assert finding["status"] == "PASSED"
    assert finding["r2"] == pytest.approx(1.0, abs=1e-4)
    assert finding["ci_low"] > 0.0
    assert finding["n_rows"] == 351
    assert finding["data_provenance"] == "person_c_accepted_no_wall_capture"


def test_published_artifact_matches_the_inventory(authority_root, tmp_path):
    SCRIPT.run(authority_root, tmp_path)
    published = json.loads((tmp_path / "step4_3_positive_control_gate.json").read_text())
    inventory = json.loads((tmp_path / "sha256_inventory_step4_3.json").read_text())

    import hashlib

    actual_sha256 = hashlib.sha256(
        (tmp_path / "step4_3_positive_control_gate.json").read_bytes()
    ).hexdigest()
    assert inventory["artifact_sha256"]["step4_3_positive_control_gate.json"] == actual_sha256
    assert published["schema_id"] == "person-d-step4-3-real-positive-control-gate-v0-1"


def test_regeneration_is_byte_identical(authority_root, tmp_path_factory):
    first = tmp_path_factory.mktemp("first")
    second = tmp_path_factory.mktemp("second")
    SCRIPT.run(authority_root, first)
    SCRIPT.run(authority_root, second)

    for name in ("step4_3_positive_control_gate.json", "sha256_inventory_step4_3.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_fails_closed_on_a_tampered_fold_manifest(authority_root, tmp_path):
    tampered_root = tmp_path / "tampered_authority"
    tampered_root.mkdir()
    for name in ("row_universe_records.jsonl", "oracle_target_records.jsonl"):
        (tampered_root / name).write_bytes((authority_root / name).read_bytes())
    (tampered_root / "fold_manifest.json").write_bytes(
        (authority_root / "fold_manifest.json").read_bytes() + b"\n"
    )
    with pytest.raises(preactivation.PreactivationFoldManifestError):
        SCRIPT.run(tampered_root, tmp_path / "out")
