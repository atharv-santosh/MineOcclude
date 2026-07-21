"""Build synthetic fixtures for the Step 1.6 rollout/registry contract."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


OUTPUT_DIR = Path(__file__).parent
SCHEMA_VERSION = "1.0"

CODE_SHA = "0" * 40
CONFIG_HASH = "1" * 64
MODEL_HASH = "2" * 64
PREPROCESS_HASH = "3" * 64
CONTEXT_HASH = "a" * 64
REQUEST_HASH = "b" * 64
OLD_CLIP_HASH = "c" * 64
CONTINUATION_HASH = "d" * 64
NON_PERSISTENCE_HASH = "e" * 64
PARTIAL_HASH = "f" * 64
DIAGNOSTIC_HASH = "9" * 64

HANDOFF_ID = "synthetic_step_1_6_handoff_001"
INPUT_RUN_ID = "synthetic_input_registration_run_001"
OLD_RUN_ID = "synthetic_rollout_run_000"
ROLLOUT_RUN_ID = "synthetic_rollout_run_001"
FAILED_RUN_ID = "synthetic_rollout_run_002"

CONTEXT_ARTIFACT_ID = "synthetic_input_context_artifact_001"
REQUEST_ARTIFACT_ID = "synthetic_intervention_request_artifact_001"
OLD_CLIP_ARTIFACT_ID = "synthetic_rollout_clip_artifact_000"
CONTINUATION_ARTIFACT_ID = "synthetic_rollout_clip_artifact_001"
NON_PERSISTENCE_ARTIFACT_ID = "synthetic_rollout_clip_artifact_002"
PARTIAL_ARTIFACT_ID = "synthetic_partial_rollout_artifact_003"
DIAGNOSTIC_ARTIFACT_ID = "synthetic_diagnostic_artifact_003"

FIXTURE_MARKER = {
    "synthetic": True,
    "scientific_use": "forbidden",
}


def artifact(
    artifact_id: str,
    artifact_type: str,
    uri: str,
    sha256: str,
    producer_run_id: str,
    *,
    status: str = "accepted",
    exclusion_reason: str | None = None,
    superseded_by: str | None = None,
) -> dict[str, Any]:
    """Create one synthetic registry artifact."""

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "uri": uri,
        "sha256": sha256,
        "producer_run_id": producer_run_id,
        "status": status,
        "exclusion_reason": exclusion_reason,
        "superseded_by": superseded_by,
    }


def run_record(
    run_id: str,
    command: list[str],
    parent_run_id: str | None,
    input_artifact_ids: list[str],
    output_artifact_ids: list[str],
    *,
    execution_status: str = "completed",
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Create one synthetic immutable run record."""

    return {
        "run_id": run_id,
        "command": command,
        "owner": "person_a",
        "parent_run_id": parent_run_id,
        "input_artifact_ids": input_artifact_ids,
        "output_artifact_ids": output_artifact_ids,
        "code_sha": CODE_SHA,
        "config_hash": CONFIG_HASH,
        "model_hash": MODEL_HASH,
        "preprocess_hash": PREPROCESS_HASH,
        "execution_status": execution_status,
        "failure_reason": failure_reason,
    }


