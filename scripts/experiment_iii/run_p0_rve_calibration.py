"""A4 / I21 — the P0 Robust Visual Evidence calibration campaign.

Four modes, and the safe one is the default:

    --plan                          emit the frozen manifests and the campaign plan
    --qualify-host                  report whether this host may produce frames
    --execute --runtime-config C    capture the campaign AND close the stage
    --analyze                       re-close the stage from an already-captured
                                    campaign, without touching the apparatus

``--execute`` refuses to start unless the host qualifies under
:func:`capture_runtime.qualify_capture_host`. That refusal is the point. An
interactive desktop compositor renders only while its window is visible and
unoccluded, which no capture receipt can observe; and P0 captures a *static*
scene, where a frozen renderer is indistinguishable from a correct capture
everywhere except the transition probes. Producing P0 frames on an unqualified
host would manufacture a plausible-looking ladder out of duplicate frames.

``--execute`` is **one transaction**. It captures the 252 units and then, in the
same run, derives the L0 masks, computes the RVE table, evaluates all nine
validity rules, performs the exhaustive 1,320-permutation ladder search and emits
every A4 artifact through ``P0_SELECTION_RECEIPT``. It does not stop after the
capture: the remaining analysis would then be written with the measurements in
hand, on the code path that decides which materials become L1/L2/L3, which
Amendment 3 §1 classifies as an outcome-adjacent choice.

    python scripts/experiment_iii/run_p0_rve_calibration.py --plan
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    AUTHORITY_VERSION,
    verify_authority_binding,
)
from mineocclude.experiment_iii.capture_driver import FrameSink, capture_p0_unit  # noqa: E402
from mineocclude.experiment_iii.capture_runtime import (  # noqa: E402
    CaptureRuntime,
    RuntimeConfig,
    qualify_capture_host,
)
from mineocclude.experiment_iii.conditions import (  # noqa: E402
    ELIGIBLE_STAINED_GLASS,
    PROSPECTIVELY_EXCLUDED_MATERIALS,
    STONE,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.p0_analysis import (  # noqa: E402
    analyse_p0,
    load_unit_frames,
    production_authorized,
    write_a4_artifacts,
)
from mineocclude.experiment_iii.p0_bindings import p0_bootstrap_seed  # noqa: E402
from mineocclude.experiment_iii.p0_campaign import (  # noqa: E402
    P0CampaignState,
    campaign_manifest,
    campaign_units,
)
from mineocclude.experiment_iii.placements import (  # noqa: E402
    placement_coordinates,
    placement_manifest,
    sentinel_placement_indices,
)
from mineocclude.experiment_iii.rve import (  # noqa: E402
    ABBA_BLOCKS,
    ADJACENT_SEPARATION_MIN,
    BOOTSTRAP_REPLICATES,
    L3_SNR_MIN,
    LADDER_ZONES,
    PLACEMENT_COUNT,
    REPLICATE_CV_MAX,
    TARGET_RVE_POINTS,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.source_closure import closure_digest  # noqa: E402

DEFAULT_PLAN_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "a1_receipts"
DEFAULT_P0_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "p0"


def build_manifest() -> dict:
    binding = verify_authority_binding()
    conditions = 1 + len(ELIGIBLE_STAINED_GLASS) + 1
    return {
        "schema_version": "mineocclude-experiment-iii-p0-manifest-v2",
        "authority_section": "7.1-7.11",
        "authority_version": AUTHORITY_VERSION,
        "authority_binding": binding,
        "placements": PLACEMENT_COUNT,
        "placement_coordinates": [dict(p) for p in placement_coordinates()],
        "sentinel_placement_indices": list(sentinel_placement_indices()),
        "conditions_measured": conditions,
        "candidate_roster": list(ELIGIBLE_STAINED_GLASS),
        "roster_size": len(ELIGIBLE_STAINED_GLASS),
        "opaque_anchor": STONE,
        "prospective_exclusions": list(PROSPECTIVELY_EXCLUDED_MATERIALS),
        "abba_blocks": [list(block) for block in ABBA_BLOCKS],
        "replicate_blocks_per_cell": len(ABBA_BLOCKS),
        "min_settled_frames_per_state_per_block": 8,
        "ladder_zones": {k: list(v) for k, v in LADDER_ZONES.items()},
        "adjacent_separation_min": ADJACENT_SEPARATION_MIN,
        "l3_snr_min": L3_SNR_MIN,
        "replicate_cv_max": REPLICATE_CV_MAX,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": p0_bootstrap_seed(),
        "target_rve_points": list(TARGET_RVE_POINTS),
        "selection_rule": "MIN_SQUARED_DISTANCE_THEN_LEXICOGRAPHIC_REGISTRY_ID",
        "source": "RAW_SOURCE_RGB_640x360_NEVER_MODEL_NORMALIZED",
        "mask_rule": "ONE_PER_PLACEMENT_FROM_L0_SHARED_BY_EVERY_CANDIDATE",
        "p0_executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--qualify-host", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument(
        "--analyze",
        action="store_true",
        help="close A4 from an already-captured campaign, touching no apparatus",
    )
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_PLAN_OUT)
    parser.add_argument("--p0-out", type=Path, default=DEFAULT_P0_OUT)
    parser.add_argument("--frames-per-slot", type=int, default=None)
    parser.add_argument("--warmup-ticks", type=int, default=60)
    args = parser.parse_args(argv)
    if not (args.plan or args.qualify_host or args.execute or args.analyze):
        args.plan = True

    config = None
    qualification: dict[str, Any] | None = None
    try:
        if args.qualify_host or args.execute:
            if args.runtime_config is None:
                raise ExperimentIIIError(
                    "ENV_RUNTIME_VERSION_MISMATCH",
                    "--runtime-config is required; Experiment III never assumes a "
                    "host path",
                )
            config = RuntimeConfig.from_json(args.runtime_config)
            qualification = qualify_capture_host(config)
            for line in qualification["reasons"]:
                print(f"HOST_UNQUALIFIED_REASON={line}", file=sys.stderr)
            print(f"CAPTURE_HOST_QUALIFIED={str(qualification['qualified']).lower()}")
            if args.qualify_host:
                return 0 if qualification["qualified"] else 1
            if not qualification["qualified"]:
                print("BLOCKER_CODE=ENV_DISPLAY_UNAVAILABLE", file=sys.stderr)
                print("P0_EXECUTED=false", file=sys.stderr)
                return 1

        manifest = build_manifest()
        placements = placement_manifest()
        campaign = campaign_manifest(frames_per_slot=args.frames_per_slot)
        placement_digest = write_json_atomic(
            args.out / "p0_placement_manifest.json", placements
        )
        manifest["p0_placement_manifest_sha256"] = placement_digest
        manifest["campaign_units_sha256"] = campaign["units_sha256"]
        manifest_digest = write_json_atomic(args.out / "p0_manifest.json", manifest)
        campaign_digest = write_json_atomic(args.out / "p0_campaign_plan.json", campaign)

        print(f"AUTHORITY_VERSION={AUTHORITY_VERSION}")
        print(f"PLACEMENTS={PLACEMENT_COUNT}")
        print(f"PLACEMENTS_SHA256={placements['placements_sha256']}")
        print(f"SENTINEL_PLACEMENT_INDICES={list(sentinel_placement_indices())}")
        print(f"P0_BOOTSTRAP_SEED={manifest['bootstrap_seed']}")
        print(f"CONDITIONS_MEASURED={manifest['conditions_measured']}")
        print(f"CAMPAIGN_UNITS={campaign['unit_count']}")
        print(f"FRAMES_PER_SLOT={campaign['frames_per_slot']}")
        print(f"TOTAL_SETTLED_FRAMES={campaign['total_settled_frames']}")
        print(f"P0_PLACEMENT_MANIFEST_SHA256={placement_digest}")
        print(f"P0_CAMPAIGN_PLAN_SHA256={campaign_digest}")
        print(f"P0_MANIFEST_SHA256={manifest_digest}")

        if not (args.execute or args.analyze):
            print("P0_EXECUTED=false")
            return 0

        state = P0CampaignState(
            args.p0_out / "p0_campaign_state.json",
            authority_sha256=manifest["authority_binding"]["AUTHORITY_SHA256"],
            source_closure=closure_digest(),
        )
        units = campaign_units()

        if args.execute:
            capture_campaign(
                config,
                state,
                units,
                frames_per_slot=campaign["frames_per_slot"],
                warmup_ticks=args.warmup_ticks,
            )

        # A4 is one transaction, not a capture followed by an unwritten analysis.
        # Stopping here -- which is what this runner used to do -- would leave the
        # mask derivation, the RVE table, the bootstrap, the nine validity rules
        # and the deterministic search to be written WITH the measurements in
        # hand, on the code path that decides which materials become L1/L2/L3.
        # Amendment 3 1 classifies that as outcome-adjacent.
        return close_p0_stage(
            state,
            units,
            campaign=campaign,
            manifest=manifest,
            p0_out=args.p0_out,
            host_receipt=qualification,
        )
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        print(f"P0_RESULT={_terminal_state(error)}", file=sys.stderr)
        return 1


def _terminal_state(error: ExperimentIIIError) -> str:
    """The authority's own vocabulary for how A4 ended (7.6 ``outcomes``)."""
    if error.blocker == "P0_NO_VALID_LADDER":
        return "P0_NO_VALID_LADDER"
    return "P0_TECHNICAL_FAIL"


