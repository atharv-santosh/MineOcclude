# Person B Phase 5 activation-store receipt — package v1.1

## Verdict

**INTERFACE DEFECT — VERSIONED DECISION REQUIRED**

Person B independently consumed fixture package v1.1 from certified Person A revision `9c8a2f63d88d0c648e3f702557727be87ab56487`. The underlying storage implementation remains the Audit 2-certified revision `b0b71653311902fffce769aca6c4e81475ba0766`.

Package v1.0 previously failed integrity validation because its README checksum described pre-Git-normalization CRLF bytes. That failed acceptance remains preserved at commit `1b229fdec74eb602c03d8301fd5744bc9c73b30e`. Package v1.1 corrected only the canonical package text bytes and checksum.

## Package and store acceptance

The public package validator passed without normalizing or repairing the fixture:

```text
Phase 5 synthetic activation-store example: VALID
```

The exact inventory contains one numeric NPY chunk, one canonical JSON index, one immutable run binding, `README.md`, and `SHA256SUMS`. There are no extra files, temporary files, symlinks, alternate payloads, or unapproved nested paths. The README and checksum inventory are valid UTF-8 with LF endings and no carriage returns. `SHA256SUMS` authenticates every listed raw payload and intentionally does not list itself.

The public index loader and validator independently validated the canonical index, run binding, and referenced chunk. The public selective reader loaded one accepted activation vector by explicit `ActivationRowKey`, producing shape `[1, 2048]` at stored dtype `float32`; Person B promoted the analysis copy to `float64`. The preserved activation identity is:

```text
synthetic-phase5-example-trajectory
+ model_frame_idx 0
+ layer_idx 0
+ residual_stream
+ phase5-synthetic-non-scientific-example
```

## Person B target path

The authoritative committed Person B path was confirmed:

- target validator: `mineocclude.oracle.schema.validate_oracle_target_document`
- target fixture: `tests/fixtures/person_b/synthetic_oracle_targets.json`
- join: `mineocclude.probes.bridge.build_joined_frame_table`
- matrix builder: `mineocclude.probes.bridge.build_probe_ready_matrices`
- probe: `mineocclude.probes.bridge.run_ridge_oof_probe`

The target fixture passed its public validator with five accepted rows and no duplicate target keys.

## Explicit-key join failure

The universal join is `trajectory_id + model_frame_idx`. The activation fixture contains:

```text
synthetic-phase5-example-trajectory + 0
```

The target fixture contains:

```text
synthetic_oracle_trajectory_0001 + 0
synthetic_oracle_trajectory_0001 + 1
synthetic_oracle_trajectory_0001 + 2
synthetic_oracle_trajectory_0001 + 3
synthetic_oracle_trajectory_0001 + 4
```

The intersection is empty: one activation frame is unmatched, all five target frames are unmatched, and zero rows join. The activation store is bound to accepted-manifest hash `5555555555555555555555555555555555555555555555555555555555555555`; the target fixture is bound to `6666666666666666666666666666666666666666666666666666666666666666`. The public join requires those identities to agree.

Person B did not rewrite identities, manufacture target rows, or infer alignment from row or filename order.

## Probe and deterministic repeat

No probe ran because zero validated rows joined. In addition, the activation
fixture exposes only one vector from one layout. Person B's selected public
probe uses frozen five-fold outer and four-fold grouped inner validation, so a
one-row fixture would not be probe-capable even if a single target row were
identity-aligned. Running a probe after either failure would not demonstrate
activation-store entry into Person B's analysis path.

Two fresh processes repeated package validation, public index loading, selective vector reading, target validation, and explicit identity comparison. They produced identical fixture hashes, activation keys, vector bytes, empty joined-key sets, row counts, and the same fail-closed result. The deterministic blocked-path result hash is `896bc87cef857b497e03af36518bfbbebe75e7211762bdd078b313be59701715`.

## Required correction

No schema migration is required (`migration_required: false`). Schema version 1.0, field meanings, and explicit join semantics are working correctly.

A new coordinated, versioned synthetic fixture pair is required. It must either
provide a publicly validated Person B target document for the activation
fixture's exact frame and accepted-manifest identities, or provide a new
activation fixture generated for an existing validated target document. The
pair must also contain enough genuine synthetic layout groups to satisfy the
frozen outer/inner probe split rules. Neither current fixture may be silently
rewritten in place.

## Scope

No private Person A assistance was used (`private_assistance_used: false`). All data is synthetic and non-scientific. This receipt makes no MineWorld or scientific-performance claim.

Target-first focused test collection also exposed an existing circular-import ordering limitation. The exact target and join tests pass when the public activation-store API is imported first, matching the prescribed complete consumer path. This is recorded as a nonblocking YELLOW issue relative to the separate fixture-identity blocker.
