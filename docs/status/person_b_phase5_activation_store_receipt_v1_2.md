# Person B Phase 5 activation-store acceptance receipt v1.2

## Verdict

**PASS.** Person B independently accepted the coordinated synthetic activation-store handoff package v1.2 at Person A package revision `b6d4304adb0f82c1722342795133dde4aa59ea7f`. No migration is required, and no private assistance was used.

This receipt covers deterministic engineering compatibility only. Every payload is marked `synthetic_non_scientific`; no scientific inference follows from this acceptance.

## What Person B received

The checked package is `docs/status/fixtures/phase5_activation_store_handoff_v1_2/`. It contains exactly eight approved files: its README, non-self checksum inventory, handoff manifest, accepted-manifest rows, one production `.npy` activation chunk, one canonical activation index, one immutable run binding, and one synthetic oracle-target document.

The package is bound to:

- schema version `1.0`;
- accepted-manifest hash `26d58a19619de38452c96832a44361cdebc240436e23c15fca4432f8e2be4757`;
- index snapshot `4421b16a6cd64014ac154f9a789eef74bca52f604643ce3006a315091b71da85`;
- run-binding digest `ce44526f314aabc2cda91bfdc265a686126b66e1143da3f82381ae664a219a51`;
- store-identity digest `2ef22ab95ab25cc64a85ecf026f21bb30324bed441d839b54824f56f18d00c1a`;
- producing run `phase5-synthetic-handoff-v1-2-activation-run`.

## Prior versions

Version 1.0 failed canonical-byte/checksum integrity; that failed receipt remains preserved at commit `1b229fdec74eb602c03d8301fd5744bc9c73b30e`. Version 1.1 corrected package bytes but activation and target identities did not join and the package did not provide enough independent groups for the frozen probe; that failed receipt remains preserved at commit `7791c938ce2d97014216974a02f5174b42893874`.

Version 1.2 coordinates accepted-manifest, activation, and target identities across ten independent layouts. Neither prior failed acceptance worktree nor receipt was accessed, changed, reused, or overwritten during this acceptance.

## Independent validation

The public v1.2 package validator passed first. Person B then independently verified the exact inventory, every non-self `SHA256SUMS` entry against raw checked-out bytes, the intentional omission of `SHA256SUMS` from itself, UTF-8/LF/no-BOM/terminal-LF rules for every text file, canonical handoff-manifest JSON, and every manifest-to-payload size, hash, identity, and count cross-reference.

The activation snapshot, immutable run binding, and referenced chunk were loaded and validated through public activation-store APIs. Ten explicit `ActivationRowKey` values selected ten finite width-2048 `float32` vectors. Reversing request order returned the same vectors by key. The vectors were promoted to little-endian C-contiguous `float64` in canonical key order for analysis; the promoted-byte SHA-256 is `56dbf9f08ac74171248201b651978d77aedf7e81db14da17dc164c63e0e2de4f`.

The target document passed `validate_oracle_target_document`. It contains ten accepted, finite, nonconstant `mu_oracle_blocks` targets at same-frame offset zero.

## Exact join and folds

The universal join was exactly:

`trajectory_id + model_frame_idx`

Activation identity additionally retained `layer_idx + hook_site + producing_run_id`. The result contained ten joined rows, zero unmatched activation rows, zero unmatched target rows, zero duplicate activation keys, and zero duplicate target keys. The canonical joined-key SHA-256 is `62448525246b86c7f3e89fbe5365fff7033f637dd1a3a91bd4c14f914d25276f`.

The ten distinct layout groups populated five outer folds with two groups each. Each held-out outer fold left eight training groups. Every outer training partition populated four grouped inner folds with two groups each. No group crossed a held-out/training boundary, and no required split was empty.

## Tiny public probe

Person B ran `run_ridge_oof_probe` with the frozen configuration:

- target `mu_oracle_blocks`;
- same-frame offset `0`;
- layer `0`;
- hook site `residual_stream`;
- feature width `2048`;
- analysis dtype `float64`;
- ten joined rows;
- five outer folds;
- four grouped inner folds;
- alpha grid `[0.1, 1.0, 10.0, 100.0]`;
- seed `20260719`.

The CPU probe returned shape `[10]`; every output was finite. Its independently computed output hash is `50bad375850e7ca1bdbcfccc28397b5bf695804cae0a4c9db857c7385e5f9c61`, exactly matching the package declaration.

## Deterministic repeat

The complete public consumer path was executed twice in fresh Python processes. Package inventory and hashes, accepted activation keys, promoted-vector hash, validated target keys, joined-key hash, counts, fold assignments, probe configuration, output bytes, and probe output hash were identical.

Direct target-first collection of `tests/oracle/test_regime_a_oracle.py` and `tests/probes/test_join_and_splits.py` encountered the repository's circular import ordering issue. This is recorded as a nonblocking warning rather than hidden by changing import order. The documented complete store-first consumer path succeeded in both fresh processes; the focused v1.2 package suite passed 10 tests and 3 subtests, while the Person B bridge/fold suite passed 17 tests and 5 subtests.

## Final classification

- `private_assistance_used`: `false`
- `migration_required`: `false`
- `scientific_status`: `synthetic_non_scientific`
- `status`: `PASS`

This receipt proves that the public activation store enters Person B's public target, join, grouped-fold, matrix, and tiny ridge-probe path. It does not establish a scientific result.
