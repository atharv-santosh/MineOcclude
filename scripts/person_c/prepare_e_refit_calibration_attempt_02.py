#!/usr/bin/env python3
"""Prepare additive Person E v0.4 calibration Attempt 02 without running Minecraft."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from mineocclude.data.noise_schedule import generate_noise_schedule, serialize_schedule  # noqa: E402


SERVER = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")
CLIENT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
MINECRAFT_ROOT = Path(r"C:\Users\lollo\AppData\Roaming\.minecraft")
SOURCE_COMMIT = "7485f3c48da4cc86c6f7cea61ce20a8c87b063db"
REQUIRED_BRANCH = "completion/person-c-c1-c6a"
ATTEMPT_NAME = "e_refit_calibration_v0_4_attempt_02"
ATTEMPT_01_CLASSIFICATION = (
    "CALIBRATION_SCREENSHOT_FRAMEBUFFER_MISMATCH_640X360_EXPECTED_1920X1046"
)
FRAMEBUFFER_MISMATCH_CAUSE = (
    "CLIENT_LAUNCH_CONFIGURATION_EXPLICITLY_REQUESTED_640X360_AND_THE_WINDOW_REMAINED_AT_640X360"
)
KNOWN_GOOD_CLIENT_CONFIGURATION = (
    "WINDOWED_FULLSCREEN_FALSE_FOV_70_GUI_SCALE_2_OVERRIDE_0X0_POST_LAUNCH_FRAMEBUFFER_1920X1046"
)
GEOMETRY_VERSION = "person-c-layout-config-v0.4"
GEOMETRY_SHA256 = "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
OPTIONS_SHA256 = "13a43adde78280041f7adc29367b0a61ced6a9549f2430d9083a88665a0d9895"
FRAMEBUFFER = {"width_pixels": 1920, "height_pixels": 1046}
FOV_DEGREES = 70.0
WARMUP_TICKS = 12000
RECORD_TICKS = 20
EPISODES = [
    ("layout_01", 12711, 202608041701),
    ("layout_02", 12712, 202608041702),
    ("layout_03", 12713, 202608041703),
    ("layout_04", 12714, 202608041704),
    ("layout_05", 12715, 202608041705),
    ("layout_06", 12716, 202608041706),
]

GEOMETRY = REPO / "configs/scenes/layouts_v0_4.yaml"
CLOSURE = REPO / "docs/status/person_c_c1_closure_v0_1/c1_closure_status.json"
ENVIRONMENT_LOCK = REPO / "docs/status/person_c_c1_runtime_ingestion_v0_1/final_environment_lock_receipt.json"
RENDER_SETTINGS = REPO / "docs/status/person_c_c1_runtime_ingestion_v0_1/render_settings_receipt.json"
SERVER_MANIFEST = REPO / "docs/status/person_c_c1_runtime_provisioning_v0_2/server_runtime_manifest.json"
CLIENT_MANIFEST = REPO / "docs/status/person_c_c1_runtime_provisioning_v0_2/client_runtime_manifest.json"
REFIT_HANDOFF = REPO / "docs/status/person_c_to_person_e_homography_refit_v0_1/refit_input_authority.json"
REFIT_HANDOFF_INVENTORY = REPO / "docs/status/person_c_to_person_e_homography_refit_v0_1/sha256_inventory.json"
ORIGINAL_PACKAGE = REPO / "docs/status/person_c_to_person_e_calibration_images_v0_4_v0_1"
REPAIR_RECEIPT = REPO / "docs/status/person_c_e_refit_calibration_finalizer_server_properties_repair_v0_1/repair_receipt.json"
C1_RENDER_RECEIPT = REPO / "docs/status/person_c_c1_runtime_ingestion_v0_1/render_settings_receipt.json"
C1_CLIENT_RECEIPT = REPO / "docs/status/person_c_c1_runtime_ingestion_v0_1/client_startup_connection_receipt.json"
C1_5_FIRST_SUCCESS = REPO / "docs/status/person_c_c1_5_first_operator_attempt_04_success_v0_1/first_operator_success_receipt.json"
C1_5_SECOND_SUCCESS = REPO / "docs/status/person_c_c1_5_second_operator_attempt_02_success_v0_1/second_operator_success_receipt.json"
SERVER_PROPERTIES_AUTHORITY = REPO / "fabric/mineocclude-mod/provisioning/person-c-c1-v0_2/server.properties"
SERVER_PROPERTIES_VALIDATOR = REPO / "scripts/person_c/validate-server-properties-authority.ps1"
FINALIZER = REPO / "scripts/person_c/finalize-e-refit-calibration-v0-4-attempt-02.ps1"
PREFLIGHT_SCRIPT = REPO / "scripts/person_c/verify-e-refit-calibration-attempt-02-framebuffer.ps1"
ATTEMPT_MODULE = REPO / "scripts/person_c/ERefitCalibrationAttempt02Authority.psm1"
SERVER_PROPERTIES_MODULE = REPO / "scripts/person_c/ServerPropertiesAuthority.psm1"
DOC_DIR = REPO / "docs/status/person_c_to_person_e_calibration_images_v0_4_attempt_02_v0_1"
CONFIG_DIR = REPO / "configs/collection/person_c_e_refit_calibration_v0_4_attempt_02_v0_1"
REPO_SCHEDULE_DIR = CONFIG_DIR / "schedules"
RUNTIME_SCHEDULE_DIR = SERVER / "mineocclude_schedules"
SERVER_EVIDENCE_DIR = SERVER / f"{ATTEMPT_NAME}_v0_1"
CLIENT_EVIDENCE_DIR = CLIENT / f"{ATTEMPT_NAME}_v0_1"
PREFLIGHT_EVIDENCE_DIR = CLIENT / f"{ATTEMPT_NAME}_preflight_v0_1"
PREFLIGHT_EVIDENCE_PATH = PREFLIGHT_EVIDENCE_DIR / f"{ATTEMPT_NAME}_framebuffer_preflight_1920x1046.png"
PREFLIGHT_RECEIPT_PATH = PREFLIGHT_EVIDENCE_DIR / f"{ATTEMPT_NAME}_framebuffer_preflight_receipt.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def dump(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def identity(path: Path, *, display: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": display or str(path.resolve()), "size_bytes": len(data), "sha256": sha256(data)}


def repo_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(REPO).as_posix(),
        "size_bytes": len(data),
        "sha256": sha256(data),
        "git_blob": git_blob(data),
    }


def generated_identity(path: Path, data: bytes, *, repo_relative: bool = True) -> dict[str, Any]:
    display = path.relative_to(REPO).as_posix() if repo_relative else str(path.resolve())
    return {"path": display, "size_bytes": len(data), "sha256": sha256(data)}


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    require(len(data) == 24 and data[:8] == b"\x89PNG\r\n\x1a\n", f"invalid PNG: {path}")
    return struct.unpack(">II", data[16:24])


def assert_identity(row: dict[str, Any]) -> None:
    path = Path(row["path"])
    require(path.is_file(), f"preserved evidence absent: {path}")
    data = path.read_bytes()
    require(len(data) == row["size_bytes"] and sha256(data) == row["sha256"], f"preserved evidence drift: {path}")


def validate_repository_and_runtime() -> dict[str, Any]:
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=REPO, text=True, capture_output=True, check=True
    ).stdout.strip()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, capture_output=True, check=True
    ).stdout.strip()
    require(branch == REQUIRED_BRANCH, f"wrong branch: {branch}")
    require(head == SOURCE_COMMIT, f"wrong starting HEAD: {head}")
    require(sha256(GEOMETRY.read_bytes()) == GEOMETRY_SHA256, "geometry hash drift")
    closure = load(CLOSURE)
    require(
        closure["c1_1_complete"] is True
        and closure["c1_3_complete"] is True
        and closure["c1_5_complete"] is True
        and closure["person_c_c1_stop_gate_closed"] is True,
        "Person C C1 stop gate is not closed",
    )
    require(sha256((SERVER / "mods/mineocclude-0.1.1.jar").read_bytes()) == JAR_SHA256, "server JAR drift")
    require(sha256((CLIENT / "mods/mineocclude-0.1.1.jar").read_bytes()) == JAR_SHA256, "client JAR drift")
    require(sha256((CLIENT / "options.txt").read_bytes()) == OPTIONS_SHA256, "client options drift")
    options = (CLIENT / "options.txt").read_text(encoding="utf-8-sig")
    for expected in ("fullscreen:false", "fov:0.0", "guiScale:2", "overrideWidth:0", "overrideHeight:0"):
        require(re.search(rf"(?m)^{re.escape(expected)}$", options) is not None, f"client option drift: {expected}")
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SERVER_PROPERTIES_VALIDATOR),
            "-AuthorityPath",
            str(SERVER_PROPERTIES_AUTHORITY),
            "-RuntimePath",
            str(SERVER / "server.properties"),
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    comparison = json.loads(result.stdout)
    require(comparison["drift_classification"] == "MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION", "unexpected server.properties classification")
    return comparison


def validate_and_record_attempt_01() -> dict[str, Any]:
    repair = load(REPAIR_RECEIPT)
    evidence = repair["completed_calibration_evidence"]
    require(evidence["receipt_count"] == 6 and evidence["raw_screenshot_count"] == 6, "Attempt 01 evidence count drift")
    require(evidence["recording_never_started"] is True, "Attempt 01 recording history drift")
    for row in [*evidence["geometry_receipts"], *evidence["raw_screenshots"], evidence["server_log"], evidence["client_log"]]:
        assert_identity(row)
    require(
        {(row["width_pixels"], row["height_pixels"]) for row in evidence["raw_screenshots"]}
        == {(640, 360)},
        "Attempt 01 framebuffer evidence drift",
    )
    return {
        "schema_version": "person-c-e-refit-calibration-attempt-01-preserved-failure-v0.1",
        "status": "FAILED_PRESERVED_UNCERTIFIED",
        "attempt_number": 1,
        "classification": ATTEMPT_01_CLASSIFICATION,
        "preserved_unchanged": True,
        "certified": False,
        "resized_or_upscaled": False,
        "receipt_count": 6,
        "raw_screenshot_count": 6,
        "observed_framebuffer": {"width_pixels": 640, "height_pixels": 360},
        "required_framebuffer": FRAMEBUFFER,
        "geometry_receipts": evidence["geometry_receipts"],
        "raw_screenshots": evidence["raw_screenshots"],
        "logs": [evidence["server_log"], evidence["client_log"]],
        "chronology": evidence["chronology"],
        "recording_never_started": True,
        "source_repair_receipt": repo_identity(REPAIR_RECEIPT),
        "attempt_02_may_modify_attempt_01": False,
    }


def launcher_profile_summary(path: Path) -> dict[str, Any]:
    profiles = load(path).get("profiles", {})
    profile = profiles.get("fabric-loader-1.16.5")
    require(profile is not None, f"MineOcclude Launcher profile absent: {path}")
    resolution = profile.get("resolution", {})
    return {
        "configuration_file": identity(path),
        "profile_id": "fabric-loader-1.16.5",
        "name": profile.get("name"),
        "game_dir": profile.get("gameDir"),
        "java_dir": profile.get("javaDir"),
        "last_version_id": profile.get("lastVersionId"),
        "resolution": {"width_pixels": resolution.get("width"), "height_pixels": resolution.get("height")},
        "last_used": profile.get("lastUsed"),
    }


def build_diagnosis(attempt_01: dict[str, Any]) -> dict[str, Any]:
    start_script = CLIENT / "start-mineocclude-client.ps1"
    script_text = start_script.read_text(encoding="utf-8-sig")
    width = re.search(r"'--width'\s*\n\s*'(\d+)'", script_text)
    height = re.search(r"'--height'\s*\n\s*'(\d+)'", script_text)
    require(width and height, "unable to parse pinned client launch dimensions")
    official_profile = launcher_profile_summary(MINECRAFT_ROOT / "launcher_profiles.json")
    isolated_profile = launcher_profile_summary(CLIENT / "launcher_profiles.json")
    require(official_profile["resolution"] == {"width_pixels": 640, "height_pixels": 360}, "official Launcher profile no longer demonstrates failed launch cause")
    require((int(width.group(1)), int(height.group(1))) == (640, 360), "pinned launch script no longer demonstrates failed launch cause")
    c1_render = load(C1_RENDER_RECEIPT)
    c1_client = load(C1_CLIENT_RECEIPT)
    c1_5_first = load(C1_5_FIRST_SUCCESS)
    c1_5_second = load(C1_5_SECOND_SUCCESS)
    c1_raw = c1_render["raw_framebuffer"]["source_screenshot"]
    assert_identity(c1_raw)
    for success in (c1_5_first, c1_5_second):
        assert_identity(success["runtime_evidence"]["client_log_archive"])
    return {
        "schema_version": "person-c-e-refit-calibration-attempt-02-framebuffer-diagnosis-v0.1",
        "status": "PASS_DIAGNOSIS",
        "diagnosed_cause": FRAMEBUFFER_MISMATCH_CAUSE,
        "known_good_client_configuration": KNOWN_GOOD_CLIENT_CONFIGURATION,
        "failed_attempt_01": {
            "classification": ATTEMPT_01_CLASSIFICATION,
            "screenshots": attempt_01["raw_screenshots"],
            "client_log": attempt_01["logs"][1],
        },
        "current_client_options": {
            **identity(CLIENT / "options.txt"),
            "fullscreen": False,
            "fov_degrees": 70.0,
            "gui_scale": 2,
            "override_width": 0,
            "override_height": 0,
        },
        "pinned_launch_script": {
            **identity(start_script),
            "requested_width_pixels": int(width.group(1)),
            "requested_height_pixels": int(height.group(1)),
        },
        "minecraft_launcher_installation_configuration": official_profile,
        "isolated_launcher_profile_configuration": isolated_profile,
        "prior_c1_1_success": {
            "client_lifecycle_receipt": repo_identity(C1_CLIENT_RECEIPT),
            "client_log_identity": c1_client["client_log"],
            "authenticated_username": c1_client["client_username"],
            "render_settings_receipt": repo_identity(C1_RENDER_RECEIPT),
            "raw_framebuffer_screenshot": c1_raw,
            "framebuffer": {"width_pixels": 1920, "height_pixels": 1046},
            "fullscreen": False,
            "fov_degrees": 70.0,
            "gui_scale": 2,
            "options_sha256": OPTIONS_SHA256,
        },
        "prior_c1_5_success_logs_inspected": [
            c1_5_first["runtime_evidence"]["client_log_archive"],
            c1_5_second["runtime_evidence"]["client_log_archive"],
        ],
        "evidence_limits": [
            "Minecraft client logs do not emit framebuffer resize events.",
            "C1.5 success screenshots are 640x360 and therefore are not used as 1920x1046 framebuffer authority.",
            "The 1920x1046 C1.1 F2 PNG plus fullscreen=false proves the accepted post-launch windowed framebuffer; it does not prove a particular Windows scaling percentage.",
        ],
        "causal_chain": [
            "Both available launch mechanisms explicitly requested 640x360.",
            "Attempt 01 retained that requested framebuffer and all six F2 PNGs are exactly 640x360.",
            "The accepted C1.1 session used the same options identity but its windowed F2 PNG is exactly 1920x1046, proving a post-launch window-size difference rather than an options, FOV, GUI-scale, fullscreen, or server-property change.",
        ],
        "exact_corrective_action": [
            "In Minecraft Launcher, edit the authenticated 'MineOcclude C1 Runtime' installation Resolution from 640x360 to 1920x1046 before launch.",
            "Launch on a display/window session capable of a 1920x1046 client framebuffer and keep fullscreen=false, FOV Normal/70.0, GUI scale 2, overrideWidth 0, and overrideHeight 0.",
            "After connection, resize the windowed client only if needed; the disposable F2 preflight PNG, not the apparent window size, is the sole go/no-go authority.",
            "Do not arm any MineOcclude episode until the preflight script passes exactly 1920x1046.",
        ],
        "fullscreen_cause_claimed": False,
        "gui_scale_cause_claimed": False,
        "windows_scaling_cause_claimed": False,
        "server_properties_cause_claimed": False,
    }


def package_inventory(outputs: dict[Path, bytes]) -> bytes:
    rows = [
        generated_identity(path, data)
        for path, data in sorted(outputs.items(), key=lambda item: item[0].as_posix())
        if path.parent == DOC_DIR and path.name != "sha256_inventory.json"
    ]
    bundle = sha256("".join(f"{row['path']}\0{row['sha256']}\n" for row in rows).encode())
    return dump(
        {
            "schema_version": "person-c-package-sha256-inventory-v1.0",
            "self_excluded": "sha256_inventory.json",
            "package_bundle_sha256": bundle,
            "files": rows,
        }
    )


def write_outputs(outputs: dict[Path, bytes]) -> None:
    for path, data in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-runtime-schedules", action="store_true")
    args = parser.parse_args()
    server_properties_comparison = validate_repository_and_runtime()
    attempt_01 = validate_and_record_attempt_01()
    diagnosis = build_diagnosis(attempt_01)

    schedule_data = {
        episode: serialize_schedule(generate_noise_schedule(seed=seed, n_draws=RECORD_TICKS, q=0.0))
        for _, episode, seed in EPISODES
    }
    runtime_schedule_paths = [RUNTIME_SCHEDULE_DIR / f"episode_{episode}.jsonl" for _, episode, _ in EPISODES]
    for (_, episode, _), path in zip(EPISODES, runtime_schedule_paths, strict=True):
        if path.exists():
            require(path.read_bytes() == schedule_data[episode], f"Attempt 02 runtime schedule drift: {path}")
    receipt_paths = [SERVER / "mineocclude_observations" / f"{ATTEMPT_NAME}_{layout_id}.json" for layout_id, _, _ in EPISODES]
    screenshot_paths = [CLIENT_EVIDENCE_DIR / f"{ATTEMPT_NAME}_{layout_id}.png" for layout_id, _, _ in EPISODES]
    final_outputs = [
        SERVER_EVIDENCE_DIR / f"{ATTEMPT_NAME}_operator_attestation.json",
        SERVER_EVIDENCE_DIR / f"{ATTEMPT_NAME}_server_latest.log",
        CLIENT_EVIDENCE_DIR / f"{ATTEMPT_NAME}_client_latest.log",
        SERVER_EVIDENCE_DIR / f"{ATTEMPT_NAME}_screenshot_inventory.json",
        SERVER_EVIDENCE_DIR / f"{ATTEMPT_NAME}_geometry_receipt_inventory.json",
        SERVER_EVIDENCE_DIR / f"{ATTEMPT_NAME}_e_image_point_annotation_template.json",
        SERVER_EVIDENCE_DIR / f"{ATTEMPT_NAME}_e_independent_validation_pair_template.json",
        SERVER_EVIDENCE_DIR / f"{ATTEMPT_NAME}_person_c_to_e_calibration_handoff.json",
        SERVER_EVIDENCE_DIR / f"{ATTEMPT_NAME}_finalization_result.json",
        PREFLIGHT_EVIDENCE_PATH,
        PREFLIGHT_RECEIPT_PATH,
    ]
    collisions = [str(path) for path in [*receipt_paths, *screenshot_paths, *final_outputs] if path.exists()]
    require(not collisions, f"Attempt 02 create-only collision: {collisions}")
    if args.install_runtime_schedules:
        RUNTIME_SCHEDULE_DIR.mkdir(parents=True, exist_ok=True)
        for (_, episode, _), path in zip(EPISODES, runtime_schedule_paths, strict=True):
            if path.exists():
                continue
            with path.open("xb") as stream:
                stream.write(schedule_data[episode])
    runtime_ready = all(
        path.is_file() and path.read_bytes() == schedule_data[episode]
        for (_, episode, _), path in zip(EPISODES, runtime_schedule_paths, strict=True)
    )

    schedule_outputs: dict[Path, bytes] = {}
    schedule_rows = []
    for (layout_id, episode, seed), runtime_path in zip(EPISODES, runtime_schedule_paths, strict=True):
        data = schedule_data[episode]
        repo_path = REPO_SCHEDULE_DIR / f"episode_{episode}.jsonl"
        schedule_outputs[repo_path] = data
        schedule_rows.append(
            {
                "layout_id": layout_id,
                "episode_id": episode,
                "seed": seed,
                "q": 0.0,
                "record_ticks": RECORD_TICKS,
                "repository_schedule": generated_identity(repo_path, data),
                "runtime_schedule": {
                    **generated_identity(runtime_path, data, repo_relative=False),
                    "installation_status": "INSTALLED_HASH_MATCH" if runtime_ready else "PENDING_CREATE_ONLY_INSTALL",
                },
            }
        )
    schedule_manifest = {
        "schema_version": "person-c-e-refit-calibration-attempt-02-schedule-set-v0.1",
        "attempt_name": ATTEMPT_NAME,
        "immutable": True,
        "create_only_runtime_install": True,
        "non_scientific_calibration_only": True,
        "source_commit": SOURCE_COMMIT,
        "schedule_count": 6,
        "schedules": schedule_rows,
    }
    schedule_manifest_bytes = dump(schedule_manifest)
    schedule_outputs[CONFIG_DIR / "schedule_set_manifest.json"] = schedule_manifest_bytes

    original_manifest = load(ORIGINAL_PACKAGE / "session_manifest.json")
    original_by_layout = {row["layout_id"]: row for row in original_manifest["layouts"]}
    layouts = []
    layout_outputs: dict[Path, bytes] = {}
    screenshot_rows = []
    receipt_rows = []
    for index, (layout_id, episode, seed) in enumerate(EPISODES):
        record = copy.deepcopy(original_by_layout[layout_id])
        receipt_path = receipt_paths[index]
        screenshot_path = screenshot_paths[index]
        schedule = schedule_rows[index]
        record.update(
            {
                "schema_version": "person-c-e-refit-layout-calibration-attempt-02-preparation-v0.1",
                "status": "READY_AFTER_MANDATORY_FRAMEBUFFER_PREFLIGHT",
                "attempt_name": ATTEMPT_NAME,
                "attempt_number": 2,
                "episode_id": episode,
                "seed": seed,
                "schedule": schedule,
                "commands": {
                    "start": f"mineocclude start {layout_id} {episode} {seed} 0.0 0.0 20",
                    "targetstatus": "mineocclude targetstatus",
                    "observegeometry": f"mineocclude observegeometry {ATTEMPT_NAME}_{layout_id}",
                    "stop": "mineocclude stop",
                },
                "runtime_paths": {
                    "geometry_receipt": str(receipt_path.resolve()),
                    "canonical_screenshot": str(screenshot_path.resolve()),
                    "server_log": str((SERVER / "logs/latest.log").resolve()),
                    "client_log": str((CLIENT / "logs/latest.log").resolve()),
                    "preflight_receipt": str(PREFLIGHT_RECEIPT_PATH.resolve()),
                },
                "source_commit": SOURCE_COMMIT,
            }
        )
        layouts.append(record)
        layout_outputs[DOC_DIR / f"{layout_id}_calibration.json"] = dump(record)
        screenshot_rows.append(
            {
                "layout_id": layout_id,
                "episode_id": episode,
                "create_only_destination": str(screenshot_path.resolve()),
                "required_width_pixels": 1920,
                "required_height_pixels": 1046,
                "preflight_screenshot_eligible": False,
                "observed_source_path": None,
                "size_bytes": None,
                "sha256": None,
                "status": "PENDING_RUNTIME_FINALIZATION",
            }
        )
        receipt_rows.append(
            {
                "layout_id": layout_id,
                "episode_id": episode,
                "receipt_id": f"{ATTEMPT_NAME}_{layout_id}",
                "create_only_path": str(receipt_path.resolve()),
                "path_absent_at_preparation": True,
                "size_bytes": None,
                "sha256": None,
                "status": "PENDING_RUNTIME_OBSERVATION",
            }
        )

    fit_template = load(ORIGINAL_PACKAGE / "e_image_point_annotation_template.json")
    validation_template = load(ORIGINAL_PACKAGE / "e_independent_validation_pair_template.json")
    for template in (fit_template, validation_template):
        template["attempt_name"] = ATTEMPT_NAME
        for row, (_, episode, _) in zip(template["layouts"], EPISODES, strict=True):
            row["episode_id"] = episode
            row["screenshot"]["path"] = str((CLIENT_EVIDENCE_DIR / f"{ATTEMPT_NAME}_{row['layout_id']}.png").resolve())
            row["screenshot"]["width_pixels"] = 1920
            row["screenshot"]["height_pixels"] = 1046
            row["screenshot"]["size_bytes"] = None
            row["screenshot"]["sha256"] = None
    fit_template["schema_version"] = "person-e-v0.4-image-point-annotation-template-attempt-02-v0.1"
    validation_template["schema_version"] = "person-e-v0.4-independent-validation-pair-template-attempt-02-v0.1"
    coordinate_convention = load(ORIGINAL_PACKAGE / "coordinate_convention.json")
    coordinate_convention["attempt_name"] = ATTEMPT_NAME

    baseline_rows = []
    for path in sorted((CLIENT / "screenshots").glob("*.png"), key=lambda item: item.name):
        width, height = png_dimensions(path)
        baseline_rows.append({**identity(path), "width_pixels": width, "height_pixels": height})
    preflight_baseline = {
        "schema_version": "person-c-e-refit-calibration-attempt-02-preflight-screenshot-baseline-v0.1",
        "attempt_name": ATTEMPT_NAME,
        "purpose": "identify exactly one new disposable F2 screenshot before any Attempt 02 episode",
        "screenshot_count": len(baseline_rows),
        "screenshots": baseline_rows,
    }
    preflight_command = (
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
        '"C:\\Users\\lollo\\MineOcclude-Person-C-C1-C6A\\scripts\\person_c\\verify-e-refit-calibration-attempt-02-framebuffer.ps1"'
    )
    finalization_command = (
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
        '"C:\\Users\\lollo\\MineOcclude-Person-C-C1-C6A\\scripts\\person_c\\finalize-e-refit-calibration-v0-4-attempt-02.ps1"'
    )
    attestation_template = {
        "schema_version": "person-c-e-refit-calibration-attempt-02-operator-attestation-v0.1",
        "template": True,
        "attempt_name": ATTEMPT_NAME,
        "operator_id": None,
        "observed_authenticated_account": None,
        "single_authenticated_operator": None,
        "framebuffer_preflight_passed": None,
        "preflight_screenshot_excluded_from_layouts": None,
        "normal_gameplay_no_pause_chat_inventory_or_f3_for_all_screenshots": None,
        "exactly_one_f2_per_layout_after_receipt_confirmation": None,
        "all_six_episodes_aborted_during_warmup": None,
        "recording_never_started": None,
        "same_server_client_options_render_and_log_session": None,
        "preparation_commit": None,
        "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": GEOMETRY_SHA256,
        "mineocclude_jar_sha256": JAR_SHA256,
        "layout_ids": [row[0] for row in EPISODES],
        "episode_ids": [row[1] for row in EPISODES],
        "utc_start": None,
        "utc_end": None,
        "notes": None,
    }
    runtime_identity = {
        "schema_version": "person-c-e-refit-calibration-attempt-02-runtime-identity-v0.1",
        "status": "PASS_PREPARATION_RUNTIME_IDENTITIES",
        "source_commit": SOURCE_COMMIT,
        "accepted_geometry": repo_identity(GEOMETRY),
        "accepted_geometry_version": GEOMETRY_VERSION,
        "person_c_c1_closure": repo_identity(CLOSURE),
        "environment_lock": {"version": "person-c-c1-final-environment-lock-v1.0", **repo_identity(ENVIRONMENT_LOCK)},
        "render_settings": repo_identity(RENDER_SETTINGS),
        "server_runtime_manifest": repo_identity(SERVER_MANIFEST),
        "client_runtime_manifest": repo_identity(CLIENT_MANIFEST),
        "person_e_refit_input_authority": repo_identity(REFIT_HANDOFF),
        "person_e_refit_handoff_inventory": repo_identity(REFIT_HANDOFF_INVENTORY),
        "server_jar": identity(SERVER / "mods/mineocclude-0.1.1.jar"),
        "client_jar": identity(CLIENT / "mods/mineocclude-0.1.1.jar"),
        "server_properties": identity(SERVER / "server.properties"),
        "server_properties_semantic_validation": server_properties_comparison,
        "spawn_animals": False,
        "client_options": identity(CLIENT / "options.txt"),
        "fov_degrees": FOV_DEGREES,
        "framebuffer": FRAMEBUFFER,
    }
    controls = [
        "mineocclude markergeomstatus",
        "mineocclude mode normal",
        "mineocclude duration 0",
        "mineocclude reveal 0",
        "mineocclude impulse -1 0",
        "mineocclude lockcam on",
        "mineocclude warmup 12000",
    ]
    session_manifest = {
        "schema_version": "person-c-to-person-e-calibration-image-session-v0.4-attempt-02-v0.1",
        "status": "READY_AFTER_MANDATORY_FRAMEBUFFER_PREFLIGHT" if runtime_ready else "PENDING_RUNTIME_SCHEDULE_INSTALL",
        "source_commit": SOURCE_COMMIT,
        "attempt_name": ATTEMPT_NAME,
        "attempt_number": 2,
        "attempt_01": {
            "preserved": True,
            "classification": ATTEMPT_01_CLASSIFICATION,
            "failure_record": "attempt_01_failure_record.json",
            "certified": False,
        },
        "purpose": "non-scientific six-layout calibration evidence for Person E v0.4 homography refit",
        "scientific_capture": False,
        "c1_5_reconstruction": False,
        "c6a_or_c6b": False,
        "operator_count_required": 1,
        "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": GEOMETRY_SHA256,
        "mineocclude_jar_sha256": JAR_SHA256,
        "framebuffer": FRAMEBUFFER,
        "fov_degrees": FOV_DEGREES,
        "runtime_identity": runtime_identity,
        "framebuffer_diagnosis": {
            "path": "framebuffer_diagnosis.json",
            "cause": FRAMEBUFFER_MISMATCH_CAUSE,
            "known_good_configuration": KNOWN_GOOD_CLIENT_CONFIGURATION,
        },
        "preflight": {
            "mandatory_before_any_episode": True,
            "script": repo_identity(PREFLIGHT_SCRIPT),
            "command": preflight_command,
            "baseline_inventory": "preflight_screenshot_baseline.json",
            "receipt_path": str(PREFLIGHT_RECEIPT_PATH.resolve()),
            "external_evidence_path": str(PREFLIGHT_EVIDENCE_PATH.resolve()),
            "required_framebuffer": FRAMEBUFFER,
            "fail_closed": True,
            "layout_screenshot_eligible": False,
        },
        "session_controls_apply_once_in_order_after_preflight": controls,
        "layout_count": 6,
        "layouts": layouts,
        "strict_per_layout_chronology": [
            "episode_armed",
            "wait_at_least_10_seconds",
            "one_passing_targetstatus_valid_true_required_true_count_1_lifecycle_READY_problems_NONE",
            "fresh_observegeometry_completes",
            "receipt_written_confirmation",
            "exactly_one_in_window_f2_after_confirmation",
            "mineocclude_stop_aborts_during_warmup",
            "recording_does_not_begin",
        ],
        "finalizer": repo_identity(FINALIZER),
        "authority_module": repo_identity(ATTEMPT_MODULE),
        "server_properties_validator": repo_identity(SERVER_PROPERTIES_MODULE),
        "finalization_command": finalization_command,
        "runtime_schedules_ready": runtime_ready,
        "schedule_set_manifest": generated_identity(CONFIG_DIR / "schedule_set_manifest.json", schedule_manifest_bytes),
        "runtime_executed_by_preparation": False,
        "c6a_executed_by_preparation": False,
        "person_e_modified_by_preparation": False,
    }
    screenshot_inventory = {
        "schema_version": "person-c-e-refit-calibration-attempt-02-screenshot-inventory-preparation-v0.1",
        "status": "PENDING_RUNTIME_FINALIZATION",
        "create_only": True,
        "preflight_screenshot_counted": False,
        "screenshots": screenshot_rows,
    }
    receipt_inventory = {
        "schema_version": "person-c-e-refit-calibration-attempt-02-geometry-receipt-inventory-preparation-v0.1",
        "status": "PENDING_RUNTIME_OBSERVATION",
        "create_only": True,
        "receipts": receipt_rows,
    }

    runbook_lines = [
        "# Person E v0.4 six-layout calibration Attempt 02",
        "",
        f"Attempt 01 is preserved unchanged and classified exactly as `{ATTEMPT_01_CLASSIFICATION}`. Never delete, rename, overwrite, resize, upscale, or certify its files. This task is not C6A and does not modify Person E.",
        "",
        "## Mandatory framebuffer preflight — before every calibration episode",
        "",
        "1. In Minecraft Launcher, edit the authenticated `MineOcclude C1 Runtime` installation. Set Resolution to `1920x1046`; its inspected value was `640x360`, which caused Attempt 01 to remain 640x360.",
        "2. Start the isolated server with `C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\server\\start-mineocclude-server.ps1`.",
        "3. Launch that authenticated Launcher installation. Connect to `127.0.0.1:25565`.",
        "4. Keep `fullscreen=false`, FOV Normal (70.0), GUI scale 2, `overrideWidth=0`, and `overrideHeight=0`. Use a display/window session capable of the target. Resize the windowed client only if needed; do not infer success from maximization, scaling, or appearance.",
        "5. Confirm normal unobstructed gameplay and that no MineOcclude episode is running. Do not run any `mineocclude start` command yet.",
        "6. Press F2 exactly once. This is the disposable preflight screenshot, never a layout screenshot.",
        f"7. Run `{preflight_command}`.",
        "8. Continue only if it prints `FRAMEBUFFER_PREFLIGHT_PASS=True` and `FRAMEBUFFER=1920x1046`. Any other dimensions fail closed. The script copies the PNG and writes its path, size, dimensions, and SHA-256 under a distinct external preflight evidence directory.",
        "",
        "## Session controls and six layouts",
        "",
        "After the successful preflight, apply these server-console controls exactly once in order: " + "; ".join(f"`{row}`" for row in controls) + ".",
        "",
        "Do not begin if any Attempt 02 receipt or canonical screenshot path already exists.",
        "",
        "| Layout | Start | Fresh observegeometry | Create-only receipt | Canonical screenshot |",
        "|---|---|---|---|---|",
    ]
    for row in layouts:
        runbook_lines.append(
            f"| `{row['layout_id']}` | `{row['commands']['start']}` | `{row['commands']['observegeometry']}` | `{row['runtime_paths']['geometry_receipt']}` | `{row['runtime_paths']['canonical_screenshot']}` |"
        )
    runbook_lines.extend(
        [
            "",
            "For every layout: start the fresh episode; wait at least ten seconds; run `mineocclude targetstatus`; require exactly `valid=true required=true count=1 lifecycle=READY problems=NONE`; run the fresh observegeometry command; wait for the receipt-written confirmation; switch to normal unobstructed gameplay; press F2 exactly once; immediately run `mineocclude stop`; require warmup abort; and require recording never started.",
            "",
            "After layout_06, disconnect and quit the client, then stop the server cleanly. Run the finalizer once:",
            "",
            f"`{finalization_command}`",
            "",
            "The finalizer first revalidates preserved Attempt 01, the 1920x1046 preflight, append-only server/client sessions, strict server.properties semantics, all six chronologies, exactly six in-window layout F2 events, and all six PNG dimensions. The preflight F2 occurs before the first arm and is explicitly forbidden as layout input. Type `YES` once only when prompted and only if the unobstructed-gameplay/authenticated-operator statement is true.",
            "",
            "The finalizer only creates new Attempt 02 evidence; it never edits runtime evidence in place, fits a homography, runs C6A, or fills Person E image points.",
        ]
    )
    validation_md = f"""# Attempt 02 preparation validation

