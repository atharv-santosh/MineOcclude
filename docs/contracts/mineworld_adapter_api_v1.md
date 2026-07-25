# Person A MineWorld Adapter API

API version: `person-a-mineworld-adapter-v1.0`

Shared schema version: `1.0`

The public `MINEWORLD_ADAPTER_API_VERSION` constant carries the API version
above for runtime-identity validation.

Status: frozen by Person A Phase 3, Step 3.1. Runtime operations remain
intentionally unavailable until their assigned later Phase 3 steps.

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
| `load_runtime` | `RuntimeLoadRequest` | `MineWorldRuntimeIdentity` | Step 3.2 |
| `validate_trajectory` | `AcceptedTrajectoryInput` | `ValidatedTrajectory` | Step 3.3 |
| `preprocess_frame` | `FramePreprocessRequest` | `PreprocessedFrame` | Step 3.4 |
| `convert_action` | `ActionConversionRequest` | `ConvertedAction` | Step 3.5 |
| `tokenize_trajectory` | `TrajectoryTokenizationRequest` | `TokenizedTrajectory` and its `FrameTokenMap` | Step 3.6 |
| `teacher_forced` | `TeacherForcedRequest` | `TeacherForcedResult` | Step 3.7 |
| `free_rollout` | `FreeRolloutRequest` | `FreeRolloutResult` | Step 3.8 |

`MineWorldAdapter` is the protocol callers depend on.
`UnavailableMineWorldAdapter` is the executable Step 3.1 implementation: it
checks the request type and raises `operation_unavailable`. It never returns a
placeholder success.

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
  identity and expose shape, dtype, color order, and content identity.
- `ActionConversionRequest` and `ConvertedAction` preserve action-row identity
  and expose the official action tokens and converter identity.
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
)
```

It must not import MineWorld's private `inference.py`, Gradio implementation,
dataset internals, or checkpoint-loading scripts. The adapter implementation
may call the pinned official code internally beginning in Step 3.2.

## Current execution status

Step 3.1 freezes and directly tests this API only. No record in this module
claims that real loading, preprocessing, conversion, tokenization,
teacher-forced execution, or rollout execution has been implemented here.
The formal Phase 2 runtime evidence remains the authority for the already
completed runtime qualification.
