#!/usr/bin/env python3
"""v0.4 entrypoint for the pre-outcome provenance and Stage-1 authorization receipts.

The receipt logic is not duplicated here. It lives in the v0.2 module, which the
frozen v0.4 Stage-1 manifest already treats as the shared implementation -- its
locked unit command names ``scripts/regime_a_prime_qualification_v0_2/
stage_unit_driver.py`` and parameterises it with the v0.4 manifest path. This
file follows that same architecture for the receipt generators: it binds the
implementation to the v0.4 package and hands over.

What this file owns is the *identity* of the experiment. ``bind_package``
refuses unless the v0.4 package's own bytes -- authority, Stage-1 manifest,
Stage-2 locked manifest and the authority's stage binding table -- all agree
that they are v0.4, so every artifact written through this entrypoint carries
``regime-a-prime-prospective-pre-outcome-provenance-v0.4``,
``regime-a-prime-stage1-authorization-v0.4``, the v0-4 run namespace, and the
a1y_* / 85xxx inventory. There is no argument that can make it emit a v0.2
identity, and no default that falls back to one.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from scripts.regime_a_prime_qualification_v0_2 import generate_receipts  # noqa: E402

VERSION_TAG = "v0.4"
ENTRYPOINT = "scripts/regime_a_prime_qualification_v0_4/generate_receipts.py"


def main(argv: list[str] | None = None) -> int:
    generate_receipts.bind_package(VERSION_TAG, entrypoint=ENTRYPOINT)
    return generate_receipts.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
