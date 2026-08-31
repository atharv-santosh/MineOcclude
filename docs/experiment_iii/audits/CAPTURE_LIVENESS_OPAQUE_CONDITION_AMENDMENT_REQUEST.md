# AUTHORITY_AMENDMENT_REQUIRED — the opaque `L4` anchor cannot satisfy the 7.10f transition probes

    RAISED_BY                  = capture-host qualification, WSL2 Ubuntu 26.04 (Xvfb + Mesa llvmpipe)
    CONTROLLING_AUTHORITY      = v1.6 (Amendment 3)
    AUTHORITY_SHA256           = 62519701bbe08f94839b6dab4e612826f902f31c736727e8c268cf738897ab4c
    AUTHORITY_FREEZE_COMMIT    = a1f5dd1a959ff477edbf469cd12bb4db606371ea
    STAGE                      = A4 (P0), pre-execution
    P0_EXECUTED                = false
    LIVE_P0_DATA_EXISTS        = false
    CLASSIFICATION             = capture scientific semantics (§36) — NOT improvised

## 1. Summary

The frozen apparatus geometry places an **opaque** `L4` wall between the camera and
the target at **every one of the nine frozen placements**. The target is therefore
fully hidden in both the `PRESENT` and `ABSENT` states, and the settled framebuffers
are byte-identical. Authority 7.10f, as implemented, requires the target-presence
transition probes to demonstrate a framebuffer change on *every* capture unit, so
each of the **18** `L4` units (9 placements × 2 ABBA blocks) raises
`CAPTURE_STALE_FRAME` on a **physically correct observation**.

This is not a renderer fault. The same client, seconds earlier and in the same
process, rendered a clearly different present/absent pair for `L0`.

## 2. The authority is internally in tension here

Authority 7.10f introduces the probes with an explicit precondition:

> **Transition probes.** *At every point where the image **must** change*, the
> framebuffer is required to demonstrate the transition after settling:
> - target present → absent, and absent → present;
> - a wall material change;
> - a mandatory controlled pre-capture liveness probe on every unit.

and the same section states, as the reason the v1.5 byte-duplicate rule was
withdrawn:

> an opaque production condition **can legitimately render pixel-identical frames
> while a fully hidden target moves**.

So the authority already recognises that a target toggle behind an opaque wall is
**not** a point where the image must change. What it does not do is say which
transition then discharges the *mandatory pre-capture liveness probe* for such a
unit, nor that the `TARGET_*` probes are to be waived there. The implementation
resolves the ambiguity in the only way it can without a rule — it demands the
change unconditionally — and that refuses the opaque anchor.

## 3. Evidence

### 3.1 Geometry — occlusion at every frozen placement

Camera eye `(0.5, 5.6200000048, -5.5)`; target lane `y = 4, z = 6`; as-built wall
`x ∈ [-3, 4]`, `y ∈ [4, 7]`, `z ∈ [2, 3]`. Ray from the eye to the target, sampled
at the wall's near and far faces:

| placement | x @ z=2 | x @ z=3 | y @ z=2 | y @ z=3 | inside wall slab |
|---|---|---|---|---|---|
| -2.0 | -1.130 | -1.348 | 4.563 | 4.423 | yes |
| -1.5 | -0.804 | -0.978 | 4.563 | 4.423 | yes |
| -1.0 | -0.478 | -0.609 | 4.563 | 4.423 | yes |
| -0.5 | -0.152 | -0.239 | 4.563 | 4.423 | yes |
|  0.0 |  0.174 |  0.130 | 4.563 | 4.423 | yes |
| +0.5 |  0.500 |  0.500 | 4.563 | 4.423 | yes |
| +1.0 |  0.826 |  0.870 | 4.563 | 4.423 | yes |
| +1.5 |  1.152 |  1.239 | 4.563 | 4.423 | yes |
| +2.0 |  1.478 |  1.609 | 4.563 | 4.423 | yes |

The nine placements (§7.2, world-x `-2.0 … +2.0`) all lie within the wall's
`x ∈ [-3, 4]` extent. Occlusion by an opaque wall is total at every placement.

### 3.2 Measured framebuffers (ENGINEERING_ONLY, `lane_x = 0.0`)

| condition | wall | state | settled frame sha256 (first 32) |
|---|---|---|---|
| `L4` | `minecraft:stone` | present | `3998b1cd2ef3cce30100c0ad12e66978` |
| `L4` | `minecraft:stone` | absent  | `3998b1cd2ef3cce30100c0ad12e66978` |
| `L0` | `minecraft:air`   | present | `80d8af15e7b1b84067296805bfc988ba` |
| `L0` | `minecraft:air`   | absent  | `11770cbee51ce542062cf460f967cd1a` |

`L4` present ≡ absent, byte for byte. `L0`, captured minutes earlier on the same
client process, differs — the renderer is demonstrably live.

Observed blocker:

```
CAPTURE_STALE_FRAME: the server tick advanced across
MANDATORY_PRE_CAPTURE_LIVENESS_PROBE but the settled framebuffer is
byte-identical (3998b1cd...); the renderer is not presenting the scene
```

## 4. Why this was not caught before execution

Every fixture exercising `verify_unit_liveness` supplies synthetic frames with
distinct `before`/`after` hashes. No static-validation test constructs the case of
a *legitimately unchanged* framebuffer across a target toggle, which is the exact
case the opaque anchor produces on every one of its units.

## 5. Blast radius

- **18 of 252** P0 capture units (`L4` × 9 placements × 2 blocks) cannot complete.
- `L4` is the **opaque anchor** of the ladder; `V_L4` is measured, not assumed
  (`V_L4_measured_not_forced_to_zero: true`), so it cannot simply be dropped.
- `L0` and the 12 translucent candidates are unaffected and qualified on this host.

## 6. What the amendment must decide (not decided here)

1. Which transition discharges `MANDATORY_PRE_CAPTURE_LIVENESS_PROBE` for a unit
   whose wall occludes the target — and whether that transition is permitted to
   perturb the arena before the unit's measured slots.
2. Whether `TARGET_PRESENT_TO_ABSENT` / `TARGET_ABSENT_TO_PRESENT` are required to
   demonstrate a pixel change for an occluding condition, or are recorded as
   diagnostics there.
3. If either is made conditional on the wall material, how that condition is
   declared **without** encoding a visibility judgement — visibility is the
   quantity P0 exists to measure, and Amendment 3 §1 classifies outcome-adjacent
   choices in the capture path as forbidden.

An implementation cannot choose among these without changing capture scientific
semantics, so no repair has been attempted. The capture host is otherwise
qualified and idle, and no P0 frame has been produced.
