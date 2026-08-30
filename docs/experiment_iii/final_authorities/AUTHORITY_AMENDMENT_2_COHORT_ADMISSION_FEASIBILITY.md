# Authority Amendment 2 — cohort admission feasibility repair (v1.4 → v1.5)

```
PREDECESSOR_AUTHORITY_VERSION       = v1.4
PREDECESSOR_AUTHORITY_SHA256        = 993e5859fa53084889abbc8dda654cd9045dd871258e078cc1afb237f59b4daa
PREDECESSOR_MACHINE_AUTHORITY_SHA256= b6fd1e09b4a9cc868a28ef522dea3a182f3ba42698bfe490ec14c05c192a5f63
PREDECESSOR_AUTHORITY_FREEZE_COMMIT = e86347b1275560f18cae79a9a3333d8af757adbe
SUCCESSOR_AUTHORITY_VERSION         = v1.5
AMENDMENT_TIMESTAMP                 = 2026-08-30
DISCOVERY_STAGE                     = I02
SCIENTIFIC_OUTCOMES_EXISTED         = false
CAPTURE_EXISTED                     = false
COHORT_MATERIALIZED                 = false
MINEWORLD_INFERENCE_EXISTED         = false
PROSPECTIVE_STATUS                  = true
```

The predecessor commit is immutable provenance and is **not** rewritten. It remains the
controlling authority for everything up to the instant this successor is frozen.

---

## 1. The defect

`I02` could not materialize a cohort. Under the simultaneously frozen v1.4 rules —

| | rule |
|---|---|
| §2.3 | strictly ascending candidate index, first qualifying admitted |
| §2.4 gate 9 | between-identity label RMS ≥ 0.10 blocks, same direction |
| §2.4 gate 12 | gates 1–11 at every binding `q`, each on that cell's own path |
| §2.4 | candidate index bound 200 per direction |
| §2.5 | first 19 consecutive eligible rows, **no phase offset** |

— the scan admitted **10 / 13** LTR and **11 / 12** RTL when gate 9 was applied at the
production `q` alone, and **4 / 13** and **4 / 12** when gate 12 was read literally as including
gate 9 at every `q`.

## 2. Evidence available before the amendment

All of it is outcome-free: regenerated paths, counterfactual geometry and timing only. No
rendered frame, activation, RVE value, prediction, MineWorld output or scientific result was read.

**2.1 Root cause of the diversity collapse — measured, not inferred.** A-prime's between-identity
label diversity came from the target-window phase offsets `[0,3,6,9,12]` that §2.5 prospectively
removes. Per-unit offset of the A-prime target window from the counterfactual-extent onset tracks
the bound manifest's own `phase_frames` field exactly:

| unit | `phase_frames` | window offset from onset |
|---|---:|---:|
| `a2y_t01_wall` | 0 | 4 |
| `a2y_t02_wall` | 3 | 7 |
| `a2y_t03_wall` | 6 | 10 |
| `a2y_t04_wall` | 9 | 12 |
| `a2y_t05_wall` | 12 | 16 |
| `a2y_t06_wall` | 0 | 3 |
| `a2y_t07_wall` | 3 | 6 |

Consequent onset spread: A-prime **1.27** blocks (LTR) / **1.38** (RTL); Experiment III without
phase offsets **0.266** / **0.345**. Median pairwise label RMS: A-prime **≈ 0.50**; Experiment III
**0.122** / **0.138**, with **37.2%** / **30.0%** of same-direction pairs below the 0.10 gate.

**2.2 The v1.4 bound was calibrated against the wrong distribution.** §2.4 justified the 200
ceiling by "an expected requirement of ~14–16 per direction … more than 12× the expectation".
Re-applying A-prime's phase offsets to the Experiment III stream reproduces exactly that
expectation — 13/13 LTR after 16 candidates, 12/12 RTL after 15. The expectation was therefore
calibrated on phase-offset diversity that §2.5 removes. **The 200 bound was an incorrectly
calibrated feasibility ceiling, not evidence that gate 9 is wrong.**

**2.3 Gate 12's literal scope contradicts the authority's own feasibility study.** §18.4 reports
per-`q` qualification of **100.0% / 100.0%** at `q = 0.0125` and names
`LANE_CLAMP_IN_PROTECTED_PREFIX` (gate 3) as the dominant high-`q` rejection; §19.4 rests gate 12's
ordering argument on a **per-candidate** rate of `0.9575`. Gate 9 is a *between-identity*
constraint whose verdict depends on which peers are already admitted — it has no per-candidate
rate at all, and with gate 9 inside the per-`q` evaluation the `q = 0.0125` rate cannot be 100%.
Measured at A1: gate 9 at `q = 0.0125` yields a compatibility-graph edge density of 0.242 (LTR) /
0.316 (RTL) and a maximum mutually-compatible set of **4** / **6** — far below the required 13 / 12,
irrespective of candidate-universe size or admission order.

Independent A1 reproduction of §18.4 over 200 candidates per direction, gate 9 excluded:

| `q` | LTR | RTL | §18.4 reference |
|---|---:|---:|---|
| 0.0125 | 100.0% | 100.0% | 100.0% / 100.0% |
| 0.05 | 100.0% | 100.0% | 99.8% / 99.8% |
| 0.15 | 95.5% | 96.0% | 98.4% / 96.4% |
| 0.2 | 92.5% | 94.5% | 97.0% / 93.8% |