def rollout_row(
    *,
    rollout_id: str,
    event_number: int,
    seed: int,
    dose_id: str,
    alpha_requested: float,
    alpha_applied: float,
    cap_reduced: bool,
    intended_block_shift: float,
    control_type: str,
    run_id: str,
    outcome: str,
    outcome_detail: str | None,
    measurable: bool,
    output_artifact_id: str | None,
    output_uri: str | None,
    output_hash: str | None,
    status: str,
    exclusion_reason: str | None,
) -> dict[str, Any]:
    """Create one synthetic rollout row with explicit scientific identity."""

    suffix = f"{event_number:03d}"
    return {
        "schema_version": SCHEMA_VERSION,
        "rollout_id": rollout_id,
        "event_id": f"synthetic_heldout_event_{suffix}",
        "episode_id": f"synthetic_episode_{suffix}",
        "trajectory_id": f"synthetic_heldout_trajectory_{suffix}",
        "server_tick": 200 + event_number,
        "render_frame_idx": 40 + event_number,
        "action_idx": 40 + event_number,
        "layout_id": "synthetic_layout_heldout_01",
        "model_frame_idx": 8,
        "regime": "synthetic_occlusion",
        "visibility": "synthetic_visible_at_intervention",
        "tau": 2.0,
        "v": 1.0,
        "q": 0.5,
        "duration": 1.0,
        "seed": seed,
        "dose_id": dose_id,
        "alpha_requested": alpha_requested,
        "alpha_applied": alpha_applied,
        "cap_reduced": cap_reduced,
        "intended_block_shift": intended_block_shift,
        "direction_version": "synthetic_direction_v1",
        "layer_idx": 12,
        "hook_site": "residual_stream",
        "timestep_idx": 8,
        "control_type": control_type,
        "input_context_id": f"synthetic_context_window_{suffix}",
        "input_context_artifact_id": CONTEXT_ARTIFACT_ID,
        "input_context_hash": CONTEXT_HASH,
        "intervention_request_artifact_id": REQUEST_ARTIFACT_ID,
        "output_artifact_id": output_artifact_id,
        "output_uri": output_uri,
        "output_hash": output_hash,
        "code_sha": CODE_SHA,
        "model_hash": MODEL_HASH,
        "config_hash": CONFIG_HASH,
        "preprocess_hash": PREPROCESS_HASH,
        "run_id": run_id,
        "outcome": outcome,
        "outcome_detail": outcome_detail,
        "measurable": measurable,
        "status": status,
        "exclusion_reason": exclusion_reason,
        "superseded_by": None,
    }


def make_accepted_rollout_manifest() -> dict[str, Any]:
    """Create measurable, non-persistent, and failed rollout examples."""

    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": "synthetic_rollout_manifest_001",
        "handoff_id": HANDOFF_ID,
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "rollout_rows": [
            rollout_row(
                rollout_id="synthetic_rollout_001",
                event_number=1,
                seed=101,
                dose_id="control",
                alpha_requested=0.0,
                alpha_applied=0.0,
                cap_reduced=False,
                intended_block_shift=0.0,
                control_type="alpha_zero",
                run_id=ROLLOUT_RUN_ID,
                outcome="measurable_continuation",
                outcome_detail=None,
                measurable=True,
                output_artifact_id=CONTINUATION_ARTIFACT_ID,
                output_uri="synthetic://step-1-6/rollouts/continuation-001.mp4",
                output_hash=CONTINUATION_HASH,
                status="accepted",
                exclusion_reason=None,
            ),
            rollout_row(
                rollout_id="synthetic_rollout_002",
                event_number=2,
                seed=102,
                dose_id="positive_low",
                alpha_requested=0.5,
                alpha_applied=0.5,
                cap_reduced=False,
                intended_block_shift=1.0,
                control_type="intervention",
                run_id=ROLLOUT_RUN_ID,
                outcome="non_persistence",
                outcome_detail=(
                    "Synthetic target ceased to persist before the measurement "
                    "endpoint; no displacement value is defined."
                ),
                measurable=False,
                output_artifact_id=NON_PERSISTENCE_ARTIFACT_ID,
                output_uri="synthetic://step-1-6/rollouts/non-persistence-002.mp4",
                output_hash=NON_PERSISTENCE_HASH,
                status="accepted",
                exclusion_reason=None,
            ),
            rollout_row(
                rollout_id="synthetic_rollout_003",
                event_number=3,
                seed=103,
                dose_id="positive_capped",
                alpha_requested=6.0,
                alpha_applied=5.0,
                cap_reduced=True,
                intended_block_shift=2.0,
                control_type="intervention",
                run_id=FAILED_RUN_ID,
                outcome="generation_failure",
                outcome_detail="Synthetic decoder failure before clip persistence.",
                measurable=False,
                output_artifact_id=None,
                output_uri=None,
                output_hash=None,
                status="excluded",
                exclusion_reason="generation_failed_before_complete_clip",
            ),
        ],
    }


