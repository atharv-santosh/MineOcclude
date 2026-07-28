"""Build the bounded, provenance-preserving Person E Phase 2 evidence batch."""

# ruff: noqa: I001

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (
    ImmutableRegistryIndex,
    formatted_json_bytes,
    hash_json_value,
    require_valid_immutable_registry,
    write_json_exclusive,
)
from mineocclude.vision.calibration import (
    FROZEN_DETECTOR_CALIBRATION_SCHEMA_VERSION,
    PNG_DECODER_VERSION,
    decode_png_rgb_bytes,
    validate_detector_calibration_dataset,
)
from mineocclude.vision.config import (
    PERSON_E_CONFIG_SCHEMA_VERSION,
    PHASE2_CALIBRATED_STATUS,
    validate_person_e_config,
)
from mineocclude.vision.homography import (
    GROUND_CONTACT_LOCALIZATION_METHOD_VERSION,
    HOMOGRAPHY_ALGORITHM_VERSION,
    MARKER_LOCALIZATION_METHOD_VERSION,
    fit_marker_homography,
    localize_ground_contact_from_background_pair,
    localize_marker_top_face,
    summarize_localization,
)
from mineocclude.vision.magenta import (
    CALIBRATION_DETECTION_DOCUMENT_SCHEMA_VERSION,
    DETECTOR_ALGORITHM_VERSION,
    HsvRange,
    detect_magenta,
    evaluate_presence,
    validate_detection_document,
)


PERSON_E_BASE_SHA = "24e4556fa03b25fd7256474593b518bdf03cdbe2"
PERSON_E_PHASE2_SCIENTIFIC_BUILDER_REVISION = (
    "8949ea5754634d5a961caf27451f44c661e3ad2b"
)
PERSON_C_REVISION = "00784756f21895d19aff44572496c956cc5d932f"
PERSON_B_REVISION = "03a2c4663ce73873b4fed0369943c1f43edcd742"
PERSON_A_REGISTRY_HANDOFF_REVISION = (
    "f0a4fed546eb1cf19a7094e6b99399a58294726a"
)
PERSON_A_SOURCE_REVISION = "85224f1951c224698a2cf6f8a0a3088de5b67664"
PERSON_C_REGISTRY_HANDOFF_REVISION = (
    "f2fa76739fd9949afe8c8ac3207f8003c018baea"
)
PERSON_C_REGISTRY_SOURCE_REVISION = (
    "487532ba1e7745fe07174090c0851269fb70a6a7"
)
PERSON_A_REGISTRY_HANDOFF_ROOT = (
    "docs/status/person_a_phase2_registry_handoff_v1"
)
PERSON_C_REGISTRY_HANDOFF_ROOT = (
    "data/handoff_e/person_c_phase2_registry_handoff_v1"
)
PERSON_C_INPUT_PATH = "data/handoff_e/detector_calibration_inputs.json"
PERSON_C_PROVENANCE_PATH = "data/handoff_e/provenance_calibration_clean.json"
PERSON_C_PROBE_PATH = "data/handoff_e/independent_probe_points.json"
EVIDENCE_SCHEMA_VERSION = "person-e-phase2-evidence-v0.1"
RESOLUTION_ID = "resolution_640x360_rgb8"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize the real C split, calibration-only detector, and "
            "measured homography evidence without using held-out detector "
            "outcomes for parameter selection."
        )
    )
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--config-template",
        type=Path,
        default=ROOT / "configs" / "vision" / "person_e_phase1.yaml",
    )
    parser.add_argument("--person-c-revision", default=PERSON_C_REVISION)
    parser.add_argument("--person-b-revision", default=PERSON_B_REVISION)
    parser.add_argument(
        "--person-a-registry-handoff-revision",
        default=PERSON_A_REGISTRY_HANDOFF_REVISION,
    )
    parser.add_argument(
        "--person-c-registry-handoff-revision",
        default=PERSON_C_REGISTRY_HANDOFF_REVISION,
    )
    return parser.parse_args()


def _git_blob(revision: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "blob", f"{revision}:{path}"],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Missing committed input {revision}:{path}: {detail}")
    return completed.stdout


def _json_blob(revision: str, path: str) -> tuple[dict[str, Any], bytes]:
    payload = _git_blob(revision, path)
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid committed JSON {revision}:{path}: {error}") from error
    if not isinstance(document, dict):
        raise TypeError(f"Committed JSON {revision}:{path} must be a mapping.")
    return document, payload


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _artifact_hash(document: Mapping[str, Any]) -> tuple[str, int]:
    payload = formatted_json_bytes(document)
    return _sha256(payload), len(payload)


def _runtime_identity() -> tuple[dict[str, Any], str]:
    source_paths = (
        "src/mineocclude/vision/calibration.py",
        "src/mineocclude/vision/magenta.py",
        "src/mineocclude/vision/homography.py",
        "scripts/build_person_e_phase2_evidence.py",
    )
    identity = {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "implementation_base_sha": PERSON_E_BASE_SHA,
        "source_file_sha256": {
            path: _sha256(
                _git_blob(PERSON_E_PHASE2_SCIENTIFIC_BUILDER_REVISION, path)
                if path == "scripts/build_person_e_phase2_evidence.py"
                else (ROOT / path).read_bytes()
            )
            for path in source_paths
        },
        "png_decoder_version": PNG_DECODER_VERSION,
        "detector_algorithm_version": DETECTOR_ALGORITHM_VERSION,
        "marker_localization_method_version": (
            MARKER_LOCALIZATION_METHOD_VERSION
        ),
        "ground_contact_localization_method_version": (
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        ),
        "homography_algorithm_version": HOMOGRAPHY_ALGORITHM_VERSION,
    }
    return identity, hash_json_value(identity)


def _image_region(image_xy: Sequence[float], width: int, height: int) -> str:
    horizontal = (
        "left"
        if float(image_xy[0]) < width / 3.0
        else "right"
        if float(image_xy[0]) >= 2.0 * width / 3.0
        else "center"
    )
    vertical = (
        "upper"
        if float(image_xy[1]) < height / 3.0
        else "lower"
        if float(image_xy[1]) >= 2.0 * height / 3.0
        else "middle"
    )
    return f"{horizontal}_{vertical}"


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


A_SESSION_IDS = (
    "person-a-registry-smoke-20260727T235120Z",
    "person-a-registry-smoke-20260727T235656Z",
    "person-a-registry-smoke-20260728T000019Z",
)
A_STATUS_BY_SESSION = {
    A_SESSION_IDS[0]: "failed",
    A_SESSION_IDS[1]: "failed",
    A_SESSION_IDS[2]: "completed",
}
A_SESSION_DOCUMENT_NAMES = (
    "artifact_verification",
    "attempt_scope",
    "exact_command",
    "run_record",
    "session_receipt",
    "source_index",
)
A_ARTIFACT_TYPE_BY_OWNER_ID = {
    "input:run_phase2_rollout.py": "model_input",
    "input:ffprobe": "model_input",
    "input:700M_16f.yaml": "model_input",
    "input:700M_16f.ckpt": "model_input",
    "input:config.json": "model_input",
    "input:vae.ckpt": "model_input",
    "input:scene.mp4": "input_context",
    "input:scene.jsonl": "model_input",
    "evidence:environment_report": "diagnostic_log",
    "evidence:exact_command": "model_input",
    "evidence:launcher_log": "diagnostic_log",
    "output:step2_6/inference_input/scene.jsonl": "model_input",
    "output:step2_6/inference_input/scene.mp4": "input_context",
    "output:step2_6/raw_stdout_stderr.log": "diagnostic_log",
    "output:step2_6/run_manifest.json": "rollout",
    "output:step2_6/scene.jsonl": "rollout",
    "output:step2_6/scene.mp4": "rollout_clip",
}
C_ARTIFACT_TYPE_BY_OWNER_ID = {
    "frame_map": "raw_trajectory",
    "action_stream": "model_input",
    "media_video": "input_context",
    "qa_report": "diagnostic_log",
    "checksum_manifest": "diagnostic_log",
    "capture_provenance": "diagnostic_log",
    "layout_config": "model_input",
    "raw_server_state": "raw_trajectory",
    "raw_client_actions": "model_input",
    "raw_client_tick": "raw_trajectory",
    "seed_noise_schedule": "model_input",
}


def _require_step2_1(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"Invalid Step 2.1 owner handoff: {message}")


def _strict_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _source_document(
    revision: str,
    path: str,
) -> dict[str, Any]:
    document, payload = _json_blob(revision, path)
    return {
        "git_revision": revision,
        "path": path,
        "sha256": _sha256(payload),
        "document": document,
    }


