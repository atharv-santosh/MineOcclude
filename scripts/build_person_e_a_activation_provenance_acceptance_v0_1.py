"""Accept the exact canonical Person A activation provenance for A6.6.

This is a bounded, additive Person E acceptance.  It verifies the committed
Person A bundle and its external copy, the Activation Store v2 index/chunks,
the direct pooling audit, and the exact join back to Person E's immutable
canonical post-C1 C6A registry.  It does not execute C6A or A6.6.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_REL = "docs/status/person_e_a_activation_provenance_acceptance_v0_1"
PACKAGE_DIR = ROOT / PACKAGE_REL

PERSON_E_PRIOR_AUTHORITY = "d76f2df885d6b0e2e6cc5ade7025e799030ecea1"
PERSON_A_COMMIT = "89c1949976f8b8db6efaace66fd2ada4d1b93b3d"
PERSON_A_RUNTIME_COMMIT = "aa3f38fc934095a2b83005b62513ef04d65053ab"
PERSON_C_COMMIT = "b810bae554ba4f31018d39beb304c9b936387ca4"

BUNDLE_NAME = (
    "person-a-canonical-c6a-layout-01-ep12602-seed-20260725-"
    "retry-20260804T193204Z-package-retry-20260804T193627Z"
)
BUNDLE_ROOT = Path("C:/Users/lollo/MineOcclude/docs/status/phase6_runtime") / BUNDLE_NAME
BUNDLE_GIT_REL = f"docs/status/phase6_runtime/{BUNDLE_NAME}"

OUTPUT_BUNDLE_SHA256 = "e03251f2a8e7f7546b354db411f801c0908739d5929e0a9475ee04ddc903b72b"
A_TO_E_HANDOFF_SHA256 = "7414956699d9d37f0b4b486b7c800ff2482b453ffd634cb2bf99d92bcb042cfe"
ACTIVATION_INDEX_SHA256 = "a6ba07a50ff20e9b90f0b036a0acd18783bad4fa3aacbebc0dd70df825f00a27"
ACCEPTED_MANIFEST_SHA256 = "e6716f4fbe015ebb098da2a6fb800c636cc9eac1a56dcbe1d7543ab377c7a40d"
BUNDLE_INVENTORY_SHA256 = "3f1365fc9957ab29691f523c0cdda24c680a5e27311e23f49eb0294af4015c24"

CANONICAL_C6A_ID = "person-c-c6a-post-c1-v0.1"
TRAJECTORY_ID = "layout_01_ep12602"
EPISODE_ID = 12602
ACTIVATION_ROW_COUNT = 1200
ACTIVATION_CHUNK_COUNT = 20
FRAME_COUNT = 60
LAYER_COUNT = 20
HIDDEN_WIDTH = 2048

PERSON_C_PACKAGE_SHA256 = "612b03fea372d10c5f5b87cb581dd5f993035112e16aa1de7341801bdc35a9ef"
PRIOR_E_HANDOFF_SHA256 = "e2897aac65a8b51893f1ef397af26cdc7958fe89e6d2bd0159082a9547d253d1"
PRIOR_E_REGISTRY_SHA256 = "77c105176bdb4d93382b36b3131267848acab6fbdc181f1d8272080e0ad5d588"
PRIOR_E_RECORD_ID = "person-e-c6a-person-c-c6a-post-c1-v0.1-episode-12602-v0.1"
PRIOR_E_RECORD_SHA256 = "366e5b1bec80c5ba3c014d22da9edace7e9eb5cfbc6700352acac28da387a642"
PRIOR_E_PACKAGE_REL = "docs/status/person_e_c6a_provenance_closure_v0_1"
PRIOR_E_INVENTORY_SHA256 = "cf4dfaf247effe73e4898e902302235e6982ab282e2b1b817c441ecea5ee1b9b"

MODEL_SHA256 = "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
MODEL_CONFIG_SHA256 = "e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018"
PREPROCESSING = (
    "mineworld_gradio_step_video_preprocessing@1.0:"
    "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
)
PREPROCESS_SHA256 = PREPROCESSING.rsplit(":", 1)[1]
ACTION_CONVERSION = (
    "mineworld_mcdataset_json_action_to_env_action@1.0:"
    "7e8d16db01f085481d41d340e5a0b84669b8e163f3338d5fd572731532c52746"
)
HOOK_SITE = "decoder_layer_output_residual_stream"
POOLING_METHOD = "mean"
TOKEN_REGION = "visual"
CAPTURE_PACKAGE_SHA256 = "e7ef5026dd170754fc7b2dd22bbb4893e5d47571111bdd3db8d021ffe62c6fa8"

RECEIPT_SCHEMA_VERSION = (
    "person-e-to-person-a-canonical-activation-provenance-receipt-v0.1"
)
VALIDATION_SCHEMA_VERSION = (
    "person-e-canonical-activation-provenance-validation-v0.1"
)
INVENTORY_SCHEMA_VERSION = (
    "person-e-canonical-activation-provenance-sha256-inventory-v0.1"
)
A6_6_STATEMENT = (
    "A6.6 may consume the activation provenance from this exact canonical "
    "Person A bundle. This receipt does not perform A6.6."
)


class AcceptanceError(RuntimeError):
    """Fail-closed provenance acceptance error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def canonical_json(document: Any) -> bytes:
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def load_json_bytes(raw: bytes, identity: str, *, canonical: bool = True) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key in {identity}: {key}")
            result[key] = value
        return result

    try:
        document = json.loads(raw, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"invalid JSON in {identity}: {exc}") from exc
    if canonical:
        require(canonical_json(document) == raw, f"noncanonical JSON: {identity}")
    return document


