#!/usr/bin/env python3
"""Build the P3 terminal historical freeze package from existing evidence.

This is a preservation-only utility.  It does not execute experiment code,
capture data, adjudicate candidates, or alter any pre-existing evidence file.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
OUT = REPO / "docs/status/integration/regime_a_prime_qualification_v0_1"
AUDIT = OUT / "p3_terminal_forensic_audit_v0_1"
BASELINE_HEAD = "e56d90b3da11966e30119dc0efe39fa3b13f1b5c"
BRANCH = "exploration/regime-a-prime-qualification-v0-1"
AUTHORITY_SHA256 = "bd391bd6f1bae0c90ea1ae74ee60c1315c5a3a171a91f98df14098e4232c9e23"
P3_MANIFEST_SHA256 = "bb74f9ae761647e49cddf24f334bd1329843304259643688f6735029170f6b32"
CONTROLLER = REPO / "scripts/regime_a_prime_qualification_v0_1/p3_run_sequential.py"
CONTROLLER_CAVEAT = (
    "THIS HASH DOES NOT RETROACTIVELY PROVE THAT THE EXECUTED P3 CONTROLLER "
    "WAS BYTE-IDENTICAL TO THIS FILE."
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO, text=True, capture_output=True, check=check
    )
    return result.stdout.strip()


def git_index(path: Path) -> tuple[bool, str | None, str | None]:
    relative = path.relative_to(REPO).as_posix()
    line = git("ls-files", "-s", "--", relative)
    if not line:
        return False, None, None
    mode, blob, _stage_and_path = line.split(maxsplit=2)
    return True, blob, mode


def metadata(path: Path) -> dict:
    info = path.stat()
    tracked, blob, index_mode = git_index(path)
    return {
        "relative_path": path.relative_to(REPO).as_posix(),
        "bytes": info.st_size,
        "sha256": sha256(path),
        "git_tracking_status_at_baseline": "tracked" if tracked else "untracked",
        "git_blob_hash_at_baseline": blob,
        "git_index_mode_at_baseline": index_mode,
        "mode_octal": oct(stat.S_IMODE(info.st_mode)),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "inode": info.st_ino,
        "mtime_utc": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
        "ctime_utc": datetime.fromtimestamp(info.st_ctime, timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def add_role(roles: dict[str, str], path_value: str, role: str) -> None:
    path = REPO / path_value
    if not path.is_file():
        raise RuntimeError(f"referenced repository file does not resolve: {path_value}")
    roles.setdefault(path_value, role)


def main() -> None:
    if git("rev-parse", "HEAD") != BASELINE_HEAD:
        raise RuntimeError("freeze builder must run before the preservation commit at the frozen baseline HEAD")
    if git("branch", "--show-current") != BRANCH:
        raise RuntimeError("unexpected branch")
    authority_path = OUT / "p3_preoutcome_authority.json"
    p3_manifest_path = OUT / "p3_development_manifest.json"
    if sha256(authority_path) != AUTHORITY_SHA256:
        raise RuntimeError("P3 authority hash mismatch")
    if sha256(p3_manifest_path) != P3_MANIFEST_SHA256:
        raise RuntimeError("P3 manifest hash mismatch")

    s3_receipt_path = HERE / "s3_preservation_receipt.json"
    s3_receipt = read_json(s3_receipt_path)
    if s3_receipt["backup_verification_status"] != "PASS":
        raise RuntimeError("S3 preservation has not passed")

    # Preserve the small, historically relevant restart receipts exactly.
    recovery_sources = [
        Path("/home/sagemaker-user/p3_restart_checkpoint/p3_events_before_restart_tail.jsonl"),
        Path("/home/sagemaker-user/p3_restart_checkpoint/p3_progress_before_restart.json"),
        Path("/home/sagemaker-user/p3_restart_checkpoint/process.json"),
        Path("/home/sagemaker-user/p3_restart_checkpoint/resume_p3_after_space_restart.sh"),
        Path("/home/sagemaker-user/p3_restart_checkpoint/resumed_pid"),
        Path("/home/sagemaker-user/p3_terminal_nvme_archive_2026-08-15/logs/p3_controller.log"),
        Path("/home/sagemaker-user/p3_terminal_nvme_archive_2026-08-15/logs/runtime_preflight_probe.mp4"),
    ]
    recovery_dir = HERE / "runtime_recovery"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    recovery_records = []
    for source in recovery_sources:
        if not source.is_file():
            raise RuntimeError(f"runtime recovery artifact missing: {source}")
        destination = recovery_dir / source.name
        if destination.exists() and sha256(destination) != sha256(source):
            raise RuntimeError(f"refusing to overwrite nonidentical recovery artifact: {destination}")
        if not destination.exists():
            shutil.copy2(source, destination)
        info = source.stat()
        recovery_records.append({
            "original_path": str(source),
            "preserved_relative_path": destination.relative_to(REPO).as_posix(),
            "bytes": info.st_size,
            "sha256": sha256(source),
            "source_and_preserved_bytes_exact": sha256(source) == sha256(destination),
            "original_mtime_utc": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            "expected_zero_byte": source.name == "p3_controller.log",
        })
    write_json(HERE / "runtime_recovery_manifest.json", {
        "artifact_id": "regime-a-prime-p3-runtime-recovery-preservation-v0.1",
        "timestamp": utc(),
        "records": recovery_records,
        "note": "The zero-byte controller log is a preserved historical fact, not a missing audit report.",
    })

    # Inventory and hash every forensic-audit artifact without rerunning analysis.
    audit_entries = []
    scripts_valid = True
    for path in sorted(p for p in AUDIT.rglob("*") if p.is_file()):
        entry = metadata(path)
        relative_inside_audit = path.relative_to(AUDIT).as_posix()
        if path.parent.name == "audit_scripts":
            role = "deterministic forensic audit script"
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                scripts_valid = False
        elif path.suffix == ".png":
            role = "forensic boundary-frame montage"
        elif path.name == "AUDIT_SUMMARY.md":
            role = "forensic audit terminal summary"
        else:
            role = "numbered forensic audit report/deliverable"
        entry.update({"audit_relative_path": relative_inside_audit, "role": role, "readable": os.access(path, os.R_OK)})
        audit_entries.append(entry)

    numbered_reports = [
        "00_evidence_inventory.json", "01_experiment_reconstruction.md", "02_gate_traceability.md",
        "03_visibility_forensics.md", "04_candidate_comparison.json", "05_p2_vs_p3_delta.md",
        "06_git_regression_audit.md", "07_runtime_recovery_audit.md", "08_exploratory_counterfactuals.md",
        "09_bug_hypothesis_log.md", "10_root_cause_matrix.md", "11_scientific_interpretation.md",
        "12_redesign_options.md",
    ]
    audit_inventory = read_json(AUDIT / "00_evidence_inventory.json")
    authority = read_json(authority_path)
    referenced_paths = {
        item["path"] for group in ("authority_and_control_artifacts", "code_artifacts")
        for item in audit_inventory[group]
    }
    referenced_paths.update(binding["path"] for binding in authority["source_bindings"].values())
    referenced_resolution = [
        {"relative_path": value, "resolves": (REPO / value).is_file()}
        for value in sorted(referenced_paths)
    ]
    audit_checks = {
        "numbered_report_deliverables_exactly_13": all((AUDIT / value).is_file() for value in numbered_reports),
        "boundary_frame_montage_present": (AUDIT / "03_visibility_boundary_frames_c01_ltr.png").is_file(),
        "audit_summary_present": (AUDIT / "AUDIT_SUMMARY.md").is_file(),
        "all_files_readable": all(item["readable"] for item in audit_entries),
        "no_zero_byte_audit_files": all(item["bytes"] > 0 for item in audit_entries),
        "deterministic_scripts_syntax_valid": scripts_valid,
        "referenced_repo_source_files_resolve": all(item["resolves"] for item in referenced_resolution),
    }
    audit_hash_manifest_path = HERE / "forensic_audit_hash_manifest.json"
    write_json(audit_hash_manifest_path, {
        "artifact_id": "regime-a-prime-p3-forensic-audit-hash-manifest-v0.1",
        "timestamp": utc(),
        "audit_status": "PASS_COMPLETE",
        "file_count": len(audit_entries),
        "numbered_report_deliverable_count": len(numbered_reports),
        "boundary_frame_montage_count": 1,
        "deterministic_script_count": sum(item["role"] == "deterministic forensic audit script" for item in audit_entries),
        "entries": audit_entries,
        "referenced_repo_source_files": referenced_resolution,
        "checks": audit_checks,
        "verification_status": "PASS" if all(audit_checks.values()) else "FAIL",
    })
    if not all(audit_checks.values()):
        raise RuntimeError("forensic audit integrity verification failed")

    controller_info = metadata(CONTROLLER)
    controller_info.update({
        "artifact_id": "regime-a-prime-p3-posthoc-controller-hash-v0.1",
        "timestamp": utc(),
        "baseline_repository_head": BASELINE_HEAD,
        "baseline_branch": BRANCH,
        "present_in_baseline_head": False,
        "relation_to_baseline_head": "ABSENT_FROM_HEAD_UNTRACKED_AT_EXECUTION_AND_FREEZE_BASELINE",
        "posthoc_preservation_hash_only": True,
        "provenance_caveat": CONTROLLER_CAVEAT,
    })
    write_json(HERE / "posthoc_p3_controller_receipt.json", controller_info)

    deferred = [
        {
            "source": "existing p3_terminal_forensic_audit_v0_1 finding D-P1/D-P2/D-P3",
            "file": "scripts/regime_a_prime_qualification_v0_1/p3_run_sequential.py",
            "line_or_function": "non_neural_gates, baseline lines 550-597",
            "description": "Path/state gate implements a narrower set of fields and row-count checks than the frozen authority specifies.",
            "evidence": "02_gate_traceability.md PATH / STATE GATE; independent reconstruction found full data exact and historical PASS unchanged.",
            "potential_impact": "Future resumed or reused units could be accepted without rechecking every authority-listed field; no P3 historical verdict change.",
        },
        {
            "source": "existing p3_terminal_forensic_audit_v0_1 findings D-V1 through D-V6",
            "file": "scripts/regime_a_prime_qualification_v0_1/p3_run_sequential.py",
            "line_or_function": "calibration_gate and non_neural_gates, baseline lines 529-597",
            "description": "Visibility qualification compares centre-point geometric visibility with existential rendered-silhouette visibility, uses pooled speed-confounded precision, and lacks the named identity/timestamp ambiguity check.",
            "evidence": "02_gate_traceability.md, 03_visibility_forensics.md, 04_candidate_comparison.json, 09_bug_hypothesis_log.md.",
            "potential_impact": "Dominant P3 gate failure mechanism; requires new prospective authority, not retroactive repair.",
        },
        {
            "source": "existing p3_terminal_forensic_audit_v0_1 finding #22",
            "file": "scripts/regime_a_prime_qualification_v0_1/p3_run_sequential.py",
            "line_or_function": "derive_artifacts, baseline lines 338-367",
            "description": "Frame, server tick, render frame, and action indices are treated as synchronous identities despite observed approximate 3.3-server-tick render lag.",
            "evidence": "03_visibility_forensics.md and 09_bug_hypothesis_log.md #22.",
            "potential_impact": "Temporal misalignment between rendered pixels and server-state labels.",
        },
        {
            "source": "existing p3_terminal_forensic_audit_v0_1 finding #31",
            "file": "scripts/regime_a_prime_qualification_v0_1/p2c_capture.py",
            "line_or_function": "package, baseline line 233",
            "description": "P3 development capture packages retain the default historical Regime A first25 scientific_run_id.",
            "evidence": "09_bug_hypothesis_log.md #31.",
            "potential_impact": "Bookkeeping/cohort-identity risk; scientific unit identities remain otherwise unique.",
        },
    ]
    write_json(HERE / "deferred_to_claude_repair.json", {
        "artifact_id": "regime-a-prime-p3-deferred-repair-register-v0.1",
        "timestamp": utc(),
        "scope": "Transcription of existing forensic-audit findings; no repair performed and no new interpretation added.",
        "DEFERRED_TO_CLAUDE_REPAIR": deferred,
    })

    terminal_result = read_json(OUT / "p3_terminal_result.json")
    candidate_outcomes = []
    capture_total = 0
    for candidate in terminal_result["candidate_history"]:
        cid = candidate["CANDIDATE_ID"]
        gate = read_json(OUT / f"p3_{cid.lower()}_non_neural_gates.json")
        capture_rows = []
        for path in sorted(OUT.glob(f"p3_{cid.lower()}_capture_ledger.jsonl")):
            capture_rows.extend(json.loads(line) for line in path.read_text().splitlines() if line)
        capture_total += len(capture_rows)
        candidate_outcomes.append({
            **candidate,
            "capture_units": len(capture_rows),
            "wall_units": sum(row["scene"] == "NORMAL" for row in capture_rows),
            "no_wall_units": sum(row["scene"] == "NO_WALL" for row in capture_rows),
            "visibility_calibration_precision": gate["visibility_calibration"]["precision"],
            "visibility_calibration_recall": gate["visibility_calibration"]["recall"],
            "normal_target_rows_passing": gate["normal_geometric_occluded_and_magenta_absent"],
            "normal_target_rows_expected": gate["target_rows_per_scene"],
            "no_wall_target_rows_passing": gate["no_wall_geometric_visible_and_magenta_detected"],
            "no_wall_target_rows_expected": gate["target_rows_per_scene"],
            "contaminated_normal_target_rows": (
                gate["target_rows_per_scene"] - gate["normal_geometric_occluded_and_magenta_absent"]
            ),
        })

    terminal_receipt_path = HERE / "p3_terminal_receipt.json"
    terminal_receipt = {
        "artifact_id": "regime-a-prime-p3-terminal-historical-freeze-receipt-v0.1",
        "timestamp": utc(),
        "P3_STATUS": terminal_result["p3_final_status"],
        "candidate_outcomes": candidate_outcomes,
        "capture_completeness": {
            "expected_scientific_units": 150,
            "verified_scientific_units": capture_total,
            "pair_structure_verified": all(
                item["wall_units"] == 25 and item["no_wall_units"] == 25
                for item in candidate_outcomes
            ),
        },
        "selected_candidate": terminal_result["candidate_selected"],
        "selected_speed": terminal_result["selected_speed"],
        "authority_hashes": {
            "p3_preoutcome_authority_sha256": AUTHORITY_SHA256,
            "p3_authority_validation_receipt_sha256": sha256(OUT / "p3_authority_validation_receipt.json"),
        },
        "manifest_hashes": {
            "p3_development_manifest_sha256": P3_MANIFEST_SHA256,
        },
        "forensic_audit_status": "PASS_COMPLETE",
        "forensic_audit_hash_manifest": audit_hash_manifest_path.relative_to(REPO).as_posix(),
        "forensic_audit_hash_manifest_sha256": sha256(audit_hash_manifest_path),
        "primary_s3_location": s3_receipt["primary_s3_location"],
        "secondary_s3_location": s3_receipt["secondary_s3_location"],
        "backup_verification_status": s3_receipt["backup_verification_status"],
        "primary_s3_object_count": s3_receipt["primary_s3_object_count"],
        "backup_s3_object_count": s3_receipt["backup_s3_object_count"],
        "primary_s3_bytes": s3_receipt["primary_s3_bytes"],
        "backup_s3_bytes": s3_receipt["backup_s3_bytes"],
        "s3_coverage_match": s3_receipt["checks"]["source_backup_relative_keys_exact"] and s3_receipt["checks"]["source_backup_sizes_exact"],
        "repository_head_at_freeze_baseline": BASELINE_HEAD,
        "branch": BRANCH,
        "upstream_remote_sha_at_freeze_baseline": git("ls-remote", "--heads", "origin", BRANCH).split()[0],
        "posthoc_controller_sha256": controller_info["sha256"],
        "posthoc_controller_receipt": (HERE / "posthoc_p3_controller_receipt.json").relative_to(REPO).as_posix(),
        "posthoc_controller_provenance_caveat": CONTROLLER_CAVEAT,
        "known_provenance_limitations": [
            CONTROLLER_CAVEAT,
            "p3_run_sequential.py was untracked and unhashed during execution; this provenance gap cannot be repaired retroactively.",
            "P3 raw data had a single durable S3 copy until this preservation operation created and verified the separate backup prefix.",
            "The historical p3_controller.pid named by p3_terminal_result.json was absent at freeze time; it was not recreated.",
            "The archived p3_controller.log is zero bytes; the durable events and restart checkpoint receipts remain available.",
            s3_receipt["sha256_verification_scope"],
        ],
        "historical_authority_modified": False,
        "historical_manifest_modified": False,
        "historical_verdicts_modified": False,
        "scientific_code_fixed": False,
        "tracked_source_code_modified": False,
        "contamination": {
            "visibility_target_row_contamination_detected": any(item["contaminated_normal_target_rows"] for item in candidate_outcomes),
            "restart_contamination_detected": False,
            "historical_terminal_contamination_status": terminal_result["contamination_status"],
        },
        "deferred_to_claude_repair": (HERE / "deferred_to_claude_repair.json").relative_to(REPO).as_posix(),
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
        "CONFIRMATORY_COLLECTION_AUTHORIZED": False,
        "NEXT_ALLOWED_ACTION": "Run Claude Code P2 temporal-alignment forensic impact audit from the frozen checkpoint. No new scientific collection.",
    }
    write_json(terminal_receipt_path, terminal_receipt)

    # Assemble a comprehensive local evidence manifest.  Existing audit inventory
    # hashes are retained as historical claims alongside freshly computed hashes.
    roles: dict[str, str] = {}
    recorded_claims: dict[str, list[dict]] = {}
    for group in ("authority_and_control_artifacts", "code_artifacts"):
        for item in audit_inventory[group]:
            add_role(roles, item["path"], item["role"])
            recorded_claims.setdefault(item["path"], []).append({
                "recorded_in": "p3_terminal_forensic_audit_v0_1/00_evidence_inventory.json",
                "sha256": item["sha256"],
            })
    for name, binding in authority["source_bindings"].items():
        add_role(roles, binding["path"], f"P3 authority source binding: {name}")
        recorded_claims.setdefault(binding["path"], []).append({
            "recorded_in": "p3_preoutcome_authority.json source_bindings",
            "sha256": binding["sha256"],
        })
    for path in sorted(OUT.glob("p3*.json")) + sorted(OUT.glob("p3*.jsonl")):
        add_role(roles, path.relative_to(REPO).as_posix(), "P3 authority, manifest, progress, event, ledger, gate, or terminal artifact")
    extra_code = {
        "scripts/regime_a_prime_qualification_v0_1/p2d_extract.py": "P2/P3 shared layer-4 extraction code imported by controller",
        "scripts/regime_a_prime_qualification_v0_1/p2e_analyze.py": "P2/P3 shared readout analysis code imported by controller",
        "scripts/run_regime_a.py": "projection/detector-row code imported by controller",
        "src/mineocclude/regime_a_first25_analysis.py": "metric code imported by controller",
        "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/MineOccludeServer.java": "server mod source hash checked by controller",
        "data/handoff_e/person_e_v0_4_homography_refit_v0_2/layout_01_homography.json": "homography input used by capture apparatus",
    }
    for path, role in extra_code.items():
        add_role(roles, path, role)
    for path in sorted(p for p in AUDIT.rglob("*") if p.is_file()):
        add_role(roles, path.relative_to(REPO).as_posix(), "P3 terminal forensic audit artifact")
    freeze_roles = {
        "verify_s3_preservation.py": "read-only deterministic S3 preservation verifier",
        "build_freeze_package.py": "deterministic historical freeze package builder",
        "s3_preservation_receipt.json": "verified second-durable-copy receipt",
        "forensic_audit_hash_manifest.json": "forensic audit file hash manifest",
        "posthoc_p3_controller_receipt.json": "post-hoc controller hash and metadata receipt",
        "runtime_recovery_manifest.json": "runtime recovery preservation manifest",
        "deferred_to_claude_repair.json": "existing audit findings deferred without repair",
        "p3_terminal_receipt.json": "machine-readable frozen P3 terminal state",
    }
    for name, role in freeze_roles.items():
        add_role(roles, (HERE / name).relative_to(REPO).as_posix(), role)
    for path in sorted(recovery_dir.iterdir()):
        add_role(roles, path.relative_to(REPO).as_posix(), "byte-exact snapshot of runtime recovery evidence")

    terminal_artifact_claims = read_json(OUT / "p3_terminal_result.json")["candidate_artifacts"]
    for item in terminal_artifact_claims:
        recorded_claims.setdefault(item["path"], []).append({
            "recorded_in": "p3_terminal_result.json candidate_artifacts",
            "sha256": item["sha256"],
            "bytes": item["byte_size"],
        })
    entries = []
    for relative, role in sorted(roles.items()):
        item = metadata(REPO / relative)
        item["role"] = role
        item["historical_sha256_records"] = recorded_claims.get(relative, [])
        item["historical_sha256_records_match"] = all(
            claim["sha256"] == item["sha256"] for claim in item["historical_sha256_records"]
        )
        entries.append(item)

    external_runtime = []
    for path, role, recorded_hash in (
        (Path("/home/sagemaker-user/mineocclude-server/mods/mineocclude-0.1.1.jar"), "installed server mod used by P3", terminal_result["preflight"]["installed_mod_sha256"]),
    ):
        external_runtime.append({
            "absolute_path": str(path), "role": role, "exists_at_freeze": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha256(path) if path.is_file() else None,
            "historically_recorded_sha256": recorded_hash,
            "recorded_hash_matches_current": path.is_file() and sha256(path) == recorded_hash,
        })
    evidence_manifest = {
        "artifact_id": "regime-a-prime-p3-terminal-historical-evidence-manifest-v0.1",
        "timestamp": utc(),
        "scope": "P3 historical preservation; no scientific repair or new evidence",
        "repository": {
            "path": str(REPO), "branch": BRANCH, "baseline_head": BASELINE_HEAD,
            "upstream": f"origin/{BRANCH}",
            "upstream_sha_at_baseline": terminal_receipt["upstream_remote_sha_at_freeze_baseline"],
            "origin_fetch_url": git("remote", "get-url", "origin"),
            "p2_closeout_commit": authority["source_p2_closeout_commit"],
            "p3_authority_commit": BASELINE_HEAD,
        },
        "entry_count": len(entries),
        "entries": entries,
        "external_runtime_artifacts": external_runtime,
        "s3": {
            "source": s3_receipt["primary_s3_location"],
            "backup": s3_receipt["secondary_s3_location"],
            "verification_receipt": s3_receipt_path.relative_to(REPO).as_posix(),
            "unit_sha256_manifests_verified": s3_receipt["unit_sha256_manifest_count_verified"],
            "historical_per_object_sha256_values": "preserved in each S3 unit sha256_manifest.json; coverage verified by s3_preservation_receipt.json",
        },
        "historical_missing_artifacts": [
            {
                "relative_path": "docs/status/integration/regime_a_prime_qualification_v0_1/p3_controller.pid",
                "exists_at_freeze": False,
                "historically_recorded_bytes": 5,
                "historically_recorded_sha256": "c40486120c84c09d834e302c3b53b9692281f15d9f2c8b1a7c5ed549ebc54080",
                "role": "ephemeral controller PID file listed by the terminal result; not recreated",
            }
        ],
        "self_exclusion": "This manifest cannot include its own SHA-256 without recursion.",
        "P3_AUTHORITY_UNMODIFIED": True,
        "P3_MANIFEST_UNMODIFIED": True,
        "P3_HISTORICAL_VERDICTS_UNMODIFIED": True,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
    }
    write_json(HERE / "historical_evidence_manifest.json", evidence_manifest)


if __name__ == "__main__":
    main()
