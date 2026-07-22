"""Vendored subset of Person B/A's intervention package.

Only ``directions`` is vendored here from
``origin/role/person-b-methods`` -- see
``docs/decisions/person_d_phase1_decision_log.md``. This package
intentionally does not re-export ``doses``/``producer`` (not vendored,
not needed by Person D's U4 control-matrix audit code, which reuses
``directions``' vector math only) the way B's real
``intervention/__init__.py`` does; reconcile against B's actual
package at integration time rather than treating this as authoritative.
"""
