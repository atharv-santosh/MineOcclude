# 02 — Authority → Code → Metric → Decision Traceability

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**

---
## PATH / STATE GATE — implementation **narrower** than authority (under-implemented, but sound where it runs)

| Layer | Content |
|---|---|
| Requirement | Paired NORMAL/NO_WALL runs must be exactly identical in trajectory, seed, noise, direction, speed, start state, target tick IDs/order, camera/FOV, cadence, frame/action/server-tick identity, **world x/y/z**; `epsilon_path = 0.0` |
| Authority | `p3_preoutcome_authority.json → path_and_state_gate.exact_fields` (13 fields), `rows_checked_per_scene_per_candidate: 4500` |
| Code | `p3_run_sequential.py:566-586` (`non_neural_gates`) + `derive_artifacts` identity assertions at `:340-355` |
| Measured | sha256 of the `<f8` byte image of the **`sheep_x` column only**, vs `spec.expected_path_sha256`; plus `np.array_equal(NORMAL.sheep_x, NO_WALL.sheep_x)` |
| Aggregation | Per run; any mismatch appended to `path_failures` / `paired_path_failures` |
| Threshold | Exact equality (ε = 0) |
| Decision | **PASS** for all three candidates; 0 failures, 0 paired failures |

**Discrepancies found (do not change the outcome):**
- **D-P1** The gate hashes only `sheep_x`. `sheep_y` and `sheep_z` are never compared, although the authority
  lists "world x/y/z". *Independently verified as harmless here*: the lane is 1-D (`y=4.0, z=6.0` fixed) and my
  reconstruction confirms 4500 rows/scene/candidate with dense `server_tick` 0..179 and matching `scene`.
- **D-P2** Camera/FOV, capture cadence and target-tick order are **not** re-verified per run by the gate.
  Frame/action/server-tick identity *is* enforced, but inside `derive_artifacts` (capture time, raises
  `CAPTURE_IDENTITY_MISMATCH`) rather than inside the gate — so a resumed/reused unit is never re-checked.
- **D-P3** `rows_checked_per_scene_per_candidate: 4500` is asserted in the authority but never computed or
  recorded by the gate; the receipt does not report a row count. (Reconstruction confirms 25×180 = 4500.)

`PATH_IMPLEMENTATION_MATCHES_AUTHORITY = false` (narrower than specified) — but every check that *did* run
was exact, and the reconstruction confirms the PASS verdict is correct on the full x/y/z + identity data.

---
## HEADROOM GATE — implementation **matches** authority; verdict correct

| Layer | Content |
|---|---|
| Requirement | Prospective, computed from frozen physical target paths **before** capture. Each trajectory target-x SD ≥ 2×P2 BEST-K RMSE = 0.3320548468891168; candidate median ≥ 3× = 0.4980822703336752 |
| Authority | `prospective_headroom_gate` |
| Code | Values produced at freeze (`p3a_freeze.py:167`, `np.std(targets)`); gate is a pure comparison in `p3_run_sequential.py:587-590` |
| Measured | Population SD (ddof=0) of the 19 frozen `expected_target_world_x_blocks` per spec |
| Aggregation | min over 25 specs, median over 25 specs |
| Threshold | ≥0.33205 (each), ≥0.49808 (median) |
| Decision | **PASS** ×3 — C01 min 0.4187/med 0.5683; C02 0.5930/0.7071; C03 0.6811/0.8235 |

**Independently verified:** recomputing `np.std(ddof=0)` from the frozen manifest paths reproduces every
`expected_target_sd_blocks` to **0.000e+00**, and the manifest min/median/max match exactly. Recomputing the
SDs from the **actually captured** `sheep_x` at the target ticks reproduces the frozen values with
**max |Δ| = 0.00e+00** across all 75 specs — the executed physics matched the frozen design bit-for-bit.
(Note: population SD, not sample SD, is used; the authority does not specify which. Sample SD would be
larger, so the gate is the conservative choice. Recorded as a documentation gap, not a defect.)

`HEADROOM_IMPLEMENTATION_MATCHES_AUTHORITY = true`.

---
## VISIBILITY GATE — **semantic mismatch; this is where P3 died**

