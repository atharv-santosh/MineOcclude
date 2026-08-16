# 04 — Exact P2 Image ↔ Target Alignment Trace

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**

## Step-by-step mapping, as implemented

| # | Step | Code | Index conversion | Clock domain | Offset |
|---|---|---|---|---|---|
| 1 | episode runs | `EpisodeManager.tick()` | tick `N` = tick-in-episode | SERVER_ENTITY_STATE | — |
| 2 | state logged | `ServerStateLogger.write()` | `server_state.jsonl[N]` | SERVER_ENTITY_STATE | 0 |
| 3 | frame captured | `MineOccludeClient.captureOne()` | `frames/{N:06d}.png`, `render_frame_idx = N` | CAPTURE_FRAME | **+3.364 ticks (unmeasured historically)** |
| 4 | artifacts derived | `derive_artifacts()` | `model_frame_idx := server_tick := render_frame_idx := action_idx := N` | asserted identical | **0 assumed** |
| 5 | coordinates | `project_world_to_coordinates(sheep_x, sheep_z)` | `coordinates.jsonl[N].world_x` | SERVER_ENTITY_STATE | 0 |
| 6 | target rows | `visibility.jsonl` rows with `tau ∈ 1..19` | `targets = [model_frame_idx]` | MODEL_FRAME | 0 |
| 7 | context window | `p2d_extract.py:166` | `indices = range(target-15, target+1)` — 16 frames, teacher forced | MODEL_FRAME | 0 |
| 8 | activation | layer-4 capture at final context position | `array[tau_index]`, shape `(19, 336, 2048)` fp16 | ACTIVATION_ROW | 0 |
| 9 | label | `p2e_analyze.load()` | `world_x = coordinates[frame].world_x` | GROUND_TRUTH_TARGET | 0 |
| 10 | readout | `best_k_readout` / `full_readout` | trajectory-grouped 5 outer folds, τ≤15 selection, τ1..19 evaluation | — | — |

**Verified**: `coordinates[N].world_x ≡ server_state[N].sheep_x`, max \|Δ\| = **0.0** over 260 rows.
No rounding, no floor/ceil, no nearest join, no interpolation, no resampling anywhere in the
chain. Cadence is exactly 20 Hz with one action / one frame / one server tick.

## The defect, stated precisely

Every conversion in the chain is **exact**. The chain is nonetheless **misaligned**, because step
3 carries a physical delay that step 4 asserts to be zero.

> The activation for target tick *T* is computed from frames `[T−15, T]`. Those frames depict the
> target's position filtered by the measured kernel — effectively **x(T − 3.364)**. The label
> attached to that activation is **x(T)**.

The P2 readout was therefore never scored on "read the position shown in the image". It was
scored on **"read the position shown in the image, then extrapolate it forward 3.364 ticks"** —
a task that includes an irreducible stochastic component (σ√3.364 = 0.0917 blocks at the frozen
q = 0.05) plus the systematic drift the readout had to infer.

## Off-by-one and staleness search — results

| Candidate defect | Verdict |
|---|---|
| off-by-one in `range(target-15, target+1)` | **No** — 16 indices, inclusive of target; matches `context_pairs = 16`, `effective_preceding_frames = 15` |
| tick/frame ratio mismatch | **No** — 1:1, enforced by cardinality assertions |
| model-frame subsampling error | **No** — no subsampling exists |
| nearest-join / timestamp rounding | **No** — joins are on exact integer index |
| label read from the wrong row | **No** — `world_x ≡ sheep_x`, exact |
| **client/server entity lag** | **YES — 3.364 ticks, the sole alignment defect** |
| action→camera timing generalised to entity-state→render timing | **YES — this is how the defect survived review** (see `03_clock_domain_trace.md`) |

## Not an implementation bug in the P2 analysis code

`p2e_analyze.py`, `p2d_extract.py` and `p2c_capture.py` all do exactly what their authority
specifies. Nothing in the P2 authority ever stated which physical instant a rendered frame
depicts. This is an **apparatus + specification** defect, not a coding error in the analysis
path — a distinction preserved in `11_defect_register.md`.
