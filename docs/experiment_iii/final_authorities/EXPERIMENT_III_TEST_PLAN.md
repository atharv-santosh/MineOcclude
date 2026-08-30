# MineOcclude Experiment III — Test Plan

**Binds to:** `EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md` (`AUTHORITY_SHA256`)
**Lifecycle stages:** Group A and Group B run at `A2`; Group C runs at `A5`.
**Test root:** `tests/experiment_iii/`
**Groups:** A, B, C are Part III-A; D and E are Part III-B (added by Phase 1 Amendment 1).
**Counts:** group A has **30** named checks, group B **13**, group D **33** — **76** named static/CPU checks in total.
**Stage binding:** groups A, B **and D** all run at `A2`. Group C runs at `A5`; group E at `B-PILOT`.
**A1 task gates:** `D.2`, `D.4` and `D.31` are *additionally* task-completion gates inside `A1`, because III-A qualification **gate 12** cannot be evaluated without them. They are run twice on purpose: once as an `A1` task gate, once as part of the `A2` suite of record.

---

## 0. Governing rules

1. **No test may be deleted, skipped, weakened, or marked `xfail` to make a stage pass.**
   A failing scientific fixture is a defect in the code, not in the fixture. Weakening one is
   `SOURCE_STATIC_TEST_FAILURE` and is treated as an attempt to bypass the authority.
2. **Group A must have zero skips.** Group B may skip only tests explicitly gated on an
   optional dependency, and each such skip must be named in `static_validation_receipt.json`.
3. **Every test records the source closure it ran against.** A closure change invalidates the
   receipt (`SOURCE_CLOSURE_DRIFT`).
4. **No production identity may be used to debug the implementation.** Group C runs only on
   `e3_p90` and `e3_p91`.
5. **Fixtures are frozen artifacts.** Every fixture used by a Group-A check is committed, hashed,
   and listed in `static_validation_receipt.json`. A fixture regenerated to match new behavior is
   a defect unless the authority changed first.
6. Tests must be deterministic. Any test that draws randomness seeds it explicitly.

---

## A. Static unit tests — Part III-A (CPU only, no Minecraft, no model)

Thirty named checks. Each is referenced by number throughout the authority.

### A.1 — Deterministic identity generation

Generate the cohort twice from the same `EXPERIMENT_III_MASTER_SALT`. Assert byte-identical
manifests: same identity IDs, seeds, directions, start positions, episode IDs, path hashes,
noise hashes, target indices, labels, folds, and priority ranks.
*Fails:* `COHORT_QUALIFICATION_INFEASIBLE`, non-determinism in generation order.

### A.2 — RNG stream stability

Assert that `numpy.random.default_rng(<frozen reference seed>).standard_normal(180)` reproduces
a committed reference digest. Also reproduce a frozen A-prime unit's `expected_path_sha256`
end-to-end from its `noise_seed`, `start_world_x`, `speed`, `q`, and direction.
*Rationale:* this exact reproduction was verified at authority construction under Python 3.14.6 /
NumPy 2.4.3 against an artifact generated on a different host. The fixture makes any future
stream change loud rather than silent.
*Fails:* `COHORT_RNG_STREAM_DRIFT`.

### A.3 — Deterministic path reproduction (iterative, drift-before-noise, not `cumsum`)

Assert the generator uses the **iterative** binary64 recurrence
`x[t] = clamp( (x[t-1] + signed_speed*dt) + noise[t] )`.

Two negative controls, both required:

1. **Vectorized substitution.** Compute `start + numpy.cumsum(increments)` on the same inputs and
   assert the two hashes **differ** on at least one committed fixture path.
2. **Operand order.** Compute `(x + noise) + drift` instead of `(x + drift) + noise` and assert
   the hashes **differ**. Assert that only the drift-first order reproduces the frozen A-prime
   hash `b5803943e515ea633cc4dd80ddeaf349db5cb99d11980febdc3f13d7f84a56b7`.
   *Rationale (Phase 1 Amendment 1, FIX-3):* binary64 addition is not associative. The two orders
   diverge by one ULP (`8.88e-16`) from tick 40 onward, which is invisible numerically but changes
   the path SHA-256 completely — and therefore silently breaks every frozen path binding.

*Fails:* silent replacement of the generator of record; `COHORT_QUALIFICATION_INFEASIBLE`.

### A.4 — Speed / `q` / `dt` correctness

Assert `speed = 2.0`, `q = 0.05`, `dt = 0.05` in every generated spec, and that the per-step
noise scale equals `sqrt(q*dt)`. Assert that no Experiment III code path reads
`src/mineocclude/regime_a.py:29` (`SPEED_BLOCKS_PER_SECOND = 1.5`). Assert a spec carrying
speed 1.5 is **rejected**.
*Fails:* `COHORT_SPEED_VIOLATION`.

### A.5 — Fold partition

Assert 25 identities, 13 LTR / 12 RTL, five outer folds of exactly five, direction counts
`[[3,2],[2,3],[3,2],[2,3],[3,2]]` in fold order, identity-disjoint folds, and deal order by
`(seed, identity_id)` within direction. Assert four inner rotations per outer fold, as equal as
arithmetically possible, deterministic under the frozen sort keys, and independent of any target
or feature value.
*Fails:* `COHORT_MATRIX_INCONSISTENT`, `FOLD_LEAKAGE_DETECTED`.

### A.6 — Within-identity target-variance gate

Assert every admitted identity has 19 labels with `std(labels, ddof=0) >= 0.10` blocks and
non-constant labels. Include a synthetic candidate with SD `0.09` and assert it is **rejected**
with that gate named as the first failure.
*Rationale:* this gate is new; the legacy generator has only the between-identity diversity gate.
*Fails:* `COHORT_QUALIFICATION_INFEASIBLE` misclassification.

### A.7 — Same target rows across all five conditions

For each identity, assert the 19 target model-frame indices and the 19 FIR labels are **byte
identical** across `L0`–`L4`. Include a negative control that mutates one condition's indices and
assert detection.
*Fails:* `TARGET_ROW_CONDITION_DIVERGENCE`.

### A.8 — Wall-coordinate invariance under material change

Assert the as-built wall cell set derived from `layout_01` is identical for
`minecraft:stone`, each of the twelve stained-glass candidates, and (as the empty case)
`minecraft:air`. Assert the derivation **computes** `floor`/`ceil` from the layout rather than
reading a hard-coded interval, by re-deriving under a perturbed layout and asserting the cells
move.
*Fails:* geometry accidentally coupled to material.