def make_accepted_registry() -> dict[str, Any]:
    """Create an auditable synthetic run and artifact registry."""

    context_uri = "synthetic://step-1-6/contexts/context-001.json"
    request_uri = "synthetic://step-1-6/requests/request-001.json"
    old_uri = "synthetic://step-1-6/rollouts/old-continuation-000.mp4"
    continuation_uri = "synthetic://step-1-6/rollouts/continuation-001.mp4"
    non_persistence_uri = (
        "synthetic://step-1-6/rollouts/non-persistence-002.mp4"
    )
    partial_uri = "synthetic://step-1-6/rollouts/partial-003.mp4"
    diagnostic_uri = "synthetic://step-1-6/diagnostics/failure-003.json"

    return {
        "schema_version": SCHEMA_VERSION,
        "registry_id": "synthetic_run_artifact_registry_001",
        "handoff_id": HANDOFF_ID,
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "runs": [
            run_record(
                INPUT_RUN_ID,
                ["mineocclude", "register-inputs", "--synthetic"],
                None,
                [],
                [CONTEXT_ARTIFACT_ID, REQUEST_ARTIFACT_ID],
            ),
            run_record(
                OLD_RUN_ID,
                ["mineocclude", "rollout", "--synthetic", "--revision", "0"],
                INPUT_RUN_ID,
                [CONTEXT_ARTIFACT_ID, REQUEST_ARTIFACT_ID],
                [OLD_CLIP_ARTIFACT_ID],
            ),
            run_record(
                ROLLOUT_RUN_ID,
                ["mineocclude", "rollout", "--synthetic", "--revision", "1"],
                OLD_RUN_ID,
                [CONTEXT_ARTIFACT_ID, REQUEST_ARTIFACT_ID],
                [CONTINUATION_ARTIFACT_ID, NON_PERSISTENCE_ARTIFACT_ID],
            ),
            run_record(
                FAILED_RUN_ID,
                ["mineocclude", "rollout", "--synthetic", "--event", "003"],
                ROLLOUT_RUN_ID,
                [CONTEXT_ARTIFACT_ID, REQUEST_ARTIFACT_ID],
                [PARTIAL_ARTIFACT_ID, DIAGNOSTIC_ARTIFACT_ID],
                execution_status="failed",
                failure_reason="synthetic_decoder_failure",
            ),
        ],
        "artifacts": [
            artifact(
                CONTEXT_ARTIFACT_ID,
                "input_context",
                context_uri,
                CONTEXT_HASH,
                INPUT_RUN_ID,
            ),
            artifact(
                REQUEST_ARTIFACT_ID,
                "intervention_request",
                request_uri,
                REQUEST_HASH,
                INPUT_RUN_ID,
            ),
            artifact(
                OLD_CLIP_ARTIFACT_ID,
                "rollout_clip",
                old_uri,
                OLD_CLIP_HASH,
                OLD_RUN_ID,
                status="superseded",
                superseded_by=CONTINUATION_ARTIFACT_ID,
            ),
            artifact(
                CONTINUATION_ARTIFACT_ID,
                "rollout_clip",
                continuation_uri,
                CONTINUATION_HASH,
                ROLLOUT_RUN_ID,
            ),
            artifact(
                NON_PERSISTENCE_ARTIFACT_ID,
                "rollout_clip",
                non_persistence_uri,
                NON_PERSISTENCE_HASH,
                ROLLOUT_RUN_ID,
            ),
            artifact(
                PARTIAL_ARTIFACT_ID,
                "partial_rollout",
                partial_uri,
                PARTIAL_HASH,
                FAILED_RUN_ID,
                status="excluded",
                exclusion_reason="incomplete_generation_not_measurable",
            ),
            artifact(
                DIAGNOSTIC_ARTIFACT_ID,
                "diagnostic_log",
                diagnostic_uri,
                DIAGNOSTIC_HASH,
                FAILED_RUN_ID,
            ),
        ],
    }


