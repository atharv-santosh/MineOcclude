# MineOcclude Experiment III — Authority Validation Report

**Phase:** 1 — Authority construction, plus **Amendment 1** (Bayesian module III-B), plus
**Repair Pass 1** closing the eight blocking defects of the first independent audit (§13), plus
**Repair Pass 2** closing the four blocking defects of the second independent audit (§14), plus the
**Ultimate Closure Pass** closing A1/A2 of the third independent audit (§15)
**Authority version:** `v1.5`
**Date:** 2026-08-30
**Verdict:** `AUTHORITY_INTERNAL_VALIDATION = PASS`

```
III-A audit ...... 285 / 285 passed   (audit_results.json)        - PRESERVED UNCHANGED
III-B audit ...... 320 / 320 passed   (audit_results_iii_b.json)  - NEW
TOTAL ............ 605 / 605 passed
```

`ALL_PREVIOUS_PHASE1_CHECKS_PRESERVED = true`
`BAYESIAN_AMENDMENT_VALIDATION = PASS`

The construction audits above are the **v1.1** record and are preserved verbatim. The **v1.2**
repair pass re-ran a superset of them; its result is recorded in **§13**.

---

## 1. What was validated

The combined authority was audited against six independent references:

1. the Phase 0 adjudicated Markdown design;
2. the Phase 0 decision matrix;
3. the Phase 0 decision memo;
4. **Phase 0 Amendment 1** (the Bayesian module);
5. the actual current source tree, including the git object database;
6. the previous Phase 1 audit, re-run **unmodified in intent** to prove nothing regressed.

Every check is machine-executable and re-runnable.

| III-A group | Passed | | III-B group | Passed |
|---|---:|---|---|---:|
| `artifacts` | 11 / 11 | | `amendment` | 16 / 16 |
| `provenance` | 5 / 5 | | `iii_a_invariant` | 15 / 15 |
| `phase0_decisions` | 158 / 158 | | `iii_a_preserved` | 17 / 17 |
| `arithmetic` | 22 / 22 | | `verify` | 26 / 26 |
| `fir` | 8 / 8 | | `oracle` | 25 / 25 |
| `source` | 20 / 20 | | `design` | 31 / 31 |
| `consistency` | 17 / 17 | | `stats` | 21 / 21 |
| `self_containment` | 36 / 36 | | `workload` | 31 / 31 |
| `outcome_independence` | 8 / 8 | | `deadline` | 23 / 23 |
| | | | `claims`, `vis`, `status`, `artifacts` | 6/6, 8/8, 16/16, 50/50 |

---

## 2. The Phase 0 amendment

`PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.md`
SHA-256 `da32ff953f0734b6de09b3733d54ad72d2fd22266ec51d0eeefe714fee231554`
machine form SHA-256 `7c769f3b5c5bc94d4024d3e81aba51eb60a795ef261a1cb6b24673253f5dc3cb`

Verified: both files exist; both hashes are bound in the machine authority; the amendment records
its own Markdown hash; **the original Phase 0 adjudicated design is not overwritten and its hash
is unchanged** (`be3ccd97…8e4c`, recomputed).

The amendment's argument, audited as stated: the original U2/U3 exclusion **remains correct for
the glass axis**, because stained glass changes the observation channel and not the generative
process — posterior spread is identical across `L0`–`L4`. The exclusion is lifted **only** for a
new, independent manipulation, **process noise `q`**, which changes the dynamics so that oracle
posterior σ differs objectively by the known factor `sqrt(q_a/q_b)` at matched occlusion age.
U4, causal intervention, steering, and causal object permanence **remain excluded**.

The `q_mid` reuse of the III-A `L4` `q = 0.05` cell is recorded as **declared before any III-A
outcome existed** — before implementation, capture, inference, or analysis, none of which have
occurred.

---

## 3. The III-A invariant — audited, not merely asserted

```
NO III-B STAGE IS A PRECONDITION OF ANY III-A SCIENTIFIC COMPLETION STAGE.
III-A MUST CLOSE IDENTICALLY WHETHER III-B RUNS, SKIPS, FAILS, OR IS DROPPED FOR TIME.
```

Fifteen checks, all passing, verify this **mechanically** rather than by assertion:

- no III-A lifecycle state (`A0`–`A19`) mentions any `B-*` state anywhere in its record;
- no III-A state lists a `B-*` state among its entry conditions;
- `A19` closure conditions contain no reference to III-B;
- every III-B artifact is flagged `required_for_iii_a_closure = false`;
- no III-A task depends on any `IB*` task;
- all nine `B-*` states are flagged `optional` and `is_precondition_of_any_iii_a_state = false`;
- the violation blocker `B_III_A_DEPENDENCY_DETECTED` exists and is `CRITICAL`;
- the invariant appears verbatim in the human authority, the machine authority, and the Phase 0
  amendment.

Test `D.26` additionally requires Phase 2 to simulate a total III-B failure and assert III-A
closure is unaffected.

---

## 4. VERIFY hooks — all seven resolved against actual source

Full evidence: `III_B_VERIFY_RESOLUTION_RECEIPT.json`.

| Hook | Result |
|---|---|
| VERIFY-1 noise model | `RESOLVED_POSITION_LEVEL_RANDOM_WALK` |
| VERIFY-2 innovation pairing | `RESOLVED_GENERATOR_NATIVE_PAIRING` |
| VERIFY-3 folds | `RESOLVED_BY_CONSTRUCTION` |
| VERIFY-4 VIS availability | `RESOLVED_NEW_FORWARDS_REQUIRED_AND_WINDOW_RELOCATED` |
| VERIFY-5 q = 0.2 support | `RESOLVED_FEASIBLE` |
| VERIFY-6 FIR at new q | `RESOLVED_KERNELS_REMAIN_AUTHORITATIVE` |
| VERIFY-7 RVE independence | `RESOLVED_NO_NEW_P0` |

**VERIFY-1.** Traced end to end: `generate_noise_schedule` produces `noise_draw = z·sqrt(q·dt)`;
`SheepController.step()` computes `proposed = axisPos + commandedVelocity·dt + eta`. Noise
perturbs **position only** — not velocity, not acceleration. Fable's assumed law is supported, so
the scalar Gaussian propagation oracle is valid. A useful corollary: the apparatus is **already**
q-parameterized end to end (Python generator, JSON header, Java loader, `startspec`,
`SheepController`), so III-B needs no apparatus change.

**VERIFY-2.** `standard_normal(n)` depends only on `(seed, n)`; `q` enters only through the
scalar `sqrt(q·dt)`; the schedule row already stores `standard_normal_draw` separately. Pairing is
therefore the generator's **native** behavior. The q = 0.05 regression reproduces the real frozen
A-prime path hash `b5803943…a56b7`.

**VERIFY-5.** Under the corrected lane-clamp gate, fresh-candidate qualification at `q = 0.2` is
97.0% (LTR) / 93.8% (RTL); **95.4%** of candidates qualify at all three `q` simultaneously; and
**25/25** real A-prime speed-2.0 identities qualify at every `q`.

**VERIFY-7.** III-B varies only `q`, at `L4` stone only. No glass material is touched.
`III_B_REQUIRES_NEW_P0 = false`.

---

## 5. Material findings — four, three of them defects this amendment caught

### 5.1 The oracle's assumed variance form is wrong below τ = 8 — and returns *negative* variance

Deriving the oracle from the verified generator law and the frozen FIR label gives the **exact**
posterior variance

