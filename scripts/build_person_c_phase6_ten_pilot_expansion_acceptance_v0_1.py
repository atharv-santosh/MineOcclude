"""Build Person C's exact Phase 6 ten-pilot expansion input acceptance.

This is a preparation-only owner decision.  It reads Person B's selection from
the exact Git object, validates every selected capture and every referenced
artifact byte, preserves the existing layout_00_ep9403 acceptance, and builds
one complete Registry v2 trust chain for the nine newly accepted inputs.
It never authorizes Person A execution and never inspects U4.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mineocclude.data.capture_contract import validate_capture_package

import build_person_c_phase4_step4_1_registry_v2_handoff_v0_1 as single


SCHEMA_ID = "person-c-phase6-ten-pilot-expansion-acceptance-v0-1"
PKG_REL = "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1"
PERSON_B_SELECTION_COMMIT = "19f08b2e27217b781961da8f7299e1396a3ab703"
PERSON_B_SELECTION_REL = (
    "docs/status/person_b_phase6_ten_pilot_expansion_selection_v0_1/"
    "expansion_selection_manifest.json"
)
PERSON_C_STARTING_AUTHORITY = "f0d4e895b56fc4ca3f4805aa13b73545744af1b0"
PERSON_E_REGISTRY_V2 = "b27d404c6aa913bac559754fa8b7accdff46e886"
EXISTING_PILOT = "layout_00_ep9403"
EXISTING_ACCEPTANCE_REL = (
    "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1/"
    "selected_pilot_acceptance.json"
)
DECISION_TIMESTAMP = "2026-07-31T00:00:00Z"

EXPECTED_ORDER = [
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
]
EXPECTED_CONTROLS = [
    "layout_00_ep9441",
    "layout_01_ep9442",
    "layout_02_ep9432",
    "layout_03_ep9443",
    "layout_04_ep9444",
]


class ExpansionAcceptanceError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ExpansionAcceptanceError(message)


def canon(document) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_show(spec: str) -> bytes:
    return subprocess.check_output(["git", "-C", ROOT, "show", spec])


def _resolve_artifact_path(declared_path: str) -> str:
    expanded = os.path.expanduser(declared_path)
    if os.path.isfile(expanded):
        return expanded
    normalized = declared_path.replace("\\", "/")
    marker = "/data/autonomous/"
    if marker in normalized:
        relative = "data/autonomous/" + normalized.split(marker, 1)[1]
        candidate = os.path.join(ROOT, *relative.split("/"))
        if os.path.isfile(candidate):
            return candidate
    fail(f"referenced capture artifact is missing: {declared_path}")
    raise AssertionError("unreachable")


def _verify_capture(selected: dict) -> tuple[bytes, dict, dict]:
    pilot_id = selected["trajectory_id"]
    capture = selected["capture_package"]
    spec = f"{PERSON_C_STARTING_AUTHORITY}:{capture['path']}"
    raw = git_show(spec)
    if len(raw) != capture["byte_size"] or sha256_bytes(raw) != capture["sha256"]:
        fail(f"Person B capture identity drift for {pilot_id}")
    working_path = os.path.join(ROOT, *capture["path"].split("/"))
    with open(working_path, "rb") as handle:
        if handle.read() != raw:
            fail(f"working capture differs from exact C Git object for {pilot_id}")
    sidecar = git_show(f"{PERSON_C_STARTING_AUTHORITY}:{capture['path']}.sha256")
    if sidecar.decode("ascii").strip() != capture["sha256"]:
        fail(f"capture checksum sidecar drift for {pilot_id}")

    package = json.loads(raw)
    result = validate_capture_package(package)
    if not result.accepted:
        reasons = "; ".join(f"{r.code.value}: {r.message}" for r in result.rejections)
        fail(f"strict capture validation failed for {pilot_id}: {reasons}")
    if package.get("trajectory_id") != pilot_id:
        fail(f"capture trajectory identity mismatch for {pilot_id}")
    if not isinstance(package.get("seed"), int):
        fail(f"capture seed is not an integer for {pilot_id}")

    required = {
        "media",
        "raw_actions",
        "normalized_actions",
        "server_state",
        "frame_map",
        "visibility",
        "config",
        "seed_noise",
        "seed_noise_source",
    }
    missing = sorted(required - set(package["artifacts"]))
    if missing:
        fail(f"capture artifact roles missing for {pilot_id}: {missing}")

    byte_verified_roles = required - {"config", "seed_noise_source"}
    verified_artifacts = {}
    for role in sorted(byte_verified_roles):
        artifact = package["artifacts"][role]
        physical_path = _resolve_artifact_path(artifact["path"])
        with open(physical_path, "rb") as handle:
            artifact_bytes = handle.read()
        if sha256_bytes(artifact_bytes) != artifact["sha256"]:
            fail(f"artifact checksum mismatch for {pilot_id}:{role}")
        verified_artifacts[role] = {
            "byte_size": len(artifact_bytes),
            "declared_path": artifact["path"],
            "format": artifact["format"],
            "sha256": artifact["sha256"],
        }

    manifest = package["episode_manifest"]
    if manifest["config_hash"] != package["artifacts"]["config"]["sha256"]:
        fail(f"config hash binding mismatch for {pilot_id}")
    if package["seed"] != manifest["seed"]:
        fail(f"seed binding mismatch for {pilot_id}")
    if manifest["noise_schedule_hash"] != package["artifacts"]["seed_noise"]["sha256"]:
        fail(f"seed schedule hash binding mismatch for {pilot_id}")

    frame_count = package["media"]["frame_count"]
    for stream_name in (
        "raw_actions",
        "normalized_actions",
        "server_state",
        "frame_map",
        "visibility",
    ):
        if len(package["streams"][stream_name]) != frame_count:
            fail(f"stream cardinality mismatch for {pilot_id}:{stream_name}")

    intake = {
        "acceptance_kind": (
            "existing_acceptance_revalidated"
            if pilot_id == EXISTING_PILOT
            else "new_expansion_acceptance"
        ),
        "capture_package_byte_size": len(raw),
        "capture_package_path": capture["path"],
        "capture_package_sha256": sha256_bytes(raw),
        "condition_role": selected["condition_role"],
        "control": selected["control"],
        "fold_idx": selected["fold_idx"],
        "frame_count": frame_count,
        "layout_id": selected["layout_id"],
        "order": selected["order"],
        "seed": package["seed"],
        "sealed_declared_artifacts": {
            role: {
                "declared_path": artifact["path"],
                "format": artifact["format"],
                "sha256": artifact["sha256"],
            }
            for role, artifact in sorted(package["artifacts"].items())
        },
        "strict_capture_validator_accepted": True,
        "trajectory_id": pilot_id,
        "verified_artifacts": verified_artifacts,
    }
    return raw, package, intake


def _load_and_validate_selection() -> tuple[bytes, dict]:
    raw = git_show(f"{PERSON_B_SELECTION_COMMIT}:{PERSON_B_SELECTION_REL}")
    selection = json.loads(raw)
    order = selection["ordered_pilot_ids"]
    if order != EXPECTED_ORDER:
        fail("exact Person B ordered pilot set changed")
    if selection["no_wall_control_pilot_ids"] != EXPECTED_CONTROLS:
        fail("exact Person B no-wall control set changed")
    if selection["selection_semantics"]["total_expansion_pilot_count"] != 10:
        fail("Person B total pilot count is not ten")
    if selection["selection_semantics"]["additional_pilot_count"] != 9:
        fail("Person B additional pilot count is not nine")
    if selection["source_authorities"]["person_c_exact_source_commit"] != PERSON_C_STARTING_AUTHORITY:
        fail("Person B does not bind the exact C starting authority")
    if [p["trajectory_id"] for p in selection["pilots"]] != order:
        fail("Person B detailed pilot rows do not preserve declared order")
    return raw, selection


def _merge_registry_chains(chains: list[tuple]) -> tuple[dict, dict, dict]:
    document = {
        "artifacts": [],
        "byte_verifications": [],
        "immutable_registry_schema_version": "mineocclude-immutable-registry-v2.0",
        "manifests": [],
        "owner_authorities": [],
        "registry_id": "person_c_phase6_ten_pilot_expansion_new_inputs_v0_1",
        "runs": [],
        "schema_version": "1.0",
        "scientific_use": "permitted",
        "synthetic": False,
    }
    trusted = {
        "trusted_owner_authorities": {},
        "trusted_status_record_bytes": {},
        "trusted_artifact_authorizations": {},
        "trusted_authorization_record_bytes": {},
        "trusted_manifest_records": {},
        "trusted_artifact_receipts": None,
    }
    artifact_bytes = {}
    for pilot_id, pilot_bytes, chain_doc, chain_trusted in chains:
        for key in ("artifacts", "byte_verifications", "manifests", "owner_authorities", "runs"):
            document[key].extend(chain_doc[key])
        for key in (
            "trusted_owner_authorities",
            "trusted_status_record_bytes",
            "trusted_artifact_authorizations",
            "trusted_authorization_record_bytes",
            "trusted_manifest_records",
        ):
            overlap = set(trusted[key]) & set(chain_trusted[key])
            if overlap:
                fail(f"Registry v2 trust identity collision: {sorted(overlap)}")
            trusted[key].update(chain_trusted[key])
        artifact_bytes[pilot_id] = pilot_bytes
    return document, trusted, artifact_bytes


def _verify_combined_registry(e_module, document, trusted, artifact_bytes) -> None:
    status_bytes = {
        key: value.encode("utf-8")
        for key, value in trusted["trusted_status_record_bytes"].items()
    }
    authorization_bytes = {
        key: value.encode("utf-8")
        for key, value in trusted["trusted_authorization_record_bytes"].items()
    }
    result = e_module.validate_immutable_run_artifact_registry(
        document,
        artifact_bytes_by_id=artifact_bytes,
        trusted_owner_authorities=trusted["trusted_owner_authorities"],
        trusted_status_record_bytes=status_bytes,
        trusted_artifact_authorizations=trusted["trusted_artifact_authorizations"],
        trusted_authorization_record_bytes=authorization_bytes,
        trusted_manifest_records=trusted["trusted_manifest_records"],
        trusted_artifact_receipts=None,
    )
    if not result.accepted:
        reasons = "; ".join(f"{r.code.value}: {r.message}" for r in result.rejections)
        fail(f"combined Registry v2 validation failed: {reasons}")


def generate(out_dir: str | None = None) -> dict[str, bytes]:
    selection_bytes, selection = _load_and_validate_selection()
    e_module, e_validator_sha = single.load_e_validator()

    intakes = []
    raw_by_id = {}
    package_by_id = {}
    for selected in selection["pilots"]:
        raw, package, intake = _verify_capture(selected)
        pilot_id = selected["trajectory_id"]
        raw_by_id[pilot_id] = raw
        package_by_id[pilot_id] = package
        intakes.append(intake)

    existing_bytes = git_show(
        f"{PERSON_C_STARTING_AUTHORITY}:{EXISTING_ACCEPTANCE_REL}"
    )
    existing_acceptance = json.loads(existing_bytes)
    existing_row = intakes[0]
    if (
        existing_acceptance["trajectory_id"] != EXISTING_PILOT
        or existing_acceptance["git_object_sha256"]
        != existing_row["capture_package_sha256"]
        or existing_acceptance["byte_size"]
        != existing_row["capture_package_byte_size"]
    ):
        fail("existing single-pilot acceptance no longer binds layout_00_ep9403")

    chains = []
    newly_accepted = EXPECTED_ORDER[1:]
    prior_single_authority = single.PERSON_C_AUTHORITY
    single.PERSON_C_AUTHORITY = PERSON_C_STARTING_AUTHORITY
    try:
        for pilot_id in newly_accepted:
            intake = next(row for row in intakes if row["trajectory_id"] == pilot_id)
            package = package_by_id[pilot_id]
            document, trusted, _status, _authorization, _ids = single.build_registry(
                pilot_id,
                intake["capture_package_sha256"],
                intake["capture_package_byte_size"],
                raw_by_id[pilot_id],
                package,
            )
            chains.append((pilot_id, raw_by_id[pilot_id], document, trusted))
    finally:
        single.PERSON_C_AUTHORITY = prior_single_authority

    registry_document, trusted_inputs, artifact_bytes = _merge_registry_chains(chains)
    _verify_combined_registry(e_module, registry_document, trusted_inputs, artifact_bytes)

    files: dict[str, bytes] = {}
    files["authority_binding.json"] = canon({
        "schema_id": f"{SCHEMA_ID}-authority-binding",
        "schema_version": "1.0",
        "person_b_selection": {
            "commit": PERSON_B_SELECTION_COMMIT,
            "path": PERSON_B_SELECTION_REL,
            "sha256": sha256_bytes(selection_bytes),
        },
        "person_c_branch": "role/person-c-data",
        "person_c_starting_authority": PERSON_C_STARTING_AUTHORITY,
        "person_e_registry_v2_authority": {
            "commit": PERSON_E_REGISTRY_V2,
            "frozen_validator_sha256": e_validator_sha,
        },
        "person_a_expansion_execution_authorized": False,
        "u4_output_inspected": False,
    })
    files["accepted_pilot_manifest.json"] = canon({
        "schema_id": f"{SCHEMA_ID}-accepted-pilot-manifest",
        "schema_version": "1.0",
        "accepted_pilot_count": 10,
        "accepted_placeholder_count": 0,
        "existing_acceptance_count": 1,
        "newly_accepted_pilot_count": 9,
        "ordered_pilot_ids": EXPECTED_ORDER,
        "intake_rows": intakes,
    })
    files["existing_pilot_acceptance_binding.json"] = canon({
        "schema_id": f"{SCHEMA_ID}-existing-pilot-acceptance-binding",
        "schema_version": "1.0",
        "decision_duplicated": False,
        "existing_acceptance_commit": PERSON_C_STARTING_AUTHORITY,
        "existing_acceptance_path": EXISTING_ACCEPTANCE_REL,
        "existing_acceptance_sha256": sha256_bytes(existing_bytes),
        "capture_package_sha256": existing_row["capture_package_sha256"],
        "status": "BOUND_TO_EXISTING_ACCEPTANCE",
        "trajectory_id": EXISTING_PILOT,
    })
    files["expansion_acceptance_decision.json"] = canon({
        "schema_id": f"{SCHEMA_ID}-decision",
        "schema_version": "1.0",
        "decision": "ACCEPT_EXACT_PERSON_B_TEN_PILOT_EXPANSION_INPUTS",
        "decision_timestamp": DECISION_TIMESTAMP,
        "owner": "person_c",
        "owner_authority_commit": PERSON_C_STARTING_AUTHORITY,
        "ordered_accepted_pilot_ids": EXPECTED_ORDER,
        "newly_accepted_pilot_ids": newly_accepted,
        "no_wall_control_pilot_ids": EXPECTED_CONTROLS,
        "existing_pilot_acceptance_preserved": True,
        "accepted_pilot_count": 10,
        "accepted_placeholder_count": 0,
        "scope": "exact_phase6_ten_pilot_expansion_inputs_for_steps_6_1_through_6_5",
        "scientific_use": "accepted_as_exact_expansion_inputs",
        "person_a_expansion_execution_authorized": False,
        "hidden_state_interpretation_authorized": False,
        "step_6_6_complete": False,
        "u4_output_inspected": False,
    })
    files["registry_v2_document.json"] = canon({
        "schema_id": f"{SCHEMA_ID}-registry-v2-document",
        "schema_version": "1.0",
        "coverage": "nine_newly_accepted_pilots_existing_pilot_bound_separately",
        "immutable_registry_document": registry_document,
    })
    files["registry_v2_trusted_verification_inputs.json"] = canon({
        "schema_id": f"{SCHEMA_ID}-registry-v2-trusted-verification-inputs",
        "schema_version": "1.0",
        "artifact_bytes_sources": [
            {
                "artifact_id": pilot_id,
                "path": next(
                    row["capture_package_path"]
                    for row in intakes
                    if row["trajectory_id"] == pilot_id
                ),
                "sha256": sha256_bytes(raw_by_id[pilot_id]),
                "size_bytes": len(raw_by_id[pilot_id]),
            }
            for pilot_id in newly_accepted
        ],
        "trusted_inputs": trusted_inputs,
        "verifier": {
            "commit": PERSON_E_REGISTRY_V2,
            "frozen_validator_sha256": e_validator_sha,
            "result": "ACCEPTED_ZERO_REJECTIONS",
        },
    })
    files["validation_receipt.json"] = canon({
        "schema_id": f"{SCHEMA_ID}-validation-receipt",
        "schema_version": "1.0",
        "status": "PASS",
        "accepted_pilot_count": 10,
        "accepted_placeholder_count": 0,
        "all_capture_packages_match_b_hashes_and_sizes": True,
        "all_capture_sidecars_match": True,
        "all_required_pilots_accepted": True,
        "all_required_artifact_bytes_verified": True,
        "all_declared_artifact_identities_sealed_by_capture_package": True,
        "config_hash_and_seed_bindings_verified": True,
        "all_strict_capture_validators_accepted": True,
        "b_order_preserved": True,
        "complete_registry_v2_trust_chain_new_pilot_count": 9,
        "exact_five_no_wall_controls_accepted": True,
        "existing_acceptance_decision_duplicated": False,
        "existing_pilot_bound_to_prior_acceptance": True,
        "person_a_expansion_execution_authorized": False,
        "u4_output_inspected": False,
    })

    inventory = {name: sha256_bytes(data) for name, data in sorted(files.items())}
    files["sha256_inventory.json"] = canon({
        "schema_id": f"{SCHEMA_ID}-sha256-inventory",
        "schema_version": "1.0",
        "file_count": len(files) + 1,
        "files": inventory,
        "inventory_excludes_self": True,
    })

    if out_dir is not None:
        os.makedirs(out_dir, exist_ok=True)
        for relative, data in files.items():
            destination = os.path.join(out_dir, relative)
            with open(destination, "wb") as handle:
                handle.write(data)
    return files


def validate(package_dir: str) -> None:
    expected = generate(out_dir=None)
    present = set(os.listdir(package_dir)) if os.path.isdir(package_dir) else set()
    if present != set(expected):
        fail(
            f"acceptance package file set mismatch: expected {sorted(expected)}, "
            f"found {sorted(present)}"
        )
    for relative, data in expected.items():
        with open(os.path.join(package_dir, relative), "rb") as handle:
            if handle.read() != data:
                fail(f"acceptance package byte drift: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--out-dir", default=os.path.join(ROOT, PKG_REL))
    args = parser.parse_args()
    try:
        if args.mode == "build":
            files = generate(args.out_dir)
            print(f"BUILD OK: {len(files)} artifacts; 10 accepted pilots; 0 placeholders")
        else:
            validate(args.out_dir)
            print("VALIDATE OK: exact ten-pilot expansion acceptance")
    except ExpansionAcceptanceError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