### A.9 — Exact wall registry ID receipt

Assert the wall receipt's `declared_block_id` equals the condition's frozen registry ID for all
five conditions, that an unsupported ID refuses the episode rather than defaulting to stone, and
that a single mismatched cell is detected.
*Fails:* `WALL_RECEIPT_MISMATCH`, `WALL_MATERIAL_MISMATCH`.

### A.10 — Counterfactual extent uses `present=True` for L0

Assert the counterfactual `WallGeometry` is constructed with `present=True` for **all five**
conditions. Include the negative control: build it with `present=False` and assert the L0 row
count of `EXTENT_FULLY_OCCLUDED` collapses to **zero**, demonstrating the failure mode this test
exists to prevent.
*Fails:* `FIR_COUNTERFACTUAL_PRESENCE_ERROR`.

### A.11 — Extent port equivalence

Using the frozen `layout_01` geometry and camera eye `(0.5, 5.6200000048, -5.5)`, assert:

- `TARGET_EXTENT_HALF_BLOCKS == 0.8727621336620037`, and that
  `derive_target_extent_half_blocks()` recomputes it from the model constants;
- `(7 + sqrt(48.5)) / 16` equals the same value;
- the as-built wall resolves to `wall_ortho=2.5`, `wall_axis_min=-3`, `wall_axis_max=4.0`,
  `wall_y_min=4.0`, `wall_y_max=7.0`, `half=0.5`;
- **all 475** A-prime `WALL` materialized target labels (from commit `f2bc2c8`) classify as
  `EXTENT_FULLY_OCCLUDED` — a 475/475 exact match;
- `segment_hits_wall` reproduces the mod's 63-sample march (`i in [1,64)`) with inclusive bounds.

*Rationale:* this is the strongest available independent check that the port is faithful.
*Fails:* `APRIME_PORT_SOURCE_UNAVAILABLE`, silent port drift.

### A.12 — FIR arithmetic and complete-history gate

Assert `normalized_kernel` rejects a kernel with fewer than two taps, any negative tap, or
non-positive mass; that it rescales with `math.fsum`; that a pure-delay kernel is refused; and
that `causal_fir_targets` raises when `t - len(taps) + 1 < 0`.

Assert the **kernel recovery**: reproduce 50/50 A-prime path hashes; solve per direction; assert
rank 9, all taps `>= -1e-9`, tap sum `1 ± 1e-9`, max absolute residual `<= 1e-12`, aggregate mode
lag `== 2`, positive support within `[0,8]`; and reproduce **950/950** materialized labels.
Assert the recovered taps equal the values frozen in the authority.
*Fails:* `FIR_KERNEL_RECOVERY_FAILED`, `FIR_INCOMPLETE_HISTORY`.

### A.13 — Context-age frame-identity verification

Build a synthetic 16-pair context for a target row at context age `a`. Assert from **explicit
frame identities** — not from a `tau` label or a bin name — that the last pre-occlusion frame is
present in the context for `a <= 15` and absent for `a >= 16`. Include a negative control that
substitutes a correct-shaped but wrong-identity frame and assert detection.
*Fails:* `TOKEN_CONTEXT_AGE_UNVERIFIED`.

### A.14 — RVE fixture

On a committed synthetic present/absent image pair with a known planted residual:

- assert sRGB→linear conversion matches the piecewise formula in float64 at the `0.04045` breakpoint
  and at 0, 128, 255;
- assert the coordinate-wise median over settled frames;
- assert masked squared-residual energy `D` equals an independently computed value;
- assert the split-half absent-frame noise `N` is deterministic under a fixed frame order;
- assert `E = max(D - N, 0)` clamps at zero;
- assert `RVE = E / E(L0)` and that `RVE(L0) == 1` exactly;
- assert the background gate fires when out-of-mask residual exceeds tolerance.

*Fails:* `RVE_BACKGROUND_TOLERANCE_EXCEEDED` misclassification, arithmetic drift.

### A.15 — Mask fixture, material selection, and P0 tie-break

Assert the L0-derived mask thresholds, unions across replicate blocks, and dilates by exactly
2 pixels; that the **same** mask object is used for every candidate (a per-candidate mask is a
hard failure); that an empty or implausible mask raises `RVE_MASK_DEGENERATE`.

On a synthetic RVE table, assert the deterministic triple search: all nine validity rules
evaluated per triple; minimization of squared distance to `(0.725, 0.425, 0.165)`; and the
lexicographic registry-ID tie-break resolving an exact distance tie. Assert `NO_VALID_LADDER` is
returned — not an approximate ladder — when no triple qualifies.
*Fails:* `RVE_MASK_DEGENERATE`, non-deterministic selection.

### A.16 — One-forward layer fixture

With a stubbed decoder, assert that a single teacher-forced call yields captures for layers
`4`, `10`, and `19`, and that exactly **one** forward occurred. Assert the hook manager
registered exactly 20 handles and that every callback fired.

**Prerequisite fixtures, run as part of A.16:**

- *token-slice numeric fixture* — `14 × 347 == 4858`, `15 × 347 == 5205`, `16 × 347 == 5552`;
  `PREVIOUS` python slice `[4858:5194]`, `CURRENT` `[5205:5541]`; excluded action ranges
  `5194–5204` and `5541–5551`.
- *`PREVIOUS` semantic frame fixture* — `spans[-2].pair_index == 14`,
  `spans[-2].visual_positions == tuple(range(4858,5194))`, and
  `spans[-2].identity.model_frame_idx == t-1`.
- *`CURRENT` semantic frame fixture* — `spans[-1].pair_index == 15`,
  `spans[-1].visual_positions == tuple(range(5205,5541))`, and
  `spans[-1].identity.model_frame_idx == t`.
- *coverage fixture* — the `FrameTokenMap` covers `range(5552)` exactly, with no duplicate or
  missing position, and selected visual positions are disjoint from every action position.

Include a negative control that returns a correctly shaped tensor from the **wrong** pair and
assert it is rejected — proving shape agreement alone is not accepted as evidence.
*Fails:* `HOOK_REGISTRATION_INCOMPLETE`, `HOOK_LAYER_MISSING`, `TOKEN_SPAN_MISMATCH`,
`TOKEN_FRAME_IDENTITY_MISMATCH`, `TOKEN_ACTION_CONTAMINATION`, `EXTRACTION_FORWARD_COUNT_EXCESS`.

