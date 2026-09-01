# Authority Amendment 5 (v1.8) — III-A analysis bootstrap seed

    AMENDMENT                        = 5
    NAME                             = III-A analysis bootstrap seed
    AUTHORITY_VERSION                = v1.8
    AUTHORITY_SHA256                 = 472eae5eac83a2709808e64aa449a2ffba24a5a12715b4f1645ce88a3094a9f4
    MACHINE_AUTHORITY_SHA256         = 22f236786013b6bf3d0b702523a2990d145d6b4e0bfb0140ddbefc4e5526613b
    PREDECESSOR_AUTHORITY_VERSION    = v1.7
    PREDECESSOR_AUTHORITY_SHA256     = c773d9620e7fde9e72682d24a7515157522064e8c23b7096780a2995b926985a
    PREDECESSOR_MACHINE_SHA256       = 75bb0acb0f7a5b7121d7754de5db623e56527a454b3bea78ce3ae2047fd43788
    PREDECESSOR_FREEZE_COMMIT        = 3fe0bc13d18f0002eebb99a2b10ef83e651d6f9a
    DISCOVERY_STAGE                  = A6_A7_BOUNDARY_PRE_PRODUCTION
    CLASSIFICATION                   = PROSPECTIVE_SCIENTIFIC_DESIGN_CHANGE_SECTION_9_2
    PROSPECTIVE                      = true
    PRODUCTION_CAPTURES_OBSERVED     = 0
    PRODUCTION_FORWARDS_OBSERVED     = 0
    PRODUCTION_OUTCOMES_EXPOSED      = false
    SCIENTIFIC_OUTCOMES_BEFORE       = P0 calibration and P1 pilot only (both disclosed)
    STATUS                           = frozen

---

## 1. Why this amendment exists

`A6` requires the P2 freeze package to bind, among the *Analysis* group, "bootstrap
`B = 10,000`; **the analysis bootstrap seed**". `A6` also names its forbidden repairs
explicitly:

> **Forbidden repairs.** Freezing with a placeholder, a null, or a "to be determined".

No concrete analysis bootstrap seed, and no derivation that would produce one, existed anywhere
in the frozen package. The machine authority carried the non-concrete token at
`statistics.bootstrap_seed`:

```
"bootstrap_seed": "FROZEN_IN_P2"
```

and §8.10.5 said only `| Bootstrap seed | frozen in P2 |`. The single seed derivation the
program does freeze — §7.10b — is domain-separated to **P0** and binds the domain string
`MINEOCCLUDE_EXPERIMENT_III_P0_BOOTSTRAP_V1|`; it is the placement bootstrap for the ladder
validity rules, and it may not be reused for the identity bootstrap of the primary analysis.

The defect is therefore closed under the authority as written: P2 could not be completed
honestly, and `A7` could never be authorized. The predecessor P2 package
(`a2734b31fb8ac5b4987f2ce13a3ff11328b8589fb93a65d1b702b400eb739687`) in fact reported `PASS`
while binding the literal string `"FROZEN_IN_P2"`, because its validator did not reject
placeholders. That producer/validator defect is repaired separately, prospectively, in source.

A bootstrap seed determines which resamples are drawn and therefore the reported two-sided 95%
identity-bootstrap intervals. By §9.3's decision test — *could this change plausibly alter the
reported value of any estimand, for reasons other than fixing an outright computational error?*
— fixing it is a **scientific design change**, not an engineering repair, and §9.2 requires an
amendment. This is that amendment.

## 2. Prospectivity

| Quantity at the moment of amendment | Value |
|---|---|
| Production captures executed | **0** |
| Production MineWorld forwards executed | **0** |
| Production predictions in existence | **false** |
| Production statistics in existence | **false** |
| Production bootstrap executions | **0** |
| Scientific production outcomes exposed | **false** |
| P0 calibration evidence | exists, disclosed, unchanged |
| P1 pilot evidence | exists, disclosed, unchanged |
| Cohort materialised before amendment | true (unchanged by this amendment) |

Verified from evidence, not asserted: no `docs/experiment_iii/capture`,
`docs/experiment_iii/analysis`, `data/experiment_iii/production` or any `e3_t*` production
artifact exists in the repository, and the predecessor P2 records
`production_captures_executed = 0`.

**This amendment was adopted before the first production capture and therefore retains
prospective status.** No production outcome was inspected while it was authored. The seed could
not have been chosen to favour any result, because no result of any kind existed.

## 3. The repair

### 5a Derivation — derived, never picked

The seed is derived by the construction §7.10b already uses for P0, under its own separation
domain, from provenance that predates every Experiment III measurement:

```
DOMAIN                  = MINEOCCLUDE_EXPERIMENT_III_ANALYSIS_BOOTSTRAP_V1
MATERIAL                = DOMAIN + "|" + PHASE0_DESIGN_SHA256
seed_bytes              = SHA256(UTF8(MATERIAL))
ANALYSIS_BOOTSTRAP_SEED = int.from_bytes(seed_bytes[:8], "big") & ((1 << 63) - 1)
```

