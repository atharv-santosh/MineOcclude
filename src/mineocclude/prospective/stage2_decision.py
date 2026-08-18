#!/usr/bin/env python3
"""Independent Stage-2 evaluation and the terminal decision artifact (B009).

The Stage-1 architecture separates three things, and Stage-2 now matches it:

* the *builder* assembles measured facts (:mod:`.stage2_evidence`);
* the *evaluator* below applies frozen authority rules to those facts and
  reaches PASS, FAIL, or BLOCKED;
* the *decision* is a versioned artifact that re-derives byte-identically from
  its bound evidence plus the frozen authority, which
  :func:`require_stage2_decision_reproduction` proves.

Before this module, ``stage2_backend.terminal`` copied the BEST-K readout's own
``qualification_status`` field into a receipt. That is not an evaluation: the
readout that computed the number also graded it, no independent component ever
re-derived a gate, and an edited boolean would have carried a scientific verdict
unchallenged. Nothing here trusts a precomputed boolean. Every gate is recomputed
from the metrics, and the recorded claims are compared against the re-derivation
-- a disagreement is evidence tampering and blocks, rather than being resolved in
either direction.

Terminal states follow project governance exactly:

``PASS``    a legitimately completed analysis in which every re-derived BEST-K
            gate holds;
``FAIL``    a legitimately completed analysis in which at least one does not.
            A completed scientific FAIL stays FAIL;
``BLOCKED`` an operational, provenance, binding, or completeness failure. An
            operational problem never becomes a scientific FAIL.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mineocclude.prospective.development_workflow import (
    EvidenceError, canonical_payload_sha256, load_json, sha256_file,
)
from mineocclude.prospective.package_binding import (
    PackageBindingError, stage2_decision_artifact_id,
)
from mineocclude.prospective.stage2_evidence import (
    REQUIRED_SCENES, verify_evidence_payload,
)

SCHEMA_VERSION = "1.0"

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"

#: The six gates, in the order the authority enumerates them. Held here as the
#: evaluator's own expectation so that a decision-authority document listing a
#: different set is refused rather than silently obeyed.
BEST_K_GATES = (
    "NO_WALL_r2", "NO_WALL_rmse", "WALL_beats_training_time_baseline",
    "WALL_r2", "WALL_rmse", "WALL_time_confound_gate",
)


class Stage2Blocked(EvidenceError):
    """An operational condition that prevents a scientific verdict.

    Deliberately an ``EvidenceError`` subclass so existing fail-closed handlers
    catch it, and deliberately distinct so the terminal unit can tell "we could
    not evaluate" from "we evaluated and it failed".
    """


@dataclass(frozen=True)
class Stage2Decision:
    """One terminal Stage-2 verdict, serializable under the experiment's identity."""

    status: str
    gates: dict[str, Any]
    estimands: dict[str, Any]
    reasons: tuple[str, ...]

    def to_dict(self, *, artifact_id: str, authority_sha256: str,
                decision_authority_sha256: str, manifest_sha256: str,
                evidence_sha256: str, scientific_run_id: str) -> dict[str, Any]:
        if not isinstance(artifact_id, str) or not artifact_id:
            raise EvidenceError("Stage-2 decision artifact identity is missing")
        if self.status not in (PASS, FAIL, BLOCKED):
            raise EvidenceError(f"Stage-2 decision status is not terminal: {self.status!r}")
        payload = {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": artifact_id,
            "classification": "DEVELOPMENT_ONLY",
            "status": self.status,
            "authority_sha256": authority_sha256,
            "stage2_decision_authority_sha256": decision_authority_sha256,
            "stage2_manifest_sha256": manifest_sha256,
            "stage2_evidence_sha256": evidence_sha256,
            "scientific_run_id": scientific_run_id,
            "gates": self.gates,
            "estimands": self.estimands,
            "reasons": list(self.reasons),
            "leading_readout": "BEST_K",
            "full_readout_is_never_gating": True,
            "full_may_not_rescue_best_k_failure": True,
            # The bounded interpretation, stated in the artifact so an auditor
            # reading the decision alone cannot mistake its scope.
            "interpretation": (
                "The frozen DEVELOPMENT_ONLY Stage-2 hidden-position decoding "
                "experiment was evaluated against its prospectively frozen "
                "decoding criteria. A PASS supports only the bounded statement "
                "that layer-4 activations contain decodable information "
                "according to those criteria, on this apparatus, at these "
                "paths. It establishes nothing about object permanence, belief, "
                "causal use, uncertainty representation, general world-model "
                "competence, or behavioral reliance on the representation."),
            "establishes_object_permanence": False,
            "establishes_belief": False,
            "establishes_causal_use": False,
            "establishes_uncertainty_representation": False,
            "establishes_general_world_model_competence": False,
            "establishes_behavioral_reliance": False,
            "may_authorize_confirmatory_collection": False,
            "may_authorize_causal_intervention": False,
            "may_authorize_next_rung": False,
            "confirmatory_reuse_forbidden": True,
            "confirmatory_interpretation_authorized": False,
        }
        payload["decision_payload_sha256"] = canonical_payload_sha256(
            payload, omit="decision_payload_sha256")
        return payload


