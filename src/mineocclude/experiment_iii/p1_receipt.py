"""The A5 exit evidence: ``p1_pilot_receipt.json`` (authority 6A, A5).

A5's exit condition is literally ``p1_pilot_receipt.json == PASS``, and its pass
condition is ``EVERY_VERIFICATION_ITEM_PROVEN_WITH_ITS_OBSERVED_VALUE`` -- not
asserted, *proven*, with the value that was observed. So this module builds the
receipt out of evidence it reads and re-derives, and refuses to write a PASS for
any item whose evidence it could not find.

**P1 spans two implementation checkpoints, and the receipt says so.** The ten
capture units were produced by the capture host at one implementation identity;
the 190 forwards and 60 arrays are produced by the extraction host at another,
because the GPU path had to be repaired before it could run at all. Both are
recorded, separately and by name. Collapsing them into one "the" checkpoint
would be a false provenance claim about bytes that already exist on disk.

**Pilot outcomes are not inputs.** Authority 6A permits inspecting pilot
predictive accuracy *only* to confirm the analysis code produces finite numbers,
and forbids it informing any scientific choice. Nothing in this module reads a
decoding result, an accuracy, or any pilot outcome; the gate is engineering
qualification and counts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from mineocclude.experiment_iii.activation_store import (
    EXPECTED_DTYPE,
    EXPECTED_NPY_BYTES,
    EXPECTED_SHAPE,
    UNITS_PER_CAPTURE,
    validate_extraction_inventory,
)
from mineocclude.experiment_iii.authority import (
    AUTHORITY_FREEZE_COMMIT,
    AUTHORITY_VERSION,
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_IDS,
    TARGET_ROWS_PER_CAPTURE,
    canonical_sha256,
    machine_authority,
    sha256_file,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.execution import HashChainLedger
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS
from mineocclude.experiment_iii.host_preflight import A5_EXTRACTION_STAGE
from mineocclude.experiment_iii.p1_extraction import (
    CANONICAL_INVENTORY_NAME,
    HOOK_SITE,
    PILOT_ARRAYS,
    PILOT_CAPTURES,
    PILOT_FORWARDS,
    PILOT_TARGET_ROWS,
)
from mineocclude.experiment_iii.schema import TemporalSlice
from mineocclude.experiment_iii.slices import verify_slice_arithmetic

__all__ = [
    "P1_RECEIPT_SCHEMA_VERSION",
    "REQUIRED_BINDINGS",
    "build_p1_pilot_receipt",
    "p1_full_pass",
]

P1_RECEIPT_SCHEMA_VERSION = "mineocclude-experiment-iii-p1-pilot-receipt-v1"

#: Every binding the A5 exit gate requires before it will return PASS. A missing
#: one is ``P1_INCOMPLETE``; none may be null.
REQUIRED_BINDINGS = (
    "authority",
    "p0_selection_receipt",
    "p1_plan",
    "p1_local_capture",
    "p1_resume_receipt",
    "capture_implementation",
    "capture_host_a3",
    "extraction_implementation",
    "extraction_host_a3",
    "model_identity",
    "target_rows",
    "forward_ledger",
    "array_inventory",
    "physical_array_validation",
    "semantic_frame_validation",
    "one_forward_validation",
    "durability",
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require(path: Path, binding: str, blocker: str = "P1_INCOMPLETE") -> Path:
    path = Path(path)
    if not path.is_file():
        raise ExperimentIIIError(
            blocker, f"the {binding} binding needs {path}, which is absent"
        )
    return path


# --------------------------------------------------------------------------
# The individual bindings
# --------------------------------------------------------------------------


def _capture_binding(
    captures_root: Path, ledger_path: Path, plan: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The ten local capture units and the implementation that produced them.

    Read from the units' own durable receipts and the hash-chained capture
    ledger, never from a summary: the ledger is re-verified here, and the
    closure recorded in it is the capture-side implementation identity.
    """
    ledger = HashChainLedger(_require(ledger_path, "p1_local_capture"))
    ledger.verify_chain()
    complete = ledger.complete_units()

    units: list[dict[str, Any]] = []
    total_rows = 0
    for planned in plan["units"]:
        unit_id = str(planned["capture_unit_id"])
        unit_dir = Path(captures_root) / unit_id
        completion = _json(_require(unit_dir / "capture_completion.json", unit_id))
        durable = _json(_require(unit_dir / "durable_receipt.json", unit_id))
        rows = [int(value) for value in completion["target_model_frame_indices"]]
        if len(rows) != TARGET_ROWS_PER_CAPTURE:
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH",
                f"{unit_id} banks {len(rows)} target rows, the authority freezes "
                f"{TARGET_ROWS_PER_CAPTURE}",
            )
        total_rows += len(rows)
        units.append(
            {
                "capture_unit_id": unit_id,
                "identity": str(completion["identity"]),
                "condition_id": str(completion["condition_id"]),
                "spec_sha256": str(completion["spec_sha256"]),
                "target_model_frame_indices": rows,
                "ledger_state": ledger.last_state(unit_id),
                "complete": unit_id in complete,
                "durable_file_count": int(durable["file_count"]),
                "durable_total_bytes": int(durable["total_bytes"]),
                "durable_readback_verified": bool(durable["readback_verified"]),
            }
        )

    identities = sorted({unit["identity"] for unit in units})
    closures = sorted(
        {
            str(record["source_closure"])
            for record in ledger.records
            if record.get("source_closure")
        }
    )
    capture = {
        "captures_expected": PILOT_CAPTURES,
        "captures_complete": len([unit for unit in units if unit["complete"]]),
        "target_rows_total": total_rows,
        "identities": identities,
        "pilot_identities_only": set(identities) <= set(PILOT_IDENTITY_IDS),
        "production_identities_used": bool(
            set(identities) & set(PRODUCTION_IDENTITY_IDS)
        ),
        "ledger_chain_verified": True,
        "ledger_record_count": len(ledger.records),
        "units": units,
    }
    implementation = {
        "role": "LOCAL_CAPTURE_HOST",
        "produced": "the ten P1 capture units and their 190 target rows",
        "source_closure": closures[0] if len(closures) == 1 else None,
        "source_closures_observed": closures,
        "single_closure": len(closures) == 1,
    }
    return capture, implementation


