"""A9 — production activation extraction (authority 8.4-8.6, lifecycle A9).

125 captures, **2,375 forwards**, 750 serialized arrays.

The forward count is the thing to get right, and the easy way to get it wrong is
to run one forward per *array*. Six logical layer/slice outputs -- layers
``{4, 10, 19}`` x slices ``{PREVIOUS, CURRENT}`` -- are read from **one** hooked
teacher-forced forward per target row, so the arithmetic is

    125 captures x 19 target rows = 2,375 forwards        (not 14,250)
    125 captures x 6 units        =   750 arrays
    750 arrays x [19, 336, 2048] float16 little-endian

``EXTRACTION_FORWARD_COUNT_EXCESS`` exists precisely because 6-per-row is the
plausible mistake: it costs six times the GPU budget and, worse, six independent
forwards of the same row need not agree, so the six "layers" would no longer be
a decomposition of one model state.

This module owns **admission and roster**. The extraction loop itself is
:class:`P1ExtractionCampaign`, qualified over the P1 pilot against the real
MineWorld adapter; A9 supplies the production roster and the A9 entry gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from mineocclude.experiment_iii.activation_store import (
    EXPECTED_NPY_BYTES,
    EXPECTED_SHAPE,
    UNITS_PER_CAPTURE,
)
from mineocclude.experiment_iii.authority import (
    PILOT_IDENTITY_IDS,
    canonical_sha256,
    PRODUCTION_IDENTITY_COUNT,
    PRODUCTION_IDENTITY_IDS,
    TARGET_ROWS_PER_CAPTURE,
    machine_authority,
    verify_authority_binding,
)
from mineocclude.experiment_iii.cohort_closure import MINIMUM_FOR_GRADED_INFERENCE
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS
from mineocclude.experiment_iii.p1_extraction import (
    HOOK_SITE,
    P1ExtractionCampaign,
    refuse_production_extraction,
    token_position_hash,
)
from mineocclude.experiment_iii.schema import TemporalSlice
from mineocclude.experiment_iii.p2_freeze import (
    P2_FREEZE_SCHEMA_VERSION,
    p2_freeze_passed,
)

__all__ = [
    "A9_STAGE",
    "a9_extraction_spec_hash",
    "PRODUCTION_ARRAYS",
    "PRODUCTION_CAPTURES",
    "PRODUCTION_FORWARDS",
    "PRODUCTION_TARGET_ROWS",
    "ProductionExtractionCampaign",
    "admit_production_extraction",
    "assert_production_identity",
    "expected_extraction_counts",
]

A9_STAGE = "A9"
NEXT_STAGE = "A10"

PRODUCTION_CAPTURES = 125
PRODUCTION_TARGET_ROWS = PRODUCTION_CAPTURES * TARGET_ROWS_PER_CAPTURE  # 2,375
#: One forward per target row, and no more. Never six.
PRODUCTION_FORWARDS = PRODUCTION_TARGET_ROWS
PRODUCTION_ARRAYS = PRODUCTION_CAPTURES * UNITS_PER_CAPTURE  # 750


def expected_extraction_counts(captures: int = PRODUCTION_CAPTURES) -> dict[str, int]:
    """The frozen A9 arithmetic for ``captures`` admitted capture units."""
    return {
        "captures": captures,
        "target_rows": captures * TARGET_ROWS_PER_CAPTURE,
        "forwards": captures * TARGET_ROWS_PER_CAPTURE,
        "arrays": captures * UNITS_PER_CAPTURE,
        "units_per_capture": UNITS_PER_CAPTURE,
        "forwards_per_capture": TARGET_ROWS_PER_CAPTURE,
        "one_forward_per_target_row": True,
    }


def a9_extraction_spec_hash() -> str:
    """The identity a resumed A9 unit must still match (authority 8.6).

    Everything that would change what an array *is*: layers, slices, token
    layout, shape, dtype, byte size, the weights, and the authority under which
    they are frozen. Stage-tagged, so an A5 pilot array and an A9 production
    array can never be mistaken for the same unit on resume.
    """
    extraction = machine_authority()["extraction"]
    return canonical_sha256(
        {
            "stage": A9_STAGE,
            "authority_sha256": verify_authority_binding()["AUTHORITY_SHA256"],
            "layers": list(SELECTED_LAYERS),
            "temporal_slices": [name.value for name in TemporalSlice],
            "token_position_hash": token_position_hash(),
            "hook_site": HOOK_SITE,
            "expected_shape": list(EXPECTED_SHAPE),
            "expected_dtype": "<f2",
            "expected_npy_bytes": EXPECTED_NPY_BYTES,
            "main_checkpoint_sha256": extraction["main_checkpoint_sha256"],
            "vae_sha256": extraction["vae_sha256"],
            "one_forward_per_target_row": True,
        }
    )


def assert_production_identity(identity: str) -> None:
    """Refuse anything but ``e3_t01``..``e3_t25`` in A9.

    The mirror of ``assert_pilot_identity``. A pilot capture extracted under A9
    would enter the production activation corpus and contaminate the cohort A8
    just closed.
    """
    name = str(identity)
    if name in set(PILOT_IDENTITY_IDS):
        raise ExperimentIIIError(
            "COHORT_PILOT_CONTAMINATION",
            f"{name} is a pilot identity; A9 extracts the production cohort only, "
            f"and the pilot's activations are engineering evidence",
        )
    if name not in set(PRODUCTION_IDENTITY_IDS):
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"{name} is not one of the {PRODUCTION_IDENTITY_COUNT} frozen "
            f"production identities",
        )


def admit_production_extraction(
    *,
    p2_path: Path,
    a8_receipt_path: Path,
    a3_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """The A9 entry gate: A8 PASS, the A6 freeze binding, model authorization.

    ``refuse_production_extraction`` already refuses whenever any of the three is
    absent, and deliberately takes them as explicit arguments so no stale banked
    field can stand in for one. This function is what supplies them **from real
    evidence** rather than from an operator's say-so.
    """
    current = verify_authority_binding()

    p2 = Path(p2_path)
    if not p2.is_file():
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED", f"no P2 freeze package at {p2}"
        )
    package = json.loads(p2.read_text(encoding="utf-8"))
    if package.get("schema_version") != P2_FREEZE_SCHEMA_VERSION:
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED", f"{p2} is not a P2 freeze package"
        )
    bound = package.get("authority_binding") or {}
    if bound.get("AUTHORITY_SHA256") != current["AUTHORITY_SHA256"]:
        raise ExperimentIIIError(
            "PROVENANCE_AUTHORITY_DRIFT",
            f"the P2 package was frozen under {bound.get('AUTHORITY_SHA256')} and "
            f"this run is bound to {current['AUTHORITY_SHA256']}",
        )
    a6_freeze_bound = bool(p2_freeze_passed(package))
    model_inference_authorized = package.get("MODEL_INFERENCE_AUTHORIZED") is True

    closure = Path(a8_receipt_path)
    if not closure.is_file():
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            f"no A8 cohort closure receipt at {closure}; A9 entry is A8 == PASS",
        )
    cohort = json.loads(closure.read_text(encoding="utf-8"))
    if cohort.get("stage") != "A8":
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", f"{closure} is not an A8 receipt"
        )
    cohort_bound = (cohort.get("authority_binding") or {}).get("AUTHORITY_SHA256")
    if cohort_bound != current["AUTHORITY_SHA256"]:
        raise ExperimentIIIError(
            "PROVENANCE_AUTHORITY_DRIFT",
            f"the A8 closure was produced under {cohort_bound}, this run is bound "
            f"to {current['AUTHORITY_SHA256']}",
        )
    a8_passed = bool(cohort.get("passed"))
    n_complete = int(cohort.get("N_complete") or 0)

    # Raises unless all three A9 entry conditions hold.
    refuse_production_extraction(
        a3_receipt,
        model_inference_authorized=model_inference_authorized,
        a6_freeze_bound=a6_freeze_bound,
        a8_passed=a8_passed,
    )

    if n_complete < MINIMUM_FOR_GRADED_INFERENCE:
        raise ExperimentIIIError(
            "COHORT_INSUFFICIENT_COMPLETE_IDENTITIES",
            f"the A8 closure records N_complete={n_complete}",
        )

    stages = list(a3_receipt.get("authorized_stages") or ())
    if A9_STAGE not in stages:
        raise ExperimentIIIError(
            "ENV_GPU_UNAVAILABLE",
            f"this host's A3 receipt authorizes {stages}, not {A9_STAGE}",
        )
    checks = a3_receipt.get("model_identity_checks") or {}
    if not checks.get("verified"):
        raise ExperimentIIIError(
            "ENV_CHECKPOINT_HASH_MISMATCH",
            "the A3 receipt does not record verified MineWorld checkpoint and VAE "
            "identities; A9 will not load weights A3 never hashed",
        )
    expected = machine_authority()["extraction"]
    observed_model = (checks.get("main_checkpoint") or {}).get("observed_sha256")
    observed_vae = (checks.get("vae_checkpoint") or {}).get("observed_sha256")
    if observed_model != expected["main_checkpoint_sha256"]:
        raise ExperimentIIIError(
            "ENV_CHECKPOINT_HASH_MISMATCH",
            f"the A3 receipt records checkpoint {observed_model}, the authority "
            f"freezes {expected['main_checkpoint_sha256']}",
        )
    if observed_vae != expected["vae_sha256"]:
        raise ExperimentIIIError(
            "ENV_VAE_HASH_MISMATCH",
            f"the A3 receipt records VAE {observed_vae}, the authority freezes "
            f"{expected['vae_sha256']}",
        )

    return {
        "stage": A9_STAGE,
        "authorized": True,
        "a8_passed": a8_passed,
        "a6_freeze_bound": a6_freeze_bound,
        "model_inference_authorized": model_inference_authorized,
        "N_complete": n_complete,
        "attrition_branch": cohort.get("attrition_branch"),
        "analysable_units": int(cohort.get("analysable_units") or 0),
        "expected_counts": expected_extraction_counts(
            int(cohort.get("analysable_units") or 0)
        ),
        "checkpoint_sha256": observed_model,
        "vae_sha256": observed_vae,
        "authority_binding": current,
        "p2_package_sha256": package.get("package_sha256"),
    }


class ProductionExtractionCampaign(P1ExtractionCampaign):
    """The qualified P1 extraction loop, over the production cohort."""

    def __init__(self, units: Sequence[Mapping[str, Any]], **kwargs: Any) -> None:
        kwargs.setdefault("roster_check", assert_production_identity)
        kwargs.setdefault("stage", A9_STAGE)
        super().__init__(units, **kwargs)

    def assert_forward_budget(self) -> dict[str, int]:
        """One forward per target row across the whole campaign, and no more."""
        expected = len(self.units) * TARGET_ROWS_PER_CAPTURE
        if self.forwards > expected:
            raise ExperimentIIIError(
                "EXTRACTION_FORWARD_COUNT_EXCESS",
                f"A9 ran {self.forwards} forwards for {len(self.units)} captures; "
                f"authority 8.4 freezes exactly {expected} -- one per target row. "
                f"Six forwards per row would be {expected * UNITS_PER_CAPTURE}",
            )
        return {"forwards": self.forwards, "expected_forwards": expected}
