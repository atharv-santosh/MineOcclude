"""Person D's 66-cell production execution universe (B-owned admission).

Builds the exact set of prediction rows Person D's frozen baselines run
on, from Person B's final analysis authority at commit
``25e09cb605699cdcb00dec1fbb1726977bec55e0``.

The single most important rule here: **admission is Person B's, not
Person D's.** The execution universe is
``row_universe_records.jsonl`` filtered to ``status == "accepted"`` --
the exact selector Person B's ``b_to_d_successor_handoff.json`` names.
Person D never re-derives admission, never widens it, and never admits a
row merely because a baseline could technically compute a number for it.

Two superseded accountings exist upstream and are deliberately not used:

* ``person_b_66_cell_preactivation_v0_1/fold_manifest.json`` declares
  ``admitted_analysis_row_count = 984``.
* Person A's frame manifest copies that same 984-row admission into each
  record's ``fold_binding.status``.

Person B's ``b_to_d_successor_handoff.json`` supersedes both with 662
admitted / 1,806 excluded, and names ``row_universe_records.jsonl`` as
the row identity source. The 322-row difference is exactly the gap
between those two accountings and is reported explicitly rather than
silently resolved. The fold manifest remains authoritative for *fold
assignment*, which is unchanged between the two (verified: zero
disagreements).

Context construction reuses Person D's own frozen causal algorithm from
:mod:`mineocclude.baselines.capture_ingest` -- last-visible position,
two-point estimated visible-window velocity, and tau resetting on each
visible frame -- applied to Person B's per-frame oracle-target records
instead of Person C's raw capture streams. That substitution is exact,
not approximate: on every visible row Person B's
``last_visible_position_blocks`` equals that frame's own
``x_true_blocks`` (verified for all 1,484 visible target rows), so the
visible-position sequence the algorithm needs is recovered without
touching hidden truth.

``x_true_blocks`` is scoring-only and is never placed on a
:class:`~mineocclude.baselines.interface.TrajectoryContext`; that type
has no hidden-truth field by construction.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from mineocclude.baselines.capture_ingest import REGIME_A_DT_SECONDS
from mineocclude.baselines.interface import TrajectoryContext

# --------------------------------------------------------------------------
# Person B 66-cell authority
# --------------------------------------------------------------------------

PERSON_B_66_CELL_COMMIT = "25e09cb605699cdcb00dec1fbb1726977bec55e0"

PERSON_B_ROW_UNIVERSE_RECORDS_PATH = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/row_universe_records.jsonl"
)
PERSON_B_ROW_UNIVERSE_RECORDS_SHA256 = (
    "29b4cf003f3d9479b3606f17947879078801b400b09d942bd6827544b95227b2"
)
PERSON_B_ROW_UNIVERSE_RECEIPT_PATH = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/row_universe_receipt_v0_2.json"
)
PERSON_B_ROW_UNIVERSE_RECEIPT_SHA256 = (
    "e897c31cda46e2dbe7fab605320cd98eba68a1396a80ccd78b178c8dc5547351"
)
PERSON_B_ORACLE_TARGET_MANIFEST_PATH = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_manifest.json"
)
PERSON_B_ORACLE_TARGET_MANIFEST_SHA256 = (
    "c064e1856be67ebab95cbcb07b80009729c396f2398b15b4dec57458b73b8ac9"
)
PERSON_B_ORACLE_TARGET_RECORDS_PATH = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_records.jsonl"
)
PERSON_B_ORACLE_TARGET_RECORDS_SHA256 = (
    "d95c83518d2ad322e6862f5460727382511fe831c0c6658a6cf72c9f7a8858b1"
)
PERSON_B_FOLD_MANIFEST_PATH = (
    "docs/status/person_b_66_cell_preactivation_v0_1/fold_manifest.json"
)
PERSON_B_FOLD_MANIFEST_SHA256 = (
    "86739975882f4926c3398d5bfa21611daf06c579b3893809eb385e8dcd03001d"
)
PERSON_B_TO_D_HANDOFF_PATH = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/b_to_d_successor_handoff.json"
)
PERSON_B_TO_D_HANDOFF_SHA256 = (
    "4b945f79ac1e64bf3253cafa05ca42ac44eccbc5eb4f1db70203871f018bed01"
)

#: Person B's own declared accounting, from ``b_to_d_successor_handoff``.
REQUIRED_MODEL_FRAME_KEY_COUNT = 2468
REQUIRED_TRAJECTORY_COUNT = 66
REQUIRED_TARGET_BEARING_ROW_COUNT = 2108
REQUIRED_ADMITTED_ANALYSIS_ROW_COUNT = 662
REQUIRED_EXCLUDED_ANALYSIS_ROW_COUNT = 1806
REQUIRED_AMBIGUOUS_GEOMETRY_ROW_COUNT = 42

#: The exact selector Person B names for the eligible baseline universe.
ADMISSION_SELECTOR = "status == 'accepted'"

#: Superseded predecessor accounting, recorded so the difference is
#: visible rather than silently resolved. Never used for admission.
SUPERSEDED_PREACTIVATION_ADMITTED_ROW_COUNT = 984

PERSON_B_ANALYSIS_ARITHMETIC_DTYPE = "float64"
PERSON_B_CONFIG_HASH = (
    "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
)
PERSON_B_U1_TARGET = "mu_oracle_blocks"
PERSON_B_U2_TARGET = "log_sigma_oracle"
PERSON_B_SCORING_ONLY_FIELDS = ("x_true_blocks",)

#: Person B's exclusion vocabulary, preserved verbatim.
EXCLUSION_REASONS: tuple[str, ...] = (
    "no_object_control_not_oracle_eligible",
    "ambiguous_geometry_edge_convention",
    "visibility_channel_disagreement",
    "person_c_quarantined_row",
    "pre_first_seen",
    "outside_frozen_condition_selection",
)

RowKey = tuple[str, int]


class ProductionUniverseError(ValueError):
    """Raised when the 66-cell execution universe cannot be honestly built."""


@dataclass(frozen=True)
class ExecutionUniverse:
    """The built, reconciled 66-cell production execution universe."""

    contexts: tuple[TrajectoryContext, ...]
    mu_oracle_by_key: Mapping[RowKey, float]
    log_sigma_oracle_by_key: Mapping[RowKey, float]
    x_true_by_key: Mapping[RowKey, float]
    tau_by_key: Mapping[RowKey, float]
    visible_positions_by_trajectory: Mapping[str, tuple[float, ...]]
    admitted_keys: frozenset[RowKey]
    excluded_counts_by_reason: Mapping[str, int]
    counts_by_fold: Mapping[int, int]
    counts_by_layout: Mapping[str, int]
    counts_by_control_type: Mapping[str, int]
    counts_by_stratum: Mapping[str, int]
    counts_by_scope: Mapping[str, int]
    total_model_frame_key_count: int
    trajectory_count: int
    admitted_trajectory_count: int


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_verified_json(path: Path, expected_sha256: str) -> Any:
    """Load a JSON artifact only after its raw bytes verify."""

    file_path = Path(path)
    if not file_path.exists():
        raise ProductionUniverseError(f"artifact not found: {file_path}")
    actual = sha256_of_file(file_path)
    if actual != expected_sha256:
        raise ProductionUniverseError(
            f"{file_path.name}: sha256 mismatch, expected {expected_sha256}, "
            f"got {actual}"
        )
    return json.loads(file_path.read_text(encoding="utf-8"))


def load_verified_jsonl(path: Path, expected_sha256: str) -> list[dict[str, Any]]:
    """Load a JSONL artifact only after its raw bytes verify."""

    file_path = Path(path)
    if not file_path.exists():
        raise ProductionUniverseError(f"artifact not found: {file_path}")
    actual = sha256_of_file(file_path)
    if actual != expected_sha256:
        raise ProductionUniverseError(
            f"{file_path.name}: sha256 mismatch, expected {expected_sha256}, "
            f"got {actual}"
        )
    return [
        json.loads(line)
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def verify_person_b_accounting(
    *,
    row_universe: Sequence[Mapping[str, Any]],
    oracle_targets: Sequence[Mapping[str, Any]],
    handoff: Mapping[str, Any],
) -> tuple[str, ...]:
    """Reconcile Person B's declared accounting against its own records.

    Fails closed on any disagreement between what the handoff declares
    and what the record files actually contain -- a chat-supplied number
    is never a substitute for either.
    """

    errors: list[str] = []

    if len(row_universe) != REQUIRED_MODEL_FRAME_KEY_COUNT:
        errors.append(
            f"row_universe_count:{len(row_universe)}!={REQUIRED_MODEL_FRAME_KEY_COUNT}"
        )
    if len(oracle_targets) != REQUIRED_TARGET_BEARING_ROW_COUNT:
        errors.append(
            f"oracle_target_count:{len(oracle_targets)}!="
            f"{REQUIRED_TARGET_BEARING_ROW_COUNT}"
        )

    keys = {(r["trajectory_id"], r["model_frame_idx"]) for r in row_universe}
    if len(keys) != len(row_universe):
        errors.append("row_universe_has_duplicate_keys")
    target_keys = {(t["trajectory_id"], t["model_frame_idx"]) for t in oracle_targets}
    if not target_keys <= keys:
        errors.append("oracle_targets_not_a_subset_of_row_universe")

    accepted = [r for r in row_universe if r.get("status") == "accepted"]
    excluded = [r for r in row_universe if r.get("status") != "accepted"]
    if len(accepted) != REQUIRED_ADMITTED_ANALYSIS_ROW_COUNT:
        errors.append(
            f"admitted_count:{len(accepted)}!={REQUIRED_ADMITTED_ANALYSIS_ROW_COUNT}"
        )
    if len(excluded) != REQUIRED_EXCLUDED_ANALYSIS_ROW_COUNT:
        errors.append(
            f"excluded_count:{len(excluded)}!={REQUIRED_EXCLUDED_ANALYSIS_ROW_COUNT}"
        )

    eligible = handoff.get("eligible_baseline_universe") or {}
    if eligible.get("admitted_analysis_row_count") != len(accepted):
        errors.append("handoff_admitted_count_disagrees_with_records")
    if eligible.get("excluded_analysis_row_count") != len(excluded):
        errors.append("handoff_excluded_count_disagrees_with_records")
    if (eligible.get("row_identity_source") or {}).get(
        "eligible_rows_selector"
    ) != ADMISSION_SELECTOR:
        errors.append("handoff_admission_selector_changed")
    if list(eligible.get("join_key") or ()) != ["trajectory_id", "model_frame_idx"]:
        errors.append("handoff_join_key_changed")

    declared_exclusions = {
        entry["exclusion_reason"]: entry["row_count"]
        for entry in handoff.get("excluded_counts_by_reason", ())
    }
    observed_exclusions = Counter(
        r.get("exclusion_reason") for r in excluded
    )
    for reason, count in declared_exclusions.items():
        if observed_exclusions.get(reason) != count:
            errors.append(
                f"exclusion_reason_count_mismatch:{reason}:"
                f"declared={count}:observed={observed_exclusions.get(reason)}"
            )
    unknown = sorted(
        str(reason)
        for reason in observed_exclusions
        if reason not in EXCLUSION_REASONS
    )
    if unknown:
        errors.append(f"unknown_exclusion_reasons:{unknown}")

    ambiguous = sum(1 for r in row_universe if r.get("geometric_ambiguous"))
    if ambiguous != REQUIRED_AMBIGUOUS_GEOMETRY_ROW_COUNT:
        errors.append(
            f"ambiguous_geometry_count:{ambiguous}!="
            f"{REQUIRED_AMBIGUOUS_GEOMETRY_ROW_COUNT}"
        )
    ambiguous_admitted = sum(
        1 for r in accepted if r.get("geometric_ambiguous")
    )
    if ambiguous_admitted != 0:
        errors.append(f"ambiguous_rows_admitted:{ambiguous_admitted}")

    for entry in eligible.get("admitted_counts_by_fold", ()):
        observed = sum(1 for r in accepted if r["fold_idx"] == entry["fold_idx"])
        if observed != entry["row_count"]:
            errors.append(
                f"fold_count_mismatch:{entry['fold_idx']}:"
                f"declared={entry['row_count']}:observed={observed}"
            )
    for entry in eligible.get("admitted_counts_by_layout", ()):
        observed = sum(1 for r in accepted if r["layout_id"] == entry["layout_id"])
        if observed != entry["row_count"]:
            errors.append(
                f"layout_count_mismatch:{entry['layout_id']}:"
                f"declared={entry['row_count']}:observed={observed}"
            )
    for entry in eligible.get("admitted_counts_by_control_type", ()):
        observed = sum(
            1 for r in accepted if r["control_type"] == entry["control_type"]
        )
        if observed != entry["row_count"]:
            errors.append(
                f"control_type_count_mismatch:{entry['control_type']}:"
                f"declared={entry['row_count']}:observed={observed}"
            )

    return tuple(errors)


def verify_fold_manifest_agreement(
    *,
    row_universe: Sequence[Mapping[str, Any]],
    fold_manifest: Mapping[str, Any],
) -> tuple[str, ...]:
    """Require the fold manifest to agree with the row universe on every fold.

    The fold manifest's *admission* counts are superseded, but its fold
    *assignment* is still authoritative, so exact agreement on
    ``fold_idx`` for every shared key is required.
    """

    memberships = fold_manifest.get("memberships")
    if not isinstance(memberships, list):
        return ("fold_manifest_has_no_memberships",)

    # Every check below runs regardless of the count, so a caller sees the
    # full set of problems rather than only the first one.
    errors: list[str] = []
    if len(memberships) != REQUIRED_MODEL_FRAME_KEY_COUNT:
        errors.append(
            f"fold_membership_count:{len(memberships)}!="
            f"{REQUIRED_MODEL_FRAME_KEY_COUNT}"
        )

    fold_by_key = {
        (m["trajectory_id"], m["model_frame_idx"]): m["fold_idx"] for m in memberships
    }
    disagreements = 0
    for row in row_universe:
        key = (row["trajectory_id"], row["model_frame_idx"])
        if key not in fold_by_key:
            errors.append(f"fold_manifest_missing_key:{key}")
        elif fold_by_key[key] != row["fold_idx"]:
            disagreements += 1
    if disagreements:
        errors.append(f"fold_assignment_disagreements:{disagreements}")

    # Layout-grouped folds: one layout never spans two folds.
    layouts_by_fold: dict[int, set[str]] = defaultdict(set)
    folds_by_layout: dict[str, set[int]] = defaultdict(set)
    for row in row_universe:
        layouts_by_fold[row["fold_idx"]].add(row["layout_id"])
        folds_by_layout[row["layout_id"]].add(row["fold_idx"])
    split = sorted(
        layout for layout, folds in folds_by_layout.items() if len(folds) > 1
    )
    if split:
        errors.append(f"layout_spans_multiple_folds:{split}")

    return tuple(errors)


def superseded_admission_difference(
    *,
    row_universe: Sequence[Mapping[str, Any]],
    frame_manifest_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Report the 984-vs-662 admission difference explicitly.

    Person A's frame manifest carries Person B's *predecessor* admission
    in ``fold_binding.status``. Reporting the difference is how the
    successor's narrowing stays visible instead of looking like a bug.
    """

    a_status = {
        (r["trajectory_id"], r["model_frame_idx"]): (r.get("fold_binding") or {}).get(
            "status"
        )
        for r in frame_manifest_records
    }
    b_status = {
        (r["trajectory_id"], r["model_frame_idx"]): r.get("status")
        for r in row_universe
    }
    disagreeing = sorted(k for k, v in b_status.items() if a_status.get(k) != v)
    a_accepted = sum(1 for v in a_status.values() if v == "accepted")
    b_accepted = sum(1 for v in b_status.values() if v == "accepted")

    return {
        "person_a_frame_manifest_accepted_count": a_accepted,
        "person_b_row_universe_accepted_count": b_accepted,
        "disagreeing_key_count": len(disagreeing),
        "narrowed_by": a_accepted - b_accepted,
        "authority_used_for_admission": "person_b_row_universe_records",
        "superseded_source": (
            "person_a frame manifest fold_binding.status, which copies "
            "person_b_66_cell_preactivation_v0_1/fold_manifest.json's "
            f"{SUPERSEDED_PREACTIVATION_ADMITTED_ROW_COUNT}-row predecessor "
            "admission"
        ),
        "explanation": (
            "Person B's b_to_d_successor_handoff supersedes the preactivation "
            "handoff and narrows admission from "
            f"{SUPERSEDED_PREACTIVATION_ADMITTED_ROW_COUNT} to "
            f"{REQUIRED_ADMITTED_ANALYSIS_ROW_COUNT} rows. Person D follows the "
            "successor. Fold assignments are unchanged between the two."
        ),
    }


