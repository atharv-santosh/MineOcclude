# Person A Phase 2.1 — official environment evidence

Status: PARTIAL PASS (local CPU environment verified; GPU runtime still pending)

Date: 2026-07-23

## Objective

Reproduce the pinned official MineWorld software environment before introducing project-only changes.

## Environment

- Conda environment name: `mineworld`
- Python version: `3.10.20`
- Environment python path: `C:\Users\lollo\miniconda3\envs\mineworld\python.exe`

## Upstream requirements source

- Upstream checkout: `C:\Users\lollo\MineWorld-Upstream`
- Requirements file: `requirements.txt`
- Pinned upstream revision already recorded separately: `9f49efbcc68a5f0cf60e78f0abc566eac409282f`

## Installed pinned packages verified

- torch: `2.6.0+cpu`
- torchvision: `0.21.0+cpu`
- transformers: `4.48.1`
- diffusers: `0.32.2`
- gradio: `5.24.0`
- omegaconf: import passed
- opencv-python / cv2: import passed
- einops: import passed
- scipy: import passed
- scikit-learn: import passed

## Integrity checks

- `python -m pip check` result: `No broken requirements found.`
- Import verification: PASSED

## CUDA / compute status

- `torch.cuda.is_available()`: `False`
- This laptop does not provide the intended CUDA runtime.
- Therefore this step is only a local software-environment verification, not the final GPU runtime qualification.

## Interpretation

Local MineWorld dependency reproduction is successful and usable for:
- source reading,
- interface tracing,
- configuration inspection,
- non-GPU checks.

Local machine is not sufficient for:
- final official GPU smoke test,
- teacher-forced GPU runtime verification,
- memory/capacity measurement for the target 700M runtime.

## Remaining blocker to fully close A2.1

A CUDA-capable runtime must still be recorded on AWS or another approved NVIDIA machine, including:
- CUDA availability,
- GPU model,
- driver/runtime details,
- successful imports in that environment.

## Pass classification

- Local software environment reproduction: PASS
- Final target-runtime qualification: PENDING

---

## Local environment qualification update

The local non-GPU portion of Phase 2.1 has now been completed and machine-checked.

### Official local environment

- Conda environment: `mineworld`
- Python: `3.10.20`
- Python executable: `C:\Users\lollo\miniconda3\envs\mineworld\python.exe`
- Platform: Windows AMD64
- Python compiler: `MSC v.1942 64 bit (AMD64)`

### MineWorld dependency verification

The pinned MineWorld dependency set imports successfully and `pip check` reports:

`No broken requirements found.`

Verified key versions include:

- torch: `2.6.0+cpu`
- torchvision: `0.21.0+cpu`
- transformers: `4.48.1`
- diffusers: `0.32.2`
- gradio: `5.24.0`

### ModelScope client

The official `mineworld` environment now contains:

- modelscope: `1.38.1`
- modelscope-hub: `0.1.8`

The package state was captured before and after installation.

The only observed additions were:

- `modelscope==1.38.1`
- `modelscope-hub==0.1.8`

The pinned MineWorld model stack did not change.

The ModelScope download client import succeeded:

`from modelscope.hub.snapshot_download import snapshot_download`

### Saved environment evidence

Environment export:

`configs/environments/mineworld_local_cpu.yml`

Pre-ModelScope package snapshot:

`docs/status/person_a_phase2_packages_before_modelscope.txt`

Post-ModelScope package snapshot:

`docs/status/person_a_phase2_packages_after_modelscope.txt`

Environment validation script:

`scripts/check_env.py`

Raw local validation report:

`docs/status/person_a_phase2_check_env_local.txt`

### Local check-env result

The local environment checker completed with:

`PASS: Software environment validated. CUDA was not required for this run.`

The checker recorded:

- operating system
- architecture
- processor information
- Python executable and version
- Python compiler/runtime information
- Conda environment
- expected and observed package versions
- dependency imports
- `pip check`
- PyTorch build
- CUDA availability
- CUDA device count
- cuDNN availability
- NVIDIA driver availability
- CUDA toolkit availability
- compiler command availability

### GPU qualification status

The current laptop does not provide the intended NVIDIA CUDA runtime.

This is expected and is not treated as a local environment failure.

Final Phase 2.1 acceptance remains pending until the same environment-validation procedure is run on the official AWS GPU machine with:

`python scripts/check_env.py --require-cuda`

That AWS run must record and verify:

- CUDA-enabled PyTorch
- CUDA runtime version
- NVIDIA GPU identity
- GPU memory
- NVIDIA driver version
- CUDA device count
- CUDA availability
- relevant AWS OS/runtime details

### Current Phase 2.1 classification

**LOCAL NON-GPU REQUIREMENTS: PASS**

**FINAL AWS GPU QUALIFICATION: PENDING**

Phase 2.1 is therefore not yet globally complete, but no remaining local blocker prevents proceeding with AWS setup.
