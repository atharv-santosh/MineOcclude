# Person C C1.1 fresh-runtime observation runbook

## State and stop rule

This is a preparation runbook, not runtime evidence. The starting audit commit is `de16fabef5dfe326cbff71118c99d32234337a53`. Do not choose C or E geometry, assign a geometry version, create `person_c_geometry_authority_v0_2`, or take canonical scientific screenshots while any receipt is pending.

The preparation host does not currently have `C:\Users\lollo\mineocclude-server`, `C:\Users\lollo\mineocclude-client`, or a Minecraft 1.16.5 Fabric production profile. The repository has no production server/client launcher. Stop after Section 2 unless the operator supplies the real absolute roots and existing launch action. Do not substitute Loom's development launchers for production evidence.

The `markergeomstatus` and `observegeometry` commands are non-scientific observation tooling. They read current state only. `observegeometry` writes a create-only JSON receipt and does not move blocks, entities, markers, camera, or target; alter reset; or alter capture timing.

## 1. Verify and build the preparation revision

### Command 1.1 - verify ancestry and branch

- Working directory: `C:\Users\lollo\MineOcclude-Person-C-C1-C6A`
- Command:

  ```powershell
  git branch --show-current
  git rev-parse HEAD
  git merge-base --is-ancestor de16fabef5dfe326cbff71118c99d32234337a53 HEAD
  ```

- Purpose: prove the required branch and audit ancestry before building.
- Expected output: branch `completion/person-c-c1-c6a`, a preparation commit descended from `de16fab...`, and exit code 0 from `merge-base`.
- Success condition: all three checks match; retain the full `HEAD` value for the pending `preparation_commit` field in `server_startup_receipt.json`.
- Failure response: stop; do not build or launch from another branch/revision.
- Writes files: no.

### Command 1.2 - confirm scientific inputs are unchanged

- Working directory: repository root.
- Command:

  ```powershell
  git status --short -- configs/scenes data/handoff_e schemas src scripts fabric/mineocclude-mod/src/main
  ```

- Purpose: ensure no uncommitted scientific configuration/evidence or runtime source is being smuggled into the observation.
- Expected output: empty after the preparation commit.
- Success condition: no output.
- Failure response: stop and adjudicate every listed path; never discard or overwrite an unknown change.
- Writes files: no.

### Command 1.3 - compile, test, and build the observation JAR

- Working directory: `C:\Users\lollo\MineOcclude-Person-C-C1-C6A\fabric\mineocclude-mod`
- Command:

  ```powershell
  .\gradlew.bat build --no-daemon
  ```

- Purpose: run the pinned Fabric build and all Java tests, including `RuntimeObservationToolingTest`.
- Expected output: `BUILD SUCCESSFUL`; Gradle 8.3 and Fabric Loom 1.4.6 configure the project.
- Success condition: exit code 0 and every test passes.
- Failure response: stop; preserve the complete console output and do not install the JAR.
- Writes files: yes, only ignored Gradle/build outputs and the local Gradle cache.

### Command 1.4 - identify versions and the built JAR

- Working directory: Fabric module directory.
- Command:

  ```powershell
  java -version
  .\gradlew.bat --version
  Get-Content -Raw .\gradle.properties
  Get-Item .\build\libs\mineocclude-0.1.0.jar | Select-Object FullName,Length,LastWriteTimeUtc
  Get-FileHash -Algorithm SHA256 -LiteralPath .\build\libs\mineocclude-0.1.0.jar
  ```

- Purpose: record build Java, Gradle, Minecraft, Yarn, Loader, Fabric API, mod version, JAR size, and JAR hash.
- Expected output: repository pins Minecraft 1.16.5, Yarn `1.16.5+build.10`, Loader 0.15.11, Fabric API `0.42.0+1.16`, Gradle 8.3, and mod 0.1.0. Java is recorded, not assumed acceptable as the production runtime.
- Success condition: every version is explicit and the JAR has a 64-hex SHA-256.
- Failure response: stop and retain output; do not infer a missing version.
- Writes files: Gradle may touch its cache; the other commands are read-only.

## 2. Bind real production roots and launchers

### Manual action 2.1 - identify, do not invent, the server installation

