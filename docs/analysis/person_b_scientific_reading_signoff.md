# Person B Scientific Evidence Reading and Sign-off

Status: `COMPLETED_CURRENT_REVIEW`

Review date: 2026-07-23

Reviewer role: Person B

This record closes Week 1 Step B0.4 for the current implementation. It records
a fresh review of the controlling evidence; it does not reconstruct or claim
historical reading that was not previously documented.

## Controlling sources

1. `AAKA-Proposal-Final.pdf`, especially pages 4-9: U1-U4 criteria, primary
   model and regimes, grouped probes, calibration, interventions, controls,
   evaluation, alternative results, and limitations.
2. `MineOcclude_Research_Execution_Roadmap_2026_Mentor_Aligned (1).docx`:
   "What the four scientific tests mean", the MVP sprint, the locked
   66-trajectory matrix, the full 372-trajectory plan, the Person B role
   reference, MVP acceptance gates, alternative-results ladder, and risk map.
3. Frozen repository contracts and `configs/analysis/core.yaml`, which encode
   the approved Phase 0/1 interface and analysis choices.

Scientific conflicts are resolved in favor of the final proposal. Roadmap
numbers explicitly labeled as planning gates remain planning thresholds rather
than universal scientific truths.

## Requirement trace

| Requirement | Authority | Implementation control | Verification |
|---|---|---|---|
| U1 predicts the oracle posterior mean on held-out layouts and beats shuffled labels and last-seen | Proposal pp. 4, 7; roadmap U1 and Person B B3 | `probes/splits.py`, `probes/ridge.py`, production probe runner, `metrics/u1_mean.py` | Group-disjoint OOF tests, positive-control gate, grouped permutation, matched-row baseline comparison |
| U1 alone is not calibrated belief | Roadmap "What the four scientific tests mean"; proposal alternative results | Result labels and claim-boundary records | Result bundle must separate U1 from U2/U3 and prohibit calibrated-belief wording from U1 alone |
| U2 must track oracle spread after controlling elapsed hidden time | Proposal pp. 4, 6-7; roadmap U2/B4 | `metrics/u2_calibration.py`, `configs/analysis/core.yaml` | Raw and partial association, tau-squared sensitivity, fixed-time q comparisons |
| U2 calibration includes 50/80/95% coverage, reliability/ECE, and z diagnostics | Proposal pp. 4, 7; roadmap B4 | `metrics/u2_calibration.py`, frozen coverage levels | Known-answer calibration tests, invalid/near-zero counts, denominators on every coverage result |
| U3 uses grouped hidden growth and paired reveal events | Proposal pp. 4, 7; roadmap U3/B4 | `metrics/u3_dynamics.py` | Trajectory/event-level tests and hierarchical intervals; frames are not independent inferential units |
| Primary Regime A uses known v and q; hidden truth is scoring-only | Proposal p. 5; roadmap B2 | `oracle/`, target contract, ordered filters | Recursive/closed-form agreement, information-flow tests, signed coordinate contract |
| Five outer folds are grouped by layout; preprocessing and selection are training-only | Proposal pp. 5-7; roadmap B1/B3 | `probes/splits.py`, `probes/ridge.py`, core config | Stored membership, disjointness, train-only scaler, outer-test label isolation |
| Ridge alpha is selected from {0.1, 1, 10, 100}; MLP is 256->128->1 at three preselected layers | Roadmap Person B B1/B3 and MVP instructions | Core config, `probes/ridge.py`, `probes/mlp.py` | Grouped inner selection and fixed-architecture tests |
| Positive visible/no-wall control must pass before hidden-state negatives are interpreted | Proposal pp. 5, 7, 9; roadmap pilot and engineering gates | Production positive-control runner and result gate | All-layer visible result versus grouped shuffle; failure marks hidden results uninterpretable |
| U4 confirmatory scope is causal use of the posterior mean, not spread | Proposal pp. 4, 6; roadmap U4 | `intervention/`, B-to-A request, U4 result labels | Raw prediction equality, time projection, held-out provenance, specificity and coherence controls |
| U4 direction is raw-space, time-orthogonal, dose-mapped, and capped at 0.25 of typical activation norm | Proposal p. 6; roadmap Person B B5 | `intervention/directions.py`, `doses.py`, `producer.py` | Equality tolerance, residual/angle audit, sign tests, requested/applied dose and cap metadata |
| Week 1 U4 is a five-event, five-dose, two-seed plumbing pilot plus random controls | Mentor-aligned roadmap locked U4 MVP pilot | MVP intervention request and rollout manifests | Explicit plumbing-only scope unless held-out conditions support a stronger claim |
| Final U4 uses a separate 3-fit/1-validation/2-test layout partition | Mentor-aligned roadmap full-study plan and B5 | `probes/splits.py` U4 partition manifest | Outcome-independent stored partition and held-out selection audit |
| MVP and final datasets remain distinct | Mentor-aligned roadmap 66-trajectory and 372-trajectory tables | Experiment manifests and run identity | Accepted counts and shortfalls are explicit; rollout clips are not counted as clean trajectories |
| Alternative outcomes do not trigger new splits or favorable layer searches | Proposal p. 9; roadmap alternative-results ladder and risk map | Decision log, correction policy, result classification | Mean-only, represented-not-used, memory failure, measurement failure, or invalid pipeline labels follow frozen gates |
| Claim-bearing values are machine-generated and provenance-bound | Mentor-aligned roadmap code/data/results rules | Artifact manifests, registry, correction log | Code/config/input hashes, seeds, folds, counts, lifecycle, and supersession are mandatory |

## Locked interpretation boundaries

- A failed oracle, alignment, hook, positive-control, detector, or
  reproducibility gate is an invalid pipeline, not a negative model result.
- A linear-probe failure with a valid positive control remains compatible with
  hidden-state absence, context-bound memory loss, nonlinearity, or measurement
  failure; the MLP diagnostic distinguishes but does not prove those causes.
- Raw spread-time association without surviving time control is clock
  substitution, not calibrated uncertainty.
- U1-U3 passing while a valid, specific U4 fails supports at most a
  represented-but-not-used interpretation.
- U4 without persistence, signed reversal, specificity, localization accuracy,
  and coherence cannot support a causal-use claim.

## Open implementation and evidence gates

- Real C accepted trajectories and coordinate-frame sign-off are still required
  for claim-bearing targets.
- Real A activation chunks are still required for positive-control and
  per-layer execution.
- D baseline rows and E registry/measurement receipts remain required for the
  Phase 6 handoff rehearsal.
- The repository must pin or otherwise record the numerical runtime before
  exact floating-point evidence hashes can be treated as cross-platform
  reproducible.

Sign-off decision: `APPROVED_TO_IMPLEMENT_WITH_FROZEN_RULES`.

Any result-changing deviation from this trace requires a dated decision,
appropriate approval, a versioned config/schema change when applicable, and a
new run identity.
