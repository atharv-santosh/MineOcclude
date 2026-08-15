# Regime A′ P2 matched no-wall diagnostic — prospective patch freeze

**Classification:** `EXPLORATORY_MATCHED_DIAGNOSTIC`

**Role:** `CURRENT_APPARATUS_VISIBLE_READOUT_QUALIFICATION_AT_MATCHED_PHYSICAL_PATHS`

**State:** `READY_FOR_P2_CAPTURE`; no scientific P2 capture, activation, or neural result existed at this freeze.

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
uncommitted and unpushed for operator review; P3 remains prohibited.