- Working location: operator's existing production dedicated-server installation.
- Action: enter its absolute root, exact Java executable, exact Fabric launcher artifact, and exact existing launch command into `server_startup_receipt.json`.
- Purpose: bind evidence to the real launcher instead of a guessed `java -jar` command.
- Expected result: a Fabric 1.16.5 dedicated-server installation with a known launcher artifact and `server.properties`.
- Success condition: all values are concrete and hashable.
- Failure response: stop. Provisioning/downloading a server is outside this runbook and requires a separately reviewed procedure.
- Writes files: only the new receipt when later ingested; this action must not edit frozen repository evidence.

### Manual action 2.2 - identify, do not invent, the client installation

- Working location: production Minecraft launcher/profile manager.
- Action: identify an existing Minecraft 1.16.5 profile using Fabric Loader 0.15.11, its exact game directory, Java executable, launcher name/version, and exact profile launch action. Record them in `client_startup_receipt.json`.
- Purpose: bind client evidence to the real production profile.
- Expected result: a dedicated 1.16.5 Fabric game directory, not the discovered 1.20.1/default profile.
- Success condition: profile and game directory are explicit; the profile has not yet been launched.
- Failure response: stop. Do not use the current unbound default `.minecraft` options/mods as production evidence.
- Writes files: launcher metadata may be read; no scientific files are changed.

### Command 2.3 - set guarded PowerShell paths

- Working directory: repository root.
- Command (replace both sentinel strings with the absolute roots established above before executing):

  ```powershell
  $C1ServerRoot = 'REPLACE_WITH_ABSOLUTE_PRODUCTION_SERVER_ROOT'
  $C1ClientGameDir = 'REPLACE_WITH_ABSOLUTE_PRODUCTION_CLIENT_GAME_DIRECTORY'
  if ($C1ServerRoot -like 'REPLACE_*' -or -not (Test-Path -LiteralPath $C1ServerRoot)) { throw 'Production server root is not bound' }
  if ($C1ClientGameDir -like 'REPLACE_*' -or -not (Test-Path -LiteralPath $C1ClientGameDir)) { throw 'Production client game directory is not bound' }
  ```

- Purpose: prevent commands from falling back to an unrelated directory.
- Expected output: none.
- Success condition: no exception and both variables are absolute existing paths.
- Failure response: stop and correct the receipt/path; do not create a guessed directory.
- Writes files: no.

## 3. Inventory the pinned server/client before launch

### Command 3.1 - hash `server.properties`

- Working directory: `$C1ServerRoot`.
- Command:

  ```powershell
  Get-Item -LiteralPath (Join-Path $C1ServerRoot 'server.properties') | Select-Object FullName,Length,LastWriteTimeUtc
  Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $C1ServerRoot 'server.properties')
  Get-Content -Raw -LiteralPath (Join-Path $C1ServerRoot 'server.properties')
  ```

- Purpose: record exact content identity, seed/world settings, pack settings, difficulty, spawning, and launcher-facing server configuration.
- Expected output: one concrete file, a 64-hex hash, and its full contents.
- Success condition: required keys can be copied literally into `server_properties_receipt.json`; no value is silently defaulted.
- Failure response: stop if missing or unreadable. Resolve the `spawn-animals` conflict explicitly; do not edit the frozen expected lock.
- Writes files: no.

### Command 3.2 - enumerate and hash every mod file

- Working directory: repository root, with the guarded variables still set.
- Command:

  ```powershell
  $C1ModRows = foreach ($scope in @(@('server',(Join-Path $C1ServerRoot 'mods')), @('client',(Join-Path $C1ClientGameDir 'mods')))) {
    if (-not (Test-Path -LiteralPath $scope[1])) { throw "$($scope[0]) mods directory missing: $($scope[1])" }
    Get-ChildItem -LiteralPath $scope[1] -File | Sort-Object Name | ForEach-Object {
      $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLower()
      [pscustomobject]@{scope=$scope[0];path=$_.FullName;file_name=$_.Name;size_bytes=$_.Length;sha256=$hash}
    }
  }
  $C1ModRows | Format-List
  ```

