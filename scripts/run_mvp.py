"""Main orchestration entry point for validated MineOcclude MVP pipeline stages.

One command drives the whole locked workflow. Sub-commands are stage-scoped so a
run can resume through recorded status rather than manual file moving:

    python scripts/run_mvp.py freeze          # 7.1 signed identity record
    python scripts/run_mvp.py matrix          # 7.2 expected-vs-accepted report
    python scripts/run_mvp.py graph           # 7.3 stage graph description
    python scripts/run_mvp.py queue-plan      # 7.5 build/refresh the queue
    python scripts/run_mvp.py queue-status    # 7.5 status and finish forecast
    python scripts/run_mvp.py run --mode synthetic   # 7.3 CPU wiring proof
    python scripts/run_mvp.py run --mode real        # 7.3/7.6 real execution
    python scripts/run_mvp.py closeout        # 7.8 implementation memo

Synthetic mode requires no model weights and no real capture; every artifact it
produces is marked synthetic with scientific use forbidden. Real mode refuses to
start without the exact frozen model identity and real accepted inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.extraction_queue import (  # noqa: E402
    ExtractionQueue,
    QueueError,
    QueueErrorCode,
    build_queue_from_matrix,
    certify_queue_cardinality,
)
from mineocclude.experiments.mvp_closeout import (  # noqa: E402
    ArtifactIndexEntry,
    Gate,
    GateState,
    build_mvp_closeout,
)
from mineocclude.experiments.mvp_config import (  # noqa: E402
    build_freeze_record,
    load_mvp_config,
)
from mineocclude.experiments.mvp_lineage import (  # noqa: E402
    AnalysisEntryPoint,
    ArtifactRecord,
    MvpLineage,
    RunIdentity,
    RunRecord,
    build_u1_u3_invocation_record,
    make_artifact_id,
    make_run_id,
    utc_now,
)
from mineocclude.experiments.mvp_matrix import (  # noqa: E402
    acceptance_from_handoff_bundles,
    load_expected_matrix,
    reconcile_matrix,
)
from mineocclude.experiments.stage_graph import (  # noqa: E402
    ExecutionMode,
    StageContext,
    describe_graph,
    run_stage_graph,
)

DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "mvp.yaml"
DEFAULT_OUTPUT_ROOT = ROOT / "docs" / "status" / "person_a_phase7_mvp_v0_1"
DEFAULT_QUEUE_STATE = DEFAULT_OUTPUT_ROOT / "extraction_queue_state.json"
HANDOFF_BUNDLE = (
    ROOT
    / "data"
    / "handoff_a"
    / "person_a_canonical_c6a_multilayout_sagemaker_input_v0_1"
    / "bundle_manifest.json"
)
FOLD_MANIFEST = (
    ROOT
    / "data"
    / "handoff_a"
    / "person_b_ten_pilot_fold_manifest_v0_1"
    / "ten_pilot_frame_fold_manifest.json"
)

# Frames per accepted trajectory, taken from Person C's accepted handoff bundles.
# The queue never guesses a frame count; a cell without one is not queued.
ACCEPTED_FRAME_COUNTS_KEY = "expected_activation_row_count"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, document: Any) -> str:
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def code_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "0" * 40


def git_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return True


def environment_hash() -> str:
    signature = json.dumps(
        {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Shared loading
# ---------------------------------------------------------------------------


def load_accepted_bundles() -> list[dict[str, Any]]:
    """Read every per-trajectory accepted handoff bundle Person A has received."""

    if not HANDOFF_BUNDLE.is_file():
        return []
    document = json.loads(HANDOFF_BUNDLE.read_text(encoding="utf-8"))
    bundles: list[dict[str, Any]] = []
    certified = document.get("current_certified_trajectory")
    if isinstance(certified, dict) and certified.get("trajectory_id"):
        bundles.append(
            {
                "trajectory_id": certified["trajectory_id"],
                "bundle_manifest": HANDOFF_BUNDLE.relative_to(ROOT).as_posix(),
                "bundle_manifest_sha256": certified.get(
                    "output_bundle_manifest_sha256"
                ),
                "expected_activation_row_count": document.get(
                    "expected_total_activation_row_count", 0
                )
                - document.get("expected_new_activation_row_count", 0),
                "expected_activation_chunk_count": document.get(
                    "expected_total_activation_chunk_count", 0
                )
                - document.get("expected_new_activation_chunk_count", 0),
            }
        )
    for entry in document.get("new_trajectory_bundles", ()):
        bundles.append(dict(entry))
    return bundles


def build_matrix_report(config: Any) -> dict[str, Any]:
    matrix_path = ROOT / config.get("matrix.expected_matrix_source.path")
    cells, digest = load_expected_matrix(
        matrix_path,
        expected_sha256=config.get("matrix.expected_matrix_source.sha256"),
        expected_cell_count=config.expected_cell_count,
    )
    bundles = load_accepted_bundles()
    report = reconcile_matrix(cells, acceptance_from_handoff_bundles(bundles))
    report["expected_matrix_sha256"] = digest
    report["expected_matrix_path"] = matrix_path.relative_to(ROOT).as_posix()
    report["expected_matrix_producing_commit"] = config.get(
        "matrix.expected_matrix_source.producing_commit"
    )
    report["identity"] = config.identity()
    return report


def frame_counts_from_bundles(
    bundles: list[dict[str, Any]],
    *,
    layer_count: int,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for bundle in bundles:
        rows = bundle.get(ACCEPTED_FRAME_COUNTS_KEY)
        trajectory = bundle.get("trajectory_id")
        if not trajectory or not isinstance(rows, int) or rows <= 0:
            continue
        if rows % layer_count:
            continue
        counts[str(trajectory)] = rows // layer_count
    return counts


def build_queue(config: Any, matrix_report: dict[str, Any]) -> ExtractionQueue:
    layer_count = int(config.get("model.decoder_layer_count"))
    bundles = load_accepted_bundles()
    frame_counts = frame_counts_from_bundles(bundles, layer_count=layer_count)
    run_id = make_run_id(
        stage_id="model_extraction",
        config_hash=config.config_hash,
        code_sha=code_sha(),
        seed=config.extraction_seed,
    )
    return build_queue_from_matrix(
        matrix_report,
        run_id=run_id,
        config_hash=config.config_hash,
        code_sha=code_sha(),
        accepted_manifest_sha256=(
            sha256_file(HANDOFF_BUNDLE) if HANDOFF_BUNDLE.is_file() else "0" * 64
        ),
        layer_count=layer_count,
        frame_counts=frame_counts,
        max_transient_retries=int(config.get("queue.max_transient_retries")),
    )


def load_or_build_queue(
    config: Any,
    matrix_report: dict[str, Any],
    *,
    state_path: Path,
) -> ExtractionQueue:
    """Resume the persisted queue, or supersede it when the identity changed.

    A changed config, code, or accepted manifest produces a different run
    identity, so its recorded work is not resumable. The stale state is archived
    under its own run identity rather than deleted, and a new queue starts.
    """

    fresh = build_queue(config, matrix_report)
    path = Path(state_path)
    if not path.is_file():
        return fresh
    try:
        queue = ExtractionQueue.load(path, expected_identity=fresh.identity())
    except QueueError as error:
        if error.code is not QueueErrorCode.RUN_IDENTITY_CHANGED:
            raise
        _archive_superseded_queue(path, superseded_by=fresh.run_id)
        return fresh
    for item_id, item in fresh.items.items():
        if item_id not in queue.items:
            queue.add(item)
    return queue


def _archive_superseded_queue(state_path: Path, *, superseded_by: str) -> Path:
    """Preserve a superseded queue state next to its replacement."""

    document = json.loads(state_path.read_text(encoding="utf-8"))
    old_run_id = str(document.get("identity", {}).get("run_id", "unknown"))
    archive = state_path.with_name(
        f"{state_path.stem}.superseded.{old_run_id[-12:]}.json"
    )
    document["superseded_by_run_id"] = superseded_by
    document["superseded_reason"] = (
        "The run identity changed, so recorded work from this queue is not "
        "resumable under the new identity."
    )
    write_json(archive, document)
    state_path.unlink()
    return archive


# ---------------------------------------------------------------------------
# Synthetic stage handlers (no weights, no capture, CPU only)
# ---------------------------------------------------------------------------


def synthetic_handlers(
    config: Any,
    matrix_report: dict[str, Any],
    queue: ExtractionQueue,
) -> dict[str, Any]:
    """Wire every stage with a deterministic, clearly-synthetic implementation."""

    layer_count = int(config.get("model.decoder_layer_count"))

    def manifest_validation(_context: StageContext) -> dict[str, Any]:
        return {"expected_vs_accepted_matrix": matrix_report}

    def oracle(context: StageContext) -> dict[str, Any]:
        matrix = context.require("expected_vs_accepted_matrix")
        return {
            "oracle_targets": {
                "synthetic": True,
                "scientific_use": "forbidden",
                "owner": "person_b_analysis",
                "target_row_count": int(matrix["accepted_cell_count"]),
                "entry_point": "mineocclude.oracle",
            }
        }

    def model_extraction(context: StageContext) -> dict[str, Any]:
        matrix = context.require("expected_vs_accepted_matrix")
        rows = 0
        for item in queue.items.values():
            rows += item.expected.expected_row_count
        return {
            "activation_index": {
                "synthetic": True,
                "scientific_use": "forbidden",
                "expected_activation_row_count": rows,
                "layer_count": layer_count,
                "queued_item_count": len(queue.items),
                "accepted_cell_count": int(matrix["accepted_cell_count"]),
            },
            "queue_status": queue.status(),
        }

    def activation_audit(context: StageContext) -> dict[str, Any]:
        context.require("activation_index")
        return {
            "activation_audit_report": certify_queue_cardinality(
                queue,
                expected_cell_count=config.expected_cell_count,
                vector_width=int(config.get("extraction.vector_width")),
                stored_dtype=str(config.get("extraction.stored_dtype")),
            )
        }

    def probes(context: StageContext) -> dict[str, Any]:
        context.require("activation_audit_report")
        context.require("oracle_targets")
        return {
            "probe_results": {
                "synthetic": True,
                "scientific_use": "forbidden",
                "owner": "person_b_analysis",
                "computed_by_person_a": False,
            }
        }

    def baselines(context: StageContext) -> dict[str, Any]:
        context.require("activation_audit_report")
        context.require("oracle_targets")
        return {
            "baseline_results": {
                "synthetic": True,
                "scientific_use": "forbidden",
                "owner": "person_d_baselines",
                "computed_by_person_a": False,
            }
        }

    def u1_u3_metrics(context: StageContext) -> dict[str, Any]:
        context.require("probe_results")
        context.require("baseline_results")
        return {
            "u1_u3_metrics": {
                "synthetic": True,
                "scientific_use": "forbidden",
                "owner": "person_b_analysis",
                "interpreted_by_person_a": False,
            }
        }

    def u4_generation(context: StageContext) -> dict[str, Any]:
        context.require("u1_u3_metrics")
        return {
            "rollout_manifest": {
                "synthetic": True,
                "scientific_use": "forbidden",
                "expected_primary_clip_count": int(
                    config.get("u4_pilot.primary_clip_count")
                ),
                "expected_control_clip_count": int(
                    config.get("u4_pilot.random_direction_control_count")
                ),
            },
            "rollout_bundle": {
                "synthetic": True,
                "scientific_use": "forbidden",
                "generated_clip_count": 0,
                "detail": (
                    "Synthetic mode proves wiring only; it never generates "
                    "rollout video."
                ),
            },
        }

    def measurement(context: StageContext) -> dict[str, Any]:
        context.require("rollout_bundle")
        return {
            "measurement_tables": {
                "synthetic": True,
                "scientific_use": "forbidden",
                "owner": "person_e_operations",
                "computed_by_person_a": False,
            }
        }

    return {
        "manifest_validation": manifest_validation,
        "oracle": oracle,
        "model_extraction": model_extraction,
        "activation_audit": activation_audit,
        "probes": probes,
        "baselines": baselines,
        "u1_u3_metrics": u1_u3_metrics,
        "u4_generation": u4_generation,
        "measurement": measurement,
    }


def real_handlers(config: Any) -> dict[str, Any]:
    """Real mode is intentionally empty until real accepted inputs exist.

    A stage with no registered entry point is reported BLOCKED by the graph, so
    a real run can never silently fall back to synthetic behaviour.
    """

    del config
    return {}


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


def cmd_freeze(args: argparse.Namespace) -> int:
    config = load_mvp_config(args.config)
    record = build_freeze_record(
        config,
        code_sha=code_sha(),
        signed_by=(
            "person_a_model",
            "person_b_analysis",
            "person_c_data",
            "person_d_baselines",
            "person_e_operations",
        ),
    )
    digest = write_json(Path(args.output_root) / "step_7_1_identity_freeze.json", record)
    print(json.dumps({"step": "7.1", "config_hash": config.config_hash, "sha256": digest}))
    return 0


def cmd_matrix(args: argparse.Namespace) -> int:
    config = load_mvp_config(args.config)
    report = build_matrix_report(config)
    digest = write_json(Path(args.output_root) / "step_7_2_matrix_report.json", report)
    print(
        json.dumps(
            {
                "step": "7.2",
                "expected": report["expected_cell_count"],
                "accepted": report["accepted_cell_count"],
                "shortfall": report["shortfall_count"],
                "owners": report["shortfall_owners"],
                "sha256": digest,
            }
        )
    )
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    document = describe_graph()
    digest = write_json(Path(args.output_root) / "step_7_3_stage_graph.json", document)
    print(json.dumps({"step": "7.3", "stages": document["stage_count"], "sha256": digest}))
    return 0


def cmd_queue_plan(args: argparse.Namespace) -> int:
    config = load_mvp_config(args.config)
    matrix_report = build_matrix_report(config)
    queue = load_or_build_queue(
        config, matrix_report, state_path=Path(args.queue_state)
    )
    resume = queue.resume()
    queue.save(args.queue_state)
    status = queue.status()
    write_json(Path(args.output_root) / "step_7_5_queue_status.json", status)
    print(
        json.dumps(
            {
                "step": "7.5",
                "run_id": queue.run_id,
                "items": status["item_count"],
                "states": status["state_counts"],
                "resume": resume,
            }
        )
    )
    return 0


def cmd_queue_status(args: argparse.Namespace) -> int:
    config = load_mvp_config(args.config)
    matrix_report = build_matrix_report(config)
    queue = load_or_build_queue(
        config, matrix_report, state_path=Path(args.queue_state)
    )
    status = queue.status()
    digest = write_json(Path(args.output_root) / "step_7_5_queue_status.json", status)
    print(json.dumps({"step": "7.5", "states": status["state_counts"], "sha256": digest}))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_mvp_config(args.config)
    mode = ExecutionMode(args.mode)
    matrix_report = build_matrix_report(config)
    queue = load_or_build_queue(
        config, matrix_report, state_path=Path(args.queue_state)
    )
    identity = {
        **config.identity(),
        "code_sha": code_sha(),
        "mode": mode.value,
    }
    handlers = (
        synthetic_handlers(config, matrix_report, queue)
        if mode is ExecutionMode.SYNTHETIC
        else real_handlers(config)
    )
    run_id = make_run_id(
        stage_id=f"integrated_{mode.value}",
        config_hash=config.config_hash,
        code_sha=code_sha(),
        seed=config.extraction_seed,
    )
    report = run_stage_graph(
        handlers,
        mode=mode,
        run_id=run_id,
        identity=identity,
    )

    lineage = MvpLineage(
        registry_id=f"person-a-mvp-{mode.value}-{run_id[-12:]}",
        synthetic=mode is ExecutionMode.SYNTHETIC,
    )
    run_identity = RunIdentity(
        code_sha=code_sha(),
        git_dirty=git_dirty(),
        config_snapshot_hash=config.config_hash,
        checkpoint_hash=str(config.get("model.checkpoint_sha256")),
        data_identity_hash=(
            sha256_file(HANDOFF_BUNDLE) if HANDOFF_BUNDLE.is_file() else "0" * 64
        ),
        preprocess_hash=config.preprocess_hash,
        environment_hash=environment_hash(),
        seeds={"extraction": config.extraction_seed},
    )
    started = utc_now()
    lineage.register_run(
        RunRecord(
            run_id=run_id,
            stage_id=f"integrated_{mode.value}",
            owner="person_a_model",
            status="in_progress",
            command=tuple(["python", "scripts/run_mvp.py", "run", "--mode", mode.value]),
            identity=run_identity,
            started_at=started,
        )
    )
    if report["complete"]:
        lineage.complete_run(run_id)
    else:
        lineage.fail_run(
            run_id,
            failure_reason=(
                "one or more stages were blocked or failed; see the stage report"
            ),
        )
    for name, digest in report["boundary_hashes"].items():
        artifact_type = _artifact_type_for(name)
        if artifact_type is None:
            continue
        lineage.register_artifact(
            ArtifactRecord(
                artifact_id=make_artifact_id(
                    artifact_type=artifact_type, run_id=run_id, sha256=digest
                ),
                artifact_type=artifact_type,
                creator_run_id=run_id,
                sha256=digest,
                uri=f"mineocclude://{mode.value}/{run_id}/{name}",
                size_bytes=0,
                status_authority="person_a_model",
            )
        )
    registry_report = lineage.validate_against_person_e_schema()

    output_root = Path(args.output_root)
    stage_digest = write_json(
        output_root / f"step_7_3_{mode.value}_stage_report.json",
        {k: v for k, v in report.items() if k != "results"},
    )
    lineage_digest = write_json(
        output_root / f"step_7_4_{mode.value}_lineage.json",
        {
            **lineage.to_document(),
            "person_e_registry_validation": registry_report,
        },
    )
    queue.save(args.queue_state)
    print(
        json.dumps(
            {
                "step": "7.3/7.4",
                "mode": mode.value,
                "complete": report["complete"],
                "completed_stages": report["completed_stage_count"],
                "blocked_stages": report["blocked_stage_count"],
                "failed_stages": report["failed_stage_count"],
                "registry_accepted": registry_report["accepted"],
                "stage_report_sha256": stage_digest,
                "lineage_sha256": lineage_digest,
            }
        )
    )
    return 0 if report["complete"] or mode is ExecutionMode.REAL else 1


_ARTIFACT_TYPES = {
    "expected_vs_accepted_matrix": "metric_table",
    "oracle_targets": "oracle_target",
    "activation_index": "activation",
    "queue_status": "diagnostic_log",
    "activation_audit_report": "metric_table",
    "probe_results": "prediction",
    "baseline_results": "baseline",
    "u1_u3_metrics": "metric_table",
    "rollout_manifest": "rollout",
    "rollout_bundle": "rollout_clip",
    "measurement_tables": "measurement",
}


def _artifact_type_for(boundary_name: str) -> str | None:
    return _ARTIFACT_TYPES.get(boundary_name)


def cmd_u1_u3(args: argparse.Namespace) -> int:
    config = load_mvp_config(args.config)
    matrix_report = build_matrix_report(config)
    queue = load_or_build_queue(
        config, matrix_report, state_path=Path(args.queue_state)
    )
    cardinality = certify_queue_cardinality(
        queue,
        expected_cell_count=config.expected_cell_count,
        vector_width=int(config.get("extraction.vector_width")),
        stored_dtype=str(config.get("extraction.stored_dtype")),
    )
    executed = bool(cardinality["complete"]) and cardinality["completed_item_count"] > 0
    fold_sha = sha256_file(FOLD_MANIFEST) if FOLD_MANIFEST.is_file() else "0" * 64
    record = build_u1_u3_invocation_record(
        run_id=make_run_id(
            stage_id="u1_u3_metrics",
            config_hash=config.config_hash,
            code_sha=code_sha(),
            seed=config.extraction_seed,
        ),
        identity={**config.identity(), "code_sha": code_sha()},
        entry_points=(
            AnalysisEntryPoint(
                owner="person_b_analysis",
                entry_point="scripts/run_person_b_pilot.py",
                command=("python", "scripts/run_person_b_pilot.py"),
                frozen_config_path="configs/analysis/core.yaml",
                frozen_config_sha256=(
                    "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
                ),
            ),
            AnalysisEntryPoint(
                owner="person_d_baselines",
                entry_point="person_d_locked_baseline_workflow",
                command=("python", "-m", "mineocclude.baselines"),
                frozen_config_path="configs/analysis/core.yaml",
                frozen_config_sha256=(
                    "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
                ),
            ),
        ),
        accepted_manifest_sha256=(
            sha256_file(HANDOFF_BUNDLE) if HANDOFF_BUNDLE.is_file() else "0" * 64
        ),
        activation_index_sha256=None if not executed else "",
        fold_manifest_sha256=fold_sha,
        fold_count=5,
        accepted_row_count=(
            cardinality["completed_activation_row_count"] if executed else None
        ),
        exclusion_count=int(matrix_report["shortfall_count"]),
        log_uris=(),
        output_paths=(),
        executed=executed,
        blocked_reason=(
            None
            if executed
            else (
                "The MVP activation dataset is not complete: "
                f"{cardinality['completed_item_count']} of "
                f"{config.expected_cell_count} expected cells have completed "
                "extraction, so Person B's and Person D's entry points have no "
                "complete accepted input to consume."
            )
        ),
    )
    digest = write_json(
        Path(args.output_root) / "step_7_7_u1_u3_invocation.json", record
    )
    print(json.dumps({"step": "7.7", "status": record["status"], "sha256": digest}))
    return 0


def cmd_closeout(args: argparse.Namespace) -> int:
    config = load_mvp_config(args.config)
    matrix_report = build_matrix_report(config)
    queue = load_or_build_queue(
        config, matrix_report, state_path=Path(args.queue_state)
    )
    cardinality = certify_queue_cardinality(
        queue,
        expected_cell_count=config.expected_cell_count,
        vector_width=int(config.get("extraction.vector_width")),
        stored_dtype=str(config.get("extraction.stored_dtype")),
    )
    status = queue.status(
        forecast_basis={
            "seconds_per_frame": 1.127971146271222,
            "bytes_per_frame": 163853.6606189968,
        }
    )
    invocation_path = Path(args.output_root) / "step_7_7_u1_u3_invocation.json"
    invocation = (
        json.loads(invocation_path.read_text(encoding="utf-8"))
        if invocation_path.is_file()
        else None
    )
    gates = (
        Gate(
            gate_id="model_runtime",
            state=GateState.PASS,
            evidence="docs/status/person_a_phase2_runtime_record.md",
            detail="Pinned 700M MineWorld loaded, generated, and hooked on an L4.",
        ),
        Gate(
            gate_id="input_alignment",
            state=GateState.PASS,
            evidence=(
                "docs/status/person_a_phase6_closeout_v0_1/"
                "step_6_7_certification.json"
            ),
            detail="Ten-pilot source-identity joins passed exactly.",
        ),
        Gate(
            gate_id="hook_site",
            state=GateState.PASS,
            evidence="tests/activations/test_hooks.py",
            detail="All 20 decoder layers discovered and captured exactly once.",
        ),
        Gate(
            gate_id="pooling",
            state=GateState.PASS,
            evidence=(
                "docs/status/person_a_phase6_closeout_v0_1/"
                "step_6_7_certification.json"
            ),
            detail="Direct visual-token mean pooling audit passed on ten pilots.",
        ),
        Gate(
            gate_id="storage",
            state=GateState.PASS,
            evidence="docs/contracts/person_a_locked_extraction_contract_v1_0.md",
            detail="Pooled 16-bit store v2, 8,192.68 bytes per activation row.",
        ),
        Gate(
            gate_id="reproducibility",
            state=GateState.PASS,
            evidence=(
                "docs/status/phase6_runtime/"
                "person-a-phase6-ten-pilot-expansion-seed-20260725/"
                "completion_report.json"
            ),
            detail="Repeat forwards agreed to a maximum absolute difference of 0.0.",
        ),
        Gate(
            gate_id="visible_positive_control",
            state=GateState.PASS,
            evidence=(
                "docs/status/person_a_canonical_multilayout_a6_6_closure_v0_1/"
                "a6_6_closure.json"
            ),
            detail="Person B's canonical multi-layout positive control passed.",
        ),
        Gate(
            gate_id="mvp_queue_completeness",
            state=GateState.BLOCKED,
            evidence=(
                "docs/status/person_a_phase7_mvp_v0_1/step_7_2_matrix_report.json"
            ),
            detail=(
                f"{matrix_report['accepted_cell_count']} of "
                f"{matrix_report['expected_cell_count']} expected cells have a "
                "per-trajectory accepted handoff bundle."
            ),
        ),
    )
    artifacts = (
        ArtifactIndexEntry(
            artifact_id="person-a-ten-pilot-combined-activation-index",
            artifact_type="activation",
            uri=(
                "file:///home/sagemaker-user/person-a-phase6-approved-outputs/"
                "person-a-phase6-ten-pilot-expansion-seed-20260725/"
                "combined_activation_index.json"
            ),
            sha256=(
                "1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9"
            ),
            owner="person_a_model",
            real=True,
        ),
        ArtifactIndexEntry(
            artifact_id="person-a-canonical-multilayout-collection-manifest",
            artifact_type="raw_trajectory",
            uri=(
                "file:///docs/status/phase6_runtime/"
                "person-a-canonical-c6a-multilayout-successor-seed-20260725-"
                "retry-20260804T211350Z/collection_manifest.json"
            ),
            sha256=(
                "a672c834e8af3fd12c735e4042951b7b90d0aeeed5b0b62790aacdf3a58c0db0"
            ),
            owner="person_a_model",
            real=True,
        ),
    )
    document = build_mvp_closeout(
        identity={**config.identity(), "code_sha": code_sha()},
        matrix_report=matrix_report,
        queue_status=status,
        cardinality_report=cardinality,
        gates=gates,
        artifact_index=artifacts,
        capacity={
            "bytes_per_model_frame": config.get("storage.bytes_per_model_frame"),
            "bytes_per_activation_row": config.get(
                "storage.bytes_per_activation_row"
            ),
            "measured_seconds_per_model_frame": 1.127971146271222,
            "reference_gpu": "NVIDIA L4",
            "reference_gpu_memory_bytes": 23661248512,
            "peak_cuda_allocated_bytes_phase2": 6207769600,
            "peak_cuda_reserved_bytes_phase2": 9330229248,
            "projected_66_trajectory_wall_seconds": 13951.198325540983,
            "projected_66_trajectory_activation_bytes": 2026607616.0,
        },
        u1_u3_invocation=invocation,
        person_b_typical_norm_path_confirmed=False,
        person_e_rollout_schema_confirmed=True,
        real_extraction_executed=False,
        external_blockers=(
            {
                "blocker_id": "C-66-HANDOFF",
                "owner": "person_c_data",
                "description": (
                    "Per-trajectory accepted handoff bundles for "
                    f"{matrix_report['shortfall_count']} of "
                    f"{matrix_report['expected_cell_count']} C6A cells have not "
                    "been published to Person A."
                ),
            },
            {
                "blocker_id": "B-TYPICAL-NORM",
                "owner": "person_b_analysis",
                "description": (
                    "Person B's typical activation norm measurement path and "
                    "final direction/dose request are not yet published."
                ),
            },
            {
                "blocker_id": "A-GPU-RUNTIME",
                "owner": "person_a_model",
                "description": (
                    "The real 66-trajectory extraction requires an authorized "
                    "GPU runtime session; none is available in this environment."
                ),
            },
        ),
    )
    digest = write_json(
        Path(args.output_root) / "step_7_8_implementation_closeout.json", document
    )
    print(
        json.dumps(
            {
                "step": "7.8",
                "status": document["status"],
                "u4_readiness": document["u4_readiness"],
                "sha256": digest,
            }
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--queue-state", default=str(DEFAULT_QUEUE_STATE))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("freeze", help="write the Step 7.1 signed identity record")
    sub.add_parser("matrix", help="write the Step 7.2 expected-vs-accepted report")
    sub.add_parser("graph", help="write the Step 7.3 stage graph description")
    sub.add_parser("queue-plan", help="build or resume the Step 7.5 queue")
    sub.add_parser("queue-status", help="write the Step 7.5 queue status")
    run = sub.add_parser("run", help="execute the integrated stage graph")
    run.add_argument("--mode", choices=("synthetic", "real"), required=True)
    sub.add_parser("u1-u3", help="write the Step 7.7 invocation record")
    sub.add_parser("closeout", help="write the Step 7.8 implementation closeout")
    return parser


COMMANDS = {
    "freeze": cmd_freeze,
    "matrix": cmd_matrix,
    "graph": cmd_graph,
    "queue-plan": cmd_queue_plan,
    "queue-status": cmd_queue_status,
    "run": cmd_run,
    "u1-u3": cmd_u1_u3,
    "closeout": cmd_closeout,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