### A.17 — Tensor shape

Assert every persisted array is exactly `[19, 336, 2048]`. Assert a `[19, 2048, 336]` array is
rejected.
*Fails:* `TENSOR_SHAPE_MISMATCH`.

### A.18 — Tensor byte count

Assert `336 * 2048 * 2 == 1,376,256` and `19 * 1,376,256 + 128 == 26,148,992`. Write a real
`[19,336,2048]` float16 `.npy` and assert its on-disk size is exactly `26,148,992` bytes and its
dtype string is `<f2` (little-endian). Assert a native-endian or `>f2` write is rejected.
*Fails:* `TENSOR_BYTE_SIZE_MISMATCH`, `TENSOR_DTYPE_MISMATCH`.

### A.19 — Historical-seed exclusion

Assert the exclusion set is materialized from actual historical manifests and that a candidate
whose seed appears in it is rejected with `COHORT_SEED_COLLISION` named as the first failure.
Assert the exclusion set's hash is recorded.
*Fails:* `COHORT_SEED_COLLISION`.

### A.20 — Coarse pooling exactness

Build a synthetic `[14, 24, 2048]` grid in which each token's vector encodes its `(row, col)`.
Pool with `COARSE_2X6_CONCAT` and compare **byte for byte** against an independently derived
expected `[12, 2048]` matrix, then against its 24,576-length concatenation. Assert each cell
averages exactly 28 tokens, that the 12 cells are non-overlapping and exhaustive, and that the
concatenation is row-major over cells.
*Fails:* `FEATURE_DIMENSION_MISMATCH`.

### A.21 — Coarse pooling grid orientation

Using the same identity-encoding fixture, assert the pooling reads the grid as **14 rows × 24
columns** (7 rows and 4 columns per cell), not 24 × 14. Include the negative control: pool a
transposed grid and assert the result **differs**, proving the test discriminates.
*Rationale:* a transposed grid produces plausible-looking but wrong features, undetectable
downstream.
*Fails:* `FEATURE_POOLING_GRID_TRANSPOSED`.

### A.22 — Temporal subtraction

Assert `CURRENT_MINUS_PREVIOUS == coarse(CURRENT) - coarse(PREVIOUS)` exactly, at dimension
24,576, and that the sign is not inverted (a fixture with known `PREVIOUS < CURRENT` yields a
positive difference).
*Fails:* `FEATURE_SLICE_SWAPPED`.

### A.23 — Temporal concatenation order

Assert `TWO_FRAME_CONCAT` has dimension 49,152, that its first 24,576 entries equal
`coarse(PREVIOUS)` and its last 24,576 equal `coarse(CURRENT)`. Include the negative control with
the halves swapped and assert detection.
*Fails:* `FEATURE_SLICE_SWAPPED`.

### A.24 — Pixel baseline dimension

Assert `48 * 28 * 3 == 4,032`; that the resize uses the frozen area interpolation
deterministically (same input → same bytes); that the source is the raw RGB capture PNG, not a
model-normalized tensor; and that flattening order is stable.
*Fails:* `FEATURE_DIMENSION_MISMATCH`, `BASELINE_FORMULA_MISMATCH`.

### A.25 — Fold leakage

Assert no identity appears in its own outer training set; that every scaler, alpha, baseline
coefficient, training mean, and time-only coefficient is fit on outer/inner training identities
only; that alpha selection never touches a held-out identity; and that no held-out target value
influences any fitted quantity. Include a deliberately leaking configuration and assert
detection.
*Fails:* `FOLD_LEAKAGE_DETECTED`, `BASELINE_LEAKAGE`, `PREDICTION_ALPHA_SELECTED_ON_HELDOUT`.

### A.26 — Bootstrap identity resampling

Assert `B == 10,000` exactly; that resampling draws **whole identities** with all five
conditions, all 19 rows, all predictions, and all representations kept together; that the seed
comes from the freeze package; and that the same seed reproduces the same interval. Include a
row-resampling implementation and assert it is rejected.
*Fails:* `STATS_BOOTSTRAP_UNIT_VIOLATION`, `STATS_SEED_MISMATCH`.

### A.27 — Prediction locking order

Assert `PREDICTION_LOCK.json` is written and hashed before any statistics file exists; that every
`(identity, condition, row, model)` cell has exactly one prediction; and that attempting to
compute a summary statistic before the lock raises `PREDICTION_LOCK_MISSING`. Assert that
modifying a feature block after the lock is detected as a lock invalidation rather than silently
accepted.
*Fails:* `PREDICTION_LOCK_AFTER_STATISTICS`, `PREDICTION_DUPLICATE_CELL`.

### A.28 — Corrupted artifact rejection

Truncate, bit-flip, and zero-pad a persisted `.npy`; inject a NaN and an infinity; and assert each
is rejected by shape, byte-size, finiteness, or SHA-256. Assert a JSONL artifact with a missing
required field is rejected rather than silently defaulted.
*Fails:* `TENSOR_HASH_MISMATCH`, `TENSOR_NONFINITE`, `TENSOR_BYTE_SIZE_MISMATCH`.

### A.29 — Same-spec resume

Simulate a crash mid-stage. Assert that resume skips units already `COMPLETE` without reading
their bytes; re-seals `DURABLE` units; re-validates `EXTRACTED` units rather than re-extracting;
and that a unit whose recorded source-capture hash or extraction-spec hash no longer matches is
**discarded and re-planned**, never silently reused.
*Fails:* `EXTRACTION_SOURCE_CAPTURE_DRIFT`, `EXTRACTION_SPEC_DRIFT`.

### A.30 — Authority and hash drift rejection

Assert every artifact records its `AUTHORITY_SHA256` and source closure; that an artifact bound to
a superseded authority is rejected; that a manifest whose recorded hash does not match its bytes
is rejected; and that the namespace guard refuses a write to any path owned by Regime A, Regime
A-prime, or Experiment II.
*Fails:* `PROVENANCE_AUTHORITY_DRIFT`, `PROVENANCE_NAMESPACE_VIOLATION`.

---

## B. CPU integration tests — Part III-A (complete manifests, synthetic fixtures, no GPU, no model)

