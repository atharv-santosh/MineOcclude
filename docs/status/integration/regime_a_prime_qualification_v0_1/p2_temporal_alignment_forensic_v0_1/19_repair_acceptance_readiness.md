# 19 — Repair Acceptance Readiness

## Outcome

All eight initial independent-review blockers and all five bounded-repair #2
follow-up blockers are repaired. Prospective tests pass at 196/196, the direct Regime A refit completes, authority-neutrality and
fail-closed audits pass, and historical/frozen artifacts remain unchanged.

Bounded repair #2 and its directly analogous touched-module findings are recorded
in `20_bounded_repair_2.md`. The expensive P2 and Regime A analyses were not
rerun during that repair session; a fresh independent freeze review must
reproduce them.

## Scientific facts carried forward

- causal smoothing interpretation confirmed;
- group delay 3.363631 ticks;
- Student-t 95% interval [3.185, 3.542] ticks;
- trajectory bootstrap 95% interval [3.219, 3.522] ticks;
- P2 corrected BEST-K RMSE 0.0778023888, macro R² 0.9555412043;
- P2 corrected FULL RMSE 0.1068284791, macro R² 0.9167019115;
- P2 substantive conclusion `VALID_WITH_NUMERIC_REVISION`;
- Regime A `FAIL_NO_DEFENSIBLE_DECODING` remains substantively supported by
  direct corrected refit, not a presumed bound.

## Boundary checks

- historical P1/P2/P3 results modified: **no**;
- historical authority modified: **no**;
- P3 terminal freeze artifacts modified: **no**;
- new authority drafted: **no**;
- new capture or collection authorized: **no**;
- commit/push performed: **no**.

`READY_FOR_INDEPENDENT_FREEZE_REVIEW = true`

Next allowed action: start a fresh Codex session for independent freeze review;
do not collect data.
