# MineOcclude Experiment III — Preimplementation Authority

**Authority name:** `MINEOCCLUDE_EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY`
**Authority version:** `v1.0`
**Authority status:** `PROSPECTIVE_FROZEN_PREIMPLEMENTATION_AUTHORITY`
**Experiment namespace:** `experiment_iii`
**Identity namespace:** `e3_*`
**Authority construction date:** 2026-08-30
**Controlling design input:** Phase 0 Adjudicated Design (provenance; see §0.3)

**Execution gates at the moment this authority is issued:**

```
IMPLEMENTATION_AUTHORIZED  = false
P0_AUTHORIZED              = false
P1_AUTHORIZED              = false
P2_AUTHORIZED              = false
PRODUCTION_AUTHORIZED      = false
MODEL_INFERENCE_AUTHORIZED = false
EXPERIMENT_III_COMPLETE    = false
```

Each gate is opened only by the explicit exit condition of its lifecycle stage in §6. No
agent may open a gate by inference, by convenience, or because a schedule is slipping.

---

## 0. Authority identity, hierarchy, and provenance binding

### 0.1 What this document is

This is the single controlling operational authority for MineOcclude Experiment III from
implementation through final scientific closure. It is **self-contained**: every frozen
scientific value, formula, count, threshold, gate, and lifecycle rule needed to implement
and execute Experiment III is reproduced here. A Phase 2 implementation agent must be able
to work from `docs/experiment_iii/final_authorities/` plus the repository source tree without
reinterpreting the Phase 0 design or the historical Fable document.

This authority does **not** redesign Experiment III. Phase 0 settled what Experiment III
is. This authority converts those settled decisions into machine-checkable operations,
evidence, and failure semantics.

### 0.2 Document hierarchy

```
1. THIS AUTHORITY (docs/experiment_iii/final_authorities/)      <- controlling for execution
2. PHASE 0 ADJUDICATED DESIGN                           <- controlling for design intent
3. PHASE 0 DECISION MEMO / DECISION MATRIX              <- adjudication provenance
4. ORIGINAL FABLE DESIGN                                <- historical provenance only
5. HISTORICAL PROPOSAL / PRIOR EXPERIMENT DOCUMENTS     <- historical provenance only
```

If this authority and the Phase 0 adjudicated design ever disagree on a **scientific
decision**, the Phase 0 design wins and this authority is defective and must be amended
(§9). If they disagree on an **operational mechanism** that Phase 0 left to Phase 1, this
authority wins. Levels 4 and 5 are never authority; they may be consulted only to
understand historical evidence.

### 0.3 Repository and provenance binding

Bound at authority construction time against the **actual** repository state, not against
the commit recorded inside the Phase 0 document.

| Field | Value |
|---|---|
| Repository root | `C:/Users/lollo/MineOcclude-Exp3` |
| Remote | `https://github.com/atharv-santosh/MineOcclude.git` |
| Current branch | `experiment/exp3-graded-partial-observability` |
| Upstream branch | `origin/experiment/exp3-graded-partial-observability` |
| Authority source HEAD | `1664907fe7205a10d9d0717e046045861c31e120` |
| Phase 0 design commit | `1664907fe7205a10d9d0717e046045861c31e120` ("adjudicate Experiment III preauthority design") |
| Phase 0 inputs commit | `4c8dd7c1a7e8ff6ac0042361579da27e362996fe` ("add Experiment III preauthority creation inputs") |
| Original executable Regime A ancestor | `fa31aaca8af2872663ea81a54d6ed3a51e9f7f0a` ("adjudicate Regime A first25 decoding") |
| Ancestor relationship | direct parent and merge base of the Phase 0 inputs commit |
| Working tree at construction | Phase 0 design files relocated (see §0.5); no source-tree modification |
| `HEAD:src` tree object | `89102e18c7e6f9616652ffc0cdc5162c86408bbe` |
| `HEAD:fabric` tree object | `9a266404b4c37fa3c8f1cf733cfafa501e7cb9e7` |
| Source closure (index digest) | `077236e70fec4e312adae00b3c57ea4c2f131293bbcc37364044a9533c06c887` |
| `final_authorities/` git state at repair | **untracked** — Phase 2 must start from a committed, frozen package |

**Controlling Phase 0 input hashes (SHA-256):**

| Artifact | Path | SHA-256 |
|---|---|---|
| Adjudicated design (Markdown) | `docs/experiment_iii/experiment_3_authorities/authority_baseplate/MineOcclude_Experiment_III_Phase0_Adjudicated_Design.md` | `be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c` |
| Adjudicated design (DOCX) | `.../MineOcclude_Experiment_III_Phase0_Adjudicated_Design.docx` | `d2458e712a5202a3cae4509df9dcca482b841931ed50af45c9ac870a64fdc8af` |
| Decision memo | `docs/experiment_iii/preauthority/PHASE0_DESIGN_ADJUDICATION.md` | `621073206e6919990847841dee3602f83924211b5e9f9efdd58502b0dd6010c3` |
| Decision matrix | `docs/experiment_iii/preauthority/PHASE0_DECISION_MATRIX.json` | `92692df05a48481d96be54bf7d96159a24e74c11c9705756559a95c9d90c96f2` |
| Preauthority input manifest | `preauthority_creation_inputs/PREAUTHORITY_INPUT_MANIFEST.json` | `8527dffaac611f27a2d8a0462b408b7bb6e1ed48463fab6167c4d70e6ae1f656` |

**Source-closure method.** The Experiment III source closure is the SHA-256 of the byte stream
produced by `git ls-files -s src fabric scripts` on a clean worktree, each record formatted
exactly `"<mode> <blob-sha1> <stage>\t<path>"`.

**The records are sorted ascending by the `<path>` field only**, compared as raw UTF-8 bytes.
A generic whole-line sort is **forbidden**: it would order on `<mode>` and then `<blob-sha1>`
before ever reaching the path, producing a different byte stream and a different digest for the
same tree. Records are joined with a single `LF` and terminated by one trailing `LF` — no `CR`,
no BOM, no locale collation. This binds file identity and mode without depending on filesystem
timestamps. P2 (§6/A6) recomputes it and records both the closure digest and the HEAD commit.

**Git state of this package.** At the time of the final authority repair pass,
`docs/experiment_iii/final_authorities/` is **untracked**. Phase 2 must begin from a
**committed, frozen** authority state: this package is committed and its hashes rebound before
`IMPLEMENTATION_AUTHORIZED` may be set. The repair pass itself does not commit.

### 0.4 Namespace isolation

Experiment III occupies its own namespace. Historical Regime A, Regime A-prime, and
Experiment II scientific artifacts are **immutable** and must not be written, moved, or
regenerated by any Experiment III process.

| Domain | Experiment III value |
|---|---|
| Identity namespace | `e3_t01` … `e3_t25` (production), `e3_p90`, `e3_p91` (pilots) |
| Artifact roots | `docs/experiment_iii/` and `data/experiment_iii/` |
| Source roots | `src/mineocclude/experiment_iii/`, `scripts/experiment_iii/`, `tests/experiment_iii/` |
| Run namespace | `mineocclude-experiment-iii-v1` |
| Episode ID block | `86001`–`86999` (disjoint from A-prime `81000`–`85999` and Regime A `51001+`) |
| Durable prefix | `<operator-provided s3:// prefix>/experiment_iii/` |

Writing to any path owned by a prior experiment is `PROVENANCE_NAMESPACE_VIOLATION` (§8)
and is always terminal for the offending unit.

### 0.5 Working-tree note recorded at construction

At authority construction the working tree contained an intentional relocation, verified
byte-identical, of the Phase 0 adjudicated design:

```
docs/experiment_iii/preauthority/MineOcclude_Experiment_III_Phase0_Adjudicated_Design.{md,docx}
  ->
docs/experiment_iii/experiment_3_authorities/authority_baseplate/...
```

The Markdown and DOCX SHA-256 values are unchanged from `HEAD` (verified). The decision memo
and decision matrix were modified only to update their pointer to the new baseplate path. No
scientific content changed. This authority binds the **new** paths.

---

## 1. A0 — Experiment identity

### 1.1 Name and lineage

**MineOcclude Experiment III — Graded Partial Observability.**

Predecessor lineage:

1. **Regime A-prime** established the paired single-layout apparatus at speed 2.0 blocks/s
   and process noise `q = 0.05`, with renderer-extent occlusion truth and direction-specific
   causal FIR labels. Classified `DEVELOPMENT_ONLY`.
2. **Experiment II** reused the same 25 development identities to search 11 layers and
   several spatial representations, selecting `L19 | COARSE_2X6_CONCAT | CURRENT`. Under
   full occlusion that readout remained severely inaccurate (`R² = -13.8263`, RMSE `2.0711`
   blocks) while retaining strong visible controls.
3. **Experiment III** is a *fresh prospective follow-up*, not another search.

### 1.2 Scientific purpose

Experiment III measures how the held-out current-position error of the **already selected,
frozen** linear readout changes as direct visual evidence of the target is weakened along a
calibrated, outcome-blind, image-only ladder from a no-wall anchor (L0) through three
one-layer stained-glass conditions (L1–L3) to a one-layer opaque stone anchor (L4).

**Experiment III is explicitly not a representation search.** No layer search, no
representation search, no BEST-K, no PCA selection, no nonlinear rescue, no alternative
token grid, and no post-hoc reselection of the primary cell is permitted at any point in the
lifecycle, before or after outcomes exist.

### 1.3 Primary scientific question

> How does held-out current-position error from the frozen
> `L19 | COARSE_2X6_CONCAT | CURRENT` linear ridge readout change as an outcome-blind,
> image-measured coordinate of direct sheep evidence decreases from L0 to L4?

### 1.4 Secondary scientific questions

1. Does any partial-evidence condition degrade relative to L0?
2. Is there an additional error increase from the heaviest qualified partial condition L3 to
   opaque L4?
3. How does the frozen MineWorld readout compare with a linear current-frame raw-pixel
   baseline?
4. Do `CURRENT_MINUS_PREVIOUS` or `TWO_FRAME_CONCAT` improve on `CURRENT` without new
   forwards?
5. Is the opaque-condition error pattern consistent with the last potentially informative
   frame leaving the 16-pair context?
6. How do last-seen, constant-velocity, training-mean, and time-only baselines contextualize
   model error?
7. Do descriptive layers 4 and 10 show the same condition ordering as layer 19?

### 1.5 Explicit exclusions

Experiment III does **not** test or claim: calibrated posterior uncertainty (U2);
uncertainty dynamics (U3); causal intervention or steering (U4); a process-noise grid;
another speed; another layout; player-turn-away; Regime B; another checkpoint or model size;
broad layer or representation searches; BEST-K; nonlinear MLP rescue; a resource-pack opacity
intervention; multi-layer glass; glass panes; perforated or geometric fallback walls; or
reveal-recovery dynamics. Deterministic glass attenuation is **not** interpreted as
principled observation noise.

### 1.6 Result-independent scientific objective

The objective is to produce a **prospectively frozen, fully paired, outcome-blind
measurement** of the condition-response curve of one already-selected readout. The
experiment succeeds *as science* when the measurement is executed as frozen and reported
honestly, **whatever the direction or magnitude of the result**. There is no overall
experiment pass/fail gate and no arbitrary success threshold (§8.10.6).

### 1.7 Permissible and prohibited claims

**Permissible**, when supported by the frozen analysis:

- Statements about the linear accessibility of current target position from the frozen
  readout, in this apparatus, at this speed and process noise, on this layout, with this
  checkpoint, across the calibrated wall family.
- Statements about the ordering and magnitude of condition-level error as a function of the
  frozen RVE evidence coordinate.
- Comparison against the explicitly named **"linear current-frame pixel baseline"**.
- Statements that a predeclared two-frame linear transform did or did not improve accuracy.
- Statements that an observed pattern is *consistent with* finite-context loss.

**Prohibited**, regardless of result:

- Calibrated posterior uncertainty, belief state, or uncertainty dynamics (U2/U3).
- Causal use, steering, or intervention conclusions (U4).
- Causal object permanence, or its absence.
- "MineWorld has no hidden-state representation", or any model-wide absence claim.
- "MineWorld beats pixels" without the "linear current-frame" qualifier.
- Causal forgetting isolated from time and position (they remain coupled).
- Any universal or psychometric law.
- Any claim generalizing beyond one layout, one speed/noise regime, one checkpoint, the fresh
  cohort, the selected layers/representations, linear probes, and the calibrated wall family.

A negative result is publishable and does not authorize model-wide absence claims. A positive
partial-visibility result does not establish uncertainty calibration, causal use, or
generalized object permanence.

---

## 2. Frozen cohort authority

### 2.1 Cohort composition

| Quantity | Value |
|---|---|
| Production identities | **25** fresh, named `e3_t01` … `e3_t25` |
| Left-to-right identities | **13** |
| Right-to-left identities | **12** |
| Outer folds | **5**, five identities each |
| Inner rotations | **4**, fixed, inside each outer training set only |
| Pilot identities | **2** fresh: `e3_p90` (LEFT_TO_RIGHT), `e3_p91` (RIGHT_TO_LEFT) |
| Pilot confirmatory membership | **false**, permanently |
| Historical `t01`–`t25` role | evidence-only; **not** recaptured, **not** pooled |
| Identity replacement after outcomes | **forbidden** |

Pilot identities are generated by the same rules from the same deterministic stream, but are
**permanently excluded** from every production manifest, fold, fit, metric, and statistic. A
pilot identity appearing in any production analysis input is `COHORT_PILOT_CONTAMINATION`
and is terminal for that analysis run.

### 2.2 Deterministic generation

| Parameter | Frozen value |
|---|---|
| RNG algorithm | NumPy `Generator(PCG64)` via `numpy.random.default_rng` |
| Master salt | `EXPERIMENT_III_MASTER_SALT = sha256("MINEOCCLUDE_EXPERIMENT_III_V1|" + AUTHORITY_SHA256 + "|" + PHASE0_DESIGN_SHA256)`, materialized and frozen by A1, bound in P2 |
| Seed derivation | `seed(domain,index) = int.from_bytes(sha256(f"experiment-iii-v1\|{domain}\|{MASTER_SALT}\|{index}").digest()[:8], "big") & ((1<<63)-1)` |
| Candidate domains | `E3_LEFT_TO_RIGHT`, `E3_RIGHT_TO_LEFT` |
| Start-position RNG | `default_rng(seed ^ 0xE3E3E3E3)` |
| Start range LTR | uniform on `[-8.00, -7.65]` |
| Start range RTL | uniform on `[7.70, 8.00]` |
| Noise draw | `default_rng(noise_seed).standard_normal(180) * sqrt(q * dt)` |
| Noise seed | equal to the identity seed |
| Position recurrence | `x[t] = clamp( (x[t-1] + signed_speed*dt) + noise[t] )`, iterative, binary64, **drift added before noise** |
| Signed speed | `+2.0` for LEFT_TO_RIGHT, `-2.0` for RIGHT_TO_LEFT |
| Path hash | `sha256(numpy.asarray(positions, dtype="<f8").tobytes())` |
| Noise hash | `sha256(numpy.asarray(noise, dtype="<f8").tobytes())` |
| Episode ID | `86001 + serial` for production (serial 0…24); `86901`, `86902` for pilots |

**Iterative recurrence is mandatory, and the operand order is load-bearing.** The A-prime path
generator accumulates position in a Python loop, and Experiment III's FIR-kernel recovery (§5.3)
is validated against exactly that arithmetic.

- A vectorized `start + numpy.cumsum(increments)` is *not* bit-identical and is **forbidden** as
  the generator of record.
- **The drift term must be added before the noise term:** `(x + s*v*dt) + w`, never
  `(x + w) + s*v*dt`. *Corrected by Phase 1 Amendment 1.* Binary64 addition is not associative;
  verified at amendment time, the two orders diverge by one ULP (`8.88e-16`) from tick 40 onward
  and produce **completely different** path SHA-256 values. Only the drift-first order reproduces
  the frozen A-prime hash `b5803943e515ea633cc4dd80ddeaf349db5cb99d11980febdc3f13d7f84a56b7`.

Enforced by fixture §11.A.3.

**RNG stream stability.** During authority construction, `default_rng(...).standard_normal`
was empirically verified to reproduce a frozen A-prime path hash **bit-exactly** under Python
3.14.6 / NumPy 2.4.3, against an artifact generated on a different host and NumPy version
(§5.3 step 1). A1 must nonetheless ship a stream-stability fixture (§11.A.2); drift is
`COHORT_RNG_STREAM_DRIFT`, terminal until the environment is pinned to a stream-compatible
NumPy.

### 2.3 Candidate admission order

Candidates are generated and tested in strictly ascending `index` per direction, and the
first qualifying candidates are admitted — LTR to a count of 13, then RTL to a count of 12.
Admission uses **only** state, geometry, and timing. It never reads a rendered frame, an
activation, a decoder error, a magenta detection, an RVE score, or any pilot or historical
outcome.

### 2.4 Qualification gates — **twelve**, all must pass

1. **Frame coverage.** Exactly `180` schedule-covered model frames at 20 Hz.
2. **Motion identity.** `speed = 2.0` blocks/s, `q = 0.05` blocks²/s, `dt = 0.05` s.
3. **No lane clamp over the protected prefix.** `-8.0 < x[t] < 8.0` strictly for every `t` in
   `[0, last_target_row_index]`. The clamp must not bind anywhere at or before the last scored
   target row, which covers every scored row together with its complete causal FIR history.
   Clamping in the **tail**, after the target window, is expected and harmless and is recorded as
   a diagnostic, not a rejection.

   *Corrected by Phase 1 Amendment 1.* A 180-frame traversal at speed 2.0 covers 18.0 blocks
   across a 16-block lane, so touching a bound somewhere in the capture is geometrically
   unavoidable: all 25 real, qualified A-prime speed-2.0 identities touch a bound near tick 153.
   The earlier formulation (`strictly inside for every t in [0,179]`) was therefore infeasible and
   would have admitted no candidate at all. Verified: 0/25 A-prime WALL units clamp at or before
   their last target row, and 25/25 clamp in the tail.
4. **Reproducible schedules.** Recomputing path and noise from the frozen seed reproduces
   `path_sha256` and `noise_schedule_sha256` exactly.
5. **Complete causal FIR history.** Every target row index `t` satisfies `t >= 8`, so the
   9-tap direction kernel (§5) has complete history.
6. **Counterfactual occlusion run.** At least **19 consecutive** model frames whose
   **material-independent counterfactual rendered extent class** (§4.5) equals
   `EXTENT_FULLY_OCCLUDED`.
7. **Nonzero target variation.** The 19 FIR labels are not constant.
8. **Minimum target standard deviation.** `std(labels, ddof=0) >= 0.10` blocks.
9. **Direction diversity.** RMS difference of the 19-label vector against every
   already-admitted identity **of the same direction** is `>= 0.10` blocks. This is a
   *between-identity* gate and is distinct from gate 8, a *within-identity* spread gate. Both
   are required. (The legacy generator at `src/mineocclude/regime_a.py:637-733` implements
   only the between-identity form; gate 8 is new and must be added.)
10. **Seed uniqueness.** The seed is unique within Experiment III.
11. **Historical-seed exclusion.** The seed appears in no historical Regime A, Regime A-prime,
    or Experiment II manifest reachable from this repository. A1 materializes the exclusion
    set explicitly and binds its hash.
12. **All-`q` prospective qualification.** The candidate satisfies gates **1–11** at **every**
    frozen `q ∈ {0.0125, 0.05, 0.2}`, each evaluated on that `(identity, q)` cell's **own**
    path regenerated from the identity seed with the identical frozen arithmetic.

    *Added by the final authority repair pass (defect B1).* §19.4 already required every
    admitted identity to qualify at all three `q`; it was simply never written into this gate
    list, and the implementing primitive was ordered **after** cohort materialization. Both are
    corrected here.

    **This gate is evaluated BEFORE the cohort is materialized or frozen.** The observed
    per-candidate all-`q` qualification rate is `0.9575`, so the probability that at least one
    of 25 independently admitted identities fails the requirement is `1 − 0.9575²⁵ = 0.661`.
    Evaluating it after materialization would therefore fail about two runs in three and would
    leave `B-GEN` with no admissible recovery other than cohort regeneration — forbidden once
    any capture exists, and never permitted on the basis of an outcome.

    It is a **III-A admission constraint**, not a III-B stage. It reads only seeds, geometry and
    timing — no rendered frame, no activation, no prediction, no RVE score, **no MineWorld
    output**, no scientific outcome of any kind. It is applied identically whether III-B later
    runs, skips, fails or is dropped, so **the same final III-A cohort exists either way**.

    The `q = 0.15` technical fallback (§29.4) is **recorded as a diagnostic column but is not
    binding**: a `q = 0.15` failure never rejects a candidate and never regenerates the cohort.
    If the fallback is later triggered, cells that fail at `0.15` are III-B-local attrition
    handled by the drop ladder (§29.6 `LEVEL 3`).

    Implemented by the `CB02` primitive and guarded by the `CB03` bit-identity regression
    fixture; **both are prerequisites of `I02`**, not dependents of it. If either is unavailable
    or failing, `I02` **fails closed** with `COHORT_ALL_Q_PRIMITIVE_MISSING` and materializes
    nothing. Exhaustion of the frozen candidate index bound is
    `COHORT_ALL_Q_QUALIFICATION_INFEASIBLE`.

**Candidate index bound.** Candidates are scanned in ascending index to a **frozen bound of 200
per direction**. The expected requirement is ~14–16 per direction, so the bound is more than
12× the expectation; exhausting it is a genuine terminal signal, not ordinary scanning. The
permitted responses to a gate-12 shortfall are: continue scanning to the bound, or repair an
implementation defect and rerun the identical deterministic procedure while **no capture of any
kind exists**. Relaxing gate 12, relaxing gates 1–11 at any `q`, dropping a `q` from the binding
set, changing the master salt, or regenerating on the basis of any outcome are all forbidden.

### 2.5 Target window selection

The production target window is the **first 19 consecutive eligible rows in ascending
model-frame order** — the earliest run of 19 adjacent rows all satisfying §4.6. There is no
phase offset, no outcome-derived adjustment, and no per-fold phase
schedule. A-prime used `phase_offsets_frames = [0,3,6,9,12]`; Experiment III removes this and
must not reintroduce it.

The 19 target indices and their 19 FIR labels are frozen per identity and applied
**unchanged and identically** to all five conditions L0–L4.

### 2.6 Folds and priority order

**Outer folds.** Five identity-disjoint outer folds of five identities, direction-balanced as
arithmetically possible:

```
fold 0: 3 LTR + 2 RTL
fold 1: 2 LTR + 3 RTL
fold 2: 3 LTR + 2 RTL
fold 3: 2 LTR + 3 RTL
fold 4: 3 LTR + 2 RTL
                     -> 13 LTR, 12 RTL, 5 identities per fold
```

Within direction, identities are ordered by `(seed, identity_id)` and dealt to folds in that
order. Folds are shared across every condition, representation, baseline, and target.

**Inner rotations.** Four fixed inner identity rotations operate **only inside** each outer
training set (20 identities in the complete cohort) and only for ridge-alpha selection.
Assignment is deterministic and outcome-independent: within each direction, sort the outer
training identities by `sha256(f"E3_INNER_ROTATION_V1|outer={outer}|{identity}")` and deal
round-robin into 4 rotations, offsetting the second direction by one rotation. If rotation
sizes are not as equal as arithmetically possible, apply a deterministic rebalance — move the
identity with the lowest `sha256(f"E3_INNER_REBALANCE_V1|outer={outer}|{identity}")` from the
largest rotation to the smallest, repeating until balanced. No target or feature value may
influence this.

*Note:* the legacy `inner_fold_assignment`
(`src/mineocclude/regime_a_first25_analysis.py:27-70`) hard-requires 20 identities and
produces **five** inner folds of four. Experiment III requires **four** rotations. The legacy
function must not be reused unmodified (§8, item C03).

**Identity priority order.** A1 freezes the total order `e3_t01 < e3_t02 < … < e3_t25`. It is
used **only** by the deadline fallbacks (§10) to choose the first `N` identities and may never
be reordered by observed performance.

### 2.7 Cohort artifacts

| Artifact | Content |
|---|---|
| `production_identity_manifest.jsonl` | 25 rows: identity, direction, seed, noise_seed, episode_id, start_world_x, speed, q, dt, frames, path_sha256, noise_schedule_sha256, target_model_frame_indices (19), expected_causal_fir_target_world_x_blocks (19), expected_target_sd_blocks, outer_fold, priority_rank, spec_hash |
| `production_identity_manifest.sha256` | SHA-256 of the manifest bytes |
| `pilot_identity_manifest.jsonl` | 2 rows, same schema, `confirmatory_membership = false` |
| `folds.json` | outer fold membership plus the four inner rotations per outer fold |
| `identity_priority_order.json` | total order over the 25 production identities |
| `historical_seed_exclusion_set.json` | excluded seeds and their source manifests |
| `cohort_qualification_receipt.json` | per-candidate accept/reject with the first failing gate, generation order, salt, RNG identity, counts |
| `cohort_all_q_qualification_receipt.json` | per candidate: the first failing sub-gate **at each frozen `q`**; the non-binding `q = 0.15` diagnostic column; the candidate index bound; and the binding assertion that gate 12 was evaluated **before** materialization and freeze |
| `q_regression_a1_receipt.json` | the `A1` copy of the `q = 0.05` bit-identity regression proof, recorded **before** `I02` runs |

Every rejected candidate is logged with its index, seed, and the **first** gate it failed.
Rejection logging is required evidence, not a convenience.

---

## 3. Frozen physical apparatus authority

### 3.1 Frozen apparatus values

| Quantity | Frozen value |
|---|---|
| Layout | `layout_01` only |
| Minecraft | 1.16.5 |
| Fabric loader / API | `0.15.11` / `0.42.0+1.16` |
| Yarn mappings | `1.16.5+build.10` |
| Capture rate / `dt` | 20 Hz / 0.05 s |
| Speed | **2.0** blocks/s |
| Process noise | `q = 0.05` blocks²/s |
| Frames per capture | **180** |
| Framebuffer | 640 × 360 (`FrameCapture.EXPECTED_W/H`) |
| Sheep lane | world `x ∈ [-8, 8]`, `y = 4`, `z = 6` |
| Camera feet | `(0.5, 4.0, -5.5)` |
| Camera eye | `(0.5, 5.6200000048, -5.5)` |
| Camera orientation / FOV | yaw 0, pitch 0, roll 0 / 70° |
| Camera lock | server re-teleports to the canonical pose every tick (`lockCamera = true`) |
| As-built wall volume | `x ∈ [-3, 4]`, `z ∈ [2, 3]`, `y ∈ [4, 7]` |
| Wall construction | one full-cube block thick, three blocks high (`ArenaBuilder.WALL_HEIGHT = 3`) |
| Lighting / weather | fixed noon, weather controlled, zero random ticks |
| Target | adult, AI-disabled, silent, persistent, invulnerable **magenta** sheep |

**Speed rationale, frozen.** 2.0 is the speed of A-prime, Experiment II, and the current
manuscript. The `SPEED_BLOCKS_PER_SECOND = 1.5` constant at
`src/mineocclude/regime_a.py:29` is an implementation-base default of the original executable
lineage and is **superseded**. No Experiment III spec, path, manifest, or validator may be
produced or accepted under 1.5. Any artifact validated at 1.5 is `COHORT_SPEED_VIOLATION`,
terminal for that artifact. A1 must audit every 1.5-bearing literal and manifest validator on
the Experiment III path.

### 3.2 As-built wall derivation (must be reproduced, not assumed)

`layout_01` declares `wallSegMin = -2.5`, `wallSegMax = 2.5`, `wallOrthoConst = 6.0`,
`wallOrthoOffset = -4.0`, `laneY = 4.0`, `wallAxis = X`. `ArenaBuilder` places whole blocks
and a block at coordinate `n` occupies `[n, n+1)`. The occluder **as built** is therefore:

```
wall_ortho     = floor(wallOrthoConst + wallOrthoOffset) + 0.5 = floor(2.0) + 0.5 = 2.5
wall_axis_min  = floor(wallSegMin)                             = -3
wall_axis_max  = ceil(wallSegMax) + 1.0                        = 4.0
wall_y_min     = laneY                                         = 4.0
wall_y_max     = laneY + WALL_HEIGHT                           = 7.0
ortho half     = 0.5
```

This reproduces the frozen volume `x ∈ [-3,4]`, `z ∈ [2,3]`, `y ∈ [4,7]` (verified at
authority construction). Implementations must **compute** these expressions, never hard-code
the interval, so a layout change fails closed rather than silently mismatching.

### 3.3 Required runtime receipts

Every production capture must emit, and every validator must check:

| Receipt | Required content | Blocker on failure |
|---|---|---|
| Wall receipt | per-cell observed block state over the full scan span; `declared_block_id` equal to the condition's frozen registry ID; zero mismatches; zero unexpected non-air cells | `WALL_RECEIPT_MISMATCH` |
| Camera receipt | observed feet/eye/yaw/pitch/roll/FOV equal to §3.1 within `1e-6`; camera lock active | `CAMERA_POSE_DRIFT` |
| Target receipt | one retained target entity UUID across all 180 frames; `target_respawn_count == 0`; adult / AI-disabled / silent / persistent / invulnerable flags observed | `TARGET_IDENTITY_FAILURE` |
| Timing receipt | `len(server_state) == len(client_tick) == len(actions) == len(frames) == 180`; `server_tick == index` on every stream | `TIMING_CARDINALITY_MISMATCH` |
| Path receipt | replayed positions equal logged `sheep_x` within `1e-9` absolute; recomputed path/noise hashes equal the manifest | `CAPTURE_PATH_HASH_MISMATCH` |
| Scene receipt | observed `scene` equals the condition's expected scene (§4.1) | `WALL_CONDITION_SCENE_MISMATCH` |
| Framebuffer receipt | every frame exactly 640 × 360 RGB; no byte-identical stale run beyond the frozen tolerance | `CAPTURE_STALE_FRAME` |

The historical replay check at `scripts/run_regime_a.py:283-409` clamps the expected position
to `[-8, 8]`. Experiment III **retains** the clamp in the replay comparison, because the
trajectory tail genuinely clamps and the replay must reproduce it. Qualification gate §2.4.3
guarantees only that the clamp never binds **at or before the last scored target row**. If a
production replay requires the clamp to bind within that protected prefix, that is
`CAPTURE_LANE_CLAMP_ENGAGED` and the unit is technically invalid; tail clamping after the target
window is expected and is recorded as a diagnostic.

---

## 4. Condition and visibility-semantics authority

### 4.1 The five frozen conditions

