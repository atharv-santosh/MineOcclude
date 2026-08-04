[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$requiredBranch = 'completion/person-c-c1-c6a'
$requiredAncestry = '7485f3c48da4cc86c6f7cea61ce20a8c87b063db'
$attemptName = 'e_refit_calibration_v0_4_attempt_02'
$attempt01Classification = 'CALIBRATION_SCREENSHOT_FRAMEBUFFER_MISMATCH_640X360_EXPECTED_1920X1046'
$geometryVersion = 'person-c-layout-config-v0.4'
$geometrySha256 = '34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d'
$jarSha256 = '9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52'
$serverRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server'
$clientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client'
$packageRoot = Join-Path $RepoRoot 'docs\status\person_c_to_person_e_calibration_images_v0_4_attempt_02_v0_1'
$manifestPath = Join-Path $packageRoot 'session_manifest.json'
$packageInventoryPath = Join-Path $packageRoot 'sha256_inventory.json'
$attempt01RecordPath = Join-Path $packageRoot 'attempt_01_failure_record.json'
$attempt01PackageRoot = Join-Path $RepoRoot 'docs\status\person_c_to_person_e_calibration_images_v0_4_v0_1'
$attempt01ManifestPath = Join-Path $attempt01PackageRoot 'session_manifest.json'
$attempt01PackageInventoryPath = Join-Path $attempt01PackageRoot 'sha256_inventory.json'
$attempt01RepairPackageInventoryPath = Join-Path $RepoRoot 'docs\status\person_c_e_refit_calibration_finalizer_server_properties_repair_v0_1\sha256_inventory.json'
$fitTemplatePath = Join-Path $packageRoot 'e_image_point_annotation_template.json'
$validationTemplatePath = Join-Path $packageRoot 'e_independent_validation_pair_template.json'
$attestationTemplatePath = Join-Path $packageRoot 'operator_attestation_template.json'
$coordinateConventionPath = Join-Path $packageRoot 'coordinate_convention.json'
$authorityModulePath = Join-Path $RepoRoot 'scripts\person_c\ERefitCalibrationAttempt02Authority.psm1'
$serverPropertiesModulePath = Join-Path $RepoRoot 'scripts\person_c\ServerPropertiesAuthority.psm1'
$serverPropertiesAuthorityPath = Join-Path $RepoRoot 'fabric\mineocclude-mod\provisioning\person-c-c1-v0_2\server.properties'
$serverPropertiesRuntimePath = Join-Path $serverRoot 'server.properties'
$repairReceiptPath = Join-Path $RepoRoot 'docs\status\person_c_e_refit_calibration_finalizer_server_properties_repair_v0_1\repair_receipt.json'
$serverLogPath = Join-Path $serverRoot 'logs\latest.log'
$clientLogPath = Join-Path $clientRoot 'logs\latest.log'
$serverEvidenceDir = Join-Path $serverRoot ($attemptName + '_v0_1')
$clientEvidenceDir = Join-Path $clientRoot ($attemptName + '_v0_1')
$serverLogArchive = Join-Path $serverEvidenceDir ($attemptName + '_server_latest.log')
$clientLogArchive = Join-Path $clientEvidenceDir ($attemptName + '_client_latest.log')
$attestationPath = Join-Path $serverEvidenceDir ($attemptName + '_operator_attestation.json')
$screenshotInventoryPath = Join-Path $serverEvidenceDir ($attemptName + '_screenshot_inventory.json')
$receiptInventoryPath = Join-Path $serverEvidenceDir ($attemptName + '_geometry_receipt_inventory.json')
$fitOutputPath = Join-Path $serverEvidenceDir ($attemptName + '_e_image_point_annotation_template.json')
$validationOutputPath = Join-Path $serverEvidenceDir ($attemptName + '_e_independent_validation_pair_template.json')
$handoffPath = Join-Path $serverEvidenceDir ($attemptName + '_person_c_to_e_calibration_handoff.json')
$resultPath = Join-Path $serverEvidenceDir ($attemptName + '_finalization_result.json')
$attempt01ServerLogArchive = Join-Path $serverRoot 'e_refit_calibration_v0_4_v0_1\server_latest.log'
$attempt01ClientLogArchive = Join-Path $clientRoot 'e_refit_calibration_v0_4_v0_1\client_latest.log'

Import-Module -Name $authorityModulePath -Force
Import-Module -Name $serverPropertiesModulePath -Force

function Find-UniqueAttempt02LogEvent {
    param([string[]]$Lines, [string]$Pattern, [string]$Label)
    $matches = @()
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index] -match $Pattern) {
            $matches += [pscustomobject]@{ Index = $index; Line = $Lines[$index] }
        }
    }
    Assert-ERefitAttempt02Condition ($matches.Count -eq 1) "$Label must occur exactly once; observed $($matches.Count)"
    return $matches[0]
}

function Get-Attempt02LineSeconds {
    param([string]$Line, [string]$Label)
    Assert-ERefitAttempt02Condition ($Line -match '^\[(\d{2}):(\d{2}):(\d{2})\]') "$Label has no HH:MM:SS timestamp"
    return ([int]$Matches[1] * 3600) + ([int]$Matches[2] * 60) + [int]$Matches[3]
}

function Get-Attempt02OffsetSeconds {
    param([int]$BaseSeconds, [int]$EventSeconds)
    return ($EventSeconds - $BaseSeconds + 86400) % 86400
}

function Test-Attempt02JsonEqual {
    param($Left, $Right)
    return (($Left | ConvertTo-Json -Depth 50 -Compress) -ceq ($Right | ConvertTo-Json -Depth 50 -Compress))
}

function Assert-Attempt02Identity {
    param($Identity, [string]$Label)
    Assert-ERefitAttempt02Identity -Identity $Identity -Label $Label
}

