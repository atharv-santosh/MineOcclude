"""Validate the canonical Step 4.1 final-comparison package only."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.step4_1_final_contract_v0_1 import (
    layout_macro_mean,
    max_t_adjusted_p_values,
    qualifying_layer_bands,
    validate_final_comparison_contract,
)
from scripts.build_person_b_step4_1_final_comparison_contract_v0_1 import (
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
            raise ValueError(f"byte-size mismatch: {name}")
        if hashlib.sha256(payload).hexdigest() != expected["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {name}")
    contract = json.loads((PACKAGE / "final_comparison_contract.json").read_text())
    validate_final_comparison_contract(contract)
    vectors = json.loads((PACKAGE / "deterministic_test_vectors.json").read_text())
    if layout_macro_mean(vectors["layout_macro"]["rows"]) != vectors["layout_macro"]["expected"]:
        raise ValueError("layout macro test vector mismatch")
    if max_t_adjusted_p_values(vectors["max_t"]["hypotheses"]) != vectors["max_t"]["observed_adjusted_p_values"]:
        raise ValueError("maxT test vector mismatch")
    gates = {int(key): value for key, value in vectors["qualifying_bands"]["layer_gates"].items()}
    if [list(value) for value in qualifying_layer_bands(gates)] != vectors["qualifying_bands"]["observed"]:
        raise ValueError("layer-band test vector mismatch")
    print("PERSON_B_STEP4_1_FINAL_COMPARISON_CONTRACT_VALID")


if __name__ == "__main__":
    main()
