# Person C C1.5 first-operator attempt 02

Attempt 01 is preserved and classified `POST_FINALIZATION_OBSERVATION_INVALID_NOT_TARGET_RETENTION_FAILURE`. Its target-retention behavior passed; only the post-finalization observation receipt is invalid. Never delete, rename, overwrite, or edit any attempt-01 file.

**Critical timing warning:** `observegeometry` must execute during the 1200-tick warmup and before recording or episode finalization. If recording starts first, stop and prepare a new successor attempt; never reuse these create-only paths.

1. Verify a clean `completion/person-c-c1-c6a` worktree, source commit `8cbf09bc59ff0cbe0e3af5ec075593349e910a34` as an ancestor, `spawn-animals=false`, repaired JAR SHA-256 `9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52`, and retry schedule SHA-256 `acff4ec8e22ecc04459f18780d4ce59153e2615385fd13291c4c92ac9ca35b8b` at `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_schedules\episode_11503.jsonl`.
2. Confirm every create-only attempt-02 receipt/evidence/output path in `attempt_02_manifest.json` is absent.
3. Start the server exactly: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\start-mineocclude-server.ps1"`
4. Authenticated client action: Open the official authenticated Minecraft Launcher; select profile fabric-loader-1.16.5 using version fabric-loader-0.15.11-1.16.5 and Game Directory C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client; click Play; confirm the authenticated account name in the client log; connect to 127.0.0.1:25565.
5. At the server console run: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 1200`; `mineocclude start layout_01 11503 202608031503 0.0 0.0 20`.
6. Wait exactly 10 seconds. Run `mineocclude targetstatus`. Continue only if it reports `valid=true required=true count=1 lifecycle=READY problems=NONE` plus the expected UUID/tag/state/location fields.
7. Immediately run `mineocclude observegeometry c1_5_first_operator_attempt_02_layout_01`. Require the create-only receipt `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\c1_5_first_operator_attempt_02_layout_01.json` to be written while lifecycle remains READY.
8. Immediately press F2 and copy that new 640x360 PNG byte-for-byte to `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\c1_5_evidence\first_operator_attempt_02_layout_01.png`.
9. Immediately run `mineocclude stop`. Do not wait for recording. Confirm the log says episode 11503 aborted during warmup and never says recording started.
10. Disconnect, Quit Game, issue server `stop`, and wait for clean client/server exits.
11. Copy `first_operator_attempt_02_attestation.template.json` to `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\c1_5_evidence\first_operator_attempt_02_attestation.json`, set `template=false`, fill all operator/timing/ordering attestations, and do not edit the template.
12. Run: `python scripts/person_c/ingest_c1_5_attempt_02_runtime.py --geometry-receipt "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\c1_5_first_operator_attempt_02_layout_01.json" --screenshot "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\c1_5_evidence\first_operator_attempt_02_layout_01.png" --attestation "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\c1_5_evidence\first_operator_attempt_02_attestation.json" --output "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\c1_5_evidence\first_operator_attempt_02_ingested.json"`

The independent second operator remains reserved as episode 11502 with seed 202608031502; attempt 02 must not consume it.
