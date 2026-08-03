# Person A Phase 2.6 - Official Free-Generation Smoke Test

**Status: PASS**

**Date:** 2026-07-24

## Objective

Verify that the pinned MineWorld 700M model can load on the approved AWS GPU
runtime and complete one end-to-end free-generation step.

## Runtime

- Service: AWS SageMaker AI JupyterLab
- Instance: `ml.g6.xlarge`
- GPU: NVIDIA L4
- Conda environment: `mineworld`
- Python: `3.10.20`
- torch: `2.6.0+cu126`
- CUDA available: `True`

## Pinned inputs

- MineWorld source revision:
  `9f49efbcc68a5f0cf60e78f0abc566eac409282f`
- ModelScope asset revision:
  `0dd5561ab317115831badc50e09a6ebe98693d0e`
- Main checkpoint:
  `/home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/700M_16f.ckpt`
- VAE configuration:
  `/home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/vae/config.json`
- VAE checkpoint:
  `/home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/vae/vae.ckpt`
- Paired sample video:
  `/home/sagemaker-user/MineWorld-Assets-Pinned/gradio_scene/scene.mp4`
- Paired sample actions:
  `/home/sagemaker-user/MineWorld-Assets-Pinned/gradio_scene/scene.jsonl`
- Model configuration:
  `/home/sagemaker-user/MineWorld-Upstream/configs/700M_16f.yaml`

## Launch command

    python -u mineworld.py \
      --scene /home/sagemaker-user/MineWorld-Assets-Pinned/gradio_scene/scene.mp4 \
      --model_ckpt /home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/700M_16f.ckpt \
      --config /home/sagemaker-user/MineWorld-Upstream/configs/700M_16f.yaml \
      --reference_frame 8 \
      --window_size 4

## Startup observations

- The VAE configuration and checkpoint loaded.
- The VAE loader reported `0 missing` and `1250 unexpected keys`.
- The Gradio application started successfully on port `7861`.
- The temporary public Gradio interface opened successfully.
- The source-frame context was displayed.

The unexpected-key count is preserved as a runtime observation. It did not
prevent model startup, context initialization, or successful frame generation.
It should be considered during later loaded-architecture inspection rather
than silently ignored.

## Manual generation procedure

1. The `forward` action was selected.
2. Repeat count remained `1`.
3. Camera X remained `0`.
4. Camera Y remained `0`.
5. The `Run` button was clicked once.
6. Processing completed.
7. A new Minecraft image appeared in the `last generated frame` panel.
8. The generated view appeared farther forward than the preceding context.
9. No visible runtime or Gradio error appeared.

## Nonblocking runtime warnings

The runtime emitted two PyTorch performance advisories after generation began:

- the GPU did not have enough streaming multiprocessors for
  `max_autotune_gemm` mode;
- TensorFloat32 acceleration was available but was not enabled.

These were warnings rather than exceptions. They did not prevent model
startup, action processing, or visible frame generation. No runtime setting
was changed during this reproduction smoke test.

## Pass interpretation

This smoke test verifies that the pinned runtime can:

- instantiate the MineWorld model and VAE;
- load the pinned checkpoint assets;
- initialize context from the paired sample;
- accept an action input;
- generate image tokens on the NVIDIA GPU;
- decode the generated tokens into a visible Minecraft frame;
- return the result through the official Gradio interface.

This is an operational smoke test. It does not by itself establish:

- generation quality;
- long-horizon stability;
- action fidelity beyond the observed single step;
- activation-hook correctness;
- teacher-forced indexing correctness;
- scientific validity of the later occlusion experiment.

## Evidence

Sanitized console log:

`docs/status/person_a_phase2_free_generation_smoke_aws_l4.txt`

The temporary Gradio share URL was redacted before placing the console log in
Git. All other runtime output was preserved.

# Phase 2.6 final result: PASS
