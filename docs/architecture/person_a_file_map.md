# Person A Authoritative File Map

Status: Phase 1 implementation boundary map.

This document records the single authoritative repository location for each
Person A responsibility defined by the MineOcclude execution roadmap.

| Responsibility | Authoritative location | Current status |
|---|---|---|
| MineWorld adapter | `src/mineocclude/models/mineworld_adapter.py` | Skeleton |
| Activation hooks | `src/mineocclude/activations/hooks.py` | Skeleton |
| FrameTokenMap and visual-token pooling | `src/mineocclude/activations/pool.py` | Skeleton |
| Activation storage | `src/mineocclude/activations/store.py` | Skeleton |
| Activation intervention | `src/mineocclude/intervention/inject.py` | Skeleton |
| MVP orchestration | `scripts/run_mvp.py` | Skeleton |
| MVP experiment configuration | `configs/experiments/mvp.yaml` | Skeleton |
| Environment verification | `scripts/check_env.py` | Skeleton |
| Environment dependency specification | `requirements.txt` | Authoritative location reserved |
| Phase 2.6-2.9 runtime-evidence validation | `src/mineocclude/models/phase2_evidence.py` | Prepared; CPU-testable |
| Phase 2.6-2.9 AWS runtime execution boundary | `src/mineocclude/models/phase2_aws.py` | Prepared; AWS GPU execution pending |
| Formal Step 2.6 rollout command | `scripts/run_phase2_rollout.py` | Prepared; AWS GPU execution pending |
| Loaded Step 2.7 architecture command | `scripts/inspect_phase2_architecture.py` | Prepared; AWS GPU execution pending |
| Step 2.8-2.9 teacher-forced command | `scripts/run_phase2_teacher_forced.py` | Prepared; AWS GPU execution pending |
| Phase 2 runtime-evidence schema | `schemas/person_a/phase2_runtime_evidence_v1.schema.json` | Additive schema v1.0 evidence contract |
| Phase 2.6-2.9 AWS execution checklist | `docs/status/person_a_phase2_aws_execution_checklist.md` | Prepared; runtime results pending |

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
