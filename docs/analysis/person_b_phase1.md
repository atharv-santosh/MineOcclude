# Person B Phase 1: Scientific Methods Foundation

Status: v0.2 foundation implemented against universal schema `1.0`; no live
results have been produced.

## Scope

Person B Phase 1 supplies the dependency-light scientific foundation needed
before real activation fitting:

- a named target and analysis configuration;
- two independent exact Regime A oracle implementations;
- synthetic state and target evidence;
- an explicit-key A-to-B activation/target join;
- deterministic five-fold layout grouping;
- tests that fail closed on leakage, cardinality, unit, and manifest errors;
- ordered filter/count audits and tamper-evident analysis artifacts;
- leakage-safe ridge/MLP, U1-U3, resampling, and U4 producer foundations.

The Phase 1 A-to-B activation and B-to-A intervention contracts are not edited.
The Person A placeholder oracle rows remain synthetic integration evidence.
Person B's scalar wall-parallel targets are a separate B-owned table joined by
`trajectory_id + model_frame_idx`.

## Canonical target fields

| Field | Unit | Source | Permitted use |
|---|---|---|---|
| `mu_oracle_blocks` | blocks | primary Regime A oracle | mean probe target |
| `var_oracle_blocks2` | blocks squared | primary Regime A oracle | oracle audit |
| `sigma_oracle_blocks` | blocks | square root of oracle variance | calibration |
| `log_sigma_oracle` | dimensionless | `ln(sigma_oracle_blocks / 1 block)` | hidden-row spread probe target |
| `x_true_blocks` | blocks | authoritative server state | scoring only |
| `tau` | seconds | schema-v1 identity | oracle input and time control |

The full field/type/source/use dictionary is frozen in
`docs/contracts/person_b_oracle_target_v0_1.md`. The remaining required inputs
inherit their frozen universal names directly:
`visibility`, `v` (blocks/s), `q` (blocks squared/s), `duration` (seconds),
`layout_id`, and `trajectory_id`. Person B does not introduce aliases for
these fields.

`duration` remains numeric seconds; B does not add `duration_id`.
`hidden_ticks` is derived from `tau / 0.05 seconds` and is not a second stored
time field. `log_sigma_oracle` eligibility is explicit: hidden rows with
positive spread receive a finite value; every other row receives null.

Visible primary-oracle rows have zero spread and no log-spread target. Hidden
truth is copied only after the posterior is computed and is absent from both
oracle function signatures and the declared information set.

## Regime A information set

The primary oracle uses only:

1. last visible authoritative wall-parallel position;
2. known scripted `v` in blocks per second;
3. known scripted `q` in blocks squared per second;
4. `tau` in seconds at the locked 20 Hz rate; and
5. visibility.

`primary_scalar_kalman.py` performs iterative prediction at `dt=0.05` seconds.
`closed_form.py` independently evaluates `mu=x_last+v*tau` and
`P=P_last+q*tau`. Target construction stops if they differ by more than
`1e-6`. It also rejects unknown visibility states, non-increasing hidden
`tau`, nonconsecutive server ticks/model frames, mixed episode IDs, changes to
`v` or `q` within an occluded run, mixed manifests, mixed model/preprocess
identities, and malformed document envelopes.

## Input boundary

The JSON consumed by `build_oracle_targets.py` is a B-owned derived-state
table that carries the frozen schema-v1 universal row identity. It is not a
claim that Person C's raw trajectory package already has this flat shape. A
validator-backed C/A-to-B adapter is still required before real state logs are
used; any missing real-data field or meaning must be handled as an explicit
adapter or migration decision, never by silent repair.

Live state inputs additionally require a content-hashed coordinate frame with
an origin and positive world-space unit vector signed by Persons B and C.

The checked B oracle fixture uses physically coherent consecutive 20 Hz ticks.
The A-to-B compatibility test separately derives non-scientific target inputs
from Person A's activation fixture. Its synthetic `tau` values follow the same
consecutive 20 Hz frame/tick invariant as claim-bearing inputs.

