# Person B Phase 5 activation-store receipt

## Verdict

**INTERFACE DEFECT — VERSIONED DECISION REQUIRED**

Person B received the committed synthetic, non-scientific Phase 5 activation-store fixture at `docs/status/fixtures/phase5_activation_store_example` from certified Person A revision `b0b71653311902fffce769aca6c4e81475ba0766`.

## Independent package verification

The clean checkout contains the exact approved directory and file classes: one numeric NPY chunk, one canonical JSON index, one immutable run binding, `README.md`, and `SHA256SUMS`. It contains no extra files, temporary files, symlinks, alternate chunks, alternate indexes, or alternate run bindings.

Four listed payload identities are consistent with the committed bytes:

- chunk: 8,320 bytes, SHA-256 `409f6a6bf3e85e2b177db81d51b621707688bdcb6630f98d336d16537f39217f`
- index: 9,019 bytes, SHA-256 `8526daf64764ec06940ca1ac4209c76371869382c13d546404d5726fc1d79805`
- run binding: 1,356 bytes, SHA-256 `3b7ee30304940f062066c57ac4219dad2f68dfc9a505007c44355fdebae9084e`
- checksum inventory: 498 bytes, SHA-256 `11162a1898649759eed4c222d538f48aff2d72da903a247aa9b4f12fcd260f1f`

The README does not match its published identity:

- declared by `SHA256SUMS`: `29b7cb053e19d4276ab283c7cad3d12269f2599dabbbce0fc8ce07e166266e8a`
- independently observed: 364 bytes, SHA-256 `6c633b930b3e35788a35b882c1067d11ccb01dee23b99d26aaa42834f3636a41`

The declared digest is exactly the digest of the same README represented with CRLF line endings (373 bytes). The clean committed checkout and repository attributes use LF. The public command consequently exits nonzero with `ValueError: example checksum mismatch: README.md`.

The index and run-binding JSON directly expose snapshot ID `834f1070e8d77680e06d7713caf618624211c0bcf5ce4cfef8b692011ebd67e4`, binding digest `5dd76ca68c331b5c7e4f6644f9c11c2161b6cc4f4b70de407eb80e6d05eb4d22`, store-identity digest `d0ba83b92ac5fc30b7092355ce9bd47faa182fa4fa4bdfb338afa3b2a5bcd231`, accepted-manifest hash `5555555555555555555555555555555555555555555555555555555555555555`, and producing run ID `phase5-synthetic-non-scientific-example`. These are recorded as unaccepted declarations, not as a successfully consumed store, because the package-integrity gate failed first.

## Consumer path and join

The committed Person B path was identified as:

- target schema and validator: `src/mineocclude/oracle/schema.py`, `validate_oracle_target_document`
- target fixture: `tests/fixtures/person_b/synthetic_oracle_targets.json`, SHA-256 `3894ab1c9abcdecc89d0741f853dcfa8677ab5ad9d6e246c7ed65cca68dc2887`
- activation/target join: `mineocclude.probes.bridge.build_joined_frame_table`
- matrix builder: `mineocclude.probes.bridge.build_probe_ready_matrices`
- bounded probe: `mineocclude.probes.bridge.run_ridge_oof_probe`

The intended universal join is explicit `trajectory_id + model_frame_idx`, while activation identity also retains `layer_idx + hook_site + producing run identity`. No target validation or join was executed after the package failure. This avoids silently bypassing the public handoff integrity contract.

## Probe and repeat

No tiny probe ran, and no deterministic repeat was claimed. The activation index loader, selective vector reader, target validator, join, and probe were not used past the failed package gate. Zero chunks were accepted and zero rows were loaded.

## Interface defect

- Producer field: the `README.md` entry in `SHA256SUMS`.
- Person B expectation: every published checksum matches the exact bytes in a clean committed checkout.
- Incompatibility: the inventory binds a pre-normalization CRLF representation, while Git publishes LF bytes.
- Affected contract: the Phase 5 synthetic activation-store handoff integrity inventory enforced by the public `validate-example` operation.
- Smallest migration: publish an explicitly versioned fixture-package revision whose inventory is computed after Git normalization from canonical committed LF bytes, then verify it from a fresh checkout. Schema version 1.0 may remain only through an explicit packaging-only version decision; the current inventory must not be silently reinterpreted.

`migration_required` is therefore `true`.

## Scope and scientific status

No private Person A assistance was used (`private_assistance_used: false`). The received fixture is synthetic and non-scientific. This failed engineering handoff does not support or contradict any scientific claim.
