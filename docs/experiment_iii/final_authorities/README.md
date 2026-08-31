# Experiment III — FINAL AUTHORITY PACKAGE

**This directory is the single controlling authority for Phase 2.**

If a document is not in this directory, it is **not** authority. Everything here is frozen,
hash-bound, and internally audited. Everything elsewhere is provenance, history, or working
material.

```
AUTHORITY_VERSION             = v1.7  (III-A + Amendment 1 / III-B + repair passes 1-2 + ultimate closure + Amendment 2 cohort admission feasibility + Amendment 3 P0 operational completeness + Amendment 4 capture liveness successor rule)
AUTHORITY_INTERNAL_VALIDATION = PASS
IMPLEMENTATION_READY          = true
IMPLEMENTATION_AUTHORIZED     = false
```

**`v1.2` closed eight blocking defects found by the independent pre-implementation audit.**
No scientific question, estimand, condition, `q` value, oracle constant, readout or claim ladder
changed. In one line each:

| | Defect | Repair |
|---|---|---|
| **B1** | the all-`q` qualification requirement was a twelfth cohort gate nobody had written down, and its primitive was ordered *after* cohort materialization | gate 12 is written into §2.4 and evaluated **before** materialization; `IB02`/`IB03` are now **prerequisites of `I02`** |
| **B2** | machine authority said the affine form went negative below τ = 5/4; the oracle says 4/3, and `D.7` demanded negativity at τ = 1…4 in *both* directions | thresholds unified at **LTR = 4, RTL = 3**; `D.7` rewritten to the exact direction-specific boundary |
| **B3** | an unconstrained ridge can return `sigma_hat < 0`, leaving Gaussian calibration undefined | `sigma_tilde = max(sigma_hat, 1e-4)` for **calibration only**; U2/U3 keep raw `sigma_hat`; `fraction_clipped` always reported |
| **B4** | "CI excludes zero after Holm" names no executable procedure | intervals **report**, Holm-adjusted p-values **decide**; every p-value construction frozen algorithmically (§22.0) |
| **B5** | U2-S2 residualized on τ alone, leaving a direction confound | conditioning is now **τ × direction**, 30 frozen cells |
| **B6** | three stale controlling hashes | recomputed from the actual files; human and machine authority agree |
| **B7** | storage gates mixed GB with GiB and double counted one filesystem as two pools | units are GiB and bytes; `POOL_WORKING` / `POOL_DURABLE` / `POOL_SCRATCH` defined physically; A3 uses the **combined-program** gate |
| **B8** | the `A1` implementation workload was never estimated | estimated it, and added implementation-progress fallback triggers — *both superseded by `v1.3` R1 below, which found the estimate was in the wrong unit and the triggers were asserted rather than derived* |

**`v1.3` closed the four blocking defects the second independent audit found in `v1.2`.**

| | Defect | Repair |
|---|---|---|
| **R1** | the schedule, the implementation envelope and the feasibility verdict were mutually impossible — effort hours were compared against wall clock | four time quantities defined separately; implementation re-derived per task from the graph (`SERIAL_ELAPSED` 20.70/38.40/65.00 h, now bound per task); `PHASE2_START` made real; checkpoints **derived** as deadline-minus-conservative-tail |
| **R2** | the 64 GiB `A3` gate and the 20 GiB III-B launch gate contradicted each other | launch gate lowered to **15 GiB** ≤ the 15.204 GiB structural headroom; the mandatory `A3` gate was **not** raised to protect optional III-B; invariant enforced by `B.13` |
| **R3** | `D.11`'s negative control was false — a direction-only decoder gives `ρ|τ = −0.067`, so a correct implementation failed it | fixture replaced with the **`q`-averaged oracle over (τ, direction)**: zero `q` sensitivity, deterministic `ρ|τ = +0.0906` |
| **R4** | `D.2`'s reference hash had no provenance and is not in the bound `v0.4` manifest | bound to commit `f2bc2c8`, the **`v0_3`** manifest (sha256 `ad718685…`), unit `a2x_t01_wall`, seed `2154560968567132226` |

