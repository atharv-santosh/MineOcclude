# ACE corrected-scope completion audit

Audit date: 2026-08-03  
Audit branch: `integration/ace-roadmap-audit`  
Pre-repair integrated tip: `a440e4166f0c91c3d73fae48aed68ad0e264c51c`

## Decision

`ACE_REQUIRED_SCOPE_COMPLETE=False`.

The repository contains substantial real runtime, capture, activation,
detector, homography, and registry evidence. It does not satisfy the corrected
hard completion rule. Person A stops at an unaccepted A6.6 single-pilot
handoff; Person C's C1 runtime/reconstruction stop gate is still explicitly
open and its proposed C6A rows are not the same rows consumed by A, B, and E;
Person E's final E4.1 registry contains actual A/B/D records but no C or E
run/artifact records and omits several workstream artifact classes required by
the manual.

No missing scientific evidence was generated. The explicit C6B authority tip
`c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960` was not integrated or audited.
Person B was inspected read-only only at the frozen A6.6 positive-control
commit `e39fef4a59142a84dfb5991d51deeb506eb23a7b`; Person B and Person D were not
merged or modified.

## Authority and counting method

The manuals used were:

- Person A DOCX SHA-256 `4b2bd07ab8399440a2e0234049fc9cccda5c6a657db724dbe236c4ca80a13591`.
- Person C DOCX SHA-256 `91290ce1d463c6db372fa01051c9f0daa0322d11e5febc35e149c4760eb74fe8`.
- Person E DOCX SHA-256 `08804f049510df03c258c63df615bd4495e9e002c85305d1360f293fb72173f0`.

The ACE branch integrates Person A authority through
`397ba849adc63df80912c21dd1efacb1e29b8977`, Person C through the single-pilot
authority `f0d4e895b56fc4ca3f4805aa13b73545744af1b0`, and Person E through
`ab41a76ce0c855c0ac54c59c736bac7599f7e69d`.

A requirement is counted complete only when its implementation, required real
operational evidence, artifact/hash identity, validation/pass check, authority
commit, upstream gate, and required downstream receipt are all present. A
technically implemented downstream step is not counted complete when an
explicit upstream STOP GATE remains open. This is why C2-C6A are recorded as
implemented/evidenced but not certified after the unclosed C1 stop gate.

## Person A requirement ledger (52 requirements)

