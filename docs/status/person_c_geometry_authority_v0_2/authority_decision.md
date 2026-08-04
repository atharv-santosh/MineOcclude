# Person C geometry authority decision v0.2

## Decision

`NEITHER_GEOMETRY_MATCHES_RUNTIME`. The complete fresh-runtime receipts prove a single internally consistent builder geometry, but that literal geometry is neither historical C v0.3 nor E. The accepted owner label is `SUCCESSOR`, and the additive C-governed accepted version is `person-c-layout-config-v0.4`.

## Evidence

The decision is bound to source commit `99b78b6578d17cffc0b5679118a42632284ce7f7`, MineOcclude JAR SHA-256 `652fe5e34f0ee186a3b6c036ab70b1bf02e9373c985eeaa218e3ef28be087bda`, the final server/client logs, server properties, client options, identical 46-JAR server/client inventories, five session screenshots, and six distinct observation-only geometry receipts. All six receipts have override `enabled=false` and signature `null/null/null/null`; each validates all floor, wall, marker, camera, world-state, time, weather, and gamerule fields.

For every layout, the runtime wall axis and camera agree with historical C, while the floor material/bounds and every literal marker coordinate do not. No layout's four runtime marker coordinates equal E's four coordinates. Exact deltas are in `geometry_comparison_report.json` and `geometry_comparison_report.md`.

## Versioning and downstream impact

Historical C v0.3 requires no mutation. It is superseded only for new evidence by additive `configs/scenes/layouts_v0_4.yaml`; historical artifacts remain addressable and valid evidence of their own states. All six E homographies/correspondence-dependent artifacts require refitting before they can be applied to v0.4 captures. No E-owned file or frozen scientific evidence is edited here.

Supersession does not redirect historical paths and does not apply offsets, `+0.5` corrections, layout-ID shifts, coordinate renumbering, or compatibility adapters. New screenshots, homographies, and capture manifests must name v0.4 explicitly and bind its file hash.

## Gates before reconstruction or C6A

C1.1 and C1.3 close on the complete environment/geometry receipts and the authoritative FOV/raw-framebuffer screenshot pair. C1.5 does not close: a genuinely independent second-operator receipt remains required. Moreover, the server log proves the explicitly spawned magenta sheep is alive at warmup tick 0 and removed at tick 1 in every layout under `spawn-animals=false`. That target-retention defect must be corrected, built into a newly hash-bound JAR, and fresh-runtime validated without weakening the environment contract before C1.5 or C6A execution.

C6A also requires new hash-bound scientific noise schedules and a new trajectory identity. The blocked manifest does not reuse `layout_00_ep9403`, does not authorize execution, and does not start paid compute or C6B.
