# Person B Phase 1: Scientific Methods Foundation

Status: implemented against universal schema `1.0`; frozen before live results.

## Scope

Person B Phase 1 supplies the dependency-light scientific foundation needed
before real activation fitting:

- a named target and analysis configuration;
- two independent exact Regime A oracle implementations;
- synthetic state and target evidence;
- an explicit-key A-to-B activation/target join;
- deterministic five-fold layout grouping; and
- tests that fail closed on leakage, cardinality, unit, and manifest errors.

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

The remaining required inputs inherit their frozen universal names directly:
`visibility`, `v` (blocks/s), `q` (blocks squared/s), `duration` (seconds),
`layout_id`, and `trajectory_id`. Person B does not introduce aliases for
these fields.

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
`tau`, changes to `v` or `q` within an occluded run, mixed manifests, mixed
model/preprocess identities, and malformed document envelopes.

## Input boundary

The JSON consumed by `build_oracle_targets.py` is a B-owned derived-state
table that carries the frozen schema-v1 universal row identity. It is not a
claim that Person C's raw trajectory package already has this flat shape. A
validator-backed C/A-to-B adapter is still required before real state logs are
used; any missing real-data field or meaning must be handled as an explicit
adapter or migration decision, never by silent repair.

The checked B oracle fixture uses physically coherent consecutive 20 Hz ticks.
The A-to-B compatibility test separately derives non-scientific target inputs
from Person A's frozen activation fixture, without editing that fixture.

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

- the original 112 schema-v1 contract/integration tests still pass;
- 34 Person B config, oracle, CLI, join, split, and leakage tests pass;
- 250 seeded oracle parameter combinations agree within `1e-6`;
- command-line target generation matches the checked synthetic fixture; and
- the SVG audit plot shows truth, last visible position, posterior mean, and
  the one/two-sigma bands across a reveal.

No frozen Person A contract, field, unit, join key, validator, or fixture was
modified. No schema migration was required for this B-owned downstream table.
