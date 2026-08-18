#!/usr/bin/env python3
"""Admitting an already-completed raw capture into a successor processing campaign.

The category error this closes
=============================

Five independent places required a capture receipt's ``source_commit_sha`` to
equal the *currently executing* campaign's commit:
:meth:`DurableController._valid_receipt` and :meth:`DurableController.completed`,
the per-unit structural probe, the unit-1 checkpoint's capture half, and the
cohort evidence builder's unit binding. Each was written as a homogeneity proxy:
"one campaign, one freeze, therefore one commit". The proxy is correct for a
campaign that never needs a successor freeze, and it silently becomes a
correctness bug the moment a *downstream* defect requires one -- because it then
declares a valid, durable, physically irreproducible raw capture invalid, and the
controller's response is to recapture it.

The authority decision separates the two facts those checks had conflated:

* **capture provenance** is historical. A completed capture is permanently bound
  to the commit, manifest, authority, authorization, provenance receipt and
  apparatus it was actually taken under. Nothing here rewrites any of that.
* **processing provenance** is current. Every derived artifact -- activation,
  readout, evidence, decision -- binds the successor commit and closure that
  produced it.

Admission is the bridge, and it is not a lineage claim. Belonging to a declared
commit lineage proves nothing about a capture apparatus; a single edit inside a
lineage can change what a camera records. What admission requires instead is
equality of the *capture-critical closure*
(:mod:`mineocclude.prospective.capture_closure`): every component that could have
changed what the capture physically recorded, or the scientific identity it
recorded itself under. Full-repository commits may differ; capture-determining
components may not.

Fail-closed, and closed in the strict direction
===============================================

Every check here refuses rather than warns, and the module never repairs, relabels
or rewrites a capture receipt -- it only reads them. A capture whose closure
differs is *not* recollected automatically: :class:`CaptureAdmissionError`
propagates so the pipeline stops for authority review, because silently
recapturing would destroy the evidence that the apparatus had changed.

Nothing in this module may consult a scientific outcome. Admission is decided by
identity, provenance and closure equality alone, so it cannot become
outcome-adaptive.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mineocclude.prospective.capture_closure import (
    CAPTURE_CRITICAL_APPARATUS_FILES,
    CAPTURE_CRITICAL_APPARATUS_OBSERVATIONS,
    CAPTURE_CRITICAL_NON_SOURCE_RUNTIME_IDENTITIES,
    CaptureClosureError,
    capture_critical_closure_at,
    capture_critical_paths,
    cross_check_recorded_file_digests,
    derive_capture_critical_symbols,
    git_reader,
)

#: Filename of the governing authority document, inside the package directory.
#: Follows the ``stage2_decision_authority.json`` precedent: a Stage-2-only
#: governance artifact sitting beside ``authority_parameters.json`` rather than
#: inside it, because the completed Stage-1 PASS is welded to that file's bytes.
CAPTURE_PROVENANCE_AUTHORITY_FILENAME = "stage2_capture_processing_provenance_authority.json"

_CAPTURE_PROVENANCE_AUTHORITY_ARTIFACT_ID = (
    "regime-a-prime-stage2-capture-processing-provenance-authority-{tag}")

SCHEMA_VERSION = "1.0"


class _UnboundLegacyIdentity:
    """Explicit marker for a caller with no authority-derived legacy identity.

    The completed historical pilot entrypoints predate the Stage-2 authority and
    have no ``layout_id``/``episode_id`` pair to derive one from. Spelled as an
    object rather than ``None`` so it cannot be produced by a missing key or a JSON
    round trip, matching the sentinel discipline in
    :mod:`mineocclude.prospective.activation_binding`.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "LEGACY_CAPTURE_TRAJECTORY_NOT_AUTHORITY_BOUND"


#: See :class:`_UnboundLegacyIdentity`. Grep for this name to find every
#: extraction whose legacy capture identity is not authority-derived.
LEGACY_CAPTURE_TRAJECTORY_NOT_AUTHORITY_BOUND = _UnboundLegacyIdentity()


class CaptureAdmissionError(RuntimeError):
    """A completed capture may not be admitted to this processing campaign.

    Deliberately not an ``EvidenceError``: it is an operational refusal that stops
    the pipeline for authority review, and it is never a scientific verdict.
    """


