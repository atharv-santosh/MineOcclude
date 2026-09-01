"""A5 / I22 — the P1 pilot campaign: ten capture units, resumable.

``a5_capture`` knows how to drive and validate ONE unit. This module owns the
campaign around it: which units the frozen plan names, what order they run in,
what the ledger says has already been done, and what a restart is allowed to
skip. The division matters for resume — the campaign is the only thing that
decides whether a unit runs, and it decides it from the hash-chained ledger and
the unit's own spec hash, never from the status document.

The Recovery Runbook's A5/A7 procedure, implemented literally:

    1. Read the ledger; collect COMPLETE unit IDs.
    2. For each planned unit in frozen order, skip if COMPLETE.
    3. If a final directory exists, re-validate against the spec hash, then
       finish durability.
    4. If a same-spec partial exists and the last state is CAPTURED, resume
       packaging.
    5. Otherwise discard the partial, append PLANNED with retry_same_spec=true,
       and re-capture.

Pilot identities only. ``e3_t01``..``e3_t25`` cannot reach this code: the plan is
checked against the pilot roster before a single episode is issued, and authority
2.1 forbids identity replacement, so a production identity spent on a debug run
would shrink the cohort permanently.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from mineocclude.experiment_iii.a5_capture import (
    WITNESS_LEGS,
    CaptureUnitSpec,
    next_witness_episode_base,
    assemble_unit_inventory,
    build_unit_spec,
    capture_a5_unit,
    capture_unit_directory,
    validate_capture_unit,
)
from mineocclude.experiment_iii.authority import (
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_IDS,
    TARGET_ROWS_PER_CAPTURE,
    verify_authority_binding,
)
from mineocclude.experiment_iii.capture_driver import FrameSink
from mineocclude.experiment_iii.conditions import build_condition_map
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.execution import HashChainLedger
from mineocclude.experiment_iii.schema import ConditionId, read_jsonl
from mineocclude.experiment_iii.status import StatusDocument

__all__ = [
    "PilotCampaign",
    "plan_specs",
    "unit_durable_receipt",
    "verify_no_production_identity",
]

STAGE = "A5"
NEXT_STAGE = "A6"


def verify_no_production_identity(plan: Mapping[str, Any]) -> None:
    """Fail closed if the plan names anything but the two pilot identities."""
    named = {str(unit["identity"]) for unit in plan["units"]}
    production = sorted(named & set(PRODUCTION_IDENTITY_IDS))
    if production:
        raise ExperimentIIIError(
            "P1_INCOMPLETE",
            f"the P1 plan names production identities {production}; authority 6A "
            f"spends only {list(PILOT_IDENTITY_IDS)} on the pilot",
        )
    unknown = sorted(named - set(PILOT_IDENTITY_IDS))
    if unknown:
        raise ExperimentIIIError(
            "P1_INCOMPLETE", f"the P1 plan names non-pilot identities {unknown}"
        )


def plan_specs(
    plan: Mapping[str, Any],
    identity_rows: Sequence[Mapping[str, Any]],
    ladder: Mapping[str, Any],
) -> list[CaptureUnitSpec]:
    """Resolve the frozen plan into executable unit specs, in plan order.

    The materials come from ``build_condition_map(ladder)`` -- the P0 selection --
    and are then checked against what the plan wrote down. A disagreement is a
    refusal, not a preference: the plan and the ladder must be the same evidence.
    """
    verify_no_production_identity(plan)
    conditions = build_condition_map(ladder)
    by_identity = {str(row["identity"]): row for row in identity_rows}
    specs: list[CaptureUnitSpec] = []
    for unit in plan["units"]:
        identity = str(unit["identity"])
        if identity not in by_identity:
            raise ExperimentIIIError(
                "PROVENANCE_BINDING_MISSING",
                f"{identity} has no row in the pilot identity manifest",
            )
        condition = conditions[ConditionId(str(unit["condition_id"]))]
        specs.append(build_unit_spec(unit, by_identity[identity], condition))
    if len(specs) != int(plan["captures"]):
        raise ExperimentIIIError(
            "P1_INCOMPLETE",
            f"resolved {len(specs)} units, the plan freezes {plan['captures']}",
        )
    return specs


def unit_durable_receipt(unit_dir: Path, spec: CaptureUnitSpec) -> dict[str, Any]:
    """Hash every banked file and read it back, then record what was proven.

    Durability here is local-mirror: the unit is published under its own
    directory, every file is hashed, and every hash is verified by re-reading the
    bytes. A receipt that merely lists the files it wrote proves nothing about
    whether they can be read again, which is the only thing durability means.
    """
    unit_dir = Path(unit_dir)
    files: dict[str, dict[str, Any]] = {}
    total = 0
    for path in sorted(unit_dir.rglob("*")):
        if not path.is_file() or path.name == "durable_receipt.json":
            continue
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        # Read back a second time and compare: this is the round trip.
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ExperimentIIIError(
                "DURABILITY_READBACK_MISMATCH",
                f"{path} did not read back to the same bytes",
            )
        relative = path.relative_to(unit_dir).as_posix()
        files[relative] = {"sha256": digest, "bytes": len(payload)}
        total += len(payload)
    body = {
        "schema_version": "mineocclude-experiment-iii-durable-receipt-v1",
        "authority_section": "8.2",
        "capture_unit_id": spec.capture_unit_id,
        "spec_sha256": spec.spec_sha256,
        "durability_mode": "LOCAL_MIRROR_SAME_POOL",
        "file_count": len(files),
        "total_bytes": total,
        "files": files,
        "readback_verified": True,
    }
    target = unit_dir / "durable_receipt.json"
    payload = json.dumps(body, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(target)
    return body


class PilotCampaign:
    """Ten units, one ledger, one status document, resumable at any boundary."""

    def __init__(
        self,
        specs: Sequence[CaptureUnitSpec],
        *,
        output_root: Path,
        ledger_path: Path,
        status_root: Path | None = None,
        namespace_root: Path | None = None,
        server_episode_root: Path | None = None,
        server_run_root: Path | None = None,
        rve_condition_scores: Mapping[str, float] | None = None,
        source_closure: str | None = None,
        stage: str = STAGE,
        next_stage: str = NEXT_STAGE,
    ) -> None:
        # A7 runs this same loop over 125 production units. The engine is what
        # A5 qualified -- ledger-driven resume, same-spec-only retry, validate
        # then bank then COMPLETE -- and authority 8.3 gives A5 and A7 the same
        # unit state machine, so A7 reuses it rather than growing a second
        # capture engine whose resume semantics nothing has ever demonstrated.
        # Only the stage labels and the roster differ.
        self.stage = stage
        self.next_stage = next_stage
        self.specs = list(specs)
        self.output_root = Path(output_root)
        # ``namespace_root`` is the repository root the write guard measures
        # against. Production passes nothing and gets the real repository; a test
        # passes its tmp_path so the guard still runs, against that tree.
        self.namespace_root = Path(namespace_root) if namespace_root else None
        # The dedicated server writes server_state.jsonl and physical_receipt.json
        # under its own run directory; the client writes the frames and the tick
        # ledger under a different one. Both roots are needed to assemble a unit.
        self.server_episode_root = (
            Path(server_episode_root) if server_episode_root else None
        )
        # The server's run directory: where startspec looks for the motion
        # schedule it refuses to run without.
        self.server_run_root = Path(server_run_root) if server_run_root else None
        #: Allocated lazily on first capture, above every witness episode already
        #: on disk in either apparatus tree, then advanced per unit. The mod never
        #: overwrites a completed episode, so a reused id is a hard refusal.
        self._witness_next: int | None = None
        self.ledger = HashChainLedger(Path(ledger_path), root=self.namespace_root)
        self.status_root = status_root
        self.rve_condition_scores = dict(rve_condition_scores or {})
        self.binding = verify_authority_binding()
        self.source_closure = source_closure
        self.started = time.time()
        self.errors_seen = 0
        self._status = StatusDocument(
            stage=self.stage,
            program_stage="III_A",
            total_units=len(self.specs),
            next_stage=self.next_stage,
            iii_a_status="RUNNING",
            iii_b_status="NOT_STARTED",
            authority_sha256=self.binding["AUTHORITY_SHA256"],
            source_closure=source_closure,
        )

    # -- status -----------------------------------------------------------
    #
    # Observational only. Nothing in this class ever reads a status field to
    # decide what to do; every control-flow input comes from the ledger or from
    # a unit's own spec hash. ``_publish`` is called for its side effect on disk
    # and its return value is deliberately ignored everywhere.

    def _publish(
        self,
        *,
        stage_status: str,
        message: str,
        current_unit: str | None = None,
        retry_count: int = 0,
        blocker: str | None = None,
        validator_status: str = "NOT_RUN",
    ) -> None:
        complete = self.ledger.complete_units()
        self._status.stage_status = stage_status
        self._status.completed_units = len(
            [spec for spec in self.specs if spec.capture_unit_id in complete]
        )
        self._status.current_unit = current_unit
        self._status.last_completed_unit = self._last_complete(complete)
        self._status.last_message = message[:512]
        self._status.errors_seen = self.errors_seen
        self._status.current_blocker = blocker
        self._status.retry_count = retry_count
        self._status.post_stage_validator_status = validator_status
        try:
            self._status.write(self.status_root)
        except Exception:  # pragma: no cover - status must never break capture
            # Losing the status document must never affect resume, validation or
            # results (LIVE_STATUS_CONTRACT). A failure to write one is not a
            # reason to stop capturing.
            pass

    def _allocate_witness_episodes(self, sink: FrameSink) -> int:
        """Reserve one witness episode id per leg, monotonically."""
        if self._witness_next is None:
            self._witness_next = next_witness_episode_base(
                Path(sink.root),
                self.server_episode_root,
            )
        allocated = self._witness_next
        self._witness_next += WITNESS_LEGS
        return allocated

    def _server_episode_dir(self, spec: CaptureUnitSpec) -> Path:
        if self.server_episode_root is None:
            raise ExperimentIIIError(
                "ENV_RUNTIME_VERSION_MISMATCH",
                "the campaign has no server episode root; server_state.jsonl and "
                "physical_receipt.json cannot be located",
            )
        return self.server_episode_root / f"episode_{spec.episode_id}"

    def _last_complete(self, complete: set[str]) -> str | None:
        for spec in reversed(self.specs):
            if spec.capture_unit_id in complete:
                return spec.capture_unit_id
        return None

    # -- resume -----------------------------------------------------------

    def resume_decision(self, spec: CaptureUnitSpec) -> dict[str, Any]:
        """Recovery Runbook steps 1-5, for one unit."""
        state = self.ledger.last_state(spec.capture_unit_id)
        unit_dir = capture_unit_directory(self.output_root, spec)
        recorded = self._recorded_spec_hash(spec.capture_unit_id)
        drifted = recorded is not None and recorded != spec.spec_sha256
        if state == "COMPLETE" and not drifted:
            return {"action": "SKIP", "reason": "COMPLETE_VALIDATED_DURABLE"}
        if drifted:
            # Same-spec resume only. A spec change is not a resume; it is a new
            # unit, and the partial from the old spec must not be adopted.
            return {
                "action": "RECAPTURE",
                "reason": "SPEC_DRIFT",
                "recorded_spec_sha256": recorded,
                "current_spec_sha256": spec.spec_sha256,
            }
        if unit_dir.is_dir() and state in ("CAPTURED", "VALIDATED", "DURABLE"):
            return {"action": "FINISH", "reason": f"RESUME_FROM_{state}"}
        if unit_dir.is_dir():
            return {"action": "RECAPTURE", "reason": "DISCARD_PARTIAL"}
        if state is not None:
            # Ledger history but nothing on disk: an attempt that died before it
            # banked anything. Runbook step 5 -- discard the partial and append
            # PLANNED with retry_same_spec=true. Recording it as a first attempt
            # would hide a retry, and authority 8.3 requires every failed attempt
            # to stay visible in the unit's provenance.
            return {"action": "RECAPTURE", "reason": f"DISCARDED_PARTIAL_FROM_{state}"}
        return {"action": "CAPTURE", "reason": "NOT_STARTED"}

    def _recorded_spec_hash(self, unit_id: str) -> str | None:
        for record in reversed(self.ledger.records):
            if record["unit_id"] == unit_id and "spec_sha256" in record:
                return str(record["spec_sha256"])
        return None

    # -- execution --------------------------------------------------------

    def run(
        self,
        runtime: Any,
        sink: FrameSink,
        *,
        warmup_ticks: int,
        frame_timeout_seconds: float = 600.0,
        on_unit: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        """Capture every unit that is not already COMPLETE, in frozen order."""
        self._publish(
            stage_status="RUNNING", message=f"{self.stage} campaign started"
        )
        previous_material: str | None = None
        skipped: list[str] = []
        captured: list[str] = []

        for spec in self.specs:
            decision = self.resume_decision(spec)
            if decision["action"] == "SKIP":
                skipped.append(spec.capture_unit_id)
                if on_unit:
                    on_unit(spec.capture_unit_id, "SKIPPED_COMPLETE")
                self._publish(
                    stage_status="RUNNING",
                    message=f"{spec.capture_unit_id} already complete; skipped",
                )
                continue

            self._publish(
                stage_status="RUNNING",
                message=f"{spec.capture_unit_id} {decision['action']} "
                f"({decision['reason']})",
                current_unit=spec.capture_unit_id,
            )
            unit_dir = capture_unit_directory(self.output_root, spec)

            if decision["action"] in ("CAPTURE", "RECAPTURE"):
                if unit_dir.exists():
                    shutil.rmtree(unit_dir)
                self.ledger.append(
                    spec.capture_unit_id,
                    "PLANNED",
                    spec_sha256=spec.spec_sha256,
                    retry_same_spec=decision["action"] == "RECAPTURE",
                    reason=decision["reason"],
                    authority_sha256=self.binding["AUTHORITY_SHA256"],
                    source_closure=self.source_closure,
                )
                self.ledger.append(
                    spec.capture_unit_id, "RUNNING", spec_sha256=spec.spec_sha256
                )
                witness_episode_id = self._allocate_witness_episodes(sink)
                result = capture_a5_unit(
                    runtime,
                    sink,
                    spec,
                    witness_episode_id=witness_episode_id,
                    warmup_ticks=warmup_ticks,
                    frame_timeout_seconds=frame_timeout_seconds,
                    previous_wall_block_id=previous_material,
                    server_episode_root=self.server_episode_root,
                    server_run_root=self.server_run_root,
                )
                assemble_unit_inventory(
                    sink.episode_dir(spec.episode_id),
                    self._server_episode_dir(spec),
                    unit_dir,
                    spec,
                    result["frame_records"],
                    rve_condition_score=self.rve_condition_scores.get(
                        spec.condition.condition_id.value
                    ),
                    liveness_witness=result.get("liveness_witness"),
                    liveness_probes=result.get("liveness_probes") or [],
                )
                self.ledger.append(
                    spec.capture_unit_id, "CAPTURED", spec_sha256=spec.spec_sha256
                )
                captured.append(spec.capture_unit_id)

            # FINISH and the freshly captured path converge here: validate, then
            # bank, then mark complete. Re-validating a resumed unit is the point
            # -- a directory on disk is not evidence until its receipts pass.
            validate_capture_unit(unit_dir, spec)
            self.ledger.append(
                spec.capture_unit_id, "VALIDATED", spec_sha256=spec.spec_sha256
            )
            receipt = unit_durable_receipt(unit_dir, spec)
            self.ledger.append(
                spec.capture_unit_id,
                "DURABLE",
                spec_sha256=spec.spec_sha256,
                file_count=receipt["file_count"],
                total_bytes=receipt["total_bytes"],
            )
            self.ledger.append(
                spec.capture_unit_id,
                "COMPLETE",
                spec_sha256=spec.spec_sha256,
                authority_sha256=self.binding["AUTHORITY_SHA256"],
                source_closure=self.source_closure,
            )
            previous_material = spec.condition.wall_block_id
            if on_unit:
                on_unit(spec.capture_unit_id, "COMPLETE")
            self._publish(
                stage_status="RUNNING",
                message=f"{spec.capture_unit_id} complete",
                current_unit=None,
            )

        inventory = self.inventory()
        self._publish(
            stage_status="COMPLETE" if inventory["complete"] else "RUNNING",
            message=f"{inventory['completed_units']}/{inventory['total_units']} units complete",
            validator_status="PASS" if inventory["complete"] else "NOT_RUN",
        )
        return {
            "skipped": skipped,
            "captured": captured,
            "inventory": inventory,
        }

    # -- inventory --------------------------------------------------------

    def inventory(self) -> dict[str, Any]:
        """Reconstruct what is actually banked, independently of the run loop."""
        complete = self.ledger.complete_units()
        units = []
        duplicates: list[str] = []
        seen: set[str] = set()
        for spec in self.specs:
            unit_dir = capture_unit_directory(self.output_root, spec)
            durable = unit_dir / "durable_receipt.json"
            if spec.capture_unit_id in seen:
                duplicates.append(spec.capture_unit_id)
            seen.add(spec.capture_unit_id)
            units.append(
                {
                    "capture_unit_id": spec.capture_unit_id,
                    "identity": spec.identity,
                    "condition_id": spec.condition.condition_id.value,
                    "wall_block_id": spec.condition.wall_block_id,
                    "episode_id": spec.episode_id,
                    "ledger_state": self.ledger.last_state(spec.capture_unit_id),
                    "complete": spec.capture_unit_id in complete,
                    "durable_receipt": durable.is_file(),
                    "target_rows": TARGET_ROWS_PER_CAPTURE,
                    "spec_sha256": spec.spec_sha256,
                }
            )
        completed = [unit for unit in units if unit["complete"] and unit["durable_receipt"]]
        # An accepted unit appearing twice in the ledger's COMPLETE set would be a
        # duplicate acceptance; the ledger is a set keyed by unit id, so the only
        # way to get one is a duplicated plan entry, which is what this counts.
        accepted_ledger_completions = [
            record["unit_id"]
            for record in self.ledger.records
            if record["state"] == "COMPLETE"
        ]
        duplicate_accepted = sorted(
            {
                unit_id
                for unit_id in accepted_ledger_completions
                if accepted_ledger_completions.count(unit_id) > 1
            }
        )
        return {
            "total_units": len(self.specs),
            "completed_units": len(completed),
            "complete": len(completed) == len(self.specs),
            "units": units,
            "duplicate_plan_entries": duplicates,
            "duplicate_accepted_units": duplicate_accepted,
            "identities": sorted({spec.identity for spec in self.specs}),
            "conditions": sorted(
                {spec.condition.condition_id.value for spec in self.specs}
            ),
            "target_rows_total": len(completed) * TARGET_ROWS_PER_CAPTURE,
            "production_identities_used": bool(
                {spec.identity for spec in self.specs} & set(PRODUCTION_IDENTITY_IDS)
            ),
        }
