"""Independent real-target audit evidence for roadmap Step 6.2."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mineocclude.analysis.config import hash_core_analysis_config
from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    seal_artifact,
    sha256_value,
    validate_sealed_artifact,
)

from .closed_form import closed_form_posterior
from .primary_scalar_kalman import scalar_kalman_posterior
from .schema import REGIME_A_DT_SECONDS, validate_oracle_target_document


ORACLE_AUDIT_SCHEMA_VERSION = "person-b-regime-a-oracle-audit-v0.1"


class OracleAuditError(ValueError):
    """Raised when audited targets disagree with the frozen oracle."""


def derive_oracle_code_sha() -> str:
    """Hash the literal oracle implementation and validation code."""

    digest = hashlib.sha1()
    directory = Path(__file__).resolve().parent
    for filename in (
        "audit.py",
        "closed_form.py",
        "primary_scalar_kalman.py",
        "schema.py",
        "targets.py",
    ):
        payload = (directory / filename).read_bytes()
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def build_oracle_audit(
    target_document: Mapping[str, Any],
    *,
    artifact_id: str,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    """Recompute both oracles and persist real-event invariants/counts."""

    validate_oracle_target_document(target_document)
    if "artifact_hash" in target_document:
        try:
            validate_sealed_artifact(
                target_document,
                expected_type="oracle_target_document",
            )
        except AnalysisArtifactError as error:
            raise OracleAuditError(
                f"Target artifact seal is invalid: {error}"
            ) from error
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(float(tolerance))
        or tolerance <= 0.0
    ):
        raise OracleAuditError("tolerance must be finite and positive.")

    max_iterative_closed_mean_error = 0.0
    max_iterative_closed_variance_error = 0.0
    max_declared_mean_error = 0.0
    max_declared_variance_error = 0.0
    invariant_failures: list[dict[str, Any]] = []
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in target_document["rows"]:
        grouped[row["trajectory_id"]].append(row)
        hidden_ticks_float = float(row["tau"]) / REGIME_A_DT_SECONDS
        hidden_ticks = round(hidden_ticks_float)
        if not math.isclose(
            hidden_ticks_float,
            hidden_ticks,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise OracleAuditError("tau is not an integer number of 20 Hz ticks.")
        iterative = scalar_kalman_posterior(
            row["last_visible_position_blocks"],
            row["v"],
            row["q"],
            hidden_ticks,
        )
        closed = closed_form_posterior(
            row["last_visible_position_blocks"],
            row["v"],
            row["q"],
            row["tau"],
        )
        max_iterative_closed_mean_error = max(
            max_iterative_closed_mean_error,
            abs(iterative.mean_blocks - closed.mean_blocks),
        )
        max_iterative_closed_variance_error = max(
            max_iterative_closed_variance_error,
            abs(iterative.variance_blocks2 - closed.variance_blocks2),
        )
        max_declared_mean_error = max(
            max_declared_mean_error,
            abs(iterative.mean_blocks - float(row["mu_oracle_blocks"])),
        )
        max_declared_variance_error = max(
            max_declared_variance_error,
            abs(iterative.variance_blocks2 - float(row["var_oracle_blocks2"])),
        )
        if row["visibility"] == "visible" and row["var_oracle_blocks2"] != 0.0:
            invariant_failures.append(
                {
                    "trajectory_id": row["trajectory_id"],
                    "model_frame_idx": row["model_frame_idx"],
                    "invariant": "visible_variance_resets_to_zero",
                }
            )
        if (
            row["visibility"] == "occluded"
            and row["q"] > 0.0
            and row["tau"] > 0.0
            and row["var_oracle_blocks2"] <= 0.0
        ):
            invariant_failures.append(
                {
                    "trajectory_id": row["trajectory_id"],
                    "model_frame_idx": row["model_frame_idx"],
                    "invariant": "hidden_variance_positive",
                }
            )

    reveal_count = 0
    hidden_row_count = 0
    visible_row_count = 0
    hidden_growth_comparison_count = 0
    for trajectory_id, rows in grouped.items():
        previous: Mapping[str, Any] | None = None
        for row in sorted(rows, key=lambda item: item["model_frame_idx"]):
            if row["visibility"] == "occluded":
                hidden_row_count += 1
                if (
                    previous is not None
                    and previous["visibility"] == "occluded"
                ):
                    hidden_growth_comparison_count += 1
                    if (
                        row["var_oracle_blocks2"]
                        < previous["var_oracle_blocks2"]
                    ):
                        invariant_failures.append(
                            {
                                "trajectory_id": trajectory_id,
                                "model_frame_idx": row["model_frame_idx"],
                                "invariant": "hidden_variance_never_decreases",
                            }
                        )
            else:
                visible_row_count += 1
                if previous is not None and previous["visibility"] == "occluded":
                    reveal_count += 1
                    if not (
                        row["var_oracle_blocks2"]
                        < previous["var_oracle_blocks2"]
                    ):
                        invariant_failures.append(
                            {
                                "trajectory_id": trajectory_id,
                                "model_frame_idx": row["model_frame_idx"],
                                "invariant": "reveal_reduces_uncertainty",
                            }
                        )
            previous = row

    hidden_by_tau: dict[float, list[Mapping[str, Any]]] = defaultdict(list)
    for row in target_document["rows"]:
        if row["visibility"] == "occluded" and row["tau"] > 0.0:
            hidden_by_tau[float(row["tau"])].append(row)
    q_sensitivity_comparison_count = 0
    for tau, rows in hidden_by_tau.items():
        ordered = sorted(rows, key=lambda item: float(item["q"]))
        for lower, higher in zip(ordered, ordered[1:]):
            if higher["q"] <= lower["q"]:
                continue
            q_sensitivity_comparison_count += 1
            if higher["var_oracle_blocks2"] <= lower["var_oracle_blocks2"]:
                invariant_failures.append(
                    {
                        "trajectory_id": higher["trajectory_id"],
                        "model_frame_idx": higher["model_frame_idx"],
                        "invariant": "larger_q_gives_larger_fixed_tau_variance",
                        "tau": tau,
                    }
                )

    max_error = max(
        max_iterative_closed_mean_error,
        max_iterative_closed_variance_error,
        max_declared_mean_error,
        max_declared_variance_error,
    )
    status = "pass" if max_error <= tolerance and not invariant_failures else "fail"
    document_hash = target_document.get("artifact_hash") or sha256_value(
        target_document
    )
    return seal_artifact(
        {
            "artifact_type": "oracle_audit",
            "artifact_id": artifact_id,
            "code_sha": derive_oracle_code_sha(),
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": document_hash,
            "oracle_audit_schema_version": ORACLE_AUDIT_SCHEMA_VERSION,
            "target_document_hash": document_hash,
            "tolerance": float(tolerance),
            "row_count": len(target_document["rows"]),
            "trajectory_count": len(grouped),
            "visible_row_count": visible_row_count,
            "hidden_row_count": hidden_row_count,
            "reveal_count": reveal_count,
            "hidden_growth_comparison_count": hidden_growth_comparison_count,
            "q_sensitivity_comparison_count": q_sensitivity_comparison_count,
            "max_iterative_closed_mean_error": max_iterative_closed_mean_error,
            "max_iterative_closed_variance_error": (
                max_iterative_closed_variance_error
            ),
            "max_declared_mean_error": max_declared_mean_error,
            "max_declared_variance_error": max_declared_variance_error,
            "invariant_failures": invariant_failures,
            "status": status,
            "synthetic": target_document.get("fixture_metadata") is not None,
            "scientific_use": (
                "forbidden"
                if target_document.get("fixture_metadata") is not None
                else "permitted"
            ),
        }
    )
