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
