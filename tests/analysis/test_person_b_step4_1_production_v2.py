"""Focused tests for the sealed Person B Step 4.1 production inputs."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path

import pytest

from mineocclude.analysis.coordinates_v2 import (
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE,
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT,
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_DIGEST_DOMAIN,
    PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
    build_state_input_v2_from_capture_bytes,
)
from mineocclude.analysis.manifests import seal_artifact
from mineocclude.analysis.positive_control_v2 import (
    ALL_PILOT_IDS,
    CORE_PILOT_IDS,
    EXPECTED_ACTIVATION_CHUNK_COUNT,
    EXPECTED_TOTAL_ACTIVATION_ROWS,
    FROZEN_LAYOUT_FOLDS,
    PERSON_A_TEN_PILOT_COMMIT,
    PERSON_C_ACCEPTANCE_COMMIT,
    VISIBLE_CONTROL_PILOT_IDS,
    validate_ten_pilot_authority_documents,
)
from mineocclude.analysis.production_v2 import (
    COMBINED_ACTIVATION_INDEX_FORMAT_VERSION,
    EXPECTED_ADMITTED_FRAME_COUNT,
    EXPECTED_EXCLUDED_FRAME_COUNT,
    EXPECTED_HIDDEN_PRODUCTION_ROWS,
    EXPECTED_SOURCE_FRAME_COUNT,
    EXPECTED_VISIBLE_CONTROL_ROWS,
    FROZEN_PRODUCTION_TARGETS,
    PRODUCTION_INPUT_FORMAT_VERSION,
    ProductionV2Error,
    build_production_oracle_target_document,
    build_ten_pilot_frame_fold_manifest,
    validate_combined_activation_index_bytes,
    validate_production_activation_store_v2,
)
from mineocclude.contracts.activation_v2 import (
    person_a_activation_index_v2_canonical_json_bytes,
)
from mineocclude.oracle.schema import (
    OracleValidationError,
    validate_oracle_target_document,
)
from mineocclude.probes.splits import GroupedSplitError, validate_fold_manifest
from scripts.prepare_person_b_step4_1_production_inputs import (
    A_RUNTIME_ROOT,
    C_ACCEPTANCE_PATH,
    _git_blob_by_suffix,
    _git_bytes,
    _git_json,
    _source_model_identity,
)

REPOSITORY = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPOSITORY / "configs/analysis/core.yaml"
CONDITION_SELECTION_PATH = (
    REPOSITORY / "data/person_b/phase6_c_intake/condition_selection_source.json"
)
FOLD_PLAN_PATH = REPOSITORY / "data/person_b/phase6_c_intake/layout_fold_plan.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_file(path: Path) -> tuple[Mapping[str, object], str]:
    payload = path.read_bytes()
    document = json.loads(payload.decode("utf-8"))
    assert isinstance(document, Mapping)
    return document, _sha256(payload)


@pytest.fixture(scope="module")
def production_documents() -> tuple[dict, dict, dict[str, Mapping[str, object]]]:
    completion = _git_json(
        REPOSITORY,
        PERSON_A_TEN_PILOT_COMMIT,
        f"{A_RUNTIME_ROOT}/completion_report.json",
    )
    artifact_manifest = _git_json(
        REPOSITORY,
        PERSON_A_TEN_PILOT_COMMIT,
        f"{A_RUNTIME_ROOT}/artifact_manifest.json",
    )
    handoff = _git_json(
        REPOSITORY,
        PERSON_A_TEN_PILOT_COMMIT,
        f"{A_RUNTIME_ROOT}/person_b_step6_6_positive_control_handoff.json",
    )
    inventories = {
        trajectory_id: _git_json(
            REPOSITORY,
            PERSON_A_TEN_PILOT_COMMIT,
            f"{A_RUNTIME_ROOT}/per_pilot_inventories/{trajectory_id}.json",
        )
        for trajectory_id in ALL_PILOT_IDS
    }
    c_payload = _git_bytes(
        REPOSITORY,
        PERSON_C_ACCEPTANCE_COMMIT,
        C_ACCEPTANCE_PATH,
    )
    c_manifest = json.loads(c_payload.decode("utf-8"))
    authority = validate_ten_pilot_authority_documents(
        completion_report=completion,
        artifact_manifest=artifact_manifest,
        positive_control_handoff=handoff,
        per_pilot_inventories=inventories,
        c_accepted_manifest=c_manifest,
    )
    selection, selection_hash = _json_file(CONDITION_SELECTION_PATH)
    fold_plan, fold_plan_hash = _json_file(FOLD_PLAN_PATH)
    fold = build_ten_pilot_frame_fold_manifest(
        condition_selection=selection,
        frozen_layout_plan=fold_plan,
        c_accepted_manifest=c_manifest,
        per_pilot_inventories=inventories,
        authority=authority,
        code_sha="a" * 40,
        condition_selection_sha256=selection_hash,
        condition_selection_byte_size=CONDITION_SELECTION_PATH.stat().st_size,
        frozen_layout_plan_sha256=fold_plan_hash,
        frozen_layout_plan_byte_size=FOLD_PLAN_PATH.stat().st_size,
        c_accepted_manifest_sha256=_sha256(c_payload),
        c_accepted_manifest_byte_size=len(c_payload),
    )
    model_hash, preprocess_hash, _ = _source_model_identity(REPOSITORY)
    c_by_id = {row["trajectory_id"]: row for row in c_manifest["intake_rows"]}
    states: dict[str, Mapping[str, object]] = {}
    for trajectory_id in ALL_PILOT_IDS:
        c_row = c_by_id[trajectory_id]
        capture_bytes = _git_bytes(
            REPOSITORY,
            PERSON_C_ACCEPTANCE_COMMIT,
            c_row["capture_package_path"],
        )
        coordinate = json.loads(
            (
                REPOSITORY
                / "data/person_b/phase6_c_intake/coordinate_frames"
                / f"{trajectory_id}.json"
            ).read_text(encoding="utf-8")
        )
        states[trajectory_id] = build_state_input_v2_from_capture_bytes(
            capture_bytes,
            expected_literal_capture_package_sha256=c_row[
                "capture_package_sha256"
            ],
            coordinate_frame=coordinate,
            model_hash=model_hash,
            preprocess_hash=preprocess_hash,
            source_row_artifact_type=(
                PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE
            ),
            source_row_producer_commit=PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
            source_row_canonicalization_contract=(
                PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT
            ),
            source_row_digest_domain=(
                PERSON_A_ACTIVATION_SOURCE_ROW_V2_DIGEST_DOMAIN
            ),
        )
    target = build_production_oracle_target_document(
        states,
        fold_manifest=fold,
        code_sha="a" * 40,
        oracle_run_id="focused_step4_1_test",
        analysis_config_path=CONFIG_PATH,
    )
    return fold, target, inventories


def _combined_fixture() -> tuple[bytes, dict, dict, str]:
    trajectory_id = "layout_fixture_ep0001"
    manifest_hash = _sha256(b"accepted C manifest")
    activation_index = {
        "byte_size": 123,
        "path": "/immutable/index.json",
        "sha256": _sha256(b"index"),
    }
    row = {
        "accepted_manifest_hash": manifest_hash,
        "checkpoint_hash": _sha256(b"checkpoint"),
        "context_local_pair_idx": 0,
        "global_model_frame_idx": 16,
        "hook_site": "decoder_block_output",
        "layer_idx": 0,
        "preprocess_hash": _sha256(b"preprocess"),
        "source_frame_id": f"{trajectory_id}:render_frame:16",
        "source_tick": 16,
        "trajectory_id": trajectory_id,
    }
    inventory = {
        "activation_index": activation_index,
        "activation_row_count": 1,
    }
    document = {
        "activation_index_format_version": COMBINED_ACTIVATION_INDEX_FORMAT_VERSION,
        "activation_store_format_version": "person-a-activation-store-v2",
        "combined_activation_row_count": 1,
        "index_rows": [row],
        "no_wall_control_pilot_ids": [trajectory_id],
        "ordered_pilot_ids": [trajectory_id],
        "per_pilot_indexes": [
            {
                "activation_index": activation_index,
                "activation_row_count": 1,
                "trajectory_id": trajectory_id,
            }
        ],
        "schema_version": "1.0",
        "scientific_identity_collision_count": 0,
    }
    payload = person_a_activation_index_v2_canonical_json_bytes(document)
    return payload, {trajectory_id: inventory}, {trajectory_id: manifest_hash}, trajectory_id


def test_production_dispatch_accepts_global_frame_beyond_15() -> None:
    payload, inventories, manifests, trajectory_id = _combined_fixture()
    document = validate_combined_activation_index_bytes(
        payload,
        expected_sha256=_sha256(payload),
        expected_byte_size=len(payload),
        per_pilot_inventories=inventories,
        accepted_manifest_by_trajectory=manifests,
        expected_pilot_ids=(trajectory_id,),
        expected_no_wall_ids=(trajectory_id,),
        expected_row_count=1,
    )
    assert document["index_rows"][0]["global_model_frame_idx"] == 16
    assert document["index_rows"][0]["context_local_pair_idx"] == 0
    with pytest.raises(ProductionV2Error, match="authorization"):
        validate_production_activation_store_v2(
            payload,
            production_input_format_version="person-b-positive-control-input-v2",
            expected_sha256=_sha256(payload),
            expected_byte_size=len(payload),
            per_pilot_inventories=inventories,
            accepted_manifest_by_trajectory=manifests,
        )


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda document: document["index_rows"][0].update(context_local_pair_idx=16), "frame/layer"),
        (lambda document: document["index_rows"][0].update(accepted_manifest_hash="f" * 64), "manifest"),
        (lambda document: document.update(scientific_identity_collision_count=1), "producer contract"),
    ],
)
def test_production_dispatch_fails_closed(mutation, message: str) -> None:
    payload, inventories, manifests, trajectory_id = _combined_fixture()
    document = json.loads(payload.decode("utf-8"))
    mutation(document)
    changed = person_a_activation_index_v2_canonical_json_bytes(document)
    with pytest.raises(ProductionV2Error, match=message):
        validate_combined_activation_index_bytes(
            changed,
            expected_sha256=_sha256(changed),
            expected_byte_size=len(changed),
            per_pilot_inventories=inventories,
            accepted_manifest_by_trajectory=manifests,
            expected_pilot_ids=(trajectory_id,),
            expected_no_wall_ids=(trajectory_id,),
            expected_row_count=1,
        )


def test_frame_fold_is_exact_complete_grouped_and_nonrandom(
    production_documents,
) -> None:
    fold, _target, inventories = production_documents
    validate_fold_manifest(fold)
    assert fold["fold_manifest_format_version"].endswith("frame-fold-v0.1")
    assert fold["accepted_pilot_ids"] == list(ALL_PILOT_IDS)
    assert fold["source_frame_count"] == EXPECTED_SOURCE_FRAME_COUNT
    assert fold["admitted_frame_count"] == EXPECTED_ADMITTED_FRAME_COUNT
    assert fold["excluded_frame_count"] == EXPECTED_EXCLUDED_FRAME_COUNT
    assert fold["activation_row_count"] == EXPECTED_TOTAL_ACTIVATION_ROWS
    assert fold["activation_chunk_count"] == EXPECTED_ACTIVATION_CHUNK_COUNT
    assert fold["random_split_used"] is False
    assert sum(item["activation_row_count"] for item in inventories.values()) == 37_480
    assert sum(len(item["chunks"]) for item in inventories.values()) == 200
    admitted = {
        (row["trajectory_id"], row["model_frame_idx"])
        for row in fold["memberships"]
    }
    excluded = {
        (row["trajectory_id"], row["model_frame_idx"])
        for row in fold["excluded_memberships"]
    }
    assert len(admitted) == len(fold["memberships"])
    assert len(excluded) == len(fold["excluded_memberships"])
    assert admitted.isdisjoint(excluded)
    assert len(admitted | excluded) == EXPECTED_SOURCE_FRAME_COUNT
    layouts_by_fold: dict[str, set[int]] = defaultdict(set)
    for row in fold["memberships"]:
        layouts_by_fold[row["layout_id"]].add(row["fold_idx"])
    assert {layout: next(iter(folds)) for layout, folds in layouts_by_fold.items()} == {
        layout: FROZEN_LAYOUT_FOLDS[layout] for layout in sorted(layouts_by_fold)
    }


def test_frame_fold_rejects_leakage_and_random_reassignment(
    production_documents,
) -> None:
    fold, _target, _inventories = production_documents
    leaked = copy.deepcopy(fold)
    leaked.pop("artifact_hash")
    leaked["memberships"][0]["fold_idx"] = (
        leaked["memberships"][0]["fold_idx"] + 1
    ) % 5
    with pytest.raises(GroupedSplitError, match="membership"):
        validate_fold_manifest(seal_artifact(leaked))
    random_split = copy.deepcopy(fold)
    random_split.pop("artifact_hash")
    random_split["random_split_used"] = True
    with pytest.raises(GroupedSplitError, match="split policy"):
        validate_fold_manifest(seal_artifact(random_split))


def test_oracle_target_is_exact_and_bound_by_identity(production_documents) -> None:
    fold, target, _inventories = production_documents
    validate_oracle_target_document(target, analysis_config_path=CONFIG_PATH)
    assert target["input_manifest_hash"] == fold["artifact_hash"]
    assert target["row_count"] == EXPECTED_ADMITTED_FRAME_COUNT
    assert target["eligibility_counts"] == {
        "accepted_hidden_positive_spread_rows": EXPECTED_HIDDEN_PRODUCTION_ROWS,
        "accepted_post_first_seen_rows": EXPECTED_ADMITTED_FRAME_COUNT,
        "visible_no_wall_control_rows": EXPECTED_VISIBLE_CONTROL_ROWS,
    }
    assert target["method"] == "primary_scalar_kalman_crosschecked_closed_form"
    assert FROZEN_PRODUCTION_TARGETS == (
        "mu_oracle_blocks",
        "log_sigma_oracle",
    )
    assert [row["trajectory_id"] for row in target["trajectory_lineage"]] == list(
        ALL_PILOT_IDS
    )
    assert len(
        {row["accepted_c_manifest_sha256"] for row in target["trajectory_lineage"]}
    ) == 10
    assert all(
        row["literal_capture_package_sha256"]
        != row["canonical_state_object_sha256"]
        for row in target["trajectory_lineage"]
    )
    row_by_key = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in target["rows"]
    }
    assert set(row_by_key) == {
        (row["trajectory_id"], row["model_frame_idx"])
        for row in fold["memberships"]
    }
    visibility_counts = Counter(row["visibility"] for row in target["rows"])
    assert visibility_counts == {
        "occluded": EXPECTED_HIDDEN_PRODUCTION_ROWS,
        "visible": EXPECTED_VISIBLE_CONTROL_ROWS,
    }
    hidden = next(row for row in target["rows"] if row["visibility"] == "occluded")
    assert hidden["mu_oracle_blocks"] == pytest.approx(
        hidden["last_visible_position_blocks"] + hidden["v"] * hidden["tau"]
    )
    assert hidden["var_oracle_blocks2"] == pytest.approx(hidden["q"] * hidden["tau"])


def test_oracle_target_rejects_changed_derivation_and_u4(production_documents) -> None:
    _fold, target, _inventories = production_documents
    changed = copy.deepcopy(target)
    changed.pop("artifact_hash")
    changed["rows"][0]["mu_oracle_blocks"] += 1.0
    with pytest.raises(OracleValidationError, match="mean"):
        validate_oracle_target_document(
            seal_artifact(changed),
            analysis_config_path=CONFIG_PATH,
        )
    u4 = copy.deepcopy(target)
    u4.pop("artifact_hash")
    u4["u4_output_inspected"] = True
    with pytest.raises(OracleValidationError, match="U4"):
        validate_oracle_target_document(
            seal_artifact(u4),
            analysis_config_path=CONFIG_PATH,
        )


def test_production_preparation_does_not_fit_or_import_probe_execution() -> None:
    from mineocclude.analysis import production_v2

    assert "fit_ridge_oof" not in vars(production_v2)
    assert PRODUCTION_INPUT_FORMAT_VERSION == "person-b-step4-1-production-input-v0.1"
    assert set(CORE_PILOT_IDS).isdisjoint(VISIBLE_CONTROL_PILOT_IDS)
    assert set(CORE_PILOT_IDS) | set(VISIBLE_CONTROL_PILOT_IDS) == set(ALL_PILOT_IDS)


def test_exact_person_a_source_index_blob_remains_available() -> None:
    suffix = "index-82dc0e18607a1a89135a1a88cbec5d53531682db970e9a1323672e7f4d28677b.json"
    payload = _git_blob_by_suffix(REPOSITORY, PERSON_A_TEN_PILOT_COMMIT, suffix)
    document = json.loads(payload.decode("utf-8"))
    assert document["format_version"] == "person-a-activation-index-v2"
    assert document["store_identity"]["hidden_width"] == 2048
