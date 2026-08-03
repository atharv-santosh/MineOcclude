# Person B real-pilot runbook through Step 6.6

Status: Person C's real capture/coordinate intake is complete. A-bound state
inputs, final oracle targets, joins, controls, and probes remain blocked on a
completed matching Person A activation handoff and authoritative A
model/preprocess hashes.

## Completed C intake evidence

- Source: `role/person-c-data@260784ea4d0f130b5ce96a383008e5a4574f3cc2`.
- Imported: ten target-present Regime A core packages across six layouts, five
  200/200-visible no-wall controls across five layouts, and one no-sheep
  control.
- Every literal capture SHA-256 matches C's checksum sidecar and all 16
  packages pass C's frozen `0.1` validator.
- B verified 15 unique signed projections: positive X for layouts
  00/02/03/04 and positive Z for layouts 01/05. The no-sheep control has no
  identifiable target axis and is explicitly `no_object_not_oracle_eligible`.
- The C-only real oracle math audit covers 15 applicable packages, has zero
  recursive/closed-form disagreement, no invariant failures, and 187 passing
  fixed-time q comparisons. It does not create or promote an A-bound target
  artifact.
- Person B accepts C's `person-c-event-stability-v0.1` two-consecutive-frame
  rule for future C-produced occlusion/reveal event IDs. This does not alter
  the preserved raw visibility stream; Person E's acknowledgement remains a
  Step 6.6 receipt.
- Sealed intake:
  `data/person_b/phase6_c_intake/capture_intake_report.json`, artifact hash
  `1d976a5543ede07b43b0be3c6eb053afbb8cbcc823dc63d6fd5fd931988ce636`.
- Frozen source selection:
  `data/person_b/phase6_c_intake/condition_selection_source.json`, containing
  1,456 hidden core rows and 1,000 visible no-wall rows.
- Frozen real layout-fold plan:
  `data/person_b/phase6_c_intake/layout_fold_plan.json`, artifact hash
  `ca265b64935880aede8c3bb8b6060cdda17c23932e5e98878a3fcf8ee5341f01`.
  It uses no A artifacts or outcome fields and assigns layouts as follows:
  `03->0`, `00->1`, `01->2`, `04->3`, and `02/05->4`. Each hidden and
  visible-control scope covers all five folds.

## Immutable execution order

1. Reproduce C intake with `scripts/intake_person_c_pilot.py`; do not use C's
   draft state outputs or placeholder A hashes.
2. Reproduce the pre-A plan with
   `scripts/build_person_b_layout_fold_plan.py`. Its selection-source and
   intake hashes must match Step 1 exactly.
3. After A supplies authoritative hashes, build B state input from each
   accepted capture package and its matching signed coordinate frame with
   `scripts/build_person_b_state_input.py`.
4. Build oracle targets with `scripts/build_oracle_targets.py`. Both writers
   refuse to overwrite an existing artifact.
5. Use the frozen `person-b-condition-selection-source-v0.1` JSON produced by
   Step 1. Result, prediction, and outcome fields are rejected.
6. Run `visible_no_wall_control` with `scripts/run_person_b_pilot.py` and its
   required `--layout-fold-plan`. The A-bound frame manifest is rejected unless
   its layout assignments match the pre-A plan exactly.
7. Review its sealed scope bundle. Record `pass` or `stop_for_diagnosis` with
   `scripts/record_person_b_control_gate.py`. The code does not invent an
   unfrozen numeric threshold or auto-approve this scientific gate.
8. Only after a passing gate, run `hidden_mean` and `hidden_spread`.
9. Give D the exact hidden-mean row/fold request produced by
   `scripts/build_person_b_d_request.py`.
10. Package the resulting B artifacts into E-validatable registry records with
   `scripts/build_person_b_e_registration.py`. Include the sealed oracle
   target, joined frame table, matrix, scaler, fit, prediction, metric, and
   failure/control artifacts. Supply E's existing upstream hash-to-artifact-ID
   mapping with `--external-artifact-map` when available.
11. Build the A/D/E outgoing-packet report with
   `scripts/build_person_b_phase6_handoff_report.py`. It deliberately leaves
   every acknowledgement receipt null until the corresponding role responds.

## Frozen selection scopes

| Scope | Required rows | Target |
|---|---|---|
| `visible_no_wall_control` | Source manifest declares `condition_role = no_wall_visible_control`; row is visible | `x_true_blocks` |
| `hidden_mean` | Occluded, post-first-seen accepted rows | `mu_oracle_blocks` |
| `hidden_spread` | Occluded rows with finite positive-spread target | `log_sigma_oracle` |

The source selection file's literal SHA-256 is recorded in the sealed
selection artifact. Unknown, duplicate, stale-layout, or target-ineligible
rows fail closed.

## Interpretation boundary

- Fewer than five layouts yields an intake receipt labeled
  `plumbing_only_insufficient_layouts`; grouped OOF evidence is not emitted.
- The hidden core source spans six layouts and the no-wall control now spans
  five layouts. The visible-control scope is eligible for frozen grouped OOF
  execution as soon as matching A activations arrive.
- Real grouped permutations always use the count and seed in
  `configs/analysis/core.yaml`. Reduced counts are accepted only for evidence
  already marked synthetic and forbidden for scientific use.
- Every outer-fold scaler and ridge fit is saved separately, followed by the
  OOF prediction, metric, permutation, and scope-bundle artifacts.
- Fold assignment is outcome-independent: C rows freeze layout membership
  before A arrives. The later frame manifest embeds the plan hash, and the
  pilot receipt embeds both the plan and bound frame-manifest hashes.
- The D packet is a request, not a D receipt. The E packet is ready for E
  validation/append, not proof that E registered it.
- Hidden probe execution does not authorize interpretation until the exact
  visible-control bundle has a passing sealed gate.

## Still requires upstream artifacts or action

- A: completed matching activation handoff and literal activation chunks.
- A: authoritative `model_hash` and `preprocess_hash`; C's draft state outputs
  explicitly used placeholders and are not accepted as B evidence.
- D: actual time-only, last-seen, and shuffled OOF response artifacts.
- E: registry validation/append and a returned receipt.
- E: acknowledgement of C's two-frame event-stability rule before
  event-derived evidence is promoted.
- A/B/C/D/E owners: cross-role acknowledgement that the exact pilot identities,
  units, hashes, and run relationships were consumed.
