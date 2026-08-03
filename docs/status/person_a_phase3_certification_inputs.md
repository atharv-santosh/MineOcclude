# Person A Phase 3 Certification-Input Preparation

Status: **READY FOR AWS INPUT UPLOAD**

This record covers CPU-only preparation of the bounded, non-scientific
engineering input for the later Person A Phase 3 GPU certification. It does
not claim that the GPU certification, real VAE, teacher-forced execution, or
rollout has run.

## Source identities

- Person A baseline:
  `bdb08d570df8a300213924992eecd4b62d2f920d`
- Person C handoff:
  `82ef1212091b3f32eac02d7eabe25d55376086f2`
- MineWorld source:
  `9f49efbcc68a5f0cf60e78f0abc566eac409282f`
- ModelScope asset revision:
  `0dd5561ab317115831badc50e09a6ebe98693d0e`
- C6A trajectory:
  `layout_00_ep9410`
- Real impulse fixture:
  `layout_00_ep9440`

Both Git worktrees and the external MineWorld checkout were clean at the
preparation gate. Person C was read only.

## Production command

The project-owned entry point is:

`scripts/prepare_phase3_certification_inputs.py`

It provides:

- `prepare`, which verifies and extracts both frame archives, validates the
  complete C6A package, verifies the real impulse, runs the pinned official
  action converter, selects the earliest valid eight-pair window, writes the
  lossless bounded MP4 and derivative package, and runs semantic negative
  checks;
- `validate`, which independently checks the external bundle without
  PyTorch, CUDA, an AWS environment report, or model assets.

The reusable implementation is isolated in:

`src/mineocclude/models/phase3_certification_inputs.py`

It does not change the frozen trajectory or identity contracts and does not
change the MineWorld adapter.

## Archive and package results

The accepted episode package passed the frozen Person A trajectory validator
with 129 synchronized records. The committed Person C QA report is accepted.
The original MP4 independently probed as 640 by 360, 20/1 fps, 129 declared
and decoded frames, and 6.45 seconds.

The C6A archive matched:

`aaa38084e59cd20e70433c9ab169ecb140edde7a0f75e8bf86363bf95ebfbc2b`

The impulse archive matched:

`823825b80d570d2f6df1bca40d765df62a2e3b47ffd82fda70d0bb18564c01d9`

All 129 C6A PNGs and all 60 impulse PNGs matched their per-frame inventories.
Both source archives also contain macOS AppleDouble sidecars. The preparation
tool ignores only the exact sidecar names associated with the expected frame
directory and inventoried PNGs. It still rejects unknown files, extra PNGs,
duplicates, links, absolute paths, and traversal.

The independent impulse check found the genuine 20-degree yaw action at index
29 and the dominant pixel effect in transition 29 to 30, giving causal offset
zero:

`action_i affects visual_i -> visual_(i+1)`

The preparation records both the Person C QA effect measurement and the
independent archive-frame measurement rather than treating their different
pixel-difference magnitudes as identical.

## Action conversion and bounded window

The pinned `MCDataset.json_action_to_env_action` and
`get_action_index_from_actiondict` path was used with vocabulary offset 8192.
The committed 19-case golden action matrix was rechecked first. Each of the
eight selected actions then produced exactly 11 ordered tokens.

Selection used no scientific or visual criterion. The deterministic rule was
the earliest contiguous valid eight-pair window. Package rows, source PNG
indices, model-frame indices, server ticks, client ticks, and action indices
were all 0 through 7. No earlier candidate existed to reject.

The conservative position budget is:

`8 * 347 + 1 * 336 = 3112`

This is below the pinned maximum of 5552.

## Designated external bundle

Preparation root:

`C:\Users\lollo\MineOcclude-Certification-Inputs\phase3\person-a-phase3-input-c6a-9410-final`

Bounded package:

- size: 46,428 bytes
- SHA-256:
  `6ef6be2076670924654db8cc3f9d6cd3390452f2f35819741d8902a6c128073d`

Bounded MP4:

- size: 163,871 bytes
- SHA-256:
  `833db269b955efaec2446969cfe3e37223dbca1b4c72cb554ba41c51a2d380f9`
- codec: lossless `libx264rgb` / H.264
- decoded format: `gbrp`
- dimensions: 640 by 360
- rate: 20/1
- declared frames: 8
- decoded frames: 8
- duration: 0.4 seconds

The encoder used one thread, CRF 0, bit-exact flags, fixed creation metadata,
and no interpolation. Every decoded BGR frame was byte-compared with the
corresponding selected PNG.

The complete exact command, executable paths, tool versions, source hashes,
selection identities, action identities, validation results, and AWS upload
list are in the external `preparation_manifest.json`.

## Determinism and negative checks

A second complete preparation was written to:

`C:\Users\lollo\MineOcclude-Certification-Inputs\phase3\person-a-phase3-input-c6a-9410-final-repeat`

The derivative package and MP4 were byte-identical to the designated bundle.
Selected identities, actions, metadata, and negative-check results were also
identical.

Temporary external corruptions were all rejected:

- altered selected PNG:
  `selected_frame_provenance_mismatch`
- altered bounded MP4:
  `bounded_media_hash_mismatch`
- frame/action cardinality mismatch:
  `bounded_package_rejected`
- unverified impulse:
  `bounded_package_rejected`
- raw-action mutation:
  `action_conversion_record_mismatch`

## Remaining AWS-only inputs

The later certification still requires:

- a fresh AWS environment report;
- a new immutable AWS session ID;
- observed AWS MineWorld source, asset, and evidence roots;
- the final committed preparation-tool revision after review.

The prepared bundle is upload-ready input only. Phase 3 real-runtime
certification remains pending.
