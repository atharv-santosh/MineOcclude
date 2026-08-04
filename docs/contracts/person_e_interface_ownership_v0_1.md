# Person E Phase 1.1 interface and ownership map v0.1

Status: repository-side ownership map and cross-role Phase 0/1 interface
compatibility approved at
`integration/mvp@80d41c5ca0e341263a7b0c683fae4b51be376c55`; central human signoff
evidence is `docs/contracts/schema_v1_0_signed_record.md`. Real-runtime and
experimental qualification remain pending.

This is the authoritative Person E Phase 1.1 map. A path or filename is never
scientific identity. "Allowed E extensions" means a separate versioned,
hash-bound E record or an approved migration; it never permits E to mutate an
upstream artifact or add private fields to schema `1.0`.

| Artifact or interface | Authoritative owner | Writer-of-record | Schema/version | Scientific or artifact key | Allowed E extensions | Validator | Downstream consumer |
|---|---|---|---|---|---|---|---|
| Universal identity and lifecycle vocabulary | A | A schema-maintenance path | Shared `1.0` | Frame: `trajectory_id + model_frame_idx`; artifact: explicit ID | None without versioned shared migration | `mineocclude.contracts.identity.validate_identity` and lifecycle helpers | A/B/C/D/E |
| Shared run registry | E owns data model and lineage behavior; A owns orchestration integration | Shared contract validator is authoritative; A orchestration will submit snapshots/transitions, but runner integration is not yet evidenced | Frozen rollout schema `1.0` plus `mineocclude-immutable-registry-v1.0` | `registry_id`, immutable `run_id`, parent and superseded run IDs | New fields or semantics require a new immutable-registry sub-schema version | `validate_immutable_run_artifact_registry`; E `require_valid_immutable_registry` delegates without redefining rules | A orchestration, E lineage/QA, B/D consumers |
| Shared artifact records | E for lineage behavior; producing role owns artifact meaning | Producing roles submit records through the shared contract; no private E registry writer exists | `mineocclude-immutable-registry-v1.0`, retaining shared `schema_version=1.0` | `artifact_id`, `creator_run_id`, direct input IDs | New types or fields require a versioned shared-contract change | `validate_immutable_run_artifact_registry` | All producers/consumers and E artifact index |
| A rollout-generation manifest | A | A rollout generator/orchestrator | Rollout manifest schema `1.0` | `manifest_id`, `handoff_id`, `rollout_id`; explicit event/seed/frame identity | E may create separate measurement/index records referencing IDs and accepted hashes | `validate_rollout_registry_bundle` | E measurement operations; B measurement intake |
| `rollouts.parquet` or equivalent measurement-facing rollout table | A | A only | Pending physical representation; meanings remain rollout schema `1.0` | `rollout_id`, with explicit event, seed, direction, control, layer, timestep, and context IDs | E may publish a separate enrichment keyed by `rollout_id`; it may not rewrite generation rows or create competing clip IDs | Until frozen, validate the source A manifest/registry and reject any projection mismatch | E measurement operations, then B |
| Accepted rollout manifest | A and its declared acceptance authority | A acceptance process | Rollout manifest schema `1.0` plus canonical accepted manifest hash | `manifest_id`, `handoff_id`, `rollout_id` | E records the canonical hash and rejection reason; no status override | `validate_rollout_registry_bundle`; B `validate_measurement_input` rechecks the bundle and hash | E measurement, B analysis, E figure provenance |
| A model/runtime provenance | A | A runtime/orchestration | Shared schema `1.0` run/rollout fields | `run_id`, `code_sha`, `model_hash`, `config_hash`, `preprocess_hash` | E may reference and trace these exact values only | `validate_rollout_registry_bundle` | E lineage and measurement; B audit |
| B target definitions | B | B oracle/target pipeline | B target contracts under `docs/contracts/` | `trajectory_id + model_frame_idx`, target name/version | None; E may reference result IDs and units | B target/oracle validators | B/D analyses and E figure assembly |
| B metric definitions and statistics | B | B metric/statistics pipeline | B analysis config and artifact contracts | Explicit result/prediction IDs, fold/config hashes, units | E may render or index accepted outputs; it cannot recompute inferential meaning | Current B metric/artifact validators | E figure/table assembly and paper QA |
| B U4 measurement intake | B | E produces the handoff; B owns acceptance semantics | `person-b-u4-measurement-input-v0.1`, shared `1.0` | `measurement_id`, `rollout_id`, `rollout_run_id` | E-only rich evidence and QA fields remain in separate hash-bound records | `mineocclude.contracts.analysis_inputs.validate_measurement_input` with actual A manifest/registry | B U4 statistics and result production |
| C layout identity | C | C layout contract/fixture producer | `person_c_contract_version=0.1`; immutable layout schema v0.1 plus additive layout schema v0.2; shared `1.0` | Stable `layout_id` | E references layout and pose IDs in detector/homography records; no redefinition | `mineocclude.data.layout_contract.validate_layout_config` | A/B/E and reconstruction QA |
| C marker and camera geometry | C | C capture/layout producer | C layout v0.2 maps stable physical IDs to canonical roles; E homography fixtures v1.0 and v1.1 | `layout_id + canonical_pose_id + marker_id`; explicit `marker_role`; declared resolution | E v1.1 joins observations by stable ID and consumes the role without changing C identity/world coordinates; v1.0 remains accepted | C layout validator; `validate_homography_fixture`; `scripts/fit_homographies.py` input checks | E homography/localization; C reconstruction QA |
| C visibility outputs | C | C capture/visibility producer | C interface v0.1 over shared `1.0` | Source capture identity and downstream `trajectory_id + model_frame_idx` | E may emit empirical detector presence/quality linked to the same source; never final `visible_flag` | C capture/trajectory validators | A/B; E measurement QA consumes but does not override |
| D baseline identifiers and outputs | D | D baseline harness/export | `person-d-baseline-spec-v1.0`, `person-d-baseline-prediction-v1.0`, B baseline input v0.1 | Baseline identity plus `trajectory_id + model_frame_idx` | E may index and render accepted rows with source hashes | D spec/prediction validators and B `validate_baseline_input` | B comparison/statistics and E figures |
| D control identifiers and outputs | D | D control-matrix/baseline producer | D Phase 1 control contracts; rollout control values remain A schema `1.0` | Explicit control/event/seed/rollout IDs | E preserves submitted control identity and measurement linkage; it does not infer or rename controls | D control validators plus A rollout bundle validator | B U4 statistics and E measurement/figures |
| E configuration | E | E config publication path | `person-e-phase1-config-schema-v0.1`, shared `1.0` | `config_instance_version` and literal config hash | New immutable config version/hash only | `validate_person_e_config`; `require_live_ready_person_e_config` for scientific runs | All E detector/homography/measurement/figure operations |
| E detector calibration dataset/plan | E owns calibration validation; C owns source frames and labels | E calibration preparation from C-provided evidence | Dataset v0.1 plus `person-e-detector-calibration-plan-v1.0`, shared `1.0` | Explicit event, model-frame, source-frame, layout, pose, split, resolution, and decoded RGB identity | E adds threshold-candidate and quality metadata, never C final visibility | `validate_detector_calibration_dataset`; `validate_detector_calibration_plan` | E detector calibration and held-out evaluation |
| E detector output/report | E | `evaluate_magenta_detector.py` | `person-e-detector-report-v0.2` plus `person-e-detection-records-v1.0`; threshold version explicit | Explicit source artifact/frame, rollout/event, model-frame, layout, pose, and resolution identity | E-owned centroid, area, bounding box, quality, and rejection fields | `validate_detection_document`; report validation in `evaluate_magenta_detector.py` | E homography/localization and measurement QA; C may review empirical evidence |
| E homography output | E | `fit_homographies.py` | `person-e-homography-report-v0.2`; Phase 1 fixture v1.0 preserved and v1.1 stable-ID/role interpretation added; algorithm `four_point_projective_gauss_jordan_v0.1` | Layout, camera pose, resolution, coordinate system, stable marker IDs, canonical roles, and fit identity | E-owned fit matrix, errors, settings hash, and rejection result | `validate_homography_fixture`; `homography_from_record` plus fit/report checks | E localization and measurement QA |
| E localization and SSIM reports | E | `localize_u4_frames.py` and `measure_ssim.py` | Localization v0.1; SSIM report v0.2 | `rollout_id + rollout_frame_idx`, with event/seed/layout/clip hashes | E-owned measured coordinates, detection hashes, SSIM values, and diagnostics | Script-level strict input, alignment, registry, config, and settings checks | `compose_u4_evidence.py`, then E measurement |
| E detailed measurement evidence | E | `build_measurement_evidence` / `measure_u4.py` | `person-e-measurement-evidence-v0.2`, shared `1.0` | `evidence_id + rollout_id` | Hash-bound payload and explicit provenance only | `validate_measurement_evidence` | E-to-B measurement document and provenance QA |
| E measurement output | E owns measurement; B owns metric/statistical interpretation | `build_measurement_document` / `measure_u4.py` | B intake `person-b-u4-measurement-input-v0.1`, shared `1.0` | `measurement_id + rollout_id`; A `rollout_run_id` | Separate rich evidence references and persistence QA; no B statistics or claim fields | B `validate_measurement_input` against actual A bundle | B U4 statistics, E figure inputs |
| E figure input | E | `build_figure_input.py` | `person-e-figure-input-v0.2` | `figure_id`; rows bind series/result/artifact/run IDs | E-owned presentation grouping, captions, units display, and QA labels | `validate_figure_input`; `validate_figure_input_against_registry` for source eligibility | `render_figure_svg.py`, lineage trace, paper/release QA |
| E rendered figure and companion manifest | E | `render_figure_svg.py` | `person-e-rendered-figure-manifest-v0.1` | `figure_id` plus input/output/caption hashes | Rendering metadata only; source scientific values remain owned upstream | Renderer revalidates figure input and derives literal output hashes | Paper assembly, reviewers, release QA |
| Artifact accepted/excluded/failed/superseded status | E owns shared lifecycle behavior; upstream source authority owns scientific acceptance | Shared records carry explicit `status_authority`; artifact `accepted`/`excluded`/`superseded` remains distinct from run `failed` | `mineocclude-immutable-registry-v1.0` | `artifact_id`; `superseded_by`; linked `creator_run_id` for execution failure | E may index, audit, and report status; it cannot override upstream acceptance or conflate run failure with artifact exclusion | `validate_immutable_run_artifact_registry`; E provenance QA | Every claim-bearing consumer and release QA |
| U4 image-coordinate and resolution contract | C owns captured resolution/camera; E owns detector pixel coordinates and homography implementation | C writes capture identity; E writes derived detection/homography records | Current safe rule: zero-based pixel-center `(x,y)`, declared width/height, C layout v0.2/camera identity, and E homography v1.1; final real-data qualification pending | `layout_id + canonical_camera_pose_id + resolution identity + source frame identity` | E may add versioned detector/homography metadata, never infer resolution or correspondence from filenames/order | C layout/capture validators plus E calibration/homography checks | E localization/measurement and C reconstruction review |