def _extraction_binding(
    activations_root: Path, plan: Mapping[str, Any]
) -> dict[str, Any]:
    """The 60 arrays, revalidated from their bytes, plus the forward ledger.

    ``validate_extraction_inventory`` re-reads every array and re-derives shape,
    dtype, byte size, finiteness and SHA-256 rather than trusting the inventory,
    so a receipt built here cannot pass on an inventory that merely claims the
    right numbers.
    """
    expected_checkpoint = str(
        machine_authority()["extraction"]["main_checkpoint_sha256"]
    )
    captures: list[dict[str, Any]] = []
    arrays = 0
    forwards = 0
    forward_rows: list[dict[str, Any]] = []
    for planned in plan["units"]:
        unit_id = str(planned["capture_unit_id"])
        root = Path(activations_root) / unit_id
        inventory_path = _require(
            root / CANONICAL_INVENTORY_NAME,
            "array_inventory",
            "EXTRACTION_INVENTORY_INCOMPLETE",
        )
        inventory = _json(inventory_path)
        rows = [int(value) for value in inventory["target_model_frame_indices"]]
        # The checkpoint identity every array binds is compared against the
        # AUTHORITY, not merely against its own inventory. Checking an inventory
        # against itself would accept six arrays that agreed with each other on
        # the wrong model.
        bound_checkpoint = str(inventory["artifacts"][0]["checkpoint_identity"])
        if bound_checkpoint != expected_checkpoint:
            raise ExperimentIIIError(
                "ENV_CHECKPOINT_HASH_MISMATCH",
                f"{unit_id} binds checkpoint {bound_checkpoint}; the authority "
                f"freezes {expected_checkpoint}",
            )
        validated = validate_extraction_inventory(
            root,
            inventory,
            expected_target_rows=rows,
            source_capture_hash=inventory.get("source_capture_hash"),
            checkpoint_identity=bound_checkpoint,
            preprocessing_identity=(
                inventory["artifacts"][0]["preprocessing_identity"]
            ),
        )
        ledger_rows = list(inventory.get("forward_ledger") or [])
        if len(ledger_rows) != len(rows):
            raise ExperimentIIIError(
                "EXTRACTION_FORWARD_COUNT_EXCESS",
                f"{unit_id} records {len(ledger_rows)} forwards for {len(rows)} "
                "target rows; authority 8.4 authorizes exactly one per row",
            )
        if [int(row["target_model_frame_idx"]) for row in ledger_rows] != rows:
            raise ExperimentIIIError(
                "EXTRACTION_TEMPORAL_INDEX_MISMATCH",
                f"{unit_id} forward ledger does not follow the frozen target rows",
            )
        arrays += len(validated)
        forwards += int(inventory["forwards"])
        forward_rows.extend(ledger_rows)
        captures.append(
            {
                "capture_unit_id": unit_id,
                "inventory_sha256": inventory["inventory_sha256"],
                "inventory_path": (
                    f"{unit_id}/{CANONICAL_INVENTORY_NAME}"
                ),
                "arrays_validated": len(validated),
                "forwards": int(inventory["forwards"]),
                "target_model_frame_indices": rows,
                "hook_site": inventory["artifacts"][0]["hook_site"],
                "token_position_hash": (
                    inventory["artifacts"][0]["token_position_hash"]
                ),
            }
        )
    return {
        "captures": captures,
        "arrays_expected": PILOT_ARRAYS,
        "arrays_validated": arrays,
        "forwards_expected": PILOT_FORWARDS,
        "forwards_recorded": forwards,
        "forward_ledger_rows": len(forward_rows),
        "shared_forward_set_per_capture": TARGET_ROWS_PER_CAPTURE,
        "logical_row_tensors": forwards * len(SELECTED_LAYERS) * len(TemporalSlice),
    }


