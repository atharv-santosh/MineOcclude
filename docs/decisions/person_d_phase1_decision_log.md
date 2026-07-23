# Person D Phase 1 Decision Log

Dated deviations, corrections, and approvals for Person D's baseline/control
work, in the format used across the project's decision logs. Entries are
append-only; a correction never edits a prior entry in place.

**Current architecture notice (2026-07-22):** the merge/vendoring entries
below are retained only as historical decision evidence and are superseded by
the final correction at the end of this log. The current
current integrated authority is `integration/mvp` at
`80d41c5ca0e341263a7b0c683fae4b51be376c55`.
D consumes the authoritative A/B/C/E implementations from that checkpoint and does
not own or vendor copies of their contracts, folds, probes, analysis code, or
intervention mathematics.

## 2026-07-21 -- Branch merge to access Person B's contract code

**Decision:** Merge `origin/role/person-b-methods` into
`role/person-d-baselines`.

**Why:** D's exported baseline documents must pass Person B's real
`mineocclude.contracts.analysis_inputs.validate_baseline_input` validator, and
D's fold assignment must match B's `mineocclude.probes.splits` algorithm
exactly. Both live only on B's branch. Confirmed with the user first since a
branch merge changes local git history; the merge only affects
`role/person-d-baselines` locally and does not alter `role/person-b-methods`
or push anything.

**Effect:** `src/mineocclude/{contracts,oracle,probes,metrics,intervention,
analysis}` and their fixtures/tests became available for D's code to import
and test against directly, rather than being reimplemented or paraphrased.

**Superseded 2026-07-21 (same day):** replaced by a vendored-file approach --
see the two entries below. The merge pulled in Person B's full commit
history onto D's branch, which would have shown up as D-authored commits in
any future PR diff against `main`.

## 2026-07-21 -- Replaced the branch merge with a minimal vendored-file copy

**Historical status:** `SUPERSEDED` by the 2026-07-22 integration-foundation
correction. This is not the current repository architecture.

**Decision:** Reset `role/person-d-baselines` back to its original pre-merge
tip (bare `Initial commit`, just `README.md`) and instead copy in only the
13 files D's baseline code actually imports, as plain untracked files added
under D's own future commits:
`contracts/{__init__,identity,analysis_inputs}.py`,
`analysis/{__init__,config,manifests,coordinates}.py`,
`probes/{__init__,ridge,splits}.py`,
`intervention/{__init__,directions}.py`, plus `mineocclude/__init__.py`.

**Why:** A branch merge means B's commits appear in D's own history; if D's
branch is later diffed against `main` or opened as a PR, those commits would
look like they were authored on D's PR. Copying just the needed files keeps
D's branch self-contained and its future commit history honest about what D
actually wrote, at the cost of maintaining small vendored copies until a
real team-wide integration branch exists. Confirmed with the user before
doing the reset, since it discards commits from local branch history (though
nothing had been pushed, so nothing external was at risk).

**Follow-up needed:** the three vendored `__init__.py` files
(`analysis`, `probes`, `intervention`) are intentionally *not* full copies of
B's real package `__init__.py` files -- they only re-export the names their
vendored submodules need, to avoid pulling in further undvendored
dependencies (`bridge.py`, `join.py`, `mlp.py`, `filters.py`, `outputs.py`,
`doses.py`, `producer.py`). Reconcile against B's real `__init__.py` files
at actual integration time rather than treating these as authoritative.

## 2026-07-21 -- Pinned the vendored copy to the exact commit already tested against

**Historical status:** `SUPERSEDED` by the 2026-07-22 integration-foundation
correction. Commit `08a6b1e` is not D's current contract authority.

**Decision:** Vendored files were copied from commit `08a6b1e` (the specific
commit merged and tested against earlier in the session), not from
`origin/role/person-b-methods`'s current tip.

**Why:** Between the original merge and this cleanup, `origin/role/person-
b-methods` moved (new commits landed, including a tightened
`validate_baseline_input` that requires additional `feature_access`/
`legal_information` fields per baseline family). Vendoring from the moving
branch tip on the first attempt broke every export test with a schema
mismatch D's code was never designed against. Pinning to the exact commit
already merged and tested keeps behavior identical to everything already
built; picking up B's newer, stricter contract is a deliberate follow-up
task, not something that should happen silently as a side effect of a git
cleanup.

