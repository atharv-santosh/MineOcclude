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
    $eventMatches = [System.Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index] -match $Pattern) {
            [void]$eventMatches.Add([pscustomobject]@{ Index = $index; Line = $Lines[$index] })
        }
    }
    Assert-ERefitAttempt02Condition ($eventMatches.Count -eq 1) "$Label must occur exactly once; observed $($eventMatches.Count)"
    return $eventMatches[0]
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

function New-Attempt02SemanticRepresentation {
    param(
        [Parameter(Mandatory = $true)][int]$Index,
        [Parameter(Mandatory = $true)][string]$Line,
        [Parameter(Mandatory = $true)][string]$EventType,
        [Parameter(Mandatory = $true)][int]$EpisodeId,
        [Parameter(Mandatory = $true)][string]$LayoutId,
        [Parameter(Mandatory = $true)][string]$RepresentationKind,
        [string]$ReceiptPath = ''
    )
    Assert-ERefitAttempt02Condition ($Line -match '^\[(\d{2}:\d{2}:\d{2})\]') "$EventType event has no HH:MM:SS timestamp"
    return [pscustomobject]@{
        Index = $Index
        Line = $Line
        EventType = $EventType
        EpisodeId = $EpisodeId
        LayoutId = $LayoutId
        Timestamp = $Matches[1]
        TimestampSeconds = Get-Attempt02LineSeconds $Line "$LayoutId $EventType"
        ReceiptPath = $ReceiptPath
        RepresentationKind = $RepresentationKind
    }
}

function Get-Attempt02SemanticEvent {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][System.Collections.Generic.List[object]]$Representations,
        [Parameter(Mandatory = $true)][string]$Label
    )
    Assert-ERefitAttempt02Condition ($Representations.Count -gt 0) "$Label is absent"
    $semanticGroups = @{}
    foreach ($representation in $Representations) {
        $normalizedReceiptPath = ([string]$representation.ReceiptPath).Replace('/', '\').ToLowerInvariant()
        $semanticKey = '{0}|{1}|{2}|{3}|{4}' -f (
            [string]$representation.EventType,
            [int]$representation.EpisodeId,
            [string]$representation.LayoutId,
            [string]$representation.Timestamp,
            $normalizedReceiptPath
        )
        if (-not $semanticGroups.ContainsKey($semanticKey)) {
            $semanticGroups[$semanticKey] = [System.Collections.Generic.List[object]]::new()
        }
        [void]$semanticGroups[$semanticKey].Add($representation)
    }
    Assert-ERefitAttempt02Condition ($semanticGroups.Count -eq 1) "$Label must occur exactly once by semantic identity; observed $($semanticGroups.Count)"
    $semanticKey = [string]@($semanticGroups.Keys)[0]
    $group = $semanticGroups[$semanticKey]
    $orderedRepresentations = @($group | Sort-Object -Property Index)
    $first = $orderedRepresentations[0]
    $last = $orderedRepresentations[$orderedRepresentations.Count - 1]
    return [pscustomobject]@{
        Index = [int]$first.Index
        FirstIndex = [int]$first.Index
        LastIndex = [int]$last.Index
        Line = [string]$first.Line
        Lines = [string[]]@($orderedRepresentations | ForEach-Object { [string]$_.Line })
        EventType = [string]$first.EventType
        EpisodeId = [int]$first.EpisodeId
        LayoutId = [string]$first.LayoutId
        Timestamp = [string]$first.Timestamp
        TimestampSeconds = [int]$first.TimestampSeconds
        ReceiptPath = [string]$first.ReceiptPath
        RepresentationCount = $orderedRepresentations.Count
    }
}

