# Prospective development package — bounded-repair test report

**Base:** `db2e110549856a465ae517c17438d4d248d9657b`  
**Scientific capture:** none  
**Minecraft launched:** yes — non-scientific operational smoke only (server
started, client joined, 0 frames captured, torn down; see *Real non-scientific
operational smoke* below)

## Successor repair context

This report covers the successor repair working tree, not a freeze.

| | |
|---|---|
| Historical BLOCKED freeze | `95d6fe9f664b701c10536e7cda90b7f981e0319f` |
| Stage-1 state at that freeze | `STAGE1_BLOCKED` |
| Valid scientific units at that freeze | 0 |
| Stage-1 collection during this repair | none |
| Successor freeze created | no |

The historical freeze is **not** amended and its BLOCKED result stands. No
scientific threshold or gate logic was changed by this repair.

The six defects from the independent cold review were repaired:

| | Defect | Disposition |
|---|---|---|
| D1 | capture startup source outside the runtime-critical closure | repaired |
| D2 | provisioning script outside the runtime-critical closure | repaired |
| D3 | operational smoke authorized by self-asserted booleans | repaired |
| D4 | smoke ran against a generic pre-created 1280x720 display | repaired |
| D5 | `__exit__` could block forever on a reader-less FIFO | repaired |
| D6 | docs did not match the executable successor workflow | repaired |

Repair did not stop at D1–D6. The current freeze-record summary of what this
successor tree changes, beyond those six:

| Area | Repair |
|---|---|
| capture contract | `spec_hash`/`raw_capture_spec_hash` production contract repaired, so a frozen unit builds a spec the reused v0.1 interface accepts |
| capture spec construction | single production/shared capture-spec construction path (`derive_effective_capture_spec`), used identically by capture and by the smoke preflight |
| startup | partial-startup cleanup, so a failed launch cannot leave the apparatus half-up |
| preflight | capture-toolchain preflight that verifies presence and linkability rather than assuming it |
| source closure | runtime-critical capture-source closure expanded to cover every file whose bytes change what a capture physically does |
| smoke | replay-verifiable operational smoke, digest- and marker-checked instead of boolean-asserted |
| smoke display | production-owned `640x360x24` Xvfb/openbox smoke, distinct from the generic renderer-probe geometry |
| teardown | non-blocking `CaptureSession` teardown |
| runtime send | non-blocking/bounded `LiveRuntime.send` with explicit operational failure semantics (`OperationalCaptureError`) rather than an unbounded FIFO wait |
| Stage-2 | Stage-2 lock and adversarial revalidation |

The runtime-critical source closure ends at **40** files; see
`RUNTIME_RECONSTRUCTION.md` for the additions and why their bytes are material
to a capture.

### Real non-scientific operational smoke — ESTABLISHED

A genuine v0.2 `NON_SCIENTIFIC_OPERATIONAL_SMOKE` was executed and replays. The
capture toolchain and the pinned JDK are present again, so the toolchain gate
that previously refused this smoke no longer fires.

The run, recorded under schema `mineocclude-operational-smoke-v0.2`:

- started the real production-owned `640x360x24` Xvfb path (`xdpyinfo` confirming
  width 640, height 360, depth 24, `started_by_smoke: true`);
- started openbox (`started_by_smoke: true`);
- started the server;
- joined the client;
- crossed the capture interface (`capture_contract_crossed: true`);
- captured **0** scientific frames;
- wrote **0** scientific receipts;
- wrote **0** Stage-1 durable scientific objects;
- stranded **0** processes;
- retained no world session lock
  (`session_lock_present_after_teardown: false`);
- passed `require_operational_smoke` replay; and
- had tampered variants refused — mutating `frames_captured`,
  `scientific_receipts_written` or `stage1_durable_objects_written` each fails
  `payload_sha256` reproduction.

