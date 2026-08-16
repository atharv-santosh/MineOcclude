# 06 — P2 Substantive Validity Adjudication

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**
**The historical procedural verdict `GO_BEST_K_FULL_VISIBLE` is NOT modified and remains the
frozen record.** What follows is a separate, post-hoc, forensic interpretation.

## What was recomputed, and how

Persisted P2 layer-4 activations (25 runs × `(19, 336, 2048)` fp16, 653,724,800 bytes, restored
from the durable S3 prefix) were re-scored through the **frozen readout procedure imported
verbatim** (`p2e_analyze.best_k_readout`, `full_readout`, `summarize`). **Only the label vector
changed.** No new capture; no model inference; no procedure edit.

Alignment came from `b03_impulse_response.py` — physics only. **At no point was any alignment
selected because it improved a readout metric.** The falsification control (MODEL F, shifted the
wrong way) exists precisely to make that checkable.

## Results

| Model | Label for the activation at target tick *T* | BEST-K RMSE | BEST-K MAE | BEST-K macro R² | BEST-K bootstrap 95 % | FULL RMSE | FULL macro R² |
|---|---|---|---|---|---|---|---|
| **F — falsification control** (shifted the **wrong way**) | `x(T + 3)` | **0.218906** | 0.181055 | **0.616213** | [0.4896, 0.7190] | 0.208380 | 0.607369 |
| **A — historical** | `x(T)` | **0.166027** | 0.133158 | **0.790695** | [0.7239, 0.8472] | 0.166577 | 0.754803 |
| D_int4 — integer shift −4 | `x(T−4)` | 0.088864 | 0.069183 | 0.947389 | [0.9292, 0.9625] | 0.113677 | 0.913770 |
| C_int3 — integer shift −3 *(no smoothing)* | `x(T−3)` | 0.085583 | 0.067303 | 0.950666 | [0.9352, 0.9635] | 0.116775 | 0.904606 |
| C — legacy normal-interval lower sensitivity point | `x(T−3.211)` | 0.083555 | 0.064851 | 0.950261 | [0.9316, 0.9658] | 0.113416 | 0.910314 |
| E — direction-aware | LTR −3.287 / RTL −3.516 | 0.082312 | 0.063959 | 0.952095 | [0.9339, 0.9670] | 0.111904 | 0.913975 |
| **B2 — point group delay** | `x(T − 3.364)` | **0.082233** | 0.063662 | **0.952042** | [0.9336, 0.9672] | 0.111850 | 0.913145 |
| D — legacy normal-interval upper sensitivity point | `x(T−3.516)` | 0.082162 | 0.063438 | 0.952541 | [0.9343, 0.9676] | 0.111042 | 0.914919 |
| **B — kernel-convolved** (what the image depicts) | `Σ h[k]·x(T−k)` | **0.077802** | 0.059493 | **0.955541** | [0.9378, 0.9708] | 0.106828 | 0.916702 |

### The falsification control settles the sign

MODEL F shifts the label the **wrong way** (`x(T+3)`), doubling the misalignment instead of
removing it. It is **far worse than historical**: RMSE 0.2189 vs 0.1660, macro R² 0.616 vs 0.791.
Had the lag been an artifact of the estimator, or had its sign been wrong, F would not have
degraded so cleanly.

### The readout optimum independently coincides with the physics estimate

The alignment was fixed from physics **before** any readout was run, and no model was selected on
a readout metric. Nevertheless the RMSE profile across models is smooth and minimised in the
immediate neighbourhood of the physically estimated group delay (3.364 ticks), with the
kernel-convolved label — the physically exact statement of *what the image depicts* — best of all.
Two fully independent routes to the same number is the strongest corroboration available from
existing data.

### Direction-awareness is not justified
MODEL E (LTR −3.287 / RTL −3.516) is indistinguishable from the single-value MODEL B2
(RMSE 0.082312 vs 0.082233). The direction difference measured in Phase 2 (0.23 ticks) is smaller
than the between-trajectory sd (0.27), and buys nothing here. **`LAG_DIRECTION_DEPENDENT = false`.**

