# MineOcclude Experiment III — Recovery and Resume Runbook

**Binds to:** `EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md` (`AUTHORITY_SHA256`)

**Premise:** at least one engineering failure **will** occur. This runbook exists so that when it
does, the failure is localizable, the repair is bounded, completed valid work survives, and the
science stays prospective.

---

## 0. The five questions, in order

Whenever anything fails, answer these five before touching anything:

1. **What exactly failed?** Name a code from `BLOCKER_TAXONOMY.json`. Never proceed on prose.
   If no code fits, the failure is unclassified — classify it first (`STATUS_BLOCKER_CODE_UNKNOWN`).
2. **Is it technical or scientific?** Look up `technical_or_scientific` for that code, then apply
   the §9.3 decision test. If uncertain, treat it as scientific.
3. **What does it invalidate?** Look up `invalidation_scope`. Invalidate exactly that — no more,
   no less. Over-invalidating destroys valid work; under-invalidating contaminates the result.
4. **Where do we resume?** Look up `resume_point`.
5. **Does the science remain prospective?** If the repair changes any frozen scientific value,
   stop and raise `AUTHORITY_AMENDMENT_REQUIRED` (§9.2). It is never a bug fix.

---

## 1. Universal invariants

- **Completed, validated, hash-bound work is never recomputed** merely because a later stage
  failed. A crash in extraction does not cost you a capture.
- **Same-spec resume only.** A unit resumes only if its recorded spec hash, source hash, authority
  hash, and source closure all still match. Any mismatch discards and re-plans the unit; it is
  never silently reused.
- **The ledger is the authority on state, not the filesystem.** A directory that exists without a
  ledger entry is an orphan and is discarded. A ledger entry without its artifacts is a failed
  unit and is retried.
- **Retry means the same frozen unit.** Never a different seed, path, direction, condition,
  material, target row, label, camera, or timing policy.
- **Keep the first technically valid attempt.** A later attempt does not replace an earlier valid
  one. All failed attempts are retained under `attempts/<ordinal>/` with their classification.
- **Status is never a control input.** Recovery reads the ledger and the receipts, never
  `status.json`.
- **A crash must never force a full experiment restart.** If it appears to, the resume logic is
  defective — that is `A.29` failing, and it is a repair, not a restart.

---

## 2. Per-stage recovery — Part III-A

### A1 — Implementation

| | |
|---|---|
| **Unit of work** | one task-graph task (`I01`–`I18`, plus `IB02` and `IB03`, which gate `I02`) |
| **Durable completion evidence** | the task's entry in `implementation_completion_receipt.json` with its named tests passing |
| **Safe restart point** | the failed task |
| **Invalidation scope** | the failed task and its dependents in the task graph |
| **Same-spec verification** | the source closure recorded in the receipt matches the worktree |
| **Reuse** | every completed task with passing tests |
| **Discard** | nothing, unless the cohort is regenerated |
| **Never rerun unnecessarily** | completed tasks whose tests still pass |

**The `D.2` reference is provenance-bound.** If `D.2` cannot find its reference, it is bound at
authority `fir.d2_regression_reference`: commit `f2bc2c8`, the **`v0_3`** `stage2_locked_manifest.json` (sha256 `ad718685…`), unit `a2x_t01_wall`, seed
`2154560968567132226`, start `-7.8`, LTR, `q = 0.05`. It is **not** in the `v0.4` manifest that
carries the FIR recovery — that is expected, not a defect.

**Cohort regeneration.** Permitted **only while no capture of any kind exists**. It invalidates
every A1 cohort artifact and everything derived from them. Once any capture exists, cohort
regeneration is forbidden and is a §9 amendment. **Regeneration on the basis of any outcome is
forbidden at all times**, capture or no capture.

**Gate 12 — the all-`q` qualification gate — fails in exactly two ways, and they are different
problems.**

1. **`COHORT_ALL_Q_PRIMITIVE_MISSING`.** `I02` was reached while `IB02` or `IB03` was absent or
   failing. `I02` **fails closed**: no cohort artifact is written. Resume at `IB02`, get `D.2`,
   `D.4` and `D.31` green, then rerun `I02`. Nothing is lost. This is a plain sequencing defect.
