# Person A Phase 2.1 - Official Environment Evidence

**Status: PASS - Phase 2.1 complete**

**Qualification date:** 2026-07-24

## Objective

Reproduce and verify the pinned MineWorld software environment before introducing project-specific model changes.

Qualification used two environments:

1. A local Windows CPU environment for dependency reproduction, source inspection, and non-GPU development.
2. An AWS SageMaker NVIDIA GPU environment for final CUDA runtime qualification.

## Upstream basis

- Official upstream repository: `https://github.com/microsoft/mineworld.git`
- Pinned upstream revision: `9f49efbcc68a5f0cf60e78f0abc566eac409282f`
- Dependency source: pinned upstream `requirements.txt`
- Project branch qualified: `role/person-a-model`
- MineOcclude commit before this update:
  `9eb37bc97063e293e0321debca460ddc0b14706a`

## Required software versions

The validator checks:

- Python: `3.10`
- torch: base version `2.6.0`
- torchvision: base version `0.21.0`
- omegaconf: `2.3.0`
- transformers: `4.48.1`
- opencv-python: `4.11.0.86`
- attrs: `25.3.0`
- diffusers: `0.32.2`
- gradio: `5.24.0`
- einops: `0.8.1`
- scipy: `1.15.2`
- torch-fidelity: `0.3.0`
- gym3: `0.3.3`
- gym: `0.26.2`
- scikit-learn: `1.6.1`
- modelscope: `1.38.1`
- modelscope-hub: `0.1.8`

CUDA build suffixes such as `+cu126` are accepted only for `torch` and
`torchvision` when their pinned base versions match.

A run using `--require-cuda` still fails unless CUDA is actually available.

## Local CPU qualification

### Runtime

- Operating system: Windows AMD64
- Conda environment: `mineworld`
- Python: `3.10.20`
- Python executable:
  `C:\Users\lollo\miniconda3\envs\mineworld\python.exe`
- Python compiler: `MSC v.1942 64 bit (AMD64)`

### PyTorch stack

- torch: `2.6.0+cpu`
- torchvision: `0.21.0+cpu`
- CUDA available: `False`

### Result

The pinned dependencies imported successfully.

`python -m pip check` returned:

    No broken requirements found.

The local validator returned:

    PASS: Software environment validated. CUDA was not required for this run.

The local machine is qualified for:

- source and configuration inspection;
- interface tracing;
- contract and non-GPU tests;
- development that does not require MineWorld inference.

It is not the final target runtime because it has no NVIDIA CUDA device.

### Local evidence

- Environment export:
  `configs/environments/mineworld_local_cpu.yml`
- Pre-ModelScope package snapshot:
  `docs/status/person_a_phase2_packages_before_modelscope.txt`
- Post-ModelScope package snapshot:
  `docs/status/person_a_phase2_packages_after_modelscope.txt`
- Raw validation report:
  `docs/status/person_a_phase2_check_env_local.txt`

## AWS GPU qualification

### AWS runtime

- Service: AWS SageMaker AI JupyterLab
- Instance class: `ml.g6.xlarge`
- Conda environment: `mineworld`
- Python executable:
  `/home/sagemaker-user/.conda/envs/mineworld/bin/python`
- Python version: `3.10.20`
- Platform: Linux x86_64
- Runtime libc: glibc `2.39`

### Linux system libraries

The SageMaker image required these operating-system libraries for the official
`opencv-python` package:

- `libgl1`
- `libglib2.0-0t64`

The official `opencv-python==4.11.0.86` dependency was preserved. It was not
replaced with `opencv-python-headless`.

### CUDA PyTorch stack

- torch: `2.6.0+cu126`
- torchvision: `0.21.0+cu126`
- PyTorch compiled CUDA runtime: `12.6`
- CUDA available: `True`
- CUDA device count: `1`
- cuDNN version: `90501`

### GPU and driver

- GPU: NVIDIA L4
- GPU memory reported by PyTorch: `23661248512` bytes
- GPU memory reported by `nvidia-smi`: `23034 MiB`
- Compute capability: `8.9`
- NVIDIA driver: `595.71.05`

A real CUDA matrix multiplication completed successfully on `cuda:0`.

### Dependency integrity

Every required package:

- matched its exact pinned version or approved CUDA build version;
- imported successfully;
- remained inside the isolated `mineworld` environment.

ModelScope was installed without dependency resolution:

    modelscope==1.38.1
    modelscope-hub==0.1.8

The before-and-after package comparison showed only those two additions. The
CUDA PyTorch and torchvision installations did not change.

`python -m pip check` returned:

    No broken requirements found.

### Repository validator result

The final command was:

    python scripts/check_env.py --require-cuda

The result was:

    PASS: Official CUDA-capable environment validated.

The exit status was:

    0

### CUDA toolkit note

The final activated environment reported:

    nvcc: NOT FOUND

This is recorded as an environment fact and is not a Phase 2.1 blocker.

MineWorld currently uses the CUDA runtime libraries supplied by the pinned
PyTorch wheel. Phase 2.1 does not require compilation of a custom CUDA
extension.

CUDA availability, the NVIDIA driver, the L4 GPU, cuDNN, and real GPU tensor
computation were all verified.

Any future component that compiles custom CUDA code must reassess whether
`nvcc` is required.

### AWS evidence

- Environment export:
  `configs/environments/mineworld_aws_l4.yml`
- Raw validation report:
  `docs/status/person_a_phase2_check_env_aws_l4.txt`
- Environment validation implementation:
  `scripts/check_env.py`

The Conda export includes pip-installed packages under its `pip:` section.
Conda emitted an informational warning that it cannot independently guarantee
reproducibility for pip packages. The exact observed pip versions, including
CUDA component wheels, are still preserved in the export.

## Final acceptance classification

- Local dependency reproduction: **PASS**
- Local non-GPU environment validation: **PASS**
- AWS CUDA environment validation: **PASS**
- NVIDIA L4 detection: **PASS**
- Real CUDA computation: **PASS**
- Package import checks: **PASS**
- Dependency conflict check: **PASS**
- ModelScope installation isolation: **PASS**

# Phase 2.1 final result: PASS

The official MineWorld software environment has been reproduced and qualified
on the approved AWS NVIDIA runtime. Person A may proceed to the model and asset
runtime steps that depend on this environment.
