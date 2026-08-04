# Second operator attempt 02 — exact instructions

You must be the same second human who performed attempt 01, and you must remain a different human from the first operator. Use the same authenticated account `Santa313`. Attempt 01 is preserved but invalid as `SCREENSHOT_CAPTURED_BEFORE_GEOMETRY_RECEIPT_CONFIRMATION`; do not edit or certify it.

1. Start a fresh isolated server/client session and connect to `127.0.0.1:25565`.
2. Run, in order: `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 12000`; `mineocclude start layout_01 11506 202608031506 0.0 0.0 20`.
3. Wait at least 10 seconds after the episode-armed message.
4. Run `mineocclude targetstatus`. Continue only for `valid=true required=true count=1 lifecycle=READY problems=NONE`.
5. Run `mineocclude observegeometry c1_5_second_operator_attempt_02_layout_01`.
6. Wait until the server prints the receipt-written confirmation for `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\c1_5_second_operator_attempt_02_layout_01.json`.
7. **Do not press F2 before that receipt-written confirmation.** After it appears, return to normal gameplay and press F2 exactly once.
8. Immediately run `mineocclude stop`. Require `episode 11506 aborted during warmup`.
9. If `episode 11506 recording started` appears, stop and report failure; do not finalize.
10. Quit the client and stop the server cleanly, preserving `logs\latest.log` in both roots.
11. Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Person-C-C1-C6A\scripts\person_c\finalize-c1-5-second-operator-attempt-02.ps1"` and type `YES` only if you are the same attempt-01 second human and remain independent from the first operator.

The 12000-tick warmup is approximately 600 seconds. The receipt, F2 screenshot, and stop must all occur during warmup. All attempt-02 runtime output paths are create-only.