### Pure integer shifts confirm it is not a smoothing artifact
C_int3 and D_int4 apply **no smoothing whatsoever** — they are the logged path read at an earlier
tick, with the same marginal statistics as the historical label. They recover almost the entire
improvement (RMSE 0.0856 / 0.0889 vs 0.0778 for the kernel). The gain is alignment, not variance.

MODEL A reproduces the frozen historical values **exactly**, validating the harness.

## Interpretation

The historical P2 readout was never scored on "read the position shown in the image". It was
scored on **"read the image, then extrapolate 3.364 ticks"**. Removing that extrapolation burden
— without changing the model, the features, the folds, the selection procedure, or the bootstrap
— **halves the RMSE and raises trajectory-equal macro R² from 0.79 to 0.96.**

The improvement is **not** a variance artifact: the corrected labels carry *more*
within-trajectory variance than the historical ones (1.048×, `13_repair_validation.md`).
The quadrature reduction (0.1467 blocks) exceeds the irreducible stochastic component of a
3.364-tick extrapolation (σ√3.364 = 0.0917 blocks), which is expected — the readout also had to
infer the systematic drift.

## Answers to the primary scientific question

**What physical instant does each rendered image represent?**
A causally smoothed average of server entity states, kernel peaking at 2–3 ticks back, spread
over 1–5 ticks, **group delay 3.364 ticks (small-sample t interval [3.185, 3.542];
trajectory bootstrap [3.219, 3.522]) = 0.1682 s = 3.364 model frames** behind the
state row historically paired with it. The 3.211/3.516 rows above are retained
only as already-computed sensitivity points; they are not the primary interval.

**What server state was historically paired with that image?**
`server_state[i].sheep_x` — the state **at** tick *i*, i.e. ~3.364 ticks *after* the instant the
image depicts.

| # | Question | Answer |
|---|---|---|
| 1 | P2 image ↔ ground-truth alignment | **Materially wrong** — off by 3.364 ticks (0.252 blocks at 1.5 b/s) |
| 2 | BEST-K metrics | **Materially changed, in P2's favour** — RMSE 0.1660 → 0.0778 |
| 3 | FULL metrics | **Materially changed, in P2's favour** — RMSE 0.1666 → 0.1068 |
| 4 | P2's substantive visible-readout conclusion | **Survives and is strengthened** |
| 5 | Numbers intended to flow into A′ | **Invalid as frozen** — see `07_future_threshold_blast_radius.md` |
| 6 | Historical Regime A interpretation | **Numerically affected; verdict stable** — see `08_regime_a_blast_radius.md` |
| 7 | Future hidden-onset / visibility definitions | **Must be rebuilt** — hidden onset is speed-dependent through lag·v (D-03) |

## Adjudication

`P2_SUBSTANTIVE_CONCLUSION_AFTER_CORRECTION = **VALID_WITH_NUMERIC_REVISION**`

- **VALID**, not `NOT_SUPPORTED`: the qualitative claim P2 was built to test — *layer-4 activations
  recover the target's visible position on the current apparatus* — is not merely intact but
  substantially stronger under corrected alignment. Both qualification criteria
  (macro R² > 0; bootstrap lower bound > 0) pass by a wider margin.
- **WITH_NUMERIC_REVISION**, not plain `VALID`: every headline number moves by roughly a factor of
  two, and those numbers were the arithmetic basis for four downstream A′ thresholds. The
  conclusion survives; the constants do not.
- Not `UNCERTAIN`: the alignment was established by three independent physical methods with a
  quantified CI, and the recomputation used the frozen procedure with a validated harness.

### One honest caveat
The historical P2 result remains *literally correct* as a measurement of a slightly different
quantity: "position 3.364 ticks ahead of the most recently depicted position". That is a
**motion-extrapolation-inclusive** readout. It is not wrong — it is mislabelled. Any future
authority must state which of the two quantities it is qualifying, because they differ by a
factor of two in RMSE.
