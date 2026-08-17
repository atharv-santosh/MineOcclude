"""Detector-independent occlusion geometry over the target's rendered extent.

Regime A' v0.3 replaces the centre-ray point-visibility truth predicate with an
occlusion test over the sheep's *rendered* horizontal extent (historical Option
A). The scored magenta detector is an area predicate; the independent geometric
truth predicate must therefore represent an area too, or the two disagree by
construction on every row where the silhouette straddles the shadow edge. That
disagreement is exactly what failed at ``560bc01``.

Three properties are load-bearing and are enforced by the tests:

* **Detector-independent.** Nothing in this module reads ``detector_visible``,
  any transferred detector band, or any observed Stage-1 outcome. The inputs are
  the frozen layout, the camera pose, the target centre, and a target extent
  derived from the pinned client jar's model geometry.
* **Reference-faithful.** :func:`segment_hits_wall` is a line-for-line
  replication of ``GeometryUtil.segmentHitsWall`` in the Fabric mod, including
  its 63-sample march and its inclusive bounds. The mod is *not* modified for
  v0.3, so every pinned apparatus artefact keeps its hash; this module must
  therefore agree with the mod rather than improve on it.
* **Fail-closed.** The wall used here is the wall *as built* (``ArenaBuilder``
  floors/ceils the spec to whole blocks), reproduced by
  :meth:`WallGeometry.from_layout` from the same expressions the mod uses.
  :func:`verify_reference_agreement` refuses to certify the engine if it cannot
  reproduce the mod's point-level answers.

See ``docs/status/integration/regime_a_prime_qualification_v0_1/
prospective_development_authority_v0_3/TARGET_EXTENT_DERIVATION.md``.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

__all__ = [
    "SHEEP_FUR_MODEL_CONSTANTS",
    "TARGET_EXTENT_HALF_BLOCKS",
    "ExtentClass",
    "WallGeometry",
    "derive_target_extent_half_blocks",
    "segment_hits_wall",
    "classify_extent",
    "extent_sample_points",
    "verify_reference_agreement",
    "ReferenceAgreementError",
]


# --------------------------------------------------------------------------
# Target extent, derived in closed form from the pinned client jar
# --------------------------------------------------------------------------

#: Constants transcribed from ``javap -p -c dvm.class`` / ``dvi.class`` on the
#: Minecraft 1.16.5 client jar (``sha1 37fd3c903861eeff3bc24b71eed48f828b5269c8``,
#: byte-identical to Mojang's published client). Units are 1/16 block, matching
#: the model's own units. ``dvm`` is ``SheepFurModel`` -- the *wool* layer, which
#: is the magenta surface the detector responds to, not the collision box.
SHEEP_FUR_MODEL_CONSTANTS = {
    # part: (cuboid origin xyz, size xyz, dilation, pivot xyz)
    "head": ((-3.0, -4.0, -4.0), (6.0, 6.0, 6.0), 0.6, (0.0, 6.0, -8.0)),
    "body": ((-4.0, -10.0, -7.0), (8.0, 16.0, 6.0), 1.75, (0.0, 5.0, 2.0)),
    "leg": ((-2.0, 0.0, -2.0), (4.0, 6.0, 4.0), 0.5, None),
    # QuadrupedModel (dvi) leg pivots: rear pair at z=+7, front pair at z=-5.
    "leg_pivots": ((-3.0, 12.0, 7.0), (3.0, 12.0, 7.0),
                   (-3.0, 12.0, -5.0), (3.0, 12.0, -5.0)),
    # QuadrupedModel.setupAnim animation constants.
    "leg_x_rot_amplitude": 1.4,          # ldc 1.4f
    "body_x_rot": 1.5707964,             # ldc 1.5707964f, a CONSTANT pi/2
    "head_yaw_scale": 0.017453292,       # ldc 0.017453292f
    "model_units_per_block": 16.0,
}


def derive_target_extent_half_blocks() -> float:
    """Recompute the declared extent from the model constants, in closed form.

    The bound is the largest horizontal displacement any wool vertex can reach
    from the entity origin, maximised over the *whole* reachable animation set
    rather than evaluated at one pose. The longitudinal (model ``z``) bound
    dominates and is driven by a rear leg at full swing.

    ``limbSwingAmount`` is clamped to 1 by the renderer, so ``|xRot| <= 1.4``.
    Maximising ``z' = y*sin(t) + z*cos(t)`` over the dilated leg cuboid corners
    ``y in [-0.5, 6.5]``, ``z in [-2.5, 2.5]`` is attained at ``(6.5, 2.5)``. Its
    stationary point ``t* = atan2(6.5, 2.5) = 1.2036...`` lies strictly inside
    ``[-1.4, 1.4]``, so the clamp is inactive and the maximum is the closed-form
    amplitude ``sqrt(6.5**2 + 2.5**2)``.

    The result is applied to *both* horizontal world axes (yaw-independent): the
    truth predicate then never has to trust a logged heading, and the bound is
    conservative in the only safe direction -- an over-large extent widens the
    unscored ``EXTENT_PARTIAL`` band, while an under-large one would declare
    ``EXTENT_FULLY_OCCLUDED`` with wool still on screen.
    """
    origin, size, dilation, _ = SHEEP_FUR_MODEL_CONSTANTS["leg"]
    y_low = origin[1] - dilation
    y_high = origin[1] + size[1] + dilation
    z_high = origin[2] + size[2] + dilation
    amplitude = math.hypot(y_high, z_high)
    # The clamp must be inactive for the closed form to be the true maximum.
    if not abs(math.atan2(y_high, z_high)) <= SHEEP_FUR_MODEL_CONSTANTS["leg_x_rot_amplitude"]:
        raise ValueError("leg swing clamp is active; closed-form amplitude is not the maximum")
    if y_low > 0.0:
        raise ValueError("leg cuboid does not straddle its pivot as the model declares")
    rear_pivot_z = max(pivot[2] for pivot in SHEEP_FUR_MODEL_CONSTANTS["leg_pivots"])
    longitudinal = rear_pivot_z + amplitude
    return longitudinal / SHEEP_FUR_MODEL_CONSTANTS["model_units_per_block"]


#: ``(7 + sqrt(48.5)) / 16 == 0.8727621336620037``.
TARGET_EXTENT_HALF_BLOCKS = derive_target_extent_half_blocks()


class ExtentClass(enum.Enum):
    """Geometric occlusion state of the target's declared rendered extent."""

    EXTENT_FULLY_VISIBLE = "extent_fully_visible"
    EXTENT_PARTIAL = "extent_partial"
    EXTENT_FULLY_OCCLUDED = "extent_fully_occluded"

    @property
    def is_stable(self) -> bool:
        return self is not ExtentClass.EXTENT_PARTIAL

    @property
    def regime(self) -> str:
        """The Stage-1 regime name this extent class maps to."""
        return {
            ExtentClass.EXTENT_FULLY_VISIBLE: "stable_visible",
            ExtentClass.EXTENT_FULLY_OCCLUDED: "stable_occluded",
            ExtentClass.EXTENT_PARTIAL: "partial_transition",
        }[self]


