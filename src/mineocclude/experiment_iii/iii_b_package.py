"""III-B closure: the belief-state ladder and the III-A invariant (authority 17.2, 28).

Two things live here because they are the module's terminal obligations.

**The belief-state ladder.** Seven rungs, adjudicated prospectively at ``B-LOCK``.
Exactly one rung is selected for any result pattern, and a claim outside the
selected rung is refused. Only rung 4 licenses "a calibrated Gaussian belief
state under this apparatus"; no rung ever licenses U4, causal use, steering or
causal object permanence.

**The III-A invariant.** No III-A lifecycle state may list a ``B-*`` state in its
entry conditions, no III-A artifact may have a III-B artifact as a prerequisite,
no III-A estimand or fold may reference a III-B cell, and ``A19`` closure may
make no reference to III-B. :func:`assert_iii_a_independence` checks this
mechanically against the frozen lifecycle rather than by inspection, because the
dependency it hunts is exactly the kind that is invisible in prose.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    AUTHORITY_ROOT,
    machine_authority,
    sha256_file,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "LADDER_RUNGS",
    "PHASE0_AMENDMENT_JSON_PATH",
    "PHASE0_AMENDMENT_MD_PATH",
    "amendment_hash_binding",
    "assert_claim_within_rung",
    "assert_iii_a_independence",
    "iii_b_closure_receipt",
    "select_ladder_rung",
    "simulate_total_iii_b_failure",
]

PHASE0_AMENDMENT_MD_PATH = AUTHORITY_ROOT / "PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.md"
PHASE0_AMENDMENT_JSON_PATH = (
    AUTHORITY_ROOT / "PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.json"
)
LIFECYCLE_PATH = AUTHORITY_ROOT / "EXPERIMENT_III_LIFECYCLE.json"

LADDER_RUNGS = {
    1: {
        "pattern": "MU_DECODABLE_SIGMA_NOT",
        "claim": (
            "position is linearly accessible under occlusion; no evidence of "
            "uncertainty representation in this readout"
        ),
        "prohibited": ("belief state", "uncertainty representation", "calibrated"),
    },
    2: {
        "pattern": "MU_NOT_DECODABLE_SIGMA_DECODABLE",
        "claim": (
            "uncertainty-relevant information is present even where the point "
            "estimate is not linearly recoverable - a partial belief-state signature"
        ),
        "prohibited": ("the model tracks the object", "calibrated"),
    },
    3: {
        "pattern": "BOTH_DECODABLE_SIGMA_UNCALIBRATED",
        "claim": (
            "uncertainty-relevant information tracking oracle posterior spread, "
            "ordinally but not on a calibrated scale"
        ),
        "prohibited": ("calibrated", "bayesian belief state"),
    },
    4: {
        "pattern": "MU_PLUS_SIGMA_DECODABLE_AND_SCALE_CALIBRATED",
        "claim": "a calibrated Gaussian belief state under this apparatus",
        "prohibited": ("u4", "causal use", "generalization beyond this apparatus"),
        "is_strongest": True,
    },
    5: {
        "pattern": "BOTH_FAIL",
        "claim": (
            "no linearly accessible belief-state signature in the selected readout "
            "at this power"
        ),
        "prohibited": ("mineworld has no uncertainty representation",),
    },
    6: {
        "pattern": "TAU_EXPLAINS_SIGMA_HAT",
        "claim": "elapsed-time decoding; the sigma result is not uncertainty-specific",
        "prohibited": ("uncertainty",),
    },
    7: {
        "pattern": "Q_CATEGORY_DETECTABLE_DYNAMICS_ABSENT",
        "claim": (
            "the regime label is detectable, but correct uncertainty dynamics are "
            "not demonstrated"
        ),
        "prohibited": ("the model represents uncertainty",),
    },
}

_NEVER_LICENSED = (
    "u4",
    "causal use",
    "steering",
    "causal object permanence",
    "object permanence",
)


def select_ladder_rung(
    *,
    mu_decodable: bool,
    sigma_decodable: bool,
    scale_calibrated: bool,
    mean_gate_passes: bool,
    tau_only_baseline_matches_probe: bool = False,
    q_only_baseline_matches_probe: bool = False,
    delta_ci_contains_zero: bool = False,
) -> int:
    """Exactly one rung, for any result pattern. Rungs 6 and 7 take precedence.

    Rungs 6 and 7 are the diagnostic patterns of authority 28: when a confound
    baseline matches the probe *and* the ``U3-S2`` interval contains zero, the
    result is elapsed-time decoding or regime-label detection, whatever else the
    decodability flags say.
    """
    if tau_only_baseline_matches_probe and delta_ci_contains_zero:
        return 6
    if q_only_baseline_matches_probe and delta_ci_contains_zero:
        return 7
    if mu_decodable and sigma_decodable:
        if scale_calibrated and mean_gate_passes:
            return 4
        return 3
    if mu_decodable and not sigma_decodable:
        return 1
    if sigma_decodable and not mu_decodable:
        return 2
    return 5


def assert_claim_within_rung(claim: str, rung: int) -> None:
    """Refuse a claim outside the selected rung, and every never-licensed claim."""
    if rung not in LADDER_RUNGS:
        raise ExperimentIIIError(
            "B_U2_ANALYSIS_FAIL", f"{rung!r} is not one of the seven frozen rungs"
        )
    lowered = claim.lower()
    # Authority 23 and 28: only rung 4 ever licenses "calibrated belief state",
    # whatever an individual rung's own prohibition list happens to enumerate.
    if rung != 4 and "belief state" in lowered and "calibrat" in lowered:
        raise ExperimentIIIError(
            "B_U2_ANALYSIS_FAIL",
            f"only rung 4 licenses a calibrated belief state; rung {rung} is "
            f"{LADDER_RUNGS[rung]['pattern']}",
        )
    for phrase in _NEVER_LICENSED:
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            raise ExperimentIIIError(
                "B_U2_ANALYSIS_FAIL",
                f"no rung licenses {phrase!r}: a positive U2/U3 result says "
                "information is linearly present, never that the model uses it",
            )
    for phrase in LADDER_RUNGS[rung]["prohibited"]:
        if phrase in lowered:
            raise ExperimentIIIError(
                "B_U2_ANALYSIS_FAIL",
                f"rung {rung} prohibits {phrase!r}: {LADDER_RUNGS[rung]['claim']}",
            )


# --------------------------------------------------------------------------
# The III-A invariant
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _lifecycle() -> dict[str, Any]:
    if not LIFECYCLE_PATH.is_file():
        raise ExperimentIIIError(
            "AUTHORITY_INCOMPLETE", f"lifecycle is absent: {LIFECYCLE_PATH}"
        )
    return json.loads(LIFECYCLE_PATH.read_text(encoding="utf-8"))


def _states() -> list[Mapping[str, Any]]:
    lifecycle = _lifecycle()
    for key in ("states", "lifecycle_states", "stages"):
        value = lifecycle.get(key)
        if isinstance(value, list):
            return [state for state in value if isinstance(state, dict)]
        if isinstance(value, dict):
            return [
                {"id": name, **body}
                for name, body in value.items()
                if isinstance(body, dict)
            ]
    raise ExperimentIIIError(
        "AUTHORITY_INCOMPLETE", "the lifecycle carries no recognizable state list"
    )


def _state_id(state: Mapping[str, Any]) -> str:
    for key in ("id", "state", "name", "stage"):
        if key in state:
            return str(state[key])
    return ""


def assert_iii_a_independence() -> dict[str, Any]:
    """Mechanically prove no III-A state depends on any ``B-*`` state."""
    offending: list[str] = []
    checked = 0
    for state in _states():
        identifier = _state_id(state)
        if identifier.startswith("B-"):
            continue
        checked += 1
        blob = json.dumps(
            {
                key: value
                for key, value in state.items()
                if key
                in {
                    "entry",
                    "entry_conditions",
                    "inputs",
                    "prerequisites",
                    "requires",
                    "depends_on",
                    "exit",
                    "closure_conditions",
                }
            }
        )
        for match in re.findall(r'"(B-[A-Z0-9]+)"', blob):
            offending.append(f"{identifier} -> {match}")
    if offending:
        raise ExperimentIIIError(
            "B_III_A_DEPENDENCY_DETECTED",
            f"III-A states depend on III-B runtime stages: {sorted(set(offending))}",
        )
    return {
        "iii_a_states_checked": checked,
        "iii_a_states_referencing_a_b_state": 0,
        "invariant": (
            "NO III-B STAGE IS A PRECONDITION OF ANY III-A SCIENTIFIC COMPLETION STAGE"
        ),
    }


def simulate_total_iii_b_failure(
    iii_a_closure_conditions: Iterable[str],
) -> dict[str, Any]:
    """III-A closure must be byte-identical under a total III-B failure."""
    conditions = list(iii_a_closure_conditions)
    contaminated = sorted(
        condition
        for condition in conditions
        if "III_B" in str(condition).upper() or str(condition).startswith("B-")
    )
    if contaminated:
        raise ExperimentIIIError(
            "B_III_A_DEPENDENCY_DETECTED",
            f"III-A closure references III-B: {contaminated}",
        )
    return {
        "iii_b_outcome": "TOTAL_FAILURE",
        "iii_a_closure_conditions": conditions,
        "iii_a_closure_unaffected": True,
        "iii_a_closure_delayed_for_iii_b": False,
    }


# --------------------------------------------------------------------------
# IB01 -- amendment hash binding
# --------------------------------------------------------------------------

def amendment_hash_binding() -> dict[str, Any]:
    """``D.1``: the machine authority records both amendment hashes, and they hold."""
    machine = machine_authority()
    amendment = machine["amendments"][0]
    recorded_md = amendment["phase0_amendment_md_sha256"]
    recorded_json = amendment["phase0_amendment_json_sha256"]
    for path in (PHASE0_AMENDMENT_MD_PATH, PHASE0_AMENDMENT_JSON_PATH):
        if not path.is_file():
            raise ExperimentIIIError(
                "AUTHORITY_INCOMPLETE", f"Phase 0 Amendment 1 is absent: {path}"
            )
    observed_md = sha256_file(PHASE0_AMENDMENT_MD_PATH)
    observed_json = sha256_file(PHASE0_AMENDMENT_JSON_PATH)
    drift = {
        name: {"recorded": recorded, "observed": observed}
        for name, recorded, observed in (
            ("phase0_amendment_md_sha256", recorded_md, observed_md),
            ("phase0_amendment_json_sha256", recorded_json, observed_json),
        )
        if recorded != observed
    }
    if drift:
        raise ExperimentIIIError(
            "PROVENANCE_AUTHORITY_DRIFT",
            f"Phase 0 Amendment 1 has drifted from the machine authority: {drift}",
        )
    if machine["experiment_iii_b"]["phase0_amendment_sha256"] != recorded_md:
        raise ExperimentIIIError(
            "PROVENANCE_AUTHORITY_DRIFT",
            "experiment_iii_b.phase0_amendment_sha256 disagrees with amendments[0]",
        )
    return {
        "schema_version": "mineocclude-experiment-iii-b-amendment-binding-v1",
        "phase0_amendment_md_sha256": observed_md,
        "phase0_amendment_json_sha256": observed_json,
        "both_files_exist": True,
        "recomputed_hashes_match_the_machine_authority": True,
    }


def iii_b_closure_receipt(
    *,
    outcome: str,
    rung: int | None,
    claim: str | None,
    iii_a_closure_conditions: Sequence[str],
) -> dict[str, Any]:
    """``iii_b_closure_receipt.json`` -- the module's terminal evidence."""
    from mineocclude.experiment_iii.iii_b_status import OUTCOME_VOCABULARY

    if outcome not in OUTCOME_VOCABULARY and outcome != "RESULT_LOCKED":
        raise ExperimentIIIError(
            "B_U2_ANALYSIS_FAIL",
            f"{outcome!r} is not a III-B outcome; the vocabulary is "
            f"{sorted(OUTCOME_VOCABULARY)} plus RESULT_LOCKED",
        )
    if rung is not None and claim is not None:
        assert_claim_within_rung(claim, rung)
    return {
        "schema_version": "mineocclude-experiment-iii-b-closure-v1",
        "outcome": outcome,
        "outcome_definition": OUTCOME_VOCABULARY.get(outcome),
        "belief_state_rung": rung,
        "claim": claim,
        "only_rung_4_licenses_calibrated_belief_state": True,
        "iii_a_independence": simulate_total_iii_b_failure(iii_a_closure_conditions),
        "amendment_binding": amendment_hash_binding(),
    }
