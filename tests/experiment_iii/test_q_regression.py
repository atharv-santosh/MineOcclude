"""IB03 / D.2 — the q = 0.05 bit-identity regression, plus A.2 and A.3.

MANDATORY BEFORE ``I02``. Without it a q-generalization defect could silently
alter the III-A cohort at the exact moment qualification gate 12 is evaluated.

The reference is reconstructed from the bound git object and nothing else: the
``v0_3`` manifest at commit ``f2bc2c8``, verified by SHA-256 before any field is
read. It is a DIFFERENT file from the ``v0_4`` manifest that carries the FIR
recovery, and the reference hash is not present in ``v0_4``.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pytest

from mineocclude.experiment_iii import aprime_reference as aprime
from mineocclude.experiment_iii.authority import (
    D2_NEGATIVE_CONTROL_NOISE_FIRST_PREFIX,
    D2_NEGATIVE_CONTROL_Q_PERTURBATION,
    D2_REFERENCE_BLOB_SHA1,
    D2_REFERENCE_BYTES,
    D2_REFERENCE_DIRECTION,
    D2_REFERENCE_PATH_SHA256,
    D2_REFERENCE_SEED,
    D2_REFERENCE_SHA256,
    D2_REFERENCE_START_WORLD_X,
    D2_REFERENCE_UNIT_ID,
    FRAMES_PER_CAPTURE,
    MOTION_NOISE_Q,
    SPEED_BLOCKS_PER_SECOND,
)
from mineocclude.experiment_iii.cohort import (
    generate_noise_schedule,
    generate_path,
    generate_path_noise_first_forbidden,
    generate_path_vectorized_forbidden,
    noise_sha256,
    path_sha256,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

BINDING_Q = 0.05


@pytest.fixture(scope="module")
def reference_unit():
    return aprime.d2_reference_unit()


def _reference_path(q: float = BINDING_Q):
    positions, _noise = generate_path(
        D2_REFERENCE_SEED,
        q,
        direction=D2_REFERENCE_DIRECTION,
        start_world_x=D2_REFERENCE_START_WORLD_X,
        speed=SPEED_BLOCKS_PER_SECOND,
        frames=FRAMES_PER_CAPTURE,
    )
    return positions


# --------------------------------------------------------------------------
# The bound reference artifact
# --------------------------------------------------------------------------

def test_reference_manifest_is_the_bound_v0_3_object():
    payload = aprime.read_git_blob(
        "f2bc2c8082e77f9c3f9e089f2fb1a20b11a052a8",
        "docs/status/integration/regime_a_prime_qualification_v0_1/"
        "prospective_development_authority_v0_3/stage2_locked_manifest.json",
    )
    assert len(payload) == D2_REFERENCE_BYTES == 270672
    assert hashlib.sha256(payload).hexdigest() == D2_REFERENCE_SHA256
    blob_sha1 = hashlib.sha1(b"blob %d\0" % len(payload) + payload).hexdigest()
    assert blob_sha1 == D2_REFERENCE_BLOB_SHA1


def test_reference_unit_fields_match_the_authority(reference_unit):
    assert reference_unit.unit_id == D2_REFERENCE_UNIT_ID == "a2x_t01_wall"
    assert reference_unit.direction == D2_REFERENCE_DIRECTION == "LEFT_TO_RIGHT"
    assert reference_unit.seed == reference_unit.noise_seed == D2_REFERENCE_SEED
    assert reference_unit.start_world_x == D2_REFERENCE_START_WORLD_X == -7.8
    assert reference_unit.motion_noise_q == BINDING_Q
    assert reference_unit.speed_blocks_per_second == 2.0
    assert reference_unit.expected_frames == 180
    assert reference_unit.expected_path_sha256 == D2_REFERENCE_PATH_SHA256


def test_reference_hash_is_absent_from_the_v0_4_manifest():
    """The two manifests are different files; only v0_3 carries the reference."""
    v0_4 = aprime.fir_recovery_manifest()
    hashes = {
        row.get("expected_path_sha256")
        for row in v0_4["units"]
        if isinstance(row, dict)
    }
    assert D2_REFERENCE_PATH_SHA256 not in hashes


# --------------------------------------------------------------------------
# D.2 — the generalized generator at q = 0.05 is bit-identical
# --------------------------------------------------------------------------

def test_q_generalized_generator_reproduces_the_frozen_path_hash():
    positions = _reference_path()
    assert path_sha256(positions) == D2_REFERENCE_PATH_SHA256


def test_q_generalized_generator_matches_the_legacy_inline_arithmetic():
    """Bit-identical to the A-prime inline loop, element by element."""
    legacy, _ = aprime.aprime_generate_path(
        noise_seed=D2_REFERENCE_SEED,
        start_world_x=D2_REFERENCE_START_WORLD_X,
        direction=D2_REFERENCE_DIRECTION,
        q=BINDING_Q,
        speed=SPEED_BLOCKS_PER_SECOND,
        frames=FRAMES_PER_CAPTURE,
    )
    generalized = _reference_path()
    assert generalized.tobytes() == legacy.tobytes()


def test_negative_control_q_perturbation_changes_the_hash():
    perturbed = _reference_path(BINDING_Q + D2_NEGATIVE_CONTROL_Q_PERTURBATION)
    assert path_sha256(perturbed) != D2_REFERENCE_PATH_SHA256


def test_negative_control_operand_order_swap_changes_the_hash():
    swapped = generate_path_noise_first_forbidden(
        D2_REFERENCE_SEED,
        BINDING_Q,
        direction=D2_REFERENCE_DIRECTION,
        start_world_x=D2_REFERENCE_START_WORLD_X,
    )
    digest = path_sha256(swapped)
    assert digest != D2_REFERENCE_PATH_SHA256
    assert digest.startswith(D2_NEGATIVE_CONTROL_NOISE_FIRST_PREFIX)


def test_only_the_drift_first_order_reproduces_the_frozen_hash():
    drift_first = _reference_path()
    noise_first = generate_path_noise_first_forbidden(
        D2_REFERENCE_SEED,
        BINDING_Q,
        direction=D2_REFERENCE_DIRECTION,
        start_world_x=D2_REFERENCE_START_WORLD_X,
    )
    assert path_sha256(drift_first) == D2_REFERENCE_PATH_SHA256
    assert path_sha256(noise_first) != D2_REFERENCE_PATH_SHA256
    # The two diverge by one ULP from tick 40 onward: numerically invisible,
    # catastrophic for the hash.
    deltas = np.abs(drift_first - noise_first)
    assert deltas[:40].max() <= 8.89e-16
    assert deltas[40:].max() > 0.0


# --------------------------------------------------------------------------
# A.3 — the vectorized substitution is not bit-identical
# --------------------------------------------------------------------------

def test_negative_control_vectorized_cumsum_changes_the_hash():
    vectorized = generate_path_vectorized_forbidden(
        D2_REFERENCE_SEED,
        BINDING_Q,
        direction=D2_REFERENCE_DIRECTION,
        start_world_x=D2_REFERENCE_START_WORLD_X,
    )
    assert path_sha256(vectorized) != D2_REFERENCE_PATH_SHA256


# --------------------------------------------------------------------------
# A.2 — RNG stream stability
# --------------------------------------------------------------------------

def test_rng_stream_reproduces_a_committed_reference_digest():
    draws = np.random.default_rng(D2_REFERENCE_SEED).standard_normal(
        FRAMES_PER_CAPTURE
    )
    digest = hashlib.sha256(np.asarray(draws, dtype="<f8").tobytes()).hexdigest()
    # Frozen at A1 under Python 3.14.6 / NumPy 2.4.3, the environment in which
    # the authority verified the end-to-end reproduction below.
    assert digest == (
        "48e73f3a727afb37401b95d51e006c7c7081e09397125970caec12ff095b26d6"
    )


def test_end_to_end_reproduction_of_a_frozen_aprime_unit(reference_unit):
    positions = _reference_path()
    assert path_sha256(positions) == reference_unit.expected_path_sha256


# --------------------------------------------------------------------------
# A.4 — speed / q / dt, and the superseded 1.5 default
# --------------------------------------------------------------------------

def test_noise_scale_is_sqrt_q_dt():
    schedule = generate_noise_schedule(D2_REFERENCE_SEED, FRAMES_PER_CAPTURE, BINDING_Q)
    scale = math.sqrt(BINDING_Q * 0.05)
    assert np.array_equal(schedule.noise_draw, schedule.standard_normal_draw * scale)
    assert schedule.q == MOTION_NOISE_Q == 0.05
    assert schedule.dt == 0.05


def test_speed_one_point_five_is_refused():
    with pytest.raises(ExperimentIIIError) as caught:
        generate_path(
            D2_REFERENCE_SEED,
            BINDING_Q,
            direction=D2_REFERENCE_DIRECTION,
            start_world_x=D2_REFERENCE_START_WORLD_X,
            speed=1.5,
        )
    assert caught.value.blocker == "COHORT_SPEED_VIOLATION"


def test_noise_hash_is_little_endian_defined():
    _positions, noise = generate_path(
        D2_REFERENCE_SEED,
        BINDING_Q,
        direction=D2_REFERENCE_DIRECTION,
        start_world_x=D2_REFERENCE_START_WORLD_X,
    )
    assert noise.dtype.str == "<f8"
    assert noise_sha256(noise) == hashlib.sha256(
        np.asarray(noise, dtype="<f8").tobytes()
    ).hexdigest()
