"""Controlled activation intervention utilities for modifying only approved model positions and layers.

Steps 8.1-8.4. The injector adds one identical ``alpha x direction`` vector to
exactly the final context frame's 336 visual positions at one chosen decoder
layer and timestep. Action tokens, earlier frames, other positions, other
layers, other timesteps, and other batch items are left byte-identical.

The hook is scoped to a single rollout and is always removed, on success and on
failure. Alpha zero must reproduce the unmodified path exactly.

Nothing in this module inspects a rollout outcome. Direction, dose, site, layer,
timestep, and event selection are inputs, never results.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from mineocclude.activations.hooks import (
    ActivationHookError,
    FrozenHookDiscovery,
    HookErrorCode,
    NormalizedHookOutput,
    normalize_hook_output,
)
from mineocclude.activations.pool import (
    VisualTokenSelection,
    select_visual_token_positions,
)
from mineocclude.contracts.activation import VISUAL_TOKENS_PER_FRAME
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.intervention_request import (
    EXPECTED_DIRECTION_DIMENSION,
    MINEWORLD_LAYER_COUNT,
    validate_intervention_request,
)
from mineocclude.models.mineworld_adapter import FrameTokenMap

MAX_RELATIVE_ACTIVATION_NORM = 0.25

INJECTION_IDENTITY = "person-a-scoped-residual-injection-v1.0"


class InjectionErrorCode(str, Enum):
    """Stable reasons an injection is refused or aborted."""

    INVALID_REQUEST = "invalid_request"
    REJECTED_REQUEST = "rejected_request"
    INVALID_DIRECTION = "invalid_direction"
    INVALID_ALPHA = "invalid_alpha"
    CAP_EXCEEDED = "cap_exceeded"
    INVALID_SITE = "invalid_site"
    INVALID_TIMESTEP = "invalid_timestep"
    HELDOUT_SEPARATION = "heldout_separation"
    SHAPE_MISMATCH = "shape_mismatch"
    HIDDEN_SIZE_MISMATCH = "hidden_size_mismatch"
    BATCH_UNSUPPORTED = "batch_unsupported"
    MANAGER_STATE = "manager_state"
    CLEANUP_FAILED = "cleanup_failed"
    TORCH_UNAVAILABLE = "torch_unavailable"


class InjectionError(RuntimeError):
    """Actionable, coded intervention failure."""

    def __init__(self, code: InjectionErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: InjectionErrorCode, message: str) -> None:
    raise InjectionError(code, message)


def _import_torch() -> Any:
    try:
        import torch  # noqa: PLC0415 - optional heavy dependency
    except ImportError as error:  # pragma: no cover - environment dependent
        _fail(
            InjectionErrorCode.TORCH_UNAVAILABLE,
            f"the scoped injector requires PyTorch: {error}",
        )
        raise
    return torch


# ---------------------------------------------------------------------------
# Step 8.1 — validate the request before held-out events are loaded
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestValidationReport:
    """The Step 8.1 machine-readable acceptance decision for one request."""

    accepted: bool
    request_id: str | None
    rejections: tuple[dict[str, str], ...]
    layer_idx: int | None
    timestep_idx: int | None
    hook_site: str | None
    direction_hash: str | None
    typical_activation_norm: float | None
    cap: float | None
    dose_count: int
    cap_reduced_dose_ids: tuple[str, ...]
    heldout_event_count: int
    heldout_events_inspected: bool

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": "person-a-intervention-request-validation-v0.1",
            "step": "8.1",
            "status": "ACCEPTED" if self.accepted else "REJECTED",
            "accepted": self.accepted,
            "request_id": self.request_id,
            "rejections": [dict(item) for item in self.rejections],
            "intervention_location": {
                "layer_idx": self.layer_idx,
                "timestep_idx": self.timestep_idx,
                "hook_site": self.hook_site,
            },
            "direction_hash": self.direction_hash,
            "cap": {
                "max_relative_activation_norm": self.cap,
                "typical_activation_norm": self.typical_activation_norm,
            },
            "dose_count": self.dose_count,
            "cap_reduced_dose_ids": list(self.cap_reduced_dose_ids),
            "cap_reduction_relabelled": False,
            "heldout_event_count": self.heldout_event_count,
            "heldout_outcomes_inspected": self.heldout_events_inspected,
            "validated_before_loading_events": True,
        }


def validate_request(request: Mapping[str, Any]) -> RequestValidationReport:
    """Run the frozen B-to-A contract and add Person A's own site checks.

    A rejected request is never repaired here. Cap-reduced doses are recorded
    with their identifiers so their intended effect is never silently relabelled.
    """

    if not isinstance(request, Mapping):
        _fail(InjectionErrorCode.INVALID_REQUEST, "the request must be a mapping")
    result = validate_intervention_request(request)
    rejections = tuple(
        {
            "code": getattr(item.code, "value", str(item.code)),
            "message": item.message,
        }
        for item in result.rejections
    )
    location = request.get("intervention_location")
    location = location if isinstance(location, Mapping) else {}
    cap = request.get("cap")
    cap = cap if isinstance(cap, Mapping) else {}
    metadata = request.get("direction_metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    alpha_table = request.get("alpha_table")
    alpha_table = alpha_table if isinstance(alpha_table, Sequence) else ()
    events = request.get("heldout_events")
    events = events if isinstance(events, Sequence) else ()

    extra: list[dict[str, str]] = []
    layer_idx = location.get("layer_idx")
    timestep_idx = location.get("timestep_idx")
    if not _is_index(layer_idx, MINEWORLD_LAYER_COUNT):
        extra.append(
            {
                "code": InjectionErrorCode.INVALID_SITE.value,
                "message": (
                    f"layer_idx must be an integer in [0, {MINEWORLD_LAYER_COUNT})"
                ),
            }
        )
    if not _is_index(timestep_idx, None):
        extra.append(
            {
                "code": InjectionErrorCode.INVALID_TIMESTEP.value,
                "message": "timestep_idx must be a non-negative integer",
            }
        )
    if not events:
        extra.append(
            {
                "code": InjectionErrorCode.HELDOUT_SEPARATION.value,
                "message": "the request must name its held-out evaluation events",
            }
        )
    policy = request.get("selection_policy")
    policy = policy if isinstance(policy, Mapping) else {}
    if policy.get("used_heldout_outcomes_to_select_direction") is not False:
        extra.append(
            {
                "code": InjectionErrorCode.HELDOUT_SEPARATION.value,
                "message": (
                    "the request must declare that held-out outcomes did not "
                    "select the direction"
                ),
            }
        )

    all_rejections = (*rejections, *extra)
    return RequestValidationReport(
        accepted=bool(result.accepted) and not extra,
        request_id=(
            str(request.get("request_id"))
            if request.get("request_id") is not None
            else None
        ),
        rejections=all_rejections,
        layer_idx=layer_idx if isinstance(layer_idx, int) else None,
        timestep_idx=timestep_idx if isinstance(timestep_idx, int) else None,
        hook_site=(
            str(location.get("hook_site"))
            if location.get("hook_site") is not None
            else None
        ),
        direction_hash=(
            str(metadata.get("direction_hash"))
            if metadata.get("direction_hash") is not None
            else None
        ),
        typical_activation_norm=_maybe_float(cap.get("typical_activation_norm")),
        cap=_maybe_float(cap.get("max_relative_activation_norm")),
        dose_count=len(alpha_table),
        cap_reduced_dose_ids=tuple(
            str(entry.get("dose_id"))
            for entry in alpha_table
            if isinstance(entry, Mapping) and entry.get("cap_reduced")
        ),
        heldout_event_count=len(events),
        heldout_events_inspected=False,
    )


def _is_index(value: Any, exclusive_upper: int | None) -> bool:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return False
    return exclusive_upper is None or value < exclusive_upper


def _maybe_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


# ---------------------------------------------------------------------------
# Step 8.4 — dose mathematics and the 0.25 cap
# ---------------------------------------------------------------------------


def perturbation_norm(alpha: float, direction_norm: float = 1.0) -> float:
    """Return the L2 norm of the applied perturbation vector."""

    return abs(float(alpha)) * float(direction_norm)


def relative_perturbation_norm(
    alpha: float,
    typical_activation_norm: float,
    *,
    direction_norm: float = 1.0,
) -> float:
    """Return the perturbation norm relative to the typical activation norm."""

    if (
        isinstance(typical_activation_norm, bool)
        or not isinstance(typical_activation_norm, (int, float))
        or not math.isfinite(float(typical_activation_norm))
        or float(typical_activation_norm) <= 0.0
    ):
        _fail(
            InjectionErrorCode.INVALID_ALPHA,
            "typical_activation_norm must be a positive finite number",
        )
    return perturbation_norm(alpha, direction_norm) / float(typical_activation_norm)


def audit_cap(
    alpha: float,
    typical_activation_norm: float,
    *,
    direction_norm: float = 1.0,
    cap: float = MAX_RELATIVE_ACTIVATION_NORM,
) -> dict[str, Any]:
    """Report the dose against the cap without silently rescaling it."""

    relative = relative_perturbation_norm(
        alpha, typical_activation_norm, direction_norm=direction_norm
    )
    return {
        "alpha": float(alpha),
        "direction_norm": float(direction_norm),
        "perturbation_norm": perturbation_norm(alpha, direction_norm),
        "typical_activation_norm": float(typical_activation_norm),
        "relative_perturbation_norm": relative,
        "cap": float(cap),
        "within_cap": relative <= float(cap) + 1e-12,
    }


def enforce_cap(
    alpha: float,
    typical_activation_norm: float,
    *,
    direction_norm: float = 1.0,
    cap: float = MAX_RELATIVE_ACTIVATION_NORM,
) -> dict[str, Any]:
    """Raise when a dose exceeds the frozen cap rather than quietly reducing it."""

    report = audit_cap(
        alpha, typical_activation_norm, direction_norm=direction_norm, cap=cap
    )
    if not report["within_cap"]:
        _fail(
            InjectionErrorCode.CAP_EXCEEDED,
            f"relative perturbation norm {report['relative_perturbation_norm']:.6f} "
            f"exceeds the frozen cap {cap}",
        )
    return report


# ---------------------------------------------------------------------------
# Step 8.2/8.3 — the scoped residual injector
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InjectionPlan:
    """Exactly which positions, layer, and timestep one rollout may modify."""

    trajectory_id: str
    model_frame_idx: int
    layer_idx: int
    timestep_idx: int
    hook_site: str
    positions: tuple[int, ...]
    sequence_length: int
    alpha: float

    def __post_init__(self) -> None:
        if len(self.positions) != VISUAL_TOKENS_PER_FRAME:
            _fail(
                InjectionErrorCode.INVALID_SITE,
                f"an injection plan must cover exactly {VISUAL_TOKENS_PER_FRAME} "
                f"visual positions, not {len(self.positions)}",
            )
        if len(set(self.positions)) != len(self.positions):
            _fail(
                InjectionErrorCode.INVALID_SITE,
                "injection positions must be unique",
            )
        if any(
            not isinstance(p, int) or isinstance(p, bool) or not 0 <= p < self.sequence_length
            for p in self.positions
        ):
            _fail(
                InjectionErrorCode.INVALID_SITE,
                "injection positions must lie inside the hooked sequence",
            )
        if not _is_index(self.layer_idx, MINEWORLD_LAYER_COUNT):
            _fail(
                InjectionErrorCode.INVALID_SITE,
                f"layer_idx must be in [0, {MINEWORLD_LAYER_COUNT})",
            )
        if not _is_index(self.timestep_idx, None):
            _fail(
                InjectionErrorCode.INVALID_TIMESTEP,
                "timestep_idx must be a non-negative integer",
            )
        if (
            isinstance(self.alpha, bool)
            or not isinstance(self.alpha, (int, float))
            or not math.isfinite(float(self.alpha))
        ):
            _fail(InjectionErrorCode.INVALID_ALPHA, "alpha must be a finite number")

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "injection_identity": INJECTION_IDENTITY,
            "trajectory_id": self.trajectory_id,
            "model_frame_idx": self.model_frame_idx,
            "layer_idx": self.layer_idx,
            "timestep_idx": self.timestep_idx,
            "hook_site": self.hook_site,
            "alpha": float(self.alpha),
            "sequence_length": self.sequence_length,
            "selected_position_count": len(self.positions),
            "selected_positions": list(self.positions),
        }


def build_injection_plan(
    frame_token_map: FrameTokenMap,
    *,
    trajectory_id: str,
    layer_idx: int,
    timestep_idx: int,
    hook_site: str,
    alpha: float,
    hooked_sequence_length: int,
    final_context_frame_idx: int | None = None,
) -> InjectionPlan:
    """Select the final context frame's visual positions and nothing else.

    When ``final_context_frame_idx`` is omitted the highest model frame present
    in the map is used, which is the final context frame by construction.
    """

    if final_context_frame_idx is None:
        final_context_frame_idx = max(
            span.identity.model_frame_idx for span in frame_token_map.spans
        )
    selection: VisualTokenSelection = select_visual_token_positions(
        frame_token_map,
        trajectory_id=trajectory_id,
        model_frame_idx=final_context_frame_idx,
        hooked_sequence_length=hooked_sequence_length,
    )
    return InjectionPlan(
        trajectory_id=trajectory_id,
        model_frame_idx=final_context_frame_idx,
        layer_idx=layer_idx,
        timestep_idx=timestep_idx,
        hook_site=hook_site,
        positions=selection.positions,
        sequence_length=selection.sequence_length,
        alpha=alpha,
    )


class ScopedInjectionHook:
    """A single-use forward hook that modifies exactly one plan's positions.

    The hook registers on one decoder layer, fires on one timestep, adds the
    identical perturbation vector to each selected position, and removes itself
    on both success and failure.
    """

    def __init__(
        self,
        discovery: FrozenHookDiscovery,
        plan: InjectionPlan,
        direction: Any,
        *,
        output_normalizer: Any = normalize_hook_output,
    ) -> None:
        if not isinstance(discovery, FrozenHookDiscovery):
            raise ActivationHookError(
                HookErrorCode.INVALID_DISCOVERY,
                "ScopedInjectionHook requires FrozenHookDiscovery",
            )
        if not isinstance(plan, InjectionPlan):
            _fail(
                InjectionErrorCode.INVALID_REQUEST,
                "ScopedInjectionHook requires an InjectionPlan",
            )
        self._discovery = discovery
        self._plan = plan
        self._direction = direction
        self._normalizer = output_normalizer
        self._handle: Any = None
        self._entered = False
        self._closed = False
        self._call_count = 0
        self._applied_call_index: int | None = None
        self._observations: list[dict[str, Any]] = []

    # -- lifecycle -------------------------------------------------------

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def applied(self) -> bool:
        return self._applied_call_index is not None

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def registered_hook_count(self) -> int:
        return 0 if self._handle is None else 1

    @property
    def observations(self) -> Sequence[Mapping[str, Any]]:
        return tuple(MappingProxyType(item) for item in self._observations)

    def __enter__(self) -> ScopedInjectionHook:  # noqa: PYI034
        if self._entered:
            _fail(
                InjectionErrorCode.MANAGER_STATE,
                "the injection hook is single-use and cannot be re-entered",
            )
        self._entered = True
        layers = list(self._discovery.iter_runtime_layers())
        try:
            layer, module = layers[self._plan.layer_idx]
        except IndexError:  # pragma: no cover - guarded by InjectionPlan
            self.close()
            _fail(
                InjectionErrorCode.INVALID_SITE,
                f"layer {self._plan.layer_idx} is not present in the discovery",
            )
            raise
        register = getattr(module, "register_forward_hook", None)
        if not callable(register):
            self.close()
            raise ActivationHookError(
                HookErrorCode.REGISTRATION_FAILED,
                "discovered module no longer supports forward hooks",
                layer_idx=layer.layer_idx,
            )
        try:
            self._handle = register(self._callback)
        except Exception as error:  # noqa: BLE001
            self.close()
            raise error
        if not callable(getattr(self._handle, "remove", None)):
            self.close()
            raise ActivationHookError(
                HookErrorCode.REGISTRATION_FAILED,
                "register_forward_hook returned a handle without remove()",
                layer_idx=layer.layer_idx,
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        del exc_type, traceback
        self.close()
        return False

    def close(self) -> None:
        """Remove the hook exactly once, on success or failure."""

        if self._closed:
            return
        handle, self._handle = self._handle, None
        if handle is not None:
            try:
                handle.remove()
            except Exception as error:  # noqa: BLE001
                self._handle = handle
                _fail(
                    InjectionErrorCode.CLEANUP_FAILED,
                    f"the injection hook could not be removed: {error}",
                )
        self._closed = True

    # -- the modification ------------------------------------------------

    def _callback(self, _module: object, _inputs: object, output: object) -> Any:
        if self._closed:
            _fail(
                InjectionErrorCode.MANAGER_STATE,
                "an injection callback arrived after the hook was removed",
            )
        call_index = self._call_count
        self._call_count += 1
        normalized: NormalizedHookOutput = self._normalizer(output)
        if call_index != self._plan.timestep_idx:
            self._observations.append(
                {
                    "call_index": call_index,
                    "applied": False,
                    "reason": "call index is not the selected timestep",
                }
            )
            return output
        modified = self._apply(normalized)
        self._applied_call_index = call_index
        self._observations.append(
            {
                "call_index": call_index,
                "applied": True,
                "shape": list(normalized.shape),
                "container_kind": normalized.container_kind,
            }
        )
        return _rewrap(output, normalized, modified)

    def _apply(self, normalized: NormalizedHookOutput) -> Any:
        torch = _import_torch()
        tensor = normalized.tensor
        if normalized.hidden_size != EXPECTED_DIRECTION_DIMENSION:
            _fail(
                InjectionErrorCode.HIDDEN_SIZE_MISMATCH,
                f"hidden size {normalized.hidden_size} does not match the frozen "
                f"direction dimension {EXPECTED_DIRECTION_DIMENSION}",
            )
        if normalized.sequence_length != self._plan.sequence_length:
            _fail(
                InjectionErrorCode.SHAPE_MISMATCH,
                f"hooked sequence length {normalized.sequence_length} does not "
                f"match the plan's {self._plan.sequence_length}",
            )
        if normalized.batch_size != 1:
            _fail(
                InjectionErrorCode.BATCH_UNSUPPORTED,
                "the scoped injector supports exactly one batch item per rollout",
            )
        direction = torch.as_tensor(self._direction)
        if tuple(direction.shape) != (EXPECTED_DIRECTION_DIMENSION,):
            _fail(
                InjectionErrorCode.INVALID_DIRECTION,
                f"the direction must have shape ({EXPECTED_DIRECTION_DIMENSION},), "
                f"not {tuple(direction.shape)}",
            )
        # Convert explicitly; never let the addition change dtype or device.
        perturbation = (
            direction.to(device=tensor.device, dtype=tensor.dtype)
            * torch.as_tensor(
                float(self._plan.alpha), device=tensor.device, dtype=tensor.dtype
            )
        )
        index = torch.as_tensor(
            list(self._plan.positions), device=tensor.device, dtype=torch.long
        )
        modified = tensor.clone()
        modified[:, index, :] = modified[:, index, :] + perturbation
        if modified.shape != tensor.shape:  # pragma: no cover - defensive
            _fail(
                InjectionErrorCode.SHAPE_MISMATCH,
                "the injection changed the residual tensor shape",
            )
        if modified.dtype != tensor.dtype or modified.device != tensor.device:
            _fail(
                InjectionErrorCode.SHAPE_MISMATCH,
                "the injection changed the residual dtype or device",
            )
        return modified

    def audit(self) -> dict[str, Any]:
        """Report what this hook actually did, for the rollout's evidence."""

        return {
            "schema_version": "person-a-scoped-injection-audit-v0.1",
            "step": "8.2",
            "plan": self._plan.to_document(),
            "call_count": self._call_count,
            "applied": self.applied,
            "applied_call_index": self._applied_call_index,
            "observations": [dict(item) for item in self._observations],
            "hook_removed": self._closed,
            "registered_hook_count": self.registered_hook_count,
        }


