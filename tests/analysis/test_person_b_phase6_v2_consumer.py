"""Focused deterministic tests for Person B's additive v2 consumer."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import mineocclude.analysis.positive_control_v2 as control_v2
from mineocclude.analysis import coordinates_v2
from mineocclude.analysis.positive_control_v2 import (
    ALL_PILOT_IDS,
    EXPECTED_TOTAL_ACTIVATION_ROWS,
    FROZEN_LAYOUT_FOLDS,
    FROZEN_TARGET_NAME,
    FROZEN_THRESHOLD_POLICY,
    PERSON_B_AUTHORIZATION_COMMIT,
    PERSON_B_SELECTION_COMMIT,
    PERSON_C_ACCEPTANCE_COMMIT,
    VISIBLE_CONTROL_PILOT_IDS,
    build_positive_control_bridge_v2,
    validate_ten_pilot_authority_documents,
)
from mineocclude.contracts.activation import validate_activation_handoff
from mineocclude.contracts.activation_v2 import (
    ACTIVATION_INDEX_V2_FORMAT_VERSION,
    ACTIVATION_STORE_V2_FORMAT_VERSION,
    PERSON_A_ACTIVATION_INDEX_V2_ARTIFACT_TYPE,
    PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT,
    REGISTRY_V2_CANONICALIZATION_CONTRACT,
    REGISTRY_V2_RECORD_ARTIFACT_TYPE,
    ActivationV2ConsumerError,
    ExternalChunkBinding,
    LoadedActivationIndexV2,
    canonical_json_bytes_for_artifact,
    derive_visual_token_positions,
    dispatch_activation_document,
    load_activation_index_v2,
    person_a_activation_index_v2_canonical_json_bytes,
    person_a_activation_index_v2_snapshot_digest,
    validate_activation_index_v2_bytes,
)
from mineocclude.experiments.registry import (
    canonical_json_bytes as registry_v2_canonical_json_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def HASH(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


ACTIVATION_COUNTS = {
    "layout_00_ep9403": 4960,
    "layout_00_ep9441": 4000,
    "layout_01_ep9405": 4600,
    "layout_01_ep9442": 4000,
    "layout_02_ep9407": 3160,
    "layout_02_ep9432": 4000,
    "layout_03_ep9404": 2500,
    "layout_03_ep9443": 4000,
    "layout_04_ep9406": 2260,
    "layout_04_ep9444": 4000,
}


def _scientific_key(row: dict) -> dict:
    return {
        "checkpoint_hash": row["checkpoint_hash"],
        "global_model_frame_idx": row["global_model_frame_idx"],
        "hook_site": row["hook_site"],
        "layer_idx": row["layer_idx"],
        "preprocess_hash": row["preprocess_hash"],
        "producing_run_id": row["run_id"],
        "source_frame_id": row["source_frame_id"],
        "source_tick": row["source_tick"],
        "trajectory_id": row["trajectory_id"],
    }


def _write_index_fixture(
    tmp_path: Path,
    *,
    trajectory_id: str = "layout_00_ep9441",
    global_indices: tuple[int, ...] = (15, 16),
    local_indices: tuple[int, ...] = (15, 0),
    array: np.ndarray | None = None,
) -> tuple[Path, str, int, dict, ExternalChunkBinding]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest = HASH(f"manifest:{trajectory_id}")
    store = {
        "accepted_manifest_hash": manifest,
        "checkpoint_hash": HASH("checkpoint"),
        "code_sha": "a" * 40,
        "config_hash": HASH("config"),
        "dtype": "float32",
        "format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
        "hidden_width": 3,
        "hook_site": "decoder_block_output",
        "model_hash": HASH("model"),
        "preprocess_hash": HASH("preprocess"),
        "requested_layers": [0],
        "run_id": "fixture-run",
        "schema_version": "1.0",
    }
    chunk_id = "activation-v2-chunk-fixture"
    rows = []
    for chunk_row_idx, (global_idx, local_idx) in enumerate(
        zip(global_indices, local_indices, strict=True)
    ):
        rows.append(
            {
                "accepted_manifest_hash": manifest,
                "activation_chunk_id": chunk_id,
                "c_frame_map_row_sha256": HASH(f"frame-row:{global_idx}"),
                "c_frame_map_sha256": HASH("frame-map"),
                "c_state_row_sha256": HASH(f"state-row:{global_idx}"),
                "c_state_sha256": HASH("state"),
                "checkpoint_hash": store["checkpoint_hash"],
                "chunk_row_idx": chunk_row_idx,
                "code_sha": store["code_sha"],
                "config_hash": store["config_hash"],
                "context_local_pair_idx": local_idx,
                "dtype": "float32",
                "exclusion_reason": None,
                "frame_token_map_sha256": HASH(f"token-map:{global_idx}"),
                "frame_token_positions": list(derive_visual_token_positions(local_idx)),
                "global_model_frame_idx": global_idx,
                "hook_site": store["hook_site"],
                "layer_idx": 0,
                "model_hash": store["model_hash"],
                "pooling_method": "mean",
                "preprocess_hash": store["preprocess_hash"],
                "run_id": store["run_id"],
                "run_status": "completed",
                "schema_version": "1.0",
                "source_frame_id": f"{trajectory_id}:render_frame:{global_idx}",
                "source_frame_idx": global_idx,
                "source_tick": global_idx,
                "status": "accepted",
                "store_format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
                "superseded_by": None,
                "token_region": "visual",
                "trajectory_id": trajectory_id,
                "vector_shape": [3],
            }
        )
    if array is None:
        array = np.arange(len(rows) * 3, dtype=np.float32).reshape(len(rows), 3)
    chunk_path = (tmp_path / "fixture.npy").resolve()
    np.save(chunk_path, array, allow_pickle=False)
    chunk_payload = chunk_path.read_bytes()
    chunk = {
        "byte_size": len(chunk_payload),
        "chunk_id": chunk_id,
        "dtype": "float32",
        "first_scientific_key": _scientific_key(rows[0]),
        "hidden_width": 3,
        "last_scientific_key": _scientific_key(rows[-1]),
        "layer_idx": 0,
        "path": f"chunks/{chunk_id}.npy",
        "row_count": len(rows),
        "sha256": hashlib.sha256(chunk_payload).hexdigest(),
    }
    identity = {
        "chunks": [chunk],
        "creation_timestamp": "2026-07-31T00:00:00+00:00",
        "format_version": ACTIVATION_INDEX_V2_FORMAT_VERSION,
        "index_rows": rows,
        "run_status": "completed",
        "schema_version": "1.0",
        "store_identity": store,
    }
    document = {
        **identity,
        "snapshot_id": hashlib.sha256(
            person_a_activation_index_v2_canonical_json_bytes(identity)
        ).hexdigest(),
    }
    index_payload = person_a_activation_index_v2_canonical_json_bytes(document)
    index_path = tmp_path / "index.json"
    index_path.write_bytes(index_payload)
    binding = ExternalChunkBinding(
        chunk_id=chunk_id,
        path=chunk_path,
        sha256=chunk["sha256"],
        byte_size=chunk["byte_size"],
        row_count=chunk["row_count"],
    )
    return (
        index_path,
        manifest,
        len(index_payload),
        document,
        binding,
    )


def _load_fixture(tmp_path: Path, **options) -> LoadedActivationIndexV2:
    index_path, manifest, byte_size, _document, binding = _write_index_fixture(
        tmp_path, **options
    )
    return load_activation_index_v2(
        index_path,
        canonicalization_contract=(
            PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
        ),
        expected_index_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
        expected_index_byte_size=byte_size,
        expected_trajectory_id=options.get("trajectory_id", "layout_00_ep9441"),
        expected_manifest_sha256=manifest,
        chunk_bindings={binding.chunk_id: binding},
        retain_vectors=True,
    )


def _validate_fixture_index_bytes(
    index_path: Path,
    manifest: str,
    *,
    canonicalization_contract: str = (
        PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
    ),
) -> object:
    payload = index_path.read_bytes()
    return validate_activation_index_v2_bytes(
        payload,
        canonicalization_contract=canonicalization_contract,
        expected_index_sha256=hashlib.sha256(payload).hexdigest(),
        expected_index_byte_size=len(payload),
        expected_trajectory_id="layout_00_ep9441",
        expected_manifest_sha256=manifest,
    )


def test_v1_dispatch_is_exactly_the_historical_validator() -> None:
    document = json.loads(
        (
            REPO_ROOT / "tests/fixtures/activation/accepted_activation_handoff.json"
        ).read_text(encoding="utf-8")
    )
    historical = validate_activation_handoff(document)
    dispatched = dispatch_activation_document(document)
    assert dispatched.format_version == "person-b-historical-activation-handoff-v1"
    assert dispatched.accepted is historical.accepted
    assert dispatched.rejection_codes == tuple(
        rejection.code.value for rejection in historical.rejections
    )


def test_v2_dispatch_is_explicit_and_rollover_is_collision_free(tmp_path: Path) -> None:
    index_path, manifest, _byte_size, document, _binding = _write_index_fixture(
        tmp_path
    )
    result = dispatch_activation_document(
        document,
        canonicalization_contract=(
            PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
        ),
        expected_trajectory_id="layout_00_ep9441",
        expected_manifest_sha256=manifest,
    )
    assert result.accepted
    assert result.format_version == ACTIVATION_INDEX_V2_FORMAT_VERSION
    loaded = _load_fixture(tmp_path / "loaded")
    identities = {
        (
            row["global_model_frame_idx"],
            row["context_local_pair_idx"],
            row["layer_idx"],
        )
        for row in loaded.rows
    }
    assert identities == {(15, 15, 0), (16, 0, 0)}
    assert index_path.is_file()


def test_v2_dispatch_rejects_missing_or_registry_canonicalization(
    tmp_path: Path,
) -> None:
    _index_path, manifest, _byte_size, document, _binding = _write_index_fixture(
        tmp_path
    )
    with pytest.raises(ActivationV2ConsumerError, match="requires canonicalization"):
        dispatch_activation_document(
            document,
            expected_trajectory_id="layout_00_ep9441",
            expected_manifest_sha256=manifest,
        )
    result = dispatch_activation_document(
        document,
        canonicalization_contract=REGISTRY_V2_CANONICALIZATION_CONTRACT,
        expected_trajectory_id="layout_00_ep9441",
        expected_manifest_sha256=manifest,
    )
    assert result.accepted is False
    assert result.rejection_codes == ("canonicalization_contract_mismatch",)


def test_canonicalization_dispatch_is_owner_and_schema_specific(tmp_path: Path) -> None:
    index_path, manifest, _byte_size, document, _binding = _write_index_fixture(
        tmp_path
    )
    producer_bytes = canonical_json_bytes_for_artifact(
        document,
        artifact_type=PERSON_A_ACTIVATION_INDEX_V2_ARTIFACT_TYPE,
        canonicalization_contract=(
            PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
        ),
    )
    registry_bytes = canonical_json_bytes_for_artifact(
        document,
        artifact_type=REGISTRY_V2_RECORD_ARTIFACT_TYPE,
        canonicalization_contract=REGISTRY_V2_CANONICALIZATION_CONTRACT,
    )
    assert producer_bytes == index_path.read_bytes()
    assert registry_bytes == registry_v2_canonical_json_bytes(document)
    assert producer_bytes != registry_bytes
    assert (
        person_a_activation_index_v2_snapshot_digest(
            document,
            canonicalization_contract=(
                PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
            ),
        )
        == document["snapshot_id"]
    )
    assert (
        hashlib.sha256(
            registry_v2_canonical_json_bytes(
                {key: value for key, value in document.items() if key != "snapshot_id"}
            )
        ).hexdigest()
        != document["snapshot_id"]
    )
    _validate_fixture_index_bytes(index_path, manifest)


@pytest.mark.parametrize(
    "artifact_type,contract",
    [
        (
            PERSON_A_ACTIVATION_INDEX_V2_ARTIFACT_TYPE,
            REGISTRY_V2_CANONICALIZATION_CONTRACT,
        ),
        (PERSON_A_ACTIVATION_INDEX_V2_ARTIFACT_TYPE, "unknown-contract"),
        ("unknown-artifact", PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT),
    ],
)
def test_wrong_or_unknown_canonicalization_dispatch_fails_closed(
    tmp_path: Path,
    artifact_type: str,
    contract: str,
) -> None:
    _index_path, _manifest, _byte_size, document, _binding = _write_index_fixture(
        tmp_path
    )
    with pytest.raises(ActivationV2ConsumerError, match="canonicalization"):
        canonical_json_bytes_for_artifact(
            document,
            artifact_type=artifact_type,
            canonicalization_contract=contract,
        )


def test_person_a_index_byte_mutations_fail_without_rewriting(tmp_path: Path) -> None:
    index_path, manifest, _byte_size, document, _binding = _write_index_fixture(
        tmp_path
    )
    original = index_path.read_bytes()
    validated = _validate_fixture_index_bytes(index_path, manifest)
    assert index_path.read_bytes() == original
    assert validated.raw_sha256 == hashlib.sha256(original).hexdigest()

    whitespace = original.replace(b"{\n", b"{ \n", 1)
    index_path.write_bytes(whitespace)
    with pytest.raises(ActivationV2ConsumerError, match="noncanonical_index"):
        _validate_fixture_index_bytes(index_path, manifest)

    reordered = (
        json.dumps(document, allow_nan=False, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    assert reordered != original
    index_path.write_bytes(reordered)
    with pytest.raises(ActivationV2ConsumerError, match="noncanonical_index"):
        _validate_fixture_index_bytes(index_path, manifest)

    changed_value = copy.deepcopy(document)
    changed_value["creation_timestamp"] = "2026-07-31T00:00:01+00:00"
    changed_value_bytes = person_a_activation_index_v2_canonical_json_bytes(
        changed_value
    )
    index_path.write_bytes(changed_value_bytes)
    with pytest.raises(ActivationV2ConsumerError, match="snapshot_identity_mismatch"):
        _validate_fixture_index_bytes(index_path, manifest)

    changed_snapshot = copy.deepcopy(document)
    changed_snapshot["snapshot_id"] = "0" * 64
    changed_snapshot_bytes = person_a_activation_index_v2_canonical_json_bytes(
        changed_snapshot
    )
    index_path.write_bytes(changed_snapshot_bytes)
    with pytest.raises(ActivationV2ConsumerError, match="snapshot_identity_mismatch"):
        _validate_fixture_index_bytes(index_path, manifest)

    index_path.write_bytes(original)
    with pytest.raises(ActivationV2ConsumerError, match="producer contract"):
        _validate_fixture_index_bytes(
            index_path,
            manifest,
            canonicalization_contract=REGISTRY_V2_CANONICALIZATION_CONTRACT,
        )
    assert index_path.read_bytes() == original


def test_context_local_identity_remains_bounded(tmp_path: Path) -> None:
    index_path, manifest, _byte_size, document, binding = _write_index_fixture(tmp_path)
    document["index_rows"][1]["context_local_pair_idx"] = 16
    identity = dict(document)
    identity.pop("snapshot_id")
    document["snapshot_id"] = hashlib.sha256(
        person_a_activation_index_v2_canonical_json_bytes(identity)
    ).hexdigest()
    payload = person_a_activation_index_v2_canonical_json_bytes(document)
    index_path.write_bytes(payload)
    with pytest.raises(ActivationV2ConsumerError, match="context_local_pair_idx"):
        load_activation_index_v2(
            index_path,
            canonicalization_contract=(
                PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
            ),
            expected_index_sha256=hashlib.sha256(payload).hexdigest(),
            expected_index_byte_size=len(payload),
            expected_trajectory_id="layout_00_ep9441",
            expected_manifest_sha256=manifest,
            chunk_bindings={binding.chunk_id: binding},
            retain_vectors=True,
        )


def test_npy_hash_and_size_are_verified_before_loading(tmp_path: Path) -> None:
    index_path, manifest, byte_size, _document, binding = _write_index_fixture(tmp_path)
    with pytest.raises(ActivationV2ConsumerError, match="SHA-256"):
        load_activation_index_v2(
            index_path,
            canonicalization_contract=(
                PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
            ),
            expected_index_sha256="0" * 64,
            expected_index_byte_size=byte_size,
            expected_trajectory_id="layout_00_ep9441",
            expected_manifest_sha256=manifest,
            chunk_bindings={binding.chunk_id: binding},
            retain_vectors=True,
        )
    with pytest.raises(ActivationV2ConsumerError, match="byte size"):
        load_activation_index_v2(
            index_path,
            canonicalization_contract=(
                PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
            ),
            expected_index_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
            expected_index_byte_size=byte_size + 1,
            expected_trajectory_id="layout_00_ep9441",
            expected_manifest_sha256=manifest,
            chunk_bindings={binding.chunk_id: binding},
            retain_vectors=True,
        )
    bad = copy.copy(binding)
    object.__setattr__(bad, "sha256", "0" * 64)
    with pytest.raises(ActivationV2ConsumerError, match="differs from inventory"):
        load_activation_index_v2(
            index_path,
            canonicalization_contract=(
                PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
            ),
            expected_index_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
            expected_index_byte_size=byte_size,
            expected_trajectory_id="layout_00_ep9441",
            expected_manifest_sha256=manifest,
            chunk_bindings={bad.chunk_id: bad},
            retain_vectors=True,
        )


def test_numpy_loader_forbids_pickle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index_path, manifest, byte_size, _document, binding = _write_index_fixture(tmp_path)
    observed: list[bool] = []
    original = np.load

    def guarded_load(*args, **kwargs):
        observed.append(kwargs.get("allow_pickle"))
        return original(*args, **kwargs)

    monkeypatch.setattr(np, "load", guarded_load)
    load_activation_index_v2(
        index_path,
        canonicalization_contract=(
            PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
        ),
        expected_index_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
        expected_index_byte_size=byte_size,
        expected_trajectory_id="layout_00_ep9441",
        expected_manifest_sha256=manifest,
        chunk_bindings={binding.chunk_id: binding},
        retain_vectors=True,
    )
    assert observed == [False]


def test_literal_capture_and_canonical_state_hashes_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory_id = "fixture-control"
    frame_rows = [
        {
            "trajectory_id": trajectory_id,
            "model_frame_idx": index,
            "render_frame_idx": index,
            "server_tick": index,
        }
        for index in range(2)
    ]
    state_rows = [
        {
            **row,
            "state": {"wall_parallel_position_blocks": float(index)},
        }
        for index, row in enumerate(frame_rows)
    ]
    package = {
        "artifacts": {
            "frame_map": {"sha256": HASH("frame-map")},
            "server_state": {"sha256": HASH("state")},
        },
        "condition": "no_wall_visible",
        "streams": {"frame_map": frame_rows, "server_state": state_rows},
        "trajectory_id": trajectory_id,
    }
    payload = json.dumps(package, indent=2).encode("utf-8")
    literal_hash = hashlib.sha256(payload).hexdigest()
    episode_manifest_hash = HASH("episode-manifest")

    def fake_v1_adapter(*_args, **_kwargs):
        return {
            "accepted_manifest_hash": episode_manifest_hash,
            "rows": [
                {
                    "accepted_manifest_hash": episode_manifest_hash,
                    "layout_id": "layout_fixture",
                    "model_frame_idx": index,
                    "trajectory_id": trajectory_id,
                }
                for index in range(2)
            ],
        }

    monkeypatch.setattr(
        coordinates_v2,
        "build_state_input_from_capture_package",
        fake_v1_adapter,
    )
    result = coordinates_v2.build_state_input_v2_from_capture_bytes(
        payload,
        expected_literal_capture_package_sha256=literal_hash,
        coordinate_frame={},
        model_hash=HASH("model"),
        preprocess_hash=HASH("preprocess"),
        source_row_artifact_type=(
            coordinates_v2.PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE
        ),
        source_row_producer_commit=(
            coordinates_v2.PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT
        ),
        source_row_canonicalization_contract=(
            coordinates_v2.PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT
        ),
        source_row_digest_domain=(
            coordinates_v2.PERSON_A_ACTIVATION_SOURCE_ROW_V2_DIGEST_DOMAIN
        ),
    )
    assert result["literal_capture_package_sha256"] == literal_hash
    assert (
        result["canonical_state_object_sha256"]
        == hashlib.sha256(registry_v2_canonical_json_bytes(package)).hexdigest()
    )
    assert result["canonical_episode_manifest_sha256"] == episode_manifest_hash
    assert (
        result["literal_capture_package_sha256"]
        != result["canonical_state_object_sha256"]
    )


@pytest.mark.parametrize(
    ("array", "message"),
    [
        (np.ones((2, 3), dtype=np.float64), "float32"),
        (
            np.array([[1.0, np.nan, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32),
            "non-finite",
        ),
        (np.ones((2, 4), dtype=np.float32), "shape"),
    ],
)
def test_npy_dtype_finite_and_shape_checks(
    tmp_path: Path, array: np.ndarray, message: str
) -> None:
    with pytest.raises(ActivationV2ConsumerError, match=message):
        _load_fixture(tmp_path, array=array)


def _authority_fixture() -> tuple[dict, dict, dict, dict, dict]:
    manifests = {pilot: HASH(f"accepted:{pilot}") for pilot in ALL_PILOT_IDS}
    inventories = {}
    for pilot in ALL_PILOT_IDS:
        chunks = [
            {
                "byte_size": 128,
                "chunk_id": f"{pilot}-chunk-{layer}",
                "path": f"/approved/{pilot}/chunk-{layer}.npy",
                "row_count": max(1, ACTIVATION_COUNTS[pilot] // 20),
                "sha256": HASH(f"chunk:{pilot}:{layer}"),
            }
            for layer in range(20)
        ]
        inventories[pilot] = {
            "activation_index": {
                "byte_size": 1024,
                "path": f"/approved/{pilot}/index.json",
                "sha256": HASH(f"index:{pilot}"),
            },
            "activation_row_count": ACTIVATION_COUNTS[pilot],
            "chunks": chunks,
            "expected_activation_row_count": ACTIVATION_COUNTS[pilot],
            "status": (
                "REUSED_EXACT_EXISTING_ARTIFACTS"
                if pilot == "layout_00_ep9403"
                else "PASS"
            ),
            "trajectory_id": pilot,
        }
    completion = {
        "accepted_pilot_count": 10,
        "actual_activation_row_count": EXPECTED_TOTAL_ACTIVATION_ROWS,
        "expected_activation_row_count": EXPECTED_TOTAL_ACTIVATION_ROWS,
        "hidden_state_interpretation_authorized": False,
        "no_wall_control_count": 5,
        "no_wall_control_pilots": list(VISIBLE_CONTROL_PILOT_IDS),
        "ordered_pilot_ids": list(ALL_PILOT_IDS),
        "person_b_expansion_authorization_object": (
            f"{PERSON_B_AUTHORIZATION_COMMIT}:docs/status/"
            "person_b_phase6_ten_pilot_expansion_authorization_v0_1/"
            "expansion_execution_authorization.json"
        ),
        "person_b_expansion_selection_commit": PERSON_B_SELECTION_COMMIT,
        "person_c_expansion_acceptance_commit": PERSON_C_ACCEPTANCE_COMMIT,
        "status": "PASS",
        "step6_6_complete": False,
        "u4_output_inspected": False,
    }
    artifact_manifest = {
        "activation_chunk_count": 200,
        "activation_chunks_staged": False,
        "per_pilot_inventory_count": 10,
    }
    controls = []
    for pilot in VISIBLE_CONTROL_PILOT_IDS:
        layout = pilot[:9]
        inventory = inventories[pilot]
        controls.append(
            {
                "activation_index": inventory["activation_index"],
                "activation_row_count": inventory["activation_row_count"],
                "chunks": inventory["chunks"],
                "condition_role": "no_wall_visible_control",
                "control": True,
                "expected_activation_row_count": inventory[
                    "expected_activation_row_count"
                ],
                "fold_idx": FROZEN_LAYOUT_FOLDS[layout],
                "frame_count": 200,
                "layout_id": layout,
                "status": "PASS",
                "trajectory_id": pilot,
            }
        )
    handoff = {
        "no_wall_control_inputs": controls,
        "person_b_step_6_6_control_execution_complete": False,
    }
    c_rows = []
    for pilot in ALL_PILOT_IDS:
        layout = pilot[:9]
        c_rows.append(
            {
                "capture_package_path": f"data/autonomous/{pilot}/capture_package_v0_1.json",
                "capture_package_sha256": manifests[pilot],
                "fold_idx": FROZEN_LAYOUT_FOLDS[layout],
                "layout_id": layout,
                "trajectory_id": pilot,
            }
        )
    c_acceptance = {"accepted_pilot_count": 10, "intake_rows": c_rows}
    return completion, artifact_manifest, handoff, inventories, c_acceptance


def test_ten_indices_200_chunks_and_distinct_manifests_are_bound() -> None:
    completion, artifact_manifest, handoff, inventories, c_acceptance = (
        _authority_fixture()
    )
    authority = validate_ten_pilot_authority_documents(
        completion_report=completion,
        artifact_manifest=artifact_manifest,
        positive_control_handoff=handoff,
        per_pilot_inventories=inventories,
        c_accepted_manifest=c_acceptance,
    )
    assert len(inventories) == 10
    assert sum(len(value["chunks"]) for value in inventories.values()) == 200
    assert len(set(authority.accepted_c_manifest_by_trajectory.values())) == 10


def _loaded_bridge_fixture() -> tuple[dict, dict, object, dict]:
    completion, artifact_manifest, handoff, inventories, c_acceptance = (
        _authority_fixture()
    )
    authority = validate_ten_pilot_authority_documents(
        completion_report=completion,
        artifact_manifest=artifact_manifest,
        positive_control_handoff=handoff,
        per_pilot_inventories=inventories,
        c_accepted_manifest=c_acceptance,
    )
    indices = {}
    states = {}
    for pilot in ALL_PILOT_IDS:
        manifest = authority.accepted_c_manifest_by_trajectory[pilot]
        store_identity = {
            "accepted_manifest_hash": manifest,
            "checkpoint_hash": HASH("checkpoint"),
            "config_hash": HASH("config"),
            "model_hash": HASH("model"),
            "preprocess_hash": HASH("preprocess"),
        }
        chunks = tuple(
            {
                "byte_size": 928,
                "chunk_id": f"{pilot}-chunk-{layer}",
                "row_count": 200,
                "sha256": HASH(f"chunk:{pilot}:{layer}"),
            }
            for layer in range(20)
        )
        if pilot in VISIBLE_CONTROL_PILOT_IDS:
            rows = []
            arrays = {}
            for layer in range(20):
                chunk_id = f"{pilot}-chunk-{layer}"
                arrays[chunk_id] = np.arange(200, dtype=np.float32).reshape(200, 1)
                arrays[chunk_id].setflags(write=False)
                for global_idx in range(200):
                    rows.append(
                        {
                            "activation_chunk_id": chunk_id,
                            "accepted_manifest_hash": manifest,
                            "c_frame_map_row_sha256": HASH(
                                f"frame-row:{pilot}:{global_idx}"
                            ),
                            "c_frame_map_sha256": HASH(f"frame-map:{pilot}"),
                            "c_state_row_sha256": HASH(
                                f"state-row:{pilot}:{global_idx}"
                            ),
                            "c_state_sha256": HASH(f"state:{pilot}"),
                            "chunk_row_idx": global_idx,
                            "context_local_pair_idx": global_idx % 16,
                            "frame_token_map_sha256": HASH(
                                f"token-map:{pilot}:{global_idx}"
                            ),
                            "global_model_frame_idx": global_idx,
                            "hook_site": "decoder_block_output",
                            "layer_idx": layer,
                            "run_id": f"run:{pilot}",
                            "source_frame_id": f"{pilot}:render_frame:{global_idx}",
                            "source_frame_idx": global_idx,
                            "source_tick": global_idx,
                            "trajectory_id": pilot,
                        }
                    )
            literal = manifest
            canonical = HASH(f"canonical:{pilot}")
            layout = pilot[:9]
            states[pilot] = {
                "accepted_c_manifest_sha256": manifest,
                "canonical_state_object_sha256": canonical,
                "condition": "no_wall_visible",
                "literal_capture_package_sha256": literal,
                "rows": [
                    {
                        "accepted_c_manifest_sha256": manifest,
                        "c_frame_map_row_sha256": HASH(f"frame-row:{pilot}:{idx}"),
                        "c_frame_map_sha256": HASH(f"frame-map:{pilot}"),
                        "c_state_row_sha256": HASH(f"state-row:{pilot}:{idx}"),
                        "c_state_sha256": HASH(f"state:{pilot}"),
                        "canonical_state_object_sha256": canonical,
                        "global_model_frame_idx": idx,
                        "layout_id": layout,
                        "literal_capture_package_sha256": literal,
                        "source_frame_id": f"{pilot}:render_frame:{idx}",
                        "source_frame_idx": idx,
                        "source_tick": idx,
                        "trajectory_id": pilot,
                        "visibility": "visible",
                        "x_true_blocks": float(idx),
                    }
                    for idx in range(200)
                ],
                "trajectory_id": pilot,
            }
        else:
            rows = tuple({} for _ in range(ACTIVATION_COUNTS[pilot]))
            arrays = {}
        indices[pilot] = LoadedActivationIndexV2(
            trajectory_id=pilot,
            index_path=Path(f"/{pilot}/index.json"),
            index_sha256=HASH(f"index:{pilot}"),
            index_byte_size=1024,
            store_identity=store_identity,
            rows=tuple(rows),
            chunks=chunks,
            arrays_by_chunk_id=arrays,
        )
    fold_plan = {
        "layout_assignments": [
            {"fold_idx": fold, "layout_id": layout}
            for layout, fold in FROZEN_LAYOUT_FOLDS.items()
        ],
        "n_splits": 5,
        "outcome_fields_used": False,
        "scope_fold_coverage": [
            {"accepted_row_count": 1000, "scope": "visible_no_wall_control"}
        ],
        "status": "frozen_before_person_a_join",
        "strategy": "layout_grouped",
    }
    return indices, states, authority, fold_plan


@pytest.fixture(scope="module")
def prepared_bridge():
    indices, states, authority, fold_plan = _loaded_bridge_fixture()
    return build_positive_control_bridge_v2(
        indices,
        states,
        authority=authority,
        fold_plan=fold_plan,
    )


def test_bridge_preserves_exact_control_contract_without_probe_execution(
    prepared_bridge,
) -> None:
    assert prepared_bridge.row_count == 1000
    assert prepared_bridge.layout_count == 5
    assert prepared_bridge.target_name == FROZEN_TARGET_NAME
    assert prepared_bridge.threshold_policy == FROZEN_THRESHOLD_POLICY
    assert prepared_bridge.scientific_execution_performed is False
    assert len(prepared_bridge.matrices) == 20
    assert {len(matrix.targets) for matrix in prepared_bridge.matrices} == {1000}
    assert {frozenset(matrix.outer_folds) for matrix in prepared_bridge.matrices} == {
        frozenset({0, 1, 2, 3, 4})
    }
    manifests = {
        row["accepted_c_manifest_sha256"]
        for row in prepared_bridge.matrices[0].metadata_rows
    }
    assert len(manifests) == 5
    assert all(
        row["literal_capture_package_sha256"] != row["canonical_state_object_sha256"]
        for row in prepared_bridge.matrices[0].metadata_rows
    )


def test_hidden_rows_and_core_visible_substitution_fail_closed() -> None:
    _indices, states, authority, _fold_plan = _loaded_bridge_fixture()
    state = copy.deepcopy(states[VISIBLE_CONTROL_PILOT_IDS[0]])
    state["rows"][0]["visibility"] = "occluded"
    with pytest.raises(control_v2.PositiveControlV2Error, match="visibility"):
        control_v2._state_rows_by_frame(
            state,
            trajectory_id=VISIBLE_CONTROL_PILOT_IDS[0],
            expected_manifest_sha256=authority.accepted_c_manifest_by_trajectory[
                VISIBLE_CONTROL_PILOT_IDS[0]
            ],
        )
    state = copy.deepcopy(states[VISIBLE_CONTROL_PILOT_IDS[0]])
    state["condition"] = "core"
    with pytest.raises(control_v2.PositiveControlV2Error, match="Core-visible"):
        control_v2._state_rows_by_frame(
            state,
            trajectory_id=VISIBLE_CONTROL_PILOT_IDS[0],
            expected_manifest_sha256=authority.accepted_c_manifest_by_trajectory[
                VISIBLE_CONTROL_PILOT_IDS[0]
            ],
        )


def test_changed_person_a_source_digest_fails_exact_join() -> None:
    indices, states, authority, fold_plan = _loaded_bridge_fixture()
    trajectory_id = VISIBLE_CONTROL_PILOT_IDS[0]
    states[trajectory_id]["rows"][0]["c_frame_map_row_sha256"] = HASH(
        "substituted-source-row-digest"
    )
    with pytest.raises(
        control_v2.PositiveControlV2Error,
        match="c_frame_map_row_sha256",
    ):
        build_positive_control_bridge_v2(
            indices,
            states,
            authority=authority,
            fold_plan=fold_plan,
        )


def test_random_split_and_changed_folds_fail_closed() -> None:
    _indices, _states, _authority, fold_plan = _loaded_bridge_fixture()
    random_plan = copy.deepcopy(fold_plan)
    random_plan["strategy"] = "random"
    with pytest.raises(control_v2.PositiveControlV2Error, match="grouped"):
        control_v2._validate_fold_plan(random_plan)
    changed = copy.deepcopy(fold_plan)
    changed["layout_assignments"][0]["fold_idx"] = 0
    with pytest.raises(control_v2.PositiveControlV2Error, match="assignments"):
        control_v2._validate_fold_plan(changed)


def test_cross_trajectory_manifest_substitution_fails_closed() -> None:
    indices, _states, authority, _fold_plan = _loaded_bridge_fixture()
    first, second = ALL_PILOT_IDS[:2]
    stale = copy.copy(indices[first])
    substituted_identity = dict(stale.store_identity)
    substituted_identity["accepted_manifest_hash"] = (
        authority.accepted_c_manifest_by_trajectory[second]
    )
    object.__setattr__(
        stale,
        "store_identity",
        substituted_identity,
    )
    indices[first] = stale
    with pytest.raises(control_v2.PositiveControlV2Error, match="another trajectory"):
        control_v2.validate_loaded_ten_pilot_indices(indices, authority=authority)
