# Person D 66-cell production baselines (v0.1)

Real Person D baselines executed on the real 66-cell U1/U2 production
universe. No synthetic stand-ins, no ten-pilot replacement rows, no
activation-derived representations.

## Authorities consumed

| Role | Commit | Key artifact | SHA-256 |
|---|---|---|---|
| A | `3384cbfe…` | `preprocessed_frame_manifest.json` | `dda2220d…` |
| A | `3384cbfe…` | `a_to_d_frame_handoff.json` | `a0575a63…` |
| C | `3846230a…` | `canonical_media_manifest.json` | `a11762bd…` |
| C | `3846230a…` | `c_to_d_media_handoff.json` | `84b5b927…` |
| B | `25e09cb6…` | `oracle_target_manifest.json` | `c064e185…` |
| B | `25e09cb6…` | `row_universe_receipt_v0_2.json` | `e897c31c…` |
| B | `25e09cb6…` | `fold_manifest.json` | `86739975…` |
| B | `25e09cb6…` | `b_to_d_successor_handoff.json` | `4b945f79…` |

The B→D handoff digest was recomputed from the committed file at Person
B's exact commit and cross-checked against Person B's own
`sha256_inventory.json`. All ten consumed artifacts verified by raw
bytes; the run fails closed on any mismatch.

## Admission is Person B's

The execution universe is `row_universe_records.jsonl` filtered to
`status == 'accepted'` — the exact selector Person B names. Person D
infers no admission of its own.

```
2468  total model-frame keys
 662  admitted analysis rows
1806  excluded rows
```

Exclusions preserved verbatim: `no_object_control_not_oracle_eligible`
360, `visibility_channel_disagreement` 370,
`ambiguous_geometry_edge_convention` 42,
`outside_frozen_condition_selection` 1034. Zero ambiguous rows admitted.

### Superseded 984-row admission

Person A's frame manifest carries `fold_binding.status` copied from
Person B's **predecessor** `person_b_66_cell_preactivation_v0_1/fold_manifest.json`,
which admitted 984 rows. Person B's `b_to_d_successor_handoff.json`
supersedes it at 662. The 322-row difference is reported in
`authority_verification_receipt.json` rather than silently resolved.
Fold *assignments* are identical between the two (zero disagreements),
so the fold manifest remains authoritative for folds.

## Pixel-input contract

Resolved from Person D's own frozen implementations, not from
availability:

* Seven families take no pixel argument at all.
* `raw_pixel`'s frozen docstring names the **exact current preprocessed
  frame**, so it binds Person A's model-facing payload:
  `[3, 224, 384]` CHW float32 RGB little-endian, range `[-1, 1]`,
  `(x - 0.5) / 0.5` per channel, `cv2.INTER_LINEAR`,
  `cv2.COLOR_BGR2RGB`, `preprocess_hash 8b585e1e…`.

Person C's lossless canonical 640×360 RGB PNG set is the scientific
pixel authority and the head of the hash chain
(`source_raw_sha256` → `source_canonical_png_sha256` /
`source_canonical_pixel_sha256` → `payload_sha256`), but it is not the
raw-pixel feature representation. The H.264 MP4 is never a pixel source.
Person D introduces no image transform.

## Families executed

All eight ran on real bytes:

| Family | Class | Applicable rows |
|---|---|---|
| `last_seen` | memory heuristic | 662 |
| `constant_velocity` | reference | 656 |
| `grouped_shuffled` | chance floor | 217 |
| `time_only` | clock floor | 311 |
| `explicit_feature` | fair fitted ceiling | 656 |
| `raw_pixel` | fair fitted ceiling | 662 |
| `visible_history_q` | fair baseline | 311 |
| `known_q_analytic` | privileged oracle ceiling | 311 |

10,592 prediction rows, 3,786 applicable, zero failed. Every
non-applicable row carries a reason and a null prediction — never a zero.

`raw_pixel` was blocked on an earlier attempt: the frozen memory
preflight (`memory_planning.build_raw_pixel_memory_plan`) declined it
because the unchanged ridge pipeline's estimated peak for 662 rows ×
258,048 features is 6.299 GiB and the host had ~4.87 GiB free. The gate
was never weakened — it exists because a prior production run was
OOM-killed. It admitted at 6.93 GiB free and the family then completed
with all 2,468 payload digests verified on read.

## Metrics

Computed with Person B's own frozen implementations (`metrics.u1_mean`,
`metrics.u2_calibration`, `metrics.resampling`) under Person B's
declared conventions: `float64` arithmetic, layout→trajectory grouping,
bootstrap 1000 @ seed 20260721, permutation 999 @ seed 20260720,
whole-trajectory-block permutation unit, add-one p-value.