```
sigma2_tau = q * dt * SUM_{m=0}^{tau-1} H(m)^2,      H(m) = cumulative normalized kernel mass
```

which reduces to the familiar affine `q·dt·(τ + c_direction)` **only for τ ≥ 8**. But
`c_direction` is negative in both directions:

| direction | `c_direction` | affine **negative** for | affine **positive** for | affine error at τ = 1 |
|---|---:|:--|:--|---:|
| `LEFT_TO_RIGHT` | −4.355500526065 | `1 ≤ τ ≤ 4` | `τ ≥ 5` | 110,139% |
| `RIGHT_TO_LEFT` | −3.395856222447 | `1 ≤ τ ≤ 3` | `τ ≥ 4` | 995,688% |

The boundary is **direction-specific** (`τ = −c_direction`), so `τ = 4` is *positive*
right-to-left. The v1.2 repair pass unified these thresholds across every artifact and rewrote
`D.7` accordingly — see §13, defect **B2**.

The primary U2 support is **τ = 1…15**. Using the affine form there would have produced negative
variances at τ = 1–4 and silently corrupted every U2 and U3 statistic. **The exact
cumulative-mass form is frozen**, the affine form is explicitly forbidden below τ = 8, and tests
`D.6`/`D.7` — including an explicit negative-value negative control — enforce it.

### 5.2 The III-A lane-clamp gate was infeasible as written (FIX-1, FIX-2)

The III-A authority required `-8.0 < x[t] < 8.0` for **every** `t` in `[0,179]`. A 180-frame
traversal at speed 2.0 covers **18.0 blocks across a 16-block lane**, so touching a bound is
geometrically unavoidable: **all 25** real, qualified A-prime identities touch a bound near tick
153. As written the gate admits nothing and would have fired
`COHORT_QUALIFICATION_INFEASIBLE` at `A1` with a 0% admission rate.

**Corrected:** the clamp must not bind at any index in `[0, last_target_row]`, which covers every
scored row and its complete causal FIR history. Tail clamping after the target window is expected
and is recorded as a diagnostic. Verified: **0/25** A-prime WALL units clamp at or before their
last target row; **25/25** clamp in the tail. `CAPTURE_LANE_CLAMP_ENGAGED` was rescoped likewise.

### 5.3 The path recurrence's addition order is load-bearing (FIX-3)

The authority required an iterative binary64 recurrence but did not freeze the **addition order**.
Binary64 addition is not associative:

```
(x + drift) + noise  ->  b5803943e515ea633cc4...   MATCHES the frozen A-prime hash
(x + noise) + drift  ->  6713929a169500a0a80a...   DOES NOT
```

The two diverge by a single ULP (`8.881784197001252e-16`), first at tick 40 — numerically
invisible, but it changes the SHA-256 completely and would silently break every frozen path
binding. **Drift-before-noise is now frozen** in §2.2 and enforced by an explicit negative control
in tests `A.3` and `D.2`.

This defect was found *because* the III-B evidence generator was written independently and
disagreed with the frozen hash — exactly the kind of cross-check an amendment audit exists to
provide.

### 5.4 The pre-occlusion VIS8 window is infeasible; visible rows move post-occlusion (VERIFY-4)

Two source facts settle it. III-A extracts **no** visible rows, so visible controls need new
forwards. And a model forward requires a complete 16-pair context (`t ≥ 15`), while the
pre-occlusion stable-visible span ends at median frame index **~12–13** — so **0/25** A-prime
identities have a usable pre-occlusion window at `q_low`/`q_mid`.

**Resolved:** visible rows are taken **post-occlusion**, clamp-free (the tail is pinned at the
lane bound for ~20–25 ticks, and a pinned sheep has no motion or positional variance), with a
complete context. **`VIS_ROWS = 6`**, not 8: the clamp-free visible band is
`|x| ∈ [7.1164, 8.0]` = 0.8836 blocks = 8.8 ticks on the LTR side, so 8 rows is marginal there
(62–82%) while 6 is comfortable (87.5–100%). Availability is **best-effort, not a gate** — visible
rows serve descriptive controls only and never enter the primary U2/U3 estimands.

---

## 6. Workload — recomputed from resolved semantics

Every figure recomputed from primitives, not copied.

```
III-B                                       COMBINED PROGRAM
  new production captures        50           production captures        175
  new pilot captures              4           production forwards      3,775
  occluded forwards             950           production arrays        1,000
  visible forwards, new q       300           production bytes  23,465,292,800  (21.8538 GiB)
  visible re-inference          150
  pilot forwards                100           all captures incl pilots   189
  PRODUCTION forwards         1,400           all forwards incl pilots 4,065
  all new forwards            1,500           all arrays incl pilots   1,076
  production arrays             250           all bytes         25,309,485,568  (23.5713 GiB)
  production bytes    3,853,548,800  (3.5889 GiB)
```

`bytes/npy[19,336,2048] = 26,148,992`; `bytes/npy[6,336,2048] = 8,257,664`.
Drop ladder arithmetic verified at every level (NORMAL 1,400 → LEVEL 1 775 → LEVEL 2 625 →
LEVEL 3 840 → LEVEL 4 0 forwards).

**Storage.** *Superseded by the v1.2 repair pass (defect **B7**).* At construction, III-A's
Phase 0 thresholds were preserved (30 / 45 GiB) with `combined_program_*` thresholds of
40 / 60 GiB. The repair pass fixed the units to GiB throughout, defined `POOL_WORKING`,
`POOL_DURABLE` and `POOL_SCRATCH` as **physical filesystems** identified by device id, forbade
counting one filesystem as two pools, froze the mirror scope, derived the peak
(**35.682 GiB** unmirrored, **59.304 GiB** mirrored), and raised the mirrored A3 gate to
**64 GiB** for real margin. A3 now always uses the **combined-program** gate. See §13.

---

## 7. Deadline discipline — audited

```
ABSOLUTE_EXPERIMENT_DEADLINE        = 2026-09-03T20:00 local
preferred III-A result lock         = 2026-09-02T23:00
preferred III-B result lock         = 2026-09-03T16:00
III-B first gate                    = 2026-09-02T12:00
III-B second (final) gate           = 2026-09-02T17:00
FRIDAY_EXPERIMENT_EXECUTION_PLANNED = false
```

Twenty-three checks verify: gate inputs are time/technical/resources only and a scientific-outcome
input is **refused**, not ignored; there is no third reconsideration and no Friday launch; the
eight launch requirements are present; a second NO-GO yields `CLEAN_SKIP`; the drop ladder has
five levels selected on time/technical/resources only; `LEVEL_1` reduces the U2 Holm family to two
(frozen prospectively, the only permitted family change); `LEVEL_3` orders by
`identity_priority_order`; the `q_high` fallback trigger is technical-only with exactly one
attempt and four named forbidden triggers; and Friday/Saturday are reserved for writing.

**No normal stage completes on Friday**, and the conservative schedule variant still locks III-A
before Thursday 20:00 — because III-B holds no III-A dependency.

---

## 8. Deviations from Phase 0 and from the III-B specification

**Phase 0 (III-A): none.** All 158 decision checks pass. No settled decision was changed. The
three corrections (FIX-1, FIX-2, FIX-3) are **Phase-1 operationalization defects** — the authority
mis-stated a gate and under-specified an arithmetic order — and change no scientific value. Each
is recorded with its evidence in the machine authority and the VERIFY receipt.

**III-B specification: three source-driven refinements**, each mandated by "subject to actual
source verification" and each documented with evidence:

