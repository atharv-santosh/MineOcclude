[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A',
    [string]$ClientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client',
    [string]$ServerRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server',
    [string]$BaselineInventoryPath = '',
    [string]$EvidenceDir = '',
    [string]$ExpectedOptionsSha256 = '13a43adde78280041f7adc29367b0a61ced6a9549f2430d9083a88665a0d9895'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$attemptName = 'e_refit_calibration_v0_4_attempt_02'
$modulePath = Join-Path $RepoRoot 'scripts\person_c\ERefitCalibrationAttempt02Authority.psm1'
if ($BaselineInventoryPath -eq '') {
    $BaselineInventoryPath = Join-Path $RepoRoot 'docs\status\person_c_to_person_e_calibration_images_v0_4_attempt_02_v0_1\preflight_screenshot_baseline.json'
}
if ($EvidenceDir -eq '') {
    $EvidenceDir = Join-Path $ClientRoot ($attemptName + '_preflight_v0_1')
}
$screenshotsDir = Join-Path $ClientRoot 'screenshots'
$optionsPath = Join-Path $ClientRoot 'options.txt'
$clientLogPath = Join-Path $ClientRoot 'logs\latest.log'
$serverLogPath = Join-Path $ServerRoot 'logs\latest.log'
$evidenceScreenshotPath = Join-Path $EvidenceDir ($attemptName + '_framebuffer_preflight_1920x1046.png')
$receiptPath = Join-Path $EvidenceDir ($attemptName + '_framebuffer_preflight_receipt.json')

Import-Module -Name $modulePath -Force

foreach ($requiredFile in @($BaselineInventoryPath, $optionsPath, $clientLogPath, $serverLogPath)) {
    Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $requiredFile -PathType Leaf) "Required preflight input absent: $requiredFile"
}
Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $screenshotsDir -PathType Container) "Minecraft screenshots directory absent: $screenshotsDir"
Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 $optionsPath) -ceq $ExpectedOptionsSha256) 'Client options identity does not match the prepared Attempt 02 authority'
$optionsText = Get-Content -Raw -LiteralPath $optionsPath
Assert-ERefitAttempt02Condition ($optionsText -match '(?m)^fullscreen:false\r?$') 'Client must remain windowed (fullscreen=false)'
Assert-ERefitAttempt02Condition ($optionsText -match '(?m)^fov:0\.0\r?$') 'Client FOV must be Normal/70.0'
Assert-ERefitAttempt02Condition ($optionsText -match '(?m)^guiScale:2\r?$') 'Client GUI scale must remain 2'
Assert-ERefitAttempt02Condition ($optionsText -match '(?m)^overrideWidth:0\r?$' -and $optionsText -match '(?m)^overrideHeight:0\r?$') 'Client options framebuffer overrides must remain zero'

$serverLines = @(Get-Content -LiteralPath $serverLogPath)
$armedEvents = @($serverLines | Where-Object { $_ -match '\[MineOcclude\] episode \d+ armed' })
Assert-ERefitAttempt02Condition ($armedEvents.Count -eq 0) 'Framebuffer preflight must occur before any MineOcclude episode is armed in this server session'
$recordingEvents = @($serverLines | Where-Object { $_ -match '\[MineOcclude\] episode \d+ recording started' })
Assert-ERefitAttempt02Condition ($recordingEvents.Count -eq 0) 'Framebuffer preflight cannot run in a server session where MineOcclude recording started'

$baseline = Get-Content -Raw -LiteralPath $BaselineInventoryPath | ConvertFrom-Json
Assert-ERefitAttempt02Condition ($baseline.schema_version -eq 'person-c-e-refit-calibration-attempt-02-preflight-screenshot-baseline-v0.1') 'Unknown preflight baseline schema'
Assert-ERefitAttempt02Condition ($baseline.attempt_name -ceq $attemptName) 'Preflight baseline attempt identity mismatch'
$baselineByPath = @{}
foreach ($row in $baseline.screenshots) {
    $fullPath = [string]$row.path
    Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $fullPath -PathType Leaf) "Baseline screenshot was removed: $fullPath"
    $item = Get-Item -LiteralPath $fullPath
    Assert-ERefitAttempt02Condition ($item.Length -eq [int64]$row.size_bytes -and (Get-ERefitAttempt02Sha256 $item.FullName) -ceq [string]$row.sha256) "Baseline screenshot drifted: $fullPath"
    $baselineByPath[$item.FullName] = $true
}
$candidates = @(
    Get-ChildItem -LiteralPath $screenshotsDir -File -Filter '*.png' |
        Where-Object { -not $baselineByPath.ContainsKey($_.FullName) }
)
Assert-ERefitAttempt02Condition ($candidates.Count -eq 1) "Expected exactly one new disposable F2 screenshot after the preparation baseline; observed $($candidates.Count)"
$candidate = $candidates[0]