| Step | Certification | Implementation, evidence, authority, validation, and handoff |
|---|---|---|
| A0.4 | COMPLETE | Pinned revision/symbol review is in `docs/status/person_a_mineworld_code_reading.md`; authority `3a077f7f9443a205c4cdb540b74b791f79af3ea3`. |
| A0.5 | COMPLETE | Versioned dependency/decision state in `docs/status/person_a_phase0.md`; integrated authority `a699797f212b5621541eed4dcc42af2b15721933`. |
| A0.6 | COMPLETE | Command-center status, owner, blockers, and evidence paths in `docs/status/person_a_phase0.md`; authority `a699797f212b5621541eed4dcc42af2b15721933`. |
| A1.1 | COMPLETE | Owned file map in `docs/architecture/person_a_file_map.md`; no duplicate authority found; schema checkpoint `a699797f212b5621541eed4dcc42af2b15721933`. |
| A1.2 | COMPLETE | Universal identity contract/tests in `docs/contracts/identity_v1.md` and `tests/contracts/test_identity.py`; schema checkpoint `a699797f212b5621541eed4dcc42af2b15721933`. |
| A1.3 | COMPLETE | C-to-A trajectory contract and reject fixtures in `docs/contracts/trajectory_v1.md` and `tests/contracts/test_trajectory_contract.py`; checkpoint `a699797f212b5621541eed4dcc42af2b15721933`. |
| A1.4 | COMPLETE | Activation contract/index identity and fixtures in `docs/contracts/activation_v1.md` and `tests/contracts/test_activation_contract.py`; checkpoint `a699797f212b5621541eed4dcc42af2b15721933`. |
| A1.5 | COMPLETE | Intervention request contract and reject fixtures in `docs/contracts/intervention_request_v1.md`; checkpoint `a699797f212b5621541eed4dcc42af2b15721933`. |
| A1.6 | COMPLETE | Rollout/registry contracts in `docs/contracts/rollout_registry_v1.md`; checkpoint `a699797f212b5621541eed4dcc42af2b15721933`. |
| A1.7 | COMPLETE | Cross-role synthetic runner/report in `src/mineocclude/integration/synthetic_pipeline.py` and `tests/fixtures/integration/synthetic_join_report.json`; regenerated result: 8/8 contracts, 13/13 joins, 15/15 integrity checks. |
| A1.8 | COMPLETE | Signed schema/decision record in `docs/contracts/schema_v1_0_signed_record.md`; checkpoint `a699797f212b5621541eed4dcc42af2b15721933`. |
| A2.1 | COMPLETE | Official local/AWS environment reports and locks under `configs/environments/` and `docs/status/person_a_phase2_environment.md`; authorities `9eb37bc97063e293e0321debca460ddc0b14706a`, `62ba8123fdf81f7ae02f3b874ee369f969985976`. |
| A2.2 | COMPLETE | Clean pinned Microsoft source acquisition record in `docs/status/person_a_mineworld_source_acquisition.md`; authority `853f67c2190f082e004caca4e2929eda9c54513d`. |
| A2.3 | COMPLETE | Exact ModelScope asset revision/paths in `docs/status/person_a_mineworld_asset_acquisition.md`; authorities `853f67c2190f082e004caca4e2929eda9c54513d`, `16b124a60068dd8afafd7ab095a4dee32630921b`. |
| A2.4 | COMPLETE | Machine hash/size evidence in `docs/status/person_a_phase2_asset_verification_aws_l4.txt` and `configs/assets/mineworld_assets_v1.json`; authority `16b124a60068dd8afafd7ab095a4dee32630921b`. |
| A2.5 | COMPLETE | Real paired-sample media/action audit in `docs/status/person_a_phase2_sample_audit.md`; bound by runtime closure `e5032cc00dd83716df6f8e1b863659477adddb95`. |
| A2.6 | COMPLETE | Real AWS free-generation logs/video/hash in `docs/status/phase2_runtime/person-a-phase2-aws-20260725-055616/step2_6/`; authorities `f149281db4dc4f64d8d1d030a6f41acf388bbe0b`, `e5032cc00dd83716df6f8e1b863659477adddb95`. |
| A2.7 | COMPLETE | Loaded architecture report/log under the same runtime bundle `step2_7/`; authority `e5032cc00dd83716df6f8e1b863659477adddb95`. |
| A2.8 | COMPLETE | Real teacher-forced report/log under `step2_8_2_9/`; authorities `35baf673312af5c21ae3f22168de405bd4ee8bd9`, `e5032cc00dd83716df6f8e1b863659477adddb95`. |
| A2.9 | COMPLETE | Repeatability/compute classification in `teacher_forced_report.json` and `docs/status/person_a_phase2_runtime_record.md`; authority `e5032cc00dd83716df6f8e1b863659477adddb95`. |
| A2.10 | COMPLETE | Authority-bound runtime closeout in `docs/status/person_a_phase2_runtime_record.md` and registry handoff; authorities `e5032cc00dd83716df6f8e1b863659477adddb95`, `f0a4fed546eb1cf19a7094e6b99399a58294726a`. |
| A3.1 | COMPLETE | Frozen minimal public API in `docs/contracts/mineworld_adapter_api_v1.md`; authority `4da55c068895d0018ffe80c88eb542c5142718c0`. |
| A3.2 | COMPLETE | Official model/config/VAE loader in `src/mineocclude/models/_mineworld_adapter_wave2.py`; certified authority `2eef2a4cd0f19e0e1b9897f2ac38dffa480e176b`. |
| A3.3 | COMPLETE | Strict trajectory validation in the adapter and capture-contract tests; authority `7e31d6047212cabcc1ce19a8fe85a16309557655`. |
| A3.4 | COMPLETE | Audited frame preprocessing/golden fixtures in Wave 2 code/tests; authority `7e31d6047212cabcc1ce19a8fe85a16309557655`. |
| A3.5 | COMPLETE | Pinned official action conversion and provenance checks in Wave 2; authority `7e31d6047212cabcc1ce19a8fe85a16309557655`. |
| A3.6 | COMPLETE | Actual-sequence FrameTokenMap implementation/fixtures in Wave 3; authority `be101f3174005e94f30eb4be6b98ee4d2aaea628`. |
| A3.7 | COMPLETE | Teacher-forced execution in Wave 3/4 with real runtime certification; authorities `be101f3174005e94f30eb4be6b98ee4d2aaea628`, `2eef2a4cd0f19e0e1b9897f2ac38dffa480e176b`. |
| A3.8 | COMPLETE | Free-rollout entry point and real rollout artifact in Phase 3 runtime evidence; authority `2eef2a4cd0f19e0e1b9897f2ac38dffa480e176b`. |
| A3.9 | COMPLETE | Identity/failure certification in `certification_summary.json`, logs, and Wave 4 tests; authority `2eef2a4cd0f19e0e1b9897f2ac38dffa480e176b`. |
| A4.1 | COMPLETE | Real hook discovery report and frozen decoder-site identity under `docs/status/phase4_runtime/...wave1...`; authorities `619d9c051106ed6c68122dccc846bd4109a4fda5`, `0577d78d865969fd346c1dc9f7a9ee7159f023a1`. |
| A4.2 | COMPLETE | Scoped hook manager and cleanup/failure tests in `src/mineocclude/activations/hooks.py`; authority `7a24809c2ccb5e831ff28c856a1dcfdec5c4ebc3`. |
| A4.3 | COMPLETE | FrameTokenMap-only visual selection in hook/pooling probe; authority `76d2a5a462e3daba0baa374e92c7e7b20de393b8`. |
| A4.4 | COMPLETE | Direct visual-token mean pooling plus real probe evidence; authorities `76d2a5a462e3daba0baa374e92c7e7b20de393b8`, `3f607eec5682dced8f106b000280691a6f6823cf`. |
| A4.5 | COMPLETE | Detach/cast/CPU-transfer/memory bounds in Wave 2/3 tests and runtime reports; authority `72f7d830b5630a4204b9d47ac81432a92a711227`. |
| A4.6 | COMPLETE | Action-token exclusion is directly tested and recorded in pooling/extraction reports; authority `f83b1805d1020f65974425a4a4bbb8f6296c980f`. |
| A4.7 | COMPLETE | Consecutive extraction/hook cleanup safety evidence under Phase 4 Wave 3; authority `b94e17efb682ae1f4352a0437c74b43dd33a5ee4`. |
| A4.8 | COMPLETE | Bounded unpooled NPZ plus hash-bound manifest retained in Phase 4/6 runtime bundles; authority `b94e17efb682ae1f4352a0437c74b43dd33a5ee4`. |
| A5.1 | COMPLETE | Evidence-gated storage decision in `docs/status/person_a_phase5_storage_decision.md`; authority `b0b71653311902fffce769aca6c4e81475ba0766`. |
| A5.2 | COMPLETE | Chunk/row uniqueness enforced in `src/mineocclude/activations/store.py` and tests; authority `b0b71653311902fffce769aca6c4e81475ba0766`. |
| A5.3 | COMPLETE | Temporary-write/hash/fsync/atomic publication behavior and fault tests; authority `b0b71653311902fffce769aca6c4e81475ba0766`. |
| A5.4 | COMPLETE | Index record and checked example in `docs/status/fixtures/phase5_activation_store_example/`; authority `b0b71653311902fffce769aca6c4e81475ba0766`. |
| A5.5 | COMPLETE | Idempotent resume/interruption tests in `tests/activations/test_phase5_store.py`; authority `b0b71653311902fffce769aca6c4e81475ba0766`. |
| A5.6 | COMPLETE | Cardinality, identity, corruption, and orphan audits in store validator/tests; authority `b0b71653311902fffce769aca6c4e81475ba0766`. |
| A5.7 | COMPLETE | CPU storage/read benchmark and forecast in `scripts/benchmark_phase5_activation_store.py`; authority `b0b71653311902fffce769aca6c4e81475ba0766`. |
| A5.8 | COMPLETE | Synthetic handoff v1.2 and independent B receipt in `docs/status/person_b_phase5_activation_store_receipt_v1_2.json`; authorities `b6d4304adb0f82c1722342795133dde4aa59ea7f`, `85224f1951c224698a2cf6f8a0a3088de5b67664`. The current Python 3.14/NumPy environment produces a different floating-point probe hash; this audit did not rewrite the frozen receipt. |
| A6.1 | COMPLETE | C-owned accepted `layout_00_ep9403` intake, exact hashes, and direct inputs in `prior_evidence/step6_1.json`; A authority `e6e0340f301abb84c127034b154be55a38bdc8f6`, C authority `f0d4e895b56fc4ca3f4805aa13b73545744af1b0`. |
| A6.2 | COMPLETE | Model-boundary 248-row media/action/state/frame-map/visibility validation with zero ambiguity in `prior_evidence/step6_2.json`; authority `e6e0340f301abb84c127034b154be55a38bdc8f6`. |
| A6.3 | COMPLETE | Real tokenization: 248 global frames, 16 contexts, 347 tokens/pair, rollover check in `step6_3.json`; authority `e6e0340f301abb84c127034b154be55a38bdc8f6`. |
| A6.4 | COMPLETE | Real teacher-force/hook/pool/store: 4,960 activation rows, 20 chunks, bounded unpooled evidence, repeatability delta 0 in `step6_4.json`; authority `e6e0340f301abb84c127034b154be55a38bdc8f6`. |
| A6.5 | COMPLETE | Independent direct-pooling, identity join, collision, and repeatability audit in `step6_5.json`; authority `e6e0340f301abb84c127034b154be55a38bdc8f6`. |
| A6.6 | **INCOMPLETE** | The single-pilot `step6_6_handoff.json` says `HANDOFF_PREPARED_NOT_ACCEPTED`, `registry_v2_acceptance_claimed=false`, and `completion_report.json` says `step6_6_complete=false`. B commit `e39fef4...` and E commit `5bbe7c7...` instead bind A's later ten-pilot commit `55776dc...` and different trajectory IDs. Later A6.7 evidence is not a substitute for the scoped A6.6 receipt. |

