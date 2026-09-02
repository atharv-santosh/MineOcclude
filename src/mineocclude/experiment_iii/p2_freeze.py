"""A6 -- the P2 prospective freeze package (authority 6/A6).

A6 is the final scientific freeze: "after this, nothing scientific may change."
Its pass condition is that *every* binding is present, non-null, and **verified
against the live artifact** -- so this module never restates a value it did not
read. Each binding is pulled from the frozen authority or from a live evidence
artifact on disk, and every one of them carries a verification record naming
what it was checked against.

Three refusals, in the authority's own vocabulary:

``P2_BINDING_INCOMPLETE``
    A mandatory binding is missing, ``None``, or a placeholder. Authority 6/A6
    forbids freezing with "a placeholder, a null, or a 'to be determined'", so
    :func:`_reject_placeholders` walks the whole assembled package and refuses
    the sentinel strings as well as ``None``.
``P2_BINDING_MISMATCH``
    A binding does not agree with the live artifact it was checked against --
    for example a manifest whose recorded SHA-256 is not the SHA-256 of the
    bytes on disk.
``P2_PREREQUISITE_NOT_PASSED``
    One of A0-A5 lacks a PASS receipt bound to this authority.

**This module freezes; it does not decide.** No value here is computed from a
production outcome, re-selected, re-tuned, or defaulted. Where a value has an
authority-qualified source, that source is the only source.

**Authorization is emitted here and nowhere else.** Authority 6/A6: "Only here,
and only on this exit, may ``PRODUCTION_AUTHORIZED = true`` and
``MODEL_INFERENCE_AUTHORIZED = true`` be emitted." A4's ladder verdict carries
its own ``PRODUCTION_AUTHORIZED`` field for historical reasons; it is deliberately
NOT read as an authorization input here -- only ``P0_RESULT == P0_PASS`` is.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from mineocclude.experiment_iii.activation_store import (
    EXPECTED_DTYPE,
    EXPECTED_NPY_BYTES,
    EXPECTED_SHAPE,
    UNITS_PER_CAPTURE,
)
from mineocclude.experiment_iii.authority import (
    AUTHORITY_FREEZE_COMMIT,
    AUTHORITY_VERSION,
    CAMERA_EYE,
    CAMERA_FEET,
    CAPTURE_HZ,
    CONTEXT_PAIRS,
    DIRECTIONS,
    DT_SECONDS,
    FRAMEBUFFER_HEIGHT,
    FRAMEBUFFER_WIDTH,
    FRAMES_PER_CAPTURE,
    IDENTITIES_PER_OUTER_FOLD,
    INNER_ROTATIONS,
    LAYOUT_01,
    LEFT_TO_RIGHT_COUNT,
    MOTION_NOISE_Q,
    OUTER_FOLDS,
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_COUNT,
    PRODUCTION_IDENTITY_IDS,
    RIGHT_TO_LEFT_COUNT,
    SPEED_BLOCKS_PER_SECOND,
    TARGET_ROWS_PER_CAPTURE,
    canonical_sha256,
    machine_authority,
    machine_authority_sha256,
    phase0_design_sha256,
    sha256_file,
    verify_authority_binding,
)
from mineocclude.experiment_iii.conditions import AIR, STONE
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.extent_geometry import (
    EXTENT_SAMPLES_PER_AXIS,
    TARGET_EXTENT_HALF_BLOCKS,
)
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS
from mineocclude.experiment_iii.fir import (
    KERNEL_LAGS,
    KERNEL_LENGTH,
    frozen_kernels,
)
from mineocclude.experiment_iii.p1_extraction import HOOK_SITE
from mineocclude.experiment_iii.statistics import (
    ANALYSIS_BOOTSTRAP_SEED_DOMAIN,
    analysis_bootstrap_seed,
    assert_concrete_bootstrap_seed,
)
from mineocclude.experiment_iii.schema import TemporalSlice
from mineocclude.experiment_iii.slices import verify_slice_arithmetic

__all__ = [
    "P2_FREEZE_SCHEMA_VERSION",
    "BINDING_GROUPS",
    "PLACEHOLDER_PREFIXES",
    "PLACEHOLDER_TOKENS",
    "build_p2_freeze_package",
    "p2_bound_source_closure",
    "p2_freeze_passed",
    "verify_p2_freeze_package",
]

P2_FREEZE_SCHEMA_VERSION = "mineocclude-experiment-iii-p2-freeze-v1"

#: The seven binding groups named by the frozen lifecycle's A6
#: ``expected_counts.groups``, in that order. The authority markdown splits the
#: last group's prose into Extraction / Analysis / Operations; the lifecycle
#: counts them as one group, and the lifecycle is the machine contract.
BINDING_GROUPS = (
    "AUTHORITY_AND_CODE",
    "ENVIRONMENT",
    "COHORT",
    "CONDITIONS_AND_EVIDENCE",
    "APPARATUS",
    "MEASUREMENT",
    "EXTRACTION_ANALYSIS_AND_OPERATIONS",
)

#: Strings a frozen binding may never hold. Authority 6/A6 forbids freezing with
#: a placeholder or a "to be determined"; a value that merely *looks* decided is
#: the failure this list exists to catch.
PLACEHOLDER_TOKENS = frozenset(
    {
        "",
        "TBD",
        "TO_BE_DETERMINED",
        "TO BE DETERMINED",
        "UNKNOWN",
        "UNVERIFIED",
        "PLACEHOLDER",
        "NULL",
        "NONE",
        "N/A",
        "NA",
        "FIXME",
        "XXX",
        "CHANGEME",
        # The authority's own deferral token. Its absence here is why the
        # superseded P2 froze ``statistics.bootstrap_seed = "FROZEN_IN_P2"`` and
        # still reported PASS: the walker had the right shape and an incomplete
        # vocabulary. Amendment 5 gives that binding a derived value; this entry
        # makes the class of defect unrepeatable.
        "FROZEN_IN_P2",
    }
)

#: A deferral to P2 can never itself be a P2 binding, whatever suffix it carries
#: (the III-B stream discipline token is ``FROZEN_IN_P2_SAME_STREAM_...``).
PLACEHOLDER_PREFIXES = ("FROZEN_IN_P2",)


# --------------------------------------------------------------------------
# Fail-closed primitives
# --------------------------------------------------------------------------


def _json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require_file(path: Path | None, binding: str) -> Path:
    """A binding's evidence must be a real file, named explicitly."""
    if path is None:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            f"the {binding} binding names no path; A6 will not freeze a binding "
            "it cannot read",
        )
    path = Path(path)
    if not path.is_file():
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            f"the {binding} binding needs {path}, which is absent",
        )
    return path