def _regime_literal(value: Any) -> str:
    if value == "regime_a":
        return "A"
    if value == "regime_b":
        return "B"
    raise ProductionUniverseError(f"unknown regime {value!r}")


def build_execution_universe(
    *,
    row_universe: Sequence[Mapping[str, Any]],
    oracle_targets: Sequence[Mapping[str, Any]],
    config_hash: str = PERSON_B_CONFIG_HASH,
    dt_seconds: float = REGIME_A_DT_SECONDS,
) -> ExecutionUniverse:
    """Build the admitted contexts and oracle lookups for the 66-cell run.

    Causal state (last-visible position, two-point estimated velocity,
    tau) is accumulated over each trajectory's **full** frame sequence in
    ``model_frame_idx`` order, then restricted to Person B's admitted
    rows -- exactly as the ten-pilot path did. Accumulating only over
    admitted rows would silently change what "the previous visible
    frame" means.
    """

    fold_by_key: dict[RowKey, int] = {}
    status_by_key: dict[RowKey, str] = {}
    for row in row_universe:
        key = (row["trajectory_id"], row["model_frame_idx"])
        fold_by_key[key] = row["fold_idx"]
        status_by_key[key] = row["status"]

    targets_by_trajectory: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for target in oracle_targets:
        targets_by_trajectory[target["trajectory_id"]].append(target)

    contexts: list[TrajectoryContext] = []
    mu_by_key: dict[RowKey, float] = {}
    log_sigma_by_key: dict[RowKey, float] = {}
    x_true_by_key: dict[RowKey, float] = {}
    tau_by_key: dict[RowKey, float] = {}
    visible_positions: dict[str, tuple[float, ...]] = {}

    for trajectory_id in sorted(targets_by_trajectory):
        rows = sorted(
            targets_by_trajectory[trajectory_id], key=lambda r: r["model_frame_idx"]
        )
        indices = [r["model_frame_idx"] for r in rows]
        if indices != list(range(len(indices))):
            raise ProductionUniverseError(
                f"{trajectory_id}: oracle target frame indices are not a "
                "contiguous 0..n-1 range; causal context construction requires "
                "the full frame sequence"
            )

        scripted = rows[0]
        layout_id = scripted["layout_id"]
        regime = _regime_literal(scripted["regime"])
        v_scripted = float(scripted["v"])
        q_scripted = float(scripted["q"])
        duration_seconds = float(scripted["duration"])
        seed = int(scripted["seed"])

        last_seen_position: Optional[float] = None
        last_seen_velocity: Optional[float] = None
        previous_visible_position: Optional[float] = None
        hidden_ticks = 0
        trajectory_visible_positions: list[float] = []

        for row in rows:
            model_frame_idx = row["model_frame_idx"]
            key = (trajectory_id, model_frame_idx)
            visibility_value = row["visibility"]
            if visibility_value not in ("visible", "occluded"):
                raise ProductionUniverseError(
                    f"{key}: unrecognized visibility {visibility_value!r}"
                )
            is_visible = visibility_value == "visible"

            if is_visible:
                position = row["last_visible_position_blocks"]
                if position is None:
                    raise ProductionUniverseError(
                        f"{key}: visible row carries no last_visible_position_blocks"
                    )
                position = float(position)
                if previous_visible_position is not None:
                    last_seen_velocity = (
                        position - previous_visible_position
                    ) / dt_seconds
                last_seen_position = position
                previous_visible_position = position
                trajectory_visible_positions.append(position)
                hidden_ticks = 0
                tau_seconds = 0.0
            else:
                hidden_ticks += 1
                tau_seconds = hidden_ticks * dt_seconds

            if status_by_key.get(key) != "accepted":
                continue
            if key not in fold_by_key:
                raise ProductionUniverseError(f"{key}: no fold assignment")

            contexts.append(
                TrajectoryContext(
                    trajectory_id=trajectory_id,
                    layout_id=layout_id,
                    model_frame_idx=model_frame_idx,
                    fold=fold_by_key[key],
                    regime=regime,
                    tau_seconds=tau_seconds,
                    visibility=is_visible,
                    last_seen_position_blocks=last_seen_position,
                    last_seen_velocity_blocks_per_s=last_seen_velocity,
                    v_scripted_blocks_per_s=v_scripted,
                    q_scripted_blocks2_per_s=q_scripted,
                    duration_seconds=duration_seconds,
                    config_hash=config_hash,
                    seed=seed,
                )
            )
            if row.get("mu_oracle_blocks") is not None:
                mu_by_key[key] = float(row["mu_oracle_blocks"])
            if row.get("log_sigma_oracle") is not None:
                log_sigma_by_key[key] = float(row["log_sigma_oracle"])
            if row.get("x_true_blocks") is not None:
                x_true_by_key[key] = float(row["x_true_blocks"])
            tau_by_key[key] = tau_seconds

        visible_positions[trajectory_id] = tuple(trajectory_visible_positions)

    accepted_rows = [r for r in row_universe if r["status"] == "accepted"]
    admitted_keys = frozenset(
        (r["trajectory_id"], r["model_frame_idx"]) for r in accepted_rows
    )
    built_keys = {(c.trajectory_id, c.model_frame_idx) for c in contexts}
    if built_keys != admitted_keys:
        missing = sorted(admitted_keys - built_keys)
        extra = sorted(built_keys - admitted_keys)
        raise ProductionUniverseError(
            "execution universe does not reconcile to Person B's admitted rows: "
            f"{len(missing)} missing {missing[:3]}, {len(extra)} extra {extra[:3]}"
        )

    scope_counts: Counter = Counter()
    for row in accepted_rows:
        for scope in row.get("analysis_scopes", ()):
            scope_counts[scope] += 1

    # Restrict the visible-history mapping to trajectories actually executed,
    # so visible_history_q's fold-integrity check cannot see an unassigned one.
    executed_trajectories = {c.trajectory_id for c in contexts}

    return ExecutionUniverse(
        contexts=tuple(contexts),
        mu_oracle_by_key=dict(mu_by_key),
        log_sigma_oracle_by_key=dict(log_sigma_by_key),
        x_true_by_key=dict(x_true_by_key),
        tau_by_key=dict(tau_by_key),
        visible_positions_by_trajectory={
            trajectory_id: positions
            for trajectory_id, positions in visible_positions.items()
            if trajectory_id in executed_trajectories
        },
        admitted_keys=admitted_keys,
        excluded_counts_by_reason=dict(
            sorted(
                Counter(
                    r.get("exclusion_reason")
                    for r in row_universe
                    if r["status"] != "accepted"
                ).items()
            )
        ),
        counts_by_fold=dict(
            sorted(Counter(r["fold_idx"] for r in accepted_rows).items())
        ),
        counts_by_layout=dict(
            sorted(Counter(r["layout_id"] for r in accepted_rows).items())
        ),
        counts_by_control_type=dict(
            sorted(Counter(r["control_type"] for r in accepted_rows).items())
        ),
        counts_by_stratum=dict(
            sorted(Counter(r["admission_stratum"] for r in accepted_rows).items())
        ),
        counts_by_scope=dict(sorted(scope_counts.items())),
        total_model_frame_key_count=len(row_universe),
        trajectory_count=len({r["trajectory_id"] for r in row_universe}),
        admitted_trajectory_count=len(executed_trajectories),
    )


