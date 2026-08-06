"""Pre-outcome U4 control manifest (Person D Step 7.1).

Execution manual Step 7.1 requires a *frozen, pre-outcome* control
manifest with stable identities for the held-out event, rollout seed,
alpha=0, the signed primary doses, seeded norm-matched random directions,
orthogonal directions where the frozen contract requires them, the wrong
layer, the wrong timestep, the control type, the direction version, the
target layer and timestep, the clip ID, the intended comparison pair key,
the expected count, and the owner and status -- plus unique clip IDs,
unique pair keys, no outcome-derived selection field, no post-rollout
control addition, planned-versus-available reconciliation, an immutable
version and checksum, and machine-readable A-to-D and D-to-A/E handoffs.

Persons A and E consume the clip IDs and pair keys this module produces.
That is why the builder is deterministic and total: given the same
contract inputs it emits byte-identical IDs, so A can generate against
them and E can measure against them without any further coordination.

Two guardrails are structural rather than procedural:

* **Pre-outcome.** :data:`FORBIDDEN_OUTCOME_FIELDS` names every field
  whose presence would mean a control was chosen after looking at a
  result. The validator rejects the manifest outright if any appears, at
  any nesting depth.
* **Frozen after publication.** ``freeze_control_manifest`` stamps a
  checksum over the full row set. :func:`assert_no_post_rollout_addition`
  compares a later manifest against the frozen one and rejects any added,
  removed, or altered row -- a control matrix that grew after rollouts
  began is not a control matrix.

Person D does not fit the intervention direction (Person B), inject it
(Person A), or measure the resulting clips (Person E). It defines what
must exist, names every row, and verifies completeness.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

SCHEMA_ID = "person-d-u4-control-manifest-v0-1"
SCHEMA_VERSION = "1.0"

#: Any of these appearing anywhere in a manifest means a control row was
#: selected using an outcome. A pre-outcome manifest cannot contain them.
FORBIDDEN_OUTCOME_FIELDS: frozenset[str] = frozenset(
    {
        "displacement_blocks",
        "measured_displacement",
        "ssim",
        "masked_ssim",
        "persisted",
        "persistence",
        "reappearance_frame_idx",
        "effect_size",
        "p_value",
        "outcome",
        "measured",
        "observed_displacement",
        "selected_by_outcome",
        "rank_by_effect",
    }
)

#: MineWorld's frozen configuration bounds, from the B-to-A intervention
#: request contract (docs/contracts/intervention_request_v1.md).
FROZEN_LAYER_RANGE = (0, 19)
FROZEN_TIMESTEP_RANGE = (0, 15)
FROZEN_HOOK_SITE = "decoder_layer_output_residual_stream"

MANIFEST_STATUSES: tuple[str, ...] = ("draft", "frozen", "superseded")
ROW_STATUSES: tuple[str, ...] = (
    "planned",
    "generation_requested",
    "generated",
    "generation_failed",
    "excluded",
)


class ControlType(str, Enum):
    """Every condition the frozen U4 control matrix must cover.

    ``PRIMARY_SIGNED_DOSE`` is included so the primary condition and its
    controls are named in one place and can be checked for paired
    event/seed coverage without a second source of truth.
    """

    PRIMARY_SIGNED_DOSE = "primary_signed_dose"
    ALPHA_ZERO = "alpha_zero"
    RANDOM_DIRECTION = "random_direction"
    ORTHOGONAL_DIRECTION = "orthogonal_direction"
    WRONG_LAYER = "wrong_layer"
    WRONG_TIMESTEP = "wrong_timestep"


class ControlManifestError(ValueError):
    """Raised when a control manifest cannot be built or validated honestly."""


@dataclass(frozen=True)
class HeldOutEvent:
    """One held-out event the control matrix is built over.

    Identity only -- no outcome field is permitted on this type, and the
    events must come from Person B's held-out partition, never from a set
    Person D selected.
    """

    event_id: str
    trajectory_id: str
    layout_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("event_id", self.event_id),
            ("trajectory_id", self.trajectory_id),
            ("layout_id", self.layout_id),
        ):
            if not value:
                raise ControlManifestError(f"held-out event requires a non-empty {name}")


@dataclass(frozen=True)
class DoseSpec:
    """One signed primary dose, copied from B's frozen alpha table."""

    dose_id: str
    alpha_requested: float
    alpha_applied: float
    cap_reduced: bool

    def __post_init__(self) -> None:
        if not self.dose_id:
            raise ControlManifestError("dose_id must be non-empty")
        if self.alpha_requested == 0.0:
            raise ControlManifestError(
                f"dose {self.dose_id!r} has alpha_requested=0; the zero-dose "
                "condition is the alpha_zero control, not a primary dose"
            )
        if (self.alpha_requested > 0) != (self.alpha_applied > 0):
            raise ControlManifestError(
                f"dose {self.dose_id!r} reverses sign between requested "
                f"{self.alpha_requested} and applied {self.alpha_applied}; cap "
                "application may reduce magnitude but never reverse direction"
            )
        if self.cap_reduced and abs(self.alpha_applied) >= abs(self.alpha_requested):
            raise ControlManifestError(
                f"dose {self.dose_id!r} flags cap_reduced but did not reduce "
                "the applied magnitude"
            )
        if not self.cap_reduced and self.alpha_requested != self.alpha_applied:
            raise ControlManifestError(
                f"dose {self.dose_id!r} changed alpha without the cap_reduced "
                "flag; an unflagged alpha change is rejected upstream too"
            )