#: Marker key on a sub-document quoted verbatim out of the frozen machine
#: authority. Such an excerpt is bound *by identity* -- the exact bytes plus a
#: digest -- and is exempt from the placeholder walk, because the authority
#: legitimately carries meaningful nulls (``statistics.overall_success_gate`` is
#: null by the amendment that removed the gate; the descriptive secondary family
#: D has ``qualification_gate: null`` because it has no gate). Those are frozen
#: scientific values, not "to be determined"s. Refusing them would make A6
#: unfreezable for a rule the authority does not state, and rewriting them would
#: falsify the authority. Every binding this module *assembles* stays strict.
_AUTHORITY_EXCERPT_KEY = "_frozen_authority_excerpt"


def _authority_excerpt(keypath: Sequence[str], verifier: _Verifier) -> dict[str, Any]:
    """Quote a machine-authority sub-document verbatim, bound by its digest."""
    node: Any = machine_authority()
    for key in keypath:
        if not isinstance(node, Mapping) or key not in node:
            raise ExperimentIIIError(
                "P2_BINDING_INCOMPLETE",
                f"the machine authority has no value at {'.'.join(keypath)}",
            )
        node = node[key]
    dotted = ".".join(keypath)
    digest = canonical_sha256(node)
    verifier.note(
        f"authority_excerpt.{dotted}",
        digest,
        f"the machine authority sub-document at {dotted}, quoted verbatim",
    )
    return {
        _AUTHORITY_EXCERPT_KEY: dotted,
        "sha256": digest,
        "value": node,
    }


def _reject_placeholders(node: Any, trail: str = "") -> None:
    """Refuse ``None`` and every placeholder token, anywhere in the package.

    Walked over the *assembled* package rather than checked per-binding, so a
    null introduced by any group is caught before the package can hash. Verbatim
    frozen-authority excerpts are bound by identity and skipped; see
    :data:`_AUTHORITY_EXCERPT_KEY`.
    """
    if isinstance(node, Mapping) and _AUTHORITY_EXCERPT_KEY in node:
        if not node.get(_AUTHORITY_EXCERPT_KEY) or not node.get("sha256"):
            raise ExperimentIIIError(
                "P2_BINDING_INCOMPLETE",
                f"the authority excerpt at {trail} is not bound by identity",
            )
        return
    if node is None:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            f"the freeze binding at {trail or '<root>'} is null; authority 6/A6 "
            "forbids freezing with a null",
        )
    if isinstance(node, str):
        token = node.strip().upper()
        if token in PLACEHOLDER_TOKENS or token.startswith(PLACEHOLDER_PREFIXES):
            raise ExperimentIIIError(
                "P2_BINDING_INCOMPLETE",
                f"the freeze binding at {trail} is the placeholder {node!r}; "
                "authority 6/A6 forbids freezing with a placeholder or a "
                "'to be determined'",
            )
        return
    if isinstance(node, Mapping):
        for key, value in node.items():
            _reject_placeholders(value, f"{trail}.{key}" if trail else str(key))
        return
    if isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            _reject_placeholders(value, f"{trail}[{index}]")


