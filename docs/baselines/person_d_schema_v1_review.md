# Person D Schema v1.0 A/B Compatibility Review

Review date: 2026-07-22

Current approval checkpoint: `integration/mvp` at
`80d41c5ca0e341263a7b0c683fae4b51be376c55`.

Status: **TECHNICALLY VERIFIED**

Formal Person A Phase 0/1 interface approval: **COMPLETE AT THE APPROVAL CHECKPOINT**

Formal Person B Phase 0/1 interface approval: **COMPLETE AT THE APPROVAL CHECKPOINT**

Central human signoff evidence is
`docs/contracts/schema_v1_0_signed_record.md`. Passing code and synthetic tests
remain engineering evidence only; the human approval is independently limited
to the reviewed Phase 0/1 interface and contract meanings at the exact
checkpoint above.

## D schema reviewed

- BaselineSpec: `person-d-baseline-spec-v1.0`, authoritative implementation
  `src/mineocclude/baselines/spec.py`.
- Prediction row: `person-d-baseline-prediction-v1.0`, same implementation.
- Universal identity version: A-owned schema `1.0`.
- Scientific row key: `trajectory_id + model_frame_idx`; both fields are
  mandatory and cannot be inferred from filenames, paths, row order, or
  directory order.

## Authoritative interfaces inspected

| Owner | Interface inspected | D use |
|---|---|---|
| A | `src/mineocclude/contracts/identity.py` (`SCHEMA_VERSION`, `FRAME_KEY`, SHA formats) | D imports schema/key constants and requires accepted-manifest and preprocessing provenance. |
| A | `src/mineocclude/contracts/activation.py` and `docs/contracts/activation_v1.md` | Review confirms the same frame key, accepted-manifest identity, and `preprocess_hash` vocabulary used by future D frame features. |
| A | `docs/contracts/schema_v1_0_signed_record.md` | Evidence that project schema `1.0` is frozen and that the D1.5 A/B handshake was human-approved for the exact checkpoint recorded above. |
| B | `configs/analysis/core.yaml` through `analysis.config.load_core_analysis_config` | D validates target names by reading B's current target authority; D does not redefine units or target semantics. |
| B | `src/mineocclude/probes/splits.py` (`validate_fold_manifest`) | D validates and consumes saved memberships unchanged, requires exact key coverage, and never assigns scientific folds. |
| B | `src/mineocclude/metrics/u1_mean.py` (`regression_metrics`) | The common harness calls B's metric implementation directly. |
| B | `src/mineocclude/contracts/analysis_inputs.py` | D's export uses B's current baseline family, feature-access, legal-information, identity, fold, and provenance validation. |

## Compatibility results

| Check | Result | Evidence |
|---|---|---|
| Row key | **TECHNICALLY VERIFIED** | `spec.py`, `firewall.py`, `harness.py`, and `tests/baselines/test_phase1_foundation.py` require exact non-duplicate `trajectory_id + model_frame_idx` identities. No unresolved technical row-key mismatch remains. |
| Fold contract | **TECHNICALLY VERIFIED** | `export.attach_b_fold_assignments` and the common harness call B's real sealed-manifest validator, reject stale/missing/duplicate coverage, and copy B memberships unchanged. Synthetic artifact: `tests/fixtures/person_d/synthetic_b_fold_manifest.json`. |
| Target contract | **TECHNICALLY VERIFIED** | BaselineSpec loads B's frozen target registry and the synthetic harness requires accepted target rows named `mu_oracle_blocks`, bound to target and accepted-manifest hashes. Target meaning/unit remain B-owned. |
| Metric contract | **TECHNICALLY VERIFIED** | Common harness directly calls B's `regression_metrics`; a focused mock-wrap test proves the call occurs. No D-local metric authority was added. |
| Manifest/preprocess identity | **TECHNICALLY VERIFIED AT SCHEMA LEVEL** | D requires schema `1.0`, SHA-256 accepted/fold/target/config/preprocess hashes, and code provenance. The B fold artifact is content-validated and bound to its input/config hashes. A real preprocessed-frame producer artifact is not claimed. |
| Prediction schema | **TECHNICALLY VERIFIED** | Strict validation rejects missing/unknown identity, non-finite predictions, wrong baseline/version/target/scope, and malformed provenance. Two existing baselines emit identical requested held-out key sets. |

## Test evidence

- `tests/baselines/test_phase1_foundation.py`: 26 focused tests.
- `tests/baselines/`: 67 tests passed on 2026-07-22 after this review.
- Full repository and whitespace verification are recorded in the task handoff
  after the final commands complete; this record does not prestate results.

## Unresolved items

1. Real accepted manifests, target tables, fold manifests, and preprocessed
   frames do not yet exist for D consumption. This is later execution work,
   not a Phase 1 synthetic-contract mismatch.
2. B's current baseline-input allowlist accepts only declared families. D
   fails closed for any additional family until B explicitly adds it; this
   does not alter the two-baseline internal synthetic proof.

There is no unresolved technical row-key, fold-field, target-name, metric-API,
accepted-manifest-field, or preprocessing-identity mismatch in the repository
review. Formal A/B approval is complete only for the Phase 0/1 handshake at
`80d41c5ca0e341263a7b0c683fae4b51be376c55`; real-data execution and final
scientific-result approval remain pending.
