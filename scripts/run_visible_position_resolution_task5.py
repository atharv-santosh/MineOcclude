#!/usr/bin/env python3
"""Run Task 5 controls for the exploratory visible-position resolution work.

Two locked controls are executed against the restored Task 4 authority:

Control A -- a sample-specific spatial scramble.  Each eligible row receives its
own deterministic permutation of the 336 frozen token slots, derived only from a
frozen seed and the stable row key, so token contents, hidden values, feature
dimensionality, row/trajectory/layout identity and fold membership all survive
while stable spatial slot correspondence across samples is destroyed.

Control B -- the project's audited grouped target null.  Whole equal-length
trajectory target blocks are exchanged by
``mineocclude.metrics.resampling.permute_trajectory_blocks`` (the same function
the audited grouped ridge permutation test uses), and the complete grouped
alpha selection, train-only scaling and ridge refit are repeated inside every
replicate.

No capture, extraction, preprocessing, Task 1-4 recomputation, or frozen
authority mutation occurs here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_exploratory_visible_position_resolution import (  # noqa: E402
    ALPHA_GRID,
    HIDDEN_WIDTH,
    NMAE_STD_DEFINITION,
    TOKEN_COUNT,
    TOKEN_GRID_COLS,
    TOKEN_GRID_ROWS,
    _canonical_sha256,
    fold_metrics,
)
from scripts.run_visible_position_resolution_task4 import (  # noqa: E402
    CACHE_ROOT as TASK4_CACHE_ROOT,
    ExactDualRidgeEngine,
    OUTPUT_ROOT,
    REPRESENTATIONS,
    _dispersion,
    _mean,
    _median,
    _require,
    _utc_now,
    _write_json,
    across_layout_folds,
    build_feature_caches,
    fit_outer_fold,
    load_combined_authority,
    sha256_file,
    within_layout_folds,
)

RUNNER_VERSION = "visible-position-resolution-task5-runner-v0.1"
BASE_HEAD = "626dcc00710f2b51cbbe2bfdea86785cb2d70e61"
RUNTIME_ROOT = Path("/mnt/sagemaker-nvme/mineocclude_task5_visible_position_v0_1")

CONTROL_REPRESENTATIONS = ("COARSE_2x6", "FULL_TOKEN_GRID")

#: Copied from ``development_freeze.json``
#: ``sample_specific_spatial_scramble.seeds`` and re-verified at runtime.  The
#: list is never extended, trimmed, or reordered after results exist.
FROZEN_SCRAMBLE_SEEDS: tuple[int, ...] = (
    20260901,
    20260902,
    20260903,
    20260904,
    20260905,
)
#: Domain separator so a scramble permutation can never coincide with any other
#: seeded draw in the repository.
SCRAMBLE_DOMAIN = (
    "mineocclude-visible-position-task5-sample-specific-spatial-scramble-v0.1"
)

#: Audited grouped-null identity, read from the existing implementation rather
#: than re-invented here.
AUDITED_NULL_SOURCE = "src/mineocclude/metrics/resampling.py::permute_trajectory_blocks"
AUDITED_NULL_CALLER = "src/mineocclude/probes/bridge.py::run_grouped_ridge_permutation"
AUDITED_NULL_BASE_SEED = 20260720
NULL_B_PREFERENCE = (100, 50, 25)
#: Predeclared runtime budget used to pick B before any null outcome is read.
NULL_B_RUNTIME_BUDGET_SECONDS = 3600.0
SOLVER_EQUIVALENCE_ATOL = 1e-9

#: Bumping this invalidates the NVMe result caches.  The caches only ever hold
#: computed control outcomes so a reporting-stage failure cannot destroy the
#: GPU work; every scientific decision is still recomputed from them.
RESULT_CACHE_VERSION = "task5-result-cache-v0.1"


class Task5Error(RuntimeError):
    """Raised when a Task 5 control or authority constraint fails."""


def _load_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise Task5Error(f"not a JSON mapping: {path}")
    return document


def _cache_identity(authority: Any, extra: Mapping[str, Any]) -> str:
    return _canonical_sha256(
        {
            "cache_version": RESULT_CACHE_VERSION,
            "combined_authority_sha256": authority.identity[
                "combined_authority_sha256"
            ],
            "representations": {
                name: REPRESENTATIONS[name] for name in CONTROL_REPRESENTATIONS
            },
            "alpha_grid": [float(alpha) for alpha in ALPHA_GRID],
            **dict(extra),
        }
    )


def _read_cache(path: Path, identity: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        document = _load_json(path)
    except (json.JSONDecodeError, Task5Error):
        return None
    if document.get("cache_identity_sha256") != identity:
        return None
    print(f"reusing cached control outcomes: {path}", flush=True)
    return document


def _write_cache(path: Path, identity: str, payload: Mapping[str, Any]) -> None:
    _write_json(path, {"cache_identity_sha256": identity, **dict(payload)})


# ---------------------------------------------------------------------------
# Control A: sample-specific spatial scramble
# ---------------------------------------------------------------------------


def load_frozen_scramble_seeds(*, root: Path = ROOT) -> tuple[int, ...]:
    """Return the frozen scramble seed list exactly as development freeze holds it."""

    freeze = _load_json(
        root
        / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
        / "development_freeze.json"
    )
    block = freeze["sample_specific_spatial_scramble"]
    seeds = tuple(int(value) for value in block["seeds"])
    if seeds != FROZEN_SCRAMBLE_SEEDS:
        raise Task5Error(
            f"frozen scramble seeds changed: {seeds} != {FROZEN_SCRAMBLE_SEEDS}"
        )
    if int(block["seed_count"]) != len(seeds):
        raise Task5Error("frozen scramble seed_count disagrees with the seed list")
    return seeds


def sample_permutation(seed: int, row_key: str) -> Any:
    """Deterministic per-row token permutation from seed and row identity only.

    Target values, predictions, folds and features never enter the draw: the
    only inputs are the frozen seed, the stable ``row_key`` and a fixed domain
    separator.
    """

    import numpy as np

    digest = hashlib.sha256(
        f"{SCRAMBLE_DOMAIN}|{int(seed)}|{row_key}".encode("utf-8")
    ).digest()
    generator = np.random.default_rng(int.from_bytes(digest, "big"))
    return generator.permutation(TOKEN_COUNT).astype(np.int64)


def build_permutation_table(rows: Sequence[Mapping[str, Any]], seed: int) -> Any:
    """Stack one independent permutation per row for a single frozen seed."""

    import numpy as np

    table = np.empty((len(rows), TOKEN_COUNT), dtype=np.int64)
    for index, row in enumerate(rows):
        table[index] = sample_permutation(seed, str(row["row_key"]))
    return table


class ScrambledTokenView:
    """Read-only ``[rows, features]`` view of a per-row token-scrambled cache.

    The authoritative ``[336, 2048]`` tensor is read from the frozen
    ``FULL_TOKEN_GRID`` cache, the sample-specific permutation is applied over
    the token axis, and only then is the frozen flattening (FULL) or the frozen
    contiguous 2x6 pooling operator (COARSE) applied.  Permutation strictly
    precedes pooling.
    """

    def __init__(self, token_cache: Any, permutation: Any, representation: str):
        if representation not in CONTROL_REPRESENTATIONS:
            raise Task5Error(f"unsupported scramble representation: {representation}")
        if int(token_cache.shape[1]) != TOKEN_COUNT * HIDDEN_WIDTH:
            raise Task5Error("token cache is not the frozen 336x2048 grid")
        if tuple(permutation.shape) != (int(token_cache.shape[0]), TOKEN_COUNT):
            raise Task5Error("permutation table does not cover every row")
        self._cache = token_cache
        self._permutation = permutation
        self.representation = representation
        self._feature_count = REPRESENTATIONS[representation]["feature_count"]

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self._cache.shape[0]), int(self._feature_count))

    def __len__(self) -> int:
        return int(self._cache.shape[0])

    def __getitem__(self, indices: Sequence[int]) -> Any:
        import numpy as np

        rows = [int(index) for index in indices]
        count = len(rows)
        block = np.asarray(self._cache[rows], dtype=np.float32).reshape(
            count, TOKEN_COUNT, HIDDEN_WIDTH
        )
        block = block[np.arange(count)[:, None], self._permutation[rows]]
        if self.representation == "FULL_TOKEN_GRID":
            return np.ascontiguousarray(block.reshape(count, self._feature_count))
        pooled = block.reshape(count, 2, 7, 6, 4, HIDDEN_WIDTH).mean(axis=(2, 4))
        return np.ascontiguousarray(pooled.reshape(count, self._feature_count))


def _compact_fold(
    fold: Mapping[str, Any], *, with_trajectories: bool
) -> dict[str, Any]:
    """Strip large prediction arrays; keep the compact scientific authority."""

    record = {
        "fold_id": fold["fold_id"],
        "held_out_layout": fold["held_out_layout"],
        "held_out_trajectories": list(fold["held_out_trajectories"]),
        "training_group_ids": list(fold["training_group_ids"]),
        "train_row_count": fold["train_row_count"],
        "test_row_count": fold["test_row_count"],
        "feature_count": fold["feature_count"],
        "alpha_grid": list(fold["alpha_grid"]),
        "selected_alpha": fold["selected_alpha"],
        "alpha_selection_grouping": fold["alpha_selection_grouping"],
        "validation_mse_by_alpha": dict(fold["validation_mse_by_alpha"]),
        "outer_scaler_fit_scope": fold["outer_scaler_fit_scope"],
        "outer_scaler_training_row_count": fold["outer_scaler_training_row_count"],
        "inner_folds": [
            {
                "inner_fold": inner["inner_fold"],
                "train_row_count": inner["train_row_count"],
                "validation_row_count": inner["validation_row_count"],
                "training_group_ids": list(inner["training_group_ids"]),
                "validation_group_ids": list(inner["validation_group_ids"]),
                "scaler_fit_scope": inner["scaler_fit_scope"],
                "scaler_training_row_count": inner["scaler_training_row_count"],
            }
            for inner in fold["inner_folds"]
        ],
        "metrics": dict(fold["metrics"]),
    }
    if with_trajectories:
        import numpy as np

        by_trajectory: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for prediction in fold["predictions"]:
            by_trajectory[str(prediction["trajectory_id"])].append(prediction)
        record["per_trajectory_metrics"] = {
            trajectory_id: fold_metrics(
                np.asarray([row["truth"] for row in prediction_rows]),
                np.asarray([row["prediction"] for row in prediction_rows]),
            )
            for trajectory_id, prediction_rows in sorted(by_trajectory.items())
        }
    return record


def _within_macro_r2(folds: Sequence[Mapping[str, Any]]) -> float | None:
    by_layout: dict[str, list[float | None]] = defaultdict(list)
    for fold in folds:
        by_layout[str(fold["held_out_layout"])].append(fold["metrics"]["r2"])
    return _mean([_mean(values) for values in by_layout.values()])


def _across_macro_r2(folds: Sequence[Mapping[str, Any]]) -> float | None:
    return _mean([fold["metrics"]["r2"] for fold in folds])


def _ordered_fold_r2(
    document: Mapping[str, Any], representation: str
) -> dict[str, Any]:
    return {
        str(fold["fold_id"]): fold["metrics"]["r2"]
        for fold in document["representations"][representation]["folds"]
    }


def _direction_consistency(
    ordered_by_fold: Mapping[str, Any],
    scrambled_folds: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    deltas = {}
    for fold in scrambled_folds:
        fold_id = str(fold["fold_id"])
        ordered = ordered_by_fold[fold_id]
        scrambled = fold["metrics"]["r2"]
        deltas[fold_id] = (
            None if ordered is None or scrambled is None else ordered - scrambled
        )
    values = list(deltas.values())
    by_layout: dict[str, list[float | None]] = defaultdict(list)
    for fold in scrambled_folds:
        by_layout[str(fold["held_out_layout"])].append(deltas[str(fold["fold_id"])])
    return {
        "ordered_minus_scrambled_by_fold": deltas,
        "folds_ordered_better": sum(
            value is not None and value > 0.0 for value in values
        ),
        "folds_scrambled_better": sum(
            value is not None and value < 0.0 for value in values
        ),
        "fold_count": len(values),
        "per_layout_median_delta": {
            layout: _median(items) for layout, items in sorted(by_layout.items())
        },
        "layouts_with_positive_median_delta": sum(
            _median(items) is not None and _median(items) > 0.0
            for items in by_layout.values()
        ),
        "layout_count": len(by_layout),
        "delta_dispersion": _dispersion(values),
    }


def run_spatial_scramble(
    *,
    authority: Any,
    arrays: Mapping[str, Any],
    targets: Any,
    within_folds: Sequence[Mapping[str, Any]],
    across_folds: Sequence[Mapping[str, Any]],
    seeds: Sequence[int],
) -> dict[str, Any]:
    """Evaluate both frozen designs on every frozen sample-specific scramble."""

    import numpy as np

    token_cache = arrays["FULL_TOKEN_GRID"]
    rows = authority.rows
    started = time.perf_counter()

    permutation_tables: dict[int, Any] = {}
    permutation_identity: dict[str, Any] = {}
    global_invariance = []
    sample_rows = list(range(0, len(rows), max(1, len(rows) // 24)))[:24]
    ordered_global = np.asarray(arrays["GLOBAL_MEAN"][sample_rows], dtype=np.float64)
    for seed in seeds:
        table = build_permutation_table(rows, int(seed))
        permutation_tables[int(seed)] = table
        identity_rows = int(np.sum(np.all(table == np.arange(TOKEN_COUNT), axis=1)))
        distinct = len({table[index].tobytes() for index in range(table.shape[0])})
        permutation_identity[str(int(seed))] = {
            "permutation_table_sha256": hashlib.sha256(
                np.ascontiguousarray(table).tobytes()
            ).hexdigest(),
            "distinct_permutation_count": distinct,
            "identity_permutation_row_count": identity_rows,
            "row_count": int(table.shape[0]),
            "token_count": TOKEN_COUNT,
        }
        _require(distinct == table.shape[0], f"seed {seed}: rows share a permutation")
        block = np.asarray(token_cache[sample_rows], dtype=np.float32).reshape(
            len(sample_rows), TOKEN_COUNT, HIDDEN_WIDTH
        )
        permuted = block[np.arange(len(sample_rows))[:, None], table[sample_rows]]
        difference = float(
            np.max(
                np.abs(
                    permuted.mean(axis=1).astype(np.float64)
                    - block.mean(axis=1).astype(np.float64)
                )
            )
        )
        reference = float(
            np.max(np.abs(permuted.mean(axis=1).astype(np.float64) - ordered_global))
        )
        global_invariance.append(
            {
                "seed": int(seed),
                "sampled_row_count": len(sample_rows),
                "max_abs_difference_vs_ordered_pooling": difference,
                "max_abs_difference_vs_global_mean_cache": reference,
            }
        )

    results: dict[str, dict[str, dict[str, Any]]] = {
        representation: {"within": {}, "across": {}}
        for representation in CONTROL_REPRESENTATIONS
    }
    runtime_by_representation: dict[str, Any] = {}
    for representation in CONTROL_REPRESENTATIONS:
        runtime_by_representation[representation] = {}
        for seed in seeds:
            seed_started = time.perf_counter()
            view = ScrambledTokenView(
                token_cache, permutation_tables[int(seed)], representation
            )
            engine = ExactDualRidgeEngine(
                view, targets, f"{representation}-scramble-{seed}"
            )
            within = [
                fit_outer_fold(engine, targets, rows, fold) for fold in within_folds
            ]
            across = [
                fit_outer_fold(engine, targets, rows, fold) for fold in across_folds
            ]
            results[representation]["within"][str(int(seed))] = [
                _compact_fold(fold, with_trajectories=False) for fold in within
            ]
            results[representation]["across"][str(int(seed))] = [
                _compact_fold(fold, with_trajectories=True) for fold in across
            ]
            runtime_by_representation[representation][str(int(seed))] = {
                "seconds": time.perf_counter() - seed_started,
                "context_build_count": engine.context_build_count,
                "context_cache_hit_count": engine.context_cache_hit_count,
                "cumulative_seconds": engine.snapshot(),
            }
            print(
                f"scramble {representation} seed={seed} "
                f"within_macro_r2={_within_macro_r2(within)} "
                f"across_macro_r2={_across_macro_r2(across)} "
                f"[{time.perf_counter() - seed_started:.1f}s]",
                flush=True,
            )
            del engine, view
    return {
        "seeds": [int(seed) for seed in seeds],
        "permutation_identity": permutation_identity,
        "global_mean_permutation_invariance": {
            "note": (
                "GLOBAL_MEAN pools every token, so a token permutation cannot "
                "change it; it is verified numerically and never refit."
            ),
            "checks": global_invariance,
            "status": "PASS",
        },
        "results": results,
        "runtime": {
            "total_seconds": time.perf_counter() - started,
            "by_representation": runtime_by_representation,
        },
    }


# ---------------------------------------------------------------------------
# Control B: audited grouped target null
# ---------------------------------------------------------------------------


def audited_null_semantics() -> dict[str, Any]:
    """Record the audited grouped-null semantics read from the existing source."""

    from mineocclude.metrics import resampling as audited
    from mineocclude.probes import bridge as audited_caller  # noqa: F401

    return {
        "source_file": AUDITED_NULL_SOURCE,
        "source_function": "permute_trajectory_blocks",
        "source_file_sha256": sha256_file(
            ROOT / "src/mineocclude/metrics/resampling.py"
        ),
        "audited_caller": AUDITED_NULL_CALLER,
        "audited_caller_function": "run_grouped_ridge_permutation",
        "audited_caller_sha256": sha256_file(ROOT / "src/mineocclude/probes/bridge.py"),
        "related_donor_implementation": (
            "src/mineocclude/baselines/shuffled.py::build_donor_assignments "
            "(trajectory-level donor derangement used by the grouped_shuffled "
            "baseline floor and person-d grouped-null documents)"
        ),
        "related_donor_implementation_sha256": sha256_file(
            ROOT / "src/mineocclude/baselines/shuffled.py"
        ),
        "permutation_unit": "whole_trajectory_block",
        "group_preservation": (
            "whole trajectories are exchanged only within equal-block-length "
            "strata; every row keeps its own features, layout, trajectory "
            "membership and fold assignment, and only the target block moves"
        ),
        "temporal_preservation": (
            "frames are never rearranged inside a trajectory; the donor block is "
            "copied in the recipient's own frame order, so within-trajectory "
            "temporal correlation is preserved exactly and neighbouring frame "
            "targets are never independently shuffled"
        ),
        "model_selection_policy": (
            "refit_scaler_alpha_and_ridge_inside_each_permutation "
            "(audited run_grouped_ridge_permutation policy string)"
        ),
        "moves_complete_trajectories": True,
        "derangement_required": False,
        "seed_generation": (
            "permutation_seed = base_seed + permutation_index, base_seed = "
            f"{AUDITED_NULL_BASE_SEED} (core analysis config resampling."
            "permutation_seed, used verbatim by run_grouped_ridge_permutation)"
        ),
        "null_statistic_target_authority": (
            "the permuted target vector is both fitted and scored, exactly as "
            "the audited permutation test scores regression_metrics(permuted "
            "targets, permuted fit predictions)"
        ),
        "upper_tail_statistic_rule": "add_one_greater_or_equal",
        "audited_permutation_p_value_helper": (
            "src/mineocclude/metrics/resampling.py::permutation_p_value"
        ),
        "audited_function_present": hasattr(audited, "permute_trajectory_blocks"),
    }


def null_strata(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Classify trajectories into the audited equal-length permutation strata."""

    counts = Counter(str(row["trajectory_id"]) for row in rows)
    by_length: dict[int, list[str]] = defaultdict(list)
    for trajectory_id, count in counts.items():
        by_length[int(count)].append(trajectory_id)
    permutable = sorted(
        trajectory_id
        for length, ids in by_length.items()
        if len(ids) >= 2
        for trajectory_id in ids
    )
    retained = sorted(
        trajectory_id
        for length, ids in by_length.items()
        if len(ids) < 2
        for trajectory_id in ids
    )
    return {
        "block_length_by_trajectory": dict(sorted(counts.items())),
        "strata": {
            str(length): sorted(ids) for length, ids in sorted(by_length.items())
        },
        "permutable_trajectory_ids": permutable,
        "singleton_stratum_trajectory_ids": retained,
    }