def load_json_file(path: Path) -> Any:
    return load_json_bytes(path.read_bytes(), str(path))


def git_bytes(commit: str, relative: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "show", f"{commit}:{relative}"],
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise AcceptanceError(
            f"missing Git object {commit}:{relative}: "
            f"{exc.stderr.decode('utf-8', errors='replace').strip()}"
        ) from exc


def git_text(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), *args], text=True, stderr=subprocess.PIPE
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise AcceptanceError(exc.stderr.strip()) from exc


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    require(not path.is_absolute(), f"absolute bundle inventory path: {value}")
    require(".." not in path.parts, f"escaping bundle inventory path: {value}")
    return path.as_posix()


def verify_bundle() -> dict[str, Any]:
    require(BUNDLE_ROOT.is_dir(), f"missing canonical Person A bundle: {BUNDLE_ROOT}")
    require(
        sha256_file(BUNDLE_ROOT / "output_bundle_manifest.json")[1]
        == OUTPUT_BUNDLE_SHA256,
        "Person A output bundle manifest hash mismatch",
    )
    inventory_path = BUNDLE_ROOT / "sha256_inventory.json"
    require(
        sha256_file(inventory_path)[1] == BUNDLE_INVENTORY_SHA256,
        "Person A bundle inventory hash mismatch",
    )
    inventory_raw = inventory_path.read_bytes()
    require(
        git_bytes(PERSON_A_COMMIT, f"{BUNDLE_GIT_REL}/sha256_inventory.json")
        == inventory_raw,
        "Person A bundle inventory is not the exact producing-commit object",
    )
    inventory = load_json_bytes(inventory_raw, str(inventory_path))
    require(
        inventory.get("schema_version")
        == "person-a-canonical-sagemaker-output-sha256-inventory-v0.1",
        "Person A bundle inventory schema mismatch",
    )
    rows = inventory.get("files")
    require(isinstance(rows, list) and len(rows) == 36, "bundle inventory count mismatch")
    paths = [safe_relative(row["path"]) for row in rows]
    require(len(paths) == len(set(paths)), "duplicate bundle inventory path")
    actual_paths = {
        path.relative_to(BUNDLE_ROOT).as_posix()
        for path in BUNDLE_ROOT.rglob("*")
        if path.is_file()
    }
    require(
        actual_paths == set(paths) | {"sha256_inventory.json"},
        "Person A bundle filesystem inventory mismatch",
    )
    for row, relative in zip(rows, paths, strict=True):
        path = BUNDLE_ROOT / Path(relative)
        size, digest = sha256_file(path)
        require(size == row["size_bytes"], f"bundle size mismatch: {relative}")
        require(digest == row["sha256"], f"bundle hash mismatch: {relative}")
        committed = git_bytes(PERSON_A_COMMIT, f"{BUNDLE_GIT_REL}/{relative}")
        require(len(committed) == size, f"Person A Git-object size mismatch: {relative}")
        require(
            sha256_bytes(committed) == digest,
            f"Person A Git-object hash mismatch: {relative}",
        )
        if relative.endswith(".json"):
            load_json_bytes(path.read_bytes(), str(path))

    require(
        git_text("rev-parse", f"{PERSON_A_COMMIT}^") == PERSON_A_RUNTIME_COMMIT,
        "Person A result commit is not based on the runtime-producing commit",
    )
    output = load_json_file(BUNDLE_ROOT / "output_bundle_manifest.json")
    require(output["status"] == "READY_FOR_LOCAL_RETRIEVAL", "bundle is not ready")
    require(output["trajectory_id"] == TRAJECTORY_ID, "bundle trajectory mismatch")
    require(output["episode_id"] == EPISODE_ID, "bundle episode mismatch")
    require(
        output["activation_chunk_count"] == ACTIVATION_CHUNK_COUNT,
        "bundle chunk count mismatch",
    )
    return {"inventory": inventory, "output": output}


