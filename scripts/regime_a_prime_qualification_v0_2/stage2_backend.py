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
    atomic_write_json, campaign_source_commit, causal_fir_targets, durable_unit_uri, load_json,
    require_stage2_authorization, sha256_file,
    RUNTIME_CRITICAL_SOURCE_PATHS, verify_remote_durable_objects,
    verify_probe_execution, verify_receipt_payload_digest, verify_runtime_identity,
    verify_runtime_source_hashes,
)
from mineocclude.prospective.activation_binding import (  # noqa: E402
    require_activation_identity, require_target_rows_authority_bound,
    verify_activation_checkpoint_binding,
)
from mineocclude.prospective.capture_admission import (  # noqa: E402
    CaptureAdmissionError, build_capture_admission_context,
    load_capture_provenance_authority, require_homogeneous_capture_closure,
    resolve_typed_capture_identity,
)
from mineocclude.prospective.stage2_decision import (  # noqa: E402
    evaluate_stage2, require_stage2_decision_reproduction,
)
from mineocclude.prospective.stage2_evidence import build_stage2_evidence  # noqa: E402
from mineocclude.prospective.stage2_processability import causal_fir_kernel  # noqa: E402
from mineocclude.regime_a_first25_analysis import scalar_metrics  # noqa: E402
from p2d_extract import Layer4Extractor  # noqa: E402
from p2e_analyze import best_k_readout, full_readout  # noqa: E402


PHYSICAL_CHECKS = {"clock_alignment", "stable_visibility", "hidden_row_validity",
                   "physical_support", "zero_target_row_contamination"}

#: The layer-4 activation contract, previously two bare literals -- ``2048`` in
#: ``extraction`` and ``np.float16`` in ``load_scene``. Named here so the frozen
#: Stage-2 decision authority can promote them by reading this module, and so the
#: terminal can verify a recorded activation shape/dtype against a frozen rule
#: rather than against nothing (B008). The row and token dimensions are not here:
#: they come from the authority's own ``required_target_rows_per_capture`` and
#: ``visual_token_grid``, and are read from it at every use.
LAYER4_HIDDEN_SIZE = 2048
LAYER4_ACTIVATION_DTYPE = "float16"


def backend_capture_admission(manifest: dict, manifest_path: Path, *,
                              current_source_commit: str):
    """The campaign's capture-admission context, built once per backend stage.

    One construction path shared by the physical gate, the extraction stage and the
    terminal evidence builder, so no stage can end up applying a slightly different
    admission rule than another.
    """
    from mineocclude.prospective.package_binding import (
        artifact_version_tag, package_directory,
    )

    version_tag = artifact_version_tag(manifest["artifact_id"])
    package = package_directory(version_tag, ROOT)
    authority_path = ROOT / manifest["authority_binding"]["path"]
    _document, authority_sha = load_capture_provenance_authority(
        package, version_tag=version_tag, authority_path=authority_path, repository=ROOT)
    return build_capture_admission_context(
        authority=load_json(authority_path), manifest=manifest,
        manifest_sha256=sha256_file(manifest_path),
        authority_sha256=sha256_file(authority_path),
        scientific_run_id=manifest["run_namespace"],
        processing_source_commit_sha=current_source_commit,
        capture_provenance_authority_sha256=authority_sha,
        repository=ROOT)


def require_admitted_capture_receipt(manifest: dict, unit: dict, receipt: dict, *,
                                     capture_admission,
                                     durable_verifier=verify_remote_durable_objects) -> dict:
    """Revalidate one RAW CAPTURE unit against its own frozen capture provenance.

    The capture counterpart to :func:`require_durable_unit_receipt`. That function
    stays exactly as it is for derived units -- the physical gate, the extractions,
    the readouts, the terminal -- because those artifacts are produced by the
    software running now and must bind its commit. A raw capture already physically
    happened, so it is admitted on capture-critical closure equality instead, and
    its historical commit is never compared to successor HEAD.
    """
    prefix = manifest.get("durable_prefix")
    if not isinstance(prefix, str) or not prefix.startswith("s3://"):
        raise RuntimeError("Stage-2 durable prefix is missing")
    try:
        record = capture_admission.admit(unit, receipt)
    except CaptureAdmissionError as exc:
        raise RuntimeError(f"capture admission refused: {unit.get('unit_id')}: {exc}") from exc
    if not durable_verifier(unit, receipt):
        raise RuntimeError(f"predecessor remote durability failed: {unit.get('unit_id')}")
    return record


