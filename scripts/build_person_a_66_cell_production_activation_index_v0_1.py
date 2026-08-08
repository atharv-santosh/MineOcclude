#!/usr/bin/env python3
"""Validate and publish the completed 66-cell production activation output.

This finalizer is CPU-only. It authenticates the completed external Store-v2
payload, preserves the immutable queue seed, publishes the established
multi-pilot combined-index format outside Git, and writes compact Git receipts
for the integrated Person B/D consumers. It never invokes model inference.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from mineocclude.activations.store_v2 import (  # noqa: E402
    ACTIVATION_STORE_V2_FORMAT_VERSION,
    canonical_json_bytes as store_v2_canonical_json_bytes,
    load_activation_index_snapshot_v2,
)
from mineocclude.analysis.production_v2 import (  # noqa: E402
    COMBINED_ACTIVATION_INDEX_FORMAT_VERSION,
    validate_combined_activation_index_bytes,
)
from mineocclude.contracts.activation_v2 import (  # noqa: E402
    ExternalChunkBinding,
    PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT,
    load_activation_index_v2,
    person_a_activation_index_v2_canonical_json_bytes,
)
from mineocclude.experiments.extraction_queue import (  # noqa: E402
    ExtractionQueue,
    ItemState,
)
import run_person_a_66_cell_production_extraction as runner  # noqa: E402

PUBLICATION_VERSION = "person-a-66-cell-production-finalization-v0.1"
EXPECTED_TRAJECTORY_COUNT = 66
EXPECTED_MODEL_FRAME_KEY_COUNT = 2468
EXPECTED_LAYER_COUNT = 20
EXPECTED_ACTIVATION_ROW_COUNT = 49360
EXPECTED_ACTIVATION_CHUNK_COUNT = 1320
EXPECTED_STORED_DTYPE = "float32"
EXPECTED_EXTRACTION_CODE_SHA = "6d3f23b0504817fe012320c285a5ed9025e5fd91"
EXECUTED_RUNNER_SHA256 = (
    "df2a90a92df10725e6c19c2e3119794878927a6a7ab58f9f86b07205288876b9"
)
RUNTIME_QUEUE_SHA256 = (
    "d92474958979669c1af45dce7423c354fbd23801a69324ff2d0308e11f076fce"
)

PRODUCTION_OUTPUT_ROOT = runner.STORE_OUTPUT_ROOT.parent
COMBINED_INDEX_PATH = PRODUCTION_OUTPUT_ROOT / "combined_activation_index.json"
EXTERNAL_STATUS_ROOT = (
    PRODUCTION_OUTPUT_ROOT / "status/person_a_66_cell_production_activation_index_v0_1"
)
EXTERNAL_INVENTORY_ROOT = EXTERNAL_STATUS_ROOT / "per_trajectory_inventories"
DOC_OUTPUT_ROOT = ROOT / "docs/status/person_a_66_cell_production_activation_index_v0_1"
EXECUTED_RUNNER_PATH = runner.RUNTIME_STATUS_ROOT / "executed_extraction_runner.py"
A_MATRIX_REPORT_PATH = (
    "docs/status/person_a_phase7_mvp_v0_1/step_7_2_matrix_report.json"
)
C_CAPTURE_MANIFEST_PATH = (
    "docs/status/person_c_66_cell_capture_authority_v0_1/capture_package_manifest.json"
)

C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
C_CANONICAL_FRAME_INDEX_PATH = (
    "docs/status/person_c_66_cell_canonical_media_v0_1/" "canonical_frame_index.jsonl"
)
B_FOLD_PATH = (
    ROOT / "docs/status/person_b_66_cell_preactivation_v0_1/fold_manifest.json"
)
B_ORACLE_MANIFEST_PATH = (
    ROOT / "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_manifest.json"
)
B_ORACLE_RECORDS_PATH = (
    ROOT / "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_records.jsonl"
)
EXPECTED_B_FOLD_SHA256 = (
    "86739975882f4926c3398d5bfa21611daf06c579b3893809eb385e8dcd03001d"
)
EXPECTED_B_ORACLE_MANIFEST_SHA256 = (
    "c064e1856be67ebab95cbcb07b80009729c396f2398b15b4dec57458b73b8ac9"
)
EXPECTED_B_ORACLE_RECORDS_SHA256 = (
    "d95c83518d2ad322e6862f5460727382511fe831c0c6658a6cf72c9f7a8858b1"
)


class PublicationError(RuntimeError):
    """The completed output conflicts with a frozen production authority."""


def _fail(message: str) -> None:
    raise PublicationError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(document: Any) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _strict_json_bytes(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{label} repeats JSON key {key!r}")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: _fail(
                f"{label} contains non-finite constant {value!r}"
            ),
        )
    except PublicationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {error}")
    if not isinstance(document, Mapping):
        _fail(f"{label} root is not an object")
    return document


def _write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(document))


def _publish_exact(path: Path, payload: bytes) -> None:
    """Publish immutable external bytes, accepting an exact prior publication."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            _fail(f"immutable external publication conflicts at {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
                _fail(f"concurrent external publication conflicts at {path}")
    finally:
        temporary.unlink(missing_ok=True)


def _git_path_commit(path: Path) -> str:
    relative = str(path.relative_to(ROOT))
    result = subprocess.run(
        ["git", "-C", str(ROOT), "log", "-1", "--format=%H", "--", relative],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if len(commit) != 40:
        _fail(f"{relative} has no committed producing-code identity")
    return commit


def _artifact(path: Path, *, repository_relative: bool = False) -> dict[str, Any]:
    return {
        "byte_size": path.stat().st_size,
        "path": str(path.relative_to(ROOT) if repository_relative else path),
        "sha256": _sha256_file(path),
    }


def _jsonl_rows(payload: bytes) -> list[dict[str, Any]]:
    return [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]


def _load_authorities() -> dict[str, Any]:
    seed_bytes = runner.SEED_QUEUE_STATE_PATH.read_bytes()
    runtime_bytes = runner.RUNTIME_QUEUE_STATE_PATH.read_bytes()
    executed_runner_bytes = EXECUTED_RUNNER_PATH.read_bytes()
    if _sha256_bytes(seed_bytes) != runner.SEED_QUEUE_STATE_SHA256:
        _fail("committed seed queue SHA256 changed")
    if _sha256_bytes(runtime_bytes) != RUNTIME_QUEUE_SHA256:
        _fail("completed runtime queue SHA256 changed")
    if _sha256_bytes(executed_runner_bytes) != EXECUTED_RUNNER_SHA256:
        _fail("executed extraction-runner bytes changed")

    expected_identity = {
        "run_id": runner.RUN_ID,
        "config_hash": runner.CONFIG_HASH,
        "code_sha": runner.QUEUE_CODE_IDENTITY_SHA256,
        "accepted_manifest_sha256": runner.ACCEPTED_MANIFEST_SHA256,
    }
    seed_queue = ExtractionQueue.load(
        runner.SEED_QUEUE_STATE_PATH, expected_identity=expected_identity
    )
    runtime_queue = ExtractionQueue.load(
        runner.RUNTIME_QUEUE_STATE_PATH, expected_identity=expected_identity
    )
    if any(item.state is not ItemState.PENDING for item in seed_queue.items.values()):
        _fail("the immutable seed queue is not wholly pending")
    if any(
        item.state is not ItemState.COMPLETED or item.completion is None
        for item in runtime_queue.items.values()
    ):
        _fail("the runtime queue is not wholly completed")
    if set(seed_queue.items) != set(runtime_queue.items):
        _fail("seed and runtime queue trajectory sets differ")
    for trajectory_id in seed_queue.items:
        seed = seed_queue.items[trajectory_id]
        runtime = runtime_queue.items[trajectory_id]
        if (
            seed.expected != runtime.expected
            or seed.layout_id != runtime.layout_id
            or seed.group != runtime.group
            or seed.input_manifest_sha256 != runtime.input_manifest_sha256
        ):
            _fail(f"{trajectory_id}: runtime queue changed immutable work identity")

    accepted_bytes = runner._git_object_bytes(
        f"{runner.C_CANONICAL_MEDIA_COMMIT}:{C_ACCEPTED_MANIFEST_PATH}"
    )
    if _sha256_bytes(accepted_bytes) != runner.ACCEPTED_MANIFEST_SHA256:
        _fail("Person C accepted-manifest Git object hash differs")
    accepted_document = _strict_json_bytes(
        accepted_bytes, label="Person C accepted manifest"
    )
    accepted_rows = accepted_document.get("records")
    if not isinstance(accepted_rows, list):
        _fail("Person C accepted manifest lacks records")
    accepted_ids = {
        str(row["trajectory_id"])
        for row in accepted_rows
        if isinstance(row, Mapping) and row.get("accepted") is True
    }

    matrix_bytes = runner._git_object_bytes(f"HEAD:{A_MATRIX_REPORT_PATH}")
    matrix_document = _strict_json_bytes(
        matrix_bytes, label="Person A accepted-cell matrix"
    )
    matrix_rows = matrix_document.get("cells")
    if not isinstance(matrix_rows, list):
        _fail("Person A accepted-cell matrix lacks cells")
    matrix_by_id = {
        str(row["cell_id"]): row
        for row in matrix_rows
        if isinstance(row, Mapping) and row.get("state") == "accepted"
    }

    capture_manifest_bytes = runner._git_object_bytes(
        f"{runner.C_CANONICAL_MEDIA_COMMIT}:{C_CAPTURE_MANIFEST_PATH}"
    )
    capture_manifest = _strict_json_bytes(
        capture_manifest_bytes, label="Person C capture-package manifest"
    )
    capture_rows = capture_manifest.get("records")
    if not isinstance(capture_rows, list):
        _fail("Person C capture-package manifest lacks records")
    capture_by_id = {
        str(row["trajectory_id"]): row
        for row in capture_rows
        if isinstance(row, Mapping) and row.get("frozen_contract_accepted") is True
    }

    canonical_bytes = runner._git_object_bytes(
        f"{runner.C_CANONICAL_MEDIA_COMMIT}:{C_CANONICAL_FRAME_INDEX_PATH}"
    )
    canonical_rows = _jsonl_rows(canonical_bytes)
    canonical_keys = {
        (str(row["trajectory_id"]), int(row["model_frame_idx"]))
        for row in canonical_rows
    }

    frame_manifest_bytes = runner.FRAME_MANIFEST_PATH.read_bytes()
    frame_manifest = _strict_json_bytes(
        frame_manifest_bytes, label="Person A preprocessed-frame manifest"
    )
    frame_records = frame_manifest.get("records")
    if not isinstance(frame_records, list):
        _fail("preprocessed-frame manifest lacks records")
    frame_keys = {
        (str(row["trajectory_id"]), int(row["model_frame_idx"]))
        for row in frame_records
    }

    fold_bytes = B_FOLD_PATH.read_bytes()
    if _sha256_bytes(fold_bytes) != EXPECTED_B_FOLD_SHA256:
        _fail("Person B fold manifest hash differs")
    fold_document = _strict_json_bytes(fold_bytes, label="Person B fold manifest")
    memberships = fold_document.get("memberships")
    if not isinstance(memberships, list):
        _fail("Person B fold manifest lacks memberships")
    fold_keys = {
        (str(row["trajectory_id"]), int(row["model_frame_idx"])) for row in memberships
    }

    oracle_manifest_bytes = B_ORACLE_MANIFEST_PATH.read_bytes()
    oracle_records_bytes = B_ORACLE_RECORDS_PATH.read_bytes()
    if _sha256_bytes(oracle_manifest_bytes) != EXPECTED_B_ORACLE_MANIFEST_SHA256:
        _fail("Person B oracle-target manifest hash differs")
    if _sha256_bytes(oracle_records_bytes) != EXPECTED_B_ORACLE_RECORDS_SHA256:
        _fail("Person B oracle-target records hash differs")

    ordered_ids = tuple(sorted(runtime_queue.items))
    if (
        len(ordered_ids) != EXPECTED_TRAJECTORY_COUNT
        or set(ordered_ids) != accepted_ids
        or set(matrix_by_id) != accepted_ids
        or set(capture_by_id) != accepted_ids
        or {trajectory_id for trajectory_id, _ in canonical_keys} != accepted_ids
        or {trajectory_id for trajectory_id, _ in frame_keys} != accepted_ids
        or {trajectory_id for trajectory_id, _ in fold_keys} != accepted_ids
    ):
        _fail("trajectory membership differs across accepted 66-cell authorities")
    if not (
        len(canonical_keys)
        == len(frame_keys)
        == len(fold_keys)
        == EXPECTED_MODEL_FRAME_KEY_COUNT
        and canonical_keys == frame_keys == fold_keys
    ):
        _fail("global model-frame keys differ across C/A/B authorities")
    if (
        frame_manifest.get("person_a_preprocessing", {}).get("preprocess_hash")
        != runner.wave5.PERSON_A_66_CELL_V0_2_PREPROCESS_HASH
        or frame_manifest.get("person_a_preprocessing", {}).get(
            "preprocessing_identity"
        )
        != runner.wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE
    ):
        _fail("current preprocessing profile/hash differs from frozen authority")

    return {
        "accepted_manifest_bytes": accepted_bytes,
        "accepted_ids": accepted_ids,
        "capture_by_id": capture_by_id,
        "capture_manifest_bytes": capture_manifest_bytes,
        "matrix_by_id": matrix_by_id,
        "matrix_bytes": matrix_bytes,
        "canonical_frame_index_bytes": canonical_bytes,
        "expected_frame_keys": frame_keys,
        "fold_bytes": fold_bytes,
        "fold_document": fold_document,
        "frame_manifest_bytes": frame_manifest_bytes,
        "oracle_manifest_bytes": oracle_manifest_bytes,
        "oracle_records_bytes": oracle_records_bytes,
        "ordered_ids": ordered_ids,
        "runtime_bytes": runtime_bytes,
        "runtime_queue": runtime_queue,
        "seed_bytes": seed_bytes,
        "seed_queue": seed_queue,
    }


def load_trajectory_source_bindings(trajectory_id: str, frame_count: int):
    frame_map_bytes = runner._c_stream_bytes(trajectory_id, "frame_map")
    state_bytes = runner._c_stream_bytes(trajectory_id, "server_state")
    frame_map_rows = sorted(
        runner._jsonl_rows(frame_map_bytes), key=lambda row: row["model_frame_idx"]
    )
    state_rows = sorted(
        runner._jsonl_rows(state_bytes), key=lambda row: row["model_frame_idx"]
    )
    if len(frame_map_rows) != frame_count or len(state_rows) != frame_count:
        _fail(f"{trajectory_id}: C stream cardinality differs from queue")
    from mineocclude.activations.store_v2 import build_source_frame_bindings_v2

    return build_source_frame_bindings_v2(
        trajectory_id=trajectory_id,
        frame_map_rows=frame_map_rows,
        state_rows=state_rows,
        c_frame_map_sha256=runner._sha256_bytes(frame_map_bytes),
        c_state_sha256=runner._sha256_bytes(state_bytes),
    )


def _validate_index_chain(
    store_root: Path,
    *,
    trajectory_id: str,
    frame_count: int,
    expected_final_snapshot_id: str,
) -> dict[str, Any]:
    """Authenticate all 20 cumulative Store-v2 index snapshots without rehashing chunks."""

    parsed: list[tuple[int, Path, Mapping[str, Any]]] = []
    for path in sorted((store_root / "indexes").glob("index-*.json")):
        payload = path.read_bytes()
        document = _strict_json_bytes(payload, label=f"{trajectory_id} Store-v2 index")
        if payload != store_v2_canonical_json_bytes(dict(document)):
            _fail(f"{trajectory_id}: noncanonical Store-v2 index bytes")
        identity_document = dict(document)
        snapshot_id = identity_document.pop("snapshot_id", None)
        if (
            not isinstance(snapshot_id, str)
            or _sha256_bytes(store_v2_canonical_json_bytes(identity_document))
            != snapshot_id
            or path.name != f"index-{snapshot_id}.json"
        ):
            _fail(f"{trajectory_id}: invalid Store-v2 snapshot hash/name chain")
        chunks = document.get("chunks")
        rows = document.get("index_rows")
        if not isinstance(chunks, list) or not isinstance(rows, list):
            _fail(f"{trajectory_id}: malformed Store-v2 snapshot lists")
        parsed.append((len(chunks), path, document))

    parsed.sort(key=lambda value: value[0])
    if len(parsed) != EXPECTED_LAYER_COUNT or [value[0] for value in parsed] != list(
        range(1, EXPECTED_LAYER_COUNT + 1)
    ):
        _fail(f"{trajectory_id}: Store-v2 index chain is not exactly 1..20 chunks")
    prior_chunk_ids: set[str] = set()
    store_identity: Mapping[str, Any] | None = None
    creation_timestamp: str | None = None
    for step, _path, document in parsed:
        chunks = document["chunks"]
        rows = document["index_rows"]
        current_chunk_ids = {str(chunk["chunk_id"]) for chunk in chunks}
        layers = {int(row["layer_idx"]) for row in rows}
        keys = {
            (int(row["global_model_frame_idx"]), int(row["layer_idx"])) for row in rows
        }
        if (
            len(rows) != frame_count * step
            or layers != set(range(step))
            or keys
            != {(frame, layer) for frame in range(frame_count) for layer in range(step)}
            or not prior_chunk_ids < current_chunk_ids
            or len(current_chunk_ids - prior_chunk_ids) != 1
        ):
            _fail(f"{trajectory_id}: Store-v2 cumulative index chain is discontinuous")
        if store_identity is None:
            store_identity = document["store_identity"]
            creation_timestamp = str(document["creation_timestamp"])
        elif (
            document["store_identity"] != store_identity
            or document["creation_timestamp"] != creation_timestamp
        ):
            _fail(f"{trajectory_id}: Store-v2 identity changed inside index chain")
        prior_chunk_ids = current_chunk_ids
        del keys
    final_document = parsed[-1][2]
    if final_document["snapshot_id"] != expected_final_snapshot_id:
        _fail(f"{trajectory_id}: final Store-v2 snapshot differs from runtime queue")
    return {
        "creation_timestamp": creation_timestamp,
        "index_snapshot_count": len(parsed),
    }


def _expected_store_identity() -> dict[str, Any]:
    return {
        "accepted_manifest_hash": runner.ACCEPTED_MANIFEST_SHA256,
        "checkpoint_hash": runner.wave2.PINNED_MAIN_CHECKPOINT_SHA256,
        "code_sha": EXPECTED_EXTRACTION_CODE_SHA,
        "config_hash": runner.CONFIG_HASH,
        "dtype": EXPECTED_STORED_DTYPE,
        "format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
        "hidden_width": runner.HIDDEN_WIDTH,
        "hook_site": runner.HOOK_SITE,
        "model_hash": runner.wave2.PINNED_MAIN_CHECKPOINT_SHA256,
        "preprocess_hash": runner.wave5.PERSON_A_66_CELL_V0_2_PREPROCESS_HASH,
        "requested_layers": list(range(EXPECTED_LAYER_COUNT)),
        "run_id": runner.RUN_ID,
        "schema_version": "1.0",
    }


def _validate_and_collect(authorities: Mapping[str, Any]) -> dict[str, Any]:
    runtime_queue: ExtractionQueue = authorities["runtime_queue"]
    ordered_ids: tuple[str, ...] = authorities["ordered_ids"]
    expected_frame_keys: set[tuple[str, int]] = authorities["expected_frame_keys"]
    actual_store_dirs = {
        path.name.removesuffix("-activation-store-v2")
        for path in runner.STORE_OUTPUT_ROOT.glob("*-activation-store-v2")
        if path.is_dir() and not path.is_symlink()
    }
    if actual_store_dirs != set(ordered_ids):
        _fail("external Store-v2 trajectory directory set differs from authority")

    expected_scientific_keys = {
        (trajectory_id, model_frame_idx, layer_idx)
        for trajectory_id, model_frame_idx in expected_frame_keys
        for layer_idx in range(EXPECTED_LAYER_COUNT)
    }
    actual_scientific_keys: set[tuple[str, int, int]] = set()
    scientific_key_counter: Counter[tuple[Any, ...]] = Counter()
    actual_frame_keys: set[tuple[str, int]] = set()
    rows: list[dict[str, Any]] = []
    per_trajectory: list[dict[str, Any]] = []
    inventories: dict[str, dict[str, Any]] = {}
    inventory_identities: list[dict[str, Any]] = []
    chunk_hashes: set[str] = set()
    total_chunks = 0
    smoke_rows: list[dict[str, Any]] | None = None
    rollover_rows: list[dict[str, Any]] | None = None
    evidence_creation_timestamps: dict[str, str] = {}

    for position, trajectory_id in enumerate(ordered_ids, start=1):
        item = runtime_queue.items[trajectory_id]
        assert item.completion is not None
        package_bytes = runner._capture_package_bytes(trajectory_id)
        capture_record = authorities["capture_by_id"][trajectory_id]
        package_sha256 = _sha256_bytes(package_bytes)
        if package_sha256 != runner._capture_package_declared_sha256(
            trajectory_id
        ) or package_sha256 != capture_record.get("capture_package_sha256"):
            _fail(f"{trajectory_id}: capture-package bytes differ from C authority")
        matrix_record = authorities["matrix_by_id"][trajectory_id]
        evidence_path = str(matrix_record.get("evidence_path", ""))
        evidence_bytes = runner._git_object_bytes(f"HEAD:{evidence_path}")
        if (
            _sha256_bytes(evidence_bytes) != item.input_manifest_sha256
            or matrix_record.get("evidence_sha256") != item.input_manifest_sha256
            or capture_record.get("person_a_frame_map_sha256")
            != item.input_manifest_sha256
        ):
            _fail(
                f"{trajectory_id}: queue identity differs across the accepted A/C bridge"
            )
        store_root = runner.STORE_OUTPUT_ROOT / f"{trajectory_id}-activation-store-v2"
        final_index_path = (
            store_root
            / "indexes"
            / f"index-{item.completion.activation_index_sha256}.json"
        )
        source_bindings = load_trajectory_source_bindings(
            trajectory_id, item.expected.frame_count
        )
        chain = _validate_index_chain(
            store_root,
            trajectory_id=trajectory_id,
            frame_count=item.expected.frame_count,
            expected_final_snapshot_id=item.completion.activation_index_sha256,
        )
        snapshot = load_activation_index_snapshot_v2(
            final_index_path,
            store_root=store_root,
            source_bindings=source_bindings,
        )
        if snapshot.store_identity.to_document() != _expected_store_identity():
            _fail(f"{trajectory_id}: Store-v2 production identity differs")
        if (
            snapshot.snapshot_id != item.completion.activation_index_sha256
            or len(snapshot.index_rows) != item.completion.activation_row_count
            or len(snapshot.chunks) != item.completion.chunk_count
            or tuple(chunk.sha256 for chunk in snapshot.chunks)
            != item.completion.chunk_sha256
            or len(snapshot.chunks) != EXPECTED_LAYER_COUNT
        ):
            _fail(
                f"{trajectory_id}: Store-v2 final index differs from queue completion"
            )
        chunk_files = {path.name for path in (store_root / "chunks").glob("*.npy")}
        expected_chunk_files = {Path(chunk.path).name for chunk in snapshot.chunks}
        if chunk_files != expected_chunk_files:
            _fail(f"{trajectory_id}: stored chunk file set differs from final index")

        index_sha256 = _sha256_file(final_index_path)
        index_identity = {
            "byte_size": final_index_path.stat().st_size,
            "path": str(final_index_path),
            "sha256": index_sha256,
        }
        chunk_bindings = {
            chunk.chunk_id: ExternalChunkBinding(
                chunk_id=chunk.chunk_id,
                path=store_root / chunk.path,
                sha256=chunk.sha256,
                byte_size=chunk.byte_size,
                row_count=chunk.row_count,
            )
            for chunk in snapshot.chunks
        }
        loaded = load_activation_index_v2(
            final_index_path,
            canonicalization_contract=(
                PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
            ),
            expected_index_sha256=index_sha256,
            expected_index_byte_size=final_index_path.stat().st_size,
            expected_trajectory_id=trajectory_id,
            expected_manifest_sha256=runner.ACCEPTED_MANIFEST_SHA256,
            chunk_bindings=chunk_bindings,
            retain_vectors=False,
        )
        if _json_bytes([dict(row) for row in loaded.rows]) != _json_bytes(
            [dict(row) for row in snapshot.index_rows]
        ):
            _fail(f"{trajectory_id}: activation-v2 consumer rows differ from Store-v2")

        source_rows = sorted(
            (dict(row) for row in loaded.rows),
            key=lambda row: (
                int(row["global_model_frame_idx"]),
                int(row["layer_idx"]),
                int(row["context_local_pair_idx"]),
            ),
        )
        for row in source_rows:
            triple = (
                trajectory_id,
                int(row["global_model_frame_idx"]),
                int(row["layer_idx"]),
            )
            scientific_key = (
                row["trajectory_id"],
                row["global_model_frame_idx"],
                row["source_frame_id"],
                row["source_tick"],
                row["layer_idx"],
                row["hook_site"],
                row["checkpoint_hash"],
                row["preprocess_hash"],
            )
            actual_scientific_keys.add(triple)
            scientific_key_counter[scientific_key] += 1
            actual_frame_keys.add((trajectory_id, int(row["global_model_frame_idx"])))
            rows.append(row)
        chunks = [
            {
                "byte_size": chunk.byte_size,
                "chunk_id": chunk.chunk_id,
                "path": str(store_root / chunk.path),
                "row_count": chunk.row_count,
                "sha256": chunk.sha256,
            }
            for chunk in snapshot.chunks
        ]
        inventory = {
            "activation_index": index_identity,
            "activation_index_snapshot_id": snapshot.snapshot_id,
            "activation_row_count": len(source_rows),
            "chunks": chunks,
            "frame_count": item.expected.frame_count,
            "group": item.group,
            "layout_id": item.layout_id,
            "run_id": runner.RUN_ID,
            "status": "COMPLETED_AND_VALIDATED",
            "store_identity": snapshot.store_identity.to_document(),
            "store_root": str(store_root),
            "trajectory_id": trajectory_id,
        }
        inventory_path = EXTERNAL_INVENTORY_ROOT / f"{trajectory_id}.json"
        _publish_exact(inventory_path, _json_bytes(inventory))
        inventories[trajectory_id] = inventory
        inventory_identities.append(
            {"trajectory_id": trajectory_id, **_artifact(inventory_path)}
        )
        per_trajectory.append(
            {
                "activation_index": index_identity,
                "activation_index_snapshot_id": snapshot.snapshot_id,
                "activation_row_count": len(source_rows),
                "chunk_count": len(snapshot.chunks),
                "frame_count": item.expected.frame_count,
                "trajectory_id": trajectory_id,
            }
        )
        total_chunks += len(snapshot.chunks)
        for chunk in snapshot.chunks:
            if chunk.sha256 in chunk_hashes:
                _fail(f"{trajectory_id}: activation chunk SHA256 collides globally")
            chunk_hashes.add(chunk.sha256)
        evidence_creation_timestamps[trajectory_id] = str(chain["creation_timestamp"])
        if trajectory_id == "layout_03_ep12622":
            smoke_rows = source_rows
        if trajectory_id == "layout_06_ep12625":
            rollover_rows = source_rows
        print(
            f"validated {position:02d}/{len(ordered_ids)} {trajectory_id}",
            file=sys.stderr,
            flush=True,
        )
        del loaded, snapshot, source_bindings, source_rows
        gc.collect()

    duplicate_key_count = sum(
        count - 1 for count in scientific_key_counter.values() if count > 1
    )
    missing = expected_scientific_keys - actual_scientific_keys
    unexpected = actual_scientific_keys - expected_scientific_keys
    if (
        len(rows) != EXPECTED_ACTIVATION_ROW_COUNT
        or len(actual_frame_keys) != EXPECTED_MODEL_FRAME_KEY_COUNT
        or total_chunks != EXPECTED_ACTIVATION_CHUNK_COUNT
        or duplicate_key_count
        or missing
        or unexpected
        or actual_frame_keys != expected_frame_keys
        or len(chunk_hashes) != EXPECTED_ACTIVATION_CHUNK_COUNT
    ):
        _fail(
            "production activation cardinality/key mismatch: "
            f"rows={len(rows)}, frame_keys={len(actual_frame_keys)}, "
            f"chunks={total_chunks}, duplicates={duplicate_key_count}, "
            f"missing={len(missing)}, unexpected={len(unexpected)}"
        )
    if smoke_rows is None or rollover_rows is None:
        _fail("stored smoke/rollover evidence trajectories are missing")

    return {
        "actual_frame_keys": actual_frame_keys,
        "duplicate_key_count": duplicate_key_count,
        "evidence_creation_timestamps": evidence_creation_timestamps,
        "inventories": inventories,
        "inventory_identities": inventory_identities,
        "missing_key_count": len(missing),
        "per_trajectory": per_trajectory,
        "rollover_rows": rollover_rows,
        "rows": rows,
        "smoke_rows": smoke_rows,
        "total_chunks": total_chunks,
        "unexpected_key_count": len(unexpected),
    }


def _run_evidence(
    authorities: Mapping[str, Any], collected: Mapping[str, Any]
) -> dict[str, Any]:
    runtime_queue: ExtractionQueue = authorities["runtime_queue"]
    reports = []
    for path in sorted(runner.SESSION_LOG_ROOT.glob("environment_report_*.json")):
        document = json.loads(path.read_bytes())
        reports.append({**_artifact(path), "generated_at": document["generated_at"]})
    first_completion = min(
        item.completion.completed_at
        for item in runtime_queue.items.values()
        if item.completion is not None
    )
    pre_completion_reports = [
        report for report in reports if report["generated_at"] < first_completion
    ]
    if not pre_completion_reports:
        _fail("no environment report can bind the production drain start")
    drain_report = max(
        pre_completion_reports, key=lambda report: report["generated_at"]
    )
    drain_start = drain_report["generated_at"]

    smoke_id = "layout_03_ep12622"
    smoke_item = runtime_queue.items[smoke_id]
    smoke_rows = collected["smoke_rows"]
    smoke_created = collected["evidence_creation_timestamps"][smoke_id]
    smoke_present = (
        smoke_item.expected.frame_count == 5
        and len(smoke_rows) == 5 * EXPECTED_LAYER_COUNT
        and smoke_created < drain_start
        and smoke_item.completion is not None
        and smoke_item.completion.activation_row_count == 100
    )

    rollover_id = "layout_06_ep12625"
    rollover_item = runtime_queue.items[rollover_id]
    rollover_rows = collected["rollover_rows"]
    rollover_created = collected["evidence_creation_timestamps"][rollover_id]
    boundary_checks = []
    for layer_idx in range(EXPECTED_LAYER_COUNT):
        by_frame = {
            int(row["global_model_frame_idx"]): row
            for row in rollover_rows
            if int(row["layer_idx"]) == layer_idx
        }
        for global_idx, expected_local in ((15, 15), (16, 0), (17, 1)):
            row = by_frame.get(global_idx)
            boundary_checks.append(
                {
                    "context_local_pair_idx": (
                        row.get("context_local_pair_idx") if row else None
                    ),
                    "expected_context_local_pair_idx": expected_local,
                    "global_model_frame_idx": global_idx,
                    "layer_idx": layer_idx,
                    "pass": bool(row)
                    and row.get("context_local_pair_idx") == expected_local,
                }
            )
    all_rollover_rows_pass = all(
        int(row["context_local_pair_idx"]) == int(row["global_model_frame_idx"]) % 16
        for row in rollover_rows
    )
    boundary_pass = all(check["pass"] for check in boundary_checks)
    rollover_present = (
        rollover_item.expected.frame_count > 16
        and rollover_created < drain_start
        and boundary_pass
        and all_rollover_rows_pass
    )
    if not smoke_present or not rollover_present:
        _fail("authenticated pre-drain smoke/rollover stored evidence is incomplete")

    return {
        "evidence_class": (
            "authenticated_pre_drain_store_v2_outputs_plus_completed_runtime_queue"
        ),
        "environment_reports": reports,
        "explicit_validation_stdout_or_log_receipt_present": False,
        "production_drain": {
            "command": (
                "/home/sagemaker-user/.conda/envs/mineworld/bin/python "
                "scripts/run_person_a_66_cell_production_extraction.py drain"
            ),
            "command_evidence_class": "operator_observed",
            "environment_report": drain_report,
            "mode": "drain",
            "started_no_later_than": drain_start,
        },
        "rollover": {
            "activation_row_count": len(rollover_rows),
            "all_frame_local_identities_pass": all_rollover_rows_pass,
            "boundary_checks": boundary_checks,
            "evidence_present": rollover_present,
            "frame_15_to_16_boundary_pass": boundary_pass,
            "frame_count": rollover_item.expected.frame_count,
            "store_creation_timestamp": rollover_created,
            "store_predates_drain": rollover_created < drain_start,
            "trajectory_id": rollover_id,
            "validation_mode_command_receipt_present": False,
        },
        "run_id": runner.RUN_ID,
        "schema_id": f"{PUBLICATION_VERSION}-run-evidence",
        "schema_version": "1.0",
        "smoke": {
            "activation_row_count": len(smoke_rows),
            "evidence_present": smoke_present,
            "frame_count": smoke_item.expected.frame_count,
            "real_gpu_output": True,
            "store_creation_timestamp": smoke_created,
            "store_predates_drain": smoke_created < drain_start,
            "trajectory_id": smoke_id,
            "validation_mode_command_receipt_present": False,
        },
    }


def _code_identity() -> dict[str, Any]:
    builder_path = Path(__file__).resolve()
    runner_path = ROOT / "scripts/run_person_a_66_cell_production_extraction.py"
    return {
        "activation_index_builder": {
            "git_commit": _git_path_commit(builder_path),
            "path": str(builder_path.relative_to(ROOT)),
            "sha256": _sha256_file(builder_path),
        },
        "executed_extraction_runner": {
            "byte_size": EXECUTED_RUNNER_PATH.stat().st_size,
            "path": str(EXECUTED_RUNNER_PATH),
            "repository_head_recorded_in_store": EXPECTED_EXTRACTION_CODE_SHA,
            "sha256": EXECUTED_RUNNER_SHA256,
        },
        "finalized_extraction_runner": {
            "git_commit": _git_path_commit(runner_path),
            "path": str(runner_path.relative_to(ROOT)),
            "sha256": _sha256_file(runner_path),
        },
    }


def _publish_combined(
    authorities: Mapping[str, Any],
    collected: Mapping[str, Any],
    code_identity: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_queue: ExtractionQueue = authorities["runtime_queue"]
    ordered_ids: tuple[str, ...] = authorities["ordered_ids"]
    no_wall_ids = [
        trajectory_id
        for trajectory_id in ordered_ids
        if runtime_queue.items[trajectory_id].group == "no_wall_visible_control"
    ]
    completion_timestamp = max(
        item.completion.completed_at
        for item in runtime_queue.items.values()
        if item.completion is not None
    )
    combined = {
        "activation_index_format_version": COMBINED_ACTIVATION_INDEX_FORMAT_VERSION,
        "activation_store_format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
        "combined_activation_row_count": len(collected["rows"]),
        "creation_timestamp": completion_timestamp,
        "index_rows": collected["rows"],
        "no_wall_control_pilot_ids": no_wall_ids,
        "ordered_pilot_ids": list(ordered_ids),
        "per_pilot_indexes": [
            {
                "activation_index": collected["inventories"][trajectory_id][
                    "activation_index"
                ],
                "activation_row_count": collected["inventories"][trajectory_id][
                    "activation_row_count"
                ],
                "trajectory_id": trajectory_id,
            }
            for trajectory_id in ordered_ids
        ],
        "production_provenance": {
            "accepted_manifest_sha256": runner.ACCEPTED_MANIFEST_SHA256,
            "activation_chunk_count": EXPECTED_ACTIVATION_CHUNK_COUNT,
            "builder_code_identity": code_identity["activation_index_builder"],
            "checkpoint_hash": runner.wave2.PINNED_MAIN_CHECKPOINT_SHA256,
            "executed_extraction_code_identity": code_identity[
                "executed_extraction_runner"
            ],
            "global_model_frame_key_count": EXPECTED_MODEL_FRAME_KEY_COUNT,
            "layer_indices": list(range(EXPECTED_LAYER_COUNT)),
            "model_hash": runner.wave2.PINNED_MAIN_CHECKPOINT_SHA256,
            "preprocess_hash": runner.wave5.PERSON_A_66_CELL_V0_2_PREPROCESS_HASH,
            "preprocessing_identity": (
                runner.wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE
            ),
            "run_id": runner.RUN_ID,
            "runtime_queue_sha256": RUNTIME_QUEUE_SHA256,
            "seed_queue_sha256": runner.SEED_QUEUE_STATE_SHA256,
            "stored_dtype": EXPECTED_STORED_DTYPE,
            "trajectory_count": EXPECTED_TRAJECTORY_COUNT,
        },
        "schema_version": "1.0",
        "scientific_identity_collision_count": collected["duplicate_key_count"],
    }
    payload = person_a_activation_index_v2_canonical_json_bytes(combined)
    _publish_exact(COMBINED_INDEX_PATH, payload)
    identity = _artifact(COMBINED_INDEX_PATH)

    per_pilot_inventories = {
        trajectory_id: collected["inventories"][trajectory_id]
        for trajectory_id in ordered_ids
    }
    accepted_by_trajectory = {
        trajectory_id: runner.ACCEPTED_MANIFEST_SHA256 for trajectory_id in ordered_ids
    }
    validated = validate_combined_activation_index_bytes(
        payload,
        expected_sha256=identity["sha256"],
        expected_byte_size=identity["byte_size"],
        per_pilot_inventories=per_pilot_inventories,
        accepted_manifest_by_trajectory=accepted_by_trajectory,
        expected_pilot_ids=ordered_ids,
        expected_no_wall_ids=no_wall_ids,
        expected_row_count=EXPECTED_ACTIVATION_ROW_COUNT,
    )
    if validated.get("production_provenance") != combined["production_provenance"]:
        _fail("production-v2 consumer lost combined-index provenance")
    return identity


def _downstream_authorities(authorities: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "person_b_fold_manifest": {
            **_artifact(B_FOLD_PATH, repository_relative=True),
            "artifact_hash": authorities["fold_document"]["artifact_hash"],
            "model_frame_key_count": authorities["fold_document"][
                "model_frame_key_count"
            ],
        },
        "person_b_oracle_target_manifest": {
            **_artifact(B_ORACLE_MANIFEST_PATH, repository_relative=True),
            "target_records": _artifact(
                B_ORACLE_RECORDS_PATH, repository_relative=True
            ),
        },
        "person_c_accepted_manifest": {
            "git_commit": runner.C_CANONICAL_MEDIA_COMMIT,
            "path": C_ACCEPTED_MANIFEST_PATH,
            "sha256": runner.ACCEPTED_MANIFEST_SHA256,
        },
    }


def _publish_receipts(
    authorities: Mapping[str, Any],
    collected: Mapping[str, Any],
    code_identity: Mapping[str, Any],
    combined_identity: Mapping[str, Any],
    run_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    downstream = _downstream_authorities(authorities)
    cardinality = {
        "activation_chunk_count": EXPECTED_ACTIVATION_CHUNK_COUNT,
        "activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
        "layer_count": EXPECTED_LAYER_COUNT,
        "model_frame_key_count": EXPECTED_MODEL_FRAME_KEY_COUNT,
        "stored_dtype": EXPECTED_STORED_DTYPE,
        "trajectory_count": EXPECTED_TRAJECTORY_COUNT,
    }
    queue_authority = {
        "runtime_queue": {
            "byte_size": len(authorities["runtime_bytes"]),
            "path": str(runner.RUNTIME_QUEUE_STATE_PATH),
            "sha256": RUNTIME_QUEUE_SHA256,
            "state_counts": {"completed": EXPECTED_TRAJECTORY_COUNT},
        },
        "seed_queue": {
            "byte_size": len(authorities["seed_bytes"]),
            "path": str(runner.SEED_QUEUE_STATE_PATH.relative_to(ROOT)),
            "sha256": runner.SEED_QUEUE_STATE_SHA256,
            "state_counts": {"pending": EXPECTED_TRAJECTORY_COUNT},
        },
        "seed_authority_preserved": True,
        "static_work_identity_matches": True,
    }
    manifest = {
        "activation_store_format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
        "cardinality": cardinality,
        "code_identity": code_identity,
        "combined_activation_index": dict(combined_identity),
        "downstream_authorities": downstream,
        "external_payload_policy": {
            "activation_chunks_committed_to_git": False,
            "combined_index_committed_to_git": False,
            "per_trajectory_inventories": collected["inventory_identities"],
        },
        "queue_authority": queue_authority,
        "run_id": runner.RUN_ID,
        "schema_id": f"{PUBLICATION_VERSION}-activation-index-manifest",
        "schema_version": "1.0",
        "status": "READY",
    }
    validation = {
        "activation_v2_consumer_load_pass": True,
        "cardinality": cardinality,
        "duplicate_key_count": collected["duplicate_key_count"],
        "exact_checkpoint_model_authority_pass": True,
        "exact_preprocessing_authority_pass": True,
        "exact_run_identity_pass": True,
        "frame_15_to_16_boundary_pass": run_evidence["rollover"][
            "frame_15_to_16_boundary_pass"
        ],
        "global_model_frame_authority_pass": True,
        "missing_key_count": collected["missing_key_count"],
        "per_trajectory_chunk_count": EXPECTED_LAYER_COUNT,
        "production_v2_combined_index_validation_pass": True,
        "raw_extraction_complete": True,
        "run_id": runner.RUN_ID,
        "schema_id": f"{PUBLICATION_VERSION}-validation-receipt",
        "schema_version": "1.0",
        "seed_queue_authority_preserved": True,
        "store_chain_snapshot_count": EXPECTED_ACTIVATION_CHUNK_COUNT,
        "store_chain_valid": True,
        "trajectory_authority_pass": True,
        "unexpected_key_count": collected["unexpected_key_count"],
    }
    handoff = {
        "activation_index": dict(combined_identity),
        "activation_index_format_version": COMBINED_ACTIVATION_INDEX_FORMAT_VERSION,
        "activation_store_format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
        "branch_locality_required": False,
        "cardinality": cardinality,
        "consumer_roles": ["person_b", "person_d"],
        "downstream_authorities": downstream,
        "execution_branch_informational_only": "integration/mvp-final",
        "join_contract": {
            "activation_key": [
                "trajectory_id",
                "global_model_frame_idx",
                "layer_idx",
            ],
            "frame_key_mapping": {
                "activation.global_model_frame_idx": "fold_or_oracle.model_frame_idx",
                "activation.trajectory_id": "fold_or_oracle.trajectory_id",
            },
            "hook_site": runner.HOOK_SITE,
            "layer_indices": list(range(EXPECTED_LAYER_COUNT)),
            "no_row_order_or_directory_join": True,
        },
        "per_trajectory_inventories": collected["inventory_identities"],
        "run_id": runner.RUN_ID,
        "schema_id": f"{PUBLICATION_VERSION}-integrated-b-d-handoff",
        "schema_version": "1.0",
        "scientific_fitting_executed": False,
        "status": "READY_FOR_B_D_INPUT_LOADING_NOT_SCIENTIFIC_FITTING",
    }

    documents = {
        "production_activation_index_manifest.json": manifest,
        "production_activation_handoff.json": handoff,
        "production_run_evidence.json": dict(run_evidence),
        "production_validation_receipt.json": validation,
    }
    for name, document in documents.items():
        _write_json(DOC_OUTPUT_ROOT / name, document)
    inventory = {
        "files": {
            name: {
                "byte_size": (DOC_OUTPUT_ROOT / name).stat().st_size,
                "sha256": _sha256_file(DOC_OUTPUT_ROOT / name),
            }
            for name in sorted(documents)
        },
        "inventory_excludes_self": True,
        "schema_id": f"{PUBLICATION_VERSION}-sha256-inventory",
        "schema_version": "1.0",
    }
    _write_json(DOC_OUTPUT_ROOT / "sha256_inventory.json", inventory)

    _publish_exact(
        runner.RUNTIME_STATUS_ROOT / "production_run_evidence.json",
        _json_bytes(run_evidence),
    )
    _publish_exact(
        EXTERNAL_STATUS_ROOT / "production_validation_receipt.json",
        _json_bytes(validation),
    )
    _publish_exact(
        EXTERNAL_STATUS_ROOT / "production_activation_handoff.json",
        _json_bytes(handoff),
    )
    return {
        "activation_index": dict(combined_identity),
        "downstream_handoff": _artifact(
            DOC_OUTPUT_ROOT / "production_activation_handoff.json",
            repository_relative=True,
        ),
        "runtime_queue": queue_authority["runtime_queue"],
        "validation_receipt": _artifact(
            DOC_OUTPUT_ROOT / "production_validation_receipt.json",
            repository_relative=True,
        ),
    }


def main() -> int:
    if runner.RUN_ID != "mineocclude-run-ea6169430d693f8adcd16a23a62c4422":
        _fail("unexpected production run identity")
    # This hashes all pinned model assets but never loads a model or touches CUDA.
    runner._assets_preflight()
    authorities = _load_authorities()
    code_identity = _code_identity()
    collected = _validate_and_collect(authorities)
    run_evidence = _run_evidence(authorities, collected)
    combined_identity = _publish_combined(authorities, collected, code_identity)
    result = _publish_receipts(
        authorities,
        collected,
        code_identity,
        combined_identity,
        run_evidence,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
