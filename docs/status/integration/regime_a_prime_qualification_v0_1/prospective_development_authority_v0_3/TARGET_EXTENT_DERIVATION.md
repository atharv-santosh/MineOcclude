# Target extent derivation — renderer-geometry upper bound

**Label: PROSPECTIVE DESIGN INPUT. Derived before any v0.3 qualification outcome
exists. No Stage-1 v0.3 data had been collected when this document was written.**

## Why this document exists

Historical Option A (`p3_terminal_forensic_audit_v0_1/12_redesign_options.md:29-33`)
requires replacing the centre-point visibility predicate with an occlusion test over
the target's **rendered extent**. It never fixed the extent itself, and that single
scalar sets the width of the unscored partial band and therefore decides the gate.

The repository's only pre-existing numeric candidate is `w ≈ 0.6–0.8` blocks
(`03_visibility_forensics.md:§4a`, produced by `a03_transition_geometry.py`). That
value was **back-solved from the observed detector transition**. Adopting it would
make the new truth predicate a function of the detector it is meant to score, and
would import a fitted constant into a prospective authority. It is therefore
rejected as the definition, and used **only** as an independent corroboration check
at the end of this document.

This derivation instead takes the extent from the renderer's own model geometry.

## Provenance of the geometry

Every number below is read out of the actual rendering artefact, not recalled.

| Artefact | Identity | Verified |
|---|---|---|
| Minecraft 1.16.5 client | `sha1 37fd3c903861eeff3bc24b71eed48f828b5269c8` | matches Mojang `version_manifest_v2` → `1.16.5.json` → `downloads.client.sha1` |
| Local capture client jar | `/home/sagemaker-user/mineocclude-client/versions/1.16.5/1.16.5.jar` | **same sha1** — the jar the apparatus actually renders with |
| Official Mojang mappings | `sha1 374c6b789574afbdc901371207155661e0509e17` | matches `downloads.client_mappings.sha1` |

Mappings resolve `net.minecraft.client.model.SheepFurModel -> dvm` and
`net.minecraft.client.model.QuadrupedModel -> dvi`. The wool layer is the magenta
surface the frozen detector responds to, so `dvm` — not the collision box — is the
correct geometric object.

Constants below are transcribed from
`javap -p -c dvm.class` / `dvi.class` under the pinned JDK.

## Model definition (units are 1/16 block)

`SheepFurModel()` — cuboid `(origin, size, dilation)` and pivot:

| Part | Cuboid origin | Size | Dilation | Pivot |
|---|---|---|---|---|
| head | `(-3, -4, -4)` | `(6, 6, 6)` | `0.6` | `(0, 6, -8)` |
| body | `(-4, -10, -7)` | `(8, 16, 6)` | `1.75` | `(0, 5, 2)` |
| leg ×4 | `(-2, 0, -2)` | `(4, 6, 4)` | `0.5` | `(±3, 12, 7)` and `(±3, 12, -5)` |

`QuadrupedModel.setupAnim` (`dvi`) fixes the animation degrees of freedom:

- `body.xRot = 1.5707964` — a **constant** π/2, not animated.
- `leg.xRot = cos(limbSwing · 0.6662 [+π]) · 1.4 · limbSwingAmount`.
- `head.yRot = netHeadYaw · 0.017453292`.

## Bounding over all animation states

The extent must hold for every frame, so each animated part is bounded over its
whole reachable set rather than evaluated at one pose.

**Body** — rotation is the fixed π/2, so `y' = -z`, `z' = y` exactly. Dilated cuboid
`x ∈ [-5.75, 5.75]`, `y ∈ [-11.75, 7.75]`, `z ∈ [-8.75, 0.75]` maps, after rotation
and pivot `(0, 5, 2)`, to `x ∈ [-5.75, 5.75]`, `y ∈ [4.25, 13.75]`,
`z ∈ [-9.75, 9.75]`.

**Head** — `netHeadYaw` is a free rotation about Y. Rather than assume a clamp, the
head is bounded by its full rotational radius in the xz plane about its own pivot:
`√(3.6² + 4.6²) = 5.841233`. With pivot `z = -8` this reaches `z ∈ [-13.841233, -2.158767]`
and `|x| ≤ 5.841233`. This is valid for *any* head yaw, including 180°.

