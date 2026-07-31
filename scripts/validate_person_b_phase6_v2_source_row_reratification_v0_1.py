"""Validate the additive Person B source-row canonicalization ratification."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PACKAGE_ROOT = (
    "docs/status/"
    "person_b_phase6_v2_source_row_canonicalization_reratification_v0_1"
)
PERSON_A_COMMIT = "55776dc88302b89b52eef483a710fbf6811cf536"
IMPLEMENTATION_COMMIT = "c6f2d1d3495fa1b4a567408e1a84a5b5484e5ecb"
SUPERSEDED_RATIFICATION_COMMIT = "03e8cdb8673f2260f42b8554b00ac30e3e4f7c8b"
SOURCE_ARTIFACT_TYPE = "person_a_activation_store_v2_source_row"
SOURCE_CANONICALIZATION_CONTRACT = (
    "person-a-activation-store-v2-canonical-json@"
    "55776dc88302b89b52eef483a710fbf6811cf536"
)
SOURCE_DIGEST_DOMAIN = (
    "person-a-activation-store-v2-source-row-entire-mapping-sha256-v1"
)
PACKAGE_FILES = (
    "activation_evidence_binding.json",
    "authority_binding.json",
    "owner_reratification.json",
    "preflight_failure_record.json",
    "real_visible_control_regression_receipt.json",
    "sha256_inventory.json",
    "source_row_canonicalization_contract.json",
    "superseding_execution_authorization.json",
    "validation_receipt.json",
)


class RatificationValidationError(ValueError):
    """Fail-closed ratification validation error."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RatificationValidationError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
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


def _git_blob(repository: Path, commit: str, path: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), "show", f"{commit}:{path}"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise RatificationValidationError(
            f"Could not read exact Git object {commit}:{path}: {error}"
        ) from error


def _package_blob(
    repository: Path,
    filename: str,
    *,
    ratification_commit: str | None,
) -> bytes:
    path = f"{PACKAGE_ROOT}/{filename}"
    if ratification_commit is not None:
        return _git_blob(repository, ratification_commit, path)
    try:
        return (repository / path).read_bytes()
    except OSError as error:
        raise RatificationValidationError(f"Could not read {path}: {error}") from error


def _strict_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            _require(key not in result, f"{label} repeats JSON key {key!r}.")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(
                RatificationValidationError(
                    f"{label} contains non-finite constant {item!r}."
                )
            ),
        )
    except RatificationValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RatificationValidationError(f"{label} is invalid JSON: {error}") from error
    _require(isinstance(value, Mapping), f"{label} must be a JSON object.")
    _require(payload == _canonical_json_bytes(value), f"{label} is not canonical JSON.")
    return value


def _load_package(
    repository: Path,
    *,
    ratification_commit: str | None,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, bytes]]:
    raw = {
        filename: _package_blob(
            repository,
            filename,
            ratification_commit=ratification_commit,
        )
        for filename in PACKAGE_FILES
    }
    documents = {
        filename: _strict_json(payload, label=filename)
        for filename, payload in raw.items()
    }
    return documents, raw


def _validate_inventory(
    documents: Mapping[str, Mapping[str, Any]],
    raw: Mapping[str, bytes],
) -> None:
    inventory = documents["sha256_inventory.json"]
    expected_names = set(PACKAGE_FILES) - {"sha256_inventory.json"}
    _require(inventory.get("inventory_excludes_self") is True, "Inventory self rule")
    files = inventory.get("files")
    _require(isinstance(files, Mapping), "Inventory files must be an object.")
    _require(set(files) == expected_names, "Inventory file set differs.")
    for filename in expected_names:
        _require(files[filename] == _sha256(raw[filename]), f"Hash mismatch: {filename}")


