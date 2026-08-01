from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from mineocclude.analysis.manifests import seal_artifact
from mineocclude.experiments.registry import formatted_json_bytes
from mineocclude.probes.production_fold_contract_v0_1 import (
    FROZEN_ACCEPTED_PILOT_IDS,
    FROZEN_FOLD_MANIFEST_BYTE_SIZE,
    FROZEN_FOLD_MANIFEST_SHA256,
    FROZEN_LAYOUT_FOLDS,
    FROZEN_LAYOUT_IDS,
    FROZEN_LAYOUT_ROW_COUNTS,
    FROZEN_ROW_MAPPING_SHA256,
    FROZEN_SEED,
    PRODUCTION_FOLD_CONTRACT_VERSION,
    ProductionFoldContractError,
    row_mapping_sha256,
    validate_fold_target_binding_bytes,
    validate_production_fold_document,
    validate_production_fold_manifest_bytes,
)
from mineocclude.probes.splits import (
    assign_layout_grouped_folds,
    validate_fold_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
STATUS_ROOT = (
    ROOT
    / "docs"
    / "status"
    / "person_b_phase4_step4_1_production_fold_contract_v0_1"
)
FOLD_PATH = (
    ROOT
    / "docs"
    / "status"
    / "person_b_phase4_step4_1_production_handoff_v0_1"
    / "ten_pilot_frame_fold_manifest.json"
)
TARGET_PATH = FOLD_PATH.with_name("production_oracle_target_manifest.json")
PLAN_PATH = ROOT / "data" / "person_b" / "phase6_c_intake" / "layout_fold_plan.json"


def _load_fold() -> dict:
    return json.loads(FOLD_PATH.read_text(encoding="utf-8"))


def _reseal(document: dict) -> dict:
    document.pop("artifact_hash", None)
    return seal_artifact(document)


def test_exact_real_manifest_and_target_binding_pass() -> None:
    fold_payload = FOLD_PATH.read_bytes()
    target_payload = TARGET_PATH.read_bytes()
    fold, target = validate_fold_target_binding_bytes(
        fold_payload,
        target_payload,
        contract_version=PRODUCTION_FOLD_CONTRACT_VERSION,
    )
    assert len(fold_payload) == FROZEN_FOLD_MANIFEST_BYTE_SIZE
    assert hashlib.sha256(fold_payload).hexdigest() == FROZEN_FOLD_MANIFEST_SHA256
    assert fold_payload == formatted_json_bytes(fold)
    assert len(fold["memberships"]) == 1_695
    assert len(target["rows"]) == 1_695
    assert fold["accepted_pilot_ids"] == list(FROZEN_ACCEPTED_PILOT_IDS)
    assert row_mapping_sha256(fold) == FROZEN_ROW_MAPPING_SHA256


def test_real_manifest_has_unique_complete_nonleaking_rows() -> None:
    fold = _load_fold()
    admitted = {
        (row["trajectory_id"], row["model_frame_idx"])
        for row in fold["memberships"]
    }
    excluded = {
        (row["trajectory_id"], row["model_frame_idx"])
        for row in fold["excluded_memberships"]
    }
    assert len(admitted) == len(fold["memberships"]) == 1_695
    assert len(excluded) == len(fold["excluded_memberships"]) == 179
    assert admitted.isdisjoint(excluded)
    assert len(admitted | excluded) == 1_874
    assert {
        layout_id: {row["fold_idx"] for row in fold["memberships"] if row["layout_id"] == layout_id}
        for layout_id in FROZEN_LAYOUT_IDS
    } == {layout_id: {FROZEN_LAYOUT_FOLDS[layout_id]} for layout_id in FROZEN_LAYOUT_IDS}
    assert {
        layout_id: sum(row["layout_id"] == layout_id for row in fold["memberships"])
        for layout_id in FROZEN_LAYOUT_IDS
    } == FROZEN_LAYOUT_ROW_COUNTS


def test_prejoin_generation_reproduces_original_frozen_plan() -> None:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    rows = [
        {
            "layout_id": evidence["layout_id"],
            "model_frame_idx": frame_idx,
            "status": "accepted",
            "trajectory_id": f"{evidence['layout_id']}_fixture",
        }
        for evidence in plan["layout_evidence"]
        for frame_idx in range(evidence["accepted_row_count"])
    ]
    expected = {row["layout_id"]: row["fold_idx"] for row in plan["layout_assignments"]}
    assert assign_layout_grouped_folds(rows, seed=FROZEN_SEED) == expected
    assert assign_layout_grouped_folds(rows, seed=FROZEN_SEED + 1) == expected


def test_subset_reproduction_is_detected_as_non_authoritative() -> None:
    fold = _load_fold()
    reproduced = assign_layout_grouped_folds(
        fold["memberships"],
        n_splits=5,
        seed=FROZEN_SEED,
    )
    assert [reproduced[layout] for layout in FROZEN_LAYOUT_IDS] == [0, 1, 2, 3, 4]
    assert reproduced != FROZEN_LAYOUT_FOLDS

    incorrectly_rebalanced = copy.deepcopy(fold)
    incorrectly_rebalanced["layout_assignments"] = [
        {"fold_idx": reproduced[layout], "layout_id": layout}
        for layout in FROZEN_LAYOUT_IDS
    ]
    for row in incorrectly_rebalanced["memberships"]:
        row["fold_idx"] = reproduced[row["layout_id"]]
    with pytest.raises(ProductionFoldContractError):
        validate_production_fold_document(
            _reseal(incorrectly_rebalanced),
            contract_version=PRODUCTION_FOLD_CONTRACT_VERSION,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.update(seed=FROZEN_SEED + 1),
        lambda document: document["layout_assignments"][0].update(fold_idx=0),
        lambda document: document["memberships"][0].update(model_frame_idx=0),
    ],
)
def test_changed_seed_mapping_or_row_identity_fails(mutation) -> None:
    fold = _load_fold()
    mutation(fold)
    with pytest.raises(ProductionFoldContractError):
        validate_production_fold_document(
            _reseal(fold),
            contract_version=PRODUCTION_FOLD_CONTRACT_VERSION,
        )


