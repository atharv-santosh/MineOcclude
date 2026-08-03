"""Real per-family fit/export dispatch for the Step 4.1 production runner.

Wires each of the eight frozen baseline families to its existing,
already-tested D implementation (``last_seen.predict_last_seen``,
``constant_velocity.predict_constant_velocity``, etc.) and shapes the
result into a ``person-b-baseline-input-v0.2`` document via
:func:`mineocclude.baselines.baseline_family_input_v0_2
.build_baseline_document_v0_2`. This module contains real,
callable execution logic -- it is exercised in tests against small
synthetic contexts/targets, but is never invoked against real data by
this preparation pass, since no real Person C capture data is present
on this machine (see the production CLI's own module docstring).

No baseline definition, target, fold, seed, or family configuration is
altered here: every fit call below uses each family module's existing,
frozen defaults exactly as already implemented and tested.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from mineocclude.baselines.baseline_family_input_v0_2 import (
    BASELINE_FAMILY_CONTRACTS_V0_2,
    BaselineFamilyInputV02Error,
    build_baseline_document_v0_2,
)
from mineocclude.baselines.constant_velocity import predict_constant_velocity
from mineocclude.baselines.explicit_feature import fit_predict_explicit_feature
from mineocclude.baselines.interface import BaselineRow, TrajectoryContext
from mineocclude.baselines.known_q_analytic import predict_known_q_analytic
from mineocclude.baselines.last_seen import predict_last_seen
from mineocclude.baselines.raw_pixel import fit_predict_raw_pixel
from mineocclude.baselines.shuffled import apply_grouped_shuffle
from mineocclude.baselines.time_only import fit_predict_time_only
from mineocclude.baselines.visible_history_q import fit_predict_visible_history_q

RowKey = tuple[str, int]

#: grouped_shuffled's frozen permutation seed -- copied from
#: BASELINE_FAMILY_CONTRACTS_V0_2["grouped_shuffled"]["configuration"],
#: never re-declared independently.
_GROUPED_SHUFFLED_SEED = BASELINE_FAMILY_CONTRACTS_V0_2["grouped_shuffled"]["configuration"][
    "permutation_seed"
]
_EXPLICIT_FEATURE_SEED = BASELINE_FAMILY_CONTRACTS_V0_2["explicit_feature"]["configuration"]["seed"]
_RAW_PIXEL_SEED = BASELINE_FAMILY_CONTRACTS_V0_2["raw_pixel"]["configuration"]["seed"]
_VISIBLE_HISTORY_Q_DT = BASELINE_FAMILY_CONTRACTS_V0_2["visible_history_q"]["configuration"][
    "dt_seconds"
]


class EightFamilyRunnerError(ValueError):
    """Raised when a family cannot be fit/exported from the supplied inputs."""


def _build_trajectory_targets(
    contexts: Sequence[TrajectoryContext],
    *,
    mu_oracle_by_key: Mapping[RowKey, float],
    log_sigma_oracle_by_key: Mapping[RowKey, float],
) -> dict:
    """Group per-row oracle targets by trajectory for grouped_shuffled's donor lookup."""

    by_trajectory: dict[str, dict[str, dict[int, float]]] = {}
    for ctx in contexts:
        bucket = by_trajectory.setdefault(
            ctx.trajectory_id, {"mu_oracle_blocks": {}, "log_sigma_oracle": {}}
        )
        key = (ctx.trajectory_id, ctx.model_frame_idx)
        if key in mu_oracle_by_key:
            bucket["mu_oracle_blocks"][ctx.model_frame_idx] = mu_oracle_by_key[key]
        if key in log_sigma_oracle_by_key:
            bucket["log_sigma_oracle"][ctx.model_frame_idx] = log_sigma_oracle_by_key[key]
    return by_trajectory


