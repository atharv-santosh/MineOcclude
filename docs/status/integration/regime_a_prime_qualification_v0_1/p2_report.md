# Regime A' P2 matched no-wall diagnostic — status report (v0.2)

**Phase** P2 · **Classification** EXPLORATORY_MATCHED_DIAGNOSTIC
**Status** BLOCKED_APPARATUS_REVALIDATION · **Blocker** `RENDER_EQUIVALENCE_FAIL`
**P3_ALLOWED = false** · **REGIME_A_PRIME_COLLECTION_AUTHORIZED = NO**

The operator authorised the minimal `startspec` scene-gating repair. That repair
was **not applied**, because a prior gate — rendered-pixel equivalence — fails,
and its failure is independent of the patch. No P2 no-wall capture, activation,
or neural outcome exists.

## 1. Why the patch was not applied

GATE B was run **first**, before editing or building anything, because it is
cheap and patch-independent: it compares frames the previous session already
produced against hash-bound historical frames. It failed.

Rebuilding the server mod changes what the *server* does. The failure is in
what the *client* draws. No mod change can alter rendered pixels, so applying
and building the patch could not have unblocked P2. Running GATE B first avoided
a Gradle build, 25 captures, and all GPU extraction that could not have produced
comparable data.

**The `startspec` blocker is still real and the patch is still required** — but
only after rendering equivalence is restored.

## 2. GATE A — wall path replay: PASS (pre-existing, unchanged runtime)

`epsilon_path = 0.0`, `EXACT_EQUALITY_REQUIRED`, 260/260 coordinate frames
bit-identical for both directions, aggregate max coordinate difference exactly
`0.0`. The runtime is unchanged since that authority was frozen, so GATE A was
not re-run — there was nothing to invalidate it.

## 3. GATE B — rendered-pixel equivalence: **FAIL**

Historical frames **are** durably retrievable: 260 per trajectory, each carrying
a `local_sha256` in a durable receipt that is itself hash-bound to the P0/P1
authority. 18 frames were compared (9 per replay spec), selected by a
metadata-only rule fixed before any difference was inspected: first, middle and
last frame of each visibility class, covering clearly-visible, wall-transition
and fully-occluded conditions.

All 18 historical frames hash-verified. Results:

| quantity | value |
|---|---|
| decoded-pixel identical | **4 / 18** |
| max differing pixels in a frame | 5,588 of 230,400 |
| max abs channel difference | 205 (of 255) |
| magenta **area** changed | **11 / 18** |
| magenta **status** flipped | **2 / 18** |
| flips on a **frozen Regime A target row** | **1** |

These are not PNG encoder artifacts — the comparison is on decoded RGB arrays.

Both status flips run in the same dangerous direction, `not_detected → detected`
on frames the frozen authority records as `OCCLUDED_AGREEMENT`:

- `regime_a_v2_t01` frame 43 — **this is tau = 1, a frozen Regime A target row** —
  historical `not_detected`, rebuilt runtime `detected` (28 px)
- `regime_a_v2_t14` frame 166 — historical `not_detected`, rebuilt `detected` (43 px)

**Equivalence rule.** Exact pixel equality. The project has no authorised
rendering tolerance, and its own apparatus-equivalence precedent
(`d6_equivalence_receipt.json`) is exact: `bitwise_identical=true`,
`max_abs_diff=0.0`. No tolerance was invented after observing differences.

**Materiality.** The rebuilt runtime would rewrite the visibility ground truth on
a frozen target row, turning an occluded frame into one carrying rendered
evidence. The same pixels feed MineWorld, so P2 activations captured here would
not be comparable to the historical apparatus — which is the entire premise of a
matched diagnostic.

## 4. Root cause

Server-side motion is pure Java arithmetic over an immutable noise schedule, so
coordinates are bit-exact. Client-side rasterisation is software GL, and that
stack was rebuilt after the NVMe wipe:

- **current renderer**: Mesa 25.2.8-0ubuntu0.24.04.2, llvmpipe (LLVM 20.1.2), Xvfb 21.1.12
- **original renderer**: **UNKNOWN — never recorded**

The original run used bundled operator-tools DRI drivers
(`LIBGL_DRIVERS_PATH → operator-tools/root/usr/lib/x86_64-linux-gnu/dri`) that
were wiped with the NVMe. I searched local `$HOME` archives and the durable S3
`mineocclude` prefix; no operator-tools backup exists.

**Provenance gap worth recording independently:**
`mineocclude-capture-runtime-receipt.json` pins Java, Minecraft, Fabric, and mod
hashes but records **no renderer, Mesa, GL, DRI, or Xvfb identity at all**. The
apparatus that produced the historical pixels is therefore not reconstructible
from frozen authority. Any future capture authority should pin the GL stack.

## 5. Remedy options (operator decision)

1. **Restore a pixel-identical rendering stack** — recover or rebuild the original
   bundled Mesa/llvmpipe + Xvfb, then re-run GATE A and GATE B. Blocked today by
   the missing renderer provenance, so this needs the exact version identified
   from another source.
2. **Authorise a rendering-equivalence rule prospectively** — define, before any
   P2 outcome, a tolerance the current stack demonstrably satisfies. It must
   handle the detector-flip case, which a naive pixel tolerance would not.
3. **Redesign P2 onto one self-consistent apparatus** — capture both conditions on
   the current runtime. This would require recollecting the wall runs, which the
   current P2 authority forbids and which changes the matched-control design.

Option 3 should not be taken lightly: it discards the existing wall cohort as the
matched comparator.

## 6. What this does and does not mean

It is an **apparatus finding**, not a scientific one. Nothing here says anything
about whether the layer-4 readout can decode a visible sheep; that remains open.
Closed Regime A (`FAIL_NO_DEFENSIBLE_DECODING`) and P1 are untouched and
unreinterpreted.

It does, however, tighten one earlier inference: the previous session's bit-exact
coordinate replay was necessary but **not sufficient** to establish apparatus
equivalence. That gap is now measured rather than assumed, which is exactly what
GATE B existed to do.

The compound-contrast limitation still stands for any future P2 run: removing the
wall changes scene pixels as well as visibility.

## 7. State

Apparatus untouched: mod source `f2c7f47b…`, installed jar
`78b4da2453ecf74140c5963df4013746845845427c12872d919b7ca98f2c4dc6` — both
byte-identical to the frozen build. No patch applied, no Gradle build, no
capture, no GPU use.

All four frozen pre-outcome artifacts remain hash-identical to commit `6943e04`.
Validation: 25 PASS, 1 FAIL (`HISTORICAL_PIXEL_EQUIVALENCE` — the gate that
correctly stopped P2), 6 NOT_REACHED.
