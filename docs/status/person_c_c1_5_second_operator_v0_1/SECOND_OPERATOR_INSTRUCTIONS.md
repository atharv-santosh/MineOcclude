# Independent second-operator instructions

You must be a different person from the first operator. Sign in with your own authenticated Minecraft account; do not use `overatedusername`. Do not use the first operator's memory, screenshot, receipt, or result to reconstruct the scene.

1. Start the server by running `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\start-mineocclude-server.ps1"`.
2. Open the official authenticated Minecraft Launcher. Select `fabric-loader-1.16.5` (version `fabric-loader-0.15.11-1.16.5`), set Game Directory to `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client`, and click Play.
3. In Multiplayer, connect to `127.0.0.1:25565`.
4. In the server console, run exactly: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 12000`; `mineocclude start layout_01 11502 202608031502 0.0 0.0 20`.
5. Wait exactly 10 seconds.
6. Run `mineocclude targetstatus`. Continue only if it says `valid=true required=true count=1 lifecycle=READY problems=NONE`.
7. Immediately run `mineocclude observegeometry c1_5_second_operator_attempt_01_layout_01` and wait only until the receipt-written confirmation appears.
8. Return to normal gameplay and immediately press F2 once. Do not photograph chat, a menu, or a paused screen.
9. Immediately run `mineocclude stop`. Require `episode 11502 aborted during warmup`; if recording starts, stop and report failure.
10. Disconnect, quit Minecraft, run `stop` in the server console, and wait for both client and server to close cleanly.
11. Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Person-C-C1-C6A\scripts\person_c\finalize-c1-5-second-operator.ps1"` once. When its checks pass, type exactly `YES`. Do not edit JSON.
