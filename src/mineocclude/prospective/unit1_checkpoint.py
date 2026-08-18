#!/usr/bin/env python3
"""Stage-2 unit-1 OPERATIONAL processability checkpoint.

Why this exists
===============

The Stage-2 controller could collect all fifty authorized scientific captures
before anything tried to *process* one. Every structural defect downstream of
capture -- a transition schema the consumer cannot read, a scene vocabulary it
rejects, a layer-4 hook that does not resolve, an activation artifact of the
wrong dtype -- would therefore be discovered only after the entire scientific
budget had been spent, on bytes that may not be recollectable.

This checkpoint runs once, after the FIRST authorized scientific capture is
complete and durable, and proves the frozen pipeline can structurally consume
that unit before units 2-50 are allowed to run unattended.

What it is emphatically NOT
===========================

It is an OPERATIONAL gate. It answers exactly one question: "can the frozen
pipeline read these bytes at all?" It must never answer, or even observe, "are
these bytes a good scientific result?"

That distinction is load-bearing, because a gate that could see an outcome and
then permit or halt collection would make the remaining 49 captures conditional
on the first one's result -- outcome-adaptive collection, which would destroy
the prospective status of the whole design. So:

* every emitted fact is structural (present/absent, shape, dtype, finiteness,
  identity, resolvability), and :data:`FORBIDDEN_OUTCOME_FIELDS` is enforced
  against the receipt before it is written AND again before it is honoured;
* a failure is classified BLOCKED (operational), never FAIL (scientific);
* a failure stops the remaining collection and changes nothing else -- it does
  not replace unit 1, remint a seed, pick a different identity, alter k, folds,
  target rows, layer, thresholds, or any baseline definition.

Fail-closed, deterministic, receipt-bound and resumable: an existing receipt is
honoured only if it reproduces its own digest and binds the same authority,
manifest, source freeze, run namespace and unit identity the controller is
currently executing under.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from mineocclude.prospective.development_workflow import (
    EvidenceError, atomic_write_json, canonical_payload_sha256, load_json,
)

SCHEMA = "regime-a-prime-stage2-unit1-operational-processability-v0.1"

#: The structural facts the checkpoint establishes, in evaluation order. Every
#: one must be True for the checkpoint to pass; there is no partial credit and
#: no check may be skipped, because a skipped check is indistinguishable from a
#: check that would have failed.
REQUIRED_CHECKS = (
    "CAPTURE_RECEIPT_VALID",
    "DURABILITY_VALID",
    "EXPECTED_FILES_PRESENT",
    "TARGET_ROWS_RESOLVABLE",
    "TEMPORAL_BINDING_RESOLVES",
    "EXPECTED_TARGET_COUNT",
    "LAYER4_HOOK_RESOLVES",
    "ACTIVATION_SHAPE_VALID",
    "ACTIVATION_DTYPE_VALID",
    "ACTIVATIONS_FINITE",
    "ACTIVATION_IDENTITY_VALID",
    "DOWNSTREAM_LOADER_ACCEPTS",
)

#: Substrings that may never appear in a checkpoint receipt key. This is the
#: mechanical guarantee of non-adaptivity: if a future edit tried to surface a
#: decoder score, an error metric, a baseline comparison or a k selection
#: through this receipt, the receipt would be refused rather than written.
FORBIDDEN_OUTCOME_FIELDS = (
    "rmse", "mse", "mae", "r2", "score", "accuracy", "error", "loss",
    "decoder", "baseline", "best_k", "chosen_k", "selected_k", "effect",
    "hidden_vs_visible", "superiority", "pass_fail", "qualification_status",
    "estimate", "metric", "performance", "correlation",
)

#: Terminal states. BLOCKED is operational and is never a scientific verdict.
PASS = "OPERATIONAL_PROCESSABILITY_PASS"
BLOCKED = "OPERATIONAL_PROCESSABILITY_BLOCKED"


class OperationalCheckpointBlocked(RuntimeError):
    """The first scientific capture is not structurally processable.

    Deliberately not an ``EvidenceError`` and deliberately not a scientific
    verdict. Raising this halts the remaining collection and requires operator
    attention; it says nothing whatever about the hypothesis.
    """


def refuse_outcome_fields(payload: Mapping[str, Any], label: str = "checkpoint receipt") -> None:
    """Refuse any key that could carry a scientific outcome, at any depth."""
    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                lowered = str(key).lower()
                for forbidden in FORBIDDEN_OUTCOME_FIELDS:
                    if forbidden in lowered:
                        raise EvidenceError(
                            f"{label} carries a forbidden outcome-bearing field: "
                            f"{path}{key!r} (matched {forbidden!r})")
                walk(item, f"{path}{key}.")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(item, f"{path}{index}.")
    walk(payload, "")


def build_receipt(*, unit_id: str, checks: Mapping[str, Any], facts: Mapping[str, Any],
                  manifest_sha256: str, authority_sha256: str, source_commit_sha: str,
                  scientific_run_id: str) -> dict[str, Any]:
    """Assemble a checkpoint receipt from structural facts only.

    ``checks`` must cover :data:`REQUIRED_CHECKS` exactly -- no extra check may
    be invented at runtime and none may be dropped -- and every value must be a
    genuine boolean rather than something merely truthy.
    """
    if set(checks) != set(REQUIRED_CHECKS):
        missing = sorted(set(REQUIRED_CHECKS) - set(checks))
        extra = sorted(set(checks) - set(REQUIRED_CHECKS))
        raise EvidenceError(
            f"unit-1 checkpoint check coverage is wrong; missing={missing} unexpected={extra}")
    if any(not isinstance(value, bool) for value in checks.values()):
        raise EvidenceError("unit-1 checkpoint checks must be booleans")
    payload = {
        "schema_version": SCHEMA,
        "classification": "OPERATIONAL_ONLY_NOT_SCIENTIFIC_EVIDENCE",
        "status": PASS if all(checks.values()) else BLOCKED,
        "unit_id": unit_id,
        "checks": dict(sorted(checks.items())),
        "failing_checks": sorted(name for name, ok in checks.items() if not ok),
        "structural_facts": dict(sorted(facts.items())),
        "manifest_sha256": manifest_sha256,
        "authority_sha256": authority_sha256,
        "source_commit_sha": source_commit_sha,
        "scientific_run_id": scientific_run_id,
        # Stated in the artifact, not only in this docstring, so an auditor
        # reading the receipt alone can see what it does and does not claim.
        "scientific_outcome_observed": False,
        "may_alter_scientific_design": False,
        "collection_remains_prospective": True,
    }
    refuse_outcome_fields(payload)
    payload["payload_sha256"] = canonical_payload_sha256(payload, omit="payload_sha256")
    return payload


def verify_receipt(receipt: Mapping[str, Any], *, unit_id: str, manifest_sha256: str,
                   authority_sha256: str, source_commit_sha: str,
                   scientific_run_id: str) -> bool:
    """True only for an intact PASS receipt bound to this exact execution.

    Used on the resume path. Every binding is checked, so a receipt from another
    unit, another campaign, another manifest revision or another source freeze
    cannot satisfy a checkpoint it was not written for.
    """
    if not isinstance(receipt, Mapping):
        return False
    try:
        refuse_outcome_fields(receipt)
    except EvidenceError:
        return False
    if receipt.get("payload_sha256") != canonical_payload_sha256(receipt, omit="payload_sha256"):
        return False
    bindings = {"schema_version": SCHEMA, "status": PASS, "unit_id": unit_id,
                "manifest_sha256": manifest_sha256, "authority_sha256": authority_sha256,
                "source_commit_sha": source_commit_sha,
                "scientific_run_id": scientific_run_id,
                "scientific_outcome_observed": False}
    if any(receipt.get(key) != value for key, value in bindings.items()):
        return False
    checks = receipt.get("checks")
    if not isinstance(checks, Mapping) or set(checks) != set(REQUIRED_CHECKS):
        return False
    return all(checks.get(name) is True for name in REQUIRED_CHECKS)


#: A prober takes the capture unit and its receipt and returns
#: ``(checks, structural_facts)``. It is injected rather than imported so the
#: checkpoint can be exercised against fixtures and rehearsal bytes without
#: standing up a model, and so this module never imports the extraction stack.
Prober = Callable[[Mapping[str, Any], Mapping[str, Any]], "tuple[dict[str, bool], dict[str, Any]]"]


def run_checkpoint(*, unit: Mapping[str, Any], receipt: Mapping[str, Any], prober: Prober,
                   receipt_path: Path, manifest_sha256: str, authority_sha256: str,
                   source_commit_sha: str, scientific_run_id: str) -> dict[str, Any]:
    """Run, or resume, the unit-1 operational processability checkpoint.

    Resumable: an existing receipt that verifies against these exact bindings is
    honoured and the probes are not repeated, so a restart cannot re-do work
    that is already proven, nor silently accept a receipt from another run.

    Fail-closed: a prober that raises is a BLOCKED checkpoint, not a crash and
    not a scientific FAIL. The receipt is written either way -- an operator
    needs the failing-check list -- and then the block is raised.
    """
    unit_id = str(unit.get("unit_id"))
    bindings = {"unit_id": unit_id, "manifest_sha256": manifest_sha256,
                "authority_sha256": authority_sha256, "source_commit_sha": source_commit_sha,
                "scientific_run_id": scientific_run_id}
    if receipt_path.is_file():
        try:
            existing = load_json(receipt_path)
        except EvidenceError:
            existing = None
        if existing is not None and verify_receipt(existing, **bindings):
            return dict(existing)

    try:
        checks, facts = prober(unit, receipt)
        checks = {name: bool(checks.get(name, False)) for name in REQUIRED_CHECKS}
    except Exception as exc:                       # noqa: BLE001 -- any probe fault blocks
        checks = {name: False for name in REQUIRED_CHECKS}
        facts = {"prober_exception": f"{type(exc).__name__}: {exc}"}

    # Structural facts are operator-facing and are screened before they are
    # persisted, so a prober cannot smuggle an outcome through the facts map.
    refuse_outcome_fields({"structural_facts": facts})
    record = build_receipt(unit_id=unit_id, checks=checks, facts=facts,
                           manifest_sha256=manifest_sha256, authority_sha256=authority_sha256,
                           source_commit_sha=source_commit_sha,
                           scientific_run_id=scientific_run_id)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, record)
    if record["status"] != PASS:
        raise OperationalCheckpointBlocked(
            f"unit-1 operational processability BLOCKED for {unit_id}: "
            f"failing checks {record['failing_checks']}. Remaining scientific "
            f"collection is stopped. This is an OPERATIONAL block and is not a "
            f"scientific FAIL; do not replace the unit, remint its seed, or "
            f"alter any scientific parameter in response to it.")
    return record