def verify_prior_e_authority() -> tuple[dict[str, Any], dict[str, Any]]:
    tree = git_text(
        "ls-tree", "-r", "--name-only", PERSON_E_PRIOR_AUTHORITY, PRIOR_E_PACKAGE_REL
    ).splitlines()
    current = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / PRIOR_E_PACKAGE_REL).rglob("*")
        if path.is_file()
    }
    require(set(tree) == current, "historical Person E package file set changed")
    for relative in tree:
        require(
            (ROOT / relative).read_bytes() == git_bytes(PERSON_E_PRIOR_AUTHORITY, relative),
            f"historical Person E record changed: {relative}",
        )
    prior_inventory = ROOT / PRIOR_E_PACKAGE_REL / "sha256_inventory.json"
    require(
        sha256_file(prior_inventory)[1] == PRIOR_E_INVENTORY_SHA256,
        "historical Person E inventory hash mismatch",
    )
    handoff_path = (
        ROOT / PRIOR_E_PACKAGE_REL / "person_e_to_person_a_c6a_provenance_handoff.json"
    )
    require(
        sha256_file(handoff_path)[1] == PRIOR_E_HANDOFF_SHA256,
        "historical Person E handoff hash mismatch",
    )
    registry_path = ROOT / PRIOR_E_PACKAGE_REL / "canonical_registry_records.json"
    require(
        sha256_file(registry_path)[1] == PRIOR_E_REGISTRY_SHA256,
        "historical Person E registry hash mismatch",
    )
    prior_handoff = load_json_file(handoff_path)
    registry = load_json_file(registry_path)
    require(prior_handoff["canonical_c6a_id"] == CANONICAL_C6A_ID, "prior C6A mismatch")
    require(
        prior_handoff["a6_6_provenance_consumption_authorized"] is True,
        "prior Person E handoff does not authorize A6.6 provenance consumption",
    )
    records = [row for row in registry["records"] if row["episode_id"] == EPISODE_ID]
    require(len(records) == 1, "canonical registry episode identity is not unique")
    record = records[0]
    require(record["registry_record_id"] == PRIOR_E_RECORD_ID, "registry record ID mismatch")
    require(record["canonical_c6a_id"] == CANONICAL_C6A_ID, "record C6A identity mismatch")
    require(record["record_status"] == "accepted", "registry record is not accepted")
    require(
        sha256_bytes(canonical_json(record)) == PRIOR_E_RECORD_SHA256,
        "registry record hash mismatch",
    )
    return prior_handoff, record


def verify_handoff_and_manifest(record: dict[str, Any]) -> dict[str, Any]:
    handoff_path = BUNDLE_ROOT / "person_a_to_person_e_canonical_provenance_handoff.json"
    manifest_path = BUNDLE_ROOT / "accepted_pilot_manifest.json"
    require(sha256_file(handoff_path)[1] == A_TO_E_HANDOFF_SHA256, "A-to-E handoff hash mismatch")
    require(
        sha256_file(manifest_path)[1] == ACCEPTED_MANIFEST_SHA256,
        "accepted manifest hash mismatch",
    )
    handoff = load_json_file(handoff_path)
    manifest = load_json_file(manifest_path)
    require(
        handoff["schema_version"]
        == "person-a-to-person-e-canonical-provenance-handoff-v0.1",
        "A-to-E handoff schema mismatch",
    )
    require(
        handoff["status"] == "READY_FOR_PERSON_E_PROVENANCE_CONSUMPTION",
        "A-to-E handoff status mismatch",
    )
    require(
        manifest["schema_version"] == "person-a-canonical-pilot-accepted-manifest-v0.1",
        "accepted manifest schema mismatch",
    )
    require(
        manifest["status"] == "ACCEPTED_FOR_FROZEN_A6_1_TO_A6_5",
        "accepted manifest status mismatch",
    )
    for document in (handoff, manifest):
        require(document["canonical_c6a_id"] == CANONICAL_C6A_ID, "canonical C6A mismatch")
    require(handoff["trajectory_id"] == TRAJECTORY_ID, "handoff trajectory mismatch")
    require(handoff["episode_id"] == EPISODE_ID, "handoff episode mismatch")
    require(manifest["selected_trajectory_id"] == TRAJECTORY_ID, "manifest trajectory mismatch")
    require(manifest["selected_episode_id"] == EPISODE_ID, "manifest episode mismatch")
    require(manifest["accepted_pilot_count"] == 1, "accepted pilot cardinality mismatch")
    require(handoff["expected_activation_row_count"] == ACTIVATION_ROW_COUNT, "row count mismatch")
    require(handoff["accepted_manifest"]["sha256"] == ACCEPTED_MANIFEST_SHA256, "manifest binding mismatch")
    require(handoff["person_c"] == {"commit": PERSON_C_COMMIT, "package_sha256": PERSON_C_PACKAGE_SHA256}, "Person C binding mismatch")
    require(manifest["person_c"]["commit"] == PERSON_C_COMMIT, "manifest Person C commit mismatch")
    require(manifest["person_c"]["package_sha256"] == PERSON_C_PACKAGE_SHA256, "manifest Person C package mismatch")
    expected_e = {
        "handoff_sha256": PRIOR_E_HANDOFF_SHA256,
        "registry_record_id": PRIOR_E_RECORD_ID,
        "registry_record_sha256": PRIOR_E_RECORD_SHA256,
    }
    require(handoff["person_e_source"] == expected_e, "handoff Person E source mismatch")
    require(
        {key: manifest["person_e"][key] for key in expected_e} == expected_e,
        "manifest Person E source mismatch",
    )
    require(
        manifest["episode_artifact_manifest"]["sha256"] == PRIOR_E_REGISTRY_SHA256,
        "manifest canonical registry binding mismatch",
    )
    require(
        manifest["direct_episode_artifacts"] == record["outputs"]
        and handoff["direct_episode_artifacts"] == record["outputs"],
        "direct Person C source artifacts do not join exactly to Person E registry",
    )
    require(len(record["outputs"]) == 67, "direct source artifact count mismatch")

    expected_identities = {
        "action_conversion": ACTION_CONVERSION,
        "activation_index_format": "person-a-activation-index-v2",
        "activation_store_format": "person-a-activation-store-v2",
        "hook_site": HOOK_SITE,
        "pooling_method": POOLING_METHOD,
        "preprocessing": PREPROCESSING,
        "token_region": TOKEN_REGION,
    }
    require(manifest["expected_identities"] == expected_identities, "manifest identities mismatch")
    require(
        {key: handoff["identities"][key] for key in expected_identities}
        == expected_identities,
        "handoff pipeline identities mismatch",
    )
    require(handoff["identities"]["model_sha256"] == MODEL_SHA256, "model hash mismatch")
    require(
        handoff["identities"]["model_config_sha256"] == MODEL_CONFIG_SHA256,
        "model config hash mismatch",
    )
    return {"handoff": handoff, "manifest": manifest}


