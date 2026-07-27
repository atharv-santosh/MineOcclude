# Person A Phase 4 Wave 3

## Scope and baseline

Phase 4 Wave 3 implements the local portions of Steps 4.7 and 4.8 on
`role/person-a-model`, starting from
`3f607eec5682dced8f106b000280691a6f6823cf`.
The runtime-grounded v1.1 correction starts from committed Wave 3 revision
`72f7d830b5630a4204b9d47ac81432a92a711227`.

The local change adds one complete-context pooled-extraction helper, one
explicitly enabled limited-unpooled pilot writer/reader, and one prepared
real-runtime probe. It does not run the probe, extract a dataset, select
scientific layers, perform Person B analysis, or change schema version `1.0`.
The SageMaker GPU remains stopped.

The accepted immutable Wave 1 and Wave 2 evidence remains valid. In particular,
Wave 2 already established the exact visual-token mean, detached CPU candidate
ownership, action/neighbor exclusion, and one-context allocated-memory result.
Wave 3 builds on those frozen boundaries rather than reinterpreting them.

### Preserved first runtime attempt

The first real v1.0 runtime attempt,
`person-a-phase4-wave3-aws-20260727-034948`, is immutable failed operational
evidence. Extraction A reached the limited-unpooled pooling audit and failed at
layer 0 before the controlled middle failure or extraction B. Its preserved
failure hashes are:

- `failed_probe.json`:
  `546f170992fdce2050df1c993f3edc8bc34f9adfd137b1a4db2d6ddaf6a61b2a`;
- `raw_stdout_stderr.log`:
  `8c6e7e568646208507da975d70ecfd69ae235bb66bceb45c4fc7b8149d17e14e`.

The failure came from an invalid v1.0 assumption that a CUDA float32 reduction
and an independent CPU float32 reduction of stored float16 rows must be
bitwise equal. The selected runtime values were not reported as nonfinite, and
the failure occurred before the later hook-lifecycle, stale-buffer, identity,
or memory checks. It therefore supplies no evidence of failure in those
boundaries and is not scientific evidence or a successful gate.

## Step 4.7 local implementation: consecutive-extraction safety

`src/mineocclude/activations/store.py` is the existing authoritative activation
storage module, so it now owns the narrow extraction helper. No competing
`extract.py` module was introduced.

`extract_complete_pooled_context()` accepts:

- one complete `Mapping[int, HookCapture]`;
- one frozen `FrameTokenMap`; and
- one explicit hook-site identity.

It requires capture keys exactly `0..19`, rank-three batch-one tensors, common
sequence and hidden dimensions, common dtype/device, common normalization
identity, and a map sequence length equal to the hook sequence. It iterates the
explicit frame identities recorded by `FrameTokenMap`, calls the existing
`select_visual_token_positions()` and `mean_pool_visual_tokens()` operations,
and returns an immutable tuple in frame-then-layer order.

The result contains exactly `frame_count * 20` existing
`PooledVisualActivation` records. Their keys are unique and preserve:

`trajectory_id + model_frame_idx + layer_idx + hook_site`.

The limited-pilot lookup filters only the requested trajectory, frame, and hook
site, then verifies the matching sequence before constructing its layer
mapping. It requires exactly 20 candidates, layers `0..19` exactly once, and
unique complete activation keys. A duplicated candidate therefore cannot be
silently collapsed by dictionary construction; unrelated candidates for other
frames in the same complete context remain valid.

The returned candidates are independently owned, detached, contiguous CPU
`torch.float32` vectors. The tuple retains no hook capture, module, model,
source tensor, selected 336-row tensor, CUDA allocation, or autograd graph.
Ordinary extraction performs no file write and never retains unpooled rows.
Frame-token selection failures retain the map/selection diagnostic category.
An actionable `VisualPoolingError`, including a nonfinite selected activation,
is instead translated to the existing candidate-extraction category with the
original pooling message and cause preserved.

### Prepared real-runtime sequence

`scripts/run_phase4_wave3_extraction_probe.py run` is prepared to execute one
loaded real runtime in this exact order:

1. successful extraction A;
2. one deliberate callback failure at decoder layer 10; and
3. successful extraction B.

The accepted eight-frame input is validated, decoded, preprocessed, action
converted, and tokenized once. The runtime loads once. Exactly three forward
attempts are made: two successful extractions and one expected failure.

Each attempt creates a fresh `ScopedHookManager`. It records hook counts before
registration, the actually observed active count during callbacks, counts after
cleanup, callback counts by layer, observed capture keys, closed-manager state,
and unresolved handles. Every layer must begin at zero hooks, all 20 hooks must
be active during forwarding, and every layer must return to zero afterward.
Successful attempts must capture layers `0..19` exactly once.

The middle attempt raises `ForcedExtractionProbeFailure` from the probe-only
capture callback at layer 10. The callback cannot run until all 20 handles have
been registered by `ScopedHookManager.__enter__`. The exception interrupts the
forward, exercises the manager's normal cleanup path, accepts no candidate
batch, and discards its partial capture mapping before extraction B. Production
extraction has no failure-injection path.

