# Person A Phase 3 Wave 4 — Local Implementation Evidence

Baseline commit:

`be101f3174005e94f30eb4be6b98ee4d2aaea628`

Baseline subject:

`Implement MineWorld adapter Wave 3 teacher forcing`

Branch at the implementation gate:

`role/person-a-model`

The local branch and `origin/role/person-a-model` matched, and the worktree
was clean before Wave 4 edits.

## Status

| Roadmap step | Local status | Real-runtime status |
|---|---|---|
| 3.8 free-rollout entry point | IMPLEMENTED LOCALLY | GPU certification pending |
| 3.9 adapter identity and failure behavior | IMPLEMENTED LOCALLY | GPU certification pending |

Phase 3 local implementation is complete. The Phase 3 gate is not yet marked
passed because the consolidated real-runtime certification has not run.

## Official path inspected

The clean external checkout at
`C:\Users\lollo\MineWorld-Upstream` was directly inspected at:

`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

The inspected generation path was:

- `inference.py:lvm_generate`;
- `lvm.py:LlamaForCausalLM.naive_generate`;
- `diagonal_decoding.py:decode_n_tokens`;
- `inference.py:token2video`;
- `vae.py:VAE.token2image`.

The private Wave 4 executor uses the official transformer
`naive_generate` boundary and official `token2video` decoder/writer. It
preserves explicit seed, action tokens, temperature, top-k or top-p, token
count, output rate, float16 CUDA inference mode, and KV-cache reset. It does
not copy the external source and does not call teacher forcing.

## Private implementation

`src/mineocclude/models/_mineworld_adapter_wave4.py` extends the private Wave
3 class. The public protocol and its 24-symbol export set are unchanged.

The rollout validation order is:

1. exact loaded runtime and adapter-code identity;
2. accepted manifest and trajectory identity;
3. token-sequence and `FrameTokenMap` hashes;
4. preprocessing, action-converter, and tokenization profiles;
5. precision, device, sampling, action order, and position budget;
6. output safety and collision checks;
7. official generation;
8. decoded-video, count, shape, rate, byte-size, and hash checks;
9. deterministic metadata serialization.

Any failure through item 6 occurs before the rollout dependency is called.

## Rollout identity and output safety

The request carries official `ConvertedAction` records, explicit sampling
parameters, expected adapter-code identity, accepted-manifest identity,
precision, device, protected inputs, and an exact generation-configuration
hash. The first action is the final recorded context action and preserves the
official action-to-next-frame relationship.

The result and its durable metadata reference:

- complete runtime identity;
- accepted manifest and source-document identity;
- trajectory, token-sequence, and `FrameTokenMap` identities;
- adapter implementation identity;
- seed and sampling configuration;
- generated token and frame identities;
- output path, dimensions, frame rate, byte size, and SHA-256;
- elapsed generation time and CUDA allocation/reservation when provided;
- request and result identities.

Outputs are rejected inside tracked source, inside the pinned external
checkout, on protected input/checkpoint paths, or on an unapproved collision.
The successful metadata does not include a self-hash claim. Runtime failures
receive a small structured failure record in the external evidence directory.

## Adapter code identity

The deterministic code identity sorts and hashes these files:

- `src/mineocclude/models/mineworld_adapter.py`;
- `src/mineocclude/models/_mineworld_adapter_wave2.py`;
- `src/mineocclude/models/_mineworld_adapter_wave3.py`;
- `src/mineocclude/models/_mineworld_adapter_wave4.py`.

Each inventory row records the repository-relative path, SHA-256, and byte
size. Canonical JSON over the identity version and sorted rows produces the
aggregate identity. No self-hashing manifest or signature claim is made.

The CPU failure matrix is stored at:

`tests/fixtures/models/phase3_wave4_failure_matrix.json`

It covers source, asset, checkpoint, VAE, configuration, code, preprocessing,
action-converter, tokenization, schema, API, accepted-manifest, runtime,
sequence, map, precision, device, and output-path mismatches. Spies prove
expensive runtime/VAE/teacher/rollout dependencies are not invoked after a
boundary rejection.

## Consolidated GPU certification

Prepared entry point:

`scripts/run_phase3_adapter_certification.py`

The command has `run` and `validate` modes. The real run accepts explicit
source, asset, evidence, accepted-package, input-media, environment, seed,
precision, and device inputs. It verifies clean revisions and hashes before
checkpoint deserialization, loads the runtime once, runs the real VAE,
constructs the real token map, runs two teacher-forced forwards with 20
externally managed hooks, performs one free rollout, and validates a bounded
report set. It also rechecks the committed 19-case action matrix against the
pinned converter before deserialization.

Expected small reports:

- `adapter_runtime_identity.json`;
- `teacher_forced_certification.json`;
- the rollout metadata JSON;
- `certification_summary.json`;
- `raw_stdout_stderr.log`.

The generated MP4 stays in the external immutable session directory and is
not intended for Git. Report paths are session-relative. The validator
requires the exact check set and verifies the pinned runtime identity,
adapter-code inventory, input identities, two teacher repeats, 20 exact hook
records, activation shapes, separate load/preprocess/action/tokenization/
forward/rollout timings, CUDA memory, rollout media facts, and cross-report
hashes. With `--verify-files`, it also requires and hashes the external inputs
and generated video. Without that option, a relocated small report bundle can
be checked semantically while retaining the recorded large-output hash. The
report set distinguishes local implementation from real-runtime
certification.

Example command after this change is committed and synchronized:

```text
python scripts/run_phase3_adapter_certification.py run \
  --mineworld-source-root /home/sagemaker-user/MineWorld-Upstream \
  --asset-root /home/sagemaker-user/MineWorld-Assets-Pinned \
  --evidence-root /home/sagemaker-user/mineocclude-phase3-evidence \
  --accepted-trajectory-package /external/accepted_trajectory.json \
  --input-mp4 /external/accepted_trajectory.mp4 \
  --environment-report /external/environment_report.txt \
  --session-id person-a-phase3-aws-NEW-IMMUTABLE-ID \
  --seed 20260725 \
  --precision float16 \
  --device cuda:0 \
  --mineocclude-revision NEW_COMMITTED_WAVE4_SHA \
  --confirm-gpu-certification
