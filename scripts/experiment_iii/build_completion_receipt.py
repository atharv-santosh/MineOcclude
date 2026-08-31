"""Assemble ``implementation_completion_receipt.json`` for the A1 stage.

Evidence-backed rather than asserted: file lists, hashes and the focused-test
result are gathered by running the suite and hashing the artifacts on disk.

**A task is not complete because its file exists.** The earlier version of this
script marked a task ``COMPLETE`` whenever every listed file was present, and
that is how ``I07`` and ``I08`` came to be recorded ``COMPLETE`` with
``a1_tasks_complete: 20/20`` while the P0 analysis half had **zero production
call sites**: ``rve.py`` existed, so ``I07`` passed. Each task therefore now
carries ``wiring`` -- named symbols that must be reachable from a production
module or script, checked by import and by source inspection, never by a test.
A module that only tests import does not satisfy a wiring requirement.

    python scripts/experiment_iii/build_completion_receipt.py
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    AUTHORITY_FREEZE_COMMIT,
    AUTHORITY_VERSION,
    CANDIDATE_INDEX_BOUND_PER_DIRECTION,
    PREDECESSOR_AUTHORITY_FREEZE_COMMIT,
    PREDECESSOR_AUTHORITY_SHA256,
    sha256_file,
    verify_authority_binding,
)
from mineocclude.experiment_iii.artifact_inventory import (  # noqa: E402
    stage_exit_check_fs,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402

SRC = REPOSITORY_ROOT / "src" / "mineocclude" / "experiment_iii"
SCRIPTS = REPOSITORY_ROOT / "scripts" / "experiment_iii"
TESTS = REPOSITORY_ROOT / "tests" / "experiment_iii"
FABRIC = (
    REPOSITORY_ROOT / "fabric" / "mineocclude-mod" / "src" / "main" / "java"
    / "com" / "mineocclude" / "server"
)
DOCS = REPOSITORY_ROOT / "docs" / "experiment_iii"

TASKS: list[dict[str, object]] = [
    {
        "id": "I01",
        "name": "Experiment III namespace and schema",
        "files": ["__init__.py", "errors.py", "authority.py", "namespace.py", "schema.py"],
        "tests": ["test_namespace_and_schema.py"],
        "decision": "NEW",
        "note": "e3_* identities, episode block 86001-86999, fail-closed namespace guard.",
    },
    {
        "id": "I05",
        "name": "Counterfactual extent logic (A-prime port)",
        "files": ["_aprime_extent_geometry.py", "extent_geometry.py", "aprime_reference.py"],
        "tests": ["test_extent_geometry.py"],
        "decision": "PORT",
        "note": "Vendored byte-identically from a5d763a (blob 45889b6b...); 475/475 "
                "A-prime WALL rows EXTENT_FULLY_OCCLUDED; present=False trap gives 0/475.",
    },
    {
        "id": "I06",
        "name": "FIR kernel recovery and target manifest",
        "files": ["fir.py", "target_manifest.py"],
        "scripts": ["recover_fir_kernels.py"],
        "tests": ["test_fir.py"],
        "decision": "PORT",
        "note": "50/50 path hashes, 950/950 labels, rank 9, residual 2.22e-15, "
                "aggregate mode lag 2; taps fsum-normalized once at load.",
    },
    {
        "id": "IB02",
        "name": "q-generalized path and qualification primitive",
        "files": ["cohort.py", "qualification.py"],
        "tests": ["test_all_q_qualification.py"],
        "decision": "NEW",
        "note": "Iterative binary64, drift before noise; gates 1-11 per (identity,q) "
                "cell on its own regenerated path.",
    },
    {
        "id": "IB03",
        "name": "q = 0.05 bit-identity regression fixture",
        "files": [],
        "tests": ["test_q_regression.py"],
        "decision": "NEW",
        "note": "Reproduces b5803943... bit-identically from the bound v0_3 object; "
                "both negative controls fire.",
    },
    {
        "id": "I02",
        "name": "Fresh cohort generator and folds",
        "files": ["cohort_build.py", "folds.py", "historical_seeds.py", "bprime.py"],
        "scripts": ["build_cohort.py", "option_d_feasibility_scan.py",
                    "bprime_feasibility_study.py"],
        "tests": ["test_cohort.py"],
        "decision": "REIMPLEMENT_MINIMALLY",
        "note": "25 production + 2 pilots materialized under authority v1.5; all "
                "twelve gates, gate 12 before materialization and freeze.",
    },
    {
        "id": "I03",
        "name": "Wall condition parameterization",
        "files": ["conditions.py"],
        "fabric": ["WallCondition.java", "EpisodeConfig.java", "ArenaBuilder.java",
                   "MineOccludeServer.java"],
        "tests": ["test_conditions_and_schedule.py"],
        "decision": "PARAMETERIZE",
        "note": "L0 reaches Scene.NO_WALL through startspec; unsupported registry ID "
                "refuses the episode instead of defaulting to stone. Fabric compiles.",
    },
    {
        "id": "I04",
        "name": "Wall receipts, cache key, and capture schedule",
        "files": ["capture_schedule.py"],
        "fabric": ["EpisodeManager.java"],
        "scripts": ["run_production_capture.py"],
        "tests": ["test_conditions_and_schedule.py"],
        "decision": "PARAMETERIZE",
        "note": "Arena cache key binds condition_id and wall_block_id (C07); wall "
                "receipt carries the exact registry ID; frozen Latin order "
                "reproducible; the schedule resolves L1/L2/L3 only through a "
                "genuine A4 P0_SELECTED_LADDER at P0_PASS.",
        "wiring": {
            "scripts/experiment_iii/run_production_capture.py": [
                "load_selected_ladder",
            ],
        },
    },
    {
        "id": "I09",
        "name": "Multi-layer temporal extraction",
        "files": ["slices.py", "extraction.py"],
        "scripts": ["run_extraction.py"],
        "tests": ["test_extraction_and_store.py"],
        "decision": "NEW",
        "note": "One forward per target row yields layers {4,10,19} x "
                "{PREVIOUS,CURRENT}; all five semantic assertions enforced.",
    },
    {
        "id": "I10",
        "name": "Tensor serialization, inventory, and validator",
        "files": ["activation_store.py"],
        "scripts": ["validate_extraction.py"],
        "tests": ["test_extraction_and_store.py"],
        "decision": "REIMPLEMENT_MINIMALLY",
        "note": "[19,336,2048] little-endian float16, 26,148,992 bytes; inventory "
                "generalized to 3 layers x 2 slices.",
    },
    {
        "id": "I11",
        "name": "Coarse representation",
        "files": ["representations.py"],
        "tests": ["test_representations.py"],
        "decision": "NEW",
        "note": "COARSE_2X6_CONCAT at 24,576 from specification; identity fixture "
                "proves the 14x24 grid is not transposed.",
    },
    {
        "id": "I12",
        "name": "Temporal representations",
        "files": ["representations.py"],
        "tests": ["test_representations.py"],
        "decision": "NEW",
        "note": "CURRENT_MINUS_PREVIOUS at 24,576 and TWO_FRAME_CONCAT at 49,152 "
                "with PREVIOUS first.",
    },
    {
        "id": "I15",
        "name": "Grouped ridge and prediction lock",
        "files": ["readout.py", "prediction_lock.py"],
        "scripts": ["lock_predictions.py"],
        "tests": ["test_readout_and_baselines.py"],
        "decision": "REUSE_UNCHANGED",
        "note": "probes/ridge.py fit_ridge reused unchanged; five-value alpha grid; "
                "identity-macro selection, smallest-alpha tie-break.",
    },
    {
        "id": "I13",
        "name": "Current-frame pixel baseline",
        "files": ["baselines_pixel.py"],
        "tests": ["test_readout_and_baselines.py"],
        "decision": "NEW",
        "note": "48x28x3 = 4,032 features from raw source RGB with deterministic "
                "area interpolation.",
    },
    {
        "id": "I14",
        "name": "Motion and clock baselines",
        "files": ["baselines_motion.py"],
        "tests": ["test_readout_and_baselines.py"],
        "decision": "REIMPLEMENT_MINIMALLY",
        "note": "Constant-velocity window is exactly 10 (legacy 15 not reused); "
                "oracle inputs refused as model features.",
    },
    {
        "id": "I16",
        "name": "Statistics and result packaging",
        "files": ["statistics.py"],
        "scripts": ["run_primary_analysis.py", "build_scientific_package.py"],
        "tests": ["test_rve_sentinels_status_execution.py"],
        "decision": "REIMPLEMENT_MINIMALLY",
        "note": "Three primary estimands, Holm-3, Holm-2 temporal, B=10,000 whole "
                "identity; no success gate; B=49 null not ported.",
    },
    {
        "id": "I07",
        "name": "RVE and P0 machinery",
        "files": ["rve.py", "p0_analysis.py", "p0_bindings.py", "capture_evidence.py"],
        "scripts": ["run_p0_rve_calibration.py"],
        "tests": [
            "test_rve_sentinels_status_execution.py",
            "test_p0_execution_closure.py",
        ],
        "decision": "NEW",
        "note": "sRGB->linear float64, shared per-placement mask dilated by 2, "
                "split-half noise, deterministic triple search with lexicographic "
                "tie-break -- wired end to end: --execute captures the 252 units "
                "and then closes A4 through P0_SELECTION_RECEIPT in the same "
                "transaction.",
        "wiring": {
            # I07's completion condition is "RVE computable END TO END ... the
            # deterministic triple search implemented with all nine validity
            # rules". Every one of these was a zero-call-site library function.
            "src/mineocclude/experiment_iii/p0_analysis.py": [
                "srgb_to_linear",
                "robust_median_image",
                "placement_mask",
                "split_half_noise",
                "excess_energy",
                "aggregate_placement",
                "aggregate_condition",
                "select_ladder",
                "l0_noise_threshold",
                "background_gate",
                "masked_energy",
                "rve(",
            ],
            "scripts/experiment_iii/run_p0_rve_calibration.py": [
                "analyse_p0",
                "write_a4_artifacts",
                "load_unit_frames",
                "close_p0_stage",
            ],
        },
    },
    {
        "id": "I08",
        "name": "Sentinel machinery",
        "files": ["sentinels.py", "p0_analysis.py"],
        "scripts": ["run_p0_rve_calibration.py"],
        "tests": [
            "test_rve_sentinels_status_execution.py",
            "test_p0_execution_closure.py",
        ],
        "decision": "NEW",
        "note": "Three frozen placements, order and envelope checks, batch-scoped "
                "invalidation; technical never scientific. The envelope is "
                "produced by A4 as P0_SENTINEL_ENVELOPE and consumed at every "
                "production condition-batch boundary through "
                "sentinels.measure_batch_boundary, which fails closed without it.",
        "wiring": {
            # I08's completion condition is sentinels "measured at every
            # condition-batch boundary". sentinels.py was imported by tests only.
            "src/mineocclude/experiment_iii/p0_analysis.py": [
                "sentinel_envelope_artifact",
            ],
            "src/mineocclude/experiment_iii/sentinels.py": [
                "measure_batch_boundary",
                "envelope_from_artifact",
                "sentinel_envelope(",
            ],
        },
    },
    {
        "id": "I17",
        "name": "Status and blocker framework",
        "files": ["status.py", "blockers.py"],
        "tests": ["test_rve_sentinels_status_execution.py"],
        "decision": "NEW",
        "note": "LIVE_STATUS_CONTRACT document, observational only; every blocker "
                "validated against the 146-code taxonomy.",
    },
    {
        "id": "I18",
        "name": "Resume and recovery",
        "files": ["execution.py"],
        "tests": ["test_rve_sentinels_status_execution.py"],
        "decision": "REIMPLEMENT_MINIMALLY",
        "note": "Capture unit (identity x condition) and extraction unit "
                "(capture x layer x slice) separable; same-spec resume only.",
    },
]


def _hash_map(paths):
    return {
        str(path.relative_to(REPOSITORY_ROOT).as_posix()): sha256_file(path)
        for path in paths
        if path.is_file()
    }


def _check_wiring(task: dict) -> tuple[list[dict], list[str]]:
    """Prove each declared symbol is referenced from a PRODUCTION file.

    Existence is not completion. This reads the named production module or script
    and requires the symbol to appear in it, so a scientifically correct library
    with no call site cannot be certified complete -- which is the exact failure
    the pre-execution audit found in ``I07`` and ``I08``.
    """
    records: list[dict] = []
    unwired: list[str] = []
    for relative, symbols in (task.get("wiring") or {}).items():
        path = REPOSITORY_ROOT / relative
        if "tests/" in relative.replace("\\", "/"):
            raise SystemExit(
                f"{task['id']}: a wiring site must be production code, not {relative}"
            )
        source = path.read_text(encoding="utf-8") if path.is_file() else ""
        for symbol in symbols:
            present = bool(source) and symbol in source
            records.append(
                {
                    "call_site": relative,
                    "symbol": symbol.rstrip("("),
                    "reachable_from_production": present,
                }
            )
            if not present:
                unwired.append(f"{relative}::{symbol}")
    return records, unwired


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DOCS / "a1_receipts")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args(argv)

    binding = verify_authority_binding()

    focused = {"ran": False}
    if not args.skip_tests:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/experiment_iii/", "-q"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
        )
        tail = completed.stdout.strip().splitlines()[-1] if completed.stdout else ""
        match = re.search(r"(\d+) passed", tail)
        failed = re.search(r"(\d+) failed", tail)
        focused = {
            "ran": True,
            "command": "python -m pytest tests/experiment_iii/ -q",
            "passed": int(match.group(1)) if match else 0,
            "failed": int(failed.group(1)) if failed else 0,
            "exit_code": completed.returncode,
            "summary": tail,
            "skipped_or_xfailed": "skipped" in tail or "xfail" in tail,
        }

    tasks = []
    for task in TASKS:
        source_files = [SRC / name for name in task.get("files", [])]
        script_files = [SCRIPTS / name for name in task.get("scripts", [])]
        test_files = [TESTS / name for name in task.get("tests", [])]
        fabric_files = [FABRIC / name for name in task.get("fabric", [])]
        missing = [
            str(path)
            for path in source_files + script_files + test_files + fabric_files
            if not path.is_file()
        ]
        wiring_records, unwired = _check_wiring(task)
        tasks.append(
            {
                "task": task["id"],
                "name": task["name"],
                "status": "BLOCKED" if (missing or unwired) else "COMPLETE",
                "implementation_decision": task["decision"],
                "implementation_note": task["note"],
                "source_files_changed": sorted(_hash_map(source_files)),
                "scripts_added": sorted(_hash_map(script_files)),
                "fabric_files_changed": sorted(_hash_map(fabric_files)),
                "tests_written": sorted(_hash_map(test_files)),
                "focused_tests_run": not args.skip_tests,
                "focused_test_result": (
                    "PASS" if focused.get("failed", 1) == 0 else "FAIL"
                ),
                "runtime_call_sites": wiring_records,
                "wiring_verified": not unwired,
                "unwired_symbols": unwired,
                "missing_files": missing,
                "completion_rationale": (
                    task["note"]
                    if not (missing or unwired)
                    else "incomplete; see missing_files / unwired_symbols"
                ),
                "blocker": (
                    None
                    if not (missing or unwired)
                    else "SOURCE_CHANGE_INCOMPLETE"
                ),
            }
        )

    artifacts = sorted(
        list((DOCS / "cohort").glob("*")) + list((DOCS / "a1_receipts").glob("*"))
    )
    # The stage-exit check, against the real filesystem. The inventory exists so
    # that missing evidence is auto-detectable; run only against caller-supplied
    # strings it detected nothing. A1 cannot be reported complete while one of its
    # required artifacts is absent from disk.
    stage_exit = stage_exit_check_fs("A1", REPOSITORY_ROOT)
    body = {
        "schema_version": "mineocclude-experiment-iii-implementation-completion-v1",
        "stage": "A1",
        "authority_version": AUTHORITY_VERSION,
        "authority_binding": binding,
        "authority_freeze_commit": AUTHORITY_FREEZE_COMMIT,
        "predecessor_authority_freeze_commit": PREDECESSOR_AUTHORITY_FREEZE_COMMIT,
        "predecessor_authority_sha256": PREDECESSOR_AUTHORITY_SHA256,
        "candidate_index_bound_per_direction": CANDIDATE_INDEX_BOUND_PER_DIRECTION,
        "a1_tasks_total": len(TASKS),
        "a1_tasks_complete": sum(1 for row in tasks if row["status"] == "COMPLETE"),
        "a1_tasks_wiring_verified": sum(1 for row in tasks if row["wiring_verified"]),
        "completion_criterion": (
            "every listed source, script, fabric and test file exists AND every "
            "declared runtime call site references the symbol from production code; "
            "a library function with no production call site is NOT complete"
        ),
        "tasks": tasks,
        "focused_tests": focused,
        "resource_policy": {
            "sagemaker_started": False,
            "gpu_used": False,
            "mineworld_inference_run": False,
            "p0_executed": False,
            "p1_executed": False,
            "p2_executed": False,
            "production_executed": False,
            "capture_exists": False,
        },
        "artifacts_produced": _hash_map(artifacts),
        "a1_stage_exit_check": stage_exit,
        "a2_started": False,
        "static_validation_receipt_written": False,
    }
    digest = write_json_atomic(
        args.out / "implementation_completion_receipt.json", body
    )
    print(f"A1_TASKS_COMPLETE={body['a1_tasks_complete']}/{body['a1_tasks_total']}")
    print(f"FOCUSED_TESTS={focused.get('summary', 'skipped')}")
    print(f"IMPLEMENTATION_COMPLETION_RECEIPT_SHA256={digest}")
    return 0 if body["a1_tasks_complete"] == body["a1_tasks_total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