- Purpose: enumerate every installed server/client mod candidate with path, size, and SHA-256.
- Expected output: MineOcclude 0.1.0 and the pinned Fabric API are present in both appropriate installations; no unexplained capture-affecting mods exist.
- Success condition: every regular file is accounted for, and mod IDs/versions from each `fabric.mod.json` or startup log are added to `installed_mods_inventory.json`.
- Failure response: stop on a missing directory, duplicate/conflicting mod, unreadable archive, or unrecorded file.
- Writes files: no.

### Command 3.3 - inventory resource packs and options before launch

- Working directory: repository root.
- Command:

  ```powershell
  Get-ChildItem -LiteralPath (Join-Path $C1ClientGameDir 'resourcepacks') -Force -ErrorAction Stop | Select-Object FullName,Length,LastWriteTimeUtc
  Get-Item -LiteralPath (Join-Path $C1ClientGameDir 'options.txt') | Select-Object FullName,Length,LastWriteTimeUtc
  Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $C1ClientGameDir 'options.txt')
  Get-Content -Raw -LiteralPath (Join-Path $C1ClientGameDir 'options.txt')
  ```

- Purpose: preserve the prelaunch render/resource-pack state.
- Expected output: concrete inventory and raw option values.
- Success condition: the selected packs and every projection/capture-affecting option can be copied without conversion into `render_settings_receipt.json`.
- Failure response: stop if paths are not the bound production directory.
- Writes files: no.

## 4. Start and prove the dedicated server

### Manual action 4.1 - launch using the recorded command

- Working directory: exact `launch_working_directory` from `server_startup_receipt.json`.
- Action: execute the exact pre-existing production command recorded in that receipt, with no extra flags or substituted launcher.
- Purpose: start a fresh dedicated-server JVM.
- Expected result: vanilla `Done (` readiness and `[MineOcclude] server ready; output ->` appear once in `logs/latest.log`.
- Success condition: both patterns occur after the recorded start UTC, no crash/error follows, and startup logs report Minecraft/Fabric/mod versions.
- Failure response: stop the server cleanly if possible; preserve the entire log and do not continue to the client.
- Writes files: yes, server logs/world/runtime files only.

### Command 4.2 - snapshot stable-ready evidence

- Working directory: repository root with `$C1ServerRoot` set.
- Command:

  ```powershell
  Select-String -Path (Join-Path $C1ServerRoot 'logs\latest.log') -Pattern 'Done \(|\[MineOcclude\] server ready|Loading Minecraft|Fabric Loader|fabric-api|mineocclude'
  Get-Item -LiteralPath (Join-Path $C1ServerRoot 'logs\latest.log') | Select-Object FullName,Length,LastWriteTimeUtc
  Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $C1ServerRoot 'logs\latest.log')
  ```

- Purpose: record stable-ready and version evidence.
- Expected output: both readiness patterns, exact versions, size, and SHA-256.
- Success condition: evidence is internally consistent with the inventories.
- Failure response: stop; do not infer readiness from an open port alone.
- Writes files: no.

## 5. Start, configure, and connect the production client

### Manual action 5.1 - launch the bound profile

- Working location: exact launcher/profile from `client_startup_receipt.json`.
- Action: use the recorded existing launch action; do not use Gradle `runClient`. Open Video Settings, set/confirm every expected setting, record the displayed FOV in degrees, and take an F2 screenshot that visibly includes the FOV setting.
- Purpose: observe the actual production projection/render configuration.
- Expected result: Minecraft 1.16.5 + Fabric Loader 0.15.11 starts from the bound game directory; settings match or produce explicit comparison differences.
- Success condition: client log, options file, and screenshot all come from the same session/profile.
- Failure response: quit without connecting; preserve log/options/screenshots and resolve the mismatch.
- Writes files: yes, client log/options and an F2 screenshot.

### Manual action 5.2 - connect and capture a raw framebuffer screenshot

- Working location: running production client.
- Action: join the recorded server address, wait for the canonical preview pose, then press F2 once in gameplay. Record the exact screenshot path.
- Purpose: prove successful connection and obtain an unnormalized framebuffer-sized PNG.
- Expected result: server log reports the player joined and was opped; client shows the built preview; a new PNG is created.
- Success condition: server and client logs agree on the connection, and the PNG is not reused from an older session.
- Failure response: disconnect, preserve logs, and stop before layout observations.
- Writes files: yes, one raw screenshot and connection log entries.