def require_durable_unit_receipt(manifest: dict, manifest_path: Path, unit: dict,
                                 receipt: dict, *, current_source_commit: str,
                                 durable_verifier=verify_remote_durable_objects) -> None:
    """Revalidate a predecessor unit from bound local and remote raw evidence."""
    prefix = manifest.get("durable_prefix")
    if not isinstance(prefix, str) or not prefix.startswith("s3://"):
        raise RuntimeError("Stage-2 durable prefix is missing")
    expected_uri = durable_unit_uri(manifest, unit.get("unit_id"))
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


def campaign_commit() -> str:
    """The source freeze THIS Stage-2 campaign was authorized under.

    Replaces ``git rev-parse HEAD`` at every processing site. The provenance
    receipt this reads is the same artifact ``require_backend_authorization``
    has already verified end to end, so the value is bound to the campaign
    rather than to whatever happens to be checked out when a later stage runs.
    """
    provenance_path = Path(os.environ.get("MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH", ""))
    if not provenance_path.is_file():
        raise RuntimeError("Stage-2 processing requires the bound pre-outcome provenance receipt")
    return campaign_source_commit(load_json(provenance_path))


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
    stage1_provenance_path = Path(
        os.environ.get("MINEOCCLUDE_STAGE1_PREOUTCOME_PROVENANCE_PATH", ""))
    if not all(path.is_file() for path in (authorization_path, evidence_path, decision_path,
                                           stage1_manifest_path, provenance_path,
                                           stage1_provenance_path)):
        raise PermissionError("direct Stage-2 backend invocation lacks authorization artifacts")
    head = campaign_commit()
    require_stage2_authorization(manifest, load_json(authorization_path),
        authorization_receipt_path=authorization_path,
        stage1_decision=load_json(decision_path), authority_path=authority_path,
        manifest_path=manifest_path, stage1_manifest_path=stage1_manifest_path,
        stage1_evidence_path=evidence_path, stage1_decision_path=decision_path,
        current_source_commit=head,
        preoutcome_provenance_path=provenance_path,
        stage1_preoutcome_provenance_path=stage1_provenance_path)


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
    source_commit = campaign_commit()
    checksum_path = bundle / "sha256_manifest.json"
    atomic_write_json(checksum_path, {"unit_id": unit_id,
        "authority_sha256": manifest["authority_binding"]["sha256"],
        "manifest_sha256": sha256_file(manifest_path), "source_commit_sha": source_commit,
        "scientific_run_id": manifest["run_namespace"], "files": objects})
    uri = durable_unit_uri(manifest, unit_id)
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
                                    manifest_sha256: str, current_source_commit: str,
                                    capture_admission) -> dict:
    """Validate all physical, coverage, pair, and provenance conditions before extraction.

    The provenance condition is the repaired one. This gate used to require every
    capture receipt's ``source_commit_sha`` to equal the campaign commit, which is a
    source-homogeneity proxy: correct while one freeze takes all fifty captures, and
    a correctness bug the moment a downstream defect forces a successor freeze,
    because it then rejects valid durable captures and the pipeline's response is to
    recollect them. Each capture is now admitted against its own frozen capture
    provenance plus capture-critical closure equality, and the cohort must resolve to
    exactly one closure. Full-repository commits may differ; the apparatus may not.
    """
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
    admitted: dict[str, dict] = {}
    for unit_id, unit in expected.items():
        receipt = receipts.get(unit_id, {})
        reasons: list[str] = []
        if receipt.get("status") != "COMPLETE_VALIDATED_DURABLE": reasons.append("durability")
        if receipt.get("unit_id") != unit_id: reasons.append("identity")
        if receipt.get("authority_sha256") != manifest["authority_binding"]["sha256"]: reasons.append("authority_provenance")
        if receipt.get("manifest_sha256") != manifest_sha256: reasons.append("manifest_provenance")
        try:
            admitted[unit_id] = capture_admission.admit(unit, receipt)
        except CaptureAdmissionError as exc:
            reasons.append(f"capture_admission:{exc}"[:200])
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
    # One apparatus, however many commits took it. Stated directly rather than
    # proxied by commit equality, and the per-unit capture commits are retained so a
    # mixed-commit cohort is visible in the gate result instead of normalized away.
    try:
        cohort_closure = require_homogeneous_capture_closure(list(admitted.values()))
    except CaptureAdmissionError as exc:
        raise RuntimeError(f"Stage-2 capture cohort failed closed: {exc}") from exc
    return {"status": "PASS", "capture_units": len(expected), "paired_trajectories": len(by_trajectory),
            "required_checks": sorted(PHYSICAL_CHECKS | {"path_state", "durability", "runtime_provenance", "pair_coverage", "capture_admission"}),
            "capture_provenance_split": {
                "cohort_capture_critical_closure_sha256": cohort_closure,
                "processing_source_commit": current_source_commit,
                "capture_source_commit_by_unit": {
                    unit_id: record["capture_source_commit"]
                    for unit_id, record in sorted(admitted.items())},
                "distinct_capture_source_commits": sorted(
                    {record["capture_source_commit"] for record in admitted.values()}),
                "all_admitted_capture_closures_equal": True}}