All three binding `q` simultaneously: **93.5%** pooled (§19.4 states 95.75%). Dominant first
failing gate at `q = 0.2`: gate 3, in both directions, exactly as §18.4 states. The table is
reproducible **only** with gate 9 outside the per-`q` evaluation.

## 3. Selected repair

### 3a — Gate 12 scope clarified

Gate 12 evaluates the **per-candidate** gates — **1–8, 10 and 11** — at every binding `q`, each on
that `(identity, q)` cell's own regenerated path. **Gate 9 is evaluated once, on the production
cohort, at the III-A `q = 0.05`.**

This restores consistency with §18.4 and §19.4. **Gate 9 is not weakened**: its threshold remains
exactly `0.10` blocks and it remains binding in full on the admitted cohort.

### 3b — Candidate index bound raised, 200 → 2000 (Option D)

The frozen ascending first-qualifying admission procedure is **unchanged**. Only the ceiling moves.

The 2000 ceiling was selected **prospectively, before the extended candidates were inspected**, and
is deliberately **not** set to the observed last-needed index. Exhausting it remains a genuine
terminal signal.

**Option D feasibility result** (unchanged frozen procedure, ceiling 2000).

*The master salt is `sha256(… ‖ AUTHORITY_SHA256 ‖ …)` (§2.2), so amending the authority
necessarily changes the candidate stream. Both scans are recorded: the pre-amendment scan is the
evidence that motivated the repair; the **successor-salt scan is the binding feasibility result**.*

Pre-amendment salt (`AUTHORITY_SHA256 = 993e5859…`, v1.4), diagnostic only:

| direction | admitted | quota completed at index |
|---|---:|---:|
| LEFT_TO_RIGHT | 13 / 13 | 460 |
| RIGHT_TO_LEFT | 12 / 12 | 328 |

**Successor salt (`AUTHORITY_SHA256 = 3d116d97…`, v1.5) — binding:**

| direction | admitted | quota completed at index | admitted candidate indices |
|---|---:|---:|---|
| LEFT_TO_RIGHT | 13 / 13 | **232** | recorded in `option_d_feasibility_receipt.json` |
| RIGHT_TO_LEFT | 12 / 12 | **336** | recorded in `option_d_feasibility_receipt.json` |

Both quotas complete **beyond the superseded 200 ceiling**, so the bound raise is load-bearing in
each direction and not marginal, and both sit far inside the 2000 ceiling that was fixed before any
of these candidates were inspected.

**Line-ending note.** `AUTHORITY_SHA256` is the SHA-256 of the canonical markdown's bytes, and
`.gitattributes` stores the repository as `eol=lf`. The amendment is therefore written and hashed
with LF endings; a CRLF working copy would hash differently and silently change the master salt and
the entire candidate stream. Enforced by a fixture over every authority artifact.

## 4. Rejected alternatives

| | alternative | why rejected |
|---|---|---|
| **A** | lower gate 9's 0.10 threshold | directly weakens a frozen scientific diversity threshold |
| **C** | restore A-prime phase offsets | changes prospectively frozen target rows and reverses a deliberate §2.5 removal |
| **B-prime** | deterministic lexicographically-smallest feasible-subset admission over indices 0–199 | **not needed.** Tested under the *literal* (pre-clarification) gate-12 scope and found infeasible — no 13-LTR / 12-RTL mutually compatible subset exists in that universe, the search exhausting in 2 987 (LTR) / 8 534 (RTL) nodes, because gate 9 at `q = 0.0125` caps any mutually compatible set at 4 / 6. Once repair 3a corrects the scope, the preauthorized priority applies and **Option D succeeds**, so B-prime is not reached. D is also the smaller change: it preserves the frozen ascending first-qualifying admission order that B-prime would have replaced. *B-prime is not asserted to be infeasible under the amended rules; it was simply not required.* |

## 5. What is unchanged

Gate 9 threshold `0.10` · all twelve gates · ascending first-qualifying admission order · target
window (first 19 consecutive eligible rows) · no phase offsets · master salt · `q` grid
`{0.0125, 0.05, 0.2}` and the non-binding `0.15` diagnostic · FIR kernels and normalization ·
counterfactual extent · speed 2.0 · `dt` 0.05 · frames 180 · cohort size 25 + 2 · direction
balance 13/12 · folds and inner rotations · conditions · representations · readout · baselines ·
statistics · estimands · claim ladder · oracle · III-A/III-B independence · deadline semantics.

## 6. Invalidation scope

Nothing scientific is invalidated: no cohort, capture, inference or outcome existed. Implementation
source for `I01`, `I05`, `I06`, `IB02` and `IB03` is unchanged and still conforms.

Every receipt, test and artifact bound to the predecessor `AUTHORITY_SHA256` is invalidated **as
authority-bound evidence**, and is rerun and rebound to the successor hash. The master salt is
derived from `AUTHORITY_SHA256`, so the successor freeze necessarily produces a different candidate
stream from any pre-amendment scan; no pre-amendment candidate index carries over.
