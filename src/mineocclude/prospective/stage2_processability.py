#!/usr/bin/env python3
"""The production Stage-2 operational processability probes (B002).

What was wrong
==============

:mod:`mineocclude.prospective.unit1_checkpoint` implemented a complete unit-1
gate and nothing in production ever constructed one. ``run-stage2`` built its
``DurableController`` without a checkpoint, no production ``Prober`` existed, and
the module was therefore dead code: a real campaign would have captured all fifty
expensive scientific trajectories before anything tried to *process* one, and a
structural defect downstream of capture would have surfaced only after the whole
budget was spent.

This module supplies the missing half -- the probes themselves -- and
``development_controller.run-stage2`` now wires them in.

Two probes, deliberately different
==================================

:func:`capture_unit_structural_probe` runs after **every** completed capture
unit. It establishes only what can be established without a model: the receipt
binds this campaign, the durable objects read back, the local bytes match the
durable inventory, the frozen target rows resolve out of the capture's own
visibility stream, the temporal binding re-derives the receipt's labels, and the
row count is the authority's. It is cheap, it needs no GPU, and it turns "a
capture the pipeline cannot consume" into a stop at unit N instead of a
discovery at unit 50.

:func:`production_unit1_prober` runs **once**, after the first capture unit, and
additionally performs a real layer-4 extraction of that unit into an
operational-only workspace: the hook resolves, the activation has the frozen
shape and dtype, its values are finite, its model identity is bound, and the
downstream loader accepts it. It is the expensive probe, so it runs once.

Why the campaign is still capture-first
=======================================

The frozen Stage-2 design is capture-first by rule, not by scheduling
convenience: ``fail_closed_before_extraction`` is true, ``pipeline_order`` is
validated as an exact sequence by
:func:`~mineocclude.prospective.development_workflow.validate_stage2_manifest_design`,
and the physical gate is a *cohort* gate -- it checks WALL/NO_WALL pair path
coherence and pair target-window agreement, which cannot be evaluated until both
scenes of a pair exist, and full 50-unit coverage. Interleaving scientific
extraction with capture would therefore require weakening a frozen scientific
rule, which is not this session's to decide. So the ordering is preserved exactly
and the per-unit protection is structural instead.

What these probes may never do
==============================

They are OPERATIONAL. Everything they emit is structural -- present/absent,
shape, dtype, finiteness, identity, resolvability. They never compute, read, or
expose a decoder result, an error term, a baseline comparison, a K selection, or
any scientific status; :data:`~mineocclude.prospective.unit1_checkpoint.FORBIDDEN_OUTCOME_FIELDS`
is enforced against every fact they produce, before it is written and again
before it is honoured. A failure is BLOCKED, never a scientific FAIL, and it
changes nothing about the design: no replacement unit, no reminted seed, no
different identity, target row, layer, or threshold.

The operational activation is written to a workspace that is not the scientific
activation tree and is not registered in any manifest inventory, so it cannot be
mistaken for -- or consumed as -- scientific evidence.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from mineocclude.prospective.activation_binding import (
    require_activation_identity, require_target_rows_authority_bound,
)
from mineocclude.prospective.capture_admission import (
    CaptureAdmissionContext, CaptureAdmissionError, resolve_typed_capture_identity,
)
from mineocclude.prospective.development_workflow import (
    EvidenceError, causal_fir_targets, durable_unit_uri, load_json, sha256_file,
    verify_remote_durable_objects,
)
from mineocclude.prospective.unit1_checkpoint import (
    OperationalCheckpointBlocked, REQUIRED_CHECKS, refuse_outcome_fields, run_checkpoint,
)

#: The subset of :data:`~mineocclude.prospective.unit1_checkpoint.REQUIRED_CHECKS`
#: that needs no model, no GPU, and no checkpoint load. These are what every
#: capture unit is probed for; the remainder are unit 1's alone.
STRUCTURAL_CHECKS = (
    "CAPTURE_RECEIPT_VALID",
    "DURABILITY_VALID",
    "EXPECTED_FILES_PRESENT",
    "TARGET_ROWS_RESOLVABLE",
    "TEMPORAL_BINDING_RESOLVES",
    "EXPECTED_TARGET_COUNT",
)

#: Everything else: the checks that require actually producing an activation.
EXTRACTION_CHECKS = tuple(name for name in REQUIRED_CHECKS if name not in STRUCTURAL_CHECKS)

# The two sets must partition the checkpoint's own contract exactly. A structural
# check named here but absent from REQUIRED_CHECKS would be probed per unit and
# never reach the checkpoint receipt; one dropped from both would be silently
# unprobed, which is indistinguishable from a check that would have failed.
if set(STRUCTURAL_CHECKS) | set(EXTRACTION_CHECKS) != set(REQUIRED_CHECKS) \
        or set(STRUCTURAL_CHECKS) & set(EXTRACTION_CHECKS):
    raise ImportError(
        "the structural and extraction probe check sets do not partition "
        "unit1_checkpoint.REQUIRED_CHECKS")

#: Directory name, under the campaign's receipt root, that operational probe
#: output is written to. Deliberately outside the scientific ``activations``
#: tree and named so nothing can mistake it for evidence.
OPERATIONAL_WORKSPACE = "operational_processability"


class StructuralProbeBlocked(RuntimeError):
    """A completed capture unit is not structurally processable.

    Like :class:`~mineocclude.prospective.unit1_checkpoint.OperationalCheckpointBlocked`,
    deliberately not an ``EvidenceError`` and deliberately not a verdict.
    """


def causal_fir_kernel(stage1_decision: Mapping[str, Any], direction: str) -> list[float]:
    """The frozen causal-FIR group-delay kernel for one motion direction.

    The single canonical read of this value. ``stage2_backend.decision_fir``
    delegates here rather than re-walking the decision document, so the labels a
    readout reconstructs and the labels a probe checks cannot be resolved by two
    slightly different paths.
    """
    methods = stage1_decision["gates"]["render_server_temporal_alignment"][
        "detail"][direction]["methods"]
    return next(method["kernel"] for method in methods
                if method["method_id"] == "causal_fir_group_delay")


def capture_root_for(unit: Mapping[str, Any]) -> Path:
    """Where the driver wrote this unit's capture tree."""
    return Path(unit["receipt_path"]).parent.parent / "captures" / str(unit["unit_id"])


