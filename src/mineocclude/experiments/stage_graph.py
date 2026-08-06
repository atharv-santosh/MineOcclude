"""The integrated MVP stage graph (Steps 7.3, 7.4, and 7.7).

Person A executes teammates' entry points; it never absorbs their scientific
logic. Each stage declares the inputs it requires and the outputs it produces,
every boundary is hash-validated, and a failed upstream gate stops every
downstream stage instead of silently producing partial results.

Two execution modes exist:

* ``synthetic`` runs on CPU with no model weights and no real capture, purely to
  prove wiring. Its outputs are marked synthetic and are never scientific.
* ``real`` requires the exact frozen model identity and real accepted inputs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

STAGE_GRAPH_SCHEMA_VERSION = "person-a-mvp-stage-graph-v0.1"


class ExecutionMode(str, Enum):
    """The two supported integrated execution modes."""

    SYNTHETIC = "synthetic"
    REAL = "real"


class StageStatus(str, Enum):
    """Terminal states one stage may reach."""

    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED_UPSTREAM_GATE = "skipped_upstream_gate"


class StageErrorCode(str, Enum):
    """Stable reasons the stage graph refuses to run or continue."""

    UNKNOWN_STAGE = "unknown_stage"
    DUPLICATE_STAGE = "duplicate_stage"
    CYCLIC_GRAPH = "cyclic_graph"
    MISSING_INPUT = "missing_input"
    INPUT_HASH_MISMATCH = "input_hash_mismatch"
    OUTPUT_HASH_MISMATCH = "output_hash_mismatch"
    UNDECLARED_OUTPUT = "undeclared_output"
    MODE_NOT_SUPPORTED = "mode_not_supported"
    OWNER_VIOLATION = "owner_violation"
    REAL_MODE_IDENTITY_MISSING = "real_mode_identity_missing"


class StageError(ValueError):
    """Raised when a stage boundary cannot be trusted."""

    def __init__(self, code: StageErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: StageErrorCode, message: str) -> None:
    raise StageError(code, message)


def hash_value(value: Any) -> str:
    """Content-hash any JSON-serializable boundary payload."""

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


@dataclass(frozen=True)
class StageSpec:
    """One declared stage: its owner, dependencies, and declared boundaries."""

    stage_id: str
    owner: str
    description: str
    requires: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    supported_modes: tuple[ExecutionMode, ...] = (
        ExecutionMode.SYNTHETIC,
        ExecutionMode.REAL,
    )
    requires_model_identity: bool = False

    def to_document(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "owner": self.owner,
            "description": self.description,
            "requires": list(self.requires),
            "consumes": list(self.consumes),
            "produces": list(self.produces),
            "supported_modes": [mode.value for mode in self.supported_modes],
            "requires_model_identity": self.requires_model_identity,
        }


# The frozen MVP stage graph. Owners outside person_a_model are invoked through
# their published entry points; their logic is never reimplemented here.
MVP_STAGES: tuple[StageSpec, ...] = (
    StageSpec(
        stage_id="manifest_validation",
        owner="person_a_model",
        description="Validate the accepted manifest against the expected 66-cell matrix.",
        produces=("expected_vs_accepted_matrix",),
    ),
    StageSpec(
        stage_id="oracle",
        owner="person_b_analysis",
        description="Invoke Person B's frozen oracle/target entry point.",
        requires=("manifest_validation",),
        consumes=("expected_vs_accepted_matrix",),
        produces=("oracle_targets",),
    ),
    StageSpec(
        stage_id="model_extraction",
        owner="person_a_model",
        description="Run the resumable teacher-forced activation extraction queue.",
        requires=("manifest_validation",),
        consumes=("expected_vs_accepted_matrix",),
        produces=("activation_index", "queue_status"),
        requires_model_identity=True,
    ),
    StageSpec(
        stage_id="activation_audit",
        owner="person_a_model",
        description="Certify activation cardinality, shape, joins, and duplicates.",
        requires=("model_extraction",),
        consumes=("activation_index", "queue_status"),
        produces=("activation_audit_report",),
    ),
    StageSpec(
        stage_id="probes",
        owner="person_b_analysis",
        description="Invoke Person B's probe fitting on accepted rows and folds.",
        requires=("activation_audit", "oracle"),
        consumes=("activation_audit_report", "oracle_targets"),
        produces=("probe_results",),
    ),
    StageSpec(
        stage_id="baselines",
        owner="person_d_baselines",
        description="Invoke Person D's locked baseline workflow.",
        requires=("activation_audit", "oracle"),
        consumes=("activation_audit_report", "oracle_targets"),
        produces=("baseline_results",),
    ),
    StageSpec(
        stage_id="u1_u3_metrics",
        owner="person_b_analysis",
        description="Invoke Person B's U1-U3 metric entry point.",
        requires=("probes", "baselines"),
        consumes=("probe_results", "baseline_results"),
        produces=("u1_u3_metrics",),
    ),
    StageSpec(
        stage_id="u4_generation",
        owner="person_a_model",
        description="Generate the immutable U4 pilot and control rollouts.",
        requires=("u1_u3_metrics",),
        consumes=("u1_u3_metrics",),
        produces=("rollout_manifest", "rollout_bundle"),
        requires_model_identity=True,
    ),
    StageSpec(
        stage_id="measurement",
        owner="person_e_operations",
        description="Invoke Person E's measurement/registry entry point.",
        requires=("u4_generation",),
        consumes=("rollout_manifest", "rollout_bundle"),
        produces=("measurement_tables",),
    ),
)


@dataclass(frozen=True)
class StageResult:
    """The recorded outcome of one stage execution."""

    stage_id: str
    owner: str
    status: StageStatus
    outputs: Mapping[str, Any] = field(default_factory=dict)
    output_hashes: Mapping[str, str] = field(default_factory=dict)
    detail: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    synthetic: bool = False

    def to_document(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "owner": self.owner,
            "status": self.status.value,
            "produced": sorted(self.output_hashes),
            "output_hashes": dict(self.output_hashes),
            "detail": self.detail,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "synthetic": self.synthetic,
        }


StageCallable = Callable[["StageContext"], Mapping[str, Any]]


@dataclass
class StageContext:
    """What one stage may read: prior boundary values plus the run identity."""

    mode: ExecutionMode
    run_id: str
    identity: Mapping[str, Any]
    boundary: dict[str, Any]
    boundary_hashes: dict[str, str]

    def require(self, name: str) -> Any:
        if name not in self.boundary:
            _fail(
                StageErrorCode.MISSING_INPUT,
                f"boundary value {name!r} has not been produced",
            )
        return self.boundary[name]


def _topological_order(stages: Sequence[StageSpec]) -> tuple[StageSpec, ...]:
    by_id: dict[str, StageSpec] = {}
    for stage in stages:
        if stage.stage_id in by_id:
            _fail(
                StageErrorCode.DUPLICATE_STAGE,
                f"stage {stage.stage_id!r} is declared more than once",
            )
        by_id[stage.stage_id] = stage
    for stage in stages:
        for dependency in stage.requires:
            if dependency not in by_id:
                _fail(
                    StageErrorCode.UNKNOWN_STAGE,
                    f"stage {stage.stage_id!r} requires unknown stage "
                    f"{dependency!r}",
                )
    ordered: list[StageSpec] = []
    permanent: set[str] = set()
    temporary: set[str] = set()

    def visit(stage_id: str) -> None:
        if stage_id in permanent:
            return
        if stage_id in temporary:
            _fail(
                StageErrorCode.CYCLIC_GRAPH,
                f"stage dependency cycle detected at {stage_id!r}",
            )
        temporary.add(stage_id)
        for dependency in by_id[stage_id].requires:
            visit(dependency)
        temporary.discard(stage_id)
        permanent.add(stage_id)
        ordered.append(by_id[stage_id])

    for stage in stages:
        visit(stage.stage_id)
    return tuple(ordered)


def describe_graph(
    stages: Sequence[StageSpec] = MVP_STAGES,
) -> dict[str, Any]:
    """Publish the stage graph, its ownership, and its boundary declarations."""

    ordered = _topological_order(stages)
    produced_by: dict[str, str] = {}
    for stage in ordered:
        for name in stage.produces:
            if name in produced_by:
                _fail(
                    StageErrorCode.DUPLICATE_STAGE,
                    f"boundary value {name!r} is produced by two stages",
                )
            produced_by[name] = stage.stage_id
    for stage in ordered:
        for name in stage.consumes:
            if name not in produced_by:
                _fail(
                    StageErrorCode.MISSING_INPUT,
                    f"stage {stage.stage_id!r} consumes unproduced {name!r}",
                )
    owners = sorted({stage.owner for stage in ordered})
    return {
        "schema_version": STAGE_GRAPH_SCHEMA_VERSION,
        "step": "7.3",
        "stage_count": len(ordered),
        "execution_order": [stage.stage_id for stage in ordered],
        "owners": owners,
        "person_a_owned_stages": [
            stage.stage_id for stage in ordered if stage.owner == "person_a_model"
        ],
        "delegated_stages": [
            stage.stage_id for stage in ordered if stage.owner != "person_a_model"
        ],
        "boundary_producers": dict(sorted(produced_by.items())),
        "stages": [stage.to_document() for stage in ordered],
        "scientific_logic_owned_by_declared_role": True,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_stage_graph(
    handlers: Mapping[str, StageCallable],
    *,
    mode: ExecutionMode,
    run_id: str,
    identity: Mapping[str, Any],
    stages: Sequence[StageSpec] = MVP_STAGES,
    declared_input_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Execute the graph, validating every boundary and stopping on a failed gate."""

    ordered = _topological_order(stages)
    if mode is ExecutionMode.REAL:
        missing = [
            key
            for key in ("model_hash", "config_hash", "code_sha", "seed")
            if not identity.get(key)
        ]
        if missing:
            _fail(
                StageErrorCode.REAL_MODE_IDENTITY_MISSING,
                "real mode requires exact identity fields: " + ", ".join(missing),
            )

    context = StageContext(
        mode=mode,
        run_id=run_id,
        identity=dict(identity),
        boundary={},
        boundary_hashes={},
    )
    results: list[StageResult] = []
    failed_stages: set[str] = set()

    for stage in ordered:
        if mode not in stage.supported_modes:
            results.append(
                StageResult(
                    stage_id=stage.stage_id,
                    owner=stage.owner,
                    status=StageStatus.BLOCKED,
                    detail=f"stage does not support {mode.value} mode",
                )
            )
            failed_stages.add(stage.stage_id)
            continue
        blocked_by = sorted(set(stage.requires) & failed_stages)
        if blocked_by:
            results.append(
                StageResult(
                    stage_id=stage.stage_id,
                    owner=stage.owner,
                    status=StageStatus.SKIPPED_UPSTREAM_GATE,
                    detail="blocked by upstream stages: " + ", ".join(blocked_by),
                )
            )
            failed_stages.add(stage.stage_id)
            continue

        handler = handlers.get(stage.stage_id)
        if handler is None:
            results.append(
                StageResult(
                    stage_id=stage.stage_id,
                    owner=stage.owner,
                    status=StageStatus.BLOCKED,
                    detail="no entry point is registered for this stage",
                )
            )
            failed_stages.add(stage.stage_id)
            continue

        missing_inputs = [
            name for name in stage.consumes if name not in context.boundary
        ]
        if missing_inputs:
            results.append(
                StageResult(
                    stage_id=stage.stage_id,
                    owner=stage.owner,
                    status=StageStatus.BLOCKED,
                    detail="missing declared inputs: " + ", ".join(missing_inputs),
                )
            )
            failed_stages.add(stage.stage_id)
            continue

        if declared_input_hashes:
            mismatched = [
                name
                for name in stage.consumes
                if name in declared_input_hashes
                and declared_input_hashes[name] != context.boundary_hashes.get(name)
            ]
            if mismatched:
                _fail(
                    StageErrorCode.INPUT_HASH_MISMATCH,
                    f"stage {stage.stage_id!r} input hashes differ from declared: "
                    + ", ".join(mismatched),
                )

        started = _now()
        try:
            outputs = handler(context)
        except Exception as error:  # noqa: BLE001 - recorded, never swallowed
            results.append(
                StageResult(
                    stage_id=stage.stage_id,
                    owner=stage.owner,
                    status=StageStatus.FAILED,
                    detail=f"{type(error).__name__}: {error}",
                    started_at=started,
                    ended_at=_now(),
                )
            )
            failed_stages.add(stage.stage_id)
            continue

        if not isinstance(outputs, Mapping):
            _fail(
                StageErrorCode.UNDECLARED_OUTPUT,
                f"stage {stage.stage_id!r} must return a mapping of outputs",
            )
        undeclared = sorted(set(outputs) - set(stage.produces))
        if undeclared:
            _fail(
                StageErrorCode.UNDECLARED_OUTPUT,
                f"stage {stage.stage_id!r} produced undeclared outputs: "
                + ", ".join(undeclared),
            )
        missing_outputs = sorted(set(stage.produces) - set(outputs))
        if missing_outputs:
            results.append(
                StageResult(
                    stage_id=stage.stage_id,
                    owner=stage.owner,
                    status=StageStatus.FAILED,
                    detail="stage did not produce declared outputs: "
                    + ", ".join(missing_outputs),
                    started_at=started,
                    ended_at=_now(),
                )
            )
            failed_stages.add(stage.stage_id)
            continue

        hashes = {name: hash_value(value) for name, value in outputs.items()}
        context.boundary.update(outputs)
        context.boundary_hashes.update(hashes)
        results.append(
            StageResult(
                stage_id=stage.stage_id,
                owner=stage.owner,
                status=StageStatus.COMPLETED,
                outputs=dict(outputs),
                output_hashes=hashes,
                started_at=started,
                ended_at=_now(),
                synthetic=mode is ExecutionMode.SYNTHETIC,
            )
        )

    completed = [r for r in results if r.status is StageStatus.COMPLETED]
    return {
        "schema_version": STAGE_GRAPH_SCHEMA_VERSION,
        "step": "7.3",
        "run_id": run_id,
        "mode": mode.value,
        "identity": dict(identity),
        "synthetic": mode is ExecutionMode.SYNTHETIC,
        "scientific_use": (
            "forbidden" if mode is ExecutionMode.SYNTHETIC else "permitted"
        ),
        "stage_count": len(results),
        "completed_stage_count": len(completed),
        "failed_stage_count": sum(
            1 for r in results if r.status is StageStatus.FAILED
        ),
        "blocked_stage_count": sum(
            1
            for r in results
            if r.status
            in {StageStatus.BLOCKED, StageStatus.SKIPPED_UPSTREAM_GATE}
        ),
        "complete": len(completed) == len(results),
        "boundary_hashes": dict(sorted(context.boundary_hashes.items())),
        "stages": [result.to_document() for result in results],
        "results": {
            result.stage_id: result.outputs
            for result in results
            if result.status is StageStatus.COMPLETED
        },
    }


__all__ = [
    "MVP_STAGES",
    "STAGE_GRAPH_SCHEMA_VERSION",
    "ExecutionMode",
    "StageContext",
    "StageError",
    "StageErrorCode",
    "StageResult",
    "StageSpec",
    "StageStatus",
    "describe_graph",
    "hash_value",
    "run_stage_graph",
]
