# Person E measurement foundation v0.1

Status: implemented before live artifacts; calibration-dependent values remain
explicitly pending.

## Inputs

E consumes the frozen A-to-E rollout manifest and A/E registry. Scientific
identity comes from fields and hashes, never filenames or row order. Decoded
frame adapters must preserve explicit event, rollout, seed, and frame identity.
The executable path is detector calibration -> homography qualification -> U4
frame localization -> aligned SSIM -> evidence composition -> measurement.
`measure_u4.py` does not accept unversioned coordinates or a caller-asserted
SSIM flag.

## Detector output

The HSV detector records presence status, zero-based pixel-center centroid,
exclusive `(x_min, y_min, x_max, y_max)` bounding box, blob area, threshold
match count, candidate count, threshold version, and rejection reason.

Thresholds, morphology, and area limits are selected on C's calibration frames
only and evaluated on a held-out set containing both visible and negative
frames. U4 outcomes cannot select detector settings.

## Homography output

Four explicit marker IDs map image `(x, y)` to ground-plane
`(world_x, world_z)` blocks. Marker identity/order, image coordinates, world
coordinates, fitted matrix, and fit hash are retained. Validation reports
signed and absolute wall-parallel error plus Euclidean error on unused points.
The fit identity also binds layout, canonical camera pose, algorithm, pivot
tolerance, coordinate conventions, marker coordinates, and matrix.

## Reappearance and displacement

- Primary: first post-reveal detection valid for two consecutive frame IDs.
- Coverage starts at `reveal_frame_idx + 1`; omitted frames are never treated
  as detector negatives.
- Sensitivity: median coordinate of the first three valid post-reveal frames.
- Baseline match: exact `event_id + seed` alpha-zero rollout.
- Displacement: pushed coordinate minus alpha-zero coordinate in blocks.
- No primary reappearance: `non_persistence`, with null numeric measurements.
- Failed generation: `generation_failure`, with null numeric measurements.
- Invalid/missing baseline or SSIM: `excluded`, with an explicit reason.
- Negative SSIM remains in rich evidence but becomes an explicit null B-row
  exclusion until the frozen consumer range is migrated.

The rich row preserves dose ID, requested/applied alpha, cap flag, intended
block shift, direction, control, layer, hook site, timestep, reveal/detection
timing, pushed and baseline world coordinates, sensitivity displacement,
masked SSIM, and quality flags. The handoff also reports alpha-zero persistence
before conditioning, while counting failures and exclusions separately.

## Coherence

Full-frame SSIM uses the declared data range and per-channel RGB mean. A
background sensitivity excludes the union of pushed/baseline sheep boxes plus
the signed-off fixed margin. Frames require exact identity and dimensions;
missing or misaligned frames are not interpolated.

## B handoff

The compact document uses
`person-b-u4-measurement-input-v0.1`, producer role `person_e`, literal rollout
manifest/config hashes, exactly one row per submitted rollout, and the existing
B validator. Each rollout gets one separately persisted immutable rich-evidence
JSON file. The SHA-256 of its exact on-disk bytes—not a self-referential digest—
is stored as `measurement_artifact_hash`. The evidence covers the raw versioned
source row, matched alpha-zero evidence, both reappearance results, and final
measurement values. The handoff contains evidence URIs and hashes plus the
registry/manifest/config and registered E run/code identities. These files do
not masquerade as registry-v1 artifacts while the artifact-type migration
remains unapproved.