### Command 5.3 - hash options, screenshots, and client log

- Working directory: repository root with `$C1ClientGameDir` set.
- Command (replace the two screenshot sentinels with the exact new files):

  ```powershell
  $C1FovScreenshot = 'REPLACE_WITH_NEW_FOV_SCREENSHOT_PNG'
  $C1RawScreenshot = 'REPLACE_WITH_NEW_GAMEPLAY_SCREENSHOT_PNG'
  foreach ($path in @((Join-Path $C1ClientGameDir 'options.txt'),(Join-Path $C1ClientGameDir 'logs\latest.log'),$C1FovScreenshot,$C1RawScreenshot)) {
    if ($path -like 'REPLACE_*' -or -not (Test-Path -LiteralPath $path)) { throw "Missing bound evidence: $path" }
    Get-Item -LiteralPath $path | Select-Object FullName,Length,LastWriteTimeUtc
    Get-FileHash -Algorithm SHA256 -LiteralPath $path
  }
  Add-Type -AssemblyName System.Drawing
  $image = [System.Drawing.Image]::FromFile($C1RawScreenshot)
  try { [pscustomobject]@{width_pixels=$image.Width;height_pixels=$image.Height} } finally { $image.Dispose() }
  ```

- Purpose: bind FOV/render settings and actual raw framebuffer dimensions to immutable bytes.
- Expected output: four hashes and positive PNG dimensions. Do not assume 640x360; that is the canonical derivative target.
- Success condition: dimensions and displayed FOV are copied exactly to `render_settings_receipt.json`.
- Failure response: stop if either screenshot predates the session, is unreadable, or lacks a hash.
- Writes files: no.

## 6. Observe override state before any geometry-changing command

### Server-console command 6.1 - query marker override

- Working location: live dedicated-server console.
- Command: `mineocclude markergeomstatus`
- Purpose: observe process-global override state without clearing or setting it.
- Expected output: `markergeom status: enabled=<true|false> ... signature=<...>`.
- Success condition: the exact output is in the server log and copied to `marker_override_receipt.json` with log hash.
- Failure response: stop. Do not run `markergeomreset`; that would destroy the state under observation.
- Writes files: only the normal server log line; runtime geometry is unchanged.

## 7. Observe layouts 01 through 06

### Server-console commands 7.1 - set observation-only episode controls once

- Working location: live dedicated-server console.
- Commands, in this exact order:

  ```text
  mineocclude mode normal
  mineocclude duration 0
  mineocclude reveal 0
  mineocclude impulse -1 0
  mineocclude lockcam on
  mineocclude warmup 1200
  ```

- Purpose: use the normal wall, stationary zero-noise observation episodes, locked camera, and a long no-capture window.
- Expected output: confirmation after every command.
- Success condition: all six confirmations appear; no marker override command was run.
- Failure response: stop and preserve logs.
- Writes files/state: changes session controls for non-scientific observation episodes only; it does not edit repository evidence.

### Server-console commands 7.2 - collect one create-only receipt per layout

- Working location: live dedicated-server console.
- Commands, in the exact order shown; wait for `Armed episode ...` before each `observegeometry`, wait for the receipt path before `stop`, and verify no listed episode/receipt path already exists before starting:

  ```text
  mineocclude start layout_01 11101 202608031101 0.0 0.0 20
  mineocclude observegeometry c1_1_layout_01
  mineocclude stop
  mineocclude start layout_02 11102 202608031102 0.0 0.0 20
  mineocclude observegeometry c1_1_layout_02
  mineocclude stop
  mineocclude start layout_03 11103 202608031103 0.0 0.0 20
  mineocclude observegeometry c1_1_layout_03
  mineocclude stop
  mineocclude start layout_04 11104 202608031104 0.0 0.0 20
  mineocclude observegeometry c1_1_layout_04
  mineocclude stop
  mineocclude start layout_05 11105 202608031105 0.0 0.0 20
  mineocclude observegeometry c1_1_layout_05
  mineocclude stop
  mineocclude start layout_06 11106 202608031106 0.0 0.0 20
  mineocclude observegeometry c1_1_layout_06
  mineocclude stop
  ```

