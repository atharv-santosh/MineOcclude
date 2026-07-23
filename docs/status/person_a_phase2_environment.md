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
