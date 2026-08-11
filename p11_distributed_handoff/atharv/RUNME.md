# P11 shard handoff: ATHARV

Frozen identity: 9 whole seeds / 36 jobs; shard SHA `c22f1f68a4f02ab70b2df04b9b4eb2daa9b3a2196ac86fa712addcd90a9be2f7`. Never edit this manifest or its seed list.

Obtain `NEW_OPERATIONAL_HANDOFF_COMMIT` from `P11_DISTRIBUTED_OPERATIONAL_CLOSURE_RECEIPT`, then run `scripts/bootstrap_large_scale_no_wall_p11_worker.py` from that exact owner-delivered commit with `--worker atharv`, repository URL `https://github.com/atharv-santosh/MineOcclude.git`, and a new destination such as `$HOME/mineocclude-p11-atharv`.

Export `P11_OPERATIONAL_ROOT=<destination>/operational` and `P11_SCIENTIFIC_ROOT=<destination>/scientific`, change to the operational root, and follow every tested command in `p11_distributed_handoff/README.md`. In every shard command use:

```text
--scientific-root "$P11_SCIENTIFIC_ROOT"
--shard-manifest p11_distributed_handoff/atharv/shard_manifest.json
--common-authority p11_distributed_handoff/common_authority.json
```

Do not launch until the owner approves. Partial reassignment is unsupported; takeover always restores and resumes this same original ATHARV shard.
