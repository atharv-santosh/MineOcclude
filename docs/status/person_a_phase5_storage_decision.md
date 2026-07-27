# Person A Phase 5 pooled activation storage decision

## Status and objective

Status: locally implemented, not committed. GPU execution is neither required
nor authorized for this work. Step 5.8 independent Person B acceptance remains
pending.

The Phase 5 v1 objective is an append-safe, independently verifiable store for
production pooled activation vectors. It must preserve the frozen activation
handoff and scientific identity while making interruption, resume, corruption,
and cardinality failures explicit.

## Authorities and environment inspected

The implementation was checked against:

- `docs/contracts/activation_v1.md`;
- `src/mineocclude/contracts/activation.py`;
- `src/mineocclude/contracts/identity.py`;
- `src/mineocclude/analysis/filters.py`;
- `src/mineocclude/experiments/registry.py`;
- `src/mineocclude/contracts/rollout_registry.py`;
- the existing Phase 4 activation store and tests;
- the accepted activation handoff and synthetic chunk fixtures; and
- the local CPU and AWS L4 environment locks.

The frozen schema remains `1.0`. The existing activation handoff validator is
run before an index snapshot is published. The first-observation authority is
Person B's frozen `apply_ordered_filters()` path: rows must belong to the
accepted manifest, have lifecycle `accepted`, and occur at or after the
trajectory's earliest authoritative `visibility == "visible"` frame.

The qualified environments contain NumPy 1.26.4, pandas 2.3.3, and
safetensors 0.8.0. They do not declare pyarrow, fastparquet, Zarr, or HDF5.
NumPy 1.26.4 does not recognize a native `bfloat16` dtype. Phase 5 v1 therefore
rejects bfloat16 with a typed error; it never reinterprets bfloat16 bytes as
float16.

## Selected v1 design

Phase 5 v1 uses:

1. immutable C-contiguous rank-2 NumPy `.npy` chunks containing homogeneous
   mean-pooled visual vectors;
2. immutable canonical JSON index snapshots;
3. normalized repository-independent relative paths beneath an explicit store
   root;
4. same-directory temporary files and exclusive hard-link publication; and
5. immutable backend-neutral Python records so another reviewed index
   serializer can be added later without changing row identity or the reader
   interface.

There is one authoritative publisher. Workers may compute candidate vectors
and row metadata, but they do not publish accepted chunks or index snapshots.
The publisher validates, sorts, writes, reopens, hashes, publishes, and then
publishes the index. This avoids a mutable shared writer and does not claim
multi-writer locking.

Every producing `run_id` is bound before chunk-temporary creation to one
complete `ActivationStoreIdentity` in a canonical immutable
`run_bindings/run-<sha256(run_id)>.json` record. The record contains the full
identity and its digest, the exact eligibility-proof/source-row digests and
counts, and its own canonical binding digest, and is published exclusively
without overwrite. Exact replay validates and reuses identical bytes. A changed
identity or changed eligibility authority under the same run ID reports both
existing and requested digests and cannot reach chunk publication. A new run
ID receives a different deterministic binding.

The production store is pooled-only. The Phase 4 limited one-frame unpooled
pilot remains separate and unchanged. Dataset-wide unpooled retention is not
enabled.

## Alternatives considered

- **NumPy chunks plus canonical JSON index — selected.** Both are available in
  the locked environment, can be validated without pickle, and need no
  dependency change.
- **NumPy chunks plus Parquet index — deferred.** No reviewed Parquet engine is
  locked. Adding pyarrow or fastparquet now would be an unreviewed dependency
  upgrade. Phase 5 v1 does not claim to produce Parquet.
- **Zarr — rejected for v1.** It is not in either qualified environment and
  would introduce another storage system and dependency.
- **HDF5 — rejected for v1.** h5py is not locked, and a large mutable container
  is a poor fit for immutable append-safe publication.
- **safetensors — not selected.** It is available, but it does not remove the
  need for a scientific row index, and adopting a second tensor layout offers
  no v1 benefit over strict NumPy chunks.

No dependencies, requirements, or environment locks were changed.

## Identity and status model

The store/run identity contains schema version, producing run ID, checkpoint
hash, model hash, configuration hash, preprocessing hash, accepted-manifest
hash, code SHA, hook site, sorted requested layers, stored dtype, and hidden
width. Changing any field produces a different identity digest. The current
activation contract additionally requires row `model_hash` to equal the
checkpoint hash.

