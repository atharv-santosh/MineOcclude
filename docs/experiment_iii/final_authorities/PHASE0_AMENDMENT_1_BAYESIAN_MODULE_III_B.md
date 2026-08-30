# MineOcclude Experiment III — Phase 0 Amendment 1

## Bayesian Posterior-Uncertainty Module (Experiment III-B)

**Amendment ID:** `PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B`
**Amendment version:** `v1.0`
**Status:** `PROSPECTIVE_ADDITIVE_AMENDMENT`
**Date:** 2026-08-30
**Amends:** `MineOcclude_Experiment_III_Phase0_Adjudicated_Design.md`
(SHA-256 `be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c`)

**Prospectivity attestation.** This amendment is written before any Experiment III
implementation, before P0, before P1, before any capture, before any MineWorld inference, and
before any Experiment III scientific outcome has been produced or observed. Nothing in it is
informed by a result.

```
IMPLEMENTATION_STARTED        = false
SCIENTIFIC_EXECUTION_STARTED  = false
PRODUCTION_OUTCOMES_OBSERVED  = none
```

---

## 1. What this amendment does, and does not do

**Does:** add one new, independent, *optional* experimental module — **Experiment III-B** —
that manipulates **process noise `q`** in order to make oracle posterior uncertainty objectively
different at matched occlusion age, and thereby permits a bounded test of U2 (uncertainty
representation) and a small U3 (uncertainty dynamics).

**Does not:** modify, weaken, reopen, or reinterpret any settled Experiment III-A decision. The
original adjudicated design is **not overwritten**. It remains the controlling design for the
glass/observability axis exactly as adjudicated.

---

## 2. Why the original U2/U3 exclusion was correct, and remains correct

The Phase 0 adjudicated design excluded U2 and U3. That exclusion was correct **for the axis it
was written about**, and this amendment does not overturn it.

The Phase 0 axis is **graded glass visibility**. Along that axis the exclusion stands, for the
reason Phase 0 gave:

> **graded glass visibility ≠ Bayesian uncertainty**

Weakening direct visual evidence with stained glass changes how much *evidence* an observer
receives. It does **not** change the *objective posterior uncertainty* of the underlying latent
state, because the generative process is untouched: the sheep's motion statistics are identical
under L0, L1, L2, L3 and L4. An apparent "uncertainty" difference across the glass ladder would
be a property of the observation channel, confounded with image evidence, and would not
correspond to any objectively different posterior. Phase 0 was right to refuse to call that U2.

Phase 0 also excluded a **process-noise grid**. That exclusion was scoped to the III-A design,
where a `q` grid would have been a confounding scope expansion crossing the glass ladder.

**What changes here is not the argument but the manipulation.** III-B introduces a *new,
independent* manipulation:

> **process noise `q`**

Varying `q` changes the **generative process itself**. At matched occlusion age `τ`, under a
fixed opaque wall, the oracle posterior standard deviation is

```
sigma_tau(q) = sqrt( q * dt * S(tau) )
```

where `S(τ)` is a q-independent function of the frozen FIR kernel. The posterior spread is
therefore **objectively different by a known factor** `sqrt(q_a/q_b)` — exactly 2× between
adjacent frozen levels and exactly 4× between `q_low` and `q_high` — while image evidence,
condition, wall material, camera, layout, speed, and the readout are **all identical**.

That is a genuine uncertainty manipulation with a ground-truth answer. It is what the glass axis
could not provide, and it is why U2/U3 become askable here and only here.

**Scope of the reversal.** The exclusion is lifted **only** for the `q` axis, **only** at
condition `L4` (opaque), and **only** for the bounded U2/U3 family defined below. U4, causal
intervention, steering, a general process-noise grid, other speeds, other layouts, other
checkpoints, and any representation search all remain excluded exactly as before.

---

## 3. Additive design: Experiment III-B

| Item | Value |
|---|---|
| Namespace | `r73-grado-v1-b` |
| Condition | **`L4` opaque only** (`minecraft:stone`) |
| Manipulation | process noise `q` |
| `q_low` | **0.0125** blocks²/s |
| `q_mid` | **0.05** blocks²/s — **reused from III-A**, not recaptured |
| `q_high` | **0.2** blocks²/s |
| `q_high` fallback | **0.15** blocks²/s, technical trigger only (§6) |
| Identities | the **same 25 III-A production identities** |
| New production cells | 25 × `L4` × `q_low` and 25 × `L4` × `q_high` |
| New production captures | **50** |
| New pilot captures | 4 (2 excluded pilot identities × {`q_low`, `q_high`} × `L4`) |
| Combined production captures | 125 (III-A) + 50 (III-B) = **175** |
| Layers extracted | **L19 only** |
| Temporal slices | `PREVIOUS` + `CURRENT` |
| Status | **OPTIONAL** — see §5 |

### 3.1 Prospective declaration of the `q_mid` reuse

