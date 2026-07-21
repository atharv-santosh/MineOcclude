"""Explicit-key A-to-B activation/target joining."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from mineocclude.contracts.activation import validate_activation_handoff
from mineocclude.contracts.identity import FRAME_KEY, IdentityValidationError, get_key
from mineocclude.oracle.schema import (
    OracleValidationError,
    validate_oracle_target_rows,
)


SOURCE_METADATA_FIELDS = (
    "episode_id",
    "server_tick",
    "render_frame_idx",
    "action_idx",
    "layout_id",
    "regime",
    "visibility",
    "tau",
    "v",
    "q",
    "duration",
    "model_hash",
    "preprocess_hash",
    "seed",
    "schema_version",
    "status",
    "exclusion_reason",
    "superseded_by",
)


class ActivationTargetJoinError(ValueError):
    """Raised when accepted A and B rows cannot join exactly."""


@dataclass(frozen=True)
class JoinedActivationTarget:
    """One validated layer/site activation row paired with one target row."""

    activation_index_row: Mapping[str, Any]
    target_row: Mapping[str, Any]

    @property
    def frame_key(self) -> tuple[Any, ...]:
        return get_key(self.target_row, FRAME_KEY)


def join_activation_targets(
    activation_package: Mapping[str, Any],
    target_rows: Iterable[Mapping[str, Any]],
) -> list[JoinedActivationTarget]:
    """Join without row-order or filename assumptions and fail closed."""

    validation = validate_activation_handoff(activation_package)
    if not validation.accepted:
        details = "; ".join(
            f"{rejection.code.value}: {rejection.message}"
            for rejection in validation.rejections
        )
        raise ActivationTargetJoinError(
            "Activation handoff failed schema-v1 validation: " + details
        )
    if activation_package["run_status"] != "completed":
        raise ActivationTargetJoinError(
            "Scientific probe joins require a completed activation run."
        )

    materialized_targets = list(target_rows)
    try:
        validate_oracle_target_rows(materialized_targets)
    except OracleValidationError as error:
        raise ActivationTargetJoinError(f"Invalid oracle targets: {error}") from error

    targets_by_key: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for target in materialized_targets:
        try:
            key = get_key(target, FRAME_KEY)
        except IdentityValidationError as error:
            raise ActivationTargetJoinError(f"Invalid oracle target: {error}") from error
        if target["status"] != "accepted":
            raise ActivationTargetJoinError("Only accepted targets may enter probes.")
        if key in targets_by_key:
            raise ActivationTargetJoinError(f"Duplicate target key: {key}.")
        if target["accepted_manifest_hash"] != activation_package["accepted_manifest_hash"]:
            raise ActivationTargetJoinError(
                "Target accepted-manifest hash does not match the activation handoff."
            )
        targets_by_key[key] = target

    activation_rows = list(activation_package["index_rows"])
    activation_frame_keys = {get_key(row, FRAME_KEY) for row in activation_rows}
    sites_by_frame: dict[tuple[Any, ...], set[tuple[Any, Any]]] = defaultdict(set)
    all_sites: set[tuple[Any, Any]] = set()
    for row in activation_rows:
        frame_key = get_key(row, FRAME_KEY)
        site = (row["layer_idx"], row["hook_site"])
        sites_by_frame[frame_key].add(site)
        all_sites.add(site)
    incomplete_frames = {
        key: sorted(all_sites - sites)
        for key, sites in sites_by_frame.items()
        if sites != all_sites
    }
    if incomplete_frames:
        raise ActivationTargetJoinError(
            "Activation handoff does not contain a complete layer/site grid; "
            f"missing_sites={incomplete_frames}."
        )

    target_keys = set(targets_by_key)
    if activation_frame_keys != target_keys:
        missing_targets = sorted(activation_frame_keys - target_keys)
        orphan_targets = sorted(target_keys - activation_frame_keys)
        raise ActivationTargetJoinError(
            f"Frame-key mismatch; missing_targets={missing_targets}, "
            f"orphan_targets={orphan_targets}."
        )

    joined: list[JoinedActivationTarget] = []
    for activation in activation_rows:
        target = targets_by_key[get_key(activation, FRAME_KEY)]
        for field in SOURCE_METADATA_FIELDS:
            if activation[field] != target[field]:
                raise ActivationTargetJoinError(
                    f"Source metadata mismatch for {field!r} at "
                    f"{get_key(activation, FRAME_KEY)}: activation="
                    f"{activation[field]!r}, target={target[field]!r}."
                )
        joined.append(
            JoinedActivationTarget(
                activation_index_row=activation,
                target_row=target,
            )
        )

    return sorted(
        joined,
        key=lambda item: (
            item.activation_index_row["trajectory_id"],
            item.activation_index_row["model_frame_idx"],
            item.activation_index_row["layer_idx"],
            item.activation_index_row["hook_site"],
        ),
    )
