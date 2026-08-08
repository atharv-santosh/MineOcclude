"""Dedicated validator for the Person D Phase 4 Step 4.1 registry v2 handoff.

This does not fit, generate, or accept any scientific baseline. It only
checks that the preparation package under
``docs/status/person_d_phase4_step4_1_registry_v2_handoff_v0_1/`` is
internally consistent: every JSON file is valid and canonical
(``json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\\n"``
reproduces the file byte-for-byte), the corrected Person B branch name
appears where required, the job is recorded as blocked, no accepted
baseline or promoted placeholder exists anywhere in the package, the
forbidden preview's bound hash still matches its live file, and (once
present) ``sha256_inventory.json`` matches every other package file's
actual on-disk hash.

Usage:
    python scripts/validate_person_d_phase4_step4_1_registry_v2_handoff_v0_1.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = (
    ROOT / "docs" / "status" / "person_d_phase4_step4_1_registry_v2_handoff_v0_1"
)
INVENTORY_PATH = PACKAGE_DIR / "sha256_inventory.json"
PREVIEW_PATH = ROOT / "docs" / "status" / "person_d_real_pilot_baseline_preview.json"

NEW_JSON_FILES = (
    "authority_binding.json",
    "production_job_status.json",
    "scientific_baseline_input_contract.json",
    "baseline_artifact_contract.json",
    "registry_v2_handoff_templates.json",
    "readiness_gate_contract.json",
    "forbidden_preview_guard.json",
    "execution_runbook.json",
    "validation_receipt.json",
)


class HandoffValidationError(ValueError):
    """Raised when the preparation package fails a consistency check."""


def _canonical_bytes(obj: object) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise HandoffValidationError(f"{path}: invalid JSON: {error}") from error


def check_json_canonical(path: Path) -> None:
    obj = _load_json(path)
    on_disk = path.read_bytes()
    if _canonical_bytes(obj) != on_disk:
        raise HandoffValidationError(
            f"{path}: not canonical (sort_keys=True, indent=2 re-serialization differs)"
        )


def check_new_files_exist_and_are_canonical() -> list[str]:
    checked = []
    for name in NEW_JSON_FILES:
        path = PACKAGE_DIR / name
        if not path.exists():
            raise HandoffValidationError(f"required file missing: {path}")
        check_json_canonical(path)
        checked.append(name)
    return checked


def check_authority_binding() -> None:
    doc = _load_json(PACKAGE_DIR / "authority_binding.json")
    person_b = doc.get("person_b", {})
    if person_b.get("corrected_branch") != "role/person-b-analysis":
        raise HandoffValidationError(
            "authority_binding.json: person_b.corrected_branch must be "
            "'role/person-b-analysis'"
        )
    if person_b.get("task_stated_branch") != "role/person-b-methods":
        raise HandoffValidationError(
            "authority_binding.json: must record the originally-stated (incorrect) "
            "branch name for audit purposes"
        )
    person_e = doc.get("person_e", {})
    if person_e.get("registry_v2_contract_authority") != (
        "25509bb4ba292a83d933058539aca1ca6002524a"
    ):
        raise HandoffValidationError("authority_binding.json: wrong Person E contract authority")
    if person_e.get("registry_v2_query_authority") != (
        "5d8660c90fbf7362d7f32005f9b650e15ae1bfb5"
    ):
        raise HandoffValidationError("authority_binding.json: wrong Person E query authority")
    claims = doc.get("claims", {})
    required_true = (
        "no_scientific_baseline_was_executed",
        "no_accepted_baseline_exists",
        "existing_preview_remains_forbidden",
        "no_project_integration_is_claimed",
        "no_u4_output_was_inspected",
    )
    for claim in required_true:
        if claims.get(claim) is not True:
            raise HandoffValidationError(f"authority_binding.json: claims.{claim} must be true")


def check_production_job_status() -> None:
    doc = _load_json(PACKAGE_DIR / "production_job_status.json")
    if doc.get("status") != "blocked":
        raise HandoffValidationError("production_job_status.json: status must be 'blocked'")
    if doc.get("output_artifact_id") is not None or doc.get("output_sha256") is not None:
        raise HandoffValidationError(
            "production_job_status.json: a blocked job must not publish an output artifact"
        )
    blockers = doc.get("required_blockers", [])
    codes = {blocker.get("reason_code") for blocker in blockers}
    required_codes = {
        "committed_authoritative_person_b_handoff_unavailable",
        "sealed_fold_membership_unavailable",
        "actual_oracle_target_unavailable",
        "exact_accepted_upstream_identities_unavailable",
    }
    missing = required_codes - codes
    if missing:
        raise HandoffValidationError(
            f"production_job_status.json: missing required blocker reason_codes: {sorted(missing)}"
        )


def check_forbidden_preview_guard() -> None:
    doc = _load_json(PACKAGE_DIR / "forbidden_preview_guard.json")
    bound = doc.get("bound_artifact", {})
    if bound.get("scientific_use") != "forbidden":
        raise HandoffValidationError("forbidden_preview_guard.json: scientific_use must be 'forbidden'")
    if not PREVIEW_PATH.exists():
        raise HandoffValidationError(f"bound preview file missing: {PREVIEW_PATH}")
    live_sha256 = hashlib.sha256(PREVIEW_PATH.read_bytes()).hexdigest()
    if bound.get("literal_sha256") != live_sha256:
        raise HandoffValidationError(
            "forbidden_preview_guard.json: bound literal_sha256 does not match the live "
            f"preview file (bound={bound.get('literal_sha256')!r}, live={live_sha256!r}); "
            "the preview may have been edited since this guard was recorded"
        )


def check_no_accepted_baseline_or_promoted_placeholder() -> tuple[int, int]:
    """Scan every JSON file for an accepted baseline or a placeholder promoted to real.

    Returns (accepted_baseline_count, accepted_placeholder_count).
    """

    accepted_baseline_count = 0
    accepted_placeholder_count = 0
    for path in sorted(PACKAGE_DIR.rglob("*.json")):
        if path.name == "sha256_inventory.json":
            continue
        doc = _load_json(path)
        text = json.dumps(doc)
        if (
            '"job_id": "person_d_produce_scientific_baseline_prediction_documents"' in text
            and '"status": "accepted"' in text
        ):
            accepted_baseline_count += 1
        if path.name in (
            "registry_v2_handoff_templates.json",
        ):
            flat = json.dumps(doc)
            if '"owner_status": "accepted"' in flat or '"decision": "accepted"' in flat:
                accepted_placeholder_count += 1
    return accepted_baseline_count, accepted_placeholder_count


def check_sha256_inventory_if_present() -> None:
    if not INVENTORY_PATH.exists():
        return
    inventory = _load_json(INVENTORY_PATH)
    entries = inventory.get("files", {})
    on_disk = {
        str(path.relative_to(PACKAGE_DIR))
        for path in sorted(PACKAGE_DIR.rglob("*"))
        if path.is_file() and path != INVENTORY_PATH
    }
    recorded = set(entries)
    if recorded != on_disk:
        raise HandoffValidationError(
            "sha256_inventory.json: recorded file set does not match on-disk files. "
            f"missing_from_inventory={sorted(on_disk - recorded)}, "
            f"stale_in_inventory={sorted(recorded - on_disk)}"
        )
    for relative_path, expected_sha256 in entries.items():
        actual = hashlib.sha256((PACKAGE_DIR / relative_path).read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise HandoffValidationError(
                f"sha256_inventory.json: hash mismatch for {relative_path} "
                f"(recorded={expected_sha256}, actual={actual})"
            )


def main() -> int:
    try:
        run_all_checks()
    except HandoffValidationError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


def run_all_checks() -> list[str]:
    checked = check_new_files_exist_and_are_canonical()
    check_authority_binding()
    check_production_job_status()
    check_forbidden_preview_guard()
    accepted_baseline_count, accepted_placeholder_count = (
        check_no_accepted_baseline_or_promoted_placeholder()
    )
    if accepted_baseline_count != 0:
        raise HandoffValidationError(
            f"found {accepted_baseline_count} accepted baseline record(s); expected 0"
        )
    if accepted_placeholder_count != 0:
        raise HandoffValidationError(
            f"found {accepted_placeholder_count} template promoted to accepted; expected 0"
        )
    check_sha256_inventory_if_present()
    print(f"OK: {len(checked)} required files present and canonical.")
    print("OK: authority_binding.json branch/authority/claims correct.")
    print("OK: production_job_status.json is blocked with all required reason codes.")
    print("OK: forbidden_preview_guard.json hash matches the live preview file.")
    print(f"OK: accepted_baseline_count={accepted_baseline_count}, "
          f"accepted_placeholder_count={accepted_placeholder_count}.")
    if INVENTORY_PATH.exists():
        print("OK: sha256_inventory.json matches on-disk package files.")
    else:
        print("SKIP: sha256_inventory.json not yet written.")
    return checked


if __name__ == "__main__":
    raise SystemExit(main())