Each chunk identity binds the complete store identity to one homogeneous layer,
the deterministic first and last scientific row keys, row count, dtype, and
hidden width. Its digest determines—but does not replace—the chunk ID and path.

The scientific row identity is:

`trajectory_id + model_frame_idx + layer_idx + hook_site + producing run_id`

Array order, directory order, and filenames are never scientific identity.
Rows are sorted by this explicit key before vector serialization.

Operational states are `pending`, `writing`, `completed`, and `failed`.
Analysis lifecycle states remain `accepted`, `excluded`, and `superseded`.
Only completed runs, completed independently validated chunks, and accepted
rows enter an accepted index snapshot. Non-accepted work remains auditable but
cannot masquerade as accepted analysis data.

## Chunk and index representation

Every completed chunk is one numeric non-object `.npy` array of shape
`[row_count, hidden_width]`. Metadata records the chunk and identity digests,
relative path, row count, hidden width, per-row vector shape, dtype, byte size,
SHA-256, explicit UTC index-record time, completed state, and bounded row-key
range. The field remains named `creation_timestamp` for the v1 record, but its
fixed semantic is `index_record_time_not_chunk_byte_creation`. It does not
claim the filesystem creation time of immutable chunk bytes and is not part of
scientific identity. Reusing an exact orphan records the time at which the
reused bytes enter the new index record, not a fabricated new byte-creation
time.

The canonical JSON snapshot stores complete store identity, completed run
status, creation time, sorted chunk descriptors, and sorted activation handoff
rows. Rows preserve condition, visibility, token positions, pooling, lifecycle,
chunk offset, and provenance fields required by the existing contract. The
snapshot ID hashes the canonical identity document; it is not presented as a
self-signature of its own serialized bytes.

Before publication, validation checks exact required data, strict scalar types,
hash formats, safe paths, identity agreement, unique chunk IDs, unique
scientific keys, unique chunk-row references, the exact offset set
`0..row_count-1`, dtype and shape agreement, homogeneous chunk layer, complete
first/last key bounds, reference cardinality, completed states, accepted
lifecycle, row ordering, canonical JSON, the existing activation handoff
contract, and every referenced chunk's persisted bytes. Lexical containment,
every existing path component, and final resolved containment are checked
separately. Symlinked chunks, indexes, parent directories, and store roots are
rejected even when their targets remain inside the store.

Publication requires the authoritative accepted-manifest rows themselves. The
public boundary reconstructs `ActivationEligibilityProof` internally through
Person B's existing `apply_ordered_filters()` implementation before a run
binding or chunk temporary can be created. A caller-created proof is never
publication authority. The compatibility `eligibility_proof` argument is
optional and, when supplied, is treated only as a claim: every field and its
canonical digest must exactly equal the internally reconstructed proof.

The reconstructed proof binds the complete store identity, accepted-manifest
hash, canonical source-row digest and count, and the exact eligible
trajectory/frame/layer/hook/run keys. Candidate condition and source
metadataâ€”including episode, ticks, render/action indices, layout, regime,
visibility, tau, v, q, duration, seed, lifecycle, and provenanceâ€”must match
the authority before any run binding or chunk temporary is created.
Pre-first-visible, unexpected, absent, duplicate, metadata-conflicting, or
claimed-proof-conflicting candidates fail closed. The independent cardinality
audit remains in place and does not derive its expectations from published
rows.

## Reviewed v1 input limits

The limits below are centralized in `mineocclude.activations.store` and reject
without truncation:

| Limit | Value |
|---|---:|
| Index JSON bytes | 134,217,728 |
| Index rows | 2,000,000 |
| Chunks per snapshot | 100,000 |
| Bytes per chunk | 536,870,912 |
| Rows per chunk | 16,384 |
| Hidden width | 16,384 |
| Total referenced bytes per snapshot | 2,199,023,255,552 |
| Run-binding bytes | 131,072 |
| Selected rows per read call | 65,536 |
| Selected chunks per read call | 256 |
| Result bytes per read call | 536,870,912 |

Index size is checked before reading its full text. Declared row/chunk counts
are checked before record construction and iteration. Chunk metadata and
physical byte size are checked before NumPy loads the array. Publication checks
the prospective row, chunk, chunk-byte, hidden-width, and total-referenced-byte
limits before creating its chunk temporary. These limits accommodate the
pooled 2,048-wide float16/float32 MVP design while placing reviewed bounds on
untrusted JSON and NumPy inputs.

