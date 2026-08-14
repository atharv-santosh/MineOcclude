"""Build real Steps 7.1-7.3 (U4) documents from Person B/E real handoffs.

Every Phase 7 building block (``u4_control_manifest_v0_1``,
``direction_control_audit_v0_1``, ``u4_measurement_join_v0_1``) is real
and generic -- none of it is hardcoded to synthetic data. What was
missing, until this script, was any way to actually feed it real data:
``run_person_d_phase6to8_completion.py``'s own blocker documents already
told the reader to run

    python scripts/run_person_d_phase6to8_completion.py \\
        --u4-direction-record <B_DIRECTION_RECORD> --freeze-real-control-manifest

and

    python scripts/run_person_d_phase6to8_completion.py \\
        --u4-measurements <E_MEASUREMENT_TABLE> --output-root <OUTPUT_ROOT>

but that script's argparse never actually defined either flag -- the
documented "exact command to run on receipt" would have failed with
"unrecognized arguments" the day Person B or Person E actually published
real U4 data. This script is that missing real path, kept additive and
separate from the synthetic generator (matching how
``run_person_d_66_cell_step6_3to6_5_completion.py`` sits alongside
``run_person_d_phase6to8_completion.py`` rather than editing its
well-tested synthetic branch).

Direction-record JSON schema (Person B's real handoff):

    {
      "held_out_events": [{"event_id", "trajectory_id", "layout_id"}, ...],
      "rollout_seeds": [int, ...],
      "doses": [{"dose_id", "alpha_requested", "alpha_applied", "cap_reduced"}, ...],
      "primary_direction": {"direction_id", "direction_version",
                             "direction_sha256", "seed"?},
      "random_directions": [{...same shape...}, ...],
      "orthogonal_directions": [{...same shape...}, ...],
      "target_layer_idx", "target_timestep_idx",
      "wrong_layer_idx", "wrong_timestep_idx",
      "direction_construction_evidence": {...REQUIRED_EVIDENCE_FIELDS...},
      "source_commit": "<Person B commit this record was published at>"
    }

Measurements JSON schema (Person E's real handoff): a JSON list of
objects with exactly ``MeasurementRow``'s fields
(``mineocclude.baselines.u4_measurement_join_v0_1.MeasurementRow``).

Usage:

    python scripts/run_person_d_u4_real_completion.py \\
        --u4-direction-record <B_DIRECTION_RECORD.json> \\
        [--u4-measurements <E_MEASUREMENT_TABLE.json>] \\
        --output-root docs/status/person_d_u4_real_completion_v0_1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from mineocclude.baselines.direction_control_audit_v0_1 import (
    audit_direction_construction,
    build_direction_control_audit,
    dump_direction_control_audit,
)
from mineocclude.baselines.u4_control_manifest_v0_1 import (
    ControlManifestError,
    DirectionRef,
    DoseSpec,
    HeldOutEvent,
    build_control_manifest,
    build_control_manifest_rows,
    build_person_d_to_a_and_e_handoff,
    dump_control_manifest,
    freeze_control_manifest,
)
from mineocclude.baselines.u4_measurement_join_v0_1 import (
    MeasurementRow,
    dump_u4_control_matrix,
    join_measurements_to_manifest,
)

RUN_ID = "person-d-u4-real-completion-v0-1"


class U4RealCompletionError(ValueError):
    """Raised when a real U4 handoff cannot be built honestly."""


def _write(output_root: Path, name: str, text: str) -> str:
    path = output_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _direction_ref(entry: dict[str, Any]) -> DirectionRef:
    try:
        return DirectionRef(
            direction_id=entry["direction_id"],
            direction_version=entry["direction_version"],
            direction_sha256=entry["direction_sha256"],
            seed=entry.get("seed"),
        )
    except KeyError as error:
        raise U4RealCompletionError(f"direction reference missing field {error}") from error


def load_direction_record(path: Path) -> dict[str, Any]:
    """Parse Person B's real direction-record JSON into the builder kwargs.

    Fails closed on any missing required field -- a partially-specified
    real record is not usable to build a real control manifest.
    """

    document = json.loads(path.read_text(encoding="utf-8"))
    try:
        held_out_events = tuple(
            HeldOutEvent(
                event_id=e["event_id"],
                trajectory_id=e["trajectory_id"],
                layout_id=e["layout_id"],
            )
            for e in document["held_out_events"]
        )
        rollout_seeds = tuple(document["rollout_seeds"])
        doses = tuple(
            DoseSpec(
                dose_id=d["dose_id"],
                alpha_requested=d["alpha_requested"],
                alpha_applied=d["alpha_applied"],
                cap_reduced=d["cap_reduced"],
            )
            for d in document["doses"]
        )
        primary_direction = _direction_ref(document["primary_direction"])
        random_directions = tuple(_direction_ref(e) for e in document["random_directions"])
        orthogonal_directions = tuple(
            _direction_ref(e) for e in document.get("orthogonal_directions", ())
        )
        manifest_kwargs = {
            "held_out_events": held_out_events,
            "rollout_seeds": rollout_seeds,
            "doses": doses,
            "primary_direction": primary_direction,
            "random_directions": random_directions,
            "orthogonal_directions": orthogonal_directions,
            "target_layer_idx": document["target_layer_idx"],
            "target_timestep_idx": document["target_timestep_idx"],
            "wrong_layer_idx": document["wrong_layer_idx"],
            "wrong_timestep_idx": document["wrong_timestep_idx"],
        }
    except KeyError as error:
        raise U4RealCompletionError(
            f"real direction record {path} is missing required field {error}"
        ) from error

    return {
        "manifest_kwargs": manifest_kwargs,
        "direction_construction_evidence": document.get("direction_construction_evidence"),
        # Optional: Person B may publish the actual primary/control direction
        # vectors inline (small dimension) rather than only their hashes.
        # Without these, the norm-matching and orthogonality checks in
        # audit_direction_construction stay "blocked" (not failed) -- an
        # honest degradation, not an error.
        "real_direction_values": document.get("real_direction_values"),
        "control_direction_values": document.get("control_direction_values"),
        "source_commit": document.get("source_commit"),
    }


def load_measurements(path: Path) -> list[MeasurementRow]:
    """Parse Person E's real measurement-table JSON into ``MeasurementRow``s."""

    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, list):
        raise U4RealCompletionError(f"real measurement table {path} must be a JSON list")
    rows = []
    for index, entry in enumerate(document):
        try:
            rows.append(
                MeasurementRow(
                    clip_id=entry["clip_id"],
                    outcome=entry["outcome"],
                    event_id=entry["event_id"],
                    rollout_seed=entry["rollout_seed"],
                    dose_id=entry.get("dose_id"),
                    control_type=entry["control_type"],
                    target_layer_idx=entry["target_layer_idx"],
                    target_timestep_idx=entry["target_timestep_idx"],
                    direction_id=entry["direction_id"],
                    pair_key=entry["pair_key"],
                    detector_version=entry["detector_version"],
                    homography_version=entry["homography_version"],
                    ssim_version=entry["ssim_version"],
                    displacement_blocks=entry.get("displacement_blocks"),
                    masked_ssim=entry.get("masked_ssim"),
                    missing_reason=entry.get("missing_reason"),
                )
            )
        except KeyError as error:
            raise U4RealCompletionError(
                f"real measurement row {index} in {path} is missing required field {error}"
            ) from error
    return rows