Person D applies no threshold and invents no metric. Headline aggregate
R² on the U1 target `mu_oracle_blocks`:

```
explicit_feature   +0.9687     (fair fitted ceiling)
constant_velocity  +0.7286     (reference)
last_seen          +0.6432     (memory heuristic)
grouped_shuffled   -1.2012     (chance floor)
raw_pixel          -1.8961     (below the floor — see below)
```

### `raw_pixel` scoring below the chance floor is the desired outcome

`raw_pixel` reaches held-out R² **-1.8961** on 662 rows (bootstrap CI
[-7.818, +0.022]; -0.183 against the chance floor on their 151 shared
rows). That is a genuine negative scientific result, not an engineering
failure, and it is the direction the study wants.

The family's own frozen docstring states the rule: *"A well-above-floor
score here is a warning sign, not a positive result: it means the current
occluded frame's raw pixels alone carry decodable position information (a
visual-leakage or scene-cue confound)."* Scoring below the floor is
evidence that no such confound is present — the current occluded frame's
pixels alone do not decode the hidden position.

Ridge on 662 rows × 258,048 features is heavily over-parameterized, so a
negative held-out R² is also the expected shape for this estimator at
this row count. Both readings point the same way. Person B owns the
interpretation; Person D applies no threshold to it.

and on the U2 target `log_sigma_oracle`:

```
known_q_analytic   +1.0000     (privileged oracle ceiling — not a fair competitor)
visible_history_q  +0.2516     (fair baseline)
time_only          +0.2186     (clock floor)
grouped_shuffled   -3.1018     (chance floor)
```

`known_q_analytic` reproducing the oracle exactly is the expected
behavior of a privileged reference that consumes the true scripted `q`;
it is labeled `privileged_oracle_ceiling` everywhere and must never be
read as a fair result.

### Recorded as not computed

* **Probe-versus-baseline comparison** — no probe exists until Person A
  publishes the activation index and Person B fits against it. Person D
  instead reports baseline-versus-chance-floor deltas, labeled
  `is_probe_comparison: false`.
* **Coverage / ECE / z-diagnostics** — `calibration_metrics` needs a
  paired mean *and* spread on the same rows. Every Person D spread family
  defines no mean, and pairing one with a mean family would create a
  method Person D has not frozen.
* **Grouped permutation p-values** — Person B's
  `permute_trajectory_blocks` requires ≥2 trajectories per block-length
  stratum; the admitted row universe does not satisfy that. The refusal
  is recorded verbatim rather than worked around with a different unit.
* **U3 reveal snapback** — `VALID_TERMINAL_REVEAL_COUNT = 0`.

## Reproduce

```
python scripts/run_person_d_66_cell_production_baselines.py \
    --authority-root <DIR WITH THE 10 VERIFIED A/B/C ARTIFACTS> \
    --frame-root "C:\Users\lollo\MineOcclude-Person-A-Outputs\person-a-66-cell-preprocessed-frames-v0-2" \
    --output-root docs/status/person_d_66_cell_production_baselines_v0_1
```

Verified byte-identical across two full eight-family runs for all six
inventoried artifacts, including the ridge-fitted `raw_pixel`
predictions. `execution_receipt.json` is deliberately excluded from
`sha256_inventory.json`: it carries wall-clock runtime and a live host
memory reading, so a busier machine can never look like a changed
scientific result.

`raw_pixel` needs at least 6.299 GiB of free physical memory or the
frozen preflight declines it and the family is recorded as blocked
rather than run.

Populate `--authority-root` with `git cat-file blob <commit>:<path>`
(raw bytes; a shell redirect that re-encodes will fail the digest check).

## Steps 4.5 / 6.3 / 6.4 / 6.5 (real)

`scripts/run_person_d_66_cell_step6_3to6_5_completion.py` wires this
package's real predictions and Person B's real row-universe/oracle-target
records through the generic `grouped_nulls_v0_1` / `missingness_audit_v0_1`
/ `preliminary_report_v0_1` / `result_lock_v0_1` modules that, before this,
had only ever been exercised against synthetic fixtures
(`docs/status/person_d_phase6to8_completion_v0_1/`). Every family row
consumed is recomputed from the real execution universe through the exact
same `eight_family_runner.compute_family_rows` dispatch this package's own
production run used, then cross-checked against the real predictions
already published in `prediction_manifest.json` (tight relative tolerance,
to allow for ordinary cross-machine floating-point noise, not logic
drift) before being trusted.

