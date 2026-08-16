# Stage-2 authority → implementation traceability

| Authority gate | Implementation | Adversarial coverage |
|---|---|---|
| Separate authorization and genuine Stage-1 PASS | `require_stage2_authorization` re-evaluates the bound on-disk evidence; repeated by `stage_unit_driver.require_capture_authorization` | fake/all-PASS decision, edited evidence, wrong/stale bindings, direct command bypass |
| Authority, both manifests, Stage-1 evidence, decision, commit, provenance, namespace | Canonical payload hash plus exact on-disk SHA comparisons | each binding mutated independently |
| Post-Stage-1 target materialization | `build_manifests.materialize_stage2` rejects draft/FAIL, uses measured stable-hidden intervals | draft template rejected; exact 19-row requirement |
| Causal render↔state labels | `causal_fir_targets`; independently rerun from durable-inventory-bound server state by capture driver and Stage-2 backend | raw same-tick labels differ; pure-delay kernel and rebound local state rejected |
| Durability and remote integrity | unit runner, `DurableController`, and every direct backend predecessor boundary rehash remote manifest/objects | stale state, local PASS summary, and missing remote object rejected |
| Unit/run identity | capture receipt bindings and exact capture-unit set | missing/copied identity fails physical gate |
| Exact path/state and WALL≡NO_WALL pair | independent path receipt and `validate_physical_gate_receipts` | pair path mismatch rejected |
| Clock alignment | complete causal FIR history and qualified Stage-1 decision kernel | unresolved/incomplete mapping rejected |
| Stable visibility | measured Stage-1 intervals applied to target FIR positions | missing physical check rejected |
| Physical support | every FIR target must remain in frozen lane and measured hidden interval | out-of-support/transition target fails |
| Hidden-row validity and row count | exactly 19 WALL hidden rows; NO_WALL visible controls | fewer rows or contamination fails |
| Zero contamination | explicit row-level contamination evidence | any listed class fails |
| Runtime/apparatus provenance | independently derived Git/JDK/JAR/mod/renderer/detector/camera/layout receipts | self-assertion and identity mismatch fail |
| Complete 25-pair / 50-capture coverage | exact manifest identity set and WALL/NO_WALL pairing | missing receipt/pair fails |
| Frozen fold × phase allocation | runtime `validate_stage2_manifest_design` enforces exact five folds × five phases, authority direction map, and capture pairing | fold/phase confounding, speed, direction, and capture allocation tampering fail |
| Layer-4 only extraction | physical-gate receipt required before `Layer4Extractor`; exact shape/dtype | extraction cannot precede gate |
| BEST-K per-scene RMSE | corrected frozen 2× P2 BEST-K ceiling | explicit qualification check |
| BEST-K per-scene macro/bootstrap R² | `summary` whole-trajectory bootstrap | explicit qualification check |
| WALL BEST-K versus training-only time baseline | `training_time_baseline` plus strict RMSE comparison | neural RMSE not beating baseline fails |
| Time-confound R² on tau 1–15 | separate tau-restricted baseline summary | threshold failure is controlling |
| FULL non-rescue | terminal reads BEST-K status; FULL is report-only | terminal records `FULL_may_rescue=false` |
| Confirmatory boundary | all receipts and terminal keep authorization false | no development PASS can authorize confirmation |
