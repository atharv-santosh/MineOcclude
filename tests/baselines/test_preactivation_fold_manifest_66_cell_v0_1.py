"""Tests for Person D's real 66-cell pre-activation fold manifest support.

Like ``test_production_fold_contract_v0_1.py`` and
``test_mvp_identity_v0_1.py``, this reads Person B's real fold manifest
directly via ``git show <commit>:<path>`` -- the same commit every
frozen hash constant in this module was already independently derived
from -- never a checkout, merge, or copy of that branch.
"""

from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from mineocclude.analysis.manifests import seal_artifact
from mineocclude.baselines import preactivation_fold_manifest_66_cell_v0_1 as contract
from mineocclude.baselines.interface import TrajectoryContext

ROOT = Path(__file__).resolve().parents[2]


def _read_git_blob(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True, check=True,
    )
    return result.stdout


@pytest.fixture(scope="module")
def real_bytes() -> bytes:
    return _read_git_blob(contract.PERSON_B_PREACTIVATION_COMMIT, contract.FROZEN_FOLD_MANIFEST_PATH)


@pytest.fixture(scope="module")
def real_document(real_bytes) -> dict:
    return json.loads(real_bytes.decode("utf-8"))


def _reseal(document: dict) -> dict:
    """Re-seal a mutated document so its own hash matches, isolating a
    deeper semantic check from the (already separately tested) literal
    hash check."""

    resealed = dict(document)
    del resealed["artifact_hash"]
    return seal_artifact(resealed)


def _context(trajectory_id, layout_id, model_frame_idx, fold=-1) -> TrajectoryContext:
    return TrajectoryContext(
        trajectory_id=trajectory_id,
        layout_id=layout_id,
        model_frame_idx=model_frame_idx,
        fold=fold,
        regime="A",
        tau_seconds=0.0,
        visibility=True,
        last_seen_position_blocks=0.0,
        last_seen_velocity_blocks_per_s=None,
        v_scripted_blocks_per_s=1.0,
        q_scripted_blocks2_per_s=0.05,
        duration_seconds=3.0,
        config_hash="test",
        seed=1,
    )


# --------------------------------------------------------------------------
# Exact real-manifest regression
# --------------------------------------------------------------------------


def test_real_fold_manifest_bytes_pass_the_literal_check(real_bytes):
    document = contract.validate_66_cell_fold_manifest_bytes(real_bytes)
    assert len(document["memberships"]) == 2468


def test_real_fold_manifest_document_passes(real_document):
    contract.validate_66_cell_fold_manifest_document(real_document)  # must not raise


def test_real_layout_assignments_are_the_declared_ones(real_document):
    declared = {e["layout_id"]: e["fold_idx"] for e in real_document["layout_assignments"]}
    assert declared == {
        "layout_01": 3, "layout_02": 2, "layout_03": 4,
        "layout_04": 4, "layout_05": 1, "layout_06": 0,
    }


def test_attach_real_no_wall_contexts(real_document):
    # This fold manifest still reflects the superseded 984-row admission
    # stage (see README's "Superseded 984-row admission"); its own
    # no-wall+accepted subset is 360, not the later oracle-target
    # stage's 351 -- attach_66_cell_fold_assignments only needs the
    # submitted rows to be a subset of what this manifest declares
    # accepted, which the real 351-row execution-universe subset is.
    no_wall_rows = [
        row for row in real_document["memberships"]
        if row["admission_stratum"] == "no_wall_visible_control" and row["status"] == "accepted"
    ]
    assert len(no_wall_rows) == 360
    contexts = [
        _context(row["trajectory_id"], row["layout_id"], row["model_frame_idx"])
        for row in no_wall_rows
    ]
    annotated = contract.attach_66_cell_fold_assignments(contexts, fold_manifest=real_document)
    assert len(annotated) == 360
    fold_by_layout = {e["layout_id"]: e["fold_idx"] for e in real_document["layout_assignments"]}
    for ctx in annotated:
        assert ctx.fold == fold_by_layout[ctx.layout_id]


def test_attach_rejects_a_key_not_covered_by_the_manifest(real_document):
    contexts = [_context("layout_01_ep99999999", "layout_01", 0)]
    with pytest.raises(contract.PreactivationFoldManifestError, match="not covered"):
        contract.attach_66_cell_fold_assignments(contexts, fold_manifest=real_document)


