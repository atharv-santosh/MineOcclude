"""Phase 4 Step 4.1: the exact scientific baseline input contract (Person D).

This module defines what "ready to fit and export a scientific (not
synthetic) D baseline" means, and fails closed until every real
upstream identity is present. It does not fit anything and does not
invent Person B's math: every real dependency below is validated by
calling B's own authority directly.

## 1. The exact scientific baseline input contract

A baseline export is scientific-ready only when *all* of the following
hold simultaneously:

- every :class:`~mineocclude.baselines.interface.TrajectoryContext`
  carries a real fold index, never
  :data:`mineocclude.baselines.capture_ingest.UNASSIGNED_FOLD`;
- a sealed, structurally valid Person B fold/split manifest is
  supplied and validates against
  :func:`mineocclude.probes.splits.validate_fold_manifest` (**item 2**);
- a sealed, structurally valid Person B oracle-target document is
  supplied and validates against
  :func:`mineocclude.oracle.schema.validate_oracle_target_document`
  (**item 3**); this transitively validates every target row's
  universal identity and lifecycle `status` via
  :func:`mineocclude.contracts.identity.validate_identity` -- D does
  not re-check accepted-trajectory/model-context identity separately,
  since B's own oracle-target validator already does (**item 4**);
- the exact `(trajectory_id, model_frame_idx)` key set requested by
  the contexts, the fold manifest's memberships, and the oracle
  target document's rows are all identical -- no row may be scored
  from a fold or a target it was never a member of, and no member/
  target row may be silently dropped;
- the caller explicitly declares `candidate_scientific_use=` a
  literal `"accepted"`. Any other value -- including the existing
  `docs/status/person_d_real_pilot_baseline_preview.json`'s own
  `"scientific_use": "forbidden"`, or a B oracle-target document
  whose `fixture_metadata.scientific_use == "forbidden"` -- fails
  closed. There is no default: a caller must say "accepted" in so
  many words to get past this gate.

Fail-closed means the function below never raises on bad input to
short-circuit early; it collects every violation and returns a single
:class:`ScientificReadinessFinding` naming all of them, so a caller
fixing one problem does not have to rediscover the rest one at a time.

## 5. Deterministic baseline prediction artifact IDs

:func:`build_baseline_prediction_artifact_id` derives one deterministic
ID from exactly the identities a scientific prediction artifact
depends on (see item 6) plus the baseline/target identity. Two calls
with the same inputs always produce the same ID; changing any one
input changes the ID. This is what Registry v2-style exact-artifact
authorization (module `registry_v2_artifacts`) binds to.

## 6. Direct-input relationships

:data:`BASELINE_PREDICTION_DIRECT_INPUTS` is the single frozen list of
upstream identities a scientific baseline prediction artifact directly
depends on. Both the artifact-ID builder and the readiness validator
read this same constant, so the code and any documentation generated
from it can never drift apart by being edited independently.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from mineocclude.analysis.manifests import AnalysisArtifactError, sha256_value
from mineocclude.baselines.capture_ingest import UNASSIGNED_FOLD
from mineocclude.baselines.interface import TrajectoryContext
from mineocclude.oracle.schema import (
    OracleValidationError,
    validate_oracle_target_document,
)
from mineocclude.probes.splits import GroupedSplitError, validate_fold_manifest

SCIENTIFIC_BASELINE_INPUT_CONTRACT_SCHEMA_VERSION = "person-d-scientific-baseline-input-v0.1"

#: The only value that unlocks a READY verdict. There is no default
#: and no boolean shortcut -- see module docstring item 1's last bullet.
READY_SCIENTIFIC_USE = "accepted"

#: Item 6: the exact, frozen set of upstream identities a scientific
#: baseline prediction artifact directly depends on. Referenced by
#: both the artifact-ID builder below and
#: ``registry_v2_artifacts.build_exact_artifact_authorization``.
BASELINE_PREDICTION_DIRECT_INPUTS: tuple[str, ...] = (
    "fold_manifest_hash",
    "oracle_target_hash",
    "config_hash",
)

RowKey = tuple[str, int]


class ScientificReadinessError(ValueError):
    """Raised when the inputs to the readiness check are malformed.

    Distinct from a BLOCKED finding: this means the call itself cannot
    be evaluated (e.g. a required argument has the wrong type), not
    that the scientific inputs were found lacking.
    """


@dataclass(frozen=True)
class ScientificReadinessFinding:
    status: str
    """One of ``"READY"`` or ``"BLOCKED"``."""

    blocked_reasons: tuple[str, ...]
    n_rows: int
    candidate_scientific_use: str
    contract_schema_version: str = SCIENTIFIC_BASELINE_INPUT_CONTRACT_SCHEMA_VERSION


def _row_keys_from_fold_manifest(fold_manifest: Mapping[str, object]) -> set:
    memberships = fold_manifest.get("memberships")
    if not isinstance(memberships, list):
        return set()
    keys = set()
    for membership in memberships:
        if isinstance(membership, Mapping):
            keys.add((membership.get("trajectory_id"), membership.get("model_frame_idx")))
    return keys


def _row_keys_from_oracle_target_document(document: Mapping[str, object]) -> set:
    rows = document.get("rows")
    if not isinstance(rows, list):
        return set()
    keys = set()
    for row in rows:
        if isinstance(row, Mapping):
            keys.add((row.get("trajectory_id"), row.get("model_frame_idx")))
    return keys


def validate_scientific_baseline_readiness(
    contexts: Sequence[TrajectoryContext],
    *,
    fold_manifest: Mapping[str, object],
    oracle_target_document: Mapping[str, object],
    candidate_scientific_use: str,
) -> ScientificReadinessFinding:
    """Fail-closed gate: is it safe to fit/export a *scientific* D baseline.

    Never raises on bad scientific inputs -- every violation is
    collected into the returned finding's ``blocked_reasons`` rather
    than stopping at the first one. Raises
    :class:`ScientificReadinessError` only for a malformed call itself
    (e.g. no contexts supplied).
    """

    if not contexts:
        raise ScientificReadinessError("no contexts supplied")
    if not isinstance(fold_manifest, Mapping):
        raise ScientificReadinessError("fold_manifest must be a mapping")
    if not isinstance(oracle_target_document, Mapping):
        raise ScientificReadinessError("oracle_target_document must be a mapping")
    if not isinstance(candidate_scientific_use, str) or not candidate_scientific_use:
        raise ScientificReadinessError("candidate_scientific_use must be a non-empty string")

    reasons: list[str] = []

    if candidate_scientific_use != READY_SCIENTIFIC_USE:
        reasons.append(
            f"candidate_scientific_use={candidate_scientific_use!r} != "
            f"{READY_SCIENTIFIC_USE!r}; a baseline can never be promoted to "
            "scientific without this exact, explicit declaration"
        )

    unassigned = [
        (ctx.trajectory_id, ctx.model_frame_idx) for ctx in contexts if ctx.fold == UNASSIGNED_FOLD
    ]
    if unassigned:
        reasons.append(
            f"{len(unassigned)} context(s) still carry UNASSIGNED_FOLD "
            f"({UNASSIGNED_FOLD!r}), e.g. {unassigned[0]}; every row must "
            "have a real fold from a validated B fold manifest"
        )

    fold_manifest_valid = False
    try:
        validate_fold_manifest(fold_manifest)
        fold_manifest_valid = True
    except (GroupedSplitError, AnalysisArtifactError) as error:
        reasons.append(f"missing or invalid sealed B fold manifest identity: {error}")

    oracle_target_valid = False
    try:
        validate_oracle_target_document(oracle_target_document)
        oracle_target_valid = True
    except OracleValidationError as error:
        reasons.append(f"missing or invalid B oracle target identity: {error}")

    if oracle_target_valid:
        metadata = oracle_target_document.get("fixture_metadata")
        if isinstance(metadata, Mapping) and metadata.get("scientific_use") == "forbidden":
            reasons.append(
                "oracle target document fixture_metadata.scientific_use="
                "'forbidden'; this document can never be promoted to an "
                "accepted scientific baseline"
            )

    if fold_manifest_valid and oracle_target_valid:
        context_keys = {(ctx.trajectory_id, ctx.model_frame_idx) for ctx in contexts}
        fold_keys = _row_keys_from_fold_manifest(fold_manifest)
        oracle_keys = _row_keys_from_oracle_target_document(oracle_target_document)
        if not (context_keys == fold_keys == oracle_keys):
            reasons.append(
                "context, fold-manifest, and oracle-target row coverage do "
                f"not exactly match (contexts={len(context_keys)}, "
                f"fold_manifest={len(fold_keys)}, "
                f"oracle_target={len(oracle_keys)}); every requested row "
                "must be a member of exactly the same fold and target set"
            )

    status = "BLOCKED" if reasons else "READY"
    return ScientificReadinessFinding(
        status=status,
        blocked_reasons=tuple(reasons),
        n_rows=len(contexts),
        candidate_scientific_use=candidate_scientific_use,
    )


def build_baseline_prediction_artifact_id(
    *,
    baseline_id: str,
    target_name: str,
    fold_manifest_hash: str,
    oracle_target_hash: str,
    config_hash: str,
) -> str:
    """Item 5: deterministic ID for one scientific baseline prediction artifact.

    Deterministic in exactly the fields named by
    :data:`BASELINE_PREDICTION_DIRECT_INPUTS` plus the baseline/target
    identity: identical inputs always produce the identical ID, and
    changing any one input changes the ID. This is not itself a claim
    that the referenced prediction is scientific -- see
    :func:`validate_scientific_baseline_readiness`.
    """

    for name, value in (
        ("baseline_id", baseline_id),
        ("target_name", target_name),
        ("fold_manifest_hash", fold_manifest_hash),
        ("oracle_target_hash", oracle_target_hash),
        ("config_hash", config_hash),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ScientificReadinessError(f"{name} must be a non-empty string")

    direct_inputs = {
        "fold_manifest_hash": fold_manifest_hash,
        "oracle_target_hash": oracle_target_hash,
        "config_hash": config_hash,
    }
    payload = {
        "artifact_id_schema_version": "person-d-baseline-prediction-artifact-id-v0.1",
        "baseline_id": baseline_id,
        "target_name": target_name,
        "direct_inputs": direct_inputs,
    }
    return f"person_d_baseline_prediction::{sha256_value(payload)}"
