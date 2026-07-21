# MineOcclude A→B Activation Contract

Current implementation version: `0.1-draft`

Target frozen version: `1.0`

Status: Phase 1 draft pending cross-role compatibility review and final schema v1.0 sign-off in Step 1.8.

## Purpose

This contract defines exactly what Person A must provide to Person B when handing off MineWorld activations for probing and scientific analysis.

The goal is to make every activation:

* scientifically identifiable
* joinable to the corresponding target row
* traceable to the exact stored vector
* traceable to the exact model and preprocessing configuration
* reproducible from documented metadata
* auditable without relying on row ordering or private explanation

Person B must be able to receive the handoff and independently determine:

* which trajectory produced each activation
* which model frame produced it
* which MineWorld layer produced it
* which exact hook site was used
* which token positions contributed to it
* how those tokens were pooled
* where the stored activation vector is located
* its dtype and shape
* which checkpoint produced it
* which preprocessing pipeline produced it
* which accepted input manifest was used
* which run produced it
* whether the producing run completed successfully

## Producer and consumer

Producer:

* Person A — MineWorld model and integration pipeline

Consumer:

* Person B — belief estimation, probing, and analysis pipeline

Person A owns activation extraction and activation-handoff integrity.

Person B owns downstream scientific analysis after receiving a valid handoff.

## Scope

This contract applies to the activation-index handoff from Person A to Person B.

It does not define:

* Person B's target-generation method
* the oracle posterior implementation
* probe-training procedures
* train, validation, or held-out split construction
* probe hyperparameters
* Person B's final predictions
* intervention requests from Person B to Person A
* rollout outputs sent to Person E

Those belong to their respective contracts and later Phase 1 steps.

## Package-level fields

Every activation handoff requires:

* `schema_version`
* `handoff_id`
* `accepted_manifest_hash`
* `checkpoint_hash`
* `preprocess_hash`
* `run_id`
* `run_status`
* `selection_policy`
* `chunks`
* `index_rows`
* `cardinality_report`

## Schema version

The current activation contract uses:

`0.1-draft`

The final schema version becomes `1.0` only after Step 1.8 cross-role sign-off.

## Handoff identity

Every handoff requires a non-empty:

`handoff_id`

This identifies one logical A→B activation delivery.

## Accepted-manifest hash

Every handoff requires:

`accepted_manifest_hash`

This is the SHA-256 identity of the accepted input manifest from which Person A selected the trajectories and frames used for activation extraction.

The hash must be a 64-character hexadecimal SHA-256 value.

Every activation-index row must repeat the same accepted-manifest hash.

This allows Person B to verify exactly which accepted input set produced the activation handoff.

The accepted-manifest hash is a required handoff companion and may not be omitted.

## Checkpoint hash

Every handoff requires:

`checkpoint_hash`

This identifies the exact model checkpoint used for activation extraction.

The hash must be a valid 64-character SHA-256 value.

Every activation-index row must agree with the package-level checkpoint hash.

The universal identity field:

`model_hash`

must also agree with:

`checkpoint_hash`

for each activation row.

## Preprocessing hash

Every handoff requires:

`preprocess_hash`

This identifies the exact preprocessing implementation or frozen preprocessing artifact used before MineWorld inference.

The hash must be a valid 64-character SHA-256 value.

Every activation-index row must carry the same preprocessing hash.

## Run identity

Every handoff requires:

`run_id`

Every activation-index row must carry the same run identifier.

This allows all activation rows to be traced back to the exact producing run.

## Run status

Every handoff requires:

`run_status`

Current allowed values are:

* `completed`
* `partial`
* `failed`

Every activation-index row must agree with the package-level run status.

For the normal accepted A→B scientific handoff, the expected status is:

`completed`

The broader status vocabulary exists so incomplete or failed production attempts can still be represented and audited rather than silently disappearing.

Whether partial or failed runs are scientifically usable is determined by later run-selection policy.

## Extraction-selection independence

