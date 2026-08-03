"""Validate Person E's implementation ratification without execution."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import formatted_json_bytes
from mineocclude.experiments.step4_1_implementation_review_v0_1 import (
    build_ratification_documents,
    validate_ratification_documents,
)

PACKAGE = (
    ROOT
    / "docs/status/person_e_phase4_step4_1_final_comparison_implementation_ratification_v0_1"
)


def validate_package() -> None:
    expected = build_ratification_documents(ROOT)
    observed = {}
    for name, document in expected.items():
        payload = (PACKAGE / name).read_bytes()
        if payload != formatted_json_bytes(document):
            raise ValueError(f"Ratification package differs at {name}.")
        observed[name] = json.loads(payload)
    validate_ratification_documents(ROOT, observed)
    inventory = json.loads((PACKAGE / "sha256_inventory.json").read_bytes())
    files = {
        name: {
            "byte_size": len((PACKAGE / name).read_bytes()),
            "sha256": hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest(),
        }
        for name in sorted(expected)
    }
    if inventory.get("files") != files or inventory.get("inventory_excludes_self") is not True:
        raise ValueError("Ratification inventory differs.")


def main() -> None:
    validate_package()
    print("PERSON_E_STEP4_1_IMPLEMENTATION_RATIFICATION_VALID")


if __name__ == "__main__":
    main()