## Person C requirement ledger (33 requirements)

| Step | Certification | Implementation, evidence, authority, validation, and handoff |
|---|---|---|
| C1.1 | **INCOMPLETE** | `configs/scenes/environment_lock.observed_dev_v0_1.json` explicitly says formal fresh-launch comparison is pending and lists the missing launcher, `server.properties` hash, resource-pack, FOV, and graphics evidence. `docs/reports/person_c_c0_c1_signoff.md` says the runtime stop gate is open. |
| C1.2 | COMPLETE | Six-layout common arena grammar, wall/lane/shadow/camera/marker conventions, and structural validation exist in `configs/scenes/layouts.yaml`; authority `61b1a1aef5fb8a721171cbe082fd5e16348f810f`. E has demonstrated usable marker-based homographies, although the frozen-coordinate mismatch is separately compatibility-blocking. |
| C1.3 | **INCOMPLETE** | Six structural definitions exist, but every `runtime_evidence.reference_screenshot` in `configs/scenes/layouts.yaml` remains `RUNTIME EVIDENCE REQUIRED LATER`; the manual requires traceable real reference screenshots. |
| C1.4 | COMPLETE | Core/no-wall/no-sheep variants, target-count logic, reset tests, and condition fields are implemented in Fabric/Python code; authorities `61b1a1a...`, `46254513bc099c41282ec01ef979b451d408c1a9`. |
| C1.5 | **INCOMPLETE** | Only templates/checklists exist. `docs/runbooks/person_c_layout_reconstruction_checklist.md` is unchecked and explicitly says it is not evidence; `docs/reports/person_c_c0_c1_signoff.md` leaves second-operator reconstruction and review `RUNTIME EVIDENCE REQUIRED LATER`. |
| C2.1 | **INCOMPLETE (C1 STOP GATE)** | Fabric build files/JAR hash/build claim exist under `fabric/mineocclude-mod/` and the observed lock, but the required complete pinned C1 environment is not approved. Technical authority `46254513bc099c41282ec01ef979b451d408c1a9`. |
| C2.2 | **INCOMPLETE (C1 STOP GATE)** | Explicit lifecycle implementation/tests and real lifecycle rows exist, but certification cannot cross the open C1 stop gate. |
| C2.3 | **INCOMPLETE (C1 STOP GATE)** | Reset/target setup and real reset receipts exist; the later layout-ID decision also records a fail-open unknown-layout fallback, and C1 is unapproved. |
| C2.4 | **INCOMPLETE (C1 STOP GATE)** | Immutable Regime A schedule/noise implementation and runtime rows exist; upstream environment/layout gate is open. |
| C2.5 | **INCOMPLETE (C1 STOP GATE)** | One authoritative server-state row per runtime tick is evidenced under `data/server_evidence/`; upstream gate is open. |
| C2.6 | **INCOMPLETE (C1 STOP GATE)** | Tick packet/broadcast implementation and client receipt identity exist; upstream gate is open. |
| C2.7 | **INCOMPLETE (C1 STOP GATE)** | Failure/replay tests exist, but the unknown-layout fallback noted in `docs/decisions/person_c_layout_id_supersession_v0_1.md` remains fail-open and the upstream gate is open. |
| C3.1 | **INCOMPLETE (C1 STOP GATE)** | Pinned Fabric client implementation/build exists; it is not certifiable against a complete approved C1 launch manifest. |
| C3.2 | **INCOMPLETE (C1 STOP GATE)** | Authoritative tick packet receipt/client log implementation and real rows exist; upstream gate is open. |
| C3.3 | **INCOMPLETE (C1 STOP GATE)** | Complete raw-action capture and real JSONL evidence exist; upstream gate is open. |
| C3.4 | **INCOMPLETE (C1 STOP GATE)** | Real MP4/frame evidence and 640x360 normalization exist; the observed lock says raw framebuffer and production client settings remain unresolved. |
| C3.5 | **INCOMPLETE (C1 STOP GATE)** | Capture diagnostics/QA reports exist for real episodes; upstream gate is open. |
| C3.6 | **INCOMPLETE (C1 STOP GATE)** | Deterministic camera/canonical return implementation and records exist; canonical reference/reconstruction evidence is absent. |
| C3.7 | **INCOMPLETE (C1 STOP GATE)** | Safe finalization markers/checksums exist; upstream gate is open. |
| C4.1 | **INCOMPLETE (C1 STOP GATE)** | Strict source readers and immutable identity are implemented and exercised on real packages; source scientific eligibility is blocked by C1. |
| C4.2 | **INCOMPLETE (C1 STOP GATE)** | Exact equality join implementation/tests exist; source scientific eligibility is blocked by C1. |
| C4.3 | **INCOMPLETE (C1 STOP GATE)** | Real package cardinality/continuity/uniqueness reports exist; source scientific eligibility is blocked by C1. |
| C4.4 | **INCOMPLETE (C1 STOP GATE)** | Official action conversion compatibility is implemented/tested; source scientific eligibility is blocked by C1. |
| C4.5 | **INCOMPLETE (C1 STOP GATE)** | A preprocessing contract compatibility code/tests exist; source scientific eligibility is blocked by C1. |
| C4.6 | **INCOMPLETE (C1 STOP GATE)** | Real `frame_map.parquet` artifacts exist; source scientific eligibility is blocked by C1. |
| C4.7 | **INCOMPLETE (C1 STOP GATE)** | Real impulse fixture/orientation evidence exists under `data/handoff_a/impulse_fixture_9440/`; source scientific eligibility is blocked by C1. |
| C4.8 | **INCOMPLETE (C1 STOP GATE)** | Immutable QA reports and SHA sidecars exist; they cannot override the C1 STOP GATE. |
| C5.1 | **INCOMPLETE (C1 STOP GATE)** | Frozen geometry convention exists; C/E marker coordinates disagree with the frozen layout geometry, so applicability is not cross-role certifiable. |
| C5.2 | **INCOMPLETE (C1 STOP GATE)** | Geometric visibility implementation/tests and real authority rows exist; source scientific eligibility is blocked by C1. |
| C5.3 | **INCOMPLETE (C1 STOP GATE)** | E detector v1 import is real and hash-bound at E commit `90855ea52b19ced3f0ce610f7d18db35070ee023`; its 1,850 rows cover `layout_01..06_ep100xx`, not either proposed C6A pilot. |
| C5.4 | **INCOMPLETE (C1 STOP GATE)** | Strict one-to-one AND join passes for the 1,850 imported rows and C remains label owner; those are not C6A rows and C1 remains open. |
| C5.5 | **INCOMPLETE (C1 STOP GATE)** | Stable event derivation/quarantine code/tests exist; source scientific eligibility is blocked by C1. |
| C6A | **INCOMPLETE** | `data/handoff_a/C6A_STATUS.md` names `layout_00_ep9410`; later C authority selects `layout_00_ep9403` for A; B's frozen receipt consumes only `layout_00_ep9441`, `layout_01_ep9442`, `layout_02_ep9432`, `layout_03_ep9443`, `layout_04_ep9444`; E registers `layout_03_ep10002` and detector rows cover only `ep100xx`. No exact C6A row set is consumed by A/B/E. The legacy layout-ID decision also says C6 pilots are engineering evidence and the C1 stop gate was never closed. |

