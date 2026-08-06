"""Build the single Person A terminal status package for Steps 6.7 through 9.8.

The package states, for every step, what was implemented, what was really
executed, what was validated only synthetically, and what remains blocked on an
external input. It never reports a real-data step as complete from synthetic
evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.clean_run import (  # noqa: E402
    environment_hash,
    environment_report,
)
from mineocclude.experiments.mvp_config import load_mvp_config  # noqa: E402

OUTPUT_ROOT = ROOT / "docs" / "status" / "person_a_terminal_status_v0_1"
PHASE6 = ROOT / "docs" / "status" / "person_a_phase6_closeout_v0_1"
PHASE7 = ROOT / "docs" / "status" / "person_a_phase7_mvp_v0_1"
PHASE9 = ROOT / "docs" / "status" / "person_a_phase9_clean_run_v0_1"

ROADMAP_VERSION = "mineocclude-person-a-execution-roadmap-phases-6-9"

PERSON_A_TEST_SELECTION = (
    "tests/activations",
    "tests/models",
    "tests/contracts",
    "tests/intervention",
    "tests/experiments",
    "tests/integration",
    "tests/test_parquet_dependency_authority.py",
)

# Failures that are identical on a clean checkout of the starting commit. They
# are recorded here with that proof rather than repaired by rewriting preserved
# historical evidence.
PREEXISTING_FAILURES = (
    {
        "test": "tests/models/test_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py::ProductionHandoffPreflightTests::test_01_exact_authorities_are_bound",
        "kind": "expired_in_flight_preparation_guard",
    },
    {
        "test": "tests/models/test_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py::ProductionHandoffPreflightTests::test_26_builder_output_is_deterministic",
        "kind": "expired_in_flight_preparation_guard",
    },
    {
        "test": "tests/models/test_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py::ProductionHandoffPreflightTests::test_29_no_existing_tracked_file_changed",
        "kind": "expired_in_flight_worktree_scope_guard",
    },
    {
        "test": "tests/models/test_person_a_phase6_sagemaker_runner_v0_1.py::PersonAPhase6SageMakerRunnerPreparationTests::test_change_inventory_matches_exact_worktree_scope",
        "kind": "expired_in_flight_worktree_scope_guard",
    },
    {
        "test": "tests/models/test_person_a_phase6_step6_3_resume_preparation_v0_1.py::PersonAPhase6Step63ResumePreparationTests::test_adapter_request_uses_physical_not_provenance_path",
        "kind": "expired_in_flight_preparation_guard",
    },
    {
        "test": "tests/models/test_person_a_phase6_step6_3_resume_preparation_v0_1.py::PersonAPhase6Step63ResumePreparationTests::test_evidence_is_canonical_and_inventory_is_exact",
        "kind": "expired_in_flight_preparation_guard",
    },
    {
        "test": "tests/integration/test_synthetic_pipeline.py::TestSyntheticCrossRolePipeline::test_checked_machine_readable_report_matches_fresh_execution",
        "kind": "cross_machine_float64_last_ulp_difference",
    },
)

# Each entry above asserts a moment that has passed (the exact worktree scope of
# an earlier in-flight preparation package) or a byte-exact cross-machine float
# equality. They are preserved historical evidence guards, not regressions, and
# are left untouched rather than rewritten.

STEP_STATUS: dict[str, dict[str, Any]] = {
    "6.7": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "The executed ten-pilot expansion was certified from committed "
            "receipts without rerunning extraction."
        ),
        "real_execution": True,
        "evidence": [
            "docs/status/person_a_phase6_closeout_v0_1/step_6_7_certification.json",
            "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725/",
        ],
        "implementation": [
            "src/mineocclude/experiments/pilot_certification.py",
            "scripts/build_person_a_phase6_closeout_v0_1.py",
        ],
    },
    "6.8": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "Six pilot-phase changes are classified; none is result-changing. "
            "The locked extraction contract is published."
        ),
        "real_execution": True,
        "evidence": [
            "docs/status/person_a_phase6_closeout_v0_1/step_6_8_closeout.json",
            "docs/contracts/person_a_locked_extraction_contract_v1_0.md",
        ],
        "implementation": ["src/mineocclude/experiments/pilot_certification.py"],
    },
    "7.1": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "The MVP configuration is frozen, content-addressed, and separates "
            "result-changing from operational values."
        ),
        "real_execution": True,
        "evidence": [
            "configs/experiments/mvp.yaml",
            "docs/status/person_a_phase7_mvp_v0_1/step_7_1_identity_freeze.json",
            "docs/contracts/schema_v1_0_signed_record.md",
        ],
        "implementation": ["src/mineocclude/experiments/mvp_config.py"],
    },
    "7.2": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "All 66 expected cells are encoded from Person C's episode matrix "
            "and reconciled; the shortfall is published with its owner."
        ),
        "real_execution": True,
        "evidence": [
            "docs/status/person_a_phase7_mvp_v0_1/step_7_2_matrix_report.json"
        ],
        "implementation": ["src/mineocclude/experiments/mvp_matrix.py"],
    },
    "7.3": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "The nine-stage graph runs cleanly in CPU synthetic mode and blocks "
            "every stage in real mode without real entry points."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "evidence": [
            "docs/status/person_a_phase7_mvp_v0_1/step_7_3_stage_graph.json",
            "docs/status/person_a_phase7_mvp_v0_1/step_7_3_synthetic_stage_report.json",
            "docs/status/person_a_phase7_mvp_v0_1/step_7_3_real_stage_report.json",
        ],
        "implementation": [
            "src/mineocclude/experiments/stage_graph.py",
            "scripts/run_mvp.py",
        ],
    },
    "7.4": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "Person A's run/artifact ledger projects onto Person E's immutable "
            "registry schema and is accepted with zero rejections."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "evidence": [
            "docs/status/person_a_phase7_mvp_v0_1/step_7_4_synthetic_lineage.json"
        ],
        "implementation": ["src/mineocclude/experiments/mvp_lineage.py"],
    },
    "7.5": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "The queue is resumable, skips only checksum-valid work, bounds "
            "transient retries, quarantines identity/data/model failures, and "
            "never changes run identity on resume."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "evidence": [
            "docs/status/person_a_phase7_mvp_v0_1/step_7_5_queue_status.json",
            "docs/status/person_a_phase7_mvp_v0_1/extraction_queue_state.json",
        ],
        "implementation": ["src/mineocclude/experiments/extraction_queue.py"],
    },
    "7.6": {
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "summary": (
            "Cardinality, shape, duplicate, and join certification is "
            "implemented and tested. The real 66-trajectory extraction has not "
            "run because 61 accepted handoff bundles and a GPU runtime are "
            "unavailable."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "blocked_by": ["C-66-HANDOFF", "A-GPU-RUNTIME"],
        "evidence": [
            "docs/status/person_a_phase7_mvp_v0_1/step_7_2_matrix_report.json"
        ],
        "implementation": ["src/mineocclude/experiments/extraction_queue.py"],
    },
    "7.7": {
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "summary": (
            "The B/D invocation entry point and its lineage record are "
            "implemented. The invocation is recorded BLOCKED because the "
            "accepted dataset is incomplete."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "blocked_by": ["C-66-HANDOFF", "A-GPU-RUNTIME"],
        "evidence": [
            "docs/status/person_a_phase7_mvp_v0_1/step_7_7_u1_u3_invocation.json"
        ],
        "implementation": ["src/mineocclude/experiments/mvp_lineage.py"],
    },
    "7.8": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "The implementation closeout reports gate state, capacity, "
            "shortfall, and U4 prerequisites without interpreting metrics."
        ),
        "real_execution": True,
        "evidence": [
            "docs/status/person_a_phase7_mvp_v0_1/step_7_8_implementation_closeout.json"
        ],
        "implementation": ["src/mineocclude/experiments/mvp_closeout.py"],
    },
    "8.1": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "The B-to-A request validator enforces raw-space direction, "
            "layer/timestep/site, held-out separation, and cap-reduced dose "
            "reporting before any event is loaded."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "implementation": ["src/mineocclude/intervention/inject.py"],
    },
    "8.2": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "Direct tensor tests prove the nonzero difference mask equals "
            "exactly the final context frame's 336 visual positions."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "evidence": ["tests/intervention/test_inject.py"],
        "implementation": ["src/mineocclude/intervention/inject.py"],
    },
    "8.3": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "Shape, dtype, device, and output container are preserved; the hook "
            "is single-use and removed on success and on failure."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "evidence": ["tests/intervention/test_inject.py"],
        "implementation": ["src/mineocclude/intervention/inject.py"],
    },
    "8.4": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "Pooled-change identity, sign reversal, alpha-zero identity, and "
            "the 0.25 relative-norm cap are all proved numerically."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "evidence": ["tests/intervention/test_inject.py"],
        "implementation": ["src/mineocclude/intervention/inject.py"],
    },
    "8.5": {
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "summary": (
            "The manifest builder encodes 5 events x 5 shifts x 2 seeds = 50 "
            "primary clips, 20 norm-matched random-direction controls, and D "
            "control IDs, with no outcome-dependent field. It has not been "
            "frozen because Person B's final request is unpublished."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "blocked_by": ["B-DIRECTION-REQUEST"],
        "implementation": ["src/mineocclude/intervention/rollout_manifest.py"],
    },
    "8.6": {
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "summary": (
            "The resumable runner records generation failure separately from "
            "non-persistence, refuses to overwrite alpha-zero and controls, and "
            "requires a supersession record to replace a completed clip. No "
            "rollout was generated."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "blocked_by": ["B-DIRECTION-REQUEST", "A-GPU-RUNTIME"],
        "implementation": ["src/mineocclude/intervention/rollout_manifest.py"],
    },
    "8.7": {
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "summary": (
            "E and D handoff generators transfer the complete bundle with "
            "expected-versus-produced counts and apply no selection."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "blocked_by": ["B-DIRECTION-REQUEST", "A-GPU-RUNTIME", "E-DETECTOR-VERSIONS"],
        "implementation": ["src/mineocclude/intervention/rollout_manifest.py"],
    },
    "8.8": {
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "summary": (
            "The classifier fails closed: without a predeclared held-out "
            "partition it caps at plumbing-only, and a measurement or control "
            "failure yields invalid_measurement rather than a causal claim."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "blocked_by": ["B-DIRECTION-REQUEST", "A-GPU-RUNTIME", "E-MEASUREMENT-TABLES"],
        "implementation": ["src/mineocclude/intervention/rollout_manifest.py"],
    },
    "9.1": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "Clean-start identity verification, the approved external artifact "
            "resolver, and the private-directory guard are implemented and run."
        ),
        "real_execution": True,
        "evidence": [
            "docs/status/person_a_phase9_clean_run_v0_1/step_9_1_clean_start.json",
            "docs/status/person_a_phase9_clean_run_v0_1/external_artifact_index.json",
        ],
        "implementation": ["src/mineocclude/experiments/clean_run.py"],
    },
    "9.2": {
        "status": "PARTIALLY_COMPLETE",
        "summary": (
            "The one documented workflow executed all seven CPU steps from a "
            "clean checkout with full stdout/stderr and resource capture. It is "
            "recorded as WORKFLOW_VALIDATED_SYNTHETIC_ONLY, not as a clean "
            "reproduction of real outputs."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "blocked_by": ["C-66-HANDOFF", "A-GPU-RUNTIME"],
        "evidence": [
            "configs/experiments/clean_run.yaml",
            "docs/status/person_a_phase9_clean_run_v0_1/step_9_2_clean_run_record.json",
        ],
        "implementation": [
            "src/mineocclude/experiments/clean_run.py",
            "scripts/run_clean_mvp.py",
        ],
    },
    "9.3": {
        "status": "PARTIALLY_COMPLETE",
        "summary": (
            "The rtol=1e-3 / atol=1e-3 comparison logic is implemented, tested, "
            "and executed on a deterministic CPU pooled vector. Repeating a "
            "real teacher-forced forward needs the GPU runtime."
        ),
        "real_execution": False,
        "synthetic_validated": True,
        "blocked_by": ["A-GPU-RUNTIME"],
        "evidence": [
            "docs/status/person_a_phase9_clean_run_v0_1/step_9_3_repeatability.json"
        ],
        "implementation": ["src/mineocclude/experiments/clean_run.py"],
    },
    "9.4": {
        "status": "BLOCKED_BY_EXTERNAL_INPUT",
        "summary": (
            "The collection rehearsal procedure and receipt generator are "
            "complete and were executed; the rehearsal is BLOCKED at server "
            "start with two documented instruction gaps."
        ),
        "real_execution": False,
        "blocked_by": ["C-COLLECTION-RUNTIME"],
        "evidence": [
            "docs/runbooks/person_a_handoff_rehearsals.md",
            "docs/status/person_a_phase9_clean_run_v0_1/step_9_4_9_5_rehearsals.json",
        ],
        "implementation": ["src/mineocclude/experiments/checkpoint.py"],
    },
    "9.5": {
        "status": "PARTIALLY_COMPLETE",
        "summary": (
            "The Person E registry invocation rehearsal COMPLETED: E's validator "
            "accepts Person A's ledger unchanged. The D baseline invocation and "
            "E measurement invocation are BLOCKED on a complete clean run."
        ),
        "real_execution": True,
        "blocked_by": ["C-66-HANDOFF", "A-GPU-RUNTIME"],
        "evidence": [
            "docs/status/person_a_phase9_clean_run_v0_1/step_9_4_9_5_rehearsals.json"
        ],
        "implementation": ["src/mineocclude/experiments/checkpoint.py"],
    },
    "9.6": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "The checkpoint demonstration checklist publishes seven ordered, "
            "hash-bound evidence links plus one fully traced example."
        ),
        "real_execution": True,
        "evidence": [
            "docs/status/person_a_phase9_clean_run_v0_1/step_9_6_evidence_chain.json"
        ],
        "implementation": ["src/mineocclude/experiments/checkpoint.py"],
    },
    "9.7": {
        "status": "COMPLETE_AND_VERIFIED",
        "summary": (
            "The decision is YELLOW on unevaluated science, not on failed "
            "engineering. Three scope cuts are recorded, all cutting breadth "
            "before validity."
        ),
        "real_execution": True,
        "evidence": [
            "docs/status/person_a_phase9_clean_run_v0_1/step_9_7_checkpoint_decision.json"
        ],
        "implementation": ["src/mineocclude/experiments/checkpoint.py"],
    },
    "9.8": {
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "summary": (
            "The tag record and immutable external artifact index are prepared "
            "and validated. The tag is deliberately not created or pushed: "
            "final tagging is a coordinated five-role operation."
        ),
        "real_execution": False,
        "blocked_by": ["COORDINATED-TAG"],
        "evidence": [
            "docs/status/person_a_phase9_clean_run_v0_1/step_9_8_tag_record.json"
        ],
        "implementation": ["src/mineocclude/experiments/checkpoint.py"],
    },
}

EXTERNAL_BLOCKERS = (
    {
        "blocker_id": "C-66-HANDOFF",
        "owner": "person_c_data",
        "description": (
            "Person C captured all 66 C6A episodes but has published "
            "per-trajectory accepted handoff bundles to Person A for only 5 of "
            "them. The remaining 61 cells cannot be queued without inventing "
            "data."
        ),
        "next_executable_command": (
            "python scripts/run_mvp.py matrix  # re-run once C publishes the "
            "remaining accepted handoff bundles"
        ),
    },
    {
        "blocker_id": "A-GPU-RUNTIME",
        "owner": "person_a_model",
        "description": (
            "The real 66-trajectory extraction and any real rollout generation "
            "require an authorized GPU runtime with the pinned MineWorld "
            "checkpoint. No such runtime is available in this environment."
        ),
        "next_executable_command": (
            "python scripts/run_mvp.py run --mode real  # on the authorized L4 "
            "session, after C-66-HANDOFF clears"
        ),
    },
    {
        "blocker_id": "B-DIRECTION-REQUEST",
        "owner": "person_b_analysis",
        "description": (
            "Person B has not published the final hash-bound raw-space "
            "direction/dose request, the typical activation norm artifact, or "
            "the predeclared held-out event partition."
        ),
        "next_executable_command": (
            "python scripts/run_u4_rollouts.py validate-request --request "
            "<b_to_a_intervention_request.json>"
        ),
    },
    {
        "blocker_id": "E-DETECTOR-VERSIONS",
        "owner": "person_e_operations",
        "description": (
            "Person E's frozen detector and homography versions for the Week 1 "
            "measurement contract are not yet bound to a U4 handoff."
        ),
        "next_executable_command": (
            "python scripts/run_u4_rollouts.py handoff --bundle "
            "docs/status/person_a_phase8_u4_v0_1/step_8_6_rollout_bundle.json "
            "--detector-version <v> --homography-version <v>"
        ),
    },
    {
        "blocker_id": "E-MEASUREMENT-TABLES",
        "owner": "person_e_operations",
        "description": (
            "U4 classification needs Person E's persistence, displacement, and "
            "SSIM tables, which require generated rollouts."
        ),
        "next_executable_command": (
            "python scripts/run_u4_rollouts.py classify --bundle <bundle> "
            "--measurement <e_tables> --injection-audit <audit>"
        ),
    },
    {
        "blocker_id": "C-COLLECTION-RUNTIME",
        "owner": "person_c_data",
        "description": (
            "The Step 9.4 collection rehearsal needs a Minecraft server, a Java "
            "runtime, and the approved credential channel, plus two documented "
            "runbook instruction gaps closed."
        ),
        "next_executable_command": (
            "python scripts/run_clean_mvp.py rehearsals  # on a machine with "
            "C's documented server runtime"
        ),
    },
    {
        "blocker_id": "COORDINATED-TAG",
        "owner": "all_roles",
        "description": (
            "The mvp-2026-07-26 tag is created only after coordinated five-role "
            "integration and review. It is never created or pushed from "
            "role/person-a-model."
        ),
        "next_executable_command": (
            "git tag -a mvp-2026-07-26  # on the integration branch, after "
            "five-role review, not from this role branch"
        ),
    },
)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, document: Any) -> str:
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    args = parser.parse_args()

    config = load_mvp_config(ROOT / "configs" / "experiments" / "mvp.yaml")
    certification = load_json(PHASE6 / "step_6_7_certification.json") or {}
    closeout6 = load_json(PHASE6 / "step_6_8_closeout.json") or {}
    matrix = load_json(PHASE7 / "step_7_2_matrix_report.json") or {}
    queue = load_json(PHASE7 / "step_7_5_queue_status.json") or {}
    closeout7 = load_json(PHASE7 / "step_7_8_implementation_closeout.json") or {}
    clean_start = load_json(PHASE9 / "step_9_1_clean_start.json") or {}
    clean_run = load_json(PHASE9 / "step_9_2_clean_run_record.json") or {}
    repeat = load_json(PHASE9 / "step_9_3_repeatability.json") or {}
    rehearsals = load_json(PHASE9 / "step_9_4_9_5_rehearsals.json") or {}
    decision = load_json(PHASE9 / "step_9_7_checkpoint_decision.json") or {}
    tag_record = load_json(PHASE9 / "step_9_8_tag_record.json") or {}

    inventory = {}
    for root in (PHASE6, PHASE7, PHASE9):
        for path in sorted(root.rglob("*.json")):
            inventory[path.relative_to(ROOT).as_posix()] = sha256_file(path)
    for extra in (
        ROOT / "configs" / "experiments" / "mvp.yaml",
        ROOT / "configs" / "experiments" / "clean_run.yaml",
        ROOT / "docs" / "contracts" / "person_a_locked_extraction_contract_v1_0.md",
        ROOT / "docs" / "runbooks" / "person_a_handoff_rehearsals.md",
    ):
        inventory[extra.relative_to(ROOT).as_posix()] = sha256_file(extra)

    document = {
        "schema_version": "person-a-terminal-status-v0.1",
        "roadmap_version": ROADMAP_VERSION,
        "scope": "Person A Steps 6.7 through 9.8",
        "branch": "role/person-a-model",
        "starting_commit": "be2d53051073bab633c29b2540dcce9f91553938",
        "origin_main": git("rev-parse", "origin/main"),
        "input_authorities": {
            "person_b_analysis": git("rev-parse", "origin/role/person-b-analysis"),
            "person_c_data": git("rev-parse", "origin/role/person-c-data"),
            "person_d_baselines": git("rev-parse", "origin/role/person-d-baselines"),
            "person_e_operations": git(
                "rev-parse", "origin/role/person-e-operations"
            ),
        },
        "identity": {**config.identity(), "code_sha": git("rev-parse", "HEAD")},
        "model_runtime_identity": {
            "model": "mineworld-700m",
            "source_revision": config.get("model.source_revision"),
            "asset_revision": config.get("model.asset_revision"),
            "checkpoint_sha256": config.get("model.checkpoint_sha256"),
            "vae_checkpoint_sha256": config.get("model.vae_checkpoint_sha256"),
            "decoder_layer_count": config.get("model.decoder_layer_count"),
            "precision": config.get("model.precision"),
            "reference_gpu": "NVIDIA L4",
            "extraction_seed": config.extraction_seed,
        },
        "frozen_evidence": {
            "c6a_package_sha256": (
                "612b03fea372d10c5f5b87cb581dd5f993035112e16aa1de7341801bdc35a9ef"
            ),
            "five_layout_collection_sha256": (
                "a672c834e8af3fd12c735e4042951b7b90d0aeeed5b0b62790aacdf3a58c0db0"
            ),
            "b_positive_control_receipt_sha256": (
                "9727da466b0a36a5ec5e7f2e13e1a9d34ef7b3bd470775a69ac8770e5f84b4a7"
            ),
            "e_successor_provenance_receipt_sha256": (
                "946a856bf704b43c13ba08ba692bda49cc2ecea4c1cc15096a35c53b31c522b3"
            ),
            "a6_6_closure_sha256": (
                "2d14de6557b642427a3beec2413e0f47e592117da39c5e26450ca649e8d2c770"
            ),
            "all_remain_valid": True,
            "rerun_or_relabelled": False,
        },
        "scientific_decisions": {
            "step_4_1_decision": "FAIL",
            "step_4_1_rerun_or_relabelled": False,
            "step_6_7_certified_without_rerun": True,
            "a6_6_status": "A6_6_COMPLETE",
            "u4_classification": "not_run; classifier fails closed",
            "checkpoint_decision": decision.get("decision"),
            "checkpoint_rationale": decision.get("rationale"),
            "metrics_interpreted_by_person_a": False,
        },
        "step_status": STEP_STATUS,
        "ten_pilot": {
            "trajectory_count": 10,
            "activation_row_count": (
                certification.get("cardinality", {}).get(
                    "total_activation_row_count"
                )
            ),
            "chunk_count": (
                certification.get("cardinality", {}).get("total_chunk_count")
            ),
            "model_frame_count": (
                certification.get("cardinality", {}).get("total_frame_count")
            ),
            "admitted_frame_count": (
                certification.get("exclusions", {}).get(
                    "downstream_admitted_frame_count"
                )
            ),
            "excluded_frame_count": (
                certification.get("exclusions", {}).get(
                    "downstream_excluded_frame_count"
                )
            ),
            "combined_activation_index_sha256": (
                certification.get("activation_index", {}).get(
                    "combined_activation_index_sha256"
                )
            ),
            "repository_input_hash_mismatch_count": 0,
        },
        "mvp_matrix": {
            "expected_cell_count": matrix.get("expected_cell_count"),
            "accepted_cell_count": matrix.get("accepted_cell_count"),
            "shortfall_count": matrix.get("shortfall_count"),
            "shortfall_owners": matrix.get("shortfall_owners"),
            "extraction_complete": bool(matrix.get("complete")),
        },
        "queue_state": {
            "run_id": queue.get("run_id"),
            "identity_digest": queue.get("identity_digest"),
            "item_count": queue.get("item_count"),
            "state_counts": queue.get("state_counts"),
        },
        "runtime_storage_forecast": (certification.get("forecast") or {}),
        "measured_rates": (
            certification.get("benchmark", {}).get("seconds_per_frame"),
            certification.get("benchmark", {}).get("bytes_per_frame"),
        ),
        "rollout_counts": {
            "expected_primary_clip_count": config.get(
                "u4_pilot.primary_clip_count"
            ),
            "expected_random_direction_control_count": config.get(
                "u4_pilot.random_direction_control_count"
            ),
            "generated_clip_count": 0,
            "generation_blocked": True,
        },
        "execution_summary": {
            "real_runs_executed": [
                "Phase 6 ten-pilot extraction on SageMaker L4 "
                "(session person-a-phase6-ten-pilot-expansion-seed-20260725), "
                "certified in this sprint without rerun",
                "Phase 6 canonical five-layout multi-layout successor extraction",
            ],
            "synthetic_only_validations": [
                "Step 7.3 integrated stage graph, CPU synthetic mode",
                "Step 7.4 run/artifact lineage against Person E's validator",
                "Step 7.5 queue resume, retry, and quarantine behaviour",
                "Steps 8.1-8.4 direct-tensor injection proofs (no model weights)",
                "Steps 8.5-8.8 manifest, runner, handoff, and classifier logic",
                "Step 9.2 clean-run workflow execution",
                "Step 9.3 repeatability comparison on a deterministic CPU vector",
            ],
            "mvp_extraction_complete": bool(matrix.get("complete")),
            "u1_u3_execution_complete": False,
            "u4_real_rollout_complete": False,
            "clean_reproduction_complete": bool(
                clean_run.get("clean_reproduction_of_real_outputs")
            ),
        },
        "clean_run": {
            "clean_start_status": clean_start.get("status"),
            "workflow_status": clean_run.get("status"),
            "all_documented_steps_passed": clean_run.get(
                "all_documented_steps_passed"
            ),
            "repeatability_gate": repeat.get("reproducibility_gate"),
            "repeatability_max_absolute_difference": repeat.get(
                "max_absolute_difference"
            ),
            "rehearsals_all_completed": rehearsals.get("all_rehearsals_completed"),
            "documented_instruction_gap_count": len(
                rehearsals.get("documented_instruction_gaps", [])
            ),
        },
        "release": {
            "tag_name": tag_record.get("tag_name"),
            "tag_created": tag_record.get("tag_created"),
            "tag_pushed": False,
            "tag_record_status": tag_record.get("status"),
            "final_tagging_is_coordinated_five_role_operation": True,
        },
        "focused_tests": {
            "interpreter": "C:/Users/lollo/MineOcclude-TestRunner/Scripts/python.exe",
            "selection": list(PERSON_A_TEST_SELECTION),
            "command": (
                "C:/Users/lollo/MineOcclude-TestRunner/Scripts/python.exe -m pytest "
                + " ".join(PERSON_A_TEST_SELECTION)
                + " -q"
            ),
            "result": "7 failed, 887 passed, 1 skipped, 632 subtests passed",
            "new_person_a_tests_added": 239,
            "new_person_a_tests_passing": 239,
            "new_person_a_test_failures": 0,
            "preexisting_failure_count": len(PREEXISTING_FAILURES),
            "preexisting_failures": list(PREEXISTING_FAILURES),
            "preexisting_failure_proof": (
                "The identical selection was run in a detached worktree at the "
                "starting commit be2d530; all seven failures listed here also "
                "fail there on a clean checkout. That baseline run reported 17 "
                "failed / 9 errors; this branch reports 7 failed / 0 errors."
            ),
            "repaired_in_this_sprint": [
                "tests/test_parquet_dependency_authority.py::"
                "test_every_prequalified_environment_dependency_is_preserved "
                "(compared against HEAD, which only held while the pyarrow "
                "change was uncommitted; now pinned to the pre-pyarrow commit)",
                "tests/test_parquet_dependency_authority.py::"
                "test_external_mineworld_dependency_file_is_untouched "
                "(a generated __pycache__ is not a dependency modification)",
                "tests/models/test_person_a_step6_runtime_acknowledgement_v0_1.py "
                "(passed once the external cache directory was cleaned)",
                "tests/models/test_mineworld_adapter_wave2.py "
                "(9 collection errors cleared with the external cache)",
                "src/mineocclude/models/_mineworld_adapter_wave2.py::"
                "_inspect_source (importing the pinned source writes a bytecode "
                "cache into it, which made the next cleanliness check fail; a "
                "generated cache is now excluded while any tracked change still "
                "marks the checkout unclean)",
                "tests/models/test_mineworld_adapter_wave3.py and _wave4.py "
                "(same cache-tolerant cleanliness predicate)",
                "tests/activations/test_phase4_wave2_probe.py and "
                "test_phase4_wave3_probe.py (the probe refuses to start once "
                "torch is imported, which is correct for its fresh-process CLI "
                "use; the tests now supply that documented precondition instead "
                "of requiring torch to be globally absent from the pytest "
                "session)",
            ],
        },
        "immutable_artifact_inventory": dict(sorted(inventory.items())),
        "external_blockers": list(EXTERNAL_BLOCKERS),
        "local_work_remaining": [],
        "environment": environment_report(),
        "environment_hash": environment_hash(),
        "no_real_data_step_claimed_from_synthetic_evidence": True,
    }

    digest = write_json(
        Path(args.output_root) / "person_a_terminal_status.json", document
    )
    write_json(
        Path(args.output_root) / "sha256_inventory.json",
        {
            "schema_version": "person-a-terminal-status-inventory-v0.1",
            "person_a_terminal_status.json": digest,
            "artifact_count": len(inventory),
        },
    )
    print(
        json.dumps(
            {
                "package": (
                    Path(args.output_root) / "person_a_terminal_status.json"
                )
                .relative_to(ROOT)
                .as_posix(),
                "sha256": digest,
                "steps": len(STEP_STATUS),
                "external_blockers": len(EXTERNAL_BLOCKERS),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
