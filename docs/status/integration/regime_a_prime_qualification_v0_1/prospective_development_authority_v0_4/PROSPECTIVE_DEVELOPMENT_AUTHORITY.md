# Regime A′ v0.4 — prospective development authority

`STATUS = DRAFT_PROSPECTIVE_UNFROZEN_NOT_AUTHORIZED`
`CLASSIFICATION = DEVELOPMENT_ONLY`
`STAGE_1_COLLECTION_AUTHORIZED = false`
`STAGE_2_COLLECTION_AUTHORIZED = false`

## 1. Why this authority exists

**It is not a scientific redesign.** The scientific delta against v0.3 is empty,
and `build_authority.py` proves it empty at build time by comparing the canonical
JSON of every scientific subtree (`apparatus`, `apparatus_observation_policy`,
`clock_domains`, `fixed_development_configuration`, `stage1_policy`,
`stage2_policy`) before and after the version sweep. A build that moved any of
them fails rather than emitting an authority.

v0.4 exists because the v0.3 Stage-1 terminated in a **scientific FAIL** at
freeze `134a242`, and a completed terminal decision permanently closes its
package's unit inventory. Those eight `a1x_*` / 83xxx units are historical
evidence and are never recollected. A new prospective run therefore needs a new
inventory — and in this repository the package version *is* the unit of
inventory identity: the authority id, both manifest ids, the authorization
receipt id, the pre-outcome provenance id, the Stage-1 decision id, the run
namespace and the durable prefix are all templated off the version tag in
`package_binding.py`. Advancing the tag advances all of them together.

## 2. What actually failed at 134a242, and what was repaired

Two independent roots.

**Root 1 — a stale Stage-1 evidence builder (a source defect, repaired).**
`build_stage1_evidence.py` remained on v0.2 point/band semantics while the
authority and evaluator had moved to v0.3 rendered-extent semantics. It emitted
the v0.2 transition schema the v0.3 evaluator could not read, produced 166
builder/evaluator regime mismatches (all one-directional: builder `stable_*`
against evaluator `partial_transition`), and selected its FIRST_N designated
hidden rows over the stale pool — LTR beginning at frame 38 where the extent pool
begins at 47. Four gates failed from this one cause:

| Gate | Root |
|---|---|
| `prospective_transition_measurement` | stale schema |
| `calibration_world_and_wall_relative_support` | regime mismatch |
| `hidden_row_contamination` | stale FIRST_N pool |
| `unit_identity_runtime_path_durability` | derived from contamination |

The repair is *not* a reimplementation. The builder now calls
`Stage1Evaluator.expected_regime`, `derive_transition_measurement` and
`designated_hidden_row_indices` — the evaluator's own methods — so there is one
semantic implementation and divergence is unrepresentable.

**Root 2 — a real temporal-alignment result (not repaired, not excluded).**
Trajectory `a1x_rtl_wall_r01` produced a trimodal normalized causal kernel whose
cross-correlation lag sat **1.8213 ticks** from its kernel mode against the frozen
**1.0-tick** bound. The other seven trajectories cleared it by 0.137–0.510 ticks,
and the RTL aggregate deviation was ~0.047. One trajectory failed; the temporal
system did not.

That is a measurement, not a defect. The bound is **not** widened, no unimodality
exception is added, the trajectory is **not** excluded, and no seed is chosen to
avoid it. The `a1y_*` seeds are minted from the new unit IDs by the same
deterministic `unit_seed` rule, with no reference to the failed trajectory.

## 3. The scientific redesign of v0.3 worked and is inherited unchanged

The v0.3 extent predicate is retained verbatim because it succeeded:

| Direction | stable visible | stable occluded | partial (unscored) | FP | FN |
|---|---|---|---|---|---|
| LEFT_TO_RIGHT | 217 | 74 | 53 | 0 | 0 |
| RIGHT_TO_LEFT | 202 | 88 | 54 | 0 | 0 |

The old `560bc01` boundary false positives were absorbed into `EXTENT_PARTIAL`
exactly as designed. Target extent stays `0.8727621336620037` blocks =
`(7 + sqrt(48.5)) / 16`, derived from the pinned client jar's `SheepFurModel`
wool geometry — detector-independent, outcome-independent, yaw-independent. See
`TARGET_EXTENT_DERIVATION.md`, carried forward unchanged.

## 4. Unit inventory

8 new units — 2 directions × 2 scenes × 2 roles — at 2.0 blocks/s, 180 frames.

| unit_id | episode | direction | scene | role |
|---|---|---|---|---|
| `a1y_ltr_wall_r01` | 85001 | LEFT_TO_RIGHT | WALL | TRANSITION_MEASUREMENT |
| `a1y_ltr_wall_r02` | 85002 | LEFT_TO_RIGHT | WALL | HELD_OUT_VALIDATION |
| `a1y_ltr_nowall_r01` | 85003 | LEFT_TO_RIGHT | NO_WALL | TRANSITION_MEASUREMENT |
| `a1y_ltr_nowall_r02` | 85004 | LEFT_TO_RIGHT | NO_WALL | HELD_OUT_VALIDATION |
| `a1y_rtl_wall_r01` | 85005 | RIGHT_TO_LEFT | WALL | TRANSITION_MEASUREMENT |
| `a1y_rtl_wall_r02` | 85006 | RIGHT_TO_LEFT | WALL | HELD_OUT_VALIDATION |
| `a1y_rtl_nowall_r01` | 85007 | RIGHT_TO_LEFT | NO_WALL | TRANSITION_MEASUREMENT |
| `a1y_rtl_nowall_r02` | 85008 | RIGHT_TO_LEFT | NO_WALL | HELD_OUT_VALIDATION |

Seeds are minted deterministically as `unit_seed(unit_id)`, with
`seed == noise_seed` — one seed identity per unit, which the server enforces at
arming. Stage-2 uses the disjoint 86xxx band and `a2y_*` identities.

The 81xxx/82xxx (v0.2), 83xxx/84xxx (v0.3) and 85xxx/86xxx (v0.4) episode bands
are pairwise disjoint, so a stale receipt can never be mistaken for a current
one. **No `560bc01` or `134a242` unit, episode, capture, receipt, decision or
durable object is reachable from this package**, and none is recollected.

## 5. Claim boundary

A v0.4 PASS qualifies the **measurement apparatus** for the next
authority-permitted development stage. It establishes nothing about hidden-state
representation, object permanence, belief, uncertainty, or causal use. Those
remain downstream experiments.

The open scientific question this authority exists to answer is narrow and
unweakened: **does the frozen temporal-alignment qualification pass
prospectively, including the RIGHT_TO_LEFT WALL trajectory class?** The rule is
unchanged, so the next campaign answers it on exactly the terms the last one
failed.

`STAGE2_AUTHORIZED = false`, and stays false unless and until a v0.4 Stage-1
produces an exact legitimate PASS artifact under this authority.
