"""Validate Person E's Step 4.1 execution authorization without execution."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import formatted_json_bytes
from mineocclude.experiments.step4_1_execution_authorization_v0_1 import (
    build_authorization_documents,
    validate_authorization_documents,
)

PACKAGE = (
    ROOT
    / "docs/status/person_e_phase4_step4_1_final_comparison_execution_authorization_v0_1"
)


def validate_package() -> None:
    expected = build_authorization_documents(ROOT)
    observed = {}
    for name, document in expected.items():
        payload = (PACKAGE / name).read_bytes()
        if payload != formatted_json_bytes(document):
            raise ValueError(f"Execution authorization package differs at {name}.")
        observed[name] = json.loads(payload)
    validate_authorization_documents(ROOT, observed)
    inventory = json.loads((PACKAGE / "sha256_inventory.json").read_bytes())
    files = {
        name: {
            "byte_size": len((PACKAGE / name).read_bytes()),
            "sha256": hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest(),
        }
        for name in sorted(expected)
    }
    if inventory.get("files") != files or inventory.get("inventory_excludes_self") is not True:
        raise ValueError("Execution authorization inventory differs.")


def main() -> None:
    validate_package()
    print("PERSON_E_STEP4_1_EXECUTION_AUTHORIZATION_VALID")


if __name__ == "__main__":
    main()
