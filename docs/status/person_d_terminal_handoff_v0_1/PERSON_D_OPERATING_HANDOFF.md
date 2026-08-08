# Person D operating handoff (Step 8.4, frozen v0.1)

Status: **frozen**. Record date 2026-08-06. Branch `role/person-d-baselines`.

This is the document a second operator uses to run, verify, resume, and
extend Person D's baselines, controls, and U4 control matrix without
asking the original operator anything. It is deliberately explicit about
what has *not* been run, and why.

Nothing in this handoff creates the final MVP Git tag. Tagging is a
coordinated integration action and is out of Person D's scope.

---

## 1. Current upstream versions

Read at record date, from `git rev-parse` against remote refs. No branch
was merged and no role branch history was imported.

| Role | Branch | Commit |
|---|---|---|
| main | `main` | `15adc43674420ae35921847a953ebbee2135f142` |
| Person A | `role/person-a-model` | `ef98d184aaed8f03757add4ecac4a48968bb6fcc` |
| Person B (official) | `role/person-b-analysis` | `98f50761ecb99bc14ed5d1ebb67aedc8dcfd3327` |
| Person B (methods) | `role/person-b-methods` | `eec9396e6a93feaab3d5d298ac7cdc4cb54fdbd4` |
| Person C | `role/person-c-data` | `365e748addcb1e1926d7e2c5a382a92fa39ebc40` |
| Person E | `role/person-e-operations` | `5e2ef61a75fe4900dc7226dec7c1f6dcc1f39171` |

Person B is **not** terminally complete with respect to Person D's
inputs: neither B branch carries a fold or oracle-target manifest at the
accepted 66-cell MVP scale. See §7.

---

## 2. Required inputs

| Input | Owner | Schema / version | Status |
|---|---|---|---|
| Accepted MVP trajectory manifest (66 cells) | Person C | `configs/collection/mvp_matrix.csv` + `data/autonomous/pilot_production_ledger.json` | **AVAILABLE** — bound in Step 6.1, re-verified in `person_d_phase6_step6_1_mvp_identity_binding_v0_2/` |
| Fold manifest at 66-cell scope | Person B | production-handoff fold manifest | **MISSING** |
| Oracle targets at 66-cell scope | Person B | `production_oracle_target_manifest` | **MISSING** |
| Preprocessed frame manifest at 66-cell scope | Person A | `person-a-preprocessed-frame-manifest-v0.2` | **MISSING** |
| Family/target applicability contract | Person B | `person-b-step4-1-family-target-applicability-v0.1` | **AVAILABLE** but scoped to the earlier ten-pilot `ep94xx` set, not the 66-cell matrix |
| Fitted U4 direction + held-out events + dose table + target layer/timestep | Person B | `person-b-intervention-request-v1.0` | **MISSING** |
| U4 rollout measurement table | Person E | `person-b-u4-measurement-input-v0.1` | **MISSING** |
| Metric table over D's predictions | Person B | `person-b-step4-1-final-comparison-output-v0-1` | **MISSING** |

---

## 3. Environment

```
interpreter : C:\Users\lollo\MineOcclude-TestRunner\Scripts\python.exe
env         : PYTHONDONTWRITEBYTECODE=1
pytest      : -q -p no:cacheprovider
temp output : outside the repository
```

Do **not** upgrade scientific dependencies. `requirements.txt` is the
package lock referenced by the clean-workflow run record.

Host-memory detection is portable: POSIX `sysconf` on Linux/macOS, Win32
`GlobalMemoryStatusEx` on Windows. A `host_memory_undetected` plan
rejection therefore now always means a real budget shortfall.

---

## 4. Exact commands

### Regenerate every Phase 6-8 Person D package (deterministic, synthetic)

```
python scripts/run_person_d_phase6to8_completion.py \
    --repository-root . \
    --output-root docs/status/person_d_phase6to8_completion_v0_1
```

Byte-identical on re-run. `tests/baselines/test_phase6to8_completion_package.py`
fails if the committed package ever diverges from a fresh generation.

### Verify the accepted MVP identity binding

Person C's two bound artifacts are not vendored into this branch. Extract
them from Person C's current tip with raw-byte fidelity (`git cat-file`,
not a shell redirect that re-encodes), then re-run the binder:

```
git cat-file blob 365e748:configs/collection/mvp_matrix.csv            > <TMP>/mvp_matrix.csv
git cat-file blob 365e748:data/autonomous/pilot_production_ledger.json > <TMP>/pilot_production_ledger.json

python scripts/run_person_d_step6_1_mvp_identity_binding.py \
    --mvp-matrix-path   <TMP>/mvp_matrix.csv \
    --pilot-ledger-path <TMP>/pilot_production_ledger.json \
    --output-path       <TMP>/mvp_input_manifest_reverify.json
```

