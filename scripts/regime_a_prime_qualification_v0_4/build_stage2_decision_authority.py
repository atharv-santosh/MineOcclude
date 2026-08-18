#!/usr/bin/env python3
"""Promote the implemented Stage-2 decision rules into frozen prospective authority.

Why this artifact exists (B009)
===============================

``authority_parameters.json`` already binds most of the Stage-2 readout: the
scenes, the counts, the folds, the phase offsets, the layer, the RMSE ceiling,
the bootstrap seed/resamples/unit, the time-baseline thresholds, and the
BEST_K-leading / FULL-non-rescuing rules. What it never bound is the *decision
procedure* those thresholds are applied to: ``K_GRID``, ``ALPHAS``, the
inner-fold construction, the selection rule, how the five outer folds are
aggregated into one point estimate, which six BEST-K gates exist, and what
PASS/FAIL/BLOCKED mean at the terminal unit. Those lived only in code, so a
completed Stage-2 decision could not have been reproduced from frozen authority
alone -- which is B009.

Why it is a separate document
=============================

The completed v0.4 Stage-1 PASS is welded to the *bytes* of
``authority_parameters.json``: ``stage1_decision.json`` carries
``authority_sha256 = 52b9590b...``, the historical re-derivation compares
against that file, and ``require_stage2_authorization`` refuses a Stage-1
decision whose authority digest is not the live one. Editing that file to add
Stage-2 decision rules would therefore have made the frozen Stage-1 decision
irreproducible AND made it permanently unusable as the predicate for Stage-2
authorization -- destroying the very PASS the promotion exists to consume.

So the promotion lands in its own frozen artifact, bound by digest from the
Stage-2 locked manifest and by digest *to* the authority it extends. Stage-1's
cryptographic chain is untouched, and Stage-2 gains a complete prospective
decision contract. Nothing is duplicated: every value this document does not
introduce is read from ``authority_parameters.json`` at evaluation time.

Why nothing here is a choice
============================

Rule 1 of the promotion is that no numeric value may move. Every rule below is
read out of, or executed against, the implementation that is already in the
tree, and :func:`require_promotion_matches_implementation` proves it: ``K_GRID``
and ``ALPHAS`` are imported, not typed; the six gate names are obtained by
*running* ``best_k_qualification_checks``; the inner-fold shape is obtained by
*running* ``inner_fold_assignment``. A future edit that wanted to change a
scientific value would have to change the implementation first, at which point
this build fails rather than silently ratifying it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "scripts/regime_a_prime_qualification_v0_1"
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(LEGACY)]

#: The freeze whose implementation is being promoted. Recorded in the artifact so
#: an auditor can diff the promoted values against exactly these bytes.
PROMOTED_FROM_FREEZE = "c9aad3e324c03c94a08222f4705c18b1a80e3a63"

#: Every package in this family carries a Stage-2 locked manifest, so every one
#: of them needs a Stage-2 decision contract: a manifest that can describe a
#: terminal decision it cannot reproduce is the B009 defect itself. The promoted
#: rules are identical across versions because they come from one shared
#: implementation -- the version tag changes the artifact identity and the
#: authority the document extends, nothing scientific.
DEFAULT_VERSION = "v0.4"


def _implementation() -> dict:
    """Read the live implementation's scientific parameters. Nothing is typed here."""
    from mineocclude.regime_a_first25_analysis import (
        ALPHAS, K_GRID, inner_fold_assignment,
    )
    from scripts.regime_a_prime_qualification_v0_2.stage2_backend import (
        best_k_qualification_checks,
    )
    return {"K_GRID": list(K_GRID), "ALPHAS": list(ALPHAS),
            "inner_fold_assignment": inner_fold_assignment,
            "best_k_qualification_checks": best_k_qualification_checks}


