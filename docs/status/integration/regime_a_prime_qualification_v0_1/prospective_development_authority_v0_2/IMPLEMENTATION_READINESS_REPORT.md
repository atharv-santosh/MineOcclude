# Prospective development package — bounded-repair readiness

`IMPLEMENTATION_STATUS=READY_FOR_FRESH_INDEPENDENT_AUTHORITY_FREEZE_REVIEW`

No capture, Minecraft launch, extraction, commit, push, or self-freeze occurred.
All collection flags remain false. Runtime HEAD is bound after freeze by the
independent pre-outcome and authorization receipts; JAR and authorization
hashes remain explicit fail-closed materialization fields.

## Repaired blockers

- **B01:** temporal measurement is separate by direction; the invalid CI-width
  gate and n=8 scaling are removed. Four exact trajectories per direction are
  required by receipt identity. Aggregate intervals and the causal FIR kernel
  are reconstructed from trajectory-level estimates and kernels; CI width is a
  reported Stage-1 measurement.
- **B02/B03:** causal FIR and derivative cross-correlation execute separately,
  emit their own estimates/intervals/evidence IDs, and must satisfy the
  authority-supplied 95% interval-overlap rule. Counts cannot substitute for a
  method or agreement.
- **B04:** unsupported extent/guard/support cutoffs are removed. WALL replicate
  1 measures complete transition intervals; replicate 2 validates them.
  NO_WALL requires physical/render evidence. Both coordinates, exactly 19
  explicitly identified hidden rows, and every contamination class are derived
  from row evidence. Raw screen/token coordinates are checked against
  authority-bound half-open frame/grid bounds and their mutual floor mapping;
  contradictory rows, dimensions, Booleans, and stale summaries fail.
- **B05:** Stage 2 requires a real on-disk Stage-1 decision and separate receipt
  binding authority, both manifests, Stage-1 evidence and decision SHA/status,
  source commit, provenance receipt, payload hash, and run namespace. The
  on-disk evidence is re-evaluated and must reproduce the exact decision.
  Direct capture, delegated, and backend commands repeat the authorization check.
- **B06:** Stage-2 windows are materialized only after frozen Stage-1 physical
  measurements. Labels are independently rebuilt through the qualified causal
  FIR. Fold/phase/direction/pair allocation is revalidated against authority at
  runtime, and physical summaries are rebuilt from bound durable raw files. All
  physical/pair gates and the WALL training-only time-baseline gates precede
  extraction/readout qualification.
- **B07:** the runner probes Git, Java, renderer stack, mod/JAR, detector, and
  the complete 37-file local runtime import closure, then independently rehashes
  those bytes and verifies camera, FOV, frame
  dimensions, target UUID, respawn count, layout authorities, and WALL/NO_WALL
  physical behavior from captured bytes. Evidence builders cannot assert
  success.
- **B08:** local completion state is reusable only after receipt/hash/binding
  checks plus remote checksum-manifest download, unit/authority/manifest/source/
  run binding, and every-object byte rehash. Direct backend phase boundaries
  repeat predecessor remote-durability verification. Three identical attempts
  are explicit; verified durable units skip without recollection.

## Stage-1 minimality

Eight runs remain the minimum replicated full-factorial design:

```text
2 directions × 2 scenes × {transition measurement, held-out validation} = 8
```

The four runs in each direction supply both temporal estimators. The WALL roles
prevent measuring and validating the transition on the same run; the NO_WALL
roles likewise separate physical/temporal support from held-out visible-control
scoring.

## Stage-2 draft boundary

`stage2_locked_manifest.json` is intentionally a template, not an executable
locked campaign. It contains fresh identities and deterministic paths but no
target windows. After frozen Stage-1 PASS, `build_manifests.py
--stage1-decision ...` deterministically materializes 19-row windows, causal-FIR
labels, and corrected 2×/3× headroom checks. That resulting manifest requires a
separate freeze and authorization. The template is rejected by the Stage-2
barrier.

## Traceability

`NUMERIC_TRACEABILITY.md` classifies every scientific number as
`FROZEN_EVIDENCE_DERIVED`, `PROSPECTIVE_STAGE1_MEASURED`, or
`PURE_IMPLEMENTATION_CONSTANT`; no value is classified `UNJUSTIFIED`.
`FORENSIC_CONTINUITY_MATRIX.md` records every material frozen finding and its
prospective disposition.

`NEXT_ALLOWED_ACTION=fresh independent authority/Stage-1 freeze review; no collection`

## Deterministic acceptance entrypoint

```text
python3 scripts/regime_a_prime_qualification_v0_2/acceptance_harness.py
```

This no-collection harness runs the 94-test B01–B08/adversarial suite, numeric
and forensic document audits, package/binding verification, and compilation.
