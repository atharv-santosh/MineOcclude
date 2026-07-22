# Person E Phase 0/1 status and current-state inventory

Status: current Person E Phase 0/1 status authority at `integration/mvp`.

The validated integrated checkpoint is
`0d5f979e14e5c5f41f59233f1222db822d30cdd6`. Its recorded historical test
evidence is `400 passed, 215 subtests passed`; those numbers are not presented
as a new run. Person E's repository-side Phase 0/1 technical work is integrated.
Formal human signoff, real calibration, and real measurement remain pending.

Allowed status values in this inventory are `Done`, `In progress`, `Blocked`,
`Not started`, and `Unverified`. A `Done` entry means only the stated
repository-side requirement is complete; it never asserts that real data or a
scientific result exists.

## Phase 0/1 requirement inventory

| Requirement | Status | Evidence or blocking condition |
|---|---|---|
| Phase 0 current-state inventory | Done | This file classifies every Phase 0 and Phase 1 requirement currently in scope. |
| Phase 0 compatibility and duplication report | Done | The report below and `docs/contracts/person_e_interface_ownership_v0_1.md` identify all current authorities and boundaries. |
| Phase 0 preserved-work list | Done | The evidence-backed list below distinguishes retained Phase 0/1 work from early future implementation. |
| Phase 0 incompatible/outdated-work list | Done | The superseded assumptions are recorded below without restoring stale shared files. |
| Phase 0 blocker/dependency list | Done | The dependency table below names the responsible owner and resolution deadline. |
| Phase 0 earliest unmet gate | Done | The repository-side Phase 1 technical gate is complete; formal human approval and A orchestration adoption remain explicit integration dependencies. |
| Phase 0 exact integration checkpoint | Done | Integrated at `integration/mvp@0d5f979e14e5c5f41f59233f1222db822d30cdd6`; historical checkpoint tests were 400 passed and 215 subtests passed. |
| Phase 1.1 complete interface and ownership map | Done | `docs/contracts/person_e_interface_ownership_v0_1.md`; unresolved boundaries are decision records in `docs/decisions/person_e_phase1_decision_log.md`. |
| Phase 1.2 complete immutable shared registry contract | Done | `validate_immutable_run_artifact_registry` in `src/mineocclude/contracts/rollout_registry.py`, the delegating E wrapper, `tests/fixtures/person_e/immutable_registry_v1.json`, and `tests/experiments/test_immutable_registry_contract.py`. Frozen A rollout schema `1.0` remains accepted unchanged. |
| Phase 1.3 contract-level vision and synthetic measurement fixtures | Done | `docs/contracts/person_e_phase1_synthetic_contracts_v1.md`, `tests/fixtures/person_e/`, and `tests/vision/test_phase1_contracts.py` cover split calibration, detection, homography, A/D-compatible rollout scenarios, measurements, and fail-closed rejection evidence. |
| Phase 1 overall end-to-end lineage trace gate | Done | `phase1_trace_registry_v1.json`, `phase1_lineage_trace_v1.json`, `trace_phase1_figure_lineage`, and `tests/experiments/test_phase1_lineage.py` prove the explicit figure-input-to-source trace without filename or row-order identity. |
| Real detector calibration and accuracy | Not started | Requires C calibration and held-out frames. Synthetic known-answer tests are not real calibration evidence. |
| Real homography qualification | Not started | Requires C marker/camera records and real held-out localization evidence. |
| Real U4 rollout measurement | Blocked | Requires accepted A rollouts, C geometry, a live E config, and B/E method approval. |
| Real figures, paper population, and release QA | Blocked | Requires accepted B/D/E scientific result artifacts plus approved orchestration/registration against the Phase 1.2 contract. Planning utilities are not result evidence. |
| Formal cross-role approval of E Phase 1 | Unverified | No repository evidence establishes human A/B/C/D/E approval. |

## Preserved work

The following work is valid and should be extended rather than recreated:

- Shared-registry validation, append-only publication, indexing, and tracing in
  `src/mineocclude/experiments/registry.py` and
  `tests/experiments/test_registry.py`. This is a wrapper and operational view
  over `src/mineocclude/contracts/rollout_registry.py`, not a second registry
  authority.
- E configuration and fail-closed readiness boundary in
  `configs/vision/person_e_phase1.yaml` and
  `src/mineocclude/vision/config.py`.
- Detector calibration contracts, held-out separation, synthetic fixtures,
  and tests in `src/mineocclude/vision/calibration.py` and `tests/vision/`.
