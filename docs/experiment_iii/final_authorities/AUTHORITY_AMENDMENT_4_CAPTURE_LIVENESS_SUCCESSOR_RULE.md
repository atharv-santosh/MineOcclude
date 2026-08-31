# Authority Amendment 4 (v1.7) — capture liveness successor rule

    AMENDMENT                        = 4
    NAME                             = Capture liveness successor rule
    AUTHORITY_VERSION                = v1.7
    AUTHORITY_SHA256                 = c773d9620e7fde9e72682d24a7515157522064e8c23b7096780a2995b926985a
    MACHINE_AUTHORITY_SHA256         = d529523c7e69653fcd47d65ef93a16bf9b4682c26db38688cec6af89e9f52c07
    PREDECESSOR_AUTHORITY_VERSION    = v1.6
    PREDECESSOR_AUTHORITY_SHA256     = 62519701bbe08f94839b6dab4e612826f902f31c736727e8c268cf738897ab4c
    PREDECESSOR_FREEZE_COMMIT        = a1f5dd1a959ff477edbf469cd12bb4db606371ea
    DISCOVERY_STAGE                  = A4_ENTRY_PRE_P0_ON_QUALIFIED_CAPTURE_HOST
    PROSPECTIVE                      = true
    P0_FRAMES_OBSERVED               = 0
    SCIENTIFIC_OUTCOMES_BEFORE       = none
    SCIENTIFIC_INVALIDATION          = none

## 1. Purpose

Renderer liveness must be established **independently of the scientific visibility
condition being measured**.

A scientific P0 condition MUST NOT be required to demonstrate framebuffer
inequality merely because the target changes `PRESENT`/`ABSENT` state, because a
correctly rendered condition may physically occlude the target such that
`TARGET_PRESENT` and `TARGET_ABSENT` produce pixel-identical settled framebuffers.
Framebuffer equality in such a condition is therefore not, by itself, evidence of
a stale renderer.

## 2. The defect this resolves

Amendment 3 §7.10f required the framebuffer to demonstrate a transition "at every
point where the image *must* change" and listed the target present/absent
transitions among those points. The same section also stated, as the reason the
v1.5 byte-duplicate rule was withdrawn, that an opaque condition "can legitimately
render pixel-identical frames while a fully hidden target moves". For an occluding
condition those two statements are in tension, and §7.10f never said which
transition then discharges the mandatory pre-capture probe.

This was not a corner case. §7.2 freezes the nine placements at world-x
`-2.0 … +2.0` and the as-built wall spans `x ∈ [-3, 4]`, so the camera-to-target
ray crosses the wall slab at **every** placement:

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

Measured on the qualified WSL2 capture host at `lane_x = 0.0`, with an opaque
stone wall, the present and absent settled framebuffers were byte-identical
(`3998b1cd…`), while `L0` on the same client process differed
(`80d8af15…` vs `11770cbe…`). The renderer was demonstrably live; the target was
simply hidden. Under v1.6 all **18** `L4` units (9 placements × 2 ABBA blocks)
refused with `CAPTURE_STALE_FRAME` on physically correct observations.

## 3. Mandatory pre-capture liveness witness

Before each authority-required scientific capture unit, execute a fixed,
`ENGINEERING_ONLY` liveness witness whose visual change is guaranteed
independently of candidate wall material and of P0 visibility. The witness uses
one prospectively frozen configuration common to every P0 unit:

| | |
|---|---|
| Scene | `NO_WALL` |
| Target | fixed authority-bound visible calibration position |
| Transition | `TARGET_PRESENT` → `TARGET_ABSENT` → `TARGET_PRESENT` |

The witness must establish:

1. server/client tick evidence advances correctly;
2. the requested transition is acknowledged;
3. the settled framebuffer changes across transitions whose visual effect is
   independently guaranteed;
4. `client_tick.jsonl` validates;
5. `capture_complete.json` validates;
6. `drained = true`;
7. `writer_errors = 0`;
8. actual framebuffer dimensions validate.

Failure of this witness produces `CAPTURE_STALE_FRAME`, or the corresponding
frozen technical blocker.

## 4. Scientific-unit present/absent transitions

For the subsequent scientific P0 unit, `TARGET_PRESENT_TO_ABSENT` and
`TARGET_ABSENT_TO_PRESENT` framebuffer hashes remain recorded, and their equality
or inequality remains useful technical evidence and diagnostics. However:

```
PIXEL_INEQUALITY IS NOT A SCIENTIFIC-UNIT VALIDITY REQUIREMENT
```

unless the controlling authority independently guarantees that the particular
transition must visibly alter the framebuffer. Therefore equal settled hashes are
**not**, by themselves, `CAPTURE_STALE_FRAME`.

This applies **uniformly to all scientific conditions**. There is **no**
material-specific exemption, **no** special-case rule for `L4`, and **no**
inference from material identity, expected opacity, candidate ranking, RVE, the
selected ladder or model behaviour when deciding whether renderer liveness has
been satisfied.

## 5. Separation from scientific evidence

Mandatory liveness-witness artifacts are `ENGINEERING_ONLY` and MUST be excluded
from: P0 RVE computation, material validity, ladder selection, the bootstrap,
sentinel measurements, P1, P2 scientific artifact discovery, production, and every
scientific statistic. The witness proves apparatus liveness only; it does not
measure scientific visibility.

## 6. Failure semantics

`CAPTURE_STALE_FRAME` may be emitted when:

- the mandatory engineering liveness witness fails;
- tick evidence fails;
- capture completion evidence fails;
- framebuffer dimensions/evidence fail;
- or another authority-defined transition whose framebuffer change is
  independently guaranteed fails to change.

A scientific `PRESENT`/`ABSENT` transition with equal framebuffers MUST NOT, by
itself, emit `CAPTURE_STALE_FRAME`.

## 7. What this does not change

Nothing scientific moves. Unchanged: P0 placements; the material roster and frozen
exclusions; RVE and its aggregation and normalization; ladder zones, separations,
SNR and CV bounds; the deterministic selection rule and tie-break; `B = 10000`;
target geometry and scientific capture contents; the cohort, folds, target rows,
FIR kernels and q grid; and all downstream model analysis and statistics.

The amendment changes only the technical apparatus-liveness witness, so that
liveness is not conditional on the unknown visibility quantity P0 exists to
measure.

```
AMENDMENT_4_STATUS = PASS
BLOCKING_DEFECTS   = 0
```
