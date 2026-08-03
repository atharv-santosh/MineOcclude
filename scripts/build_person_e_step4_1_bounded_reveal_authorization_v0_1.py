"""Build Person E's additive bounded reveal authorization."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.step4_1_contract_review_v0_1 import (
    PERSON_B_COMPARISON_COMMIT,
    PERSON_B_POST_REVEAL_COMMIT,
    PERSON_D_COMPLETION_COMMIT,
    PERSON_E_STARTING_AUTHORITY,
    build_bounded_reveal_authorization,
    canonical_bytes,
    review_person_b_contracts,
    validate_bounded_reveal_authorization,
)

PACKAGE = ROOT / (
    "docs/status/person_e_phase4_step4_1_bounded_reveal_authorization_v0_1"
)


def documents() -> dict[str, dict[str, Any]]:
    review = review_person_b_contracts(ROOT)
    authorization = build_bounded_reveal_authorization(ROOT)
    validate_bounded_reveal_authorization(authorization, repository=ROOT)
    return {
        "authority_binding.json": {
            "authorization_commit_semantics": (
                "The Git commit containing this package is the Person E bounded reveal "
                "authority and must directly descend from person_e_starting_authority."
            ),
            "person_b_comparison_contract_commit": PERSON_B_COMPARISON_COMMIT,
            "person_b_post_reveal_contract_commit": PERSON_B_POST_REVEAL_COMMIT,
            "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
            "person_e_starting_authority": PERSON_E_STARTING_AUTHORITY,
            "schema_id": "person-e-step4-1-bounded-reveal-authority-binding-v0-1",
            "schema_version": "1.0",
            "u4_output_inspected": False,
        },
        "bounded_reveal_authorization.json": authorization,
        "independent_review.json": {
            **review,
            "ratification_decision": "PASS_AUTHORIZE_BOUNDED_REVEAL_ONLY",
            "schema_id": "person-e-step4-1-independent-contract-review-v0-1",
            "schema_version": "1.0",
            "u4_output_inspected": False,
        },
        "validation_receipt.json": {
            "bounded_reveal_authorization_complete": True,
            "canonical_json_validated": True,
            "exact_git_object_reads": True,
            "focused_validation_only": True,
            "person_b_branch_merged": False,
            "person_b_contracts_independently_validated": True,
            "post_reveal_predictions_produced": False,
            "schema_id": "person-e-step4-1-bounded-reveal-validation-receipt-v0-1",
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
        "schema_id": "person-e-step4-1-bounded-reveal-sha256-inventory-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    (PACKAGE / "sha256_inventory.json").write_bytes(canonical_bytes(inventory))


if __name__ == "__main__":
    main()
