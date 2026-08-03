"""Phase 4 Step 4.1: Registry v2-style artifacts for D-owned baseline outputs.

Person E owns the project's actual Immutable Registry v2 system
(`docs/contracts/immutable_registry_v2.md`, `role/person-e-operations`).
This module does not vendor, import, or reimplement that system --
doing so would mean D owning a copy of another role's authority, and
the task instructions are explicit that this branch must not merge or
integrate other role branches. Instead, this defines D's *own*,
independent artifact types that mirror the same four handoff concepts
(owner-status, exact-artifact authorization, manifest,
verification-receipt) for exactly D's own baseline-output domain,
built entirely on primitives D already has real, direct access to:
:func:`mineocclude.analysis.manifests.seal_artifact` and
:func:`mineocclude.analysis.manifests.validate_sealed_artifact` (Person
B's real canonical-hash sealing/verification authority -- the same
primitive D already uses for fold manifests and ridge-fit artifacts).

## 7. The four D-owned registry v2 artifact types

- **Owner-status** (:func:`build_owner_status_record` /
  :func:`validate_owner_status_record`): D's own declared authority
  state -- which artifact types D is currently authorized to produce,
  and D's current ``owner_status``/``decision`` pair.
- **Exact-artifact authorization** (:func:`build_exact_artifact_authorization`
  / :func:`validate_exact_artifact_authorization`): scoped to exactly
  one target ``artifact_id`` -- never a wildcard by type or owner --
  and binds that one artifact's hash to the owner-status record and to
  the exact upstream identities named in
  ``scientific_readiness.BASELINE_PREDICTION_DIRECT_INPUTS``.
- **Manifest** (:func:`build_handoff_manifest` / :func:`validate_handoff_manifest`):
  the ordered inventory of every artifact this handoff covers, each
  entry carrying its own exact id/type/hash.
- **Verification-receipt** (:func:`build_verification_receipt` /
  :func:`validate_verification_receipt`): records that one artifact's
  bytes were independently re-hashed and matched what the manifest
  declared.

:func:`validate_registry_v2_handoff_package` is the composite
"validation" deliverable: it checks all four artifact types plus the
cross-references between them (an authorization's
``owner_status_record_hash`` must equal the owner-status record's own
sealed hash; its ``target_artifact_id`` must appear in the manifest;
a receipt must reference a manifest entry that exists).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    is_hex_digest,
    seal_artifact,
    validate_sealed_artifact,
)
from mineocclude.baselines.scientific_readiness import BASELINE_PREDICTION_DIRECT_INPUTS
from mineocclude.contracts.identity import CODE_SHA_LENGTH, SHA256_LENGTH

REGISTRY_V2_HANDOFF_SCHEMA_VERSION = "person-d-registry-v2-handoff-v0.1"

OWNER_STATUS_ARTIFACT_TYPE = "person_d_baseline_owner_status"
EXACT_ARTIFACT_AUTHORIZATION_ARTIFACT_TYPE = "person_d_baseline_exact_artifact_authorization"
HANDOFF_MANIFEST_ARTIFACT_TYPE = "person_d_baseline_handoff_manifest"
VERIFICATION_RECEIPT_ARTIFACT_TYPE = "person_d_baseline_verification_receipt"

OWNER_STATUSES = frozenset({"pending", "accepted", "rejected", "failed", "superseded"})

#: Fixed owner_status -> decision mapping, matching the closed
#: lifecycle vocabulary this project uses elsewhere
#: (``mineocclude.contracts.identity.ArtifactStatus``), extended with
#: the pending/failed states a not-yet-sealed registry needs.
OWNER_STATUS_DECISIONS: Mapping[str, str] = {
    "pending": "pending",
    "accepted": "accepted",
    "rejected": "excluded",
    "failed": "failed",
    "superseded": "excluded",
}

VERIFICATION_MODES = frozenset({"local_bytes"})
VERIFICATION_RESULTS = frozenset({"pass", "fail"})


class RegistryV2ArtifactError(ValueError):
    """Raised when a D-owned registry v2 artifact is malformed, altered,
    or references an identity that does not match its target."""


def _base_kwargs(artifact_id: str, code_sha: str, config_hash: str, input_manifest_hash: str) -> dict:
    return {
        "artifact_id": artifact_id,
        "code_sha": code_sha,
        "config_hash": config_hash,
        "input_manifest_hash": input_manifest_hash,
    }


# --------------------------------------------------------------------------
# 1. Owner-status
# --------------------------------------------------------------------------


def build_owner_status_record(
    *,
    owner_status: str,
    authority_revision: str,
    authorized_artifact_types: Sequence[str],
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
) -> dict:
    if owner_status not in OWNER_STATUSES:
        raise RegistryV2ArtifactError(
            f"owner_status must be one of {sorted(OWNER_STATUSES)}, got {owner_status!r}"
        )
    if not is_hex_digest(authority_revision, CODE_SHA_LENGTH):
        raise RegistryV2ArtifactError(
            "authority_revision must be a 40-character hex git revision"
        )
    if not authorized_artifact_types or any(
        not isinstance(value, str) or not value for value in authorized_artifact_types
    ):
        raise RegistryV2ArtifactError(
            "authorized_artifact_types must be a non-empty list of non-empty strings"
        )
    payload = {
        "artifact_type": OWNER_STATUS_ARTIFACT_TYPE,
        **_base_kwargs(artifact_id, code_sha, config_hash, input_manifest_hash),
        "registry_v2_handoff_schema_version": REGISTRY_V2_HANDOFF_SCHEMA_VERSION,
        "owner_id": "person_d",
        "owner_status": owner_status,
        "decision": OWNER_STATUS_DECISIONS[owner_status],
        "authority_revision": authority_revision,
        "authorized_artifact_types": sorted(set(authorized_artifact_types)),
    }
    return seal_artifact(payload)


def validate_owner_status_record(document: Mapping[str, object]) -> None:
    try:
        validate_sealed_artifact(document, expected_type=OWNER_STATUS_ARTIFACT_TYPE)
    except AnalysisArtifactError as error:
        raise RegistryV2ArtifactError(f"invalid owner-status record: {error}") from error
    if document.get("registry_v2_handoff_schema_version") != REGISTRY_V2_HANDOFF_SCHEMA_VERSION:
        raise RegistryV2ArtifactError("owner-status registry_v2_handoff_schema_version mismatch")
    if document.get("owner_id") != "person_d":
        raise RegistryV2ArtifactError("owner-status owner_id must be 'person_d'")
    owner_status = document.get("owner_status")
    if owner_status not in OWNER_STATUSES:
        raise RegistryV2ArtifactError("owner-status owner_status is not a recognized value")
    if document.get("decision") != OWNER_STATUS_DECISIONS[owner_status]:
        raise RegistryV2ArtifactError(
            "owner-status decision does not match the fixed owner_status mapping"
        )
    if not is_hex_digest(document.get("authority_revision"), CODE_SHA_LENGTH):
        raise RegistryV2ArtifactError("owner-status authority_revision must be a 40-hex revision")
    authorized = document.get("authorized_artifact_types")
    if (
        not isinstance(authorized, list)
        or not authorized
        or any(not isinstance(value, str) or not value for value in authorized)
    ):
        raise RegistryV2ArtifactError("owner-status authorized_artifact_types is invalid")


# --------------------------------------------------------------------------
# 2. Exact-artifact authorization (scoped to exactly one artifact_id)
# --------------------------------------------------------------------------


def build_exact_artifact_authorization(
    *,
    target_artifact_id: str,
    target_artifact_type: str,
    target_artifact_sha256: str,
    owner_status_record_hash: str,
    direct_input_hashes: Mapping[str, str],
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
) -> dict:
    for name, value in (
        ("target_artifact_id", target_artifact_id),
        ("target_artifact_type", target_artifact_type),
    ):
        if not isinstance(value, str) or not value.strip():
            raise RegistryV2ArtifactError(f"{name} must be a non-empty string")
    if not is_hex_digest(target_artifact_sha256, SHA256_LENGTH):
        raise RegistryV2ArtifactError("target_artifact_sha256 must be a SHA-256 digest")
    if not is_hex_digest(owner_status_record_hash, SHA256_LENGTH):
        raise RegistryV2ArtifactError("owner_status_record_hash must be a SHA-256 digest")
    if set(direct_input_hashes) != set(BASELINE_PREDICTION_DIRECT_INPUTS):
        raise RegistryV2ArtifactError(
            "direct_input_hashes must supply exactly "
            f"{sorted(BASELINE_PREDICTION_DIRECT_INPUTS)}"
        )
    for name, value in direct_input_hashes.items():
        if not is_hex_digest(value, SHA256_LENGTH):
            raise RegistryV2ArtifactError(f"direct_input_hashes[{name!r}] must be a SHA-256 digest")

    payload = {
        "artifact_type": EXACT_ARTIFACT_AUTHORIZATION_ARTIFACT_TYPE,
        **_base_kwargs(artifact_id, code_sha, config_hash, input_manifest_hash),
        "registry_v2_handoff_schema_version": REGISTRY_V2_HANDOFF_SCHEMA_VERSION,
        "target_artifact_id": target_artifact_id,
        "target_artifact_type": target_artifact_type,
        "target_artifact_sha256": target_artifact_sha256,
        "owner_status_record_hash": owner_status_record_hash,
        "direct_input_hashes": dict(sorted(direct_input_hashes.items())),
    }
    return seal_artifact(payload)


def validate_exact_artifact_authorization(
    document: Mapping[str, object],
    *,
    owner_status_record: Mapping[str, object],
) -> None:
    """Validate one authorization and cross-check it against its owner-status record.

    ``owner_status_record`` must itself already be a validated (not
    merely sealed) owner-status record -- callers should call
    :func:`validate_owner_status_record` on it first.
    """

    try:
        validate_sealed_artifact(document, expected_type=EXACT_ARTIFACT_AUTHORIZATION_ARTIFACT_TYPE)
    except AnalysisArtifactError as error:
        raise RegistryV2ArtifactError(f"invalid exact-artifact authorization: {error}") from error
    if document.get("registry_v2_handoff_schema_version") != REGISTRY_V2_HANDOFF_SCHEMA_VERSION:
        raise RegistryV2ArtifactError("authorization registry_v2_handoff_schema_version mismatch")
    for field in ("target_artifact_id", "target_artifact_type"):
        value = document.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RegistryV2ArtifactError(f"authorization {field} is invalid")
    if not is_hex_digest(document.get("target_artifact_sha256"), SHA256_LENGTH):
        raise RegistryV2ArtifactError("authorization target_artifact_sha256 is invalid")
    direct_input_hashes = document.get("direct_input_hashes")
    if (
        not isinstance(direct_input_hashes, Mapping)
        or set(direct_input_hashes) != set(BASELINE_PREDICTION_DIRECT_INPUTS)
    ):
        raise RegistryV2ArtifactError(
            "authorization direct_input_hashes must supply exactly "
            f"{sorted(BASELINE_PREDICTION_DIRECT_INPUTS)}"
        )
    if document.get("owner_status_record_hash") != owner_status_record.get("artifact_hash"):
        raise RegistryV2ArtifactError(
            "authorization owner_status_record_hash does not match the "
            "supplied owner-status record's own sealed hash"
        )


# --------------------------------------------------------------------------
# 3. Handoff manifest
# --------------------------------------------------------------------------


def build_handoff_manifest(
    *,
    artifact_identities: Sequence[Mapping[str, str]],
    owner_status_record_hash: str,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
) -> dict:
    if not is_hex_digest(owner_status_record_hash, SHA256_LENGTH):
        raise RegistryV2ArtifactError("owner_status_record_hash must be a SHA-256 digest")
    normalized: list[dict] = []
    seen_ids: set[str] = set()
    for entry in artifact_identities:
        if not isinstance(entry, Mapping):
            raise RegistryV2ArtifactError("each artifact identity must be a mapping")
        entry_id = entry.get("artifact_id")
        entry_type = entry.get("artifact_type")
        entry_sha256 = entry.get("artifact_sha256")
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise RegistryV2ArtifactError("artifact identity artifact_id is invalid")
        if not isinstance(entry_type, str) or not entry_type.strip():
            raise RegistryV2ArtifactError("artifact identity artifact_type is invalid")
        if not is_hex_digest(entry_sha256, SHA256_LENGTH):
            raise RegistryV2ArtifactError("artifact identity artifact_sha256 is invalid")
        if entry_id in seen_ids:
            raise RegistryV2ArtifactError(f"duplicate artifact identity in manifest: {entry_id}")
        seen_ids.add(entry_id)
        normalized.append(
            {"artifact_id": entry_id, "artifact_type": entry_type, "artifact_sha256": entry_sha256}
        )
    if not normalized:
        raise RegistryV2ArtifactError("a handoff manifest requires at least one artifact identity")
    normalized.sort(key=lambda entry: entry["artifact_id"])

    payload = {
        "artifact_type": HANDOFF_MANIFEST_ARTIFACT_TYPE,
        **_base_kwargs(artifact_id, code_sha, config_hash, input_manifest_hash),
        "registry_v2_handoff_schema_version": REGISTRY_V2_HANDOFF_SCHEMA_VERSION,
        "owner_status_record_hash": owner_status_record_hash,
        "artifact_identities": normalized,
    }
    return seal_artifact(payload)


def validate_handoff_manifest(document: Mapping[str, object]) -> None:
    try:
        validate_sealed_artifact(document, expected_type=HANDOFF_MANIFEST_ARTIFACT_TYPE)
    except AnalysisArtifactError as error:
        raise RegistryV2ArtifactError(f"invalid handoff manifest: {error}") from error
    if document.get("registry_v2_handoff_schema_version") != REGISTRY_V2_HANDOFF_SCHEMA_VERSION:
        raise RegistryV2ArtifactError("manifest registry_v2_handoff_schema_version mismatch")
    if not is_hex_digest(document.get("owner_status_record_hash"), SHA256_LENGTH):
        raise RegistryV2ArtifactError("manifest owner_status_record_hash is invalid")
    identities = document.get("artifact_identities")
    if not isinstance(identities, list) or not identities:
        raise RegistryV2ArtifactError("manifest artifact_identities must be a non-empty list")
    seen_ids: set[str] = set()
    for entry in identities:
        if not isinstance(entry, Mapping):
            raise RegistryV2ArtifactError("manifest artifact identity entries must be mappings")
        entry_id = entry.get("artifact_id")
        if entry_id in seen_ids:
            raise RegistryV2ArtifactError(f"duplicate artifact identity in manifest: {entry_id}")
        seen_ids.add(entry_id)
        if not is_hex_digest(entry.get("artifact_sha256"), SHA256_LENGTH):
            raise RegistryV2ArtifactError(f"manifest entry {entry_id!r} has an invalid artifact_sha256")


# --------------------------------------------------------------------------
# 4. Verification receipt
# --------------------------------------------------------------------------


def build_verification_receipt(
    *,
    verified_artifact_id: str,
    verified_sha256: str,
    verification_mode: str,
    verification_result: str,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
) -> dict:
    if not isinstance(verified_artifact_id, str) or not verified_artifact_id.strip():
        raise RegistryV2ArtifactError("verified_artifact_id must be a non-empty string")
    if not is_hex_digest(verified_sha256, SHA256_LENGTH):
        raise RegistryV2ArtifactError("verified_sha256 must be a SHA-256 digest")
    if verification_mode not in VERIFICATION_MODES:
        raise RegistryV2ArtifactError(f"verification_mode must be one of {sorted(VERIFICATION_MODES)}")
    if verification_result not in VERIFICATION_RESULTS:
        raise RegistryV2ArtifactError(f"verification_result must be one of {sorted(VERIFICATION_RESULTS)}")

    payload = {
        "artifact_type": VERIFICATION_RECEIPT_ARTIFACT_TYPE,
        **_base_kwargs(artifact_id, code_sha, config_hash, input_manifest_hash),
        "registry_v2_handoff_schema_version": REGISTRY_V2_HANDOFF_SCHEMA_VERSION,
        "verified_artifact_id": verified_artifact_id,
        "verified_sha256": verified_sha256,
        "verification_mode": verification_mode,
        "verification_result": verification_result,
    }
    return seal_artifact(payload)


def validate_verification_receipt(
    document: Mapping[str, object],
    *,
    handoff_manifest: Mapping[str, object],
) -> None:
    """Validate one receipt and cross-check it against the handoff manifest.

    ``handoff_manifest`` must already be validated (call
    :func:`validate_handoff_manifest` first) and must contain a
    manifest entry for ``verified_artifact_id`` whose declared hash
    matches ``verified_sha256``.
    """

    try:
        validate_sealed_artifact(document, expected_type=VERIFICATION_RECEIPT_ARTIFACT_TYPE)
    except AnalysisArtifactError as error:
        raise RegistryV2ArtifactError(f"invalid verification receipt: {error}") from error
    if document.get("registry_v2_handoff_schema_version") != REGISTRY_V2_HANDOFF_SCHEMA_VERSION:
        raise RegistryV2ArtifactError("receipt registry_v2_handoff_schema_version mismatch")
    if document.get("verification_mode") not in VERIFICATION_MODES:
        raise RegistryV2ArtifactError("receipt verification_mode is invalid")
    if document.get("verification_result") not in VERIFICATION_RESULTS:
        raise RegistryV2ArtifactError("receipt verification_result is invalid")

    verified_id = document.get("verified_artifact_id")
    manifest_entry = next(
        (
            entry
            for entry in handoff_manifest.get("artifact_identities", [])
            if isinstance(entry, Mapping) and entry.get("artifact_id") == verified_id
        ),
        None,
    )
    if manifest_entry is None:
        raise RegistryV2ArtifactError(
            f"receipt verified_artifact_id {verified_id!r} has no entry in the handoff manifest"
        )
    if document.get("verified_sha256") != manifest_entry.get("artifact_sha256"):
        raise RegistryV2ArtifactError(
            "receipt verified_sha256 does not match the manifest's declared hash "
            f"for {verified_id!r}"
        )


# --------------------------------------------------------------------------
# 5. Composite validation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistryV2HandoffPackage:
    owner_status_record: Mapping[str, object]
    exact_artifact_authorization: Mapping[str, object]
    handoff_manifest: Mapping[str, object]
    verification_receipt: Mapping[str, object]


def validate_registry_v2_handoff_package(package: RegistryV2HandoffPackage) -> None:
    """Validate all four D-owned registry v2 artifacts and their cross-references.

    Raises :class:`RegistryV2ArtifactError` on the first violation
    found (unlike the readiness check, this validates a package that
    is expected to already be internally consistent -- there is no
    partial-fix workflow for a corrupted handoff package the way there
    is for missing scientific data).
    """

    validate_owner_status_record(package.owner_status_record)
    validate_exact_artifact_authorization(
        package.exact_artifact_authorization,
        owner_status_record=package.owner_status_record,
    )
    validate_handoff_manifest(package.handoff_manifest)
    validate_verification_receipt(
        package.verification_receipt,
        handoff_manifest=package.handoff_manifest,
    )
    authorized_id = package.exact_artifact_authorization.get("target_artifact_id")
    manifest_ids = {
        entry.get("artifact_id") for entry in package.handoff_manifest.get("artifact_identities", [])
    }
    if authorized_id not in manifest_ids:
        raise RegistryV2ArtifactError(
            f"authorized target_artifact_id {authorized_id!r} does not appear in the "
            "handoff manifest's artifact identities"
        )