## Phase 1.2 immutable registry fields

The authoritative implementation is
`mineocclude.contracts.rollout_registry.validate_immutable_run_artifact_registry`.
`mineocclude.experiments.registry.require_valid_immutable_registry` only
delegates and converts rejections into an operational error. A orchestration is
expected to submit registry snapshots and transitions to the shared validator;
that caller integration is not yet implemented or claimed.

Every run record requires:

- shared `schema_version`, immutable `run_id`, full `code_sha`, and
  `git_dirty`;
- `config_snapshot_hash`, `checkpoint_hash`, `data_identity_hash`,
  `preprocess_hash`, and `environment_hash`;
- named integer `seeds`, exact `command`, `owner`, UTC `started_at` and
  nullable `ended_at`;
- `status`, `parent_run_id`, direct run input IDs, output artifact IDs, and
  nullable `failure_reason`; and
- nullable `supersedes_run_id` and `supersession_reason`.

Every artifact record requires:

- shared `schema_version`, explicit `artifact_schema_version`, and immutable
  `artifact_id`;
- `direct_input_artifact_ids`, `creator_run_id`, closed-catalog
  `artifact_type`, explicit `uri`, SHA-256, and `size_bytes`; and
- `status`, `status_authority`, nullable `status_reason`, and nullable
  `superseded_by`.

