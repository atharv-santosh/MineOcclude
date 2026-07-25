# Person A MineWorld Adapter API

API version: `person-a-mineworld-adapter-v1.0`

Shared schema version: `1.0`

The public `MINEWORLD_ADAPTER_API_VERSION` constant carries the API version
above for runtime-identity validation.

Status: frozen by Person A Phase 3, Step 3.1. Steps 3.2 through 3.5 now have
one private implementation behind the frozen protocol. Steps 3.6 through 3.8
remain intentionally unavailable.

## Purpose

`mineocclude.models.mineworld_adapter` is the public translation boundary
between accepted MineOcclude trajectories and the official MineWorld runtime.
Downstream MineOcclude code may depend on this module without importing
MineWorld's private scripts.

The API is project-owned. It wraps paths, runtime provenance, identities,
requests, results, and failures in typed records. A future implementation may
hold official MineWorld objects internally, but those objects are not the
primary downstream contract.

## Public operations

| Operation | Input | Output | Implemented in |
|---|---|---|---|
| `load_runtime` | `RuntimeLoadRequest` | `MineWorldRuntimeIdentity` | Step 3.2, implemented locally |
| `validate_trajectory` | `AcceptedTrajectoryInput` | `ValidatedTrajectory` | Step 3.3, implemented locally |
| `preprocess_frame` | `FramePreprocessRequest` | `PreprocessedFrame` | Step 3.4, implemented locally |
| `convert_action` | `ActionConversionRequest` | `ConvertedAction` | Step 3.5, implemented locally |
| `tokenize_trajectory` | `TrajectoryTokenizationRequest` | `TokenizedTrajectory` and its `FrameTokenMap` | Step 3.6 |
| `teacher_forced` | `TeacherForcedRequest` | `TeacherForcedResult` | Step 3.7 |
| `free_rollout` | `FreeRolloutRequest` | `FreeRolloutResult` | Step 3.8 |

`MineWorldAdapter` is the protocol callers depend on.
`create_mineworld_adapter()` constructs the private Wave 2 implementation
without exposing its class or MineWorld runtime objects. The Step 3.1 API had
reserved a protocol but no construction path; this factory is the smallest
compatible correction. `UnavailableMineWorldAdapter` remains available for
explicit contract-only use and never returns a placeholder success.

## Public types

- `FrameIdentity` carries the frozen `trajectory_id + model_frame_idx` key.
- `RuntimeLoadRequest` identifies all source, configuration, checkpoint, VAE,
  environment, precision, and device inputs required by the loader.
- `MineWorldRuntimeIdentity` records the complete loaded runtime provenance,
  loaded class and decoder path identity, dimensions, token layout, precision,
  and device.
- `AcceptedTrajectoryInput` identifies the accepted manifest and supplies the
  C-to-A document to the validator. `ValidatedTrajectory` records its exact
  content identity and ordered frame identities.
- `FramePreprocessRequest` and `PreprocessedFrame` preserve source-frame
  identity and expose source/output shape, source/output dtype, color
  conversion, interpolation, preprocessing profile, hashes, statistics, and
  the normalized CHW payload.
- `ActionConversionRequest` and `ConvertedAction` preserve action-row identity
  and expose the original action hash, normalized official action, exact
  11-token sequence, vocabulary offset, positional roles, no-op status, and
  converter identity.
- `FrameTokenSpan` and `FrameTokenMap` explicitly associate each scientific
  frame with visual and action token positions. No row-order inference is
  permitted.
- `TrajectoryTokenizationRequest` and `TokenizedTrajectory` carry the validated
  components, runtime identity, explicit token sequence, map, and sequence
  hash.
- `TeacherForcedRequest` and `TeacherForcedResult` define one explicit
  teacher-forced call and its project-owned output metadata.
- `FreeRolloutRequest` and `FreeRolloutResult` define one explicit generation
  call and durable video/metadata identities.

Records that describe identity, requests, and results are frozen dataclasses.
Array or tensor payload fields remain implementation-neutral and must not hold
a private MineWorld control object as the public contract.

The extra Step 3.4 and Step 3.5 result metadata is additive and defaulted. No
Step 3.1 symbol, field meaning, or required constructor argument changed, so
the API remains `person-a-mineworld-adapter-v1.0`. Implementations produced by
the Wave 2 factory populate every new field.

## Implemented Wave 2 boundary

`load_runtime` verifies every path, request digest, actual file digest, pinned
source revision, source cleanliness, asset revision, precision, and device
before checkpoint deserialization. It then calls the exact Phase 2 loader,
which instantiates the pinned configuration through MineWorld `utils.py`.
The centralized provenance-bound checkpoint classifier is rerun, the complete
pinned architecture is asserted, and both the model and VAE are placed in
evaluation mode. Requested provenance remains in `RuntimeLoadRequest`; the
returned `MineWorldRuntimeIdentity` is emitted only after the observed files,
checkout, load state, and architecture match it.

