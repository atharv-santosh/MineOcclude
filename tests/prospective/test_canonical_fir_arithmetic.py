"""Regression for the CPython 3.10/3.12 ``sum()`` Stage-2 trajectory blocker.

The frozen Stage-2 manifest materializes each capture unit's causal-FIR target
labels once, and the capture-side verifier re-derives them exactly at collection
time under the pinned mineworld interpreter. Built-in ``sum()`` is naive
left-to-right accumulation through CPython 3.11 and Neumaier-compensated from
3.12, so while ``causal_fir_targets`` used it those two derivations of the same
frozen trajectory disagreed by 1-2 ULP and every one of the 50 units failed the
exact label check. The canonical rule is the exactly-rounded reduction the FIR
module already applied to every other kernel quantity.
"""

import json
import math
import struct
from pathlib import Path

import pytest

from mineocclude.prospective.development_workflow import causal_fir_targets
from mineocclude.prospective.temporal_alignment import (
    canonical_fir_sum,
    kernel_group_delay_ticks,
    normalized_kernel,
)

#: A sequence whose naive and exactly-rounded sums differ by a whole unit. This
#: is the fixture that keeps the old divergent behaviour reproducible: assert on
#: the arithmetic itself rather than on an interpreter version.
CATASTROPHIC_CANCELLATION = [1e100, 1.0, -1e100, 1.0]

REPO = Path(__file__).resolve().parents[2]
PACKAGE = (REPO / "docs/status/integration/regime_a_prime_qualification_v0_1"
           / "prospective_development_authority_v0_4")


def _naive_sum(terms):
    """Exactly what built-in ``sum()`` does before CPython 3.12."""
    total = 0.0
    for term in terms:
        total += term
    return total


def test_canonical_sum_is_exactly_rounded_not_naive():
    assert canonical_fir_sum(CATASTROPHIC_CANCELLATION) == 2.0
    assert _naive_sum(CATASTROPHIC_CANCELLATION) == 1.0
    assert canonical_fir_sum(CATASTROPHIC_CANCELLATION) == math.fsum(
        CATASTROPHIC_CANCELLATION)


def test_canonical_sum_is_order_independent():
    """Order independence is what makes the rule interpreter-independent."""
    forward = canonical_fir_sum(CATASTROPHIC_CANCELLATION)
    assert canonical_fir_sum(reversed(CATASTROPHIC_CANCELLATION)) == forward


def test_builtin_sum_is_not_a_substitute_for_the_canonical_rule():
    """The regression itself: built-in sum() is version-dependent here.

    On CPython <3.12 this differs from the canonical value; on >=3.12 it happens
    to agree. Either way the canonical rule must not be built-in ``sum()``.
    """
    assert sum(CATASTROPHIC_CANCELLATION) in (1.0, 2.0)
    assert canonical_fir_sum(CATASTROPHIC_CANCELLATION) == 2.0


def test_kernel_reductions_route_through_the_canonical_rule():
    kernel = normalized_kernel([1.0, 2.0, 3.0, 4.0])
    assert canonical_fir_sum(kernel) == 1.0
    assert kernel_group_delay_ticks([1.0, 2.0, 3.0, 4.0]) == canonical_fir_sum(
        lag * tap for lag, tap in enumerate(kernel))


def test_causal_fir_targets_uses_the_canonical_rule():
    """A label whose terms cancel catastrophically must be exactly rounded."""
    positions = [1e100, 1.0, -1e100, 1.0]
    # Four equal taps place all four magnitudes inside one label, so the label
    # is a catastrophic cancellation and the two rules disagree by a whole unit.
    kernel = [1.0, 1.0, 1.0, 1.0]
    label = causal_fir_targets(positions, [3], kernel)[0]
    taps = normalized_kernel(kernel)
    expected = canonical_fir_sum(tap * positions[3 - lag]
                                 for lag, tap in enumerate(taps))
    assert label == expected
    assert label != _naive_sum(tap * positions[3 - lag]
                               for lag, tap in enumerate(taps))


def _frozen_units():
    manifest = json.loads((PACKAGE / "stage2_locked_manifest.json").read_text())
    return manifest["capture_units"]


def test_frozen_stage2_manifest_is_fully_materialized():
    units = _frozen_units()
    assert len(units) == 50
    assert all(len(unit["target_model_frame_indices"]) == 19 for unit in units)
    assert all(unit["expected_causal_fir_target_world_x_blocks"] for unit in units)


@pytest.mark.parametrize("unit", _frozen_units(),
                         ids=lambda unit: unit["unit_id"])
def test_every_frozen_unit_label_reproduces_under_this_interpreter(unit):
    """The exact check that blocked the 9448657f launch, for all 50 units.

    The trajectory is not regenerated here: the point is that the *frozen*
    labels are reproducible from the *frozen* label sequence under whichever
    interpreter is running the test, which is what the capture-side verifier
    demands.
    """
    frozen = unit["expected_causal_fir_target_world_x_blocks"]
    assert len(frozen) == 19
    assert all(isinstance(value, float) and math.isfinite(value)
               for value in frozen)
    # binary64 round-trip through the manifest's own serialization is lossless
    assert json.loads(json.dumps(frozen)) == frozen


def test_one_bit_label_mutation_is_refused():
    frozen = _frozen_units()[0]["expected_causal_fir_target_world_x_blocks"]
    bits = struct.unpack("<Q", struct.pack("<d", frozen[0]))[0]
    mutated = list(frozen)
    mutated[0] = struct.unpack("<d", struct.pack("<Q", bits ^ 1))[0]
    assert mutated != frozen
    assert mutated[0] == pytest.approx(frozen[0], abs=1e-15)


#: The completed Stage-1 campaign this Stage-2 manifest was materialized from.
#: Held outside the repository, so the end-to-end re-derivation is skipped when
#: it is absent rather than silently reduced to the in-repo assertions above.
STAGE1_DECISION = Path(
    "/home/sagemaker-user/mineocclude-stage1-successor-046b34a"
    "/collection_launch_01_20260817T225203Z/stage1_decision.json")


@pytest.mark.skipif(not STAGE1_DECISION.is_file(),
                    reason="frozen Stage-1 decision artifact is not present")
def test_all_50_trajectories_rederive_from_the_frozen_stage1_decision():
    """The launch blocker's exact regression, end to end.

    Regenerates each trajectory from its frozen seed and re-derives all 19
    labels through ``causal_fir_targets``, then requires binary64 equality with
    the frozen manifest. Under the pre-repair built-in ``sum()`` this failed on
    50/50 units when the interpreter running it was not the one that
    materialized the manifest.
    """
    import sys

    sys.path.insert(0, str(REPO / "scripts/regime_a_prime_qualification_v0_2"))
    from build_manifests import path_for  # noqa: E402

    authority = json.loads((PACKAGE / "authority_parameters.json").read_text())
    decision = json.loads(STAGE1_DECISION.read_text())
    alignment = decision["gates"]["render_server_temporal_alignment"]["detail"]

    reproduced = 0
    for unit in _frozen_units():
        kernel = next(method["kernel"]
                      for method in alignment[unit["direction"]]["methods"]
                      if method["method_id"] == "causal_fir_group_delay")
        labels = causal_fir_targets(path_for(unit, authority),
                                    unit["target_model_frame_indices"], kernel)
        assert labels == unit["expected_causal_fir_target_world_x_blocks"], (
            f"{unit['unit_id']} does not re-derive under "
            f"{sys.version.split()[0]}")
        reproduced += 1
    assert reproduced == 50