def _model_binding(a3_receipt: Mapping[str, Any]) -> dict[str, Any]:
    """The checkpoint and VAE the extraction host hashed, checked again here."""
    expected = machine_authority()["extraction"]
    checks = a3_receipt.get("model_identity_checks") or {}
    if not checks.get("verified"):
        raise ExperimentIIIError(
            "ENV_CHECKPOINT_HASH_MISMATCH",
            "the extraction-host A3 receipt records no verified model identity",
        )
    observed = {
        "main_checkpoint_sha256": (checks["main_checkpoint"]["observed_sha256"]),
        "vae_sha256": checks["vae_checkpoint"]["observed_sha256"],
    }
    for field, blocker in (
        ("main_checkpoint_sha256", "ENV_CHECKPOINT_HASH_MISMATCH"),
        ("vae_sha256", "ENV_VAE_HASH_MISMATCH"),
    ):
        if observed[field] != expected[field]:
            raise ExperimentIIIError(
                blocker,
                f"the receipt records {field} {observed[field]}, the authority "
                f"freezes {expected[field]}",
            )
    return {
        "model": expected["model"],
        "main_checkpoint_sha256": observed["main_checkpoint_sha256"],
        "main_checkpoint_path": checks["main_checkpoint"]["path"],
        "vae_sha256": observed["vae_sha256"],
        "vae_path": checks["vae_checkpoint"]["path"],
        "preprocessing_change_allowed": bool(
            expected["preprocessing_change_allowed"]
        ),
        "verified_on_extraction_host": True,
    }


