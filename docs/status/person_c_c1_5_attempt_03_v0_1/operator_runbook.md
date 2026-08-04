# Person C C1.5 first-operator attempt 03

Attempts 01 and 02 are preserved failed historical evidence. Attempt 02 is classified `POST_FINALIZATION_OBSERVATION_INVALID_NOT_TARGET_RETENTION_FAILURE`: target retention passed, but observation occurred after finalization. Never delete, overwrite, rename, or reuse any prior-attempt file.

**Critical timing rule:** `mineocclude warmup 2400` must run immediately before `mineocclude start layout_01 11504 202608031504 0.0 0.0 20`. This provides approximately 120 seconds before recording. `observegeometry` must execute during READY, before recording or finalization.

1. Verify a clean `completion/person-c-c1-c6a` worktree, source commit `dfe1b68e481af156ed58559cd5de0f8f27d7ea1d` as an ancestor, `spawn-animals=false`, repaired JAR SHA-256 `9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52`, and retry schedule SHA-256 `8152948688e5a9a025fc1c6d0544cdf14e6b00e4ac252b664dcc00650546f924` at `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_schedules\episode_11504.jsonl`.
2. Confirm every create-only attempt-03 evidence/output path in `attempt_03_manifest.json` is absent.
3. Start the server exactly: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\start-mineocclude-server.ps1"`
4. Authenticated client action: Open the official authenticated Minecraft Launcher; select profile fabric-loader-1.16.5 using version fabric-loader-0.15.11-1.16.5 and Game Directory C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client; click Play; confirm the authenticated account name in the client log; connect to 127.0.0.1:25565.
5. Run these server-console commands in order: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 2400`; `mineocclude start layout_01 11504 202608031504 0.0 0.0 20`. Confirm the armed log says `2400 warmup + 20 record ticks`.
6. Wait exactly 10 seconds after arming. Run `mineocclude targetstatus`. Continue only on `valid=true required=true count=1 lifecycle=READY problems=NONE` with exact UUID/tag/state/location.
7. Immediately run `mineocclude observegeometry c1_5_first_operator_attempt_03_layout_01`. Confirm the create-only receipt was written to `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\c1_5_first_operator_attempt_03_layout_01.json` before continuing.
8. Immediately press F2 and copy that new 640x360 PNG byte-for-byte to `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\c1_5_evidence\first_operator_attempt_03_layout_01.png`.
9. Immediately run `mineocclude stop`. Confirm episode 11504 aborted during warmup and never entered recording.
10. Disconnect, Quit Game, issue server `stop`, and wait for clean exits.
11. Copy `first_operator_attempt_03_attestation.template.json` to `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\c1_5_evidence\first_operator_attempt_03_attestation.json`, set `template=false`, fill every ordering attestation, and leave the template unchanged.
12. Run: `python scripts/person_c/ingest_c1_5_attempt_03_runtime.py --geometry-receipt "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\mineocclude_observations\c1_5_first_operator_attempt_03_layout_01.json" --screenshot "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\c1_5_evidence\first_operator_attempt_03_layout_01.png" --attestation "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\c1_5_evidence\first_operator_attempt_03_attestation.json" --output "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\c1_5_evidence\first_operator_attempt_03_ingested.json"`

Episode 11502/seed 202608031502 remains reserved for the independent second operator.
