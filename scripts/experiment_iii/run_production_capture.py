"""A7 / I04 — the production capture driver.

Emits the frozen 125-unit capture plan and its condition batches, validates the
Latin balance and capture-order determinism, reports whether a host is qualified
to produce scientific frames, and -- with ``--execute`` -- runs the campaign.

Live production capture is gated behind ``PRODUCTION_AUTHORIZED``, which only A6
(P2) can set. That gate is not a formality: A7 spends the 25 production
identities, and authority 2.1 forbids identity replacement, so a batch captured
under an unfrozen ladder or an unqualified renderer permanently shrinks the
cohort rather than merely wasting time. ``--execute`` therefore consumes a real,
passed, current P2 package through :func:`admit_production`, and there is no
override flag: a superseded freeze, a drifted authority, a drifted source
closure or an unqualified capture host each refuse terminally.

    python scripts/experiment_iii/run_production_capture.py --plan-only
    python scripts/experiment_iii/run_production_capture.py --qualify-host --runtime-config C
    python scripts/experiment_iii/run_production_capture.py --execute \
        --p2 docs/experiment_iii/p2/P2_FREEZE_PACKAGE.json \
        --capture-host-receipt docs/experiment_iii/receipts/environment_receipt_*.json \
        --ladder docs/experiment_iii/p0/P0_SELECTED_LADDER.json \
        --runtime-config <runtime.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.a7_production import (  # noqa: E402
    EXPECTED_CAPTURES,
    EXPECTED_FRAMES,
    EXPECTED_TARGET_ROWS,
    ProductionCampaign,
    admit_production,
    production_specs,
)
from mineocclude.experiment_iii.authority import verify_authority_binding  # noqa: E402
from mineocclude.experiment_iii.capture_driver import FrameSink  # noqa: E402
from mineocclude.experiment_iii.capture_runtime import CaptureRuntime  # noqa: E402
from mineocclude.experiment_iii.source_closure import source_closure  # noqa: E402
from mineocclude.experiment_iii.capture_schedule import (  # noqa: E402
    build_capture_schedule,
    condition_batches,
    validate_capture_order,
)
from mineocclude.experiment_iii.conditions import build_condition_map  # noqa: E402
from mineocclude.experiment_iii.capture_runtime import (  # noqa: E402
    RuntimeConfig,
    qualify_capture_host,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.p0_analysis import load_selected_ladder  # noqa: E402
from mineocclude.experiment_iii.schema import read_jsonl, write_json_atomic  # noqa: E402

COHORT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "cohort"
DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "capture"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan-only",
        action="store_true",
        default=True,
        help="the only supported mode here; A7 capture is not authorized",
    )
    parser.add_argument(
        "--ladder",
        type=Path,
        help="P0_SELECTED_LADDER json mapping L1/L2/L3 to registry IDs",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--qualify-host", action="store_true")
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--p2",
        type=Path,
        default=REPOSITORY_ROOT
        / "docs"
        / "experiment_iii"
        / "p2"
        / "P2_FREEZE_PACKAGE.json",
        help="the P2 freeze package that authorizes production",
    )
    parser.add_argument("--capture-host-receipt", type=Path)
    parser.add_argument(
        "--capture-root",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "experiment_iii" / "production" / "captures",
    )
    parser.add_argument("--warmup-ticks", type=int, default=60)
    parser.add_argument("--frame-timeout-seconds", type=float, default=600.0)
    args = parser.parse_args(argv)

    if args.qualify_host:
        if args.runtime_config is None:
            print("BLOCKER_CODE=ENV_RUNTIME_VERSION_MISMATCH", file=sys.stderr)
            print("--runtime-config is required", file=sys.stderr)
            return 1
        qualification = qualify_capture_host(RuntimeConfig.from_json(args.runtime_config))
        for line in qualification["reasons"]:
            print(f"HOST_UNQUALIFIED_REASON={line}", file=sys.stderr)
        print(f"CAPTURE_HOST_QUALIFIED={str(qualification['qualified']).lower()}")
        return 0 if qualification["qualified"] else 1

    # As in A9: --plan-only together with --execute must not quietly become a
    # production run of 125 captures.
    if args.execute and "--plan-only" in (argv if argv is not None else sys.argv[1:]):
        print("BLOCKER_CODE=P2_PREREQUISITE_NOT_PASSED", file=sys.stderr)
        print("--plan-only and --execute are contradictory; A7 will not spend "
              "production captures under an explicit plan-only request",
              file=sys.stderr)
        return 1
    if args.execute:
        return _execute(args)

    try:
        binding = verify_authority_binding()
        if args.ladder is None:
            # build_condition_map refuses an unresolved ladder rather than
            # defaulting L1-L3, which is correct: a schedule naming a placeholder
            # material is indistinguishable from a real one and was exactly how a
            # pre-P0 dry run once acquired white/lime/blue. Refuse here too.
            raise ExperimentIIIError(
                "P0_CANDIDATE_ID_UNSUPPORTED",
                "the production capture schedule binds the P0-selected L1/L2/L3 "
                "materials; pass --ladder P0_SELECTED_LADDER.json once A4 has "
                "returned P0_PASS",
            )
        # And refuse a file that merely *looks* like a ladder. Any JSON object
        # with three keys used to be accepted here, so the artefact that once
        # contaminated a dry run -- a v1.5-bound schedule naming white/lime/blue --
        # would have been consumed without complaint. load_selected_ladder admits
        # only a genuine A4 P0_SELECTED_LADDER at P0_PASS under this authority.
        ladder = load_selected_ladder(args.ladder)
        conditions = build_condition_map(ladder)
        production = read_jsonl(COHORT / "production_identity_manifest.jsonl")
        schedule = build_capture_schedule(production, conditions)
        report = validate_capture_order(schedule)
        batches = condition_batches(schedule)
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    digest = write_json_atomic(
        args.out / "capture_schedule.json",
        {
            "schema_version": "mineocclude-experiment-iii-capture-schedule-v1",
            "authority_section": "8.1",
            "authority_binding": binding,
            "conditions": {
                condition.value: spec.as_dict()
                for condition, spec in conditions.items()
            },
            "validation": report,
            "condition_batches": batches,
            "captures": [unit.as_dict() for unit in schedule],
        },
    )
    print(f"CAPTURES={report['captures']}")
    print(f"CONDITION_BATCHES={report['condition_batches']}")
    print(f"WALL_MATERIAL_TRANSITIONS={report['wall_material_transitions']}")
    print(f"CAPTURE_SCHEDULE_SHA256={digest}")
    print("CAPTURE_EXECUTED=false")
    return 0


def _execute(args) -> int:
    """Run the 125-unit production campaign. Every refusal here is terminal."""
    import time

    try:
        # Admission FIRST, before a runtime is started or a schedule is built.
        # An unauthorized run must not so much as open a display, because the
        # apparatus coming up is already an observable side effect on the host
        # whose A3 receipt this stage depends on.
        admission = admit_production(
            args.p2,
            capture_host_receipt=args.capture_host_receipt,
        )
        if args.ladder is None:
            raise ExperimentIIIError(
                "P0_CANDIDATE_ID_UNSUPPORTED",
                "A7 binds the P0-selected L1/L2/L3 materials; pass --ladder",
            )
        if args.runtime_config is None:
            raise ExperimentIIIError(
                "ENV_RUNTIME_VERSION_MISMATCH",
                "A7 needs a capture runtime config; Experiment III never assumes "
                "a host path",
            )
        ladder = load_selected_ladder(args.ladder)
        production = read_jsonl(COHORT / "production_identity_manifest.jsonl")
        specs, schedule, report = production_specs(production, ladder)
        config = RuntimeConfig.from_json(args.runtime_config)
        qualification = qualify_capture_host(config)
        if not qualification["qualified"]:
            raise ExperimentIIIError(
                "ENV_DISPLAY_UNAVAILABLE",
                "this host is not a qualified Experiment III capture renderer: "
                + "; ".join(qualification["reasons"]),
            )
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        print("A7_EXECUTED=false", file=sys.stderr)
        return 1

    output_root = Path(args.capture_root)
    campaign = ProductionCampaign(
        specs,
        output_root=output_root,
        ledger_path=output_root.parent / "production_capture_ledger.jsonl",
        server_episode_root=Path(config.server_root) / "mineocclude_out",
        server_run_root=Path(config.server_root),
        source_closure=source_closure()["source_closure_sha256"],
    )
    boundaries = campaign.batch_boundaries(schedule)
    counts = campaign.expected_counts()

    print(f"A7_P2_PACKAGE_SHA256={admission['p2_package_sha256']}")
    print(f"A7_SOURCE_CLOSURE={admission['source_closure_sha256']}")
    print(f"A7_CAPTURE_HOST_RECEIPT={admission['capture_host_receipt']['path']}")
    print(f"A7_EXPECTED_CAPTURES={counts['captures']}")
    print(f"A7_EXPECTED_FRAMES={counts['frames']}")
    print(f"A7_EXPECTED_TARGET_ROWS={counts['target_rows']}")
    print(f"A7_SENTINEL_CHECKS={len(boundaries)}")
    print(f"A7_WALL_MATERIAL_TRANSITIONS={report['wall_material_transitions']}")

    def announce(unit_id: str, state: str) -> None:
        print(f"A7_UNIT={unit_id} STATE={state}", flush=True)

    started = time.time()
    try:
        with CaptureRuntime(config) as runtime:
            display = runtime.start_display()
            server = runtime.start_server()
            client = runtime.start_client()
            print(f"A7_DISPLAY={display}", flush=True)
            print(f"A7_SERVER_PID={server.get('pid')}", flush=True)
            print(f"A7_CLIENT_PID={client.get('pid')}", flush=True)
            sink = FrameSink(Path(config.client_root) / "mineocclude_client_out")
            result = campaign.run(
                runtime,
                sink,
                warmup_ticks=args.warmup_ticks,
                frame_timeout_seconds=args.frame_timeout_seconds,
                on_unit=announce,
            )
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        print("A7_EXECUTED=true", file=sys.stderr)
        return 1
    elapsed = time.time() - started

    inventory = result["inventory"]
    write_json_atomic(
        args.out / "capture_matrix.json",
        {
            "schema_version": "mineocclude-experiment-iii-capture-matrix-v1",
            "stage": "A7",
            "authority_binding": admission["authority_binding"],
            "source_closure_sha256": admission["source_closure_sha256"],
            "p2_package_sha256": admission["p2_package_sha256"],
            "expected_counts": counts,
            "validation": report,
            "sentinel_boundaries": boundaries,
            "inventory": inventory,
        },
    )
    print(f"A7_CAPTURES_COMPLETE={inventory['completed_units']}")
    print(f"A7_CAPTURES_SKIPPED_AS_COMPLETE={len(result['skipped'])}")
    print(f"A7_CAPTURES_CAPTURED_THIS_RUN={len(result['captured'])}")
    print(f"A7_TARGET_ROWS={inventory['target_rows_total']}")
    print(f"A7_DUPLICATE_ACCEPTED_UNITS={len(inventory['duplicate_accepted_units'])}")
    print(f"A7_ELAPSED_SECONDS={elapsed:.1f}")
    print("A7_EXECUTED=true")
    if not inventory["complete"]:
        print("BLOCKER_CODE=CAPTURE_MISSING_FRAME", file=sys.stderr)
        print(
            f"{inventory['completed_units']}/{inventory['total_units']} units are "
            f"COMPLETE_VALIDATED_DURABLE",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
