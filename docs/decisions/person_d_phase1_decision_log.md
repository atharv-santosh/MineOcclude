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

## 2026-07-27 -- Diagnosed and closed the zero-applicable-row episode in the real pilot preview

**Classification: (a) LEGITIMATE, not a defect.** `layout_05_ep9422`'s
`capture_package_v0_1.json` (`origin/role/person-c-data@260784e`) records
`"condition": "occluder_only_no_sheep"`. Direct inspection of the real row
streams confirms this at the data level, not just the manifest label: all
200 `visibility.jsonl` rows are `visibility="occluded"` and all 200
`server_state.jsonl` rows have `state.target_present=false` -- there is no
visible-target frame anywhere in the episode.

**Line-level trace (`capture_ingest.py::build_contexts_from_capture`):**
`last_seen_position` is initialized to `None` (line 116) and is only ever
assigned inside the `if is_visible:` branch (line 140). Since
`visibility_value == "visible"` is never true for this episode, that branch
never executes for any of the 200 frames, so `last_seen_position_blocks`
stays `None` on every resulting `TrajectoryContext` -- confirmed directly
(not assumed) via
`tests/baselines/test_no_sheep_episode_missingness.py::test_build_contexts_from_capture_never_fabricates_a_position`.
`last_seen.py`/`constant_velocity.py` therefore correctly mark every row
non-applicable with `prediction=None`; this is the adapter behaving exactly
as documented, not a join/parse failure.

**Fix (legibility, not baseline logic):** per instruction, no baseline math
changed. `scripts/run_real_pilot_baseline_preview.py::_summarize` now
surfaces, for any baseline/target with non-applicable rows, a
`"missingness"` block containing
`non_applicable_reason_counts` (new
`mineocclude.baselines.missingness.summarize_non_applicable_reasons`,
counting each `fit_metadata["reason"]` string) and `has_silent_missingness`
(existing `build_missingness_exclusion_report`, unchanged). This is the same
Step 4.5 seam every other D baseline is already checked against, reused
rather than reimplemented. A wholly-non-applicable episode in the preview
report now reads as an explained `0/200` with its exact reason text, instead
of a bare, unexplained zero.

**Regenerated evidence:** re-ran the preview script against the same 17
real episodes; every numeric field (`applicable_rows`, `total_rows`,
`prediction_mean/min/max`) is byte-identical to the prior committed report
for all 17 episodes -- confirmed by direct diff before overwriting. Only the
new `missingness` block was added, and only where non-applicable rows exist.
`docs/status/person_d_real_pilot_baseline_preview.json` updated in place.

**Evidence:** `tests/fixtures/person_d/real_capture_no_sheep_excerpt/`
(real excerpted frames 0-19 of `layout_05_ep9422`, with provenance README),
`tests/baselines/test_no_sheep_episode_missingness.py` (3 new tests: raw
stream confirms no-sheep condition; contexts never fabricate a position;
both baselines are wholly non-applicable but zero silent exclusions).
Baseline suite: 79 -> 82 passing. Repo-wide: same 13 pre-existing A/B-owned
failures in `test_synthetic_analysis_chain.py`/`test_synthetic_pipeline.py`
before and after, confirmed unchanged by direct re-run.

## 2026-07-27 -- Built the Step 4.3 no-wall positive-control statistical gate

**Gap:** Step 4.3 was marked COMPLETE, but `controls.audit_no_wall_control`
only ever checked the structural half (every no-wall frame really is
visible with `tau=0`). The scientific half -- fit the frozen
visible-position ridge on no-wall rows and require held-out R^2 >= 0.50
with a bootstrap CI strictly above zero -- did not exist anywhere. A
repo-wide grep for `0.50` found only `leakage.py`'s unrelated
`r2_threshold=0.1`.

**Decision:** Added `src/mineocclude/baselines/positive_control_gate.py`
as a sibling module to `controls.py`, not an addition to it.
`controls.py` deliberately has no numpy/ridge/fold-manifest dependency for
its lightweight structural audits; this gate pulls in Person B's real
`probes.ridge.fit_ridge_oof`, `metrics.u1_mean.regression_metrics`, and
`metrics.resampling` (`hierarchical_bootstrap_indices` +
`bootstrap_confidence_interval`) plus `export.attach_b_fold_assignments`
for fold membership. D calls these directly; nothing here reimplements or
paraphrases B's ridge, metric, or resampling math. The ridge alpha grid,
inner-fold count, split seed, and the bootstrap's resample count/seed all
come from `configs/analysis/core.yaml` via `analysis.config
.load_core_analysis_config()` -- none of those numbers are invented or
hardcoded independently in this module.

