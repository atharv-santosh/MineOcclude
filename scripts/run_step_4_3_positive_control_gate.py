"""Run Step 4.3's no-wall positive-control gate and persist the report.

This is explicitly a machinery-evidence run, not a scientific result:
real no-wall rows, a real Person B fold manifest, and real oracle
targets do not exist yet anywhere in this repository (see
``docs/status/person_d_real_pilot_baseline_preview.json`` and the
Phase 1 decision log for the current state of Person A/B/C handoffs).
This script runs the gate against the same synthetic fixtures used in
``tests/baselines/test_positive_control_gate.py``, with
``data_provenance`` honestly labeled as non-real, so the gate reports
``BLOCKED`` -- proving the machinery (ridge fit, R^2, bootstrap CI) is
wired correctly and fails closed, without claiming anything about the
model's actual hidden-state representation.

Usage:
    python scripts/run_step_4_3_positive_control_gate.py [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.baselines.interface import TrajectoryContext  # noqa: E402
from mineocclude.baselines.positive_control_gate import (  # noqa: E402
    evaluate_no_wall_positive_control_gate,
)

FOLD_FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "person_d" / "synthetic_b_fold_manifest.json"
)

#: Same 5-layout, all-visible, perfect-linear-signal construction as
#: the "clean pass" unit test in test_positive_control_gate.py --
#: deliberately labeled non-real below, so this run proves the
#: arithmetic works without ever claiming a scientific PASSED.
LAYOUTS = tuple("abcde")
NON_REAL_DATA_PROVENANCE = "synthetic_fixture_no_real_no_wall_capture_exists_yet"


def _build_synthetic_no_wall_inputs():
    contexts = []
    mu_oracle_by_key = {}
    for layout in LAYOUTS:
        for frame_idx, position in enumerate((0.0, 1.0, 2.0)):
            contexts.append(
                TrajectoryContext(
                    trajectory_id=f"traj-{layout}",
                    layout_id=f"layout-{layout}",
                    model_frame_idx=frame_idx,
                    fold=-1,
                    regime="A",
                    tau_seconds=0.0,
                    visibility=True,
                    last_seen_position_blocks=position,
                    last_seen_velocity_blocks_per_s=None,
                    v_scripted_blocks_per_s=None,
                    q_scripted_blocks2_per_s=None,
                    duration_seconds=None,
                    config_hash="cfg-test",
                    seed=123,
                )
            )
            mu_oracle_by_key[(f"traj-{layout}", frame_idx)] = position
    return contexts, mu_oracle_by_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    fold_manifest = json.loads(FOLD_FIXTURE_PATH.read_text(encoding="utf-8"))
    contexts, mu_oracle_by_key = _build_synthetic_no_wall_inputs()

    finding = evaluate_no_wall_positive_control_gate(
        contexts,
        mu_oracle_by_key,
        fold_manifest=fold_manifest,
        data_provenance=NON_REAL_DATA_PROVENANCE,
    )

    report = {
        "report_type": "person_d_step_4_3_positive_control_gate",
        "scientific_use": "forbidden",
        "reason": (
            "no real no-wall rows, real Person B fold manifest, or real "
            "oracle targets exist yet; this run exercises the gate's "
            "ridge/R^2/bootstrap machinery against the same synthetic "
            "fixture used in tests/baselines/test_positive_control_gate.py, "
            "with data_provenance honestly labeled as non-real, so the gate "
            "reports BLOCKED rather than a scientific PASSED/FAILED verdict"
        ),
        "gate_finding": asdict(finding),
    }

    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
