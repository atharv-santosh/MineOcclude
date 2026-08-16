# 18 — Regime A Direct Existing-Data Reanalysis

**Status: PASS.** This analysis uses existing receipt-hashed data only and does
not alter the closed Regime A result.

## Inputs and procedure

- 25 persisted Regime A layer-4 arrays, each verified against the frozen input
  binding SHA-256;
- 25 persisted Regime A `server_state.jsonl` objects selected unambiguously and
  verified from durable receipts;
- 475 frozen target identities and outer folds;
- the measured nine-tap causal FIR kernel (group delay 3.363631 ticks);
- the frozen `Analysis.nested_scalar` FULL procedure and `Analysis.best_k`
  procedure, including training-only inner selection and recomputed token ranks;
- deterministic refits of time-only and training-mean baselines.

JSON-versus-Parquet target serialization differed by at most 8.9×10⁻¹⁶ blocks
(one binary64 ULP); the script fails above 2×10⁻¹⁵ as an encoding check.

## Direct corrected results

Trajectory-equal RMSE, FULL τ1..15:

| Quantity | RMSE | macro R² |
|---|---:|---:|
| neural FULL | 0.392754 | -0.869312 |
| neural BEST-K | 0.327960 | -0.241047 |
| time-only linear | **0.140838** | **0.733129** |
| training mean | **0.168830** | **0.672224** |
| last-seen under fully realigned target | 0.739699 | -3.806625 |

The primary corrected macro R² is still below zero, independently preserving a
terminal gate failure. Time-only and training-mean beat FULL by 0.251916 and
0.223924 blocks, and beat BEST-K by 0.187123 and 0.159131 blocks. They also beat
both neural readouts on SHORT, INTERMEDIATE, LONG, NEAR_CONTEXT, τ8..15, and
BEYOND_CONTEXT.

With the historical hidden target held fixed, FIR-correcting only last-seen
changes SHORT RMSE from 0.216441 to 0.505942. Historical neural BEST-K is
0.394794, so the SHORT comparison flips from neural losing by 0.178353 to neural
winning by 0.111149 blocks. This expected material change is directly verified,
not bounded.

The exact machine receipt and fold selections are in
`regime_a_blast_radius.json`; the method and broader table are in
`08_regime_a_blast_radius.md`.

`REGIME_A_DIRECT_REANALYSIS_STATUS = PASS`

`REGIME_A_CONCLUSION_STABLE = yes`

`REGIME_A_HISTORICAL_RESULT_MODIFIED = false`