def load_phase2_registry_handoffs(
    *,
    person_a_handoff_revision: str = PERSON_A_REGISTRY_HANDOFF_REVISION,
    person_c_handoff_revision: str = PERSON_C_REGISTRY_HANDOFF_REVISION,
) -> dict[str, Any]:
    """Load only the two exact committed owner handoffs for Step 2.1."""

    _require_step2_1(
        person_a_handoff_revision == PERSON_A_REGISTRY_HANDOFF_REVISION,
        "Person A handoff revision changed.",
    )
    _require_step2_1(
        person_c_handoff_revision == PERSON_C_REGISTRY_HANDOFF_REVISION,
        "Person C handoff revision changed.",
    )
    a_index = _source_document(
        person_a_handoff_revision,
        f"{PERSON_A_REGISTRY_HANDOFF_ROOT}/handoff_index.json",
    )
    a_external_link = _source_document(
        person_a_handoff_revision,
        f"{PERSON_A_REGISTRY_HANDOFF_ROOT}/external_link_record.json",
    )
    a_sessions = {}
    for session_id in A_SESSION_IDS:
        root = f"{PERSON_A_REGISTRY_HANDOFF_ROOT}/sessions/{session_id}"
        a_sessions[session_id] = {
            name: _source_document(
                person_a_handoff_revision,
                f"{root}/{name}.json",
            )
            for name in A_SESSION_DOCUMENT_NAMES
        }
    c_documents = {
        name: _source_document(
            person_c_handoff_revision,
            f"{PERSON_C_REGISTRY_HANDOFF_ROOT}/{name}.json",
        )
        for name in (
            "artifact_verification",
            "attempt_scope",
            "pilot_registry_handoff",
            "source_index",
        )
    }
    return {
        "person_a_handoff_revision": person_a_handoff_revision,
        "person_c_handoff_revision": person_c_handoff_revision,
        "person_a": {
            "handoff_index": a_index,
            "external_link_record": a_external_link,
            "sessions": a_sessions,
        },
        "person_c": c_documents,
    }


def _document(entry: Mapping[str, Any], name: str) -> dict[str, Any]:
    document = entry.get("document")
    _require_step2_1(
        isinstance(document, dict),
        f"{name} must be a JSON object.",
    )
    _require_step2_1(
        _strict_sha256(entry.get("sha256")),
        f"{name} source-document hash is malformed.",
    )
    _require_step2_1(
        entry.get("sha256") == _sha256(formatted_json_bytes(document)),
        f"{name} source-document bytes or hash changed.",
    )
    _require_step2_1(
        isinstance(entry.get("git_revision"), str)
        and entry["sha256"]
        == _sha256(_git_blob(entry["git_revision"], entry["path"])),
        f"{name} no longer matches its exact committed blob.",
    )
    return document


def _verification_records(
    verification: Mapping[str, Any],
    *,
    owner: str,
    expected_count: int,
) -> dict[str, dict[str, Any]]:
    records = verification.get("artifacts")
    _require_step2_1(
        isinstance(records, list) and len(records) == expected_count,
        f"{owner} artifact-verification count changed.",
    )
    by_id = {}
    for record in records:
        _require_step2_1(
            isinstance(record, dict)
            and isinstance(record.get("artifact_id"), str)
            and record["artifact_id"] not in by_id,
            f"{owner} artifact-verification identity changed.",
        )
        expected = record.get("expected_sha256")
        observed = record.get("observed_sha256")
        _require_step2_1(
            _strict_sha256(observed),
            f"{owner} observed artifact hash is malformed.",
        )
        if expected is not None:
            _require_step2_1(
                _strict_sha256(expected) and expected == observed,
                f"{owner} expected/observed artifact hashes differ.",
            )
            _require_step2_1(
                record.get("verification_result") == "match",
                f"{owner} verification result is not match.",
            )
        else:
            _require_step2_1(
                record.get("verification_result") == "directly_hashed",
                f"{owner} direct-hash result changed.",
            )
        byte_count = record.get("byte_count")
        _require_step2_1(
            (
                isinstance(byte_count, int)
                and not isinstance(byte_count, bool)
                and byte_count >= 0
            )
            or (
                owner == "Person C"
                and record["artifact_id"] == "raw_frames_640x360"
                and byte_count is None
            ),
            f"{owner} artifact byte count is unsupported.",
        )
        by_id[record["artifact_id"]] = record
    return by_id


