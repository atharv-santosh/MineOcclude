# Person B real-pilot runbook through Step 6.6

Status: implementation-ready; execution remains blocked on accepted real
Person C state/capture evidence and matching completed Person A activations.

## Immutable execution order

1. Build B state input from C's accepted capture package and the signed B/C
   coordinate frame with `scripts/build_person_b_state_input.py`.
2. Build oracle targets with `scripts/build_oracle_targets.py`. Both writers
   refuse to overwrite an existing artifact.
3. Prepare an accepted
   `person-b-condition-selection-source-v0.1` JSON with
   `selection_policy = predeclared_before_probe_results`. Each accepted row
   contains `trajectory_id`, `model_frame_idx`, `layout_id`,
   `condition_role`, and an `analysis_scopes` list. Result, prediction, and
   outcome fields are rejected.
4. Run `visible_no_wall_control` with `scripts/run_person_b_pilot.py`.
5. Review its sealed scope bundle. Record `pass` or `stop_for_diagnosis` with
   `scripts/record_person_b_control_gate.py`. The code does not invent an
   unfrozen numeric threshold or auto-approve this scientific gate.
6. Only after a passing gate, run `hidden_mean` and `hidden_spread`.
7. Give D the exact hidden-mean row/fold request produced by
   `scripts/build_person_b_d_request.py`.
8. Package the resulting B artifacts into E-validatable registry records with
   `scripts/build_person_b_e_registration.py`. Include the sealed oracle
   target, joined frame table, matrix, scaler, fit, prediction, metric, and
   failure/control artifacts. Supply E's existing upstream hash-to-artifact-ID
   mapping with `--external-artifact-map` when available.
9. Build the A/D/E outgoing-packet report with
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
- Real grouped permutations always use the count and seed in
  `configs/analysis/core.yaml`. Reduced counts are accepted only for evidence
  already marked synthetic and forbidden for scientific use.
- Every outer-fold scaler and ridge fit is saved separately, followed by the
  OOF prediction, metric, permutation, and scope-bundle artifacts.
- The D packet is a request, not a D receipt. The E packet is ready for E
  validation/append, not proof that E registered it.
- Hidden probe execution does not authorize interpretation until the exact
  visible-control bundle has a passing sealed gate.

## Still requires upstream artifacts or action

- C: accepted real capture/state package, accepted condition manifest, and
  B/C-signed wall-parallel coordinate frame.
- A: completed matching activation handoff and literal activation chunks.
- D: actual time-only, last-seen, and shuffled OOF response artifacts.
- E: registry validation/append and a returned receipt.
- A/B/C/D/E owners: cross-role acknowledgement that the exact pilot identities,
  units, hashes, and run relationships were consumed.