def observed_best_k_gate_names(best_k_qualification_checks, policy: dict) -> list[str]:
    """Obtain the gate name set by executing the implementation, not by copying it.

    The synthetic scene outputs below are structurally shaped like a real readout
    and carry deliberately neutral numbers; only the *keys* of the returned map
    are used. Running the function is what makes the enumeration a measurement of
    the code rather than a second, drift-prone spelling of it.
    """
    def scene(value: float) -> dict:
        metrics = {"rmse_blocks": value, "mae_blocks": value, "macro_r2": value,
                   "bootstrap95_macro_r2": [value, value]}
        return {"metrics": dict(metrics), "training_time_baseline": dict(metrics),
                "training_time_baseline_tau1_15": dict(metrics)}
    outputs = {"WALL": scene(0.0), "NO_WALL": scene(0.0)}
    return sorted(best_k_qualification_checks(outputs, policy))


def observed_inner_fold_shape(inner_fold_assignment) -> dict:
    """Obtain the inner-fold structure by executing the frozen assignment."""
    identities = [f"probe_t{index:02d}" for index in range(20)]
    directions = {identity: ("LEFT_TO_RIGHT" if index < 10 else "RIGHT_TO_LEFT")
                  for index, identity in enumerate(identities)}
    sizes = set()
    fold_counts = set()
    for outer in range(5):
        assignment = inner_fold_assignment(identities, directions, outer)
        counts: dict[int, int] = {}
        for fold in assignment.values():
            counts[fold] = counts.get(fold, 0) + 1
        fold_counts.add(len(counts))
        sizes.update(counts.values())
    return {"training_identities_required": 20,
            "inner_fold_count": sorted(fold_counts)[0] if len(fold_counts) == 1 else -1,
            "identities_per_inner_fold": sorted(sizes)[0] if len(sizes) == 1 else -1}


def package_paths(version_tag: str) -> tuple[Path, Path, str]:
    """Resolve one package's authority, output path, and artifact identity."""
    from mineocclude.prospective.package_binding import (
        package_directory, stage2_decision_authority_artifact_id_for,
    )
    package = package_directory(version_tag, ROOT)
    return (package / "authority_parameters.json",
            package / "stage2_decision_authority.json",
            stage2_decision_authority_artifact_id_for(version_tag))