Person A must not use Person B's target values or held-out evaluation labels to decide which activations to extract.

The handoff therefore requires:

`selection_policy`

with:

* `uses_target_labels`
* `uses_heldout_labels`
* `description`

For an accepted extraction policy:

`uses_target_labels` must be `false`

and:

`uses_heldout_labels` must be `false`

The description must explain the target-independent extraction rule.

Valid selection information may include:

* accepted trajectory identity
* configured layers
* configured hook sites
* configured frame positions
* visibility or experimental condition fields that are part of the predetermined experimental design
* predetermined extraction configuration

Person A must not inspect scientific target values and then selectively extract only desirable rows.

Person A must not inspect held-out results and then change which activation rows are exported.

This prevents label leakage and selective extraction bias.

## Condition fields

Activation rows inherit the universal identity and condition fields defined in Step 1.2.

These include:

* `layout_id`
* `regime`
* `visibility`
* `tau`
* `v`
* `q`
* `duration`

These fields are included so Person B can:

* group rows by experimental condition
* construct predetermined analysis subsets
* study behavior across occlusion duration
* join activations to condition metadata

Their presence does not permit Person A to use target or held-out labels when selecting activations.

Condition fields describe the experimental input condition.

They are not the scientific target predictions that Person B is attempting to decode.

## Universal row identity

Every activation-index row inherits the universal row identity established in Step 1.2.

This includes:

* `episode_id`
* `trajectory_id`
* `server_tick`
* `render_frame_idx`
* `action_idx`
* `model_frame_idx`

It also includes the universal condition, provenance, lifecycle, and status fields required by the Step 1.2 identity contract.

This ensures activation rows remain joinable with other MineOcclude artifacts.

## Scientific activation identity

A scientific activation row is uniquely identified in the current Step 1.4 contract by:

`trajectory_id + model_frame_idx + layer_idx + hook_site`

Two activation-index rows may not share the same complete scientific activation identity.

This prevents ambiguity about which stored activation corresponds to one trajectory, model frame, layer, and extraction site.

## Activation chunk identity

Activation vectors may be stored in chunks rather than as separate files.

Every activation chunk requires:

* `chunk_id`
* `path`
* `sha256`
* `row_count`
* `dtype`
* `vector_shape`

### `chunk_id`

A non-empty unique identifier for one activation storage chunk.

### `path`

The documented location of the activation chunk.

### `sha256`

The SHA-256 hash identifying the exact stored chunk artifact.

### `row_count`

The number of activation vectors stored in that chunk.

### `dtype`

The dtype used for activation vectors in the chunk.

### `vector_shape`

The shape of one activation vector.

Every declared chunk row must have exactly one corresponding activation-index entry.

## Activation row storage location

Every activation-index row requires:

* `activation_chunk_id`
* `chunk_row_idx`

Together these identify the exact physical storage position of the activation vector.

Example:

`activation_chunk_id = activation_chunk_0004`

and:

`chunk_row_idx = 17`

means that the indexed activation is stored at row 17 of activation chunk 0004.

A chunk row may not be referenced by multiple activation-index rows.

The referenced chunk must exist in the handoff.

The row index must fall within the declared chunk row count.

## Layer identity

Every activation-index row requires:

`layer_idx`

This identifies the exact MineWorld layer from which the activation was captured.

The value must be a non-negative integer.

The final production extraction configuration determines which exact layers are exported.

Layer selection must be predetermined and must not depend on target or held-out labels.

## Hook site

Every activation-index row requires:

`hook_site`

This must be a non-empty string naming the exact model location from which the activation was captured.

Examples of possible hook-site identities include explicitly verified model locations such as a residual stream location.

The production hook-site vocabulary must correspond to locations verified against the pinned MineWorld implementation.

The same human-readable layer number with different hook sites represents different scientific activations.

Therefore, `hook_site` is part of the activation identity.

## Model frame identity

Every activation-index row requires:

`model_frame_idx`