`validate_trajectory` delegates to
`mineocclude.contracts.trajectory.validate_trajectory_package`. It does not
copy or repair that contract. An accepted package is bound to its canonical
content hash and ordered `trajectory_id + model_frame_idx` identities.

`preprocess_frame` accepts only the decoded 640 x 360, three-channel, uint8 BGR
representation named by an accepted frame-map row. Following the pinned
MineWorld Gradio path, it performs BGR-to-RGB conversion, OpenCV
`INTER_LINEAR` resize to 384 x 224, HWC-to-CHW conversion, float32 scaling by
`1/255`, then normalization with mean and standard deviation `0.5`.
The frozen request already carries a decoded frame, so media-container decoding
stays with the accepted capture reader rather than being added implicitly to
this operation.

`convert_action` accepts only the raw action mapping bound to an accepted
action row. It invokes the clean pinned checkout's
`MCDataset.json_action_to_env_action` and
`MCDataset.get_action_index_from_actiondict` with offset `8192`. The adapter
does not assign token IDs. It requires the audited source revision and
`mcdataset.py` Git-blob identity, exact normalized key set, exact 11-token
length, valid vocabulary membership, and deterministic repeated conversion.

The failure order is deliberate: path/hash/source failures precede
deserialization; trajectory failures precede preprocessing and conversion;
frame failures precede any later tokenization; action failures precede
sequence construction and execution.

## Teacher-forced and rollout separation

Teacher forcing and free rollout have different request types, result types,
and protocol methods. `teacher_forced` must not call `free_rollout`, and
`free_rollout` must not call `teacher_forced`, implicitly or as fallback.

This separation prevents a caller from confusing activation-producing
teacher-forced execution with generated rollout evidence.

## Identity

All public frame-bearing records carry:

`trajectory_id + model_frame_idx`

The API imports the existing schema and token-layout constants rather than
defining a second shared identity contract. It does not alter activation
identity:

`trajectory_id + model_frame_idx + layer_idx + hook_site`

Runtime identity separately binds MineOcclude code, pinned MineWorld source,
ModelScope assets, model/VAE configurations and checkpoints, environment
report, preprocessing, action conversion, classes, architecture, precision,
and device.

## Structured failures

Every adapter failure is a `MineWorldAdapterError` with:

- an `AdapterFailureCode`;
- the `AdapterOperation` that failed;
- a human-readable message;
- immutable field/detail pairs.

Invalid schema, identity, request, or provenance fails at record construction
or the adapter boundary. Operations that have not reached their assigned
roadmap step fail with `operation_unavailable`; they never silently succeed.
Step 3.9 adds final identity propagation and failure-path certification without
changing this exception shape.

## Ownership boundary

The adapter owns:

- translation from accepted MineOcclude inputs to official MineWorld inputs;
- validated runtime loading and complete runtime identity;
- trajectory validation;
- preprocessing and raw-action conversion;
- token sequence construction and frame/token mapping;
- explicit teacher-forced and rollout execution entry points;
- adapter/runtime failures.

The adapter does not own:

- activation-layer selection or hook registration policy;
- activation pooling or storage;
- probe training or scientific analysis;
- interventions;
- experimental registry ownership.

Those responsibilities stay in their existing authoritative modules. In
particular, `mineocclude.activations.hooks`, `pool`, and `store` are not
imported by the adapter.

## Permitted downstream imports

Downstream project code should import from:

```python
from mineocclude.models.mineworld_adapter import (
    MineWorldAdapter,
    TeacherForcedRequest,
    FreeRolloutRequest,
    create_mineworld_adapter,
)
```

It must not import MineWorld's private `inference.py`, Gradio implementation,
dataset internals, or checkpoint-loading scripts. Only the private adapter
implementation imports the pinned official code.

## Current execution status

Steps 3.2 through 3.5 are implemented and CPU-tested as an input/loading
boundary. Loader tests use controlled objects and do not claim a new real
checkpoint load. The action matrix is direct output from the clean pinned
converter. The preprocessing golden is CPU-derived; its 336-code boundary uses
an explicitly labeled fake VAE. Real Wave 2 behavior remains subject to the
later GPU certification step.

Step 3.6 must construct the real interleaved sequence and `FrameTokenMap`.
Step 3.7 must execute teacher forcing, Step 3.8 must execute rollout, and Step
3.9 must certify identity/failure propagation. Until then,
`tokenize_trajectory`, `teacher_forced`, and `free_rollout` raise
`operation_unavailable`.