| ID | Physical condition | Runtime scene | `wall_block_id` | Scientific role |
|---|---|---|---|---|
| `L0` | no blocks in the original wall cells | `NO_WALL` | `minecraft:air` | fully visible anchor |
| `L1` | one full-cube layer, P0-selected stained glass | `NORMAL` | P0-selected | high partial evidence |
| `L2` | one full-cube layer, P0-selected stained glass | `NORMAL` | P0-selected | medium partial evidence |
| `L3` | one full-cube layer, P0-selected stained glass | `NORMAL` | P0-selected | low but measurable partial evidence |
| `L4` | one full-cube layer of stone | `NORMAL` | `minecraft:stone` | opaque anchor |

`L0` requires runtime scene `NO_WALL`. The current `startspec` path **refuses** any scene
other than `NORMAL` and hard-codes `Scene.NORMAL` into the config
(`MineOccludeServer.java:305-325`). Making `L0` reachable through the spec path is a required
bounded engineering change (§8, item C06). Capturing `L0` as `NORMAL` would build a stone wall
and silently destroy the anchor condition; the scene receipt (§3.3) is the fail-closed guard.

### 4.2 Eligible P0 stained-glass candidate roster (exactly 12)

```
minecraft:white_stained_glass         minecraft:cyan_stained_glass
minecraft:orange_stained_glass        minecraft:blue_stained_glass
minecraft:light_blue_stained_glass    minecraft:brown_stained_glass
minecraft:yellow_stained_glass        minecraft:green_stained_glass
minecraft:lime_stained_glass          minecraft:black_stained_glass
minecraft:gray_stained_glass
minecraft:light_gray_stained_glass
```

### 4.3 Prospective exclusions (frozen, not reopenable)

Excluded and never eligible as an Experiment III scientific level:

- **magenta, pink, purple, red** stained glass — target-adjacent hue contaminates the magenta
  measurement channel;
- **clear glass** — Minecraft 1.16.5 renders clear glass through the *cutout* path while
  stained glass is *translucent*; clear glass is an engineering diagnostic only;
- **glass panes** — different geometry and surface count;
- **multi-layer walls**, **air gaps**, **mixed-color stacks** — alter geometry, surface count,
  or face culling;
- **perforated / hole-pattern walls**;
- **any alternate geometric wall fallback**.

**If no valid three-level stained-glass ladder exists, P0 emits:**

```
P0_RESULT = NO_VALID_LADDER
PRODUCTION_AUTHORIZED = false
```

Experiment III **stops** and returns to authority adjudication. It does **not** substitute
another experimental geometry, another material family, or a reduced condition count.

### 4.4 Separated visibility fields (frozen row schema)

Physical condition, counterfactual geometry, direct image evidence, the magenta diagnostic,
and target eligibility are five **separate** things and must remain five separate fields.

| Field | Domain | Authority role |
|---|---|---|
| `condition_id` | `L0`…`L4` | scientific condition label |
| `wall_present` | bool | physical block presence |
| `wall_block_id` | registry ID or `minecraft:air` | exact observed material |
| `counterfactual_extent_class` | `EXTENT_FULLY_VISIBLE` / `EXTENT_PARTIAL` / `EXTENT_FULLY_OCCLUDED` | **the only geometric target-selector input**; computed against the unchanged original wall volume regardless of condition |
| `server_geometric_status` | `visible` / `occluded` | runtime center-ray diagnostic — **never** a selector |
| `magenta_status` | `detected` / `not_detected` | image diagnostic — **never** a selector |
| `magenta_area_pixels` | int | image diagnostic — **never** a selector |
| `rve_condition_score` | float | P0-frozen condition-level evidence coordinate — **never** a selector |
| `target_eligible` | bool | §4.6 |

### 4.5 Counterfactual extent — exact semantics

`counterfactual_extent_class` is computed from the **material-independent counterfactual
occluder**: the original one-layer wall footprint of §3.2, treated as **present for every
condition, including L0**.

This is the single most dangerous place in the implementation. The ported A-prime
`classify_extent` returns `EXTENT_FULLY_VISIBLE` immediately when `wall.present is False`.
Constructing the L0 counterfactual wall with `present=False` therefore yields *zero* eligible
target rows for L0 and silently breaks the pairing. **The counterfactual `WallGeometry` must
always be constructed with `present=True`, for all five conditions.** Enforced by fixture
§11.A.10 and blocker `FIR_COUNTERFACTUAL_PRESENCE_ERROR`.

The classification engine is the ported A-prime v0.3 module (§5.1):

```
half_extent           = TARGET_EXTENT_HALF_BLOCKS = 0.8727621336620037   # (7 + sqrt(48.5)) / 16
samples_per_axis      = 5    (25-point closed lattice over the horizontal extent box)
vertical test height  = target centre y = laneY + 0.5 = 4.5
occlusion primitive   = segment_hits_wall — an exact replication of
                        GeometryUtil.segmentHitsWall including its 63-sample march
                        (i in [1,64)) and its inclusive face bounds
EXTENT_FULLY_OCCLUDED <=> every lattice point occluded
EXTENT_FULLY_VISIBLE  <=> no lattice point occluded
EXTENT_PARTIAL        <=> any mixture (reported, never scored)
```

Verified during authority construction against the frozen `layout_01` geometry and the frozen
camera eye `(0.5, 5.6200000048, -5.5)`: the counterfactual fully-occluded lane interval is
approximately `x ∈ [-3.49, 4.49]`, about **7.98 blocks** wide. At 2.0 blocks/s that is roughly
**79 consecutive ticks** of full counterfactual occlusion — comfortably more than the 19
required, so gate §2.4.6 is feasible with wide margin.

Independent cross-check performed at authority construction: all **475** A-prime `WALL`
materialized target labels classify as `EXTENT_FULLY_OCCLUDED` under this engine and this
geometry (475/475). This is the required port-equivalence fixture (§11.A.11).

### 4.6 Target eligibility — exact rule

```
target_eligible(row) :=
      row.model_frame_idx ∈ frozen_target_model_frame_indices(identity)   # exact manifest membership
  AND row.counterfactual_extent_class == EXTENT_FULLY_OCCLUDED
  AND complete path / noise / timing alignment for this row
  AND complete causal FIR history (model_frame_idx >= 8)
```

**The old Regime A `OCCLUDED_AGREEMENT` predicate is not, and may never become, the
Experiment III target selector.** `classify_visibility`
(`src/mineocclude/regime_a.py:245-254`) requires `geometric_status == "occluded"` **and**
`magenta_status == "not_detected"`. For L1–L3 the target is deliberately behind the wall
footprint *while still producing image evidence*, so magenta will frequently be `detected`.
Applying `OCCLUDED_AGREEMENT` would make eligibility material-dependent and outcome-dependent,
destroying the pairing and the manipulation itself. Likewise `assign_stable_hidden_tau`
(`:257-300`) and its `tau` field must not select Experiment III targets, and
`scripts/run_regime_a.py:283-409` must not be reused unmodified for target construction.
Presence of either as a selector on the Experiment III path is
`TARGET_LEGACY_SELECTOR_PRESENT`, terminal until removed.

The **exact same 19 target rows and 19 labels** are shared across all five conditions within
an identity. Any per-condition difference in target indices or labels is
`TARGET_ROW_CONDITION_DIVERGENCE`.

Neither magenta detectability nor RVE may admit or remove a production target row. "Behind the
wall footprint" does **not** mean "no visible evidence"; L0–L3 can carry direct evidence on the
same counterfactually occluded row.

---

## 5. FIR target labels and context age

### 5.1 A-prime measurement port — exact provenance

Experiment III ports the **minimal A-prime measurement subset** and nothing else. It does not
port the A-prime campaign lifecycle, remote authorities, recovery admissions, S3 lifecycle, or
development verdict logic.

| Ported item | Source commit | Source path | Blob SHA-1 |
|---|---|---|---|
| Renderer-extent geometry: `SHEEP_FUR_MODEL_CONSTANTS`, `TARGET_EXTENT_HALF_BLOCKS`, `derive_target_extent_half_blocks`, `WallGeometry`, `segment_hits_wall`, `classify_extent`, `extent_sample_points`, `verify_reference_agreement` | `a5d763a2ed4574c082dce2572ddb97c831929f81` | `src/mineocclude/prospective/extent_geometry.py` | `45889b6bc9ed07129f5fd2f15167b694206eab31` |
| Canonical causal-FIR sum and complete-history gate: `causal_fir_targets` | `a5d763a2ed4574c082dce2572ddb97c831929f81` | `src/mineocclude/prospective/development_workflow.py` | recorded by A1 |
| `normalized_kernel` and kernel diagnostics (`kernel_off_peak_mass`, `kernel_group_delay_ticks`, `kernel_mode_lag`, `kernel_positive_mass_support`, `kernel_is_effectively_pure_delay`) | `a5d763a2ed4574c082dce2572ddb97c831929f81` | `src/mineocclude/prospective/temporal_alignment.py` | recorded by A1 |

These paths are **not present in the current worktree**; they are retrieved from the
repository object database via `git show a5d763a:<path>` and copied into Experiment III-native
modules under `src/mineocclude/experiment_iii/`. A1 records the retrieved blob SHA-1 of each
ported file in `aprime_port_receipt.json`. Retrieval failure is
`APRIME_PORT_SOURCE_UNAVAILABLE`.

Commit `a5d763a` ("Regime A' v0.3 extent-visibility prospective successor freeze") is reachable
from `origin/exploration/regime-a-prime-qualification-v0-1` and
`origin/repair/stage2-disaster-recovery-v0-4`. The branch ancestry of
`experiment/exp3-graded-partial-observability` is **not** changed by this port; only the named
scientific primitives are copied.

### 5.2 Canonical label construction

```
taps     = normalized_kernel(direction_kernel)   # nonnegative, rescaled to unit mass by math.fsum
label[t] = sum over lag in [0, len(taps)) of taps[lag] * position[t - lag]
require    t - len(taps) + 1 >= 0                # complete causal history
```

`normalized_kernel` rejects kernels with fewer than two taps, any negative tap, or non-positive
total mass. A pure-delay kernel (off-peak mass within the frozen numerical tolerance of a bare
integer-tick delay) is forbidden.

### 5.3 The frozen direction-specific kernels — recovery, not invention

Phase 0 requires "the frozen direction-specific A-prime causal FIR". **The literal tap values
are not present in this repository**: they lived only in an A-prime Stage-1 decision artifact
(`stage1_decision_sha256 = d00d7730e44200c2406d32475843a69011f3fff5b4cdaaa67167321416b7f6e2`)
that was never committed here.

They are, however, **exactly recoverable and independently verifiable** from committed
artifacts, using no outcome of any kind. Authority construction performed and verified this
recovery; A1 must reproduce it and bind the result.

**Recovery source (committed, read-only):**

```
commit  f2bc2c8082e77f9c3f9e089f2fb1a20b11a052a8
path    docs/status/integration/regime_a_prime_qualification_v0_1/
        prospective_development_authority_v0_4/stage2_locked_manifest.json
status  POST_STAGE1_MATERIALIZED_AWAITING_SEPARATE_FREEZE_AND_AUTHORIZATION
content 50 capture units = 25 trajectories x {WALL, NO_WALL}, every unit
        target_window_status = MATERIALIZED_FROM_STAGE1, carrying
        target_model_frame_indices and expected_causal_fir_target_world_x_blocks
```

**Recovery procedure (deterministic, outcome-blind):**

1. For each capture unit, regenerate its 180-frame path with the A-prime generator arithmetic:
   `default_rng(noise_seed).standard_normal(180) * sqrt(q*dt)`, iterative accumulation with the
   `[-8, 8]` clamp, from `start_world_x` at `speed_blocks_per_second` in the unit's direction.
   **Verify `sha256(asarray(path, "<f8").tobytes())` equals the unit's `expected_path_sha256`.**
   Refuse the entire recovery if any unit mismatches.
2. For each direction, assemble the linear system `A h = b`, where each row of `A` is
   `[x[t], x[t-1], …, x[t-8]]` for a target index `t`, and the corresponding `b` entry is that
   unit's materialized `expected_causal_fir_target_world_x_blocks` label.
3. Solve by least squares over all units of that direction.
4. **Acceptance gates — refuse unless all hold:** design rank exactly `9`; every tap
   `>= -1e-9`; tap sum equals `1` within `1e-9`; maximum absolute residual `<= 1e-12` blocks;
   the normalized aggregate kernel mode lag equals `2` and positive-mass support is contained in
   `[0, 8]`, matching A-prime's own frozen forensic reference.
5. Re-derive all **950** A-prime materialized labels from the recovered taps and confirm
   agreement.

**Values recovered and verified at authority construction.** Kernel lags 0…8. A-prime stored
the taps at 10 decimal places; the least-squares solution reproduces all 950 labels to
`2.2e-15` (binary64 round-off), and the 10-decimal rounded form reproduces them to `9.0e-12`.

```
LEFT_TO_RIGHT  h = [0.0552210582, 0.0955547802, 0.1729033607, 0.2562377030,
                    0.1725945773, 0.1502955787, 0.0283805770, 0.0327627758, 0.0360495890]
RIGHT_TO_LEFT  h = [0.0155128136, 0.1420986717, 0.3819949723, 0.2529919934,
                    0.1314006058, 0.0092585384, 0.0336603539, 0.0330820509, 0.0000000000]

kernel length             = 9 taps, lags 0..8
first fully-resolved tick = 8
LTR  group delay 3.339950418234, mode lag 3, positive support [0,8]
RTL  group delay 2.670496191400, mode lag 2, positive support [0,7]
aggregate mode lag        = 2      (matches A-prime frozen forensic reference)
verification              = 950/950 labels reproduced; 50/50 path hashes reproduced
```

**Normalization is mandatory and is frozen here, once, for every consumer.**

```
normalized[k] = taps[k] / math.fsum(taps)        accumulate H(m) with math.fsum
```

Applied **once, at load**, before any label, any `H(m)`, any `S(τ)`, any `gbar`, any
`c_direction`, and before any oracle quantity whatsoever.

The published taps are rounded to 10 decimal places, so
`fsum(LEFT_TO_RIGHT) = 0.9999999999` — `1.0e-10` short of unit mass — while
`fsum(RIGHT_TO_LEFT) = 1.0` exactly and is unchanged by normalization. **Unnormalized taps
satisfy the `1e-9` label tolerance of §11.A.12 but FAIL the stricter `1e-12` `S(τ)` oracle
tolerance of §11.D.6**, by up to `9.29e-10` in the `LEFT_TO_RIGHT` direction. Normalized taps
reproduce the frozen `H(m)`, `S(τ)`, `gbar` and `c_direction` tables of §20.3 and
`III_B_ORACLE_SPECIFICATION.json` with maximum absolute difference `0.0`. The `RIGHT_TO_LEFT`
tap 8 is the exact float `-0.0`; it is treated as `+0.0` and does not violate the
nonnegativity gate. Using unnormalized taps anywhere is `FIR_KERNEL_NOT_NORMALIZED`.

The same normalization is frozen identically in `FIR_KERNEL_RECOVERY_RECEIPT.json`,
`III_B_ORACLE_SPECIFICATION.json`, the machine authority, change item `C14`, and tests
`A.12` and `D.6`.

The recovered taps are **measurement calibration inherited from the same speed-2.0 apparatus**,
not a learned outcome readout. They are frozen at A1, bound in P2, and may never be refitted
from Experiment III data. Refitting is a scientific amendment (§9), never a repair.

If recovery fails any acceptance gate, emit `FIR_KERNEL_RECOVERY_FAILED` — terminal for
Experiment III until a prospective amendment supplies an authenticated kernel source.

### 5.4 Context age

```
a = 1   at the first fully occluded counterfactual target row
a = 19  at the last
a       = ticks since the last counterfactual row that was NOT fully occluded
```

The MineWorld context is `[t-15, …, t]` (16 pairs). Therefore the last potentially informative
pre-occlusion pair is **present in context for `a <= 15`** and **absent for `a >= 16`**.

This must be **verified from explicit frame identities** in the tokenized context — never
inferred from a generic `tau` label, a bin name, or an index convention. Verification fixture
§11.A.13; failure is `TOKEN_CONTEXT_AGE_UNVERIFIED`.

---

## 6. Experiment III lifecycle

Twenty states, `A0` through `A19`. Each state carries: purpose, entry conditions, controlling
inputs, exact operations, source entrypoints, unit of work, expected counts, expected outputs,
required evidence, PASS, FAIL, blockers, allowed repairs, forbidden repairs, retry rules,
resume rules, invalidation scope, exit condition, and next authorized state.

The machine-readable form is `EXPERIMENT_III_LIFECYCLE.json`. It is normative and must agree
with this section field for field.

**Global rules for every state:**

- No state may be entered until its predecessor's exit condition is satisfied and its evidence
  artifact exists and hashes correctly.
- No state may be declared PASS on the basis of "looks correct". Every PASS condition below is
  machine-checkable.
- Any state may emit a blocker. A blocker halts that state; it never silently downgrades scope.
- Completed, validated, hash-bound work from earlier states is preserved across failures and is
  never recomputed merely because a later state failed.
- Every artifact records the `AUTHORITY_SHA256` it was produced under. A mismatch is
  `PROVENANCE_AUTHORITY_DRIFT`.

---

### A0 — AUTHORITY_IDENTITY

**Purpose.** Establish and hash-bind the authority, so every later artifact can name the exact
authority it was produced under.

**Entry.** Phase 0 adjudication complete (`AUTHORITY_CREATION_READY = true`).
**Inputs.** Phase 0 adjudicated design, decision memo, decision matrix, preauthority input
manifest, live repository state.
**Operations.** Bind repository identity (§0.3); hash the five Phase 0 inputs; compute the
source closure; write the authority package; run the internal audit (§12).
**Entrypoint.** This authority package; no code.
**Unit of work.** The authority package.
**Expected counts.** 11 required authority artifacts plus the FIR recovery receipt.
**Outputs.** `docs/experiment_iii/final_authorities/*`.
**Evidence.** `AUTHORITY_VALIDATION_REPORT.md`; `AUTHORITY_SHA256`.

**PASS.** All required artifacts exist; every JSON parses; the machine authority agrees with
the Markdown on every frozen value; internal audit PASS; self-containment audit PASS.
**FAIL.** Any missing artifact, parse failure, cross-file disagreement, or unresolved Phase 0
contradiction.
**Blockers.** `AUTHORITY_INCOMPLETE`, `AUTHORITY_INTERNAL_INCONSISTENCY`,
`AUTHORITY_PHASE0_CONTRADICTION`, `AUTHORITY_NOT_SELF_CONTAINED`.
**Allowed repairs.** Edit the authority before implementation begins.
**Forbidden repairs.** Changing a settled Phase 0 scientific decision (that is §9).
**Retry.** Unlimited before A1 starts.
**Resume.** Rewrite the authority package.
**Invalidation scope.** If the authority changes after A1 has begun, every downstream artifact
bound to the old `AUTHORITY_SHA256` is invalidated and must be revalidated.
**Exit.** `AUTHORITY_INTERNAL_VALIDATION = PASS`.
**Next.** `A1`. `IMPLEMENTATION_AUTHORIZED` may be set true only by an explicit operator
decision recorded against this authority.

---

### A1 — IMPLEMENTATION

**Purpose.** Build every Experiment III module named in the change matrix. No execution.

**Entry.** A0 PASS; `IMPLEMENTATION_AUTHORIZED = true`.
**Inputs.** This authority; `IMPLEMENTATION_CHANGE_MATRIX.json`;
`IMPLEMENTATION_TASK_GRAPH.json`; the source tree; the A-prime port sources (§5.1); the
A-prime v0.4 stage2 manifest (§5.3).
**Operations.** Execute tasks `I01`–`I18` in dependency order, **plus the two shared-path
tasks `IB02` and `IB03`, which must complete before `I02`**. Materialize the fresh cohort under
all **twelve** qualification gates, the A-prime port, and the FIR kernel recovery with
fsum-normalized taps. Write unit tests alongside each task.

> **`I19` and `I20` are not A1 tasks.** A1 **writes** the tests; `A2` **runs** them. The
> superseded phrase "tasks `I01`–`I20`" contradicted those tasks' own `lifecycle_stage` of
> `A2` in the task graph. Corrected by the final authority repair pass.

> **Why two III-B tasks live in A1.** `IB02` supplies the `q`-generalized path and
> qualification primitive that **III-A gate 12** is defined in terms of; `IB03` is the
> bit-identity regression fixture that stops a `q`-generalization defect from silently altering
> the III-A cohort at the moment that gate is evaluated. They are **implementation** tasks, not
> III-B **runtime stages**, so the §17.2 invariant is untouched: no `B-*` stage and no III-B
> artifact is a precondition of anything in III-A.

**Entrypoints.** New modules under `src/mineocclude/experiment_iii/` and
`scripts/experiment_iii/`; bounded Fabric-mod edits for wall material and scene (§8, C05–C08).
**Unit of work.** One task-graph task.
**Expected counts.** 20 tasks (`I01`–`I18` + `IB02` + `IB03`); 32 change-matrix items; **12**
qualification gates; 25 + 2 identities; 2 FIR kernels.
**Outputs.** Source modules; cohort artifacts (§2.7); `aprime_port_receipt.json`;
`fir_kernel_recovery_receipt.json`; unit tests.
**Evidence.** `implementation_completion_receipt.json` naming, per change-matrix item, its
decision, files changed, tests added, and test result.

**PASS.** Every change-matrix item `COMPLETE` with its named tests passing; `IB02` and `IB03`
green **before** `I02` ran; the cohort manifests exist, hash correctly, and satisfy **all twelve**
gates of §2.4 with gate 12 evaluated **before** materialization and freeze; the FIR recovery
satisfies every gate of §5.3 on fsum-normalized taps.
**FAIL.** Any item incomplete; any cohort gate failure; the all-`q` primitive missing at `I02`;
FIR recovery failure.
**Blockers.** `SOURCE_CHANGE_INCOMPLETE`, `COHORT_QUALIFICATION_INFEASIBLE`,
`COHORT_ALL_Q_QUALIFICATION_INFEASIBLE`, `COHORT_ALL_Q_PRIMITIVE_MISSING`,
`COHORT_RNG_STREAM_DRIFT`, `COHORT_SPEED_VIOLATION`, `COHORT_SEED_COLLISION`,
`FIR_KERNEL_RECOVERY_FAILED`, `FIR_KERNEL_NOT_NORMALIZED`, `APRIME_PORT_SOURCE_UNAVAILABLE`.
**Allowed repairs.** Any code repair; regenerate the cohort **only while no capture exists**.
**Forbidden repairs.** Changing any frozen scientific value; loosening a qualification gate to
admit a stubborn candidate; **materializing the cohort without evaluating gate 12**;
**regenerating the cohort on the basis of any outcome**; refitting the FIR from Experiment III
data.
**Retry.** Unlimited.
**Resume.** Per task; completed tasks with passing tests are not redone.
**Invalidation scope.** Regenerating the cohort invalidates only A1 artifacts if no capture
exists. Once any capture exists, cohort regeneration is forbidden and is a §9 amendment.
**Exit.** `implementation_completion_receipt.json` PASS.
**Next.** `A2`.

---

### A2 — STATIC_VALIDATION

**Purpose.** Prove the implementation correct on CPU, with no Minecraft and no model.

**Entry.** A1 PASS.
**Inputs.** Source tree; `EXPERIMENT_III_TEST_PLAN.md`; frozen fixtures.
**Operations.** Run test-plan groups **A** (static unit), **B** (CPU integration) **and D**
(III-B static and CPU) in full. All three are CPU-only, with no Minecraft and no model.

> **Group-D stage binding.** Group D is a III-B suite but runs **here, at A2**, alongside A and
> B. Three of its checks — `D.2`, `D.4` and `D.31` — guard the **III-A** cohort and are
> *additionally* `A1` task-completion gates, run before `I02` materializes anything. Running
> them twice is deliberate. A failure in any **other** group-D check is a III-B blocker only:
> III-A closes unaffected and III-B proceeds toward `CLEAN_SKIP` if it cannot be repaired in
> time.

**Entrypoint.** `pytest tests/experiment_iii/`.
**Unit of work.** One test.
**Expected counts.** All **30** group-A, **12** group-B and **33** group-D checks pass — **75**
named checks; zero group-A skips; zero group-D skips.
**Outputs.** Test report.
**Evidence.** `static_validation_receipt.json` with per-test outcome, test-suite hash, and the
source closure it ran against.

**PASS.** Zero failures, zero errors, zero group-A skips, zero group-D skips; source closure
recorded.
**FAIL.** Any failure, error, group-A skip, or group-D skip.
**Blockers.** `SOURCE_STATIC_TEST_FAILURE`, `SOURCE_CLOSURE_DRIFT`.

**Deadline checkpoints read this stage.** `A2 == PASS` is the input to the derived
implementation checkpoints **CP1 / CP2 / CP3** (§10.5) at Tue 2026-09-01 13:00, Tue 20:36 and
Wed 2026-09-02 00:48 — the earliest observable signal that implementation is overrunning. Each
instant is *deadline minus that plan's conservative post-`A2` tail*.
**Allowed repairs.** Fix code or fixtures; rerun.
**Forbidden repairs.** Deleting, skipping, or weakening a test to make it pass; marking a
failing scientific fixture `xfail`.
**Retry.** Unlimited.
**Resume.** Rerun the full suite; a partial suite run is not evidence.
**Invalidation scope.** Any source change invalidates this receipt.
**Exit.** All tests pass at the recorded source closure.
**Next.** `A3`.

---

### A3 — ENVIRONMENT_PREFLIGHT

**Purpose.** Prove the execution host can actually run the experiment before anything expensive
starts.

**Entry.** A2 PASS.
**Inputs.** Host; Minecraft/Fabric build; MineWorld checkpoint and VAE; storage; durable store.
**Operations.** Verify and record: OS, Python, NumPy, torch, CUDA, GPU model and memory;
Minecraft 1.16.5, Fabric `0.15.11`, Fabric API `0.42.0+1.16`, Yarn `1.16.5+build.10`; mod jar
hash; client framebuffer exactly 640 × 360; display availability; MineWorld checkpoint SHA-256
`a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5`; VAE SHA-256
`370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab`; preprocessing identity;
action-conversion identity; **the device/volume id of every gated path**, the durability mode,
and whether a local mirror is enabled; **free bytes against the combined-program storage gate
of §13.2**; durable-store write/read-back round trip; the RNG stream fixture.
**Entrypoint.** `scripts/experiment_iii/preflight.py`.
**Unit of work.** One preflight check.
**Expected counts.** Every check present and PASS.
**Outputs.** `environment_receipt.json`, naming which stages this host is authorized to run.

**PASS.** All pins match; **`POOL_WORKING` free bytes `>= 64 GiB` with a local durability
mirror, or `>= 40 GiB` without** (§13.2 — the **combined-program** gate, because III-B is
prospectively authorized and `A3` always precedes the III-B launch gate); every gated path's
device id recorded and **no pool double counted**; the durability mode recorded; durable round
trip verified; GPU present and sufficient for A9.
**FAIL.** Any pin mismatch, insufficient resource, or a gate satisfied only by counting one
filesystem twice.
**Blockers.** `ENV_CHECKPOINT_HASH_MISMATCH`, `ENV_VAE_HASH_MISMATCH`,
`ENV_RUNTIME_VERSION_MISMATCH`, `ENV_FRAMEBUFFER_SIZE_MISMATCH`, `ENV_GPU_UNAVAILABLE`,
`ENV_DISPLAY_UNAVAILABLE`, `ENV_PREPROCESSING_IDENTITY_MISMATCH`, `STORAGE_INSUFFICIENT`,
`STORAGE_POOL_DOUBLE_COUNTED`, `DURABILITY_STORE_UNREACHABLE`.

**Multi-host note.** Extraction (A9) requires a GPU host; capture (A4/A5/A7) requires a
display-capable client host. A3 must be run **on every host that will execute a stage**, and
each receipt records which stages it authorizes. The authority-construction host has no local
torch and 93 GiB free; it authorizes CPU stages only, and its 93 GiB comfortably clears the
64 GiB mirrored combined-program gate.

**Allowed repairs.** Fix the environment; free disk; re-pin versions; rerun.
**Forbidden repairs.** Proceeding with a mismatched checkpoint or VAE; lowering the disk
threshold; substituting a different checkpoint; **treating two logical categories that resolve
to one filesystem as two independent free-space pools**; **comparing decimal-GB free space
against a binary-GiB threshold**.
**Retry.** Unlimited.
**Resume.** Rerun the full preflight.
**Invalidation scope.** Any environment change invalidates this receipt and every later receipt
bound to it.
**Exit.** `environment_receipt.json` PASS for the stages this host will run.
**Next.** `A4`.

---

### A4 — P0_VISIBILITY_CALIBRATION

**Purpose.** Select L1/L2/L3 by an outcome-blind, image-only measurement, **before** any
Experiment III model inference.

**Entry.** A2 PASS; A3 PASS on the capture host; `P0_AUTHORIZED = true`.
**Inputs.** §7 in full; the 12-candidate roster; L0 and stone; the frozen placements.
**Operations.** §7.2 – §7.8.
**Entrypoint.** `scripts/experiment_iii/run_p0_rve_calibration.py`.
**Unit of work.** One (condition × placement × replicate block) capture set.
**Expected counts.** 14 conditions × 9 placements × 2 ABBA blocks × 2 states × ≥ 8 settled
frames = **≥ 4,032 settled frames**; 126 (condition, placement) cells; 9 masks.
**Outputs.** The eight P0 artifacts of §7.8.
**Evidence.** `P0_SELECTION_RECEIPT`.

**PASS (`P0_PASS`).** A valid triple exists under every rule of §7.5 and is selected by §7.6.
**FAIL.** `P0_NO_VALID_LADDER` or `P0_TECHNICAL_FAIL` — reported separately per §7.7.
**Blockers.** `P0_TECHNICAL_FAIL`, `P0_NO_VALID_LADDER`, `RVE_MASK_DEGENERATE`,
`RVE_BACKGROUND_TOLERANCE_EXCEEDED`, `RVE_REPLICATE_CV_EXCEEDED`, `RVE_SNR_INSUFFICIENT`,
`RVE_ORDER_UNSTABLE`, `RVE_BOOTSTRAP_LOWER_BOUND_NOT_POSITIVE`, `P0_CANDIDATE_ID_UNSUPPORTED`,
`P0_PLACEMENT_GROSS_ERROR`.
**Allowed repairs.** Fix capture, settling, or lighting defects and re-measure the affected
(condition, placement, block) units under the identical frozen procedure.
**Forbidden repairs.** Widening an RVE zone; lowering a separation, SNR, CV, or background
threshold; adding a candidate outside the 12-block roster; using clear glass, panes, or multiple
layers; re-running until a ladder appears; selecting on anything but RVE and image QA;
per-candidate masks.
**Retry.** Same frozen unit only; all attempts retained.
**Resume.** Per (condition, placement, block); completed verified units are not re-measured.
**Invalidation scope.** A mask change invalidates every candidate at that placement. A candidate
re-measure invalidates only that candidate's placement scores and the selection.
**Exit.** `P0_SELECTION_RECEIPT` with `P0_RESULT = P0_PASS` and a hash-bound selected triple.
**Next.** `A5`.

