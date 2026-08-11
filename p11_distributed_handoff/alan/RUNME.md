# P11 shard handoff: ALAN

Frozen identity: 9 whole seeds / 36 jobs; shard SHA `ac156edfacf29824061de28c103d77f61d3402216fa473da5dfd795303986f96`. Never edit this manifest or its seed list.

Obtain `NEW_OPERATIONAL_HANDOFF_COMMIT` from `P11_DISTRIBUTED_OPERATIONAL_CLOSURE_RECEIPT`, then execute the bootstrap script from that exact owner-delivered commit:

```bash
export P11_OPERATIONAL_HANDOFF_COMMIT=NEW_OPERATIONAL_HANDOFF_COMMIT
export P11_WORKER_HOME="$HOME/mineocclude-p11-alan"
python3 /path/to/exact-commit/scripts/bootstrap_large_scale_no_wall_p11_worker.py \
  --repository-url https://github.com/atharv-santosh/MineOcclude.git \
  --destination "$P11_WORKER_HOME" \
  --operational-handoff-commit "$P11_OPERATIONAL_HANDOFF_COMMIT" \
  --worker alan
export P11_OPERATIONAL_ROOT="$P11_WORKER_HOME/operational"
export P11_SCIENTIFIC_ROOT="$P11_WORKER_HOME/scientific"
cd "$P11_OPERATIONAL_ROOT"
```

Use `p11_distributed_handoff/README.md` for the tested preflight, input/cache acquisition, future launch, full-loss recovery, whole-shard takeover, status, validation, and durable return commands. In every shard command use:

```text
--scientific-root "$P11_SCIENTIFIC_ROOT"
--shard-manifest p11_distributed_handoff/alan/shard_manifest.json
--common-authority p11_distributed_handoff/common_authority.json
```

Do not launch until the owner approves. Partial reassignment is unsupported; takeover always restores and resumes this same original ALAN shard.