**Legs** — `limbSwingAmount ≤ 1`, so `|xRot| ≤ 1.4` rad. Maximising
`z' = y·sin θ + z·cos θ` over the dilated cuboid corners
(`y ∈ [-0.5, 6.5]`, `z ∈ [-2.5, 2.5]`) and `θ ∈ [-1.4, 1.4]`.

The maximum is attained at the corner `(y, z) = (6.5, 2.5)`. The stationary point
of `6.5·sin θ + 2.5·cos θ` is `θ* = atan2(6.5, 2.5) = 1.2036224929766774` rad, which
lies **strictly inside** `[-1.4, 1.4]`, so the constraint is inactive and the
maximum is the unconstrained amplitude in closed form:

```
|z'| ≤ √(6.5² + 2.5²) = √48.5 = 6.96419413859206
```

With the rear pivot `z = 7` this reaches `13.96419413859206`; laterally
`|x| ≤ 3 + 2.5 = 5.5`.

**Envelope** (entity-local, model units):

| Axis | Bound | Driven by |
|---|---|---|
| lateral `|x|` | `5.841233` | head rotational radius |
| longitudinal `|z|` | `7 + √48.5 = 13.96419413859206` | rear leg at full swing |

## The declared constant

The sheep's heading tracks its direction of travel, so model `z` maps to the world
travel axis. Rather than depend on the logged yaw — which is noisy and which the
truth predicate should not have to trust — the extent is declared **yaw-independent**:
the larger of the two bounds is applied to both horizontal world axes.

```
target_extent_horizontal_half_blocks = (7 + √48.5) / 16
                                     = 13.96419413859206 / 16
                                     = 0.8727621336620037
```

### Correction — superseded draft value

An earlier draft of this document declared `0.8727621026470629`, corresponding to a
longitudinal bound of `13.964193642353006`. That figure is `3.10×10⁻⁸` blocks
**below** the analytic supremum and could not be reproduced from the model
constants by any exact, float32, or grid evaluation of the maximisation; it is a
numerical artefact of the draft's evaluation of the leg-swing maximum, not a
different geometric claim.

Because the draft value sat *under* the true supremum, it did not satisfy this
document's own containment claim, and it erred in the same direction as the
`560bc01` false positive — declaring `EXTENT_FULLY_OCCLUDED` marginally too
readily. The declared constant is therefore the exact closed form above.

The correction is **strictly conservative**: it widens the extent, so it can only
widen the unscored `EXTENT_PARTIAL` band and shrink the scored classes. It cannot
manufacture stable samples. It was adopted for reproducibility and containment, not
for sample yield, and the prospective sample floor was confirmed to hold at both
values with identical per-row classifications on the frozen trajectory schedule.

The declared value is now reproducible in closed form from the jar constants alone,
and `tests/prospective/test_target_extent_derivation.py` recomputes it rather than
asserting a literal.

Vertical extent, from the same envelope (`model y ∈ [1.4, 18.5]`, mapped by the
renderer's `world_y = 1.501 − model_y/16`), spans approximately feet + `[0.345, 1.414]`.

### What kind of constant this is

It is an **upper bound**, not a fit. Every step maximises over the reachable set, so
the true rendered silhouette is contained in this box in every frame and at every
pose. That direction is deliberate: an over-large extent can only widen the unscored
`EXTENT_PARTIAL` band and shrink the scored classes, and the independent
`minimum_stable_samples_per_direction_per_class ≥ 60` floor is what polices
over-conservatism. An under-large extent, by contrast, would declare
`EXTENT_FULLY_OCCLUDED` while wool is still on screen — the exact false-positive mode
that failed at `560bc01`. The bound is therefore conservative in the only safe
direction.

No Stage-1 outcome, no detector output, and no observed error margin enters any line
of this derivation.

### Independent corroboration (not an input)

The historical detector-fitted effective half-extent was `w ≈ 0.6–0.8` blocks. This
derivation, which used no detector data at all, yields `0.8728` — just above the top
of that range, which is what a bound over *all* animation states should be relative to
an empirical average over observed poses. The two agree in the expected direction and
magnitude. This check was performed after the derivation was complete and did not set
any value in it.
