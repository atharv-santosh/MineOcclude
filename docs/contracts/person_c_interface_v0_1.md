# Person C Interface Packet v0.1

Shared schema version: `1.0`

Person C additive contract version: `0.1`

Status: `IMPLEMENTED_FOR_SYNTHETIC_C0_VALIDATION`

This packet defines the capture-side contract layered on Person A's frozen
C-to-A trajectory contract. It does not change shared schema v1.0. Person A's
validator remains authoritative for handoff compatibility; Person C adds
producer-side checks and may reject packages that A's structural validator does
not reject.

All fixtures under `tests/fixtures/person_c/` are synthetic, set
`scientific_use = "forbidden"`, and are not Minecraft runtime evidence.

## Contract hierarchy

1. `schema_version = "1.0"` retains the frozen shared meaning.
2. `person_c_contract_version = "0.1"` identifies this additive producer
   contract.
3. `src/mineocclude/contracts/trajectory.py` remains unmodified and must pass
   for an accepted C-to-A package.
4. `src/mineocclude/data/capture_contract.py` adds C0 acceptance rules.
5. Filenames, directory order, and physical JSON row order are never identity.

## Identifier dictionary

| Field | Meaning | Type and unit | Scope and rule |
|---|---|---|---|
| `episode_id` | Immutable source capture episode | non-empty string | Assigned before capture; identical across package and row streams. |
| `trajectory_id` | Immutable model-analysis trajectory derived from one episode | non-empty string | One trajectory belongs to exactly one episode. |
| `layout_id` | Immutable versioned base scene identity | non-empty string | A condition is not encoded in or inferred from this value. C1 freezes six stable layout IDs; layout schema v0.2 adds marker roles without changing this identity. |
| `server_tick` | Authoritative server time | non-negative integer ticks at 20 Hz | Unique per accepted trajectory and consecutive when ordered by explicit tick. |
| `render_frame_idx` | Frame position in declared capture media | zero-based integer frames | Unique and complete from `0` through `frame_count - 1`. |
| `action_idx` | Action snapshot paired with one model transition | zero-based integer actions | Unique and complete; `action_i` is intended between `visual_i` and `visual_(i+1)`. Real impulse evidence is required later. |
| `model_frame_idx` | Position in the handed-off model trajectory | zero-based integer model frames | Shared downstream key with `trajectory_id`; unique and complete in this single-rate fixture contract. |
| `run_id` | Immutable producing execution identity | non-empty string | Never inferred from a path or filename. |
| `seed` | RNG seed | signed integer, dimensionless | Recorded at package, manifest, and schedule-row scope. |

The strict capture key is the frozen six-field key:

`episode_id + trajectory_id + server_tick + render_frame_idx + action_idx + model_frame_idx`

The model-analysis join key remains:

`trajectory_id + model_frame_idx`

## Version and hash dictionary

| Field | Format | Meaning |
|---|---|---|
| `schema_version` | constant string `1.0` | Frozen shared schema. |
| `person_c_contract_version` | constant string `0.1` | Additive Person C packet. |
| `lifecycle_version` | non-empty string | Tick event-order decision version. |
| `code_sha` | 40 hexadecimal characters | Exact producing Git commit. |
| `config_hash` | 64 hexadecimal characters | Complete capture configuration content hash. |
| `layout_config_hash` | 64 hexadecimal characters | Exact layout definition content hash. |
| `environment_lock_hash` | 64 hexadecimal characters | Exact environment lock content hash. |
| `noise_schedule_hash` | 64 hexadecimal characters | Immutable seed/noise schedule content hash. |
| artifact `sha256` | 64 hexadecimal characters | Exact artifact bytes, never a filename identity. |

Synthetic fixtures use formatted placeholder hashes. They are not hashes of
real scientific artifacts.

## Numeric units

| Field or concept | Unit |
|---|---|
| `server_tick`, `client_tick` | ticks |
| `render_frame_idx`, `model_frame_idx` | frames |
| `action_idx`, `draw_idx` | dimensionless zero-based indices |
| media `width`, `height` | pixels |
| media `fps`, `tick_rate_hz` | frames or ticks per second |
| `dt_seconds`, `tau`, `duration` | seconds |
| `v`, velocity components | blocks per second |
| `q` | blocks squared per second |
| position components, wall-parallel position, `noise_draw`, `noise_std_blocks` | blocks |
| `standard_normal_draw` | dimensionless |
| seed | dimensionless integer |

Every numeric schema property has an `x-unit` annotation in
`schemas/person_c/capture_v0_1.schema.json`.

## Record schemas

### Frame-map row

Required fields are exactly the six capture-key fields for identity purposes.
The frame map is authoritative. Each index is non-negative and the four-tick
synthetic contract uses complete zero-based frame/action/model indices.

Unique keys:

- strict six-field capture key;
- `server_tick` within a trajectory;
- `render_frame_idx` within a trajectory;
- `action_idx` within a trajectory;
- `model_frame_idx` within a trajectory.

### Raw-action row

Requires the capture key and a non-empty `raw_action` mapping. The raw action is
preserved unchanged. Exact input-device fields and official conversion rules
are owned by A/C review and remain unresolved; this packet does not invent
them.