$clientLines = @(Get-Content -LiteralPath $clientLogPath)
$accountEvents = @($clientLines | Where-Object { $_ -match 'Setting user: ([A-Za-z0-9_]+)' })
Assert-ERefitAttempt02Condition ($accountEvents.Count -eq 1) 'Preflight client log must contain exactly one client account event'
Assert-ERefitAttempt02Condition ($accountEvents[0] -match 'Setting user: ([A-Za-z0-9_]+)') 'Unable to parse preflight client account'
$observedAccount = $Matches[1]
$connectEvents = @($clientLines | Where-Object { $_ -match 'Connecting to 127\.0\.0\.1, 25565' })
Assert-ERefitAttempt02Condition ($connectEvents.Count -eq 1) 'Preflight client log must contain exactly one loopback connection event'
$screenshotEvents = @($clientLines | Where-Object { $_ -match 'Saved screenshot as ([^\\/\s]+\.png)' })
Assert-ERefitAttempt02Condition ($screenshotEvents.Count -eq 1) "Preflight client session must contain exactly one F2 event before calibration; observed $($screenshotEvents.Count)"
Assert-ERefitAttempt02Condition ($screenshotEvents[0] -match 'Saved screenshot as ([^\\/\s]+\.png)') 'Unable to parse preflight screenshot event'
Assert-ERefitAttempt02Condition ($Matches[1] -ceq $candidate.Name) 'The sole new PNG does not match the client log preflight F2 event'

$dimensions = Get-ERefitAttempt02PngDimensions $candidate.FullName
Assert-ERefitAttempt02Condition ($dimensions.Width -eq 1920 -and $dimensions.Height -eq 1046) "Framebuffer preflight failed closed: observed $($dimensions.Width)x$($dimensions.Height), required 1920x1046"
foreach ($path in @($evidenceScreenshotPath, $receiptPath)) {
    Assert-ERefitAttempt02Condition (-not (Test-Path -LiteralPath $path)) "Create-only preflight output already exists: $path"
}
if (-not (Test-Path -LiteralPath $EvidenceDir)) {
    New-Item -ItemType Directory -Path $EvidenceDir | Out-Null
}
Copy-ERefitAttempt02CreateOnly $candidate.FullName $evidenceScreenshotPath
Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 $candidate.FullName) -ceq (Get-ERefitAttempt02Sha256 $evidenceScreenshotPath)) 'Preflight screenshot create-only copy hash mismatch'

$clientLogItem = Get-Item -LiteralPath $clientLogPath
$serverLogItem = Get-Item -LiteralPath $serverLogPath
$receipt = [ordered]@{
    schema_version = 'person-c-e-refit-calibration-attempt-02-framebuffer-preflight-v0.1'
    status = 'PASS'
    attempt_name = $attemptName
    required_framebuffer = [ordered]@{ width_pixels = 1920; height_pixels = 1046 }
    observed_framebuffer = [ordered]@{ width_pixels = [int64]$dimensions.Width; height_pixels = [int64]$dimensions.Height }
    source_screenshot = Get-ERefitAttempt02Identity $candidate.FullName
    external_preflight_evidence = Get-ERefitAttempt02Identity $evidenceScreenshotPath
    client_options = Get-ERefitAttempt02Identity $optionsPath
    observed_account = $observedAccount
    server_session_prefix = [ordered]@{
        path = $serverLogItem.FullName
        size_bytes = [int64]$serverLogItem.Length
        sha256 = Get-ERefitAttempt02Sha256 $serverLogItem.FullName
        creation_time_utc = $serverLogItem.CreationTimeUtc.ToString('o')
    }
    client_session_prefix = [ordered]@{
        path = $clientLogItem.FullName
        size_bytes = [int64]$clientLogItem.Length
        sha256 = Get-ERefitAttempt02Sha256 $clientLogItem.FullName
        creation_time_utc = $clientLogItem.CreationTimeUtc.ToString('o')
    }
    mineocclude_episode_running = $false
    mineocclude_episode_armed_before_preflight = $false
    f2_events_before_calibration = 1
    disposable_preflight_screenshot = $true
    excluded_from_layout_screenshot_count = $true
    runtime_evidence_modified_in_place = $false
    verified_utc = [DateTime]::UtcNow.ToString('o')
}
Write-ERefitAttempt02CreateOnlyJson $receiptPath $receipt

Write-Output 'E_REFIT_CALIBRATION_ATTEMPT_02_PREFLIGHT_BEGIN'
Write-Output 'FRAMEBUFFER_PREFLIGHT_PASS=True'
Write-Output "SOURCE_SCREENSHOT=$($candidate.FullName)"
Write-Output "PREFLIGHT_EVIDENCE=$evidenceScreenshotPath"
Write-Output "PREFLIGHT_RECEIPT=$receiptPath"
Write-Output "FRAMEBUFFER=$($dimensions.Width)x$($dimensions.Height)"
Write-Output "SCREENSHOT_SIZE_BYTES=$($candidate.Length)"
Write-Output "SCREENSHOT_SHA256=$(Get-ERefitAttempt02Sha256 $candidate.FullName)"
Write-Output 'LAYOUT_SCREENSHOT_ELIGIBLE=False'
Write-Output 'E_REFIT_CALIBRATION_ATTEMPT_02_PREFLIGHT_END'
