# Final time-feasibility report

**Independently resummed from the per-task model, not read back from the totals.**

## The four quantities

`SERIAL_CRITICAL_PATH_ELAPSED_HOURS` drives the schedule: the sum over the selected task set for
**one** agent session. It is *not* the dependency-path floor (7.20/13.20/22.40 h), because every
`A1` task is repository-exclusive and single-session. `TOTAL_TASK_EFFORT = elapsed x 2.0` exactly.
`OPERATOR_ATTENDED` 9/16/27 h and `UNATTENDED_COMPUTE` 7.5/12.25/22 h are reported separately.

## Per-task model (22 tasks + 3 named buckets, no anonymous residual)

| Task | best | nom | cons | 10.2 cut | 10.3 extra | in 10.3 |
|---|---:|---:|---:|---:|---:|:--:|
| `I01` | 0.40 | 0.70 | 1.20 | — | — | yes |
| `I05` | 0.80 | 1.40 | 2.40 | — | — | yes |
| `I06` | 1.00 | 1.80 | 3.00 | — | — | yes |
| `IB02` | 0.50 | 0.90 | 1.50 | — | — | yes |
| `IB03` | 0.30 | 0.50 | 0.90 | — | — | yes |
| `I02` | 1.50 | 2.80 | 4.50 | — | — | yes |
| `I03` | 1.00 | 1.80 | 3.00 | — | — | yes |
| `I04` | 1.20 | 2.20 | 3.50 | — | — | yes |
| `I09` | 1.20 | 2.20 | 3.60 | 0.15/0.30/0.50 | 0.30/0.50/0.80 | yes |
| `I10` | 0.80 | 1.40 | 2.40 | — | — | yes |
| `I11` | 0.50 | 0.90 | 1.50 | — | — | yes |
| `I12` | 0.50 | 0.90 | 1.50 | — | 0.50/0.90/1.50 | **no** |
| `I15` | 1.00 | 1.80 | 3.00 | — | — | yes |
| `I13` | 0.40 | 0.70 | 1.20 | — | — | yes |
| `I14` | 0.50 | 0.90 | 1.50 | — | — | yes |
| `I16` | 1.20 | 2.20 | 3.60 | 0.25/0.50/0.85 | 0.30/0.60/1.00 | yes |
| `I07` | 1.50 | 2.60 | 4.20 | — | — | yes |
| `I08` | 0.40 | 0.70 | 1.20 | — | — | yes |
| `I17` | 0.60 | 1.00 | 1.70 | — | — | yes |
| `I18` | 0.70 | 1.20 | 2.00 | — | — | yes |
| `I19` | 0.60 | 1.20 | 2.20 | — | — | yes |
| `I20` | 0.60 | 1.20 | 2.20 | — | — | yes |
| *GROUP_B_D_INTEGRATION_FIXTURES* | 1.00 | 1.90 | 3.20 | 0.10/0.20/0.35 | 0.20/0.40/0.70 | yes |
| *FABRIC_BUILD_CYCLES* | 1.00 | 2.00 | 3.50 | — | — | yes |
| *STATIC_VALIDATION_AND_ENGINEERING_REPAIR_ALLOWANCE* | 1.50 | 3.50 | 6.50 | — | — | yes |

```
band          tasks  buckets  NORMAL   cut2    10.2   cut3    10.3   III-B
best          17.20    3.50   20.70    0.50   20.20   1.30   18.90    2.30
nominal       31.00    7.40   38.40    1.00   37.40   2.40   35.00    4.60
conservative  51.80   13.20   65.00    1.70   63.30   4.00   59.30    8.00
```

## Post-`A2` tails, rebuilt from the frozen plan scopes

| Plan | captures | arrays | tail best/nom/cons |
|---|---:|---:|---|
| NORMAL | 125 | 750 | 17.50 / 31.25 / 55.00 |
| 10.2 | 100 | 200 | 15.20 / 27.33 / 47.40 |
| 10.3 | 75 | 75 | 13.75 / 24.97 / 43.20 |

## Feasibility, `PHASE2_START = 2026-08-30T20:00`, budget 96 h

| Plan | impl band | exec band | total | margin | verdict |
|---|---|---|---:|---:|---|
| NORMAL | best | best | 38.20 | +57.80 | **feasible** |
| NORMAL | nominal | nominal | 69.65 | +26.35 | **feasible** |
| NORMAL | conservative | nominal | 96.25 | -0.25 | **NOT feasible** |
| NORMAL | conservative | conservative | 120.00 | -24.00 | **NOT feasible** |
| PLAN_10_2 | best | best | 35.40 | +60.60 | **feasible** |
| PLAN_10_2 | nominal | nominal | 64.73 | +31.27 | **feasible** |
| PLAN_10_2 | conservative | nominal | 90.63 | +5.37 | **feasible** |
| PLAN_10_2 | conservative | conservative | 110.70 | -14.70 | **NOT feasible** |
| PLAN_10_3 | best | best | 32.65 | +63.35 | **feasible** |
| PLAN_10_3 | nominal | nominal | 59.97 | +36.03 | **feasible** |
| PLAN_10_3 | conservative | nominal | 84.27 | +11.73 | **feasible** |
| PLAN_10_3 | conservative | conservative | 102.50 | -6.50 | **NOT feasible** |

```
III_A_TIME_FEASIBILITY   NORMAL best/nominal FEASIBLE ; NORMAL conservative NOT FEASIBLE
                         PLAN 10.2 / 10.3 FEASIBLE under conservative implementation
III_B_TIME_FEASIBILITY   best/nominal FEASIBLE ; conservative CLEAN_SKIP
COMBINED                 best/nominal FEASIBLE ; conservative III-A only
EXPECTED_III_A_RESULT_LOCK  2026-09-02T17:39 local
EXPECTED_III_B_RESULT_LOCK  2026-09-03T05:00 local (CLEAN_SKIP acceptable)
ABSOLUTE_DEADLINE           2026-09-03 20:00 local
FRIDAY_EXPERIMENT_EXECUTION_REQUIRED = false
DEADLINE_PLAN_VALIDATED = PASS
```

**The full NORMAL plan is tight and is NOT feasible under conservative implementation.** That is
recorded honestly rather than forced to pass; plans 10.2 and 10.3 close in that case with +5.37 h
and +11.73 h. Checkpoints CP0/CP1/CP2/CP3 fire at Mon 20:00, Tue 13:00, Tue 20:36 and Wed 00:48,
each derived as *deadline minus that plan's conservative tail*.