def _rewrap(original: object, normalized: NormalizedHookOutput, tensor: Any) -> Any:
    """Return the output in exactly the structure the layer produced."""

    if normalized.container_kind == "direct_tensor":
        return tensor
    if normalized.container_kind == "tuple":
        parts = list(original)  # type: ignore[arg-type]
        parts[normalized.tuple_index or 0] = tensor
        return tuple(parts)
    if normalized.container_kind == "structured":
        updated = dict(original)  # type: ignore[arg-type]
        updated[normalized.structured_field or "last_hidden_state"] = tensor
        return updated
    _fail(  # pragma: no cover - normalize_hook_output constrains the kinds
        InjectionErrorCode.SHAPE_MISMATCH,
        f"unsupported hook output container {normalized.container_kind!r}",
    )
    raise AssertionError  # pragma: no cover


# ---------------------------------------------------------------------------
# Step 8.2/8.4 — direct tensor proofs
# ---------------------------------------------------------------------------


def difference_mask(before: Any, after: Any) -> Any:
    """Return the boolean mask of positions whose residual actually changed."""

    torch = _import_torch()
    before_tensor = torch.as_tensor(before)
    after_tensor = torch.as_tensor(after)
    if before_tensor.shape != after_tensor.shape:
        _fail(
            InjectionErrorCode.SHAPE_MISMATCH,
            "before and after tensors must share one shape",
        )
    return (after_tensor - before_tensor).ne(0).any(dim=-1)