def write_json(filename: str, value: Any) -> None:
    """Write one deterministic JSON fixture."""

    with (OUTPUT_DIR / filename).open("w", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, indent=2, sort_keys=True)
        file.write("\n")


def write_rejected_fixtures(
    manifest: dict[str, Any],
    registry: dict[str, Any],
) -> None:
    """Write invalid bundles that each expose an important contract rule."""

    def bundle() -> dict[str, Any]:
        return {
            "rollout_manifest": deepcopy(manifest),
            "registry": deepcopy(registry),
        }

    filename_only = bundle()
    del filename_only["rollout_manifest"]["rollout_rows"][0]["event_id"]
    write_json("rejected_filename_only_identity.json", filename_only)

    universal_identity = bundle()
    del universal_identity["rollout_manifest"]["rollout_rows"][0]["visibility"]
    write_json("rejected_universal_identity.json", universal_identity)

    failure_as_zero = bundle()
    failure_as_zero["rollout_manifest"]["rollout_rows"][2][
        "measured_displacement"
    ] = 0.0
    write_json("rejected_generation_failure_as_zero.json", failure_as_zero)

    non_persistence_as_zero = bundle()
    non_persistence_as_zero["rollout_manifest"]["rollout_rows"][1][
        "displacement_blocks"
    ] = 0.0
    write_json(
        "rejected_non_persistence_as_zero.json",
        non_persistence_as_zero,
    )

    bare_filename = bundle()
    bare_filename["rollout_manifest"]["rollout_rows"][0][
        "output_uri"
    ] = "continuation-001.mp4"
    bare_filename["registry"]["artifacts"][3][
        "uri"
    ] = "continuation-001.mp4"
    write_json("rejected_bare_filename_uri.json", bare_filename)

    conflated = bundle()
    conflated["rollout_manifest"]["rollout_rows"][1][
        "outcome"
    ] = "generation_failure"
    write_json("rejected_outcome_conflation.json", conflated)

    missing_run = bundle()
    missing_run["rollout_manifest"]["rollout_rows"][0][
        "run_id"
    ] = "unknown_producing_run"
    write_json("rejected_missing_run_lineage.json", missing_run)

    bad_supersession = bundle()
    bad_supersession["registry"]["artifacts"][2][
        "superseded_by"
    ] = "unknown_replacement_artifact"
    write_json("rejected_invalid_supersession.json", bad_supersession)

    parent_cycle = bundle()
    parent_cycle["registry"]["runs"][0]["parent_run_id"] = FAILED_RUN_ID
    write_json("rejected_parent_cycle.json", parent_cycle)

    malformed = bundle()
    malformed["rollout_manifest"]["rollout_rows"][0]["outcome"] = []
    malformed["rollout_manifest"]["rollout_rows"][1]["superseded_by"] = []
    malformed["registry"]["artifacts"][2]["superseded_by"] = []
    malformed["registry"]["artifacts"][0]["uri"] = "https://["
    malformed["registry"]["runs"][2]["execution_status"] = []
    write_json("rejected_malformed_types.json", malformed)

    lifecycle = bundle()
    lifecycle["registry"]["artifacts"][5]["exclusion_reason"] = None
    write_json("rejected_artifact_lifecycle.json", lifecycle)

    metadata = bundle()
    metadata["rollout_manifest"]["rollout_rows"][0][
        "output_hash"
    ] = "8" * 64
    write_json("rejected_metadata_mismatch.json", metadata)

    duplicate = bundle()
    duplicate["rollout_manifest"]["rollout_rows"][1][
        "rollout_id"
    ] = duplicate["rollout_manifest"]["rollout_rows"][0]["rollout_id"]
    write_json("rejected_duplicate_rollout_id.json", duplicate)


def main() -> None:
    """Regenerate all Step 1.6 evidence fixtures."""

    manifest = make_accepted_rollout_manifest()
    registry = make_accepted_registry()
    write_json("accepted_rollout_manifest.json", manifest)
    write_json("accepted_registry.json", registry)
    write_rejected_fixtures(manifest, registry)


if __name__ == "__main__":
    main()