def _structural_facts(unit: Mapping[str, Any], receipt: Mapping[str, Any], *,
                      manifest: Mapping[str, Any], manifest_sha256: str,
                      authority_sha256: str, source_commit_sha: str,
                      scientific_run_id: str, required_target_rows: int,
                      stage1_decision: Mapping[str, Any],
                      durable_verifier: Callable[..., bool],
                      capture_admission: CaptureAdmissionContext,
                      ) -> tuple[dict[str, bool], dict[str, Any]]:
    """Establish the model-free half of processability. Never raises for a check.

    ``CAPTURE_RECEIPT_VALID`` is a CAPTURE-provenance check, and that is the whole
    of the repair here. It used to require the receipt's ``source_commit_sha`` to
    equal the *currently executing* campaign's commit -- a homogeneity proxy that
    silently reclassifies a valid, durable, physically irreproducible capture as
    invalid the moment a downstream defect forces a successor freeze. It now
    verifies the capture against its OWN frozen capture provenance and separately
    requires its capture-critical closure to equal the cohort's authorized one, so
    a full-repository commit may differ only where the capture-determining
    apparatus provably did not.

    ``source_commit_sha`` is still a parameter, and is still the successor's: the
    checkpoint RECEIPT this probe feeds is a derived processing artifact and binds
    current processing provenance. The two are kept apart deliberately.
    """
    unit_id = str(unit.get("unit_id"))
    checks = {name: False for name in STRUCTURAL_CHECKS}
    facts: dict[str, Any] = {"unit_id": unit_id, "probe_kind": "STRUCTURAL_ONLY"}

    try:
        admission = capture_admission.admit(unit, receipt)
        checks["CAPTURE_RECEIPT_VALID"] = True
        facts["capture_admission"] = {
            key: value for key, value in admission.items()
            if key in ("capture_source_commit", "capture_critical_closure_sha256",
                       "capture_compatibility", "durable_object_count",
                       "durable_object_inventory_sha256", "typed_capture_identity",
                       "capture_and_processing_commits_equal")}
        # Recorded so a mixed-commit cohort stays VISIBLE rather than hidden behind
        # a boolean: the per-unit capture commit is retained even when it differs
        # from the processing commit.
        facts["capture_source_commit"] = admission["capture_source_commit"]
        facts["capture_critical_closure_sha256"] = (
            admission["capture_critical_closure_sha256"])
        facts["processing_source_commit"] = source_commit_sha
    except CaptureAdmissionError as exc:
        checks["CAPTURE_RECEIPT_VALID"] = False
        # Named to avoid the forbidden outcome substrings screened by
        # ``refuse_outcome_fields``; "error" is one of them.
        facts["capture_admission_refusal"] = f"{type(exc).__name__}: {exc}"

    if checks["CAPTURE_RECEIPT_VALID"]:
        checks["DURABILITY_VALID"] = bool(durable_verifier(unit, receipt))
        facts["durable_object_count"] = len(receipt.get("durable_objects") or {})

    root = capture_root_for(unit)
    absent: list[str] = []
    divergent: list[str] = []
    declared = receipt.get("durable_objects")
    if isinstance(declared, Mapping) and declared:
        for relative, expected in sorted(declared.items()):
            path = root / str(relative)
            if not path.is_file():
                absent.append(str(relative))
            elif sha256_file(path) != expected:
                divergent.append(str(relative))
        for required in ("raw/server_state.jsonl", "raw/visibility.jsonl",
                         "capture_package_v0_1.json"):
            if required not in declared:
                absent.append(required)
    else:
        absent.append("<durable inventory absent>")
    checks["EXPECTED_FILES_PRESENT"] = not absent and not divergent
    facts["absent_capture_files"] = sorted(absent)
    facts["capture_files_diverging_from_durable_inventory"] = sorted(divergent)

    # The typed identity boundary, established per unit rather than only inside the
    # extractor: the raw capture package must carry the authority-derived LEGACY
    # identity and the Stage-2 visibility rows must carry the SCIENTIFIC one.
    try:
        from mineocclude.prospective.capture_admission import (
            verify_capture_package_identity, verify_visibility_rows_scientific_identity,
        )
        identity = resolve_typed_capture_identity(capture_admission.authority, unit)
        package = json.loads((root / "capture_package_v0_1.json").read_text())
        verify_capture_package_identity(package, identity)
        rows = [json.loads(line) for line
                in (root / "raw/visibility.jsonl").read_text().splitlines() if line]
        verify_visibility_rows_scientific_identity(rows, identity)
        facts["typed_identity_binding"] = "VERIFIED_BOTH_NAMESPACES"
        facts["legacy_capture_trajectory_id"] = identity.legacy_capture_trajectory_id
        facts["scientific_trajectory_id"] = identity.scientific_trajectory_id
    except Exception as exc:                        # noqa: BLE001 -- any fault blocks
        facts["typed_identity_binding"] = "REFUSED"
        facts["typed_identity_refusal"] = f"{type(exc).__name__}: {exc}"
        checks["CAPTURE_RECEIPT_VALID"] = False

    physical = receipt.get("stage2_physical_evidence")
    rows = physical.get("target_model_frame_indices") if isinstance(physical, Mapping) else None
    expected_rows = list(unit.get("target_model_frame_indices") or [])
    checks["TARGET_ROWS_RESOLVABLE"] = (isinstance(rows, list) and rows == expected_rows
                                        and bool(expected_rows))
    checks["EXPECTED_TARGET_COUNT"] = (isinstance(rows, list)
                                       and len(rows) == int(required_target_rows))
    facts["target_row_count"] = len(rows) if isinstance(rows, list) else 0
    facts["target_rows_equal_frozen_manifest"] = checks["TARGET_ROWS_RESOLVABLE"]

    # The temporal binding: the frozen FIR kernel applied to this unit's own
    # server state must reproduce the labels the receipt recorded AND the labels
    # the frozen manifest expects. Structural: it establishes that the binding
    # resolves, and says nothing about whether any of it decodes.
    try:
        state_path = root / "raw/server_state.jsonl"
        positions = [float(json.loads(line)["sheep_x"])
                     for line in state_path.read_text().splitlines() if line]
        labels = causal_fir_targets(positions, rows,
                                    causal_fir_kernel(stage1_decision, str(unit["direction"])))
        recorded = physical.get("aligned_target_world_x_blocks") if isinstance(physical, Mapping) else None
        checks["TEMPORAL_BINDING_RESOLVES"] = (
            labels == recorded
            and labels == list(unit.get("expected_causal_fir_target_world_x_blocks") or []))
        facts["temporal_binding_reconstructed_rows"] = len(labels)
    except Exception as exc:                        # noqa: BLE001 -- any fault blocks
        checks["TEMPORAL_BINDING_RESOLVES"] = False
        facts["temporal_binding_fault"] = f"{type(exc).__name__}: {exc}"
    return checks, facts