# --------------------------------------------------------------------------
# The receipt
# --------------------------------------------------------------------------


def build_p1_pilot_receipt(
    *,
    plan_path: Path,
    captures_root: Path,
    capture_ledger_path: Path,
    activations_root: Path,
    p0_selection_receipt_path: Path,
    resume_receipt_path: Path,
    capture_host_a3_path: Path,
    extraction_host_a3_path: Path,
    extraction_implementation: Mapping[str, Any],
    analysis_smoke: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind the whole P1 chain and decide A5's exit, from evidence only."""
    binding = verify_authority_binding()
    plan = _json(_require(plan_path, "p1_plan"))
    selection = _json(_require(p0_selection_receipt_path, "p0_selection_receipt"))
    resume = _json(_require(resume_receipt_path, "p1_resume_receipt"))
    capture_a3 = _json(_require(capture_host_a3_path, "capture_host_a3"))
    extraction_a3 = _json(_require(extraction_host_a3_path, "extraction_host_a3"))

    capture, capture_implementation = _capture_binding(
        captures_root, capture_ledger_path, plan
    )
    capture_implementation["checkpoint_commit"] = str(
        capture_a3.get("implementation_checkpoint_commit") or ""
    ) or None
    extraction = _extraction_binding(activations_root, plan)
    model = _model_binding(extraction_a3)

    if A5_EXTRACTION_STAGE not in list(extraction_a3.get("authorized_stages") or []):
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            "the extraction-host A3 receipt does not authorize A5_EXTRACTION",
        )

    bindings: dict[str, Any] = {
        "authority": {
            "version": AUTHORITY_VERSION,
            "authority_sha256": binding["AUTHORITY_SHA256"],
            "machine_authority_sha256": binding["MACHINE_AUTHORITY_SHA256"],
            "phase0_design_sha256": binding["PHASE0_DESIGN_SHA256"],
            "authority_freeze_commit": AUTHORITY_FREEZE_COMMIT,
        },
        "p0_selection_receipt": {
            "path": Path(p0_selection_receipt_path).as_posix(),
            "sha256": sha256_file(Path(p0_selection_receipt_path)),
            "P0_RESULT": selection.get("P0_RESULT"),
        },
        "p1_plan": {
            "path": Path(plan_path).as_posix(),
            "sha256": sha256_file(Path(plan_path)),
            "captures": int(plan["captures"]),
            "expected_model_forwards": int(plan["expected_model_forwards"]),
            "expected_serialized_arrays": int(plan["expected_serialized_arrays"]),
        },
        "p1_local_capture": capture,
        "p1_resume_receipt": {
            "path": Path(resume_receipt_path).as_posix(),
            "sha256": sha256_file(Path(resume_receipt_path)),
            "P1_RESUME_DEMONSTRATION": resume.get("P1_RESUME_DEMONSTRATION"),
        },
        # The two implementation identities P1 actually spans. Recorded
        # separately because they are separately true.
        "capture_implementation": capture_implementation,
        "extraction_implementation": {
            "role": "GPU_EXTRACTION_HOST",
            "produced": "the 190 forwards and the 60 persisted arrays",
            **dict(extraction_implementation),
        },
        "capture_host_a3": {
            "path": Path(capture_host_a3_path).as_posix(),
            "sha256": sha256_file(Path(capture_host_a3_path)),
            "host_role": capture_a3.get("host_role"),
            "authorized_stages": list(capture_a3.get("authorized_stages") or []),
            "passed": bool(capture_a3.get("passed")),
        },
        "extraction_host_a3": {
            "path": Path(extraction_host_a3_path).as_posix(),
            "sha256": sha256_file(Path(extraction_host_a3_path)),
            "host_role": extraction_a3.get("host_role"),
            "authorized_stages": list(extraction_a3.get("authorized_stages") or []),
            "passed": bool(extraction_a3.get("passed")),
        },
        "model_identity": model,
        "target_rows": {
            "per_capture": TARGET_ROWS_PER_CAPTURE,
            "expected_total": PILOT_TARGET_ROWS,
            "observed_total": capture["target_rows_total"],
        },
        "forward_ledger": {
            "expected": PILOT_FORWARDS,
            "observed": extraction["forwards_recorded"],
            "rows": extraction["forward_ledger_rows"],
            "one_forward_per_target_row": True,
            "extra_forward_authorized": False,
        },
        "array_inventory": {
            "expected": PILOT_ARRAYS,
            "observed": extraction["arrays_validated"],
            "units_per_capture": UNITS_PER_CAPTURE,
            "inventory_name": CANONICAL_INVENTORY_NAME,
            "captures": extraction["captures"],
        },
        "physical_array_validation": {
            "revalidated_from_bytes": True,
            "expected_shape": list(EXPECTED_SHAPE),
            "expected_dtype": EXPECTED_DTYPE,
            "expected_byte_size": EXPECTED_NPY_BYTES,
            "arrays_validated": extraction["arrays_validated"],
        },
        "semantic_frame_validation": {
            "hook_site": HOOK_SITE,
            "layers": list(SELECTED_LAYERS),
            "temporal_slices": [name.value for name in TemporalSlice],
            "slice_arithmetic": verify_slice_arithmetic(),
            "assertions": list(machine_authority()["extraction"]["semantic_assertions"]),
            "shape_agreement_is_insufficient_evidence": True,
        },
        "one_forward_validation": {
            "forwards": extraction["forwards_recorded"],
            "logical_row_tensors": extraction["logical_row_tensors"],
            "layers_per_forward": len(SELECTED_LAYERS),
            "slices_per_forward": len(TemporalSlice),
            "forward_count_excess_blocker": "EXTRACTION_FORWARD_COUNT_EXCESS",
        },
        "durability": {
            "capture_units_durable": len(
                [
                    unit
                    for unit in capture["units"]
                    if unit["durable_readback_verified"]
                ]
            ),
            "capture_units_expected": PILOT_CAPTURES,
            "arrays_durable": extraction["arrays_validated"],
            "arrays_expected": PILOT_ARRAYS,
        },
    }

    checks = _verification_checks(bindings, capture, extraction, model, resume)
    failures = [name for name, entry in checks.items() if not entry["passed"]]
    missing = [name for name in REQUIRED_BINDINGS if bindings.get(name) in (None, {})]

    body: dict[str, Any] = {
        "schema_version": P1_RECEIPT_SCHEMA_VERSION,
        "authority_section": "6A, A5",
        "stage": "A5",
        "next_authorized_state": "A6",
        "authority_version": AUTHORITY_VERSION,
        "authority_binding": binding,
        "bindings": bindings,
        "verification_items": checks,
        "missing_bindings": missing,
        "failed_items": failures,
        "pilot_outcomes_consulted": False,
        "pilot_outcome_note": (
            "authority 6A permits inspecting pilot predictive accuracy only to "
            "confirm the analysis code produces finite numbers; no pilot outcome "
            "is an input to this gate"
        ),
        "analysis_smoke": dict(analysis_smoke) if analysis_smoke else None,
        "P1_FULL_PASS": not failures and not missing,
        "P1_RESULT": "PASS" if not failures and not missing else "FAIL",
        "PRODUCTION_AUTHORIZED": False,
        "MODEL_INFERENCE_AUTHORIZED": False,
        "P2_EXECUTED": False,
    }
    body["receipt_sha256"] = canonical_sha256(body)
    return body