def capture_provenance_authority_artifact_id_for(version_tag: str) -> str:
    """``v0.4`` -> the capture/processing provenance authority's identity."""
    from mineocclude.prospective.package_binding import artifact_version_tag

    # Round-trips through the shared validator so a malformed tag fails here
    # rather than producing a plausible-looking identifier.
    identifier = _CAPTURE_PROVENANCE_AUTHORITY_ARTIFACT_ID.format(tag=version_tag)
    if artifact_version_tag(identifier) != version_tag:
        raise CaptureAdmissionError(f"malformed package version tag: {version_tag!r}")
    return identifier


def capture_provenance_authority_path(package: Path) -> Path:
    return Path(package) / CAPTURE_PROVENANCE_AUTHORITY_FILENAME


def load_capture_provenance_authority(package: Path, *, version_tag: str,
                                      authority_path: Path,
                                      repository: Path) -> tuple[dict[str, Any], str]:
    """Load and verify the governing authority document. Returns ``(doc, sha256)``.

    Verified in both directions, exactly as the Stage-2 decision authority is: the
    document must name this package version and must extend the bytes of
    ``authority_parameters.json`` actually on disk, so neither can be swapped for
    another package's.
    """
    path = capture_provenance_authority_path(package)
    if not path.is_file():
        raise CaptureAdmissionError(
            f"capture/processing provenance authority is absent: {path}")
    document = json.loads(path.read_bytes())
    expected_id = capture_provenance_authority_artifact_id_for(version_tag)
    if document.get("artifact_id") != expected_id:
        raise CaptureAdmissionError(
            f"capture/processing provenance authority identity is "
            f"{document.get('artifact_id')!r}, expected {expected_id!r}")
    extends = document.get("extends_authority")
    if not isinstance(extends, Mapping):
        raise CaptureAdmissionError(
            "capture/processing provenance authority extends no authority")
    relative = Path(authority_path).resolve().relative_to(Path(repository).resolve()).as_posix()
    observed = hashlib.sha256(Path(authority_path).read_bytes()).hexdigest()
    if extends.get("path") != relative or extends.get("sha256") != observed:
        raise CaptureAdmissionError(
            "capture/processing provenance authority is bound to different authority bytes")
    for field in ("STAGE_2_COLLECTION_AUTHORIZED", "confirmatory_collection_authorized",
                  "depends_on_scientific_outcome"):
        if document.get(field) is not False:
            raise CaptureAdmissionError(
                f"capture/processing provenance authority does not carry the "
                f"unauthorized/non-adaptive baseline: {field}")
    return document, hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Typed capture identity
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TypedCaptureIdentity:
    """The four distinct identities one Stage-2 capture carries.

    They are different *types*, not spellings of one value, and the frozen design
    requires correspondence between them -- never string equality. Conflating the
    first two is the defect this type exists to make unrepresentable.
    """

    #: ``layout_01_ep86001``. The raw capture package's own trajectory identity,
    #: defined by ``mineocclude.data.align`` as ``"<layout_id>_ep<episode_id>"``.
    #: It names a *rendered episode*, and predates Stage-2 entirely.
    legacy_capture_trajectory_id: str
    #: ``a2y_t01``. One of the 25 fold x phase Stage-2 scientific trajectories.
    scientific_trajectory_id: str
    #: ``a2y_t01_wall``. One of the 50 trajectory x scene Stage-2 capture units.
    scientific_capture_unit_id: str
    #: ``86001``. The WALL episode; its NO_WALL partner is offset by +500.
    episode_id: int
    #: ``WALL`` or ``NO_WALL``.
    scene: str
    #: ``layout_01``. From the frozen authority's apparatus block.
    layout_id: str

    def to_dict(self) -> dict[str, Any]:
        return dict(sorted(asdict(self).items()))


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureAdmissionError(f"{label} is absent or blank")
    return value