**B.1 — Cohort end to end.** Generate the full 25 + 2 cohort from the frozen salt, run all
**twelve** qualification gates of authority §2.4 — including **gate 12**, all-`q` prospective
qualification, evaluated **before** materialization and freeze — build folds and priority order,
and assert every artifact of authority §2.7 exists, hashes, and is internally consistent.
Assert `cohort_all_q_qualification_receipt.json` records, per candidate index, the first failing
gate **at each frozen `q`**. Assert the candidate scan honours the frozen index bound of 200 per
direction and that exhausting it raises `COHORT_ALL_Q_QUALIFICATION_INFEASIBLE` rather than
admitting an unqualified candidate.

**B.2 — Target manifest end to end.** From the cohort, materialize 19 target indices and labels
per identity via the ported extent engine and the recovered kernels; assert they are identical
across all five conditions and satisfy `t >= 8`.

**B.3 — Capture schedule end to end.** Generate the frozen Latin capture order and assert: 125
units; each condition once per block and once per period; identity order ascending
`priority_rank` within a condition block; exactly 25 condition batches; sentinel checks placed at
every batch boundary.

**B.4 — Synthetic extraction pipeline.** With a stubbed decoder returning deterministic
`[1,5552,2048]` tensors, run extraction for one synthetic capture and assert 19 forwards, 6
arrays, correct shapes, dtypes, byte sizes, hashes, and full provenance binding.

**B.5 — Feature pipeline end to end.** From synthetic activations, build all three
representations plus the pixel baseline and assert dimensions 24,576 / 24,576 / 49,152 / 4,032,
row order matching the frozen target-row order, and finite values throughout.

**B.6 — Analysis pipeline end to end.** On synthetic locked predictions with a **planted, known**
condition response, assert the three primary estimands recover the planted values; that Holm is
applied across exactly 3 (primary) and exactly 2 (temporal); that intervals reproduce under the
same seed; and that no overall success gate is emitted anywhere in the output.

**B.7 — Attrition branches.** Construct synthetic cohorts with `N_complete` of 25, 20, 15, and 14
and assert the correct attrition branch is selected, that the 14 case yields **no graded
inferential claim**, and that no imputation, condition dropping, or identity replacement occurs
in any branch.

**B.8 — Deadline fallback selection.** Assert each plan is selected from time and status alone;
that plan selection never reads a scientific outcome; that the reduced plans use the first N by
`identity_priority_order`; and that a plan, once selected, is frozen.

**B.9 — Status document.** Assert the emitted status document validates against
`LIVE_STATUS_CONTRACT.json`, that `CURRENT_BLOCKER` is always a taxonomy code or null, that
`COMPLETED_UNITS + REMAINING_UNITS == TOTAL_UNITS`, and that no scientific outcome field appears.

**B.10 — Artifact inventory completeness.** For each lifecycle stage, assert that removing any
artifact marked `required_before_next_stage` causes the stage-exit check to fail with that
artifact's named `missing_blocker`.

**B.11 — Adjudication coverage.** Assert every one of the 17 outcome rows has permitted and
prohibited interpretations, and that a synthetic claim outside every permitted interpretation is
rejected with `ANALYSIS_CLAIM_OUT_OF_SCOPE`.

**B.12 — Combined-program storage preflight.** Assert `A3` resolves the device/volume id of
every gated path; that `POOL_WORKING`, `POOL_DURABLE` and `POOL_SCRATCH` sharing one device id
are counted as **one** pool and their free bytes counted **once**; that free space is read as
**bytes** and compared against the frozen **binary GiB** thresholds
(`64 GiB` with a local mirror, `40 GiB` without — unchanged; the mandatory III-A gate is **not**
raised to protect optional III-B); that the **combined-program** gate is used
because III-B is prospectively authorized; that a `REMOTE_OBJECT_STORE` durable mode imposes no
local free-space gate but still requires a hashed round trip; and that the durability mode and
whether a local mirror is enabled are both recorded. Feed it a synthetic host where durable and
scratch share a device and assert `STORAGE_POOL_DOUBLE_COUNTED`. Feed it a host with
`63.9 GiB` free under a local mirror and assert `STORAGE_INSUFFICIENT` — the gate fails closed
and is never lowered to proceed.

**B.13 — Storage-gate coherence (the two gates must not contradict).** Assert the frozen
invariant, in binary GiB:

```
A3_PASS_GIB  -  MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB  >=  III_B_INCREMENTAL_LAUNCH_GATE_GIB
     64      -                48.796                   =   15.204   >=   15        OK

III_B_INCREMENTAL_LAUNCH_GATE_GIB  >  III_B_INCREMENTAL_EXPECTED_PEAK_GIB
               15                  >              10.508          margin 4.492 GiB
```

Simulate a host that passes `A3` at **exactly** the 64 GiB mirrored threshold, consume the
modelled III-A share, and assert the III-B launch gate can still **pass** — the defect this
test exists to prevent is a host that legitimately clears `A3` being forced into a spurious
`CLEAN_SKIP`. Assert that raising the launch gate above the structural headroom, or lowering it
below the III-B incremental peak, is **rejected**. Assert `MAX_III_A_STORAGE_SHARE` is derived
as *whole-program mirrored peak − III-B incremental mirrored peak*, not asserted.
*Fails:* `STORAGE_INSUFFICIENT`, `STORAGE_POOL_DOUBLE_COUNTED`.

Group-B skips are permitted only for tests gated on an optional dependency, and each must be
named in `static_validation_receipt.json`.

---

## C. P1 live tests — Part III-A (stage `A5`)

Run **only** on `e3_p90` and `e3_p91`. No production identity may be used to debug the
implementation.

Group C is exactly the §6A verification list of the authority, executed end to end, with each
item's **observed value** recorded in `p1_pilot_receipt.json`:

- **Apparatus and condition** — material switching across all five conditions; arena cache
  invalidation on every material change; exact block receipts; `L0` reaching scene `NO_WALL`;
  camera pose and lock; target identity, flags, and zero respawns.
- **Motion and labels** — path replay to `1e-9`; noise replay by hash; FIR labels reproduced from
  the frozen kernels; counterfactual target semantics identical across all five conditions; the
  same 19 target indices in all five; frame/action/tick lockstep at 180 frames.
- **Model path** — preprocessing identity; sequence construction; hook completeness; layers
  `{4,10,19}`; both slices numerically and semantically correct; token-position map equality;
  frame-identity verification for context age.
- **Storage** — shape, dtype, byte size, serialization, SHA-256, durable publish and read-back.
- **Analysis path** — feature building; 24,576 / 49,152 / 4,032 dimensions; analysis ingestion
  produces finite numbers.
