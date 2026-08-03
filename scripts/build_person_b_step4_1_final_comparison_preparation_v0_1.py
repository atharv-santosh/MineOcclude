"""Build the non-executing final-comparison preparation package."""

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
from mineocclude.experiments.registry import formatted_json_bytes

PACKAGE = (
    ROOT
    / "docs/status/person_b_phase4_step4_1_final_comparison_execution_preparation_v0_1"
)


def main() -> None:
    documents = build_preparation_documents(ROOT)
    validate_preparation_documents(ROOT, documents)
    PACKAGE.mkdir(parents=True, exist_ok=True)
    payloads = {}
    for name, document in documents.items():
        payload = formatted_json_bytes(document)
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
        "schema_id": "person-b-step4-1-final-comparison-preparation-inventory-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    (PACKAGE / "sha256_inventory.json").write_bytes(formatted_json_bytes(inventory))


if __name__ == "__main__":
    main()