| Provisional | Frozen | Why |
|---|---|---|
| `sigma2 = q·dt·(τ + c)` | exact cumulative-mass form | affine is negative for τ ≤ 4 (LTR) and τ ≤ 3 (RTL); primary support starts at τ = 1 |
| VIS8, pre-occlusion | VIS6, post-occlusion, clamp-free | pre-occlusion window has no 16-pair context; 8 rows marginal on one direction |
| ~1,658 forwards / ~4.25 GiB | 1,500 forwards / 3.845 GiB | follows from VIS6 |

**One item could not be sourced.** The external *Bayesian Extension Review* is not present in this
repository and was not supplied. The task text specified the module in enough detail to build the
authority, with one exception: **the exact U2 positive-declaration conjunction**. That conjunction
is therefore **defined by this authority** from the three specified statistics, frozen in §22.4,
and flagged in both the human and machine authority. If the external review specifies a different
conjunction, adopting it is a §9.2 scientific change requiring a dated, pre-execution amendment —
never a silent substitution, and never after results exist.

---

## 9. III-A preservation — explicitly re-verified

| Assertion | Result |
|---|---|
| III-A audit re-run, all previous checks | **285 / 285 PASS** |
| Five conditions, 25 identities, layers {4,10,19} unchanged | PASS |
| Three primary estimands, Holm-3, `B = 10,000` unchanged | PASS |
| Recovered FIR kernels and their verification unchanged | PASS |
| Wall cache-key fix (`C07`, `WALL_CACHE_KEY_STALE`) still required | PASS |
| L0 no-wall scene fix (`C06`, `WALL_CONDITION_SCENE_MISMATCH`) still required | PASS |
| No III-A change-matrix item modified | PASS (`iii_a_items_modified_by_amendment = []`) |
| III-A production totals unchanged (125 / 2,375 / 750 / 19,611,744,000) | PASS |
| 20 III-A lifecycle states, 24 III-A tasks, 30 III-A change items | PASS |
| q = 0.05 behavior bit-identical under the generalized generator | PASS |

The three Phase 1 findings from the original authority are intact: the recovered A-prime FIR
kernels, the arena-cache material binding, and the L0 no-wall scene path.

---

## 10. Self-containment

**Could a Phase 2 agent implement both III-A and III-B from `docs/experiment_iii/final_authorities/` plus
the source tree, without reopening the original Fable document, the Bayesian review, prior chat,
or the proposal?**

**Yes.** Thirty-five III-B and thirty-six III-A self-containment checks confirm the canonical
authority carries every controlling value in-line: the `q` values and fallback; the exact oracle
mean and variance formulas with per-direction constants; the primary target and its linear scale;
the representations; the three U2 statistics with their operationalizations and the permutation
null; the eight confound controls; VIS6; the U3 family; the calibration battery; the seven-rung
claim ladder; the workload; the gates; the drop ladder; the schedule; and every claim restriction.

`AUTHORITY_SELF_CONTAINED = PASS`

---

## 11. Artifact hashes

**Recomputed from the actual files at the close of the v1.2 repair pass** (defect **B6**). Every
value below was produced by hashing the file on disk, not copied forward.

| SHA-256 | Bytes | Artifact |
|---|---:|---|
| `eb0a5a602372cbb1d06f54dbb4a6a1c01994128bd9ed47245dff9881212f3cee` | 103,663 | `BLOCKER_TAXONOMY.json` |
| `6bf647b3196a38aeec767faffd343ca0241526b0114e1bdda081fb153a5d5c3e` | 62,537 | `EXPECTED_ARTIFACT_INVENTORY.json` |
| `3df2ee0ca89a0bc4953501dbc46f77f894754cb2b18fdc951b9a46e943597e97` | 82,560 | `EXPERIMENT_III_LIFECYCLE.json` |
| `f707d5f8264e46c22861707d4caa871cf634da931aa97556eaec31d1df3463a9` | 209,592 | `EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json` |
| `3d116d9713b2c7fa705a194023e271061f712d0693618abbd991efa45437d7fb` | 241,084 | `EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md` |
| `e720cbe4383dcacab3ede2200d384d51a7acc14c698c547ecdd1f7515a8f458f` | 49,143 | `EXPERIMENT_III_TEST_PLAN.md` |
| `72dc0633482a31fdf3f825ab19147aa57e8f4b8cbafa9eba696eb76799f365a0` | 6,527 | `FIR_KERNEL_RECOVERY_RECEIPT.json` |
| `e39d056417447494555979ed43fcfd08671b14cc09b204ec0c4b788251716d97` | 9,255 | `III_B_ORACLE_SPECIFICATION.json` |
| `e83a8ac34920cd7753c9e49dba3a00a66db7b2fad34663ef0462676f835bcfed` | 24,175 | `III_B_VERIFY_RESOLUTION_RECEIPT.json` |
| `09bfca1ca061e5e494575d1203485ec20d5fdf90e44e2c662fdaf76d37def326` | 64,139 | `IMPLEMENTATION_CHANGE_MATRIX.json` |
| `c2ecbcc2de3a4a5d400811358a39c8f1427493ba30f3efd1b127862c4ff225b6` | 40,493 | `IMPLEMENTATION_TASK_GRAPH.json` |
| `ac75d2057e07f6685212580952bedcc3dee75598f3c69b128e7a259e34d25af9` | 14,476 | `LIVE_STATUS_CONTRACT.json` |
| `7c769f3b5c5bc94d4024d3e81aba51eb60a795ef261a1cb6b24673253f5dc3cb` | 5,305 | `PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.json` |
| `da32ff953f0734b6de09b3733d54ad72d2fd22266ec51d0eeefe714fee231554` | 9,682 | `PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.md` |
| `65f16ea3f40b50c53641fa2f2f62e527d51063c7a4bc5096e8aa732f1409380e` | 10,834 | `README.md` |
| `14283d4fe2fcd1f454d85eb93735ec9a2a308dcc10b47ca21b9718ba04e3969f` | 33,542 | `RECOVERY_AND_RESUME_RUNBOOK.md` |

*`AUTHORITY_VALIDATION_REPORT.md` is omitted: it carries this table, so its own hash cannot appear inside it. It is not hash-bound by any other artifact.*

*The `final_audit/` subdirectory holds audit OUTPUT about this package and is therefore not listed above, for the same self-reference reason as this report.*

The machine authority records the canonical Markdown hash as `authority_markdown_sha256`; the
Phase 0 amendment hashes are bound under `amendments[0]`. Human and machine authority agree
exactly.

**Three stale references were found and corrected** — the authority Markdown hash and byte count
in this section, and the Phase 0 Amendment 1 **machine-form** hash in both §2 of this report and
§17 of the human authority (all three had `0b126874…`, while the machine authority already held
the correct `7c769f3b…`). A recursive search of the controlling tree confirms **no stale hash
reference remains**.

`../draft_authority/audit_results.json` and `../draft_authority/audit_results_iii_b.json` are the
**v1.1** construction-audit output and are **not** updated by the repair pass; the v1.2 record is
§13 below and `../draft_authority/audit_results_repair_pass.json`.

---

## 12. Verdict

