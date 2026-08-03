"""Cross-role contract validators.

Exports are resolved lazily (PEP 562). ``analysis_inputs`` imports Person B's
analysis chain, which itself imports ``mineocclude.data.capture_contract``;
an eager import here made the package-import order significant (importing
``mineocclude.data`` before ``mineocclude.contracts`` raised a circular
ImportError). Lazy resolution keeps every import order working without
changing any exported name.
"""

__all__ = [
    "AnalysisInputRejectionCode",
    "AnalysisInputValidationResult",
    "validate_baseline_input",
    "validate_measurement_input",
    "validate_state_input",
]


def __getattr__(name):
    if name in __all__:
        from mineocclude.contracts import analysis_inputs

        return getattr(analysis_inputs, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
