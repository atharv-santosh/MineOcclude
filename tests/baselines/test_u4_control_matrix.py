"""Tests for the U4 intervention control-matrix verification tools."""

from __future__ import annotations

import math

from mineocclude.baselines.u4_control_matrix import (
    ControlKind,
    audit_control_matrix_completeness,
    audit_orthogonal_to_real_direction,
    audit_random_direction_norm_matched,
    build_control_matrix,
)


def test_build_control_matrix_covers_every_event_seed_kind_combination():
    matrix = build_control_matrix(["event-a", "event-b"], [1, 2])

    assert len(matrix) == 2 * 2 * len(ControlKind)
    control_ids = [spec.control_id for spec in matrix]
    assert len(control_ids) == len(set(control_ids))  # every ID is unique
    kinds_present = {spec.kind for spec in matrix}
    assert kinds_present == set(ControlKind)


def test_audit_control_matrix_completeness_passes_when_everything_exists():
    matrix = build_control_matrix(["event-a"], [1])
    produced = [spec.control_id for spec in matrix]

    finding = audit_control_matrix_completeness(matrix, produced)
    assert finding.passed


def test_audit_control_matrix_completeness_flags_missing_and_duplicated():
    matrix = build_control_matrix(["event-a"], [1])
    produced = [spec.control_id for spec in matrix]
    # Drop the alpha_zero row (omitted control) and duplicate the
    # primary row (overwritten-then-rewritten control).
    dropped = next(cid for cid in produced if cid.endswith(":alpha_zero"))
    produced.remove(dropped)
    primary_id = next(cid for cid in produced if cid.endswith(":primary"))
    produced.append(primary_id)

    finding = audit_control_matrix_completeness(matrix, produced)
    assert not finding.passed
    assert "missing" in finding.detail
    assert "duplicated" in finding.detail


def test_audit_random_direction_norm_matched_passes_on_unit_vector():
    finding = audit_random_direction_norm_matched([0.6, 0.8])
    assert finding.passed


def test_audit_random_direction_norm_matched_fails_on_non_unit_vector():
    finding = audit_random_direction_norm_matched([1.0, 1.0])
    assert not finding.passed


def test_audit_orthogonal_to_real_direction_passes_on_perpendicular_vectors():
    finding = audit_orthogonal_to_real_direction([1.0, 0.0], [0.0, 5.0])
    assert finding.passed


def test_audit_orthogonal_to_real_direction_fails_on_parallel_vectors():
    finding = audit_orthogonal_to_real_direction([2.0, 0.0], [1.0, 0.0])
    assert not finding.passed
    assert math.isclose(float(finding.detail.split("=")[1].split()[0]), 1.0, abs_tol=1e-6)