def build_all(
    output_root: Path,
    direction_record_path: Path,
    measurements_path: Path | None,
    person_a_commit: str,
    person_b_commit: str,
) -> dict[str, Any]:
    inventory: dict[str, str] = {}

    record = load_direction_record(direction_record_path)
    manifest_kwargs = record["manifest_kwargs"]

    # ---- Step 7.1: real U4 control manifest ------------------------------
    control_manifest = build_control_manifest(
        manifest_id="person-d-u4-control-manifest-real-v0-1",
        manifest_version="1.0.0",
        rows=build_control_manifest_rows(**manifest_kwargs),
        source_authorities={
            "person_a_commit": person_a_commit,
            "person_b_commit": person_b_commit,
            "direction_record_source_commit": record.get("source_commit"),
            "real_direction_available": "YES",
            "real_heldout_events_available": "YES",
        },
        evidence_kind="real",
        **manifest_kwargs,
    )
    frozen_manifest = freeze_control_manifest(control_manifest)
    manifest_text = dump_control_manifest(frozen_manifest)
    manifest_sha = _write(output_root, "step7_1_u4_control_manifest.json", manifest_text)
    inventory["step7_1_u4_control_manifest.json"] = manifest_sha

    handoff = build_person_d_to_a_and_e_handoff(
        frozen_manifest,
        manifest_path="docs/status/person_d_u4_real_completion_v0_1/step7_1_u4_control_manifest.json",
        manifest_sha256=manifest_sha,
    )
    handoff["real_manifest_status"] = "FROZEN_AS_REAL_EVIDENCE"
    handoff["blocking_inputs"] = []
    inventory["step7_1_control_handoff_to_a_and_e.json"] = _write(
        output_root,
        "step7_1_control_handoff_to_a_and_e.json",
        json.dumps(handoff, indent=2, sort_keys=True, default=list) + "\n",
    )

    # ---- Step 7.2: real direction-control construction audit ------------
    evidence = record["direction_construction_evidence"]
    direction_audit = build_direction_control_audit(
        audit_id="person-d-step7-2-direction-control-audit-real-v0-1",
        findings=audit_direction_construction(
            evidence,
            real_direction_values=record["real_direction_values"],
            control_direction_values=record["control_direction_values"],
        ),
        evidence_source={
            "person_b_commit": person_b_commit,
            "person_a_commit": person_a_commit,
            "direction_record_path": str(direction_record_path),
            "finding": (
                "Real evidence supplied by Person B's direction record."
                if evidence is not None
                else (
                    "The real direction record did not include a "
                    "direction_construction_evidence block; audited as absent."
                )
            ),
        },
        evidence_kind="real",
    )
    inventory["step7_2_direction_control_audit.json"] = _write(
        output_root,
        "step7_2_direction_control_audit.json",
        dump_direction_control_audit(direction_audit),
    )

    # ---- Step 7.3: real U4 control matrix (measurement join) ------------
    if measurements_path is not None:
        measurements = load_measurements(measurements_path)
        control_matrix = join_measurements_to_manifest(
            manifest=frozen_manifest,
            measurements=measurements,
            run_id="person-d-step7-3-real-measurement-join-v0-1",
            evidence_kind="real",
        )
    else:
        control_matrix = join_measurements_to_manifest(
            manifest=frozen_manifest,
            measurements=[],
            run_id="person-d-step7-3-real-measurement-join-v0-1",
            evidence_kind="real",
        )
    inventory["step7_3_u4_control_matrix.json"] = _write(
        output_root,
        "step7_3_u4_control_matrix.json",
        dump_u4_control_matrix(control_matrix),
    )

    inventory_document = {
        "schema_id": "person-d-u4-real-completion-inventory-v0-1",
        "schema_version": "1.0",
        "producer_role": "person_d",
        "package_id": "person-d-u4-real-completion-v0-1",
        "evidence_kind": "real",
        "real_execution_performed": True,
        "measurements_supplied": measurements_path is not None,
        "artifact_sha256": dict(sorted(inventory.items())),
        "artifact_count": len(inventory),
    }
    _write(
        output_root,
        "sha256_inventory.json",
        json.dumps(inventory_document, indent=2, sort_keys=True) + "\n",
    )
    return inventory_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--u4-direction-record", required=True, type=Path)
    parser.add_argument("--u4-measurements", type=Path, default=None)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "docs" / "status" / "person_d_u4_real_completion_v0_1",
    )
    parser.add_argument(
        "--person-a-commit",
        default="UNKNOWN_UPDATE_TO_THE_REAL_PERSON_A_COMMIT_AT_RECEIPT_TIME",
    )
    parser.add_argument(
        "--person-b-commit",
        default="UNKNOWN_UPDATE_TO_THE_REAL_PERSON_B_COMMIT_AT_RECEIPT_TIME",
    )
    args = parser.parse_args(argv)

    try:
        document = build_all(
            args.output_root,
            args.u4_direction_record,
            args.u4_measurements,
            args.person_a_commit,
            args.person_b_commit,
        )
    except (U4RealCompletionError, ControlManifestError) as error:
        print(f"real U4 completion failed closed: {error}", file=sys.stderr)
        return 1

    print(f"wrote {document['artifact_count']} real U4 artifacts to {args.output_root}")
    print(f"evidence_kind=real real_execution_performed=True measurements_supplied={document['measurements_supplied']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
