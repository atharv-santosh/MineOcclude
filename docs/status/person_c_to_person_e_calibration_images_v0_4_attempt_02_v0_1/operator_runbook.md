# Person E v0.4 six-layout calibration Attempt 02

Attempt 01 is preserved unchanged and classified exactly as `CALIBRATION_SCREENSHOT_FRAMEBUFFER_MISMATCH_640X360_EXPECTED_1920X1046`. Never delete, rename, overwrite, resize, upscale, or certify its files. This task is not C6A and does not modify Person E.

## Mandatory framebuffer preflight — before every calibration episode

1. In Minecraft Launcher, edit the authenticated `MineOcclude C1 Runtime` installation. Set Resolution to `1920x1046`; its inspected value was `640x360`, which caused Attempt 01 to remain 640x360.
2. Start the isolated server with `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\start-mineocclude-server.ps1`.
3. Launch that authenticated Launcher installation. Connect to `127.0.0.1:25565`.
4. Keep `fullscreen=false`, FOV Normal (70.0), GUI scale 2, `overrideWidth=0`, and `overrideHeight=0`. Use a display/window session capable of the target. Resize the windowed client only if needed; do not infer success from maximization, scaling, or appearance.
5. Confirm normal unobstructed gameplay and that no MineOcclude episode is running. Do not run any `mineocclude start` command yet.
6. Press F2 exactly once. This is the disposable preflight screenshot, never a layout screenshot.
7. Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Person-C-C1-C6A\scripts\person_c\verify-e-refit-calibration-attempt-02-framebuffer.ps1"`.
8. Continue only if it prints `FRAMEBUFFER_PREFLIGHT_PASS=True` and `FRAMEBUFFER=1920x1046`. Any other dimensions fail closed. The script copies the PNG and writes its path, size, dimensions, and SHA-256 under a distinct external preflight evidence directory.

## Session controls and six layouts

After the successful preflight, apply these server-console controls exactly once in order: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 12000`.

Do not begin if any Attempt 02 receipt or canonical screenshot path already exists.

| Layout | Start | Fresh observegeometry | Create-only receipt | Canonical screenshot |
|---|---|---|---|---|
| `layout_01` | `mineocclude start layout_01 12711 202608041701 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_attempt_02_layout_01` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_attempt_02_layout_01.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_attempt_02_v0_1\e_refit_calibration_v0_4_attempt_02_layout_01.png` |
| `layout_02` | `mineocclude start layout_02 12712 202608041702 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_attempt_02_layout_02` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_attempt_02_layout_02.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_attempt_02_v0_1\e_refit_calibration_v0_4_attempt_02_layout_02.png` |
| `layout_03` | `mineocclude start layout_03 12713 202608041703 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_attempt_02_layout_03` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_attempt_02_layout_03.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_attempt_02_v0_1\e_refit_calibration_v0_4_attempt_02_layout_03.png` |
| `layout_04` | `mineocclude start layout_04 12714 202608041704 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_attempt_02_layout_04` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_attempt_02_layout_04.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_attempt_02_v0_1\e_refit_calibration_v0_4_attempt_02_layout_04.png` |
| `layout_05` | `mineocclude start layout_05 12715 202608041705 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_attempt_02_layout_05` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_attempt_02_layout_05.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_attempt_02_v0_1\e_refit_calibration_v0_4_attempt_02_layout_05.png` |
| `layout_06` | `mineocclude start layout_06 12716 202608041706 0.0 0.0 20` | `mineocclude observegeometry e_refit_calibration_v0_4_attempt_02_layout_06` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\e_refit_calibration_v0_4_attempt_02_layout_06.json` | `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\e_refit_calibration_v0_4_attempt_02_v0_1\e_refit_calibration_v0_4_attempt_02_layout_06.png` |

For every layout: start the fresh episode; wait at least ten seconds; run `mineocclude targetstatus`; require exactly `valid=true required=true count=1 lifecycle=READY problems=NONE`; run the fresh observegeometry command; wait for the receipt-written confirmation; switch to normal unobstructed gameplay; press F2 exactly once; immediately run `mineocclude stop`; require warmup abort; and require recording never started.

After layout_06, disconnect and quit the client, then stop the server cleanly. Run the finalizer once:

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Person-C-C1-C6A\scripts\person_c\finalize-e-refit-calibration-v0-4-attempt-02.ps1"`

The finalizer first revalidates preserved Attempt 01, the 1920x1046 preflight, append-only server/client sessions, strict server.properties semantics, all six chronologies, exactly six in-window layout F2 events, and all six PNG dimensions. The preflight F2 occurs before the first arm and is explicitly forbidden as layout input. Type `YES` once only when prompted and only if the unobstructed-gameplay/authenticated-operator statement is true.

The finalizer only creates new Attempt 02 evidence; it never edits runtime evidence in place, fits a homography, runs C6A, or fills Person E image points.