The read API resolves requested scientific keys from the index and opens only
the referenced chunks. Before validating or loading any selected chunk, it
computes selected row count, selected chunk count, result element count, and
result bytes using reviewed signed-64-bit arithmetic. Float16 vectors promoted
to float32 are costed at the float32 result item size; stored bytes and dtype
metadata remain unchanged. The 65,536-row and 512-MiB result limits admit four
full 16,384-row chunks at the MVP width of 2,048 float32 values, while the
256-chunk limit bounds file opens for fragmented selections. Exact boundary
values pass; requests above any limit fail before `numpy.load()` or
`numpy.stack()` and are never truncated or partially returned.

## Publication, interruption, and rollback

Publication is:

1. validate identity, rows, uniqueness, array shape, dtype, and finiteness;
2. sort rows and vectors by scientific identity;
3. write and fsync a unique temporary `.npy` beside its destination;
4. reopen it with `allow_pickle=False` and independently validate it;
5. hash the persisted temporary bytes;
6. hard-link it exclusively to the deterministic final path;
7. reopen and validate the final chunk;
8. construct and fully validate the next immutable index snapshot;
9. write and fsync a unique temporary JSON file; and
10. hard-link it exclusively, then reload and validate it.

No accepted object is overwritten. A failed operation removes only its own
temporary files and preserves all prior accepted files. Both a midwrite failure
and a hard-link publication failure place deletion of their operation-created
temporary under an unconditional cleanup boundary. Cleanup success leaves no
current-operation temporary. Cleanup failure preserves the original primary
exception and attaches structured `cleanup_error` information containing the
temporary path plus the cleanup exception type and message. Pre-existing
accepted objects, bindings, and unrelated temporary files are never removed.

An interruption after chunk publication may leave an immutable orphan. It is
not accepted analysis data because no index references it. An exact retry may
reuse the orphan only when deterministic identity and bytes agree and the
persisted rank, shape, dtype, row count, byte size, and checksum validate.
Conflicting content at the same final path fails closed. The audit lists
unreferenced `.npy` chunks as immutable orphans.

Deterministic fault injection covers every write/publication boundary,
including immediately after index publication. A forced interruption leaves
either no accepted index or one complete checksum-valid index reference.

## Resume and audit

Resume always starts from an explicitly selected immutable snapshot. The
snapshot and every referenced chunk are independently revalidated. A row is
skipped only when its full scientific identity, store identity, lifecycle,
completed state, expected metadata, chunk identity, offset, bytes, checksum,
rank, shape, row count, and dtype agree. Missing and unchanged
pending/writing/failed rows are retry candidates. A missing row claimed as
completed is a conflict. Wrong run, hook, layer, trajectory, frame, or
provenance is a conflict rather than retry. Excluded and superseded work is
reported as excluded only when no accepted completed row already exists;
otherwise it conflicts. Skip, retry, conflict, and excluded sets are
canonically sorted, making repeated planning idempotent.

The audit derives expected frame/layer keys through the frozen accepted-manifest
and post-first-visible filter. A pre-first-seen violation is reported only when
that activation key is actually present in the snapshot or supplied work
records. A row counts as completed accepted only after the referenced ordinary
non-symlink chunk, bytes, checksum, NumPy inventory, exact offset, homogeneous
layer, row range, and complete identity all validate. The audit reports
expected, completed, missing, duplicate, unknown-chunk, out-of-bounds,
incomplete-offset, row/chunk binding, unexpected, observed pre-first-seen,
corrupt, checksum, byte-size, dtype, shape, row-count, identity,
operational-state, lifecycle, orphan, and conflict categories. Every expected
shortfall has a deterministic machine-readable reason preserving state,
lifecycle, state/exclusion/supersession detail, and whether it came from a work
record, integrity finding, conflict, or unexplained absence. It never inserts
zero vectors for unavailable data.

Loaded snapshot rows are recursively frozen as read-only mappings and tuples.
Canonical serialization thaws them into ordinary JSON objects and arrays, so a
caller cannot mutate a validated in-memory snapshot while persisted JSON
remains conventional and deterministic.

This record shape remains compatible with Person B's activation handoff:
readers retain universal identity, condition fields, visibility, token
positions, pooling method, chunk ID/offset, model and preprocessing provenance,
manifest identity, run identity, and accepted lifecycle. Step 5.8 still
requires Person B's independent acceptance.