- Purpose: invoke the existing reset/builder once per layout, then inspect actual floor, wall, markers, lane, sampled shadow, camera, world state, layout ID, and override state before recording begins.
- Expected output: six `mineocclude_observations\c1_1_layout_0N.json` files; each says `observation_only=true`, `scientific_use=forbidden`, requested one-based layout ID, four matching marker blocks, fully matching wall/floor counts, connected-player camera data, and the same override signature.
- Success condition: all six files are distinct, complete, and no episode reaches capture.
- Failure response: stop immediately on any `REFUSED`, missing/mismatched block, layout-ID mismatch, empty player list, receipt collision, or capture start. Do not rerun under the same receipt ID; record a new ID and explain the failed attempt.
- Writes files/state: each `start` resets the observation arena and creates an episode directory; each `observegeometry` writes one create-only non-scientific receipt; each `stop` finalizes the observation episode. No frozen evidence is edited.

### Command 7.3 - hash all geometry receipts

- Working directory: repository root with `$C1ServerRoot` set.
- Command:

  ```powershell
  Get-ChildItem -LiteralPath (Join-Path $C1ServerRoot 'mineocclude_observations') -Filter 'c1_1_layout_0?.json' -File | Sort-Object Name | ForEach-Object {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLower()
    [pscustomobject]@{path=$_.FullName;size_bytes=$_.Length;sha256=$hash}
  } | Format-List
  ```

- Purpose: bind each runtime geometry receipt to exact bytes.
- Expected output: exactly six files and six unique hashes.
- Success condition: `layout_runtime_observations.json` can reference every path/size/hash.
- Failure response: stop on a missing, extra, duplicate, or unreadable receipt.
- Writes files: no.

## 8. Shut down cleanly and preserve final evidence

### Manual action 8.1 - disconnect and quit the client

- Working location: production client.
- Action: use Disconnect, then Quit Game; wait for the Java client process to exit.
- Purpose: flush client logs/options and avoid an abrupt disconnect.
- Expected result: server records the player leaving; client log closes normally.
- Success condition: no client Java process remains for that game directory.
- Failure response: record the forced termination and mark client startup/observation unsuccessful.
- Writes files: client logs/options are flushed.

### Server-console command 8.2 - stop server

- Working location: dedicated-server console.
- Command: `stop`
- Purpose: save world state and close logs cleanly.
- Expected output: normal save/shutdown messages and process exit.
- Success condition: server process exits with no crash.
- Failure response: preserve logs and mark the shutdown receipt failed.
- Writes files: server world/log save only.

### Command 8.3 - final log identities

- Working directory: repository root with both guarded roots set.
- Command:

  ```powershell
  foreach ($path in @((Join-Path $C1ServerRoot 'logs\latest.log'),(Join-Path $C1ClientGameDir 'logs\latest.log'),(Join-Path $C1ClientGameDir 'options.txt'))) {
    Get-Item -LiteralPath $path | Select-Object FullName,Length,LastWriteTimeUtc
    Get-FileHash -Algorithm SHA256 -LiteralPath $path
  }
  ```

- Purpose: bind final, flushed logs/options.
- Expected output: three readable files with final sizes/hashes.
- Success condition: receipts use these final identities, not pre-shutdown hashes.
- Failure response: leave C1.1 incomplete and preserve all available evidence.
- Writes files: no.

## 9. Return evidence for ingestion and adjudication

Do not edit the pending JSON templates by hand in place of evidence. Return the exact server root, client game directory, launch receipts, final logs, `server.properties`, options file, mod inventories, FOV screenshot, raw gameplay screenshot, and six geometry-receipt paths to Codex. Codex must ingest only those produced bytes, verify their hashes, compare literal runtime coordinates to C and E, retain `RUNTIME_OBSERVATION_INCOMPLETE` on any missing field, and commit completed receipts separately.

Only after that validation may `docs/status/person_c_geometry_authority_v0_2/` be created. Its accepted version must be hash-bound to the server/client/JAR/environment/geometry receipts and must retain all v0.1 evidence unchanged.