2. **`COHORT_ALL_Q_QUALIFICATION_INFEASIBLE`.** Candidates satisfying gates 1–11 at **every**
   frozen `q` ran out. The **only** permitted responses are: continue scanning in ascending
   candidate index up to the frozen bound of **200 per direction**; or repair an implementation
   defect and rerun the identical deterministic procedure while no capture exists. If the bound
   is genuinely exhausted, that is terminal and requires a §9 amendment.

   **Never**: relax gate 12; relax gates 1–11 at any `q`; drop a `q` from the binding set;
   change the master salt to get a friendlier candidate stream; or consult any outcome. Each of
   those is a scientific change wearing a repair's clothes.

   The cohort is **identical whether III-B later runs or clean-skips**. A gate-12 failure is a
   III-A problem with a III-A remedy; it is never fixed by weakening or skipping III-B.

**FIR recovery failure.** `FIR_KERNEL_RECOVERY_FAILED` is terminal for Experiment III until a
prospective amendment supplies an authenticated kernel source. Do **not** refit the kernel from
Experiment III data — that is a scientific change wearing a repair's clothes.

**`FIR_KERNEL_NOT_NORMALIZED` is not that, and is cheap to fix.** The published taps are rounded
to 10 decimals, so `fsum(LEFT_TO_RIGHT) = 0.9999999999`. Unnormalized taps pass the `1e-9` label
tolerance of `A.12` but fail the `1e-12` `S(τ)` tolerance of `D.6` by up to `9.29e-10`. Divide
each tap by `math.fsum(taps)` **once at load**, accumulate with `fsum`, and rerun. This is a
code repair, not an amendment.

---

### A2 / A3 — Static validation and preflight

| | |
|---|---|
| **Unit of work** | one test (A2 — groups **A, B and D**); one preflight check (A3) |
| **Durable completion evidence** | `static_validation_receipt.json`; `environment_receipt_<host>.json` |
| **Safe restart point** | rerun the **full** suite / **full** preflight |
| **Invalidation scope** | any source change invalidates A2; any environment change invalidates A3 and every later receipt bound to it |
| **Reuse** | nothing — both are cheap and must be re-run whole |
| **Never rerun unnecessarily** | n/a |

A partial test run is not evidence. Do not "rerun just the failing test" and record a PASS.

**A2 runs group D too.** A failure in `D.2`, `D.4` or `D.31` **blocks III-A** — those three
guard the cohort. A failure in any other group-D check is a **III-B** blocker only: III-A closes
unaffected, and III-B proceeds toward `CLEAN_SKIP` if it cannot be repaired in time. Never delay
III-A for a group-D failure outside those three.

**A2 is read by the deadline clock.** `A2 == PASS` is the input to the derived
implementation checkpoints (authority §10.5): **CP1 Tue 2026-09-01 13:00** → plan 10.2,
**CP2 Tue 20:36** → plan 10.3, **CP3 Wed 2026-09-02 00:48** → plan 10.4. Each instant is
*deadline minus that plan's conservative post-`A2` tail*, so it is the last moment that plan
can still close. If you are repairing A2 near one of those instants, the checkpoint still
fires on the clock; it does not wait for you.

**Before those, CP0 (Mon 2026-08-31 20:00, milestone `I10`) defers all III-B-only
implementation.** That is the only checkpoint that reliably recovers *implementation* time
(2.0/4.0/7.0 h); CP1 and CP2 mostly recover the *tail*. `IB02`/`IB03` are never deferred.

**A3 storage failures.** `STORAGE_INSUFFICIENT` means free bytes on `POOL_WORKING` are below the
combined-program gate (**64 GiB** mirrored, **40 GiB** unmirrored — authority §13.2). Free real
space and rerun; **never lower the threshold**. Note the gate-coherence invariant: a host that
passes `A3` at exactly 64 GiB retains `15.204 GiB` at the III-B launch gate, which requires
`15 GiB` — so passing `A3` at the threshold does **not** doom III-B. `STORAGE_POOL_DOUBLE_COUNTED` means a gate was
satisfied by counting one filesystem twice, or decimal GB were compared against a binary-GiB
threshold: resolve the device/volume id of every gated path, record the durability mode, and
rerun. If the durable store is remote object storage it has **no** local free-space gate — verify
reachability and a hashed round trip instead.

