"""Produce ``docs/experiment_iii/receipts/static_validation_receipt.json`` (stage A2).

Runs the authoritative entrypoint -- ``pytest tests/experiment_iii/`` -- in
process, collecting one record per test, and binds the result to the authority
hashes, the final **source closure** and the test-suite hash. A partial suite run
is not evidence, so this script always runs the whole suite; it never accepts a
filter.

The named-check coverage table is derived from the test-plan enumeration
(``A.1``-``A.30``, ``B.1``-``B.13``, ``D.1``-``D.33`` = 76 named static/CPU
checks) by matching each check's identifier against the test module and node
names that implement it.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

import numpy  # noqa: E402
import pytest  # noqa: E402

from mineocclude.experiment_iii.authority import (  # noqa: E402
    AUTHORITY_FREEZE_COMMIT,
    AUTHORITY_VERSION,
    PREDECESSOR_AUTHORITY_FREEZE_COMMIT,
    authority_sha256,
    machine_authority_sha256,
    phase0_design_sha256,
)
from mineocclude.experiment_iii.artifact_inventory import (  # noqa: E402
    stage_exit_check_fs,
)
from mineocclude.experiment_iii.source_closure import source_closure  # noqa: E402

TEST_ROOT = REPO / "tests" / "experiment_iii"
RECEIPT_PATH = REPO / "docs" / "experiment_iii" / "receipts" / "static_validation_receipt.json"

GROUP_A = tuple(f"A.{index}" for index in range(1, 31))
GROUP_B = tuple(f"B.{index}" for index in range(1, 14))
GROUP_D = tuple(f"D.{index}" for index in range(1, 34))

#: Which test module implements which named checks. The A1 modules annotate
#: their checks in the module docstring; the A2 modules are named per group.
_MODULE_CHECKS = {
    "test_cohort.py": ("A.1", "A.2", "A.3", "A.4", "A.5", "A.6", "A.19"),
    "test_q_regression.py": ("A.3", "D.2", "D.3"),
    "test_all_q_qualification.py": ("D.2", "D.3", "D.4", "D.31"),
    "test_extent_geometry.py": ("A.7", "A.8", "A.10", "A.11"),
    "test_conditions_and_schedule.py": ("A.7", "A.8", "A.9", "A.15"),
    "test_fir.py": ("A.12", "A.13"),
    "test_extraction_and_store.py": ("A.13", "A.16", "A.17", "A.18", "A.28"),
    "test_representations.py": ("A.20", "A.21", "A.22", "A.23", "A.24"),
    "test_readout_and_baselines.py": ("A.24", "A.25", "A.26", "A.27"),
    "test_rve_sentinels_status_execution.py": ("A.14", "A.15", "A.29"),
    "test_namespace_and_schema.py": ("A.19", "A.30"),
    "test_authority_binding.py": ("A.30",),
    "test_iii_b_oracle_and_cells.py": ("D.1", "D.5", "D.6", "D.7", "D.8", "D.9", "D.10"),
    "test_iii_b_statistics.py": (
        "D.11", "D.12", "D.13", "D.14", "D.15", "D.16", "D.17", "D.18", "D.19",
        "D.20", "D.32", "D.33",
    ),
    "test_iii_b_lifecycle.py": (
        "D.21", "D.22", "D.23", "D.24", "D.25", "D.26", "D.27", "D.28", "D.29", "D.30",
    ),
    "test_group_b.py": GROUP_B,
}

#: The single adversarial implementation audit of stage A2 (test plan / prompt
#: section 12): predecessor freeze -> current working tree, against v1.5.
IMPLEMENTATION_AUDIT = {
    "status": "PASS",
    "scope": "PREDECESSOR_FREEZE_TO_CURRENT_WORKING_TREE_AGAINST_V1_5",
    "passes": 1,
    "files_reviewed": 62,
    "blocking_findings": 0,
    "findings": [
        {
            "id": "AUD-01",
            "severity": "HIGH",
            "blocking": True,
            "area": "cohort / gate 12",
            "finding": (
                "qualification.qualifies_at_all_q -- the documented gate-12 "
                "primitive -- defaulted to enforce_gate_9=True, i.e. the "
                "peer-dependent gate 9 evaluated at every binding q, which is "
                "exactly the interpretation Authority Amendment 2 superseded. The "
                "production scan opted out explicitly, so the materialized cohort "
                "was correct, but the entrypoint was fail-OPEN: any other caller "
                "reached v1.4 semantics without asking for them."
            ),
            "repair": (
                "Default changed to False (the amended per-candidate scope) and "
                "threaded into both the binding-q and diagnostic-q evaluations; "
                "the stale v1.4 docstring rewritten. Cohort byte-identity "
                "re-verified end to end by B.1."
            ),
            "status": "FIXED",
        },
        {
            "id": "AUD-02",
            "severity": "MEDIUM",
            "blocking": True,
            "area": "test harness / group A",
            "finding": (
                "test_cohort.py carried a module-level pytest.mark.skipif on the "
                "presence of the materialized cohort. Group A must have zero "
                "skips; had the artifact been absent, about thirty named group-A "
                "checks would have silently vanished from an A2 run while the "
                "receipt still read 'zero failures'."
            ),
            "repair": (
                "A missing cohort now raises at collection time. It is a required "
                "A1 artifact, so its absence is a failure, never a skip."
            ),
            "status": "FIXED",
        },
        {
            "id": "AUD-03",
            "severity": "MEDIUM",
            "blocking": True,
            "area": "III-A CPU coverage",
            "finding": (
                "The task graph names no A1 task owning the A3 storage preflight, "
                "the artifact-inventory stage-exit checker, the adjudication "
                "coverage checker, or the deadline plan selector and attrition "
                "branch -- yet B.7, B.8, B.10, B.11, B.12 and B.13 bind all four "
                "at A2."
            ),
            "repair": (
                "Implemented as minimum complete frozen modules: "
                "storage_preflight.py, artifact_inventory.py, adjudication.py, "
                "deadline.py. The adjudication matrix is parsed from the hashed "
                "authority markdown rather than hand-copied, so it cannot drift."
            ),
            "status": "FIXED",
        },
        {
            "id": "AUD-04",
            "severity": "MEDIUM",
            "blocking": True,
            "area": "III-B belief-state ladder",
            "finding": (
                "assert_claim_within_rung refused 'calibrated' only where an "
                "individual rung's prohibition list happened to enumerate it. "
                "Rungs 5, 6 and 7 did not, so 'a calibrated belief state' was "
                "accepted at rung 5, against authority 28's headline rule that "
                "only rung 4 ever licenses it."
            ),
            "repair": "Explicit cross-rung rule added; D.15 and D.25 assert it.",
            "status": "FIXED",
        },
        {
            "id": "AUD-05",
            "severity": "LOW",
            "blocking": False,
            "area": "documentation",
            "finding": (
                "cohort_build.py and bprime.py module docstrings still described "
                "the superseded v1.4 candidate bound (200 / indices 0..199). "
                "Behaviour read CANDIDATE_INDEX_BOUND_PER_DIRECTION = 2000 "
                "throughout; only the prose was stale."
            ),
            "repair": "Docstrings corrected to the frozen v1.5 bound.",
            "status": "FIXED",
        },
        {
            "id": "AUD-06",
            "severity": "LOW",
            "blocking": False,
            "area": "authority data gap",
            "finding": (
                "Four EXPECTED_ARTIFACT_INVENTORY.json rows are "
                "required_before_next_stage with a NULL missing_blocker (three "
                "B-GEN III-B provenance artifacts and the B-LOCK closure "
                "receipt). A null must not read as permission to exit the stage."
            ),
            "repair": (
                "stage_exit_check fails closed under PROVENANCE_BINDING_MISSING "
                "for those rows; B.10 asserts both branches. No scientific value "
                "changes, so this is not an amendment trigger, but it is a defect "
                "in the inventory worth naming for the next authority pass."
            ),
            "status": "FIXED_WITH_DISCLOSURE",
        },
        {
            "id": "AUD-07",
            "severity": "INFORMATIONAL",
            "blocking": False,
            "area": "authority consistency",
            "finding": (
                "The 75-vs-76 named-check discrepancy is internal to the HUMAN "
                "authority: section A2 says '12 group-B checks -- 75 named "
                "checks', while section 11 and the controlling test plan both say "
                "B = 13, total 76, and the plan enumerates B.1 through B.13. The "
                "machine authority carries no group counts, so there is no "
                "human/machine disagreement of the kind that triggers "
                "AUTHORITY_AMENDMENT_REQUIRED; the 75 line is a residual "
                "predating the v1.3 R2 repair that added B.13."
            ),
            "repair": "Resolved to 76 and recorded in this receipt.",
            "status": "RESOLVED_NO_CODE_CHANGE",
        },
        {
            "id": "AUD-08",
            "severity": "INFORMATIONAL",
            "blocking": False,
            "area": "wall / fabric seam",
            "finding": (
                "EpisodeManager.buildArenaIfChanged and conditions.arena_cache_key "
                "compose the same fields in the same order with the same "
                "separator, but render floats differently (Java double toString "
                "vs Python repr). The authority requires the material to be part "
                "of the cache identity (C07), not byte equality across the seam, "
                "and the Python key is a receipt/spec artifact rather than the "
                "runtime key."
            ),
            "repair": "None required.",
            "status": "NO_CHANGE",
        },
        {
            "id": "AUD-09",
            "severity": "INFORMATIONAL",
            "blocking": False,
            "area": "adjudication",
            "finding": (
                "assert_claim_in_scope matches a claim to a row by "
                "substantive-token subset and refuses the never-established list "
                "plus each row's prohibited phrases. A claim that restates a "
                "permitted row AND appends an unlisted extra assertion would "
                "pass. No textual gate can close that."
            ),
            "repair": (
                "The never-established list is the hard backstop; B.11 tests both "
                "directions."
            ),
            "status": "NO_CHANGE",
        },
    ],
    "seam_evidence": [
        "gate 9 is evaluated once on the production cohort at the III-A q = 0.05 "
        "and excluded from the per-candidate gate-12 scope (D.4, B.1)",
        "no III-A module imports any III-B module, and no III-A lifecycle state "
        "references a B-* state (D.26)",
        "the arena cache key binds condition identity AND material identity in "
        "both the Java runtime path and the Python spec path",
        "the forbidden generators (cumsum, noise-before-drift) are reachable only "
        "from negative-control call sites and tests",
        "D.11 reproduces the frozen tau-only rho = 0.0905724833 to ten "
        "significant digits and Var(r_hat) = 351.0; D.6 reproduces the frozen "
        "unnormalized S(tau) error 9.289005120649563e-10 exactly",
    ],
}

#: Every source change made during A2, in order. Each invalidated the previous
#: suite result; the run recorded in this receipt is the one after the last.
REPAIR_HISTORY = [
    "I19/I20 test authoring: added tests/experiment_iii/integration/ (Group B, "
    "13 named checks) and the three III-B Group-D modules (D.1, D.5-D.30, D.32, "
    "D.33).",
    "Implemented the III-B CPU modules the live task graph binds at A2 but had "
    "not yet built (IB01, IB04-IB20, CPU side only): iii_b_oracle, iii_b_vis, "
    "iii_b_cells, iii_b_inference, iii_b_u2, iii_b_u3, iii_b_calibration, "
    "iii_b_status, iii_b_extraction, iii_b_gate, iii_b_package.",
    "Implemented the III-A CPU modules Group B binds: storage_preflight, "
    "artifact_inventory, adjudication, deadline; plus source_closure.",
    "AUD-01: qualifies_at_all_q now defaults to the amended gate-12 scope.",
    "AUD-02: a missing materialized cohort fails collection instead of skipping.",
    "AUD-04: only rung 4 may license a calibrated belief state.",
    "AUD-05: stale v1.4 candidate bound removed from two docstrings.",
    "AUD-06: stage_exit_check fails closed on a null missing_blocker.",
    "write_cohort gained an optional namespace_root so B.1 can exercise the real "
    "writer against a temporary tree without touching the materialized cohort.",
    "Dead helpers removed from iii_b_u2 and the Group-D statistics module.",
    # --- Pre-execution readiness remediation sprint, 2026-08-31 --------------
    # Closing PRE_EXECUTION_READINESS_AUDIT_v1_6.md. Each of these invalidated
    # the previous suite result; the run recorded here is the one after the last.
    "F-01 (BLOCKER): added p0_analysis.py and wired the complete frozen P0 "
    "analysis into run_p0_rve_calibration.py --execute. The runner captured 252 "
    "units and returned; seven of A4's eight outputs had no producer and A4's "
    "exit condition P0_SELECTION_RECEIPT was unreachable. --execute is now one "
    "transaction through stage closure, and --analyze re-closes A4 from an "
    "already-captured campaign.",
    "F-02 (HIGH): capture_p0_unit now emits the frozen WALL_MATERIAL_CHANGE probe "
    "across a material transition, and verify_unit_liveness requires it when one "
    "occurred instead of excluding the kind unconditionally.",
    "F-03 (HIGH): added capture_evidence.py. Frame tick identity now comes from "
    "the mod's client_tick.jsonl, dimensions from the PNG IHDR chunk, and "
    "read_succeeded from capture_complete.json. verify_frame_dimensions refuses "
    "any record not marked OBSERVED_PHYSICAL_EVIDENCE.",
    "F-04 (HIGH): the untracked v1.5-bound capture_schedule.json naming "
    "white/lime/blue was removed from the operational capture path and "
    "dispositioned; run_production_capture.py resolves --ladder through "
    "p0_analysis.load_selected_ladder, which admits only a genuine A4 "
    "P0_SELECTED_LADDER at P0_PASS under the current authority.",
    "F-05 (HIGH): AUTHORITY_FREEZE_COMMIT set to the v1.6 freeze a1f5dd1; it held "
    "v1.5's freeze, making current and predecessor provenance degenerate. The "
    "frozen authority was correct and was not modified.",
    "F-06 (HIGH): both JVM stdout pipes are drained by daemon threads; nothing "
    "read them after startup, so the campaign would have blocked on a full OS "
    "pipe buffer with no blocker code.",
    "F-07/F-12/F-17 (MEDIUM/LOW): the mandatory liveness probe is now a "
    "controlled toggle issued BEFORE the measured slots; the warmup is actually "
    "sent; dry-run evidence carries a distinct shape and cannot be persisted as a "
    "measurement.",
    "F-08 (MEDIUM): server replies are parsed, so a mod REFUSED response raises "
    "P0_CANDIDATE_ID_UNSUPPORTED or P0_PLACEMENT_GROSS_ERROR instead of surfacing "
    "180 s later as TIMING_CARDINALITY_MISMATCH.",
    "F-09 (MEDIUM): stage_exit_check_fs stats the real filesystem through an "
    "explicit path-alias table; the previous check compared caller-supplied "
    "strings and its only test was tautological.",
    "F-10 (MEDIUM): a failed capture unit is marked ATTEMPTED and the state saved "
    "before the error propagates, satisfying A4's 'all attempts retained'.",
    "F-11 (MEDIUM): wait_for_frames waits on capture_complete.json with "
    "drained=true and writer_errors=0 rather than on a file count.",
    "F-13/F-14/F-16 (LOW): output_root is honoured for the drained apparatus "
    "logs; the duplicated COHORT_SALT_AUTHORITY_SHA256 definition was removed; "
    "the module-scoped cohort skip now fails instead of silently dropping the "
    "frozen capture-order group.",
    "I08: sentinels.derive_envelope delegated to p0_bindings.sentinel_envelope. "
    "It had implemented a 3*stdev envelope, which is not the frozen 7.10e rule "
    "and would have produced different production invalidations from the same P0 "
    "data. Added sentinel_envelope_artifact (A4 producer) and "
    "measure_batch_boundary (production consumer), both fail-closed.",
    "R-01 (found during remediation, outside the audit): p1_pilot_plan.json was "
    "bound to authority hash 442f6a6e..., which exists nowhere in the repository, "
    "while declaring authority_version v1.6. Regenerated under v1.6.",
    "Added tests/experiment_iii/test_p0_execution_closure.py (73 tests) asserting "
    "runtime reachability, not just behaviour: every test in it would have failed "
    "on the audited source state.",
    # --- P1 GPU path repair sprint -----------------------------------------
    # The GPU extraction path was unreachable: A3 could not pass on an
    # extraction host, and no A5 extraction executor existed. No scientific
    # value changed and the frozen v1.7 authority was not amended.
    "BLOCKER A: host_preflight scoped display availability and renderer "
    "qualification to the CAPTURE host. The gate ran on both roles, so a "
    "headless GPU host failed ENV_DISPLAY_UNAVAILABLE on its way to a receipt "
    "that would have recorded the renderer as NOT_APPLICABLE. The Windows "
    "display branch also ended in 'or True', making the check unfalsifiable; it "
    "now reads the primary screen extent and can answer False.",
    "BLOCKER B: the GPU-host A3 model check raised ENV_CHECKPOINT_HASH_MISMATCH "
    "unconditionally with verified=false, so A5's 'A3 == PASS on the extraction "
    "host' entry condition was unsatisfiable. verify_model_identity now takes "
    "the operational checkpoint and VAE paths, requires ordinary files, computes "
    "real SHA-256 and compares against the authority; naming no path is still a "
    "refusal. A real CUDA probe was added under ENV_GPU_UNAVAILABLE.",
    "BLOCKER D: added the A5_EXTRACTION stage token. CAPTURE_HOST_STAGES named "
    "A5_CAPTURE but EXTRACTION_HOST_STAGES was ('A9','A10'), both production and "
    "post-P2, so frozen A5's extraction half had no stage any host could "
    "authorize. A5_EXTRACTION is deliberately NOT A9: A9 keeps its A8 / "
    "A6_FREEZE_BOUND / MODEL_INFERENCE_AUTHORIZED entry.",
    "BLOCKER C: added p1_extraction.py and run_p1_extraction.py -- the A5 pilot "
    "executor. run_extraction.py is left as the A9 production driver. The pilot "
    "path drives the frozen MineWorldAdapter boundary end to end and issues "
    "exactly one teacher_forced call per target row, harvesting layers {4,10,19} "
    "and both temporal slices from that single forward.",
    "Added p1_receipt.py and build_p1_pilot_receipt.py: A5's exit condition is "
    "p1_pilot_receipt.json == PASS and no producer existed. The receipt records "
    "BOTH implementation identities P1 spans -- the capture-side closure read out "
    "of the capture ledger and the extraction-side closure -- rather than "
    "claiming one checkpoint produced both halves.",
    "Reconciled the activation inventory filename on the authority name, "
    "extraction_inventory.json (authority 8.5 and EXPECTED_ARTIFACT_INVENTORY."
    "json). activation_inventory.json is the historical Regime-A name; the "
    "handoff manifest and runbook had it wrong.",
    "Corrected the non-frozen handoff manifest, runbook and run_p1_pilot "
    "docstring from A9 to the A5 pilot extraction stage. No scientific value "
    "changed and no frozen authority artifact was touched.",
]

#: The audit this sprint closed, and the boundary it clears.
PRE_EXECUTION_REMEDIATION = {
    "original_audit": (
        "docs/experiment_iii/audits/PRE_EXECUTION_READINESS_AUDIT_v1_6.md"
    ),
    "original_status": "FAIL",
    "original_findings": {
        "blocker": 1,
        "high": 5,
        "medium": 5,
        "low": 6,
        "informational": 4,
    },
    "closure_report": (
        "docs/experiment_iii/audits/PRE_EXECUTION_READINESS_AUDIT_CLOSURE_v1_6.md"
    ),
    "authority_changed": False,
    "authority_change_reason": (
        "none required; the stale AUTHORITY_FREEZE_COMMIT was in implementation "
        "source, not inside the frozen authority package, and the frozen v1.6 "
        "amendment correctly names v1.5 as its predecessor"
    ),
    "scientific_decisions_changed": "NONE",
    "boundary_cleared": "READY_FOR_CAPTURE_HOST_PROVISIONING",
    "capture_host_provisioned": False,
    "p0_executed": False,
}


_CHECK_IN_NODE = re.compile(r"test_([abd])(\d+)_", re.IGNORECASE)


class _Collector:
    """Records one row per test, in execution order."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.counts = {
            "passed": 0,
            "failed": 0,
            "error": 0,
            "skipped": 0,
            "xfailed": 0,
            "xpassed": 0,
        }

    def pytest_runtest_logreport(self, report) -> None:
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            if report.when == "setup" and report.outcome == "failed":
                outcome = "error"
            elif report.outcome == "skipped" and getattr(report, "wasxfail", None) is not None:
                outcome = "xfailed"
            elif report.outcome == "passed" and getattr(report, "wasxfail", None) is not None:
                outcome = "xpassed"
            else:
                outcome = report.outcome
            if outcome == "failed":
                outcome = "failed"
            self.counts[outcome] = self.counts.get(outcome, 0) + 1
            self.rows.append(
                {
                    "nodeid": report.nodeid,
                    "outcome": outcome,
                    "duration_seconds": round(float(report.duration), 4),
                }
            )


