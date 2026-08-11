# Frozen P11 five-worker handoff

No distributed shard has been launched. P11 is paused after exact frozen seed index 2: 3/49 seeds and 12/196 jobs are independently validated and durable. The remaining original seed indices 3–48 are assigned whole-seed-only by frozen round-robin order.

All workers must use branch `exploration/large-scale-no-wall-scaling-best-k-v0-1` at commit `173a3ca3e92ffe771d19911c15c006dba6acc934`. Each person follows their own `RUNME.md`; the procedures are identical apart from the signed manifest, mutable local paths, log, and durable S3 prefix.

## Shared scientific inputs

Each worker receives this small handoff plus exactly 240 protected P6 activation arrays (`9,968,056,320` bytes). The runner downloads only those arrays and verifies every SHA-256. It then reconstructs the token cache (`8,422,686,848` bytes, SHA `2cf40e7ad1f0fe5269b16c0d7e03ff486e3ffa00379f8acea5145829bff6cf90`) and COARSE cache (`707,788,928` bytes, SHA `4a1c9562a26416eb6b069baeeb9f1c73513f7306f30a7cfe54dd30efe7094bdf`) locally. Reserve at least `23,098,532,096` bytes; the preflight requires 24 GB free NVMe.

Raw Minecraft captures, Minecraft/MineWorld runtime, new extraction, and P8/P9/P10 recomputation are neither needed nor authorized. Never copy AWS keys, session tokens, `.aws/credentials`, passwords, or SSH private keys. Each worker uses their own authorized AWS identity. If direct access is unavailable, transfer the same immutable 240-array set through an approved shared location.

## Return authority

Each worker returns only their `p11_shard_<name>_return.tar.gz`, `package_upload_receipt.json`, immutable shard manifest/SHA, and durable URI. Do not return the P6 arrays or reconstructable caches.

## Final merge hard gate

After extracting the five returned packages into isolated roots, the owner runs:

```bash
/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/validate_large_scale_no_wall_p11_merge.py \
  --common-authority /home/sagemaker-user/MineOcclude/p11_distributed_handoff/common_authority.json \
  --sequential-result-root /mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/p11_prospective_derangement_null_v0_1 \
  --shard-result me=/mnt/sagemaker-nvme/p11_merge_inputs/me \
  --shard-result alan=/mnt/sagemaker-nvme/p11_merge_inputs/alan \
  --shard-result atharv=/mnt/sagemaker-nvme/p11_merge_inputs/atharv \
  --shard-result ayman=/mnt/sagemaker-nvme/p11_merge_inputs/ayman \
  --shard-result sahil=/mnt/sagemaker-nvme/p11_merge_inputs/sahil \
  --validate-only
```

The validator hard-fails before aggregation unless all exact original 49 seeds / 196 jobs are present once, with four representations per seed, matching parent/study/P5/P6/P7/P10/fold/test/grid/null authority and BEST-K training-only provenance. It does not aggregate or calculate the final p-value.
