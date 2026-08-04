"""Ingest the certified post-C1 C6A package into Person E provenance.

This builder is deliberately bounded to the certified Person C package and
the accepted Person E v0.2 homography authority.  It verifies literal bytes,
builds additive episode registry records, and emits the E-to-A handoff.  It
does not execute C6A or modify any historical registry or homography package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_REL = "docs/status/person_e_c6a_provenance_closure_v0_1"
DEFAULT_PERSON_C_ROOT = Path(r"C:\Users\lollo\MineOcclude-Person-C-C1-C6A")

PERSON_C_COMMIT = "b810bae554ba4f31018d39beb304c9b936387ca4"
PERSON_E_REFIT_COMMIT = "c46d838b5a277e71a39090900f9e8ca814b743a7"
CANONICAL_C6A_ID = "person-c-c6a-post-c1-v0.1"
EXPECTED_EPISODE_COUNT = 66
ACCEPTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"
ACCEPTED_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)
REPAIRED_JAR_SHA256 = (
    "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
)

C_PACKAGE_REL = "docs/status/person_c_c6a_completion_v0_1/package_manifest.json"
C_PACKAGE_SHA256 = (
    "612b03fea372d10c5f5b87cb581dd5f993035112e16aa1de7341801bdc35a9ef"
)
C_HANDOFF_REL = (
    "docs/status/person_c_c6a_completion_v0_1/"
    "person_c_to_person_e_c6a_provenance_handoff.json"
)
C_HANDOFF_SHA256 = (
    "4f66c49c28deb8beba8410468bf876f7b1e3bfabaa84dc0f561b602e4eda5336"
)

E_REFIT_ROOT_REL = "data/handoff_e/person_e_v0_4_homography_refit_v0_2"
E_PACKAGE_REL = f"{E_REFIT_ROOT_REL}/package_manifest.json"
E_PACKAGE_SHA256 = (
    "f5a90bb97d0f54e754cfa11c971532d8d2e29cbe6ce0151dfeb17faae61a17bc"
)
E_HANDOFF_REL = f"{E_REFIT_ROOT_REL}/person_e_to_person_c_refit_handoff.json"
E_HANDOFF_SHA256 = (
    "0937dcc6335927a1c724e8e3f1510be94b76ff91e3583c10d59d10ec60fb38ca"
)

REGISTRY_SCHEMA_ID = "person-e-c6a-canonical-registry-schema-v0.1"
REGISTRY_SCHEMA_VERSION = "person-e-c6a-canonical-registry-v0.1"
RECEIPT_SCHEMA_ID = "person-e-c6a-provenance-receipt-schema-v0.1"
RECEIPT_SCHEMA_VERSION = "person-e-c6a-provenance-receipt-v0.1"
HANDOFF_SCHEMA_ID = "person-e-to-person-a-c6a-provenance-handoff-schema-v0.1"
HANDOFF_SCHEMA_VERSION = "person-e-to-person-a-c6a-provenance-handoff-v0.1"
E4_STATUS_SCHEMA_VERSION = "person-e-e4.1-status-v0.1"
VALIDATION_SCHEMA_VERSION = "person-e-c6a-provenance-validation-v0.1"
INVENTORY_SCHEMA_VERSION = "person-e-c6a-provenance-sha256-inventory-v0.1"

A6_6_STATEMENT = (
    "A6.6 may consume this canonical C6A provenance. This handoff does not "
    "perform A6.6."
)

JSON_OUTPUT_SCHEMAS: dict[str, tuple[str, frozenset[str]]] = {
    "finalization.json": (
        "mineocclude-c6a-finalization-json-v0.1",
        frozenset(
            {
                "episode_id",
                "state",
                "ticks",
                "rng_source",
                "schedule_draws_consumed",
                "failure_reason",
            }
        ),
    ),
    "layout_meta.json": (
        "mineocclude-c6a-layout-meta-json-v0.1",
        frozenset({"layout_id", "wall_axis", "wall_ortho", "scene", "markers"}),
    ),
    "reset_result.json": (
        "mineocclude-c6a-reset-result-json-v0.1",
        frozenset(
            {
                "episode_id",
                "layout_id",
                "scene",
                "seed",
                "v",
                "q",
                "expected_target_count",
                "observed_target_count",
                "start_axis_pos",
                "rng_source",
                "schedule_draws",
                "target_count_ok",
                "lock_camera",
                "impulse_tick",
                "impulse_yaw_deg",
                "reveal_ticks",
            }
        ),
    ),
}

JSONL_OUTPUT_SCHEMAS: dict[str, tuple[str, frozenset[str]]] = {
    "lifecycle.jsonl": (
        "mineocclude-c6a-lifecycle-jsonl-v0.1",
        frozenset({"from", "to", "reason", "diagnostic_nanos"}),
    ),
    "server_state.jsonl": (
        "mineocclude-c6a-server-state-jsonl-v0.1",
        frozenset(
            {
                "episode_id",
                "server_tick",
                "layout_id",
                "regime",
                "scene",
                "seed",
                "v",
                "q",
                "hidden_frames",
                "noise_draw",
                "axis_pos",
                "axis_velocity",
                "sheep_x",
                "sheep_y",
                "sheep_z",
                "geometric_visible",
                "player_x",
                "player_y",
                "player_z",
                "player_yaw",
                "player_pitch",
                "server_epoch_nanos",
            }
        ),
    ),
    "client_tick.jsonl": (
        "mineocclude-c6a-client-tick-jsonl-v0.1",
        frozenset(
            {
                "episode_id",
                "server_tick",
                "render_frame_idx",
                "server_epoch_nanos",
                "client_recv_nanos",
                "client_capture_nanos",
                "frame_path",
            }
        ),
    ),
    "raw_actions.jsonl": (
        "mineocclude-c6a-raw-actions-jsonl-v0.1",
        frozenset(
            {
                "episode_id",
                "server_tick",
                "render_frame_idx",
                "action_idx",
                "forward",
                "back",
                "left",
                "right",
                "jump",
                "sneak",
                "sprint",
                "use",
                "attack",
                "drop",
                "pick_item",
                "hotbar",
                "camera_dx",
                "camera_dy",
            }
        ),
    ),
}

PNG_SCHEMA_ID = "image-png-1920x1046-v0.1"
REQUIRED_NON_FRAME_OUTPUTS = frozenset(
    {*JSON_OUTPUT_SCHEMAS, *JSONL_OUTPUT_SCHEMAS}
)


class ClosureError(RuntimeError):
    """Raised when a certified identity or required provenance binding fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ClosureError(message)


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


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClosureError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"invalid JSON {path}: {exc}") from exc


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line_number, line in enumerate(handle, start=1):
                require(bool(line.strip()), f"blank JSONL row {path}:{line_number}")
                row = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
                require(isinstance(row, dict), f"non-object JSONL row {path}:{line_number}")
                rows.append(row)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"invalid JSONL {path}: {exc}") from exc
    return rows


