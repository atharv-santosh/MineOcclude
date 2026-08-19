#!/usr/bin/env python3
"""Admission of an IMMUTABLE HISTORICAL physical-gate PASS by a successor freeze.

The conflation this closes
==========================

``stage2_backend.require_durable_unit_receipt`` is the rule for DERIVED units,
and it requires ``receipt["source_commit_sha"] == the processing commit``. That
is correct for an activation this campaign is producing right now. It is wrong
for the physical gate the moment a downstream execution defect forces a
successor processing freeze: the gate is a two-and-a-quarter-hour, fifty-unit,
durably-verified PASS over an immutable cohort, and refusing it because an
unrelated extraction module was repaired is the same source-homogeneity proxy
that ``OPTION_3`` already removed on the capture side -- surviving here on the
derived side, where nobody had looked.

Why admitting it is sound, and what makes it sound
==================================================

Not "the gate is old evidence, trust it". A derived artifact IS a function of
processing source, so age alone proves nothing. What makes admission sound is
GATE-CRITICAL CLOSURE EQUALITY: the call-graph reachable, definition-granular
closure seeded at the definition that computes the gate verdict is equal at the
commit that produced the receipt and at the commit now consuming it. Equality
means the successor's own code, run on the same immutable cohort, computes the
same verdict -- so re-executing the gate could only reproduce it, and the two
hours buy nothing. Inequality means the successor genuinely changed how the gate
decides, and the receipt is refused.

The closure is re-derived here rather than asserted, and the seed is the gate
verdict rather than the capture apparatus. The reachability walk is the same
algorithm :mod:`~mineocclude.prospective.capture_closure` uses; it is seeded
locally rather than by adding an ``entrypoints`` parameter to that module,
because that module's derivation functions are themselves gate-reachable -- the
gate admits captures through them -- so parameterising them would change the very
closure this rule compares and refuse the receipt for the act of writing the
rule. A test asserts this walk reproduces the capture-critical closure exactly
when seeded at the capture entrypoints, which is what keeps the two in step.

Governance
==========

``stage2_physical_gate_admission_authority.json`` names the ONE admitted
predecessor commit explicitly. A successor that names none admits no historical
gate at all. Nothing here rewrites the receipt, and nothing here lets the
successor claim to have produced it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

# Imported by module path rather than as ``from mineocclude.prospective import
# capture_closure``, which is the convention every other consumer follows and which
# keeps the governed closure resolving to this module's real dependency instead of
# to the package __init__. The private helpers are reused deliberately: the
# reachability walk below is capture_closure's algorithm reseeded, and duplicating
# its name-resolution rules instead of reusing them is how the two would drift.
from mineocclude.prospective.capture_closure import (  # noqa: E402
    CAPTURE_ENTRYPOINTS, MODULE_HANDLE, MODULE_PROLOGUE, REPOSITORY_ROOT, SourceReader,
    _binding_targets, _FileIndex, _import_bindings, _referenced_names,
    capture_critical_digests, closure_sha256, git_reader, worktree_reader,
)

#: The definition whose output IS the gate verdict.
GATE_ENTRYPOINTS: tuple[tuple[str, str], ...] = (
    ("scripts/regime_a_prime_qualification_v0_2/stage2_backend.py", "gates"),
)

AUTHORITY_FILENAME = "stage2_physical_gate_admission_authority.json"


class PhysicalGateAdmissionError(RuntimeError):
    """A physical-gate receipt was refused. Operational -- never a scientific FAIL."""


def _reachable(read: SourceReader, entrypoints: Sequence[tuple[str, str]],
               repository: Path) -> list[tuple[str, str]]:
    """Definitions reachable from ``entrypoints``; the capture_closure walk, reseeded."""
    index: dict[str, _FileIndex | None] = {}

    def indexed(relative: str):
        if relative not in index:
            source = read(relative)
            try:
                index[relative] = None if source is None else _FileIndex(relative, source)
            except SyntaxError:
                index[relative] = None
        return index[relative]

    for relative, symbol in entrypoints:
        entry = indexed(relative)
        if entry is None or symbol not in entry.definitions:
            raise PhysicalGateAdmissionError(
                f"gate entrypoint {relative}::{symbol} is absent from this source")

    seen: set[tuple[str, str]] = set()
    stack: list[tuple[str, str]] = list(entrypoints)
    module_handles: set[str] = set()
    while stack:
        relative, symbol = stack.pop()
        if (relative, symbol) in seen:
            continue
        file_index = indexed(relative)
        if file_index is None:
            continue
        if symbol == MODULE_PROLOGUE:
            if file_index.prologue:
                seen.add((relative, symbol))
            continue
        nodes = file_index.definitions.get(symbol)
        if not nodes:
            continue
        seen.add((relative, symbol))
        for node in nodes:
            local = _import_bindings(node)
            bindings = {**file_index.module_bindings, **local}
            for name in _referenced_names(node):
                head, _, tail = name.partition(".")
                if name in file_index.definitions:
                    stack.append((relative, name))
                    continue
                if not tail and head in file_index.definitions:
                    stack.append((relative, head))
                    continue
                binding = bindings.get(name) or bindings.get(head)
                if binding is None:
                    continue
                exact = bindings.get(name) is binding
                module, imported = binding
                for target, wanted in _binding_targets(
                        module, imported, "" if exact else tail, read):
                    if wanted == MODULE_HANDLE:
                        module_handles.add(target)
                        wanted = MODULE_PROLOGUE
                    stack.append((target, wanted))

    for relative in sorted(module_handles):
        file_index = indexed(relative)
        if file_index is None:
            continue
        for symbol in file_index.definitions:
            seen.add((relative, symbol))
    for relative in {path for path, _ in seen}:
        file_index = indexed(relative)
        if file_index is not None and file_index.prologue:
            seen.add((relative, MODULE_PROLOGUE))
    return sorted(seen)


def gate_critical_closure_at(source, *, repository: Path = REPOSITORY_ROOT,
                             entrypoints: Sequence[tuple[str, str]] | None = None
                             ) -> tuple[str, dict[str, str]]:
    """``(closure_sha256, component_digests)`` for the gate verdict at one source."""
    read = git_reader(source, repository) if isinstance(source, str) else source
    symbols = _reachable(read, entrypoints or GATE_ENTRYPOINTS, repository)
    digests = capture_critical_digests(symbols, read, repository=repository)
    return closure_sha256(digests), digests


def load_gate_admission_authority(package: Path) -> tuple[dict, str]:
    """The sibling admission authority document and its sha256."""
    path = package / AUTHORITY_FILENAME
    if not path.is_file():
        raise PhysicalGateAdmissionError(
            f"physical-gate admission authority is absent: {path}")
    import hashlib
    payload = path.read_bytes()
    return json.loads(payload), hashlib.sha256(payload).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PhysicalGateAdmissionError(message)


def admit_physical_gate_receipt(manifest: dict, gate: dict, *, authority: dict,
                                admission_authority: dict,
                                manifest_sha256: str,
                                processing_source_commit: str,
                                expected_durable_uri: str,
                                expected_required_checks: Sequence[str],
                                authorized_capture_critical_closure: str,
                                repository: Path = REPOSITORY_ROOT,
                                durable_verifier=None,
                                closure_at=gate_critical_closure_at) -> dict:
    """Admit an immutable physical-gate PASS, historical or same-freeze.

    Returns an admission record naming which regime applied. Raises
    :class:`PhysicalGateAdmissionError` -- an OPERATIONAL refusal, to be reported
    as BLOCKED and never as a scientific FAIL -- on any unmet condition.
    """
    unit = manifest.get("physical_gate_unit") or {}
    policy = authority["stage2_policy"]

    # ---- receipt integrity and identity -------------------------------------
    _require(gate.get("status") == "COMPLETE_VALIDATED_DURABLE",
             f"physical-gate receipt is not durable-complete: {gate.get('status')!r}")
    _require(gate.get("unit_id") == unit.get("unit_id"),
             f"physical-gate receipt unit identity mismatch: {gate.get('unit_id')!r}")
    _require(gate.get("authority_sha256") == manifest["authority_binding"]["sha256"],
             "physical-gate receipt authority binding mismatch")
    _require(gate.get("manifest_sha256") == manifest_sha256,
             "physical-gate receipt manifest binding mismatch")
    _require(gate.get("scientific_run_id") == manifest.get("run_namespace"),
             "physical-gate receipt run-namespace mismatch")
    _require(gate.get("durable_uri") == expected_durable_uri,
             "physical-gate receipt durable-uri mismatch")

    # ---- the gate result, and the semantics that produced it ----------------
    gates = gate.get("physical_gates")
    _require(isinstance(gates, dict), "physical-gate receipt carries no gate result")
    _require(gates.get("status") == "PASS",
             f"physical-gate result is not PASS: {gates.get('status')!r}")
    _require(list(gates.get("required_checks") or []) == sorted(expected_required_checks),
             "physical-gate check vocabulary differs from this implementation's")
    _require(gates.get("capture_units") == policy["scientific_capture_count"],
             "physical-gate cohort size differs from the authorized capture count")
    identities = policy["paired_trajectory_identities"]
    expected_pairs = identities if isinstance(identities, int) else len(identities)
    _require(gates.get("paired_trajectories") == expected_pairs,
             "physical-gate pair count differs from the authorized identity count")

    # ---- exact cohort identity, not merely cohort size -----------------------
    split = gates.get("capture_provenance_split") or {}
    by_unit = split.get("capture_source_commit_by_unit")
    _require(isinstance(by_unit, dict), "physical-gate receipt carries no per-unit cohort")
    _require(sorted(by_unit) == sorted(u["unit_id"] for u in manifest["capture_units"]),
             "physical-gate cohort identity differs from the manifest capture units")
    _require(split.get("cohort_capture_critical_closure_sha256")
             == authorized_capture_critical_closure,
             "physical-gate cohort apparatus closure is not the authorized closure")
    _require(split.get("all_admitted_capture_closures_equal") is True,
             "physical-gate cohort did not resolve to one capture apparatus")

    # ---- anti-laundering: the receipt must agree with itself -----------------
    recorded = gate.get("source_commit_sha")
    _require(isinstance(recorded, str) and len(recorded) == 40,
             "physical-gate receipt does not name the source that produced it")
    _require(split.get("processing_source_commit") == recorded,
             "physical-gate receipt source commit disagrees with the gate's own record")

    # ---- which admission regime applies -------------------------------------
    if recorded == processing_source_commit:
        regime = "SAME_FREEZE"
    else:
        admitted = (admission_authority.get("admitted_historical_physical_gate") or {})
        named = admitted.get("predecessor_processing_source_commit")
        _require(named == recorded,
                 f"physical-gate receipt was produced under {recorded}, which this "
                 f"successor's admission authority does not name as its admitted "
                 f"predecessor ({named!r})")
        _require(admitted.get("gate_result") == "PASS",
                 "admission authority does not record a PASS for the named predecessor")
        # The load-bearing condition: the successor would compute the same verdict.
        historical, _ = closure_at(recorded, repository=repository)
        current, _ = closure_at(worktree_reader(repository), repository=repository)
        _require(historical == current,
                 f"gate-critical closure changed between {recorded[:7]} and this "
                 f"successor ({historical[:16]} vs {current[:16]}); the historical "
                 f"verdict no longer represents what this source would compute")
        regime = "HISTORICAL_ADMITTED"

    if durable_verifier is not None and not durable_verifier(unit, gate):
        raise PhysicalGateAdmissionError("physical-gate remote durability failed")

    return {"admission_regime": regime,
            "gate_source_commit": recorded,
            "processing_source_commit": processing_source_commit,
            "gate_result": "PASS",
            "capture_units": gates.get("capture_units"),
            "paired_trajectories": gates.get("paired_trajectories"),
            "cohort_capture_critical_closure_sha256":
                split.get("cohort_capture_critical_closure_sha256")}


#: The sibling authority governing admission of a SURVIVING DURABLE PAYLOAD after
#: the local wrapper receipt was destroyed. Separate document, separate identity,
#: separate regime: a successor that does not ship this file cannot reach the
#: payload path at all.
DURABLE_PAYLOAD_AUTHORITY_FILENAME = (
    "stage2_historical_durable_gate_payload_admission_authority.json")

#: The admission regime this path emits. Deliberately distinct from both
#: ``SAME_FREEZE`` and ``HISTORICAL_ADMITTED`` so no downstream artifact can
#: record a wrapper admission it did not receive.
DURABLE_PAYLOAD_REGIME = "HISTORICAL_DURABLE_GATE_PAYLOAD_ADMITTED"


def load_durable_payload_admission_authority(package: Path) -> tuple[dict, str]:
    """The durable-payload admission authority document and its sha256."""
    path = package / DURABLE_PAYLOAD_AUTHORITY_FILENAME
    if not path.is_file():
        raise PhysicalGateAdmissionError(
            "historical durable gate-payload admission authority is absent: "
            f"{path}. Without it this successor admits no durable payload, and a "
            "lost wrapper receipt is simply a blocker.")
    import hashlib
    payload = path.read_bytes()
    return json.loads(payload), hashlib.sha256(payload).hexdigest()


def admit_historical_durable_gate_payload(
        manifest: dict, *, payload_bytes: bytes, checksum_manifest_bytes: bytes,
        authority: dict, payload_authority: dict, authority_sha256: str,
        manifest_sha256: str, processing_source_commit: str,
        expected_required_checks: Sequence[str],
        authorized_capture_critical_closure: str,
        repository: Path = REPOSITORY_ROOT,
        closure_at=gate_critical_closure_at) -> dict:
    """Admit the SURVIVING DURABLE PAYLOAD of a physical-gate PASS whose wrapper was lost.

    What this is, and what it is not
    ================================

    It is NOT a new physical gate: nothing is measured. It is NOT a replay:
    nothing is re-executed over the cohort. It is NOT receipt reconstruction:
    no wrapper is built, written, or named as the original. It is an ADMISSION
    VERIFIER over two immutable durable objects that a host rebuild could not
    reach -- the gate's own ``payload.json`` and its ``sha256_manifest.json``.

    Why the loss of the wrapper does not lose the result
    ====================================================

    :func:`admit_physical_gate_receipt` reads eight fields off the wrapper:
    ``status``, ``unit_id``, ``authority_sha256``, ``manifest_sha256``,
    ``scientific_run_id``, ``durable_uri``, ``source_commit_sha`` and
    ``physical_gates``. Six of those are independently recorded in the surviving
    checksum manifest, which is a separately written document; ``physical_gates``
    IS the surviving payload; and ``durable_uri`` is re-derived here from the
    manifest rather than read from anywhere. The one field with no surviving
    counterpart is the wrapper's ``status``, and the honest response is to not
    assert it: this function never claims the wrapper was
    ``COMPLETE_VALIDATED_DURABLE``, and the record it returns says so by naming a
    regime that no wrapper path can produce.

    What is actually load-bearing is unchanged from the wrapper rule, because it
    was never the wrapper: GATE-CRITICAL CLOSURE EQUALITY at the gate's source
    commit and at the source consuming it now. Equality means this source, run on
    the same immutable cohort, computes the same verdict -- so the verdict is
    reproducible in principle and re-running it could only reproduce it.
    Inequality means the successor genuinely changed how the gate decides, and
    the payload is refused exactly as a wrapper would be.

    Fail-closed, in the strict direction
    ====================================

    Both durable objects must reproduce the digests the governing authority pins;
    the checksum manifest must vouch for the payload independently; every campaign
    binding must equal the LIVE authority and manifest bytes rather than anything
    the payload asserts about itself; the cohort must be this manifest's exact
    capture-unit identity set; the apparatus closure must be the authorized one;
    the check vocabulary must be this implementation's own; and the result must be
    PASS. A FAIL, a BLOCKED, an incomplete payload, a short or long cohort, or a
    payload and manifest that disagree are all refusals.

    Finally, this path refuses to operate at the gate's own commit. Admitting a
    payload in place of a wrapper is a recovery measure for evidence that has
    genuinely become unreachable; at the gate's own freeze the wrapper question
    does not arise, and allowing it there would create a second, looser route to
    the same conclusion.
    """
    unit = manifest.get("physical_gate_unit") or {}
    policy = authority["stage2_policy"]
    admitted = payload_authority.get("admitted_historical_durable_gate_payload") or {}

    # ---- 1. the governing authority must actually authorize this ------------
    _require(payload_authority.get("status") == "FROZEN",
             "durable gate-payload admission authority is not FROZEN")
    _require(payload_authority.get("authorized_option")
             == "OPTION_4_ADMIT_SURVIVING_DURABLE_GATE_PAYLOAD_AFTER_WRAPPER_LOSS",
             "durable gate-payload admission authority authorizes a different option")
    lost = payload_authority.get("lost_wrapper") or {}
    _require(lost.get("recoverable") is False,
             "durable gate-payload admission requires the authority to record the "
             "wrapper as unrecoverable; it does not")
    named_source = admitted.get("gate_source_commit")
    _require(isinstance(named_source, str) and len(named_source) == 40,
             "durable gate-payload admission authority names no gate source commit")

    # ---- 2. both durable objects reproduce their pinned digests -------------
    import hashlib

    payload_digest = hashlib.sha256(payload_bytes).hexdigest()
    checksum_digest = hashlib.sha256(checksum_manifest_bytes).hexdigest()
    _require(checksum_digest == admitted.get("durable_checksum_manifest_sha256"),
             f"durable gate checksum manifest digest is {checksum_digest}, not the "
             f"authorized {admitted.get('durable_checksum_manifest_sha256')}")
    _require(payload_digest == admitted.get("durable_payload_sha256"),
             f"durable gate payload digest is {payload_digest}, not the authorized "
             f"{admitted.get('durable_payload_sha256')}")

    try:
        checksum_manifest = json.loads(checksum_manifest_bytes)
        payload = json.loads(payload_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PhysicalGateAdmissionError(
            "durable gate evidence is not readable JSON") from exc
    _require(isinstance(checksum_manifest, dict) and isinstance(payload, dict),
             "durable gate evidence is malformed")

    # ---- 3. the checksum manifest vouches for the payload independently -----
    files = checksum_manifest.get("files")
    _require(isinstance(files, dict), "durable gate checksum manifest lists no files")
    recorded_payload = files.get(admitted.get("durable_payload_object"))
    _require(recorded_payload == payload_digest,
             "durable gate checksum manifest and payload disagree: the manifest "
             f"records {recorded_payload!r} for the payload object, the payload "
             f"hashes to {payload_digest}")

    # ---- 4. campaign bindings, against the LIVE bytes ------------------------
    _require(checksum_manifest.get("authority_sha256") == authority_sha256,
             "durable gate evidence authority binding mismatch")
    _require(checksum_manifest.get("manifest_sha256") == manifest_sha256,
             "durable gate evidence manifest binding mismatch")
    _require(checksum_manifest.get("scientific_run_id") == manifest.get("run_namespace"),
             "durable gate evidence run-namespace mismatch")
    _require(checksum_manifest.get("unit_id") == unit.get("unit_id"),
             f"durable gate evidence unit identity mismatch: "
             f"{checksum_manifest.get('unit_id')!r}")
    recorded_source = checksum_manifest.get("source_commit_sha")
    _require(recorded_source == named_source,
             f"durable gate evidence was produced under {recorded_source!r}, which "
             f"this successor's authority does not name as its admitted gate source "
             f"({named_source!r})")

    # ---- 5. the gate result, and the semantics that produced it -------------
    gates = payload.get("physical_gates")
    _require(isinstance(gates, dict), "durable gate payload carries no gate result")
    _require(gates.get("status") == "PASS",
             f"durable gate result is not PASS: {gates.get('status')!r}")
    _require(list(gates.get("required_checks") or []) == sorted(expected_required_checks),
             "durable gate check vocabulary differs from this implementation's")
    _require(gates.get("capture_units") == policy["scientific_capture_count"],
             "durable gate cohort size differs from the authorized capture count")
    identities = policy["paired_trajectory_identities"]
    expected_pairs = identities if isinstance(identities, int) else len(identities)
    _require(gates.get("paired_trajectories") == expected_pairs,
             "durable gate pair count differs from the authorized identity count")

    # ---- 6. exact cohort identity, not merely cohort size --------------------
    split = gates.get("capture_provenance_split") or {}
    by_unit = split.get("capture_source_commit_by_unit")
    _require(isinstance(by_unit, dict), "durable gate payload carries no per-unit cohort")
    _require(sorted(by_unit) == sorted(u["unit_id"] for u in manifest["capture_units"]),
             "durable gate cohort identity differs from the manifest capture units")
    _require(split.get("cohort_capture_critical_closure_sha256")
             == authorized_capture_critical_closure,
             "durable gate cohort apparatus closure is not the authorized closure")
    _require(split.get("all_admitted_capture_closures_equal") is True,
             "durable gate cohort did not resolve to one capture apparatus")

    # ---- 7. anti-laundering: the payload must agree with the manifest -------
    _require(split.get("processing_source_commit") == recorded_source,
             "durable gate payload processing commit disagrees with the checksum "
             "manifest's source commit; the two durable objects do not describe "
             "the same gate execution")

    # ---- 8. this is the HISTORICAL regime, and only the historical regime ---
    _require(recorded_source != processing_source_commit,
             "the durable-payload path is a recovery measure for a lost wrapper "
             "under a SUCCESSOR freeze; at the gate's own commit the wrapper "
             "question does not arise and this path is refused")

    # ---- 9. the load-bearing condition -------------------------------------
    historical, _ = closure_at(recorded_source, repository=repository)
    current, _ = closure_at(worktree_reader(repository), repository=repository)
    _require(historical == current,
             f"gate-critical closure changed between {recorded_source[:7]} and this "
             f"successor ({historical[:16]} vs {current[:16]}); the historical "
             f"verdict no longer represents what this source would compute")

    return {"admission_regime": DURABLE_PAYLOAD_REGIME,
            "gate_source_commit": recorded_source,
            "processing_source_commit": processing_source_commit,
            "gate_result": "PASS",
            "capture_units": gates.get("capture_units"),
            "paired_trajectories": gates.get("paired_trajectories"),
            "cohort_capture_critical_closure_sha256":
                split.get("cohort_capture_critical_closure_sha256"),
            "gate_critical_closure_sha256": current,
            "durable_payload_sha256": payload_digest,
            "durable_checksum_manifest_sha256": checksum_digest,
            # Stated as facts, never as claims of success. Downstream artifacts
            # record these verbatim, so an activation produced this way can never
            # be read as one produced under a surviving wrapper.
            "physical_gate_wrapper_receipt_recovered": False,
            "physical_gate_wrapper_receipt_regenerated": False,
            "physical_gate_replay_performed": False,
            "lost_wrapper_receipt_sha256": lost.get("receipt_sha256")}