def capture_unit_structural_probe(
        *, manifest: Mapping[str, Any], manifest_sha256: str, authority_sha256: str,
        source_commit_sha: str, scientific_run_id: str, required_target_rows: int,
        stage1_decision: Mapping[str, Any],
        capture_admission: CaptureAdmissionContext,
        durable_verifier: Callable[..., bool] = verify_remote_durable_objects,
        ) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build the per-capture-unit structural probe the controller runs each time.

    Raises :class:`StructuralProbeBlocked` on any failed check, which stops the
    remaining collection. It is an operational stop: nothing about the design,
    the identity, the seed or the analysis changes in response to it.
    """
    def probe(unit: Mapping[str, Any]) -> dict[str, Any]:
        unit_id = str(unit.get("unit_id"))
        receipt_path = Path(unit["receipt_path"])
        try:
            receipt = load_json(receipt_path)
        except (EvidenceError, OSError):
            receipt = {}
        checks, facts = _structural_facts(
            unit, receipt, manifest=manifest, manifest_sha256=manifest_sha256,
            authority_sha256=authority_sha256, source_commit_sha=source_commit_sha,
            scientific_run_id=scientific_run_id, required_target_rows=required_target_rows,
            stage1_decision=stage1_decision, durable_verifier=durable_verifier,
            capture_admission=capture_admission)
        refuse_outcome_fields({"structural_facts": facts}, "capture unit structural probe")
        failing = sorted(name for name, ok in checks.items() if not ok)
        if failing:
            raise StructuralProbeBlocked(
                f"capture unit {unit_id} is not structurally processable: failing "
                f"checks {failing}. Remaining scientific collection is stopped. This "
                f"is an OPERATIONAL block and is not a scientific FAIL; do not replace "
                f"the unit, remint its seed, or alter any scientific parameter.")
        return {"unit_id": unit_id, "checks": dict(sorted(checks.items())),
                "structural_facts": dict(sorted(facts.items()))}
    return probe


def production_unit1_prober(
        *, manifest: Mapping[str, Any], manifest_sha256: str, authority_sha256: str,
        source_commit_sha: str, scientific_run_id: str, required_target_rows: int,
        expected_activation_shape: list[int], expected_activation_dtype: str,
        stage1_decision: Mapping[str, Any], workspace: Path,
        capture_admission: CaptureAdmissionContext,
        durable_verifier: Callable[..., bool] = verify_remote_durable_objects,
        extractor_factory: Callable[[], Any] | None = None,
        ):
    """The real production prober: structural checks plus one live layer-4 probe.

    ``extractor_factory`` defaults to the production ``Layer4Extractor``, imported
    lazily so that constructing a controller never pulls the model stack into a
    process that is not going to probe.
    """
    def prober(unit: Mapping[str, Any], receipt: Mapping[str, Any]):
        checks, facts = _structural_facts(
            unit, receipt, manifest=manifest, manifest_sha256=manifest_sha256,
            authority_sha256=authority_sha256, source_commit_sha=source_commit_sha,
            scientific_run_id=scientific_run_id, required_target_rows=required_target_rows,
            stage1_decision=stage1_decision, durable_verifier=durable_verifier,
            capture_admission=capture_admission)
        checks.update({name: False for name in EXTRACTION_CHECKS})
        facts["probe_kind"] = "STRUCTURAL_AND_LAYER4_EXTRACTION"
        facts["operational_workspace"] = str(workspace)
        facts["operational_activation_is_scientific_evidence"] = False
        if any(not checks[name] for name in STRUCTURAL_CHECKS):
            # No point loading a checkpoint for bytes that already failed.
            facts["layer4_probe_skipped_after_structural_block"] = True
            return checks, facts

        factory = extractor_factory
        if factory is None:
            def factory():                          # pragma: no cover - needs the model stack
                from p2d_extract import Layer4Extractor

                extractor = Layer4Extractor()
                extractor.ensure_loaded()
                return extractor

        workspace.mkdir(parents=True, exist_ok=True)
        capture_identity = resolve_typed_capture_identity(
            capture_admission.authority, unit)
        record = factory().extract(
            str(unit["unit_id"]), capture_root_for(unit), workspace,
            expected_target_model_frame_indices=list(unit["target_model_frame_indices"]),
            scientific_trajectory_id=capture_identity.scientific_trajectory_id,
            expected_legacy_capture_trajectory_id=(
                capture_identity.legacy_capture_trajectory_id))
        checks["LAYER4_HOOK_RESOLVES"] = record.get("layer") == 4
        checks["ACTIVATION_SHAPE_VALID"] = list(record.get("shape") or []) == list(
            expected_activation_shape)
        checks["ACTIVATION_DTYPE_VALID"] = record.get("dtype") == expected_activation_dtype
        facts["observed_activation_shape"] = list(record.get("shape") or [])
        facts["observed_activation_dtype"] = record.get("dtype")

        try:
            # C4: the model runtime identity is a mapping and the typed capture
            # identity is a frozen dataclass. The scientific backend bound both to
            # one name and died reading ``.legacy_capture_trajectory_id`` off the
            # mapping; this probe survived only because it never read the typed
            # one back. Kept distinct here so the shadow cannot reappear.
            runtime_identity = require_activation_identity(
                record, label=str(unit["unit_id"]))
            require_target_rows_authority_bound(
                record, list(unit["target_model_frame_indices"]),
                label=str(unit["unit_id"]))
            checks["ACTIVATION_IDENTITY_VALID"] = bool(runtime_identity)
            facts["model_runtime_id"] = runtime_identity.get("runtime_id")
        except EvidenceError as exc:
            facts["activation_identity_fault"] = f"{type(exc).__name__}: {exc}"

        activation = Path(record["activation_path"])
        array = np.load(activation, mmap_mode="r")
        checks["ACTIVATIONS_FINITE"] = bool(np.isfinite(np.asarray(array, dtype=np.float32)).all())
        # The downstream loader's own acceptance test, run against the artifact
        # this probe produced: same shape/dtype assertion, same digest check, and
        # the same reload path a readout would take.
        checks["DOWNSTREAM_LOADER_ACCEPTS"] = bool(
            tuple(array.shape) == tuple(expected_activation_shape)
            and array.dtype == np.dtype(expected_activation_dtype)
            and sha256_file(activation) == record.get("activation_sha256"))
        facts["operational_activation_byte_size"] = int(activation.stat().st_size)
        return checks, facts
    return prober


def make_unit1_checkpoint(
        *, manifest: Mapping[str, Any], manifest_sha256: str, authority_sha256: str,
        source_commit_sha: str, scientific_run_id: str, required_target_rows: int,
        expected_activation_shape: list[int], expected_activation_dtype: str,
        stage1_decision: Mapping[str, Any], receipts_root: Path,
        capture_admission: CaptureAdmissionContext,
        durable_verifier: Callable[..., bool] = verify_remote_durable_objects,
        extractor_factory: Callable[[], Any] | None = None,
        ) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """The callable ``DurableController(unit1_checkpoint=...)`` expects.

    Deliberately closes over every binding the checkpoint receipt must carry, so
    a receipt written for one campaign cannot satisfy the checkpoint of another,
    and a restart re-uses a proven receipt rather than re-doing the probe.
    """
    workspace = receipts_root / OPERATIONAL_WORKSPACE
    prober = production_unit1_prober(
        manifest=manifest, manifest_sha256=manifest_sha256,
        authority_sha256=authority_sha256, source_commit_sha=source_commit_sha,
        scientific_run_id=scientific_run_id, required_target_rows=required_target_rows,
        expected_activation_shape=expected_activation_shape,
        expected_activation_dtype=expected_activation_dtype,
        stage1_decision=stage1_decision, workspace=workspace / "activation",
        capture_admission=capture_admission,
        durable_verifier=durable_verifier, extractor_factory=extractor_factory)

    def checkpoint(unit: Mapping[str, Any]) -> dict[str, Any]:
        receipt_path = Path(unit["receipt_path"])
        try:
            receipt = load_json(receipt_path)
        except (EvidenceError, OSError):
            receipt = {}
        return run_checkpoint(
            unit=unit, receipt=receipt, prober=prober,
            receipt_path=workspace / f"unit1_checkpoint_{unit['unit_id']}.json",
            manifest_sha256=manifest_sha256, authority_sha256=authority_sha256,
            source_commit_sha=source_commit_sha, scientific_run_id=scientific_run_id)
    return checkpoint


__all__ = [
    "EXTRACTION_CHECKS", "OPERATIONAL_WORKSPACE", "OperationalCheckpointBlocked",
    "STRUCTURAL_CHECKS", "StructuralProbeBlocked", "capture_root_for",
    "capture_unit_structural_probe", "causal_fir_kernel", "make_unit1_checkpoint",
    "production_unit1_prober",
]
