# Person B MVP Roadmap: Scientific Methods

## Mission

Person B owns the scientific validity of the MineOcclude MVP. The role is to define and validate the Regime A oracle, join oracle targets to indexed MineWorld activations, run leakage-safe probes and U1-U3 statistics, derive the U4 posterior-mean intervention direction and doses, and limit every conclusion to what the evidence supports.

The Week 1 MVP is a small end-to-end experiment, not the final paper-scale study. It must prove that one traceable path can run from synchronized Minecraft data through oracle targets, activations, probes, controls, intervention plumbing, metrics, and a claim-safe checkpoint decision.

Source authority: the final proposal controls the research question, Regimes A/B, Bayesian targets, probes, baselines, U1-U4 criteria, and scientific claims. The mentor-aligned execution guide controls the MineWorld-compatible interfaces, Fabric handoffs, MVP schedule, planning gates, and ownership. This roadmap narrows those sources to Person B's Week 1 work only.

## Scope boundary

Person B owns:

- Oracle definitions, information sets, units, invariants, and tests.
- Analysis schemas, exclusions, layout-grouped splits, train-only preprocessing, probe configuration, resampling, and metrics.
- U1 posterior-mean decoding, U2 calibrated-spread analysis, and U3 uncertainty-dynamics analysis.
- The raw-space U4 posterior-mean direction, elapsed-time projection, alpha-to-block dose mapping, and U4 statistical plan.
- Scientific interpretation, alternative-result classification, and claim-to-evidence boundaries.
- Approval of changes to samples, splits, metrics, oracle logic, analysis logic, or scientific claims.

Person B does not own:

- MineWorld loading, teacher-forced inference, hooks, activation extraction, or injection code (Person A).
- Minecraft/Fabric implementation, collection, authoritative state logs, or exclusions at capture time (Person C).
- Baseline implementation and literature verification (Person D), though B defines the shared folds and statistical comparison contract.
- Detection, homography, SSIM, registry, figures, or artifact storage (Person E), though B defines the U4 analysis contract and consumes their locked outputs.

## MVP scope

Analyze the 66-trajectory MVP matrix supplied by Person C:

- 48 core Regime A trajectories: 6 layouts x 2 speeds `{1, 2}` x 2 noise extremes `{0.02, 0.2}` x 2 durations `{0.25, 1.0}` context.
- 6 no-wall visible trajectories for the positive-control probe.
- 6 occluder-only/no-sheep trajectories for the negative control.
- 6 context-sentinel trajectories at `1.5 x` context with `q=0.05`.

Defer Regime B particle filtering, full paper-scale sampling, broad token localization, model-size robustness, and confirmatory U4 significance until after the MVP checkpoint. Week 1 needs a valid Regime A analysis and working U4 plumbing.

## Non-negotiable analysis contract

### Targets and units

Freeze these fields before inspecting live results:

- `mu_oracle_blocks`: oracle wall-parallel posterior mean in blocks.
- `var_oracle_blocks2`: oracle posterior variance in blocks squared.
- `sigma_oracle_blocks`: square root of posterior variance in blocks.
- `log_sigma_oracle`: dimensionless `ln(sigma_oracle_blocks / 1 block)` for hidden rows with positive spread.
- `tau`: canonical schema v1.0 elapsed hidden time in seconds.
- `x_true_blocks`: authoritative hidden position, scoring-only.
- `visibility`, `v`, `q`, `duration`, `layout_id`, and `trajectory_id`; `v` is in blocks/s, `q` is in blocks squared/s, and `duration` is in seconds.

At the locked 20 Hz rate, use `dt=0.05 s`. The primary Regime A information set contains only the last visible authoritative position, known scripted `v` and `q`, elapsed hidden ticks, and visibility. Hidden truth may be used to score predictions but must never enter the oracle or an occlusion baseline.

### Primary Regime A oracle

Implement both calculations independently in float64:

1. Scalar filter: `x_(k+1) = x_k + v*dt + eta_k`, with `eta_k ~ Normal(0, q*dt)`, exact visible observations (`R=0`), and no hidden measurement update.
2. Closed form: `mu(tau) = x_last + v*tau` and `variance(tau) = P_last + q*tau`, with `P_last=0` for the primary authoritative-state oracle.

On reveal, reset/correct from the authoritative visible state. Do not estimate `v` or `q` in the primary oracle. Any visible-history estimate is a separately labeled sensitivity or baseline.

