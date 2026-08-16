# Regime A′ Prospective Development Authority v0.2 — repaired draft

**Status:** `DRAFT_REPAIRED_UNFROZEN_NOT_AUTHORIZED`  
**Class:** `DEVELOPMENT_ONLY`  
**Immutable forensic base:** `db2e110549856a465ae517c17438d4d248d9657b`

This draft does not authorize Stage 1, Stage 2, Regime A′, or confirmatory
collection. Historical results and freeze artifacts are unchanged. The
runtime source commit and authorization hashes must be materialized by the
independent pre-outcome and authorization receipts after freeze. This avoids a
self-referential commit hash while still requiring exact HEAD, source-byte, Git
mode, authority, manifest, and run-namespace bindings before execution.

## Stage 1: measurement versus acceptance

Stage 1 has eight runs: two directions × two scenes × two predeclared roles.
For each direction and scene, replicate 1 is the transition-measurement run and
replicate 2 is held-out validation. This is the minimum full-factorial design
that does not define and validate the visibility band on the same WALL run.
All four trajectories per direction feed both temporal methods.

Temporal alignment is measured separately by direction using:

1. a causal nonnegative FIR group-delay fit; and
2. independently executed derivative cross-correlation.

Each method emits its own estimate, confidence interval, trajectory identities,
and status. Qualification requires the two predeclared 95% intervals to
overlap. This statistical consistency rule has no invented tick tolerance.
The historical estimate `3.363631073825902` and interval
`[3.1850024634276997, 3.5422596842241045]` are reference evidence only. They
are not a prospective acceptance envelope. CI width is measured and reported;
there is no numerical CI-width gate. The causal FIR must beat the best pure
delay and must contain more than one positive tap.

## Visibility and physical support

The unsupported `0.52` silhouette half-extent, fixed transition guard, fixed
hidden onset, 320-row minimum, and 0.25-block endpoint/gap tolerances are
removed. Frozen forensics support only an approximate `0.6–0.8` silhouette
range, retained solely as a historical reference.

On each direction's predeclared WALL measurement run, Stage 1 measures:

- the point-hidden interval;
- the detector-absent rendered interval;
- their stable-occluded intersection;
- both complete partial-transition bands; and
- both stable-visible intervals.

Those measured intervals are then applied unchanged to the held-out WALL run.
Partial rows are reported and never scored. NO_WALL is stable-visible only when
actual physical and rendered evidence establishes point visibility, projection
inside the frame, a present render frame, valid identity, in-support position,
and resolved alignment. Scene identity alone is insufficient.

Projection validity is reconstructed from raw screen coordinates and integer
token-cell coordinates using the authority-bound frame and visual-token-grid
dimensions. Screen bounds are half open, `[0,width) × [0,height)`, and the
token cell must equal the floor-mapped screen cell. A supplied in-frame Boolean,
wrong dimensions, or stale token summary cannot override contradictory raw
coordinates.

Every sample carries both world-x and `wall_relative_x = world_x - 0.5`.
Complete expected frame/path coverage and the frozen lane bounds are required.
Endpoint, gap, and sample count summaries are measurements, not gates.

Detector qualification remains prevalence-independent: held-out stable-visible
false negatives and stable-occluded false positives must both be zero, with at
least 60 observations per direction and class. Sixty zero-error observations
give the exact one-sided 95% upper error bound `0.04870291331009746 < 0.05`.

Each held-out WALL run must designate exactly 19 hidden rows. Every prohibited
class is separately counted and must be zero: point-visible,
partial-transition, detector-visible, clock-unresolved, out-of-support,
ambiguous/invalid identity, unresolved runtime/provenance, invalid path/state,
and malformed/missing.

## Runtime, provenance, and restart

The runner independently probes branch, HEAD, Java/JDK, renderer, Mesa, Xvfb,
Minecraft/mod/JAR, detector configuration, camera authority, wall/layout
identity, and apparatus-critical file hashes. It reuses the frozen renderer and
path machinery. Evidence builders only copy signed probe receipts; they cannot
create successful runtime, path, or durability flags.

