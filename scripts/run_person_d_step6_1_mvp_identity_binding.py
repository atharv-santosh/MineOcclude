"""Person D Step 6.1: build the real 66-trajectory MVP input manifest.

Reads Person C's two real MVP-collection artifacts from local paths
(materialized copies of the exact bytes committed on
``role/person-c-data`` at ``mvp_identity_v0_1.PERSON_C_MVP_COLLECTION_COMMIT``
-- this script never fetches Git history itself), validates their
literal identity and bijective reconciliation, and writes Person D's
canonical MVP input manifest: the identity hash plus count table Step
6.1's pass check requires.

Usage:
  python scripts/run_person_d_step6_1_mvp_identity_binding.py \\
      --mvp-matrix-path /path/to/mvp_matrix.csv \\
      --pilot-ledger-path /path/to/pilot_production_ledger.json \\
      --output-path docs/status/person_d_phase6_step6_1_mvp_identity_binding_v0_1/mvp_input_manifest.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.baselines.mvp_identity_v0_1 import (
    MvpIdentityError,
    build_mvp_input_manifest,
)
from mineocclude.experiments.registry import formatted_json_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mvp-matrix-path", type=Path, required=True)
    parser.add_argument("--pilot-ledger-path", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    args = parser.parse_args(argv)

    matrix_payload = args.mvp_matrix_path.read_bytes()
    ledger_payload = args.pilot_ledger_path.read_bytes()

    try:
        manifest = build_mvp_input_manifest(matrix_payload, ledger_payload)
    except MvpIdentityError as error:
        print(f"MVP identity binding failed closed: {error}", file=sys.stderr)
        return 1

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_bytes(formatted_json_bytes(manifest))

    print(
        f"reconciliation_complete={manifest['reconciliation_complete']} "
        f"total={manifest['count_table']['total_count']} "
        f"set_counts={manifest['count_table']['set_counts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
