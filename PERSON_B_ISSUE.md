# Person B: Scientific Methods Roadmap

## Objective

Own MineOcclude's oracle, probes, statistical analysis, U1-U4 interpretation, and claim validity from MVP setup through final scientific sign-off.

Full details: [`PERSON_B_MVP_ROADMAP.md`](./PERSON_B_MVP_ROADMAP.md)

## Phase 0 evidence and current checkpoint

This file is the Person B command-center authority. The current integrated
checkpoint is `integration/mvp` at
`80d41c5ca0e341263a7b0c683fae4b51be376c55`. Git and current files establish
the repository state below. They do not prove a person's historical branch
inspection, private access, hardware capacity, or reading history; those items
are explicitly `UNVERIFIED` rather than reconstructed as facts.

### Responsibility inventory

| Area | Authoritative location | Current state |
|---|---|---|
| Oracle and target production | `src/mineocclude/oracle/` | AVAILABLE; synthetic Phase 1 evidence only |
| Filtering/legal row selection | `src/mineocclude/analysis/filters.py` and frozen consumer contracts | AVAILABLE |
| Grouped splits | `src/mineocclude/probes/splits.py` | AVAILABLE |
| Ridge and MLP | `src/mineocclude/probes/ridge.py`, `src/mineocclude/probes/mlp.py` | AVAILABLE; real fits not claimed |
| Join/vector bridge | `src/mineocclude/probes/join.py`, `src/mineocclude/probes/bridge.py` | AVAILABLE |
| U1/U2/U3 metrics | `src/mineocclude/metrics/u1_mean.py`, `src/mineocclude/metrics/u2_calibration.py`, `src/mineocclude/metrics/u3_dynamics.py` | AVAILABLE and synthetically composed |
| Calibration | `src/mineocclude/metrics/u2_calibration.py` | AVAILABLE |
| Bootstrap/permutation | `src/mineocclude/metrics/resampling.py` | AVAILABLE |
| Directions/doses/request production | `src/mineocclude/intervention/directions.py`, `src/mineocclude/intervention/doses.py`, `src/mineocclude/intervention/producer.py` | AVAILABLE |
| Artifacts/results/config | `src/mineocclude/analysis/manifests.py`, `src/mineocclude/analysis/outputs.py`, `configs/analysis/core.yaml` | AVAILABLE |
| Full Phase 1 synthetic analysis chain | `src/mineocclude/analysis/synthetic_chain.py` | CURRENT CPU-only contract evidence |

These locations consume A/C/D/E authorities; they do not transfer ownership
of activation extraction, capture truth, baseline logic, or measurement.

### Upstream dependencies and resources

| Dependency/resource | Status | Evidence or limitation | Owner | Needed before |
|---|---|---|---|---|
| A activation/intervention/rollout contracts | AVAILABLE | Frozen schema `1.0` and synthetic fixtures | A | Real activation analysis needs real A artifacts |
| C capture and C-to-B projection | AVAILABLE synthetically | C validator and consumer-side adapter are tested; real capture absent | C source, B projection | Real oracle targets |
| D baseline handoff | AVAILABLE synthetically | Current D exporter/harness and B intake are connected | D | Real comparisons need accepted D output |
| E measurement handoff | AVAILABLE synthetically | Hash-bound E evidence and B intake are connected | E | Real U4 needs accepted A/E output |
| Local CPU execution | AVAILABLE | Synthetic repository suite | Project environment | Phase 1 proof |
| GPU/AWS/account access | UNVERIFIED | No repository permission or capacity record | Project owner | Real/scale execution |
| Durable storage/quota | UNVERIFIED | Hash/URI contracts exist; deployment capacity is not evidenced | Project owner/E | Claim-bearing artifacts |
| Phase 0/1 schema, analysis-config, and interface approval | COMPLETE at `80d41c5ca0e341263a7b0c683fae4b51be376c55` | Coordinator-confirmed five-role signoff in `docs/contracts/schema_v1_0_signed_record.md` | A/B/C/D/E role owners | New approval required for a result-changing revision |
| Runtime and final scientific-result approval | PENDING | The Phase 0/1 signoff does not approve real execution or results | Applicable later-phase owners | Applicable runtime or result gate |

