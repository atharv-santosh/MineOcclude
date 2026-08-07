"""Complete Person A's local 66-cell preparation before any GPU transfer.

This builder consumes Person C's C7.5 handoff at an exact commit, hash-verifies
the episode payloads on the Windows preparation host, materializes the real
production frame maps keyed by (trajectory_id, model_frame_idx), publishes the
Person A 66-cell accepted-input manifest that the Step 7.2 matrix and Step 7.5
queue consume, records the storage-dtype reconciliation, and prepares the
byte-transport plan.

It never loads model weights, never extracts activations, and never authorizes
Phase 6.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

SCHEMA_VERSION = "1.0"
SCHEMA_PREFIX = "person-a-66-cell-local-preparation-v0.1"
BUILDER_PATH = "scripts/build_person_a_66_cell_local_preparation_v0_1.py"
TEST_PATH = "tests/models/test_person_a_66_cell_local_preparation_v0_1.py"

A_BRANCH = "role/person-a-model"
A_STARTING_AUTHORITY = "f8c99df5724ac8756d45f224a7d54b1380aed73b"

C_COMMIT = "a8bed8adf7e24ca7fe5b6b6afa3342da61434be3"
C_REMOTE_REF = "origin/role/person-c-data"
C_PACKAGE_ROOT = "docs/status/person_c_c7_mvp_handoff_v0_1"
C_ACCEPTED_MANIFEST_PATH = f"{C_PACKAGE_ROOT}/trajectories_mvp_manifest.json"
C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
C_INVENTORY_PATH = f"{C_PACKAGE_ROOT}/sha256_inventory.json"

FIRST_EPISODE = 12601
LAST_EPISODE = 12666
EXPECTED_TRAJECTORY_COUNT = 66
EXPECTED_MODEL_FRAME_KEY_COUNT = 2468
LAYER_COUNT = 20

MINEWORLD_SOURCE_ROOT = Path(r"C:\Users\lollo\MineWorld-Upstream")
PINNED_MINEWORLD_REVISION = "9f49efbcc68a5f0cf60e78f0abc566eac409282f"

# Person A production data package (frame maps + accepted-input manifest).
DATA_ROOT = ROOT / "data" / "handoff_a" / "person_a_66_cell_production_input_v0_1"
DATA_ROOT_REL = "data/handoff_a/person_a_66_cell_production_input_v0_1"

# Person A preparation receipts.
STATUS_ROOT = ROOT / "docs" / "status" / "person_a_66_cell_local_preparation_v0_1"
STATUS_ROOT_REL = "docs/status/person_a_66_cell_local_preparation_v0_1"

FRAME_MAP_SCHEMA_ID = f"{SCHEMA_PREFIX}-production-frame-map"
FRAME_MAP_ROW_FIELDS = (
    "trajectory_id",
    "model_frame_idx",
    "episode_id",
    "layout_id",
    "planned_cell_id",
    "set_id",
    "control_type",
    "server_tick",
    "render_frame_idx",
    "action_idx",
    "source_frame_role",
    "source_frame_runtime_path",
    "source_frame_sha256",
    "source_frame_byte_size",
    "source_client_tick_row_sha256",
    "source_raw_action_row_sha256",
    "source_server_state_row_sha256",
    "raw_action_identity_sha256",
    "normalized_action_sha256",
    "action_token_sha256",
    "action_tokens",
    "action_is_noop",
    "geometric_visible",
    "visibility_identity_sha256",
    "visibility_source",
    "detector_visibility_status",
    "condition_identity_sha256",
    "c_bundle_sha256",
    "c_manifest_sha256",
    "c_source_commit",
    "preprocessing_identity",
    "action_converter_identity",
    "frame_map_schema_version",
)

MODEL_FACING_KEY = ("trajectory_id", "model_frame_idx")

PREPROCESSING_IDENTITY = "person-a-bgr2rgb-inter-linear-224x384-v1.0"
PREPROCESSING_PROFILE = (
    "mineworld_gradio_step_video_preprocessing@1.0:"
    "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
)
ACTION_CONVERTER_IDENTITY = (
    "mineworld_action_compatibility@1.0:"
    "7e8d16db01f085481d41d340e5a0b84669b8e163f3338d5fd572731532c52746"
)

DETECTOR_VISIBILITY_STATUS = "produced_downstream_not_at_c6a_raw_capture_layer"
GEOMETRIC_VISIBILITY_SOURCE = "server_state.geometric_visible"


class PreparationError(RuntimeError):
    """Raised when local preparation cannot proceed on authoritative evidence."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> None:
    raise PreparationError(code, message)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def _completed(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, cwd=ROOT, check=False, capture_output=True)


def _git_text(*arguments: str) -> str:
    result = _completed(["git", *arguments])
    if result.returncode != 0:
        raise PreparationError(
            "git_failed", result.stderr.decode("utf-8", errors="replace").strip()
        )
    return result.stdout.decode("utf-8").strip()


