"""Frozen Experiment III authority constants and provenance binding.

Every value here is reproduced from
``docs/experiment_iii/final_authorities/EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md``
and its machine form. Nothing in this module is a tunable: a value that must
change is a scientific amendment (authority section 9.2), never a repair.

The module recomputes the authority SHA-256 from the file on disk rather than
trusting a literal, so an authority edit is loud (``PROVENANCE_AUTHORITY_DRIFT``)
rather than silent.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "REPOSITORY_ROOT",
    "AUTHORITY_ROOT",
    "AUTHORITY_MARKDOWN_PATH",
    "AUTHORITY_JSON_PATH",
    "PHASE0_DESIGN_PATH",
    "FROZEN_AUTHORITY_SHA256",
    "FROZEN_MACHINE_AUTHORITY_SHA256",
    "FROZEN_PHASE0_DESIGN_SHA256",
    "AUTHORITY_FREEZE_COMMIT",
    "COHORT_SALT_AUTHORITY_SHA256",
    "RUN_NAMESPACE",
    "SPEED_BLOCKS_PER_SECOND",
    "MOTION_NOISE_Q",
    "DT_SECONDS",
    "CAPTURE_HZ",
    "FRAMES_PER_CAPTURE",
    "TARGET_ROWS_PER_CAPTURE",
    "CONTEXT_PAIRS",
    "PRODUCTION_IDENTITY_COUNT",
    "LEFT_TO_RIGHT_COUNT",
    "RIGHT_TO_LEFT_COUNT",
    "OUTER_FOLDS",
    "INNER_ROTATIONS",
    "CANDIDATE_INDEX_BOUND_PER_DIRECTION",
    "MINIMUM_TARGET_SD_BLOCKS",
    "BETWEEN_IDENTITY_DIVERSITY_RMS_BLOCKS",
    "BINDING_Q_SET",
    "DIAGNOSTIC_Q_FALLBACK",
    "START_RANGE",
    "LANE_MIN",
    "LANE_MAX",
    "DIRECTIONS",
    "PRODUCTION_EPISODE_ID_BASE",
    "PILOT_EPISODE_IDS",
    "EPISODE_ID_BLOCK",
    "PRODUCTION_IDENTITY_IDS",
    "PILOT_IDENTITY_IDS",
    "CAMERA_EYE",
    "CAMERA_FEET",
    "LAYOUT_01",
    "FRAMEBUFFER_WIDTH",
    "FRAMEBUFFER_HEIGHT",
    "APRIME_PORT_COMMIT",
    "FIR_RECOVERY_COMMIT",
    "FIR_RECOVERY_PATH",
    "D2_REFERENCE_PATH",
    "D2_REFERENCE_SHA256",
    "D2_REFERENCE_BLOB_SHA1",
    "D2_REFERENCE_UNIT_ID",
    "D2_REFERENCE_SEED",
    "D2_REFERENCE_START_WORLD_X",
    "D2_REFERENCE_PATH_SHA256",
    "D2_NEGATIVE_CONTROL_NOISE_FIRST_PREFIX",
    "direction_sign",
    "authority_sha256",
    "machine_authority_sha256",
    "phase0_design_sha256",
    "machine_authority",
    "master_salt",
    "derive_seed",
    "verify_authority_binding",
    "canonical_bytes",
    "canonical_sha256",
    "sha256_bytes",
    "sha256_file",
]


# --------------------------------------------------------------------------
# Paths and provenance
# --------------------------------------------------------------------------

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AUTHORITY_ROOT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "final_authorities"
AUTHORITY_MARKDOWN_PATH = AUTHORITY_ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md"
AUTHORITY_JSON_PATH = AUTHORITY_ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json"
PHASE0_DESIGN_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "experiment_iii"
    / "experiment_3_authorities"
    / "authority_baseplate"
    / "MineOcclude_Experiment_III_Phase0_Adjudicated_Design.md"
)

#: The frozen authority package, committed at ``AUTHORITY_FREEZE_COMMIT``.
#: v1.8 (Authority Amendment 5, the III-A analysis bootstrap seed). The
#: predecessor v1.7 freeze commit remains immutable provenance, as do v1.6's and
#: v1.5's before it.
FROZEN_AUTHORITY_SHA256 = "472eae5eac83a2709808e64aa449a2ffba24a5a12715b4f1645ce88a3094a9f4"
FROZEN_MACHINE_AUTHORITY_SHA256 = "22f236786013b6bf3d0b702523a2990d145d6b4e0bfb0140ddbefc4e5526613b"
FROZEN_PHASE0_DESIGN_SHA256 = "be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c"
PREDECESSOR_AUTHORITY_FREEZE_COMMIT = "3fe0bc13d18f0002eebb99a2b10ef83e651d6f9a"

#: Authority 2.2a. The master salt is pinned to the authority under which A1
#: materialized the cohort, so an operational amendment cannot regenerate the
#: scientific population. This is v1.5's AUTHORITY_SHA256 and never moves.
COHORT_SALT_AUTHORITY_SHA256 = (
    "3d116d9713b2c7fa705a194023e271061f712d0693618abbd991efa45437d7fb"
)
PREDECESSOR_AUTHORITY_SHA256 = "c773d9620e7fde9e72682d24a7515157522064e8c23b7096780a2995b926985a"
#: v1.6, the predecessor of the predecessor.
PREDECESSOR_2_AUTHORITY_FREEZE_COMMIT = "a1f5dd1a959ff477edbf469cd12bb4db606371ea"
PREDECESSOR_2_AUTHORITY_SHA256 = "62519701bbe08f94839b6dab4e612826f902f31c736727e8c268cf738897ab4c"
#: The commit that froze the CURRENT (v1.8) authority package. It is asserted
#: against PREDECESSOR_AUTHORITY_FREEZE_COMMIT so current and predecessor
#: provenance can never collapse into one another.
AUTHORITY_FREEZE_COMMIT = "043c5301f431d3ec60315ca6ef98caf8d472f010"

if AUTHORITY_FREEZE_COMMIT == PREDECESSOR_AUTHORITY_FREEZE_COMMIT:  # pragma: no cover
    raise RuntimeError(
        "AUTHORITY_FREEZE_COMMIT and PREDECESSOR_AUTHORITY_FREEZE_COMMIT are "
        "identical; a successor freeze was declared but never recorded"
    )

RUN_NAMESPACE = "mineocclude-experiment-iii-v1"
AUTHORITY_VERSION = "v1.8"


# --------------------------------------------------------------------------
# Apparatus and motion (authority 3.1)
# --------------------------------------------------------------------------

SPEED_BLOCKS_PER_SECOND = 2.0
MOTION_NOISE_Q = 0.05
DT_SECONDS = 0.05
CAPTURE_HZ = 20
FRAMES_PER_CAPTURE = 180
TARGET_ROWS_PER_CAPTURE = 19
CONTEXT_PAIRS = 16
FRAMEBUFFER_WIDTH = 640
FRAMEBUFFER_HEIGHT = 360

LANE_MIN = -8.0
LANE_MAX = 8.0

DIRECTIONS = ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")

#: Authority 3.1. The eye is the sightline origin used by every extent test.
CAMERA_FEET = (0.5, 4.0, -5.5)
CAMERA_EYE = (0.5, 5.6200000048, -5.5)

#: Authority 3.2. The occluder is DERIVED from these, never hard-coded, so a
#: layout change fails closed instead of silently mismatching.
LAYOUT_01 = {
    "layout_id": "layout_01",
    "wall_axis": "X",
    "wall_seg_min": -2.5,
    "wall_seg_max": 2.5,
    "wall_ortho_const": 6.0,
    "wall_ortho_offset": -4.0,
    "lane_y": 4.0,
    "lane_min": LANE_MIN,
    "lane_max": LANE_MAX,
}


# --------------------------------------------------------------------------
# Cohort (authority 2.1 - 2.7)
# --------------------------------------------------------------------------

PRODUCTION_IDENTITY_COUNT = 25
LEFT_TO_RIGHT_COUNT = 13
RIGHT_TO_LEFT_COUNT = 12
PILOT_IDENTITY_COUNT = 2
OUTER_FOLDS = 5
IDENTITIES_PER_OUTER_FOLD = 5
INNER_ROTATIONS = 4
FOLD_DIRECTION_COUNTS = ((3, 2), (2, 3), (3, 2), (2, 3), (3, 2))
CANDIDATE_INDEX_BOUND_PER_DIRECTION = 2000
MINIMUM_TARGET_SD_BLOCKS = 0.10
BETWEEN_IDENTITY_DIVERSITY_RMS_BLOCKS = 0.10

#: Authority 2.4 gate 12. Binding; a candidate must satisfy gates 1-11 at each.
BINDING_Q_SET = (0.0125, 0.05, 0.2)
#: Authority 29.4. Recorded as a diagnostic column; NEVER rejects a candidate.
DIAGNOSTIC_Q_FALLBACK = 0.15

START_RANGE = {
    "LEFT_TO_RIGHT": (-8.00, -7.65),
    "RIGHT_TO_LEFT": (7.70, 8.00),
}

CANDIDATE_DOMAIN = {
    "LEFT_TO_RIGHT": "E3_LEFT_TO_RIGHT",
    "RIGHT_TO_LEFT": "E3_RIGHT_TO_LEFT",
}

START_POSITION_RNG_XOR = 0xE3E3E3E3

PRODUCTION_IDENTITY_IDS = tuple(f"e3_t{index:02d}" for index in range(1, 26))
PILOT_IDENTITY_IDS = ("e3_p90", "e3_p91")
PILOT_DIRECTIONS = {"e3_p90": "LEFT_TO_RIGHT", "e3_p91": "RIGHT_TO_LEFT"}

EPISODE_ID_BLOCK = (86001, 86999)
PRODUCTION_EPISODE_ID_BASE = 86001
PILOT_EPISODE_IDS = {"e3_p90": 86901, "e3_p91": 86902}


# --------------------------------------------------------------------------
# Bound historical git objects (authority 5.1, 5.3, test D.2)
# --------------------------------------------------------------------------

APRIME_PORT_COMMIT = "a5d763a2ed4574c082dce2572ddb97c831929f81"
APRIME_PORT_BLOBS = {
    "src/mineocclude/prospective/extent_geometry.py": (
        "45889b6bc9ed07129f5fd2f15167b694206eab31"
    ),
}

FIR_RECOVERY_COMMIT = "f2bc2c8082e77f9c3f9e089f2fb1a20b11a052a8"
FIR_RECOVERY_PATH = (
    "docs/status/integration/regime_a_prime_qualification_v0_1/"
    "prospective_development_authority_v0_4/stage2_locked_manifest.json"
)
FIR_RECOVERY_SHA256 = "f89c24fe01c18dc19432c425583bec25d3331173b19ef23f95094bd46f0a170e"

D2_REFERENCE_COMMIT = FIR_RECOVERY_COMMIT
D2_REFERENCE_PATH = (
    "docs/status/integration/regime_a_prime_qualification_v0_1/"
    "prospective_development_authority_v0_3/stage2_locked_manifest.json"
)
D2_REFERENCE_BLOB_SHA1 = "fb93a08ba2d71c28c9929469d9b34bf8fc6de17b"
D2_REFERENCE_BYTES = 270672
D2_REFERENCE_SHA256 = "ad718685b33030a0c0de405cd9d3abb737c3f3e9d087ad7c78768fe151855eb8"
D2_REFERENCE_UNIT_ID = "a2x_t01_wall"
D2_REFERENCE_SEED = 2154560968567132226
D2_REFERENCE_START_WORLD_X = -7.8
D2_REFERENCE_DIRECTION = "LEFT_TO_RIGHT"
D2_REFERENCE_PATH_SHA256 = (
    "b5803943e515ea633cc4dd80ddeaf349db5cb99d11980febdc3f13d7f84a56b7"
)
D2_NEGATIVE_CONTROL_NOISE_FIRST_PREFIX = "6713929a169500a0a80ad05c"
D2_NEGATIVE_CONTROL_Q_PERTURBATION = 1e-12


# --------------------------------------------------------------------------
# Hashing helpers
# --------------------------------------------------------------------------

def canonical_bytes(value: object) -> bytes:
    """Canonical JSON bytes: sorted keys, no whitespace, no NaN."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, chunk_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def direction_sign(direction: str) -> float:
    """+1 for LEFT_TO_RIGHT, -1 for RIGHT_TO_LEFT. Refuses anything else."""
    if direction == "LEFT_TO_RIGHT":
        return 1.0
    if direction == "RIGHT_TO_LEFT":
        return -1.0
    raise ExperimentIIIError(
        "COHORT_MATRIX_INCONSISTENT", f"unknown motion direction: {direction!r}"
    )


