#!/usr/bin/env python3
"""Stage-2 physical gates, causal labels, extraction, and readouts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "scripts/regime_a_prime_qualification_v0_1"
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(LEGACY)]

from mineocclude.prospective.development_workflow import (  # noqa: E402
    atomic_write_json, causal_fir_targets, load_json, require_stage2_authorization, sha256_file,
    RUNTIME_CRITICAL_SOURCE_PATHS, verify_remote_durable_objects,
    verify_probe_execution, verify_receipt_payload_digest, verify_runtime_identity,
    verify_runtime_source_hashes,
)
from mineocclude.regime_a_first25_analysis import scalar_metrics  # noqa: E402
from p2d_extract import Layer4Extractor  # noqa: E402
from p2e_analyze import best_k_readout, full_readout  # noqa: E402


PHYSICAL_CHECKS = {"clock_alignment", "stable_visibility", "hidden_row_validity",
                   "physical_support", "zero_target_row_contamination"}


def require_durable_unit_receipt(manifest: dict, manifest_path: Path, unit: dict,
                                 receipt: dict, *, current_source_commit: str,
                                 durable_verifier=verify_remote_durable_objects) -> None:
    """Revalidate a predecessor unit from bound local and remote raw evidence."""
    prefix = manifest.get("durable_prefix")
    if not isinstance(prefix, str) or not prefix.startswith("s3://"):
        raise RuntimeError("Stage-2 durable prefix is missing")
    capture_ids = {item.get("unit_id") for item in manifest.get("capture_units", [])
                   if isinstance(item, dict)}
    durable_role = "" if unit.get("unit_id") in capture_ids else "/derived"
    expected_uri = f"{prefix.rstrip('/')}{durable_role}/{unit.get('unit_id')}"
    expected = {"unit_id": unit.get("unit_id"), "status": "COMPLETE_VALIDATED_DURABLE",
        "authority_sha256": manifest.get("authority_binding", {}).get("sha256"),
        "manifest_sha256": sha256_file(manifest_path),
        "source_commit_sha": current_source_commit,
        "scientific_run_id": manifest.get("run_namespace"),
        # The generic remote verifier can bind object bytes and the terminal
        # unit identity, but only the manifest-aware caller knows which bucket,
        # prefix, and capture-vs-derived namespace are authorized.
        "durable_uri": expected_uri}
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f"predecessor receipt binding mismatch: {unit.get('unit_id')}")
    if not durable_verifier(unit, receipt):
        raise RuntimeError(f"predecessor remote durability failed: {unit.get('unit_id')}")


def bound_capture_artifact(unit: dict, receipt: dict, relative: str) -> Path:
    """Resolve a capture artifact only when local bytes match the durable inventory."""
    expected = (Path(unit["receipt_path"]).parent.parent / "captures" / unit["unit_id"] / relative)
    declared = receipt.get("durable_objects")
    if not isinstance(declared, dict) or relative not in declared or not expected.is_file():
        raise RuntimeError(f"bound capture artifact is missing: {unit['unit_id']}/{relative}")
    if sha256_file(expected) != declared[relative]:
        raise RuntimeError(f"bound capture artifact hash mismatch: {unit['unit_id']}/{relative}")
    return expected


def verify_local_capture_inventory(unit: dict, receipt: dict) -> Path:
    """Bind every local capture byte consumed by extraction to durable evidence."""
    root = Path(unit["receipt_path"]).parent.parent / "captures" / unit["unit_id"]
    declared = receipt.get("durable_objects")
    if not isinstance(declared, dict) or not declared:
        raise RuntimeError(f"capture durable inventory is missing: {unit['unit_id']}")
    for relative, expected_sha in declared.items():
        candidate = PurePosixPath(relative) if isinstance(relative, str) else PurePosixPath("..")
        if candidate.is_absolute() or ".." in candidate.parts or str(candidate) != relative:
            raise RuntimeError(f"capture durable inventory path is unsafe: {relative!r}")
        path = root / relative
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise RuntimeError(f"capture durable inventory escapes unit root: {relative!r}") from exc
        if (not path.is_file() or not isinstance(expected_sha, str)
                or sha256_file(path) != expected_sha):
            raise RuntimeError(
                f"local capture bytes diverge from durable inventory: {unit['unit_id']}/{relative}")
    return root


def verify_bound_stage2_physical_evidence(unit: dict, receipt: dict, authority: dict) -> None:
    """Reconstruct physical checks from durable state and visibility rows."""
    from scripts.regime_a_prime_qualification_v0_2.stage_unit_driver import stage2_physical_evidence

    state_path = bound_capture_artifact(unit, receipt, "raw/server_state.jsonl")
    visibility_path = bound_capture_artifact(unit, receipt, "raw/visibility.jsonl")
    if receipt.get("server_state_path") != str(state_path):
        raise RuntimeError("server-state path is not bound to the capture unit")
    if receipt.get("server_state_sha256") != sha256_file(state_path):
        raise RuntimeError("server-state receipt hash diverges from durable inventory")
    state = [json.loads(line) for line in state_path.read_text().splitlines() if line]
    visibility = [json.loads(line) for line in visibility_path.read_text().splitlines() if line]
    observed = np.asarray([float(row["sheep_x"]) for row in state], dtype="<f8")
    reconstructed = stage2_physical_evidence(unit, {"visibility": visibility}, observed, authority)
    if reconstructed != receipt.get("stage2_physical_evidence"):
        raise RuntimeError("Stage-2 physical summary disagrees with bound raw evidence")


def receipt_path() -> Path:
    value = os.environ.get("MINEOCCLUDE_RECEIPT_PATH")
    if not value:
        raise RuntimeError("MINEOCCLUDE_RECEIPT_PATH is required")
    return Path(value)


def require_backend_authorization(manifest: dict, manifest_path: Path) -> None:
    """Repeat the Stage-2 barrier even when this backend is invoked directly."""
    authority_path = ROOT / manifest["authority_binding"]["path"]
    authorization_path = Path(os.environ.get("MINEOCCLUDE_STAGE2_AUTHORIZATION_PATH", ""))
    evidence_path = Path(os.environ.get("MINEOCCLUDE_STAGE1_EVIDENCE_PATH", ""))
    decision_path = Path(os.environ.get("MINEOCCLUDE_STAGE1_DECISION_PATH", ""))
    stage1_manifest_path = Path(os.environ.get("MINEOCCLUDE_STAGE1_MANIFEST_PATH", ""))
    provenance_path = Path(os.environ.get("MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH", ""))
    if not all(path.is_file() for path in (authorization_path, evidence_path, decision_path,
                                           stage1_manifest_path, provenance_path)):
        raise PermissionError("direct Stage-2 backend invocation lacks authorization artifacts")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()
    require_stage2_authorization(manifest, load_json(authorization_path),
        authorization_receipt_path=authorization_path,
        stage1_decision=load_json(decision_path), authority_path=authority_path,
        manifest_path=manifest_path, stage1_manifest_path=stage1_manifest_path,
        stage1_evidence_path=evidence_path, stage1_decision_path=decision_path,
        current_source_commit=head,
        preoutcome_provenance_path=provenance_path)


def complete(manifest: dict, manifest_path: Path, unit_id: str, payload: dict, *,
             additional_files: dict[str, Path] | None = None) -> None:
    """Persist every derived unit and make its remote evidence controller-verifiable."""
    output = receipt_path()
    bundle = output.parent / "durable" / unit_id
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True, exist_ok=True)
    payload_path = bundle / "payload.json"
    atomic_write_json(payload_path, payload)
    objects = {"payload.json": sha256_file(payload_path)}
    for relative, source in (additional_files or {}).items():
        destination = bundle / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        objects[relative] = sha256_file(destination)
    source_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                   capture_output=True, check=True).stdout.strip()
    checksum_path = bundle / "sha256_manifest.json"
    atomic_write_json(checksum_path, {"unit_id": unit_id,
        "authority_sha256": manifest["authority_binding"]["sha256"],
        "manifest_sha256": sha256_file(manifest_path), "source_commit_sha": source_commit,
        "scientific_run_id": manifest["run_namespace"], "files": objects})
    uri = manifest["durable_prefix"].rstrip("/") + f"/derived/{unit_id}"
    subprocess.run(["aws", "s3", "sync", str(bundle), uri, "--only-show-errors"], check=True)
    readback = subprocess.run(["aws", "s3", "cp", uri + "/sha256_manifest.json", "-", "--only-show-errors"],
                              capture_output=True, check=True).stdout
    if readback != checksum_path.read_bytes():
        raise RuntimeError("derived durable readback mismatch")
    atomic_write_json(output, {"schema_version": "1.1",
        "artifact_id": "regime-a-prime-stage2-unit-receipt-v0.2", "unit_id": unit_id,
        "status": "COMPLETE_VALIDATED_DURABLE", "classification": "DEVELOPMENT_ONLY",
        "confirmatory_membership": False, "authority_sha256": manifest["authority_binding"]["sha256"],
        "manifest_sha256": sha256_file(manifest_path), "source_commit_sha": source_commit,
        "scientific_run_id": manifest["run_namespace"], "durable_uri": uri,
        "durable_objects": objects, "remote_checksum_manifest_sha256": sha256_file(checksum_path), **payload})


def validate_physical_gate_receipts(manifest: dict, receipts: dict[str, dict], *,
                                    manifest_sha256: str, current_source_commit: str) -> dict:
    """Validate all physical, coverage, pair, and provenance conditions before extraction."""
    authority_path = ROOT / manifest["authority_binding"]["path"]
    authority = load_json(authority_path)
    if sha256_file(authority_path) != manifest["authority_binding"]["sha256"]:
        raise RuntimeError("Stage-2 authority binding mismatch")
    expected = {unit["unit_id"]: unit for unit in manifest["capture_units"]}
    failures: dict[str, list[str]] = {}
    if manifest.get("status") != "POST_STAGE1_MATERIALIZED_AWAITING_SEPARATE_FREEZE_AND_AUTHORIZATION":
        failures["manifest"] = ["target windows are not materialized"]
    if set(receipts) != set(expected):
        failures["coverage"] = ["capture unit identity set mismatch"]
    by_trajectory: dict[str, dict[str, tuple[dict, dict]]] = {}
    for unit_id, unit in expected.items():
        receipt = receipts.get(unit_id, {})
        reasons: list[str] = []
        if receipt.get("status") != "COMPLETE_VALIDATED_DURABLE": reasons.append("durability")
        if receipt.get("unit_id") != unit_id: reasons.append("identity")
        if receipt.get("authority_sha256") != manifest["authority_binding"]["sha256"]: reasons.append("authority_provenance")
        if receipt.get("manifest_sha256") != manifest_sha256: reasons.append("manifest_provenance")
        if receipt.get("source_commit_sha") != current_source_commit: reasons.append("source_provenance")
        if receipt.get("stage1_decision_sha256") != manifest.get("stage1_decision_sha256"): reasons.append("stage1_decision_provenance")
        if receipt.get("scientific_run_id") != manifest["run_namespace"]: reasons.append("run_namespace")
        for name in ("runtime_provenance_receipt", "path_state_receipt", "durability_receipt"):
            item = receipt.get(name, {})
            try:
                verify_receipt_payload_digest(item, name)
                if (item.get("independently_derived") is not True
                        or item.get("asserted_by_evidence_builder") is not False):
                    raise ValueError(f"{name} does not declare independent derivation")
                if name == "runtime_provenance_receipt":
                    # Concrete probe-execution evidence, not a self-asserted PASS.
                    verify_probe_execution(item, name, authority=authority)
            except (ValueError, TypeError):
                reasons.append(name)
        runtime = receipt.get("runtime_provenance_receipt", {})
        try:
            verify_runtime_identity(authority["runtime_identity_policy"], runtime)
        except (ValueError, TypeError):
            reasons.append("runtime_identity")
        source_hashes = runtime.get("runtime_source_sha256")
        try:
            verify_runtime_source_hashes(source_hashes)
        except (ValueError, TypeError):
            reasons.append("runtime_source_coverage")
        apparatus = runtime.get("captured_apparatus_receipt", {})
        try:
            verify_receipt_payload_digest(apparatus, "captured apparatus receipt")
        except (ValueError, TypeError):
            reasons.append("apparatus_provenance")
        apparatus_policy = authority["apparatus_observation_policy"]
        if (apparatus.get("scene") != unit["scene"]
                or apparatus.get("camera_feet_world_xyz") != apparatus_policy["camera_feet_world_xyz"]
                or apparatus.get("camera_eye_world_xyz") != apparatus_policy["camera_eye_world_xyz"]
                or apparatus.get("yaw_pitch_degrees") != apparatus_policy["yaw_pitch_degrees"]
                or apparatus.get("fov_degrees") != apparatus_policy["fov_degrees"]
                or apparatus.get("canonical_frame_pixels") != apparatus_policy["canonical_frame_pixels"]
                or apparatus.get("layout_id") != authority["apparatus"]["layout_id"]
                or apparatus.get("camera_authority") != authority["apparatus"]["camera_authority"]
                or apparatus.get("wall_authority") != authority["apparatus"]["wall_authority"]
                or apparatus.get("target_respawn_count") != 0
                or not isinstance(apparatus.get("target_entity_uuid"), str)):
            reasons.append("apparatus_identity")
        path_probe = receipt.get("path_state_receipt", {})
        if (path_probe.get("unit_id") != unit_id or path_probe.get("exact_binary64_path_match") is not True
                or path_probe.get("captured_path_sha256") != unit.get("expected_path_sha256")
                or path_probe.get("expected_path_sha256") != unit.get("expected_path_sha256")):
            reasons.append("path_state_identity")
        durability = receipt.get("durability_receipt", {})
        expected_uri = manifest["durable_prefix"].rstrip("/") + "/" + unit_id
        if (durability.get("unit_id") != unit_id or durability.get("durable_uri") != expected_uri
                or not isinstance(durability.get("remote_object_count"), int)
                or isinstance(durability.get("remote_object_count"), bool)
                or durability.get("remote_object_count", 0) < 1):
            reasons.append("durability_identity")
        physical = receipt.get("stage2_physical_evidence", {})
        checks = physical.get("checks", {})
        if set(checks) != PHYSICAL_CHECKS or not all(value is True for value in checks.values()): reasons.append("physical_checks")
        if physical.get("target_row_count") != manifest["required_target_rows_per_capture"]: reasons.append("target_row_count")
        if physical.get("contamination_rows") != []: reasons.append("contamination")
        if physical.get("target_model_frame_indices") != unit.get("target_model_frame_indices"):
            reasons.append("target_window_binding")
        if physical.get("aligned_target_world_x_blocks") != unit.get("expected_causal_fir_target_world_x_blocks"):
            reasons.append("target_label_binding")
        if reasons: failures[unit_id] = reasons
        by_trajectory.setdefault(unit["trajectory_id"], {})[unit["scene"]] = (unit, receipt)
    for trajectory, scenes in by_trajectory.items():
        if set(scenes) != {"WALL", "NO_WALL"}:
            failures.setdefault(trajectory, []).append("pair_coverage"); continue
        wall_unit, wall = scenes["WALL"]; no_unit, no_wall = scenes["NO_WALL"]
        if wall_unit.get("expected_path_sha256") != no_unit.get("expected_path_sha256"):
            failures.setdefault(trajectory, []).append("manifest_pair_path")
        if wall.get("path_state_receipt", {}).get("captured_path_sha256") != no_wall.get("path_state_receipt", {}).get("captured_path_sha256"):
            failures.setdefault(trajectory, []).append("captured_pair_path")
        if wall.get("stage2_physical_evidence", {}).get("target_model_frame_indices") != no_wall.get("stage2_physical_evidence", {}).get("target_model_frame_indices"):
            failures.setdefault(trajectory, []).append("pair_target_window")
    if failures:
        raise RuntimeError(f"Stage-2 physical gates failed closed: {failures}")
    return {"status": "PASS", "capture_units": len(expected), "paired_trajectories": len(by_trajectory),
            "required_checks": sorted(PHYSICAL_CHECKS | {"path_state", "durability", "runtime_provenance", "pair_coverage"})}


def capture_receipt(manifest: dict, unit_id: str) -> dict:
    unit = next(unit for unit in manifest["capture_units"] if unit["unit_id"] == unit_id)
    return load_json(Path(unit["receipt_path"]))


def gates(manifest: dict, manifest_path: Path, unit_id: str) -> None:
    receipts = {unit["unit_id"]: capture_receipt(manifest, unit["unit_id"])
                for unit in manifest["capture_units"]}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()
    for unit in manifest["capture_units"]:
        require_durable_unit_receipt(manifest, manifest_path, unit, receipts[unit["unit_id"]],
                                     current_source_commit=head)
        verify_bound_stage2_physical_evidence(unit, receipts[unit["unit_id"]],
                                              load_json(ROOT / manifest["authority_binding"]["path"]))
    complete(manifest, manifest_path, unit_id, {"physical_gates": validate_physical_gate_receipts(
        manifest, receipts, manifest_sha256=sha256_file(manifest_path), current_source_commit=head)})


def extraction(manifest: dict, manifest_path: Path, unit_id: str) -> None:
    gate = load_json(Path(manifest["physical_gate_unit"]["receipt_path"]))
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()
    require_durable_unit_receipt(manifest, manifest_path, manifest["physical_gate_unit"], gate,
                                 current_source_commit=head)
    if gate.get("physical_gates", {}).get("status") != "PASS":
        raise RuntimeError("physical-gate PASS is required before extraction")
    receipts = {unit["unit_id"]: capture_receipt(manifest, unit["unit_id"])
                for unit in manifest["capture_units"]}
    validate_physical_gate_receipts(manifest, receipts, manifest_sha256=sha256_file(manifest_path),
                                    current_source_commit=head)
    unit = next(unit for unit in manifest["extraction_units"] if unit["unit_id"] == unit_id)
    source = next(item for item in manifest["capture_units"] if item["unit_id"] == unit["source_capture_unit_id"])
    source_receipt = capture_receipt(manifest, source["unit_id"])
    # Revalidate the exact source immediately before scientific extraction.
    # A durable physical-gate PASS from an earlier step cannot rescue a frame or
    # package changed locally after that gate was written.
    require_durable_unit_receipt(manifest, manifest_path, source, source_receipt,
                                 current_source_commit=head)
    capture_root = verify_local_capture_inventory(source, source_receipt)
    authority = load_json(ROOT / manifest["authority_binding"]["path"])
    target_rows = authority["stage2_policy"]["required_target_rows_per_capture"]
    token_rows, token_cols = authority["apparatus"]["visual_token_grid"]
    expected_shape = [target_rows, token_rows * token_cols, 2048]
    output_root = receipt_path().parent.parent.parent / "activations"
    record = Layer4Extractor().extract(source["unit_id"], capture_root, output_root)
    if record.get("layer") != 4 or record.get("shape") != expected_shape:
        raise RuntimeError("layer-4 extraction identity mismatch")
    activation = Path(record["activation_path"])
    relative_activation = f"activation/{activation.name}"
    uri = manifest["durable_prefix"].rstrip("/") + f"/derived/{unit_id}/{relative_activation}"
    complete(manifest, manifest_path, unit_id, {"source_capture_unit_id": source["unit_id"], "layer": 4,
        "shape": expected_shape, "activation_path": str(activation),
        "activation_sha256": sha256_file(activation), "durable_activation_uri": uri},
        additional_files={relative_activation: activation})


def decision_fir(direction: str) -> list[float]:
    path = Path(os.environ.get("MINEOCCLUDE_STAGE1_DECISION_PATH", ""))
    if not path.is_file():
        raise RuntimeError("bound Stage-1 decision is required for labels")
    decision = load_json(path)
    methods = decision["gates"]["render_server_temporal_alignment"]["detail"][direction]["methods"]
    return next(method["kernel"] for method in methods if method["method_id"] == "causal_fir_group_delay")


def labels_from_capture(unit: dict, receipt: dict) -> tuple[list[int], list[float]]:
    state_path = bound_capture_artifact(unit, receipt, "raw/server_state.jsonl")
    if receipt.get("server_state_path") != str(state_path):
        raise RuntimeError("server-state path is not bound to capture identity")
    if sha256_file(state_path) != receipt.get("server_state_sha256"):
        raise RuntimeError("server-state provenance mismatch")
    state = [json.loads(line) for line in state_path.read_text().splitlines() if line]
    positions = [float(row["sheep_x"]) for row in state]
    ticks = unit.get("target_model_frame_indices")
    labels = causal_fir_targets(positions, ticks, decision_fir(unit["direction"]))
    if labels != receipt.get("stage2_physical_evidence", {}).get("aligned_target_world_x_blocks"):
        raise RuntimeError("independently reconstructed FIR labels disagree with capture receipt")
    if labels != unit.get("expected_causal_fir_target_world_x_blocks"):
        raise RuntimeError("FIR labels disagree with frozen materialized manifest")
    return ticks, labels


def load_scene(manifest: dict, scene: str):
    authority = load_json(ROOT / manifest["authority_binding"]["path"])
    target_rows = authority["stage2_policy"]["required_target_rows_per_capture"]
    token_rows, token_cols = authority["apparatus"]["visual_token_grid"]
    expected_shape = (target_rows, token_rows * token_cols, 2048)
    arrays, rows, identities, outer, directions = [], [], [], {}, {}
    for identity in manifest["trajectory_identities"]:
        capture_id = f"{identity['trajectory_id']}_{scene.lower()}"
        capture_unit = next(item for item in manifest["capture_units"] if item["unit_id"] == capture_id)
        capture = load_json(Path(capture_unit["receipt_path"]))
        ticks, labels = labels_from_capture(capture_unit, capture)
        extract_id = f"extract_{capture_id}"
        unit = next(item for item in manifest["extraction_units"] if item["unit_id"] == extract_id)
        receipt = load_json(Path(unit["receipt_path"])); activation = Path(receipt["activation_path"])
        if sha256_file(activation) != receipt["activation_sha256"]:
            raise RuntimeError(f"activation checksum mismatch: {capture_id}")
        relative_activation = f"activation/{activation.name}"
        if receipt.get("durable_objects", {}).get(relative_activation) != receipt["activation_sha256"]:
            raise RuntimeError(f"activation durable inventory mismatch: {capture_id}")
        array = np.load(activation, mmap_mode="r")
        if array.shape != expected_shape or array.dtype != np.float16:
            raise RuntimeError(f"activation shape/dtype mismatch: {capture_id}")
        arrays.append(array); trajectory = identity["trajectory_id"]; identities.append(trajectory)
        outer[trajectory] = identity["outer_fold"]; directions[trajectory] = identity["direction"]
        for offset, (tick, x) in enumerate(zip(ticks, labels, strict=True)):
            rows.append({"trajectory_id": trajectory, "run_id": capture_id, "scene": scene,
                "activation_row": offset, "model_frame_idx": tick, "server_tick_is_not_label": tick,
                "label_mapping": "qualified_causal_fir", "tau": offset + 1,
                "outer_fold": identity["outer_fold"], "direction": identity["direction"], "world_x": x})
    return np.concatenate(arrays), np.asarray([row["world_x"] for row in rows]), rows, identities, outer, directions


def summary(rows: list[dict], key: str, policy: dict) -> dict:
    metrics = scalar_metrics(rows, key)
    values = np.asarray([metrics["per_trajectory"][name]["r2"] for name in sorted(metrics["per_trajectory"])])
    rng = np.random.default_rng(policy["bootstrap_seed"])
    draws = rng.choice(values, size=(policy["bootstrap_resamples"], len(values)), replace=True).mean(axis=1)
    return {"rmse_blocks": metrics["trajectory_aggregated_rmse"],
        "mae_blocks": metrics["trajectory_aggregated_mae"], "macro_r2": metrics["macro_r2"],
        "bootstrap95_macro_r2": [float(np.quantile(draws, .025)), float(np.quantile(draws, .975))]}


def training_time_baseline(rows: list[dict], target: np.ndarray, training_tau_maximum: int) -> np.ndarray:
    """Frozen outer-training baseline [1, direction, tau, tau*direction]."""
    predictions = np.empty(len(rows), dtype=float)
    folds = sorted({row["outer_fold"] for row in rows})
    for fold in folds:
        train = [i for i, row in enumerate(rows)
                 if row["outer_fold"] != fold and row["tau"] <= training_tau_maximum]
        test = [i for i, row in enumerate(rows) if row["outer_fold"] == fold]
        def features(indices):
            return np.asarray([[1.0, 1.0 if rows[i]["direction"] == "LEFT_TO_RIGHT" else -1.0,
                                rows[i]["tau"], rows[i]["tau"] * (1.0 if rows[i]["direction"] == "LEFT_TO_RIGHT" else -1.0)]
                               for i in indices])
        coefficients, *_ = np.linalg.lstsq(features(train), target[train], rcond=None)
        predictions[test] = features(test) @ coefficients
    return predictions


def best_k_qualification_checks(scene_outputs: dict, policy: dict) -> dict[str, bool]:
    """Apply every controlling BEST-K gate, including the WALL time baseline."""
    checks: dict[str, bool] = {}
    for scene in ("WALL", "NO_WALL"):
        metrics = scene_outputs[scene]["metrics"]
        checks[f"{scene}_rmse"] = metrics["rmse_blocks"] <= policy["best_k_each_scene_rmse_maximum_blocks"]
        checks[f"{scene}_r2"] = metrics["macro_r2"] > 0 and metrics["bootstrap95_macro_r2"][0] > 0
    wall = scene_outputs["WALL"]
    checks["WALL_beats_training_time_baseline"] = (
        wall["metrics"]["rmse_blocks"] < wall["training_time_baseline"]["rmse_blocks"])
    checks["WALL_time_confound_gate"] = (
        wall["training_time_baseline_tau1_15"]["macro_r2"]
        <= policy["training_only_time_baseline_macro_r2_tau_1_to_15_maximum"])
    return checks


def readout(manifest: dict, manifest_path: Path, unit_id: str, kind: str) -> None:
    policy = load_json(ROOT / manifest["authority_binding"]["path"])["stage2_policy"]["readout"]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()
    gate = load_json(Path(manifest["physical_gate_unit"]["receipt_path"]))
    require_durable_unit_receipt(manifest, manifest_path, manifest["physical_gate_unit"], gate,
                                 current_source_commit=head)
    if gate.get("physical_gates", {}).get("status") != "PASS":
        raise RuntimeError("physical-gate PASS is required before readout")
    for extraction_unit in manifest["extraction_units"]:
        extraction_receipt = load_json(Path(extraction_unit["receipt_path"]))
        require_durable_unit_receipt(manifest, manifest_path, extraction_unit,
                                     extraction_receipt, current_source_commit=head)
    if kind == "FULL":
        best_unit = next(item for item in manifest["readout_and_terminal_units"]
                         if item["pipeline_stage"] == "best_k")
        require_durable_unit_receipt(manifest, manifest_path, best_unit,
                                     load_json(Path(best_unit["receipt_path"])),
                                     current_source_commit=head)
    output = {"readout": kind, "scenes": {}}
    for scene in ("WALL", "NO_WALL"):
        features, target, rows, identities, outer, directions = load_scene(manifest, scene)
        if kind == "BEST_K":
            predictions, selection, _ = best_k_readout(features, target, rows, identities, outer, directions)
            key = "predicted_best_k"
        else:
            predictions, selection, _ = full_readout(features, target, rows, identities, outer, directions)
            key = "predicted_full"
        for index, row in enumerate(rows): row[key] = float(predictions[index])
        metrics = summary(rows, key, policy)
        tau_maximum = policy["training_only_time_baseline_training_tau_maximum"]
        baseline = training_time_baseline(rows, target, tau_maximum)
        for index, row in enumerate(rows): row["predicted_training_time_baseline"] = float(baseline[index])
        baseline_metrics = summary(rows, "predicted_training_time_baseline", policy)
        tau_rows = [row for row in rows if row["tau"] <= tau_maximum]
        baseline_tau1_15 = summary(tau_rows, "predicted_training_time_baseline", policy)
        output["scenes"][scene] = {"metrics": metrics, "training_time_baseline": baseline_metrics,
                                    "training_time_baseline_tau1_15": baseline_tau1_15,
                                    "selection_by_outer_fold": selection}
    if kind == "BEST_K":
        checks = best_k_qualification_checks(output["scenes"], policy)
        output["qualification_checks"] = checks
        output["qualification_status"] = "PASS" if all(checks.values()) else "FAIL"
    complete(manifest, manifest_path, unit_id, output)


def terminal(manifest: dict, manifest_path: Path, unit_id: str) -> None:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()
    best_unit = next(unit for unit in manifest["readout_and_terminal_units"]
                     if unit["pipeline_stage"] == "best_k")
    full_unit = next(unit for unit in manifest["readout_and_terminal_units"]
                     if unit["pipeline_stage"] == "full")
    best = load_json(Path(best_unit["receipt_path"])); full = load_json(Path(full_unit["receipt_path"]))
    require_durable_unit_receipt(manifest, manifest_path, best_unit, best,
                                 current_source_commit=head)
    require_durable_unit_receipt(manifest, manifest_path, full_unit, full,
                                 current_source_commit=head)
    if best.get("qualification_status") not in {"PASS", "FAIL"} or full.get("readout") != "FULL":
        raise RuntimeError("readout receipts incomplete")
    complete(manifest, manifest_path, unit_id, {"development_qualification": best["qualification_status"],
        "BEST_K_controls": True, "FULL_may_rescue": False,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO", "confirmatory_collection_authorized": False})


def main() -> None:
    if len(sys.argv) != 3: raise SystemExit("usage: stage2_backend.py STAGE MANIFEST")
    stage, manifest_path = sys.argv[1], Path(sys.argv[2]); manifest = load_json(manifest_path)
    require_backend_authorization(manifest, manifest_path)
    unit_id = os.environ.get("MINEOCCLUDE_UNIT_ID", "")
    if stage == "gates": gates(manifest, manifest_path, unit_id)
    elif stage == "extract": extraction(manifest, manifest_path, unit_id)
    elif stage == "best-k": readout(manifest, manifest_path, unit_id, "BEST_K")
    elif stage == "full": readout(manifest, manifest_path, unit_id, "FULL")
    elif stage == "terminal": terminal(manifest, manifest_path, unit_id)
    else: raise RuntimeError(f"unknown stage {stage}")


if __name__ == "__main__": main()
