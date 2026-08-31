# Experiment III Pre-Execution Readiness Audit

**Audit date:** 2026-08-31
**Auditor:** independent pre-execution audit, read-only
**Controlling authority:** `v1.6` (Amendment 3, P0 operational completeness)
**Repository HEAD at audit:** `d0ad665887b56a898784a701cee13214a8b20c9a`
**Lifecycle boundary assessed:** `A2 == PASS` → provision and qualify the live capture host (`A3`)

---

## 1. Executive Verdict

```
READINESS_VERDICT = NOT_READY_FOR_CAPTURE_HOST_PROVISIONING
```

| Severity | Count |
|---|---|
| **BLOCKER** | **1** |
| HIGH | 5 |
| MEDIUM | 5 |
| LOW | 6 |
| INFORMATIONAL | 4 |

**Host provisioning should not begin yet.** The blocker is not about the host, and it is not a
hardware question. It is that the premise on which this transition rests — *"implementation and
validation are complete"* — is **not true**. Two `A1` implementation tasks (`I07` RVE and P0
machinery, `I08` sentinel machinery) are recorded `COMPLETE` in
`implementation_completion_receipt.json`, but their frozen completion conditions are not met: the
P0 **measurement** half is built and tested, while the P0 **analysis** half — mask derivation, RVE
table, bootstrap, the nine validity rules, the deterministic triple search, and the sentinel
batch-boundary check — exists only as unit-tested library functions with **zero production call
sites**. `scripts/experiment_iii/run_p0_rve_calibration.py --execute` would capture all 252 units
and 4,032+ frames and then terminate without producing seven of `A4`'s eight expected outputs,
including `P0_SELECTION_RECEIPT`, which is `A4`'s exit condition.

The consequence is the specific hazard Amendment 3 §1 was written to prevent. If this is
discovered during `A4`, the remaining P0 analysis would be written **with measurements in hand** —
an outcome-adjacent implementation choice on the code path that decides which materials become
`L1`/`L2`/`L3`. That is a §9.2 amendment trigger, not a bug fix.

Procuring the hardware is itself harmless, and nothing found here suggests the frozen science is
wrong. But `A3` should not be run either until finding **F-05** is settled, because the
`environment_receipt.json` that `A3` writes on the new host would record an incorrect
`authority_freeze_commit`, permanently mis-binding the first host artifact of the live program.

What is genuinely solid is worth stating plainly: the authority hashes reproduce exactly, the
cohort is byte-stable and correctly salt-pinned to `v1.5`, all Amendment 3 numeric bindings
reproduce, the RVE mathematics and the mod-side physical scene semantics are correct and carefully
written, and 594/594 tests pass at the recorded source closure. The gap is integration and
evidence-binding, not science.

---

## 2. Audit Scope and Boundary

The program's intended next operational sequence is:

```
provision the real headless Linux capture host
  → run A3 (ENVIRONMENT_PREFLIGHT) on that host
  → qualify the capture runtime
  → execute P0 (A4, P0_VISIBILITY_CALIBRATION)
```

This audit occurs strictly **before** that sequence. Its question is not whether prior receipts say
`PASS`. It is:

> If an independent engineer received this frozen authority and this repository today, would they
> conclude that all design, implementation, validation and evidence work that *should* precede live
> experimental execution is complete, coherent and reproducible?

The audit was conducted read-only. No source, authority, or receipt was modified. No live
experimental evidence was generated. No Minecraft, Xvfb, GPU, CUDA, SageMaker or MineWorld
execution occurred. The only write performed was this document.

Commands run were limited to inspection and re-validation: `git`, `sha256sum`, source reading, JSON
manifest parsing, deterministic CPU reproduction of frozen bindings, and one full `pytest` run of
`tests/experiment_iii/`.

---

## 3. Controlling Authority and Repository State

All hashes below were **recomputed during this audit**, not copied from receipts.

| Quantity | Value | Reproduced |
|---|---|---|
| `AUTHORITY_VERSION` | `v1.6` | ✅ |
| `AUTHORITY_SHA256` (human, `.md`) | `62519701…97ab4c` | ✅ exact |
| `MACHINE_AUTHORITY_SHA256` (`.json`) | `d9de2616…a50609` | ✅ exact |
| `PHASE0_DESIGN_SHA256` | `be3ccd97…9c8e4c` | ✅ |
| Authority freeze commit (actual) | `a1f5dd1a959ff477edbf469cd12bb4db606371ea` | ✅ in history |
| Implementation checkpoint | `d0ad665887b56a898784a701cee13214a8b20c9a` | ✅ = HEAD |
| `SOURCE_CLOSURE` | `b35a125f…a938c252` | ✅ exact match to reported |
| Working tree | clean except two untracked dirs | see §5 |
| Test suite | **594 passed, 0 failed, 0 error, 0 skipped** in 282.6 s | ✅ independently re-run |

Authority package: 20 files in `docs/experiment_iii/final_authorities/` plus a 8-file `final_audit/`
subtree. The human authority (`.md`) and machine authority (`.json`) both reproduce their bound
hashes bit-exactly, so there is **no authority drift**.

Amendment chain `v1.4 → v1.5 → v1.6` is represented coherently:

- `v1.4` = `993e5859…` freeze `e86347b`
- `v1.5` = `3d116d97…` freeze `3fd66ed`
- `v1.6` = `62519701…` freeze `a1f5dd1`

---

## 4. Independently Reconstructed Expected State

Before inspecting the implementation, the expected state was derived from
`EXPERIMENT_III_LIFECYCLE.json` (29 states), `IMPLEMENTATION_TASK_GRAPH.json` (44 tasks),
`EXPECTED_ARTIFACT_INVENTORY.json` (99 artifacts) and the canonical authority, without reference to
any completion report.

The lifecycle places the boundary precisely. `A0 AUTHORITY_IDENTITY → A1 IMPLEMENTATION →
A2 STATIC_VALIDATION → A3 ENVIRONMENT_PREFLIGHT → A4 P0_VISIBILITY_CALIBRATION → A5 P1 → A6 P2 →
A7 PRODUCTION_CAPTURE → …`. We sit immediately after `A2`.

**What must already be complete.** All 20 `A1` tasks (`I01`–`I18`, plus `IB02`/`IB03` which gate
`I02`), and both `A2` tasks (`I19`, `I20`). Two task definitions are decisive for this audit and are
quoted from the frozen graph:

> **`I07` — RVE and P0 machinery** · `lifecycle_stage: A1`
> `files_expected_to_change: [src/…/rve.py, scripts/experiment_iii/run_p0_rve_calibration.py]`
> *completion_condition:* "RVE computable **end to end** on fixtures; the ABBA capture routine,
> shared L0 mask, and **deterministic triple search are implemented with all nine validity
> rules**."