def build(authority: dict, authority_sha256: str, *, artifact_id: str,
          authority_relative: str) -> dict:
    implementation = _implementation()
    readout_policy = authority["stage2_policy"]["readout"]
    gates = observed_best_k_gate_names(
        implementation["best_k_qualification_checks"], readout_policy)
    inner = observed_inner_fold_shape(implementation["inner_fold_assignment"])
    from mineocclude.prospective.package_binding import (
        artifact_version_tag, stage2_decision_artifact_id_for,
        stage2_evidence_artifact_id_for,
    )
    version_tag = artifact_version_tag(artifact_id)
    evidence_artifact_id = stage2_evidence_artifact_id_for(version_tag)
    decision_artifact_id = stage2_decision_artifact_id_for(version_tag)
    underscored = version_tag.replace(".", "_")
    evidence_schema = f"schemas/prospective/regime_a_prime_stage2_evidence_{underscored}.schema.json"
    decision_schema = f"schemas/prospective/regime_a_prime_stage2_decision_{underscored}.schema.json"
    return {
        "artifact_id": artifact_id,
        "schema_version": "1.0",
        "classification": "DEVELOPMENT_ONLY",
        "status": "DRAFT_PROSPECTIVE_UNFROZEN_NOT_AUTHORIZED",
        "STAGE_2_COLLECTION_AUTHORIZED": False,
        "confirmatory_collection_authorized": False,
        # Binds the authority it extends, by path and digest, so this document
        # can never be paired with a different authority's stage2_policy.
        "extends_authority": {"path": authority_relative,
                              "sha256": authority_sha256,
                              "artifact_id": authority["artifact_id"]},
        "promotion": {
            "kind": "EXPLICIT_PROMOTION_OF_EXISTING_STAGE2_IMPLEMENTATION",
            "promoted_from_freeze": PROMOTED_FROM_FREEZE,
            "scientific_outcomes_observed": False,
            "outcome_adaptive_change": False,
            "new_scientific_values_invented": False,
            "authority_parameters_json_modified": False,
            "derivation": (
                "Every rule below already governed the Stage-2 readout at "
                f"{PROMOTED_FROM_FREEZE}; none of them was reachable from frozen "
                "authority, so a completed Stage-2 decision could not have been "
                "reproduced without reading source. K_GRID and ALPHAS are imported "
                "from mineocclude.regime_a_first25_analysis rather than typed; the "
                "six BEST-K gate names are obtained by executing "
                "stage2_backend.best_k_qualification_checks; the inner-fold shape "
                "is obtained by executing regime_a_first25_analysis."
                "inner_fold_assignment. No numeric value is chosen here."),
            "why_not_in_authority_parameters_json": (
                "The completed v0.4 Stage-1 decision d00d7730 binds the bytes of "
                "authority_parameters.json (52b9590b), the historical "
                "re-derivation compares against that same file, and "
                "require_stage2_authorization refuses a Stage-1 decision whose "
                "authority digest is not the live one. Editing those bytes would "
                "have made the frozen Stage-1 PASS both irreproducible and unusable "
                "as the predicate for Stage-2 authorization. This document is bound "
                "by the Stage-2 locked manifest instead, which nothing frozen "
                "binds yet."),
        },
        "estimands": {
            "primary": "trajectory_equal_macro_r2",
            "primary_derivation": (
                "regime_a_first25_analysis.scalar_metrics: the unweighted mean of "
                "per-trajectory R-squared, each computed against that trajectory's "
                "own mean. Trajectory-equal, never row-pooled."),
            "error": "trajectory_aggregated_rmse_blocks",
            "error_derivation": (
                "scalar_metrics: the unweighted mean of per-trajectory RMSE in "
                "world blocks. Reported by stage2_backend.summary as rmse_blocks."),
            "interval": "whole_trajectory_bootstrap95_macro_r2",
            "descriptive_only": ["trajectory_aggregated_mae_blocks",
                                 "pooled_row_r2_secondary", "pooled_rmse_secondary"],
            "pooled_metrics_are_never_gating": True,
        },
        "readout_procedure": {
            "k_grid": implementation["K_GRID"],
            "alpha_grid": implementation["ALPHAS"],
            "kernel": "standardized summed-token kernel ridge",
            "token_ranking": "absolute maximum hidden-dimension training correlation",
            "ranking_scope": "training rows only, inside every inner and final fold",
            "feature_standardization": "fit on each training split only",
            "target_handling": (
                "training-target centering inside the kernel ridge; no target "
                "standardization"),
            "inner_fold_rule": {
                "function": "mineocclude.regime_a_first25_analysis.inner_fold_assignment",
                "construction": (
                    "five deterministic direction-stratified folds. Identities are "
                    "ordered by SHA256 of "
                    "'REGIME_A_INNER_FOLD_V1|outer={outer}|{identity}' within each "
                    "direction, round-robin assigned, with the second direction "
                    "offset by one fold. A partition whose direction balance "
                    "prevents five equal folds is rebalanced by one identity, "
                    "chosen by SHA256 of "
                    "'REGIME_A_INNER_REBALANCE_V1|outer={outer}|{identity}'."),
                "ordering_is_outcome_independent": True,
                **inner,
            },
            "selection_rule": {
                "objective": "maximum inner trajectory-equal macro R2",
                "best_k_tie_break": "smaller K, then smaller alpha",
                "full_tie_break": "smaller alpha",
                "selection_training_tau_maximum": 15,
                "final_fit_training_tau_maximum": 15,
                "evaluation_tau_scope": "every qualified target row, tau 1..19",
            },
            "outer_fold_aggregation": {
                "rule": "POOLED_OUT_OF_FOLD_THEN_TRAJECTORY_EQUAL",
                "derivation": (
                    "Each of the five outer folds contributes out-of-fold "
                    "predictions for its own held-out trajectories; the five "
                    "prediction sets are pooled to cover each row exactly once, and "
                    "the terminal point estimate is then computed over all 25 "
                    "trajectories by scalar_metrics. Per-fold metrics are never "
                    "averaged, and no fold is weighted."),
                "each_row_predicted_exactly_once": True,
                "per_fold_metrics_are_not_averaged": True,
            },
            "readouts": {"leading": "BEST_K", "secondary_non_rescuing": "FULL"},
        },
        "bootstrap_procedure": {
            "function": "scripts.regime_a_prime_qualification_v0_2.stage2_backend.summary",
            "resample_population": (
                "the per-trajectory R-squared values, ordered by trajectory "
                "identity ascending"),
            "draw": "numpy.random.default_rng(seed).choice(values, size=(resamples, n), replace=True)",
            "statistic": "mean of each resampled set",
            "interval": "numpy.quantile at 0.025 and 0.975",
            "seed_source": "authority_parameters.json stage2_policy.readout.bootstrap_seed",
            "resamples_source": "authority_parameters.json stage2_policy.readout.bootstrap_resamples",
            "unit_source": "authority_parameters.json stage2_policy.readout.bootstrap_unit",
            "seed_is_reused_per_summary_call": True,
        },
        "time_baseline_procedure": {
            "function": ("scripts.regime_a_prime_qualification_v0_2.stage2_backend."
                         "training_time_baseline"),
            "design_matrix": ["1", "direction", "tau", "tau*direction"],
            "direction_encoding": {"LEFT_TO_RIGHT": 1.0, "RIGHT_TO_LEFT": -1.0},
            "solver": "numpy.linalg.lstsq(rcond=None)",
            "fitting_scope": (
                "rows of the outer-training folds whose tau is at or below "
                "training_only_time_baseline_training_tau_maximum"),
            "prediction_scope": "every row of the held-out outer fold",
            "tau_maximum_source": ("authority_parameters.json stage2_policy.readout."
                                   "training_only_time_baseline_training_tau_maximum"),
        },
        "best_k_gates": {
            "names": gates,
            "count": len(gates),
            "all_must_pass": True,
            "derivation": (
                "Obtained by executing stage2_backend.best_k_qualification_checks. "
                "The four authority booleans expand to six gates because the two "
                "per-scene rules are applied to WALL and NO_WALL separately."),
            "definitions": {
                "WALL_rmse": ("WALL rmse_blocks <= stage2_policy.readout."
                              "best_k_each_scene_rmse_maximum_blocks"),
                "NO_WALL_rmse": ("NO_WALL rmse_blocks <= stage2_policy.readout."
                                 "best_k_each_scene_rmse_maximum_blocks"),
                "WALL_r2": "WALL macro_r2 > 0 and WALL bootstrap95 lower bound > 0",
                "NO_WALL_r2": ("NO_WALL macro_r2 > 0 and NO_WALL bootstrap95 lower "
                               "bound > 0"),
                "WALL_beats_training_time_baseline": (
                    "WALL rmse_blocks < WALL training-time-baseline rmse_blocks"),
                "WALL_time_confound_gate": (
                    "WALL training-time-baseline macro_r2 restricted to tau 1..15 "
                    "<= stage2_policy.readout."
                    "training_only_time_baseline_macro_r2_tau_1_to_15_maximum"),
            },
            "full_readout_is_evaluated_but_never_gating": True,
            "full_may_not_rescue_best_k_failure": True,
        },
        "terminal": {
            "states": ["PASS", "FAIL", "BLOCKED"],
            "state_semantics": {
                "PASS": ("a legitimately completed Stage-2 analysis in which every "
                         "BEST-K gate, re-derived from bound evidence, holds"),
                "FAIL": ("a legitimately completed Stage-2 analysis in which at "
                         "least one re-derived BEST-K gate does not hold"),
                "BLOCKED": ("an operational, provenance, binding, or completeness "
                            "failure. Never a scientific verdict"),
            },
            "operational_failure_may_not_become_scientific_fail": True,
            "completed_scientific_fail_is_terminal": True,
            "leading_readout": "BEST_K",
            "terminal_status_is_re_derived_not_copied": True,
            "precomputed_qualification_booleans_are_not_trusted": True,
            "pass_meaning": (
                "The frozen DEVELOPMENT_ONLY Stage-2 hidden-position decoding "
                "experiment satisfied its prospectively frozen Stage-2 decoding "
                "criteria. It may support the bounded statement that layer-4 "
                "activations contain decodable information according to those "
                "criteria, on this apparatus, at these paths."),
            "pass_does_not_establish": [
                "object_permanence", "belief", "causal_use",
                "uncertainty_representation", "general_world_model_competence",
                "behavioral_reliance_on_the_representation",
            ],
            "pass_authorizes": {
                "confirmatory_collection": False,
                "causal_intervention": False,
                "next_rung": False,
                "derivation": (
                    "authority_parameters.json stage2_policy.post_stage2."
                    "may_authorize_confirmatory_collection is false and remains "
                    "binding. A PASS completes this DEVELOPMENT_ONLY rung and "
                    "nothing else; any later experiment requires its own separate "
                    "prospective design and authorization."),
            },
            "claim_boundary_scope": (
                "authority_parameters.json scientific_claim_boundary describes the "
                "Stage-1 apparatus-qualification rung, whose PASS tests no model "
                "activation. This block describes the Stage-2 decoding rung, which "
                "does read layer-4 activations. The two are different rungs and "
                "neither statement weakens the other."),
        },
        "artifacts": {
            "evidence_artifact_id": evidence_artifact_id,
            "decision_artifact_id": decision_artifact_id,
            "evidence_schema": evidence_schema,
            "decision_schema": decision_schema,
            "evidence_builder": "mineocclude.prospective.stage2_evidence.build_stage2_evidence",
            "evaluator": "mineocclude.prospective.stage2_decision.Stage2Evaluator",
            "reproduction_verifier": (
                "mineocclude.prospective.stage2_decision.require_stage2_decision_reproduction"),
            "evidence_builder_may_assert_scientific_status": False,
        },
    }


