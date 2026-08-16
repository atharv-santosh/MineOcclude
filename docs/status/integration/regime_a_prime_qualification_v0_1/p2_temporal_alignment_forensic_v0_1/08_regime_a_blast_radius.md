# 08 — Regime A Direct Temporal-Alignment Reanalysis

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.** Historical Regime A artifacts
remain read only. Script: `audit_scripts/b08_regime_a_blast_radius.py`; machine
receipt: `regime_a_blast_radius.json`.

The earlier quadrature calculation was not a mathematical upper bound and is
withdrawn. Stability is established here by direct deterministic refit using
only receipt-hashed persisted Regime A layer-4 activations, receipt-hashed
persisted Regime A server-state logs, the frozen nested FULL/BEST-K procedures,
and the independently measured causal FIR kernel. No capture or model inference
was performed.

## Direct refit with the causal FIR physical target

The target at frame *t* is replaced with `sum_k h[k] x[t-k]`, then FULL,
BEST-K, time-only, and training-mean procedures are refit on their original
outer/inner trajectory folds. BEST-K token ranking is recomputed from training
rows only. Values below are trajectory-equal RMSE in blocks; parenthetical
values are macro R².

| Domain | neural FULL | neural BEST-K | time-only | training mean | corrected last-seen |
|---|---:|---:|---:|---:|---:|
| FULL τ1..15 | 0.3928 (-0.8693) | 0.3280 (-0.2410) | **0.1408 (0.7331)** | **0.1688 (0.6722)** | 0.7397 |
| SHORT | 0.4224 (-27.8419) | 0.3593 (-17.9159) | **0.0527 (0.4807)** | **0.1112 (-0.4009)** | 0.2406 |
| INTERMEDIATE | 0.3644 | 0.2803 | **0.1130** | **0.1503** | 0.5539 |
| LONG | 0.3147 | 0.2631 | **0.1580** | **0.1820** | 0.8588 |
| NEAR_CONTEXT | 0.3612 | 0.3028 | **0.1934** | **0.2084** | 1.1214 |
| τ8..15 | 0.3617 | 0.2959 | **0.1727** | **0.1954** | 0.9473 |
| BEYOND_CONTEXT | 3.2873 | 3.3097 | **0.2155** | **0.2292** | undefined (no evidence-bearing context) |

The corrected primary FULL macro R² remains below zero, so the historical
continuation gate still fails independently of its B=49 null result. On the
FULL domain, time-only and training-mean beat FULL by 0.2519 and 0.2239 blocks;
they also beat the corrected BEST-K readout by 0.1871 and 0.1591 blocks.
Both trivial baselines beat both neural readouts in every reported duration
domain, including SHORT and later hidden domains.

## Direct last-seen sensitivity with the historical hidden target fixed

This is a separate diagnostic because the hidden server-state target itself is
authoritative. Only the position physically depicted by the last evidence
frame is FIR-corrected; historical neural predictions and hidden targets remain
fixed.

| Domain | historical last-seen | FIR-corrected depicted last-seen | historical neural BEST-K |
|---|---:|---:|---:|
| FULL τ1..15 | 0.6955 | **0.9707** | 0.3502 |
| SHORT | **0.2164** | **0.5059** | 0.3948 |
| τ8..15 | 0.8901 | **1.1863** | 0.3133 |

The SHORT comparison changes materially and flips: neural BEST-K historically
lost to last-seen by 0.1784 blocks, but beats the physically corrected
last-seen value by 0.1111 blocks. This does not rescue Regime A because the
direct corrected refit above shows time-only and training-mean still decisively
defeat both neural readouts.

`REGIME_A_DIRECT_REANALYSIS_STATUS = PASS`

`REGIME_A_CONCLUSION_STABLE = yes`

`REGIME_A_HISTORICAL_RESULT_MODIFIED = false`