> **`I08` — Sentinel machinery** · `lifecycle_stage: A1`
> *completion_condition:* "Three frozen sentinel placements **measured at every condition-batch
> boundary** against the frozen repeatability envelope; failure invalidates only the affected
> unmodeled batch."

Against these, `I21` — the task that actually runs P0 — is bound to `A4` and carries
`change_matrix_items: []` with `files_expected_to_change: ["docs/experiment_iii/p0/"]`. **`I21`
produces data, not source.** The authority therefore requires every line of P0 code, analysis
included, to exist at `A1`. This is the reconstruction that determines the blocker below; it was
derived from the task graph before the implementation was read.

**What must intentionally still be incomplete.** `A3` environment receipt (needs the real host);
`A4`/`I21` P0 data; `A5`/`I22` P1 data; `A6` P2 freeze; `A7`–`A19` production, extraction and
analysis outputs; every III-B runtime stage (`B-PILOT` onward). No GPU or MineWorld artifact may
exist. `POOL_*` device identities cannot exist until the host does.

**What must already be frozen.** All six Amendment 3 bindings: the nine placements, the derived
bootstrap seed, the tunable-free `L0_noise_threshold_p` procedure, the noise-relative background
tolerance, the sentinel selection rule and envelope formula, and the withdrawn/replaced capture
liveness contract.

**What must not exist.** Any scientific outcome; any production capture schedule naming `L1`/`L2`/
`L3` materials, since those are what `A4` decides.

---

## 5. Actual State Observed

`HEAD = d0ad665`, branch `experiment/exp3-graded-partial-observability`, three commits after the
`v1.6` authority freeze (`a1f5dd1` → `1378fd0` capture layer → `d0ad665` A3 capture authorization).

Tracked Experiment III surface: 56 modules in `src/mineocclude/experiment_iii/` (15,287 lines),
22 scripts in `scripts/experiment_iii/`, 19 test modules (594 tests), 23 Java files in
`fabric/mineocclude-mod/`. Artifact directories `a1_receipts/` (8), `cohort/` (9), `receipts/` (1),
`runtime/` (2), `p1/` (1).

**Two untracked directories exist:**

- `docs/experiment_iii/draft_authority/` — 7 files of raw audit output. The authority README
  explicitly describes this location as working material, superseded by the validation report. Not
  authority; see F-15.
- `docs/experiment_iii/capture/capture_schedule.json` — **a 125-unit production capture schedule
  bound to the superseded `v1.5` authority and naming concrete `L1`/`L2`/`L3` materials.** See
  F-04. This is the single most surprising artifact found.

One `.pyc` without a source file (`test_placements_and_host_preflight`) was traced to a legitimate
`R062` rename at `1378fd0` into `test_host_preflight.py`. Not a defect.

---

## 6. Authority / Provenance Integrity

**Sole controlling authority — confirmed.** `v1.6` is the only authority tree, its hashes reproduce
exactly, and the freeze commit `a1f5dd1` is immutable in history. Human and machine authority
correspond.

**Cohort salt pinning — correct, and worth defending.** `cohort_qualification_receipt.json` records
`authority_sha256 = 3d116d97…`, which is `v1.5`, not the current `v1.6`. This is **not** drift. It
is the `COHORT_SALT_AUTHORITY_SHA256` mechanism working exactly as designed: the master salt is
pinned to the authority under which `A1` prospectively materialized the population, so an
operational amendment cannot regenerate it. The salt was reproduced from source during this audit:

```
COHORT_SALT_AUTHORITY_SHA256 = 3d116d97…  (v1.5, pinned)
master_salt()                = 87aa30a57ce7113c172e3e1207088d889fef63b4f51447e1a3d19a1d09354d32
receipt master_salt          = 87aa30a57ce7113c172e3e1207088d889fef63b4f51447e1a3d19a1d09354d32   ✅
```

No circular authority/hash dependency was found: the bootstrap seed correctly binds the *immutable
Phase 0 design hash* rather than the current authority hash, so it survives later amendments
unchanged.

**One real provenance defect (F-05).** `authority.py:127` still reads
`AUTHORITY_FREEZE_COMMIT = "3fd66ed…"` — the **`v1.5`** freeze commit — under a comment that says
"Rewritten by the `v1.6` successor freeze commit once it exists." The `v1.6` freeze commit does
exist (`a1f5dd1`); the rewrite never happened. `PREDECESSOR_AUTHORITY_FREEZE_COMMIT` holds the same
value, so current and predecessor are degenerate. Both the `A1` and `A2` receipts consequently
record `authority_freeze_commit = 3fd66ed`, and `host_preflight.py:542` will write the same wrong
value into the `A3` `environment_receipt.json` on the new host.

---

## 7. Cohort and Target Integrity

**The frozen cohort is the cohort the current authority specifies.** Byte-level comparison across
the two authority freeze commits confirms the `v1.5 → v1.6` amendment did not change cohort bytes:
the cohort artifacts did not exist at `3fd66ed` (materialized later at `cdda8e7`), and every file's
bytes at `a1f5dd1` are **identical** to the working tree today.

| Artifact | `a1f5dd1` (v1.6 freeze) | worktree | Match |
|---|---|---|---|
| `production_identity_manifest.jsonl` | `336a3bac…` | `336a3bac…` | ✅ |
| `folds.json` | `cf72e750…` | `cf72e750…` | ✅ |
| `identity_priority_order.json` | `21dac3dd…` | `21dac3dd…` | ✅ |
| `cohort_qualification_receipt.json` | `5b2d878b…` | `5b2d878b…` | ✅ |

The qualification receipt records all 12 gates by name, `candidate_index_bound_per_direction = 2000`,
`STRICTLY_ASCENDING_INDEX_PER_DIRECTION_LTR_THEN_RTL` generation order, 25 admitted (13 LTR / 12 RTL),
545 rejected with per-candidate first-failing-gate provenance, and explicit
`admission_reads_outcomes = false` / `admission_reads_activations = false` /
`admission_reads_rendered_frames = false`. Gate 12 (all-`q`) has its own receipt, and the `q=0.05`
bit-identity regression (`IB03`/`D.2`) has an `A1` gate copy. The population is sound.

**Target/FIR pipeline.** `fir.py` (549 lines), `target_manifest.py`, `extent_geometry.py` and the
`_aprime_extent_geometry.py` port are present with a reproduced `FIR_KERNEL_RECOVERY_RECEIPT`, and
their 24 + 15 tests pass. No second, divergent FIR implementation was found on the Experiment III
path — FIR math has a single home. No historical target selector is reachable from the current
runtime path.

