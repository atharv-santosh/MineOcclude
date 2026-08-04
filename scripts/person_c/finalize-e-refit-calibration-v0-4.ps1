[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$requiredBranch = 'completion/person-c-c1-c6a'
$requiredAncestry = '8ed87e80cd809a7b8b97861dda6bbc79d29e2aac'
$geometryVersion = 'person-c-layout-config-v0.4'
$geometrySha256 = '34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d'
$jarSha256 = '9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52'
$optionsSha256 = '13a43adde78280041f7adc29367b0a61ced6a9549f2430d9083a88665a0d9895'
$serverPropertiesSha256 = 'fbe750e18b1040eaf4d22ff73fa3492638822c726825c50fb249be240eea4c6e'
$serverRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server'
$clientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client'
$packageRoot = Join-Path $RepoRoot 'docs\status\person_c_to_person_e_calibration_images_v0_4_v0_1'
$manifestPath = Join-Path $packageRoot 'session_manifest.json'
$packageInventoryPath = Join-Path $packageRoot 'sha256_inventory.json'
$fitTemplatePath = Join-Path $packageRoot 'e_image_point_annotation_template.json'
$validationTemplatePath = Join-Path $packageRoot 'e_independent_validation_pair_template.json'
$attestationTemplatePath = Join-Path $packageRoot 'operator_attestation_template.json'
$coordinateConventionPath = Join-Path $packageRoot 'coordinate_convention.json'
$serverLogPath = Join-Path $serverRoot 'logs\latest.log'
$clientLogPath = Join-Path $clientRoot 'logs\latest.log'
$serverEvidenceDir = Join-Path $serverRoot 'e_refit_calibration_v0_4_v0_1'
$clientEvidenceDir = Join-Path $clientRoot 'e_refit_calibration_v0_4_v0_1'
$serverLogArchive = Join-Path $serverEvidenceDir 'server_latest.log'
$clientLogArchive = Join-Path $clientEvidenceDir 'client_latest.log'
$attestationPath = Join-Path $serverEvidenceDir 'operator_attestation.json'
$screenshotInventoryPath = Join-Path $serverEvidenceDir 'screenshot_inventory.json'
$receiptInventoryPath = Join-Path $serverEvidenceDir 'geometry_receipt_inventory.json'
$fitOutputPath = Join-Path $serverEvidenceDir 'e_image_point_annotation_template.json'
$validationOutputPath = Join-Path $serverEvidenceDir 'e_independent_validation_pair_template.json'
$handoffPath = Join-Path $serverEvidenceDir 'person_c_to_e_calibration_handoff_v0_4.json'
$resultPath = Join-Path $serverEvidenceDir 'finalization_result.json'

function Require([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-Identity([string]$Path) {
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        path = $item.FullName
        size_bytes = [int64]$item.Length
        sha256 = Get-Sha256 $item.FullName
    }
}

function Find-UniqueLogEvent([string[]]$Lines, [string]$Pattern, [string]$Label) {
    $matches = @()
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index] -match $Pattern) {
            $matches += [pscustomobject]@{ Index = $index; Line = $Lines[$index] }
        }
    }
    Require ($matches.Count -eq 1) "$Label must occur exactly once; observed $($matches.Count)"
    return $matches[0]
}

function Get-LineSeconds([string]$Line, [string]$Label) {
    Require ($Line -match '^\[(\d{2}):(\d{2}):(\d{2})\]') "$Label has no HH:MM:SS timestamp"
    return ([int]$Matches[1] * 3600) + ([int]$Matches[2] * 60) + [int]$Matches[3]
}

function Get-OffsetSeconds([int]$BaseSeconds, [int]$EventSeconds) {
    return ($EventSeconds - $BaseSeconds + 86400) % 86400
}

function Json-Equal($Left, $Right) {
    return (($Left | ConvertTo-Json -Depth 50 -Compress) -ceq ($Right | ConvertTo-Json -Depth 50 -Compress))
}