class ReferenceAgreementError(RuntimeError):
    """The Python engine disagrees with the mod's reference geometry."""


# --------------------------------------------------------------------------
# Reference primitive -- exact replication of GeometryUtil.segmentHitsWall
# --------------------------------------------------------------------------

#: ``GeometryUtil.segmentHitsWall`` marches ``samples = 64`` and iterates
#: ``i in [1, 64)``, i.e. 63 interior samples with neither endpoint tested.
#: This is a discrete approximation, not an analytic slab intersection. It is
#: replicated exactly -- including the sample count -- because the mod is the
#: trusted reference and is deliberately left unmodified for v0.3.
REFERENCE_MARCH_SAMPLES = 64


def segment_hits_wall(
    cam_x: float, cam_y: float, cam_z: float,
    tgt_x: float, tgt_y: float, tgt_z: float,
    wall_ortho: float, wall_axis_min: float, wall_axis_max: float,
    wall_y_min: float, wall_y_max: float, half: float,
    *, wall_axis: str = "X",
) -> bool:
    """Line-for-line replication of ``GeometryUtil.segmentHitsWall``.

    Bounds are inclusive on every face exactly as the Java does (``<=`` on the
    ortho distance, ``>=``/``<=`` on the axis and vertical spans). The arithmetic
    is IEEE-754 double in both languages and the expression order is preserved,
    so the two agree bit-for-bit on identical inputs.
    """
    if wall_axis not in ("X", "Z"):
        raise ValueError("wall_axis must be 'X' or 'Z'")
    for i in range(1, REFERENCE_MARCH_SAMPLES):
        t = i / REFERENCE_MARCH_SAMPLES
        px = cam_x + (tgt_x - cam_x) * t
        py = cam_y + (tgt_y - cam_y) * t
        pz = cam_z + (tgt_z - cam_z) * t
        ortho = pz if wall_axis == "X" else px
        axis = px if wall_axis == "X" else pz
        in_ortho = abs(ortho - wall_ortho) <= half
        in_axis = wall_axis_min <= axis <= wall_axis_max
        in_y = wall_y_min <= py <= wall_y_max
        if in_ortho and in_axis and in_y:
            return True
    return False