* `step6_3_grouped_nulls.json` -- the real grouped-shuffled null rows
  (1,324 = 662 x 2 targets; 217 available / 1,107 non-applicable, matching
  `prediction_manifest.json`'s own `family_status.grouped_shuffled` exactly).
* `step6_3_paired_comparisons_u1.json` / `_u2.json` -- one real paired
  comparison per frozen objective pair (`last_seen` vs `grouped_shuffled`
  for U1; `time_only` vs `visible_history_q` for U2).
* `step4_5_missingness_exclusion_report.json` -- the consolidated real
  audit over all 10,592 real prediction rows; `audit_passed: true`, zero
  rows missing a reason code, zero duplicates, zero orphans.
* `step6_4_preliminary_comparison_report.json` -- 9 of 10 required
  sections rendered from real, registered values (matching this README's
  headline numbers exactly), including `visible_positive_control` (see
  below). Only `no_object_negative_control` stays blocked: 360 real
  no-sheep rows exist (6 trajectories, one per layout; `control_type=
  "no_object_control"`), excluded from oracle-target scoring by design
  (there is no `mu_oracle_blocks` target with no object to locate), but
  no structural negative-control audit
  (`mineocclude.baselines.controls.audit_occluder_only_control`) has been
  run and registered against them yet -- a real, actionable next step,
  not a claim that the data is absent.
* `step6_5_result_lock.json` -- real locked facts (10,592 predictions,
  3,786 scored, 6,806 non-applicable, 0 missing, 42 accepted / 24 excluded
  trajectories), bound to Person B's real row-universe-receipt and
  fold-manifest SHA-256s.

Reproduce:

```
python scripts/run_person_d_66_cell_step6_3to6_5_completion.py \
    --authority-root <DIR WITH row_universe_records.jsonl AND
                       oracle_target_records.jsonl, verified against
                       PERSON_B_ROW_UNIVERSE_RECORDS_SHA256 /
                       PERSON_B_ORACLE_TARGET_RECORDS_SHA256> \
    --output-root docs/status/person_d_66_cell_production_baselines_v0_1
```

## Step 4.3 (real, PASSED)

`step4_3_positive_control_gate.json`: the frozen visible-position ridge
fit on the real 351 no-wall rows, real fold assignments, real oracle
targets. **PASSED**: held-out R^2=0.99999985 (95% bootstrap CI
[0.99999980, 0.99999987], 1000 resamples), against the roadmap's
R^2>=0.50-and-CI-above-zero pass condition. This is the expected result
for a no-wall row (no occlusion ever occurs, so the last visible
position essentially *is* the true position) -- it's the sanity check
that the measurement pipeline can decode a visible target at all, not a
novel finding.

Getting a real verdict needed a second real artifact Person D's fold
tooling didn't recognize yet: Person B's real 66-cell pre-activation
fold manifest
(`docs/status/person_b_66_cell_preactivation_v0_1/fold_manifest.json`)
declares `artifact_type="person_b_66_cell_fold_manifest"` -- a later
real schema neither `export.attach_b_fold_assignments` nor the
historical `probes.splits.validate_fold_manifest` recognized. Its
layout-to-fold assignment is also structurally unreproducible by
recomputing from admitted-row counts alone: Person B's admission policy
deliberately balances every layout to exactly 164 admitted rows, so
there are no distinct counts left to break ties with. Verified directly
(not assumed): Person B's own builder computes the assignment from
*every* model-frame row (984 accepted + 1,484 excluded = 2,468), via
the same shared, already-tested `assign_layout_grouped_folds` D's
historical validator itself calls -- just over the full row set.
`mineocclude.baselines.preactivation_fold_manifest_66_cell_v0_1`
reproduces that and verifies it matches the real declared assignment
exactly.

Reproduce:

```
python scripts/run_person_d_step4_3_real_positive_control_gate.py \
    --authority-root <DIR WITH row_universe_records.jsonl,
                       oracle_target_records.jsonl, AND
                       fold_manifest.json> \
    --output-root docs/status/person_d_66_cell_production_baselines_v0_1
```

## U4

Not touched. The U4 control manifest remains **unpromoted** and
synthetic. `VALID_TERMINAL_REVEAL_COUNT = 0` and supplemental capture is
required; the real manifest still awaits Person B's direction/dose/
held-out authority.

## Frozen decisions unchanged

Step 4.1 remains **FAIL**. The historical ten-pilot authority
(`frame_handoff_v0_2.py`, 1,695 records, `FROZEN_PILOT_IDS`) is
untouched and still reproducible; `frame_handoff_v0_3.py` is an additive
successor and the ten-pilot set has no executable role in the production
path.
