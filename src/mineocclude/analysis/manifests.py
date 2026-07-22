"""Canonical hashing and provenance validation for Person B artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mineocclude.contracts.identity import CODE_SHA_LENGTH, SHA256_LENGTH


ANALYSIS_ARTIFACT_SCHEMA_VERSION = "person-b-analysis-artifact-v0.1"


class AnalysisArtifactError(ValueError):
    """Raised when a B-owned artifact cannot be trusted or reproduced."""


def is_hex_digest(value: Any, length: int) -> bool:
    if not isinstance(value, str) or len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize one artifact deterministically and reject non-finite floats."""

    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise AnalysisArtifactError(
            f"Artifact is not canonical-JSON serializable: {error}"
        ) from error


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path | str) -> str:
    """Hash literal file bytes; no parsing or normalization is performed."""

    try:
        payload = Path(path).read_bytes()
    except OSError as error:
        raise AnalysisArtifactError(f"Could not hash {path}: {error}") from error
    return hashlib.sha256(payload).hexdigest()


def seal_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copied artifact carrying a hash over every other field."""

    if not isinstance(payload, Mapping):
        raise AnalysisArtifactError("Artifact payload must be a mapping.")
    sealed = dict(payload)
    if "artifact_hash" in sealed:
        raise AnalysisArtifactError(
            "artifact_hash is computed by seal_artifact and cannot be supplied."
        )
    sealed.setdefault("artifact_schema_version", ANALYSIS_ARTIFACT_SCHEMA_VERSION)
    _validate_base_fields(sealed)
    sealed["artifact_hash"] = sha256_value(sealed)
    return sealed


def _validate_base_fields(document: Mapping[str, Any]) -> None:
    required = (
        "artifact_schema_version",
        "artifact_type",
        "artifact_id",
        "code_sha",
        "config_hash",
        "input_manifest_hash",
    )
    missing = [field for field in required if field not in document]
    if missing:
        raise AnalysisArtifactError(
            "Missing artifact provenance fields: " + ", ".join(missing)
        )
    if document["artifact_schema_version"] != ANALYSIS_ARTIFACT_SCHEMA_VERSION:
        raise AnalysisArtifactError("Analysis artifact schema version mismatch.")
    for field in ("artifact_type", "artifact_id"):
        if not isinstance(document[field], str) or not document[field].strip():
            raise AnalysisArtifactError(f"{field} must be a non-empty string.")
    if not is_hex_digest(document["code_sha"], CODE_SHA_LENGTH):
        raise AnalysisArtifactError("code_sha must be a full hexadecimal Git SHA.")
    for field in ("config_hash", "input_manifest_hash"):
        if not is_hex_digest(document[field], SHA256_LENGTH):
            raise AnalysisArtifactError(f"{field} must be a SHA-256 digest.")


def validate_sealed_artifact(
    document: Mapping[str, Any],
    *,
    expected_type: str | None = None,
) -> None:
    """Validate base provenance and the canonical content hash."""

    if not isinstance(document, Mapping):
        raise AnalysisArtifactError("Artifact must be a mapping.")
    _validate_base_fields(document)
    if expected_type is not None and document["artifact_type"] != expected_type:
        raise AnalysisArtifactError(
            f"Expected artifact_type={expected_type!r}, "
            f"received {document['artifact_type']!r}."
        )
    artifact_hash = document.get("artifact_hash")
    if not is_hex_digest(artifact_hash, SHA256_LENGTH):
        raise AnalysisArtifactError("artifact_hash must be a SHA-256 digest.")
    unhashed = dict(document)
    del unhashed["artifact_hash"]
    if sha256_value(unhashed) != artifact_hash:
        raise AnalysisArtifactError("artifact_hash does not match artifact contents.")


def build_event_manifest(
    manifest_id: str,
    event_ids: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Build the compact fit/validation event manifest required by B-to-A."""

    if not isinstance(manifest_id, str) or not manifest_id.strip():
        raise AnalysisArtifactError("manifest_id must be non-empty.")
    if (
        not isinstance(event_ids, (list, tuple))
        or not event_ids
        or any(not isinstance(value, str) or not value for value in event_ids)
        or len(set(event_ids)) != len(event_ids)
    ):
        raise AnalysisArtifactError("event_ids must be unique non-empty strings.")
    ordered = sorted(event_ids)
    body = {"manifest_id": manifest_id, "event_ids": ordered}
    return {**body, "manifest_hash": sha256_value(body)}


def validate_event_manifest(manifest: Mapping[str, Any]) -> None:
    if not isinstance(manifest, Mapping):
        raise AnalysisArtifactError("Event manifest must be a mapping.")
    required = ("manifest_id", "manifest_hash", "event_ids")
    missing = [field for field in required if field not in manifest]
    if missing:
        raise AnalysisArtifactError(
            "Event manifest is missing: " + ", ".join(missing)
        )
    rebuilt = build_event_manifest(manifest["manifest_id"], manifest["event_ids"])
    if manifest["manifest_hash"] != rebuilt["manifest_hash"]:
        raise AnalysisArtifactError(
            "Event manifest hash does not match its ID and event identities."
        )


def require_disjoint_event_sets(
    fit_manifest: Mapping[str, Any],
    validation_manifest: Mapping[str, Any],
    heldout_events: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> None:
    """Reject fit/validation/held-out overlap before request construction."""

    validate_event_manifest(fit_manifest)
    validate_event_manifest(validation_manifest)
    fit_ids = set(fit_manifest.get("event_ids", []))
    validation_ids = set(validation_manifest.get("event_ids", []))
    if not isinstance(heldout_events, (list, tuple)) or not heldout_events:
        raise AnalysisArtifactError("Held-out events must be a non-empty sequence.")
    heldout_ids: set[str] = set()
    for event in heldout_events:
        if not isinstance(event, Mapping):
            raise AnalysisArtifactError("Held-out event records must be mappings.")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise AnalysisArtifactError("Held-out events require non-empty event_id.")
        if event_id in heldout_ids:
            raise AnalysisArtifactError("Held-out event IDs must be unique.")
        heldout_ids.add(event_id)
    if fit_ids & validation_ids or fit_ids & heldout_ids or validation_ids & heldout_ids:
        raise AnalysisArtifactError(
            "Fit, validation, and held-out event identities must be disjoint."
        )
