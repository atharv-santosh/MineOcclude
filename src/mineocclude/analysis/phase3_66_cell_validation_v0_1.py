"""Fail-closed validation of Person C's 66-cell visibility handoff.

This module is deliberately a consumer validator, not a visibility builder.
It reads Person C's evidence through exact Git objects, preserves C's
``visible_flag`` and checks the frozen AND rule without recomputing or
overwriting the label.  The validator is additive: it does not change the
historical 1,850-row Phase 3 signoff package.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PACKAGE_DIRECTORY = "docs/status/person_b_phase3_66_cell_handoff_v0_1"
PACKAGE_FILES = (
    "authority_binding.json",
    "c_consumer_validation_receipt.json",
    "phase3_closure_recommendation.json",
    "phase3_status.json",
    "sha256_inventory.json",
)

# e908 is the exact C strict-visibility publication.  The producer commit is
# retained separately because publication and production have different roles.
PERSON_C_AUTHORITY_COMMIT = "e908ead4a7ff5ab3ae310bb846969a7859fdb26b"
PERSON_C_PRODUCER_COMMIT = "aceb319c47af6d494d6e5314049b12ab1a0a002f"
PERSON_C_ACCEPTED_MANIFEST_COMMIT = "a8bed8adf7e24ca7fe5b6b6afa3342da61434be3"
PERSON_C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
PERSON_C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
PERSON_C_CAPTURE_MANIFEST_PATH = (
    "docs/status/person_c_66_cell_capture_authority_v0_1/capture_package_manifest.json"
)
PERSON_C_CAPTURE_MANIFEST_SHA256 = (
    "ca6ef6bd0a6ee144731ff3e6f470f767a2c1a82e8b46aef9fb5e458efb814f56"
)
PERSON_C_CAPTURE_MANIFEST_SIZE = 80_149
PERSON_C_ORACLE_HANDOFF_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/c_to_b_oracle_handoff.json"
)
PERSON_C_ORACLE_HANDOFF_SHA256 = (
    "dd5569164d72ba8a25e4efbd74e013819744b7cf10b22ea949e22a13b3a3b33b"
)
PERSON_C_ORACLE_HANDOFF_SIZE = 9_525
PERSON_C_JOIN_MANIFEST_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/visibility_join_manifest.json"
)
PERSON_C_JOIN_MANIFEST_SHA256 = (
    "8e03d6564c3a5d17e6199af258708bd8526842410c78a7f58330df9e0bf960cc"
)
PERSON_C_JOIN_MANIFEST_SIZE = 3_926
PERSON_C_JOIN_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/visibility_join.jsonl"
)
PERSON_C_JOIN_SHA256 = (
    "6fcfaba99feed706e7106d0f1d9b758700d920ee2001b3ca6f150320f09313b7"
)
PERSON_C_JOIN_SIZE = 5_654_859
PERSON_C_GEOMETRIC_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/geometric_visibility.jsonl"
)
PERSON_C_GEOMETRIC_SHA256 = (
    "b49b098b2176cd8416f5a18465290131a9a7067d7d0a1e79ab2b6590489598d9"
)
PERSON_C_GEOMETRIC_SIZE = 3_057_106
PERSON_C_EVENT_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/event_table.jsonl"
)
PERSON_C_EVENT_SHA256 = (
    "fadc0fc4c2afab2b39b992979317d4576fa2618263c8b09e29ca6c215528bb49"
)
PERSON_C_EVENT_SIZE = 45_561
PERSON_C_DISAGREEMENT_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/disagreement_ledger.json"
)
PERSON_C_DISAGREEMENT_SHA256 = (
    "bf3243b5c0c7581db053a56c4a4fd6c151d017504f067e8a66f2a31b7cb69b99"
)
PERSON_C_DISAGREEMENT_SIZE = 476_996
PERSON_C_CLOSURE_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/closure_receipt.json"
)
PERSON_C_CLOSURE_SHA256 = (
    "2d7ba1bb7dd953c3679fcfef0c69c32588b86775c3fb3af86e14deb58e9b6a8a"
)
PERSON_C_CLOSURE_SIZE = 2_622
PERSON_C_U4_FINDING_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/u4_eligibility_finding_v0_2.json"
)
PERSON_C_U4_FINDING_SHA256 = (
    "307e4ebe034e10a5ca76bf00532eab9f96e00da54e68211e8a7b2e37917d2afd"
)
PERSON_C_U4_FINDING_SIZE = 5_019

PERSON_A_COMMIT = "77e43bd1665671b9e23d6d6ef927ee4944611342"
PERSON_A_FRAME_MAP_INVENTORY_PATH = (
    "data/handoff_a/person_a_66_cell_production_input_v0_1/sha256_inventory.json"
)
PERSON_A_FRAME_MAP_INVENTORY_SHA256 = (
    "a473bf830ed31e49762d62bba97032e52f4967e52f9987ad10cd5879ed9bd004"
)
PERSON_A_FRAME_MAP_INVENTORY_SIZE = 7_736
PERSON_E_COMMIT = "fec27d08b4629afa07c7858598e94778dc6e7bef"
PERSON_E_RECORDS_PATH = (
    "data/handoff_c/person_e_66_cell_empirical_visibility_v0_1/"
    "empirical_visibility_records.jsonl"
)
PERSON_E_RECORDS_SHA256 = (
    "fd0ad70ce880645fcda668d23dacc07784c2f8e418a3eceabd9f88ac391e07f9"
)
PERSON_E_RECORDS_SIZE = 4_164_985
PERSON_B_COSIGN_COMMIT = "a8648514033f8d58887c3b919f02985704aaa310"
PERSON_B_COSIGN_PATH = (
    "docs/status/person_b_66_cell_coordinate_frame_cosign_v0_1/"
    "coordinate_frame_cosign.json"
)
PERSON_B_COSIGN_SHA256 = (
    "b40d8ba1103e1638af386cc365ec727ab576d842516accc41d675d4fdb3d6b7d"
)
PERSON_C_COORDINATE_AUTHORITY_COMMIT = PERSON_C_AUTHORITY_COMMIT
PERSON_C_COORDINATE_AUTHORITY_PATH = (
    "docs/status/person_c_66_cell_capture_authority_v0_1/"
    "coordinate_frame_authority.json"
)
PERSON_C_COORDINATE_AUTHORITY_SHA256 = (
    "1aed95e444f82ab4caf9935c039e87df3aafbf38830bf763a646aba3d62b509b"
)

EXPECTED_TRAJECTORIES = 66
EXPECTED_FRAME_KEYS = 2468
EXPECTED_APPLICABLE = 2108
EXPECTED_NOT_APPLICABLE = 360
EXPECTED_VISIBLE = 1413
EXPECTED_HIDDEN = 695
EXPECTED_QUARANTINED = 744
EXPECTED_LAYOUT_ROWS = {
    "layout_01": 375,
    "layout_02": 379,
    "layout_03": 268,
    "layout_04": 354,
    "layout_05": 518,
    "layout_06": 574,
}
EXPECTED_QUARANTINE_CATEGORIES = {
    "geometry_hidden_detector_visible": 313,
    "geometry_visible_detector_hidden": 71,
    "invalid_geometry": 360,
    "missing_detector": 0,
    "none": 1724,
}
EXPECTED_DISAGREEMENT_CLASSES = {
    "agreement": 1696,
    "detector_not_applicable": 360,
    "geometry_ambiguous": 42,
    "geometry_hidden_detector_visible": 313,
    "geometry_visible_detector_hidden": 57,
}


class Phase3ValidationError(ValueError):
    """Raised when a C 66-cell authority fails a required invariant."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Phase3ValidationError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_bytes(repository_root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise Phase3ValidationError(
            f"git {' '.join(arguments)} failed: {detail or 'unknown error'}"
        )
    return result.stdout


