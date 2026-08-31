# Experiment III Pre-Execution Readiness Audit — Closure

**Closure date:** 2026-08-31
**Scope:** finding-by-finding closure of `PRE_EXECUTION_READINESS_AUDIT_v1_6.md`
**Controlling authority:** `v1.6` (Amendment 3, P0 operational completeness) — **unchanged**
**Boundary assessed:** `A2 == PASS` → provision and qualify the live capture host (`A3`)

This report **stands beside** the failed audit; it does not replace it. That document remains the
record of what was discovered, and this one is the record of what was done about it.

---

## 1. Final Verdict

```
PRE_EXECUTION_AUDIT_STATUS = PASS
READINESS_VERDICT          = READY_FOR_CAPTURE_HOST_PROVISIONING
BLOCKERS_UNRESOLVED        = 0
HIGH_FINDINGS_UNRESOLVED   = 0
MEDIUM_FINDINGS_UNRESOLVED = 0
LOW_FINDINGS_UNRESOLVED    = 0
```

| Disposition | Count |
|---|---|
| `CLOSED` | 17 (+ 2 found during remediation) |
| `ACCEPTED_NONBLOCKING` (informational) | 4 |
| `NOT_A_DEFECT_WITH_EVIDENCE` | 0 |
| `SUPERSEDED_BY_SUCCESSOR_AUTHORITY` | 0 |
| **Unresolved** | **0** |

Two additional defects (`R-01`, `R-02`) were found during remediation, outside the audit's finding
set, and are closed here as well.

The blocker was real and its diagnosis was exact. `run_p0_rve_calibration.py --execute` would have
driven all 252 capture units, spent hours of renderer time, produced 4,032+ frames, and returned —
with no mask, no RVE table, no bootstrap, no validity evaluation and no ladder. The remaining
analysis would then have been written *with the measurements in hand*, on the code path that
decides which materials become `L1`/`L2`/`L3`. That is the outcome-adjacent hazard Amendment 3 §1
exists to prevent, and it is now closed: `--execute` is a single transaction that ends at
`P0_SELECTION_RECEIPT`.

The audit's other central claim — that the evidence chain was self-certifying — was also correct
and is also closed. Tick identity came from `enumerate()`, framebuffer dimensions came from the
`FRAMEBUFFER_*` constants, and `read_succeeded` was the literal `True`, so five `required_evidence`
items were produced by the consumer and could not disagree with it. Python now reads
`client_tick.jsonl`, `capture_complete.json`, `client_authority.json` and the PNG headers, and a
frame record not marked `OBSERVED_PHYSICAL_EVIDENCE` is refused outright.

---

## 2. Controlling Authority

**No authority change was required, and none was made.**

| Quantity | Value |
|---|---|
| `AUTHORITY_VERSION` | `v1.6` |
| `AUTHORITY_SHA256` | `62519701bbe08f94839b6dab4e612826f902f31c736727e8c268cf738897ab4c` |
| `MACHINE_AUTHORITY_SHA256` | `d9de26163df4ca599a5049fb75fd68d010169e53f90aceeb9e4063e60da50609` |
| `AUTHORITY_FREEZE_COMMIT` | `a1f5dd1a959ff477edbf469cd12bb4db606371ea` |
| `PREDECESSOR_AUTHORITY_FREEZE_COMMIT` | `3fd66eddfce017078b6af2774a381077759b98a0` (`v1.5`) |
| Files under `final_authorities/` changed | **0** |
| Authority drift | `false` |

**F-05 resolved as Case A.** The stale `AUTHORITY_FREEZE_COMMIT` lived in
`src/mineocclude/experiment_iii/authority.py:127` — implementation source, not the frozen package.
The frozen `v1.6` amendment is internally correct: both
`AUTHORITY_AMENDMENT_3_P0_OPERATIONAL_COMPLETENESS.md` and
`EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json` name `3fd66ed` as the **predecessor** freeze,
which it is. Only the implementation constant, which the comment said would be "rewritten by the
v1.6 successor freeze commit once it exists", had never been rewritten. Correcting it required no
edit inside `final_authorities/`, so no successor authority was created.

**Scientific decisions changed: none.** The cohort, cohort selection, `q` grid, gate thresholds,
target rows, FIR, extent semantics, P0 placements, candidate roster, ladder rules, RVE formulas,
bootstrap definition, sentinel formula, liveness contract, layers, token slices, representations,
ridge procedure, statistics, multiplicity and claim ladder are untouched. The cohort is proven
byte-identical to the `v1.6` freeze in §7.

---

## 3. Original Audit

`docs/experiment_iii/audits/PRE_EXECUTION_READINESS_AUDIT_v1_6.md` — 913 lines, 21 findings
(1 BLOCKER, 5 HIGH, 5 MEDIUM, 6 LOW, 4 INFORMATIONAL), verdict
`NOT_READY_FOR_CAPTURE_HOST_PROVISIONING` at `HEAD = d0ad665`.

Every finding was independently verified against source before any change was made. **No finding
was dismissed.** All seventeen substantive findings were confirmed accurate as written.

---

## 4. Remediation Scope

