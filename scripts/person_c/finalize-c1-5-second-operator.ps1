[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$requiredBranch = 'completion/person-c-c1-c6a'
$preparationBaseCommit = 'a4d55394d5fb411b6bf7a2c4b36d527733a445d5'
$serverRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server'
$clientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client'
$receiptPath = Join-Path $serverRoot 'mineocclude_observations\c1_5_second_operator_attempt_01_layout_01.json'
$screenshotPath = Join-Path $clientRoot 'c1_5_evidence\second_operator_attempt_01_layout_01.png'
$attestationPath = Join-Path $serverRoot 'c1_5_evidence\second_operator_attempt_01_attestation.json'
$ingestedPath = Join-Path $serverRoot 'c1_5_evidence\second_operator_attempt_01_ingested.json'
$serverLogPath = Join-Path $serverRoot 'logs\latest.log'
$clientLogPath = Join-Path $clientRoot 'logs\latest.log'
$serverLogArchive = Join-Path $serverRoot 'c1_5_evidence\second_operator_attempt_01_success\server_latest.log'
$clientLogArchive = Join-Path $clientRoot 'c1_5_evidence\second_operator_attempt_01_success\client_latest.log'
$schedulePath = Join-Path $serverRoot 'mineocclude_schedules\episode_11502.jsonl'
$templatePath = Join-Path $RepoRoot 'docs\status\person_c_c1_5_second_operator_v0_1\second_operator_attestation.template.json'
$ingestionPath = Join-Path $RepoRoot 'scripts\person_c\ingest_c1_5_second_operator_runtime.py'
$firstReceipt = Join-Path $serverRoot 'mineocclude_observations\c1_5_first_operator_attempt_04_layout_01.json'
$firstScreenshot = Join-Path $clientRoot 'c1_5_evidence\first_operator_attempt_04_layout_01.png'
$firstAttestationPath = Join-Path $serverRoot 'c1_5_evidence\first_operator_attempt_04_attestation.json'
$firstIngested = Join-Path $serverRoot 'c1_5_evidence\first_operator_attempt_04_ingested.json'
$firstServerLogArchive = Join-Path $serverRoot 'c1_5_evidence\attempt_04_success_preserved\server_latest.log'
$firstClientLogArchive = Join-Path $clientRoot 'c1_5_evidence\attempt_04_success_preserved\client_latest.log'

function Require([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Find-LogEvent([string[]]$Lines, [string]$Pattern, [string]$Label) {
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index] -match $Pattern) {
            return [pscustomobject]@{ Index = $index; Line = $Lines[$index] }
        }
    }
    throw "Required log event absent: $Label"
}

function Get-LineSeconds([string]$Line, [string]$Label) {
    Require ($Line -match '^\[(\d{2}):(\d{2}):(\d{2})\]') "$Label has no HH:MM:SS timestamp"
    return ([int]$Matches[1] * 3600) + ([int]$Matches[2] * 60) + [int]$Matches[3]
}

function Get-OffsetSeconds([int]$BaseSeconds, [int]$EventSeconds) {
    return ($EventSeconds - $BaseSeconds + 86400) % 86400
}