---

### A5 — P1_ENGINEERING_PILOT

**Purpose.** Prove the whole pipeline end to end on sacrificial identities, so no production
identity is ever spent on debugging.

**Entry.** A4 `P0_PASS`; A3 PASS on capture and extraction hosts; `P1_AUTHORIZED = true`.
**Inputs.** `e3_p90`, `e3_p91`; the P0-selected ladder; the full pipeline.
**Operations.** §6A (the P1 verification list).
**Entrypoint.** `scripts/experiment_iii/run_p1_pilot.py`.
**Unit of work.** One (pilot identity × condition) capture, then one extraction unit.

**Expected counts.**

```
2 pilot identities x 5 conditions  =    10 captures
10 captures x 19 target rows       =   190 target rows
                                   =   190 MineWorld forwards
190 x 3 layers x 2 slices          = 1,140 logical row tensors
10 x 3 layers x 2 slices           =    60 persisted .npy arrays
60 x 26,148,992 bytes              = 1,568,939,520 bytes  (1.4612 GiB)
```

**Outputs.** Pilot captures, activations, features, and a pilot analysis smoke run.
**Evidence.** `p1_pilot_receipt.json` enumerating every verification item with its observed
value.

**PASS.** Every verification item proven; counts exactly as above; a deliberate mid-run kill and
restart demonstrates same-spec resume without recomputing verified units.
**FAIL.** Any verification item unproven or any count mismatch.
**Blockers.** Any `CAPTURE_*`, `WALL_*`, `CAMERA_*`, `TARGET_*`, `TIMING_*`, `FIR_*`,
`EXTRACTION_*`, `HOOK_*`, `TOKEN_*`, `TENSOR_*`, `FEATURE_*` code, plus `P1_INCOMPLETE`,
`P1_RESUME_UNPROVEN`.

**What P1 outputs may be inspected.** Everything technical: shapes, dtypes, hashes, token
positions, frame identities, receipts, timings, resume behavior, and feature values. Pilot
*predictive accuracy* may be inspected **only** to confirm the analysis code runs end to end and
produces finite numbers. Pilot accuracy may never inform any scientific choice.

**P1 may NOT tune.** Materials; RVE rules or thresholds; the cohort; the primary readout; the
alpha grid; representations; estimands; statistical thresholds; analysis families; target rows;
folds.

**Allowed repairs.** Fix the engineering defect, rerun the affected static/P1 test, and repeat
the pilot unit — or the whole pilot if the defect could have affected earlier units.
**Forbidden repairs.** Any scientific redesign; promoting a pilot identity into production;
proceeding to production on a failed pilot.
**Retry.** Unlimited on pilot units.
**Resume.** Per pilot capture/extraction unit.
**Invalidation scope.** A pipeline change invalidates the pilot receipt; re-pilot the affected
span.
**Exit.** `p1_pilot_receipt.json` PASS.
**Next.** `A6`.

---

### A6 — P2_PROSPECTIVE_FREEZE

**Purpose.** The final scientific freeze. After this, nothing scientific may change.

**Entry.** A0–A5 all PASS.
**Operations.** Emit one machine-readable freeze package binding every item below, each by exact
value or hash, and verify each binding against the live artifact.
**Entrypoint.** `scripts/experiment_iii/build_p2_freeze.py`.
**Unit of work.** The freeze package.
**Outputs.** `P2_FREEZE_PACKAGE.json`, `P2_FREEZE_PACKAGE.sha256`.

**The freeze package must bind, at minimum:**

*Authority and code* — `AUTHORITY_SHA256`; machine-authority SHA-256; source closure digest;
HEAD commit; A-prime port receipt; FIR recovery receipt.

*Environment* — OS, Python, NumPy, torch, CUDA, GPU; Minecraft 1.16.5; Fabric `0.15.11`; Fabric
API `0.42.0+1.16`; Yarn `1.16.5+build.10`; mod jar hash; MineWorld checkpoint `a92c311b…`; VAE
`370d06be…`; preprocessing identity; action-conversion identity.

*Cohort* — the 25 production identities with seeds, directions, start positions, path hashes,
noise hashes, 19 target indices, 19 FIR labels, target SD, outer fold, priority rank, spec hash;
the 2 excluded pilots; `folds.json`; `identity_priority_order.json`.

*Conditions and evidence* — the condition schema; the selected `L1`/`L2`/`L3` registry IDs;
`minecraft:stone` for L4; `minecraft:air` for L0; the P0 selection receipt hash; the frozen `V_c`
for all five conditions; the three sentinel placements and the repeatability envelope; the P0
bootstrap seed.

*Apparatus* — layout, camera, wall volume, speed 2.0, `q = 0.05`, `dt = 0.05`, 180 frames,
framebuffer, lighting/weather policy, warm-up policy.

*Measurement* — both direction FIR kernels; extent half-width `0.8727621336620037`;
`samples_per_axis = 5`; the eligibility equation.

*Extraction* — layers `{4,10,19}`; `PREVIOUS` `[4858:5194]`; `CURRENT` `[5205:5541]`; the
excluded action ranges; hook site; sequence length 5552; tensor schema `[19,336,2048]` float16
little-endian; expected byte sizes.

*Analysis* — `COARSE_2X6_CONCAT` and the three representation formulas; the ridge recipe; alpha
grid `{0.1, 1, 10, 100, 1000}`; the four inner rotations; all five baselines; the three primary
estimands; every secondary family; bootstrap `B = 10,000`; the analysis bootstrap seed; the Holm
families; the prediction-lock rule.

*Operations* — capture order and Latin rotation; retry policy; attrition rule; deadline
fallbacks and their clock triggers; every stop rule.

**PASS.** Every binding present, non-null, and verified against the live artifact; the package
hashes; every prerequisite stage receipt is PASS.
**FAIL.** Any missing, null, or unverified binding.
**Blockers.** `P2_BINDING_INCOMPLETE`, `P2_BINDING_MISMATCH`, `P2_PREREQUISITE_NOT_PASSED`.
**Allowed repairs.** Complete a missing binding; correct a mismatch by fixing the artifact, then
re-freeze.
**Forbidden repairs.** Freezing with a placeholder, a null, or a "to be determined"; freezing
before A4 and A5 pass.
**Retry.** Unlimited before production launch.
**Resume.** Rebuild the package.
**Invalidation scope.** Re-freezing after production has begun invalidates every capture bound
to the superseded package — which is precisely why P2 must be complete first.
**Exit.** `P2_FREEZE_PACKAGE.json` verified.

**Only here, and only on this exit, may `PRODUCTION_AUTHORIZED = true` and
`MODEL_INFERENCE_AUTHORIZED = true` be emitted.**

**Next.** `A7`.

---

### A7 — PRODUCTION_CAPTURE

**Purpose.** Capture the frozen 125-unit production matrix.

**Entry.** A6 PASS; `PRODUCTION_AUTHORIZED = true`; A3 PASS on the capture host.
**Operations.** §8.1 – §8.3.
**Entrypoint.** `scripts/experiment_iii/run_production_capture.py`.
**Unit of work.** One **(identity × condition)** capture unit — the atomic unit for retry,
resume, and invalidation.

**Expected counts.**

```
25 identities x 5 conditions = 125 captures
125 x 180 frames             = 22,500 frames
125 x 19 target rows         = 2,375 production target rows
approximately 25 wall material transitions
10 sentinel checks (before and after each of 5 condition batches)
```

**Outputs (per unit).** `raw/server_state.jsonl`, `raw/client_tick.jsonl`, `raw/actions.jsonl`,
`raw/frame_map.jsonl`, `raw/visibility.jsonl`, `raw/frames/000000.png`…`000179.png`,
`coordinates.jsonl`, `wall_receipt.json`, `camera_receipt.json`, `target_receipt.json`,
`condition_receipt.json`, `capture_completion.json`, `durable_receipt.json`.
**Evidence.** `capture_matrix.json`; per-unit completion and durable receipts; sentinel
receipts; the hash-chain ledger.

**PASS (per unit).** Every receipt of §3.3 passes; the 19 frozen target rows are present and
identical to the manifest; the unit is durably published and read back by hash.
**FAIL (per unit).** Any receipt failure — all technical, all defined without model outcomes.
**Blockers.** `CAPTURE_PATH_HASH_MISMATCH`, `CAPTURE_NOISE_MISMATCH`, `CAPTURE_MISSING_FRAME`,
`CAPTURE_MISSING_ACTION`, `CAPTURE_MISSING_STATE`, `TIMING_CARDINALITY_MISMATCH`,
`TIMING_LOCKSTEP_MISMATCH`, `WALL_MATERIAL_MISMATCH`, `WALL_CELL_MISMATCH`,
`WALL_CACHE_KEY_STALE`, `WALL_CONDITION_SCENE_MISMATCH`, `WALL_RECEIPT_MISMATCH`,
`CAMERA_POSE_DRIFT`, `TARGET_IDENTITY_FAILURE`, `TARGET_RESPAWN_DETECTED`,
`TARGET_ROW_MISMATCH`, `CAPTURE_STALE_FRAME`, `CAPTURE_LANE_CLAMP_ENGAGED`,
`CAPTURE_ORDER_VIOLATION`, `SENTINEL_ORDER_VIOLATION`, `SENTINEL_ENVELOPE_VIOLATION`,
`DURABILITY_READBACK_MISMATCH`, `STORAGE_EXHAUSTED`.
**Allowed repairs.** Same-frozen-unit retry (§8.3). Fix an apparatus or software defect and
retry the affected units. Rebuild the arena.
**Forbidden repairs.** Changing seed, path, direction, condition, wall material, target rows,
target labels, camera, timing policy, or scientific identity; replacing an identity; dropping a
condition; imputing a missing cell.
**Retry.** Same frozen unit only; all failed attempts retained with provenance; the **first
technically valid** attempt is kept.
**Resume.** Per capture unit via the ledger: `PLANNED → RUNNING → CAPTURED → VALIDATED →
DURABLE → COMPLETE_VALIDATED_DURABLE`. Units already `COMPLETE` are skipped.
**Invalidation scope.** A sentinel failure invalidates **only** the affected as-yet-unmodeled
capture batch. A per-unit failure invalidates only that unit.
**Exit.** Every planned unit `COMPLETE_VALIDATED_DURABLE`, or the A8 attrition rule is met.
**Next.** `A8`.

---

### A8 — CAPTURE_COHORT_VALIDATION

**Purpose.** Close the cohort and decide, without outcomes, what population the analysis has.

**Entry.** A7 finished or halted.
**Operations.** Build the full identity × condition matrix; identify complete five-way paired
identities; apply the frozen attrition rule.
**Entrypoint.** `scripts/experiment_iii/validate_capture_cohort.py`.
**Unit of work.** The cohort.
**Expected counts.** Normal: 25 complete five-way paired identities; 125 units; 2,375 rows.

**Frozen attrition rule.**

```
complete five-way paired identities >= 25 : normal analysis
complete five-way paired identities in [15, 24] :
        proceed with the prespecified analysis, at reduced precision,
        with conspicuous attrition disclosure in every reported result
complete five-way paired identities < 15 :
        NO graded Experiment III inferential claim
```

The primary population is the **complete five-way paired identity subset** only. Partially
captured identities are excluded whole; their captured conditions are not partially used.

**PASS.** `N_complete >= 15` and the matrix is internally consistent.
**FAIL.** `N_complete < 15`.
**Blockers.** `COHORT_INSUFFICIENT_COMPLETE_IDENTITIES`, `COHORT_MATRIX_INCONSISTENT`,
`COHORT_PILOT_CONTAMINATION`.
**Forbidden.** Missing-cell imputation; reactive condition dropping; outcome-based identity
replacement; mixing historical identities into the cohort; substituting a pilot.
**Allowed repairs.** Return to A7 and retry incomplete units while the deadline allows.
**Retry.** Recompute the closure after further capture.
**Resume.** Recompute from the ledger.
**Invalidation scope.** None backwards; this stage only reads.
**Outputs.** `cohort_closure_receipt.json`, `capture_matrix.json`.
**Exit.** `cohort_closure_receipt.json` with `N_complete` and the selected attrition branch.
**Next.** `A9`.

---

### A9 — ACTIVATION_EXTRACTION

**Purpose.** Produce the frozen activation tensors from exactly one forward per target row.

**Entry.** A8 PASS; A3 PASS on the GPU host; A6 freeze bound;
`MODEL_INFERENCE_AUTHORIZED = true`.
**Operations.** §8.4 – §8.6.
**Entrypoint.** `scripts/experiment_iii/run_extraction.py`.
**Unit of work.** One **(capture unit × layer × temporal slice)** persisted array — the smallest
independently hashable durable artifact. All six arrays of a capture unit derive from the same
19 forwards; the ledger records that shared forward set so a crash never re-runs a completed
capture's forwards.

**Expected counts (normal production).**

```
125 captures
2,375 forwards                    (one per target row; NO extra forward for PREVIOUS or layers)
14,250 logical row tensors        (2,375 x 3 layers x 2 slices)
750 persisted .npy arrays         (125 x 3 x 2)
19,611,744,000 activation bytes   (18.2649 GiB)
```

Independently recomputed from the schema at authority construction; every figure matches Phase 0
exactly.

**PASS.** Every planned array `DURABLE`; every §8.5 validation passes; the forward count is
exactly 2,375.
**FAIL.** Any validation failure or forward-count excess.
**Blockers.** `EXTRACTION_FORWARD_COUNT_EXCESS`, `EXTRACTION_TEMPORAL_INDEX_MISMATCH`,
`HOOK_REGISTRATION_INCOMPLETE`, `HOOK_LAYER_MISSING`, `TOKEN_SPAN_MISMATCH`,
`TOKEN_ACTION_CONTAMINATION`, `TOKEN_FRAME_IDENTITY_MISMATCH`, `TOKEN_CONTEXT_AGE_UNVERIFIED`,
`TOKEN_SEQUENCE_LENGTH_MISMATCH`, `TENSOR_SHAPE_MISMATCH`, `TENSOR_DTYPE_MISMATCH`,
`TENSOR_BYTE_SIZE_MISMATCH`, `TENSOR_NONFINITE`, `TENSOR_HASH_MISMATCH`,
`EXTRACTION_SOURCE_CAPTURE_DRIFT`, `EXTRACTION_SPEC_DRIFT`, `STORAGE_EXHAUSTED`.
**Allowed repairs.** Re-extract an affected unit from the **unchanged** source capture under the
**identical** extraction spec.
**Forbidden repairs.** Re-running with a changed source capture, changed preprocessing, changed
checkpoint, changed token slice, or changed layer set; "fixing" the historical RGB/BGR
preprocessing behavior; adding a forward.
**Retry.** Same spec only.
**Resume.** Per unit; §8.6.
**Invalidation scope.** A source-capture change invalidates every array derived from it. An
extraction-spec change invalidates **all** arrays.
**Exit.** All planned arrays `DURABLE`.
**Next.** `A10`.

---

### A10 — EXTRACTION_VALIDATION

**Purpose.** Independently verify the extraction inventory.

**Entry.** A9 complete.
**Operations.** Recompute the expected inventory from the cohort and the freeze package; compare
against what exists; re-hash every array; verify each array's bound metadata.
**Entrypoint.** `scripts/experiment_iii/validate_extraction.py`.
**Unit of work.** One persisted array.
**Expected counts.** 750 arrays; 14,250 logical row tensors; 19,611,744,000 bytes.

**PASS.** Counts exact; every array finite, non-empty, `[19,336,2048]`, little-endian float16,
exactly 26,148,992 bytes, SHA-256 matching, and bound to the correct identity, condition, layer,
slice, target-row order, hook site, token-position hash, preprocessing identity, and checkpoint
identity.
**FAIL.** Any mismatch.
**Blockers.** `EXTRACTION_INVENTORY_INCOMPLETE`, any `TENSOR_*`, `PROVENANCE_BINDING_MISSING`.

**Note.** The legacy validator at `src/mineocclude/regime_a_execution.py:62-97` hard-codes
`layer_indices == list(range(20))`, `target_tau == list(range(1,20))`, and exactly 20 artifacts.
Experiment III requires 3 layers × 2 slices = 6 arrays per capture. Reused unchanged it fails
closed (correctly) but uselessly; item C20 generalizes it.

**Allowed repairs.** Re-extract the affected unit (A9).
**Forbidden repairs.** Accepting a shape, byte, or hash mismatch; regenerating the inventory to
match whatever happens to exist.
**Exit.** `extraction_validation_receipt.json` PASS.
**Next.** `A11`.

---

### A11 — FEATURE_CONSTRUCTION

**Purpose.** Build the three frozen representations and the pixel-baseline features.

**Entry.** A10 PASS.
**Operations.** §8.7 and §8.9.1.
**Entrypoint.** `scripts/experiment_iii/build_features.py`.
**Unit of work.** One (capture unit × representation) feature block.
**Expected counts.** `CURRENT` and `CURRENT_MINUS_PREVIOUS` at 24,576 features;
`TWO_FRAME_CONCAT` at 49,152; pixel baseline at 4,032. 2,375 rows per representation.

**PASS.** Exact dimensions; finite values; row order equals the frozen target-row order; feature
fixtures (§11.A.20–23) reproduce byte-identically.
**FAIL.** Any dimension, order, or fixture mismatch.
**Blockers.** `FEATURE_DIMENSION_MISMATCH`, `FEATURE_ROW_ORDER_MISMATCH`,
`FEATURE_POOLING_GRID_TRANSPOSED`, `FEATURE_NONFINITE`, `FEATURE_SLICE_SWAPPED`.
**Forbidden repairs.** Changing the pooling grid, the concatenation order, or the feature
dimension; adding a representation; substituting global mean pooling.
**Exit.** `feature_config.json` plus hashed feature blocks.
**Next.** `A12`.

---

### A12 — PREDICTION_LOCK

**Purpose.** Emit and hash-lock every held-out prediction **before** any summary statistic is
computed or viewed.

**Entry.** A11 PASS.
**Operations.** Fit the frozen grouped nested ridge (§8.8) and every baseline (§8.9) on the
frozen folds; emit held-out predictions for every (identity, condition, row, model) cell; hash
and seal them.
**Entrypoint.** `scripts/experiment_iii/lock_predictions.py`.
**Unit of work.** One (outer fold × condition × model) prediction block.

**PASS.** Every cell has exactly one held-out prediction; no identity appears in its own
training set; every scaler and alpha was selected inside the outer training set only; the lock
file is written and hashed **before** any statistic is computed.
**FAIL.** Any missing or duplicate prediction, any leakage, or any statistic computed first.
**Blockers.** `PREDICTION_LOCK_MISSING`, `PREDICTION_LOCK_AFTER_STATISTICS`,
`FOLD_LEAKAGE_DETECTED`, `PREDICTION_DUPLICATE_CELL`, `PREDICTION_NONFINITE`,
`PREDICTION_ALPHA_SELECTED_ON_HELDOUT`.

**This is the irreversible scientific boundary.** After the lock exists, no feature, fold, alpha
grid, representation, baseline, or model may change. Any such change requires a §9 amendment and
a fully re-run, explicitly disclosed analysis.

**Allowed repairs.** Before the lock: fix and re-run. After the lock: nothing except a §9
amendment.
**Retry.** Unlimited before the lock is written.
**Resume.** Per (outer fold × condition × model) block.
**Invalidation scope.** Any feature or fold change invalidates the whole lock.
**Exit.** `PREDICTION_LOCK.json` and `PREDICTION_LOCK.sha256`.
**Next.** `A13`.

---

### A13 — BASELINES_CONTROLS

**Purpose.** Produce the five baselines and the L0 interpretability control.

**Entry.** A12 PASS (baselines are part of the lock).
**Operations.** §8.9; §8.11.
**Unit of work.** One baseline.
**Expected counts.** 5 baselines; 1 L0 control statistic.
**PASS.** All five baselines present with locked predictions; leakage tests pass; the L0 control
statistic is computed from locked predictions.
**FAIL.** Any baseline missing or leaking.
**Blockers.** `BASELINE_MISSING`, `BASELINE_LEAKAGE`, `BASELINE_FORMULA_MISMATCH`,
`BASELINE_ORACLE_USED_AS_MODEL_INPUT`.
**Forbidden repairs.** Feeding last-seen or constant-velocity oracle state into any model
feature; re-tuning a baseline after seeing its result.
**Exit.** `baselines_receipt.json`.
**Next.** `A14`.

---

### A14 — PRIMARY_ANALYSIS

**Purpose.** Compute the three frozen primary estimands. Nothing else.

**Entry.** A12 and A13 PASS.
**Operations.** §8.10.
**Entrypoint.** `scripts/experiment_iii/run_primary_analysis.py`.
**Unit of work.** One estimand.
**Expected counts.** Exactly 3 primary estimands; exactly 3 p-values in the Holm family;
`B = 10,000` whole-identity bootstrap resamples.

**PASS.** All three computed from locked predictions; Holm applied across exactly three;
bootstrap resamples whole identities with all conditions, rows, and representations kept
together; the seed matches the freeze package.
**FAIL.** Any estimand added, removed, or substituted; any row-level resampling.
**Blockers.** `ANALYSIS_FAMILY_ALTERED`, `STATS_MULTIPLICITY_FAMILY_MISMATCH`,
`STATS_BOOTSTRAP_UNIT_VIOLATION`, `STATS_SEED_MISMATCH`, `ANALYSIS_INPUT_NOT_LOCKED`,
`STATS_ZERO_TSS`, `ANALYSIS_SUCCESS_GATE_REINTRODUCED`.
**Forbidden repairs.** Adding an estimand after seeing results; changing the hypothesis
direction; re-running with a different seed; promoting a secondary result to primary.
**Retry.** Only to repair a mechanical defect, from the same locked predictions and seed.
**Resume.** Recompute from the lock; the lock is never regenerated.
**Invalidation scope.** None backwards.
**Exit.** `primary_results.json`.
**Next.** `A15`.

---

### A15 — TEMPORAL_ANALYSIS

**Purpose.** The two predeclared temporal-rescue contrasts.

**Entry.** A14 complete.
**Operations.** §8.12.B.
**Unit of work.** One contrast.
**Expected counts.** Exactly 2 contrasts; Holm across exactly those 2.
**PASS.** Both computed from locked predictions; Holm-2 applied; identity-bootstrap intervals
reported.
**FAIL.** A contrast added, removed, or substituted.
**Blockers.** `ANALYSIS_FAMILY_ALTERED`, `STATS_MULTIPLICITY_FAMILY_MISMATCH`.
**Forbidden.** Letting a temporal representation replace or rescue the primary readout.
**Allowed repairs.** Mechanical defect repair from the same locked predictions.
**Retry.** From the lock only.
**Resume.** Recompute from the lock.
**Invalidation scope.** None backwards.
**Exit.** `temporal_results.json`.
**Next.** `A16`.

---

### A16 — CONTEXT_AGE_ANALYSIS

**Purpose.** The descriptive context-age boundary evidence.

**Entry.** A14 complete.
**Operations.** §8.12.C.
**Unit of work.** One age bin or the single boundary interaction.
**Expected counts.** Four age bins `1–5`, `6–10`, `11–15`, `16–19`; exactly one prespecified
boundary interaction.
**PASS.** Bins exactly as frozen; the interaction computed exactly as §8.12.C; the
frame-identity verification of §5.4 passed at extraction.
**FAIL.** Re-binned, or the frame-identity verification never ran.
**Blockers.** `ANALYSIS_CONTEXT_BIN_MISMATCH`, `TOKEN_CONTEXT_AGE_UNVERIFIED`.
**Forbidden.** Any causal-forgetting claim; re-binning after seeing results.
**Allowed repairs.** Mechanical defect repair from the same locked predictions.
**Retry.** From the lock only.
**Resume.** Recompute from the lock.
**Invalidation scope.** None backwards.
**Exit.** `context_age_results.json`.
**Next.** `A17`.

---

### A17 — STATISTICAL_ADJUDICATION

**Purpose.** Map computed results onto the **pre-registered** adjudication matrix (§14) and fix
the permitted wording.

**Entry.** A14–A16 complete.
**Operations.** For each §14 outcome row that obtains, record permitted interpretation,
prohibited interpretation, paper value, scientific usability, and whether Experiment III can
close.
**Unit of work.** One adjudication row.
**Expected counts.** Every obtaining row of the 17-row matrix adjudicated.
**PASS.** Every reported claim maps to a permitted interpretation of a §14 row; no claim appears
that §1.7 prohibits.
**FAIL.** A claim with no matching row, or a prohibited claim.
**Blockers.** `ANALYSIS_CLAIM_OUT_OF_SCOPE`, `ANALYSIS_ADJUDICATION_MISSING`.
**Forbidden.** Writing a new adjudication row after seeing results.
**Allowed repairs.** Rewording a claim to fall inside a permitted interpretation.
**Retry.** Unlimited; the underlying numbers never change.
**Resume.** Recompute from the results files.
**Invalidation scope.** None backwards.
**Exit.** `adjudication_receipt.json`.
**Next.** `A18`.

---

### A18 — SCIENTIFIC_PACKAGE

**Purpose.** Assemble the terminal evidence package.

**Entry.** A17 PASS.
**Operations.** §15.
**Unit of work.** One package artifact.
**Expected counts.** Every row of the §15.1 inventory present.
**PASS.** Every item of §15 present, hashed, and internally consistent; every figure and table
traceable to a locked prediction or a receipt.
**FAIL.** Any missing artifact, hash mismatch, or untraceable figure.
**Blockers.** `PACKAGE_ARTIFACT_MISSING`, `PACKAGE_HASH_MISMATCH`,
`PACKAGE_FIGURE_UNTRACEABLE`.
**Allowed repairs.** Regenerate a figure or table from locked predictions; supply a missing
receipt.
**Forbidden repairs.** Producing a figure from anything other than locked predictions or
receipts.
**Retry.** Unlimited.
**Resume.** Per package artifact.
**Invalidation scope.** None backwards.
**Exit.** `scientific_package_manifest.json`.
**Next.** `A19`.

---

### A19 — FINAL_CLOSURE

**Purpose.** Declare Experiment III scientifically complete.

**Entry.** A18 PASS.
**Operations.** Evaluate the eight closure conditions; emit the closure receipt and summary.
**Unit of work.** The experiment.

**`EXPERIMENT_III_COMPLETE = true` may be emitted if and only if all of:**

1. A0–A18 each have a PASS receipt bound to the same `AUTHORITY_SHA256`.
2. `P2_FREEZE_PACKAGE.json` verifies against every downstream artifact.
3. The cohort closure records `N_complete >= 15` and names its attrition branch — **or** the run
   terminates under §14 row 16/17 or §10.4 with an explicit, disclosed no-claim closure.
4. `PREDICTION_LOCK.json` was written before any statistic, and every reported number derives
   from it.
5. The three primary estimands, the secondary families, and the L0 control are reported with
   their frozen multiplicity and intervals.
6. Every claim maps to a permitted interpretation in §14, and no prohibited claim appears.
7. The scientific package (§15) is complete and hash-consistent.
8. All open blockers are either resolved or explicitly disclosed as unresolved limitations.

**FAIL.** Any condition unmet.
**Blockers.** `CLOSURE_CONDITION_UNMET`, `PROVENANCE_AUTHORITY_DRIFT`.
**Forbidden.** Declaring completion on the basis of a favorable result; withholding closure on
the basis of an unfavorable one.

**A closure that reports a null, negative, attrited, apparatus-limited, or `NO_VALID_LADDER`
outcome is a valid closure.** Completion is defined by execution integrity, never by the
direction of the result.

**Outputs.** `EXPERIMENT_III_CLOSURE_RECEIPT.json`, `FINAL_SCIENTIFIC_SUMMARY.md`.
**Next.** none — terminal.

---

## 6A. P1 engineering-pilot verification list

P1 must verify, end to end, and record the observed value of each:

**Apparatus and condition** — material switching across all five conditions; arena cache
invalidation on every material change; exact block receipts for each condition; `L0` reaching
scene `NO_WALL`; camera pose and lock; target identity, flags, and zero respawns.

**Motion and labels** — path replay to `1e-9`; noise replay by hash; direction-specific FIR
labels reproduced from the frozen kernels; counterfactual target semantics identical across all
five conditions; the same 19 target indices in all five; frame/action/tick timing lockstep at
180 frames.

**Model path** — preprocessing identity; MineWorld sequence construction; hook registration
completeness; layers `{4,10,19}` present; `PREVIOUS` and `CURRENT` slices numerically and
semantically correct; token-position map equality; frame-identity verification for context age.

**Storage** — tensor shape `[19,336,2048]`; dtype little-endian float16; byte size 26,148,992;
serialization; SHA-256; durable publish and read-back.

**Analysis path** — feature building; coarse pooling dimension 24,576; temporal feature formulas
(24,576 and 49,152); pixel baseline dimension 4,032; analysis ingestion produces finite numbers.

**Recovery** — a deliberate mid-run kill and restart resumes on the same spec, skips completed
verified units, and recomputes nothing that was already `DURABLE`.

---

## 7. A4 — P0 Robust Visual Evidence calibration

P0 is a bounded, image-only calibration conducted **before any Experiment III MineWorld
inference**. It may select materials. It may **not** read activations, decoder errors, pilot
scientific outcomes, or historical material-performance outcomes.

### 7.1 Inputs and prohibitions

P0 uses **raw rendered source-RGB frames only**, at 640 × 360, decoded as RGB. It must not use
model-normalized tensors and must not couple to the model preprocessing path (which performs its
own OpenCV channel conversion and resize at
`src/mineocclude/models/_mineworld_adapter_wave2.py:408-473`).

### 7.2 Capture protocol

| Parameter | Frozen value |
|---|---|
| Placements | **9**, frozen, spanning the target corridor; coordinates frozen by A1 and bound in P2 |
| Conditions measured | L0 (no wall) + all **12** candidates + `minecraft:stone` = **14** |
| Replicate structure | **2 ABBA blocks** per (condition, placement) |
| States | sheep **present** (`P`) and sheep **absent** (`A`, `Scene.NO_SHEEP`) |
| Frames per state per block | **≥ 8 settled** |
| Warm-up | frozen warm-up ticks before any capture; remesh settling after every arena rebuild |
| Lighting / weather | fixed noon, weather controlled, **zero random ticks** |
| Camera | fixed at §3.1; camera lock active |
| Framebuffer | exactly 640 × 360; framebuffer hash recorded per frame |
| Staleness | byte-identical consecutive frames beyond the frozen tolerance invalidate the block |