def changed_positions(before: Any, after: Any) -> tuple[int, ...]:
    """Return the sorted sequence positions whose residual vector changed."""

    mask = difference_mask(before, after)
    if mask.dim() == 2:
        mask = mask.any(dim=0)
    return tuple(int(index) for index in mask.nonzero().flatten().tolist())


def pooled_visual_change(
    before: Any,
    after: Any,
    positions: Sequence[int],
) -> Any:
    """Return the change in the mean-pooled visual vector for one frame."""

    torch = _import_torch()
    before_tensor = torch.as_tensor(before)
    after_tensor = torch.as_tensor(after)
    index = torch.as_tensor(list(positions), dtype=torch.long)
    pooled_before = before_tensor[..., index, :].to(torch.float64).mean(dim=-2)
    pooled_after = after_tensor[..., index, :].to(torch.float64).mean(dim=-2)
    return pooled_after - pooled_before


def audit_pooled_change_identity(
    before: Any,
    after: Any,
    positions: Sequence[int],
    direction: Any,
    alpha: float,
    *,
    rtol: float = 1e-3,
    atol: float = 1e-3,
) -> dict[str, Any]:
    """Prove the pooled change equals ``alpha x direction`` within tolerance.

    Adding the same vector to every pooled position must move the mean by
    exactly that vector times alpha; this is the numerical identity Step 8.4
    requires before any generated video is interpreted.
    """

    torch = _import_torch()
    observed = pooled_visual_change(before, after, positions)
    expected = torch.as_tensor(direction).to(torch.float64) * float(alpha)
    if observed.dim() == 2:
        observed = observed[0]
    difference = (observed - expected).abs()
    max_abs = float(difference.max().item()) if difference.numel() else 0.0
    matches = bool(
        torch.allclose(observed, expected, rtol=rtol, atol=atol)
    )
    return {
        "schema_version": "person-a-pooled-change-identity-v0.1",
        "step": "8.4",
        "alpha": float(alpha),
        "position_count": len(positions),
        "max_absolute_difference": max_abs,
        "rtol": rtol,
        "atol": atol,
        "identity_holds": matches,
        "expected_l2_norm": float(expected.norm().item()),
        "observed_l2_norm": float(observed.norm().item()),
    }


__all__ = [
    "INJECTION_IDENTITY",
    "MAX_RELATIVE_ACTIVATION_NORM",
    "InjectionError",
    "InjectionErrorCode",
    "InjectionPlan",
    "RequestValidationReport",
    "ScopedInjectionHook",
    "audit_cap",
    "audit_pooled_change_identity",
    "build_injection_plan",
    "changed_positions",
    "difference_mask",
    "enforce_cap",
    "perturbation_norm",
    "pooled_visual_change",
    "relative_perturbation_norm",
    "validate_request",
]