### Identity and leakage rules

- Join on exact `trajectory_id` and `model_frame_idx`, backed by `(episode_id, server_tick, render_frame_idx, action_idx)`.
- Require one target per frame key and require every activation layer/site row to join exactly one target; save the full cardinality audit and quarantine mismatches instead of repairing core rows.
- Keep every layout entirely within one of five grouped folds.
- Fit scalers, preprocessing, hyperparameters, layer choices, and directions using training/validation data only.
- Never let test layouts choose preprocessing, ridge alpha, layer, MLP eligibility, intervention direction, or dose.
- Report only out-of-fold or truly held-out predictions.
- Resample layouts/trajectories, never neighboring frames as independent observations.

## Critical path

`schema/config -> exact oracle -> activation/target join -> visible positive control -> frozen per-layer harness -> U1/U2/U3 -> U4 direction and doses -> result classification -> checkpoint handoff`

Downstream work must stop at the first invalid gate. A failed runtime, join, oracle, positive control, or reproducibility gate is a pipeline failure, not a negative scientific finding.

Schedule note: this roadmap was created on Tuesday, July 21, 2026 (the source plan's Day 2). The checkout contained no Person B implementation, so the Day 0/Day 1 schema, fixture, and oracle outputs are immediate catch-up gates rather than assumed-complete work.

## Day-by-day execution plan

### Immediate catch-up: Day 0 and Day 1 artifacts

Complete these before interpreting any real activation results:

- Freeze target names, units, sources, exclusions, and allowed uses.
- Create `configs/analysis/core.yaml` with five grouped folds, ridge alpha grid `{0.1, 1, 10, 100}`, MLP shape `256 -> 128 -> 1`, seeds, resampling counts, coverage levels `{0.50, 0.80, 0.95}`, and U1-U4 output definitions.
- Create synthetic state logs and expected oracle targets.
- Implement independent scalar-filter and closed-form Regime A oracles.
- Test at least 100 seeded parameter combinations; require mean and variance agreement within `1e-6` under matching assumptions.
- Test invariants: finite positive hidden variance, larger `q` gives larger variance at fixed `tau`, hidden variance never decreases before reveal, and reveal reduces uncertainty.
- Produce one readable truth/last-seen/mean/`+/-1 sigma`/`+/-2 sigma` trajectory plot.

Exit evidence: analysis schema/config v0.1, synthetic fixture, grouped-resampling plan, two oracle implementations, unit tests, and oracle validation plot.

### Day 2: First real trajectory to a valid probe

- Consume Person A's indexed activations and Person C's pilot manifest/state logs.
- Join activations to targets using exact identities and compare source ticks/timestamps.
- Remove pre-first-seen frames only through named, logged filters.
- Freeze five layout-grouped folds and persist them.
- Fit fold-specific training-only scalers.
- Run a ridge visible-position positive-control probe with nested/training-only alpha selection.
- Save out-of-fold predictions, `R^2`, MAE, alpha, coefficients, intercept, sample/layout counts, folds, seed, and join audit.

Exit evidence: complete frame-to-layer/site join audit, persistent fold assignments, and no-wall visible positive-control result. Do not interpret hidden-state probe failures if the visible control fails.

### Day 3: Freeze the U1-U3 harness

- Freeze accepted-row inputs, folds, scalers, exclusions, alpha grid, seeds, coverage levels, and output schemas.
- Fit separate ridge probes for posterior mean and `log_sigma` at every decoder layer.
- Save out-of-fold predictions and complete fit metadata for every layer/target.
- Predeclare the three ridge-best layers eligible for the MLP comparison without using held-out U4 events.
- Implement grouped permutations, hierarchical bootstrap, partial correlation controlling `tau`, interval coverage/ECE, z diagnostics, hidden-time growth, and reveal snapback.
- Re-run row-cardinality and timestamp audits whenever the accepted manifest changes.

Exit evidence: frozen analysis config/folds, runnable per-layer pipeline, U1-U3 commands, result templates, and initial live outputs.

### Day 4: Run preliminary U1-U3

U1 - posterior mean:

- Fit ridge at every layer with train-only scaling and alpha selection.
- Report overall and duration-binned `R^2` and MAE.
- Compare against last-seen, explicit-feature, raw-pixel, grouped-shuffle, visible, and no-object outputs supplied under the shared fold/row contract.
- Run at least 999 grouped permutations for the MVP `p<0.01` criterion.
- Prefer a contiguous useful layer band over a post-hoc isolated maximum.
- At the three predeclared layers, report `Delta = R^2(MLP) - R^2(ridge)` as a nonlinearity/measurement diagnostic.

U2 - calibrated spread:

- Reconstruct `sigma_hat = exp(log_sigma_hat)` before coverage or z calculations.
- Preserve and count nonfinite or near-zero failures; never silently clip, take absolute values, or drop them.
- Use a fixed-seed hierarchical bootstrap: layouts first, then whole trajectories; 1,000 resamples for the MVP.
- Evaluate 50%, 80%, and 95% interval coverage, nominal-empirical gaps, ECE, bin counts, and sparse cells.
- Compute partial correlation between decoded and oracle spread controlling `tau`.
- Compute z diagnostics and `+/-1.96` coverage.
- At fixed `tau`, test separation by `q`; compare with time-only and fair visible-history-`q` baselines.

U3 - uncertainty dynamics:

- Estimate hidden-time spread growth using trajectory/grouped units.
- Compare decoded and oracle slopes and report their ratio with uncertainty.
- Align reveal events at zero and compare pre/post spread with a paired trajectory-level bootstrap/test.
- Plot the available `-1 s` to `+1 s` window around reveal.
- Keep absence-as-evidence analysis out of the Regime A MVP unless the wall-shadow assumption is violated.

Exit evidence: per-layer U1/U2 tables and curves, calibration outputs, z diagnostics, time-control and fixed-`q` results, U3 growth/reveal plots, baselines, seeds, counts, and CIs.

### Day 5: Derive the U4 mean direction and doses

- Choose the layer and timestep from predeclared validation evidence, never held-out U4 outcomes.
- Convert the standardized ridge coefficient to raw activation coordinates: `w_raw = w_z / scale` elementwise.
- Numerically verify that raw-space predictions match the fitted standardized pipeline.
- Fit and raw-convert an elapsed-time direction at the same layer.
- Normalize both directions, subtract the mean direction's projection onto time, and renormalize.
- Record pre/post angles and reject a near-zero residual direction.
- Calculate decoded blocks per unit alpha and map intended shifts to signed doses.
- Enforce the `0.25 x` typical-activation-norm cap and record every reduced dose.
- Hand Person A and Person E the selected layer, timestep, direction, alpha table, cap, held-out event list, and analysis specification.

Exit evidence: versioned raw-space direction, scaler/fit metadata, prediction-equality test, time-projection audit, alpha-to-block table, layer/timestep rationale, and held-out event manifest.

### Day 6: Reproduce and classify

- Confirm that all metrics use the clean run, current accepted manifest, frozen folds, and locked configs.
- State engineering-gate status before U1-U4 interpretation.
- Classify the result as one of: calibrated belief; mean-only/state-not-calibrated; represented-but-not-used; context-bound memory failure; nonlinear measurement failure; or invalid pipeline.
- Write claim-safe sentences that include the metric, CI, sample unit, control comparison, and limitation.
- Produce a green/yellow/red checkpoint memo with the smallest useful Phase 2 diagnostics and explicit cuts.

Exit evidence: reproducible metric bundle, outcome classification, claim boundaries, alternative-results ladder, and checkpoint memo.

### Day 7: Demonstrate and hand off

Person B presents:

- Independent oracle validation and the readable trajectory plot.
- U1 layer results and controls.
- U2 calibration, time-control, and fixed-`q` evidence.
- U3 growth and reveal-snapback evidence.
- Claim-safe result classification.
- With Persons A and E: U4 direction, exact injection contract, signed pilot/control outputs, persistence, displacement, and SSIM.

After the checkpoint, Person B and Person A jointly approve any change to scientific logic, schemas, interfaces, accepted samples, metrics, or claims. Preserve the accepted code/config/artifact state as `mvp-2026-07-26` with the matching external artifact hashes.

## Proposed repository backlog

Create these in small, reviewable commits:

1. Analysis contract and fixtures
   - `configs/analysis/core.yaml`
   - `src/mineocclude/oracle/schema.py`
   - `tests/fixtures/regime_a_synthetic.jsonl`
2. Exact oracle
   - `src/mineocclude/oracle/primary_scalar_kalman.py`
   - `src/mineocclude/oracle/closed_form.py`
   - `tests/oracle/test_regime_a_oracle.py`
3. Join, folds, and positive control
   - `src/mineocclude/probes/join.py`
   - `src/mineocclude/probes/splits.py`
   - `src/mineocclude/probes/ridge.py`
   - `tests/probes/test_join_and_splits.py`
4. U1-U3 metrics
   - `src/mineocclude/metrics/u1_mean.py`
   - `src/mineocclude/metrics/u2_calibration.py`
   - `src/mineocclude/metrics/u3_dynamics.py`
   - `src/mineocclude/metrics/resampling.py`
5. U4 analysis design
   - `src/mineocclude/intervention/directions.py`
   - `src/mineocclude/intervention/doses.py`
   - `tests/intervention/test_raw_space_direction.py`
6. Reproducible entry points and outputs
   - `scripts/build_oracle_targets.py`
   - `scripts/run_probe_analysis.py`
   - `scripts/derive_u4_direction.py`
   - `results/mvp/` for locked machine-readable outputs only
   - `docs/decisions/` for dated deviations, corrections, and approvals

Do not commit checkpoints, raw videos, full activation tensors, rollout clips, credentials, or large caches.

## MVP acceptance gates

- Oracle: scalar filter and closed form agree within `1e-6` across at least 100 seeded combinations; units and invariants pass; hidden truth is scoring-only.
- Alignment: 100% of accepted activation rows join exactly one target row; mismatches are quarantined and documented.
- Positive/negative controls: no-wall visible ridge reaches held-out `R^2 >= 0.50` with bootstrap CI above zero; grouped shuffled labels center near zero; occluder-only data do not decode condition-specific sheep position.
- U1 green signal: a contiguous band of at least two layers has held-out `R^2 > 0`, beats last-seen, and beats grouped shuffle at `p<0.01`.
- U2 green signal: partial correlation of decoded/oracle spread controlling `tau` has a hierarchical 95% bootstrap CI above zero; average absolute 50/80/95% coverage error is at most `0.10` and improves on time-only and visible-history-`q` baselines.
- U3 green signal: positive hidden-time growth, decoded/oracle slope ratio in `[0.5, 2.0]`, and a reveal decrease with CI below zero and median spread reduction of at least 25%.
- U4 plumbing: positive and negative doses yield opposite-signed median shifts, random directions do not share the pattern, and pushed-vs-unpushed SSIM remains within natural unpushed variation. Confirmatory significance is not required for Week 1.
- Reproducibility: a clean environment regenerates metrics from stored config/manifests and records code, checkpoint, data, config, preprocessing hashes, seeds, folds, exclusions, and package lock.

The numeric thresholds above are MVP planning gates, not universal scientific standards. Report them as predeclared project criteria rather than general truths.

## Decision rule

- GREEN: engineering gates pass; U1 and U2 are green; U3 is directionally correct. Scale Regime A and continue selected mechanistic/U4 work.
- YELLOW: engineering and controls pass, but a U1-U4 criterion fails cleanly. Report the corresponding valid alternative result and cut breadth before validity.
- RED: runtime, alignment, oracle, positive control, detector, or reproduction fails. Do not interpret negative science; repair the pipeline and repeat the gates.

## Definition of done for Person B

- [ ] Every target has a stable name, unit, source, and permitted use.
- [ ] Independent Regime A oracle implementations agree and pass invariants.
- [ ] Accepted rows all have traceable targets; hidden truth never enters the oracle.
- [ ] Folds are layout-grouped and frozen; preprocessing and selection are train-only.
- [ ] All reported probe predictions are out-of-fold or held out with complete metadata.
- [ ] U1 includes grouped shuffle, last-seen, controls, and MLP-minus-linear diagnostic.
- [ ] U2 includes time control, positive-spread audit, coverage/ECE, z diagnostics, fixed-time `q`, and grouped bootstrap.
- [ ] U3 includes grouped growth and reveal-snapback analysis.
- [ ] U4 direction reproduces the fitted probe in raw space, removes elapsed-time overlap, maps alpha to blocks, respects the norm cap, and records selection provenance.
- [ ] Every conclusion maps explicitly to U1, U2, U3, U4, or a diagnostic.
- [ ] The checkpoint memo distinguishes a scientific negative from an invalid pipeline.
- [ ] Every displayed number matches a locked machine-readable result.
