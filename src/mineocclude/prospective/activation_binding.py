#!/usr/bin/env python3
"""What binds an activation artifact to the model and the rows that produced it.

Two independent holes were found in the Stage-2 extraction path during the
post-freeze rehearsal at ``c9aad3e``. Both let extraction succeed while emitting
a receipt that could not prove what it had actually done, so both are repaired
here, in one governed module, rather than as two local patches.

NEW-B001 -- the checkpoint binding failed OPEN
==============================================

``p2d_extract`` recorded::

    "checkpoint_sha256": getattr(runtime, "checkpoint_sha256", None)
                         or str(getattr(runtime, "checkpoint_identity", ""))

Neither attribute exists. :class:`~mineocclude.models.mineworld_adapter.MineWorldRuntimeIdentity`
exposes ``main_checkpoint_sha256`` and ``vae_checkpoint_sha256`` as two distinct
digests, because the runtime really is two frozen artifacts. The expression
therefore evaluated to ``""`` on every real runtime, and the receipt asserted a
checkpoint binding it did not have. Real activations were extracted; nothing
tied them cryptographically to the weights that produced them.

The repair does not rename a field. A single generic ``checkpoint_sha256`` would
be a *worse* lie than the blank one, because it would have to pick one of two
digests and silently discard the other. :func:`model_runtime_identity_binding`
records the complete project-owned runtime identity and refuses to return
anything at all when a required digest is missing, blank, or malformed.

NEW-B002 -- the target rows were inferred, never proved
=======================================================

Extraction selected its scientific rows with ``visibility.tau in 1..19`` while
physical gating and the frozen manifest use ``unit["target_model_frame_indices"]``.
Both derive from the same upstream artifact today -- the capture writes ``tau``
*from* the manifest's indices -- so they agreed throughout the rehearsal. That
agreement was a coincidence of construction, not a checked property: a stale
``visibility.jsonl``, a re-derived capture, or a manifest edit between capture
and extraction would have moved one and not the other, and extraction would have
consumed a row set the physical gate never qualified.

:func:`resolve_authority_bound_target_rows` keeps the tau lookup -- it is the
operationally useful one, since it reads the rows the capture actually wrote --
and then *proves* it equals the authority's set, exactly and in order. Neither
source wins on disagreement: the resolver raises, before any activation is read.

Everything here is fail-closed and pure: no model is imported, no file is read,
no network call is made, so the whole module is exercisable against fixtures.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mineocclude.prospective.development_workflow import EvidenceError

#: Digest fields of the loaded runtime. Every one must be a real lowercase
#: SHA-256; a blank or short value is what NEW-B001 actually emitted, so the
#: shape check is the whole point rather than a formality.
REQUIRED_IDENTITY_DIGESTS = (
    "main_checkpoint_sha256",
    "vae_checkpoint_sha256",
    "model_config_sha256",
    "vae_config_sha256",
    "environment_report_sha256",
)

#: Non-digest identity fields. These answer "which adapter, which architecture,
#: which preprocessing" -- a correct pair of checkpoint hashes under a different
#: preprocessing profile is still a different activation.
REQUIRED_IDENTITY_TEXT = (
    "runtime_id",
    "schema_version",
    "adapter_api_version",
    "mineocclude_revision",
    "mineworld_source_revision",
    "modelscope_asset_revision",
    "preprocessing_identity",
    "action_conversion_identity",
    "model_class",
    "transformer_class",
    "vae_class",
    "decoder_layer_path",
    "precision",
)

#: Architectural integers that must match for two activations to be comparable.
REQUIRED_IDENTITY_INTEGERS = (
    "layer_count",
    "hidden_size",
    "visual_tokens_per_frame",
    "tokens_per_pair",
    "max_context_pairs",
)

#: The complete binding key set an activation receipt must carry.
ACTIVATION_IDENTITY_FIELDS = (
    REQUIRED_IDENTITY_DIGESTS + REQUIRED_IDENTITY_TEXT + REQUIRED_IDENTITY_INTEGERS
)


class _Unbound:
    """Explicit marker for a caller with no authority-selected row set.

    Spelled as an object rather than ``None`` so that it can never be produced by
    a missing key, a default argument, or a JSON round trip. The two historical
    pilot entrypoints (the completed P2 twenty-five-run diagnostic and the
    completed P3 sequential campaign) pass it deliberately, and every Stage-2
    consumer refuses a record it produced.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "TARGET_ROWS_NOT_AUTHORITY_BOUND"