For the locked MineWorld `700M_16f` configuration, valid model-frame positions are currently expected to fall within:

`0` through `15`

because one model input window contains 16 frame/action pairs.

## Frame token positions

Every activation-index row requires:

`frame_token_positions`

This records the exact model sequence positions used to produce the activation vector associated with one model frame.

Under the current locked MineWorld token layout:

* each frame contributes `336` visual tokens
* each corresponding action contributes `11` action tokens
* each frame/action pair therefore occupies `347` sequence positions

For model frame index `f`, the current visual-token positions are:

`f × 347`

through:

`f × 347 + 335`

inclusive.

Therefore:

### Model frame 0

Visual positions:

`0–335`

### Model frame 1

Visual positions:

`347–682`

### Model frame 2

Visual positions:

`694–1029`

and so forth.

The 11 positions following each visual region belong to the corresponding action tokens and are not included in visual-only frame pooling.

Every current activation-index row must contain exactly 336 visual-token positions matching the locked frame layout.

The token positions are stored explicitly rather than inferred downstream so Person B can audit exactly what Person A pooled.

## Token region

Every current activation row requires:

`token_region = "visual"`

This indicates that the activation vector represents the visual-token region associated with one model frame.

If the project later adds action-token, combined-token, or other regions, they require an explicit schema update rather than silently reusing the current definition.

## Pooling method

Every current activation-index row requires:

`pooling_method = "mean"`

This means Person A averages the hidden activation vectors across the 336 visual-token positions belonging to the relevant model frame.

The resulting pooled vector therefore has one hidden-state vector per:

* trajectory
* model frame
* layer
* hook site

The pooling method is recorded explicitly so Person B does not need private knowledge of Person A's extraction implementation.

A future change to the pooling method requires an explicit contract update.

## Activation dtype

Every activation-index row and every referenced chunk records:

`dtype`

Current supported values are:

* `float16`
* `bfloat16`
* `float32`
* `float64`

The row dtype must agree with the referenced chunk dtype.

## Activation vector shape

Every activation-index row and every referenced chunk records:

`vector_shape`

For the current MineWorld `700M_16f` hidden-state extraction contract, the required pooled hidden vector size is:

`2048`

and is represented as:

`[2048]`

Both the row and chunk descriptor must use exactly `[2048]`.

Agreement between two different shapes is not sufficient for acceptance.

The contract records the shape explicitly rather than requiring Person B to infer it from model knowledge.

## Index ordering

Row ordering has no scientific meaning.

Person B must not assume:

* layer-major ordering
* frame-major ordering
* chronological file order
* chunk order
* insertion order

All joins must use documented identity fields.

The synthetic Step 1.4 fixtures intentionally use target rows whose order differs from the activation-index order.

The join must still succeed.

## Target-table join

The minimum synthetic Step 1.4 join demonstrated by the contract is:

`trajectory_id + model_frame_idx`

The synthetic target table contains one target row per trajectory/model-frame pair.

The activation table contains multiple layer rows for each trajectory/model-frame pair.

Therefore one target row is expected to join to multiple activation rows when multiple layers are extracted.

In the current synthetic fixture:

* 3 model frames exist
* 2 layers are extracted
* 6 activation rows exist
* 3 target rows exist

After joining:

`3 frames × 2 layers = 6 joined activation rows`

This proves Person B can reproduce the join without relying on row order or private explanation.

Production target tables may use additional universal identity fields where required by the final Person B contract.

## Cardinality report

Every A→B activation handoff requires a:

`cardinality_report`

The report requires:

* `accepted_manifest_rows`
* `expected_activation_rows`
* `actual_activation_rows`
* `expected_rows_by_layer`
* `actual_rows_by_layer`

### `accepted_manifest_rows`

The number of accepted input manifest rows represented by the extraction plan.

### `expected_activation_rows`

The total number of activation-index rows that should have been produced by the predetermined extraction configuration.

### `actual_activation_rows`

The number of activation-index rows actually produced.

### `expected_rows_by_layer`