Two new modules, seven modified modules, three modified scripts, one new test module, and the
disposition of one contaminated artifact.

| File | Change |
|---|---|
| `src/…/p0_analysis.py` | **new** — the P0 analysis half and all eight `A4` artifact producers |
| `src/…/capture_evidence.py` | **new** — physical evidence parsers and the evidence binding matrix |
| `src/…/capture_driver.py` | evidence read from the apparatus; wall-material and pre-capture probes; warmup issued; dry-run shape |
| `src/…/capture_liveness.py` | `WALL_MATERIAL_CHANGE` required on a transition; observed-provenance requirement |
| `src/…/capture_runtime.py` | pipe-draining threads; server-reply parsing; `output_root` honoured |
| `src/…/sentinels.py` | envelope delegated to the frozen formula; live producer and consumer added |
| `src/…/authority.py` | freeze commit corrected; duplicate constant removed |
| `src/…/artifact_inventory.py` | filesystem-backed stage-exit check |
| `scripts/…/run_p0_rve_calibration.py` | `--execute` closes `A4`; `--analyze` added; attempts retained |
| `scripts/…/run_production_capture.py` | ladder resolved only through the `A4` gate |
| `scripts/…/build_completion_receipt.py` | completion now requires verified runtime wiring |
| `scripts/…/build_static_validation_receipt.py` | remediation recorded |
| `tests/…/test_p0_execution_closure.py` | **new** — 75 discriminating tests |
| `docs/…/capture/capture_schedule.json` | **deleted**; dispositioned under `superseded_evidence/` |

---

## 5. Finding-by-Finding Closure

### F-01 — BLOCKER — the P0 analysis stage is unimplemented and unwired · **CLOSED**

**Verification.** Confirmed exactly as reported. `run_p0_rve_calibration.py` imported only the
eight constants from `rve`. The `--execute` path ended at `state.summary(units)` followed by
`return 0`. Call-site census reproduced: `srgb_to_linear`, `robust_median_image`, `placement_mask`,
`split_half_noise`, `outside_mask_split_half_noise`, `excess_energy`, `aggregate_placement`,
`select_ladder`, `derive_envelope`, `evaluate_batch_boundary` — all zero. Seven of `A4`'s eight
outputs had no producer.

**Repair.** New `p0_analysis.py` orchestrates the frozen pipeline and **calls** the existing
implementation rather than restating it — there is exactly one scientific implementation of record.
`run_p0_rve_calibration.py --execute` now runs `capture_campaign()` then `close_p0_stage()`, which
refuses an incomplete campaign, refuses dry-run evidence, loads real pixels, runs `analyse_p0()`,
and writes all eight artifacts through `write_a4_artifacts()`. A `--analyze` mode re-closes `A4`
from an already-captured campaign without touching the apparatus.

**Evidence.** `test_a14_the_p0_runner_reaches_the_rve_analysis` asserts the call sites exist in the
runner and that `capture_campaign(` precedes `close_p0_stage(`.
`test_a14_every_frozen_rve_primitive_has_a_production_call_site` asserts each formerly-zero symbol
now has one. A full synthetic 252-cell campaign runs end to end and selects the expected ladder.

---

### F-02 — HIGH — the frozen `WALL_MATERIAL_CHANGE` probe is never emitted · **CLOSED**

**Verification.** Confirmed. `verify_unit_liveness` read
`required = {kind for kind in TRANSITION_KINDS if kind != "WALL_MATERIAL_CHANGE"}`, and the only
construction of the probe in the repository was incidental, inside a unit test.

**Repair.** `capture_p0_unit` emits the probe when `transition["probe_required"]`, comparing the
previous unit's last settled frame against this unit's first, and passes
`material_transition=` into `verify_unit_liveness`, which adds the kind to `required` when a
transition occurred. A missing probe on a transition is `CAPTURE_STALE_FRAME`.

**Evidence.** `test_a15_a_material_transition_requires_the_wall_material_probe`,
`test_a15_the_wall_material_probe_satisfies_the_requirement`,
`test_a15_a_stale_wall_across_a_material_change_is_caught`,
`test_a15_the_driver_emits_the_probe_on_a_material_change`.

---

### F-03 — HIGH — four required liveness evidence items are self-certifying · **CLOSED**

**Verification.** Confirmed, and in fact five items were affected rather than four
(`FRAMEBUFFER_READ_SUCCEEDED` was also hard-coded). `FrameSink.frame_records` set
`tick = first_tick + index`, `width`/`height` from constants, `read_succeeded = True`.

**Repair.** New `capture_evidence.py`:

| Evidence | Source now read |
|---|---|
| `SERVER_TICK_MONOTONIC_STEP_ONE` | `client_tick.jsonl` → `server_tick` |
| `ONE_ACCEPTED_FRAME_PER_EXPECTED_TICK` | ledger ⟷ PNG join on `frame_path` |
| `TICK_IDENTITIES_COMPLETE_AND_UNIQUE` | `client_tick.jsonl` |
| `FRAMEBUFFER_READ_SUCCEEDED` | `capture_complete.json` → `drained`, `writer_errors` |
| `FRAMEBUFFER_DIMENSIONS_640x360` | the PNG IHDR chunk, and `client_authority.json` |

