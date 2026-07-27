# Person A Phase 4 Wave 2

## Scope and baseline

Phase 4 Wave 2 implements the local portions of Steps 4.4, 4.5, and 4.6 on
`role/person-a-model`, starting from
`7a24809c2ccb5e831ff28c856a1dcfdec5c4ebc3`.

The change adds visual-token mean pooling, detached CPU ownership, tensor-level
action and neighbor exclusion tests, and a bounded real-runtime probe. It does
not implement Step 4.7 long-running extraction safety or Step 4.8 general
unpooled activation evidence.

The bounded Wave 2 runtime gate subsequently passed in immutable session
`person-a-phase4-wave2-aws-20260727-015157` at MineOcclude revision
`76d2a5a462e3daba0baa374e92c7e7b20de393b8`.

## Step 4.4: COMPLETE — explicit visual-token mean

`mean_pool_visual_tokens()` accepts an already validated
`VisualTokenSelection`; it does not reconstruct positions from frame number or
row order. For one batch row and hidden component \(h\), the operation is:

\[
z_h = \frac{1}{336}\sum_{p \in P_{\mathrm{visual}}} A_{0,p,h}
\]

where `P_visual` is the exact tuple of 336 positions supplied by the frozen
`FrameTokenMap` boundary. The implementation selects those positions with a
device-local index tensor, casts only the selected values to `torch.float32`,
and means only across the token axis. Batch size must be exactly one. The
hidden axis is preserved, producing shape `[hidden]`.

Every `PooledVisualActivation` synchronously binds:

`trajectory_id + model_frame_idx + layer_idx + hook_site`.

It also records source batch/sequence/hidden facts, selected-token count,
pooling identity, and source/returned dtype and device. The operation rejects
non-tensors, malformed shapes, non-real-floating dtypes, invalid selections,
identity errors, and nonfinite selected visual values through project-owned
error codes.

The accepted real-runtime report contains 160 candidates from 8 frames across
all 20 decoder layers. Each candidate binds one
`trajectory_id + model_frame_idx + layer_idx + hook_site`, has final shape
`[2048]`, and exactly equals the independently computed mean of its explicit
336 visual-token rows. Every candidate records
`max_abs_difference = 0.0`.

## Step 4.5: COMPLETE — detached CPU ownership

The returned candidate is independently owned, contiguous, detached
`torch.float32` on CPU. It has shape `[hidden]`, does not require gradients,
has no `grad_fn`, and retains neither the source hook tensor nor the selected
`336 x hidden` tensor. Mutation or deletion of the source cannot change the
candidate, and candidate mutation cannot change the source.

The ordinary pooling API performs no CUDA synchronization, cache clearing,
file writing, or serialization. Float32 accumulation is the approved candidate
precision; later Person B analysis precision remains outside this step.

The prepared runtime probe measures one already-loaded real context. After one
teacher-forced forward has captured all 20 layers, it records the post-forward
CUDA baseline, pools all 20 candidates for each real frame, moves each
candidate to CPU immediately, and measures allocated/reserved memory at
explicit per-frame boundaries. Every per-frame allocated-memory measurement
and the final allocated-memory measurement must remain within 1 MiB of the
post-forward baseline. The report records and the validator recomputes each
baseline delta, the maximum per-frame allocation, and the maximum per-frame
delta. Reserved memory is recorded for allocator visibility but is not subjected
to a simplistic allocator-naive pass threshold. The probe does not call
`torch.cuda.empty_cache()` and does not perform a second forward or a long
stress loop.

The bounded one-real-context memory gate passed. Every returned candidate was a
detached, contiguous CPU `torch.float32` vector; no source CUDA tensor or
selected 336-row matrix was retained as a candidate or saved as evidence. Every
per-frame allocation remained within the fixed tolerance, the maximum
after-frame allocated delta was 0 bytes, and the final allocated delta was
0 bytes. All 20 temporary hook handles were removed successfully.

This result is limited to the required bounded Wave 2 one-context gate. It does
not establish the long-running extraction safety reserved for Step 4.7.

## Step 4.6: COMPLETE — contribution exclusion

Local tests independently compute the direct mean from the same explicit 336
rows and require exact `torch.equal` equality. They place extreme, mutated,
and nonfinite values in action rows; alter neighboring visual/action rows and
pair boundaries; and verify those changes cannot affect the target visual
mean. A known selected-row delta changes the output by exactly `delta / 336`,
while NaN or infinity in any selected row fails closed.

The future runtime probe repeats the contribution proof on actual hook tensors.
For one identified real frame and every one of the 20 decoder layers, it:

1. pools the original explicit visual positions;
2. clones only that layer tensor;
3. independently recomputes the visual selection and changes all 11 action
   rows with alternating finite positive/negative sentinels;
4. derives the actually modified rows by comparing the clone to the original
   tensor across the hidden dimension;
5. compares and hashes the visual-position tuple before and after mutation;
6. requires the actual changed-row set to equal exactly the declared 11 action
   positions and the visual selection to remain unchanged;
7. pools and records the finite result, then deletes the finite clone and all
   finite-only temporaries;
8. only then creates a nonfinite clone, independently recomputes the visual
   selection, and assigns NaN, positive infinity, and negative infinity across
   all 11 action rows;
9. derives and checks the nonfinite changed-row set and visual-selection hashes;
   and
10. deletes the nonfinite clone and temporaries before proceeding to the next
    layer.

This is a structural contribution test on captured activations, not a model
rerun with changed scientific actions. The evidence fields are derived from
actual tensor differences rather than being asserted from intended indices.

