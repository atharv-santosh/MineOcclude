"""A8 — capture cohort validation (authority A8, lifecycle A8).

Closes the cohort and decides **what population the analysis has**, using only
technical evidence: the hash-chained ledger, the per-unit durable receipts and
the frozen identity manifest. Nothing here may read a model outcome, a
prediction, an activation or a statistic, and nothing here may decide *which*
identities survive on any basis other than whether their five capture units are
complete.

The frozen attrition rule, verbatim:

    complete five-way paired identities >= 25 : normal analysis
    complete five-way paired identities in [15, 24] :
            proceed with the prespecified analysis, at reduced precision,
            with conspicuous attrition disclosure in every reported result
    complete five-way paired identities < 15 :
            NO graded Experiment III inferential claim

The primary population is the complete five-way paired subset **only**. A
partially captured identity is excluded whole: its captured conditions are not
partially used, because a within-identity contrast computed over a different set
of conditions per identity is not the frozen estimand. That is why
:func:`close_cohort` reports ``partial_identities`` separately and never folds
their units into the analysable count.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_COUNT,
    PRODUCTION_IDENTITY_IDS,
    TARGET_ROWS_PER_CAPTURE,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.execution import HashChainLedger
from mineocclude.experiment_iii.schema import ConditionId

__all__ = [
    "ATTRITION_BRANCHES",
    "MINIMUM_FOR_GRADED_INFERENCE",
    "NORMAL_COMPLETE_IDENTITIES",
    "attrition_branch",
    "close_cohort",
]

STAGE = "A8"
NEXT_STAGE = "A9"

NORMAL_COMPLETE_IDENTITIES = PRODUCTION_IDENTITY_COUNT  # 25
MINIMUM_FOR_GRADED_INFERENCE = 15

ATTRITION_BRANCHES = (
    "NORMAL",
    "REDUCED_PRECISION_WITH_CONSPICUOUS_DISCLOSURE",
    "NO_GRADED_INFERENTIAL_CLAIM",
)

_ALL_CONDITIONS = tuple(condition.value for condition in ConditionId)


def attrition_branch(n_complete: int) -> dict[str, Any]:
    """The frozen branch for ``n_complete``, with its reporting obligation."""
    if n_complete >= NORMAL_COMPLETE_IDENTITIES:
        return {
            "branch": "NORMAL",
            "n_complete": n_complete,
            "graded_inferential_claim_permitted": True,
            "attrition_disclosure_required": False,
            "reduced_precision": False,
        }
    if n_complete >= MINIMUM_FOR_GRADED_INFERENCE:
        return {
            "branch": "REDUCED_PRECISION_WITH_CONSPICUOUS_DISCLOSURE",
            "n_complete": n_complete,
            "graded_inferential_claim_permitted": True,
            "attrition_disclosure_required": True,
            "reduced_precision": True,
            "disclosure_obligation": (
                "conspicuous attrition disclosure in EVERY reported result"
            ),
        }
    return {
        "branch": "NO_GRADED_INFERENTIAL_CLAIM",
        "n_complete": n_complete,
        "graded_inferential_claim_permitted": False,
        "attrition_disclosure_required": True,
        "reduced_precision": True,
    }


def _unit_is_durable(capture_root: Path, unit_id: str) -> bool:
    """A unit counts only if its durable receipt is actually on disk.

    The ledger says what the campaign believed; the receipt is what survived.
    A8 requires both, so a COMPLETE ledger entry whose evidence was lost cannot
    silently inflate the cohort.
    """
    for candidate in Path(capture_root).glob(f"**/{unit_id}/durable_receipt.json"):
        if candidate.is_file():
            return True
    direct = Path(capture_root) / unit_id / "durable_receipt.json"
    return direct.is_file()


def close_cohort(
    *,
    ledger_path: Path,
    capture_root: Path,
    identity_rows: Sequence[Mapping[str, Any]],
    require_durable_receipt: bool = True,
) -> dict[str, Any]:
    """Build the matrix, find complete five-way identities, apply attrition."""
    binding = verify_authority_binding()
    manifest_identities = [str(row["identity"]) for row in identity_rows]

    pilots = sorted(set(manifest_identities) & set(PILOT_IDENTITY_IDS))
    if pilots:
        raise ExperimentIIIError(
            "COHORT_PILOT_CONTAMINATION",
            f"the production manifest names pilot identities {pilots}; a pilot "
            f"may never be substituted into the production cohort",
        )
    unknown = sorted(set(manifest_identities) - set(PRODUCTION_IDENTITY_IDS))
    if unknown:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"the production manifest names non-production identities {unknown}",
        )
    if len(set(manifest_identities)) != PRODUCTION_IDENTITY_COUNT:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"the manifest holds {len(set(manifest_identities))} identities, "
            f"authority 2.1 freezes {PRODUCTION_IDENTITY_COUNT}",
        )

    ledger = HashChainLedger(Path(ledger_path))
    complete_units = ledger.complete_units()

    # Any COMPLETE unit id outside the frozen matrix is contamination, whether
    # it names a pilot or something that is not an Experiment III unit at all.
    expected_units = {
        f"{identity}__{condition}"
        for identity in manifest_identities
        for condition in _ALL_CONDITIONS
    }
    foreign = sorted(complete_units - expected_units)
    if foreign:
        pilot_units = [
            unit for unit in foreign if unit.split("__")[0] in set(PILOT_IDENTITY_IDS)
        ]
        raise ExperimentIIIError(
            "COHORT_PILOT_CONTAMINATION" if pilot_units else "COHORT_MATRIX_INCONSISTENT",
            f"the capture ledger accepted units outside the frozen production "
            f"matrix: {foreign[:5]}{'...' if len(foreign) > 5 else ''}",
        )

    matrix: dict[str, dict[str, bool]] = {}
    for identity in manifest_identities:
        row: dict[str, bool] = {}
        for condition in _ALL_CONDITIONS:
            unit_id = f"{identity}__{condition}"
            accepted = unit_id in complete_units
            if accepted and require_durable_receipt:
                accepted = _unit_is_durable(capture_root, unit_id)
            row[condition] = accepted
        matrix[identity] = row

    complete_identities = sorted(
        identity for identity, row in matrix.items() if all(row.values())
    )
    partial_identities = sorted(
        identity
        for identity, row in matrix.items()
        if any(row.values()) and not all(row.values())
    )
    absent_identities = sorted(
        identity for identity, row in matrix.items() if not any(row.values())
    )

    n_complete = len(complete_identities)
    branch = attrition_branch(n_complete)
    analysable_units = n_complete * len(_ALL_CONDITIONS)

    receipt = {
        "schema_version": "mineocclude-experiment-iii-cohort-closure-receipt-v1",
        "stage": STAGE,
        "authority_section": "A8",
        "authority_binding": binding,
        "outcome_blind": True,
        "inputs_read": [
            "HASH_CHAIN_LEDGER",
            "PER_UNIT_DURABLE_RECEIPTS",
            "production_identity_manifest.jsonl",
        ],
        "model_outcome_consulted": False,
        "expected": {
            "normal_complete_identities": NORMAL_COMPLETE_IDENTITIES,
            "normal_units": NORMAL_COMPLETE_IDENTITIES * len(_ALL_CONDITIONS),
            "normal_rows": NORMAL_COMPLETE_IDENTITIES
            * len(_ALL_CONDITIONS)
            * TARGET_ROWS_PER_CAPTURE,
            "minimum_for_graded_inference": MINIMUM_FOR_GRADED_INFERENCE,
            "conditions_per_identity": len(_ALL_CONDITIONS),
        },
        "matrix": matrix,
        "N_complete": n_complete,
        "complete_five_way_paired_identities": complete_identities,
        "partial_identities": partial_identities,
        "absent_identities": absent_identities,
        "partial_identities_excluded_whole": True,
        "partial_conditions_used": False,
        "analysable_units": analysable_units,
        "analysable_target_rows": analysable_units * TARGET_ROWS_PER_CAPTURE,
        "attrition": branch,
        "attrition_branch": branch["branch"],
        "imputed_cells": 0,
        "dropped_conditions": [],
        "replaced_identities": [],
        "passed": n_complete >= MINIMUM_FOR_GRADED_INFERENCE,
        "next_authorized_state": NEXT_STAGE,
    }
    if not receipt["passed"]:
        receipt["blocker"] = "COHORT_INSUFFICIENT_COMPLETE_IDENTITIES"
        receipt["next_authorized_state"] = None
    return receipt