function Copy-CreateOnly([string]$Source, [string]$Destination) {
    $sourceStream = [System.IO.File]::OpenRead($Source)
    try {
        $destinationStream = [System.IO.File]::Open(
            $Destination,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        try { $sourceStream.CopyTo($destinationStream) }
        finally { $destinationStream.Dispose() }
    }
    finally { $sourceStream.Dispose() }
}

function Write-CreateOnlyUtf8([string]$Path, [string]$Text) {
    $encoding = [System.Text.UTF8Encoding]::new($false)
    $bytes = $encoding.GetBytes($Text)
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    try { $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
}

Push-Location -LiteralPath $RepoRoot
try {
    $branch = (& git branch --show-current).Trim()
    Require ($LASTEXITCODE -eq 0) 'Unable to determine Git branch'
    Require ($branch -eq $requiredBranch) "Wrong branch: $branch"
    $worktreeStatus = @(& git status --porcelain=v1)
    Require ($LASTEXITCODE -eq 0) 'Unable to determine Git worktree status'
    Require ($worktreeStatus.Count -eq 0) 'Repository worktree must be clean before finalization'
    $preparationCommit = (& git log -1 --format=%H -- scripts/person_c/finalize-c1-5-second-operator.ps1).Trim()
    Require ($LASTEXITCODE -eq 0) 'Unable to resolve the second-operator preparation commit'
    Require ($preparationCommit -match '^[0-9a-f]{40}$') 'Second-operator package is not committed'
    & git merge-base --is-ancestor $preparationBaseCommit $preparationCommit
    Require ($LASTEXITCODE -eq 0) 'Second-operator preparation does not descend from the required base'
    & git merge-base --is-ancestor $preparationCommit HEAD
    Require ($LASTEXITCODE -eq 0) 'Expected second-operator preparation commit is not an ancestor of HEAD'

    $firstExpected = @{
        $firstReceipt = 'fcf58263571210aeb4c926cddccbebc48ac9324b903143ceae2c15c09868878c'
        $firstScreenshot = '1df5bea1be63e0f900f74871b40eafa480015f5173b70253f9a8175d5d224057'
        $firstAttestationPath = 'bd4b0f5070a6d2b96b03e81dbe8e90ac9b7e51e31fbebb9e556cea9532605edd'
        $firstIngested = '55efd6c247d873f0bda59f48a66817952fbb22e3566c4e416a63e4b42461f5b9'
        $firstServerLogArchive = 'f2e533a79b12496ae353346b9e65d04cedd541f364abdeb65b8bcc4727ca0158'
        $firstClientLogArchive = 'e2ea65dadeff45e91ef9ac68e90688994b68d7043e6eee2eb8de7517c9bcecc5'
    }
    foreach ($entry in $firstExpected.GetEnumerator()) {
        Require (Test-Path -LiteralPath $entry.Key -PathType Leaf) "First-operator evidence absent: $($entry.Key)"
        Require ((Get-Sha256 $entry.Key) -eq $entry.Value) "First-operator evidence hash drift: $($entry.Key)"
    }
    $firstAttestation = Get-Content -Raw -LiteralPath $firstAttestationPath | ConvertFrom-Json
    Require ($firstAttestation.operator_id -eq 'lollo') 'First-operator identity drift'

    foreach ($requiredFile in @($receiptPath, $serverLogPath, $clientLogPath, $schedulePath, $templatePath, $ingestionPath)) {
        Require (Test-Path -LiteralPath $requiredFile -PathType Leaf) "Required second-operator input absent: $requiredFile"
    }
    Require ((Get-Sha256 $schedulePath) -eq 'b399dd08b7e2dcdecc136400cb47afa680995edf04239f3a79e36bcc688655c7') 'Reserved second-operator schedule hash mismatch'
    foreach ($createOnlyPath in @($screenshotPath, $attestationPath, $ingestedPath, $serverLogArchive, $clientLogArchive)) {
        Require (-not (Test-Path -LiteralPath $createOnlyPath)) "Create-only second-operator path already exists: $createOnlyPath"
    }

    $receipt = Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json
    Require ($receipt.receipt_id -eq 'c1_5_second_operator_attempt_01_layout_01') 'Geometry receipt ID mismatch'
    Require ($receipt.layout_id -eq 'layout_01' -and $receipt.episode_id -eq 11502) 'Geometry receipt layout/episode mismatch'
    Require ($receipt.running -eq $true -and $receipt.capturing -eq $false -and $receipt.lifecycle_state -eq 'READY') 'Geometry receipt was not written during READY warmup'
    Require ($receipt.warmup_ticks_remaining -gt 0) 'Geometry receipt has no remaining warmup ticks'
    Require ($receipt.target.valid -eq $true -and $receipt.target.required -eq $true) 'Geometry receipt target valid/required fields failed'
    Require ($receipt.target.tagged_target_count -eq 1 -and $receipt.target.problems.Count -eq 0) 'Geometry receipt target count/problems failed'

    $serverLines = @(Get-Content -LiteralPath $serverLogPath)
    $clientLines = @(Get-Content -LiteralPath $clientLogPath)
    $warmup = Find-LogEvent $serverLines 'Warmup delay set to 12000 ticks \(600\.0s\)' 'warmup 12000 configuration'
    $armed = Find-LogEvent $serverLines 'episode 11502 armed \(layout=layout_01, 12000 warmup \+ 20 record ticks' 'episode armed'
    $status = Find-LogEvent $serverLines 'target status: valid=true required=true count=1.*episode=11502.*lifecycle=READY.*problems=NONE' 'valid targetstatus'
    $observed = Find-LogEvent $serverLines 'wrote read-only geometry receipt .*c1_5_second_operator_attempt_01_layout_01\.json' 'observation receipt written'
    $aborted = Find-LogEvent $serverLines 'episode 11502 aborted during warmup' 'episode aborted during warmup'
    $serverStopped = Find-LogEvent $serverLines 'Stopping server' 'clean server stop'
    $clientStopped = Find-LogEvent $clientLines 'Stopping!' 'clean client stop'
    Require ($warmup.Index -lt $armed.Index -and $armed.Index -lt $status.Index -and $status.Index -lt $observed.Index -and $observed.Index -lt $aborted.Index -and $aborted.Index -lt $serverStopped.Index) 'Server chronology failed'
    Require (-not ($serverLines -match 'episode 11502 recording started')) 'Second-operator episode entered recording before abort'
    Require (-not ($serverLines -match '(?i)target retention failure')) 'Second-operator target-retention failure present'
    $armedSeconds = Get-LineSeconds $armed.Line 'armed event'
    $statusOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $status.Line 'targetstatus event')
    $observedOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $observed.Line 'receipt event')
    $abortOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $aborted.Line 'abort event')
    $serverStopOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $serverStopped.Line 'server stop event')
    $clientStopOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $clientStopped.Line 'client stop event')
    Require ($statusOffset -ge 10) 'targetstatus occurred less than ten seconds after arming'
    $screenshotCandidates = @()
    foreach ($line in $clientLines) {
        if ($line -match 'Saved screenshot as ([^\\/\s]+\.png)') {
            $screenshotFileName = $Matches[1]
            $offset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $line 'screenshot event')
            if ($offset -gt $observedOffset -and $offset -lt $abortOffset) {
                $screenshotCandidates += [pscustomobject]@{ Offset = $offset; FileName = $screenshotFileName }
            }
        }
    }
    Require ($screenshotCandidates.Count -eq 1) 'Exactly one F2 screenshot must occur after receipt and before abort'
    $screenshotEvent = $screenshotCandidates[0]
    Require (10 -le $statusOffset -and $statusOffset -lt $observedOffset -and $observedOffset -lt $screenshotEvent.Offset -and $screenshotEvent.Offset -lt $abortOffset -and $abortOffset -lt $serverStopOffset) 'Cross-log chronology failed'
    Require ($clientStopOffset -gt $abortOffset) 'Client did not stop after warmup abort'
    $sourceScreenshot = Join-Path (Join-Path $clientRoot 'screenshots') $screenshotEvent.FileName
    Require (Test-Path -LiteralPath $sourceScreenshot -PathType Leaf) "Logged F2 screenshot absent: $sourceScreenshot"
    $accountEvent = Find-LogEvent $clientLines 'Setting user: ([A-Za-z0-9_]+)' 'authenticated account'
    Require ($accountEvent.Line -match 'Setting user: ([A-Za-z0-9_]+)') 'Unable to parse authenticated account'
    $observedAccount = $Matches[1]
    $operatorId = $observedAccount
    Require ($operatorId -ine 'lollo') 'operator_id=lollo is forbidden for the independent second operator'
    Require ($operatorId -ine [string]$firstAttestation.operator_id) 'Second operator identity matches first operator'
    Require ($observedAccount -ine [string]$firstAttestation.observed_account_name) 'Second authenticated account matches first operator'

    $confirmation = Read-Host 'Type YES once to attest that you are a different human and did not use the first operator memory, screenshot, receipt, or result'
    Require ($confirmation -ceq 'YES') 'Operator did not provide the required exact YES confirmation'

    foreach ($directory in @((Split-Path -Parent $screenshotPath), (Split-Path -Parent $serverLogArchive), (Split-Path -Parent $clientLogArchive))) {
        if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory | Out-Null }
    }
    Copy-CreateOnly $serverLogPath $serverLogArchive
    Copy-CreateOnly $clientLogPath $clientLogArchive
    Copy-CreateOnly $sourceScreenshot $screenshotPath
    Require ((Get-Sha256 $serverLogPath) -eq (Get-Sha256 $serverLogArchive)) 'Server-log archive hash mismatch'
    Require ((Get-Sha256 $clientLogPath) -eq (Get-Sha256 $clientLogArchive)) 'Client-log archive hash mismatch'
    Require ((Get-Sha256 $sourceScreenshot) -eq (Get-Sha256 $screenshotPath)) 'Screenshot copy hash mismatch'

    $attestation = Get-Content -Raw -LiteralPath $templatePath | ConvertFrom-Json
    $attestation.template = $false
    $attestation.operator_id = $operatorId
    $attestation.independent_from_first_operator = $true
    $attestation.utc_start = (Get-Item -LiteralPath $serverLogPath).CreationTimeUtc.ToString('o')
    $attestation.utc_end = (Get-Item -LiteralPath $serverLogPath).LastWriteTimeUtc.ToString('o')
    $attestation.preparation_commit = $preparationCommit
    $attestation.observed_account_name = $observedAccount
    $attestation.fresh_runtime_session = $true
    $attestation.all_runbook_steps_performed_without_memory_or_prior_artifact_reuse = $true
    $attestation.targetstatus_passed_after_ten_seconds = $true
    $attestation.observegeometry_completed_during_warmup_before_recording = $true
    $attestation.receipt_write_confirmed_before_f2 = $true
    $attestation.f2_pressed_immediately_after_receipt_confirmation = $true
    $attestation.mineocclude_stop_issued_immediately_after_f2 = $true
    $attestation.screenshot_from_same_session = $true
    $attestation.server_stopped_cleanly = $true
    $attestation.operator_identity_differs_from_first_operator = $true
    $attestation.authenticated_account_differs_from_first_operator = $true
    $attestation.did_not_use_first_operator_memory_screenshot_receipt_or_prior_result_to_reconstruct_scene = $true
    $attestation.notes = 'Independent second-operator run; automated checks plus one YES populated all timing and independence attestations.'
    Write-CreateOnlyUtf8 $attestationPath (($attestation | ConvertTo-Json -Depth 20) + "`n")

    $python = (Get-Command python -ErrorAction Stop).Source
    $commonArguments = @(
        $ingestionPath,
        '--geometry-receipt', $receiptPath,
        '--screenshot', $screenshotPath,
        '--attestation', $attestationPath,
        '--output', $ingestedPath
    )
    $validationOutput = @(& $python @commonArguments --validate-only 2>&1)
    Require ($LASTEXITCODE -eq 0) ("Second-operator validation failed: " + ($validationOutput -join ' '))
    $ingestionOutput = @(& $python @commonArguments 2>&1)
    Require ($LASTEXITCODE -eq 0) ("Second-operator ingestion failed: " + ($ingestionOutput -join ' '))
    Require (Test-Path -LiteralPath $ingestedPath -PathType Leaf) 'Second-operator ingestion output was not created'

    Write-Output 'C1_5_SECOND_OPERATOR_FINALIZE_BEGIN'
    Write-Output "PREPARATION_COMMIT=$preparationCommit"
    Write-Output "OPERATOR_ID=$operatorId"
    Write-Output 'INDEPENDENT_FROM_FIRST_OPERATOR=True'
    Write-Output 'CHRONOLOGY_VALID=True'
    Write-Output 'TARGET_RECEIPT_VALID=True'
    Write-Output "RAW_SCREENSHOT=$sourceScreenshot"
    Write-Output "CANONICAL_SCREENSHOT_SHA256=$(Get-Sha256 $screenshotPath)"
    Write-Output "ATTESTATION_SHA256=$(Get-Sha256 $attestationPath)"
    Write-Output "INGESTED_OUTPUT=$ingestedPath"
    Write-Output "INGESTED_SHA256=$(Get-Sha256 $ingestedPath)"
    Write-Output 'C1_5_COMPLETE=True'
    Write-Output 'C1_5_SECOND_OPERATOR_FINALIZE_END'
}
finally {
    Pop-Location
}
