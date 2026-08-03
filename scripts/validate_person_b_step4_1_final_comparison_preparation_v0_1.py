"""Validate the final-comparison preparation package without execution."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.step4_1_final_comparison_preparation_v0_1 import (
    build_preparation_documents,
    validate_preparation_documents,
)
from mineocclude.analysis.step4_1_final_comparison_runtime_v0_1 import (
    decode_strict_json,
)
from mineocclude.experiments.registry import formatted_json_bytes

PACKAGE = (
    ROOT
    / "docs/status/person_b_phase4_step4_1_final_comparison_execution_preparation_v0_1"
)


def validate_package() -> None:
    expected = build_preparation_documents(ROOT)
    observed = {}
    for name in expected:
        payload = (PACKAGE / name).read_bytes()
        if payload != formatted_json_bytes(expected[name]):
            raise ValueError(f"Preparation package differs at {name}.")
        observed[name] = decode_strict_json(payload, label=name)
    validate_preparation_documents(ROOT, observed)
    inventory_payload = (PACKAGE / "sha256_inventory.json").read_bytes()
    inventory = decode_strict_json(inventory_payload, label="preparation inventory")
    expected_files = {
        name: {
            "byte_size": len((PACKAGE / name).read_bytes()),
            "sha256": hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest(),
        }
        for name in sorted(expected)
    }
    if (
        inventory.get("files") != expected_files
        or inventory.get("inventory_excludes_self") is not True
    ):
        raise ValueError("Preparation inventory differs.")


def main() -> None:
    validate_package()
    print("PERSON_B_STEP4_1_FINAL_COMPARISON_PREPARATION_VALID")


if __name__ == "__main__":
    main()