def _verification_checks(
    bindings: Mapping[str, Any],
    capture: Mapping[str, Any],
    extraction: Mapping[str, Any],
    model: Mapping[str, Any],
    resume: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Each A5 pass condition with the value that was observed for it."""

    def check(expected: Any, observed: Any, why: str) -> dict[str, Any]:
        return {
            "expected": expected,
            "observed": observed,
            "passed": expected == observed,
            "requirement": why,
        }

    expected_model = machine_authority()["extraction"]
    return {
        "ten_local_captures_complete": check(
            PILOT_CAPTURES, capture["captures_complete"], "A5 expected_counts.captures"
        ),
        "one_hundred_ninety_target_rows": check(
            PILOT_TARGET_ROWS,
            capture["target_rows_total"],
            "A5 expected_counts.target_rows",
        ),
        "pilot_identities_only": check(
            True, capture["pilot_identities_only"], "authority 6A pilot roster"
        ),
        "no_production_identity_spent": check(
            False,
            capture["production_identities_used"],
            "authority 2.1 forbids identity replacement",
        ),
        "capture_ledger_chain_verified": check(
            True, capture["ledger_chain_verified"], "authority 8.3 hash chain"
        ),
        "capture_host_a3_pass": check(
            True, bindings["capture_host_a3"]["passed"], "A5 entry: A3 on capture host"
        ),
        "extraction_host_a3_pass": check(
            True,
            bindings["extraction_host_a3"]["passed"],
            "A5 entry: A3 on extraction host",
        ),
        "extraction_host_authorizes_a5_extraction": check(
            True,
            A5_EXTRACTION_STAGE in bindings["extraction_host_a3"]["authorized_stages"],
            "A5's extraction half needs its own authorized stage",
        ),
        "checkpoint_identity_verified": check(
            expected_model["main_checkpoint_sha256"],
            model["main_checkpoint_sha256"],
            "A3 VERIFY_CHECKPOINT_SHA256",
        ),
        "vae_identity_verified": check(
            expected_model["vae_sha256"], model["vae_sha256"], "A3 VERIFY_VAE_SHA256"
        ),
        "one_hundred_ninety_forwards": check(
            PILOT_FORWARDS, extraction["forwards_recorded"], "A5 expected_counts.forwards"
        ),
        "forward_ledger_complete": check(
            PILOT_FORWARDS,
            extraction["forward_ledger_rows"],
            "one ledger row per authorized forward",
        ),
        "sixty_arrays_complete": check(
            PILOT_ARRAYS,
            extraction["arrays_validated"],
            "A5 expected_counts.serialized_npy_arrays",
        ),
        "logical_row_tensors": check(
            PILOT_FORWARDS * len(SELECTED_LAYERS) * len(TemporalSlice),
            extraction["logical_row_tensors"],
            "A5 expected_counts.logical_row_tensors",
        ),
        "physical_array_validation": check(
            PILOT_ARRAYS,
            bindings["physical_array_validation"]["arrays_validated"],
            "authority 8.5 revalidation from bytes",
        ),
        "capture_durability_complete": check(
            PILOT_CAPTURES,
            bindings["durability"]["capture_units_durable"],
            "A5 durable publish and read-back",
        ),
        "array_durability_complete": check(
            PILOT_ARRAYS,
            bindings["durability"]["arrays_durable"],
            "A5 durable publish and read-back",
        ),
        "resume_demonstrated": check(
            "PASS",
            resume.get("P1_RESUME_DEMONSTRATION"),
            "A5 pass condition: mid-run kill and restart resumes same-spec",
        ),
        "dual_checkpoint_provenance_recorded": check(
            True,
            bool(bindings["capture_implementation"].get("source_closure"))
            and bool(bindings["extraction_implementation"].get("source_closure")),
            "P1 spans two implementation identities and both must be named",
        ),
    }


def p1_full_pass(receipt: Mapping[str, Any]) -> bool:
    """Whether a built receipt is an A5 exit. Counts only; no pilot outcome."""
    return bool(
        receipt.get("P1_FULL_PASS")
        and receipt.get("P1_RESULT") == "PASS"
        and not receipt.get("failed_items")
        and not receipt.get("missing_bindings")
    )