The accepted proof used real decoder hook tensors on all 20 layers. For both
the finite-sentinel and NaN/+Inf/-Inf variants, the derived changed-row set was
exactly the intended 11 action positions, the explicit visual selection was
unchanged, and the resulting pooled vector remained exactly equal to the
original. Local tests continue to cover neighboring-frame contamination and
action-boundary off-by-one failures.

## Runtime probe

`scripts/run_phase4_wave2_pooling_probe.py` provides three explicit modes:

- `preflight`: reuses the frozen Phase 3 package/media/environment boundary,
  verifies exact input hashes, 20 layers, hidden size 2048, complete context
  identities, `float16`/`cuda:0`, one forward, and unused immutable session
  identity. It imports no PyTorch module, queries no CUDA state, loads no
  runtime, and creates no session directory.
- `run`: after successful preflight and explicit confirmation, creates one new
  immutable session, loads the runtime once, performs exactly one
  teacher-forced forward under `ScopedHookManager`, pools every real
  frame/layer candidate, performs direct-mean/action-exclusion/memory checks,
  and writes only bounded hashes and metadata. It requires all 20 decoder
  modules to have zero pre-existing forward hooks before manager construction,
  and requires zero hooks plus a closed manager after the forward.
- `validate`: independently requires full frame/layer/hook identity coverage,
  exact candidate/action/memory results, one forward, hook cleanup, referenced
  hashes, and absence of saved unpooled tensors.

## Accepted runtime evidence

The accepted immutable evidence is stored at:

`docs/status/phase4_runtime/person-a-phase4-wave2-aws-20260727-015157/`

Identity and environment:

- session ID:
  `person-a-phase4-wave2-aws-20260727-015157`;
- MineOcclude revision:
  `76d2a5a462e3daba0baa374e92c7e7b20de393b8`;
- MineWorld revision:
  `9f49efbcc68a5f0cf60e78f0abc566eac409282f`;
- ModelScope asset revision:
  `0dd5561ab317115831badc50e09a6ebe98693d0e`;
- qualified interpreter:
  `/home/sagemaker-user/.conda/envs/mineworld/bin/python`;
- Python `3.10.20`;
- precision `float16`;
- device `cuda:0`;
- NVIDIA L4 in the pinned validated environment;
- exactly one teacher-forced forward.

The run exited with status 0, the independent validator exited with status 0,
and `pooling_probe_report.json` records overall status `PASS`. The report
contains 8 frames, 20 layers, 160 of 160 expected candidates, 20 successful
action-exclusion layer records, memory status `PASS`, 20 complete captures,
successful hook cleanup, and
`unpooled_activation_artifacts_saved = false`.

The downloaded evidence archive SHA-256 is:

`79d7cd0e26a41525a16797130b529e742d4721bfe0064f710c9699808a68bf9b`

The internal `export_file_hashes.sha256` inventory was reverified locally:
all eight listed non-self evidence files match their recorded SHA-256 values.

## Files and local validation

Changed or added:

- `src/mineocclude/activations/pool.py`;
- `tests/activations/test_pool.py`;
- `tests/activations/test_phase4_wave2_probe.py`;
- `scripts/run_phase4_wave2_pooling_probe.py`;
- `docs/status/person_a_phase4_wave2.md`.

The bounded local validation cycle covers production pooling, Wave 1 hook
compatibility, CPU-only probe boundaries, adapter/activation-contract
compatibility, CLI help, Ruff, AST parsing, and `git diff --check`. Exact
commands and results, using the isolated verified test interpreter and required
environment variables, were:

- `python -m pytest -q tests/activations/test_pool.py`: PASS, 21 tests and
  28 subtests; one inaccessible pytest-cache warning;
- `python -m pytest -q tests/activations/test_hooks.py
  tests/activations/test_pool.py`: PASS, 43 tests and 35 subtests; one
  inaccessible pytest-cache warning;
- `python -m pytest -q
  tests/activations/test_phase4_wave2_probe.py`: PASS, 11 tests and 12
  subtests; one inaccessible pytest-cache warning;
- `python -m pytest -q tests/models/test_mineworld_adapter.py
  tests/models/test_mineworld_adapter_wave3.py
  tests/models/test_mineworld_adapter_wave4.py
  tests/contracts/test_activation_contract.py`: PASS, 81 tests and 72
  subtests; four pre-existing `mcdataset.py` invalid-escape warnings;
- `python scripts/run_phase4_wave2_pooling_probe.py --help`: PASS, with
  `preflight`, `run`, and `validate` displayed;
- Ruff on all four changed Python files: PASS;
- AST parsing of all four changed Python files: PASS;
- `git diff --check`: PASS.

The CPU-only preflight was exercised through its narrow unit boundary with a
stubbed shared Phase 3 preflight result. It recorded all four false side-effect
flags and created no session directory. The CLI intentionally has no
synthetic-success mode that could be mistaken for certification, so no
standalone fake CLI preflight was reported as runtime evidence.

## Completion boundary

Steps 4.4, 4.5, and 4.6 are complete, including their bounded real-runtime
evidence. The existing immutable Wave 1 AWS evidence remains valid and is
complemented by the accepted Wave 2 pooling, ownership, exclusion, and memory
evidence.

Remaining scope is explicit:

- Step 4.7 remains unimplemented;
- Step 4.8 remains unimplemented;
- no dataset-wide extraction was performed;
- no Person B analysis, standardization, or regression was performed;
- schema version remains `1.0` and no schema was changed.