def capture_campaign(
    config: RuntimeConfig,
    state: P0CampaignState,
    units: Sequence[Any],
    *,
    frames_per_slot: int,
    warmup_ticks: int,
) -> None:
    """Drive the 252 capture units, retaining every attempt (A4 retry rules).

    ``A4`` specifies ``retry_rules: SAME_FROZEN_UNIT_ONLY; all attempts
    retained``. A bare top-level ``except`` satisfies neither: the failing unit
    was never marked and no attempt provenance was written, so a resumed campaign
    could not tell a unit that had never been tried from one that had failed
    three times.
    """
    sink = FrameSink(Path(config.client_root) / "mineocclude_client_out")
    pending = state.pending(units)
    print(f"UNITS_PENDING={len(pending)}")

    previous_material: str | None = None
    previous_settled_hash: str | None = None
    with CaptureRuntime(config) as runtime:
        runtime.start_display()
        runtime.start_server()
        runtime.start_client()
        for unit in pending:
            try:
                evidence = capture_p0_unit(
                    runtime,
                    sink,
                    unit,
                    frames_per_slot=frames_per_slot,
                    warmup_ticks=warmup_ticks,
                    episode_id_for_slot=lambda u, s: 87000 + u.order_index * 4 + s,
                    previous_wall_block_id=previous_material,
                    previous_unit_settled_hash=previous_settled_hash,
                )
            except ExperimentIIIError as error:
                state.mark_attempt(unit, error.blocker, error.message)
                state.save()
                raise
            previous_material = unit.wall_block_id
            previous_settled_hash = evidence.get("settled_hash")
            state.mark_complete(unit, evidence)
            state.save()