# --------------------------------------------------------------------------
# Authority binding
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def authority_sha256() -> str:
    """SHA-256 of the canonical human authority, recomputed from disk."""
    if not AUTHORITY_MARKDOWN_PATH.is_file():
        raise ExperimentIIIError(
            "AUTHORITY_INCOMPLETE",
            f"canonical authority is absent: {AUTHORITY_MARKDOWN_PATH}",
        )
    return sha256_file(AUTHORITY_MARKDOWN_PATH)


@lru_cache(maxsize=1)
def machine_authority_sha256() -> str:
    if not AUTHORITY_JSON_PATH.is_file():
        raise ExperimentIIIError(
            "AUTHORITY_INCOMPLETE",
            f"machine authority is absent: {AUTHORITY_JSON_PATH}",
        )
    return sha256_file(AUTHORITY_JSON_PATH)


@lru_cache(maxsize=1)
def phase0_design_sha256() -> str:
    if not PHASE0_DESIGN_PATH.is_file():
        raise ExperimentIIIError(
            "AUTHORITY_INCOMPLETE",
            f"Phase 0 adjudicated design is absent: {PHASE0_DESIGN_PATH}",
        )
    return sha256_file(PHASE0_DESIGN_PATH)


@lru_cache(maxsize=1)
def machine_authority() -> dict:
    """The parsed machine authority, for values cross-checked against the text."""
    return json.loads(AUTHORITY_JSON_PATH.read_text(encoding="utf-8"))


