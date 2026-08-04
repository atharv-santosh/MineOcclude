# Person C runtime geometry comparison v0.2

Classification: `NEITHER_GEOMETRY_MATCHES_RUNTIME`.

The comparison is literal. Runtime top-face centres are compared to C's literal `world_blocks` values and E's literal top-face-centre values without offsets, layout-ID shifts, renumbering, or adapters. Every layout has zero of four marker matches to C and zero of four to E. C's wall and camera declarations match all six receipts; C's smooth-stone arena declaration does not match the observed grass floor bounds.

| Layout | Color | Runtime top-face centre xyz | Runtime - C xyz | Runtime - E xyz |
|---|---|---:|---:|---:|
| layout_01 | blue | `[-5.5, 4.0, 4.5]` | `[1.5, 0.0, 3.5]` | `[1.0, 0.0, 3.0]` |
| layout_01 | yellow | `[6.5, 4.0, 4.5]` | `[-0.5, 0.0, 3.5]` | `[-1.0, 0.0, 3.0]` |
| layout_01 | lime | `[-7.5, 4.0, 8.5]` | `[-0.5, 0.0, 3.5]` | `[-1.0, 0.0, 3.0]` |
| layout_01 | white | `[8.5, 4.0, 8.5]` | `[1.5, 0.0, 3.5]` | `[1.0, 0.0, 3.0]` |
| layout_02 | blue | `[4.5, 4.0, -5.5]` | `[3.5, 0.0, 1.5]` | `[4.0, 0.0, -3.0]` |
| layout_02 | yellow | `[4.5, 4.0, 6.5]` | `[3.5, 0.0, -0.5]` | `[4.0, 0.0, 3.0]` |
| layout_02 | lime | `[8.5, 4.0, -7.5]` | `[3.5, 0.0, -0.5]` | `[1.0, 0.0, 0.0]` |
| layout_02 | white | `[8.5, 4.0, 8.5]` | `[3.5, 0.0, 1.5]` | `[1.0, 0.0, 0.0]` |
| layout_03 | blue | `[-6.5, 4.0, 4.5]` | `[1.5, 0.0, 3.5]` | `[-3.0, 0.0, 4.0]` |
| layout_03 | yellow | `[7.5, 4.0, 4.5]` | `[-0.5, 0.0, 3.5]` | `[3.0, 0.0, 4.0]` |
| layout_03 | lime | `[-8.5, 4.0, 8.5]` | `[-0.5, 0.0, 3.5]` | `[0.0, 0.0, 1.0]` |
| layout_03 | white | `[9.5, 4.0, 8.5]` | `[1.5, 0.0, 3.5]` | `[0.0, 0.0, 1.0]` |
| layout_04 | blue | `[-5.5, 4.0, 6.5]` | `[1.5, 0.0, 4.5]` | `[1.0, 0.0, 4.0]` |
| layout_04 | yellow | `[6.5, 4.0, 6.5]` | `[-0.5, 0.0, 4.5]` | `[-1.0, 0.0, 4.0]` |
| layout_04 | lime | `[-7.5, 4.0, 10.5]` | `[-0.5, 0.0, 4.5]` | `[-1.0, 0.0, 4.0]` |
| layout_04 | white | `[8.5, 4.0, 10.5]` | `[1.5, 0.0, 4.5]` | `[1.0, 0.0, 4.0]` |
| layout_05 | blue | `[-4.5, 4.0, 3.5]` | `[1.5, 0.0, 2.5]` | `[1.0, 0.0, 2.0]` |
| layout_05 | yellow | `[5.5, 4.0, 3.5]` | `[-0.5, 0.0, 2.5]` | `[-1.0, 0.0, 2.0]` |
| layout_05 | lime | `[-6.5, 4.0, 7.5]` | `[-0.5, 0.0, 2.5]` | `[-1.0, 0.0, 2.0]` |
| layout_05 | white | `[7.5, 4.0, 7.5]` | `[1.5, 0.0, 2.5]` | `[1.0, 0.0, 2.0]` |
| layout_06 | blue | `[5.5, 4.0, -6.5]` | `[3.5, 0.0, 1.5]` | `[3.0, 0.0, 1.0]` |
| layout_06 | yellow | `[5.5, 4.0, 7.5]` | `[3.5, 0.0, -0.5]` | `[3.0, 0.0, -1.0]` |
| layout_06 | lime | `[9.5, 4.0, -8.5]` | `[3.5, 0.0, -0.5]` | `[3.0, 0.0, -1.0]` |
| layout_06 | white | `[9.5, 4.0, 9.5]` | `[3.5, 0.0, 1.5]` | `[3.0, 0.0, 1.0]` |

The accepted additive successor is `person-c-layout-config-v0.4` at `configs/scenes/layouts_v0_4.yaml`. The legacy v0.3 file and every E file remain historical evidence and were not edited.
