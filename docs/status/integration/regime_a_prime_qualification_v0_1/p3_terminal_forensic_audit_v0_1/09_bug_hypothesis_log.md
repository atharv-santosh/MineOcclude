# 09 — Adversarial Bug Hypothesis Log

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.** Each hypothesis was actively tested against durable raw data.

| # | Hypothesis | Test | Result |
|---|---|---|---|
| 1 | Wrong scene assigned to a run | compare `server_state.scene` to commanded scene, all 27,000 rows | **FALSIFIED** — 0 mismatches |
| 2 | WALL rendered as NO_WALL (or vice versa) | NORMAL units must show an occlusion interval; NO_WALL must not | **FALSIFIED** — every NORMAL unit has a geometric occlusion interval; NO_WALL target rows 475/475 detected ×3 |
| 3 | Duplicated / colliding run IDs | set-vs-list cardinality on 150 capture + 12 calibration identities | **FALSIFIED** — all unique, 0 missing, 0 extra |
| 4 | Scene/server state leaking between reused `CaptureSession` episodes | `expected_path_sha256` per unit; `target_respawn_count == 0` asserted per row | **FALSIFIED** — 150/150 exact path match |
| 5 | Motion schedule not re-armed / noise mismatch | frozen vs observed target-x SD across all 75 specs | **FALSIFIED** — max |Δ| = 0.00e+00 |
| 6 | Wrong speed sign / direction reversal | start x sign vs `direction`; LTR from −7.8, RTL from +7.8 | **FALSIFIED** — consistent in all 162 units |
| 7 | Wrong initial position | `start_world_xyz` vs observed tick-0 x | **FALSIFIED** (within one frozen noise draw) |
| 8 | Wrong `expected_max_frames` | distinct frame counts per candidate | **FALSIFIED** — exactly {180} everywhere |
| 9 | Missing / duplicate / dropped frames | `server_tick` densely 0..179; `len(state)==len(ticks)==len(actions)==180` enforced at capture | **FALSIFIED** |
| 10 | Wrong target-time mapping / τ off-by-one | `target_server_ticks == range(onset+phase, +19)`, `target_tau == 1..19` | **FALSIFIED** — validated in `validate_authority()` and re-checked here |
| 11 | Frame-vs-tick indexing error | `frame_map`/`visibility` key on `model_frame_idx == server_tick == render_frame_idx == action_idx == i` | **CONFIRMED AS A LATENT ASSUMPTION** → see #22 |
| 12 | Resumption skipped or reused the wrong files | ledger `attempt` fields; largest-gap stratification | **FALSIFIED** — all `attempt: 1`, 41+9 = 50, no retries |
| 13 | S3 restore overwrote newer files | per-unit `sha256_manifest.json` + remote readback recorded at write time | **FALSIFIED** — all 162 manifests present, readback exact |
| 14 | Calibration files reused across candidates | per-candidate calibration IDs and seeds | **FALSIFIED** — 4 distinct IDs/seeds per candidate, 12 total, all `attempt: 1` |
| 15 | Candidate ID mis-parsed | ledger `candidate_id` vs directory vs manifest | **FALSIFIED** |
| 16 | Wall position/thickness mismatch | geometric shadow symmetry about camera x = 0.5 | **FALSIFIED** — [−4.80, +5.87], midpoint 0.53, half-width 5.33, stable across all 3 candidates |
| 17 | Viewport crop / clipping | FPs occur mid-frame at the wall edge, not at image borders; frames are 640×360 as asserted | **FALSIFIED** |
| 18 | Incorrect magenta segmentation | vectorised re-implementation vs frozen `detect_magenta` on sample frames | **FALSIFIED** — identical area and centroid on 5/5 frames |
| 19 | Detector false negatives | recall 0.979/0.990/0.995; after lag correction **1.000** | **Real but benign** — 12 FNs total, all at run start, all explained by #22 |
| 20 | Threshold computed in px but interpreted in blocks | `min_area_pixels`/`max_area_pixels` used only for detection; gate thresholds are unitless ratios | **FALSIFIED** |
| 21 | Float precision / inappropriate exact equality | ε = 0 path equality on bit-identical `<f8` arrays produced by the same frozen schedule | **FALSIFIED** — passed 150/150 |
| 22 | **Rendered frame not synchronous with the state row of the same index** | pixel-centroid ↔ `sheep_x` cross-correlation on NO_WALL runs, 2 speeds × 2 directions | **CONFIRMED — ≈3.3 server ticks of render lag**, constant in ticks across speeds |
| 23 | **Geometric predicate ≠ rendered predicate (point vs area)** | boundary profiling + direct frame inspection | **CONFIRMED — ~1.04-block disagreement band; at the first "occluded" frame the target is still 97 % visible** |
| 24 | **Gate metric confounded with the swept variable** | FP-rate vs precision vs base rate across candidates | **CONFIRMED — FP-rate flat (0.118/0.104/0.103); precision tracks base rate (0.400/0.532/0.608)** |
| 25 | **Stale spatial constant applied outside its calibrated speed** | predicted vs frozen `HIDDEN_BOUNDS` margin vs observed contamination | **CONFIRMED — margin +0.04/−0.03/−0.09 blocks ⇒ contamination 0/1/7** |
| 26 | Pooled weighting error (pooled rows where trajectory-equal intended) | authority forbids pooled override for *readout* metrics only; calibration gate is specified pooled | **Not a code bug — but see `10_root_cause_matrix.md` H4: pooling is what makes the metric base-rate sensitive** |
| 27 | Gate uses all frames where authority intended a subset | `calibration_gate` reads every row of `raw/visibility.jsonl` (180/run) | **CONFIRMED as specified-but-inappropriate** — includes the transition band the design excludes from scientific use |
| 28 | Stale P2 constants in P3 code | P2 RMSE 0.16602742 → 2×/3× thresholds; recomputed exactly | **FALSIFIED** — correct and intentional |
| 29 | Hidden reliance on execution order | candidates run strictly sequentially; `completed()` is identity-keyed and order-independent | **FALSIFIED** |
| 30 | Controller source not provenance-bound | `git status` | **CONFIRMED (process defect)** — `p3_run_sequential.py` is untracked and unhashed in the terminal receipt |
| 31 | P3 dev units carry confirmatory-cohort identity | `capture_package_v0_1.json` | **CONFIRMED (bookkeeping risk)** — `run_id = "mineocclude-regime-a-first25-v2"` on P3 development units |
| 32 | Authority's "identity/timestamp ambiguity" check missing | read `calibration_gate` and target-row loop | **CONFIRMED** — `ambiguous` implements two other things; the named check does not exist |
