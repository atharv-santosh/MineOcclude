"""Step 4.3 positive-control statistical gate (Person D).

Roadmap Step 4.3 (the no-wall positive control) is marked COMPLETE, but
only its structural half exists: :func:`mineocclude.baselines.controls
.audit_no_wall_control` confirms every no-wall frame really is always
visible with ``tau=0``. The scientific half was never built: fit the
frozen visible-position ridge on no-wall rows using Person B's real
fold/metric authorities, and require held-out R^2 >= 0.50 with a
bootstrap CI strictly above zero before anything downstream may claim
the pipeline can decode *any* hidden-state representation at all. This
is the gate separating "the model has no hidden-state representation"
from "our pipeline cannot decode anything."

This lives in its own module rather than ``controls.py`` because it
pulls in Person B's ridge/metrics/resampling machinery and a real
sealed fold manifest, where ``controls.py`` deliberately stays free of
any statistical-fitting dependency for its lightweight structural
audits (no numpy, no fold manifests, no bootstrap).

D never assigns folds, never re-derives Person B's regression metric,
and never invents a bootstrap procedure:

- fold membership comes only from
  :func:`mineocclude.baselines.export.attach_b_fold_assignments`
  against a caller-supplied sealed B fold manifest;
- ridge fitting is Person B's
  :func:`mineocclude.probes.ridge.fit_ridge_oof`;
- R^2 is Person B's
  :func:`mineocclude.metrics.u1_mean.regression_metrics`;
- the bootstrap unit, resample count, and seed come from the frozen
  ``configs/analysis/core.yaml`` ``resampling`` section via Person B's
  :mod:`mineocclude.metrics.resampling` primitives, not an invented
  bootstrap of D's own.

Fail-closed contract: real no-wall rows, a real B fold manifest, and
real oracle targets do not exist yet anywhere in this repository. This
gate must never report ``PASSED`` on top of anything but a caller's
explicit, literal declaration that its inputs really are Person C's
accepted no-wall capture data (``REAL_NO_WALL_DATA_PROVENANCE``); any
other ``data_provenance`` value -- including every synthetic fixture in
this test suite -- makes the gate report ``BLOCKED`` before any ridge
is even fit and before any R^2 is computed. There is no default for
``data_provenance``: every caller must choose explicitly, so a
synthetic run can never be silently mistaken for a satisfied gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from mineocclude.analysis.config import load_core_analysis_config
from mineocclude.baselines.controls import audit_no_wall_control
from mineocclude.baselines.export import BaselineExportError, attach_b_fold_assignments
from mineocclude.baselines.interface import TrajectoryContext
from mineocclude.metrics.resampling import (
    ResamplingError,
    bootstrap_confidence_interval,
    hierarchical_bootstrap_indices,
)
from mineocclude.metrics.u1_mean import U1MetricError, regression_metrics
from mineocclude.probes.ridge import ProbeFitError, fit_ridge_oof

RowKey = Tuple[str, int]

#: The only ``data_provenance`` value that unlocks a scientific
#: PASSED/FAILED verdict. Anything else -- including every synthetic
#: fixture in this repository -- reports BLOCKED before any statistics
#: are computed. There is deliberately no boolean shortcut (e.g.
#: ``is_real=True``): a caller must reproduce this exact literal to
#: get past BLOCKED, which keeps a mislabeling honest and visible in
#: any code review rather than a silent default.
REAL_NO_WALL_DATA_PROVENANCE = "person_c_accepted_no_wall_capture"

#: Roadmap Step 4.3's frozen pass threshold: held-out R^2 >= 0.50.
STEP_4_3_R2_THRESHOLD = 0.50

#: Roadmap Step 4.3's frozen bootstrap coverage for the CI check.
BOOTSTRAP_COVERAGE = 0.95


class PositiveControlGateError(ValueError):
    """Raised when the gate's inputs are structurally invalid.

    This is distinct from a BLOCKED finding: a finding of BLOCKED means
    "the inputs are structurally fine, but not declared real"; this
    exception means the inputs could not even be evaluated (e.g. the
    no-wall structural audit itself failed, a required target is
    missing, or B's fold manifest does not validate).
    """


@dataclass(frozen=True)
class PositiveControlGateFinding:
    status: str
    """One of ``"PASSED"``, ``"FAILED"``, or ``"BLOCKED"``."""

    r2: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    n_rows: int
    fold_count: Optional[int]
    resample_count: Optional[int]
    seed: Optional[int]
    r2_threshold: float
    data_provenance: str
    detail: str


def evaluate_no_wall_positive_control_gate(
    contexts: Sequence[TrajectoryContext],
    mu_oracle_by_key: Mapping[RowKey, float],
    *,
    fold_manifest: Mapping[str, object],
    data_provenance: str,
    r2_threshold: float = STEP_4_3_R2_THRESHOLD,
) -> PositiveControlGateFinding:
    """Run Step 4.3's positive-control ridge and report a fail-closed verdict.

    ``data_provenance`` must equal :data:`REAL_NO_WALL_DATA_PROVENANCE`
    for this to report anything but ``BLOCKED`` -- see the module
    docstring. When blocked, no ridge is fit and no R^2 is computed;
    the finding's numeric fields are ``None``, never a fabricated or
    stubbed value.

    Raises :class:`PositiveControlGateError` if the no-wall structural
    audit fails, a target/position is missing for a submitted row, or
    the supplied fold manifest does not validate against Person B's
    real authority -- these are engineering-input errors, not a
    scientific verdict.
    """

    if not contexts:
        raise PositiveControlGateError("no no-wall contexts supplied")

    structural_audit = audit_no_wall_control(contexts)
    if not structural_audit.passed:
        raise PositiveControlGateError(
            "no-wall structural audit failed; cannot run the positive-control "
            f"ridge on invalid control data: {structural_audit.detail}"
        )

    n_rows = len(contexts)

    if data_provenance != REAL_NO_WALL_DATA_PROVENANCE:
        return PositiveControlGateFinding(
            status="BLOCKED",
            r2=None,
            ci_low=None,
            ci_high=None,
            n_rows=n_rows,
            fold_count=None,
            resample_count=None,
            seed=None,
            r2_threshold=r2_threshold,
            data_provenance=data_provenance,
            detail=(
                "Gate inputs are not declared as Person C's real accepted "
                f"no-wall capture data (data_provenance={data_provenance!r} "
                f"!= {REAL_NO_WALL_DATA_PROVENANCE!r}). Real no-wall rows, a "
                "real B fold manifest, and real oracle targets do not exist "
                "yet in this repository, so this reports BLOCKED rather than "
                "computing a scientific R^2 no one has grounds to trust."
            ),
        )

    try:
        annotated = attach_b_fold_assignments(contexts, fold_manifest=fold_manifest)
    except BaselineExportError as error:
        raise PositiveControlGateError(
            f"could not attach Person B's real fold manifest: {error}"
        ) from error

    missing_targets = [
        (ctx.trajectory_id, ctx.model_frame_idx)
        for ctx in annotated
        if (ctx.trajectory_id, ctx.model_frame_idx) not in mu_oracle_by_key
    ]
    if missing_targets:
        raise PositiveControlGateError(
            f"missing real oracle mu target for {len(missing_targets)} row(s), "
            f"e.g. {missing_targets[0]}"
        )
    missing_positions = [
        (ctx.trajectory_id, ctx.model_frame_idx)
        for ctx in annotated
        if ctx.last_seen_position_blocks is None
    ]
    if missing_positions:
        raise PositiveControlGateError(
            f"missing visible position for {len(missing_positions)} row(s) in "
            "a trajectory the structural audit already certified as always-"
            f"visible, e.g. {missing_positions[0]}"
        )

    features = [[ctx.last_seen_position_blocks] for ctx in annotated]
    targets = [
        mu_oracle_by_key[(ctx.trajectory_id, ctx.model_frame_idx)] for ctx in annotated
    ]
    outer_folds = [ctx.fold for ctx in annotated]
    layout_ids = [ctx.layout_id for ctx in annotated]

    analysis_config = load_core_analysis_config()
    alpha_grid = tuple(analysis_config["ridge"]["alpha_grid"])
    inner_fold_count = analysis_config["cross_validation"]["inner_fold_count"]
    split_seed = analysis_config["cross_validation"]["split_seed"]
    resampling_config = analysis_config["resampling"]
    resample_count = resampling_config["bootstrap_count_mvp"]
    bootstrap_seed = resampling_config["bootstrap_seed"]

    try:
        oof = fit_ridge_oof(
            features,
            targets,
            outer_folds,
            layout_ids,
            alpha_grid=alpha_grid,
            inner_fold_count=inner_fold_count,
            seed=split_seed,
        )
    except ProbeFitError as error:
        raise PositiveControlGateError(f"ridge fit failed: {error}") from error

    try:
        overall = regression_metrics(targets, oof.predictions)
    except U1MetricError as error:
        raise PositiveControlGateError(f"R^2 is undefined: {error}") from error

    bootstrap_rows = [
        {"layout_id": ctx.layout_id, "trajectory_id": ctx.trajectory_id}
        for ctx in annotated
    ]
    try:
        index_sets = hierarchical_bootstrap_indices(
            bootstrap_rows, resample_count=resample_count, seed=bootstrap_seed
        )
    except ResamplingError as error:
        raise PositiveControlGateError(
            f"bootstrap resampling failed: {error}"
        ) from error

    bootstrap_r2s: list[float] = []
    for indices in index_sets:
        resampled_truth = [targets[index] for index in indices]
        resampled_prediction = [oof.predictions[index] for index in indices]
        try:
            bootstrap_r2s.append(
                regression_metrics(resampled_truth, resampled_prediction).r2
            )
        except U1MetricError as error:
            raise PositiveControlGateError(
                f"a bootstrap resample produced an undefined R^2: {error}"
            ) from error

    ci_low, ci_high = bootstrap_confidence_interval(
        bootstrap_r2s, coverage=BOOTSTRAP_COVERAGE
    )

    passed = overall.r2 >= r2_threshold and ci_low > 0.0
    status = "PASSED" if passed else "FAILED"
    detail = (
        f"held-out R^2={overall.r2:.4f} (threshold {r2_threshold}), "
        f"{int(BOOTSTRAP_COVERAGE * 100)}% bootstrap CI=[{ci_low:.4f}, "
        f"{ci_high:.4f}] over {resample_count} resamples -- "
        f"{'meets' if passed else 'fails'} the Step 4.3 pass condition "
        "(R^2 >= 0.50 and CI strictly above zero)."
    )

    return PositiveControlGateFinding(
        status=status,
        r2=overall.r2,
        ci_low=ci_low,
        ci_high=ci_high,
        n_rows=n_rows,
        fold_count=len(set(outer_folds)),
        resample_count=resample_count,
        seed=bootstrap_seed,
        r2_threshold=r2_threshold,
        data_provenance=data_provenance,
        detail=detail,
    )