def compute_family_rows(
    family_id: str,
    contexts: Sequence[TrajectoryContext],
    *,
    mu_oracle_by_key: Mapping[RowKey, float],
    log_sigma_oracle_by_key: Mapping[RowKey, float],
    visible_positions_by_trajectory: Mapping[str, Sequence[float]],
    pixel_features_by_key: Mapping[RowKey, Sequence[float]],
) -> list[BaselineRow]:
    """Dispatch to the one existing D implementation this family already has.

    Every call below uses that module's own frozen defaults (alpha
    grid, inner-fold count, seed, degree, dt) exactly as already
    implemented -- none are overridden or re-derived here.
    """

    if family_id == "last_seen":
        return predict_last_seen(contexts)
    if family_id == "constant_velocity":
        return predict_constant_velocity(contexts)
    if family_id == "grouped_shuffled":
        trajectory_targets = _build_trajectory_targets(
            contexts,
            mu_oracle_by_key=mu_oracle_by_key,
            log_sigma_oracle_by_key=log_sigma_oracle_by_key,
        )
        return apply_grouped_shuffle(contexts, trajectory_targets, seed=_GROUPED_SHUFFLED_SEED)
    if family_id == "time_only":
        return fit_predict_time_only(contexts, log_sigma_oracle_by_key, degree=1)
    if family_id == "explicit_feature":
        return fit_predict_explicit_feature(
            contexts, mu_oracle_by_key, seed=_EXPLICIT_FEATURE_SEED
        )
    if family_id == "raw_pixel":
        return fit_predict_raw_pixel(
            contexts, mu_oracle_by_key, pixel_features_by_key, seed=_RAW_PIXEL_SEED
        )
    if family_id == "visible_history_q":
        return fit_predict_visible_history_q(
            contexts, visible_positions_by_trajectory, dt_seconds=_VISIBLE_HISTORY_Q_DT
        )
    if family_id == "known_q_analytic":
        return predict_known_q_analytic(contexts)
    raise EightFamilyRunnerError(f"unsupported baseline_family={family_id!r}")


def fit_and_export_family(
    family_id: str,
    contexts: Sequence[TrajectoryContext],
    *,
    mu_oracle_by_key: Mapping[RowKey, float],
    log_sigma_oracle_by_key: Mapping[RowKey, float],
    visible_positions_by_trajectory: Mapping[str, Sequence[float]],
    pixel_features_by_key: Mapping[RowKey, Sequence[float]],
    config_hash: str,
    input_manifest_hash: str,
    fit_manifest_hash: str,
    preprocessed_frame_manifest_reference: Mapping[str, object] | None = None,
) -> dict:
    """Fit one family and shape every target it produces into v0.2 documents.

    Returns ``{target_name: document}`` for every target this family's
    frozen contract declares. Raises :class:`EightFamilyRunnerError` if
    a required target has zero applicable rows (e.g. missing inputs) --
    this never fabricates a document from nothing.
    """

    if family_id not in BASELINE_FAMILY_CONTRACTS_V0_2:
        raise EightFamilyRunnerError(f"unsupported baseline_family={family_id!r}")

    rows = compute_family_rows(
        family_id,
        contexts,
        mu_oracle_by_key=mu_oracle_by_key,
        log_sigma_oracle_by_key=log_sigma_oracle_by_key,
        visible_positions_by_trajectory=visible_positions_by_trajectory,
        pixel_features_by_key=pixel_features_by_key,
    )

    contract = BASELINE_FAMILY_CONTRACTS_V0_2[family_id]
    documents: dict[str, dict] = {}
    for target_name in sorted(contract["target_names"]):
        try:
            documents[target_name] = build_baseline_document_v0_2(
                rows,
                baseline_id=f"{family_id}_v1",
                baseline_family=family_id,
                target_name=target_name,
                config_hash=config_hash,
                input_manifest_hash=input_manifest_hash,
                fit_manifest_hash=fit_manifest_hash,
                preprocessed_frame_manifest_reference=preprocessed_frame_manifest_reference,
                default_fit_id=f"{family_id}:{target_name}:v0_2",
            )
        except BaselineFamilyInputV02Error as error:
            raise EightFamilyRunnerError(
                f"{family_id}:{target_name}: {error}"
            ) from error
    return documents