def _validate_owner(repository: Path, documents: Mapping[str, Mapping[str, Any]]) -> None:
    owner = documents["owner_reratification.json"]
    expected = {
        "authorized_execution": "person_b_frozen_visible_position_positive_control_only",
        "decision": "RERATIFY_EXACT_V2_SOURCE_ROW_CANONICALIZATION_CONSUMER",
        "e_schema_change_required": False,
        "exact_source_identity_join_pass": True,
        "hidden_state_interpretation_authorized": False,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "person_a_ten_pilot_commit": PERSON_A_COMMIT,
        "previous_execution_authorization_superseded": True,
        "real_visible_control_rows_matched": 1_000,
        "real_visible_control_rows_tested": 1_000,
        "registry_canonicalization_scope": "registry_v2_owned_records_only",
        "registry_digest_substitution_count": 0,
        "source_row_artifact_type": SOURCE_ARTIFACT_TYPE,
        "source_row_canonicalization_contract": SOURCE_CANONICALIZATION_CONTRACT,
        "source_row_digest_domain": SOURCE_DIGEST_DOMAIN,
        "source_row_producer_commit": PERSON_A_COMMIT,
        "supersedes_ratification_commit": SUPERSEDED_RATIFICATION_COMMIT,
        "u4_output_inspected": False,
    }
    _require(
        all(owner.get(key) == value for key, value in expected.items()),
        "Owner ratification boundary differs.",
    )
    implementation_files = owner.get("implementation_files")
    _require(
        isinstance(implementation_files, list) and len(implementation_files) == 5,
        "Owner must bind five implementation files.",
    )
    for binding in implementation_files:
        _require(isinstance(binding, Mapping), "Implementation binding malformed.")
        path = binding.get("path")
        _require(isinstance(path, str), "Implementation path missing.")
        payload = _git_blob(repository, IMPLEMENTATION_COMMIT, path)
        _require(binding.get("byte_size") == len(payload), f"Byte size mismatch: {path}")
        _require(binding.get("sha256") == _sha256(payload), f"SHA mismatch: {path}")


def _validate_source_contract(documents: Mapping[str, Mapping[str, Any]]) -> None:
    contract = documents["source_row_canonicalization_contract.json"]
    expected = {
        "artifact_type": SOURCE_ARTIFACT_TYPE,
        "canonicalization_contract": SOURCE_CANONICALIZATION_CONTRACT,
        "digest_algorithm": "sha256",
        "digest_domain": SOURCE_DIGEST_DOMAIN,
        "digest_prefix": None,
        "excluded_fields": [],
        "person_a_bytes_may_be_modified": False,
        "person_a_producer_commit": PERSON_A_COMMIT,
        "registry_canonicalization_scope": "registry_v2_owned_records_only",
        "registry_digest_substitution_allowed": False,
        "unknown_or_contradictory_dispatch": "fail_closed",
    }
    _require(
        all(contract.get(key) == value for key, value in expected.items()),
        "Source-row contract differs.",
    )
    encoding = contract.get("json_encoding")
    _require(
        isinstance(encoding, Mapping)
        and encoding.get("allow_nan") is False
        and encoding.get("ensure_ascii") is False
        and encoding.get("indent") == 2
        and encoding.get("key_order") == "sorted_lexicographically"
        and encoding.get("separators") == "python_json_indent_2_defaults"
        and encoding.get("text_encoding") == "utf-8"
        and encoding.get("trailing_newline_count") == 1,
        "Person A encoding differs.",
    )


