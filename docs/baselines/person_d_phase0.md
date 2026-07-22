# Person D Phase 0 Status, Ownership, and Dependencies

Record date: 2026-07-22

Current branch: `repair/person-d-phase1`

Base: `integration/mvp` at `d38835c` (`Integrate finalized Phase 0-1 for
Roles A B and C`). Person D's files are layered onto that integration base;
Person D does not vendor or own copies of A-, B-, or C-owned authorities.

Formal Person A/Person B human signoff of the D handoff is **pending and
unverified**. Repository contract compatibility and passing synthetic tests
are engineering evidence, not a substitute for human approval.

## Phase 0.1 -- Evidence-backed milestone status

| Milestone | Status | Evidence and boundary |
|---|---|---|
| Branch/base and ownership inventory | READY | This record; `docs/baselines/person_d_phase1.md`; `git` base `d38835c` verified on 2026-07-22. |
| D-to-B baseline document compatibility | READY | `src/mineocclude/baselines/export.py`; `tests/baselines/test_export.py`; current B validator at `src/mineocclude/contracts/analysis_inputs.py`. |
| Authoritative-fold consumption | READY for synthetic Phase 1 evidence | D validates and consumes B's sealed manifest without assigning folds. Evidence: `tests/fixtures/person_d/synthetic_b_fold_manifest.json` and `tests/baselines/test_export.py`. A real accepted-run fold manifest has not been produced. |
| D synthetic baseline/control checks | READY | `src/mineocclude/baselines/`; `tests/baselines/`; 67 tests passed on 2026-07-22. This is synthetic evidence only. |
| A/B compatibility handshake | TECHNICALLY VERIFIED / HUMAN APPROVAL PENDING | `docs/baselines/person_d_schema_v1_review.md` records the repository-side review. No D-specific human approval record from A and B exists. |
| Real-data baselines and scientific comparisons | BLOCKED / NOT STARTED | No real accepted rows, real fold manifest, real target table, or final experimental result is claimed here. |

## Phase 0.2 -- File scope and ownership

Person D owns:

- `src/mineocclude/baselines/`
- `tests/baselines/`
- `tests/fixtures/person_d/`
- `docs/baselines/person_d_phase0.md`
- `docs/baselines/person_d_phase1.md`
- `docs/decisions/person_d_phase1_decision_log.md`
- `PERSON_D_ISSUE.md`
- the repository-root `conftest.py` only as test import-path support, not as a
  scientific authority

Person D consumes but does not own:

- Person A: `src/mineocclude/contracts/identity.py`, activation/trajectory/
  rollout contracts, schema-v1.0 records, and preprocessing identity fields;
- Person B: `src/mineocclude/contracts/analysis_inputs.py`,
  `src/mineocclude/probes/splits.py`, `src/mineocclude/probes/ridge.py`,
  `src/mineocclude/metrics/`, `src/mineocclude/analysis/`,
  `src/mineocclude/intervention/directions.py`, and
  `configs/analysis/core.yaml`; and
- Person C: `src/mineocclude/data/`, `schemas/person_c/`, and
  `configs/scenes/` as the future accepted capture/layout source.

D imports those authoritative implementations directly from the integration
foundation. D must not copy, fork, silently edit, or weaken them. Changes to
another role's authority require that owner to review and make the change in
their owned location. The current D repair changes only the D-owned paths
listed above.

## Phase 0.3 -- Dependency register

`READY` means the authoritative contract/API needed by D exists now.
`SAMPLE-ONLY` means contract and synthetic evidence exist but no real accepted
producer artifact exists. `BLOCKED` means D cannot safely exercise the
dependency even synthetically.

| Dependency | State | Current evidence and limitation |
|---|---|---|
| Accepted-manifest schema | READY | Universal schema `1.0`, accepted-manifest hashes, and exact `trajectory_id + model_frame_idx` identity are frozen in `src/mineocclude/contracts/identity.py`, A's contracts, and B's intake. No real accepted manifest is claimed. |
| Fold schema / sealed fold manifest | SAMPLE-ONLY | B owns `build_fold_manifest` and `validate_fold_manifest` in `src/mineocclude/probes/splits.py`. D consumes the saved synthetic artifact at `tests/fixtures/person_d/synthetic_b_fold_manifest.json`; a real accepted-run manifest remains pending. |
| Target schema | SAMPLE-ONLY | B owns target names, units, and oracle-target validation in `docs/contracts/person_b_oracle_target_v0_1.md`, `configs/analysis/core.yaml`, and `src/mineocclude/oracle/`. Only synthetic targets are available to D. |
| Preprocessed-frame identity | SAMPLE-ONLY | A schema `1.0` binds `trajectory_id + model_frame_idx` and `preprocess_hash`; synthetic activation/frame evidence exists. No real preprocessed-frame handoff for raw-pixel or random-weight baselines exists. |
| Metric API | READY | B owns `src/mineocclude/metrics/` and metric rules in `configs/analysis/core.yaml`. D's common synthetic harness calls `metrics.u1_mean.regression_metrics` directly; no final real-data metric is claimed. |
| U4 manifest schema | SAMPLE-ONLY | B's sealed U4 partition manifest and A's rollout/registry contracts exist with synthetic evidence. Real fitted directions, rollouts, E measurements, and D control-matrix audit inputs remain pending. |

## Phase 0.4 -- Decision and assumption register

| Issue | Current safe default | Owner / required approver | Resolve before |
|---|---|---|---|
| D-specific A/B schema-v1.0 handshake | Repository compatibility is technically verified in `person_d_schema_v1_review.md`; do not claim human approval. | Persons A and B approve; D records. | Any real D artifact is accepted for scientific comparison. |
| Additional D baseline families in B intake | Fail closed. The current B contract accepts only its declared family/target/feature allowlists. | Person B owns intake; Person D proposes producer fields. | Exporting any family not already accepted by B. |
| Real scientific fold membership | Use only a validated, saved B fold manifest; never reconstruct membership in D. Synthetic fixture remains non-scientific. | Person B produces/approves; Person D consumes. | Any real fitting or prediction. |
| Real accepted target rows | Use synthetic rows only and make no scientific claim. | Persons B and C for target/source compatibility; D consumes. | Any real baseline fit or comparison. |
| Preprocessed-frame handoff | Require A-owned explicit frame identity and preprocessing provenance; do not infer identity from filenames or order. | Person A approves producer fields; D consumes. | Raw-pixel or random-weight baseline on real data. |
| Metric invocation and result interpretation | Use B's current metric API; no D-local metric definition. | Person B approves metric use; D records outputs. | First real baseline evaluation. |
| U4 real control/rollout linkage | Keep control-matrix work synthetic/structural; do not infer missing rollout or measurement rows. | Persons A, B, and E own upstream artifacts; D audits. | Any real U4 control conclusion. |

No calendar deadline is invented where the roadmap supplies only a phase gate;
the `Resolve before` column is the binding deadline.
