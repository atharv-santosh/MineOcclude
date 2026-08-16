# 11 — Structured Defect Register

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**
A defect is called a **software** defect only where code violated its authority. Where the
authority itself was wrong or silent, it is classed as SCIENTIFIC_DESIGN / GATE_STATISTICS /
APPARATUS instead.

---
## D-01 — Entity render lags server entity state by ~3.36 ticks
| | |
|---|---|
| **CATEGORY** | `APPARATUS` (+ `DATA_PIPELINE` for the unvalidated assumption) |
| **SCIENTIFIC_INTENT** | The frame indexed *i* depicts the target at server tick *i*, so an activation from frames `[i−15, i]` may be labelled with `sheep_x[i]`. |
| **ACTUAL_IMPLEMENTATION** | The rendered entity position is a causal smoothing of the logged position with kernel peaking at k = 2–3, spread over k = 1–5, **group delay 3.364 ticks (small-sample t interval [3.185, 3.542]; trajectory bootstrap [3.219, 3.522])**. `h[0] ≈ 0.013`: the current tick's position is essentially never shown. |
| **ROOT_CAUSE** | Vanilla client-side entity interpolation plus capture of "the last fully completed frame" at `END_CLIENT_TICK`. The lockstep protocol synchronises capture with the server tick but does not cancel entity interpolation. |
| **EVIDENCE** | 3 independent methods (level regression, first-difference cross-correlation, calibration-free saturation-event timing), 12 trajectories, 4 speeds, both directions, all positive. FIR fit beats best pure delay by 33.0 %. `02_temporal_lag_reproduction.md`. |
| **FIRST_INTRODUCED** | Present in all captured evidence examined (Regime A first25 v2 → P2 → P3). No revision ever measured it. |
| **AFFECTED_PHASES** | Regime A, P1, P2, P3 |
| **AFFECTED_FILES** | `MineOccludeClient.java`, `EpisodeManager.java`, `p2c_capture.py::package` (temporal_alignment receipt), `p3_run_sequential.py::derive_artifacts` |
| **HISTORICAL_IMPLICATION** | P2's headline numbers are **pessimistic by ≈2.1× in RMSE**. Regime A's last-seen baseline was accidentally advantaged. **No historical PASS/FAIL label flips.** |
| **FUTURE_IMPLICATION** | Every P2-derived threshold in the P3 authority is mis-scaled (D-02). Hidden-onset constants become speed-dependent (D-03). |
| **SEVERITY** | **CRITICAL** |
| **REPAIR_REQUIRED** | Yes — future-facing. `src/mineocclude/prospective/temporal_alignment.py`, `clock_domains.py`. |
| **PROSPECTIVE_AUTHORITY_IMPACT** | A new authority must declare which physical instant a model frame represents, and must validate it on **real entity render vs server state**, not synthetic action/camera fixtures. |

---
## D-02 — P2-derived thresholds propagate the misalignment into the A′ design
| | |
|---|---|
| **CATEGORY** | `SCIENTIFIC_DESIGN` |
| **SCIENTIFIC_INTENT** | `reference_p2_best_k_visible_rmse_blocks` is the apparatus's achievable visible-readout error, and the natural scale for both the hidden-RMSE ceiling and the motion-headroom floor. |
| **ACTUAL_IMPLEMENTATION** | Frozen as 0.1660274234445584 — the *misaligned* value. Recomputed under physically derived alignment with the frozen procedure unchanged: **0.077802**. |
| **ROOT_CAUSE** | D-01, inherited without question. |
| **EVIDENCE** | `05_p2_corrected_metrics.json`, `07_future_threshold_blast_radius.md`. |
| **AFFECTED_PHASES** | P3 authority; any future A′ authority |
| **AFFECTED_FILES** | `p3a_freeze.py:34-37`, `p3_preoutcome_authority.json` |
| **HISTORICAL_IMPLICATION** | **None on completed verdicts** — headroom passed with margin under the (too-strict) floor, and the (too-lenient) RMSE ceiling was never reached because extraction never ran. |
| **FUTURE_IMPLICATION** | Headroom floor ≈2.1× too strict; hidden-RMSE ceiling ≈2.1× **too lenient** — a hidden readout twice as bad as intended could have qualified. |
| **SEVERITY** | **HIGH** |
| **REPAIR_REQUIRED** | Not code — requires a new prospectively frozen reference value. |
| **PROSPECTIVE_AUTHORITY_IMPACT** | All four numeric thresholds must be re-derived after alignment is prospectively fixed. |

