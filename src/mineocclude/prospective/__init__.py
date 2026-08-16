"""Future-facing prospective-experiment infrastructure.

Everything in this package was written AFTER the Regime A-prime P3 terminal
freeze (commit 351da852965bb20f89fe848bdef71703c34f0705) in response to
confirmed defects recorded in
``docs/status/integration/regime_a_prime_qualification_v0_1/p2_temporal_alignment_forensic_v0_1/11_defect_register.md``.

It is deliberately isolated from every historical analysis path.  Importing it
cannot change any frozen P1/P2/P3 result: no module here is referenced by
``p1_*``, ``p2_*`` or ``p3_*`` scripts.

Design rules that apply to the whole package:

* Clock domains are named, never implied.  A bare "frame index" is never
  accepted where a domain-qualified index is meant.
* Scientific thresholds are inputs, never constants.  These modules compute and
  report; a prospectively frozen authority decides.
* Ambiguity fails closed.  A quantity that cannot be established is raised, not
  defaulted.
"""

from mineocclude.prospective.clock_domains import (  # noqa: F401
    ClockDomain,
    DomainIndex,
    TimebaseSpec,
    UnresolvedAlignment,
)

__all__ = ["ClockDomain", "DomainIndex", "TimebaseSpec", "UnresolvedAlignment"]