class _Verifier:
    """Collects one verification record per binding checked against evidence."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def check(self, binding: str, observed: Any, expected: Any, against: str) -> Any:
        """Record that ``binding`` was compared to a live artifact, and refuse a
        mismatch. Returns ``observed`` so call sites read as assignments."""
        agrees = observed == expected
        self.records.append(
            {
                "binding": binding,
                "verified_against": against,
                "expected": expected,
                "observed": observed,
                "agrees": bool(agrees),
            }
        )
        if not agrees:
            raise ExperimentIIIError(
                "P2_BINDING_MISMATCH",
                f"the {binding} binding does not verify against {against}: "
                f"expected {expected!r}, observed {observed!r}",
            )
        return observed

    def note(self, binding: str, value: Any, against: str) -> Any:
        """Record a binding read directly from a live artifact (no second
        source to compare against); its presence is still proven."""
        self.records.append(
            {
                "binding": binding,
                "verified_against": against,
                "expected": value,
                "observed": value,
                "agrees": True,
            }
        )
        return value

    @property
    def unverified(self) -> list[str]:
        return [r["binding"] for r in self.records if not r["agrees"]]


def _hashed(path: Path, binding: str, verifier: _Verifier) -> dict[str, Any]:
    """Bind a live artifact by its real SHA-256, computed here from its bytes."""
    path = _require_file(path, binding)
    digest = sha256_file(path)
    verifier.note(binding, digest, f"sha256 of the bytes at {path.as_posix()}")
    return {"path": path.as_posix(), "sha256": digest, "bytes": path.stat().st_size}


def _stage_pass(
    receipt: Mapping[str, Any], field_paths: Sequence[Sequence[str]], stage: str
) -> None:
    """Refuse unless the named stage receipt actually reads PASS."""
    for field_path in field_paths:
        node: Any = receipt
        for key in field_path:
            if not isinstance(node, Mapping) or key not in node:
                node = None
                break
            node = node[key]
        if node in (True, "PASS", "P0_PASS"):
            return
    raise ExperimentIIIError(
        "P2_PREREQUISITE_NOT_PASSED",
        f"{stage} does not carry a PASS verdict in its receipt",
    )


# --------------------------------------------------------------------------
# The seven binding groups
# --------------------------------------------------------------------------


def _group_authority_and_code(
    *,
    aprime_port_receipt_path: Path,
    fir_recovery_receipt_path: Path,
    source_closure: Mapping[str, Any],
    verifier: _Verifier,
) -> dict[str, Any]:
    """Authority SHA-256, machine-authority SHA-256, source closure, HEAD, and
    the two A1 provenance receipts (authority 6/A6 *Authority and code*)."""
    binding = verify_authority_binding()
    verifier.check(
        "authority.AUTHORITY_SHA256",
        binding["AUTHORITY_SHA256"],
        machine_authority()["authority_markdown_sha256"],
        "the machine authority's own recorded markdown digest",
    )
    verifier.check(
        "authority.MACHINE_AUTHORITY_SHA256",
        binding["MACHINE_AUTHORITY_SHA256"],
        machine_authority_sha256(),
        "the machine authority JSON recomputed from its bytes",
    )
    verifier.check(
        "authority.PHASE0_DESIGN_SHA256",
        binding["PHASE0_DESIGN_SHA256"],
        phase0_design_sha256(),
        "the Phase 0 adjudicated design recomputed from its bytes",
    )
    closure_digest = source_closure.get("source_closure_sha256")
    head = source_closure.get("head_commit")
    if not closure_digest or not head:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            "the source closure binding lacks a digest or a HEAD commit",
        )
    verifier.note(
        "code.source_closure_sha256", closure_digest, "source_closure() at freeze time"
    )
    verifier.note("code.head_commit", head, "git rev-parse HEAD at freeze time")
    return {
        "authority_version": AUTHORITY_VERSION,
        "authority_sha256": binding["AUTHORITY_SHA256"],
        "machine_authority_sha256": binding["MACHINE_AUTHORITY_SHA256"],
        "phase0_design_sha256": binding["PHASE0_DESIGN_SHA256"],
        "authority_freeze_commit": AUTHORITY_FREEZE_COMMIT,
        "source_closure": dict(source_closure),
        "head_commit": head,
        "aprime_port_receipt": _hashed(
            aprime_port_receipt_path, "authority_and_code.aprime_port_receipt", verifier
        ),
        "fir_kernel_recovery_receipt": _hashed(
            fir_recovery_receipt_path,
            "authority_and_code.fir_kernel_recovery_receipt",
            verifier,
        ),
    }


def _group_environment(
    *,
    capture_a3: Mapping[str, Any],
    extraction_a3: Mapping[str, Any],
    observed_preprocessing_identity: str,
    verifier: _Verifier,
) -> dict[str, Any]:
    """OS/Python/NumPy/torch/CUDA/GPU, the Minecraft and Fabric pins, the mod jar
    hash, and the model and VAE identities (authority 6/A6 *Environment*).

    Every value is read out of an A3 receipt that hashed or probed it on the host
    that actually holds it. The mod jar lives only on the capture host and the
    weights only on the extraction host, so neither receipt alone can supply this
    group and both are required.
    """
    authority_extraction = machine_authority()["extraction"]
    apparatus = machine_authority()["apparatus"]

    pins = capture_a3.get("runtime_pins") or {}
    declared = pins.get("declared_pins") or {}
    for field, expected in (
        ("minecraft_version", apparatus["minecraft_version"]),
        ("fabric_loader_version", apparatus["fabric_loader_version"]),
        ("fabric_api_version", apparatus["fabric_api_version"]),
        ("yarn_mappings", apparatus["yarn_mappings"]),
    ):
        verifier.check(
            f"environment.{field}",
            declared.get(field),
            expected,
            "the capture-host A3 runtime pins against the frozen apparatus",
        )
    mod_jar = pins.get("mod_jar") or {}
    if not mod_jar.get("sha256"):
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            "the capture-host A3 receipt carries no mod jar SHA-256",
        )
    verifier.note(
        "environment.mod_jar_sha256",
        mod_jar["sha256"],
        "the capture-host A3 receipt, which hashed the jar it loaded",
    )

    model = extraction_a3.get("model_identity_checks") or {}
    if not model.get("verified"):
        raise ExperimentIIIError(
            "P2_BINDING_MISMATCH",
            "the extraction-host A3 receipt does not record a verified model "
            "identity; A6 will not freeze a checkpoint nobody hashed",
        )
    verifier.check(
        "environment.main_checkpoint_sha256",
        (model.get("main_checkpoint") or {}).get("observed_sha256"),
        authority_extraction["main_checkpoint_sha256"],
        "the extraction-host A3 receipt's observed digest against the authority",
    )
    verifier.check(
        "environment.vae_sha256",
        (model.get("vae_checkpoint") or {}).get("observed_sha256"),
        authority_extraction["vae_sha256"],
        "the extraction-host A3 receipt's observed digest against the authority",
    )

    # The preprocessing profile is a frozen adapter constant, and the P1
    # extraction inventories recorded what the *loaded runtime* reported for the
    # same field. Freezing the constant only after it agrees with the live
    # recording is the difference between a binding and a restatement.
    from mineocclude.models._mineworld_adapter_wave2 import (
        ACTION_CONVERTER_IDENTITY,
        PREPROCESSING_PROFILE,
    )

    verifier.check(
        "environment.preprocessing_identity",
        observed_preprocessing_identity,
        PREPROCESSING_PROFILE,
        "the P1 extraction inventories, which recorded the loaded runtime's "
        "preprocessing identity, against the frozen adapter constant",
    )
    verifier.note(
        "environment.action_conversion_identity",
        ACTION_CONVERTER_IDENTITY,
        "the frozen adapter action-converter constant",
    )

    gpu = extraction_a3.get("gpu") or {}
    return {
        "preprocessing_identity": PREPROCESSING_PROFILE,
        "action_conversion_identity": ACTION_CONVERTER_IDENTITY,
        "capture_host": {
            "platform": (capture_a3.get("host") or {}).get("platform"),
            "python": (capture_a3.get("host") or {}).get("python"),
            "implementation_checkpoint_commit": capture_a3.get(
                "implementation_checkpoint_commit"
            ),
        },
        "extraction_host": {
            "platform": (extraction_a3.get("host") or {}).get("platform"),
            "python": (extraction_a3.get("host") or {}).get("python"),
            "torch_version": gpu.get("torch_version"),
            "cuda_version": gpu.get("cuda_version"),
            "gpu_device_name": gpu.get("device_name"),
            "gpu_capability": gpu.get("capability"),
            "implementation_checkpoint_commit": extraction_a3.get(
                "implementation_checkpoint_commit"
            ),
        },
        "minecraft_version": apparatus["minecraft_version"],
        "fabric_loader_version": apparatus["fabric_loader_version"],
        "fabric_api_version": apparatus["fabric_api_version"],
        "yarn_mappings": apparatus["yarn_mappings"],
        "mod_jar": dict(mod_jar),
        "main_checkpoint_sha256": authority_extraction["main_checkpoint_sha256"],
        "vae_sha256": authority_extraction["vae_sha256"],
        "model": authority_extraction["model"],
        "preprocessing_change_allowed": bool(
            authority_extraction["preprocessing_change_allowed"]
        ),
    }


def _group_cohort(
    *,
    production_manifest_path: Path,
    production_manifest_sha256_path: Path,
    pilot_manifest_path: Path,
    folds_path: Path,
    priority_order_path: Path,
    verifier: _Verifier,
) -> dict[str, Any]:
    """The 25 production identities with their full per-identity binding, the two
    excluded pilots, the folds and the priority order (authority 6/A6 *Cohort*).

    The manifest is bound by hash *and* re-read row by row, because the freeze
    owes the 19 target indices and 19 FIR labels per identity, not merely a
    digest over them.
    """
    manifest_path = _require_file(production_manifest_path, "cohort.production_manifest")
    rows = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    verifier.check(
        "cohort.production_identity_count",
        len(rows),
        PRODUCTION_IDENTITY_COUNT,
        "the materialized production identity manifest",
    )

    # The committed .sha256 sidecar is evidence only if it agrees with the bytes.
    # It is a JSON mapping of filename -> digest, not `sha256sum` text output.
    sidecar_path = _require_file(
        production_manifest_sha256_path, "cohort.production_manifest_sha256"
    )
    sidecar_doc = _json(sidecar_path)
    sidecar = sidecar_doc.get(manifest_path.name)
    if sidecar is None:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            f"the sidecar {sidecar_path} names no digest for {manifest_path.name}",
        )
    verifier.check(
        "cohort.production_manifest_sha256",
        sidecar,
        sha256_file(manifest_path),
        "the committed .sha256 sidecar against the manifest bytes",
    )

    identity_ids = [row["identity"] for row in rows]
    verifier.check(
        "cohort.production_identity_ids",
        identity_ids,
        list(PRODUCTION_IDENTITY_IDS),
        "the manifest rows against the authority's frozen identity roster",
    )

    directions = [row["direction"] for row in rows]
    verifier.check(
        "cohort.left_to_right_count",
        sum(1 for d in directions if d == "LEFT_TO_RIGHT"),
        LEFT_TO_RIGHT_COUNT,
        "the manifest's direction column",
    )
    verifier.check(
        "cohort.right_to_left_count",
        sum(1 for d in directions if d == "RIGHT_TO_LEFT"),
        RIGHT_TO_LEFT_COUNT,
        "the manifest's direction column",
    )

    identities: list[dict[str, Any]] = []
    for row in rows:
        target_indices = list(row["target_model_frame_indices"])
        # The manifest's frozen FIR labels are the per-target-row causal FIR
        # target positions; authority 6/A6 calls them the "19 FIR labels".
        fir_labels = list(row["expected_causal_fir_target_world_x_blocks"])
        for field, values in (
            ("target indices", target_indices),
            ("FIR labels", fir_labels),
        ):
            if len(values) != TARGET_ROWS_PER_CAPTURE:
                raise ExperimentIIIError(
                    "P2_BINDING_MISMATCH",
                    f"{row['identity']} carries {len(values)} {field}, the "
                    f"authority freezes {TARGET_ROWS_PER_CAPTURE}",
                )
        identities.append(
            {
                "identity": row["identity"],
                "episode_id": row["episode_id"],
                "seed": row["seed"],
                "noise_seed": row["noise_seed"],
                "candidate_index": row["candidate_index"],
                "direction": row["direction"],
                "start_world_x": row["start_world_x"],
                "path_sha256": row["path_sha256"],
                "noise_schedule_sha256": row["noise_schedule_sha256"],
                "target_model_frame_indices": target_indices,
                "expected_causal_fir_target_world_x_blocks": fir_labels,
                "expected_target_sd_blocks": row["expected_target_sd_blocks"],
                "outer_fold": row["outer_fold"],
                "priority_rank": row["priority_rank"],
                "spec_hash": row["spec_hash"],
                "frames": row["frames"],
                "tail_clamped_after_target_window": row[
                    "tail_clamped_after_target_window"
                ],
            }
        )

    pilot_path = _require_file(pilot_manifest_path, "cohort.pilot_manifest")
    pilot_rows = [
        json.loads(line)
        for line in pilot_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    verifier.check(
        "cohort.excluded_pilot_ids",
        sorted({row["identity"] for row in pilot_rows}),
        sorted(PILOT_IDENTITY_IDS),
        "the pilot identity manifest against the authority's pilot roster",
    )
    # The cohort was materialized under the v1.5 authority and has been carried
    # forward byte-identically ever since (amendments 2-4 changed no cohort
    # value; the A2 suite re-verifies the bytes end to end). The declared field
    # is bound as observed rather than silently normalised to v1.7's digest,
    # because rewriting it would be a false claim about frozen bytes.
    declared = sorted({row["authority_sha256"] for row in rows})
    verifier.note(
        "cohort.manifest_declared_authority_sha256",
        declared,
        "the production manifest rows, recorded as materialized",
    )

    return {
        "production_identity_count": PRODUCTION_IDENTITY_COUNT,
        "left_to_right_count": LEFT_TO_RIGHT_COUNT,
        "right_to_left_count": RIGHT_TO_LEFT_COUNT,
        "target_rows_per_capture": TARGET_ROWS_PER_CAPTURE,
        "identities": identities,
        "production_identity_manifest": _hashed(
            manifest_path, "cohort.production_identity_manifest", verifier
        ),
        "excluded_pilot_identities": sorted(PILOT_IDENTITY_IDS),
        "manifest_declared_authority_sha256": declared,
        "manifest_declared_authority_note": (
            "the cohort was materialized under v1.5 and carried forward "
            "byte-identically; amendments 2-4 changed no cohort value"
        ),
        "excluded_pilots_not_promotable": True,
        "folds": _hashed(folds_path, "cohort.folds", verifier),
        "folds_content": _json(_require_file(folds_path, "cohort.folds")),
        "identity_priority_order": _hashed(
            priority_order_path, "cohort.identity_priority_order", verifier
        ),
        "outer_folds": OUTER_FOLDS,
        "identities_per_outer_fold": IDENTITIES_PER_OUTER_FOLD,
        "inner_rotations": INNER_ROTATIONS,
    }


def _group_conditions_and_evidence(
    *,
    p0_selection_receipt_path: Path,
    p0_selected_ladder_path: Path,
    p0_sentinel_envelope_path: Path,
    verifier: _Verifier,
) -> dict[str, Any]:
    """The five conditions, the P0-selected ladder with its frozen ``V_c``, the
    P0 selection receipt hash, the sentinel placements and repeatability
    envelope, and the P0 bootstrap seed (authority 6/A6 *Conditions and
    evidence*).

    P0 is banked upstream evidence. Nothing here re-selects a material or
    recomputes an RVE; the ladder is read and checked for the ``P0_PASS`` it
    must already carry.
    """
    receipt_path = _require_file(
        p0_selection_receipt_path, "conditions.p0_selection_receipt"
    )
    receipt = _json(receipt_path)
    _stage_pass(receipt, [("P0_RESULT",)], "A4 (P0 visibility calibration)")

    ladder_path = _require_file(p0_selected_ladder_path, "conditions.p0_selected_ladder")
    ladder = _json(ladder_path)
    _stage_pass(ladder, [("P0_RESULT",)], "A4 (P0 selected ladder)")

    for level in ("L1", "L2", "L3"):
        verifier.check(
            f"conditions.{level}_registry_id",
            ladder.get(level),
            (receipt.get("selected_ladder") or {}).get(level),
            "the P0 selected ladder against the P0 selection receipt",
        )
    v_c = ladder.get("V_c") or {}
    for level in ("L1", "L2", "L3"):
        if v_c.get(level) is None:
            raise ExperimentIIIError(
                "P2_BINDING_INCOMPLETE",
                f"the P0 ladder carries no frozen V_c for {level}",
            )
        verifier.note(
            f"conditions.V_c.{level}",
            v_c[level],
            "the frozen P0 selected ladder",
        )

    envelope_path = _require_file(
        p0_sentinel_envelope_path, "conditions.p0_sentinel_envelope"
    )
    envelope = _json(envelope_path)
    _stage_pass(envelope, [("P0_RESULT",)], "A4 (P0 sentinel envelope)")
    placements = sorted(int(k) for k in (envelope.get("envelope") or {}).get("bounds", {}))
    if not placements:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            "the P0 sentinel envelope names no sentinel placements",
        )
    verifier.note(
        "conditions.sentinel_placements", placements, "the frozen P0 sentinel envelope"
    )

    bootstrap_seed = (receipt.get("provenance") or {}).get(
        "p0_bootstrap_seed"
    ) or receipt.get("p0_bootstrap_seed")
    if bootstrap_seed is None:
        from mineocclude.experiment_iii.p0_bindings import p0_bootstrap_seed

        bootstrap_seed = p0_bootstrap_seed()
        verifier.note(
            "conditions.p0_bootstrap_seed",
            bootstrap_seed,
            "p0_bindings.p0_bootstrap_seed() derived from the frozen Phase 0 design",
        )
    else:
        verifier.note(
            "conditions.p0_bootstrap_seed",
            bootstrap_seed,
            "the P0 selection receipt provenance",
        )

    return {
        "condition_ids": ["L0", "L1", "L2", "L3", "L4"],
        "L0_material": AIR,
        "L1_material": ladder["L1"],
        "L2_material": ladder["L2"],
        "L3_material": ladder["L3"],
        "L4_material": STONE,
        "V_c": {
            "L0": 1.0 if v_c.get("L0") is None else v_c["L0"],
            "L1": v_c["L1"],
            "L2": v_c["L2"],
            "L3": v_c["L3"],
            "L4": 0.0 if v_c.get("L4") is None else v_c["L4"],
        },
        "V_c_source": "P0_SELECTED_LADDER.json (L1-L3 measured); L0/L4 are the "
        "frozen endpoints of the visibility scale, not measured quantities",
        "p0_selection_receipt": _hashed(
            receipt_path, "conditions.p0_selection_receipt", verifier
        ),
        "p0_selected_ladder": _hashed(
            ladder_path, "conditions.p0_selected_ladder", verifier
        ),
        "p0_sentinel_envelope": _hashed(
            envelope_path, "conditions.p0_sentinel_envelope", verifier
        ),
        "sentinel_placements": placements,
        "sentinel_repeatability_envelope": envelope.get("envelope"),
        "p0_bootstrap_seed": bootstrap_seed,
        "p0_result": receipt["P0_RESULT"],
    }


def _group_apparatus(*, verifier: _Verifier) -> dict[str, Any]:
    """Layout, camera, wall volume, speed, ``q``, ``dt``, 180 frames, the
    framebuffer and the lighting/warm-up policy (authority 6/A6 *Apparatus*).

    Each value is taken from the implementation constant and checked against the
    machine authority, so a drift between the two is a freeze failure rather than
    a silent preference for one of them.
    """
    apparatus = machine_authority()["apparatus"]
    verifier.check(
        "apparatus.speed_blocks_per_second",
        SPEED_BLOCKS_PER_SECOND,
        apparatus["speed_blocks_per_second"],
        "the implementation constant against the machine authority",
    )
    verifier.check(
        "apparatus.dt_seconds",
        DT_SECONDS,
        apparatus["dt_seconds"],
        "the implementation constant against the machine authority",
    )
    verifier.check(
        "apparatus.frames_per_capture",
        FRAMES_PER_CAPTURE,
        apparatus["frames_per_capture"],
        "the implementation constant against the machine authority",
    )
    verifier.check(
        "apparatus.capture_hz",
        CAPTURE_HZ,
        apparatus["capture_hz"],
        "the implementation constant against the machine authority",
    )
    verifier.check(
        "apparatus.process_noise_q",
        MOTION_NOISE_Q,
        apparatus["process_noise_q_blocks_squared_per_second"],
        "the implementation constant against the machine authority",
    )
    verifier.check(
        "apparatus.framebuffer",
        [FRAMEBUFFER_WIDTH, FRAMEBUFFER_HEIGHT],
        list(apparatus["framebuffer"]),
        "the implementation constants against the machine authority",
    )
    verifier.note("apparatus.layout", LAYOUT_01, "the frozen layout constant")
    verifier.note("apparatus.camera_eye", list(CAMERA_EYE), "the frozen camera constant")

    return {
        "layout": LAYOUT_01,
        "layout_detail": apparatus["layout"],
        "camera_eye": list(CAMERA_EYE),
        "camera_feet": list(CAMERA_FEET),
        "camera_yaw": apparatus["camera_yaw"],
        "camera_pitch": apparatus["camera_pitch"],
        "camera_roll": apparatus["camera_roll"],
        "camera_fov_degrees": apparatus["camera_fov_degrees"],
        "camera_lock": apparatus["camera_lock"],
        "wall_volume": apparatus["as_built_wall_volume"],
        "wall_height_blocks": apparatus["wall_height_blocks"],
        "wall_thickness_blocks": apparatus["wall_thickness_blocks"],
        "sheep_lane": apparatus["sheep_lane"],
        "target": apparatus["target"],
        "speed_blocks_per_second": SPEED_BLOCKS_PER_SECOND,
        "process_noise_q_blocks_squared_per_second": MOTION_NOISE_Q,
        "dt_seconds": DT_SECONDS,
        "frames_per_capture": FRAMES_PER_CAPTURE,
        "capture_hz": CAPTURE_HZ,
        "framebuffer": {"width": FRAMEBUFFER_WIDTH, "height": FRAMEBUFFER_HEIGHT},
        "lighting": apparatus["lighting"],
        "required_receipts": apparatus["required_receipts"],
        "directions": list(DIRECTIONS),
    }


def _group_measurement(*, verifier: _Verifier) -> dict[str, Any]:
    """Both direction FIR kernels, the extent half-width, ``samples_per_axis``
    and the eligibility equation (authority 6/A6 *Measurement*)."""
    fir_authority = machine_authority()["fir"]
    kernels = frozen_kernels()
    if set(kernels) != set(DIRECTIONS):
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            f"the freeze needs a FIR kernel per direction {sorted(DIRECTIONS)}, "
            f"found {sorted(kernels)}",
        )
    for direction, taps in kernels.items():
        if len(taps) != KERNEL_LENGTH:
            raise ExperimentIIIError(
                "P2_BINDING_MISMATCH",
                f"the {direction} FIR kernel has {len(taps)} taps, the authority "
                f"freezes {KERNEL_LENGTH}",
            )
        verifier.note(
            f"measurement.fir_kernel.{direction}",
            list(taps),
            "fir.frozen_kernels(), recovered under the FIR recovery receipt",
        )
    verifier.check(
        "measurement.extent_half_width",
        TARGET_EXTENT_HALF_BLOCKS,
        machine_authority()["visibility_semantics"]["target_extent_half_blocks"],
        "the implementation constant against the machine authority",
    )
    verifier.check(
        "measurement.extent_samples_per_axis",
        EXTENT_SAMPLES_PER_AXIS,
        machine_authority()["visibility_semantics"]["extent_samples_per_axis"],
        "the implementation constant against the machine authority",
    )
    return {
        "fir_kernels": {
            direction: list(taps) for direction, taps in sorted(kernels.items())
        },
        "fir_kernel_length": KERNEL_LENGTH,
        "fir_kernel_lags": list(KERNEL_LAGS),
        "fir_normalization": fir_authority["normalization"],
        "fir_normalization_method": fir_authority["normalization_method"],
        "fir_label_formula": fir_authority["label_formula"],
        "first_fully_resolved_tick": fir_authority["first_fully_resolved_tick"],
        "target_extent_half_blocks": TARGET_EXTENT_HALF_BLOCKS,
        "extent_samples_per_axis": EXTENT_SAMPLES_PER_AXIS,
        "target_eligibility_rule": machine_authority()["visibility_semantics"][
            "target_eligibility_rule"
        ],
        "target_extent_closed_form": machine_authority()["visibility_semantics"][
            "target_extent_closed_form"
        ],
    }


def _group_extraction_analysis_and_operations(
    *, p1_pilot_receipt_path: Path, verifier: _Verifier
) -> dict[str, Any]:
    """Extraction geometry, the analysis recipe and the operations policy.

    The lifecycle counts these as one group; the authority markdown discusses
    them under three headings. Nothing here is chosen: the layers, slices and
    tensor schema are the ones P1 already produced 60 arrays under, the analysis
    recipe is read from the frozen authority, and the operations policy is the
    frozen capture order, retry, attrition and deadline rules.
    """
    authority = machine_authority()
    extraction = authority["extraction"]
    production = authority["production"]
    readout = authority["readout"]
    statistics = authority["statistics"]
    representations = authority["representations"]

    # --- extraction ------------------------------------------------------
    verifier.check(
        "extraction.layers",
        list(SELECTED_LAYERS),
        list(extraction["layers"]),
        "the implementation's selected layers against the machine authority",
    )
    verifier.check(
        "extraction.expected_shape",
        list(EXPECTED_SHAPE),
        [
            TARGET_ROWS_PER_CAPTURE,
            extraction["visual_tokens_per_pair"],
            extraction["hidden_width"],
        ],
        "the activation-store shape against the authority's token geometry",
    )
    slice_arithmetic = verify_slice_arithmetic()
    for name in (temporal.value for temporal in TemporalSlice):
        frozen = extraction["temporal_slices"][name]
        verifier.check(
            f"extraction.slice.{name}",
            [
                slice_arithmetic[name]["python_start"],
                slice_arithmetic[name]["python_stop_exclusive"],
            ],
            [frozen["python_start"], frozen["python_stop_exclusive"]],
            "the derived slice arithmetic against the machine authority",
        )
        verifier.check(
            f"extraction.slice.{name}.excluded_action_range",
            [
                slice_arithmetic[name]["excluded_action_inclusive_start"],
                slice_arithmetic[name]["excluded_action_inclusive_end"],
            ],
            [
                frozen["excluded_action_inclusive_start"],
                frozen["excluded_action_inclusive_end"],
            ],
            "the derived slice arithmetic against the machine authority",
        )
    verifier.check(
        "extraction.sequence_length",
        slice_arithmetic["sequence_length"],
        extraction["sequence_length"],
        "the derived slice arithmetic against the machine authority",
    )

    # --- the P1 pilot receipt this freeze stands on ----------------------
    receipt_path = _require_file(p1_pilot_receipt_path, "operations.p1_pilot_receipt")
    p1_receipt = _json(receipt_path)
    _stage_pass(p1_receipt, [("P1_RESULT",), ("P1_FULL_PASS",)], "A5 (P1 pilot)")
    if p1_receipt.get("failed_items") or p1_receipt.get("missing_bindings"):
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            "the P1 pilot receipt carries failed items or missing bindings",
        )

    return {
        # extraction
        "layers": list(SELECTED_LAYERS),
        "transient_hook_layer_count": extraction["hooked_layer_count_transient"],
        "hook_site": HOOK_SITE,
        "sequence_length": extraction["sequence_length"],
        "context_pair_count": CONTEXT_PAIRS,
        "visual_tokens_per_pair": extraction["visual_tokens_per_pair"],
        "action_tokens_per_pair": extraction["action_tokens_per_pair"],
        "tokens_per_pair": extraction["tokens_per_pair"],
        "temporal_slices": {
            name: dict(extraction["temporal_slices"][name])
            for name in (temporal.value for temporal in TemporalSlice)
        },
        "activation_storage": _authority_excerpt(("extraction", "storage"), verifier),
        "expected_shape": list(EXPECTED_SHAPE),
        "expected_dtype": EXPECTED_DTYPE,
        "expected_npy_bytes": EXPECTED_NPY_BYTES,
        "arrays_per_capture": UNITS_PER_CAPTURE,
        "one_forward_per_target_row": bool(extraction["one_forward_per_target_row"]),
        "extra_forward_authorized": bool(extraction["extra_forward_authorized"]),
        # analysis
        "primary_representation": representations["concatenation_order"],
        "representation_definitions": _authority_excerpt(
            ("representations", "definitions"), verifier
        ),
        "coarse_grid": [
            representations["coarse_grid_rows"],
            representations["coarse_grid_cols"],
        ],
        "pooling": representations["pooling"],
        "alpha_grid": list(readout["alpha_grid"]),
        "alpha_selection_criterion": readout["alpha_selection_criterion"],
        "inner_rotations": readout["inner_rotations"],
        "outer_folds": readout["outer_folds"],
        "training_only_standardization": readout["training_only_standardization"],
        "unpenalized_intercept": readout["unpenalized_intercept"],
        "baselines": _authority_excerpt(("baselines",), verifier),
        "primary_tests": _authority_excerpt(("statistics", "primary_tests"), verifier),
        "primary_family_size": statistics["primary_family_size"],
        "primary_error_metric": statistics["primary_error_metric"],
        "secondary_families": _authority_excerpt(
            ("statistics", "secondary_families"), verifier
        ),
        "bootstrap_replicates": statistics["bootstrap_replicates"],
        # Authority 8.10.5a. Derived from the immutable Phase 0 design binding
        # and cross-checked against the frozen machine authority, rather than
        # copied out of it: copying is exactly how the placeholder reached the
        # superseded package.
        "bootstrap_seed": verifier.check(
            "analysis.bootstrap_seed",
            assert_concrete_bootstrap_seed(statistics["bootstrap_seed"]),
            analysis_bootstrap_seed(),
            "statistics.analysis_bootstrap_seed() derived from the frozen "
            "Phase 0 design binding under the 8.10.5a domain",
        ),
        "bootstrap_seed_domain": ANALYSIS_BOOTSTRAP_SEED_DOMAIN,
        "bootstrap_seed_binds_to": "PHASE0_DESIGN_SHA256",
        "bootstrap_seed_phase0_design_sha256": phase0_design_sha256(),
        "bootstrap_seed_material_sha256": hashlib.sha256(
            (ANALYSIS_BOOTSTRAP_SEED_DOMAIN + phase0_design_sha256()).encode("utf-8")
        ).hexdigest(),
        "bootstrap_unit": statistics["bootstrap_unit"],
        "primary_multiplicity": statistics["primary_multiplicity"],
        "prediction_lock_before_statistics": readout["prediction_lock_before_statistics"],
        # operations
        "production_captures": production["captures"],
        "production_target_rows": production["target_rows"],
        "production_forwards": production["forwards"],
        "production_serialized_npy_arrays": production["serialized_npy_arrays"],
        "production_logical_row_tensors": production["logical_row_tensors"],
        "production_condition_batches": production["condition_batches"],
        "capture_order": production["capture_order"],
        "latin_square": production["latin_square"],
        "identity_order_within_condition_block": production[
            "identity_order_within_condition_block"
        ],
        "retry_policy": _authority_excerpt(("production", "retry_policy"), verifier),
        "retry_may_not_change": production["retry_may_not_change"],
        "keep_first_technically_valid_attempt": bool(
            production["keep_first_technically_valid_attempt"]
        ),
        "identity_replacement_allowed": bool(production["identity_replacement_allowed"]),
        "capture_state_machine": _authority_excerpt(
            ("production", "capture_state_machine"), verifier
        ),
        "required_files_per_unit": production["required_files_per_unit"],
        "deadline_fallbacks": _authority_excerpt(("deadline_fallbacks",), verifier),
        "absolute_deadline": _authority_excerpt(("absolute_deadline",), verifier),
        "p1_pilot_receipt": _hashed(
            receipt_path, "operations.p1_pilot_receipt", verifier
        ),
        "p1_pilot_receipt_canonical_sha256": canonical_sha256(p1_receipt),
    }


# --------------------------------------------------------------------------
# The package
# --------------------------------------------------------------------------


def _observed_preprocessing_identity(activations_root: Path) -> str:
    """What the loaded runtime reported, read back out of the P1 inventories."""
    root = Path(activations_root)
    observed: set[str] = set()
    for inventory_path in sorted(root.glob("*/extraction_inventory.json")):
        inventory = _json(inventory_path)
        for artifact in inventory.get("artifacts", []):
            identity = artifact.get("preprocessing_identity")
            if identity:
                observed.add(identity)
    if not observed:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            f"no P1 extraction inventory under {root} records a preprocessing "
            "identity; the environment binding cannot be verified",
        )
    if len(observed) != 1:
        raise ExperimentIIIError(
            "P2_BINDING_MISMATCH",
            f"the P1 arrays were produced under {len(observed)} different "
            f"preprocessing identities: {sorted(observed)}",
        )
    return observed.pop()


def build_p2_freeze_package(
    *,
    source_closure: Mapping[str, Any],
    aprime_port_receipt_path: Path,
    fir_recovery_receipt_path: Path,
    capture_host_a3_path: Path,
    extraction_host_a3_path: Path,
    production_manifest_path: Path,
    production_manifest_sha256_path: Path,
    pilot_manifest_path: Path,
    folds_path: Path,
    priority_order_path: Path,
    p0_selection_receipt_path: Path,
    p0_selected_ladder_path: Path,
    p0_sentinel_envelope_path: Path,
    static_validation_receipt_path: Path,
    implementation_completion_receipt_path: Path,
    p1_pilot_receipt_path: Path,
    activations_root: Path,
) -> dict[str, Any]:
    """Assemble and verify the A6 freeze package, or refuse.

    Returns the package. Every failure path raises ``ExperimentIIIError`` with
    the authority's own blocker code; there is no partial or "provisional"
    package, because authority 6/A6 forbids one.
    """
    verifier = _Verifier()

    # --- prerequisites A0-A5, proven from their own receipts -------------
    static = _json(_require_file(static_validation_receipt_path, "prerequisite.A2"))
    _stage_pass(static, [("passed",)], "A2 (static validation)")
    implementation = _json(
        _require_file(implementation_completion_receipt_path, "prerequisite.A1")
    )
    if implementation.get("a1_tasks_complete") != implementation.get("a1_tasks_total"):
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            "the A1 implementation completion receipt does not report every task "
            "complete",
        )
    if not (implementation.get("a1_stage_exit_check") or {}).get("exit_permitted"):
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED", "A1's stage-exit check does not permit exit"
        )
    capture_a3 = _json(_require_file(capture_host_a3_path, "prerequisite.A3_capture"))
    _stage_pass(capture_a3, [("passed",)], "A3 (capture host)")
    extraction_a3 = _json(
        _require_file(extraction_host_a3_path, "prerequisite.A3_extraction")
    )
    _stage_pass(extraction_a3, [("passed",)], "A3 (extraction host)")

    # A6 must not be reachable from an extraction receipt that never authorized
    # the pilot extraction stage it is standing on.
    if "A5_EXTRACTION" not in list(extraction_a3.get("authorized_stages") or []):
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            "the extraction-host A3 receipt does not authorize A5_EXTRACTION",
        )

    groups = {
        "AUTHORITY_AND_CODE": _group_authority_and_code(
            aprime_port_receipt_path=aprime_port_receipt_path,
            fir_recovery_receipt_path=fir_recovery_receipt_path,
            source_closure=source_closure,
            verifier=verifier,
        ),
        "ENVIRONMENT": _group_environment(
            capture_a3=capture_a3,
            extraction_a3=extraction_a3,
            observed_preprocessing_identity=_observed_preprocessing_identity(
                activations_root
            ),
            verifier=verifier,
        ),
        "COHORT": _group_cohort(
            production_manifest_path=production_manifest_path,
            production_manifest_sha256_path=production_manifest_sha256_path,
            pilot_manifest_path=pilot_manifest_path,
            folds_path=folds_path,
            priority_order_path=priority_order_path,
            verifier=verifier,
        ),
        "CONDITIONS_AND_EVIDENCE": _group_conditions_and_evidence(
            p0_selection_receipt_path=p0_selection_receipt_path,
            p0_selected_ladder_path=p0_selected_ladder_path,
            p0_sentinel_envelope_path=p0_sentinel_envelope_path,
            verifier=verifier,
        ),
        "APPARATUS": _group_apparatus(verifier=verifier),
        "MEASUREMENT": _group_measurement(verifier=verifier),
        "EXTRACTION_ANALYSIS_AND_OPERATIONS": (
            _group_extraction_analysis_and_operations(
                p1_pilot_receipt_path=p1_pilot_receipt_path, verifier=verifier
            )
        ),
    }

    missing = [name for name in BINDING_GROUPS if name not in groups or not groups[name]]
    if missing:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            f"the freeze package is missing binding groups: {missing}",
        )
    if verifier.unverified:
        raise ExperimentIIIError(
            "P2_BINDING_MISMATCH",
            f"unverified bindings: {verifier.unverified}",
        )

    package: dict[str, Any] = {
        "schema_version": P2_FREEZE_SCHEMA_VERSION,
        "stage": "A6",
        "stage_name": "P2_PROSPECTIVE_FREEZE",
        "authority_section": "6/A6",
        "authority_version": AUTHORITY_VERSION,
        "authority_freeze_commit": AUTHORITY_FREEZE_COMMIT,
        "authority_binding": verify_authority_binding(),
        "binding_groups": list(BINDING_GROUPS),
        "binding_group_count": len(BINDING_GROUPS),
        "bindings": groups,
        "verification": {
            "checks": verifier.records,
            "check_count": len(verifier.records),
            "unverified": verifier.unverified,
            "every_binding_verified_against_a_live_artifact": True,
        },
        "prerequisites": {
            "A1_implementation": True,
            "A2_static_validation": True,
            "A3_capture_host": True,
            "A3_extraction_host": True,
            "A4_p0_visibility_calibration": True,
            "A5_p1_engineering_pilot": True,
        },
        "missing_bindings": [],
        "null_bindings": [],
        "unverified_bindings": [],
        # Authority 6/A6: only on this exit may these be emitted.
        "P2_RESULT": "PASS",
        "PRODUCTION_AUTHORIZED": True,
        "MODEL_INFERENCE_AUTHORIZED": True,
        "next_authorized_state": "A7",
        "production_captures_executed": 0,
        "immutable_after_production_outcomes": True,
    }

    # Last gate before hashing: nothing anywhere in the package may be a null or
    # a placeholder, whichever group produced it.
    _reject_placeholders(package)
    package["package_sha256"] = canonical_sha256(
        {key: value for key, value in package.items() if key != "package_sha256"}
    )
    return package


def p2_bound_source_closure(package: Mapping[str, Any]) -> str:
    """The source closure digest a P2 package actually froze. Fails closed.

    A6 binds the closure at ``bindings.AUTHORITY_AND_CODE.source_closure``. A
    consumer that reads some *other* path finds nothing, and the tempting
    recovery -- treat the live closure as the expected one -- turns the gate
    into ``live == live``, which passes for any working tree at all. That is
    strictly worse than no check, because it reads as one. So this is the single
    place that knows where the digest lives, and a binding that is missing,
    null, or malformed raises rather than returning a substitute.
    """
    binding = (package.get("bindings") or {}).get("AUTHORITY_AND_CODE") or {}
    closure = binding.get("source_closure")
    if not isinstance(closure, Mapping):
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            "the P2 package binds no AUTHORITY_AND_CODE.source_closure "
            "structure; production may not be admitted against a freeze that "
            "never recorded the code it froze",
        )
    digest = closure.get("source_closure_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            f"the P2 source-closure binding carries "
            f"source_closure_sha256={digest!r}, which is not a sha256 digest",
        )
    try:
        int(digest, 16)
    except ValueError:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            f"the P2 source-closure binding carries a non-hexadecimal digest "
            f"{digest!r}",
        ) from None
    return digest


def p2_freeze_passed(package: Mapping[str, Any]) -> bool:
    """Whether a built package is an A6 exit. Counts and bindings only."""
    return bool(
        package.get("P2_RESULT") == "PASS"
        and package.get("schema_version") == P2_FREEZE_SCHEMA_VERSION
        and list(package.get("binding_groups") or ()) == list(BINDING_GROUPS)
        and not package.get("missing_bindings")
        and not package.get("null_bindings")
        and not package.get("unverified_bindings")
        and not (package.get("verification") or {}).get("unverified")
    )


def verify_p2_freeze_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Re-check a built package independently of the producer that wrote it."""
    findings: list[str] = []
    if package.get("schema_version") != P2_FREEZE_SCHEMA_VERSION:
        findings.append("schema_version")
    if list(package.get("binding_groups") or ()) != list(BINDING_GROUPS):
        findings.append("binding_groups")
    for group in BINDING_GROUPS:
        if not (package.get("bindings") or {}).get(group):
            findings.append(f"bindings.{group}")
    recorded = package.get("package_sha256")
    recomputed = canonical_sha256(
        {key: value for key, value in package.items() if key != "package_sha256"}
    )
    if recorded != recomputed:
        findings.append("package_sha256")
    try:
        _reject_placeholders(
            {key: value for key, value in package.items() if key != "package_sha256"}
        )
    except ExperimentIIIError as error:
        findings.append(f"placeholder:{error.message}")
    return {
        "passed": not findings and p2_freeze_passed(package),
        "findings": findings,
        "recomputed_package_sha256": recomputed,
        "binding_group_count": len(BINDING_GROUPS),
    }