Push-Location -LiteralPath $RepoRoot
try {
    $branch = (& git branch --show-current).Trim()
    Assert-ERefitAttempt02Condition ($LASTEXITCODE -eq 0 -and $branch -ceq $requiredBranch) "Wrong branch: $branch"
    $worktreeStatus = @(& git status --porcelain=v1)
    Assert-ERefitAttempt02Condition ($LASTEXITCODE -eq 0 -and $worktreeStatus.Count -eq 0) 'Repository worktree must be clean before finalization'
    $finalizerRelativePath = 'scripts/person_c/finalize-e-refit-calibration-v0-4-attempt-02.ps1'
    $preparationCommit = (& git log -1 --format=%H -- $finalizerRelativePath).Trim()
    Assert-ERefitAttempt02Condition ($preparationCommit -match '^[0-9a-f]{40}$') 'Attempt 02 preparation is not committed'
    & git merge-base --is-ancestor $requiredAncestry $preparationCommit
    Assert-ERefitAttempt02Condition ($LASTEXITCODE -eq 0) 'Attempt 02 preparation does not descend from the required starting HEAD'
    & git merge-base --is-ancestor $preparationCommit HEAD
    Assert-ERefitAttempt02Condition ($LASTEXITCODE -eq 0) 'Attempt 02 preparation commit is not an ancestor of HEAD'

    foreach ($requiredFile in @(
        $manifestPath, $packageInventoryPath, $attempt01RecordPath,
        $attempt01ManifestPath, $attempt01PackageInventoryPath, $attempt01RepairPackageInventoryPath,
        $fitTemplatePath,
        $validationTemplatePath, $attestationTemplatePath, $coordinateConventionPath,
        $authorityModulePath, $serverPropertiesModulePath, $serverPropertiesAuthorityPath,
        $serverPropertiesRuntimePath, $repairReceiptPath, $serverLogPath, $clientLogPath
    )) {
        Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $requiredFile -PathType Leaf) "Required Attempt 02 input absent: $requiredFile"
    }
    $packageInventory = Get-Content -Raw -LiteralPath $packageInventoryPath | ConvertFrom-Json
    Assert-ERefitAttempt02Condition ($packageInventory.schema_version -eq 'person-c-package-sha256-inventory-v1.0') 'Unknown package inventory schema'
    foreach ($row in $packageInventory.files) {
        $path = Join-Path $RepoRoot ([string]$row.path -replace '/', '\')
        Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $path -PathType Leaf) "Package file absent: $path"
        $item = Get-Item -LiteralPath $path
        Assert-ERefitAttempt02Condition ($item.Length -eq [int64]$row.size_bytes -and (Get-ERefitAttempt02Sha256 $item.FullName) -ceq [string]$row.sha256) "Package file hash drift: $path"
    }

    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    Assert-ERefitAttempt02Condition ($manifest.status -eq 'READY_AFTER_MANDATORY_FRAMEBUFFER_PREFLIGHT' -and $manifest.layout_count -eq 6 -and $manifest.runtime_schedules_ready -eq $true) 'Attempt 02 manifest is not ready'
    Assert-ERefitAttempt02Condition ($manifest.attempt_name -ceq $attemptName -and $manifest.attempt_number -eq 2) 'Attempt 02 manifest identity mismatch'
    Assert-ERefitAttempt02Condition ($manifest.accepted_geometry_version -eq $geometryVersion -and $manifest.accepted_geometry_sha256 -eq $geometrySha256) 'Attempt 02 geometry identity mismatch'
    Assert-ERefitAttempt02Condition ($manifest.mineocclude_jar_sha256 -eq $jarSha256 -and $manifest.scientific_capture -eq $false -and $manifest.c6a_or_c6b -eq $false) 'Attempt 02 JAR/use contract mismatch'
    Assert-ERefitAttempt02Condition ($manifest.framebuffer.width_pixels -eq 1920 -and $manifest.framebuffer.height_pixels -eq 1046 -and $manifest.fov_degrees -eq 70.0) 'Attempt 02 projection authority mismatch'
    Assert-ERefitAttempt02Condition ($manifest.layouts.Count -eq 6) 'Attempt 02 does not contain all six layouts'
    $expectedLayoutIds = @(1..6 | ForEach-Object { 'layout_{0:d2}' -f $_ })
    $manifestLayoutIds = @($manifest.layouts | ForEach-Object { [string]$_.layout_id })
    $manifestLayoutIdDifferences = @(Compare-Object $expectedLayoutIds $manifestLayoutIds)
    Assert-ERefitAttempt02Condition ($manifestLayoutIdDifferences.Count -eq 0) 'Attempt 02 layout IDs drifted'

    $attempt01PackageInventory = Get-Content -Raw -LiteralPath $attempt01PackageInventoryPath | ConvertFrom-Json
    Assert-ERefitAttempt02Condition ($attempt01PackageInventory.schema_version -eq 'person-c-package-sha256-inventory-v1.0') 'Unknown Attempt 01 package inventory schema'
    foreach ($row in $attempt01PackageInventory.files) {
        $path = Join-Path $RepoRoot ([string]$row.path -replace '/', '\')
        Assert-ERefitAttempt02Identity -Identity ([ordered]@{
            path = $path
            size_bytes = [int64]$row.size_bytes
            sha256 = [string]$row.sha256
        }) -Label 'Immutable Attempt 01 repository package evidence'
    }
    $attempt01ManifestInventoryRows = @($attempt01PackageInventory.files | Where-Object { $_.path -ceq 'docs/status/person_c_to_person_e_calibration_images_v0_4_v0_1/session_manifest.json' })
    Assert-ERefitAttempt02Condition ($attempt01ManifestInventoryRows.Count -eq 1) 'Attempt 01 package inventory does not uniquely bind its repository manifest'
    $attempt01Manifest = Get-Content -Raw -LiteralPath $attempt01ManifestPath | ConvertFrom-Json
    Assert-ERefitAttempt02Condition ($attempt01Manifest.layout_count -eq 6 -and $attempt01Manifest.accepted_geometry_version -eq $geometryVersion -and $attempt01Manifest.accepted_geometry_sha256 -eq $geometrySha256) 'Immutable Attempt 01 repository manifest drift'

    $attempt01RepairPackageInventory = Get-Content -Raw -LiteralPath $attempt01RepairPackageInventoryPath | ConvertFrom-Json
    Assert-ERefitAttempt02Condition ($attempt01RepairPackageInventory.schema_version -eq 'person-c-package-sha256-inventory-v1.0') 'Unknown Attempt 01 repair-package inventory schema'
    foreach ($row in $attempt01RepairPackageInventory.files) {
        $path = Join-Path $RepoRoot ([string]$row.path -replace '/', '\')
        Assert-ERefitAttempt02Identity -Identity ([ordered]@{
            path = $path
            size_bytes = [int64]$row.size_bytes
            sha256 = [string]$row.sha256
        }) -Label 'Immutable Attempt 01 repair-package evidence'
    }

    $attempt01 = Get-Content -Raw -LiteralPath $attempt01RecordPath | ConvertFrom-Json
    Assert-ERefitAttempt02Condition ($attempt01.status -eq 'FAILED_PRESERVED_UNCERTIFIED' -and $attempt01.classification -ceq $attempt01Classification) 'Attempt 01 failure classification drift'
    Assert-ERefitAttempt02Condition ($attempt01.preserved_unchanged -eq $true -and $attempt01.certified -eq $false) 'Attempt 01 preservation contract drift'
    foreach ($row in @($attempt01.geometry_receipts) + @($attempt01.raw_screenshots)) {
        Assert-Attempt02Identity $row 'Preserved Attempt 01 evidence'
    }
    $attempt01MutableLatestLogIdentitiesRecordedOnly = @($attempt01.logs)
    Assert-ERefitAttempt02Condition ($attempt01MutableLatestLogIdentitiesRecordedOnly.Count -eq 2) 'Attempt 01 historical mutable-log identity count drift'
    $attempt01HistoricalServerLog = @($attempt01MutableLatestLogIdentitiesRecordedOnly | Where-Object { [string]$_.path -ceq $serverLogPath })
    $attempt01HistoricalClientLog = @($attempt01MutableLatestLogIdentitiesRecordedOnly | Where-Object { [string]$_.path -ceq $clientLogPath })
    Assert-ERefitAttempt02Condition ($attempt01HistoricalServerLog.Count -eq 1 -and $attempt01HistoricalClientLog.Count -eq 1) 'Attempt 01 historical mutable latest.log aliases drift'
    foreach ($row in $attempt01MutableLatestLogIdentitiesRecordedOnly) {
        Assert-ERefitAttempt02Condition ([int64]$row.size_bytes -gt 0 -and [string]$row.sha256 -match '^[0-9a-f]{64}$') 'Attempt 01 recorded historical mutable-log identity is malformed'
    }
    # The latest.log aliases now contain Attempt 02 and are never asserted against Attempt 01 hashes.
    # If immutable Attempt 01 archive copies exist, validate those copies against the recorded historical identities.
    $attempt01ImmutableLogArchives = @()
    foreach ($mapping in @(
        [pscustomobject]@{ ArchivePath = $attempt01ServerLogArchive; HistoricalIdentity = $attempt01HistoricalServerLog[0] },
        [pscustomobject]@{ ArchivePath = $attempt01ClientLogArchive; HistoricalIdentity = $attempt01HistoricalClientLog[0] }
    )) {
        if (Test-Path -LiteralPath $mapping.ArchivePath -PathType Leaf) {
            $archiveIdentity = [ordered]@{
                path = $mapping.ArchivePath
                size_bytes = [int64]$mapping.HistoricalIdentity.size_bytes
                sha256 = [string]$mapping.HistoricalIdentity.sha256
            }
            Assert-ERefitAttempt02Identity -Identity $archiveIdentity -Label 'Immutable Attempt 01 archived log evidence'
            $attempt01ImmutableLogArchives += Get-ERefitAttempt02Identity $mapping.ArchivePath
        }
    }

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
        Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $authorityPath -PathType Leaf) "Runtime authority absent: $authorityPath"
        $item = Get-Item -LiteralPath $authorityPath
        Assert-ERefitAttempt02Condition ($item.Length -eq [int64]$authority.size_bytes -and (Get-ERefitAttempt02Sha256 $item.FullName) -ceq [string]$authority.sha256) "Runtime authority hash drift: $authorityPath"
    }
    Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 (Join-Path $serverRoot 'mods\mineocclude-0.1.1.jar')) -ceq $jarSha256) 'Installed server JAR drift'
    Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 (Join-Path $clientRoot 'mods\mineocclude-0.1.1.jar')) -ceq $jarSha256) 'Installed client JAR drift'
    Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 (Join-Path $clientRoot 'options.txt')) -ceq [string]$manifest.runtime_identity.client_options.sha256) 'Client options drift'
    $optionsText = Get-Content -Raw -LiteralPath (Join-Path $clientRoot 'options.txt')
    Assert-ERefitAttempt02Condition ($optionsText -match '(?m)^fov:0\.0\r?$' -and $optionsText -match '(?m)^fullscreen:false\r?$' -and $optionsText -match '(?m)^guiScale:2\r?$') 'Client options no longer encode the accepted window/FOV/GUI state'

    $repairReceipt = Get-Content -Raw -LiteralPath $repairReceiptPath | ConvertFrom-Json
    Assert-ERefitAttempt02Condition ($repairReceipt.status -eq 'PASS' -and $repairReceipt.accepted_difference_classification -eq 'MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION') 'Server-properties semantic-validator repair is not authoritative'
    Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 $serverPropertiesModulePath) -ceq [string]$repairReceipt.semantic_validator.sha256) 'Server-properties semantic validator identity drift'
    $serverPropertiesComparison = Compare-ServerPropertiesAuthority -AuthorityPath $serverPropertiesAuthorityPath -RuntimePath $serverPropertiesRuntimePath
    Assert-ERefitAttempt02Condition ($serverPropertiesComparison.status -eq 'PASS' -and $serverPropertiesComparison.drift_classification -eq 'MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION') 'Runtime server.properties is not the accepted Minecraft auto-expansion of the strict authority'

    $preflightReceiptPath = [string]$manifest.preflight.receipt_path
    $preflightEvidencePath = [string]$manifest.preflight.external_evidence_path
    foreach ($path in @($preflightReceiptPath, $preflightEvidencePath)) {
        Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $path -PathType Leaf) "Successful mandatory framebuffer preflight evidence absent: $path"
    }
    $preflight = Get-Content -Raw -LiteralPath $preflightReceiptPath | ConvertFrom-Json
    Assert-ERefitAttempt02Condition ($preflight.status -eq 'PASS' -and $preflight.attempt_name -ceq $attemptName) 'Mandatory framebuffer preflight did not pass for Attempt 02'
    Assert-ERefitAttempt02Condition ($preflight.observed_framebuffer.width_pixels -eq 1920 -and $preflight.observed_framebuffer.height_pixels -eq 1046) 'Mandatory framebuffer preflight receipt is not 1920x1046'
    Assert-ERefitAttempt02Condition ($preflight.excluded_from_layout_screenshot_count -eq $true -and $preflight.disposable_preflight_screenshot -eq $true) 'Preflight/layout exclusion contract drift'
    Assert-Attempt02Identity $preflight.external_preflight_evidence 'Preflight external screenshot'
    Assert-Attempt02Identity $preflight.source_screenshot 'Preflight source screenshot'
    $preflightDimensions = Get-ERefitAttempt02PngDimensions $preflightEvidencePath
    Assert-ERefitAttempt02Condition ($preflightDimensions.Width -eq 1920 -and $preflightDimensions.Height -eq 1046) 'Preflight external screenshot is not 1920x1046'
    Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02PrefixSha256 $serverLogPath ([int64]$preflight.server_session_prefix.size_bytes)) -ceq [string]$preflight.server_session_prefix.sha256) 'Server log is not an append-only continuation of the preflight session'
    Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02PrefixSha256 $clientLogPath ([int64]$preflight.client_session_prefix.size_bytes)) -ceq [string]$preflight.client_session_prefix.sha256) 'Client log is not an append-only continuation of the preflight session'
    Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 (Join-Path $clientRoot 'options.txt')) -ceq [string]$preflight.client_options.sha256) 'Client options changed after framebuffer preflight'

    $createOnlyPaths = @(
        $serverLogArchive, $clientLogArchive, $attestationPath, $screenshotInventoryPath,
        $receiptInventoryPath, $fitOutputPath, $validationOutputPath, $handoffPath, $resultPath
    )
    foreach ($layout in $manifest.layouts) {
        $createOnlyPaths += [string]$layout.runtime_paths.canonical_screenshot
    }
    foreach ($path in $createOnlyPaths) {
        Assert-ERefitAttempt02Condition (-not (Test-Path -LiteralPath $path)) "Create-only Attempt 02 output already exists: $path"
    }

    $serverLines = @(Get-Content -LiteralPath $serverLogPath)
    $clientLines = @(Get-Content -LiteralPath $clientLogPath)
    $accountEvent = Find-UniqueAttempt02LogEvent $clientLines 'Setting user: ([A-Za-z0-9_]+)' 'authenticated client account'
    Assert-ERefitAttempt02Condition ($accountEvent.Line -match 'Setting user: ([A-Za-z0-9_]+)') 'Unable to parse authenticated account'
    $observedAccount = $Matches[1]
    Assert-ERefitAttempt02Condition ($observedAccount -ceq [string]$preflight.observed_account) 'Client account differs from framebuffer preflight'
    $fovEvent = Find-UniqueAttempt02LogEvent $clientLines '\[MineOcclude/client\] FOV pinned to 70 \(Normal\)' 'accepted FOV 70.0 client event'
    $connectEvent = Find-UniqueAttempt02LogEvent $clientLines 'Connecting to 127\.0\.0\.1, 25565' 'loopback connection'
    $clientStop = Find-UniqueAttempt02LogEvent $clientLines 'Stopping!' 'clean client stop'
    $serverStop = Find-UniqueAttempt02LogEvent $serverLines 'Stopping server' 'clean server stop'
    $preflightFileName = Split-Path -Leaf ([string]$preflight.source_screenshot.path)
    $preflightEvent = Find-UniqueAttempt02LogEvent $clientLines ("Saved screenshot as {0}" -f [regex]::Escape($preflightFileName)) 'disposable preflight F2 event'

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
        $controlEvents += Find-UniqueAttempt02LogEvent $serverLines $pattern "single session control: $pattern"
    }
    for ($index = 1; $index -lt $controlEvents.Count; $index++) {
        Assert-ERefitAttempt02Condition ($controlEvents[$index - 1].Index -lt $controlEvents[$index].Index) 'Attempt 02 session controls were not applied once in order'
    }
    $allArmed = @($serverLines | Where-Object { $_ -match '\[MineOcclude\] episode \d+ armed' })
    Assert-ERefitAttempt02Condition ($allArmed.Count -eq 6) 'Attempt 02 server session must contain exactly six armed episodes'
    $firstArmed = Find-UniqueAttempt02LogEvent $serverLines ("\[MineOcclude\] episode {0} armed" -f [int]$manifest.layouts[0].episode_id) 'first Attempt 02 episode armed'
    Assert-ERefitAttempt02Condition ($controlEvents[-1].Index -lt $firstArmed.Index) 'Attempt 02 controls were not completed before the first episode'
    $sessionBaseSeconds = Get-Attempt02LineSeconds $firstArmed.Line 'first armed event'
    $preflightSeconds = Get-Attempt02LineSeconds $preflightEvent.Line 'preflight F2 event'
    $preflightToFirstArm = Get-Attempt02OffsetSeconds $preflightSeconds $sessionBaseSeconds
    Assert-ERefitAttempt02Condition ($preflightToFirstArm -gt 0 -and $preflightToFirstArm -lt 43200) 'Disposable preflight F2 was not before the first Attempt 02 episode'

    $previousAbortIndex = -1
    $seenRawScreenshots = @{}
    $validatedLayouts = @()
    $layoutScreenshotInputs = @()
    foreach ($layout in $manifest.layouts) {
        $layoutId = [string]$layout.layout_id
        $episodeId = [int]$layout.episode_id
        $seed = [int64]$layout.seed
        $receiptId = "${attemptName}_$layoutId"
        $receiptPath = [string]$layout.runtime_paths.geometry_receipt
        $schedulePath = [string]$layout.schedule.runtime_schedule.path
        foreach ($path in @($receiptPath, $schedulePath)) {
            Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $path -PathType Leaf) "Required $layoutId runtime input absent: $path"
        }
        Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 $schedulePath) -ceq [string]$layout.schedule.runtime_schedule.sha256) "$layoutId runtime schedule hash mismatch"

        $armed = Find-UniqueAttempt02LogEvent $serverLines ("\[MineOcclude\] episode {0} armed \(layout={1}, 12000 warmup \+ 20 record ticks, v=0\.0, q=0\.0, seed={2}, rng=immutable_numpy_schedule\)" -f $episodeId, $layoutId, $seed) "$layoutId armed"
        $scheduleLoaded = Find-UniqueAttempt02LogEvent $serverLines ("loaded immutable noise schedule \(20 draws\) from .*episode_{0}\.jsonl" -f $episodeId) "$layoutId immutable schedule load"
        $targetStatus = Find-UniqueAttempt02LogEvent $serverLines ("\[MineOcclude/target\] target status: valid=true required=true count=1.*layout={0} episode={1} lifecycle=READY problems=NONE" -f $layoutId, $episodeId) "$layoutId passing targetstatus"
        $observe = Find-UniqueAttempt02LogEvent $serverLines ("\[MineOcclude/observation\] wrote read-only geometry receipt .*{0}\.json" -f $receiptId) "$layoutId observegeometry"
        $confirmation = Find-UniqueAttempt02LogEvent $serverLines ("Wrote observation-only geometry receipt: .*{0}\.json" -f $receiptId) "$layoutId receipt confirmation"
        $abort = Find-UniqueAttempt02LogEvent $serverLines ("\[MineOcclude\] episode {0} aborted during warmup" -f $episodeId) "$layoutId warmup abort"
        Assert-ERefitAttempt02Condition ($previousAbortIndex -lt $armed.Index -and $armed.Index -le $scheduleLoaded.Index -and $scheduleLoaded.Index -lt $targetStatus.Index -and $targetStatus.Index -lt $observe.Index -and $observe.Index -le $confirmation.Index -and $confirmation.Index -lt $abort.Index -and $abort.Index -lt $serverStop.Index) "$layoutId server chronology failed"
        Assert-ERefitAttempt02Condition (-not ($serverLines -match ("episode {0} recording started" -f $episodeId))) "$layoutId entered recording"
        $previousAbortIndex = $abort.Index

        $armedSeconds = Get-Attempt02LineSeconds $armed.Line "$layoutId armed"
        $statusOffsetFromArmed = Get-Attempt02OffsetSeconds $armedSeconds (Get-Attempt02LineSeconds $targetStatus.Line "$layoutId targetstatus")
        Assert-ERefitAttempt02Condition ($statusOffsetFromArmed -ge 10) "$layoutId targetstatus occurred less than ten seconds after arming"
        $confirmationOffset = Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $confirmation.Line "$layoutId receipt confirmation")
        $abortOffset = Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $abort.Line "$layoutId abort")
        $screenshotEvents = @()
        foreach ($line in $clientLines) {
            if ($line -match 'Saved screenshot as ([^\\/\s]+\.png)') {
                $eventOffset = Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $line 'screenshot event')
                if ($eventOffset -gt $confirmationOffset -and $eventOffset -lt $abortOffset) {
                    $screenshotEvents += [pscustomobject]@{ Offset = $eventOffset; FileName = $Matches[1]; Line = $line }
                }
            }
        }
        Assert-ERefitAttempt02Condition ($screenshotEvents.Count -eq 1) "$layoutId requires exactly one in-window F2 screenshot after receipt confirmation and before abort"
        Assert-ERefitAttempt02Condition ($screenshotEvents[0].FileName -cne $preflightFileName) "$layoutId attempts to count the disposable preflight screenshot"
        $rawScreenshot = Join-Path (Join-Path $clientRoot 'screenshots') $screenshotEvents[0].FileName
        Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $rawScreenshot -PathType Leaf) "$layoutId logged screenshot is absent: $rawScreenshot"
        Assert-ERefitAttempt02Condition (-not $seenRawScreenshots.ContainsKey($rawScreenshot)) "$layoutId reused a raw screenshot"
        $seenRawScreenshots[$rawScreenshot] = $true
        $layoutScreenshotInputs += [pscustomobject]@{ layout_id = $layoutId; path = $rawScreenshot }

        $receipt = Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json
        Assert-ERefitAttempt02Condition ($receipt.schema_version -eq 'person-c-c1-runtime-geometry-observation-v0.1' -and $receipt.receipt_id -ceq $receiptId) "$layoutId receipt schema/ID mismatch"
        Assert-ERefitAttempt02Condition ($receipt.observation_only -eq $true -and $receipt.scientific_use -eq 'forbidden' -and $receipt.mutates_runtime_state -eq $false) "$layoutId receipt is not observation-only"
        Assert-ERefitAttempt02Condition ($receipt.layout_id -eq $layoutId -and [int]$receipt.episode_id -eq $episodeId) "$layoutId receipt layout/episode mismatch"
        Assert-ERefitAttempt02Condition ($receipt.scene -eq 'NORMAL' -and $receipt.running -eq $true -and $receipt.capturing -eq $false -and $receipt.lifecycle_state -eq 'READY' -and [int]$receipt.warmup_ticks_remaining -gt 0) "$layoutId receipt was not captured during READY warmup"
        Assert-ERefitAttempt02Condition ($receipt.target.valid -eq $true -and $receipt.target.required -eq $true -and [int]$receipt.target.tagged_target_count -eq 1 -and $receipt.target.problems.Count -eq 0) "$layoutId target status failed"
        Assert-ERefitAttempt02Condition (Test-Attempt02JsonEqual $receipt.target.actual_xyz $layout.layout_geometry.target_start.world_xyz) "$layoutId actual target coordinate mismatch"
        Assert-ERefitAttempt02Condition (Test-Attempt02JsonEqual $receipt.target.expected_xyz $layout.layout_geometry.target_start.world_xyz) "$layoutId expected target coordinate mismatch"
        Assert-ERefitAttempt02Condition ($receipt.floor.mismatches.Count -eq 0 -and [int]$receipt.floor.matching_position_count -eq [int]$receipt.floor.expected_position_count) "$layoutId floor mismatch"
        Assert-ERefitAttempt02Condition ($receipt.wall.mismatches.Count -eq 0 -and [int]$receipt.wall.matching_position_count -eq [int]$receipt.wall.expected_position_count) "$layoutId wall mismatch"
        foreach ($property in $layout.layout_geometry.expected_receipt_geometry.floor.PSObject.Properties) {
            Assert-ERefitAttempt02Condition ($receipt.floor.($property.Name) -eq $property.Value) "$layoutId floor field mismatch: $($property.Name)"
        }
        foreach ($property in $layout.layout_geometry.expected_receipt_geometry.wall.PSObject.Properties) {
            Assert-ERefitAttempt02Condition ($receipt.wall.($property.Name) -eq $property.Value) "$layoutId wall field mismatch: $($property.Name)"
        }
        Assert-ERefitAttempt02Condition ([int]$receipt.observed_marker_block_count -eq 4 -and $receipt.markers.Count -eq 4) "$layoutId marker count mismatch"
        foreach ($expectedMarker in $layout.layout_geometry.markers) {
            $actualMarker = @($receipt.markers | Where-Object { $_.role -eq $expectedMarker.marker_id })
            Assert-ERefitAttempt02Condition ($actualMarker.Count -eq 1) "$layoutId marker missing or duplicated: $($expectedMarker.marker_id)"
            Assert-ERefitAttempt02Condition ($actualMarker[0].matches -eq $true -and (Test-Attempt02JsonEqual $actualMarker[0].block_pos_xyz $expectedMarker.block_pos_xyz) -and (Test-Attempt02JsonEqual $actualMarker[0].top_face_centre_world_xyz $expectedMarker.top_face_centre_world_xyz)) "$layoutId literal marker mismatch: $($expectedMarker.marker_id)"
        }
        Assert-ERefitAttempt02Condition (Test-Attempt02JsonEqual $receipt.camera.canonical_feet_xyz $layout.layout_geometry.camera.feet_xyz) "$layoutId canonical camera position mismatch"
        Assert-ERefitAttempt02Condition ([double]$receipt.camera.canonical_yaw_degrees -eq [double]$layout.layout_geometry.camera.yaw_degrees -and [double]$receipt.camera.canonical_pitch_degrees -eq [double]$layout.layout_geometry.camera.pitch_degrees) "$layoutId canonical camera orientation mismatch"
        Assert-ERefitAttempt02Condition ($receipt.camera.observed_players.Count -eq 1 -and $receipt.camera.observed_players[0].name -ceq $observedAccount) "$layoutId observed player/session mismatch"
        Assert-ERefitAttempt02Condition (Test-Attempt02JsonEqual $receipt.camera.observed_players[0].feet_xyz $layout.layout_geometry.camera.feet_xyz) "$layoutId observed camera position mismatch"
        Assert-ERefitAttempt02Condition ([double]$receipt.camera.observed_players[0].yaw_degrees -eq [double]$layout.layout_geometry.camera.yaw_degrees -and [double]$receipt.camera.observed_players[0].pitch_degrees -eq [double]$layout.layout_geometry.camera.pitch_degrees) "$layoutId observed camera orientation mismatch"

        $validatedLayouts += [pscustomobject]@{
            Preparation = $layout
            ReceiptPath = $receiptPath
            RawScreenshotPath = $rawScreenshot
            CanonicalScreenshotPath = [string]$layout.runtime_paths.canonical_screenshot
            ArmedOffsetSeconds = Get-Attempt02OffsetSeconds $sessionBaseSeconds $armedSeconds
            TargetStatusOffsetSeconds = Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $targetStatus.Line "$layoutId targetstatus")
            ReceiptConfirmationOffsetSeconds = $confirmationOffset
            ScreenshotOffsetSeconds = $screenshotEvents[0].Offset
            AbortOffsetSeconds = $abortOffset
        }
    }

    $validatedScreenshotIdentities = @(Assert-ERefitAttempt02LayoutScreenshotSet -Layouts $layoutScreenshotInputs -PreflightEvidencePath $preflightEvidencePath -PreflightSourcePath ([string]$preflight.source_screenshot.path))
    Assert-ERefitAttempt02Condition ($validatedLayouts.Count -eq 6 -and $seenRawScreenshots.Count -eq 6 -and $validatedScreenshotIdentities.Count -eq 6) 'All six distinct 1920x1046 Attempt 02 screenshots were not validated'
    Assert-ERefitAttempt02Condition ($accountEvent.Index -lt $fovEvent.Index -and $fovEvent.Index -lt $connectEvent.Index -and $connectEvent.Index -lt $preflightEvent.Index -and $preflightEvent.Index -lt $clientStop.Index) 'Client account/FOV/connection/preflight/stop order failed'
    $lastAbortOffset = $validatedLayouts[-1].AbortOffsetSeconds
    Assert-ERefitAttempt02Condition ((Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $serverStop.Line 'server stop')) -gt $lastAbortOffset) 'Server did not stop after the sixth warmup abort'
    Assert-ERefitAttempt02Condition ((Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $clientStop.Line 'client stop')) -gt $lastAbortOffset) 'Client did not stop after the sixth warmup abort'
    $inWindowScreenshotEvents = @()
    foreach ($line in $clientLines) {
        if ($line -match 'Saved screenshot as ([^\\/\s]+\.png)') {
            $eventOffset = Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $line 'session screenshot event')
            if ($eventOffset -gt 0 -and $eventOffset -lt $lastAbortOffset) { $inWindowScreenshotEvents += $line }
        }
    }
    Assert-ERefitAttempt02Condition ($inWindowScreenshotEvents.Count -eq 6) 'Exactly six layout F2 events must occur from first arm through sixth warmup abort; the preflight F2 is excluded'

    $confirmation = Read-Host 'Type YES only if one authenticated operator ran the entire Attempt 02 session and all six layout screenshots are normal gameplay with no pause menu, chat, inventory, or F3 overlay'
    Assert-ERefitAttempt02Condition ($confirmation -ceq 'YES') 'Required one-YES operator attestation was not provided'

    foreach ($directory in @($serverEvidenceDir, $clientEvidenceDir)) {
        if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory | Out-Null }
    }
    Copy-ERefitAttempt02CreateOnly $serverLogPath $serverLogArchive
    Copy-ERefitAttempt02CreateOnly $clientLogPath $clientLogArchive
    foreach ($validated in $validatedLayouts) {
        Copy-ERefitAttempt02CreateOnly $validated.RawScreenshotPath $validated.CanonicalScreenshotPath
        Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 $validated.RawScreenshotPath) -ceq (Get-ERefitAttempt02Sha256 $validated.CanonicalScreenshotPath)) "Screenshot copy hash mismatch: $($validated.Preparation.layout_id)"
    }
    Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 $serverLogPath) -ceq (Get-ERefitAttempt02Sha256 $serverLogArchive)) 'Server log archive hash mismatch'
    Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 $clientLogPath) -ceq (Get-ERefitAttempt02Sha256 $clientLogArchive)) 'Client log archive hash mismatch'

    $attestation = Get-Content -Raw -LiteralPath $attestationTemplatePath | ConvertFrom-Json
    $attestation.template = $false
    $attestation.operator_id = $observedAccount
    $attestation.observed_authenticated_account = $observedAccount
    $attestation.single_authenticated_operator = $true
    $attestation.framebuffer_preflight_passed = $true
    $attestation.preflight_screenshot_excluded_from_layouts = $true
    $attestation.normal_gameplay_no_pause_chat_inventory_or_f3_for_all_screenshots = $true
    $attestation.exactly_one_f2_per_layout_after_receipt_confirmation = $true
    $attestation.all_six_episodes_aborted_during_warmup = $true
    $attestation.recording_never_started = $true
    $attestation.same_server_client_options_render_and_log_session = $true
    $attestation.preparation_commit = $preparationCommit
    $attestation.utc_start = (Get-Item -LiteralPath $serverLogPath).CreationTimeUtc.ToString('o')
    $attestation.utc_end = (Get-Item -LiteralPath $serverLogPath).LastWriteTimeUtc.ToString('o')
    $attestation.notes = 'One operator attested YES only after all fail-closed Attempt 02 validations passed and before create-only finalization.'
    Write-ERefitAttempt02CreateOnlyJson $attestationPath $attestation

    $fitTemplate = Get-Content -Raw -LiteralPath $fitTemplatePath | ConvertFrom-Json
    $validationTemplate = Get-Content -Raw -LiteralPath $validationTemplatePath | ConvertFrom-Json
    $screenshotRows = @()
    $receiptRows = @()
    $layoutEvidence = @()
    foreach ($validated in $validatedLayouts) {
        $layoutId = [string]$validated.Preparation.layout_id
        $canonical = Get-ERefitAttempt02Identity $validated.CanonicalScreenshotPath
        $raw = Get-ERefitAttempt02Identity $validated.RawScreenshotPath
        $receiptIdentity = Get-ERefitAttempt02Identity $validated.ReceiptPath
        $fitRow = @($fitTemplate.layouts | Where-Object { $_.layout_id -eq $layoutId })
        $validationRow = @($validationTemplate.layouts | Where-Object { $_.layout_id -eq $layoutId })
        Assert-ERefitAttempt02Condition ($fitRow.Count -eq 1 -and $validationRow.Count -eq 1) "$layoutId annotation template row missing"
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
            schedule = Get-ERefitAttempt02Identity ([string]$validated.Preparation.schedule.runtime_schedule.path)
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
    Write-ERefitAttempt02CreateOnlyJson $fitOutputPath $fitTemplate
    Write-ERefitAttempt02CreateOnlyJson $validationOutputPath $validationTemplate

    $screenshotInventory = [ordered]@{
        schema_version = 'person-c-e-refit-calibration-attempt-02-screenshot-inventory-v0.1'
        status = 'PASS'
        screenshot_count = 6
        preflight_screenshot_counted = $false
        same_client_session = $true
        framebuffer = [ordered]@{ width_pixels = 1920; height_pixels = 1046 }
        screenshots = $screenshotRows
    }
    $receiptInventory = [ordered]@{
        schema_version = 'person-c-e-refit-calibration-attempt-02-geometry-receipt-inventory-v0.1'
        status = 'PASS'
        receipt_count = 6
        accepted_geometry_version = $geometryVersion
        accepted_geometry_sha256 = $geometrySha256
        receipts = $receiptRows
    }
    Write-ERefitAttempt02CreateOnlyJson $screenshotInventoryPath $screenshotInventory
    Write-ERefitAttempt02CreateOnlyJson $receiptInventoryPath $receiptInventory

    $handoff = [ordered]@{
        schema_version = 'person-c-to-person-e-v0.4-calibration-image-handoff-attempt-02-v0.1'
        status = 'READY_FOR_PERSON_E_ANNOTATION_NOT_HOMOGRAPHY_FIT_YET'
        immutable = $true
        preparation_commit = $preparationCommit
        package_bundle_sha256 = $packageInventory.package_bundle_sha256
        attempt_01 = [ordered]@{
            preserved = $true
            classification = $attempt01Classification
            certified = $false
            immutable_repository_manifest = Get-ERefitAttempt02Identity $attempt01ManifestPath
            immutable_repository_package_inventory = Get-ERefitAttempt02Identity $attempt01PackageInventoryPath
            immutable_repair_package_inventory = Get-ERefitAttempt02Identity $attempt01RepairPackageInventoryPath
            immutable_log_archives = @($attempt01ImmutableLogArchives)
            historical_mutable_latest_log_identities_recorded_only = @($attempt01MutableLatestLogIdentitiesRecordedOnly)
            mutable_latest_log_paths_are_preserved_artifacts = $false
        }
        attempt_name = $attemptName
        accepted_geometry_version = $geometryVersion
        accepted_geometry_sha256 = $geometrySha256
        mineocclude_jar_sha256 = $jarSha256
        fov_degrees = 70.0
        framebuffer = [ordered]@{ width_pixels = 1920; height_pixels = 1046 }
        framebuffer_preflight = Get-ERefitAttempt02Identity $preflightReceiptPath
        preflight_screenshot_counted_as_layout = $false
        options = Get-ERefitAttempt02Identity (Join-Path $clientRoot 'options.txt')
        environment_lock = Get-ERefitAttempt02Identity (Join-Path $RepoRoot 'docs\status\person_c_c1_runtime_ingestion_v0_1\final_environment_lock_receipt.json')
        server_properties_authority_validation = $serverPropertiesComparison
        coordinate_convention = Get-ERefitAttempt02Identity $coordinateConventionPath
        authenticated_account = $observedAccount
        operator_attestation = Get-ERefitAttempt02Identity $attestationPath
        current_latest_logs_classification = 'ATTEMPT_02_SESSION_EVIDENCE_ONLY'
        server_log = Get-ERefitAttempt02Identity $serverLogArchive
        client_log = Get-ERefitAttempt02Identity $clientLogArchive
        screenshot_inventory = Get-ERefitAttempt02Identity $screenshotInventoryPath
        geometry_receipt_inventory = Get-ERefitAttempt02Identity $receiptInventoryPath
        e_image_point_annotation_template = Get-ERefitAttempt02Identity $fitOutputPath
        e_independent_validation_pair_template = Get-ERefitAttempt02Identity $validationOutputPath
        person_c_invented_image_coordinates = $false
        person_c_fit_homographies = $false
        layouts = $layoutEvidence
    }
    Write-ERefitAttempt02CreateOnlyJson $handoffPath $handoff
    $result = [ordered]@{
        schema_version = 'person-c-e-refit-calibration-attempt-02-finalization-result-v0.1'
        status = 'PASS'
        preparation_commit = $preparationCommit
        attempt_01_preserved = $true
        attempt_01_classification = $attempt01Classification
        attempt_01_mutable_latest_log_paths_are_preserved_artifacts = $false
        current_latest_logs_classification = 'ATTEMPT_02_SESSION_EVIDENCE_ONLY'
        framebuffer_preflight_valid = $true
        preflight_screenshot_counted_as_layout = $false
        operator_id = $observedAccount
        layout_count = 6
        episode_ids = @($manifest.layouts | ForEach-Object { [int]$_.episode_id })
        chronology_valid = $true
        screenshot_dimensions_valid = $true
        geometry_receipts_valid = $true
        recording_never_started = $true
        homography_fit_performed = $false
        c6a_executed = $false
        runtime_evidence_modified_in_place = $false
        server_properties_authority_validation = $serverPropertiesComparison
        handoff = Get-ERefitAttempt02Identity $handoffPath
    }
    Write-ERefitAttempt02CreateOnlyJson $resultPath $result

    Write-Output 'E_REFIT_CALIBRATION_ATTEMPT_02_FINALIZE_BEGIN'
    Write-Output "PREPARATION_COMMIT=$preparationCommit"
    Write-Output 'ATTEMPT_01_PRESERVED=True'
    Write-Output "ATTEMPT_01_CLASSIFICATION=$attempt01Classification"
    Write-Output 'FRAMEBUFFER_PREFLIGHT_VALID=True'
    Write-Output 'PREFLIGHT_SCREENSHOT_COUNTED=False'
    Write-Output "OPERATOR_ID=$observedAccount"
    Write-Output 'CALIBRATION_LAYOUT_COUNT=6'
    Write-Output 'CHRONOLOGY_VALID=True'
    Write-Output 'SCREENSHOT_COUNT=6'
    Write-Output 'GEOMETRY_RECEIPT_COUNT=6'
    Write-Output "HANDOFF_PATH=$handoffPath"
    Write-Output "HANDOFF_SHA256=$(Get-ERefitAttempt02Sha256 $handoffPath)"
    Write-Output 'PERSON_E_IMAGE_POINTS_PENDING=True'
    Write-Output 'HOMOGRAPHY_FIT_PERFORMED=False'
    Write-Output 'C6A_EXECUTED=False'
    Write-Output 'E_REFIT_CALIBRATION_ATTEMPT_02_FINALIZE_END'
}
finally {
    Pop-Location
}
