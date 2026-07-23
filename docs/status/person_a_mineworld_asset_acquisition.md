# Person A Phase 2.3–2.4 — MineWorld Asset Acquisition and Hash Verification

Status: **COMPLETE**

## Purpose

Download and verify the exact external MineWorld runtime assets required for the first official runtime gate.

## Source

ModelScope repository:

`AI-ModelScope/mineworld`

Pinned ModelScope revision:

`0dd5561ab317115831badc50e09a6ebe98693d0e`

Local asset root:

`C:\Users\lollo\MineWorld-Assets-Pinned`

## Required files

### 1. 700M checkpoint

Path:

`C:\Users\lollo\MineWorld-Assets-Pinned\checkpoints\700M_16f.ckpt`

Size:

`3798736924 bytes`

SHA-256:

`A92C311BAF49BBF31338DA2CAAADC9E4F947B94DF8ABCF75DA350C4AE41319C5`

### 2. VAE config

Path:

`C:\Users\lollo\MineWorld-Assets-Pinned\checkpoints\vae\config.json`

Size:

`805 bytes`

SHA-256:

`32CA759D5B90F0C5AA5DF0E312A81E03DD4D3AF68896863C88F910D19F2526CB`

### 3. VAE checkpoint

Path:

`C:\Users\lollo\MineWorld-Assets-Pinned\checkpoints\vae\vae.ckpt`

Size:

`1657555486 bytes`

SHA-256:

`370D06BE427E034476B6B95BA0080A4B48266E876C4776A757B944B87B87D9AB`

### 4. Paired sample video

Path:

`C:\Users\lollo\MineWorld-Assets-Pinned\gradio_scene\scene.mp4`

Size:

`124782221 bytes`

SHA-256:

`B546E7657505004223742E2174E01D0B6A19091DE7EE39A2F213BCF003C243DE`

### 5. Paired sample actions

Path:

`C:\Users\lollo\MineWorld-Assets-Pinned\gradio_scene\scene.jsonl`

Size:

`15326380 bytes`

SHA-256:

`0029DAF06496BB974305431A20E8C9D419791F362098BF9D57EE8B8E0F036F9B`

## Download revision

The required files were downloaded from:

`AI-ModelScope/mineworld`

at exact revision:

`0dd5561ab317115831badc50e09a6ebe98693d0e`

## Verification date

`2026-07-23 16:50:43 -04:00`

## Verification result

All five required runtime files exist at the expected locations.

Observed sizes are:

- 700M checkpoint: `3798736924 bytes`
- VAE config: `805 bytes`
- VAE checkpoint: `1657555486 bytes`
- scene.mp4: `124782221 bytes`
- scene.jsonl: `15326380 bytes`

The files are full-sized binary/data assets and are not tiny Git-LFS pointer files or obvious HTML error payloads.

Exact SHA-256 identities have been recorded above.

## Source-control rule

These assets remain outside normal MineOcclude Git history.

Later runtime records must reference these exact paths and hashes unless a new asset revision is explicitly reviewed and approved.

## Pass check

- Exact pinned ModelScope revision downloaded: PASS
- All required files present: PASS
- Expected directory structure preserved: PASS
- File sizes recorded: PASS
- SHA-256 hashes recorded: PASS
- No required asset is a tiny pointer file: PASS

## Phase classification

- Phase 2.3: **COMPLETE**
- Phase 2.4: **COMPLETE**