## Grouping and resampling plan

- Five folds are grouped by `layout_id`; a layout never crosses folds.
- A trajectory cannot appear in multiple layouts, model-frame keys must be
  unique, and existing fold assignments cannot be silently overwritten.
- Scaling, alpha selection, layer selection, and direction selection use only
  training/validation data.
- MVP permutations preserve trajectory structure.
- Bootstrap hierarchy is layout first, then whole trajectories.
- Neighboring frames are never treated as independent inferential units.

Exact seeds, counts, alpha grid, MLP shape, coverage levels, exclusions, and
U1-U4 output names are frozen in `configs/analysis/core.yaml`.

The v0.2 config also freezes accepted-manifest membership before visible-anchor
eligibility in the filter order, inner grouped validation, MLP
optimizer settings, exact-duration bins, central inclusive Gaussian coverage,
near-zero reporting, add-one permutation p-values, artifact hashing, and the
3-fit/1-validation/2-test U4 development partition algorithm.

## Artifact-independent analysis foundations

The branch now supplies reusable code for:

- literal config-byte hashes;
- stable filter rejection codes and pre/post counts;
- saved fold/U4-partition/scaler/ridge-fit/prediction/result manifests;
- grouped inner ridge selection and OOF predictions;
- validation-only MLP layer eligibility and deterministic OOF training;
- U1 regression/binning, U2 calibration/partial correlation, and U3 grouped
  growth/reveal calculations;
- layout→trajectory bootstrap and whole-trajectory permutations;
- raw-space conversion, elapsed-time projection, alpha mapping/caps, and a
  B→A producer that self-validates against the frozen Person A contract; and
- C/D/E consumer validators that remain blocked from live use until their
  producer-owned artifacts and signoffs exist.

None of these foundations creates real results without external artifacts.

## Phase 1 evidence

- `tests/fixtures/person_b/synthetic_state_log.json`
- `tests/fixtures/person_b/synthetic_oracle_targets.json`
- `docs/analysis/fixtures/regime_a_oracle_validation.svg`
- `tests/oracle/test_regime_a_oracle.py`
- `tests/probes/test_join_and_splits.py`
- `tests/analysis/test_core_config.py`

All B fixtures are marked synthetic and forbidden for scientific use. Real
rows must validate against schema v1.0 and the accepted-manifest hash before
probe work begins. Scientific activation joins additionally require a
completed Person A run and a complete frame-by-layer/site grid.

## Verification

Phase 1 verification on July 21, 2026:

- the then-current full repository suite passed, and later compatibility
  repairs are checked by rerunning the current full suite;
- frozen schema-v1 behavior is covered alongside the versioned A-owned
  fixture correction and B-owned compatibility tests;
- the new B foundation tests cover config, filters, artifacts, intake,
  leakage-safe fits, metrics, resampling, and intervention production;
- 250 seeded oracle parameter combinations agree within `1e-6`;
- command-line target generation matches the checked synthetic fixture; and
- the SVG audit plot shows truth, last visible position, posterior mean, and
  the one/two-sigma bands across a reveal.

Person A subsequently corrected its non-scientific activation fixture from
`tau = 0, 1, 2` to the frozen 20 Hz values `tau = 0, 0.05, 0.10`. Person A owns
that compatibility correction and records its replacement handoff, run, and
accepted-manifest identities in the schema decision log and generated lineage
fixture. No Person A contract, field, unit, join key, or validator changed, and
no schema migration was required for either the correction or this B-owned
downstream table.

## Synthetic A-to-B probe bridge

Repair Chunk 2 connects the existing frozen interfaces through a CPU-only,
non-scientific probe path. `mineocclude.probes.bridge` now:

- validates Person A's activation handoff and Person B's target document with
  their authoritative validators, then creates one canonical frame row per
  `trajectory_id + model_frame_idx`;