The sheep is placed statically at each placement; the target is the same adult, AI-disabled,
silent, persistent, invulnerable magenta sheep as production.

The **ABBA order is load-bearing**: it balances any monotone drift in client state across the
present/absent contrast within a block. Blocks are `P A A P` and `A P P A` respectively, and the
realized order is recorded per frame.

### 7.3 Robust Visual Evidence — exact definition

Let `P(c,p,b)` and `A(c,p,b)` be settled 640 × 360 **source-RGB** frames for condition or
candidate `c`, placement `p`, and replicate block `b`, with the sheep present and absent.

**Step 1 — linearization.** Convert each 8-bit sRGB channel to linear light:

```
s = v / 255                                    for v in {0..255}
linear(s) = s / 12.92                          if s <= 0.04045
linear(s) = ((s + 0.055) / 1.055) ** 2.4       otherwise
```

Computation is in float64.

**Step 2 — robust images.** Take the **coordinate-wise median** over the settled frames of a
state within a block, giving `P_lin(c,p,b,·)` and `A_lin(c,p,b,·)`.

**Step 3 — support mask.** Derive one outcome-independent sheep support mask `M_p` per
placement, **once**, from the **L0** present-minus-absent residual:

```
r(u)   = || P_lin(L0,p,b,u) - A_lin(L0,p,b,u) ||_2^2
M_p^b  = { u : r(u) > L0_noise_threshold_p }
M_p    = dilate( union over blocks b of M_p^b , 2 pixels )
```

`L0_noise_threshold_p` is derived from the absent-frame split-half noise at that placement and
frozen by A1. **The same `M_p` is used for every candidate** — a per-candidate mask would make
the metric material-dependent and is forbidden.

The authoritative projected sheep center may gate gross placement errors, and the magenta
detector may verify target presence, but **neither defines residual magnitude or candidate
ordering**.

**Step 4 — evidence energy.**

```
D(c,p,b) = sum over u in M_p of || P_lin(c,p,b,u) - A_lin(c,p,b,u) ||_2^2
```

**Step 5 — noise floor.** `N(c,p,b)` is the same energy computed from a **deterministic
split-half comparison of the repeated absent frames** of the same `(c,p,b)`: partition the
settled absent frames into two halves by ascending capture index (first half / second half),
take the coordinate-wise median of each half, and evaluate the same masked squared-residual
energy between them.

**Step 6 — excess energy and normalization.**

```
E(c,p,b)   = max( D(c,p,b) - N(c,p,b), 0 )
RVE(c,p,b) = E(c,p,b) / E(L0,p,b)
```

**Step 7 — aggregation.**

```
placement score       RVE(c,p) = median over replicate blocks b
condition score V_c            = median over the 9 placements
```

`L0` is defined as `V_0 = 1`. **`L4` is measured, not forced to zero**; its measured `V_4` is
reported and used as the L4 evidence coordinate. Uncapped values are retained for QA.

**Step 8 — background gate.** The present/absent residual **outside** `M_p` must not exceed the
Phase-1-frozen background tolerance; exceeding it is `RVE_BACKGROUND_TOLERANCE_EXCEEDED` and
invalidates that block.

### 7.4 What RVE is and is not

RVE measures **the image perturbation attributable to inserting the sheep into a matched
rendered scene**. It does **not** claim silhouette recovery, perceptual equivalence, posterior
variance, principled observation noise, or pure opacity.

**RVE measures source-rendered visual evidence, not the model's perceptual metric.** The frames
it consumes are the **source RGB** output of the Minecraft client. The historical MineWorld
preprocessing path is documented as **BGR**-ordered. That ordering does **not** change the RVE
number — the masked squared residual sums squared per-channel differences and is invariant to
any permutation of the channel axis — but it does mean RVE and the model's own front end need
not weight a scene identically.

Consequently the ladder `L1 > L2 > L3` is ordered by **source visual evidence**, and the
evidence coordinate `O_c` is an **apparatus-side** measurement of scene degradation, not a
measurement of what the model perceives. Every claim must be phrased over the source evidence
coordinate. This is a disclosure requirement for the manuscript; **RVE is not redesigned**, and
the preprocessing identity is still verified independently at `A3` and bound at `P2`.

Linear RGB is used instead of Lab ΔE because squared radiometric residual has a direct energy
interpretation, requires no new color-science dependency, and supports an explicit absent-frame
noise subtraction. The ABBA sequence, medians, fixed camera, zero random ticks, fixed
noon/weather, warm-up, framebuffer hashing, and the outside-mask residual gate together control
remeshing, antialiasing, and client timing artifacts.

### 7.5 Ladder validity rules (all must hold)

A valid ladder is three **distinct** eligible blocks ordered `L1 > L2 > L3` satisfying **all** of:

| Rule | Threshold |
|---|---|
| L1 median RVE | in `[0.60, 0.85]` |
| L2 median RVE | in `[0.30, 0.55]` |
| L3 median RVE | in `[0.08, 0.25]` |
| Adjacent median separation | `>= 0.12` for both adjacent pairs |
| Strict order stability | the same strict order at **at least 8 of 9** placements |
| Bootstrap | deterministic **10,000**-resample placement bootstrap lower bound **strictly above zero** for **both** adjacent differences |
| L3 SNR | excess-energy-to-noise ratio `E/N >= 5` at **at least 8** placements |
| Replicate repeatability | within-placement replicate coefficient of variation `<= 0.15` wherever the mean is nonzero |
| Background | outside-mask present/absent residual `<=` the Phase-1-frozen background tolerance |

The bootstrap resamples the **9 placements** with replacement, `B = 10,000`, using the
Phase-1-frozen P0 bootstrap seed bound in P2.

**These zones are engineering design constraints, not scientific success criteria.** They exist
to obtain a well-separated evidence ladder, not to predict or gate a result.

### 7.6 Deterministic selection rule

Among all valid triples drawn from the 12-candidate roster:

1. Compute squared distance to the target RVE points **`(0.725, 0.425, 0.165)`** for
   `(L1, L2, L3)`.
2. Choose the minimizing triple.
3. **Tie-break:** lexicographically earliest triple by candidate registry ID (ordinary string
   order over the `minecraft:*` IDs, compared position by position L1, then L2, then L3).

The search over triples is deterministic and exhaustive. All candidate scores, failures, masks,
images, code hash, and the selected triple are retained — including candidates that failed.

### 7.7 P0 outcomes — three distinct states

| Outcome | Meaning | Consequence |
|---|---|---|
| `P0_PASS` | a valid ladder exists and was selected | proceed to A5 |
| `P0_NO_VALID_LADDER` | measurement clean, **no** triple satisfies §7.5 | `PRODUCTION_AUTHORIZED = false`; Experiment III stops; return to authority adjudication; **do not** substitute another geometry or material family |
| `P0_TECHNICAL_FAIL` | the measurement itself is untrustworthy (mask, noise, background, replicate, capture, or QA failure) | technical retry of the affected units is permitted; this is **not** a scientific result |

These three must be reported separately. Collapsing `NO_VALID_LADDER` into `TECHNICAL_FAIL`, or
the reverse, is a reporting violation.

### 7.8 Required P0 artifacts

| Artifact | Content |
|---|---|
| `P0_MANIFEST` | placements, candidate roster, ABBA order, frame counts, warm-up, lighting policy, code hash, bootstrap seed, thresholds |
| `P0_IMAGE_INVENTORY` | every captured frame with placement, condition, block, state, ordinal, framebuffer hash, SHA-256 |
| `P0_RVE_TABLE` | `D`, `N`, `E`, `RVE` per (condition, placement, block); placement medians; condition medians; uncapped values retained |
| `P0_BOOTSTRAP_RESULTS` | per-triple adjacent-difference bootstrap distributions and lower bounds |
| `P0_MASK_INVENTORY` | per-placement mask, its pixel count, threshold, dilation, and hash |
| `P0_SELECTED_LADDER` | the selected `L1`/`L2`/`L3` registry IDs and their `V_c` |
| `P0_SELECTION_RECEIPT` | `P0_RESULT`; every rule evaluated per triple with pass/fail; the distance ranking; the tie-break applied |
| `P0_SENTINEL_ENVELOPE` | the three sentinel placements and their frozen repeatability envelope (§7.9) |

The frozen `V_c` for all five conditions (`V_0 = 1`; `V_1`, `V_2`, `V_3`, `V_4` measured) is
bound in P2 and is the **only** evidence coordinate used by the analysis (§8.10).

### 7.9 Production drift sentinels

Before **and** after each production condition batch, repeat **three frozen sentinel
placements** — a fixed subset of the nine P0 placements, frozen by A1 and bound in P2.

Requirements:

- The image-only RVE order across the sentinel placements must match P0.
- Each sentinel score must lie inside the Phase-1-frozen **repeatability envelope**, derived from
  the P0 replicate spread at those placements and bound in P2.

A sentinel failure:

- is **technical**, never scientific;
- invalidates **only the affected, as-yet-unmodeled capture batch**;
- permits an **exact technical retry** of that batch;
- **cannot** change materials, target rows, the RVE definition, or any statistic.

Evidence: `sentinel_receipt.json` per batch boundary, recording placement, condition, measured
RVE, envelope bounds, order check, and pass/fail. Blockers: `SENTINEL_ORDER_VIOLATION`,
`SENTINEL_ENVELOPE_VIOLATION`.

---

## 8. Production, extraction, and analysis authority

### 8.1 Production capture matrix and order

```
25 identities x 5 conditions = 125 production captures
each capture: 180 frames, 19 frozen target rows
total: 2,375 production target rows
```

**Frozen capture order.** Five **blocks of five identities**. Within each block, all five
identities are captured under one condition before the material is switched. Condition order
follows a **balanced five-period Latin rotation** across blocks. Identity order within a
condition block is frozen.

Blocks partition the 25 identities by outer fold (block `k` = outer fold `k`), and identity order
inside a block is ascending `priority_rank`. The Latin square is the cyclic square:

```
                condition period
              1    2    3    4    5
block 0:     L0   L1   L2   L3   L4
block 1:     L1   L2   L3   L4   L0
block 2:     L2   L3   L4   L0   L1
block 3:     L3   L4   L0   L1   L2
block 4:     L4   L0   L1   L2   L3
```

Each condition appears exactly once per block and exactly once per period, balancing time and
order effects against condition. Execution proceeds block 0 period 1 … block 0 period 5, then
block 1 period 1, and so on. This yields **25 condition batches and therefore at most 25 wall
material transitions**, minimizing expensive rebuilds while preserving the frozen balancing
design.

Wall switching is minimized **only** by this frozen design. Reordering captures at runtime to
avoid a rebuild is forbidden and is `CAPTURE_ORDER_VIOLATION`.

**Sentinels.** Three frozen RVE sentinel placements are measured **before and after each
condition batch** (§7.9).

**Material transitions.** Every material transition **must** force an arena rebuild and a
complete observed block receipt. The arena-cache key **must** include `condition_id` and
`wall_block_id`.

The current cache key is
`layoutId | scene | wallOrtho | orthoMin | orthoMax | markerGeomSignature`
(`EpisodeManager.java:1138-1150`) — it **omits material**. Left unchanged, a stone→glass switch
would hit the cache and leave the **previous wall standing**, silently producing a whole batch of
captures under the wrong condition with no error. This is the single highest-severity latent
defect in the apparatus. Change-matrix item C07 fixes the key; the wall receipt (§3.3) is the
independent fail-closed guard; blocker `WALL_CACHE_KEY_STALE`.

**Warm-up gate.** A capture may begin only after the standard warm-up, remesh settling, camera
lock, exact target retention, and no-stale-frame checks all pass.

### 8.2 Production unit binding and file inventory

A complete production unit must bind: identity; condition; seed; direction; path hash; noise
hash; episode ID; wall receipt; camera receipt; target UUID and state flags; state stream; action
stream; tick stream; frame stream; temporal alignment; target map; counterfactual extent per row;
FIR labels; the 19 target indices; capture provenance (authority hash, source closure, freeze
package hash, attempt ordinal); and the SHA-256 of every file.

**Deterministic episode naming.**

```
episode_id      = 86001 + priority_rank                 (production; rank 0..24)
                  86901 / 86902                         (pilots)
capture_unit_id = f"{identity}__{condition_id}"         e.g. e3_t07__L2
episode_dir     = f"episode_{episode_id}_{condition_id}"
```

Every capture unit of one identity shares that identity's `episode_id` and is disambiguated by
`condition_id`, so a unit is addressable by `(episode_id, condition_id)` alone.

**Required file inventory per unit** (all required before the unit may be declared `VALIDATED`):

```
raw/server_state.jsonl        180 rows
raw/client_tick.jsonl         180 rows
raw/actions.jsonl             180 rows
raw/frame_map.jsonl           180 rows
raw/visibility.jsonl          180 rows   (with the §4.4 field schema)
raw/frames/000000.png ... 000179.png     180 files, 640x360 RGB
coordinates.jsonl             180 rows
wall_receipt.json
camera_receipt.json
target_receipt.json
condition_receipt.json
capture_completion.json
durable_receipt.json          (required before COMPLETE_VALIDATED_DURABLE)
```

### 8.3 Capture failure and retry semantics

**Technical failures**, all defined without any model outcome: path or hash mismatch; noise
mismatch; missing frame, action, or state; timing mismatch; wrong wall material; wrong wall
cells; camera drift; target identity failure; target respawn; target-row mismatch; stale capture;
RVE sentinel failure; lane clamp engaged; durability failure.

**Only SAME FROZEN UNIT retries are permitted.** A retry may not change: seed; path; direction;
condition; wall material; target rows; target labels; camera; timing policy; or scientific
identity.

- All failed-attempt provenance is retained under `attempts/<ordinal>/` with its failure
  classification and receipts.
- The **first technically valid attempt** is the kept unit. A later attempt does not replace an
  earlier valid one.
- **No identity replacement after scientific outcomes exist.** No identity replacement at all
  once production capture has begun.
- Retries are bounded per unit by a frozen attempt cap recorded in P2; exceeding it marks the
  unit `FAILED_TECHNICAL` and hands the decision to the A8 attrition rule. It never triggers a
  substitution.

### 8.4 MineWorld extraction authority

**Frozen model path.**

| Item | Frozen value |
|---|---|
| Model | MineWorld `700M_16f`, frozen |
| Main checkpoint SHA-256 | `a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5` |
| VAE SHA-256 | `370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab` |
| Adapter, action conversion, preprocessing | unchanged historical bytes; hash-bound |
| Source frame | opened as **RGB** and passed through the already-bound preprocessing path |

Experiment III does **not** "fix" or reinterpret the historical RGB/BGR channel-order behavior.
All conditions use identical code and the exact preprocessing identity is hash-bound. RVE (§7)
is computed from **source RGB frames**, never from model-normalized tensors.

**One forward per target row.**

```
context      = 16 complete visual/action pairs for model frames [t-15, ..., t]
per pair     = 336 visual tokens then 11 action tokens = 347 tokens
sequence     = 16 x 347 = 5,552 tokens
hooked shape = [1, 5552, 2048] at every decoder layer
```

**Selected layers:** `4`, `10`, `19`. The hook manager may transiently register and validate all
20 decoder layers (`src/mineocclude/activations/hooks.py:419-528` requires exactly 20 handles),
but **only** layers `{4,10,19}` are serialized.

**Frozen temporal slices.**

| Slice | Pair ordinal | Inclusive positions | Python slice | Shape per selected layer |
|---|---:|---:|---:|---|
| `PREVIOUS` | 14 | 4,858 – 5,193 | `[4858:5194]` | `[1, 336, 2048]` |
| `CURRENT`  | 15 | 5,205 – 5,540 | `[5205:5541]` | `[1, 336, 2048]` |

**Excluded action tokens.** Pair-14 action tokens occupy positions **5,194 – 5,204** and are
excluded. Pair-15 action tokens occupy **5,541 – 5,551** and are excluded.

This arithmetic follows directly from the enforced span contract
(`src/mineocclude/models/mineworld_adapter.py:626-701`), where
`expected_start = pair_index * 347`, visual = `[expected_start, expected_start + 336)`, action =
`[expected_start + 336, expected_start + 347)`. Verified at authority construction:
`14 × 347 = 4858`, `15 × 347 = 5205`, `16 × 347 = 5552`.

Decoder causality means the pair-14 residual cannot attend to pair 15, even though both are
harvested after the same teacher-forced call. **No extra model forward is authorized** for
`PREVIOUS` or for multiple layers. Production is exactly **2,375** forwards; any excess is
`EXTRACTION_FORWARD_COUNT_EXCESS`.

**Semantic fixtures are mandatory.** Shape agreement is **not** sufficient evidence that a slice
is the intended frame. Extraction must assert, per forward:

1. `spans[-1].pair_index == 15` and `spans[-2].pair_index == 14`;
2. `spans[-1].visual_positions == tuple(range(5205, 5541))` and
   `spans[-2].visual_positions == tuple(range(4858, 5194))`;
3. `spans[-1].identity.model_frame_idx == t` and `spans[-2].identity.model_frame_idx == t - 1`
   — the **frame identity**, not merely the ordinal;
4. the full `FrameTokenMap` covers `range(5552)` exactly, with no duplicate or missing position
   (`src/mineocclude/activations/pool.py:303-383` already enforces this and must be invoked);
5. selected visual positions are disjoint from every action position.

Failures map to `TOKEN_SPAN_MISMATCH`, `TOKEN_FRAME_IDENTITY_MISMATCH`,
`TOKEN_ACTION_CONTAMINATION`, `TOKEN_SEQUENCE_LENGTH_MISMATCH`.

### 8.5 Activation storage and validation

For each **capture × layer × temporal slice**, persist exactly one array:

```
shape  [19, 336, 2048]
dtype  float16, little-endian ("<f2")
```

**Exact byte arithmetic** (independently recomputed at authority construction):

```
one logical row tensor  [336, 2048] float16 = 336 x 2048 x 2 = 1,376,256 bytes
one persisted .npy      19 x 1,376,256 + 128-byte NumPy header = 26,148,992 bytes
```

The 128-byte header is the standard NumPy v1 header size for this dtype and shape and is part of
the frozen expected size.

**Each artifact must bind:** identity; condition; layer; temporal slice; the 19 target rows in
order; hook site; token-position hash; preprocessing identity; checkpoint identity; shape; dtype;
byte size; SHA-256.

**Each artifact must validate:** all values finite; array non-empty; shape exactly
`[19,336,2048]`; dtype exactly little-endian float16; byte size exactly 26,148,992; layer index
in `{4,10,19}`; slice in `{PREVIOUS, CURRENT}`; source capture hash matches the kept capture;
checkpoint and preprocessing identities match P2; target index order matches the manifest exactly.

### 8.6 Extraction resume semantics

**Unit of extraction:** one `(capture_unit_id, layer, slice)` persisted array. Six units per
capture derive from one shared set of 19 forwards; the ledger records that shared forward set so
a crash never re-runs a completed capture's forwards.

**State machine.**

```
PLANNED -> RUNNING -> EXTRACTED -> VALIDATED -> DURABLE -> COMPLETE
```

| State | Meaning |
|---|---|
| `PLANNED` | the unit is in the frozen extraction plan |
| `RUNNING` | forwards in progress for this capture |
| `EXTRACTED` | the array is written to local storage |
| `VALIDATED` | every §8.5 check passed |
| `DURABLE` | published and read back by hash from the durable store |
| `COMPLETE` | ledger-sealed; never recomputed |

**Every unit records:** state; source capture hash; extraction spec hash; expected outputs;
actual hashes; completion receipt.

**Same-spec resume only.** On restart, a unit is resumed **only** if its recorded source capture
hash and extraction spec hash both match the current plan. A mismatch is
`EXTRACTION_SOURCE_CAPTURE_DRIFT` or `EXTRACTION_SPEC_DRIFT`; the unit is discarded and
re-planned, never silently re-used. Silent re-extraction against a changed source is forbidden.

A crash must not require recomputing previously verified tensors. Units already `COMPLETE` are
skipped without reading their bytes; units at `DURABLE` are re-sealed; units at `EXTRACTED` are
re-validated rather than re-extracted.

### 8.7 Representation authority

**Token grid.** The 336 visual tokens form the frozen **14 × 24** MineWorld grid (rows ×
columns), consistent with the projection at `src/mineocclude/regime_a.py:312-337`
(`token_row = screen_y * 14/360`, `token_col = screen_x * 24/640`).

**`COARSE_2X6_CONCAT`.**

```
source grid        14 x 24 tokens
coarse grid        2 x 6 cells
tokens per cell    7 x 4 = 28          (14/2 = 7 rows, 24/6 = 4 columns)
cells              12, non-overlapping, exhaustive
pooling            arithmetic mean over the 28 tokens of a cell, per hidden dimension
concatenation      row-major over cells: (0,0),(0,1)...(0,5),(1,0)...(1,5)
output dimension   12 x 2048 = 24,576
```

**Temporal representations.**

| Representation | Definition | Dimension | Role |
|---|---|---:|---|
| `CURRENT` | `coarse(CURRENT)` | 24,576 | **frozen primary at L19**; descriptive at L4/L10 |
| `CURRENT_MINUS_PREVIOUS` | `coarse(CURRENT) - coarse(PREVIOUS)` | 24,576 | secondary temporal diagnostic at L19 |
| `TWO_FRAME_CONCAT` | `concat(coarse(PREVIOUS), coarse(CURRENT))` | 49,152 | secondary temporal diagnostic at L19 |

`TWO_FRAME_CONCAT` places `PREVIOUS` first and `CURRENT` second. The order is frozen; swapping it
is `FEATURE_SLICE_SWAPPED`.

**Forbidden:** global mean pooling; any alternative grid; BEST-K; PCA selection; nonlinear
rescue; any representation search. `mean_pool_visual_tokens`
(`src/mineocclude/activations/pool.py:437-556`) is a **global** 336-token mean and must **not** be
used as the Experiment III representation.

**Required fixtures.** A synthetic `14 × 24 × 2048` grid whose token values encode their
`(row, col)` identity must be pooled and compared byte-for-byte to an independently derived
expected matrix, proving the grid is not transposed and the cells are exactly 7 × 4
(§11.A.20–21). Grid transposition is the specific named risk:
`FEATURE_POOLING_GRID_TRANSPOSED`.

The exact Experiment II source commit is not present in this repository's object database, so
this representation is implemented **from specification** and validated with fixtures. No claim
of literal source reuse may be made. If an authenticated historical artifact later becomes
available, it may be used **only** for equivalence testing.

### 8.8 Readout authority

**Primary cell (frozen):** `layer 19 | COARSE_2X6_CONCAT | CURRENT | ridge`.

| Parameter | Frozen value |
|---|---|
| Alpha grid | `{0.1, 1, 10, 100, 1000}` — five values |
| Intercept | unpenalized |
| Standardization | training-only, fit on the relevant outer/inner training identities only |
| Solver | high-dimensional dual solve when `p > n`, algebraically equivalent to the primal |
| Outer folds | 5 frozen identity folds (§2.6) |
| Inner rotations | 4 fixed, inside each outer training set only |
| Alpha selection | the predeclared **identity-macro** inner-validation criterion: minimize the mean over inner-validation identities of that identity's RMSE |
| Tie-break | **smallest alpha** |
| Held-out tuning | **forbidden** |

The existing `fit_ridge` (`src/mineocclude/probes/ridge.py:192-223`) already implements the
unpenalized intercept, training-only standardization, and the dual solve, and is reusable.

The legacy `ALPHAS = (0.1, 1.0, 10.0, 100.0)`
(`src/mineocclude/regime_a_first25_analysis.py:17`) has only **four** values and must not be
reused; Experiment III requires five.

**Held-out predictions must be emitted and hash-locked BEFORE any final statistical summary is
opened** (stage A12). Layers 4 and 10 **cannot** replace layer 19. The temporal representations
**cannot** replace the primary readout. No reselection of the primary cell is permitted after
outcomes exist.

### 8.9 Baselines

#### 8.9.1 Current-frame pixel ridge

```
source            the RGB target frame (raw capture PNG, not model-normalized)
resize            to 48 x 28, frozen area interpolation
flatten           48 x 28 x 3 = 4,032 values
standardization   training identities only
fit               the same grouped nested ridge recipe as §8.8
```

**Required manuscript language: "linear current-frame pixel baseline".** This baseline asks
whether a linear readout of *current pixels* tracks the evidence curve. It is **not** a
capacity-matched neural comparison and does **not** represent all possible pixel-history models.
MineWorld `CURRENT` is causally conditioned on up to 16 visual/action pairs; this baseline sees
one downsampled current image. Differences can reflect context, pretrained nonlinear visual
processing, dimensionality, and representation — not an isolated internal-memory advantage.

Do not generalize this to "raw-pixel accessibility", "internal support beyond pixels", or any
statement about pixel histories, CNNs, optical flow, or all sensory baselines.

#### 8.9.2 Last-seen

Hold the FIR-aligned world-x from the **last counterfactual row that was not fully occluded**.

#### 8.9.3 Constant velocity

Fit velocity from the **last 10** FIR-aligned pre-occlusion (not-fully-occluded) positions by
ordinary least squares on `(time, position)`, and extrapolate to the target tick. Window length
and arithmetic are frozen. The legacy `constant_velocity_baseline`
(`src/mineocclude/regime_a.py:456-465`) uses a 15-sample window via `EFFECTIVE_PRECEDING_STEPS`;
Experiment III requires **10** and must not reuse it unmodified.

#### 8.9.4 Training mean

Outer-training mean target. Direction stratification is applied **only if** A1 prospectively
confirms and freezes that the stratified mean is estimable in **every** outer fold; otherwise the
unstratified outer-training mean is used. The choice is frozen in P2 and never revisited.

#### 8.9.5 Time-only

Outer-training linear model on the design `[1, direction_sign, a, direction_sign × a]`, where `a`
is context age (§5.4) and `direction_sign` is `+1` for LEFT_TO_RIGHT, `-1` for RIGHT_TO_LEFT.

#### 8.9.6 Oracle status and leakage

Last-seen and constant-velocity are **oracle-state heuristics, not model inputs**. They are
identical across L0–L4 within an identity and contextualize motion difficulty. They are **not**
evidence that the model had access to authoritative state, and their inputs must never enter any
model feature. Violation is `BASELINE_ORACLE_USED_AS_MODEL_INPUT`.

**Leakage tests (all required):** no identity contributes to its own training set; every scaler,
alpha, and baseline coefficient is fit on outer/inner training identities only; the training mean
and time-only coefficients derive from outer-training rows only; no held-out target value
influences any fitted quantity.

### 8.10 Primary analysis authority

**Inferential unit: the trajectory identity.** Not the row, not the frame, not the capture.
Row-level or capture-level inference is pseudo-replication and is forbidden
(`STATS_BOOTSTRAP_UNIT_VIOLATION`).

#### 8.10.1 Identity-level metrics

For each identity `i` and condition `c`, from that cell's 19 held-out rows compute `RMSE_ic`,
`MAE_ic`, and `R²_ic`. **`RMSE` is the primary error metric**, because per-identity `R²` can be
unstable when within-window target variance is small. Per-identity `R²` is retained
descriptively. Condition summaries are **identity-macro** (mean over identities of the
per-identity value). Pooled row metrics may appear only as clearly labeled secondary
descriptions.

Per-identity `R²` requires nonzero total sum of squares; the §2.4.8 target-SD floor of 0.10
blocks guarantees it. A zero-TSS identity is `STATS_ZERO_TSS`.

#### 8.10.2 Condition evidence coordinate

```
V_c = the P0-frozen RVE condition score      (V_0 = 1 by definition; V_4 measured, not forced to 0)
O_c = 1 - V_c
```

#### 8.10.3 The three primary estimands

For each identity `i`:

```
1. Ordered evidence-response slope
   S_i        = OLS slope of RMSE_ic on O_c across the five conditions L0..L4

2. Partial degradation
   Dpartial_i = mean(RMSE_i,L1 , RMSE_i,L2 , RMSE_i,L3) - RMSE_i,L0

3. Opaque increment
   Dopaque_i  = RMSE_i,L4 - RMSE_i,L3
```

These three, and only these three, form **`FINAL_PRIMARY_ANALYSIS_FAMILY`**.

#### 8.10.4 Directional hypotheses

All three are hypothesized **positive**: error increases as direct evidence weakens.

#### 8.10.5 Frozen statistics

| Quantity | Frozen value |
|---|---|
| Reported per estimand | mean, standard error |
| Test | **one-sided** repeated-measures / identity-level t test in the hypothesized positive direction |
| Interval | **two-sided 95%** identity-bootstrap confidence interval |
| Multiplicity | **Holm** across exactly the **three** primary p-values |
| Bootstrap replicates | `B = 10,000` |
| Bootstrap unit | **whole identity**, with all five conditions, all rows, all predictions, and all representations kept together |
| Bootstrap seed | frozen in P2 |

Captures and rows are **never** resampled as independent units. The existing whole-identity
bootstrap at `src/mineocclude/regime_a_first25_analysis.py:226-251` (`B = 10,000`, resampling
identities) is the reusable pattern.

#### 8.10.6 Removed gates — do not reintroduce

The following are **removed** and may not reappear anywhere in Experiment III:

- discontinuity ratio `>= 3`;
- expected opaque `R²` / RMSE reproduction band;
- `B = 199` per-condition decoder nulls;
- the `B = 49` selection-aware derangement null (`src/mineocclude/regime_a.py:571-612`) — it
  answers a searched-family question Experiment III does not ask;
- a four-statistic Holm family including the pixel comparator;
- all-row pseudo-replication;
- an MLP stretch or any nonlinear rescue;
- outcome-dependent condition dropping;
- **any overall experiment pass/fail qualification verdict**.

Confidence intervals are estimates, **not** pass/fail gates. Historical `R² > 0` and
`RMSE <= 0.50` thresholds may appear as **manuscript reference lines only**, never as
Experiment III success gates. Adding a success gate is `ANALYSIS_SUCCESS_GATE_REINTRODUCED`.

### 8.11 L0 interpretability control

The L0 positive control has exactly one meaningful interpretability check:

> The **two-sided 95% identity-bootstrap interval** for the L0 RMSE **improvement over the
> outer-training mean baseline** must **exclude zero in the favorable direction** — that is, the
> model's L0 RMSE is lower than the training-mean baseline's L0 RMSE.

**If this check passes**, the apparatus and readout are interpretable and the primary results are
reported normally.

**If this check fails**, then, exactly:

- **Do not** retune anything.
- **Do not** replace or drop identities.
- **Do not** redefine the primary representation, layer, alpha grid, or estimands.
- **Do not** re-run the analysis hoping for a different result.

Instead the experiment becomes an **apparatus/readout-limited result**, and reporting changes as
follows:

1. The failure is stated prominently in the abstract, the results section, and every figure
   caption reporting a condition curve.
