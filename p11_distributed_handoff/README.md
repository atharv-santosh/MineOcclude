# Frozen P11 distributed operational closure

No distributed shard has been launched. P11 remains paused after original seed indices `0,1,2`: 3/49 seeds and 12/196 jobs are independently validated and durable. The original seed indices `3..48` remain assigned whole-seed-only by the frozen round-robin manifests.

## Immutable authorities and checkout boundary

- Scientific implementation: `173a3ca3e92ffe771d19911c15c006dba6acc934`.
- Original immutable handoff: `c701eef7ef4042802c489748fb3f1c532d322cf2`.
- Parent P11 manifest: `634720967cd8e23b2e9f0994981150768123018ef08a8f76ee9d8433f8886f87`.
- Operational closure tooling: the exact `NEW_OPERATIONAL_HANDOFF_COMMIT` recorded in `P11_DISTRIBUTED_OPERATIONAL_CLOSURE_RECEIPT`.

The `173a3ca3..c701eef` Git range adds only `p11_distributed_handoff/`; it changes no scientific code. The old single-checkout guide was impossible because pulling the handoff produced HEAD `c701eef`, while every frozen shard manifest and `environment_preflight()` require the named branch at exact HEAD `173a3ca3`.

The tested deployment model uses two checkouts. A detached operational checkout at the exact closure commit supplies commands and handoff files. A separate scientific worktree stays on branch `exploration/large-scale-no-wall-scaling-best-k-v0-1` at exact HEAD `173a3ca3`. Bootstrap verifies that the common authority, all original shard manifests, and the authority bundle are byte-identical to `c701eef`; no moving branch HEAD is used.

Each worker runs the fresh bootstrap and exact commands in their own `RUNME.md`. The scientific preflight intentionally retains the exact branch/HEAD requirements; it also proves checkout separation and immutable handoff bytes.

## Durable recovery and takeover

Every durable control snapshot binds worker, shard SHA, parent manifest SHA, durable prefix, exact control-file sizes/hashes, and validated job-result hashes. The snapshot is published only after each validated job directory. Full-loss restore downloads into a new staging root, rejects foreign or missing job keys, validates the complete ledger transition history and exact job identities, verifies the control receipt is unchanged throughout restoration, revalidates every restored result with frozen science, then atomically installs the original shard root. `--run --resume` skips those validated jobs and executes only unfinished original jobs.

The only supported takeover is whole-shard takeover. The original process must be proven stopped in an operator attestation. The replacement restores the same durable state and runs the same frozen shard manifest with `--resume`. The human may change; worker identity, shard SHA, durable prefix, job identities, and seed ownership may not. Partial-reassignment manifests and manual seed-list edits are unsupported.

## Owner collection

From the operational checkout, with the separate frozen scientific root installed by bootstrap:

```bash
export P11_OPERATIONAL_ROOT=/path/to/p11-owner/operational
export P11_SCIENTIFIC_ROOT=/path/to/p11-owner/scientific
cd "$P11_OPERATIONAL_ROOT"
/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/collect_large_scale_no_wall_p11_returns.py \
  --scientific-root "$P11_SCIENTIFIC_ROOT" \
  --common-authority p11_distributed_handoff/common_authority.json \
  --output-root /mnt/sagemaker-nvme/p11_merge_inputs
```

The collector reads each durable `package_upload_receipt.json`, validates worker/shard/parent/prefix plus package size/SHA, downloads the fixed package name, safely extracts without links/devices/traversal/duplicate members, revalidates all exact jobs, rejects cross-worker duplicates or foreign jobs, and creates exactly these five isolated directories:

```text
/mnt/sagemaker-nvme/p11_merge_inputs/me
/mnt/sagemaker-nvme/p11_merge_inputs/alan
/mnt/sagemaker-nvme/p11_merge_inputs/atharv
/mnt/sagemaker-nvme/p11_merge_inputs/ayman
/mnt/sagemaker-nvme/p11_merge_inputs/sahil
```

## Five-root gate and canonical aggregation

Validation only:

```bash
/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/validate_large_scale_no_wall_p11_merge.py \
  --scientific-root "$P11_SCIENTIFIC_ROOT" \
  --common-authority p11_distributed_handoff/common_authority.json \
  --sequential-result-root /mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/p11_prospective_derangement_null_v0_1 \
  --shard-result me=/mnt/sagemaker-nvme/p11_merge_inputs/me \
  --shard-result alan=/mnt/sagemaker-nvme/p11_merge_inputs/alan \
  --shard-result atharv=/mnt/sagemaker-nvme/p11_merge_inputs/atharv \
  --shard-result ayman=/mnt/sagemaker-nvme/p11_merge_inputs/ayman \
  --shard-result sahil=/mnt/sagemaker-nvme/p11_merge_inputs/sahil \
  --validate-only
```

Canonical aggregation repeats that exact hard gate internally before writing anything. It then delegates to the frozen `build_result()` implementation, preserving `B=49` and `p=(1+count(null>=observed))/50`, creates a deterministic canonical package and receipt, and uploads both to the explicit durable URI:

```bash
/home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/validate_large_scale_no_wall_p11_merge.py \
  --scientific-root "$P11_SCIENTIFIC_ROOT" \
  --common-authority p11_distributed_handoff/common_authority.json \
  --sequential-result-root /mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/p11_prospective_derangement_null_v0_1 \
  --shard-result me=/mnt/sagemaker-nvme/p11_merge_inputs/me \
  --shard-result alan=/mnt/sagemaker-nvme/p11_merge_inputs/alan \
  --shard-result atharv=/mnt/sagemaker-nvme/p11_merge_inputs/atharv \
  --shard-result ayman=/mnt/sagemaker-nvme/p11_merge_inputs/ayman \
  --shard-result sahil=/mnt/sagemaker-nvme/p11_merge_inputs/sahil \
  --aggregate \
  --output-root /mnt/sagemaker-nvme/p11_canonical_distributed_aggregation \
  --durable-output-uri s3://sagemaker-us-east-1-323206973672/mineocclude/exploratory_large_scale_no_wall_scaling_best_k_v0_1/p11_prospective_derangement_null_v0_1/canonical_distributed_aggregation_v0_1/
```

The aggregation command hard-requires 49/49 original seeds, 196/196 original jobs, four representations per seed, and zero missing, extra/foreign, duplicate, or partial state. This operational closure does not interpret the scientific result.
