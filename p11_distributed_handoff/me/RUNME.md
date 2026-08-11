# P11 shard handoff: ME

This shard is frozen to 10 whole seeds / 40 jobs. Do not edit the manifests. Do not share AWS or SSH credentials. Authenticate with your own authorized environment.

## 1. Repository

```bash
git fetch origin exploration/large-scale-no-wall-scaling-best-k-v0-1
git checkout exploration/large-scale-no-wall-scaling-best-k-v0-1
git pull --ff-only origin exploration/large-scale-no-wall-scaling-best-k-v0-1
test "$(git rev-parse HEAD)" = "173a3ca3e92ffe771d19911c15c006dba6acc934"
git status --short --branch
```

## 2. Install the small authority bundle

From the repository root after receiving the handoff directory:

```bash
cp p11_distributed_handoff/authority_bundle/* docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1/
sha256sum -c p11_distributed_handoff/authority_bundle.sha256
```

## 3. Environment preflight

```bash
/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/run_large_scale_no_wall_p11_shard.py --shard-manifest p11_distributed_handoff/me/shard_manifest.json --common-authority p11_distributed_handoff/common_authority.json --environment-preflight
```

Requires the qualified `mineworld` Python, CUDA, one comparable GPU, and at least 24 GB free under `/mnt/sagemaker-nvme`.

## 4. Acquire only P6 activations

```bash
/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/run_large_scale_no_wall_p11_shard.py --acquire-inputs
```

This is 9968056320 bytes of immutable scientific input. It replaces raw captures, Minecraft/MineWorld, and P8/P9/P10 recomputation. If your AWS identity cannot read it, request the same immutable prefix through an approved shared location; never request credentials.

## 5. Reconstruct cheap caches and verify hashes

```bash
/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/run_large_scale_no_wall_p11_shard.py --reconstruct-caches
```

Expected token cache: `2cf40e7ad1f0fe5269b16c0d7e03ff486e3ffa00379f8acea5145829bff6cf90` (8422686848 bytes). Expected COARSE cache: `4a1c9562a26416eb6b069baeeb9f1c73513f7306f30a7cfe54dd30efe7094bdf` (707788928 bytes).

## 6. Validate the frozen shard

```bash
/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/run_large_scale_no_wall_p11_shard.py --shard-manifest p11_distributed_handoff/me/shard_manifest.json --common-authority p11_distributed_handoff/common_authority.json --validate-shard
```

## 7. Future detached launch (do not run until the owner approves)

```bash
nohup setsid /home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/run_large_scale_no_wall_p11_shard.py --shard-manifest p11_distributed_handoff/me/shard_manifest.json --common-authority p11_distributed_handoff/common_authority.json --run --resume </dev/null >$HOME/mineocclude_p11_shard_me.log 2>&1 &
```

## 8. Read-only status/watchdog

```bash
watch -n 600 '/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/run_large_scale_no_wall_p11_shard.py --shard-manifest p11_distributed_handoff/me/shard_manifest.json --common-authority p11_distributed_handoff/common_authority.json --status'
```

## 9. Completion validation

```bash
/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/run_large_scale_no_wall_p11_shard.py --shard-manifest p11_distributed_handoff/me/shard_manifest.json --common-authority p11_distributed_handoff/common_authority.json --validate-complete
```

This hard-requires 10/10 seeds, 40/40 jobs, and zero missing, duplicate, blocked, retryable, or running jobs.

## 10. Durable package/upload

```bash
/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/run_large_scale_no_wall_p11_shard.py --shard-manifest p11_distributed_handoff/me/shard_manifest.json --common-authority p11_distributed_handoff/common_authority.json --package-upload
```

Return the small `p11_shard_me_return.tar.gz`, `package_upload_receipt.json`, shard manifest/SHA, and the durable S3 URI to the owner. Do not return P6 activations or reconstructable token/COARSE caches.
