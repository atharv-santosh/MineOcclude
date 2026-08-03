# Phase 5 coordinated synthetic handoff v1.2

This package is deterministic `synthetic_non_scientific` engineering data. It is not runtime evidence, a scientific result, or an independent Person B receipt.

Version 1.0 failed canonical-byte/checksum integrity. Version 1.1 fixed package integrity but its activation and target identities did not join and it lacked enough groups for the frozen Person B probe. Version 1.2 coordinates accepted-manifest, activation, and target identities across ten independent layouts.

The persisted activation data is the production Phase 5 `.npy` store written and loaded through public Person A APIs. Person B's frozen bridge authenticates a JSON fixture envelope, so the public consumer path reads the `.npy` vectors first and creates a deterministic in-memory envelope; no second persisted activation authority is introduced.

Validate and execute the bounded consumer proof with:

```powershell
python scripts/benchmark_phase5_activation_store.py validate-handoff-v1-2 --output-dir docs/status/fixtures/phase5_activation_store_handoff_v1_2
```

The public sequence is `load_activation_index_snapshot` -> `read_activation_vectors` -> `validate_oracle_target_document` -> `build_joined_frame_table` -> `build_probe_ready_matrices` -> `run_ridge_oof_probe`. The universal join key is exactly `trajectory_id + model_frame_idx`; row and file order are never identity.

Fresh independent Person B acceptance is still required before Step 5.8 can pass.