`verify_frame_dimensions` now refuses any record not marked `OBSERVED_PHYSICAL_EVIDENCE`, so a
record synthesised from the requested configuration cannot be validated at all. A nonzero
`tick_queue_depth_at_capture` — direct evidence the world advanced past the photographed state — is
a cardinality failure.

**Evidence.** Fourteen tests, including
`test_a29_a_corrupt_tick_ledger_fails_even_when_the_frame_count_is_right` (four frames on disk,
four ledger rows, duplicated ticks — only a real ledger reveals it) and
`test_a29_requested_configuration_cannot_substitute_for_observed_evidence`.

---

### F-04 — HIGH — an untracked, superseded-authority production capture schedule · **CLOSED**

**Verification.** Confirmed in full.

```
path    docs/experiment_iii/capture/capture_schedule.json   (untracked)
sha256  beceb38f0058dd3ed7a76e1cf0b10dd45ab1ad5ce0f3bb4d51c75f70ec145339
bytes   47,383
bound   AUTHORITY_SHA256 = 3d116d97…  (v1.5, superseded)
units   125 captures across all 25 production identities
ladder  L1 = minecraft:white_stained_glass
        L2 = minecraft:lime_stained_glass
        L3 = minecraft:blue_stained_glass
```

**Repair.** Deleted from the operational path. Its identity, binding, provisional ladder and the
reason for its removal are recorded in
`docs/experiment_iii/superseded_evidence/SUPERSEDED_ARTIFACT_DISPOSITION.json`, alongside
Amendment 3 §3a's disposition of the superseded placement derivation. The bytes are deliberately
**not** retained: retaining them would recreate a consumable artifact, and it captured no frame.

The code hole is closed too. `run_production_capture.py` previously accepted any JSON object with
three keys; it now resolves `--ladder` through `p0_analysis.load_selected_ladder`, which requires
the `P0_SELECTED_LADDER` schema, `P0_RESULT == P0_PASS`, `PRODUCTION_AUTHORIZED`, materials inside
the frozen twelve-item roster, no repeated material, `is_provisional`/`superseded` both false, and a
binding to the **current** authority.

**Evidence.** `test_a15_a_v1_5_bound_provisional_schedule_is_rejected` reconstructs the exact shape
of the artifact and asserts refusal; plus `..._a_bare_three_key_ladder_is_rejected`,
`..._a_ladder_bound_to_another_authority_is_rejected`, `..._a_provisional_ladder_is_rejected`,
`..._production_capture_resolves_the_ladder_through_the_gate`,
`..._the_contaminated_schedule_is_gone_and_dispositioned`.

**`P2_CAN_CONSUME_CONTAMINATED_SCHEDULE = false`.**

---

### F-05 — HIGH — `AUTHORITY_FREEZE_COMMIT` names the `v1.5` freeze · **CLOSED** (Case A)

**Verification.** Confirmed, and located precisely: `authority.py:127`, outside the frozen
authority package. See §2 for why no successor authority was required.

**Repair.** `AUTHORITY_FREEZE_COMMIT = "a1f5dd1a959ff477edbf469cd12bb4db606371ea"`, with a
module-level guard raising if it ever again equals `PREDECESSOR_AUTHORITY_FREEZE_COMMIT`. Both
receipts were regenerated and now carry the correct commit; `host_preflight.py:542` will write it
into the `A3` `environment_receipt.json` on the new host, and `host_preflight.py:152` mixes it into
the durable round-trip probe payload, so `A3` evidence binds the right generation.

