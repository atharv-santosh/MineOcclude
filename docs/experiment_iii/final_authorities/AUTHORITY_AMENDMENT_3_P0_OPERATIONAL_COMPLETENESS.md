# Authority Amendment 3 (v1.6) — P0 operational completeness

**Status:** frozen
**Predecessor:** `v1.5` — `3d116d9713b2c7fa705a194023e271061f712d0693618abbd991efa45437d7fb`,
freeze commit `3fd66eddfce017078b6af2774a381077759b98a0`
**Discovery stage:** `A4` entry, pre-P0
**Date:** 2026-08-31

---

## 1. Why this amendment exists

`A4` could not execute under `v1.5`. Six controlling P0 rules named a value or a procedure and
then deferred it to a "Phase 1" freeze **that was never written**. Not one of them has a number
or an algorithm anywhere in the `v1.5` package, the Phase 0 adjudicated design, the preauthority
documents, or the implementation.

| # | Deferred item | What `v1.5` said | Where it bites |
|---|---|---|---|
| 3a | nine placement coordinates | "coordinates frozen by A1" | §7.2 — the campaign has nowhere to put the target |
| 3b | P0 bootstrap seed | "the Phase-1-frozen P0 bootstrap seed" | §7.5 — one of the nine ladder validity rules |
| 3c | `L0_noise_threshold_p` | "derived from the absent-frame split-half noise … frozen by A1" | §7.3 step 3 — the support mask, hence every `D` |
| 3d | background tolerance | `PHASE1_FROZEN_OUTSIDE_MASK_RESIDUAL_TOLERANCE` | §7.3 step 8, §7.5 — a validity rule |
| 3e | sentinel repeatability envelope | "the Phase-1-frozen repeatability envelope" | §7.9 — the production drift gate |
| 3f | framebuffer staleness tolerance | "beyond the frozen tolerance" | §3.3, §7.2 — block invalidation |

The A1 `p0_manifest.json` recorded `placements: 9` and no coordinates, confirming 3a was never
discharged.

Because at least 3c and 3d can move which pixels enter the support mask, and therefore which
materials qualify, filling them ad hoc during P0 would have been an outcome-adjacent choice made
with measurements in hand. §9.2 requires an amendment. This is that amendment.

## 2. Prospectivity

| Quantity at the moment of amendment | Value |
|---|---|
| P0 frames observed | **0** |
| MineWorld forwards observed | **0** |
| Production outcomes observed | **0** |
| Scientific outcomes existed before amendment | **false** |
| Cohort materialised before amendment | true (unchanged by this amendment) |

No binding below could have been chosen to favour a material or a result, because no
measurement of any material existed.

## 3. The six repairs

Full normative text is `EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md` §7.10 and §7.11.

### 3a Placements — frozen

The nine scripted Phase 0 calibration positions, on the frozen sheep lane `y = 4`, `z = 6`,
ascending world-x:

```
-2.0  -1.5  -1.0  -0.5  0.0  +0.5  +1.0  +1.5  +2.0
P0_PLACEMENTS_SHA256 = 5676aa3371fcc481f89c709d8be81e2b14932f550b94ce44a42b2617420a84b6
```

All nine lie strictly inside the verified counterfactually fully occluded lane interval
`[-3.49, 4.49]` (§4.5).

**Superseded.** An implementation-side derivation (endpoint-inclusive uniform partition of
`[-3.49, 4.49]`, digest `a3deb1df…`) was made at the previous checkpoint while the Phase 0
positions were not materialised in the authority. It captured no frame and is recorded as
**superseded engineering evidence**; it must not enter P2.

### 3b Bootstrap seed — derived, not picked

```
seed_bytes        = SHA256("MINEOCCLUDE_EXPERIMENT_III_P0_BOOTSTRAP_V1|" + PHASE0_DESIGN_SHA256)
P0_BOOTSTRAP_SEED = int.from_bytes(seed_bytes[:8], "big") & ((1 << 63) - 1)
                  = 1530570907966297797
```