With the immutable `PHASE0_DESIGN_SHA256 =
be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c`:

```
MATERIAL        = MINEOCCLUDE_EXPERIMENT_III_ANALYSIS_BOOTSTRAP_V1|be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c
MATERIAL_SHA256 = f29ab1fd6c819e7ff584b6ca9344b6d112fe15a10dbc32ff47bed6536589a895
SEED            = 8258108568742502015
```

**Construction verification.** The same construction, under the P0 domain, must regenerate the
seed the authority already published. It does:

```
MINEOCCLUDE_EXPERIMENT_III_P0_BOOTSTRAP_V1|be3ccd97...9c8e4c
MATERIAL_SHA256 = 153dae21a8e0d6c568eb1977e738ecf485f2b4dfc6670e8dc1709bcd8ce6625f
SEED            = 1530570907966297797        (= the frozen §7.10b value)
```

Had it not reproduced, the construction would have been wrong and no amendment could have been
written from it.

### 5b Domain separation is load-bearing

`..._ANALYSIS_BOOTSTRAP_V1` and `..._P0_BOOTSTRAP_V1` bind the same digest and must never
collide. The analysis bootstrap may not inherit the P0 placement-bootstrap stream, and reusing
`1530570907966297797` here is forbidden.

### 5c Stability

Like the P0 seed, this value binds the **Phase 0 design digest**, not the current authority
hash. It is therefore stable across every later operational amendment and cannot be moved by
re-freezing the authority.

### 5d P2 obligation

P2 must bind the concrete integer together with its domain, `PHASE0_DESIGN_SHA256` and the
derivation material digest, and must **refuse** `null`, `""`, a non-integer, and the tokens
`FROZEN_IN_P2`, `TBD`, `TO_BE_DETERMINED`, `PLACEHOLDER`.

## 4. Scope — exactly one value moves

`statistics.bootstrap_seed`: `"FROZEN_IN_P2"` → `8258108568742502015`.

Unchanged: bootstrap `B = 10,000`; the whole-identity resampling unit; pairing semantics; all
three primary estimands and their directions; the Holm family; every secondary family; folds;
inner rotations; the alpha grid; all five baselines; feature definitions; representations;
layers `{4,10,19}`; token slices; the 19 target rows; FIR labels; the cohort; the apparatus;
the five conditions; RVE values and zones; capture order; retry rules; attrition rules; deadline
fallbacks.

**No new success gate is created.** §8.10.6's removed gates stay removed.

## 5. Cohort invariance

`master_salt()` is `sha256("MINEOCCLUDE_EXPERIMENT_III_V1|" + COHORT_SALT_AUTHORITY_SHA256 +
"|" + PHASE0_DESIGN_SHA256)`, where `COHORT_SALT_AUTHORITY_SHA256` is **pinned to v1.5's
authority hash** and never moves — Amendment 3g closed that coupling precisely so an operational
amendment could not regenerate the scientific population. Neither input changes here.

Verified by recomputation across the amendment, field by field, over all 25 identities:

```
COHORT_CHANGED_BY_AMENDMENT  = false
PATHS_CHANGED_BY_AMENDMENT   = false
TARGETS_CHANGED_BY_AMENDMENT = false
FOLDS_CHANGED_BY_AMENDMENT   = false
```

## 6. Invalidation

This is **receipt currentness and authority supersession**, not scientific evidence
invalidation.

| Artifact | Consequence |
|---|---|
| P0 calibration evidence | `P0_SCIENTIFIC_INVALIDATION_SCOPE = NONE` |
| P1 local capture evidence | `P1_LOCAL_SCIENTIFIC_INVALIDATION_SCOPE = NONE` |
| P1 GPU extraction evidence | `P1_GPU_SCIENTIFIC_INVALIDATION_SCOPE = NONE` |
| Production | `PRODUCTION_INVALIDATION_SCOPE = NONE` — production has not started |
| Predecessor P2 `a2734b31…` | `SUPERSEDED_BEFORE_PRODUCTION` — retained permanently as historical evidence; it may **not** authorize production; it authorized none, and none was executed |
| A2 static receipt | stale against the successor authority; must be re-earned at the final closure |
| A3 receipts | stale against the successor authority; must be re-earned per host role |

A new final P2 must be built under the successor authority after the implementation sprint, the
final source closure, the final A2 and the required A3 requalification.

## 7. Predecessor bytes

All predecessor authority bytes are preserved immutably in git history at freeze commit
`3fe0bc13d18f0002eebb99a2b10ef83e651d6f9a`. `v1.7` was not rewritten in place; the machine
authority records `authority_markdown_sha256_superseded_v1_7`.

```
AMENDMENT_5_STATUS = PASS
BLOCKING_DEFECTS   = 0
```