PASS for additive preparation. Attempt 01 is preserved and classified as `{ATTEMPT_01_CLASSIFICATION}`. The diagnosed failure cause is `{FRAMEBUFFER_MISMATCH_CAUSE}`. The known-good configuration is `{KNOWN_GOOD_CLIENT_CONFIGURATION}`.

The new six-layout schedules, receipt names, screenshot destinations, preflight paths, attestation path, log archives, handoff paths, and finalization outputs are create-only and distinct. The 1920x1046 disposable-F2 preflight is mandatory and cannot count toward a layout. The repaired strict semantic server.properties validator remains authoritative and accepts only the observed Minecraft auto-expansion. Runtime calibration and C6A were not executed; Person E was not modified.
"""

    outputs: dict[Path, bytes] = {
        **schedule_outputs,
        **layout_outputs,
        DOC_DIR / "attempt_01_failure_record.json": dump(attempt_01),
        DOC_DIR / "framebuffer_diagnosis.json": dump(diagnosis),
        DOC_DIR / "preflight_screenshot_baseline.json": dump(preflight_baseline),
        DOC_DIR / "session_manifest.json": dump(session_manifest),
        DOC_DIR / "runtime_identity.json": dump(runtime_identity),
        DOC_DIR / "screenshot_inventory.json": dump(screenshot_inventory),
        DOC_DIR / "geometry_receipt_inventory.json": dump(receipt_inventory),
        DOC_DIR / "e_image_point_annotation_template.json": dump(fit_template),
        DOC_DIR / "e_independent_validation_pair_template.json": dump(validation_template),
        DOC_DIR / "coordinate_convention.json": dump(coordinate_convention),
        DOC_DIR / "operator_attestation_template.json": dump(attestation_template),
        DOC_DIR / "operator_runbook.md": ("\n".join(runbook_lines) + "\n").encode("utf-8"),
        DOC_DIR / "validation_report.md": validation_md.encode("utf-8"),
    }
    outputs[DOC_DIR / "sha256_inventory.json"] = package_inventory(outputs)
    write_outputs(outputs)
    require(runtime_ready, "runtime schedules are not installed; rerun with --install-runtime-schedules")
    print(
        json.dumps(
            {
                "status": "PASS",
                "attempt_01_preserved": True,
                "attempt_01_classification": ATTEMPT_01_CLASSIFICATION,
                "framebuffer_mismatch_cause": FRAMEBUFFER_MISMATCH_CAUSE,
                "known_good_client_configuration": KNOWN_GOOD_CLIENT_CONFIGURATION,
                "episode_ids": [row[1] for row in EPISODES],
                "seeds": [row[2] for row in EPISODES],
                "runtime_schedules_ready": True,
                "runtime_executed": False,
                "c6a_executed": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