- **Recovery** — a deliberate mid-run kill and restart resumes same-spec, skips completed verified
  units, and recomputes nothing already `DURABLE`.

**Expected counts:** 10 captures, 190 target rows, 190 forwards, 1,140 logical row tensors,
60 persisted arrays, 1,568,939,520 bytes.

**Pilot accuracy may be inspected only** to confirm the analysis code runs end to end and produces
finite numbers. It may never inform any scientific choice. P1 may not tune materials, RVE rules,
the cohort, the primary readout, the alpha grid, representations, estimands, thresholds, analysis
families, target rows, or folds.

---

## D. III-B static and CPU tests (stage `A2`; module III-B)

**Thirty-three** named checks, all executed at `A2` alongside groups A and B — CPU only, no
Minecraft, no model.

Three of them guard **III-A** and are therefore *also* `A1` task-completion gates, run before
`I02` materializes the cohort: **`D.2`** (bit-identity regression on the shared generator),
**`D.4`** (all-`q` qualification — III-A gate 12) and **`D.31`** (gate-12 ordering). A failure
in any of those three blocks III-A. A failure in any *other* group-D check is a III-B blocker
only: III-A closes unaffected and III-B proceeds toward `CLEAN_SKIP` if it cannot be repaired
in time.

### D.1 — Amendment hash binding
Assert the machine authority records the Phase 0 Amendment 1 Markdown and JSON SHA-256 values,
that both files exist, and that recomputing their hashes reproduces the recorded values.

### D.2 — q = 0.05 regression (**mandatory before `I02`**)

**Bound reference — reconstruct it from the git object database, nothing else.**

| Field | Value |
|---|---|
| commit | `f2bc2c8082e77f9c3f9e089f2fb1a20b11a052a8` *(the same commit that binds the v0.4 FIR recovery source)* |
| path | `docs/status/integration/regime_a_prime_qualification_v0_1/prospective_development_authority_v0_3/stage2_locked_manifest.json` |
| blob SHA-1 | `fb93a08ba2d71c28c9929469d9b34bf8fc6de17b` |
| bytes | 270,672 |
| manifest SHA-256 | `ad718685b33030a0c0de405cd9d3abb737c3f3e9d087ad7c78768fe151855eb8` |
| unit | `a2x_t01_wall` (the `a2x_t01_no_wall` twin shares the trajectory and the hash) |
| direction | `LEFT_TO_RIGHT` |
| seed = noise_seed | `2154560968567132226` |
| `start_world_x` | `-7.8` |
| speed | `2.0` blocks/s |
| `q` | `0.05` |
| frames | 180 |
| `expected_path_sha256` | `b5803943e515ea633cc4dd80ddeaf349db5cb99d11980febdc3f13d7f84a56b7` |

> **This manifest is `v0_3`, a different file from the `v0_4` manifest that carries the FIR
> recovery.** The reference hash is **not** present in `v0_4`. Both are bound at commit
> `f2bc2c8`. Retrieve with
> `git cat-file blob f2bc2c8082e77f9c3f9e089f2fb1a20b11a052a8:<path>` and verify the manifest
> SHA-256 before reading any field from it.

Assert the q-generalized generator at `q = 0.05`, seeded and started exactly as above,
reproduces **bit-identically**: the legacy inline path arithmetic; and that
`sha256(numpy.asarray(path, dtype='<f8').tobytes())` equals the bound `expected_path_sha256`.
Include two negative controls: perturb `q` by `1e-12` and assert the hash changes; and swap the
recurrence operand order to `(x + noise) + drift` and assert the hash changes to one beginning
`6713929a169500a0a80ad05c…` (see A.3, FIX-3).
*Rationale:* without this, a q-generalization defect could silently alter the **III-A** cohort
at the exact moment qualification gate 12 is evaluated. This is why the check is an `A1` task
gate on `IB03` and not merely a pre-P1 requirement.
*Fails:* `B_Q_PAIRING_MISMATCH`, `COHORT_ALL_Q_PRIMITIVE_MISSING`.

### D.3 — Innovation pairing
Assert `generate_noise_schedule(seed, n, q, dt).rows[i].standard_normal_draw` is identical for
`q ∈ {0.0125, 0.05, 0.2}` at a fixed seed, and that
`noise_draw == standard_normal_draw * sqrt(q*dt)` exactly. Assert the ratio between any two `q`
is exactly `sqrt(q_a/q_b)` at every tick.
*Fails:* `B_Q_PAIRING_MISMATCH`.

### D.4 — All-`q` qualification (III-A qualification **gate 12**)
Assert the `IB02` primitive evaluates authority §2.4 gates **1–11** at each frozen
`q ∈ {0.0125, 0.05, 0.2}` on that cell's **own** regenerated path, under the identical frozen
arithmetic and including the corrected lane-clamp gate.

Assert every admitted III-A identity in the materialized cohort qualifies at **all three**
frozen `q`. Include a synthetic candidate that qualifies at `q_mid` but not at `q_high` and
assert **gate 12 rejects it at admission**, not later. Assert the rejection is logged with its
first failing sub-gate **at each `q`**.

Assert the non-binding `q = 0.15` diagnostic column is recorded and that a `q = 0.15` failure
**never** rejects a candidate and **never** triggers cohort regeneration.
*Fails:* `COHORT_ALL_Q_QUALIFICATION_INFEASIBLE`.

### D.5 — Cross-`q` fold identity
Assert all `q` variants of one identity share that identity's outer fold **and** inner rotation;
that `q` appears nowhere in fold assignment; and that no identity appears in its own training set
across `q`. Include a deliberately leaking assignment and assert detection.
*Fails:* `B_CROSS_Q_FOLD_LEAKAGE`.

### D.6 — Oracle exactness (on **fsum-normalized** taps)
Assert the kernel taps are fsum-normalized at load — `normalized[k] = taps[k] / fsum(taps)`,
accumulated with `fsum` — **before** any `H(m)` or `S(τ)` is computed. Assert that the
**unnormalized** `LEFT_TO_RIGHT` taps (whose `fsum` is `0.9999999999`) reproduce `S(τ)` only to
`9.29e-10` and therefore **fail** this check, while the normalized taps reproduce it to `0.0`;
`RIGHT_TO_LEFT` taps already sum to exactly `1.0` and are unchanged. Then assert
`S(τ) = Σ_{m<τ} H(m)²` matches the frozen per-direction table to `1e-12` for τ = 0…19;
that `sigma_tau > 0` strictly for every τ in 1…19 at every `q`; that `mu_tau` uses the frozen
`gbar` offset; and that no oracle quantity reads an activation, a prediction, or a fitted
parameter.
*Fails:* `B_ORACLE_MISMATCH`.

