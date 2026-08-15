"""STEP 7: autonomous deterministic capture runner for the 25 P2 NO_WALL runs.

Designed to run unattended: it consumes the already-frozen 25-spec manifest and
advances specs 1..25 with no external reasoning. Per spec it verifies frozen
identity, captures the NO_WALL run, validates integrity and exact path identity,
persists artifacts durably with hashes, appends an fsync'd ledger entry, and
updates a compact progress artifact. Failures are retried on the SAME frozen
spec only. Systemic failure stops the batch early rather than burning runtime.

Never substitutes a seed, alters target ticks/motion/camera, regenerates the
scientific manifest, skips a difficult unit, or makes any outcome-dependent
decision. tau labels come from the frozen wall-derived manifest.

Resumable: runs already COMPLETE_VALIDATED_DURABLE in the ledger are skipped.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np

from p2_common import (
    BRANCH,
    OUT,
    REPO,
    S3_PREFIX,
    WORK,
    CaptureSession,
    expected_path,
    p2_episode_id,
    p2_run_id,
    raw_capture_spec_hash,
    read_jsonl,
    sha256_file,
    source_specs,
    wall_coordinates,
    write_json,
)

MAX_ATTEMPTS = 3
CAPTURES = WORK / "captures"
LEDGER = OUT / "p2_capture_ledger.jsonl"
PROGRESS = OUT / "p2_capture_progress.json"

# Errors that indicate a systemic apparatus problem rather than a transient one.
HARD_MARKERS = (
    "requires scene mode", "NO_WALL_MISMATCH", "PRECHECK_FAILED",
    "identity mismatch", "path identity failed", "hash mismatch",
    "No space left on device", "validator refused",
)

PATCHED_SOURCE_SHA256 = "3c37227654415956ab34a0c3245fe25697ed8c2b8d18dcbca7373a21f5c32de0"
PATCHED_JAR_SHA256 = "febf31cad7c6de003a6d2d87ed9183c6a6739e086e293b30e92999520e3bfaba"
MOD_SOURCE = REPO / (
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/MineOccludeServer.java"
)
SERVER_MOD = Path("/home/sagemaker-user/mineocclude-server/mods/mineocclude-0.1.1.jar")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def append_ledger(entry: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def completed_records() -> dict[str, dict[str, Any]]:
    if not LEDGER.exists():
        return {}
    return {
        r["p2_no_wall_run_id"]: r
        for r in read_jsonl(LEDGER)
        if r.get("status") == "COMPLETE_VALIDATED_DURABLE"
    }


def write_progress(state: dict[str, Any]) -> None:
    write_json(PROGRESS, state)


def classify(error: str) -> str:
    return "FAILED_HARD" if any(m in error for m in HARD_MARKERS) else "FAILED_RETRYABLE"


def preflight() -> None:
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=REPO, capture_output=True, text=True,
        check=True,
    ).stdout.strip()
    if branch != BRANCH:
        raise RuntimeError(f"PRECHECK_FAILED: branch identity mismatch: {branch}")
    if sha256_file(MOD_SOURCE) != PATCHED_SOURCE_SHA256:
        raise RuntimeError("PRECHECK_FAILED: patched source hash mismatch")
    if sha256_file(SERVER_MOD) != PATCHED_JAR_SHA256:
        raise RuntimeError("PRECHECK_FAILED: installed patched jar hash mismatch")
    amendment = json.loads((OUT / "p2_patch_acceptance_supersession.json").read_text())
    if (amendment.get("effective_status") != "FROZEN_PROSPECTIVE_PRE_OUTCOME"
            or amendment.get("patch_acceptance_status") != "PASS"
            or not amendment.get("no_pixel_tolerance_introduced")):
        raise RuntimeError("PRECHECK_FAILED: patch acceptance authority mismatch")
    for outcome in ("p2_activation_manifest.json", "p2_best_k_results.json",
                    "p2_full_results.json"):
        if (OUT / outcome).exists():
            raise RuntimeError(f"PRECHECK_FAILED: scientific outcome already exists: {outcome}")
    home_free = shutil.disk_usage("/home/sagemaker-user").free
    nvme_free = shutil.disk_usage("/mnt/sagemaker-nvme").free
    if home_free < 512 * (1 << 20) or nvme_free < 20 * (1 << 30):
        raise RuntimeError(
            f"PRECHECK_FAILED: BLOCKED_DISK home_free={home_free} nvme_free={nvme_free}"
        )


def verify_renderer_identity() -> None:
    env = {**os.environ, "DISPLAY": ":99"}
    proc = subprocess.run(["glxinfo", "-B"], env=env, capture_output=True, text=True)
    identity = proc.stdout + proc.stderr
    required = ("llvmpipe", "LLVM 20.1.2", "Mesa 25.2.8")
    if proc.returncode != 0 or any(value not in identity for value in required):
        raise RuntimeError("PRECHECK_FAILED: current renderer identity mismatch")
    xvfb = subprocess.run(["Xvfb", "-version"], capture_output=True, text=True)
    if "21.1.12" not in xvfb.stdout + xvfb.stderr:
        raise RuntimeError("PRECHECK_FAILED: Xvfb identity mismatch")


def build_artifacts(spec: dict, destination: Path, frozen_taus: dict[int, int]) -> dict:
    """Derive visibility/frame_map/coordinates and assert no-wall identity."""
    from mineocclude.vision.magenta import HsvRange, detect_magenta
    from scripts.run_regime_a import detector_rgb_rows, project_world_to_coordinates

    raw = destination / "raw"
    state = read_jsonl(raw / "server_state.jsonl")
    ticks = read_jsonl(raw / "client_tick.jsonl")
    actions = read_jsonl(raw / "actions.jsonl")
    frames = len(state)
    if not (len(ticks) == len(actions) == frames):
        raise RuntimeError("capture stream cardinality mismatch")

    spec_id = str(spec["trajectory_spec_id"])
    capture_hash = raw_capture_spec_hash(spec)
    uuids = {row.get("target_entity_uuid") for row in state}
    if len(uuids) != 1 or None in uuids:
        raise RuntimeError("target entity UUID was not retained")
    for index, row in enumerate(state):
        if (row.get("server_tick") != index
                or row.get("trajectory_spec_id") != spec_id
                or row.get("spec_hash") != capture_hash
                or row.get("seed") != spec["seed"]
                or row.get("scene") != "NO_WALL"
                or row.get("target_respawn_count") != 0):
            raise RuntimeError(f"no-wall state identity mismatch at frame {index}")
        if ticks[index].get("server_tick") != index or actions[index].get("server_tick") != index:
            raise RuntimeError("client/server frame alignment mismatch")

    config = json.loads(
        (REPO / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1"
                "/detector_candidate_config.json").read_text()
    )["configuration"]["detector_settings"]
    thresholds = tuple(HsvRange(*v) for v in config["hsv_ranges"])
    homography = json.loads(
        (REPO / "data/handoff_e/person_e_v0_4_homography_refit_v0_2"
                "/layout_01_homography.json").read_text())

    visibility, frame_map, coordinates = [], [], []
    for index, row in enumerate(state):
        result = detect_magenta(
            detector_rgb_rows(raw / f"frames/{index:06d}.png", expected_size=(640, 360)),
            hsv_ranges=thresholds,
            min_area_pixels=config["min_area_pixels"],
            max_area_pixels=config["max_area_pixels"],
            open_iterations=config["open_iterations"],
            close_iterations=config["close_iterations"],
            morphology_radius_pixels=config["morphology_radius_pixels"],
            connectivity=config["connectivity"])
        key = {"trajectory_id": spec_id, "model_frame_idx": index, "server_tick": index,
               "render_frame_idx": index, "action_idx": index}
        visibility.append({
            **key,
            "geometric_status": "visible" if row["geometric_visible"] else "occluded",
            "magenta_status": result.status,
            "magenta_area_pixels": result.area_pixels,
            "scene": "NO_WALL",
            "tau": frozen_taus.get(index),
            "duration_bin": None,
            "primary_hidden_eligible": False,
        })
        frame_map.append({**key, "target_entity_uuid": next(iter(uuids)),
                          "frame_path": f"raw/frames/{index:06d}.png"})
        coordinates.append({**key, **project_world_to_coordinates(
            float(row["sheep_x"]), float(row["sheep_z"]), homography["inverse_matrix"])})

    _write_jsonl(raw / "visibility.jsonl", visibility)
    _write_jsonl(raw / "frame_map.jsonl", frame_map)
    _write_jsonl(destination / "coordinates.jsonl", coordinates)
    return {"frames": frames, "visibility": visibility}


def package(spec: dict, destination: Path, episode_id: int, live: Any) -> None:
    from mineocclude.data.build_dataset import process_episode
    from mineocclude.data.package_episode import package_and_validate

    server_episode = live.SERVER_ROOT / f"mineocclude_out/episode_{episode_id}"
    client_episode = live.CLIENT_ROOT / f"mineocclude_client_out/episode_{episode_id}"
    noise_path = live.SERVER_ROOT / f"mineocclude_schedules/episode_{episode_id}.jsonl"
    motion_path = live.SERVER_ROOT / f"mineocclude_motion_schedules/episode_{episode_id}.json"

    processed = destination / "capture_validation"
    if processed.exists():
        shutil.rmtree(processed)
    summary = process_episode(str(server_episode), str(client_episode), str(processed),
                              run_empirical=True, canonical_640=True)
    if not summary.get("accepted"):
        raise RuntimeError(f"capture adapter refused trajectory: {summary.get('problems')}")
    bundle = Path(str(summary.get("frame_map", ""))).resolve().parent
    _pkg, result = package_and_validate(
        str(bundle), str(server_episode), str(client_episode), str(noise_path),
        str(REPO), str(spec.get("scientific_run_id", "mineocclude-regime-a-first25-v2")))
    if not result.accepted:
        raise RuntimeError("frozen capture-package validator refused trajectory")
    shutil.copy2(bundle / "capture_package_v0_1.json",
                 destination / "capture_package_v0_1.json")
    shutil.copy2(noise_path, destination / "noise_schedule.jsonl")
    shutil.copy2(motion_path, destination / "motion_schedule.json")


def purge_runtime_episode(live: Any, episode_id: int) -> None:
    """Free the $HOME volume immediately; it is small and fills fast."""
    for path in (live.SERVER_ROOT / f"mineocclude_out/episode_{episode_id}",
                 live.CLIENT_ROOT / f"mineocclude_client_out/episode_{episode_id}"):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def path_identity(spec: dict, destination: Path, schedule: Any) -> dict[str, Any]:
    spec_id = str(spec["trajectory_spec_id"])
    state = read_jsonl(destination / "raw/server_state.jsonl")
    observed = np.asarray([float(r["sheep_x"]) for r in state], dtype=np.float64)
    wall_map = wall_coordinates(spec_id)
    wall = np.asarray([wall_map[i] for i in range(len(observed))], dtype=np.float64)
    analytic = np.asarray(expected_path(spec, schedule), dtype=np.float64)
    diff = np.abs(observed - wall)
    return {
        "max_abs_diff_vs_wall": float(diff.max()),
        "frames_bitwise_identical": int((observed == wall).sum()),
        "frames": int(len(observed)),
        "bitwise_identical": bool((observed == wall).all()),
        "max_abs_diff_vs_analytic": float(np.abs(observed - analytic).max()),
    }


def persist_durably(run_id: str, destination: Path) -> dict[str, Any]:
    files = sorted(
        p for p in destination.rglob("*")
        if p.is_file() and p.name != "sha256_manifest.json"
    )
    checksums = {
        "artifact_id": "regime-a-prime-p2-capture-checksums-v0.1",
        "p2_no_wall_run_id": run_id,
        "file_count": len(files),
        "files": [
            {
                "path": p.relative_to(destination).as_posix(),
                "byte_size": p.stat().st_size,
                "sha256": sha256_file(p),
            }
            for p in files
        ],
    }
    manifest_path = destination / "sha256_manifest.json"
    write_json(manifest_path, checksums)

    uri = f"{S3_PREFIX}/{run_id}"
    proc = subprocess.run(["aws", "s3", "sync", str(destination), uri, "--only-show-errors"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"durable sync failed: {proc.stderr.strip()[:200]}")
    remote = subprocess.run(
        ["aws", "s3", "cp", f"{uri}/sha256_manifest.json", "-", "--only-show-errors"],
        capture_output=True,
    )
    if remote.returncode != 0 or remote.stdout != manifest_path.read_bytes():
        raise RuntimeError("durable checksum manifest verification failed")
    all_files = sorted(p for p in destination.rglob("*") if p.is_file())
    return {
        "durable_uri": uri,
        "object_count": len(all_files),
        "byte_size": sum(p.stat().st_size for p in all_files),
        "checksum_manifest_sha256": sha256_file(manifest_path),
        "checksum_manifest_remote_readback_exact": True,
    }


def main() -> int:
    preflight()
    specs = source_specs()
    manifest = json.loads((OUT / "p2_target_row_manifest.json").read_text())
    authority = json.loads((OUT / "p2_preoutcome_authority.json").read_text())
    exact_required = authority["path_identity_rules"]["rule"] == "EXACT_EQUALITY_REQUIRED"
    epsilon = float(authority["path_identity_rules"]["epsilon_path"])

    taus_by_spec: dict[str, dict[int, int]] = {}
    for row in manifest["rows"]:
        taus_by_spec.setdefault(row["source_regime_a_spec_id"], {})[
            int(row["target_model_frame_idx"])] = int(row["tau"])

    CAPTURES.mkdir(parents=True, exist_ok=True)
    complete_by_run = completed_records()
    done = set(complete_by_run)
    records: list[dict[str, Any]] = []
    retries = 0
    started = time.monotonic()
    campaign_status = "RUNNING"
    last_error = None
    last_completed = None

    def progress(current: str | None) -> None:
        write_progress({
            "artifact_id": "regime-a-prime-p2-capture-progress-v0.1",
            "total_expected": 25,
            "complete_validated_durable": len(done),
            "currently_running": current,
            "current_run_id": current,
            "retryable_failed": sum(1 for r in records if r.get("status") == "FAILED_RETRYABLE"),
            "hard_failed": sum(1 for r in records if r.get("status") == "FAILED_HARD"),
            "remaining": 25 - len(done),
            "last_completed_run_id": last_completed,
            "campaign_status": campaign_status,
            "last_error_code": last_error,
            "capture_retries": retries,
            "elapsed_seconds": time.monotonic() - started,
        })

    progress(None)
    try:
        with CaptureSession("nowall") as session:
            verify_renderer_identity()
            for spec in specs:
                spec_id = str(spec["trajectory_spec_id"])
                run_id = p2_run_id(spec_id)
                if run_id in done:
                    continue
                episode = p2_episode_id(spec)
                destination = CAPTURES / run_id
                progress(run_id)
                accepted = False

                for attempt in range(1, MAX_ATTEMPTS + 1):
                    entry: dict[str, Any] = {
                        "p2_no_wall_run_id": run_id,
                        "source_regime_a_spec_id": spec_id,
                        "episode_id": episode,
                        "attempt": attempt,
                        "seed": int(spec["seed"]),
                        "seed_substituted": False,
                        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                    try:
                        if destination.exists():
                            shutil.rmtree(destination)
                        destination.mkdir(parents=True)
                        info = session.capture(spec, episode, destination)
                        build_artifacts(spec, destination, taus_by_spec[spec_id])
                        package(spec, destination, episode, session.live)
                        identity = path_identity(spec, destination, info["schedule"])
                        ok = (identity["bitwise_identical"] if exact_required
                              else identity["max_abs_diff_vs_wall"] <= epsilon)
                        if not ok:
                            raise RuntimeError(
                                f"path identity failed: max|diff|="
                                f"{identity['max_abs_diff_vs_wall']}")
                        vis = read_jsonl(destination / "raw/visibility.jsonl")
                        targets = [r for r in vis if r["tau"] is not None]
                        if len(targets) != 19:
                            raise RuntimeError(f"expected 19 target rows, got {len(targets)}")
                        durable = persist_durably(run_id, destination)
                        purge_runtime_episode(session.live, episode)

                        visible = sum(1 for r in targets if r["magenta_status"] == "detected")
                        geo = sum(1 for r in targets if r["geometric_status"] == "visible")
                        entry.update({
                            "status": "COMPLETE_VALIDATED_DURABLE",
                            "direction": spec["direction"],
                            "outer_fold": int(spec["outer_fold"]),
                            "frames": info["frames"],
                            "attempts": attempt,
                            "capture_seconds": info["capture_seconds"],
                            "path_identity": identity,
                            "target_rows": len(targets),
                            "target_rows_magenta_detected": visible,
                            "target_rows_geometric_visible": geo,
                            "durable": durable,
                            "local_root": str(destination),
                            "capture_package_sha256": sha256_file(
                                destination / "capture_package_v0_1.json"),
                            "visibility_sha256": sha256_file(
                                destination / "raw/visibility.jsonl"),
                            "coordinates_sha256": sha256_file(
                                destination / "coordinates.jsonl"),
                        })
                        complete_by_run[run_id] = entry
                        accepted = True
                        done.add(run_id)
                        last_completed = run_id
                    except Exception as exc:  # noqa: BLE001 - recorded then retried
                        message = f"{type(exc).__name__}: {exc}"
                        kind = classify(message)
                        entry.update({"status": kind, "error": message[:400]})
                        last_error = kind
                        records.append({"p2_no_wall_run_id": run_id, "status": kind,
                                        "attempt": attempt, "error": message[:400]})
                        purge_runtime_episode(session.live, episode)
                    append_ledger(entry)
                    progress(run_id)
                    if accepted:
                        break
                    if entry["status"] == "FAILED_HARD":
                        campaign_status = "STOPPED_SYSTEMIC_FAILURE"
                        progress(None)
                        raise RuntimeError(
                            f"SYSTEMIC: {run_id} failed hard; stopping remaining campaign"
                        )
                    if attempt < MAX_ATTEMPTS:
                        retries += 1

                if not accepted:
                    campaign_status = "STOPPED_RETRY_EXHAUSTED"
                    progress(None)
                    raise RuntimeError(
                        f"SYSTEMIC: {run_id} exhausted {MAX_ATTEMPTS} retryable attempts; "
                        "stopping remaining campaign"
                    )
        campaign_status = "COMPLETE" if len(done) == 25 else "INCOMPLETE"
    except Exception:
        if campaign_status == "RUNNING":
            campaign_status = "STOPPED_SYSTEMIC_FAILURE"
            last_error = "FAILED_HARD"
        raise
    finally:
        progress(None)

    complete = [complete_by_run[p2_run_id(str(spec["trajectory_spec_id"]))]
                for spec in specs
                if p2_run_id(str(spec["trajectory_spec_id"])) in complete_by_run]
    payload = {
        "artifact_id": "regime-a-prime-p2-capture-manifest-v0.3",
        "schema_version": "1.2",
        "phase": "P2",
        "classification": "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "status": "PASS" if len(done) == 25 else "BLOCKED",
        "scene": "NO_WALL",
        "wall_runs_recollected": 0,
        "no_wall_run_count": len(complete),
        "complete_validated_durable_count": len(done),
        "capture_retries": retries,
        "total_target_rows": sum(r["target_rows"] for r in complete),
        "capture_wall_clock_seconds": time.monotonic() - started,
        "campaign_status": campaign_status,
        "durable_prefix": S3_PREFIX,
        "runs": complete,
    }
    write_json(OUT / "p2_capture_manifest.json", payload)
    print(f"P2_CAPTURE_STATUS={payload['status']} campaign={campaign_status}")
    print(f"COMPLETE_VALIDATED_DURABLE={len(done)}/25 retries={retries}")
    return 0 if len(done) == 25 else 1


if __name__ == "__main__":
    raise SystemExit(main())