## Person E requirement ledger (8 requirements)

| Step | Certification | Implementation, evidence, authority, validation, and handoff |
|---|---|---|
| E2.1 | COMPLETE | Real A smoke attempts and real C pilot `layout_03_ep10002` are registered with hashes/direct inputs in `docs/status/person_e_phase2_v0_1/registry_snapshot.json`; receipt status PASS, authority `4950fee1d43ae3e853faf2123904a918035d20c7`. This is not the cross-role C6A identity. |
| E2.2 | COMPLETE | Frozen calibration/held-out manifests, disjoint identities, coverage, source hashes, and chronology precede detector selection in `docs/status/person_e_phase2_v0_1/`; authority `e9af9394b93674dc735be38bb7c0c519c66cc135`. |
| E2.3 | COMPLETE | Real calibration-only detector rows/report/config and negative/corrupt behavior exist; held-out formal data was not used for selection; authorities `e9af939...`, `3930669eddc026ecb081e947f71f1855a7415904`. |
| E2.4 | COMPLETE | Six real per-layout homographies and unused-position validation exist in `person_e_phase2_step2_4_v0_4`; authority `44af0d06c47a8270991bd1b1d70031d116dd5e00`. Frozen geometry disagreement with C is a compatibility failure, not silently adapted. |
| E3.1 | COMPLETE | Frozen one-shot held-out set: 48 frames, precision 1.0 and recall 1.0, complete per-frame records; authority `ed3ca072b184ccb45dbf154d4209c5893b67f42e`. |
| E3.2 | COMPLETE | Six layouts, 36 unused probes, median wall-parallel error 0.093418 blocks and p95 0.287204 blocks; authority `bfe7d55acc1fcf0b90aca5c152672070b15e6ee7`. |
| E3.3 | COMPLETE | Real 1,850-row E-to-C empirical handoff joins one-to-one, preserves both raw channels, and leaves final `visible_flag` to C; authorities `90855ea52b19ced3f0ce610f7d18db35070ee023`, `bf09c23bb12f59acae724811eed6b82bab17c0ed`. |
| E4.1 | **INCOMPLETE** | The final v2 registry has seven runs owned only by A/B/D and 15 artifacts of types model_input, activation, fitted_probe, prediction, baseline, and metric_table. It has no Person C or Person E run/artifact record and no data, oracle, extraction, rollout, detection, or figure artifact. Forward/backward query code works for the partial graph, but it does not register every actual result-bearing workstream required by E4.1. `validation_receipt.json` saying `step4_1_complete=true` cannot substitute for the missing records. |

