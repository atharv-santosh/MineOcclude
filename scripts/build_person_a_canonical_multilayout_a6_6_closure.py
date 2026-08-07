#!/usr/bin/env python3
"""Build the immutable Person A A6.6 multi-layout closure.

This consumer never runs extraction or a scientific probe.  It verifies the
canonical five-layout collection, consumes the independently committed Person
B and Person E receipts, and copies those exact receipt bytes into a
self-contained Person A closure package.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MULTILAYOUT_SCRIPT = ROOT / "scripts/prepare_person_a_phase6_canonical_multilayout.py"
SUCCESSOR_ROOT = ROOT / (
    "docs/status/phase6_runtime/"
    "person-a-canonical-c6a-multilayout-successor-seed-20260725-retry-"
    "20260804T211350Z"
)
COLLECTION_PATH = SUCCESSOR_ROOT / "collection_manifest.json"

PERSON_A_SUCCESSOR_COMMIT = "1858ea12513f833b62ea916e0691ae994f117428"
PERSON_A_BRANCH = "role/person-a-model"
CANONICAL_C6A_ID = "person-c-c6a-post-c1-v0.1"
COLLECTION_SHA256 = "a672c834e8af3fd12c735e4042951b7b90d0aeeed5b0b62790aacdf3a58c0db0"
A_TO_B_SHA256 = "9d932df3aec859b17a4bbdd2afaa31d81dcb21c2bb62db668ed4158cbb855d94"
A_TO_E_SHA256 = "75d35991f34dabc3851dd2e31dc9e2b2912fa66a776034b7ecb7932bc854575b"
B_RECEIPT_SCHEMA = (
    "person-b-canonical-multilayout-positive-control-b-to-a-receipt-v0.1"
)
E_RECEIPT_SCHEMA = (
    "person-e-to-person-a-canonical-multilayout-activation-provenance-"
    "receipt-v0.1"
)
CLOSURE_SCHEMA_VERSION = "person-a-canonical-multilayout-a6-6-closure-v0.1"

EXPECTED_TRAJECTORIES = (
    "layout_01_ep12602",
    "layout_02_ep12610",
    "layout_03_ep12645",
    "layout_04_ep12626",
    "layout_05_ep12634",
)
EXPECTED_LAYOUTS = (
    "layout_01",
    "layout_02",
    "layout_03",
    "layout_04",
    "layout_05",
)
EXPECTED_INDEX_SHA256 = (
    "a6ba07a50ff20e9b90f0b036a0acd18783bad4fa3aacbebc0dd70df825f00a27",
    "29a750527e6b8bd3b8987d5a481f292280dec7e22263e292505fbce0103b711d",
    "2a4b0112f648f23cbe95a50404e073fd4839280a74973273d20afaf9d5b1c683",
    "a4a8b5943d2f2ad75b1e95d613ce44a6f88c9edba22f666837a671c5db1d5376",
    "32bf62d734dd2a0b8e6fee0599f28a920f7bf6d3ae9beb6b6222fdbc4321d4b3",
)


class A66ClosureError(RuntimeError):
    """A fail-closed receipt-consumption or package-validation error."""


def _fail(message: str) -> None:
    raise A66ClosureError(message)


def _load_module(path: Path, name: str) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        _fail(f"module is unavailable: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _json_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(document),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise A66ClosureError(f"could not read {label}: {error}") from error
    if not isinstance(document, dict):
        _fail(f"{label} must be a JSON object")
    return document


def _write_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"immutable output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(_json_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())


def _copy_exclusive(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"immutable output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_handle, destination.open("xb") as target:
        shutil.copyfileobj(source_handle, target, length=1024 * 1024)
        target.flush()
        os.fsync(target.fileno())
    if source.stat().st_size != destination.stat().st_size or _sha256_file(
        source
    ) != _sha256_file(destination):
        _fail(f"packaged receipt bytes differ: {source}")


def _require_sha256(value: str, label: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        _fail(f"{label} is not a SHA-256 digest")
    return normalized


def _require_commit(value: str, label: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 40 or any(character not in "0123456789abcdef" for character in normalized):
        _fail(f"{label} is not a full Git commit")
    return normalized


def _identity_order(rows: object, names: Sequence[str], label: str) -> tuple[str, ...]:
    if not isinstance(rows, list):
        _fail(f"{label} must be an array")
    values: list[str] = []
    for row in rows:
        if isinstance(row, str):
            values.append(row)
            continue
        if not isinstance(row, Mapping):
            _fail(f"{label} contains a non-identity row")
        found = next((row.get(name) for name in names if isinstance(row.get(name), str)), None)
        if found is None:
            _fail(f"{label} identity field is missing")
        values.append(str(found))
    return tuple(values)


def _descriptor(root: Path, path: Path, role: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _collection_summary() -> dict[str, Any]:
    if _sha256_file(COLLECTION_PATH) != COLLECTION_SHA256:
        _fail("canonical collection manifest hash differs")
    collection = _read_object(COLLECTION_PATH, "canonical collection manifest")
    logical_order = collection.get("logical_order")
    if not isinstance(logical_order, list):
        _fail("canonical collection logical order is missing")
    trajectories = tuple(
        str(row.get("trajectory_id", ""))
        for row in logical_order
        if isinstance(row, Mapping)
    )
    indexes = tuple(
        str(row.get("activation_index_sha256", ""))
        for row in logical_order
        if isinstance(row, Mapping)
    )
    runs = collection.get("runs")
    layouts = tuple(
        str(row.get("layout_id", ""))
        for row in runs
        if isinstance(row, Mapping)
    ) if isinstance(runs, list) else ()
    expected = {
        "schema_version": "person-a-canonical-c6a-multirun-collection-v0.1",
        "status": "READY_FOR_PERSON_B_AND_PERSON_E_REVIEW",
        "immutable": True,
        "canonical_c6a_id": CANONICAL_C6A_ID,
        "layout_count": 5,
        "trajectory_count": 5,
        "activation_index_count": 5,
        "activation_row_count": 6000,
        "activation_chunk_count": 100,
        "no_missing_extra_duplicate_stale_or_reordered_rows": True,
    }
    if any(collection.get(key) != value for key, value in expected.items()):
        _fail("canonical collection identity or aggregate counts differ")
    if trajectories != EXPECTED_TRAJECTORIES or layouts != EXPECTED_LAYOUTS:
        _fail("canonical trajectory or layout order differs")
    if indexes != EXPECTED_INDEX_SHA256:
        _fail("canonical activation-index order differs")
    if (
        collection.get("person_a_to_person_b_handoff", {}).get("sha256")
        != A_TO_B_SHA256
        or collection.get("person_a_to_person_e_handoff", {}).get("sha256")
        != A_TO_E_SHA256
    ):
        _fail("canonical downstream handoff identities differ")

    multilayout = _load_module(MULTILAYOUT_SCRIPT, "person_a_a6_6_multilayout_validator")
    runtime_root = SUCCESSOR_ROOT.parent
    for run, trajectory in zip(runs, EXPECTED_TRAJECTORIES, strict=True):
        manifest_identity = run.get("output_bundle_manifest")
        if not isinstance(manifest_identity, Mapping):
            _fail(f"{trajectory} output-bundle identity is missing")
        expected_manifest_sha = str(manifest_identity.get("sha256", ""))
        matches = [
            path.parent
            for path in runtime_root.glob("*/output_bundle_manifest.json")
            if _sha256_file(path) == expected_manifest_sha
        ]
        if len(matches) != 1:
            _fail(f"{trajectory} local output bundle is missing or ambiguous")
        multilayout._validate_output_bundle(matches[0], trajectory)
    return {
        "activation_chunk_count": 100,
        "activation_index_count": 5,
        "activation_index_sha256": list(EXPECTED_INDEX_SHA256),
        "activation_row_count": 6000,
        "a_to_b_handoff_sha256": A_TO_B_SHA256,
        "a_to_e_handoff_sha256": A_TO_E_SHA256,
        "canonical_c6a_id": CANONICAL_C6A_ID,
        "collection_manifest_path": str(COLLECTION_PATH.resolve()),
        "collection_manifest_sha256": COLLECTION_SHA256,
        "layout_count": 5,
        "layout_ids": list(EXPECTED_LAYOUTS),
        "source_frame_count": 300,
        "trajectory_count": 5,
        "trajectory_ids": list(EXPECTED_TRAJECTORIES),
    }


def _validate_b_receipt(document: Mapping[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != B_RECEIPT_SCHEMA or document.get("immutable") is not True:
        _fail("Person B successor receipt schema or immutability differs")
    collection = document.get("collection_manifest")
    handoff = document.get("a_to_b_handoff")
    decision = document.get("decision")
    real = document.get("real_label_positive_control")
    shuffled = document.get("shuffled_control")
    join = document.get("source_identity_join")
    folds = document.get("fold_identities")
    execution = document.get("execution")
    if not all(
        isinstance(value, Mapping)
        for value in (
            collection,
            handoff,
            decision,
            real,
            shuffled,
            join,
            folds,
            execution,
        )
    ):
        _fail("Person B successor receipt sections are missing")
    if collection.get("sha256") != COLLECTION_SHA256 or handoff.get("sha256") != A_TO_B_SHA256:
        _fail("Person B receipt binds a different Person A successor")
    trajectories = _identity_order(
        document.get("trajectory_identities"), ("trajectory_id", "id"), "Person B trajectories"
    )
    indexes = _identity_order(
        document.get("activation_index_identities"), ("sha256", "activation_index_sha256"), "Person B indexes"
    )
    layouts = tuple(
        str(row.get("layout_id", ""))
        for row in document.get("trajectory_identities", [])
        if isinstance(row, Mapping)
    )
    if trajectories != EXPECTED_TRAJECTORIES or layouts != EXPECTED_LAYOUTS or indexes != EXPECTED_INDEX_SHA256:
        _fail("Person B receipt collection identities differ")
    if (
        document.get("layout_count") != 5
        or document.get("trajectory_count") != 5
        or document.get("activation_index_count") != 5
        or document.get("activation_row_count") != 6000
        or document.get("activation_chunk_count") != 100
    ):
        _fail("Person B receipt activation counts differ")
    if (
        join.get("pass") is not True
        or join.get("activation_rows_matched") != 6000
        or join.get("frame_rows_matched") != 300
        or join.get("identity_error_count") != 0
    ):
        _fail("Person B source-identity join did not pass")
    if (
        folds.get("grouping_key") != "layout_id"
        or folds.get("outer_fold_count") != 5
        or folds.get("inner_fold_count") != 4
        or sorted(
            row.get("fold_idx")
            for row in folds.get("layout_assignments", ())
            if isinstance(row, Mapping)
        )
        != list(range(5))
    ):
        _fail("Person B frozen grouped-fold identities differ")
    shuffled_metrics = shuffled.get("metrics")
    if (
        real.get("complete") is not True
        or real.get("status") != "COMPLETE_FROZEN_LAYOUT_GROUPED_OOF"
        or not isinstance(real.get("metrics"), list)
        or len(real["metrics"]) != 20
        or shuffled.get("complete") is not True
        or shuffled.get("status")
        != "COMPLETE_FROZEN_WHOLE_TRAJECTORY_GROUPED_SHUFFLE"
        or not isinstance(shuffled_metrics, Mapping)
        or shuffled_metrics.get("permutation_count") != 999
        or shuffled_metrics.get("permutation_seed") != 20260720
        or shuffled_metrics.get("permutation_unit") != "whole_trajectory_block"
        or shuffled_metrics.get("p_value_rule") != "add_one_greater_or_equal"
        or shuffled_metrics.get("permutation_refit_policy")
        != "refit_scaler_alpha_and_ridge_inside_each_permutation"
        or shuffled_metrics.get("p_value")
        != (int(shuffled_metrics.get("extreme_null_count", -1)) + 1) / 1000
        or not (
            float(shuffled_metrics.get("null_r2_minimum", float("inf")))
            <= float(shuffled_metrics.get("null_r2_mean", float("-inf")))
            <= float(shuffled_metrics.get("null_r2_maximum", float("-inf")))
        )
    ):
        _fail("Person B real-label or shuffled control is incomplete")
    if (
        decision.get("positive_control_pass") is not True
        or decision.get("status")
        != "PASS_FROZEN_CANONICAL_MULTILAYOUT_VISIBLE_POSITION_POSITIVE_CONTROL"
        or execution.get("person_a_commit") != PERSON_A_SUCCESSOR_COMMIT
        or execution.get("scientific_fit_performed") is not True
        or execution.get("receipt_generation_recomputed_scientific_control")
        is not False
        or execution.get("scientific_execution_semantics", {}).get(
            "real_label_execution_count"
        )
        != 1
        or execution.get("scientific_execution_semantics", {}).get(
            "shuffled_execution_count"
        )
        != 1
    ):
        _fail("Person B frozen positive control did not pass")
    blockers = document.get("remaining_blockers")
    if blockers != []:
        _fail("Person B receipt retains blockers")
    return {
        "decision_status": decision.get("status"),
        "positive_control_pass": True,
        "real_label_complete": True,
        "shuffled_control_complete": True,
        "source_identity_join_pass": True,
    }


def _validate_e_receipt(document: Mapping[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != E_RECEIPT_SCHEMA or document.get("immutable") is not True:
        _fail("Person E successor receipt schema or immutability differs")
    if (
        document.get("status") != "READY_FOR_A6_6_PROVENANCE_CONSUMPTION"
        or document.get("a6_6_performed") is not False
        or document.get("a6_6_provenance_consumption_authorized") is not True
        or document.get("unresolved_blockers") != []
    ):
        _fail("Person E receipt does not authorize blocker-free A6.6 consumption")
    identity = document.get("collection_identity")
    if not isinstance(identity, Mapping):
        _fail("Person E collection identity is missing")
    collection_sha256 = identity.get("collection_manifest_sha256")
    handoff_sha256 = identity.get("a_to_e_handoff_sha256")
    if collection_sha256 != COLLECTION_SHA256 or handoff_sha256 != A_TO_E_SHA256:
        _fail("Person E receipt binds a different Person A successor")
    trajectories = _identity_order(
        identity.get("trajectory_ids", identity.get("trajectories")),
        ("trajectory_id", "id"),
        "Person E trajectories",
    )
    layouts = _identity_order(
        identity.get("layout_ids", identity.get("layouts")),
        ("layout_id", "id"),
        "Person E layouts",
    )
    activation = document.get("activation_provenance")
    if not isinstance(activation, Mapping):
        _fail("Person E activation provenance is missing")
    indexes = _identity_order(
        activation.get("activation_index_identities", activation.get("activation_indexes")),
        ("sha256", "activation_index_sha256"),
        "Person E indexes",
    )
    if trajectories != EXPECTED_TRAJECTORIES or layouts != EXPECTED_LAYOUTS or indexes != EXPECTED_INDEX_SHA256:
        _fail("Person E receipt collection identities differ")
    for key, expected in (
        ("layout_count", 5),
        ("trajectory_count", 5),
        ("activation_index_count", 5),
        ("activation_row_count", 6000),
        ("activation_chunk_count", 100),
    ):
        if identity.get(key) != expected:
            _fail(f"Person E receipt {key} differs")
    logical_order = identity.get("logical_order")
    if not isinstance(logical_order, list) or tuple(
        (row.get("trajectory_id"), row.get("activation_index_sha256"))
        for row in logical_order
        if isinstance(row, Mapping)
    ) != tuple(zip(EXPECTED_TRAJECTORIES, EXPECTED_INDEX_SHA256, strict=True)):
        _fail("Person E logical collection order differs")
    person_a_result = document.get("person_a_result")
    validation = document.get("validation")
    if (
        not isinstance(person_a_result, Mapping)
        or person_a_result.get("producing_successor_commit")
        != PERSON_A_SUCCESSOR_COMMIT
        or not isinstance(validation, Mapping)
        or not all(value is True for value in validation.values())
    ):
        _fail("Person E producing commit or provenance validations differ")
    return {
        "a6_6_provenance_consumption_authorized": True,
        "receipt_status": str(document["status"]),
        "successor_accepted": True,
    }


def _schema_document() -> dict[str, Any]:
    required = [
        "a6_6_complete",
        "authority_binding",
        "collection_identity",
        "consumed_receipts",
        "decision",
        "historical_preservation",
        "immutable",
        "remaining_blockers",
        "schema_version",
        "status",
        "step",
    ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "properties": {
            "a6_6_complete": {"const": True},
            "authority_binding": {"type": "object"},
            "collection_identity": {"type": "object"},
            "consumed_receipts": {"type": "object"},
            "decision": {"type": "object"},
            "historical_preservation": {"type": "object"},
            "immutable": {"const": True},
            "remaining_blockers": {"maxItems": 0, "type": "array"},
            "schema_version": {"const": CLOSURE_SCHEMA_VERSION},
            "status": {"const": "A6_6_COMPLETE"},
            "step": {"const": "A6.6"},
        },
        "required": required,
        "title": "Person A canonical multi-layout A6.6 closure",
        "type": "object",
    }


def build_closure(
    *,
    person_b_receipt: Path,
    person_b_receipt_sha256: str,
    person_b_commit: str,
    person_e_receipt: Path,
    person_e_receipt_sha256: str,
    person_e_commit: str,
    destination: Path,
) -> dict[str, Any]:
    """Validate both owner receipts and publish one create-only closure package."""

    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"immutable A6.6 package already exists: {destination}")
    b_hash = _require_sha256(person_b_receipt_sha256, "Person B receipt hash")
    e_hash = _require_sha256(person_e_receipt_sha256, "Person E receipt hash")
    if _sha256_file(person_b_receipt) != b_hash:
        _fail("Person B receipt hash differs")
    if _sha256_file(person_e_receipt) != e_hash:
        _fail("Person E receipt hash differs")
    b_document = _read_object(person_b_receipt, "Person B successor receipt")
    e_document = _read_object(person_e_receipt, "Person E successor receipt")
    collection = _collection_summary()
    b_result = _validate_b_receipt(b_document)
    e_result = _validate_e_receipt(e_document)

    b_commit = _require_commit(person_b_commit, "Person B receipt commit")
    e_commit = _require_commit(person_e_commit, "Person E receipt commit")
    destination.mkdir(parents=True)
    b_copy = destination / "consumed_receipts/person_b_b_to_a_successor_receipt.json"
    b_result_copy = destination / "consumed_receipts/person_b_completed_control_results.json"
    e_copy = destination / "consumed_receipts/person_e_to_person_a_successor_receipt.json"
    _copy_exclusive(person_b_receipt, b_copy)
    b_result_identity = b_document.get("completed_control_results")
    if not isinstance(b_result_identity, Mapping) or b_result_identity.get("valid") is not True:
        _fail("Person B completed-control artifact identity is missing")
    b_result_source = Path(str(b_result_identity.get("path", ""))).resolve()
    b_result_hash = _require_sha256(
        str(b_result_identity.get("sha256", "")),
        "Person B completed-control artifact hash",
    )
    if not b_result_source.is_file() or _sha256_file(b_result_source) != b_result_hash:
        _fail("Person B completed-control artifact hash differs")
    _copy_exclusive(b_result_source, b_result_copy)
    _copy_exclusive(person_e_receipt, e_copy)

    closure = {
        "a6_6_complete": True,
        "authority_binding": {
            "person_a_branch": PERSON_A_BRANCH,
            "person_a_successor_commit": PERSON_A_SUCCESSOR_COMMIT,
            "person_b_receipt_commit": b_commit,
            "person_e_receipt_commit": e_commit,
        },
        "collection_identity": collection,
        "consumed_receipts": {
            "person_b": {
                "commit": b_commit,
                "decision": b_result,
                "packaged_path": b_copy.relative_to(destination).as_posix(),
                "result_artifact": {
                    "packaged_path": b_result_copy.relative_to(destination).as_posix(),
                    "sha256": b_result_hash,
                    "source_path": str(b_result_source),
                },
                "schema_version": B_RECEIPT_SCHEMA,
                "sha256": b_hash,
                "source_path": str(person_b_receipt.resolve()),
            },
            "person_e": {
                "commit": e_commit,
                "decision": e_result,
                "packaged_path": e_copy.relative_to(destination).as_posix(),
                "schema_version": E_RECEIPT_SCHEMA,
                "sha256": e_hash,
                "source_path": str(person_e_receipt.resolve()),
            },
        },
        "decision": {
            "person_b_positive_control_pass": True,
            "person_e_provenance_consumption_authorized": True,
            "status": "CLOSE_A6_6",
        },
        "historical_preservation": {
            "person_b_probe_rerun_by_person_a": False,
            "person_e_single_trajectory_receipt_preserved": True,
            "predecessor_handoffs_preserved": True,
            "scientific_extraction_rerun": False,
            "successor_receipts_packaged_byte_for_byte": True,
        },
        "immutable": True,
        "remaining_blockers": [],
        "schema_version": CLOSURE_SCHEMA_VERSION,
        "status": "A6_6_COMPLETE",
        "step": "A6.6",
    }
    schema_path = destination / "a6_6_closure.schema.json"
    closure_path = destination / "a6_6_closure.json"
    validation_path = destination / "validation_receipt.json"
    _write_exclusive(schema_path, _schema_document())
    _write_exclusive(closure_path, closure)
    _write_exclusive(
        validation_path,
        {
            "a6_6_complete": True,
            "collection_manifest_valid": True,
            "collection_outputs_valid": True,
            "identity_convergence_valid": True,
            "person_b_receipt_hash_valid": True,
            "person_b_frozen_positive_control_pass": True,
            "person_e_a6_6_consumption_authorized": True,
            "person_e_receipt_hash_valid": True,
            "receipt_bytes_packaged": True,
            "schema_version": "person-a-canonical-multilayout-a6-6-validation-v0.1",
            "status": "PASS",
            "unresolved_blockers": [],
        },
    )
    inventory_rows = [
        _descriptor(destination, path, "a6_6_closure_evidence")
        for path in sorted(item for item in destination.rglob("*") if item.is_file())
    ]
    inventory_path = destination / "sha256_inventory.json"
    _write_exclusive(
        inventory_path,
        {
            "files": inventory_rows,
            "schema_version": "person-a-canonical-multilayout-a6-6-inventory-v0.1",
            "status": "PASS",
        },
    )
    return {
        "a6_6_complete": True,
        "closure_path": str(closure_path.resolve()),
        "closure_sha256": _sha256_file(closure_path),
        "inventory_path": str(inventory_path.resolve()),
        "status": "PASS",
    }


def validate_closure_package(package_root: Path) -> dict[str, Any]:
    """Validate an already published self-contained closure package."""

    closure_path = package_root / "a6_6_closure.json"
    closure = _read_object(closure_path, "A6.6 closure")
    schema = _read_object(package_root / "a6_6_closure.schema.json", "A6.6 schema")
    validation = _read_object(package_root / "validation_receipt.json", "A6.6 validation")
    inventory = _read_object(package_root / "sha256_inventory.json", "A6.6 inventory")
    if set(closure) != set(schema.get("required", [])):
        _fail("A6.6 closure fields differ from its closed schema")
    if (
        closure.get("schema_version") != CLOSURE_SCHEMA_VERSION
        or closure.get("status") != "A6_6_COMPLETE"
        or closure.get("a6_6_complete") is not True
        or closure.get("remaining_blockers") != []
        or validation.get("status") != "PASS"
    ):
        _fail("A6.6 closure decision is not complete")
    rows = inventory.get("files")
    if not isinstance(rows, list):
        _fail("A6.6 inventory rows are missing")
    expected_paths = {
        "a6_6_closure.json",
        "a6_6_closure.schema.json",
        "consumed_receipts/person_b_b_to_a_successor_receipt.json",
        "consumed_receipts/person_b_completed_control_results.json",
        "consumed_receipts/person_e_to_person_a_successor_receipt.json",
        "validation_receipt.json",
    }
    if {row.get("path") for row in rows if isinstance(row, Mapping)} != expected_paths:
        _fail("A6.6 inventory file set differs")
    for row in rows:
        if not isinstance(row, Mapping):
            _fail("A6.6 inventory contains a non-object row")
        path = package_root / str(row.get("path", ""))
        if (
            not path.is_file()
            or path.stat().st_size != row.get("size_bytes")
            or _sha256_file(path) != row.get("sha256")
        ):
            _fail(f"A6.6 inventory identity differs: {path}")
    for owner in ("person_b", "person_e"):
        descriptor = closure.get("consumed_receipts", {}).get(owner)
        if not isinstance(descriptor, Mapping):
            _fail(f"A6.6 {owner} receipt descriptor is missing")
        packaged = package_root / str(descriptor.get("packaged_path", ""))
        if _sha256_file(packaged) != descriptor.get("sha256"):
            _fail(f"A6.6 packaged {owner} receipt hash differs")
    return {
        "a6_6_complete": True,
        "closure_sha256": _sha256_file(closure_path),
        "status": "PASS",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--person-b-receipt", type=Path, required=True)
    build.add_argument("--person-b-receipt-sha256", required=True)
    build.add_argument("--person-b-commit", required=True)
    build.add_argument("--person-e-receipt", type=Path, required=True)
    build.add_argument("--person-e-receipt-sha256", required=True)
    build.add_argument("--person-e-commit", required=True)
    build.add_argument("--destination", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--package-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(argv)
    if namespace.operation == "build":
        result = build_closure(
            person_b_receipt=namespace.person_b_receipt.resolve(),
            person_b_receipt_sha256=namespace.person_b_receipt_sha256,
            person_b_commit=namespace.person_b_commit,
            person_e_receipt=namespace.person_e_receipt.resolve(),
            person_e_receipt_sha256=namespace.person_e_receipt_sha256,
            person_e_commit=namespace.person_e_commit,
            destination=namespace.destination.resolve(),
        )
    else:
        result = validate_closure_package(namespace.package_root.resolve())
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
