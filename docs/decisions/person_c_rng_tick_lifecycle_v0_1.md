# Person C RNG and Tick Lifecycle Decision v0.1

Decision status: `APPROVED_FOR_SYNTHETIC_CONTRACT_TESTING`

Human Phase 0/1 interface review: `APPROVED` at
`80d41c5ca0e341263a7b0c683fae4b51be376c55`; central evidence is
`docs/contracts/schema_v1_0_signed_record.md`.

Runtime status: `RUNTIME EVIDENCE REQUIRED LATER`

Shared schema version remains `1.0`; this record is additive Person C contract
version `0.1`.

## RNG execution design

The Python capture preparation step is the only random-number producer. It
uses `numpy.random.Generator` with the `PCG64` bit generator to create the
complete schedule before an episode starts. The Java server does not recreate
draws from a seed. It verifies and consumes the stored schedule in increasing
`draw_idx` order.

The exact NumPy package version must be pinned alongside the final compatible
Python/MineWorld environment. That version is unresolved in the current
repository, whose Person A dependency file is still a placeholder. Synthetic
fixtures therefore use `PIN_REQUIRED_BEFORE_RUNTIME` and are accepted only
when `synthetic = true` and `scientific_use = "forbidden"`. A real capture with
that sentinel is rejected as `unresolved_runtime_pin`.

The immutable schedule records:

- seed, dimensionless integer;
- `draw_idx`, zero-based dimensionless index;
- `standard_normal_draw`, dimensionless;
- `q`, variance rate in blocks squared/second;
- `dt_seconds`, seconds;
- `noise_std_blocks = sqrt(q * dt_seconds)`, blocks;
- `noise_draw = standard_normal_draw * noise_std_blocks`, blocks;
- the explicit capture key for the tick.

The exact schedule bytes are hashed with SHA-256. A mismatch, missing draw,
duplicate draw, or scaling mismatch rejects the episode; it is never repaired
or regenerated during validation.

## Authoritative tick lifecycle

For each accepted tick, the lifecycle is:

1. Validate episode identity, configuration, condition, and schedule bounds.
2. Consume exactly one stored noise draw by `draw_idx`.
3. Apply the scripted motion update and the stored noise increment.
4. Write authoritative server state for `server_tick`.
5. Broadcast the authoritative packet.
6. Record explicit client receipt/tick evidence.
7. Snapshot action `action_i` for the next model transition.
8. Capture rendered `visual_i` and write the frame-map identity.

No component may infer correspondence from record order or filenames.

## Action orientation

The intended teacher-forcing orientation is:

`visual_i -> action_i -> visual_(i+1)`

The checked synthetic fixture places an impulse at `action_idx = 1` between
model frames 1 and 2 and resolves the declared effect tick through the frame
map. This proves validator mechanics only. It does not prove the real MineWorld
camera axes, client/server timing, or rendered effect. Those require a pinned
runtime impulse capture reviewed by Person A.

## Failure behavior

- Exhausted, duplicated, or skipped schedule positions reject the episode.
- Shifted action identities reject the episode.
- Missing frames/actions/state rows reject the episode.
- Invalid packages remain unchanged and auditable.
- Validation never interpolates, truncates, reorders, clips, or coerces rows.

## Required later evidence

- Exact Python and NumPy versions.
- Fresh schedule generation with the pinned environment.
- Java byte-for-byte schedule verification and consumption log.
- Real one-tick camera/action impulse evidence.
- Server/client tick and render timing diagnostics.
- Approval of the observed real schedule and transition implementation after
  runtime evidence. The Phase 0/1 RNG/event-order interface meaning itself is
  already approved at the checkpoint recorded above.
