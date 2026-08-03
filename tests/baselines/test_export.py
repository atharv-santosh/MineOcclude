"""Tests for the D-to-B baseline export/handoff shape.

These exercise the real ``mineocclude.contracts.analysis_inputs
.validate_baseline_input`` validator (via export.validate_document), not
a paraphrase of it, so a passing test here is evidence the document
would actually be accepted by Person B's consumer contract.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from mineocclude.analysis.manifests import seal_artifact
from mineocclude.baselines.export import (
    BaselineExportError,
    attach_b_fold_assignments,
    build_baseline_document,
    validate_b_fold_manifest,
    validate_document,
)
from mineocclude.baselines.last_seen import predict_last_seen
from mineocclude.baselines.production_fold_contract_v0_1 import (
    PRODUCTION_FOLD_MANIFEST_FORMAT_VERSION,
)
from mineocclude.contracts.analysis_inputs import BASELINE_FAMILY_CONTRACTS
from tests.baselines.conftest import build_trajectory_contexts

VALID_HASH = hashlib.sha256(b"test").hexdigest()
FOLD_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "person_d"
    / "synthetic_b_fold_manifest.json"
)


def _fold_manifest():
    return json.loads(FOLD_FIXTURE_PATH.read_text(encoding="utf-8"))


def _five_layout_contexts():
    contexts = []
    for index, layout in enumerate("abcde", start=1):
        contexts.extend(
            build_trajectory_contexts(
                trajectory_id=f"traj-{layout}",
                layout_id=f"layout-{layout}",
                fold=-1,
                visible_positions=(0.0, float(index)),
                dt=1.0,
                hidden_taus=(1.0,),
            )
        )
    return contexts


def _attach(contexts=None):
    return attach_b_fold_assignments(
        _five_layout_contexts() if contexts is None else contexts,
        fold_manifest=_fold_manifest(),
    )


def test_attach_b_fold_assignments_consumes_saved_manifest_unchanged():
    contexts = _five_layout_contexts()
    manifest = _fold_manifest()
    original_manifest = copy.deepcopy(manifest)
    annotated = attach_b_fold_assignments(contexts, fold_manifest=manifest)

    folds_by_layout = {ctx.layout_id: ctx.fold for ctx in annotated}
    expected = {
        row["layout_id"]: row["fold_idx"]
        for row in manifest["layout_assignments"]
    }
    assert folds_by_layout == expected
    assert manifest == original_manifest


def test_attach_b_fold_assignments_rejects_missing_or_extra_coverage():
    contexts = _five_layout_contexts()
    with pytest.raises(BaselineExportError, match="exactly match"):
        _attach(contexts[:-1])

    extra = replace(
        contexts[-1],
        trajectory_id="traj-not-in-manifest",
        model_frame_idx=99,
    )
    with pytest.raises(BaselineExportError, match="exactly match"):
        _attach(contexts + [extra])


def test_attach_b_fold_assignments_rejects_duplicate_requested_identity():
    contexts = _five_layout_contexts()
    with pytest.raises(BaselineExportError, match="duplicate requested"):
        _attach(contexts + [contexts[0]])


def test_attach_b_fold_assignments_rejects_duplicate_manifest_identity():
    manifest = _fold_manifest()
    manifest.pop("artifact_hash")
    manifest["memberships"].append(copy.deepcopy(manifest["memberships"][0]))
    manifest = seal_artifact(manifest)

    with pytest.raises(BaselineExportError, match="authoritative B fold manifest"):
        attach_b_fold_assignments(
            _five_layout_contexts(),
            fold_manifest=manifest,
        )


def test_attach_b_fold_assignments_rejects_conflicting_manifest_fold():
    manifest = _fold_manifest()
    manifest.pop("artifact_hash")
    manifest["memberships"][0]["fold_idx"] = (
        manifest["memberships"][0]["fold_idx"] + 1
    ) % manifest["n_splits"]
    manifest = seal_artifact(manifest)

    with pytest.raises(BaselineExportError, match="authoritative B fold manifest"):
        attach_b_fold_assignments(
            _five_layout_contexts(),
            fold_manifest=manifest,
        )


def test_attach_b_fold_assignments_rejects_existing_conflicting_fold():
    contexts = _five_layout_contexts()
    manifest = _fold_manifest()
    expected_fold = manifest["memberships"][0]["fold_idx"]
    contexts[0] = replace(contexts[0], fold=(expected_fold + 1) % 5)

    with pytest.raises(BaselineExportError, match="existing fold"):
        attach_b_fold_assignments(contexts, fold_manifest=manifest)


def test_build_and_validate_last_seen_document_passes_b_contract():
    fold_manifest = _fold_manifest()
    contexts = attach_b_fold_assignments(
        _five_layout_contexts(), fold_manifest=fold_manifest
    )
    rows = predict_last_seen(contexts)

    document = build_baseline_document(
        rows,
        target_name="mu_oracle_blocks",
        baseline_id="last_seen_v1",
        baseline_family="last_seen",
        config_hash=VALID_HASH,
        input_manifest_hash=VALID_HASH,
        fold_manifest_hash=fold_manifest["artifact_hash"],
        fit_manifest_hash=VALID_HASH,
        default_fit_id="last_seen:mu_oracle_blocks:closed_form",
    )

    result = validate_document(document)
    assert result.accepted, result.rejections
    family_contract = BASELINE_FAMILY_CONTRACTS["last_seen"]
    assert document["feature_access"] == sorted(family_contract["feature_access"])
    assert document["legal_information"] == family_contract["legal_information"]


def test_build_baseline_document_rejects_unsupported_family():
    fold_manifest = _fold_manifest()
    contexts = attach_b_fold_assignments(
        _five_layout_contexts(), fold_manifest=fold_manifest
    )
    rows = predict_last_seen(contexts)

    with pytest.raises(BaselineExportError, match="not supported"):
        build_baseline_document(
            rows,
            target_name="mu_oracle_blocks",
            baseline_id="renamed_hidden_truth_v1",
            baseline_family="renamed_hidden_truth",
            config_hash=VALID_HASH,
            input_manifest_hash=VALID_HASH,
            fold_manifest_hash=fold_manifest["artifact_hash"],
            fit_manifest_hash=VALID_HASH,
            default_fit_id="renamed_hidden_truth:mu_oracle_blocks:closed_form",
        )


def test_validate_document_enforces_exact_coverage_against_b_expectations():
    fold_manifest = _fold_manifest()
    contexts = attach_b_fold_assignments(
        _five_layout_contexts(), fold_manifest=fold_manifest
    )
    rows = predict_last_seen(contexts)
    document = build_baseline_document(
        rows,
        target_name="mu_oracle_blocks",
        baseline_id="last_seen_v1",
        baseline_family="last_seen",
        config_hash=VALID_HASH,
        input_manifest_hash=VALID_HASH,
        fold_manifest_hash=fold_manifest["artifact_hash"],
        fit_manifest_hash=VALID_HASH,
        default_fit_id="last_seen:mu_oracle_blocks:closed_form",
    )

    expected_fold_by_frame = {
        (ctx.trajectory_id, ctx.model_frame_idx): ctx.fold for ctx in contexts
    }
    # Drop one key: coverage no longer matches B's expected frame set.
    missing_key = next(iter(expected_fold_by_frame))
    del expected_fold_by_frame[missing_key]
    expected_fold_by_frame[("some-other-traj", 0)] = 0

    result = validate_document(document, expected_fold_by_frame=expected_fold_by_frame)
    assert not result.accepted
    codes = {rejection.code for rejection in result.rejections}
    assert "manifest_mismatch" in {code.value for code in codes}


def test_build_baseline_document_rejects_bad_hash():
    fold_manifest = _fold_manifest()
    contexts = attach_b_fold_assignments(
        _five_layout_contexts(), fold_manifest=fold_manifest
    )
    rows = predict_last_seen(contexts)
    with pytest.raises(BaselineExportError):
        build_baseline_document(
            rows,
            target_name="mu_oracle_blocks",
            baseline_id="last_seen_v1",
            baseline_family="last_seen",
            config_hash="not-a-hash",
            input_manifest_hash=VALID_HASH,
            fold_manifest_hash=fold_manifest["artifact_hash"],
            fit_manifest_hash=VALID_HASH,
            default_fit_id="last_seen:mu_oracle_blocks:closed_form",
        )


def test_validate_b_fold_manifest_preserves_historical_behavior_for_historical_manifests():
    """format_version absent (historical manifests never carried this
    field) must still route through the pre-existing
    ``validate_fold_manifest`` deterministic-reproduction check,
    completely unchanged -- proven here via the same synthetic fixture
    every other historical-path test in this file already relies on."""

    validate_b_fold_manifest(_fold_manifest())  # must not raise


def test_validate_b_fold_manifest_rejects_unknown_format_version():
    manifest = _fold_manifest()
    manifest["fold_manifest_format_version"] = "some-unrecognized-future-format-v9.9"
    with pytest.raises(BaselineExportError, match="unknown fold_manifest_format_version"):
        validate_b_fold_manifest(manifest)


def test_validate_b_fold_manifest_dispatches_to_signed_explicit_mapping_for_production_format():
    """A document merely *claiming* the production format version but
    failing that validator's real checks must be rejected through the
    production path, not silently accepted or misrouted to the
    historical path (which would ignore the field entirely)."""

    manifest = _fold_manifest()
    manifest["fold_manifest_format_version"] = PRODUCTION_FOLD_MANIFEST_FORMAT_VERSION
    with pytest.raises(BaselineExportError, match="authoritative B production fold manifest"):
        validate_b_fold_manifest(manifest)


def test_validate_b_fold_manifest_accepts_the_real_production_fold_manifest():
    """The exact real-manifest regression this task requires, exercised
    through the same dispatch function ``attach_b_fold_assignments``
    (and the CLI's preflight) actually calls -- not a paraphrase of it.
    """

    import subprocess
    from pathlib import Path as _Path

    from mineocclude.baselines.production_fold_contract_v0_1 import (
        FROZEN_FOLD_MANIFEST_PATH,
        RATIFYING_PERSON_B_COMMIT,
    )

    root = _Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "show", f"{RATIFYING_PERSON_B_COMMIT}:{FROZEN_FOLD_MANIFEST_PATH}"],
        cwd=root, capture_output=True, check=True,
    )
    real_fold_manifest = json.loads(result.stdout.decode("utf-8"))
    validate_b_fold_manifest(real_fold_manifest)  # must not raise


def test_build_baseline_document_rejects_empty_applicable_set():
    fold_manifest = _fold_manifest()
    contexts = attach_b_fold_assignments(
        _five_layout_contexts(), fold_manifest=fold_manifest
    )
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
            fold_manifest_hash=fold_manifest["artifact_hash"],
            fit_manifest_hash=VALID_HASH,
            default_fit_id="last_seen:log_sigma_oracle:closed_form",
        )
