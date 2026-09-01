"""A7 — the production capture campaign (authority 8.1-8.3, lifecycle A7).

125 units: 25 production identities x 5 conditions, in the frozen Latin order,
22,500 frames, 2,375 target rows.

**This module owns admission and sentinels. It does not own capture.** The unit
loop -- ledger-driven resume, same-spec-only retry, validate then bank then
COMPLETE -- is the one A5 qualified over the P1 pilot, and authority 8.3 gives
A5 and A7 the *same* unit state machine. Growing a second capture engine here
would mean shipping resume semantics that nothing has ever demonstrated against
a real apparatus, so :class:`ProductionCampaign` extends the A5 campaign rather
than replacing it. What A7 adds is what A7 actually has that A5 does not:

* an **admission gate** that consumes a real, passed, current P2 freeze;
* the **production roster**, with pilot identities refused rather than admitted;
* **10 sentinel checks**, before and after each of the five condition batches.

Admission is the whole point of the stage boundary. A7 spends the 25 production
identities, authority 2.1 forbids identity replacement, and a batch captured
under a stale freeze permanently shrinks the cohort rather than merely wasting
an afternoon. Every refusal below is therefore terminal, and none of them can be
overridden by an operator flag: there is no ``--force``, and the superseded P2
that froze a placeholder bootstrap seed cannot authorize anything, because its
authority binding no longer matches the live one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from mineocclude.experiment_iii.a5_capture import CaptureUnitSpec
from mineocclude.experiment_iii.a5_pilot import PilotCampaign
from mineocclude.experiment_iii.authority import (
    FRAMES_PER_CAPTURE,
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_COUNT,
    PRODUCTION_IDENTITY_IDS,
    TARGET_ROWS_PER_CAPTURE,
    verify_authority_binding,
)
from mineocclude.experiment_iii.capture_schedule import (
    CaptureUnit,
    build_capture_schedule,
    condition_batches,
    validate_capture_order,
)
from mineocclude.experiment_iii.conditions import build_condition_map
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.p2_freeze import (
    P2_FREEZE_SCHEMA_VERSION,
    p2_freeze_passed,
    verify_p2_freeze_package,
)
from mineocclude.experiment_iii.schema import ConditionId
from mineocclude.experiment_iii.source_closure import source_closure

__all__ = [
    "EXPECTED_CAPTURES",
    "EXPECTED_FRAMES",
    "EXPECTED_TARGET_ROWS",
    "ProductionCampaign",
    "admit_production",
    "build_production_unit_spec",
    "production_specs",
    "verify_no_pilot_identity",
]

STAGE = "A7"
NEXT_STAGE = "A8"

EXPECTED_CAPTURES = 125
EXPECTED_FRAMES = EXPECTED_CAPTURES * FRAMES_PER_CAPTURE
EXPECTED_TARGET_ROWS = EXPECTED_CAPTURES * TARGET_ROWS_PER_CAPTURE


# --------------------------------------------------------------------------
# Admission
# --------------------------------------------------------------------------


def admit_production(
    p2_path: Path,
    *,
    capture_host_receipt: Path | None = None,
    expected_source_closure: str | None = None,
) -> dict[str, Any]:
    """Decide whether A7 may spend a production identity. Fails closed.

    Every check below has a specific way it has already been got wrong somewhere
    in this program, which is why each is separate and none is inferred from
    another:

    * a package that is not a P2 at all (wrong schema);
    * a package whose own recorded digest does not match its contents;
    * a package that did not pass, or that passed under a different authority --
      the superseded ``a2734b31`` freeze is exactly this case, and it must not
      authorize anything after Amendment 5;
    * a package bound to a different source closure than the code about to run;
    * ``PRODUCTION_AUTHORIZED`` or ``MODEL_INFERENCE_AUTHORIZED`` not true;
    * ``next_authorized_state`` not ``A7`` -- a package that has already been
      spent, or that authorizes some other stage;
    * production captures already executed against this freeze;
    * a capture-host A3 receipt that is absent, failed, or does not authorize A7.

    ``P0``'s own ``PRODUCTION_AUTHORIZED`` field is never consulted. Only A6 may
    emit production authorization, and only from a P2 exit.
    """
    path = Path(p2_path)
    if not path.is_file():
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            f"no P2 freeze package at {path}; A7 entry requires A6 PASS",
        )
    package = json.loads(path.read_text(encoding="utf-8"))

    if package.get("schema_version") != P2_FREEZE_SCHEMA_VERSION:
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            f"{path} is not a P2 freeze package "
            f"(schema {package.get('schema_version')!r})",
        )

    findings = verify_p2_freeze_package(package)
    if findings.get("findings"):
        raise ExperimentIIIError(
            "P2_BINDING_MISMATCH",
            f"the P2 package at {path} does not re-verify: {findings['findings']}",
        )
    if not p2_freeze_passed(package):
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            f"the P2 package at {path} is not an A6 exit "
            f"(P2_RESULT={package.get('P2_RESULT')!r})",
        )

    current = verify_authority_binding()
    bound = package.get("authority_binding") or {}
    for key in ("AUTHORITY_SHA256", "MACHINE_AUTHORITY_SHA256", "PHASE0_DESIGN_SHA256"):
        if bound.get(key) != current[key]:
            raise ExperimentIIIError(
                "PROVENANCE_AUTHORITY_DRIFT",
                f"the P2 package at {path} was frozen under {key}="
                f"{bound.get(key)} and this run is bound to {current[key]}; a "
                f"superseded freeze may never authorize production",
            )

    live_closure = source_closure()["source_closure_sha256"]
    expected = expected_source_closure or live_closure
    frozen_closure = (
        (package.get("bindings") or {})
        .get("IMPLEMENTATION", {})
        .get("source_closure_sha256")
    ) or package.get("source_closure_sha256")
    if frozen_closure is not None and frozen_closure != expected:
        raise ExperimentIIIError(
            "SOURCE_CLOSURE_DRIFT",
            f"the P2 package binds source closure {frozen_closure} and this run "
            f"is {expected}; production must run the code that was frozen",
        )
    if live_closure != expected:
        raise ExperimentIIIError(
            "SOURCE_CLOSURE_DRIFT",
            f"the working tree closure {live_closure} is not the expected "
            f"{expected}",
        )

    if package.get("PRODUCTION_AUTHORIZED") is not True:
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            "PRODUCTION_AUTHORIZED is not true in the P2 freeze",
        )
    if package.get("MODEL_INFERENCE_AUTHORIZED") is not True:
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            "MODEL_INFERENCE_AUTHORIZED is not true in the P2 freeze",
        )
    if package.get("next_authorized_state") != STAGE:
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            f"the P2 freeze authorizes {package.get('next_authorized_state')!r}, "
            f"not {STAGE}",
        )
    executed = int(package.get("production_captures_executed") or 0)
    if executed:
        raise ExperimentIIIError(
            "P2_BINDING_MISMATCH",
            f"the P2 freeze records {executed} production captures already "
            f"executed; it is not a fresh A7 authorization",
        )

    host = _admit_capture_host(capture_host_receipt)

    return {
        "admitted": True,
        "stage": STAGE,
        "p2_path": path.as_posix(),
        "p2_package_sha256": package.get("package_sha256"),
        "authority_binding": current,
        "source_closure_sha256": live_closure,
        "capture_host_receipt": host,
        "production_authorized_by": "A6_P2_FREEZE_EXIT",
        "p0_production_authorized_field_consulted": False,
    }


def _admit_capture_host(receipt_path: Path | None) -> dict[str, Any]:
    """A3 PASS on the capture host, for the capture stages, or refuse."""
    if receipt_path is None:
        raise ExperimentIIIError(
            "ENV_DISPLAY_UNAVAILABLE",
            "A7 entry requires an A3 capture-host receipt; none was supplied",
        )
    path = Path(receipt_path)
    if not path.is_file():
        raise ExperimentIIIError(
            "ENV_DISPLAY_UNAVAILABLE", f"no A3 capture-host receipt at {path}"
        )
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("stage") != "A3" or receipt.get("passed") is not True:
        raise ExperimentIIIError(
            "ENV_DISPLAY_UNAVAILABLE",
            f"{path} is not a passed A3 receipt",
        )
    if STAGE not in (receipt.get("authorized_stages") or ()):
        raise ExperimentIIIError(
            "ENV_DISPLAY_UNAVAILABLE",
            f"{path} authorizes {receipt.get('authorized_stages')}, not {STAGE}; "
            f"a host that never established a renderer may not capture",
        )
    current = verify_authority_binding()
    bound = receipt.get("authority_binding") or {}
    if bound.get("AUTHORITY_SHA256") != current["AUTHORITY_SHA256"]:
        raise ExperimentIIIError(
            "PROVENANCE_AUTHORITY_DRIFT",
            f"{path} was produced under authority {bound.get('AUTHORITY_SHA256')} "
            f"and this run is bound to {current['AUTHORITY_SHA256']}",
        )
    return {
        "path": path.as_posix(),
        "passed": True,
        "authorized_stages": list(receipt.get("authorized_stages") or ()),
        "host_role": receipt.get("host_role"),
    }


# --------------------------------------------------------------------------
# Roster and specs
# --------------------------------------------------------------------------


def verify_no_pilot_identity(specs: Sequence[CaptureUnitSpec]) -> None:
    """Refuse a pilot identity in the production cohort (A8 contamination)."""
    named = {spec.identity for spec in specs}
    pilots = sorted(named & set(PILOT_IDENTITY_IDS))
    if pilots:
        raise ExperimentIIIError(
            "COHORT_PILOT_CONTAMINATION",
            f"the production schedule names pilot identities {pilots}; the pilot "
            f"is engineering evidence and never enters the production cohort",
        )
    unknown = sorted(named - set(PRODUCTION_IDENTITY_IDS))
    if unknown:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"the production schedule names non-production identities {unknown}",
        )
    if len(named) != PRODUCTION_IDENTITY_COUNT:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"the production schedule covers {len(named)} identities, authority "
            f"2.1 freezes {PRODUCTION_IDENTITY_COUNT}",
        )


def build_production_unit_spec(
    unit: CaptureUnit,
    identity_row: Mapping[str, Any],
    condition: Any,
) -> CaptureUnitSpec:
    """Bind one scheduled production unit to its identity manifest row.

    Deliberately not ``a5_capture.build_unit_spec``: that function refuses any
    identity outside ``PILOT_EPISODE_IDS``, which is correct for A5 and exactly
    wrong here. The episode id comes from the frozen manifest rather than a
    literal table, because production episode ids are cohort data.
    """
    identity = str(identity_row["identity"])
    if unit.identity != identity:
        raise ExperimentIIIError(
            "PROVENANCE_BINDING_MISSING",
            f"identity manifest row is {identity!r}, scheduled unit is "
            f"{unit.identity!r}",
        )
    if int(identity_row["episode_id"]) != unit.episode_id:
        raise ExperimentIIIError(
            "PROVENANCE_BINDING_MISMATCH",
            f"{identity} carries episode {identity_row['episode_id']} in the "
            f"manifest and {unit.episode_id} in the schedule",
        )
    if unit.wall_block_id != condition.wall_block_id:
        raise ExperimentIIIError(
            "WALL_MATERIAL_MISMATCH",
            f"{unit.capture_unit_id} schedules {unit.wall_block_id!r} but the "
            f"P0-bound condition map resolves {condition.wall_block_id!r}",
        )
    rows = tuple(int(index) for index in identity_row["target_model_frame_indices"])
    if len(rows) != TARGET_ROWS_PER_CAPTURE:
        raise ExperimentIIIError(
            "TARGET_ROW_MISMATCH",
            f"{identity} names {len(rows)} target rows, authority freezes "
            f"{TARGET_ROWS_PER_CAPTURE}",
        )
    return CaptureUnitSpec(
        capture_unit_id=unit.capture_unit_id,
        identity=identity,
        condition=condition,
        episode_id=unit.episode_id,
        seed=int(identity_row["seed"]),
        direction=str(identity_row["direction"]),
        start_world_x=float(identity_row["start_world_x"]),
        motion_noise_q=float(identity_row["motion_noise_q"]),
        speed_blocks_per_second=float(identity_row["speed_blocks_per_second"]),
        dt_seconds=float(identity_row["dt_seconds"]),
        frames=int(identity_row["frames"]),
        path_sha256=str(identity_row["path_sha256"]),
        noise_schedule_sha256=str(identity_row["noise_schedule_sha256"]),
        target_model_frame_indices=rows,
        identity_spec_hash=str(identity_row["spec_hash"]),
    )


def production_specs(
    identity_rows: Sequence[Mapping[str, Any]],
    ladder: Mapping[str, Any],
) -> tuple[list[CaptureUnitSpec], list[CaptureUnit], dict[str, Any]]:
    """The 125 executable unit specs in frozen Latin order, with their report."""
    conditions = build_condition_map(ladder)
    schedule = build_capture_schedule(identity_rows, conditions)
    report = validate_capture_order(schedule)
    by_identity = {str(row["identity"]): row for row in identity_rows}
    specs = [
        build_production_unit_spec(
            unit, by_identity[unit.identity], conditions[ConditionId(unit.condition_id)]
        )
        for unit in schedule
    ]
    verify_no_pilot_identity(specs)
    if len(specs) != EXPECTED_CAPTURES:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"resolved {len(specs)} production units, authority 8.1 freezes "
            f"{EXPECTED_CAPTURES}",
        )
    return specs, schedule, report


# --------------------------------------------------------------------------
# Campaign
# --------------------------------------------------------------------------


class ProductionCampaign(PilotCampaign):
    """The A5 unit loop, over the production roster, with batch sentinels."""

    def __init__(self, specs: Sequence[CaptureUnitSpec], **kwargs: Any) -> None:
        kwargs.setdefault("stage", STAGE)
        kwargs.setdefault("next_stage", NEXT_STAGE)
        verify_no_pilot_identity(specs)
        super().__init__(specs, **kwargs)

    def batch_boundaries(self, schedule: Sequence[CaptureUnit]) -> list[dict[str, Any]]:
        """The 10 sentinel points: before and after each of the 5 batches.

        Authority 8.1 expects "10 sentinel checks (before and after each of 5
        condition batches)". They are enumerated from the schedule rather than
        assumed, so a schedule that somehow held a different number of batches
        produces a different count here and fails its own expected-count check
        instead of silently running five.
        """
        batches = condition_batches(schedule)
        boundaries: list[dict[str, Any]] = []
        for batch in batches:
            for position in ("BEFORE", "AFTER"):
                boundaries.append(
                    {
                        "position": position,
                        "block": batch.get("block"),
                        "period": batch.get("period"),
                        "condition_id": batch.get("condition_id"),
                    }
                )
        return boundaries

    def expected_counts(self) -> dict[str, int]:
        return {
            "captures": EXPECTED_CAPTURES,
            "frames": EXPECTED_FRAMES,
            "target_rows": EXPECTED_TARGET_ROWS,
            "identities": PRODUCTION_IDENTITY_COUNT,
            "frames_per_capture": FRAMES_PER_CAPTURE,
            "target_rows_per_capture": TARGET_ROWS_PER_CAPTURE,
        }
