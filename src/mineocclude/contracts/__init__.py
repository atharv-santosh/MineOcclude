"""Public contract helpers without import-time dependency cycles.

The analysis-input validators depend on the Person C capture contract through
the coordinate adapter. Importing them eagerly here made a direct import of
``mineocclude.data.capture_contract`` recurse back into itself. Keep the
package-level convenience API, but resolve it only when a caller requests one
of these names.
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