## Checked-in synthetic index example

`docs/status/fixtures/phase5_activation_store_example/` is an explicitly
synthetic, non-scientific, deterministic example produced by the public writer.
The checked package is fixture package v1.1 under unchanged schema version 1.0.
Fixture package v1.0 was independently rejected by Person B because its README
checksum was calculated from a pre-Git-normalization 373-byte CRLF
representation while a fresh checkout contained the canonical 364-byte LF
representation. The failed receipt commit
`1b229fdec74eb602c03d8301fd5744bc9c73b30e` remains preserved. Version 1.1
writes the README and checksum inventory as explicit BOM-free UTF-8 bytes with
LF endings, then hashes the exact README bytes written to disk. This is a
fixture-package integrity correction, not a schema or storage-protocol
migration.

The package contains:

- `chunks/activation-chunk-106b16904a4ae44c7bac4903.npy` (8,320 bytes,
  SHA-256
  `409f6a6bf3e85e2b177db81d51b621707688bdcb6630f98d336d16537f39217f`);
- `indexes/index-834f1070e8d77680e06d7713caf618624211c0bcf5ce4cfef8b692011ebd67e4.json`
  (9,019 bytes, SHA-256
  `8526daf64764ec06940ca1ac4209c76371869382c13d546404d5726fc1d79805`);
- the immutable run binding (1,356 bytes, SHA-256
  `3b7ee30304940f062066c57ac4219dad2f68dfc9a505007c44355fdebae9084e`);
- `README.md`; and
- `SHA256SUMS`, written after all other files were closed and not presented as
  a signature of itself.

The documented `validate-example` command validates every checksum, loads the
canonical snapshot through the public loader, and selectively reads and checks
the expected synthetic vector. It also requires the exact approved inventory:
the three named subdirectories and only the README, checksum inventory, one
approved chunk, one approved canonical index, and one approved run binding.
Extra files, directories, alternate objects, temporaries, symlinks, unsupported
entries, missing files, and checksum omissions are rejected. `SHA256SUMS` does
not claim a checksum for itself. Generation is byte-identical across repeated
runs in the supported environment. The public validator hashes raw checked-out
bytes and rejects CRLF-mutated text rather than normalizing or repairing it.
The chunk, canonical index, and immutable run binding are unchanged: there is
no chunk, index, or run-binding migration. Audit 2 remains valid because
production storage code and numeric/identity payloads are unchanged. This
example is not accepted runtime evidence and is not independent Person B
execution. A fresh Person B acceptance run in a new worktree and branch is
required; the failed acceptance worktree and receipt must not be reused.

## Coordinated synthetic handoff v1.2

The independent v1.1 consumer attempt is preserved at receipt commit
`7791c938ce2d97014216974a02f5174b42893874`. Its package integrity, public
store load/read, and dtype-promotion checks passed, but the activation key
`synthetic-phase5-example-trajectory + 0` did not match Person B's target keys,
the accepted-manifest identities differed, and one trajectory/row could not
support the frozen five outer grouped folds with four grouped inner folds.
Those are fixture-coordination defects, not a production-store or schema
failure.

`docs/status/fixtures/phase5_activation_store_handoff_v1_2/` is the new
deterministic coordinated package. It remains explicitly
`synthetic_non_scientific`, uses schema version 1.0, and does not modify or
replace v1.1. Ten one-frame trajectories use ten distinct layout groups and one
shared accepted-manifest identity across authoritative manifest rows,
activation rows, the canonical index, and Person B target rows. The
deterministic five-way outer assignment has two groups in every fold. Each
outer training set therefore has eight groups, and each frozen four-way
grouped inner split has two groups in every fold.

The activation store remains the production `.npy` format written by
`publish_activation_chunk`, validated by `load_activation_index_snapshot`, and
read by `read_activation_vectors`. Person B's frozen synthetic bridge
authenticates a JSON chunk envelope. The bounded public consumer proof
therefore creates a deterministic in-memory bridge envelope only after the
production reader has verified and returned all ten vectors. That envelope is
not persisted as a second activation authority. Person B's unchanged public
`validate_oracle_target_document`, `build_joined_frame_table`,
`build_probe_ready_matrices`, and `run_ridge_oof_probe` functions then validate
ten exact universal-key joins, a `[10, 2048]` matrix, five nonempty outer folds,
all required inner folds, and ten finite out-of-fold predictions. The
consumer-proof output hash is
`50bad375850e7ca1bdbcfccc28397b5bf695804cae0a4c9db857c7385e5f9c61`.
It proves only that the public consumer path executes; the numeric result has
no scientific meaning.

