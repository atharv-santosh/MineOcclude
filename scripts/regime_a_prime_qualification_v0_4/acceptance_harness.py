#!/usr/bin/env python3
"""Deterministic no-collection acceptance harness for the v0.4 package.

Binds the shared harness to v0.4, which selects the v0.4 document set, the v0.4
test suites, and the v0.4 package audit. Collects nothing and starts no runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from scripts.regime_a_prime_qualification_v0_2 import acceptance_harness  # noqa: E402

VERSION_TAG = "v0.4"


def main() -> int:
    acceptance_harness.VERSION_TAG = VERSION_TAG
    return acceptance_harness.main()


if __name__ == "__main__":
    raise SystemExit(main())