def capture_receipt(manifest: dict, unit_id: str) -> dict:
    unit = next(unit for unit in manifest["capture_units"] if unit["unit_id"] == unit_id)
    return load_json(Path(unit["receipt_path"]))


def gates(manifest: dict, manifest_path: Path, unit_id: str) -> None:
    receipts = {unit["unit_id"]: capture_receipt(manifest, unit["unit_id"])
                for unit in manifest["capture_units"]}
    head = campaign_commit()
    capture_admission = backend_capture_admission(manifest, manifest_path,
                                                  current_source_commit=head)
    for unit in manifest["capture_units"]:
        # A CAPTURE unit, so it is admitted against its own frozen capture
        # provenance and capture-critical closure equality -- never against
        # successor HEAD. Requiring commit equality here was the last surviving
        # instance of the source-homogeneity proxy: the physical gate IS a derived
        # unit and its own receipt still binds HEAD in complete() below, but the
        # fifty raw captures it reads are historical evidence, and a successor
        # freeze does not make a durable capture invalid.
        require_admitted_capture_receipt(manifest, unit, receipts[unit["unit_id"]],
                                         capture_admission=capture_admission)
        verify_bound_stage2_physical_evidence(unit, receipts[unit["unit_id"]],
                                              load_json(ROOT / manifest["authority_binding"]["path"]))
    complete(manifest, manifest_path, unit_id, {"physical_gates": validate_physical_gate_receipts(
        manifest, receipts, manifest_sha256=sha256_file(manifest_path), current_source_commit=head,
        capture_admission=capture_admission)})