def _git_bytes(commit: str, path: str) -> bytes:
    result = _completed(["git", "show", f"{commit}:{path}"])
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        _fail("git_object_missing", f"{commit}:{path}: {detail}")
    return result.stdout


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256(_canonical_bytes(value))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) + b"\n" for row in rows)


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    payload = path.read_bytes()
    rows: list[dict[str, Any]] = []
    for line in payload.decode("utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            _fail("invalid_stream_row", f"{path.name} contains a non-object row")
        rows.append(row)
    return rows, payload


def _load_canonical_raw_action_mapper() -> Any:
    """Reuse the repository's existing capture-action to MineWorld mapping."""

    path = ROOT / "scripts" / "run_person_a_phase6_single_pilot_sagemaker.py"
    spec = importlib.util.spec_from_file_location("phase6_single_pilot_runner", path)
    if spec is None or spec.loader is None:
        _fail("mapper_unavailable", f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["phase6_single_pilot_runner"] = module
    spec.loader.exec_module(module)
    return module._canonical_raw_action


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------
def verify_authorities() -> str:
    branch = _git_text("branch", "--show-current")
    if branch != A_BRANCH:
        _fail("unexpected_branch", f"Person A branch is {branch!r}")
    if (
        _completed(
            ["git", "merge-base", "--is-ancestor", A_STARTING_AUTHORITY, "HEAD"]
        ).returncode
        != 0
    ):
        _fail(
            "authority_not_ancestor",
            f"{A_STARTING_AUTHORITY} is not an ancestor of HEAD",
        )
    if _completed(["git", "cat-file", "-e", f"{C_COMMIT}^{{commit}}"]).returncode != 0:
        _fail("missing_c_commit", C_COMMIT)
    if (
        _completed(
            ["git", "merge-base", "--is-ancestor", C_COMMIT, C_REMOTE_REF]
        ).returncode
        != 0
    ):
        _fail("c_commit_not_remote", f"{C_COMMIT} is not reachable from {C_REMOTE_REF}")
    observed = _sha256(_git_bytes(C_COMMIT, C_ACCEPTED_MANIFEST_PATH))
    if observed != C_ACCEPTED_MANIFEST_SHA256:
        _fail("c_manifest_sha_mismatch", observed)
    return A_STARTING_AUTHORITY


def load_c_bundles() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load and hash-verify Person C's manifest and 66 per-trajectory bundles."""

    manifest = json.loads(_git_bytes(C_COMMIT, C_ACCEPTED_MANIFEST_PATH))
    inventory = json.loads(_git_bytes(C_COMMIT, C_INVENTORY_PATH))
    declared = inventory["files"]
    bundles: list[dict[str, Any]] = []
    for episode_id in range(FIRST_EPISODE, LAST_EPISODE + 1):
        relative = f"per_trajectory/ep{episode_id}.json"
        expected = declared.get(relative)
        if expected is None:
            _fail("missing_c_bundle", relative)
        raw = _git_bytes(C_COMMIT, f"{C_PACKAGE_ROOT}/{relative}")
        digest = _sha256(raw)
        if digest != expected:
            _fail("c_bundle_hash_mismatch", relative)
        bundle = json.loads(raw)
        bundle["_bundle_sha256"] = digest
        bundle["_bundle_path"] = f"{C_PACKAGE_ROOT}/{relative}"
        bundles.append(bundle)
    if len(bundles) != EXPECTED_TRAJECTORY_COUNT:
        _fail("c_bundle_count", str(len(bundles)))
    return manifest, bundles


# ---------------------------------------------------------------------------
# Frame-map materialization
# ---------------------------------------------------------------------------
def _artifact_lookup(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for artifact in bundle["artifacts"]:
        role = str(artifact["artifact_role"])
        if role in lookup:
            _fail("duplicate_artifact_role", role)
        lookup[role] = artifact
    return lookup


def _verified_stream(
    lookup: dict[str, dict[str, Any]], role: str
) -> tuple[list[dict[str, Any]], str]:
    artifact = lookup.get(role)
    if artifact is None:
        _fail("missing_artifact", role)
    path = Path(artifact["path_or_uri"])
    if not path.is_file():
        _fail("missing_runtime_payload", artifact["path_or_uri"])
    rows, payload = _read_jsonl(path)
    digest = _sha256(payload)
    if digest != artifact["sha256"] or len(payload) != artifact["byte_size"]:
        _fail("runtime_payload_hash_mismatch", artifact["path_or_uri"])
    return rows, digest


def build_trajectory_frame_map(
    bundle: dict[str, Any],
    *,
    convert_action: Any,
    canonical_raw_action: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Materialize one trajectory's real production frame map."""

    identity = bundle["identity"]
    trajectory_id = str(identity["trajectory_id"])
    episode_id = int(identity["episode_id"])
    lookup = _artifact_lookup(bundle)

    declared_frames = int(bundle["qa_summary"]["cardinality_counts"]["frame_count"])
    client_rows, client_sha = _verified_stream(lookup, "client_tick.jsonl")
    action_rows, action_sha = _verified_stream(lookup, "raw_actions.jsonl")
    state_rows, state_sha = _verified_stream(lookup, "server_state.jsonl")

    counts = {
        "client_tick": len(client_rows),
        "raw_actions": len(action_rows),
        "server_state": len(state_rows),
    }
    if len(set(counts.values())) != 1:
        _fail(
            "stream_cardinality_mismatch",
            f"{trajectory_id}: runtime stream row counts disagree: {counts}",
        )
    observed_frames = len(client_rows)
    if observed_frames != declared_frames:
        _fail(
            "declared_frame_count_mismatch",
            f"{trajectory_id}: Person C declares {declared_frames} frames, "
            f"the runtime streams carry {observed_frames}",
        )

    condition_identity_sha256 = _canonical_sha256(bundle["condition"])
    rows: list[dict[str, Any]] = []
    for index, (client, action, state) in enumerate(
        zip(client_rows, action_rows, state_rows, strict=True)
    ):
        server_tick = int(client["server_tick"])
        if int(action["server_tick"]) != server_tick or int(
            state["server_tick"]
        ) != server_tick:
            _fail(
                "server_tick_join_mismatch",
                f"{trajectory_id}: streams disagree on server_tick at row {index}",
            )
        if server_tick != index:
            _fail(
                "non_consecutive_server_ticks",
                f"{trajectory_id}: server_tick {server_tick} at position {index}",
            )
        render_frame_idx = int(client["render_frame_idx"])
        if int(action["render_frame_idx"]) != render_frame_idx:
            _fail(
                "render_frame_join_mismatch",
                f"{trajectory_id}: render_frame_idx disagrees at row {index}",
            )
        action_idx = int(action["action_idx"])
        for name, value in (
            ("episode_id", int(client["episode_id"])),
            ("episode_id", int(action["episode_id"])),
            ("episode_id", int(state["episode_id"])),
        ):
            if value != episode_id:
                _fail("episode_join_mismatch", f"{trajectory_id}: {name} {value}")

        frame_role = str(client["frame_path"]).replace("\\", "/")
        frame_artifact = lookup.get(frame_role)
        if frame_artifact is None:
            _fail(
                "frame_not_in_accepted_bundle",
                f"{trajectory_id}: {frame_role} is absent from Person C's bundle",
            )
        frame_path = Path(frame_artifact["path_or_uri"])
        if not frame_path.is_file():
            _fail("missing_runtime_frame", frame_artifact["path_or_uri"])
        frame_payload = frame_path.read_bytes()
        frame_sha = _sha256(frame_payload)
        if (
            frame_sha != frame_artifact["sha256"]
            or len(frame_payload) != frame_artifact["byte_size"]
        ):
            _fail("frame_hash_mismatch", frame_artifact["path_or_uri"])

        canonical_action = canonical_raw_action(action)
        normalized, tokens, is_noop = convert_action(canonical_action)

        rows.append(
            {
                "action_converter_identity": ACTION_CONVERTER_IDENTITY,
                "action_idx": action_idx,
                "action_is_noop": bool(is_noop),
                "action_token_sha256": _canonical_sha256(list(tokens)),
                "action_tokens": [int(token) for token in tokens],
                "c_bundle_sha256": bundle["_bundle_sha256"],
                "c_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
                "c_source_commit": C_COMMIT,
                "condition_identity_sha256": condition_identity_sha256,
                "control_type": str(identity["control_type"]),
                "detector_visibility_status": DETECTOR_VISIBILITY_STATUS,
                "episode_id": episode_id,
                "frame_map_schema_version": SCHEMA_VERSION,
                "geometric_visible": bool(state["geometric_visible"]),
                "layout_id": str(identity["layout_id"]),
                "model_frame_idx": index,
                "normalized_action_sha256": _canonical_sha256(normalized),
                "planned_cell_id": str(identity["planned_cell_id"]),
                "preprocessing_identity": PREPROCESSING_IDENTITY,
                "raw_action_identity_sha256": _canonical_sha256(canonical_action),
                "render_frame_idx": render_frame_idx,
                "server_tick": server_tick,
                "set_id": str(identity["set_id"]),
                "source_client_tick_row_sha256": _canonical_sha256(client),
                "source_frame_byte_size": int(frame_artifact["byte_size"]),
                "source_frame_role": frame_role,
                "source_frame_runtime_path": str(frame_artifact["path_or_uri"]),
                "source_frame_sha256": frame_sha,
                "source_raw_action_row_sha256": _canonical_sha256(action),
                "source_server_state_row_sha256": _canonical_sha256(state),
                "trajectory_id": trajectory_id,
                "visibility_identity_sha256": _canonical_sha256(
                    {
                        "geometric_visible": bool(state["geometric_visible"]),
                        "geometric_visibility_version": bundle["visibility"][
                            "geometric_visibility_version"
                        ],
                        "source": GEOMETRIC_VISIBILITY_SOURCE,
                    }
                ),
                "visibility_source": GEOMETRIC_VISIBILITY_SOURCE,
            }
        )

    keys = [(row["trajectory_id"], row["model_frame_idx"]) for row in rows]
    if len(set(keys)) != len(keys):
        _fail("duplicate_model_frame_key", trajectory_id)
    if sorted(row["model_frame_idx"] for row in rows) != list(range(len(rows))):
        _fail("non_dense_model_frame_idx", trajectory_id)
    for field in ("server_tick", "render_frame_idx", "action_idx"):
        values = [row[field] for row in rows]
        if len(set(values)) != len(values):
            _fail("duplicate_index_field", f"{trajectory_id}:{field}")

    summary = {
        "action_noop_row_count": sum(1 for row in rows if row["action_is_noop"]),
        "c_bundle_path": bundle["_bundle_path"],
        "c_bundle_sha256": bundle["_bundle_sha256"],
        "control_type": str(identity["control_type"]),
        "declared_frame_count": declared_frames,
        "episode_id": episode_id,
        "expected_activation_chunk_count": LAYER_COUNT,
        "expected_activation_row_count": len(rows) * LAYER_COUNT,
        "geometric_visible_row_count": sum(
            1 for row in rows if row["geometric_visible"]
        ),
        "layout_id": str(identity["layout_id"]),
        "model_frame_count": len(rows),
        "planned_cell_id": str(identity["planned_cell_id"]),
        "runtime_client_root": bundle["locations"]["runtime_path"]["client"],
        "runtime_server_root": bundle["locations"]["runtime_path"]["server"],
        "set_id": str(identity["set_id"]),
        "source_client_tick_sha256": client_sha,
        "source_raw_actions_sha256": action_sha,
        "source_server_state_sha256": state_sha,
        "trajectory_id": trajectory_id,
    }
    return rows, summary


def build_frame_maps() -> tuple[
    dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]
]:
    from mineocclude.models._mineworld_adapter_wave2 import _OfficialActionConverter

    if not MINEWORLD_SOURCE_ROOT.is_dir():
        _fail("missing_pinned_mineworld_source", str(MINEWORLD_SOURCE_ROOT))
    converter = _OfficialActionConverter(MINEWORLD_SOURCE_ROOT)
    canonical_raw_action = _load_canonical_raw_action_mapper()

    _manifest, bundles = load_c_bundles()
    frame_maps: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    for bundle in bundles:
        rows, summary = build_trajectory_frame_map(
            bundle,
            convert_action=converter.convert,
            canonical_raw_action=canonical_raw_action,
        )
        trajectory_id = summary["trajectory_id"]
        if trajectory_id in frame_maps:
            _fail("duplicate_trajectory", trajectory_id)
        frame_maps[trajectory_id] = rows
        summaries[trajectory_id] = summary
    return frame_maps, summaries


# ---------------------------------------------------------------------------
# Package documents
# ---------------------------------------------------------------------------
def frame_map_index(
    frame_maps: dict[str, list[dict[str, Any]]],
    summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    total = sum(len(rows) for rows in frame_maps.values())
    global_keys = [
        (trajectory_id, row["model_frame_idx"])
        for trajectory_id, rows in frame_maps.items()
        for row in rows
    ]
    duplicates = sorted(
        f"{trajectory}:{index}"
        for (trajectory, index), count in Counter(global_keys).items()
        if count > 1
    )
    missing = sorted(
        trajectory_id
        for trajectory_id, summary in summaries.items()
        if summary["model_frame_count"] != summary["declared_frame_count"]
    )
    per_trajectory = {
        trajectory_id: {
            **summary,
            "frame_map_path": f"frame_maps/{trajectory_id}.jsonl",
            "frame_map_sha256": _sha256(_jsonl_bytes(frame_maps[trajectory_id])),
        }
        for trajectory_id, summary in sorted(summaries.items())
    }
    return {
        "action_converter_identity": ACTION_CONVERTER_IDENTITY,
        "c_accepted_manifest_path": C_ACCEPTED_MANIFEST_PATH,
        "c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "c_source_commit": C_COMMIT,
        "detector_visibility_status": DETECTOR_VISIBILITY_STATUS,
        "duplicate_model_frame_keys": duplicates,
        "duplicate_model_frame_key_count": len(duplicates),
        "expected_activation_row_count_total": total * LAYER_COUNT,
        "expected_chunk_count_total": len(frame_maps) * LAYER_COUNT,
        "expected_model_frame_key_count": EXPECTED_MODEL_FRAME_KEY_COUNT,
        "geometric_visibility_source": GEOMETRIC_VISIBILITY_SOURCE,
        "layer_count": LAYER_COUNT,
        "missing_trajectory_ids": missing,
        "missing_trajectory_count": len(missing),
        "model_facing_key": list(MODEL_FACING_KEY),
        "model_frame_key_count": total,
        "model_frame_key_count_matches_expected": (
            total == EXPECTED_MODEL_FRAME_KEY_COUNT
        ),
        "per_trajectory": per_trajectory,
        "pinned_mineworld_revision": PINNED_MINEWORLD_REVISION,
        "preprocessing_identity": PREPROCESSING_IDENTITY,
        "preprocessing_profile": PREPROCESSING_PROFILE,
        "row_fields": list(FRAME_MAP_ROW_FIELDS),
        "row_order_is_not_identity": True,
        "schema_id": FRAME_MAP_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "source_bytes_hash_verified": True,
        "trajectory_count": len(frame_maps),
    }


def accepted_input_manifest(index: dict[str, Any]) -> dict[str, Any]:
    """The Person A 66-cell accepted-input manifest consumed by run_mvp.py."""

    entries = []
    for trajectory_id, summary in sorted(index["per_trajectory"].items()):
        entries.append(
            {
                "bundle_manifest": f"{DATA_ROOT_REL}/{summary['frame_map_path']}",
                "bundle_manifest_sha256": summary["frame_map_sha256"],
                "direct_artifact_count": summary["model_frame_count"],
                "episode_id": summary["episode_id"],
                "expected_activation_chunk_count": summary[
                    "expected_activation_chunk_count"
                ],
                "expected_activation_row_count": summary[
                    "expected_activation_row_count"
                ],
                "layout_id": summary["layout_id"],
                "trajectory_id": trajectory_id,
            }
        )
    return {
        "accepted_trajectory_count": len(entries),
        "c_accepted_manifest_path": C_ACCEPTED_MANIFEST_PATH,
        "c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "c_source_commit": C_COMMIT,
        "canonical_c6a_id": "person-c-c6a-post-c1-v0.1",
        "current_certified_trajectory": None,
        "excluded_trajectory_count": 0,
        "expected_total_activation_chunk_count": index["expected_chunk_count_total"],
        "expected_total_activation_row_count": index[
            "expected_activation_row_count_total"
        ],
        "frame_map_index_path": f"{DATA_ROOT_REL}/frame_map_index.json",
        "immutable": True,
        "model_facing_key": list(MODEL_FACING_KEY),
        "new_trajectory_bundles": entries,
        "no_historical_artifact_reused_as_66_cell_output": True,
        "schema_id": f"{SCHEMA_PREFIX}-accepted-input-manifest",
        "schema_version": SCHEMA_VERSION,
        "supersedes": (
            "data/handoff_a/person_a_canonical_c6a_multilayout_sagemaker_input_v0_1"
            "/bundle_manifest.json"
        ),
    }


def source_byte_inventory(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    """Exact Windows source byte inventory taken only from C's handoff."""

    per_trajectory: dict[str, Any] = {}
    total_bytes = 0
    total_artifacts = 0
    verified_artifacts = 0
    missing: list[str] = []
    for bundle in bundles:
        trajectory_id = str(bundle["identity"]["trajectory_id"])
        artifacts = []
        subtotal = 0
        absent = 0
        for artifact in bundle["artifacts"]:
            path = Path(artifact["path_or_uri"])
            present = path.is_file()
            if not present:
                absent += 1
                missing.append(str(artifact["path_or_uri"]))
            else:
                payload = path.read_bytes()
                if (
                    _sha256(payload) != artifact["sha256"]
                    or len(payload) != artifact["byte_size"]
                ):
                    _fail("source_byte_hash_mismatch", str(artifact["path_or_uri"]))
                verified_artifacts += 1
                subtotal += len(payload)
            total_artifacts += 1
            artifacts.append(
                {
                    "artifact_role": artifact["artifact_role"],
                    "byte_size": artifact["byte_size"],
                    "hash_verified": present,
                    "sha256": artifact["sha256"],
                    "side": artifact["side"],
                    "windows_source_path": artifact["path_or_uri"],
                }
            )
        total_bytes += subtotal
        per_trajectory[trajectory_id] = {
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
            "byte_size_total": subtotal,
            "episode_id": int(bundle["identity"]["episode_id"]),
            "runtime_client_root": bundle["locations"]["runtime_path"]["client"],
            "runtime_server_root": bundle["locations"]["runtime_path"]["server"],
            "state": "available_hash_verified" if not absent else "incomplete",
        }
    return {
        "artifact_count": total_artifacts,
        "artifact_hash_verified_count": verified_artifacts,
        "byte_size_total": total_bytes,
        "c_capture_output_bundle_sha256": (
            "c8453cb8a459d0d56d69f5bf39233997537e28a14b10a3a2ba4aeb3f421c624b"
        ),
        "c_source_commit": C_COMMIT,
        "missing_paths": sorted(missing),
        "per_trajectory": dict(sorted(per_trajectory.items())),
        "schema_id": f"{SCHEMA_PREFIX}-source-byte-inventory",
        "schema_version": SCHEMA_VERSION,
        "source_host_role": "windows_preparation_host",
        "trajectory_count": len(per_trajectory),
    }


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def write_data_package() -> dict[str, Any]:
    frame_maps, summaries = build_frame_maps()
    index = frame_map_index(frame_maps, summaries)
    if index["model_frame_key_count"] != EXPECTED_MODEL_FRAME_KEY_COUNT:
        _fail(
            "model_frame_key_count_mismatch",
            f"authoritative runtime evidence yields "
            f"{index['model_frame_key_count']} model frames, not "
            f"{EXPECTED_MODEL_FRAME_KEY_COUNT}",
        )
    if index["duplicate_model_frame_keys"] or index["missing_trajectory_ids"]:
        _fail("frame_map_key_audit_failed", "duplicate or missing frame identities")

    _manifest, bundles = load_c_bundles()
    inventory = source_byte_inventory(bundles)
    manifest = accepted_input_manifest(index)

    maps_dir = DATA_ROOT / "frame_maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    for trajectory_id, rows in sorted(frame_maps.items()):
        (maps_dir / f"{trajectory_id}.jsonl").write_bytes(_jsonl_bytes(rows))
    (DATA_ROOT / "frame_map_index.json").write_bytes(_json_bytes(index))
    (DATA_ROOT / "bundle_manifest.json").write_bytes(_json_bytes(manifest))
    (DATA_ROOT / "source_byte_inventory.json").write_bytes(_json_bytes(inventory))

    files = {
        "bundle_manifest.json": _sha256(_json_bytes(manifest)),
        "frame_map_index.json": _sha256(_json_bytes(index)),
        "source_byte_inventory.json": _sha256(_json_bytes(inventory)),
    }
    for trajectory_id, rows in sorted(frame_maps.items()):
        files[f"frame_maps/{trajectory_id}.jsonl"] = _sha256(_jsonl_bytes(rows))
    package_inventory = {
        "file_count": len(files) + 1,
        "files": dict(sorted(files.items())),
        "inventory_excludes_self": True,
        "schema_id": f"{SCHEMA_PREFIX}-data-sha256-inventory",
        "schema_version": SCHEMA_VERSION,
    }
    (DATA_ROOT / "sha256_inventory.json").write_bytes(_json_bytes(package_inventory))
    return {
        "accepted_input_manifest": manifest,
        "frame_map_index": index,
        "package_inventory": package_inventory,
        "source_byte_inventory": inventory,
    }


# ---------------------------------------------------------------------------
# Storage-dtype reconciliation (Section 4)
# ---------------------------------------------------------------------------
DTYPE_EVIDENCE = {
    "frozen_mvp_configuration": (
        "configs/experiments/mvp.yaml",
        "3c20c014dddd9b2f8b9a9225b97d7d6d11994b08363f5026d8c26fd2f5aaaaa3",
    ),
    "step_7_1_identity_freeze": (
        "docs/status/person_a_phase7_mvp_v0_1/step_7_1_identity_freeze.json",
        "b0709a7eaee0384d77ef27c2b42235002bc5dda1c65feb515a8e97ef917b34d0",
    ),
    "preflight_activation_contract": (
        (
            "docs/status/person_a_phase4_step4_1_production_handoff_preflight_v0_1"
            "/activation_contract.json"
        ),
        "3a0195317121b7a07f47bd0eed624635adafa2b2ba3530aa3236ae9b2634f03f",
    ),
    "preflight_immutable_runtime_configuration": (
        (
            "docs/status/person_a_phase4_step4_1_production_handoff_preflight_v0_1"
            "/immutable_runtime_configuration.json"
        ),
        "eb634c1e81c65a724b7cf32cbfe03f62e80a4428afda605071e1a43c6d0f4c10",
    ),
    "step6_frozen_runtime_configuration": (
        (
            "docs/status/person_a_step6_runtime_acknowledgement_v0_1"
            "/frozen_runtime_configuration.json"
        ),
        "ecf3e5700da2ade1ca30290966a77bfb558b6afa3d834a0771007a90c06e9cd7",
    ),
    "executed_ten_pilot_certification": (
        "docs/status/person_a_phase6_closeout_v0_1/step_6_7_certification.json",
        "663eda3638235b168ca10e7cef6ace8f7b385df620f751890326852af8fbb0d8",
    ),
    "phase5_storage_decision": (
        "docs/status/person_a_phase5_storage_decision.md",
        "d02a6be1f9346ad7ae54fea5a809ac4466d409ecbaf74e179c9849193399ae2d",
    ),
    "pooling_implementation": (
        "src/mineocclude/activations/pool.py",
        "a5fd4c5d7272883432c29401e90880e70b8f90af2c0d0365bf65bc2847b0ead7",
    ),
    "queue_cardinality_certification": (
        "src/mineocclude/experiments/extraction_queue.py",
        "08e12f4bb25088bb2fd4c18058fd0ac8ab34be2d57824cd4ac986819115cb159",
    ),
    "activation_store_v2": (
        "src/mineocclude/activations/store_v2.py",
        "8c2313f4ab99c02abb302af1d0b688ba353e34a1cd7985492ed9e562995dd575",
    ),
}


def repository_bytes(path: str) -> bytes:
    """Return a tracked text file's repository-canonical bytes.

    `.gitattributes` pins the repository to `* text=auto eol=lf`, so Git always
    stores LF. Tools that wrote a receipt through Windows text mode leave CRLF
    in the working tree even though the committed blob is LF, and Git reports no
    change. Hashing the working-tree bytes directly would therefore produce a
    host-specific digest; normalizing to LF yields the digest the repository
    actually stores, on every host and both before and after a commit.
    """

    return (ROOT / path).read_bytes().replace(b"\r\n", b"\n")


def _verified_evidence() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for name, (path, expected) in sorted(DTYPE_EVIDENCE.items()):
        raw = repository_bytes(path)
        digest = _sha256(raw)
        if digest != expected:
            _fail("dtype_evidence_drifted", f"{path}: {digest} != {expected}")
        records[name] = {
            "byte_size": len(raw),
            "digest_scope": "repository_canonical_lf_bytes",
            "path": path,
            "sha256": digest,
        }
    return records


def storage_dtype_reconciliation() -> dict[str, Any]:
    """Audit the stored-vs-analysis dtype authority without changing either side."""

    evidence = _verified_evidence()
    certification = json.loads(
        repository_bytes(DTYPE_EVIDENCE["executed_ten_pilot_certification"][0])
    )
    measured = []
    for pilot in certification["benchmark"]["per_pilot"]:
        rows = int(pilot["activation_row_count"])
        payload = int(pilot["activation_bytes"])
        measured.append(
            {
                "activation_bytes": payload,
                "activation_row_count": rows,
                "bytes_per_row": payload / rows,
                "implied_element_bytes": payload / rows / 2048,
                "trajectory_id": pilot["trajectory_id"],
            }
        )
    implied = [entry["implied_element_bytes"] for entry in measured]
    all_float32 = all(3.9 < value < 4.1 for value in implied)

    return {
        "analysis_arithmetic_dtype": "float64",
        "conflict": {
            "declared_stored_dtype": "float16",
            "declared_stored_dtype_path": "configs/experiments/mvp.yaml"
            "#extraction.stored_dtype",
            "internal_to_one_frozen_file": True,
            "internal_conflict_detail": (
                "The same frozen configuration pins extraction.stored_dtype=float16 "
                "and storage.bytes_per_activation_row=8192.68303094984. At the "
                "frozen vector width of 2048 only a 4-byte element explains that "
                "measured byte rate, so the two frozen values cannot both be "
                "correct. Either resolution therefore changes at least one "
                "result_changing frozen value."
            ),
            "observed_stored_dtype": "float32",
        },
        "decision": "PENDING_COORDINATED_A_B_REVIEW",
        "decision_date": "2026-08-07",
        "decision_owner": "person_a_model",
        "evidence": evidence,
        "evidence_for_float16_storage": [
            {
                "claim": "extraction.stored_dtype is frozen as float16",
                "source": "frozen_mvp_configuration",
                "weight": "declared_design_intent",
            },
            {
                "claim": (
                    "Step 7.1 lists extraction.stored_dtype as a result_changing "
                    "path frozen at float16"
                ),
                "source": "step_7_1_identity_freeze",
                "weight": "declared_design_intent",
            },
            {
                "claim": (
                    "certify_queue_cardinality emits "
                    "pooled_storage_preserved_16_bit and "
                    "analysis_arithmetic_promoted_in_person_b_only"
                ),
                "source": "queue_cardinality_certification",
                "weight": "declared_design_intent",
            },
            {
                "claim": (
                    "the Phase 5 read API promotes float16 vectors to float32 for "
                    "analysis while stored bytes and dtype metadata are unchanged"
                ),
                "source": "phase5_storage_decision",
                "weight": "declared_design_intent",
            },
        ],
        "evidence_for_float32_storage": [
            {
                "claim": (
                    "all ten executed production pilots imply a 4-byte stored "
                    "element at width 2048"
                ),
                "measured": measured,
                "source": "executed_ten_pilot_certification",
                "weight": "executed_production_measurement",
            },
            {
                "claim": (
                    "the frozen preflight activation contract pins "
                    "pooled_representation.stored_dtype=float32 with "
                    "analysis_dtype=float64"
                ),
                "source": "preflight_activation_contract",
                "weight": "accepted_contract",
            },
            {
                "claim": "the frozen runtime configuration pins pooling stored_dtype=float32",
                "source": "preflight_immutable_runtime_configuration",
                "weight": "accepted_contract",
            },
            {
                "claim": (
                    "the Step 6 acknowledgement's frozen runtime configuration "
                    "carries the same float32 pooling contract"
                ),
                "source": "step6_frozen_runtime_configuration",
                "weight": "accepted_contract",
            },
            {
                "claim": (
                    "select_and_pool upcasts to float32 and rejects any pooled "
                    "vector whose dtype is not float32, so the current "
                    "implementation cannot emit a float16 pooled vector"
                ),
                "source": "pooling_implementation",
                "weight": "implementation",
            },
        ],
        "executed_production_all_imply_float32": all_float32,
        "hooked_source_tensor_dtype": "float16",
        "mvp_yaml_modified_by_this_package": False,
        "person_a_unilateral_change_made": False,
        "proposal": {
            "authority_required": ["person_a_model", "person_b_analysis"],
            "extraction_authorized_by_this_proposal": False,
            "new_run_identity_required": True,
            "options": [
                {
                    "changes": [
                        (
                            "configs/experiments/mvp.yaml#extraction.stored_dtype "
                            "float16 -> float32"
                        )
                    ],
                    "consequence": (
                        "Aligns the frozen configuration with the executed "
                        "production run, the accepted preflight contracts, the "
                        "frozen bytes_per_activation_row, and the current pooling "
                        "implementation. No code change is required."
                    ),
                    "option_id": "align_config_to_executed_float32_storage",
                    "recommended_by_person_a": True,
                },
                {
                    "changes": [
                        (
                            "configs/experiments/mvp.yaml#storage."
                            "bytes_per_activation_row 8192.68303094984 -> a measured "
                            "float16 rate"
                        ),
                        (
                            "docs/status/person_a_phase4_step4_1_production_handoff_"
                            "preflight_v0_1/activation_contract.json#pooled_"
                            "representation.stored_dtype float32 -> float16"
                        ),
                        (
                            "src/mineocclude/activations/pool.py: emit a float16 "
                            "pooled vector and promote to float32 only on read"
                        ),
                    ],
                    "consequence": (
                        "Preserves the declared 16-bit storage intent and the "
                        "B-side promotion design, but invalidates the executed "
                        "ten-pilot activation bytes as a production reference and "
                        "requires a code change plus a new extraction run."
                    ),
                    "option_id": "implement_declared_float16_storage",
                    "recommended_by_person_a": False,
                },
            ],
            "result_changing_paths_touched": [
                "extraction.stored_dtype",
                "storage.bytes_per_activation_row",
            ],
        },
        "result_changing_review_required": True,
        "schema_id": f"{SCHEMA_PREFIX}-storage-dtype-reconciliation",
        "schema_version": SCHEMA_VERSION,
        "separation": {
            "analysis_arithmetic_dtype": "float64",
            "analysis_arithmetic_owner": "person_b_analysis",
            "hooked_activation_dtype": "float16",
            "pooled_stored_dtype_declared": "float16",
            "pooled_stored_dtype_executed": "float32",
            "rule": (
                "The hooked residual-stream tensor is float16 because the model "
                "runs in float16. Pooling is a separate step, and analysis "
                "arithmetic is promoted downstream by Person B. The unresolved "
                "question is only the pooled storage dtype."
            ),
        },
        "stale_statement_identified": None,
        "status": (
            "UNRESOLVED_REQUIRES_COORDINATED_REVIEW_NO_UNILATERAL_CHANGE_MADE"
        ),
        "stored_activation_dtype_executed": "float32",
        "superseded_additively": False,
    }


# ---------------------------------------------------------------------------
# Byte-transport plan (Section 5)
# ---------------------------------------------------------------------------
EXTERNAL_ARTIFACT_INDEX_PATH = (
    "docs/status/person_a_phase9_clean_run_v0_1/external_artifact_index.json"
)
EXECUTION_HOST_CONTRACT_PATH = (
    "docs/status/person_a_phase6_sagemaker_runtime_addendum_v0_1"
    "/execution_host_contract.json"
)
HANDOFF_RUNBOOK_PATH = "docs/runbooks/person_a_handoff_rehearsals.md"


def _durable_destination_audit() -> dict[str, Any]:
    """Search the repository for an already approved durable destination."""

    from mineocclude.experiments.clean_run import APPROVED_SCHEMES, PRIVATE_PREFIXES

    index = json.loads(repository_bytes(EXTERNAL_ARTIFACT_INDEX_PATH))
    candidates: list[dict[str, Any]] = []
    for entry in index.get("artifacts", ()):
        uri = str(entry.get("uri", ""))
        candidates.append(
            {
                "artifact_id": entry.get("artifact_id"),
                "approved_scheme": uri.startswith(tuple(APPROVED_SCHEMES)),
                "is_object_store": uri.startswith("s3://"),
                "uri": uri,
            }
        )
    object_store = [entry for entry in candidates if entry["is_object_store"]]
    return {
        "approved_durable_destination": None,
        "approved_schemes": list(APPROVED_SCHEMES),
        "credential_channel": {
            "accessible_from_this_environment": False,
            "access_procedure_documented_for_person_a": False,
            "credential_value_present_in_repository": False,
            "instruction_gap": (
                "The approved secret channel is named but its access procedure is "
                "not documented for Person A or Person B."
            ),
            "mechanism": "approved_out_of_band_channel",
            "source_path": HANDOFF_RUNBOOK_PATH,
        },
        "external_artifact_index_path": EXTERNAL_ARTIFACT_INDEX_PATH,
        "external_artifact_index_sha256": _sha256(
            repository_bytes(EXTERNAL_ARTIFACT_INDEX_PATH)
        ),
        "index_artifact_candidates": candidates,
        "local_cache_root": index.get("local_cache_root"),
        "object_store_destination_count": len(object_store),
        "private_prefixes_rejected": list(PRIVATE_PREFIXES),
        "repository_authorizes_this_operator_to_upload": False,
        "s3_bucket_or_prefix_found": bool(object_store),
        "searched": [
            "docs/runbooks",
            "configs",
            EXTERNAL_ARTIFACT_INDEX_PATH,
            EXECUTION_HOST_CONTRACT_PATH,
            "src/mineocclude/experiments/clean_run.py",
        ],
    }


def byte_transfer_plan(inventory: dict[str, Any]) -> dict[str, Any]:
    audit = _durable_destination_audit()
    host_contract = json.loads(repository_bytes(EXECUTION_HOST_CONTRACT_PATH))
    sources = []
    for trajectory_id, entry in sorted(inventory["per_trajectory"].items()):
        sources.append(
            {
                "artifact_count": entry["artifact_count"],
                "byte_size_total": entry["byte_size_total"],
                "episode_id": entry["episode_id"],
                "hash_verified": entry["state"] == "available_hash_verified",
                "intended_durable_destination": None,
                "trajectory_id": trajectory_id,
                "windows_source_client_root": entry["runtime_client_root"],
                "windows_source_server_root": entry["runtime_server_root"],
            }
        )
    pending = audit["approved_durable_destination"] is None
    return {
        "approved_durable_destination": audit["approved_durable_destination"],
        "byte_transport_destination_pending": pending,
        "credential_mechanism": audit["credential_channel"],
        "destination_authorization_missing": [
            (
                "an approved durable destination URI (no S3 bucket/prefix and no other "
                "durable artifact store is assigned anywhere in this repository)"
            ),
            (
                "a repository policy statement authorizing this operator to upload the "
                "Person C episode payloads"
            ),
            "a documented access procedure for the approved secret channel",
            (
                "a Person C decision assigning the durable URI, which C records as "
                "durable_s3_assigned=false"
            ),
        ],
        "destination_fabricated": False,
        "destination_layout_when_authorized": {
            "note": (
                "This layout is a proposal keyed to Person C's own runtime "
                "structure. It is not a destination and carries no host, bucket, "
                "or prefix until one is authorized."
            ),
            "relative_layout": (
                "<approved_destination_root>/person-c-c6a-post-c1-v0.1/"
                "episode_<episode_id>/<side>/<artifact_role>"
            ),
            "sides": ["client", "server"],
        },
        "execution_environment": {
            "allowed_production_environment": host_contract["execution_boundary"][
                "allowed_production_environment"
            ],
            "local_windows_host_role": host_contract["execution_boundary"][
                "local_windows_host_role"
            ],
            "source_path": EXECUTION_HOST_CONTRACT_PATH,
        },
        "executable_transfer_command_available": False,
        "expected_byte_inventory": {
            "artifact_count": inventory["artifact_count"],
            "artifact_hash_verified_count": inventory[
                "artifact_hash_verified_count"
            ],
            "byte_size_total": inventory["byte_size_total"],
            "source_byte_inventory_path": (
                f"{DATA_ROOT_REL}/source_byte_inventory.json"
            ),
            "trajectory_count": inventory["trajectory_count"],
        },
        "destination_audit": audit,
        "sagemaker_materialization_procedure": [
            (
                "materialize the approved destination objects under the session's "
                "input root, preserving episode_<episode_id>/<side>/<artifact_role>"
            ),
            "recompute SHA-256 for every materialized artifact",
            (
                "compare each digest and byte size against "
                f"{DATA_ROOT_REL}/source_byte_inventory.json"
            ),
            (
                "compare each per-trajectory frame map's source_frame_sha256 against "
                "the materialized frame bytes"
            ),
            (
                "refuse to start Step 6.1 unless all 66 trajectories and every "
                "artifact match exactly"
            ),
        ],
        "schema_id": f"{SCHEMA_PREFIX}-byte-transfer-plan",
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
        "status": "PREPARED_AWAITING_APPROVED_DESTINATION_AND_CREDENTIAL_ACCESS",
        "transfer_command_template": (
            "<approved_transfer_tool> <windows_source_path> "
            "<approved_destination_uri>  # unavailable until a destination and "
            "an upload authorization exist"
        ),
        "transfer_launched": False,
        "verification_procedure": [
            (
                "python scripts/build_person_a_66_cell_local_preparation_v0_1.py "
                "frame-maps  # re-verifies every source byte against Person C's hashes"
            ),
            "compare source_byte_inventory.json artifact digests before transfer",
            "recompute digests after transfer and require an exact match",
            (
                "require the 66 frame-map files' SHA-256 values from "
                f"{DATA_ROOT_REL}/sha256_inventory.json to be unchanged"
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Preparation receipt (Section 6)
# ---------------------------------------------------------------------------
def _receipt_source(path: str) -> dict[str, Any]:
    raw = repository_bytes(path)
    return {
        "byte_size": len(raw),
        "digest_scope": "repository_canonical_lf_bytes",
        "path": path,
        "sha256": _sha256(raw),
    }


def preparation_receipt(
    *,
    a_commit: str,
    index: dict[str, Any],
    inventory: dict[str, Any],
    dtype_decision: dict[str, Any],
    transfer_plan: dict[str, Any],
) -> dict[str, Any]:
    matrix = _receipt_source(
        "docs/status/person_a_phase7_mvp_v0_1/step_7_2_matrix_report.json"
    )
    queue_status = _receipt_source(
        "docs/status/person_a_phase7_mvp_v0_1/step_7_5_queue_status.json"
    )
    queue_state = _receipt_source(
        "docs/status/person_a_phase7_mvp_v0_1/extraction_queue_state.json"
    )
    matrix_document = json.loads(repository_bytes(matrix["path"]))
    queue_document = json.loads(repository_bytes(queue_state["path"]))
    frame_index = _receipt_source(f"{DATA_ROOT_REL}/frame_map_index.json")
    accepted_manifest = _receipt_source(f"{DATA_ROOT_REL}/bundle_manifest.json")
    data_inventory = _receipt_source(f"{DATA_ROOT_REL}/sha256_inventory.json")

    states = Counter(item["state"] for item in queue_document["items"])
    byte_access_ready = bool(
        transfer_plan["approved_durable_destination"] is not None
    )
    local_complete = bool(
        matrix_document["expected_cell_count"] == EXPECTED_TRAJECTORY_COUNT
        and matrix_document["accepted_cell_count"] == EXPECTED_TRAJECTORY_COUNT
        and matrix_document["shortfall_count"] == 0
        and len(queue_document["items"]) == EXPECTED_TRAJECTORY_COUNT
        and index["trajectory_count"] == EXPECTED_TRAJECTORY_COUNT
        and index["model_frame_key_count"] == EXPECTED_MODEL_FRAME_KEY_COUNT
        and not index["duplicate_model_frame_keys"]
        and not index["missing_trajectory_ids"]
        and inventory["artifact_hash_verified_count"] == inventory["artifact_count"]
    )

    return {
        "aggregate_phase6_runtime_authorized": False,
        "byte_accessibility": {
            "byte_transfer_plan_path": f"{STATUS_ROOT_REL}/byte_transfer_plan.json",
            "byte_transport_destination_pending": transfer_plan[
                "byte_transport_destination_pending"
            ],
            "sagemaker_byte_access_ready": byte_access_ready,
            "windows_artifact_count": inventory["artifact_count"],
            "windows_artifact_hash_verified_count": inventory[
                "artifact_hash_verified_count"
            ],
            "windows_byte_size_total": inventory["byte_size_total"],
            "windows_trajectory_count": inventory["trajectory_count"],
            "windows_trajectory_hash_verified_count": sum(
                1
                for entry in inventory["per_trajectory"].values()
                if entry["state"] == "available_hash_verified"
            ),
        },
        "extraction_readiness": {
            "blockers": sorted(
                filter(
                    None,
                    [
                        None
                        if byte_access_ready
                        else "sagemaker_cannot_access_the_66_episode_payload_bytes",
                        None
                        if not dtype_decision["result_changing_review_required"]
                        else "storage_dtype_decision_pending_coordinated_a_b_review",
                        "aggregate_phase6_runtime_authorization_absent",
                    ],
                )
            ),
            "gpu_extraction_started": False,
            "model_loaded": False,
            "person_a_66_extraction_ready": False,
            "person_a_66_input_contract_ready": True,
            "person_a_66_local_preparation_complete": local_complete,
        },
        "frame_maps": {
            "accepted_input_manifest": accepted_manifest,
            "data_package_root": DATA_ROOT_REL,
            "data_package_sha256_inventory": data_inventory,
            "duplicate_model_frame_key_count": index[
                "duplicate_model_frame_key_count"
            ],
            "expected_activation_row_count_total": index[
                "expected_activation_row_count_total"
            ],
            "expected_chunk_count_total": index["expected_chunk_count_total"],
            "frame_map_index": frame_index,
            "missing_trajectory_count": index["missing_trajectory_count"],
            "model_facing_key": index["model_facing_key"],
            "model_frame_key_count": index["model_frame_key_count"],
            "model_frame_key_count_expected": EXPECTED_MODEL_FRAME_KEY_COUNT,
            "per_trajectory_model_frame_counts": {
                trajectory_id: entry["model_frame_count"]
                for trajectory_id, entry in sorted(index["per_trajectory"].items())
            },
            "real_frame_maps_materialized": True,
            "trajectory_count": index["trajectory_count"],
        },
        "matrix": {
            "accepted_cell_count": matrix_document["accepted_cell_count"],
            "complete": matrix_document["complete"],
            "excluded_or_missing_count": (
                matrix_document["state_counts"]["excluded"]
                + matrix_document["state_counts"]["missing"]
                + matrix_document["state_counts"]["recollection_pending"]
            ),
            "expected_cell_count": matrix_document["expected_cell_count"],
            "person_c_accepted_manifest_sha256": matrix_document[
                "accepted_input_manifest"
            ]["person_c_accepted_manifest_sha256"],
            "receipt": matrix,
            "superseded_manifest": matrix_document["accepted_input_manifest"][
                "superseded_manifest"
            ],
        },
        "owner": "person_a",
        "person_a_branch": A_BRANCH,
        "person_a_commit": a_commit,
        "person_c": {
            "accepted_manifest_path": C_ACCEPTED_MANIFEST_PATH,
            "accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
            "accepted_trajectory_count": EXPECTED_TRAJECTORY_COUNT,
            "commit": C_COMMIT,
            "excluded_trajectory_count": 0,
        },
        "production_authorities": {
            "action_converter_identity": ACTION_CONVERTER_IDENTITY,
            "frame_map_schema_id": FRAME_MAP_SCHEMA_ID,
            "frame_map_schema_version": SCHEMA_VERSION,
            "pinned_mineworld_revision": PINNED_MINEWORLD_REVISION,
            "preprocessing_identity": PREPROCESSING_IDENTITY,
            "preprocessing_profile": PREPROCESSING_PROFILE,
        },
        "queue": {
            "complete_count": int(states.get("completed", 0)),
            "expected_activation_row_count": sum(
                int(item["expected_activation_row_count"])
                for item in queue_document["items"]
            ),
            "expected_chunk_count": sum(
                int(item["expected_chunk_count"]) for item in queue_document["items"]
            ),
            "historical_artifact_reused_as_66_cell_output": False,
            "identity": queue_document["identity"],
            "pending_count": int(states.get("pending", 0)),
            "receipt": queue_status,
            "run_id": queue_document["identity"]["run_id"],
            "state_receipt": queue_state,
            "superseded_states": sorted(
                path.name
                for path in (
                    ROOT / "docs" / "status" / "person_a_phase7_mvp_v0_1"
                ).glob("extraction_queue_state.superseded.*.json")
            ),
            "trajectory_count": len(queue_document["items"]),
        },
        "schema_id": f"{SCHEMA_PREFIX}-preparation-receipt",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "LOCAL_PREPARATION_COMPLETE_AWAITING_BYTE_TRANSPORT_"
            "DTYPE_DECISION_AND_AGGREGATE_AUTHORIZATION"
        ),
        "storage_dtype": {
            "analysis_arithmetic_dtype": dtype_decision["analysis_arithmetic_dtype"],
            "decision": dtype_decision["decision"],
            "decision_receipt": {
                "path": f"{STATUS_ROOT_REL}/storage_dtype_reconciliation.json"
            },
            "mvp_yaml_modified": False,
            "result_changing_review_required": dtype_decision[
                "result_changing_review_required"
            ],
            "stored_activation_dtype_executed": dtype_decision[
                "stored_activation_dtype_executed"
            ],
        },
    }


def _validation_receipt(
    index: dict[str, Any],
    inventory: dict[str, Any],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    return {
        "aggregate_phase6_runtime_authorized": False,
        "c_source_hashes_verified_before_consumption": True,
        "canonical_json_valid": True,
        "deterministic_regeneration": True,
        "duplicate_model_frame_key_count": index["duplicate_model_frame_key_count"],
        "frame_map_cardinality_pass": (
            index["model_frame_key_count"] == EXPECTED_MODEL_FRAME_KEY_COUNT
        ),
        "gpu_extraction_started": False,
        "matrix_accepted_cell_count": receipt["matrix"]["accepted_cell_count"],
        "matrix_expected_cell_count": receipt["matrix"]["expected_cell_count"],
        "missing_trajectory_count": index["missing_trajectory_count"],
        "model_loaded": False,
        "mvp_yaml_modified": False,
        "person_a_66_extraction_ready": False,
        "queue_trajectory_count": receipt["queue"]["trajectory_count"],
        "schema_id": f"{SCHEMA_PREFIX}-validation-receipt",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "source_artifact_hash_verified_count": inventory[
            "artifact_hash_verified_count"
        ],
        "source_artifact_missing_count": len(inventory["missing_paths"]),
        "transfer_launched": False,
    }


PROTECTED_FALSE_FIELDS = frozenset(
    {
        "aggregate_phase6_runtime_authorized",
        "destination_fabricated",
        "executable_transfer_command_available",
        "gpu_extraction_started",
        "historical_artifact_reused_as_66_cell_output",
        "model_loaded",
        "mvp_yaml_modified",
        "mvp_yaml_modified_by_this_package",
        "person_a_66_extraction_ready",
        "person_a_unilateral_change_made",
        "sagemaker_byte_access_ready",
        "scientific_execution_performed",
        "transfer_launched",
    }
)


def _protected_false_violations(value: Any, path: str) -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = value[key]
            child_path = f"{path}.{key}"
            if key in PROTECTED_FALSE_FIELDS and child is not False:
                violations.append(f"{child_path} must be exact Boolean false")
            violations.extend(_protected_false_violations(child, child_path))
    elif isinstance(value, list):
        for offset, child in enumerate(value):
            violations.extend(_protected_false_violations(child, f"{path}[{offset}]"))
    return violations


STATUS_OUTPUT_PATHS = (
    "byte_transfer_plan.json",
    "preparation_receipt.json",
    "sha256_inventory.json",
    "storage_dtype_reconciliation.json",
    "validation_receipt.json",
)


def write_status_package(a_commit: str) -> dict[str, Any]:
    index = json.loads((DATA_ROOT / "frame_map_index.json").read_bytes())
    inventory = json.loads((DATA_ROOT / "source_byte_inventory.json").read_bytes())
    dtype_decision = storage_dtype_reconciliation()
    transfer_plan = byte_transfer_plan(inventory)
    receipt = preparation_receipt(
        a_commit=a_commit,
        index=index,
        inventory=inventory,
        dtype_decision=dtype_decision,
        transfer_plan=transfer_plan,
    )
    documents = {
        "byte_transfer_plan.json": transfer_plan,
        "preparation_receipt.json": receipt,
        "storage_dtype_reconciliation.json": dtype_decision,
        "validation_receipt.json": _validation_receipt(index, inventory, receipt),
    }
    violations: list[str] = []
    for name, document in sorted(documents.items()):
        violations.extend(_protected_false_violations(document, name))
    if violations:
        raise PreparationError("protected_claim_violation", "; ".join(violations))
    documents["sha256_inventory.json"] = {
        "file_count": len(documents) + 1,
        "files": {
            name: _sha256(_json_bytes(document))
            for name, document in sorted(documents.items())
        },
        "inventory_excludes_self": True,
        "schema_id": f"{SCHEMA_PREFIX}-status-sha256-inventory",
        "schema_version": SCHEMA_VERSION,
    }
    if set(documents) != set(STATUS_OUTPUT_PATHS):
        raise PreparationError("path_inventory_changed", str(sorted(documents)))
    STATUS_ROOT.mkdir(parents=True, exist_ok=True)
    for name, document in sorted(documents.items()):
        (STATUS_ROOT / name).write_bytes(_json_bytes(document))
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Person A's local 66-cell preparation package."
    )
    parser.add_argument(
        "stage",
        choices=("frame-maps", "receipts", "all"),
        help=(
            "frame-maps materializes the 66 production frame maps and the "
            "accepted-input manifest; receipts publishes the dtype "
            "reconciliation, transfer plan, and preparation receipt."
        ),
    )
    arguments = parser.parse_args()
    a_commit = verify_authorities()
    if arguments.stage in ("frame-maps", "all"):
        result = write_data_package()
        index = result["frame_map_index"]
        print(
            f"frame maps: {index['trajectory_count']} trajectories, "
            f"{index['model_frame_key_count']} model frames"
        )
    if arguments.stage in ("receipts", "all"):
        documents = write_status_package(a_commit)
        receipt = documents["preparation_receipt.json"]
        print(
            "receipts: local_preparation_complete="
            f"{receipt['extraction_readiness']['person_a_66_local_preparation_complete']}"
            f" dtype={documents['storage_dtype_reconciliation.json']['decision']}"
        )


if __name__ == "__main__":
    main()
