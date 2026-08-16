# 09 — `scientific_run_id` Bookkeeping Audit

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.** Codex deferred this; it was investigated
independently rather than assumed.

## Intended invariant
A captured unit's `scientific_run_id` should identify the **cohort it belongs to**, so that a
later selection can separate confirmatory data from development, diagnostic and calibration data.
The P3 authority declares all P3 data `permanently_excluded_from_confirmatory_a_prime`, and the
P2 authority declares P2 `p2_data_confirmatory_membership: false` — both rely on cohort identity
being distinguishable.

## Actual implementation
`scripts/regime_a_prime_qualification_v0_1/p2c_capture.py:233`

```python
str(spec.get("scientific_run_id", "mineocclude-regime-a-first25-v2"))
```

A **silent default**. Neither the P2 source specs nor the P3 development specs set
`scientific_run_id`, so the default fires for every unit in both cohorts.

## Affected artifacts — measured, not assumed

| Cohort | capture packages | `run_id` observed | distinct values |
|---|---|---|---|
| P2 NO_WALL diagnostic | 50 (25 units × 2 copies) | `mineocclude-regime-a-first25-v2` | 1 |
| P3 development (C01+C02+C03) | 300 (150 units × 2 copies) | `mineocclude-regime-a-first25-v2` | 1 |

Both development/diagnostic cohorts carry the **Regime A first25 scientific** run identity.

## Are the identities that joins actually use unique? — YES

| Key | P2 | P3 | Collisions P2 ∩ P3 |
|---|---|---|---|
| `episode_id` | 25 distinct | 150 distinct | **none** |
| `trajectory_id` | 25 distinct | 150 distinct | **none** |
| unit directory / `run_id` per unit | 25 distinct | 150 distinct | **none** |

Every analysis join in P1/P2/P3 is on `trajectory_spec_id`, `p2_no_wall_run_id`, `episode_id`,
or the unit directory — **never on `scientific_run_id`**. Verified by reading
`p2e_analyze.load()`, `p2d_extract`, and `p3_run_sequential.non_neural_gates`.

## Classification

**PROVENANCE-ONLY DEFECT — not a scientific-data-integrity defect.**

- No historical row-to-capture mapping can be wrong as a result: the fields that carry the
  mapping are unique and collision-free.
- No historical result changes.
- The hazard is **prospective**: any future cohort selection written in terms of `run_id` —
  which is the natural thing for a confirmatory pipeline to do — would silently merge Regime A
  scientific, P2 diagnostic and P3 development units into one cohort. Given that the P3 authority
  *permanently excludes* its own data from the confirmatory A′ cohort, that would be a
  contamination event.

`RUN_IDENTITY_DEFECT_CONFIRMED = true` (provenance scope).

## Repair (future-facing only; no historical ID modified)
`src/mineocclude/prospective/run_identity.py`:
- `RunIdentity.scientific_run_id` has **no default** and rejects blank/whitespace values.
- `CohortTier` must be declared; `confirmatory_membership` must agree with it or construction fails.
- `assert_unique_identities()` enforces uniqueness of unit/episode/spec ids **and** rejects a
  `scientific_run_id` that spans more than one cohort tier — the exact historical condition.

Tests: `tests/prospective/test_run_identity.py`, including a direct reproduction of the
three-tier collision under the shared `mineocclude-regime-a-first25-v2` identity.
