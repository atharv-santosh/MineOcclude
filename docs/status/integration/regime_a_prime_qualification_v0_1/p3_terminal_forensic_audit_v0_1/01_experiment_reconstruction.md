# 01 — Independent P3 Experiment Reconstruction

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.** No historical PASS/FAIL label was altered.

## Method
`p3_progress.json` was **not** trusted. The timeline and every gate were rebuilt from:
- the frozen `p3_development_manifest.json` (sha256 `bb74f9ae…`, hash verified),
- the frozen `p3_preoutcome_authority.json` (sha256 `bd391bd6…`, hash verified),
- the **durable S3 raw streams** (`raw/server_state.jsonl`, `raw/visibility.jsonl`, `raw/frames/*.png`)
  restored from `s3://…/p3_sequential_development_v0_1/` — the local NVMe working root
  `/mnt/sagemaker-nvme/p3_sequential_development_v0_1` is **wiped/empty**, so S3 is the sole surviving copy,
- `p3_events.jsonl` and the per-candidate capture/calibration ledgers (used for timeline only, not for verdicts).

Reconstruction script: `audit_scripts/a04_independent_gate_reconstruction.py` (written against the manifest and raw
data, not against the controller's control flow). Output: `04_candidate_comparison.json`.

## Inventory verification — PASS

| Candidate | capture units | WALL | NO_WALL | calib units | missing | extra | duplicate ids | frames/unit |
|---|---|---|---|---|---|---|---|---|
| P3DEV_C01 | 50 | 25 | 25 | 4 | none | none | none | 180 |
| P3DEV_C02 | 50 | 25 | 25 | 4 | none | none | none | 180 |
| P3DEV_C03 | 50 | 25 | 25 | 4 | none | none | none | 180 |

150/150 scientific capture units exist, are uniquely attributable to one candidate + one trajectory identity +
one scene, and every manifest-expected `run_id` is present with no extras. Every unit carries the full stream
set. `server_tick` is a dense 0..179 sequence in every unit; `scene` field matches the commanded scene in every
row of every unit (0 mismatches across 27,000 state rows).

## Independent candidate timeline

| Candidate | v (b/s) | calibration | capture window (UTC) | adjudicated |
|---|---|---|---|---|
| P3DEV_C01 | 2.0 | 4 runs, 11:52:37 → 12:34:28 (spans restart) | 12:38:01 → 15:36:13 | 15:36:13 |
| P3DEV_C02 | 2.5 | 4 runs, 15:37:00 → 15:49 | 15:49 → 18:29:01 | 18:29:01 |
| P3DEV_C03 | 3.0 | 4 runs, 18:29:49 → 18:42 | 18:42 → 21:23:28 | 21:23:28 |

Two hard failures are recorded, both during C01 calibration, both *before* any scientific capture:
`RuntimeError: approved JDK absent` (12:15:53Z) and `FileNotFoundError: /usr/bin/xdpyinfo` (12:18:09Z).
`runtime_provenance_verified=PASS` was re-emitted at 12:30:56Z and 15:05:26Z.

## Independently reconstructed gate results

| Candidate | capture | PATH | HEADROOM | VISIBILITY | qualification |
|---|---|---|---|---|---|
| P3DEV_C01 | PASS 50/50 | **PASS** | **PASS** | **FAIL** | FAIL_ADVANCE_ALLOWED |
| P3DEV_C02 | PASS 50/50 | **PASS** | **PASS** | **FAIL** | FAIL_ADVANCE_ALLOWED |
| P3DEV_C03 | PASS 50/50 | **PASS** | **PASS** | **FAIL** | FAIL_ADVANCE_ALLOWED |

**This reproduces the controller's recorded verdicts exactly, candidate for candidate, gate for gate.**
`P3_CONTROLLER_DECISION_REPRODUCED_INDEPENDENTLY = true`.

## Precisely which predicate failed each candidate

The `VISIBILITY` gate is a conjunction of four predicates (`p3_run_sequential.py:583`):
`calibration.status == PASS` **and** `normal_ok == 475` **and** `nowall_ok == 475` **and** `ambiguous == 0`.

| Candidate | calib precision (≥0.95) | calib recall (≥0.95) | NORMAL target rows | NO_WALL target rows | failing predicate(s) |
|---|---|---|---|---|---|
| **C01** | **0.846847 FAIL** | 0.979167 pass | 475/475 pass | 475/475 pass | **calibration precision only** |
| **C02** | **0.915459 FAIL** | 0.989556 pass | **474/475 FAIL** | 475/475 pass | **calibration precision + 1 contaminated target row** |
| **C03** | **0.937634 FAIL** | 0.995434 pass | **468/475 FAIL** | 475/475 pass | **calibration precision + 7 contaminated target rows** |

- `C01_FAILED_GATE` = `VISIBILITY → visibility_calibration.rendered_magenta_component_status = FAIL` (precision 0.8468 < 0.95).
  The scientific cohort itself was **perfect**: 475/475 NORMAL and 475/475 NO_WALL, zero disagreements.
- `C02_FAILED_GATE` = same calibration-precision failure (0.9155 < 0.95), **plus** one NORMAL target row
  (`p3dev_c02_t21`, τ=1, tick 28, x=−3.7113) where the detector still saw the target.
- `C03_FAILED_GATE` = same calibration-precision failure (0.9376 < 0.95), **plus** seven NORMAL target rows
  (specs t01, t06, t11, t16, t21 — all τ∈{1,2}, all phase 0).

Recall, the geometric component, the ambiguity count, capture cardinality, path identity and headroom
**passed for all three candidates.** No candidate ever failed for the reason a naive reading of
"VISIBILITY=FAIL" suggests (i.e. the wall not occluding, or the target not being visible without the wall).

## Was extraction legally reachable?
No. `extraction_gated_on_capture_path_visibility_pass = true` in the authority, and the controller emits
`status = FAIL_ADVANCE_ALLOWED` whenever `{path, visibility, headroom} != {PASS}`. Layer-4 extraction, BEST-K
and FULL were correctly `NOT_REACHED` for all three candidates. `layers_extracted = []`, `gpu_used = false`.
Advancement C01→C02→C03 was authorised correctly ("terminal FAIL against this frozen rule"), and termination
after C03 with `BLOCKED_REQUIRES_NEW_PROSPECTIVE_AUTHORITY`, `selected_candidate=None`,
`next_candidate_authorized=None` is correct under the frozen stop rule. **No C04 exists or was created.**