def verify_activation_index_and_chunks(handoff: dict[str, Any]) -> dict[str, Any]:
    artifacts = handoff["activation_artifacts"]
    chunks = [row for row in artifacts if row["type"] == "activation_chunk"]
    indexes = [row for row in artifacts if row["type"] == "activation_index"]
    require(len(chunks) == ACTIVATION_CHUNK_COUNT, "handoff activation chunk count mismatch")
    require(len(indexes) == 1, "handoff activation index count mismatch")
    index_path = BUNDLE_ROOT / "activation_store" / "indexes" / Path(indexes[0]["path"]).name
    index_size, index_hash = sha256_file(index_path)
    require(index_hash == ACTIVATION_INDEX_SHA256, "activation index hash mismatch")
    require(indexes[0]["sha256"] == index_hash, "handoff activation index hash mismatch")
    require(indexes[0]["byte_size"] == index_size, "handoff activation index size mismatch")
    index = load_json_file(index_path)
    require(index["format_version"] == "person-a-activation-index-v2", "index format mismatch")
    require(index["run_status"] == "completed", "activation run is not completed")
    require(len(index["chunks"]) == ACTIVATION_CHUNK_COUNT, "index chunk count mismatch")
    require(len(index["index_rows"]) == ACTIVATION_ROW_COUNT, "activation row count mismatch")
    store = index["store_identity"]
    required_store = {
        "accepted_manifest_hash": CAPTURE_PACKAGE_SHA256,
        "checkpoint_hash": MODEL_SHA256,
        "code_sha": PERSON_A_RUNTIME_COMMIT,
        "dtype": "float32",
        "format_version": "person-a-activation-store-v2",
        "hidden_width": HIDDEN_WIDTH,
        "hook_site": HOOK_SITE,
        "model_hash": MODEL_SHA256,
        "preprocess_hash": PREPROCESS_SHA256,
        "requested_layers": list(range(LAYER_COUNT)),
    }
    for key, value in required_store.items():
        require(store.get(key) == value, f"activation store identity mismatch: {key}")
    require(store["run_id"] == index["index_rows"][0]["run_id"], "run ID mismatch")

    handoff_chunks = {Path(row["path"]).name: row for row in chunks}
    index_chunk_names = {Path(row["path"]).name for row in index["chunks"]}
    require(set(handoff_chunks) == index_chunk_names, "chunk inventory join mismatch")
    chunk_receipts = []
    layer_to_chunk: dict[int, str] = {}
    for row in index["chunks"]:
        name = Path(row["path"]).name
        local = BUNDLE_ROOT / "activation_store" / "chunks" / name
        size, digest = sha256_file(local)
        handed = handoff_chunks[name]
        require(size == row["byte_size"] == handed["byte_size"], f"chunk size mismatch: {name}")
        require(digest == row["sha256"] == handed["sha256"], f"chunk hash mismatch: {name}")
        require(row["row_count"] == FRAME_COUNT, f"chunk row count mismatch: {name}")
        require(row["hidden_width"] == HIDDEN_WIDTH, f"chunk width mismatch: {name}")
        require(row["dtype"] == "float32", f"chunk dtype metadata mismatch: {name}")
        layer = row["layer_idx"]
        require(layer not in layer_to_chunk, f"duplicate activation layer: {layer}")
        layer_to_chunk[layer] = row["chunk_id"]
        array = np.load(local, mmap_mode="r", allow_pickle=False)
        require(array.shape == (FRAME_COUNT, HIDDEN_WIDTH), f"chunk shape mismatch: {name}")
        require(array.dtype == np.dtype("float32"), f"chunk dtype mismatch: {name}")
        require(bool(np.isfinite(array).all()), f"nonfinite activation value: {name}")
        chunk_receipts.append(
            {
                "byte_size": size,
                "layer_idx": layer,
                "path": str(local.resolve()),
                "row_count": row["row_count"],
                "sha256": digest,
            }
        )
    require(set(layer_to_chunk) == set(range(LAYER_COUNT)), "activation layer coverage mismatch")

    seen: set[tuple[int, int]] = set()
    frame_map_rows: dict[int, str] = {}
    state_rows: dict[int, str] = {}
    joins = handoff["exact_source_identity_joins"]
    for row in index["index_rows"]:
        frame = row["global_model_frame_idx"]
        layer = row["layer_idx"]
        identity = (frame, layer)
        require(identity not in seen, f"duplicate activation identity: {identity}")
        seen.add(identity)
        require(row["source_frame_idx"] == frame == row["source_tick"], "source frame/tick mismatch")
        require(row["source_frame_id"] == f"{TRAJECTORY_ID}:render_frame:{frame}", "source frame ID mismatch")
        require(row["trajectory_id"] == TRAJECTORY_ID, "row trajectory mismatch")
        require(row["activation_chunk_id"] == layer_to_chunk[layer], "row-to-chunk join mismatch")
        require(row["chunk_row_idx"] == frame, "chunk row identity mismatch")
        require(row["status"] == "accepted" and row["run_status"] == "completed", "row status mismatch")
        require(row["exclusion_reason"] is None and row["superseded_by"] is None, "row is excluded or superseded")
        exact = {
            "accepted_manifest_hash": CAPTURE_PACKAGE_SHA256,
            "checkpoint_hash": MODEL_SHA256,
            "code_sha": PERSON_A_RUNTIME_COMMIT,
            "dtype": "float32",
            "hook_site": HOOK_SITE,
            "model_hash": MODEL_SHA256,
            "pooling_method": POOLING_METHOD,
            "preprocess_hash": PREPROCESS_SHA256,
            "store_format_version": "person-a-activation-store-v2",
            "token_region": TOKEN_REGION,
            "vector_shape": [HIDDEN_WIDTH],
        }
        for key, value in exact.items():
            require(row.get(key) == value, f"activation row identity mismatch: {key}")
        require(row["c_frame_map_sha256"] == joins["c_frame_map_source_sha256"], "frame-map source hash mismatch")
        require(row["c_state_sha256"] == joins["c_server_state_source_sha256"], "server-state source hash mismatch")
        frame_map_rows.setdefault(frame, row["c_frame_map_row_sha256"])
        state_rows.setdefault(frame, row["c_state_row_sha256"])
        require(frame_map_rows[frame] == row["c_frame_map_row_sha256"], "frame-map row join differs across layers")
        require(state_rows[frame] == row["c_state_row_sha256"], "state row join differs across layers")
    require(seen == {(frame, layer) for frame in range(FRAME_COUNT) for layer in range(LAYER_COUNT)}, "activation frame/layer coverage mismatch")
    require(len(set(frame_map_rows.values())) == FRAME_COUNT, "frame-map row identities are not unique")
    require(len(set(state_rows.values())) == FRAME_COUNT, "state row identities are not unique")
    require(joins["status"] == "PASS" and joins["failure_count"] == 0, "source identity join did not pass")
    return {
        "chunks": sorted(chunk_receipts, key=lambda row: row["layer_idx"]),
        "index_byte_size": index_size,
        "index_path": str(index_path.resolve()),
        "source_frame_map_sha256": joins["c_frame_map_source_sha256"],
        "source_server_state_sha256": joins["c_server_state_source_sha256"],
    }