**Follow-up needed:** re-check `origin/role/person-b-methods` for the
`feature_access`/`legal_information`/`BASELINE_FAMILY_CONTRACTS` additions
before the next real handoff to Person B -- D's export documents will need
to satisfy the newer contract once it is the one actually in force.

## 2026-07-21 -- Target-name reconciliation

**Decision:** Renamed the provisional baseline target names `mu_blocks` /
`log_sigma` to Person B's frozen canonical names `mu_oracle_blocks` /
`log_sigma_oracle` (`docs/contracts/person_b_oracle_target_v0_1.md`,
`configs/analysis/core.yaml`).

**Why:** `interface.py` was explicitly marked provisional pending B's real
schema; that schema is now available, so the placeholder names should be
reconciled rather than left to drift.

**Affected files:** `interface.py`, `last_seen.py`, `constant_velocity.py`,
`time_only.py`, and every baseline module written after this point.

## 2026-07-21 -- Explicit-feature baseline spec correction

**Decision:** The explicit-feature ceiling baseline uses last-seen position,
*estimated* visible-window velocity, tau, duration, and two declared
interaction terms -- not the scripted `v`/`q`.

**Why:** An initial design mistakenly planned to give this baseline the
privileged scripted `v`/`q` (confusing it with a ceiling built from *true*
belief ingredients). Re-reading the roadmap's D2 comparison table ("Explicit
features | Last-seen position, estimated speed, elapsed time; declared
interactions | Ceiling/reference for known belief ingredients") caught this
before any code shipped. Privileged scripted `v`/`q` is reserved for
`known_q_analytic.py`, which is explicitly labeled a non-fair oracle-ceiling
reference.

## 2026-07-21 -- Added two baselines not in the initial scope

**Decision:** Implemented `visible_history_q.py` (fair, per-fold q_hat
estimated from pooled pre-occlusion residuals) and `known_q_analytic.py`
(privileged oracle-ceiling reference using the true scripted q), in addition
to the originally planned last-seen/constant-velocity/time-only/shuffled/
explicit-feature/raw-pixel set.

**Why:** The roadmap's D2 table and Person D's owned-files list both name
these explicitly ("visible-history-q spread, known-q analytic reference") as
separate baselines from explicit-feature. They were missing from the initial
plan, which was built from a paraphrased summary rather than the primary
roadmap document; caught on cross-checking the roadmap PDF directly.

## 2026-07-21 -- U4 control matrix scoped as an audit tool, not a fitting tool

**Decision:** `u4_control_matrix.py` builds the expected set of control
conditions (alpha=0, seeded random direction, orthogonal direction, wrong
layer, wrong timestep) per held-out event/seed, and audits completeness,
norm-matching, and orthogonality -- it does not derive Person B's real
fitted direction or inject anything.

**Why:** Direction fitting is Person B's ownership
(`mineocclude.intervention.directions`/`doses`/`producer.py`); injection is
Person A's (`src/mineocclude/intervention/inject.py`). The roadmap's Day 5
Person D block is titled "Verify the U4 control matrix," and D's role
reference lists "Check that the random direction is norm-matched... Compare
completeness and paired event/seed coverage... Report control failures" --
all audit language, not derivation language. D's module reuses B's
`mineocclude.intervention.directions` utilities (`dot`, `l2_norm`,
`normalize`) for the norm/orthogonality checks rather than reimplementing
vector math.

## 2026-07-21 -- Random-weight MineWorld baseline implemented, not stubbed

**Decision:** `random_weight.py` is a full thin wrapper around
`raw_pixel.fit_predict_raw_pixel` (relabeling `baseline_name`), rather than a
bare `NotImplementedError` stub.

**Why:** The roadmap says to "leave random-weight MineWorld for Week 2... but
keep the interface ready." The ridge/fold fitting logic does not depend on
whether a feature vector came from pixels or activations, so implementing the
real fitting path now (with no real random-weight activations to pass in
yet) satisfies "interface ready" more usefully than a stub that would need to
be rewritten later. Real use remains blocked on Person A's Week 2 handoff of
random-weight-checkpoint activations.

## 2026-07-22 -- Supersede vendoring with the finalized integration foundation

