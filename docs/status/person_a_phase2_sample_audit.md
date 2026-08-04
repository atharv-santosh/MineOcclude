# Person A Phase 2.5 — MineWorld Paired Sample Audit

Status: **COMPLETE**

## Purpose

Audit the official paired MineWorld sample before using it for runtime and model-input validation.

The paired sample consists of:

- `gradio_scene/scene.mp4`
- `gradio_scene/scene.jsonl`

Both files were acquired from the pinned ModelScope asset revision:

`0dd5561ab317115831badc50e09a6ebe98693d0e`

## Video audit

Input:

`C:\Users\lollo\MineWorld-Assets-Pinned\gradio_scene\scene.mp4`

Verified with `ffprobe`.

Observed metadata:

- Width: `640`
- Height: `360`
- Reported frame rate: `20/1`
- Average frame rate: `20/1`
- Time base: `1/10240`
- Start time: `0.000000`
- Encoded duration: `207.600000 seconds`
- Declared frame count: `4152`
- Decoded/read frame count: `4152`

### Video result

PASS.

The sample has the expected source resolution of `640 x 360`, the expected encoded frame rate of `20 FPS`, and exactly `4152` decodable frames.

## JSONL audit

Input:

`C:\Users\lollo\MineWorld-Assets-Pinned\gradio_scene\scene.jsonl`

Observed:

- JSONL rows: `4152`
- Invalid JSON rows: `0`

First record:

- `tick = 0`
- `serverTick = 6003`
- `milli = 1638048922210`

Last record:

- `tick = 5999`
- `serverTick = 12003`
- `milli = 1638049241367`

The records contain the expected raw MineWorld capture fields, including:

- mouse state
- keyboard state
- GUI state
- hotbar state
- yaw and pitch
- player position
- tick
- millisecond timestamp
- inventory
- server tick
- server tick duration
- statistics

### JSONL result

PASS.

All `4152` rows are valid JSON records.

## Pairing cardinality

Video frames:

`4152`

JSONL rows:

`4152`

Cardinality:

`1:1`

The official MineWorld source code uses same-index access for the corresponding video frame and JSON record.

For this sample, the accepted basic pairing rule is therefore:

`video frame index i <-> JSONL row index i`

### Pairing result

PASS.

No cardinality mismatch was found.

## Timing and tick diagnostics

The timing fields were audited across all adjacent JSONL rows.

### Tick progression

- Number of adjacent transitions: `4151`
- Minimum tick delta: `1`
- Maximum tick delta: `286`
- Average tick delta: approximately `1.44519`
- Tick delta less than or equal to zero: `0`
- Tick delta greater than 1: `76`

### Server-tick progression

- Number of adjacent transitions: `4151`
- Minimum server-tick delta: `1`
- Maximum server-tick delta: `286`
- Average server-tick delta: approximately `1.44543`
- Server-tick delta less than or equal to zero: `0`
- Server-tick delta greater than 1: `76`

### Millisecond timestamp progression

- Number of adjacent transitions: `4151`
- Minimum delta: `41 ms`
- Maximum delta: `14361 ms`
- Average delta: approximately `76.8868 ms`
- Delta less than or equal to zero: `0`
- Delta greater than `100 ms`: `50`
- Delta greater than `250 ms`: `34`
- Delta greater than `1000 ms`: `25`

Raw first-to-last millisecond span:

`319.157 seconds`

Encoded video duration:

`207.600 seconds`

## Largest observed timing gaps

| Frame index | Tick delta | Server-tick delta | Millisecond delta |
|---:|---:|---:|---:|
| 4035 | 286 | 286 | 14361 |
| 3021 | 219 | 219 | 11154 |
| 1523 | 184 | 184 | 9225 |
| 3267 | 103 | 103 | 5219 |
| 1581 | 98 | 98 | 4921 |
| 1268 | 68 | 68 | 4088 |
| 2882 | 79 | 79 | 3957 |
| 1934 | 74 | 74 | 3757 |
| 2961 | 72 | 72 | 3656 |
| 3814 | 72 | 72 | 3606 |
| 1199 | 64 | 64 | 3226 |
| 771 | 60 | 60 | 3059 |
| 2843 | 53 | 53 | 2958 |
| 2848 | 44 | 44 | 2395 |
| 3028 | 32 | 32 | 1696 |

## Interpretation

The paired sample is valid for same-index frame/JSON pairing, but its raw timing stream is not perfectly continuous.

There are no duplicated, backward, or non-monotonic tick/timestamp transitions.

However, there are `76` tick discontinuities where more than one game tick elapsed between adjacent recorded sample rows.

These discontinuities correspond to timestamp gaps and explain why the raw first-to-last millisecond span is longer than the encoded video duration.

Therefore:

1. Do not infer scientific identity from wall-clock timing alone.
2. Do not assume every adjacent encoded frame represents exactly `50 ms` of uninterrupted game time.
3. Preserve frame index as the exact paired-media index.
4. Preserve `serverTick` and other timing fields as provenance for later alignment and diagnostic work.
5. Do not silently interpolate, remove, or renumber the observed timing gaps.
6. Any later MineOcclude trajectory conversion must follow the project's frozen identity and trajectory contracts rather than deriving identity from filenames or row order alone.

## Pass check

- Video opens and decodes: PASS
- Resolution is `640 x 360`: PASS
- Encoded frame rate is `20 FPS`: PASS
- Video frame count is `4152`: PASS
- JSONL row count is `4152`: PASS
- JSONL parse failures: `0`: PASS
- Frame/row cardinality is exactly `1:1`: PASS
- Tick progression is monotonic: PASS
- Server-tick progression is monotonic: PASS
- Millisecond progression is monotonic: PASS
- Timing discontinuities identified and recorded: PASS

## Phase 2.5 classification

**COMPLETE**

The official paired sample has been audited and is suitable to proceed to the official GPU runtime smoke tests, provided the recorded timing discontinuities are preserved as provenance and are not silently interpreted as continuous 20 Hz wall-clock sampling.
