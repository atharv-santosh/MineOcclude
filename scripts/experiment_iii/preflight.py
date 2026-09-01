"""A3 -- ENVIRONMENT_PREFLIGHT entrypoint (lifecycle ``source_files_entrypoints``).

Runs every A3 check applicable to one host and writes that host's
``environment_receipt_<host>.json``. The receipt names the stages the host
authorizes; a capture-only host never authorizes ``A5_EXTRACTION``/``A9``/
``A10``, because it holds no MineWorld weights and this program will not
fabricate a check it cannot run.

    python scripts/experiment_iii/preflight.py --host-role LOCAL_CAPTURE_HOST

The extraction host must name the weights it will load, because A3 hashes them
rather than recording a literal:

    python scripts/experiment_iii/preflight.py \
        --host-role GPU_EXTRACTION_HOST \
        --main-checkpoint <path to the MineWorld 700M_16f checkpoint> \
        --vae-checkpoint <path to the VAE checkpoint>

Fails closed: a refused check exits non-zero with its frozen blocker code and
writes no receipt.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.capture_runtime import RuntimeConfig  # noqa: E402
from mineocclude.experiment_iii.host_preflight import (  # noqa: E402
    HostRole,
    environment_receipt,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.storage_preflight import GIB  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "receipts"
FABRIC_PROJECT = REPOSITORY_ROOT / "fabric" / "mineocclude-mod"
DEFAULT_MOD_JAR = FABRIC_PROJECT / "build" / "libs" / "mineocclude-0.1.1.jar"


def _head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host-role",
        default=HostRole.LOCAL_CAPTURE_HOST,
        choices=[HostRole.LOCAL_CAPTURE_HOST, HostRole.GPU_EXTRACTION_HOST],
    )
    parser.add_argument("--host-id", default=None, help="receipt filename suffix")
    parser.add_argument("--working", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--durable", type=Path, default=REPOSITORY_ROOT / "data")
    parser.add_argument("--scratch", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--runtime-root", type=Path, default=None)
    parser.add_argument("--mod-jar", type=Path, default=DEFAULT_MOD_JAR)
    parser.add_argument("--durability-mode", default="LOCAL_MIRROR_SAME_POOL")
    parser.add_argument("--no-local-mirror", action="store_true")
    parser.add_argument("--runtime-config", type=Path, default=None)
    parser.add_argument(
        "--main-checkpoint",
        type=Path,
        default=None,
        help="MineWorld main checkpoint; required for GPU_EXTRACTION_HOST",
    )
    parser.add_argument(
        "--vae-checkpoint",
        type=Path,
        default=None,
        help="MineWorld VAE checkpoint; required for GPU_EXTRACTION_HOST",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    host_id = args.host_id or args.host_role.lower()
    try:
        receipt = environment_receipt(
            host_role=args.host_role,
            pool_paths={
                "POOL_WORKING": args.working,
                "POOL_DURABLE": args.durable,
                "POOL_SCRATCH": args.scratch,
            },
            durable_root=args.durable,
            project=FABRIC_PROJECT,
            runtime_root=args.runtime_root,
            mod_jar=args.mod_jar,
            durability_mode=args.durability_mode,
            local_mirror_enabled=not args.no_local_mirror,
            implementation_checkpoint_commit=_head_commit(),
            runtime_config=(
                RuntimeConfig.from_json(args.runtime_config)
                if args.runtime_config
                else None
            ),
            main_checkpoint_path=args.main_checkpoint,
            vae_checkpoint_path=args.vae_checkpoint,
        )
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        print("A3_STATUS=FAIL", file=sys.stderr)
        return 1

    target = args.out / f"environment_receipt_{host_id}.json"
    digest = write_json_atomic(target, receipt)

    working = receipt["storage_pools"]["POOL_WORKING"]
    gate = receipt["storage_gate"]
    print(f"A3_STATUS=PASS")
    print(f"HOST_ROLE={receipt['host_role']}")
    print(f"AUTHORIZED_STAGES={','.join(receipt['authorized_stages'])}")
    print(f"NOT_AUTHORIZED_STAGES={','.join(receipt['not_authorized_stages'])}")
    print(f"RENDERER_QUALIFICATION={receipt['renderer_qualification']['status']}")
    print(f"DISPLAY={receipt['display']['status']}")
    print(f"GPU={receipt['gpu']['status']}")
    print(f"MODEL_IDENTITY_CHECKS={receipt['model_identity_checks']['status']}")
    print(
        "MODEL_IDENTITY_VERIFIED="
        f"{str(receipt['model_identity_checks']['verified']).lower()}"
    )
    print(f"AUTHORIZES_CAPTURE_STAGES={str(receipt['authorizes_capture_stages']).lower()}")
    print(f"POOL_WORKING_DEVICE_ID={working['device_id']}")
    print(f"POOL_WORKING_FREE_BYTES={working['free_bytes']}")
    print(f"POOL_WORKING_FREE_GIB={working['free_gib']:.3f}")
    print(f"STORAGE_GATE={gate['gate_applied']}")
    print(f"STORAGE_GATE_THRESHOLD_BYTES={gate['gate_threshold_bytes']}")
    print(f"STORAGE_GATE_PASSED={gate['passed']}")
    print(f"PHYSICAL_POOL_COUNT={gate['physical_pool_count']}")
    print(f"DURABLE_ROUND_TRIP={receipt['durability']['round_trip']['verified']}")
    print(f"RECEIPT={target.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"RECEIPT_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
