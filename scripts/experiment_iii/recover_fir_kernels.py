"""Reproduce the A-prime FIR kernel recovery and write the A1 receipt.

CPU only. Reads the bound git object, regenerates the 50 A-prime paths, solves
per direction, applies every acceptance gate, and re-derives all 950 labels.

    python scripts/experiment_iii/recover_fir_kernels.py [--out <path>]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import verify_authority_binding  # noqa: E402
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.extent_geometry import aprime_port_receipt  # noqa: E402
from mineocclude.experiment_iii.fir import fir_recovery_receipt  # noqa: E402
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "a1_receipts"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    try:
        binding = verify_authority_binding()
        recovery = fir_recovery_receipt() | {"authority_binding": binding}
        port = aprime_port_receipt() | {"authority_binding": binding}
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    recovery_digest = write_json_atomic(
        args.out / "fir_kernel_recovery_receipt.json", recovery
    )
    port_digest = write_json_atomic(args.out / "aprime_port_receipt.json", port)

    verification = recovery["verification"]
    print(f"FIR_RESULT={recovery['result']}")
    print(f"PATH_HASHES_REPRODUCED={verification['path_hashes_reproduced']}/50")
    print(f"LABELS_REPRODUCED={verification['labels_reproduced']}/950")
    print(f"AGGREGATE_MODE_LAG={recovery['aggregate_diagnostics']['mode_lag']}")
    print(f"FIR_RECOVERY_RECEIPT_SHA256={recovery_digest}")
    print(f"APRIME_PORT_RECEIPT_SHA256={port_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
