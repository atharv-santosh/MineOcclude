# P2 Temporal-Alignment Forensic Audit — Summary

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**
Starting freeze commit `351da852965bb20f89fe848bdef71703c34f0705`, branch
`exploration/regime-a-prime-qualification-v0-1`. No commit, no push, no branch change, no
historical artifact modified. All Claude work left uncommitted for operator + Codex review.

## Verdict in one paragraph

The ~3.3-tick render lag was **independently reproduced and materially refined**. Three
conceptually independent physical methods — level regression, first-difference cross-correlation,
and a calibration-free kinematic saturation event — all show the rendered entity lagging the
logged server state, across four speeds and both directions. Deconvolution **falsifies the
pure-delay model**: the render is a *causal smoothing filter* with a group delay of
**3.364 server ticks** (small-sample t interval **[3.185, 3.542]**; trajectory
bootstrap **[3.219, 3.522]**) = 0.1682 s = 3.364 model frames, with no material
tick dependence detected over observed speeds and therefore **not** constant in world blocks. Re-scoring P2's persisted layer-4
activations through the **frozen** readout procedure — changing only the label alignment, never
tuning on a readout metric — cuts BEST-K RMSE from **0.166027 to 0.077802** and raises
trajectory-equal macro R² from **0.7907 to 0.9555**. P2's substantive conclusion therefore
**survives and is strengthened**, but every P2-derived constant in the P3 authority is
**≈2.1× mis-scaled** — leaving the hidden-RMSE ceiling ≈2.1× too lenient. Regime A's
`FAIL_NO_DEFENSIBLE_DECODING` **stands after direct deterministic refit**: corrected
FULL macro R² is −0.8693 and corrected FULL RMSE 0.3928, while corrected time-only
and training-mean RMSE are 0.1408 and 0.1688. The rejected quadrature argument is
not used.

## Confirmed defects (full register in `11_defect_register.md`)

| ID | Category | Severity | Historical impact |
|---|---|---|---|
| D-01 | APPARATUS | **CRITICAL** | P2 numbers pessimistic ≈2.1×; **no verdict flips** |
| D-02 | SCIENTIFIC_DESIGN | HIGH | none on completed verdicts; mis-scales all future thresholds |
| D-03 | SCIENTIFIC_DESIGN | HIGH | explains NORMAL target-row contamination 0/1/7 |
| D-04 | VISIBILITY_SEMANTICS | **CRITICAL** | dominant cause of all three P3 failures |
| D-05 | GATE_STATISTICS | **CRITICAL** | gate tracked the swept variable, not detector quality |
| D-06 | PATH_GATE (**software**) | MEDIUM | **blast radius ZERO** — all 20 invariants hold on all 150 units |
| D-07 | RUN_IDENTITY | MEDIUM | **provenance only** — ids unique, no join uses `run_id` |
| D-08 | PROVENANCE | HIGH | **permanent, unrepairable**, not claimed repaired |
| D-09 | OTHER | LOW | none (caused a false positive in this audit's first pass) |
| D-10 | GATE_STATISTICS (**software**) | LOW–MED | none |

**No historical PASS/FAIL label changes as a result of any defect found.**

## Key numbers

| | Historical | Corrected (MODEL B) | Δ |
|---|---|---|---|
| BEST-K RMSE | 0.1660274234445584 | **0.077802** | −53 % |
| BEST-K MAE | 0.13315757524309618 | **0.059493** | −55 % |
| BEST-K macro R² | 0.7906954002303574 | **0.955541** | +0.165 |
| BEST-K bootstrap 95 % | [0.72387, 0.84724] | **[0.9378, 0.9708]** | — |
| FULL RMSE | 0.16657677302324672 | **0.106828** | −36 % |
| FULL macro R² | 0.7548030087626074 | **0.916702** | +0.162 |

MODEL A (historical pairing) reproduced the frozen numbers **exactly**, validating the harness.
The corrected labels carry **1.048× more** within-trajectory variance, so the gain is not a
smoothing artifact. Nine alignment models were run; the **falsification control** (label shifted
the *wrong* way, `x(T+3)`) degrades to RMSE **0.218906** / macro R² **0.616213**, confirming the
sign. Pure integer shifts with no smoothing at all (`x(T−3)`, `x(T−4)`) recover almost the whole
improvement. The readout-optimal alignment coincides with the physics-derived group delay,
although the physics estimate was made without reference to any readout metric.

## Repairs delivered (future-facing only, uncommitted)

`src/mineocclude/prospective/` — 8 modules: `clock_domains`, `temporal_alignment`,
`visibility_semantics`, `detection_diagnostics`, `calibration_support`, `path_state_gate`,
`run_identity`, `source_provenance`. No P1/P2/P3 script imports this package.

`tests/prospective/` — **196 tests, all passing**, all deterministic. Bounded
repair #2 details are recorded in `20_bounded_repair_2.md`.

## Documents
`00_checkpoint_receipt.json` · `01_evidence_inventory.json` · `02_temporal_lag_reproduction.md` ·
`03_clock_domain_trace.md` · `04_p2_alignment_trace.md` · `05_p2_corrected_metrics.json` ·
`06_p2_impact_analysis.md` · `07_future_threshold_blast_radius.md` · `08_regime_a_blast_radius.md` ·
`09_run_identity_audit.md` · `10_path_gate_audit.md` · `11_defect_register.md` ·
`12_repair_summary.md` · `13_repair_validation.md` · `14_redesign_readiness.md` ·
`audit_scripts/` (8 deterministic scripts) · supporting raw JSON.

## Next allowed action
Operator scientific review, then independent Codex review of the uncommitted repairs. Nothing may
be captured, and no authority frozen, until a corrected prospective authority exists.
`REGIME_A_PRIME_COLLECTION_AUTHORIZED = NO`. `CONFIRMATORY_COLLECTION_AUTHORIZED = false`.
