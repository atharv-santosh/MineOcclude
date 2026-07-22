# Person B: Scientific Methods Roadmap

## Objective

Own MineOcclude's oracle, probes, statistical analysis, U1-U4 interpretation, and claim validity from MVP setup through final scientific sign-off.

Full details: [`PERSON_B_MVP_ROADMAP.md`](./PERSON_B_MVP_ROADMAP.md)

## Current blockers

- [ ] Receive a completed real activation handoff from Person A; the frozen
  contract and compatibility evidence are already merged.
- [ ] Receive authoritative state schema, manifest, and pilot logs from Person C.
- [ ] Produce Person D baseline artifacts against B's frozen consumer contract
  (the same owner now holds B and D).
- [ ] Receive registry and U4 measurement schemas from Person E.

## MVP work

- [x] Freeze analysis targets, units, exclusions, folds, seeds, and metrics in `configs/analysis/core.yaml`.
  - [x] Mark hidden truth as scoring-only.
  - [x] Lock five layout-grouped folds and train-only preprocessing.
- [x] Implement the exact Regime A oracle.
  - [x] Build independent scalar-filter and closed-form implementations.
  - [x] Test at least 100 seeded cases with agreement within `1e-6`.
  - [x] Add variance-growth, `q`-sensitivity, and reveal-reset tests.
- [x] Create synthetic state logs, expected targets, and an oracle validation plot.
- [x] Prove each Person A activation layer/site row joins exactly one frame target, with complete-grid, cardinality, and leakage audits.
- [x] Implement the artifact-independent B analysis foundation.
  - [x] Bind claim-bearing runs to literal config bytes.
  - [x] Add signed wall-parallel coordinate requirements.
  - [x] Add ordered filters, stable rejection codes, and count audits.
  - [x] Add saved fold/scaler/fit/prediction/result manifests and hashes.
  - [x] Add grouped inner selection, ridge/MLP OOF fitting, and MLP eligibility.
  - [x] Add U1-U3 metric functions and known-answer tests.
  - [x] Add hierarchical bootstrap and whole-trajectory permutation functions.
  - [x] Add raw-space/time-projected direction and B→A producer plumbing.
  - [x] Add C/D/E intake validators; producer signoff/artifacts remain pending.
- [ ] Run the no-wall visible positive-control probe before interpreting hidden-state results.
- [ ] Run the per-layer analysis.
  - [ ] U1: posterior-mean decoding, grouped permutations, controls, and MLP comparison.
  - [ ] U2: time-controlled spread, coverage/ECE, z diagnostics, and grouped bootstrap.
  - [ ] U3: hidden-time growth and reveal-snapback analysis.
- [ ] Derive the U4 posterior-mean direction and doses.
  - [ ] Convert the probe direction to raw activation space.
  - [ ] Project out elapsed time and verify prediction equivalence.
  - [ ] Map alpha to blocks and enforce the activation-norm cap.
- [ ] Classify the MVP result as green, yellow, or red without moving the criteria.
- [ ] Present oracle, U1-U3, U4, controls, limitations, and claim-safe conclusions at the checkpoint.
- [ ] Preserve the accepted state as `mvp-2026-07-26` with matching artifact hashes.

## Post-MVP work

- [ ] Week 2: lock the full analysis plan, run complete Regime A analysis, and specify Regime B calibration.
- [ ] Week 3: complete core statistics and mechanistic analyses across depth, geometry, context, and selected tokens.
- [ ] Week 4: lock results and counts; write Results, statistics, oracle/probe/calibration/U4 Methods, and claim boundaries.
- [ ] Week 5: triage review feedback, recompute only correctness-impacting analyses, and maintain the correction log.
- [ ] Week 6: audit every final metric, CI, count, unit, figure, and claim; approve U1-U4 wording and sign off scientifically.

## Definition of done

- [ ] All reported predictions are out-of-fold or held out with complete provenance.
- [ ] Every result uses grouped layouts/trajectories rather than treating frames as independent.
- [ ] Every scientific value comes from locked machine-readable output, never hand editing.
- [ ] Every conclusion maps to U1, U2, U3, U4, or a clearly labeled diagnostic.
- [ ] Failed engineering or measurement gates are not presented as negative scientific results.
- [ ] Final manuscript numbers and claims match the locked result fact sheet exactly.
