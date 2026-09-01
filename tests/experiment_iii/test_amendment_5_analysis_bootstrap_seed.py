"""Authority Amendment 5 (v1.8) -- the III-A analysis bootstrap seed.

The defect these tests pin down is not hypothetical. The superseded P2 package
`a2734b31...` reported ``P2_RESULT = PASS`` while binding

    bindings.EXTRACTION_ANALYSIS_AND_OPERATIONS.bootstrap_seed = "FROZEN_IN_P2"

because ``PLACEHOLDER_TOKENS`` never listed the authority's own deferral token,
and the producer copied ``statistics.bootstrap_seed`` straight out of the machine
authority instead of deriving it. Both halves are covered here.
"""

from __future__ import annotations

import hashlib

import pytest

from mineocclude.experiment_iii.authority import phase0_design_sha256
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.p0_bindings import (
    BOOTSTRAP_SEED_DOMAIN as P0_BOOTSTRAP_SEED_DOMAIN,
    p0_bootstrap_seed,
)
from mineocclude.experiment_iii.p2_freeze import (
    PLACEHOLDER_PREFIXES,
    PLACEHOLDER_TOKENS,
    _reject_placeholders,
)
from mineocclude.experiment_iii.statistics import (
    ANALYSIS_BOOTSTRAP_SEED_DOMAIN,
    BOOTSTRAP_REPLICATES,
    analysis_bootstrap_seed,
    assert_concrete_bootstrap_seed,
)

FROZEN_ANALYSIS_SEED = 8258108568742502015
FROZEN_MATERIAL_SHA256 = "f29ab1fd6c819e7ff584b6ca9344b6d112fe15a10dbc32ff47bed6536589a895"
FROZEN_P0_SEED = 1530570907966297797
FROZEN_P0_MATERIAL_SHA256 = (
    "153dae21a8e0d6c568eb1977e738ecf485f2b4dfc6670e8dc1709bcd8ce6625f"
)
PHASE0 = "be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c"


def _material(domain: str, phase0: str = PHASE0) -> str:
    return hashlib.sha256((domain + phase0).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# The construction
# --------------------------------------------------------------------------


def test_the_construction_reproduces_the_already_frozen_p0_seed():
    """If it cannot regenerate 7.10b's published seed it is the wrong formula.

    This is the gate Amendment 5 had to clear before it could be written at all:
    the analysis seed is only trustworthy because the identical construction,
    under the P0 domain, returns the value the authority already published.
    """
    assert _material(P0_BOOTSTRAP_SEED_DOMAIN) == FROZEN_P0_MATERIAL_SHA256
    assert p0_bootstrap_seed() == FROZEN_P0_SEED


def test_the_analysis_seed_is_derived_not_literal():
    assert phase0_design_sha256() == PHASE0
    assert ANALYSIS_BOOTSTRAP_SEED_DOMAIN == (
        "MINEOCCLUDE_EXPERIMENT_III_ANALYSIS_BOOTSTRAP_V1|"
    )
    assert _material(ANALYSIS_BOOTSTRAP_SEED_DOMAIN) == FROZEN_MATERIAL_SHA256
    assert analysis_bootstrap_seed() == FROZEN_ANALYSIS_SEED
    assert 0 <= FROZEN_ANALYSIS_SEED < (1 << 63)


def test_the_analysis_domain_never_collides_with_the_p0_domain():
    """Domain separation is load-bearing, not decorative.

    Both domains bind the same Phase 0 digest. If they collided, the primary
    identity bootstrap would silently reuse the P0 placement-bootstrap stream.
    """
    assert ANALYSIS_BOOTSTRAP_SEED_DOMAIN != P0_BOOTSTRAP_SEED_DOMAIN
    assert analysis_bootstrap_seed() != p0_bootstrap_seed()


def test_the_seed_tracks_the_phase0_binding_not_the_authority_hash():
    """A moved Phase 0 binding must change the seed; an amendment must not."""
    moved = analysis_bootstrap_seed(phase0_sha256="0" * 64)
    assert moved != FROZEN_ANALYSIS_SEED
    assert analysis_bootstrap_seed() == FROZEN_ANALYSIS_SEED


def test_bootstrap_replicates_are_unchanged_by_the_amendment():
    assert BOOTSTRAP_REPLICATES == 10_000


# --------------------------------------------------------------------------
# The fail-closed guard
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [None, "", "FROZEN_IN_P2", "frozen_in_p2", "TBD", "TO_BE_DETERMINED",
     "PLACEHOLDER", "  FROZEN_IN_P2  "],
)
def test_placeholder_and_null_seeds_are_refused(value):
    with pytest.raises(ExperimentIIIError) as caught:
        assert_concrete_bootstrap_seed(value)
    assert caught.value.blocker in {"P2_BINDING_INCOMPLETE", "P2_BINDING_MISMATCH"}


@pytest.mark.parametrize("value", [1.5, True, False, [8258108568742502015], 1 << 63, -1])
def test_non_integer_or_out_of_range_seeds_are_refused(value):
    """``True`` matters: bool is an int subclass and would freeze as seed 1."""
    with pytest.raises(ExperimentIIIError):
        assert_concrete_bootstrap_seed(value)


def test_a_concrete_seed_is_accepted_and_returned():
    assert assert_concrete_bootstrap_seed(FROZEN_ANALYSIS_SEED) == FROZEN_ANALYSIS_SEED


# --------------------------------------------------------------------------
# The package walker
# --------------------------------------------------------------------------


def test_the_authoritys_own_deferral_token_is_a_placeholder():
    """The exact omission that let the superseded P2 pass."""
    assert "FROZEN_IN_P2" in PLACEHOLDER_TOKENS


def test_the_walker_refuses_the_superseded_binding_shape():
    package = {
        "bindings": {
            "EXTRACTION_ANALYSIS_AND_OPERATIONS": {"bootstrap_seed": "FROZEN_IN_P2"}
        }
    }
    with pytest.raises(ExperimentIIIError) as caught:
        _reject_placeholders(package)
    assert caught.value.blocker == "P2_BINDING_INCOMPLETE"
    assert "bootstrap_seed" in caught.value.message


def test_the_walker_refuses_every_frozen_in_p2_suffix():
    """A deferral to P2 can never be a P2 binding, whatever suffix it carries."""
    assert PLACEHOLDER_PREFIXES == ("FROZEN_IN_P2",)
    with pytest.raises(ExperimentIIIError):
        _reject_placeholders({"b": "FROZEN_IN_P2_SAME_STREAM_DISCIPLINE_AS_III_A"})


def test_the_walker_admits_the_derived_seed():
    _reject_placeholders({"bindings": {"X": {"bootstrap_seed": FROZEN_ANALYSIS_SEED}}})
