# 12 — Repair Summary (future-facing code only)

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY for the analysis; the code below is production
future-facing infrastructure, left UNCOMMITTED for operator + Codex review.**

## Boundary honoured
- **No historical file was modified.** `git diff` against the freeze commit is empty for every
  tracked path; all new material is untracked additions.
- No historical authority, manifest, result, progress/event ledger, terminal verdict or Codex
  freeze artifact was touched.
- Every repair lives in a **new package** (`src/mineocclude/prospective/`) that no P1/P2/P3 script
  imports, so importing it cannot alter any frozen result.
- Claude does not freeze its own repairs.

## New package: `src/mineocclude/prospective/`

| Module | Repairs | What it does |
|---|---|---|
| `clock_domains.py` | D-01 | Makes each clock nominal, requires caller-supplied cadence, and rejects invalid domains/non-finite conversions. |
| `temporal_alignment.py` | D-01 | Measures a non-negative causal FIR from finite, masked, explicitly indexed trajectories. Coverage, uncertainty, and discrepancy requirements are caller supplied; absent requirements return `MEASURED_NOT_ADJUDICATED`. Exact server-state→render/model target mappings are retained. |
| `visibility_semantics.py` | D-04 | Exposes point, silhouette, fraction, geometry, world/wall position, temporal confidence, and independent evidence. Only explicit `VisibilityPolicy` can classify; no policy returns `UNADJUDICATED`, and predicate agreement alone cannot establish stability. |
| `detection_diagnostics.py` | D-05, D-10 | Strict `bool`/`None` input, prevalence-explicit metrics, and an ambiguity-explicit identity/key/clock join that returns INVALID/AMBIGUOUS rather than selecting a row. |
| `calibration_support.py` | D-05 | Reports requested physical support, observed range, intervals, largest gap and invalid counts. Gap/end/sample requirements are caller supplied; invalid input cannot pass. |
| `path_state_gate.py` | D-06, D-09 | Enforces all declared path/state/camera/FOV/index/identity fields with explicit mappings, including camera-rounding and signed-velocity traps. |
| `run_identity.py` | D-07 | All identity and cohort membership fields are explicit and strictly typed; empty cohorts and cross-tier run IDs fail. |
| `source_provenance.py` | D-08 | Requires an exact commit and per-file SHA, independently verifying expected tree, staging index, and working bytes. Receipt preserves the historical disclaimer. |

## Requirements from Phase 12, and where each is met

| # | Requirement | Where |
|---|---|---|
| 1 | distinguish server-state time from render time | `ClockDomain.SERVER_ENTITY_STATE` vs `CLIENT_RENDER` |
| 2 | distinguish render time from capture/video time | `CLIENT_RENDER` vs `CAPTURE_FRAME` / `VIDEO_FRAME` |
| 3 | distinguish capture time from model-frame time | `CAPTURE_FRAME` vs `MODEL_FRAME`; `TimebaseSpec.server_ticks_per_model_frame` |
| 4 | validate **real entity** render/state timing | `AlignmentEvidence` takes real logged + rendered series |
| 5 | not rely solely on synthetic action/camera timing | `EvidenceScope` names both; receipts record which was used |
| 6 | estimate lag independently of neural performance | no decoder input exists in the module; asserted in the receipt |
| 7 | measure uncertainty | caller-requested Student-t and trajectory-bootstrap summaries; per-trajectory fits retained |
| 8 | support both motion directions | direction carried per evidence item; tested both ways |
| 9 | fail closed if alignment cannot be established | `require_resolved()` → `UnresolvedAlignment` |
| 10 | machine-readable receipts | `AlignmentEstimate.receipt()`, and `.to_dict()` on every result type |
| 11 | expose the exact target mapping per model frame | each fit receipt records render/model index and all contributing server-state ticks |
| 12 | deterministic tests | 196 tests, all seeded where randomness is used |

**No final scientific alignment tolerance is chosen.** No existing authority specifies one, so the
modules report the estimate and its uncertainty and leave acceptance to a future authority.

## Deliberately NOT done
- No historical result recomputed into any historical artifact.
- No new authority drafted or frozen.
- No thresholds chosen (visibility, alignment tolerance, hidden-onset bounds, calibration bounds).
- No commit, no push, no branch change.