The runtime source receipt covers the complete local import closure used by
projection, capture packaging, noise generation, extraction, and readout. Both
Stage 1 and Stage 2 independently rehash those source bytes rather than trusting
declared hash summaries.

Every completed unit binds authority SHA, manifest SHA, source commit, run
namespace, unit identity, local receipt SHA, remote checksum-manifest SHA, and
the remote object inventory. Resume downloads and hashes the remote manifest
and checks every remote object before reuse. A stale local state or missing
remote object causes no reuse. Incomplete units receive at most three identical
attempts. A verified durable unit is never recollected.

Stage 1 always emits a terminal PASS/FAIL decision and stops. It never starts
Stage 2.

## Stage 2 barrier and manifest finalization

The current Stage-2 artifact is intentionally a draft template. Exact target
windows cannot be frozen until Stage 1 measures the physical hidden interval.
After a frozen Stage-1 PASS, a deterministic materialization step selects the
predeclared 19-row windows from the measured direction-specific hidden bounds,
constructs expected labels with the qualified direction-specific causal FIR,
checks corrected headroom, and produces a Stage-2 manifest for a separate
freeze.

Stage 2 requires a distinct authorization receipt binding all of:

- authority SHA;
- Stage-1 manifest SHA;
- Stage-1 evidence artifact SHA;
- genuine Stage-1 decision artifact SHA and exact PASS status;
- materialized Stage-2 manifest SHA;
- prospective source commit;
- expected Stage-2 run namespace; and
- the independently verified pre-outcome provenance receipt SHA; and
- the canonical authorization-payload hash.

The bound Stage-1 evidence artifact must exist on disk and independently
reproduce the exact Stage-1 decision through the frozen evaluator. A
structurally convincing all-PASS decision is insufficient.

Edited PASS text, a missing decision file, stale/copied receipts, wrong hashes,
wrong commit, wrong namespace, or the draft template cannot authorize Stage 2.

## Stage 2 labels and gates

Model targets are independently reconstructed from captured server-state
history through the frozen Stage-1 direction-specific causal FIR. Raw
same-numbered server state is never a label. The reconstructed labels must
exactly match both capture receipts and the materialized manifest.

Before extraction, all 50 captures and all 25 WALL/NO_WALL pairs must pass
durability, identity, exact paired path/state, alignment, stable visibility,
physical support, 19-row hidden/visible-control validity, zero contamination,
runtime provenance, and pair coverage. Layer 4 only is then extracted.

Physical summaries are reconstructed from the durable server-state and
visibility files. Every direct backend phase revalidates predecessor receipt
bindings and remote durable objects, so local PASS/completion summaries cannot
bypass capture → gates → extraction → BEST-K → FULL → terminal order.

The 25 identities preserve the frozen five-fold × five-phase design: every
outer fold contains phase offsets `[0,3,6,9,12]` exactly once, with the frozen
13 LEFT_TO_RIGHT / 12 RIGHT_TO_LEFT assignment. Fold and phase may not share a
single modulo assignment or otherwise become confounded.

BEST-K controls. FULL is non-rescuing. Each scene must have strictly positive
macro R² and whole-trajectory bootstrap lower R², and RMSE no greater than
`0.15560477763641264`, preserving the controlling `2 × P2 BEST-K` formula with
the corrected frozen P2 value. WALL BEST-K must strictly beat the frozen
outer-training time baseline. The time baseline uses
`[1, direction, tau, tau×direction]`, trains on outer-training `tau<=15`, and
must have trajectory-equal macro R² `<=0.10` on `tau<=15`.

Headroom preserves the controlling formulas using corrected P2 BEST-K:
minimum each-trajectory SD `0.15560477763641264` (2×) and minimum candidate
median SD `0.23340716645461895` (3×).

No development outcome authorizes confirmatory collection or may enter a
confirmatory cohort.

## Authority state

```text
STAGE_1_COLLECTION_AUTHORIZED=false
STAGE_2_COLLECTION_AUTHORIZED=false
REGIME_A_PRIME_COLLECTION_AUTHORIZED=NO
CONFIRMATORY_COLLECTION_AUTHORIZED=false
```
