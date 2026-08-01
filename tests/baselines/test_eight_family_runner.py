"""Tests for the real per-family fit/export dispatcher.

Exercises ``fit_and_export_family``/``compute_family_rows`` for all
eight frozen families against small synthetic contexts and targets.
No U4 path is touched; no baseline definition, seed, or configuration
is overridden from each family module's own frozen defaults.
"""

from __future__ import annotations

import pytest

from mineocclude.baselines.baseline_family_input_v0_2 import (
    FROZEN_BASELINE_FAMILY_IDS,
    FROZEN_DIRECT_INPUTS,
    validate_baseline_document_v0_2,
)
from mineocclude.baselines.eight_family_runner import (
    EightFamilyRunnerError,
    fit_and_export_family,
)
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


def _synthetic_inputs():
    contexts = []
    mu_oracle_by_key = {}
    log_sigma_oracle_by_key = {}
    visible_positions_by_trajectory = {}
    pixel_features_by_key = {}
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
            pixel_features_by_key[key] = [float(ctx.model_frame_idx), 1.0]
    return (
        contexts,
        mu_oracle_by_key,
        log_sigma_oracle_by_key,
        visible_positions_by_trajectory,
        pixel_features_by_key,
    )


@pytest.mark.parametrize("family_id", FROZEN_BASELINE_FAMILY_IDS)
def test_every_family_fits_and_exports_a_valid_v0_2_document(family_id):
    (
        contexts, mu_oracle_by_key, log_sigma_oracle_by_key,
        visible_positions_by_trajectory, pixel_features_by_key,
    ) = _synthetic_inputs()
    frame_ref = build_frame_manifest_direct_input_reference(byte_size=6460547)

    documents = fit_and_export_family(
        family_id, contexts,
        mu_oracle_by_key=mu_oracle_by_key,
        log_sigma_oracle_by_key=log_sigma_oracle_by_key,
        visible_positions_by_trajectory=visible_positions_by_trajectory,
        pixel_features_by_key=pixel_features_by_key,
        config_hash=FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
        input_manifest_hash="e" * 64,
        fit_manifest_hash="f" * 64,
        preprocessed_frame_manifest_reference=frame_ref if family_id == "raw_pixel" else None,
    )
    assert documents  # at least one target produced
    for target_name, document in documents.items():
        assert document["baseline_family"] == family_id
        assert document["target_name"] == target_name
        assert validate_baseline_document_v0_2(document) == ()


def test_unsupported_family_raises():
    (
        contexts, mu_oracle_by_key, log_sigma_oracle_by_key,
        visible_positions_by_trajectory, pixel_features_by_key,
    ) = _synthetic_inputs()
    with pytest.raises(EightFamilyRunnerError, match="unsupported"):
        fit_and_export_family(
            "not_a_real_family", contexts,
            mu_oracle_by_key=mu_oracle_by_key,
            log_sigma_oracle_by_key=log_sigma_oracle_by_key,
            visible_positions_by_trajectory=visible_positions_by_trajectory,
            pixel_features_by_key=pixel_features_by_key,
            config_hash=FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
            input_manifest_hash="e" * 64,
            fit_manifest_hash="f" * 64,
        )


def test_grouped_shuffled_produces_both_targets():
    (
        contexts, mu_oracle_by_key, log_sigma_oracle_by_key,
        visible_positions_by_trajectory, pixel_features_by_key,
    ) = _synthetic_inputs()
    documents = fit_and_export_family(
        "grouped_shuffled", contexts,
        mu_oracle_by_key=mu_oracle_by_key,
        log_sigma_oracle_by_key=log_sigma_oracle_by_key,
        visible_positions_by_trajectory=visible_positions_by_trajectory,
        pixel_features_by_key=pixel_features_by_key,
        config_hash=FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
        input_manifest_hash="e" * 64,
        fit_manifest_hash="f" * 64,
    )
    assert set(documents) == {"log_sigma_oracle", "mu_oracle_blocks"}