---

### A4 — P0 candidate capture

| | |
|---|---|
| **Unit of work** | one `(condition, placement, replicate block)` capture set |
| **Durable completion evidence** | that unit's rows in `P0_IMAGE_INVENTORY` and `P0_RVE_TABLE`, with per-frame framebuffer hashes |
| **Safe restart point** | the failed `(condition, placement, block)` |
| **Invalidation scope** | a **mask** change invalidates every candidate at that placement; a **candidate re-measure** invalidates only that candidate's placement scores and the selection |
| **Same-spec verification** | placement coordinates, ABBA order, frame counts, lighting policy, and code hash all match `P0_MANIFEST` |
| **Reuse** | every verified `(condition, placement, block)` unit |
| **Discard** | blocks that failed staleness, background tolerance, or replicate CV |
| **Never rerun unnecessarily** | the full 14×9×2 grid, when one block failed |

**Distinguish the three outcomes before repairing.** `P0_TECHNICAL_FAIL` is repairable.
`P0_NO_VALID_LADDER` is a **scientific result** — it stops Experiment III and returns to authority
adjudication. Re-running P0 hoping a ladder appears is forbidden; so is widening any zone or
threshold.

---

### A5 — P1 pilot

| | |
|---|---|
| **Unit of work** | one `(pilot identity × condition)` capture, then one extraction unit |
| **Durable completion evidence** | the item's observed value in `p1_pilot_receipt.json` |
| **Safe restart point** | the failed pilot unit |
| **Invalidation scope** | a pipeline change invalidates the pilot receipt; re-pilot the affected span. If the defect could have affected earlier units, re-pilot **everything** |
| **Reuse** | pilot units unaffected by the defect |
| **Never rerun unnecessarily** | the whole pilot, for a defect provably confined to one unit |

Pilots are sacrificial. Spend them freely — that is what they are for. Never substitute a
production identity, and never promote a pilot into production.

---

### A7 — Production capture

| | |
|---|---|
| **Unit of work** | one `(identity × condition)` capture unit |
| **Durable completion evidence** | ledger state `COMPLETE_VALIDATED_DURABLE` plus `durable_receipt.json` verified by read-back hash |
| **Safe restart point** | the next unit in the frozen Latin order that is not `COMPLETE` |
| **Invalidation scope** | per-unit failure → that unit only. **Sentinel failure → the affected as-yet-unmodeled capture batch only.** Cache-key/stale-wall failure → every unit since the last verified rebuild |
| **Same-spec verification** | spec hash, path hash, noise hash, target rows, condition, material, authority hash, freeze package hash |
| **Reuse** | every `COMPLETE_VALIDATED_DURABLE` unit |
| **Discard** | partial units with no ledger `CAPTURED` entry; units failing any receipt |
| **Never rerun unnecessarily** | a `COMPLETE` unit; an entire batch when one unit failed |

**State machine:** `PLANNED → RUNNING → CAPTURED → VALIDATED → DURABLE → COMPLETE_VALIDATED_DURABLE`.

**Resume procedure:**

1. Read the ledger; collect `COMPLETE` unit IDs.
2. For each planned unit in frozen order, skip if `COMPLETE`.
3. If a final directory exists, re-validate against the spec hash, then finish durability.
4. If a same-spec partial exists and the last state is `CAPTURED`, resume packaging.
5. Otherwise discard the partial, append `PLANNED` with `retry_same_spec=true`, and re-capture.

**A stale-wall event is the dangerous one.** If `WALL_CACHE_KEY_STALE` or
`WALL_MATERIAL_MISMATCH` fires, do not assume it is confined to the detected unit. Invalidate
every unit captured since the last verified rebuild, because the wall receipt is the only
independent evidence of what was actually standing.

---

### Durability publication

