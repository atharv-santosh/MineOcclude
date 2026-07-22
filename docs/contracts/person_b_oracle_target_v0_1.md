# Person B Oracle Target Contract v0.1

Status: implemented before live results. Universal schema v1.0 is unchanged.

## Coordinate convention

All scalar positions are signed projections in blocks:

`dot(world_position_xyz - wall_parallel_origin_world_xyz,
wall_parallel_positive_unit_vector_world_xyz)`

The positive vector must have unit norm. Its origin, direction, source layout
manifest, and content hash are carried in a
`person-b-wall-parallel-frame-v0.1` coordinate-frame document. Live use fails
closed until Persons B and C sign that adapter. Axis names are never inferred
from filenames, layout names, or coordinate magnitudes.

`duration` remains the canonical numeric duration in seconds. Person B does
not introduce `duration_id`. `hidden_ticks` is deterministically derived as
`round(tau / 0.05 seconds)` and is rejected unless `tau` lies exactly on the
20 Hz grid; `tau` remains the stored canonical field.

## Complete row dictionary

| Field | Type | Unit | Source | Permitted use |
|---|---|---|---|---|
| `episode_id` | non-empty string | identifier | universal identity | join/provenance |
| `trajectory_id` | non-empty string | identifier | universal identity | primary trajectory/group key |
| `server_tick` | nonnegative integer | server ticks | universal identity | synchronization audit |
| `render_frame_idx` | nonnegative integer | frames | universal identity | synchronization audit |
| `action_idx` | nonnegative integer | actions | universal identity | synchronization audit |
| `model_frame_idx` | nonnegative integer | model frames | universal identity | primary frame join key |
| `layout_id` | non-empty string | identifier | universal identity | grouping/resampling |
| `regime` | non-empty string | category | universal identity | eligibility; primary target requires `regime_a` |
| `visibility` | `visible` or `occluded` | category | universal identity | oracle transition/eligibility |
| `tau` | finite number, nonnegative | seconds | universal identity | oracle input/time control |
| `v` | finite number | blocks/second | scripted condition | primary oracle input |
| `q` | finite number, nonnegative | blocks squared/second | scripted condition | primary oracle input |
| `duration` | finite number, nonnegative | seconds | universal identity | exact-duration binning |
| `code_sha` | 40-character hex string | identifier | B producing code | provenance |
| `config_hash` | SHA-256 string | identifier | literal validated config bytes | provenance/run binding |
| `model_hash` | SHA-256 string | identifier | A model identity | provenance |
| `preprocess_hash` | SHA-256 string | identifier | A preprocessing identity | provenance |
| `seed` | integer | seed | universal identity | reproducibility |
| `schema_version` | string equal to `1.0` | version | universal identity | compatibility gate |
| `run_id` | non-empty string | identifier | B oracle run | provenance |
| `status` | `accepted` | lifecycle | universal identity | analysis eligibility |
| `exclusion_reason` | null on accepted rows | lifecycle | universal identity | audit only |
| `superseded_by` | null on accepted rows | lifecycle | universal identity | audit only |
| `target_schema_version` | `person-b-oracle-target-v0.1` | version | B target contract | compatibility gate |
| `target_id` | non-empty string | identifier | trajectory/frame plus method suffix | stable target identity |
| `target_source` | fixed string | category | authoritative visible state plus known `v/q` | method audit |
| `oracle_method` | fixed string | category | iterative/closed-form cross-check | method audit |
| `oracle_information_set` | ordered list of strings | fields | B contract | leakage audit |
| `accepted_manifest_hash` | SHA-256 string | identifier | accepted source manifest | row-set binding |
| `source_run_id` | non-empty string | identifier | source state run | provenance |
| `last_visible_position_blocks` | finite number | blocks | authoritative visible state | primary oracle input |
| `mu_oracle_blocks` | finite number | blocks | primary Regime A oracle | mean probe target |
| `var_oracle_blocks2` | finite nonnegative number | blocks squared | primary Regime A oracle | oracle audit |
| `sigma_oracle_blocks` | finite nonnegative number | blocks | square root of variance | calibration |
| `log_sigma_oracle` | finite number or null | dimensionless | `ln(sigma / 1 block)` | hidden positive-spread probe target only |
| `x_true_blocks` | finite number | blocks | authoritative server state | scoring only; forbidden oracle input |

`log_sigma_oracle` is valid exactly when the row is occluded and
`sigma_oracle_blocks > 0`. It is null otherwise. This explicit eligibility rule
is the validity contract; an additional boolean alias is intentionally not
introduced.

## Table-level invariants

- Every `(trajectory_id, model_frame_idx)` is unique.
- Code, config, accepted-manifest, model, and preprocessing hashes cannot mix.
- A trajectory cannot mix source runs.
- The last-visible position remains fixed through an occluded run.
- `v` and `q` cannot change during an occluded run.
- Hidden `tau` strictly increases until reveal; reveal resets `tau` and spread.
- Hidden truth is copied only after posterior construction and remains
  scoring-only.
- Claim-bearing generation hashes the actual analysis config file bytes.
  Caller-supplied hashes are accepted only for legacy evidence explicitly
  marked non-scientific.
