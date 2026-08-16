# Projection crop correction — forensic continuity record

**Disposition:** `SUPERSEDED_WITH_JUSTIFICATION`
**Scope:** prospective apparatus source only. Every frozen P2/P3 artifact,
receipt, and conclusion is unchanged and remains immutable.

## The defect

`project_world_to_coordinates` mapped the frozen `layout_01` homography's raw
framebuffer output into the canonical frame by the bare resolution ratio:

```text
screen_x = raw_x * 640 / 1920
screen_y = raw_y * 360 / 1046
```

`preprocess.to_canonical` does not do that. It centre-crops the raw
`1920x1046` framebuffer to 16:9 **before** resizing to `640x360`. The corrected
mapping reproduces that crop tap for tap:

```text
crop window = (x0=30, y0=0, width=1860, height=1046)
screen_x = (raw_x - 30) * 640 / 1860
screen_y =  raw_y       * 360 / 1046
```

The superseded mapping was exact only at the frame centre, drifted to `5.88`
canonical pixels (`0.22` of a token column) at the crop edges, and silently
accepted the 30-pixel columns on each side that the crop removes altogether.

## Bounded historical blast-radius assessment

Reproduce with:

```text
python3 scripts/regime_a_prime_qualification_v0_2/projection_blast_radius.py
```

No neural analysis was rerun, and the assessment did not need to be: the
superseded mapping is a pure linear scale, so the raw framebuffer coordinate is
recovered **exactly** from each frozen `coordinates.jsonl` row and re-projected
arithmetically. All 25 frozen Regime A v2 trajectories (6500 rows) were checked.

| Question | Result |
|---|---:|
| Frames whose in-frame/out-of-frame admission changes | `0` |
| Frames whose out-of-frame status becomes in-frame | `0` |
| Frames whose discrete `token_cell_row` changes | `0` |
| Frames whose discrete `token_cell_col` changes | `1176 / 6500` |
| Maximum \|Δ screen_x\| | `5.877367877777544` px |
| Maximum \|Δ continuous token_col\| | `0.2204012954166572` cells |

The correction is **exactly** an affine transform of the superseded value in x
and the identity in y (verified residual `< 1e-13` px):

```text
screen_x_corrected = screen_x_superseded * (32/31) - (320/31)
screen_y_corrected = screen_y_superseded
```

### Why no frozen classification or conclusion changes

1. **The frozen quality gate does not move.** `target_authority.json` sets
   `missing_nonfinite_or_out_of_bounds_policy = FAIL_FRAME_AND_FAIL_TRAJECTORY_QUALITY_GATE`.
   That policy reads only the in-bounds predicate, and zero frames change it. No
   frame that was admitted should have been failed, and none that was failed
   should have been admitted.
2. **The primary target is untouched.** `target_authority.json` designates the
   primary target as the authoritative sheep world-x coordinate in blocks.
   `world_x` is server state copied through the projection unchanged, so the
   Regime A substantive-failure conclusion, which is a world-x readout result,
   cannot move.
3. **P2 and P3 consume no projection output.** The frozen P2 temporal-alignment
   estimate is computed from server `sheep_x` against the magenta detector
   centroid; `p2e_analyze.py` reads `coordinates.jsonl` for `world_x` only. P3
   C01 target-row contamination is decided by server-side geometric visibility
   and the magenta detector. Neither reads `screen_x`, `screen_y`, or a token
   cell.
4. **The secondary target rescales by a known constant and changes no verdict.**
   The continuous token row/col secondary target is an affine image of the
   superseded value, so every scale-invariant metric — including the reported
   `pooled_row_r2_secondary` — is exactly invariant, and token-cell-unit RMSE and
   MAE scale by exactly `32/31 ≈ 1.032258`. A uniform rescaling of a reported
   magnitude is not a change of classification, and no frozen artifact states a
   token-cell acceptance threshold that this rescaling crosses.

```text
PROJECTION_HISTORICAL_BLAST_RADIUS=NONE_MATERIAL_BOUNDED_ARITHMETIC_ASSESSMENT_SUFFICIENT
```

No frozen historical classification or conclusion is materially changed, so the
bounded assessment did not establish any need to rerun a historical neural
analysis, and none was rerun.

## Forward rule

```text
PROJECTION_FORWARD_RULE=CROP_AWARE_CANONICAL_PROJECTION_MANDATORY_FROM_STAGE1_ONWARD
```

- All prospective Regime A′ Stage-1 and Stage-2 work uses the crop-aware
  mapping. `src/mineocclude/regime_a.py` is an apparatus-critical runtime source,
  so its corrected bytes are pinned by the pre-outcome provenance receipt and
  rehashed by `verify_runtime_source_hashes`; a capture produced by the
  superseded mapping cannot satisfy Stage-1 runtime provenance.
- Stage 1 never trusts a supplied `projected_in_frame` Boolean. It reconstructs
  validity from raw screen and integer token-cell coordinates against the
  authority-bound frame and token-grid dimensions, with half-open `[0,width) ×
  [0,height)` bounds and a required floor-mapped token cell.
- Historical P2/P3 coordinates remain on the superseded mapping and are
  **not** rewritten. Any future comparison that mixes historical and prospective
  screen or token coordinates must apply the affine relation above explicitly
  rather than treating the two as the same quantity.
- Reusing the superseded mapping anywhere prospective is a defect, not an
  option.