def resolve_typed_capture_identity(authority: Mapping[str, Any],
                                   unit: Mapping[str, Any]) -> TypedCaptureIdentity:
    """Derive all four identities for one capture unit, or refuse.

    The legacy identity is *derived* from the frozen authority's ``layout_id`` and
    the manifest unit's ``episode_id`` -- the same rule ``align`` froze -- rather
    than read out of the capture package. That direction matters: it means the
    package's self-declared identity can be *checked* against authority instead of
    being trusted, so a capture package belonging to another episode cannot
    authenticate itself.
    """
    apparatus = authority.get("apparatus")
    if not isinstance(apparatus, Mapping):
        raise CaptureAdmissionError("frozen authority declares no apparatus block")
    layout_id = _text(apparatus.get("layout_id"), "authority apparatus layout_id")
    scientific_trajectory_id = _text(unit.get("trajectory_id"),
                                    "capture unit trajectory_id")
    unit_id = _text(unit.get("unit_id"), "capture unit unit_id")
    scene = _text(unit.get("scene"), "capture unit scene")
    if scene not in ("WALL", "NO_WALL"):
        raise CaptureAdmissionError(f"capture unit scene is outside the design: {scene!r}")
    episode = unit.get("episode_id")
    if isinstance(episode, bool) or not isinstance(episode, int):
        raise CaptureAdmissionError("capture unit episode_id is not an integer")
    if scientific_trajectory_id == f"{layout_id}_ep{episode}":
        # The two namespaces must stay distinguishable. Equality would mean an
        # ambiguous mapping in which a legacy-identity check and a scientific
        # identity check could not be told apart.
        raise CaptureAdmissionError(
            "scientific trajectory identity collides with the legacy capture "
            "identity, so the two namespaces are ambiguous")
    return TypedCaptureIdentity(
        legacy_capture_trajectory_id=f"{layout_id}_ep{episode}",
        scientific_trajectory_id=scientific_trajectory_id,
        scientific_capture_unit_id=unit_id,
        episode_id=episode,
        scene=scene,
        layout_id=layout_id)


def verify_capture_package_identity(document: Mapping[str, Any],
                                    identity: TypedCaptureIdentity, *,
                                    label: str = "capture package") -> None:
    """Refuse a raw capture package that is not this unit's rendered episode.

    Checks the legacy identity, the episode and the layout independently. Each has
    its own diagnosis: a package for the right trajectory but the wrong episode,
    and one for the right episode but the wrong trajectory, are different faults
    and must not collapse into one boolean.
    """
    if not isinstance(document, Mapping):
        raise CaptureAdmissionError(f"{label} is not a mapping")
    declared = document.get("trajectory_id")
    if declared is None:
        raise CaptureAdmissionError(
            f"{label} declares no legacy capture trajectory identity")
    if declared != identity.legacy_capture_trajectory_id:
        raise CaptureAdmissionError(
            f"{label} legacy capture trajectory identity is {declared!r}, not "
            f"{identity.legacy_capture_trajectory_id!r}")
    episode = document.get("episode_id")
    if episode is None:
        raise CaptureAdmissionError(f"{label} declares no episode identity")
    if int(episode) != identity.episode_id:
        raise CaptureAdmissionError(
            f"{label} episode is {episode!r}, not {identity.episode_id!r}")
    layout = document.get("layout_id")
    if layout is not None and layout != identity.layout_id:
        raise CaptureAdmissionError(
            f"{label} layout is {layout!r}, not {identity.layout_id!r}")
    # The legacy identity must be exactly the frozen composition of the two, so a
    # package cannot carry a self-consistent but unauthorized spelling.
    if declared != f"{layout or identity.layout_id}_ep{episode}":
        raise CaptureAdmissionError(
            f"{label} legacy identity {declared!r} is not the frozen composition "
            f"of its own layout and episode")


def verify_visibility_rows_scientific_identity(rows: Sequence[Mapping[str, Any]],
                                               identity: TypedCaptureIdentity, *,
                                               label: str = "visibility evidence") -> int:
    """Refuse Stage-2 visibility rows that are not this scientific trajectory's.

    The counterpart to :func:`verify_capture_package_identity`, on the other side
    of the namespace boundary: these rows are Stage-2 artifacts and carry the
    *scientific* trajectory identity. Both checks run; neither replaces the other.
    """
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise CaptureAdmissionError(f"{label} is not a sequence of rows")
    observed: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise CaptureAdmissionError(f"{label} contains a malformed row")
        value = row.get("trajectory_id")
        if value is None:
            raise CaptureAdmissionError(
                f"{label} contains a row with no scientific trajectory identity")
        observed.add(str(value))
    if not observed:
        raise CaptureAdmissionError(f"{label} is empty")
    if observed != {identity.scientific_trajectory_id}:
        raise CaptureAdmissionError(
            f"{label} carries scientific trajectory identities {sorted(observed)}, "
            f"not {{{identity.scientific_trajectory_id!r}}}")
    return len(rows)