def close_p0_stage(
    state: P0CampaignState,
    units: Sequence[Any],
    *,
    campaign: Mapping[str, Any],
    manifest: Mapping[str, Any],
    p0_out: Path,
    host_receipt: Mapping[str, Any] | None,
) -> int:
    """Consume the captured evidence and emit every A4 artifact, atomically.

    This is ``A4``'s exit: it refuses an incomplete campaign, reads real pixels
    back off disk, runs the frozen analysis, and ends at ``P0_SELECTION_RECEIPT``.
    """
    summary = state.summary(units)
    print(f"UNITS_COMPLETE={summary['units_complete']}/{summary['units_total']}")
    if summary["units_pending"]:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            f"{summary['units_pending']} of {summary['units_total']} capture units "
            f"are not COMPLETE_VALIDATED_DURABLE; the P0 analysis consumes the "
            f"whole frozen campaign or none of it",
        )

    cells = []
    inventory = []
    for unit in units:
        record = state.units[unit.unit_id]
        evidence = record["evidence"]
        if evidence.get("dry_run") or evidence.get("liveness", {}).get("dry_run"):
            raise ExperimentIIIError(
                "P0_TECHNICAL_FAIL",
                f"unit {unit.unit_id} holds dry-run evidence; a planning artefact "
                f"is not a measurement and must never be analysed as one",
            )
        cells.append(load_unit_frames(evidence))
        for slot in evidence["slots"]:
            for path, digest, tick in zip(
                slot.get("frame_paths") or [],
                slot.get("frame_hashes") or [],
                slot.get("server_ticks") or [],
                strict=False,
            ):
                inventory.append(
                    {
                        "unit_id": unit.unit_id,
                        "condition_key": unit.condition_key,
                        "placement_index": unit.placement_index,
                        "block_index": unit.block_index,
                        "slot_index": slot["slot_index"],
                        "target_present": slot["target_present"],
                        "episode_id": slot["episode_id"],
                        "server_tick": tick,
                        "frame_path": path,
                        "frame_sha256": digest,
                    }
                )

    analysis = analyse_p0(cells)
    digests = write_a4_artifacts(
        analysis,
        out_dir=p0_out,
        capture_manifest=campaign,
        campaign_state_sha256=state.save(),
        host_receipt=host_receipt,
        image_inventory=inventory,
    )

    result = str(analysis["P0_RESULT"])
    for name, digest in sorted(digests.items()):
        print(f"{name}_SHA256={digest}")
    print(f"P0_EXECUTED=true")
    print(f"P0_RESULT={result}")
    # The ladder verdict and the lifecycle production gate are two different
    # things and are printed as two different lines on purpose. A4 answers the
    # first and can never answer the second: authority A6 permits
    # PRODUCTION_AUTHORIZED = true at the P2 freeze exit and nowhere else.
    print(f"P0_LADDER_ACCEPTED={str(analysis['P0_LADDER_ACCEPTED']).lower()}")
    print(f"PRODUCTION_AUTHORIZED={str(production_authorized()).lower()}")
    print("PRODUCTION_AUTHORIZATION_STAGE=A6_P2_PROSPECTIVE_FREEZE")
    if result == "P0_PASS":
        selected = analysis["selection"]["selected"]
        for level in ("L1", "L2", "L3"):
            print(f"{level}={selected[level]}")
        return 0
    for blocker in analysis["blockers"]:
        print(f"BLOCKER_CODE={blocker['blocker']}", file=sys.stderr)
    print("BLOCKER_CODE=P0_NO_VALID_LADDER", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