function Get-Attempt02LayoutChronology {
    param(
        [Parameter(Mandatory = $true)][string[]]$Lines,
        [Parameter(Mandatory = $true)][string]$LayoutId,
        [Parameter(Mandatory = $true)][int]$EpisodeId,
        [Parameter(Mandatory = $true)][int64]$Seed,
        [Parameter(Mandatory = $true)][string]$ReceiptId,
        [Parameter(Mandatory = $true)][int]$PreviousAbortIndex,
        [Parameter(Mandatory = $true)][int]$ServerStopIndex
    )
    $startRepresentations = [System.Collections.Generic.List[object]]::new()
    $scheduleRepresentations = [System.Collections.Generic.List[object]]::new()
    $armedRepresentations = [System.Collections.Generic.List[object]]::new()
    $targetRepresentations = [System.Collections.Generic.List[object]]::new()
    $abortRepresentations = [System.Collections.Generic.List[object]]::new()
    $recordingRepresentations = [System.Collections.Generic.List[object]]::new()

    for ($index = 0; $index -lt $Lines.Count; $index++) {
        $line = $Lines[$index]
        if ($line -match '\[MineOcclude\] /start requested: layout=(?<layout>layout_\d{2}) ep=(?<episode>\d+) seed=(?<seed>-?\d+) v=(?<v>-?[0-9.]+) q=(?<q>-?[0-9.]+) ticks=(?<ticks>\d+) warmup=(?<warmup>\d+)') {
            $parsedLayout = [string]$Matches['layout']
            $parsedEpisode = [int]$Matches['episode']
            if ($parsedLayout -ceq $LayoutId -or $parsedEpisode -eq $EpisodeId) {
                Assert-ERefitAttempt02Condition ($parsedLayout -ceq $LayoutId -and $parsedEpisode -eq $EpisodeId) "$LayoutId start command identity mismatch"
                Assert-ERefitAttempt02Condition ([int64]$Matches['seed'] -eq $Seed -and [double]$Matches['v'] -eq 0.0 -and [double]$Matches['q'] -eq 0.0 -and [int]$Matches['ticks'] -eq 20 -and [int]$Matches['warmup'] -eq 12000) "$LayoutId start command parameters drifted"
                [void]$startRepresentations.Add((New-Attempt02SemanticRepresentation $index $line 'START_REQUESTED' $EpisodeId $LayoutId 'INFORMATIONAL'))
            }
        }
        if ($line -match 'loaded immutable noise schedule \(20 draws\) from .*episode_(?<episode>\d+)\.jsonl') {
            $parsedEpisode = [int]$Matches['episode']
            if ($parsedEpisode -eq $EpisodeId) {
                [void]$scheduleRepresentations.Add((New-Attempt02SemanticRepresentation $index $line 'SCHEDULE_LOADED' $EpisodeId $LayoutId 'INFORMATIONAL'))
            }
        }
        if ($line -match '\[MineOcclude\] episode (?<episode>\d+) armed \(layout=(?<layout>layout_\d{2}), (?<warmup>\d+) warmup \+ (?<record>\d+) record ticks, v=(?<v>-?[0-9.]+), q=(?<q>-?[0-9.]+), seed=(?<seed>-?\d+), rng=(?<rng>[^)]+)\)') {
            $parsedLayout = [string]$Matches['layout']
            $parsedEpisode = [int]$Matches['episode']
            if ($parsedLayout -ceq $LayoutId -or $parsedEpisode -eq $EpisodeId) {
                Assert-ERefitAttempt02Condition ($parsedLayout -ceq $LayoutId -and $parsedEpisode -eq $EpisodeId) "$LayoutId armed event identity mismatch"
                Assert-ERefitAttempt02Condition ([int]$Matches['warmup'] -eq 12000 -and [int]$Matches['record'] -eq 20 -and [double]$Matches['v'] -eq 0.0 -and [double]$Matches['q'] -eq 0.0 -and [int64]$Matches['seed'] -eq $Seed -and [string]$Matches['rng'] -ceq 'immutable_numpy_schedule') "$LayoutId armed event parameters drifted"
                [void]$armedRepresentations.Add((New-Attempt02SemanticRepresentation $index $line 'ARMED' $EpisodeId $LayoutId 'INFORMATIONAL'))
            }
        }
        elseif ($line -match 'Armed episode (?<episode>\d+) \((?<layout>layout_\d{2}), scene (?<scene>[A-Z]+), warmup (?<warmup>\d+)t, record (?<record>\d+)t, hiddenTarget (?<hidden>\d+)\)') {
            $parsedLayout = [string]$Matches['layout']
            $parsedEpisode = [int]$Matches['episode']
            if ($parsedLayout -ceq $LayoutId -or $parsedEpisode -eq $EpisodeId) {
                Assert-ERefitAttempt02Condition ($parsedLayout -ceq $LayoutId -and $parsedEpisode -eq $EpisodeId) "$LayoutId armed console event identity mismatch"
                Assert-ERefitAttempt02Condition ([string]$Matches['scene'] -ceq 'NORMAL' -and [int]$Matches['warmup'] -eq 12000 -and [int]$Matches['record'] -eq 20 -and [int]$Matches['hidden'] -eq 0) "$LayoutId armed console event parameters drifted"
                [void]$armedRepresentations.Add((New-Attempt02SemanticRepresentation $index $line 'ARMED' $EpisodeId $LayoutId 'CONSOLE'))
            }
        }
        if ($line -match 'target status: valid=(?<valid>\w+) required=(?<required>\w+) count=(?<count>\d+).*layout=(?<layout>layout_\d{2}) episode=(?<episode>\d+) lifecycle=(?<lifecycle>\w+) problems=(?<problems>\S+)') {
            $parsedLayout = [string]$Matches['layout']
            $parsedEpisode = [int]$Matches['episode']
            if ($parsedLayout -ceq $LayoutId -or $parsedEpisode -eq $EpisodeId) {
                Assert-ERefitAttempt02Condition ($parsedLayout -ceq $LayoutId -and $parsedEpisode -eq $EpisodeId) "$LayoutId targetstatus identity mismatch"
                Assert-ERefitAttempt02Condition ([string]$Matches['valid'] -ceq 'true' -and [string]$Matches['required'] -ceq 'true' -and [int]$Matches['count'] -eq 1 -and [string]$Matches['lifecycle'] -ceq 'READY' -and [string]$Matches['problems'] -ceq 'NONE') "$LayoutId targetstatus did not pass"
                $representationKind = if ($line -match '\[MineOcclude/target\]') { 'INFORMATIONAL' } else { 'CONSOLE' }
                [void]$targetRepresentations.Add((New-Attempt02SemanticRepresentation $index $line 'TARGET_STATUS' $EpisodeId $LayoutId $representationKind))
            }
        }
        if ($line -match 'episode (?<episode>\d+) aborted during warmup') {
            $parsedEpisode = [int]$Matches['episode']
            if ($parsedEpisode -eq $EpisodeId) {
                $representationKind = if ($line -match '\[MineOcclude\]') { 'INFORMATIONAL' } else { 'CONSOLE' }
                [void]$abortRepresentations.Add((New-Attempt02SemanticRepresentation $index $line 'WARMUP_ABORT' $EpisodeId $LayoutId $representationKind))
            }
        }
        if ($line -match 'episode (?<episode>\d+) recording started') {
            $parsedEpisode = [int]$Matches['episode']
            if ($parsedEpisode -eq $EpisodeId) {
                [void]$recordingRepresentations.Add((New-Attempt02SemanticRepresentation $index $line 'RECORDING_STARTED' $EpisodeId $LayoutId 'INFORMATIONAL'))
            }
        }
    }

    $start = Get-Attempt02SemanticEvent $startRepresentations "$LayoutId start command"
    $schedule = Get-Attempt02SemanticEvent $scheduleRepresentations "$LayoutId immutable schedule load"
    $armed = Get-Attempt02SemanticEvent $armedRepresentations "$LayoutId armed"
    $targetStatus = Get-Attempt02SemanticEvent $targetRepresentations "$LayoutId targetstatus"
    $abort = Get-Attempt02SemanticEvent $abortRepresentations "$LayoutId warmup abort"
    Assert-ERefitAttempt02Condition ($recordingRepresentations.Count -eq 0) "$layoutId entered recording"

    $receiptRepresentations = [System.Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($index -le $start.FirstIndex -or $index -ge $abort.LastIndex) { continue }
        $line = $Lines[$index]
        if ($line -match '(?:wrote read-only geometry receipt|Wrote observation-only geometry receipt:)\s+(?<path>\S+\.json)') {
            $receiptPath = [string]$Matches['path']
            Assert-ERefitAttempt02Condition ($receiptPath -match '(?<layout>layout_\d{2})\.json$') "$LayoutId receipt path has no layout identity"
            $receiptLayout = [string]$Matches['layout']
            $representationKind = if ($line -match '\[MineOcclude/observation\]') { 'INFORMATIONAL' } else { 'CONSOLE' }
            [void]$receiptRepresentations.Add((New-Attempt02SemanticRepresentation $index $line 'RECEIPT_WRITTEN' $EpisodeId $receiptLayout $representationKind $receiptPath))
        }
    }
    $receipt = Get-Attempt02SemanticEvent $receiptRepresentations "$LayoutId geometry receipt"
    Assert-ERefitAttempt02Condition ($receipt.LayoutId -ceq $LayoutId -and $receipt.EpisodeId -eq $EpisodeId -and (Split-Path -Leaf $receipt.ReceiptPath) -ceq ($ReceiptId + '.json')) "$LayoutId receipt belongs to another layout or episode"

    Assert-ERefitAttempt02Condition (
        $PreviousAbortIndex -lt $start.FirstIndex -and
        $start.LastIndex -lt $schedule.FirstIndex -and
        $schedule.LastIndex -lt $armed.FirstIndex -and
        $armed.LastIndex -lt $targetStatus.FirstIndex -and
        $targetStatus.LastIndex -lt $receipt.FirstIndex -and
        $receipt.LastIndex -lt $abort.FirstIndex -and
        $abort.LastIndex -lt $ServerStopIndex
    ) "$layoutId server chronology failed"
    $armToTargetSeconds = Get-Attempt02OffsetSeconds $armed.TimestampSeconds $targetStatus.TimestampSeconds
    Assert-ERefitAttempt02Condition ($armToTargetSeconds -ge 10) "$layoutId targetstatus occurred less than ten seconds after arming"

    return [pscustomobject]@{
        Start = $start
        Schedule = $schedule
        Armed = $armed
        TargetStatus = $targetStatus
        Receipt = $receipt
        Abort = $abort
        ArmToTargetSeconds = $armToTargetSeconds
        DuplicateRepresentationCount = (
            ($armed.RepresentationCount - 1) +
            ($targetStatus.RepresentationCount - 1) +
            ($receipt.RepresentationCount - 1) +
            ($abort.RepresentationCount - 1)
        )
    }
}

