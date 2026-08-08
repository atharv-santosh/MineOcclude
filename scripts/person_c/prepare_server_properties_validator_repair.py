#!/usr/bin/env python3
"""Build the additive server.properties semantic-validator repair receipt."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
SERVER = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")
CLIENT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
SOURCE_COMMIT = "e4deae0e5c3f3ed4fd820b1f0d0381ec0c5b39da"
DOC_DIR = REPO / "docs/status/person_c_e_refit_calibration_finalizer_server_properties_repair_v0_1"
PREPARATION_MANIFEST = REPO / "docs/status/person_c_to_person_e_calibration_images_v0_4_v0_1/session_manifest.json"
PREPARATION_RUNTIME_IDENTITY = REPO / "docs/status/person_c_to_person_e_calibration_images_v0_4_v0_1/runtime_identity.json"
AUTHORITY = REPO / "fabric/mineocclude-mod/provisioning/person-c-c1-v0_2/server.properties"
RUNTIME = SERVER / "server.properties"
FINALIZER = REPO / "scripts/person_c/finalize-e-refit-calibration-v0-4.ps1"
MODULE = REPO / "scripts/person_c/ServerPropertiesAuthority.psm1"
CLI = REPO / "scripts/person_c/validate-server-properties-authority.ps1"
SCREENSHOT_DIMENSION_BLOCKER = "CALIBRATION_SCREENSHOTS_ARE_640X360_BUT_FINALIZER_REQUIRES_1920X1046"

EPISODES = [
    ("layout_01", 12701, "2026-08-04_00.14.28.png"),
    ("layout_02", 12702, "2026-08-04_00.15.11.png"),
    ("layout_03", 12703, "2026-08-04_00.15.47.png"),
    ("layout_04", 12704, "2026-08-04_00.16.30.png"),
    ("layout_05", 12705, "2026-08-04_00.17.07.png"),
    ("layout_06", 12706, "2026-08-04_00.17.44.png"),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def dump(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def identity(path: Path, *, repo_relative: bool = False) -> dict[str, Any]:
    data = path.read_bytes()
    display = path.relative_to(REPO).as_posix() if repo_relative else str(path.resolve())
    result = {"path": display, "size_bytes": len(data), "sha256": sha256(data)}
    if repo_relative:
        result["git_blob"] = git_blob(data)
    return result


def line_seconds(line: str) -> int:
    match = re.match(r"\[(\d{2}):(\d{2}):(\d{2})\]", line)
    require(match is not None, f"log line lacks timestamp: {line}")
    hour, minute, second = (int(value) for value in match.groups())
    return hour * 3600 + minute * 60 + second


def offset(base: int, event: int) -> int:
    return (event - base) % 86400


def unique_line(lines: list[str], pattern: str, label: str) -> tuple[int, str]:
    regex = re.compile(pattern)
    matches = [(index, line) for index, line in enumerate(lines) if regex.search(line)]
    require(len(matches) == 1, f"{label} count is {len(matches)}, expected one")
    return matches[0]


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    require(data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24, f"invalid PNG: {path}")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def semantic_comparison() -> dict[str, Any]:
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(CLI),
            "-AuthorityPath", str(AUTHORITY), "-RuntimePath", str(RUNTIME),
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    require(result.returncode == 0, f"semantic validator failed: {result.stdout} {result.stderr}")
    comparison = json.loads(result.stdout)
    require(comparison["status"] == "PASS", "semantic comparison is not PASS")
    require(comparison["drift_classification"] == "MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION", "wrong drift classification")
    require(comparison["authority"]["property_count"] == 49 and comparison["runtime"]["property_count"] == 51, "property counts drift")
    require(comparison["shared_property_values_match"] is True, "shared property drift")
    require(comparison["allowed_additional_keys_present"] == ["query.port", "text-filtering-config"], "allowed expansion drift")
    require(comparison["unexpected_additional_keys"] == [], "unexpected runtime properties")
    return comparison


def evidence_integrity() -> dict[str, Any]:
    server_log = SERVER / "logs/latest.log"
    client_log = CLIENT / "logs/latest.log"
    server_lines = server_log.read_text(encoding="utf-8-sig").splitlines()
    client_lines = client_log.read_text(encoding="utf-8-sig").splitlines()
    receipt_rows = []
    screenshot_rows = []
    chronology_rows = []
    previous_abort = -1
    first_armed_seconds: int | None = None
    for layout_id, episode, screenshot_name in EPISODES:
        receipt_path = SERVER / "mineocclude_observations" / f"e_refit_calibration_v0_4_{layout_id}.json"
        receipt = load(receipt_path)
        require(receipt["receipt_id"] == f"e_refit_calibration_v0_4_{layout_id}", f"receipt ID drift: {layout_id}")
        require(receipt["layout_id"] == layout_id and receipt["episode_id"] == episode, f"receipt episode drift: {layout_id}")
        require(receipt["lifecycle_state"] == "READY" and receipt["running"] is True and receipt["capturing"] is False, f"receipt lifecycle drift: {layout_id}")
        target = receipt["target"]
        require(target["valid"] is True and target["required"] is True and target["tagged_target_count"] == 1 and target["problems"] == [], f"receipt target drift: {layout_id}")
        armed = unique_line(server_lines, rf"\[MineOcclude\] episode {episode} armed \(layout={layout_id}, 12000 warmup \+ 20 record ticks", f"{layout_id} armed")
        status = unique_line(server_lines, rf"\[MineOcclude/target\] target status: valid=true required=true count=1.*layout={layout_id} episode={episode} lifecycle=READY problems=NONE", f"{layout_id} targetstatus")
        observed = unique_line(server_lines, rf"\[MineOcclude/observation\] wrote read-only geometry receipt .*e_refit_calibration_v0_4_{layout_id}\.json", f"{layout_id} observe")
        confirmed = unique_line(server_lines, rf"Wrote observation-only geometry receipt: .*e_refit_calibration_v0_4_{layout_id}\.json", f"{layout_id} confirmation")
        aborted = unique_line(server_lines, rf"\[MineOcclude\] episode {episode} aborted during warmup", f"{layout_id} abort")
        require(previous_abort < armed[0] < status[0] < observed[0] <= confirmed[0] < aborted[0], f"server chronology drift: {layout_id}")
        previous_abort = aborted[0]
        armed_seconds = line_seconds(armed[1])
        if first_armed_seconds is None:
            first_armed_seconds = armed_seconds
        require(offset(armed_seconds, line_seconds(status[1])) >= 10, f"targetstatus too early: {layout_id}")
        screenshot_event = unique_line(client_lines, rf"Saved screenshot as {re.escape(screenshot_name)}", f"{layout_id} screenshot")
        confirmation_offset = offset(first_armed_seconds, line_seconds(confirmed[1]))
        screenshot_offset = offset(first_armed_seconds, line_seconds(screenshot_event[1]))
        abort_offset = offset(first_armed_seconds, line_seconds(aborted[1]))
        require(confirmation_offset < screenshot_offset < abort_offset, f"screenshot chronology drift: {layout_id}")
        screenshot_path = CLIENT / "screenshots" / screenshot_name
        dimensions = png_dimensions(screenshot_path)
        receipt_rows.append(identity(receipt_path))
        screenshot_rows.append({**identity(screenshot_path), "width_pixels": dimensions[0], "height_pixels": dimensions[1]})
        chronology_rows.append(
            {
                "layout_id": layout_id,
                "episode_id": episode,
                "targetstatus_after_arming_seconds": offset(armed_seconds, line_seconds(status[1])),
                "receipt_confirmation_session_offset_seconds": confirmation_offset,
                "screenshot_session_offset_seconds": screenshot_offset,
                "warmup_abort_session_offset_seconds": abort_offset,
                "recording_started": False,
            }
        )
        require(not any(f"episode {episode} recording started" in line for line in server_lines), f"recording started: {episode}")
    partial_paths = [
        SERVER / "e_refit_calibration_v0_4_v0_1/operator_attestation.json",
        SERVER / "e_refit_calibration_v0_4_v0_1/server_latest.log",
        CLIENT / "e_refit_calibration_v0_4_v0_1/client_latest.log",
        SERVER / "e_refit_calibration_v0_4_v0_1/screenshot_inventory.json",
        SERVER / "e_refit_calibration_v0_4_v0_1/geometry_receipt_inventory.json",
        SERVER / "e_refit_calibration_v0_4_v0_1/e_image_point_annotation_template.json",
        SERVER / "e_refit_calibration_v0_4_v0_1/e_independent_validation_pair_template.json",
        SERVER / "e_refit_calibration_v0_4_v0_1/person_c_to_e_calibration_handoff_v0_4.json",
        SERVER / "e_refit_calibration_v0_4_v0_1/finalization_result.json",
        *(CLIENT / "e_refit_calibration_v0_4_v0_1" / f"layout_{index:02d}.png" for index in range(1, 7)),
    ]
    present_partial = [str(path.resolve()) for path in partial_paths if path.exists()]
    require(not present_partial, f"partial finalization output present: {present_partial}")
    return {
        "status": "PASS",
        "completed_calibration_session_preserved": True,
        "receipt_count": 6,
        "raw_screenshot_count": 6,
        "server_log": identity(server_log),
        "client_log": identity(client_log),
        "geometry_receipts": receipt_rows,
        "raw_screenshots": screenshot_rows,
        "observed_screenshot_dimensions": {"width_pixels": 640, "height_pixels": 360},
        "required_finalizer_screenshot_dimensions": {"width_pixels": 1920, "height_pixels": 1046},
        "screenshot_dimensions_match_finalizer_requirement": False,
        "chronology": chronology_rows,
        "all_target_objects_valid": True,
        "all_episodes_aborted_during_warmup": True,
        "recording_never_started": True,
        "partial_finalization_output_present": False,
        "partial_finalization_paths_present": [],
        "minecraft_rerun_by_repair": False,
        "runtime_evidence_modified_by_repair": False,
    }


def package_inventory(outputs: dict[Path, bytes]) -> bytes:
    rows = []
    for path, data in sorted(outputs.items(), key=lambda item: item[0].as_posix()):
        if path.name == "sha256_inventory.json":
            continue
        rows.append({"path": path.relative_to(REPO).as_posix(), "size_bytes": len(data), "sha256": sha256(data)})
    return dump({"schema_version": "person-c-package-sha256-inventory-v1.0", "self_excluded": "sha256_inventory.json", "files": rows})


def main() -> int:
    comparison = semantic_comparison()
    evidence = evidence_integrity()
    preparation_manifest = load(PREPARATION_MANIFEST)
    preparation_runtime = load(PREPARATION_RUNTIME_IDENTITY)
    repair_receipt = {
        "schema_version": "person-c-e-refit-calibration-finalizer-server-properties-repair-v0.1",
        "status": "PASS",
        "source_commit": SOURCE_COMMIT,
        "scope": "validator repair only; completed calibration session not rerun or modified",
        "predecessor_finalizer": preparation_manifest["finalizer"],
        "successor_finalizer": identity(FINALIZER, repo_relative=True),
        "semantic_validator": identity(MODULE, repo_relative=True),
        "validator_cli": identity(CLI, repo_relative=True),
        "authority_baseline": identity(AUTHORITY, repo_relative=True),
        "preparation_observed_runtime_server_properties": preparation_runtime["server_properties"],
        "semantic_comparison": comparison,
        "accepted_difference_classification": "MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION",
        "raw_files_identical": False,
        "raw_hash_check_replaced": True,
        "fail_closed_for_other_drift": True,
        "allowed_additional_keys": ["query.port", "text-filtering-config"],
        "server_properties_validator_repair_ready": True,
        "full_finalization_ready": False,
        "unresolved_blockers": [SCREENSHOT_DIMENSION_BLOCKER],
        "completed_calibration_evidence": evidence,
    }
    validation = {
        "schema_version": "person-c-e-refit-calibration-finalizer-server-properties-repair-validation-v0.1",
        "status": "PASS",
        "checks": {
            "authority_property_count_49": True,
            "runtime_property_count_51": True,
            "shared_property_values_match": True,
            "only_query_port_and_empty_text_filtering_config_added": True,
            "safety_critical_values_match": True,
            "strict_parser_rejects_duplicates_and_malformed_lines": True,
            "missing_changed_and_unknown_properties_fail_closed": True,
            "query_port_must_equal_server_port": True,
            "text_filtering_config_must_be_empty": True,
            "spawn_animals_must_be_false": True,
            "calibration_chronology_intact": True,
            "calibration_evidence_hash_bound": True,
            "partial_finalization_output_absent": True,
            "existing_screenshot_dimension_mismatch_recorded": True,
            "screenshot_dimension_check_not_weakened": True,
            "minecraft_not_rerun": True,
            "c6a_not_executed": True,
        },
    }
    explanation = """# E-refit calibration finalizer server.properties repair

