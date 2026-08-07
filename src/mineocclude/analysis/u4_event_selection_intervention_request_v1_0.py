"""Fail-closed preparation contract for the Person B U4 request.

This module deliberately does *not* select an event, fit a direction, inspect
an intervention outcome, or construct a scientific request.  The current
66-cell authorities do not provide the five held-out terminal reveals required
by the frozen U3/U4 contract, and no fitted direction or dose table is present
on the Person B branch.  The published package therefore records a blocked,
machine-readable request decision and the exact producer evidence still
required.

The validator is intentionally separate from ``validate_intervention_request``:
that validator accepts only a complete request, while this package proves that
an incomplete request is being held at the pre-execution gate rather than being
silently converted into an executable artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mineocclude.analysis.manifests import canonical_json_bytes

PACKAGE_DIRECTORY = (
    "docs/status/person_b_u4_event_selection_intervention_request_v1_0"
)
PACKAGE_SCHEMA_VERSION = "person-b-u4-event-selection-intervention-request-v1.0"
REQUEST_SCHEMA_VERSION = "person-b-intervention-request-v1.0"
DECISION_BLOCKED = "BLOCKED_MISSING_DIRECTION_AND_HELDOUT_EVENT_AUTHORITY"

PERSON_B_BRANCH = "role/person-b-analysis"
PERSON_B_PREACTIVATION_COMMIT = "25e09cb605699cdcb00dec1fbb1726977bec55e0"
PERSON_B_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
PERSON_B_PARTITION_PATH = (
    "docs/status/person_b_66_cell_preactivation_v0_1/u4_heldout_partition.json"
)
PERSON_B_PARTITION_SHA256 = (
    "8a4f266cb984195d72514f1e9ce21d5e6b6714aa1bcd87f22bf83e7ea3b59941"
)
PERSON_B_PARTITION_SIZE = 3_981
PERSON_B_SELECTION_PATH = (
    "docs/status/person_b_66_cell_preactivation_v0_1/"
    "b_to_c_u4_selection_receipt.json"
)
PERSON_B_SELECTION_SHA256 = (
    "603972fe36b24925dfa3ea5b655a4285a86375bbe9ee0ac976c75f3c3d59369a"
)
PERSON_B_SELECTION_SIZE = 4_753
PERSON_B_SELECTION_ARTIFACT_HASH = (
    "be476341a4e67094f986b1d47d5fd63c8a0eb6951e8b92a75f050af899c2da3b"
)
PERSON_B_CONFIG_PATH = "configs/analysis/core.yaml"
PERSON_B_CONFIG_SHA256 = (
    "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
)

PERSON_C_COMMIT = "3846230a4f141a8a55084eeaaa040f9a10cfc408"
PERSON_C_BRANCH = "role/person-c-data"
PERSON_C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
PERSON_C_ACCEPTED_MANIFEST_SIZE = 34542
PERSON_C_U4_REQUIREMENTS_PATH = (
    "docs/status/person_c_66_cell_capture_authority_v0_1/"
    "u4_supplemental_capture_requirements.json"
)
PERSON_C_U4_REQUIREMENTS_SHA256 = (
    "e2397f8398e50dd4e7c4b8c34780fc5a9978e878cb0b5690c62b76a553298b75"
)
PERSON_C_U4_FINDING_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/"
    "u4_eligibility_finding_v0_2.json"
)
PERSON_C_U4_FINDING_SHA256 = (
    "307e4ebe034e10a5ca76bf00532eab9f96e00da54e68211e8a7b2e37917d2afd"
)
PERSON_C_C8_2_HANDOFF_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/"
    "c_to_b_oracle_handoff.json"
)
PERSON_C_C8_2_HANDOFF_SHA256 = (
    "dd5569164d72ba8a25e4efbd74e013819744b7cf10b22ea949e22a13b3a3b33b"
)

PERSON_D_COMMIT = "8cd2fdfc7759b285a7748ccdb4564e475b3ce1cf"
PERSON_D_BRANCH = "role/person-d-baselines"
PERSON_D_SECTION_7_PATH = (
    "docs/status/person_d_terminal_handoff_v0_1/PERSON_D_OPERATING_HANDOFF.md"
)
PERSON_D_SECTION_7_SHA256 = (
    "0d54888e3613f1b1e0c4d8128c2a9d50a9bdf9aa81cb65ef399e57bbc0ac3820"
)
PERSON_D_DEPENDENCY_ID = "D-7.3"
PERSON_D_REQUIRED_FIELDS = (
    "direction_id",
    "direction_version",
    "direction_hash",
    "seed",
    "event_id",
    "layer_idx",
    "timestep_idx",
    "dose_id",
    "alpha_requested",
    "alpha_applied",
)

REQUIRED_EVENT_COUNT = 5
HELDOUT_LAYOUT_IDS = ("layout_03", "layout_04")
REQUIRED_DIRECTION_FIELDS = (
    "direction_id",
    "direction_version",
    "direction_hash",
    "source_run_id",
    "seed",
)
REQUIRED_EVENT_FIELDS = (
    "event_id",
    "trajectory_id",
    "layout_id",
    "layer_idx",
    "timestep_idx",
)
REQUIRED_DOSE_FIELDS = (
    "dose_id",
    "alpha_requested",
    "alpha_applied",
    "intended_block_shift",
    "cap_reduced",
)
INVENTORIED_PACKAGE_FILES = (
    "authority_binding.json",
    "event_selection_decision.json",
    "intervention_request.json",
    "missing_inputs.json",
    "validation_receipt.json",
)


class U4EventRequestError(ValueError):
    """Raised when the blocked U4 request package is inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise U4EventRequestError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_string(value: Any, *, label: str) -> None:
    _require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
        f"{label} must be 64 lowercase hexadecimal characters",
    )