def extraction(manifest: dict, manifest_path: Path, unit_id: str) -> None:
    gate = load_json(Path(manifest["physical_gate_unit"]["receipt_path"]))
    head = campaign_commit()
    require_durable_unit_receipt(manifest, manifest_path, manifest["physical_gate_unit"], gate,
                                 current_source_commit=head)
    if gate.get("physical_gates", {}).get("status") != "PASS":
        raise RuntimeError("physical-gate PASS is required before extraction")
    receipts = {unit["unit_id"]: capture_receipt(manifest, unit["unit_id"])
                for unit in manifest["capture_units"]}
    capture_admission = backend_capture_admission(manifest, manifest_path,
                                                  current_source_commit=head)
    validate_physical_gate_receipts(manifest, receipts, manifest_sha256=sha256_file(manifest_path),
                                    current_source_commit=head,
                                    capture_admission=capture_admission)
    unit = next(unit for unit in manifest["extraction_units"] if unit["unit_id"] == unit_id)
    source = next(item for item in manifest["capture_units"] if item["unit_id"] == unit["source_capture_unit_id"])
    source_receipt = capture_receipt(manifest, source["unit_id"])
    # Revalidate the exact source immediately before scientific extraction.
    # A durable physical-gate PASS from an earlier step cannot rescue a frame or
    # package changed locally after that gate was written.
    # A CAPTURE unit: admitted against its own frozen capture provenance, never
    # against successor HEAD.
    source_admission = require_admitted_capture_receipt(
        manifest, source, source_receipt, capture_admission=capture_admission)
    capture_root = verify_local_capture_inventory(source, source_receipt)
    authority = load_json(ROOT / manifest["authority_binding"]["path"])
    target_rows = authority["stage2_policy"]["required_target_rows_per_capture"]
    token_rows, token_cols = authority["apparatus"]["visual_token_grid"]
    expected_shape = [target_rows, token_rows * token_cols, LAYER4_HIDDEN_SIZE]
    output_root = receipt_path().parent.parent.parent / "activations"
    # NEW-B002: the authority's own row set is handed to the extractor, which
    # proves its tau lookup equals it before opening a frame. Neither source is
    # preferred on disagreement; extraction refuses.
    expected_rows = source.get("target_model_frame_indices")
    if not isinstance(expected_rows, list) or len(expected_rows) != target_rows:
        raise RuntimeError(
            f"Stage-2 extraction requires {target_rows} authority-selected target rows")
    # The two typed identities, both derived from frozen authority rather than
    # from the bytes they validate: the legacy identity from the authority's
    # layout_id plus this unit's episode, and the Stage-2 identity from the
    # manifest unit itself.
    identity = resolve_typed_capture_identity(authority, source)
    record = Layer4Extractor().extract(
        source["unit_id"], capture_root, output_root,
        expected_target_model_frame_indices=expected_rows,
        scientific_trajectory_id=identity.scientific_trajectory_id,
        expected_legacy_capture_trajectory_id=identity.legacy_capture_trajectory_id)
    if record.get("layer") != 4 or record.get("shape") != expected_shape:
        raise RuntimeError("layer-4 extraction identity mismatch")
    # NEW-B001: refuse to persist activations whose producing model cannot be
    # named. The superseded receipt emitted checkpoint_sha256="" and failed open.
    identity = require_activation_identity(record, label=unit_id)
    require_target_rows_authority_bound(record, expected_rows, label=unit_id)
    activation = Path(record["activation_path"])
    relative_activation = f"activation/{activation.name}"
    uri = manifest["durable_prefix"].rstrip("/") + f"/derived/{unit_id}/{relative_activation}"
    complete(manifest, manifest_path, unit_id, {"source_capture_unit_id": source["unit_id"], "layer": 4,
        "shape": expected_shape, "activation_path": str(activation),
        "activation_sha256": sha256_file(activation), "durable_activation_uri": uri,
        "model_runtime_identity": identity,
        "main_checkpoint_sha256": identity["main_checkpoint_sha256"],
        "vae_checkpoint_sha256": identity["vae_checkpoint_sha256"],
        "targets": list(record["targets"]),
        "target_rows_authority_bound": True,
        # The provenance split, on the derived artifact: this activation was
        # PRODUCED by the successor source, from a capture TAKEN under whatever
        # commit actually took it. Both are stated; neither is inferred.
        "processing_source_commit": head,
        "source_capture_unit_id": source["unit_id"],
        "source_capture_receipt_sha256": sha256_file(Path(source["receipt_path"])),
        "source_capture_source_commit": source_admission["capture_source_commit"],
        "source_capture_capture_critical_closure_sha256":
            source_admission["capture_critical_closure_sha256"],
        "capture_taken_under_processing_commit":
            source_admission["capture_taken_under_processing_commit"],
        "legacy_capture_trajectory_id": identity.legacy_capture_trajectory_id,
        "scientific_trajectory_id": identity.scientific_trajectory_id},
        additional_files={relative_activation: activation})