```
ALL_PHASE0_DECISIONS_PRESERVED        = true
PHASE0_AMENDMENT_PRESERVED            = true
ALL_PREVIOUS_PHASE1_CHECKS_PRESERVED  = true
BAYESIAN_AMENDMENT_VALIDATION         = PASS
AUTHORITY_SELF_CONTAINED              = PASS
FULL_LIFECYCLE_COVERED                = true
DEADLINE_PLAN_VALIDATED               = true
III_A_PROTECTED_FROM_III_B            = true
III_A_CHANGED                         = false  (scientifically; 3 operationalization corrections)
III_A_CRITICAL_PATH_CHANGED           = false
AUTHORITY_INTERNAL_VALIDATION         = PASS

v1.1 CONSTRUCTION AUDIT               = 605 / 605
PHASE1_BLOCKERS                       = 0
```

**The v1.2 totals — the ones that govern — are in §13.** Implementation remains **unauthorized**
until an operator explicitly sets `IMPLEMENTATION_AUTHORIZED = true` against this authority's
hash, and until this package is **committed**: `docs/experiment_iii/final_authorities/` is
currently **untracked**, and Phase 2 must begin from a committed, frozen authority state.

---

## 13. The final authority repair pass (v1.2)

An independent pre-implementation audit returned **`CONDITIONAL_GO`** with eight blocking authority
defects, while independently confirming that the oracle matches the generator, the oracle
mathematics are valid, the science is feasible, the workload arithmetic holds, no identity leaks,
the authority is self-contained, III-B needs no new P0, the III-B launch gate and drop ladder are
outcome-independent, the Thursday hard stop is enforceable, and no Friday execution is required.

This pass repaired **only** those eight defects and their downstream consistency surfaces. **No
scientific question, estimand, condition, `q` value, oracle constant, FIR tap, representation,
readout, claim ladder rung or closure rule changed.**

```
III_A_SCIENTIFIC_DESIGN_CHANGED = false
III_B_SCIENTIFIC_DESIGN_CHANGED = false
```

### 13.1 The eight blocking defects

**B1 — the multi-`q` qualification gate was ordered after cohort materialization.**
§19.4 already required every admitted identity to qualify at all three frozen `q`, but the gate
list in §2.4 named only eleven gates, and the task graph had `IB02` *depending on* `I02` — so the
primitive that evaluates the requirement would not exist until after the cohort was built. At an
observed per-identity all-`q` rate of `0.9575`, `1 − 0.9575²⁵ = 0.661`: roughly two runs in three
would have discovered the failure too late, with no admissible recovery, since cohort regeneration
is forbidden once capture exists and is never permitted on the basis of an outcome.

*Repaired:* the requirement is **§2.4 qualification gate 12**, evaluated **before** materialization
and freeze. `IB02` (narrowed to the shared `q`-generalized path and qualification primitive) and
`IB03` (its bit-identity regression guard) are **prerequisites of `I02`**, both inside `A1`; `I02`
**fails closed** with `COHORT_ALL_Q_PRIMITIVE_MISSING` if either is absent. A frozen candidate
index bound of **2000 per direction** (raised from 200 by Amendment 2, v1.5) makes the pre-existing but never-materialized bound executable,
and `COHORT_ALL_Q_QUALIFICATION_INFEASIBLE` defines the prospective repair and resume behaviour —
continue scanning, or fix a defect and rerun the identical deterministic procedure while no capture
exists. Outcome-based regeneration is forbidden; the gate reads no MineWorld output. Test `D.31`
proves the ordering and that the materialized cohort is byte-identical whether III-B runs or
clean-skips.

```
ALL_Q_GATE_COUNT                       = 12
ALL_Q_GATE_APPLIED_BEFORE_COHORT_FREEZE = true
III_A_PROTECTED_FROM_III_B             = PASS
```

**B2 — the affine-negativity threshold contradicted the oracle, and `D.7` was wrong.**
The machine authority carried `LTR = 5, RTL = 4` under an ambiguous `..._below_tau` key name, while
the oracle specification, the human authority and this report all carried the correct `4` and `3`.
Independently: `c_LTR = −4.3555` and `c_RTL = −3.3959`, so the affine form is negative for
`1 ≤ τ ≤ 4` left-to-right and `1 ≤ τ ≤ 3` right-to-left. `D.7` demanded negativity at `τ = 1…4` in
**both** directions — it would have failed a correct implementation, because `τ = 4` is *positive*
right-to-left.

*Repaired:* the ambiguous key is replaced everywhere by `affine_last_negative_tau` (4, 3) plus
`affine_first_positive_tau` (5, 4) and an explicit semantics string, sourced from
`III_B_ORACLE_SPECIFICATION.json` and reproduced verbatim in the machine authority. `D.7` is
rewritten as a boundary-exactness test — negative **exactly** where the frozen oracle says
negative, strictly positive after the direction-specific boundary, no integer τ where the form is
zero, exact agreement of the two forms at `τ ≥ 8`, and the implementation never evaluating the
affine form below `τ = 8`. It is stricter than the test it replaces, not weaker.

```
AFFINE_THRESHOLD_LTR      = 4
AFFINE_THRESHOLD_RTL      = 3
D7_ORACLE_BOUNDARY_TEST_VALID = PASS
```

**B3 — negative `sigma_hat` handling was undefined.**
III-B fits an unconstrained ridge to linear σ, which can return `sigma_hat < 0` near low `q` and
low τ. That does not invalidate statistics built on raw predictions, but it leaves Gaussian
interval construction, Gaussian NLL, `log σ` and density scoring undefined.

*Repaired:* §27.0 freezes `sigma_tilde = max(sigma_hat, 1e-4 blocks)` for **calibration
probabilistic uses only** — coverage, both NLL variants, log axes, density scores. U2-S1/S2/S3,
U3-S1/S2/S3, scale agreement and monotonicity keep **raw** `sigma_hat`. `EPS = 1e-4` is `3.878×`
below the smallest oracle σ anywhere on the primary support (`3.8782034e-4` blocks:
`RIGHT_TO_LEFT`, `q_low`, `τ = 1`) and `1000×` below the frozen minimum target SD, so it cannot
manufacture or mask a signal. `fraction_clipped`, `count_negative` and `min_sigma_hat` are reported
for every analysis that uses `sigma_tilde`; above `0.05` the results are labelled
`POSITIVITY_GUARD_MATERIAL` — a disclosure, never a failure. The rule may not change after
prediction lock (`B_CALIBRATION_POSITIVITY_RULE_ALTERED`); locked predictions store raw values.

```
PRIMARY_U2_U3_USE_RAW_SIGMA_HAT      = true
CALIBRATION_SIGMA_EPS_BLOCKS         = 0.0001
CALIBRATION_REPORTS_CLIPPED_FRACTION = true
NEGATIVE_SIGMA_HANDLING_DEFINED      = PASS
CALIBRATION_PLAN_VALID               = PASS
```

**B4 — "Holm-adjusted CI" named no executable procedure.**
Holm adjusts p-values or an explicitly adjusted confidence level; "the CI excludes zero after Holm"
is not a unique construction, and U2-S2 and U2-S3 had no p-value defined at all.

*Repaired:* §22.0 separates the two roles. Intervals are **ordinary unadjusted two-sided 95%
whole-identity bootstrap percentile intervals**, `B = 10,000`, for effect-size reporting; the phrase
"Holm-adjusted CI" is forbidden. Significance is declared only from a Holm-adjusted p-value. Every
p-value is now constructed algorithmically: U2-S1 by the within-identity `q`-permutation null
(`B = 9,999`, `p = (1 + #{perm ≥ obs})/10,000`); U2-S2, U2-S3, U3-S1 and U3-S2 by one-sided
whole-identity **bootstrap inversion**, `p = (1 + #{T*_b ≤ T_null})/(B + 1)` with `B = 10,000` and
`T_null = 0` (or `1/6` for U2-S3). Null, alternative, sidedness, family membership, Holm ordering
with tie-breaking by frozen member order, the step-down monotone adjustment, and the decision rule
are all stated. The calibration battery, U3-S3, the context-boundary secondary and the eight
confound controls enter **no** family. Human and machine authority carry the identical procedure;
`D.33` tests it.