def test_changed_fold_or_target_literal_hash_fails() -> None:
    fold_payload = bytearray(FOLD_PATH.read_bytes())
    fold_payload[-2] = ord(" ")
    with pytest.raises(ProductionFoldContractError):
        validate_production_fold_manifest_bytes(
            bytes(fold_payload),
            contract_version=PRODUCTION_FOLD_CONTRACT_VERSION,
        )

    target_payload = bytearray(TARGET_PATH.read_bytes())
    target_payload[-2] = ord(" ")
    with pytest.raises(ProductionFoldContractError):
        validate_fold_target_binding_bytes(
            FOLD_PATH.read_bytes(),
            bytes(target_payload),
            contract_version=PRODUCTION_FOLD_CONTRACT_VERSION,
        )


def test_unknown_contract_version_fails_closed() -> None:
    with pytest.raises(ProductionFoldContractError, match="Unknown"):
        validate_production_fold_manifest_bytes(
            FOLD_PATH.read_bytes(),
            contract_version="person-b-step4-1-production-fold-contract-v9",
        )


def test_existing_person_b_production_dispatch_still_accepts_real_manifest() -> None:
    validate_fold_manifest(_load_fold())


def test_contract_schema_and_package_are_canonical_and_inventoried() -> None:
    contract_path = STATUS_ROOT / "production_fold_assignment_contract.json"
    schema_path = (
        ROOT
        / "schemas"
        / "analysis"
        / "person_b_step4_1_production_fold_contract_v0_1.schema.json"
    )
    for path in (contract_path, schema_path):
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
        assert raw == formatted_json_bytes(document)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert contract["contract_version"] == PRODUCTION_FOLD_CONTRACT_VERSION
    assert schema["properties"]["contract_version"]["const"] == (
        PRODUCTION_FOLD_CONTRACT_VERSION
    )
    assert contract["authoritative_validation_mode"] == "signed_explicit_mapping"
    assert contract["u4_output_inspected"] is False

    inventory = json.loads(
        (STATUS_ROOT / "sha256_inventory.json").read_text(encoding="utf-8")
    )
    assert inventory["inventory_excludes_self"] is True
    for relative_path, expected in inventory["files"].items():
        payload = (ROOT / relative_path).read_bytes()
        assert len(payload) == expected["byte_size"]
        assert hashlib.sha256(payload).hexdigest() == expected["sha256"]