def decision_fir(direction: str) -> list[float]:
    """The frozen causal-FIR kernel for a direction, from the bound Stage-1 decision.

    The walk into the decision document lives in ``causal_fir_kernel`` and is
    delegated to rather than repeated: the unit-1 prober checks the same labels
    this readout reconstructs, and two slightly different reads of one frozen
    document is exactly the kind of divergence that has bitten this pipeline
    before.
    """
    path = Path(os.environ.get("MINEOCCLUDE_STAGE1_DECISION_PATH", ""))
    if not path.is_file():
        raise RuntimeError("bound Stage-1 decision is required for labels")
    return causal_fir_kernel(load_json(path), direction)


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
    expected_shape = (target_rows, token_rows * token_cols, LAYER4_HIDDEN_SIZE)
    arrays, rows, identities, outer, directions = [], [], [], {}, {}
    reference_identity = None
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
        # Re-checked at the point of scientific consumption, not only at the
        # point of production: a readout must never load an activation whose
        # checkpoint is unnamed, whose model differs from the cohort's, or whose
        # rows were never proved against the authority.
        observed_identity = require_activation_identity(receipt, label=capture_id)
        require_target_rows_authority_bound(receipt, ticks, label=capture_id)
        if reference_identity is None:
            reference_identity = observed_identity
        else:
            verify_activation_checkpoint_binding(receipt, reference_identity, label=capture_id)
        relative_activation = f"activation/{activation.name}"
        if receipt.get("durable_objects", {}).get(relative_activation) != receipt["activation_sha256"]:
            raise RuntimeError(f"activation durable inventory mismatch: {capture_id}")
        array = np.load(activation, mmap_mode="r")
        if array.shape != expected_shape or array.dtype != np.dtype(LAYER4_ACTIVATION_DTYPE):
            raise RuntimeError(f"activation shape/dtype mismatch: {capture_id}")
        arrays.append(array); trajectory = identity["trajectory_id"]; identities.append(trajectory)
        outer[trajectory] = identity["outer_fold"]; directions[trajectory] = identity["direction"]
        for offset, (tick, x) in enumerate(zip(ticks, labels, strict=True)):
            rows.append({"trajectory_id": trajectory, "run_id": capture_id, "scene": scene,
                "activation_row": offset, "model_frame_idx": tick, "server_tick_is_not_label": tick,
                "label_mapping": "qualified_causal_fir", "tau": offset + 1,
                "outer_fold": identity["outer_fold"], "direction": identity["direction"], "world_x": x})
    return np.concatenate(arrays), np.asarray([row["world_x"] for row in rows]), rows, identities, outer, directions


#: The confidence-bound definition this module implements. Recorded in the
#: readout receipt as a measured fact rather than read back out of the authority,
#: which is the whole of B004: a verifier that compares the authority against
#: itself proves nothing about what the readout did.
BOOTSTRAP_CONFIDENCE_BOUND = "two_sided_95_numpy_quantile_0.025_0.975"
BOOTSTRAP_STATISTIC = "mean_of_resampled_per_trajectory_r2"
BOOTSTRAP_GENERATOR = "numpy.random.default_rng.choice(replace=True)"