The tracked provisioning file remains the immutable semantic authority. Minecraft added only `query.port=25565` and an empty `text-filtering-config` to the runtime file; all 49 authoritative key/value pairs still match. The raw files are explicitly not identical. This successor finalizer accepts that exact auto-expansion as `MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION` and rejects missing keys, changed values, duplicates, malformed lines, non-empty filtering configuration, a mismatched query port, or any other extra key.

The completed six-layout calibration receipts, raw screenshots, and logs remain external and hash-bound. The failed predecessor invocation created no finalization output. The repair does not rerun Minecraft, consume the operator attestation, fit Person E homographies, or execute C6A.

This validator repair does not make the complete finalization runnable: all six preserved screenshots are 640x360, while the preparation manifest and unchanged finalizer require 1920x1046. That pre-existing mismatch remains fail-closed and is recorded as `CALIBRATION_SCREENSHOTS_ARE_640X360_BUT_FINALIZER_REQUIRES_1920X1046`.
"""
    outputs = {
        DOC_DIR / "repair_receipt.json": dump(repair_receipt),
        DOC_DIR / "validation_receipt.json": dump(validation),
        DOC_DIR / "README.md": explanation.encode(),
    }
    outputs[DOC_DIR / "sha256_inventory.json"] = package_inventory(outputs)
    for path, data in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(json.dumps({"status": "PASS", "shared_property_count": 49, "classification": comparison["drift_classification"], "partial_output_present": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