def verify_audits(handoff: dict[str, Any]) -> dict[str, Any]:
    bounded = {row["type"]: row for row in handoff["bounded_unpooled_audit_artifacts"]}
    require(set(bounded) == {"bounded_unpooled_activation", "bounded_unpooled_manifest"}, "bounded audit artifact inventory mismatch")
    artifact_path = BUNDLE_ROOT / "bounded_audit" / "limited_unpooled_frame_0.npz"
    manifest_path = BUNDLE_ROOT / "bounded_audit" / "limited_unpooled_frame_0.manifest.json"
    for kind, path in (
        ("bounded_unpooled_activation", artifact_path),
        ("bounded_unpooled_manifest", manifest_path),
    ):
        size, digest = sha256_file(path)
        require(size == bounded[kind]["byte_size"], f"{kind} size mismatch")
        require(digest == bounded[kind]["sha256"], f"{kind} hash mismatch")
    manifest = load_json_file(manifest_path)
    require(manifest["status"] == "PASS", "bounded audit manifest did not pass")
    require(manifest["scientific_identity"] == {"hook_site": HOOK_SITE, "model_frame_idx": 0, "trajectory_id": TRAJECTORY_ID}, "bounded audit scientific identity mismatch")
    provenance = manifest["provenance"]
    require(provenance["main_checkpoint_sha256"] == MODEL_SHA256, "audit model hash mismatch")
    require(provenance["model_config_sha256"] == MODEL_CONFIG_SHA256, "audit model config mismatch")
    require(provenance["preprocessing_profile"] == PREPROCESSING, "audit preprocessing mismatch")
    require(provenance["action_conversion_profile"] == ACTION_CONVERSION, "audit action conversion mismatch")
    audit = manifest["pooling_audit"]
    require(audit["status"] == "PASS", "direct pooling audit did not pass")
    require(audit["exact_candidate_binding"]["all_layers_match"] is True, "candidate pooling binding mismatch")
    require(audit["token_reproduction"]["status"] == "PASS", "pooling token reproduction did not pass")
    with np.load(artifact_path, allow_pickle=False) as arrays:
        require(set(arrays.files) == {"token_values", "pooled_means", "layer_indices", "visual_positions"}, "bounded audit array inventory mismatch")
        tokens = arrays["token_values"]
        pooled = arrays["pooled_means"]
        layers = arrays["layer_indices"]
        positions = arrays["visual_positions"]
        require(tokens.shape == (LAYER_COUNT, 336, HIDDEN_WIDTH), "unpooled token shape mismatch")
        require(tokens.dtype == np.dtype("float16"), "unpooled token dtype mismatch")
        require(pooled.shape == (LAYER_COUNT, HIDDEN_WIDTH), "stored pooling shape mismatch")
        require(pooled.dtype == np.dtype("float32"), "stored pooling dtype mismatch")
        require(np.array_equal(layers, np.arange(LAYER_COUNT)), "audit layer identities mismatch")
        require(np.array_equal(positions, np.arange(336)), "audit visual positions mismatch")
        recomputed = tokens.astype(np.float32).mean(axis=1)
        token_audit = audit["token_reproduction"]
        require(
            bool(np.allclose(recomputed, pooled, rtol=token_audit["rtol"], atol=token_audit["atol"])),
            "direct pooling recomputation mismatch",
        )
        require(
            float(np.max(np.abs(recomputed - pooled)))
            <= token_audit["maximum_absolute_difference"] + 1e-12,
            "direct pooling maximum difference exceeds receipt",
        )
        layer_records = audit["layer_records"]
        require(len(layer_records) == LAYER_COUNT, "pooling layer audit count mismatch")
        for layer, row in enumerate(layer_records):
            require(row["layer_idx"] == layer and row["allclose"] is True, "pooling layer status mismatch")
            require(row["candidate_binding_sha256_equal"] is True, "pooling candidate binding failed")
            stored_hash = sha256_bytes(np.ascontiguousarray(pooled[layer]).tobytes())
            require(stored_hash == row["stored_pooled_sha256"] == row["candidate_sha256"], "stored pooled vector hash mismatch")

    step6_4 = load_json_file(BUNDLE_ROOT / "step6_4.json")
    step6_5 = load_json_file(BUNDLE_ROOT / "step6_5.json")
    terminal = load_json_file(BUNDLE_ROOT / "terminal_execution_receipt.json")
    final = load_json_file(BUNDLE_ROOT / "final_report.json")
    require(step6_4["status"] == "PASS" and step6_4["result"]["status"] == "PASS", "Step 6.4 did not pass")
    require(step6_5["status"] == "PASS" and step6_5["result"]["status"] == "PASS", "Step 6.5 did not pass")
    require(step6_5["result"]["direct_pooling_audit"] == "PASS", "Step 6.5 direct pooling did not pass")
    require(step6_5["result"]["source_identity_join_failure_count"] == 0, "Step 6.5 source join failed")
    repeatability = handoff["repeatability_validation"]
    require(repeatability["status"] == "PASS", "handoff repeatability did not pass")
    require(repeatability["maximum_absolute_difference"] == 0.0, "repeatability is not exact")
    require(step6_4["result"]["repeatability_maximum_absolute_difference"] == 0.0, "Step 6.4 repeatability mismatch")
    require(step6_5["result"]["repeatability_maximum_absolute_difference"] == 0.0, "Step 6.5 repeatability mismatch")
    require(terminal["direct_pooling_validation"] == "PASS", "terminal pooling status mismatch")
    require(terminal["repeatability_validation"] == "PASS", "terminal repeatability status mismatch")
    require(terminal["source_identity_joins"] == "PASS", "terminal source join status mismatch")
    require(final["status"] == "PASS" and final["selected_pilot"] == TRAJECTORY_ID, "final report identity mismatch")
    require(final["handoff"]["e_facing_handoff"]["sha256"] == A_TO_E_HANDOFF_SHA256, "final report handoff hash mismatch")
    preflight = load_json_file(BUNDLE_ROOT / "runtime_preflight_receipt.json")
    require(preflight["status"] == "PASS", "runtime preflight did not pass")
    require(preflight["git_commit"] == PERSON_A_RUNTIME_COMMIT, "runtime producer commit mismatch")
    require(preflight["frozen_file_sha256"]["main_checkpoint"] == MODEL_SHA256, "preflight model mismatch")
    require(preflight["model_config_physical_sha256"] == MODEL_CONFIG_SHA256, "preflight model config mismatch")
    require(preflight["canonical_authority"]["canonical_c6a_id"] == CANONICAL_C6A_ID, "preflight C6A mismatch")
    return {
        "bounded_manifest_path": str(manifest_path.resolve()),
        "bounded_manifest_sha256": sha256_file(manifest_path)[1],
        "bounded_npz_path": str(artifact_path.resolve()),
        "bounded_npz_sha256": sha256_file(artifact_path)[1],
        "maximum_repeatability_difference": 0.0,
    }


