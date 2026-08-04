# Person E v0.4 six-layout calibration-image session

This is one non-scientific calibration session for one authenticated operator. It is not C1.5, C6A, C6B, or a second-operator task. Do not start if any create-only receipt or screenshot destination in `session_manifest.json` exists.

1. Start the isolated server with `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\start-mineocclude-server.ps1`.
2. Launch the isolated authenticated Fabric client with `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\start-mineocclude-client.ps1`.
3. Connect to `127.0.0.1:25565`. Confirm normal gameplay at 1920x1046, FOV Normal (70.0), with no pause menu, chat, inventory, or F3 overlay.
4. In the server console apply these session controls exactly once, in order: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 12000`.
5. For each row below, do not press F2 until the receipt-written confirmation appears. If targetstatus fails, recording starts, or any destination already exists, stop and preserve the session as failed; do not reuse paths.

| Layout | Start | Observe | Receipt | Screenshot destination |
|---|---|---|---|---|
| `layout_01` | `mineocclude start layout_01 12701 202608031701 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_layout_01` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_layout_01.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_v0_1\layout_01.png` |
| `layout_02` | `mineocclude start layout_02 12702 202608031702 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_layout_02` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_layout_02.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_v0_1\layout_02.png` |
| `layout_03` | `mineocclude start layout_03 12703 202608031703 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_layout_03` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_layout_03.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_v0_1\layout_03.png` |
| `layout_04` | `mineocclude start layout_04 12704 202608031704 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_layout_04` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_layout_04.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_v0_1\layout_04.png` |
| `layout_05` | `mineocclude start layout_05 12705 202608031705 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_layout_05` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_layout_05.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_v0_1\layout_05.png` |
| `layout_06` | `mineocclude start layout_06 12706 202608031706 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_layout_06` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_layout_06.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_v0_1\layout_06.png` |

For every layout: run the Start command; wait at least 10 seconds; run `mineocclude targetstatus`; require `valid=true required=true count=1 lifecycle=READY problems=NONE`; immediately run Observe; wait for the receipt-written confirmation; return to normal unobstructed gameplay; press F2 exactly once; immediately run `mineocclude stop`; require `episode <id> aborted during warmup`; then continue to the next row. Recording must never begin.

After layout_06: disconnect and quit the client, then stop the server cleanly. Preserve both `logs\latest.log` files. Run the finalizer once and type `YES` only if all six screenshots meet the unobstructed-gameplay rule and the client was authenticated:

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Person-C-C1-C6A\scripts\person_c\finalize-e-refit-calibration-v0-4.ps1"`

The finalizer discovers the six raw F2 files from the same client log, validates chronology and literal v0.4 receipts, copies them create-only, fills hashes automatically, and leaves all Person E image-coordinate fields null. Do not manually edit preparation JSON.
