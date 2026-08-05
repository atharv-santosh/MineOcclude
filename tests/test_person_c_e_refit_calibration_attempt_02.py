from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path

from mineocclude.data.noise_schedule import generate_noise_schedule, serialize_schedule
from scripts.person_c.prepare_e_refit_calibration_attempt_02 import (
    ATTEMPT_01_CLASSIFICATION,
    ATTEMPT_NAME,
    CLIENT_EVIDENCE_DIR,
    CONFIG_DIR,
    DOC_DIR,
    EPISODES,
    FRAMEBUFFER_MISMATCH_CAUSE,
    GEOMETRY_SHA256,
    GEOMETRY_VERSION,
    JAR_SHA256,
    KNOWN_GOOD_CLIENT_CONFIGURATION,
    PREFLIGHT_EVIDENCE_PATH,
    PREFLIGHT_RECEIPT_PATH,
    RECORD_TICKS,
    REPO,
    RUNTIME_SCHEDULE_DIR,
    SERVER,
    SERVER_EVIDENCE_DIR,
)


PREFLIGHT_SCRIPT = REPO / "scripts/person_c/verify-e-refit-calibration-attempt-02-framebuffer.ps1"
ATTEMPT_MODULE = REPO / "scripts/person_c/ERefitCalibrationAttempt02Authority.psm1"
FINALIZER = REPO / "scripts/person_c/finalize-e-refit-calibration-v0-4-attempt-02.ps1"
SERVER_PROPERTIES_VALIDATOR = REPO / "scripts/person_c/validate-server-properties-authority.ps1"
SERVER_PROPERTIES_AUTHORITY = REPO / "fabric/mineocclude-mod/provisioning/person-c-c1-v0_2/server.properties"
SERVER_PROPERTIES_RUNTIME = SERVER / "server.properties"
SERVER_PROPERTIES_FIXTURES = REPO / "tests/fixtures/server_properties_semantic_authority"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def minimal_png(width: int, height: int, discriminator: bytes = b"") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + discriminator