## Cross-role compatibility audit

| Required check | Result | Evidence |
|---|---|---|
| 1. C6A source identities match A | FAIL | C status names `layout_00_ep9410`; C/A single-pilot authority uses `layout_00_ep9403`. |
| 2. C frame/action/state/model-frame mappings match A token/activation mappings | PASS for `layout_00_ep9403` only | A records 248 exact source rows, 248 global model frames, 4,960 activation rows, zero join failures, and 347 tokens/pair. This does not establish the all-role C6A gate. |
| 3. E detector rows join one-to-one to C frame identities | PASS for E's 1,850-row production handoff; FAIL for C6A | Strict join reports zero missing/extra/duplicate/context mismatches, but contains neither `ep9403` nor `ep9410`. |
| 4. C remains owner of final `visible_flag` | PASS | Interface and strict join forbid E from writing `visible_flag`; C computes the AND rule and quarantine status. |
| 5. C-recorded E detector/homography versions match E frozen versions | PARTIAL/FAIL | Detector identity `0cadf618...` matches on the 1,850-row handoff. Frozen marker/layout world coordinates do not agree, and pre-repair U4 code rejected E homography report v0.3. The code dispatch defect was repaired; scientific geometry was not changed. |
| 6. A activation rows preserve C trajectory/model-frame identity | PASS for A's selected pilot | A6.5 reports zero source-identity join failures and no activation-key collisions. |
| 7. A E-facing provenance records resolve in E registry | FAIL for scoped A6.6 | E's accepted provenance binds later A commit `55776dc...` and ten pilots; A's single-pilot commit `e6e0340...` remains unaccepted. |
| 8. Versions, hashes, units, coordinates, layout, pose, resolution, accepted status agree | FAIL | C's frozen layout marker coordinates and E marker/homography inputs disagree; C6A identities/accepted-use basis also disagree. |
| 9. No artifact accepted by filename or row order | PASS in implementation; one portability defect repaired | Joins use explicit typed keys/hashes. The C registry validator now resolves only the exact repository-relative `data/...` suffix and still verifies byte size/SHA-256; it does not use basename or row order. |
| 10. No adapter silently changes scientific meaning | PASS for audit repairs | No identity, coordinate, visibility, detector, homography, or frozen evidence row was rewritten. The unresolved marker mismatch remains a reported failure. |

