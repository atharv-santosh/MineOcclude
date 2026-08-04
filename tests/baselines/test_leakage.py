"""Tests for the metadata-only leakage diagnostics."""

from __future__ import annotations

from mineocclude.baselines.leakage import (
    audit_identity_not_filename_derived,
    audit_layout_fold_isolation,
    check_metadata_predictability,
)


def test_audit_identity_not_filename_derived_passes_on_clean_ids():
    finding = audit_identity_not_filename_derived(["traj-0001", "traj-0002"])
    assert finding.passed


def test_audit_identity_not_filename_derived_flags_path_like_ids():
    finding = audit_identity_not_filename_derived(
        ["traj-0001", "episodes/traj-0002.mp4"]
    )
    assert not finding.passed
    assert "episodes/traj-0002.mp4" in finding.detail


def test_audit_layout_fold_isolation_passes_when_layouts_stay_in_one_fold():
    pairs = [("layout-a", 0), ("layout-a", 0), ("layout-b", 1), ("layout-b", 1)]
    finding = audit_layout_fold_isolation(pairs)
    assert finding.passed


def test_audit_layout_fold_isolation_flags_a_split_layout():
    pairs = [("layout-a", 0), ("layout-a", 1), ("layout-b", 1)]
    finding = audit_layout_fold_isolation(pairs)
    assert not finding.passed
    assert "layout-a" in finding.detail


def _four_layout_grouping():
    layout_ids = []
    folds = []
    for fold, layout_id in enumerate(["layout-1", "layout-2", "layout-3", "layout-4"]):
        for _ in range(3):
            layout_ids.append(layout_id)
            folds.append(fold % 2)
    return layout_ids, folds


def test_check_metadata_predictability_flags_a_leaky_feature():
    layout_ids, folds = _four_layout_grouping()
    # The "metadata" feature IS the target here -- maximally leaky.
    targets = [float(i) for i in range(len(layout_ids))]
    feature_rows = [[value] for value in targets]

    finding = check_metadata_predictability(
        feature_rows,
        targets,
        layout_ids,
        folds,
        diagnostic_name="target_leakage_smoke_test",
        r2_threshold=0.1,
        alpha_grid=(0.01, 0.1),
        inner_fold_count=2,
    )
    assert finding.suspicious
    assert finding.r2 > 0.1


def test_check_metadata_predictability_passes_on_unrelated_metadata():
    layout_ids, folds = _four_layout_grouping()
    # A constant "metadata" feature carries no information about the
    # per-row target, which itself varies unpredictably by row.
    feature_rows = [[1.0] for _ in layout_ids]
    targets = [((i * 37) % 7) - 3.0 for i in range(len(layout_ids))]

    finding = check_metadata_predictability(
        feature_rows,
        targets,
        layout_ids,
        folds,
        diagnostic_name="unrelated_metadata_smoke_test",
        r2_threshold=0.1,
        alpha_grid=(0.1, 1.0),
        inner_fold_count=2,
    )
    assert not finding.suspicious
    assert finding.r2 <= 0.1