### Normalized-action row

Requires the capture key and A's frozen integer fields:

- `camera_component_0`
- `camera_component_1`
- `hotbar`
- `forward_back`
- `left_right`
- `sprint_sneak`
- `use_attack`
- `jump`
- `drop_pick_item`

Component orientation and conversion semantics remain A-owned unresolved
decisions. Person C does not rename, clip, or coerce these fields.

### Server-state row

Requires the capture key plus a non-empty authoritative `state` mapping. C0's
minimum state payload contains:

- `target_entity_id`: non-empty string;
- `target_present`: boolean;
- `position_x_blocks`, `position_y_blocks`, `position_z_blocks`: finite blocks;
- `wall_parallel_position_blocks`: finite blocks;
- `velocity_x_blocks_per_second`, `velocity_y_blocks_per_second`,
  `velocity_z_blocks_per_second`: finite blocks/second.

Full world coordinates are preserved. The consumer-side
`build_state_input_from_capture_package` adapter validates the complete C
package, binds an externally supplied B coordinate frame and A model/preprocess
hashes, projects B's exact `x_true_blocks`, and emits
`observed_position_blocks` only for legally visible rows. It verifies any
C-declared wall-parallel value and never silently reinterprets state.

### Client-tick row

Requires the capture key and non-negative integer `client_tick`, in client
ticks. Client ticks are mapped explicitly and are not assumed equal to server
ticks.

### Visibility row

Requires the capture key and a non-empty `visibility` string. The Regime A
derived table accepts `visible` and `occluded`. A package with
`target_present = false`, including the no-sheep control, is explicitly
`no_object_not_oracle_eligible`; the adapter does not fabricate position,
visibility, or a zero target and does not mutate the original C package.

### Seed/noise row

Requires the capture key, package seed, `draw_idx`, dimensionless
`standard_normal_draw`, `q` in blocks squared/second, `dt_seconds`,
`noise_std_blocks`, and `noise_draw` in blocks. It must satisfy:

`noise_std_blocks = sqrt(q * dt_seconds)`

`noise_draw = standard_normal_draw * noise_std_blocks`

There is exactly one immutable draw per accepted server tick.

### Episode manifest

Requires all package IDs, condition/regime, seed, clock, `q`, `v`, `duration`,
version fields, provenance hashes, RNG declaration, lifecycle version, and
status. Duplicate fields must equal their package values. Accepted real data
cannot use an unresolved runtime NumPy pin.

### Exclusion ledger

The ledger is always present, including as an empty list for an accepted
synthetic package. Each entry has a unique `exclusion_id`, exact package IDs,
schema/contract versions, `status = "excluded"`, non-empty
`exclusion_reason`, non-empty rejection-code list, UTC record time, source
artifact SHA-256, and `superseded_by = null`. Rejected material is preserved;
it is never silently dropped.

## Cross-table relationships

- Every required row stream contains exactly `media.frame_count` identities.
- Every stream's capture-key set equals the frame-map key set.
- Relationships use key sets and explicit timeline sorting, never row order.
- Package, manifest, and rows agree on episode and trajectory identities.
- Schedule seed equals package seed and schedule draw count equals tick count.
- Media indices are complete and unique.
- When ordered by `server_tick`, ticks advance by one and frame/action/model
  indices advance monotonically.
- A temporal impulse record resolves its effect frame through the frame map.

## Acceptance and rejection

Acceptance requires both the frozen A validator and the stricter C validator to
pass. C validation returns stable rejection records, does not mutate input, and
does not repair or remove rows.

The required C0 corruption codes are:

- `missing_action`
- `missing_frame`
- `duplicate_frame`
- `duplicate_state`
- `skipped_tick`
- `mixed_episode_id`
- `non_monotonic_index`
- `shifted_action`
- `invalid_media_metadata`

A rejection may additionally contain `upstream_trajectory_rejected` with A's
original schema-v1.0 rejection code and message.

## Explicit unresolved decisions

| Decision | Owner/reviewer | Status |
|---|---|---|
| RGB/BGR, resize interpolation, scaling, and normalization | Person A | `UNRESOLVED` |
| Official raw-action vocabulary and conversion | Persons A/C | `UNRESOLVED` |
| Real camera component orientation and transition impulse proof | Person A with C evidence | `RUNTIME EVIDENCE REQUIRED LATER` |
| Exact NumPy package version compatible with the final Python/MineWorld lock | Persons A/C | `UNRESOLVED` |
| B adapter field mapping and no-object visibility policy | Person B | `STRUCTURALLY IMPLEMENTED`; formal owner approval and real evidence unverified |
| Stable marker ID to canonical geometric role | Persons C/E | `STRUCTURALLY IMPLEMENTED` in C layout v0.2 / E homography v1.1; real-camera qualification pending |
| Detector thresholds and empirical visibility evidence | Person E; C owns final visibility | `RUNTIME/CALIBRATION EVIDENCE REQUIRED LATER` |
| Layout IDs, geometry, conditions, and environment lock | Person C Phase C1 | `STRUCTURALLY IMPLEMENTED`; runtime/reconstruction evidence required later |

C0 is not externally signed off until the unresolved owner decisions are
recorded. No real scientific collection is authorized by this packet.
