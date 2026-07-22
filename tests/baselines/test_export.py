"""Tests for the D-to-B baseline export/handoff shape.

These exercise the real ``mineocclude.contracts.analysis_inputs
.validate_baseline_input`` validator (via export.validate_document), not
a paraphrase of it, so a passing test here is evidence the document
would actually be accepted by Person B's consumer contract.
"""

from __future__ import annotations

import hashlib

import pytest

from mineocclude.baselines.export import (
    BaselineExportError,
    attach_b_fold_assignments,
    build_baseline_document,
    validate_document,
)
from mineocclude.baselines.last_seen import predict_last_seen
from tests.baselines.conftest import build_trajectory_contexts

VALID_HASH = hashlib.sha256(b"test").hexdigest()


def _two_layout_contexts():
    layout_a = build_trajectory_contexts(
        trajectory_id="traj-a",
        layout_id="layout-a",
        fold=-1,
        visible_positions=(0.0, 1.0),
        dt=1.0,
        hidden_taus=(1.0,),
    )
    layout_b = build_trajectory_contexts(
        trajectory_id="traj-b",
        layout_id="layout-b",
        fold=-1,
        visible_positions=(0.0, 2.0),
        dt=1.0,
        hidden_taus=(1.0,),
    )
    return layout_a + layout_b


def test_attach_b_fold_assignments_groups_by_layout():
    contexts = _two_layout_contexts()
    annotated = attach_b_fold_assignments(contexts, n_splits=2, seed=20260719)

    folds_by_layout = {ctx.layout_id: ctx.fold for ctx in annotated}
    assert len(folds_by_layout) == 2
    # Every context from one layout must land in that layout's fold.
    for ctx in annotated:
        assert ctx.fold == folds_by_layout[ctx.layout_id]
    # Two layouts split across two folds -- not all bunched in one.
    assert len(set(folds_by_layout.values())) == 2


def test_build_and_validate_last_seen_document_passes_b_contract():
    contexts = attach_b_fold_assignments(_two_layout_contexts(), n_splits=2)
    rows = predict_last_seen(contexts)

    document = build_baseline_document(
        rows,
        target_name="mu_oracle_blocks",
        baseline_id="last_seen_v1",
        baseline_family="last_seen",
        config_hash=VALID_HASH,
        input_manifest_hash=VALID_HASH,
        fold_manifest_hash=VALID_HASH,
        fit_manifest_hash=VALID_HASH,
        default_fit_id="last_seen:mu_oracle_blocks:closed_form",
    )

    result = validate_document(document)
    assert result.accepted, result.rejections


def test_validate_document_enforces_exact_coverage_against_b_expectations():
    contexts = attach_b_fold_assignments(_two_layout_contexts(), n_splits=2)
    rows = predict_last_seen(contexts)
    document = build_baseline_document(
        rows,
        target_name="mu_oracle_blocks",
        baseline_id="last_seen_v1",
        baseline_family="last_seen",
        config_hash=VALID_HASH,
        input_manifest_hash=VALID_HASH,
        fold_manifest_hash=VALID_HASH,
        fit_manifest_hash=VALID_HASH,
        default_fit_id="last_seen:mu_oracle_blocks:closed_form",
    )

    covered_keys = {
        (row["trajectory_id"], row["model_frame_idx"]) for row in document["rows"]
    }
    expected_fold_by_frame = {key: 0 for key in covered_keys}
    # Drop one key: coverage no longer matches B's expected frame set.
    missing_key = next(iter(expected_fold_by_frame))
    del expected_fold_by_frame[missing_key]
    expected_fold_by_frame[("some-other-traj", 0)] = 0

    result = validate_document(document, expected_fold_by_frame=expected_fold_by_frame)
    assert not result.accepted
    codes = {rejection.code for rejection in result.rejections}
    assert "manifest_mismatch" in {code.value for code in codes}


def test_build_baseline_document_rejects_bad_hash():
    contexts = attach_b_fold_assignments(_two_layout_contexts(), n_splits=2)
    rows = predict_last_seen(contexts)
    with pytest.raises(BaselineExportError):
        build_baseline_document(
            rows,
            target_name="mu_oracle_blocks",
            baseline_id="last_seen_v1",
            baseline_family="last_seen",
            config_hash="not-a-hash",
            input_manifest_hash=VALID_HASH,
            fold_manifest_hash=VALID_HASH,
            fit_manifest_hash=VALID_HASH,
            default_fit_id="last_seen:mu_oracle_blocks:closed_form",
        )


def test_build_baseline_document_rejects_empty_applicable_set():
    contexts = attach_b_fold_assignments(_two_layout_contexts(), n_splits=2)
    rows = predict_last_seen(contexts)
    with pytest.raises(BaselineExportError):
        # log_sigma is never applicable for last-seen (memory heuristic
        # defines no spread), so every row is non-applicable here.
        build_baseline_document(
            rows,
            target_name="log_sigma_oracle",
            baseline_id="last_seen_v1",
            baseline_family="last_seen",
            config_hash=VALID_HASH,
            input_manifest_hash=VALID_HASH,
            fold_manifest_hash=VALID_HASH,
            fit_manifest_hash=VALID_HASH,
            default_fit_id="last_seen:log_sigma_oracle:closed_form",
        )
