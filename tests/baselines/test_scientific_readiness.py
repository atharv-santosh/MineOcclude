"""Fail-closed tests for the Phase 4 Step 4.1 scientific baseline gate.

Item 8 of the Step 4.1 handoff asks for proof that four specific
conditions can never pass: ``UNASSIGNED_FOLD``, a missing oracle
identity, a missing sealed fold identity, and
``scientific_use=forbidden``. Each has its own test below.

None of these tests attempt to demonstrate a ``READY`` verdict. The
"best case" fixture (``_best_case_inputs``) is the most structurally
valid oracle target document buildable *without* Person B's real
coordinate-frame signoff and the real literal `configs/analysis
/core.yaml` hash binding -- and it still comes out BLOCKED, because
every such document this project's own oracle schema will accept
(`mineocclude.oracle.schema.validate_oracle_target_document`) without
that real signoff must be marked ``fixture_metadata.scientific_use
="forbidden"`` (see the schema's own `is_non_scientific_fixture`
bypass). That is not a limitation of this test suite -- it is the
intended, load-bearing property under test: it is currently
*impossible*, not just discouraged, to construct a document that
clears both B's own oracle schema and this gate without genuine real
data. See ``test_even_the_best_case_synthetic_fixture_is_blocked``.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mineocclude.baselines.capture_ingest import UNASSIGNED_FOLD
from mineocclude.baselines.interface import TrajectoryContext
from mineocclude.baselines.scientific_readiness import (
    BASELINE_PREDICTION_DIRECT_INPUTS,
    READY_SCIENTIFIC_USE,
    ScientificReadinessError,
    build_baseline_prediction_artifact_id,
    validate_scientific_baseline_readiness,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.oracle.schema import (
    ORACLE_INFORMATION_SET,
    ORACLE_METHOD,
    ORACLE_TARGET_SCHEMA_VERSION,
    TARGET_ID_SUFFIX,
    TARGET_SOURCE,
)

FOLD_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "person_d"
    / "synthetic_b_fold_manifest.json"
)

_CONST_RUN_ID = "run-synthetic-d-readiness-check"
_CONST_CODE_SHA = "d" * 40
_CONST_CONFIG_HASH = "b" * 64
_CONST_MODEL_HASH = "c" * 64
_CONST_PREPROCESS_HASH = "e" * 64
_CONST_ACCEPTED_MANIFEST_HASH = "a" * 64
_CONST_SOURCE_RUN_ID = "source-run-1"


def _fold_manifest():
    return json.loads(FOLD_FIXTURE_PATH.read_text(encoding="utf-8"))


def _best_case_inputs():
    """The most structurally valid inputs buildable without real B/A data.

    Every row is honestly, consistently marked
    ``regime="synthetic_test"``, ``synthetic=True``,
    ``scientific_use="forbidden"`` -- the same convention
    ``oracle.schema`` itself uses to allow a non-scientific fixture
    past its coordinate-frame/config-hash requirements. This is
    deliberately the *easiest* input to construct, to make the
    resulting BLOCKED verdict the strongest possible proof.
    """

    fold_manifest = _fold_manifest()
    keys = [
        (membership["trajectory_id"], membership["model_frame_idx"])
        for membership in fold_manifest["memberships"]
    ]
    fold_by_key = {
        (membership["trajectory_id"], membership["model_frame_idx"]): membership["fold_idx"]
        for membership in fold_manifest["memberships"]
    }

    contexts = [
        TrajectoryContext(
            trajectory_id=trajectory_id,
            layout_id=trajectory_id.replace("traj-", "layout-"),
            model_frame_idx=frame,
            fold=fold_by_key[(trajectory_id, frame)],
            regime="A",
            tau_seconds=0.0,
            visibility=True,
            last_seen_position_blocks=float(frame),
            last_seen_velocity_blocks_per_s=None,
            v_scripted_blocks_per_s=None,
            q_scripted_blocks2_per_s=None,
            duration_seconds=None,
            config_hash="cfg-test",
            seed=123,
        )
        for trajectory_id, frame in keys
    ]

    rows = []
    for trajectory_id, frame in keys:
        position = float(frame)
        rows.append(
            {
                "episode_id": f"ep-{trajectory_id}",
                "trajectory_id": trajectory_id,
                "server_tick": frame,
                "render_frame_idx": frame,
                "action_idx": frame,
                "model_frame_idx": frame,
                "layout_id": trajectory_id.replace("traj-", "layout-"),
                "regime": "synthetic_test",
                "visibility": "visible",
                "tau": 0.0,
                "v": 1.0,
                "q": 0.02,
                "duration": 3.0,
                "code_sha": _CONST_CODE_SHA,
                "config_hash": _CONST_CONFIG_HASH,
                "model_hash": _CONST_MODEL_HASH,
                "preprocess_hash": _CONST_PREPROCESS_HASH,
                "seed": 20260719,
                "schema_version": SCHEMA_VERSION,
                "run_id": _CONST_RUN_ID,
                "status": "accepted",
                "exclusion_reason": None,
                "superseded_by": None,
                "target_schema_version": ORACLE_TARGET_SCHEMA_VERSION,
                "target_id": f"{trajectory_id}:{frame}:{TARGET_ID_SUFFIX}",
                "target_source": TARGET_SOURCE,
                "oracle_method": ORACLE_METHOD,
                "oracle_information_set": list(ORACLE_INFORMATION_SET),
                "accepted_manifest_hash": _CONST_ACCEPTED_MANIFEST_HASH,
                "source_run_id": _CONST_SOURCE_RUN_ID,
                "last_visible_position_blocks": position,
                "mu_oracle_blocks": position,
                "var_oracle_blocks2": 0.0,
                "sigma_oracle_blocks": 0.0,
                "log_sigma_oracle": None,
                "x_true_blocks": position,
                "synthetic": True,
                "scientific_use": "forbidden",
            }
        )
    oracle_target_document = {
        "schema_version": SCHEMA_VERSION,
        "target_schema_version": ORACLE_TARGET_SCHEMA_VERSION,
        "join_key": ["trajectory_id", "model_frame_idx"],
        "rows": rows,
        "fixture_metadata": {"synthetic": True, "scientific_use": "forbidden"},
    }
    return contexts, fold_manifest, oracle_target_document


def test_even_the_best_case_synthetic_fixture_is_blocked():
    # This is the load-bearing proof: the most structurally valid,
    # fully self-consistent synthetic input this project's own oracle
    # schema will accept is still BLOCKED, and BLOCKED for exactly one
    # reason -- scientific_use=forbidden -- not any structural defect.
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=fold_manifest,
        oracle_target_document=oracle_target_document,
        candidate_scientific_use=READY_SCIENTIFIC_USE,
    )
    assert finding.status == "BLOCKED"
    assert len(finding.blocked_reasons) == 1
    assert "scientific_use" in finding.blocked_reasons[0]
    assert "forbidden" in finding.blocked_reasons[0]


def test_unassigned_fold_cannot_pass():
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    contexts = list(contexts)
    contexts[0] = replace(contexts[0], fold=UNASSIGNED_FOLD)

    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=fold_manifest,
        oracle_target_document=oracle_target_document,
        candidate_scientific_use=READY_SCIENTIFIC_USE,
    )
    assert finding.status == "BLOCKED"
    assert any("UNASSIGNED_FOLD" in reason for reason in finding.blocked_reasons)


def test_missing_sealed_fold_identity_cannot_pass():
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    broken_manifest = dict(fold_manifest)
    del broken_manifest["artifact_hash"]

    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=broken_manifest,
        oracle_target_document=oracle_target_document,
        candidate_scientific_use=READY_SCIENTIFIC_USE,
    )
    assert finding.status == "BLOCKED"
    assert any(
        "sealed B fold manifest identity" in reason for reason in finding.blocked_reasons
    )


def test_missing_oracle_identity_cannot_pass():
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    broken_document = dict(oracle_target_document)
    del broken_document["target_schema_version"]

    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=fold_manifest,
        oracle_target_document=broken_document,
        candidate_scientific_use=READY_SCIENTIFIC_USE,
    )
    assert finding.status == "BLOCKED"
    assert any(
        "B oracle target identity" in reason for reason in finding.blocked_reasons
    )


def test_scientific_use_forbidden_cannot_pass():
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    # Already forbidden in the base fixture; assert explicitly rather
    # than relying on the best-case test alone, since this is the one
    # item-8 condition every other test above also happens to trip.
    assert oracle_target_document["fixture_metadata"]["scientific_use"] == "forbidden"

    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=fold_manifest,
        oracle_target_document=oracle_target_document,
        candidate_scientific_use=READY_SCIENTIFIC_USE,
    )
    assert finding.status == "BLOCKED"
    assert any("forbidden" in reason for reason in finding.blocked_reasons)


def test_non_accepted_candidate_scientific_use_cannot_pass():
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()

    for candidate in ("pending", "forbidden", "synthetic", ""):
        if candidate == "":
            with pytest.raises(ScientificReadinessError):
                validate_scientific_baseline_readiness(
                    contexts,
                    fold_manifest=fold_manifest,
                    oracle_target_document=oracle_target_document,
                    candidate_scientific_use=candidate,
                )
            continue
        finding = validate_scientific_baseline_readiness(
            contexts,
            fold_manifest=fold_manifest,
            oracle_target_document=oracle_target_document,
            candidate_scientific_use=candidate,
        )
        assert finding.status == "BLOCKED"
        assert any("candidate_scientific_use" in reason for reason in finding.blocked_reasons)


def test_coverage_mismatch_cannot_pass():
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    short_document = dict(oracle_target_document)
    short_document["rows"] = oracle_target_document["rows"][:-1]

    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=fold_manifest,
        oracle_target_document=short_document,
        candidate_scientific_use=READY_SCIENTIFIC_USE,
    )
    assert finding.status == "BLOCKED"
    assert any("coverage" in reason for reason in finding.blocked_reasons)


def test_multiple_simultaneous_violations_are_all_reported():
    # The gate collects every violation rather than stopping at the
    # first, so a caller fixing one problem doesn't rediscover the
    # rest one at a time.
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    contexts = list(contexts)
    contexts[0] = replace(contexts[0], fold=UNASSIGNED_FOLD)
    broken_manifest = dict(fold_manifest)
    del broken_manifest["artifact_hash"]

    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=broken_manifest,
        oracle_target_document=oracle_target_document,
        candidate_scientific_use="pending",
    )
    assert finding.status == "BLOCKED"
    joined = " | ".join(finding.blocked_reasons)
    assert "UNASSIGNED_FOLD" in joined
    assert "sealed B fold manifest identity" in joined
    assert "candidate_scientific_use" in joined
    assert "forbidden" in joined


def test_artifact_id_is_deterministic_and_sensitive_to_every_direct_input():
    base_kwargs = dict(
        baseline_id="last_seen_v1",
        target_name="mu_oracle_blocks",
        fold_manifest_hash="1" * 64,
        oracle_target_hash="2" * 64,
        config_hash="3" * 64,
    )
    first = build_baseline_prediction_artifact_id(**base_kwargs)
    second = build_baseline_prediction_artifact_id(**base_kwargs)
    assert first == second
    assert first.startswith("person_d_baseline_prediction::")

    for field in ("baseline_id", "target_name", *BASELINE_PREDICTION_DIRECT_INPUTS):
        changed_kwargs = dict(base_kwargs)
        changed_kwargs[field] = changed_kwargs[field] + "_changed"
        changed = build_baseline_prediction_artifact_id(**changed_kwargs)
        assert changed != first, f"changing {field} did not change the artifact ID"


def test_rejects_a_malformed_call():
    _, fold_manifest, oracle_target_document = _best_case_inputs()
    with pytest.raises(ScientificReadinessError, match="no contexts"):
        validate_scientific_baseline_readiness(
            [],
            fold_manifest=fold_manifest,
            oracle_target_document=oracle_target_document,
            candidate_scientific_use=READY_SCIENTIFIC_USE,
        )