def git_head(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            encoding="utf-8",
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise ClosureError(f"cannot resolve Git HEAD for {path}") from exc


def verify_file(path: Path, expected_size: int, expected_sha256: str) -> None:
    require(path.is_file(), f"missing certified file: {path}")
    size, digest = sha256_file(path)
    require(size == expected_size, f"size mismatch: {path}")
    require(digest == expected_sha256, f"SHA-256 mismatch: {path}")


def verify_manifest_entry(root: Path, entry: dict[str, Any]) -> None:
    verify_file(root / entry["path"], entry["size_bytes"], entry["sha256"])


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    require(len(header) == 24, f"truncated PNG: {path}")
    require(header[:8] == b"\x89PNG\r\n\x1a\n", f"invalid PNG signature: {path}")
    require(header[12:16] == b"IHDR", f"missing PNG IHDR: {path}")
    return struct.unpack(">II", header[16:24])


def registry_schema() -> dict[str, Any]:
    output_required = [
        "expected_record_count",
        "expected_schema_id",
        "path",
        "relative_path",
        "sha256",
        "side",
        "size_bytes",
    ]
    record_required = [
        "accepted_geometry",
        "canonical_c6a_id",
        "episode_id",
        "homography",
        "layout_id",
        "noise_schedule",
        "outputs",
        "record_status",
        "registry_record_id",
        "repaired_jar_sha256",
        "seed",
    ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": REGISTRY_SCHEMA_ID,
        "additionalProperties": False,
        "properties": {
            "canonical_c6a_id": {"const": CANONICAL_C6A_ID},
            "immutable": {"const": True},
            "record_count": {"const": EXPECTED_EPISODE_COUNT},
            "record_index": {"type": "array", "minItems": EXPECTED_EPISODE_COUNT},
            "records": {
                "type": "array",
                "minItems": EXPECTED_EPISODE_COUNT,
                "items": {
                    "type": "object",
                    "required": record_required,
                    "properties": {
                        "outputs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": output_required,
                            },
                        }
                    },
                },
            },
            "schema_version": {"const": REGISTRY_SCHEMA_VERSION},
            "source_registry_policy": {"type": "string"},
            "total_output_file_count": {"type": "integer", "minimum": 1},
        },
        "required": [
            "canonical_c6a_id",
            "immutable",
            "record_count",
            "record_index",
            "records",
            "schema_version",
            "source_registry_policy",
            "total_output_file_count",
        ],
        "title": "Person E canonical post-C1 C6A provenance registry",
        "type": "object",
    }


def receipt_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": RECEIPT_SCHEMA_ID,
        "additionalProperties": True,
        "properties": {
            "canonical_c6a_id": {"const": CANONICAL_C6A_ID},
            "canonical_registry_records_complete": {"const": True},
            "e4_1_complete": {"const": True},
            "immutable": {"const": True},
            "schema_version": {"const": RECEIPT_SCHEMA_VERSION},
            "status": {"const": "PASS"},
            "unresolved_blockers": {"maxItems": 0, "type": "array"},
            "valid_episode_count": {"const": EXPECTED_EPISODE_COUNT},
        },
        "required": [
            "canonical_c6a_id",
            "canonical_registry_records_complete",
            "e4_1_complete",
            "immutable",
            "schema_version",
            "status",
            "unresolved_blockers",
            "valid_episode_count",
        ],
        "title": "Person E canonical C6A provenance receipt",
        "type": "object",
    }


