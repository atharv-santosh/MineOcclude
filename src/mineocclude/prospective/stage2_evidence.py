#!/usr/bin/env python3
"""Deterministic Stage-2 evidence construction.

Mirrors the Stage-1 split exactly: this module *assembles measured facts* and
never reaches a scientific verdict. Whether the six BEST-K gates hold is
:mod:`mineocclude.prospective.stage2_decision`'s question, and it re-derives them
from what is assembled here rather than from any boolean a readout receipt
happens to carry.

What "deterministic" means here
===============================

The inventory comes from the frozen Stage-2 locked manifest, never from a glob.
Every unit named there must be present, complete, and durably bound; nothing not
named there may contribute a single row. That is the difference between "the
fifty captures the campaign was authorized to take" and "whatever fifty files
were on the disk", and it is the only version of the question a reproducible
decision can be built on.

The document this produces is closed: after it is written, no field depends on
mutable live-tree state. Digests, not paths, carry the bindings, so the decision
re-derives byte-identically from the evidence and the frozen authority alone --
which is what :func:`~mineocclude.prospective.stage2_decision.require_stage2_decision_reproduction`
then proves.

What it refuses
===============

A missing capture, an extra scientific capture, a wrong unit/fold/scene/identity,
an activation whose checkpoint binding is absent or belongs to a different model,
a target row set that was never proved against the authority, a receipt bound to
a different authority/manifest/run namespace/source freeze, a rehearsal or smoke
artifact, and a receipt carrying a predecessor package's identity. Each is a
:class:`~mineocclude.prospective.development_workflow.EvidenceError`, which the
terminal unit turns into BLOCKED -- an operational state, never a scientific FAIL.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

from mineocclude.prospective.activation_binding import (
    require_activation_identity,
    require_target_rows_authority_bound,
    verify_activation_checkpoint_binding,
)
from mineocclude.prospective.development_workflow import (
    EvidenceError, canonical_payload_sha256, load_json,
    refuse_operational_smoke_as_evidence, sha256_file,
)
from mineocclude.prospective.package_binding import (
    PackageBindingError, stage2_evidence_artifact_id,
)

SCHEMA_VERSION = "1.0"

#: The readout receipts a completed Stage-2 must carry, by pipeline stage.
REQUIRED_READOUTS = ("best_k", "full")

#: Scene names the design admits. A readout that reports any other key is not
#: the frozen experiment.
REQUIRED_SCENES = ("WALL", "NO_WALL")

#: Metric names each scene block must carry, for both the readout and its
#: time baseline. The evaluator recomputes gates from exactly these.
REQUIRED_METRIC_FIELDS = ("rmse_blocks", "mae_blocks", "macro_r2", "bootstrap95_macro_r2")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceError(f"{label} is missing or malformed")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{label} is not a number: {value!r}")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise EvidenceError(f"{label} is not finite")
    return result


def _metrics(block: Any, label: str) -> dict[str, Any]:
    mapping = _mapping(block, label)
    missing = [name for name in REQUIRED_METRIC_FIELDS if name not in mapping]
    if missing:
        raise EvidenceError(f"{label} is missing metric fields: {missing}")
    interval = mapping["bootstrap95_macro_r2"]
    if not isinstance(interval, (list, tuple)) or len(interval) != 2:
        raise EvidenceError(f"{label} bootstrap interval is not a pair")
    lower, upper = (_number(interval[0], f"{label} bootstrap lower"),
                    _number(interval[1], f"{label} bootstrap upper"))
    if lower > upper:
        raise EvidenceError(f"{label} bootstrap interval is inverted")
    return {"rmse_blocks": _number(mapping["rmse_blocks"], f"{label} rmse_blocks"),
            "mae_blocks": _number(mapping["mae_blocks"], f"{label} mae_blocks"),
            "macro_r2": _number(mapping["macro_r2"], f"{label} macro_r2"),
            "bootstrap95_macro_r2": [lower, upper]}


def _require_unit_binding(receipt: Mapping[str, Any], unit: Mapping[str, Any], *,
                          manifest: Mapping[str, Any], manifest_sha256: str,
                          source_commit_sha: str, label: str) -> None:
    """Every completed unit must be bound to this campaign, and to no other."""
    refuse_operational_smoke_as_evidence(receipt, label)
    expected = {
        "unit_id": unit.get("unit_id"),
        "status": "COMPLETE_VALIDATED_DURABLE",
        "classification": "DEVELOPMENT_ONLY",
        "confirmatory_membership": False,
        "authority_sha256": _mapping(manifest.get("authority_binding"),
                                     "manifest authority binding").get("sha256"),
        "manifest_sha256": manifest_sha256,
        "source_commit_sha": source_commit_sha,
        "scientific_run_id": manifest.get("run_namespace"),
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise EvidenceError(
                f"{label}: receipt binding mismatch on {key!r} "
                f"({receipt.get(key)!r} != {value!r})")
    objects = receipt.get("durable_objects")
    if not isinstance(objects, Mapping) or not objects:
        raise EvidenceError(f"{label}: receipt declares no durable objects")
    if not isinstance(receipt.get("durable_uri"), str) \
            or not receipt["durable_uri"].startswith("s3://"):
        raise EvidenceError(f"{label}: receipt declares no durable location")


def build_stage2_evidence(
        manifest: Mapping[str, Any], *,
        manifest_path: Path,
        authority_path: Path,
        stage2_decision_authority_path: Path,
        stage1_manifest_path: Path,
        stage1_evidence_path: Path,
        stage1_decision_path: Path,
        stage2_authorization_path: Path,
        preoutcome_provenance_path: Path,
        stage1_preoutcome_provenance_path: Path,
        source_commit_sha: str,
        reader: Callable[[Path], dict[str, Any]] = load_json,
        digest: Callable[[Path], str] = sha256_file) -> dict[str, Any]:
    """Assemble closed, digest-bound Stage-2 evidence. Reaches no verdict.

    ``reader`` and ``digest`` are injected so the whole builder is exercisable
    against fixtures without a live campaign on disk; the defaults are the real
    ones and every production caller uses them.
    """
    manifest_sha256 = digest(manifest_path)
    authority = reader(authority_path)
    policy = _mapping(_mapping(authority.get("stage2_policy"), "authority stage2_policy")
                      .get("readout"), "authority stage2_policy.readout")
    decision_authority = reader(stage2_decision_authority_path)

    try:
        artifact_id = stage2_evidence_artifact_id(manifest)
    except PackageBindingError as exc:
        raise EvidenceError("Stage-2 manifest carries no versioned identity") from exc

    binding = _mapping(manifest.get("stage2_decision_authority_binding"),
                       "Stage-2 manifest decision-authority binding")
    decision_authority_sha256 = digest(stage2_decision_authority_path)
    if binding.get("sha256") != decision_authority_sha256 \
            or binding.get("artifact_id") != decision_authority.get("artifact_id"):
        raise EvidenceError(
            "Stage-2 manifest is not bound to the decision-authority bytes on disk")

    # ---- inventory: from the frozen manifest, never from a directory listing --
    identities = manifest.get("trajectory_identities")
    captures = manifest.get("capture_units")
    extractions = manifest.get("extraction_units")
    if not isinstance(identities, list) or not isinstance(captures, list) \
            or not isinstance(extractions, list):
        raise EvidenceError("Stage-2 manifest inventory is malformed")
    expected_captures = int(manifest.get("scientific_capture_count", -1))
    if len(captures) != expected_captures:
        raise EvidenceError(
            f"Stage-2 capture inventory is {len(captures)}, manifest declares "
            f"{expected_captures}")
    required_rows = int(manifest.get("required_target_rows_per_capture", -1))
    identity_by_id = {item["trajectory_id"]: item for item in identities}

    # ---- physical gate ------------------------------------------------------
    gate_unit = _mapping(manifest.get("physical_gate_unit"), "Stage-2 physical gate unit")
    gate_receipt = reader(Path(gate_unit["receipt_path"]))
    _require_unit_binding(gate_receipt, gate_unit, manifest=manifest,
                          manifest_sha256=manifest_sha256,
                          source_commit_sha=source_commit_sha,
                          label="Stage-2 physical gate")
    gate_status = _mapping(gate_receipt.get("physical_gates"),
                           "Stage-2 physical gate result").get("status")
    if gate_status != "PASS":
        raise EvidenceError(f"Stage-2 physical gate did not PASS: {gate_status!r}")

    # ---- captures and extractions ------------------------------------------
    extraction_by_source = {}
    for unit in extractions:
        source = unit.get("source_capture_unit_id")
        if source in extraction_by_source:
            raise EvidenceError(f"Stage-2 extraction inventory duplicates {source!r}")
        extraction_by_source[source] = unit

    reference_identity: dict[str, Any] | None = None
    capture_records: list[dict[str, Any]] = []
    for unit in sorted(captures, key=lambda item: str(item.get("unit_id"))):
        unit_id = str(unit.get("unit_id"))
        trajectory = unit.get("trajectory_id")
        identity = identity_by_id.get(trajectory)
        if identity is None:
            raise EvidenceError(f"{unit_id}: capture names an unknown trajectory identity")
        if unit.get("scene") not in REQUIRED_SCENES:
            raise EvidenceError(f"{unit_id}: capture scene is outside the frozen design")

        receipt = reader(Path(unit["receipt_path"]))
        _require_unit_binding(receipt, unit, manifest=manifest,
                              manifest_sha256=manifest_sha256,
                              source_commit_sha=source_commit_sha, label=unit_id)
        physical = _mapping(receipt.get("stage2_physical_evidence"),
                            f"{unit_id} Stage-2 physical evidence")
        ticks = physical.get("target_model_frame_indices")
        if ticks != unit.get("target_model_frame_indices"):
            raise EvidenceError(f"{unit_id}: capture target rows differ from the frozen manifest")
        if not isinstance(ticks, list) or len(ticks) != required_rows:
            raise EvidenceError(f"{unit_id}: capture does not carry {required_rows} target rows")
        labels = physical.get("aligned_target_world_x_blocks")
        if labels != unit.get("expected_causal_fir_target_world_x_blocks"):
            raise EvidenceError(f"{unit_id}: aligned labels differ from the frozen manifest")
        if physical.get("contamination_rows"):
            raise EvidenceError(f"{unit_id}: target rows are contaminated")

        extraction_unit = extraction_by_source.get(unit_id)
        if extraction_unit is None:
            raise EvidenceError(f"{unit_id}: no extraction unit is bound to this capture")
        extraction = reader(Path(extraction_unit["receipt_path"]))
        _require_unit_binding(extraction, extraction_unit, manifest=manifest,
                              manifest_sha256=manifest_sha256,
                              source_commit_sha=source_commit_sha,
                              label=str(extraction_unit.get("unit_id")))
        if extraction.get("source_capture_unit_id") != unit_id:
            raise EvidenceError(f"{unit_id}: extraction is bound to a different capture")
        if extraction.get("layer") != 4:
            raise EvidenceError(f"{unit_id}: extraction is not the authorized layer-4 readout")

        # NEW-B001 and NEW-B002, enforced on the consuming side. An activation
        # whose model identity is absent, or whose rows were never proved against
        # the authority, may not contribute to a scientific decision even if it
        # was extracted successfully.
        activation_identity = require_activation_identity(
            extraction, label=f"{unit_id} activation")
        require_target_rows_authority_bound(extraction, ticks,
                                            label=f"{unit_id} activation")
        if reference_identity is None:
            reference_identity = activation_identity
        else:
            verify_activation_checkpoint_binding(
                extraction, reference_identity, label=f"{unit_id} activation")

        capture_records.append({
            "unit_id": unit_id,
            "trajectory_id": trajectory,
            "scene": unit["scene"],
            "direction": identity["direction"],
            "outer_fold": identity["outer_fold"],
            "phase_frames": identity["phase_frames"],
            "episode_id": unit.get("episode_id"),
            "capture_receipt_sha256": digest(Path(unit["receipt_path"])),
            "extraction_unit_id": extraction_unit["unit_id"],
            "extraction_receipt_sha256": digest(Path(extraction_unit["receipt_path"])),
            "activation_sha256": extraction.get("activation_sha256"),
            "activation_shape": extraction.get("shape"),
            "target_model_frame_indices": list(ticks),
            "aligned_target_world_x_blocks": list(labels),
            "target_rows_authority_bound": True,
            "server_state_sha256": receipt.get("server_state_sha256"),
            "durable_uri": receipt.get("durable_uri"),
        })

    if len(capture_records) != expected_captures:
        raise EvidenceError("Stage-2 capture inventory is incomplete after validation")
    if reference_identity is None:
        raise EvidenceError("Stage-2 evidence carries no model runtime identity")

    # ---- readouts -----------------------------------------------------------
    tails = manifest.get("readout_and_terminal_units")
    if not isinstance(tails, list):
        raise EvidenceError("Stage-2 readout inventory is malformed")
    readouts: dict[str, Any] = {}
    for stage in REQUIRED_READOUTS:
        unit = next((item for item in tails if item.get("pipeline_stage") == stage), None)
        if unit is None:
            raise EvidenceError(f"Stage-2 manifest declares no {stage} readout unit")
        receipt = reader(Path(unit["receipt_path"]))
        _require_unit_binding(receipt, unit, manifest=manifest,
                              manifest_sha256=manifest_sha256,
                              source_commit_sha=source_commit_sha,
                              label=str(unit.get("unit_id")))
        expected_kind = "BEST_K" if stage == "best_k" else "FULL"
        if receipt.get("readout") != expected_kind:
            raise EvidenceError(
                f"{unit['unit_id']}: receipt reports readout {receipt.get('readout')!r}, "
                f"not {expected_kind!r}")
        scenes = _mapping(receipt.get("scenes"), f"{unit['unit_id']} scene results")
        if set(scenes) != set(REQUIRED_SCENES):
            raise EvidenceError(
                f"{unit['unit_id']}: scene coverage is {sorted(scenes)}, "
                f"not {sorted(REQUIRED_SCENES)}")
        block: dict[str, Any] = {"readout": expected_kind,
                                 "receipt_sha256": digest(Path(unit["receipt_path"])),
                                 "scenes": {}}
        for scene in REQUIRED_SCENES:
            result = _mapping(scenes[scene], f"{unit['unit_id']} {scene}")
            block["scenes"][scene] = {
                "metrics": _metrics(result.get("metrics"),
                                    f"{unit['unit_id']} {scene} metrics"),
                "training_time_baseline": _metrics(
                    result.get("training_time_baseline"),
                    f"{unit['unit_id']} {scene} time baseline"),
                "training_time_baseline_tau1_15": _metrics(
                    result.get("training_time_baseline_tau1_15"),
                    f"{unit['unit_id']} {scene} time baseline tau1-15"),
                "selection_by_outer_fold": _selection(
                    result.get("selection_by_outer_fold"),
                    f"{unit['unit_id']} {scene}", expected_kind),
            }
        if stage == "best_k":
            # Recorded, never trusted. The evaluator re-derives every gate from
            # the metrics above and refuses the evidence if the two disagree, so
            # a hand-edited boolean cannot carry a decision.
            claimed = receipt.get("qualification_checks")
            if not isinstance(claimed, Mapping) or not claimed:
                raise EvidenceError("BEST-K readout carries no qualification checks")
            block["readout_claimed_qualification_checks"] = {
                str(name): bool(value) for name, value in sorted(claimed.items())}
            block["readout_claimed_qualification_status"] = receipt.get("qualification_status")
        readouts[stage] = block

    evidence = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "classification": "DEVELOPMENT_ONLY",
        "confirmatory_reuse_forbidden": True,
        "development_only": True,
        "scientific_run_id": manifest.get("run_namespace"),
        "source_commit_sha": source_commit_sha,
        "authority_sha256": digest(authority_path),
        "stage2_decision_authority_sha256": decision_authority_sha256,
        "stage2_manifest_sha256": manifest_sha256,
        "stage1_manifest_sha256": digest(stage1_manifest_path),
        "stage1_evidence_sha256": digest(stage1_evidence_path),
        "stage1_decision_sha256": digest(stage1_decision_path),
        "stage2_authorization_sha256": digest(stage2_authorization_path),
        "preoutcome_provenance_sha256": digest(preoutcome_provenance_path),
        "stage1_preoutcome_provenance_sha256": digest(stage1_preoutcome_provenance_path),
        "physical_gate": {
            "unit_id": gate_unit["unit_id"],
            "status": "PASS",
            "receipt_sha256": digest(Path(gate_unit["receipt_path"])),
            "checks": dict(sorted(
                _mapping(gate_receipt.get("physical_gates"), "physical gates").items()))
            if isinstance(gate_receipt.get("physical_gates"), Mapping) else {},
        },
        "model_runtime_identity": dict(sorted(reference_identity.items())),
        "main_checkpoint_sha256": reference_identity["main_checkpoint_sha256"],
        "vae_checkpoint_sha256": reference_identity["vae_checkpoint_sha256"],
        "capture_inventory": capture_records,
        "capture_count": len(capture_records),
        "trajectory_identity_count": len(identities),
        "required_target_rows_per_capture": required_rows,
        "layer": 4,
        "all_layer_extraction_performed": False,
        "bootstrap_configuration": {
            "unit": policy.get("bootstrap_unit"),
            "resamples": policy.get("bootstrap_resamples"),
            "seed": policy.get("bootstrap_seed"),
        },
        "readouts": readouts,
        "evidence_builder_asserted_scientific_status": False,
    }
    evidence["evidence_payload_sha256"] = canonical_payload_sha256(
        evidence, omit="evidence_payload_sha256")
    return evidence


def _selection(value: Any, label: str, kind: str) -> dict[str, Any]:
    """Record what each outer fold selected, as measured, without judging it."""
    mapping = _mapping(value, f"{label} selection_by_outer_fold")
    if sorted(mapping) != [str(index) for index in range(5)]:
        raise EvidenceError(f"{label} does not report all five outer folds")
    recorded: dict[str, Any] = {}
    for fold, chosen in sorted(mapping.items()):
        block = _mapping(chosen, f"{label} outer fold {fold}")
        entry = {"selected_alpha": block.get("selected_alpha"),
                 "training_trajectory_ids": list(block.get("training_trajectory_ids") or []),
                 "test_trajectory_ids": list(block.get("test_trajectory_ids") or [])}
        if kind == "BEST_K":
            entry["selected_k"] = block.get("selected_k")
            entry["selected_token_count"] = len(block.get("selected_tokens") or [])
        recorded[fold] = entry
    return recorded


def verify_evidence_payload(evidence: Mapping[str, Any]) -> None:
    """Refuse Stage-2 evidence whose own digest does not reproduce."""
    expected = canonical_payload_sha256(evidence, omit="evidence_payload_sha256")
    if evidence.get("evidence_payload_sha256") != expected:
        raise EvidenceError("Stage-2 evidence payload digest does not reproduce")
