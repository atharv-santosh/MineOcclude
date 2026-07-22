"""Vendored subset of Person B's probes package.

Only ``ridge`` and ``splits`` are vendored here from
``origin/role/person-b-methods`` -- see
``docs/decisions/person_d_phase1_decision_log.md``. This package
intentionally does not re-export ``bridge``/``join``/``mlp`` (not
vendored, not needed by Person D's baseline code) the way B's real
``probes/__init__.py`` does; reconcile against B's actual package at
integration time rather than treating this as authoritative.
"""