@dataclass(frozen=True)
class DirectionRef:
    """A direction's stable identity. Person D never derives the values."""

    direction_id: str
    direction_version: str
    direction_sha256: str
    space: str = "raw_activation"
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.direction_id or not self.direction_version:
            raise ControlManifestError(
                "a direction reference requires both an id and a version"
            )
        if len(self.direction_sha256) != 64:
            raise ControlManifestError(
                f"direction {self.direction_id!r} sha256 is not a SHA-256 digest"
            )
        if self.space != "raw_activation":
            raise ControlManifestError(
                f"direction {self.direction_id!r} declares space {self.space!r}; "
                "the frozen contract requires raw_activation space"
            )


@dataclass(frozen=True)
class ControlManifestRow:
    """One planned control clip: everything A needs to generate it."""

    clip_id: str
    pair_key: str
    control_type: str
    event_id: str
    trajectory_id: str
    layout_id: str
    rollout_seed: int
    alpha_requested: float
    alpha_applied: float
    cap_reduced: bool
    dose_id: Optional[str]
    direction_id: str
    direction_version: str
    direction_sha256: str
    direction_seed: Optional[int]
    target_layer_idx: int
    target_timestep_idx: int
    hook_site: str
    owner_role: str
    status: str

    def __post_init__(self) -> None:
        if self.status not in ROW_STATUSES:
            raise ControlManifestError(
                f"clip {self.clip_id!r} has unknown status {self.status!r}"
            )
        if self.control_type not in {member.value for member in ControlType}:
            raise ControlManifestError(
                f"clip {self.clip_id!r} has unknown control_type "
                f"{self.control_type!r}"
            )
        low, high = FROZEN_LAYER_RANGE
        if not low <= self.target_layer_idx <= high:
            raise ControlManifestError(
                f"clip {self.clip_id!r} targets layer {self.target_layer_idx}, "
                f"outside the frozen range {FROZEN_LAYER_RANGE}"
            )
        low, high = FROZEN_TIMESTEP_RANGE
        if not low <= self.target_timestep_idx <= high:
            raise ControlManifestError(
                f"clip {self.clip_id!r} targets timestep "
                f"{self.target_timestep_idx}, outside the frozen range "
                f"{FROZEN_TIMESTEP_RANGE}"
            )
        if self.control_type == ControlType.ALPHA_ZERO.value and (
            self.alpha_requested != 0.0 or self.alpha_applied != 0.0
        ):
            raise ControlManifestError(
                f"alpha_zero clip {self.clip_id!r} carries a nonzero alpha"
            )


