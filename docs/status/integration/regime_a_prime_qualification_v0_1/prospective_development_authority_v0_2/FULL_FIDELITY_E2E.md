# Freeze-boundary full-fidelity end-to-end check

**Label: DEVELOPMENT_ONLY. Runs no collection, starts no Minecraft, observes no
scientific outcome.**

## Why this exists separately

`tests/prospective/test_stage1_evidence_builder_end_to_end.py` drives the real
builder over a synthetic capture at a **reduced** canonical frame so it can run
inside the acceptance harness. It is a software regression, not apparatus-fidelity
closure evidence.

| | Fast E2E | Freeze-boundary E2E |
|---|---|---|
| `canonical_frame_pixels` | `[160, 90]` | `[640, 360]` (the authority's own) |
| Aspect ratio | 16:9, exactly 1/4 scale | 16:9, native |
| Runtime | ~110 s | ~25 min |
| Runs in acceptance harness | yes, every invocation | **no** |
| Status | required, every convergence | **required exactly once, before freeze** |

The fast E2E reduces only `canonical_frame_pixels`. Every scientific policy it
exercises -- temporal agreement, visibility, contamination, completeness,
pure-delay refusal -- is the frozen authority's own. The reduction is
aspect-ratio-preserving, so the projection geometry the evaluator reasons about
is the authority's 16:9 rather than a distorted strip.

`detect_magenta` is pure Python and scans every pixel of every frame, so the
native frame costs roughly 12x the reduced one. That cost is the only reason the
native run is not in the harness. It is **not** optional: the reduced frame
cannot demonstrate that the detector, the centroid resolution, and the causal FIR
reconstruction behave at the resolution the apparatus will actually produce.

## Required command

Run once, from the repository root, immediately before the freeze, on an
otherwise idle machine:

```
MINEOCCLUDE_FULL_FIDELITY_E2E=1 python3 -m pytest \
  tests/prospective/test_stage1_evidence_builder_end_to_end.py \
  -q --no-header -p no:randomly
```

The environment variable selects `[640, 360]` in place of `[160, 90]`; without
it the module runs at the reduced frame, which is what the harness does.

## Expected output

```
..                                                                       [100%]
2 passed in <t>s
```

Both cases must pass, and their meanings are asymmetric:

1. `test_real_builder_evidence_reaches_a_legitimate_stage1_pass` -- the real
   builder, over a synthetic apparatus capture rendered with a causal two-tap
   smoothing kernel at lags 3 and 4, produces an evidence document that the
   frozen `Stage1Evaluator` grades `PASS` with no reasons, and the reconstructed
   kernel recovers the renderer's actual taps (true group delay 3.5 ticks,
   asserted to +-0.05).
2. `test_effectively_pure_delay_render_is_refused_by_the_real_builder` -- a bare
   integer-tick delay render is refused with `FIR alignment unresolved ... pure
   delay`, and **no evidence document is written**.

A pass on case 1 with a failure on case 2 is worse than both failing: it would
mean the pure-delay refusal is inactive at native resolution.

## Recording the result

The freeze is not authorized until this run is recorded here:

```
FULL_FIDELITY_E2E_RUN_AT_UTC=
FULL_FIDELITY_E2E_COMMIT=
FULL_FIDELITY_E2E_RESULT=
FULL_FIDELITY_E2E_DURATION_SECONDS=
```

Status as of this checkpoint: **DEFINED, NOT RUN.** Deliberately not executed
during repair; running it repeatedly wastes ~25 minutes per iteration and proves
nothing the fast E2E has not already proven about the software path.