The expected activation row count for every extracted layer.

### `actual_rows_by_layer`

The observed activation row count for every extracted layer.

For an accepted complete handoff:

`expected_activation_rows`

must equal:

`actual_activation_rows`

The reported actual count must equal the number of activation-index rows.

The reported per-layer actual counts must be reproducible directly from the activation index.

The reported `accepted_manifest_rows` count must equal the number of unique `trajectory_id + model_frame_idx` identities represented by the activation index.

Expected per-layer counts must sum to `expected_activation_rows`.

Actual per-layer counts must sum to `actual_activation_rows`.

Expected per-layer counts must equal actual per-layer counts for the complete synthetic handoff.

The cardinality report is a required A→B handoff companion.

## Cardinality example

The Step 1.4 synthetic fixture contains:

* 3 accepted model-frame rows
* 2 configured extraction layers

Therefore:

`3 × 2 = 6`

expected activation rows.

The synthetic report contains:

* layer 5: 3 expected, 3 actual
* layer 12: 3 expected, 3 actual

Total:

* 6 expected
* 6 actual

Person B can independently reproduce these counts directly from the activation index.

## Manifest companion requirement

The accepted-manifest hash and cardinality report must travel with the activation handoff.

A valid scientific handoff therefore contains both:

1. the SHA-256 identity of the accepted input manifest
2. a reproducible activation cardinality report

This allows Person B to distinguish:

* a complete extraction
* missing activation rows
* duplicated activation rows
* unexpected layer omissions
* a handoff generated from the wrong accepted input set

## Rejection behavior

The validator does not repair or modify malformed activation handoffs.

Invalid handoffs produce machine-readable rejection records.

Malformed external JSON values must produce rejection records rather than uncaught Python type errors.

## Rejection codes

### `missing_required_field`

A required top-level or row-level field is absent.

### `invalid_schema_version`

The activation handoff uses an unsupported schema version.

### `invalid_hash`

A required SHA-256 value is malformed.

### `invalid_run_status`

The producing run status is outside the documented status vocabulary.

### `invalid_selection_policy`

The extraction-selection policy is missing or malformed.

### `leakage_selection_forbidden`

The extraction policy indicates that Person A used target labels or held-out labels to decide which activations to extract.

### `invalid_chunk_descriptor`

An activation chunk descriptor is incomplete or malformed.

### `duplicate_chunk_id`

Multiple chunk descriptors use the same chunk identity.

### `invalid_index_row`

An activation-index row violates required identity or activation metadata rules.

### `duplicate_activation_identity`

Two activation rows share the same scientific activation identity.

### `duplicate_chunk_row`

Multiple index rows point to the same physical chunk row.

### `invalid_token_positions`

The recorded frame-token positions do not contain the exact visual-token positions required by the locked MineWorld frame layout.

### `chunk_reference_mismatch`

An activation index references a missing chunk, invalid chunk row, or incompatible chunk metadata.

### `metadata_mismatch`

Row-level provenance does not agree with package-level checkpoint, preprocessing, manifest, or run metadata.

### `invalid_cardinality_report`

The required cardinality report is missing or structurally invalid.

### `cardinality_mismatch`

Expected, actual, per-layer, chunk, or activation-index row counts disagree.

## Synthetic accepted fixture

Step 1.4 provides:

`tests/fixtures/activation/accepted_activation_handoff.json`

The fixture contains:

* 1 synthetic trajectory
* 3 model frames
* 2 extraction layers
* 1 hook site
* 6 activation-index rows
* 1 activation chunk
* 1 accepted-manifest hash
* 1 cardinality report

The fixture is structural test data only.

It is not scientific evidence.

## Synthetic activation chunk

Step 1.4 provides:

`tests/fixtures/activation/synthetic_activation_chunk.json`

It contains six synthetic activation vectors.

Each vector has shape:

`[2048]`

The synthetic values exist only to verify storage indexing and row correspondence.