def handoff_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": HANDOFF_SCHEMA_ID,
        "additionalProperties": True,
        "properties": {
            "a6_6_provenance_consumption_authorized": {"const": True},
            "a6_6_provenance_consumption_statement": {"const": A6_6_STATEMENT},
            "canonical_c6a_id": {"const": CANONICAL_C6A_ID},
            "immutable": {"const": True},
            "schema_version": {"const": HANDOFF_SCHEMA_VERSION},
            "status": {"const": "READY_FOR_A6_6_PROVENANCE_CONSUMPTION"},
            "unresolved_blockers": {"maxItems": 0, "type": "array"},
        },
        "required": [
            "a6_6_provenance_consumption_authorized",
            "a6_6_provenance_consumption_statement",
            "accepted_geometry",
            "canonical_c6a_id",
            "canonical_registry",
            "person_c_c6a_handoff",
            "person_c_c6a_package",
            "person_e_refit_handoff",
            "person_e_refit_package",
            "provenance_receipt",
            "schema_version",
            "status",
            "unresolved_blockers",
        ],
        "title": "Person E to Person A canonical C6A provenance handoff",
        "type": "object",
    }


def _validate_exact_keys(row: dict[str, Any], expected: frozenset[str], path: Path) -> None:
    require(frozenset(row) == expected, f"schema key mismatch: {path}")


def _validate_sequence(values: Iterable[Any], count: int, identity: str) -> None:
    require(list(values) == list(range(count)), f"nonconsecutive index in {identity}")


def validate_output(
    item: dict[str, Any],
    episode: dict[str, Any],
    *,
    expected_server_root: Path,
    expected_client_root: Path,
) -> dict[str, Any]:
    path = Path(item["path"])
    verify_file(path, item["size_bytes"], item["sha256"])
    side = item["side"]
    require(side in {"server", "client"}, f"invalid output side: {path}")
    expected_root = expected_server_root if side == "server" else expected_client_root
    require(path.parent == expected_root or expected_root in path.parents, f"output root mismatch: {path}")
    relative = item["relative_path"].replace("\\", "/")
    require(path == expected_root / Path(relative), f"relative output path mismatch: {path}")

    record_count: int
    schema_id: str
    if relative in JSON_OUTPUT_SCHEMAS:
        schema_id, expected_keys = JSON_OUTPUT_SCHEMAS[relative]
        row = load_json(path)
        require(isinstance(row, dict), f"JSON output is not an object: {path}")
        _validate_exact_keys(row, expected_keys, path)
        record_count = 1
        if relative == "finalization.json":
            require(row["episode_id"] == episode["episode_id"], f"finalization episode mismatch: {path}")
            require(row["state"] == "COMPLETED", f"finalization state mismatch: {path}")
            require(row["ticks"] == episode["completed_record_ticks"], f"finalization count mismatch: {path}")
            expected_draws_consumed = row["ticks"] if episode["target_required"] else -1
            require(
                row["schedule_draws_consumed"] == expected_draws_consumed,
                f"schedule consumption mismatch: {path}",
            )
            require(
                row["rng_source"]
                == ("immutable_numpy_schedule" if episode["target_required"] else "no_target"),
                f"finalization RNG source mismatch: {path}",
            )
            require(row["failure_reason"] is None, f"finalization failure: {path}")
        elif relative == "layout_meta.json":
            require(row["layout_id"] == episode["layout_id"], f"layout metadata mismatch: {path}")
            require(len(row["markers"]) == 4, f"marker cardinality mismatch: {path}")
        else:
            require(row["episode_id"] == episode["episode_id"], f"reset episode mismatch: {path}")
            require(row["layout_id"] == episode["layout_id"], f"reset layout mismatch: {path}")
            require(row["seed"] == episode["seed"], f"reset seed mismatch: {path}")
            require(row["target_count_ok"] is True, f"reset target check failed: {path}")
            require(row["schedule_draws"] == episode["schedule_draw_count"], f"reset schedule mismatch: {path}")
    elif relative in JSONL_OUTPUT_SCHEMAS:
        schema_id, expected_keys = JSONL_OUTPUT_SCHEMAS[relative]
        rows = load_jsonl(path)
        require(rows, f"empty JSONL output: {path}")
        for row in rows:
            _validate_exact_keys(row, expected_keys, path)
        record_count = len(rows)
        if relative == "lifecycle.jsonl":
            require(record_count == 5, f"lifecycle record count mismatch: {path}")
            require(rows[0]["from"] == "IDLE", f"lifecycle start mismatch: {path}")
            require(rows[-1]["to"] == "COMPLETED", f"lifecycle completion mismatch: {path}")
        else:
            require(
                all(row["episode_id"] == episode["episode_id"] for row in rows),
                f"JSONL episode identity mismatch: {path}",
            )
            if relative == "server_state.jsonl":
                require(record_count == episode["server_row_count"], f"server row count mismatch: {path}")
                _validate_sequence((row["server_tick"] for row in rows), record_count, str(path))
                require(all(row["layout_id"] == episode["layout_id"] for row in rows), f"server layout mismatch: {path}")
                require(all(row["seed"] == episode["seed"] for row in rows), f"server seed mismatch: {path}")
            elif relative == "client_tick.jsonl":
                require(record_count == episode["client_tick_count"], f"client row count mismatch: {path}")
                _validate_sequence((row["server_tick"] for row in rows), record_count, str(path))
                _validate_sequence((row["render_frame_idx"] for row in rows), record_count, str(path))
                require(
                    [row["frame_path"] for row in rows]
                    == [f"frames/{index:06d}.png" for index in range(record_count)],
                    f"client frame map mismatch: {path}",
                )
            else:
                require(record_count == episode["action_row_count"], f"action row count mismatch: {path}")
                _validate_sequence((row["server_tick"] for row in rows), record_count, str(path))
                _validate_sequence((row["render_frame_idx"] for row in rows), record_count, str(path))
                _validate_sequence((row["action_idx"] for row in rows), record_count, str(path))
    elif relative.startswith("frames/") and relative.endswith(".png"):
        require(side == "client", f"frame assigned to non-client side: {path}")
        width, height = png_dimensions(path)
        require((width, height) == (1920, 1046), f"PNG dimensions changed: {path}")
        schema_id = PNG_SCHEMA_ID
        record_count = 1
    else:
        raise ClosureError(f"unexpected C6A output: {path}")

    return {
        "expected_record_count": record_count,
        "expected_schema_id": schema_id,
        "path": str(path),
        "relative_path": relative,
        "sha256": item["sha256"],
        "side": side,
        "size_bytes": item["size_bytes"],
    }


