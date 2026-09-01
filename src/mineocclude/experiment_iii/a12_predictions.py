"""A12 — held-out prediction generation (authority 8.8, 8.9; lifecycle A12).

This module owns what A12 actually is: **fit the frozen models on the frozen
folds and emit one held-out prediction per (identity, condition, row, model)
cell.** :mod:`prediction_lock` then hashes and seals them, and no statistic may
be opened before that seal exists.

It fits nothing of its own devising. Every recipe is already frozen elsewhere and
is applied here unchanged:

* the grouped nested ridge of §8.8 -- :mod:`readout`, over the five identity
  folds of §2.6 with four inner rotations and the five-value alpha grid;
* the linear current-frame pixel baseline of §8.9.1 -- the same ridge recipe over
  the persisted ``PIXEL_BASELINE`` block;
* last-seen (§8.9.2) and constant velocity (§8.9.3) -- oracle-state heuristics
  computed from counterfactual geometry, therefore identical across L0-L4 within
  an identity and fitted on nothing;
* the outer-training mean (§8.9.4) and the time-only design (§8.9.5) -- fitted on
  outer-training rows only.

**No identity is ever in its own training set.** The fold structure is read from
``folds.json`` and every fit is routed through :func:`readout.fit_outer_fold`,
which refuses an overlap; the outer-training-only baselines are additionally
checked here, because a mean taken over the wrong rows is arithmetically valid
and scientifically fatal.

Targets are the frozen causal-FIR labels of the identity manifest. They are
identical across the five conditions by authority 4.6, so a per-condition target
would be a target that moved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    DT_SECONDS,
    TARGET_ROWS_PER_CAPTURE,
)
from mineocclude.experiment_iii.baselines_motion import (
    CONSTANT_VELOCITY_WINDOW,
    ORACLE_BASELINES,
    constant_velocity,
    fit_time_only,
    last_seen,
    predict_time_only,
    training_mean,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.feature_store import (
    PIXEL_BLOCK,
    read_blocks_for_unit,
    unit_id,
)
from mineocclude.experiment_iii.prediction_lock import PredictionCell
from mineocclude.experiment_iii.readout import ALPHA_GRID, FoldData, cross_validated_predictions
from mineocclude.experiment_iii.schema import ConditionId

__all__ = [
    "PRIMARY_MODEL",
    "RIDGE_MODELS",
    "TEMPORAL_MODELS",
    "DEPTH_PANEL_MODELS",
    "BASELINE_MODELS",
    "ALL_MODELS",
    "PIXEL_MODEL",
    "IdentityInputs",
    "load_identity_inputs",
    "build_prediction_cells",
    "assert_no_identity_in_its_own_training_set",
]

#: §8.8 — the frozen primary cell: layer 19 | COARSE_2X6_CONCAT | CURRENT | ridge.
PRIMARY_MODEL = "MW_CURRENT"

#: §8.12 family B — the two temporal-rescue comparators, secondary and never
#: able to replace the primary readout.
TEMPORAL_MODELS = {
    "CURRENT_MINUS_PREVIOUS": "MW_CURRENT_MINUS_PREVIOUS",
    "TWO_FRAME_CONCAT": "MW_TWO_FRAME_CONCAT",
}

#: §8.12 family E — descriptive depth panel at the other two frozen layers.
DEPTH_PANEL_MODELS = {"CURRENT_L04": "MW_CURRENT_L04", "CURRENT_L10": "MW_CURRENT_L10"}

#: §8.9.1 — required manuscript language lives in baselines_pixel.
PIXEL_MODEL = "LINEAR_CURRENT_PIXEL"

#: Every model whose predictions come from the grouped nested ridge, mapped from
#: the persisted feature block it is fitted on.
RIDGE_MODELS: dict[str, str] = {
    PRIMARY_MODEL: "CURRENT",
    TEMPORAL_MODELS["CURRENT_MINUS_PREVIOUS"]: "CURRENT_MINUS_PREVIOUS",
    TEMPORAL_MODELS["TWO_FRAME_CONCAT"]: "TWO_FRAME_CONCAT",
    DEPTH_PANEL_MODELS["CURRENT_L04"]: "CURRENT_L04",
    DEPTH_PANEL_MODELS["CURRENT_L10"]: "CURRENT_L10",
    PIXEL_MODEL: PIXEL_BLOCK,
}

#: §8.9 — exactly five baselines. A13 verifies this count against the lock.
BASELINE_MODELS = (
    PIXEL_MODEL,
    "LAST_SEEN",
    "CONSTANT_VELOCITY",
    "TRAINING_MEAN",
    "TIME_ONLY",
)

#: The oracle-state heuristics, condition-invariant and fitted on nothing.
ORACLE_MODELS = ("LAST_SEEN", "CONSTANT_VELOCITY")

ALL_MODELS = tuple(RIDGE_MODELS) + ("LAST_SEEN", "CONSTANT_VELOCITY", "TRAINING_MEAN", "TIME_ONLY")

CONDITIONS = tuple(condition.value for condition in ConditionId)

#: §5.4 — context age runs 1..19 over the target window by construction;
#: target_manifest.context_ages refuses any window where it does not.
CONTEXT_AGES = tuple(range(1, TARGET_ROWS_PER_CAPTURE + 1))


class IdentityInputs:
    """Everything A12 needs about one identity, and nothing about an outcome."""

    __slots__ = ("identity", "direction", "targets", "positions", "occluded", "target_rows")

    def __init__(
        self,
        identity: str,
        direction: str,
        targets: Sequence[float],
        positions: Sequence[float],
        occluded: Sequence[bool],
        target_rows: Sequence[int],
    ) -> None:
        if len(targets) != TARGET_ROWS_PER_CAPTURE:
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH",
                f"{identity} carries {len(targets)} FIR labels, the authority "
                f"freezes {TARGET_ROWS_PER_CAPTURE}",
            )
        if len(target_rows) != TARGET_ROWS_PER_CAPTURE:
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH",
                f"{identity} names {len(target_rows)} target rows",
            )
        self.identity = identity
        self.direction = direction
        self.targets = np.asarray([float(v) for v in targets], dtype=np.float64)
        self.positions = [float(v) for v in positions]
        self.occluded = [bool(v) for v in occluded]
        self.target_rows = [int(v) for v in target_rows]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_identity_inputs(
    identity: str,
    manifest_row: Mapping[str, Any],
    capture_dir: Path,
) -> IdentityInputs:
    """Assemble one identity's targets and counterfactual motion series.

    The counterfactual position and occlusion series are read from the L0
    capture because they are counterfactual: authority 8.9.6 makes last-seen and
    constant-velocity identical across L0-L4 within an identity, so reading them
    per condition would be reading five copies of one series and inviting them to
    disagree.
    """
    coordinates = _read_jsonl(Path(capture_dir) / "coordinates.jsonl")
    visibility = _read_jsonl(Path(capture_dir) / "raw" / "visibility.jsonl")
    positions_by_tick = {int(row["server_tick"]): float(row["axis_pos"]) for row in coordinates}
    occluded_by_frame = {
        int(row["model_frame_idx"]): row["counterfactual_extent_class"]
        == "EXTENT_FULLY_OCCLUDED"
        for row in visibility
    }
    frames = sorted(occluded_by_frame)
    missing = [index for index in frames if index not in positions_by_tick]
    if missing:
        raise ExperimentIIIError(
            "PROVENANCE_BINDING_MISSING",
            f"{identity}: {len(missing)} visibility rows have no coordinate row, "
            f"e.g. {missing[:3]}",
        )
    return IdentityInputs(
        identity=identity,
        direction=str(manifest_row["direction"]),
        targets=manifest_row["expected_causal_fir_target_world_x_blocks"],
        positions=[positions_by_tick[index] for index in frames],
        occluded=[occluded_by_frame[index] for index in frames],
        target_rows=manifest_row["target_model_frame_indices"],
    )


def assert_no_identity_in_its_own_training_set(
    folds: Sequence[Mapping[str, Any]]
) -> None:
    """§8.9.6 leakage test 1, checked on the fold structure itself."""
    for fold in folds:
        outer = int(fold["outer_fold"])
        held = set(fold["held_out_identities"])
        training = set(fold["training_identities"])
        overlap = sorted(held & training)
        if overlap:
            raise ExperimentIIIError(
                "FOLD_LEAKAGE_DETECTED",
                f"outer fold {outer} places {overlap} in both its held-out and "
                f"its training set",
            )
        for rotation, members in fold["inner_rotations"].items():
            escaped = sorted(set(members) - training)
            if escaped:
                raise ExperimentIIIError(
                    "FOLD_LEAKAGE_DETECTED",
                    f"outer fold {outer} inner rotation {rotation} contains "
                    f"non-training identities {escaped}",
                )


def _fold_of(folds: Sequence[Mapping[str, Any]], identity: str) -> Mapping[str, Any]:
    for fold in folds:
        if identity in fold["held_out_identities"]:
            return fold
    raise ExperimentIIIError(
        "FOLD_LEAKAGE_DETECTED",
        f"{identity} is never held out by any outer fold; it would be scored by "
        f"a model that trained on it",
    )


def _ridge_predictions(
    features_root: Path,
    inputs: Mapping[str, IdentityInputs],
    folds: Sequence[Mapping[str, Any]],
    block: str,
    condition: str,
    *,
    feature_hashes: Mapping[str, Mapping[str, str]] | None,
) -> tuple[dict[str, np.ndarray], dict[int, Any]]:
    """One held-out prediction vector per identity for one (block, condition)."""
    data: dict[str, FoldData] = {}
    for identity, entry in inputs.items():
        unit = unit_id(identity, condition)
        expected = None if feature_hashes is None else feature_hashes.get(unit)
        blocks = read_blocks_for_unit(
            features_root, unit, blocks=(block,), expected_digests=expected
        )
        data[identity] = FoldData(
            identity=identity, features=blocks[block], targets=entry.targets
        )
    return cross_validated_predictions(data, folds, alpha_grid=ALPHA_GRID)


def _training_targets(
    inputs: Mapping[str, IdentityInputs], training_identities: Sequence[str]
) -> dict[str, list[float]]:
    present = [name for name in training_identities if name in inputs]
    if not present:
        raise ExperimentIIIError(
            "BASELINE_MISSING", "the outer-training set is empty for this fold"
        )
    return {name: list(inputs[name].targets) for name in present}


def build_prediction_cells(
    features_root: Path,
    inputs: Mapping[str, IdentityInputs],
    folds: Sequence[Mapping[str, Any]],
    *,
    feature_hashes: Mapping[str, Mapping[str, str]] | None = None,
    on_progress=None,
) -> tuple[list[PredictionCell], dict[str, Any]]:
    """Every held-out prediction cell, plus the fitting receipt A12 reports.

    Returns cells for exactly ``len(inputs) x 5 conditions x 19 rows x
    len(ALL_MODELS)``. Nothing here reads a statistic, and no quantity computed
    from a held-out target influences any fit.
    """
    assert_no_identity_in_its_own_training_set(folds)
    identities = sorted(inputs)
    cells: list[PredictionCell] = []
    alpha_selections: dict[str, dict[str, Any]] = {}

    # ---- the grouped nested ridge models, per condition -------------------
    for model, block in RIDGE_MODELS.items():
        alpha_selections[model] = {}
        for condition in CONDITIONS:
            predictions, selections = _ridge_predictions(
                features_root, inputs, folds, block, condition,
                feature_hashes=feature_hashes,
            )
            alpha_selections[model][condition] = {
                str(outer): selection.as_dict() for outer, selection in selections.items()
            }
            for identity in identities:
                vector = predictions[identity]
                if vector.shape[0] != TARGET_ROWS_PER_CAPTURE:
                    raise ExperimentIIIError(
                        "PREDICTION_LOCK_MISSING",
                        f"{model}/{identity}/{condition} produced "
                        f"{vector.shape[0]} predictions, the authority freezes "
                        f"{TARGET_ROWS_PER_CAPTURE}",
                    )
                targets = inputs[identity].targets
                for row in range(TARGET_ROWS_PER_CAPTURE):
                    cells.append(
                        PredictionCell(
                            identity=identity,
                            condition_id=condition,
                            row_index=row,
                            model=model,
                            prediction=float(vector[row]),
                            target=float(targets[row]),
                        )
                    )
            if on_progress is not None:
                on_progress(model, condition)

    # ---- the oracle-state heuristics: condition-invariant, fitted on nothing
    for identity in identities:
        entry = inputs[identity]
        oracle: dict[str, list[float]] = {"LAST_SEEN": [], "CONSTANT_VELOCITY": []}
        for target_row in entry.target_rows:
            oracle["LAST_SEEN"].append(
                last_seen(entry.positions, entry.occluded, target_row)
            )
            oracle["CONSTANT_VELOCITY"].append(
                constant_velocity(
                    entry.positions,
                    entry.occluded,
                    target_row,
                    window=CONSTANT_VELOCITY_WINDOW,
                    dt=DT_SECONDS,
                )
            )
        for model in ORACLE_MODELS:
            for condition in CONDITIONS:
                for row in range(TARGET_ROWS_PER_CAPTURE):
                    cells.append(
                        PredictionCell(
                            identity=identity,
                            condition_id=condition,
                            row_index=row,
                            model=model,
                            prediction=float(oracle[model][row]),
                            target=float(entry.targets[row]),
                        )
                    )

    # ---- the outer-training-only clock baselines --------------------------
    training_mean_by_fold: dict[int, float] = {}
    time_only_by_fold: dict[int, list[float]] = {}
    for fold in folds:
        outer = int(fold["outer_fold"])
        training_ids = [name for name in fold["training_identities"] if name in inputs]
        held = set(fold["held_out_identities"])
        leaked = sorted(set(training_ids) & held)
        if leaked:
            raise ExperimentIIIError(
                "FOLD_LEAKAGE_DETECTED",
                f"outer fold {outer} would fit its baselines on held-out "
                f"identities {leaked}",
            )
        targets = _training_targets(inputs, training_ids)
        # §8.9.4: unstratified unless A1 prospectively froze the stratified mean
        # as estimable in EVERY outer fold. Nothing froze it, so this is the
        # authority's own default and not a choice made here.
        training_mean_by_fold[outer] = float(
            training_mean(targets, stratify_by_direction=False)
        )
        ages: list[int] = []
        directions: list[str] = []
        values: list[float] = []
        for name in training_ids:
            ages.extend(CONTEXT_AGES)
            directions.extend([inputs[name].direction] * TARGET_ROWS_PER_CAPTURE)
            values.extend(float(v) for v in inputs[name].targets)
        time_only_by_fold[outer] = fit_time_only(ages, directions, values)

    for identity in identities:
        entry = inputs[identity]
        fold = _fold_of(folds, identity)
        outer = int(fold["outer_fold"])
        mean_value = training_mean_by_fold[outer]
        time_only_values = predict_time_only(
            time_only_by_fold[outer],
            CONTEXT_AGES,
            [entry.direction] * TARGET_ROWS_PER_CAPTURE,
        )
        for condition in CONDITIONS:
            for row in range(TARGET_ROWS_PER_CAPTURE):
                cells.append(
                    PredictionCell(
                        identity=identity,
                        condition_id=condition,
                        row_index=row,
                        model="TRAINING_MEAN",
                        prediction=float(mean_value),
                        target=float(entry.targets[row]),
                    )
                )
                cells.append(
                    PredictionCell(
                        identity=identity,
                        condition_id=condition,
                        row_index=row,
                        model="TIME_ONLY",
                        prediction=float(time_only_values[row]),
                        target=float(entry.targets[row]),
                    )
                )

    receipt = {
        "authority_section": "8.8, 8.9",
        "identities": identities,
        "conditions": list(CONDITIONS),
        "rows_per_cell": TARGET_ROWS_PER_CAPTURE,
        "models": list(ALL_MODELS),
        "primary_model": PRIMARY_MODEL,
        "baseline_models": list(BASELINE_MODELS),
        "oracle_models": sorted(ORACLE_BASELINES),
        "ridge_models": dict(RIDGE_MODELS),
        "alpha_grid": list(ALPHA_GRID),
        "alpha_selection_criterion": "IDENTITY_MACRO_INNER_VALIDATION_MEAN_RMSE",
        "alpha_tie_break": "SMALLEST_ALPHA",
        "alpha_selections": alpha_selections,
        "outer_folds": len(folds),
        "training_mean_by_outer_fold": training_mean_by_fold,
        "training_mean_direction_stratified": False,
        "held_out_tuning_performed": False,
        "no_identity_in_its_own_training_set": True,
        "expected_cells": len(identities) * len(CONDITIONS) * TARGET_ROWS_PER_CAPTURE * len(ALL_MODELS),
    }
    return cells, receipt