Read [`AUTHORITY_VALIDATION_REPORT.md`](AUTHORITY_VALIDATION_REPORT.md) §13–§14 for the full record.

---

## Start here

**Read [`EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md`](EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md) first, in full.**
It is the canonical, self-contained authority: §0–§16 are Experiment III-A, §17–§31 are
Experiment III-B. Every controlling value is reproduced inside it — you do not need the Phase 0
design, the Fable document, the Bayesian review, or any prior conversation.

Then execute [`IMPLEMENTATION_TASK_GRAPH.json`](IMPLEMENTATION_TASK_GRAPH.json) in dependency
order.

---

## What each file is for

### Controlling — you follow these

| File | Role |
|---|---|
| [`EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md`](EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md) | **Canonical human authority.** The one document that governs. |
| [`EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json`](EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json) | Machine authority — every frozen scientific and execution value |
| [`PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.md`](PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.md) | The Phase 0 amendment admitting III-B (additive, prospective) |
| [`PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.json`](PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.json) | Machine form of the amendment |
| [`IMPLEMENTATION_TASK_GRAPH.json`](IMPLEMENTATION_TASK_GRAPH.json) | **44 tasks** — the Phase 2 execution order (`A1` holds `I01`–`I18` + `IB02` + `IB03`; `A2` holds `I19`/`I20`) |
| [`IMPLEMENTATION_CHANGE_MATRIX.json`](IMPLEMENTATION_CHANGE_MATRIX.json) | 50 change items — what to build and how |
| [`EXPERIMENT_III_LIFECYCLE.json`](EXPERIMENT_III_LIFECYCLE.json) | 29 states (`A0`–`A19`, `B-GEN`–`B-LOCK`) with entry/PASS/FAIL/repair/resume |
| [`BLOCKER_TAXONOMY.json`](BLOCKER_TAXONOMY.json) | 146 blocker codes — never report a failure without one |
| [`EXPECTED_ARTIFACT_INVENTORY.json`](EXPECTED_ARTIFACT_INVENTORY.json) | 99 artifacts — makes missing evidence auto-detectable |
| [`LIVE_STATUS_CONTRACT.json`](LIVE_STATUS_CONTRACT.json) | Runtime status surface (observational only) |
| [`EXPERIMENT_III_TEST_PLAN.md`](EXPERIMENT_III_TEST_PLAN.md) | Test groups A–E — A 30, B 13, D 33; A/B/D all run at `A2` |
| [`RECOVERY_AND_RESUME_RUNBOOK.md`](RECOVERY_AND_RESUME_RUNBOOK.md) | What to do when something breaks |
| [`III_B_ORACLE_SPECIFICATION.json`](III_B_ORACLE_SPECIFICATION.json) | The Bayesian oracle — exact posterior formulas and constants |

### Controlling evidence — you reproduce and verify against these

| File | Role |
|---|---|
| [`FIR_KERNEL_RECOVERY_RECEIPT.json`](FIR_KERNEL_RECOVERY_RECEIPT.json) | The recovered A-prime FIR kernels. Task `I06` must reproduce this recovery and match it. |
| [`III_B_VERIFY_RESOLUTION_RECEIPT.json`](III_B_VERIFY_RESOLUTION_RECEIPT.json) | All 7 III-B VERIFY hooks resolved against source, with the feasibility studies |
| [`AUTHORITY_VALIDATION_REPORT.md`](AUTHORITY_VALIDATION_REPORT.md) | The construction audit, the four material findings, and the §13 record of the eight repaired blocking defects. Read this before implementing. |

---

## Phase 2 quick start

1. Read the canonical authority in full.
2. Read §5 of the validation report — **four findings that will bite you if you skip them**:
   the oracle's affine variance form is wrong below τ=8 (returns negative variance); the
   lane-clamp gate was infeasible as originally written; the path recurrence's addition order is
   load-bearing to the bit; and the pre-occlusion visible window is infeasible.