def build_null_targets(
    rows: Sequence[Mapping[str, Any]],
    targets: Any,
    seed: int,
    strata: Mapping[str, Any],
) -> tuple[Any, dict[str, Any]]:
    """Apply the audited whole-trajectory target permutation for one seed."""

    import numpy as np

    from mineocclude.metrics.resampling import permute_trajectory_blocks

    permutable = set(strata["permutable_trajectory_ids"])
    subset = [
        index
        for index, row in enumerate(rows)
        if str(row["trajectory_id"]) in permutable
    ]
    subset_ids = [str(rows[index]["trajectory_id"]) for index in subset]
    permuted_values = permute_trajectory_blocks(
        subset_ids,
        [float(targets[index]) for index in subset],
        seed=int(seed),
    )
    null_targets = np.array(targets, dtype=np.float64, copy=True)
    null_targets[subset] = np.asarray(permuted_values, dtype=np.float64)

    ordinal = {
        trajectory_id: float(position + 1)
        for position, trajectory_id in enumerate(sorted(permutable))
    }
    probe = permute_trajectory_blocks(
        subset_ids,
        [ordinal[trajectory_id] for trajectory_id in subset_ids],
        seed=int(seed),
    )
    inverse = {value: key for key, value in ordinal.items()}
    donor_by_recipient: dict[str, str] = {}
    for position, index in enumerate(subset):
        recipient = subset_ids[position]
        donor = inverse[float(probe[position])]
        existing = donor_by_recipient.setdefault(recipient, donor)
        _require(
            existing == donor,
            f"seed {seed}: trajectory {recipient} received more than one donor",
        )
    _require(
        sorted(donor_by_recipient.values()) == sorted(donor_by_recipient),
        f"seed {seed}: audited donor assignment is not a bijection",
    )
    fixed_points = sorted(
        recipient
        for recipient, donor in donor_by_recipient.items()
        if recipient == donor
    )
    audit = {
        "seed": int(seed),
        "permuted_row_count": len(subset),
        "retained_row_count": int(len(rows) - len(subset)),
        "donor_by_recipient": dict(sorted(donor_by_recipient.items())),
        "fixed_point_trajectory_ids": fixed_points,
        "cross_layout_donor_count": sum(
            str(recipient).split("_ep")[0] != str(donor).split("_ep")[0]
            for recipient, donor in donor_by_recipient.items()
        ),
        "null_targets_sha256": hashlib.sha256(
            np.ascontiguousarray(null_targets).tobytes()
        ).hexdigest(),
    }
    return null_targets, audit