def receipt_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "properties": {
            "a6_6_performed": {"const": False},
            "a6_6_provenance_consumption_authorized": {"const": True},
            "a6_6_provenance_consumption_statement": {"const": A6_6_STATEMENT},
            "activation_provenance": {"type": "object"},
            "canonical_c6a_binding": {"type": "object"},
            "historical_preservation": {"type": "object"},
            "immutable": {"const": True},
            "person_a_result": {"type": "object"},
            "receipt_id": {"const": "person-e-to-person-a-layout-01-ep12602-activation-provenance-v0.1"},
            "schema_version": {"const": RECEIPT_SCHEMA_VERSION},
            "status": {"const": "READY_FOR_A6_6_PROVENANCE_CONSUMPTION"},
            "unresolved_blockers": {"maxItems": 0, "type": "array"},
            "validation": {"type": "object"},
        },
        "required": [
            "a6_6_performed",
            "a6_6_provenance_consumption_authorized",
            "a6_6_provenance_consumption_statement",
            "activation_provenance",
            "canonical_c6a_binding",
            "historical_preservation",
            "immutable",
            "person_a_result",
            "receipt_id",
            "schema_version",
            "status",
            "unresolved_blockers",
            "validation",
        ],
        "title": "Person E to Person A canonical activation provenance receipt",
        "type": "object",
    }


