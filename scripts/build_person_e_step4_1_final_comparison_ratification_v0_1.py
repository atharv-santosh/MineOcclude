"""Build Person E's final Step 4.1 comparison and closure ratification."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.step4_1_closure_contract_v0_1 import (
    BOUNDED_REVEAL_AUTHORIZATION_COMMIT,
    build_closure_contract,
    build_final_comparison_ratification,
    build_registry_v2_import_contract,
    validate_final_ratification_package,
)
from mineocclude.experiments.step4_1_contract_review_v0_1 import (
    PERSON_B_COMPARISON_COMMIT,
    PERSON_B_POST_REVEAL_COMMIT,
    PERSON_D_COMPLETION_COMMIT,
    canonical_bytes,
)

PACKAGE = ROOT / (
    "docs/status/person_e_phase4_step4_1_final_comparison_ratification_v0_1"
)


def documents() -> dict[str, dict[str, Any]]:
    ratification = build_final_comparison_ratification(ROOT)
    closure = build_closure_contract(ROOT)
    registry = build_registry_v2_import_contract(ROOT)
    validate_final_ratification_package(
        ratification, closure, registry, repository=ROOT
    )
    return {
        "authority_binding.json": {
            "bounded_reveal_authorization_commit": BOUNDED_REVEAL_AUTHORIZATION_COMMIT,
            "person_b_comparison_contract_commit": PERSON_B_COMPARISON_COMMIT,
            "person_b_post_reveal_contract_commit": PERSON_B_POST_REVEAL_COMMIT,
            "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
            "ratification_commit_semantics": (
                "The Git commit containing this package is the final comparison "
                "ratification authority and directly descends from the bounded reveal "
                "authorization commit."
            ),
            "schema_id": "person-e-step4-1-final-ratification-authority-binding-v0-1",
            "schema_version": "1.0",
            "u4_output_inspected": False,
        },
        "closure_contract.json": closure,
        "final_comparison_ratification.json": ratification,
        "registry_v2_import_contract.json": registry,
        "validation_receipt.json": {
            "canonical_json_validated": True,
            "closure_contract_complete": True,
            "comparison_contract_complete": True,
            "exact_b_and_d_evidence_bound": True,
            "focused_validation_only": True,
            "registry_v2_import_contract_complete": True,
            "schema_id": "person-e-step4-1-final-ratification-validation-receipt-v0-1",
            "schema_version": "1.0",
            "scientific_execution_performed": False,
            "step4_1_complete": False,
            "u4_output_inspected": False,
            "unknown_versions_and_hashes_fail_closed": True,
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
        "schema_id": "person-e-step4-1-final-ratification-sha256-inventory-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    (PACKAGE / "sha256_inventory.json").write_bytes(canonical_bytes(inventory))


if __name__ == "__main__":
    main()
