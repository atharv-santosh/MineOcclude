# Regime A′ P2 matched no-wall diagnostic — prospective patch freeze

**Classification:** `EXPLORATORY_MATCHED_DIAGNOSTIC`

**Role:** `CURRENT_APPARATUS_VISIBLE_READOUT_QUALIFICATION_AT_MATCHED_PHYSICAL_PATHS`

**State:** `PASS`; no scientific P2 capture, activation, or neural result existed at the prospective authority freeze.

## Patch acceptance

The minimal server-side `startspec` patch is accepted prospectively. It permits
`Scene.NO_WALL` alongside `Scene.NORMAL` and passes the selected scene into the
episode configuration. `Scene.NO_SHEEP` remains refused. No client-renderer code
was modified.

The installed patched JAR is
`febf31cad7c6de003a6d2d87ed9183c6a6739e086e293b30e92999520e3bfaba`.
NORMAL path/state replay is exact across 520/520 coordinate frames, with maximum
coordinate difference `0.0`; spec identity, ordering, timing, and NORMAL
semantics are unchanged.

## Pixel-gate supersession

The prior patch gate required exact rendered-pixel equality. An identical-binary
repeat on the current renderer produced only 4/18 exact sampled frames, proving
that exact RGB equality is not a satisfiable deterministic criterion on this
apparatus. Its disposition is:

`NOT_APPLICABLE_AS_PATCH_INERTNESS_GATE_DUE_TO_EMPIRICALLY_ESTABLISHED_RENDERER_NONDETERMINISM`

This is not a pixel PASS claim. No numerical, detector-aware, or other pixel
tolerance is introduced, and no GPU renderer-sensitivity study is performed.
The historical pixel-equivalence `FAIL` remains preserved and may not be
reinterpreted as a clean historical wall/no-wall contrast.

The current P2 renderer is bound as Mesa 25.2.8-0ubuntu0.24.04.2, llvmpipe
(LLVM 20.1.2), Xvfb 21.1.12. Future confirmatory A′ requires fresh paired
wall/no-wall collection under one prospectively pinned apparatus.

## Remaining gates

The autonomous runner must collect the 25 frozen NO_WALL specifications, persist
and validate them durably, and enforce exact path identity (`epsilon_path=0.0`).
Visibility qualification precedes any GPU use. Extraction, if authorized by
capture/path/visibility, is layer 4 only. Final scientific results remain
uncommitted and unpushed for operator review; P3 must not be started during
this P2 session.

## Final P2 result

Capture, exact path equivalence, and current-renderer visibility all passed:
25/25 durable NO_WALL trajectories, 475/475 jointly geometric- and
magenta-visible targets, and maximum path difference `0.0`. Layer-4-only
extraction produced 475 rows (`653,724,800` bytes) with all local hashes and
durable receipt readbacks exact.

The frozen trajectory-grouped visible readouts both qualified:

| Readout | RMSE (blocks) | MAE (blocks) | Macro R² | Whole-trajectory bootstrap 95% |
|---|---:|---:|---:|---:|
| BEST-K | 0.166027 | 0.133158 | 0.790695 | [0.723873, 0.847242] |
| FULL_TOKEN_GRID | 0.166577 | 0.134004 | 0.754803 | [0.621274, 0.855558] |

Both macro R² values and both bootstrap lower bounds exceed the prospectively
frozen threshold of zero. `P2_DECISION=GO_BEST_K_FULL_VISIBLE` and
`P3_ALLOWED=true`; P3 was not started.

This establishes only current-apparatus visible-readout qualification at the
matched physical paths/times. It does not establish hidden-state decoding,
memory, object permanence, belief, a clean historical pixel-causal contrast,
or confirmatory Regime A′ success. Historical comparison remains
`DESCRIPTIVE_CROSS_APPARATUS_CONTEXT_ONLY`.