def summary(rows: list[dict], key: str, policy: dict) -> tuple[dict, dict]:
    """Summarize one scene, and report the bootstrap configuration actually used.

    The second return value is a *measurement of this call*, not a restatement of
    the authority: the seed handed to the generator, the number of resamples
    drawn, the population resampled, and the interval definition applied. The
    readout receipt carries it, evidence consumes it from there, and the
    evaluator compares it to frozen authority -- so a readout that resampled rows
    instead of trajectories, or drew a different seed, is refusable.
    """
    metrics = scalar_metrics(rows, key)
    values = np.asarray([metrics["per_trajectory"][name]["r2"] for name in sorted(metrics["per_trajectory"])])
    unit = policy["bootstrap_unit"]
    if unit != "WHOLE_TRAJECTORY":
        raise RuntimeError(f"unsupported bootstrap resampling unit: {unit!r}")
    resamples = int(policy["bootstrap_resamples"])
    seed = int(policy["bootstrap_seed"])
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(resamples, len(values)), replace=True).mean(axis=1)
    configuration = {"unit": unit, "resamples": resamples, "seed": seed,
        "resample_population": "per_trajectory_macro_r2_sorted_by_trajectory_id",
        "resample_population_size": int(values.size),
        "statistic": BOOTSTRAP_STATISTIC,
        "confidence_bound_definition": BOOTSTRAP_CONFIDENCE_BOUND,
        "generator": BOOTSTRAP_GENERATOR}
    return {"rmse_blocks": metrics["trajectory_aggregated_rmse"],
        "mae_blocks": metrics["trajectory_aggregated_mae"], "macro_r2": metrics["macro_r2"],
        "bootstrap95_macro_r2": [float(np.quantile(draws, .025)), float(np.quantile(draws, .975))]}, configuration


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
    head = campaign_commit()
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
    bootstrap_configurations: list[dict] = []
    for scene in ("WALL", "NO_WALL"):
        features, target, rows, identities, outer, directions = load_scene(manifest, scene)
        if kind == "BEST_K":
            predictions, selection, _ = best_k_readout(features, target, rows, identities, outer, directions)
            key = "predicted_best_k"
        else:
            predictions, selection, _ = full_readout(features, target, rows, identities, outer, directions)
            key = "predicted_full"
        # Pooled out-of-fold coverage, checked at the point of production as well
        # as at the terminal: a readout that left a row unpredicted, or predicted
        # one twice, must not reach an evidence document at all.
        if set(predictions) != set(range(len(rows))):
            raise RuntimeError(
                f"{kind} {scene}: out-of-fold predictions do not cover each row exactly once")
        for index, row in enumerate(rows): row[key] = float(predictions[index])
        metrics, metrics_bootstrap = summary(rows, key, policy)
        tau_maximum = policy["training_only_time_baseline_training_tau_maximum"]
        baseline = training_time_baseline(rows, target, tau_maximum)
        for index, row in enumerate(rows): row["predicted_training_time_baseline"] = float(baseline[index])
        baseline_metrics, baseline_bootstrap = summary(rows, "predicted_training_time_baseline", policy)
        tau_rows = [row for row in rows if row["tau"] <= tau_maximum]
        baseline_tau1_15, tau_bootstrap = summary(tau_rows, "predicted_training_time_baseline", policy)
        bootstrap_configurations.extend([metrics_bootstrap, baseline_bootstrap, tau_bootstrap])
        output["scenes"][scene] = {"metrics": metrics, "training_time_baseline": baseline_metrics,
                                    "training_time_baseline_tau1_15": baseline_tau1_15,
                                    "selection_by_outer_fold": selection}
    # B004: the configuration the readout ACTUALLY resampled under, recorded by
    # the component that performed it. Every summary call in this readout must
    # have used one configuration; a divergence between them is a defect in this
    # file, not something to average over.
    if any(item != bootstrap_configurations[0] for item in bootstrap_configurations):
        raise RuntimeError("readout applied more than one bootstrap configuration")
    output["bootstrap_configuration"] = bootstrap_configurations[0]
    if kind == "BEST_K":
        checks = best_k_qualification_checks(output["scenes"], policy)
        output["qualification_checks"] = checks
        output["qualification_status"] = "PASS" if all(checks.values()) else "FAIL"
    complete(manifest, manifest_path, unit_id, output)


