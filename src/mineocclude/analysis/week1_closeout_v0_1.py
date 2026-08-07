"""Fail-closed, validation-only checker for the Person B Week 1 closeout.

The checker binds the small ten-pilot evidence package to immutable Git
objects.  It deliberately does not invoke a scientific runner, materialize
external activation bytes, inspect U4 output, or write any files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_ID = "person-b-week1-mvp-closeout-v0-1"
SCHEMA_VERSION = "1.0"
PACKAGE_DIRECTORY = "docs/status/person_b_week1_mvp_closeout_v0_1"
PACKAGE_FILES = (
    "authority_binding.json",
    "roadmap_completion_matrix.json",
    "scope_shortfall.json",
    "checkpoint_decision.json",
    "reproducibility_status.json",
    "external_blockers.json",
    "validation_receipt.json",
    "checkpoint_memo.md",
    "sha256_inventory.json",
)
INVENTORIED_FILES = PACKAGE_FILES[:-1]

HANDOFF_COMMIT = "1905f4bec7c917baafa084d7bf3a473fb8e40460"
HANDOFF_PATH = (
    "docs/status/integration/mvp_step4_1_candidate_v0_1/handoffs/"
    "person_b_next_phase_input_manifest.json"
)
HANDOFF_RAW_BYTE_SIZE = 25_849
HANDOFF_RAW_SHA256 = "60b98bf60fb696a052a3ebe9f5ba8af846977da5871bd760f5c71a42f191d6c6"
HANDOFF_GIT_BLOB_OID_SHA1 = "040c85ce2a2b9e1df161a2c613f42ffc2203a01d"
STARTING_HEAD = "98f50761ecb99bc14ed5d1ebb67aedc8dcfd3327"

AUTHORITY_COMMITS = {
    "person_a": "397ba849adc63df80912c21dd1efacb1e29b8977",
    "person_b": "8c5374d00983e6fec22f560a9fd5849e92060f3e",
    "person_c": "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960",
    "person_d": "5ea6ce92890da7faa46f6aa837135081633d5f3d",
    "person_e": "ab41a76ce0c855c0ac54c59c736bac7599f7e69d",
}
EXTERNAL_ACTIVATION_SHA256 = (
    "1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9"
)
EXTERNAL_ACTIVATION_SIZE = 245_491_346
EXTERNAL_ACTIVATION_URI = (
    "file:///home/sagemaker-user/person-a-phase6-approved-outputs/"
    "person-a-phase6-ten-pilot-expansion-seed-20260725/combined_activation_index.json"
)

POSITIVE_CONTROL_PATH = (
    "docs/status/person_b_phase6_step6_6_positive_control_v0_1/"
    "positive_control_decision.json"
)
POSITIVE_CONTROL_SHA256 = (
    "742557b32326180003b1cd83ed5db6f1a1ebfebd692d969809698d323f239056"
)
FINAL_COMPARISON_PATH = (
    "docs/status/person_b_phase4_step4_1_final_comparison_completion_v0_1/"
    "layer_band_decision.json"
)
FINAL_COMPARISON_SHA256 = (
    "7737b43ed13b1a7c7f3af1ebb07dbd050224e50064873b4bdbce47273e72d36c"
)
REGISTRY_VALIDATION_PATH = (
    "docs/status/person_b_phase4_step4_1_registry_v2_final_evidence_v0_1/"
    "validation_receipt.json"
)
REGISTRY_VALIDATION_SHA256 = (
    "0f8ea56206b45a0a1570667200bb3945875cad188c88bcd94521dd3d6cc68fae"
)
REGISTRY_DECISION_PATH = (
    "docs/status/person_b_phase4_step4_1_registry_v2_final_evidence_v0_1/"
    "registration_decision.json"
)
REGISTRY_MANIFEST_PATH = (
    "docs/status/person_b_phase4_step4_1_registry_v2_final_evidence_v0_1/"
    "trusted_manifest_record.json"
)

PHASE_COUNTS = (6, 9, 10, 9, 9, 10, 8, 8, 8, 8)
STATUS_COUNTS = {
    "complete_current": 17,
    "complete_scoped": 38,
    "superseded_marker": 5,
    "blocked_external": 19,
    "not_authorized": 6,
}
ALLOWED_STATUSES = {
    "complete_current",
    "complete_scoped",
    "superseded_marker",
    "blocked_external",
    "not_authorized",
}
STEP_ID_RE = re.compile(r"^(0|[1-9][0-9]*)\.([1-9][0-9]*)$")


class CloseoutValidationError(ValueError):
    """Raised when a closeout invariant fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CloseoutValidationError(message)


def require_equal(actual: Any, expected: Any, name: str) -> None:
    require(actual == expected, f"{name}: expected {expected!r}, got {actual!r}")


