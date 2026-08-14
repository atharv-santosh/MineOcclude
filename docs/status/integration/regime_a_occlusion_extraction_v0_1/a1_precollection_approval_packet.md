# Regime A A1 pre-collection approval packet

Status: `PENDING_MENTOR_OPERATOR_APPROVAL`

Authority: decision sheet only; **not** A1 authority and **not** a collection authorization.
A0 inputs: the six JSON authorities beside this packet. No scientific Regime-A trajectory or decoding outcome was produced.

## 1. Primary coordinate target

Measured facts: layout-01's world wall-parallel scalar is world `x` in blocks (origin 0, positive `+x`). Its accepted homography maps finite in-bounds lane points to canonical 640x360 pixels; held-out wall-parallel absolute error is 0.085008 blocks. Canonical screen `(x,y)` maps to continuous visual-token `(row,col)` as `(y*14/360, x*24/640)` and discrete cells by floor. Increasing world `x` decreases screen `x`/token column.

Recommended approval: **world wall-parallel coordinate as primary; continuous screen-token coordinate as secondary.** Preserve world, screen, continuous token, discrete token, and both raw visibility signals per aligned model frame.

Decision: `PENDING` — approve / revise.

## 2. Context and candidate-bin interpretation

- Nominal capacity: 16 complete frame/action pairs, 5,552 tokens, 0.80 s sample occupancy.
- Effective pre-current causal history: `E=15` captured steps and `C=0.75 s` at 20 Hz.
- Exact proposed path: independent, teacher-forced, trailing contiguous windows ending at each target frame; no recurrent state or KV persistence across calls. The first 15 target frames are unusable for primary full-context analysis.
- Candidate clean post-entry-guard bins: SHORT 1–4 (0.05–0.20 s), INTERMEDIATE 5–8 (0.25–0.40 s), LONG 9–12 (0.45–0.60 s), NEAR_CONTEXT 13–15 (0.65–0.75 s), BEYOND_CONTEXT 16–19 (0.80–0.95 s).
- Guards: `g_entry=20` frames (1.00 s), `g_exit=8` frames (0.40 s). Every bin has at least three clean model frames after guard exclusion.

Recommended approval: use this finite-history interpretation and the five candidate bins. `tau=1` begins only at the first stable `OCCLUDED_AGREEMENT` frame after entry-guard exclusion.

Decision: `PENDING` — approve / revise.

## 3. First-slice geometry

Recommended fixed layout-01 camera: feet `(0.5,4.0,-5.5)`, eye `(0.5,5.6200000048,-5.5)`, yaw/pitch/roll `0/0/0`, FOV 70°. Use the `x=-8..8, y=4, z=6` lane and one long wall with block indices `x=-3..3, y=4..6, z=2`.

The clear lead-in is approximately 3.2 blocks. At candidate speed 1.5 blocks/s, `C + max(g_entry,0.10C)` needs 2.625 blocks, leaving about 0.575 block. The stable hidden path is at least 9.62 blocks; the BEYOND_CONTEXT upper edge plus exit guard needs 2.025 blocks. Existing full-visible observations show a 26–27 px by 24–25 px sheep bbox and a 2x2 token footprint without candidate-lane clipping.

Recommended approval: one long wall; design all 25 future trajectories to span every bin. Before collection, require a runtime target-retention smoke check because the v0.4 geometry authority records a historical post-warmup sheep-removal caveat.

Decision: `PENDING` — approve / revise.

## 4. Motion direction and confound authority

`BIDIRECTIONAL_GEOMETRY_SUPPORTED=UNCLEAR`: static containment and projection are compatible, but matched reverse-direction entry/exit visibility calibration is absent.

Recommended approval: first slice uses left-to-right (`+x`) only. Bind the inherited pre-outcome screens:

- absolute pooled normalized-time correlation `<=0.10`;
- high-profile-similarity fraction `<=20%` overall;
- `<=10%` within the approved direction;
- `<=10%` across approved path-shape strata.

Proposed Regime-A extensions for approval:

- support overlap: each outer fold and each duration bin must contain target-coordinate support overlapping its corresponding outer-training support; report interval and occupancy overlap before outcomes;
- duplicates: zero exact duplicate complete motion/target profiles across trajectory groups;
- fold balance: trajectory counts differ by at most one across outer folds, and direction/path-shape/bin counts are balanced as closely as integer feasibility permits and reported before outcomes.

No new time-only R2 hard threshold is proposed.

Decision: `PENDING` — approve single direction and the extensions / require a matched reverse-direction calibration.

## 5. Mid speed and mid noise

Existing speed authority supplies moving values 1.0 and 2.0 blocks/s; the visible-study profile authority adds their untuned exact midpoint 1.5. Existing motion-noise levels are `q={0.02,0.05,0.2}`, with unique ordinal middle `q=0.05`.

Recommended candidates: **speed 1.5 blocks/s; motion-noise q=0.05.** These are not frozen here.

Decision: `PENDING` — approve / revise.

## 6. First-slice split

Recommended: nested five-fold trajectory-grouped out-of-fold evaluation, with all preprocessing, token ranking (secondary BEST-K), and hyperparameter selection confined to the outer-training data. Alternative: fixed 15/5/5 trajectory split.

Decision: `PENDING` — choose nested 5-fold / 15-5-5.

## 7. Target-specific null

Recommended: `B=49`, whole-trajectory, outer-training-only, motion-stratified where applicable, no self donor, true held-out targets untouched, and the same exact primary equal-layout macro per-trajectory R2 statistic. Do not execute nulls before approval.

Decision: `PENDING` — approve / revise.

## 8. Continuation gate

Recommended gate, not automatically approved:

- operational quality `PASS`;
- every evaluated trajectory has `TSS_t > 0`;
- layer-4 FULL exact macro-R2 `>0` on SHORT through NEAR_CONTEXT;
- `B=49` empirical `p<=0.05`;
- trajectory bootstrap is reported but is not a hard gate.

Decision: `PENDING` — approve / revise.

## Required signatures before A1 can freeze

- Mentor: primary/secondary coordinates; context/bin semantics; geometry; direction/confound rules; factor values; split; null; continuation gate.
- Operator: confirms exact implementability, target-retention smoke check, resource bounds, and restart contract.

Until those choices are signed, A1 remains pending, A2 remains unauthorized, and scientific collection remains prohibited.