| | |
|---|---|
| **Unit of work** | one object |
| **Durable completion evidence** | uploaded-object metadata verified **and** downloaded bytes re-hashed |
| **Safe restart point** | the failed object |
| **Invalidation scope** | the failed object only |
| **Reuse** | every object whose downloaded bytes already verified |
| **Never rerun unnecessarily** | re-uploading a whole unit for one failed object |

Local deletion is permitted **only** after a durable copy plus read-back hash verification. If
`DURABILITY_READBACK_MISMATCH` fires, the local copy is authoritative and must not be deleted.

---

### A9 — Extraction

| | |
|---|---|
| **Unit of work** | one `(capture unit × layer × slice)` persisted array — 6 per capture |
| **Durable completion evidence** | unit state `COMPLETE` in the ledger, with source-capture hash, extraction-spec hash, expected outputs, and actual hashes |
| **Safe restart point** | the failed array unit |
| **Invalidation scope** | source-capture change → every array derived from it. **Extraction-spec change → ALL arrays.** Otherwise the single array |
| **Same-spec verification** | recorded source-capture hash **and** extraction-spec hash both match the current plan |
| **Reuse** | `COMPLETE` units are skipped without reading bytes; `DURABLE` units are re-sealed; `EXTRACTED` units are re-validated rather than re-extracted |
| **Discard** | any unit whose source or spec hash no longer matches |
| **Never rerun unnecessarily** | a completed capture's 19 forwards, when one of its 6 arrays failed to write |

**State machine:** `PLANNED → RUNNING → EXTRACTED → VALIDATED → DURABLE → COMPLETE`.

The six arrays of a capture share one set of 19 forwards. The ledger records that shared forward
set, so a crash after four of six arrays re-writes only the missing two — it does not re-run
inference. This is the single most valuable recovery property in the pipeline: at roughly
`19 × 0.69 s` of GPU time per capture, re-running forwards unnecessarily across 125 captures is
hours of avoidable work.

---

### A10 — Tensor validation

| | |
|---|---|
| **Unit of work** | one persisted array |
| **Durable completion evidence** | its row in `extraction_validation_receipt.json` |
| **Safe restart point** | re-validate the failed array; if it fails on content, re-extract it (A9) |
| **Invalidation scope** | the array only |
| **Reuse** | every validated array |
| **Never rerun unnecessarily** | full re-extraction for a validation-code defect |

Distinguish a **validator bug** from a **bad array**. If the validator was wrong, fix it and
re-validate — do not re-extract 750 arrays.

---

### A11 — Feature construction

| | |
|---|---|
| **Unit of work** | one `(capture unit × representation)` feature block |
| **Durable completion evidence** | the block's hash in `feature_config.json` |
| **Safe restart point** | the failed block |
| **Invalidation scope** | a representation-definition change invalidates **every** block of that representation and the prediction lock. A single corrupt block invalidates only itself |
| **Reuse** | every block whose hash verifies against the current feature config |
| **Never rerun unnecessarily** | all four representations, when one block failed |

Features are cheap relative to capture and extraction. When in doubt here, rebuild.

---

### A12 — Prediction generation

| | |
|---|---|
| **Unit of work** | one `(outer fold × condition × model)` prediction block |
| **Durable completion evidence** | the block's presence and hash in `PREDICTION_LOCK.json` |
| **Safe restart point** | **before the lock:** the failed block. **After the lock:** nothing — see below |
| **Invalidation scope** | any feature or fold change invalidates the whole lock |
| **Reuse** | before the lock, completed blocks |
| **Never rerun unnecessarily** | the full fit, for a defect in one fold |

**This is the irreversible boundary.** Once `PREDICTION_LOCK.json` exists, no feature, fold, alpha
grid, representation, baseline, or model may change. A change after the lock requires a §9
amendment, a fully re-run analysis, and explicit disclosure that the change was made with outcomes
visible. There is no quiet path back across this line.

---

### A14–A16 — Statistics and bootstrap

| | |
|---|---|
| **Unit of work** | one estimand, contrast, or age bin |
| **Durable completion evidence** | its entry in the corresponding results file |
| **Safe restart point** | recompute the failed estimand **from the lock** |
| **Invalidation scope** | the affected estimand only; never backwards |
| **Same-spec verification** | the lock hash and bootstrap seed match the freeze package |
| **Reuse** | the prediction lock, always. It is never regenerated |
| **Never rerun unnecessarily** | prediction generation, for a statistics bug |