---

## 8. P0 Scientific Readiness

**Every Amendment 3 binding reproduces from source.** These were recomputed, not read from receipts:

| Binding | Authority value | Reproduced |
|---|---|---|
| Nine placements (world-x) | `-2.0 … +2.0` step `0.5`, lane `y=4, z=6` | ✅ |
| `P0_PLACEMENTS_SHA256` | `5676aa3371fcc481f89c709d8be81e2b14932f550b94ce44a42b2617420a84b6` | ✅ exact |
| `P0_BOOTSTRAP_SEED` | `1530570907966297797` | ✅ exact |
| Sentinel indices | `[0, 4, 8]` (left/centre/right) | ✅ |
| Candidate roster | 12 stained glass + stone anchor + L0 = 14 conditions | ✅ |

**The RVE mathematics is correct and complete.** `rve.py:evaluate_triple` implements all nine
validity rules of §7.5 — three zone rules, two adjacent separations, strict order stability
(≥8 placements), `L3` SNR, replicate CV, background — and gates the bootstrap behind the separation
rules. `select_ladder` performs the exhaustive 1,320-permutation search, minimizes squared distance
to the frozen `(0.725, 0.425, 0.165)`, breaks ties lexicographically by registry ID, re-seeds
per triple so the result is order-independent, refuses candidates outside the twelve-item roster
with `P0_CANDIDATE_ID_UNSUPPORTED`, and returns `NO_VALID_LADDER` rather than an approximate ladder.
This is careful, faithful work.

**But none of it is reachable.** This is the blocker (F-01). `run_p0_rve_calibration.py` imports
from `rve` **only the constants** — `ABBA_BLOCKS`, `LADDER_ZONES`, `ADJACENT_SEPARATION_MIN`,
`L3_SNR_MIN`, `REPLICATE_CV_MAX`, `BOOTSTRAP_REPLICATES`, `TARGET_RVE_POINTS`, `PLACEMENT_COUNT` —
and not one analysis function. Call-site census across `src/` and `scripts/`:

```
srgb_to_linear                0     robust_median_image           0
placement_mask                0     split_half_noise              0
outside_mask_split_half_noise 0     excess_energy                 0
aggregate_placement           0     select_ladder                 0
derive_envelope               0     evaluate_batch_boundary       0
masked_energy                 1  ← internal to rve.py
aggregate_condition           1  ← internal to rve.py
background_residual           1  ← internal to rve.py
evaluate_triple               1  ← internal to rve.py
```

Every non-zero count is `rve.py` calling itself. `sentinels.py` is imported by **tests only**.

Consequently, of `A4`'s eight expected outputs, seven have **no producer anywhere in the
repository**: `P0_IMAGE_INVENTORY`, `P0_RVE_TABLE`, `P0_BOOTSTRAP_RESULTS`, `P0_MASK_INVENTORY`,
`P0_SELECTED_LADDER`, `P0_SELECTION_RECEIPT`, `P0_SENTINEL_ENVELOPE`. A repository-wide search for
these names finds them only as *inputs* consumed by the P1 and production runners
(`--ladder P0_SELECTED_LADDER json`). `A4`'s exit condition — `P0_SELECTION_RECEIPT with
P0_RESULT == P0_PASS` — is unreachable.

Three `A4` blocker codes also have no producer: `RVE_SNR_INSUFFICIENT`, `RVE_ORDER_UNSTABLE`,
`RVE_BOOTSTRAP_LOWER_BOUND_NOT_POSITIVE` (their rules are evaluated as booleans inside
`evaluate_triple`, but no code path raises them).

**No placeholder values remain in the frozen P0 rules themselves.** All six previously deferred
items are numerically or algorithmically bound, and the two derivations that can only produce
numbers after P0 (the sentinel envelope) correctly freeze the *formula* now and bind the *values*
in P2. That part of Amendment 3 is discharged properly.

---

## 9. Live Capture Runtime Readiness

The capture layer (`capture_runtime.py`, `capture_driver.py`, `capture_liveness.py`,
`capture_schedule.py`) was traced end to end: manifest → runner → `RuntimeConfig` → `CaptureRuntime`
→ server/client processes → `/mineocclude p0` → frames → `FrameSink` → liveness → `P0CampaignState`.

**Genuinely good.** Host portability is real: every path is data in `RuntimeConfig`, no host is
assumed, the command channel is the server's stdin pipe rather than a POSIX FIFO, and the display is
a declared strategy. Host *qualification* is correctly separated from portability —
`qualify_capture_host` admits only the Linux/Xvfb/llvmpipe software-rendering stack and refuses an
interactive compositor with a stated reason. `gpu_required: False` and `mineworld_loaded: False`;
no SageMaker path is required. Capture and extraction are cleanly separable. The `A3` receipt fails
closed: an unqualified renderer authorizes **no** stages (`authorized = []`), and
`CAPTURE_HOST_STAGES = ("A4", "A5_CAPTURE", "A7")` correctly excludes `A9`. `P0CampaignState`
refuses to resume across an authority or source-closure change. Production capture is gated behind
`P2_PREREQUISITE_NOT_PASSED` and refuses to build a schedule without a real `--ladder`. `run_p1_pilot`
refuses to substitute placeholder materials. These gates are correct and were verified by reading
them, not by their names.

**The evidence chain is not.** Four of the seven `required_evidence` items in the frozen
`capture_liveness_contract` are satisfied by construction rather than by observing the apparatus
(F-03). In `capture_driver.FrameSink.frame_records`:

```python
records.append({
    "tick": first_tick + index,          # ← enumerate(), not the server tick
    "width": FRAMEBUFFER_WIDTH,          # ← the constant, not the PNG header
    "height": FRAMEBUFFER_HEIGHT,        # ← the constant, not the PNG header
    "read_succeeded": True,              # ← hard-coded
    ...})
