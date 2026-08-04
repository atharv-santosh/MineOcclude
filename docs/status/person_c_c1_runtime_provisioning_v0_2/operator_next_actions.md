# Person C C1 isolated runtime: operator next actions

Deterministic provisioning is complete under baseline `person-c-c1-runtime-baseline-v0.2`. The server smoke passed and stopped cleanly. The client was not launched because the remaining gate is GUI and direct observation.

1. Start the server with: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\start-mineocclude-server.ps1"`
2. Start the client with: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\start-mineocclude-client.ps1"`
3. In the isolated client, confirm the 640x360 window, options, framebuffer size, and the absence of inherited resource packs; connect directly to `127.0.0.1:25565`.
4. Continue with `docs/status/person_c_c1_runtime_observation_v0_2/operator_next_actions.md`. The first server-console command is `mineocclude markergeomstatus`.
5. Stop before geometry adjudication if any runtime receipt, camera state, marker state, or pixel-setting check fails. Do not begin C6A.

No account login is expected because this isolated loopback baseline uses `online-mode=false`. No personal `.minecraft` data may be copied into either root.