### Controlling requirements trace

| Requirement | Repository evidence | Status |
|---|---|---|
| Targets, units, legal/scoring-only information | `docs/contracts/person_b_oracle_target_v0_1.md`, `configs/analysis/core.yaml` | TECHNICALLY VERIFIED |
| Identity and deterministic filters | Frozen schema `1.0`, `analysis/filters.py` | TECHNICALLY VERIFIED |
| Layout-grouped folds and selection hierarchy | `probes/splits.py`, analysis config | TECHNICALLY VERIFIED |
| Metrics, calibration, bootstrap, permutation | `analysis/metrics.py`, `analysis/calibration.py`, `analysis/resampling.py` | TECHNICALLY VERIFIED |
| A/B/C/D/E intake expectations | `docs/contracts/person_b_analysis_inputs_v0_1.md` and current validators | TECHNICALLY VERIFIED |
| Synthetic state-to-result/request proof | `analysis/synthetic_chain.py` and saved fixture/tests | TECHNICALLY VERIFIED, NON-SCIENTIFIC |
| Historical roadmap reading | No reliable repository evidence | UNVERIFIED |
| B1.9 Phase 0/1 human approval | `docs/contracts/schema_v1_0_signed_record.md` at `80d41c5ca0e341263a7b0c683fae4b51be376c55` | COMPLETE FOR THAT CHECKPOINT |

### Dependency and decision register

| Issue | Safe current rule | Owner / approver | Resolve before |
|---|---|---|---|
| Real coordinate frame and capture identity | Reject unsigned/mismatched projection | B/C | First real C-to-B handoff |
| No-object capture use | Not oracle-target eligible; preserve source for D/E controls | B/C/D/E | First such real control |
| Real activation/fold/target manifests | Validate exact hashes and identity; no placeholder promotion | A/B | Real probe fitting |
| U4 measurement/statistical method approval | E measures; B owns inference and claims | B/E | Real U4 analysis |
| Compute/access/storage | Remain `UNVERIFIED`; do not infer availability | Project owner | Scale plan |
| Formal Phase 0/1 interface approval | Complete only for `80d41c5ca0e341263a7b0c683fae4b51be376c55`; do not extend it to real execution or results | A/B/C/D/E role owners; coordinator confirmation | Re-review before a result-changing contract/config revision |

### Command center

| Work | State | Output/pass condition |
|---|---|---|
| Repository and ownership inventory | CURRENT/RECORDED | This file names one authoritative location per B responsibility |
| Phase 1 contracts and synthetic chain | COMPLETED TECHNICALLY | Deterministic synthetic validators, folds, OOF fits, U1/U2/U3, direction/request, result bundle pass |
| Cross-role synthetic validation | CURRENT | Shared runner validates C/A/B/D/E boundaries |
| B1.9 schema/config/interface signoff | COMPLETE for `80d41c5ca0e341263a7b0c683fae4b51be376c55` | Central signoff record; runtime and result approvals remain pending |
| Real scientific execution | NEXT LATER PHASE | Accepted real upstream artifacts and runtime/access gates exist |

## Current blockers

- [ ] Receive a completed real activation handoff from Person A; the frozen
  contract and compatibility evidence are already merged.
- [ ] Receive accepted real state/capture artifacts from Person C; the current
  C schema and synthetic C-to-B adapter already exist.
- [ ] Receive real Person D baseline artifacts; D's current contract and
  synthetic handoff already validate against B.
- [ ] Receive real Person E measurements; E's registry/evidence contract and
  synthetic E-to-B handoff already validate against B.

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
  - [x] Add and synthetically exercise C/D/E intake validators; Phase 0/1
    owner signoff is recorded for the approved checkpoint, while real artifacts
    remain pending.
  - [x] Compose state through oracle, grouped OOF ridge, U1/U2/U3, directions,
    intervention request, and sealed result evidence in one CPU-only chain.
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
