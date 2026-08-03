"""Build the canonical, non-scientific Step 4.1 comparison package."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.step4_1_final_contract_v0_1 import (
    PERSON_B_STARTING_AUTHORITY,
    PERSON_D_COMPLETION_COMMIT,
    PERSON_E_STARTING_AUTHORITY,
    build_final_comparison_contract,
    layout_macro_mean,
    max_t_adjusted_p_values,
    qualifying_layer_bands,
    validate_final_comparison_contract,
)

PACKAGE = ROOT / "docs/status/person_b_phase4_step4_1_final_comparison_contract_v0_1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def documents() -> dict[str, dict[str, Any]]:
    contract = build_final_comparison_contract()
    validate_final_comparison_contract(contract)
    hypotheses = {
        "layer_00_last_seen": {
            "layout_00": 0.5,
            "layout_01": 0.2,
            "layout_02": 0.4,
            "layout_03": -0.1,
            "layout_04": 0.3,
        },
        "layer_01_last_seen": {
            "layout_00": 0.6,
            "layout_01": 0.3,
            "layout_02": 0.5,
            "layout_03": 0.1,
            "layout_04": 0.4,
        },
    }
    layer_gates = {layer: layer in {2, 3, 4, 8} for layer in range(20)}
    vectors = {
        "layout_macro": {
            "expected": 5.5,
            "rows": [
                {"layout_id": "a", "trajectory_id": "a1", "value": 1.0},
                {"layout_id": "a", "trajectory_id": "a1", "value": 3.0},
                {"layout_id": "b", "trajectory_id": "b1", "value": 9.0},
            ],
            "observed": layout_macro_mean(
                [
                    {"layout_id": "a", "trajectory_id": "a1", "value": 1.0},
                    {"layout_id": "a", "trajectory_id": "a1", "value": 3.0},
                    {"layout_id": "b", "trajectory_id": "b1", "value": 9.0},
                ]
            ),
        },
        "max_t": {
            "hypotheses": hypotheses,
            "observed_adjusted_p_values": max_t_adjusted_p_values(hypotheses),
            "permutation_count": 999,
            "seed": 20260720,
        },
        "qualifying_bands": {
            "layer_gates": {str(key): value for key, value in layer_gates.items()},
            "observed": [list(band) for band in qualifying_layer_bands(layer_gates)],
        },
        "schema_id": "person-b-step4-1-final-comparison-test-vectors-v0-1",
        "schema_version": "1.0",
    }
    authority = {
        "contract_authority_semantics": (
            "The Git commit containing this package is the contract authority and "
            "must be the direct child of person_b_starting_authority."
        ),
        "person_b_starting_authority": PERSON_B_STARTING_AUTHORITY,
        "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
        "person_d_completion_manifest_sha256": (
            "79c49e7c794f37c4a574dfef365b8183ddb443b246adbe94743dfdf1ff1f4cf5"
        ),
        "person_e_starting_authority": PERSON_E_STARTING_AUTHORITY,
        "schema_id": "person-b-step4-1-final-comparison-authority-binding-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    output_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "properties": {
            "decision": {"enum": ["PASS", "FAIL", "INCONCLUSIVE"]},
            "direct_input_sha256s": {
                "additionalProperties": {"pattern": "^[0-9a-f]{64}$", "type": "string"},
                "minProperties": 1,
                "type": "object",
            },
            "layer_bands": {
                "items": {"items": {"maximum": 19, "minimum": 0, "type": "integer"}, "minItems": 2, "type": "array"},
                "type": "array",
            },
            "metric_records": {"items": {"type": "object"}, "type": "array"},
            "paired_test_records": {"items": {"type": "object"}, "type": "array"},
            "schema_id": {"const": "person-b-step4-1-final-comparison-output-v0-1"},
            "schema_version": {"const": "1.0"},
            "scientific_execution_performed": {"const": True},
            "u4_output_inspected": {"const": False},
        },
        "required": [
            "schema_id",
            "schema_version",
            "decision",
            "direct_input_sha256s",
            "metric_records",
            "paired_test_records",
            "layer_bands",
            "scientific_execution_performed",
            "u4_output_inspected",
        ],
        "title": "Person B Step 4.1 final comparison output v0.1",
        "type": "object",
    }
    validation = {
        "canonical_json_validated": True,
        "comparison_contract_complete": True,
        "deterministic_test_vectors_present": True,
        "focused_validation_only": True,
        "no_post_hoc_degree_of_freedom_check": True,
        "post_reveal_predictions_produced": False,
        "schema_id": "person-b-step4-1-final-comparison-validation-receipt-v0-1",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "u4_output_inspected": False,
        "unresolved_scientific_choice_count": 0,
    }
    return {
        "authority_binding.json": authority,
        "deterministic_test_vectors.json": vectors,
        "final_comparison_contract.json": contract,
        "output_schema.json": output_schema,
        "validation_receipt.json": validation,
    }


def main() -> None:
    PACKAGE.mkdir(parents=True, exist_ok=True)
    payloads = {}
    for name, document in documents().items():
        payload = canonical_bytes(document)
        (PACKAGE / name).write_bytes(payload)
        payloads[name] = payload
    inventory = {
        "algorithm": "sha256",
        "files": {
            name: {"byte_size": len(payload), "sha256": _sha256(payload)}
            for name, payload in sorted(payloads.items())
        },
        "inventory_excludes_self": True,
        "schema_id": "person-b-step4-1-final-comparison-sha256-inventory-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    (PACKAGE / "sha256_inventory.json").write_bytes(canonical_bytes(inventory))


if __name__ == "__main__":
    main()
