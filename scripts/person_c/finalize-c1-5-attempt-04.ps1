[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$requiredBranch = 'completion/person-c-c1-c6a'
$preparationBaseCommit = 'a2c1544a528ed0b96bea6d1213f1d79ceb508dc0'
$serverRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server'
$clientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client'
$receiptPath = Join-Path $serverRoot 'mineocclude_observations\c1_5_first_operator_attempt_04_layout_01.json'
$screenshotPath = Join-Path $clientRoot 'c1_5_evidence\first_operator_attempt_04_layout_01.png'
$attestationPath = Join-Path $serverRoot 'c1_5_evidence\first_operator_attempt_04_attestation.json'
$ingestedPath = Join-Path $serverRoot 'c1_5_evidence\first_operator_attempt_04_ingested.json'
$serverLogPath = Join-Path $serverRoot 'logs\latest.log'
$clientLogPath = Join-Path $clientRoot 'logs\latest.log'
$templatePath = Join-Path $RepoRoot 'docs\status\person_c_c1_5_attempt_04_v0_1\first_operator_attempt_04_attestation.template.json'
$ingestionPath = Join-Path $RepoRoot 'scripts\person_c\ingest_c1_5_attempt_04_runtime.py'

function Require([bool]$Condition, [string]$Message) {
    if (-not $Condition) {
        throw $Message
    }
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

function Write-CreateOnlyUtf8([string]$Path, [string]$Text) {
    $encoding = [System.Text.UTF8Encoding]::new($false)
    $bytes = $encoding.GetBytes($Text)
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    try {
        $stream.Write($bytes, 0, $bytes.Length)
    }
    finally {
        $stream.Dispose()
    }
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
        try {
            $sourceStream.CopyTo($destinationStream)
        }
        finally {
            $destinationStream.Dispose()
        }
    }
    finally {
        $sourceStream.Dispose()
    }
}

Push-Location -LiteralPath $RepoRoot
try {
    $branch = (& git branch --show-current).Trim()
    Require ($LASTEXITCODE -eq 0) 'Unable to determine Git branch'
    Require ($branch -eq $requiredBranch) "Wrong branch: $branch"
    $worktreeStatus = @(& git status --porcelain=v1)
    Require ($LASTEXITCODE -eq 0) 'Unable to determine Git worktree status'
    Require ($worktreeStatus.Count -eq 0) 'Repository worktree must be clean before finalization'

    $preparationCommit = (& git log -1 --format=%H -- scripts/person_c/finalize-c1-5-attempt-04.ps1).Trim()
    Require ($LASTEXITCODE -eq 0) 'Unable to resolve the attempt-04 preparation commit'
    Require ($preparationCommit -match '^[0-9a-f]{40}$') 'Attempt-04 preparation commit is not committed'
    & git merge-base --is-ancestor $preparationBaseCommit $preparationCommit
    Require ($LASTEXITCODE -eq 0) 'Preparation commit does not descend from the required base commit'
    & git merge-base --is-ancestor $preparationCommit HEAD
    Require ($LASTEXITCODE -eq 0) 'Expected attempt-04 preparation commit is not an ancestor of HEAD'

    foreach ($requiredFile in @($receiptPath, $serverLogPath, $clientLogPath, $templatePath, $ingestionPath)) {
        Require (Test-Path -LiteralPath $requiredFile -PathType Leaf) "Required finalization input absent: $requiredFile"
    }
    foreach ($createOnlyPath in @($screenshotPath, $attestationPath, $ingestedPath)) {
        Require (-not (Test-Path -LiteralPath $createOnlyPath)) "Create-only attempt-04 path already exists: $createOnlyPath"
    }

    $receipt = Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json
    Require ($receipt.receipt_id -eq 'c1_5_first_operator_attempt_04_layout_01') 'Geometry receipt ID mismatch'
    Require ($receipt.layout_id -eq 'layout_01' -and $receipt.episode_id -eq 11505) 'Geometry receipt layout/episode mismatch'
    Require ($receipt.running -eq $true -and $receipt.capturing -eq $false -and $receipt.lifecycle_state -eq 'READY') 'Geometry receipt was not written during READY warmup'
    Require ($receipt.warmup_ticks_remaining -gt 0) 'Geometry receipt has no remaining warmup ticks'
    Require ($receipt.target.valid -eq $true) 'Geometry receipt target.valid is not true'
    Require ($receipt.target.required -eq $true) 'Geometry receipt target.required is not true'
    Require ($receipt.target.tagged_target_count -eq 1) 'Geometry receipt tagged_target_count is not one'
    Require ($receipt.target.problems.Count -eq 0) 'Geometry receipt target problems are not empty'

    $serverLines = @(Get-Content -LiteralPath $serverLogPath)
    $clientLines = @(Get-Content -LiteralPath $clientLogPath)
    $warmup = Find-LogEvent $serverLines 'Warmup delay set to 12000 ticks \(600\.0s\)' 'warmup 12000 configuration'
    $armed = Find-LogEvent $serverLines 'episode 11505 armed \(layout=layout_01, 12000 warmup \+ 20 record ticks' 'episode armed'
    $status = Find-LogEvent $serverLines 'target status: valid=true required=true count=1.*episode=11505.*lifecycle=READY.*problems=NONE' 'valid targetstatus'
    $observed = Find-LogEvent $serverLines 'wrote read-only geometry receipt .*c1_5_first_operator_attempt_04_layout_01\.json' 'observation receipt written'
    $aborted = Find-LogEvent $serverLines 'episode 11505 aborted during warmup' 'episode aborted during warmup'
    $serverStopped = Find-LogEvent $serverLines 'Stopping server' 'clean server stop'
    $clientStopped = Find-LogEvent $clientLines 'Stopping!' 'clean client stop'
    Require ($warmup.Index -lt $armed.Index -and $armed.Index -lt $status.Index -and $status.Index -lt $observed.Index -and $observed.Index -lt $aborted.Index -and $aborted.Index -lt $serverStopped.Index) 'Server chronology is not warmup < armed < status < receipt < abort < shutdown'
    Require (-not ($serverLines -match 'episode 11505 recording started')) 'Attempt 04 entered recording before abort'
    Require (-not ($serverLines -match '(?i)target retention failure')) 'Attempt 04 contains a target-retention failure'

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
                $screenshotCandidates += [pscustomobject]@{ Line = $line; Offset = $offset; FileName = $screenshotFileName }
            }
        }
    }
    Require ($screenshotCandidates.Count -eq 1) 'Exactly one F2 screenshot must occur after receipt confirmation and before warmup abort'
    $screenshotEvent = $screenshotCandidates[0]
    Require (10 -le $statusOffset -and $statusOffset -lt $observedOffset -and $observedOffset -lt $screenshotEvent.Offset -and $screenshotEvent.Offset -lt $abortOffset -and $abortOffset -lt $serverStopOffset) 'Cross-log chronology is not armed < targetstatus >=10s < receipt < F2 < warmup abort < server stop'
    Require ($clientStopOffset -gt $abortOffset) 'Client did not stop after the warmup abort'

    $sourceScreenshot = Join-Path (Join-Path $clientRoot 'screenshots') $screenshotEvent.FileName
    Require (Test-Path -LiteralPath $sourceScreenshot -PathType Leaf) "Logged F2 screenshot is absent: $sourceScreenshot"
    $accountEvent = Find-LogEvent $clientLines 'Setting user: ([A-Za-z0-9_]+)' 'authenticated account'
    Require ($accountEvent.Line -match 'Setting user: ([A-Za-z0-9_]+)') 'Unable to parse authenticated account'
    $observedAccount = $Matches[1]

    $confirmation = Read-Host 'Type YES once to attest that this was a fresh attempt-04 run and every timing/order statement above is accurate'
    Require ($confirmation -ceq 'YES') 'Operator did not provide the required exact YES confirmation'

    $screenshotDirectory = Split-Path -Parent $screenshotPath
    if (-not (Test-Path -LiteralPath $screenshotDirectory)) {
        New-Item -ItemType Directory -Path $screenshotDirectory | Out-Null
    }
    Copy-CreateOnly $sourceScreenshot $screenshotPath
    Require ((Get-Sha256 $sourceScreenshot) -eq (Get-Sha256 $screenshotPath)) 'Canonical screenshot copy hash mismatch'

    $attestation = Get-Content -Raw -LiteralPath $templatePath | ConvertFrom-Json
    $attestation.template = $false
    $attestation.operator_id = $env:USERNAME
    $attestation.independent_from_first_operator = $false
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
    $attestation.notes = 'Fresh first-operator attempt 04; one YES confirmation populated all timing attestations after automated log and receipt validation.'
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
    Require ($LASTEXITCODE -eq 0) ("Attempt-04 attestation/evidence validation failed: " + ($validationOutput -join ' '))
    $ingestionOutput = @(& $python @commonArguments 2>&1)
    Require ($LASTEXITCODE -eq 0) ("Attempt-04 ingestion failed: " + ($ingestionOutput -join ' '))
    Require (Test-Path -LiteralPath $ingestedPath -PathType Leaf) 'Attempt-04 ingestion output was not created'

    Write-Output 'C1_5_ATTEMPT_04_FINALIZE_BEGIN'
    Write-Output "PREPARATION_COMMIT=$preparationCommit"
    Write-Output 'CHRONOLOGY_VALID=True'
    Write-Output 'TARGET_RECEIPT_VALID=True'
    Write-Output "RAW_SCREENSHOT=$sourceScreenshot"
    Write-Output "CANONICAL_SCREENSHOT_SHA256=$(Get-Sha256 $screenshotPath)"
    Write-Output "ATTESTATION_SHA256=$(Get-Sha256 $attestationPath)"
    Write-Output "INGESTED_OUTPUT=$ingestedPath"
    Write-Output "INGESTED_SHA256=$(Get-Sha256 $ingestedPath)"
    Write-Output 'C1_5_ATTEMPT_04_FINALIZE_END'
}
finally {
    Pop-Location
}