def _validate_activation_binding(
    repository: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    binding = documents["activation_evidence_binding.json"]
    pilots = binding.get("per_pilot_bindings")
    _require(isinstance(pilots, list) and len(pilots) == 10, "Ten pilots required.")
    total_rows = 0
    total_chunks = 0
    manifests: set[str] = set()
    for row in pilots:
        _require(isinstance(row, Mapping), "Pilot binding malformed.")
        path = row.get("inventory_git_object")
        _require(isinstance(path, str), "Inventory path missing.")
        payload = _git_blob(repository, PERSON_A_COMMIT, path)
        _require(row.get("inventory_byte_size") == len(payload), "Inventory size")
        _require(row.get("inventory_raw_sha256") == _sha256(payload), "Inventory SHA")
        inventory = _strict_json(payload, label=path)
        index = inventory.get("activation_index")
        chunks = inventory.get("chunks")
        _require(isinstance(index, Mapping), "Activation index binding missing.")
        _require(isinstance(chunks, list) and len(chunks) == 20, "Twenty chunks required.")
        _require(index.get("sha256") == row.get("activation_index_sha256"), "Index SHA")
        _require(index.get("byte_size") == row.get("activation_index_byte_size"), "Index size")
        _require(inventory.get("trajectory_id") == row.get("pilot_id"), "Pilot ID")
        index_path = Path(str(index.get("path")))
        _require(index_path.is_file() and not index_path.is_symlink(), "Index file")
        index_payload = index_path.read_bytes()
        _require(len(index_payload) == index.get("byte_size"), "External index size")
        _require(_sha256(index_payload) == index.get("sha256"), "External index SHA")
        index_document = _strict_json(index_payload, label=str(index_path))
        _require(index_document.get("snapshot_id") == row.get("snapshot_id"), "Snapshot")
        store_identity = index_document.get("store_identity")
        _require(isinstance(store_identity, Mapping), "Store identity missing.")
        total_rows += int(inventory["activation_row_count"])
        total_chunks += len(chunks)
        manifests.add(str(store_identity["accepted_manifest_hash"]))
    _require(total_rows == 37_480, "Activation row total differs.")
    _require(total_chunks == 200, "Activation chunk total differs.")
    _require(len(manifests) == 10, "Accepted manifests are not distinct.")
    _require(binding.get("combined_identity_set_equals_per_pilot_union") is True, "Union")


def _validate_receipts(documents: Mapping[str, Mapping[str, Any]]) -> None:
    failure = documents["preflight_failure_record.json"]
    _require(failure.get("probe_fit_executed") is False, "Prior fit must be false.")
    _require(failure.get("positive_control_output_created") is False, "Prior output")
    _require(failure.get("immutable_person_a_digest_match_count") == 1_000, "Prior match")
    _require(failure.get("registry_compact_digest_match_count") == 0, "Prior compact")
    regression = documents["real_visible_control_regression_receipt.json"]
    expected = {
        "activation_chunk_count_verified": 200,
        "activation_index_count_verified": 10,
        "activation_row_count_verified": 37_480,
        "exact_source_identity_join_pass": True,
        "frozen_fold_unchanged": True,
        "frozen_target_unchanged": True,
        "frozen_threshold_unchanged": True,
        "hidden_row_count": 0,
        "layout_fold_group_count": 5,
        "no_wall_trajectory_count": 5,
        "probe_fit_executed": False,
        "random_split_used": False,
        "registry_digest_substitution_count": 0,
        "scientific_decision_produced": False,
        "status": "PASS",
        "u4_output_inspected": False,
        "visible_control_rows_matched": 1_000,
        "visible_control_rows_tested": 1_000,
    }
    _require(
        all(regression.get(key) == value for key, value in expected.items()),
        "Real regression receipt differs.",
    )
    authorization = documents["superseding_execution_authorization.json"]
    _require(
        authorization.get("supersedes_ratification_commit")
        == SUPERSEDED_RATIFICATION_COMMIT
        and authorization.get("positive_control_execution_authorized") is True
        and authorization.get("hidden_state_interpretation_authorized") is False
        and authorization.get("u4_output_inspected") is False,
        "Execution authorization differs.",
    )
    receipt = documents["validation_receipt.json"]
    _require(
        receipt.get("status") == "PASS"
        and receipt.get("focused_tests_pass") is True
        and receipt.get("focused_test_count") == 44
        and receipt.get("e_schema_change_required") is False,
        "Validation receipt differs.",
    )


def validate(repository: Path, *, ratification_commit: str | None) -> dict[str, Any]:
    documents, raw = _load_package(
        repository,
        ratification_commit=ratification_commit,
    )
    _validate_inventory(documents, raw)
    _validate_owner(repository, documents)
    _validate_source_contract(documents)
    _validate_activation_binding(repository, documents)
    _validate_receipts(documents)
    runner_path = "scripts/run_person_b_phase6_v2_positive_control_sagemaker.py"
    runner = (
        _git_blob(repository, ratification_commit, runner_path)
        if ratification_commit is not None
        else (repository / runner_path).read_bytes()
    )
    _require(
        documents["owner_reratification.json"].get(
            "ratification_guard_runner_sha256"
        )
        == _sha256(runner),
        "Ratification guard runner SHA differs.",
    )
    return {
        "activation_chunk_count": 200,
        "activation_index_count": 10,
        "activation_row_count": 37_480,
        "e_schema_change_required": False,
        "exact_source_identity_join_pass": True,
        "registry_digest_substitution_count": 0,
        "status": "PASS",
        "visible_control_row_count": 1_000,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--ratification-commit")
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    result = validate(
        arguments.repository_root.resolve(),
        ratification_commit=arguments.ratification_commit,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
