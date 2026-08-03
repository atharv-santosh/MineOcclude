# Person A Phase 3 Parquet dependency decision

## Decision

**APPROVED:** `pyarrow==25.0.0` is the sole approved Parquet implementation
for MineOcclude. The downstream owner is Person E.

This approval adds a MineOcclude-specific dependency after the official
MineWorld environment was qualified. It does not change or reinterpret the
pinned MineWorld dependency set, source revision, asset revision, activation
storage format, or schema version.

## Authority and preserved environment

The decision was made from Person A branch revision
`f0a4fed546eb1cf19a7094e6b99399a58294726a`. Both qualified environment
specifications retain:

- CPython `3.10.20`;
- NumPy `1.26.4`; and
- pandas `2.3.3`.

The Phase 2 AWS evidence records CPython `3.10.20`, Linux x86-64, and glibc
`2.39`. No qualified package pin other than the new `pyarrow` entry was
changed.

## Candidates and local compatibility evidence

Candidate versions `24.0.0` and `25.0.0` were installed separately with exact
NumPy `1.26.4` and pandas `2.3.3` pins in disposable environments beneath:

`C:\Users\lollo\MineOcclude-Parquet-Qualification\person-a-20260728-f0a4fed`

That directory is outside the MineOcclude repository and outside the qualified
MineWorld environment. The tested host was Windows
`10.0.26200`, AMD64, CPython `3.10.20`.

Both candidates passed:

- package import and `pip check`;
- an explicit Arrow-schema Parquet write/read round trip;
- nullable string, boolean, signed-integer, floating-point, and binary columns;
- schema metadata preservation;
- stable declared column order and input row order;
- pandas `2.3.3` write/read using `engine="pyarrow"`;
- rejection of an unsupported arbitrary Python object; and
- a guarded round trip in which any call to `pickle.dump`, `pickle.dumps`,
  `pickle.load`, or `pickle.loads` failed the test; no call occurred.

The exact-schema output digests were:

| Candidate | Arrow table SHA-256 | pandas table SHA-256 | Result |
|---|---|---|---|
| `24.0.0` | `9749980c8fec9d578a227522513282944e64564aee1ae58fbb3e900d346308ea` | `35e6a4c6f8376bb13d40505ef1921db0ceba7d0e05543143647dcefe7b112ed0` | PASS |
| `25.0.0` | `881aa5de360c62d90f2362325d5232dcf54ae97745a05a4a06fbe6c6576e7dc7` | `744a2a0829f75cb7d41043c8a00a8fd5fb6bd7a20f516844f971c57399492c2b` | PASS |

These digests identify the disposable test outputs only. They are not a
cross-version Parquet-byte stability promise.

Version `25.0.0` was selected because it is the newest candidate actually
qualified by this review and passed the same exact compatibility matrix as
`24.0.0`.

## Why pyarrow rather than fastparquet

`pyarrow` provides the Apache Arrow project-owned Parquet implementation,
explicit Arrow schemas and field metadata, binary columns, and direct pandas
engine support through one package. Those behaviors match Person E's typed
artifact requirement and passed the controlled qualification.

`fastparquet` was not added or installed. Adding it after `pyarrow` passed
would create two competing Parquet authorities without a demonstrated need.
This decision is not a generic claim that `fastparquet` is defective; it is a
minimal single-engine authority decision.

## Package metadata and Linux/AWS distribution evidence

Installed distribution metadata for `pyarrow==25.0.0` reports:

- `Requires-Python: >=3.10`;
- license expression `Apache-2.0`; and
- no separately declared Python distribution dependency.

CPU-only `pip download --only-binary=:all: --no-deps` checks obtained:

| Platform tag | Wheel | Bytes | SHA-256 |
|---|---|---:|---|
| CPython 3.10 Windows AMD64 | `pyarrow-25.0.0-cp310-cp310-win_amd64.whl` | 27,840,572 | `d293e9959b29a24c82d936d04ab2b7fd8b8d334030de2e56a99aba94f008ad7a` |
| CPython 3.10 manylinux 2.28 x86-64 | `pyarrow-25.0.0-cp310-cp310-manylinux_2_28_x86_64.whl` | 50,056,398 | `b72d943ff4e10fec8d48aedb23322d8f6ea8bc2d698b81db37e73730f69e4862` |

The Linux wheel's glibc floor is compatible with the Phase 2 AWS evidence's
glibc `2.39`. This proves distribution availability for the declared Python
and Linux ABI; it is not an AWS installation or runtime test. No SageMaker
instance or GPU was started.

## Authoritative surfaces

The exact pin is recorded in:

- `requirements.txt`, the authoritative MineOcclude dependency file;
- `configs/environments/mineworld_local_cpu.yml`;
- `configs/environments/mineworld_aws_l4.yml`; and
- `scripts/check_env.py`, which requires the exact installed version and a
  successful import.

Only `pyarrow` is approved. `fastparquet` remains undeclared.

## Scope, limitations, and downstream obligation

This review approves a compatible dependency. It does **not** prove that
Person E's future `detections.parquet` or `homographies.parquet` bytes are
deterministic. Person E must define an explicit schema, engine, writer
parameters, ordering, metadata policy, and independent round-trip/hash tests.

No Person E worktree was modified. No U4 pushed-result content was inspected.
The external MineWorld checkout remained at
`9f49efbcc68a5f0cf60e78f0abc566eac409282f` and clean; its
`requirements.txt` remained 268 bytes with SHA-256
`b58d7e3514e7f9787ddd428fdc755e08cb48a75dd3cd09a4e1fc8e4c210af38c`.
No GPU was used.

The Phase 5 activation store remains the approved NumPy/JSON design. This
dependency decision does not migrate it to Parquet and does not alter its
evidence.

## Rollback

If a later controlled environment cannot install or validate this exact pin:

1. stop Parquet-producing work rather than silently selecting another engine;
2. remove `pyarrow==25.0.0` from `requirements.txt` and both qualified
   environment files;
3. remove the `pyarrow` version/import requirements from `scripts/check_env.py`;
4. rerun the dependency-authority and environment/config checks; and
5. open a new Person A dependency review for any replacement version or
   engine.

Rollback revokes the Parquet dependency approval; it does not authorize CSV,
JSON, NPZ, pickle, a custom Parquet implementation, or `fastparquet` as an
implicit substitute.
