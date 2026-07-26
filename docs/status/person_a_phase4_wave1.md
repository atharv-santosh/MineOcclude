# Person A Phase 4 Wave 1

## Scope and baseline

Phase 4 Wave 1 implements only Steps 4.1, 4.2, and 4.3 on
`role/person-a-model`, starting from
`2eef2a4cd0f19e0e1b9897f2ac38dffa480e176b`.

The implementation is limited to decoder hook-site discovery, temporary hook
lifetime, hook-output normalization, and explicit visual-position selection.
It does not implement pooling, asynchronous storage, probe training,
interventions, or any later Phase 4 step.

## Step 4.1: frozen discovery rules

`discover_decoder_hook_site()` treats the loaded model's `named_modules()`
stream as the discovery authority. It does not traverse a remembered Llama
attribute chain. Candidate layer names must form one and only one parent group
whose final component is an integer and whose exact index set is `0..19`.

The discovery fails closed for duplicate module names or indices, missing or
non-contiguous indices, counts other than 20, multiple complete groups,
aliased module objects, modules without forward-hook support, and inconsistent
fully qualified module types. The result is ordered by `layer_idx` and records:

- `layer_idx`;
- exact `module_name`;
- fully qualified `module_type`;
- conceptual site `decoder_layer_output_residual_stream`;
- discovery identity
  `person-a-phase4-decoder-output-v1.0:9f49efbcc68a5f0cf60e78f0abc566eac409282f`;
- the dynamically discovered indexed name pattern.

The expected real pattern is
`transformer.model.layers.{layer_idx}`. This expectation is evidence-backed,
not the discovery mechanism.

### Output normalization

One hook output is accepted only when it identifies one positive
`[batch, sequence, hidden]` tensor without flattening:

- a direct tensor;
- a tuple with exactly one tensor-like value at validated index `0`;
- a mapping with exactly one tensor-like value under
  `last_hidden_state`.

An empty, malformed, two-dimensional, multi-tensor, unknown-field, or otherwise
ambiguous output fails. Normalization retains the original tensor object and
records the batch, sequence, and hidden dimensions plus the exact container
rule that selected it.

### Existing real-runtime evidence

The committed Phase 2 architecture report records exactly 20
`LlamaDecoderLayer` modules at
`transformer.model.layers.0` through
`transformer.model.layers.19`. The Phase 2 teacher-forced report records
20/20 captures on both repeats, each with shape `[1, 5552, 2048]`, dtype
`torch.float16`, device `cuda:0`, and successful hook cleanup. The Phase 3
certification records the same 20 names on two repeats with shape
`[1, 2776, 2048]`.

Those reports record the normalized tensor but not the raw Python output
container before the existing direct-versus-tuple extraction. Therefore one
later minimal real-runtime probe must record whether the loaded
`LlamaDecoderLayer` output is direct or tuple-based and, for a tuple, confirm
that the residual is at index `0`. Wave 1 does not invent that missing fact and
does not run AWS.

## Step 4.2: scoped hook lifetime

`ScopedHookManager` is single-use. On entry it clears its capture buffer and
registers exactly one hook for every frozen layer. Captures are keyed and
exposed in explicit `layer_idx` order, never callback-arrival order.

All handles are removed:

- after a complete successful context;
- after a forward exception;
- after normalization or capture-callback failure;
- after duplicate or inconsistent capture;
- on explicit `close()`;
- whenever context exit runs.

Cleanup is idempotent. Re-entry after closure, callbacks after closure,
duplicate callbacks, missing callbacks, inconsistent shapes or normalization
sites, partial registration, and incomplete 20-layer coverage fail clearly.
The manager does not mutate model outputs or perform disk storage.

## Step 4.3: FrameTokenMap-only selection

`select_visual_token_positions()` requires an explicit
`trajectory_id + model_frame_idx`, a frozen `FrameTokenMap`, and the observed
hook sequence length. It returns a `VisualTokenSelection` containing the exact
336 positions stored in the matching span. It never reconstructs a slice from
frame arithmetic.

The selector revalidates the map at the boundary. It requires:

- one unambiguous matching scientific frame identity;
- exactly 336 unique, increasing visual positions;
- exactly 11 unique, increasing action positions per span;
- integer, non-negative, in-bounds positions;
- exact agreement between map and hooked sequence lengths;
- ordered context-relative pair indices;
- full, non-overlapping sequence coverage;
- visual positions disjoint from every action position;
- selected positions disjoint from every neighboring frame.

Missing or duplicate identities, malformed maps, count errors, duplicate or
out-of-bounds positions, action overlap, and neighboring-frame contamination
fail closed.

## Validation

The focused Wave 1 test cycle covers discovery, output normalization, hook
lifetime and cleanup, repeated independent runs, and first/middle/final/
context-boundary FrameTokenMap selection.

With `PYTHONPATH=C:\Users\lollo\MineOcclude\src`,
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, and `PYTHONDONTWRITEBYTECODE=1`, the
isolated test runner produced:

- `python -m pytest -q tests/activations/test_hooks.py
  tests/activations/test_pool.py`: PASS, 27 tests and 14 subtests;
- `python -m pytest -q tests/models/test_mineworld_adapter.py
  tests/models/test_mineworld_adapter_wave3.py
  tests/models/test_mineworld_adapter_wave4.py
  tests/contracts/test_activation_contract.py`: PASS, 81 tests and 72
  subtests, with four pre-existing `mcdataset.py` invalid-escape
  deprecation warnings;
- Python AST parsing of all four added or modified Wave 1 Python files: PASS;
- Ruff static checking of all four Wave 1 Python files: PASS.

## Explicit non-implementation

Step 4.4 mean pooling was not implemented. `pool.py` contains only strict
position selection; it does not read activation values or calculate a pooled
vector.
