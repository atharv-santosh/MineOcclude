#!/usr/bin/env python3
"""v0.4 entrypoint for evaluation, monitoring, and locked durable execution.

Binds the shared controller to the v0.4 package and hands over. The controller
itself names no version: it resolves the authorization identity, run namespace
and stage role out of whichever authority it is bound to, through the frozen
``stage_binding_policy`` table. Setting ``VERSION_TAG`` here is therefore the
whole of the difference between running the v0.4 a1y_* / 85xxx campaign and
either closed predecessor inventory -- v0.3's a1x_* / 83xxx or v0.2's a1q_* /
81xxx -- which is exactly why this file's bytes are in the runtime-critical
closure.

``run-stage1`` through this entrypoint will refuse a v0.2 or v0.3 authorization,
a v0.2 or v0.3 provenance receipt, or a v0.2 or v0.3 manifest, because the
authorization artifact_id, the provenance artifact_id, both package digests, the
run namespace and the run inventory digest are all resolved from the v0.4
package and compared.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from scripts.regime_a_prime_qualification_v0_2 import development_controller  # noqa: E402

VERSION_TAG = "v0.4"


def main() -> int:
    development_controller.VERSION_TAG = VERSION_TAG
    return development_controller.main()


if __name__ == "__main__":
    sys.exit(main())
