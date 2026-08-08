#!/usr/bin/env python3
"""CLI entry point for the Person B Week 1 closeout validator."""

from __future__ import annotations

from mineocclude.analysis.week1_closeout_v0_1 import (
    CloseoutValidationError,
    canonical_json_bytes,
    load_strict_json,
    main,
    validate,
    validate_package,
)

__all__ = [
    "CloseoutValidationError",
    "canonical_json_bytes",
    "load_strict_json",
    "main",
    "validate",
    "validate_package",
]


if __name__ == "__main__":
    raise SystemExit(main())
