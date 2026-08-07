# Person C C1.1 successor runtime actions

This successor binds the existing C1.1 observation procedure to `person-c-c1-runtime-baseline-v0.2`, the provisioned Java 17 server/client roots, and the built JAR at source commit `99b78b6578d17cffc0b5679118a42632284ce7f7`. It does not supersede, edit, or reinterpret frozen geometry evidence. It assigns no accepted geometry version.

1. Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\start-mineocclude-server.ps1"`.
2. Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\start-mineocclude-client.ps1"` and use the GUI to verify a 640x360 window/framebuffer, the pinned client options, vanilla-only resource packs, and direct connection to `127.0.0.1:25565`.
3. At the server console, run `mineocclude markergeomstatus` first. Preserve the exact logged status; do not run `markergeom` or `markergeomreset`.
4. Follow section 7 of `docs/status/person_c_c1_runtime_observation_v0_1/operator_runbook.md` exactly: set the six observation controls, then execute the six create-only layout receipt sequences listed in `runtime_observation_readiness.json`.
5. Preserve and hash every runtime receipt. Stop on any collision, missing player camera, layout mismatch, unexpected override, block mismatch, or capture start.
6. Only after all six receipts and canonical visual checks validate may a new geometry-authority package be considered. Do not begin C6A in this step.

Remaining work is deliberately manual because it requires the GUI and direct runtime/visual observation. Provisioning itself has no unresolved blocker.