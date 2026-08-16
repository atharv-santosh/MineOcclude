# 15 — Codex Freeze-Blocker Repair

**Scope:** bounded R1–R8 repair only. No capture, Minecraft launch, P3 restart,
authority draft, historical-result edit, commit, or push occurred.

| Blocker | Repair | Adversarial evidence |
|---|---|---|
| R1 source provenance | Requires exact 40-hex commit and per-file SHA; independently reads expected tree, index, and working bytes; empty/duplicate lists fail | staged-only addition, staged edit with clean worktree, unstaged edit, deletion, rename, correct file, wrong commit/hash, missing commit/path |
| R2 path/state gate | Enforces run/episode/spec, seeds and noise schedule, direction/speed, full xyz path/start state, camera eye/yaw/pitch/FOV, exact server/render/action/model mapping, scene, target identity/ticks, cadence, and pair equality | every declared field mutated independently; yaw, pitch, FOV, render frame, action index, and server tick specifically covered |
| R3 calibration support | Rejects/reports non-finite and malformed values; empty input is INVALID; reports range, intervals, largest gap, counts, requested support; gap/end/sample requirements are caller supplied | NaN, both infinities, strings, bools, objects, empty observations, endpoint shortfall, internal gap |
| R4 diagnostics + D-10 | Detection state accepts only exact `bool`/`None`; explicit identity/key/clock join reports VALID, INVALID, or AMBIGUOUS and never selects among candidates | strings, ints, floats, NaN, containers; duplicate identities/keys, missing identity/index, run mismatch, multiple candidates, incompatible clocks |
| R5 temporal alignment | Separates measurement from adjudication; removes trajectory/tolerance/timebase defaults; requires explicit masks, scenes, finite arrays, unique identities, valid directions/speeds and exact index mapping; caller supplies coverage, uncertainty, and discrepancy requirements | same-direction, single-speed, missing/invalid masks, NaN, duplicate IDs, bad direction/speed, insufficient support, missing uncertainty, policy pass/fail |
| R6 visibility | Separates measurements from explicit `VisibilityPolicy`; no thresholds default; no policy returns UNADJUDICATED; stable regimes require policy-selected independent/temporal evidence | agreeing wrong predicates unresolved; point/silhouette disagreement, visible, occluded, partial, missing/conflicting evidence, explicit policy |
| R7 Regime A | Replaced the rejected quadrature claim with a direct deterministic FULL and BEST-K refit using persisted activations/state and the causal FIR correction | all duration domains plus τ8..15 and beyond-context; fixed-target last-seen sensitivity directly recomputed |
| R8 reporting | Replaced categorical universality claims with observed-condition language; primary interval is Student-t; trajectory bootstrap reported separately | t interval [3.185, 3.542], bootstrap [3.219, 3.522] |

Two additional fail-closed hardenings were found during the bounded sweep:
`RunIdentity` no longer defaults confirmatory membership or accepts an empty
identity cohort, and clock-domain values/conversions reject invalid domains and
non-finite values.

The prospective suite after bounded repair #2 is **196 passed** (baseline: 94
passed). Follow-up mode/type/count/unit/precedence repairs are recorded in
`20_bounded_repair_2.md`.
