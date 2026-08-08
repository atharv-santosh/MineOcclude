"""Public cross-role contract helpers without import-time dependency cycles.

The analysis-input validators depend on the Person C capture contract through
the coordinate adapter. Importing them eagerly here made a direct import of
``mineocclude.data.capture_contract`` recurse back into itself. Keep the
package-level convenience API, but resolve it lazily (PEP 562) when a caller
requests one of these names. This preserves the existing main-branch API and
the Person B analysis validators without making import order significant.
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
    """Resolve the package-level analysis-input convenience exports lazily."""

    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import analysis_inputs

    return getattr(analysis_inputs, name)