---
## D-03 — `HIDDEN_BOUNDS` is a speed-blind spatial constant
| | |
|---|---|
| **CATEGORY** | `SCIENTIFIC_DESIGN` (stale constant) |
| **SCIENTIFIC_INTENT** | Place target windows inside a stably dual-hidden region. |
| **ACTUAL_IMPLEMENTATION** | Fixed world-x constants (`p3a_freeze.py:39-42`) imported from a Regime A calibration performed at one speed, applied unchanged at 2.0 / 2.5 / 3.0 b/s. |
| **ROOT_CAUSE** | The rendered-hidden boundary sits at `geometric_edge + silhouette_extent + lag·v`. Because the lag is constant in **ticks**, the boundary moves in **blocks** with speed (0.248 / 0.349 / 0.520 at 1.5 / 2.0 / 3.0 b/s). |
| **EVIDENCE** | Margin +0.04 / −0.03 / −0.09 blocks ⇒ NORMAL target-row contamination **0 / 1 / 7**, monotonic. Prior P3 audit §5; lag speed-invariance in ticks confirmed here. |
| **FIRST_INTRODUCED** | Regime A v2; already exceeded once (`t04 TRUE_FROZEN_GUARD_EXCEEDANCE`, guards widened 11/13 → 18/20) and re-patched rather than re-modelled. |
| **AFFECTED_PHASES** | Regime A, P3 (C02, C03) |
| **HISTORICAL_IMPLICATION** | Explains the recorded NORMAL target-row contamination. Does not change any P3 verdict (visibility already failed on calibration precision). |
| **SEVERITY** | **HIGH** |
| **REPAIR_REQUIRED** | Yes — future-facing: hidden onset must be specified in a physically coherent domain. |
| **PROSPECTIVE_AUTHORITY_IMPACT** | Hidden onset must be derived as `edge + extent + lag·v + safety`, not hardcoded. |

---
## D-04 — Visibility gate compares non-equivalent predicates
| | |
|---|---|
| **CATEGORY** | `VISIBILITY_SEMANTICS` |
| **SCIENTIFIC_INTENT** | Confirm the rendered detector agrees with ground-truth occlusion. |
| **ACTUAL_IMPLEMENTATION** | Point-visibility (one ray to the target centre) scored against any-silhouette visibility (any magenta blob ≥ 19 px), required to agree to 0.95 precision, pooled over all frames including the ~1.04-block transition band. |
| **EVIDENCE** | Prior P3 audit `03_visibility_forensics.md`; independently corroborated by the bound `directional_visibility_authority_v2.1_a1` recording a 17–19-frame partial/disagreement run. |
| **HISTORICAL_IMPLICATION** | Dominant cause of all three P3 candidate failures. Verdicts correct **as the gate was written**. |
| **SEVERITY** | **CRITICAL** |
| **REPAIR_REQUIRED** | Yes — future-facing: `visibility_semantics.py`. |
| **PROSPECTIVE_AUTHORITY_IMPACT** | Authority must name which predicate is primary and score agreement per regime. |

---
## D-05 — Gate statistic confounded with the swept variable
| | |
|---|---|
| **CATEGORY** | `GATE_STATISTICS` |
| **ACTUAL_IMPLEMENTATION** | Pooled `precision ≥ 0.95` over a fixed 180-frame window. Precision depends on class prevalence; prevalence is a direct function of speed. |
| **EVIDENCE** | FP-rate flat 0.1181 / 0.1039 / 0.1028 while precision rose 0.8468 / 0.9155 / 0.9376. Reproduced as a unit test (`test_precision_moves_with_prevalence_while_error_rate_is_fixed`). |
| **HISTORICAL_IMPLICATION** | Correct application of a mis-specified criterion. |
| **SEVERITY** | **CRITICAL** |
| **REPAIR_REQUIRED** | Yes — `detection_diagnostics.py`, `calibration_support.py`. |