```
HOLM_PROCEDURE_EXECUTABLE = true
CI_ROLE                   = EFFECT_SIZE_REPORTING
HOLM_ROLE                 = FAMILYWISE_HYPOTHESIS_DECISION
```

**B5 — U2-S2 carried a direction confound.**
Oracle σ depends on direction through the direction-specific FIR alignment term `H_direction(m)`,
so after τ-**only** residualization a residual direction contrast survives in both rank vectors: a
decoder reading direction alone, with literally zero `q` sensitivity, could produce a positive
U2-S2. U2-S1 and U2-S3 are protected by their within-identity contrasts.

*Repaired:* U2-S2 conditions on **τ × direction** — a frozen 30-cell categorical nuisance structure
(`τ = 1…15 × {LTR, RTL}`). The order is frozen: rank over the pooled set first, then residualize by
OLS on `[1 | 30 cell indicators]` via `lstsq`, whose fitted values and residuals are unique despite
the rank deficiency and are numerically identical to within-cell mean centring (the definition of
record). Singleton cells yield residual `0.0` and are retained; single-direction bootstrap
replicates are retained and counted. `D.11` adds a mandatory negative control: a pure-direction,
zero-`q`-sensitivity dataset must yield a positive U2-S2 under τ-only conditioning and an
interval covering zero under the frozen conditioning.

```
U2_S2_CONDITIONING                = tau_x_direction
U2_S2_DIRECTION_CONFOUND_REMOVED  = true
U2_STATISTICS_VALID               = PASS
```

**B6 — three stale controlling hashes.** See §11. All recomputed from the files on disk; a
recursive search of the controlling tree confirms none remain.

```
STALE_HASH_REFERENCES              = 0
MACHINE_HUMAN_AUTHORITY_CONSISTENT = PASS
```

**B7 — storage units, pools and the A3 threshold were inconsistent.**
A3 carried III-A-only thresholds (45 / 30 GiB) while the combined program used 60 / 40 elsewhere;
the III-B launch gate mixed `GB` with `GiB` and required "`≥ 60 GB` durable free **and** `≥ 40 GB`
scratch free" — two independent pools that may be the same filesystem, counted twice.

*Repaired:* §13.2 fixes units to **GiB** with every gate also frozen in bytes; defines
`POOL_WORKING`, `POOL_DURABLE` and `POOL_SCRATCH` as **physical** filesystems identified by
device/volume id; forbids counting one filesystem as two pools
(`STORAGE_POOL_DOUBLE_COUNTED`); defines the three durability modes, defaulting to
`LOCAL_MIRROR_SAME_POOL` so the gate fails closed, and stating that a **remote object store carries
no local free-space gate**; and freezes the mirror scope (activations, receipts, manifests, ledger
— **not** raw PNGs). The peak is derived rather than asserted: **35.682 GiB** unmirrored,
**59.304 GiB** mirrored, reproducing the independent estimates of ~35 and ~57 GiB. A3 uses the
**combined-program** gate — III-B is prospectively authorized and A3 always precedes the III-B
launch gate, so the III-A-only thresholds are unreachable. The mirrored gate is **64 GiB**, not 60,
to keep 4.696 GiB of real margin. The launch gate now measures III-B's **incremental** headroom
(`≥ 20 GiB` on `POOL_WORKING` against a 10.508 GiB incremental mirrored peak, a 1.9× margin), which
is the correct quantity at that point in the program.

```
STORAGE_UNITS_CONSISTENT              = true
STORAGE_POOLS_PHYSICALLY_DEFINED      = true
A3_USES_COMBINED_PROGRAM_STORAGE_GATE = true
STORAGE_FEASIBILITY                   = PASS
```

**B8 — the `A1` implementation workload was never estimated.**
Cohort generation, P0, P1, capture, extraction and analysis all had envelopes; the largest item —
building 50 change-matrix items, 22 tasks and 75 named checks — had none, despite being the
schedule's dominant uncertainty.

*Repaired:* §13.3.1 estimates `A1 + A2` in **operator-attended hours**, decomposed into III-A
shared implementation, Fabric/mod changes, III-B shared-path implementation, III-B additive
implementation, test implementation, static-validation execution, and an integration/debug
allowance:

```
A1 + A2 TOTAL                       30.0 / 53.0 / 88.0   h   (best / nominal / conservative)
III-A mandatory only                26.5 / 47.0 / 78.0   h
III-A end to end                    45.0 / 79.25 / 135.0 h
III-B incremental, execution only    4.2 /  7.4 /  11.9  h   (matches the independent audit exactly)
III-B incremental, incl. its impl.   7.7 / 13.4 /  21.9  h
```

Attendance and resource class are recorded per component. **No false parallelism is claimed:**
everything in `A1` is repository-exclusive and single-session, so nothing inside `A1` overlaps
anything else in `A1`. The only real parallelism is unattended capture overlapping repository work,
unattended III-B capture overlapping III-A CPU analysis, and GPU extraction overlapping writing.
Against 83 wall-clock hours — of which roughly **56** are realistically attended — the schedule was
recomputed (§30): P0 moves from Monday to Tuesday afternoon, capture launches Tuesday night, III-A
locks Wed ~14:00 / Wed ~23:00 / Thu ~12:00.

The conservative variant does **not** fit unmanaged, and the pre-existing fallback triggers all
keyed on the **P2 freeze**, which fires far too late to help. §10.5 therefore adds
implementation-progress checkpoints on `A2 == PASS` at **Tue 12:00**, **Tue 20:00** and **Wed
08:00**, escalating monotonically through plans §10.2 → §10.3 → §10.4, plus a III-B
implementation checkpoint at Wed 10:00. The Wednesday 12:00 III-B launch gate was re-evaluated
against the revised schedule and **retained unchanged**: III-A capture closes at 11:00 nominal, so
the gate is passable under BEST and NOMINAL and correctly returns NO-GO under CONSERVATIVE. All
triggers read time, stage status and resources only.

```
A1_IMPLEMENTATION_TIME_ESTIMATED = true
DEADLINE_PLAN_VALIDATED          = PASS
THURSDAY_HARD_STOP_PRESERVED     = true
```

### 13.2 Non-blocking findings also closed

