"""Validate Person B's Phase 3 Step 3.3 final analysis-readiness signoff.

This module is intentionally validation-only.  It reads the frozen Person B,
Person C, and Person E authorities, verifies their exact identities, and
checks Person C's already-produced ``visible_flag`` values.  It never runs a
detector, writes an authority package, or creates/replaces a visibility label.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_TOKEN = "person-b-phase3-step3-3-final-signoff-v0-1"
SIGNOFF_DIRECTORY = "person_b_phase3_step3_3_final_signoff_v0_1"
SIGNOFF_FILES = {
    "analysis_readiness_decision.json",
    "authority_binding.json",
    "coordinate_frame_validation.json",
    "detector_gate_validation.json",
    "homography_gate_validation.json",
    "joined_package_validation.json",
    "phase3_closure_recommendation.json",
    "quarantine_policy_validation.json",
    "sha256_inventory.json",
    "validation_receipt.json",
}
C_PACKAGE_DIRECTORY = "person_c_phase3_step3_3_joined_visibility_v0_1"
C_PACKAGE_FILES = {
    "authority_binding.json",
    "coverage_report.json",
    "joined_visibility_records.jsonl",
    "joined_visibility_schema.json",
    "phase3_status.json",
    "provenance_index.json",
    "quarantine_accounting_report.json",
    "sha256_inventory.json",
    "strict_join_receipt.json",
    "validation_receipt.json",
}

B_POLICY_COMMIT = "eec9396e6a93feaab3d5d298ac7cdc4cb54fdbd4"
B_OPERATIONAL_PARENT = "08b9677124f3ed04db49d5e5e720f04771c96b83"
B_HISTORICAL_AUTHORITY = "03a2c4663ce73873b4fed0369943c1f43edcd742"
A_AUTHORITY_COMMIT = "06b87fe1f43d2133c25db498fcc1fd234f958aad"
E_DETECTOR_FREEZE_COMMIT = "3930669eddc026ecb081e947f71f1855a7415904"
E_STEP_3_1_COMMIT = "ed3ca072b184ccb45dbf154d4209c5893b67f42e"
E_STEP_3_2_COMMIT = "bfe7d55acc1fcf0b90aca5c152672070b15e6ee7"
E_EMPIRICAL_COMMIT = "90855ea52b19ced3f0ce610f7d18db35070ee023"
C_JOINED_COMMIT = "bf09c23bb12f59acae724811eed6b82bab17c0ed"

COORDINATE_PATH = "src/mineocclude/analysis/coordinates.py"
COORDINATE_SHA256 = "19e3946e0b0385989b639187e0eda8ff4cc7712938fd87c6084fb9d2306af493"
COORDINATE_SCHEMA = "person-b-wall-parallel-frame-v0.1"
JOINED_RECORDS_SHA256 = (
    "e9bb71ae4ebb046297abf700f6fabb1813facdd691be9f02e0e730dfe79ad17e"
)
DETECTOR_IDENTITY = "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
DETECTOR_VERSION = (
    "hsv-largest-valid-blob-v1.0-candidate:"
    "sha256:0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
)
E_EMPIRICAL_RECORDS_SHA256 = (
    "b6da7d73e2eea0975469d59cb92a47aace90d1651c8e42cc22cfc40675d90681"
)
E_EMPIRICAL_INVENTORY_SHA256 = (
    "f21fd49e001aac9f35545721e5d0f357b8b635cd26d1fcb5ce9f5938b284fc52"
)
C_GEOMETRIC_RECORDS_SHA256 = (
    "914a5bee842c92e707b94c6d58c91807681310ac6a393d18a06ba8dfa70572eb"
)

B_POLICY_DIRECTORY = "docs/status/person_b_phase3_step3_3_policy_v0_1"
B_POLICY_HASHES = {
    "authority_binding.json": (
        "909a46563859575a34458a3460d0d3173a3181b883ddfdcb6f37ae371a907399"
    ),
    "phase3_status.json": (
        "f730643493ee533fdf19e4c71c035c705f23080fa20db151141b6eec3e66725f"
    ),
    "quarantine_accounting_policy.json": (
        "55ef47de149647127de510079d790e1fda6ed5b26cb11e0f72d792fadbb8e056"
    ),
    "validation_receipt.json": (
        "fb663cee6e252cebd87064dc56817e5ec391a93621ee0669a9a1b726705e3c83"
    ),
    "visibility_acceptance_policy.json": (
        "c745a2d20467d7719e60e3aac8f1d5c04b70a0bc2a3b6bdbb027a6a8e1f16222"
    ),
}

E_FORMAL_DIRECTORY = "docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1"
E_HOMOGRAPHY_DIRECTORY = "docs/status/person_e_phase3_step3_2_homography_closure_v0_1"
E_EMPIRICAL_DIRECTORY = (
    "data/handoff_c/person_e_phase3_step3_3_empirical_visibility_v0_1"
)
C_GEOMETRIC_PATH = (
    "data/handoff_e/phase3_visibility_authority_v0_1/geometric_visibility_records.jsonl"
)

PRIMARY_KEY = ("trajectory_id", "model_frame_idx")
ALLOWED_QUARANTINE_CATEGORIES = {
    "geometry_hidden_detector_visible",
    "geometry_visible_detector_hidden",
    "invalid_geometry",
    "missing_detector",
    "none",
}
ALLOWED_VISIBILITY_TRIPLES = {
    (False, False, False),
    (False, True, False),
    (True, False, False),
    (True, True, True),
}
EXPECTED_TOTALS = {
    "geometry_hidden_detector_visible": 364,
    "geometry_visible_detector_hidden": 53,
    "input_rows": 1850,
    "invalid_geometry": 0,
    "missing_detector": 0,
    "non_quarantined": 1433,
    "none": 1433,
    "quarantined": 417,
    "visible_flag_false": 749,
    "visible_flag_true": 1101,
}
EXPECTED_PER_LAYOUT = {
    "layout_01": {
        "geometry_hidden_detector_visible": 108,
        "geometry_visible_detector_hidden": 0,
        "input_rows": 375,
        "invalid_geometry": 0,
        "missing_detector": 0,
        "non_quarantined": 267,
        "none": 267,
        "quarantined": 108,
        "visible_flag_false": 176,
        "visible_flag_true": 199,
    },
    "layout_02": {
        "geometry_hidden_detector_visible": 25,
        "geometry_visible_detector_hidden": 2,
        "input_rows": 248,
        "invalid_geometry": 0,
        "missing_detector": 0,
        "non_quarantined": 221,
        "none": 221,
        "quarantined": 27,
        "visible_flag_false": 106,
        "visible_flag_true": 142,
    },
    "layout_03": {
        "geometry_hidden_detector_visible": 82,
        "geometry_visible_detector_hidden": 0,
        "input_rows": 154,
        "invalid_geometry": 0,
        "missing_detector": 0,
        "non_quarantined": 72,
        "none": 72,
        "quarantined": 82,
        "visible_flag_false": 104,
        "visible_flag_true": 50,
    },
    "layout_04": {
        "geometry_hidden_detector_visible": 67,
        "geometry_visible_detector_hidden": 0,
        "input_rows": 261,
        "invalid_geometry": 0,
        "missing_detector": 0,
        "non_quarantined": 194,
        "none": 194,
        "quarantined": 67,
        "visible_flag_false": 104,
        "visible_flag_true": 157,
    },
    "layout_05": {
        "geometry_hidden_detector_visible": 79,
        "geometry_visible_detector_hidden": 0,
        "input_rows": 381,
        "invalid_geometry": 0,
        "missing_detector": 0,
        "non_quarantined": 302,
        "none": 302,
        "quarantined": 79,
        "visible_flag_false": 104,
        "visible_flag_true": 277,
    },
    "layout_06": {
        "geometry_hidden_detector_visible": 3,
        "geometry_visible_detector_hidden": 51,
        "input_rows": 431,
        "invalid_geometry": 0,
        "missing_detector": 0,
        "non_quarantined": 377,
        "none": 377,
        "quarantined": 54,
        "visible_flag_false": 155,
        "visible_flag_true": 276,
    },
}


class SignoffValidationError(ValueError):
    """Raised when a frozen authority or signoff invariant fails."""


def require(condition: bool, message: str) -> None:
    """Fail closed with one stable validation exception."""

    if not condition:
        raise SignoffValidationError(message)


def require_equal(actual: Any, expected: Any, name: str) -> None:
    """Require exact equality and report both values on failure."""

    require(actual == expected, f"{name}: expected {expected!r}, got {actual!r}")


def sha256_bytes(payload: bytes) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file without changing it."""

    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(document: Any) -> bytes:
    """Serialize one signoff JSON document deterministically."""

    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_jsonl_line(document: Any) -> str:
    """Serialize one authority JSONL row deterministically."""

    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def load_json_bytes(payload: bytes, name: str) -> dict[str, Any]:
    """Decode and parse one UTF-8 JSON object, rejecting BOMs and non-objects."""

    require(not payload.startswith(b"\xef\xbb\xbf"), f"{name}: UTF-8 BOM forbidden")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SignoffValidationError(f"{name}: invalid UTF-8") from error
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise SignoffValidationError(f"{name}: invalid JSON") from error
    require(isinstance(document, dict), f"{name}: root must be an object")
    return document