- builds the existing layout-grouped fold manifest at frame granularity and
  propagates its `outer_fold_idx`, hash, version, and config hash to every
  layer/site activation row for that frame;
- resolves vectors exclusively by `activation_chunk_id + chunk_row_idx`, while
  checking the literal chunk bytes against the declared SHA-256, dtype, shape,
  row bounds, and exact claim coverage; and
- builds one deterministic matrix per layer/site and sends the checked Person
  A synthetic vectors, joined `mu_oracle_blocks` targets, and propagated folds
  through the existing OOF ridge harness and sealed prediction/U1 result
  artifacts.

The five-layout test evidence is derived from the checked Person A synthetic
activation chunk because the original three-frame fixture has only one layout
and cannot exercise five grouped outer folds. The copied rows receive new
explicitly synthetic test identities; the vector values remain the literal
Person A fixture values. Chunk filenames and physical row order are never
scientific identity. This path is marked `synthetic = true` and
`scientific_use = forbidden` and cannot be used as runtime or scientific
evidence.

Chunk 2 does not connect MLP fitting end to end; the existing MLP harness
remains separately tested. U2/U3 scientific analyses, real activation loading,
the C-to-A adapter, runtime evidence, and final approvals remain pending in
their assigned later work.

## Authenticated synthetic probe provenance

Repair Chunk 2B closes the remaining provenance gaps in the synthetic ridge
bridge. Matrix construction now accepts the original A activation handoff,
the original B target document, the sealed frame/fold evidence, and the
literal activation-chunk bytes. It rebuilds the join, fold propagation, and
vector loading internally. A canonical `matrix_hash` authenticates the exact
X vectors, y values, folds, layer/site identity, frame identity, source hashes,
and synthetic-use markers; caller-modified intermediate rows or vectors are
rejected rather than trusted.

Fold validation is bound to the literal `configs/analysis/core.yaml` hash and
version and recomputes the deterministic seeded layout assignment. A different
valid-looking grouping, seed, fold count, strategy, or config cannot be
resealed and accepted. Synthetic frame tables, fold manifests, propagated
rows, matrices, predictions, and results all retain `synthetic = true` and
`scientific_use = forbidden`.

Synthetic ridge predictions and U1 results are bound to the matrix hash, the
literal core-config hash, and a SHA over the B-owned bridge/split/ridge source
bytes. They record the frozen alpha grid, inner-fold count, outer-fold seed,
selected alpha per outer fold, scaler metadata, and exact training/test
memberships. This is interface evidence only. End-to-end MLP, bridged U2/U3,
live/runtime evidence, and cross-role signoffs remain pending.

## Step 1.7 authenticated A-to-B runner connection

Repair Chunk 3 makes the authenticated ridge bridge a required part of the
machine-readable Step 1.7 runner. The integration bundle now loads the literal
Person A synthetic activation chunk as a named source and authenticates both
the parsed handoff and chunk document against their exact fixture-byte hashes.
It deterministically derives the five non-scientific layouts needed by the
frozen grouped split, builds the B target document, frame table, sealed fold
manifest, layer/site matrices, OOF ridge predictions, and U1 results through
the production bridge APIs.

The join report records source/correction lineage, frame and fold evidence,
matrix hashes, complete OOF prediction/metric rows, sealed prediction and U1
artifacts, and resealed per-fold summaries of selected alpha, exact membership
hashes, fold identities, and scaler metadata. Compact saved artifacts carry
new hashes over their exact stored contents and retain the uncompacted artifact
hash only as explicitly named lineage; U1 artifacts reference the final saved
prediction-artifact hash.
`authenticated_a_b_probe_bridge` is a required integrity check: stale source
bytes, invalid bridge metadata, or any fail-closed bridge rejection fails the
overall Step 1.7 status. All derived evidence remains `synthetic = true` and
`scientific_use = forbidden`; this connection does not create runtime or
scientific evidence and does not add MLP or U2/U3 execution.
