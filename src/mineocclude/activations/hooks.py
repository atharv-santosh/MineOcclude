"""Discover verified MineWorld decoder sites and capture them safely.

Phase 4 Wave 1 owns discovery and temporary hook lifetime only. It does not
choose scientific layers, pool tensors, write activation storage, or mutate a
model's output.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from numbers import Integral
from types import MappingProxyType

EXPECTED_DECODER_LAYER_COUNT = 20
PINNED_MINEWORLD_SOURCE_REVISION = (
    "9f49efbcc68a5f0cf60e78f0abc566eac409282f"
)
CONCEPTUAL_HOOK_SITE = "decoder_layer_output_residual_stream"
HOOK_DISCOVERY_VERSION = (
    "person-a-phase4-decoder-output-v1.0:"
    f"{PINNED_MINEWORLD_SOURCE_REVISION}"
)

_INDEXED_MODULE_NAME = re.compile(
    r"^(?P<parent>.+)\.(?P<layer_idx>0|[1-9][0-9]*)$"
)
_STRUCTURED_RESIDUAL_FIELD = "last_hidden_state"


class HookErrorCode(str, Enum):
    """Stable failure classifications for discovery and scoped capture."""

    NAMED_MODULES_UNAVAILABLE = "named_modules_unavailable"
    DUPLICATE_MODULE_NAME = "duplicate_module_name"
    LAYER_COUNT_MISMATCH = "layer_count_mismatch"
    INVALID_LAYER_INDICES = "invalid_layer_indices"
    AMBIGUOUS_LAYER_GROUP = "ambiguous_layer_group"
    INCONSISTENT_MODULE_TYPE = "inconsistent_module_type"
    INVALID_DISCOVERY = "invalid_discovery"
    INVALID_OUTPUT = "invalid_output"
    AMBIGUOUS_OUTPUT = "ambiguous_output"
    INVALID_OUTPUT_SHAPE = "invalid_output_shape"
    INVALID_MANAGER_STATE = "invalid_manager_state"
    REGISTRATION_FAILED = "registration_failed"
    DUPLICATE_CALLBACK = "duplicate_callback"
    MISSING_CALLBACK = "missing_callback"
    INCONSISTENT_CAPTURE = "inconsistent_capture"
    CALLBACK_AFTER_CLOSE = "callback_after_close"
    CLEANUP_FAILED = "cleanup_failed"


class ActivationHookError(RuntimeError):
    """Actionable, machine-classifiable Phase 4 hook failure."""

    def __init__(
        self,
        code: HookErrorCode,
        message: str,
        *,
        layer_idx: int | None = None,
    ) -> None:
        self.code = code
        self.layer_idx = layer_idx
        prefix = f"{code.value}"
        if layer_idx is not None:
            prefix += f"[layer_idx={layer_idx}]"
        super().__init__(f"{prefix}: {message}")


def _module_type_name(module: object) -> str:
    cls = type(module)
    return f"{cls.__module__}.{cls.__qualname__}"


def _positive_tensor_shape(value: object) -> tuple[int, int, int] | None:
    raw_shape = getattr(value, "shape", None)
    if raw_shape is None:
        return None
    try:
        parts = tuple(raw_shape)
    except TypeError:
        return None
    if (
        len(parts) != 3
        or any(
            not isinstance(part, Integral)
            or isinstance(part, bool)
            or int(part) <= 0
            for part in parts
        )
    ):
        return None
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


@dataclass(frozen=True)
class HookLayerMetadata:
    """One discovered decoder layer at the frozen conceptual hook site."""

    layer_idx: int
    module_name: str
    module_type: str
    conceptual_site: str
    discovery_version: str


@dataclass(frozen=True)
class FrozenHookDiscovery:
    """Validated named-module discovery plus private runtime module handles."""

    layers: tuple[HookLayerMetadata, ...]
    module_name_pattern: str
    conceptual_site: str
    discovery_version: str
    _modules: tuple[object, ...] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        expected_indices = tuple(range(EXPECTED_DECODER_LAYER_COUNT))
        if (
            len(self.layers) != EXPECTED_DECODER_LAYER_COUNT
            or len(self._modules) != EXPECTED_DECODER_LAYER_COUNT
            or tuple(layer.layer_idx for layer in self.layers)
            != expected_indices
            or len({layer.module_name for layer in self.layers})
            != EXPECTED_DECODER_LAYER_COUNT
            or len({id(module) for module in self._modules})
            != EXPECTED_DECODER_LAYER_COUNT
            or len({layer.module_type for layer in self.layers}) != 1
            or self.conceptual_site != CONCEPTUAL_HOOK_SITE
            or self.discovery_version != HOOK_DISCOVERY_VERSION
            or any(
                layer.conceptual_site != self.conceptual_site
                or layer.discovery_version != self.discovery_version
                or layer.module_type != _module_type_name(module)
                or not callable(
                    getattr(module, "register_forward_hook", None)
                )
                for layer, module in zip(
                    self.layers,
                    self._modules,
                    strict=True,
                )
            )
        ):
            raise ActivationHookError(
                HookErrorCode.INVALID_DISCOVERY,
                "frozen discovery metadata is incomplete or inconsistent",
            )
        try:
            expected_names = tuple(
                self.module_name_pattern.format(layer_idx=index)
                for index in expected_indices
            )
        except (IndexError, KeyError, ValueError) as exc:
            raise ActivationHookError(
                HookErrorCode.INVALID_DISCOVERY,
                f"module-name pattern is invalid: {exc}",
            ) from exc
        if expected_names != tuple(layer.module_name for layer in self.layers):
            raise ActivationHookError(
                HookErrorCode.INVALID_DISCOVERY,
                "module names do not match the frozen indexed pattern",
            )

    def iter_runtime_layers(
        self,
    ) -> Iterator[tuple[HookLayerMetadata, object]]:
        """Yield metadata and runtime modules in authoritative layer order."""

        return iter(zip(self.layers, self._modules, strict=True))


def discover_decoder_hook_site(
    model: object,
    *,
    expected_layer_count: int = EXPECTED_DECODER_LAYER_COUNT,
) -> FrozenHookDiscovery:
    """Discover the one complete indexed decoder group from named_modules()."""

    if expected_layer_count != EXPECTED_DECODER_LAYER_COUNT:
        raise ActivationHookError(
            HookErrorCode.LAYER_COUNT_MISMATCH,
            f"the pinned runtime requires exactly {EXPECTED_DECODER_LAYER_COUNT} layers",
        )
    named_modules = getattr(model, "named_modules", None)
    if not callable(named_modules):
        raise ActivationHookError(
            HookErrorCode.NAMED_MODULES_UNAVAILABLE,
            "loaded model does not expose callable named_modules()",
        )
    try:
        entries = tuple(named_modules())
    except Exception as exc:
        raise ActivationHookError(
            HookErrorCode.NAMED_MODULES_UNAVAILABLE,
            f"named_modules() failed: {exc}",
        ) from exc

    seen_names: set[str] = set()
    groups: dict[str, list[tuple[int, str, object]]] = defaultdict(list)
    for entry in entries:
        if (
            not isinstance(entry, tuple)
            or len(entry) != 2
            or not isinstance(entry[0], str)
        ):
            raise ActivationHookError(
                HookErrorCode.NAMED_MODULES_UNAVAILABLE,
                "named_modules() emitted an invalid name/module pair",
            )
        name, module = entry
        if name in seen_names:
            raise ActivationHookError(
                HookErrorCode.DUPLICATE_MODULE_NAME,
                f"named_modules() emitted duplicate name {name!r}",
            )
        seen_names.add(name)
        match = _INDEXED_MODULE_NAME.fullmatch(name)
        if match is None or not callable(
            getattr(module, "register_forward_hook", None)
        ):
            continue
        groups[match.group("parent")].append(
            (int(match.group("layer_idx")), name, module)
        )

    expected_indices = set(range(expected_layer_count))
    complete_groups: list[
        tuple[str, tuple[tuple[int, str, object], ...]]
    ] = []
    noncontiguous_groups: list[str] = []
    wrong_count_groups: list[str] = []
    for parent, raw_layers in groups.items():
        indices = [layer_idx for layer_idx, _name, _module in raw_layers]
        if len(indices) != len(set(indices)):
            raise ActivationHookError(
                HookErrorCode.INVALID_LAYER_INDICES,
                f"group {parent!r} contains a duplicate layer index",
            )
        if len(indices) == expected_layer_count and set(indices) != expected_indices:
            noncontiguous_groups.append(parent)
        elif set(indices) == expected_indices and len(indices) == expected_layer_count:
            complete_groups.append(
                (parent, tuple(sorted(raw_layers, key=lambda item: item[0])))
            )
        elif 0 in indices:
            wrong_count_groups.append(parent)

    if noncontiguous_groups:
        raise ActivationHookError(
            HookErrorCode.INVALID_LAYER_INDICES,
            "indexed candidate groups are non-contiguous: "
            + ", ".join(sorted(noncontiguous_groups)),
        )
    if not complete_groups:
        detail = ", ".join(sorted(wrong_count_groups)) or "none"
        raise ActivationHookError(
            HookErrorCode.LAYER_COUNT_MISMATCH,
            "expected one complete 20-layer indexed group; "
            f"incomplete candidates: {detail}",
        )
    if len(complete_groups) != 1:
        raise ActivationHookError(
            HookErrorCode.AMBIGUOUS_LAYER_GROUP,
            "multiple complete 20-layer groups match: "
            + ", ".join(parent for parent, _layers in complete_groups),
        )

    parent, ordered = complete_groups[0]
    module_types = tuple(
        _module_type_name(module) for _index, _name, module in ordered
    )
    if len(set(module_types)) != 1:
        raise ActivationHookError(
            HookErrorCode.INCONSISTENT_MODULE_TYPE,
            f"group {parent!r} does not use one compatible module type",
        )
    modules = tuple(module for _index, _name, module in ordered)
    if len({id(module) for module in modules}) != expected_layer_count:
        raise ActivationHookError(
            HookErrorCode.INVALID_DISCOVERY,
            "the candidate group aliases one or more runtime modules",
        )
    pattern = f"{parent}.{{layer_idx}}"
    layers = tuple(
        HookLayerMetadata(
            layer_idx=index,
            module_name=name,
            module_type=module_type,
            conceptual_site=CONCEPTUAL_HOOK_SITE,
            discovery_version=HOOK_DISCOVERY_VERSION,
        )
        for (index, name, _module), module_type in zip(
            ordered,
            module_types,
            strict=True,
        )
    )
    return FrozenHookDiscovery(
        layers=layers,
        module_name_pattern=pattern,
        conceptual_site=CONCEPTUAL_HOOK_SITE,
        discovery_version=HOOK_DISCOVERY_VERSION,
        _modules=modules,
    )


@dataclass(frozen=True)
class NormalizedHookOutput:
    """An unmodified residual tensor with explicit batch/sequence/hidden axes."""

    tensor: object = field(repr=False, compare=False)
    shape: tuple[int, int, int]
    batch_size: int
    sequence_length: int
    hidden_size: int
    container_kind: str
    tuple_index: int | None = None
    structured_field: str | None = None


def normalize_hook_output(output: object) -> NormalizedHookOutput:
    """Identify one residual tensor without flattening or guessing."""

    tensor = output
    container_kind = "direct_tensor"
    tuple_index: int | None = None
    structured_field: str | None = None

    direct_shape = _positive_tensor_shape(output)
    if direct_shape is None and getattr(output, "shape", None) is not None:
        raise ActivationHookError(
            HookErrorCode.INVALID_OUTPUT_SHAPE,
            "residual tensor must have positive [batch, sequence, hidden] dimensions",
        )
    if direct_shape is None and isinstance(output, tuple):
        tensor_candidates = tuple(
            index
            for index, value in enumerate(output)
            if _positive_tensor_shape(value) is not None
        )
        if tensor_candidates != (0,):
            code = (
                HookErrorCode.AMBIGUOUS_OUTPUT
                if tensor_candidates
                else HookErrorCode.INVALID_OUTPUT
            )
            raise ActivationHookError(
                code,
                "tuple output must expose exactly one tensor at validated index 0",
            )
        tensor = output[0]
        container_kind = "tuple"
        tuple_index = 0
    elif direct_shape is None and isinstance(output, Mapping):
        tensor_fields = tuple(
            key
            for key, value in output.items()
            if _positive_tensor_shape(value) is not None
        )
        if tensor_fields != (_STRUCTURED_RESIDUAL_FIELD,):
            code = (
                HookErrorCode.AMBIGUOUS_OUTPUT
                if tensor_fields
                else HookErrorCode.INVALID_OUTPUT
            )
            raise ActivationHookError(
                code,
                "structured output must expose only unambiguous "
                f"{_STRUCTURED_RESIDUAL_FIELD!r}",
            )
        tensor = output[_STRUCTURED_RESIDUAL_FIELD]
        container_kind = "structured"
        structured_field = _STRUCTURED_RESIDUAL_FIELD
    elif direct_shape is None:
        raise ActivationHookError(
            HookErrorCode.INVALID_OUTPUT,
            "hook output does not expose a supported residual tensor",
        )

    shape = _positive_tensor_shape(tensor)
    if shape is None:
        raise ActivationHookError(
            HookErrorCode.INVALID_OUTPUT_SHAPE,
            "residual tensor must have positive [batch, sequence, hidden] dimensions",
        )
    return NormalizedHookOutput(
        tensor=tensor,
        shape=shape,
        batch_size=shape[0],
        sequence_length=shape[1],
        hidden_size=shape[2],
        container_kind=container_kind,
        tuple_index=tuple_index,
        structured_field=structured_field,
    )


@dataclass(frozen=True)
class HookCapture:
    """One layer-indexed residual-stream capture."""

    layer: HookLayerMetadata
    output: NormalizedHookOutput


class _ManagerState(str, Enum):
    NEW = "new"
    ACTIVE = "active"
    CLEANING_UP = "cleaning_up"
    CLEANUP_FAILED = "cleanup_failed"
    CLOSED = "closed"


class ScopedHookManager:
    """Single-use context manager for exactly one callback per layer."""

    def __init__(
        self,
        discovery: FrozenHookDiscovery,
        *,
        output_normalizer: Callable[
            [object], NormalizedHookOutput
        ] = normalize_hook_output,
        capture_callback: Callable[[HookCapture], None] | None = None,
    ) -> None:
        if not isinstance(discovery, FrozenHookDiscovery):
            raise ActivationHookError(
                HookErrorCode.INVALID_DISCOVERY,
                "ScopedHookManager requires FrozenHookDiscovery",
            )
        self._discovery = discovery
        self._output_normalizer = output_normalizer
        self._capture_callback = capture_callback
        self._state = _ManagerState.NEW
        self._handles: list[object] = []
        self._captures: dict[int, HookCapture] = {}
        self._normalization_identity: tuple[
            tuple[int, int, int],
            str,
            int | None,
            str | None,
        ] | None = None

    @property
    def captures(self) -> Mapping[int, HookCapture]:
        """Return an immutable layer-indexed view of this run's captures."""

        return MappingProxyType(dict(sorted(self._captures.items())))

    @property
    def closed(self) -> bool:
        return self._state is _ManagerState.CLOSED

    @property
    def registered_hook_count(self) -> int:
        return len(self._handles)

    def __enter__(self) -> ScopedHookManager:  # noqa: PYI034
        if self._state is not _ManagerState.NEW:
            raise ActivationHookError(
                HookErrorCode.INVALID_MANAGER_STATE,
                "hook manager is single-use and cannot be re-entered",
            )
        self._captures.clear()
        self._normalization_identity = None
        self._state = _ManagerState.ACTIVE
        try:
            for layer, module in self._discovery.iter_runtime_layers():
                register = getattr(module, "register_forward_hook", None)
                if not callable(register):
                    raise ActivationHookError(
                        HookErrorCode.REGISTRATION_FAILED,
                        "discovered module no longer supports forward hooks",
                        layer_idx=layer.layer_idx,
                    )
                handle = register(self._make_callback(layer))
                self._handles.append(handle)
                if not callable(getattr(handle, "remove", None)):
                    raise ActivationHookError(
                        HookErrorCode.REGISTRATION_FAILED,
                        "register_forward_hook returned a handle without remove()",
                        layer_idx=layer.layer_idx,
                    )
        except Exception as exc:  # noqa: BLE001
            self._raise_primary_after_cleanup(exc)
        if len(self._handles) != EXPECTED_DECODER_LAYER_COUNT:
            self._raise_primary_after_cleanup(
                ActivationHookError(
                    HookErrorCode.REGISTRATION_FAILED,
                    "registration did not produce exactly 20 hook handles",
                )
            )
        return self

    def _raise_primary_after_cleanup(self, primary: Exception) -> None:
        """Keep *primary* authoritative while exposing cleanup failure as cause."""

        try:
            self.close()
        except Exception as cleanup_error:
            raise primary from cleanup_error
        raise primary

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        del exc_type, traceback
        if exc_value is not None:
            try:
                self.close()
            except Exception as cleanup_error:
                raise exc_value from cleanup_error
            return False
        try:
            if self._state is _ManagerState.ACTIVE:
                self.require_complete()
        except Exception as exc:  # noqa: BLE001
            self._raise_primary_after_cleanup(exc)
        self.close()
        return False

    def _make_callback(
        self,
        layer: HookLayerMetadata,
    ) -> Callable[[object, object, object], None]:
        def capture(
            _module: object,
            _inputs: object,
            output: object,
        ) -> None:
            if self._state is not _ManagerState.ACTIVE:
                raise ActivationHookError(
                    HookErrorCode.CALLBACK_AFTER_CLOSE,
                    "hook callback arrived outside the active context",
                    layer_idx=layer.layer_idx,
                )
            if layer.layer_idx in self._captures:
                self._raise_primary_after_cleanup(
                    ActivationHookError(
                        HookErrorCode.DUPLICATE_CALLBACK,
                        "one layer emitted more than one callback",
                        layer_idx=layer.layer_idx,
                    )
                )
            try:
                normalized = self._output_normalizer(output)
                identity = (
                    normalized.shape,
                    normalized.container_kind,
                    normalized.tuple_index,
                    normalized.structured_field,
                )
                if self._normalization_identity is None:
                    self._normalization_identity = identity
                elif self._normalization_identity != identity:
                    raise ActivationHookError(
                        HookErrorCode.INCONSISTENT_CAPTURE,
                        "capture shape or normalization site differs across layers",
                        layer_idx=layer.layer_idx,
                    )
                captured = HookCapture(layer=layer, output=normalized)
                self._captures[layer.layer_idx] = captured
                if self._capture_callback is not None:
                    self._capture_callback(captured)
            except Exception as exc:  # noqa: BLE001
                self._raise_primary_after_cleanup(exc)

        return capture

    def require_complete(self) -> Mapping[int, HookCapture]:
        """Fail unless every intended layer emitted exactly once."""

        expected = set(range(EXPECTED_DECODER_LAYER_COUNT))
        observed = set(self._captures)
        if observed != expected:
            raise ActivationHookError(
                HookErrorCode.MISSING_CALLBACK,
                "capture set differs from expected layers; "
                f"missing={sorted(expected - observed)}, "
                f"unexpected={sorted(observed - expected)}",
            )
        return self.captures

    def close(self) -> None:
        """Remove every hook, retaining unresolved handles for a later retry."""

        if self._state is _ManagerState.CLOSED:
            return
        if self._state is _ManagerState.CLEANING_UP:
            raise ActivationHookError(
                HookErrorCode.CLEANUP_FAILED,
                "hook cleanup is already in progress",
            )
        self._state = _ManagerState.CLEANING_UP
        unresolved_in_cleanup_order: list[object] = []
        failures: list[str] = []
        for handle in reversed(self._handles):
            remove = getattr(handle, "remove", None)
            if not callable(remove):
                unresolved_in_cleanup_order.append(handle)
                failures.append(
                    f"{type(handle).__name__}: handle does not expose remove()"
                )
                continue
            try:
                remove()
            except Exception as exc:  # noqa: BLE001
                unresolved_in_cleanup_order.append(handle)
                failures.append(f"{type(exc).__name__}: {exc}")
        self._handles = list(reversed(unresolved_in_cleanup_order))
        if failures:
            self._state = _ManagerState.CLEANUP_FAILED
            raise ActivationHookError(
                HookErrorCode.CLEANUP_FAILED,
                "one or more hook handles could not be removed: "
                + "; ".join(failures),
            )
        self._state = _ManagerState.CLOSED


__all__ = [
    "CONCEPTUAL_HOOK_SITE",
    "EXPECTED_DECODER_LAYER_COUNT",
    "HOOK_DISCOVERY_VERSION",
    "ActivationHookError",
    "FrozenHookDiscovery",
    "HookCapture",
    "HookErrorCode",
    "HookLayerMetadata",
    "NormalizedHookOutput",
    "ScopedHookManager",
    "discover_decoder_hook_site",
    "normalize_hook_output",
]
