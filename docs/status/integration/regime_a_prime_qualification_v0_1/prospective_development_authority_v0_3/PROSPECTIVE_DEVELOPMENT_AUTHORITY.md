# Regime A' — prospective development authority v0.3

**Classification: DEVELOPMENT_ONLY. Prospective. Written before any v0.3
qualification datum exists.**

| | |
|---|---|
| Artifact | `regime-a-prime-prospective-development-authority-v0.3` |
| Predecessor | `regime-a-prime-prospective-development-authority-v0.2` at freeze `560bc01e3b01ecdc266737c015fed6677b0611c3` |
| Predecessor Stage-1 result | **SCIENTIFIC FAIL — terminal, immutable** |
| Stage-2 | **UNAUTHORIZED** |

## 1. The predecessor result stands

`560bc01` ran a complete Stage-1: 8/8 units, 0 operational retries. It passed
`unit_completeness`, `required_evidence_completeness`,
`calibration_world_and_wall_relative_support`, `calibration_detector_response`
and `render_server_temporal_alignment`, and it **failed**
`stable_visibility_base_rate_robust` on a single legitimate false positive —
`a1q_rtl_wall_r02` frame 28, `0.006282776508991` blocks inside the transferred
band, with every evidence flag valid. The frozen FIRST_N hidden-row schedule
selects rows nearest the boundary, so the same row also failed
`hidden_row_contamination`.

That decision is complete historical scientific evidence. v0.3 does not repair
it, reclassify it, launder it into PASS, or authorize Stage-2 from it. Nothing in
this package may be read as doing so.

## 2. Why v0.3 exists

The v0.2 truth predicate was *point visibility outside a detector-measured
transition band transferred from an independent replicate*. The scored detector
is an **area** predicate over the rendered magenta silhouette. A centre-point
truth predicate and an area detector must disagree on rows where the silhouette
straddles the occlusion edge — not as a defect, but by construction. `560bc01`
found exactly such a row.

v0.3 adopts historical redesign **Option A**: the independent geometric truth
predicate measures the target's **rendered extent**, so truth and detector are
predicates over the same physical quantity.

## 3. The truth predicate

```
primary_predicate = extent_occlusion_geometry_over_rendered_target_extent
```

Each row is classified from camera geometry, as-built wall geometry, the target
centre and the declared rendered extent:

| Class | Meaning | Scored |
|---|---|---|
| `EXTENT_FULLY_VISIBLE` | no point of the declared extent is occluded | yes → `stable_visible` |
| `EXTENT_PARTIAL` | any mixture | **no** — reported only |
| `EXTENT_FULLY_OCCLUDED` | every point of the declared extent is occluded | yes → `stable_occluded` |

`EXTENT_FULLY_OCCLUDED` is decided **exactly**. Beyond the occluder the occluded
set is the cone from the camera through the convex wall box, which is convex, so
it contains the extent box iff it contains every corner; the sample lattice is
closed on both faces of each axis and therefore always contains the corners.

**No detector output, no detector edge, and no band transferred from another
replicate participates.** Every held-out row is classified directly from its own
geometry. `point_visible` keeps its v0.2 meaning as a diagnostic and as the
primitive the Python engine is validated against; it is not redefined and not
scored.

## 4. The target extent

```
target_extent_horizontal_half_blocks = (7 + √48.5) / 16 = 0.8727621336620037
```

