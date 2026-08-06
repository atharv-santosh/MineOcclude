"""Direction-control construction audit (Person D Step 7.2).

Execution manual Step 7.2 requires validating Person B/A evidence for the
direction identity, seed, raw-space versus standardized-space identity,
pre-projection norm, post-projection norm, orthogonality tolerance, norm
matching, perturbation cap, target layer, target timestep, held-out
partition, and supersession status -- and rejecting missing or
contradictory metadata.

Person D *audits* this evidence. It does not reconstruct, retune, or
re-derive Person B's scientific direction: there is deliberately no
function here that fits, normalizes, or repairs a direction. Every check
is a comparison between what B/A declared and what the frozen B-to-A
intervention request contract requires
(``docs/contracts/intervention_request_v1.md``).

A missing field is a failure, not a skipped check. That distinction is
the whole point: an audit that silently passes on absent metadata would
certify a direction nobody actually verified.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

SCHEMA_ID = "person-d-direction-control-audit-v0-1"
SCHEMA_VERSION = "1.0"

#: Frozen requirements copied from the B-to-A intervention request
#: contract. Person D restates them for provenance and never relaxes them.
FROZEN_DIRECTION_SPACE = "raw_activation"
FROZEN_DIRECTION_DIMENSION = 2048
FROZEN_UNIT_NORM_TOLERANCE = 1e-5
FROZEN_ORTHOGONALITY_TOLERANCE = 1e-6
FROZEN_LAYER_RANGE = (0, 19)
FROZEN_TIMESTEP_RANGE = (0, 15)

#: Every field an auditable direction-construction record must carry.
#: Absence of any one of them is a hard failure.
REQUIRED_EVIDENCE_FIELDS: tuple[str, ...] = (
    "direction_id",
    "direction_version",
    "direction_hash",
    "space",
    "dimension",
    "seed",
    "residual_norm_before_normalization",
    "near_zero_threshold",
    "pre_projection_norm",
    "post_projection_norm",
    "standardized_during_fit",
    "inverse_transformed_before_export",
    "raw_space_equivalence_verified",
    "max_relative_activation_norm",
    "typical_activation_norm",
    "target_layer_idx",
    "target_timestep_idx",
    "hook_site",
    "held_out_partition_id",
    "used_test_data_to_select_direction",
    "used_heldout_outcomes_to_select_direction",
    "supersession_status",
)

SUPERSESSION_STATUSES: tuple[str, ...] = ("current", "superseded", "withdrawn")

CHECK_RESULTS: tuple[str, ...] = ("pass", "fail", "blocked")


class DirectionAuditError(ValueError):
    """Raised when an audit cannot be performed or expressed honestly."""


@dataclass(frozen=True)
class AuditFinding:
    """One check's outcome.

    ``blocked`` is distinct from ``fail``: blocked means the evidence
    needed to decide does not exist yet (an external dependency), while
    fail means the evidence exists and contradicts the contract.
    """

    check_name: str
    result: str
    detail: str

    def __post_init__(self) -> None:
        if self.result not in CHECK_RESULTS:
            raise DirectionAuditError(
                f"check {self.check_name!r} has unknown result {self.result!r}"
            )
        if not self.detail:
            raise DirectionAuditError(
                f"check {self.check_name!r} records no detail; an audit finding "
                "with no explanation cannot be reviewed"
            )


def _finding(name: str, passed: bool, detail: str) -> AuditFinding:
    return AuditFinding(name, "pass" if passed else "fail", detail)


def audit_direction_construction(
    evidence: Optional[Mapping[str, Any]],
    *,
    real_direction_values: Optional[Sequence[float]] = None,
    control_direction_values: Optional[Sequence[float]] = None,
) -> list[AuditFinding]:
    """Audit one direction-construction record against the frozen contract.

    Passing ``evidence=None`` (no real B artifact yet) yields a single
    ``blocked`` finding rather than a pass or a fail -- an unavailable
    input is not a negative result.
    """

    if evidence is None:
        return [
            AuditFinding(
                "direction_evidence_present",
                "blocked",
                "no Person B direction-construction record was supplied; the "
                "audit cannot decide either way until B publishes one",
            )
        ]

    findings: list[AuditFinding] = []

    missing = [field for field in REQUIRED_EVIDENCE_FIELDS if field not in evidence]
    findings.append(
        _finding(
            "required_metadata_complete",
            not missing,
            "every required construction field is present"
            if not missing
            else f"missing required fields: {missing}",
        )
    )
    if missing:
        # Without complete metadata the remaining checks would be
        # decided on absent evidence, which is exactly what this module
        # refuses to do.
        return findings

    findings.append(
        _finding(
            "direction_identity_declared",
            bool(evidence["direction_id"]) and bool(evidence["direction_version"]),
            f"direction_id={evidence['direction_id']!r} "
            f"version={evidence['direction_version']!r}",
        )
    )
    findings.append(
        _finding(
            "direction_hash_is_sha256",
            isinstance(evidence["direction_hash"], str)
            and len(evidence["direction_hash"]) == 64,
            f"direction_hash={str(evidence['direction_hash'])[:16]}...",
        )
    )
    findings.append(
        _finding(
            "seed_recorded",
            evidence["seed"] is not None,
            f"seed={evidence['seed']!r}",
        )
    )

    space = evidence["space"]
    findings.append(
        _finding(
            "direction_is_raw_activation_space",
            space == FROZEN_DIRECTION_SPACE,
            f"space={space!r}; the frozen contract requires "
            f"{FROZEN_DIRECTION_SPACE!r}",
        )
    )
    findings.append(
        _finding(
            "direction_dimension_matches_contract",
            evidence["dimension"] == FROZEN_DIRECTION_DIMENSION,
            f"dimension={evidence['dimension']!r}; contract requires "
            f"{FROZEN_DIRECTION_DIMENSION}",
        )
    )

    standardized = bool(evidence["standardized_during_fit"])
    inverse_done = bool(evidence["inverse_transformed_before_export"])
    raw_verified = bool(evidence["raw_space_equivalence_verified"])
    if standardized:
        findings.append(
            _finding(
                "standardized_fit_was_inverse_transformed",
                inverse_done and raw_verified,
                "standardized fitting requires an inverse transform back to raw "
                f"space and explicit verification; inverse_transformed="
                f"{inverse_done} raw_space_equivalence_verified={raw_verified}",
            )
        )
    else:
        findings.append(
            _finding(
                "raw_space_equivalence_verified",
                raw_verified,
                f"raw_space_equivalence_verified={raw_verified}",
            )
        )

    residual = evidence["residual_norm_before_normalization"]
    threshold = evidence["near_zero_threshold"]
    findings.append(
        _finding(
            "residual_above_near_zero_threshold",
            isinstance(residual, (int, float))
            and isinstance(threshold, (int, float))
            and residual > threshold,
            f"residual_norm_before_normalization={residual!r} must exceed "
            f"near_zero_threshold={threshold!r}",
        )
    )

    pre_norm = evidence["pre_projection_norm"]
    post_norm = evidence["post_projection_norm"]
    findings.append(
        _finding(
            "pre_and_post_projection_norms_recorded",
            isinstance(pre_norm, (int, float)) and isinstance(post_norm, (int, float)),
            f"pre_projection_norm={pre_norm!r} post_projection_norm={post_norm!r}",
        )
    )
    if isinstance(post_norm, (int, float)):
        findings.append(
            _finding(
                "post_projection_norm_is_unit",
                abs(post_norm - 1.0) <= FROZEN_UNIT_NORM_TOLERANCE,
                f"post_projection_norm={post_norm!r} must be within "
                f"{FROZEN_UNIT_NORM_TOLERANCE} of 1.0",
            )
        )

    max_relative = evidence["max_relative_activation_norm"]
    typical = evidence["typical_activation_norm"]
    if isinstance(max_relative, (int, float)) and isinstance(typical, (int, float)):
        cap = max_relative * typical
        findings.append(
            _finding(
                "perturbation_cap_is_positive_and_declared",
                cap > 0.0,
                f"declared cap = {max_relative!r} x {typical!r} = {cap}",
            )
        )
    else:
        findings.append(
            AuditFinding(
                "perturbation_cap_is_positive_and_declared",
                "fail",
                "max_relative_activation_norm and typical_activation_norm must "
                "both be numeric",
            )
        )

    layer_low, layer_high = FROZEN_LAYER_RANGE
    findings.append(
        _finding(
            "target_layer_in_frozen_range",
            isinstance(evidence["target_layer_idx"], int)
            and layer_low <= evidence["target_layer_idx"] <= layer_high,
            f"target_layer_idx={evidence['target_layer_idx']!r}; frozen range "
            f"{FROZEN_LAYER_RANGE}",
        )
    )
    step_low, step_high = FROZEN_TIMESTEP_RANGE
    findings.append(
        _finding(
            "target_timestep_in_frozen_range",
            isinstance(evidence["target_timestep_idx"], int)
            and step_low <= evidence["target_timestep_idx"] <= step_high,
            f"target_timestep_idx={evidence['target_timestep_idx']!r}; frozen "
            f"range {FROZEN_TIMESTEP_RANGE}",
        )
    )
    findings.append(
        _finding(
            "held_out_partition_declared",
            bool(evidence["held_out_partition_id"]),
            f"held_out_partition_id={evidence['held_out_partition_id']!r}",
        )
    )
    findings.append(
        _finding(
            "direction_not_selected_by_test_or_heldout_outcomes",
            not evidence["used_test_data_to_select_direction"]
            and not evidence["used_heldout_outcomes_to_select_direction"],
            "used_test_data="
            f"{evidence['used_test_data_to_select_direction']!r} "
            "used_heldout_outcomes="
            f"{evidence['used_heldout_outcomes_to_select_direction']!r}",
        )
    )
    findings.append(
        _finding(
            "supersession_status_is_known",
            evidence["supersession_status"] in SUPERSESSION_STATUSES,
            f"supersession_status={evidence['supersession_status']!r}; expected "
            f"one of {SUPERSESSION_STATUSES}",
        )
    )

    if real_direction_values is not None and control_direction_values is not None:
        findings.append(_audit_norm_matching(real_direction_values, control_direction_values))
        findings.append(
            _audit_orthogonality(real_direction_values, control_direction_values)
        )
    else:
        findings.append(
            AuditFinding(
                "control_direction_norm_and_orthogonality",
                "blocked",
                "the real and control direction vectors were not supplied; norm "
                "matching and orthogonality cannot be checked from metadata alone",
            )
        )

    return findings


def _l2(values: Sequence[float]) -> float:
    return math.sqrt(sum(float(v) * float(v) for v in values))


def _audit_norm_matching(
    real_values: Sequence[float], control_values: Sequence[float]
) -> AuditFinding:
    real_norm = _l2(real_values)
    control_norm = _l2(control_values)
    if real_norm == 0.0:
        return AuditFinding(
            "control_direction_norm_matched",
            "fail",
            "the real direction has zero norm and cannot be norm-matched against",
        )
    ratio = control_norm / real_norm
    passed = abs(ratio - 1.0) <= FROZEN_UNIT_NORM_TOLERANCE
    return AuditFinding(
        "control_direction_norm_matched",
        "pass" if passed else "fail",
        f"control/real norm ratio={ratio:.10f} (real={real_norm:.10f}, "
        f"control={control_norm:.10f}); tolerance {FROZEN_UNIT_NORM_TOLERANCE}",
    )


def _audit_orthogonality(
    real_values: Sequence[float], control_values: Sequence[float]
) -> AuditFinding:
    real_norm = _l2(real_values)
    control_norm = _l2(control_values)
    if real_norm == 0.0 or control_norm == 0.0:
        return AuditFinding(
            "control_direction_orthogonal_to_real",
            "fail",
            "a zero-norm direction has no defined orientation",
        )
    dot = sum(float(a) * float(b) for a, b in zip(real_values, control_values))
    cosine = dot / (real_norm * control_norm)
    passed = abs(cosine) <= FROZEN_ORTHOGONALITY_TOLERANCE
    return AuditFinding(
        "control_direction_orthogonal_to_real",
        "pass" if passed else "fail",
        f"cosine similarity to the real direction={cosine:.12f}; tolerance "
        f"{FROZEN_ORTHOGONALITY_TOLERANCE}",
    )


def build_direction_control_audit(
    *,
    audit_id: str,
    findings: Sequence[AuditFinding],
    evidence_source: Mapping[str, Any],
    evidence_kind: str = "synthetic",
) -> dict[str, Any]:
    """Assemble the machine-readable direction-control audit document."""

    if evidence_kind not in ("real", "synthetic"):
        raise DirectionAuditError("evidence_kind must be 'real' or 'synthetic'")
    if not findings:
        raise DirectionAuditError("an audit must contain at least one finding")

    counts = {result: 0 for result in CHECK_RESULTS}
    for finding in findings:
        counts[finding.result] += 1

    if counts["fail"]:
        decision = "FAIL"
    elif counts["blocked"]:
        decision = "BLOCKED"
    else:
        decision = "PASS"

    return {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "audit_id": audit_id,
        "evidence_kind": evidence_kind,
        "evidence_source": dict(sorted(evidence_source.items())),
        "auditor_scope": (
            "Person D verifies Person B/A direction-construction evidence "
            "against the frozen B-to-A intervention request contract. Person D "
            "never fits, normalizes, retunes, or repairs the direction."
        ),
        "decision": decision,
        "result_counts": counts,
        "findings": tuple(
            {
                "check_name": finding.check_name,
                "result": finding.result,
                "detail": finding.detail,
            }
            for finding in sorted(findings, key=lambda f: f.check_name)
        ),
    }


def validate_direction_control_audit(document: Mapping[str, Any]) -> None:
    """Validate an audit document, raising on the first violation."""

    if document.get("schema_id") != SCHEMA_ID:
        raise DirectionAuditError(
            f"expected schema_id {SCHEMA_ID!r}, got {document.get('schema_id')!r}"
        )
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise DirectionAuditError("evidence_kind must be 'real' or 'synthetic'")

    findings = document.get("findings") or ()
    if not findings:
        raise DirectionAuditError("an audit must contain findings")

    counts = {result: 0 for result in CHECK_RESULTS}
    for finding in findings:
        if finding["result"] not in CHECK_RESULTS:
            raise DirectionAuditError(
                f"unknown finding result {finding['result']!r}"
            )
        if not finding.get("detail"):
            raise DirectionAuditError(
                f"finding {finding['check_name']!r} has no detail"
            )
        counts[finding["result"]] += 1

    if document.get("result_counts") != counts:
        raise DirectionAuditError("result_counts do not match the findings")

    expected = "FAIL" if counts["fail"] else ("BLOCKED" if counts["blocked"] else "PASS")
    if document.get("decision") != expected:
        raise DirectionAuditError(
            f"decision {document.get('decision')!r} does not follow from the "
            f"findings (expected {expected!r}); a blocked check must never be "
            "reported as a pass"
        )


def dump_direction_control_audit(document: Mapping[str, Any]) -> str:
    """Serialize a validated audit deterministically."""

    validate_direction_control_audit(document)
    return json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "CHECK_RESULTS",
    "FROZEN_DIRECTION_DIMENSION",
    "FROZEN_DIRECTION_SPACE",
    "FROZEN_ORTHOGONALITY_TOLERANCE",
    "FROZEN_UNIT_NORM_TOLERANCE",
    "REQUIRED_EVIDENCE_FIELDS",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "SUPERSESSION_STATUSES",
    "AuditFinding",
    "DirectionAuditError",
    "audit_direction_construction",
    "build_direction_control_audit",
    "dump_direction_control_audit",
    "validate_direction_control_audit",
]