```

The concrete accepted-package/media paths, immutable session ID, and committed
Wave 4 SHA must be supplied from the later AWS environment. No placeholder in
the example is evidence.

The accepted-package argument is the frozen C-to-A trajectory-package JSON
consumed by `validate_trajectory_package`, not an arbitrary JSONL or action
file. For the one-frame certification rollout it must contain at most 15
complete accepted frame/action pairs and its `media.sha256` must match the
supplied 640 x 360 MP4. The repository's small
`tests/fixtures/trajectory/accepted_package.json` is CPU-only contract
evidence with a synthetic media hash; it has no matching MP4 and is not an AWS
certification input. The complete 4,152-frame ModelScope sample likewise
cannot be passed directly to this bounded certification command. A matching,
explicitly accepted bounded package/media pair must be prepared before AWS.

The environment report must be generated for the new AWS session. The prior
Phase 2 report remains valid Phase 2 evidence but must not be relabeled as an
observation of a new session. The session ID must be new and path-free, and
`--mineocclude-revision` must be the exact clean committed Wave 4 revision.

## Local validation

The final Wave 4 validation cycle records:

- Python AST/static parsing: PASS for all seven Wave 4 Python files;
- JSON fixture parsing: PASS;
- combined Step 3.1, Wave 2, Wave 3, Wave 4, frozen-contract, and Phase 2
  regression cycle: PASS, 182 tests;
- fixture determinism: PASS; repeated generation produced SHA-256
  `f4d9d16e6a465874da8dae72c452325cf491b6ffc929f07ff78b9db8be8011d1`;
- certification CLI dry-run, help, configuration, and validator tests: PASS
  within the combined 177-test cycle;
- full repository suite: 544 passed and 478 subtests passed, with only the
  two pre-existing saved-evidence drift checks failing:
  `tests/analysis/test_synthetic_analysis_chain.py::test_full_chain_is_sealed_non_scientific_and_matches_saved_evidence`
  and
  `tests/integration/test_synthetic_pipeline.py::TestSyntheticCrossRolePipeline::test_checked_machine_readable_report_matches_fresh_execution`;
- `git diff --check`: PASS.

The final bounded audit reproduced those two saved-evidence failures in both
the Wave 4 worktree and a temporary detached worktree at baseline
`be101f3174005e94f30eb4be6b98ee4d2aaea628`. Fresh and saved report hashes
were identical across the two worktrees. They are pre-existing Person B/shared
synthetic-evidence drift, not Wave 4 regressions; no unrelated saved evidence
was rewritten.

## Boundaries and non-claims

Wave 4 does not import or modify activation hook, pooling, or storage modules.
It does not own scientific layer selection, probe training, interventions,
analysis, or registry behavior. The shared schema remains `1.0`; universal
and activation identities are unchanged.

No AWS, CUDA, real checkpoint, real VAE, real transformer, or real rollout
execution occurred during this local implementation. Phase 3 real-runtime
certification remains **PENDING**.