The smoke is bound to predecessor HEAD
`95d6fe9f664b701c10536e7cda90b7f981e0319f` **plus the uncommitted successor
runtime-critical closure** `5f86595d4adb0f07dbb254268eeaee33936000fdfe7bd00dba02ec5346a78185`.
That pairing is exactly why it is **development evidence only**: it does not
correspond to any single committed tree, and it therefore **cannot count as a
Stage-1 unit**. `counts_toward_stage1_units` is `false` and
`scientific_evidence` is `false` in the document itself.

A fresh smoke must be taken against the successor freeze commit once that commit
exists; this one authorizes nothing.

The smoke document produced by that run was written to an ephemeral working
directory and is **not** retained in this package, deliberately: it binds to an
uncommitted tree, so retaining it would invite it being cited as authorization
for a tree it does not describe. Nothing in this package references it, and the
freeze does not depend on it.

## Mandated prospective suite

```text
python3 -m pytest tests/prospective/ -q
462 passed
```

The total decomposes as the independently frozen 196-test
prospective-infrastructure suites, 59 provenance/authorization/stage-binding
tests, the 205 targeted repair regressions described below (105 authority + 100
capture/startup), and the 2 end-to-end Stage-1 evidence-builder regressions.
The targeted suites are counted here, not in addition to this total.
Adversarial coverage includes:

- contradictory temporal methods, method-identity and n/coverage mismatch,
  and fake method counts;
- scene-only NO_WALL visibility, unapplied transition bounds, missing
  wall-relative coordinates, incomplete contamination enumeration, fewer than
  19 hidden rows, and self-asserted provenance;
- fake/edited Stage-1 PASS, missing direct-command authorization, every stale
  Stage-2 authorization binding, and payload-hash tampering;
- raw same-tick labels and pure-delay kernels;
- missing WALL training-time-baseline advantage;
- runtime identity mismatch;
- stale local resume state, missing remote durable evidence, and
  authority/manifest/source resume mismatches; and
- incomplete Stage-2 physical checks and pair coverage.
- contradictory row evidence and stale contamination summaries across every
  prohibited class;
- aggregate temporal summaries/kernels inconsistent with trajectory evidence;
- manifest direction/scene/speed/frame overrides and evidence-hash mismatch;
- delegated and direct-backend Stage-2 authorization bypass attempts;
- incomplete runtime/apparatus/source provenance;
- copied remote manifests, wrong run bindings, duplicate durable identities,
  verified-unit no-recollection, and exact bounded retry behavior; and
- numeric-traceability and canonical forensic-disposition audits.
- finite-but-out-of-frame projection, token-boundary/off-by-one, wrong-dimension,
  and raw-coordinate/derived-Boolean contradictions;
- fabricated all-PASS Stage-1 decisions and rebound edited evidence;
- Stage-2 fold/phase/direction/speed/capture allocation overrides;
- local raw state or activation summaries diverging from durable inventories;
- direct-backend predecessor and remote-durability bypass attempts; and
- complete-looking runtime source hash summaries that disagree with source bytes;
- a foreign durable prefix whose URI ends in the expected unit identity;
- flipping point visibility across a whole scored class to empty it; and
- the real Stage-1 evidence builder end to end, on synthetic raw captures:
  a legitimate PASS whose temporal fields are reconstructed (never injected)
  and must recover the synthetic renderer's actual smoothing kernel, plus a
  bare integer-tick delay render the builder must refuse outright.

## Deterministic acceptance harness

```text
python3 scripts/regime_a_prime_qualification_v0_2/acceptance_harness.py
166 passed
PROSPECTIVE_ACCEPTANCE_HARNESS_STATUS=PASS
```

## Bounded-repair adversarial coverage

Two targeted suites carry this repair's regressions:

```text
python3 -m pytest tests/prospective/test_capture_contract_and_startup_repair.py -q
100 passed

python3 -m pytest tests/prospective/test_development_authority_v0_2_repair.py -q
105 passed
```

Both run inside `tests/prospective/` and are already counted in the 462 above;
they are not an independent suite to be added to it.

Beyond the capture-contract cases already recorded, this repair adds:

