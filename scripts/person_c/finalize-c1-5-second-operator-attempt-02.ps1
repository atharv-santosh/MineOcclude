[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$requiredBranch = 'completion/person-c-c1-c6a'
$requiredAncestry = '75f6515aead5755f1f47a3cddea354102eead328'
$serverRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server'
$clientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client'
$receiptPath = Join-Path $serverRoot 'mineocclude_observations\c1_5_second_operator_attempt_02_layout_01.json'
$screenshotPath = Join-Path $clientRoot 'c1_5_evidence\second_operator_attempt_02_layout_01.png'
$attestationPath = Join-Path $serverRoot 'c1_5_evidence\second_operator_attempt_02_attestation.json'
$ingestedPath = Join-Path $serverRoot 'c1_5_evidence\second_operator_attempt_02_ingested.json'
$serverLogPath = Join-Path $serverRoot 'logs\latest.log'
$clientLogPath = Join-Path $clientRoot 'logs\latest.log'
$serverLogArchive = Join-Path $serverRoot 'c1_5_evidence\second_operator_attempt_02_success\server_latest.log'
$clientLogArchive = Join-Path $clientRoot 'c1_5_evidence\second_operator_attempt_02_success\client_latest.log'
$schedulePath = Join-Path $serverRoot 'mineocclude_schedules\episode_11506.jsonl'
$templatePath = Join-Path $RepoRoot 'docs\status\person_c_c1_5_second_operator_attempt_02_v0_1\second_operator_attempt_02_attestation.template.json'
$failureRecordPath = Join-Path $RepoRoot 'docs\status\person_c_c1_5_second_operator_attempt_02_v0_1\attempt_01_failure_record.json'
$ingestionPath = Join-Path $RepoRoot 'scripts\person_c\ingest_c1_5_second_operator_attempt_02_runtime.py'
$firstAttestationPath = Join-Path $serverRoot 'c1_5_evidence\first_operator_attempt_04_attestation.json'
$attempt01Receipt = Join-Path $serverRoot 'mineocclude_observations\c1_5_second_operator_attempt_01_layout_01.json'
$attempt01Screenshot = Join-Path $clientRoot 'screenshots\2026-08-03_22.25.53.png'
$attempt01ServerLog = Join-Path $serverRoot 'c1_5_evidence\second_operator_attempt_01_preserved\server_latest.log'
$attempt01ClientLog = Join-Path $clientRoot 'c1_5_evidence\second_operator_attempt_01_preserved\client_latest.log'

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

Push-Location -LiteralPath $RepoRoot
try {
    $branch = (& git branch --show-current).Trim()
    Require ($LASTEXITCODE -eq 0 -and $branch -eq $requiredBranch) "Wrong branch: $branch"
    $worktreeStatus = @(& git status --porcelain=v1)
    Require ($LASTEXITCODE -eq 0 -and $worktreeStatus.Count -eq 0) 'Repository worktree must be clean before finalization'
    $preparationCommit = (& git log -1 --format=%H -- scripts/person_c/finalize-c1-5-second-operator-attempt-02.ps1).Trim()
    Require ($preparationCommit -match '^[0-9a-f]{40}$') 'Attempt-02 package is not committed'
    & git merge-base --is-ancestor $requiredAncestry $preparationCommit
    Require ($LASTEXITCODE -eq 0) 'Attempt-02 preparation does not descend from required ancestry'
    & git merge-base --is-ancestor $preparationCommit HEAD
    Require ($LASTEXITCODE -eq 0) 'Attempt-02 preparation commit is not an ancestor of HEAD'

    $attempt01Expected = @{
        $attempt01Receipt = '7625fd454b71acedcd42524cab64bb799147020e21e7e78e888f3d31e092b630'
        $attempt01Screenshot = 'ebcde38bf4b2e8edd313d26de5bf95efabda0a183354ad09d03593565c063c21'
        $attempt01ServerLog = '2dd9c8aa26c1e15f1b9331991d13d24b73bbaa13ce98ff18348283af4248b513'
        $attempt01ClientLog = '155ad971f724ac5f5db81a13d7eae42e032011eb8c70ea4c8e2cb3c0a2249812'
    }
    foreach ($entry in $attempt01Expected.GetEnumerator()) {
        Require (Test-Path -LiteralPath $entry.Key -PathType Leaf) "Attempt-01 evidence absent: $($entry.Key)"
        Require ((Get-Sha256 $entry.Key) -eq $entry.Value) "Attempt-01 evidence hash drift: $($entry.Key)"
    }
    $failureRecord = Get-Content -Raw -LiteralPath $failureRecordPath | ConvertFrom-Json
    Require ($failureRecord.classification -eq 'SCREENSHOT_CAPTURED_BEFORE_GEOMETRY_RECEIPT_CONFIRMATION') 'Attempt-01 failure classification drift'
    Require ($failureRecord.preservation.status -eq 'PRESERVED_HASH_BOUND_NOT_CERTIFIED') 'Attempt-01 preservation status drift'
    Require ((Get-Sha256 $firstAttestationPath) -eq 'bd4b0f5070a6d2b96b03e81dbe8e90ac9b7e51e31fbebb9e556cea9532605edd') 'First-operator attestation hash drift'

    foreach ($requiredFile in @($receiptPath, $serverLogPath, $clientLogPath, $schedulePath, $templatePath, $ingestionPath, $firstAttestationPath)) {
        Require (Test-Path -LiteralPath $requiredFile -PathType Leaf) "Required attempt-02 input absent: $requiredFile"
    }
    foreach ($createOnlyPath in @($screenshotPath, $attestationPath, $ingestedPath, $serverLogArchive, $clientLogArchive)) {
        Require (-not (Test-Path -LiteralPath $createOnlyPath)) "Create-only attempt-02 path already exists: $createOnlyPath"
    }

    $receipt = Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json
    Require ($receipt.receipt_id -eq 'c1_5_second_operator_attempt_02_layout_01') 'Geometry receipt ID mismatch'
    Require ($receipt.layout_id -eq 'layout_01' -and $receipt.episode_id -eq 11506) 'Geometry receipt layout/episode mismatch'
    Require ($receipt.running -eq $true -and $receipt.capturing -eq $false -and $receipt.lifecycle_state -eq 'READY' -and $receipt.warmup_ticks_remaining -gt 0) 'Geometry receipt was not written during READY warmup'
    Require ($receipt.target.valid -eq $true -and $receipt.target.required -eq $true -and $receipt.target.tagged_target_count -eq 1 -and $receipt.target.problems.Count -eq 0) 'Geometry receipt target fields failed'

    $serverLines = @(Get-Content -LiteralPath $serverLogPath)
    $clientLines = @(Get-Content -LiteralPath $clientLogPath)
    $warmup = Find-LogEvent $serverLines 'Warmup delay set to 12000 ticks \(600\.0s\)' 'warmup 12000 configuration'
    $armed = Find-LogEvent $serverLines 'episode 11506 armed \(layout=layout_01, 12000 warmup \+ 20 record ticks' 'episode armed'
    $status = Find-LogEvent $serverLines 'target status: valid=true required=true count=1.*episode=11506.*lifecycle=READY.*problems=NONE' 'valid targetstatus'
    $observed = Find-LogEvent $serverLines 'wrote read-only geometry receipt .*c1_5_second_operator_attempt_02_layout_01\.json' 'observegeometry completed'
    $confirmed = Find-LogEvent $serverLines 'Wrote observation-only geometry receipt: .*c1_5_second_operator_attempt_02_layout_01\.json' 'receipt-written confirmation'
    $aborted = Find-LogEvent $serverLines 'episode 11506 aborted during warmup' 'episode aborted during warmup'
    $serverStopped = Find-LogEvent $serverLines 'Stopping server' 'clean server stop'
    $clientStopped = Find-LogEvent $clientLines 'Stopping!' 'clean client stop'
    Require ($warmup.Index -lt $armed.Index -and $armed.Index -lt $status.Index -and $status.Index -lt $observed.Index -and $observed.Index -lt $confirmed.Index -and $confirmed.Index -lt $aborted.Index -and $aborted.Index -lt $serverStopped.Index) 'Strict server chronology failed'
    Require (-not ($serverLines -match 'episode 11506 recording started')) 'Attempt 02 entered recording'
    Require (-not ($serverLines -match '(?i)target retention failure')) 'Attempt 02 contains target-retention failure'

    $armedSeconds = Get-LineSeconds $armed.Line 'armed event'
    $statusOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $status.Line 'targetstatus event')
    $observedOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $observed.Line 'observegeometry event')
    $confirmationOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $confirmed.Line 'receipt confirmation event')
    $abortOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $aborted.Line 'abort event')
    $serverStopOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $serverStopped.Line 'server stop event')
    $clientStopOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $clientStopped.Line 'client stop event')
    Require ($statusOffset -ge 10) 'targetstatus occurred less than ten seconds after arming'
    $screenshotCandidates = @()
    foreach ($line in $clientLines) {
        if ($line -match 'Saved screenshot as ([^\\/\s]+\.png)') {
            $fileName = $Matches[1]
            $eventOffset = Get-OffsetSeconds $armedSeconds (Get-LineSeconds $line 'screenshot event')
            if ($eventOffset -gt 0 -and $eventOffset -lt $abortOffset) {
                $screenshotCandidates += [pscustomobject]@{ Offset = $eventOffset; FileName = $fileName }
            }
        }
    }
    Require ($screenshotCandidates.Count -eq 1) 'Exactly one F2 screenshot must occur after arming and before warmup abort'
    $screenshotEvent = $screenshotCandidates[0]
    Require (10 -le $statusOffset -and $statusOffset -lt $observedOffset -and $observedOffset -le $confirmationOffset -and $confirmationOffset -lt $screenshotEvent.Offset -and $screenshotEvent.Offset -lt $abortOffset -and $abortOffset -lt $serverStopOffset) 'Strict cross-log chronology failed; F2 must follow receipt-written confirmation'
    Require ($clientStopOffset -gt $abortOffset) 'Client did not stop after warmup abort'
    $sourceScreenshot = Join-Path (Join-Path $clientRoot 'screenshots') $screenshotEvent.FileName
    Require (Test-Path -LiteralPath $sourceScreenshot -PathType Leaf) "Logged F2 screenshot absent: $sourceScreenshot"

    $accountEvent = Find-LogEvent $clientLines 'Setting user: ([A-Za-z0-9_]+)' 'authenticated account'
    Require ($accountEvent.Line -match 'Setting user: ([A-Za-z0-9_]+)') 'Unable to parse authenticated account'
    $observedAccount = $Matches[1]
    Require ($observedAccount -ceq 'Santa313') 'Attempt 02 must use the same second-operator account as attempt 01: Santa313'
    $firstAttestation = Get-Content -Raw -LiteralPath $firstAttestationPath | ConvertFrom-Json
    Require ($observedAccount -ine [string]$firstAttestation.observed_account_name -and $observedAccount -ine [string]$firstAttestation.operator_id) 'Second operator matches first operator'
    $confirmation = Read-Host 'Type YES only if you are the same second human as attempt 01 and remain a different human from the first operator'
    Require ($confirmation -ceq 'YES') 'Required same-human/independence attestation was not provided'

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
    $attestation.operator_id = $observedAccount
    $attestation.same_human_as_second_operator_attempt_01 = $true
    $attestation.utc_start = (Get-Item -LiteralPath $serverLogPath).CreationTimeUtc.ToString('o')
    $attestation.utc_end = (Get-Item -LiteralPath $serverLogPath).LastWriteTimeUtc.ToString('o')
    $attestation.preparation_commit = $preparationCommit
    $attestation.observed_account_name = $observedAccount
    $attestation.fresh_runtime_session = $true
    $attestation.targetstatus_passed_after_at_least_ten_seconds = $true
    $attestation.observegeometry_completed_before_receipt_confirmation = $true
    $attestation.receipt_write_confirmed_before_f2 = $true
    $attestation.exactly_one_f2_after_receipt_confirmation = $true
    $attestation.mineocclude_stop_aborted_during_warmup = $true
    $attestation.recording_never_started = $true
    $attestation.screenshot_from_same_session = $true
    $attestation.server_stopped_cleanly = $true
    $attestation.operator_identity_differs_from_first_operator = $true
    $attestation.authenticated_account_differs_from_first_operator = $true
    $attestation.notes = 'Same independent second human as attempt 01; strict chronology was validated before create-only finalization.'
    Write-CreateOnlyUtf8 $attestationPath (($attestation | ConvertTo-Json -Depth 20) + "`n")

    $python = (Get-Command python -ErrorAction Stop).Source
    $commonArguments = @($ingestionPath, '--geometry-receipt', $receiptPath, '--screenshot', $screenshotPath, '--attestation', $attestationPath, '--output', $ingestedPath)
    $validationOutput = @(& $python @commonArguments --validate-only 2>&1)
    Require ($LASTEXITCODE -eq 0) ("Attempt-02 validation failed: " + ($validationOutput -join ' '))
    $ingestionOutput = @(& $python @commonArguments 2>&1)
    Require ($LASTEXITCODE -eq 0) ("Attempt-02 ingestion failed: " + ($ingestionOutput -join ' '))
    Require (Test-Path -LiteralPath $ingestedPath -PathType Leaf) 'Attempt-02 ingestion output was not created'

    Write-Output 'C1_5_SECOND_OPERATOR_ATTEMPT_02_FINALIZE_BEGIN'
    Write-Output "PREPARATION_COMMIT=$preparationCommit"
    Write-Output "OPERATOR_ID=$observedAccount"
    Write-Output 'SAME_HUMAN_AS_ATTEMPT_01=True'
    Write-Output 'INDEPENDENT_FROM_FIRST_OPERATOR=True'
    Write-Output 'CHRONOLOGY_VALID=True'
    Write-Output "RAW_SCREENSHOT=$sourceScreenshot"
    Write-Output "CANONICAL_SCREENSHOT_SHA256=$(Get-Sha256 $screenshotPath)"
    Write-Output "ATTESTATION_SHA256=$(Get-Sha256 $attestationPath)"
    Write-Output "INGESTED_OUTPUT=$ingestedPath"
    Write-Output "INGESTED_SHA256=$(Get-Sha256 $ingestedPath)"
    Write-Output 'C1_5_COMPLETE=True'
    Write-Output 'C1_5_SECOND_OPERATOR_ATTEMPT_02_FINALIZE_END'
}
finally {
    Pop-Location
}