### D.7 — Affine-form rejection and the direction-specific boundary (**the dangerous one**)

The affine reduction `sigma2 = q*dt*(tau + c_direction)` is exact only for `τ ≥ 8` and is
forbidden below it. Its sign change is **direction-specific**, because
`c_LTR = −4.355500526064508` and `c_RTL = −3.395856222446993`, so it flips at
`τ = −c_direction`: **4.3555** for `LEFT_TO_RIGHT` and **3.3959** for `RIGHT_TO_LEFT`.

| direction | affine **negative** for integer τ | affine **positive** for integer τ |
|---|---|---|
| `LEFT_TO_RIGHT` | `1 ≤ τ ≤ 4` | `τ ≥ 5` |
| `RIGHT_TO_LEFT` | `1 ≤ τ ≤ 3` | `τ ≥ 4` |

Assert **exactly** this boundary, per direction, against the frozen oracle constants:

1. For `LEFT_TO_RIGHT`, the affine expression is **strictly negative** at `τ = 1,2,3,4` and
   **strictly positive** at `τ = 5…19`.
2. For `RIGHT_TO_LEFT`, it is **strictly negative** at `τ = 1,2,3` and **strictly positive** at
   `τ = 4…19`. **`τ = 4` is positive in this direction** — a test that demanded negativity at
   `τ = 1…4` in *both* directions would fail a correct implementation, and is the defect this
   rewrite removes.
3. There is no integer `τ` at which the affine expression is exactly zero; assert that too.
4. Assert `affine_last_negative_tau == {LTR: 4, RTL: 3}` and
   `affine_first_positive_tau == {LTR: 5, RTL: 4}` as read from
   `III_B_ORACLE_SPECIFICATION.json`, and that the machine authority reproduces both verbatim.
5. Assert the **implementation** never evaluates the affine form below `τ = 8`, and that the
   exact cumulative-mass form it does evaluate returns a **strictly positive** `sigma2` at every
   `τ = 1…19` in both directions and at every `q`.
6. Assert the two forms agree to `1e-12` at every `τ ≥ 8`.

This is a boundary-exactness test, not a weakened one: it proves the affine form is negative
**exactly** where the frozen oracle says it is negative, and non-negative after the
direction-specific boundary.
*Fails:* `B_ORACLE_MISMATCH`.

### D.8 — Cross-`q` σ ratio
Assert `sigma(q_high, τ) / sigma(q_low, τ) == sqrt(q_high/q_low) = 4.0` to `1e-12` at **every**
τ, and likewise 2.0 for adjacent levels. Assert the ratio is τ-independent.

### D.9 — VIS6 definition
Assert the selector returns the **last 6 consecutive** model frames that are counterfactually
`EXTENT_FULLY_VISIBLE`, clamp-free, and have index ≥ 15. Assert a **pre-occlusion** window is
never returned. Assert that when fewer than 6 eligible consecutive rows exist, the selector
returns empty and records `B_VIS_UNAVAILABLE` **without** failing the cell.

### D.10 — VIS6 clamp-free requirement
Construct a path whose tail is pinned at the lane bound and assert the pinned rows are excluded.
Assert the returned rows have nonzero positional variance.
*Rationale:* a pinned sheep has no motion, voiding the position control and the q-perception
diagnostic.

### D.11 — U2 statistics, and the U2-S2 direction control
On synthetic locked predictions with a **planted** `q` effect, assert U2-S1 recovers the planted
matched-τ contrast; U2-S2 recovers the planted partial association after **τ × direction**
residualization; and U2-S3 recovers the planted ordering proportion. Assert τ matching is by
occlusion age, never by absolute frame index.

**The direction-confound negative control (mandatory).**

> *Corrected by repair pass 2.* The superseded fixture made `sigma_hat` a **pure function of
> direction** and demanded a positive τ-only U2-S2. That is false: the oracle's direction
> ordering **flips** with τ — LTR > RTL at τ ∈ {1,2}, RTL > LTR for τ ≥ 3 — so a decoder that is
> constant within direction largely cancels when pooled over τ = 1…15 and measures
> **ρ|τ = −0.067**. A correct implementation would have **failed** the old test. The confound is
> carried by the τ-by-direction **interaction**, not by direction alone.

**Frozen construction — zero `q` sensitivity, `(τ, direction)`-dependent:**

```
sigma_hat_fixture(identity, q, tau)
    := mean over q' in {0.0125, 0.05, 0.2} of sigma_oracle(direction(identity), q', tau)
```

It is a function of `(τ, direction)` only, and is **identical across `q`** at fixed
`(identity, τ)`. Build it on the frozen 13 LTR / 12 RTL split over `τ = 1…15`.

Assert, in this order:

1. **Zero `q` sensitivity, exactly.** For every `(identity, τ)` the fixture value is identical
   at `q_low`, `q_mid` and `q_high` — max across-`q` spread `== 0.0`. This assertion is exact;
   everything below is compared against ranges.
2. **The false-positive pathway exists.** Under **τ-only** residualization the partial
   association is **positive** and equals the frozen deterministic reference
   **`ρ|τ = +0.0905724833 ± 0.002`**, with the whole-identity bootstrap 95% CI lying
   **entirely above zero**. (The tolerance is small because the observed statistic carries
   **no randomness** — it covers only rank/BLAS ordering differences.)
3. **The τ × direction residual is degenerate, by construction.** The fixture is constant
   within every `(τ, direction)` cell, so `Var(r_hat) ≤ TOL` where
   `TOL = 1e-15 × Var(unresidualized rank vector)` (`1.05e-10` at the frozen 1,125-cell
   design). Assert the zero-variance branch **fires**.
4. **The frozen rule maps it deterministically.** Assert `rho == 0.0` **exactly** and the
   one-sided `p == 1.0` **exactly**, that `U2_S2_ZERO_VARIANCE_CASE` is set, and that every
   bootstrap replicate in the same case is **retained** with `rho* = 0.0`.
5. **No `NaN` anywhere.** Assert no `NaN` is produced, propagated or compared in the decision
   path. A test that would pass only because `NaN <= 0.05` evaluates `False` is a **defect**.
6. **No positive declaration.** The decision is `NOT SIGNIFICANT` and `U2_POSITIVE` is **not**
   declared on this fixture.