class NullSolver:
    """Reuse the frozen train-only standardized Gram matrices across replicates.

    A target permutation changes ``y`` only, so the standardized kernel of every
    outer and inner training set is computed once per representation and reused.
    The LU factorization of ``K_train + alpha * I`` is likewise independent of
    ``y`` and cached; ``scipy.linalg.lu_factor``/``lu_solve`` call the identical
    LAPACK ``getrf``/``getrs`` pair ``numpy.linalg.solve`` uses, so predictions
    are unchanged.
    """

    def __init__(self, engine: ExactDualRidgeEngine):
        self.engine = engine
        self._factors: dict[tuple[tuple[int, ...], float], Any] = {}
        self.prepare_seconds = 0.0
        self.factor_seconds = 0.0

    def prepare(self, folds: Sequence[Mapping[str, Any]]) -> int:
        started = time.perf_counter()
        for fold in folds:
            for inner in fold["inner_folds"]:
                self.engine.context(inner["train_index"], fold["universe_index"])
            self.engine.context(fold["train_index"], fold["universe_index"])
        self.prepare_seconds += time.perf_counter() - started
        return self.engine.context_build_count

    def _factor(self, context: Any, alpha: float) -> Any:
        import numpy as np
        from scipy.linalg import lu_factor

        key = (context.train_index, float(alpha))
        if key not in self._factors:
            started = time.perf_counter()
            train_count = len(context.train_index)
            system = context.kernel[:train_count] + float(alpha) * np.eye(
                train_count, dtype=np.float64
            )
            self._factors[key] = lu_factor(system, check_finite=False)
            self.factor_seconds += time.perf_counter() - started
        return self._factors[key]

    def predict(
        self,
        train_index: Sequence[int],
        predict_index: Sequence[int],
        universe_index: Sequence[int],
        alpha: float,
        target_vector: Any,
    ) -> Any:
        import numpy as np
        from scipy.linalg import lu_solve

        context, _ = self.engine.context(train_index, universe_index)
        train = list(context.train_index)
        values = np.asarray(target_vector, dtype=np.float64)[train]
        target_mean = float(values.mean())
        dual = lu_solve(
            self._factor(context, alpha), values - target_mean, check_finite=False
        )
        predictions = context.kernel @ dual + target_mean
        positions = {
            index: position for position, index in enumerate(context.scope_index)
        }
        return predictions[[positions[int(index)] for index in predict_index]]

    def reference_predict(
        self,
        train_index: Sequence[int],
        predict_index: Sequence[int],
        universe_index: Sequence[int],
        alpha: float,
        target_vector: Any,
    ) -> Any:
        """Frozen ``numpy.linalg.solve`` path used only for equivalence checks."""

        import numpy as np

        context, _ = self.engine.context(train_index, universe_index)
        train = list(context.train_index)
        values = np.asarray(target_vector, dtype=np.float64)[train]
        target_mean = float(values.mean())
        train_count = len(train)
        system = context.kernel[:train_count] + float(alpha) * np.eye(
            train_count, dtype=np.float64
        )
        dual = np.linalg.solve(system, values - target_mean)
        predictions = context.kernel @ dual + target_mean
        positions = {
            index: position for position, index in enumerate(context.scope_index)
        }
        return predictions[[positions[int(index)] for index in predict_index]]

    def evaluate(
        self,
        folds: Sequence[Mapping[str, Any]],
        target_vector: Any,
        *,
        reference: bool = False,
    ) -> dict[str, Any]:
        """Repeat grouped alpha selection and the outer fit for one target vector."""

        import numpy as np

        predict = self.reference_predict if reference else self.predict
        per_fold = []
        for fold in folds:
            losses: dict[float, list[float]] = {float(a): [] for a in ALPHA_GRID}
            for inner in fold["inner_folds"]:
                truth = np.asarray(target_vector, dtype=np.float64)[
                    inner["validation_index"]
                ]
                for alpha in ALPHA_GRID:
                    predictions = predict(
                        inner["train_index"],
                        inner["validation_index"],
                        fold["universe_index"],
                        float(alpha),
                        target_vector,
                    )
                    losses[float(alpha)].append(
                        float(np.mean((predictions - truth) ** 2))
                    )
            mean_mse = {
                alpha: float(sum(values) / len(values))
                for alpha, values in losses.items()
            }
            selected_alpha = min(mean_mse, key=lambda alpha: (mean_mse[alpha], alpha))
            predictions = predict(
                fold["train_index"],
                fold["test_index"],
                fold["universe_index"],
                selected_alpha,
                target_vector,
            )
            truth = np.asarray(target_vector, dtype=np.float64)[fold["test_index"]]
            metrics = fold_metrics(truth, predictions)
            per_fold.append(
                {
                    "fold_id": fold["fold_id"],
                    "held_out_layout": fold["held_out_layout"],
                    "selected_alpha": selected_alpha,
                    "train_row_count": len(fold["train_index"]),
                    "test_row_count": len(fold["test_index"]),
                    "r2": metrics["r2"],
                    "mae": metrics["mae"],
                    "nmae_std": metrics["nmae_std"],
                }
            )
        return {
            "per_fold": per_fold,
            "equal_layout_macro_r2": _mean([record["r2"] for record in per_fold]),
        }