#: See :class:`_Unbound`. Grep for this name to find every unbound extraction.
TARGET_ROWS_NOT_AUTHORITY_BOUND = _Unbound()


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value):
        raise EvidenceError(
            f"activation identity field {name!r} is not a lowercase SHA-256: {value!r}")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"activation identity field {name!r} is blank or absent")
    return value


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EvidenceError(f"activation identity field {name!r} is not a positive integer")
    return value


def model_runtime_identity_binding(runtime: Any) -> dict[str, Any]:
    """Extract the complete, fail-closed model identity from a loaded runtime.

    Accepts anything exposing the attributes -- the real
    ``MineWorldRuntimeIdentity`` dataclass, or a fixture shaped like it -- so the
    binding can be tested without standing up a checkpoint. Raises rather than
    returning a partial record: a receipt with one blank digest is the defect
    this function exists to make impossible.
    """
    binding: dict[str, Any] = {}
    for name in REQUIRED_IDENTITY_DIGESTS:
        binding[name] = _digest(getattr(runtime, name, None), name)
    for name in REQUIRED_IDENTITY_TEXT:
        binding[name] = _text(getattr(runtime, name, None), name)
    for name in REQUIRED_IDENTITY_INTEGERS:
        binding[name] = _integer(getattr(runtime, name, None), name)
    if binding["main_checkpoint_sha256"] == binding["vae_checkpoint_sha256"]:
        # The transformer and the VAE are distinct frozen artifacts. Equal
        # digests mean one value was copied into both slots, which is precisely
        # the single-generic-hash failure this module refuses to produce.
        raise EvidenceError(
            "main and VAE checkpoint digests are identical; the two frozen "
            "artifacts cannot have the same bytes")
    return binding


def require_activation_identity(record: Mapping[str, Any], *,
                                label: str = "activation receipt") -> dict[str, Any]:
    """Refuse an activation record whose model identity is absent or malformed."""
    if not isinstance(record, Mapping):
        raise EvidenceError(f"{label} is not a mapping")
    identity = record.get("model_runtime_identity")
    if not isinstance(identity, Mapping):
        raise EvidenceError(f"{label} carries no model runtime identity")
    missing = [name for name in ACTIVATION_IDENTITY_FIELDS if name not in identity]
    if missing:
        raise EvidenceError(f"{label} model identity is incomplete: {sorted(missing)}")
    for name in REQUIRED_IDENTITY_DIGESTS:
        _digest(identity.get(name), name)
    for name in REQUIRED_IDENTITY_TEXT:
        _text(identity.get(name), name)
    for name in REQUIRED_IDENTITY_INTEGERS:
        _integer(identity.get(name), name)
    # The two digests are also promoted to the top level of the record so a
    # verifier never has to reach through a nested map to find the thing that
    # matters most. They must agree with the nested identity they summarize.
    for name in ("main_checkpoint_sha256", "vae_checkpoint_sha256"):
        if record.get(name) != identity[name]:
            raise EvidenceError(
                f"{label} top-level {name} disagrees with its model runtime identity")
    return dict(identity)


def verify_activation_checkpoint_binding(record: Mapping[str, Any],
                                         expected: Mapping[str, Any], *,
                                         label: str = "activation receipt") -> None:
    """Refuse unless the record was produced by exactly the expected model.

    ``expected`` is another identity binding -- typically the first accepted
    unit's, so a campaign cannot silently change checkpoints partway through.
    Every field is compared, not just the two checkpoint digests, because a
    matching pair of weights under a different preprocessing profile or adapter
    revision still yields different activations.
    """
    observed = require_activation_identity(record, label=label)
    reference = require_activation_identity(
        {"model_runtime_identity": expected,
         "main_checkpoint_sha256": dict(expected).get("main_checkpoint_sha256"),
         "vae_checkpoint_sha256": dict(expected).get("vae_checkpoint_sha256")},
        label="expected model identity")
    differing = sorted(name for name in ACTIVATION_IDENTITY_FIELDS
                       if observed[name] != reference[name])
    if differing:
        raise EvidenceError(
            f"{label} was produced by a different model runtime; fields differ: {differing}")