# ---------------------------------------------------------------------------
# Capture compatibility
# ---------------------------------------------------------------------------

#: Receipt fields that are capture-time facts about the scientific DESIGN, and so
#: must equal the campaign's values for any admitted capture regardless of which
#: commit took it. ``source_commit_sha`` is deliberately absent: that is the
#: historical fact the split exists to stop comparing against successor HEAD.
DESIGN_BINDING_FIELDS = (
    "unit_id",
    "status",
    "classification",
    "confirmatory_membership",
    "manifest_sha256",
    "authority_sha256",
    "scientific_run_id",
    "durable_uri",
)


def _receipt_capture_commit(receipt: Mapping[str, Any]) -> str:
    commit = receipt.get("source_commit_sha")
    if not isinstance(commit, str) or len(commit) != 40 \
            or any(character not in "0123456789abcdef" for character in commit):
        raise CaptureAdmissionError(
            f"capture receipt declares no valid capture source commit: {commit!r}")
    runtime = receipt.get("runtime_provenance_receipt")
    if not isinstance(runtime, Mapping):
        raise CaptureAdmissionError("capture receipt carries no runtime provenance receipt")
    # The receipt states the commit twice, in two independently written blocks.
    # They must agree, or the receipt cannot say what took the capture.
    if runtime.get("head") != commit:
        raise CaptureAdmissionError(
            f"capture receipt runtime provenance head {runtime.get('head')!r} "
            f"disagrees with its capture source commit {commit!r}")
    return commit


def verify_capture_runtime_apparatus(receipt: Mapping[str, Any],
                                     expected: Mapping[str, Any], *,
                                     label: str) -> dict[str, Any]:
    """Refuse a capture taken on a different physical apparatus.

    Source equality is necessary and not sufficient: identical bytes under a
    different JDK, Mesa, Xvfb, Minecraft/Fabric build, installed mod or detector
    configuration is a different measuring instrument. Camera pose and frame
    geometry are checked for the same reason.
    """
    runtime = receipt.get("runtime_provenance_receipt")
    if not isinstance(runtime, Mapping):
        raise CaptureAdmissionError(f"{label}: receipt carries no runtime provenance")
    differing: list[str] = []
    observed: dict[str, Any] = {}
    for field in CAPTURE_CRITICAL_NON_SOURCE_RUNTIME_IDENTITIES:
        observed[field] = runtime.get(field)
        if field in expected and runtime.get(field) != expected[field]:
            differing.append(field)
    files = runtime.get("critical_file_sha256")
    if not isinstance(files, Mapping):
        raise CaptureAdmissionError(f"{label}: receipt carries no apparatus file digests")
    expected_files = expected.get("critical_file_sha256") or {}
    for field in CAPTURE_CRITICAL_APPARATUS_FILES:
        if field not in files:
            differing.append(f"critical_file_sha256.{field}")
            continue
        observed[f"critical_file_sha256.{field}"] = files[field]
        if field in expected_files and files[field] != expected_files[field]:
            differing.append(f"critical_file_sha256.{field}")
    apparatus = runtime.get("captured_apparatus_receipt")
    if not isinstance(apparatus, Mapping):
        raise CaptureAdmissionError(f"{label}: receipt carries no captured apparatus receipt")
    expected_apparatus = expected.get("captured_apparatus") or {}
    for field in CAPTURE_CRITICAL_APPARATUS_OBSERVATIONS:
        if field not in apparatus:
            differing.append(f"captured_apparatus.{field}")
            continue
        observed[f"captured_apparatus.{field}"] = apparatus[field]
        if field in expected_apparatus and apparatus[field] != expected_apparatus[field]:
            differing.append(f"captured_apparatus.{field}")
    if differing:
        raise CaptureAdmissionError(
            f"{label}: capture apparatus differs from the successor campaign's on "
            f"{sorted(set(differing))}; this is a different measuring instrument "
            f"and the capture may not be admitted")
    return observed


