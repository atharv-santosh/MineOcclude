"""Focused evidence for Person D Phase 1.1, 1.2, and 1.4."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mineocclude.baselines.firewall import select_legal_inputs
from mineocclude.baselines.harness import (
    EstimatorPrediction,
    run_synthetic_baseline_harness,
)
from mineocclude.baselines.spec import (
    BASELINE_SPEC_SCHEMA_VERSION,
    BaselineContractCode,
    BaselineContractError,
    supported_baseline_spec,
    validate_baseline_spec,
    validate_prediction_row,
)
from mineocclude.analysis.manifests import seal_artifact
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.metrics.u1_mean import RegressionMetrics, regression_metrics


FOLD_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "person_d"
    / "synthetic_b_fold_manifest.json"
)
TARGET_HASH = "f" * 64
PREPROCESS_HASH = "a" * 64
CODE_SHA = "b" * 40


def _fold_manifest():
    return json.loads(FOLD_FIXTURE_PATH.read_text(encoding="utf-8"))


def _provenance(manifest=None):
    manifest = manifest or _fold_manifest()
    return {
        "schema_version": SCHEMA_VERSION,
        "accepted_manifest_hash": manifest["input_manifest_hash"],
        "fold_manifest_hash": manifest["artifact_hash"],
        "target_manifest_hash": TARGET_HASH,
        "analysis_config_hash": manifest["config_hash"],
        "preprocess_hash": PREPROCESS_HASH,
        "code_sha": CODE_SHA,
    }


def _phase1_rows(baseline_name: str):
    manifest = _fold_manifest()
    input_rows = []
    target_rows = []
    for membership in manifest["memberships"]:
        layout_number = ord(membership["layout_id"][-1]) - ord("a") + 1
        frame_idx = membership["model_frame_idx"]
        last_visible = float(layout_number * 10 + frame_idx)
        input_row = {
            "trajectory_id": membership["trajectory_id"],
            "model_frame_idx": frame_idx,
            "last_visible_position_blocks": last_visible,
            "tau": frame_idx * 0.05,
            "visibility": "visible" if frame_idx == 0 else "occluded",
        }
        if baseline_name == "constant_velocity":
            input_row["estimated_velocity_blocks_per_s"] = 0.5
        input_rows.append(input_row)
        target_rows.append(
            {
                "trajectory_id": membership["trajectory_id"],
                "model_frame_idx": frame_idx,
                "target_name": "mu_oracle_blocks",
                "target_value": last_visible + frame_idx * 0.5,
                "status": "accepted",
                "target_manifest_hash": TARGET_HASH,
                "accepted_manifest_hash": manifest["input_manifest_hash"],
            }
        )
    return input_rows, target_rows


def _heldout_keys(fold_idx=4):
    return [
        (row["trajectory_id"], row["model_frame_idx"])
        for row in _fold_manifest()["memberships"]
        if row["fold_idx"] == fold_idx
    ]


def _run(name: str, **overrides):
    inputs, targets = _phase1_rows(name)
    arguments = {
        "input_rows": inputs,
        "target_rows": targets,
        "fold_manifest": _fold_manifest(),
        "requested_test_keys": _heldout_keys(),
        "provenance": _provenance(),
    }
    arguments.update(overrides)
    return run_synthetic_baseline_harness(
        supported_baseline_spec(name), **arguments
    )


def test_baseline_spec_is_strict_and_uses_v1_identity():
    document = supported_baseline_spec("last_seen")
    spec = validate_baseline_spec(document)
    assert spec.baseline_spec_schema_version == BASELINE_SPEC_SCHEMA_VERSION
    assert spec.target_name == "mu_oracle_blocks"
    assert spec.fit_scope == "outer_train_only"
    assert tuple(spec.required_provenance)[0] == "schema_version"

    missing = copy.deepcopy(document)
    missing.pop("seed")
    with pytest.raises(BaselineContractError) as caught:
        validate_baseline_spec(missing)
    assert caught.value.code is BaselineContractCode.MISSING_FIELD

    unknown = copy.deepcopy(document)
    unknown["notes"] = "not schema"
    with pytest.raises(BaselineContractError) as caught:
        validate_baseline_spec(unknown)
    assert caught.value.code is BaselineContractCode.UNKNOWN_FIELD

    non_string_unknown = copy.deepcopy(document)
    non_string_unknown[7] = "malformed field name"
    with pytest.raises(BaselineContractError) as caught:
        validate_baseline_spec(non_string_unknown)
    assert caught.value.code is BaselineContractCode.UNKNOWN_FIELD


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("baseline_version", "renamed-v2"),
        ("legal_features", ["hidden_truth"]),
        ("fit_scope", "all_rows"),
        ("required_provenance", ["filename"]),
    ],
)
def test_baseline_spec_rejects_unsupported_or_malformed_definition(field, value):
    document = supported_baseline_spec("last_seen")
    document[field] = value
    with pytest.raises(BaselineContractError):
        validate_baseline_spec(document)


def test_firewall_selects_only_legal_features_without_mutation():
    spec = validate_baseline_spec(supported_baseline_spec("last_seen"))
    rows, _ = _phase1_rows("last_seen")
    original = copy.deepcopy(rows)
    selected = select_legal_inputs(spec, rows, provenance=_provenance())
    assert rows == original
    assert set(selected[0].features) == set(spec.legal_features)
    assert [row.frame_key for row in selected] == sorted(
        row.frame_key for row in selected
    )


@pytest.mark.parametrize(
    "illegal_field",
    [
        "x_true_blocks",
        "q_scripted_blocks2_per_s",
        "oracle_mu_blocks",
        "position_at_next_frame",
        "layout_target_hint",
        "filename",
        "source_file_path",
        "unknown_metadata",
    ],
)
def test_firewall_rejects_privileged_future_file_and_unknown_fields(illegal_field):
    spec = validate_baseline_spec(supported_baseline_spec("last_seen"))
    rows, _ = _phase1_rows("last_seen")
    rows[0][illegal_field] = 123
    with pytest.raises(BaselineContractError) as caught:
        select_legal_inputs(spec, rows, provenance=_provenance())
    assert caught.value.code is BaselineContractCode.ILLEGAL_FEATURE


def test_firewall_rejects_malformed_identity_and_provenance():
    spec = validate_baseline_spec(supported_baseline_spec("last_seen"))
    rows, _ = _phase1_rows("last_seen")
    rows[0]["model_frame_idx"] = True
    with pytest.raises(BaselineContractError) as caught:
        select_legal_inputs(spec, rows, provenance=_provenance())
    assert caught.value.code is BaselineContractCode.INVALID_IDENTITY

    rows, _ = _phase1_rows("last_seen")
    provenance = _provenance()
    provenance["preprocess_hash"] = "stale"
    with pytest.raises(BaselineContractError) as caught:
        select_legal_inputs(spec, rows, provenance=provenance)
    assert caught.value.code is BaselineContractCode.INVALID_PROVENANCE


class _NeverCalledEstimator:
    def __init__(self):
        self.fit_called = False
        self.predict_called = False

    def fit(self, spec, rows, targets_by_key):
        self.fit_called = True
        return {}

    def predict(self, spec, fit_state, rows):
        self.predict_called = True
        return []


def test_firewall_failure_prevents_fit_and_prediction_calls():
    inputs, targets = _phase1_rows("last_seen")
    inputs[0]["filename"] = "shortcut.mp4"
    estimator = _NeverCalledEstimator()
    with pytest.raises(BaselineContractError):
        _run(
            "last_seen",
            input_rows=inputs,
            target_rows=targets,
            estimator=estimator,
        )
    assert not estimator.fit_called
    assert not estimator.predict_called


def test_common_harness_runs_two_existing_baselines_on_identical_test_ids():
    with patch(
        "mineocclude.baselines.harness.regression_metrics",
        wraps=regression_metrics,
    ) as metric_call:
        last_seen = _run("last_seen")
    constant_velocity = _run("constant_velocity")

    expected = set(_heldout_keys())
    assert {row.frame_key for row in last_seen.predictions} == expected
    assert {row.frame_key for row in constant_velocity.predictions} == expected
    assert isinstance(last_seen.metrics, RegressionMetrics)
    metric_call.assert_called_once()
    for result in (last_seen, constant_velocity):
        train = {tuple(key) for key in result.fit_metadata["train_identities"]}
        test = {tuple(key) for key in result.fit_metadata["test_identities"]}
        assert train.isdisjoint(test)
        assert test == expected
        assert result.fit_metadata["preprocessing_scope"] == "outer_train_rows_only"
        for prediction in result.predictions:
            assert validate_prediction_row(
                prediction.as_document(), result.spec
            ).frame_key == prediction.frame_key


def test_prediction_schema_rejects_missing_unknown_and_wrong_identity_fields():
    result = _run("last_seen")
    document = result.predictions[0].as_document()

    missing = copy.deepcopy(document)
    missing.pop("trajectory_id")
    with pytest.raises(BaselineContractError) as caught:
        validate_prediction_row(missing, result.spec)
    assert caught.value.code is BaselineContractCode.MISSING_FIELD

    unknown = copy.deepcopy(document)
    unknown["filename"] = "not-identity.mp4"
    with pytest.raises(BaselineContractError) as caught:
        validate_prediction_row(unknown, result.spec)
    assert caught.value.code is BaselineContractCode.UNKNOWN_FIELD

    wrong_version = copy.deepcopy(document)
    wrong_version["baseline_version"] = "stale"
    with pytest.raises(BaselineContractError) as caught:
        validate_prediction_row(wrong_version, result.spec)
    assert caught.value.code is BaselineContractCode.INVALID_SPEC


def test_common_harness_is_row_order_independent_and_non_mutating():
    inputs, targets = _phase1_rows("last_seen")
    manifest = _fold_manifest()
    provenance = _provenance(manifest)
    spec_document = supported_baseline_spec("last_seen")
    original_inputs = copy.deepcopy(inputs)
    original_targets = copy.deepcopy(targets)
    original_manifest = copy.deepcopy(manifest)
    original_provenance = copy.deepcopy(provenance)
    original_spec = copy.deepcopy(spec_document)
    forward = run_synthetic_baseline_harness(
        spec_document,
        input_rows=inputs,
        target_rows=targets,
        fold_manifest=manifest,
        requested_test_keys=_heldout_keys(),
        provenance=provenance,
    )
    reverse = _run(
        "last_seen",
        input_rows=list(reversed(inputs)),
        target_rows=list(reversed(targets)),
        requested_test_keys=list(reversed(_heldout_keys())),
    )
    assert inputs == original_inputs
    assert targets == original_targets
    assert manifest == original_manifest
    assert provenance == original_provenance
    assert spec_document == original_spec
    assert forward == reverse


@pytest.mark.parametrize(
    "broken",
    [
        "duplicate_input",
        "missing_target",
        "missing_requested_input",
        "duplicate_request",
    ],
)
def test_common_harness_fails_closed_on_identity_coverage_errors(broken):
    inputs, targets = _phase1_rows("last_seen")
    requested = _heldout_keys()
    if broken == "duplicate_input":
        inputs.append(copy.deepcopy(inputs[0]))
    elif broken == "missing_target":
        targets.pop()
    elif broken == "missing_requested_input":
        missing = requested[0]
        inputs = [
            row
            for row in inputs
            if (row["trajectory_id"], row["model_frame_idx"]) != missing
        ]
    else:
        requested.append(requested[0])
    with pytest.raises(BaselineContractError):
        _run(
            "last_seen",
            input_rows=inputs,
            target_rows=targets,
            requested_test_keys=requested,
        )


class _UnexpectedPredictionEstimator:
    def fit(self, spec, rows, targets_by_key):
        return {"train_count": len(rows)}

    def predict(self, spec, fit_state, rows):
        return [EstimatorPrediction(("unexpected", 999), 0.0)]


def test_common_harness_rejects_unexpected_prediction_identity():
    with pytest.raises(BaselineContractError) as caught:
        _run("last_seen", estimator=_UnexpectedPredictionEstimator())
    assert caught.value.code is BaselineContractCode.PREDICTION_IDENTITY


def test_common_harness_rejects_stale_fold_provenance():
    provenance = _provenance()
    provenance["fold_manifest_hash"] = "0" * 64
    with pytest.raises(BaselineContractError) as caught:
        _run("last_seen", provenance=provenance)
    assert caught.value.code is BaselineContractCode.INVALID_PROVENANCE


def test_common_harness_rejects_invalid_authoritative_fold_coverage():
    manifest = _fold_manifest()
    manifest.pop("artifact_hash")
    manifest["memberships"][0]["fold_idx"] = 0
    manifest = seal_artifact(manifest)
    provenance = _provenance(manifest)
    with pytest.raises(BaselineContractError) as caught:
        _run("last_seen", fold_manifest=manifest, provenance=provenance)
    assert caught.value.code is BaselineContractCode.INVALID_FOLD