@dataclass(frozen=True)
class WallGeometry:
    """The occluder *as built*, in the parameterisation the mod passes.

    ``ArenaBuilder`` places whole blocks, and a block at coordinate ``n`` occupies
    ``[n, n+1)``, so the realised occluder is wider and thicker than the raw
    layout spec. ``EpisodeManager`` accounts for this by flooring/ceiling the
    spec at the call site; :meth:`from_layout` reproduces those same expressions
    rather than the spec, because testing the spec declared "visible" while the
    rendered wall still occluded the sheep.
    """

    wall_axis: str
    wall_ortho: float
    wall_axis_min: float
    wall_axis_max: float
    wall_y_min: float
    wall_y_max: float
    half: float
    present: bool = True

    #: ``ArenaBuilder.WALL_HEIGHT``.
    WALL_HEIGHT = 3
    #: The ortho half-thickness the mod passes at every call site.
    ORTHO_HALF = 0.5

    @classmethod
    def from_layout(
        cls,
        *,
        wall_axis: str,
        wall_seg_min: float,
        wall_seg_max: float,
        wall_ortho_const: float,
        wall_ortho_offset: float,
        lane_y: float,
        present: bool = True,
    ) -> "WallGeometry":
        wall_ortho = wall_ortho_const + wall_ortho_offset
        return cls(
            wall_axis=wall_axis,
            # Math.floor(wallOrtho) + 0.5
            wall_ortho=math.floor(wall_ortho) + 0.5,
            # Math.floor(cfg.wallSegMin)
            wall_axis_min=math.floor(wall_seg_min),
            # Math.ceil(cfg.wallSegMax) + 1.0
            wall_axis_max=math.ceil(wall_seg_max) + 1.0,
            wall_y_min=lane_y,
            wall_y_max=lane_y + cls.WALL_HEIGHT,
            half=cls.ORTHO_HALF,
            present=present,
        )

    def occludes(self, camera: Sequence[float], target: Sequence[float]) -> bool:
        """Reference point occlusion for one camera->target sightline."""
        if not self.present:
            return False
        return segment_hits_wall(
            camera[0], camera[1], camera[2],
            target[0], target[1], target[2],
            self.wall_ortho, self.wall_axis_min, self.wall_axis_max,
            self.wall_y_min, self.wall_y_max, self.half,
            wall_axis=self.wall_axis,
        )


# --------------------------------------------------------------------------
# Extent classification
# --------------------------------------------------------------------------

#: Samples per horizontal axis across the extent box. The box corners alone
#: decide FULLY_OCCLUDED exactly (see :func:`classify_extent`); the interior
#: samples exist only to make FULLY_VISIBLE conservative, and the tests prove the
#: classification is stable under refinement so this is not a tuned constant.
EXTENT_SAMPLES_PER_AXIS = 5


def extent_sample_points(
    centre: Sequence[float], half_extent: float, *,
    samples_per_axis: int = EXTENT_SAMPLES_PER_AXIS,
) -> list[tuple[float, float, float]]:
    """Deterministic sample lattice over the horizontal extent box.

    The lattice is closed on both faces of each horizontal axis, so the four box
    corners are always members regardless of ``samples_per_axis``. The vertical
    coordinate is the target centre height the mod itself tests
    (``cfg.laneY + 0.5``); the extent is declared horizontally, and the wall's
    vertical span strictly contains the sightline band at this layout, which
    :func:`verify_reference_agreement` re-checks rather than assumes.
    """
    if samples_per_axis < 2:
        raise ValueError("samples_per_axis must be at least 2 so corners are included")
    if not math.isfinite(half_extent) or half_extent <= 0.0:
        raise ValueError("half_extent must be a positive finite number of blocks")
    offsets = [
        -half_extent + (2.0 * half_extent) * index / (samples_per_axis - 1)
        for index in range(samples_per_axis)
    ]
    return [
        (centre[0] + dx, centre[1], centre[2] + dz)
        for dx in offsets
        for dz in offsets
    ]


