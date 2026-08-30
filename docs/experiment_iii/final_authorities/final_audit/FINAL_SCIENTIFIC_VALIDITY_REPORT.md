# Final scientific validity report

Every claim below was reconstructed from source, git objects or formulas — not read back.

## III-A — graded partial observability

Fresh 25-identity cohort (13 LTR / 12 RTL), five identity-disjoint outer folds, four inner
rotations, two permanently excluded pilots. **Twelve** admission gates, gate 12 (all-`q`) evaluated
**before** materialization and freeze, with a frozen 200/direction candidate bound. Targets are the
first 19 consecutive counterfactually `EXTENT_FULLY_OCCLUDED` rows, identical across `L0`–`L4`;
selection is material-independent and never reads a rendered frame, a magenta detection or an RVE
score. FIR labels use the recovered 9-tap direction kernels, **fsum-normalized** — verified to
reproduce the frozen `H`, `S(τ)`, `gbar` and `c_direction` tables to exactly `0.0`. Context age
`a = 1…19` with a 16-pair window. Primary statistics: three identity-level estimands, one-sided
repeated-measures tests, Holm across 3, two-sided 95% identity bootstrap. No overall success gate.

`III_A_SCIENTIFIC_VALIDITY = PASS`. The Bayesian module changed no III-A scientific value.

## III-B — posterior uncertainty

`q ∈ {0.0125, 0.05, 0.2}` with a technical-only `0.15` fallback, `L4`/stone, same 25 identities,
no new P0. The oracle is **generator-matched**, not fitted: live source confirms
`std = sqrt(q·dt)`, `z` independent of `q`, and `x[t+1] = x[t] + s·v·dt + η` before clamp; the
posterior variance `σ²_τ = q·dt·Σ H(m)²` follows analytically. Matched-τ, different-`q` cells carry
objectively different posterior spread with `σ(q_high)/σ(q_low) = 4.0` at every τ — verified.

U2-S1 (matched-τ contrast) is protected by a within-identity `q`-permutation null. U2-S2 conditions
on **τ × direction**, closing a real false-positive pathway: an optimal zero-`q`-sensitivity decoder
reaches `ρ|τ = +0.11` with a bootstrap CI excluding zero, and collapses under the repaired
conditioning. U2-S3 is the three-`q` monotone dose response. U3 is hierarchical on U2 and its
slope-difference statistic cannot be produced by any additive clock-plus-`q`-category model.
Calibration uses **raw** `σ̂` for U2/U3, scale and monotonicity, and `σ̃ = max(σ̂, 1e-4)` only for
probabilistic uses, with `fraction_clipped` always reported.

`III_B_SCIENTIFIC_VALIDITY = PASS`.

## Guaranteed scientific value

Every outcome is publishable without redesign: III-A graded degradation, abrupt collapse, temporal
help or none, context effect or none, pixel-vs-MineWorld either way, and an L0 control failure;
III-B U2 positive or null, U3 positive or null, clock substitution, `q`-category-only, μ/σ
dissociation, calibrated or uncalibrated spread, boundary collapse, and `CLEAN_SKIP`. The
seven-rung belief-state ladder bounds every claim; only rung 4 licenses "calibrated Gaussian belief
state", and **no** rung licenses "the model performs Bayesian inference" or "the model uses
uncertainty" — those need U4/causal evidence this program does not collect.

`GUARANTEED_SCIENTIFIC_VALUE = PASS`  ·  `CLAIMS_BOUNDED = PASS`
