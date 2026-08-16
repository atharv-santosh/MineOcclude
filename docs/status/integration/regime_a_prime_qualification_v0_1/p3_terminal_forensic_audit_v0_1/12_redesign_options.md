# 12 — Minimum Scientifically Defensible Redesign

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY. No authority is created or frozen by this document.**
`REGIME_A_PRIME_COLLECTION_AUTHORIZED = NO`. `CONFIRMATORY_COLLECTION_AUTHORIZED = false`.
No confirmatory collection may be proposed until a new development condition is prospectively qualified.

## The demonstrated blocker, stated minimally
> P3's visibility gate requires ≥0.95 precision between a **point-visibility** predicate and an
> **area-visibility** predicate, pooled over frames that include the occlusion transition band. On this
> apparatus that band is ~1.04 blocks wide and is documented in a source the authority itself binds.
> The requirement is unsatisfiable in the tested range and satisfiable above it only through a base-rate
> artifact. Speed cannot fix it.

## What MUST remain unchanged to preserve continuity
- The frozen P3 outcome: all three candidates `FAIL_NOT_QUALIFIED`, terminal
  `BLOCKED_REQUIRES_NEW_PROSPECTIVE_AUTHORITY`, `selected_candidate = None`. **Not revisable.**
- P3 data classification: development-tier, `confirmatory_membership = false`,
  `permanently_excluded_from_confirmatory_a_prime = true` — all 150 captures and 12 calibrations.
- Fixed apparatus: camera `layout_01_fixed_v0.4`, eye (0.5, 5.62, −5.5), FOV 70°, 640×360 → 384×224,
  336 visual tokens, wall `layout_01_long_wall_v0.4`, 20 Hz lockstep, mod `febf31ca…`.
- The frozen magenta detector config (`99acc45e…`) — **unchanged**; it is not the defect.
- Layer-4-only extraction; BEST-K leading / FULL secondary; the P2-derived numeric thresholds
  (0.3320548468891168 ceiling, 0.4980822703336752 median headroom).
- Path/state gate at ε = 0 and paired NORMAL≡NO_WALL exactness.
- Stop-at-first-PASS ordered search; no reordering, no skipping, no post-outcome threshold changes.

## Options, ranked

### Option A — **Redefine the geometric predicate as a silhouette/bounding-box test** *(recommended)*
Replace the single centre-ray test with an occlusion test over the target's rendered extent: cast rays to the
bounding-box corners (or compute the projected AABB against the wall shadow) and label
`fully_occluded` / `partially_occluded` / `fully_visible`. Score the detector against `fully_visible` and
`fully_occluded` only; the partial band becomes an explicit, reported quantity rather than a source of FPs.

| criterion | assessment |
|---|---|
| Scientific defensibility | **Highest** — makes the two compared quantities actually the same quantity; the detector is an area predicate, so the geometry must be too |
| Likelihood of resolving blocker | **High** — directly removes the FP band; the residual disagreement becomes detector min-area only |
| Compute cost | Low (mod change + rebuild; no GPU) |
| New capture burden | 4 calibration runs + a small paired pilot per candidate; full 25-pair cohort only for the qualifying candidate |
| Implementation risk | **Medium** — requires a Fabric mod change, which invalidates the current runtime provenance hashes and demands fresh renderer-identity qualification |
| Goalpost risk | **Low** — this is a *correction of a mis-specified instrument*, decided before any neural outcome, on evidence that predates P3 (the v2.1 amendment) |

### Option B — **Keep the point predicate; restrict and rebalance the calibration scoring regime**
Score precision/recall only on frames in the **stable** regimes (outside `geometric_edge ± guard`), and report
the transition band separately against a prospectively frozen guard width. Add NO_WALL calibration runs so the
confusion matrix is not drawn from a single scene, and fix the calibration window in **world-x span** rather
than frame count so the class balance is speed-invariant.

| criterion | assessment |
|---|---|
| Scientific defensibility | **High** — honest about what the point predicate can and cannot certify; removes the base-rate confound (H2) |
| Likelihood of resolving blocker | **High** |
| Compute cost | **Lowest** — analysis/authority change only, no mod change |
| New capture burden | 4–8 calibration runs per candidate |
| Implementation risk | **Lowest** — preserves runtime provenance entirely |
| Goalpost risk | **Medium** — narrowing a gate after it failed needs a very clear prospective justification; mitigated by citing the pre-existing v2.1 amendment guard rule |

### Option C — **Fix the ≈3.3-tick render/state lag first, then re-run a corrected gate**
Cancel client-side entity interpolation during capture (or log the render-time entity position and pair frames
with it), re-measure the boundary, then re-derive a speed-aware hidden-onset rule.

| criterion | assessment |
|---|---|
| Scientific defensibility | **Highest for the wider programme** — this defect affects Regime A, P2 and P3 alike and is the deepest issue found |
| Likelihood of resolving **this** blocker | **Low on its own** — lag correction drives recall to 1.000 but leaves precision essentially unchanged (51→51, 35→34, 29→29 FPs). It must be combined with A or B |
| Compute cost | Low–medium |
| New capture burden | Re-qualification of the apparatus; potentially re-examination of P2 |
| Implementation risk | **High** — mod/client change, new renderer identity, and it puts P2's headline numbers back in question |
| Goalpost risk | Low |

### Option D — **Continue the speed sweep with a C04 at ≈3.75–4.0 b/s**
| criterion | assessment |
|---|---|
| Scientific defensibility | **Unacceptable** — modelled to pass **purely** by class-balance shift, with the detector↔geometry disagreement unchanged, while target-row contamination (already 0→1→7) would worsen. It would manufacture a PASS on an instrument artifact |
| Recommendation | **Do not pursue.** Recorded here only to document that it was considered and rejected on evidence |

## Minimum recommended redesign
**B + A, in that order, under one new prospective authority.**

1. **Immediately, no capture:** freeze a corrected visibility authority that (i) scores detector↔geometry
   agreement on **specificity / FP-rate on occluded rows** and recall, not base-rate-sensitive pooled
   precision; (ii) restricts scoring to the stable-visible and stable-hidden regimes with a prospectively frozen
   guard; (iii) fixes the calibration window in world-x span, not frame count; (iv) adds NO_WALL calibration;
   (v) makes the hidden-onset rule **speed-aware** (`edge + w + lag·v + safety`) instead of the hardcoded
   `HIDDEN_BOUNDS`; (vi) carries an explicit **feasibility derivation** for every threshold against the bound
   apparatus evidence. Also: commit and hash-bind the controller, and give development cohorts their own
   `run_id` namespace.
2. **Then, one small prospective development condition** at the *already-qualified* headroom point — **v = 2.0
   b/s, the C01 setting**, since headroom passed there with margin — re-run calibration + a paired cohort under
   the corrected gate. Speed stays fixed; the gate definition is what is being qualified.
3. **Only if that qualifies**, consider Option A / Option C as a follow-on apparatus improvement, and only then
   proceed toward P4.

`NEW_CAPTURE_REQUIRED = true` (calibration + one development cohort).
`NEW_PROSPECTIVE_AUTHORITY_REQUIRED = true`.
