# Person A/B Handoff Rehearsal Runbook (Steps 9.4 and 9.5)

Purpose: prove that Person A and Person B can operate Person C's collection
workflow, Person D's baseline workflow, and Person E's measurement workflow from
a clean checkout, without the owning role present and without changing
experiment code.

Every rehearsal writes a machine-readable receipt through:

```
python scripts/run_clean_mvp.py rehearsals
```

Receipts land in `docs/status/person_a_phase9_clean_run_v0_1/step_9_4_9_5_rehearsals.json`.

A rehearsal that cannot be completed records `status: BLOCKED` with the exact
blocking step and every missing instruction it found. It never records a
success it did not achieve.

## Credential rule (applies to all three rehearsals)

Credentials travel only through the approved out-of-band channel. They are never
placed in Git, in an S3 object, in a log, in a notebook, or in chat. No receipt
in this repository contains a credential value, and the receipt records that
fact explicitly.

## 9.4 — Person C collection rehearsal

Source runbook: `docs/runbooks/person_c_layout_reconstruction_checklist.md`

| Step | Action | Acceptance |
|---|---|---|
| C.1 | Read C's clean-machine runbook end to end. | The runbook is published and readable. |
| C.2 | Start the Minecraft server and reset world state. | Server reaches a ready state from a documented command sequence. |
| C.3 | Capture, validate, and accept one new trajectory. | The trajectory passes the same acceptance checks C applies. |
| C.4 | Upload, download, append to the accepted manifest, shut down. | The appended manifest validates and the server shuts down cleanly. |

Repeat until one new trajectory passes without C changing experiment code. Any
instruction that had to be supplied verbally is recorded as an instruction gap
and returned to C for a runbook correction.

### Current status

BLOCKED at C.2. This environment has no Minecraft server, no Java runtime, and
no access to the approved credential channel. Two instruction gaps are recorded:

1. C's runbook does not yet publish a single clean-machine server
   start/reset/shutdown command sequence that A or B can run unaided.
2. The approved secret channel is named but its access procedure is not
   documented for A/B.

## 9.5 — Person D baseline rehearsal

Source runbook: `docs/baselines/person_d_phase1.md`

| Step | Action | Acceptance |
|---|---|---|
| D.1 | Read D's locked baseline workflow. | The workflow and its frozen config are published. |
| D.2 | Invoke the baseline workflow from the clean accepted manifest and folds. | The workflow runs without A/B editing result logic. |
| D.3 | Compare baseline output identity against the clean run. | Outputs trace to the clean run's run and artifact identities. |

### Current status

BLOCKED at D.2. The complete MVP accepted manifest and activation index do not
exist yet, so there is no clean run for the baseline workflow to consume.

## 9.5 — Person E measurement rehearsal

Source runbook: `docs/operations/person_e_phase1_runbook.md`

| Step | Action | Acceptance |
|---|---|---|
| E.1 | Read E's runbook and measurement contract. | Both are published. |
| E.2 | Confirm E's immutable registry accepts a Person A run/artifact ledger unchanged. | E's validator accepts A's projection with zero rejections. |
| E.3 | Invoke E's measurement entry point on clean-run clips. | Measurement consumes the complete bundle and preserves lineage. |

### Current status

E.1 and E.2 are COMPLETE. `mineocclude.experiments.mvp_lineage` projects Person
A's ledger onto Person E's frozen immutable run/artifact registry schema, and
`validate_immutable_run_artifact_registry` accepts it with zero rejections; this
is asserted by `tests/experiments/test_mvp_lineage.py`.

E.3 is BLOCKED: no U4 rollout clips exist, because generation requires Person
B's final direction/dose request and an authorized model runtime.

## Returning defects

An interface defect found during a rehearsal is returned through A/B review and
a versioned rerun. It is never worked around by editing the owning role's
result logic inside a Person A module.
