# Person A Authoritative File Map

Status: Phase 1 implementation boundary map.

This document records the single authoritative repository location for each
Person A responsibility defined by the MineOcclude execution roadmap.

| Responsibility | Authoritative location | Current status |
|---|---|---|
| MineWorld adapter | `src/mineocclude/models/mineworld_adapter.py` | Skeleton |
| Activation hooks | `src/mineocclude/activations/hooks.py` | Skeleton |
| FrameTokenMap and visual-token pooling | `src/mineocclude/activations/pool.py` | Skeleton |
| Activation storage | `src/mineocclude/activations/store.py`, `store_v2.py` | Implemented; v2 used from Phase 6 |
| Activation intervention | `src/mineocclude/intervention/inject.py` | Implemented; direct-tensor tested |
| MVP orchestration | `scripts/run_mvp.py` | Implemented; synthetic mode executed |
| MVP experiment configuration | `configs/experiments/mvp.yaml` | Frozen at Step 7.1 |
| Environment verification | `scripts/check_env.py` | Skeleton |
| Environment dependency specification | `requirements.txt` | Authoritative location reserved |
| Phase 2.6-2.9 runtime-evidence validation | `src/mineocclude/models/phase2_evidence.py` | Prepared; CPU-testable |
| Phase 2.6-2.9 AWS runtime execution boundary | `src/mineocclude/models/phase2_aws.py` | Prepared; AWS GPU execution pending |
| Formal Step 2.6 rollout command | `scripts/run_phase2_rollout.py` | Prepared; AWS GPU execution pending |
| Loaded Step 2.7 architecture command | `scripts/inspect_phase2_architecture.py` | Prepared; AWS GPU execution pending |
| Step 2.8-2.9 teacher-forced command | `scripts/run_phase2_teacher_forced.py` | Prepared; AWS GPU execution pending |
| Phase 2 runtime-evidence schema | `schemas/person_a/phase2_runtime_evidence_v1.schema.json` | Additive schema v1.0 evidence contract |
| Phase 2.6-2.9 AWS execution checklist | `docs/status/person_a_phase2_aws_execution_checklist.md` | Prepared; runtime results pending |

## Phases 6.7-9.8 responsibilities

| Responsibility | Authoritative location | Roadmap step |
|---|---|---|
| Ten-pilot certification and pilot closeout | `src/mineocclude/experiments/pilot_certification.py` | 6.7, 6.8 |
| Phase 6 closeout command | `scripts/build_person_a_phase6_closeout_v0_1.py` | 6.7, 6.8 |
| Locked extraction contract | `docs/contracts/person_a_locked_extraction_contract_v1_0.md` | 6.8 |
| MVP configuration identity and freeze | `src/mineocclude/experiments/mvp_config.py` | 7.1 |
| Expected 66-cell matrix and reconciliation | `src/mineocclude/experiments/mvp_matrix.py` | 7.2 |
| Integrated stage graph | `src/mineocclude/experiments/stage_graph.py` | 7.3 |
| Run/artifact lineage and U1-U3 invocation record | `src/mineocclude/experiments/mvp_lineage.py` | 7.4, 7.7 |
| Resumable extraction queue and cardinality certification | `src/mineocclude/experiments/extraction_queue.py` | 7.5, 7.6 |
| MVP implementation closeout | `src/mineocclude/experiments/mvp_closeout.py` | 7.8 |
| Scoped residual injector and dose audits | `src/mineocclude/intervention/inject.py` | 8.1-8.4 |
| U4 manifest, runner, handoffs, classification | `src/mineocclude/intervention/rollout_manifest.py` | 8.5-8.8 |
| U4 command | `scripts/run_u4_rollouts.py` | 8.1-8.8 |
| Clean-run identity, workflow capture, repeatability | `src/mineocclude/experiments/clean_run.py` | 9.1-9.3 |
| Rehearsals, evidence chain, decision, tag record | `src/mineocclude/experiments/checkpoint.py` | 9.4-9.8 |
| Clean-run workflow definition | `configs/experiments/clean_run.yaml` | 9.2 |
| Clean-run and checkpoint command | `scripts/run_clean_mvp.py` | 9.1-9.8 |
| Handoff rehearsal runbook | `docs/runbooks/person_a_handoff_rehearsals.md` | 9.4, 9.5 |

## Boundary rule

Each responsibility above has one authoritative implementation location.

New modules that duplicate these responsibilities must not be created without
reviewing and updating this map.

Role-specific scientific logic owned by Persons B, C, D, or E must not be
silently implemented inside Person A modules.

## Review result

At the time this map was created, the repository was inspected before the
Person A skeleton was added. No pre-existing authoritative implementations
duplicated the listed Person A responsibilities.
