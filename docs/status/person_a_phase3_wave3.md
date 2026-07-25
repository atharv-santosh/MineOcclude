# Person A Phase 3 Wave 3 — Local Implementation Evidence

Scope: Steps 3.6 and 3.7 together

Shared schema version: `1.0`

Adapter API version: `person-a-mineworld-adapter-v1.0`

Implementation baseline:
`7e31d6047212cabcc1ce19a8fe85a16309557655`
(`Implement MineWorld adapter Wave 2 inputs`)

## Status

| Step | Local status | Runtime-certification status |
|---|---|---|
| 3.6 VAE tokenization, sequence, and FrameTokenMap | IMPLEMENTED LOCALLY | Real adapter VAE execution pending later GPU certification |
| 3.7 teacher-forced execution | IMPLEMENTED LOCALLY | Real adapter transformer execution pending later GPU certification |

Step 3.8 free rollout and Step 3.9 certification were not implemented.

## Private implementation boundary

Public callers continue to import only
`mineocclude.models.mineworld_adapter`. The factory now constructs
`mineocclude.models._mineworld_adapter_wave3._Wave3MineWorldAdapter`, a private
subclass of the Wave 2 implementation. The public export set and API version
did not change.

The Wave 3 implementation owns:

- invocation of the private loaded VAE tokenization method;
- exact visual/action sequence assembly;
- complete-pair context truncation;
- `FrameTokenMap` construction and identity;
- teacher-forced transformer invocation;
- bounded temporary external-hook compatibility;
- structured failures and output metadata.

It does not import or modify activation hooks, pooling, storage, probes,
interventions, rollout, analysis, or registry code.

## Pinned source paths inspected

External checkout:
`C:\Users\lollo\MineWorld-Upstream`

Revision:
`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

The checkout was clean when inspected. Direct source review covered:

- `vae.py::VAE.tokenize_images`, which returns VQ
  `min_encoding_indices`;
- `mineworld.py::step_video`, including normalized frame batching, VAE
  tokenization, 336-token flattening, and visual/action interleaving for
  generation prefill;
- `lvm.py::LlamaModel.forward`, which derives the causal mask from explicit
  position IDs;
- `lvm.py::LlamaForCausalLM.forward` and `refresh_kvcache`;
- `mineocclude.models.phase2_aws._build_teacher_input` and
  `execute_teacher_forced`, the previously validated 16 complete-pair
  teacher-forced path.

No external source was copied or modified.

## Sequence and context semantics

Each included accepted frame contributes exactly:

- 336 visual tokens from the VAE boundary;
- 11 already converted official action tokens;
- 347 total pair positions.

The teacher sequence uses complete pairs, including the final accepted action
record. For histories longer than 16 pairs, only the oldest complete pairs are
excluded. The most recent 16 remain in accepted order, scientific
`model_frame_idx` values are not renumbered, and context-relative position IDs
run from zero through the assembled sequence length minus one.

Every included `FrameTokenSpan` records the exact visual and action positions,
pair bounds, original accepted-pair index, context-relative pair index, and
accepted predecessor/successor identities. Excluded accepted identities are
recorded separately. Token-sequence and complete-map SHA-256 identities are
recomputed before teacher forwarding.

## Teacher-forced boundary

The private real executor uses the loaded pinned model and calls:

`model.transformer(input_ids=input_ids, position_ids=position_ids)`

after a KV-cache refresh, with explicit seed, batch size 1, float16 CUDA
precision, evaluation state, and `torch.inference_mode()`. It performs no
autoregressive generation and does not call free rollout.

The optional public request callback receives the ordered decoder-module
names/objects only for a caller-managed context around the forward. This is
the minimum additive capability required because the Step 3.1 request had no
way for external activation code to attach temporary hooks to the private
runtime. The adapter supplies all 20 identity-bound decoder modules but does
not choose scientific layers or hook sites, register hooks, pool output, or
store activations.

## Fixture

`tests/fixtures/models/phase3_wave3_token_map.json` is a compact
machine-readable three-pair pilot. It records exact pair ranges and causal
neighbors for model-frame indices 40, 41, and 42, plus the complete token and
map hashes.

The fixture is classified `cpu_fake_official_boundary`: its deterministic
visual token IDs come from a controlled fake VAE boundary. It is not real VAE
output and is not real runtime certification.

Fixture file SHA-256:
`314b0e1403ca09cee66d6c2bfc8daf938a39f9da08e8d4b2c7bd7d86e4b84228`

Regenerate or verify it with:

```powershell
$env:PYTHONPATH = "src"
python scripts/build_phase3_wave3_fixtures.py `
  --output tests/fixtures/models/phase3_wave3_token_map.json `
  --check
```

## Failure ordering

The tested order is:

`ValidatedTrajectory`
→ preprocessing/profile and payload verification
→ deterministic VAE tokenization
→ action/profile verification
→ complete sequence construction
→ `FrameTokenMap` validation
→ teacher input revalidation
→ external hook context
→ model forward

Any earlier failure prevents the injected model-forward boundary from being
called.

## Local validation

The bounded Wave 3 validation cycle covers:

- Python AST parsing for modified Python;
- JSON parsing and deterministic fixture regeneration;
- Step 3.1 public API tests;
- Wave 2 tests;
- Wave 3 unit and integrated fake-runtime tests;
- frozen identity, trajectory, activation, and schema contract tests;
- relevant Phase 2 token-layout and teacher-forced regressions;
- direct source parity inspection;
- `git diff --check`.

Recorded results:

- Ruff static checks: PASS;
- Python AST and fixture JSON parsing: PASS;
- deterministic fixture regeneration: PASS;
- Step 3.1, Wave 2, and Wave 3 adapter tests:
  56 passed, 118 subtests passed;
- frozen identity, trajectory, activation, and schema tests:
  56 passed, 35 subtests passed;
- selected Phase 2 context/preprocessing/token/hook/repeatability regressions:
  9 passed, 26 subtests passed, 40 unrelated tests deselected;
- direct clean pinned-source parity: PASS;
- `git diff --check`: PASS.

No AWS, CUDA, checkpoint, real VAE, real transformer, free-rollout, or full
repository test-suite execution is claimed.

## Remaining work

Step 3.8 must implement free rollout without using teacher forcing as an
implicit fallback. Step 3.9 must certify end-to-end identity and failure
propagation and perform the later real-runtime/GPU check required by the
roadmap. This Wave 3 record does not claim either step.
