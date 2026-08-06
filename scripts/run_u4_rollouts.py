"""Validate, freeze, generate, hand off, and classify the Week 1 U4 rollouts.

    python scripts/run_u4_rollouts.py validate-request --request PATH   # 8.1
    python scripts/run_u4_rollouts.py freeze-manifest --request PATH    # 8.5
    python scripts/run_u4_rollouts.py generate --manifest PATH          # 8.6
    python scripts/run_u4_rollouts.py handoff --bundle PATH             # 8.7
    python scripts/run_u4_rollouts.py classify --bundle PATH            # 8.8

Generation requires Person B's hash-bound direction/dose request, Person C's
held-out event metadata, Person D's control manifest, Person E's measurement
contract, and an authorized model runtime. Without all of them the command
refuses to generate rather than producing an unusable artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.mvp_config import load_mvp_config  # noqa: E402
from mineocclude.intervention.inject import validate_request  # noqa: E402
from mineocclude.intervention.rollout_manifest import (  # noqa: E402
    DoseSpec,
    HeldoutEvent,
    RolloutRunner,
    build_control_handoff,
    build_measurement_handoff,
    build_rollout_manifest,
    classify_u4,
    manifest_hash,
)

DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "mvp.yaml"
DEFAULT_OUTPUT_ROOT = ROOT / "docs" / "status" / "person_a_phase8_u4_v0_1"


def write_json(path: Path, document: Any) -> str:
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_validate_request(args: argparse.Namespace) -> int:
    request = load_json(Path(args.request))
    report = validate_request(request).to_document()
    report["request_sha256"] = hashlib.sha256(
        Path(args.request).read_bytes()
    ).hexdigest()
    digest = write_json(
        Path(args.output_root) / "step_8_1_request_validation.json", report
    )
    print(json.dumps({"step": "8.1", "status": report["status"], "sha256": digest}))
    return 0 if report["accepted"] else 1


def cmd_freeze_manifest(args: argparse.Namespace) -> int:
    config = load_mvp_config(args.config)
    request = load_json(Path(args.request))
    report = validate_request(request)
    if not report.accepted:
        print(
            json.dumps(
                {
                    "step": "8.5",
                    "status": "REFUSED",
                    "reason": "the B-to-A intervention request was rejected",
                    "rejections": [dict(item) for item in report.rejections],
                }
            )
        )
        return 1
    events = [
        HeldoutEvent(
            event_id=str(event["event_id"]),
            trajectory_id=str(event.get("trajectory_id", "")),
            layout_id=str(event.get("layout_id", "")),
            model_frame_idx=int(event.get("model_frame_idx", 0)),
        )
        for event in request["heldout_events"]
    ]
    doses = [
        DoseSpec(
            dose_id=str(entry["dose_id"]),
            intended_block_shift=int(entry["intended_block_shift"]),
            alpha_requested=float(entry["alpha_requested"]),
            alpha_applied=float(entry["alpha_applied"]),
            cap_reduced=bool(entry.get("cap_reduced")),
        )
        for entry in request["alpha_table"]
    ]
    control_manifest = (
        load_json(Path(args.d_control_manifest)) if args.d_control_manifest else {}
    )
    manifest = build_rollout_manifest(
        manifest_id=args.manifest_id,
        handoff_id=args.handoff_id,
        heldout_events=events,
        doses=doses,
        seeds=list(config.get("seeds.rollout_seeds")),
        direction_version=str(request["direction_metadata"]["direction_version"]),
        layer_idx=int(request["intervention_location"]["layer_idx"]),
        timestep_idx=int(request["intervention_location"]["timestep_idx"]),
        hook_site=str(request["intervention_location"]["hook_site"]),
        output_root=args.rollout_root,
        random_control_seeds=list(args.random_control_seeds),
        random_control_direction_versions=list(args.random_control_directions),
        random_control_shift=int(config.get("u4_pilot.random_control_block_mapping")),
        d_control_ids=list(control_manifest.get("control_ids", ())),
        expected_primary_clip_count=int(config.get("u4_pilot.primary_clip_count")),
        expected_random_control_count=int(
            config.get("u4_pilot.random_direction_control_count")
        ),
    )
    manifest["manifest_sha256"] = manifest_hash(manifest)
    digest = write_json(
        Path(args.output_root) / "step_8_5_rollout_manifest.json", manifest
    )
    print(
        json.dumps(
            {
                "step": "8.5",
                "clips": manifest["expected_counts"]["total_clip_count"],
                "sha256": digest,
            }
        )
    )
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    manifest = load_json(Path(args.manifest))
    runner = RolloutRunner(manifest=manifest)
    bundle = runner.bundle()
    digest = write_json(
        Path(args.output_root) / "step_8_6_rollout_bundle.json", bundle
    )
    print(
        json.dumps(
            {
                "step": "8.6",
                "expected": bundle["expected_clip_count"],
                "completed": bundle["completed_clip_count"],
                "pending": bundle["pending_clip_count"],
                "sha256": digest,
                "note": (
                    "No clip was generated: real generation requires an "
                    "authorized model runtime and is never simulated."
                ),
            }
        )
    )
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    bundle = load_json(Path(args.bundle))
    measurement = build_measurement_handoff(
        bundle,
        handoff_id=f"{args.handoff_id}-e",
        event_dose_table=load_json(Path(args.event_dose_table))
        if args.event_dose_table
        else {},
        detector_version=args.detector_version,
        homography_version=args.homography_version,
    )
    control = build_control_handoff(bundle, handoff_id=f"{args.handoff_id}-d")
    e_digest = write_json(
        Path(args.output_root) / "step_8_7_person_e_handoff.json", measurement
    )
    d_digest = write_json(
        Path(args.output_root) / "step_8_7_person_d_handoff.json", control
    )
    print(
        json.dumps(
            {
                "step": "8.7",
                "e_expected": measurement["expected_clip_count"],
                "e_produced": measurement["produced_clip_count"],
                "d_controls": control["control_clip_count"],
                "e_sha256": e_digest,
                "d_sha256": d_digest,
            }
        )
    )
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    bundle = load_json(Path(args.bundle)) if args.bundle else None
    measurement = load_json(Path(args.measurement)) if args.measurement else None
    injection_audit = (
        load_json(Path(args.injection_audit)) if args.injection_audit else None
    )
    document = classify_u4(
        injection_exact=bool(
            injection_audit and injection_audit.get("exact_mask_match")
        ),
        baseline_persistence_confirmed=bool(
            measurement and measurement.get("baseline_persistence_confirmed")
        ),
        signed_displacement_pattern_confirmed=bool(
            measurement and measurement.get("signed_displacement_pattern_confirmed")
        ),
        random_direction_specificity_confirmed=bool(
            measurement and measurement.get("random_direction_specificity_confirmed")
        ),
        wrong_site_specificity_confirmed=bool(
            measurement and measurement.get("wrong_site_specificity_confirmed")
        ),
        ssim_within_natural_variation=bool(
            measurement and measurement.get("ssim_within_natural_variation")
        ),
        predeclared_heldout_partition_present=bool(
            args.predeclared_heldout_partition
        ),
        measurement_valid=bool(measurement and measurement.get("valid")),
        controls_valid=bool(bundle and bundle.get("complete")),
        evidence_tables={
            "rollout_bundle": args.bundle or "",
            "measurement_tables": args.measurement or "",
            "injection_audit": args.injection_audit or "",
        },
        detail=args.detail,
    )
    digest = write_json(
        Path(args.output_root) / "step_8_8_u4_classification.json", document
    )
    print(
        json.dumps(
            {
                "step": "8.8",
                "classification": document["classification"],
                "causal_claim_made": document["causal_claim_made"],
                "sha256": digest,
            }
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-request")
    validate.add_argument("--request", required=True)

    freeze = sub.add_parser("freeze-manifest")
    freeze.add_argument("--request", required=True)
    freeze.add_argument("--manifest-id", default="person-a-u4-week1-v0.1")
    freeze.add_argument("--handoff-id", default="person-a-u4-week1-handoff-v0.1")
    freeze.add_argument("--rollout-root", default="u4/week1")
    freeze.add_argument("--d-control-manifest")
    freeze.add_argument(
        "--random-control-seeds",
        nargs="+",
        type=int,
        default=[20260803, 20260804],
    )
    freeze.add_argument(
        "--random-control-directions",
        nargs="+",
        default=[f"random-{index:02d}" for index in range(10)],
    )

    generate = sub.add_parser("generate")
    generate.add_argument("--manifest", required=True)

    handoff = sub.add_parser("handoff")
    handoff.add_argument("--bundle", required=True)
    handoff.add_argument("--handoff-id", default="person-a-u4-week1-handoff-v0.1")
    handoff.add_argument("--event-dose-table")
    handoff.add_argument("--detector-version", default="UNAVAILABLE")
    handoff.add_argument("--homography-version", default="UNAVAILABLE")

    classify = sub.add_parser("classify")
    classify.add_argument("--bundle")
    classify.add_argument("--measurement")
    classify.add_argument("--injection-audit")
    classify.add_argument(
        "--predeclared-heldout-partition", action="store_true", default=False
    )
    classify.add_argument("--detail")
    return parser


COMMANDS = {
    "validate-request": cmd_validate_request,
    "freeze-manifest": cmd_freeze_manifest,
    "generate": cmd_generate,
    "handoff": cmd_handoff,
    "classify": cmd_classify,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