III-B reuses the III-A `L4` `q = 0.05` cell as its middle dose. **This reuse is declared here,
prospectively, before any III-A outcome has been produced or inspected.** No III-A capture,
activation, prediction, metric, or result informed this decision, and none could have: none
exists.

The reuse is therefore not a post-hoc borrowing of data selected for a favourable property. It
is a pre-registered design economy that avoids recapturing 25 identical captures. This fact is
frozen and must be restated in the final scientific package.

The III-A `q = 0.05` `L4` **occluded** rows are reused as extracted. Only the **visible control
rows** (§4 of the authority) require new inference on those existing captures — no recapture.

---

## 4. The III-A invariant

This amendment is bound by one invariant, which the Phase 1 authority must restate in both its
human-readable and machine-readable forms:

```
NO III-B STAGE IS A PRECONDITION OF ANY III-A SCIENTIFIC COMPLETION STAGE.

III-A MUST CLOSE IDENTICALLY WHETHER III-B RUNS, SKIPS, FAILS, OR IS DROPPED FOR TIME.
```

Concretely:

- No III-A lifecycle state may list a III-B state among its entry conditions.
- No III-A artifact may require a III-B artifact to validate.
- No III-A estimand, fold, prediction, or statistic may depend on a III-B cell.
- III-A's cohort, target rows, folds, readout, baselines, and analysis families are unchanged.
- A III-B `TECHNICAL_FAIL`, `CLEAN_SKIP`, or `SCIENTIFIC_NULL` leaves III-A's closure untouched.

**Never delay III-A closure to save III-B.**

---

## 5. III-B is optional, and its launch is outcome-independent

III-B is a **bonus module**. Its launch, degradation, and abandonment are decided **exclusively**
by time, technical state, and available resources. **No scientific outcome — from III-A, from
the III-B pilot, or from anywhere else — may be consulted.**

The Phase 1 authority freezes:

- a two-evaluation launch gate (Wed 2026-09-02 at 12:00, re-evaluated once at 17:00);
- a four-level drop ladder terminating in a clean skip;
- an absolute stop at **Thu 2026-09-03 20:00** after which no new scientific execution begins.

A `CLEAN_SKIP` is an honourable, pre-registered outcome and is not a failure of the program.

---

## 6. Preserved and new claim restrictions

Everything the original design prohibited remains prohibited. In particular, **U4, causal
intervention, steering, and causal object permanence remain excluded**, and no U2 or U3 result
may be taken to imply any of them.

New restrictions specific to III-B:

- A positive U2 result licenses only bounded wording such as **"uncertainty-relevant information
  tracking oracle posterior spread"** or **"a partial belief-state signature"**.
- The phrase **"calibrated Gaussian belief state under this apparatus"** requires the strongest
  prospectively frozen result conjunction, including scale calibration.
- No U2/U3 result may be described as demonstrating that the model *uses* its uncertainty.
- Any U2 result must survive the frozen clock and q-category confound controls before it may be
  described as uncertainty representation rather than elapsed-time or regime-label decoding.
- Claims remain limited to one layout, one speed, one checkpoint, condition `L4`, the three
  frozen `q` levels, linear probes, and the selected representation.

---

## 7. What this amendment deliberately does not add

- No new glass material, and no new P0/RVE calibration (`III_B_REQUIRES_NEW_P0 = false`).
- No new condition beyond `L4`.
- No new speed, layout, or checkpoint.
- No representation search: `L19 | COARSE_2X6_CONCAT | CURRENT` primary, with a single
  predeclared secondary `CURRENT_MINUS_PREVIOUS`. Layers 4/10, BEST-K, alternative pooling, PCA,
  MLP, and nonlinear rescue all remain excluded.
- No further `q` search beyond the frozen `{0.0125, 0.05, 0.2}` and the single technical
  fallback `0.15`.
- No new identities. III-B reuses the III-A cohort.

---

## 8. Amendment status

```
AMENDMENT_TYPE                 = ADDITIVE_PROSPECTIVE
ORIGINAL_PHASE0_DESIGN_MODIFIED= false
III_A_DECISIONS_REOPENED       = false
III_A_CRITICAL_PATH_CHANGED    = false
U2_U3_EXCLUSION_LIFTED_FOR     = PROCESS_NOISE_Q_AXIS_AT_L4_ONLY
U2_U3_EXCLUSION_RETAINED_FOR   = GLASS_VISIBILITY_AXIS
U4_EXCLUSION                   = RETAINED
III_B_STATUS                   = OPTIONAL
```

This amendment must be hash-bound before it is incorporated into the Phase 1 authority. Its
machine-readable equivalent is `PHASE0_AMENDMENT_1_BAYESIAN_MODULE_III_B.json`.

The operational specification — the oracle, the estimands, the controls, the calibration
battery, the gates, the drop ladder, the workload, and the claim ladder — lives in the Phase 1
authority, which is self-contained. This amendment establishes only that the module is
scientifically admissible, additive, optional, and prospectively declared.