def _validate_person_a_handoff(
    handoffs: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    person_a = handoffs.get("person_a")
    _require_step2_1(isinstance(person_a, Mapping), "Person A handoff missing.")
    index = _document(person_a["handoff_index"], "Person A handoff_index")
    _require_step2_1(
        index.get("schema_version") == "1.0"
        and index.get("handoff_version")
        == "person-a-phase2-registry-handoff-v1"
        and index.get("person_a_source_revision")
        == PERSON_A_SOURCE_REVISION
        and index.get("verification_authority") == "Kazim Abbas",
        "Person A handoff identity changed.",
    )
    session_rows = index.get("sessions")
    _require_step2_1(
        isinstance(session_rows, list)
        and [row.get("session_id") for row in session_rows]
        == list(A_SESSION_IDS),
        "Person A session inventory changed.",
    )
    sessions = person_a.get("sessions")
    _require_step2_1(
        isinstance(sessions, Mapping)
        and set(sessions) == set(A_SESSION_IDS),
        "Person A session documents changed.",
    )
    validated = {}
    for index_row in session_rows:
        session_id = index_row["session_id"]
        status = A_STATUS_BY_SESSION[session_id]
        entries = sessions[session_id]
        documents = {
            name: _document(
                entries[name],
                f"Person A {session_id}/{name}",
            )
            for name in A_SESSION_DOCUMENT_NAMES
        }
        run = documents["run_record"]
        scope = documents["attempt_scope"]
        command = documents["exact_command"]
        receipt = documents["session_receipt"]
        source_index = documents["source_index"]
        verification = documents["artifact_verification"]
        run_id = f"{session_id}-step2.6"
        attempt_id = f"{session_id}-attempt-001"
        _require_step2_1(
            run.get("schema_version") == "1.0"
            and run.get("run_id") == run_id
            and run.get("session_id") == session_id
            and run.get("attempt_id") == attempt_id
            and run.get("repository_revision") == PERSON_A_SOURCE_REVISION
            and run.get("status") == status
            and run.get("verification_authority") == "Kazim Abbas"
            and run.get("seed") == 20260724,
            f"Person A {session_id} run identity changed.",
        )
        _require_step2_1(
            command.get("argv") == run.get("command")
            and command.get("run_id") == run_id
            and command.get("attempt_id") == attempt_id
            and command.get("session_id") == session_id,
            f"Person A {session_id} exact command changed.",
        )
        attempts = scope.get("attempts")
        _require_step2_1(
            scope.get("inventory_complete") is True
            and scope.get("attempt_count") == 1
            and isinstance(attempts, list)
            and len(attempts) == 1,
            f"Person A {session_id} attempt inventory is incomplete.",
        )
        attempt = attempts[0]
        _require_step2_1(
            attempt.get("attempt_id") == attempt_id
            and attempt.get("run_id") == run_id
            and attempt.get("lifecycle_status") == status
            and attempt.get("started_at") == run.get("started_at")
            and attempt.get("ended_at") == run.get("ended_at")
            and attempt.get("failure_reasons") == run.get("failure_reasons"),
            f"Person A {session_id} attempt/run binding changed.",
        )
        expected_verification_result = (
            "pass" if status == "completed" else "fail"
        )
        _require_step2_1(
            receipt.get("run_id") == run_id
            and receipt.get("attempt_id") == attempt_id
            and receipt.get("lifecycle_status") == status
            and receipt.get("ended_at") == run.get("ended_at")
            and receipt.get("repository_revision")
            == PERSON_A_SOURCE_REVISION
            and receipt.get("verification_authority") == "Kazim Abbas"
            and receipt.get("verification_result")
            == expected_verification_result
            and receipt.get("failure_reasons")
            == run.get("failure_reasons")
            and receipt.get("repository_clean_before") is True
            and receipt.get("repository_clean_after") is True,
            f"Person A {session_id} session receipt changed.",
        )
        _require_step2_1(
            index_row.get("run_id") == run_id
            and index_row.get("lifecycle_status") == status
            and index_row.get("attempt_count") == 1
            and index_row.get("attempt_inventory_complete") is True
            and index_row.get("verification_result")
            == expected_verification_result
            and index_row.get("started_at") == receipt.get("started_at")
            and index_row.get("ended_at") == receipt.get("ended_at"),
            f"Person A {session_id} index/receipt binding changed.",
        )
        _require_step2_1(
            verification.get("session_id") == session_id
            and verification.get("run_id") == run_id
            and verification.get("attempt_id") == attempt_id
            and verification.get("verification_authority") == "Kazim Abbas"
            and verification.get("verification_result")
            == expected_verification_result,
            f"Person A {session_id} verification authority changed.",
        )
        expected_artifact_count = 17 if status == "completed" else (
            11 if session_id == A_SESSION_IDS[0] else 12
        )
        verification_by_id = _verification_records(
            verification,
            owner="Person A",
            expected_count=expected_artifact_count,
        )
        _require_step2_1(
            set(verification_by_id) <= set(A_ARTIFACT_TYPE_BY_OWNER_ID),
            f"Person A {session_id} has an unmapped artifact type.",
        )
        sources = {
            source.get("source_id"): source
            for source in source_index.get("sources", [])
            if isinstance(source, dict)
        }
        _require_step2_1(
            sources.get("person_a_repository", {}).get("revision")
            == PERSON_A_SOURCE_REVISION,
            f"Person A {session_id} source revision changed.",
        )
        if status == "failed":
            _require_step2_1(
                isinstance(run.get("failure_reasons"), list)
                and bool(run["failure_reasons"]),
                f"Person A {session_id} failure reasons are missing.",
            )
        else:
            _require_step2_1(
                run.get("failure_reasons") == [],
                "Completed Person A run contains a failure.",
            )
        validated[session_id] = {
            **documents,
            "verification_by_id": verification_by_id,
        }
    return validated


def _validate_person_c_handoff(
    handoffs: Mapping[str, Any],
) -> dict[str, Any]:
    person_c = handoffs.get("person_c")
    _require_step2_1(isinstance(person_c, Mapping), "Person C handoff missing.")
    documents = {
        name: _document(person_c[name], f"Person C {name}")
        for name in (
            "artifact_verification",
            "attempt_scope",
            "pilot_registry_handoff",
            "source_index",
        )
    }
    pilot = documents["pilot_registry_handoff"]
    scope = documents["attempt_scope"]
    verification = documents["artifact_verification"]
    source_index = documents["source_index"]
    _require_step2_1(
        pilot.get("schema_version") == "1.0"
        and pilot.get("source_revision")
        == PERSON_C_REGISTRY_SOURCE_REVISION
        and pilot.get("episode_id") == 10002
        and pilot.get("trajectory_id") == "layout_03_ep10002"
        and pilot.get("session_id")
        == "person-c-production-run-base10000-2026-07-27"
        and pilot.get("attempt_id") == "layout_03_ep10002-attempt-1"
        and pilot.get("started_at") == "2026-07-27T21:12:05Z"
        and pilot.get("ended_at") == "2026-07-27T21:12:10Z"
        and pilot.get("lifecycle_status") == "accepted"
        and pilot.get("accepted") is True,
        "Person C pilot identity or lifecycle changed.",
    )
    _require_step2_1(
        pilot.get("historical_pilot_note", {}).get(
            "preferred_historical_episode"
        )
        == 9410
        and pilot["historical_pilot_note"].get(
            "replacement_is_first_registry_grade_pilot"
        )
        is True,
        "Person C historical episode ruling changed.",
    )
    attempts = scope.get("attempts")
    _require_step2_1(
        scope.get("inventory_is_authoritative_and_complete_for_scope")
        is True
        and scope.get("session_id") == pilot["session_id"]
        and isinstance(attempts, list)
        and len(attempts) == 1
        and scope.get("pilot_cell_attempt_inventory", {}).get("attempts")
        == 1,
        "Person C attempt inventory is incomplete.",
    )
    attempt = attempts[0]
    _require_step2_1(
        attempt.get("attempt_id") == pilot["attempt_id"]
        and attempt.get("episode_id") == 10002
        and attempt.get("trajectory_id") == pilot["trajectory_id"]
        and attempt.get("started_at") == pilot["started_at"]
        and attempt.get("ended_at") == pilot["ended_at"]
        and attempt.get("status") == "accepted"
        and attempt.get("failure_or_supersession_reason") is None,
        "Person C attempt/pilot binding changed.",
    )
    authority = pilot.get("verification_authority")
    _require_step2_1(
        isinstance(authority, str)
        and authority
        == "Person C (atharvsantosh, owner and verifier of the capture evidence)"
        and verification.get("verification_authority") == authority
        and verification.get("source_revision")
        == PERSON_C_REGISTRY_SOURCE_REVISION,
        "Person C verification authority changed.",
    )
    verification_by_id = _verification_records(
        verification,
        owner="Person C",
        expected_count=12,
    )
    _require_step2_1(
        set(C_ARTIFACT_TYPE_BY_OWNER_ID) <= set(verification_by_id)
        and set(verification_by_id)
        == {*C_ARTIFACT_TYPE_BY_OWNER_ID, "raw_frames_640x360"},
        "Person C artifact inventory changed.",
    )
    for artifact_id, claim in pilot.get("artifacts", {}).items():
        verification_record = verification_by_id[artifact_id]
        claimed_hash = claim.get(
            "frame_manifest_sha256"
            if artifact_id == "raw_frames_640x360"
            else "sha256"
        )
        _require_step2_1(
            claimed_hash == verification_record["observed_sha256"]
            and claim.get("verification_classification")
            == verification_record["verification_classification"],
            f"Person C {artifact_id} pilot/verification binding changed.",
        )
    for record in verification_by_id.values():
        repository_path = record.get("repository_path")
        if repository_path is None:
            continue
        payload = _git_blob(PERSON_C_REGISTRY_SOURCE_REVISION, repository_path)
        _require_step2_1(
            record.get("source_revision")
            == PERSON_C_REGISTRY_SOURCE_REVISION
            and _sha256(payload) == record["observed_sha256"]
            and len(payload) == record["byte_count"],
            f"Person C committed bytes changed for {record['artifact_id']}.",
        )
    for source in source_index.get("sources", []):
        payload = _git_blob(
            PERSON_C_REGISTRY_SOURCE_REVISION,
            source["repository_path"],
        )
        _require_step2_1(
            source.get("git_revision")
            == PERSON_C_REGISTRY_SOURCE_REVISION
            and _sha256(payload) == source.get("sha256"),
            "Person C source-index binding changed.",
        )
    capture, _ = _json_blob(
        PERSON_C_REGISTRY_SOURCE_REVISION,
        "data/autonomous/layout_03_ep10002/capture_provenance.json",
    )
    qa, _ = _json_blob(
        PERSON_C_REGISTRY_SOURCE_REVISION,
        "data/autonomous/layout_03_ep10002/qa_report_10002.json",
    )
    _require_step2_1(
        capture.get("start_utc") == pilot["started_at"]
        and capture.get("end_utc") == pilot["ended_at"]
        and capture.get("git_sha") == pilot["capture_time_code_sha"]
        and capture.get("capture_command") == pilot["capture_command"]
        and capture.get("accepted") is True
        and qa.get("accepted") is True
        and qa.get("status") == "accepted"
        and qa.get("validator_version") == "person-c-qa-v0.1",
        "Person C source lifecycle evidence changed.",
    )
    return {
        **documents,
        "verification_by_id": verification_by_id,
        "capture_provenance": capture,
        "qa_report": qa,
    }


def _registry_artifact(
    *,
    artifact_id: str,
    creator_run_id: str,
    artifact_type: str,
    uri: str,
    sha256: str,
    size_bytes: int,
    status: str,
    status_authority: str,
    status_reason: str | None,
    direct_input_artifact_ids: Sequence[str] = (),
    artifact_schema_version: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_schema_version": artifact_schema_version,
        "artifact_id": artifact_id,
        "direct_input_artifact_ids": sorted(direct_input_artifact_ids),
        "creator_run_id": creator_run_id,
        "artifact_type": artifact_type,
        "uri": uri,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "status": status,
        "status_authority": status_authority,
        "status_reason": status_reason,
        "superseded_by": None,
    }


def _build_a_registry_records(
    sessions: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runs = []
    artifacts = []
    for session_id in A_SESSION_IDS:
        source = sessions[session_id]
        run_record = source["run_record"]
        verification = source["artifact_verification"]
        verification_by_id = source["verification_by_id"]
        run_id = run_record["run_id"]
        status = run_record["status"]
        failure_reason = (
            None
            if status == "completed"
            else json.dumps(
                run_record["failure_reasons"],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        artifact_id_by_owner_id = {
            owner_id: f"person_a:{session_id}:{owner_id}"
            for owner_id in verification_by_id
        }
        upstream_owner_ids = sorted(
            owner_id
            for owner_id in verification_by_id
            if owner_id.startswith("input:")
            or owner_id
            in {"evidence:environment_report", "evidence:exact_command"}
        )
        upstream_ids = [
            artifact_id_by_owner_id[owner_id]
            for owner_id in upstream_owner_ids
        ]
        for owner_id, record in sorted(verification_by_id.items()):
            direct_inputs = (
                upstream_ids
                if owner_id.startswith("output:")
                else []
            )
            artifacts.append(
                _registry_artifact(
                    artifact_id=artifact_id_by_owner_id[owner_id],
                    creator_run_id=run_id,
                    artifact_type=A_ARTIFACT_TYPE_BY_OWNER_ID[owner_id],
                    uri=(
                        "external+sha256://person-a"
                        f"{record['path']}"
                    ),
                    sha256=record["observed_sha256"],
                    size_bytes=record["byte_count"],
                    status=(
                        "accepted" if status == "completed" else "excluded"
                    ),
                    status_authority=verification[
                        "verification_authority"
                    ],
                    status_reason=failure_reason,
                    direct_input_artifact_ids=direct_inputs,
                    artifact_schema_version=verification["receipt_version"],
                )
            )
        runs.append(
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "code_sha": PERSON_A_SOURCE_REVISION,
                "git_dirty": False,
                "config_snapshot_hash": verification_by_id[
                    "input:700M_16f.yaml"
                ]["observed_sha256"],
                "checkpoint_hash": verification_by_id[
                    "input:700M_16f.ckpt"
                ]["observed_sha256"],
                "data_identity_hash": verification_by_id[
                    "input:scene.jsonl"
                ]["observed_sha256"],
                "preprocess_hash": verification_by_id[
                    "input:run_phase2_rollout.py"
                ]["observed_sha256"],
                "environment_hash": run_record[
                    "environment_report_sha256"
                ],
                "seeds": {"rollout_seed": run_record["seed"]},
                "command": copy.deepcopy(run_record["command"]),
                "owner": "person_a",
                "started_at": run_record["started_at"],
                "ended_at": run_record["ended_at"],
                "status": status,
                "parent_run_id": None,
                "input_artifact_ids": upstream_ids,
                "output_artifact_ids": sorted(
                    artifact_id_by_owner_id.values()
                ),
                "failure_reason": failure_reason,
                "supersedes_run_id": None,
                "supersession_reason": None,
            }
        )
    return runs, artifacts


def _build_c_registry_records(
    source: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    pilot = source["pilot_registry_handoff"]
    verification = source["artifact_verification"]
    verification_by_id = source["verification_by_id"]
    run_id = pilot["attempt_id"]
    registered_owner_ids = sorted(C_ARTIFACT_TYPE_BY_OWNER_ID)
    artifact_id_by_owner_id = {
        owner_id: f"person_c:{pilot['trajectory_id']}:{owner_id}"
        for owner_id in registered_owner_ids
    }
    direct_owner_ids = {
        "layout_config": (),
        "seed_noise_schedule": (),
        "raw_server_state": ("layout_config", "seed_noise_schedule"),
        "raw_client_actions": ("layout_config", "seed_noise_schedule"),
        "raw_client_tick": ("layout_config", "seed_noise_schedule"),
        "capture_provenance": (
            "layout_config",
            "seed_noise_schedule",
        ),
        "frame_map": (
            "raw_server_state",
            "raw_client_actions",
            "raw_client_tick",
        ),
        "action_stream": ("raw_client_actions",),
        "media_video": (),
        "qa_report": (
            "frame_map",
            "action_stream",
            "media_video",
            "capture_provenance",
        ),
        "checksum_manifest": ("qa_report",),
    }
    artifacts = []
    for owner_id in registered_owner_ids:
        record = verification_by_id[owner_id]
        repository_path = record.get("repository_path")
        uri = (
            "git+sha256://"
            f"{PERSON_C_REGISTRY_SOURCE_REVISION}/{repository_path}"
            if repository_path is not None
            else (
                "external+sha256://person-c/"
                f"{record['external_object']}"
            )
        )
        artifacts.append(
            _registry_artifact(
                artifact_id=artifact_id_by_owner_id[owner_id],
                creator_run_id=run_id,
                artifact_type=C_ARTIFACT_TYPE_BY_OWNER_ID[owner_id],
                uri=uri,
                sha256=record["observed_sha256"],
                size_bytes=record["byte_count"],
                status="accepted",
                status_authority=verification["verification_authority"],
                status_reason=None,
                direct_input_artifact_ids=[
                    artifact_id_by_owner_id[input_id]
                    for input_id in direct_owner_ids[owner_id]
                ],
                artifact_schema_version=pilot["receipt_version"],
            )
        )
    run_input_ids = sorted(
        {
            artifact_id_by_owner_id[input_id]
            for owner_id in registered_owner_ids
            for input_id in direct_owner_ids[owner_id]
        }
    )
    capture = source["capture_provenance"]
    run = {
        "schema_version": "1.0",
        "run_id": run_id,
        "code_sha": pilot["capture_time_code_sha"],
        "git_dirty": pilot["dirty_state"]["git_dirty_code_scoped"],
        "config_snapshot_hash": verification_by_id["layout_config"][
            "observed_sha256"
        ],
        "checkpoint_hash": pilot["deterministic_capture_inputs"][
            "capturing_jar_sha256"
        ],
        "data_identity_hash": verification_by_id["frame_map"][
            "observed_sha256"
        ],
        "preprocess_hash": verification_by_id["action_stream"][
            "observed_sha256"
        ],
        "environment_hash": verification_by_id["capture_provenance"][
            "observed_sha256"
        ],
        "seeds": {"capture_seed": capture["seed"]},
        "command": copy.deepcopy(pilot["capture_command"]),
        "owner": "person_c",
        "started_at": pilot["started_at"],
        "ended_at": pilot["ended_at"],
        "status": "completed",
        "parent_run_id": None,
        "input_artifact_ids": run_input_ids,
        "output_artifact_ids": sorted(artifact_id_by_owner_id.values()),
        "failure_reason": None,
        "supersedes_run_id": None,
        "supersession_reason": None,
    }
    return [run], artifacts, ["raw_frames_640x360"]


def _source_document_hashes(handoffs: Mapping[str, Any]) -> dict[str, str]:
    records = {}
    person_a = handoffs["person_a"]
    for name in ("handoff_index", "external_link_record"):
        entry = person_a[name]
        records[entry["path"]] = entry["sha256"]
    for session in person_a["sessions"].values():
        for entry in session.values():
            records[entry["path"]] = entry["sha256"]
    for entry in handoffs["person_c"].values():
        records[entry["path"]] = entry["sha256"]
    return dict(sorted(records.items()))


def build_phase2_step2_1_documents(
    handoffs: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Map validated owner receipts into the one shared immutable registry."""

    _require_step2_1(
        handoffs.get("person_a_handoff_revision")
        == PERSON_A_REGISTRY_HANDOFF_REVISION
        and handoffs.get("person_c_handoff_revision")
        == PERSON_C_REGISTRY_HANDOFF_REVISION,
        "Owner handoff commit identity changed.",
    )
    a_sessions = _validate_person_a_handoff(handoffs)
    c_source = _validate_person_c_handoff(handoffs)
    a_runs, a_artifacts = _build_a_registry_records(a_sessions)
    c_runs, c_artifacts, unregistered_c = _build_c_registry_records(c_source)
    registry = {
        "schema_version": "1.0",
        "immutable_registry_schema_version": (
            "mineocclude-immutable-registry-v1.0"
        ),
        "registry_id": "person-e-phase2-step2.1-real-registry-v1",
        "synthetic": False,
        "scientific_use": "permitted",
        "runs": sorted(
            [*a_runs, *c_runs],
            key=lambda record: record["run_id"],
        ),
        "artifacts": sorted(
            [*a_artifacts, *c_artifacts],
            key=lambda record: record["artifact_id"],
        ),
    }
    validation = require_valid_immutable_registry(registry)
    index = ImmutableRegistryIndex(registry)
    all_runs = index.query_runs()
    failed_runs = index.query_runs(statuses=["failed"])
    completed_runs = index.query_runs(statuses=["completed"])
    accepted_artifacts = index.accepted_artifacts()
    failed_artifacts = index.query_artifacts(
        creator_run_statuses=["failed"]
    )
    completed_a_session = A_SESSION_IDS[-1]
    a_config_id = (
        f"person_a:{completed_a_session}:input:700M_16f.yaml"
    )
    a_rollout_id = (
        f"person_a:{completed_a_session}:output:step2_6/scene.mp4"
    )
    backward_lineage = index.backward_lineage(a_rollout_id)
    backward_lineage["creator_run"] = next(
        copy.deepcopy(run)
        for run in completed_runs
        if run["run_id"]
        == f"{completed_a_session}-step2.6"
    )
    registry_hash, _ = _artifact_hash(registry)
    query = {
        "schema_version": "1.0",
        "query_example_schema_version": (
            "person-e-phase2-step2.1-registry-query-v1"
        ),
        "registry_id": registry["registry_id"],
        "registry_sha256": registry_hash,
        "run_queries": {
            "all_status": all_runs,
            "failed": failed_runs,
            "completed": completed_runs,
        },
        "artifact_queries": {
            "accepted_only": accepted_artifacts,
            "failed_creator_all_status": failed_artifacts,
            "superseded_all_status": index.query_artifacts(
                statuses=["superseded"]
            ),
        },
        "lineage_queries": {
            "forward_run_input_to_outputs": index.forward_lineage(
                a_config_id
            ),
            "backward_output_to_inputs_and_run": backward_lineage,
        },
        "deterministic_ordering": {
            "run_order_key": "run_id",
            "artifact_order_key": "artifact_id",
            "all_sequences_canonical": True,
        },
    }
    query_hash, _ = _artifact_hash(query)
    run_counts = Counter(run["status"] for run in registry["runs"])
    verification_classes = Counter(
        record["verification_classification"]
        for record in (
            *a_sessions[A_SESSION_IDS[0]]["artifact_verification"][
                "artifacts"
            ],
            *a_sessions[A_SESSION_IDS[1]]["artifact_verification"][
                "artifacts"
            ],
            *a_sessions[A_SESSION_IDS[2]]["artifact_verification"][
                "artifacts"
            ],
            *c_source["artifact_verification"]["artifacts"],
        )
    )
    receipt = {
        "schema_version": "1.0",
        "receipt_schema_version": (
            "person-e-phase2-step2.1-registry-receipt-v1"
        ),
        "step": "2.1",
        "status": "PASS",
        "registry_id": registry["registry_id"],
        "registry_sha256": registry_hash,
        "query_example_sha256": query_hash,
        "owner_handoff_revisions": {
            "person_a": PERSON_A_REGISTRY_HANDOFF_REVISION,
            "person_c": PERSON_C_REGISTRY_HANDOFF_REVISION,
        },
        "owner_source_revisions": {
            "person_a": PERSON_A_SOURCE_REVISION,
            "person_c": PERSON_C_REGISTRY_SOURCE_REVISION,
        },
        "owner_handoff_roots": {
            "person_a": PERSON_A_REGISTRY_HANDOFF_ROOT,
            "person_c": PERSON_C_REGISTRY_HANDOFF_ROOT,
        },
        "owner_verification_authorities": {
            "person_a": "Kazim Abbas",
            "person_c": c_source["artifact_verification"][
                "verification_authority"
            ],
        },
        "attempt_scope_confirmation": {
            "person_a": [
                {
                    "session_id": session_id,
                    "attempt_count": 1,
                    "inventory_complete": True,
                }
                for session_id in A_SESSION_IDS
            ],
            "person_c": {
                "session_id": c_source["attempt_scope"]["session_id"],
                "attempt_count": 1,
                "inventory_complete": True,
            },
        },
        "registry_validation": {
            "validator": "require_valid_immutable_registry",
            "accepted": validation.accepted,
            "synthetic": registry["synthetic"],
            "scientific_use": registry["scientific_use"],
        },
        "run_counts_by_lifecycle_status": {
            status: run_counts.get(status, 0)
            for status in ("in_progress", "completed", "failed")
        },
        "registered_artifact_count": len(registry["artifacts"]),
        "accepted_artifact_count": len(accepted_artifacts),
        "excluded_failed_run_artifact_count": len(failed_artifacts),
        "owner_verification_record_count": {
            "person_a": sum(
                len(a_sessions[session_id]["artifact_verification"][
                    "artifacts"
                ])
                for session_id in A_SESSION_IDS
            ),
            "person_c": len(
                c_source["artifact_verification"]["artifacts"]
            ),
        },
        "verification_classification_counts": dict(
            sorted(verification_classes.items())
        ),
        "verified_but_unregistered_artifacts": [
            {
                "owner": "person_c",
                "artifact_id": artifact_id,
                "reason": (
                    "owner verification supplies a frame-manifest hash and "
                    "file count but no aggregate byte_count required by the "
                    "shared immutable artifact schema"
                ),
            }
            for artifact_id in unregistered_c
        ],
        "historical_episode_9410_registered": False,
        "source_document_sha256": _source_document_hashes(handoffs),
        "non_inference": {
            "timestamps_inferred": False,
            "failures_inferred": False,
            "hashes_inferred": False,
            "authority_inferred": False,
        },
        "non_inference_statement": (
            "No timestamps, failures, hashes, or verification authority "
            "were inferred by Person E."
        ),
    }
    _require_step2_1(
        len(all_runs) == 4
        and len(failed_runs) == 2
        and len(completed_runs) == 2
        and all(
            artifact["creator_run_id"]
            not in {run["run_id"] for run in failed_runs}
            for artifact in accepted_artifacts
        )
        and all(
            sequence == sorted(
                sequence,
                key=lambda record: record[
                    "run_id"
                    if "run_id" in record
                    else "artifact_id"
                ],
            )
            for sequence in (
                all_runs,
                failed_runs,
                completed_runs,
                accepted_artifacts,
                failed_artifacts,
            )
        )
        and "9410"
        not in json.dumps(registry, separators=(",", ":"), sort_keys=True),
        "Registry query or historical-pilot exclusion changed.",
    )
    return {
        "registry_snapshot.json": registry,
        "registry_query_example.json": query,
        "step2_1_registry_receipt.json": receipt,
    }


def _candidate_settings() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": "candidate_00_primary",
            "hsv_ranges": [[280.0, 320.0, 0.5, 1.0, 0.35, 1.0]],
            "min_area_pixels": 20,
            "max_area_pixels": 5000,
            "open_iterations": 0,
            "close_iterations": 0,
            "morphology_radius_pixels": 1,
            "connectivity": 8,
        },
        {
            "candidate_id": "candidate_01_broad",
            "hsv_ranges": [[275.0, 325.0, 0.4, 1.0, 0.25, 1.0]],
            "min_area_pixels": 20,
            "max_area_pixels": 5000,
            "open_iterations": 0,
            "close_iterations": 0,
            "morphology_radius_pixels": 1,
            "connectivity": 8,
        },
        {
            "candidate_id": "candidate_02_narrow",
            "hsv_ranges": [[285.0, 315.0, 0.55, 1.0, 0.4, 1.0]],
            "min_area_pixels": 20,
            "max_area_pixels": 5000,
            "open_iterations": 0,
            "close_iterations": 0,
            "morphology_radius_pixels": 1,
            "connectivity": 8,
        },
    ]


def _detect(
    rgb: Sequence[Sequence[Sequence[float]]],
    settings: Mapping[str, Any],
):
    return detect_magenta(
        rgb,
        hsv_ranges=[HsvRange(*values) for values in settings["hsv_ranges"]],
        min_area_pixels=settings["min_area_pixels"],
        max_area_pixels=settings["max_area_pixels"],
        open_iterations=settings["open_iterations"],
        close_iterations=settings["close_iterations"],
        morphology_radius_pixels=settings["morphology_radius_pixels"],
        connectivity=settings["connectivity"],
    )


def _metrics(results: Sequence[tuple[bool, Any]]) -> dict[str, Any]:
    metrics = evaluate_presence(results)
    return {
        "true_positive": metrics.true_positive,
        "false_positive": metrics.false_positive,
        "true_negative": metrics.true_negative,
        "false_negative": metrics.false_negative,
        "precision": metrics.precision,
        "recall": metrics.recall,
    }


def _build_documents(
    *,
    config_template: Path,
    person_c_revision: str,
    person_b_revision: str,
    person_a_registry_handoff_revision: str,
    person_c_registry_handoff_revision: str,
) -> dict[str, dict[str, Any]]:
    step2_1_documents = build_phase2_step2_1_documents(
        load_phase2_registry_handoffs(
            person_a_handoff_revision=(
                person_a_registry_handoff_revision
            ),
            person_c_handoff_revision=(
                person_c_registry_handoff_revision
            ),
        )
    )
    source, source_payload = _json_blob(person_c_revision, PERSON_C_INPUT_PATH)
    provenance, provenance_payload = _json_blob(
        person_c_revision, PERSON_C_PROVENANCE_PATH
    )
    probes, probe_payload = _json_blob(person_c_revision, PERSON_C_PROBE_PATH)
    if len(source.get("frames", [])) != 72 or len(source.get("layouts", [])) != 6:
        raise ValueError("Person C calibration input count changed.")
    if len(provenance.get("trajectories", [])) != 12:
        raise ValueError("Person C clean-capture provenance count changed.")
    if len(probes.get("points", [])) != 36:
        raise ValueError("Person C independent-probe count changed.")

    runtime_identity, runtime_hash = _runtime_identity()
    rgb_by_frame: dict[str, list[list[list[int]]]] = {}
    input_frame_by_id = {frame["frame_id"]: frame for frame in source["frames"]}
    for frame in source["frames"]:
        payload = _git_blob(person_c_revision, frame["png_path"])
        if _sha256(payload) != frame["source_frame_hash"]:
            raise ValueError(f"{frame['frame_id']} source_frame_hash changed.")
        rgb = decode_png_rgb_bytes(payload)
        if len(rgb) != 360 or len(rgb[0]) != 640:
            raise ValueError(f"{frame['frame_id']} resolution changed.")
        rgb_by_frame[frame["frame_id"]] = rgb

    pair_id_by_visible_id: dict[str, str] = {}
    ground_contact_by_visible_id: dict[str, dict[str, Any]] = {}
    for frame in source["frames"]:
        if frame["truth_class"] != "visible":
            continue
        background_id = (
            f"{frame['layout_id']}_negative_{frame['source_frame_idx']:03d}"
        )
        background = input_frame_by_id.get(background_id)
        if (
            background is None
            or background["split"] != frame["split"]
            or background["truth_class"] != "negative"
        ):
            raise ValueError(f"{frame['frame_id']} lacks a same-split background.")
        pair_id_by_visible_id[frame["frame_id"]] = background_id
        ground_contact_by_visible_id[frame["frame_id"]] = (
            localize_ground_contact_from_background_pair(
                rgb_by_frame[frame["frame_id"]],
                rgb_by_frame[background_id],
            )
        )

    marker_colors = {
        "north_west": "blue",
        "north_east": "yellow",
        "south_east": "white",
        "south_west": "lime",
    }
    frozen_layouts = []
    marker_details_by_layout: dict[str, list[dict[str, Any]]] = {}
    for layout in sorted(source["layouts"], key=lambda item: item["layout_id"]):
        layout_id = layout["layout_id"]
        marker_source_id = f"{layout_id}_negative_000"
        marker_source = input_frame_by_id[marker_source_id]
        localized_markers = []
        detail_rows = []
        for marker in layout["markers"]:
            role = marker["marker_id"]
            detail = localize_marker_top_face(
                rgb_by_frame[marker_source_id],
                marker_color=marker_colors[role],
            )
            detail_rows.append(
                {
                    "marker_id": role,
                    "marker_role": role,
                    "marker_color": marker_colors[role],
                    "source_frame_id": marker_source_id,
                    "source_frame_hash": marker_source["source_frame_hash"],
                    **detail,
                    "world_xz_blocks": marker["world_xz_blocks"],
                    "coordinate_source_hash": marker[
                        "coordinate_source_hash"
                    ],
                }
            )
            localized_markers.append(
                {
                    "marker_id": role,
                    "marker_role": role,
                    "marker_color": marker_colors[role],
                    "image_xy": detail["image_xy"],
                    "world_xz_blocks": marker["world_xz_blocks"],
                    "coordinate_source_hash": marker[
                        "coordinate_source_hash"
                    ],
                    "source_frame_id": marker_source_id,
                    "source_frame_hash": marker_source["source_frame_hash"],
                    "localization_method_version": detail[
                        "localization_method_version"
                    ],
                    "segmentation_pixel_count": detail[
                        "segmentation_pixel_count"
                    ],
                    "bounding_box_xyxy": detail["bounding_box_xyxy"],
                }
            )
        marker_details_by_layout[layout_id] = detail_rows
        frozen_layouts.append(
            {
                "layout_id": layout_id,
                "canonical_camera_pose_id": layout[
                    "canonical_camera_pose_id"
                ],
                "marker_set_id": layout["marker_set_id"],
                "marker_set_source_hash": layout["marker_set_source_hash"],
                "image_width_px": 640,
                "image_height_px": 360,
                "resolution_id": RESOLUTION_ID,
                "pixel_format": "rgb8",
                "markers": localized_markers,
            }
        )

    frozen_frames = []
    for frame in sorted(source["frames"], key=lambda item: item["frame_id"]):
        visible = frame["truth_class"] == "visible"
        region = (
            _image_region(
                ground_contact_by_visible_id[frame["frame_id"]]["image_xy"],
                640,
                360,
            )
            if visible
            else "full_frame_negative"
        )
        frozen_frames.append(
            {
                "frame_id": frame["frame_id"],
                "layout_id": frame["layout_id"],
                "canonical_camera_pose_id": frame[
                    "canonical_camera_pose_id"
                ],
                "split": frame["split"],
                "truth_class": frame["truth_class"],
                "truth_present": frame["truth_present"],
                "source_artifact_id": frame["source_artifact_id"],
                "source_frame_idx": frame["source_frame_idx"],
                "source_frame_hash": frame["source_frame_hash"],
                "source_git_revision": person_c_revision,
                "source_git_path": frame["png_path"],
                "decoded_rgb_hash": hash_json_value(
                    rgb_by_frame[frame["frame_id"]]
                ),
                "image_width_px": 640,
                "image_height_px": 360,
                "pixel_format": "rgb8",
                "resolution_id": RESOLUTION_ID,
                "image_region": region,
                "threshold_selection_eligible": (
                    frame["split"] == "calibration"
                ),
                "paired_background_frame_id": (
                    pair_id_by_visible_id[frame["frame_id"]]
                    if visible
                    else None
                ),
            }
        )
    split = {
        "schema_version": "1.0",
        "detector_calibration_schema_version": (
            FROZEN_DETECTOR_CALIBRATION_SCHEMA_VERSION
        ),
        "dataset_id": "person_e_phase2_c_frames_v0_1",
        "split_version": None,
        "freeze": {
            "status": "frozen_before_threshold_selection",
            "split_frozen_before_threshold_selection": True,
            "threshold_selection_eligible_split": "calibration",
            "heldout_parameter_selection_forbidden": True,
        },
        "source_document": {
            "git_revision": person_c_revision,
            "path": PERSON_C_INPUT_PATH,
            "sha256": _sha256(source_payload),
        },
        "capture_provenance": {
            "git_revision": person_c_revision,
            "path": PERSON_C_PROVENANCE_PATH,
            "sha256": _sha256(provenance_payload),
            "trajectory_count": len(provenance["trajectories"]),
        },
        "partition_authority": {
            "person_b_revision": person_b_revision,
            "u4_partition_schema_version": "person-b-u4-partition-v0.1",
            "real_final_u4_manifest_status": "not_available",
            "available_u4_artifact_ids": [],
            "included_u4_artifact_ids": [],
        },
        "layouts": frozen_layouts,
        "frames": frozen_frames,
    }
    split["split_version"] = "sha256:" + hash_json_value(
        {key: value for key, value in split.items() if key != "split_version"}
    )
    validate_detector_calibration_dataset(split)
    split_hash, _ = _artifact_hash(split)

    coverage_counts = Counter(
        (
            frame["layout_id"],
            frame["split"],
            frame["truth_class"],
            frame["image_region"],
        )
        for frame in frozen_frames
    )
    calibration_ids = {
        (frame["source_artifact_id"], frame["source_frame_idx"])
        for frame in frozen_frames
        if frame["split"] == "calibration"
    }
    heldout_ids = {
        (frame["source_artifact_id"], frame["source_frame_idx"])
        for frame in frozen_frames
        if frame["split"] == "heldout"
    }
    coverage = {
        "schema_version": "1.0",
        "coverage_schema_version": "person-e-phase2-split-coverage-v0.1",
        "split_version": split["split_version"],
        "frame_count": len(frozen_frames),
        "layout_count": len(frozen_layouts),
        "calibration_frame_count": sum(
            frame["split"] == "calibration" for frame in frozen_frames
        ),
        "heldout_frame_count": sum(
            frame["split"] == "heldout" for frame in frozen_frames
        ),
        "visible_frame_count": sum(
            frame["truth_class"] == "visible" for frame in frozen_frames
        ),
        "negative_frame_count": sum(
            frame["truth_class"] == "negative" for frame in frozen_frames
        ),
        "source_identity_intersection": [
            list(item) for item in sorted(calibration_ids & heldout_ids)
        ],
        "source_identities_disjoint": not (calibration_ids & heldout_ids),
        "anonymous_frame_copies_used": False,
        "heldout_used_for_parameter_selection": False,
        "real_final_u4_manifest_available": False,
        "available_u4_artifacts_included": [],
        "counts": [
            {
                "layout_id": key[0],
                "split": key[1],
                "truth_class": key[2],
                "image_region": key[3],
                "count": count,
            }
            for key, count in sorted(coverage_counts.items())
        ],
    }

    calibration_frames = [
        frame for frame in frozen_frames if frame["split"] == "calibration"
    ]
    candidate_audit = []
    candidate_results: dict[str, list[tuple[bool, Any]]] = {}
    for candidate in _candidate_settings():
        results = [
            (
                frame["truth_present"],
                _detect(rgb_by_frame[frame["frame_id"]], candidate),
            )
            for frame in calibration_frames
        ]
        metrics = _metrics(results)
        candidate_results[candidate["candidate_id"]] = results
        candidate_audit.append(
            {
                **copy.deepcopy(candidate),
                "metrics": metrics,
            }
        )
    selected_audit = min(
        candidate_audit,
        key=lambda item: (
            -item["metrics"]["true_positive"],
            item["metrics"]["false_positive"],
            item["metrics"]["false_negative"],
            item["candidate_id"],
        ),
    )
    selected_settings = {
        key: copy.deepcopy(value)
        for key, value in selected_audit.items()
        if key not in {"candidate_id", "metrics"}
    }
    settings_hash = hash_json_value(selected_settings)
    threshold_version = (
        f"person-e-magenta-threshold-sha256-{settings_hash}"
    )
    detector_identity_hash = hash_json_value(
        {
            "detector_algorithm_version": DETECTOR_ALGORITHM_VERSION,
            "threshold_version": threshold_version,
            "settings_hash": settings_hash,
            "split_version": split["split_version"],
            "software_runtime_hash": runtime_hash,
        }
    )
    detector_version = (
        f"{DETECTOR_ALGORITHM_VERSION}:sha256:{detector_identity_hash}"
    )
    selected_results = candidate_results[selected_audit["candidate_id"]]
    contexts = []
    records = []
    by_layout_results: dict[str, list[tuple[bool, Any]]] = defaultdict(list)
    for frame, (_, result) in zip(
        calibration_frames, selected_results, strict=True
    ):
        context = {
            "source_frame_id": frame["frame_id"],
            "source_artifact_id": frame["source_artifact_id"],
            "source_frame_idx": frame["source_frame_idx"],
            "source_frame_hash": frame["source_frame_hash"],
            "decoded_rgb_hash": frame["decoded_rgb_hash"],
            "source_git_revision": frame["source_git_revision"],
            "source_git_path": frame["source_git_path"],
            "split": frame["split"],
            "layout_id": frame["layout_id"],
            "canonical_camera_pose_id": frame[
                "canonical_camera_pose_id"
            ],
            "resolution_id": frame["resolution_id"],
            "image_width_px": frame["image_width_px"],
            "image_height_px": frame["image_height_px"],
            "pixel_format": frame["pixel_format"],
            "image_coordinate_system": "pixel_center_xy_zero_based",
            "truth_class": frame["truth_class"],
            "truth_present": frame["truth_present"],
            "frame_available": True,
        }
        contexts.append(context)
        records.append(
            {
                **{
                    key: value
                    for key, value in context.items()
                    if key != "frame_available"
                },
                "detection_id": (
                    f"{detector_identity_hash}:{frame['frame_id']}"
                ),
                "detector_version": detector_version,
                "threshold_version": threshold_version,
                "status": result.status,
                "presence": result.detected,
                "centroid_xy": (
                    None
                    if result.centroid_xy is None
                    else list(result.centroid_xy)
                ),
                "area_pixels": result.area_pixels,
                "bounding_box_xyxy": (
                    None
                    if result.bounding_box_xyxy is None
                    else list(result.bounding_box_xyxy)
                ),
                "quality_status": "accepted",
                "rejection_reason": result.rejection_reason,
                "threshold_match_pixels": result.threshold_match_pixels,
                "candidate_blob_count": result.candidate_blob_count,
            }
        )
        by_layout_results[frame["layout_id"]].append(
            (frame["truth_present"], result)
        )
    detections = {
        "schema_version": "1.0",
        "detection_schema_version": (
            CALIBRATION_DETECTION_DOCUMENT_SCHEMA_VERSION
        ),
        "document_id": f"person_e_phase2_calibration_{detector_identity_hash}",
        "synthetic": False,
        "scientific_use": "permitted",
        "detector_version": detector_version,
        "threshold_version": threshold_version,
        "split_version": split["split_version"],
        "settings_hash": settings_hash,
        "source_contexts": contexts,
        "records": records,
    }
    validate_detection_document(detections)
    detections_hash, _ = _artifact_hash(detections)

    config = json.loads(config_template.read_text(encoding="utf-8"))
    config["config_schema_version"] = PERSON_E_CONFIG_SCHEMA_VERSION
    config["config_instance_version"] = (
        f"person-e-phase2-calibration-sha256-{detector_identity_hash}"
    )
    config["status"] = PHASE2_CALIBRATED_STATUS
    detector_config = config["detector"]
    detector_config.update(
        {
            "threshold_status": "frozen_calibration_only",
            "threshold_version": threshold_version,
            "calibration_dataset_hash": split_hash,
            "heldout_report_hash": None,
            "detector_algorithm_version": DETECTOR_ALGORITHM_VERSION,
            "split_version": split["split_version"],
            "settings_hash": settings_hash,
            "software_runtime_hash": runtime_hash,
            "hsv_ranges": [
                {
                    "h_min": values[0],
                    "h_max": values[1],
                    "s_min": values[2],
                    "s_max": values[3],
                    "v_min": values[4],
                    "v_max": values[5],
                }
                for values in selected_settings["hsv_ranges"]
            ],
        }
    )
    detector_config["morphology"] = {
        "open_iterations": selected_settings["open_iterations"],
        "close_iterations": selected_settings["close_iterations"],
        "radius_pixels": selected_settings["morphology_radius_pixels"],
    }
    detector_config["blob"] = {
        "connectivity": selected_settings["connectivity"],
        "min_area_pixels": selected_settings["min_area_pixels"],
        "max_area_pixels": selected_settings["max_area_pixels"],
        "selection": "largest_valid_area_then_top_left",
    }
    validate_person_e_config(config)
    config_hash, _ = _artifact_hash(config)

    calibration_report = {
        "schema_version": "1.0",
        "detector_report_schema_version": "person-e-detector-report-v0.3",
        "report_id": f"person_e_phase2_calibration_{detector_identity_hash}",
        "evaluation_split": "calibration",
        "split_version": split["split_version"],
        "split_manifest_hash": split_hash,
        "detector_version": detector_version,
        "threshold_version": threshold_version,
        "settings_hash": settings_hash,
        "selected_candidate_id": selected_audit["candidate_id"],
        "selected_settings": selected_settings,
        "selection_objective": (
            "maximize_true_positive_then_minimize_false_positive_"
            "then_false_negative_then_candidate_id"
        ),
        "candidate_audit": candidate_audit,
        "metrics": selected_audit["metrics"],
        "per_layout_metrics": [
            {
                "layout_id": layout_id,
                **_metrics(results),
            }
            for layout_id, results in sorted(by_layout_results.items())
        ],
        "calibration_detection_document_hash": detections_hash,
        "heldout_frame_count": sum(
            frame["split"] == "heldout" for frame in frozen_frames
        ),
        "heldout_opened_for_parameter_selection": False,
        "heldout_performance_reported": False,
        "software_runtime": runtime_identity,
        "software_runtime_hash": runtime_hash,
    }
    calibration_report_hash, _ = _artifact_hash(calibration_report)
    detector_version_record = {
        "schema_version": "1.0",
        "detector_version_schema_version": (
            "person-e-detector-version-record-v0.1"
        ),
        "detector_version": detector_version,
        "detector_algorithm_version": DETECTOR_ALGORITHM_VERSION,
        "threshold_version": threshold_version,
        "settings_hash": settings_hash,
        "split_version": split["split_version"],
        "split_manifest_hash": split_hash,
        "config_hash": config_hash,
        "calibration_report_hash": calibration_report_hash,
        "detection_document_hash": detections_hash,
        "software_runtime_hash": runtime_hash,
        "heldout_used_for_parameter_selection": False,
        "phase3_heldout_performance_claimed": False,
    }

    correspondence_layouts = []
    homography_records = []
    localization_layouts = []
    all_localization_records = []
    for layout in frozen_layouts:
        layout_id = layout["layout_id"]
        marker_details = marker_details_by_layout[layout_id]
        correspondence = {
            "layout_id": layout_id,
            "canonical_camera_pose_id": layout[
                "canonical_camera_pose_id"
            ],
            "resolution_id": RESOLUTION_ID,
            "image_width_px": 640,
            "image_height_px": 360,
            "image_coordinate_system": "pixel_center_xy_zero_based",
            "world_coordinate_system": "ground_plane_world_xz_blocks",
            "marker_order": [
                "north_west",
                "north_east",
                "south_east",
                "south_west",
            ],
            "marker_localization_method_version": (
                MARKER_LOCALIZATION_METHOD_VERSION
            ),
            "markers": marker_details,
        }
        correspondence_hash = hash_json_value(correspondence)
        correspondence["correspondence_hash"] = correspondence_hash
        correspondence_layouts.append(correspondence)
        image_points = {
            marker["marker_id"]: marker["image_xy"]
            for marker in marker_details
        }
        world_points = {
            marker["marker_id"]: marker["world_xz_blocks"]
            for marker in marker_details
        }
        marker_ids = correspondence["marker_order"]
        homography = fit_marker_homography(
            image_points,
            world_points,
            marker_ids=marker_ids,
            layout_id=layout_id,
            canonical_camera_pose_id=layout[
                "canonical_camera_pose_id"
            ],
            resolution_id=RESOLUTION_ID,
            image_width_px=640,
            image_height_px=360,
            source_correspondence_hash=correspondence_hash,
            detector_version=detector_version,
            software_runtime_hash=runtime_hash,
        )
        homography_records.append(homography.to_record())
        layout_probe_rows = [
            point
            for point in probes["points"]
            if point["layout_id"] == layout_id
        ]
        validation_pairs = []
        image_regions = []
        validation_sources = []
        for point in layout_probe_rows:
            frozen_frame = next(
                frame
                for frame in frozen_frames
                if frame["frame_id"] == point["frame_id"]
            )
            ground = ground_contact_by_visible_id[point["frame_id"]]
            validation_pairs.append(
                (
                    ground["image_xy"],
                    point["probe_point_world_xz_blocks"],
                )
            )
            image_regions.append(frozen_frame["image_region"])
            validation_sources.append(
                {
                    "frame_id": point["frame_id"],
                    "source_artifact_id": point["source_artifact_id"],
                    "source_frame_idx": point["source_frame_idx"],
                    "source_frame_hash": frozen_frame["source_frame_hash"],
                    "decoded_rgb_hash": frozen_frame["decoded_rgb_hash"],
                    "paired_background_frame_id": frozen_frame[
                        "paired_background_frame_id"
                    ],
                    "split": point["split"],
                    "ground_contact": ground,
                    "true_world_xz_blocks": point[
                        "probe_point_world_xz_blocks"
                    ],
                    "world_y_blocks": point[
                        "probe_point_world_y_blocks"
                    ],
                }
            )
        north_west = world_points["north_west"]
        north_east = world_points["north_east"]
        direction = [
            north_east[0] - north_west[0],
            north_east[1] - north_west[1],
        ]
        norm = math.hypot(*direction)
        wall_unit = [direction[0] / norm, direction[1] / norm]
        summary = summarize_localization(
            homography,
            validation_pairs,
            wall_parallel_origin_xz=north_west,
            wall_parallel_positive_unit_xz=wall_unit,
            image_regions=image_regions,
        )
        for record, source_record in zip(
            summary["records"], validation_sources, strict=True
        ):
            record.update(source_record)
            record["layout_id"] = layout_id
            record["canonical_camera_pose_id"] = layout[
                "canonical_camera_pose_id"
            ]
        all_localization_records.extend(summary["records"])
        localization_layouts.append(
            {
                "layout_id": layout_id,
                "canonical_camera_pose_id": layout[
                    "canonical_camera_pose_id"
                ],
                "wall_parallel_origin_xz": north_west,
                "wall_parallel_positive_unit_xz": wall_unit,
                "homography_version_id": homography.to_record()[
                    "homography_version_id"
                ],
                "summary": summary,
            }
        )
    correspondences = {
        "schema_version": "1.0",
        "homography_correspondence_schema_version": (
            "person-e-real-homography-correspondences-v0.1"
        ),
        "source_revision": person_c_revision,
        "source_document_hash": _sha256(source_payload),
        "probe_document_hash": _sha256(probe_payload),
        "detector_version": detector_version,
        "software_runtime_hash": runtime_hash,
        "layouts": correspondence_layouts,
    }
    correspondence_document_hash, _ = _artifact_hash(correspondences)
    homography_document = {
        "schema_version": "1.0",
        "homography_record_schema_version": (
            "person-e-bound-homography-records-v0.1"
        ),
        "correspondence_document_hash": correspondence_document_hash,
        "detector_version": detector_version,
        "software_runtime": runtime_identity,
        "software_runtime_hash": runtime_hash,
        "records": homography_records,
    }
    homography_document_hash, _ = _artifact_hash(homography_document)

    signed = [
        record["signed_wall_parallel_error_blocks"]
        for record in all_localization_records
    ]
    absolute_wall = [abs(value) for value in signed]
    euclidean = [
        record["euclidean_error_blocks"]
        for record in all_localization_records
    ]
    region_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in all_localization_records:
        region_groups[record["image_region"]].append(record)
    localization = {
        "schema_version": "1.0",
        "localization_report_schema_version": (
            "person-e-real-localization-report-v0.1"
        ),
        "source_probe_revision": person_c_revision,
        "source_probe_document_hash": _sha256(probe_payload),
        "homography_document_hash": homography_document_hash,
        "detector_version": detector_version,
        "ground_contact_localization_method_version": (
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        ),
        "sample_count": len(all_localization_records),
        "signed_wall_parallel_error_blocks": {
            "minimum": min(signed),
            "maximum": max(signed),
            "mean": sum(signed) / len(signed),
            "median": _percentile(signed, 0.5),
        },
        "median_absolute_wall_parallel_error_blocks": _percentile(
            absolute_wall, 0.5
        ),
        "p95_absolute_wall_parallel_error_blocks": _percentile(
            absolute_wall, 0.95
        ),
        "median_euclidean_error_blocks": _percentile(euclidean, 0.5),
        "p95_euclidean_error_blocks": _percentile(euclidean, 0.95),
        "planning_gate_passed": (
            _percentile(absolute_wall, 0.5) <= 0.2
            and _percentile(absolute_wall, 0.95) < 0.5
        ),
        "per_layout": localization_layouts,
        "by_image_region": [
            {
                "image_region": region,
                "sample_count": len(rows),
                "median_absolute_wall_parallel_error_blocks": _percentile(
                    [
                        abs(row["signed_wall_parallel_error_blocks"])
                        for row in rows
                    ],
                    0.5,
                ),
                "p95_absolute_wall_parallel_error_blocks": _percentile(
                    [
                        abs(row["signed_wall_parallel_error_blocks"])
                        for row in rows
                    ],
                    0.95,
                ),
                "median_euclidean_error_blocks": _percentile(
                    [row["euclidean_error_blocks"] for row in rows], 0.5
                ),
                "p95_euclidean_error_blocks": _percentile(
                    [row["euclidean_error_blocks"] for row in rows], 0.95
                ),
            }
            for region, rows in sorted(region_groups.items())
        ],
        "by_location": [
            {
                "location_id": record["frame_id"],
                "layout_id": record["layout_id"],
                "image_region": record["image_region"],
                "true_world_xz_blocks": record["true_world_xz_blocks"],
                "signed_wall_parallel_error_blocks": record[
                    "signed_wall_parallel_error_blocks"
                ],
                "absolute_wall_parallel_error_blocks": abs(
                    record["signed_wall_parallel_error_blocks"]
                ),
                "euclidean_error_blocks": record[
                    "euclidean_error_blocks"
                ],
                "sample_count": 1,
            }
            for record in sorted(
                all_localization_records,
                key=lambda row: (row["layout_id"], row["frame_id"]),
            )
        ],
        "records": all_localization_records,
    }

    documents = {
        **step2_1_documents,
        "frozen_split_manifest.json": split,
        "split_coverage_report.json": coverage,
        "frozen_detector_config.json": config,
        "calibration_detection_records.json": detections,
        "calibration_report.json": calibration_report,
        "detector_version_record.json": detector_version_record,
        "homography_correspondences.json": correspondences,
        "homography_record.json": homography_document,
        "localization_validation_report.json": localization,
    }
    provenance_records = []
    direct_inputs = {
        "registry_snapshot.json": [
            (
                f"git:{person_a_registry_handoff_revision}:"
                f"{PERSON_A_REGISTRY_HANDOFF_ROOT}/handoff_index.json"
            ),
            (
                f"git:{person_c_registry_handoff_revision}:"
                f"{PERSON_C_REGISTRY_HANDOFF_ROOT}/"
                "pilot_registry_handoff.json"
            ),
            (
                f"git:{person_c_registry_handoff_revision}:"
                f"{PERSON_C_REGISTRY_HANDOFF_ROOT}/"
                "artifact_verification.json"
            ),
        ],
        "registry_query_example.json": ["registry_snapshot.json"],
        "step2_1_registry_receipt.json": [
            "registry_snapshot.json",
            "registry_query_example.json",
            (
                f"git:{person_a_registry_handoff_revision}:"
                f"{PERSON_A_REGISTRY_HANDOFF_ROOT}/handoff_index.json"
            ),
            (
                f"git:{person_c_registry_handoff_revision}:"
                f"{PERSON_C_REGISTRY_HANDOFF_ROOT}/attempt_scope.json"
            ),
        ],
        "frozen_split_manifest.json": [
            f"git:{person_c_revision}:{PERSON_C_INPUT_PATH}",
            f"git:{person_c_revision}:{PERSON_C_PROVENANCE_PATH}",
            f"git:{person_b_revision}:src/mineocclude/probes/splits.py",
        ],
        "split_coverage_report.json": ["frozen_split_manifest.json"],
        "frozen_detector_config.json": ["frozen_split_manifest.json"],
        "calibration_detection_records.json": [
            "frozen_split_manifest.json",
            "frozen_detector_config.json",
        ],
        "calibration_report.json": [
            "calibration_detection_records.json",
            "frozen_detector_config.json",
        ],
        "detector_version_record.json": [
            "frozen_detector_config.json",
            "calibration_report.json",
        ],
        "homography_correspondences.json": [
            "frozen_split_manifest.json",
            f"git:{person_c_revision}:{PERSON_C_PROBE_PATH}",
        ],
        "homography_record.json": [
            "homography_correspondences.json",
            "detector_version_record.json",
        ],
        "localization_validation_report.json": [
            "homography_record.json",
            f"git:{person_c_revision}:{PERSON_C_PROBE_PATH}",
        ],
    }
    for path, document in sorted(documents.items()):
        digest, size = _artifact_hash(document)
        provenance_records.append(
            {
                "artifact_id": f"person_e_phase2_v0_1:{path}",
                "path": path,
                "sha256": digest,
                "size_bytes": size,
                "direct_inputs": direct_inputs.get(path, []),
                "status": "accepted",
                "shared_immutable_registry_emitted": path
                in {
                    "registry_snapshot.json",
                    "registry_query_example.json",
                    "step2_1_registry_receipt.json",
                },
            }
        )
    provenance_index = {
        "schema_version": "1.0",
        "provenance_index_schema_version": (
            "person-e-phase2-provenance-index-v0.1"
        ),
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "source_revisions": {
            "person_c": person_c_revision,
            "person_b": person_b_revision,
            "person_e_base": PERSON_E_BASE_SHA,
            "person_a_registry_handoff": (
                person_a_registry_handoff_revision
            ),
            "person_a_registry_source": PERSON_A_SOURCE_REVISION,
            "person_c_registry_handoff": (
                person_c_registry_handoff_revision
            ),
            "person_c_registry_source": (
                PERSON_C_REGISTRY_SOURCE_REVISION
            ),
        },
        "shared_immutable_registry_status": (
            "step2_1_real_registry_emitted_and_validated"
        ),
        "records": provenance_records,
    }
    documents["provenance_index.json"] = provenance_index
    provenance_index_hash, _ = _artifact_hash(provenance_index)
    documents["phase2_status.json"] = {
        "schema_version": "1.0",
        "status_schema_version": "person-e-phase2-status-v0.1",
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "overall_status": "PARTIAL",
        "steps": [
            {
                "step": "2.1",
                "status": "PASS",
                "evidence": "step2_1_registry_receipt.json",
                "remaining_blocker": None,
            },
            {
                "step": "2.2",
                "status": "PASS",
                "evidence": "frozen_split_manifest.json",
                "remaining_blocker": None,
            },
            {
                "step": "2.3",
                "status": "PASS",
                "evidence": "calibration_report.json",
                "remaining_blocker": None,
            },
            {
                "step": "2.4",
                "status": "PARTIAL",
                "evidence": "localization_validation_report.json",
                "remaining_blocker": (
                    "measured_independent_probe_localization_gate_failed"
                    if not localization["planning_gate_passed"]
                    else None
                ),
            },
        ],
        "provenance_index_hash": provenance_index_hash,
        "real_completed_a_or_c_pilot_records_emitted": True,
        "detector_heldout_performance_claimed": False,
        "homography_planning_gate_passed": localization[
            "planning_gate_passed"
        ],
    }
    return documents


def main() -> None:
    args = parse_args()
    documents = _build_documents(
        config_template=args.config_template,
        person_c_revision=args.person_c_revision,
        person_b_revision=args.person_b_revision,
        person_a_registry_handoff_revision=(
            args.person_a_registry_handoff_revision
        ),
        person_c_registry_handoff_revision=(
            args.person_c_registry_handoff_revision
        ),
    )
    for relative_path, document in sorted(documents.items()):
        write_json_exclusive(args.output_dir / relative_path, document)


if __name__ == "__main__":
    main()