def make_clip_id(
    *,
    event_id: str,
    rollout_seed: int,
    control_type: str,
    dose_id: Optional[str],
    target_layer_idx: int,
    target_timestep_idx: int,
) -> str:
    """Build one clip's stable ID from its identity fields only.

    Deterministic and collision-free by construction: two clips can share
    an ID only if every identity field matches, in which case they are the
    same clip. Nothing here reads a filename, a path, or a row position.
    """

    dose_part = dose_id or "none"
    return (
        f"{event_id}|seed{rollout_seed}|{control_type}|dose{dose_part}"
        f"|L{target_layer_idx}|T{target_timestep_idx}"
    )


def make_pair_key(*, event_id: str, rollout_seed: int, dose_id: Optional[str]) -> str:
    """Build the intended comparison pair key.

    Every clip that must be compared against the same alpha-zero baseline
    shares this key: the baseline match rule is "exact event_id + seed"
    (Person E's measurement contract), and the dose distinguishes which
    signed comparison a pushed clip belongs to.
    """

    return f"{event_id}|seed{rollout_seed}|dose{dose_id or 'none'}"


def build_control_manifest_rows(
    *,
    held_out_events: Sequence[HeldOutEvent],
    rollout_seeds: Sequence[int],
    doses: Sequence[DoseSpec],
    primary_direction: DirectionRef,
    random_directions: Sequence[DirectionRef],
    orthogonal_directions: Sequence[DirectionRef] = (),
    target_layer_idx: int,
    target_timestep_idx: int,
    wrong_layer_idx: int,
    wrong_timestep_idx: int,
    require_orthogonal_controls: bool = True,
    hook_site: str = FROZEN_HOOK_SITE,
    owner_role: str = "person_a",
) -> list[ControlManifestRow]:
    """Build every planned control row, deterministically and totally.

    For each (event, seed) the matrix contains: one alpha-zero clip; one
    primary signed-dose clip per dose; one norm-matched random-direction
    clip per supplied random direction per dose; one orthogonal-direction
    clip per supplied orthogonal direction per dose (when required); one
    wrong-layer clip per dose; and one wrong-timestep clip per dose.
    """

    if not held_out_events:
        raise ControlManifestError("at least one held-out event is required")
    if not rollout_seeds:
        raise ControlManifestError("at least one rollout seed is required")
    if not doses:
        raise ControlManifestError("at least one signed primary dose is required")
    if not random_directions:
        raise ControlManifestError(
            "at least one seeded norm-matched random direction is required"
        )
    if require_orthogonal_controls and not orthogonal_directions:
        raise ControlManifestError(
            "the frozen contract requires orthogonal-direction controls, but "
            "none were supplied; pass require_orthogonal_controls=False only "
            "when the contract itself does not require them"
        )
    if wrong_layer_idx == target_layer_idx:
        raise ControlManifestError(
            "the wrong-layer control must target a different layer than the "
            "primary intervention"
        )
    if wrong_timestep_idx == target_timestep_idx:
        raise ControlManifestError(
            "the wrong-timestep control must target a different timestep than "
            "the primary intervention"
        )
    for direction in random_directions:
        if direction.seed is None:
            raise ControlManifestError(
                f"random direction {direction.direction_id!r} has no seed; a "
                "'seeded random direction' with no recorded seed is not "
                "reproducible"
            )

    event_ids = [event.event_id for event in held_out_events]
    if len(set(event_ids)) != len(event_ids):
        raise ControlManifestError("held-out event IDs must be unique")
    if len(set(rollout_seeds)) != len(rollout_seeds):
        raise ControlManifestError("rollout seeds must be unique")
    dose_ids = [dose.dose_id for dose in doses]
    if len(set(dose_ids)) != len(dose_ids):
        raise ControlManifestError("dose IDs must be unique")

    rows: list[ControlManifestRow] = []

    def emit(
        *,
        event: HeldOutEvent,
        seed: int,
        control_type: ControlType,
        dose: Optional[DoseSpec],
        direction: DirectionRef,
        layer_idx: int,
        timestep_idx: int,
    ) -> None:
        dose_id = dose.dose_id if dose is not None else None
        rows.append(
            ControlManifestRow(
                clip_id=make_clip_id(
                    event_id=event.event_id,
                    rollout_seed=seed,
                    control_type=control_type.value,
                    dose_id=(
                        f"{dose_id}+{direction.direction_id}"
                        if control_type
                        in (
                            ControlType.RANDOM_DIRECTION,
                            ControlType.ORTHOGONAL_DIRECTION,
                        )
                        else dose_id
                    ),
                    target_layer_idx=layer_idx,
                    target_timestep_idx=timestep_idx,
                ),
                pair_key=make_pair_key(
                    event_id=event.event_id, rollout_seed=seed, dose_id=dose_id
                ),
                control_type=control_type.value,
                event_id=event.event_id,
                trajectory_id=event.trajectory_id,
                layout_id=event.layout_id,
                rollout_seed=seed,
                alpha_requested=dose.alpha_requested if dose is not None else 0.0,
                alpha_applied=dose.alpha_applied if dose is not None else 0.0,
                cap_reduced=dose.cap_reduced if dose is not None else False,
                dose_id=dose_id,
                direction_id=direction.direction_id,
                direction_version=direction.direction_version,
                direction_sha256=direction.direction_sha256,
                direction_seed=direction.seed,
                target_layer_idx=layer_idx,
                target_timestep_idx=timestep_idx,
                hook_site=hook_site,
                owner_role=owner_role,
                status="planned",
            )
        )

    for event in sorted(held_out_events, key=lambda e: e.event_id):
        for seed in sorted(rollout_seeds):
            emit(
                event=event,
                seed=seed,
                control_type=ControlType.ALPHA_ZERO,
                dose=None,
                direction=primary_direction,
                layer_idx=target_layer_idx,
                timestep_idx=target_timestep_idx,
            )
            for dose in sorted(doses, key=lambda d: d.dose_id):
                emit(
                    event=event,
                    seed=seed,
                    control_type=ControlType.PRIMARY_SIGNED_DOSE,
                    dose=dose,
                    direction=primary_direction,
                    layer_idx=target_layer_idx,
                    timestep_idx=target_timestep_idx,
                )
                for direction in sorted(random_directions, key=lambda d: d.direction_id):
                    emit(
                        event=event,
                        seed=seed,
                        control_type=ControlType.RANDOM_DIRECTION,
                        dose=dose,
                        direction=direction,
                        layer_idx=target_layer_idx,
                        timestep_idx=target_timestep_idx,
                    )
                for direction in sorted(
                    orthogonal_directions, key=lambda d: d.direction_id
                ):
                    emit(
                        event=event,
                        seed=seed,
                        control_type=ControlType.ORTHOGONAL_DIRECTION,
                        dose=dose,
                        direction=direction,
                        layer_idx=target_layer_idx,
                        timestep_idx=target_timestep_idx,
                    )
                emit(
                    event=event,
                    seed=seed,
                    control_type=ControlType.WRONG_LAYER,
                    dose=dose,
                    direction=primary_direction,
                    layer_idx=wrong_layer_idx,
                    timestep_idx=target_timestep_idx,
                )
                emit(
                    event=event,
                    seed=seed,
                    control_type=ControlType.WRONG_TIMESTEP,
                    dose=dose,
                    direction=primary_direction,
                    layer_idx=target_layer_idx,
                    timestep_idx=wrong_timestep_idx,
                )

    return rows