def _index_unique(rows: list[dict[str, Any]], key: str, identity: str) -> dict[Any, dict[str, Any]]:
    result: dict[Any, dict[str, Any]] = {}
    for row in rows:
        value = row[key]
        require(value not in result, f"duplicate {identity}: {value}")
        result[value] = row
    return result


def _verify_e_refit() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    package_path = ROOT / E_PACKAGE_REL
    handoff_path = ROOT / E_HANDOFF_REL
    package_size, package_hash = sha256_file(package_path)
    handoff_size, handoff_hash = sha256_file(handoff_path)
    require(package_hash == E_PACKAGE_SHA256, "Person E refit package SHA-256 mismatch")
    require(handoff_hash == E_HANDOFF_SHA256, "Person E refit handoff SHA-256 mismatch")
    package = load_json(package_path)
    handoff = load_json(handoff_path)
    require(package["status"] == "PASS", "Person E refit package is not passing")
    require(package["all_tolerances_pass"] is True, "Person E refit tolerance gate failed")
    require(package["successor_homography_count"] == 6, "Person E homography cardinality changed")
    require(package["accepted_geometry_version"] == ACCEPTED_GEOMETRY_VERSION, "E package geometry version mismatch")
    require(package["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256, "E package geometry hash mismatch")
    require(handoff["status"] == "READY_FOR_C6A", "Person E handoff is not C6A-ready")
    require(handoff["c6a_execution_authorized"] is True, "Person E handoff does not authorize C6A")
    require(handoff["c6a_executed"] is False, "Person E handoff unexpectedly claims C6A execution")
    require(handoff["person_e_refit_package"]["sha256"] == E_PACKAGE_SHA256, "E handoff package binding mismatch")

    registry_path = ROOT / E_REFIT_ROOT_REL / "registry_records.json"
    registry = load_json(registry_path)
    records = _index_unique(registry["records"], "layout_id", "homography layout")
    require(set(records) == {f"layout_{index:02d}" for index in range(1, 7)}, "homography layout set changed")
    layout_results = _index_unique(handoff["layout_results"], "layout_id", "handoff layout")
    for layout_id, record in records.items():
        require(record["lifecycle_status"] == "accepted_successor", f"homography is not accepted: {layout_id}")
        require(record["tolerance_result"] is True, f"homography tolerance failed: {layout_id}")
        require(record["accepted_geometry_version"] == ACCEPTED_GEOMETRY_VERSION, f"homography geometry version mismatch: {layout_id}")
        require(record["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256, f"homography geometry hash mismatch: {layout_id}")
        homography_file = layout_results[layout_id]["homography_file"]
        verify_file(Path(homography_file["path"]), homography_file["size_bytes"], homography_file["sha256"])
        record["homography_file"] = homography_file
    preserved = {
        "person_e_v0_1_handoff": handoff["preserved_v0_1_handoff"],
        "person_e_v0_1_package": handoff["preserved_v0_1_package"],
    }
    for entry in preserved.values():
        verify_file(Path(entry["path"]), entry["size_bytes"], entry["sha256"])
    return (
        {"path": str(package_path), "sha256": package_hash, "size_bytes": package_size},
        {"path": str(handoff_path), "sha256": handoff_hash, "size_bytes": handoff_size},
        records,
        preserved,
    )


def build_documents(person_c_root: Path = DEFAULT_PERSON_C_ROOT) -> dict[str, bytes]:
    require(git_head(person_c_root) == PERSON_C_COMMIT, "Person C commit identity mismatch")

    c_package_path = person_c_root / C_PACKAGE_REL
    c_handoff_path = person_c_root / C_HANDOFF_REL
    c_package_size, c_package_hash = sha256_file(c_package_path)
    c_handoff_size, c_handoff_hash = sha256_file(c_handoff_path)
    require(c_package_hash == C_PACKAGE_SHA256, "C6A package SHA-256 mismatch")
    require(c_handoff_hash == C_HANDOFF_SHA256, "C-to-E handoff SHA-256 mismatch")
    c_package = load_json(c_package_path)
    c_handoff = load_json(c_handoff_path)
    require(c_package["canonical_c6a_id"] == CANONICAL_C6A_ID, "canonical C6A ID mismatch")
    require(c_handoff["canonical_c6a_id"] == CANONICAL_C6A_ID, "C handoff canonical ID mismatch")
    require(c_package["status"] == "PASS", "C6A package is not passing")
    require(c_handoff["status"] == "READY_FOR_PERSON_E_PROVENANCE_INGESTION", "C-to-E handoff is not ready")
    require(c_package["required_episode_count"] == EXPECTED_EPISODE_COUNT, "required episode count mismatch")
    require(c_package["completed_episode_count"] == EXPECTED_EPISODE_COUNT, "completed episode count mismatch")
    require(c_handoff["unresolved_blockers"] == [], "C-to-E handoff has blockers")
    require(c_handoff["accepted_geometry"] == {"version": ACCEPTED_GEOMETRY_VERSION, "sha256": ACCEPTED_GEOMETRY_SHA256}, "C-to-E geometry identity mismatch")
    require(c_handoff["repaired_jar_sha256"] == REPAIRED_JAR_SHA256, "repaired JAR identity mismatch")
    require(c_handoff["person_e_refit_commit"] == PERSON_E_REFIT_COMMIT, "Person E refit commit mismatch")
    require(c_handoff["person_e_refit_package_sha256"] == E_PACKAGE_SHA256, "C handoff E package binding mismatch")
    require(c_handoff["person_e_to_person_c_refit_handoff_sha256"] == E_HANDOFF_SHA256, "C handoff E handoff binding mismatch")

    for entry in c_package["component_files"]:
        verify_manifest_entry(person_c_root, entry)
    verify_manifest_entry(person_c_root, c_package["capture_manifest"])
    verify_manifest_entry(person_c_root, c_package["schedule_manifest"])

    completion_path = person_c_root / "docs/status/person_c_c6a_completion_v0_1/c6a_completion_receipt.json"
    completion = load_json(completion_path)
    required_completion = {
        "client_shutdown_clean": True,
        "completed_episode_count": EXPECTED_EPISODE_COUNT,
        "output_counts_valid": True,
        "output_schemas_valid": True,
        "recording_completed_for_all": True,
        "recording_started_for_all": True,
        "required_episode_count": EXPECTED_EPISODE_COUNT,
        "schedules_valid": True,
        "server_shutdown_clean": True,
        "status": "PASS",
        "target_checks_valid": True,
        "unresolved_blockers": [],
    }
    for key, expected in required_completion.items():
        require(completion.get(key) == expected, f"C6A completion mismatch for {key}")

    episode_inventory = load_json(person_c_root / c_handoff["episode_inventory"]["path"])
    schedule_inventory = load_json(person_c_root / c_handoff["schedule_inventory"]["path"])
    output_inventory = load_json(person_c_root / c_handoff["output_inventory"]["path"])
    capture_manifest = load_json(person_c_root / c_package["capture_manifest"]["path"])
    require(episode_inventory["canonical_c6a_id"] == CANONICAL_C6A_ID, "episode inventory identity mismatch")
    require(schedule_inventory["canonical_c6a_id"] == CANONICAL_C6A_ID, "schedule inventory identity mismatch")
    require(output_inventory["canonical_c6a_id"] == CANONICAL_C6A_ID, "output inventory identity mismatch")
    require(schedule_inventory["schedule_set_sha256"] == c_handoff["schedule_set_sha256"], "schedule set identity mismatch")

    episodes = _index_unique(episode_inventory["episodes"], "episode_id", "episode")
    schedules = _index_unique(schedule_inventory["schedules"], "episode_id", "schedule episode")
    capture_rows = _index_unique(capture_manifest["episodes"], "episode_id", "capture episode")
    require(len(episodes) == EXPECTED_EPISODE_COUNT, "episode inventory cardinality mismatch")
    require(set(episodes) == set(schedules) == set(capture_rows), "episode/schedule/capture identity set mismatch")

    e_package_ref, e_handoff_ref, homographies, preserved_refit = _verify_e_refit()
    output_rows_by_episode: dict[int, list[dict[str, Any]]] = {key: [] for key in episodes}
    seen_output_paths: set[str] = set()
    for item in output_inventory["files"]:
        episode_id = item["episode_id"]
        require(episode_id in episodes, f"output has unknown episode ID: {episode_id}")
        require(item["path"] not in seen_output_paths, f"duplicate output path: {item['path']}")
        seen_output_paths.add(item["path"])
        output_rows_by_episode[episode_id].append(item)
    require(len(seen_output_paths) == output_inventory["file_count"], "output inventory file count mismatch")

    records: list[dict[str, Any]] = []
    record_index: list[dict[str, Any]] = []
    for episode_id in sorted(episodes):
        episode = episodes[episode_id]
        schedule = schedules[episode_id]
        capture = capture_rows[episode_id]
        require(episode["status"] == "PASS", f"episode is not passing: {episode_id}")
        require(episode["recording_started"] is True, f"recording did not start: {episode_id}")
        require(episode["recording_completed"] is True, f"recording did not complete: {episode_id}")
        require(episode["target_check_valid"] is True, f"target check failed: {episode_id}")
        require(
            episode["target_observed_count"] == episode["target_expected_count"]
            and episode["target_expected_count"]
            == (1 if episode["target_required"] else 0),
            f"target cardinality mismatch: {episode_id}",
        )
        require(schedule["seed"] == episode["seed"] == capture["seed"], f"seed binding mismatch: {episode_id}")
        require(schedule["repository"]["sha256"] == episode["schedule_sha256"] == capture["noise_schedule"]["sha256"], f"schedule SHA binding mismatch: {episode_id}")
        require(
            schedule["draw_count"] == episode["schedule_draw_count"]
            and schedule["draw_count"] > 0,
            f"schedule count mismatch: {episode_id}",
        )
        require(capture["layout_id"] == episode["layout_id"], f"layout binding mismatch: {episode_id}")
        require(capture["accepted_geometry_version"] == ACCEPTED_GEOMETRY_VERSION, f"capture geometry version mismatch: {episode_id}")
        require(capture["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256, f"capture geometry hash mismatch: {episode_id}")
        require(capture["mineocclude_jar_sha256"] == REPAIRED_JAR_SHA256, f"capture JAR mismatch: {episode_id}")
        verify_manifest_entry(person_c_root, schedule["repository"])
        verify_file(Path(schedule["runtime_install"]["path"]), schedule["runtime_install"]["size_bytes"], schedule["runtime_install"]["sha256"])
        schedule_rows = load_jsonl(person_c_root / schedule["repository"]["path"])
        require(
            len(schedule_rows) == schedule["draw_count"] + 1,
            f"repository schedule row count mismatch: {episode_id}",
        )
        schedule_header, schedule_draws = schedule_rows[0], schedule_rows[1:]
        require(
            schedule_header["n_draws"] == schedule["draw_count"],
            f"schedule header count mismatch: {episode_id}",
        )
        require(schedule_header["seed"] == episode["seed"], f"schedule header seed mismatch: {episode_id}")
        _validate_sequence(
            (row["draw_idx"] for row in schedule_draws),
            schedule["draw_count"],
            f"schedule episode {episode_id}",
        )

        server_root = Path(episode["server_output_path"])
        client_root = Path(episode["client_output_path"])
        validated_outputs = [
            validate_output(
                item,
                episode,
                expected_server_root=server_root,
                expected_client_root=client_root,
            )
            for item in sorted(
                output_rows_by_episode[episode_id],
                key=lambda row: (row["side"], row["relative_path"]),
            )
        ]
        names = {row["relative_path"] for row in validated_outputs if not row["relative_path"].startswith("frames/")}
        require(names == REQUIRED_NON_FRAME_OUTPUTS, f"required output set mismatch: {episode_id}")
        frames = [row for row in validated_outputs if row["relative_path"].startswith("frames/")]
        require(len(frames) == episode["frame_count"], f"frame output count mismatch: {episode_id}")
        require(
            sorted(row["relative_path"] for row in frames)
            == [f"frames/{index:06d}.png" for index in range(episode["frame_count"])],
            f"frame filename sequence mismatch: {episode_id}",
        )

        homography = homographies[episode["layout_id"]]
        record_id = f"person-e-c6a-{CANONICAL_C6A_ID}-episode-{episode_id}-v0.1"
        record = {
            "accepted_geometry": {
                "sha256": ACCEPTED_GEOMETRY_SHA256,
                "version": ACCEPTED_GEOMETRY_VERSION,
            },
            "byte_hashes_valid": True,
            "canonical_c6a_id": CANONICAL_C6A_ID,
            "episode_id": episode_id,
            "expected_output_file_count": len(validated_outputs),
            "homography": {
                "artifact_path": homography["homography_file"]["path"],
                "artifact_sha256": homography["homography_file"]["sha256"],
                "homography_version_id": homography["homography_version_id"],
                "layout_id": episode["layout_id"],
                "person_e_refit_commit": PERSON_E_REFIT_COMMIT,
                "person_e_refit_handoff_sha256": E_HANDOFF_SHA256,
                "person_e_refit_package_sha256": E_PACKAGE_SHA256,
            },
            "layout_id": episode["layout_id"],
            "noise_schedule": {
                "draw_count": schedule["draw_count"],
                "path": schedule["repository"]["path"],
                "sha256": schedule["repository"]["sha256"],
            },
            "output_bundle_sha256": sha256_bytes(canonical_json(validated_outputs)),
            "output_counts_valid": True,
            "output_schemas_valid": True,
            "outputs": validated_outputs,
            "record_status": "accepted",
            "registry_record_id": record_id,
            "repaired_jar_sha256": REPAIRED_JAR_SHA256,
            "seed": episode["seed"],
        }
        record_hash = sha256_bytes(canonical_json(record))
        records.append(record)
        record_index.append(
            {
                "episode_id": episode_id,
                "registry_record_id": record_id,
                "registry_record_sha256": record_hash,
            }
        )

    total_outputs = sum(len(record["outputs"]) for record in records)
    require(total_outputs == output_inventory["file_count"], "registered output total mismatch")
    registry = {
        "canonical_c6a_id": CANONICAL_C6A_ID,
        "immutable": True,
        "record_count": len(records),
        "record_index": record_index,
        "records": records,
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "source_registry_policy": (
            "Additive Person E provenance bindings over certified Person C raw "
            "outputs; no historical registry record is altered."
        ),
        "total_output_file_count": total_outputs,
    }

    documents: dict[str, bytes] = {
        "canonical_registry_records.schema.json": canonical_json(registry_schema()),
        "canonical_registry_records.json": canonical_json(registry),
        "provenance_receipt.schema.json": canonical_json(receipt_schema()),
        "person_e_to_person_a_c6a_provenance_handoff.schema.json": canonical_json(handoff_schema()),
    }
    package_root = ROOT / PACKAGE_REL
    registry_ref = {
        "path": str(package_root / "canonical_registry_records.json"),
        "sha256": sha256_bytes(documents["canonical_registry_records.json"]),
        "size_bytes": len(documents["canonical_registry_records.json"]),
    }
    registry_schema_ref = {
        "path": str(package_root / "canonical_registry_records.schema.json"),
        "sha256": sha256_bytes(documents["canonical_registry_records.schema.json"]),
        "size_bytes": len(documents["canonical_registry_records.schema.json"]),
    }
    c_package_ref = {"path": str(c_package_path), "sha256": c_package_hash, "size_bytes": c_package_size}
    c_handoff_ref = {"path": str(c_handoff_path), "sha256": c_handoff_hash, "size_bytes": c_handoff_size}
    receipt = {
        "accepted_geometry": {"sha256": ACCEPTED_GEOMETRY_SHA256, "version": ACCEPTED_GEOMETRY_VERSION},
        "byte_hashes_valid": True,
        "canonical_c6a_id": CANONICAL_C6A_ID,
        "canonical_registry": registry_ref,
        "canonical_registry_record_count": len(records),
        "canonical_registry_records_complete": True,
        "canonical_registry_schema": registry_schema_ref,
        "certified_utc": completion["certified_utc"],
        "e4_1_complete": True,
        "expected_episode_count": EXPECTED_EPISODE_COUNT,
        "historical_preservation": {
            "existing_registry_entries_modified": False,
            "failed_calibrations_modified": False,
            "failed_closed_packages_modified": False,
            "historical_pilots_modified": False,
            "old_homographies_modified": False,
            **preserved_refit,
        },
        "immutable": True,
        "output_file_count": total_outputs,
        "person_c_certification_commit": PERSON_C_COMMIT,
        "person_c_c6a_handoff": c_handoff_ref,
        "person_c_c6a_package": c_package_ref,
        "person_e_refit_commit": PERSON_E_REFIT_COMMIT,
        "person_e_refit_handoff": e_handoff_ref,
        "person_e_refit_package": e_package_ref,
        "repaired_jar_sha256": REPAIRED_JAR_SHA256,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "PASS",
        "unresolved_blockers": [],
        "valid_episode_count": len(records),
    }
    documents["provenance_receipt.json"] = canonical_json(receipt)
    receipt_ref = {
        "path": str(package_root / "provenance_receipt.json"),
        "sha256": sha256_bytes(documents["provenance_receipt.json"]),
        "size_bytes": len(documents["provenance_receipt.json"]),
    }
    e4_status = {
        "canonical_c6a_id": CANONICAL_C6A_ID,
        "canonical_registry_records_complete": True,
        "e4_1_complete": True,
        "immutable": True,
        "provenance_receipt": receipt_ref,
        "repository_registry_requirements_pass": True,
        "schema_version": E4_STATUS_SCHEMA_VERSION,
        "status": "PASS",
        "unresolved_blockers": [],
    }
    documents["e4_1_status.json"] = canonical_json(e4_status)
    e4_status_ref = {
        "path": str(package_root / "e4_1_status.json"),
        "sha256": sha256_bytes(documents["e4_1_status.json"]),
        "size_bytes": len(documents["e4_1_status.json"]),
    }
    validation = {
        "accepted_geometry_identity_valid": True,
        "canonical_c6a_id": CANONICAL_C6A_ID,
        "canonical_registry_records_complete": True,
        "c6a_package_valid": True,
        "c_to_e_handoff_valid": True,
        "e4_1_complete": True,
        "e_refit_identity_valid": True,
        "expected_episode_count": EXPECTED_EPISODE_COUNT,
        "historical_artifacts_modified": False,
        "output_file_count": total_outputs,
        "output_hashes_valid": True,
        "output_record_counts_valid": True,
        "output_schemas_valid": True,
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "status": "PASS",
        "unresolved_blockers": [],
        "valid_episode_count": len(records),
    }
    documents["validation_receipt.json"] = canonical_json(validation)
    validation_ref = {
        "path": str(package_root / "validation_receipt.json"),
        "sha256": sha256_bytes(documents["validation_receipt.json"]),
        "size_bytes": len(documents["validation_receipt.json"]),
    }
    handoff_schema_ref = {
        "path": str(package_root / "person_e_to_person_a_c6a_provenance_handoff.schema.json"),
        "sha256": sha256_bytes(documents["person_e_to_person_a_c6a_provenance_handoff.schema.json"]),
        "size_bytes": len(documents["person_e_to_person_a_c6a_provenance_handoff.schema.json"]),
    }
    handoff = {
        "a6_6_provenance_consumption_authorized": True,
        "a6_6_provenance_consumption_statement": A6_6_STATEMENT,
        "a6_6_performed": False,
        "accepted_geometry": {"sha256": ACCEPTED_GEOMETRY_SHA256, "version": ACCEPTED_GEOMETRY_VERSION},
        "canonical_c6a_id": CANONICAL_C6A_ID,
        "canonical_registry": {
            **registry_ref,
            "record_count": len(records),
            "record_identities": record_index,
            "schema": registry_schema_ref,
            "total_output_file_count": total_outputs,
        },
        "e4_1_status": e4_status_ref,
        "handoff_schema": handoff_schema_ref,
        "immutable": True,
        "person_c_certification_commit": PERSON_C_COMMIT,
        "person_c_c6a_handoff": c_handoff_ref,
        "person_c_c6a_package": c_package_ref,
        "person_e_refit_commit": PERSON_E_REFIT_COMMIT,
        "person_e_refit_handoff": e_handoff_ref,
        "person_e_refit_package": e_package_ref,
        "provenance_receipt": receipt_ref,
        "repaired_jar_sha256": REPAIRED_JAR_SHA256,
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "status": "READY_FOR_A6_6_PROVENANCE_CONSUMPTION",
        "unresolved_blockers": [],
        "validation_receipt": validation_ref,
    }
    documents["person_e_to_person_a_c6a_provenance_handoff.json"] = canonical_json(handoff)

    inventory_files = []
    for name, raw in sorted(documents.items()):
        inventory_files.append({"path": name, "sha256": sha256_bytes(raw), "size_bytes": len(raw)})
    inventory = {
        "file_count": len(inventory_files) + 1,
        "files": inventory_files,
        "hash_algorithm": "sha256",
        "hash_source": "literal_file_bytes",
        "inventory_excludes_self": True,
        "schema_version": INVENTORY_SCHEMA_VERSION,
    }
    documents["sha256_inventory.json"] = canonical_json(inventory)
    validate_documents(documents)
    return documents


def validate_documents(documents: dict[str, bytes]) -> None:
    required = {
        "canonical_registry_records.json",
        "canonical_registry_records.schema.json",
        "e4_1_status.json",
        "person_e_to_person_a_c6a_provenance_handoff.json",
        "person_e_to_person_a_c6a_provenance_handoff.schema.json",
        "provenance_receipt.json",
        "provenance_receipt.schema.json",
        "sha256_inventory.json",
        "validation_receipt.json",
    }
    require(set(documents) == required, "closure document set mismatch")
    parsed = {
        name: json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        for name, raw in documents.items()
    }
    registry = parsed["canonical_registry_records.json"]
    require(registry["schema_version"] == REGISTRY_SCHEMA_VERSION, "registry schema version mismatch")
    require(registry["record_count"] == EXPECTED_EPISODE_COUNT, "registry record count mismatch")
    require(len(registry["records"]) == len(registry["record_index"]) == EXPECTED_EPISODE_COUNT, "registry index mismatch")
    require(len({row["registry_record_id"] for row in registry["records"]}) == EXPECTED_EPISODE_COUNT, "registry IDs are not unique")
    by_id = {row["registry_record_id"]: row for row in registry["records"]}
    for identity in registry["record_index"]:
        record = by_id[identity["registry_record_id"]]
        require(identity["episode_id"] == record["episode_id"], "registry episode identity mismatch")
        require(identity["registry_record_sha256"] == sha256_bytes(canonical_json(record)), "registry record identity hash mismatch")
    require(sum(len(row["outputs"]) for row in registry["records"]) == registry["total_output_file_count"], "registry output count mismatch")
    receipt = parsed["provenance_receipt.json"]
    require(receipt["status"] == "PASS" and receipt["e4_1_complete"] is True, "provenance receipt is not passing")
    handoff = parsed["person_e_to_person_a_c6a_provenance_handoff.json"]
    require(handoff["a6_6_provenance_consumption_authorized"] is True, "A6.6 provenance consumption is not authorized")
    require(handoff["a6_6_provenance_consumption_statement"] == A6_6_STATEMENT, "A6.6 statement mismatch")
    require(handoff["a6_6_performed"] is False, "handoff unexpectedly performs A6.6")
    require(handoff["provenance_receipt"]["sha256"] == sha256_bytes(documents["provenance_receipt.json"]), "handoff receipt binding mismatch")
    require(handoff["canonical_registry"]["sha256"] == sha256_bytes(documents["canonical_registry_records.json"]), "handoff registry binding mismatch")
    e4_status = parsed["e4_1_status.json"]
    require(e4_status["e4_1_complete"] is True, "E4.1 is not complete")
    inventory = parsed["sha256_inventory.json"]
    require(inventory["inventory_excludes_self"] is True, "inventory must exclude itself")
    require(inventory["file_count"] == len(documents), "inventory file count mismatch")
    for entry in inventory["files"]:
        raw = documents[entry["path"]]
        require(entry["size_bytes"] == len(raw), f"inventory size mismatch: {entry['path']}")
        require(entry["sha256"] == sha256_bytes(raw), f"inventory hash mismatch: {entry['path']}")


def load_package(package_root: Path) -> dict[str, bytes]:
    require(package_root.is_dir(), f"missing closure package: {package_root}")
    return {path.name: path.read_bytes() for path in package_root.iterdir() if path.is_file()}


def validate_package(package_root: Path) -> None:
    documents = load_package(package_root)
    validate_documents(documents)
    for name, raw in documents.items():
        require(raw == canonical_json(json.loads(raw, object_pairs_hook=_reject_duplicate_keys)), f"noncanonical JSON: {name}")


def write_exclusive(package_root: Path, documents: dict[str, bytes]) -> None:
    require(not package_root.exists(), f"refusing to overwrite immutable package: {package_root}")
    package_root.mkdir(parents=True)
    for name, raw in sorted(documents.items()):
        with (package_root / name).open("xb") as handle:
            handle.write(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--person-c-root", type=Path, default=DEFAULT_PERSON_C_ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / PACKAGE_REL)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        validate_package(args.output)
    else:
        documents = build_documents(args.person_c_root)
        write_exclusive(args.output, documents)
        validate_package(args.output)
    print("PERSON_E_C6A_PROVENANCE_CLOSURE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
