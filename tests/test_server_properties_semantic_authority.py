from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AUTHORITY = REPO / "fabric/mineocclude-mod/provisioning/person-c-c1-v0_2/server.properties"
RUNTIME = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\server.properties")
VALIDATOR = REPO / "scripts/person_c/validate-server-properties-authority.ps1"
REPAIR_DIR = REPO / "docs/status/person_c_e_refit_calibration_finalizer_server_properties_repair_v0_1"
FIXTURES = REPO / "tests/fixtures/server_properties_semantic_authority"
MINIMAL_AUTHORITY = FIXTURES / "authority.properties"


def run_validator(runtime: Path, authority: Path = AUTHORITY) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(VALIDATOR),
            "-AuthorityPath",
            str(authority),
            "-RuntimePath",
            str(runtime),
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def assert_fixture_rejected(name: str, expected_message: str) -> None:
    result = run_validator(FIXTURES / name, MINIMAL_AUTHORITY)
    assert result.returncode != 0
    assert expected_message in (result.stdout + result.stderr)


def test_exact_preparation_authority_file_passes() -> None:
    result = run_validator(AUTHORITY)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["drift_classification"] == "EXACT_SEMANTIC_AUTHORITY_MATCH"
    assert receipt["raw_files_identical"] is True
    assert receipt["shared_property_count"] == 49


def test_preparation_plus_only_two_minecraft_expansion_keys_passes() -> None:
    result = run_validator(RUNTIME)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["drift_classification"] == "MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION"
    assert receipt["allowed_additional_keys_present"] == ["query.port", "text-filtering-config"]
    assert receipt["unexpected_additional_keys"] == []


def test_changed_authoritative_value_fails() -> None:
    assert_fixture_rejected("changed-authoritative-value.properties", "Changed authoritative")


def test_whitespace_padded_authoritative_value_fails() -> None:
    assert_fixture_rejected("whitespace-padded-value.properties", "Changed authoritative")


def test_missing_authoritative_property_fails() -> None:
    assert_fixture_rejected("missing-authoritative-property.properties", "Missing authoritative")


def test_unknown_additional_property_fails() -> None:
    assert_fixture_rejected("unknown-additional-property.properties", "Unexpected additional")


def test_duplicate_property_fails() -> None:
    assert_fixture_rejected("duplicate-property.properties", "Duplicate server.properties key")


def test_malformed_non_comment_line_fails() -> None:
    assert_fixture_rejected("malformed-line.properties", "Malformed non-comment")


def test_query_port_different_from_server_port_fails() -> None:
    assert_fixture_rejected("query-port-mismatch.properties", "query.port must equal server-port")


def test_nonempty_text_filtering_config_fails() -> None:
    assert_fixture_rejected("nonempty-text-filtering.properties", "text-filtering-config must be empty")


def test_spawn_animals_true_fails() -> None:
    assert_fixture_rejected("spawn-animals-true.properties", "Changed authoritative")


def test_current_runtime_and_additive_repair_receipt_are_exact() -> None:
    result = run_validator(RUNTIME)
    assert result.returncode == 0, result.stdout + result.stderr
    semantic = json.loads(result.stdout)
    assert semantic["authority"]["raw_sha256"] == "8d6495e9e4c2aa3dfad783d863a3b03165cbe233564e5717aac38a5ebc5ed651"
    assert semantic["authority"]["canonical_semantic_sha256"] == "9d17905ca3ad56adf8c6464e1b06d6396bde9c890c55a0853c61ab39ef3a4f28"
    assert semantic["shared_property_values_match"] is True
    receipt = json.loads((REPAIR_DIR / "repair_receipt.json").read_text(encoding="utf-8"))
    assert receipt["semantic_comparison"]["authority"]["raw_sha256"] == semantic["authority"]["raw_sha256"]
    assert receipt["semantic_comparison"]["authority"]["canonical_semantic_sha256"] == semantic["authority"]["canonical_semantic_sha256"]
    assert receipt["semantic_comparison"]["shared_property_values_match"] is True
    assert receipt["server_properties_validator_repair_ready"] is True
    assert receipt["full_finalization_ready"] is False
    assert receipt["unresolved_blockers"] == [
        "CALIBRATION_SCREENSHOTS_ARE_640X360_BUT_FINALIZER_REQUIRES_1920X1046"
    ]
    evidence = receipt["completed_calibration_evidence"]
    assert evidence["screenshot_dimensions_match_finalizer_requirement"] is False
    assert {(row["width_pixels"], row["height_pixels"]) for row in evidence["raw_screenshots"]} == {(640, 360)}
    for name in ("successor_finalizer", "semantic_validator", "authority_baseline"):
        row = receipt[name]
        path = REPO / row["path"]
        assert path.stat().st_size == row["size_bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]


def test_finalizer_uses_semantic_validator_and_records_raw_runtime_hash() -> None:
    finalizer = (REPO / "scripts/person_c/finalize-e-refit-calibration-v0-4.ps1").read_text()
    assert "$serverPropertiesSha256" not in finalizer
    assert "Compare-ServerPropertiesAuthority" in finalizer
    assert "server_properties_authority_validation = $serverPropertiesComparison" in finalizer
    assert "MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION" in finalizer


def test_additive_repair_package_inventory_is_complete_and_hash_bound() -> None:
    inventory = json.loads((REPAIR_DIR / "sha256_inventory.json").read_text(encoding="utf-8"))
    assert inventory["self_excluded"] == "sha256_inventory.json"
    assert {Path(row["path"]).name for row in inventory["files"]} == {
        "README.md",
        "repair_receipt.json",
        "validation_receipt.json",
    }
    for row in inventory["files"]:
        path = REPO / row["path"]
        data = path.read_bytes()
        assert len(data) == row["size_bytes"]
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