def run_powershell_file(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path), *arguments],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def make_preflight_fixture(tmp_path: Path, width: int, height: int) -> tuple[Path, Path, Path, Path, str]:
    client = tmp_path / "client"
    server = tmp_path / "server"
    screenshots = client / "screenshots"
    client_logs = client / "logs"
    server_logs = server / "logs"
    screenshots.mkdir(parents=True)
    client_logs.mkdir(parents=True)
    server_logs.mkdir(parents=True)
    old = screenshots / "old.png"
    old.write_bytes(minimal_png(640, 360, b"old"))
    candidate = screenshots / "preflight.png"
    candidate.write_bytes(minimal_png(width, height, b"preflight"))
    options = client / "options.txt"
    options.write_text(
        "fullscreen:false\nfov:0.0\nguiScale:2\noverrideWidth:0\noverrideHeight:0\n",
        encoding="utf-8",
    )
    (client_logs / "latest.log").write_text(
        "[12:00:00] [main/INFO]: Setting user: TestOperator\n"
        "[12:00:01] [main/INFO]: Connecting to 127.0.0.1, 25565\n"
        "[12:00:02] [main/INFO]: Saved screenshot as preflight.png\n",
        encoding="utf-8",
    )
    (server_logs / "latest.log").write_text("[11:59:59] [Server thread/INFO]: Done\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": "person-c-e-refit-calibration-attempt-02-preflight-screenshot-baseline-v0.1",
                "attempt_name": ATTEMPT_NAME,
                "screenshot_count": 1,
                "screenshots": [
                    {
                        "path": str(old),
                        "size_bytes": old.stat().st_size,
                        "sha256": file_hash(old),
                        "width_pixels": 640,
                        "height_pixels": 360,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return client, server, baseline, tmp_path / "preflight-evidence", file_hash(options)


def run_preflight_fixture(tmp_path: Path, width: int, height: int) -> subprocess.CompletedProcess[str]:
    client, server, baseline, evidence, options_hash = make_preflight_fixture(tmp_path, width, height)
    return run_powershell_file(
        PREFLIGHT_SCRIPT,
        "-RepoRoot",
        str(REPO),
        "-ClientRoot",
        str(client),
        "-ServerRoot",
        str(server),
        "-BaselineInventoryPath",
        str(baseline),
        "-EvidenceDir",
        str(evidence),
        "-ExpectedOptionsSha256",
        options_hash,
    )


def run_layout_assertion(layouts_path: Path, preflight_path: Path) -> subprocess.CompletedProcess[str]:
    command = (
        f"Import-Module -Force -Name '{ATTEMPT_MODULE}'; "
        f"$rows = @((Get-Content -Raw -LiteralPath '{layouts_path}' | ConvertFrom-Json).layouts); "
        f"@(Assert-ERefitAttempt02LayoutScreenshotSet -Layouts $rows -PreflightEvidencePath '{preflight_path}') | ConvertTo-Json -Depth 5"
    )
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def make_layout_fixture(tmp_path: Path) -> tuple[list[dict[str, str]], Path]:
    preflight = tmp_path / "preflight.png"
    preflight.write_bytes(minimal_png(1920, 1046, b"preflight"))
    rows = []
    for index in range(1, 7):
        path = tmp_path / f"layout_{index:02d}.png"
        path.write_bytes(minimal_png(1920, 1046, f"layout-{index}".encode()))
        rows.append({"layout_id": f"layout_{index:02d}", "path": str(path)})
    return rows, preflight


def test_attempt_01_is_preserved_with_exact_required_classification() -> None:
    record = load(DOC_DIR / "attempt_01_failure_record.json")
    assert record["classification"] == ATTEMPT_01_CLASSIFICATION
    assert record["status"] == "FAILED_PRESERVED_UNCERTIFIED"
    assert record["preserved_unchanged"] is True
    assert record["certified"] is False
    assert record["resized_or_upscaled"] is False
    assert record["receipt_count"] == record["raw_screenshot_count"] == 6
    assert {(row["width_pixels"], row["height_pixels"]) for row in record["raw_screenshots"]} == {(640, 360)}
    for row in [*record["geometry_receipts"], *record["raw_screenshots"], *record["logs"]]:
        path = Path(row["path"])
        assert path.is_absolute()
        assert row["size_bytes"] > 0
        assert len(row["sha256"]) == 64


def test_diagnosis_uses_launcher_options_logs_and_known_good_c1_framebuffer() -> None:
    diagnosis = load(DOC_DIR / "framebuffer_diagnosis.json")
    assert diagnosis["status"] == "PASS_DIAGNOSIS"
    assert diagnosis["diagnosed_cause"] == FRAMEBUFFER_MISMATCH_CAUSE
    assert diagnosis["known_good_client_configuration"] == KNOWN_GOOD_CLIENT_CONFIGURATION
    assert diagnosis["pinned_launch_script"]["requested_width_pixels"] == 640
    assert diagnosis["pinned_launch_script"]["requested_height_pixels"] == 360
    assert diagnosis["minecraft_launcher_installation_configuration"]["resolution"] == {
        "width_pixels": 640,
        "height_pixels": 360,
    }
    assert diagnosis["prior_c1_1_success"]["framebuffer"] == {"width_pixels": 1920, "height_pixels": 1046}
    assert diagnosis["prior_c1_1_success"]["fullscreen"] is False
    assert len(diagnosis["prior_c1_5_success_logs_inspected"]) == 2
    assert diagnosis["fullscreen_cause_claimed"] is False
    assert diagnosis["gui_scale_cause_claimed"] is False
    assert diagnosis["windows_scaling_cause_claimed"] is False


def test_attempt_02_requires_all_six_fresh_create_only_layouts_and_schedules() -> None:
    manifest = load(DOC_DIR / "session_manifest.json")
    assert manifest["status"] == "READY_AFTER_MANDATORY_FRAMEBUFFER_PREFLIGHT"
    assert manifest["attempt_name"] == ATTEMPT_NAME
    assert manifest["layout_count"] == len(manifest["layouts"]) == 6
    assert manifest["accepted_geometry_version"] == GEOMETRY_VERSION
    assert manifest["accepted_geometry_sha256"] == GEOMETRY_SHA256
    assert manifest["mineocclude_jar_sha256"] == JAR_SHA256
    assert manifest["framebuffer"] == {"width_pixels": 1920, "height_pixels": 1046}
    assert manifest["fov_degrees"] == 70.0
    for key in ("script",):
        row = manifest["preflight"][key]
        payload = subprocess.run(
            ["git", "cat-file", "blob", row["git_blob"]],
            cwd=REPO,
            check=True,
            capture_output=True,
        ).stdout
        assert len(payload) == row["size_bytes"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]
    for key in ("finalizer", "authority_module", "server_properties_validator"):
        row = manifest[key]
        payload = subprocess.run(
            ["git", "cat-file", "blob", row["git_blob"]],
            cwd=REPO,
            check=True,
            capture_output=True,
        ).stdout
        assert len(payload) == row["size_bytes"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]
    assert EPISODES == [
        ("layout_01", 12711, 202608041701),
        ("layout_02", 12712, 202608041702),
        ("layout_03", 12713, 202608041703),
        ("layout_04", 12714, 202608041704),
        ("layout_05", 12715, 202608041705),
        ("layout_06", 12716, 202608041706),
    ]
    assert [row["layout_id"] for row in manifest["layouts"]] == [f"layout_{index:02d}" for index in range(1, 7)]
    for row, (layout_id, episode, seed) in zip(manifest["layouts"], EPISODES, strict=True):
        assert row["layout_id"] == layout_id and row["episode_id"] == episode and row["seed"] == seed
        assert row["mode"] == "normal" and row["duration"] == row["reveal"] == 0
        assert row["impulse"] == [-1, 0] and row["lockcam"] == "on"
        assert row["warmup_ticks"] == 12000 and row["record_ticks"] == 20
        assert row["spawn_animals"] is False
        assert ATTEMPT_NAME in row["commands"]["observegeometry"]
        assert ATTEMPT_NAME in row["runtime_paths"]["geometry_receipt"]
        assert ATTEMPT_NAME in row["runtime_paths"]["canonical_screenshot"]
        schedule = CONFIG_DIR / "schedules" / f"episode_{episode}.jsonl"
        repo_identity = row["schedule"]["repository_schedule"]
        runtime_identity = row["schedule"]["runtime_schedule"]
        assert file_hash(schedule) == repo_identity["sha256"]
        assert runtime_identity["sha256"] == repo_identity["sha256"]
        assert Path(row["runtime_paths"]["geometry_receipt"]).is_absolute()
        assert Path(row["runtime_paths"]["canonical_screenshot"]).is_absolute()
    assert ATTEMPT_NAME in PREFLIGHT_EVIDENCE_PATH.name
    assert ATTEMPT_NAME in PREFLIGHT_RECEIPT_PATH.name


def test_1920x1046_preflight_passes_and_records_distinct_evidence(tmp_path: Path) -> None:
    result = run_preflight_fixture(tmp_path, 1920, 1046)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FRAMEBUFFER_PREFLIGHT_PASS=True" in result.stdout
    assert "FRAMEBUFFER=1920x1046" in result.stdout
    assert "LAYOUT_SCREENSHOT_ELIGIBLE=False" in result.stdout
    receipt = load(tmp_path / "preflight-evidence" / f"{ATTEMPT_NAME}_framebuffer_preflight_receipt.json")
    assert receipt["status"] == "PASS"
    assert receipt["observed_framebuffer"] == {"width_pixels": 1920, "height_pixels": 1046}
    assert receipt["excluded_from_layout_screenshot_count"] is True
    evidence = Path(receipt["external_preflight_evidence"]["path"])
    assert evidence.is_file() and evidence.parent == tmp_path / "preflight-evidence"
    assert evidence.stat().st_size == receipt["external_preflight_evidence"]["size_bytes"]
    assert file_hash(evidence) == receipt["external_preflight_evidence"]["sha256"]


def test_640x360_preflight_fails_closed_without_creating_evidence(tmp_path: Path) -> None:
    result = run_preflight_fixture(tmp_path, 640, 360)
    assert result.returncode != 0
    assert "observed 640x360, required 1920x1046" in result.stdout + result.stderr
    assert not (tmp_path / "preflight-evidence").exists()


def test_preflight_cannot_count_and_all_six_correct_layout_screenshots_pass(tmp_path: Path) -> None:
    rows, preflight = make_layout_fixture(tmp_path)
    rows_path = tmp_path / "layouts.json"
    rows_path.write_text(json.dumps({"layouts": rows}), encoding="utf-8")
    result = run_layout_assertion(rows_path, preflight)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(json.loads(result.stdout)) == 6
    rows[0]["path"] = str(preflight)
    rows_path.write_text(json.dumps({"layouts": rows}), encoding="utf-8")
    rejected = run_layout_assertion(rows_path, preflight)
    assert rejected.returncode != 0
    assert "preflight" in (rejected.stdout + rejected.stderr).lower()


def test_missing_layout_or_one_wrong_sized_layout_fails_entire_package(tmp_path: Path) -> None:
    rows, preflight = make_layout_fixture(tmp_path)
    rows_path = tmp_path / "layouts.json"
    rows_path.write_text(json.dumps({"layouts": rows[:-1]}), encoding="utf-8")
    missing = run_layout_assertion(rows_path, preflight)
    assert missing.returncode != 0
    assert "exactly six" in (missing.stdout + missing.stderr).lower()
    Path(rows[-1]["path"]).write_bytes(minimal_png(640, 360, b"wrong-size"))
    rows_path.write_text(json.dumps({"layouts": rows}), encoding="utf-8")
    wrong = run_layout_assertion(rows_path, preflight)
    assert wrong.returncode != 0
    assert "layout_06 screenshot is not 1920x1046" in wrong.stdout + wrong.stderr


def test_server_properties_auto_expansion_passes_and_other_drift_fails_closed() -> None:
    accepted = run_powershell_file(
        SERVER_PROPERTIES_VALIDATOR,
        "-AuthorityPath",
        str(SERVER_PROPERTIES_AUTHORITY),
        "-RuntimePath",
        str(SERVER_PROPERTIES_RUNTIME),
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert json.loads(accepted.stdout)["drift_classification"] == "MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION"
    rejected = run_powershell_file(
        SERVER_PROPERTIES_VALIDATOR,
        "-AuthorityPath",
        str(SERVER_PROPERTIES_FIXTURES / "authority.properties"),
        "-RuntimePath",
        str(SERVER_PROPERTIES_FIXTURES / "unknown-additional-property.properties"),
    )
    assert rejected.returncode != 0
    assert "Unexpected additional" in rejected.stdout + rejected.stderr


def test_runbook_finalizer_and_templates_encode_preflight_and_fail_closed_contracts() -> None:
    runbook = (DOC_DIR / "operator_runbook.md").read_text(encoding="utf-8")
    finalizer = FINALIZER.read_text(encoding="utf-8")
    assert "before every calibration episode" in runbook
    assert "Press F2 exactly once" in runbook
    assert "do not infer success from maximization, scaling, or appearance" in runbook
    assert "valid=true required=true count=1 lifecycle=READY problems=NONE" in runbook
    assert "recording never started" in runbook
    assert finalizer.count("Read-Host") == 1
    assert "Assert-ERefitAttempt02LayoutScreenshotSet" in finalizer
    assert "preflight_screenshot_counted_as_layout = $false" in finalizer
    assert "Compare-ServerPropertiesAuthority" in finalizer
    assert "MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION" in finalizer
    assert "recording started" in finalizer
    assert "run-c6a" not in finalizer.lower()
    fit = load(DOC_DIR / "e_image_point_annotation_template.json")
    validation = load(DOC_DIR / "e_independent_validation_pair_template.json")
    assert fit["owner_of_image_coordinates"] == "Person E"
    assert fit["person_c_invented_image_coordinates"] is False
    assert validation["owner_of_image_coordinates_and_visibility_decisions"] == "Person E"
    assert all(point["image_xy_pixels"] is None for row in fit["layouts"] for point in row["fit_correspondences"])
    assert all(point["image_xy_pixels"] is None for row in validation["layouts"] for point in row["validation_points"])


def test_additive_attempt_02_package_inventory_is_complete_and_hash_bound() -> None:
    inventory = load(DOC_DIR / "sha256_inventory.json")
    assert inventory["self_excluded"] == "sha256_inventory.json"
    for row in inventory["files"]:
        path = REPO / row["path"]
        assert path.is_file()
        assert path.stat().st_size == row["size_bytes"]
        assert file_hash(path) == row["sha256"]
    expected_bundle = hashlib.sha256(
        "".join(f"{row['path']}\0{row['sha256']}\n" for row in inventory["files"]).encode()
    ).hexdigest()
    assert inventory["package_bundle_sha256"] == expected_bundle
    names = {path.name for path in DOC_DIR.iterdir() if path.is_file()}
    assert {
        "attempt_01_failure_record.json",
        "framebuffer_diagnosis.json",
        "preflight_screenshot_baseline.json",
        "session_manifest.json",
        "runtime_identity.json",
        "screenshot_inventory.json",
        "geometry_receipt_inventory.json",
        "e_image_point_annotation_template.json",
        "e_independent_validation_pair_template.json",
        "coordinate_convention.json",
        "operator_attestation_template.json",
        "operator_runbook.md",
        "validation_report.md",
        *(f"layout_{index:02d}_calibration.json" for index in range(1, 7)),
    } <= names
