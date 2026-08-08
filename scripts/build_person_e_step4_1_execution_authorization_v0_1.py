"""Build the non-executing Person E Step 4.1 execution authorization."""

from __future__ import annotations

import hashlib
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


def main() -> None:
    documents = build_authorization_documents(ROOT)
    validate_authorization_documents(ROOT, documents)
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
        "schema_id": "person-e-step4-1-execution-authorization-inventory-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    (PACKAGE / "sha256_inventory.json").write_bytes(formatted_json_bytes(inventory))


if __name__ == "__main__":
    main()