A statistics defect is repaired by fixing the statistics code and recomputing **from the same
locked predictions and the same seed**. Regenerating the lock to fix a statistics bug is a
category error and destroys the prospective guarantee.

---

## 3. Cross-stage recovery scenarios — Part III-A

**Host dies mid-production-capture.** Restart the process. It reads the ledger, skips every
`COMPLETE` unit, and resumes at the next unit in the frozen Latin order. Nothing is recaptured.
Verify the sentinel state of the interrupted batch before continuing; if the interruption spanned
a batch boundary, re-run the boundary sentinel.

**Disk fills during extraction.** `STORAGE_EXHAUSTED` on the in-flight unit only. Free space on
`POOL_WORKING` — the safest candidate is temporary activation copies whose durable counterparts
already verified — then resume. Completed arrays are untouched. If `POOL_SCRATCH` shares a device
id with `POOL_WORKING`, freeing scratch frees the same pool; if it is genuinely a distinct
filesystem, freeing it does **not** help the working pool. Check the device ids recorded in the
A3 receipt before deciding what to delete.

**Wrong wall discovered three units into a batch.** `WALL_MATERIAL_MISMATCH` or
`WALL_CACHE_KEY_STALE`. Invalidate every unit since the last verified rebuild — not just the
detected one. Fix the cache key (C07), force a rebuild, re-capture the invalidated units under
the same frozen specs. Earlier batches are unaffected.

**Sentinel fails after a batch.** Technical, batch-scoped. The affected batch's captures are
invalidated **only if not yet modeled**. Investigate client state, re-run the sentinel, re-capture
the batch. Materials, target rows, and statistics are untouchable.

**Extraction spec found to be wrong after 300 arrays.** `EXTRACTION_SPEC_DRIFT` invalidates **all**
arrays — the spec defines what every array means. Captures are **not** invalidated. Fix the spec,
re-extract from the unchanged captures. This is exactly why capture and extraction are separate
stages with separate units.

**A statistics bug is found after results exist.** Fix the code, recompute from the lock with the
same seed. Disclose nothing beyond the repair — the predictions did not change. If the "bug" turns
out to be a disagreement about which estimand to compute, it is a §9.2 scientific change, not a
bug.

**Fewer than 15 complete identities at the deadline.** Not a recovery problem. `A8` emits
`COHORT_INSUFFICIENT_COMPLETE_IDENTITIES`, no graded inferential claim is made, and the experiment
closes under §14 row 16 as a disclosed no-claim closure. Do not replace identities, drop
conditions, or impute cells to reach 15.

---

## 4. What must never be rerun

- A capture unit already `COMPLETE_VALIDATED_DURABLE`.
- An extraction unit already `COMPLETE`.
- A completed capture's 19 forwards, when only a serialization step failed.
- The full P0 grid, when one `(condition, placement, block)` failed.
- The prediction lock, to fix anything downstream of it.
- Any historical Regime A, Regime A-prime, or Experiment II artifact — these are immutable and
  must never be regenerated by any Experiment III process.

## 5. What must always be rerun

- The **full** static test suite after any source change.
- The **full** preflight after any environment change.
- The batch-boundary sentinel after any interruption spanning a boundary.
- The complete validator for any stage whose receipt was invalidated.
- Every unit invalidated by a stale-wall event, back to the last verified rebuild.

---

## 6. III-B recovery (module III-B, added by Phase 1 Amendment 1)

**Governing principle.** A III-B failure's invalidation scope is **bounded to III-B**, unless it
proves a **shared III-A implementation defect** — in the q-generalized generator, the extent
engine, the FIR machinery, the extraction path, or the ridge machinery. In that case the III-A
repair policy (§9) applies in full, including III-A's invalidation scopes.

**Three outcomes, never confused:**

