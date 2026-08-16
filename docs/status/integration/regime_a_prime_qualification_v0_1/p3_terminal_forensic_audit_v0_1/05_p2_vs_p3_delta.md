# 05 — P2 → P3 Forensic Delta

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**

## The headline
P2 passed strongly (BEST-K RMSE 0.1660, macro R² 0.7907, bootstrap lower 0.7239). P3 failed before extraction.
**The apparatus did not change. The visibility gate did.**

## Structured delta table

| Dimension | P2 (matched NO_WALL visible qualification) | P3 (sequential development preflight) | Δ |
|---|---|---|---|
| Renderer / Java / mods / Minecraft | Corretto 17.0.20.8.1, Xvfb 21.1.12, Mesa 25.2.8, llvmpipe LLVM 20.1.2; mod `febf31ca…` | identical (`installed_mod_sha256 = febf31cad7c…`, `mod_source_sha256 = 3c372276…`, verified in preflight) | **none** |
| Camera / FOV / resolution | layout_01 fixed, eye (0.5, 5.62, −5.5), FOV 70°, 640×360 → 384×224 | identical (`fixed_apparatus`, `camera_fixed: true`) | **none** |
| Frame cadence / lockstep | 20 Hz, 1 action / 1 frame / 1 server tick | identical | **none** |
| Capture loop / packaging | `p2c_capture.py` `CaptureSession`, `package()` | **same code, imported directly** by `p3_run_sequential.py` | **none** |
| Wall geometry | layout_01 long wall | identical layout/authority | **none** |
| **Scene mode** | **NO_WALL only** (matched to historical wall runs by replay) | **paired NORMAL + NO_WALL, 25 each** | **MATERIAL** |
| Trajectory source | 25 **historical Regime A first25 v2** specs, replayed | 75 **new** frozen specs, new seeds (`MINEOCCLUDE_P3_DEV_V0_1` namespace) | new identities |
| Speed | inherited from Regime A specs (nominal speed held identical) | **swept: 2.0 / 2.5 / 3.0 b/s** — the only variable | **MATERIAL** |
| Noise generation | historical frozen draws | `default_rng(seed).standard_normal(180)·√(q·dt)`, q = 0.05 | equivalent form |
| Target times | 19 τ per spec, frozen | 19 τ per spec, placed at `first_stable_hidden_onset + phase` | placement rule new |
| Path gate | exact bit-for-bit vs replayed historical coordinate, ε = 0 | exact sha256 of `sheep_x` + NORMAL≡NO_WALL, ε = 0 | equivalent, both PASS |
| **Visibility gate rule** | **"all 475 frozen NO_WALL targets must be detector-visible AND geometric-visible"** | (a) 475 NO_WALL visible-AND-detected, (b) **475 NORMAL occluded-AND-not-detected**, (c) **NEW: ≥0.95 precision AND ≥0.95 recall of detector vs geometry pooled over 720 all-frame calibration rows** | **MATERIAL — this is the cause** |
| Visibility rows evaluated | 475, **all in NO_WALL**, all at target ticks | 950 target rows **+ 2160 calibration rows across the full lane traverse** | **MATERIAL** |
| Occluded frames ever scored | **zero** | **936 per candidate** (calibration) + 475 NORMAL targets | **MATERIAL** |
| Calibration runs | none required | 4 per candidate, **all `scene = NORMAL`** | **new** |
| Extraction prerequisites | gated on path equivalence PASS | gated on path **+ visibility + headroom** PASS | stricter |
| Headroom gate | none | new prospective gate (2×/3× P2 RMSE) — **passed easily ×3** | new, benign |

## The assumption that was valid in P2 and invalid in P3

> **In NO_WALL the mod hardcodes `geometricVisible = true`** (`EpisodeManager.java:437-444`, with an explicit
> comment that testing the "phantom wall volume" in the control wrongly labelled it occluded).

Therefore **P2's visibility gate could not fail for geometric reasons and never evaluated a single occluded or
transition frame.** Its `geometric_visible_rows = 475` is a tautology, not a measurement. P2 established that
the detector *sees a visible sheep* — nothing about detector↔geometry **agreement**.

P3 then introduced, for the first time, a gate that scores detector↔geometry agreement **in the wall scene
across the occlusion transition** — the one regime in which the two quantities are known to disagree. P2
provides **no evidence whatsoever** that this new gate was achievable, and it was never feasibility-checked.

## Was there semantic drift?
`P2_TO_P3_SEMANTIC_DRIFT = material`, and it is **entirely in the visibility gate**. Apparatus, renderer,
camera, cadence, capture code, packaging, path semantics and headroom are unchanged or strictly additive and
benign. P2's "GO_BEST_K_FULL_VISIBLE" decision remains sound *for what P2 actually tested*; it simply did not
license the inference that a detector↔geometry precision gate would pass on the wall scene.
