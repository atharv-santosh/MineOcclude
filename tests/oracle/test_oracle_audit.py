from __future__ import annotations

import copy

import pytest

from mineocclude.oracle.audit import build_oracle_audit
from mineocclude.oracle.schema import OracleValidationError
from tests.probes.test_probe_bridge import make_multilayout_a_b_fixture


def test_oracle_audit_recomputes_both_methods_and_invariants() -> None:
    _activation, targets, *_ = make_multilayout_a_b_fixture()
    report = build_oracle_audit(
        targets,
        artifact_id="known_answer_oracle_audit",
    )
    assert report["status"] == "pass"
    assert report["row_count"] == 15
    assert report["trajectory_count"] == 5
    assert report["max_iterative_closed_mean_error"] <= 1e-6
    assert report["max_declared_variance_error"] <= 1e-6
    assert report["invariant_failures"] == []


def test_oracle_audit_rejects_a_tampered_declared_target() -> None:
    _activation, targets, *_ = make_multilayout_a_b_fixture()
    targets = copy.deepcopy(targets)
    targets["rows"][1]["mu_oracle_blocks"] += 1.0
    with pytest.raises(OracleValidationError):
        build_oracle_audit(
            targets,
            artifact_id="tampered_oracle_audit",
        )
