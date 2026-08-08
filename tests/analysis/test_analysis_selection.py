from __future__ import annotations

import copy

import pytest

from mineocclude.analysis.selection import (
    AnalysisSelectionError,
    SCOPE_HIDDEN_MEAN,
    SCOPE_HIDDEN_SPREAD,
    SCOPE_VISIBLE_NO_WALL,
    build_analysis_selection_manifest,
    selections_from_condition_source,
    selected_frame_keys,
    validate_analysis_selection_manifest,
)
from mineocclude.probes.bridge import build_joined_frame_table, derive_probe_code_sha
from tests.probes.test_probe_bridge import make_multilayout_a_b_fixture


def _selection_inputs():
    activation, targets, *_ = make_multilayout_a_b_fixture()
    frame_table = build_joined_frame_table(activation, targets)
    visible = next(
        row for row in frame_table["rows"] if row["visibility"] == "visible"
    )
    hidden = next(
        row
        for row in frame_table["rows"]
        if row["visibility"] == "occluded"
        and row["log_sigma_oracle"] is not None
    )
    selections = [
        {
            "trajectory_id": visible["trajectory_id"],
            "model_frame_idx": visible["model_frame_idx"],
            "layout_id": visible["layout_id"],
            "scope": SCOPE_VISIBLE_NO_WALL,
            "condition_role": "no_wall_visible_control",
        },
        {
            "trajectory_id": hidden["trajectory_id"],
            "model_frame_idx": hidden["model_frame_idx"],
            "layout_id": hidden["layout_id"],
            "scope": SCOPE_HIDDEN_MEAN,
            "condition_role": "regime_a_core",
        },
        {
            "trajectory_id": hidden["trajectory_id"],
            "model_frame_idx": hidden["model_frame_idx"],
            "layout_id": hidden["layout_id"],
            "scope": SCOPE_HIDDEN_SPREAD,
            "condition_role": "regime_a_core",
        },
    ]
    return frame_table, selections


def test_selection_is_sealed_and_returns_exact_scope_keys() -> None:
    frame_table, selections = _selection_inputs()
    document = build_analysis_selection_manifest(
        frame_table,
        selections,
        artifact_id="known_answer_selection",
        code_sha=derive_probe_code_sha(),
        source_condition_manifest_hash="7" * 64,
    )

    validate_analysis_selection_manifest(document, frame_table=frame_table)
    hidden_key = (
        selections[1]["trajectory_id"],
        selections[1]["model_frame_idx"],
    )
    assert selected_frame_keys(
        document,
        scope=SCOPE_HIDDEN_MEAN,
        frame_table=frame_table,
    ) == (hidden_key,)
    assert document["synthetic"] is True
    assert document["scientific_use"] == "forbidden"


def test_visible_control_requires_manifest_declared_no_wall_role() -> None:
    frame_table, selections = _selection_inputs()
    selections[0]["condition_role"] = "regime_a_core"
    with pytest.raises(AnalysisSelectionError, match="no_wall_visible_control"):
        build_analysis_selection_manifest(
            frame_table,
            selections,
            artifact_id="bad_selection",
            code_sha=derive_probe_code_sha(),
            source_condition_manifest_hash="7" * 64,
        )


def test_selection_rejects_stale_layout_and_hash_tampering() -> None:
    frame_table, selections = _selection_inputs()
    stale = copy.deepcopy(selections)
    stale[0]["layout_id"] = "wrong_layout"
    with pytest.raises(AnalysisSelectionError, match="wrong layout"):
        build_analysis_selection_manifest(
            frame_table,
            stale,
            artifact_id="bad_selection",
            code_sha=derive_probe_code_sha(),
            source_condition_manifest_hash="7" * 64,
        )

    document = build_analysis_selection_manifest(
        frame_table,
        selections,
        artifact_id="known_answer_selection",
        code_sha=derive_probe_code_sha(),
        source_condition_manifest_hash="7" * 64,
    )
    document["rows"][0]["model_frame_idx"] += 1
    with pytest.raises(AnalysisSelectionError, match="Invalid selection artifact"):
        validate_analysis_selection_manifest(document, frame_table=frame_table)


def test_condition_source_must_be_predeclared_and_result_free() -> None:
    source = {
        "selection_source_schema_version": (
            "person-b-condition-selection-source-v0.1"
        ),
        "status": "accepted",
        "selection_policy": "predeclared_before_probe_results",
        "rows": [
            {
                "trajectory_id": "trajectory",
                "model_frame_idx": 2,
                "layout_id": "layout",
                "condition_role": "regime_a_core",
                "analysis_scopes": [SCOPE_HIDDEN_MEAN, SCOPE_HIDDEN_SPREAD],
                "status": "accepted",
            }
        ],
    }
    assert len(selections_from_condition_source(source)) == 2
    source["rows"][0]["r2"] = 0.99
    with pytest.raises(AnalysisSelectionError, match="result or outcome"):
        selections_from_condition_source(source)