def validate_receipt_schema(receipt: dict[str, Any], schema: dict[str, Any]) -> None:
    require(schema["type"] == "object", "receipt schema root type mismatch")
    require(set(receipt) == set(schema["required"]), "receipt top-level schema mismatch")
    for key, rule in schema["properties"].items():
        value = receipt[key]
        if "const" in rule:
            require(value == rule["const"], f"receipt schema const mismatch: {key}")
        if rule.get("type") == "object":
            require(isinstance(value, dict), f"receipt schema object mismatch: {key}")
        if rule.get("type") == "array":
            require(isinstance(value, list), f"receipt schema array mismatch: {key}")
            require(len(value) <= rule.get("maxItems", len(value)), f"receipt array too long: {key}")


def generate(out_dir: Path | None = None) -> dict[str, bytes]:
    bundle = verify_bundle()
    prior_handoff, record = verify_prior_e_authority()
    provenance = verify_handoff_and_manifest(record)
    activation = verify_activation_index_and_chunks(provenance["handoff"])
    audits = verify_audits(provenance["handoff"])

    schema = receipt_schema()
    receipt = {
        "a6_6_performed": False,
        "a6_6_provenance_consumption_authorized": True,
        "a6_6_provenance_consumption_statement": A6_6_STATEMENT,
        "activation_provenance": {
            "activation_chunk_count": ACTIVATION_CHUNK_COUNT,
            "activation_chunks": activation["chunks"],
            "activation_index": {
                "byte_size": activation["index_byte_size"],
                "path": activation["index_path"],
                "sha256": ACTIVATION_INDEX_SHA256,
            },
            "activation_row_count": ACTIVATION_ROW_COUNT,
            "action_conversion": ACTION_CONVERSION,
            "direct_pooling_audit": audits,
            "hook_site": HOOK_SITE,
            "model_config_sha256": MODEL_CONFIG_SHA256,
            "model_sha256": MODEL_SHA256,
            "pooling_method": POOLING_METHOD,
            "preprocessing": PREPROCESSING,
            "repeatability": {
                "atol": provenance["handoff"]["repeatability_validation"]["atol"],
                "maximum_absolute_difference": audits["maximum_repeatability_difference"],
                "rtol": provenance["handoff"]["repeatability_validation"]["rtol"],
                "status": "PASS",
            },
            "source_identity_join": {
                "failure_count": 0,
                "frame_map_sha256": activation["source_frame_map_sha256"],
                "server_state_sha256": activation["source_server_state_sha256"],
                "status": "PASS",
            },
            "storage_format": "person-a-activation-store-v2",
            "token_region": TOKEN_REGION,
        },
        "canonical_c6a_binding": {
            "canonical_c6a_id": CANONICAL_C6A_ID,
            "episode_id": EPISODE_ID,
            "person_c_commit": PERSON_C_COMMIT,
            "person_c_package_sha256": PERSON_C_PACKAGE_SHA256,
            "person_e_c6a_handoff_sha256": PRIOR_E_HANDOFF_SHA256,
            "person_e_registry_record_id": PRIOR_E_RECORD_ID,
            "person_e_registry_record_sha256": PRIOR_E_RECORD_SHA256,
            "person_e_registry_sha256": PRIOR_E_REGISTRY_SHA256,
            "trajectory_id": TRAJECTORY_ID,
        },
        "historical_preservation": {
            "existing_person_e_records_modified": False,
            "person_e_prior_authority_commit": PERSON_E_PRIOR_AUTHORITY,
            "prior_c6a_handoff_status": prior_handoff["status"],
            "prior_c6a_package_inventory_sha256": PRIOR_E_INVENTORY_SHA256,
            "prior_c6a_records_modified": False,
        },
        "immutable": True,
        "person_a_result": {
            "accepted_manifest_sha256": ACCEPTED_MANIFEST_SHA256,
            "a_to_e_handoff_sha256": A_TO_E_HANDOFF_SHA256,
            "bundle_inventory_sha256": BUNDLE_INVENTORY_SHA256,
            "canonical_result_commit": PERSON_A_COMMIT,
            "output_bundle_manifest_path": str((BUNDLE_ROOT / "output_bundle_manifest.json").resolve()),
            "output_bundle_sha256": OUTPUT_BUNDLE_SHA256,
            "producing_runtime_commit": PERSON_A_RUNTIME_COMMIT,
            "verified_bundle_root": str(BUNDLE_ROOT.resolve()),
        },
        "receipt_id": "person-e-to-person-a-layout-01-ep12602-activation-provenance-v0.1",
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "READY_FOR_A6_6_PROVENANCE_CONSUMPTION",
        "unresolved_blockers": [],
        "validation": {
            "a_output_bundle_valid": True,
            "a_to_e_handoff_valid": True,
            "accepted_manifest_valid": True,
            "activation_chunks_valid": True,
            "activation_index_valid": True,
            "direct_pooling_audit_valid": True,
            "model_and_pipeline_identities_valid": True,
            "repeatability_valid": True,
            "source_identity_join_valid": True,
        },
    }
    validate_receipt_schema(receipt, schema)
    validation = {
        **receipt["validation"],
        "a6_6_provenance_consumption_authorized": True,
        "activation_chunk_count": ACTIVATION_CHUNK_COUNT,
        "activation_row_count": ACTIVATION_ROW_COUNT,
        "canonical_c6a_id": CANONICAL_C6A_ID,
        "historical_person_e_records_unchanged": True,
        "person_a_commit_valid": True,
        "receipt_schema_valid": True,
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "status": "PASS",
        "unresolved_blockers": [],
    }
    files = {
        "person_e_to_person_a_activation_provenance_receipt.json": canonical_json(receipt),
        "person_e_to_person_a_activation_provenance_receipt.schema.json": canonical_json(schema),
        "validation_receipt.json": canonical_json(validation),
    }
    inventory_rows = [
        {
            "path": relative,
            "sha256": sha256_bytes(data),
            "size_bytes": len(data),
        }
        for relative, data in sorted(files.items())
    ]
    files["sha256_inventory.json"] = canonical_json(
        {
            "file_count": len(files) + 1,
            "files": inventory_rows,
            "hash_algorithm": "sha256",
            "hash_source": "literal_file_bytes",
            "inventory_excludes_self": True,
            "schema_version": INVENTORY_SCHEMA_VERSION,
        }
    )
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for relative, data in files.items():
            (out_dir / relative).write_bytes(data)
    return files


