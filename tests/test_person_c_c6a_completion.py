from __future__ import annotations

import gzip
from functools import lru_cache
from pathlib import Path

from scripts.person_c.certify_c6a_completion import (
    AUTHORIZATION_COMMIT,
    CANONICAL_ID,
    CLIENT,
    E_HANDOFF_SHA256,
    E_PACKAGE_SHA256,
    GEOMETRY_SHA256,
    JAR_SHA256,
    PACKAGE_DIR,
    PERSON_E_COMMIT,
    ROOT,
    SERVER,
    bundle_digest,
    load_json,
    sha256,
    validate_runtime,
)


@lru_cache(maxsize=1)
def _runtime() -> dict:
    return validate_runtime()


def test_manifest_runtime_and_episode_completion_are_valid() -> None:
    validation = _runtime()
    assert len(validation["episodes"]) == 66
    assert [row["episode_id"] for row in validation["episodes"]] == list(range(12601, 12667))
    assert all(row["status"] == "PASS" for row in validation["episodes"])
    assert all(row["target_check_valid"] for row in validation["episodes"])
    assert all(row["recording_started"] and row["recording_completed"] for row in validation["episodes"])
    assert all(
        row["server_row_count"]
        == row["client_tick_count"]
        == row["action_row_count"]
        == row["frame_count"]
        == row["completed_record_ticks"]
        for row in validation["episodes"]
    )


def test_schedule_inventory_binds_all_immutable_schedules() -> None:
    inventory = load_json(PACKAGE_DIR / "schedule_inventory.json")
    assert inventory["schedule_count"] == 66
    assert inventory["schedules"] == _runtime()["schedules"]
    for row in inventory["schedules"]:
        for key in ("repository", "runtime_install"):
            path = ROOT / row[key]["path"] if key == "repository" else Path(row[key]["path"])
            assert path.stat().st_size == row[key]["size_bytes"]
            assert sha256(path) == row[key]["sha256"]


def test_output_schema_counts_and_inventory_are_valid() -> None:
    inventory = load_json(PACKAGE_DIR / "output_inventory.json")
    assert inventory["episode_count"] == 66
    assert inventory["files"] == _runtime()["output_files"]
    assert inventory["file_count"] == len(inventory["files"])
    assert inventory["total_size_bytes"] == sum(row["size_bytes"] for row in inventory["files"])
    assert inventory["output_bundle_sha256"] == bundle_digest(inventory["files"])
    for row in inventory["files"]:
        path = Path(row["path"])
        assert path.stat().st_size == row["size_bytes"]
        assert sha256(path) == row["sha256"]


def test_candidate_chronology_prior_abort_and_shutdown_are_bound() -> None:
    receipt = load_json(PACKAGE_DIR / "c6a_completion_receipt.json")
    episode_inventory = load_json(PACKAGE_DIR / "episode_inventory.json")
    assert receipt["status"] == "PASS"
    assert receipt["earlier_12601_warmup_abort_distinguished"] is True
    assert receipt["server_shutdown_clean"] is True
    assert receipt["client_shutdown_clean"] is True
    assert episode_inventory["episodes"] == _runtime()["episodes"]
    first = episode_inventory["episodes"][0]
    server_events = first["server_log_line_numbers"]
    assert server_events["start"] < server_events["schedule_load"] < server_events["armed"] < server_events["recording_started"] < server_events["completed"]
    assert any(path.endswith("2026-08-04-3.log.gz") for path in receipt["earlier_12601_warmup_abort_logs"])
    with gzip.open(PACKAGE_DIR / "server_latest.log.gz", "rb") as archived:
        assert archived.read() == (SERVER / "logs/latest.log").read_bytes()
    with gzip.open(PACKAGE_DIR / "client_latest.log.gz", "rb") as archived:
        assert archived.read() == (CLIENT / "logs/latest.log").read_bytes()


def test_package_sha256_inventory_is_complete_and_content_bound() -> None:
    package = load_json(PACKAGE_DIR / "package_manifest.json")
    inventory = load_json(PACKAGE_DIR / "sha256_inventory.json")
    assert package["canonical_c6a_id"] == CANONICAL_ID
    assert package["status"] == "PASS"
    assert package["required_episode_count"] == package["completed_episode_count"] == 66
    assert package["evidence_bundle_sha256"] == bundle_digest(package["component_files"])
    assert inventory["package_bundle_sha256"] == bundle_digest(inventory["files"])
    for row in inventory["files"]:
        path = ROOT / row["path"]
        assert path.stat().st_size == row["size_bytes"]
        assert sha256(path) == row["sha256"]


def test_canonical_identity_and_person_c_to_e_handoff_are_exact() -> None:
    canonical = load_json(PACKAGE_DIR / "canonical_c6a_identity.json")
    handoff = load_json(PACKAGE_DIR / "person_c_to_person_e_c6a_provenance_handoff.json")
    assert canonical["canonical_c6a_id"] == CANONICAL_ID
    assert canonical["status"] == "CANONICAL"
    assert canonical["person_e_registry_closure_performed"] is False
    assert handoff["status"] == "READY_FOR_PERSON_E_PROVENANCE_INGESTION"
    assert handoff["person_e_registry_closure_performed"] is False
    assert handoff["person_c_authorization_commit"] == AUTHORIZATION_COMMIT
    assert handoff["person_e_refit_commit"] == PERSON_E_COMMIT
    assert handoff["person_e_refit_package_sha256"] == E_PACKAGE_SHA256
    assert handoff["person_e_to_person_c_refit_handoff_sha256"] == E_HANDOFF_SHA256
    assert handoff["accepted_geometry"]["sha256"] == GEOMETRY_SHA256
    assert handoff["repaired_jar_sha256"] == JAR_SHA256
    assert handoff["required_episode_count"] == handoff["completed_episode_count"] == 66
    assert handoff["unresolved_blockers"] == []
