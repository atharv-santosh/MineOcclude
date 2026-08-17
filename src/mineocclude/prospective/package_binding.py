"""Binds an execution entrypoint to exactly one qualification package version.

Every runner in this repository used to spell its package as a module-level
literal ending in ``_v0_2``. That made the *implementation* and the *experiment*
one object: pointing the existing tooling at the v0.3 authority was impossible
without editing frozen bytes, and running the tooling unmodified silently
selected the predecessor's ``a1q_*`` / 81xxx inventory -- the units whose Stage-1
already terminated in a scientific FAIL that must never be recollected.

This module separates the two. An entrypoint declares which version it is, and
``resolve_package_binding`` returns the concrete paths and artifact identities
for that version *after* proving, from the package's own bytes, that the
directory really is the version it was asked for.

The proof is by artifact identity and digest, never by directory naming: a
``prospective_development_authority_v0_3`` directory holding the v0.2 authority
is refused, and so is a v0.3 request whose manifest, authority, and stage
binding table do not mutually agree. The stage binding table is the authority's
own (``stage_binding_policy``), so the authorization identity a runner demands
is read out of the frozen authority rather than re-spelled here.

Note that ``require_stage_manifest_binding`` alone cannot close this: it checks a
manifest against *whichever* authority the caller loaded, so a v0.2 authority
paired with its own v0.2 manifest satisfies it. The version tag pinned by the
entrypoint is what makes the pair refusable.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

#: Directory holding every versioned qualification package.
PACKAGE_PARENT_RELATIVE = "docs/status/integration/regime_a_prime_qualification_v0_1"

#: ``v0.3`` -> ``prospective_development_authority_v0_3``.
_PACKAGE_DIRECTORY_TEMPLATE = "prospective_development_authority_v{major}_{minor}"

_VERSION_TAG = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)$")

#: Trailing ``-v0.3`` on an artifact identifier.
_ARTIFACT_VERSION_SUFFIX = re.compile(r"-(v\d+\.\d+)$")

_AUTHORITY_ARTIFACT_ID = "regime-a-prime-prospective-development-authority-{tag}"
_STAGE1_MANIFEST_ARTIFACT_ID = "regime-a-prime-stage1-manifest-{tag}"
_STAGE2_MANIFEST_ARTIFACT_ID = "regime-a-prime-stage2-locked-manifest-{tag}"

# The two identities the frozen authority does not declare for itself. Every
# other identifier below is read out of the authority; these are constructed, so
# they are constructed from the same tag the rest of the binding was proved
# against.
_PROVENANCE_ARTIFACT_ID = "regime-a-prime-prospective-pre-outcome-provenance-{tag}"

#: The Stage-1 gate decision's own identity. Until the v0.3 builder
#: synchronization this was a module-level literal ending in ``v0.2`` inside
#: ``Decision.to_dict``, so a v0.3 Stage-1 decision serialized itself as the
#: predecessor's artifact and the Stage-2 gate compared against that same
#: literal -- meaning a v0.3 Stage-2 would have accepted a v0.2 decision and
#: refused its own. It never reached a live gate because Stage-2 has never been
#: authorized, but it is repaired prospectively for exactly that reason.
_STAGE1_DECISION_ARTIFACT_ID = "regime-a-prime-stage1-decision-{tag}"

#: Repository root, resolved from this file's location (src/mineocclude/prospective).
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class PackageBindingError(PermissionError):
    """An entrypoint could not be bound to the package version it declared.

    Derives from ``PermissionError`` so a mis-binding fails closed on the same
    path as an unmet authorization, rather than being caught as a value error
    and downgraded to a warning somewhere upstream.
    """


@dataclass(frozen=True)
class PackageBinding:
    """The resolved, mutually-verified identity of one qualification package."""

    version_tag: str
    package: Path
    authority_path: Path
    stage1_manifest_path: Path
    stage2_manifest_path: Path
    authority_artifact_id: str
    stage1_manifest_artifact_id: str
    stage2_manifest_artifact_id: str
    authorization_artifact_id: str
    provenance_artifact_id: str
    run_namespace: str
    durable_prefix: str
    authority_status: str

    def unit_ids(self) -> tuple[str, ...]:
        """Stage-1 unit identifiers, in frozen manifest order."""
        manifest = _load(self.stage1_manifest_path)
        return tuple(str(unit["unit_id"]) for unit in manifest["units"])

    def episode_ids(self) -> tuple[int, ...]:
        """Stage-1 episode identifiers, in frozen manifest order."""
        manifest = _load(self.stage1_manifest_path)
        return tuple(int(unit["episode_id"]) for unit in manifest["units"])


def package_directory(version_tag: str, repository: Path = REPOSITORY_ROOT) -> Path:
    """Location of a version's package, without asserting anything about it."""
    match = _VERSION_TAG.match(version_tag)
    if match is None:
        raise PackageBindingError(f"malformed package version tag: {version_tag!r}")
    directory = _PACKAGE_DIRECTORY_TEMPLATE.format(**match.groupdict())
    return repository / PACKAGE_PARENT_RELATIVE / directory


