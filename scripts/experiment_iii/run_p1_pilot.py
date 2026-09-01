"""A5 / I22 — the P1 engineering pilot capture stage.

The pilot spends **only** ``e3_p90`` and ``e3_p91`` (authority 6A): no production
identity may ever be used to debug the implementation, because a production
identity consumed by a failed debug run cannot be replaced -- authority 2.1
forbids identity replacement, so the cohort would simply shrink.

    2 pilot identities x 5 conditions = 10 captures, 19 target rows each = 190

This script owns the **capture** half of P1. The extraction half -- 190 MineWorld
forwards and 60 persisted arrays -- is the same frozen A5 stage run on the GPU
extraction host, which is why A5's entry condition names A3 on *both* hosts. Its
entrypoint is ``run_p1_extraction.py``; it is not A9, which is production
extraction behind the A6/P2 freeze. Nothing in this file loads a model.

    python scripts/experiment_iii/run_p1_pilot.py --plan
    python scripts/experiment_iii/run_p1_pilot.py --execute \
        --runtime-config docs/experiment_iii/runtime/capture_runtime_wsl2_linux.json \
        --ladder docs/experiment_iii/p0/P0_SELECTED_LADDER.json

``--execute`` drives all ten units through :class:`PilotCampaign`, which is
resumable: re-running the same command after an interruption skips every unit the
hash-chained ledger records as COMPLETE and continues at the first that is not.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    AUTHORITY_VERSION,
    PILOT_IDENTITY_IDS,
    TARGET_ROWS_PER_CAPTURE,
    machine_authority,
    verify_authority_binding,
)
from mineocclude.experiment_iii.capture_runtime import (  # noqa: E402
    RuntimeConfig,
    qualify_capture_host,
)
from mineocclude.experiment_iii.conditions import build_condition_map  # noqa: E402
from mineocclude.experiment_iii.schema import ConditionId  # noqa: E402
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.schema import (  # noqa: E402
    capture_unit_id,
    read_jsonl,
    write_json_atomic,
)
from mineocclude.experiment_iii.a5_pilot import PilotCampaign, plan_specs  # noqa: E402
from mineocclude.experiment_iii.capture_driver import FrameSink  # noqa: E402
from mineocclude.experiment_iii.capture_runtime import CaptureRuntime  # noqa: E402
from mineocclude.experiment_iii.p0_analysis import load_selected_ladder  # noqa: E402
from mineocclude.experiment_iii.source_closure import source_closure  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "p1"
CONDITION_ORDER = (
    ConditionId.L0,
    ConditionId.L1,
    ConditionId.L2,
    ConditionId.L3,
    ConditionId.L4,
)


def pilot_plan(ladder: dict | None) -> dict:
    binding = verify_authority_binding()
    pilot = machine_authority()["p1_pilot"]
    # Without the P0 ladder L1-L3 have no material. build_condition_map refuses
    # rather than substituting a placeholder, which is right: a plan that named
    # a placeholder material would be indistinguishable from a real one. So the
    # unbound plan describes the pilot SHAPE and leaves those materials pending.
    resolved = build_condition_map(ladder) if ladder is not None else None
    units = []
    for identity in PILOT_IDENTITY_IDS:
        for condition in CONDITION_ORDER:
            spec = resolved[condition].as_dict() if resolved is not None else None
            units.append(
                {
                    "capture_unit_id": capture_unit_id(identity, condition),
                    "identity": identity,
                    "condition_id": condition.value,
                    "wall_block_id": (
                        spec["wall_block_id"] if spec else "PENDING_P0_SELECTION"
                    ),
                    "scene": spec["scene"] if spec else "PENDING_P0_SELECTION",
                    "target_rows": TARGET_ROWS_PER_CAPTURE,
                }
            )
    if len(units) != int(pilot["captures"]):
        raise ExperimentIIIError(
            "P1_INCOMPLETE",
            f"the pilot plan built {len(units)} captures, authority freezes "
            f"{pilot['captures']}",
        )
    return {
        "schema_version": "mineocclude-experiment-iii-p1-plan-v1",
        "authority_section": "6A",
        "authority_version": AUTHORITY_VERSION,
        "authority_binding": binding,
        "pilot_identities": list(PILOT_IDENTITY_IDS),
        "production_identities_used": False,
        "captures": len(units),
        "target_rows_per_capture": TARGET_ROWS_PER_CAPTURE,
        "target_rows_total": int(pilot["target_rows"]),
        "expected_model_forwards": int(pilot["forwards"]),
        "expected_serialized_arrays": int(pilot["serialized_npy_arrays"]),
        "ladder_bound": ladder is not None,
        "resume_demonstration_required": bool(pilot["resume_demonstration_required"]),
        "units": units,
    }



def _execute(args, plan: dict, ladder: dict, plan_digest: str) -> int:
    """Drive the ten pilot captures against the live apparatus."""
    identity_rows = read_jsonl(
        REPOSITORY_ROOT
        / "docs"
        / "experiment_iii"
        / "cohort"
        / "pilot_identity_manifest.jsonl"
    )
    specs = plan_specs(plan, identity_rows, ladder)

    # The V_c coordinates are P0's frozen condition-level evidence and travel
    # into the visibility rows as a diagnostic (authority 4.4). They are read
    # from the ladder, never recomputed.
    scores = dict(ladder.get("V_c") or {})
    scores.setdefault("L0", 1.0)

    config = RuntimeConfig.from_json(args.runtime_config)
    output_root = args.captures or (
        REPOSITORY_ROOT / "data" / "experiment_iii" / "p1" / "captures"
    )
    # Where the apparatus actually writes. Neither path is configurable in the
    # mod: MineOccludeServer resolves ``<server run dir>/mineocclude_out`` and the
    # client resolves ``<client run dir>/mineocclude_client_out``. The runtime
    # config's own ``output_root`` governs the process logs, not the episodes.
    client_episodes = Path(config.client_root) / "mineocclude_client_out"
    server_episodes = Path(config.server_root) / "mineocclude_out"

    campaign = PilotCampaign(
        specs,
        output_root=output_root,
        ledger_path=output_root.parent / "p1_capture_ledger.jsonl",
        server_episode_root=server_episodes,
        server_run_root=Path(config.server_root),
        rve_condition_scores=scores,
        source_closure=source_closure()["source_closure_sha256"],
    )

    def announce(unit_id: str, state: str) -> None:
        print(f"P1_UNIT={unit_id} STATE={state}", flush=True)

    started = time.time()
    with CaptureRuntime(config) as runtime:
        # The context manager only guarantees teardown; the apparatus has to be
        # brought up explicitly, in this order. Xvfb must exist before the client
        # opens a framebuffer, and the client must have joined before any episode
        # is armed or the lockstep ack never arrives.
        display = runtime.start_display()
        server = runtime.start_server()
        client = runtime.start_client()
        print(f"P1_DISPLAY={display}", flush=True)
        print(f"P1_SERVER_PID={server.get('pid')}", flush=True)
        print(f"P1_CLIENT_PID={client.get('pid')}", flush=True)
        sink = FrameSink(client_episodes)
        result = campaign.run(
            runtime,
            sink,
            warmup_ticks=args.warmup_ticks,
            frame_timeout_seconds=args.frame_timeout_seconds,
            on_unit=announce,
        )
    elapsed = time.time() - started

    inventory = result["inventory"]
    print(f"P1_PILOT_PLAN_SHA256={plan_digest}")
    print(f"P1_CAPTURES_EXPECTED={inventory['total_units']}")
    print(f"P1_CAPTURES_COMPLETE={inventory['completed_units']}")
    print(f"P1_CAPTURES_SKIPPED_AS_COMPLETE={len(result['skipped'])}")
    print(f"P1_CAPTURES_CAPTURED_THIS_RUN={len(result['captured'])}")
    print(f"P1_TARGET_ROWS_VALIDATED={inventory['target_rows_total']}")
    print(f"P1_DUPLICATE_ACCEPTED_UNITS={len(inventory['duplicate_accepted_units'])}")
    print(
        "P1_PRODUCTION_IDENTITIES_USED="
        f"{str(inventory['production_identities_used']).lower()}"
    )
    print(f"P1_CAPTURE_ELAPSED_SECONDS={elapsed:.1f}")
    print(f"P1_EXECUTED=true")
    if not inventory["complete"]:
        print("BLOCKER_CODE=P1_INCOMPLETE", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--qualify-host", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--ladder", type=Path, help="P0_SELECTED_LADDER json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--captures", type=Path, help="where capture units are banked"
    )
    parser.add_argument("--warmup-ticks", type=int, default=60)
    parser.add_argument("--frame-timeout-seconds", type=float, default=600.0)
    args = parser.parse_args(argv)
    if not (args.plan or args.qualify_host or args.execute):
        args.plan = True

    try:
        if args.qualify_host or args.execute:
            if args.runtime_config is None:
                raise ExperimentIIIError(
                    "ENV_RUNTIME_VERSION_MISMATCH", "--runtime-config is required"
                )
            qualification = qualify_capture_host(
                RuntimeConfig.from_json(args.runtime_config)
            )
            for line in qualification["reasons"]:
                print(f"HOST_UNQUALIFIED_REASON={line}", file=sys.stderr)
            print(f"CAPTURE_HOST_QUALIFIED={str(qualification['qualified']).lower()}")
            if args.qualify_host:
                return 0 if qualification["qualified"] else 1
            if not qualification["qualified"]:
                print("BLOCKER_CODE=ENV_DISPLAY_UNAVAILABLE", file=sys.stderr)
                return 1

        if args.execute and args.ladder is None:
            # A5's entry condition is A4 == P0_PASS. Without the selected ladder
            # L1..L3 have no material, so a "pilot" would capture placeholders.
            raise ExperimentIIIError(
                "P2_PREREQUISITE_NOT_PASSED",
                "P1 capture requires the P0_SELECTED_LADDER; A5 entry is "
                "A4 == P0_PASS",
            )

        import json

        # A file that merely looks like a ladder must not resolve L1/L2/L3, so the
        # execute path admits only a genuine A4 P0_SELECTED_LADDER at P0_PASS
        # under this authority. --plan keeps the permissive read so an unbound
        # plan can still describe the pilot SHAPE.
        if args.ladder is not None and args.execute:
            load_selected_ladder(args.ladder)
        ladder = (
            json.loads(args.ladder.read_text(encoding="utf-8")) if args.ladder else None
        )
        plan = pilot_plan(ladder)
        digest = write_json_atomic(args.out / "p1_pilot_plan.json", plan)

        if args.execute:
            return _execute(args, plan, ladder, digest)

        print(f"AUTHORITY_VERSION={AUTHORITY_VERSION}")
        print(f"PILOT_IDENTITIES={','.join(plan['pilot_identities'])}")
        print(f"P1_CAPTURES_EXPECTED={plan['captures']}")
        print(f"P1_TARGET_ROWS={plan['target_rows_total']}")
        print(f"P1_EXPECTED_MODEL_FORWARDS={plan['expected_model_forwards']}")
        print(f"P1_EXPECTED_ARRAYS={plan['expected_serialized_arrays']}")
        print(f"P1_PRODUCTION_IDENTITIES_USED=false")
        print(f"LADDER_BOUND={str(plan['ladder_bound']).lower()}")
        print(f"P1_PILOT_PLAN_SHA256={digest}")
        print("P1_EXECUTED=false")
        return 0
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
