#!/usr/bin/env python3
"""Validate Person B's exact signed Step 4.1 production fold authority."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.probes.production_fold_contract_v0_1 import (
    PRODUCTION_FOLD_CONTRACT_VERSION,
    ProductionFoldContractError,
    validate_fold_target_binding_bytes,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fold-manifest", required=True, type=Path)
    parser.add_argument("--target-manifest", required=True, type=Path)
    parser.add_argument(
        "--contract-version",
        default=PRODUCTION_FOLD_CONTRACT_VERSION,
    )
    args = parser.parse_args()
    try:
        fold, _target = validate_fold_target_binding_bytes(
            args.fold_manifest.read_bytes(),
            args.target_manifest.read_bytes(),
            contract_version=args.contract_version,
        )
    except (OSError, ProductionFoldContractError) as error:
        print(f"ERROR={error}")
        print("PERSON_B_STEP4_1_PRODUCTION_FOLD_CONTRACT_VALID=False")
        return 1
    print(f"FOLD_CONTRACT_VERSION={PRODUCTION_FOLD_CONTRACT_VERSION}")
    print(f"ADMITTED_ROW_COUNT={len(fold['memberships'])}")
    print("AUTHORITATIVE_VALIDATION_MODE=signed-explicit-mapping")
    print("PERSON_B_STEP4_1_PRODUCTION_FOLD_CONTRACT_VALID=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
