from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mineocclude.data.noise_schedule import generate_noise_schedule, serialize_schedule
from scripts.person_c.prepare_e_refit_calibration_v0_4 import (
    CLIENT,
    CLIENT_EVIDENCE_DIR,
    DOC_DIR,
    EPISODES,
    FRAMEBUFFER,
    GEOMETRY,
    GEOMETRY_SHA256,
    GEOMETRY_VERSION,
    JAR_SHA256,
    MARKER_ORDER,
    RECORD_TICKS,
    REPO,
    REPO_SCHEDULE_DIR,
    RUNTIME_SCHEDULE_DIR,
    SERVER,
    SERVER_EVIDENCE_DIR,
    WARMUP_TICKS,
    marker_rows,
    validation_points,
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_package_inventory() -> str:
    inventory = load(DOC_DIR / "sha256_inventory.json")
    assert inventory["schema_version"] == "person-c-package-sha256-inventory-v1.0"
    assert inventory["self_excluded"] == "sha256_inventory.json"
    rows = inventory["files"]
    for row in rows:
        path = REPO / row["path"]
        assert path.is_file()
        assert path.stat().st_size == row["size_bytes"]
        assert file_hash(path) == row["sha256"]
    bundle = hashlib.sha256(
        "".join(f"{row['path']}\0{row['sha256']}\n" for row in rows).encode()
    ).hexdigest()
    assert bundle == inventory["package_bundle_sha256"]
    return bundle


def test_runtime_authorities_and_closed_c1_gate_are_exact() -> None:
    manifest = load(DOC_DIR / "session_manifest.json")
    runtime = load(DOC_DIR / "runtime_identity.json")
    assert file_hash(GEOMETRY) == GEOMETRY_SHA256
    assert manifest["status"] == "READY_FOR_ONE_AUTHENTICATED_OPERATOR"
    assert manifest["accepted_geometry_version"] == GEOMETRY_VERSION
    assert manifest["accepted_geometry_sha256"] == GEOMETRY_SHA256
    assert manifest["mineocclude_jar_sha256"] == JAR_SHA256
    assert manifest["runtime_schedules_ready"] is True
    assert manifest["runtime_executed_by_preparation"] is False
    assert manifest["scientific_capture"] is False
    assert manifest["c6a_or_c6b"] is False
    assert runtime["spawn_animals"] is False
    assert runtime["fov_degrees"] == 70.0
    assert runtime["framebuffer"] == FRAMEBUFFER
    assert runtime["server_jar"]["sha256"] == JAR_SHA256
    assert runtime["client_jar"]["sha256"] == JAR_SHA256
    assert runtime["client_options"]["sha256"] == "13a43adde78280041f7adc29367b0a61ced6a9549f2430d9083a88665a0d9895"
    closure = load(REPO / "docs/status/person_c_c1_closure_v0_1/c1_closure_status.json")
    assert closure["c1_1_complete"] and closure["c1_3_complete"] and closure["c1_5_complete"]
    assert closure["person_c_c1_stop_gate_closed"] is True


def test_six_episode_seed_schedules_are_new_deterministic_and_installed() -> None:
    assert EPISODES == [
        ("layout_01", 12701, 202608031701),
        ("layout_02", 12702, 202608031702),
        ("layout_03", 12703, 202608031703),
        ("layout_04", 12704, 202608031704),
        ("layout_05", 12705, 202608031705),
        ("layout_06", 12706, 202608031706),
    ]
    assert not {row[1] for row in EPISODES} & set(range(11501, 11507))
    assert not {row[1] for row in EPISODES} & set(range(12601, 12667))
    schedule_manifest = load(
        REPO / "configs/collection/person_c_e_refit_calibration_v0_4_v0_1/schedule_set_manifest.json"
    )
    assert schedule_manifest["schedule_count"] == 6
    assert schedule_manifest["non_scientific_calibration_only"] is True
    for layout_id, episode, seed in EPISODES:
        expected = serialize_schedule(
            generate_noise_schedule(seed=seed, n_draws=RECORD_TICKS, q=0.0)
        )
        repo_schedule = REPO_SCHEDULE_DIR / f"episode_{episode}.jsonl"
        runtime_schedule = RUNTIME_SCHEDULE_DIR / f"episode_{episode}.jsonl"
        assert repo_schedule.read_bytes() == expected
        assert runtime_schedule.read_bytes() == expected
        row = next(item for item in schedule_manifest["schedules"] if item["layout_id"] == layout_id)
        assert row["episode_id"] == episode and row["seed"] == seed
        assert row["record_ticks"] == 20 and row["q"] == 0.0


def test_session_manifest_binds_all_literal_layout_geometry_and_commands() -> None:
    geometry = load(GEOMETRY)
    manifest = load(DOC_DIR / "session_manifest.json")
    assert manifest["layout_count"] == 6
    assert manifest["operator_count_required"] == 1
    assert manifest["session_controls_apply_once_in_order"][-1] == "mineocclude warmup 12000"
    assert len(manifest["layouts"]) == 6
    for source, prepared, (_, episode, seed) in zip(
        geometry["layouts"], manifest["layouts"], EPISODES, strict=True
    ):
        assert prepared["layout_id"] == source["layout_id"]
        assert prepared["episode_id"] == episode and prepared["seed"] == seed
        assert prepared["warmup_ticks"] == WARMUP_TICKS
        assert prepared["record_ticks"] == RECORD_TICKS
        assert prepared["mode"] == "normal" and prepared["duration"] == 0
        assert prepared["reveal"] == 0 and prepared["impulse"] == [-1, 0]
        assert prepared["lockcam"] == "on" and prepared["spawn_animals"] is False
        assert prepared["layout_geometry"]["floor"] == source["floor"]
        assert prepared["layout_geometry"]["wall"] == source["wall"]
        assert prepared["layout_geometry"]["camera"] == source["camera"]
        assert prepared["layout_geometry"]["markers"] == marker_rows(source)
        assert prepared["commands"]["start"] == (
            f"mineocclude start {source['layout_id']} {episode} {seed} 0.0 0.0 20"
        )
        assert prepared["commands"]["observegeometry"] == (
            f"mineocclude observegeometry e_refit_calibration_v0_4_{source['layout_id']}"
        )


def test_all_runtime_evidence_paths_are_fresh_create_only() -> None:
    manifest = load(DOC_DIR / "session_manifest.json")
    for row in manifest["layouts"]:
        assert not Path(row["runtime_paths"]["geometry_receipt"]).exists()
        assert not Path(row["runtime_paths"]["canonical_screenshot"]).exists()
    for path in (
        SERVER_EVIDENCE_DIR / "operator_attestation.json",
        SERVER_EVIDENCE_DIR / "server_latest.log",
        CLIENT_EVIDENCE_DIR / "client_latest.log",
        SERVER_EVIDENCE_DIR / "person_c_to_e_calibration_handoff_v0_4.json",
        SERVER_EVIDENCE_DIR / "finalization_result.json",
    ):
        assert not path.exists()


def test_person_e_templates_have_exact_world_points_and_no_invented_pixels() -> None:
    geometry = load(GEOMETRY)
    refit = load(
        REPO / "docs/status/person_c_to_person_e_homography_refit_v0_1/refit_input_authority.json"
    )
    refit_by_layout = {row["layout_id"]: row for row in refit["layouts"]}
    fit = load(DOC_DIR / "e_image_point_annotation_template.json")
    validation = load(DOC_DIR / "e_independent_validation_pair_template.json")
    assert fit["owner_of_image_coordinates"] == "Person E"
    assert fit["person_c_invented_image_coordinates"] is False
    assert validation["owner_of_image_coordinates_and_visibility_decisions"] == "Person E"
    for source, fit_row, validation_row in zip(
        geometry["layouts"], fit["layouts"], validation["layouts"], strict=True
    ):
        assert [row["marker_id"] for row in fit_row["fit_correspondences"]] == MARKER_ORDER
        assert fit_row["fit_correspondences"] == marker_rows(source)
        assert fit_row["marker_set_source_hash"] == refit_by_layout[source["layout_id"]]["marker_set_source_hash"]
        assert all(row["image_xy_pixels"] is None for row in fit_row["fit_correspondences"])
        assert validation_row["validation_points"] == validation_points(source)
        assert all(row["image_xy_pixels"] is None for row in validation_row["validation_points"])
        marker_points = {tuple(row["world_xz_blocks"]) for row in fit_row["fit_correspondences"]}
        validation_world = {tuple(row["world_xz_blocks"]) for row in validation_row["validation_points"]}
        assert not marker_points & validation_world


def test_coordinate_convention_and_pending_inventories_are_explicit() -> None:
    convention = load(DOC_DIR / "coordinate_convention.json")
    screenshots = load(DOC_DIR / "screenshot_inventory.json")
    receipts = load(DOC_DIR / "geometry_receipt_inventory.json")
    assert convention["image_coordinates"]["convention"] == "pixel_center_xy_zero_based"
    assert convention["image_coordinates"]["valid_x_center_range"] == [0, 1919]
    assert convention["image_coordinates"]["valid_y_center_range"] == [0, 1045]
    assert "invented_image_pixel_coordinates" in convention["forbidden"]
    assert screenshots["status"] == "PENDING_RUNTIME_FINALIZATION"
    assert receipts["status"] == "PENDING_RUNTIME_OBSERVATION"
    assert len(screenshots["screenshots"]) == len(receipts["receipts"]) == 6
    assert all(row["sha256"] is None for row in screenshots["screenshots"])
    assert all(row["sha256"] is None for row in receipts["receipts"])


def test_runbook_and_finalizer_enforce_strict_single_session_without_fitting() -> None:
    runbook = (DOC_DIR / "operator_runbook.md").read_text(encoding="utf-8")
    finalizer = (REPO / "scripts/person_c/finalize-e-refit-calibration-v0-4.ps1").read_text(
        encoding="utf-8"
    )
    for layout_id, episode, seed in EPISODES:
        assert f"mineocclude start {layout_id} {episode} {seed} 0.0 0.0 20" in runbook
        assert f"mineocclude observegeometry e_refit_calibration_v0_4_{layout_id}" in runbook
    assert "episode {0} aborted during warmup" in finalizer
    assert "press F2 exactly once" in runbook
    assert "no pause menu, chat, inventory, or F3 overlay" in runbook
    assert finalizer.count("Read-Host") == 1
    assert "target status: valid=true required=true count=1" in finalizer
    assert "recording started" in finalizer
    assert "Get-PngDimensions" in finalizer
    assert "CreateNew" in finalizer
    assert "scripts/fit_homographies.py" not in finalizer
    assert "person_c_fit_homographies = $false" in finalizer
    assert "run-c6a" not in finalizer.lower()


def test_additive_package_inventory_is_complete_and_valid() -> None:
    assert validate_package_inventory() == "cec7639ee2e8d024bfe3434346f828e32be7aeba00ab241f4e38881be2b74356"
    names = {path.name for path in DOC_DIR.iterdir() if path.is_file()}
    required = {
        "session_manifest.json",
        "runtime_identity.json",
        *(f"layout_{index:02d}_calibration.json" for index in range(1, 7)),
        "screenshot_inventory.json",
        "geometry_receipt_inventory.json",
        "e_image_point_annotation_template.json",
        "e_independent_validation_pair_template.json",
        "coordinate_convention.json",
        "sha256_inventory.json",
        "validation_report.md",
        "operator_runbook.md",
    }
    assert required <= names