- Hash-bound E-to-B measurement production in
  `src/mineocclude/vision/measurement.py`, including the authoritative B field
  `accepted_registry_hash`, A-derived `rollout_run_id`, and detailed evidence
  payload hashing.
- Figure-input validation, immutable output helpers, and trace tooling in
  `src/mineocclude/experiments/figure_inputs.py`, `scripts/`, and
  `tests/experiments/`.
- Contracts and operational records under `docs/contracts/`,
  `docs/decisions/`, and `docs/operations/` bearing the `person_e` name.

The detector, homography, localization, SSIM, U4 measurement, renderer, and
paper utilities are **early future implementation**. Preserve and verify them
in their later phases; their existence is not evidence that real calibration,
measurement, figures, or scientific claims are complete.

## Incompatible or outdated work

- Superseded: the original E-to-B handoff used `registry_hash` for literal
  registry-file bytes. The current B contract requires canonical
  `accepted_registry_hash`. The E measurement pipeline now uses the latter and
  validates it against the actual A rollout/registry bundle. The remaining
  `registry_hash` fields in artifact-index and trace reports mean literal
  source-file integrity only and are not E-to-B accepted-registry identity.
- Superseded: E's older copies of
  `src/mineocclude/analysis/manifests.py` and
  `src/mineocclude/contracts/rollout_registry.py` were not restored. The files
  integrated through `integration/mvp@0d5f979e14e5c5f41f59233f1222db822d30cdd6`
  remain authoritative.
- Superseded: caller-supplied rollout facts are not trusted by E measurement
  production. The current path passes the actual A manifest and registry to
  B's validator.
- Current boundary, not an alternate authority: the shared immutable-registry
  sub-schema can represent E detection, measurement, and figure-input records.
  Operational A-orchestrated publication remains pending and no private E
  registry is used meanwhile.

## Blockers and dependencies

| Dependency | Current state | Owner | Must be resolved before |
|---|---|---|---|
| A orchestration integration with the Phase 1.2 immutable shared-registry validator | Contract ready; runner integration unverified | E owns the data model; A owns orchestration integration; A/E approve | First orchestration-produced immutable registry snapshot |
| `rollouts.parquet` writer-of-record and measurement-facing projection | Safe default recorded; final file contract pending | A, reviewed by E | First real A-to-E rollout handoff |
| Capture resolution, camera pose, four marker correspondences, and signed world axis | Synthetic contract only | C, reviewed by E and B for the signed analysis axis | Real detector/homography calibration |
| Final `visible_flag` derivation | C remains authoritative; E emits empirical detections only | C, reviewed by E/B | Any real use of detection as visibility evidence |
| U4 metric/statistical interpretation and final SSIM rule | Pending approval | B owns statistics/claims; E owns measurement implementation | Real U4 analysis or claim-bearing figure |
| Baseline/control IDs and outputs | Repository contract exists; real outputs unavailable | D, consumed by E/B | Real control-matrix measurement and figure assembly |
| Formal cross-role signoff | Unverified | A/B/C/D/E and project approver | Declaring the Phase 1 checkpoint formally approved |

## Compatibility and duplication report

- The shared schema remains `1.0`; universal model-analysis identity remains
  `trajectory_id + model_frame_idx` where frame identity applies.
- A remains authoritative for rollout generation, model/runtime provenance,
  and rollout identity. E joins by explicit IDs and does not rewrite A rows.
- B remains authoritative for targets, metrics, statistics, and claim meaning.
  E emits `person-b-u4-measurement-input-v0.1` and calls B's validator.
- C remains authoritative for layouts, captures, geometric visibility, and the
  final visibility label. E's detector output is empirical evidence only.
- D remains authoritative for baseline/control definitions and outputs. E
  indexes and renders supplied IDs but does not recreate D logic.
- There is one shared registry authority:
  `src/mineocclude/contracts/rollout_registry.py`. It preserves the frozen A
  rollout bundle validator and defines the compatible
  `mineocclude-immutable-registry-v1.0` sub-schema. E's
  `src/mineocclude/experiments/registry.py` delegates validation and provides
  operational helpers; it does not define a competing schema. A runner
  integration has not yet been claimed.
- Scientific identity is never inferred from filenames, directories, row
  positions, or implicit ordering. E file paths are locations only; IDs and
  hashes carry identity.
- Accepted, excluded, failed, and superseded records remain explicit. E does
  not override an upstream producer's acceptance authority.

## Earliest unmet gate

No repository-side Person E Phase 0/1 technical gate remains unmet. Formal
human cross-role approval is unverified, and A orchestration adoption of the
shared registry remains a later integration dependency. Neither is fabricated
as completed by the synthetic Phase 1 evidence.
