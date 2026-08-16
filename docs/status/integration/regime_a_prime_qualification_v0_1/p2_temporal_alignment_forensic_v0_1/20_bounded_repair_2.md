# 20 — Bounded Repair #2 After Independent Freeze Block

**Scope:** only the five blockers demonstrated by the independent freeze review,
plus directly analogous defects found while sweeping those same touched modules.
No capture, collection, authority draft, historical-result edit, expensive P2 or
Regime A rerun, commit, or push occurred.

| Blocker | Exact repair | Regression evidence |
|---|---|---|
| R1 mode provenance | Source verification now compares expected-commit tree mode, index mode, and Git-compatible working-tree mode in addition to the existing commit, bytes, and SHA-256 checks. Regular/executable and symlink modes are explicit; unavailable or mismatched modes fail closed. | Index-only and worktree-only executable-bit changes fail; unchanged `100644` mode verifies; prior add/edit/delete/rename/hash/commit cases remain passing. |
| R2 strict authority types | The complete declared path/state spec and row schemas are validated before scientific comparison. IDs must be non-empty strings; counts, seeds, respawn counts, and indices must be non-Boolean plain non-negative integers; numeric fields must be finite and domain-valid; mappings, hashes, scenes, coordinates, camera values, and target ticks are validated structurally. Pair checks cannot bypass failed unit validation. | Exact regressions cover `episode_id=True`, string seed, float frame count, and Boolean respawn count, plus wrong-typed IDs/noise seed/mapping, invalid hashes, non-finite values, camera/FOV domains, and row types. |
| R3 in-support count | `minimum_samples` now counts only finite, well-typed observations inside the requested physical support. Receipts separately expose `total_valid_samples` and `in_support_samples`; outside points cannot satisfy support. | Two in-window plus 98 outside observations fail a minimum of 100 while reporting totals 100/2/98. Existing malformed, non-finite, endpoint, and gap cases remain fail closed. |
| R5 physical ticks | Alignment evidence requires explicit integer coordinates that are non-negative, unique, strictly increasing, and unit-spaced in both server-tick and render/model domains. A conflicting timebase is invalid. Lag is therefore never labelled in ticks from unverified array spacing. | Ten-tick spacing, irregular spacing, duplicate/non-monotonic/missing ticks, irregular render spacing, and inconsistent cadence fail; unit-spaced evidence still resolves. |
| R6 visibility contradiction | `VisibilityPolicy` must explicitly select the primary `VisibilityPredicate`; no available measurement gets silent precedence. Structural and independent-evidence contradictions return `UNRESOLVED`; no policy remains `UNADJUDICATED`. Fraction thresholds remain caller supplied. | The exact `point=false`, `any=false`, `fraction=1.0` case cannot become stable, with additional point/silhouette/fraction/independent contradictions and explicit-primary tests. |

## Directly analogous defects found and fixed

1. Calibration `uncovered_low`/`uncovered_high` had also used total observed
   extrema, allowing outside-support points to understate uncovered endpoint
   spans. They now use only in-support extrema.
2. `AlignmentEvidence` validation could be invalidated after construction by
   mutating caller-owned NumPy arrays. Evidence arrays are now detached copies
   and read-only after validation.
3. The exposed FIR state-to-render mapping used the start rather than the end of
   each differenced interval. It is corrected from `index-lag` to
   `index+1-lag`, with an exact mapping regression.

## Verification

```text
python3 -m pytest tests/prospective/ -q
196 passed in 1.42s

python3 -m compileall -q src/mineocclude/prospective tests/prospective
PASS (no output)
```

Thirty-one adversarial cases were added to the prior 165-test suite. All prior
tests remain passing. Authority choices remain caller supplied and tested
invalid/ambiguous/contradictory evidence cannot emit a scientific PASS, verified
provenance, resolved temporal estimate, full support, or stable visibility
regime.

`BOUNDED_REPAIR_2_STATUS = PASS`

`READY_FOR_FRESH_INDEPENDENT_FREEZE_REVIEW = true`
