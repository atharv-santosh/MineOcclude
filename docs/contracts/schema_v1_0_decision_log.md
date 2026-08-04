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

## activation-fixture-20hz-timebase-correction-001

Date: 2026-07-21

Owner: Person A

Status: `SUPERSEDED_SYNTHETIC_EVIDENCE_REPLACED`

### Context

The original accepted synthetic activation fixture used `tau = 0, 1, 2`
seconds for consecutive `model_frame_idx = 0, 1, 2` and `server_tick = 100,
101, 102`. Those values contradicted the frozen 20 Hz timebase. Correcting the
values to `tau = 0, 0.05, 0.10` changed the meaning and bytes of the accepted
synthetic handoff, so retaining its original evidence identities would have
silently rewritten frozen evidence.

### Correction and lineage

Person A replaced the synthetic evidence identities together with the timing
correction:

| Evidence field | Superseded value | Replacement value |
|---|---|---|
| `handoff_id` | `synthetic_activation_handoff_001` | `synthetic_activation_handoff_002` |
| `run_id` | `synthetic_activation_run_001` | `synthetic_activation_run_002` |
| `accepted_manifest_hash` | 64 repetitions of `5` | 64 repetitions of `6` |

The generated machine-readable record is
`tests/fixtures/activation/timebase_correction_lineage.json`. All accepted and
intentionally rejected activation fixtures now derive from the replacement
identity. The Step 1.7 synthetic oracle target fixture continues to derive its
time fields from the corrected activation handoff.

### Schema consequence

This is an A-owned compatibility correction to non-scientific synthetic
evidence, not a B-owned rewrite and not a schema migration. The already frozen
contract defines `tau` in seconds at 20 Hz, so `schema_version` remains `1.0`.
The superseded identity remains auditable in this decision log, the generated
lineage record, and Git history; it must not be reused for corrected evidence.
