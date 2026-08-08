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

Seven of eight ran on real bytes:

| Family | Class | Applicable rows |
|---|---|---|
| `last_seen` | memory heuristic | 662 |
| `constant_velocity` | reference | 656 |
| `grouped_shuffled` | chance floor | 217 |
| `time_only` | clock floor | 311 |
| `explicit_feature` | fair fitted ceiling | 656 |
| `raw_pixel` | fair fitted ceiling | **blocked — see below** |
| `visible_history_q` | fair baseline | 311 |
| `known_q_analytic` | privileged oracle ceiling | 311 |

9,268 prediction rows, 3,124 applicable. Every non-applicable row
carries a reason and a null prediction — never a zero.

### `raw_pixel` is blocked on host capacity, not on a missing input

Every input `raw_pixel` needs exists and verified: all 2,468 payloads are
present on disk with matching digests. The frozen memory preflight
(`memory_planning.build_raw_pixel_memory_plan`) declined it because the
unchanged ridge pipeline's estimated peak for 662 rows × 258,048 features
is **6.299 GiB**, and this host had ~4.75 GiB free.

This is a host-capacity blocker. No code or input change is required —
re-run the same command on a host with at least 6.3 GiB free physical
memory and the gate admits automatically. The gate is deliberately not
weakened: it exists because a prior production run was OOM-killed.

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
```

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

Verified byte-identical across two runs for all six inventoried
artifacts. `execution_receipt.json` is deliberately excluded from
`sha256_inventory.json`: it carries wall-clock runtime and a live host
memory reading, so a busier machine can never look like a changed
scientific result.

Populate `--authority-root` with `git cat-file blob <commit>:<path>`
(raw bytes; a shell redirect that re-encodes will fail the digest check).

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