2. The three primary estimands are still computed and reported in full, but every one of them is
   labeled **uninterpretable as evidence about hidden-state accessibility**, because the readout
   is not demonstrably better than a constant even on the fully visible anchor.
3. No claim in §1.7's permissible list may be made about graded observability.
4. The permitted claim is confined to: "in this fresh cohort, the frozen readout did not
   demonstrably beat the outer-training mean even under full visibility; the graded comparison is
   therefore not interpretable."
5. Experiment III **can still close** (§14 row 12) as a valid negative apparatus/readout report.

No expected L4 failure is required, and no L4 outcome gates anything.

### 8.12 Secondary analysis authority

`FINAL_SECONDARY_ANALYSIS_FAMILY` contains exactly the five families below. No secondary result
may change the primary readout or the primary-family interpretation, and none may be promoted to
primary after outcomes exist.

#### A. MineWorld versus linear current-frame pixel

```
per identity i:  Delta_i = mean over c in {L1, L2, L3} of ( RMSE_pixel,ic - RMSE_MW,ic )
report:          mean, two-sided 95% identity-bootstrap CI
```

L0 and L4 differences are **descriptive only**. No "internal support beyond pixels" claim is
allowed unless the **partial-condition** interval excludes zero in favor of MineWorld — and even
then the claim is limited to **the frozen linear current-frame pixel baseline** (§8.9.1).

#### B. Temporal rescue

```
per identity i, average over c in {L1, L2, L3, L4} of the RMSE reduction of
  (i)  CURRENT_MINUS_PREVIOUS  versus CURRENT
  (ii) TWO_FRAME_CONCAT        versus CURRENT
tests:        two one-sided paired t tests
multiplicity: Holm across exactly those two comparisons
intervals:    two-sided 95% identity-bootstrap
```

Condition-specific temporal deltas are descriptive.

#### C. Context boundary

Report RMSE in the four frozen age bins `a ∈ 1–5`, `6–10`, `11–15`, `16–19`.

The single prespecified descriptive boundary interaction is:

```
[ ( RMSE_L4(a in 16..19) - RMSE_L4(a in 12..15) )
- ( mean_{c in L1..L3} RMSE_c(a in 16..19) - mean_{c in L1..L3} RMSE_c(a in 12..15) ) ]
```

summarized by a two-sided 95% identity-bootstrap interval. The interaction deliberately uses the
**adjacent four-row windows `12–15` and `16–19`** straddling the context boundary at `a = 15/16`
(§5.4) — not the four reporting bins. Both the bins and the interaction must be computed and
reported.

This is **mechanistic consistency evidence only**. It is **not** a causal forgetting test,
because age and target position/time remain coupled within a trajectory. The boundary must be
established from explicit last-evidence age and verified frame identities, never assumed from a
generic `tau` bin.

#### D. Motion and clock baselines

Descriptive paired RMSE differences of the frozen readout against last-seen, constant-velocity,
training-mean, and time-only, each with a two-sided 95% identity-bootstrap interval. Descriptive;
**no qualification gate**.

#### E. Depth

Layers 4 and 10: descriptive condition curves and slopes only. They are correlated checks. They
**cannot** rescue, replace, or redefine the primary result.

---

## 9. Engineering repair versus scientific amendment

This boundary is the core protection of the experiment's prospective status. **No implementation
agent may classify a scientific redesign as a "bug fix".**

### 9.1 Engineering repair

An **engineering repair** restores **already-authorized** behavior that the code failed to
implement. It changes no frozen scientific value. Examples:

- a wrong filesystem path;
- a serialization defect;
- a wall-builder implementation bug;
- a manifest parser defect;
- a process launch bug;
- an arena-cache bug, including the missing material in the cache key;
- an incorrect temporal-slice implementation **when this authority already specifies the correct
  slice**;
- a resume defect;
- a logging or status defect;
- a durability code bug;
- a validator that fails to check something this authority requires.

**Procedure.** Fix the code; add or extend the test that would have caught it; rerun the affected
static/P1 test; re-run the invalidated units per that stage's invalidation scope; record the
repair in the stage receipt. No amendment is required.

### 9.2 Scientific design change

A **scientific design change** alters a frozen decision. Examples:

- new identities, or replacement identities after outcomes;
- a different speed, or a different `q`;
- different materials after the P0 freeze;
- changed RVE thresholds, zones, separation, SNR, CV, or background tolerance;
- changed target rows, target labels, or the eligibility rule;
- a changed layer, representation, pooling grid, or token-slice **specification**;
- a changed alpha grid, fold structure, or inner-rotation count;
- a changed or added baseline;
- a changed primary estimand, hypothesis direction, or metric;
- changed multiplicity or bootstrap unit;
- any new success gate;
- refitting the FIR kernel from Experiment III data.

**Procedure.** Stop. Emit `AUTHORITY_AMENDMENT_REQUIRED` with the exact decision, why it cannot
stand, and the minimum change. Produce a **prospective** authority amendment: a new authority
version, a new `AUTHORITY_SHA256`, an explicit statement of what changed and what evidence
existed at the time of the change, and an explicit re-derivation of which downstream artifacts
are invalidated. Any amendment made **after** outcomes are visible must be disclosed as such in
the final package and in the manuscript, and the affected result loses prospective status.

### 9.3 The decision test

If an agent cannot immediately tell which side a change falls on, apply this test:

> Could this change plausibly alter the reported value of any of the three primary estimands, any
> secondary estimand, or the L0 control — **for reasons other than fixing an outright
> computational error**?

If yes, it is a scientific change (§9.2). If uncertain, treat it as scientific. Under-classifying
is the failure mode that destroys the experiment; over-classifying merely costs a review.

---

## 10. Deadline fallback authority

All fallbacks are selected **before production launch** by **time and status only**. A scientific
outcome may **never** be used to choose a fallback. Fallback selection is recorded in P2 or, if
selected later, in an explicit dated pre-launch amendment.

### 10.1 NORMAL

```
25 identities x 5 conditions      = 125 captures
layers {4, 10, 19}
CURRENT + PREVIOUS
analyses: primary + temporal + context + depth
storage:  750 arrays, 19,611,744,000 bytes (18.2649 GiB)
```

### 10.2 ONE DAY BEHIND

```
first 20 frozen identities (by identity_priority_order) x 5 conditions = 100 captures
layer 19 only
CURRENT + PREVIOUS retained  (so temporal analyses remain possible)
depth panel dropped
report N = 20; do NOT combine historical identities
storage: 20 x 5 x 1 layer x 2 slices = 200 arrays = 5,229,798,400 bytes (4.8706 GiB)
```

### 10.3 TWO DAYS BEHIND

```
first 15 frozen identities x 5 conditions = 75 captures
layer 19 only
CURRENT only
temporal and depth analyses dropped
report N = 15
storage: 75 arrays = 1,961,174,400 bytes (1.8265 GiB)
```

This preserves a five-point evidence curve at reduced precision. It is preferred over a
three-condition design because the primary question is **curve shape**.

### 10.4 DISASTER

No fresh graded Experiment III confirmatory result is produced.

A zero-capture archival analysis **may** add last-seen, constant-velocity, current-pixel, and
correctly defined context-age descriptions to the existing Experiment II corpus. It must be
explicitly labeled **post hoc / developmental**. It may **not** be presented as the fresh
Experiment III primary cohort, nor as evidence for glass or graded observability.

### 10.5 Frozen clock triggers and derived implementation checkpoints

The reference schedule (2026) is now expressed relative to `PHASE2_START` (§13.3.5), not to a
hard-coded Monday.

```
TARGET_RESULT_LOCK      = Wed 2026-09-02 23:00 local
LATEST_SAFE_RESULT_LOCK = Thu 2026-09-03 20:00 local   (the absolute stop)

-- freeze/launch triggers (unchanged) --
TRIGGER_ONE_DAY_BEHIND  : P2 freeze not complete by Tue 2026-09-01 23:59 -> plan 10.2
TRIGGER_TWO_DAYS_BEHIND : P2 freeze not complete by Wed 2026-09-02 12:00 -> plan 10.3
TRIGGER_DISASTER        : production capture cannot safely launch by
                          Wed 2026-09-02 22:00                          -> plan 10.4
```

#### The implementation checkpoints are **derived**, not asserted

Repair pass 1 typed in Tue 12:00 / Tue 20:00 / Wed 08:00 and never quantified what the plans they
selected actually saved. Each instant below is now computed as

```
checkpoint(P) = ABSOLUTE_EXPERIMENT_DEADLINE - post_A2_tail(P, CONSERVATIVE)
```

so it is the last moment at which plan `P` can still capture, extract, analyse and lock before the
hard stop **even if execution goes badly**. These instants are absolute: they do **not** move with
`PHASE2_START`.

| Checkpoint | Instant (local) | Required milestone | Action if unmet |
|---|---|---|---|
| **CP0** — III-B deferral | **Mon 2026-08-31 20:00** | task `I10` complete | defer **all** III-B-only implementation (`IB01`, `IB04`–`IB20`) |
| **CP1** — drop below NORMAL | **Tue 2026-09-01 13:00** | `A2 == PASS` | select **plan 10.2** |
| **CP2** — drop below 10.2 | **Tue 2026-09-01 20:36** | `A2 == PASS` | select **plan 10.3** |
| **CP3** — disaster | **Wed 2026-09-02 00:48** | `A2 == PASS` | select **plan 10.4** |

Derivations: NORMAL conservative tail `55.00 h`; 10.2 `47.40 h`; 10.3 `43.20 h`. CP0 is
`PHASE2_START + 24 h` at the reference start — the earliest instant at which a lag is
distinguishable from ordinary variance.

**The general rule, frozen:**

```
at checkpoint instant T, if A2 is not PASS:
    remaining := ABSOLUTE_EXPERIMENT_DEADLINE - T
    select the LARGEST frozen plan P with  post_A2_tail(P, CONSERVATIVE) <= remaining
    if no plan qualifies -> PLAN 10.4 DISASTER
```

The tail is evaluated at **conservative** deliberately, so a checkpoint never selects a plan that
only closes if execution happens to go well.

**What each checkpoint actually buys:**

| Checkpoint | Implementation hours saved b/n/c | *Realizable* at that instant | Tail hours saved b/n/c |
|---|---|---|---|
| CP0 | 2.30 / 4.60 / 8.00 | 2.30 / 4.60 / 8.00 | — |
| CP1 → 10.2 | 0.50 / 1.00 / 1.70 | **0.00 / 0.00 / 1.20** | 2.30 / 3.92 / 7.60 |
| CP2 → 10.3 | 1.80 / 3.40 / 5.70 | **0.00 / 0.00 / ~1.05** | 3.75 / 6.28 / 11.80 |

The realizable implementation saving is near zero because the deletable work is built early —
stated plainly rather than hidden. **CP0 is the only checkpoint that reliably recovers
implementation time**, which is why III-B-only work is the first thing dropped (§29.11). CP1 and
CP2 recover the **tail**.

Milestone timeline at the reference start (`PHASE2_START = Sun 2026-08-30 20:00`):

| Band | `I10` | `A1` complete (`I18`) | `A2` green (`I20`) | CP0 | CP1 | CP2 | CP3 |
|---|---|---|---|---|---|---|---|
| best | Mon 05:42 | Mon 14:00 | Mon 16:42 | pass | pass | pass | pass |
| nominal | Mon 13:42 | Tue 04:30 | Tue 10:24 | pass | pass | pass | pass |
| conservative | Tue 01:30 | Wed 02:06 | Wed 13:00 | **trip** | **trip** | **trip** | **trip** |

Each trigger and checkpoint is evaluated **once**, at its stated instant, against stage-receipt
status and the clock **only**. Plans escalate **monotonically** — a later evaluation may move only
to a more reduced plan, never back. Every evaluation and its inputs are recorded in
`deadline_decision_receipt.json`. **No scientific outcome is an input to any of them.**

---

## 11. Test plan summary

The full plan is `EXPERIMENT_III_TEST_PLAN.md`. Groups A, B and **D** all execute at `A2`;
group C at `A5`; group E at `B-PILOT`. Counts: **A = 30**, **B = 13**, **D = 33** — **76** named
static/CPU checks. Group-D checks `D.2`, `D.4` and `D.31` are *additionally* `A1`
task-completion gates because III-A qualification gate 12 depends on them.

Group A (static unit tests) has 30 named checks, referenced throughout this authority:

| # | Check | # | Check |
|---:|---|---:|---|
| A.1 | deterministic identity generation | A.16 | one-forward layer fixture (`{4,10,19}` from one call) |
| A.2 | RNG stream stability | A.17 | tensor shape `[19,336,2048]` |
| A.3 | deterministic path reproduction (iterative, not cumsum) | A.18 | tensor byte count 26,148,992 |
| A.4 | speed 2.0 / `q` 0.05 / `dt` 0.05 correctness | A.19 | historical-seed exclusion |
| A.5 | fold partition (13/12, 5×5, direction balance) | A.20 | coarse pooling exactness |
| A.6 | within-identity target-variance gate (SD ≥ 0.10) | A.21 | coarse pooling grid orientation (not transposed) |
| A.7 | same target rows across all five conditions | A.22 | temporal subtraction |
| A.8 | wall-coordinate invariance under material change | A.23 | temporal concatenation order |
| A.9 | exact wall registry ID receipt | A.24 | pixel baseline dimension 4,032 |
| A.10 | counterfactual extent uses `present=True` for L0 | A.25 | fold leakage |
| A.11 | extent port equivalence (475/475 A-prime labels) | A.26 | bootstrap identity resampling |
| A.12 | FIR arithmetic and complete-history gate | A.27 | prediction locking order |
| A.13 | context-age frame-identity verification | A.28 | corrupted artifact rejection |
| A.14 | RVE fixture (linearization, energy, normalization) | A.29 | same-spec resume |
| A.15 | mask fixture, deterministic material selection, P0 tie-break | A.30 | authority/hash drift rejection |

The `PREVIOUS`/`CURRENT` semantic frame fixtures and the token-slice numeric fixture are
prerequisites of A.16 and are enumerated separately in the test plan.

Group B is 13 CPU integration checks over complete manifests and synthetic/frozen fixtures
without GPU or model inference, including `B.12`, the combined-program storage preflight, and
`B.13`, the storage-gate coherence invariant.
Group D is 33 III-B static/CPU checks, also at `A2`; `D.7` is the affine-boundary test,
`D.31` the gate-12 ordering test, `D.32` the `sigma_hat` positivity test, and `D.33` the Holm
procedure test. Group C is the P1 live test, run **only** on the two sacrificial pilot
identities. **No production identity may be used to debug the implementation.**

---

## 12. Authority internal audit

The audit performed at construction, and the audit any amendment must repeat, is recorded in
`AUTHORITY_VALIDATION_REPORT.md`. It compares this authority against (1) the Phase 0 adjudicated
Markdown design, (2) the Phase 0 decision matrix, (3) the Phase 0 decision memo, and (4) the
actual current source tree, checking that every Phase 0 decision is represented, no settled
decision was silently changed, all counts/bytes/captures/forwards/layers/slices/targets/statistics
and fallback plans agree, no stale Fable value survived, no stale 1.5-speed behavior is
authoritative, no `OCCLUDED_AGREEMENT` selector survives for L1–L3, no Experiment II
qualification gate reappears, and no outcome-dependent design choice exists.

---

## 13. Time, compute, and storage authority

### 13.1 Activation storage (exact)

| Scope | Captures | Rows / forwards | Logical tensors | `.npy` arrays | Exact bytes | GiB |
|---|---:|---:|---:|---:|---:|---:|
| Production | 125 | 2,375 | 14,250 | 750 | 19,611,744,000 | 18.2649 |
| P1 pilot (excluded) | 10 | 190 | 1,140 | 60 | 1,568,939,520 | 1.4612 |
| Total if pilot retained | 135 | 2,565 | 15,390 | 810 | 21,180,683,520 | 19.7260 |

Every figure independently recomputed from the schema at authority construction; all match Phase 0
exactly. "Logical tensor" counts each row × layer × slice; the array counts reflect the actual
per-capture serialized layout.

### 13.2 Other storage — units, physical pools, and the A3 gate

**Units.** Every storage figure in this authority is **GiB = 2³⁰ bytes**. Every gate is also
frozen in exact bytes, and tooling compares **bytes**, read from the OS (`statvfs` `f_bavail × f_frsize` on POSIX, `GetDiskFreeSpaceExW` `lpFreeBytesAvailableToCaller` on
Windows). Where an earlier draft wrote "GB" it meant GiB; the byte value is authoritative.
Comparing decimal-GB free space against a binary-GiB threshold is `STORAGE_POOL_DOUBLE_COUNTED`.

**Physical pools.** Three logical roles, and A3 must resolve each to a real filesystem:

| Pool | Role | Identified by |
|---|---|---|
| `POOL_WORKING` | the local filesystem holding the repository, `data/experiment_iii/`, raw PNGs, activations, features, caches, predictions, figures, logs | device/volume id of `data/experiment_iii/` |
| `POOL_DURABLE` | where `COMPLETE_VALIDATED_DURABLE` copies live and are read back by hash | mode recorded at A3 |
| `POOL_SCRATCH` | temporary activation copies and extraction working files | device/volume id of the scratch path |

**Two logical categories that resolve to the same device id are ONE pool, and their free space
is counted ONCE.** `POOL_SCRATCH` is a separate pool **only** if its device id differs from
`POOL_WORKING` — proven by comparing device ids, never by comparing path strings. The superseded
III-B launch-gate formulation "`≥ 60 GB` durable free **and** `≥ 40 GB` scratch free" double
counted a single filesystem and is withdrawn (§29.5).

**Durability modes** — A3 records exactly one, defaulting to the first if the others are not
proven:

| Mode | Local free-space consequence |
|---|---|
| `LOCAL_MIRROR_SAME_POOL` *(default; fails closed)* | the mirror consumes `POOL_WORKING`; the **mirrored** gate applies |
| `LOCAL_MIRROR_DISTINCT_POOL` | `POOL_DURABLE` gets its own `≥ 28 GiB` gate; `POOL_WORKING` uses the no-mirror gate |
| `REMOTE_OBJECT_STORE` | **no local free-space gate** — remote object storage has no meaningful local bound; A3 verifies reachability and a hashed round trip instead, and `POOL_WORKING` uses the no-mirror gate |

**Mirror scope is frozen.** The local mirror covers activation arrays, per-unit receipts,
manifests and the ledger. It does **not** mirror raw PNGs, P0 images, feature caches, temporary
copies or logs — those are reproducible from a frozen capture spec and are not the durable
scientific record. Mirroring them would add ~8.1 GiB for no scientific benefit.

**Derived peak (combined program, 189 captures including pilots).** Raw PNGs at a generous
250 KiB/frame budget; P0 images; features, predictions, bootstrap outputs, figures and logs;
failed-attempt provenance and temporary copies:

| Component | GiB |
|---|---:|
| activations, all 189 captures | 23.571 |
| capture raw PNGs (189 × 180 × 250 KiB) | 8.113 |
| P0 images budget | 1.500 |
| features / predictions / bootstrap / figures / logs | 1.000 |
| failed attempts and temporary copies | 1.500 |
| **peak, no local mirror** | **35.682** |
| local mirror (activations + receipts/manifests/ledger) | 23.621 |
| **peak, with local mirror** | **59.304** |

This reproduces the independent audit's ~35 GiB / ~57 GiB estimates to within ~0.7 and ~2.3 GiB;
the excess is the explicit failed-attempt and P0 budget.

```
A3 GATE, COMBINED PROGRAM, with a local mirror : POOL_WORKING free >= 64 GiB (68,719,476,736 B)
A3 GATE, COMBINED PROGRAM, no local mirror     : POOL_WORKING free >= 40 GiB (42,949,672,960 B)
A3 GATE, distinct local POOL_DURABLE           : POOL_DURABLE free >= 28 GiB (30,064,771,072 B)
A3 GATE, REMOTE_OBJECT_STORE                   : no local gate; round trip verified

superseded III-A-only thresholds               : 45 GiB mirrored / 30 GiB unmirrored
```

**The two gates must not contradict each other.** *Added by repair pass 2.* A host that passes
`A3` at exactly the mirrored threshold must still be able to pass the III-B launch gate;
otherwise the program forces a spurious `CLEAN_SKIP` on a host that legitimately cleared the
gate that was sized for the combined program. The frozen invariant, in binary GiB:

```
A3_PASS_GIB  -  MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB  >=  III_B_INCREMENTAL_LAUNCH_GATE_GIB
     64      -                48.796                    =   15.204   >=   15         OK

III_B_INCREMENTAL_LAUNCH_GATE_GIB  >  III_B_INCREMENTAL_EXPECTED_PEAK_GIB
               15                  >              10.508        margin 4.492 GiB
```

`MAX_III_A_STORAGE_SHARE` is **derived**, not asserted: whole-program mirrored peak
`59.304` − III-B incremental mirrored peak `10.508` = `48.796 GiB`.

**The mandatory A3 threshold was NOT raised to protect optional III-B.** III-A is
indispensable and III-B is optional; raising the gate that lets III-A start, in order to make
III-B easier to finish, is the wrong trade. The **optional** gate was lowered from 20 to
**15 GiB** to fit the structural headroom instead. Enforced by `B.13`.

**A3 uses the COMBINED-program gate.** III-B is `PROSPECTIVELY_AUTHORIZED_OPTIONAL`, and A3
always precedes the III-B launch gate, so III-B can never have been terminally skipped by the
time A3 runs. The III-A-only thresholds are therefore unreachable in this program and are
retained only for the counterfactual in which III-B is de-authorized by amendment.

The mirrored gate is **64 GiB**, not 60, to keep a real margin (4.696 GiB) over the derived
59.304 GiB mirrored peak. A3 fails closed on `STORAGE_INSUFFICIENT` rather than starting a run
that cannot finish, and the threshold is never lowered to proceed. The authority-construction
host reported **93 GiB** free, clearing the mirrored gate with 33.7 GiB to spare.

### 13.3 Time envelopes

#### 13.3.1 The four time quantities — never interchangeable

Repair pass 1 conflated developer **effort** with calendar **elapsed time** and produced an
internally impossible schedule. Four quantities are now defined separately, and the schedule uses
exactly one of them.

| Quantity | Meaning | Used by the schedule? |
|---|---|---|
| `TOTAL_TASK_EFFORT_HOURS` | human-equivalent developer effort to build a task and its tests | **no** — it is a sum of effort, not calendar time |
| `SERIAL_CRITICAL_PATH_ELAPSED_HOURS` | wall clock consumed by **one** agent session executing A1/A2 in dependency order | **yes** |
| `DEPENDENCY_CRITICAL_PATH_HOURS` | longest dependency chain; the floor with unlimited parallel agents | no — recorded as reference only |
| `OPERATOR_ATTENDED_HOURS` | human review, approval, rig operation | no — reported for staffing |
| `UNATTENDED_COMPUTE_HOURS` | production capture and GPU extraction | consumes wall clock, not attention |

`SERIAL_ELAPSED` is the **sum** over the selected task set, **not** the dependency critical path,
because every `A1` task is repository-exclusive and single-session. Claiming the dependency path
would be exactly the false parallelism §13.3.1 forbids below.

```
TOTAL_TASK_EFFORT  =  SERIAL_ELAPSED x AGENT_COMPRESSION_FACTOR
AGENT_COMPRESSION_FACTOR = 2.0 exactly, by definition
```

**That factor is an assumption, and it is the dominant schedule risk.** It is not measured from
this program. The §10.5 checkpoints do not trust it: they key on **observed task-completion
milestones against the clock**. If the true factor is 1.0 — no agent speedup at all — the program
degrades to the CONSERVATIVE column, which the checkpoints handle by selecting a reduced plan.

#### 13.3.2 `A1` + `A2` implementation envelope, derived per task

Derived per task from `IMPLEMENTATION_TASK_GRAPH.json` at this frozen, dependency-respecting
serial build order:

```
I01 -> I05 -> I06 -> IB02 -> IB03 -> I02 -> I03 -> I04 -> I09 -> I10 -> I11
    -> I12 -> I15 -> I13 -> I14 -> I16 -> I07 -> I08 -> I17 -> I18 -> I19 -> I20
```

**Every hour below is attributable to a named task or a named cross-task bucket. There is no
anonymous residual.** Full machine form, including resource class, predecessors, parallelization
verdict and plan membership per task: `resources.implementation_time_model.per_task_elapsed_model`.

| Task | Description | best | nom | cons | 10.2 cut | 10.3 extra cut | in 10.3? |
|---|---|---:|---:|---:|---:|---:|:--:|
| `I01` | Experiment III namespace and schema | 0.40 | 0.70 | 1.20 | — | — | yes |
| `I05` | Counterfactual extent logic (A-prime port) | 0.80 | 1.40 | 2.40 | — | — | yes |
| `I06` | FIR kernel recovery and target manifest | 1.00 | 1.80 | 3.00 | — | — | yes |
| `IB02` | q-generalized path and qualification primitive (SHARED, gates I02) | 0.50 | 0.90 | 1.50 | — | — | yes |
| `IB03` | q=0.05 regression fixture | 0.30 | 0.50 | 0.90 | — | — | yes |
| `I02` | Fresh cohort generator and folds | 1.50 | 2.80 | 4.50 | — | — | yes |
| `I03` | Wall condition parameterization | 1.00 | 1.80 | 3.00 | — | — | yes |
| `I04` | Wall receipts, cache key, and capture schedule | 1.20 | 2.20 | 3.50 | — | — | yes |
| `I09` | Multi-layer temporal extraction | 1.20 | 2.20 | 3.60 | 0.15/0.30/0.50 | 0.30/0.50/0.80 | yes |
| `I10` | Tensor serialization, inventory, and validator | 0.80 | 1.40 | 2.40 | — | — | yes |
| `I11` | Coarse representation | 0.50 | 0.90 | 1.50 | — | — | yes |
| `I12` | Temporal representations | 0.50 | 0.90 | 1.50 | — | 0.50/0.90/1.50 | **no** |
| `I15` | Grouped ridge and prediction lock | 1.00 | 1.80 | 3.00 | — | — | yes |
| `I13` | Current-frame pixel baseline | 0.40 | 0.70 | 1.20 | — | — | yes |
| `I14` | Motion and clock baselines | 0.50 | 0.90 | 1.50 | — | — | yes |
| `I16` | Statistics and result packaging | 1.20 | 2.20 | 3.60 | 0.25/0.50/0.85 | 0.30/0.60/1.00 | yes |
| `I07` | RVE and P0 machinery | 1.50 | 2.60 | 4.20 | — | — | yes |
| `I08` | Sentinel machinery | 0.40 | 0.70 | 1.20 | — | — | yes |
| `I17` | Status and blocker framework | 0.60 | 1.00 | 1.70 | — | — | yes |
| `I18` | Resume and recovery | 0.70 | 1.20 | 2.00 | — | — | yes |
| `I19` | Static unit tests | 0.60 | 1.20 | 2.20 | — | — | yes |
| `I20` | CPU integration tests | 0.60 | 1.20 | 2.20 | — | — | yes |
| **22 tasks** | | **17.20** | **31.00** | **51.80** | | | |
| *GROUP_B_D_INTEGRATION_FIXTURES* | Cross-task synthetic fixtures for test groups B and D that belong to no single task (complete synthetic manifests, stubbed decoder tensors, planted-effect datasets) | 1.00 | 1.90 | 3.20 | 0.10/0.20/0.35 | 0.20/0.40/0.70 | yes |
| *FABRIC_BUILD_CYCLES* | Gradle build, jar hashing and Minecraft client relaunch cycles for the bounded Fabric edits C05-C08 | 1.00 | 2.00 | 3.50 | — | — | yes |
| *STATIC_VALIDATION_AND_ENGINEERING_REPAIR_ALLOWANCE* | Bounded engineering repair allowance: cross-module integration defects, the A-prime port reconciliation, FIR recovery reproduction, and defects surfaced late by group A/B/D | 1.50 | 3.50 | 6.50 | — | — | yes |
| **3 buckets** | | **3.50** | **7.40** | **13.20** | | | |
| **NORMAL TOTAL** | | **20.70** | **38.40** | **65.00** | | | |

```
NORMAL     = sum(tasks) + sum(buckets)
PLAN 10.2  = NORMAL    - sum(10.2 cuts over tasks and buckets)      cuts 0.50 / 1.00 / 1.70
PLAN 10.3  = PLAN 10.2 - sum(10.3 extra cuts over tasks and buckets) extra 1.30 / 2.40 / 4.00
```

| Plan | `SERIAL_ELAPSED` b/n/c | `TOTAL_TASK_EFFORT` b/n/c | dependency-path floor b/n/c |
|---|---|---|---|
| **NORMAL** | **20.70 / 38.40 / 65.00** | 41.40 / 76.80 / 130.00 | 7.20 / 13.20 / 22.40 |
| **PLAN 10.2** | **20.20 / 37.40 / 63.30** | 40.40 / 74.80 / 126.60 | 7.20 / 13.20 / 22.40 |
| **PLAN 10.3** | **18.90 / 35.00 / 59.30** | 37.80 / 70.00 / 118.60 | 6.70 / 12.30 / 20.90 |
| III-B additive (`IB01`, `IB04`–`IB20`, 18 tasks) | 2.30 / 4.60 / 8.00 | 4.60 / 9.20 / 16.00 | — |
| shared mandatory (`IB02` + `IB03`) | 0.80 / 1.40 / 2.40 | 1.60 / 2.80 / 4.80 | — |

`TOTAL_TASK_EFFORT = SERIAL_ELAPSED x AGENT_COMPRESSION_FACTOR`, with the factor **exactly 2.0**
by definition. Effort is a derived reporting quantity; **elapsed is the primitive the schedule
uses**, and it is the *sum* over the task set, not the dependency-path floor, because every `A1`
task is repository-exclusive and single-session.

**Task `I12` is the only task removed outright** — by plan 10.3, which drops temporal
representations. Plans 10.2 and 10.3 otherwise trim named *portions* of `I09`, `I16` and the group
B/D fixture bucket.

**Honest finding: the reduced plans are not an implementation-overrun remedy.** Their cuts are
realizable only if the plan is selected *before* the work is built, and the deletable work is built
early. Measured at the §10.5 checkpoint instants the realizable implementation saving is **0.00 h**
at best and nominal and about **1.0–1.2 h** at conservative. Their real value is the post-`A2`
tail: **3.92 h** and **6.28 h** at nominal, **7.60 h** / **11.80 h** at conservative.

**The three real recovery levers, in order of size:**

1. **Start Phase 2 immediately on authorization** (§13.3.5) — authorizing Sunday 20:00 rather than
   waiting for Monday 09:00 recovers **13 wall-clock hours**, larger than every plan-reduction
   saving combined.
