# 07 — Blast Radius on Prospective A′ Thresholds

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY. No authority is edited by this document.**

## The propagating constant
`p3a_freeze.py:34` and `p3_preoutcome_authority.json` both anchor on

```
P2_BEST_K_RMSE_BLOCKS = reference_p2_best_k_visible_rmse_blocks = 0.1660274234445584
```

That number is the **historically misaligned** BEST-K visible RMSE. Recomputed under the
physically derived alignment with the frozen readout procedure unchanged, the same quantity is
**0.077802** (kernel-convolved label) / **0.082233** (point group-delay label) — the historical
value is **≈2.1× too large**.

Every P3 threshold is a multiple of it.

## Classification of each P2-derived value that flows into A′

| Value | Historical | Derivation | Recomputed basis | Class |
|---|---|---|---|---|
| `reference_p2_best_k_visible_rmse_blocks` | 0.1660274234445584 | P2 BEST-K visible RMSE | **0.0778** | **RECOMPUTE_REQUIRED** |
| `absolute_rmse_ceiling_blocks` | 0.3320548468891168 | 2 × P2 RMSE | ≈ 0.1556 | **RECOMPUTE_REQUIRED** — historical ceiling is **≈2.1× too lenient**; a hidden readout could have qualified while being twice as bad as intended |
| `minimum_each_trajectory_target_sd_blocks` | 0.3320548468891168 | 2 × P2 RMSE | ≈ 0.1556 | **RECOMPUTE_REQUIRED** — historical headroom floor is **≈2.1× too strict** |
| `minimum_candidate_median_target_sd_blocks` | 0.4980822703336752 | 3 × P2 RMSE | ≈ 0.2334 | **RECOMPUTE_REQUIRED** — same, ≈2.1× too strict |
| P2 BEST-K macro R² (0.7907) as evidence "visible position is decodable" | 0.7907 | direct | **0.9555** | **SAFE_TO_RETAIN as a lower bound** — the corrected value is strictly better, so the qualitative claim is conservative |
| P2 bootstrap lower bound > 0 | 0.7239 | direct | **0.9378** | **SAFE_TO_RETAIN as a lower bound** |
| `time_confound_gate.maximum_trajectory_equal_macro_r2_tau_1_to_15 = 0.10` | 0.10 | round number | not P2-derived | **SAFE_TO_RETAIN** (but see note) |
| visibility calibration `0.95` precision / `0.95` recall | 0.95 | round numbers, no derivation | not P2-derived | **DISCARD** — shown structurally unsatisfiable and base-rate confounded (prior P3 audit) |
| BEST-K leading / FULL secondary role | — | procedural | unchanged | **SAFE_TO_RETAIN** |
| K grid, alpha grid, fold structure, bootstrap seed/resamples | — | procedural | unchanged | **SAFE_TO_RETAIN** |
| `context_pairs = 16`, `effective_preceding_frames = 15` | — | apparatus | unchanged | **SAFE_TO_RETAIN** |
| Camera / FOV / resolution / token grid | — | apparatus | unchanged | **SAFE_TO_RETAIN** |
| `HIDDEN_BOUNDS` directional constants | −3.7310 / +4.8376 etc. | Regime A empirical, single speed | invalid off 2.0 b/s | **DISCARD** — must become speed-aware |
| Sample-size / power assumptions | none recorded | — | — | **UNCERTAIN** — no explicit power analysis exists to re-derive |

## Direction of the error matters

The mis-derived constant pushes **two gates in opposite directions**:

- **Headroom** (a *floor* = 2×/3× RMSE) was set **≈2.1× too high** → P3 demanded more motion
  headroom than the apparatus actually required. C01 passed anyway, with margin — so under a
  corrected floor (0.156 / 0.233) C01's headroom (min 0.4187, median 0.5683) would pass even
  more comfortably. **No historical verdict changes.**
- **RMSE ceiling** (a *cap* = 2× RMSE) was set **≈2.1× too lenient** → had extraction ever been
  reached, a hidden readout roughly twice as inaccurate as intended could have qualified.
  Extraction was never reached in P3, so **no historical result is affected** — but this would
  have been a live scientific error the moment a candidate passed the visibility gate.

**That is the most consequential forward-looking consequence of the lag defect:** it did not
corrupt any completed P3 verdict, but it had already mis-set the bar that a future confirmatory
qualification would have been measured against.

## Not yet actionable
`NEW_PROSPECTIVE_AUTHORITY_REQUIRED = true`. The corrected P2 numbers reported here are
**post-hoc forensic diagnostics**. They may inform, but may not silently become, a new authority:
a corrected reference RMSE must be established under a prospectively frozen alignment procedure
before any threshold is re-derived from it.