def test_attach_rejects_an_excluded_row(real_document):
    excluded_row = next(
        row for row in real_document["memberships"] if row["status"] == "excluded"
    )
    contexts = [_context(excluded_row["trajectory_id"], excluded_row["layout_id"], excluded_row["model_frame_idx"])]
    with pytest.raises(contract.PreactivationFoldManifestError, match="excluded"):
        contract.attach_66_cell_fold_assignments(contexts, fold_manifest=real_document)


def test_attach_rejects_a_conflicting_layout_identity(real_document):
    accepted_row = next(
        row for row in real_document["memberships"] if row["status"] == "accepted"
    )
    contexts = [_context(accepted_row["trajectory_id"], "wrong_layout", accepted_row["model_frame_idx"])]
    with pytest.raises(contract.PreactivationFoldManifestError, match="layout identity"):
        contract.attach_66_cell_fold_assignments(contexts, fold_manifest=real_document)


def test_attach_rejects_a_conflicting_preexisting_fold(real_document):
    accepted_row = next(
        row for row in real_document["memberships"] if row["status"] == "accepted"
    )
    ctx = replace(
        _context(accepted_row["trajectory_id"], accepted_row["layout_id"], accepted_row["model_frame_idx"]),
        fold=99999,
    )
    with pytest.raises(contract.PreactivationFoldManifestError, match="conflicts"):
        contract.attach_66_cell_fold_assignments([ctx], fold_manifest=real_document)


def test_attach_rejects_a_duplicate_requested_row(real_document):
    accepted_row = next(
        row for row in real_document["memberships"] if row["status"] == "accepted"
    )
    ctx = _context(accepted_row["trajectory_id"], accepted_row["layout_id"], accepted_row["model_frame_idx"])
    with pytest.raises(contract.PreactivationFoldManifestError, match="duplicate"):
        contract.attach_66_cell_fold_assignments([ctx, ctx], fold_manifest=real_document)


# --------------------------------------------------------------------------
# Fail-closed on tampering
# --------------------------------------------------------------------------


def test_tampered_bytes_fail_the_literal_hash_check(real_bytes):
    with pytest.raises(contract.PreactivationFoldManifestError, match="SHA-256"):
        contract.validate_66_cell_fold_manifest_bytes(real_bytes + b"\n")


def test_wrong_artifact_type_is_rejected(real_document):
    tampered = copy.deepcopy(real_document)
    tampered["artifact_type"] = "fold_manifest"
    with pytest.raises(contract.PreactivationFoldManifestError):
        contract.validate_66_cell_fold_manifest_document(tampered)


def test_changed_layout_assignment_is_rejected(real_document):
    tampered = copy.deepcopy(real_document)
    tampered["layout_assignments"] = [
        {"layout_id": "layout_01", "fold_idx": 0},
        {"layout_id": "layout_02", "fold_idx": 1},
        {"layout_id": "layout_03", "fold_idx": 2},
        {"layout_id": "layout_04", "fold_idx": 3},
        {"layout_id": "layout_05", "fold_idx": 4},
        {"layout_id": "layout_06", "fold_idx": 0},
    ]
    with pytest.raises(contract.PreactivationFoldManifestError, match="recomputed"):
        contract.validate_66_cell_fold_manifest_document(_reseal(tampered))


def test_admitted_row_count_disagreeing_with_memberships_is_rejected(real_document):
    tampered = copy.deepcopy(real_document)
    tampered["admitted_analysis_row_count"] = 1
    with pytest.raises(contract.PreactivationFoldManifestError, match="admitted_analysis_row_count"):
        contract.validate_66_cell_fold_manifest_document(_reseal(tampered))


def test_missing_exclusion_reason_on_an_excluded_row_is_rejected(real_document):
    tampered = copy.deepcopy(real_document)
    for row in tampered["memberships"]:
        if row["status"] == "excluded":
            row["exclusion_reason"] = None
            break
    with pytest.raises(contract.PreactivationFoldManifestError, match="exclusion_reason"):
        contract.validate_66_cell_fold_manifest_document(_reseal(tampered))


def test_duplicate_membership_key_is_rejected(real_document):
    tampered = copy.deepcopy(real_document)
    tampered["memberships"] = tampered["memberships"] + [tampered["memberships"][0]]
    with pytest.raises(contract.PreactivationFoldManifestError, match="model_frame_key_count"):
        contract.validate_66_cell_fold_manifest_document(_reseal(tampered))


def test_non_mapping_document_is_rejected():
    with pytest.raises(contract.PreactivationFoldManifestError):
        contract.validate_66_cell_fold_manifest_document("not a mapping")