class Stage2Evaluator:
    """Re-derive every Stage-2 gate from bound evidence and frozen authority.

    Reads thresholds from ``authority_parameters.json``'s ``stage2_policy`` and
    procedure/terminal rules from the promoted ``stage2_decision_authority.json``.
    Neither is consulted for a verdict; both are consulted for a rule.
    """

    def __init__(self, authority: Mapping[str, Any], decision_authority: Mapping[str, Any],
                 manifest: Mapping[str, Any], *, authority_sha256: str,
                 decision_authority_sha256: str, manifest_sha256: str):
        self.authority = authority
        self.decision_authority = decision_authority
        self.manifest = manifest
        self.authority_sha256 = authority_sha256
        self.decision_authority_sha256 = decision_authority_sha256
        self.manifest_sha256 = manifest_sha256
        try:
            self.policy = authority["stage2_policy"]["readout"]
            self.design = authority["stage2_policy"]
        except (KeyError, TypeError) as exc:
            raise Stage2Blocked("authority declares no Stage-2 readout policy") from exc
        gates = (decision_authority.get("best_k_gates") or {}).get("names")
        if list(gates or []) != list(BEST_K_GATES):
            raise Stage2Blocked(
                "Stage-2 decision authority enumerates a different BEST-K gate set "
                f"than the evaluator implements: {gates!r}")
        terminal = decision_authority.get("terminal") or {}
        if list(terminal.get("states") or []) != [PASS, FAIL, BLOCKED]:
            raise Stage2Blocked("Stage-2 decision authority declares different terminal states")
        if terminal.get("leading_readout") != "BEST_K" \
                or self.policy.get("leading") != "BEST_K":
            raise Stage2Blocked("Stage-2 leading readout is not BEST_K")
        if self.policy.get("full_may_not_rescue_best_k_failure") is not True:
            raise Stage2Blocked("authority does not forbid FULL from rescuing BEST-K")

    # -- gate re-derivation --------------------------------------------------

    def _rederive_best_k_gates(self, scenes: Mapping[str, Any]) -> dict[str, bool]:
        """Recompute the six gates. This is the only place a gate value is produced."""
        ceiling = self.policy["best_k_each_scene_rmse_maximum_blocks"]
        confound_maximum = self.policy[
            "training_only_time_baseline_macro_r2_tau_1_to_15_maximum"]
        checks: dict[str, bool] = {}
        for scene in REQUIRED_SCENES:
            metrics = scenes[scene]["metrics"]
            checks[f"{scene}_rmse"] = metrics["rmse_blocks"] <= ceiling
            checks[f"{scene}_r2"] = (metrics["macro_r2"] > 0
                                     and metrics["bootstrap95_macro_r2"][0] > 0)
        wall = scenes["WALL"]
        checks["WALL_beats_training_time_baseline"] = (
            wall["metrics"]["rmse_blocks"] < wall["training_time_baseline"]["rmse_blocks"])
        checks["WALL_time_confound_gate"] = (
            wall["training_time_baseline_tau1_15"]["macro_r2"] <= confound_maximum)
        if sorted(checks) != list(BEST_K_GATES):
            raise Stage2Blocked("re-derived gate set is not the authority's six")
        return checks

    # -- completeness --------------------------------------------------------

    def _require_complete_and_bound(self, evidence: Mapping[str, Any]) -> None:
        verify_evidence_payload(evidence)
        expected = {
            "authority_sha256": self.authority_sha256,
            "stage2_decision_authority_sha256": self.decision_authority_sha256,
            "stage2_manifest_sha256": self.manifest_sha256,
            "scientific_run_id": self.manifest.get("run_namespace"),
            "classification": "DEVELOPMENT_ONLY",
            "layer": 4,
            "all_layer_extraction_performed": False,
            "evidence_builder_asserted_scientific_status": False,
        }
        for key, value in expected.items():
            if evidence.get(key) != value:
                raise Stage2Blocked(
                    f"Stage-2 evidence binding mismatch on {key!r} "
                    f"({evidence.get(key)!r} != {value!r})")
        try:
            expected_artifact = stage2_decision_artifact_id(self.manifest).replace(
                "-decision-", "-evidence-")
        except PackageBindingError as exc:
            raise Stage2Blocked("Stage-2 manifest carries no versioned identity") from exc
        if evidence.get("artifact_id") != expected_artifact:
            raise Stage2Blocked(
                f"Stage-2 evidence identity is {evidence.get('artifact_id')!r}, "
                f"expected {expected_artifact!r}")
        if evidence.get("capture_count") != self.design["scientific_capture_count"]:
            raise Stage2Blocked(
                f"Stage-2 evidence covers {evidence.get('capture_count')!r} captures, "
                f"authority requires {self.design['scientific_capture_count']}")
        if evidence.get("trajectory_identity_count") != self.design["paired_trajectory_identities"]:
            raise Stage2Blocked("Stage-2 evidence trajectory identity count is not the authority's")
        if evidence.get("required_target_rows_per_capture") \
                != self.design["required_target_rows_per_capture"]:
            raise Stage2Blocked("Stage-2 evidence target row count is not the authority's")
        gate = evidence.get("physical_gate") or {}
        if gate.get("status") != "PASS":
            raise Stage2Blocked("Stage-2 physical gate did not PASS")
        inventory = evidence.get("capture_inventory")
        if not isinstance(inventory, list) or len(inventory) != evidence["capture_count"]:
            raise Stage2Blocked("Stage-2 capture inventory is incomplete")
        for record in inventory:
            if record.get("target_rows_authority_bound") is not True:
                raise Stage2Blocked(
                    f"{record.get('unit_id')!r}: activations were not proved against "
                    "the authority's target rows")
        bootstrap = evidence.get("bootstrap_configuration") or {}
        for field, key in (("unit", "bootstrap_unit"), ("resamples", "bootstrap_resamples"),
                           ("seed", "bootstrap_seed")):
            if bootstrap.get(field) != self.policy[key]:
                raise Stage2Blocked(f"Stage-2 bootstrap {field} is not the authority's")
        readouts = evidence.get("readouts") or {}
        for stage in ("best_k", "full"):
            if stage not in readouts:
                raise Stage2Blocked(f"Stage-2 evidence carries no {stage} readout")
            if set(readouts[stage].get("scenes") or {}) != set(REQUIRED_SCENES):
                raise Stage2Blocked(f"Stage-2 {stage} readout scene coverage is incomplete")

    # -- entry point ---------------------------------------------------------

    def evaluate(self, evidence: Mapping[str, Any]) -> Stage2Decision:
        """Return the terminal verdict. Never raises for a scientific outcome."""
        try:
            self._require_complete_and_bound(evidence)
            best = evidence["readouts"]["best_k"]
            checks = self._rederive_best_k_gates(best["scenes"])
            # The readout graded itself. That grade is compared, never consumed:
            # if it disagrees with the re-derivation the evidence is inconsistent
            # and the result is operational, not scientific.
            claimed = best.get("readout_claimed_qualification_checks") or {}
            if {name: bool(value) for name, value in claimed.items()} != checks:
                raise Stage2Blocked(
                    "recorded BEST-K qualification checks disagree with the "
                    f"re-derivation: recorded={dict(sorted(claimed.items()))} "
                    f"re-derived={dict(sorted(checks.items()))}")
        except Stage2Blocked as exc:
            return Stage2Decision(BLOCKED, {}, {}, (str(exc),))
        except (EvidenceError, KeyError, TypeError, ValueError) as exc:
            return Stage2Decision(BLOCKED, {}, {}, (f"{type(exc).__name__}: {exc}",))

        gates = {name: {"status": PASS if checks[name] else FAIL} for name in BEST_K_GATES}
        failing = sorted(name for name in BEST_K_GATES if not checks[name])
        status = PASS if not failing else FAIL
        estimands = {}
        for stage in ("best_k", "full"):
            for scene in REQUIRED_SCENES:
                block = evidence["readouts"][stage]["scenes"][scene]
                estimands[f"{stage}.{scene}"] = {
                    "rmse_blocks": block["metrics"]["rmse_blocks"],
                    "macro_r2": block["metrics"]["macro_r2"],
                    "bootstrap95_macro_r2": list(block["metrics"]["bootstrap95_macro_r2"]),
                    "training_time_baseline_rmse_blocks":
                        block["training_time_baseline"]["rmse_blocks"],
                    "training_time_baseline_tau1_15_macro_r2":
                        block["training_time_baseline_tau1_15"]["macro_r2"],
                }
        return Stage2Decision(status, gates, estimands, tuple(failing))