function Copy-CreateOnly([string]$Source, [string]$Destination) {
    $sourceStream = [System.IO.File]::OpenRead($Source)
    try {
        $destinationStream = [System.IO.File]::Open($Destination, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try { $sourceStream.CopyTo($destinationStream) }
        finally { $destinationStream.Dispose() }
    }
    finally { $sourceStream.Dispose() }
}

function Write-CreateOnlyUtf8([string]$Path, [string]$Text) {
    $encoding = [System.Text.UTF8Encoding]::new($false)
    $bytes = $encoding.GetBytes($Text)
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
}

function Write-CreateOnlyJson([string]$Path, $Value) {
    Write-CreateOnlyUtf8 $Path (($Value | ConvertTo-Json -Depth 100) + "`n")
}

function Get-PngDimensions([string]$Path) {
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    Require ($bytes.Length -ge 24) "PNG is too short: $Path"
    $signature = @(137, 80, 78, 71, 13, 10, 26, 10)
    for ($index = 0; $index -lt $signature.Count; $index++) {
        Require ($bytes[$index] -eq $signature[$index]) "Invalid PNG signature: $Path"
    }
    $width = ([int64]$bytes[16] -shl 24) -bor ([int64]$bytes[17] -shl 16) -bor ([int64]$bytes[18] -shl 8) -bor [int64]$bytes[19]
    $height = ([int64]$bytes[20] -shl 24) -bor ([int64]$bytes[21] -shl 16) -bor ([int64]$bytes[22] -shl 8) -bor [int64]$bytes[23]
    return [pscustomobject]@{ Width = $width; Height = $height }
}

Push-Location -LiteralPath $RepoRoot
try {
    $branch = (& git branch --show-current).Trim()
    Require ($LASTEXITCODE -eq 0 -and $branch -eq $requiredBranch) "Wrong branch: $branch"
    $worktreeStatus = @(& git status --porcelain=v1)
    Require ($LASTEXITCODE -eq 0 -and $worktreeStatus.Count -eq 0) 'Repository worktree must be clean before finalization'
    $preparationCommit = (& git log -1 --format=%H -- scripts/person_c/finalize-e-refit-calibration-v0-4.ps1).Trim()
    Require ($preparationCommit -match '^[0-9a-f]{40}$') 'Calibration preparation is not committed'
    & git merge-base --is-ancestor $requiredAncestry $preparationCommit
    Require ($LASTEXITCODE -eq 0) 'Calibration preparation does not descend from required ancestry'
    & git merge-base --is-ancestor $preparationCommit HEAD
    Require ($LASTEXITCODE -eq 0) 'Calibration preparation commit is not an ancestor of HEAD'

    foreach ($requiredFile in @($manifestPath, $packageInventoryPath, $fitTemplatePath, $validationTemplatePath, $attestationTemplatePath, $coordinateConventionPath, $serverLogPath, $clientLogPath)) {
        Require (Test-Path -LiteralPath $requiredFile -PathType Leaf) "Required calibration input absent: $requiredFile"
    }
    $packageInventory = Get-Content -Raw -LiteralPath $packageInventoryPath | ConvertFrom-Json
    Require ($packageInventory.schema_version -eq 'person-c-package-sha256-inventory-v1.0') 'Unknown package inventory schema'
    foreach ($row in $packageInventory.files) {
        $path = Join-Path $RepoRoot ($row.path -replace '/', '\')
        Require (Test-Path -LiteralPath $path -PathType Leaf) "Package file absent: $path"
        Require ((Get-Item -LiteralPath $path).Length -eq [int64]$row.size_bytes -and (Get-Sha256 $path) -eq $row.sha256) "Package file hash drift: $path"
    }

    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    Require ($manifest.status -eq 'READY_FOR_ONE_AUTHENTICATED_OPERATOR' -and $manifest.layout_count -eq 6 -and $manifest.runtime_schedules_ready -eq $true) 'Calibration manifest is not ready'
    Require ($manifest.accepted_geometry_version -eq $geometryVersion -and $manifest.accepted_geometry_sha256 -eq $geometrySha256) 'Manifest geometry identity mismatch'
    Require ($manifest.mineocclude_jar_sha256 -eq $jarSha256 -and $manifest.scientific_capture -eq $false) 'Manifest JAR/scientific-use contract mismatch'
    foreach ($authority in @(
        $manifest.runtime_identity.accepted_geometry,
        $manifest.runtime_identity.person_c_c1_closure,
        $manifest.runtime_identity.environment_lock,
        $manifest.runtime_identity.render_settings,
        $manifest.runtime_identity.server_runtime_manifest,
        $manifest.runtime_identity.client_runtime_manifest,
        $manifest.runtime_identity.person_e_refit_input_authority,
        $manifest.runtime_identity.person_e_refit_handoff_inventory
    )) {
        $authorityPath = Join-Path $RepoRoot ([string]$authority.path -replace '/', '\')
        Require (Test-Path -LiteralPath $authorityPath -PathType Leaf) "Runtime authority absent: $authorityPath"
        Require ((Get-Item -LiteralPath $authorityPath).Length -eq [int64]$authority.size_bytes -and (Get-Sha256 $authorityPath) -eq $authority.sha256) "Runtime authority hash drift: $authorityPath"
    }
    $finalizerPath = Join-Path $RepoRoot 'scripts\person_c\finalize-e-refit-calibration-v0-4.ps1'
    Require ((Get-Item -LiteralPath $finalizerPath).Length -eq [int64]$manifest.finalizer.size_bytes -and (Get-Sha256 $finalizerPath) -eq $manifest.finalizer.sha256) 'Finalizer identity drift'
    Require ((Get-Sha256 (Join-Path $serverRoot 'mods\mineocclude-0.1.1.jar')) -eq $jarSha256) 'Installed server JAR drift'
    Require ((Get-Sha256 (Join-Path $clientRoot 'mods\mineocclude-0.1.1.jar')) -eq $jarSha256) 'Installed client JAR drift'
    Require ((Get-Sha256 (Join-Path $clientRoot 'options.txt')) -eq $optionsSha256) 'Client options drift'
    Require ((Get-Sha256 (Join-Path $serverRoot 'server.properties')) -eq $serverPropertiesSha256) 'server.properties drift'
    $optionsText = Get-Content -Raw -LiteralPath (Join-Path $clientRoot 'options.txt')
    Require ($optionsText -match '(?m)^fov:0\.0\r?$') 'Client options no longer encode FOV Normal/70.0'
    $propertiesText = Get-Content -Raw -LiteralPath (Join-Path $serverRoot 'server.properties')
    Require ($propertiesText -match '(?m)^spawn-animals=false\r?$') 'spawn-animals is not false'

    $createOnlyPaths = @($serverLogArchive, $clientLogArchive, $attestationPath, $screenshotInventoryPath, $receiptInventoryPath, $fitOutputPath, $validationOutputPath, $handoffPath, $resultPath)
    foreach ($layout in $manifest.layouts) {
        $createOnlyPaths += [string]$layout.runtime_paths.canonical_screenshot
    }
    foreach ($path in $createOnlyPaths) {
        Require (-not (Test-Path -LiteralPath $path)) "Create-only calibration output already exists: $path"
    }

    $serverLines = @(Get-Content -LiteralPath $serverLogPath)
    $clientLines = @(Get-Content -LiteralPath $clientLogPath)
    $controlPatterns = @(
        'markergeom status: enabled=false .*signature=null/null/null/null',
        'Scene mode = normal',
        'Duration = full tick count \(no hidden-frame auto-stop\)',
        'Post-reveal window = 0 ticks',
        'Scripted impulse disabled',
        'Camera lock ON',
        'Warmup delay set to 12000 ticks \(600\.0s\)'
    )
    $controlEvents = @()
    foreach ($pattern in $controlPatterns) {
        $controlEvents += Find-UniqueLogEvent $serverLines $pattern "single session control: $pattern"
    }
    for ($index = 1; $index -lt $controlEvents.Count; $index++) {
        Require ($controlEvents[$index - 1].Index -lt $controlEvents[$index].Index) 'Session controls were not applied once in order'
    }
    $accountEvent = Find-UniqueLogEvent $clientLines 'Setting user: ([A-Za-z0-9_]+)' 'authenticated client account'
    Require ($accountEvent.Line -match 'Setting user: ([A-Za-z0-9_]+)') 'Unable to parse authenticated account'
    $observedAccount = $Matches[1]
    $connectEvent = Find-UniqueLogEvent $clientLines 'Connecting to 127\.0\.0\.1, 25565' 'loopback connection'
    $serverStop = Find-UniqueLogEvent $serverLines 'Stopping server' 'clean server stop'
    $clientStop = Find-UniqueLogEvent $clientLines 'Stopping!' 'clean client stop'
    $allArmed = @($serverLines | Where-Object { $_ -match '\[MineOcclude\] episode \d+ armed' })
    Require ($allArmed.Count -eq 6) 'The calibration server session must contain exactly six armed episodes'

    $firstLayout = $manifest.layouts[0]
    $firstArmed = Find-UniqueLogEvent $serverLines ("\[MineOcclude\] episode {0} armed" -f $firstLayout.episode_id) 'first episode armed'
    Require ($controlEvents[-1].Index -lt $firstArmed.Index) 'Session controls were not completed before the first episode'
    $sessionBaseSeconds = Get-LineSeconds $firstArmed.Line 'first armed event'
    $previousAbortIndex = -1
    $seenRawScreenshots = @{}
    $validatedLayouts = @()

    foreach ($layout in $manifest.layouts) {
        $layoutId = [string]$layout.layout_id
        $episodeId = [int]$layout.episode_id
        $seed = [int64]$layout.seed
        $receiptId = "e_refit_calibration_v0_4_$layoutId"
        $receiptPath = [string]$layout.runtime_paths.geometry_receipt
        $schedulePath = [string]$layout.schedule.runtime_schedule.path
        foreach ($path in @($receiptPath, $schedulePath)) {
            Require (Test-Path -LiteralPath $path -PathType Leaf) "Required layout runtime input absent: $path"
        }
        Require ((Get-Sha256 $schedulePath) -eq $layout.schedule.runtime_schedule.sha256) "Runtime schedule hash mismatch: $layoutId"

        $armed = Find-UniqueLogEvent $serverLines ("\[MineOcclude\] episode {0} armed \(layout={1}, 12000 warmup \+ 20 record ticks, v=0\.0, q=0\.0, seed={2}, rng=immutable_numpy_schedule\)" -f $episodeId, $layoutId, $seed) "$layoutId armed"
        $scheduleLoaded = Find-UniqueLogEvent $serverLines ("loaded immutable noise schedule \(20 draws\) from .*episode_{0}\.jsonl" -f $episodeId) "$layoutId immutable schedule load"
        $targetStatus = Find-UniqueLogEvent $serverLines ("\[MineOcclude/target\] target status: valid=true required=true count=1.*layout={0} episode={1} lifecycle=READY problems=NONE" -f $layoutId, $episodeId) "$layoutId passing targetstatus"
        $observe = Find-UniqueLogEvent $serverLines ("\[MineOcclude/observation\] wrote read-only geometry receipt .*{0}\.json" -f $receiptId) "$layoutId observegeometry"
        $confirmation = Find-UniqueLogEvent $serverLines ("Wrote observation-only geometry receipt: .*{0}\.json" -f $receiptId) "$layoutId receipt confirmation"
        $abort = Find-UniqueLogEvent $serverLines ("\[MineOcclude\] episode {0} aborted during warmup" -f $episodeId) "$layoutId warmup abort"
        Require ($previousAbortIndex -lt $armed.Index -and $armed.Index -le $scheduleLoaded.Index -and $scheduleLoaded.Index -lt $targetStatus.Index -and $targetStatus.Index -lt $observe.Index -and $observe.Index -le $confirmation.Index -and $confirmation.Index -lt $abort.Index -and $abort.Index -lt $serverStop.Index) "$layoutId server chronology failed"
        Require (-not ($serverLines -match ("episode {0} recording started" -f $episodeId))) "$layoutId entered recording"
        $previousAbortIndex = $abort.Index

        $armedSeconds = Get-LineSeconds $armed.Line "$layoutId armed"
        $statusOffsetFromArmed = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $targetStatus.Line "$layoutId targetstatus")
        Require ($statusOffsetFromArmed -ge 10) "$layoutId targetstatus occurred less than ten seconds after arming"
        $confirmationOffset = Get-OffsetSeconds $sessionBaseSeconds (Get-LineSeconds $confirmation.Line "$layoutId receipt confirmation")
        $abortOffset = Get-OffsetSeconds $sessionBaseSeconds (Get-LineSeconds $abort.Line "$layoutId abort")
        $screenshotEvents = @()
        foreach ($line in $clientLines) {
            if ($line -match 'Saved screenshot as ([^\\/\s]+\.png)') {
                $eventOffset = Get-OffsetSeconds $sessionBaseSeconds (Get-LineSeconds $line 'screenshot event')
                if ($eventOffset -gt $confirmationOffset -and $eventOffset -lt $abortOffset) {
                    $screenshotEvents += [pscustomobject]@{ Offset = $eventOffset; FileName = $Matches[1]; Line = $line }
                }
            }
        }
        Require ($screenshotEvents.Count -eq 1) "$layoutId requires exactly one F2 screenshot after receipt confirmation and before abort"
        $rawScreenshot = Join-Path (Join-Path $clientRoot 'screenshots') $screenshotEvents[0].FileName
        Require (Test-Path -LiteralPath $rawScreenshot -PathType Leaf) "$layoutId logged screenshot is absent: $rawScreenshot"
        Require (-not $seenRawScreenshots.ContainsKey($rawScreenshot)) "$layoutId reused a raw screenshot"
        $seenRawScreenshots[$rawScreenshot] = $true
        $dimensions = Get-PngDimensions $rawScreenshot
        Require ($dimensions.Width -eq 1920 -and $dimensions.Height -eq 1046) "$layoutId screenshot is not 1920x1046"

        $receipt = Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json
        Require ($receipt.schema_version -eq 'person-c-c1-runtime-geometry-observation-v0.1' -and $receipt.receipt_id -eq $receiptId) "$layoutId receipt schema/ID mismatch"
        Require ($receipt.observation_only -eq $true -and $receipt.scientific_use -eq 'forbidden' -and $receipt.mutates_runtime_state -eq $false) "$layoutId receipt is not observation-only"
        Require ($receipt.layout_id -eq $layoutId -and [int]$receipt.episode_id -eq $episodeId) "$layoutId receipt layout/episode mismatch"
        Require ($receipt.scene -eq 'NORMAL' -and $receipt.running -eq $true -and $receipt.capturing -eq $false -and $receipt.lifecycle_state -eq 'READY' -and [int]$receipt.warmup_ticks_remaining -gt 0) "$layoutId receipt was not captured during READY warmup"
        Require ($receipt.target.valid -eq $true -and $receipt.target.required -eq $true -and [int]$receipt.target.tagged_target_count -eq 1 -and $receipt.target.problems.Count -eq 0) "$layoutId target object failed"
        Require (Json-Equal $receipt.target.actual_xyz $layout.layout_geometry.target_start.world_xyz) "$layoutId actual target coordinate mismatch"
        Require (Json-Equal $receipt.target.expected_xyz $layout.layout_geometry.target_start.world_xyz) "$layoutId expected target coordinate mismatch"
        Require ($receipt.floor.mismatches.Count -eq 0 -and [int]$receipt.floor.matching_position_count -eq [int]$receipt.floor.expected_position_count) "$layoutId floor mismatch"
        Require ($receipt.wall.mismatches.Count -eq 0 -and [int]$receipt.wall.matching_position_count -eq [int]$receipt.wall.expected_position_count) "$layoutId wall mismatch"
        foreach ($property in $layout.layout_geometry.expected_receipt_geometry.floor.PSObject.Properties) {
            Require ($receipt.floor.($property.Name) -eq $property.Value) "$layoutId floor field mismatch: $($property.Name)"
        }
        foreach ($property in $layout.layout_geometry.expected_receipt_geometry.wall.PSObject.Properties) {
            Require ($receipt.wall.($property.Name) -eq $property.Value) "$layoutId wall field mismatch: $($property.Name)"
        }
        Require ([int]$receipt.observed_marker_block_count -eq 4 -and $receipt.markers.Count -eq 4) "$layoutId marker count mismatch"
        foreach ($expectedMarker in $layout.layout_geometry.markers) {
            $actualMarker = @($receipt.markers | Where-Object { $_.role -eq $expectedMarker.marker_id })
            Require ($actualMarker.Count -eq 1) "$layoutId marker missing or duplicated: $($expectedMarker.marker_id)"
            Require ($actualMarker[0].matches -eq $true -and (Json-Equal $actualMarker[0].block_pos_xyz $expectedMarker.block_pos_xyz) -and (Json-Equal $actualMarker[0].top_face_centre_world_xyz $expectedMarker.top_face_centre_world_xyz)) "$layoutId literal marker mismatch: $($expectedMarker.marker_id)"
        }
        Require (Json-Equal $receipt.camera.canonical_feet_xyz $layout.layout_geometry.camera.feet_xyz) "$layoutId canonical camera position mismatch"
        Require ([double]$receipt.camera.canonical_yaw_degrees -eq [double]$layout.layout_geometry.camera.yaw_degrees -and [double]$receipt.camera.canonical_pitch_degrees -eq [double]$layout.layout_geometry.camera.pitch_degrees) "$layoutId canonical camera orientation mismatch"
        Require ($receipt.camera.observed_players.Count -eq 1 -and $receipt.camera.observed_players[0].name -ceq $observedAccount) "$layoutId observed player/session mismatch"
        Require (Json-Equal $receipt.camera.observed_players[0].feet_xyz $layout.layout_geometry.camera.feet_xyz) "$layoutId observed camera position mismatch"
        Require ([double]$receipt.camera.observed_players[0].yaw_degrees -eq [double]$layout.layout_geometry.camera.yaw_degrees -and [double]$receipt.camera.observed_players[0].pitch_degrees -eq [double]$layout.layout_geometry.camera.pitch_degrees) "$layoutId observed camera orientation mismatch"

        $validatedLayouts += [pscustomobject]@{
            Preparation = $layout
            ReceiptPath = $receiptPath
            RawScreenshotPath = $rawScreenshot
            CanonicalScreenshotPath = [string]$layout.runtime_paths.canonical_screenshot
            ArmedOffsetSeconds = Get-OffsetSeconds $sessionBaseSeconds $armedSeconds
            TargetStatusOffsetSeconds = Get-OffsetSeconds $sessionBaseSeconds (Get-LineSeconds $targetStatus.Line "$layoutId targetstatus")
            ReceiptConfirmationOffsetSeconds = $confirmationOffset
            ScreenshotOffsetSeconds = $screenshotEvents[0].Offset
            AbortOffsetSeconds = $abortOffset
        }
    }

    Require ($validatedLayouts.Count -eq 6 -and $seenRawScreenshots.Count -eq 6) 'Six distinct layout screenshots were not validated'
    Require ($accountEvent.Index -lt $connectEvent.Index -and $connectEvent.Index -lt $clientStop.Index) 'Client account/connection/stop order failed'
    $lastAbortOffset = $validatedLayouts[-1].AbortOffsetSeconds
    Require ((Get-OffsetSeconds $sessionBaseSeconds (Get-LineSeconds $serverStop.Line 'server stop')) -gt $lastAbortOffset) 'Server did not stop after the sixth abort'
    Require ((Get-OffsetSeconds $sessionBaseSeconds (Get-LineSeconds $clientStop.Line 'client stop')) -gt $lastAbortOffset) 'Client did not stop after the sixth abort'
    $sessionScreenshotEvents = @()
    foreach ($line in $clientLines) {
        if ($line -match 'Saved screenshot as ([^\\/\s]+\.png)') {
            $eventOffset = Get-OffsetSeconds $sessionBaseSeconds (Get-LineSeconds $line 'session screenshot event')
            if ($eventOffset -gt 0 -and $eventOffset -lt $lastAbortOffset) {
                $sessionScreenshotEvents += $line
            }
        }
    }
    Require ($sessionScreenshotEvents.Count -eq 6) 'Exactly six F2 events must occur from first arm through sixth warmup abort'

    $confirmation = Read-Host 'Type YES only if one authenticated operator ran the entire session and every screenshot is normal gameplay with no pause menu, chat, inventory, or F3 overlay'
    Require ($confirmation -ceq 'YES') 'Required operator attestation was not provided'

    foreach ($directory in @($serverEvidenceDir, $clientEvidenceDir)) {
        if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory | Out-Null }
    }
    Copy-CreateOnly $serverLogPath $serverLogArchive
    Copy-CreateOnly $clientLogPath $clientLogArchive
    foreach ($validated in $validatedLayouts) {
        Copy-CreateOnly $validated.RawScreenshotPath $validated.CanonicalScreenshotPath
        Require ((Get-Sha256 $validated.RawScreenshotPath) -eq (Get-Sha256 $validated.CanonicalScreenshotPath)) "Screenshot copy hash mismatch: $($validated.Preparation.layout_id)"
    }
    Require ((Get-Sha256 $serverLogPath) -eq (Get-Sha256 $serverLogArchive)) 'Server log archive hash mismatch'
    Require ((Get-Sha256 $clientLogPath) -eq (Get-Sha256 $clientLogArchive)) 'Client log archive hash mismatch'

    $attestation = Get-Content -Raw -LiteralPath $attestationTemplatePath | ConvertFrom-Json
    $attestation.template = $false
    $attestation.operator_id = $observedAccount
    $attestation.observed_authenticated_account = $observedAccount
    $attestation.single_authenticated_operator = $true
    $attestation.normal_gameplay_no_pause_chat_inventory_or_f3_for_all_screenshots = $true
    $attestation.exactly_one_f2_per_layout_after_receipt_confirmation = $true
    $attestation.all_six_episodes_aborted_during_warmup = $true
    $attestation.recording_never_started = $true
    $attestation.same_server_client_options_render_and_log_session = $true
    $attestation.preparation_commit = $preparationCommit
    $attestation.utc_start = (Get-Item -LiteralPath $serverLogPath).CreationTimeUtc.ToString('o')
    $attestation.utc_end = (Get-Item -LiteralPath $serverLogPath).LastWriteTimeUtc.ToString('o')
    $attestation.notes = 'One operator attested YES after the finalizer validated all six layouts and before create-only finalization.'
    Write-CreateOnlyJson $attestationPath $attestation

    $fitTemplate = Get-Content -Raw -LiteralPath $fitTemplatePath | ConvertFrom-Json
    $validationTemplate = Get-Content -Raw -LiteralPath $validationTemplatePath | ConvertFrom-Json
    $screenshotRows = @()
    $receiptRows = @()
    $layoutEvidence = @()
    foreach ($validated in $validatedLayouts) {
        $layoutId = [string]$validated.Preparation.layout_id
        $canonical = Get-Identity $validated.CanonicalScreenshotPath
        $raw = Get-Identity $validated.RawScreenshotPath
        $receiptIdentity = Get-Identity $validated.ReceiptPath
        $fitRow = @($fitTemplate.layouts | Where-Object { $_.layout_id -eq $layoutId })
        $validationRow = @($validationTemplate.layouts | Where-Object { $_.layout_id -eq $layoutId })
        Require ($fitRow.Count -eq 1 -and $validationRow.Count -eq 1) "$layoutId annotation template row missing"
        foreach ($row in @($fitRow[0], $validationRow[0])) {
            $row.screenshot.path = $canonical.path
            $row.screenshot.size_bytes = $canonical.size_bytes
            $row.screenshot.sha256 = $canonical.sha256
        }
        $screenshotRows += [ordered]@{
            layout_id = $layoutId
            episode_id = [int]$validated.Preparation.episode_id
            raw_same_session_screenshot = $raw
            canonical_screenshot = $canonical
            width_pixels = 1920
            height_pixels = 1046
            receipt_confirmation_offset_seconds = $validated.ReceiptConfirmationOffsetSeconds
            screenshot_offset_seconds = $validated.ScreenshotOffsetSeconds
        }
        $receiptRows += [ordered]@{
            layout_id = $layoutId
            episode_id = [int]$validated.Preparation.episode_id
            geometry_receipt = $receiptIdentity
            target_valid = $true
            literal_v0_4_geometry_valid = $true
            ready_warmup_observation = $true
        }
        $layoutEvidence += [ordered]@{
            layout_id = $layoutId
            episode_id = [int]$validated.Preparation.episode_id
            seed = [int64]$validated.Preparation.seed
            schedule = Get-Identity ([string]$validated.Preparation.schedule.runtime_schedule.path)
            geometry_receipt = $receiptIdentity
            canonical_screenshot = $canonical
            expected_floor = $validated.Preparation.layout_geometry.floor
            expected_wall = $validated.Preparation.layout_geometry.wall
            expected_camera = $validated.Preparation.layout_geometry.camera
            expected_markers = $validated.Preparation.layout_geometry.markers
            chronology = [ordered]@{
                armed_offset_seconds = $validated.ArmedOffsetSeconds
                targetstatus_offset_seconds = $validated.TargetStatusOffsetSeconds
                receipt_confirmation_offset_seconds = $validated.ReceiptConfirmationOffsetSeconds
                screenshot_offset_seconds = $validated.ScreenshotOffsetSeconds
                warmup_abort_offset_seconds = $validated.AbortOffsetSeconds
                recording_started = $false
            }
        }
    }
    $fitTemplate.status = 'READY_FOR_PERSON_E_IMAGE_ANNOTATION'
    $validationTemplate.status = 'READY_FOR_PERSON_E_INDEPENDENT_IMAGE_ANNOTATION'
    Write-CreateOnlyJson $fitOutputPath $fitTemplate
    Write-CreateOnlyJson $validationOutputPath $validationTemplate

    $screenshotInventory = [ordered]@{
        schema_version = 'person-c-e-refit-calibration-screenshot-inventory-v0.1'
        status = 'PASS'
        screenshot_count = 6
        same_client_session = $true
        framebuffer = [ordered]@{ width_pixels = 1920; height_pixels = 1046 }
        screenshots = $screenshotRows
    }
    $receiptInventory = [ordered]@{
        schema_version = 'person-c-e-refit-calibration-geometry-receipt-inventory-v0.1'
        status = 'PASS'
        receipt_count = 6
        accepted_geometry_version = $geometryVersion
        accepted_geometry_sha256 = $geometrySha256
        receipts = $receiptRows
    }
    Write-CreateOnlyJson $screenshotInventoryPath $screenshotInventory
    Write-CreateOnlyJson $receiptInventoryPath $receiptInventory

    $handoff = [ordered]@{
        schema_version = 'person-c-to-person-e-v0.4-calibration-image-handoff-v0.1'
        status = 'READY_FOR_PERSON_E_ANNOTATION_NOT_HOMOGRAPHY_FIT_YET'
        immutable = $true
        preparation_commit = $preparationCommit
        package_bundle_sha256 = $packageInventory.package_bundle_sha256
        accepted_geometry_version = $geometryVersion
        accepted_geometry_sha256 = $geometrySha256
        mineocclude_jar_sha256 = $jarSha256
        fov_degrees = 70.0
        framebuffer = [ordered]@{ width_pixels = 1920; height_pixels = 1046 }
        options = Get-Identity (Join-Path $clientRoot 'options.txt')
        environment_lock = Get-Identity (Join-Path $RepoRoot 'docs\status\person_c_c1_runtime_ingestion_v0_1\final_environment_lock_receipt.json')
        coordinate_convention = Get-Identity $coordinateConventionPath
        authenticated_account = $observedAccount
        operator_attestation = Get-Identity $attestationPath
        server_log = Get-Identity $serverLogArchive
        client_log = Get-Identity $clientLogArchive
        screenshot_inventory = Get-Identity $screenshotInventoryPath
        geometry_receipt_inventory = Get-Identity $receiptInventoryPath
        e_image_point_annotation_template = Get-Identity $fitOutputPath
        e_independent_validation_pair_template = Get-Identity $validationOutputPath
        person_c_invented_image_coordinates = $false
        person_c_fit_homographies = $false
        layouts = $layoutEvidence
    }
    Write-CreateOnlyJson $handoffPath $handoff
    $result = [ordered]@{
        schema_version = 'person-c-e-refit-calibration-finalization-result-v0.1'
        status = 'PASS'
        preparation_commit = $preparationCommit
        operator_id = $observedAccount
        layout_count = 6
        episode_ids = @($manifest.layouts | ForEach-Object { [int]$_.episode_id })
        chronology_valid = $true
        screenshot_dimensions_valid = $true
        geometry_receipts_valid = $true
        recording_never_started = $true
        homography_fit_performed = $false
        c6a_executed = $false
        handoff = Get-Identity $handoffPath
    }
    Write-CreateOnlyJson $resultPath $result

    Write-Output 'E_REFIT_CALIBRATION_FINALIZE_BEGIN'
    Write-Output "PREPARATION_COMMIT=$preparationCommit"
    Write-Output "OPERATOR_ID=$observedAccount"
    Write-Output 'CALIBRATION_LAYOUT_COUNT=6'
    Write-Output 'CHRONOLOGY_VALID=True'
    Write-Output 'SCREENSHOT_COUNT=6'
    Write-Output 'GEOMETRY_RECEIPT_COUNT=6'
    Write-Output "HANDOFF_PATH=$handoffPath"
    Write-Output "HANDOFF_SHA256=$(Get-Sha256 $handoffPath)"
    Write-Output 'PERSON_E_IMAGE_POINTS_PENDING=True'
    Write-Output 'HOMOGRAPHY_FIT_PERFORMED=False'
    Write-Output 'C6A_EXECUTED=False'
    Write-Output 'E_REFIT_CALIBRATION_FINALIZE_END'
}
finally {
    Pop-Location
}