def require_bool(actual: Any, expected: bool, name: str) -> None:
    require(type(actual) is bool, f"{name}: expected boolean")
    require_equal(actual, expected, name)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Repository JSON canonicalization (sorted keys, two-space indent)."""

    try:
        text = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return (text + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise CloseoutValidationError(f"cannot canonicalize JSON: {error}") from error


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        require(key not in value, f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _reject_constant(token: str) -> Any:
    raise CloseoutValidationError(f"non-finite JSON constant: {token}")


def _all_finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(_all_finite(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return all(_all_finite(item) for item in value)
    return True


def load_strict_json(
    payload: bytes, label: str, *, canonical: bool = True
) -> dict[str, Any]:
    """Parse one UTF-8 JSON object, rejecting duplicate/non-finite values.

    Handoff authorities are historical blobs and are parsed strictly without a
    canonical-byte assertion; closeout package documents use ``canonical=True``.
    """

    require(not payload.startswith(b"\xef\xbb\xbf"), f"{label}: UTF-8 BOM forbidden")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except CloseoutValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CloseoutValidationError(f"{label}: invalid JSON: {error}") from error
    require(isinstance(value, dict), f"{label}: root must be an object")
    require(_all_finite(value), f"{label}: non-finite number")
    if canonical:
        require_equal(
            payload, canonical_json_bytes(value), f"{label}: noncanonical JSON bytes"
        )
    return value


def load_canonical_json(path: Path) -> dict[str, Any]:
    return load_strict_json(path.read_bytes(), str(path), canonical=True)


def _git_bytes(repository_root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise CloseoutValidationError(
            f"git {' '.join(arguments)} failed: {detail or 'unknown error'}"
        )
    return result.stdout


def _git_text(repository_root: Path, *arguments: str) -> str:
    return _git_bytes(repository_root, *arguments).decode("utf-8").strip()


def _require_commit(repository_root: Path, commit: str, label: str) -> None:
    require(
        isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
        f"{label}: invalid commit",
    )
    require_equal(
        _git_text(repository_root, "cat-file", "-t", commit),
        "commit",
        f"{label} object type",
    )


def _reject_u4_path(path: str | Path) -> None:
    normalized = str(path).replace("\\", "/").casefold()
    require("u4" not in normalized, f"U4 path read prohibited: {path}")


def _git_blob(repository_root: Path, commit: str, path: str) -> bytes:
    _reject_u4_path(path)
    require(
        "\x00" not in path and not path.startswith("/"),
        f"invalid repository path: {path}",
    )
    require(".." not in Path(path).parts, f"parent repository path forbidden: {path}")
    return _git_bytes(repository_root, "cat-file", "blob", f"{commit}:{path}")


def _git_head(repository_root: Path) -> str:
    return _git_text(repository_root, "rev-parse", "HEAD")


def _require_current_head_descends_from_starting_authority(
    repository_root: Path,
) -> None:
    """Require that the checked-out HEAD is the bound authority or its descendant."""

    _require_commit(repository_root, STARTING_HEAD, "starting authority commit")
    current_head = _git_head(repository_root)
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "merge-base",
            "--is-ancestor",
            STARTING_HEAD,
            current_head,
        ],
        capture_output=True,
        check=False,
    )
    require(
        result.returncode == 0,
        (
            "current HEAD is unrelated to the starting authority: "
            f"{current_head} does not descend from {STARTING_HEAD}"
        ),
    )


def _schema(document: Mapping[str, Any], name: str) -> None:
    require_equal(
        document.get("schema_version"), SCHEMA_VERSION, f"{name} schema_version"
    )
    schema_id = document.get("schema_id")
    require(
        isinstance(schema_id, str)
        and (schema_id == SCHEMA_ID or schema_id.startswith(f"{SCHEMA_ID}-")),
        f"{name} schema_id",
    )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{label}: expected object")
    return value


def _validate_handoff(repository_root: Path) -> dict[str, Any]:
    _require_commit(repository_root, HANDOFF_COMMIT, "handoff commit")
    blob = _git_blob(repository_root, HANDOFF_COMMIT, HANDOFF_PATH)
    require_equal(len(blob), HANDOFF_RAW_BYTE_SIZE, "handoff raw byte size")
    require_equal(sha256_bytes(blob), HANDOFF_RAW_SHA256, "handoff raw SHA-256")
    require_equal(
        _git_text(repository_root, "rev-parse", f"{HANDOFF_COMMIT}:{HANDOFF_PATH}"),
        HANDOFF_GIT_BLOB_OID_SHA1,
        "handoff Git blob OID SHA-1",
    )
    manifest = load_strict_json(
        blob, f"{HANDOFF_COMMIT}:{HANDOFF_PATH}", canonical=False
    )
    require_bool(
        manifest.get("PERSON_B_NEXT_PHASE_HANDOFF_READY"), True, "handoff ready marker"
    )
    require_equal(manifest.get("blocking_missing_inputs"), [], "handoff missing inputs")
    require_equal(manifest.get("consumer_role"), "person_b", "handoff consumer role")
    require_equal(
        manifest.get("candidate_branch"),
        "integration/mvp-step4-1-candidate",
        "handoff candidate branch",
    )
    authorities = _mapping(
        manifest.get("authority_commits"), "handoff authority commits"
    )
    require_equal(dict(authorities), AUTHORITY_COMMITS, "handoff authority commits")
    for role, commit in AUTHORITY_COMMITS.items():
        _require_commit(repository_root, commit, f"handoff authority {role}")

    identity = _mapping(
        manifest.get("accepted_identity_set"), "handoff accepted identity set"
    )
    require_equal(
        identity.get("admitted_sample_count"), 1695, "handoff admitted samples"
    )
    require_equal(
        identity.get("excluded_sample_count"), 179, "handoff excluded samples"
    )
    require_equal(
        identity.get("activation_row_count"), 37_480, "handoff activation rows"
    )
    require_equal(
        identity.get("activation_chunk_count"), 200, "handoff activation chunks"
    )
    require_equal(identity.get("fold_count"), 5, "handoff fold count")
    trajectory_ids = identity.get("trajectory_ids")
    require(isinstance(trajectory_ids, list), "handoff trajectory ids")
    require_equal(len(trajectory_ids), 10, "handoff trajectory count")

    external = _mapping(
        manifest.get("external_materialization"), "handoff external materialization"
    )
    require_equal(
        external.get("sha256"), EXTERNAL_ACTIVATION_SHA256, "handoff external SHA-256"
    )
    require_equal(
        external.get("byte_size"),
        EXTERNAL_ACTIVATION_SIZE,
        "handoff external byte size",
    )
    require_bool(
        external.get("required_for_computation"), True, "handoff external required"
    )
    require_bool(
        external.get("repository_payload_present"),
        False,
        "handoff external repository payload",
    )

    inputs = manifest.get("inputs")
    require(isinstance(inputs, list), "handoff inputs")
    require_equal(len(inputs), 12, "handoff repository input count")
    seen_paths: set[str] = set()
    for index, item in enumerate(inputs, start=1):
        row = _mapping(item, f"handoff input {index}")
        path = row.get("repository_relative_path")
        require(isinstance(path, str) and path, f"handoff input {index} path")
        _reject_u4_path(path)
        require(path not in seen_paths, f"handoff duplicate input path: {path}")
        seen_paths.add(path)
        source_commit = row.get("source_commit")
        require(isinstance(source_commit, str), f"handoff input {index} source commit")
        _require_commit(
            repository_root, source_commit, f"handoff input {index} source commit"
        )
        source_blob = _git_blob(repository_root, source_commit, path)
        require_equal(
            sha256_bytes(source_blob),
            row.get("sha256"),
            f"handoff input {index} SHA-256",
        )
        validation = _mapping(
            row.get("validation"), f"handoff input {index} validation"
        )
        require_bool(
            validation.get("path_exists"), True, f"handoff input {index} path_exists"
        )
        require_bool(
            validation.get("sha256_verified"),
            True,
            f"handoff input {index} sha256_verified",
        )
        require_bool(
            validation.get("authority_blob_matches_candidate"),
            True,
            f"handoff input {index} authority match",
        )
    return {
        "manifest_sha256": sha256_bytes(blob),
        "input_count": len(inputs),
        "external_activation_index": {
            "sha256": EXTERNAL_ACTIVATION_SHA256,
            "byte_size": EXTERNAL_ACTIVATION_SIZE,
        },
    }


def _validate_authority_binding(
    document: Mapping[str, Any], handoff: Mapping[str, Any]
) -> None:
    _schema(document, "authority_binding")
    require_equal(
        document.get("starting_person_b_commit"),
        STARTING_HEAD,
        "authority starting_person_b_commit",
    )
    require_equal(
        document.get("handoff_commit"), HANDOFF_COMMIT, "authority handoff_commit"
    )
    require_equal(
        document.get("handoff_manifest_path"),
        HANDOFF_PATH,
        "authority handoff_manifest_path",
    )
    require_equal(
        document.get("handoff_manifest_raw_byte_size"),
        HANDOFF_RAW_BYTE_SIZE,
        "authority handoff byte size",
    )
    require_equal(
        document.get("handoff_manifest_raw_sha256"),
        HANDOFF_RAW_SHA256,
        "authority handoff raw SHA-256",
    )
    require_equal(
        document.get("handoff_manifest_git_blob_oid_sha1"),
        HANDOFF_GIT_BLOB_OID_SHA1,
        "authority handoff Git blob OID",
    )
    handoff_record = _mapping(document.get("handoff"), "authority handoff object")
    require_equal(
        handoff_record.get("commit"), HANDOFF_COMMIT, "authority handoff.commit"
    )
    require_equal(handoff_record.get("path"), HANDOFF_PATH, "authority handoff.path")
    require_equal(
        handoff_record.get("raw_byte_size"),
        HANDOFF_RAW_BYTE_SIZE,
        "authority handoff.raw_byte_size",
    )
    require_equal(
        handoff_record.get("raw_sha256"),
        HANDOFF_RAW_SHA256,
        "authority handoff.raw_sha256",
    )
    require_equal(
        handoff_record.get("git_blob_oid_sha1"),
        HANDOFF_GIT_BLOB_OID_SHA1,
        "authority handoff.git_blob_oid_sha1",
    )
    authorities = _mapping(document.get("authority_commits"), "authority commits")
    require_equal(dict(authorities), AUTHORITY_COMMITS, "authority commits")
    require_equal(handoff.get("input_count"), 12, "authority handoff input count")


def _validate_roadmap(document: Mapping[str, Any]) -> dict[str, Any]:
    _schema(document, "roadmap_completion_matrix")
    phase_counts = document.get("phase_counts")
    require(isinstance(phase_counts, list), "roadmap phase_counts")
    normalized = tuple(phase_counts)
    require_equal(normalized, PHASE_COUNTS, "roadmap phase_counts")
    phase_step_counts = document.get("phase_step_counts")
    require(isinstance(phase_step_counts, Mapping), "roadmap phase_step_counts")
    require_equal(
        set(phase_step_counts),
        {str(index) for index in range(10)},
        "roadmap phase_step_counts keys",
    )
    require_equal(
        {str(index): phase_step_counts[str(index)] for index in range(10)},
        {str(index): count for index, count in enumerate(PHASE_COUNTS)},
        "roadmap phase_step_counts",
    )
    rows = document.get("steps")
    require(isinstance(rows, list), "roadmap steps")
    require_equal(len(rows), sum(PHASE_COUNTS), "roadmap step count")
    expected_ids = {
        f"{phase}.{step}"
        for phase, count in enumerate(PHASE_COUNTS)
        for step in range(1, count + 1)
    }
    seen: set[str] = set()
    observed_counts = [0] * 10
    for index, item in enumerate(rows, start=1):
        row = _mapping(item, f"roadmap step {index}")
        step_id = row.get("step_id")
        require(
            isinstance(step_id, str) and STEP_ID_RE.fullmatch(step_id) is not None,
            f"roadmap step {index} id",
        )
        require(step_id not in seen, f"roadmap duplicate step_id: {step_id}")
        require(step_id in expected_ids, f"roadmap unexpected step_id: {step_id}")
        seen.add(step_id)
        phase = int(step_id.split(".", 1)[0])
        require_equal(row.get("phase"), phase, f"roadmap {step_id} phase")
        status = row.get("status")
        require(status in ALLOWED_STATUSES, f"roadmap {step_id} status")
        observed_counts[phase] += 1
        evidence_paths = row.get("evidence_paths")
        require(isinstance(evidence_paths, list), f"roadmap {step_id} evidence_paths")
        for evidence_path in evidence_paths:
            require(
                isinstance(evidence_path, str) and evidence_path,
                f"roadmap {step_id} evidence path",
            )
            _reject_u4_path(evidence_path)
        require(
            isinstance(row.get("title"), str) and row["title"],
            f"roadmap {step_id} title",
        )
        require(
            isinstance(row.get("remaining_condition"), str),
            f"roadmap {step_id} remaining_condition",
        )
        if phase in (7, 8, 9):
            require(
                status not in {"complete_current", "complete_scoped"},
                f"roadmap false Phase {phase} completion: {step_id}",
            )
    require_equal(seen, expected_ids, "roadmap step IDs")
    require_equal(tuple(observed_counts), PHASE_COUNTS, "roadmap observed phase counts")
    observed_status_counts = {
        status: sum(1 for row in rows if row.get("status") == status)
        for status in ALLOWED_STATUSES
    }
    require_equal(observed_status_counts, STATUS_COUNTS, "roadmap status_counts")
    require_equal(
        document.get("status_counts"), STATUS_COUNTS, "roadmap status_counts field"
    )
    phases = document.get("phases")
    require(isinstance(phases, list), "roadmap phases")
    require_equal(len(phases), len(PHASE_COUNTS), "roadmap phase summary count")
    for phase, expected_step_count in enumerate(PHASE_COUNTS):
        summary = _mapping(phases[phase], f"roadmap phase summary {phase}")
        require_equal(summary.get("phase"), phase, f"roadmap phase summary {phase} id")
        require_equal(
            summary.get("step_count"),
            expected_step_count,
            f"roadmap phase summary {phase} step count",
        )
        require_equal(
            summary.get("step_ids"),
            [f"{phase}.{step}" for step in range(1, expected_step_count + 1)],
            f"roadmap phase summary {phase} step IDs",
        )
        phase_status_counts = _mapping(
            summary.get("status_counts"),
            f"roadmap phase summary {phase} status counts",
        )
        observed_phase_status_counts = {
            status: sum(
                1
                for row in rows
                if row.get("phase") == phase and row.get("status") == status
            )
            for status in ALLOWED_STATUSES
        }
        require_equal(
            dict(phase_status_counts),
            observed_phase_status_counts,
            f"roadmap phase summary {phase} status counts",
        )
    step_41 = next(row for row in rows if row.get("step_id") == "4.1")
    require_equal(
        step_41.get("status"), "superseded_marker", "roadmap Step 4.1 promotion"
    )
    step_55 = next(row for row in rows if row.get("step_id") == "5.5")
    require_equal(
        step_55.get("status"), "complete_current", "roadmap Step 5.5 status"
    )
    require_equal(
        step_55.get("evidence_paths"),
        [
            "src/mineocclude/metrics/u2_calibration.py",
            "tests/metrics/test_person_b_metrics.py",
        ],
        "roadmap Step 5.5 evidence paths",
    )
    require_equal(
        step_55.get("remaining_condition"),
        "No additional condition for the committed quadratic tau-squared sensitivity implementation; production claims still require accepted inputs and execution.",
        "roadmap Step 5.5 remaining condition",
    )
    require_equal(document.get("roadmap_step_count"), 85, "roadmap roadmap_step_count")
    require_equal(document.get("phase_count"), 10, "roadmap phase_count")
    require_equal(document.get("roadmap_complete"), False, "roadmap complete")
    return {"step_count": 85, "phase_count": 10, "phase_counts": list(PHASE_COUNTS)}


def _validate_scope(document: Mapping[str, Any]) -> None:
    _schema(document, "scope_shortfall")
    planned = _mapping(document.get("planned"), "scope planned")
    available = _mapping(document.get("available"), "scope available")
    missing = _mapping(document.get("missing"), "scope missing")

    def component(mapping: Mapping[str, Any], name: str, label: str) -> int:
        require(name in mapping, f"{label}: missing component")
        value = mapping[name]
        require(
            isinstance(value, int) and not isinstance(value, bool),
            f"{label} integer",
        )
        return value

    planned_total = component(planned, "total", "planned total")
    planned_core = component(planned, "core", "planned core")
    planned_visible = component(planned, "visible", "planned visible")
    planned_no_object = component(planned, "no_object", "planned no_object")
    planned_sentinel = component(planned, "sentinel", "planned sentinel")
    require_equal(
        (
            planned_total,
            planned_core,
            planned_visible,
            planned_no_object,
            planned_sentinel,
        ),
        (66, 48, 6, 6, 6),
        "planned scope",
    )
    available_total = component(available, "total", "available total")
    available_core = component(available, "core", "available core")
    available_visible = component(available, "visible", "available visible")
    available_no_object = component(available, "no_object", "available no_object")
    available_sentinel = component(available, "sentinel", "available sentinel")
    require_equal(
        (
            available_total,
            available_core,
            available_visible,
            available_no_object,
            available_sentinel,
        ),
        (10, 5, 5, 0, 0),
        "available scope",
    )
    missing_total = component(missing, "total", "missing total")
    missing_core = component(missing, "core", "missing core")
    missing_visible = component(missing, "visible", "missing visible")
    missing_no_object = component(missing, "no_object", "missing no_object")
    missing_sentinel = component(missing, "sentinel", "missing sentinel")
    require_equal(
        (
            missing_total,
            missing_core,
            missing_visible,
            missing_no_object,
            missing_sentinel,
        ),
        (56, 43, 1, 6, 6),
        "missing scope",
    )
    require_equal(missing_total, planned_total - available_total, "scope arithmetic")
    for key, expected in (
        ("admitted_sample_count", 1695),
        ("excluded_sample_count", 179),
        ("activation_row_count", 37480),
        ("activation_chunk_count", 200),
        ("fold_count", 5),
    ):
        require_equal(document.get(key), expected, f"scope {key}")
    require_equal(document.get("ten_pilot_is_not_66_mvp"), True, "scope boundary")


def _validate_checkpoint(document: Mapping[str, Any]) -> None:
    _schema(document, "checkpoint_decision")
    require_equal(document.get("decision"), "YELLOW", "checkpoint decision")
    require_equal(document.get("color"), "YELLOW", "checkpoint color")
    require_equal(
        document.get("step4_1_decision"), "FAIL", "checkpoint Step 4.1 decision"
    )
    require_bool(
        document.get("positive_control_pass"), True, "checkpoint positive control"
    )
    require_equal(
        document.get("qualifying_layer_bands"), [], "checkpoint qualifying bands"
    )
    require_equal(document.get("layer_gate_count"), 20, "checkpoint layer gate count")
    require_equal(
        document.get("classification"),
        "clean_negative_bounded_ten_pilot_linear_probe_study",
        "checkpoint classification",
    )
    require_bool(
        document.get("belief_absence_proof"), False, "checkpoint belief absence proof"
    )
    require_bool(document.get("u4_authorized"), False, "checkpoint U4 authorization")
    require_bool(document.get("u4_output_inspected"), False, "checkpoint U4 inspection")
    require_bool(
        document.get("scientific_execution_performed"),
        False,
        "checkpoint scientific execution",
    )
    alternatives = document.get("unresolved_alternatives")
    require(isinstance(alternatives, list), "checkpoint unresolved alternatives")
    require(
        all(isinstance(item, str) for item in alternatives),
        "checkpoint unresolved alternatives entries",
    )
    alternative_text = " ".join(alternatives).casefold()
    for phrase in ("absence", "context-bound memory loss", "nonlinear measurement"):
        require(phrase in alternative_text, f"checkpoint alternative missing: {phrase}")
    claims = document.get("claim_boundaries")
    require(isinstance(claims, list), "checkpoint claim_boundaries")
    require(
        all(isinstance(item, str) for item in claims),
        "checkpoint claim_boundaries entries",
    )
    claim_text = " ".join(claims).casefold()
    for phrase in ("not proof", "belief", "not the 66", "not u4", "favorable rerun"):
        require(phrase in claim_text, f"checkpoint claim boundary missing: {phrase}")


def _validate_reproducibility(document: Mapping[str, Any]) -> None:
    _schema(document, "reproducibility_status")
    require_equal(
        document.get("integration_structural_validation"),
        "PASS",
        "reproducibility structural validation",
    )
    require_equal(
        document.get("clean_scientific_reproduction"),
        "BLOCKED_EXTERNAL_MATERIALIZATION",
        "reproducibility clean status",
    )
    require_equal(
        document.get("external_activation_uri"),
        EXTERNAL_ACTIVATION_URI,
        "reproducibility external URI",
    )
    require_equal(
        document.get("external_activation_sha256"),
        EXTERNAL_ACTIVATION_SHA256,
        "reproducibility external SHA-256",
    )
    require_equal(
        document.get("external_activation_byte_size"),
        EXTERNAL_ACTIVATION_SIZE,
        "reproducibility external byte size",
    )
    require_bool(
        document.get("scientific_execution_performed"),
        False,
        "reproducibility scientific execution",
    )
    require_equal(document.get("result_tag"), None, "reproducibility result tag")


def _validate_external_blockers(document: Mapping[str, Any]) -> None:
    _schema(document, "external_blockers")
    require_equal(document.get("status"), "BLOCKED_EXTERNAL", "external blocker status")
    blockers = document.get("blockers")
    require(isinstance(blockers, list) and blockers, "external blockers list")
    for index, item in enumerate(blockers, start=1):
        row = _mapping(item, f"external blocker {index}")
        require(
            isinstance(row.get("owner"), str) and row["owner"],
            f"external blocker {index} owner",
        )
        require(
            isinstance(row.get("action"), str) and row["action"],
            f"external blocker {index} action",
        )


def _validate_receipt(document: Mapping[str, Any], roadmap: Mapping[str, Any]) -> None:
    _schema(document, "validation_receipt")
    require_equal(document.get("status"), "PASS", "validation receipt status")
    require_bool(
        document.get("package_canonical"), True, "validation receipt package canonical"
    )
    require_bool(
        document.get("inventory_verified"), True, "validation receipt inventory"
    )
    require_equal(document.get("steps_validated"), 85, "validation receipt steps")
    require_equal(document.get("phase_count"), 10, "validation receipt phases")
    require_equal(
        document.get("roadmap_step_count"),
        85,
        "validation receipt roadmap steps",
    )
    require_bool(
        document.get("scientific_execution_performed"),
        False,
        "validation receipt science",
    )
    require_bool(document.get("u4_output_inspected"), False, "validation receipt U4")
    require_bool(
        document.get("frozen_artifacts_modified"),
        False,
        "validation receipt frozen artifacts",
    )
    require_bool(
        document.get("roadmap_complete"), False, "validation receipt roadmap completion"
    )
    require_equal(document.get("result_tag"), None, "validation receipt result tag")
    require_equal(roadmap.get("step_count"), 85, "receipt roadmap step count")


def _validate_evidence(repository_root: Path) -> dict[str, Any]:
    _require_commit(repository_root, STARTING_HEAD, "starting evidence commit")
    positive_blob = _git_blob(repository_root, STARTING_HEAD, POSITIVE_CONTROL_PATH)
    require_equal(
        sha256_bytes(positive_blob), POSITIVE_CONTROL_SHA256, "positive control SHA-256"
    )
    positive = load_strict_json(
        positive_blob, f"{STARTING_HEAD}:{POSITIVE_CONTROL_PATH}"
    )
    require_bool(positive.get("positive_control_pass"), True, "positive control pass")
    require_bool(
        positive.get("hidden_state_interpretation_authorized"),
        False,
        "positive control hidden interpretation",
    )
    require_bool(positive.get("u4_output_inspected"), False, "positive control U4")

    comparison_blob = _git_blob(repository_root, STARTING_HEAD, FINAL_COMPARISON_PATH)
    require_equal(
        sha256_bytes(comparison_blob),
        FINAL_COMPARISON_SHA256,
        "final comparison SHA-256",
    )
    comparison = load_strict_json(
        comparison_blob, f"{STARTING_HEAD}:{FINAL_COMPARISON_PATH}"
    )
    require_equal(comparison.get("decision"), "FAIL", "final comparison decision")
    require_equal(
        comparison.get("qualifying_layer_bands"),
        [],
        "final comparison qualifying bands",
    )
    require_bool(comparison.get("u4_output_inspected"), False, "final comparison U4")
    gates = comparison.get("layer_gates")
    require(
        isinstance(gates, list) and len(gates) == 20,
        "final comparison layer gate count",
    )
    layer_ids: set[int] = set()
    for gate in gates:
        row = _mapping(gate, "final comparison layer gate")
        layer = row.get("layer_idx")
        require(
            isinstance(layer, int) and not isinstance(layer, bool),
            "final comparison layer index",
        )
        layer_ids.add(layer)
        require_bool(
            row.get("qualifies"), False, f"final comparison layer {layer} qualifies"
        )
        for gate_name in ("U1_green", "U2_green", "U3_green"):
            require_bool(
                row.get(gate_name),
                False,
                f"final comparison layer {layer} {gate_name}",
            )
    require_equal(layer_ids, set(range(20)), "final comparison layer indices")

    registry_blob = _git_blob(repository_root, STARTING_HEAD, REGISTRY_VALIDATION_PATH)
    require_equal(
        sha256_bytes(registry_blob),
        REGISTRY_VALIDATION_SHA256,
        "registry validation SHA-256",
    )
    registry = load_strict_json(
        registry_blob, f"{STARTING_HEAD}:{REGISTRY_VALIDATION_PATH}"
    )
    require_equal(registry.get("status"), "PASS", "registry validation status")
    require_equal(
        registry.get("acceptance_decision"), "FAIL", "registry acceptance decision"
    )
    require_equal(
        registry.get("metric_owner_status"), "accepted", "registry metric owner status"
    )
    require_equal(
        registry.get("prediction_owner_status"),
        "accepted",
        "registry prediction owner status",
    )
    require_bool(
        registry.get("registry_v2_import_ready"), True, "registry import ready"
    )
    require_bool(
        registry.get("scientific_execution_performed"),
        False,
        "registry scientific execution",
    )
    require_bool(
        registry.get("manual_u4_inspection_performed"), False, "registry U4 inspection"
    )
    require_bool(
        registry.get("external_artifacts_modified"),
        False,
        "registry external artifacts",
    )

    decision = load_strict_json(
        _git_blob(repository_root, STARTING_HEAD, REGISTRY_DECISION_PATH),
        f"{STARTING_HEAD}:{REGISTRY_DECISION_PATH}",
    )
    require_equal(
        decision.get("acceptance_decision"), "FAIL", "registry registration acceptance"
    )
    manifest = load_strict_json(
        _git_blob(repository_root, STARTING_HEAD, REGISTRY_MANIFEST_PATH),
        f"{STARTING_HEAD}:{REGISTRY_MANIFEST_PATH}",
    )
    require_equal(
        manifest.get("decision"),
        "accepted",
        "registry final evidence manifest decision",
    )
    return {
        "positive_control_pass": True,
        "step4_1_decision": "FAIL",
        "layer_gate_count": 20,
        "qualifying_layer_bands": [],
        "registry_acceptance_decision": "FAIL",
    }


def _validate_inventory(package_root: Path, raw: Mapping[str, bytes]) -> None:
    inventory = load_canonical_json(package_root / "sha256_inventory.json")
    _schema(inventory, "sha256_inventory")
    require_bool(
        inventory.get("inventory_excludes_self"), True, "inventory self exclusion"
    )
    files = _mapping(inventory.get("files"), "inventory files")
    expected = set(INVENTORIED_FILES)
    # Package agent uses bare names.  Reject any omitted or unexpected entry.
    require_equal(set(files), expected, "inventory file names")
    for name in INVENTORIED_FILES:
        entry = _mapping(files.get(name), f"inventory {name}")
        require_equal(
            entry.get("sha256"), sha256_bytes(raw[name]), f"inventory {name} SHA-256"
        )
        require_equal(
            entry.get("byte_size"), len(raw[name]), f"inventory {name} byte size"
        )
    require_equal(
        inventory.get("file_count"), len(INVENTORIED_FILES), "inventory file_count"
    )


def validate(
    repository_root: Path, *, package_root: Path | None = None
) -> dict[str, Any]:
    """Validate an existing package without changing repository state."""

    repository_root = repository_root.resolve()
    package_root = (package_root or repository_root / PACKAGE_DIRECTORY).resolve()
    require(repository_root.is_dir(), "repository root missing")
    _reject_u4_path(package_root)
    _require_current_head_descends_from_starting_authority(repository_root)
    handoff = _validate_handoff(repository_root)
    evidence = _validate_evidence(repository_root)

    require(package_root.is_dir(), f"package root missing: {package_root}")
    files = list(package_root.iterdir())
    require(
        all(path.is_file() or path.is_symlink() for path in files),
        "package contains unexpected directory",
    )
    actual_names = {path.name for path in files if path.is_file() or path.is_symlink()}
    require_equal(actual_names, set(PACKAGE_FILES), "package file set")
    raw: dict[str, bytes] = {}
    docs: dict[str, dict[str, Any]] = {}
    for name in PACKAGE_FILES:
        path = package_root / name
        require(
            path.is_file() and not path.is_symlink(),
            f"package file missing or symlink: {name}",
        )
        _reject_u4_path(path)
        raw[name] = path.read_bytes()
        if name.endswith(".json"):
            docs[name] = load_strict_json(raw[name], str(path), canonical=True)
            _schema(docs[name], name)
    memo = raw["checkpoint_memo.md"].decode("utf-8")
    require(memo.endswith("\n"), "checkpoint memo final newline")
    memo_lower = memo.casefold()
    for phrase in (
        "yellow",
        "clean_negative_bounded_ten_pilot_linear_probe_study",
        "not u4",
        "not proof",
    ):
        require(
            phrase in memo_lower, f"checkpoint memo claim boundary missing: {phrase}"
        )
    require(
        "mvp complete" not in memo_lower and "u4 authorized" not in memo_lower,
        "checkpoint memo overclaim",
    )

    roadmap_result = _validate_roadmap(docs["roadmap_completion_matrix.json"])
    _validate_authority_binding(docs["authority_binding.json"], handoff)
    _validate_scope(docs["scope_shortfall.json"])
    _validate_checkpoint(docs["checkpoint_decision.json"])
    _validate_reproducibility(docs["reproducibility_status.json"])
    _validate_external_blockers(docs["external_blockers.json"])
    _validate_receipt(docs["validation_receipt.json"], roadmap_result)
    _validate_inventory(package_root, raw)
    return {
        "status": "PASS",
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "handoff_commit": HANDOFF_COMMIT,
        "handoff_manifest_sha256": HANDOFF_RAW_SHA256,
        "starting_person_b_commit": STARTING_HEAD,
        "repository_input_count": 12,
        "external_activation_index": {
            "sha256": EXTERNAL_ACTIVATION_SHA256,
            "byte_size": EXTERNAL_ACTIVATION_SIZE,
        },
        "step_count": roadmap_result["step_count"],
        "phase_count": roadmap_result["phase_count"],
        "positive_control_pass": evidence["positive_control_pass"],
        "step4_1_decision": evidence["step4_1_decision"],
        "qualifying_layer_bands": [],
        "validation_mode": "validation-only",
        "scientific_execution_performed": False,
        "u4_output_inspected": False,
    }


def validate_package(
    repository_root: Path, *, package_root: Path | None = None
) -> dict[str, Any]:
    """Explicit alias for callers using the CLI command name."""

    return validate(repository_root, package_root=package_root)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", nargs="?", choices=("validate-package",), default="validate-package"
    )
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[3]
    )
    parser.add_argument("--package-root", type=Path)
    parser.add_argument(
        "--json", action="store_true", help="emit JSON summary (the default)"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = validate(args.repository_root, package_root=args.package_root)
    except (CloseoutValidationError, OSError, UnicodeError) as error:
        print(f"PERSON_B_WEEK1_MVP_CLOSEOUT_VALIDATION=FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
