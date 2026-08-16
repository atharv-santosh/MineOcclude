# 02 — Independent Reproduction of the Render/State Temporal Lag

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**
Scripts: `audit_scripts/b02_lag_multimethod.py`, `audit_scripts/b03_impulse_response.py`.
The prior P3 audit's ~3.3-tick figure was **not** inherited. Its code was not re-run; the
measurement was rebuilt from raw evidence with three conceptually independent methods, on a
**wider** evidence base (P2 at 1.5 b/s added, giving four speeds instead of two).

## Methods

| | Method | What it uses | What it is immune to |
|---|---|---|---|
| **A** | Level-domain regression of rendered blob centroid on logged `sheep_x` over integer lag | homography-free pixel centroid | — |
| **B** | **First-difference cross-correlation** (`Δcentroid ~ a·Δx[t−k]`, no intercept) | only the stochastic increments | any constant spatial offset; the px/block scale |
| **C** | **Kinematic saturation event**: the lane clamp at \|x\|=8 stops the motion; compare the tick at which logged x saturates with the frame at which the rendered centroid saturates | "when does motion stop" | homography, wall geometry, scale calibration, offset — *entirely* |

Method C uses no calibration of any kind, which is why it is included: it can confirm the sign
and rough magnitude of the lag even if every geometric assumption in A and B were wrong.

## Result — all three methods agree that the render lags the state

12 NO_WALL trajectories (8 × P2 @1.5 b/s, 2 × P3DEV_C01 @2.0, 2 × P3DEV_C03 @3.0), both directions:

| Method | n | mean | median | sd | min | max |
|---|---|---|---|---|---|---|
| A level regression | 12 | **+3.11** | +3.09 | 0.34 | +2.33 | +3.77 |
| B first-difference | 12 | **+2.46** | +2.34 | 0.30 | +2.04 | +2.94 |
| C saturation event | 12 | **+4.17** | +4.00 | 0.55 | +3.00 | +5.00 |

Sign convention: **positive = the frame written with index *i* depicts the target where it was
*i* − lag ticks.** Every trajectory, every method, every speed, both directions gives a positive
lag. `TEMPORAL_LAG_REPRODUCED = true`.

## The methods disagree systematically — and that falsifies the pure-delay model

B < A < C is not noise; it is the signature of a **causal smoothing filter** rather than a delay
line. B is weighted toward high-frequency increments (attenuated, not merely delayed); A is
weighted toward the low-frequency random walk (full DC group delay); C measures when the
impulse response has fully decayed (later than the group delay).

Deconvolving the causal impulse response in the first-difference domain (non-negative least
squares, `Δcentroid ~ Σ h[k]·Δx[t−k]`, kernel normalised to unit sum):

```
h[0] = 0.0129 ± 0.0178  #
h[1] = 0.0526 ± 0.0426  ###
h[2] = 0.2950 ± 0.0552  ##################
h[3] = 0.2601 ± 0.0542  ################
h[4] = 0.1512 ± 0.0548  #########
h[5] = 0.1230 ± 0.0546  #######
h[6] = 0.0436 ± 0.0450  ###
h[7] = 0.0342 ± 0.0263  ##
h[8] = 0.0275 ± 0.0361  ##
```

- **Five taps exceed 0.05.** The response is spread, not a spike. **The pure-delay model is
  falsified**: the FIR model's residual is 0.7262 vs 1.0843 for the best single-tap delay — a
  **33.0 % better fit**.
- `h[0] ≈ 0.013`: the rendered frame essentially **never** shows the current tick's position.
  This is physically expected — the client captures at `END_CLIENT_TICK`, and the mod's own
  comment states the framebuffer then holds "the last fully completed frame".

## Headline estimate

| Quantity | Value |
|---|---|
| **Group delay** Σ k·h[k] | **3.364 server ticks** |
| Small-sample 95% Student-t interval on the mean (n = 12, df = 11) | **[3.185, 3.542]** ticks |
| Trajectory bootstrap 95% percentile interval | **[3.219, 3.522]** ticks |
| sample sd across trajectories (ddof=1) | 0.281 ticks |
| In seconds @ observed 20 Hz cadence | **0.1682 s**; t interval **[0.1593, 0.1771] s** |
| In model frames (1 tick / model frame) | **3.364** |

## Invariance structure

| Question | Evidence | Answer |
|---|---|---|
| Approximately constant in **ticks** over observed conditions? | 1.5 b/s → 3.307; 2.0 → 3.485; 3.0 → 3.469 | **No material dependence detected over observed speeds** |
| Approximately constant in **seconds** over observed conditions? | equivalent to ticks at the observed fixed 20 Hz cadence | same observed-condition result |
| Approximately constant in **model frames** over observed conditions? | observed cadence is 1 tick/model frame | same observed-condition result |
| Constant in **blocks**? | 0.248 / 0.349 / 0.520 blocks at 1.5 / 2.0 / 3.0 b/s | **NO — scales with speed** |
| **Speed dependent?** | 3.307 / 3.485 / 3.469 ticks, spread 0.18 vs sd 0.27 | **No material dependence detected over observed speeds; universal speed independence is not established** |
| **Direction dependent?** | LTR 3.287, RTL 3.516 (Δ 0.23 < sd 0.27) | **No compelling direction effect in the current sample; universal direction independence is not established** |
| **Scene dependent?** | measured on NO_WALL only, where the silhouette is always whole; NORMAL cannot be measured cleanly because occlusion truncates the blob | **not established** |
| **Restart dependent?** | available P3 restart strata show no detectable contamination; estimates (3.70 / 3.27) sit inside the P2 spread | **No restart-associated difference detected in available strata; universal restart independence is not established** |

**That the lag is constant in ticks but not in blocks is the fact that invalidated the fixed
`HIDDEN_BOUNDS` world-x constant above 2.0 blocks/s** (see `08_regime_a_blast_radius.md` and the
prior P3 audit's §5).

## Mechanism

The measurement is consistent with **causal client-side entity interpolation/smoothing**: the
server logs the authoritative entity position, the client receives tracked position updates and
lerps toward them over several client ticks, and the capture takes the last completed render.
The lockstep protocol synchronises *frame capture with server tick* but does not cancel the
client's entity interpolation. The capture package's own
`temporal_alignment.evidence_scope = "synthetic_contract_only"` confirms the gap: alignment was
verified for **action → camera** response, never for **entity render vs entity server state**.

The mechanism is *inferred*; the magnitude and the kernel shape are *measured*.
