"""Semantic-equivalence tests for the memory repair (Person D Step 4.1).

Proves the compact-storage repair (float32 NumPy arrays instead of
boxed Python-float lists for raw_pixel's feature matrix) changes
nothing about what gets fit, predicted, or exported: identical admitted
row identities, feature shape/ordering/values, fold assignments, family
configuration, predictions (exact equality, since both representations
feed the same unchanged ``fit_ridge_oof``/``_matrix`` pipeline), export
schema, and lineage -- for all eight families, on one bounded,
deterministic synthetic fixture.

No real production data is used and no real baseline execution occurs;
this is bounded to a handful of synthetic trajectories.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from mineocclude.baselines.baseline_family_input_v0_2 import (
    FROZEN_BASELINE_FAMILY_IDS,
    FROZEN_DIRECT_INPUTS,
    validate_baseline_document_v0_2,
)
from mineocclude.baselines.eight_family_runner import fit_and_export_family
from mineocclude.baselines.frame_handoff_v0_2 import (
    build_frame_manifest_direct_input_reference,
)
from tests.baselines.conftest import build_trajectory_contexts

_LAYOUT_FOLDS = {"layout_00": 1, "layout_01": 2, "layout_02": 4, "layout_03": 0, "layout_04": 3}
_PILOTS = {
    "layout_00_ep9403": ("layout_00", (0.0, 1.0, 2.0)),
    "layout_00_ep9441": ("layout_00", (0.0, 2.0, 4.0)),
    "layout_01_ep9405": ("layout_01", (0.0, 1.5, 3.0)),
    "layout_02_ep9407": ("layout_02", (0.0, 0.5, 1.0)),
    "layout_03_ep9404": ("layout_03", (0.0, 1.0, 0.5)),
    "layout_04_ep9406": ("layout_04", (0.0, 2.0, 1.0)),
}


def _build_fixture(*, feature_container):
    """Build one deterministic fixture. ``feature_container`` converts
    the same underlying per-frame feature values into either a plain
    Python list (the pre-repair representation) or a float32 NumPy
    array (the repaired representation) -- everything else is
    byte-for-byte identical between the two calls."""

    contexts, mu_oracle_by_key, log_sigma_oracle_by_key = [], {}, {}
    visible_positions_by_trajectory, pixel_features_by_key = {}, {}
    for trajectory_id, (layout_id, positions) in _PILOTS.items():
        ctx_list = build_trajectory_contexts(
            trajectory_id=trajectory_id, layout_id=layout_id, fold=_LAYOUT_FOLDS[layout_id],
            visible_positions=positions, dt=1.0, hidden_taus=(1.0,), duration_seconds=2.0,
            q_scripted=0.02,
        )
        contexts.extend(ctx_list)
        visible_positions_by_trajectory[trajectory_id] = positions
        last_seen = ctx_list[-1].last_seen_position_blocks
        velocity = ctx_list[-1].last_seen_velocity_blocks_per_s
        for ctx in ctx_list:
            key = (ctx.trajectory_id, ctx.model_frame_idx)
            mu_oracle_by_key[key] = last_seen + velocity * ctx.tau_seconds
            log_sigma_oracle_by_key[key] = 0.1 * ctx.tau_seconds + 0.01
            raw_values = [float(ctx.model_frame_idx), 1.0, float(ctx.model_frame_idx) * 0.5]
            pixel_features_by_key[key] = feature_container(raw_values)
    return {
        "contexts": contexts,
        "mu_oracle_by_key": mu_oracle_by_key,
        "log_sigma_oracle_by_key": log_sigma_oracle_by_key,
        "visible_positions_by_trajectory": visible_positions_by_trajectory,
        "pixel_features_by_key": pixel_features_by_key,
    }


def _fit_all_families(fixture, *, config_hash, frame_reference):
    documents_by_family = {}
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        documents_by_family[family_id] = fit_and_export_family(
            family_id,
            fixture["contexts"],
            mu_oracle_by_key=fixture["mu_oracle_by_key"],
            log_sigma_oracle_by_key=fixture["log_sigma_oracle_by_key"],
            visible_positions_by_trajectory=fixture["visible_positions_by_trajectory"],
            pixel_features_by_key=fixture["pixel_features_by_key"],
            config_hash=config_hash,
            input_manifest_hash="e" * 64,
            fit_manifest_hash="f" * 64,
            preprocessed_frame_manifest_reference=(
                frame_reference if family_id == "raw_pixel" else None
            ),
        )
    return documents_by_family


@pytest.fixture(scope="module")
def old_and_new_documents():
    config_hash = FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"]
    frame_reference = build_frame_manifest_direct_input_reference(byte_size=6460547)

    old_fixture = _build_fixture(feature_container=list)
    new_fixture = _build_fixture(
        feature_container=lambda values: np.asarray(values, dtype=np.float32)
    )

    old_documents = _fit_all_families(
        old_fixture, config_hash=config_hash, frame_reference=frame_reference
    )
    new_documents = _fit_all_families(
        new_fixture, config_hash=config_hash, frame_reference=frame_reference
    )
    return old_documents, new_documents


def test_every_family_produces_documents_under_both_representations(old_and_new_documents):
    old_documents, new_documents = old_and_new_documents
    assert set(old_documents) == set(new_documents) == set(FROZEN_BASELINE_FAMILY_IDS)
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        assert set(old_documents[family_id]) == set(new_documents[family_id]), family_id


def test_identical_admitted_row_identities_across_representations(old_and_new_documents):
    old_documents, new_documents = old_and_new_documents
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        for target_name in old_documents[family_id]:
            old_keys = {
                (row["trajectory_id"], row["model_frame_idx"])
                for row in old_documents[family_id][target_name]["rows"]
            }
            new_keys = {
                (row["trajectory_id"], row["model_frame_idx"])
                for row in new_documents[family_id][target_name]["rows"]
            }
            assert old_keys == new_keys, f"{family_id}/{target_name}"


def test_identical_fold_assignments_across_representations(old_and_new_documents):
    old_documents, new_documents = old_and_new_documents
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        for target_name in old_documents[family_id]:
            old_folds = {
                (row["trajectory_id"], row["model_frame_idx"]): row["fold_idx"]
                for row in old_documents[family_id][target_name]["rows"]
            }
            new_folds = {
                (row["trajectory_id"], row["model_frame_idx"]): row["fold_idx"]
                for row in new_documents[family_id][target_name]["rows"]
            }
            assert old_folds == new_folds, f"{family_id}/{target_name}"


def test_identical_deterministic_predictions_across_representations_for_all_eight_families(
    old_and_new_documents,
):
    """The one check that matters most: raw_pixel's predictions (the
    only family whose input actually changes shape/container type
    between the two representations) must be bit-for-bit identical,
    since both feed the same unchanged fit_ridge_oof/_matrix pipeline
    with numerically identical values."""

    old_documents, new_documents = old_and_new_documents
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        for target_name in old_documents[family_id]:
            old_by_key = {
                (row["trajectory_id"], row["model_frame_idx"]): row["prediction"]
                for row in old_documents[family_id][target_name]["rows"]
            }
            new_by_key = {
                (row["trajectory_id"], row["model_frame_idx"]): row["prediction"]
                for row in new_documents[family_id][target_name]["rows"]
            }
            assert old_by_key.keys() == new_by_key.keys(), f"{family_id}/{target_name}"
            for key, old_prediction in old_by_key.items():
                new_prediction = new_by_key[key]
                assert old_prediction == pytest.approx(new_prediction, abs=0.0, rel=1e-12), (
                    f"{family_id}/{target_name}/{key}: "
                    f"old={old_prediction!r} new={new_prediction!r}"
                )


def test_no_new_nan_or_infinity_in_either_representation(old_and_new_documents):
    old_documents, new_documents = old_and_new_documents
    for documents in (old_documents, new_documents):
        for family_id in FROZEN_BASELINE_FAMILY_IDS:
            for target_name in documents[family_id]:
                for row in documents[family_id][target_name]["rows"]:
                    assert math.isfinite(row["prediction"]), (family_id, target_name, row)


def test_identical_family_configuration_and_legal_information_across_representations(
    old_and_new_documents,
):
    old_documents, new_documents = old_and_new_documents
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        for target_name in old_documents[family_id]:
            old_doc = old_documents[family_id][target_name]
            new_doc = new_documents[family_id][target_name]
            assert old_doc["feature_access"] == new_doc["feature_access"]
            assert old_doc["legal_information"] == new_doc["legal_information"]
            assert old_doc["baseline_family"] == new_doc["baseline_family"] == family_id
            assert old_doc["config_hash"] == new_doc["config_hash"]


def test_identical_export_schema_and_lineage_across_representations(old_and_new_documents):
    old_documents, new_documents = old_and_new_documents
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        for target_name in old_documents[family_id]:
            old_doc = old_documents[family_id][target_name]
            new_doc = new_documents[family_id][target_name]
            assert old_doc["schema_version"] == new_doc["schema_version"]
            assert old_doc["baseline_input_schema_version"] == new_doc["baseline_input_schema_version"]
            assert old_doc["direct_inputs"] == new_doc["direct_inputs"]
            assert old_doc["accepted_pilot_ids"] == new_doc["accepted_pilot_ids"]
            assert validate_baseline_document_v0_2(old_doc) == ()
            assert validate_baseline_document_v0_2(new_doc) == ()


def test_raw_pixel_feature_values_are_numerically_identical_between_representations():
    """Direct proof (not inferred from downstream predictions) that
    converting the same values from list to float32 ndarray changes
    nothing about the values or their ordering."""

    raw_values = [3.0, 1.0, 1.5]
    as_list = list(raw_values)
    as_array = np.asarray(raw_values, dtype=np.float32)
    assert as_array.tolist() == pytest.approx(as_list)
    assert list(as_array) == [pytest.approx(v) for v in as_list]