| Finding | Disposition |
|---|---|
| `q_mid` capture-session confound | **Disclosed**, not recaptured. §19.2 states that `q_mid` comes from the III-A session while `q_low`/`q_high` are fresh and paired, that U2-S1 and U3-S2 are therefore unaffected, and that U2-S3 and `q_mid`-inclusive calibration may carry a session effect. A sensitivity analysis is required. |
| FIR normalization | **Frozen once, everywhere.** `normalized[k] = taps[k]/fsum(taps)`, applied at load. `fsum(LTR) = 0.9999999999`, so unnormalized taps pass the `1e-9` label tolerance but fail the `1e-12` `S(τ)` tolerance by up to `9.29e-10`; normalized taps reproduce the frozen tables to `0.0`. Blocker `FIR_KERNEL_NOT_NORMALIZED`. |
| Group-D stage binding | Group D runs at **`A2`** with groups A and B. `D.2`, `D.4` and `D.31` are *additionally* `A1` task gates because III-A gate 12 depends on them; a failure in any other group-D check is a III-B blocker only. |
| `I19`/`I20` stage binding | `A1` **writes** tests (`I01`–`I18` + `IB02` + `IB03`, 20 tasks); `A2` **runs** them (`I19`, `I20`). The "`I01`–`I20`" phrasing is corrected. |
| Source-closure sorting | Sorted **by the `<path>` field only**, raw UTF-8 byte order. A whole-line sort would order on mode and blob sha first and is forbidden. |
| `final_authorities/` git tracking | **Untracked.** Reported, not committed by this pass. Phase 2 must begin from a committed, frozen authority state. |
| Scale-calibration wording | A CI containing slope = 1 is a **non-rejection** of scale mismatch, not proof of equivalence. Permitted and forbidden phrasings are frozen in §27.A and §27.E; `D.18` enforces them. |
| RVE source RGB vs MineWorld BGR | **Disclosed** in §7.4. The RVE statistic is channel-permutation invariant, so the number is unaffected, but the ladder orders conditions by **source-rendered** visual evidence, not by a model perceptual metric. RVE is not redesigned. |

### 13.3 v1.2 verdict

```
ALL_8_BLOCKERS_RESOLVED               = true
III_A_SCIENTIFIC_DESIGN_CHANGED       = false
III_B_SCIENTIFIC_DESIGN_CHANGED       = false
ORACLE_MATCHES_GENERATOR              = PASS
ORACLE_MATHEMATICS_VALID              = PASS
U2_IDENTIFICATION_VALID               = PASS
U3_IDENTIFICATION_VALID               = PASS
CALIBRATION_PLAN_VALID                = PASS
III_A_PROTECTED_FROM_III_B            = PASS
III_B_OPTIONALITY_VALID               = PASS
III_B_LAUNCH_GATE_OUTCOME_INDEPENDENT = PASS
III_B_DROP_LADDER_OUTCOME_INDEPENDENT = PASS
AUTHORITY_SELF_CONTAINED              = PASS
MACHINE_HUMAN_AUTHORITY_CONSISTENT    = PASS
STALE_HASH_REFERENCES                 = 0

ABSOLUTE_EXPERIMENT_DEADLINE          = 2026-09-03 20:00 local
FRIDAY_EXPERIMENT_EXECUTION_REQUIRED  = false

IMPLEMENTATION_READY                  = true
IMPLEMENTATION_AUTHORIZED             = false
```

Per-check output for the repair-pass audit is
`../draft_authority/audit_results_repair_pass.json`. **Phase 2 does not begin until this package is
committed and an operator sets `IMPLEMENTATION_AUTHORIZED = true` against its hash.**

---

## 14. Repair pass 2 (v1.3) — closing R1–R4

The **second** independent final audit returned `FINAL_AUDIT_STATUS = FAIL`,
`IMPLEMENTATION_GO = false`, with four blocking defects — three of them **introduced by repair
pass 1**. It independently reproduced and re-confirmed the entire scientific core: the oracle
matches the generator against live source; the FIR recovery reproduces 50/50 path hashes at rank 9;
the fsum normalization is necessary and exact; the affine boundaries derive to LTR 4 / RTL 3; the
source closure is path-sorted and matches; zero stale hashes; the Holm formula and bootstrap
inversion are correct and calibrated; the τ × direction repair is substantively justified;
`EPS = 1e-4` is valid; the workload arithmetic, structural integrity, III-A protection, III-B
optionality, gate outcome-independence and the Thursday hard stop all hold.

**Those decisions were not reopened.** Repair pass 2 changed no scientific question, estimand,
condition, `q` value, oracle constant, FIR tap, representation, readout, claim-ladder rung or
closure rule.

```
III_A_SCIENTIFIC_DESIGN_CHANGED = false
III_B_SCIENTIFIC_DESIGN_CHANGED = false
```

### 14.1 R1 — the deadline/schedule/envelope contradiction

**The defect.** Repair pass 1 reported `A1+A2` as `26.5 / 47 / 78` **hours** and compared them
against the calendar, while the schedule claimed completion at instants offering only 13 / 21 / 38
hours. Propagated literally, the nominal plan reached `A2` green around Thursday 00:00 and tripped
the disaster plan; III-A nominal needed 69.75 attended hours against 56 declared available. The
checkpoints selected plans 10.2/10.3, which reduce **capture and analysis** while the overrun was in
**implementation**. `DEADLINE_PLAN_VALIDATED = PASS` was unsupported.

**The repair — and it is not a smaller invented number.** The root cause was a **unit error**:
`26.5 / 47 / 78` were human-equivalent **effort** hours, and the budget is **wall clock**. §13.3.1
now defines four quantities that are never interchangeable — `TOTAL_TASK_EFFORT_HOURS`,
`SERIAL_CRITICAL_PATH_ELAPSED_HOURS`, `DEPENDENCY_CRITICAL_PATH_HOURS`,
`OPERATOR_ATTENDED_HOURS`, `UNATTENDED_COMPUTE_HOURS` — and the schedule uses exactly one.

§13.3.2 re-derives implementation **per task from the actual task graph**, at a frozen
dependency-respecting serial build order, carrying both effort and elapsed:

```
NORMAL      SERIAL_ELAPSED 20.70 / 38.40 / 65.00 h     EFFORT 41.40 / 76.80 / 130.00 h
PLAN 10.2   SERIAL_ELAPSED 20.20 / 37.40 / 63.30 h     saves 0.50 / 1.00 / 1.70 h of implementation
PLAN 10.3   SERIAL_ELAPSED 18.90 / 35.00 / 59.30 h     saves 1.80 / 3.40 / 5.70 h of implementation
III-B additive                2.30 /  4.60 /  8.00 h   deferrable, dropped first
IB02 + IB03 (shared)          0.80 /  1.40 /  2.40 h   NEVER deferrable
```

Elapsed is the **sum** over the task set, not the dependency path (7.2/13.2/22.4 h), because every
`A1` task is repository-exclusive and single-session — claiming the dependency path would be the
false parallelism the authority forbids. The agent compression factor is **exactly 2.0** by definition; it
is recorded as **an assumption and the dominant schedule risk**, and the checkpoints key on observed
milestones rather than trusting it.

**The reduced plans were mapped to real implementation work** (§13.3.2): 10.2 deletes the L4/L10
descriptive-depth portions of `I09`/`I16` and their fixtures; 10.3 additionally deletes **task `I12`
entirely**, the `PREVIOUS`-span half of `I09`/`C17`, the temporal-rescue panel of `I16`, and the
temporal fixtures. **Honest finding, recorded rather than hidden:** measured at the checkpoint
instants the *realizable* implementation saving is `0.00 h` at best and nominal and `~1.0–1.2 h` at
conservative, because the deletable work is built early. **The reduced plans are not an
implementation-overrun remedy.** Their real value is the post-`A2` tail: `3.92 h` and `6.28 h` at
nominal, `7.60 h` / `11.80 h` at conservative.

**`PHASE2_START` is now real** (§13.3.5): implementation begins at the GO instant, not on a
hard-coded Monday. Authorizing Sunday 20:00 rather than Monday 09:00 recovers **13 wall-clock
hours — larger than every plan-reduction saving combined**, and it is the single biggest lever.