**Fail-closed contract:** `evaluate_no_wall_positive_control_gate` takes a
mandatory (no-default) `data_provenance` argument. Only the exact literal
`REAL_NO_WALL_DATA_PROVENANCE` unlocks a scientific PASSED/FAILED verdict;
any other value -- including every synthetic fixture in this test suite --
returns `status="BLOCKED"` with every numeric field (`r2`, `ci_low`,
`ci_high`, `fold_count`, `resample_count`, `seed`) left `None` before any
ridge is even fit. There is no boolean shortcut (e.g. `is_real=True`) that
could default to true; a mislabeling has to be an explicit, visible literal
in the caller's own code. This mirrors the project's existing convention
for real-vs-not provenance (`"scientific_use": "forbidden"` in the real
pilot preview, `IS_FAIR_BASELINE` in `known_q_analytic.py`) rather than
inventing a new enforcement mechanism.

**Current status:** `BLOCKED`. Real no-wall rows, a real Person B fold
manifest, and real oracle targets do not exist anywhere in this repository
yet (same blockers tracked throughout this log and
`docs/status/person_d_real_pilot_baseline_preview.json`). The gate cannot
report PASSED or FAILED until they do.

**Evidence:** `tests/baselines/test_positive_control_gate.py` (10 tests:
BLOCKED on non-real provenance regardless of signal quality, a clean
PASSED, a sub-threshold-R^2 FAILED, a CI-straddling-zero FAILED with R^2
above threshold, structural-audit/empty-input/missing-target/invalid-fold-
manifest error paths, and a "BLOCKED never carries a numeric field" check).
All four PASSED/FAILED/BLOCKED test scenarios use the caller-declared real
literal deliberately, on the same synthetic fixture already used elsewhere
in Phase 4, to exercise the arithmetic -- none of this is a claim about
real data. Persisted evidence:
`docs/status/person_d_step_4_3_positive_control_gate.json`
(`scripts/run_step_4_3_positive_control_gate.py`), explicitly marked
`"scientific_use": "forbidden"` and reporting `BLOCKED`, run against the
same synthetic fixture with an honestly non-real `data_provenance` label.

**Follow-up needed, not done here:** Phase 4's other three SAVE
deliverables (`split_integrity.json` from `leakage.audit_layout_fold
_isolation`, a metadata-leakage report from `leakage
.check_metadata_predictability`/`audit_identity_not_filename_derived`, and
a missingness-exclusion report from `missingness
.build_missingness_exclusion_report`) exist as functions with test
coverage but have never been written to disk as an artifact. Persisting
them is a separate, still-open task.

Baseline suite: 82 -> 92 passing. Repo-wide: same 13 pre-existing
A/B-owned failures, confirmed unchanged by direct re-run.

## 2026-07-27 -- Reconciled stale documentation across three D docs

**Found:** `docs/baselines/person_d_phase1.md` still said "Formal human
approval by Persons A and B remains pending," and `PERSON_D_ISSUE.md` still
listed that same signoff as an open, unchecked blocker. Both were stale --
`docs/baselines/person_d_phase0.md` already correctly recorded it as
**COMPLETE**, matching the central record in
`docs/contracts/schema_v1_0_signed_record.md`
(`APPROVED_FOR_PHASE_1_FREEZE` at `80d41c5ca0e341263a7b0c683fae4b51be376c55`).
Test counts also disagreed: phase0.md said 74, phase1.md said 67; the
actual count (after the two entries above) is 92.

**Fixed:**
- `person_d_phase1.md`: replaced the stale pending-approval line with the
  same COMPLETE-for-that-checkpoint language phase0.md already used, plus
  an explicit note that it does not cover real-data baselines or the Step
  4.3 gate. Updated the test count to 92 (dated 2026-07-27). Added the
  three modules missing from the module map entirely
  (`missingness.py`, `capture_ingest.py`, `positive_control_gate.py`).
  Added a "Step 4.3 status: implemented, UNEVALUATED" section stating the
  gate's actual current status is BLOCKED, not passed.
- `person_d_phase0.md`: updated the record date, the test count (74 -> 92),
  and the milestone table -- added an explicit Step 4.3 row (UNEVALUATED /
  BLOCKED pending real no-wall data) and a note on the real-capture preview
  under the real-data-baselines row, so "implemented" is never conflated
  with "passed" anywhere in this doc either.
- `PERSON_D_ISSUE.md`: checked off the A/B signoff blocker with the same
  COMPLETE-for-that-checkpoint qualification (not a blanket signoff on
  everything downstream); added the real-capture ingest adapter and the
  Step 4.3 gate to the MVP work checklist, both marked complete with their
  actual current status (non-scientific preview; BLOCKED) stated inline
  rather than implied by the checkmark alone.

