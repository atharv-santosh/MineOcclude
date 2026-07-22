# Person D: Baselines, Controls, and Related Work

## Objective

Own MineOcclude's non-model baselines, floors, references, controls, leakage
diagnostics, and the U4 control matrix through the MVP checkpoint. After the
checkpoint, own verified literature sources, Related Work/Background, and the
BibTeX/evidence matrix.

Full details: the team's "MineOcclude Research Execution Guide v3.0" --
Section 3 team map, Day 0 through Day 7 Person D blocks, and Role Reference /
Person D.

## Current blockers

- [ ] Receive Person B's persisted `fold_manifest` artifact. Today D
      reconstructs the identical layout-grouped assignment via
      `mineocclude.probes.splits.assign_layout_grouped_folds` using B's frozen
      seed/config (`mineocclude.baselines.export.attach_b_fold_assignments`);
      consuming a real signed manifest directly is preferred once one exists.
- [ ] Receive Person C's accepted trajectory manifest and Person B's real
      oracle targets (`mu_oracle_blocks`, `log_sigma_oracle`) to fit the
      explicit-feature/raw-pixel ridge baselines against.
- [ ] Receive Person A's real MineWorld activations (raw-pixel baseline needs
      real preprocessed frames; random-weight baseline is explicitly deferred
      to Week 2 pending a random-initialized checkpoint run).
- [ ] Receive Person B's real fitted U4 direction/layer/timestep/doses to run
      the control matrix against for real, and Person A's rollout registry to
      audit control-matrix completeness against.

## MVP work

- [x] Closed-form baselines: last-seen (memory heuristic), constant-velocity
      (reference in Regime A, genuine baseline in Regime B), grouped-shuffled
      labels (chance floor, trajectory-level derangement), time-only spread
      (clock test).
- [x] D-to-B baseline-input export
      (`mineocclude.baselines.export.build_baseline_document`) that passes
      Person B's real `validate_baseline_input` consumer contract
      (`person-b-baseline-input-v0.1`), using B's own layout-grouped fold
      algorithm rather than an independently filtered split.
- [x] Explicit-feature ceiling: ridge on last-seen position, *estimated*
      visible-window velocity, tau, duration, and two declared interaction
      terms -- never the privileged scripted v/q.
- [x] Raw-pixel ridge baseline: same leakage-safe ridge-OOF machinery, fed
      externally supplied pixel feature vectors (no real captured frames yet).
- [x] Visible-history-q spread baseline (fair): per-fold q_hat estimated from
      pooled pre-occlusion visible-window residuals of the *other* folds'
      trajectories only.
- [x] Known-q analytic spread baseline: reproduces the oracle's own
      `variance = q*tau` form with the *true* scripted q, explicitly flagged
      `is_fair_baseline = False` -- a privileged reference ceiling, never a
      fair competitor.
- [x] No-wall / occluder-only control audits
      (`mineocclude.baselines.controls`): structural checks that no-wall data
      is always visible and occluder-only data never carries a position, plus
      a leakage check that no baseline row is ever marked applicable on a
      no-object frame.
- [x] Random-weight MineWorld baseline interface
      (`mineocclude.baselines.random_weight`): thin wrapper reusing the
      raw-pixel fitting path so the interface is ready; real use is deferred
      to Week 2 per the roadmap.
- [x] Metadata-only leakage diagnostics (`mineocclude.baselines.leakage`):
      identity/filename structural checks, independent layout-fold isolation
      re-check, and a general leakage-safe grouped-ridge predictability check
      usable against wall length, q, duration, frame count, ordering, padding,
      or the oracle target itself.
- [x] U4 control-matrix builder and audits
      (`mineocclude.baselines.u4_control_matrix`): stable IDs for alpha=0,
      seeded random direction, orthogonal direction, wrong layer, and wrong
      timestep; completeness (no omitted/duplicated control), norm-matching,
      and orthogonality-to-the-real-direction checks. D verifies this matrix;
      it does not fit the real direction (B) or inject it (A).
- [ ] Run all of the above against real accepted rows/folds/targets once
      C/B/A hand off real data -- everything above is currently exercised
      only against synthetic fixtures (`tests/baselines/`).

## Post-MVP work

- [ ] Draft Related Work/Background.
- [ ] Verify every proposal-named paper against primary sources (title,
      authors, venue, claims) before it enters prose; mark unresolved facts
      as unresolved.
- [ ] Own the verified bibliography/BibTeX and claim-evidence matrix.
- [ ] Continue running locked baseline/leakage workflows whenever the
      accepted manifest changes; any change to baseline/control logic itself
      goes through A/B review.

## Definition of done

- [ ] Every baseline scores exactly Person B's accepted rows and frozen
      folds -- never an independently filtered split.
- [ ] Every baseline is honestly labeled floor/reference/ceiling/control;
      constant-velocity's "reference" role and known-q analytic's privileged
      status are never presented as fair competitors.
- [ ] A non-applicable prediction is always `None`, never scored as zero.
- [ ] Every D-to-B document passes Person B's real `validate_baseline_input`.
- [ ] Control failures (missing/duplicated control rows, non-unit or
      non-orthogonal control directions) are reported, never silently
      dropped.
- [ ] Every literature claim in Related Work traces to a verified primary
      record; unresolved facts stay unresolved rather than entering prose.