**Decision:** Base `repair/person-d-phase1` on the finalized A+B+C
`integration/mvp` checkpoint at `d38835c`. Person D owns only
`src/mineocclude/baselines/` and its D-specific tests, fixtures, status, and
decision records. D directly imports the current A/B/C authorities already
present in the integration foundation; D does not vendor, pin, fork, or own
copies of those files.

**Supersedes:** the 2026-07-21 vendored-file and `08a6b1e` pinning decisions.
They remain above solely as append-only history and must not be used to infer
the current architecture.

**Contract correction:** `mineocclude.baselines.export` now builds documents
from Person B's current `BASELINE_FAMILY_CONTRACTS` and validates them with
Person B's current `validate_baseline_input`. Unsupported families and target
combinations fail closed; D does not alter B's validator.

**Fold correction:** D no longer calls B's assignment algorithm to construct
folds. `attach_b_fold_assignments` requires a saved sealed B-owned
`fold_manifest`, validates it with B's `validate_fold_manifest`, requires
exact `trajectory_id + model_frame_idx` coverage, and copies the recorded
folds unchanged. Phase 1 evidence uses
`tests/fixtures/person_d/synthetic_b_fold_manifest.json`; this is not a real
scientific fold artifact.

**Evidence:** `docs/baselines/person_d_phase0.md`,
`src/mineocclude/baselines/export.py`, `tests/baselines/test_export.py`, and
the 41-test D suite recorded on 2026-07-22.

**Approval status:** engineering compatibility is verified by current
contracts and synthetic tests. Formal Person A/Person B human approval of the
D handoff is still pending and is not implied by this entry.

## 2026-07-22 -- Complete D Phase 1 technical foundation and repository review

**Decision:** Make `mineocclude.baselines.spec` the single D-owned authority
for the versioned Phase 1 BaselineSpec and prediction row. Put exact legal
feature selection in `baselines.firewall` and run the existing last-seen and
constant-velocity implementations through one `baselines.harness` boundary.

**External ownership:** B's frozen config supplies target vocabulary, B's
sealed fold validator supplies membership, and B's regression metric API
supplies evaluation. A's schema `1.0`, frame key, accepted-manifest identity,
and preprocessing hash remain external provenance. D does not reproduce any
of those definitions.

**Evidence:** `tests/baselines/test_phase1_foundation.py` covers strict spec
fields, illegal features, pre-estimator rejection, identity/fold coverage,
row-order independence, non-mutation, two-baseline identical held-out keys,
strict predictions, and direct B metric invocation. The repository-side
interface review is `docs/baselines/person_d_schema_v1_review.md`.

**Approval status at the time of this entry:** repository compatibility was
**TECHNICALLY VERIFIED** and formal human approval from Persons A and B was
**PENDING**. The following entry records the later checkpoint-scoped approval;
this historical entry did not invent or imply it early.

## 2026-07-22 -- Record D1.5 human handshake approval

**Decision:** Record the project coordinator's confirmation that Persons A and
B, together with the other role owners, reviewed and approved the Phase 0/1
interface meanings and compatibility at
`integration/mvp@80d41c5ca0e341263a7b0c683fae4b51be376c55`.

**Evidence:** the central checkpoint-scoped record is
`docs/contracts/schema_v1_0_signed_record.md`; the technical D review remains
`docs/baselines/person_d_schema_v1_review.md`.

**Scope:** this completes the D1.5 A/B handshake for that exact Phase 0/1
checkpoint. It does not approve real-data baseline execution, final scientific
comparisons, or later-phase methods. The earlier pending statements above are
retained as historical status at the time they were written.

## 2026-07-22 -- Reconciled local branch after an out-of-session history rewrite

**Context found:** between the 2026-07-21 session and this one, `origin/
role/person-d-baselines` was force-updated to match `integration/mvp`
(current tip `a699797`, "Record Phase 0-1 cross-role signoffs"), replacing
the vendored-file commit pushed at the end of the prior session. That prior
commit is preserved, not lost, at `origin/backup/person-d-before-final-sync`.
A parallel `origin/repair/person-d-phase1` branch shows the new Phase 0/1
foundation (`BaselineSpec`, legal-input firewall, common harness) was built
independently of the prior session's work.