def validate_package(package_dir: Path) -> None:
    expected = generate()
    present = (
        {path.name for path in package_dir.iterdir() if path.is_file()}
        if package_dir.is_dir()
        else set()
    )
    require(present == set(expected), "acceptance package file inventory mismatch")
    for relative, expected_bytes in expected.items():
        actual = (package_dir / relative).read_bytes()
        require(actual == expected_bytes, f"acceptance package byte drift: {relative}")
    schema = load_json_file(
        package_dir / "person_e_to_person_a_activation_provenance_receipt.schema.json"
    )
    receipt = load_json_file(
        package_dir / "person_e_to_person_a_activation_provenance_receipt.json"
    )
    validate_receipt_schema(receipt, schema)
    inventory = load_json_file(package_dir / "sha256_inventory.json")
    require(inventory["file_count"] == len(expected), "receipt inventory count mismatch")
    for row in inventory["files"]:
        size, digest = sha256_file(package_dir / row["path"])
        require(size == row["size_bytes"], f"receipt inventory size mismatch: {row['path']}")
        require(digest == row["sha256"], f"receipt inventory hash mismatch: {row['path']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--out-dir", type=Path, default=PACKAGE_DIR)
    args = parser.parse_args()
    try:
        if args.mode == "build":
            files = generate(args.out_dir)
            receipt_hash = sha256_bytes(
                files["person_e_to_person_a_activation_provenance_receipt.json"]
            )
            print(
                "BUILD OK: canonical Person A activation provenance accepted; "
                f"receipt_sha256={receipt_hash}"
            )
        else:
            validate_package(args.out_dir)
            print("VALIDATE OK: exact Person E to Person A activation provenance receipt")
    except (AcceptanceError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"FAIL-CLOSED: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