**Permitted stronger variant (`OPTIMAL_PROJECTION`).** `sigma_hat` := the `(τ, direction)` cell
mean of the τ-residualized oracle **rank** vector. Also zero-`q`-sensitivity; it attains the
worst case `ρ|τ ≈ +0.110` against a theoretical ceiling of `+0.114`, with a τ-only bootstrap
CI excluding zero. It is subject to the identical zero-variance branch under τ × direction.

Bootstrap interval endpoints are compared against ranges; the **observed** `ρ|τ`, the
zero-variance mapping (`rho = 0.0`, `p = 1.0`) and the zero-`q` assertion are **exact**.

Assert the nuisance structure is exactly **30 cells** (`τ = 1…15` × `{LTR, RTL}`); that ranking
happens **over the pooled set first** and residualization **second**; that a singleton cell
yields residual exactly `0.0` and is **retained**, not dropped; and that ranking and
residualization are recomputed **inside every bootstrap replicate**.
*Fails:* `B_TAU_ALIGNMENT_ERROR`, `B_U2_S2_CONDITIONING_MISMATCH`.

### D.12 — Within-identity permutation null
Assert the null permutes `q` labels **within** each identity only, holding τ, identity and fold
fixed; that `B = 9,999`; that the p-value is `(1 + #{perm ≥ obs}) / 10,000`; and that under a
synthetic no-effect dataset the p-value is approximately uniform.

### D.13 — Holm family sizes
Assert Holm is applied across exactly **3** U2 p-values (or exactly **2** under the frozen drop
`LEVEL_1`), and exactly **2** U3 p-values. Assert U3-S3, the calibration battery, the context
boundary secondary and the eight confound controls enter **no** family and are **never**
Holm-corrected. Assert adding or removing a statistic is rejected.
*Fails:* `B_U2_FAMILY_ALTERED`.

### D.14 — All eight confound controls present
Assert every one of the eight frozen controls is computed and reported: τ-only baseline, q-only
categorical baseline, analytic oracle reference, pixel baseline, permutation null, matched-τ
evaluation, U3 interaction, τ ≥ 16 boundary collapse. Assert a missing control fails the stage.

### D.15 — Wording gate
Assert that until the §23 controls pass, emitted language is
`Q_REGIME_RELEVANT_INFORMATION`; and only after they pass may it be
`UNCERTAINTY_RELEVANT_INFORMATION_TRACKING_ORACLE_POSTERIOR_SPREAD`. Assert
"calibrated belief state" is never emitted outside ladder rung 4.

### D.16 — U3 statistics
On synthetic data with a planted `q`-dependent slope, assert U3-S1 recovers per-identity slopes
and U3-S2 recovers the slope interaction. Assert U3-S3 is descriptive and enters no family.

### D.17 — U3 hierarchy
Assert U3 **scientific claims** are emitted only when U2 passes; when U2 does not pass, U3 is
computed and labelled descriptive.

### D.18 — Scale agreement
On synthetic `sigma_hat = a * sigma_oracle + b`, assert the recovered slope and intercept match
`a` and `b`, and that the strong criterion fires only when the slope CI contains 1 **and** the
intercept CI contains 0. Assert the regression runs on **raw** `sigma_hat` (no positivity
guard). Assert the emitted wording for a passing criterion is a **non-rejection** statement
("consistent with scale calibration; scale mismatch is not detected at this power") and that
any equivalence claim — "proven scale-calibrated", "equivalent to the oracle scale" — is
refused, since no equivalence test is run.

### D.19 — Conditional coverage gate
Assert coverage is computed **only** when the mean gate passes; when it fails, assert the output
is `NOT_INTERPRETABLE` and **not** a reported calibration failure.
*Fails:* `B_U3_ANALYSIS_FAIL`.

### D.20 — Hybrid NLL
Assert both NLL variants are computed; that the hybrid uses the frozen oracle-compatible mean;
that the hybrid is reported as primary; and that both are compared against the τ-only spread
baseline and the oracle spread ceiling.

### D.21 — Status schema
Assert the emitted status document validates against the extended contract, that `III_B_BLOCKER`
is a taxonomy code or null, and that `III_A_STATUS` is not a function of `III_B_STATUS`.

### D.22 — Outcome vocabulary
Assert `CLEAN_SKIP`, `TECHNICAL_FAIL` and `SCIENTIFIC_NULL` are distinguished, and that a
`SCIENTIFIC_NULL` is **never** emitted as a blocker.

### D.23 — Capture unit binding
Assert a III-B capture unit binds identity, condition `L4`, `q`, seed, direction, path hash,
noise hash, episode ID in 87001–87999, its **own** 19 target rows, its **own** VIS window, and
its inherited fold. Assert `capture_unit_id` is `{identity}__L4__q{q:.4f}`.

### D.24 — Array shapes and byte sizes
Assert occluded arrays are `[19,336,2048]` at exactly 26,148,992 bytes and VIS arrays are
`[6,336,2048]` at exactly 8,257,664 bytes, both little-endian float16, and that only L19 is
serialized.

### D.25 — Belief-state ladder coverage
Assert all seven rungs are defined, that exactly one is selected for any result pattern, and that
a claim outside the selected rung is rejected.

### D.26 — III-A independence (**the invariant test**)
Assert, mechanically: no III-A lifecycle state lists a `B-*` state in its entry conditions; no
III-A artifact has a III-B artifact as a prerequisite; no III-A estimand or fold references a
III-B cell; and III-A `A19` closure conditions make no reference to III-B. Simulate a total III-B
failure and assert III-A closure is unaffected.
*Fails:* `B_III_A_DEPENDENCY_DETECTED`.

### D.27 — Launch-gate inputs are outcome-independent
Assert the gate evaluator reads only time, technical stage receipts and resource measurements.
Feed it a scientific-outcome field and assert it is **refused**, not ignored. Assert the free
space requirement is `POOL_WORKING >= 15 GiB` in **bytes**, that `POOL_DURABLE >= 5 GiB` is
evaluated **only** when `POOL_DURABLE` is a distinct local filesystem and is otherwise recorded
`N/A`, and that the eight requirements are unchanged in count.

### D.28 — Two evaluations only
Assert the gate evaluates at 12:00, re-evaluates at most once at 17:00, and refuses a third
evaluation. Assert a Friday launch is refused.