2. **Defer all III-B-only implementation** (`IB01`, `IB04`–`IB20`): **2.30 / 4.60 / 8.00 h**, the
   first thing dropped under any lag. `IB02`/`IB03` are never deferred.
3. **Reduce the tail** by selecting plan 10.2 or 10.3: **3.92 – 11.80 h**.

**False parallelism is forbidden.** Every task above records `SAFE_TO_PARALLELIZE = false` with its
reason: repository-exclusive mutation in a single agent session, and for `I03`/`I04` additionally
the shared Minecraft/Gradle build. **Nothing overlaps `A1` implementation.** The only real
parallelism is unattended capture overlapping repository work, unattended III-B capture overlapping
III-A CPU analysis, and GPU extraction overlapping writing.

**Attended vs unattended:** `OPERATOR_ATTENDED` `9 / 16 / 27 h`; `UNATTENDED_COMPUTE`
`7.5 / 12.25 / 22 h`.

#### 13.3.3 Execution envelopes

| Stage | Expected | Conservative | Worst reasonable |
|---|---|---|---|
| Fresh generation, qualification, manifest freeze | 2–4 person-hours | 6 h | 8 h |
| P0 calibration | ~half a day | 1 day | 1.5 days |
| P1 pilot (10 captures + 190 forwards) | 1–2 h | 3 h | 5 h |
| Production capture (125 captures) | **6–13 h** | 16 h | 20 h |
| Extraction (2,375 forwards) | **1.5–4 h** | 6 h | 8 h |
| CPU analysis | **2–4 h** | 6 h | 8 h |

**Extraction envelope, independently reasoned.** Pure forward time projected from Experiment II's
0.69 s/forward is `2,375 × 0.69 ≈ 27 minutes`. Preprocessing, hook overhead across 20 transiently
registered layers, 19.6 GB of writes, per-array validation, and durable publish/read-back
dominate, making **1.5–4 hours** the operational envelope. The extra `PREVIOUS` slice adds **no
forwards** — only selection and writes.

Capture is resumable and suitable for overnight execution.

#### 13.3.4 Post-`A2` tail, and the feasibility matrix

The **post-`A2` tail** is everything after static validation goes green: `A3`, P0, P1, P2,
production capture, extraction, analysis, packaging and result lock, plus an explicit allowance
for rig/attended window waits (`1.0 / 2.0 / 4.0 h`).

| Plan | tail b/n/c (h) | nominal breakdown |
|---|---|---|
| **NORMAL** | 17.50 / **31.25** / 55.00 | A3 1.00, P0 8.00, P1 2.00, P2 1.00, capture 9.50, extraction 2.75, analysis 3.00, packaging 2.00 |
| **10.2** | 15.20 / **27.33** / 47.40 | capture 7.60, extraction 0.73 (100 captures, 200 arrays) |
| **10.3** | 13.75 / **24.97** / 43.20 | capture 5.70, extraction 0.28 (75 captures, 75 arrays) |

**Feasibility matrix.** `PHASE2_START = 2026-08-30T20:00` gives a **96 h** budget to the absolute
Thursday 20:00 stop. Implementation band and execution band are modelled **independently** — they
are not assumed to move together.

| Plan | impl band | exec band | impl h | tail h | total | margin | verdict |
|---|---|---|---:|---:|---:|---:|---|
| NORMAL | best | best | 20.70 | 17.50 | 38.20 | +57.80 | **feasible** |
| NORMAL | nominal | nominal | 38.40 | 31.25 | 69.65 | +26.35 | **feasible** |
| NORMAL | conservative | nominal | 65.00 | 31.25 | 96.25 | −0.25 | **NOT feasible** |
| NORMAL | conservative | conservative | 65.00 | 55.00 | 120.00 | −24.00 | **NOT feasible** |
| 10.2 | best | best | 20.20 | 15.20 | 35.40 | +60.60 | feasible |
| 10.2 | nominal | nominal | 37.40 | 27.33 | 64.73 | +31.27 | feasible |
| 10.2 | conservative | nominal | 63.30 | 27.33 | 90.63 | +5.37 | **feasible** |
| 10.2 | conservative | conservative | 63.30 | 47.40 | 110.70 | −14.70 | not feasible |
| 10.3 | best | best | 18.90 | 13.75 | 32.65 | +63.35 | feasible |
| 10.3 | nominal | nominal | 35.00 | 24.97 | 59.97 | +36.03 | feasible |
| 10.3 | conservative | nominal | 59.30 | 24.97 | 84.27 | +11.73 | **feasible** |
| 10.3 | conservative | conservative | 59.30 | 43.20 | 102.50 | −6.50 | not feasible |

```
III_A_TIME_FEASIBILITY
  NORMAL  best      FEASIBLE          NORMAL  nominal  FEASIBLE
  NORMAL  conservative  NOT FEASIBLE  <- stated honestly, not forced to pass
  PLAN 10.2 / 10.3 under conservative implementation  FEASIBLE

III_B_TIME_FEASIBILITY   best FEASIBLE | nominal FEASIBLE | conservative CLEAN_SKIP
COMBINED_TIME_FEASIBILITY best FEASIBLE | nominal FEASIBLE
                          conservative  III-A only under 10.2/10.3, III-B CLEAN_SKIP

EXPECTED_III_A_RESULT_LOCK  2026-09-02T17:39 local  (NORMAL, nominal)
EXPECTED_III_B_RESULT_LOCK  2026-09-03T05:00 local  (NORMAL, nominal); CLEAN_SKIP acceptable
DEADLINE_PLAN_VALIDATED     true
```

**The full NORMAL plan is tight.** It closes at best and nominal implementation with a comfortable
margin, and it does **not** close if implementation runs conservative. That is precisely why the
fallback ladder exists and why §10.5 fires early. A prospectively valid reduced III-A plan remains
deadline-feasible under conservative implementation, and that is an acceptable outcome.

#### 13.3.5 `PHASE2_START` — real, not historical

```
PHASE2_START = the instant the independent final audit returns PASS with
               IMPLEMENTATION_GO = true AND this package is committed and frozen.
```

Implementation begins **immediately** at that instant. There is no fixed calendar start. The
superseded schedule hard-coded Monday 09:00; if authorization occurs on Sunday, waiting until
Monday discards 13 hours of usable buffer for nothing.

`BUDGET_HOURS = ABSOLUTE_EXPERIMENT_DEADLINE − PHASE2_START`. Reference cases: Sunday
2026-08-30 20:00 → **96 h**; the superseded Monday 2026-08-31 09:00 → 83 h.

**The absolute deadline and the §10.5 checkpoints do not move with `PHASE2_START`.** Each
checkpoint is derived as *deadline minus that plan's conservative tail*, so it is a fixed instant
valid for any start. `PHASE2_START` is recorded in `implementation_completion_receipt.json` and
every later stage receipt.

---

## 14. Result adjudication matrix (pre-registered)

Written **before any result exists**. Every reported claim must map to a permitted interpretation
in this table (stage A17).

| # | Outcome | Permitted interpretation | Prohibited interpretation | Paper value | Usable | Can close |
|---:|---|---|---|---|---|---|
| 1 | Smooth error increase as RVE falls | Linear accessibility tracks the calibrated direct-evidence ladder in this apparatus | Universal psychometric law; posterior uncertainty; object permanence | High — the headline graded result | Yes | Yes |
| 2 | Partial conditions near L0 | Weak/partial direct evidence still supports the frozen readout nearly as well as full visibility | The model "sees through" walls; hidden-state memory demonstrated | High | Yes | Yes |
| 3 | Partial conditions near L4 | The selected linear representation is fragile even with measured residual evidence | The model has no hidden-object representation anywhere | High | Yes | Yes |
| 4 | L1–L3 strong, L4 sharply worse | Weak direct evidence supports the frozen readout; complete occlusion adds a discontinuity | A causal memory module has been identified | High | Yes | Yes |
| 5 | MineWorld parallels the pixel baseline | The frozen neural and linear current-pixel readouts have a similar condition response | MineWorld merely copies pixels in general | Moderate | Yes | Yes |
| 6 | MineWorld exceeds the pixel baseline (partial CI excludes 0) | The frozen neural readout is more robust than **this linear current-frame pixel baseline** | It beats pixel histories, nonlinear vision, or all sensory baselines | Moderate–High | Yes | Yes |
| 7 | A temporal representation improves | Position information is more linearly accessible in the predeclared two-frame transform | Calibrated belief state; causal object permanence | Moderate | Yes | Yes |
| 8 | No temporal improvement | These two linear two-frame transforms do not rescue the selected family | No temporal information exists in MineWorld | Moderate | Yes | Yes |
| 9 | Context-age boundary pattern near `a = 16` | Pattern is consistent with finite-context loss in this coupled trajectory | Causal forgetting isolated from time and position | Moderate | Yes | Yes |
| 10 | No context-age boundary | No boundary effect detected at this power in this coupled design | Context length is irrelevant to the model | Low–Moderate | Yes | Yes |
| 11 | L0 control succeeds | Apparatus and readout are interpretable; the graded comparison is meaningful | — | Enabling | Yes | Yes |
| 12 | **L0 control fails** | Fresh apparatus/readout interpretability is limited; report the failure per §8.11 | Refit, replace identities, or tune thresholds after seeing it; interpret the graded curve | Moderate — a valid negative apparatus report | Yes, as apparatus-limited | **Yes** |
| 13 | Graded primary contrasts are null | The frozen readout shows no detectable graded response at this power in this apparatus | The model is invariant to observability; no hidden state exists | Moderate — publishable negative | Yes | Yes |
| 14 | Technical capture failure | Named technical blocker; retry the same frozen unit; disclose attrition | Reclassify as a scientific finding; replace identities | — | Depends on A8 | Yes if A8 passes |
| 15 | Technical extraction failure | Named technical blocker; re-extract same-spec | Change slice, layer, checkpoint, or preprocessing to "fix" it | — | Yes after repair | Yes |
| 16 | Fewer than 15 complete identities | Report the attrition and its technical cause; **no graded inferential claim** | Any graded claim; imputation; identity replacement; condition dropping | Low — methods/attrition report | No graded claim | **Yes**, as a no-claim closure |
| 17 | **P0 `NO_VALID_LADDER`** | The one-layer 1.16.5 stained-glass family does not yield three stable, separated RVE levels under this renderer/camera/target combination | Substitute another wall geometry, material family, or reduced condition count and proceed | Moderate — a real, reportable calibration finding | No graded claim | **Yes**, as a no-claim closure with a calibration result |

**No outcome in this table may establish:** calibrated posterior uncertainty; U2; U3; U4; causal
object permanence; or universal absence of hidden state in MineWorld.

All claims remain limited to one layout, one speed/noise regime, one checkpoint, a fresh
25-identity cohort (or a prespecified reduced cohort), the selected layers and representations,
linear probes, and the calibrated wall family.

---

## 15. Final scientific package and closure

### 15.1 Terminal evidence package

| Artifact | Content |
|---|---|
| Authority | this document |
| Machine authority | `EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json` |
| Authority hash | `AUTHORITY_SHA256` |
| Source closure | index digest + HEAD commit |
| Environment receipt | per host, per stage |
| Cohort manifests | production, pilot, folds, priority order, qualification receipt |
| A-prime port receipt | ported blob SHA-1s |
| FIR recovery receipt | kernels, residuals, verification counts |
| P0 calibration | manifest, image inventory, RVE table, bootstrap, masks |
| Selected ladder | `P0_SELECTED_LADDER`, `P0_SELECTION_RECEIPT` |
| P1 receipt | full verification list with observed values |
| P2 freeze | `P2_FREEZE_PACKAGE.json` + hash |
| Capture matrix | identity × condition state |
| Capture provenance | per-unit receipts, attempts, sentinels, ledger |
| Cohort validation | `cohort_closure_receipt.json` |
| Extraction inventory | per-array metadata |
| Extraction validation | `extraction_validation_receipt.json` |
| Tensor hashes | SHA-256 per array |
| Feature config | pooling and representation definitions + fixture hashes |
| Prediction lock | `PREDICTION_LOCK.json` + `.sha256` |
| Baselines | `baselines_receipt.json` |
| Primary results | three estimands, tests, Holm-3, intervals |
| Secondary results | five families with their limited claims |
| Bootstrap outputs | seeds, replicate summaries |
| Statistical report | full narrative with attrition disclosure |
| Figures / tables | each traceable to a locked prediction or receipt |
| Claim / adjudication matrix | `adjudication_receipt.json` |
| Final scientific summary | `FINAL_SCIENTIFIC_SUMMARY.md` |
| Closure receipt | `EXPERIMENT_III_CLOSURE_RECEIPT.json` |

### 15.2 When `EXPERIMENT_III_COMPLETE = true` may be emitted

Exactly the eight conditions of stage A19 (§6). Restated for emphasis: completion is defined by
**execution integrity**, not by the direction of the result. A null, negative, attrited,
apparatus-limited, or `NO_VALID_LADDER` outcome that was executed as frozen and reported honestly
is a **complete** Experiment III.

---

## 16. Final standard (Part III-A)

*Extended by §31, which states the combined III-A + III-B standard.*

This authority is successful only if it is simultaneously: scientifically prospective; complete;
self-contained; implementable; testable; fail-closed; diagnostic; recoverable; resumable;
hash-bound; deadline-aware; and outcome-independent.

It exists to answer, at any point in the lifecycle:

```
WHAT SHOULD HAPPEN?                  -> §6 stage PURPOSE / OPERATIONS
WHAT EXACTLY SHOULD BE BUILT?        -> IMPLEMENTATION_CHANGE_MATRIX.json,
                                        IMPLEMENTATION_TASK_GRAPH.json
WHAT SHOULD EXIST WHEN IT WORKS?     -> EXPECTED_ARTIFACT_INVENTORY.json, §6 EXPECTED OUTPUTS
HOW DO WE PROVE IT WORKED?           -> §6 REQUIRED EVIDENCE / PASS CONDITIONS
WHAT EXACTLY FAILED IF IT BREAKS?    -> BLOCKER_TAXONOMY.json, §6 BLOCKER CODES
CAN WE REPAIR IT?                    -> §9, §6 ALLOWED / FORBIDDEN REPAIRS
WHAT DOES THE REPAIR INVALIDATE?     -> §6 INVALIDATION SCOPE
WHERE DO WE RESUME?                  -> RECOVERY_AND_RESUME_RUNBOOK.md, §6 RESUME RULES
DOES THE SCIENCE REMAIN PROSPECTIVE? -> §9 boundary test; A12 prediction lock
WHAT HAPPENS NEXT?                   -> §6 NEXT AUTHORIZED STATE
```

---

# PART III-B — BAYESIAN POSTERIOR-UNCERTAINTY MODULE

*Added by Phase 1 Amendment 1, 2026-08-30. Everything above (§0–§16) is Part III-A and is
unchanged by this amendment except for the two lane-clamp corrections explicitly marked in §2.4.3
and §3.3, which repair a Phase-1 operationalization defect and change no Phase 0 decision.*

**Controlling Phase 0 amendment:**
`docs/experiment_iii/final_authorities/PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.md`
SHA-256 `da32ff953f0734b6de09b3733d54ad72d2fd22266ec51d0eeefe714fee231554`
machine form SHA-256 `7c769f3b5c5bc94d4024d3e81aba51eb60a795ef261a1cb6b24673253f5dc3cb`

---

## 17. III-B identity, the III-A invariant, and optionality

### 17.1 What III-B is

**Experiment III-B — Bayesian posterior uncertainty under objectively manipulated process noise.**

Namespace `r73-grado-v1-b`. Condition **`L4` opaque only**. The manipulation is **process noise
`q`**, which changes the *generative process* and therefore makes the oracle posterior spread
objectively different at matched occlusion age, while image evidence, condition, wall material,
camera, layout, speed, and the readout are all identical.

This is the manipulation the glass ladder could not provide. Weakening direct evidence with
stained glass changes the observation channel, not the latent dynamics; posterior spread is
identical across `L0`–`L4`. Varying `q` changes the dynamics, with a known ground-truth answer.

### 17.2 THE III-A INVARIANT — restated normatively

```
NO III-B STAGE IS A PRECONDITION OF ANY III-A SCIENTIFIC COMPLETION STAGE.

III-A MUST CLOSE IDENTICALLY WHETHER III-B RUNS, SKIPS, FAILS, OR IS DROPPED FOR TIME.
```

Enforced concretely, and audited:

- No III-A lifecycle state (`A0`–`A19`) lists any `B-*` state in its entry conditions.
- No III-A artifact requires a III-B artifact to validate.
- No III-A estimand, fold, prediction, baseline, or statistic depends on a III-B cell.
- III-A's cohort, target rows, folds, readout, baselines, and analysis families are unchanged.
- A III-B `TECHNICAL_FAIL`, `CLEAN_SKIP`, or `SCIENTIFIC_NULL` leaves III-A closure untouched.
- III-A `A19` closure conditions make no reference to III-B.

**Never delay III-A closure to save III-B.** III-B is valuable; III-A is indispensable.

### 17.3 Optionality

III-B is **optional**. Its launch, degradation, and abandonment are decided **exclusively** by
time, technical state, and available resources (§29.5, §29.6). **No scientific outcome — from
III-A, from the III-B pilot, or from anywhere else — may be consulted.** A `CLEAN_SKIP` is a
pre-registered, honourable outcome and is not a failure of the program.

### 17.4 Claim restrictions specific to III-B

Everything §1.7 prohibits remains prohibited. **U4, causal intervention, steering, and causal
object permanence remain excluded**, and no U2/U3 result may be taken to imply any of them.

Additionally:

- A positive U2 result licenses only bounded wording: **"uncertainty-relevant information
  tracking oracle posterior spread"**, or **"a partial belief-state signature"**.
- **"Calibrated Gaussian belief state under this apparatus"** requires the strongest frozen
  conjunction of §28, including scale calibration.
- No result may be described as showing the model **uses** its uncertainty.
- No U2 result may be described as uncertainty representation until it survives the clock and
  q-category confound controls of §23.
- All claims are limited to one layout, one speed, one checkpoint, condition `L4`, the three
  frozen `q` levels, linear probes, and the selected representation.

---

## 18. VERIFY resolution — every hook closed against actual source

Full evidence: `III_B_VERIFY_RESOLUTION_RECEIPT.json`. Summary, with the consequences that are
now frozen:

| Hook | Result | Consequence |
|---|---|---|
| **VERIFY-1** noise model | `RESOLVED_POSITION_LEVEL_RANDOM_WALK` | Fable's assumed law is correct; the scalar Gaussian propagation oracle is valid and frozen |
| **VERIFY-2** innovation pairing | `RESOLVED_GENERATOR_NATIVE_PAIRING` | no new mechanism needed; q=0.05 reproduces frozen behavior bit-identically |
| **VERIFY-3** folds | `RESOLVED_BY_CONSTRUCTION` | fold membership is a property of the identity; q never enters it |
| **VERIFY-4** VIS availability | `RESOLVED_NEW_FORWARDS_REQUIRED_AND_WINDOW_RELOCATED` | visible rows move **post-occlusion**; `VIS_ROWS = 6` |
| **VERIFY-5** q=0.2 support | `RESOLVED_FEASIBLE` | 95.4% of candidates qualify at all three q; 25/25 A-prime identities qualify |
| **VERIFY-6** FIR at new q | `RESOLVED_KERNELS_REMAIN_AUTHORITATIVE` | kernels unchanged; a pilot coherence check is frozen |
| **VERIFY-7** RVE independence | `RESOLVED_NO_NEW_P0` | `III_B_REQUIRES_NEW_P0 = false` |

### 18.1 VERIFY-1 — the generator applies noise to **position**

Traced end to end:

```
src/mineocclude/data/noise_schedule.py  generate_noise_schedule(seed, n, q, dt):
    std        = sqrt(q * dt)
    draws      = Generator(PCG64(seed)).standard_normal(n)
    noise_draw = z * std

fabric/.../server/SheepController.java  step(commandedVelocity):
    eta      = schedule.nextNoiseDraw()
    proposed = axisPos + commandedVelocity * dt + eta
    axisPos  = cfg.clampAxis(proposed)

fabric/.../server/NoiseSchedule.java  load(): verifies per-row sqrt(q*dt) scaling and header q
fabric/.../server/MineOccludeServer.java: startspec ALREADY accepts q as a command argument
```

**The frozen law is therefore:**

```
x[t+1] = clamp( x[t] + s*v*dt + w[t] ),      w[t] ~ N(0, q*dt), i.i.d.
```

Noise perturbs **position only** — not velocity, not acceleration. Fable's assumed law is
supported, and the scalar Gaussian propagation oracle of §20 is valid.

**Consequence for implementation:** the apparatus is *already* q-parameterized end to end
(Python schedule generator, JSON header, Java loader, `startspec`, `SheepController`). The only
component that hard-codes `q` is the Python **cohort generator** via the module global
`MOTION_NOISE_Q` (`src/mineocclude/regime_a.py:30`) — which III-A item `C01` already
parameterizes. **III-B requires no apparatus change.**

### 18.2 VERIFY-2 — innovation pairing is generator-native

`generator.standard_normal(n)` depends only on `(seed, n)`. `q` enters **only** through the
scalar `std = sqrt(q*dt)`. The schedule row already stores `standard_normal_draw` separately from
`noise_draw`. Verified:

- standard normals identical across `q ∈ {0.0125, 0.05, 0.2}` for a fixed seed: **true**;
- `noise_draw == standard_normal_draw * sqrt(q*dt)` exactly: **true**;
- `noise_draw` ratio between any two `q` is exactly `sqrt(q_a/q_b)`, uniform across ticks.

**Frozen pairing rule:** the same identity at different `q` shares one seed and therefore one
standard-normal innovation sequence, rescaled by `sqrt(q*dt)`. This is the generator's native
behavior; no new mechanism is introduced.

**q = 0.05 regression, verified:** the generalized schedule-driven path at `q = 0.05` is
bit-identical to the legacy inline form **and** reproduces the real frozen A-prime path hash
`b5803943e515ea633cc4dd80ddeaf349db5cb99d11980febdc3f13d7f84a56b7`.

**Reference provenance, bound (repair pass 2).** The hash is **not** in the `v0.4` manifest that
carries the FIR recovery. It is the `expected_path_sha256` of unit **`a2x_t01_wall`** in the
**`v0_3`** manifest, bound at the same commit:

| Field | Value |
|---|---|
| commit | `f2bc2c8082e77f9c3f9e089f2fb1a20b11a052a8` |
| path | `docs/status/integration/regime_a_prime_qualification_v0_1/prospective_development_authority_v0_3/stage2_locked_manifest.json` |
| blob SHA-1 | `fb93a08ba2d71c28c9929469d9b34bf8fc6de17b` |
| bytes | 270,672 |
| manifest SHA-256 | `ad718685b33030a0c0de405cd9d3abb737c3f3e9d087ad7c78768fe151855eb8` |
| unit / direction | `a2x_t01_wall` / `LEFT_TO_RIGHT` |
| seed = noise_seed | `2154560968567132226` |
| `start_world_x` / speed / `q` / frames | `-7.8` / `2.0` / `0.05` / `180` |

Machine form: `fir.d2_regression_reference`. Phase 2 reconstructs `D.2` from **this package plus
the git object database only** — no historical draft directory is required. This regression
fixture is
mandatory (§D.2) and must land **before III-A P1**.

### 18.3 VERIFY-4 — visible control rows move post-occlusion, and `VIS_ROWS = 6`

Two source facts settle this.

1. **III-A extracts no visible rows.** III-A's extraction scope is exactly the 19 counterfactually
   fully-occluded target rows. Visible controls therefore require **new forwards**.

2. **A pre-occlusion visible window is infeasible.** A model forward needs a complete 16-pair
   context, so the row index must be `>= 15`. The left visible band ends at
   `x = -6.1163518773`, and the sheep starts near `-7.8` travelling 0.1 blocks/tick, so the
   pre-occlusion stable-visible span ends at median frame index **~12–13**. Essentially no
   pre-occlusion visible row carries a complete context: **0/25** A-prime identities at
   `q_low`/`q_mid`, 1/25 at `q_high`.

**Frozen resolution — the visible control rows are taken POST-occlusion:**

> the last `VIS_ROWS` **consecutive** model frames of the capture that are counterfactually
> `EXTENT_FULLY_VISIBLE`, are **clamp-free**, and have a **complete 16-pair context**.

The clamp-free requirement is load-bearing: the trajectory tail is pinned at the lane bound for
~20–25 ticks, and a pinned sheep has no motion and no positional variance, which would void both
the position positive control and the q-perception diagnostic.

**`VIS_ROWS = 6`** (the provisional value 8 is superseded). The clamp-free visible re-entry band
is `|x| ∈ [7.1163518773, 8.0]` = 0.8836 blocks = 8.8 ticks on the `LEFT_TO_RIGHT` side, because
the occluded interval `[-3.4968, 4.4968]` is centred at `+0.5`, not at 0. Eight rows is therefore
marginal there (62–82% of candidates), while six is comfortable:

| q | LTR run ≥ 6 | LTR run ≥ 8 | RTL run ≥ 6 | RTL run ≥ 8 |
|---|---:|---:|---:|---:|
| 0.0125 | 100.0% | 97.2% | 100.0% | 100.0% |
| 0.05 | 99.2% | 81.8% | 100.0% | 100.0% |
| 0.2 | 87.5% | 62.3% | 99.5% | 99.5% |

**Visible-row availability is NOT a qualification gate.** It is best-effort with reported
coverage. Visible rows serve descriptive controls only (§24) and never enter the primary U2/U3
estimands, so a cell lacking them simply contributes no visible-control rows and the primary
analysis is unaffected. Blocker `B_VIS_UNAVAILABLE` is informational.

### 18.4 VERIFY-5 — `q = 0.2` is feasible

Under the corrected lane-clamp gate (§2.4.3):

| q | LTR qualify | RTL qualify |
|---|---:|---:|
| 0.0125 | 100.0% | 100.0% |
| 0.05 | 99.8% | 99.8% |
| 0.15 | 98.4% | 96.4% |
| 0.2 | 97.0% | 93.8% |

**95.4%** of fresh candidates qualify simultaneously at all three primary `q`; 97.4% at the
fallback triple. All **25/25** real A-prime speed-2.0 identities qualify at every `q`. The
dominant rejection at high `q` is `LANE_CLAMP_IN_PROTECTED_PREFIX`, as expected.

`q = 0.2` is feasible with wide margin. The live pilot gate (§29.4) is still required.

### 18.5 VERIFY-6 — the FIR kernels remain authoritative at new `q`

The FIR is a **state-to-render temporal alignment calibration of the capture pipeline** — a
property of server-tick → client-render timing, not of the motion statistics. `q` rescales
innovation magnitude; it changes neither the tick cadence, the render pipeline, nor the alignment
delay. Speed, `dt`, layout, camera, and client are all unchanged. **The kernels are unchanged and
may not be refitted at new `q`** — refitting is a §9.2 scientific change.

**Frozen coherence check**, run at `B-PILOT`, per direction, per new `q`:

1. `normalized_kernel` accepts the frozen taps unchanged (nonnegative, unit mass, not pure delay);
2. every III-B target row satisfies `t >= 8`, so the 9-tap kernel has complete causal history;
3. FIR-aligned labels recomputed from the replayed path reproduce the manifest labels to
   `<= 1e-9` blocks;
4. the kernel mode lag precedes its first moment, as in the A-prime frozen forensic reference;
5. the causal FIR beats the best pure integer-tick delay on the pilot trajectory, per direction.

Failure is `B_ORACLE_MISMATCH`.

### 18.6 VERIFY-7 — no new P0

III-B varies only `q`, at condition `L4` (`minecraft:stone`) exclusively. No glass material is
introduced, removed, or changed. RVE is a condition-level image-evidence coordinate over the wall
material family and is invariant to `q`, which alters only the target trajectory.

```
III_B_REQUIRES_NEW_P0 = false
```

The P0-selected ladder is reused unchanged. III-B capture batches remain subject to the existing
sentinel machinery (cheap, frozen placements, no new calibration and no new envelope).

---

## 19. III-B cohort, conditions, and target semantics

### 19.1 Cells

| Item | Value |
|---|---|
| Identities | the **same 25 III-A production identities**; **no new identities** |
| Condition | `L4` only, `minecraft:stone`, `Scene.NORMAL` |
| `q_low` | **0.0125** blocks²/s — new capture |
| `q_mid` | **0.05** blocks²/s — **reused from III-A, not recaptured** |
| `q_high` | **0.2** blocks²/s — new capture |
| `q_high` fallback | **0.15** blocks²/s — technical trigger only (§29.4) |
| New production captures | **50** (25 × `q_low` + 25 × `q_high`) |
| New pilot captures | **4** (`e3_p90`, `e3_p91` × {`q_low`, `q_high`} × `L4`) |
| Combined production captures | 125 + 50 = **175** |

Identity naming: `e3_t01` … `e3_t25` unchanged; a III-B capture unit is
`{identity}__L4__q{q}` (e.g. `e3_t07__L4__q0.2000`), with `q` formatted to four decimals.
Episode IDs use the reserved block `87001`–`87999`, disjoint from III-A's `86001`–`86999`.

### 19.2 The `q_mid` reuse is prospectively declared

III-B reuses the III-A `L4` `q = 0.05` cell as its middle dose. **This is declared before any
III-A outcome exists** — before implementation, capture, inference, or analysis. It is a
pre-registered design economy, not a post-hoc selection of favourable data, and it must be
restated in the final scientific package.

The III-A `q = 0.05` **occluded** rows are reused exactly as extracted. Only the **visible
control rows** require new inference on those existing captures — **no recapture**.

**Capture-session disclosure (required).** The reused `q_mid` rows come from the **III-A**
capture session (`A7`); `q_low` and `q_high` are captured in a **separate, later III-B session**
(`B-CAP`) on the same rig under the same frozen pins. Any session-level effect — client build
state, driver state, rig warm-up, thermal state — is therefore confounded with the `q_mid`
**level**, not with the `q_low`-versus-`q_high` contrast.

- **U2-S1 is not threatened**: it contrasts `q_high` against `q_low` only, both fresh and paired
  within one session. `q_mid` does not enter it.
- **U3-S2 is not threatened**: it is `b(q_high) − b(q_low)`; `q_mid` does not enter it.
- **U2-S3 and the `q_mid`-inclusive calibration cells may carry a session effect** and must say
  so.

`q_mid` is **not** recaptured for this reason: doing so would cost 25 captures and ~2 h of rig
time to remove a confound that touches neither decisive statistic, and would endanger the
Thursday hard stop. The proportionate remedy is disclosure plus a descriptive sensitivity
analysis — U2-S3 restricted to the two fresh doses where it is defined, and the calibration
battery reported both with and without `q_mid` cells. The disclosure is mandatory in the III-B
result package and in the manuscript.

### 19.3 Target semantics — τ is matched, frame index is not