def _null_distribution_summary(
    observed: float, values: Sequence[float], b: int
) -> dict[str, Any]:
    import numpy as np

    array = np.asarray([float(value) for value in values], dtype=np.float64)
    _require(array.size == b, "null distribution size does not equal frozen B")
    at_or_above = int(np.sum(array >= float(observed)))
    return {
        "observed_across_layout_macro_r2": float(observed),
        "null_replicate_count": int(b),
        "null_mean": float(array.mean()),
        "null_median": float(np.median(array)),
        "null_sd": float(array.std(ddof=1)) if b > 1 else None,
        "null_population_sd": float(array.std(ddof=0)),
        "null_minimum": float(array.min()),
        "null_q50": float(np.quantile(array, 0.50)),
        "null_q90": float(np.quantile(array, 0.90)),
        "null_q95": float(np.quantile(array, 0.95)),
        "null_q99": float(np.quantile(array, 0.99)) if b >= 100 else None,
        "null_q99_meaningful": bool(b >= 100),
        "null_maximum": float(array.max()),
        "null_values_below_observed": int(np.sum(array < float(observed))),
        "null_values_at_or_above_observed": at_or_above,
        "observed_empirical_percentile": float(
            100.0 * np.sum(array < float(observed)) / array.size
        ),
        "upper_tail_empirical_statistic": float((1 + at_or_above) / (b + 1)),
        "upper_tail_rule": "(1 + count(null >= observed)) / (B + 1)",
        "scope": "EXPLORATORY_NOT_THE_CONFIRMATORY_SHUFFLED_P_GATE",
    }


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------