def admit_completed_capture(
        *, unit: Mapping[str, Any], receipt: Mapping[str, Any],
        authority: Mapping[str, Any], manifest_sha256: str, authority_sha256: str,
        scientific_run_id: str, durable_uri: str,
        expected_capture_critical_closure_sha256: str,
        processing_source_commit_sha: str,
        expected_runtime_apparatus: Mapping[str, Any] | None = None,
        repository: Path,
        capture_provenance_authority_sha256: str) -> dict[str, Any]:
    """Decide whether one completed raw capture may be processed here.

    Establishes, in order, and refusing at the first failure:

    1. the receipt's scientific DESIGN bindings equal this campaign's;
    2. the receipt names a valid capture source commit, consistently, in both
       blocks that record it;
    3. that commit's capture-critical closure equals the cohort's authorized one;
    4. the commit's Git bytes are the bytes the capture actually measured, proved
       against the per-path digests the receipt itself recorded;
    5. the physical apparatus matches;
    6. no provenance laundering: the record states the capture and processing
       commits separately and never claims they are equal when they are not.

    Returns the admission record. Writes nothing and mutates nothing.
    """
    unit_id = str(unit.get("unit_id"))
    identity = resolve_typed_capture_identity(authority, unit)

    expected_design = {
        "unit_id": unit.get("unit_id"),
        "status": "COMPLETE_VALIDATED_DURABLE",
        "classification": "DEVELOPMENT_ONLY",
        "confirmatory_membership": False,
        "manifest_sha256": manifest_sha256,
        "authority_sha256": authority_sha256,
        "scientific_run_id": scientific_run_id,
        "durable_uri": durable_uri,
    }
    mismatched = sorted(key for key in DESIGN_BINDING_FIELDS
                        if receipt.get(key) != expected_design[key])
    if mismatched:
        raise CaptureAdmissionError(
            f"{unit_id}: capture receipt does not bind this campaign's scientific "
            f"design; mismatched {mismatched}")

    capture_commit = _receipt_capture_commit(receipt)

    try:
        symbols = derive_capture_critical_symbols(git_reader(capture_commit, repository),
                                                  repository=repository)
        observed_closure, _ = capture_critical_closure_at(capture_commit,
                                                          repository=repository)
    except CaptureClosureError as exc:
        raise CaptureAdmissionError(
            f"{unit_id}: capture-critical closure could not be derived at capture "
            f"commit {capture_commit}: {exc}") from exc
    if observed_closure != expected_capture_critical_closure_sha256:
        raise CaptureAdmissionError(
            f"{unit_id}: capture-critical closure at capture commit {capture_commit} "
            f"is {observed_closure}, not the cohort's authorized "
            f"{expected_capture_critical_closure_sha256}. The capture apparatus is "
            f"NOT equivalent; reuse is forbidden and this requires authority review "
            f"rather than automatic recollection.")

    runtime = receipt.get("runtime_provenance_receipt") or {}
    recorded = runtime.get("runtime_source_sha256")
    cross = cross_check_recorded_file_digests(
        recorded if isinstance(recorded, Mapping) else {}, capture_commit,
        paths=capture_critical_paths(symbols), repository=repository)
    if not cross["recorded_file_digests_agree_with_commit"]:
        raise CaptureAdmissionError(
            f"{unit_id}: the capture-critical bytes at commit {capture_commit} are not "
            f"the bytes this capture recorded measuring; absent="
            f"{cross['paths_absent_from_receipt_or_commit']} "
            f"divergent={cross['paths_whose_bytes_disagree']}")

    apparatus = verify_capture_runtime_apparatus(
        receipt, expected_runtime_apparatus or {}, label=unit_id)

    durable_objects = receipt.get("durable_objects")
    if not isinstance(durable_objects, Mapping) or not durable_objects:
        raise CaptureAdmissionError(f"{unit_id}: capture receipt declares no durable objects")
    inventory_digest = hashlib.sha256(json.dumps(
        dict(sorted(durable_objects.items())), sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()

    record = {
        "schema_version": SCHEMA_VERSION,
        "classification": "OPERATIONAL_DERIVED_VERIFICATION_NOT_A_CAPTURE_RECEIPT",
        "capture_compatibility": "PASS",
        "unit_id": unit_id,
        "typed_capture_identity": identity.to_dict(),
        # ---- historical capture provenance: never rewritten -----------------
        "capture_source_commit": capture_commit,
        "capture_critical_closure_sha256": observed_closure,
        "capture_manifest_sha256": receipt.get("manifest_sha256"),
        "capture_authority_sha256": receipt.get("authority_sha256"),
        "capture_receipt_recorded_bytes_agree_with_capture_commit": True,
        "capture_critical_paths_verified": cross["capture_critical_paths_checked"],
        "capture_runtime_apparatus": dict(sorted(apparatus.items())),
        "durable_uri": receipt.get("durable_uri"),
        "durable_object_count": len(durable_objects),
        "durable_object_inventory_sha256": inventory_digest,
        "remote_checksum_manifest_sha256": receipt.get("remote_checksum_manifest_sha256"),
        "scene": identity.scene,
        "episode_id": identity.episode_id,
        "seed": unit.get("seed"),
        "noise_seed": unit.get("noise_seed"),
        "expected_path_sha256": unit.get("expected_path_sha256"),
        # ---- successor processing provenance: separate, and current ----------
        "processing_source_commit": processing_source_commit_sha,
        "expected_capture_critical_closure_sha256":
            expected_capture_critical_closure_sha256,
        "capture_processing_provenance_authority_sha256":
            capture_provenance_authority_sha256,
        # ---- the anti-laundering statement, recorded explicitly --------------
        "capture_and_processing_commits_equal":
            capture_commit == processing_source_commit_sha,
        "capture_taken_under_processing_commit":
            capture_commit == processing_source_commit_sha,
        "scientific_outcome_observed": False,
    }
    return record


def require_no_provenance_laundering(record: Mapping[str, Any]) -> None:
    """Refuse a derived record that claims a capture it did not take.

    The one claim a downstream processor must never be able to make is that a
    capture was produced by the successor source. Both statements are recorded, so
    the check is an equality of facts rather than a trusted boolean.
    """
    capture = record.get("capture_source_commit")
    processing = record.get("processing_source_commit")
    if not isinstance(capture, str) or not isinstance(processing, str):
        raise CaptureAdmissionError(
            "derived record does not state both capture and processing source commits")
    for field in ("capture_and_processing_commits_equal",
                  "capture_taken_under_processing_commit"):
        claimed = record.get(field)
        if claimed is not (capture == processing):
            raise CaptureAdmissionError(
                f"derived record claims {field}={claimed!r} while capture commit "
                f"{capture} and processing commit {processing} say otherwise; this is "
                f"provenance laundering and is refused")


def require_homogeneous_capture_closure(records: Sequence[Mapping[str, Any]]) -> str:
    """The cohort rule: one capture apparatus, however many commits took it.

    Returns the single authorized closure digest. Full-repository capture commits
    may legitimately differ across the cohort -- and remain visible in the evidence
    -- but a cohort spanning two capture apparatuses is not one experiment.
    """
    if not records:
        raise CaptureAdmissionError("cohort carries no admitted captures")
    closures = {str(record.get("capture_critical_closure_sha256")) for record in records}
    if len(closures) != 1:
        by_closure: dict[str, list[str]] = {}
        for record in records:
            by_closure.setdefault(
                str(record.get("capture_critical_closure_sha256")), []).append(
                    str(record.get("unit_id")))
        raise CaptureAdmissionError(
            "cohort spans more than one capture-critical closure, so its captures "
            f"were not taken on one apparatus: "
            f"{ {key: sorted(value) for key, value in sorted(by_closure.items())} }")
    closure = closures.pop()
    if len(closure) != 64:
        raise CaptureAdmissionError("cohort capture-critical closure is malformed")
    return closure


# ---------------------------------------------------------------------------
# The admission context
# ---------------------------------------------------------------------------

def expected_capture_apparatus(authority: Mapping[str, Any]) -> dict[str, Any]:
    """The frozen apparatus every admitted capture must have been taken on.

    Read out of frozen authority rather than out of any capture's receipt, so both
    the predecessor unit and units 2-50 are compared against the same pin instead
    of against each other -- a cohort that drifted together would otherwise agree.

    The textual runtime identities come from
    ``runtime_identity_policy.required_fields``, which is the probe-comparable pin
    set. ``apparatus.java`` is deliberately *not* used: it holds the marketing
    spelling ``Amazon Corretto 17.0.20.8.1``, which the runtime never emits, and
    the authority documents that in ``java_identity_pin_derivation``. Comparing
    against it would refuse every genuine capture.
    """
    policy = authority.get("runtime_identity_policy")
    if not isinstance(policy, Mapping):
        raise CaptureAdmissionError("frozen authority declares no runtime identity policy")
    required = policy.get("required_fields")
    files = policy.get("critical_file_sha256")
    if not isinstance(required, Mapping) or not isinstance(files, Mapping):
        raise CaptureAdmissionError(
            "frozen authority runtime identity policy is incomplete")
    apparatus = authority.get("apparatus")
    observation = authority.get("apparatus_observation_policy")
    if not isinstance(apparatus, Mapping) or not isinstance(observation, Mapping):
        raise CaptureAdmissionError(
            "frozen authority declares no apparatus or apparatus observation policy")
    expected: dict[str, Any] = {
        field: required[field]
        for field in CAPTURE_CRITICAL_NON_SOURCE_RUNTIME_IDENTITIES
        if field in required
    }
    missing = [field for field in CAPTURE_CRITICAL_NON_SOURCE_RUNTIME_IDENTITIES
               if field not in expected]
    if missing:
        raise CaptureAdmissionError(
            f"frozen authority pins no value for capture-critical runtime "
            f"identities {missing}")
    expected["critical_file_sha256"] = {name: files[name]
                                        for name in CAPTURE_CRITICAL_APPARATUS_FILES
                                        if name in files}
    absent = [name for name in CAPTURE_CRITICAL_APPARATUS_FILES
              if name not in expected["critical_file_sha256"]]
    if absent:
        raise CaptureAdmissionError(
            f"frozen authority pins no digest for apparatus files {absent}")
    captured: dict[str, Any] = {}
    for field in CAPTURE_CRITICAL_APPARATUS_OBSERVATIONS:
        if field in observation:
            captured[field] = observation[field]
        elif field in apparatus:
            captured[field] = apparatus[field]
        else:
            raise CaptureAdmissionError(
                f"frozen authority declares no apparatus observation for {field!r}")
    expected["captured_apparatus"] = captured
    return expected


@dataclass(frozen=True)
class CaptureAdmissionContext:
    """Everything needed to decide whether a completed capture may be processed.

    Constructed once per campaign and passed to every consumer, so the per-unit
    structural probe, the unit-1 checkpoint, the controller's reuse test and the
    cohort evidence builder cannot end up applying four slightly different
    admission rules -- which is how the original homogeneity proxy came to be
    duplicated in five places.
    """

    authority: Mapping[str, Any]
    manifest_sha256: str
    authority_sha256: str
    scientific_run_id: str
    durable_prefix: str
    expected_capture_critical_closure_sha256: str
    processing_source_commit_sha: str
    capture_provenance_authority_sha256: str
    repository: Path
    expected_runtime_apparatus: Mapping[str, Any]

    def durable_uri_for(self, unit_id: str) -> str:
        return self.durable_prefix.rstrip("/") + "/" + str(unit_id)

    def admit(self, unit: Mapping[str, Any],
              receipt: Mapping[str, Any]) -> dict[str, Any]:
        """Admit one completed capture, or raise :class:`CaptureAdmissionError`."""
        record = admit_completed_capture(
            unit=unit, receipt=receipt, authority=self.authority,
            manifest_sha256=self.manifest_sha256,
            authority_sha256=self.authority_sha256,
            scientific_run_id=self.scientific_run_id,
            durable_uri=self.durable_uri_for(unit.get("unit_id")),
            expected_capture_critical_closure_sha256=(
                self.expected_capture_critical_closure_sha256),
            processing_source_commit_sha=self.processing_source_commit_sha,
            expected_runtime_apparatus=self.expected_runtime_apparatus,
            repository=self.repository,
            capture_provenance_authority_sha256=(
                self.capture_provenance_authority_sha256))
        require_no_provenance_laundering(record)
        return record


def build_capture_admission_context(
        *, authority: Mapping[str, Any], manifest: Mapping[str, Any],
        manifest_sha256: str, authority_sha256: str, scientific_run_id: str,
        processing_source_commit_sha: str,
        capture_provenance_authority_sha256: str,
        repository: Path,
        expected_capture_critical_closure_sha256: str | None = None,
        ) -> CaptureAdmissionContext:
    """Build the campaign's admission context.

    ``expected_capture_critical_closure_sha256`` defaults to the closure of the
    source actually executing, which is the correct cohort reference: the campaign
    admits exactly those captures whose apparatus equals its own.
    """
    if expected_capture_critical_closure_sha256 is None:
        from mineocclude.prospective.capture_closure import worktree_reader

        expected_capture_critical_closure_sha256, _ = capture_critical_closure_at(
            worktree_reader(repository), repository=repository)
    return CaptureAdmissionContext(
        authority=authority,
        manifest_sha256=manifest_sha256,
        authority_sha256=authority_sha256,
        scientific_run_id=scientific_run_id,
        durable_prefix=str(manifest["durable_prefix"]),
        expected_capture_critical_closure_sha256=(
            expected_capture_critical_closure_sha256),
        processing_source_commit_sha=processing_source_commit_sha,
        capture_provenance_authority_sha256=capture_provenance_authority_sha256,
        repository=Path(repository),
        expected_runtime_apparatus=expected_capture_apparatus(authority))


def verify_processing_provenance_binding(provenance: Mapping[str, Any], *,
                                        package: Path, version_tag: str,
                                        authority_path: Path, repository: Path,
                                        ) -> dict[str, Any]:
    """Verify a successor provenance receipt actually binds this governance.

    The consumer half of the binding minted by
    ``generate_receipts.capture_processing_provenance_bindings``. Deliberately lives
    here rather than inside ``require_preoutcome_provenance``: that verifier is a
    capture-time admission check and is itself inside the capture-critical closure,
    so adding to it would change the capture apparatus and -- correctly, by the rule
    -- make every completed capture inadmissible. The governance check is downstream
    of capture, so it belongs in a downstream module.

    Establishes that the receipt names the authority document that exists on disk, by
    identity and digest; that the closure it authorizes is the one this source
    actually derives; and that the capture and processing closures it records are two
    different values, which is the shape of the split rather than an accident.
    """
    document, authority_sha256 = load_capture_provenance_authority(
        package, version_tag=version_tag, authority_path=authority_path,
        repository=repository)
    if provenance.get("capture_processing_provenance_authority_artifact_id") \
            != document["artifact_id"]:
        raise CaptureAdmissionError(
            "provenance receipt does not name the capture/processing provenance "
            f"authority: {provenance.get('capture_processing_provenance_authority_artifact_id')!r}")
    if provenance.get("capture_processing_provenance_authority_sha256") != authority_sha256:
        raise CaptureAdmissionError(
            "provenance receipt binds a different capture/processing provenance "
            "authority than the bytes on disk")
    from mineocclude.prospective.capture_closure import (
        capture_critical_closure_at, worktree_reader,
    )

    derived, _ = capture_critical_closure_at(worktree_reader(repository),
                                             repository=repository)
    recorded = provenance.get("authorized_capture_critical_closure_sha256")
    if recorded != derived:
        raise CaptureAdmissionError(
            f"provenance receipt authorizes capture-critical closure {recorded!r}, "
            f"but this source derives {derived!r}")
    processing = provenance.get("runtime_critical_source_closure_sha256")
    if not isinstance(processing, str) or len(processing) != 64:
        raise CaptureAdmissionError(
            "provenance receipt records no processing runtime-critical closure")
    if processing == derived:
        # Not a paranoid check: if the two closures ever computed to the same value
        # the split would be silently inert, and every downstream repair would once
        # again invalidate raw captures.
        raise CaptureAdmissionError(
            "the capture-critical and processing closures are identical, so the "
            "provenance split is not actually in force")
    return {
        "capture_processing_provenance_authority_sha256": authority_sha256,
        "authorized_capture_critical_closure_sha256": derived,
        "processing_runtime_critical_closure_sha256": processing,
        "closures_are_distinct": True,
    }


__all__ = [
    "CAPTURE_PROVENANCE_AUTHORITY_FILENAME",
    "verify_processing_provenance_binding",
    "expected_capture_apparatus",
    "build_capture_admission_context",
    "CaptureAdmissionContext",
    "LEGACY_CAPTURE_TRAJECTORY_NOT_AUTHORITY_BOUND",
    "DESIGN_BINDING_FIELDS",
    "SCHEMA_VERSION",
    "CaptureAdmissionError",
    "TypedCaptureIdentity",
    "admit_completed_capture",
    "capture_provenance_authority_artifact_id_for",
    "capture_provenance_authority_path",
    "load_capture_provenance_authority",
    "require_homogeneous_capture_closure",
    "require_no_provenance_laundering",
    "resolve_typed_capture_identity",
    "verify_capture_package_identity",
    "verify_capture_runtime_apparatus",
    "verify_visibility_rows_scientific_identity",
]