The package has an exact eight-file inventory: README, checksum inventory,
machine-readable handoff manifest, authoritative accepted-manifest document,
Person B target document, one immutable `.npy` chunk, one canonical index, and
one immutable run binding. `SHA256SUMS` hashes every payload except itself.
Generation and the probe result are byte-deterministic in the supported local
environment. Package v1.0 and v1.1, both failed receipts, Audit 2 storage
revision `b0b71653311902fffce769aca6c4e81475ba0766`, production storage, and
schema 1.0 remain unchanged.

This is still Person A-authored synthetic handoff evidence. A fresh independent
Person B worktree must validate and consume v1.2 before Step 5.8 can pass.
Phase 5 remains gate-incomplete until that new receipt succeeds.

## S3 transfer considerations

Chunks and indexes are immutable independently checksummed objects with relative
paths. Transfer chunks first and the validated index last. A receiver must
revalidate bytes and references after transfer. This local hard-link protocol
does not claim that S3 provides atomic rename or filesystem hard-link
semantics.

## Benchmark harness and smoke result

`scripts/benchmark_phase5_activation_store.py` is CPU-only. It requires exactly
four named scenarios: `10-pilot`, `66-trajectory-mvp`, `regime-a`, and
`full-372-trajectory`. The roadmap-bound trajectory counts 10, 66, and 372 are
enforced. Regime A's trajectory count and every scenario's model-frame count,
layer count, hidden width, dtype, and chunk-row count remain explicit
caller-supplied inputs. Missing Regime A input fails the command; it is never
invented.

The command measures raw and persisted bytes, write/read/selective-read
throughput, checksum cost, float-to-float32 promotion, index size, and index
parse/validation time. Its machine-computed forecast records vector count, raw
bytes per vector/frame/trajectory, physical persisted bytes, exact NumPy
header overhead, measured/index-derived JSON estimate, checksum/write/full-read
and selective-read time, float32 promotion quantity/time, uncompressed
archive/S3 transfer quantity, largest chunk, simultaneous temporary staging,
and conservative staging peak. Measured bounded values, extrapolations,
assumptions, and uncompressed quantities are separate fields with byte/second
units. It requires a new output directory and refuses overwrite.

A bounded Windows smoke run used two float16 rows at hidden width 2048. It
produced an 8,320-byte chunk and a 14,688-byte index and passed the independent
`validate` command. Measured values from this single run were approximately:

- raw bytes per vector: 4,096;
- persisted bytes per vector: 4,160;
- chunk write throughput: 61,263 bytes/s;
- chunk read throughput: 804,960 bytes/s;
- selective read throughput: 461,209 bytes/s;
- checksum throughput: 6,351,630 bytes/s; and
- float16-to-float32 promotion throughput: 10,853,206 bytes/s.

These measurements only prove that the bounded harness works. They do not
establish approved capacity or generalize to production hardware. The current
repository and supplied roadmap do not contain the authoritative Regime A
trajectory/frame count or an approved capacity byte limit. A four-scenario
production forecast therefore remains blocked on that external input rather
than emitting invented values. Capacity status is `UNRESOLVED`; when an
explicit approved limit is supplied, each scenario reports `PASS` or `FAIL`
against persisted bytes plus its largest simultaneous staging object.

## Known limitations and future path

- Native bfloat16 persistence is unavailable in NumPy 1.26.4 and rejected.
- The publisher is deliberately single-authority; concurrent workers must hand
  candidates to that publisher.
- Indexes are JSON in v1 and may be larger/slower than a future columnar index.
- No S3 atomicity is claimed.
- No real model extraction or production-capacity benchmark was run.
- Authoritative Regime A counts and approved capacity remain unresolved inputs
  for Step 5.7 and the final four-scenario forecast; neither value is invented.
- A future reviewed Parquet serializer may encode the same backend-neutral
  records after its dependency and byte-level contract are approved.
- Step 5.8 independent Person B acceptance is pending.
- Phase 5 remains gate-incomplete until Step 5.8; no Person B receipt was
  created or fabricated.
- The frozen schema remains `1.0`, and no dependency upgrade occurred.