It binds the **immutable Phase 0 design hash**, not the current authority hash, so it survives
every later operational amendment unchanged. `B = 10,000` is unchanged.

### 3c `L0_noise_threshold_p` — a tunable-free technical-noise envelope

Consumes **only** L0 absent frames at that placement. Deterministic balanced split-half by
ascending capture index; coordinate-wise medians; per-pixel squared residual; `max` over
replicate blocks; `max` over pixels; strict `>` comparison; `float64` throughout.

Its defining virtue is that it contains **no tunable constant at all** — no quantile, no
multiplier, no floor — so there is no dial to turn to make a material qualify. A degenerate mask
is `RVE_MASK_DEGENERATE`, a technical failure to be reported and retried under the identical
procedure, never grounds to relax the rule.

### 3d Background tolerance — noise-relative, not a raw constant

```
PASS iff  B(c,p,b) <= 4.0 * N_out(c,p,b)
```

where `B` is the outside-mask present/absent energy and `N_out` is the same outside-mask energy
between that cell's **own** split-half absent medians. Scale-normalised, so one rule is
meaningful at all nine placements. The reference is technical noise from the cell's own absent
frames, so the rule is candidate-independent by construction.

The ratio 4.0 is derived, not chosen by taste: the split-half reference compares medians of
`n/2` frames while the present/absent contrast compares medians of `n`, so the reference already
carries roughly twice the energy of the noise it bounds; 4.0 leaves about eightfold energy
headroom against false failure, while a real background change is orders of magnitude larger.

`N_out == 0` requires `B == 0` exactly, with no epsilon: with demonstrably zero renderer noise,
any outside-mask difference is a real scene change.

### 3e Sentinels — prospective selection, frozen derivation, later numbers

Selection is deterministic coverage — left, centre, right — of the nine frozen placements:
indices `0, 4, 8`, i.e. world-x `-2.0`, `0.0`, `+2.0`. It reads no measurement.

The envelope **formula** is frozen now; the **numbers** can only exist after P0 and are bound in
P2:

```
half = 2.0 * max( range_over_replicates , 0.15 * centre )
envelope = [ max(centre - half, 0.0) , centre + half ]
```

The floor reuses the already-frozen §7.5 replicate-CV bound so two exactly equal P0 replicates
cannot yield a zero-width envelope that every later batch fails.

### 3f Capture liveness contract — withdrawing an unsound rule

This is the only repair that changes a stated rule rather than filling a hole.

The withdrawn rule invalidated a block on byte-identical consecutive frames. P0 **deliberately
captures a static settled scene**, and an opaque `L4` production condition can legitimately
render pixel-identical frames while a fully hidden target moves. Under the withdrawn rule the
*correct* observation was indistinguishable from a frozen renderer: it would have invalidated
valid science while failing to detect the fault it was written for.

Liveness is now proven where it is observable — tick integrity, one accepted frame per expected
tick, process liveness, framebuffer validity, and **transition probes** at points where the image
must change (target present↔absent, material change, and a mandatory pre-capture probe).

```
CAPTURE_STALE_FRAME  iff  the server tick advanced across a known scene transition
                          AND the settled framebuffer is byte-identical across it
```

Repeated bytes inside one settled static state are **not** staleness. Frame hashes remain
recorded as diagnostics.

## 4. What is unchanged

The 12-candidate roster and the frozen exclusions; the RVE formula, aggregation and
normalization; the ladder validity zones, separations, SNR and CV bounds; the deterministic
selection rule and tie-break; `B = 10,000`; the cohort, folds, target rows, FIR kernels and `q`
grid; every statistic and analysis family.

```
III_A_SCIENTIFIC_DESIGN_CHANGED = false
III_B_SCIENTIFIC_DESIGN_CHANGED = false
AMENDMENT_3_STATUS              = PASS
BLOCKING_DEFECTS                = 0
```
