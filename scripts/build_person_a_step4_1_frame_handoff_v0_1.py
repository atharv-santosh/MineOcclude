#!/usr/bin/env python3
"""Build and verify the Person A Step 4.1 frame handoff.

This is a metadata-only, fail-closed builder.  It reads accepted Git objects
and retained external artifacts, but it never loads a model, decodes frames
through the Person A adapter, runs a probe/baseline, or reads U4 output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_REL = Path(
    "docs/status/person_a_phase4_step4_1_frame_handoff_v0_1"
)
PACKAGE_ROOT = ROOT / PACKAGE_REL

STARTING_AUTHORITY = "55776dc88302b89b52eef483a710fbf6811cf536"
PERSON_B_CONTRACT_COMMIT = "265cbbb394ee481439397879ad9a99c9038bf4cd"
PERSON_B_RATIFICATION_COMMIT = "c9a519b42cf651e05f5b4f640fda6e1a0aed3e7c"
PERSON_B_STEP6_6_COMMIT = "e39fef4a59142a84dfb5991d51deeb506eb23a7b"
PERSON_C_ACCEPTANCE_COMMIT = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"
PERSON_D_STARTING_AUTHORITY = "853e0acadf050a0b1f318b399b524e57379d03bf"
PERSON_E_HANDOFF_COMMIT = "21d83c19c9d8f36c4dbeeaf45d4626eaf082e7a7"
PERSON_E_ACCEPTANCE_COMMIT = "5bbe7c7021fe3b1c4c35c78fadfbd92ab51484e8"

FOLD_SHA256 = "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71"
TARGET_SHA256 = "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282"
PREPROCESS_HASH = "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
PREPROCESSING_PROFILE = (
    "mineworld_gradio_step_video_preprocessing@1.0:"
    + PREPROCESS_HASH
)
ANALYSIS_CONFIG_SHA256 = (
    "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
)

ACCEPTED_PILOTS = (
    "layout_00_ep9403",
    "layout_00_ep9441",
    "layout_01_ep9405",
    "layout_01_ep9442",
    "layout_02_ep9407",
    "layout_02_ep9432",
    "layout_03_ep9404",
    "layout_03_ep9443",
    "layout_04_ep9406",
    "layout_04_ep9444",
)
BASELINE_FAMILIES = (
    "last_seen",
    "constant_velocity",
    "grouped_shuffled",
    "time_only",
    "explicit_feature",
    "raw_pixel",
    "visible_history_q",
    "known_q_analytic",
)
SOURCE_CONTEXT_FAMILIES = (
    "last_seen",
    "constant_velocity",
    "time_only",
    "explicit_feature",
    "visible_history_q",
    "known_q_analytic",
)

APPROVED_INPUT_ROOT = Path(
    "/home/sagemaker-user/person-a-phase6-approved-inputs"
)
APPROVED_OUTPUT_ROOT = Path(
    "/home/sagemaker-user/person-a-phase6-approved-outputs"
)
PHASE6_PACKAGE_ROOT = (
    APPROVED_OUTPUT_ROOT
    / "person-a-phase6-ten-pilot-expansion-seed-20260725"
)
FFPROBE = Path("/home/sagemaker-user/tools/ffmpeg/bin/ffprobe")

B_CONTRACT_ROOT = (
    "docs/status/person_b_phase4_step4_1_baseline_family_contract_v0_2"
)
B_PRODUCTION_ROOT = (
    "docs/status/person_b_phase4_step4_1_production_handoff_v0_1"
)
E_HANDOFF_ROOT = "docs/status/person_e_phase6_to_step4_1_handoff_v0_1"
E_ACCEPTANCE_ROOT = (
    "docs/status/person_e_phase6_step6_6_provenance_acceptance_v0_1"
)
D_HANDOFF_ROOT = (
    "docs/status/person_d_phase4_step4_1_registry_v2_handoff_v0_1"
)

SOURCE_FILE_FIELDS = {
    "capture_package": (
        "capture_package_v0_1.json",
        "capture_package_byte_size",
        "capture_package_sha256",
        "json",
    ),
    "frame_map": (
        "frame_map.jsonl",
        "frame_map_byte_size",
        "frame_map_sha256",
        "jsonl",
    ),
    "media": (
        "video_640x360.mp4",
        "media_byte_size",
        "media_sha256",
        "mp4",
    ),
    "normalized_actions": (
        "normalized_actions.jsonl",
        "normalized_actions_byte_size",
        "normalized_actions_sha256",
        "jsonl",
    ),
    "raw_actions": (
        "raw_actions.jsonl",
        "raw_actions_byte_size",
        "raw_actions_sha256",
        "jsonl",
    ),
    "server_state": (
        "server_state.jsonl",
        "state_byte_size",
        "state_sha256",
        "jsonl",
    ),
    "visibility": (
        "visibility.jsonl",
        "visibility_byte_size",
        "visibility_sha256",
        "jsonl",
    ),
}

PACKAGE_FILENAMES = (
    "authority_binding.json",
    "handoff_decision.json",
    "preprocessed_frame_gap_manifest.json",
    "preprocessing_contract.json",
    "source_context_inventory.json",
    "validation_receipt.json",
)


class HandoffError(RuntimeError):
    """One fail-closed discovery or validation error."""


def fail(message: str) -> None:
    raise HandoffError(message)


def canonical_json_bytes(value: object) -> bytes:
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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(*arguments: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        fail(f"command failed ({' '.join(arguments)}): {detail}")
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="strict").strip()


def git_object_bytes(commit: str, path: str) -> bytes:
    return run("git", "show", f"{commit}:{path}", binary=True)  # type: ignore[return-value]


def git_json(commit: str, path: str) -> Any:
    try:
        return json.loads(git_object_bytes(commit, path))
    except json.JSONDecodeError as error:
        fail(f"invalid JSON Git object {commit}:{path}: {error}")


def git_ref(commit: str, path: str, *, role: str) -> dict[str, object]:
    payload = git_object_bytes(commit, path)
    oid = run("git", "rev-parse", f"{commit}:{path}")
    return {
        "byte_size": len(payload),
        "git_blob_oid": oid,
        "git_commit": commit,
        "path": path,
        "role": role,
        "sha256": sha256_bytes(payload),
    }


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        fail(f"could not load JSON {path}: {error}")


def load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                row = json.loads(line)
                if not isinstance(row, dict):
                    fail(f"{path}:{line_number} is not a JSON object")
                rows.append(row)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"could not load JSONL {path}: {error}")
    return rows


def external_ref(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
    artifact_format: str,
) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        fail(f"required external artifact is absent or not an ordinary file: {path}")
    observed_size = path.stat().st_size
    if observed_size != expected_size:
        fail(f"external byte-size mismatch for {path}: {observed_size} != {expected_size}")
    observed_sha256 = sha256_file(path)
    if observed_sha256 != expected_sha256:
        fail(f"external SHA-256 mismatch for {path}: {observed_sha256} != {expected_sha256}")
    return {
        "byte_size": observed_size,
        "format": artifact_format,
        "path": str(path),
        "sha256": observed_sha256,
    }


def input_root(trajectory_id: str) -> Path:
    if trajectory_id == "layout_00_ep9403":
        return APPROVED_INPUT_ROOT / "person-a-phase6-layout-00-ep9403-seed-20260725"
    return (
        APPROVED_INPUT_ROOT
        / f"person-a-phase6-ten-pilot-expansion-seed-20260725-{trajectory_id}"
    )


def intake_row(trajectory_id: str, root: Path) -> dict[str, object]:
    document = load_json(root / "accepted_pilot_manifest.json")
    if trajectory_id == "layout_00_ep9403" and "intake_row" in document:
        row = document["intake_row"]
    else:
        rows = document.get("intake_rows")
        if not isinstance(rows, list):
            fail(f"accepted C intake rows unavailable for {trajectory_id}")
        matching = [row for row in rows if row.get("trajectory_id") == trajectory_id]
        if len(matching) != 1:
            fail(f"accepted C intake row is not unique for {trajectory_id}")
        row = matching[0]
    if not isinstance(row, dict):
        fail(f"accepted C intake row is invalid for {trajectory_id}")
    return row


def ffprobe_media(path: Path) -> dict[str, object]:
    if not FFPROBE.is_file() or not FFPROBE.stat().st_mode & 0o111:
        fail(f"existing ffprobe executable is unavailable: {FFPROBE}")
    payload = run(
        str(FFPROBE),
        "-v",
        "error",
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames",
        "-of",
        "json",
        str(path),
    )
    document = json.loads(payload)
    streams = document.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        fail(f"media must contain exactly one video stream: {path}")
    stream = streams[0]
    frame_count_text = stream.get("nb_read_frames", stream.get("nb_frames"))
    try:
        frame_count = int(frame_count_text)
    except (TypeError, ValueError):
        fail(f"ffprobe did not resolve frame count for {path}")
    return {
        "average_frame_rate": stream.get("avg_frame_rate"),
        "codec_name": stream.get("codec_name"),
        "frame_count": frame_count,
        "height": stream.get("height"),
        "pixel_format": stream.get("pix_fmt"),
        "real_frame_rate": stream.get("r_frame_rate"),
        "width": stream.get("width"),
    }


def no_u4_path(value: object) -> bool:
    if isinstance(value, Mapping):
        return all(no_u4_path(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return all(no_u4_path(item) for item in value)
    if not isinstance(value, str):
        return True
    segments = value.casefold().replace("\\", "/").split("/")
    return not any(segment == "u4" or segment.startswith("u4_") for segment in segments)


def concise_c_binding(binding: Mapping[str, object]) -> dict[str, object]:
    accepted = binding["accepted_artifact"]
    authorization = binding["exact_artifact_authorization"]
    manifest = binding["manifest"]
    verification = binding["byte_verification"]
    return {
        "accepted_artifact": accepted,
        "accepted_by_commit": binding["accepted_by_commit"],
        "authorization": {
            "authorization_id": authorization["authorization_id"],
            "authorization_record_id": authorization["authorization_record_id"],
            "authorization_record_sha256": authorization["authorization_record_sha256"],
            "authority_id": authorization["authority_id"],
            "decision": authorization["decision"],
            "owner_authority_revision": authorization["owner_authority_revision"],
        },
        "manifest": manifest,
        "verification": {
            "mode": verification["mode"],
            "verification_id": verification["verification_id"],
            "verified_sha256": verification["verified_sha256"],
            "verified_size_bytes": verification["verified_size_bytes"],
        },
    }


def validate_index(
    index_path: Path,
    *,
    trajectory_id: str,
    frame_rows: Sequence[Mapping[str, object]],
    state_rows: Sequence[Mapping[str, object]],
    frame_map_sha256: str,
    state_sha256: str,
    capture_sha256: str,
) -> dict[str, object]:
    document = load_json(index_path)
    rows = document.get("index_rows")
    if not isinstance(rows, list):
        fail(f"activation index has no rows: {index_path}")
    expected_count = len(frame_rows) * 20
    if len(rows) != expected_count:
        fail(f"activation row count mismatch for {trajectory_id}")
    scientific_keys: set[tuple[object, ...]] = set()
    run_ids: set[str] = set()
    code_shas: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            fail(f"activation index row is not a mapping for {trajectory_id}")
        frame_idx = row.get("global_model_frame_idx")
        if not isinstance(frame_idx, int) or not 0 <= frame_idx < len(frame_rows):
            fail(f"activation index has invalid frame identity for {trajectory_id}")
        expected_source_id = f"{trajectory_id}:render_frame:{frame_idx}"
        frame_row = frame_rows[frame_idx]
        state_row = state_rows[frame_idx]
        expected = {
            "accepted_manifest_hash": capture_sha256,
            "c_frame_map_row_sha256": sha256_bytes(canonical_json_bytes(dict(frame_row))),
            "c_frame_map_sha256": frame_map_sha256,
            "c_state_row_sha256": sha256_bytes(canonical_json_bytes(dict(state_row))),
            "c_state_sha256": state_sha256,
            "context_local_pair_idx": frame_idx % 16,
            "preprocess_hash": PREPROCESS_HASH,
            "source_frame_id": expected_source_id,
            "source_frame_idx": frame_idx,
            "source_tick": frame_idx,
            "trajectory_id": trajectory_id,
        }
        for field, expected_value in expected.items():
            if row.get(field) != expected_value:
                fail(f"activation index {field} mismatch for {trajectory_id}:{frame_idx}")
        key = (
            row.get("trajectory_id"),
            frame_idx,
            row.get("source_frame_id"),
            row.get("source_tick"),
            row.get("layer_idx"),
            row.get("hook_site"),
            row.get("checkpoint_hash"),
            row.get("preprocess_hash"),
            row.get("run_id"),
        )
        if key in scientific_keys:
            fail(f"duplicate activation scientific identity: {key}")
        scientific_keys.add(key)
        run_ids.add(row["run_id"])
        code_shas.add(row["code_sha"])
    if len(run_ids) != 1 or len(code_shas) != 1:
        fail(f"activation producing identity is not unique for {trajectory_id}")
    return {
        "activation_row_count": len(rows),
        "context_local_pair_idx_range": [0, 15],
        "extraction_code_commit": next(iter(code_shas)),
        "producing_run_id": next(iter(run_ids)),
        "scientific_identity_duplicate_count": 0,
    }


def build_documents() -> dict[str, object]:
    branch = run("git", "branch", "--show-current")
    if branch != "role/person-a-model":
        fail(f"wrong branch: {branch}")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", STARTING_AUTHORITY, "HEAD"],
        cwd=ROOT,
        check=False,
    ).returncode != 0:
        fail("Person A starting authority is not an ancestor of HEAD")

    b_contract = git_json(
        PERSON_B_CONTRACT_COMMIT,
        f"{B_CONTRACT_ROOT}/baseline_family_contract.json",
    )
    b_source_contexts = git_json(
        PERSON_B_CONTRACT_COMMIT,
        f"{B_CONTRACT_ROOT}/source_context_manifest.json",
    )
    fold = git_json(
        PERSON_B_RATIFICATION_COMMIT,
        f"{B_PRODUCTION_ROOT}/ten_pilot_frame_fold_manifest.json",
    )
    target = git_json(
        PERSON_B_RATIFICATION_COMMIT,
        f"{B_PRODUCTION_ROOT}/production_oracle_target_manifest.json",
    )
    e_handoff = git_json(
        PERSON_E_HANDOFF_COMMIT,
        f"{E_HANDOFF_ROOT}/phase6_artifact_handoff.json",
    )

    if tuple(b_source_contexts["accepted_pilot_ids"]) != ACCEPTED_PILOTS:
        fail("Person B source-context pilot identities drifted")
    if tuple(fold["accepted_pilot_ids"]) != ACCEPTED_PILOTS:
        fail("Person B fold pilot identities drifted")
    if tuple(target["accepted_pilot_ids"]) != ACCEPTED_PILOTS:
        fail("Person B target pilot identities drifted")
    if tuple(pilot["trajectory_id"] for pilot in e_handoff["pilots"]) != ACCEPTED_PILOTS:
        fail("Person E handoff pilot identities drifted")
    if b_contract["baseline_family_count"] != 8:
        fail("Person B baseline-family count drifted")
    if tuple(item["family_id"] for item in b_contract["baseline_families"]) != BASELINE_FAMILIES:
        fail("Person B baseline-family identities drifted")

    fold_ref = git_ref(
        PERSON_B_RATIFICATION_COMMIT,
        f"{B_PRODUCTION_ROOT}/ten_pilot_frame_fold_manifest.json",
        role="person_b",
    )
    target_ref = git_ref(
        PERSON_B_RATIFICATION_COMMIT,
        f"{B_PRODUCTION_ROOT}/production_oracle_target_manifest.json",
        role="person_b",
    )
    if fold_ref["sha256"] != FOLD_SHA256 or fold_ref["byte_size"] != 742601:
        fail("accepted fold-manifest identity mismatch")
    if target_ref["sha256"] != TARGET_SHA256 or target_ref["byte_size"] != 4934874:
        fail("accepted target-manifest identity mismatch")

    admitted = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in fold["memberships"]
    }
    excluded = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in fold["excluded_memberships"]
    }
    target_rows = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in target["rows"]
    }
    if len(admitted) != 1695 or len(excluded) != 179 or len(target_rows) != 1695:
        fail("accepted fold/target cardinality mismatch")
    if set(admitted) != set(target_rows) or set(admitted).intersection(excluded):
        fail("accepted fold/target identity coverage mismatch")

    b_context_by_id = {
        item["trajectory_id"]: item for item in b_source_contexts["source_contexts"]
    }
    e_pilot_by_id = {item["trajectory_id"]: item for item in e_handoff["pilots"]}
    trajectory_lineage_by_id = {
        item["trajectory_id"]: item for item in target["trajectory_lineage"]
    }

    pilot_records: list[dict[str, object]] = []
    source_frame_records: list[dict[str, object]] = []
    missing_preprocessed: list[dict[str, object]] = []
    global_frame_keys: set[tuple[str, int]] = set()
    external_file_count = 0

    for trajectory_id in ACCEPTED_PILOTS:
        e_pilot = e_pilot_by_id[trajectory_id]
        root = input_root(trajectory_id)
        intake = intake_row(trajectory_id, root)
        c_binding = concise_c_binding(e_pilot["source_input_registry_binding"])
        source_artifacts: dict[str, dict[str, object]] = {}
        parsed_jsonl: dict[str, list[dict[str, object]]] = {}

        for artifact_name, (filename, size_field, hash_field, artifact_format) in SOURCE_FILE_FIELDS.items():
            expected_size = intake.get(size_field)
            expected_sha256 = intake.get(hash_field)
            if expected_size is None or expected_sha256 is None:
                verified_name = artifact_name
                verified = intake.get("verified_artifacts", {}).get(verified_name, {})
                expected_size = verified.get("byte_size")
                expected_sha256 = verified.get("sha256")
            if not isinstance(expected_size, int) or not isinstance(expected_sha256, str):
                fail(f"accepted intake identity missing for {trajectory_id}:{artifact_name}")
            path = root / filename
            ref = external_ref(
                path,
                expected_size=expected_size,
                expected_sha256=expected_sha256,
                artifact_format=artifact_format,
            )
            source_artifacts[artifact_name] = ref
            external_file_count += 1
            if artifact_format == "jsonl":
                parsed_jsonl[artifact_name] = load_jsonl(path)

        capture = load_json(root / "capture_package_v0_1.json")
        frame_count = e_pilot["frame_count"]
        expected_capture = b_context_by_id[trajectory_id]["capture_package"]
        if (
            capture.get("trajectory_id") != trajectory_id
            or capture.get("media", {}).get("width") != 640
            or capture.get("media", {}).get("height") != 360
            or capture.get("media", {}).get("frame_count") != frame_count
            or float(capture.get("media", {}).get("fps", -1)) != 20.0
            or source_artifacts["capture_package"]["byte_size"] != expected_capture["byte_size"]
            or source_artifacts["capture_package"]["sha256"] != expected_capture["sha256"]
        ):
            fail(f"capture-package contract mismatch for {trajectory_id}")

        frame_rows = parsed_jsonl["frame_map"]
        state_rows = parsed_jsonl["server_state"]
        if len(frame_rows) != frame_count or len(state_rows) != frame_count:
            fail(f"source frame/state count mismatch for {trajectory_id}")
        for stream_name, rows in parsed_jsonl.items():
            if len(rows) != frame_count:
                fail(f"source stream count mismatch for {trajectory_id}:{stream_name}")
            embedded_name = "server_state" if stream_name == "server_state" else stream_name
            if capture.get("streams", {}).get(embedded_name) != rows:
                fail(f"external/embedded source stream mismatch for {trajectory_id}:{stream_name}")

        media_probe = ffprobe_media(root / "video_640x360.mp4")
        if (
            media_probe["width"] != 640
            or media_probe["height"] != 360
            or media_probe["frame_count"] != frame_count
            or media_probe["average_frame_rate"] != "20/1"
        ):
            fail(f"media schema/dimension mismatch for {trajectory_id}")
        source_artifacts["media"]["ffprobe"] = media_probe

        activation = e_pilot["activation"]
        activation_ref = activation["activation_index"]
        activation_path = Path(activation_ref["path"])
        validated_activation_ref = external_ref(
            activation_path,
            expected_size=activation_ref["byte_size"],
            expected_sha256=activation_ref["sha256"],
            artifact_format="person-a-activation-index-v2-json",
        )
        external_file_count += 1
        index_validation = validate_index(
            activation_path,
            trajectory_id=trajectory_id,
            frame_rows=frame_rows,
            state_rows=state_rows,
            frame_map_sha256=source_artifacts["frame_map"]["sha256"],
            state_sha256=source_artifacts["server_state"]["sha256"],
            capture_sha256=source_artifacts["capture_package"]["sha256"],
        )
        validated_activation_ref.update(
            {
                "producing_commit": activation_ref["producing_commit"],
                "producing_role": "person_a",
                "schema_version": activation_ref["schema_version"],
            }
        )
        inventory_ref = activation["external_inventory_copy"]
        validated_inventory_ref = external_ref(
            Path(inventory_ref["path"]),
            expected_size=inventory_ref["byte_size"],
            expected_sha256=inventory_ref["sha256"],
            artifact_format="json",
        )
        external_file_count += 1
        committed_inventory = activation["committed_inventory"]
        observed_committed_inventory = git_ref(
            committed_inventory["git_commit"],
            committed_inventory["path"],
            role="person_a",
        )
        if (
            observed_committed_inventory["sha256"] != committed_inventory["sha256"]
            or observed_committed_inventory["byte_size"] != committed_inventory["byte_size"]
            or validated_inventory_ref["sha256"] != committed_inventory["sha256"]
        ):
            fail(f"Person A inventory receipt mismatch for {trajectory_id}")

        target_lineage = trajectory_lineage_by_id[trajectory_id]
        if (
            e_pilot["fold_idx"] != target_lineage["fold_idx"]
            or e_pilot["layout_id"] != target_lineage["layout_id"]
            or frame_count != target_lineage["source_frame_count"]
            or source_artifacts["capture_package"]["sha256"]
            != target_lineage["accepted_c_manifest_sha256"]
        ):
            fail(f"fold/target pilot lineage mismatch for {trajectory_id}")

        pilot_admitted_count = 0
        pilot_excluded_count = 0
        for frame_idx, (frame_row, state_row) in enumerate(zip(frame_rows, state_rows, strict=True)):
            exact_identity = {
                "model_frame_idx": frame_idx,
                "render_frame_idx": frame_idx,
                "server_tick": frame_idx,
                "trajectory_id": trajectory_id,
            }
            if any(
                frame_row.get(field) != expected or state_row.get(field) != expected
                for field, expected in exact_identity.items()
            ):
                fail(f"source identity mismatch for {trajectory_id}:{frame_idx}")
            key = (trajectory_id, frame_idx)
            if key in global_frame_keys:
                fail(f"duplicate global frame identity: {key}")
            global_frame_keys.add(key)
            admission = admitted.get(key)
            exclusion = excluded.get(key)
            if (admission is None) == (exclusion is None):
                fail(f"frame is neither exclusively admitted nor excluded: {key}")
            source_frame_id = f"{trajectory_id}:render_frame:{frame_idx}"
            record: dict[str, object] = {
                "accepted_c_manifest_sha256": source_artifacts["capture_package"]["sha256"],
                "c_frame_map_row_sha256": sha256_bytes(canonical_json_bytes(dict(frame_row))),
                "c_frame_map_sha256": source_artifacts["frame_map"]["sha256"],
                "c_state_row_sha256": sha256_bytes(canonical_json_bytes(dict(state_row))),
                "c_state_sha256": source_artifacts["server_state"]["sha256"],
                "context_idx": frame_idx // 16,
                "context_local_pair_idx": frame_idx % 16,
                "global_frame_identity": f"{trajectory_id}:{frame_idx}",
                "global_model_frame_idx": frame_idx,
                "layout_id": e_pilot["layout_id"],
                "model_frame_idx": frame_idx,
                "pilot_id": trajectory_id,
                "source_frame_id": source_frame_id,
                "source_frame_idx": frame_idx,
                "source_tick": frame_idx,
                "trajectory_id": trajectory_id,
            }
            if admission is not None:
                target_row = target_rows[key]
                if (
                    admission["fold_idx"] != e_pilot["fold_idx"]
                    or admission["source_frame_id"] != source_frame_id
                    or target_row["fold_idx"] != admission["fold_idx"]
                    or target_row["source_frame_id"] != source_frame_id
                    or target_row["c_frame_map_row_sha256"] != record["c_frame_map_row_sha256"]
                    or target_row["c_state_row_sha256"] != record["c_state_row_sha256"]
                ):
                    fail(f"admitted source/target identity mismatch for {key}")
                target_names = ["mu_oracle_blocks"]
                if target_row.get("log_sigma_oracle") is not None:
                    target_names.insert(0, "log_sigma_oracle")
                record["fold_binding"] = {
                    "analysis_scopes": admission["analysis_scopes"],
                    "fold_idx": admission["fold_idx"],
                    "status": "admitted",
                }
                record["target_binding"] = {
                    "available_target_names": target_names,
                    "target_id": target_row["target_id"],
                    "target_manifest_sha256": TARGET_SHA256,
                }
                missing_preprocessed.append(
                    {
                        "expected_content_sha256_record_present": False,
                        "expected_payload_byte_size": 3 * 224 * 384 * 4,
                        "fold_idx": admission["fold_idx"],
                        "global_frame_identity": f"{trajectory_id}:{frame_idx}",
                        "model_frame_idx": frame_idx,
                        "required_by_baseline_families": ["raw_pixel"],
                        "source_frame_id": source_frame_id,
                        "source_tick": frame_idx,
                        "status": "missing_not_serialized_by_accepted_run",
                        "trajectory_id": trajectory_id,
                    }
                )
                pilot_admitted_count += 1
            else:
                record["fold_binding"] = {
                    "exclusion_reason": exclusion["exclusion_reason"],
                    "status": "excluded",
                }
                record["target_binding"] = {
                    "status": "not_admitted",
                    "target_manifest_sha256": TARGET_SHA256,
                }
                pilot_excluded_count += 1
            source_frame_records.append(record)

        if (
            pilot_admitted_count != target_lineage["admitted_target_row_count"]
            or pilot_excluded_count != target_lineage["excluded_frame_count"]
        ):
            fail(f"per-pilot fold cardinality mismatch for {trajectory_id}")

        pilot_records.append(
            {
                "accepted_c_manifest_binding": c_binding,
                "admitted_frame_count": pilot_admitted_count,
                "condition_role": e_pilot["condition_role"],
                "control": e_pilot["control"],
                "excluded_frame_count": pilot_excluded_count,
                "fold_idx": e_pilot["fold_idx"],
                "frame_count": frame_count,
                "layout_id": e_pilot["layout_id"],
                "person_a_index_binding": {
                    "accepted_by_commit": activation["accepted_by_commit"],
                    "activation_index": validated_activation_ref,
                    "committed_inventory": observed_committed_inventory,
                    "external_inventory_copy": validated_inventory_ref,
                    "index_validation": index_validation,
                    "producer_contract_commit": activation["producer_contract_commit"],
                    "runtime_execution_commit": activation["runtime_execution_commit"],
                    "status": activation["status"],
                },
                "source_artifacts": source_artifacts,
                "source_context_direct_input_eligibility": {
                    family: family in SOURCE_CONTEXT_FAMILIES
                    for family in BASELINE_FAMILIES
                },
                "source_context_id": f"person_a_source_context__{trajectory_id}",
                "target_lineage": target_lineage,
                "trajectory_id": trajectory_id,
            }
        )

    if len(global_frame_keys) != 1874 or len(source_frame_records) != 1874:
        fail("complete source-frame inventory cardinality mismatch")
    if len(missing_preprocessed) != 1695:
        fail("required preprocessed-frame gap cardinality mismatch")
    if external_file_count != 90:
        fail(f"external referenced-file count mismatch: {external_file_count}")

    preprocessing_contract = {
        "content_hash_rule": "sha256(C-order bytes of the finite float32 CHW array)",
        "implementation_authority": STARTING_AUTHORITY,
        "operations_in_order": [
            "require source NumPy array shape (360, 640, 3) and dtype uint8",
            "make the source BGR array C-contiguous",
            "convert BGR to RGB with cv2.cvtColor(COLOR_BGR2RGB)",
            "resize RGB to width 384 and height 224 with cv2.INTER_LINEAR",
            "transpose HWC to CHW",
            "cast to float32 and divide by float32(255.0)",
            "normalize with (tensor - float32(0.5)) / float32(0.5)",
            "make the resulting tensor C-contiguous",
        ],
        "output_contract": {
            "channels": 3,
            "color_order": "RGB",
            "dtype": "float32",
            "height": 224,
            "layout": "CHW",
            "payload_byte_size": 1032192,
            "shape": [3, 224, 384],
            "value_range_inclusive": [-1.0, 1.0],
            "width": 384,
        },
        "preprocess_hash": PREPROCESS_HASH,
        "preprocessing_profile": PREPROCESSING_PROFILE,
        "runtime_lifetime": {
            "accepted_phase6_behavior": "preprocessed frames existed only in process memory during Step 6.3",
            "content_sha256_records_retained": False,
            "serialized_frame_payloads_retained": False,
        },
        "schema_id": "person-a-step4-1-preprocessing-contract-v0-1",
        "schema_version": "1.0",
        "source_contract": {
            "channels": 3,
            "color_order": "BGR",
            "dtype": "uint8",
            "height": 360,
            "layout": "HWC",
            "width": 640,
        },
    }

    authority_binding = {
        "authorities": {
            "person_a_ten_pilot_completion": STARTING_AUTHORITY,
            "person_b_baseline_input_v0_2": PERSON_B_CONTRACT_COMMIT,
            "person_b_step4_1_production_ratification": PERSON_B_RATIFICATION_COMMIT,
            "person_b_step6_6_pass": PERSON_B_STEP6_6_COMMIT,
            "person_c_ten_pilot_acceptance": PERSON_C_ACCEPTANCE_COMMIT,
            "person_d_recorded_starting_authority": PERSON_D_STARTING_AUTHORITY,
            "person_e_phase6_acceptance": PERSON_E_ACCEPTANCE_COMMIT,
            "person_e_phase6_to_step4_1_handoff": PERSON_E_HANDOFF_COMMIT,
        },
        "bindings": {
            "analysis_config_sha256": ANALYSIS_CONFIG_SHA256,
            "fold_manifest": fold_ref,
            "person_b_predictions_direct_input_to_person_d": False,
            "preprocess_hash": PREPROCESS_HASH,
            "target_manifest": target_ref,
        },
        "person_a_contract_sources": [
            git_ref(STARTING_AUTHORITY, path, role="person_a")
            for path in (
                "scripts/run_person_a_phase6_single_pilot_sagemaker.py",
                "scripts/run_person_a_phase6_ten_pilot_sagemaker.py",
                "src/mineocclude/activations/store_v2.py",
                "src/mineocclude/models/mineworld_adapter.py",
                "src/mineocclude/models/_mineworld_adapter_wave2.py",
                "src/mineocclude/models/_mineworld_adapter_wave4.py",
                "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725/artifact_manifest.json",
                "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725/completion_report.json",
            )
        ],
        "person_b_v0_2_contract_sources": [
            git_ref(PERSON_B_CONTRACT_COMMIT, path, role="person_b")
            for path in (
                f"{B_CONTRACT_ROOT}/authority_binding.json",
                f"{B_CONTRACT_ROOT}/baseline_family_contract.json",
                f"{B_CONTRACT_ROOT}/contract_ratification.json",
                f"{B_CONTRACT_ROOT}/execution_blocker_receipt.json",
                f"{B_CONTRACT_ROOT}/source_context_manifest.json",
                f"{B_CONTRACT_ROOT}/validation_receipt.json",
                "schemas/analysis/person_b_baseline_input_v0_2.schema.json",
                "scripts/validate_person_b_step4_1_baseline_family_inputs_v0_2.py",
                "src/mineocclude/contracts/baseline_family_inputs.py",
            )
        ],
        "person_d_contract_sources": [
            git_ref(PERSON_D_STARTING_AUTHORITY, path, role="person_d")
            for path in (
                "docs/baselines/person_d_phase0.md",
                "docs/baselines/person_d_phase1.md",
                f"{D_HANDOFF_ROOT}/scientific_baseline_input_contract.json",
                "src/mineocclude/baselines/raw_pixel.py",
            )
        ],
        "person_e_handoff_sources": [
            git_ref(PERSON_E_HANDOFF_COMMIT, f"{E_HANDOFF_ROOT}/{filename}", role="person_e")
            for filename in (
                "authority_binding.json",
                "person_e_closure_requirements.json",
                "phase6_artifact_handoff.json",
                "sha256_inventory.json",
                "step4_1_execution_contract.json",
                "validation_receipt.json",
            )
        ],
        "person_e_phase6_acceptance_sources": [
            git_ref(PERSON_E_ACCEPTANCE_COMMIT, f"{E_ACCEPTANCE_ROOT}/{filename}", role="person_e")
            for filename in (
                "accepted_provenance_manifest.json",
                "authority_binding.json",
                "phase6_closure_decision.json",
                "validation_receipt.json",
            )
        ],
        "schema_id": "person-a-step4-1-frame-handoff-v0-1-authority-binding",
        "schema_version": "1.0",
    }

    source_inventory = {
        "accepted_pilot_count": 10,
        "accepted_pilot_ids": list(ACCEPTED_PILOTS),
        "admitted_frame_count": 1695,
        "authorized_baseline_families": list(BASELINE_FAMILIES),
        "fold_manifest_sha256": FOLD_SHA256,
        "pilots": pilot_records,
        "schema_id": "person-a-step4-1-frame-handoff-v0-1-source-context-inventory",
        "schema_version": "1.0",
        "source_context_artifact_count": 10,
        "source_frame_count": 1874,
        "source_frames": source_frame_records,
        "target_manifest_sha256": TARGET_SHA256,
        "u4_output_inspected": False,
    }

    gap_manifest = {
        "direct_input_eligibility": {
            "constant_velocity": "source_context_available_but_eight_family_package_blocked",
            "explicit_feature": "source_context_available_but_eight_family_package_blocked",
            "grouped_shuffled": "no_person_a_frame_input_required_but_eight_family_package_blocked",
            "known_q_analytic": "source_context_available_but_eight_family_package_blocked",
            "last_seen": "source_context_available_but_eight_family_package_blocked",
            "raw_pixel": "blocked_missing_exact_current_preprocessed_frames",
            "time_only": "source_context_available_but_eight_family_package_blocked",
            "visible_history_q": "source_context_available_but_eight_family_package_blocked",
        },
        "missing_artifacts": missing_preprocessed,
        "missing_preprocessed_frame_count": 1695,
        "preprocessed_frame_artifact_count": 0,
        "producing_authority_required": {
            "accepted_person_a_authority": STARTING_AUTHORITY,
            "owner": "person_a",
            "required_artifact": "an immutable byte-sized preprocessed-frame manifest with exact retained payload paths, byte sizes, content SHA-256 values, and the 1,695 admitted global frame identities",
            "required_resolution": "publish only retained original accepted-run preprocessed-frame payloads and receipts; if those bytes do not exist, obtain a new explicit cross-role authorization outside this handoff task",
        },
        "schema_id": "person-a-step4-1-frame-handoff-v0-1-preprocessed-frame-gap-manifest",
        "schema_version": "1.0",
        "source_mp4_is_preprocessed_frame_direct_input": False,
        "status": "BLOCKED_REQUIRED_PREPROCESSED_FRAMES_NOT_SERIALIZED",
        "u4_output_inspected": False,
    }

    retention_requirements = [
        {
            "path": str(APPROVED_INPUT_ROOT),
            "requirement": "retain immutable source/input trees through final Step 4.1 closure and durable Registry v2 receipt verification",
        },
        {
            "path": str(APPROVED_OUTPUT_ROOT),
            "requirement": "retain accepted indexes, chunks, inventories, bounded audits, logs, and reports without overwrite, relocation, or deletion",
        },
    ]
    handoff_decision = {
        "all_required_artifacts_present": False,
        "all_required_hashes_verified": False,
        "all_required_sizes_verified": False,
        "baseline_execution_performed": False,
        "fold_manifest_bound": True,
        "immutable_artifact_requirements": [
            "all referenced source-context and Person A index/receipt artifacts are immutable",
            "a future valid preprocessed-frame direct input must be immutable and byte-sized",
            "source MP4, activation chunks, and Person B predictions must not be substituted for preprocessed-frame payloads",
            "no source or Phase 6 artifact may be overwritten, normalized, resized, converted, or reserialized by this handoff",
        ],
        "person_a_reextraction_authorized": False,
        "person_a_reextraction_required": False,
        "person_d_frame_handoff_ready": False,
        "preprocessed_frames_modified": False,
        "probe_execution_performed": False,
        "record_date": "2026-08-01",
        "retention_requirements": retention_requirements,
        "schema_id": "person-a-step4-1-frame-handoff-v0-1-decision",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "source_contexts_modified": False,
        "source_identities_verified": True,
        "status": "FAIL_CLOSED_MISSING_PREPROCESSED_FRAME_DIRECT_INPUT",
        "target_manifest_bound": True,
        "u4_output_inspected": False,
        "unresolved_blockers": [
            {
                "blocker_id": "preprocessed_frame_manifest_and_1695_payloads_absent",
                "detail": "The accepted Phase 6 runner preprocessed all source frames only in process memory. The authorized retained trees contain no serialized CHW float32 frame payloads, no per-frame output content hashes, and no byte-sized preprocessed-frame manifest for the 1,695 fold-admitted raw-pixel rows.",
                "owner": "person_a",
                "required_producing_authority": STARTING_AUTHORITY,
            }
        ],
    }

    validation_receipt = {
        "accepted_pilot_count": 10,
        "all_referenced_external_files_exist": True,
        "all_referenced_external_hashes_verified": True,
        "all_referenced_external_sizes_verified": True,
        "baseline_execution_performed": False,
        "canonical_json_generated": True,
        "duplicate_global_frame_identity_count": 0,
        "duplicate_person_a_index_identity_count": 0,
        "exact_authority_git_objects_resolved": True,
        "external_referenced_file_count": external_file_count,
        "focused_validation_only": True,
        "fold_manifest_bound": True,
        "fold_manifest_sha256_verified": True,
        "media_dimension_and_frame_count_checks_passed": True,
        "missing_preprocessed_frame_count": 1695,
        "person_a_reextraction_authorized": False,
        "person_a_reextraction_required": False,
        "person_b_v0_2_preprocessed_frame_direct_input_satisfied": False,
        "person_d_frame_handoff_ready": False,
        "preprocessed_frame_artifact_count": 0,
        "preprocessed_frames_modified": False,
        "probe_execution_performed": False,
        "schema_and_identity_checks_passed": True,
        "schema_id": "person-a-step4-1-frame-handoff-v0-1-validation-receipt",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "source_context_artifact_count": 10,
        "source_contexts_modified": False,
        "source_frame_identity_count": 1874,
        "source_identities_verified": True,
        "status": "PASS_SOURCE_CONTEXTS_FAIL_CLOSED_PREPROCESSED_FRAMES_ABSENT",
        "target_manifest_bound": True,
        "target_manifest_sha256_verified": True,
        "u4_output_inspected": False,
        "unauthorized_pilot_count": 0,
    }

    documents: dict[str, object] = {
        "authority_binding.json": authority_binding,
        "handoff_decision.json": handoff_decision,
        "preprocessed_frame_gap_manifest.json": gap_manifest,
        "preprocessing_contract.json": preprocessing_contract,
        "source_context_inventory.json": source_inventory,
        "validation_receipt.json": validation_receipt,
    }
    if not no_u4_path(documents):
        fail("a U4-derived path was referenced")
    return documents


def inventory_bytes(documents: Mapping[str, object]) -> bytes:
    files = []
    for filename in PACKAGE_FILENAMES:
        payload = canonical_json_bytes(documents[filename])
        files.append(
            {
                "byte_size": len(payload),
                "path": filename,
                "sha256": sha256_bytes(payload),
            }
        )
    return canonical_json_bytes(
        {
            "algorithm": "sha256",
            "file_count": len(files),
            "files": files,
            "schema_id": "person-a-step4-1-frame-handoff-v0-1-sha256-inventory",
            "schema_version": "1.0",
        }
    )


def write_documents(documents: Mapping[str, object]) -> None:
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for filename in PACKAGE_FILENAMES:
        (PACKAGE_ROOT / filename).write_bytes(canonical_json_bytes(documents[filename]))
    (PACKAGE_ROOT / "sha256_inventory.json").write_bytes(inventory_bytes(documents))


def check_documents(documents: Mapping[str, object]) -> None:
    expected_names = {*PACKAGE_FILENAMES, "sha256_inventory.json"}
    observed_names = {path.name for path in PACKAGE_ROOT.iterdir() if path.is_file()}
    if observed_names != expected_names:
        fail(f"package file set mismatch: {sorted(observed_names)} != {sorted(expected_names)}")
    for filename in PACKAGE_FILENAMES:
        path = PACKAGE_ROOT / filename
        expected = canonical_json_bytes(documents[filename])
        observed = path.read_bytes()
        if observed != expected:
            fail(f"generated package file drifted: {path}")
        if canonical_json_bytes(json.loads(observed)) != observed:
            fail(f"package file is not canonical JSON: {path}")
    expected_inventory = inventory_bytes(documents)
    inventory_path = PACKAGE_ROOT / "sha256_inventory.json"
    if inventory_path.read_bytes() != expected_inventory:
        fail("SHA-256 inventory drifted")
    if canonical_json_bytes(json.loads(expected_inventory)) != expected_inventory:
        fail("SHA-256 inventory is not canonical JSON")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    documents = build_documents()
    if arguments.check:
        check_documents(documents)
    else:
        write_documents(documents)
        check_documents(documents)
    receipt = documents["validation_receipt.json"]
    print(
        json.dumps(
            {
                "external_referenced_file_count": receipt["external_referenced_file_count"],
                "missing_preprocessed_frame_count": receipt["missing_preprocessed_frame_count"],
                "person_d_frame_handoff_ready": receipt["person_d_frame_handoff_ready"],
                "source_context_artifact_count": receipt["source_context_artifact_count"],
                "source_frame_identity_count": receipt["source_frame_identity_count"],
                "status": receipt["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HandoffError as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