### D.29 — Drop-level inputs
Assert the drop level is selected from time, technical completion and resources only. Feed it a
scientific outcome and assert refusal. Assert `LEVEL_3` orders identities by
`identity_priority_order`, never by observed performance.

### D.30 — Absolute stop
Assert that at 2026-09-03 20:00 local no new scientific execution may begin, that III-A closure
is never delayed for III-B, and that a `CLEAN_SKIP` leaves III-A closure conditions satisfied.

### D.31 — Gate-12 ordering and cohort-freeze precedence (**an `A1` task gate**)
Assert the **ordering**, not merely the content, of III-A qualification gate 12:

1. `I02` refuses to materialize a cohort when the `IB02` primitive or the `IB03` regression
   fixture is absent or failing, and raises `COHORT_ALL_Q_PRIMITIVE_MISSING`. It **fails
   closed**; it never materializes an ungated cohort and never defers the gate.
2. Gate 12 is evaluated **before** `production_identity_manifest.jsonl` is written and before
   its hash is taken. Assert no admitted identity was written prior to its gate-12 evaluation.
3. Gate 12 reads **no** rendered frame, activation, prediction, RVE score, MineWorld output or
   any other scientific outcome. Feed the evaluator each of those and assert refusal.
4. The materialized cohort is **byte-identical** whether or not any III-B stage subsequently
   runs. Materialize the cohort twice — once with every III-B runtime stage stubbed out as
   `CLEAN_SKIP`, once with them nominally available — and assert identical manifest hashes.
5. No III-A task depends on any III-B **runtime stage** artifact (`B-GEN`…`B-LOCK`); the only
   III-A dependency on III-B is `I02 → {IB02, IB03}`, both **implementation** tasks inside `A1`.
6. Cohort regeneration is refused once any capture exists, and is refused at all times when the
   trigger is any outcome.
*Fails:* `COHORT_ALL_Q_PRIMITIVE_MISSING`, `B_III_A_DEPENDENCY_DETECTED`.

### D.32 — Negative `sigma_hat` handling
Assert the frozen calibration positivity guard:

1. `EPS == 1e-4` blocks exactly, read from the authority, and
   `sigma_tilde = max(sigma_hat, EPS)`.
2. **U2-S1, U2-S2, U2-S3, U3-S1, U3-S2, U3-S3, calibration A (scale) and calibration B
   (monotonicity) use RAW `sigma_hat`.** Plant a dataset containing negative `sigma_hat` and
   assert every one of those statistics is numerically identical with and without the guard
   available — i.e. the guard never leaks into them.
3. Coverage, both NLL variants, any `log(sigma_hat)`, any Gaussian density score and any
   log-axis calibration plot use `sigma_tilde`.
4. `fraction_clipped`, `count_negative` and `min_sigma_hat` are reported for **every**
   calibration analysis that used `sigma_tilde`, overall and split by `q` and by `τ`.
5. The locked predictions store **raw** `sigma_hat`; clipping before prediction lock is refused.
6. Changing `EPS`, or the set of statistics the guard applies to, after prediction lock is
   refused.
7. When `fraction_clipped > 0.05` the affected results are labelled
   `POSITIVITY_GUARD_MATERIAL` and the fraction is emitted prominently — a disclosure, never a
   failure and never a reason to re-fit.
*Fails:* `B_CALIBRATION_POSITIVITY_RULE_ALTERED`.

### D.33 — Holm procedure executability
Assert the inferential procedure is algorithmic and that intervals and decisions are separate:

1. Every family member emits a **raw p-value** and a **Holm-adjusted p-value**, and
   significance is declared **only** from the adjusted p-value. Assert no output describes an
   interval as "Holm-adjusted"; assert that string is refused.
2. U2-S1's p-value is the within-identity permutation `(1 + #{perm ≥ obs}) / 10,000` with
   `B = 9,999`.
3. U2-S2, U2-S3, U3-S1 and U3-S2 p-values are the frozen one-sided bootstrap inversion
   `p = (1 + #{T*_b ≤ T_null}) / (B + 1)` with `B = 10,000`, `T_null = 0` except `1/6` for
   U2-S3. Assert `p ≥ 1/(B+1)` always and is never exactly 0.
4. On a planted no-effect dataset the inversion p-values are approximately uniform; on a planted
   strong effect they are at the floor.
5. Holm is the step-down `padj_(1) = min(1, m·p_(1))`,
   `padj_(k) = min(1, max(padj_(k−1), (m−k+1)·p_(k)))`, with ties broken by the frozen member
   order, `m = 3` for U2 (`2` at drop `LEVEL_1`) and `m = 2` for U3. Verify against a
   hand-computed table.
6. All reported intervals are ordinary two-sided 95% whole-identity bootstrap **percentile**
   intervals, `B = 10,000`, unadjusted, and the same resampling pass serves both the interval
   and the inversion p-value under the frozen seed.
7. The U2 positive-declaration conjunction requires, per member, a Holm-adjusted `p ≤ 0.05`
   **and** a directionally-clear unadjusted interval — and refuses to declare `U2_POSITIVE`
   when either the §23 controls fail or any member's adjusted p exceeds 0.05.
*Fails:* `B_INFERENCE_PROCEDURE_MISMATCH`, `B_U2_FAMILY_ALTERED`.

---

## E. III-B live pilot tests (stage `B-PILOT`)

Run **only** on `e3_p90` and `e3_p91`, at `q_low` and `q_high`, condition `L4`. Four captures,
100 forwards. No production identity may be used to debug III-B.

Verifies, with each observed value recorded in `iii_b_pilot_receipt.json`:

- `q` parameterization end to end (`startspec` → schedule → `SheepController`);
- innovation pairing at the new `q`;
- path replay to `1e-9` and noise replay by hash;
- ≥ 19 consecutive counterfactually fully-occluded target rows at each new `q`;
- VIS6 support and its coverage;
- the frozen FIR coherence check (§18.5), per direction, per new `q`;
- capture provenance, all seven receipts, sentinels;
- extraction: L19 × {`PREVIOUS`, `CURRENT`}, both array shapes;
- oracle target generation and the oracle validation receipt.

**`q_high` gate.** If the predeclared **technical** trajectory/window/FIR qualification gate fails
at `q = 0.2`, exactly **one** fallback re-pilot at `q = 0.15` is permitted. If that also fails,
`III_B = SKIPPED` and III-A continues untouched. The fallback may **never** be triggered by any
outcome-related consideration (`B_Q_FALLBACK_OUTCOME_DRIVEN`).