def resolve_authority_bound_target_rows(
        visibility_rows: Sequence[Mapping[str, Any]], *,
        expected: Sequence[int] | _Unbound,
        required_count: int,
        trajectory_id: str | None = None,
        label: str = "extraction unit") -> list[int]:
    """Resolve the scientific target rows and prove they are the authority's.

    The tau lookup is preserved: the rows returned are the ones the capture
    itself labelled ``tau = 1..required_count``, in tau order, which is what the
    extractor must actually index. What is new is that they are then compared to
    ``expected`` -- the frozen manifest's ``target_model_frame_indices`` -- for
    exact ordered equality before anything downstream is allowed to read a frame.

    Refuses on: wrong count, a duplicated tau, a missing tau, a duplicated frame
    index, non-monotonic frames, a row bound to a different trajectory, a row
    whose temporal identity is internally inconsistent, and -- last, so the more
    specific diagnoses fire first -- any inequality with ``expected``.
    """
    if not isinstance(visibility_rows, Sequence) or isinstance(visibility_rows, (str, bytes)):
        raise EvidenceError(f"{label}: visibility evidence is not a sequence of rows")
    wanted = list(range(1, required_count + 1))
    by_tau: dict[int, Mapping[str, Any]] = {}
    for row in visibility_rows:
        if not isinstance(row, Mapping):
            raise EvidenceError(f"{label}: visibility row is malformed")
        tau = row.get("tau")
        if isinstance(tau, bool) or not isinstance(tau, int) or tau not in wanted:
            continue
        if tau in by_tau:
            raise EvidenceError(f"{label}: tau {tau} is claimed by more than one visibility row")
        by_tau[tau] = row
    absent = [tau for tau in wanted if tau not in by_tau]
    if absent:
        raise EvidenceError(
            f"{label}: visibility evidence is missing target rows for tau {absent}")

    resolved: list[int] = []
    for tau in wanted:
        row = by_tau[tau]
        frame = row.get("model_frame_idx")
        if isinstance(frame, bool) or not isinstance(frame, int):
            raise EvidenceError(f"{label}: tau {tau} has no integer model_frame_idx")
        # Temporal binding. The capture writes one integer into every clock
        # column of a row; a row where they disagree is not a row whose frame
        # index can be trusted to name the tick the label was computed at.
        for column in ("server_tick", "render_frame_idx"):
            if column in row and row.get(column) != frame:
                raise EvidenceError(
                    f"{label}: tau {tau} temporal binding is inconsistent "
                    f"({column}={row.get(column)!r}, model_frame_idx={frame!r})")
        if trajectory_id is not None and "trajectory_id" in row \
                and row.get("trajectory_id") != trajectory_id:
            raise EvidenceError(
                f"{label}: tau {tau} is bound to trajectory {row.get('trajectory_id')!r}, "
                f"not {trajectory_id!r}")
        resolved.append(frame)

    if len(set(resolved)) != len(resolved):
        raise EvidenceError(f"{label}: target rows contain a duplicated model frame index")
    if resolved != sorted(resolved):
        raise EvidenceError(f"{label}: target rows are not in ascending frame order")

    if isinstance(expected, _Unbound):
        # An explicit, greppable opt-out for the two completed historical pilot
        # entrypoints. Every Stage-2 consumer refuses the record this produces,
        # so it cannot reach a scientific readout.
        return resolved
    if not isinstance(expected, Sequence) or isinstance(expected, (str, bytes)):
        raise EvidenceError(f"{label}: authority target rows are not a sequence")
    authority_rows = list(expected)
    if len(authority_rows) != required_count:
        raise EvidenceError(
            f"{label}: authority declares {len(authority_rows)} target rows, "
            f"not {required_count}")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in authority_rows):
        raise EvidenceError(f"{label}: authority target rows are not all integers")
    if len(set(authority_rows)) != len(authority_rows):
        raise EvidenceError(f"{label}: authority target rows contain a duplicate")
    if resolved != authority_rows:
        raise EvidenceError(
            f"{label}: resolved target rows do not equal the authority's. "
            f"resolved={resolved} authority={authority_rows}")
    return resolved


def require_target_rows_authority_bound(record: Mapping[str, Any],
                                        expected: Sequence[int], *,
                                        label: str = "activation receipt") -> None:
    """Refuse an activation record that was not proved against the authority.

    This is the downstream half of the NEW-B002 repair: even a record produced by
    an unbound historical pilot run carries ``target_rows_authority_bound: false``
    and is refused here, so the sentinel can never leak into a scientific readout.
    """
    if record.get("target_rows_authority_bound") is not True:
        raise EvidenceError(
            f"{label}: activations were extracted without an authority-bound target row set")
    observed = record.get("targets")
    if not isinstance(observed, list) or observed != list(expected):
        raise EvidenceError(
            f"{label}: recorded target rows do not equal the frozen manifest's")
