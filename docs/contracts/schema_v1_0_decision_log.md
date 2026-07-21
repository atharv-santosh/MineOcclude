# MineOcclude Schema Decision Log

## schema-freeze-v1.0-phase-1

Date: 2026-07-21

Status: `APPROVED_FOR_PHASE_1_INTERNAL_SCHEMA_FREEZE`

Decision: `schema_version = 1.0`

Previous implementation version: `0.1-draft`

### Context

Steps 1.1 through 1.7 established one Person A ownership map, strict universal
and cross-role validators, accepted and rejected synthetic fixtures, and a
CPU-only cross-role integration proof. Leaving accepted evidence on the draft
identifier would allow later runs to mix incompatible meanings without an
explicit migration boundary.

### Decision

The shared schema constant and all newly generated accepted Phase 1 evidence
use version `1.0`. The existing field names, units, explicit-key joins,
cardinality, lifecycle semantics, machine-readable rejection behavior, and
non-repair policy are frozen as recorded in
`schema_v1_0_signed_record.md` and the five contract documents.

The freeze resolves the remaining draft choices as follows:

- time orthogonalization must be explicitly checked before intervention;
- condition and displacement units use seconds and Minecraft blocks as recorded;
- controlled project vocabularies not enumerated by a universal validator are
  explicit configuration values bound to provenance hashes;
- registry IDs remain immutable non-empty strings rather than requiring UUIDs;
- URI schemes/storage roots and owner names are deployment configuration;
- partial run success is `completed_with_failures`; and
- un-reduced requested/applied alpha equivalence uses `1e-12` relative and
  absolute tolerance.

### Migration policy

Any result-changing change after this decision requires a **new schema version**
and a documented migration. Evidence produced under changed meaning also
requires a **new run identity**. Accepted v1.0 files are not rewritten in place;
old records and supersession lineage remain auditable. Fixture builders, contract
tests, the synthetic integration report, and this decision history must move
together when a new version is introduced.

### Known Step 1.7 orphan-report caveat

The Step 1.7 `orphaned_claim_bearing_rows` evidence explicitly enumerates the
target, baseline, rollout, and measurement provenance classes used by the
pipeline. It does not independently enumerate every auxiliary normalized-action,
token-map, or activation row as an orphan class. Those auxiliary rows are still
covered by mandatory explicit joins, cardinality checks, and integrity checks;
any missing or duplicate coverage makes the pipeline fail. Therefore the caveat
does not permit a passing report with a failed required join, but future schema
work may broaden the orphan enumeration for clearer reporting.

### Consequences

- Version-mismatched draft evidence now rejects with the existing schema-version
  rejection codes.
- Accepted and generated Phase 1 fixtures must remain deterministic schema v1.0
  evidence.
- Step 2 work may consume these interfaces but may not silently reinterpret
  them.
- This is an interface freeze, not approval of real scientific outputs or later
  teammate methods.

Approval: `APPROVED_FOR_PHASE_1_INTERNAL_SCHEMA_FREEZE`.
