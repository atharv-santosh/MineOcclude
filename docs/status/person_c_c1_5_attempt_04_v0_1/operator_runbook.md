# Person C C1.5 first-operator attempt 04

Attempts 01, 02, and 03 are preserved failed historical evidence. Attempt 03 is classified `GEOMETRY_RECEIPT_VALID_BUT_SCREENSHOT_AND_ABORT_OCCURRED_AFTER_RECORDING_STARTED`. Never reuse, edit, delete, rename, overwrite, or certify any attempt-01 through attempt-03 runtime artifact.

This is the final timing-safe first-operator retry. The 12000-tick warmup provides approximately ten minutes (600 seconds). **Do not wait for recording to start.** Wait only for the receipt-written confirmation, then press F2 once and stop immediately.

1. Start server exactly: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\start-mineocclude-server.ps1"`
2. Connect authenticated client using the isolated Person C client profile and `127.0.0.1:25565`.
3. Run session controls: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`.
4. Set warmup 12000: `mineocclude warmup 12000`.
5. Start attempt-04 episode: `mineocclude start layout_01 11505 202608031505 0.0 0.0 20`. Require the armed log to say `12000 warmup + 20 record ticks`.
6. Wait ten seconds.
7. Run `mineocclude targetstatus` and require `valid=true required=true count=1 lifecycle=READY problems=NONE`.
8. Immediately run `mineocclude observegeometry c1_5_first_operator_attempt_04_layout_01`.
9. Wait only for the receipt-written confirmation at `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\c1_5_first_operator_attempt_04_layout_01.json`.
10. Immediately press F2 once.
11. Immediately run `mineocclude stop`.
12. Confirm the server reports episode 11505 was aborted during warmup. If recording starts, this attempt is invalid.
13. Disconnect and quit the client.
14. Stop the server cleanly.
15. Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Person-C-C1-C6A\scripts\person_c\finalize-c1-5-attempt-04.ps1"` once. After its automated checks, type the single confirmation `YES`; do not edit JSON manually.

Episode 11502/seed 202608031502 remains reserved for the independent second operator.
