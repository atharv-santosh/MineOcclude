"""Execute and record the Person A clean-run workflow and checkpoint package.

    python scripts/run_clean_mvp.py verify        # 9.1 clean-start identity
    python scripts/run_clean_mvp.py workflow      # 9.2 one documented workflow
    python scripts/run_clean_mvp.py repeat        # 9.3 repeatability comparison
    python scripts/run_clean_mvp.py rehearsals    # 9.4/9.5 handoff receipts
    python scripts/run_clean_mvp.py checkpoint    # 9.6/9.7 evidence and decision
    python scripts/run_clean_mvp.py tag-preflight # 9.8 tag record, never pushed
    python scripts/run_clean_mvp.py all           # every command above in order
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.checkpoint import (  # noqa: E402
    MVP_TAG_NAME,
    EvidenceLink,
    RehearsalStatus,
    RunbookStep,
    build_evidence_chain,
    build_rehearsal_receipt,
    build_tag_record,
    decide_checkpoint,
)
from mineocclude.experiments.clean_run import (  # noqa: E402
    WorkflowStep,
    build_clean_run_record,
    compare_repeat,
    environment_hash,
    run_workflow_step,
    sha256_file,
    verify_clean_start,
)
from mineocclude.experiments.mvp_config import load_mvp_config  # noqa: E402

DEFAULT_WORKFLOW = ROOT / "configs" / "experiments" / "clean_run.yaml"
DEFAULT_OUTPUT_ROOT = ROOT / "docs" / "status" / "person_a_phase9_clean_run_v0_1"


def write_json(path: Path, document: Any) -> str:
    # Write bytes, not text: text mode translates "\n" to "\r\n" on Windows, so
    # the file on disk would not hash to the digest this function returns.
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def load_workflow(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def code_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    )
    return result.stdout.strip() or "0" * 40


def build_external_artifact_index() -> dict[str, Any]:
    """The approved index every large artifact is resolved through (Step 9.1)."""

    return {
        "schema_version": "person-a-external-artifact-index-v0.1",
        "index_id": "person-a-mvp-external-artifacts-v0.1",
        "local_cache_root": None,
        "resolution_policy": (
            "Large artifacts resolve through this approved index only. An "
            "operator's private working directory is never an acceptable source."
        ),
        "artifacts": [
            {
                "artifact_id": "person-a-ten-pilot-combined-activation-index",
                "artifact_type": "activation",
                "uri": (
                    "file:///person-a-phase6-approved-outputs/"
                    "person-a-phase6-ten-pilot-expansion-seed-20260725/"
                    "combined_activation_index.json"
                ),
                "sha256": (
                    "1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9"
                ),
                "byte_size": 245491346,
                "owner": "person_a_model",
            },
            {
                "artifact_id": "person-a-ten-pilot-final-report",
                "artifact_type": "diagnostic_log",
                "uri": (
                    "file:///person-a-phase6-approved-outputs/"
                    "person-a-phase6-ten-pilot-expansion-seed-20260725/"
                    "final_report.json"
                ),
                "sha256": (
                    "64507e18aad3d922ff4cbdd2fd7ef336718a788e2cc7945288d2e0e05772eee0"
                ),
                "byte_size": 310652759,
                "owner": "person_a_model",
            },
            {
                "artifact_id": "person-c-c6a-output-bundle",
                "artifact_type": "raw_trajectory",
                "uri": "file:///person-c-c6a-outputs/person-c-c6a-post-c1-v0.1",
                "sha256": (
                    "c8453cb8a459d0d56d69f5bf39233997537e28a14b10a3a2ba4aeb3f421c624b"
                ),
                "byte_size": 609099426,
                "owner": "person_c_data",
            },
            {
                "artifact_id": "mineworld-700m-main-checkpoint",
                "artifact_type": "model_input",
                "uri": (
                    "https://www.modelscope.cn/models/MineWorld/"
                    "0dd5561ab317115831badc50e09a6ebe98693d0e"
                ),
                "sha256": (
                    "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
                ),
                "byte_size": None,
                "owner": "person_a_model",
            },
            {
                "artifact_id": "mineworld-vae-checkpoint",
                "artifact_type": "model_input",
                "uri": (
                    "https://www.modelscope.cn/models/MineWorld/"
                    "0dd5561ab317115831badc50e09a6ebe98693d0e/vae"
                ),
                "sha256": (
                    "370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab"
                ),
                "byte_size": None,
                "owner": "person_a_model",
            },
        ],
    }


def cmd_verify(args: argparse.Namespace) -> int:
    workflow = load_workflow(Path(args.workflow))
    config = load_mvp_config(ROOT / workflow["mvp_config"])
    index = build_external_artifact_index()
    write_json(Path(args.output_root) / "external_artifact_index.json", index)
    file_identities = {
        name: sha256_file(ROOT / name) or "" for name in workflow["verify_file_identities"]
    }
    report = verify_clean_start(
        repository_root=ROOT,
        declared={
            "code_sha": code_sha(),
            "config_hash": config.config_hash,
            "schema_version": config.get("schema_version"),
            "model_hash": config.model_hash,
            "preprocess_hash": config.preprocess_hash,
        },
        file_identities=file_identities,
        external_artifact_index=index,
        require_clean_worktree=bool(workflow.get("require_clean_worktree", True)),
    )
    digest = write_json(
        Path(args.output_root) / "step_9_1_clean_start.json", report
    )
    print(json.dumps({"step": "9.1", "status": report["status"], "sha256": digest}))
    return 0


def cmd_workflow(args: argparse.Namespace) -> int:
    workflow = load_workflow(Path(args.workflow))
    config = load_mvp_config(ROOT / workflow["mvp_config"])
    steps = [
        WorkflowStep(
            step_id=str(entry["step_id"]),
            description=str(entry["description"]),
            command=tuple(
                sys.executable if part == "python" else part
                for part in entry["command"]
            ),
            owner=str(entry.get("owner", "person_a_model")),
            required=bool(entry.get("required", True)),
        )
        for entry in workflow["steps"]
    ]
    captures = [run_workflow_step(step, cwd=ROOT) for step in steps]
    start_path = Path(args.output_root) / "step_9_1_clean_start.json"
    start_report = (
        json.loads(start_path.read_text(encoding="utf-8"))
        if start_path.is_file()
        else {"status": "NOT_RUN"}
    )
    record = build_clean_run_record(
        start_report=start_report,
        steps=steps,
        captures=captures,
        real_inputs_used=False,
        identity={**config.identity(), "code_sha": code_sha()},
        output_paths=[
            "docs/status/person_a_phase7_mvp_v0_1",
        ],
    )
    record["real_only_steps"] = workflow.get("real_only_steps", [])
    record["real_only_steps_skipped_reason"] = (
        "Real accepted inputs, the final B direction/dose request, and an "
        "authorized GPU runtime are unavailable in this environment."
    )
    digest = write_json(
        Path(args.output_root) / "step_9_2_clean_run_record.json", record
    )
    print(
        json.dumps(
            {
                "step": "9.2",
                "status": record["status"],
                "steps": record["executed_step_count"],
                "failed": record["failed_step_ids"],
                "sha256": digest,
            }
        )
    )
    return 0 if record["all_documented_steps_passed"] else 1


def cmd_repeat(args: argparse.Namespace) -> int:
    """Repeat one deterministic pooled computation and compare it in tolerance.

    This exercises and validates the comparison logic on the same machine, seed,
    and configuration. It is explicitly not a repeat of a real model forward;
    that requires the authorized GPU runtime and is recorded as such.
    """

    workflow = load_workflow(Path(args.workflow))
    config = load_mvp_config(ROOT / workflow["mvp_config"])
    first, second = _deterministic_pooled_repeat(config.extraction_seed)
    report = compare_repeat(
        first,
        second,
        rtol=float(workflow["repeatability"]["rtol"]),
        atol=float(workflow["repeatability"]["atol"]),
        nondeterministic_operations=(),
        precision=str(config.get("extraction.stored_dtype")),
    )
    report["input_kind"] = "deterministic_cpu_pooled_vector"
    report["real_model_forward_repeated"] = False
    report["real_repeat_blocked_reason"] = (
        "Repeating a real eval-mode teacher-forced forward requires the "
        "authorized GPU runtime with the pinned checkpoint."
    )
    report["identity"] = {**config.identity(), "code_sha": code_sha()}
    digest = write_json(
        Path(args.output_root) / "step_9_3_repeatability.json", report
    )
    print(
        json.dumps(
            {
                "step": "9.3",
                "gate": report["reproducibility_gate"],
                "max_abs": report["max_absolute_difference"],
                "sha256": digest,
            }
        )
    )
    return 0 if report["within_tolerance"] else 1


def _deterministic_pooled_repeat(seed: int) -> tuple[list[float], list[float]]:
    import numpy as np  # noqa: PLC0415 - pinned scientific dependency

    def compute() -> list[float]:
        rng = np.random.default_rng(seed)
        tokens = rng.standard_normal((336, 2048)).astype(np.float16)
        return tokens.astype(np.float64).mean(axis=0).tolist()

    return compute(), compute()


def cmd_rehearsals(args: argparse.Namespace) -> int:
    """Record the C, D, and E handoff rehearsals attempted from this checkout."""

    c_runbook = ROOT / "docs" / "runbooks" / "person_c_layout_reconstruction_checklist.md"
    e_runbook = ROOT / "docs" / "operations" / "person_e_phase1_runbook.md"

    collection = build_rehearsal_receipt(
        rehearsal_id="person-a-c-collection-rehearsal-v0.1",
        owning_role="person_c_data",
        runbook_path=c_runbook.relative_to(ROOT).as_posix(),
        runbook_sha256=sha256_file(c_runbook),
        steps=(
            RunbookStep(
                step_id="C.1",
                description="Read Person C's clean-machine collection runbook.",
                status=RehearsalStatus.COMPLETED,
                detail="The layout reconstruction checklist is published and readable.",
            ),
            RunbookStep(
                step_id="C.2",
                description="Start the Minecraft server and reset world state.",
                status=RehearsalStatus.BLOCKED,
                detail=(
                    "No Minecraft server, Java runtime, or approved credential "
                    "channel is available in this environment."
                ),
                instruction_gap=(
                    "Person C's runbook does not yet publish a single "
                    "clean-machine server start/reset/shutdown command sequence "
                    "that Person A or B can run without C present."
                ),
            ),
            RunbookStep(
                step_id="C.3",
                description="Capture, validate, and accept one new trajectory.",
                status=RehearsalStatus.BLOCKED,
                detail="Blocked by C.2.",
            ),
            RunbookStep(
                step_id="C.4",
                description="Upload, download, append, and shut down cleanly.",
                status=RehearsalStatus.BLOCKED,
                detail="Blocked by C.2.",
                instruction_gap=(
                    "The approved secret channel for capture credentials is named "
                    "but its access procedure is not documented for A/B."
                ),
            ),
        ),
        blocked_reason=(
            "A collection rehearsal requires a Minecraft runtime and the approved "
            "credential channel; neither is available here."
        ),
    )

    baselines = build_rehearsal_receipt(
        rehearsal_id="person-a-d-baseline-rehearsal-v0.1",
        owning_role="person_d_baselines",
        runbook_path="docs/baselines/person_d_phase1.md",
        runbook_sha256=sha256_file(ROOT / "docs" / "baselines" / "person_d_phase1.md"),
        steps=(
            RunbookStep(
                step_id="D.1",
                description="Read Person D's locked baseline workflow.",
                status=RehearsalStatus.COMPLETED,
            ),
            RunbookStep(
                step_id="D.2",
                description=(
                    "Invoke the baseline workflow from the clean accepted "
                    "manifest and folds."
                ),
                status=RehearsalStatus.BLOCKED,
                detail=(
                    "The complete MVP accepted manifest and activation index do "
                    "not exist yet, so there is no clean run to consume."
                ),
            ),
            RunbookStep(
                step_id="D.3",
                description="Compare baseline output identity against the clean run.",
                status=RehearsalStatus.BLOCKED,
                detail="Blocked by D.2.",
            ),
        ),
        blocked_reason=(
            "Person D's baseline workflow has no complete clean-run input to "
            "consume until the 66-cell extraction completes."
        ),
    )

    measurement = build_rehearsal_receipt(
        rehearsal_id="person-a-e-measurement-rehearsal-v0.1",
        owning_role="person_e_operations",
        runbook_path=e_runbook.relative_to(ROOT).as_posix(),
        runbook_sha256=sha256_file(e_runbook),
        steps=(
            RunbookStep(
                step_id="E.1",
                description="Read Person E's Phase 1 runbook and measurement contract.",
                status=RehearsalStatus.COMPLETED,
            ),
            RunbookStep(
                step_id="E.2",
                description=(
                    "Confirm Person E's immutable registry accepts a Person A "
                    "run/artifact ledger unchanged."
                ),
                status=RehearsalStatus.COMPLETED,
                detail=(
                    "mineocclude.experiments.mvp_lineage projects onto Person E's "
                    "immutable registry schema and the validator accepts it; see "
                    "tests/experiments/test_mvp_lineage.py."
                ),
            ),
            RunbookStep(
                step_id="E.3",
                description=(
                    "Invoke Person E's measurement entry point on clean-run clips."
                ),
                status=RehearsalStatus.BLOCKED,
                detail=(
                    "No U4 rollout clips exist: generation requires Person B's "
                    "final direction/dose request and an authorized model runtime."
                ),
            ),
        ),
        blocked_reason=(
            "Measurement has no rollout clips to consume until U4 generation is "
            "unblocked."
        ),
    )

    package = {
        "schema_version": "person-a-phase9-rehearsals-v0.1",
        "steps": ["9.4", "9.5"],
        "collection_rehearsal": collection,
        "baseline_rehearsal": baselines,
        "measurement_rehearsal": measurement,
        "all_rehearsals_completed": all(
            receipt["succeeded"]
            for receipt in (collection, baselines, measurement)
        ),
        "documented_instruction_gaps": (
            collection["documented_instruction_gaps"]
            + baselines["documented_instruction_gaps"]
            + measurement["documented_instruction_gaps"]
        ),
    }
    digest = write_json(
        Path(args.output_root) / "step_9_4_9_5_rehearsals.json", package
    )
    print(
        json.dumps(
            {
                "steps": "9.4/9.5",
                "completed": package["all_rehearsals_completed"],
                "gaps": len(package["documented_instruction_gaps"]),
                "sha256": digest,
            }
        )
    )
    return 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    workflow = load_workflow(Path(args.workflow))
    config = load_mvp_config(ROOT / workflow["mvp_config"])
    output_root = Path(args.output_root)
    phase7 = ROOT / "docs" / "status" / "person_a_phase7_mvp_v0_1"
    phase6 = ROOT / "docs" / "status" / "person_a_phase6_closeout_v0_1"

    links = (
        EvidenceLink(
            order=1,
            claim="Model, source, checkpoint, and VAE identity plus official generation.",
            evidence_path="docs/status/person_a_phase2_runtime_record.md",
            evidence_sha256=sha256_file(
                ROOT / "docs" / "status" / "person_a_phase2_runtime_record.md"
            ),
            real=True,
        ),
        EvidenceLink(
            order=2,
            claim="Teacher forcing, FrameTokenMap, and the verified all-layer hook site.",
            evidence_path=(
                "docs/status/phase6_runtime/"
                "person-a-phase6-ten-pilot-expansion-seed-20260725/"
                "pilots/layout_01_ep9405/step6_3.json"
            ),
            evidence_sha256=sha256_file(
                ROOT
                / "docs/status/phase6_runtime"
                / "person-a-phase6-ten-pilot-expansion-seed-20260725"
                / "pilots/layout_01_ep9405/step6_3.json"
            ),
            real=True,
        ),
        EvidenceLink(
            order=3,
            claim="Visual-only pooling and the activation index cardinality certification.",
            evidence_path=(
                "docs/status/person_a_phase6_closeout_v0_1/step_6_7_certification.json"
            ),
            evidence_sha256=sha256_file(phase6 / "step_6_7_certification.json"),
            real=True,
        ),
        EvidenceLink(
            order=4,
            claim="The frozen MVP identity and the encoded 66-cell matrix.",
            evidence_path=(
                "docs/status/person_a_phase7_mvp_v0_1/step_7_2_matrix_report.json"
            ),
            evidence_sha256=sha256_file(phase7 / "step_7_2_matrix_report.json"),
            real=True,
        ),
        EvidenceLink(
            order=5,
            claim="The integrated stage graph and its run/artifact lineage.",
            evidence_path=(
                "docs/status/person_a_phase7_mvp_v0_1/"
                "step_7_4_synthetic_lineage.json"
            ),
            evidence_sha256=sha256_file(phase7 / "step_7_4_synthetic_lineage.json"),
            real=False,
            detail="Synthetic wiring proof; scientific use forbidden.",
        ),
        EvidenceLink(
            order=6,
            claim="Exact U4 injection scope proved by a direct tensor difference mask.",
            evidence_path="tests/intervention/test_inject.py",
            evidence_sha256=sha256_file(
                ROOT / "tests" / "intervention" / "test_inject.py"
            ),
            real=True,
            detail="Direct tensor test, not a model run.",
        ),
        EvidenceLink(
            order=7,
            claim="The one documented clean-run workflow and its captured output.",
            evidence_path=(
                "docs/status/person_a_phase9_clean_run_v0_1/"
                "step_9_2_clean_run_record.json"
            ),
            evidence_sha256=sha256_file(output_root / "step_9_2_clean_run_record.json"),
            real=False,
            detail="Workflow validated without real accepted inputs.",
        ),
    )
    lineage_path = phase7 / "step_7_4_synthetic_lineage.json"
    lineage = (
        json.loads(lineage_path.read_text(encoding="utf-8"))
        if lineage_path.is_file()
        else {"runs": [], "artifacts": []}
    )
    first_artifact = (lineage.get("artifacts") or [{}])[0]
    first_run = (lineage.get("runs") or [{}])[0]
    chain = build_evidence_chain(
        links,
        traced_example={
            "artifact_id": first_artifact.get("artifact_id", "unavailable"),
            "artifact_sha256": first_artifact.get("sha256", "0" * 64),
            "run_id": first_run.get("run_id", "unavailable"),
            "code_sha": first_run.get("code_sha", code_sha()),
            "config_hash": first_run.get("config_snapshot_hash", config.config_hash),
            "model_hash": first_run.get("checkpoint_hash", config.model_hash),
            "data_identity_hash": first_run.get("data_identity_hash", "0" * 64),
            "preprocess_hash": first_run.get(
                "preprocess_hash", config.preprocess_hash
            ),
            "environment_hash": environment_hash(),
            "seed": config.extraction_seed,
            "synthetic": True,
        },
    )
    chain_digest = write_json(
        output_root / "step_9_6_evidence_chain.json", chain
    )

    closeout_path = phase7 / "step_7_8_implementation_closeout.json"
    closeout = (
        json.loads(closeout_path.read_text(encoding="utf-8"))
        if closeout_path.is_file()
        else {}
    )
    engineering_gates = {
        gate["gate_id"]: gate["state"] == "pass"
        for gate in closeout.get("gates", ())
        if gate["gate_id"] != "mvp_queue_completeness"
    }
    decision = decide_checkpoint(
        engineering_gates=engineering_gates,
        u1_green=None,
        u2_green=None,
        u3_directionally_correct=None,
        u4_is_smoke_test_only=True,
        scientific_test_failed_cleanly=False,
        scope_cuts=(
            {
                "cut_id": "SC-1",
                "cut": (
                    "Run the MVP on the accepted subset of C6A cells rather than "
                    "waiting for all 66 handoff bundles."
                ),
                "kind": "breadth",
                "preserves_validity": True,
                "owner": "person_a_model",
            },
            {
                "cut_id": "SC-2",
                "cut": (
                    "Treat U4 as plumbing-only for Week 1 rather than claiming a "
                    "causal pilot without a predeclared held-out partition."
                ),
                "kind": "claim_strength",
                "preserves_validity": True,
                "owner": "person_a_model",
            },
            {
                "cut_id": "SC-3",
                "cut": (
                    "Defer paper-scale expansion until the MVP extraction and "
                    "U1-U3 gates are known."
                ),
                "kind": "breadth",
                "preserves_validity": True,
                "owner": "person_a_model",
            },
        ),
        detail=(
            "Every Person A engineering gate that can be evaluated without the "
            "complete accepted MVP dataset passes. U1-U3 are not evaluated "
            "because the dataset is incomplete, so the decision is YELLOW on "
            "unevaluated science rather than on failed engineering."
        ),
    )
    decision["frozen_step_4_1_decision"] = "FAIL"
    decision["frozen_step_4_1_rerun"] = False
    decision_digest = write_json(
        output_root / "step_9_7_checkpoint_decision.json", decision
    )
    print(
        json.dumps(
            {
                "steps": "9.6/9.7",
                "decision": decision["decision"],
                "evidence_links": chain["link_count"],
                "chain_sha256": chain_digest,
                "decision_sha256": decision_digest,
            }
        )
    )
    return 0


def cmd_tag_preflight(args: argparse.Namespace) -> int:
    workflow = load_workflow(Path(args.workflow))
    config = load_mvp_config(ROOT / workflow["mvp_config"])
    index = build_external_artifact_index()
    queue_state = (
        ROOT / "docs" / "status" / "person_a_phase7_mvp_v0_1"
        / "extraction_queue_state.json"
    )
    run_ids: list[str] = []
    if queue_state.is_file():
        document = json.loads(queue_state.read_text(encoding="utf-8"))
        run_id = document.get("identity", {}).get("run_id")
        if run_id:
            run_ids.append(str(run_id))
    record = build_tag_record(
        tag_name=MVP_TAG_NAME,
        target_commit=code_sha(),
        branch="role/person-a-model",
        identity={**config.identity(), "code_sha": code_sha()},
        accepted_manifest_sha256=sha256_file(
            ROOT
            / "data/handoff_a/person_a_canonical_c6a_multilayout_sagemaker_input_v0_1"
            / "bundle_manifest.json"
        )
        or "",
        schema_version=str(config.get("schema_version")),
        external_artifacts=index["artifacts"],
        run_ids=run_ids,
        review_completed=False,
        tag_created=False,
        tag_pushed=False,
    )
    record["blocked_reason"] = (
        "Final tagging is a coordinated five-role operation performed after "
        "integration and review; it is never created or pushed from "
        "role/person-a-model."
    )
    digest = write_json(
        Path(args.output_root) / "step_9_8_tag_record.json", record
    )
    print(
        json.dumps(
            {
                "step": "9.8",
                "status": record["status"],
                "tag": record["tag_name"],
                "tag_pushed": record["tag_pushed"],
                "sha256": digest,
            }
        )
    )
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    exit_code = 0
    for command in (
        cmd_verify,
        cmd_workflow,
        cmd_repeat,
        cmd_rehearsals,
        cmd_checkpoint,
        cmd_tag_preflight,
    ):
        exit_code = max(exit_code, command(args))
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", default=str(DEFAULT_WORKFLOW))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "verify",
        "workflow",
        "repeat",
        "rehearsals",
        "checkpoint",
        "tag-preflight",
        "all",
    ):
        sub.add_parser(name)
    return parser


COMMANDS = {
    "verify": cmd_verify,
    "workflow": cmd_workflow,
    "repeat": cmd_repeat,
    "rehearsals": cmd_rehearsals,
    "checkpoint": cmd_checkpoint,
    "tag-preflight": cmd_tag_preflight,
    "all": cmd_all,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