def _test_suite_sha256() -> tuple[str, int]:
    """SHA-256 over every test file, sorted by repository-relative POSIX path."""
    files = sorted(
        (path for path in TEST_ROOT.rglob("*.py") if "__pycache__" not in path.parts),
        key=lambda path: path.relative_to(REPO).as_posix(),
    )
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(REPO).as_posix().encode("utf-8"))
        digest.update(b"\n")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest(), len(files)


def _named_check_coverage(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    coverage: dict[str, dict[str, object]] = {
        check: {"tests": 0, "passed": 0, "failed": 0}
        for check in (*GROUP_A, *GROUP_B, *GROUP_D)
    }
    for row in rows:
        nodeid = str(row["nodeid"])
        module = nodeid.split("::", 1)[0].split("/")[-1]
        name = nodeid.split("::", 1)[1] if "::" in nodeid else ""
        checks: set[str] = set()
        match = _CHECK_IN_NODE.search(name)
        if match:
            candidate = f"{match.group(1).upper()}.{int(match.group(2))}"
            if candidate in coverage:
                checks.add(candidate)
        if not checks:
            checks.update(_MODULE_CHECKS.get(module, ()))
        for check in checks:
            if check not in coverage:
                continue
            coverage[check]["tests"] += 1
            if row["outcome"] == "passed":
                coverage[check]["passed"] += 1
            elif row["outcome"] in ("failed", "error"):
                coverage[check]["failed"] += 1
    return coverage


def main() -> int:
    closure_before = source_closure()
    collector = _Collector()
    started = time.time()
    exit_code = pytest.main(
        [str(TEST_ROOT), "-q", "-p", "no:randomly", "--tb=short"], plugins=[collector]
    )
    elapsed = time.time() - started
    closure_after = source_closure()
    if closure_before["source_closure_sha256"] != closure_after["source_closure_sha256"]:
        raise SystemExit(
            "SOURCE_CLOSURE_DRIFT: the source changed while the suite ran; the "
            "receipt would not describe a single closure"
        )

    # A1's artifacts must still be on disk at A2 exit, and A2's own receipt is
    # written below; both are checked against the filesystem rather than against
    # a list this script supplies to itself.
    a1_stage_exit = stage_exit_check_fs("A1", REPO)
    suite_hash, suite_files = _test_suite_sha256()
    coverage = _named_check_coverage(collector.rows)

    def group_totals(checks: tuple[str, ...]) -> dict[str, int]:
        return {
            "expected": len(checks),
            "covered": sum(1 for check in checks if coverage[check]["tests"] > 0),
            "passed": sum(1 for check in checks if coverage[check]["failed"] == 0
                          and coverage[check]["tests"] > 0),
            "failed": sum(1 for check in checks if coverage[check]["failed"] > 0),
            "tests": sum(int(coverage[check]["tests"]) for check in checks),
        }

    groups = {"A": group_totals(GROUP_A), "B": group_totals(GROUP_B), "D": group_totals(GROUP_D)}
    total_expected = sum(group["expected"] for group in groups.values())
    total_passed = sum(group["passed"] for group in groups.values())

    receipt = {
        "schema_version": "mineocclude-experiment-iii-static-validation-receipt-v1",
        "stage": "A2",
        "entrypoint": "pytest tests/experiment_iii/",
        "authority_version": AUTHORITY_VERSION,
        "authority_sha256": authority_sha256(),
        "machine_authority_sha256": machine_authority_sha256(),
        "phase0_design_sha256": phase0_design_sha256(),
        "authority_freeze_commit": AUTHORITY_FREEZE_COMMIT,
        "predecessor_authority_freeze_commit": PREDECESSOR_AUTHORITY_FREEZE_COMMIT,
        "authority_drift": False,
        "source_closure": closure_after,
        "test_suite_sha256": suite_hash,
        "test_suite_file_count": suite_files,
        "named_checks": {
            "group_a_expected": len(GROUP_A),
            "group_b_expected": len(GROUP_B),
            "group_d_expected": len(GROUP_D),
            "total_expected": total_expected,
            "total_passed": total_passed,
            "count_resolved_from": (
                "EXPERIMENT_III_TEST_PLAN.md (A 30, B 13, D 33 = 76); the machine "
                "authority carries no group counts, so there is no human/machine "
                "disagreement to adjudicate"
            ),
            "groups": groups,
            "per_check": coverage,
        },
        "pytest": {
            "exit_code": int(exit_code),
            "collected": len(collector.rows),
            "passed": collector.counts["passed"],
            "failed": collector.counts["failed"],
            "error": collector.counts["error"],
            "skipped": collector.counts["skipped"],
            "xfailed": collector.counts["xfailed"],
            "xpassed": collector.counts["xpassed"],
            "elapsed_seconds": round(elapsed, 2),
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": numpy.__version__,
            "pytest": pytest.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "resource_policy": {
            "SAGEMAKER_STARTED": False,
            "GPU_USED": False,
            "CUDA_USED": False,
            "MINEWORLD_MODEL_LOADED": False,
            "MINEWORLD_INFERENCE_RUN": False,
            "MINECRAFT_RUN": False,
        },
        "a1_stage_exit_check": a1_stage_exit,
        "implementation_audit": IMPLEMENTATION_AUDIT,
        "pre_execution_remediation": PRE_EXECUTION_REMEDIATION,
        "repair_history": REPAIR_HISTORY,
        "full_suite_rerun_after_last_source_change": True,
        "per_test": collector.rows,
        "passed": exit_code == 0
        and collector.counts["failed"] == 0
        and collector.counts["error"] == 0
        and collector.counts["skipped"] == 0
        and collector.counts["xfailed"] == 0,
    }
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    RECEIPT_PATH.write_text(payload, encoding="utf-8", newline="\n")
    print(f"wrote {RECEIPT_PATH.relative_to(REPO).as_posix()}")
    print(f"  passed={receipt['passed']} collected={receipt['pytest']['collected']}")
    print(f"  named checks {total_passed}/{total_expected}")
    print(f"  source closure {closure_after['source_closure_sha256']}")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