def load_json_file(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""

    require(path.is_file(), f"Missing JSON document: {path}")
    return load_json_bytes(path.read_bytes(), str(path))


def load_jsonl_bytes(
    payload: bytes,
    name: str,
    *,
    require_canonical: bool = True,
) -> list[dict[str, Any]]:
    """Parse deterministic UTF-8 JSONL without accepting blank rows."""

    require(not payload.startswith(b"\xef\xbb\xbf"), f"{name}: UTF-8 BOM forbidden")
    require(payload.endswith(b"\n"), f"{name}: final newline required")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SignoffValidationError(f"{name}: invalid UTF-8") from error
    lines = text.splitlines()
    require(lines, f"{name}: at least one row required")
    require(all(line for line in lines), f"{name}: blank JSONL row forbidden")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise SignoffValidationError(f"{name}:{index}: invalid JSON") from error
        require(isinstance(row, dict), f"{name}:{index}: row must be an object")
        if require_canonical:
            require_equal(
                line,
                canonical_jsonl_line(row),
                f"{name}:{index}: deterministic serialization",
            )
        rows.append(row)
    return rows


def _git(
    repository_root: Path,
    *arguments: str,
    text: bool = False,
) -> bytes | str:
    result = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() if text else result.stderr.decode().strip()
        raise SignoffValidationError(f"git {' '.join(arguments)} failed: {stderr}")
    return result.stdout


def git_file_bytes(repository_root: Path, commit: str, path: str) -> bytes:
    """Read exact committed bytes without checking out or mutating the commit."""

    payload = _git(repository_root, "show", f"{commit}:{path}")
    require(isinstance(payload, bytes), "Internal git byte-mode failure")
    return payload


def git_json(repository_root: Path, commit: str, path: str) -> dict[str, Any]:
    """Read one committed JSON object."""

    return load_json_bytes(
        git_file_bytes(repository_root, commit, path),
        f"{commit}:{path}",
    )


def git_jsonl(repository_root: Path, commit: str, path: str) -> list[dict[str, Any]]:
    """Read one committed deterministic JSONL file."""

    return load_jsonl_bytes(
        git_file_bytes(repository_root, commit, path),
        f"{commit}:{path}",
    )


def validate_commit(repository_root: Path, commit: str, name: str) -> None:
    """Require an exact Git object to be a commit."""

    object_type = _git(repository_root, "cat-file", "-t", commit, text=True)
    require(isinstance(object_type, str), "Internal git text-mode failure")
    require_equal(object_type.strip(), "commit", f"{name} object type")


def reject_u4_path(path: Path) -> None:
    """Reject any input path that could expose a U4 artifact."""

    normalized = path.as_posix().casefold()
    require("u4" not in normalized, f"U4 path is prohibited: {path}")


def validate_pretty_json(path: Path) -> dict[str, Any]:
    """Require canonical sorted, two-space, newline-terminated JSON."""

    payload = path.read_bytes()
    document = load_json_bytes(payload, str(path))
    require_equal(payload, canonical_json_bytes(document), f"{path}: serialization")
    return document


def validate_inventory(
    root: Path,
    *,
    expected_files: set[str],
    count_field: str,
) -> dict[str, Any]:
    """Validate a self-excluding SHA-256 inventory and exact package scope."""

    require(root.is_dir(), f"Package root missing: {root}")
    actual_files = {path.name for path in root.iterdir() if path.is_file()}
    require_equal(actual_files, expected_files, f"{root}: file inventory")
    inventory = validate_pretty_json(root / "sha256_inventory.json")
    require_equal(
        inventory.get(count_field),
        len(expected_files),
        f"{root}: declared file count",
    )
    declared = inventory.get("files")
    require(isinstance(declared, dict), f"{root}: files inventory must be an object")
    require_equal(
        set(declared),
        expected_files - {"sha256_inventory.json"},
        f"{root}: hashed file names",
    )
    for name, expected_hash in declared.items():
        require_equal(
            sha256_file(root / name),
            expected_hash,
            f"{root / name}: SHA-256",
        )
    return inventory


def validate_git_inventory(
    repository_root: Path,
    *,
    commit: str,
    directory: str,
    count_field: str,
) -> dict[str, Any]:
    """Validate one exact committed package inventory without checkout."""

    inventory_path = f"{directory}/sha256_inventory.json"
    inventory = git_json(repository_root, commit, inventory_path)
    declared = inventory.get("files")
    require(
        isinstance(declared, dict),
        f"{commit}:{inventory_path}: files must be an object",
    )
    output = _git(
        repository_root,
        "ls-tree",
        "-r",
        "--name-only",
        commit,
        "--",
        f"{directory}/",
        text=True,
    )
    require(isinstance(output, str), "Internal git text-mode failure")
    paths = [line for line in output.splitlines() if line]
    require_equal(
        len(paths),
        inventory.get(count_field),
        f"{commit}:{directory}: package file count",
    )
    require_equal(
        {Path(path).name for path in paths},
        set(declared) | {"sha256_inventory.json"},
        f"{commit}:{directory}: package paths",
    )
    for name, expected_hash in declared.items():
        require_equal(
            sha256_bytes(
                git_file_bytes(repository_root, commit, f"{directory}/{name}")
            ),
            expected_hash,
            f"{commit}:{directory}/{name}: SHA-256",
        )
    return inventory


def validate_authority_commits(repository_root: Path) -> dict[str, str]:
    """Validate all explicitly bound authorities and B's exact parent."""

    commits = {
        "person_a_model_preprocessing": A_AUTHORITY_COMMIT,
        "person_b_historical": B_HISTORICAL_AUTHORITY,
        "person_b_operational_parent": B_OPERATIONAL_PARENT,
        "person_b_step3_3_policy": B_POLICY_COMMIT,
        "person_c_joined_visibility": C_JOINED_COMMIT,
        "person_e_detector_freeze": E_DETECTOR_FREEZE_COMMIT,
        "person_e_empirical_visibility": E_EMPIRICAL_COMMIT,
        "person_e_step_3_1": E_STEP_3_1_COMMIT,
        "person_e_step_3_2": E_STEP_3_2_COMMIT,
    }
    for name, commit in commits.items():
        validate_commit(repository_root, commit, name)

    header = _git(
        repository_root,
        "show",
        "-s",
        "--format=%H%n%P%n%s",
        B_POLICY_COMMIT,
        text=True,
    )
    require(isinstance(header, str), "Internal git text-mode failure")
    lines = header.rstrip("\n").splitlines()
    require_equal(
        lines,
        [
            B_POLICY_COMMIT,
            B_OPERATIONAL_PARENT,
            "Define Person B Phase 3 Step 3.3 acceptance policy",
        ],
        "Person B policy commit identity",
    )
    return commits


def validate_b_policy(repository_root: Path) -> dict[str, Any]:
    """Validate the exact predeclared Person B Step 3.3 policy."""

    documents: dict[str, dict[str, Any]] = {}
    actual_hashes: dict[str, str] = {}
    for name, expected_hash in B_POLICY_HASHES.items():
        path = f"{B_POLICY_DIRECTORY}/{name}"
        payload = git_file_bytes(repository_root, B_POLICY_COMMIT, path)
        actual_hash = sha256_bytes(payload)
        require_equal(actual_hash, expected_hash, f"{path}: SHA-256")
        actual_hashes[name] = actual_hash
        documents[name] = load_json_bytes(payload, f"{B_POLICY_COMMIT}:{path}")

    visibility = documents["visibility_acceptance_policy.json"]
    require_equal(
        visibility.get("authoritative_join_key"),
        list(PRIMARY_KEY),
        "B policy authoritative join key",
    )
    require_equal(
        visibility.get("final_label_equation"),
        "visible_flag = geometric_visible AND empirical_magenta_visible",
        "B policy final label rule",
    )
    preservation = visibility.get("channel_preservation")
    require(isinstance(preservation, dict), "B channel preservation missing")
    require_equal(
        preservation.get("person_b_may_recompute_or_overwrite_visible_flag"),
        False,
        "B visible_flag recomputation permission",
    )
    require_equal(
        preservation.get("person_e_may_supply_or_overwrite_visible_flag"),
        False,
        "E visible_flag permission",
    )
    ownership = visibility.get("ownership")
    require(isinstance(ownership, dict), "B policy ownership missing")
    require_equal(ownership.get("policy_owner"), "person_b", "policy owner")
    require_equal(
        ownership.get("final_label_owner"),
        "person_c",
        "final label owner",
    )
    require_equal(
        ownership.get("empirical_channel_owner"),
        "person_e",
        "empirical channel owner",
    )
    require_equal(
        ownership.get("model_preprocessing_provenance_owner"),
        "person_a",
        "model/preprocessing provenance owner",
    )

    quarantine = documents["quarantine_accounting_policy.json"]
    require_equal(
        set(quarantine.get("authoritative_categories", [])),
        ALLOWED_QUARANTINE_CATEGORIES,
        "B policy quarantine categories",
    )
    status = documents["phase3_status.json"]
    require_equal(
        status.get("step_3_3_person_b_policy_authority"),
        "READY",
        "B Step 3.3 policy status",
    )
    require_equal(
        status.get("step_3_3_empirical_integration"),
        "PENDING",
        "pre-signoff empirical integration status",
    )
    require_equal(
        status.get("u4_output_inspected"),
        False,
        "B policy U4 status",
    )
    return {"documents": documents, "hashes": actual_hashes}


def validate_detector_gate(
    report: Mapping[str, Any],
    run_receipt: Mapping[str, Any],
    status: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate only the frozen Step 3.1 formal-gate metrics."""

    thresholds = report.get("formal_thresholds")
    metrics = report.get("metrics")
    require(isinstance(thresholds, Mapping), "Step 3.1 thresholds missing")
    require(isinstance(metrics, Mapping), "Step 3.1 metrics missing")
    precision = metrics.get("precision")
    recall = metrics.get("recall")
    require(isinstance(precision, Mapping), "Step 3.1 precision missing")
    require(isinstance(recall, Mapping), "Step 3.1 recall missing")

    minimum_precision = thresholds.get("minimum_precision")
    minimum_recall = thresholds.get("minimum_recall")
    precision_value = precision.get("decimal")
    recall_value = recall.get("decimal")
    require_equal(minimum_precision, 0.95, "Step 3.1 minimum precision")
    require_equal(minimum_recall, 0.95, "Step 3.1 minimum recall")
    require_equal(precision_value, 1.0, "Step 3.1 frozen precision")
    require_equal(recall_value, 1.0, "Step 3.1 frozen recall")
    require(
        precision_value >= minimum_precision,
        "Step 3.1 precision threshold failed",
    )
    require(recall_value >= minimum_recall, "Step 3.1 recall threshold failed")
    require_equal(metrics.get("true_positive"), 24, "Step 3.1 TP")
    require_equal(metrics.get("false_positive"), 0, "Step 3.1 FP")
    require_equal(metrics.get("true_negative"), 24, "Step 3.1 TN")
    require_equal(metrics.get("false_negative"), 0, "Step 3.1 FN")
    require_equal(report.get("formal_gate_passed"), True, "Step 3.1 gate")
    require_equal(report.get("formal_run_ordinal"), 1, "formal run ordinal")
    require_equal(
        report.get("second_formal_run_occurred"),
        False,
        "second formal run",
    )
    require_equal(
        report.get("detector_tuned_after_result"),
        False,
        "post-result tuning",
    )
    require_equal(report.get("u4_output_inspected"), False, "Step 3.1 U4 status")
    require_equal(run_receipt.get("formal_run_count"), 1, "formal run count")
    require_equal(
        run_receipt.get("second_formal_run_occurred"),
        False,
        "formal receipt second run",
    )
    require_equal(
        run_receipt.get("detector_tuned_after_result"),
        False,
        "formal receipt tuning",
    )
    require_equal(status.get("step_3_1_status"), "PASS", "Step 3.1 status")
    return {
        "false_negative": 0,
        "false_positive": 0,
        "minimum_precision": 0.95,
        "minimum_recall": 0.95,
        "precision": 1.0,
        "recall": 1.0,
        "status": "PASS",
        "true_negative": 24,
        "true_positive": 24,
    }


def validate_homography_gate(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the frozen Step 3.2 numeric and process gates."""

    median = report.get("median_absolute_wall_parallel_error_blocks")
    p95 = report.get("p95_absolute_wall_parallel_error_blocks")
    median_limit = report.get("median_threshold_maximum_blocks")
    p95_limit = report.get("p95_threshold_exclusive_maximum_blocks")
    for name, value in {
        "median": median,
        "p95": p95,
        "median limit": median_limit,
        "p95 limit": p95_limit,
    }.items():
        require(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value),
            f"Step 3.2 {name} must be finite",
        )
    require_equal(median, 0.09341800000000022, "Step 3.2 median")
    require_equal(p95, 0.28720401897341596, "Step 3.2 p95")
    require_equal(median_limit, 0.20, "Step 3.2 median threshold")
    require_equal(p95_limit, 0.50, "Step 3.2 p95 threshold")
    require(median <= median_limit, "Step 3.2 median threshold failed")
    require(p95 < p95_limit, "Step 3.2 strict p95 threshold failed")
    require_equal(report.get("homography_count"), 6, "homography count")
    require_equal(
        report.get("distinct_homography_identity_count"),
        6,
        "distinct homography count",
    )
    require_equal(report.get("localization_probe_count"), 36, "probe count")
    require_equal(report.get("excluded_layout_ids"), [], "excluded layouts")
    require_equal(
        report.get("probe_filtering_applied"),
        False,
        "probe filtering",
    )
    require_equal(
        report.get("probe_derived_tuning_applied"),
        False,
        "probe-derived tuning",
    )
    applicability = report.get("applicability_validation")
    require(isinstance(applicability, Mapping), "applicability validation missing")
    require_equal(
        applicability.get("exact_context_passed"),
        True,
        "exact applicability",
    )
    mismatch = applicability.get("individual_mismatch_fail_closed")
    require(isinstance(mismatch, Mapping), "mismatch tests missing")
    require_equal(len(mismatch), 6, "applicability mismatch count")
    require(all(value is True for value in mismatch.values()), "mismatch not closed")
    require_equal(report.get("numeric_gate_passed"), True, "numeric gate")
    require_equal(report.get("status"), "PASS", "Step 3.2 status")
    require_equal(report.get("u4_output_inspected"), False, "Step 3.2 U4 status")
    return {
        "applicability_fails_closed": True,
        "homography_count": 6,
        "median_error_blocks": median,
        "median_threshold_blocks": median_limit,
        "p95_error_blocks": p95,
        "p95_threshold_exclusive_blocks": p95_limit,
        "probe_count": 36,
        "status": "PASS",
    }


def validate_coordinate_authority(
    source: bytes,
    c_authority: Mapping[str, Any],
    c_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the exact signed wall-parallel coordinate authority."""

    require_equal(
        sha256_bytes(source),
        COORDINATE_SHA256,
        "coordinate implementation SHA-256",
    )
    try:
        source_text = source.decode("utf-8")
        tree = ast.parse(source_text)
    except (UnicodeDecodeError, SyntaxError) as error:
        raise SignoffValidationError("coordinate implementation is invalid") from error

    schema_assignments = [
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "COORDINATE_FRAME_SCHEMA_VERSION"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    require_equal(
        schema_assignments,
        [COORDINATE_SCHEMA],
        "coordinate schema declaration",
    )
    project_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "project"
    ]
    require_equal(len(project_functions), 1, "signed project implementation count")
    project = project_functions[0]
    require(
        any(isinstance(node, ast.Sub) for node in ast.walk(project)),
        "signed origin subtraction missing",
    )
    require(
        any(isinstance(node, ast.Mult) for node in ast.walk(project)),
        "signed direction projection missing",
    )
    required_literals = {
        "wall_parallel_origin_world_xyz",
        "wall_parallel_positive_unit_vector_world_xyz",
        "wall_parallel_position_blocks",
    }
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    require(
        required_literals <= literals,
        "coordinate origin, positive direction, or block-unit field missing",
    )
    require(
        "math.isclose(norm, 1.0" in source_text,
        "unit positive direction check missing",
    )

    coordinate = c_authority.get("person_b_coordinate_authority")
    require(isinstance(coordinate, Mapping), "C coordinate authority missing")
    require_equal(coordinate.get("path"), COORDINATE_PATH, "coordinate path")
    require_equal(coordinate.get("sha256"), COORDINATE_SHA256, "C coordinate SHA")
    require_equal(coordinate.get("schema"), COORDINATE_SCHEMA, "C coordinate schema")
    signoff = coordinate.get("required_signoff")
    require(isinstance(signoff, Mapping), "C coordinate signoff missing")
    require_equal(signoff.get("person_b"), True, "Person B coordinate signoff")
    require_equal(signoff.get("person_c"), True, "Person C coordinate signoff")

    provenance_coordinate = (
        c_provenance.get("authorities", {}).get("person_b_coordinate_frame")
        if isinstance(c_provenance.get("authorities"), Mapping)
        else None
    )
    require(
        isinstance(provenance_coordinate, Mapping),
        "C provenance coordinate authority missing",
    )
    require_equal(
        provenance_coordinate.get("sha256"),
        COORDINATE_SHA256,
        "C provenance coordinate SHA",
    )
    require_equal(
        provenance_coordinate.get("schema"),
        COORDINATE_SCHEMA,
        "C provenance coordinate schema",
    )
    provenance_signoff = provenance_coordinate.get("signoff")
    require(
        isinstance(provenance_signoff, Mapping),
        "C provenance coordinate signoff missing",
    )
    require_equal(
        provenance_signoff.get("person_b"),
        True,
        "C provenance B signoff",
    )
    require_equal(
        provenance_signoff.get("person_c"),
        True,
        "C provenance C signoff",
    )

    person_a = c_authority.get("person_a_model_preprocessing_authority")
    require(isinstance(person_a, Mapping), "Person A ownership record missing")
    require_equal(
        person_a.get("owns"),
        "model and preprocessing provenance only",
        "Person A ownership scope",
    )
    does_not_own = person_a.get("does_not_own")
    require(isinstance(does_not_own, Sequence), "Person A exclusions missing")
    require(
        "wall_parallel_coordinate_frame" in does_not_own,
        "Person A coordinate-ownership exclusion missing",
    )
    return {
        "origin_field": "wall_parallel_origin_world_xyz",
        "person_a_owns_coordinate_frame": False,
        "person_b_signoff": True,
        "person_c_signoff": True,
        "positive_axis_field": ("wall_parallel_positive_unit_vector_world_xyz"),
        "schema": COORDINATE_SCHEMA,
        "sha256": COORDINATE_SHA256,
        "signed_projection": True,
        "status": "PASS",
        "unit_positive_direction_required": True,
        "units": "blocks",
    }


def _row_key(row: Mapping[str, Any], name: str) -> tuple[str, int]:
    trajectory_id = row.get("trajectory_id")
    model_frame_idx = row.get("model_frame_idx")
    require(
        isinstance(trajectory_id, str) and bool(trajectory_id),
        f"{name}: trajectory_id must be non-empty",
    )
    require(
        isinstance(model_frame_idx, int)
        and not isinstance(model_frame_idx, bool)
        and model_frame_idx >= 0,
        f"{name}: model_frame_idx must be a nonnegative integer",
    )
    return trajectory_id, model_frame_idx


def index_rows(
    rows: Iterable[Mapping[str, Any]],
    name: str,
) -> dict[tuple[str, int], Mapping[str, Any]]:
    """Index rows by the frozen key and reject duplicates."""

    indexed: dict[tuple[str, int], Mapping[str, Any]] = {}
    for row_index, row in enumerate(rows):
        require(isinstance(row, Mapping), f"{name}[{row_index}]: object required")
        key = _row_key(row, f"{name}[{row_index}]")
        require(key not in indexed, f"{name}: duplicate primary key {key!r}")
        indexed[key] = row
    return indexed


def summarize_joined_rows(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate row-level final-rule and quarantine invariants.

    The allowed truth-table triples validate Person C's existing final label
    without assigning or emitting any replacement ``visible_flag`` value.
    """

    indexed = index_rows(rows, "joined rows")
    keys = list(indexed)
    require_equal(keys, sorted(keys), "joined deterministic primary-key order")

    category_counts: Counter[str] = Counter()
    per_layout: dict[str, Counter[str]] = defaultdict(Counter)
    visible_true = 0
    quarantined_count = 0
    for row_index, row in enumerate(rows):
        prefix = f"joined rows[{row_index}]"
        geometric = row.get("geometric_visible")
        empirical = row.get("empirical_magenta_visible")
        final_label = row.get("visible_flag")
        require(type(geometric) is bool, f"{prefix}: geometric channel invalid")
        require(type(empirical) is bool, f"{prefix}: empirical channel invalid")
        require(type(final_label) is bool, f"{prefix}: visible_flag invalid")
        require(
            (geometric, empirical, final_label) in ALLOWED_VISIBILITY_TRIPLES,
            f"{prefix}: final AND rule violated",
        )
        require_equal(row.get("label_owner"), "Person C", f"{prefix}: label owner")
        require_equal(
            row.get("detector_version"),
            DETECTOR_VERSION,
            f"{prefix}: detector version",
        )

        category = row.get("quarantine_category")
        quarantined = row.get("quarantined")
        layout_id = row.get("layout_id")
        require(
            category in ALLOWED_QUARANTINE_CATEGORIES,
            f"{prefix}: invalid quarantine category {category!r}",
        )
        require(type(quarantined) is bool, f"{prefix}: quarantined must be boolean")
        require(
            isinstance(layout_id, str) and bool(layout_id),
            f"{prefix}: layout_id must be non-empty",
        )
        require_equal(
            quarantined,
            category != "none",
            f"{prefix}: quarantine/category relationship",
        )
        if quarantined:
            require(final_label is False, f"{prefix}: quarantined row is visible")
            quarantined_count += 1
        if final_label:
            require_equal(category, "none", f"{prefix}: visible-row category")
            visible_true += 1

        category_counts[category] += 1
        layout = per_layout[layout_id]
        layout["input_rows"] += 1
        layout[category] += 1
        layout["quarantined" if quarantined else "non_quarantined"] += 1
        layout["visible_flag_true" if final_label else "visible_flag_false"] += 1

    total = {
        **{
            category: category_counts.get(category, 0)
            for category in sorted(ALLOWED_QUARANTINE_CATEGORIES)
        },
        "input_rows": len(rows),
        "non_quarantined": len(rows) - quarantined_count,
        "quarantined": quarantined_count,
        "visible_flag_false": len(rows) - visible_true,
        "visible_flag_true": visible_true,
    }
    per_layout_normalized = {
        layout_id: {
            category: counts.get(category, 0)
            for category in sorted(
                ALLOWED_QUARANTINE_CATEGORIES
                | {
                    "input_rows",
                    "non_quarantined",
                    "quarantined",
                    "visible_flag_false",
                    "visible_flag_true",
                }
            )
        }
        for layout_id, counts in sorted(per_layout.items())
    }
    return {
        "final_and_rule_exact": True,
        "per_layout": per_layout_normalized,
        "primary_keys": keys,
        "raw_channels_preserved_as_distinct_fields": True,
        "total": total,
        "unique_primary_keys": len(indexed),
    }


def validate_expected_accounting(summary: Mapping[str, Any]) -> None:
    """Require exact global and per-layout production accounting."""

    require_equal(summary.get("total"), EXPECTED_TOTALS, "global accounting")
    require_equal(
        summary.get("per_layout"),
        EXPECTED_PER_LAYOUT,
        "per-layout accounting",
    )
    require_equal(
        summary.get("unique_primary_keys"),
        EXPECTED_TOTALS["input_rows"],
        "unique primary-key count",
    )


def validate_source_channel_preservation(
    joined_rows: Sequence[Mapping[str, Any]],
    geometric_rows: Sequence[Mapping[str, Any]],
    empirical_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Require raw C and E channels to be byte-authority-equivalent by key."""

    joined = index_rows(joined_rows, "joined source comparison")
    geometric = index_rows(geometric_rows, "geometric source")
    empirical = index_rows(empirical_rows, "empirical source")
    require_equal(set(joined), set(geometric), "joined/geometric key set")
    require_equal(set(joined), set(empirical), "joined/empirical key set")
    for key, row in joined.items():
        c_row = geometric[key]
        e_row = empirical[key]
        require_equal(
            row.get("geometric_visible"),
            c_row.get("geometric_visible"),
            f"{key}: geometric channel preservation",
        )
        require_equal(
            row.get("empirical_magenta_visible"),
            e_row.get("empirical_magenta_visible"),
            f"{key}: empirical channel preservation",
        )
        for field in (
            "layout_id",
            "canonical_camera_pose_id",
        ):
            require_equal(
                row.get(field),
                c_row.get(field),
                f"{key}: C context {field}",
            )
            require_equal(
                row.get(field),
                e_row.get(field),
                f"{key}: E context {field}",
            )
        for field in ("resolution", "coordinate_convention", "detector_version"):
            require_equal(
                row.get(field),
                e_row.get(field),
                f"{key}: E context {field}",
            )
        require(
            "visible_flag" not in e_row,
            f"{key}: Person E supplied visible_flag",
        )


def validate_c_package(
    repository_root: Path,
    c_package_root: Path,
) -> dict[str, Any]:
    """Validate Person C's detached joined package and every joined row."""

    reject_u4_path(c_package_root)
    require(c_package_root.is_dir(), f"C package root missing: {c_package_root}")
    c_repository = Path(
        str(
            _git(
                c_package_root,
                "rev-parse",
                "--show-toplevel",
                text=True,
            )
        ).strip()
    ).resolve()
    c_head = str(_git(c_repository, "rev-parse", "HEAD", text=True)).strip()
    require_equal(c_head, C_JOINED_COMMIT, "detached Person C HEAD")
    require_equal(
        str(_git(c_repository, "status", "--porcelain", text=True)).strip(),
        "",
        "detached Person C worktree status",
    )
    expected_root = (
        c_repository / "data" / "handoff_b" / C_PACKAGE_DIRECTORY
    ).resolve()
    require_equal(
        c_package_root.resolve(),
        expected_root,
        "detached Person C package path",
    )

    validate_inventory(
        c_package_root,
        expected_files=C_PACKAGE_FILES,
        count_field="file_count",
    )
    documents = {
        name: validate_pretty_json(c_package_root / name)
        for name in sorted(C_PACKAGE_FILES)
        if name.endswith(".json")
    }
    records_path = c_package_root / "joined_visibility_records.jsonl"
    require_equal(
        sha256_file(records_path),
        JOINED_RECORDS_SHA256,
        "joined records SHA-256",
    )
    joined_rows = load_jsonl_bytes(records_path.read_bytes(), str(records_path))
    summary = summarize_joined_rows(joined_rows)
    validate_expected_accounting(summary)

    coverage = documents["coverage_report.json"]
    require_equal(coverage.get("expected_c_rows"), 1850, "expected C rows")
    require_equal(coverage.get("expected_e_rows"), 1850, "expected E rows")
    require_equal(coverage.get("produced_joined_rows"), 1850, "joined rows")
    require_equal(coverage.get("unique_joined_keys"), 1850, "joined keys")
    for field in (
        "context_mismatches",
        "detector_version_mismatches",
        "duplicate_c_keys",
        "duplicate_e_keys",
        "extra_e_keys",
        "malformed_empirical_values",
        "missing_e_keys",
    ):
        require_equal(coverage.get(field), 0, f"C coverage {field}")
    for field in (
        "diagnostic_e_key_set_equality",
        "joined_c_key_set_equality",
        "joined_e_key_set_equality",
    ):
        require_equal(coverage.get(field), True, f"C coverage {field}")

    schema = documents["joined_visibility_schema.json"]
    require_equal(schema.get("primary_key"), list(PRIMARY_KEY), "C primary key")
    require_equal(schema.get("final_label_owner"), "Person C", "C label owner")
    require_equal(
        schema.get("person_e_may_write_visible_flag"),
        False,
        "C E-label permission",
    )
    require_equal(
        schema.get("final_rule"),
        "visible_flag = geometric_visible AND empirical_magenta_visible",
        "C final rule",
    )
    require_equal(
        set(schema.get("quarantine_category_enum", [])),
        ALLOWED_QUARANTINE_CATEGORIES,
        "C quarantine categories",
    )

    report = documents["quarantine_accounting_report.json"]
    require_equal(report.get("total"), EXPECTED_TOTALS, "C reported totals")
    require_equal(
        report.get("per_layout"),
        EXPECTED_PER_LAYOUT,
        "C reported per-layout accounting",
    )
    receipt = documents["validation_receipt.json"]
    for field in (
        "and_rule_validated",
        "c_e_joined_key_set_equality",
        "deterministic_serialization",
        "no_accuracy_metrics",
        "no_detector_execution",
        "no_u4_inspection",
        "per_layout_accounting_reconciles",
        "quarantine_accounting_reconciles",
        "quarantine_invariants_hold",
        "raw_empirical_channel_preserved",
        "raw_geometric_channel_preserved",
        "zero_structural_failures",
    ):
        require_equal(receipt.get(field), True, f"C receipt {field}")
    phase = documents["phase3_status.json"]
    require_equal(
        phase.get("person_c_final_strict_join"),
        "READY",
        "C strict join status",
    )
    require_equal(phase.get("u4_output_inspected"), False, "C U4 status")

    geometric_payload = git_file_bytes(
        repository_root,
        C_JOINED_COMMIT,
        C_GEOMETRIC_PATH,
    )
    empirical_path = f"{E_EMPIRICAL_DIRECTORY}/empirical_visibility_records.jsonl"
    empirical_payload = git_file_bytes(
        repository_root,
        E_EMPIRICAL_COMMIT,
        empirical_path,
    )
    require_equal(
        sha256_bytes(geometric_payload),
        C_GEOMETRIC_RECORDS_SHA256,
        "C geometric records SHA-256",
    )
    require_equal(
        sha256_bytes(empirical_payload),
        E_EMPIRICAL_RECORDS_SHA256,
        "E empirical records SHA-256",
    )
    geometric_rows = load_jsonl_bytes(
        geometric_payload,
        f"{C_JOINED_COMMIT}:{C_GEOMETRIC_PATH}",
        require_canonical=False,
    )
    empirical_rows = load_jsonl_bytes(
        empirical_payload,
        f"{E_EMPIRICAL_COMMIT}:{empirical_path}",
    )
    validate_source_channel_preservation(
        joined_rows,
        geometric_rows,
        empirical_rows,
    )
    require_equal(
        str(_git(c_repository, "status", "--porcelain", text=True)).strip(),
        "",
        "detached Person C worktree status after validation",
    )
    return {
        "documents": documents,
        "joined_records_sha256": JOINED_RECORDS_SHA256,
        "summary": summary,
    }


def _forbidden_metric_key(key: str) -> bool:
    normalized = key.casefold()
    return normalized in {
        "accuracy",
        "accuracy_metrics",
        "false_negative",
        "false_positive",
        "precision",
        "recall",
        "true_negative",
        "true_positive",
    }


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield str(key)
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


def validate_no_production_accuracy_metrics(
    documents: Sequence[Mapping[str, Any]],
) -> None:
    """Reject detector-accuracy metrics in production authority documents."""

    for document in documents:
        forbidden = [key for key in _walk_keys(document) if _forbidden_metric_key(key)]
        require(
            not forbidden,
            "Production package contains forbidden accuracy metric keys: "
            + ", ".join(sorted(set(forbidden))),
        )


def validate_e_empirical_authority(repository_root: Path) -> dict[str, Any]:
    """Validate E's one-run production channel without deriving accuracy."""

    validate_git_inventory(
        repository_root,
        commit=E_EMPIRICAL_COMMIT,
        directory=E_EMPIRICAL_DIRECTORY,
        count_field="package_file_count",
    )
    inventory_path = f"{E_EMPIRICAL_DIRECTORY}/sha256_inventory.json"
    require_equal(
        sha256_bytes(
            git_file_bytes(
                repository_root,
                E_EMPIRICAL_COMMIT,
                inventory_path,
            )
        ),
        E_EMPIRICAL_INVENTORY_SHA256,
        "E empirical inventory SHA-256",
    )
    empirical_path = f"{E_EMPIRICAL_DIRECTORY}/empirical_visibility_records.jsonl"
    require_equal(
        sha256_bytes(
            git_file_bytes(
                repository_root,
                E_EMPIRICAL_COMMIT,
                empirical_path,
            )
        ),
        E_EMPIRICAL_RECORDS_SHA256,
        "E empirical records SHA-256",
    )
    rows = git_jsonl(
        repository_root,
        E_EMPIRICAL_COMMIT,
        empirical_path,
    )
    require_equal(len(rows), 1850, "E empirical row count")
    require_equal(len(index_rows(rows, "E empirical rows")), 1850, "E unique keys")
    for index, row in enumerate(rows):
        require_equal(
            row.get("detector_version"),
            DETECTOR_VERSION,
            f"E empirical rows[{index}]: detector version",
        )
        require(
            type(row.get("empirical_magenta_visible")) is bool,
            f"E empirical rows[{index}]: empirical value invalid",
        )
        require(
            "visible_flag" not in row,
            f"E empirical rows[{index}]: visible_flag forbidden",
        )
        require(
            "geometric_visible" not in row,
            f"E empirical rows[{index}]: geometric channel forbidden",
        )
    diagnostics_path = f"{E_EMPIRICAL_DIRECTORY}/detector_diagnostics.jsonl"
    diagnostics = git_jsonl(
        repository_root,
        E_EMPIRICAL_COMMIT,
        diagnostics_path,
    )
    require_equal(len(diagnostics), 1850, "E diagnostic row count")
    require_equal(
        len(index_rows(diagnostics, "E diagnostic rows")),
        1850,
        "E diagnostic unique keys",
    )
    for schema_name in (
        "detector_diagnostics_schema.json",
        "empirical_visibility_schema.json",
    ):
        git_json(
            repository_root,
            E_EMPIRICAL_COMMIT,
            f"{E_EMPIRICAL_DIRECTORY}/{schema_name}",
        )

    authority = git_json(
        repository_root,
        E_EMPIRICAL_COMMIT,
        f"{E_EMPIRICAL_DIRECTORY}/authority_binding.json",
    )
    require_equal(
        authority.get("person_b_policy_commit"),
        B_POLICY_COMMIT,
        "E B-policy binding",
    )
    detector = authority.get("detector")
    require(isinstance(detector, Mapping), "E detector authority missing")
    require_equal(
        detector.get("freeze_commit"),
        E_DETECTOR_FREEZE_COMMIT,
        "E detector freeze commit",
    )
    require_equal(
        detector.get("identity_sha256"),
        DETECTOR_IDENTITY,
        "E detector identity",
    )
    require_equal(
        detector.get("version"),
        DETECTOR_VERSION,
        "E detector version",
    )
    require_equal(
        authority.get("step_3_1_commit"),
        E_STEP_3_1_COMMIT,
        "E Step 3.1 binding",
    )
    require_equal(
        authority.get("step_3_2_commit"),
        E_STEP_3_2_COMMIT,
        "E Step 3.2 binding",
    )

    receipt = git_json(
        repository_root,
        E_EMPIRICAL_COMMIT,
        f"{E_EMPIRICAL_DIRECTORY}/production_run_receipt.json",
    )
    require_equal(receipt.get("completed_count"), 1850, "E completed count")
    require_equal(
        receipt.get("formal_production_ordinal"),
        1,
        "E production ordinal",
    )
    require_equal(
        receipt.get("formal_production_run_count"),
        1,
        "E production run count",
    )
    for field in (
        "detector_config_changed_after_start",
        "detector_implementation_changed_after_start",
        "geometric_visible_opened",
        "second_production_pass_occurred",
        "tuning_after_start",
        "u4_output_inspected",
        "visible_flag_computed",
    ):
        require_equal(receipt.get(field), False, f"E production {field}")

    validation = git_json(
        repository_root,
        E_EMPIRICAL_COMMIT,
        f"{E_EMPIRICAL_DIRECTORY}/validation_receipt.json",
    )
    require_equal(
        validation.get("no_accuracy_metrics_generated"),
        True,
        "E production accuracy-metric restriction",
    )
    require_equal(
        validation.get("detector_executed_in_validation_only_mode"),
        False,
        "E validation detector execution",
    )
    require_equal(
        validation.get("validation_only_mode_passed"),
        True,
        "E validation-only mode",
    )
    require_equal(validation.get("u4_output_inspected"), False, "E U4 status")

    production_documents = [authority, receipt, validation]
    for name in (
        "coverage_report.json",
        "phase3_status.json",
        "provenance_index.json",
        "run_predeclaration.json",
    ):
        production_documents.append(
            git_json(
                repository_root,
                E_EMPIRICAL_COMMIT,
                f"{E_EMPIRICAL_DIRECTORY}/{name}",
            )
        )
    validate_no_production_accuracy_metrics([*rows, *diagnostics])
    validate_no_production_accuracy_metrics(production_documents)
    return {
        "detector_identity": DETECTOR_IDENTITY,
        "detector_version": DETECTOR_VERSION,
        "empirical_records_sha256": E_EMPIRICAL_RECORDS_SHA256,
        "production_accuracy_metrics_computed": False,
        "production_run_count": 1,
        "row_count": 1850,
        "status": "PASS",
        "visible_flag_computed": False,
    }


def validate_e_gates(repository_root: Path) -> dict[str, Any]:
    """Validate the exact detector and homography authority documents."""

    detector_config_path = (
        "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/"
        "detector_candidate_config.json"
    )
    detector_version_path = (
        "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/"
        "detector_candidate_version_record.json"
    )
    detector_version = git_json(
        repository_root,
        E_DETECTOR_FREEZE_COMMIT,
        detector_version_path,
    )
    require_equal(
        detector_version.get("detector_identity_sha256"),
        DETECTOR_IDENTITY,
        "frozen detector identity",
    )
    require_equal(
        detector_version.get("detector_version"),
        DETECTOR_VERSION,
        "frozen detector version",
    )
    detector_hashes = {
        "detector_candidate_config.json": sha256_bytes(
            git_file_bytes(
                repository_root,
                E_DETECTOR_FREEZE_COMMIT,
                detector_config_path,
            )
        ),
        "detector_candidate_version_record.json": sha256_bytes(
            git_file_bytes(
                repository_root,
                E_DETECTOR_FREEZE_COMMIT,
                detector_version_path,
            )
        ),
    }

    detector_report_path = f"{E_FORMAL_DIRECTORY}/formal_evaluation_report.json"
    detector_receipt_path = f"{E_FORMAL_DIRECTORY}/formal_run_receipt.json"
    detector_status_path = f"{E_FORMAL_DIRECTORY}/phase3_status.json"
    detector_report = git_json(
        repository_root,
        E_STEP_3_1_COMMIT,
        detector_report_path,
    )
    detector_receipt = git_json(
        repository_root,
        E_STEP_3_1_COMMIT,
        detector_receipt_path,
    )
    detector_status = git_json(
        repository_root,
        E_STEP_3_1_COMMIT,
        detector_status_path,
    )
    detector_gate = validate_detector_gate(
        detector_report,
        detector_receipt,
        detector_status,
    )
    detector_gate["formal_evaluation_report_sha256"] = sha256_bytes(
        git_file_bytes(
            repository_root,
            E_STEP_3_1_COMMIT,
            detector_report_path,
        )
    )
    detector_gate["formal_run_receipt_sha256"] = sha256_bytes(
        git_file_bytes(
            repository_root,
            E_STEP_3_1_COMMIT,
            detector_receipt_path,
        )
    )

    homography_report_path = f"{E_HOMOGRAPHY_DIRECTORY}/step3_2_closure_report.json"
    homography_report = git_json(
        repository_root,
        E_STEP_3_2_COMMIT,
        homography_report_path,
    )
    homography_gate = validate_homography_gate(homography_report)
    homography_gate["closure_report_sha256"] = sha256_bytes(
        git_file_bytes(
            repository_root,
            E_STEP_3_2_COMMIT,
            homography_report_path,
        )
    )
    homography_receipt = git_json(
        repository_root,
        E_STEP_3_2_COMMIT,
        f"{E_HOMOGRAPHY_DIRECTORY}/validation_receipt.json",
    )
    for field in (
        "evidence_regeneration_occurred",
        "homography_refit_occurred",
        "probe_derived_tuning_applied",
        "probe_filtering_applied",
        "tuning_applied",
        "u4_output_inspected",
    ):
        require_equal(
            homography_receipt.get(field),
            False,
            f"Step 3.2 receipt {field}",
        )
    require_equal(
        homography_receipt.get("exact_applicability_context_passed"),
        True,
        "Step 3.2 receipt applicability",
    )
    homography_authority = git_json(
        repository_root,
        E_STEP_3_2_COMMIT,
        f"{E_HOMOGRAPHY_DIRECTORY}/authority_binding.json",
    )
    artifacts = homography_authority.get("authoritative_artifacts")
    require(isinstance(artifacts, list), "homography authority inventory missing")
    require_equal(len(artifacts), 7, "homography authority file count")
    for item in artifacts:
        require(isinstance(item, Mapping), "homography authority item invalid")
        path = item.get("path")
        expected_hash = item.get("sha256")
        require(isinstance(path, str), "homography authority path invalid")
        require(isinstance(expected_hash, str), "homography authority hash invalid")
        require_equal(
            sha256_bytes(
                git_file_bytes(
                    repository_root,
                    E_STEP_3_2_COMMIT,
                    path,
                )
            ),
            expected_hash,
            f"homography authority {path}",
        )
    return {
        "detector_file_hashes": detector_hashes,
        "detector_gate": detector_gate,
        "homography_gate": homography_gate,
    }


def validate_ownership(
    c_authority: Mapping[str, Any],
    c_provenance: Mapping[str, Any],
    b_policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exclusive cross-role ownership boundaries."""

    require_equal(
        c_authority.get("final_label_owner"),
        "Person C",
        "C package final label owner",
    )
    require_equal(
        c_authority.get("empirical_channel_owner"),
        "Person E",
        "C package empirical owner",
    )
    require_equal(
        c_provenance.get("final_label_owner"),
        "Person C",
        "C provenance final label owner",
    )
    require_equal(
        c_provenance.get("empirical_channel_owner"),
        "Person E",
        "C provenance empirical owner",
    )
    ownership = b_policy.get("ownership")
    require(isinstance(ownership, Mapping), "B ownership policy missing")
    require_equal(
        ownership.get("final_label_owner"),
        "person_c",
        "B policy final label owner",
    )
    require_equal(
        ownership.get("empirical_channel_owner"),
        "person_e",
        "B policy empirical owner",
    )
    require_equal(
        ownership.get("model_preprocessing_provenance_owner"),
        "person_a",
        "B policy model provenance owner",
    )
    preservation = b_policy.get("channel_preservation")
    require(isinstance(preservation, Mapping), "B preservation policy missing")
    require_equal(
        preservation.get("person_b_may_recompute_or_overwrite_visible_flag"),
        False,
        "B visible_flag computation claim",
    )
    require_equal(
        preservation.get("person_e_may_supply_or_overwrite_visible_flag"),
        False,
        "E visible_flag ownership claim",
    )
    return {
        "person_a_owns_model_preprocessing_provenance_only": True,
        "person_b_recomputed_visible_flag": False,
        "person_c_owns_visible_flag": True,
        "person_e_owns_empirical_channel_only": True,
        "status": "PASS",
    }


def validate_phase_restrictions(document: Mapping[str, Any]) -> None:
    """Require the signoff to leave U4 and Person A Phase 6 unauthorized."""

    require_equal(
        document.get("u4_output_inspected"),
        False,
        "U4 output inspection",
    )
    require_equal(
        document.get("person_a_phase6_authorized"),
        False,
        "Person A Phase 6 authorization",
    )


def validate_repository_scope(repository_root: Path) -> dict[str, Any]:
    """Require every difference from the B authority to be an authorized add."""

    output = _git(
        repository_root,
        "diff",
        "--name-status",
        B_POLICY_COMMIT,
        text=True,
    )
    require(isinstance(output, str), "Internal git text-mode failure")
    records = [line.split("\t") for line in output.splitlines() if line]
    untracked_output = _git(
        repository_root,
        "ls-files",
        "--others",
        "--exclude-standard",
        text=True,
    )
    require(isinstance(untracked_output, str), "Internal git text-mode failure")
    tracked_paths = {fields[-1].replace("\\", "/") for fields in records}
    untracked_paths = {
        line.replace("\\", "/") for line in untracked_output.splitlines() if line
    }
    paths = tracked_paths | untracked_paths

    def authorized(path: str) -> bool:
        return (
            path.startswith(f"docs/status/{SIGNOFF_DIRECTORY}/")
            or path
            == ("scripts/validate_person_b_phase3_step3_3_final_signoff_v0_1.py")
            or path
            == ("tests/analysis/test_person_b_phase3_step3_3_final_signoff_v0_1.py")
        )

    require(all(authorized(path) for path in paths), "Unauthorized path changed")
    require(
        all(fields[0] == "A" for fields in records),
        "A pre-existing path was modified",
    )
    return {
        "authorized_paths_only": True,
        "difference_paths": sorted(paths),
        "pre_existing_paths_modified": False,
    }


def validate_signoff_documents(
    signoff_root: Path,
    *,
    authorities: Mapping[str, str],
    b_policy_hashes: Mapping[str, str],
    c_result: Mapping[str, Any],
    coordinate: Mapping[str, Any],
    e_gates: Mapping[str, Any],
    e_empirical: Mapping[str, Any],
    ownership: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate the ten deterministic Person B signoff documents."""

    reject_u4_path(signoff_root)
    validate_inventory(
        signoff_root,
        expected_files=SIGNOFF_FILES,
        count_field="file_count",
    )
    documents = {
        name: validate_pretty_json(signoff_root / name)
        for name in sorted(SIGNOFF_FILES)
    }
    for name, document in documents.items():
        require_equal(
            document.get("schema_version"),
            "1.0",
            f"{name}: schema_version",
        )
        schema_id = document.get("schema_id")
        require(
            isinstance(schema_id, str) and SCHEMA_TOKEN in schema_id,
            f"{name}: schema_id must contain {SCHEMA_TOKEN}",
        )

    binding = documents["authority_binding.json"]
    require_equal(binding.get("commits"), authorities, "signoff authority commits")
    require_equal(
        binding.get("person_b_policy_file_sha256"),
        b_policy_hashes,
        "signoff B policy hashes",
    )
    require_equal(
        binding.get("person_b_coordinate_implementation", {}).get("sha256"),
        COORDINATE_SHA256,
        "signoff coordinate SHA",
    )
    require_equal(
        binding.get("person_c_joined_records", {}).get("sha256"),
        JOINED_RECORDS_SHA256,
        "signoff joined-record SHA",
    )
    require_equal(
        binding.get("person_e_empirical_records", {}).get("sha256"),
        E_EMPIRICAL_RECORDS_SHA256,
        "signoff empirical-record SHA",
    )
    require_equal(
        binding.get("person_e_empirical_records", {}).get("inventory_sha256"),
        E_EMPIRICAL_INVENTORY_SHA256,
        "signoff empirical-inventory SHA",
    )
    require_equal(
        binding.get("detector_identity_sha256"),
        DETECTOR_IDENTITY,
        "signoff detector identity",
    )
    require_equal(
        binding.get("detector_version"),
        DETECTOR_VERSION,
        "signoff detector version",
    )
    require_equal(
        binding.get("no_role_branch_merge_or_cherry_pick"),
        True,
        "signoff branch integration restriction",
    )
    require_equal(
        binding.get("project_wide_integration_claimed"),
        False,
        "signoff project integration claim",
    )

    detector = documents["detector_gate_validation.json"]
    require_equal(detector.get("result"), e_gates["detector_gate"], "detector result")
    require_equal(
        detector.get("production_package_metrics_used"),
        False,
        "production metrics use",
    )
    require_equal(detector.get("detector_executed"), False, "detector execution")
    require_equal(detector.get("u4_output_inspected"), False, "detector U4 status")
    require_equal(
        detector.get("detector_freeze_commit"),
        E_DETECTOR_FREEZE_COMMIT,
        "signoff detector-freeze commit",
    )
    require_equal(
        detector.get("formal_evaluation_commit"),
        E_STEP_3_1_COMMIT,
        "signoff formal-evaluation commit",
    )
    require_equal(
        detector.get("detector_identity_sha256"),
        DETECTOR_IDENTITY,
        "signoff detector-gate identity",
    )
    require_equal(
        detector.get("detector_version"),
        DETECTOR_VERSION,
        "signoff detector-gate version",
    )
    require_equal(
        detector.get("formal_gate_source_only"),
        True,
        "signoff formal-gate source",
    )
    require_equal(detector.get("formal_run_count"), 1, "signoff formal-run count")
    require_equal(detector.get("no_second_run"), True, "signoff second-run status")
    require_equal(
        detector.get("no_tuning_after_result"),
        True,
        "signoff detector tuning status",
    )

    homography = documents["homography_gate_validation.json"]
    require_equal(
        homography.get("result"),
        e_gates["homography_gate"],
        "homography result",
    )
    require_equal(
        homography.get("homography_refit_occurred"),
        False,
        "homography refit",
    )
    require_equal(homography.get("u4_output_inspected"), False, "homography U4")
    require_equal(
        homography.get("authority_commit"),
        E_STEP_3_2_COMMIT,
        "signoff homography commit",
    )
    for field in (
        "no_exclusions",
        "no_probe_filtering",
        "no_tuning",
    ):
        require_equal(homography.get(field), True, f"signoff homography {field}")

    joined = documents["joined_package_validation.json"]
    summary = c_result["summary"]
    require_equal(joined.get("row_count"), 1850, "signoff joined row count")
    require_equal(
        joined.get("unique_primary_key_count"),
        1850,
        "signoff joined key count",
    )
    require_equal(
        joined.get("joined_records_sha256"),
        JOINED_RECORDS_SHA256,
        "signoff joined SHA",
    )
    require_equal(
        joined.get("global_accounting"),
        summary["total"],
        "signoff global accounting",
    )
    require_equal(
        joined.get("per_layout"),
        summary["per_layout"],
        "signoff per-layout accounting",
    )
    require_equal(joined.get("final_and_rule_exact"), True, "signoff AND rule")
    require_equal(
        joined.get("raw_channels_preserved"),
        True,
        "signoff channel preservation",
    )
    require_equal(
        joined.get("production_accuracy_metrics_computed"),
        False,
        "signoff production metrics",
    )
    for field in (
        "deterministic_key_ordering",
        "deterministic_package_serialization",
        "final_and_rule_exact",
        "no_dropped_rows",
        "no_duplicate_identities",
        "raw_channels_preserved",
    ):
        require_equal(joined.get(field), True, f"signoff joined {field}")
    for field in (
        "detector_executed",
        "person_b_recomputed_visible_flag",
        "production_accuracy_metrics_computed",
        "u4_output_inspected",
    ):
        require_equal(joined.get(field), False, f"signoff joined {field}")
    require_equal(
        joined.get("person_c_commit"),
        C_JOINED_COMMIT,
        "signoff joined C commit",
    )
    require_equal(joined.get("primary_key"), list(PRIMARY_KEY), "signoff joined key")
    require_equal(
        joined.get("structural_failure_count"),
        0,
        "signoff joined structural failures",
    )

    coordinate_document = documents["coordinate_frame_validation.json"]
    require_equal(
        coordinate_document.get("result"),
        coordinate,
        "signoff coordinate result",
    )
    require_equal(
        coordinate_document.get("authority_commit"),
        B_POLICY_COMMIT,
        "signoff coordinate authority commit",
    )
    require_equal(
        coordinate_document.get("u4_output_inspected"),
        False,
        "signoff coordinate U4 status",
    )

    quarantine = documents["quarantine_policy_validation.json"]
    require_equal(
        quarantine.get("allowed_categories"),
        sorted(ALLOWED_QUARANTINE_CATEGORIES),
        "signoff quarantine categories",
    )
    require_equal(
        quarantine.get("global_accounting"),
        EXPECTED_TOTALS,
        "signoff quarantine totals",
    )
    require_equal(
        quarantine.get("per_layout"),
        EXPECTED_PER_LAYOUT,
        "signoff quarantine per-layout",
    )
    require_equal(quarantine.get("status"), "PASS", "quarantine signoff")
    invariants = quarantine.get("invariants")
    require(isinstance(invariants, Mapping), "signoff quarantine invariants missing")
    require(
        invariants and all(value is True for value in invariants.values()),
        "signoff quarantine invariant failed",
    )
    require_equal(
        quarantine.get("structural_failure_count"),
        0,
        "signoff quarantine structural failures",
    )
    require_equal(
        quarantine.get("u4_output_inspected"),
        False,
        "signoff quarantine U4 status",
    )

    decision = documents["analysis_readiness_decision.json"]
    require_equal(
        decision.get("step_3_3_final_decision"),
        "PASS",
        "Step 3.3 final decision",
    )
    require_equal(
        decision.get("joined_package_accepted"),
        True,
        "joined package acceptance",
    )
    require_equal(
        decision.get("analysis_readiness"),
        "READY",
        "analysis readiness",
    )
    require_equal(
        decision.get("supporting_person_c_commit"),
        C_JOINED_COMMIT,
        "decision C commit",
    )
    require_equal(
        decision.get("supporting_joined_records_sha256"),
        JOINED_RECORDS_SHA256,
        "decision C records hash",
    )
    require_equal(
        decision.get("coordinate_frame_validation"),
        coordinate,
        "decision coordinate result",
    )
    require_equal(
        decision.get("quarantine_totals"),
        EXPECTED_TOTALS,
        "decision quarantine totals",
    )
    require_equal(
        decision.get("structural_failure_count"),
        0,
        "decision structural failures",
    )
    require_equal(
        decision.get("unresolved_owner_correction_count"),
        0,
        "decision owner corrections",
    )
    require_equal(
        decision.get("detector_gate_validation"),
        e_gates["detector_gate"],
        "decision detector result",
    )
    require_equal(
        decision.get("homography_gate_validation"),
        e_gates["homography_gate"],
        "decision homography result",
    )
    require_equal(
        decision.get("ownership_validation"),
        ownership,
        "decision ownership",
    )
    require_equal(
        decision.get("detector_executed"),
        False,
        "decision detector execution",
    )
    require_equal(
        decision.get("production_accuracy_metrics_computed"),
        False,
        "decision production metrics",
    )
    validate_phase_restrictions(decision)

    closure = documents["phase3_closure_recommendation.json"]
    require_equal(closure.get("step_3_1"), "PASS", "closure Step 3.1")
    require_equal(closure.get("step_3_2"), "PASS", "closure Step 3.2")
    require_equal(closure.get("step_3_3"), "PASS", "closure Step 3.3")
    require_equal(
        closure.get("phase3_closure_recommendation"),
        "READY",
        "Phase 3 closure recommendation",
    )
    require_equal(
        closure.get("independent_final_verification"),
        "PENDING",
        "independent final verification",
    )
    require_equal(
        closure.get("overall_phase3_status"),
        "IN_PROGRESS",
        "overall Phase 3 status",
    )
    require_equal(
        closure.get("integration_branch_merged_or_integrated"),
        False,
        "closure integration status",
    )
    require_equal(
        closure.get("phase3_formally_closed"),
        False,
        "formal Phase 3 closure",
    )
    validate_phase_restrictions(closure)

    receipt = documents["validation_receipt.json"]
    expected_receipt = {
        "analysis_readiness": "READY",
        "coordinate_frame_pass": True,
        "detector_executed": False,
        "final_and_rule_exact": True,
        "independent_final_verification": "PENDING",
        "joined_package_pass": True,
        "no_unresolved_structural_failure": True,
        "overall_phase3_status": "IN_PROGRESS",
        "person_a_phase6_authorized": False,
        "person_b_recomputed_visible_flag": False,
        "phase3_closure_recommendation": "READY",
        "pre_existing_paths_modified": False,
        "production_accuracy_metrics_computed": False,
        "quarantine_policy_pass": True,
        "raw_channels_preserved": True,
        "step_3_1_gate_pass": True,
        "step_3_2_gate_pass": True,
        "step_3_3_final_signoff_ready": True,
        "u4_output_inspected": False,
        "validation_mode": "validation-only",
    }
    for field, expected in expected_receipt.items():
        require_equal(receipt.get(field), expected, f"validation receipt {field}")
    require_equal(
        receipt.get("ownership_validation"),
        ownership,
        "validation receipt ownership",
    )
    require_equal(
        receipt.get("person_e_empirical_validation"),
        e_empirical,
        "validation receipt E authority",
    )
    require_equal(
        receipt.get("signoff_artifact_count"),
        len(SIGNOFF_FILES),
        "validation receipt artifact count",
    )
    return documents


def validate_all(
    *,
    repository_root: Path,
    signoff_root: Path,
    person_c_package_root: Path,
    mode: str,
) -> dict[str, Any]:
    """Run the complete validation-only signoff audit."""

    require_equal(mode, "validation-only", "execution mode")
    for path in (repository_root, signoff_root, person_c_package_root):
        reject_u4_path(path)
    require(repository_root.is_dir(), "repository root missing")

    authorities = validate_authority_commits(repository_root)
    b_policy_result = validate_b_policy(repository_root)
    c_result = validate_c_package(repository_root, person_c_package_root)
    c_documents = c_result["documents"]
    coordinate_source = git_file_bytes(
        repository_root,
        B_POLICY_COMMIT,
        COORDINATE_PATH,
    )
    coordinate = validate_coordinate_authority(
        coordinate_source,
        c_documents["authority_binding.json"],
        c_documents["provenance_index.json"],
    )
    e_gates = validate_e_gates(repository_root)
    e_empirical = validate_e_empirical_authority(repository_root)
    b_visibility_policy = b_policy_result["documents"][
        "visibility_acceptance_policy.json"
    ]
    ownership = validate_ownership(
        c_documents["authority_binding.json"],
        c_documents["provenance_index.json"],
        b_visibility_policy,
    )
    signoff_documents = validate_signoff_documents(
        signoff_root,
        authorities=authorities,
        b_policy_hashes=b_policy_result["hashes"],
        c_result=c_result,
        coordinate=coordinate,
        e_gates=e_gates,
        e_empirical=e_empirical,
        ownership=ownership,
    )
    scope = validate_repository_scope(repository_root)
    public_joined_summary = {
        key: value
        for key, value in c_result["summary"].items()
        if key != "primary_keys"
    }
    return {
        "analysis_readiness": signoff_documents["analysis_readiness_decision.json"][
            "analysis_readiness"
        ],
        "coordinate_frame": coordinate,
        "detector_gate": e_gates["detector_gate"],
        "homography_gate": e_gates["homography_gate"],
        "joined_records_sha256": JOINED_RECORDS_SHA256,
        "joined_summary": public_joined_summary,
        "mode": mode,
        "ownership": ownership,
        "person_e_empirical": e_empirical,
        "phase3_closure_recommendation": signoff_documents[
            "phase3_closure_recommendation.json"
        ]["phase3_closure_recommendation"],
        "repository_scope": scope,
        "status": "PASS",
        "step_3_3_final_decision": signoff_documents[
            "analysis_readiness_decision.json"
        ]["step_3_3_final_decision"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse validation-only command-line arguments."""

    repository_default = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Validate Person B Phase 3 Step 3.3 final signoff without "
            "executing a detector or mutating an authority package."
        )
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=repository_default,
    )
    parser.add_argument(
        "--signoff-root",
        type=Path,
        default=(repository_default / "docs" / "status" / SIGNOFF_DIRECTORY),
    )
    parser.add_argument(
        "--person-c-package-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--mode",
        choices=("validation-only",),
        default="validation-only",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run validation and print a deterministic receipt to stdout."""

    args = parse_args(argv)
    try:
        result = validate_all(
            repository_root=args.repository_root.resolve(),
            signoff_root=args.signoff_root.resolve(),
            person_c_package_root=args.person_c_package_root.resolve(),
            mode=args.mode,
        )
    except SignoffValidationError as error:
        print(
            f"PERSON_B_STEP3_3_FINAL_SIGNOFF_VALIDATION=FAIL: {error}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    print("PERSON_B_STEP3_3_FINAL_SIGNOFF_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