def artifact_version_tag(artifact_id: Any) -> str:
    """Recover ``v0.3`` from any ``...-v0.3`` artifact identifier.

    Lets a component that is handed a manifest -- the unit driver, the evidence
    builder -- label what it emits after the experiment it was actually pointed
    at, instead of after the directory its own source file happens to live in.
    """
    if not isinstance(artifact_id, str):
        raise PackageBindingError(f"artifact identifier is not a string: {artifact_id!r}")
    match = _ARTIFACT_VERSION_SUFFIX.search(artifact_id)
    if match is None:
        raise PackageBindingError(f"artifact identifier carries no version: {artifact_id!r}")
    return match.group(1)


def provenance_artifact_id_for(version_tag: str) -> str:
    """The pre-outcome provenance identity that a package version's receipts carry.

    The frozen authority declares every other identity a runner demands, but not
    this one, so it has to be constructed -- here, once, from the version tag the
    rest of the binding was proved against. Both ``resolve_package_binding`` and
    ``development_workflow.require_stage_manifest_binding`` route through this
    function, so a runner cannot end up demanding a provenance identity that
    disagrees with the experiment it was actually bound to.
    """
    if _VERSION_TAG.match(version_tag) is None:
        raise PackageBindingError(f"malformed package version tag: {version_tag!r}")
    return _PROVENANCE_ARTIFACT_ID.format(tag=version_tag)


def stage1_decision_artifact_id_for(version_tag: str) -> str:
    """The Stage-1 decision identity that a package version's gate emits.

    Constructed here, once, from a version tag -- the same treatment
    :func:`provenance_artifact_id_for` gives the other identity the authority
    does not declare. Both the serializer (``Decision.to_dict``) and the Stage-2
    gate route through this function, so a decision cannot be written under one
    version's identity and then accepted by another version's gate.
    """
    if _VERSION_TAG.match(version_tag) is None:
        raise PackageBindingError(f"malformed package version tag: {version_tag!r}")
    return _STAGE1_DECISION_ARTIFACT_ID.format(tag=version_tag)


def stage1_decision_artifact_id(manifest: Mapping[str, Any]) -> str:
    """The decision identity implied by the Stage-1 manifest actually evaluated.

    The version is recovered from the manifest's own ``artifact_id`` -- the same
    derivation the evidence builder already uses to label the evidence document
    -- so the decision, the evidence and the manifest cannot disagree about
    which experiment produced them. A manifest carrying no versioned identity
    raises rather than defaulting to any version.
    """
    return stage1_decision_artifact_id_for(
        artifact_version_tag((manifest or {}).get("artifact_id")))


