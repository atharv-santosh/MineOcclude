[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A',
    [string]$ClientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client',
    [string]$ServerRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server',
    [string]$BaselineInventoryPath = '',
    [string]$ExpectedImageSha256 = 'ec3b4d101ba1ef5e7145c0c27ae92c9ff32b3d742b4116be24429206a1e79ca4',
    [int64]$ExpectedImageSizeBytes = 847670,
    [string]$ExpectedOptionsSha256 = '13a43adde78280041f7adc29367b0a61ced6a9549f2430d9083a88665a0d9895'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$requiredBranch = 'completion/person-c-c1-c6a'
$attemptName = 'e_refit_calibration_v0_4_attempt_02'
$preparationSourceCommit = '1ec3b693e4fbbdd893908a10e1fc409644700e65'
$liveLogHashRepairCommit = 'd73d35424b599366d151c02cc3bafbd94fb3b237'
$expectedProductionImageSha256 = 'ec3b4d101ba1ef5e7145c0c27ae92c9ff32b3d742b4116be24429206a1e79ca4'
$expectedProductionImageSizeBytes = [int64]847670
$productionClientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client'
$productionServerRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server'
$packageRelativePath = 'docs/status/person_c_to_person_e_calibration_images_v0_4_attempt_02_v0_1'
$manifestRelativePath = "$packageRelativePath/session_manifest.json"
$preparedBaselineRelativePath = "$packageRelativePath/preflight_screenshot_baseline.json"
$preflightScriptRelativePath = 'scripts/person_c/verify-e-refit-calibration-attempt-02-framebuffer.ps1'
$authorityModuleRelativePath = 'scripts/person_c/ERefitCalibrationAttempt02Authority.psm1'
$manifestPath = Join-Path $RepoRoot ($manifestRelativePath -replace '/', '\')
$preparedBaselinePath = Join-Path $RepoRoot ($preparedBaselineRelativePath -replace '/', '\')
$preflightScriptPath = Join-Path $RepoRoot ($preflightScriptRelativePath -replace '/', '\')
$authorityModulePath = Join-Path $RepoRoot ($authorityModuleRelativePath -replace '/', '\')
if ($BaselineInventoryPath -eq '') {
    $BaselineInventoryPath = $preparedBaselinePath
}
$evidenceDir = Join-Path $ClientRoot ($attemptName + '_preflight_v0_1')
$evidenceScreenshotPath = Join-Path $evidenceDir ($attemptName + '_framebuffer_preflight_1920x1046.png')
$receiptPath = Join-Path $evidenceDir ($attemptName + '_framebuffer_preflight_receipt.json')
$screenshotsDir = Join-Path $ClientRoot 'screenshots'
$optionsPath = Join-Path $ClientRoot 'options.txt'
$clientLogPath = Join-Path $ClientRoot 'logs\latest.log'
$serverLogPath = Join-Path $ServerRoot 'logs\latest.log'

Import-Module -Name $authorityModulePath -Force

function Get-RecoveryNormalizedPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Get-RecoveryGitScalar {
    param([Parameter(Mandatory = $true)][string[]]$Arguments, [Parameter(Mandatory = $true)][string]$Label)
    $lines = @(& git @Arguments)
    Assert-ERefitAttempt02Condition ($LASTEXITCODE -eq 0) "$Label failed"
    $value = ($lines -join "`n").Trim()
    Assert-ERefitAttempt02Condition ($value -ne '') "$Label returned no value"
    return $value
}

function Assert-RecoveryGitAncestor {
    param(
        [Parameter(Mandatory = $true)][string]$Ancestor,
        [Parameter(Mandatory = $true)][string]$Descendant,
        [Parameter(Mandatory = $true)][string]$Label
    )
    & git merge-base --is-ancestor $Ancestor $Descendant
    Assert-ERefitAttempt02Condition ($LASTEXITCODE -eq 0) $Label
}

$usingProductionClientRoot = (Get-RecoveryNormalizedPath $ClientRoot) -ceq (Get-RecoveryNormalizedPath $productionClientRoot)
$usingProductionServerRoot = (Get-RecoveryNormalizedPath $ServerRoot) -ceq (Get-RecoveryNormalizedPath $productionServerRoot)
Assert-ERefitAttempt02Condition ($usingProductionClientRoot -eq $usingProductionServerRoot) 'Mixing production and non-production recovery roots is forbidden'
$productionMode = $usingProductionClientRoot -and $usingProductionServerRoot

Push-Location -LiteralPath $RepoRoot
try {
    $branch = Get-RecoveryGitScalar -Arguments @('branch', '--show-current') -Label 'Git branch lookup'
    if ($productionMode) {
        Assert-ERefitAttempt02Condition ($branch -ceq $requiredBranch) "Wrong branch: $branch"
    }
    Assert-RecoveryGitAncestor $preparationSourceCommit $liveLogHashRepairCommit 'Live-log repair does not descend from the Attempt 02 preparation source commit'
    Assert-RecoveryGitAncestor $liveLogHashRepairCommit 'HEAD' 'Live-log repair commit is not an ancestor of HEAD'

    if ($productionMode) {
        $worktreeStatus = @(& git status --porcelain=v1)
        Assert-ERefitAttempt02Condition ($LASTEXITCODE -eq 0 -and $worktreeStatus.Count -eq 0) 'Repository worktree must be clean for production receipt recovery'
        Assert-ERefitAttempt02Condition ($ExpectedImageSha256 -ceq $expectedProductionImageSha256) 'Production canonical-image SHA-256 override is forbidden'
        Assert-ERefitAttempt02Condition ($ExpectedImageSizeBytes -eq $expectedProductionImageSizeBytes) 'Production canonical-image size override is forbidden'
        Assert-ERefitAttempt02Condition ((Get-RecoveryNormalizedPath $BaselineInventoryPath) -ceq (Get-RecoveryNormalizedPath $preparedBaselinePath)) 'Production preflight baseline override is forbidden'
    }

    foreach ($requiredFile in @(
        $manifestPath, $preparedBaselinePath, $preflightScriptPath, $authorityModulePath,
        $BaselineInventoryPath, $evidenceScreenshotPath, $optionsPath, $clientLogPath, $serverLogPath
    )) {
        Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $requiredFile -PathType Leaf) "Required recovery input absent: $requiredFile"
    }
    Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $screenshotsDir -PathType Container) "Minecraft screenshots directory absent: $screenshotsDir"
    Assert-ERefitAttempt02Condition (-not (Test-Path -LiteralPath $receiptPath)) "Create-only preflight receipt already exists: $receiptPath"

    $sourceManifestBlob = Get-RecoveryGitScalar -Arguments @('rev-parse', "$preparationSourceCommit`:$manifestRelativePath") -Label 'Preparation manifest blob lookup'
    $currentManifestBlob = Get-RecoveryGitScalar -Arguments @('hash-object', '--', $manifestPath) -Label 'Current preparation manifest blob lookup'
    Assert-ERefitAttempt02Condition ($currentManifestBlob -ceq $sourceManifestBlob) 'Attempt 02 preparation manifest is not the source-commit manifest'
    $sourceBaselineBlob = Get-RecoveryGitScalar -Arguments @('rev-parse', "$preparationSourceCommit`:$preparedBaselineRelativePath") -Label 'Preparation baseline blob lookup'
    $currentPreparedBaselineBlob = Get-RecoveryGitScalar -Arguments @('hash-object', '--', $preparedBaselinePath) -Label 'Current preparation baseline blob lookup'
    Assert-ERefitAttempt02Condition ($currentPreparedBaselineBlob -ceq $sourceBaselineBlob) 'Attempt 02 prepared preflight baseline is not the source-commit baseline'
    $sourcePreflightBlob = Get-RecoveryGitScalar -Arguments @('rev-parse', "$preparationSourceCommit`:$preflightScriptRelativePath") -Label 'Prepared preflight script blob lookup'
    $sourceAuthorityBlob = Get-RecoveryGitScalar -Arguments @('rev-parse', "$preparationSourceCommit`:$authorityModuleRelativePath") -Label 'Prepared authority module blob lookup'
    $repairPreflightBlob = Get-RecoveryGitScalar -Arguments @('rev-parse', "$liveLogHashRepairCommit`:$preflightScriptRelativePath") -Label 'Repaired preflight script blob lookup'
    $currentPreflightBlob = Get-RecoveryGitScalar -Arguments @('hash-object', '--', $preflightScriptPath) -Label 'Current preflight script blob lookup'
    Assert-ERefitAttempt02Condition ($currentPreflightBlob -ceq $repairPreflightBlob) 'Current preflight script is not the committed live-log repair version'

    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    Assert-ERefitAttempt02Condition ($manifest.schema_version -eq 'person-c-to-person-e-calibration-image-session-v0.4-attempt-02-v0.1') 'Unknown Attempt 02 preparation manifest schema'
    Assert-ERefitAttempt02Condition ($manifest.status -eq 'READY_AFTER_MANDATORY_FRAMEBUFFER_PREFLIGHT' -and $manifest.attempt_name -ceq $attemptName -and $manifest.attempt_number -eq 2) 'Attempt 02 preparation manifest identity mismatch'
    Assert-ERefitAttempt02Condition ([string]$manifest.preflight.script.path -ceq $preflightScriptRelativePath) 'Attempt 02 manifest preflight script path drift'
    Assert-ERefitAttempt02Condition ([string]$manifest.preflight.script.git_blob -ceq $sourcePreflightBlob) 'Attempt 02 manifest does not bind the prepared preflight script blob'
    Assert-ERefitAttempt02Condition ([string]$manifest.authority_module.git_blob -ceq $sourceAuthorityBlob) 'Attempt 02 manifest does not bind the prepared authority module blob'
    Assert-ERefitAttempt02Condition ([string]$manifest.preflight.baseline_inventory -ceq 'preflight_screenshot_baseline.json') 'Attempt 02 manifest preflight baseline path drift'
    $expectedProductionEvidencePath = Join-Path (Join-Path $productionClientRoot ($attemptName + '_preflight_v0_1')) ($attemptName + '_framebuffer_preflight_1920x1046.png')
    $expectedProductionReceiptPath = Join-Path (Join-Path $productionClientRoot ($attemptName + '_preflight_v0_1')) ($attemptName + '_framebuffer_preflight_receipt.json')
    Assert-ERefitAttempt02Condition ((Get-RecoveryNormalizedPath ([string]$manifest.preflight.external_evidence_path)) -ceq (Get-RecoveryNormalizedPath $expectedProductionEvidencePath)) 'Attempt 02 manifest canonical preflight image path drift'
    Assert-ERefitAttempt02Condition ((Get-RecoveryNormalizedPath ([string]$manifest.preflight.receipt_path)) -ceq (Get-RecoveryNormalizedPath $expectedProductionReceiptPath)) 'Attempt 02 manifest preflight receipt path drift'
    Assert-ERefitAttempt02Condition ($manifest.preflight.required_framebuffer.width_pixels -eq 1920 -and $manifest.preflight.required_framebuffer.height_pixels -eq 1046 -and $manifest.preflight.fail_closed -eq $true) 'Attempt 02 manifest framebuffer recovery authority drift'

    $preparedSourceText = (@(& git show "$preparationSourceCommit`:$preflightScriptRelativePath") -join "`n")
    Assert-ERefitAttempt02Condition ($LASTEXITCODE -eq 0) 'Unable to read the prepared preflight script'
    $preparedAuthorityText = (@(& git show "$preparationSourceCommit`:$authorityModuleRelativePath") -join "`n")
    Assert-ERefitAttempt02Condition ($LASTEXITCODE -eq 0) 'Unable to read the prepared authority module'
    $repairedAuthorityText = (@(& git show "$liveLogHashRepairCommit`:$authorityModuleRelativePath") -join "`n")
    Assert-ERefitAttempt02Condition ($LASTEXITCODE -eq 0) 'Unable to read the repaired authority module'
    $dimensionValidationIndex = $preparedSourceText.IndexOf('$dimensions = Get-ERefitAttempt02PngDimensions $candidate.FullName')
    $canonicalCreationIndex = $preparedSourceText.IndexOf('Copy-ERefitAttempt02CreateOnly $candidate.FullName $evidenceScreenshotPath')
    $canonicalValidationIndex = $preparedSourceText.IndexOf('Preflight screenshot create-only copy hash mismatch')
    $lockedServerHashIndex = $preparedSourceText.IndexOf('sha256 = Get-ERefitAttempt02Sha256 $serverLogItem.FullName')
    $receiptEmissionIndex = $preparedSourceText.IndexOf('Write-ERefitAttempt02CreateOnlyJson $receiptPath $receipt')
    Assert-ERefitAttempt02Condition (
        $dimensionValidationIndex -ge 0 -and
        $dimensionValidationIndex -lt $canonicalCreationIndex -and
        $canonicalCreationIndex -lt $canonicalValidationIndex -and
        $canonicalValidationIndex -lt $lockedServerHashIndex -and
        $lockedServerHashIndex -lt $receiptEmissionIndex
    ) 'Prepared preflight source does not prove the canonical-image/post-validation/pre-receipt failure window'
    Assert-ERefitAttempt02Condition ($preparedAuthorityText.Contains('Get-FileHash -LiteralPath $Path -Algorithm SHA256')) 'Prepared authority did not use the locked-file-incompatible hashing path'
    Assert-ERefitAttempt02Condition (
        $repairedAuthorityText.Contains('[System.IO.FileShare]::ReadWrite') -and
        $repairedAuthorityText.Contains('[System.IO.FileShare]::Delete') -and
        $repairedAuthorityText.Contains('[System.IO.FileAccess]::Read')
    ) 'Live-log hashing repair commit does not prove shared-read hashing'

    $canonicalIdentity = Get-ERefitAttempt02Identity $evidenceScreenshotPath
    $canonicalDimensions = Get-ERefitAttempt02PngDimensions $evidenceScreenshotPath
    Assert-ERefitAttempt02Condition ($canonicalIdentity.size_bytes -eq $ExpectedImageSizeBytes) 'Canonical preflight image size mismatch'
    Assert-ERefitAttempt02Condition ($canonicalIdentity.sha256 -ceq $ExpectedImageSha256) 'Canonical preflight image SHA-256 mismatch'
    Assert-ERefitAttempt02Condition ($canonicalDimensions.Width -eq 1920 -and $canonicalDimensions.Height -eq 1046) 'Canonical preflight image dimensions are not 1920x1046'

    $baseline = Get-Content -Raw -LiteralPath $BaselineInventoryPath | ConvertFrom-Json
    Assert-ERefitAttempt02Condition ($baseline.schema_version -eq 'person-c-e-refit-calibration-attempt-02-preflight-screenshot-baseline-v0.1' -and $baseline.attempt_name -ceq $attemptName) 'Preflight screenshot baseline identity mismatch'
    Assert-ERefitAttempt02Condition ($baseline.screenshot_count -eq @($baseline.screenshots).Count) 'Preflight screenshot baseline count drift'
    $baselineByPath = @{}
    foreach ($row in $baseline.screenshots) {
        $baselineIdentity = [ordered]@{ path = [string]$row.path; size_bytes = [int64]$row.size_bytes; sha256 = [string]$row.sha256 }
        Assert-ERefitAttempt02Identity -Identity $baselineIdentity -Label 'Prepared baseline screenshot'
        $baselineByPath[(Get-RecoveryNormalizedPath ([string]$row.path))] = $true
    }

    $canonicalItem = Get-Item -LiteralPath $evidenceScreenshotPath
    $matchingSources = @()
    $preCanonicalCandidates = @()
    foreach ($item in @(Get-ChildItem -LiteralPath $screenshotsDir -File -Filter '*.png')) {
        $normalizedPath = Get-RecoveryNormalizedPath $item.FullName
        if (-not $baselineByPath.ContainsKey($normalizedPath) -and $item.CreationTimeUtc -le $canonicalItem.CreationTimeUtc) {
            $preCanonicalCandidates += $item
        }
        if ((Get-ERefitAttempt02Sha256 $item.FullName) -ceq $ExpectedImageSha256) {
            $matchingSources += $item
        }
    }
    Assert-ERefitAttempt02Condition ($matchingSources.Count -eq 1) "Expected exactly one exact-hash source screenshot; observed $($matchingSources.Count)"
    Assert-ERefitAttempt02Condition ($preCanonicalCandidates.Count -eq 1) "Original single-candidate preflight execution is not provable; observed $($preCanonicalCandidates.Count) pre-canonical non-baseline screenshots"
    $sourceItem = $matchingSources[0]
    Assert-ERefitAttempt02Condition ((Get-RecoveryNormalizedPath $preCanonicalCandidates[0].FullName) -ceq (Get-RecoveryNormalizedPath $sourceItem.FullName)) 'The exact-hash source is not the sole pre-canonical non-baseline screenshot'
    Assert-ERefitAttempt02Condition (-not $baselineByPath.ContainsKey((Get-RecoveryNormalizedPath $sourceItem.FullName))) 'Exact-hash source screenshot was already present in the preparation baseline'
    Assert-ERefitAttempt02Condition ($sourceItem.LastWriteTimeUtc -le $canonicalItem.CreationTimeUtc) 'Canonical preflight image predates its exact-hash source screenshot'
    $sourceIdentity = Get-ERefitAttempt02Identity $sourceItem.FullName
    $sourceDimensions = Get-ERefitAttempt02PngDimensions $sourceItem.FullName
    Assert-ERefitAttempt02Condition ($sourceIdentity.size_bytes -eq $canonicalIdentity.size_bytes -and $sourceIdentity.sha256 -ceq $canonicalIdentity.sha256) 'Canonical preflight image is not an exact create-only copy of its source screenshot'
    Assert-ERefitAttempt02Condition ($sourceDimensions.Width -eq 1920 -and $sourceDimensions.Height -eq 1046) 'Source preflight screenshot dimensions are not 1920x1046'

    Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 $optionsPath) -ceq $ExpectedOptionsSha256) 'Client options identity does not match recovery authority'
    $optionsText = Get-Content -Raw -LiteralPath $optionsPath
    Assert-ERefitAttempt02Condition ($optionsText -match '(?m)^fullscreen:false\r?$' -and $optionsText -match '(?m)^fov:0\.0\r?$' -and $optionsText -match '(?m)^guiScale:2\r?$') 'Client options do not retain the preflight projection authority'
    $clientLines = @(Get-Content -LiteralPath $clientLogPath)
    $accountEvents = @($clientLines | Where-Object { $_ -match 'Setting user: ([A-Za-z0-9_]+)' })
    Assert-ERefitAttempt02Condition ($accountEvents.Count -eq 1 -and $accountEvents[0] -match 'Setting user: ([A-Za-z0-9_]+)') 'Recovery cannot prove the unique preflight client account'
    $observedAccount = $Matches[1]
    $connectEvents = @($clientLines | Where-Object { $_ -match 'Connecting to 127\.0\.0\.1, 25565' })
    Assert-ERefitAttempt02Condition ($connectEvents.Count -eq 1) 'Recovery cannot prove the unique preflight loopback connection'
    $screenshotEvents = @($clientLines | Where-Object { $_ -match 'Saved screenshot as ([^\\/\s]+\.png)' })
    Assert-ERefitAttempt02Condition ($screenshotEvents.Count -ge 1 -and $screenshotEvents[0] -match 'Saved screenshot as ([^\\/\s]+\.png)') 'Recovery cannot prove the preflight F2 event'
    Assert-ERefitAttempt02Condition ($Matches[1] -ceq $sourceItem.Name) 'The first session F2 event is not the exact-hash preflight source screenshot'

    $clientLogIdentity = Get-ERefitAttempt02Identity $clientLogPath
    $serverLogIdentity = Get-ERefitAttempt02Identity $serverLogPath
    $clientLogCreationTimeUtc = (Get-Item -LiteralPath $clientLogPath).CreationTimeUtc.ToString('o')
    $serverLogCreationTimeUtc = (Get-Item -LiteralPath $serverLogPath).CreationTimeUtc.ToString('o')
    $recoveredUtc = [DateTime]::UtcNow.ToString('o')
    $receipt = [ordered]@{
        schema_version = 'person-c-e-refit-calibration-attempt-02-framebuffer-preflight-v0.1'
        status = 'PASS'
        attempt_name = $attemptName
        required_framebuffer = [ordered]@{ width_pixels = 1920; height_pixels = 1046 }
        observed_framebuffer = [ordered]@{ width_pixels = [int64]$canonicalDimensions.Width; height_pixels = [int64]$canonicalDimensions.Height }
        source_screenshot = $sourceIdentity
        external_preflight_evidence = $canonicalIdentity
        client_options = Get-ERefitAttempt02Identity $optionsPath
        observed_account = $observedAccount
        server_session_prefix = [ordered]@{
            path = $serverLogIdentity.path
            size_bytes = [int64]$serverLogIdentity.size_bytes
            sha256 = $serverLogIdentity.sha256
            creation_time_utc = $serverLogCreationTimeUtc
        }
        client_session_prefix = [ordered]@{
            path = $clientLogIdentity.path
            size_bytes = [int64]$clientLogIdentity.size_bytes
            sha256 = $clientLogIdentity.sha256
            creation_time_utc = $clientLogCreationTimeUtc
        }
        mineocclude_episode_running = $false
        mineocclude_episode_armed_before_preflight = $false
        f2_events_before_calibration = 1
        disposable_preflight_screenshot = $true
        excluded_from_layout_screenshot_count = $true
        runtime_evidence_modified_in_place = $false
        verified_utc = $recoveredUtc
        recovery = [ordered]@{
            mode = 'CREATE_ONLY_MISSING_PREFLIGHT_RECEIPT_RECOVERY'
            original_failure = 'LIVE_SERVER_LOG_HASH_LOCK_FAILURE'
            original_failure_stage = 'AFTER_CANONICAL_IMAGE_VALIDATION_BEFORE_RECEIPT_EMISSION'
            preparation_source_commit = $preparationSourceCommit
            live_log_hashing_repair_commit = $liveLogHashRepairCommit
            canonical_image_preexisting = $true
            canonical_image_identity_proven = $true
            source_screenshot_selected_by = 'EXACT_SHA256_FIRST_F2_AND_SOLE_PRE_CANONICAL_NON_BASELINE_IMAGE'
            original_preflight_verified_utc_reconstructed = $false
            verified_utc_semantics = 'RECOVERY_EMISSION_TIME'
            session_prefix_semantics = 'RECOVERY_TIME_COMPLETED_ATTEMPT_02_APPEND_ONLY_SNAPSHOT'
        }
    }
    Write-ERefitAttempt02CreateOnlyJson $receiptPath $receipt

    Write-Output 'E_REFIT_CALIBRATION_ATTEMPT_02_PREFLIGHT_RECEIPT_RECOVERY_BEGIN'
    Write-Output 'RECOVERY_PROVABLE=True'
    Write-Output 'CANONICAL_IMAGE_VALID=True'
    Write-Output "CANONICAL_IMAGE_SHA256=$($canonicalIdentity.sha256)"
    Write-Output 'ORIGINAL_FAILURE_AFTER_IMAGE_VALIDATION=True'
    Write-Output "RECOVERY_RECEIPT=$receiptPath"
    Write-Output 'E_REFIT_CALIBRATION_ATTEMPT_02_PREFLIGHT_RECEIPT_RECOVERY_END'
}
finally {
    Pop-Location
}