def classify_extent(
    camera: Sequence[float],
    centre: Sequence[float],
    wall: WallGeometry,
    *,
    half_extent: float = TARGET_EXTENT_HALF_BLOCKS,
    samples_per_axis: int = EXTENT_SAMPLES_PER_AXIS,
) -> ExtentClass:
    """Classify the target's rendered extent as fully visible/partial/occluded.

    Semantics, fixed prospectively:

    * ``EXTENT_FULLY_OCCLUDED`` -- *every* point of the declared extent is
      geometrically occluded. This is decided **exactly** by the box corners:
      within the region beyond the occluder the occluded set is the cone from the
      camera through the (convex) wall box, which is convex, so it contains the
      box iff it contains all of its corners. The lattice is a superset of the
      corners, so requiring all lattice points occluded is the same test.
    * ``EXTENT_FULLY_VISIBLE`` -- *no* sampled point of the extent is occluded.
    * ``EXTENT_PARTIAL`` -- any mixture. Reported, never scored.

    A wall-free scene has no occluder, so every row is fully visible.
    """
    if not wall.present:
        return ExtentClass.EXTENT_FULLY_VISIBLE
    results = [
        wall.occludes(camera, point)
        for point in extent_sample_points(
            centre, half_extent, samples_per_axis=samples_per_axis)
    ]
    if all(results):
        return ExtentClass.EXTENT_FULLY_OCCLUDED
    if not any(results):
        return ExtentClass.EXTENT_FULLY_VISIBLE
    return ExtentClass.EXTENT_PARTIAL


# --------------------------------------------------------------------------
# Fail-closed cross-check against the mod's own reference answers
# --------------------------------------------------------------------------

def verify_reference_agreement(
    camera: Sequence[float],
    wall: WallGeometry,
    reference_samples: Iterable[Mapping[str, object]],
    *,
    target_centre_y: float,
    lane_axis: str = "X",
    lane_ortho_const: float,
) -> dict[str, object]:
    """Reproduce the mod's ``integer_lane_samples`` occlusion shadow exactly.

    ``EpisodeManager`` emits, once per episode, an occlusion answer at every
    integer lane position using the same primitive the runtime uses. That ledger
    is the only place the mod publishes its geometry in a form this engine can be
    checked against, so it is the cross-check: identical camera, identical wall,
    identical target centre, point semantics on both sides.

    Raises :class:`ReferenceAgreementError` on any disagreement. The caller must
    not fall back to extent truth with an engine that has failed this check.
    """
    disagreements = []
    checked = 0
    for sample in reference_samples:
        axis_position = sample.get("axis_position")
        expected = sample.get("occluded")
        if not isinstance(axis_position, (int, float)) or not isinstance(expected, bool):
            raise ReferenceAgreementError(
                "reference lane sample is missing axis_position or occluded")
        if lane_axis == "X":
            target = (float(axis_position), target_centre_y, lane_ortho_const)
        else:
            target = (lane_ortho_const, target_centre_y, float(axis_position))
        observed = wall.occludes(camera, target)
        checked += 1
        if observed is not expected:
            disagreements.append(
                {"axis_position": axis_position, "mod": expected, "python": observed})
    if not checked:
        raise ReferenceAgreementError("no reference lane samples were supplied")
    if disagreements:
        raise ReferenceAgreementError(
            f"python geometry disagrees with the mod on {len(disagreements)} of "
            f"{checked} reference lane samples: {disagreements[:8]}")
    return {
        "reference_lane_samples_checked": checked,
        "disagreements": 0,
        "primitive": "GeometryUtil.segmentHitsWall",
        "march_samples": REFERENCE_MARCH_SAMPLES,
    }
