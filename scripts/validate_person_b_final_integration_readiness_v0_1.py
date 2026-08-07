#!/usr/bin/env python3
"""CLI entry point for final Person B integration-readiness validation."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mineocclude.analysis.final_integration_readiness_v0_1 import (
    CertificationValidationError,
    FinalIntegrationReadinessValidationError,
    canonical_json_bytes,
    load_strict_json,
    main,
    validate,
    validate_package,
)

__all__ = [
    "CertificationValidationError",
    "FinalIntegrationReadinessValidationError",
    "canonical_json_bytes",
    "load_strict_json",
    "main",
    "validate",
    "validate_package",
]


if __name__ == "__main__":
    raise SystemExit(main())