__all__ = [
    "ADMISSION_SELECTOR",
    "EXCLUSION_REASONS",
    "PERSON_B_66_CELL_COMMIT",
    "PERSON_B_ANALYSIS_ARITHMETIC_DTYPE",
    "PERSON_B_CONFIG_HASH",
    "PERSON_B_FOLD_MANIFEST_PATH",
    "PERSON_B_FOLD_MANIFEST_SHA256",
    "PERSON_B_ORACLE_TARGET_MANIFEST_PATH",
    "PERSON_B_ORACLE_TARGET_MANIFEST_SHA256",
    "PERSON_B_ORACLE_TARGET_RECORDS_PATH",
    "PERSON_B_ORACLE_TARGET_RECORDS_SHA256",
    "PERSON_B_ROW_UNIVERSE_RECEIPT_PATH",
    "PERSON_B_ROW_UNIVERSE_RECEIPT_SHA256",
    "PERSON_B_ROW_UNIVERSE_RECORDS_PATH",
    "PERSON_B_ROW_UNIVERSE_RECORDS_SHA256",
    "PERSON_B_SCORING_ONLY_FIELDS",
    "PERSON_B_TO_D_HANDOFF_PATH",
    "PERSON_B_TO_D_HANDOFF_SHA256",
    "PERSON_B_U1_TARGET",
    "PERSON_B_U2_TARGET",
    "REQUIRED_ADMITTED_ANALYSIS_ROW_COUNT",
    "REQUIRED_AMBIGUOUS_GEOMETRY_ROW_COUNT",
    "REQUIRED_EXCLUDED_ANALYSIS_ROW_COUNT",
    "REQUIRED_MODEL_FRAME_KEY_COUNT",
    "REQUIRED_TARGET_BEARING_ROW_COUNT",
    "REQUIRED_TRAJECTORY_COUNT",
    "SUPERSEDED_PREACTIVATION_ADMITTED_ROW_COUNT",
    "ExecutionUniverse",
    "ProductionUniverseError",
    "build_execution_universe",
    "load_verified_json",
    "load_verified_jsonl",
    "sha256_of_file",
    "superseded_admission_difference",
    "verify_fold_manifest_agreement",
    "verify_person_b_accounting",
]