**The checkpoints are derived, not typed in** (§10.5). Each is
*deadline − that plan's **conservative** post-`A2` tail*, so it is the last instant that plan can
still close even if execution goes badly, and it does not move with `PHASE2_START`:

| Checkpoint | Instant | Milestone | Action |
|---|---|---|---|
| **CP0** | Mon 2026-08-31 20:00 | `I10` complete | defer all III-B-only implementation (`IB01`, `IB04`–`IB20`) |
| **CP1** | Tue 2026-09-01 13:00 | `A2 == PASS` | select plan 10.2 |
| **CP2** | Tue 2026-09-01 20:36 | `A2 == PASS` | select plan 10.3 |
| **CP3** | Wed 2026-09-02 00:48 | `A2 == PASS` | select plan 10.4 |

**CP0 is the only checkpoint that reliably recovers implementation time**, which is why III-B-only
work is the first sacrifice (§29.11). `IB02`/`IB03` are never deferred — gate 12 depends on them.

**The feasibility verdict is now honest** (§13.3.4). Implementation and execution bands are modelled
independently. Every cell marked feasible closes arithmetically:

```
NORMAL   best/best            38.20 h  vs 96 h budget   +57.80  FEASIBLE
NORMAL   nominal/nominal      69.65 h                   +26.35  FEASIBLE
NORMAL   conservative/nominal 96.25 h                    -0.25  NOT FEASIBLE
PLAN 10.2 conservative/nominal 90.63 h                   +5.37  FEASIBLE
PLAN 10.3 conservative/nominal 84.27 h                  +11.73  FEASIBLE
```

**The full NORMAL plan is stated as TIGHT and as NOT FEASIBLE under conservative implementation**,
rather than forced to pass. A prospectively valid reduced III-A plan closes in that case. That is
what the ladder is for.

```
III_A_TIME_FEASIBILITY     NORMAL best/nominal FEASIBLE; NORMAL conservative NOT FEASIBLE;
                           PLAN 10.2 / 10.3 FEASIBLE under conservative implementation
III_B_TIME_FEASIBILITY     best/nominal FEASIBLE; conservative CLEAN_SKIP
COMBINED_TIME_FEASIBILITY  best/nominal FEASIBLE; conservative III-A only, III-B CLEAN_SKIP
EXPECTED_III_A_RESULT_LOCK 2026-09-02T17:39 local (NORMAL, nominal)
EXPECTED_III_B_RESULT_LOCK 2026-09-03T05:00 local (NORMAL, nominal)
DEADLINE_PLAN_VALIDATED    PASS
```

### 14.2 R2 — storage-gate incoherence

A host passing `A3` at exactly 64 GiB mirrored retained only `15.204 GiB` when the III-B launch
gate fired, which required `20 GiB` — a forced, spurious `CLEAN_SKIP` on a host that legitimately
cleared the gate sized for the combined program.

**The mandatory `A3` threshold was deliberately NOT raised.** III-A is indispensable and III-B is
optional; making III-A harder to start in order to make III-B easier to finish is the wrong trade.
The **optional** gate was lowered to **15 GiB**, and the invariant is frozen and tested (`B.13`):

```
A3_PASS_GIB - MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB >= III_B_INCREMENTAL_LAUNCH_GATE_GIB
     64     -              48.796                    =  15.204  >=  15          OK
III_B_INCREMENTAL_LAUNCH_GATE_GIB > III_B_INCREMENTAL_EXPECTED_PEAK_GIB
              15                  >            10.508           margin 4.492 GiB
```

`MAX_III_A_STORAGE_SHARE` is derived (whole-program mirrored peak `59.304` − III-B incremental
`10.508`), not asserted. `STORAGE_GATE_COHERENCE = PASS`.

### 14.3 R3 — the `D.11` negative control was false

`D.11` made `sigma_hat` a **pure function of direction** and demanded a positive τ-only U2-S2. The
audit measured `ρ|τ = −0.067`: a correct implementation would have **failed** the test — the same
defect class as the original `D.7`. The cause: the oracle's direction ordering **flips** with τ
(LTR > RTL at τ ∈ {1,2}, RTL > LTR for τ ≥ 3), so a direction-constant decoder largely cancels when
pooled. The confound is carried by the τ-by-direction **interaction**.

The fixture is now the **`q`-averaged oracle as a function of `(τ, direction)`** — frozen formula,
literally zero `q` information, asserted exactly (max across-`q` spread `== 0.0`). Reference
behaviour, **recentred by the ultimate closure pass**: the deterministic frozen construction
yields `ρ|τ = +0.0905724833 ± 0.002` (the old `+0.063 ± 0.03` came from a noise-perturbed
variant and left only 0.0024 of margin). The `OPTIMAL_PROJECTION` variant attains `≈ +0.110`
against a ceiling of `+0.114`. Under τ × direction the fixture is constant within every nuisance
cell, so the **A2 zero-variance rule** fires and maps the statistic to `rho = 0.0`, `p = 1.0`
deterministically. `D11_NEGATIVE_CONTROL = PASS`.

### 14.4 R4 — the `D.2` reference provenance

The reference path hash `b5803943…` was cited in five places with no provenance, and is **not** in
the bound `v0.4` FIR manifest. It is now bound, at the **same commit** that binds the FIR source:

| Field | Value |
|---|---|
| commit | `f2bc2c8082e77f9c3f9e089f2fb1a20b11a052a8` |
| path | `…/prospective_development_authority_v0_3/stage2_locked_manifest.json` |
| blob SHA-1 | `fb93a08ba2d71c28c9929469d9b34bf8fc6de17b` |
| bytes | 270,672 |
| manifest SHA-256 | `ad718685b33030a0c0de405cd9d3abb737c3f3e9d087ad7c78768fe151855eb8` |
| unit / direction | `a2x_t01_wall` / `LEFT_TO_RIGHT` |
| seed = noise_seed | `2154560968567132226` |
| start / speed / `q` / frames | `-7.8` / `2.0` / `0.05` / `180` |
| `expected_path_sha256` | `b5803943e515ea633cc4dd80ddeaf349db5cb99d11980febdc3f13d7f84a56b7` |

Reproduced at repair with the frozen drift-first arithmetic; both negative controls change the hash
(noise-first yields `6713929a…`). Bound in the machine authority, the FIR receipt, the human
authority §18.2, `D.2`, the change matrix `CB03` and the runbook. Phase 2 reconstructs `D.2` from
this package plus the git object database alone. `D2_REFERENCE_PROVENANCE_BOUND = PASS`,
`AUTHORITY_SELF_CONTAINED = PASS`.

### 14.5 v1.3 verdict

```
ALL_4_BLOCKERS_RESOLVED               = true
R1_DEADLINE_PLAN                      = PASS
R2_STORAGE_GATE_COHERENCE             = PASS
R3_D11_NEGATIVE_CONTROL               = PASS
R4_D2_PROVENANCE_BINDING              = PASS

III_A_SCIENTIFIC_DESIGN_CHANGED       = false
III_B_SCIENTIFIC_DESIGN_CHANGED       = false
DEADLINE_PLAN_VALIDATED               = PASS
STORAGE_GATE_COHERENCE                = PASS
AUTHORITY_SELF_CONTAINED              = PASS
MACHINE_HUMAN_AUTHORITY_CONSISTENT    = PASS
STALE_HASH_REFERENCES                 = 0

ABSOLUTE_EXPERIMENT_DEADLINE          = 2026-09-03 20:00 local
FRIDAY_EXPERIMENT_EXECUTION_REQUIRED  = false

IMPLEMENTATION_READY                  = true
IMPLEMENTATION_AUTHORIZED             = false
AUTHORITY_FREEZE_COMMIT_RECOMMENDED   = false
```