```
CLEAN_SKIP       III-B was never launched, or was dropped by the frozen time/resource ladder.
                 Pre-registered and honourable. NOT a failure. NOT a technical blocker.

TECHNICAL_FAIL   Something broke. Repairable. NOT a scientific result.

SCIENTIFIC_NULL  A valid III-B measurement that did not support U2/U3.
                 A publishable result. NEVER reported as a blocker, and never "recovered from".
```

**The overriding rule at every step below: never delay III-A closure to save III-B.**

---

### `B-GEN` — q manifest generation

| | |
|---|---|
| **Unit of work** | one `(identity, q)` cell |
| **Durable completion evidence** | the cell's row in `iii_b_q_manifests.jsonl` plus the manifest hash |
| **Safe restart point** | regenerate the manifests |
| **Invalidation scope** | III-B only — **unless** the defect is in the shared q-generalized generator, in which case the III-A cohort is also suspect and §9 applies |
| **Same-spec verification** | the q=0.05 regression receipt still reproduces the frozen A-prime path hash |
| **Reuse** | the III-A cohort, always. III-B never regenerates III-A identities |
| **Never rerun unnecessarily** | the III-A cohort, for a III-B manifest defect |

**B-GEN re-verifies; it does not discover.** Every admitted identity was already proven at `A1`,
under qualification **gate 12**, to qualify at all three binding `q`. A B-GEN qualification
failure at a **binding** `q` therefore means the A1 and B-GEN evaluations disagree — an
implementation defect — and it **never** regenerates the III-A cohort.

**The `q = 0.15` exception.** Cells at the technical fallback `q = 0.15` were **not** covered by
binding gate 12 (the fallback is a recorded diagnostic, not a binding level). If the fallback is
triggered at `B-PILOT` and some cells then fail qualification, that is ordinary **III-B-local
attrition**: apply the drop ladder (`LEVEL 3`, the first ≥15 complete triples in frozen priority
order). It is not a cohort problem and never touches III-A.

**The dangerous case.** If `B_Q_PAIRING_MISMATCH` fires, determine immediately whether the defect
is confined to the III-B cell expansion or reaches the shared generator. Run D.2 (the q=0.05
regression). If D.2 **fails**, the III-A cohort is suspect: stop, escalate to §9, and re-validate
III-A before proceeding. If D.2 **passes**, the defect is III-B-local and III-A is untouched.

Manifest regeneration is permitted **only while no III-B capture exists**.

---

### `B-PILOT` — III-B pilot and the q_high technical gate

| | |
|---|---|
| **Unit of work** | one pilot capture (4 total) |
| **Durable completion evidence** | the item's observed value in `iii_b_pilot_receipt.json` |
| **Safe restart point** | the failed pilot unit |
| **Invalidation scope** | III-B only |
| **Reuse** | pilot units unaffected by the defect |
| **Never rerun unnecessarily** | the III-A pilot; the III-A production cohort |

**q_high failure procedure — follow exactly:**

1. Classify the failure. Is it the **predeclared technical** trajectory/window/FIR qualification
   gate? Only that gate may trigger the fallback.
2. If yes: run **exactly one** fallback re-pilot at `q = 0.15`. Record the trigger and its
   inputs in the pilot receipt.
3. If the fallback also fails: `III_B = SKIPPED` (`CLEAN_SKIP`). **III-A continues untouched.**
4. If the failure is anything else — undesirable model results, separation judged too easy or too
   hard, disappointing decoder output, weak effect size — **the fallback is forbidden**. That is
   `B_Q_FALLBACK_OUTCOME_DRIVEN`, a scientific violation requiring adjudication, not a repair.

**No further `q` search is permitted** beyond this single fallback.

---

### `B-GATE` — launch gate

| | |
|---|---|
| **Unit of work** | the decision |
| **Durable completion evidence** | `iii_b_launch_gate_receipt.json` recording every input and the verdict |
| **Safe restart point** | not resumable — the decision is made at most twice |
| **Invalidation scope** | none; a NO-GO is a `CLEAN_SKIP`, not a failure |

Before the 17:00 re-evaluation you may **free resources** or **complete a missing test or pilot**.
You may not extend the window, add a third evaluation, launch on Friday, or consult any
scientific outcome. After a second NO-GO, III-B is terminal (`CLEAN_SKIP`) and III-A proceeds
exactly as planned.