function Test-Attempt02JsonEqual {
    param($Left, $Right)
    return (($Left | ConvertTo-Json -Depth 50 -Compress) -ceq ($Right | ConvertTo-Json -Depth 50 -Compress))
}

function Assert-Attempt02CreateOnlyPathsAbsent {
    param([Parameter(Mandatory = $true)][System.Collections.Generic.List[string]]$Paths)
    foreach ($path in $Paths) {
        Assert-ERefitAttempt02Condition (-not (Test-Path -LiteralPath $path)) "Create-only Attempt 02 output already exists: $path"
    }
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
    $attempt01PreservedEvidence = [System.Collections.Generic.List[object]]::new()
    foreach ($row in @($attempt01.geometry_receipts)) { [void]$attempt01PreservedEvidence.Add($row) }
    foreach ($row in @($attempt01.raw_screenshots)) { [void]$attempt01PreservedEvidence.Add($row) }
    foreach ($row in $attempt01PreservedEvidence) {
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
    $attempt01ImmutableLogArchives = [System.Collections.Generic.List[object]]::new()
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
            [void]$attempt01ImmutableLogArchives.Add((Get-ERefitAttempt02Identity $mapping.ArchivePath))
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

    $createOnlyPaths = [System.Collections.Generic.List[string]]::new()
    foreach ($path in @(
        $serverLogArchive, $clientLogArchive, $attestationPath, $screenshotInventoryPath,
        $receiptInventoryPath, $fitOutputPath, $validationOutputPath, $handoffPath, $resultPath
    )) {
        [void]$createOnlyPaths.Add([string]$path)
    }
    foreach ($layout in $manifest.layouts) {
        [void]$createOnlyPaths.Add([string]$layout.runtime_paths.canonical_screenshot)
    }
    Assert-Attempt02CreateOnlyPathsAbsent -Paths $createOnlyPaths

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
    $controlEvents = [System.Collections.Generic.List[object]]::new()
    foreach ($pattern in $controlPatterns) {
        [void]$controlEvents.Add((Find-UniqueAttempt02LogEvent $serverLines $pattern "single session control: $pattern"))
    }
    for ($index = 1; $index -lt $controlEvents.Count; $index++) {
        Assert-ERefitAttempt02Condition ($controlEvents[$index - 1].Index -lt $controlEvents[$index].Index) 'Attempt 02 session controls were not applied once in order'
    }
    $allArmed = @($serverLines | Where-Object { $_ -match '\[MineOcclude\] episode \d+ armed' })
    Assert-ERefitAttempt02Condition ($allArmed.Count -eq 6) 'Attempt 02 server session must contain exactly six armed episodes'
    $firstArmed = Find-UniqueAttempt02LogEvent $serverLines ("\[MineOcclude\] episode {0} armed" -f [int]$manifest.layouts[0].episode_id) 'first Attempt 02 episode armed'
    Assert-ERefitAttempt02Condition ($controlEvents[$controlEvents.Count - 1].Index -lt $firstArmed.Index) 'Attempt 02 controls were not completed before the first episode'
    $sessionBaseSeconds = Get-Attempt02LineSeconds $firstArmed.Line 'first armed event'
    $preflightSeconds = Get-Attempt02LineSeconds $preflightEvent.Line 'preflight F2 event'
    $preflightToFirstArm = Get-Attempt02OffsetSeconds $preflightSeconds $sessionBaseSeconds
    Assert-ERefitAttempt02Condition ($preflightToFirstArm -gt 0 -and $preflightToFirstArm -lt 43200) 'Disposable preflight F2 was not before the first Attempt 02 episode'

    $previousAbortIndex = -1
    $seenRawScreenshots = @{}
    $validatedLayouts = [System.Collections.Generic.List[object]]::new()
    $layoutScreenshotInputs = [System.Collections.Generic.List[object]]::new()
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

        $chronology = Get-Attempt02LayoutChronology -Lines $serverLines -LayoutId $layoutId -EpisodeId $episodeId -Seed $seed -ReceiptId $receiptId -PreviousAbortIndex $previousAbortIndex -ServerStopIndex $serverStop.Index
        $armed = $chronology.Armed
        $targetStatus = $chronology.TargetStatus
        $receiptEvent = $chronology.Receipt
        $abort = $chronology.Abort
        $previousAbortIndex = $abort.LastIndex

        $armedSeconds = $armed.TimestampSeconds
        $statusOffsetFromArmed = $chronology.ArmToTargetSeconds
        $confirmationOffset = Get-Attempt02OffsetSeconds $sessionBaseSeconds $receiptEvent.TimestampSeconds
        $abortOffset = Get-Attempt02OffsetSeconds $sessionBaseSeconds $abort.TimestampSeconds
        $screenshotEvents = [System.Collections.Generic.List[object]]::new()
        foreach ($line in $clientLines) {
            if ($line -match 'Saved screenshot as ([^\\/\s]+\.png)') {
                $eventOffset = Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $line 'screenshot event')
                if ($eventOffset -gt $confirmationOffset -and $eventOffset -lt $abortOffset) {
                    [void]$screenshotEvents.Add([pscustomobject]@{ Offset = $eventOffset; FileName = $Matches[1]; Line = $line })
                }
            }
        }
        Assert-ERefitAttempt02Condition ($screenshotEvents.Count -eq 1) "$layoutId requires exactly one in-window F2 screenshot after receipt confirmation and before abort"
        Assert-ERefitAttempt02Condition ($screenshotEvents[0].FileName -cne $preflightFileName) "$layoutId attempts to count the disposable preflight screenshot"
        $rawScreenshot = Join-Path (Join-Path $clientRoot 'screenshots') $screenshotEvents[0].FileName
        Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $rawScreenshot -PathType Leaf) "$layoutId logged screenshot is absent: $rawScreenshot"
        Assert-ERefitAttempt02Condition (-not $seenRawScreenshots.ContainsKey($rawScreenshot)) "$layoutId reused a raw screenshot"
        $seenRawScreenshots[$rawScreenshot] = $true
        [void]$layoutScreenshotInputs.Add([pscustomobject]@{ layout_id = $layoutId; path = $rawScreenshot })

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

        [void]$validatedLayouts.Add([pscustomobject]@{
            Preparation = $layout
            ReceiptPath = $receiptPath
            RawScreenshotPath = $rawScreenshot
            CanonicalScreenshotPath = [string]$layout.runtime_paths.canonical_screenshot
            ArmedOffsetSeconds = Get-Attempt02OffsetSeconds $sessionBaseSeconds $armedSeconds
            TargetStatusOffsetSeconds = Get-Attempt02OffsetSeconds $sessionBaseSeconds $targetStatus.TimestampSeconds
            ReceiptConfirmationOffsetSeconds = $confirmationOffset
            ScreenshotOffsetSeconds = $screenshotEvents[0].Offset
            AbortOffsetSeconds = $abortOffset
        })
    }

    $validatedScreenshotIdentities = @(Assert-ERefitAttempt02LayoutScreenshotSet -Layouts ([object[]]$layoutScreenshotInputs.ToArray()) -PreflightEvidencePath $preflightEvidencePath -PreflightSourcePath ([string]$preflight.source_screenshot.path))
    Assert-ERefitAttempt02Condition ($validatedLayouts.Count -eq 6 -and $seenRawScreenshots.Count -eq 6 -and $validatedScreenshotIdentities.Count -eq 6) 'All six distinct 1920x1046 Attempt 02 screenshots were not validated'
    Assert-ERefitAttempt02Condition ($accountEvent.Index -lt $fovEvent.Index -and $fovEvent.Index -lt $connectEvent.Index -and $connectEvent.Index -lt $preflightEvent.Index -and $preflightEvent.Index -lt $clientStop.Index) 'Client account/FOV/connection/preflight/stop order failed'
    $lastAbortOffset = $validatedLayouts[$validatedLayouts.Count - 1].AbortOffsetSeconds
    Assert-ERefitAttempt02Condition ((Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $serverStop.Line 'server stop')) -gt $lastAbortOffset) 'Server did not stop after the sixth warmup abort'
    Assert-ERefitAttempt02Condition ((Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $clientStop.Line 'client stop')) -gt $lastAbortOffset) 'Client did not stop after the sixth warmup abort'
    $inWindowScreenshotEvents = [System.Collections.Generic.List[string]]::new()
    foreach ($line in $clientLines) {
        if ($line -match 'Saved screenshot as ([^\\/\s]+\.png)') {
            $eventOffset = Get-Attempt02OffsetSeconds $sessionBaseSeconds (Get-Attempt02LineSeconds $line 'session screenshot event')
            if ($eventOffset -gt 0 -and $eventOffset -lt $lastAbortOffset) { [void]$inWindowScreenshotEvents.Add([string]$line) }
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
    $screenshotRows = [System.Collections.Generic.List[object]]::new()
    $receiptRows = [System.Collections.Generic.List[object]]::new()
    $layoutEvidence = [System.Collections.Generic.List[object]]::new()
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
        [void]$screenshotRows.Add([ordered]@{
            layout_id = $layoutId
            episode_id = [int]$validated.Preparation.episode_id
            raw_same_session_screenshot = $raw
            canonical_screenshot = $canonical
            width_pixels = 1920
            height_pixels = 1046
            receipt_confirmation_offset_seconds = $validated.ReceiptConfirmationOffsetSeconds
            screenshot_offset_seconds = $validated.ScreenshotOffsetSeconds
        })
        [void]$receiptRows.Add([ordered]@{
            layout_id = $layoutId
            episode_id = [int]$validated.Preparation.episode_id
            geometry_receipt = $receiptIdentity
            target_valid = $true
            literal_v0_4_geometry_valid = $true
            ready_warmup_observation = $true
        })
        [void]$layoutEvidence.Add([ordered]@{
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
        })
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
        screenshots = [object[]]$screenshotRows.ToArray()
    }
    $receiptInventory = [ordered]@{
        schema_version = 'person-c-e-refit-calibration-attempt-02-geometry-receipt-inventory-v0.1'
        status = 'PASS'
        receipt_count = 6
        accepted_geometry_version = $geometryVersion
        accepted_geometry_sha256 = $geometrySha256
        receipts = [object[]]$receiptRows.ToArray()
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
            immutable_log_archives = [object[]]$attempt01ImmutableLogArchives.ToArray()
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
        layouts = [object[]]$layoutEvidence.ToArray()
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