def evaluate_stage2(evidence: Mapping[str, Any], *, authority: Mapping[str, Any],
                    decision_authority: Mapping[str, Any], manifest: Mapping[str, Any],
                    authority_sha256: str, decision_authority_sha256: str,
                    manifest_sha256: str, evidence_sha256: str) -> dict[str, Any]:
    """Evaluate and serialize in one step, under the manifest's own identity.

    Constructing the evaluator can itself block -- a decision authority declaring
    a different gate set is exactly such a case -- so construction is inside the
    guarded region and the caller always receives a terminal artifact.
    """
    try:
        evaluator = Stage2Evaluator(
            authority, decision_authority, manifest, authority_sha256=authority_sha256,
            decision_authority_sha256=decision_authority_sha256,
            manifest_sha256=manifest_sha256)
        decision = evaluator.evaluate(evidence)
    except Stage2Blocked as exc:
        decision = Stage2Decision(BLOCKED, {}, {}, (str(exc),))
    try:
        artifact_id = stage2_decision_artifact_id(manifest)
    except PackageBindingError as exc:
        raise EvidenceError("Stage-2 manifest carries no versioned identity") from exc
    return decision.to_dict(
        artifact_id=artifact_id, authority_sha256=authority_sha256,
        decision_authority_sha256=decision_authority_sha256,
        manifest_sha256=manifest_sha256, evidence_sha256=evidence_sha256,
        scientific_run_id=str(manifest.get("run_namespace")))