**This is the single most important III-B semantic and must not be improvised later.**

Because `q` rescales the innovations, the same identity's trajectory *differs* between `q` cells.
Its counterfactual occlusion window therefore also differs. Consequently:

> Each `(identity, q)` cell derives **its own** 19-row target window and **its own** visible-row
> window, from **its own** path, using the **identical frozen III-A rules** (§2.4, §2.5, §4.6):
> the first 19 consecutive counterfactually `EXTENT_FULLY_OCCLUDED` rows in ascending model-frame
> order.

Matching across `q` is by **occlusion age τ**, not by absolute model-frame index:

```
tau = 1  at the cell's own first fully-occluded target row
tau = 19 at its last
```

The U2 matched-τ contrast (§22.1) compares `sigma_hat(q_high, i, tau)` with
`sigma_hat(q_low, i, tau)` at **equal τ**, which is the scientifically matched comparison: equal
elapsed occlusion, equal context structure, different objective posterior spread.

Comparing at equal absolute frame index would be wrong and is forbidden
(`B_TAU_ALIGNMENT_ERROR`).

### 19.4 Qualification

Each `(identity, q)` cell must satisfy the full frozen III-A qualification set of §2.4 —
including the corrected lane-clamp gate — evaluated on that cell's own path. An identity is a
**complete III-B triple** when all three of its `q` cells qualify and capture successfully.

Empirically (§18.4) **95.75%** of candidates qualify at all three `q`. The III-A cohort
generator therefore requires, at `A1`, that every admitted identity qualifies at **all three
frozen `q`** — a cheap, outcome-blind, purely geometric extra gate that guarantees III-B is
executable on the frozen cohort. It is **§2.4 qualification gate 12**, and it is **evaluated
before the cohort is materialized or frozen**.

**Ordering is the whole point.** At a per-identity rate of `0.9575`, the probability that at
least one of 25 independently admitted identities fails is `1 − 0.9575²⁵ = 0.661`. Applying the
requirement *after* materialization — as the superseded task ordering did, with `IB02` depending
on `I02` — would fail about two runs in three and would leave `B-GEN` with no admissible
recovery: cohort regeneration is forbidden once any capture exists and is never permitted on the
basis of an outcome. The dependency is therefore **inverted**: `IB02` (the `q`-generalized path
and qualification primitive) and `IB03` (its `q = 0.05` bit-identity regression guard) are
**prerequisites of `I02`**, both inside `A1`, and `I02` **fails closed** with
`COHORT_ALL_Q_PRIMITIVE_MISSING` if either is absent or failing.

This is III-A change-matrix item `C02` extended by `CB02` and guarded by `CB03`. It alters no
III-A scientific value — no estimand, no condition, no readout, no statistic — and it does **not**
make III-A depend on III-B: gate 12 is evaluated entirely inside `A1` from seeds, geometry and
timing, consumes no III-B artifact and no III-B **runtime stage**, and is applied identically
whether III-B later runs, skips, fails or is dropped. **The same final III-A cohort exists either
way.** If III-B is skipped, gate 12 is simply an unused additional admission constraint.

`B-GEN` therefore **re-verifies** rather than discovers. A `B-GEN` qualification failure at a
binding `q` means the two evaluations disagree — an implementation defect — and never regenerates
the III-A cohort. Cells at the non-binding `q = 0.15` fallback were not covered by gate 12; if
the fallback is triggered and some fail, that is III-B-local attrition handled by the §29.6 drop
ladder.

### 19.5 Folds — VERIFY-3

All `q` variants of one identity inherit that identity's III-A **outer fold** and **inner
rotation**. Fold membership is a property of the identity, assigned by `(seed, identity_id)`
within direction; `q` is a within-identity factor and never enters fold assignment. Cross-`q`
identity leakage is therefore impossible by construction, and is tested (§D.5).

---

## 20. The Bayesian oracle

Full specification: `III_B_ORACLE_SPECIFICATION.json`.

The oracle is derived **entirely from frozen generator and apparatus parameters**. It **may not**
fit parameters from MineWorld activations, **may not** fit `q`, and **may not** use any
scientific outcome.

### 20.1 Derivation

From the verified law `x[t+1] = x[t] + s·v·dt + w[t]`, `w ~ N(0, q·dt)`, and the frozen FIR label
`y[t] = Σ_{k=0..8} h_k · x[t−k]`:

Let `t0` be the last counterfactually **not**-fully-occluded row, where the oracle treats the
state as known (posterior collapses under direct evidence). For `τ = t − t0`:

```
y[t0+tau] = x[t0] + s*v*dt*(tau - gbar) + sum_{j=1..tau} H(tau - j) * w[t0+j]
```

where `H(m) = Σ_{k≤m} h_k` is the cumulative normalized kernel mass (`H(m) = 1` for `m ≥ 8`) and
`gbar = Σ_k k·h_k` is the frozen FIR group delay. Therefore:

```
POSTERIOR MEAN      mu_tau     = x[t0] + s*v*dt*(tau - gbar_direction)

POSTERIOR VARIANCE  sigma2_tau = q * dt * SUM_{m=0}^{tau-1} H_direction(m)^2      <-- EXACT

POSTERIOR SIGMA     sigma_tau  = sqrt(sigma2_tau)                     in blocks
```

### 20.2 The affine form is WRONG below τ = 8 — do not use it

For `τ ≥ 8` the exact form reduces to the familiar affine expression:

```
sigma2_tau = q*dt*(tau + c_direction),     c_direction = SUM_{m=0}^{7} H(m)^2 - 8
```

**But `c_direction` is negative in both directions**, so the affine expression returns a
**negative variance** at small τ and is catastrophically wrong exactly where the primary U2
support begins:

**The boundary is direction-specific.** The affine expression flips sign at `τ = −c_direction`:
`4.3555` for `LEFT_TO_RIGHT` and `3.3959` for `RIGHT_TO_LEFT`. There is no integer `τ` at which
it is exactly zero.

| direction | `gbar` (ticks) | `c_direction` | affine **negative** for | affine **positive** for | affine error at τ=1 |
|---|---:|---:|:--|:--|---:|
| `LEFT_TO_RIGHT` | 3.339950418234 | −4.355500526065 | `1 ≤ τ ≤ 4` | `τ ≥ 5` | 110,139% |
| `RIGHT_TO_LEFT` | 2.670496191400 | −3.395856222447 | `1 ≤ τ ≤ 3` | `τ ≥ 4` | 995,688% |

```
AFFINE_THRESHOLD_LTR = 4      (last negative integer tau)
AFFINE_THRESHOLD_RTL = 3      (last negative integer tau)
```

**`τ = 4` is POSITIVE in the `RIGHT_TO_LEFT` direction.** A test that demanded negativity at
`τ = 1…4` in *both* directions would fail a correct implementation; `D.7` is rewritten to assert
the exact direction-specific boundary instead. These two integers live in
`III_B_ORACLE_SPECIFICATION.json` as `affine_last_negative_tau`, and the machine authority
reproduces them verbatim — the superseded machine-authority values of 5 and 4 are corrected.

Since the primary U2 support is **τ = 1…15**, the **exact cumulative-mass form is mandatory** and
is what this authority freezes. Using the affine form over the primary support would be a silent,
fatal error. The affine form may appear only as an asymptotic remark for `τ ≥ 8`.

### 20.3 Frozen constants

```
LEFT_TO_RIGHT   H(0..8) = [0.055221, 0.150776, 0.323679, 0.579917, 0.752511,
                           0.902807, 0.931188, 0.963950, 1.000000]
RIGHT_TO_LEFT   H(0..8) = [0.015513, 0.157611, 0.539606, 0.792598, 0.923999,
                           0.933258, 0.966918, 1.000000, 1.000000]
```

`S(τ) = Σ_{m=0}^{τ−1} H(m)²` for τ = 0…19 is tabulated in the oracle specification and is
**q-independent**.

Representative `sigma_tau` in blocks (`LEFT_TO_RIGHT`):

| τ | q=0.0125 | q=0.05 | q=0.2 |
|---:|---:|---:|---:|
| 1 | 0.001381 | 0.002761 | 0.005522 |
| 5 | 0.025411 | 0.050821 | 0.101643 |
| 10 | 0.059395 | 0.118791 | 0.237582 |
| 15 | 0.081565 | 0.163130 | 0.326259 |
| 19 | 0.095670 | 0.191341 | 0.382681 |

### 20.4 Two consequences that shape the analysis

**(a) The cross-`q` σ ratio is exactly `sqrt(q_a/q_b)` and is τ-independent.** Because
`sigma_tau = sqrt(q) · sqrt(dt·S(τ))`, the ratio is exactly **4.0** between `q_high` and `q_low`,
and **2.0** between adjacent levels, at every τ. The oracle therefore predicts a clean
multiplicative separation with no free parameter.

**(b) This is why the primary scale is LINEAR σ.** On the linear scale the matched-τ separation
is

```
sigma_high(tau) - sigma_low(tau) = (sqrt(q_high) - sqrt(q_low)) * sqrt(dt * S(tau))
```

which **grows with τ** and therefore carries the q-dependent uncertainty-growth interaction that
U3 tests. On the log scale the separation collapses to the constant `0.5·log(q_high/q_low)`,
destroying exactly that interaction. **`log σ` is descriptive only** and may never be silently
substituted for the primary target.

### 20.5 Power caveat, recorded prospectively

`sigma_tau` spans ~0.0014 blocks (τ=1, `q_low`) to ~0.383 blocks (τ=19, `q_high`) — a
fine-grained target relative to III-A's occluded position RMSE of ~2.07 blocks. This is recorded
as an interpretation and power caveat, **not** as a gate, and must be disclosed in the final
report. A null U2 under this dynamic range is a legitimate, publishable `SCIENTIFIC_NULL`.

### 20.6 Oracle validation receipt

`B-ORC` must emit `iii_b_oracle_validation_receipt.json` proving: the exact form is implemented
(not the affine one); `S(τ)` matches the frozen table to `1e-12`; `sigma_tau > 0` for every τ in
1…19 at every `q`; the cross-`q` ratio equals `sqrt(q_a/q_b)` to `1e-12`; and no oracle quantity
depends on any activation, prediction, or fitted parameter. Failure is `B_ORACLE_MISMATCH`.

---

## 21. III-B representations, target, and readout

### 21.1 Primary uncertainty target

```
PRIMARY_UNCERTAINTY_TARGET = sigma_x,tau   in blocks,  LINEAR scale
```

The probe regresses the frozen representation onto the **oracle** `sigma_tau` (§20). `log σ` is
descriptive only. The primary target may **not** be switched after results (§9.2).

### 21.2 Representations — no search

| Role | Cell |
|---|---|
| **Primary** | `L19 \| COARSE_2X6_CONCAT \| CURRENT` |
| **Secondary (one, predeclared)** | `L19 \| COARSE_2X6_CONCAT \| CURRENT_MINUS_PREVIOUS` |

**Forbidden:** layers 4 and 10; BEST-K; alternative pooling; PCA search; MLP; nonlinear rescue;
any other representation. III-B is an uncertainty test, not another representation search.

### 21.3 Readout recipe — inherited from III-A unchanged

```
alpha grid                {0.1, 1, 10, 100, 1000}
intercept                 unpenalized
standardization           training-only
solver                    high-dimensional dual solve when p > n
outer folds               the 5 frozen III-A identity folds
inner rotations           the 4 frozen III-A inner rotations
alpha selection           identity-macro inner-validation criterion
tie-break                 smallest alpha
held-out tuning           FORBIDDEN
```

### 21.4 Training semantics

The primary U2 probe is trained **pooled across `q` cells** on the outer-training identities.
Pooling is required: a probe trained within a single `q` could not express a `q`-dependent σ, and
the matched-τ contrast would be vacuous.

```
Primary U2/U3 support     tau = 1..15
Boundary secondary        tau = 16..19
```

The τ ≤ 15 restriction is the frozen III-A context-boundary fact (§5.4): the last potentially
informative pre-occlusion pair is in context for `τ ≤ 15` and absent for `τ ≥ 16`.

Held-out predictions for every `(identity, q, tau, model)` cell are emitted and hash-locked
**before any III-B statistic is opened**, exactly as in III-A `A12`.

---

## 22. U2 authority

`FINAL_U2_ANALYSIS_FAMILY` contains exactly three statistics. The inference unit is the
**identity**. Rows are never independent units.

### 22.0 The frozen inferential procedure — intervals report, Holm decides

**This section is normative for every inferential statistic in III-B.** The superseded phrase
"bootstrap 95% CI excludes zero after Holm" named no executable procedure: Holm adjusts
*p-values* (or an explicitly adjusted confidence level), and a "CI after Holm" is not a unique
construction. It is replaced by the following.

```
CI_ROLE   = EFFECT_SIZE_REPORTING
HOLM_ROLE = FAMILYWISE_HYPOTHESIS_DECISION
```

**Intervals.** Every reported interval is an **ordinary two-sided 95% whole-identity bootstrap
percentile interval**, `B = 10,000`, resampling identities with replacement and recomputing the
entire statistic — including any ranking, residualization and fold-wise pooling — inside each
replicate. Its confidence level is **not** adjusted for multiplicity and it carries **no**
familywise guarantee. **No interval in this authority is a "Holm-adjusted CI"; that phrase is
forbidden.**

**Decisions.** Significance is declared **only** by a Holm-adjusted p-value.

**p-value construction, per statistic:**

| Statistic | H₀ | H₁ | Sided | Construction |
|---|---|---|---|---|
| U2-S1 | `Dbar ≤ 0` | `Dbar > 0` | one | within-identity `q`-assignment **permutation**, `B = 9,999` |
| U2-S2 | `ρ ≤ 0` | `ρ > 0` | one | whole-identity **bootstrap inversion**, `B = 10,000` |
| U2-S3 | `π ≤ 1/6` | `π > 1/6` | one | whole-identity **bootstrap inversion**, `B = 10,000` |
| U3-S1 | pooled slope `≤ 0` | `> 0` | one | whole-identity **bootstrap inversion**, `B = 10,000` |
| U3-S2 | `Δ ≤ 0` | `Δ > 0` | one | whole-identity **bootstrap inversion**, `B = 10,000` |

**Permutation p-value (U2-S1 only).** Permute `q_low` / `q_high` labels **within** each identity
across that identity's own cells, holding τ, identity, fold and every other structure fixed.
`p = (1 + #{D_perm ≥ D_obs}) / 10,000`.

**Bootstrap-inversion p-value — the exact algorithm:**

```
1. T_obs   = the statistic on the locked held-out predictions
2. T*_b    = the complete statistic recomputed in each of B = 10,000 whole-identity
             bootstrap replicates, under the P2-frozen seed
3. CI      = percentiles 2.5 and 97.5 of {T*_b}          (unadjusted; reporting only)
4. p       = (1 + #{T*_b <= T_null}) / (B + 1)           (one-sided)
5. T_null  = 0 for U2-S2, U3-S1 and U3-S2 ; 1/6 for U2-S3
           (U2-S1 uses the permutation null above, never inversion)
6. p is clipped to [1/(B+1), 1] and is never exactly 0
```

One resampling pass serves both the interval and the p-value for a given statistic.

**Holm, step-down, monotonicity enforced.** With `m` the frozen family size and p-values sorted
ascending, ties broken by the frozen member order:

```
padj_(1) = min(1, m * p_(1))
padj_(k) = min(1, max( padj_(k-1), (m - k + 1) * p_(k) ))
declare SIGNIFICANT  iff  padj <= alpha = 0.05
```

**Families.** U2 = `{U2-S1, U2-S2, U2-S3}` in that order, `m = 3` (`m = 2` at drop `LEVEL 1`,
where U2-S3 is not estimable). U3 = `{U3-S1, U3-S2}`, `m = 2`, hierarchical on U2.

**Outside every family, never Holm-corrected:** U3-S3; the entire calibration battery (§27); the
context-boundary secondary (§25); the eight confound controls (§23). Entering any of these into
a Holm family, or altering a family after results exist, is `B_U2_FAMILY_ALTERED`. Departing
from this procedure in any other way is `B_INFERENCE_PROCEDURE_MISMATCH`.

### 22.1 U2-S1 — matched-τ contrast (the primary U2 statistic)

```
per identity i, per tau in 1..15:
    D_i,tau = sigma_hat(q_high, i, tau) - sigma_hat(q_low, i, tau)

identity statistic:    D_i  = mean over tau in 1..15 of D_i,tau
experiment statistic:  Dbar = macro mean over identities of D_i

interval:   whole-identity bootstrap, B = 10,000, ordinary two-sided 95% percentile CI
            (UNADJUSTED; effect-size reporting only)
p-value:    within-identity q-assignment permutation, B = 9,999, one-sided
            p = (1 + #{perm >= obs}) / 10,000        -> enters the Holm family
hypothesis: Dbar > 0   (oracle predicts sigma_high = 4 * sigma_low)
```

**The permutation null is the load-bearing control.** Within each identity, the `q_low` and
`q_high` labels are permuted across that identity's own cells, holding τ, identity, fold, and
everything else fixed. This destroys the `q`→σ association while preserving every clock,
identity, and context structure. If `Dbar` is not extreme against this null, the apparent effect
is not `q`-driven. Exactly `B = 9,999` permutations plus the observed statistic gives an exact
`(1 + #{perm ≥ obs}) / 10,000` p-value.

### 22.2 U2-S2 — proposal-aligned conditional association

```
partial rank association:   rho( sigma_hat, sigma_oracle | tau x direction )
```

**Conditioning is on `τ × direction`, not τ alone.** *Corrected by the final authority repair
pass (defect B5).* The oracle σ depends on **direction** through the direction-specific
FIR-derived alignment term `H_direction(m)`: `S(τ)`, and therefore `sigma_oracle`, differ
between `LEFT_TO_RIGHT` and `RIGHT_TO_LEFT` at equal τ. After **τ-only** residualization the
residual direction contrast survives in *both* rank vectors, so a decoder that reads only
direction — carrying **literally zero** `q` sensitivity — could produce a positive U2-S2. U2-S1
and U2-S3 are protected by their within-identity contrasts and needed no change; U2-S2 did.

**Frozen operationalization** (30-cell `τ × direction` residualization):

1. Pool all `(identity, q, tau)` cells with `tau in 1..15` over held-out predictions, across all
   in-scope `q`.
2. **Rank first:** rank-transform `sigma_hat` and `sigma_oracle` separately over the **pooled**
   set, average ranks for ties.
3. **Residualize second:** regress each rank vector separately, by ordinary least squares, on
   an intercept plus the **30 `τ × direction` cell indicators**
   (`τ = 1…15` × `{LEFT_TO_RIGHT, RIGHT_TO_LEFT}`); retain the residuals.
4. `rho` is the Pearson correlation of the two residual vectors.
5. Inference at the **identity** level: whole-identity bootstrap, `B = 10,000`, recomputing
   ranking **and** residualization inside every replicate; ordinary unadjusted two-sided 95%
   percentile CI, and the one-sided bootstrap-inversion p-value of §22.0.

**Solver, exactly.** The design `[1 | 30 indicators]` is rank deficient by one, so the
coefficients are not unique — but the minimum-norm least-squares **fitted values and residuals**
are, and they are the only quantities used. Use `numpy.linalg.lstsq(design, y, rcond=None)`.

**Canonical equivalent form (the definition of record for tests).** The residual of a rank
vector is exactly `rank − mean(rank within its own (τ, direction) cell)`. Implementations may
use within-cell mean centring directly; it is numerically identical to the pseudoinverse fit.

**Zero-variance residual — frozen (defect A2).** After residualization, if
`Var(r_hat) ≤ TOL` **or** `Var(r_oracle) ≤ TOL`, then **`rho := 0.0` exactly** and the
one-sided p-value is **`1.0` exactly**. `TOL = 1e-15 × Var(the corresponding
unresidualized rank vector)` — scale-free; at the frozen 1,125-cell design that is
`1.05e-10`, about `1.4e9` above the numerical round-off floor and about `3.3e12` below the
variance of a genuine residual. The statistic is **never** `NaN`, missing, skipped or
positive, and **no decision may rest on an IEEE comparison against `NaN`**. Bootstrap
replicates in this case are **retained** with `rho* = 0.0`, never dropped. The case is
reported via `U2_S2_ZERO_VARIANCE_CASE` with its replicate count. With `rho = 0.0` and
`p = 1.0`, U2-S2 fails its clause and `U2_POSITIVE` cannot be declared.

**Edge cases, frozen.** A `(τ, direction)` cell holding exactly one observation yields residual
exactly `0.0` for both rank vectors and is **retained**, not dropped. An empty cell contributes
nothing. A bootstrap replicate may contain identities of only one direction; the centring is
still well defined and the replicate is retained, with the count of single-direction replicates
reported.

**The `D.11` negative control is a `(τ, direction)` decoder, not a direction-only one.** The
oracle's direction ordering **flips** with τ (LTR > RTL at τ ∈ {1,2}, RTL > LTR for τ ≥ 3), so a
decoder constant within direction largely cancels and measures `ρ|τ = −0.067`. The confound is
carried by the τ-by-direction **interaction**. The frozen fixture is the **`q`-averaged oracle**
as a function of `(τ, direction)` — literally zero `q` information, deterministic
`ρ|τ = +0.0905724833`. Under τ × direction that fixture is constant within every nuisance
cell, so the zero-variance rule above fires and gives `ρ = 0.0`, `p = 1.0`. See §11 `D.11`.

**Order is load-bearing.** Rank over the pooled set **first**, residualize **second**.
Residualizing before ranking, or ranking within cells, is a different statistic and is
forbidden (`B_U2_S2_CONDITIONING_MISMATCH`).

Residualizing on the full `τ × direction` cell structure removes **all** τ-driven and
**all** direction-driven association, including nonlinear, so any surviving association is
`q`-driven at matched τ **and** matched direction. Hypothesis: `rho > 0`.

### 22.3 U2-S3 — three-`q` monotone dose response

```
per identity i:  m_i(q) = mean over tau in 1..15 of sigma_hat(q, i, tau),  for q in {low, mid, high}
per identity ordered agreement:
    A_i = +1 if m_i(q_low) < m_i(q_mid) < m_i(q_high)   (matches the oracle order)
          -1 if strictly reversed
           0 otherwise
experiment statistic: the proportion of identities with A_i = +1
interval:             whole-identity bootstrap, B = 10,000, ordinary two-sided 95%
                      percentile CI (UNADJUSTED; effect-size reporting only)
p-value:              whole-identity bootstrap inversion against 1/6, one-sided
                      p = (1 + #{pi*_b <= 1/6}) / 10,001   -> enters the Holm family
```

Under the null of no `q` sensitivity the expected proportion of strictly correct orderings is
`1/6`. Hypothesis: the proportion exceeds `1/6` with the CI excluding `1/6`.

`q_mid` participates **only** here and in §26/§27; it is not part of U2-S1.

### 22.4 The frozen U2 positive-declaration conjunction

`U2_POSITIVE` may be declared **only** when **all three** hold, each evaluated by the frozen
procedure of §22.0:

1. **U2-S1**: the **Holm-adjusted permutation p-value** is `≤ 0.05`, **and** the ordinary
   unadjusted two-sided 95% identity-bootstrap CI for `Dbar` lies entirely above `0`;
2. **U2-S2**: the **Holm-adjusted bootstrap-inversion p-value** is `≤ 0.05`, **and** the ordinary
   unadjusted CI for `rho` lies entirely above `0`;
3. **U2-S3**: the **Holm-adjusted bootstrap-inversion p-value** is `≤ 0.05`, **and** the ordinary
   unadjusted CI for the correct-ordering proportion lies entirely above `1/6`.

> The CI clause in each item is an **unadjusted directional sanity requirement**, not a
> multiplicity adjustment. Multiplicity is handled **only** by Holm on the three p-values.
> No interval anywhere in this authority is "Holm-adjusted".

**Multiplicity:** Holm across exactly these **three** U2 p-values (**two** at drop `LEVEL 1`,
where U2-S3 is not estimable). The family may not be inflated or reduced post hoc
(`B_U2_FAMILY_ALTERED`).

**Additionally required before the word "uncertainty" is used at all:** the clock and q-category
controls of §23 must pass. A conjunction that succeeds while §23 fails is reported as
**"q-category or elapsed-time decoding"**, not as uncertainty representation.

> **Note on provenance.** The referenced external Bayesian review was not available in this
> repository at amendment time. This conjunction is therefore **defined by this authority** from
> the three statistics specified for the module, and is frozen here. If the external review
> specifies a different conjunction, that is a §9.2 scientific change requiring an explicit,
> dated, pre-execution amendment — it may not be adopted silently, and never after results exist.

---

## 23. Clock and category confound controls

**This is fundamental.** III-B must demonstrate that the result is not merely *"the model knows
elapsed time"* or *"the model distinguishes `q` categories"*. All eight controls are frozen and
mandatory.

| # | Control | What it rules out | Frozen form |
|---|---|---|---|
| 1 | **τ-only baseline** | elapsed-time decoding | ridge on `[1, tau]` (and τ dummies) only, no activations, same folds; report its `sigma_hat` accuracy against the frozen probe |
| 2 | **q-only categorical baseline** | regime-label decoding | ridge on the `q` one-hot only, no τ, no activations; a probe that merely identifies the `q` cell can match this but cannot match τ-resolved structure |
| 3 | **Analytic τ+q oracle reference** | — | the exact oracle σ as a ceiling/reference curve; reports how much of the achievable structure the probe recovers |
| 4 | **Raw current-frame pixel baseline** | trivially visible cues | the frozen 48×28×3 = 4,032 pixel ridge (§8.9.1) regressed onto σ, same recipe |
| 5 | **Within-identity q permutation null** | any non-`q` explanation | §22.1, `B = 9,999` |
| 6 | **Matched-τ evaluation** | τ/`q` confounding | every primary contrast is computed at equal τ (§19.3) |
| 7 | **U3 q-dependent rate interaction** | additive `clock + q-category` | §26.2 — the main structural protection |
| 8 | **τ ≥ 16 boundary collapse** | context-independent artefact | §25 |

**Why control 7 is the decisive one.** An additive "clock + `q` category" model predicts a
**constant** offset between `q` levels, independent of τ. The oracle predicts a separation that
**grows** with τ, because `sigma_high(τ) − sigma_low(τ) = (√q_high − √q_low)·√(dt·S(τ))`. A
positive `slope(q_high) − slope(q_low)` cannot be produced by any additive clock-plus-label
model. That interaction, not U2-S1 alone, is what distinguishes uncertainty dynamics from
category detection.

**Frozen wording rule.** Until §23 passes, results are described as
**"`q`-regime-relevant information"**. Only when §23 passes may they be described as
**"uncertainty-relevant information tracking oracle posterior spread"**. Neither ever licenses
**"calibrated belief state"**, which requires §28's strongest rung.

---

## 24. Visible controls (`VIS6`)

**Definition** (VERIFY-4, §18.3): the last **6** consecutive model frames of a capture that are
counterfactually `EXTENT_FULLY_VISIBLE`, clamp-free, and have a complete 16-pair context.
Best-effort; **not** a qualification gate; coverage reported per cell.

Three frozen uses, all descriptive:

**A. New-`q` visible position positive control.** Decode position from the visible rows at each
`q` with the frozen III-A readout. Confirms the apparatus and readout behave at the new `q`
values exactly as at `q = 0.05`. A failure here indicates a technical defect, not a scientific
result.

**B. σ-visible floor.** The oracle posterior collapses under direct evidence, so decoded σ on
visible rows should be near its floor. Establishes the probe's lower dynamic range and provides
the reference against which occluded σ growth is read.

**C. Descriptive `q`-perception diagnostic.** Can the representation discriminate motion-noise
regime **while direct motion is visible**? This licenses a genuinely useful distinction:

> `q` information **perceived while visible but not retained** under occlusion
> versus
> `q` information **not encoded at all**.

That distinction materially changes the interpretation of a null U2 and is worth its modest cost.

**No VIS result may change III-B's primary readout, its `q` values, its estimands, or its
statistics.** Blocker `B_VIS_UNAVAILABLE` is informational only.

---

## 25. Context boundary prediction

Primary U2/U3 support is `τ ≤ 15`. At `τ ≥ 16` the last potentially informative pre-occlusion
frame has left the 16-pair context (§5.4, verified from explicit frame identities, never inferred
from a label).

**Frozen secondary boundary statistic:**

```
recompute the matched-q separation  D_i,tau = sigma_hat(q_high,i,tau) - sigma_hat(q_low,i,tau)
on  tau = 16..19,  identity-macro mean, whole-identity bootstrap 95% CI (B = 10,000)
```

**Expected under the finite-context interpretation:** the separation falls to approximately zero,
because with no in-context evidence anchoring the propagation the representation has no basis for
a `q`-dependent spread.

**This is NOT a technical pass gate.** A nonzero result is *scientific evidence to investigate
under the already-frozen analyses* — it would suggest `q`-relevant information survives beyond
the evidence horizon, which is interesting and reportable. **Do not modify the experiment because
the prediction fails.** Adding an analysis in response to this outcome is a §9.2 scientific
change.

---

## 26. U3 authority

U3 is **hierarchical**: U3 scientific claims may be made **only if U2 passes** (§22.4 conjunction
plus §23 controls). If U2 does not pass, U3 is computed and reported as descriptive only.

### 26.1 U3-S1 — per-identity uncertainty growth rate

```
per identity i, per q:   b_i(q) = OLS slope of sigma_hat(q,i,tau) on tau, over tau = 1..15
family statistic:        identity-macro mean of the within-identity average of b_i(q)
                         over the in-scope q levels  (POOLED ACROSS q)
also reported:           identity-macro mean of b_i(q) per q, each with its own
                         ordinary unadjusted two-sided 95% percentile CI (descriptive)
interval:                whole-identity bootstrap, B = 10,000, unadjusted 95% percentile
p-value:                 whole-identity bootstrap inversion, one-sided
                         p = (1 + #{b*_b <= 0}) / 10,001   -> enters the Holm family
hypothesis:              pooled mean slope > 0
```

### 26.2 U3-S2 — the `q`-dependent rate interaction (the decisive statistic)

```
per identity i:   Delta_i = b_i(q_high) - b_i(q_low)
experiment:       identity-macro mean
interval:         whole-identity bootstrap, B = 10,000, ordinary unadjusted two-sided
                  95% percentile CI (effect-size reporting only)
p-value:          whole-identity bootstrap inversion, one-sided
                  p = (1 + #{Delta*_b <= 0}) / 10,001   -> enters the Holm family
hypothesis:       Delta > 0
```

**This is the main protection against an additive `clock + q-category` explanation.** An additive
model predicts identical slopes across `q` (`Delta = 0`); the oracle predicts
`b(q_high)/b(q_low) = sqrt(q_high/q_low) = 4`.

### 26.3 U3-S3 — descriptive slope-ratio comparison