3. Execute `IMPLEMENTATION_TASK_GRAPH.json`. Critical path:
   `I01 → I05 → I06 → IB02 → IB03 → I02` gates the cohort; `I03 → I04` gates capture
   correctness; `I09 → I10 → I11 → I12 → I15` gates analysis.
4. **`IB02` and `IB03` must land before `I02`** — not merely before III-A P1. III-A
   qualification **gate 12** (all-`q` prospective qualification) is defined in terms of the
   `IB02` primitive, and `IB03` is the bit-identity regression fixture that stops a
   `q`-generalization defect from silently altering III-A's cohort at the moment that gate is
   evaluated. `I02` **fails closed** if either is missing.
5. `A1` **writes** the tests; `A2` **runs** them. Groups A (30), B (12) and **D (33)** all
   execute at `A2` — 75 named static/CPU checks. `D.2`, `D.4` and `D.31` are *additionally* `A1`
   task gates.
6. **Start immediately on authorization** — `PHASE2_START` is the GO instant, not a calendar
   date (§13.3.5). Budget against §13.3.2: `A1 + A2` serial elapsed is
   **20.7 / 38.4 / 65.0 h**, and nothing inside `A1` runs in parallel with anything else in
   `A1`. Watch the §10.5 checkpoints: **CP0 Mon 20:00** (defer III-B-only work),
   **CP1 Tue 13:00** (→ plan 10.2), **CP2 Tue 20:36** (→ 10.3), **CP3 Wed 00:48** (→ 10.4).
7. Stop and emit `AUTHORITY_AMENDMENT_REQUIRED` for anything on the §9.2 list. Never classify a
   scientific redesign as a bug fix.

## Two rules that override everything else

```
NO III-B STAGE IS A PRECONDITION OF ANY III-A SCIENTIFIC COMPLETION STAGE.
III-A MUST CLOSE IDENTICALLY WHETHER III-B RUNS, SKIPS, FAILS, OR IS DROPPED FOR TIME.
```

```
THE ENTIRE PROGRAM MUST BE RESULT-LOCKED BY THURSDAY 2026-09-03, 20:00 LOCAL.
No new scientific execution begins after that instant. No Friday experiment work.
```

III-B is valuable. III-A is indispensable. Never sacrifice III-A to rescue III-B.

**III-B `CLEAN_SKIP` is a pre-registered, honourable outcome.** It is the **first** optional
work dropped under any implementation lag (§29.11, CP0). At nominal implementation III-B
closes comfortably; under conservative implementation it is skipped so that a reduced III-A
plan can close. A skip is never an error state and never a reason to delay III-A.

---

## What is NOT here, and why

| Location | Contents | Status |
|---|---|---|
| `../draft_authority/` | raw audit output (`audit_results*.json`) | working artifacts; superseded by the validation report |
| `../preauthority/` | Phase 0 decision memo and decision matrix | **provenance only** — not authority |
| `../experiment_3_authorities/authority_baseplate/` | the Phase 0 adjudicated design (`.md`, `.docx`) | **provenance only** — not authority |
| `../../../preauthority_creation_inputs/` | Fable design, A-prime reconstruction, Experiment II consolidation, proposal PDFs | **historical provenance only** |

The document hierarchy, restated from §0.2 of the authority:

```
1. THIS PACKAGE                                    <- controlling for execution
2. PHASE 0 ADJUDICATED DESIGN + AMENDMENT 1        <- controlling for design intent
3. PHASE 0 DECISION MEMO / DECISION MATRIX         <- adjudication provenance
4. ORIGINAL FABLE DESIGN                           <- historical provenance only
5. HISTORICAL PROPOSAL / PRIOR EXPERIMENT DOCS     <- historical provenance only
```

Do not silently reverse this hierarchy.
