"""Build the Phase 1 Step 1.7 synthetic cross-role integration fixtures."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from mineocclude.contracts.activation import validate_activation_handoff
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.intervention_request import validate_intervention_request
from mineocclude.contracts.rollout_registry import validate_rollout_registry_bundle
from mineocclude.contracts.trajectory import validate_trajectory_package


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = Path(__file__).resolve().parent

TRAJECTORY_PATH = ROOT / "tests" / "fixtures" / "trajectory" / "accepted_package.json"
ACTIVATION_PATH = (
    ROOT / "tests" / "fixtures" / "activation" / "accepted_activation_handoff.json"
)
INTERVENTION_PATH = (
    ROOT / "tests" / "fixtures" / "intervention" / "accepted_intervention_request.json"
)
ROLLOUT_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "rollout_registry"
    / "accepted_rollout_manifest.json"
)
REGISTRY_PATH = (
    ROOT / "tests" / "fixtures" / "rollout_registry" / "accepted_registry.json"
)

FIXTURE_MARKER = {
    "synthetic": True,
    "scientific_use": "forbidden",
}


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON document."""

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def json_bytes(value: Any) -> bytes:
    """Return deterministic JSON bytes."""

    text = json.dumps(value, indent=2, sort_keys=True)
    return (text + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return the SHA-256 digest of bytes."""

    return hashlib.sha256(value).hexdigest()


def write_json(filename: str, value: Any) -> str:
    """Write deterministic JSON and return the exact file SHA-256."""

    payload = json_bytes(value)
    path = OUTPUT_DIR / filename
    path.write_bytes(payload)
    return sha256_bytes(payload)


def require_accepted(label: str, result: Any) -> None:
    """Raise clearly if an existing contract rejects integration evidence."""

    if result.accepted:
        return

    details = "\n".join(
        f"- {rejection.code}: {rejection.message}"
        for rejection in result.rejections
    )

    raise RuntimeError(f"{label} failed contract validation:\n{details}")


def frame_key(row: dict[str, Any]) -> tuple[str, int]:
    """Return the universal synthetic frame join key."""

    return (row["trajectory_id"], row["model_frame_idx"])


def build_token_map(
    trajectory: dict[str, Any],
    activation: dict[str, Any],
) -> dict[str, Any]:
    """Build one explicit MineWorld token map per model frame."""

    positions_by_frame: dict[tuple[str, int], list[int]] = {}

    for row in activation["index_rows"]:
        key = frame_key(row)
        positions = row["frame_token_positions"]
        previous = positions_by_frame.get(key)

        if previous is not None and previous != positions:
            raise RuntimeError(
                f"Activation layers disagree on frame-token positions for {key!r}."
            )

        positions_by_frame[key] = positions

    rows: list[dict[str, Any]] = []

    for source_row in trajectory["streams"]["frame_map"]:
        key = frame_key(source_row)

        if key not in positions_by_frame:
            raise RuntimeError(
                f"No activation token positions exist for trajectory frame {key!r}."
            )

        pair_start = source_row["model_frame_idx"] * 347
        expected_frame_positions = list(range(pair_start, pair_start + 336))

        if positions_by_frame[key] != expected_frame_positions:
            raise RuntimeError(
                "Activation token map disagrees with the locked MineWorld "
                f"336-frame-token layout for {key!r}."
            )

        action_token_positions = list(range(pair_start + 336, pair_start + 347))

        rows.append(
            {
                "episode_id": source_row["episode_id"],
                "trajectory_id": source_row["trajectory_id"],
                "server_tick": source_row["server_tick"],
                "render_frame_idx": source_row["render_frame_idx"],
                "action_idx": source_row["action_idx"],
                "model_frame_idx": source_row["model_frame_idx"],
                "frame_token_positions": expected_frame_positions,
                "action_token_positions": action_token_positions,
                "frame_token_count": 336,
                "action_token_count": 11,
                "state_action_token_count": 347,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "join_key": ["trajectory_id", "model_frame_idx"],
        "rows": rows,
    }


def build_oracle_targets(
    trajectory: dict[str, Any],
    activation: dict[str, Any],
) -> dict[str, Any]:
    """Build explicitly synthetic oracle-posterior target rows."""

    activation_identity: dict[tuple[str, int], dict[str, Any]] = {}

    for row in activation["index_rows"]:
        activation_identity.setdefault(frame_key(row), row)

    rows: list[dict[str, Any]] = []

    for index, source_row in enumerate(trajectory["streams"]["frame_map"]):
        key = frame_key(source_row)

        if key not in activation_identity:
            raise RuntimeError(f"No activation identity exists for oracle target {key!r}.")

        activation_row = activation_identity[key]

        rows.append(
            {
                "target_id": f"synthetic_oracle_target_{index:03d}",
                "episode_id": source_row["episode_id"],
                "trajectory_id": source_row["trajectory_id"],
                "server_tick": source_row["server_tick"],
                "render_frame_idx": source_row["render_frame_idx"],
                "action_idx": source_row["action_idx"],
                "model_frame_idx": source_row["model_frame_idx"],
                "layout_id": activation_row["layout_id"],
                "regime": activation_row["regime"],
                "visibility": activation_row["visibility"],
                "tau": activation_row["tau"],
                "v": activation_row["v"],
                "q": activation_row["q"],
                "duration": activation_row["duration"],
                "posterior_mean_blocks": [
                    float(index),
                    float(index) + 0.25,
                    float(index) + 0.50,
                ],
                "posterior_sigma_blocks": 0.50 + (0.10 * index),
                "target_source": "synthetic_placeholder_oracle",
                "synthetic": True,
                "scientific_use": "forbidden",
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "source_activation": {
            "handoff_id": activation["handoff_id"],
            "run_id": activation["run_id"],
            "accepted_manifest_hash": activation["accepted_manifest_hash"],
        },
        "join_key": ["trajectory_id", "model_frame_idx"],
        "rows": rows,
    }


def build_baseline_predictions(oracle_targets: dict[str, Any]) -> dict[str, Any]:
    """Build explicitly synthetic Person D placeholder predictions."""

    rows: list[dict[str, Any]] = []

    for index, target in enumerate(oracle_targets["rows"]):
        mean = target["posterior_mean_blocks"]

        rows.append(
            {
                "baseline_prediction_id": f"synthetic_baseline_prediction_{index:03d}",
                "baseline_id": "synthetic_clock_baseline",
                "trajectory_id": target["trajectory_id"],
                "model_frame_idx": target["model_frame_idx"],
                "predicted_mean_blocks": [
                    mean[0] + 0.10,
                    mean[1] - 0.05,
                    mean[2] + 0.05,
                ],
                "predicted_sigma_blocks": target["posterior_sigma_blocks"] + 0.05,
                "synthetic": True,
                "scientific_use": "forbidden",
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "join_key": ["trajectory_id", "model_frame_idx"],
        "rows": rows,
    }


def build_probe_manifests(
    oracle_targets: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create synthetic fit and validation event manifests."""

    event_rows: list[dict[str, Any]] = []

    for index, target in enumerate(oracle_targets["rows"]):
        event_rows.append(
            {
                "event_id": f"synthetic_probe_event_{index:03d}",
                "trajectory_id": target["trajectory_id"],
                "model_frame_idx": target["model_frame_idx"],
                "target_id": target["target_id"],
            }
        )

    fit = {
        "schema_version": SCHEMA_VERSION,
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "manifest_id": "synthetic_step_1_7_fit_manifest",
        "events": event_rows[:2],
    }

    validation = {
        "schema_version": SCHEMA_VERSION,
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "manifest_id": "synthetic_step_1_7_validation_manifest",
        "events": event_rows[2:],
    }

    return fit, validation


def align_intervention_request(
    request: dict[str, Any],
    rollout_manifest: dict[str, Any],
    fit_manifest: dict[str, Any],
    fit_manifest_hash: str,
    validation_manifest: dict[str, Any],
    validation_manifest_hash: str,
) -> dict[str, Any]:
    """Create a Step 1.7 request whose event manifests resolve exactly."""

    request = deepcopy(request)
    request["fixture_metadata"] = deepcopy(FIXTURE_MARKER)

    request["fit_manifest"] = {
        "manifest_id": fit_manifest["manifest_id"],
        "manifest_hash": fit_manifest_hash,
        "event_ids": [row["event_id"] for row in fit_manifest["events"]],
    }

    request["validation_manifest"] = {
        "manifest_id": validation_manifest["manifest_id"],
        "manifest_hash": validation_manifest_hash,
        "event_ids": [row["event_id"] for row in validation_manifest["events"]],
    }

    request["heldout_events"] = [
        {
            "event_id": row["event_id"],
            "layout_id": row["layout_id"],
            "trajectory_id": row["trajectory_id"],
        }
        for row in rollout_manifest["rollout_rows"]
    ]

    return request


def build_input_contexts(rollout_manifest: dict[str, Any]) -> dict[str, Any]:
    """Build logical context rows contained by one registered artifact."""

    rows: list[dict[str, Any]] = []

    for rollout in rollout_manifest["rollout_rows"]:
        rows.append(
            {
                "input_context_id": rollout["input_context_id"],
                "event_id": rollout["event_id"],
                "episode_id": rollout["episode_id"],
                "trajectory_id": rollout["trajectory_id"],
                "model_frame_idx": rollout["model_frame_idx"],
                "seed": rollout["seed"],
                "synthetic": True,
                "scientific_use": "forbidden",
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "join_key": ["input_context_id"],
        "rows": rows,
    }


def align_rollouts_with_request(
    rollout_manifest: dict[str, Any],
    request: dict[str, Any],
    context_hash: str,
) -> dict[str, Any]:
    """Make rollout intervention fields exactly match the B-to-A request."""

    manifest = deepcopy(rollout_manifest)
    alpha_by_dose = {row["dose_id"]: row for row in request["alpha_table"]}
    heldout_event_ids = {row["event_id"] for row in request["heldout_events"]}
    location = request["intervention_location"]
    direction_version = request["direction_metadata"]["direction_version"]

    for rollout in manifest["rollout_rows"]:
        dose_id = rollout["dose_id"]

        if dose_id not in alpha_by_dose:
            raise RuntimeError(
                f"Rollout dose {dose_id!r} is absent from the intervention request."
            )

        if rollout["event_id"] not in heldout_event_ids:
            raise RuntimeError(f"Rollout event {rollout['event_id']!r} is not held out.")

        dose = alpha_by_dose[dose_id]

        rollout["alpha_requested"] = dose["alpha_requested"]
        rollout["alpha_applied"] = dose["alpha_applied"]
        rollout["cap_reduced"] = dose["cap_reduced"]
        rollout["intended_block_shift"] = dose["intended_block_shift"]
        rollout["direction_version"] = direction_version
        rollout["layer_idx"] = location["layer_idx"]
        rollout["hook_site"] = location["hook_site"]
        rollout["timestep_idx"] = location["timestep_idx"]
        rollout["input_context_hash"] = context_hash

    return manifest


def update_registry_artifact(
    registry: dict[str, Any],
    artifact_id: str,
    *,
    sha256: str,
    uri: str,
) -> None:
    """Update one integration-copy registry artifact."""

    matches = [
        artifact
        for artifact in registry["artifacts"]
        if artifact["artifact_id"] == artifact_id
    ]

    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one registry artifact {artifact_id!r}.")

    matches[0]["sha256"] = sha256
    matches[0]["uri"] = uri


def build_measurements(rollout_manifest: dict[str, Any]) -> dict[str, Any]:
    """Build synthetic Person E measurement placeholders."""

    rows: list[dict[str, Any]] = []

    for index, rollout in enumerate(rollout_manifest["rollout_rows"]):
        if rollout["outcome"] == "measurable_continuation":
            measurement_status = "measured"
            displacement_blocks: float | None = 1.25
        elif rollout["outcome"] == "non_persistence":
            measurement_status = "not_measurable_non_persistence"
            displacement_blocks = None
        else:
            measurement_status = "generation_failed"
            displacement_blocks = None

        rows.append(
            {
                "measurement_id": f"synthetic_measurement_{index:03d}",
                "rollout_id": rollout["rollout_id"],
                "event_id": rollout["event_id"],
                "run_id": rollout["run_id"],
                "output_artifact_id": rollout["output_artifact_id"],
                "outcome": rollout["outcome"],
                "measurement_status": measurement_status,
                "displacement_blocks": displacement_blocks,
                "synthetic": True,
                "scientific_use": "forbidden",
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "join_key": ["rollout_id"],
        "rows": rows,
    }


def main() -> None:
    """Generate the complete Step 1.7 synthetic fixture bundle."""

    trajectory = load_json(TRAJECTORY_PATH)
    activation = load_json(ACTIVATION_PATH)
    base_request = load_json(INTERVENTION_PATH)
    base_rollout_manifest = load_json(ROLLOUT_PATH)
    registry = deepcopy(load_json(REGISTRY_PATH))

    require_accepted("trajectory package", validate_trajectory_package(trajectory))
    require_accepted("activation handoff", validate_activation_handoff(activation))

    token_map = build_token_map(trajectory, activation)
    oracle_targets = build_oracle_targets(trajectory, activation)
    baseline_predictions = build_baseline_predictions(oracle_targets)

    fit_manifest, validation_manifest = build_probe_manifests(oracle_targets)

    fit_hash = write_json("synthetic_fit_manifest.json", fit_manifest)
    validation_hash = write_json("synthetic_validation_manifest.json", validation_manifest)

    request = align_intervention_request(
        base_request,
        base_rollout_manifest,
        fit_manifest,
        fit_hash,
        validation_manifest,
        validation_hash,
    )

    require_accepted(
        "integration intervention request",
        validate_intervention_request(request),
    )

    request_hash = write_json("synthetic_intervention_request.json", request)

    input_contexts = build_input_contexts(base_rollout_manifest)
    context_hash = write_json("synthetic_input_contexts.json", input_contexts)

    rollout_manifest = align_rollouts_with_request(
        base_rollout_manifest,
        request,
        context_hash,
    )

    first_rollout = rollout_manifest["rollout_rows"][0]
    context_artifact_id = first_rollout["input_context_artifact_id"]
    request_artifact_id = first_rollout["intervention_request_artifact_id"]

    update_registry_artifact(
        registry,
        context_artifact_id,
        sha256=context_hash,
        uri="synthetic://step-1-7/contexts/synthetic_input_contexts.json",
    )

    update_registry_artifact(
        registry,
        request_artifact_id,
        sha256=request_hash,
        uri="synthetic://step-1-7/requests/synthetic_intervention_request.json",
    )

    require_accepted(
        "integration rollout/registry bundle",
        validate_rollout_registry_bundle(rollout_manifest, registry),
    )

    measurements = build_measurements(rollout_manifest)

    write_json("synthetic_token_map.json", token_map)
    write_json("synthetic_oracle_targets.json", oracle_targets)
    write_json("synthetic_baseline_predictions.json", baseline_predictions)
    write_json("synthetic_rollout_manifest.json", rollout_manifest)
    write_json("synthetic_registry.json", registry)
    write_json("synthetic_measurements.json", measurements)

    bundle = {
        "schema_version": SCHEMA_VERSION,
        "integration_id": "synthetic_cross_role_pipeline_001",
        "fixture_metadata": deepcopy(FIXTURE_MARKER),
        "synthetic_marker_scope": "document_and_nested_records",
        "expected_activation_sites": [
            {
                "layer_idx": 5,
                "hook_site": "residual_stream",
            },
            {
                "layer_idx": 12,
                "hook_site": "residual_stream",
            },
        ],
        "sources": {
            "trajectory_package": "../trajectory/accepted_package.json",
            "activation_handoff": "../activation/accepted_activation_handoff.json",
            "token_map": "synthetic_token_map.json",
            "oracle_targets": "synthetic_oracle_targets.json",
            "baseline_predictions": "synthetic_baseline_predictions.json",
            "fit_manifest": "synthetic_fit_manifest.json",
            "validation_manifest": "synthetic_validation_manifest.json",
            "intervention_request": "synthetic_intervention_request.json",
            "input_contexts": "synthetic_input_contexts.json",
            "rollout_manifest": "synthetic_rollout_manifest.json",
            "registry": "synthetic_registry.json",
            "measurements": "synthetic_measurements.json",
        },
        "explicit_join_keys": {
            "trajectory_to_normalized_actions": ["trajectory_id", "model_frame_idx"],
            "trajectory_to_token_map": ["trajectory_id", "model_frame_idx"],
            "trajectory_to_targets": ["trajectory_id", "model_frame_idx"],
            "targets_to_activations": ["trajectory_id", "model_frame_idx"],
            "targets_to_baselines": ["trajectory_id", "model_frame_idx"],
            "request_heldout_events_to_rollouts": ["event_id"],
            "request_alpha_table_to_rollouts": ["dose_id"],
            "contexts_to_rollouts": ["input_context_id"],
            "rollouts_to_runs": ["run_id"],
            "rollouts_to_input_context_artifacts": [
                "input_context_artifact_id",
                "artifact_id",
            ],
            "rollouts_to_intervention_request_artifacts": [
                "intervention_request_artifact_id",
                "artifact_id",
            ],
            "rollouts_to_output_artifacts": ["output_artifact_id", "artifact_id"],
            "rollouts_to_measurements": ["rollout_id"],
        },
        "documented_integrity_links": [
            "expected_activation_sites_to_activation_rows",
            "token_map_positions_to_mineworld_layout",
            "fit_manifest_hash_to_file_bytes",
            "validation_manifest_hash_to_file_bytes",
            "request_manifest_metadata_to_manifest_files",
            "input_context_hash_to_file_bytes",
            "intervention_request_hash_to_file_bytes",
            "logical_input_context_rows_to_rollouts",
            "rollout_measurement_failure_semantics",
            "orphaned_claim_bearing_row_enumeration",
        ],
    }

    write_json("synthetic_cross_role_bundle.json", bundle)

    print("Step 1.7 synthetic fixture bundle generated successfully.")


if __name__ == "__main__":
    main()