```

`verify_tick_integrity` then checks these fabricated ticks for monotonicity, uniqueness and
step-one advance — properties `enumerate()` guarantees, so the check can never fail on real data.
`verify_frame_dimensions` compares the constants against themselves, so
`ENV_FRAMEBUFFER_SIZE_MISMATCH` can never fire from a capture even though `FrameCapture.java` warns
that a HiDPI surface yields a different framebuffer size. `probe.tick_advanced` is likewise always
true.

This matters because **the real evidence is already on disk and is simply not read**. The mod writes
`client_tick.jsonl` per episode carrying the actual `server_tick`, `render_frame_idx` and
`queue_depth_at_capture` (direct tick/frame desync evidence), and `capture_complete.json` carrying
`frame_count`, `pending_writes`, `writer_errors` and `drained`. The Python layer reads none of them.
So the audit question "can tick identity and framebuffer evidence silently disagree?" has an
uncomfortable answer: they cannot disagree, because tick identity carries no information.

Two further runtime defects: the server and client are launched with `stdout=subprocess.PIPE` and
nothing drains those pipes after startup (F-06) — over a 252-unit campaign the OS pipe buffer will
fill and block the JVM; and `CaptureRuntime.send()` never reads the server's reply, so a
`p0 REFUSED:` response is invisible and surfaces 180 s later as a timeout under the wrong blocker
code (F-08).

---

## 10. Fabric / Physical Scene Integrity

**The mod side is the strongest part of the system.** `p0Cmd` is correct on every point the
authority cares about: the wall follows the condition while target presence is an independent axis
(so the wall material is identical between the present and absent halves of a cell — without which
`D(c,p,b)` would measure the wall, not the target); L0 reaches `Scene.NO_WALL` and never grows a
wall; `NO_SHEEP` preserves the wall and material; motion is exactly zero (drift `0.0`, process noise
`0.0`) so the scene is the static settled scene RVE is defined on; an unsupported registry ID
**refuses** the episode rather than defaulting to stone; and a placement outside the lane is
refused. `ArenaBuilder` takes the wall state from `cfg.condition.wallState()`, never a hard-coded
`Blocks.STONE`, "so the builder cannot disagree with the config, the cache key or the receipt."

Arena cache invalidation is correct and was clearly written against a real past failure:

```java
// The material MUST be part of the identity. Omitting it let a
// stone->glass switch hit the cache and leave the previous wall standing,
// silently capturing a whole batch under the wrong condition.
String key = cfg.layoutId + "|" + cfg.scene + "|" + cfg.condition.cacheKeyFragment() + …
```

Frame filenames are `String.format("%06d.png", idx)` — zero-padded, so the Python side's
`sorted(glob("*.png"))` is numerically correct. The mod wipes `episodeDir` on episode start, so
stale frames from a failed attempt cannot be re-consumed on resume. Both of those were checked
specifically because they are classic silent-corruption vectors; both are handled.

**The gap is the independent pixel-level check (F-02).** Amendment 3 §3f freezes four transition
probes, `WALL_MATERIAL_CHANGE` among them, and the machine authority lists it in
`capture_liveness_contract.transition_probes`. `capture_liveness.TRANSITION_KINDS` declares it.
`capture_driver.prepare_condition()` computes `material_changed` and `probe_required`. And then
nothing uses them: `capture_p0_unit` constructs probes only for target present↔absent transitions,
and `verify_unit_liveness` **explicitly excludes** the kind from its required set:

```python
required = {kind for kind in TRANSITION_KINDS if kind != "WALL_MATERIAL_CHANGE"}
```

A repository-wide search finds `LivenessProbe("WALL_MATERIAL_CHANGE", …)` constructed **only in a
unit test**, and there incidentally, to exercise the tick-advance guard.

The campaign manifest nevertheless asserts `"wall_material_transitions": 14` and a rationale reading
"makes every transition an explicit liveness probe," and the driver's own module docstring warns:
*"a cache key is a claim about intent; the probe is evidence about pixels. Without it a stale wall
can stand through a whole batch with every receipt still green."* That is an accurate description of
the current state of the code.

This is the divergence path the audit was asked to look for: a wall stuck at the previous material
would still show present/absent pixel differences and therefore pass every probe that *is* emitted,
while corrupting all 18 units of that condition. The mod-side cache key makes this unlikely, which
is why this is HIGH and not the blocker — but the authority froze a second, independent check
precisely because the first one is intent-level, and that second check is absent.

---

## 11. Capture Liveness and Recovery

**Does the mechanism distinguish a legitimately static scene from a frozen renderer?** Partly, and
for the right reason where it works. Amendment 3's withdrawal of the universal byte-duplicate rule
is correct and correctly implemented: repeated bytes within one settled static state are recorded as
a diagnostic and are explicitly not a failure, so P0 will not falsely reject valid static frames.
The transition probes compare **real PNG bytes** across present↔absent boundaries, so a fully frozen
renderer *is* caught. Over a multi-hour campaign the design will not accept a dead renderer outright,
nor falsely reject legitimate static frames.

What is weakened is defence in depth. The `MANDATORY_PRE_CAPTURE_LIVENESS_PROBE` is not a
pre-capture probe (F-07): it is synthesized *after* all four ABBA slots are captured, from
`results[0]` versus `results[1]`, which under ABBA already differ in target presence. It therefore
duplicates the first target-transition probe rather than providing the independent controlled check
the authority names, and it cannot prevent a wasted unit. Combined with F-03, a run can produce a
liveness receipt reporting `passed: True` with `SERVER_TICK_MONOTONIC_STEP_ONE` and
`FRAMEBUFFER_DIMENSIONS_640x360` "proven" from data the Python layer generated itself.

**Recovery.** The durability design is sound: `write_json_atomic` throughout, `P0CampaignState`
keyed on the `A4` resume unit `(condition, placement, block)`, `COMPLETE_VALIDATED_DURABLE` gating,
fail-closed refusal on authority or source-closure drift, and `mark_attempt` written so as never to
overwrite a completed unit. Two gaps: the runner never calls `mark_attempt` (F-10), so `A4`'s
"all attempts retained" rule is not actually satisfied on the operational path; and
`wait_for_frames` polls for file *count* while frames are written asynchronously on a background IO
thread, guarded only by a 1 s sleep, ignoring the `drained` / `pending_writes` / `writer_errors`
fields the mod already publishes (F-11).

---

## 12. Future MineWorld / Extraction Readiness

No GPU-host `A3` evidence is expected yet and none was required. The question asked was whether the
*local* implementation holds what the later extraction stage will need.

It largely does. `run_extraction.py` is honest about its gate — "CPU/plan only in this build.
Loading MineWorld and running inference is stage `A9` and is NOT authorized here" — and refuses to
run inference without an injected decoder. `activation_store.py` (365 lines), `extraction.py`,
`slices.py` and `validate_extraction.py` are present; the validator re-reads every persisted array's
bytes and re-derives shape, dtype, byte size, finiteness and SHA-256 rather than trusting the
inventory, which is the right posture. The 33 tests in `test_extraction_and_store.py` cover the
discriminations the authority cares about — wrong frame, wrong slice, extra forward, wrong layer,
wrong dtype, wrong byte count, wrong shape.

`A3` correctly declines to authorize `A9` on a capture-only host, and
`resource_policy` in the environment receipt pins `SAGEMAKER_STARTED`, `GPU_USED`, `CUDA_USED`,
`MINEWORLD_MODEL_LOADED` and `MINEWORLD_INFERENCE_RUN` all to `False`. No MineWorld or GPU artifact
exists anywhere in the tree. This is the expected and correct state.

---

## 13. Analysis Pipeline Readiness

`representations.py`, `prediction_lock.py`, `statistics.py`, `baselines_pixel.py`,
`baselines_motion.py`, `readout.py`, `folds.py` and `adjudication.py` are implemented and tested
(33 + 16 + 64 tests across the relevant modules). The safeguards are real, not nominal:
`run_primary_analysis.py` refuses to run before the prediction lock is sealed, emits no overall
pass/fail verdict, and never inspects a scientific outcome on import; `lock_predictions.py` refuses
to seal on a missing or duplicated `(identity, condition, row, model)` cell and refuses entirely once
statistics have been opened. Held-out identity grouping and fold structure are frozen in
`folds.json` and byte-stable.

The whole chain is `plan-only` pending real data, which is correct at this boundary — but note that
this means the analysis pipeline's *integration* is, like P0's, proven per-module rather than
end-to-end. That is legitimate for `A11`+ (which needs real captures); it is **not** legitimate for
`A4`, which is why F-01 is a blocker and this section is not.

---

## 14. Test and Validation Adequacy

594 tests pass at the recorded source closure — independently re-run, `0 failed / 0 error /
0 skipped`. Coverage is genuinely broad and many tests are properly discriminating: the frozen-
renderer test asserts `CAPTURE_STALE_FRAME` fires when ticks advance but pixels do not; duplicated
and missing tick identities each fail with `TIMING_CARDINALITY_MISMATCH`; a unit with no mandatory
probe fails closed; the static-scene test proves repeated bytes are *not* treated as staleness.

The weakness is not count, it is **direction**: several tests mirror the implementation rather than
the authority, and therefore cannot detect the gaps found here.

- **No test asserts that the driver emits a `WALL_MATERIAL_CHANGE` probe when the material changes.**
  The kind appears in tests only as an incidental argument. F-02 is invisible to the suite.
- **No test asserts that `run_p0_rve_calibration.py --execute` produces `P0_SELECTION_RECEIPT`** or
  any other `A4` output. `I07`'s own listed gate, "RVE computable end to end," is tested on fixtures
  at the function level only. F-01 is invisible to the suite.
- **B.10 (artifact inventory completeness) is tautological.** It feeds `stage_exit_check` the
  inventory's own `path_or_pattern` strings and asserts they are found. `stage_exit_check` never
  touches the filesystem, so the test cannot detect that no `A1` artifact is actually at its
  specified path (F-09).
- One module-scoped `pytest.skip("cohort not materialized")` (F-16) would silently drop the entire
  frozen-capture-order group if the cohort file were ever absent. The cohort is committed, so this
  does not fire today.

No test is excluded from the `pytest tests/experiment_iii/` entrypoint, and a clean clone would
collect the full suite: `conftest.py` puts `src/` on the path, all fixtures and cohort artifacts are
tracked, and there is no `pytest.ini`/`pyproject.toml` narrowing collection.

---

## 15. Artifact Inventory / Lifecycle Completeness

Classification derived from lifecycle timing, then checked against disk.

| Stage | Artifact class | Classification |
|---|---|---|
| `A0` | All 12 authority artifacts | **PRESENT_AND_VALID** (hashes reproduce) |
| `A1` | Cohort × 6, provenance receipts × 3, completion receipts × 2 | **REQUIRED_NOW_AND_PRESENT**, but **all 11 at paths other than the frozen inventory's** (F-09) |
| `A1` | `run_p0_rve_calibration.py` analysis half, sentinel batch-boundary wiring | **REQUIRED_NOW_BUT_MISSING** (F-01) |
| `A2` | `static_validation_receipt.json` | **PRESENT_AND_VALID** — the only artifact at its specified path |
| `A2`/`A1` | `authority_freeze_commit` field in both receipts | **PRESENT_BUT_STALE** (F-05) |
| `A3` | `environment_receipt_<host>.json` | **INTENTIONALLY_FUTURE** — requires the real host |
| `A4` | `P0_RVE_TABLE`, `P0_SELECTION_RECEIPT`, `P0_SENTINEL_ENVELOPE`, +4 | **INTENTIONALLY_FUTURE as data**, but their **producers are REQUIRED_NOW_BUT_MISSING** |
| `A4` | `p0_manifest.json`, `p0_campaign_plan.json`, `p0_placement_manifest.json` | **PRESENT_AND_VALID** (plan-mode outputs) |
| `A4` | Superseded uniform-partition placement derivation (`a3deb1df…`) | **SUPERSEDED_PROVENANCE_ONLY** — correctly dispositioned by Amendment 3 §3a |
| `A5` | `p1_pilot_plan.json` | **PRESENT_AND_VALID**; pilot data intentionally future |
| `A7` | `docs/experiment_iii/capture/capture_schedule.json` | **PRESENT_BUT_PREMATURE and STALE** — untracked, `v1.5`-bound, placeholder ladder (F-04) |
| `A8`–`A19`, `B-*` | Production, extraction, analysis, III-B runtime outputs | **INTENTIONALLY_FUTURE** |
| GPU / MineWorld | Any artifact | **CORRECTLY ABSENT** |

The path divergence deserves emphasis because it defeats the mechanism the authority built for
exactly this purpose. The frozen inventory specifies `data/experiment_iii/cohort/…` and
`data/experiment_iii/provenance/…`; the implementation writes `docs/experiment_iii/cohort/…` and
`docs/experiment_iii/a1_receipts/…`. Run against the real tree, `stage_exit_check("A1", …)` would
report all 11 `A1` artifacts missing. It is never run against the real tree.

---

## 16. Findings

### F-01 — BLOCKER — the P0 analysis stage is unimplemented and unwired, while `A1` reports it complete

**Affected surface:** `scripts/experiment_iii/run_p0_rve_calibration.py`,
`src/mineocclude/experiment_iii/rve.py`, `src/mineocclude/experiment_iii/sentinels.py`,
`docs/experiment_iii/a1_receipts/implementation_completion_receipt.json`

**Evidence.** `I07` (`lifecycle_stage: A1`) requires "RVE computable end to end … deterministic
triple search … implemented with all nine validity rules," and names
`run_p0_rve_calibration.py` among its expected files. `I08` (`A1`) requires sentinels "measured at
every condition-batch boundary." `I21`, the task that runs P0, is `A4` with
`change_matrix_items: []` and produces only `docs/experiment_iii/p0/` — so all P0 *code* belongs to
`A1`.

The runner imports only constants from `rve`. Production call-site count across `src/` + `scripts/`
is **0** for `srgb_to_linear`, `robust_median_image`, `placement_mask`, `split_half_noise`,
`outside_mask_split_half_noise`, `excess_energy`, `aggregate_placement`, `select_ladder`,
`derive_envelope` and `evaluate_batch_boundary`; the four non-zero counts are `rve.py` calling
itself. `sentinels.py` is imported by tests only. Seven of `A4`'s eight expected outputs have no
producer in the repository. `A4`'s exit condition, `P0_SELECTION_RECEIPT with P0_RESULT == P0_PASS`,
cannot be reached. `implementation_completion_receipt.json` nonetheless records `I07` and `I08` as
`status: COMPLETE` with `focused_test_result: PASS`, and `a1_tasks_complete: 20 / 20`.

**Why it matters.** `--execute` would drive all 252 units, spend hours of renderer time and produce
4,032+ frames, then stop with no mask, no RVE table, no bootstrap, no validity evaluation and no
ladder. The remaining analysis would then be written **with the measurements already in hand**, on
the code path that decides which materials become `L1`/`L2`/`L3`. Amendment 3 §1 classifies exactly
this — a choice affecting which pixels enter the support mask and therefore which materials qualify,
made with data available — as outcome-adjacent and requiring a §9.2 amendment rather than a repair.

**Blocks host provisioning:** **Yes.** The claim "implementation complete," which is the premise of
this transition, is false.

**Smallest repair direction:** complete `I07`/`I08` under `A1` rules — wire the existing, correct
`rve.py` and `sentinels.py` primitives into the `--execute` path so it emits the seven missing `A4`
artifacts; add the sentinel batch-boundary measurement at the 14 condition transitions; then
re-derive the `A1` receipt and re-run `A2`. No new science is required: the mathematics is already
written and tested.

---

### F-02 — HIGH — the frozen `WALL_MATERIAL_CHANGE` liveness probe is never emitted

**Affected surface:** `capture_driver.py:166-181` (`prepare_condition`), `capture_driver.py:240-275`
(`capture_p0_unit`), `capture_liveness.py:218`

**Evidence.** The machine authority lists `WALL_MATERIAL_CHANGE` in
`capture_liveness_contract.transition_probes`; Amendment 3 §3f names it as one of three probe points.
`TRANSITION_KINDS` declares it and `prepare_condition` computes `probe_required`, but no production
code ever constructs `LivenessProbe("WALL_MATERIAL_CHANGE", …)`, and `verify_unit_liveness`
explicitly removes the kind from its required set. The only construction site is a unit test. The
campaign manifest still asserts `wall_material_transitions: 14` and a rationale claiming every
transition becomes an explicit probe.

**Why it matters.** 13 of 14 conditions involve a material transition, and each condition covers 18
units. A wall left standing at the previous material would still produce present/absent pixel
differences and pass every probe that *is* emitted, corrupting a whole condition's RVE score and
therefore the ladder. The mod's cache key makes this unlikely; the authority froze an independent
pixel-level check precisely because the cache key is intent-level.

**Blocks host provisioning:** No — but it must be closed before the first P0 frame.

**Smallest repair direction:** emit the probe in `capture_p0_unit` when
`transition["probe_required"]`, comparing the last settled frame of the previous unit against the
first of this one, and include the kind in `required` when a transition occurred.

---

### F-03 — HIGH — four required liveness evidence items are self-certifying

**Affected surface:** `capture_driver.py:104-121` (`FrameSink.frame_records`),
`capture_liveness.py:139-186`

**Evidence.** `frame_records` sets `tick = first_tick + index` (from `enumerate`), `width`/`height`
from the `FRAMEBUFFER_*` constants, and `read_succeeded = True` unconditionally. `verify_tick_integrity`
then validates monotonicity, uniqueness and step-one advance — all guaranteed by `enumerate` — and
`verify_frame_dimensions` compares the constants against themselves. The apparatus already writes the
real evidence: `client_tick.jsonl` carries `server_tick`, `render_frame_idx` and
`queue_depth_at_capture`; `capture_complete.json` carries `frame_count`, `writer_errors` and
`drained`. Neither file is read by Python.

**Why it matters.** `SERVER_TICK_MONOTONIC_STEP_ONE`, `ONE_ACCEPTED_FRAME_PER_EXPECTED_TICK`,
`TICK_IDENTITIES_COMPLETE_AND_UNIQUE`, `FRAMEBUFFER_READ_SUCCEEDED` and
`FRAMEBUFFER_DIMENSIONS_640x360` are `required_evidence` in the frozen contract. As implemented they
are produced from constants, so tick identity and framebuffer evidence cannot disagree — not because
they were reconciled, but because one side carries no information. A HiDPI or misconfigured surface
cannot raise `ENV_FRAMEBUFFER_SIZE_MISMATCH` from a capture.

**Blocks host provisioning:** No — but it must be closed before the first P0 frame.

**Smallest repair direction:** join frames to `client_tick.jsonl` on `frame_path` for the real
`server_tick`, read the PNG header for actual dimensions, and derive `read_succeeded` from
`capture_complete.json`'s `writer_errors` / `drained`.

---

### F-04 — HIGH — an untracked, superseded-authority production capture schedule with a placeholder ladder

**Affected surface:** `docs/experiment_iii/capture/capture_schedule.json` (untracked)

**Evidence.** The file binds `AUTHORITY_SHA256 = 3d116d97…` — the superseded `v1.5` authority — and
names concrete materials for the three conditions P0 is supposed to select:
`L1 = white_stained_glass`, `L2 = lime_stained_glass`, `L3 = blue_stained_glass`, across 125 capture
units covering all 25 production identities. It sits at `DEFAULT_OUT` for
`run_production_capture.py`. The current code is fail-closed and its comment names this exact
incident: *"a schedule naming a placeholder material is indistinguishable from a real one and was
exactly how a pre-P0 dry run once acquired white/lime/blue."* The code defect was fixed; the
contaminated artifact was never removed. Because it is untracked it is invisible to git, to
`SOURCE_CLOSURE`, and to every provenance check.

**Why it matters.** Amendment 3 §3a explicitly dispositions the analogous superseded placement
derivation as "superseded engineering evidence; it must not enter P2." No equivalent disposition
exists for this file, and it is materially more dangerous: it names a full production ladder. No
current code path reads it, which is why this is HIGH rather than a blocker.

**Blocks host provisioning:** No.

**Smallest repair direction:** delete it, or move it under an explicitly-labelled superseded-evidence
path and record the disposition alongside Amendment 3 §3a's.

---

### F-05 — HIGH — `AUTHORITY_FREEZE_COMMIT` still names the `v1.5` freeze commit

**Affected surface:** `authority.py:127`, `host_preflight.py:152` and `:542`,
`build_completion_receipt.py:314`, `build_static_validation_receipt.py:406`

**Evidence.** `AUTHORITY_FREEZE_COMMIT = "3fd66eddfce017078b6af2774a381077759b98a0"` is `v1.5`'s
freeze commit, under the comment "Rewritten by the `v1.6` successor freeze commit once it exists."
The `v1.6` freeze commit is `a1f5dd1a959ff477edbf469cd12bb4db606371ea`.
`PREDECESSOR_AUTHORITY_FREEZE_COMMIT` holds the identical value. Both receipts on disk record
`authority_freeze_commit = 3fd66ed…` **and** `predecessor_authority_freeze_commit = 3fd66ed…`.

**Why it matters.** Every operational artifact mis-names the commit that froze the authority it ran
under, and current/predecessor provenance is degenerate. `host_preflight.py:542` writes the same
value into `environment_receipt.json`, so the first artifact produced on the new capture host would
carry it. The constant is also mixed into the durable round-trip probe payload
(`host_preflight.py:152`), so the `A3` durability evidence is bound to the wrong generation.

**Blocks host provisioning:** **Effectively yes for running `A3`** — the receipt would be wrong at
birth. It does not block procuring hardware.

**Smallest repair direction:** set `AUTHORITY_FREEZE_COMMIT = a1f5dd1…` and
`PREDECESSOR_AUTHORITY_FREEZE_COMMIT = 3fd66ed…`. Note this is a source change and therefore
invalidates the `A2` receipt, which must be re-run — best done together with F-01's repair.

---

### F-06 — HIGH — undrained `subprocess.PIPE` stdout will deadlock the JVM mid-campaign

**Affected surface:** `capture_runtime.py:245-300` (`start_server`, `start_client`,
`_await_markers`)

**Evidence.** Both processes are launched with `stdout=subprocess.PIPE` (server also
`stderr=STDOUT`). `_await_markers` reads until a readiness marker, then returns. No thread or loop
drains either pipe thereafter, and there is no `threading` import in the module.

**Why it matters.** When the OS pipe buffer fills (typically 64 KiB), the writing process blocks on
`write`. A Minecraft server logging across 252 units will exceed that within minutes. The campaign
would hang with no blocker code, no timeout and no diagnostic — the failure mode is an unexplained
stall hours into an unattended run, and `wait_for_frames` would eventually raise
`TIMING_CARDINALITY_MISMATCH`, which misattributes the cause.

**Blocks host provisioning:** No — but P0 will not survive without it.

**Smallest repair direction:** start a daemon reader thread per process that drains to a log file
(and preserve the marker scan through the same channel).

---

### F-07 — MEDIUM — the "mandatory pre-capture liveness probe" is neither mandatory-before-capture nor independent

**Affected surface:** `capture_driver.py:240-256`

**Evidence.** The probe is constructed after the full ABBA sequence has been captured, from
`results[0].settled_hash` versus `results[1].settled_hash`. Under either frozen ABBA order those two
slots already differ in target presence, so the probe duplicates the first target-transition probe.
Amendment 3 §3f names it as a distinct third probe point.

**Why it matters.** A frozen renderer is still detected, but only after the unit's renderer time is
spent, and the authority's independent controlled check does not exist. If `len(results) < 2` the
expression would also raise `IndexError` rather than a blocker.

**Blocks host provisioning:** No.

**Smallest repair direction:** issue a real controlled probe before the first slot (a known scene
toggle), and keep the ABBA transitions as separate probes.

---

### F-08 — MEDIUM — server command results are never read, so refusals surface as timeouts

**Affected surface:** `capture_runtime.py:send()`, `capture_driver.capture_p0_unit`

**Evidence.** `send()` writes to stdin and returns the command string; nothing reads the reply.
`p0Cmd` returns `0` and emits `p0 REFUSED: …` for an unsupported registry ID or an out-of-lane
placement. Python sees neither, then fails 180 s later with `TIMING_CARDINALITY_MISMATCH`.

**Why it matters.** `P0_CANDIDATE_ID_UNSUPPORTED` and `P0_PLACEMENT_GROSS_ERROR` are named `A4`
blocker codes with no producer on the live path, so a real refusal is misrouted in the recovery
runbook and costs 180 s per occurrence.

**Blocks host provisioning:** No.

**Smallest repair direction:** parse the drained server output (see F-06) for the mod's
`REFUSED`/`Armed` responses and raise the mod's own blocker.

---

### F-09 — MEDIUM — the artifact-inventory completeness mechanism is unwired from the filesystem, and paths diverge

**Affected surface:** `EXPECTED_ARTIFACT_INVENTORY.json`, `artifact_inventory.py:78`,
`tests/experiment_iii/integration/test_group_b.py:744`

**Evidence.** The frozen inventory specifies `data/experiment_iii/cohort/*` and
`data/experiment_iii/provenance/*`; the implementation writes `docs/experiment_iii/cohort/*` and
`docs/experiment_iii/a1_receipts/*`. All 11 `A1` artifacts exist, none at the specified path; only
the `A2` receipt matches. `stage_exit_check(stage, present)` compares caller-supplied strings and
never touches the filesystem; its only caller is B.10, which supplies the inventory's own patterns.

**Why it matters.** The authority describes this inventory as what "makes missing evidence
auto-detectable." As wired, it can detect nothing about the real repository, and its one test is
tautological.

**Blocks host provisioning:** No.

**Smallest repair direction:** decide which path set is normative, reconcile one to the other, and
give `stage_exit_check` a filesystem-backed caller invoked at stage exit.

---

### F-10 — MEDIUM — failed P0 units are not recorded, so `A4`'s "all attempts retained" is unmet

**Affected surface:** `run_p0_rve_calibration.py:180-205`, `p0_campaign.py:245`

**Evidence.** `P0CampaignState.mark_attempt` is called only from a test. The runner's `try/except`
catches `ExperimentIIIError` at top level and returns `1`; the failing unit is never marked
`ATTEMPTED` and no attempt provenance is written. `A4` specifies `retry_rules:
SAME_FROZEN_UNIT_ONLY; all attempts retained`.

**Blocks host provisioning:** No.

**Smallest repair direction:** wrap the per-unit call so a failure marks the attempt, saves state,
and then re-raises.

---

### F-11 — MEDIUM — frames may be hashed before they are fully written

**Affected surface:** `capture_driver.py:122-140` (`wait_for_frames`), `FrameCapture.java` async
writer

**Evidence.** The mod encodes and writes PNGs on a background IO thread (`IO.execute`) and publishes
`capture_complete.json` with `pending_writes`, `writer_errors` and `drained` after
`awaitDrained(5000)`. Python waits for file *count* `>= expected`, then sleeps
`settle_seconds = 1.0`, then reads and hashes. The completion marker is never consulted.

**Why it matters.** A file appears at `open`, not at completion, so a slow write can be hashed
truncated. The hash is diagnostic, but the bytes also feed the (currently unwired) RVE analysis, and
`writer_errors` is silently discarded.

**Blocks host provisioning:** No.

**Smallest repair direction:** wait on `capture_complete.json` with `drained == true` and
`writer_errors == 0` instead of on file count.

---

### F-12 — LOW — `warmup_ticks` is accepted, recorded, and never applied

`capture_p0_unit` takes `warmup_ticks`, places it in the unit evidence, and never issues a warmup to
the server; the mod's `/mineocclude warmup` command is never sent. The receipt therefore claims a
warmup that did not occur.

### F-13 — LOW — `RuntimeConfig.output_root` is required but ignored by the P0 runner

`from_mapping` rejects a config lacking `output_root`, but the runner derives the sink from
`config.client_root / "mineocclude_client_out"`. The value happens to be correct (the client is
launched with `--gameDir client_root`), but a host operator setting `output_root` would see it have
no effect.

### F-14 — LOW — `COHORT_SALT_AUTHORITY_SHA256` is defined twice

`authority.py:119` and `:132` assign the identical value under an identical duplicated comment
block. Harmless today; an amendment editing only one copy would be silently ineffective.

### F-15 — LOW — `draft_authority/` is untracked but referenced by the authority README

The README's "What is NOT here, and why" table points at `../draft_authority/`. A clean clone lacks
it. Provenance-only material, so the impact is bounded.

### F-16 — LOW — a module-scoped fixture can silently skip the frozen capture-order group

`test_conditions_and_schedule.py:293` calls `pytest.skip("cohort not materialized")` from a
`scope="module"` fixture. The cohort is tracked so this does not fire, but `A2` forbids Group A/D
skips and this is the kind of environment-dependent silent skip that rule exists for.

### F-17 — LOW — dry-run liveness shares the evidence shape of a real verdict

`capture_p0_unit` returns `{"dry_run": True, "passed": None}` in the same `liveness` slot a real
verdict occupies. Nothing downstream currently distinguishes them, so a dry-run unit could be
persisted into campaign state looking structurally like a measured one.

### I-01 — INFORMATIONAL — task-graph `status` fields all read `NOT_STARTED`

Frozen at `A0` and never intended to track live progress. Progress lives in the receipts. Not a
defect; noted so a future reader does not mistake it for one.

### I-02 — INFORMATIONAL — the authority README states `IMPLEMENTATION_AUTHORIZED = false`

This is the `A0`-time value inside the frozen package. Authorization is conferred by the independent
final audit's `IMPLEMENTATION_GO`, not by editing the frozen README.

### I-03 — INFORMATIONAL — schedule pressure is material

`deadline.py` pins `TARGET_CAPTURE_LAUNCH = 2026-09-01 20:00` and `TARGET_RESULT_LOCK =
2026-09-02 23:00`, against an absolute lock of 2026-09-03 20:00. Today is 2026-08-31. Checkpoints
`CP1 09-01 13:00`, `CP2 09-01 20:36`, `CP3 09-02 00:48` are live. The F-01 repair consumes
implementation time before capture launch, and the `A2` re-run it forces should be budgeted.

### I-04 — INFORMATIONAL — the mod's own stale-renderer detector logs where nothing listens

`FrameCapture.java` maintains a `sampleChecksum`/`staleStreak` detector that logs `ERROR` on
consecutive byte-identical captures. Python never reads the client log, so this evidence — which is
independent of the Python probes and would have caught the historical duplicate-frame incident — is
currently write-only. Folding it into the liveness receipt would strengthen F-03's repair at
near-zero cost.

---

## 17. Intentionally Outstanding Future Work

The following are **correctly** incomplete. None is a defect, and none should be reported as one.

- **`A3` environment receipt.** Requires the real host: `POOL_WORKING`/`POOL_DURABLE`/`POOL_SCRATCH`
  device identities, free-byte measurement against the combined-program gate, durable round trip,
  Xvfb/display availability, mod jar hash, and the Minecraft 1.16.5 / Fabric 0.15.11 / API 0.42.0
  pins. Cannot exist before provisioning.
- **All `A4` P0 *data*** — image inventory, RVE table, bootstrap results, mask inventory, selected
  ladder, selection receipt, sentinel envelope *values*. (Their **producers** are not future work;
  see F-01.)
- **Sentinel envelope numbers.** Amendment 3 §3e deliberately freezes the formula now and binds the
  numbers in P2. Their absence is correct prospectivity, not an omission.
- **`A5` P1 pilot data** — 10 captures, 190 forwards, 60 arrays, demonstrated resume. Requires a
  passed `A4`.
- **`A6` P2 prospective freeze** and everything gated behind `PRODUCTION_AUTHORIZED`.
- **`A7`–`A10` production capture and extraction**, including the real `capture_schedule.json` built
  from a genuine `--ladder`.
- **All MineWorld and GPU artifacts.** No checkpoint load, no VAE load, no CUDA, no inference, no
  SageMaker. `run_extraction.py` correctly refuses inference without an injected decoder, and the
  `A3` receipt pins all five resource-policy flags to `False`.
- **`A11`–`A19` analysis, prediction lock, statistics, packaging and closure** — all correctly
  plan-only pending real captures.
- **Every III-B runtime stage** (`B-PILOT`, `B-CAP`, `B-EXT`, `B-U2`, `B-U3`, `B-LOCK`). III-B
  `CLEAN_SKIP` remains a pre-registered honourable outcome and is the first optional work dropped
  under implementation lag.

---

## 18. Final Gate

```
PRE_EXECUTION_AUDIT_STATUS=FAIL
READINESS_VERDICT=NOT_READY_FOR_CAPTURE_HOST_PROVISIONING
BLOCKERS=1
HIGH_FINDINGS=5
MEDIUM_FINDINGS=5
LOW_FINDINGS=6
AUTHORITY_DRIFT=false
SOURCE_CLOSURE_MATCH=true
A1_STATUS=INCOMPLETE_REPORTED_COMPLETE
A2_STATUS=PASS_AT_RECORDED_CLOSURE
P0_CODE_READY=false
CAPTURE_HOST_PROVISIONED=false
LIVE_P0_DATA_EXISTS=false
MINEWORLD_INFERENCE_EXISTS=false
READY_FOR_CAPTURE_HOST_PROVISIONING=false
```
