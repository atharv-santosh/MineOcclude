# 03 — Clock-Domain Reconstruction

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**

## The chain, with the physical delay at each hop

```
  [SERVER ENTITY STATE]  EpisodeManager.tick(): sheep position updated from the frozen
   tick N                 noise schedule; geometric_visible computed by one ray to
        |                 (sheepX, sheepY+0.5, sheepZ)
        |  0 ticks        ServerStateLogger.write() -> server_state.jsonl[N]
        v                 (server_epoch_nanos stamped here)
  [SERVER TICK N]
        |
        |  ~1.9 ms wall clock (client_recv_nanos - server_epoch_nanos, measured)
        v                 but ZERO simulated ticks: the world is held in lockstep
  [NETWORK UPDATE]        TickSyncPacket delivered; vanilla entity tracker position
        |                 packets are a SEPARATE, unsynchronised stream
        |  >= 0 ticks     <-- FIRST UNMEASURED HOP (historical)
        v
  [CLIENT ENTITY STATE]   vanilla client lerps the tracked entity toward the received
        |                 position over several client ticks
        |  ~2-3 ticks     <-- SECOND UNMEASURED HOP (historical)
        v
  [CLIENT RENDER]         world drawn with the INTERPOLATED entity position
        |
        |  ~1 tick        capture runs at END_CLIENT_TICK and reads "the last fully
        v                 completed frame" (mod comment, MineOccludeClient.java:88-96)
  [CAPTURE FRAME]         FrameCapture.capture() -> frames/{N:06d}.png
        |                 client_tick.jsonl[N]: render_frame_idx = N
        |  0 ticks
        v
  [VIDEO / MODEL FRAME]   derive_artifacts(): model_frame_idx := server_tick := N
        |                 <-- THE IDENTITY ASSERTION. 20 Hz, 1 tick / model frame.
        |  0 ticks
        v
  [ACTIVATION ROW]        p2d_extract: context = frames[N-15 .. N], layer-4 activation
        |                 at the final position
        |  0 ticks
        v
  [GROUND-TRUTH TARGET]   p2e_analyze.load(): world_x := coordinates[N].world_x
                          := server_state[N].sheep_x     <-- verified identical, max|Δ| = 0.0
```

**Total measured lag from SERVER ENTITY STATE to the entity geometry in the CAPTURE FRAME:
3.364 server ticks (small-sample t interval [3.185, 3.542]; trajectory bootstrap
[3.219, 3.522]).**

## Where the assumption of synchrony is made explicit in code

`p3_run_sequential.py::derive_artifacts` (and its P2 equivalent) asserts, per row:

```python
key = {"trajectory_id": expected_id, "model_frame_idx": index,
       "server_tick": index, "render_frame_idx": index, "action_idx": index}
```

Four clock domains are collapsed to one integer. The assertion is *enforced* — a mismatch raises
`CAPTURE_IDENTITY_MISMATCH` — so the pipeline is internally consistent. What was never
established is that the **entity geometry inside** frame `index` corresponds to server tick
`index`. It does not.

## Which hops were previously validated, and which were not

| Hop | Historical evidence | Adequate? |
|---|---|---|
| action_idx → camera response | `temporal_alignment`: `action_idx 1 → effect_server_tick 2`, `visual_before/after_model_frame_idx 1/2`; `impulse_orientation`: camera component-1 step visible i→i+1 | **Yes, for the camera** |
| **entity server state → entity render** | **none** — `evidence_scope = "synthetic_contract_only"` | **NO — this is the defect** |
| render → capture frame | frame/state/action cardinality equality; stale-framebuffer detector | yes (cardinality only) |
| capture → model frame | 1:1 at 20 Hz, asserted | yes |
| model frame → activation row | `range(target-15, target+1)`, teacher forced | yes |
| activation row → target label | `coordinates[frame].world_x ≡ server_state[frame].sheep_x`, verified max\|Δ\| = 0.0 | yes (identity is exact — but it is the *wrong* instant) |

The camera is static in this apparatus, so camera-based alignment evidence could never have
revealed an entity-interpolation lag. **Validating the wrong hop is the root of the defect.**

## Terminology now enforced in code

`src/mineocclude/prospective/clock_domains.py` makes each of these a distinct
`ClockDomain` member and refuses (`UnresolvedAlignment`) to combine indices from different
domains without an explicit alignment. `TimebaseSpec` never assumes 1 tick per model frame.
