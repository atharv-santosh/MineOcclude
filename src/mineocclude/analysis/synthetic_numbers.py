"""Version-stable numeric representation for non-scientific synthetic evidence.

The supported repository environments currently span NumPy 1.26 through 2.4.
Their linear-algebra results can differ in the final binary64 bits.  Synthetic
reports retain fourteen significant decimal digits, which is well below those
last-bit differences and far more precise than any synthetic contract gate.
Real scientific artifacts must never use this canonicalizer.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from mineocclude.analysis.manifests import sha256_value


SYNTHETIC_SIGNIFICANT_DIGITS = 14


def canonical_synthetic_float(value: float) -> float:
    """Return the stable fourteen-significant-digit synthetic representation."""

    if not math.isfinite(value):
        raise ValueError("Synthetic evidence cannot contain non-finite floats.")
    return float(format(value, f".{SYNTHETIC_SIGNIFICANT_DIGITS}g"))


def canonicalize_synthetic_value(value: Any) -> Any:
    """Recursively canonicalize Python floats without changing container shape."""

    if type(value) is float:
        return canonical_synthetic_float(value)
    if isinstance(value, Mapping):
        return {
            key: canonicalize_synthetic_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [canonicalize_synthetic_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(canonicalize_synthetic_value(item) for item in value)
    return value


def canonicalize_synthetic_artifact_payload(
    artifact: Mapping[str, Any],
    *,
    prediction_manifest_hashes: list[str] | None = None,
) -> dict[str, Any]:
    """Canonicalize an unsealed synthetic artifact and its derived hashes."""

    payload = canonicalize_synthetic_value(
        {key: value for key, value in artifact.items() if key != "artifact_hash"}
    )
    if prediction_manifest_hashes is not None:
        payload["prediction_manifest_hashes"] = list(prediction_manifest_hashes)
    fold_records = payload.get("fold_fit_records")
    if isinstance(fold_records, list) and "fold_fit_records_hash" in payload:
        payload["fold_fit_records_hash"] = sha256_value(fold_records)
    return payload