**Decision:** adopt the current official state as-is. Local
`role/person-d-baselines` was reset (`git reset --hard
origin/role/person-d-baselines`) to match; the prior session's vendored-file
commit is not merged forward or reconciled against this one. Confirmed with
the user before resetting, since this discards a locally-committed history
in favor of the remote's, though nothing of the prior work is actually lost
(it remains reachable via the backup branch if ever needed).

**Why:** the new foundation is the one the rest of the team (and whatever
integration/repair process ran) is building on top of; maintaining two
divergent Person D implementations would only create confusion at the next
real integration point.

## 2026-07-22 -- Isolated all current test failures to a Python-version mismatch

**Finding:** a full-suite run on the current official state showed 23
failing tests. Traced every one to two root causes, both 3.10-only syntax
running under this machine's Python 3.9: `zip(..., strict=True)` in
`mineocclude.analysis.synthetic_chain` (Person B) and
`mineocclude.vision.homography`/`ssim` (Person E), and `Path.write_text(...,
newline=...)` in a Person B plotting script. None of the 23 failures are in
Person D's own code; the one D-relevant integration test
(`test_current_d_and_e_boundaries_use_real_validators`) fails only because it
depends on B's `run_synthetic_analysis_chain`, which hits the same `zip`
issue upstream of D's own boundary check.

**Attempted fix:** installed `python@3.10` via Homebrew, but the resulting
interpreter's `pyexpat` module fails to load (`_XML_SetAllocTrackerActivationThreshold`
symbol missing from the system `libexpat`), traced to this machine's Command
Line Tools being older than its macOS version. Fixing that needs `sudo` and
an Apple Command Line Tools update -- deferred rather than done silently as
a side effect of chasing test failures; the user can update Command Line
Tools independently via System Settings whenever convenient.

**Effect:** none of Person D's own code needed a Python-version fix. The
three real gaps fixed below were found by reading the code directly, not
from the pytest failures.

## 2026-07-22 -- Fixed the three PDF-flagged Phase 2-4 gaps

**Step 2.1 (grouped shuffled-label floor):** `shuffled.py` aligned a
recipient frame to its donor by *position within a locally sorted list*,
not by explicit `model_frame_idx`. If donor and recipient trajectories ever
have different excluded/missing-frame patterns, positional alignment
silently pairs the wrong frames. Fixed: `TrajectoryTargets` is now keyed by
explicit `model_frame_idx` (`Mapping[str, Mapping[int, Optional[float]]]`,
was `Mapping[str, Sequence[Optional[float]]]`) and a donor missing that
exact frame index now correctly falls out as not applicable, with a reason
code (previously missing entirely). This is a breaking change to
`apply_grouped_shuffle`'s second argument shape; nothing else in the repo
called it yet, so no other caller needed updating.

**Step 3.4 (visible-history-q spread baseline):** `visible_history_q.py`
silently took whichever `fold` value it saw first per trajectory
(`dict.setdefault`), masking any upstream bug that assigned one trajectory
to two folds. Fixed: added `VisibleHistoryQError`, raised the moment a
trajectory's contexts disagree on `fold`, rather than silently resolving to
the first-seen value.

**Step 4.5 (missingness/exclusion audit):** no consolidated tabulation
existed across baselines/conditions; only scattered per-row reason strings.
Added `mineocclude.baselines.missingness.build_missingness_exclusion_report`,
which tabulates accepted/missing counts by (baseline, target, layout,
regime, duration bin) and flags any non-applicable row whose
`fit_metadata` carries no `reason` key as a silent exclusion. Running it
against every real D baseline over a synthetic multi-layout fixture found
one such silent exclusion -- `shuffled.py`'s non-applicable rows never
carried a reason -- fixed in the same pass as the Step 2.1 change above.

**Evidence:** `tests/baselines/test_shuffled.py`,
`tests/baselines/test_visible_history_q.py`
(`test_fit_predict_visible_history_q_rejects_conflicting_fold_assignments`),
`tests/baselines/test_missingness.py`. Full baseline suite passing after
these changes; no regressions in the wider repo suite (same 23
pre-existing, unrelated failures before and after).

**Scope note:** Phase 5 (Steps 5.1-5.4, the real end-to-end pilot) remains
blocked on external data -- an accepted real trajectory, Person B's real
folds/targets, and Person A's real frames/activations do not exist yet. No
amount of D-side code changes substitutes for that; the three fixes above
are the finishable, non-blocked portion of the outstanding gaps.
