# P11 shard handoff: SAHIL

Frozen identity: 9 whole seeds / 36 jobs; shard SHA `5c96edc249a064c6f07e0f430f31a748c1c641cc58e0960e282960e5a42983fb`. Never edit this manifest or its seed list.

Obtain `NEW_OPERATIONAL_HANDOFF_COMMIT` from `P11_DISTRIBUTED_OPERATIONAL_CLOSURE_RECEIPT`, then run `scripts/bootstrap_large_scale_no_wall_p11_worker.py` from that exact owner-delivered commit with `--worker sahil`, repository URL `https://github.com/atharv-santosh/MineOcclude.git`, and a new destination such as `$HOME/mineocclude-p11-sahil`.

Export `P11_OPERATIONAL_ROOT=<destination>/operational` and `P11_SCIENTIFIC_ROOT=<destination>/scientific`, change to the operational root, and follow every tested command in `p11_distributed_handoff/README.md`. In every shard command use:

```text
--scientific-root "$P11_SCIENTIFIC_ROOT"
--shard-manifest p11_distributed_handoff/sahil/shard_manifest.json
--common-authority p11_distributed_handoff/common_authority.json
```

Do not launch until the owner approves. Partial reassignment is unsupported; takeover always restores and resumes this same original SAHIL shard.
