# Person B Analysis v0.2 Decision Log

Date: 2026-07-21

Status: implemented before live results. B1.9 schema/config and cross-role
Phase 0/1 interface signoff is complete for
`80d41c5ca0e341263a7b0c683fae4b51be376c55`. Live producer artifacts,
runtime qualification, and result approval remain pending.

## Decision

Advance the B analysis config from `person-b-phase1-v0.1` to
`person-b-phase1-v0.2` before any live activation result exists. Universal
schema v1.0 and Person A's frozen contracts remain unchanged.

Version 0.2 freezes:

- signed wall-parallel coordinate requirements;
- ordered filter stages and count audits;
- fold/scaler/fit/prediction/result artifact provenance;
- grouped inner validation and the U4 development split algorithm;
- complete MLP training settings;
- exact U1/U2/U3 binning, calibration, invalid-value, and reveal rules;
- trajectory-block permutations and layout→trajectory bootstrap rules;
- literal config-byte hashing;
- append-only corrections and new-run policy.

## Migration policy

No live Person B result exists, so no scientific result is migrated. Any
artifact generated under config v0.1 is validation evidence only and cannot be
relabeled as a v0.2 result. A future schema/config change must:

1. receive a new version;
2. record the reason and affected artifacts;
3. preserve prior artifacts;
4. rebuild filters, folds, scalers, fits, predictions, and metrics when the
   change can affect a result;
5. obtain Person B approval and any affected producer/consumer approval.

Universal schema changes follow the existing schema-v1 migration process and
are never introduced silently by B-owned tables.

## New-run policy

A new run is mandatory after a change to accepted rows, coordinate mapping,
target semantics, config bytes, filter order, folds, preprocessing, alpha or
layer selection, metric rules, resampling, direction selection, or dose/cap
logic. Documentation-only wording changes may reuse artifacts only when the
correction log explicitly records that no result-affecting field changed.

## Signoff record

- Central evidence: `docs/contracts/schema_v1_0_signed_record.md`.
- Person B scientific/config owner: approved the Phase 0/1 schema and analysis
  configuration at `80d41c5ca0e341263a7b0c683fae4b51be376c55`.
- Person A activation/request producer-consumer boundary: approved for the same
  Phase 0/1 checkpoint.
- Person C coordinate/state producer boundary: approved for the same Phase 0/1
  checkpoint; real adapter/runtime evidence remains pending.
- Person D baseline producer boundary: approved for the same Phase 0/1
  checkpoint; real baseline outputs remain pending.
- Person E measurement producer boundary: approved for the same Phase 0/1
  checkpoint; real measurement and U4 method/result approval remain pending.

This signoff does not approve live scientific results or later-phase methods.