## Missing evidence and required owners

### A6.6

- Missing artifact: a Person B exact-row join/visible-position positive-control
  receipt bound to A single-pilot authority
  `e6e0340f301abb84c127034b154be55a38bdc8f6`, pilot
  `layout_00_ep9403`, activation-index SHA-256
  `473efef1eb52514c097051ec8f4501cb621f92c9ceaeb847249c7e3ae042ad55`,
  and the C accepted-manifest hash. Expected owner: Person B. Expected schema:
  the frozen Step 6.6 positive-control receipt schema, with the single-pilot
  source identity and grouped-fold result. Recommended owner branch:
  `completion/person-b-a6-6-single-pilot-receipt`.
- Missing artifact: an E immutable provenance acceptance receipt for the same
  single-pilot A run/index/chunks and direct inputs. Expected owner: Person E.
  Expected path pattern:
  `docs/status/person_e_phase6_step6_6_single_pilot_provenance_acceptance_v0_1/`.
  Prerequisite: owner-verifiable access to the A single-pilot activation
  artifacts. Recommended owner branch:
  `completion/person-e-a6-6-single-pilot-provenance`.
- After both receipts exist, Person A must publish an authority-bound A6.6
  closure that changes the single-pilot handoff from prepared to accepted.
  The ACE branch must not manufacture any of these owner receipts.