---

### `B-CAP` — III-B production capture

| | |
|---|---|
| **Unit of work** | one `(identity, q)` capture unit |
| **Durable completion evidence** | ledger `COMPLETE_VALIDATED_DURABLE` plus `durable_receipt.json` verified by read-back |
| **Safe restart point** | the next non-`COMPLETE` unit in the frozen order |
| **Invalidation scope** | III-B only. A III-B capture failure never invalidates a III-A capture |
| **Same-spec verification** | spec hash, path hash, noise hash, `q`, the cell's own target rows, fold |
| **Reuse** | every `COMPLETE_VALIDATED_DURABLE` III-B unit; **all** III-A units, always |
| **Never rerun unnecessarily** | the III-A `q = 0.05` `L4` cell — it is **reused, never recaptured** |

Retry semantics are identical to III-A `A7`: same frozen unit only; first technically valid
attempt kept; all failed attempts retained.

**Under time pressure, do not improvise.** Apply the frozen drop ladder (§29.6) and record the
level and its time/resource inputs in `iii_b_drop_level_receipt.json`.

---

### `B-EXT` — III-B extraction

| | |
|---|---|
| **Unit of work** | one `(capture unit × layer × slice)` array |
| **Durable completion evidence** | unit `COMPLETE` in the ledger with source and spec hashes |
| **Safe restart point** | the failed array unit |
| **Invalidation scope** | the affected III-B arrays. **III-A activations are never invalidated by a III-B extraction failure** |
| **Same-spec verification** | source capture hash **and** extraction spec hash both match |
| **Reuse** | `COMPLETE` units skipped; `DURABLE` re-sealed; `EXTRACTED` re-validated, not re-extracted |
| **Never rerun unnecessarily** | III-A's 750 arrays; a capture's forwards when only a write failed |

**The `q_mid` VIS re-inference is the special case.** It runs new forwards against **existing
III-A captures**. A failure there invalidates only those VIS arrays — never the III-A captures,
and never III-A's occluded activations. If time is short, drop `LEVEL_2` removes this work
entirely.

---

### `B-ORC` — oracle ledger

| | |
|---|---|
| **Unit of work** | one `(identity, q, tau)` cell |
| **Durable completion evidence** | `iii_b_oracle_validation_receipt.json` |
| **Safe restart point** | regenerate the ledger — it is deterministic and cheap |
| **Invalidation scope** | III-B analysis only |
| **Never rerun unnecessarily** | any capture or extraction; the oracle touches neither |

**If `B_ORACLE_MISMATCH` fires, check two things, in this order.**

1. **The affine form.** The most likely defect by far is using `sigma2 = q*dt*(tau + c)` below
   τ = 8, which returns a **negative variance** — for `τ ≤ 4` in `LEFT_TO_RIGHT` and for
   `τ ≤ 3` in `RIGHT_TO_LEFT` (the boundary is **direction-specific**; `τ = 4` is *positive*
   right-to-left) — and is wrong by up to 1e5 percent at τ = 1. The exact cumulative-mass form is
   mandatory.
2. **Tap normalization.** If the affine form is not being used and `S(τ)` is still off by ~1e-9,
   the taps were not fsum-normalized at load (`FIR_KERNEL_NOT_NORMALIZED`). `fsum` of the
   `LEFT_TO_RIGHT` taps is `0.9999999999`, not 1.

Both are code repairs. Fix and regenerate the ledger; **no captures are affected**.

---

### `B-U2` and `B-U3` — analysis

| | |
|---|---|
| **Unit of work** | one statistic |
| **Durable completion evidence** | the statistic's entry in the corresponding results file |
| **Safe restart point** | recompute the failed statistic **from the U2 prediction lock** |
| **Invalidation scope** | III-B analysis only; never backwards |
| **Same-spec verification** | lock hash and bootstrap seed match the freeze package |
| **Reuse** | the U2 prediction lock, always — it is never regenerated to fix a statistics bug |
| **Never rerun unnecessarily** | extraction; capture; the oracle ledger |

**Two frozen rules that a statistics bug must never be "fixed" by changing.**