def require_stage2_decision_reproduction(
        decision: Mapping[str, Any], *, evidence_path: Path, authority_path: Path,
        stage2_decision_authority_path: Path, manifest_path: Path,
        decision_path: Path | None = None) -> dict[str, Any]:
    """Refuse unless the decision re-derives byte-identically from what it binds.

    The Stage-2 counterpart of the Stage-1 re-derivation inside
    ``require_stage2_authorization``: given the frozen evidence, authority,
    decision authority, and manifest, the decision must reproduce exactly. Any
    mutation of a metric, a gate, a fold, a bootstrap parameter, a checkpoint
    binding, a target mapping, a digest, an artifact identity, or a package
    version breaks the reproduction and raises.
    """
    if not isinstance(decision, Mapping) or not decision:
        raise EvidenceError("Stage-2 decision artifact is absent")
    if decision_path is not None:
        if not decision_path.is_file() or load_json(decision_path) != dict(decision):
            raise EvidenceError("exact on-disk Stage-2 decision artifact is required")
    for path in (evidence_path, authority_path, stage2_decision_authority_path, manifest_path):
        if not path.is_file():
            raise EvidenceError(f"Stage-2 reproduction input is absent: {path}")

    evidence = load_json(evidence_path)
    evidence_sha256 = sha256_file(evidence_path)
    if decision.get("stage2_evidence_sha256") != evidence_sha256:
        raise EvidenceError("Stage-2 decision is not bound to the evidence on disk")
    if decision.get("decision_payload_sha256") != canonical_payload_sha256(
            decision, omit="decision_payload_sha256"):
        raise EvidenceError("Stage-2 decision payload digest does not reproduce")

    reproduced = evaluate_stage2(
        evidence, authority=load_json(authority_path),
        decision_authority=load_json(stage2_decision_authority_path),
        manifest=load_json(manifest_path),
        authority_sha256=sha256_file(authority_path),
        decision_authority_sha256=sha256_file(stage2_decision_authority_path),
        manifest_sha256=sha256_file(manifest_path), evidence_sha256=evidence_sha256)
    if reproduced != dict(decision):
        raise EvidenceError("Stage-2 decision is not reproduced from bound evidence")
    return reproduced