def expected_row_count(
    *,
    event_count: int,
    seed_count: int,
    dose_count: int,
    random_direction_count: int,
    orthogonal_direction_count: int,
) -> int:
    """The exact number of rows :func:`build_control_manifest_rows` emits.

    Stated independently of the builder so the two can disagree loudly
    rather than a silent omission passing unnoticed.
    """

    per_dose = 1 + random_direction_count + orthogonal_direction_count + 2
    return event_count * seed_count * (1 + dose_count * per_dose)


def build_control_manifest(
    *,
    manifest_id: str,
    manifest_version: str,
    rows: Sequence[ControlManifestRow],
    held_out_events: Sequence[HeldOutEvent],
    rollout_seeds: Sequence[int],
    doses: Sequence[DoseSpec],
    primary_direction: DirectionRef,
    random_directions: Sequence[DirectionRef],
    orthogonal_directions: Sequence[DirectionRef] = (),
    target_layer_idx: int,
    target_timestep_idx: int,
    wrong_layer_idx: int,
    wrong_timestep_idx: int,
    source_authorities: Mapping[str, Any],
    evidence_kind: str = "synthetic",
    status: str = "draft",
) -> dict[str, Any]:
    """Assemble the machine-readable control-manifest document."""

    if evidence_kind not in ("real", "synthetic"):
        raise ControlManifestError("evidence_kind must be 'real' or 'synthetic'")
    if status not in MANIFEST_STATUSES:
        raise ControlManifestError(f"unknown manifest status {status!r}")

    expected = expected_row_count(
        event_count=len(held_out_events),
        seed_count=len(rollout_seeds),
        dose_count=len(doses),
        random_direction_count=len(random_directions),
        orthogonal_direction_count=len(orthogonal_directions),
    )

    document: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "manifest_id": manifest_id,
        "manifest_version": manifest_version,
        "status": status,
        "evidence_kind": evidence_kind,
        "pre_outcome": True,
        "outcome_derived_selection": False,
        "hook_site": FROZEN_HOOK_SITE,
        "target_layer_idx": target_layer_idx,
        "target_timestep_idx": target_timestep_idx,
        "wrong_layer_idx": wrong_layer_idx,
        "wrong_timestep_idx": wrong_timestep_idx,
        "primary_direction": _direction_to_dict(primary_direction),
        "random_directions": tuple(
            _direction_to_dict(d)
            for d in sorted(random_directions, key=lambda d: d.direction_id)
        ),
        "orthogonal_directions": tuple(
            _direction_to_dict(d)
            for d in sorted(orthogonal_directions, key=lambda d: d.direction_id)
        ),
        "held_out_events": tuple(
            {
                "event_id": event.event_id,
                "trajectory_id": event.trajectory_id,
                "layout_id": event.layout_id,
            }
            for event in sorted(held_out_events, key=lambda e: e.event_id)
        ),
        "rollout_seeds": tuple(sorted(rollout_seeds)),
        "doses": tuple(
            {
                "dose_id": dose.dose_id,
                "alpha_requested": dose.alpha_requested,
                "alpha_applied": dose.alpha_applied,
                "cap_reduced": dose.cap_reduced,
            }
            for dose in sorted(doses, key=lambda d: d.dose_id)
        ),
        "expected_clip_count": expected,
        "planned_clip_count": len(rows),
        "source_authorities": dict(sorted(source_authorities.items())),
        "rows": tuple(_row_to_dict(row) for row in sorted(rows, key=lambda r: r.clip_id)),
    }
    document["manifest_checksum"] = compute_manifest_checksum(document)
    return document


