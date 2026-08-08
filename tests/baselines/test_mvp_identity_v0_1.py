"""Tests for Person D's Step 6.1 real 66-trajectory MVP identity binding.

Like ``test_production_fold_contract_v0_1.py``, the real reconciliation
this task requires can only be proved against Person C's actual real
bytes -- a hand-built fixture cannot satisfy the frozen literal SHA-256
checks by construction. These tests read the real bytes directly from
Person C's branch via ``git show <commit>:<path>`` -- the same commit
already trusted elsewhere in this package -- never a checkout, merge,
or copy of that branch.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import subprocess
from pathlib import Path

import pytest

from mineocclude.baselines import mvp_identity_v0_1 as identity

ROOT = Path(__file__).resolve().parents[2]


def _read_git_blob(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT, capture_output=True, check=True,
    )
    return result.stdout


@pytest.fixture(scope="module")
def real_matrix_bytes() -> bytes:
    return _read_git_blob(identity.PERSON_C_MVP_COLLECTION_COMMIT, identity.FROZEN_MVP_MATRIX_PATH)


@pytest.fixture(scope="module")
def real_ledger_bytes() -> bytes:
    return _read_git_blob(identity.PERSON_C_MVP_COLLECTION_COMMIT, identity.FROZEN_PILOT_LEDGER_PATH)


# --------------------------------------------------------------------------
# Exact real-artifact regression
# --------------------------------------------------------------------------


def test_real_mvp_matrix_passes_literal_byte_check(real_matrix_bytes):
    rows = identity.validate_mvp_matrix_bytes(real_matrix_bytes)
    assert len(rows) == 66


def test_real_pilot_ledger_passes_literal_byte_check(real_ledger_bytes):
    cells = identity.validate_pilot_ledger_bytes(real_ledger_bytes)
    assert len(cells) == 66
    assert all(cell["accepted_episode"] is not None for cell in cells)


def test_real_mvp_identity_reconciles_with_zero_shortfall(real_matrix_bytes, real_ledger_bytes):
    manifest = identity.build_mvp_input_manifest(real_matrix_bytes, real_ledger_bytes)
    assert manifest["reconciliation_complete"] is True
    assert manifest["shortfalls"] == []
    assert manifest["count_table"]["set_counts"] == {
        "core": 48, "sentinel": 6, "nowall": 6, "nosheep": 6,
    }
    assert manifest["count_table"]["total_count"] == 66
    assert manifest["count_table"]["layout_counts"] == {
        layout: 11 for layout in identity.REQUIRED_LAYOUT_IDS
    }
    assert len(manifest["trajectories"]) == 66
    trajectory_ids = {row["trajectory_id"] for row in manifest["trajectories"]}
    assert len(trajectory_ids) == 66  # every accepted trajectory is unique


def test_real_manifest_trajectory_ids_match_layout_prefix(real_matrix_bytes, real_ledger_bytes):
    manifest = identity.build_mvp_input_manifest(real_matrix_bytes, real_ledger_bytes)
    for row in manifest["trajectories"]:
        assert row["trajectory_id"].startswith(row["layout_id"] + "_ep")


def test_real_manifest_is_deterministic_across_runs(real_matrix_bytes, real_ledger_bytes):
    first = identity.build_mvp_input_manifest(real_matrix_bytes, real_ledger_bytes)
    second = identity.build_mvp_input_manifest(real_matrix_bytes, real_ledger_bytes)
    assert first == second


# --------------------------------------------------------------------------
# Fail-closed literal-byte checks
# --------------------------------------------------------------------------


def test_tampered_matrix_bytes_fail_byte_size_or_hash(real_matrix_bytes):
    tampered = real_matrix_bytes + b"\n"
    with pytest.raises(identity.MvpIdentityError):
        identity.validate_mvp_matrix_bytes(tampered)


def test_tampered_ledger_bytes_fail_hash(real_ledger_bytes):
    tampered = real_ledger_bytes.replace(b"layout_01", b"layout_99", 1)
    with pytest.raises(identity.MvpIdentityError):
        identity.validate_pilot_ledger_bytes(tampered)


def test_non_bytes_matrix_payload_rejected():
    with pytest.raises(identity.MvpIdentityError):
        identity.validate_mvp_matrix_bytes("not bytes")  # type: ignore[arg-type]


def test_malformed_json_ledger_rejected(real_ledger_bytes):
    # Same byte size/shape-breaking payload; must fail on hash before JSON parsing.
    with pytest.raises(identity.MvpIdentityError):
        identity.validate_pilot_ledger_bytes(b"{not json but matches nothing}")


# --------------------------------------------------------------------------
# Structural / semantic rejections built from a mutated but real-shaped matrix
# --------------------------------------------------------------------------


def _rewrite_matrix_csv(real_matrix_bytes: bytes, mutate_rows) -> bytes:
    text = real_matrix_bytes.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames
    rows = [dict(row) for row in reader]
    rows = mutate_rows(rows)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def test_matrix_with_wrong_row_count_is_rejected_once_hash_check_is_bypassed(real_matrix_bytes):
    # Directly exercise the row-count guard by feeding a real-shaped but
    # short CSV through the internal parser (hash check intentionally
    # bypassed here to isolate this specific structural check).
    mutated = _rewrite_matrix_csv(real_matrix_bytes, lambda rows: rows[:-1])
    with pytest.raises(identity.MvpIdentityError, match="row count"):
        identity._parse_mvp_matrix_rows(mutated)


def test_join_fails_closed_when_a_planned_cell_has_no_real_capture(real_matrix_bytes, real_ledger_bytes):
    matrix_rows = identity._parse_mvp_matrix_rows(real_matrix_bytes)
    ledger_cells = json.loads(real_ledger_bytes.decode("utf-8"))
    mutated_ledger = copy.deepcopy(ledger_cells)
    mutated_ledger[0]["cell"]["hidden"] = 999  # break its join key
    with pytest.raises(identity.MvpIdentityError, match="bijectively reconcile"):
        identity.join_matrix_and_ledger(matrix_rows, mutated_ledger)


def test_join_fails_closed_on_duplicate_matrix_key(real_matrix_bytes, real_ledger_bytes):
    matrix_rows = identity._parse_mvp_matrix_rows(real_matrix_bytes)
    ledger_cells = json.loads(real_ledger_bytes.decode("utf-8"))
    duplicated = matrix_rows + [dict(matrix_rows[0])]
    with pytest.raises(identity.MvpIdentityError, match="not unique"):
        identity.join_matrix_and_ledger(duplicated, ledger_cells)


def test_ledger_cell_missing_accepted_episode_is_rejected(real_ledger_bytes):
    cells = json.loads(real_ledger_bytes.decode("utf-8"))
    cells[0]["accepted_episode"] = None
    with pytest.raises(identity.MvpIdentityError, match="accepted"):
        identity._validate_ledger_cells(cells)


def test_reconcile_counts_reports_shortfall_explicitly_without_raising():
    identities = [
        identity.MvpTrajectoryIdentity(
            set_name="core", layout_id="layout_01", trajectory_id="layout_01_ep1",
            accepted_episode=1, hidden_frames=4, v=1.0, q=0.02,
        )
    ]
    result = identity.reconcile_mvp_counts(identities)
    assert result.is_complete is False
    assert any("core" in s for s in result.shortfalls)
    assert any("total accepted trajectory count" in s for s in result.shortfalls)


def test_reconcile_counts_flags_unexpected_set():
    identities = [
        identity.MvpTrajectoryIdentity(
            set_name="mystery", layout_id="layout_01", trajectory_id="layout_01_ep1",
            accepted_episode=1, hidden_frames=4, v=1.0, q=0.02,
        )
    ]
    result = identity.reconcile_mvp_counts(identities)
    assert any("unexpected set" in s for s in result.shortfalls)