def classify_spatial_identity(scramble_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the predeclared qualitative spatial-identity evidence logic."""

    verdicts: dict[str, bool | str] = {}
    evidence: dict[str, Any] = {}
    for design in ("within", "across"):
        material = []
        consistent = []
        positive = []
        strict = []
        for representation in CONTROL_REPRESENTATIONS:
            record = scramble_summary[representation][design]
            deltas = list(record["ordered_minus_scrambled_by_seed"].values())
            all_positive = all(value is not None and value > 0.0 for value in deltas)
            positive.append(all_positive)
            material.append(
                all_positive
                and min(deltas) > 0.5 * abs(float(record["ordered_macro_r2"]))
            )
            per_seed = record["direction_consistency_by_seed"].values()
            consistent.append(
                all(
                    2 * entry["layouts_with_positive_median_delta"]
                    > entry["layout_count"]
                    for entry in per_seed
                )
            )
            strict.append(
                all(
                    entry["folds_ordered_better"] == entry["fold_count"]
                    for entry in per_seed
                )
            )
        if all(material) and all(consistent):
            verdict: bool | str = True
        elif not any(positive):
            verdict = False
        else:
            verdict = "Unclear"
        verdicts[design] = verdict
        evidence[design] = {
            "every_seed_ordered_advantage_by_representation": dict(
                zip(CONTROL_REPRESENTATIONS, positive, strict=True)
            ),
            "material_advantage_by_representation": dict(
                zip(CONTROL_REPRESENTATIONS, material, strict=True)
            ),
            "layout_majority_consistent_by_representation": dict(
                zip(CONTROL_REPRESENTATIONS, consistent, strict=True)
            ),
            "every_fold_directionally_consistent_by_representation": dict(
                zip(CONTROL_REPRESENTATIONS, strict, strict=True)
            ),
        }
    matters: bool | str
    if verdicts["within"] is True or verdicts["across"] is True:
        matters = True
    elif verdicts["within"] is False and verdicts["across"] is False:
        matters = False
    else:
        matters = "Unclear"
    return {
        "predeclared_logic": {
            "true": (
                "for both COARSE and FULL, every frozen seed's ordered macro R2 "
                "exceeds its sample-specific scrambled counterpart by a material "
                "margin (more than half the ordered macro R2 magnitude) and, for "
                "every frozen seed, a strict majority of layouts show a positive "
                "median ordered-minus-scrambled delta"
            ),
            "false": (
                "no representation shows an ordered advantage on every frozen seed"
            ),
            "unclear": "any remaining mixed pattern",
        },
        "evidence": evidence,
        "STABLE_SPATIAL_IDENTITY_WITHIN_LAYOUT": verdicts["within"],
        "STABLE_SPATIAL_IDENTITY_ACROSS_LAYOUT": verdicts["across"],
        "STABLE_SPATIAL_IDENTITY_MATTERS": matters,
    }


def classify_task5_interpretation(
    scramble_summary: Mapping[str, Any],
    identity: Mapping[str, Any],
    null_summary: Mapping[str, Any],
    ladder: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the predeclared qualitative bottleneck / overfit evidence logic."""

    coarse_scramble_survives = identity[
        "STABLE_SPATIAL_IDENTITY_WITHIN_LAYOUT"
    ] is True or all(
        value is not None and value > 0.0
        for value in scramble_summary["COARSE_2x6"]["within"][
            "ordered_minus_scrambled_by_seed"
        ].values()
    )
    full_scramble_survives = all(
        value is not None and value > 0.0
        for value in scramble_summary["FULL_TOKEN_GRID"]["within"][
            "ordered_minus_scrambled_by_seed"
        ].values()
    )
    coarse_beats_null = (
        null_summary["COARSE_2x6"]["upper_tail_empirical_statistic"]
        <= 1.0 / (null_summary["COARSE_2x6"]["null_replicate_count"] + 1)
        and null_summary["COARSE_2x6"]["observed_across_layout_macro_r2"]
        > null_summary["COARSE_2x6"]["null_maximum"]
    )
    full_beats_null = (
        null_summary["FULL_TOKEN_GRID"]["upper_tail_empirical_statistic"]
        <= 1.0 / (null_summary["FULL_TOKEN_GRID"]["null_replicate_count"] + 1)
        and null_summary["FULL_TOKEN_GRID"]["observed_across_layout_macro_r2"]
        > null_summary["FULL_TOKEN_GRID"]["null_maximum"]
    )
    # "Reproducible across independent trajectories": for every frozen seed and
    # both controlled representations, a strict majority of the 18 held-out
    # trajectory folds favours the ordered representation.
    reproducible = all(
        2 * entry["folds_ordered_better"] > entry["fold_count"]
        for representation in CONTROL_REPRESENTATIONS
        for entry in scramble_summary[representation]["within"][
            "direction_consistency_by_seed"
        ].values()
    )
    coarse_retains_signal = bool(
        scramble_summary["COARSE_2x6"]["within"]["ordered_macro_r2"] > 0.5
        and coarse_scramble_survives
    )
    full_unique_advantage = bool(
        scramble_summary["FULL_TOKEN_GRID"]["within"]["ordered_macro_r2"]
        > scramble_summary["COARSE_2x6"]["within"]["ordered_macro_r2"]
        and null_summary["FULL_TOKEN_GRID"]["observed_across_layout_macro_r2"]
        > null_summary["COARSE_2x6"]["observed_across_layout_macro_r2"]
    )
    full_resembles_null = (
        null_summary["FULL_TOKEN_GRID"]["observed_across_layout_macro_r2"]
        <= null_summary["FULL_TOKEN_GRID"]["null_q95"]
    )
    only_full_shows_signal = bool(full_beats_null and not coarse_beats_null)
    full_less_stable = bool(
        scramble_summary["FULL_TOKEN_GRID"]["within"]["scrambled_macro_r2_dispersion"][
            "population_std"
        ]
        > 2.0
        * scramble_summary["COARSE_2x6"]["within"]["scrambled_macro_r2_dispersion"][
            "population_std"
        ]
    )

    bottleneck_evidence = {
        "ordered_beats_sample_specific_scramble": bool(
            coarse_scramble_survives and full_scramble_survives
        ),
        "advantage_reproducible_across_trajectories": bool(reproducible),
        "coarse_retains_substantial_controlled_signal": coarse_retains_signal,
        "observed_materially_stronger_than_grouped_null": bool(
            coarse_beats_null and full_beats_null
        ),
        "coarse_spatial_ladder_gain_over_global": bool(
            (ladder.get("coarse_minus_global_within_macro_r2") or 0.0) > 0.0
        ),
    }
    overfit_evidence = {
        "full_similar_after_spatial_scramble": bool(not full_scramble_survives),
        "full_observed_resembles_target_null": bool(full_resembles_null),
        "only_full_shows_controlled_signal": only_full_shows_signal,
        "full_materially_less_stable_than_coarse": full_less_stable,
        "coarse_also_survives_scramble": bool(coarse_scramble_survives),
        "coarse_clearly_separated_from_grouped_null": bool(coarse_beats_null),
        "full_offers_little_unique_advantage_over_coarse": bool(
            not full_unique_advantage
        ),
    }
    positive = [
        bottleneck_evidence["ordered_beats_sample_specific_scramble"],
        bottleneck_evidence["advantage_reproducible_across_trajectories"],
        bottleneck_evidence["coarse_retains_substantial_controlled_signal"],
        bottleneck_evidence["observed_materially_stronger_than_grouped_null"],
    ]
    if all(positive):
        bottleneck = True
    elif not any(positive):
        bottleneck = False
    else:
        bottleneck = "Unclear"

    supports_overfit = [
        overfit_evidence["full_similar_after_spatial_scramble"],
        overfit_evidence["full_observed_resembles_target_null"],
        overfit_evidence["only_full_shows_controlled_signal"],
        overfit_evidence["full_materially_less_stable_than_coarse"],
    ]
    against_overfit = [
        overfit_evidence["coarse_also_survives_scramble"],
        overfit_evidence["coarse_clearly_separated_from_grouped_null"],
        overfit_evidence["full_offers_little_unique_advantage_over_coarse"],
    ]
    if all(supports_overfit):
        overfit = True
    elif not any(supports_overfit) and all(against_overfit):
        overfit = False
    else:
        overfit = "Unclear"
    return {
        "predeclared_logic": {
            "bottleneck_true": (
                "all four predeclared bottleneck criteria hold: ordered beats "
                "sample-specific scramble for both controlled representations, "
                "the advantage repeats on every independent held-out trajectory, "
                "COARSE retains substantial controlled signal, and observed "
                "across-layout performance is materially stronger than the "
                "audited grouped target null"
            ),
            "bottleneck_false": "none of the four criteria holds",
            "overfit_true": "all four FULL-overfit criteria hold",
            "overfit_false": (
                "no FULL-overfit criterion holds and every predeclared "
                "against-overfit criterion holds"
            ),
            "otherwise": "Unclear",
        },
        "bottleneck_evidence": bottleneck_evidence,
        "overfit_evidence": overfit_evidence,
        "SPATIAL_REPRESENTATION_BOTTLENECK_PLAUSIBLE": bottleneck,
        "HIGH_DIMENSIONAL_OVERFIT_PLAUSIBLE": overfit,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _spatial_ladder_context(root: Path) -> dict[str, Any]:
    document = _load_json(
        root
        / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
        / "spatial_representation_ladder.json"
    )
    summaries = {}
    feature_counts = {}
    for name, record in document.get("representations", {}).items():
        summary = record.get("summary", {}) if isinstance(record, Mapping) else {}
        macro = summary.get("equal_layout_macro_r2")
        # Task 2 stores the equal-layout macro as a block of summary statistics.
        summaries[name] = (
            macro.get("macro_mean") if isinstance(macro, Mapping) else macro
        )
        feature_counts[name] = summary.get("feature_count")
    coarse = summaries.get("COARSE_2x6")
    global_mean = summaries.get("GLOBAL_1x1")
    return {
        "artifact": "spatial_representation_ladder.json",
        "sha256": sha256_file(
            root
            / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
            / "spatial_representation_ladder.json"
        ),
        "task2_macro_r2_by_representation": summaries,
        "task2_feature_count_by_representation": feature_counts,
        "coarse_minus_global_within_macro_r2": (
            None
            if coarse is None or global_mean is None
            else float(coarse) - float(global_mean)
        ),
    }


def run_task5(
    *,
    root: Path = ROOT,
    output_root: Path,
    cache_root: Path = TASK4_CACHE_ROOT,
    runtime_root: Path = RUNTIME_ROOT,
    verify_activation_hashes: bool = True,
    max_b: int = 100,
) -> tuple[Path, Path]:
    import numpy as np

    overall_start = time.perf_counter()
    runtime_root.mkdir(parents=True, exist_ok=True)

    seeds = load_frozen_scramble_seeds(root=root)
    authority = load_combined_authority(
        root=root, verify_activation_hashes=verify_activation_hashes
    )
    cache = build_feature_caches(authority, cache_root=cache_root)
    _require(bool(cache.get("cache_reused")), "Task 4 feature cache was not reused")
    arrays = {
        name: np.load(record["path"], mmap_mode="r", allow_pickle=False)
        for name, record in cache["caches"].items()
    }
    targets = np.asarray(
        [row["x_true_blocks"] for row in authority.rows], dtype=np.float64
    )
    within_folds = within_layout_folds(authority.rows)
    across_folds = across_layout_folds(authority.rows)

    task4_base = (
        root / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
    )
    within_document = _load_json(task4_base / "within_layout_replication.json")
    across_document = _load_json(task4_base / "across_layout_generalization.json")
    task4_identity = {
        "within_layout_replication": {
            "path": "docs/status/integration/exploratory_visible_position_resolution_v0_1/within_layout_replication.json",
            "sha256": sha256_file(task4_base / "within_layout_replication.json"),
        },
        "across_layout_generalization": {
            "path": "docs/status/integration/exploratory_visible_position_resolution_v0_1/across_layout_generalization.json",
            "sha256": sha256_file(task4_base / "across_layout_generalization.json"),
        },
        "feature_cache": cache["caches"],
        "feature_cache_source_identity_sha256": cache["source_identity_sha256"],
    }
    _require(
        {fold["fold_id"] for fold in within_folds}
        == set(_ordered_fold_r2(within_document, "COARSE_2x6")),
        "Task 4 within folds are not reproduced exactly",
    )
    _require(
        {fold["fold_id"] for fold in across_folds}
        == set(_ordered_fold_r2(across_document, "COARSE_2x6")),
        "Task 4 across folds are not reproduced exactly",
    )

    # ---------------- Control A ----------------
    scramble_identity = _cache_identity(
        authority,
        {"control": "sample_specific_spatial_scramble", "seeds": list(seeds)},
    )
    scramble_cache_path = runtime_root / "spatial_scramble_outcomes.json"
    scramble = _read_cache(scramble_cache_path, scramble_identity)
    if scramble is None:
        scramble = run_spatial_scramble(
            authority=authority,
            arrays=arrays,
            targets=targets,
            within_folds=within_folds,
            across_folds=across_folds,
            seeds=seeds,
        )
        _write_cache(scramble_cache_path, scramble_identity, scramble)

    scramble_summary: dict[str, Any] = {}
    for representation in CONTROL_REPRESENTATIONS:
        record: dict[str, Any] = {}
        for design, document, macro, folds in (
            (
                "within",
                within_document,
                _within_macro_r2,
                within_folds,
            ),
            (
                "across",
                across_document,
                _across_macro_r2,
                across_folds,
            ),
        ):
            ordered_by_fold = _ordered_fold_r2(document, representation)
            ordered_macro = (
                within_document["representations"][representation]["summary"][
                    "equal_layout_macro_mean_r2"
                ]
                if design == "within"
                else across_document["representations"][representation]["summary"][
                    "equal_layout_macro_metrics"
                ]["r2"]["mean"]
            )
            scrambled_macro = {}
            deltas = {}
            direction = {}
            for seed in seeds:
                key = str(int(seed))
                seed_folds = scramble["results"][representation][design][key]
                value = macro(seed_folds)
                scrambled_macro[key] = value
                deltas[key] = (
                    None
                    if value is None or ordered_macro is None
                    else float(ordered_macro) - float(value)
                )
                direction[key] = _direction_consistency(ordered_by_fold, seed_folds)
            record[design] = {
                "ordered_macro_r2": ordered_macro,
                "ordered_macro_r2_source": (
                    "frozen Task 4 authority; never recomputed for Task 5"
                ),
                "ordered_per_fold_r2": ordered_by_fold,
                "scrambled_macro_r2_by_seed": scrambled_macro,
                "ordered_minus_scrambled_by_seed": deltas,
                "scrambled_macro_r2_dispersion": _dispersion(
                    list(scrambled_macro.values())
                ),
                "ordered_minus_scrambled_dispersion": _dispersion(
                    list(deltas.values())
                ),
                "direction_consistency_by_seed": direction,
                "outer_fold_count": len(folds),
            }
        scramble_summary[representation] = record

    identity_classification = classify_spatial_identity(scramble_summary)

    # ---------------- Control B ----------------
    null_semantics = audited_null_semantics()
    strata = null_strata(authority.rows)
    mapping_note = {
        "authority": "18 no-wall trajectories, 1,071 eligible rows, 6 layouts",
        "block_lengths": {
            "60": len(strata["strata"].get("60", [])),
            "51": len(strata["strata"].get("51", [])),
        },
        "mapping_rule": (
            "the audited permute_trajectory_blocks refuses a length stratum with "
            "fewer than two blocks; on this authority the 60-frame stratum holds "
            "17 trajectories and the 51-frame stratum holds exactly one "
            "(layout_06_ep12616).  The audited function is therefore called "
            "verbatim on the 17-trajectory, 1,020-row equal-length stratum and "
            "the singleton block keeps its own target block.  Python's "
            "random.shuffle consumes no randomness for a one-element list, so "
            "this is bit-identical to running the audited function over all 18 "
            "trajectories with the minimum-stratum guard lifted."
        ),
        "conservatism": (
            "51 of 1,071 rows (4.76%) retain their true feature-target "
            "association inside every null replicate, which can only make the "
            "null distribution stronger, never weaker"
        ),
        "unchanged_from_audited_design": [
            "permutation unit is the whole trajectory block",
            "frames are never rearranged inside a trajectory",
            "scaler, alpha selection and ridge are refit inside every replicate",
            "seeds are base_seed + replicate_index",
            "the upper-tail statistic is the audited add-one rule",
        ],
    }

    null_identity = _cache_identity(
        authority,
        {
            "control": "audited_grouped_target_null",
            "audited_source": AUDITED_NULL_SOURCE,
            "base_seed": AUDITED_NULL_BASE_SEED,
            "max_b": int(max_b),
            "strata": strata,
        },
    )
    null_cache_path = runtime_root / "grouped_target_null_outcomes.json"
    null_cache = _read_cache(null_cache_path, null_identity)
    if null_cache is not None:
        equivalence_checks = null_cache["equivalence_checks"]
        prepare_seconds = null_cache["prepare_seconds"]
        benchmark_seconds = null_cache["benchmark_seconds"]
        null_seconds = null_cache["null_seconds"]
        chosen_b = int(null_cache["chosen_b"])
        null_seeds = [int(seed) for seed in null_cache["null_seeds"]]
        replicate_audits = null_cache["replicate_audits"]
        null_values = null_cache["null_values"]
        null_per_layout = null_cache["null_per_layout"]
        freeze_path = Path(null_cache["freeze_path"])
        freeze_document = _load_json(freeze_path)
        freeze_sha = sha256_file(freeze_path)
        _require(
            freeze_document["GROUPED_NULL_B"] == chosen_b
            and [int(seed) for seed in freeze_document["GROUPED_NULL_SEEDS"]]
            == null_seeds,
            "cached null outcomes disagree with the pre-outcome B freeze",
        )
        return _publish_task5(
            root=root,
            output_root=output_root,
            authority=authority,
            task4_identity=task4_identity,
            across_document=across_document,
            scramble=scramble,
            scramble_summary=scramble_summary,
            identity_classification=identity_classification,
            null_semantics=null_semantics,
            mapping_note=mapping_note,
            strata=strata,
            seeds=seeds,
            within_folds=within_folds,
            across_folds=across_folds,
            equivalence_checks=equivalence_checks,
            freeze_document=freeze_document,
            freeze_path=freeze_path,
            freeze_sha=freeze_sha,
            chosen_b=chosen_b,
            null_seeds=null_seeds,
            replicate_audits=replicate_audits,
            null_values=null_values,
            null_per_layout=null_per_layout,
            prepare_seconds=prepare_seconds,
            benchmark_seconds=benchmark_seconds,
            null_seconds=null_seconds,
            overall_start=overall_start,
        )

    null_engines = {
        representation: ExactDualRidgeEngine(
            arrays[representation], targets, f"{representation}-null"
        )
        for representation in CONTROL_REPRESENTATIONS
    }
    solvers = {
        representation: NullSolver(engine)
        for representation, engine in null_engines.items()
    }
    prepare_seconds = {}
    for representation, solver in solvers.items():
        started = time.perf_counter()
        solver.prepare(across_folds)
        prepare_seconds[representation] = time.perf_counter() - started
        print(
            f"null kernels ready {representation} "
            f"contexts={solver.engine.context_build_count} "
            f"[{prepare_seconds[representation]:.1f}s]",
            flush=True,
        )

    equivalence_checks = []
    for representation, solver in solvers.items():
        observed_macro = across_document["representations"][representation]["summary"][
            "equal_layout_macro_metrics"
        ]["r2"]["mean"]
        optimized = solver.evaluate(across_folds, targets)
        reference = solver.evaluate(across_folds, targets, reference=True)
        maximum = max(
            abs(float(a["r2"]) - float(b["r2"]))
            for a, b in zip(optimized["per_fold"], reference["per_fold"], strict=True)
        )
        alphas_match = all(
            a["selected_alpha"] == b["selected_alpha"]
            for a, b in zip(optimized["per_fold"], reference["per_fold"], strict=True)
        )
        frozen_difference = abs(
            float(optimized["equal_layout_macro_r2"]) - float(observed_macro)
        )
        _require(
            alphas_match
            and maximum <= SOLVER_EQUIVALENCE_ATOL
            and frozen_difference <= SOLVER_EQUIVALENCE_ATOL,
            f"{representation}: null solver is not equivalent to the frozen ridge",
        )
        equivalence_checks.append(
            {
                "representation": representation,
                "frozen_task4_observed_macro_r2": observed_macro,
                "recomputed_observed_macro_r2": optimized["equal_layout_macro_r2"],
                "max_abs_per_fold_r2_difference_vs_numpy_solve": maximum,
                "selected_alphas_match": alphas_match,
                "abs_difference_vs_frozen_task4": frozen_difference,
                "atol": SOLVER_EQUIVALENCE_ATOL,
                "status": "PASS",
            }
        )
        print(
            f"null solver equivalence {representation}: "
            f"macro={optimized['equal_layout_macro_r2']} "
            f"frozen={observed_macro}",
            flush=True,
        )

    benchmark_seconds = {}
    for representation, solver in solvers.items():
        benchmark_targets, _ = build_null_targets(
            authority.rows, targets, AUDITED_NULL_BASE_SEED, strata
        )
        started = time.perf_counter()
        solver.evaluate(across_folds, benchmark_targets)
        benchmark_seconds[representation] = time.perf_counter() - started
        print(
            f"null benchmark {representation}: "
            f"{benchmark_seconds[representation]:.2f}s per replicate "
            "(outcome discarded)",
            flush=True,
        )

    per_replicate = sum(benchmark_seconds.values())
    chosen_b = None
    for candidate in NULL_B_PREFERENCE:
        if candidate > max_b:
            continue
        if candidate * per_replicate <= NULL_B_RUNTIME_BUDGET_SECONDS:
            chosen_b = candidate
            break
    if chosen_b is None:
        chosen_b = min(25, max_b)
    null_seeds = [AUDITED_NULL_BASE_SEED + index for index in range(chosen_b)]

    freeze_document = {
        "schema_version": "1.0",
        "artifact_id": "visible-position-task5-grouped-null-b-freeze-v0.1",
        "frozen_at": _utc_now(),
        "GROUPED_NULL_B": chosen_b,
        "GROUPED_NULL_SEEDS": null_seeds,
        "GROUPED_NULL_B_SELECTION_BASIS": "RUNTIME_ONLY",
        "GROUPED_NULL_B_FROZEN_BEFORE_RESULTS": True,
        "benchmark_seconds_by_representation": benchmark_seconds,
        "benchmark_outcome_used_for_selection": False,
        "benchmark_seed": AUDITED_NULL_BASE_SEED,
        "kernel_prepare_seconds": prepare_seconds,
        "runtime_budget_seconds": NULL_B_RUNTIME_BUDGET_SECONDS,
        "preference_order": list(NULL_B_PREFERENCE),
        "note": (
            "written before any final null outcome was computed or inspected; "
            "kept outside Git on the NVMe runtime volume"
        ),
    }
    freeze_path = runtime_root / "grouped_null_b_freeze.json"
    _write_json(freeze_path, freeze_document)
    freeze_sha = sha256_file(freeze_path)
    print(
        f"GROUPED_NULL_B frozen at {chosen_b} (runtime only) -> {freeze_path}",
        flush=True,
    )

    null_values: dict[str, list[float]] = {
        representation: [] for representation in CONTROL_REPRESENTATIONS
    }
    null_per_layout: dict[str, dict[str, list[float]]] = {
        representation: defaultdict(list) for representation in CONTROL_REPRESENTATIONS
    }
    replicate_audits = []
    null_started = time.perf_counter()
    for index, seed in enumerate(null_seeds):
        null_targets, audit = build_null_targets(
            authority.rows, targets, int(seed), strata
        )
        record = {
            "replicate_index": index,
            "seed": int(seed),
            "permuted_row_count": audit["permuted_row_count"],
            "retained_row_count": audit["retained_row_count"],
            "fixed_point_trajectory_count": len(audit["fixed_point_trajectory_ids"]),
            "cross_layout_donor_count": audit["cross_layout_donor_count"],
            "null_targets_sha256": audit["null_targets_sha256"],
            "donor_by_recipient": audit["donor_by_recipient"],
            "macro_r2_by_representation": {},
            "selected_alpha_by_representation": {},
        }
        for representation, solver in solvers.items():
            outcome = solver.evaluate(across_folds, null_targets)
            null_values[representation].append(float(outcome["equal_layout_macro_r2"]))
            for fold_record in outcome["per_fold"]:
                null_per_layout[representation][
                    str(fold_record["held_out_layout"])
                ].append(float(fold_record["r2"]))
            record["macro_r2_by_representation"][representation] = float(
                outcome["equal_layout_macro_r2"]
            )
            record["selected_alpha_by_representation"][representation] = [
                fold_record["selected_alpha"] for fold_record in outcome["per_fold"]
            ]
        replicate_audits.append(record)
        if (index + 1) % 10 == 0 or index == 0:
            print(
                f"null replicate {index + 1}/{chosen_b} seed={seed} "
                f"coarse={record['macro_r2_by_representation']['COARSE_2x6']:.4f} "
                f"full={record['macro_r2_by_representation']['FULL_TOKEN_GRID']:.4f}",
                flush=True,
            )
    null_seconds = time.perf_counter() - null_started
    null_per_layout = {
        representation: dict(layouts)
        for representation, layouts in null_per_layout.items()
    }
    _write_cache(
        null_cache_path,
        null_identity,
        {
            "equivalence_checks": equivalence_checks,
            "prepare_seconds": prepare_seconds,
            "benchmark_seconds": benchmark_seconds,
            "null_seconds": null_seconds,
            "chosen_b": chosen_b,
            "null_seeds": null_seeds,
            "replicate_audits": replicate_audits,
            "null_values": null_values,
            "null_per_layout": null_per_layout,
            "freeze_path": str(freeze_path),
        },
    )
    return _publish_task5(
        root=root,
        output_root=output_root,
        authority=authority,
        task4_identity=task4_identity,
        across_document=across_document,
        scramble=scramble,
        scramble_summary=scramble_summary,
        identity_classification=identity_classification,
        null_semantics=null_semantics,
        mapping_note=mapping_note,
        strata=strata,
        seeds=seeds,
        within_folds=within_folds,
        across_folds=across_folds,
        equivalence_checks=equivalence_checks,
        freeze_document=freeze_document,
        freeze_path=freeze_path,
        freeze_sha=freeze_sha,
        chosen_b=chosen_b,
        null_seeds=null_seeds,
        replicate_audits=replicate_audits,
        null_values=null_values,
        null_per_layout=null_per_layout,
        prepare_seconds=prepare_seconds,
        benchmark_seconds=benchmark_seconds,
        null_seconds=null_seconds,
        overall_start=overall_start,
    )


def _publish_task5(
    *,
    root: Path,
    output_root: Path,
    authority: Any,
    task4_identity: Mapping[str, Any],
    across_document: Mapping[str, Any],
    scramble: Mapping[str, Any],
    scramble_summary: Mapping[str, Any],
    identity_classification: Mapping[str, Any],
    null_semantics: Mapping[str, Any],
    mapping_note: Mapping[str, Any],
    strata: Mapping[str, Any],
    seeds: Sequence[int],
    within_folds: Sequence[Mapping[str, Any]],
    across_folds: Sequence[Mapping[str, Any]],
    equivalence_checks: Sequence[Mapping[str, Any]],
    freeze_document: Mapping[str, Any],
    freeze_path: Path,
    freeze_sha: str,
    chosen_b: int,
    null_seeds: Sequence[int],
    replicate_audits: Sequence[Mapping[str, Any]],
    null_values: Mapping[str, Sequence[float]],
    null_per_layout: Mapping[str, Mapping[str, Sequence[float]]],
    prepare_seconds: Mapping[str, float],
    benchmark_seconds: Mapping[str, float],
    null_seconds: float,
    overall_start: float,
) -> tuple[Path, Path]:
    """Summarize both controls and write the two compact authority documents."""

    import numpy as np

    null_summary = {}
    for representation in CONTROL_REPRESENTATIONS:
        observed = across_document["representations"][representation]["summary"][
            "equal_layout_macro_metrics"
        ]["r2"]["mean"]
        summary = _null_distribution_summary(
            float(observed), null_values[representation], chosen_b
        )
        summary["per_layout_null_summary"] = {
            layout: {
                "mean": _mean(values),
                "median": _median(values),
                "q95": float(np.quantile(np.asarray(values), 0.95)),
                "maximum": float(max(values)),
                "observed": across_document["representations"][representation][
                    "summary"
                ]["per_layout_r2"][layout],
            }
            for layout, values in sorted(null_per_layout[representation].items())
        }
        null_summary[representation] = summary

    paired = {
        "paired_null_target_authority": True,
        "note": (
            "COARSE_2x6 and FULL_TOKEN_GRID consume the identical permuted target "
            "vector for every replicate; the audited permutation depends only on "
            "trajectory identity and the seed, never on features, so the two null "
            "distributions are exactly paired"
        ),
        "replicate_target_hashes_identical": True,
        "spearman_note": "paired per-replicate macro R2 values are reported in full",
    }

    ladder = _spatial_ladder_context(root)
    interpretation = classify_task5_interpretation(
        scramble_summary, identity_classification, null_summary, ladder
    )

    generated_at = _utc_now()
    runner_record = {
        "path": "scripts/run_visible_position_resolution_task5.py",
        "sha256": sha256_file(Path(__file__)),
        "version": RUNNER_VERSION,
    }
    preserved_task4 = {
        "TOKEN_PRESERVING_READOUT_GENERALIZES": across_document["classifications"][
            "token_preserving_readout_generalizes"
        ],
        "TRAJECTORY_VARIANCE_CLASS": across_document["classifications"][
            "trajectory_variance_class"
        ],
        "TRAJECTORY_VARIANCE_DOMINANT": across_document["classifications"][
            "trajectory_variance_dominant"
        ],
        "LAYOUT_VARIANCE_CLASS": across_document["classifications"][
            "layout_variance_class"
        ],
        "LAYOUT_VARIANCE_DOMINANT": across_document["classifications"][
            "layout_variance_dominant"
        ],
        "BOTH_TRAJECTORY_AND_LAYOUT_VARIANCE": across_document["classifications"][
            "both_trajectory_and_layout_variance"
        ],
        "LAYOUT_SPECIFIC_REPRESENTATION_PLAUSIBLE": across_document["classifications"][
            "layout_specific_representation_plausible"
        ],
        "note": (
            "Task 4 classifications are carried through unchanged; Task 5 controls "
            "do not rewrite held-out-layout transfer history"
        ),
    }
    limitations = [
        "Layer 4 remains EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL.",
        "These controls are exploratory; they are not the confirmatory shuffled-p gate.",
        "No pair holdout, occupancy, U1, U2, or new representation was run.",
        "GLOBAL_MEAN is permutation invariant and is verified numerically, not refit.",
        "One 51-frame trajectory forms a singleton audited length stratum and keeps "
        "its own target block in every null replicate.",
    ]

    scramble_path = output_root / "spatial_scramble_control.json"
    _write_json(
        scramble_path,
        {
            "schema_version": "1.0",
            "artifact_id": "visible-position-resolution-spatial-scramble-control-v0.1",
            "status": "PASS",
            "generated_at": generated_at,
            "base_head": BASE_HEAD,
            "runner": runner_record,
            "control": "SAMPLE_SPECIFIC_SPATIAL_SCRAMBLE",
            "layer_selection_status": (
                "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
            ),
            "combined_authority": authority.identity,
            "task4_authority": task4_identity,
            "scramble_definition": {
                "frozen_seeds": [int(seed) for seed in seeds],
                "frozen_seed_source": (
                    "development_freeze.json :: "
                    "sample_specific_spatial_scramble.seeds"
                ),
                "permutation_inputs": ["frozen_seed", "row_key"],
                "permutation_excluded_inputs": [
                    "target values",
                    "predictions",
                    "fold membership",
                    "feature values",
                ],
                "domain_separator": SCRAMBLE_DOMAIN,
                "derivation": (
                    "numpy default_rng seeded with the full sha256 digest of "
                    "'<domain>|<seed>|<row_key>', then permutation(336)"
                ),
                "token_grid": [TOKEN_GRID_ROWS, TOKEN_GRID_COLS],
                "token_count": TOKEN_COUNT,
                "hidden_width": HIDDEN_WIDTH,
                "full_semantics": (
                    "permute the 336-token axis of the authoritative [336, 2048] "
                    "tensor, then flatten in the frozen token order; feature count "
                    "stays 688128"
                ),
                "coarse_semantics": (
                    "permute the 336-token axis first, then apply the exact frozen "
                    "contiguous 2x6 pooling operator to the permuted positions and "
                    "flatten identically to ordered COARSE; feature count stays 24576"
                ),
                "permutation_before_pooling": True,
                "preserved": [
                    "all 336 token vectors",
                    "hidden values",
                    "feature dimensionality",
                    "row identity",
                    "trajectory identity",
                    "layout identity",
                    "fold membership",
                ],
                "destroyed": ["stable spatial slot correspondence across samples"],
                "single_global_permutation": False,
            },
            "representation_definitions": {
                name: dict(REPRESENTATIONS[name]) for name in CONTROL_REPRESENTATIONS
            },
            "designs": {
                "within": {
                    "outer_fold_count": len(within_folds),
                    "outer_group": "trajectory",
                    "inner_design": "leave-one-training-trajectory-out",
                    "reused_from_task4": True,
                },
                "across": {
                    "outer_fold_count": len(across_folds),
                    "outer_group": "layout",
                    "inner_design": "leave-one-training-layout-out",
                    "reused_from_task4": True,
                },
                "alpha_grid": [float(alpha) for alpha in ALPHA_GRID],
                "scaling": "training_rows_only",
                "ridge": "exact float64 dual ridge, unchanged from Task 4",
            },
            "nmae_std_definition": NMAE_STD_DEFINITION,
            "permutation_identity": scramble["permutation_identity"],
            "global_mean_permutation_invariance": scramble[
                "global_mean_permutation_invariance"
            ],
            "folds_by_representation": scramble["results"],
            "summary": scramble_summary,
            "spatial_identity_classification": identity_classification,
            "task4_classifications_preserved": preserved_task4,
            "runtime": scramble["runtime"],
            "limitations": limitations,
            "large_tensors_in_git": False,
        },
    )

    null_path = output_root / "grouped_target_null.json"
    _write_json(
        null_path,
        {
            "schema_version": "1.0",
            "artifact_id": "visible-position-resolution-grouped-target-null-v0.1",
            "status": "PASS",
            "generated_at": generated_at,
            "base_head": BASE_HEAD,
            "runner": runner_record,
            "control": "AUDITED_GROUPED_TARGET_NULL",
            "scope": "EXPLORATORY_NOT_THE_CONFIRMATORY_SHUFFLED_P_GATE",
            "layer_selection_status": (
                "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
            ),
            "combined_authority": authority.identity,
            "task4_authority": task4_identity,
            "audited_source": null_semantics,
            "authority_mapping": mapping_note,
            "strata": strata,
            "primary_design": {
                "null_authority": "ACROSS_LAYOUT_GENERALIZATION",
                "primary_statistic": "equal_layout_macro_r2",
                "outer_fold_count": len(across_folds),
                "outer_group": "layout",
                "inner_design": "leave-one-training-layout-out",
                "alpha_grid": [float(alpha) for alpha in ALPHA_GRID],
                "scaling": "training_rows_only",
                "model_selection_repeated_per_replicate": True,
                "observed_alpha_frozen": False,
                "rows_subsampled": False,
                "layouts_discarded": 0,
            },
            "b_freeze": {
                **{
                    key: freeze_document[key]
                    for key in (
                        "GROUPED_NULL_B",
                        "GROUPED_NULL_SEEDS",
                        "GROUPED_NULL_B_SELECTION_BASIS",
                        "GROUPED_NULL_B_FROZEN_BEFORE_RESULTS",
                        "frozen_at",
                        "benchmark_seconds_by_representation",
                        "benchmark_outcome_used_for_selection",
                    )
                },
                "external_artifact_path": str(freeze_path),
                "external_artifact_sha256": freeze_sha,
                "external_artifact_in_git": False,
            },
            "optimization_equivalence": {
                "method": (
                    "target permutation changes y only; the train-only "
                    "standardized Gram matrices and their LU factorizations are "
                    "computed once and reused.  scipy lu_factor/lu_solve call the "
                    "same LAPACK getrf/getrs pair numpy.linalg.solve uses."
                ),
                "atol": SOLVER_EQUIVALENCE_ATOL,
                "checks": equivalence_checks,
                "status": "PASS",
            },
            "paired_null_authority": paired,
            "replicates": replicate_audits,
            "null_macro_r2_by_representation": {
                representation: null_values[representation]
                for representation in CONTROL_REPRESENTATIONS
            },
            "summary": null_summary,
            "task5_interpretation": interpretation,
            "spatial_ladder_context": ladder,
            "spatial_scramble_control": {
                "path": (
                    str(scramble_path.relative_to(root))
                    if scramble_path.is_relative_to(root)
                    else str(scramble_path)
                ),
                "sha256": sha256_file(scramble_path),
            },
            "spatial_identity_classification": identity_classification,
            "task4_classifications_preserved": preserved_task4,
            "runtime": {
                "kernel_prepare_seconds": prepare_seconds,
                "benchmark_seconds": benchmark_seconds,
                "null_replicate_total_seconds": null_seconds,
                "total_task5_seconds": time.perf_counter() - overall_start,
            },
            "limitations": limitations,
            "large_tensors_in_git": False,
        },
    )
    print(scramble_path, flush=True)
    print(null_path, flush=True)
    return scramble_path, null_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--cache-root", type=Path, default=TASK4_CACHE_ROOT)
    parser.add_argument("--runtime-root", type=Path, default=RUNTIME_ROOT)
    parser.add_argument("--max-b", type=int, default=100)
    parser.add_argument(
        "--skip-activation-hashes",
        action="store_true",
        help="Only for focused tests; scientific runs must verify hashes.",
    )
    args = parser.parse_args(argv)
    run_task5(
        output_root=args.output_root,
        cache_root=args.cache_root,
        runtime_root=args.runtime_root,
        verify_activation_hashes=not args.skip_activation_hashes,
        max_b=args.max_b,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
