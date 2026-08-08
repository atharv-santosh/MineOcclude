"""Build the canonical Person B bounded reveal interface package."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.step4_1_bounded_reveal_v0_1 import (
    COMPARISON_CONTRACT_COMMIT,
    PERSON_E_STARTING_AUTHORITY,
    build_bounded_reveal_contract,
    predict_with_raw_probe,
    validate_bounded_reveal_contract,
)

PACKAGE = ROOT / "docs/status/person_b_phase4_step4_1_bounded_reveal_contract_v0_1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def documents() -> dict[str, dict[str, Any]]:
    contract = build_bounded_reveal_contract()
    validate_bounded_reveal_contract(contract)
    vector = [0.0] * 2048
    vector[0] = 2.0
    weights = [0.0] * 2048
    weights[0] = 0.25
    return {
        "authority_binding.json": {
            "comparison_contract_commit": COMPARISON_CONTRACT_COMMIT,
            "person_e_starting_authority": PERSON_E_STARTING_AUTHORITY,
            "post_reveal_contract_authority_semantics": (
                "The Git commit containing this package is the post-reveal authority "
                "and must be the direct child of comparison_contract_commit."
            ),
            "schema_id": "person-b-step4-1-bounded-reveal-authority-binding-v0-1",
            "schema_version": "1.0",
            "u4_output_inspected": False,
        },
        "bounded_reveal_contract.json": contract,
        "deterministic_test_vector.json": {
            "expected_prediction": 0.625,
            "raw_intercept": 0.125,
            "observed_prediction": predict_with_raw_probe(vector, weights, 0.125),
            "schema_id": "person-b-step4-1-bounded-reveal-test-vector-v0-1",
            "schema_version": "1.0",
            "vector_nonzero_entries": [{"index": 0, "value": 2.0}],
            "weight_nonzero_entries": [{"index": 0, "value": 0.25}],
        },
        "output_schema.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
            "properties": {
                "comparison_contract_commit": {"const": COMPARISON_CONTRACT_COMMIT},
                "person_b_contract_commit": {"pattern": "^[0-9a-f]{40}$", "type": "string"},
                "person_e_authorization_commit": {"pattern": "^[0-9a-f]{40}$", "type": "string"},
                "prediction_count": {"const": 100},
                "rows": {"items": {"type": "object"}, "maxItems": 100, "minItems": 100, "type": "array"},
                "schema_id": {"const": "person-b-step4-1-bounded-reveal-predictions-v0-1"},
                "schema_version": {"const": "1.0"},
                "u4_output_inspected": {"const": False},
            },
            "required": [
                "schema_id", "schema_version", "comparison_contract_commit",
                "person_b_contract_commit", "person_e_authorization_commit",
                "prediction_count", "rows", "u4_output_inspected",
            ],
            "title": "Person B Step 4.1 bounded reveal predictions v0.1",
            "type": "object",
        },
        "validation_receipt.json": {
            "canonical_json_validated": True,
            "deterministic_prediction_vector_validated": True,
            "person_a_additional_extraction_required": False,
            "person_b_probe_refit_required": False,
            "post_reveal_input_identity_count": 5,
            "post_reveal_inputs_available": True,
            "post_reveal_prediction_count_when_executed": 100,
            "post_reveal_predictions_produced": False,
            "schema_id": "person-b-step4-1-bounded-reveal-validation-receipt-v0-1",
            "schema_version": "1.0",
            "scientific_execution_performed": False,
            "u4_output_inspected": False,
        },
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
            name: {
                "byte_size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for name, payload in sorted(payloads.items())
        },
        "inventory_excludes_self": True,
        "schema_id": "person-b-step4-1-bounded-reveal-sha256-inventory-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    (PACKAGE / "sha256_inventory.json").write_bytes(canonical_bytes(inventory))


if __name__ == "__main__":
    main()