The closed catalog includes raw trajectory, model input, oracle target,
activation, fitted probe, prediction, baseline, rollout, detection, metric
table, and figure, while preserving existing A rollout types and the E-owned
lineage products represented by this contract. Catalog membership does not
implement or transfer ownership of the scientific producer.

Run state changes are limited to `in_progress -> completed` or
`in_progress -> failed`. Terminal run records cannot change. Corrections append
a new run with a same-owner completed target, a new identity, and a reason.
Artifact content and provenance cannot change in place; an accepted artifact
may move only to `superseded` while naming a same-type replacement and reason.
Literal bytes, when supplied, must match both recorded SHA-256 and size.

## Writer and consumer check

- No artifact above has two authoritative writers. The shared contract is the
  sole validation authority. A orchestration integration remains pending and
  must consume it rather than introduce a second schema or validator.
- Every E Phase 0/1 output has a named consumer: detector and homography outputs
  feed localization; localization and SSIM feed measurement; measurements feed
  B; figure inputs feed rendering and paper QA; registry QA feeds checkpoint
  acceptance.
- E does not own A rollout/model semantics, B targets/metrics/statistics, C
  layout/visibility semantics, or D baseline/control logic.
- Unresolved ownership and interface questions are `PE-OWN-001` through
  `PE-OWN-006` in `docs/decisions/person_e_phase1_decision_log.md`.
