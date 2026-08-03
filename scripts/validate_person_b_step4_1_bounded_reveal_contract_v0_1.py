"""Validate the bounded reveal package without producing predictions."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.step4_1_bounded_reveal_v0_1 import (
    build_bounded_reveal_contract,
    predict_with_raw_probe,
    validate_bounded_reveal_contract,
)
from scripts.build_person_b_step4_1_bounded_reveal_contract_v0_1 import (
    PACKAGE,
    canonical_bytes,
)


def main() -> None:
    inventory = json.loads((PACKAGE / "sha256_inventory.json").read_text())
    for name, expected in inventory["files"].items():
        payload = (PACKAGE / name).read_bytes()
        document = json.loads(payload)
        if payload != canonical_bytes(document):
            raise ValueError(f"noncanonical JSON: {name}")
        if len(payload) != expected["byte_size"]:
            raise ValueError(f"byte size mismatch: {name}")
        if hashlib.sha256(payload).hexdigest() != expected["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {name}")
    contract = json.loads((PACKAGE / "bounded_reveal_contract.json").read_text())
    validate_bounded_reveal_contract(contract)
    if contract != build_bounded_reveal_contract():
        raise ValueError("contract rebuild mismatch")
    vector = json.loads((PACKAGE / "deterministic_test_vector.json").read_text())
    values = [0.0] * 2048
    weights = [0.0] * 2048
    for item in vector["vector_nonzero_entries"]:
        values[item["index"]] = item["value"]
    for item in vector["weight_nonzero_entries"]:
        weights[item["index"]] = item["value"]
    if predict_with_raw_probe(values, weights, vector["raw_intercept"]) != vector["expected_prediction"]:
        raise ValueError("deterministic prediction vector mismatch")
    print("PERSON_B_STEP4_1_BOUNDED_REVEAL_CONTRACT_VALID")


if __name__ == "__main__":
    main()
