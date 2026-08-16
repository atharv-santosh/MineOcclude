# 06 — Source / Git History / Regression Audit

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.** No commit, push, or source change was made.

## Repository state
- HEAD `e56d90b3da11966e30119dc0efe39fa3b13f1b5c` = "Freeze Regime A-prime P3 development authority"
- Branch `exploration/regime-a-prime-qualification-v0-1`; `origin/<branch>` at the same commit
- Working tree: **13 untracked files, 0 modified, 0 staged** — the P3 controller, its progress/terminal/event
  ledgers and per-candidate ledgers were **never committed**. The frozen authority + manifest **are** committed.

> **Finding G-0 (data-integrity/process):** `p3_run_sequential.py` — the program that produced every P3 verdict —
> is **untracked**. Its own `static_preflight()` asserts `head == AUTHORITY_HEAD`, giving the *appearance* of code
> provenance, but the controller source is not covered by that hash. The `p3_terminal_result.json` hash list
> records the authority, manifest and ledgers, but **not** the controller. P3's verdicts are therefore not
> reproducibly bound to a specific controller revision.

## Traced origins

### `HIDDEN_BOUNDS` — a twice-patched empirical constant (the key regression)
`p3a_freeze.py:39-42` hardcodes:
```
LEFT_TO_RIGHT: (-3.7309960703951197,  5.42739195539593)
RIGHT_TO_LEFT: ( 4.837594280703691,  -4.4614025063149105)
```
These are copied verbatim from
`docs/…/regime_a_occlusion_extraction_v0_1/v2_amendment_1/directional_visibility_authority_v2_1_amendment_1.json`
(`planning_calibration.directional_hidden_entry/exit`), which is a **bound source** of the P3 authority.

Lineage:

| Version | LTR hidden entry | RTL hidden entry | entry guard frames (LTR/RTL) | trigger |
|---|---|---|---|---|
| Regime A v2 (`src/mineocclude/regime_a.py:189-196`) | −3.9567355841 | +5.0668083372 | 11 / 13 | original calibration, 2 crossings/dir |
| **v2.1 amendment 1** (used by P3) | **−3.7309960704** | **+4.8375942807** | **18 / 20** | `t04 TRUE_FROZEN_GUARD_EXCEEDANCE` — the guard was **already exceeded once at Regime A's own speed**, 8 crossings/dir |

> **Finding G-1 (implementation / stale constant):** the amendment's own fields —
> `geometric_hidden_boundary_point_world_x` (LTR −4.8325, RTL +5.8342) vs
> `stable_dual_hidden_entry_conservative_world_x` (LTR −3.7310, RTL +4.8376) and
> `guard_rule = "directional maximum consecutive partial/disagreement run plus one captured frame"` with
> `replication_diagnostics.entry_run_max = 17 (LTR) / 19 (RTL)` — **formally record that geometric and rendered
> visibility disagree over a run of up to 17–19 frames.** My measurements reproduce these numbers to ~0.01–0.07
> blocks. The project therefore *already knew and had frozen as authority* the very disagreement that P3's new
> ≥0.95-precision calibration gate then declared a failure. **The gate contradicts a source the same authority
> binds.**

> **Finding G-2 (implementation / stale constant):** `HIDDEN_BOUNDS` is a **fixed world-x constant applied to
> three different speeds**, with no speed term. It carries ≈0.01 blocks of margin at v = 2.0 and goes negative
> above it (see `03_visibility_forensics.md` §5). The amendment history shows this class of constant has been
> exceeded and re-patched once before — P3 is the **second regression of the same root cause**, now surfacing
> as target-row contamination 0 → 1 → 7.

### Geometric visibility (`EpisodeManager.java:434-462`)
History: `4625451` (original mod) → `0e5f5ad` "Fix no-wall control visibility" → `8213c79`/`0f6bdef` runtime
geometry → `7a78226` lockstep. Two surviving in-code comments document prior repairs:
- **NO_WALL branch** (`:437-444`): hardcodes `geometricVisible = true`; comment records that testing the phantom
  wall gave "geometric 5/200 while the detector saw the sheep 200/200". *This is the source of P2's tautological
  pass — see `05_p2_vs_p3_delta.md`.*
- **Wall branch** (`:445-459`): tests against the **as-built** block-inflated wall
  (`floor(wallSegMin)`, `ceil(wallSegMax)+1.0`, `floor(wallOrtho)+0.5`, half-thickness 0.5); comment records an
  earlier bug where using the raw spec "declared visible while the rendered wall still occluded the sheep".
  **Independently verified correct**: the resulting shadow is symmetric about the camera x = 0.5 to within
  0.08 blocks, and the lag-corrected geometric edge matches the observed onset of silhouette occlusion.

> **Finding G-3:** the mod's visibility is, and has always been, a **single-ray point test** to
> `(sheepX, sheepY+0.5, sheepZ)`. No revision ever tested the target's bounding box or silhouette. Every
> downstream consumer that treats it as "the target is (in)visible" inherits a ~1-block error band.

### Temporal alignment
`capture_package_v0_1.json` (produced by `p2c_capture.package`, shared P2/P3) records
`temporal_alignment.status = "verified"` but `evidence_scope = "synthetic_contract_only"`, covering
`action_idx 1 → effect_server_tick 2` and camera impulse response only.

> **Finding G-4 (apparatus):** **no revision of the pipeline has ever verified rendered *entity* position against
> logged entity position.** Grep across `scripts/regime_a_prime_qualification_v0_1/` and `src/mineocclude/`
> finds no render-lag / lerp / tick-offset correction anywhere; the only "lag" symbols are
> `capture_lag_nanos_*` (wall-clock I/O latency, `regime_a.py:399-410`), a different quantity. The measured
> ≈3.3-tick entity render lag has therefore been present and unmeasured across Regime A, P2 and P3.

### Other traced items
- `first_stable_hidden_onset` (`p3a_freeze.py:90-99`): requires 31 consecutive in-bounds frames; correct for
  max phase 12 + 19 targets. Sound — but inherits **G-2** through `HIDDEN_BOUNDS`.
- Detector config `detector_candidate_config.json` (`99acc45e…`) — hash-bound and unchanged between P2 and P3.
- Direction handling: `design_cells()` gives 13 LTR / 12 RTL, every phase once per fold. Verified balanced.
- `run_id` namespace: P3 capture packages are stamped `episode_manifest.run_id = "mineocclude-regime-a-first25-v2"`
  and `trajectory_id = layout_01_ep7xxxx` inherited from the shared packager. **Finding G-5 (bookkeeping):**
  P3 development units carry the *Regime A scientific* run identity even though the authority declares them
  `permanently_excluded_from_confirmatory_a_prime`. Episode IDs (72001+, 75101+) and spec IDs (`p3dev_*`) are
  unique, so no collision occurred, but selection *by `run_id`* would silently sweep P3 development data into a
  Regime A cohort. Must be fixed before any confirmatory collection.