Expected: `reconciliation_complete=True total=66 set_counts={'core': 48,
'sentinel': 6, 'nosheep': 6, 'nowall': 6}`, and the output SHA-256 equals
`81d3ec35559e470744850310748a476543247c4626aec626d2e6520267122ee0` —
byte-identical to the published `mvp_input_manifest.json`.

The binder fails closed on a byte-size mismatch, so a shell that adds a
BOM or rewrites line endings is rejected rather than silently accepted.

### Baseline production run (blocked; see §7)

```
python scripts/run_person_d_step4_1_eight_family_production.py \
    --fold-manifest    <B_66_CELL_FOLD_MANIFEST> \
    --oracle-targets   <B_66_CELL_ORACLE_TARGETS> \
    --frame-manifest   <A_66_CELL_FRAME_MANIFEST> \
    --output-root      <PERSON_D_PRODUCTION_ROOT> \
    --resume auto
```

### Relevant test selection

```
python -m pytest tests/baselines -q -p no:cacheprovider
```

---

## 5. Modules, schemas, validators, outputs

| Step | Module | Schema ID | Validator |
|---|---|---|---|
| 2.1 | `baselines/shuffled.py` | — | `build_donor_assignments` (fails closed) |
| 3.4 | `baselines/visible_history_q.py` | — | raises `VisibleHistoryQError` |
| 4.5 | `baselines/missingness_audit_v0_1.py` | `person-d-missingness-exclusion-report-v0-1` | `validate_missingness_exclusion_report` |
| 6.1 | `baselines/mvp_identity_v0_1.py` | `person-d-phase6-step6-1-*` | `run_person_d_step6_1_mvp_identity_binding.py` |
| 6.2 | `scripts/run_person_d_step4_1_eight_family_production.py` | `person-b-baseline-input-v0.2` | `baseline_family_input_v0_2.py` |
| 6.3 | `baselines/grouped_nulls_v0_1.py` | `person-d-grouped-nulls-v0-1`, `person-d-paired-comparisons-v0-1` | `validate_grouped_null_document`, `validate_paired_comparison_document` |
| 6.4 | `baselines/preliminary_report_v0_1.py` | `person-d-preliminary-comparison-report-v0-1` | `validate_preliminary_report` |
| 6.5 | `baselines/result_lock_v0_1.py` | `person-d-result-lock-v0-1` | `validate_result_lock` |
| 7.1 | `baselines/u4_control_manifest_v0_1.py` | `person-d-u4-control-manifest-v0-1` | `validate_control_manifest` |
| 7.2 | `baselines/direction_control_audit_v0_1.py` | `person-d-direction-control-audit-v0-1` | `validate_direction_control_audit` |
| 7.3 | `baselines/u4_measurement_join_v0_1.py` | `person-d-u4-control-matrix-v0-1` | `validate_u4_control_matrix` |
| 7.4 | `baselines/specificity_damage_report_v0_1.py` | `person-d-specificity-damage-report-v0-1` | `validate_specificity_damage_report` |
| 7.5 | `baselines/control_failure_record_v0_1.py` | `person-d-control-failure-claim-impact-v0-1` | `validate_control_failure_record` |
| 8.1-8.3 | `baselines/clean_workflow_v0_1.py` | `person-d-clean-workflow-run-v0-1`, `person-d-checkpoint-demonstration-v0-1`, `person-d-checkpoint-classification-v0-1` | three matching validators |

All outputs live under `docs/status/person_d_phase6to8_completion_v0_1/`
with `sha256_inventory.json` recording every artifact's digest.

---

## 6. Known limitations and failure behavior

* Every Phase 6-8 document currently carries `evidence_kind = "synthetic"`.
  None of it is a scientific result. The generator refuses to write
  `"real"` without a real consumed artifact.
* Blocked report and demonstration sections are **structurally empty**.
  An empty section is a missing input, never a null result.
* `run_person_d_step4_1_eight_family_production.py` fails closed per
  family and preserves already-verified outputs. A failed family is
  recorded in `run_state.json` with its error and is never overwritten.
* `raw_pixel` is gated by a memory-plan preflight before any fitting.
  Rejection is recorded, not retried silently.
* The Step 4.1 decision is **FAIL** and stays FAIL wherever referenced.
  It is not rerun, relabelled, or reinterpreted.
* Person D never creates a scientific or causal threshold. Every
  scientific gate in the report pipeline is copied verbatim from Person
  B's frozen `person-b-step4-1-final-comparison-contract-v0-1` and is
  owned by Person B. Person D's own thresholds live in a separate
  `planning_thresholds` namespace and the validator rejects any overlap.

---

## 7. Exact remaining external dependencies

