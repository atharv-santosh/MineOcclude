[CmdletBinding()]
param(
    [string] $RuntimeRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server',
    [string] $JavaExe = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe',
    [int] $ReadyTimeoutSeconds = 240,
    [int] $StopTimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$launcher = Join-Path $RuntimeRoot 'fabric-server-launch.jar'
$logRoot = Join-Path $RuntimeRoot 'logs\smoke'
$consoleLog = Join-Path $logRoot 'server-smoke-console.log'
$receiptPath = Join-Path $logRoot 'server-smoke-receipt.json'
$latestLog = Join-Path $RuntimeRoot 'logs\latest.log'
foreach ($requiredFile in @($JavaExe, $launcher, (Join-Path $RuntimeRoot 'server.properties'), (Join-Path $RuntimeRoot 'eula.txt'))) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required smoke-test file is absent: $requiredFile"
    }
}

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
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
$mineOccludeReady = $false
$stopSent = $false
$forcedTermination = $false
$exitCode = $null
try {
    if (-not $process.Start()) {
        throw 'Java server process did not start.'
    }
    $deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $latestLog -PathType Leaf) {
            $latestLogInfo = Get-Item -LiteralPath $latestLog
            $logText = if ($latestLogInfo.LastWriteTimeUtc -ge $startedUtc.AddSeconds(-1)) {
                Get-Content -Raw -LiteralPath $latestLog -ErrorAction SilentlyContinue
            }
            else {
                ''
            }
            $vanillaReady = $logText -match 'Done \([0-9.]+s\)! For help'
            $mineOccludeReady = $logText -match '\[MineOcclude\] server ready; output ->'
        }
        if ($vanillaReady -and $mineOccludeReady) {
            $process.StandardInput.WriteLine('stop')
            $process.StandardInput.Flush()
            $stopSent = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }

    if (-not $process.HasExited -and -not $stopSent) {
        $process.StandardInput.WriteLine('stop')
        $process.StandardInput.Flush()
        $stopSent = $true
    }
    if (-not $process.WaitForExit($StopTimeoutSeconds * 1000)) {
        $process.Kill()
        $forcedTermination = $true
        $process.WaitForExit()
    }
    $process.WaitForExit()
    $exitCode = $process.ExitCode
}
finally {
    if (-not $process.HasExited) {
        try {
            $process.StandardInput.WriteLine('stop')
            $process.StandardInput.Flush()
            if (-not $process.WaitForExit(30000)) {
                $process.Kill()
                $forcedTermination = $true
            }
        }
        catch {
            $process.Kill()
            $forcedTermination = $true
        }
    }
    $process.Dispose()
}

if (Test-Path -LiteralPath $latestLog -PathType Leaf) {
    Copy-Item -LiteralPath $latestLog -Destination $consoleLog -Force
}
$ready = $vanillaReady -and $mineOccludeReady
$stoppedCleanly = $stopSent -and -not $forcedTermination -and $exitCode -eq 0
$receipt = [ordered]@{
    schema_version = '1.0'
    runtime_baseline_version = 'person-c-c1-runtime-baseline-v0.2'
    java_executable = $JavaExe
    launch_arguments = "-Xms1G -Xmx2G -Dfile.encoding=UTF-8 -jar $launcher nogui"
    working_directory = $RuntimeRoot
    started_utc = $startedUtc.ToString('o')
    completed_utc = [DateTime]::UtcNow.ToString('o')
    vanilla_ready_signal_observed = $vanillaReady
    mineocclude_ready_signal_observed = $mineOccludeReady
    server_smoke_pass = $ready
    stop_command_sent = $stopSent
    forced_termination = $forcedTermination
    exit_code = $exitCode
    server_stopped_cleanly = $stoppedCleanly
    console_log = $consoleLog
}
$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
$receipt | ConvertTo-Json -Depth 5
if (-not $ready -or -not $stoppedCleanly) {
    exit 1
}