1. **The positivity guard.** `sigma_tilde = max(sigma_hat, 1e-4 blocks)` applies to coverage,
   both NLL variants, log axes and density scores — and to **nothing else**. U2, U3, scale
   agreement and monotonicity use **raw** `sigma_hat`. If negative `sigma_hat` appears, report
   `fraction_clipped`, `count_negative` and `min_sigma_hat`; do **not** change `EPS`, do **not**
   widen the guard's scope, and do **not** re-fit. Changing it after prediction lock is
   `B_CALIBRATION_POSITIVITY_RULE_ALTERED` and is terminal.
2. **The inference procedure.** Intervals are ordinary unadjusted two-sided 95% percentile
   intervals and report effect size only; Holm-adjusted **p-values** decide significance. If you
   find yourself writing "Holm-adjusted CI", stop — that names no procedure and is
   `B_INFERENCE_PROCEDURE_MISMATCH`.

**A U2-S2 that looks surprisingly strong deserves one specific check**: confirm the
residualization is on the **30 `τ × direction` cells**, not on τ alone. τ-only conditioning
leaves a direction confound that a decoder with zero `q` sensitivity can exploit
(`B_U2_S2_CONDITIONING_MISMATCH`).

A statistics defect is repaired by fixing the statistics code and recomputing from the **same
locked predictions** and the **same seed**. Regenerating the lock to fix a statistics bug is a
category error and destroys III-B's prospective guarantee, exactly as in III-A.

**A null result is not a defect.** If U2 does not pass, that is `SCIENTIFIC_NULL` — record it,
report it under the frozen ladder rung, and close. Do not add analyses, change the target scale
to `log σ`, extend the τ range, or re-tune anything. All of those are §9.2 scientific changes.

---

### `B-LOCK` — closure

| | |
|---|---|
| **Unit of work** | the module |
| **Durable completion evidence** | `iii_b_closure_receipt.json` |
| **Safe restart point** | recompute from the results files |
| **Invalidation scope** | none; terminal for III-B |

III-B closes as `RESULT_LOCKED`, `CLEAN_SKIP`, or `TERMINALLY_ADJUDICATED`. All three are valid
terminal states. **III-A closure is never contingent on any of them.**

---

### Deadline drop — the procedure

When a frozen clock trigger fires or the Thursday 20:00 absolute stop approaches:

1. Read the **time**, the **technical completion state**, and the **available resources**. Read
   nothing else. A scientific outcome may not be consulted (`B_DEADLINE_DROP` is technical, and
   consulting an outcome to choose a level is a scientific violation).
2. Select the highest drop level that fits, in order: `NORMAL` → `LEVEL_1` → `LEVEL_2` →
   `LEVEL_3` → `LEVEL_4` (`CLEAN_SKIP`).
3. Record the level, its inputs, and the timestamp in `iii_b_drop_level_receipt.json`.
4. **Preserve everything already captured and extracted.** A drop reduces future scope; it never
   discards completed valid work.
5. At `LEVEL_1`, U2-S3 becomes non-estimable and the U2 Holm family reduces to **two** — this is
   frozen prospectively in §29.6 and is the only permitted family change.
6. **Verify III-A is unaffected**, and continue III-A on its own schedule.

---

### Cross-module scenarios

**A shared-rig failure during III-B capture.** Stop III-B. Assess whether III-A capture is
affected. If III-A is still capturing, III-A has priority for the rig — always. Resume III-B only
if the launch-gate conditions still hold.

**III-A slips while III-B is running.** Stop III-B immediately and return the rig to III-A. This
is not a judgment call: launch-gate requirement 8 already forbids III-B from threatening the
III-A result lock, so a slip means the gate's premise has failed.

**A defect found in III-B that also affects III-A.** Escalate to §9 at once. Fix, re-validate
III-A, re-run III-A's invalidated units. III-B waits, and is dropped if the delay consumes its
window.

**III-B incomplete at Thursday 20:00.** Apply the drop ladder, close III-B as
`TERMINALLY_ADJUDICATED` or `CLEAN_SKIP`, and report what was and was not measured. **Do not
extend into Friday.**
