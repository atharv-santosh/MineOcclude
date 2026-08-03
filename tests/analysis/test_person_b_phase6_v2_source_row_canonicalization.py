"""Focused owner-dispatch and real-row regression for Person B Step 6.6."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from mineocclude.analysis import coordinates_v2
from mineocclude.analysis.positive_control_v2 import (
    ALL_PILOT_IDS,
    FROZEN_LAYOUT_FOLDS,
    FROZEN_TARGET_NAME,
    FROZEN_THRESHOLD_POLICY,
    VISIBLE_CONTROL_PILOT_IDS,
    build_positive_control_bridge_v2,
    validate_ten_pilot_authority_documents,
)
from mineocclude.contracts.activation_v2 import (
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE,
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT,
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_DIGEST_DOMAIN,
    PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
    REGISTRY_V2_CANONICALIZATION_CONTRACT,
    REGISTRY_V2_RECORD_ARTIFACT_TYPE,
    ActivationV2ConsumerError,
    canonical_json_bytes_for_artifact,
    derive_visual_token_positions,
)
from mineocclude.experiments.registry import (
    canonical_json_bytes as registry_v2_canonical_json_bytes,
)

REPOSITORY = Path(__file__).resolve().parents[2]
PERSON_A_COMMIT = "55776dc88302b89b52eef483a710fbf6811cf536"
A_RUNTIME_ROOT = (
    "docs/status/phase6_runtime/"
    "person-a-phase6-ten-pilot-expansion-seed-20260725"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _person_a_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _contract_arguments() -> dict[str, str]:
    return {
        "source_row_artifact_type": (
            PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE
        ),
        "source_row_producer_commit": PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
        "source_row_canonicalization_contract": (
            PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT
        ),
        "source_row_digest_domain": (
            PERSON_A_ACTIVATION_SOURCE_ROW_V2_DIGEST_DOMAIN
        ),
    }


def _fixture_package() -> dict:
    trajectory_id = "layout_fixture_ep0001"
    frame_rows = [
        {
            "model_frame_idx": index,
            "render_frame_idx": index,
            "server_tick": index,
            "trajectory_id": trajectory_id,
            "unicode_note": "café",
        }
        for index in (1, 0)
    ]
    state_rows = [
        {
            "model_frame_idx": index,
            "render_frame_idx": index,
            "server_tick": index,
            "state": {"wall_parallel_position_blocks": float(index)},
            "trajectory_id": trajectory_id,
        }
        for index in (0, 1)
    ]
    return {
        "artifacts": {
            "frame_map": {"sha256": _sha256(b"frame-map")},
            "server_state": {"sha256": _sha256(b"server-state")},
        },
        "condition": "no_wall_visible",
        "streams": {"frame_map": frame_rows, "server_state": state_rows},
        "trajectory_id": trajectory_id,
    }


def _fake_state_v1(package: dict) -> dict:
    trajectory_id = package["trajectory_id"]
    manifest = _sha256(b"canonical-episode-manifest")
    return {
        "accepted_manifest_hash": manifest,
        "rows": [
            {
                "accepted_manifest_hash": manifest,
                "layout_id": "layout_fixture",
                "model_frame_idx": index,
                "trajectory_id": trajectory_id,
                "visibility": "visible",
                "x_true_blocks": float(index),
            }
            for index in (1, 0)
        ],
    }


def _build_fixture_state(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    *,
    expected_literal_sha256: str | None = None,
    **contract_overrides: str,
) -> dict:
    monkeypatch.setattr(
        coordinates_v2,
        "build_state_input_from_capture_package",
        lambda package, **_kwargs: _fake_state_v1(package),
    )
    contract = {**_contract_arguments(), **contract_overrides}
    return coordinates_v2.build_state_input_v2_from_capture_bytes(
        payload,
        expected_literal_capture_package_sha256=(
            expected_literal_sha256 or _sha256(payload)
        ),
        coordinate_frame={},
        model_hash=_sha256(b"model"),
        preprocess_hash=_sha256(b"preprocess"),
        **contract,
    )


def test_owner_dispatch_preserves_person_a_and_registry_domains() -> None:
    row = {
        "trajectory_id": "layout_fixture_ep0001",
        "model_frame_idx": 0,
        "render_frame_idx": 0,
        "server_tick": 0,
        "unicode_note": "café",
    }
    person_a = canonical_json_bytes_for_artifact(
        row,
        artifact_type=PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE,
        canonicalization_contract=(
            PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT
        ),
    )
    registry = canonical_json_bytes_for_artifact(
        row,
        artifact_type=REGISTRY_V2_RECORD_ARTIFACT_TYPE,
        canonicalization_contract=REGISTRY_V2_CANONICALIZATION_CONTRACT,
    )
    assert person_a == _person_a_bytes(row)
    assert person_a.endswith(b"\n")
    assert b'\n  "model_frame_idx"' in person_a
    assert b"caf\xc3\xa9" in person_a
    assert registry == registry_v2_canonical_json_bytes(row)
    assert not registry.endswith(b"\n")
    assert person_a != registry


def test_source_rows_join_by_global_identity_not_row_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _fixture_package()
    payload = json.dumps(package, indent=2).encode("utf-8")
    state = _build_fixture_state(monkeypatch, payload)
    frame_by_id = {
        row["model_frame_idx"]: row for row in package["streams"]["frame_map"]
    }
    source_state_by_id = {
        row["model_frame_idx"]: row for row in package["streams"]["server_state"]
    }
    assert [row["global_model_frame_idx"] for row in state["rows"]] == [1, 0]
    for row in state["rows"]:
        global_idx = row["global_model_frame_idx"]
        assert row["c_frame_map_row_sha256"] == _sha256(
            _person_a_bytes(frame_by_id[global_idx])
        )
        assert row["c_state_row_sha256"] == _sha256(
            _person_a_bytes(source_state_by_id[global_idx])
        )
        assert row["source_tick"] == global_idx
        assert row["source_frame_idx"] == global_idx
    assert state["source_row_artifact_type"] == (
        PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE
    )
    assert state["source_row_digest_domain"] == (
        PERSON_A_ACTIVATION_SOURCE_ROW_V2_DIGEST_DOMAIN
    )
    assert state["literal_capture_package_sha256"] != (
        state["canonical_state_object_sha256"]
    )


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("source_row_artifact_type", REGISTRY_V2_RECORD_ARTIFACT_TYPE),
        ("source_row_producer_commit", "0" * 40),
        (
            "source_row_canonicalization_contract",
            REGISTRY_V2_CANONICALIZATION_CONTRACT,
        ),
        ("source_row_digest_domain", "unknown-source-row-domain"),
    ],
)
def test_wrong_or_unknown_source_contract_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    override: str,
    value: str,
) -> None:
    payload = json.dumps(_fixture_package(), indent=2).encode("utf-8")
    with pytest.raises(coordinates_v2.StateInputV2Error, match="conflicts"):
        _build_fixture_state(monkeypatch, payload, **{override: value})


def test_registry_digest_substitution_is_rejected() -> None:
    row = _fixture_package()["streams"]["frame_map"][0]
    with pytest.raises(
        ActivationV2ConsumerError,
        match="exact Person A producer contract",
    ):
        canonical_json_bytes_for_artifact(
            row,
            artifact_type=PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE,
            canonicalization_contract=REGISTRY_V2_CANONICALIZATION_CONTRACT,
        )


def test_literal_whitespace_key_order_and_value_changes_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _fixture_package()
    original = json.dumps(package, indent=2).encode("utf-8")
    original_hash = _sha256(original)
    changed_value = json.loads(original)
    changed_value["streams"]["frame_map"][0]["server_tick"] = 0
    variants = (
        json.dumps(package, separators=(",", ":")).encode("utf-8"),
        json.dumps(dict(reversed(tuple(package.items()))), indent=2).encode("utf-8"),
        json.dumps(changed_value, indent=2).encode("utf-8"),
    )
    for variant in variants:
        assert variant != original
        with pytest.raises(
            coordinates_v2.StateInputV2Error,
            match="Literal capture-package SHA-256",
        ):
            _build_fixture_state(
                monkeypatch,
                variant,
                expected_literal_sha256=original_hash,
            )


def test_exact_sagemaker_visible_rows_join_without_fit() -> None:
    import scripts.run_person_b_phase6_v2_positive_control_sagemaker as runner

    if not Path(
        "/home/sagemaker-user/person-a-phase6-approved-outputs"
    ).is_dir():
        pytest.skip("Exact external Person A evidence is not mounted.")
    completion, artifact_manifest, handoff, inventories, c_acceptance = (
        runner._load_authority_documents(REPOSITORY)
    )
    authority = validate_ten_pilot_authority_documents(
        completion_report=completion,
        artifact_manifest=artifact_manifest,
        positive_control_handoff=handoff,
        per_pilot_inventories=inventories,
        c_accepted_manifest=c_acceptance,
    )
    indices = runner._load_indices(
        inventories,
        accepted_manifest_by_trajectory=(
            authority.accepted_c_manifest_by_trajectory
        ),
    )
    states = runner._load_control_states(
        REPOSITORY,
        indices=indices,
        capture_path_by_trajectory=authority.c_capture_path_by_trajectory,
        accepted_manifest_by_trajectory=(
            authority.accepted_c_manifest_by_trajectory
        ),
    )
    fold_plan = json.loads(
        (
            REPOSITORY
            / "data/person_b/phase6_c_intake/layout_fold_plan.json"
        ).read_text(encoding="utf-8")
    )
    bridge = build_positive_control_bridge_v2(
        indices,
        states,
        authority=authority,
        fold_plan=fold_plan,
    )

    assert len(indices) == 10
    assert sum(index.activation_row_count for index in indices.values()) == 37_480
    assert sum(len(index.chunks) for index in indices.values()) == 200
    assert len(
        {index.accepted_manifest_sha256 for index in indices.values()}
    ) == 10
    assert bridge.row_count == 1_000
    assert bridge.layout_count == 5
    assert bridge.target_name == FROZEN_TARGET_NAME == "x_true_blocks"
    assert bridge.threshold_policy == FROZEN_THRESHOLD_POLICY
    assert bridge.scientific_execution_performed is False
    assert len(bridge.matrices) == 20
    assert {len(matrix.features) for matrix in bridge.matrices} == {1_000}
    assert {frozenset(matrix.outer_folds) for matrix in bridge.matrices} == {
        frozenset(FROZEN_LAYOUT_FOLDS.values())
    }
    assert set(states) == set(VISIBLE_CONTROL_PILOT_IDS)
    assert all(state["condition"] == "no_wall_visible" for state in states.values())
    assert all(
        row["visibility"] == "visible"
        for state in states.values()
        for row in state["rows"]
    )
    assert all(
        0 <= row["context_local_pair_idx"] <= 15
        and tuple(row["frame_token_positions"])
        == derive_visual_token_positions(row["context_local_pair_idx"])
        for index in indices.values()
        for row in index.rows
    )
    assert all(
        array.dtype == np.float32 and bool(np.isfinite(array).all())
        for index in indices.values()
        for array in index.arrays_by_chunk_id.values()
    )

    compact_substitutions = 0
    matched_rows = 0
    for trajectory_id in VISIBLE_CONTROL_PILOT_IDS:
        capture = json.loads(
            runner._git(
                REPOSITORY,
                "show",
                (
                    f"{runner.PERSON_C_ACCEPTANCE_COMMIT}:"
                    f"{authority.c_capture_path_by_trajectory[trajectory_id]}"
                ),
                text=False,
            )
        )
        frame_source_by_id = {
            row["model_frame_idx"]: row
            for row in capture["streams"]["frame_map"]
        }
        state_source_by_id = {
            row["model_frame_idx"]: row
            for row in capture["streams"]["server_state"]
        }
        activation_by_frame = {}
        for row in indices[trajectory_id].rows:
            activation_by_frame.setdefault(row["global_model_frame_idx"], row)
        state_by_frame = {
            row["global_model_frame_idx"]: row for row in states[trajectory_id]["rows"]
        }
        assert set(activation_by_frame) == set(state_by_frame) == set(range(200))
        for frame_idx, activation in activation_by_frame.items():
            state = state_by_frame[frame_idx]
            frame_source = frame_source_by_id[frame_idx]
            state_source = state_source_by_id[frame_idx]
            assert activation["c_frame_map_row_sha256"] == (
                state["c_frame_map_row_sha256"]
            )
            assert activation["c_state_row_sha256"] == state["c_state_row_sha256"]
            assert activation["c_frame_map_row_sha256"] == _sha256(
                _person_a_bytes(frame_source)
            )
            assert activation["c_state_row_sha256"] == _sha256(
                _person_a_bytes(state_source)
            )
            compact_substitutions += activation["c_frame_map_row_sha256"] == (
                _sha256(registry_v2_canonical_json_bytes(frame_source))
            )
            compact_substitutions += activation["c_state_row_sha256"] == (
                _sha256(registry_v2_canonical_json_bytes(state_source))
            )
            matched_rows += 1
        assert states[trajectory_id]["source_row_canonicalization_contract"] == (
            PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT
        )
        assert states[trajectory_id]["source_row_producer_commit"] == PERSON_A_COMMIT
    assert matched_rows == 1_000
    assert compact_substitutions == 0

    combined_binding = artifact_manifest["combined_activation_index"]
    combined_path = Path(combined_binding["external_path"])
    assert combined_path.stat().st_size == combined_binding["byte_size"]
    assert _sha256(combined_path.read_bytes()) == combined_binding["sha256"]
    combined = json.loads(combined_path.read_bytes())
    identity_fields = (
        "trajectory_id",
        "global_model_frame_idx",
        "source_frame_id",
        "source_tick",
        "layer_idx",
        "hook_site",
        "checkpoint_hash",
        "preprocess_hash",
    )
    per_pilot_union = {
        tuple(row[field] for field in identity_fields)
        for trajectory_id in ALL_PILOT_IDS
        for row in indices[trajectory_id].rows
    }
    combined_set = {
        tuple(row[field] for field in identity_fields)
        for row in combined["index_rows"]
    }
    assert len(per_pilot_union) == len(combined_set) == 37_480
    assert per_pilot_union == combined_set
    assert completion["missing_activation_row_count"] == 0
    assert completion["duplicate_activation_row_count"] == 0
    assert completion["nonfinite_activation_count"] == 0
    assert combined["scientific_identity_collision_count"] == 0