### C1.1, C1.3, C1.5, and C6A

- C1.1 missing artifact: fresh dedicated-server and production-launcher client
  startup manifest equal to an approved complete environment lock, with
  launcher/mod list, corrected and hashed `server.properties`, resource packs,
  FOV, graphics/performance settings, gamerules/time/weather, resolution, and
  visible stable-runtime checks. Expected owner: Person C. Expected schema:
  `schemas/person_c/environment_lock_v0_1.schema.json` plus hash-bound launch
  receipts. Prerequisite: clean pinned capture machine. Recommended branch:
  `completion/person-c-c1-runtime-lock`.
- C1.3 missing artifacts: six real canonical reference screenshots, each bound
  to exact environment/layout/camera/resolution identities and hashes. Expected
  owner: Person C. Expected paths should replace, via a versioned record rather
  than in-place evidence editing, the `RUNTIME EVIDENCE REQUIRED LATER` links in
  the layout contract.
- C1.5 missing artifact: completed clean reconstruction package for at least
  one layout, including automated coordinate/config comparison, new/reference
  screenshots and hashes, visible-drift result, second-operator identity/date,
  independent outcome, and final gate approval. Expected owner: Person C;
  second-operator receipt expected from the independent operator. Expected path
  pattern: `docs/reports/person_c_layout_validation_report_<run-id>.{md,json}`.
- Compatibility prerequisite: Person C must resolve the frozen
  `configs/scenes/layouts.yaml` marker geometry versus
  `data/handoff_e/markers_layout_01..06.json` through an explicit versioned
  scientific decision. No `+0.5`, layout-ID shift, or runtime `markergeom`
  adjustment may be hidden in an adapter. E must refit/revalidate only on its
  owner branch if the authoritative geometry changes.
- C6A missing artifact: one newly authority-valid accepted trajectory created
  only after the C1 stop gate closes, with a new episode ID and the complete
  media/count/state/causal/motion/scene/visibility/traceability QA bundle.
  The exact row identity set must then have owner receipts from A, B, and E.
  Expected owner: Person C, followed by A/B/E downstream owners. Recommended
  branches: `completion/person-c-c6a-after-c1`, then role-owned receipt branches.
  The ACE audit must not capture or relabel this evidence.

### E4.1

- Missing artifact: a successor immutable registry document that imports
  actual Person C data and actual Person E detection/homography records, plus
  all applicable required artifact classes (data, model input, oracle,
  extraction, activation, probe, prediction, baseline, rollout, detection,
  metric, and figure) with direct-input links and authoritative owner status.
- Missing validation: forward impact and backward provenance queries over that
  complete graph, including a query from a C source correction to affected A/E
  outputs and from a displayed result/figure to every direct input.
- Expected owner: Person E. Expected path pattern:
  `docs/status/person_e_phase4_step4_1_registry_v2_closure_v0_2/` using the
  immutable-registry v2 schema. Prerequisite: signed owner records for each
  actual artifact; placeholders are forbidden. Recommended branch:
  `completion/person-e-e4-1-full-workstream-registry`.

## Integration repairs and verification

Allowed repairs made on the ACE branch:

- Made the C registry validator portable without altering recorded provenance:
  it may resolve only an exact `data/...` repository suffix and still requires
  the declared SHA-256 and byte size. Arbitrary basenames/order remain rejected.