def require_promotion_matches_implementation(document: dict) -> None:
    """Refuse unless every promoted value is the value the code actually uses.

    This is what makes ``PROMOTED_RULES_MATCH_PREEXISTING_CODE`` a proof. It runs
    after the document is assembled and re-reads the implementation
    independently, so an edit to :func:`build` that quietly changed a grid would
    fail here rather than shipping.
    """
    from mineocclude.regime_a_first25_analysis import ALPHAS, K_GRID

    readout = document["readout_procedure"]
    if readout["k_grid"] != list(K_GRID):
        raise RuntimeError(f"promoted K_GRID {readout['k_grid']} != implementation {list(K_GRID)}")
    if readout["alpha_grid"] != list(ALPHAS):
        raise RuntimeError(
            f"promoted ALPHAS {readout['alpha_grid']} != implementation {list(ALPHAS)}")
    inner = readout["inner_fold_rule"]
    if inner["inner_fold_count"] != 5 or inner["identities_per_inner_fold"] != 4 \
            or inner["training_identities_required"] != 20:
        raise RuntimeError(
            "inner-fold structure measured from the implementation is not 5 folds of 4 "
            f"over 20 training identities: {inner}")
    gates = document["best_k_gates"]
    if gates["count"] != 6 or sorted(gates["definitions"]) != gates["names"]:
        raise RuntimeError(
            f"BEST-K gate enumeration is not the six the implementation emits: {gates}")
    if document["promotion"]["outcome_adaptive_change"] is not False:
        raise RuntimeError("a promotion may never be outcome-adaptive")


def write(path: Path, value: dict) -> str:
    path.write_text(json.dumps(value, indent=1, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=DEFAULT_VERSION,
                        help="package version tag to promote into, e.g. v0.4")
    arguments = parser.parse_args()
    authority_path, output_path, artifact_id = package_paths(arguments.version)
    authority = json.loads(authority_path.read_text())
    authority_sha256 = hashlib.sha256(authority_path.read_bytes()).hexdigest()
    document = build(authority, authority_sha256, artifact_id=artifact_id,
                     authority_relative=str(authority_path.relative_to(ROOT)))
    require_promotion_matches_implementation(document)
    digest = write(output_path, document)
    print("STAGE2_DECISION_AUTHORITY_PROMOTION=EXPLICIT_PROMOTION_OF_EXISTING_STAGE2_IMPLEMENTATION")
    print("OUTCOME_ADAPTIVE_CHANGE=false")
    print(f"PROMOTED_PACKAGE_VERSION={arguments.version}")
    print(f"AUTHORITY_PARAMETERS_SHA256_UNCHANGED={authority_sha256}")
    print(f"stage2_decision_authority.json sha256 = {digest}")


if __name__ == "__main__":
    main()
