#!/usr/bin/env python3
"""v0.3 construction-time consistency audit; performs no capture.

Binds the shared audit to the v0.3 package. Every assertion the v0.2 audit makes
holds for v0.3 unchanged -- the two packages are structurally identical and
differ only in identity strings and authority status -- so the checks are shared
rather than transcribed, and the audit refuses before its first assertion if the
directory it was pointed at does not identify itself as v0.3.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from scripts.regime_a_prime_qualification_v0_2 import verify_package  # noqa: E402

VERSION_TAG = "v0.3"


def main() -> None:
    verify_package.VERSION_TAG = VERSION_TAG
    verify_package.main()


if __name__ == "__main__":
    main()
