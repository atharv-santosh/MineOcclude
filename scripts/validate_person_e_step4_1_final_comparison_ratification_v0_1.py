"""Validate final Step 4.1 ratification without executing science."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.step4_1_closure_contract_v0_1 import (
    validate_final_ratification_package,
)
from mineocclude.experiments.step4_1_contract_review_v0_1 import canonical_bytes
from scripts.build_person_e_step4_1_final_comparison_ratification_v0_1 import (
    PACKAGE,
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
    validate_final_ratification_package(
        json.loads((PACKAGE / "final_comparison_ratification.json").read_text()),
        json.loads((PACKAGE / "closure_contract.json").read_text()),
        json.loads((PACKAGE / "registry_v2_import_contract.json").read_text()),
        repository=ROOT,
    )
    print("PERSON_E_STEP4_1_FINAL_COMPARISON_RATIFICATION_VALID")


if __name__ == "__main__":
    main()