def _git_blob(root: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "blob", f"{commit}:{path}"],
        capture_output=True,
        check=False,
    )
    _require(
        result.returncode == 0,
        f"required Git object is unavailable: {commit}:{path}",
    )
    return result.stdout


def _git_commit_exists(root: Path, commit: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{commit}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    _require(result.returncode == 0, f"required commit is unavailable: {commit}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise U4EventRequestError(f"could not load {path}: {error}") from error
    _require(isinstance(document, dict), f"{path.name} must contain a JSON object")
    return document


def _canonical_json(path: Path, document: Mapping[str, Any]) -> None:
    canonical = canonical_json_bytes(document)
    _require(
        path.read_bytes() == canonical + b"\n",
        f"{path.name} is not canonical UTF-8 JSON with one final newline",
    )


def _validate_authority_binding(document: Mapping[str, Any], root: Path) -> None:
    _require(
        document.get("schema_version") == "1.0",
        "authority binding schema_version must be 1.0",
    )
    _require(document.get("package_schema") == PACKAGE_SCHEMA_VERSION, "package schema mismatch")
    _require(document.get("decision") == DECISION_BLOCKED, "authority decision is not blocked")
    _require(document.get("person_b_branch") == PERSON_B_BRANCH, "Person B branch binding mismatch")
    _require(
        document.get("person_b_preparation_commit") == PERSON_B_PREACTIVATION_COMMIT,
        "Person B preparation commit binding mismatch",
    )
    _require(document.get("person_c_branch") == PERSON_C_BRANCH, "Person C branch binding mismatch")
    _require(document.get("person_c_source_commit") == PERSON_C_COMMIT, "Person C commit binding mismatch")
    _require(document.get("person_d_branch") == PERSON_D_BRANCH, "Person D branch binding mismatch")
    _require(document.get("person_d_source_commit") == PERSON_D_COMMIT, "Person D commit binding mismatch")
    d_record = document.get("person_d_dependency")
    _require(isinstance(d_record, Mapping), "Person D dependency binding is missing")
    _require(d_record.get("dependency_id") == PERSON_D_DEPENDENCY_ID, "Person D dependency ID mismatch")
    _require(d_record.get("required_fields") == list(PERSON_D_REQUIRED_FIELDS), "Person D required field contract changed")
    c_artifacts = document.get("person_c_artifacts")
    _require(isinstance(c_artifacts, Mapping), "Person C artifact bindings are missing")
    expected_c = {
        "accepted_manifest": (PERSON_C_ACCEPTED_MANIFEST_PATH, PERSON_B_ACCEPTED_MANIFEST_SHA256),
        "u4_requirements": (PERSON_C_U4_REQUIREMENTS_PATH, PERSON_C_U4_REQUIREMENTS_SHA256),
        "u4_eligibility_finding": (PERSON_C_U4_FINDING_PATH, PERSON_C_U4_FINDING_SHA256),
        "c8_2_handoff": (PERSON_C_C8_2_HANDOFF_PATH, PERSON_C_C8_2_HANDOFF_SHA256),
    }
    for name, (path, digest) in expected_c.items():
        record = c_artifacts.get(name)
        _require(isinstance(record, Mapping), f"Person C {name} binding is missing")
        _require(record.get("path") == path, f"Person C {name} path mismatch")
        _require(record.get("sha256") == digest, f"Person C {name} SHA-256 mismatch")
        payload = _git_blob(root, PERSON_C_COMMIT, path)
        _require(_sha256(payload) == digest, f"Person C {name} Git object hash mismatch")
        if name == "accepted_manifest":
            _require(len(payload) == PERSON_C_ACCEPTED_MANIFEST_SIZE, "Person C manifest byte size mismatch")
    _require(d_record.get("path") == PERSON_D_SECTION_7_PATH, "Person D section 7 path mismatch")
    _require(d_record.get("sha256") == PERSON_D_SECTION_7_SHA256, "Person D section 7 SHA-256 mismatch")
    _require(_sha256(_git_blob(root, PERSON_D_COMMIT, PERSON_D_SECTION_7_PATH)) == PERSON_D_SECTION_7_SHA256, "Person D section 7 Git object hash mismatch")


def _load_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise U4EventRequestError(f"{label} is not valid JSON: {error}") from error
    _require(isinstance(document, dict), f"{label} must be a JSON object")
    return document


def _validate_historical_selection_sources(root: Path) -> None:
    """Verify the blocked package points at immutable B source objects."""

    _git_commit_exists(root, PERSON_B_PREACTIVATION_COMMIT)
    partition = _git_blob(root, PERSON_B_PREACTIVATION_COMMIT, PERSON_B_PARTITION_PATH)
    _require(len(partition) == PERSON_B_PARTITION_SIZE, "historical U4 partition byte size changed")
    _require(_sha256(partition) == PERSON_B_PARTITION_SHA256, "historical U4 partition hash changed")
    selection = _git_blob(root, PERSON_B_PREACTIVATION_COMMIT, PERSON_B_SELECTION_PATH)
    _require(len(selection) == PERSON_B_SELECTION_SIZE, "historical U4 selection byte size changed")
    _require(_sha256(selection) == PERSON_B_SELECTION_SHA256, "historical U4 selection hash changed")
    source = _load_json_bytes(selection, "historical U4 selection")
    _require(source.get("artifact_hash") == PERSON_B_SELECTION_ARTIFACT_HASH, "historical U4 selection artifact hash changed")
    _require(source.get("event_ids_frozen") is False and source.get("selection_ready_for_c8_2") is False, "historical U4 selection is not blocked")
    _require(source.get("u4_outcomes_inspected") is False, "historical U4 selection inspected outcomes")


def _validate_selection(document: Mapping[str, Any], root: Path) -> None:
    _require(document.get("schema_version") == "1.0", "selection schema_version must be 1.0")
    _require(document.get("package_schema") == PACKAGE_SCHEMA_VERSION, "selection package schema mismatch")
    _require(document.get("decision") == DECISION_BLOCKED, "selection decision is not blocked")
    _require(document.get("event_ids_frozen") is False, "event IDs must remain unfrozen")
    _require(document.get("selected_event_ids") == [], "blocked selection must not contain event IDs")
    _require(document.get("required_heldout_event_count") == REQUIRED_EVENT_COUNT, "required held-out event count changed")
    _require(document.get("heldout_layout_ids") == list(HELDOUT_LAYOUT_IDS), "held-out layout partition changed")
    _require(document.get("partition_path") == PERSON_B_PARTITION_PATH, "partition path mismatch")
    _require(document.get("partition_sha256") == PERSON_B_PARTITION_SHA256, "partition SHA-256 mismatch")
    _require(document.get("source_selection_path") == PERSON_B_SELECTION_PATH, "historical selection path mismatch")
    _require(document.get("source_selection_sha256") == PERSON_B_SELECTION_SHA256, "historical selection SHA-256 mismatch")
    _require(document.get("source_selection_artifact_hash") == PERSON_B_SELECTION_ARTIFACT_HASH, "historical selection artifact hash mismatch")
    _require(document.get("selection_ready_for_c8_2") is False, "selection cannot claim C8.2 readiness")
    _require(document.get("u4_output_inspected") is False, "U4 output inspection is forbidden")
    _require(document.get("scientific_execution_performed") is False, "scientific execution is forbidden")
    _require(document.get("selection_basis") == "frozen_layout_partition_only_event_authority_unavailable", "selection basis must remain fail-closed")
    _validate_historical_selection_sources(root)


def _validate_request(document: Mapping[str, Any]) -> None:
    _require(document.get("schema_version") == REQUEST_SCHEMA_VERSION, "request schema version mismatch")
    _require(document.get("decision") == DECISION_BLOCKED, "request decision is not blocked")
    _require(document.get("request_authorized") is False, "blocked request cannot be authorized")
    _require(document.get("scientific_execution_performed") is False, "scientific execution is forbidden")
    _require(document.get("u4_output_inspected") is False, "U4 output inspection is forbidden")
    for field in REQUIRED_DIRECTION_FIELDS:
        _require(document.get(field) is None, f"blocked request must not invent {field}")
    for field in REQUIRED_EVENT_FIELDS:
        _require(document.get(field) is None, f"blocked request must not invent {field}")
    _require(document.get("dose_table") == [], "blocked request must not invent doses")
    _require(
        document.get("dose_fields_required") == list(REQUIRED_DOSE_FIELDS),
        "dose field contract is incomplete",
    )
    _require(document.get("direction") is None, "blocked request must not contain direction values")
    _require(document.get("heldout_events") == [], "blocked request must not contain held-out events")
    _require(document.get("missing_producer") == "person_b_direction_and_event_selection", "missing producer is not Person B")


def _validate_missing_inputs(document: Mapping[str, Any]) -> None:
    _require(document.get("schema_version") == "1.0", "missing-input schema_version must be 1.0")
    _require(document.get("decision") == DECISION_BLOCKED, "missing-input decision is not blocked")
    entries = document.get("required_inputs")
    _require(isinstance(entries, list) and entries, "required_inputs must be non-empty")
    by_id = {entry.get("input_id"): entry for entry in entries if isinstance(entry, Mapping)}
    required = {
        "person_b_fitted_u4_direction",
        "person_b_heldout_event_selection",
        "person_b_u4_dose_table",
        "person_b_u4_layer_timestep_selection",
    }
    _require(set(by_id) == required, "required-input set is not exact")
    for entry in entries:
        _require(entry.get("owner_role") == "person_b", "missing input owner must be Person B")
        _require(entry.get("status") == "missing", "missing input must be marked missing")
        _require(entry.get("placeholder_created") is False, "placeholder input was created")
    _require(document.get("person_c_c8_2_blocked") is True, "C8.2 block must be recorded")
    _require(document.get("person_d_dependency_7_3_blocked") is True, "D dependency 7.3 block must be recorded")


def validate_documents(
    documents: Mapping[str, Mapping[str, Any]],
    inventory: Mapping[str, Any],
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate an in-memory package and its exact external authorities."""

    expected_names = set(INVENTORIED_PACKAGE_FILES)
    _require(set(documents) == expected_names, "package document set is not exact")
    for name, document in documents.items():
        _require(isinstance(document, Mapping), f"{name} must be a JSON object")
    _validate_authority_binding(documents["authority_binding.json"], repository_root)
    _validate_selection(documents["event_selection_decision.json"], repository_root)
    _validate_request(documents["intervention_request.json"])
    _validate_missing_inputs(documents["missing_inputs.json"])
    receipt = documents["validation_receipt.json"]
    _require(receipt.get("schema_version") == "1.0", "validation receipt schema_version must be 1.0")
    _require(receipt.get("decision") == DECISION_BLOCKED, "validation receipt decision is not blocked")
    _require(receipt.get("all_checks_passed") is True, "validation receipt does not report passing structural checks")
    _require(receipt.get("scientific_execution_performed") is False, "receipt claims scientific execution")
    _require(receipt.get("u4_output_inspected") is False, "receipt claims U4 inspection")
    _require(receipt.get("selection_ready_for_c8_2") is False, "receipt claims C8.2 readiness")
    _require(inventory.get("schema_version") == "1.0", "inventory schema_version must be 1.0")
    _require(inventory.get("file_count") == len(INVENTORIED_PACKAGE_FILES), "inventory file_count mismatch")
    observed: set[str] = set()
    for item in inventory.get("files", []):
        _require(isinstance(item, Mapping), "inventory entries must be objects")
        name = item.get("path")
        _require(name in expected_names, f"inventory names unknown file {name!r}")
        _require(name not in observed, f"inventory duplicates {name!r}")
        observed.add(name)
        # Repository JSON artifacts conventionally carry one final newline;
        # the semantic bytes before that newline are the canonical JSON form.
        payload = canonical_json_bytes(documents[name]) + b"\n"
        _require(item.get("sha256") == _sha256(payload), f"inventory SHA mismatch for {name}")
        _require(item.get("byte_size") == len(payload), f"inventory byte size mismatch for {name}")
    _require(observed == expected_names, "inventory does not cover every package document")
    return {
        "validated": True,
        "decision": DECISION_BLOCKED,
        "selected_event_count": 0,
        "required_event_count": REQUIRED_EVENT_COUNT,
        "selection_ready_for_c8_2": False,
        "person_d_dependency_7_3_blocked": True,
        "scientific_execution_performed": False,
        "u4_output_inspected": False,
    }


def validate_package(package_root: Path, repository_root: Path) -> dict[str, Any]:
    """Load and validate the checked-in package without writing anything."""

    documents = {name: _load_json(package_root / name) for name in INVENTORIED_PACKAGE_FILES}
    inventory = _load_json(package_root / "sha256_inventory.json")
    for name, document in (*documents.items(), ("sha256_inventory.json", inventory)):
        _canonical_json(package_root / name, document)
    return validate_documents(documents, inventory, repository_root=repository_root)


__all__ = [
    "DECISION_BLOCKED",
    "INVENTORIED_PACKAGE_FILES",
    "PACKAGE_DIRECTORY",
    "PACKAGE_SCHEMA_VERSION",
    "REQUEST_SCHEMA_VERSION",
    "U4EventRequestError",
    "validate_documents",
    "validate_package",
]
