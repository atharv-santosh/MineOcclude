"""Validate Person E bounded reveal authorization and exact B objects."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.step4_1_contract_review_v0_1 import (
    canonical_bytes,
    review_person_b_contracts,
    validate_bounded_reveal_authorization,
)
from scripts.build_person_e_step4_1_bounded_reveal_authorization_v0_1 import (
    PACKAGE,
)


def main() -> None:
    review_person_b_contracts(ROOT)
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
    authorization = json.loads(
        (PACKAGE / "bounded_reveal_authorization.json").read_text()
    )
    validate_bounded_reveal_authorization(authorization, repository=ROOT)
    print("PERSON_E_STEP4_1_BOUNDED_REVEAL_AUTHORIZATION_VALID")


if __name__ == "__main__":
    main()