Derived in closed form from the wool model geometry of the pinned Minecraft
1.16.5 client (`sha1 37fd3c90…`, byte-identical to Mojang's published client),
maximised over the **whole reachable animation set** — see
`TARGET_EXTENT_DERIVATION.md`. It is yaw-independent: the larger horizontal bound
is applied to both world axes, so the predicate never has to trust a logged
heading.

The bound is conservative in the only safe direction. An over-large extent can
only widen the unscored `EXTENT_PARTIAL` band and shrink the scored classes; an
under-large one would declare `EXTENT_FULLY_OCCLUDED` with wool still on screen —
the exact false-positive mode that failed at `560bc01`. Over-conservatism is
policed independently by the `>= 60` sample floor.

The repository's historical `w ≈ 0.6–0.8` estimate was **back-solved from the
observed detector transition** and is rejected as a definition; it appears only
as an after-the-fact corroboration check.

## 5. Implementation locus

The geometry engine is **Python** (`src/mineocclude/prospective/extent_geometry.py`).
The Fabric mod is deliberately unmodified, so every pinned apparatus artefact
keeps its hash.

The engine replicates `GeometryUtil.segmentHitsWall` exactly — including its
63-sample march and inclusive face tests — and uses the wall *as built*
(`ArenaBuilder` floors/ceils the spec to whole blocks). It fails closed:
`verify_reference_agreement` refuses to certify the engine unless it reproduces
the mod's own published occlusion answers, and the evaluator refuses an authority
whose declared extent does not recompute from the model constants.

## 6. Transition measurement, and the derivation fix

The transition role is retained but **re-purposed**. Intervals are derived
*geometrically* on the predeclared WALL `TRANSITION_MEASUREMENT` replicates and
calibrate the rendered detector's response across the geometric transition. They
define no boundary that held-out truth depends on, and the evidence must say so
(`detector_defines_held_out_truth: false`).

**Required fix.** A row may contribute to any derivation requiring aligned
physical position **only if `temporal_alignment_resolved == true`**. A finite raw
`world_x` is not a substitute: across the causal-FIR warm-up prefix the raw
coordinate exists while the aligned one does not. At v0.2 the builder derived from
aligned values (self-excluding in warm-up) while the evaluator re-derived from
raw `sample["world_x"]` with no filter, inflating the interval toward the lane
extremes. Builder and evaluator now read one aligned-position field through one
admissibility rule.

## 7. Unchanged gates

Retained at full strength, and **not** relaxed because the predecessor failed by
one frame:

- `minimum_stable_samples_per_direction_per_class = 60`
- false positives = 0, false negatives = 0 on the stable extent classes
- pooled precision and pooled accuracy qualification forbidden (H2)
- causal FIR alignment, direction-specific, two estimands, pure-delay refusal,
  per-trajectory coverage, exact warm-up handling (H3)
- no stale fixed `HIDDEN_BOUNDS` (H5)
- `seed == noise_seed` — one seed identity per unit
- camera eye/feet interpretation, FOV and framebuffer verified from captured bytes
- durable write/readback, exact runtime provenance, fail closed

`FROZEN_HUD_VERIFIER_IMPLEMENTED = false`. `hud_hidden` stays observational; v0.3
does not elevate it.

**No guard band was added.** No exclusion exists around `0.006282776508991`. The
failing row is not excluded — it is not reachable, because v0.3 collects new units.

## 8. Hidden-row selection

`FIRST_N_QUALIFIED_STABLE_OCCLUDED_ROWS_IN_ASCENDING_MODEL_FRAME_ORDER`, 19 rows
per held-out WALL run, maximum contamination 0 per prohibited class.

**Retained deliberately as the conservative stress test.** The window is *not*
moved away from the boundary because the predecessor's first row failed there —
that would weaken the test in response to an outcome. Under extent geometry a
FIRST_N row is fully occluded over its whole rendered extent, not merely at its
centre.

## 9. Prospective sample floor

Computed before the authority was frozen, from the frozen trajectory design and
deterministic geometry only — no v0.3 data existed:

| | LEFT_TO_RIGHT | RIGHT_TO_LEFT | Required |
|---|---|---|---|
| stable visible | 212 | 202 | ≥ 60 |
| stable occluded | 77 | 86 | ≥ 60 |
| partial (unscored) | 55 | 56 | > 0 |

`SAMPLE_FLOOR_PROSPECTIVELY_SATISFIED = true`. Partial band ≈ 2.6195 blocks per
edge (2·extent magnified by the 11.5/7.5 perspective ratio at the target depth).
Counts are invariant across lattice densities 3, 5, 9 and 17 per axis.

## 10. Unit inventory

8 new units — 2 directions × 2 scenes × 2 roles — at 2.0 blocks/s, 180 frames.
New IDs (`a1x_*`), new episode block (83001–83008), new seeds, new receipt paths,
new namespace, new durable prefix. **No `560bc01` unit, episode, capture, or
receipt is reachable from this package**, and none is recollected.

## 11. Claim boundary

A v0.3 PASS qualifies the **measurement apparatus** for the next
authority-permitted development stage. It establishes nothing about hidden-state
representation, object permanence, belief, uncertainty, or causal use. Those
remain downstream experiments.

`STAGE2_AUTHORIZED = false`, and stays false unless and until a v0.3 Stage-1
produces an exact legitimate PASS artifact under this authority.