The committed Phase 2 same-runtime repeatability rule is `rtol=1e-3` and
`atol=1e-3`. Extraction A and B therefore use `torch.allclose` with those exact
tolerances and require zero unequal candidates. Each candidate and the
aggregate report retain the measured maximum absolute difference; each
candidate also records the maximum elementwise tolerance ratio so the validator
can require it to be at most one. Keys, ordering, counts, shapes, dtype/device
metadata, detachment, contiguity, visual-token counts, and hook-site identity
must also match. No new or looser tolerance is introduced.

### Memory rule

The probe synchronizes and records:

- the baseline after the one runtime load and one tokenization, before
  extraction A;
- allocated/reserved memory after extraction A capture cleanup;
- allocated/reserved memory after forced-failure cleanup;
- allocated/reserved memory after extraction B capture cleanup; and
- peak allocated and reserved memory.

With `B` as baseline allocated bytes and `T = 1,048,576` bytes, each cleanup
measurement `C` must satisfy:

`C <= B + T`.

Extraction B must additionally satisfy:

`allocated_after_B <= allocated_after_A + T`.

The independent validator recomputes both equations from the numeric
measurements. Reserved memory is retained as allocator diagnostics and has no
allocator-naive pass threshold. The probe never calls `torch.cuda.empty_cache()`
or `backward()`.

## Step 4.8 local implementation: limited unpooled pilot

Unpooled retention is separate and explicit:
`write_limited_unpooled_pilot(..., enabled=True)`. Its default is disabled.
Ordinary complete-context extraction returns pooled candidates only and creates
no artifact.

The prepared real probe selects the first explicit `FrameTokenMap` span
(`model_frame_idx 0` in the accepted context) and saves only:

- one trajectory/frame identity;
- hook site `decoder_layer_output_residual_stream`;
- layers `0..19`;
- exactly 336 explicit visual rows per layer; and
- hidden size 2048.

The numeric payload is one deterministic, uncompressed `.npz` file with:

- `token_values`: `[20, 336, 2048]`, source-preserving `float16`;
- `pooled_means`: `[20, 2048]`, independently owned CPU `float32` rows that
  are byte-bound to the extraction-A pooled candidates;
- `layer_indices`: exact integer values `0..19`; and
- `visual_positions`: the exact 336 absolute positions for the selected frame.

The raw `token_values` payload is 27,525,120 bytes. The complete serialized NPZ
adds 163,840 bytes of pooled rows and must not exceed 32 MiB (33,554,432
bytes). Arrays are NumPy numeric arrays only; object arrays and pickle are
forbidden, and readback always uses `allow_pickle=False`.

Layers are copied sequentially: each explicit 336-row selection is detached,
moved to CPU, made contiguous, cloned, and released before processing the next
layer. No second 20-layer CUDA copy is created. The artifact excludes action
rows, neighboring-frame rows, and whole-sequence tensors.

The adjacent JSON manifest records schema/artifact versions, session identity,
scientific identity, hook/capture facts, FrameTokenMap identity, all pinned
runtime/config/checkpoint/input identities, profile identities, artifact
size/hash, explicit scope assertions, and per-layer pooling-audit hashes. Its
classification is:

`limited_one_frame_unpooled_pilot`.

It explicitly records that dataset-wide unpooled storage is disabled. Artifact
and manifest writes refuse overwrite and use same-directory temporary files
followed by atomic rename. The completed manifest is not claimed to sign or
hash itself.

The public writer treats artifact write, manifest write, and final independent
self-validation as one all-or-nothing operation. Any ordinary failure removes
both operation-created final files and both same-directory temporary paths;
pre-existing output or temporary paths fail before writing and are never
removed. If cleanup itself fails, the original project-owned failure remains
the raised exception and the cleanup failure is retained as its explicit
cause. Successful return therefore means exactly one independently validated
NPZ and one independently validated manifest exist.

### Independent pooling reproduction

The independent reader reopens the NPZ with `allow_pickle=False`, checks its
exact four-array inventory, numeric dtypes, shapes, 20 layer indices, one
complete 336-row visual prefix, identities, hashes, and size bound.

Artifact/probe v1.1 preserves two different guarantees:

1. exact candidate binding: every stored `pooled_means` row has the same
   byte-level SHA-256 as its extraction-A `PooledVisualActivation`; and
2. independent token reproduction: CPU-recomputed means from the stored token
   rows must be close to those exact stored production vectors under
   `rtol=1e-3` and `atol=1e-3`.

For each layer the reader:

1. reads the saved `[336, hidden]` `float16` rows;
2. casts them to `torch.float32`;
3. means over only the token axis; and
4. applies `torch.allclose` against the corresponding exact stored
   `pooled_means` row.

It independently recomputes the mean hash, maximum absolute difference,
maximum tolerance ratio, and unequal-layer count rather than trusting manifest
or report PASS fields. Cross-device reduction results are not falsely claimed
to be bitwise identical, and no tolerance looser than `1e-3/1e-3` is accepted.

## Runtime probe

Probe v1.1,
`person-a-phase4-wave3-extraction-probe-v1.1`, exposes exactly:

