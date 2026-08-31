"""The Bayesian oracle (authority 20; ``III_B_ORACLE_SPECIFICATION.json``).

Every quantity here is derived from frozen apparatus constants and the frozen
direction FIR kernels. Nothing in this module reads an activation, a prediction,
a fitted parameter or any other scientific outcome -- that prohibition is the
whole point of an *analytic* oracle, and it is enforced by
:func:`assert_no_fitted_input`.

Two things are load-bearing and easy to get wrong:

* **Normalization.** ``H(m)`` is the cumulative mass of the **fsum-normalized**
  kernel. The published ``LEFT_TO_RIGHT`` taps sum to ``0.9999999999``; using
  them unnormalized reproduces ``S(tau)`` only to ``9.29e-10`` and fails the
  ``1e-12`` tolerance of test ``D.6``. The single normalized kernel of record is
  :func:`mineocclude.experiment_iii.fir.frozen_kernel`, and this module reads it
  through there and nowhere else.
* **The affine form is wrong below tau = 8.** ``sigma2 = q*dt*(tau + c)`` is
  exact only for ``tau >= 8``; below it the expression is strictly negative up to
  a *direction-specific* boundary. The implementation never evaluates it below
  ``tau = 8`` unless a caller explicitly asks for the diagnostic form, which
  exists only so ``D.7`` can prove the boundary.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    AUTHORITY_ROOT,
    BINDING_Q_SET,
    DIAGNOSTIC_Q_FALLBACK,
    DT_SECONDS,
    SPEED_BLOCKS_PER_SECOND,
    direction_sign,
    machine_authority,
    sha256_file,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.fir import frozen_kernel
from mineocclude.experiment_iii.schema import validate_identity_id

__all__ = [
    "ORACLE_SPECIFICATION_PATH",
    "TAU_MAX",
    "TAU_PRIMARY_SUPPORT",
    "affine_first_positive_tau",
    "affine_last_negative_tau",
    "affine_sigma2",
    "assert_no_fitted_input",
    "c_direction",
    "cumulative_mass",
    "gbar",
    "mu_tau",
    "oracle_specification",
    "oracle_validation_receipt",
    "s_tau",
    "sigma",
    "sigma2",
    "sigma_ledger",
]

ORACLE_SPECIFICATION_PATH = AUTHORITY_ROOT / "III_B_ORACLE_SPECIFICATION.json"

#: Occlusion age runs 1..19; ``tau = 0`` is the last not-fully-occluded row.
TAU_MAX = 19
#: The primary U2/U3 support (authority 21.4); 16..19 is the boundary secondary.
TAU_PRIMARY_SUPPORT = tuple(range(1, 16))

_AFFINE_EXACT_FROM_TAU = 8


@lru_cache(maxsize=1)
def oracle_specification() -> dict[str, Any]:
    """The frozen oracle specification, read from the authority package."""
    if not ORACLE_SPECIFICATION_PATH.is_file():
        raise ExperimentIIIError(
            "AUTHORITY_INCOMPLETE",
            f"oracle specification is absent: {ORACLE_SPECIFICATION_PATH}",
        )
    return json.loads(ORACLE_SPECIFICATION_PATH.read_text(encoding="utf-8"))


def _per_direction(direction: str) -> dict[str, Any]:
    spec = oracle_specification()["per_direction"]
    if direction not in spec:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", f"unknown direction {direction!r}"
        )
    return spec[direction]


def assert_no_fitted_input(**candidates: object) -> None:
    """Refuse any activation, prediction or fitted parameter reaching the oracle."""
    offered = sorted(name for name, value in candidates.items() if value is not None)
    if offered:
        raise ExperimentIIIError(
            "B_ORACLE_MISMATCH",
            "the oracle is analytic: it reads frozen apparatus constants and "
            f"kernels only, never {offered}",
        )


@lru_cache(maxsize=None)
def cumulative_mass(direction: str) -> tuple[float, ...]:
    """``H(m) = fsum(h_0..h_min(m,8))`` on the fsum-normalized kernel, m = 0..8.

    ``H(m) = 1`` for every ``m >= 8``; :func:`s_tau` relies on that tail.
    """
    taps = frozen_kernel(direction)
    return tuple(math.fsum(taps[: index + 1]) for index in range(len(taps)))


def _h(direction: str, m: int) -> float:
    masses = cumulative_mass(direction)
    if m >= len(masses) - 1:
        return 1.0
    return masses[m]


def _validate_tau(tau: int, *, allow_zero: bool = False, maximum: int = TAU_MAX) -> int:
    if isinstance(tau, bool) or not isinstance(tau, int):
        raise ExperimentIIIError("B_ORACLE_MISMATCH", f"tau must be an int, got {tau!r}")
    low = 0 if allow_zero else 1
    if not low <= tau <= maximum:
        raise ExperimentIIIError(
            "B_ORACLE_MISMATCH", f"tau must lie in [{low}, {maximum}], got {tau}"
        )
    return tau


def _validate_q(q: float) -> float:
    value = float(q)
    if not math.isfinite(value) or value <= 0.0:
        raise ExperimentIIIError("B_ORACLE_MISMATCH", f"q must be positive, got {q!r}")
    return value


@lru_cache(maxsize=None)
def s_tau(direction: str, tau: int) -> float:
    """``S(tau) = sum_{m=0}^{tau-1} H(m)^2``, accumulated with ``fsum``."""
    tau = _validate_tau(tau, allow_zero=True)
    return math.fsum(_h(direction, m) ** 2 for m in range(tau))


def sigma2(direction: str, q: float, tau: int) -> float:
    """The EXACT posterior variance ``q*dt*S(tau)``. Valid at every tau."""
    q = _validate_q(q)
    tau = _validate_tau(tau, allow_zero=True)
    return q * DT_SECONDS * s_tau(direction, tau)


def sigma(direction: str, q: float, tau: int) -> float:
    """Posterior standard deviation in blocks."""
    return math.sqrt(sigma2(direction, q, tau))


@lru_cache(maxsize=None)
def gbar(direction: str) -> float:
    """The frozen FIR group delay used by the posterior mean offset."""
    return float(_per_direction(direction)["fir_group_delay_ticks_gbar"])


@lru_cache(maxsize=None)
def c_direction(direction: str) -> float:
    """The frozen asymptotic affine offset ``c`` for this direction."""
    return float(_per_direction(direction)["c_direction_asymptotic"])


def mu_tau(x_t0: float, direction: str, tau: int) -> float:
    """``mu_tau = x[t0] + s*v*dt*(tau - gbar_direction)``."""
    tau = _validate_tau(tau, allow_zero=True)
    start = float(x_t0)
    if not math.isfinite(start):
        raise ExperimentIIIError("B_ORACLE_MISMATCH", "x[t0] must be finite")
    return start + direction_sign(direction) * SPEED_BLOCKS_PER_SECOND * DT_SECONDS * (
        tau - gbar(direction)
    )


def affine_sigma2(
    direction: str, q: float, tau: int, *, allow_below_tau_8: bool = False
) -> float:
    """``q*dt*(tau + c_direction)`` -- EXACT only for ``tau >= 8``.

    Below ``tau = 8`` the expression is not the posterior variance and is
    strictly negative up to the direction-specific boundary. Evaluating it there
    is refused unless ``allow_below_tau_8`` is set, which exists solely so test
    ``D.7`` can demonstrate the boundary it forbids.
    """
    q = _validate_q(q)
    tau = _validate_tau(tau, allow_zero=True)
    if tau < _AFFINE_EXACT_FROM_TAU and not allow_below_tau_8:
        raise ExperimentIIIError(
            "B_ORACLE_MISMATCH",
            f"the affine reduction is exact only for tau >= {_AFFINE_EXACT_FROM_TAU}; "
            f"refusing to evaluate it at tau = {tau}. Use sigma2() instead.",
        )
    return q * DT_SECONDS * (tau + c_direction(direction))


def affine_last_negative_tau(direction: str) -> int:
    return int(oracle_specification()["affine_last_negative_tau"][direction])


def affine_first_positive_tau(direction: str) -> int:
    return int(oracle_specification()["affine_first_positive_tau"][direction])


def sigma_ledger(
    cells: Iterable[Mapping[str, Any]],
    *,
    tau_values: Sequence[int] = tuple(range(1, TAU_MAX + 1)),
) -> list[dict[str, Any]]:
    """The ``B-ORC`` sigma-target ledger: one row per ``(identity, q, tau)``.

    ``cells`` supplies ``identity``, ``direction`` and ``q``; nothing else is
    read, and no outcome field is accepted.
    """
    rows: list[dict[str, Any]] = []
    for cell in cells:
        identity = validate_identity_id(str(cell["identity"]))
        direction = str(cell["direction"])
        q = _validate_q(cell["q"])
        assert_no_fitted_input(
            activation=cell.get("activation"),
            prediction=cell.get("prediction"),
            sigma_hat=cell.get("sigma_hat"),
            fitted_parameter=cell.get("fitted_parameter"),
        )
        for tau in tau_values:
            rows.append(
                {
                    "identity": identity,
                    "direction": direction,
                    "q": q,
                    "tau": int(tau),
                    "sigma_oracle_blocks": sigma(direction, q, int(tau)),
                    "sigma2_oracle_blocks2": sigma2(direction, q, int(tau)),
                    "S_tau": s_tau(direction, int(tau)),
                }
            )
    return rows


def oracle_validation_receipt() -> dict[str, Any]:
    """``iii_b_oracle_validation_receipt.json`` -- reproduce every frozen table."""
    spec = oracle_specification()
    directions = tuple(spec["per_direction"])
    per_direction: dict[str, Any] = {}
    max_s_error = 0.0
    max_sigma_error = 0.0
    for direction in directions:
        frozen_s = spec["per_direction"][direction]["S_tau_exact_tau_0_to_19"]
        computed_s = [s_tau(direction, tau) for tau in range(len(frozen_s))]
        s_error = max(abs(a - b) for a, b in zip(frozen_s, computed_s))
        max_s_error = max(max_s_error, s_error)

        frozen_h = spec["per_direction"][direction]["cumulative_kernel_mass_H_0_to_8"]
        computed_h = list(cumulative_mass(direction))
        h_error = max(abs(a - b) for a, b in zip(frozen_h, computed_h))

        by_q: dict[str, Any] = {}
        for key, frozen_sigma in spec["sigma_tau_blocks_by_q"][direction].items():
            computed_sigma = [
                sigma(direction, float(key), tau) for tau in range(len(frozen_sigma))
            ]
            error = max(abs(a - b) for a, b in zip(frozen_sigma, computed_sigma))
            max_sigma_error = max(max_sigma_error, error)
            by_q[key] = {"max_abs_error": error}

        per_direction[direction] = {
            "max_abs_S_tau_error": s_error,
            "max_abs_H_error": h_error,
            "gbar": gbar(direction),
            "c_direction": c_direction(direction),
            "affine_last_negative_tau": affine_last_negative_tau(direction),
            "affine_first_positive_tau": affine_first_positive_tau(direction),
            "sigma_positive_for_all_tau_at_every_q": all(
                sigma(direction, q, tau) > 0.0
                for q in (*BINDING_Q_SET, DIAGNOSTIC_Q_FALLBACK)
                for tau in range(1, TAU_MAX + 1)
            ),
            "sigma_by_q_max_abs_error": by_q,
        }

    machine = machine_authority()["experiment_iii_b"]["oracle"]
    agrees = all(
        machine["affine_last_negative_tau"][direction]
        == spec["affine_last_negative_tau"][direction]
        and machine["affine_first_positive_tau"][direction]
        == spec["affine_first_positive_tau"][direction]
        for direction in directions
    )
    return {
        "schema_version": "mineocclude-experiment-iii-b-oracle-validation-v1",
        "oracle_specification_sha256": sha256_file(ORACLE_SPECIFICATION_PATH),
        "taps_normalized_at_load": True,
        "kernel_source": "mineocclude.experiment_iii.fir.frozen_kernel",
        "reads_activation_prediction_or_fitted_parameter": False,
        "affine_form_evaluated_below_tau_8": False,
        "machine_authority_reproduces_affine_boundary": agrees,
        "max_abs_S_tau_error": max_s_error,
        "max_abs_sigma_error": max_sigma_error,
        "tolerance": 1e-12,
        "per_direction": per_direction,
        "passed": max_s_error <= 1e-12 and max_sigma_error <= 1e-12 and agrees,
    }