| # | Missing artifact | Owner | Expected schema | Required identity fields | Command after receipt |
|---|---|---|---|---|---|
| 1 | Fold + oracle-target manifests at 66-cell scope (`layout_01..06`, `ep100xx`) | Person B | production-handoff fold manifest + `production_oracle_target_manifest` | `trajectory_id`, `model_frame_idx`, `fold_idx`, `target_name`, `fold_manifest_sha256`, `oracle_target_sha256` | `run_person_d_step4_1_eight_family_production.py` (see §4) |
| 2 | Preprocessed frame manifest at 66-cell scope | Person A | `person-a-preprocessed-frame-manifest-v0.2` | `trajectory_id`, `model_frame_idx`, `payload_sha256`, `preprocess_hash` | `run_person_d_step4_1_eight_family_production.py --preflight --frame-manifest <path>` |
| 3 | Fitted U4 direction, held-out events, dose table, target layer/timestep | Person B | `person-b-intervention-request-v1.0` | `direction_id`, `direction_version`, `direction_hash`, `seed`, `event_id`, `layer_idx`, `timestep_idx`, `dose_id`, `alpha_requested`, `alpha_applied` | `run_person_d_phase6to8_completion.py --u4-direction-record <path> --freeze-real-control-manifest` |
| 4 | U4 rollout measurement table | Person E | `person-b-u4-measurement-input-v0.1` | `clip_id`, `pair_key`, `detector_version`, `homography_version`, `ssim_version`, `outcome`, `missing_reason` | `run_person_d_phase6to8_completion.py --u4-measurements <path>` |
| 5 | Metric table over Person D's predictions | Person B | `person-b-step4-1-final-comparison-output-v0-1` | `metric_id`, `baseline_family`, `target_name`, `layer_idx`, `sample_unit` | `run_person_d_phase6to8_completion.py --metric-table <path>` |

Dependencies 3 and 4 are what Persons A and E are waiting on Person D
for. Person D has published the **complete deterministic builder,
schema, validators, tests, frozen-manifest mechanics, and the D→A/E
handoff document** (`step7_1_control_handoff_to_a_and_e.json`). The real
manifest cannot be frozen until dependency 3 arrives, because the clip
IDs are functions of the real direction version, held-out event IDs,
doses, layer, and timestep. Freezing a manifest over invented identities
would produce clip IDs that A would generate against and E would measure
against — and every one of them would be wrong.

---

## 8. Supersession rules

* Never overwrite a result-bearing artifact. Corrections create versioned
  successors.
* `result_lock_v0_1.supersede_result_lock` returns `(retired_previous,
  successor)`. Persist **both**. The predecessor keeps its facts,
  version, and checksum; it only gains `status="superseded"` and a
  `superseded_by` pointer.
* `control_failure_record_v0_1.add_control_failure` only appends. A
  changed interpretation is a new entry citing the one it supersedes;
  the superseded entry stays visible with its original content.
* The Step 6.1 authority binding v0.1 remains valid evidence; v0.2 is a
  successor that re-cites the current Person C tip, not a replacement.
* Invalid and superseded runs are excluded from current-result summaries
  and retained in `run_history`.

---

## 9. Permitted operational reruns

Allowed without A/B review:

* Regenerating the Phase 6-8 package (deterministic, no scientific value).
* Re-running the missingness/exclusion audit over unchanged rows.
* Re-running preflight and validators.
* Resuming a failed production family from registered `run_state.json`.

**Requires A/B review:**

* Any change to baseline or control *logic*.
* Any change to the frozen family order, applicability, folds, seeds, or
  the derangement rule.
* Any change to a schema ID or version.
* Enabling `require_cross_group_donors` on the grouped-shuffle floor.
* Publishing any document with `evidence_kind = "real"`.
* Any reinterpretation of the frozen Step 4.1 FAIL decision.

---

## 10. Escalation owners

| Topic | Owner |
|---|---|
| Folds, targets, metrics, inference, causal thresholds | Person B |
| Activations, frames, rollouts, injection | Person A |
| Accepted trajectory manifest, capture | Person C |
| Rollout measurement, detector/homography/SSIM versions | Person E |
| Baselines, floors, controls, leakage audits, U4 control matrix | Person D |

---

## 11. Second-operator checklist

1. `git fetch origin --prune`; confirm the six commits in §1 still match.
   If any moved, re-verify the affected binding before running anything.
2. `python -m pytest tests/baselines -q -p no:cacheprovider` — expect zero
   failures and zero collection errors.
3. `python scripts/run_person_d_phase6to8_completion.py` — expect
   `differing_files=0` against the committed package.
4. `git diff --check` — expect no output.
5. `git status --porcelain` — expect empty (the regeneration is
   byte-identical, so it leaves no diff).
6. Read `step8_3_checkpoint_classification.json`. Expect **YELLOW** with
   three `unavailable_input` findings and zero engineering failures. If it
   reads GREEN, something upstream arrived — go to §7 and run the matching
   command. If it reads RED, stop and escalate per §10.
7. Do **not** create the final MVP tag.