def read_git_blob(
    repository_root: Path,
    commit: str,
    path: str,
    expected_sha256: str | None = None,
) -> bytes:
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "commit must be full SHA-1")
    require(path and not path.startswith("/") and ".." not in Path(path).parts, "unsafe path")
    require(
        _git_bytes(repository_root, "cat-file", "-t", commit).decode().strip() == "commit",
        f"{commit} is not a commit object",
    )
    payload = _git_bytes(repository_root, "cat-file", "blob", f"{commit}:{path}")
    if expected_sha256 is not None:
        require(sha256_bytes(payload) == expected_sha256, f"{commit}:{path} hash mismatch")
    return payload


def strict_json(payload: bytes, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"{label} repeats key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                Phase3ValidationError(f"{label} contains {value}")
            ),
        )
    except Phase3ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Phase3ValidationError(f"{label} is invalid JSON: {error}") from error


def strict_jsonl(payload: bytes, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise Phase3ValidationError(f"{label} is not UTF-8") from error
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        value = strict_json(line.encode("utf-8"), f"{label} line {number}")
        require(isinstance(value, Mapping), f"{label} line {number} is not an object")
        rows.append(dict(value))
    return rows


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def validate_accepted_manifest(document: Mapping[str, Any]) -> set[str]:
    require(document.get("schema_version") == "1.0", "C accepted manifest schema changed")
    require(document.get("accepted_count") == EXPECTED_TRAJECTORIES, "C accepted count changed")
    require(document.get("excluded_count") == 0, "C excluded count is nonzero")
    records = document.get("records")
    require(isinstance(records, list) and len(records) == EXPECTED_TRAJECTORIES, "C records must contain 66 rows")
    ids: set[str] = set()
    for record in records:
        require(isinstance(record, Mapping), "C accepted record is not an object")
        trajectory_id = record.get("trajectory_id")
        require(isinstance(trajectory_id, str) and trajectory_id not in ids, "C trajectory identity is missing or duplicated")
        ids.add(trajectory_id)
        require(record.get("accepted") is True and record.get("status") == "PASS", f"C record {trajectory_id} is not accepted")
        require(isinstance(record.get("episode_id"), int), f"C record {trajectory_id} lacks episode_id")
        require(isinstance(record.get("layout_id"), str), f"C record {trajectory_id} lacks layout_id")
    require(len(ids) == EXPECTED_TRAJECTORIES, "C accepted trajectory IDs are not unique")
    return ids


def validate_capture_manifest(document: Mapping[str, Any], accepted_ids: set[str]) -> None:
    require(document.get("accepted_count") == EXPECTED_TRAJECTORIES, "C capture accepted count changed")
    require(document.get("capture_package_count") == EXPECTED_TRAJECTORIES, "C capture package count changed")
    require(document.get("expected_model_frame_count") == EXPECTED_FRAME_KEYS, "C model-frame count changed")
    require(document.get("person_b_oracle_eligible_count") == 60, "C oracle-eligible count changed")
    require(document.get("person_b_oracle_ineligible_count") == 6, "C oracle-ineligible count changed")
    records = document.get("records")
    require(isinstance(records, list) and len(records) == EXPECTED_TRAJECTORIES, "C capture records must contain 66 rows")
    capture_ids = {record.get("trajectory_id") for record in records if isinstance(record, Mapping)}
    require(capture_ids == accepted_ids, "C capture and accepted trajectory identities differ")
    require(sum(int(record.get("frame_count", -1)) for record in records) == EXPECTED_FRAME_KEYS, "C frame counts do not sum to 2468")
    require(all(record.get("frozen_contract_accepted") is True for record in records), "C capture contract has rejected records")


def validate_join_rows(rows: Sequence[Mapping[str, Any]], accepted_ids: set[str]) -> dict[str, Any]:
    require(len(rows) == EXPECTED_FRAME_KEYS, "C joined row count changed")
    keys = {(row.get("trajectory_id"), row.get("model_frame_idx")) for row in rows}
    require(len(keys) == EXPECTED_FRAME_KEYS and all(None not in key for key in keys), "C joined keys are missing or duplicated")
    ordered_keys = [(row.get("trajectory_id"), row.get("model_frame_idx")) for row in rows]
    require(ordered_keys == sorted(ordered_keys), "C joined rows are not deterministically ordered")
    require({row.get("trajectory_id") for row in rows} == accepted_ids, "C joined trajectories differ from accepted set")
    require(all(row.get("label_owner") == "Person C" for row in rows), "C must own visible_flag")
    require(all("geometric_visible" in row and "empirical_magenta_visible" in row for row in rows), "raw channels are not preserved")
    allowed_categories = set(EXPECTED_QUARANTINE_CATEGORIES)
    for row in rows:
        require(isinstance(row.get("trajectory_id"), str), "C row trajectory identity is not a string")
        require(isinstance(row.get("model_frame_idx"), int) and row["model_frame_idx"] >= 0, "C row model-frame identity is invalid")
        require(row.get("visible_flag_rule") == "geometric_visible AND empirical_magenta_visible", "C visibility rule identity changed")
        require(row.get("final_visibility_interface_version") == "person-c-final-visibility-interface-v1.0", "C visibility interface version changed")
        require(isinstance(row.get("quarantine_category"), str) and row["quarantine_category"] in allowed_categories, "C quarantine category is invalid")
        require(isinstance(row.get("quarantined"), bool), "C quarantined field is not boolean")
        applicable = row.get("visibility_applicable") is True
        if applicable:
            require(isinstance(row.get("geometric_visible"), bool), "applicable geometric channel is not boolean")
            require(isinstance(row.get("empirical_magenta_visible"), bool), "applicable empirical channel is not boolean")
            require(row.get("visible_flag_defined") is True, "applicable C row lacks defined flag")
            require(isinstance(row.get("visible_flag"), bool), "applicable visible_flag is not boolean")
            require(row.get("visible_flag") is (row.get("geometric_visible") and row.get("empirical_magenta_visible")), "C AND visibility rule failed")
        else:
            require(row.get("geometric_visible") is None and row.get("empirical_magenta_visible") is None, "not-applicable raw channels must be null")
            require(row.get("visible_flag_defined") is False and row.get("visible_flag") is False, "not-applicable flag semantics changed")
        if row["quarantine_category"] == "invalid_geometry":
            require(not applicable, "invalid-geometry row is marked applicable")
        elif row["quarantine_category"] != "none":
            require(applicable, "applicable quarantine category is not applicable")
    categories = Counter(str(row.get("quarantine_category")) for row in rows)
    observed_categories = {
        category: categories.get(category, 0)
        for category in EXPECTED_QUARANTINE_CATEGORIES
    }
    require(observed_categories == EXPECTED_QUARANTINE_CATEGORIES, f"C quarantine accounting changed: {observed_categories}")
    disagreements = Counter(str(row.get("disagreement_class")) for row in rows)
    require(dict(disagreements) == EXPECTED_DISAGREEMENT_CLASSES, f"C disagreement accounting changed: {dict(disagreements)}")
    for row in rows:
        category = row.get("quarantine_category")
        if category == "none":
            require(row.get("quarantined") is False, "none category must not be quarantined")
        else:
            require(row.get("quarantined") is True and row.get("visible_flag") is False, "quarantined row is not fail-closed")
    require(sum(1 for row in rows if row.get("visibility_applicable") is True) == EXPECTED_APPLICABLE, "applicable count changed")
    require(sum(1 for row in rows if row.get("visibility_applicable") is False) == EXPECTED_NOT_APPLICABLE, "not-applicable count changed")
    require(sum(1 for row in rows if row.get("visible_flag") is True) == EXPECTED_VISIBLE, "visible count changed")
    require(sum(1 for row in rows if row.get("visibility_applicable") is True and row.get("visible_flag") is False) == EXPECTED_HIDDEN, "applicable hidden count changed")
    require(sum(1 for row in rows if row.get("quarantined") is True) == EXPECTED_QUARANTINED, "quarantine count changed")
    by_layout = Counter(str(row.get("layout_id")) for row in rows)
    require(dict(by_layout) == EXPECTED_LAYOUT_ROWS, f"C per-layout counts changed: {dict(by_layout)}")
    return {
        "row_count": len(rows),
        "unique_primary_key_count": len(keys),
        "trajectory_count": len(accepted_ids),
        "applicable_count": EXPECTED_APPLICABLE,
        "not_applicable_count": EXPECTED_NOT_APPLICABLE,
        "visible_count": EXPECTED_VISIBLE,
        "applicable_hidden_count": EXPECTED_HIDDEN,
        "quarantined_count": EXPECTED_QUARANTINED,
        "quarantine_categories": dict(sorted(observed_categories.items())),
        "disagreement_classes": dict(sorted(disagreements.items())),
        "per_layout_row_counts": dict(sorted(by_layout.items())),
    }


def validate_authority_binding(document: Mapping[str, Any], repository_root: Path) -> None:
    """Validate the checked-in B binding before trusting external authorities."""

    require(document.get("schema_version") == "1.0", "B authority binding schema changed")
    require(document.get("owner") == "person_b", "B authority owner changed")
    accepted = document.get("accepted_data_authority")
    require(isinstance(accepted, Mapping), "B accepted-data authority is missing")
    require(accepted.get("accepted_count") == EXPECTED_TRAJECTORIES, "B accepted count binding changed")
    require(accepted.get("trajectory_count") == EXPECTED_TRAJECTORIES, "B trajectory count binding changed")
    require(accepted.get("commit") == PERSON_C_ACCEPTED_MANIFEST_COMMIT, "B accepted-manifest commit binding changed")
    require(accepted.get("path") == PERSON_C_ACCEPTED_MANIFEST_PATH, "B accepted-manifest path binding changed")
    require(accepted.get("sha256") == PERSON_C_ACCEPTED_MANIFEST_SHA256, "B accepted-manifest hash binding changed")
    require(accepted.get("source_commit") == "c836641c894c88e3add207ef2190a2db88726024", "B accepted-manifest source binding changed")
    require(document.get("person_c_authority_commit") == PERSON_C_AUTHORITY_COMMIT, "B C authority commit binding changed")
    require(document.get("person_c_producer_commit") == PERSON_C_PRODUCER_COMMIT, "B C producer commit binding changed")
    e_authority = document.get("person_e_authority")
    require(isinstance(e_authority, Mapping), "B E authority binding is missing")
    require(e_authority.get("commit") == PERSON_E_COMMIT and e_authority.get("records_sha256") == PERSON_E_RECORDS_SHA256, "B E authority binding changed")
    cosign = document.get("coordinate_signoff")
    require(isinstance(cosign, Mapping), "B coordinate signoff is missing")
    require(cosign.get("person_b") is True and cosign.get("person_c") is True, "B/C coordinate signoffs are incomplete")
    require(cosign.get("person_b_commit") == PERSON_B_COSIGN_COMMIT, "B coordinate cosign commit changed")
    require(cosign.get("person_b_sha256") == PERSON_B_COSIGN_SHA256, "B coordinate cosign hash changed")
    strict = document.get("strict_visibility_authority")
    require(isinstance(strict, Mapping), "B strict visibility authority is missing")
    expected_artifacts = {
        "capture_manifest": (PERSON_C_CAPTURE_MANIFEST_PATH, PERSON_C_CAPTURE_MANIFEST_SHA256, PERSON_C_CAPTURE_MANIFEST_SIZE),
        "oracle_handoff": (PERSON_C_ORACLE_HANDOFF_PATH, PERSON_C_ORACLE_HANDOFF_SHA256, PERSON_C_ORACLE_HANDOFF_SIZE),
        "visibility_join_manifest": (PERSON_C_JOIN_MANIFEST_PATH, PERSON_C_JOIN_MANIFEST_SHA256, PERSON_C_JOIN_MANIFEST_SIZE),
        "visibility_join": (PERSON_C_JOIN_PATH, PERSON_C_JOIN_SHA256, PERSON_C_JOIN_SIZE),
        "geometry_table": (PERSON_C_GEOMETRIC_PATH, PERSON_C_GEOMETRIC_SHA256, PERSON_C_GEOMETRIC_SIZE),
        "event_table": (PERSON_C_EVENT_PATH, PERSON_C_EVENT_SHA256, PERSON_C_EVENT_SIZE),
        "disagreement_ledger": (PERSON_C_DISAGREEMENT_PATH, PERSON_C_DISAGREEMENT_SHA256, PERSON_C_DISAGREEMENT_SIZE),
        "closure_receipt": (PERSON_C_CLOSURE_PATH, PERSON_C_CLOSURE_SHA256, PERSON_C_CLOSURE_SIZE),
        "u4_finding": (PERSON_C_U4_FINDING_PATH, PERSON_C_U4_FINDING_SHA256, PERSON_C_U4_FINDING_SIZE),
    }
    for name, (path, digest, size) in expected_artifacts.items():
        record = strict.get(name)
        require(isinstance(record, Mapping), f"B strict authority record is missing: {name}")
        require(record.get("path") == path and record.get("sha256") == digest and record.get("byte_size") == size, f"B strict authority binding changed: {name}")
    require(document.get("u4_output_inspected") is False, "B authority claims U4 inspection")


def validate_authority(repository_root: Path) -> dict[str, Any]:
    binding_payload = (repository_root / PACKAGE_DIRECTORY / "authority_binding.json").read_bytes()
    validate_authority_binding(strict_json(binding_payload, "B authority binding"), repository_root)
    accepted_payload = read_git_blob(repository_root, PERSON_C_ACCEPTED_MANIFEST_COMMIT, PERSON_C_ACCEPTED_MANIFEST_PATH, PERSON_C_ACCEPTED_MANIFEST_SHA256)
    accepted = strict_json(accepted_payload, "C accepted manifest")
    accepted_ids = validate_accepted_manifest(accepted)
    capture_payload = read_git_blob(repository_root, PERSON_C_AUTHORITY_COMMIT, PERSON_C_CAPTURE_MANIFEST_PATH, PERSON_C_CAPTURE_MANIFEST_SHA256)
    require(len(capture_payload) == PERSON_C_CAPTURE_MANIFEST_SIZE, "C capture manifest byte size changed")
    validate_capture_manifest(strict_json(capture_payload, "C capture manifest"), accepted_ids)
    handoff_payload = read_git_blob(repository_root, PERSON_C_AUTHORITY_COMMIT, PERSON_C_ORACLE_HANDOFF_PATH, PERSON_C_ORACLE_HANDOFF_SHA256)
    require(len(handoff_payload) == PERSON_C_ORACLE_HANDOFF_SIZE, "C oracle handoff byte size changed")
    handoff = strict_json(handoff_payload, "C oracle handoff")
    require(handoff.get("C_TO_B_ORACLE_INPUT_READY") is True, "C oracle inputs are not ready")
    require(handoff.get("person_c_generated_person_b_target_values") is False and handoff.get("person_c_modified_person_b_oracle_logic") is False, "C must not author B targets or logic")
    require(handoff.get("rewrites_frozen_c7_5_authority") is False, "C rewrote its accepted authority")
    require(handoff.get("person_c_accepted_manifest", {}).get("sha256") == PERSON_C_ACCEPTED_MANIFEST_SHA256, "C handoff accepted-manifest binding changed")
    require(handoff.get("frame_universe", {}).get("model_frame_key_count") == EXPECTED_FRAME_KEYS, "C frame universe changed")
    require(handoff.get("coordinate_authority", {}).get("adapter_signoff") == {"person_b": True, "person_c": True}, "coordinate cosigns are incomplete")
    require(handoff.get("empirical_visibility_binding", {}).get("person_e_commit") == PERSON_E_COMMIT, "E authority changed")
    require(handoff.get("empirical_visibility_binding", {}).get("records_sha256") == PERSON_E_RECORDS_SHA256, "E records binding changed")
    join_manifest_payload = read_git_blob(repository_root, PERSON_C_AUTHORITY_COMMIT, PERSON_C_JOIN_MANIFEST_PATH, PERSON_C_JOIN_MANIFEST_SHA256)
    require(len(join_manifest_payload) == PERSON_C_JOIN_MANIFEST_SIZE, "C join manifest byte size changed")
    join_manifest = strict_json(join_manifest_payload, "C visibility join manifest")
    require(join_manifest.get("VISIBILITY_JOIN_COMPLETE") is True and join_manifest.get("trajectory_count") == EXPECTED_TRAJECTORIES, "C strict join is incomplete")
    require(join_manifest.get("sources", {}).get("person_c_accepted_manifest_sha256") == PERSON_C_ACCEPTED_MANIFEST_SHA256, "C join manifest accepted binding changed")
    join_payload = read_git_blob(repository_root, PERSON_C_AUTHORITY_COMMIT, PERSON_C_JOIN_PATH, PERSON_C_JOIN_SHA256)
    require(len(join_payload) == PERSON_C_JOIN_SIZE, "C visibility join byte size changed")
    rows = strict_jsonl(join_payload, "C visibility join")
    summary = validate_join_rows(rows, accepted_ids)
    geometric_payload = read_git_blob(repository_root, PERSON_C_AUTHORITY_COMMIT, PERSON_C_GEOMETRIC_PATH, PERSON_C_GEOMETRIC_SHA256)
    require(len(geometric_payload) == PERSON_C_GEOMETRIC_SIZE, "C geometric table byte size changed")
    event_payload = read_git_blob(repository_root, PERSON_C_AUTHORITY_COMMIT, PERSON_C_EVENT_PATH, PERSON_C_EVENT_SHA256)
    require(len(event_payload) == PERSON_C_EVENT_SIZE, "C event table byte size changed")
    events = strict_jsonl(event_payload, "C event table")
    require(len(events) == 55, "C event table count changed")
    require(sum(1 for row in events if row.get("valid_terminal_reveal") is True) == 0, "C reports an unexpected terminal reveal")
    disagreement_payload = read_git_blob(repository_root, PERSON_C_AUTHORITY_COMMIT, PERSON_C_DISAGREEMENT_PATH, PERSON_C_DISAGREEMENT_SHA256)
    require(len(disagreement_payload) == PERSON_C_DISAGREEMENT_SIZE, "C disagreement ledger byte size changed")
    closure_payload = read_git_blob(repository_root, PERSON_C_AUTHORITY_COMMIT, PERSON_C_CLOSURE_PATH, PERSON_C_CLOSURE_SHA256)
    require(len(closure_payload) == PERSON_C_CLOSURE_SIZE, "C closure receipt byte size changed")
    closure = strict_json(closure_payload, "C closure receipt")
    require(closure.get("VISIBILITY_JOIN_COMPLETE") is True and closure.get("accepted_trajectory_count") == EXPECTED_TRAJECTORIES, "C closure receipt is incomplete")
    u4_payload = read_git_blob(repository_root, PERSON_C_AUTHORITY_COMMIT, PERSON_C_U4_FINDING_PATH, PERSON_C_U4_FINDING_SHA256)
    require(len(u4_payload) == PERSON_C_U4_FINDING_SIZE, "C U4 finding byte size changed")
    u4 = strict_json(u4_payload, "C U4 finding")
    require(u4.get("CURRENT_66_CELL_U4_REVEAL_ELIGIBLE") is False and u4.get("U4_SUPPLEMENTAL_CAPTURE_REQUIRED") is True, "C U4 finding changed")
    a_frame_map_payload = read_git_blob(repository_root, PERSON_A_COMMIT, PERSON_A_FRAME_MAP_INVENTORY_PATH, PERSON_A_FRAME_MAP_INVENTORY_SHA256)
    require(len(a_frame_map_payload) == PERSON_A_FRAME_MAP_INVENTORY_SIZE, "A frame-map inventory byte size changed")
    e_records_payload = read_git_blob(repository_root, PERSON_E_COMMIT, PERSON_E_RECORDS_PATH, PERSON_E_RECORDS_SHA256)
    require(len(e_records_payload) == PERSON_E_RECORDS_SIZE, "E empirical records byte size changed")
    e_records = strict_jsonl(e_records_payload, "E empirical visibility records")
    require(len(e_records) == EXPECTED_FRAME_KEYS, "E empirical record count changed")
    e_keys = {(row.get("trajectory_id"), row.get("model_frame_idx")) for row in e_records}
    require(len(e_keys) == EXPECTED_FRAME_KEYS and all(None not in key for key in e_keys), "E empirical keys are missing or duplicated")
    require(all("visible_flag" not in row for row in e_records), "E must not own visible_flag")
    require(all(row.get("c_accepted_manifest_sha256") == PERSON_C_ACCEPTED_MANIFEST_SHA256 for row in e_records), "E accepted-manifest binding changed")
    cosign_payload = read_git_blob(repository_root, PERSON_B_COSIGN_COMMIT, PERSON_B_COSIGN_PATH, PERSON_B_COSIGN_SHA256)
    cosign_doc = strict_json(cosign_payload, "B coordinate cosign")
    cosign_signoff = cosign_doc.get("adapter_signoff")
    require(isinstance(cosign_signoff, Mapping), "B coordinate cosign signoff is missing")
    require(cosign_signoff.get("person_b") is True and cosign_signoff.get("person_c") is True, "B coordinate cosign signoffs changed")
    require(cosign_doc.get("layout_count") == 6 and cosign_doc.get("layout_ids") == ["layout_01", "layout_02", "layout_03", "layout_04", "layout_05", "layout_06"], "B coordinate cosign layout binding changed")
    coordinate_payload = read_git_blob(repository_root, PERSON_C_COORDINATE_AUTHORITY_COMMIT, PERSON_C_COORDINATE_AUTHORITY_PATH, PERSON_C_COORDINATE_AUTHORITY_SHA256)
    coordinate_doc = strict_json(coordinate_payload, "C coordinate authority")
    require(coordinate_doc.get("person_b_cosign_present") is False and coordinate_doc.get("person_b_cosign_required_before_live_use") is True, "C coordinate authority was rewritten by B")
    return {
        "person_c_authority_commit": PERSON_C_AUTHORITY_COMMIT,
        "person_c_producer_commit": PERSON_C_PRODUCER_COMMIT,
        "person_c_accepted_manifest_commit": PERSON_C_ACCEPTED_MANIFEST_COMMIT,
        "accepted_manifest_sha256": PERSON_C_ACCEPTED_MANIFEST_SHA256,
        "accepted_trajectory_count": EXPECTED_TRAJECTORIES,
        "frame_key_count": EXPECTED_FRAME_KEYS,
        "visibility": summary,
        "c_to_b_oracle_input_ready": True,
        "u4_output_inspected": False,
        "terminal_reveal_count": 0,
    }


def canonical_json_file(path: Path) -> Any:
    payload = path.read_bytes()
    value = strict_json(payload, str(path))
    require(payload == canonical_json_bytes(value), f"{path} is not canonical JSON")
    return value


def validate_package(repository_root: Path, package_root: Path | None = None) -> dict[str, Any]:
    root = package_root or repository_root / PACKAGE_DIRECTORY
    require(root.is_dir(), f"missing package directory: {root}")
    observed = tuple(sorted(path.name for path in root.iterdir() if path.is_file()))
    require(observed == tuple(sorted(PACKAGE_FILES)), f"package scope changed: {observed}")
    documents = {name: canonical_json_file(root / name) for name in PACKAGE_FILES}
    inventory = documents["sha256_inventory.json"]
    require(inventory.get("files") and set(inventory["files"]) == set(PACKAGE_FILES) - {"sha256_inventory.json"}, "inventory scope is incomplete")
    for name, record in inventory["files"].items():
        require(record.get("sha256") == sha256_bytes((root / name).read_bytes()), f"inventory hash mismatch for {name}")
        require(record.get("byte_size") == (root / name).stat().st_size, f"inventory size mismatch for {name}")
    evidence = validate_authority(repository_root)
    receipt = documents["c_consumer_validation_receipt.json"]
    require(receipt.get("decision") == "PASS" and receipt.get("accepted_manifest_sha256") == PERSON_C_ACCEPTED_MANIFEST_SHA256, "consumer receipt is not bound to C authority")
    require(receipt.get("u4_output_inspected") is False, "U4 inspection is forbidden")
    status = documents["phase3_status.json"]
    recommendation = documents["phase3_closure_recommendation.json"]
    require(status.get("step_3_3_final_joined_package_validation") == "PASS", "Step 3.3 remains pending")
    require(status.get("phase3_formally_closed") is False and status.get("overall_phase_3") == "IN_PROGRESS", "phase3 status must remain fail-closed")
    require(recommendation.get("phase3_closure_recommendation") == "READY", "closure recommendation is not READY")
    require(recommendation.get("independent_final_verification") == "PENDING", "independent verification must remain pending")
    return {"evidence": evidence, "receipt": receipt, "phase3_status": status, "closure_recommendation": recommendation}


__all__ = [
    "EXPECTED_FRAME_KEYS",
    "EXPECTED_TRAJECTORIES",
    "PACKAGE_DIRECTORY",
    "PACKAGE_FILES",
    "PERSON_C_ACCEPTED_MANIFEST_SHA256",
    "PERSON_C_AUTHORITY_COMMIT",
    "Phase3ValidationError",
    "canonical_json_bytes",
    "read_git_blob",
    "strict_json",
    "strict_jsonl",
    "validate_authority",
    "validate_authority_binding",
    "validate_join_rows",
    "validate_package",
]