- Froze the visibility-interface generator to its committed C source authority
  instead of the integration branch's moving `HEAD`.
- Added fail-closed dispatch for E homography report v0.3 in the U4 localizer;
  all existing config/settings/applicability checks remain mandatory.
- Regenerated the explicitly synthetic, non-scientific Step 1.7 join report
  from the integrated contracts.

Verification results:

- Corrected C registry/visibility/U4 focused set: `30 passed`.
- Regenerated synthetic cross-role set: `34 passed, 42 subtests passed`.
- Final combined ACE-focused set: `221 passed, 4 skipped, 355 subtests
  passed`.
- Fabric server/client implementation tests: Gradle 8.3/Loom 1.4.6 offline
  build successful, `18 passed`.
- Broad CPU-compatible run before repairs: `1350 passed, 36 failed, 15 errors,
  5 skipped, 1232 subtests passed`. Remaining failures include the six real
  marker/layout geometry mismatches, owner-branch tests that intentionally
  reject an integration `HEAD` or advanced remote tip, and a Python
  3.14/NumPy-dependent frozen synthetic probe hash. The 15 errors require
  PyTorch or a currently clean pinned external MineWorld checkout; neither was
  installed/rewritten for this audit. These results are not used to promote a
  missing scientific gate.

## Required final fields

```text
PERSON_A_SCOPE_START=A0.4
PERSON_A_SCOPE_END=A6.6
PERSON_A_IN_SCOPE_REQUIREMENT_COUNT=52
PERSON_A_IN_SCOPE_COMPLETE_COUNT=51
PERSON_A_SCOPE_A0_4_THROUGH_A6_6_COMPLETE=False
PERSON_A_FIRST_INCOMPLETE_IN_SCOPE_STEP=A6.6
PERSON_A_MISSING_IN_SCOPE_EVIDENCE=[single-pilot layout_00_ep9403 B exact-row join and visible-position positive-control receipt bound to A authority e6e0340f301abb84c127034b154be55a38bdc8f6 and activation-index SHA-256 473efef1eb52514c097051ec8f4501cb621f92c9ceaeb847249c7e3ae042ad55; single-pilot E immutable provenance acceptance receipt bound to the same run/index/chunks/direct inputs; Person A authority-bound accepted A6.6 closure]

PERSON_C_SCOPE_START=C1.1
PERSON_C_SCOPE_END=C6A
PERSON_C_IN_SCOPE_REQUIREMENT_COUNT=33
PERSON_C_IN_SCOPE_COMPLETE_COUNT=2
PERSON_C_SCOPE_C1_1_THROUGH_C6A_COMPLETE=False
PERSON_C_FIRST_INCOMPLETE_IN_SCOPE_STEP=C1.1
PERSON_C_MISSING_IN_SCOPE_EVIDENCE=[C1.1 approved fresh server/client startup manifest and complete production launcher/mod/server.properties/resource-pack/FOV/graphics/runtime lock; C1.3 six traceable real canonical reference screenshots; C1.5 clean automated and second-operator reconstruction evidence; closure of the C1 STOP GATE before downstream certification; explicit versioned resolution of C frozen-layout versus E marker/homography geometry; one post-C1 accepted C6A trajectory with identical A/B/E row-consumption receipts]
PERSON_C_C6B_STARTED=False

PERSON_E_SCOPE_START=E2.1
PERSON_E_SCOPE_END=E4.1
PERSON_E_IN_SCOPE_REQUIREMENT_COUNT=8
PERSON_E_IN_SCOPE_COMPLETE_COUNT=7
PERSON_E_SCOPE_E2_1_THROUGH_E4_1_COMPLETE=False
PERSON_E_FIRST_INCOMPLETE_IN_SCOPE_STEP=E4.1
PERSON_E_MISSING_IN_SCOPE_EVIDENCE=[actual Person C and Person E run/artifact records in the final immutable registry; required data/oracle/extraction/rollout/detection/figure workstream records with owner status and direct-input links; forward-impact and backward-provenance receipts over the complete actual graph]

ACE_IDENTITY_COMPATIBILITY_PASS=False
ACE_SCHEMA_COMPATIBILITY_PASS=False
ACE_VISIBILITY_AUTHORITY_COMPATIBILITY_PASS=True
ACE_PROVENANCE_COMPATIBILITY_PASS=False
ACE_CROSS_ROLE_COMPATIBILITY_PASS=False

ACE_REQUIRED_SCOPE_COMPLETE=False
```
