[CmdletBinding()]
param(
    [string] $RuntimeRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server',
    [string] $JavaExe = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe',
    [string] $ExpectedJarSha256,
    [string] $SourceCommit,
    [int] $ReadyTimeoutSeconds = 240,
    [int] $StopTimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$launcher = Join-Path $RuntimeRoot 'fabric-server-launch.jar'
$propertiesPath = Join-Path $RuntimeRoot 'server.properties'
$installedJar = Join-Path $RuntimeRoot 'mods\mineocclude-0.1.1.jar'
$latestLog = Join-Path $RuntimeRoot 'logs\latest.log'
$receiptRoot = Join-Path $RuntimeRoot 'logs\target-retention-smoke'
$receiptPath = Join-Path $receiptRoot 'target-retention-smoke-receipt.json'
$logCopy = Join-Path $receiptRoot 'target-retention-smoke-latest.log'
foreach ($required in @($JavaExe, $launcher, $propertiesPath, $installedJar)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required target-retention smoke file is absent: $required"
    }
}
$properties = Get-Content -LiteralPath $propertiesPath
if ($properties -notcontains 'spawn-animals=false') {
    throw 'Target-retention smoke refuses to run unless spawn-animals=false remains exact.'
}
$jarSha = (Get-FileHash -LiteralPath $installedJar -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ExpectedJarSha256 -and $jarSha -ne $ExpectedJarSha256.ToLowerInvariant()) {
    throw "Installed JAR hash mismatch: expected $ExpectedJarSha256, found $jarSha"
}

New-Item -ItemType Directory -Path $receiptRoot -Force | Out-Null
$startedUtc = [DateTime]::UtcNow
$process = [Diagnostics.Process]::new()
$process.StartInfo = [Diagnostics.ProcessStartInfo]@{
    FileName = $JavaExe
    Arguments = ('-Xms1G -Xmx2G -Dfile.encoding=UTF-8 -jar "{0}" nogui' -f $launcher)
    WorkingDirectory = $RuntimeRoot
    UseShellExecute = $false
    RedirectStandardInput = $true
    RedirectStandardOutput = $false
    RedirectStandardError = $false
    CreateNoWindow = $true
}

$vanillaReady = $false
$modReady = $false
$previewValid = $false
$episodeArmed = $false
$episodeValid = $false
$forcedTermination = $false
$stopSent = $false
$exitCode = $null

function Read-FreshLog {
    if (-not (Test-Path -LiteralPath $latestLog -PathType Leaf)) { return '' }
    $info = Get-Item -LiteralPath $latestLog
    if ($info.LastWriteTimeUtc -lt $startedUtc.AddSeconds(-1)) { return '' }
    return Get-Content -Raw -LiteralPath $latestLog -ErrorAction SilentlyContinue
}

function Wait-ForLog([string] $Pattern, [int] $TimeoutSeconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        if ((Read-FreshLog) -match $Pattern) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

try {
    if (-not $process.Start()) { throw 'Java server process did not start.' }
    $vanillaReady = Wait-ForLog 'Done \([0-9.]+s\)! For help' $ReadyTimeoutSeconds
    $modReady = Wait-ForLog '\[MineOcclude\] server ready; output ->' 10
    if (-not ($vanillaReady -and $modReady)) { throw 'Server readiness signals were not observed.' }

    $process.StandardInput.WriteLine('mineocclude targetstatus')
    $process.StandardInput.Flush()
    $previewValid = Wait-ForLog 'target status: valid=true required=true count=1.*episode=-1.*problems=NONE' 20
    if (-not $previewValid) { throw 'Preview target did not pass the read-only target status gate.' }

    foreach ($command in @(
        'mineocclude mode normal',
        'mineocclude duration 0',
        'mineocclude reveal 0',
        'mineocclude impulse -1 0',
        'mineocclude lockcam on',
        'mineocclude warmup 1200',
        'mineocclude start layout_01 11499 202608031499 0.0 0.0 20'
    )) {
        $process.StandardInput.WriteLine($command)
    }
    $process.StandardInput.Flush()
    $episodeArmed = Wait-ForLog 'Armed episode 11499 \(layout_01.*warmup 1200t' 30
    if (-not $episodeArmed) { throw 'Target-retention smoke episode was not armed.' }

    Start-Sleep -Seconds 3
    $process.StandardInput.WriteLine('mineocclude targetstatus')
    $process.StandardInput.Flush()
    $episodeValid = Wait-ForLog 'target status: valid=true required=true count=1.*episode=11499.*lifecycle=READY.*problems=NONE' 20
    if (-not $episodeValid) { throw 'Armed target did not remain valid across server ticks.' }

    $logText = Read-FreshLog
    if ($logText -match 'target retention failure|warmup tick [1-9][0-9]* alive=false|REFUSED:.*target') {
        throw 'The server log contains a target-retention refusal or removal signal.'
    }
    $process.StandardInput.WriteLine('mineocclude stop')
    $process.StandardInput.WriteLine('stop')
    $process.StandardInput.Flush()
    $stopSent = $true
    if (-not $process.WaitForExit($StopTimeoutSeconds * 1000)) {
        $process.Kill()
        $forcedTermination = $true
        $process.WaitForExit()
    }
    $exitCode = $process.ExitCode
}
finally {
    if (-not $process.HasExited) {
        try {
            $process.StandardInput.WriteLine('mineocclude stop')
            $process.StandardInput.WriteLine('stop')
            $process.StandardInput.Flush()
            $stopSent = $true
            if (-not $process.WaitForExit($StopTimeoutSeconds * 1000)) {
                $process.Kill()
                $forcedTermination = $true
                $process.WaitForExit()
            }
            $exitCode = $process.ExitCode
        }
        catch {
            $process.Kill()
            $forcedTermination = $true
        }
    }
    $process.Dispose()
}

if (Test-Path -LiteralPath $latestLog -PathType Leaf) {
    Copy-Item -LiteralPath $latestLog -Destination $logCopy -Force
}
$stoppedCleanly = $stopSent -and -not $forcedTermination -and $exitCode -eq 0
$receipt = [ordered]@{
    schema_version = 'person-c-target-retention-smoke-v0.1'
    source_commit = $SourceCommit
    java_executable = $JavaExe
    runtime_root = $RuntimeRoot
    spawn_animals = $false
    mineocclude_jar = [ordered]@{ path = $installedJar; sha256 = $jarSha }
    preview_target_status_pass = $previewValid
    episode_id = 11499
    episode_command = 'mineocclude start layout_01 11499 202608031499 0.0 0.0 20'
    episode_armed = $episodeArmed
    armed_target_status_pass = $episodeValid
    target_retention_smoke_pass = ($vanillaReady -and $modReady -and $previewValid -and $episodeArmed -and $episodeValid)
    server_stopped_cleanly = $stoppedCleanly
    forced_termination = $forcedTermination
    exit_code = $exitCode
    latest_log_copy = $logCopy
    completed_utc = [DateTime]::UtcNow.ToString('o')
}
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
$receipt | ConvertTo-Json -Depth 8
if (-not $receipt.target_retention_smoke_pass -or -not $stoppedCleanly) { exit 1 }
