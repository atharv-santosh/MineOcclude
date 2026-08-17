# Prospective sample-floor analysis — v0.3 extent predicate

**Label: PROSPECTIVE. Computed before the v0.3 authority was frozen and before
any v0.3 datum existed. No v0.3 outcome data enters this document.**

## Question

Does the yaw-independent target half-extent `0.8727621336620037` still permit the
Stage-1 design to satisfy `minimum_stable_samples_per_direction_per_class >= 60`,
given that a conservative extent necessarily widens the unscored partial band?

## Inputs — all frozen, none observed from v0.3

| Input | Value | Source |
|---|---|---|
| camera eye | `(0.5, 5.62, -5.5)` | authority `apparatus.camera_eye_world_xyz` |
| target centre height | `4.5` | `cfg.laneY + 0.5`, the height `EpisodeManager` tests |
| lane | `x ∈ [-8, 8]` at `z = 6.0` | `Layouts.layout_01` |
| wall as built | `x ∈ [-3, 4]`, `z ∈ [2, 3]`, `y ∈ [4, 7]` | `ArenaBuilder` floor/ceil of the spec |
| speed / frames | 2.0 blocks/s, 180 frames, 1 tick per frame | `fixed_development_configuration` |
| causal-FIR warm-up | 8 frames unresolved | `maximum_lag_ticks_for_estimation` |
| occlusion primitive | `GeometryUtil.segmentHitsWall`, 63-sample march | Fabric mod, replicated exactly |

The per-frame aligned position schedule is the frozen trajectory design (2.0
blocks/s over a 16-block lane with the frozen noise process, 180 frames, 172
aligned). It is a property of the apparatus, not of any detector outcome.

## Lane structure under the extent predicate

Scanning the lane at 0.0005-block resolution:

| Region | `world_x` | Width |
|---|---|---|
| fully visible | `[-8.0000, -6.1160]` | 1.8840 |
| partial | `[-6.1160, -3.4965]` | 2.6195 |
| fully occluded | `[-3.4965, 4.4970]` | 7.9935 |
| partial | `[4.4970, 7.1165]` | 2.6195 |
| fully visible | `[7.1165, 8.0000]` | 0.8835 |

The partial band is `2 × 0.87276 = 1.7455` blocks of extent magnified by the
perspective ratio `11.5 / 7.5 = 1.533` between camera→wall and camera→target
depth, giving `2.676` — consistent with the measured `2.6195` once the wall's
finite thickness is included.

## Result

Held-out validation replicates supply the scored rows: one WALL and one NO_WALL
unit per direction.

```
EXTENT_HALF_WIDTH_BLOCKS       = 0.8727621336620037
EXPECTED_PARTIAL_WORLD_X_WIDTH = 2.6195   (per edge)

LTR_STABLE_VISIBLE_AVAILABLE   = 212      (172 NO_WALL + 40 WALL)
LTR_STABLE_OCCLUDED_AVAILABLE  = 77
RTL_STABLE_VISIBLE_AVAILABLE   = 202      (172 NO_WALL + 30 WALL)
RTL_STABLE_OCCLUDED_AVAILABLE  = 86

MINIMUM_REQUIRED_EACH_CLASS    = 60
SAMPLE_FLOOR_PROSPECTIVELY_SATISFIED = true
```

Held-out partial rows are 55 (LTR) and 56 (RTL), satisfying
`partial_transition_observation_required_on_held_out_wall`. Stable-occluded
counts exceed the 19 rows the FIRST_N contamination schedule requires.

## Robustness

Counts are **identical** for lattice densities 3, 5, 9 and 17 samples per axis, so
the sample floor does not depend on the sampling constant.

Counts are also identical at the superseded draft extent `0.8727621026470629`,
which differs by `3.1×10⁻⁸` blocks — no row on the frozen schedule lies that close
to a class boundary. The extent correction was therefore adopted for
reproducibility and containment, **not** for sample yield.

## Margin

The binding class is stable-occluded on the WALL held-out replicates: 77 (LTR) and
86 (RTL) against a floor of 60.

Sweeping the extent upward on the frozen schedule, the first half-extent at which
any direction/class falls below 60 is `h = 1.5028` blocks — LTR stable-occluded
drops to 58 there. That is **+0.6300 blocks** beyond the declared value, i.e. the
declared extent could be over-large by a factor of 1.72 and the design would still
qualify.

The conservative bound is therefore far inside the design's headroom, and no
pressure exists to shrink it. This is the intended relationship between the two
safeguards: the extent is chosen as an upper bound on physical grounds, and the
sample floor — not the extent — is what would refuse an over-conservative design.