**Why the qualification matters everywhere it appears:** the A/B signoff is
real and complete for one specific frozen interface checkpoint. Repeating
it without that scope note (as the stale copies did, if left uncorrected in
one direction, or as a blanket "everything is approved" if overcorrected in
the other) would misstate what was actually approved. Every corrected
occurrence in this pass keeps the same explicit checkpoint-scoped wording
phase0.md already used, rather than inventing a new phrasing per file.

## 2026-07-29 -- Phase 4 Step 4.1 registry v2 handoff preparation package

**Decision:** Build the Step 4.1 scientific-baseline handoff preparation
package under
`docs/status/person_d_phase4_step4_1_registry_v2_handoff_v0_1/`, covering
everything independent of Person B's still-unavailable fold manifest and
oracle-target document. Two new modules:
`src/mineocclude/baselines/scientific_readiness.py` (the exact scientific
baseline input contract: fold identity, oracle identity, accepted-context
identity, deterministic artifact IDs, direct-input relationships) and
`src/mineocclude/baselines/registry_v2_artifacts.py` (D's own
owner-status/exact-artifact-authorization/manifest/verification-receipt
schemas, built on Person B's real `analysis.manifests.seal_artifact`
sealing primitive).

**Ownership boundary respected:** Person E owns the project's actual
Immutable Registry v2 system (`docs/contracts/immutable_registry_v2.md`,
`role/person-e-operations`). Per the task's explicit instruction not to
merge or integrate other role branches, `registry_v2_artifacts.py` does
not vendor or import E's code; it defines D's own independent artifact
types mirroring the same four handoff concepts for exactly D's own
baseline-output domain. This is a deliberate parallel construction, not a
copy -- documented explicitly in the module's own docstring so a future
reader does not mistake it for E's system or attempt to merge the two.

**Fail-closed design:** `validate_scientific_baseline_readiness` requires
an explicit, no-default `candidate_scientific_use` argument; only the
literal `"accepted"` unlocks a READY verdict. It collects every violation
(rather than stopping at the first) into a `ScientificReadinessFinding`.
Confirmed the four item-8 conditions independently: `UNASSIGNED_FOLD`,
missing sealed B fold identity, missing B oracle identity, and
`scientific_use=forbidden` each block on their own, and can co-occur
(`test_multiple_simultaneous_violations_are_all_reported`).

**Key finding, empirically verified rather than assumed:** constructed the
most structurally valid synthetic oracle-target document buildable
*without* Person B's real coordinate-frame signoff (using the same
`fixture_metadata.synthetic=True, scientific_use="forbidden"` bypass
`mineocclude.oracle.schema.validate_oracle_target_document` itself
defines) and confirmed it still reports `BLOCKED`, for exactly one reason
-- `scientific_use=forbidden` -- not any structural defect
(`test_even_the_best_case_synthetic_fixture_is_blocked`). This proves the
gate cannot be satisfied by any synthetic fixture this project's own
oracle schema will currently accept; READY is only reachable once Person
B's real coordinate-frame signoff and literal-config-hash binding exist.
No test in this suite claims or attempts to demonstrate a READY verdict,
by design -- see `test_scientific_readiness.py`'s module docstring.

**Evidence:** `tests/baselines/test_scientific_readiness.py` (11 tests),
`tests/baselines/test_registry_v2_artifacts.py` (11 tests). Persisted,
reproducible artifacts via
`scripts/prepare_step_4_1_registry_v2_handoff.py`: the four registry v2
templates (owner-status recorded honestly as `pending`; the other three
built against obviously-placeholder hashes), a composite validation
report confirming their cross-references agree, and
`scientific_readiness_best_case_check.json` recording the BLOCKED result
above. `production_job_status.json` records the production baseline job
as BLOCKED with exact, dated, sourced reason codes (missing real B fold
manifest; missing real B oracle-target document, itself blocked on Person
A's activation handoff per B's own `capture_intake_report.json`).
`runbook.md` records the exact command/inputs/outputs/acceptance checks
for every step once B's real artifacts land, including an explicit "what
must never happen" section against premature/fabricated READY results.

**Scope respected:** no scientific baseline was generated, fit, or
accepted; `docs/status/person_d_real_pilot_baseline_preview.json`'s
`scientific_use: forbidden` marking is untouched. No other role's branch
was merged or integrated. Baseline suite: 92 -> 113 passing. Repo-wide:
same 13 pre-existing A/B-owned failures, confirmed unchanged by direct
re-run.