---
## D-06 — Path/state gate narrower than authority
| | |
|---|---|
| **CATEGORY** | `PATH_GATE` (**software defect**: code did not implement its authority) |
| **SCIENTIFIC_INTENT** | 13 `exact_fields`, 4500 rows/scene/candidate. |
| **ACTUAL_IMPLEMENTATION** | Two checks (world-x hash; paired world-x equality). Other fields asserted only at capture time, so **resumed/reused units were never re-checked** — 41 of C01's 50 units were reused across a restart. No row count recorded. |
| **EVIDENCE** | `10_path_gate_audit.md`; 20 authority-scope invariants re-checked on all 150 units. |
| **HISTORICAL_IMPLICATION** | **BLAST RADIUS ZERO** — all invariants hold; the historical PASS verdicts were correct. |
| **SEVERITY** | **MEDIUM** (latent) |
| **REPAIR_REQUIRED** | Yes — `path_state_gate.py`, 24 tests. |

---
## D-07 — `scientific_run_id` silent default merges cohort tiers
| | |
|---|---|
| **CATEGORY** | `RUN_IDENTITY` / `PROVENANCE` |
| **ACTUAL_IMPLEMENTATION** | `spec.get("scientific_run_id", "mineocclude-regime-a-first25-v2")` — default fires for all 50 P2 and 300 P3 capture packages. |
| **EVIDENCE** | `09_run_identity_audit.md`. Episode/trajectory ids unique with zero P2∩P3 collision; no join uses `run_id`. |
| **HISTORICAL_IMPLICATION** | **Provenance only.** No historical row/capture mapping can be wrong. |
| **FUTURE_IMPLICATION** | A confirmatory selection written on `run_id` would merge Regime A scientific + P2 diagnostic + P3 development. |
| **SEVERITY** | **MEDIUM** |
| **REPAIR_REQUIRED** | Yes — `run_identity.py`, 9 tests. |

---
## D-08 — Historical controller not provenance-bound
| | |
|---|---|
| **CATEGORY** | `PROVENANCE` |
| **ACTUAL_IMPLEMENTATION** | `p3_run_sequential.py` was untracked at execution; its preflight asserted `HEAD == AUTHORITY_HEAD`, giving the appearance of provenance while the controller was outside the commit. |
| **EVIDENCE** | Codex `posthoc_p3_controller_receipt.json`: `git_tracking_status_at_baseline = "untracked"`, `present_in_baseline_head = false`, with the explicit caveat that the hash does not prove the executed bytes. |
| **HISTORICAL_IMPLICATION** | **PERMANENT AND UNREPAIRABLE.** Not repaired by this audit and not claimed to be. |
| **SEVERITY** | **HIGH** (process) |
| **REPAIR_REQUIRED** | Yes — future-facing only: `source_provenance.py`, 10 tests. |

---
## D-09 — Authority stores a rounded constant but demands exact equality
| | |
|---|---|
| **CATEGORY** | `OTHER` (documentation/precision) |
| **ACTUAL_IMPLEMENTATION** | `camera_eye_world_xyz = [0.5, 5.6200000048, -5.5]` is a 10-dp rounding of `5.620000004768372` (Δ = 3.16e−11), inside a gate whose authority says `exact_fields`. |
| **EVIDENCE** | `10_path_gate_audit.md`. Caused a false positive in the first pass of this very audit. |
| **HISTORICAL_IMPLICATION** | None. |
| **SEVERITY** | **LOW** |
| **REPAIR_REQUIRED** | Handled in `path_state_gate.py` (compare within rounding + require bitwise constancy). |

---
## D-10 — Named ambiguity check never implemented
| | |
|---|---|
| **CATEGORY** | `GATE_STATISTICS` (**software defect**) |
| **SCIENTIFIC_INTENT** | Visibility authority: "no identity/timestamp ambiguity". |
| **ACTUAL_IMPLEMENTATION** | `calibration_gate` defines `ambiguous` as `magenta_status ∉ {detected, not_detected}` (always 0); the target loop defines it as `geo != mag` (redundant). Neither is an identity/timestamp check. |
| **HISTORICAL_IMPLICATION** | None — both surrogates were 0/consistent. |
| **SEVERITY** | **LOW–MEDIUM** |
| **REPAIR_REQUIRED** | Covered by `detection_diagnostics.py` (`undetermined` counted separately, never coerced). |

---
## Summary counts
- **Software defects confirmed** (code violated authority): **D-06, D-10** → 2
- **Scientific-design defects confirmed**: **D-02, D-03, D-04, D-05** → 4
- **Apparatus defects confirmed**: **D-01** → 1
- **Provenance/bookkeeping defects confirmed**: **D-07, D-08, D-09** → 3
- **Historical PASS/FAIL labels changed by any of the above: NONE.**
