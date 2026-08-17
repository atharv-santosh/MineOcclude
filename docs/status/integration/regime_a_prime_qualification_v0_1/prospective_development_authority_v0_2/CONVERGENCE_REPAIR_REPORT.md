# Prospective package convergence repair report

**Status:** `READY_FOR_FRESH_INDEPENDENT_FREEZE_REVIEW`

No data was collected, no historical frozen artifact was modified, and no
commit, push, or freeze was performed.

## Repaired independent and analogous blockers

- B04 projection is derived from raw finite screen coordinates, half-open
  authority frame bounds, integer token-cell bounds, and the declared floor
  screen-to-token mapping. Dimensions and the supplied Boolean are verified.
- B05 Stage 2 now requires the exact Stage-1 evidence file and independently
  reproduces the complete decision before accepting its PASS status or hashes.
- B06 authorization validates the full 25-cell fold×phase allocation, frozen
  direction balance, fixed speed, 50 paired captures, extraction allocation,
  and pipeline order. Physical summaries and labels are reconstructed from
  durable-inventory-bound raw files.
- B07 runtime provenance covers and rehashes the complete 40-file local import
  closure used by projection, capture, packaging, extraction, and readout.
- B08 every direct backend phase revalidates predecessor bindings and remote
  object bytes; verified durable units remain non-recollectable.

## Checkpoint 2 — provenance, authorization, and stage binding

- **C01 temporal agreement rule was scientifically wrong and is replaced.** The
  superseded rule required the causal FIR *first moment* and the derivative
  cross-correlation *single-tap lag* to fall inside each other's confidence
  intervals. Those are different functionals of the same kernel. Checked against
  the frozen P2/P3 forensic reference the rule fails outright: FIR
  `3.363631073825902` t95 `[3.1850024634276997, 3.5422596842241045]` against
  cross-correlation `2.4597455789132974` t95 `[2.2587886058224114,
  2.6607025520041834]` — disjoint intervals, mutual containment violated by
  `0.7252568845144023` ticks. Worse, the rule was satisfiable only by a kernel
  whose mode equals its mean, i.e. the symmetric or bare-delay response this
  same authority forbids, so it was anti-correlated with the authority's own
  scientific position and contradicted the frozen `B < A < C` finding. The
  repaired rule pairs matched estimands: the cross-correlation lag against the
  *mode* of the bound FIR kernel, per trajectory and in aggregate, inside the
  estimator's own `+-1`-tick parabolic-refinement clamp, with both estimates
  inside the aggregate kernel's positive-mass support and all endpoints inside
  the admissible causal range. The frozen reference satisfies it with
  `0.607234` ticks of unused slack. The identification is evidence-derived:
  `argmax(per-trajectory kernel)` equals the best single-tap delay in 12/12
  frozen trajectories. The bound is the estimator's structural clamp, not a
  fitted tolerance, and no Stage-1 outcome was consulted.
- **C02 A4 provenance no longer passes on self-assertion.** `verify_signed_probe`
  accepted any document carrying `status=PASS`,`independently_derived=true`,
  `asserted_by_evidence_builder=false` and a hash of itself — every one a claim
  the evidence builder could emit with no probe existing. It is replaced by
  `verify_probe_execution`, which re-derives probe source bytes, argv, resolved
  executable bytes, exit status, and normalized output from disk, requires the
  authority's own identity tokens in that output, and rejects any producer on
  the forbidden list. The digest is named a digest: no signing mechanism exists
  here, so nothing is called a signature.
- **C03 A6 binds stage to manifest, namespace, unit role, and receipt type.**
  `--stage stage1-capture --manifest stage2_locked_manifest.json` and every
  lower-level equivalent now fail before capture or extraction, at the direct,
  delegated, controller, backend, and restart/resume entrypoints. The durable
  controller checks each unit's namespace and declared stage before reuse as
  well as before launch.
- **C04 both receipts are generated, not hand-written.**
  `generate_receipts.py` derives every boolean from the verifier that
  establishes it. Source-commit binding is two-step —
  `PRE_FREEZE_VERIFIED` -> freeze -> `--freeze-commit` re-verification that
  committed bytes equal reviewed bytes -> `FROZEN_VERIFIED` — which avoids an
  impossible self-referential commit hash. A pre-freeze receipt authorizes
  nothing.
- **C05 runtime reconstruction is deterministic.** The Java identity pin was
  `Amazon Corretto 17.0.20.8.1`, a spelling the JDK never emits; the probe's own
  substring test could not have matched and Stage-1 capture would have aborted
  at launch. Corrected to `Corretto-17.0.20.8.1`. The pinned JDK is resolved
  from the authority and invoked by absolute path, never from PATH, and the
  pinned virtual display is reconstructed rather than inherited. See
  `RUNTIME_RECONSTRUCTION.md`.
- **C06 the fast E2E is aspect-ratio-preserving.** `320x32` became `160x90`, an
  exact quarter-scale reduction of the authority's `640x360`. The native-frame
  run is a separate required one-time pre-freeze check; see
  `FULL_FIDELITY_E2E.md`.

The convergence acceptance suite is 102 tests, plus 2 end-to-end Stage-1
evidence-builder regressions and 53 checkpoint-2 adversarial tests covering
probe-execution provenance, cross-stage binding, and the receipt generators.
Together with the independently frozen prospective-infrastructure tests, the
complete prospective suite is 353 tests.

`STAGE_1_COLLECTION_AUTHORIZED=false`

`STAGE_2_COLLECTION_AUTHORIZED=false`

`REGIME_A_PRIME_COLLECTION_AUTHORIZED=NO`

`CONFIRMATORY_COLLECTION_AUTHORIZED=false`
