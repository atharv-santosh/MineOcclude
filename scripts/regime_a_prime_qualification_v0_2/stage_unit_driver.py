#!/usr/bin/env python3
"""One-unit runner with independently derived runtime, path, and durability receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "scripts/regime_a_prime_qualification_v0_1"
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(LEGACY)]

from mineocclude.prospective.development_workflow import (  # noqa: E402
    RUNTIME_CRITICAL_SOURCE_PATHS, atomic_write_json, canonical_payload_sha256,
    causal_fir_targets, derive_effective_capture_spec, load_json, probe_evidence_digest,
    require_capture_spec_contract,
    require_preoutcome_provenance, require_stage2_authorization,
    require_stage_manifest_binding, resolve_qualified_runtime,
    runtime_critical_source_closure_sha256, runtime_probe_identity_tokens,
    sha256_file, stage_run_inventory_sha256,
    verify_probe_execution, verify_runtime_identity,
)
from mineocclude.prospective.package_binding import artifact_version_tag  # noqa: E402


def required_runtime_sources() -> list[Path]:
    return [ROOT / relative for relative in RUNTIME_CRITICAL_SOURCE_PATHS]


def unit_from(manifest: dict, unit_id: str) -> dict:
    matches = [unit for unit in manifest["units"] if unit.get("unit_id") == unit_id]
    if len(matches) != 1:
        raise RuntimeError(f"unit identity must resolve exactly once: {unit_id}")
    return matches[0]


def subprocess_text(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout + result.stderr


def digest_bound_receipt(payload: dict) -> dict:
    """Bind a deterministic SHA-256 over the receipt's own canonical JSON.

    Not a signature: no asymmetric key or authenticated signer exists here. It
    detects post-hoc edits to a receipt; it does not establish authorship. Probe
    authorship is constrained by ``probe_execution`` and its verifier.
    """
    payload = dict(payload)
    payload["payload_sha256"] = canonical_payload_sha256(payload)
    return payload


def require_capture_authorization(stage: str, manifest: dict, manifest_path: Path,
                                  authority_path: Path, unit: dict | None = None) -> str:
    """Prevent direct invocation of a manifest command from bypassing authorization."""
    head = subprocess_text(["git", "rev-parse", "HEAD"], cwd=ROOT).strip()
    # A6: the requested stage must match the manifest, namespace, and unit role
    # before any authorization receipt is even looked for.
    binding = require_stage_manifest_binding(stage, manifest, manifest_path=manifest_path,
                                             authority=load_json(authority_path), unit=unit)
    provenance_path = Path(os.environ.get("MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH", ""))
    if not provenance_path.is_file():
        raise PermissionError("bound pre-outcome provenance receipt is required")
    require_preoutcome_provenance(load_json(provenance_path), authority_path=authority_path,
        manifest_path=manifest_path, required_source_paths=required_runtime_sources())
    if stage == "stage1-capture":
        authorization_path = Path(os.environ.get("MINEOCCLUDE_STAGE1_AUTHORIZATION_PATH", ""))
        if not authorization_path.is_file():
            raise PermissionError("separate Stage-1 authorization receipt is required")
        receipt = load_json(authorization_path)
        expected = {"artifact_id": binding["authorization_artifact_id"],
            "status": "FROZEN_AUTHORIZED", "STAGE_1_COLLECTION_AUTHORIZED": True,
            "STAGE_2_COLLECTION_AUTHORIZED": False, "confirmatory_collection_authorized": False,
            "authority_sha256": sha256_file(authority_path),
            "stage1_manifest_sha256": sha256_file(manifest_path), "source_commit_sha": head,
            "expected_run_namespace": manifest["run_namespace"],
            # The authorization names the exact stage it authorizes, the exact
            # unit inventory it was derived against, and the exact apparatus
            # source closure it was verified over, so a receipt cannot be
            # carried to another stage, another unit set, or an edited tree.
            "authorized_stage": binding["stage"], "stage_role": binding["stage_role"],
            "stage1_run_inventory_sha256": stage_run_inventory_sha256(manifest),
            "runtime_critical_source_closure_sha256": runtime_critical_source_closure_sha256(ROOT),
            "preoutcome_provenance_receipt_sha256": sha256_file(provenance_path)}
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise PermissionError("Stage-1 authorization binding mismatch")
        if receipt.get("authorization_payload_sha256") != canonical_payload_sha256(
                receipt, omit="authorization_payload_sha256"):
            raise PermissionError("Stage-1 authorization payload hash mismatch")
    elif stage.startswith("stage2-"):
        authorization_path = Path(os.environ.get("MINEOCCLUDE_STAGE2_AUTHORIZATION_PATH", ""))
        evidence_path = Path(os.environ.get("MINEOCCLUDE_STAGE1_EVIDENCE_PATH", ""))
        decision_path = Path(os.environ.get("MINEOCCLUDE_STAGE1_DECISION_PATH", ""))
        stage1_manifest_path = Path(os.environ.get("MINEOCCLUDE_STAGE1_MANIFEST_PATH", ""))
        if (not authorization_path.is_file() or not evidence_path.is_file()
                or not decision_path.is_file() or not stage1_manifest_path.is_file()):
            raise PermissionError("complete Stage-2 authorization artifacts are required")
        require_stage2_authorization(manifest, load_json(authorization_path),
            authorization_receipt_path=authorization_path,
            stage1_decision=load_json(decision_path), authority_path=authority_path,
            manifest_path=manifest_path, stage1_manifest_path=stage1_manifest_path,
            stage1_evidence_path=evidence_path, stage1_decision_path=decision_path,
            current_source_commit=head,
            preoutcome_provenance_path=provenance_path)
    else:
        raise PermissionError(f"unknown capture stage: {stage}")
    return head


PROBE_PRODUCER = "scripts.regime_a_prime_qualification_v0_2.stage_unit_driver.probe_runtime"
PROBE_SOURCE_RELATIVE = "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py"


def _resolve_executable(name: str, environment: dict) -> str:
    """Absolute path of the executable that will actually run."""
    resolved = shutil.which(name, path=environment.get("PATH", os.defpath))
    if resolved is None:
        raise RuntimeError(f"probe executable is absent from the reconstructed PATH: {name}")
    return str(Path(resolved).resolve())


def _run_probe(command_id: str, argv: list[str], environment: dict) -> dict:
    """Execute one probe and record everything a verifier needs to re-derive it.

    Records the exact argv, the resolved executable and its bytes, the process
    exit status, and the normalized combined output with its digest. Nothing
    here is a claim about success; adjudication is the verifier's.
    """
    result = subprocess.run(argv, cwd=ROOT, env=environment, capture_output=True,
                            text=True, check=False)
    output = result.stdout + result.stderr
    return {"command_id": command_id, "argv": argv, "executable_path": argv[0],
            "executable_sha256": sha256_file(Path(argv[0])),
            "working_directory": str(ROOT), "exit_status": result.returncode,
            "normalized_output": output,
            "normalized_output_sha256": hashlib.sha256(output.encode()).hexdigest()}


def probe_runtime(authority: dict) -> dict:
    """Independently measure the runtime and emit reproducible probe evidence.

    Every identity claim below is carried by a recorded process execution --
    argv, resolved executable bytes, exit status, normalized output -- rather
    than by a boolean this function sets. ``verify_probe_execution`` re-derives
    the whole record from disk, so a receipt that merely asserts PASS is
    rejected.
    """
    expected = authority["runtime_identity_policy"]
    fields = expected["required_fields"]
    runtime = resolve_qualified_runtime(authority)
    environment = runtime["environment"]
    branch = subprocess_text(["git", "branch", "--show-current"], cwd=ROOT).strip()
    head = subprocess_text(["git", "rev-parse", "HEAD"], cwd=ROOT).strip()

    invocations = [
        # The pinned interpreter by absolute path; a `java` inherited from PATH
        # would be an unpinned runtime whose bytes are not the recorded bytes.
        _run_probe("java_version", [runtime["java_executable"], "-version"], environment),
        _run_probe("renderer", [_resolve_executable("glxinfo", environment), "-B"], environment),
        _run_probe("xvfb", [_resolve_executable("dpkg-query", environment), "-W",
                            "-f=${Version}", "xvfb"], environment),
    ]
    tokens = runtime_probe_identity_tokens(fields)
    by_id = {item["command_id"]: item for item in invocations}
    for command_id, required in tokens.items():
        invocation = by_id[command_id]
        if invocation["exit_status"] != 0:
            raise RuntimeError(
                f"{command_id} probe exited {invocation['exit_status']}")
        missing = [token for token in required if token not in invocation["normalized_output"]]
        if missing:
            raise RuntimeError(f"{command_id} identity mismatch: missing {missing}")

    paths = expected["critical_file_paths"]
    hashes = {name: sha256_file(Path(path) if Path(path).is_absolute() else ROOT / path)
              for name, path in paths.items()}
    with zipfile.ZipFile(paths["minecraft_server_jar"]) as archive:
        minecraft_version = json.loads(archive.read("version.json"))["id"]
    measurements = {"branch": branch, "head": head, "java": fields["java"],
        "minecraft_version": minecraft_version, "renderer": fields["renderer"],
        "xvfb": fields["xvfb"], "mesa": fields["mesa"],
        "detector_config_id": fields["detector_config_id"]}
    execution = {"producer": PROBE_PRODUCER,
        "probe_source_path": PROBE_SOURCE_RELATIVE,
        "probe_source_sha256": sha256_file(ROOT / PROBE_SOURCE_RELATIVE),
        "java_home": runtime["java_home"], "display": runtime["display"],
        "invocations": invocations, "measurements": measurements,
        "apparatus_file_sha256": hashes,
        "runtime_source_sha256": {path.relative_to(ROOT).as_posix(): sha256_file(path)
                                  for path in required_runtime_sources()}}
    observed = {"independently_derived": True, "asserted_by_evidence_builder": False,
        **measurements, "critical_file_sha256": hashes,
        "java_version_probe_sha256": by_id["java_version"]["normalized_output_sha256"],
        "renderer_probe_sha256": by_id["renderer"]["normalized_output_sha256"],
        "xvfb_probe_sha256": by_id["xvfb"]["normalized_output_sha256"],
        "runtime_source_sha256": execution["runtime_source_sha256"],
        "probe_execution": execution,
        "probe_evidence_sha256": probe_evidence_digest(execution)}
    verify_runtime_identity(expected, observed)
    receipt = digest_bound_receipt({"status": "PASS", **observed})
    verify_probe_execution(receipt, "runtime_provenance_receipt", authority=authority)
    return receipt


def verify_captured_apparatus(authority: dict, unit: dict, artifacts: dict,
                              destination: Path) -> dict:
    """Derive camera, scene/layout, target, and frame identity from captured bytes."""
    policy = authority["apparatus_observation_policy"]
    state = artifacts.get("state")
    visibility = artifacts.get("visibility")
    frames = sorted((destination / "raw/frames").glob("*.png"))
    if not isinstance(state, list) or not state or not isinstance(visibility, list) or not frames:
        raise RuntimeError("captured apparatus evidence is incomplete")
    feet = policy["camera_feet_world_xyz"]
    eye = policy["camera_eye_world_xyz"]
    # server_state rows carry the camera EYE, not the feet: EpisodeManager logs
    # `py = player.getEyeY()` beside `player.getX()/getZ()`, because that same
    # triple is the sightline origin handed to GeometryUtil.segmentHitsWall.
    # The feet are never a state column -- they are established by the lockcam
    # teleport to camPoseFeetY -- so feet are derived from the observed eye by
    # removing the authority's own declared eye-height offset. Reading player_y
    # as feet compared the eye against the feet and blocked every unit by a
    # constant +1.6200000047683716 (= the 1.62f standing eye height).
    eye_height = float(eye[1]) - float(feet[1])
    for row in state:
        observed_eye = [float(row["player_x"]), float(row["player_y"]), float(row["player_z"])]
        observed_feet = [observed_eye[0], observed_eye[1] - eye_height, observed_eye[2]]
        # atol is an ENCODING tolerance, not a scientific threshold: the frozen
        # authority serializes eye coordinates to 10 decimal places, so the
        # exact binary64 eye differs from the declared value by ~3.2e-11. This
        # matches CAMERA_ROUNDING_TOLERANCE in prospective/path_state_gate.py.
        if not np.allclose(observed_eye, eye, rtol=0, atol=1e-9):
            raise RuntimeError("captured camera eye mismatch")
        if not np.allclose(observed_feet, feet, rtol=0, atol=1e-9):
            raise RuntimeError("captured camera feet mismatch")
        if [float(row["player_yaw"]), float(row["player_pitch"])] != policy["yaw_pitch_degrees"]:
            raise RuntimeError("captured camera orientation mismatch")
    # FOV is a CLIENT property -- the server declares it "not_server_observable"
    # -- so it is verified from the client authority record captured for THIS
    # episode, not from a state column that never carried it. The episode
    # binding is what makes a stale record from an earlier episode fail.
    authority_record = destination / "raw/client_authority.json"
    if not authority_record.is_file():
        raise RuntimeError("captured client authority record is missing")
    client = load_json(authority_record)
    if int(client["episode_id"]) != int(unit["episode_id"]):
        raise RuntimeError("captured client authority record is stale")
    if float(client["fov_degrees"]) != float(policy["fov_degrees"]):
        raise RuntimeError("captured FOV mismatch")
    # Without the speed/sprint FOV effect pinned off, the pinned FOV above is
    # not the FOV actually rendered into the frames.
    if float(client["fov_effect_scale"]) != 0.0:
        raise RuntimeError("captured FOV effect scale is not pinned")
    if [int(client["framebuffer_width"]), int(client["framebuffer_height"])] != policy["canonical_frame_pixels"]:
        raise RuntimeError("captured framebuffer dimensions mismatch")
    with Image.open(frames[0]) as image:
        if list(image.size) != policy["canonical_frame_pixels"]:
            raise RuntimeError("captured frame dimensions mismatch")
    uuids = {row.get("target_entity_uuid") for row in state}
    if None in uuids or len(uuids) != 1 or any(row.get("target_respawn_count") != 0 for row in state):
        raise RuntimeError("captured target identity/respawn mismatch")
    point = [row.get("geometric_status") == "visible" for row in visibility]
    if unit["scene"] == "WALL" and (not any(point) or all(point)):
        raise RuntimeError("WALL layout evidence lacks visible/hidden regimes")
    if unit["scene"] == "NO_WALL" and not all(point):
        raise RuntimeError("NO_WALL layout evidence contains point occlusion")
    return digest_bound_receipt({"status": "PASS", "independently_derived": True,
        "asserted_by_evidence_builder": False, "camera_feet_world_xyz": feet,
        "camera_eye_world_xyz": eye, "yaw_pitch_degrees": policy["yaw_pitch_degrees"],
        "fov_degrees": policy["fov_degrees"], "canonical_frame_pixels": policy["canonical_frame_pixels"],
        "target_entity_uuid": next(iter(uuids)), "target_respawn_count": 0,
        "scene": unit["scene"], "layout_id": authority["apparatus"]["layout_id"],
        "camera_authority": authority["apparatus"]["camera_authority"],
        "wall_authority": authority["apparatus"]["wall_authority"],
        "wall_layout_physical_evidence": "PASS"})


def transition_regime(x: float, scene: str, transition: dict, point_visible: bool) -> str:
    if scene == "NO_WALL":
        return "stable_visible" if point_visible else "unresolved"
    low, high = transition["stable_occluded_world_x_interval"]
    if low <= x <= high:
        return "stable_occluded"
    if any(a < x < b for a, b in transition["partial_transition_world_x_intervals"]):
        return "partial_transition"
    return "stable_visible" if point_visible else "unresolved"


def stage2_physical_evidence(unit: dict, artifacts: dict, observed: np.ndarray,
                             authority: dict) -> dict:
    decision_path = Path(os.environ.get("MINEOCCLUDE_STAGE1_DECISION_PATH", ""))
    if not decision_path.is_file():
        raise RuntimeError("Stage-2 capture requires the bound Stage-1 decision artifact")
    decision = load_json(decision_path)
    direction = unit["direction"]
    detail = decision["gates"]["render_server_temporal_alignment"]["detail"][direction]
    fir = next(method for method in detail["methods"] if method["method_id"] == "causal_fir_group_delay")
    ticks = unit.get("target_model_frame_indices")
    required_rows = authority["stage2_policy"]["required_target_rows_per_capture"]
    if not isinstance(ticks, list) or len(ticks) != required_rows:
        raise RuntimeError(f"Stage-2 target window is not materialized to exactly {required_rows} rows")
    labels = causal_fir_targets(observed.tolist(), ticks, fir["kernel"])
    expected = unit.get("expected_causal_fir_target_world_x_blocks")
    if not isinstance(expected, list) or labels != expected:
        raise RuntimeError("captured FIR labels differ from the frozen materialized labels")
    visibility_rows = artifacts.get("visibility")
    if not isinstance(visibility_rows, list) or not all(isinstance(row, dict) for row in visibility_rows):
        raise RuntimeError("Stage-2 visibility evidence is malformed")
    visibility_by_tick = {row.get("server_tick"): row for row in visibility_rows}
    if len(visibility_by_tick) != len(visibility_rows):
        raise RuntimeError("Stage-2 visibility tick identities are duplicate")
    transition = decision["gates"]["prospective_transition_measurement"]["detail"][direction]
    lane_low, lane_high = authority["apparatus"]["lane_world_x_blocks"]
    contamination = []
    for tick, x in zip(ticks, labels, strict=True):
        row = visibility_by_tick.get(tick)
        if (row is None or row.get("model_frame_idx") != tick
                or row.get("render_frame_idx") != tick or row.get("scene") != unit["scene"]):
            contamination.append({"tick": tick, "classes": ["malformed_or_missing"]}); continue
        if unit["scene"] == "WALL":
            point_low, point_high = transition["geometric_point_hidden_world_x_interval"]
            point_visible = not (point_low <= x <= point_high)
        else:
            point_visible = row.get("geometric_status") == "visible"
        detected = row.get("magenta_status") == "detected"
        regime = transition_regime(x, unit["scene"], transition, point_visible)
        classes = []
        if unit["scene"] == "WALL":
            if point_visible: classes.append("point_visible")
            if regime == "partial_transition": classes.append("partial_transition")
            if detected: classes.append("detector_visible")
            if regime != "stable_occluded": classes.append("hidden_row_invalid")
        else:
            if not point_visible or regime != "stable_visible": classes.append("visible_control_invalid")
            if not detected: classes.append("detector_absent")
        if not lane_low <= x <= lane_high:
            classes.append("out_of_support")
        if classes: contamination.append({"tick": tick, "classes": classes})
    return {"target_model_frame_indices": ticks, "aligned_target_world_x_blocks": labels,
        "target_row_count": len(ticks), "contamination_rows": contamination,
        "checks": {"clock_alignment": True, "stable_visibility": not contamination,
            "hidden_row_validity": not contamination,
            "physical_support": all(lane_low <= x <= lane_high for x in labels),
            "zero_target_row_contamination": not contamination}}


def capture(stage: str, unit: dict, manifest: dict, manifest_path: Path, receipt_path: Path) -> None:
    from p2_common import CaptureSession
    from p2c_capture import package as package_capture
    from p3_run_sequential import derive_artifacts
    from mineocclude.data.noise_schedule import generate_noise_schedule

    authority_path = ROOT / manifest["authority_binding"]["path"]
    authority = load_json(authority_path)
    if sha256_file(authority_path) != manifest["authority_binding"]["sha256"]:
        raise RuntimeError("manifest authority binding mismatch")
    authorized_head = require_capture_authorization(stage, manifest, manifest_path,
                                                    authority_path, unit)
    runtime_receipt = probe_runtime(authority)
    if runtime_receipt["head"] != authorized_head:
        raise RuntimeError("runtime HEAD changed after authorization check")
    if manifest.get("source_commit_binding") != "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT":
        raise RuntimeError("manifest runtime source-commit policy mismatch")
    if manifest.get("confirmatory_collection_authorized") is not False:
        raise RuntimeError("manifest confirmatory boundary is invalid")
    # One shared construction path, also used by the pre-authorization preflight,
    # so a preflight cannot pass against a spec this run would not actually use.
    spec = derive_effective_capture_spec(unit, authority)
    require_capture_spec_contract(spec)
    seconds_per_tick = authority["apparatus"]["seconds_per_server_tick"]
    lane_low, lane_high = authority["apparatus"]["lane_world_x_blocks"]
    schedule = generate_noise_schedule(int(spec["noise_seed"]), int(spec["expected_frames"]),
                                       float(spec["motion_noise_q"]), seconds_per_tick)
    destination = receipt_path.parent.parent / "captures" / unit["unit_id"]
    if destination.exists():
        quarantine = destination.with_name(destination.name + ".incomplete-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        destination.rename(quarantine)
    destination.mkdir(parents=True)
    scene = unit["scene"]
    with CaptureSession("normal" if scene == "WALL" else "nowall") as session:
        info = session.capture(spec, int(unit["episode_id"]), destination)
        artifacts = derive_artifacts(spec, destination, "NORMAL" if scene == "WALL" else "NO_WALL",
                                     unit.get("target_model_frame_indices"))
        package_capture(spec, destination, int(unit["episode_id"]), session.live)
        observed = np.asarray([float(row["sheep_x"]) for row in artifacts["state"]], dtype="<f8")
        signed_step = float(spec["speed_blocks_per_second"]) * seconds_per_tick * (
            1 if spec["direction"] == "LEFT_TO_RIGHT" else -1)
        analytic_values, position = [], float(spec["start_world_x"])
        for schedule_row in info["schedule"].rows:
            position = min(lane_high, max(lane_low,
                position + signed_step + float(schedule_row.noise_draw)))
            analytic_values.append(position)
        analytic = np.asarray(analytic_values, dtype="<f8")
        if not np.array_equal(observed, analytic):
            raise RuntimeError("captured path differs from frozen recurrence")
    path_receipt = digest_bound_receipt({"status": "PASS", "independently_derived": True,
        "asserted_by_evidence_builder": False, "unit_id": unit["unit_id"],
        "frame_count": len(observed), "exact_binary64_path_match": True,
        "captured_path_sha256": hashlib.sha256(observed.tobytes()).hexdigest(),
        "expected_path_sha256": hashlib.sha256(analytic.tobytes()).hexdigest()})
    apparatus_receipt = verify_captured_apparatus(authority, unit, artifacts, destination)
    runtime_without_hash = {key: value for key, value in runtime_receipt.items() if key != "payload_sha256"}
    runtime_receipt = digest_bound_receipt({**runtime_without_hash,
                                     "captured_apparatus_receipt": apparatus_receipt})
    stage2_evidence = (stage2_physical_evidence(unit, artifacts, observed, authority)
                       if unit.get("scientific_run_id", "").endswith("stage2") else None)
    files = sorted(path for path in destination.rglob("*") if path.is_file())
    checksums = {path.relative_to(destination).as_posix(): sha256_file(path) for path in files}
    checksum_path = destination / "sha256_manifest.json"
    atomic_write_json(checksum_path, {"unit_id": unit["unit_id"],
        "authority_sha256": sha256_file(authority_path),
        "manifest_sha256": sha256_file(manifest_path), "source_commit_sha": authorized_head,
        "scientific_run_id": manifest["run_namespace"], "files": checksums})
    durable_prefix = manifest["durable_prefix"].rstrip("/") + "/" + unit["unit_id"]
    subprocess.run(["aws", "s3", "sync", str(destination), durable_prefix, "--only-show-errors"], check=True)
    readback = subprocess.run(["aws", "s3", "cp", durable_prefix + "/sha256_manifest.json", "-",
                               "--only-show-errors"], check=True, capture_output=True).stdout
    if readback != checksum_path.read_bytes():
        raise RuntimeError("durable checksum-manifest readback mismatch")
    bucket, prefix = durable_prefix.split("/", 3)[2:4]
    listing = subprocess.run(["aws", "s3api", "list-objects-v2", "--bucket", bucket,
                              "--prefix", prefix + "/", "--output", "json"],
                             check=True, capture_output=True)
    remote_keys = {item["Key"] for item in json.loads(listing.stdout).get("Contents", [])}
    expected_keys = {prefix + "/" + relative for relative in checksums} | {prefix + "/sha256_manifest.json"}
    if remote_keys != expected_keys:
        raise RuntimeError("durable object count/structure mismatch")
    for relative, expected_sha in checksums.items():
        remote = subprocess.run(["aws", "s3", "cp", durable_prefix + "/" + relative, "-",
                                 "--only-show-errors"], check=True, capture_output=True).stdout
        if hashlib.sha256(remote).hexdigest() != expected_sha:
            raise RuntimeError(f"durable object checksum mismatch: {relative}")
    durability_receipt = digest_bound_receipt({"status": "PASS", "independently_derived": True,
        "asserted_by_evidence_builder": False, "unit_id": unit["unit_id"],
        "durable_uri": durable_prefix, "remote_object_count": len(checksums),
        "remote_checksum_manifest_sha256": sha256_file(checksum_path)})
    # Labelled after the manifest this invocation was handed, not after the
    # directory this file lives in. The v0.3 Stage-1 manifest names this driver
    # in its own locked unit command, so the same bytes emit v0.2 and v0.3 unit
    # receipts and neither can carry the other's identity.
    receipt = {"schema_version": "1.1",
        "artifact_id": "regime-a-prime-development-unit-receipt-"
                       + artifact_version_tag(manifest["artifact_id"]),
        "unit_id": unit["unit_id"], "status": "COMPLETE_VALIDATED_DURABLE",
        "classification": "DEVELOPMENT_ONLY", "confirmatory_membership": False,
        "authority_sha256": sha256_file(authority_path), "manifest_sha256": sha256_file(manifest_path),
        "source_commit_sha": runtime_receipt["head"], "scientific_run_id": manifest["run_namespace"],
        "durable_uri": durable_prefix, "durable_objects": checksums,
        "remote_checksum_manifest_sha256": sha256_file(checksum_path),
        "runtime_provenance_receipt": runtime_receipt, "path_state_receipt": path_receipt,
        "durability_receipt": durability_receipt,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    if stage2_evidence is not None:
        decision_path = Path(os.environ["MINEOCCLUDE_STAGE1_DECISION_PATH"])
        receipt["stage2_physical_evidence"] = stage2_evidence
        receipt["stage1_decision_sha256"] = sha256_file(decision_path)
        receipt["server_state_path"] = str(destination / "raw/server_state.jsonl")
        receipt["server_state_sha256"] = sha256_file(destination / "raw/server_state.jsonl")
    atomic_write_json(receipt_path, receipt)


def delegated(unit: dict, manifest: dict, manifest_path: Path, stage: str, receipt_path: Path) -> None:
    authority_path = ROOT / manifest["authority_binding"]["path"]
    require_capture_authorization(stage, manifest, manifest_path, authority_path, unit)
    commands = manifest.get("locked_stage_commands")
    if not isinstance(commands, dict) or stage not in commands:
        raise RuntimeError(f"locked implementation command is absent for {stage}")
    command = commands[stage]
    if not isinstance(command, list) or not command or not all(isinstance(value, str) and value for value in command):
        raise RuntimeError(f"malformed locked implementation command for {stage}")
    environment = {**os.environ, "MINEOCCLUDE_UNIT_ID": unit["unit_id"],
                   "MINEOCCLUDE_RECEIPT_PATH": str(receipt_path)}
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    receipt = load_json(receipt_path)
    if receipt.get("unit_id") != unit["unit_id"] or receipt.get("status") != "COMPLETE_VALIDATED_DURABLE":
        raise RuntimeError("delegated stage receipt is invalid")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True); parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--unit-id", required=True); parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    manifest = load_json(args.manifest); unit = unit_from(manifest, args.unit_id)
    # A6: refuse a cross-stage request at the outermost entrypoint as well, so a
    # future dispatch branch cannot silently inherit an unbound stage string.
    require_stage_manifest_binding(args.stage, manifest, manifest_path=args.manifest,
        authority=load_json(ROOT / manifest["authority_binding"]["path"]), unit=unit)
    if args.stage in {"stage1-capture", "stage2-capture"}:
        capture(args.stage, unit, manifest, args.manifest, args.receipt)
    else:
        delegated(unit, manifest, args.manifest, args.stage, args.receipt)


if __name__ == "__main__":
    main()