def resolve_package_binding(version_tag: str,
                            repository: Path = REPOSITORY_ROOT) -> PackageBinding:
    """Resolve and verify the package for ``version_tag``, or refuse.

    Refuses unless the authority, the Stage-1 manifest, the Stage-2 locked
    manifest, and the authority's own stage binding table all independently
    identify themselves as this version, and the manifest's recorded authority
    digest matches the authority bytes actually on disk.
    """
    if _VERSION_TAG.match(version_tag) is None:
        raise PackageBindingError(f"malformed package version tag: {version_tag!r}")
    repository = repository.resolve()
    package = package_directory(version_tag, repository)
    if not package.is_dir():
        raise PackageBindingError(f"package directory is absent: {package}")

    authority_path = package / "authority_parameters.json"
    stage1_path = package / "stage1_manifest.json"
    stage2_path = package / "stage2_locked_manifest.json"
    for path in (authority_path, stage1_path, stage2_path):
        if not path.is_file():
            raise PackageBindingError(f"package artifact is absent: {path}")

    authority = _load(authority_path)
    stage1 = _load(stage1_path)
    stage2 = _load(stage2_path)

    # 1. Each artifact names its own version. A package directory whose name says
    #    v0.3 but whose bytes say v0.2 dies here.
    _require_identity(authority, _AUTHORITY_ARTIFACT_ID, version_tag, "authority")
    _require_identity(stage1, _STAGE1_MANIFEST_ARTIFACT_ID, version_tag, "Stage-1 manifest")
    _require_identity(stage2, _STAGE2_MANIFEST_ARTIFACT_ID, version_tag, "Stage-2 locked manifest")

    # 2. The manifest points back at this authority, by path and by digest. A
    #    manifest carrying a stale authority digest cannot bind a runner.
    declared = stage1.get("authority_binding")
    if not isinstance(declared, Mapping):
        raise PackageBindingError(f"{version_tag} Stage-1 manifest declares no authority binding")
    expected_relative = authority_path.relative_to(repository).as_posix()
    if declared.get("path") != expected_relative:
        raise PackageBindingError(
            f"{version_tag} Stage-1 manifest binds authority {declared.get('path')!r}, "
            f"expected {expected_relative!r}")
    observed = hashlib.sha256(authority_path.read_bytes()).hexdigest()
    if declared.get("sha256") != observed:
        raise PackageBindingError(
            f"{version_tag} Stage-1 manifest authority digest does not match the authority bytes")

    # 3. The authority's own stage table agrees, and supplies the authorization
    #    identity so no runner re-spells it as a literal.
    stages = (authority.get("stage_binding_policy") or {}).get("stages")
    if not isinstance(stages, Mapping) or not isinstance(stages.get("stage1-capture"), Mapping):
        raise PackageBindingError(f"{version_tag} authority declares no stage1-capture binding")
    stage1_binding = stages["stage1-capture"]
    stage1_relative = stage1_path.relative_to(repository).as_posix()
    for field, expected in (("manifest_artifact_id", stage1["artifact_id"]),
                            ("manifest_relative_path", stage1_relative),
                            ("run_namespace", stage1["run_namespace"])):
        if stage1_binding.get(field) != expected:
            raise PackageBindingError(
                f"{version_tag} stage1-capture binding {field} is "
                f"{stage1_binding.get(field)!r}, expected {expected!r}")
    authorization_artifact_id = stage1_binding.get("authorization_artifact_id")
    if artifact_version_tag(authorization_artifact_id) != version_tag:
        raise PackageBindingError(
            f"{version_tag} stage1-capture authorization identity is "
            f"{authorization_artifact_id!r}, which is not this version")

    # 4. The unfrozen, unauthorized collection baseline. A package that already
    #    claims authorization cannot be bound by a runner that is about to mint
    #    one, which is what keeps an authorization from authorizing itself.
    for field in ("STAGE_1_COLLECTION_AUTHORIZED", "STAGE_2_COLLECTION_AUTHORIZED",
                  "confirmatory_collection_authorized"):
        if authority.get(field) is not False:
            raise PackageBindingError(
                f"{version_tag} authority does not carry the unauthorized baseline: {field}")

    return PackageBinding(
        version_tag=version_tag,
        package=package,
        authority_path=authority_path,
        stage1_manifest_path=stage1_path,
        stage2_manifest_path=stage2_path,
        authority_artifact_id=str(authority["artifact_id"]),
        stage1_manifest_artifact_id=str(stage1["artifact_id"]),
        stage2_manifest_artifact_id=str(stage2["artifact_id"]),
        authorization_artifact_id=str(authorization_artifact_id),
        provenance_artifact_id=provenance_artifact_id_for(version_tag),
        run_namespace=str(stage1["run_namespace"]),
        durable_prefix=str(stage1["durable_prefix"]),
        authority_status=str(authority["status"]),
    )


def _require_identity(document: Mapping[str, Any], template: str,
                      version_tag: str, label: str) -> None:
    expected = template.format(tag=version_tag)
    if document.get("artifact_id") != expected:
        raise PackageBindingError(
            f"{label} identifies itself as {document.get('artifact_id')!r}, "
            f"but {expected!r} was required")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())