def _direction_to_dict(direction: DirectionRef) -> dict[str, Any]:
    return {
        "direction_id": direction.direction_id,
        "direction_version": direction.direction_version,
        "direction_sha256": direction.direction_sha256,
        "space": direction.space,
        "seed": direction.seed,
    }


def _row_to_dict(row: ControlManifestRow) -> dict[str, Any]:
    return {
        "clip_id": row.clip_id,
        "pair_key": row.pair_key,
        "control_type": row.control_type,
        "event_id": row.event_id,
        "trajectory_id": row.trajectory_id,
        "layout_id": row.layout_id,
        "rollout_seed": row.rollout_seed,
        "alpha_requested": row.alpha_requested,
        "alpha_applied": row.alpha_applied,
        "cap_reduced": row.cap_reduced,
        "dose_id": row.dose_id,
        "direction_id": row.direction_id,
        "direction_version": row.direction_version,
        "direction_sha256": row.direction_sha256,
        "direction_seed": row.direction_seed,
        "target_layer_idx": row.target_layer_idx,
        "target_timestep_idx": row.target_timestep_idx,
        "hook_site": row.hook_site,
        "owner_role": row.owner_role,
        "status": row.status,
    }


def compute_manifest_checksum(document: Mapping[str, Any]) -> str:
    """Checksum the manifest's content, excluding the checksum itself."""

    payload = {
        key: value for key, value in document.items() if key != "manifest_checksum"
    }
    encoded = json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def freeze_control_manifest(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return the manifest marked frozen, with a checksum over the frozen bytes.

    Freezing is only meaningful before rollouts exist, so this rejects a
    manifest whose rows have already moved past ``planned``.
    """

    validate_control_manifest(document)
    non_planned = sorted(
        {row["status"] for row in document["rows"] if row["status"] != "planned"}
    )
    if non_planned:
        raise ControlManifestError(
            f"cannot freeze a manifest whose rows already have statuses "
            f"{non_planned}; the control matrix must be frozen before any "
            "rollout is generated"
        )
    frozen = dict(document)
    frozen["status"] = "frozen"
    frozen["manifest_checksum"] = compute_manifest_checksum(frozen)
    return frozen


def assert_no_post_rollout_addition(
    frozen: Mapping[str, Any], candidate: Mapping[str, Any]
) -> None:
    """Reject any control row added, removed, or re-identified after freezing.

    Row *status* may advance (``planned`` -> ``generated``, and so on):
    that is what execution does. Row *identity* may not change at all,
    because a control matrix that gains a row after outcomes exist is no
    longer a pre-outcome design.
    """

    if frozen.get("status") != "frozen":
        raise ControlManifestError("the reference manifest is not frozen")

    frozen_rows = {row["clip_id"]: row for row in frozen["rows"]}
    candidate_rows = {row["clip_id"]: row for row in candidate["rows"]}

    added = sorted(set(candidate_rows) - set(frozen_rows))
    removed = sorted(set(frozen_rows) - set(candidate_rows))
    if added:
        raise ControlManifestError(
            f"{len(added)} control clips were added after the manifest was "
            f"frozen: {added[:5]}"
        )
    if removed:
        raise ControlManifestError(
            f"{len(removed)} frozen control clips are missing from the "
            f"candidate: {removed[:5]}"
        )

    mutable = {"status"}
    for clip_id, frozen_row in frozen_rows.items():
        candidate_row = candidate_rows[clip_id]
        for field_name, value in frozen_row.items():
            if field_name in mutable:
                continue
            if candidate_row.get(field_name) != value:
                raise ControlManifestError(
                    f"clip {clip_id!r} field {field_name!r} changed after "
                    f"freezing ({value!r} -> {candidate_row.get(field_name)!r})"
                )


def _find_forbidden_fields(node: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if str(key) in FORBIDDEN_OUTCOME_FIELDS:
                found.append(here)
            found.extend(_find_forbidden_fields(value, here))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            found.extend(_find_forbidden_fields(value, f"{path}[{index}]"))
    return found


def validate_control_manifest(document: Mapping[str, Any]) -> None:
    """Validate a control manifest, raising on the first violation."""

    if document.get("schema_id") != SCHEMA_ID:
        raise ControlManifestError(
            f"expected schema_id {SCHEMA_ID!r}, got {document.get('schema_id')!r}"
        )
    if document.get("status") not in MANIFEST_STATUSES:
        raise ControlManifestError(f"unknown status {document.get('status')!r}")
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise ControlManifestError("evidence_kind must be 'real' or 'synthetic'")
    if not document.get("pre_outcome"):
        raise ControlManifestError("a control manifest must declare pre_outcome=true")
    if document.get("outcome_derived_selection"):
        raise ControlManifestError(
            "outcome_derived_selection must be false; a control chosen from an "
            "outcome is not a control"
        )

    forbidden = _find_forbidden_fields(document)
    if forbidden:
        raise ControlManifestError(
            f"manifest contains outcome-derived fields {sorted(forbidden)[:5]}; "
            "a pre-outcome manifest cannot reference a measurement"
        )

    rows = document.get("rows") or ()
    if not rows:
        raise ControlManifestError("a control manifest must contain rows")

    clip_ids = [row["clip_id"] for row in rows]
    duplicates = sorted({cid for cid in clip_ids if clip_ids.count(cid) > 1})
    if duplicates:
        raise ControlManifestError(f"duplicate clip IDs {duplicates[:5]}")

    if document.get("planned_clip_count") != len(rows):
        raise ControlManifestError(
            "planned_clip_count does not match the number of rows"
        )
    if document.get("expected_clip_count") != len(rows):
        raise ControlManifestError(
            f"expected {document.get('expected_clip_count')} clips but the "
            f"manifest contains {len(rows)}; a control matrix with an omitted "
            "or extra row is incomplete"
        )

    # Every pair key must have exactly one alpha-zero baseline, and every
    # non-alpha-zero clip must have a pair key that resolves to one.
    alpha_zero_by_pair: dict[str, int] = {}
    pair_keys: set[str] = set()
    for row in rows:
        pair_keys.add(row["pair_key"])
        if row["control_type"] == ControlType.ALPHA_ZERO.value:
            alpha_zero_by_pair[row["pair_key"]] = (
                alpha_zero_by_pair.get(row["pair_key"], 0) + 1
            )
    for pair_key, count in alpha_zero_by_pair.items():
        if count != 1:
            raise ControlManifestError(
                f"pair key {pair_key!r} has {count} alpha-zero baselines; each "
                "comparison pair needs exactly one"
            )

    baseline_pair_prefixes = {
        key.rsplit("|dose", 1)[0] for key in alpha_zero_by_pair
    }
    unmatched = sorted(
        key for key in pair_keys if key.rsplit("|dose", 1)[0] not in baseline_pair_prefixes
    )
    if unmatched:
        raise ControlManifestError(
            f"pair keys {unmatched[:5]} have no alpha-zero baseline for their "
            "event/seed; every pushed clip needs a matched baseline"
        )

    for row in rows:
        if row["status"] not in ROW_STATUSES:
            raise ControlManifestError(
                f"clip {row['clip_id']!r} has unknown status {row['status']!r}"
            )
        if not row["owner_role"]:
            raise ControlManifestError(f"clip {row['clip_id']!r} has no owner")
        if row["hook_site"] != FROZEN_HOOK_SITE:
            raise ControlManifestError(
                f"clip {row['clip_id']!r} declares hook site {row['hook_site']!r}"
            )
        if row["control_type"] == ControlType.WRONG_LAYER.value:
            if row["target_layer_idx"] == document["target_layer_idx"]:
                raise ControlManifestError(
                    f"wrong-layer clip {row['clip_id']!r} targets the primary layer"
                )
        if row["control_type"] == ControlType.WRONG_TIMESTEP.value:
            if row["target_timestep_idx"] == document["target_timestep_idx"]:
                raise ControlManifestError(
                    f"wrong-timestep clip {row['clip_id']!r} targets the primary "
                    "timestep"
                )
        if row["control_type"] == ControlType.RANDOM_DIRECTION.value:
            if row["direction_seed"] is None:
                raise ControlManifestError(
                    f"random-direction clip {row['clip_id']!r} records no seed"
                )

    if document.get("manifest_checksum") != compute_manifest_checksum(document):
        raise ControlManifestError(
            "manifest_checksum does not match the manifest's own content"
        )


def reconcile_planned_versus_available(
    manifest: Mapping[str, Any], available_clip_ids: Sequence[str]
) -> dict[str, Any]:
    """Compare the planned control matrix against what actually exists."""

    planned = {row["clip_id"] for row in manifest["rows"]}
    available = list(available_clip_ids)
    counts: dict[str, int] = {}
    for clip_id in available:
        counts[clip_id] = counts.get(clip_id, 0) + 1

    missing = sorted(planned - set(counts))
    duplicated = sorted(cid for cid, count in counts.items() if count > 1)
    unexpected = sorted(set(counts) - planned)

    return {
        "schema_id": "person-d-u4-control-manifest-reconciliation-v0-1",
        "schema_version": SCHEMA_VERSION,
        "manifest_id": manifest["manifest_id"],
        "manifest_version": manifest["manifest_version"],
        "manifest_checksum": manifest["manifest_checksum"],
        "planned_count": len(planned),
        "available_count": len(counts),
        "missing_clip_ids": tuple(missing),
        "duplicated_clip_ids": tuple(duplicated),
        "unexpected_clip_ids": tuple(unexpected),
        "complete": not missing and not duplicated and not unexpected,
    }


def build_person_d_to_a_and_e_handoff(
    manifest: Mapping[str, Any],
    *,
    manifest_path: str,
    manifest_sha256: str,
) -> dict[str, Any]:
    """Build the machine-readable D-to-A / D-to-E control handoff.

    This is the document Persons A and E consume: A generates one clip per
    ``clip_id``; E measures each generated clip and joins back on
    ``clip_id`` and ``pair_key``, never on filename or row order.
    """

    validate_control_manifest(manifest)
    return {
        "schema_id": "person-d-u4-control-handoff-v0-1",
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "consumer_roles": ("person_a", "person_e"),
        "manifest_id": manifest["manifest_id"],
        "manifest_version": manifest["manifest_version"],
        "manifest_status": manifest["status"],
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_sha256,
        "manifest_checksum": manifest["manifest_checksum"],
        "evidence_kind": manifest["evidence_kind"],
        "clip_count": len(manifest["rows"]),
        "clip_ids": tuple(row["clip_id"] for row in manifest["rows"]),
        "pair_keys": tuple(sorted({row["pair_key"] for row in manifest["rows"]})),
        "join_keys": ("clip_id", "pair_key"),
        "join_rule": (
            "Join on clip_id and pair_key only. Filenames, paths, and row order "
            "are not identity and must never be used to match a measurement to a "
            "control."
        ),
        "person_a_obligation": (
            "Generate exactly one rollout per clip_id at the declared direction, "
            "layer, timestep, and alpha; report generation_failed rather than "
            "omitting a clip."
        ),
        "person_e_obligation": (
            "Measure every generated clip and return one measurement row per "
            "clip_id, using an explicit reason code for any clip that is not "
            "measured."
        ),
        "post_rollout_addition_permitted": False,
    }


def dump_control_manifest(document: Mapping[str, Any]) -> str:
    """Serialize a validated control manifest deterministically."""

    validate_control_manifest(document)
    return json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "FORBIDDEN_OUTCOME_FIELDS",
    "FROZEN_HOOK_SITE",
    "FROZEN_LAYER_RANGE",
    "FROZEN_TIMESTEP_RANGE",
    "MANIFEST_STATUSES",
    "ROW_STATUSES",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "ControlManifestError",
    "ControlManifestRow",
    "ControlType",
    "DirectionRef",
    "DoseSpec",
    "HeldOutEvent",
    "assert_no_post_rollout_addition",
    "build_control_manifest",
    "build_control_manifest_rows",
    "build_person_d_to_a_and_e_handoff",
    "compute_manifest_checksum",
    "dump_control_manifest",
    "expected_row_count",
    "freeze_control_manifest",
    "make_clip_id",
    "make_pair_key",
    "reconcile_planned_versus_available",
    "validate_control_manifest",
]
