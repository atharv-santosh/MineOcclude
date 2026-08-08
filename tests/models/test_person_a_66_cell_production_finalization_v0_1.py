"""Focused CPU-only checks for the completed 66-cell production finalization."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
STATUS = ROOT / "docs/status/person_a_66_cell_production_activation_index_v0_1"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load(
    "person_a_66_cell_production_runner",
    SCRIPTS / "run_person_a_66_cell_production_extraction.py",
)
builder = _load(
    "person_a_66_cell_production_finalizer",
    SCRIPTS / "build_person_a_66_cell_production_activation_index_v0_1.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_runner_preserves_seed_and_routes_runtime_state_outside_git() -> None:
    assert _sha256(runner.SEED_QUEUE_STATE_PATH) == runner.SEED_QUEUE_STATE_SHA256
    assert runner.RUNTIME_QUEUE_STATE_PATH == runner.QUEUE_STATE_PATH
    assert runner.RUNTIME_QUEUE_STATE_PATH != runner.SEED_QUEUE_STATE_PATH
    assert not runner.RUNTIME_QUEUE_STATE_PATH.is_relative_to(ROOT)
    seed = json.loads(runner.SEED_QUEUE_STATE_PATH.read_bytes())
    assert {item["state"] for item in seed["items"]} == {"pending"}
    assert len(seed["items"]) == 66


def test_completed_runtime_queue_is_preserved_and_bound_to_seed() -> None:
    assert _sha256(runner.RUNTIME_QUEUE_STATE_PATH) == builder.RUNTIME_QUEUE_SHA256
    seed = json.loads(runner.SEED_QUEUE_STATE_PATH.read_bytes())
    runtime = json.loads(runner.RUNTIME_QUEUE_STATE_PATH.read_bytes())
    assert seed["identity"] == runtime["identity"]
    assert [item["item_id"] for item in seed["items"]] == [
        item["item_id"] for item in runtime["items"]
    ]
    assert {item["state"] for item in runtime["items"]} == {"completed"}
    assert (
        sum(item["completion"]["activation_row_count"] for item in runtime["items"])
        == 49360
    )
    assert sum(item["completion"]["chunk_count"] for item in runtime["items"]) == 1320


def _final_index(trajectory_id: str) -> dict:
    runtime = json.loads(runner.RUNTIME_QUEUE_STATE_PATH.read_bytes())
    item = next(
        item for item in runtime["items"] if item["trajectory_id"] == trajectory_id
    )
    path = (
        runner.STORE_OUTPUT_ROOT
        / f"{trajectory_id}-activation-store-v2"
        / "indexes"
        / f"index-{item['completion']['activation_index_sha256']}.json"
    )
    return json.loads(path.read_bytes())


def test_real_five_frame_smoke_and_rollover_are_visible_posthoc() -> None:
    smoke = _final_index("layout_03_ep12622")
    assert len(smoke["index_rows"]) == 100
    assert len(smoke["chunks"]) == 20
    assert {row["global_model_frame_idx"] for row in smoke["index_rows"]} == set(
        range(5)
    )

    rollover = _final_index("layout_06_ep12625")
    assert len(rollover["index_rows"]) == 1340
    for layer_idx in range(20):
        rows = {
            row["global_model_frame_idx"]: row
            for row in rollover["index_rows"]
            if row["layer_idx"] == layer_idx
        }
        assert rows[15]["context_local_pair_idx"] == 15
        assert rows[16]["context_local_pair_idx"] == 0
        assert rows[17]["context_local_pair_idx"] == 1
        assert all(
            row["context_local_pair_idx"] == frame_idx % 16
            for frame_idx, row in rows.items()
        )


def test_finalizer_is_cpu_only_and_uses_existing_consumers() -> None:
    source = (
        SCRIPTS / "build_person_a_66_cell_production_activation_index_v0_1.py"
    ).read_text()
    assert "load_activation_index_snapshot_v2(" in source
    assert "load_activation_index_v2(" in source
    assert "validate_combined_activation_index_bytes(" in source
    assert "process_trajectory(" not in source
    assert "teacher_forced(" not in source
    assert "torch.cuda" not in source


def test_published_receipts_are_hash_bound_when_present() -> None:
    inventory_path = STATUS / "sha256_inventory.json"
    if not inventory_path.is_file():
        pytest.skip("publication builder has not run yet")
    inventory = json.loads(inventory_path.read_bytes())
    for name, identity in inventory["files"].items():
        path = STATUS / name
        assert path.stat().st_size == identity["byte_size"]
        assert _sha256(path) == identity["sha256"]
    validation = json.loads(
        (STATUS / "production_validation_receipt.json").read_bytes()
    )
    assert validation["raw_extraction_complete"] is True
    assert validation["store_chain_valid"] is True
    assert validation["duplicate_key_count"] == 0
    assert validation["missing_key_count"] == 0
    assert validation["unexpected_key_count"] == 0
    assert validation["cardinality"] == {
        "activation_chunk_count": 1320,
        "activation_row_count": 49360,
        "layer_count": 20,
        "model_frame_key_count": 2468,
        "stored_dtype": "float32",
        "trajectory_count": 66,
    }


def test_integrated_handoff_has_no_branch_locality_requirement_when_present() -> None:
    path = STATUS / "production_activation_handoff.json"
    if not path.is_file():
        pytest.skip("publication builder has not run yet")
    handoff = json.loads(path.read_bytes())
    assert handoff["consumer_roles"] == ["person_b", "person_d"]
    assert handoff["branch_locality_required"] is False
    assert handoff["scientific_fitting_executed"] is False
    assert handoff["join_contract"]["activation_key"] == [
        "trajectory_id",
        "global_model_frame_idx",
        "layer_idx",
    ]
    assert (
        handoff["downstream_authorities"]["person_b_fold_manifest"]["sha256"]
        == builder.EXPECTED_B_FOLD_SHA256
    )
    assert (
        handoff["downstream_authorities"]["person_b_oracle_target_manifest"]["sha256"]
        == builder.EXPECTED_B_ORACLE_MANIFEST_SHA256
    )