def terminal(manifest: dict, manifest_path: Path, unit_id: str) -> None:
    """Run the evidence-builder and evaluator chain; consume its decision.

    This used to copy ``best["qualification_status"]`` into a receipt, which is
    not an evaluation: the component that computed the metrics also graded them,
    and nothing independent ever re-derived a gate. B009 replaces that with the
    same three-part chain Stage-1 has -- deterministic evidence, an independent
    evaluator reading only frozen authority, and a decision artifact that must
    re-derive byte-identically from what it binds.

    No scientific logic is duplicated here. Terminal assembles the inputs,
    delegates, and then *verifies the reproduction* before persisting anything.
    """
    head = campaign_commit()
    best_unit = next(unit for unit in manifest["readout_and_terminal_units"]
                     if unit["pipeline_stage"] == "best_k")
    full_unit = next(unit for unit in manifest["readout_and_terminal_units"]
                     if unit["pipeline_stage"] == "full")
    best = load_json(Path(best_unit["receipt_path"])); full = load_json(Path(full_unit["receipt_path"]))
    require_durable_unit_receipt(manifest, manifest_path, best_unit, best,
                                 current_source_commit=head)
    require_durable_unit_receipt(manifest, manifest_path, full_unit, full,
                                 current_source_commit=head)
    if full.get("readout") != "FULL" or best.get("readout") != "BEST_K":
        raise RuntimeError("readout receipts incomplete")

    authority_path = ROOT / manifest["authority_binding"]["path"]
    decision_authority_path = ROOT / manifest["stage2_decision_authority_binding"]["path"]
    evidence = build_stage2_evidence(
        manifest, manifest_path=manifest_path, authority_path=authority_path,
        stage2_decision_authority_path=decision_authority_path,
        stage1_manifest_path=Path(os.environ["MINEOCCLUDE_STAGE1_MANIFEST_PATH"]),
        stage1_evidence_path=Path(os.environ["MINEOCCLUDE_STAGE1_EVIDENCE_PATH"]),
        stage1_decision_path=Path(os.environ["MINEOCCLUDE_STAGE1_DECISION_PATH"]),
        stage2_authorization_path=Path(os.environ["MINEOCCLUDE_STAGE2_AUTHORIZATION_PATH"]),
        preoutcome_provenance_path=Path(os.environ["MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH"]),
        stage1_preoutcome_provenance_path=Path(
            os.environ["MINEOCCLUDE_STAGE1_PREOUTCOME_PROVENANCE_PATH"]),
        source_commit_sha=head,
        capture_admission=backend_capture_admission(manifest, manifest_path,
                                                    current_source_commit=head))

    bundle = receipt_path().parent / "terminal"
    bundle.mkdir(parents=True, exist_ok=True)
    evidence_path = bundle / "stage2_evidence.json"
    atomic_write_json(evidence_path, evidence)
    decision = evaluate_stage2(
        evidence, authority=load_json(authority_path),
        decision_authority=load_json(decision_authority_path), manifest=manifest,
        authority_sha256=sha256_file(authority_path),
        decision_authority_sha256=sha256_file(decision_authority_path),
        manifest_sha256=sha256_file(manifest_path),
        evidence_sha256=sha256_file(evidence_path))
    decision_path = bundle / "stage2_decision.json"
    atomic_write_json(decision_path, decision)
    # The decision is persisted only after it has been proved to re-derive from
    # its own bound evidence and the frozen authority.
    require_stage2_decision_reproduction(
        decision, evidence_path=evidence_path, authority_path=authority_path,
        stage2_decision_authority_path=decision_authority_path,
        manifest_path=manifest_path, decision_path=decision_path)

    complete(manifest, manifest_path, unit_id, {
        "development_qualification": decision["status"],
        "stage2_decision_artifact_id": decision["artifact_id"],
        "stage2_decision_sha256": sha256_file(decision_path),
        "stage2_evidence_sha256": sha256_file(evidence_path),
        "stage2_decision_reproduced_from_bound_evidence": True,
        "stage2_decision_status_was_re_derived_not_copied": True,
        "BEST_K_controls": True, "FULL_may_rescue": False,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
        "confirmatory_collection_authorized": False,
        "may_authorize_confirmatory_collection": False,
        "may_authorize_next_rung": False},
        additional_files={"stage2_evidence.json": evidence_path,
                          "stage2_decision.json": decision_path})


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
