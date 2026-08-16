# 17 — Prospective Fail-Closed Audit

**Result: PASS.** Nine fail-open classes were found and repaired.

Bounded repair #2 closed five follow-up edge cases within these classes: Git
mode-only provenance divergence, wrong-typed path authority, outside-support
sample counting, unverified temporal index units, and contradictory visibility
evidence. See `20_bounded_repair_2.md`.

| # | Fail-open class | Closed behavior |
|---:|---|---|
| 1 | Index-only/staged source divergence invisible to working-tree `git diff` | tree/index/work bytes are independently bound; any mismatch makes `verified=false` |
| 2 | Declared path/state fields omitted | full field schema and exact caller mapping are enforced; missing/invalid fields cannot pass |
| 3 | NaN/Inf/malformed/empty calibration observations or internal gaps | INVALID/FAIL; absent requirements are UNADJUDICATED, never covered |
| 4 | Truthy/falsy non-Boolean detector values | exact type check permits only `bool`/`None` |
| 5 | Duplicate, missing, mismatched, or cross-clock detector/reference join | AMBIGUOUS or INVALID with zero returned pairs |
| 6 | Thin or homogeneous temporal evidence plus embedded acceptance defaults | measurement remains unadjudicated/fails requirements; all coverage and uncertainty requirements are explicit |
| 7 | Predicate agreement or default fractional bounds promoted to physical stability | no policy → UNADJUDICATED; missing/conflicting independent evidence → UNRESOLVED |
| 8 | Defaulted cohort membership/empty cohort identity | explicit strict Boolean membership and non-empty typed cohort required |
| 9 | Invalid clock-domain type or non-finite conversion | exception before mapping/measurement; no scientific row can be emitted |

Adversarial tests cover missing data, invalid types, NaN/infinity, missing
provenance, ambiguous identity, insufficient coverage, missing policy,
unsupported clock mapping, unknown scene requirements, and unknown direction.
No tested path produces PASS, `verified=true`, stable regime, qualification, or
`fully_covered=true` from those conditions.

`FAIL_OPEN_PATHS_FOUND = 9`

`FAIL_OPEN_PATHS_REPAIRED = 9`

`FAIL_CLOSED_AUDIT_STATUS = PASS`
