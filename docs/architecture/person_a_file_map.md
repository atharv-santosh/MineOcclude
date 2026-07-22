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