Per-check output: `../draft_authority/audit_results_repair_pass_2.json`. **The package remains
uncommitted. One more independent final audit is required; only `PASS` with
`IMPLEMENTATION_GO = true` permits freeze and Phase 2.**

---

## 15. Ultimate closure pass (v1.4) — A1 and A2

The third independent audit returned `FAIL` with two blocking defects, both introduced by repair
pass 2, and independently reconfirmed the entire scientific core (oracle, FIR, affine boundaries,
q semantics, D.2 provenance, U2/U3, calibration, token indexing, folds, wall cache, L0, workload,
storage, source closure, III-A protection, optionality, gate independence, Thursday stop, 89/89
regression checks). Those decisions were not reopened.

### 15.1 A1 — the implementation-time model is now reproducible

**The defect.** `implementation_time_model.derived_from` claimed a per-task derivation, but the
per-task hours existed nowhere in the package. Only three cross-task buckets were recorded; a
22-task residual of `17.20 / 31.00 / 51.80 h` was asserted. Nobody reading only
`final_authorities/` could reproduce `20.70 / 38.40 / 65.00`.

**The repair.** Every task in the frozen serial build order now carries a full record:
`TASK_ID`, `DESCRIPTION`, `PLAN_MEMBERSHIP`, best/nominal/conservative elapsed **and** effort,
`PLAN_10_2_REDUCTION_HOURS`, `PLAN_10_3_ADDITIONAL_REDUCTION_HOURS`, `ATTENDED_OR_UNATTENDED`,
`RESOURCE_CLASS`, `PREDECESSORS`, `SAFE_TO_PARALLELIZE` with its reason, `PLAN_10_2_REQUIRED`,
`PLAN_10_3_REQUIRED`, `III_B_ONLY`, `SHARED_A_B`. The three cross-task buckets are **named
activities** with purpose and plan membership, not residuals; `no_anonymous_residual = true`.

```
NORMAL     = sum(22 tasks) + sum(3 buckets)
PLAN 10.2  = NORMAL    - sum(10.2 reductions)
PLAN 10.3  = PLAN 10.2 - sum(10.3 additional reductions)

band          tasks  buckets  NORMAL   cut2    10.2   cut3    10.3   III-B
best          17.20    3.50   20.70    0.50   20.20   1.30   18.90    2.30
nominal       31.00    7.40   38.40    1.00   37.40   2.40   35.00    4.60
conservative  51.80   13.20   65.00    1.70   63.30   4.00   59.30    8.00
```

`TOTAL_TASK_EFFORT = SERIAL_ELAPSED × 2.0` exactly, so effort is derived rather than asserted;
the factor is recorded as an assumption and the dominant schedule risk. `I12` is the only task
removed outright (by 10.3). III-B-only work is itemized across 18 tasks and totals
`2.30 / 4.60 / 8.00 h` — derived, replacing the previously asserted `2.0 / 4.0 / 7.0`.

No feasibility verdict changed: NORMAL best/nominal feasible, **NORMAL conservative NOT feasible**,
10.2 and 10.3 feasible under conservative implementation.

### 15.2 A2 — zero-variance U2-S2 semantics are frozen

**The defect.** The D.11 fixture is constant within every `(τ, direction)` cell by construction, so
its residual is identically zero and Pearson is `0/0`. numpy returns `NaN` with a RuntimeWarning,
scipy returns `NaN` with a ConstantInputWarning, a guarded implementation returns `0.0`. D.11
assertion 3 "passed" only because `NaN <= 0.05` evaluates `False` — an IEEE accident. Conforming
implementations could disagree.

**The repair.** `u2_family.S2.zero_variance_rule`:

```
if Var(r_hat) <= TOL or Var(r_oracle) <= TOL:
        rho := 0.0        exactly
        p   := 1.0        exactly        (one-sided test of rho > 0)
        U2_S2_ZERO_VARIANCE_CASE := true

TOL = 1e-15 * Var(the corresponding UNRESIDUALIZED rank vector)      scale-free
    = 1.05e-10 at the frozen 1,125-cell design
```

The tolerance sits ~`1.4e9` **above** the numerical round-off floor (`7.7e-20`) and ~`3.3e12`
**below** the variance of a genuine residual (measured `3.51e+02`) — unambiguous in both
directions. The statistic is never `NaN`, missing, skipped or positive. Bootstrap replicates in the
same case are **retained** with `rho* = 0.0`, never dropped, which keeps the inversion formula
consistent: `p = (1 + B)/(B + 1) = 1.0`. With `rho = 0.0` and `p = 1.0`, U2-S2 fails its clause and
`U2_POSITIVE` cannot be declared.

`D.11` now asserts the branch **fires**, the mapping is **exact**, and that **no `NaN` is produced,
propagated or compared** anywhere in the decision path.

### 15.3 Non-blocking cleanups

| Item | Disposition |
|---|---|
| D.11 reference recentred | recomputed deterministically: `+0.0905724833 ± 0.002` (was `+0.063 ± 0.03`, from a noise-perturbed variant with 0.0024 of margin) |
| §30.1 checkpoint order | rows are now monotone in elapsed offset; CP1 annotated as clock-driven |
| Window allowance | now its own named `+69.7 h` row; no hidden time inside packaging |
| §29.11 placement | moved after §29.10, before §30 |

### 15.4 v1.4 verdict

```
A1_IMPLEMENTATION_TIME_MODEL_REPRODUCIBLE = PASS
A2_ZERO_VARIANCE_U2_S2_DEFINED            = PASS
NO_ANONYMOUS_RESIDUAL                     = true
III_A_SCIENTIFIC_DESIGN_CHANGED           = false
III_B_SCIENTIFIC_DESIGN_CHANGED           = false
DEADLINE_PLAN_VALIDATED                   = PASS
```

Per-check output: `final_audit/audit_results.json`. Full independent audit:
`final_audit/FINAL_PREIMPLEMENTATION_AUDIT.md`.

---

## 16. Authority Amendment 2 (v1.5) — cohort admission feasibility

Prospective §9.2 scientific amendment, raised at `I02` before any cohort, capture, inference or
scientific outcome existed. Full record:
[`AUTHORITY_AMENDMENT_2_COHORT_ADMISSION_FEASIBILITY.md`](AUTHORITY_AMENDMENT_2_COHORT_ADMISSION_FEASIBILITY.md).

| | |
|---|---|
| Defect | §2.3 + §2.4 gate 9 + §2.4 bound 200 + §2.5 no-phase-offset are jointly infeasible |
| Root cause | the 200 bound was calibrated on A-prime phase-offset diversity that §2.5 removes |
| Repair 2a | gate 12 scope = the per-candidate gates (1–8, 10, 11); gate 9 is peer-dependent and evaluated once at the III-A `q` |
| Repair 2b | candidate index bound 200 → 2000 (Option D), admission order unchanged |
| Gate 9 threshold | **unchanged at 0.10** |
| Rejected | lowering gate 9 (A); restoring phase offsets (C); feasible-subset selection (B-prime, tested infeasible at bound 200) |
| Invalidation | no scientific invalidation; all predecessor-bound receipts rerun and rebound |

```
AMENDMENT_2_STATUS = PASS
BLOCKING_DEFECTS   = 0
```