def verify_authority_binding() -> dict[str, str]:
    """Refuse to run against a drifted authority package.

    Called by every artifact writer. Authority drift after the freeze commit is
    ``PROVENANCE_AUTHORITY_DRIFT`` and is terminal for the artifact.
    """
    observed = {
        "AUTHORITY_SHA256": authority_sha256(),
        "MACHINE_AUTHORITY_SHA256": machine_authority_sha256(),
        "PHASE0_DESIGN_SHA256": phase0_design_sha256(),
    }
    expected = {
        "AUTHORITY_SHA256": FROZEN_AUTHORITY_SHA256,
        "MACHINE_AUTHORITY_SHA256": FROZEN_MACHINE_AUTHORITY_SHA256,
        "PHASE0_DESIGN_SHA256": FROZEN_PHASE0_DESIGN_SHA256,
    }
    drift = {
        name: {"expected": expected[name], "observed": value}
        for name, value in observed.items()
        if value != expected[name]
    }
    if drift:
        raise ExperimentIIIError(
            "PROVENANCE_AUTHORITY_DRIFT",
            f"frozen authority package has changed on disk: {drift}",
        )
    return observed


@lru_cache(maxsize=1)
def master_salt() -> str:
    """``EXPERIMENT_III_MASTER_SALT`` (authority 2.2, 2.2a).

    ``sha256("MINEOCCLUDE_EXPERIMENT_III_V1|" + COHORT_SALT_AUTHORITY_SHA256 +
    "|" + PHASE0_DESIGN_SHA256)``. Derived from immutable published digests,
    never chosen: a salt substituted to obtain a more convenient candidate stream
    is an explicitly forbidden repair.

    The first input is **pinned** to the authority under which A1 materialized the
    cohort (v1.5), not to the current authority hash. Reading the current hash
    coupled the scientific population to every later authority edit: an
    operational amendment would have produced a different candidate stream and a
    different 25-identity cohort. Authority Amendment 3g closed that, so the
    materialized cohort is byte-identical across v1.5 and v1.6.
    """
    verify_authority_binding()
    payload = (
        "MINEOCCLUDE_EXPERIMENT_III_V1|"
        + COHORT_SALT_AUTHORITY_SHA256
        + "|"
        + phase0_design_sha256()
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def derive_seed(domain: str, index: int) -> int:
    """``seed(domain,index)`` of authority 2.2, as a non-negative 63-bit int."""
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", "candidate index must be a non-negative int"
        )
    payload = f"experiment-iii-v1|{domain}|{master_salt()}|{index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") & ((1 << 63) - 1)
