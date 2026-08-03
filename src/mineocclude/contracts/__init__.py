"""Cross-role contract validators.

Exports are resolved lazily (PEP 562). ``analysis_inputs`` imports Person B's
analysis chain, which itself imports ``mineocclude.data.capture_contract``;
an eager import here made the package-import order significant (importing
``mineocclude.data`` before ``mineocclude.contracts`` raised a circular
ImportError). Lazy resolution keeps every import order working without
changing any exported name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .analysis_inputs import (
        AnalysisInputRejectionCode,
        AnalysisInputValidationResult,
        validate_baseline_input,
        validate_measurement_input,
        validate_state_input,
    )

__all__ = [
    "AnalysisInputRejectionCode",
    "AnalysisInputValidationResult",
    "validate_baseline_input",
    "validate_measurement_input",
    "validate_state_input",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import analysis_inputs

    return getattr(analysis_inputs, name)