```
observed  b(q_high)/b(q_mid),  b(q_mid)/b(q_low),  b(q_high)/b(q_low)
oracle    sqrt(q ratios)    =  2.0, 2.0, 4.0  exactly
```

Descriptive only, with identity-bootstrap intervals. No pass/fail gate.

### 26.4 Multiplicity

Holm across exactly the **two** inferential U3 **p-values** (U3-S1 pooled across `q`, and
U3-S2), by the step-down procedure of §22.0 with `m = 2`. U3-S3 is descriptive, enters no
family, and is **never** Holm-corrected. The family may not be inflated post hoc.

**The inference unit is the identity. Rows are never independent units.**

---

## 27. Calibration battery

**Nothing in this section enters any Holm family.** The battery is criterion-based and
descriptive; every interval here is an ordinary unadjusted two-sided 95% whole-identity
bootstrap percentile interval (§22.0).

### 27.0 The `sigma_hat` positivity guard — calibration only

III-B fits an **unconstrained** ridge directly to **linear** σ. An unconstrained ridge may
return `sigma_hat < 0`, most plausibly at low `q` and low τ where the oracle σ is smallest — the
minimum oracle σ anywhere on the primary support is `3.8782034e-4` blocks
(`RIGHT_TO_LEFT`, `q_low`, `τ = 1`). A negative `sigma_hat` does not invalidate any statistic
built on raw predictions, but it makes Gaussian interval construction, Gaussian NLL,
`log(sigma_hat)` and any density score **undefined**. The rule is therefore frozen **now**,
before any result exists.

```
PRIMARY_U2_U3_USE_RAW_SIGMA_HAT = true

sigma_tilde = max(sigma_hat, EPS)        EPS = 1e-4 blocks
```

**`EPS = 1e-4` blocks is a purely numerical and physical positivity guard.** It is `3.878×`
below the smallest oracle σ anywhere on the primary support, `13.8×` below the smallest
`LEFT_TO_RIGHT` oracle σ (`1.3805e-3`), and `1000×` below the frozen minimum within-identity
target SD of `0.10` blocks. It cannot manufacture, mask or reverse any uncertainty signal.

**Applies to — probabilistic uses only:**

- **C. Coverage** — the interval `mu_hat ± z · sigma_tilde`;
- **D. NLL** — **both** variants, and both baselines wherever their spread argument could be
  non-positive; the Gaussian NLL is
  `0.5·log(2π) + log(sigma_tilde) + 0.5·((y − mu)/sigma_tilde)²`, identity-macro mean;
- any `log(sigma_hat)` or log-scale calibration axis;
- any Gaussian density or probability-integral-transform score;
- any scale metric requiring a strictly positive spread.

**Does NOT apply to — these use RAW `sigma_hat`:**

- U2-S1, U2-S2, U2-S3;
- U3-S1, U3-S2, U3-S3;
- **A. Scale agreement** — a linear regression; a negative `sigma_hat` is legitimate data there;
- **B. Monotonicity** — sign comparisons only; no positivity needed;
- the eight §23 confound controls;
- the §25 context-boundary secondary.

**Reporting is mandatory.** Every calibration analysis that uses `sigma_tilde` reports
`fraction_clipped = #{sigma_hat < EPS} / N` — overall, by `q`, and by τ — together with
`count_negative = #{sigma_hat < 0}` and `min_sigma_hat`, and the same statistic recomputed on
raw `sigma_hat` wherever that is defined. When `fraction_clipped > 0.05` the affected coverage
and NLL results are labelled `POSITIVITY_GUARD_MATERIAL` and the fraction is stated
prominently. **That is a disclosure, never a failure, and never a reason to change `EPS`, change
the rule, or re-fit.**

The locked predictions store **raw** `sigma_hat`; clipping before prediction lock is forbidden.
**The positivity rule may not be changed after prediction lock**
(`iii_b_u2_prediction_lock.json`); doing so is `B_CALIBRATION_POSITIVITY_RULE_ALTERED`.

### A. Scale agreement

```
regress  sigma_hat  on  sigma_oracle   over tau = 1..15, pooled across q
report:  slope, intercept, R^2, each with whole-identity bootstrap 95% CIs (B = 10,000)
```

Computed on **raw** `sigma_hat` (no positivity guard).

**Strong scale-calibration criterion** — both must hold:

```
slope CI contains 1     AND     intercept CI contains 0
```

**Wording bound.** A CI *containing* `1` is a **non-rejection** of scale mismatch at this power,
**not** proof of scale equivalence — no equivalence test is run anywhere in this authority.
Permitted: "consistent with scale calibration; scale mismatch is not detected at this power".
Forbidden: "proven scale-calibrated", "equivalent to the oracle scale", or any other
equivalence claim.

### B. Monotonicity

Ordered cell-pair agreement: over all pairs of `(q, tau)` cells, the fraction where
`sign(sigma_hat_a − sigma_hat_b)` matches `sign(sigma_oracle_a − sigma_oracle_b)`, with an
ordinary unadjusted identity-bootstrap interval. Chance is 0.5. Computed on **raw**
`sigma_hat` — sign comparisons need no positivity guard (§27.0).

### C. Coverage — **conditional**

Standard Gaussian coverage of decoded intervals may be computed and interpreted **only if the
predeclared mean gate passes**:

```
MEAN GATE: the decoded mu must beat the frozen constant-velocity baseline on held-out
           occluded rows, identity-macro RMSE, with a whole-identity bootstrap 95% CI
           excluding zero in the favourable direction.
```

Intervals are built as `mu_hat ± z·sigma_tilde` with the §27.0 positivity guard, and
`fraction_clipped` is reported. If the mean gate fails, coverage is **uninterpretable as
calibration**
— a miscentred interval fails coverage for reasons unrelated to σ — and must be reported as
`NOT_INTERPRETABLE`, not as a calibration failure.

### D. Negative log-likelihood — both variants, hybrid is primary

```
(i)  decoded mu + decoded sigma        -- computed ONLY when the mean gate permits
(ii) oracle-compatible mean + decoded sigma   -- HYBRID, the more important variant
```

The hybrid isolates the quality of the **σ** estimate from the quality of the **μ** estimate,
which is precisely what III-B is about. Its mean is the frozen constant-velocity/oracle-compatible
predictor, so any NLL difference is attributable to σ alone.

Both variants use `sigma_tilde` (§27.0) and report `fraction_clipped`.

Compare both against: a **τ-only spread baseline** (σ predicted from τ alone) and the **oracle
spread** (σ = `sigma_oracle`, the achievable ceiling). Report identity-macro NLL with ordinary
unadjusted whole-identity bootstrap intervals. **No NLL comparison enters a Holm family.**

### E. Permissible calibration language by result pattern

| Pattern | Permitted language | Forbidden |
|---|---|---|
| Scale slope CI ∌ 1 or intercept CI ∌ 0 | "σ̂ tracks oracle spread **ordinally** but is not scale-calibrated" | "calibrated" |
| Scale criterion passes, mean gate fails | "σ is **consistent with scale calibration** — scale mismatch is not detected at this power; interval coverage is not interpretable because the decoded mean is not established" | "calibrated belief state"; "proven scale-calibrated"; any equivalence claim |
| Scale criterion passes **and** mean gate passes **and** coverage near nominal **and** hybrid NLL beats τ-only | "a **calibrated Gaussian belief state** under this apparatus" (the strongest rung, §28) | any U4 or causal-use implication |
| Monotonicity above chance but scale fails | "**ordinal** uncertainty information" | "calibrated", "Bayesian" |

---

## 28. Belief-state claim ladder

Adjudicated prospectively at `B-LOCK`. Every reported III-B claim must map to exactly one rung.

| # | Result pattern | Permitted claim | Prohibited |
|---|---|---|---|
| 1 | **μ decodable, σ not** | "position is linearly accessible under occlusion; no evidence of uncertainty representation in this readout" | any belief-state or uncertainty claim |
| 2 | **μ not decodable, σ decodable** | "uncertainty-relevant information is present even where the point estimate is not linearly recoverable" — a **partial belief-state signature** | "the model tracks the object"; calibration |
| 3 | **both decodable, σ uncalibrated** | "**uncertainty-relevant information tracking oracle posterior spread**, ordinally but not on a calibrated scale" | "calibrated"; "Bayesian belief state" |
| 4 | **μ + σ decodable and scale-calibrated** (§27.A and the mean gate both pass) | "**a calibrated Gaussian belief state under this apparatus**" — the strongest permitted wording | U4; causal use; generalization beyond this apparatus |
| 5 | **both fail** | "no linearly accessible belief-state signature in the selected readout at this power" | "MineWorld has no uncertainty representation" |
| 6 | **τ explains σ̂** (§23 control 1 matches the probe; §26.2 `Delta` CI contains 0) | "**elapsed-time decoding**; the σ result is not uncertainty-specific" | any uncertainty claim |
| 7 | **`q` category detectable, dynamics absent** (§23 control 2 matches; `Delta` CI contains 0) | "**the regime label is detectable**, but correct uncertainty dynamics are not demonstrated" | "the model represents uncertainty" |

**Only rung 4 licenses "calibrated Gaussian belief state under this apparatus."** Rungs 2 and 3
license only "uncertainty-relevant information tracking oracle posterior spread" or "partial
belief-state signature".

**No rung ever licenses U4, causal use, steering, or causal object permanence.** A positive U2/U3
result says information is *linearly present*; it says nothing about whether the model *uses* it.

---

## 29. III-B workload, lifecycle, gates, and drop ladder

### 29.1 Frozen workload — recomputed from resolved semantics

`VIS_ROWS = 6`, `OCC_ROWS = 19`, **L19 only**, `PREVIOUS + CURRENT`.

```
new production captures                       50
new pilot captures                             4

occluded forwards            50 x 19  =      950
visible forwards, new q      50 x  6  =      300
visible re-inference on the existing
  III-A L4 q=0.05 captures   25 x  6  =      150     (NO recapture)
pilot forwards                4 x 25  =      100
                                        ----------
PRODUCTION forwards                        1,400
ALL new forwards incl. pilot               1,500

production logical row tensors  1,400 x 2 = 2,800
all logical row tensors         1,500 x 2 = 3,000

bytes per .npy [19,336,2048]           26,148,992
bytes per .npy [ 6,336,2048]            8,257,664

production .npy arrays                       250
production activation bytes        3,853,548,800   (3.5889 GiB)
pilot .npy arrays                             16
pilot activation bytes               275,253,248   (0.2563 GiB)
III-B total incl. pilot            4,128,802,048   (3.8452 GiB)
```

### 29.2 Combined program workload

```
production captures        125 + 50            =       175
production forwards      2,375 + 1,400         =     3,775
production .npy arrays     750 + 250           =     1,000
production activation bytes                      23,465,292,800   (21.8538 GiB)

ALL captures incl. pilots  125+50+10+4         =       189
ALL forwards incl. pilots                              4,065
ALL .npy arrays incl. pilots                           1,076
ALL activation bytes incl. pilots                25,309,485,568   (23.5713 GiB)
```

**Storage preflight is raised** for the combined program. Units, physical pools and the
double-counting rule are frozen in **§13.2**, which is controlling:

```
A3 GATE, POOL_WORKING, no local mirror   >= 40 GiB   (was 30 for III-A alone)
A3 GATE, POOL_WORKING, local mirror      >= 64 GiB   (was 45 for III-A alone)
derived combined peak, mirrored          =  59.304 GiB

III-B launch gate (incremental headroom) >= 15 GiB free on POOL_WORKING
                                         >= 5  GiB on POOL_DURABLE only if it is a
                                            DISTINCT local filesystem
III-B incremental peak, mirrored         =  10.508 GiB
gate coherence: 64 - 48.796 = 15.204     >= 15 GiB           OK
```

**The superseded launch-gate formulation "`≥ 60 GB` durable free AND `≥ 40 GB` scratch free"
is withdrawn.** It mixed decimal GB with binary GiB, applied whole-**program** totals to an
**incremental** decision, and treated "durable" and "scratch" as two independent free-space
pools when both may resolve to one filesystem — counting the same free bytes twice. The
whole-program preflight belongs to `A3` and has already been enforced before the launch gate can
fire; the gate now measures **remaining headroom** for III-B's incremental footprint.

### 29.3 Time envelopes

| Stage | Best | Nominal | Conservative |
|---|---|---|---|
| III-B pilot (4 captures + 100 forwards) | 0.3 h | 0.6 h | 1.2 h |
| III-B capture (50 captures) | 2.4 h | 3.8 h | 5.2 h |
| III-B extraction (1,500 forwards) | 0.5 h | 1.0 h | 2.0 h |
| III-B oracle + U2 + U3 + calibration | 1.0 h | 2.0 h | 3.5 h |
| III-B **additive implementation** (`IB01`, `IB04`–`IB20`) | 2.30 h | 4.60 h | 8.00 h |
| **III-B total, execution only** | **4.2 h** | **7.4 h** | **11.9 h** |
| **III-B total, incl. additive implementation** | **6.5 h** | **12.0 h** | **19.9 h** |
| Combined capture (175) | 8.4 h | 13.0 h | 18.2 h |
| Combined extraction (4,065 forwards) | 2.0 h | 3.5 h | 5.0 h |
| Combined analysis | 4.0 h | 6.0 h | 8.0 h |

The execution-only total matches the independent audit's `+4.2 / +7.4 / +11.9 h` exactly. The
additive-implementation row is new (§13.3.1); the audit did not count it separately. `IB02` and
`IB03` are **not** in this table — they are `A1` tasks on the III-A critical path and are
counted in §13.3.1.

Per-capture rate is derived from III-A's frozen 6–13 h envelope over 125 captures
(2.9–6.2 min/capture). Pure forward time for the combined program is
`4,065 × 0.69 s ≈ 47 min`; the remainder is preprocessing, hooks, writes, validation, and
durability.

### 29.4 III-B pilot (`B-PILOT`)

```
2 excluded pilot identities (e3_p90, e3_p91) x {q_low, q_high} x L4  =  4 captures
100 forwards (4 x (19 occluded + 6 visible))
```

Verifies: `q` parameterization; innovation pairing; path replay; target support; ≥19 stable
occluded rows; VIS6 support; FIR coherence (§18.5); capture provenance; extraction; oracle target
generation.

**`q_high` fallback — technical trigger only.**

```
primary q_high = 0.2
if the PREDECLARED TECHNICAL window/FIR gate fails at q = 0.2:
    exactly ONE fallback re-pilot at q = 0.15
if the fallback also fails:
    III_B = SKIPPED   (CLEAN_SKIP; III-A continues untouched)
```

The **only** admissible trigger is failure of the technical trajectory/window/FIR qualification
gate — i.e. an identity cannot yield 19 consecutive counterfactually occluded rows with complete
FIR history, a clamp-free protected prefix, and coherent FIR labels at `q = 0.2`.

**The fallback may NEVER be selected because:** `q = 0.2` produces undesirable model results;
uncertainty separation looks too easy or too hard; decoder results are disappointing; or the
U2/U3 effect size is weak. Any such selection is `B_Q_FALLBACK_OUTCOME_DRIVEN` — a scientific
violation, not a repair. **No further `q` search is permitted** beyond this single fallback.

### 29.5 III-B launch gate — hard deadline protection

**Primary evaluation: Wednesday 2026-09-02, 12:00 local.** Launch III-B **iff every** condition
holds:

1. III-A capture is technically closed, or sufficiently complete under the frozen `A8` gate;
2. III-A remains on schedule for its result lock;
3. `>= 15 GiB` free on `POOL_WORKING` — III-B's incremental mirrored footprint is `10.508 GiB`,
   a `1.43×` margin, and `15 ≤ 15.204 GiB`, the structural headroom left by the `A3` gate, so a
   host that passed `A3` at exactly 64 GiB can still pass here (§13.2, §29.2, test `B.13`);
4. `>= 5 GiB` free on `POOL_DURABLE` — **only if** `POOL_DURABLE` is provably a **distinct**
   local filesystem; otherwise this requirement is satisfied by construction and recorded as
   `N/A`, because counting the same filesystem twice is forbidden;
5. III-B static and CPU tests **PASS**;
6. III-B pilot **PASS**;
7. no unresolved shared-rig blocker;
8. launching III-B does not threaten the III-A result lock.

**Inputs are time, technical state, and resources only. No scientific outcome may be consulted.**

```
NO-GO at 12:00  ->  re-evaluate ONCE at 17:00 the same day
NO-GO at 17:00  ->  III_B = DROPPED / CLEAN_SKIP
```

**No third reconsideration. No Friday experiment launch.** Every evaluation, its inputs, and its
verdict are recorded in `iii_b_launch_gate_receipt.json`.

**Re-evaluated against the revised schedule (§30) — the 12:00 timing is retained unchanged.**
Under BEST and NOMINAL, III-A capture has closed before Wednesday 12:00 (11:00 nominal), so
requirement 1 is satisfiable at the primary evaluation. Under CONSERVATIVE the gate correctly
returns NO-GO, because III-A is still capturing and launching III-B would threaten the III-A
result lock. Moving the gate **earlier** would make it un-passable under NOMINAL; moving it
**later** would push III-B capture into the Thursday analysis window. Every input remains time,
technical state and resources — **no scientific outcome is consulted at any evaluation**.

### 29.6 III-B drop ladder — frozen, outcome-independent

Selected using **time, technical completion, and available resources only**. At no point may a
scientific outcome determine the level.

| Level | Content | New caps | Forwards | Arrays | Bytes |
|---|---|---:|---:|---:|---:|
| **NORMAL** | `q = {0.0125, 0.05, 0.2}`, N=25, VIS6, U2 + small U3 | 50 | 1,400 | 250 | 3.589 GiB |
| **LEVEL 1** | drop `q_low`; retain `q_mid` + `q_high`, N=25 — the predeclared **two-`q` U2 fallback** | 25 | 775 | 150 | 1.987 GiB |
| **LEVEL 2** | Level 1 **+** drop the redundant `q_mid` VIS re-inference | 25 | 625 | 100 | 1.602 GiB |
| **LEVEL 3** | analyse the first **≥15 COMPLETE identity `q`-triples** in frozen priority order | 30 | 840 | 150 | 2.153 GiB |
| **LEVEL 4** | **III-B `CLEAN_SKIP`** | 0 | 0 | 0 | 0 |

At Level 1, U2-S3 (three-`q` dose response) is not estimable and is dropped from the U2
conjunction; the Holm family reduces to the **two** remaining U2 statistics. This reduction is
frozen here, prospectively, and is the *only* permitted family change.

Level 3 uses `identity_priority_order` (§2.6) — never observed performance.

### 29.7 The absolute Thursday stop rule

```
ABSOLUTE_EXPERIMENT_DEADLINE = Thursday 2026-09-03, 20:00 local

At that instant NO new scientific Experiment III execution may begin.

By then:
  III-A must be  RESULT_LOCKED  or  TERMINALLY_ADJUDICATED
  III-B must be  RESULT_LOCKED  or  CLEANLY_SKIPPED  or  TERMINALLY_ADJUDICATED
```

**No ordinary III-A or III-B work rolls into Friday.** Friday 2026-09-04 and Saturday
2026-09-05 are **not** experiment-development days: they are reserved for manuscript writing,
figures and tables generated from already-locked results, interpretation, and submission
preparation.

```
FRIDAY_EXPERIMENT_EXECUTION_PLANNED = false
```

If III-B is incomplete as Thursday approaches, apply the §29.6 drop ladder. **Never delay III-A
closure to save III-B.**

### 29.8 III-B lifecycle states

Nine optional states. Full machine form in `EXPERIMENT_III_LIFECYCLE.json`. **No `B-*` state is
a prerequisite of any `A*` state.**

| State | Purpose | Unit of work | Exit |
|---|---|---|---|
| `B-GEN` | materialize III-B `q` manifests from the frozen III-A cohort | one `(identity, q)` cell | manifests hashed; all cells qualify |
| `B-PILOT` | 4-capture end-to-end pilot incl. FIR coherence | one pilot capture | `iii_b_pilot_receipt.json` PASS |
| `B-GATE` | outcome-independent launch decision | the decision | GO, or `CLEAN_SKIP` |
| `B-CAP` | 50 production captures | one `(identity, q)` capture | all units `COMPLETE_VALIDATED_DURABLE` |
| `B-EXT` | extraction, L19 × {PREVIOUS, CURRENT}, occluded + VIS6 | one `(capture, layer, slice)` array | all arrays `DURABLE` |
| `B-ORC` | oracle σ ledger for every `(identity, q, tau)` | one cell | `iii_b_oracle_validation_receipt.json` PASS |
| `B-U2` | U2 probe, prediction lock, three statistics, controls | one statistic | `iii_b_u2_results.json` |
| `B-U3` | U3 dynamics and calibration battery | one statistic | `iii_b_u3_results.json`, `iii_b_calibration_report.json` |
| `B-LOCK` | belief-state ladder adjudication and III-B closure | the module | `iii_b_closure_receipt.json` |

### 29.9 III-B blockers

Full entries in `BLOCKER_TAXONOMY.json`. **Three outcomes are strictly distinguished:**

```
CLEAN_SKIP      III-B was never launched, or was dropped by the frozen time/resource ladder.
                An honourable, pre-registered outcome. NOT a failure.

TECHNICAL_FAIL  Something broke. Repairable under the frozen repair policy. NOT a result.

SCIENTIFIC_NULL A valid III-B measurement that did not support U2/U3.
                A publishable scientific result. NOT a blocker, and never reported as one.
```

Codes: `B_ORACLE_MISMATCH`, `B_Q_PAIRING_MISMATCH`, `B_Q_HIGH_PILOT_FAIL`,
`B_Q_FALLBACK_OUTCOME_DRIVEN`, `B_GATE_NOT_MET`, `B_CAPTURE_ATTRITION`, `B_VIS_UNAVAILABLE`,
`B_EXTRACTION_FAIL`, `B_U2_ANALYSIS_FAIL`, `B_U3_ANALYSIS_FAIL`, `B_U2_FAMILY_ALTERED`,
`B_TAU_ALIGNMENT_ERROR`, `B_CROSS_Q_FOLD_LEAKAGE`, `B_DEADLINE_DROP`,
`B_III_A_DEPENDENCY_DETECTED`.

`B_III_A_DEPENDENCY_DETECTED` is **critical**: it fires if any III-A stage, artifact, or statistic
is found to depend on a III-B product, violating §17.2.

### 29.10 III-B recovery scope

A III-B failure's invalidation scope is **bounded to III-B**, unless it proves a **shared III-A
implementation defect** — for example a defect in the q-generalized generator, the extent engine,
the FIR machinery, the extraction path, or the ridge machinery. In that case the existing III-A
repair policy (§9) applies in full, including III-A's invalidation scopes.

---

### 29.11 III-B implementation deferral — the first optional work sacrificed

III-A is mandatory. III-B is optional. **Under any implementation lag, III-B-only
implementation work is the first thing dropped**, before any III-A scope is touched.

```
CP0  Mon 2026-08-31 20:00 local, milestone: task I10 COMPLETE
     if unmet -> DEFER ALL III-B-ONLY IMPLEMENTATION
                 IB01, IB04-IB20            recovers 2.30 / 4.60 / 8.00 h
```

**`IB02` and `IB03` are never deferred.** They are `SHARED_A_B` and prospectively mandatory:
III-A qualification **gate 12** is defined in terms of the `IB02` primitive and guarded by the
`IB03` regression fixture (§2.4, §19.4). Deferring them would stop III-A, not save it.

If time never recovers, `III_B = CLEAN_SKIP` and III-A proceeds untouched. **No III-B
implementation rescue may delay III-A.** The decision reads implementation completion, the
clock, technical state and resources only — never a scientific outcome.

---

## 30. Combined program schedule

### 30.1 Nominal schedule, relative to `PHASE2_START`

*Rewritten by repair pass 2.* The schedule is now expressed as offsets from `PHASE2_START`
(§13.3.5) and is derived from the §13.3.2 elapsed model plus the §13.3.4 tail — not asserted.
Instants below use the reference start **Sun 2026-08-30 20:00** (96 h budget).

| Offset | Stage | Nominal instant | Attendance |
|---|---|---|---|
| `+0.0 h` | `A1` implementation begins immediately on authorization | Sun 20:00 | agent, repo-exclusive |
| `+17.7 h` | `I10` complete — extraction/serialization spine | Mon 13:42 | agent |
| `+24.0 h` | **CP0** III-B deferral checkpoint | Mon 20:00 | decision |
| `+32.5 h` | `A1` complete (`I18`) | Tue 04:30 | agent |
| `+38.4 h` | **`A2` green** | Tue 10:24 | agent |
| `+39.4 h` | `A3` preflight | Tue 11:24 | attended |
| `+41.0 h` | **CP1** drop-below-NORMAL checkpoint *(fires on the clock regardless of progress)* | Tue 13:00 | decision |
| `+47.4 h` | **P0** calibration | Tue 19:24 | rig-attended |
| `+49.4 h` | **P1** pilot | Tue 21:24 | rig-attended |
| `+50.4 h` | **P2** freeze | Tue 22:24 | attended |
| `+59.9 h` | production capture (125) | Wed 07:54 | **unattended** |
| `+62.7 h` | extraction | Wed 10:39 | GPU |
| `+65.7 h` | analysis | Wed 13:39 | attended |
| `+67.7 h` | packaging | Wed 15:39 | attended |
| `+69.7 h` | **rig/attended window allowance** *(named explicitly; never folded into another row)* | Wed 17:39 | — |
| `+69.7 h` | **III-A result lock** | **Wed 17:39** | attended |
| — | III-B pilot, capture, extraction, analysis | Wed 18:00 – Thu 06:00 | rig then CPU |
| — | **III-B result lock** | **Thu 06:00** | attended |
| **Thu 2026-09-03 20:00** | **ABSOLUTE STOP** | | |
| Fri 2026-09-04 – Sat 2026-09-05 | manuscript, figures from locked results, submission | | |

```
FRIDAY_EXPERIMENT_EXECUTION_REQUIRED = false
```

III-B capture runs on the rig freed at Wed 07:54 and overlaps III-A CPU analysis — genuinely
different resources. The serial figure above is the pessimistic bound.

### 30.2 Best / nominal / conservative

| Variant | impl elapsed | tail | total | budget | III-A lock | III-B |
|---|---:|---:|---:|---:|---|---|
| **BEST** | 20.70 | 17.50 | 38.20 | 96 | **Tue 01 10:12** | NORMAL, Thu ~00:00 |
| **NOMINAL** | 38.40 | 31.25 | 69.65 | 96 | **Wed 02 17:39** | NORMAL, Thu ~05:00 |
| **CONSERVATIVE** | 65.00 | 55.00 | 120.00 | 96 | **does not close on NORMAL** | `CLEAN_SKIP` |
| CONSERVATIVE → 10.2 | 63.30 | 27.33 | 90.63 | 96 | **Thu 03 14:38** (+5.4 h) | `CLEAN_SKIP` |
| CONSERVATIVE → 10.3 | 59.30 | 24.97 | 84.27 | 96 | **Thu 03 08:16** (+11.7 h) | `CLEAN_SKIP` |

**Stated plainly: the full NORMAL plan does not close under conservative implementation.** It is
`0.25 h` short even with nominal execution, and `24 h` short with conservative execution. This is
recorded as **NOT FEASIBLE** rather than forced to pass. The §10.5 checkpoints exist exactly for
this case, and a prospectively valid reduced III-A plan (10.2 or 10.3) **does** close under
conservative implementation with `+5.4 h` and `+11.7 h` of margin.

Under every variant III-A locks before Thursday 20:00 once the correct plan is selected, because
III-B holds no III-A dependency on any III-B **runtime** stage (§17.2). **III-B `CLEAN_SKIP` is
pre-registered, honourable, and is the expected outcome whenever implementation trends
conservative.** It is never an error state and never a reason to delay III-A.

### 30.3 Shared-code tasks that must land EARLY

Two implementation items are on the **shared** critical path and must land **before `I02`** —
not merely before III-A P1, as the superseded text said:

1. **`IB02` — the `q`-generalized path and qualification primitive.** III-A's `C01` already
   parameterizes `q`; `IB02` adds `generate_path(seed, q)`, `qualifies(candidate, q)` and
   `qualifies_at_all_q(candidate, Q)`. **III-A qualification gate 12 is defined in terms of it**,
   so `I02` cannot materialize the cohort without it. The III-B q-cell manifest **expansion** it
   previously carried moved to `IB09`.
2. **`IB03` — the `q = 0.05` bit-identity regression fixture.** It proves the generalized
   generator reproduces the frozen `q = 0.05` behavior bit-identically, including the real
   A-prime path hash `b5803943…`, with both negative controls changing the hash. Without it, a
   `q`-generalization defect could silently alter III-A's cohort **at the exact moment gate 12 is
   evaluated**.

```
I01 -> I05 -> I06 -> IB02 -> IB03 -> I02
```

The superseded graph had `IB02` **depending on** `I02`, which was backwards. If either task is
absent or failing when `I02` runs, `I02` **fails closed** with
`COHORT_ALL_Q_PRIMITIVE_MISSING` and materializes nothing.

Both are **implementation** tasks inside `A1`, not III-B **runtime stages**. No `B-*` stage and
no III-B artifact is a precondition of anything in III-A, and the materialized cohort is
byte-identical whether III-B later runs or clean-skips (§11 `D.31`).

Everything else in III-B (`IB01`, `IB04`–`IB20`) is off III-A's critical path and may proceed in
the repository gaps or be abandoned at any drop level without touching III-A.

---

## 31. Final standard — the combined program

Experiment III is one coherent two-part program:

```
III-A   graded observability, position accessibility,
        temporal representation, context age                   INDISPENSABLE

III-B   objectively manipulated posterior uncertainty,
        matched-tau U2, q-dependent uncertainty dynamics U3,
        oracle calibration, bounded belief-state interpretation OPTIONAL, ADDITIVE
```

subject to one overriding operational requirement:

```
THE ENTIRE EXPERIMENTAL PROGRAM MUST BE RESULT-LOCKED BY
THURSDAY, SEPTEMBER 3, 2026 — 20:00 LOCAL.
```

The optimization target is

```
SCIENTIFIC VALUE  x  COMPLETION PROBABILITY BY THURSDAY
                  x  PROTECTION OF III-A
                  x  MANUSCRIPT VALUE
```

**III-B is valuable. III-A is indispensable. Never sacrifice the completion of III-A to rescue
III-B.** If time becomes insufficient, the frozen drop ladder (§29.6) terminates the Bayesian
extension cleanly, leaving the core experiment fully valid and independently closable.

Both parts obey the same discipline: prospective freezing, machine-checkable gates, named
blockers, bounded repairs, localized invalidation, resumable execution, hash-bound provenance,
and outcome-independent operational decisions. No scientific design decision may be improvised
after results exist — in either part.