- `preflight`: reuses the frozen Phase 3 CPU package/media/environment
  validator and adds the exact Wave 3 counts. It requires an unused session,
  eight complete frame identities, 20 layers, hidden size 2048, 336 visual
  tokens, 11 action tokens, one runtime load, three attempts, two successes,
  one forced failure, one unpooled frame, `float16`, and `cuda:0`. It imports no
  PyTorch, queries no CUDA, decodes no video, loads no runtime, creates no
  session, and permits no overwrite.
- `run`: only after preflight and `--confirm-runtime-probe`, creates a new
  immutable session, loads once, tokenizes once, performs the exact
  success/failure/success sequence, writes one limited NPZ and manifest,
  records bounded candidate hashes/metadata, and internally validates the
  report. A failed run retains an immutable raw log and failure record.
- `validate`: strictly parses the report, rejects duplicate/nonfinite JSON,
  verifies counts, coverage, hook lifecycle, exact A/B comparison, memory
  equations, paths, sizes, hashes, and exactly one approved NPZ. It reopens the
  artifact independently and rejects other `.pt`, `.pth`, `.npy`, `.npz`,
  `.ckpt`, or `.safetensors` files. It imports neither MineWorld nor a model and
  performs no CUDA work.

The intended later AWS command shape is:

```text
/home/sagemaker-user/.conda/envs/mineworld/bin/python \
  scripts/run_phase4_wave3_extraction_probe.py preflight \
  --mineworld-source-root <observed-pinned-source-root> \
  --asset-root <observed-pinned-asset-root> \
  --evidence-root <new-external-evidence-root> \
  --accepted-trajectory-package <uploaded-bounded-package.json> \
  --accepted-trajectory-package-sha256 <verified-sha256> \
  --input-mp4 <uploaded-bounded-scene.mp4> \
  --input-mp4-sha256 <verified-sha256> \
  --environment-report <fresh-environment-report.txt> \
  --environment-report-sha256 <verified-sha256> \
  --session-id <new-immutable-session-id> \
  --seed 7 --precision float16 --device cuda:0 \
  --mineocclude-revision <reviewed-committed-wave3-sha>

/home/sagemaker-user/.conda/envs/mineworld/bin/python \
  scripts/run_phase4_wave3_extraction_probe.py run \
  <the-identical-explicit-arguments-above> \
  --confirm-runtime-probe

/home/sagemaker-user/.conda/envs/mineworld/bin/python \
  scripts/run_phase4_wave3_extraction_probe.py validate \
  --report <new-session>/extraction_probe_report.json
```

The corrected v1.1 command has not been run locally or on AWS. The earlier
v1.0 failed session remains immutable and is not reused.

## Files and local validation

Changed or added:

- `src/mineocclude/activations/store.py`;
- `tests/activations/test_store.py`;
- `scripts/run_phase4_wave3_extraction_probe.py`;
- `tests/activations/test_phase4_wave3_probe.py`;
- `docs/status/person_a_phase4_wave3.md`.

The bounded local validation cycle uses the isolated verified interpreter and:

```text
PYTHONPATH=C:\Users\lollo\MineOcclude\src
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
PYTHONDONTWRITEBYTECODE=1
```

The ordered local validation results are:

- `python -m pytest -q -p no:cacheprovider
  tests/activations/test_store.py`: PASS, 17 tests and 22 subtests;
- `python -m pytest -q -p no:cacheprovider
  tests/activations/test_phase4_wave3_probe.py`: PASS, 18 tests and 6
  subtests;
- `python -m pytest -q -p no:cacheprovider
  tests/activations/test_pool.py`: PASS, 21 tests and 28 subtests;
- `python -m pytest -q -p no:cacheprovider
  tests/activations/test_hooks.py`: PASS, 22 tests and 7 subtests;
- `python -m pytest -q -p no:cacheprovider
  tests/activations/test_phase4_wave2_probe.py`: PASS, 11 tests and 12
  subtests;
- `python -m pytest -q -p no:cacheprovider
  tests/contracts/test_activation_contract.py`: PASS, 22 tests and 3
  subtests;
- `python scripts/run_phase4_wave3_extraction_probe.py --help`: PASS, with
  exactly `preflight`, `run`, and `validate`;
- Ruff over all four changed Python files: PASS;
- AST parsing of all four changed Python files: PASS;
- `git diff --check`: PASS.

No test warning was emitted in this cycle because the isolated commands
disabled pytest's cache provider. The CPU-only preflight boundary test uses a
controlled shared-preflight result and proves all five side-effect flags false;
no real package, video, checkpoint, CUDA, or model operation was run.

## Completion boundary

Steps 4.7 and 4.8 are implemented locally and have CPU-only tests. Neither step
is marked complete: the required success-failure-success report and the real
one-frame unpooled pooling audit must still be produced by one later bounded
AWS run from an exact reviewed commit.

No dataset-wide extraction, Person B analysis, scientific layer selection,
localization, intervention, training, schema change, or Phase 5 work occurred.
No AWS or GPU execution occurred during the correction pass; the GPU remains
stopped and runtime evidence remains pending.
Schema version remains `1.0`, and the accepted Wave 1 and Wave 2 evidence
remains valid.