- **source closure (D1/D2)** — each added apparatus source is enumerated and is
  the path actually reached (`p2_common.load_live()` imports the campaign module;
  `launch_runtime` execs the provisioning script by path); a byte mutation to
  either moves the closure digest and is refused by `verify_sources` with that
  path named in the violations;
- **smoke authenticity (D3)** — the superseded hand-written PASS booleans are
  refused by schema; a mutated payload without a recomputed digest, a forged
  server-ready or client-joined digest, a correctly-digested excerpt that never
  contained the marker, out-of-order stages, and missing stage coverage are each
  refused; non-zero `frames_captured`, `scientific_receipts_written` or
  `stage1_durable_objects_written` are refused as collection;
- **display ownership (D4)** — a pre-existing display is refused rather than
  reused; the authority's generic `0 1280x720x24` probe geometry is asserted
  distinct from the capture `640x360x24`; the production `start_display` bytes
  are checked to really start both that geometry and openbox, and to contain the
  `xdpyinfo` early-return a pre-created display would trigger; smoke evidence
  reporting the generic geometry, a display the smoke did not start, or no
  openbox is refused; the smoke producer is structurally asserted not to call
  `ensure_display`, while runtime-preflight keeps its generic renderer probe;
- **teardown (D5)** — a dead server short-circuits the graceful stop; a genuine
  reader-less FIFO returns `ENXIO` instead of blocking (this test hangs outright
  against the superseded implementation); the polite path still writes when a
  reader is attached; `__exit__` runs authoritative cleanup with a dead server,
  is idempotent across repeated calls, preserves the with-block's own exception,
  and never signals processes it did not launch.

## Compile and data-format checks

```text
python3 -m compileall -q src/mineocclude/prospective tests/prospective
PASS (no output)

python3 -m compileall -q scripts/regime_a_prime_qualification_v0_2
PASS (no output)

python3 -m json.tool authority_parameters.json
python3 -m json.tool stage1_manifest.json
python3 -m json.tool stage2_locked_manifest.json
PASS
```

## Cross-artifact audit

```text
python3 scripts/regime_a_prime_qualification_v0_2/verify_package.py
PACKAGE_CONSISTENCY_STATUS=PASS
HISTORICAL_FROZEN_ARTIFACTS_MODIFIED=false
PROSPECTIVELY_CORRECTED_APPARATUS_SOURCES=scripts/regime_a_prime_qualification_v0_1/p2_common.py,scripts/run_large_scale_no_wall_campaign.py,src/mineocclude/prospective/temporal_alignment.py,src/mineocclude/regime_a.py,tests/test_regime_a_production.py
COLLECTION_AUTHORIZED=false
```

`p2_common.py` and `run_large_scale_no_wall_campaign.py` join the enumerated
apparatus sources through this repair: the first for the non-blocking,
authoritative `CaptureSession.__exit__`, the second for the non-blocking
`request_graceful_stop` it now calls.

Each prospectively corrected apparatus source is enumerated one file at a time
and carries a recorded forensic-continuity disposition; see
`PROJECTION_FORENSIC_CONTINUITY.md` for the projection crop correction and its
bounded historical blast-radius assessment.

`TEST_STATUS=PASS`

`STAGE1_AUTHORIZED=false` — every offline control converges and the mandated
real operational smoke is now established (see *Successor repair context*
above), but Stage-1 remains unauthorized for two independent reasons:

1. **No successor freeze commit exists yet.** The smoke and the closure digest
   bind to predecessor HEAD `95d6fe9f...` plus uncommitted successor bytes, which
   is not a citable tree. Provenance requires `--freeze-commit`.
2. **`runtime-preflight` cannot run.** `mesa-utils`/`glxinfo` is absent, so the
   renderer identity probe fails closed and no probe evidence — and therefore no
   provenance receipt — can be produced. See `RUNTIME_RECONSTRUCTION.md`.

Neither is a source defect. Both are cleared by the sequence recorded in
`RUNTIME_RECONSTRUCTION.md`: cut the successor freeze, restore `mesa-utils`,
re-run preflight and a fresh smoke against the new commit, then build
provenance and authorize Stage-1.