**Evidence.** `test_a30_the_authority_freeze_commit_is_the_v1_6_freeze`,
`test_a30_current_and_predecessor_freeze_commits_are_distinct`,
`test_a30_the_predecessor_freeze_matches_the_frozen_amendment` (asserts source agrees with the
authority's own declaration rather than with a literal), `test_a30_the_host_receipt_would_carry_the_correct_freeze`.

---

### F-06 — HIGH — undrained `subprocess.PIPE` stdout will deadlock the JVM · **CLOSED**

**Verification.** Confirmed; no `threading` import existed in the module and nothing read either
pipe after `_await_markers` returned.

**Repair.** `_OutputPump` drains each process on a daemon thread from the moment the readiness
marker is seen, mirrors output to a log file under `output_root`, and retains a bounded 400-line
tail for reply inspection. Both pumps are closed on teardown.

**Evidence.** `test_a29_both_process_pipes_are_drained`.

---

### F-07 — MEDIUM — the mandatory pre-capture probe is neither pre-capture nor independent · **CLOSED**

**Verification.** Confirmed. It was synthesised after all four ABBA slots from `results[0]` vs
`results[1]`, which already differ in target presence, duplicating the first target transition — and
`len(results) < 2` would have raised `IndexError` rather than a blocker.

**Repair.** A genuine controlled probe now runs **before** the measured slots: two short capture
slots toggling target presence against the unit's own first state. A dead renderer costs one probe
rather than a whole unit, and the ABBA transitions remain separate probes.

**Evidence.** `test_a29_the_pre_capture_probe_is_issued_before_the_measured_slots` asserts the
probe's source position precedes the measured-slot loop and that the old `results[0]`/`results[1]`
expression is gone.

---

### F-08 — MEDIUM — server command results are never read · **CLOSED**

**Verification.** Confirmed; `send()` wrote to stdin and returned the command string.

**Repair.** `send()` now reads the drained reply and `_assert_not_refused` raises the mod's own
blocker: `P0_CANDIDATE_ID_UNSUPPORTED` for an unsupported registry ID,
`P0_PLACEMENT_GROSS_ERROR` for an out-of-lane placement, `P0_TECHNICAL_FAIL` for any other refusal.
These three `A4` blocker codes previously had no producer on the live path.

**Evidence.** `test_a29_a_mod_refusal_raises_the_mods_own_blocker`.

---

### F-09 — MEDIUM — the artifact-inventory mechanism is unwired from the filesystem · **CLOSED**

**Verification.** Confirmed. `stage_exit_check` compared caller-supplied strings and its only
caller (B.10) supplied the inventory's own patterns, so the check could not fail. Against the real
tree all 11 `A1` artifacts would have reported missing.

**Repair.** `stage_exit_check_fs(stage, root)` stats the real filesystem, resolving each frozen
inventory path through an explicit `REPOSITORY_PATH_ALIASES` table. The frozen inventory is `A0`
and immutable; the implementation materialised the same artifacts at different locations. The table
reconciles implementation to authority explicitly and documents the divergence — every entry is a
*location*, never a substitution, so no artifact can be satisfied by a different artifact.

It is also **called**, not merely available: both `build_completion_receipt.py` and
`build_static_validation_receipt.py` now run it, which is where the stage actually exits, and the
result is recorded in each receipt.

**Evidence.** `test_a29_stage_exit_check_reads_the_real_filesystem` (A1 and A2 pass against the real
repository), `test_a29_stage_exit_check_fails_on_a_missing_artifact` (an empty tree fails with the
artifact's own blocker, not the generic one), `test_a29_a4_cannot_exit_before_p0_has_run`,
`test_a29_every_a1_artifact_resolves_to_a_real_file`,
`test_a29_the_stage_exit_check_has_a_production_caller`,
`test_a29_the_receipts_record_the_stage_exit_check`.

---

### F-10 — MEDIUM — failed P0 units are not recorded · **CLOSED**

**Verification.** Confirmed; `mark_attempt` was called only from a test.

**Repair.** `capture_campaign` wraps the per-unit call so a failure marks the attempt, saves state,
and re-raises. `A4`'s `retry_rules: SAME_FROZEN_UNIT_ONLY; all attempts retained` is now satisfied
on the operational path, and a resumed campaign can distinguish a never-tried unit from one that
has failed repeatedly.

**Evidence.** `test_a29_a_failed_unit_is_marked_before_the_error_propagates`.

---

### F-11 — MEDIUM — frames may be hashed before they are fully written · **CLOSED**

**Verification.** Confirmed; `wait_for_frames` polled file count then slept 1 s.

**Repair.** It now waits for `capture_complete.json`, which the mod publishes only after
`awaitDrained`, and validates `drained == true`, `writer_errors == 0`, `pending_writes == 0` and
the frame count. A file appears at `open`, not at completion.

**Evidence.** `test_a29_wait_for_frames_waits_on_the_drain_receipt_not_a_file_count`,
`test_a29_drained_false_fails_closed`, `test_a29_writer_errors_fail_closed`,
`test_a29_a_missing_completion_receipt_fails_closed`,
`test_a29_a_malformed_completion_receipt_fails_closed`,
`test_a29_a_completion_receipt_for_the_wrong_unit_fails_closed`.

---

### F-12 — LOW — `warmup_ticks` is accepted, recorded, and never applied · **CLOSED**

`capture_p0_unit` now issues `warmup_command(ticks=warmup_ticks)` to the server and records
`warmup_issued`. A receipt claiming a warmup that never reached the server is worse than no warmup.
`test_a29_the_warmup_is_actually_issued`.

---

### F-13 — LOW — `RuntimeConfig.output_root` is required but ignored · **CLOSED**

`output_root` now names where the drained apparatus logs land — the one artefact belonging to
neither game directory. `test_a29_output_root_is_honoured`.

---

### F-14 — LOW — `COHORT_SALT_AUTHORITY_SHA256` is defined twice · **CLOSED**

The second definition and its duplicated comment block were removed.
`test_a30_the_cohort_salt_constant_is_defined_once`. The salt value itself is unchanged and the
cohort remains byte-identical (§7).

---

### F-15 — LOW — `draft_authority/` is untracked but referenced by the authority README · **CLOSED**

The directory is construction-time audit output, explicitly labelled *"NOT AUTHORITY. Do not follow
anything in this directory."* by its own README, and nothing operational reads it. The frozen
authority README cannot be edited, and committing 808 KB of superseded audit scripts is outside
this sprint's scope. It is now declared in `.gitignore` with a comment explaining that its absence
from a clean clone is intentional rather than a silent gap — which is the actual remedy for the
finding, since the finding was that its status was invisible.

---

### F-16 — LOW — a module-scoped fixture can silently skip the frozen capture-order group · **CLOSED**

`test_conditions_and_schedule.py` now raises `AssertionError` instead of `pytest.skip` when the
cohort is absent. It is a required `A1` artifact, so its absence is a failure. This is the same
repair AUD-02 applied to `test_cohort.py`.

---

### F-17 — LOW — dry-run liveness shares the evidence shape of a real verdict · **CLOSED**

A dry run now returns a distinct schema with `measured: False`, `verdict:
NOT_MEASURED_DRY_RUN` and `may_be_persisted_as_complete: False`, and `close_p0_stage` refuses to
analyse any unit whose evidence is dry-run. A planning artefact cannot be analysed as a
measurement. `test_a29_dry_run_evidence_cannot_look_like_a_measurement`.

---

### I-01 … I-04 — INFORMATIONAL · **ACCEPTED_NONBLOCKING**

- **I-01** task-graph `status` fields read `NOT_STARTED`: correct — frozen at `A0`; progress lives
  in the receipts. No source change.
- **I-02** authority README states `IMPLEMENTATION_AUTHORIZED = false`: correct — the `A0`-time
  value inside the frozen package. Authorization is conferred by the independent final audit's
  `IMPLEMENTATION_GO`. No source change.
- **I-03** schedule pressure: acknowledged. `TARGET_CAPTURE_LAUNCH = 2026-09-01 20:00`. This
  sprint consumed implementation time before capture launch, as the audit predicted it would.
- **I-04** the mod's stale-renderer detector logs where nothing listens: **partially actioned at
  near-zero cost**, as the audit suggested. Now that both pipes are drained (F-06), the client's
  `consecutive byte-identical captures` warnings are captured into
  `CaptureRuntime.stale_renderer_warnings` rather than discarded. This is evidence independent of
  the Python probes. `test_a29_the_mods_stale_renderer_warning_is_retained`.

None was promoted to a real finding; none revealed a concrete defect on source inspection.

---

### R-02 — found during remediation, outside the audit · **CLOSED**

Authority 7.6 freezes exactly three outcomes: `P0_PASS`, `P0_NO_VALID_LADDER`, `P0_TECHNICAL_FAIL`.
`rve.select_ladder` returned the bare `"NO_VALID_LADDER"`, so the terminal state reaching an
artifact, a receipt or an operator was a second spelling of an outcome the blocker taxonomy and the
recovery runbook key on under a different name. `p0_analysis.P0_OUTCOMES` normalises the emitted
state to the authority's own vocabulary. Found by the §12 vocabulary check, not by the audit.

---

### R-01 — found during remediation, outside the audit · **CLOSED**

`docs/experiment_iii/p1/p1_pilot_plan.json` declared `authority_version: v1.6` while binding
`AUTHORITY_SHA256 = 442f6a6e4e8a2103…`, a hash that appears **nowhere else in the repository** — an
orphaned binding to an authority generation that no longer exists. Found by the §25 sweep for
artifacts bound to superseded or unknown authorities. Regenerated under `v1.6`; `ladder_bound` was
and remains `false`, so no ladder contamination was involved.

Also swept and found clean: no other artifact claims a stage has executed, no placeholder hashes,
no other operational artifact binds a superseded authority. The `v1.5` hash in
`cohort_qualification_receipt.json` is the `COHORT_SALT_AUTHORITY_SHA256` pinning mechanism working
as designed and is deliberately not touched.

---

## 6. A1 Re-Derivation

`A1_COMPLETE = true`, `A1_TASKS_COMPLETE = 20/20`, **re-derived, not edited**.

The audit's deepest structural point was that the previous receipt marked a task `COMPLETE`
whenever every listed file existed. That is how `I07` and `I08` reached `COMPLETE` with
`20/20` while the analysis half had zero call sites: `rve.py` existed, so `I07` passed.

`build_completion_receipt.py` now carries a `wiring` declaration per task — named symbols that must
be referenced from a **production module or script**, verified by reading that file. A wiring site
inside `tests/` is rejected by the builder itself. A library with no production call site can no
longer be certified complete.

| Task | Status | Runtime call sites verified |
|---|---|---|
| `I04` | `COMPLETE` | 1 (`load_selected_ladder` in `run_production_capture.py`) |
| `I07` | `COMPLETE` | 16 (10 `rve`/`p0_bindings` primitives in `p0_analysis.py`; 4 in the runner) |
| `I08` | `COMPLETE` | 4 (`sentinel_envelope_artifact`, `measure_batch_boundary`, `envelope_from_artifact`, the frozen formula) |
| `I01`–`I03`, `I05`, `I06`, `I09`–`I18`, `IB02`, `IB03` | `COMPLETE` | files, tests and artifacts verified as before |

`I07` is complete only because the full P0 RVE/ladder path is wired; `I08` only because the sentinel
machinery is reachable from live stage boundaries. Receipt regenerated at the final source closure
with `focused_tests: 669 passed`, and it now records the `A1` stage-exit check run against the real
filesystem (`filesystem_backed: true`, `exit_permitted: true`).

---

## 7. A2 Final Validation

Full rerun of the authoritative entrypoint `pytest tests/experiment_iii/` at the final source
closure, after the last source change.

```
PYTEST_COLLECTED = 669      (was 594)
PYTEST_PASS      = 669
PYTEST_FAIL      = 0
PYTEST_ERROR     = 0
PYTEST_SKIP      = 0
PYTEST_XFAIL     = 0

NAMED CHECKS     = 76/76
  Group A  30/30 covered, 30 passed, 0 failed  (1,166 tests)
  Group B  13/13 covered, 13 passed, 0 failed  (   59 tests)
  Group D  33/33 covered, 33 passed, 0 failed  (  268 tests)

JAVA_TESTS       = 43 passed, 0 failed
GRADLE_BUILD     = BUILD SUCCESSFUL (offline, --rerun-tasks)

FINAL_SOURCE_CLOSURE = 1ec404a59f26e0f932fdc0b804d479a581cdead7f93b38a75069c6a922014fa7
```

The receipt's recorded closure equals the working tree's recomputed closure, and the builder aborts
on `SOURCE_CLOSURE_DRIFT` if source changes while the suite runs, so this receipt describes exactly
one closure.

Java was rerun in full even though no Java source changed, because the Python evidence consumers
changed. `P0PresentAbsentSceneTest` and `PythonScheduleCrossCheckTest` both pass, so the frozen
semantics hold: the cache binds material and condition, `NO_SHEEP` preserves the wall and material,
an unsupported material fails closed, frames are zero-padded, the episode directory is reset, and
tick and completion evidence are produced. No Minecraft was launched.

**Explicit regression checks.**

| Check | Result |
|---|---|
| `D.2` — `q = 0.05` generator bit-identity | PASS |
| `D.4` — gate 12 under the amended per-candidate scope | PASS |
| `D.31` — gate-9 scope, gate-12 ordering, cohort-freeze precedence | PASS |
| Cohort byte-identity vs `a1f5dd1` | **6/6 IDENTICAL** |

```
production_identity_manifest.jsonl   336a3baca9316525…   IDENTICAL
folds.json                           cf72e750024ce5b6…   IDENTICAL
identity_priority_order.json         21dac3ddc80d8543…   IDENTICAL
cohort_qualification_receipt.json    5b2d878b47a0eb53…   IDENTICAL
pilot_identity_manifest.jsonl        8eb611afd3b75097…   IDENTICAL
historical_seed_exclusion_set.json   20005d0c01499571…   IDENTICAL
```

The remediation did not move a single byte of the materialized cohort.

---

## 8. P0 End-to-End Code Readiness

`P0_CODE_READY = true`. The full `A4` transaction, traced:

```
--execute --runtime-config C
  │
  ├─ qualify_capture_host()          Linux + Xvfb + llvmpipe, or refuse
  ├─ verify_authority_binding()      v1.6 hashes reproduce, or refuse
  ├─ campaign_manifest()             252 units, 4,032 settled frames
  ├─ P0CampaignState                 refuses resume across authority/source drift
  │
  ├─ capture_campaign()  ── per unit ────────────────────────────────────
  │     warmup issued → controlled pre-capture probe → WALL_MATERIAL_CHANGE
  │     probe on a transition → four ABBA slots → wait on capture_complete.json
  │     → frame_records() joins PNGs to client_tick.jsonl → verify_unit_liveness
  │     → mark_complete / mark_attempt (every attempt retained)
  │
  └─ close_p0_stage() ───────────────────────────────────────────────────
        refuse an incomplete campaign      252/252 COMPLETE_VALIDATED_DURABLE
        refuse dry-run evidence            a plan is not a measurement
        load_unit_frames()                 real pixels, sRGB → linear float64
        analyse_p0()
          ├─ l0_noise_threshold()          per placement, tunable-free, L0 only
          ├─ placement_mask()              union over blocks, dilate 2, shared
          ├─ masked_energy / split_half_noise / excess_energy
          ├─ rve()                         E / E(L0,p,b);  RVE(L0) == 1 exactly
          ├─ aggregate_placement()         median over replicate blocks
          ├─ aggregate_condition()         median over the nine placements
          ├─ background_gate()             noise-relative, candidate-independent
          └─ select_ladder()               1,320 permutations, nine validity
                                           rules, bootstrap seed 1530570907966297797,
                                           lexicographic tie-break
        write_a4_artifacts()               eight artifacts, atomic, hash-bound
        terminal state                     P0_PASS | P0_NO_VALID_LADDER | P0_TECHNICAL_FAIL
```

`A4_ARTIFACTS_EXPECTED = 8`, `A4_ARTIFACT_PRODUCERS_IMPLEMENTED = 8` — derived independently from
`EXPECTED_ARTIFACT_INVENTORY.json`, not from the audit's count. All eight are written to the exact
frozen paths under `docs/experiment_iii/p0/`.

`P0_SELECTION_RECEIPT.json` is written **last** and binds the SHA-256 of every artifact it depends
on, the authority triple, the authority freeze commit, the source closure, the campaign-state
digest, the capture manifest digest, the capture-host receipt, the full per-triple validity records
(nine rules each, with reference values and blocker codes), the deterministic search result, the
tie-break evidence, and the selected `L1`/`L2`/`L3`. P2 can consume it without reconstructing an
interactive decision.

The three previously producer-less `A4` blocker codes — `RVE_SNR_INSUFFICIENT`,
`RVE_ORDER_UNSTABLE`, `RVE_BOOTSTRAP_LOWER_BOUND_NOT_POSITIVE` — are emitted by
`_no_valid_ladder_blockers` with per-rule elimination counts.

**Verified on synthetic data only.** A noise-free 252-cell fixture makes `RVE` exactly the squared
perturbation amplitude, so the assertions are about the frozen arithmetic rather than a tolerance:
`RVE(L0) == 1.0`, each candidate reproduces its assigned value to 1e-9, `V(L4)` is measured and not
forced to zero, the search evaluates exactly 1,320 triples, and the expected ladder is selected.
A degenerate fixture reaches `P0_NO_VALID_LADDER` and refuses to return an approximate ladder.

---

## 9. Sentinel Runtime Readiness

`SENTINEL_RUNTIME_WIRED = true`. `sentinels.py` was imported by tests alone.

A defect not in the audit's finding set was found here: `derive_envelope` implemented a
`3 × stdev` envelope. Authority 7.10e freezes `half_width = k · max(range, floor_fraction · centre)`
with `k = 2.0` and `floor_fraction = 0.15`, and `p0_bindings.sentinel_envelope` already implemented
it correctly. Two divergent formulas would have produced different production invalidations from
identical P0 data. `derive_envelope` now delegates to the single implementation of record.

- **Producer** — `sentinel_envelope_artifact()` is called from `p0_analysis` and emits
  `P0_SENTINEL_ENVELOPE.json` from the selected `L1`'s replicate spread at the three frozen
  placements `[0, 4, 8]`. It refuses any other placement set: sentinel selection is the
  deterministic left/centre/right rule, never chosen from which placements later looked steadiest.
- **Consumer** — `measure_batch_boundary()` is the live production entry point for each
  before/after condition-batch boundary.
- **Prospectivity preserved** — no numeric envelope is invented before P0. The artifact records
  `numeric_envelope_bound: false`, `numeric_envelope_bound_in: "P2"`. When no ladder qualifies the
  envelope is `null` with a stated reason rather than fabricated bounds.

**Fail-closed behaviour, all tested:** a missing envelope refuses the boundary
(`SENTINEL_ENVELOPE_VIOLATION`); an envelope bound to another authority refuses
(`PROVENANCE_AUTHORITY_DRIFT`); an envelope at the wrong placements refuses; a reading missing a
frozen placement refuses; deriving at unfrozen placements refuses. A failure invalidates only the
affected as-yet-unmodeled batch (`AFFECTED_UNMODELED_BATCH_ONLY`, other batches unaffected), an
already-modeled batch escalates rather than being rewritten, and the receipt asserts
`may_change_materials: false` and `is_a_condition_selection_mechanism: false` — scientific condition
selection cannot change based on sentinel performance.

---

## 10. Physical Evidence Binding

`PHYSICAL_EVIDENCE_SELF_CERTIFICATION_REMAINING = 0` for every authority-required item observable
before P0. The binding matrix is emitted into each unit's liveness receipt by
`capture_evidence.evidence_binding_matrix()`, and a test asserts it covers exactly the frozen
`required_evidence` set.

| Evidence ID | Class | Physical producer | Artifact | Python parser | Validator |
|---|---|---|---|---|---|
| `SERVER_TICK_MONOTONIC_STEP_ONE` | observed | `ClientLogger.writeTick` | `client_tick.jsonl` | `read_client_tick_ledger` | `verify_tick_integrity` |
| `ONE_ACCEPTED_FRAME_PER_EXPECTED_TICK` | observed | `MineOccludeClient.captureOne` | ledger ⟷ PNGs | `join_frames_to_ticks` | `verify_tick_integrity(expected=…)` |
| `TICK_IDENTITIES_COMPLETE_AND_UNIQUE` | observed | `ClientLogger.writeTick` | `client_tick.jsonl` | `read_client_tick_ledger` | `verify_tick_integrity` |
| `CAPTURE_PROCESS_ALIVE` | observed | the JVM processes | `subprocess.poll()` | `CaptureRuntime.alive` | `verify_unit_liveness` |
| `FRAMEBUFFER_READ_SUCCEEDED` | observed | `FrameCapture.writeErrors`/`awaitDrained` | `capture_complete.json` | `read_capture_complete` | `verify_frame_dimensions` |
| `FRAMEBUFFER_DIMENSIONS_640x360` | observed | the PNG encoder; `getFramebuffer()` | IHDR chunks; `client_authority.json` | `png_dimensions`/`read_client_authority` | `verify_frame_dimensions` |
| `FRAME_HASH_RECORDED_AS_DIAGNOSTIC` | requested | the PNG bytes | the frame files | `FrameSink.frame_records` | diagnostic only (7.10f) |

Runtime call site for all of them: `capture_driver.FrameSink.frame_records`, reached from
`capture_p0_unit`, reached from `run_p0_rve_calibration.py --execute`.

**P0 present/absent semantics.** `Scene.NO_SHEEP` means target absent with the same requested wall,
material, camera and environment. The mod side was already correct and is re-verified by
`P0PresentAbsentSceneTest`; what changed is that Python no longer takes the request as proof.
The wall material is now confirmed at the pixel level by the `WALL_MATERIAL_CHANGE` probe, and the
scene the frames actually record is confirmed through the mod's own tick and completion receipts.

---

## 11. Contaminated / Superseded Artifact Disposition

| Artifact | SHA-256 | Disposition |
|---|---|---|
| `docs/experiment_iii/capture/capture_schedule.json` | `beceb38f…c145339` | **DELETED** from the operational path; identity retained in `superseded_evidence/SUPERSEDED_ARTIFACT_DISPOSITION.json`; `may_enter_p2: false` |
| `docs/experiment_iii/p1/p1_pilot_plan.json` | (regenerated) | **REBOUND** from orphaned `442f6a6e…` to `v1.6` |
| Superseded uniform-partition placements | `a3deb1df…` | unchanged — already correctly dispositioned by Amendment 3 §3a |
| `docs/experiment_iii/draft_authority/` | — | working material; declared in `.gitignore`; not authority, nothing reads it |

The §25 sweep across `docs/experiment_iii/`, `scripts/experiment_iii/` and
`src/mineocclude/experiment_iii/` found no other operational hazard: no artifact claims a stage has
executed, no placeholder hashes, and the remaining `v1.5` hashes are the deliberate cohort-salt
pinning and legitimate historical provenance.

---

## 12. Intentionally Future Work

None of the following is missing work. Each is correctly absent at this boundary.

- **Capture-host provisioning** — WSL2, JDK, Xvfb, Mesa, Fabric, the Minecraft mirror. Not started;
  this sprint deliberately changed no machine state.
- **`A3` on the real host** — `environment_receipt_<host>.json` requires `POOL_*` device
  identities, free-byte measurement, a durable round trip, display availability, the mod jar hash
  and the 1.16.5 / Fabric 0.15.11 / API 0.42.0 pins. Cannot exist before the host does.
- **`A4` P0 *data*** — image inventory, RVE table, bootstrap results, mask inventory, selected
  ladder, selection receipt, sentinel envelope *values*. Their **producers** are complete and
  tested; the data requires the host.
- **Sentinel envelope numbers** — Amendment 3 §3e freezes the formula now and binds the numbers in
  P2. Their absence is correct prospectivity.
- **`A5` P1 pilot data**, **`A6` P2 freeze**, **`A7`–`A10` production capture and extraction**,
  **`A11`–`A19` analysis through closure** — all gated behind a passed `A4`.
- **GPU host, MineWorld inference, SageMaker** — no checkpoint load, no VAE, no CUDA, no inference.
  `run_extraction.py` still refuses inference without an injected decoder.
- **Every III-B runtime stage** — `CLEAN_SKIP` remains a pre-registered honourable outcome.

---

## 13. Final Pre-Execution Gate

```
PRE_EXECUTION_AUDIT_STATUS = PASS
READINESS_VERDICT          = READY_FOR_CAPTURE_HOST_PROVISIONING

AUTHORITY_VERSION          = v1.6
AUTHORITY_DRIFT            = false
AUTHORITY_CHANGED          = false

BLOCKERS_UNRESOLVED        = 0
HIGH_FINDINGS_UNRESOLVED   = 0
MEDIUM_FINDINGS_UNRESOLVED = 0
LOW_FINDINGS_UNRESOLVED    = 0

A1_COMPLETE                = true    (20/20, wiring verified)
A2_STATUS                  = PASS    (669/669, 76/76 named checks)
P0_CODE_READY              = true
CAPTURE_RUNTIME_READY_IN_CODE = true
SENTINEL_RUNTIME_WIRED     = true
PHYSICAL_EVIDENCE_SELF_CERTIFICATION_REMAINING = 0

CAPTURE_HOST_PROVISIONED   = false
CAPTURE_HOST_A3_STATUS     = NOT_RUN
LIVE_P0_DATA_EXISTS        = false
P1_DATA_EXISTS             = false
P2_EXECUTED                = false
PRODUCTION_DATA_EXISTS     = false

SAGEMAKER_STARTED          = false
GPU_USED                   = false
CUDA_USED                  = false
MINEWORLD_MODEL_LOADED     = false
MINEWORLD_INFERENCE_RUN    = false
MINECRAFT_RUN              = false

READY_FOR_CAPTURE_HOST_PROVISIONING = true
```

An independent engineer cloning this repository today would find that everything required to exist
before provisioning the live Experiment III capture host does exist, is wired into the real runtime
path, is authority-bound, has discriminating tests, and has passed the complete static/CPU
validation wall. No live P0 evidence has been generated.

**The next legitimate action is host provisioning**, followed by `A3` on that host, host
qualification, and only then P0 execution.
