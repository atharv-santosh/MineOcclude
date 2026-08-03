"""C-only real-capture oracle audit without Person A-bound target rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .closed_form import closed_form_posterior
from .primary_scalar_kalman import scalar_kalman_posterior
from .schema import REGIME_A_DT_SECONDS


class CaptureOracleAuditError(ValueError):
    """Raised when C's real visibility/timing cannot support an oracle audit."""


def _capture_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row["episode_id"],
        row["trajectory_id"],
        row["server_tick"],
        row["render_frame_idx"],
        row["action_idx"],
        row["model_frame_idx"],
    )


def audit_capture_package_oracle_math(
    package: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare both oracles and invariants using only legal visible history."""

    states = {
        _capture_key(row): row["state"]
        for row in package["streams"]["server_state"]
    }
    ordered_visibility = sorted(
        package["streams"]["visibility"],
        key=lambda row: row["server_tick"],
    )
    if all(not state["target_present"] for state in states.values()):
        return {
            "status": "not_applicable_no_object",
            "row_count": len(ordered_visibility),
            "visible_row_count": 0,
            "hidden_row_count": 0,
            "reveal_count": 0,
            "log_sigma_valid_count": 0,
            "log_sigma_not_applicable_count": 0,
            "max_iterative_closed_mean_error": 0.0,
            "max_iterative_closed_variance_error": 0.0,
            "invariant_failures": [],
        }

    v = float(package["episode_manifest"]["v"])
    q = float(package["episode_manifest"]["q"])
    last_visible_position: float | None = None
    last_visible_tick: int | None = None
    previous_visibility: str | None = None
    previous_hidden_variance: float | None = None
    max_mean_error = 0.0
    max_variance_error = 0.0
    visible_count = 0
    hidden_count = 0
    reveal_count = 0
    log_valid_count = 0
    log_not_applicable_count = 0
    failures: list[dict[str, Any]] = []
    hidden_variances_by_tau: list[dict[str, float]] = []

    for visibility_row in ordered_visibility:
        key = _capture_key(visibility_row)
        state = states[key]
        visibility = visibility_row["visibility"]
        server_tick = visibility_row["server_tick"]
        if visibility == "visible":
            last_visible_position = float(
                state["wall_parallel_position_blocks"]
            )
            last_visible_tick = server_tick
            hidden_ticks = 0
            visible_count += 1
            log_not_applicable_count += 1
        else:
            if last_visible_position is None or last_visible_tick is None:
                raise CaptureOracleAuditError(
                    f"{package['trajectory_id']}: hidden row precedes visibility."
                )
            hidden_ticks = server_tick - last_visible_tick
            if hidden_ticks <= 0:
                raise CaptureOracleAuditError(
                    f"{package['trajectory_id']}: hidden tick mapping is invalid."
                )
            hidden_count += 1
            log_valid_count += 1

        tau = hidden_ticks * REGIME_A_DT_SECONDS
        iterative = scalar_kalman_posterior(
            last_visible_position,
            v,
            q,
            hidden_ticks,
        )
        closed = closed_form_posterior(
            last_visible_position,
            v,
            q,
            tau,
        )
        max_mean_error = max(
            max_mean_error,
            abs(iterative.mean_blocks - closed.mean_blocks),
        )
        max_variance_error = max(
            max_variance_error,
            abs(iterative.variance_blocks2 - closed.variance_blocks2),
        )

        if visibility == "visible":
            if iterative.variance_blocks2 != 0.0:
                failures.append(
                    {
                        "model_frame_idx": visibility_row["model_frame_idx"],
                        "invariant": "visible_variance_resets_to_zero",
                    }
                )
            if previous_visibility == "occluded":
                reveal_count += 1
                if (
                    previous_hidden_variance is not None
                    and iterative.variance_blocks2 >= previous_hidden_variance
                ):
                    failures.append(
                        {
                            "model_frame_idx": visibility_row[
                                "model_frame_idx"
                            ],
                            "invariant": "reveal_reduces_uncertainty",
                        }
                    )
            previous_hidden_variance = None
        else:
            if q > 0.0 and iterative.variance_blocks2 <= 0.0:
                failures.append(
                    {
                        "model_frame_idx": visibility_row["model_frame_idx"],
                        "invariant": "hidden_variance_positive",
                    }
                )
            if (
                previous_visibility == "occluded"
                and previous_hidden_variance is not None
                and iterative.variance_blocks2 < previous_hidden_variance
            ):
                failures.append(
                    {
                        "model_frame_idx": visibility_row["model_frame_idx"],
                        "invariant": "hidden_variance_never_decreases",
                    }
                )
            previous_hidden_variance = iterative.variance_blocks2
            hidden_variances_by_tau.append(
                {
                    "tau": tau,
                    "q": q,
                    "variance": iterative.variance_blocks2,
                }
            )
        previous_visibility = visibility

    status = (
        "pass"
        if max(max_mean_error, max_variance_error) <= 1e-6 and not failures
        else "fail"
    )
    return {
        "status": status,
        "row_count": len(ordered_visibility),
        "visible_row_count": visible_count,
        "hidden_row_count": hidden_count,
        "reveal_count": reveal_count,
        "log_sigma_valid_count": log_valid_count,
        "log_sigma_not_applicable_count": log_not_applicable_count,
        "max_iterative_closed_mean_error": max_mean_error,
        "max_iterative_closed_variance_error": max_variance_error,
        "invariant_failures": failures,
        "_hidden_variances_by_tau": hidden_variances_by_tau,
    }

def audit_fixed_tau_q_sensitivity(
    package_audits: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Require larger q to imply larger variance at every shared hidden time."""

    by_tau: dict[float, dict[float, float]] = {}
    for audit in package_audits:
        for row in audit.get("_hidden_variances_by_tau", []):
            by_tau.setdefault(float(row["tau"]), {})[
                float(row["q"])
            ] = float(row["variance"])

    comparisons = 0
    failures: list[dict[str, float]] = []
    for tau, variances_by_q in sorted(by_tau.items()):
        ordered = sorted(variances_by_q.items())
        for (lower_q, lower_variance), (
            higher_q,
            higher_variance,
        ) in zip(ordered, ordered[1:]):
            comparisons += 1
            if higher_variance <= lower_variance:
                failures.append(
                    {
                        "tau": tau,
                        "lower_q": lower_q,
                        "higher_q": higher_q,
                    }
                )
    return {
        "comparison_count": comparisons,
        "failure_count": len(failures),
        "failures": failures,
    }