The accepted handoff's chunk descriptor resolves this fixture by relative path, and its declared SHA-256 must equal the hash recomputed from the fixture bytes.

## Synthetic target fixture

Step 1.4 provides:

`tests/fixtures/activation/synthetic_targets.json`

The target rows are deliberately stored in a different order from the activation rows.

The fixture proves that Person B can join using explicit identities rather than row order.

## Rejected synthetic fixtures

Step 1.4 also provides intentionally invalid handoffs for:

* target-label leakage
* activation cardinality mismatch
* invalid frame-token positions
* duplicate scientific activation identity
* row/package provenance mismatch

These fixtures are:

* `rejected_label_leakage.json`
* `rejected_cardinality.json`
* `rejected_token_positions.json`
* `rejected_duplicate_activation_identity.json`
* `rejected_metadata_mismatch.json`

Each fixture must fail for its intended reason.

## Validator expectations

The Step 1.4 validator must:

1. Accept the known-good synthetic activation handoff.
2. Reject target-dependent extraction selection.
3. Reject inconsistent activation cardinality.
4. Reject incorrect visual-token positions.
5. Reject duplicate scientific activation identities.
6. Reject provenance disagreement between rows and handoff metadata.
7. Verify activation chunk row references and the synthetic companion's path and SHA-256.
8. Verify activation vector dtype and the exact `[2048]` shape metadata.
9. Verify the accepted-manifest hash is propagated to activation rows.
10. Verify checkpoint and preprocessing identity.
11. Verify Person B can reproduce total activation counts.
12. Verify Person B can reproduce per-layer activation counts.
13. Verify the accepted-manifest row count against unique represented frame identities.
14. Verify per-layer counts sum to the reported totals.
15. Reject malformed status and dtype metadata without crashing.
16. Verify validation does not mutate the submitted handoff.
17. Verify Person B can join the synthetic target table without using row order and receives the complete frame/site grid.

## Current automated verification

The Step 1.4 tests verify:

* a valid activation handoff passes
* extraction based on target labels is rejected
* cardinality mismatch is rejected
* incorrect token positions are rejected
* duplicate activation identities are rejected
* provenance mismatch is rejected
* the exact `[2048]` row and chunk vector shape is enforced
* malformed run-status and dtype metadata is rejected without crashing
* accepted-manifest row count is reproduced from unique activation frame identities
* per-layer counts sum to the reported totals
* rejected handoffs are not mutated by validation
* the synthetic activation chunk contains six vectors
* every synthetic activation vector has 2,048 elements
* activation chunk row indices agree with the activation index
* the activation chunk descriptor resolves the supplied companion and its SHA-256 matches the companion bytes
* Person B can join targets by explicit identity and reproduce the complete frame/site grid
* Person B can reproduce the total activation row count
* Person B can reproduce per-layer activation counts
* accepted-manifest, checkpoint, and preprocessing hashes propagate correctly

## Step 1.4 pass condition

Step 1.4 passes when Person B can receive the documented synthetic handoff and, without private explanation from Person A:

1. identify every activation row
2. locate every stored activation vector
3. determine its layer and hook site
4. determine which visual tokens produced it
5. determine the pooling method
6. determine its dtype and shape
7. determine its model checkpoint and preprocessing provenance
8. identify the accepted input manifest
9. reproduce total and per-layer row counts
10. join the synthetic target table using documented identities

The synthetic compatibility test must succeed without relying on row ordering.

## Scope boundary

Completing Step 1.4 does not yet freeze schema v1.0.

The following Phase 1 work remains separate:

* Step 1.5 — B→A intervention request contract
* Step 1.6 — A→E rollout and run/artifact registry contracts
* Step 1.7 — cross-role synthetic pipeline
* Step 1.8 — final schema v1.0 freeze and sign-off

## Versioning status

The current implementation is:

`0.1-draft`

It must not yet be described as final schema v1.0.

Final schema v1.0 is frozen only after all Phase 1 interfaces have been tested together and approved in Step 1.8.