| Layer | Content |
|---|---|
| Requirement | (a) NO_WALL: every target row geometrically visible **and** rendered-magenta detected. (b) NORMAL: every target row geometrically occluded **and** magenta **not** detected. (c) calibration: "**At least 0.95 precision and 0.95 recall for the frozen magenta detector against geometric visibility**, with no identity/timestamp ambiguity". (d) `ambiguous_target_rows_allowed: 0`, `qualified_target_rows_required: 475` |
| Authority | `visibility_authority` |
| Code | `calibration_gate` (`p3_run_sequential.py:529-548`) + target-row loop (`:571-583`) |
| Raw quantity A | `geometric_status` ← `server_state.geometric_visible` ← **Java** `EpisodeManager.java:453-459`: `GeometryUtil.segmentHitsWall(...)` — a **single ray** from the player eye to the **single point** `(sheepX, sheepY+0.5, sheepZ)` against the block-inflated wall AABB |
| Raw quantity B | `magenta_status` ← `detect_magenta()` on the 640×360 PNG — **"does a magenta blob of area ∈ [19,5000] px exist anywhere in the frame"**, an existential predicate over the **whole rendered silhouette** |
| Aggregation | Calibration: **pooled over every one of the 720 frames** of 4 full NORMAL lane traversals (no restriction to any regime). Target rows: exact counts, 475 per scene |
| Threshold | precision ≥ 0.95 **and** recall ≥ 0.95 **and** ambiguous == 0 |
| Decision | **FAIL** ×3, always via `precision`, never via recall |

### The mismatch
Quantity A is a **point-visibility** predicate. Quantity B is an **area-visibility** predicate. For a body of
finite width these two predicates *cannot* agree over the ~1-block-wide band in which the target's centre
point is behind the occluder while part of its silhouette is not. The authority text ("the frozen magenta
detector **against geometric visibility**") treats A as ground truth for B, but nothing in the pipeline ever
established that A and B are the same quantity — and the project's own bound authority says they are not
(see below). **`VISIBILITY_IMPLEMENTATION_MATCHES_AUTHORITY = false`.**

### Further discrepancies
- **D-V1 (material)** The calibration gate is evaluated on **all 180 frames** of each calibration run, including
  the occlusion-transition band. The scientific design deliberately places target rows *past* that band
  (`expected_stable_hidden_onset_server_tick`). The gate therefore judges the detector precisely in the regime
  the experiment excludes from use.
- **D-V2 (material)** All four calibration specs are `scene = "NORMAL"`. There is **no NO_WALL calibration run**,
  so the calibration confusion matrix is drawn entirely from the wall scene; its class balance is
  `visible_frames/180`, a direct function of the swept speed (see `08_exploratory_counterfactuals.md`).
- **D-V3 (material)** `precision` is **base-rate dependent**. The authority intends to bound detector error;
  precision does not do that when the negative class size is a function of the candidate variable.
- **D-V4** The authority's "no identity/timestamp ambiguity" is **not implemented**. `calibration_gate` defines
  `ambiguous` as `magenta_status ∉ {detected, not_detected}` (a detector-status sentinel, always 0), and the
  target-row loop defines `ambiguous` as `geo != mag` (redundant with `normal_ok`/`nowall_ok`). Neither is an
  identity/timestamp check. `target_visibility_ambiguous` in the receipt is therefore **not** the quantity the
  authority named.
- **D-V5** `zero_evidence_no_wall_target_rows_allowed: 0` has no distinct implementation; it is folded into the
  `nowall_ok` count.
- **D-V6** The gate compares a **20 Hz server-tick** label against a frame that is *not* synchronous with it —
  see `03_visibility_forensics.md` §4 (~3.3-tick render lag). Neither the authority nor the code states which
  clock `geometric_status` and `magenta_status` are on; the code simply assumes index *i* ≡ index *i*.

---
## Cross-cutting: threshold provenance
`absolute_rmse_ceiling_blocks`, `minimum_*_target_sd_blocks` all derive from
`reference_p2_best_k_visible_rmse_blocks = 0.1660274234445584`. Verified: `p2_best_k_results.json` sha256
matches the authority's `source_bindings.p2_best_k` binding, and 2× / 3× reproduce the frozen thresholds
exactly. The **visibility** thresholds (0.95/0.95) have **no such derivation** — they are round numbers with no
recorded feasibility analysis against this apparatus. That omission is the proximate cause of the P3 blockage.
