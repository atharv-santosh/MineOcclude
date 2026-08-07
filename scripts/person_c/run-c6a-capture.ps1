[CmdletBinding()]
param(
    [string] $Manifest = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A\docs\status\person_c_c6a_capture_manifest_v0_2\c6a_capture_manifest.json',
    [string] $RepositoryRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A',
    [string] $ServerRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server',
    [string] $ClientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client',
    [string] $JavaExe = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe',
    [switch] $ExecuteScientificCapture
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $ExecuteScientificCapture) {
    throw 'Scientific capture is fail-closed. Re-run with -ExecuteScientificCapture only after every manifest manual gate is PASS.'
}
$liveLogModule = Join-Path $RepositoryRoot 'scripts\person_c\C6ALiveLog.psm1'
foreach ($path in @($Manifest, $JavaExe, (Join-Path $ServerRoot 'fabric-server-launch.jar'), $liveLogModule)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file absent: $path" }
}
Import-Module -Name $liveLogModule -Force
$plan = Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json
if (-not $plan.manifest_ready -or $plan.c6b_episode_count -ne 0) {
    throw 'Manifest is not ready or contains C6B episodes.'
}
$head = (& git -C $RepositoryRoot rev-parse HEAD).Trim()
& git -C $RepositoryRoot merge-base --is-ancestor $plan.source_commit $head
if ($LASTEXITCODE -ne 0) { throw "Capture source commit is not an ancestor of HEAD: $($plan.source_commit)" }
if (& git -C $RepositoryRoot status --porcelain) { throw 'Repository must be clean before C6A execution.' }

$geometry = Join-Path $RepositoryRoot ($plan.accepted_geometry.path.Replace('/', '\'))
$geometrySha = (Get-FileHash -LiteralPath $geometry -Algorithm SHA256).Hash.ToLowerInvariant()
if ($geometrySha -ne $plan.accepted_geometry.sha256) { throw 'Accepted geometry hash mismatch.' }
$installedJar = Join-Path $ServerRoot 'mods\mineocclude-0.1.1.jar'
$installedJarSha = (Get-FileHash -LiteralPath $installedJar -Algorithm SHA256).Hash.ToLowerInvariant()
if ($installedJarSha -ne $plan.mineocclude_jar.sha256) { throw 'Installed server JAR hash mismatch.' }
foreach ($episode in $plan.episodes) {
    $schedule = Join-Path $ServerRoot ("mineocclude_schedules\episode_{0}.jsonl" -f $episode.episode_id)
    if (-not (Test-Path -LiteralPath $schedule -PathType Leaf)) { throw "Schedule missing: $schedule" }
    $actual = (Get-FileHash -LiteralPath $schedule -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $episode.noise_schedule.sha256) { throw "Schedule hash mismatch: $schedule" }
    foreach ($output in @($episode.expected_output_paths.server, $episode.expected_output_paths.client)) {
        if (Test-Path -LiteralPath $output) { throw "Refusing to overwrite existing C6A output: $output" }
    }
}

$launcher = Join-Path $ServerRoot 'fabric-server-launch.jar'
$latestLog = Join-Path $ServerRoot 'logs\latest.log'
$clientLog = Join-Path $ClientRoot 'logs\latest.log'
$startedUtc = [DateTime]::UtcNow
$process = [Diagnostics.Process]::new()
$process.StartInfo = [Diagnostics.ProcessStartInfo]@{
    FileName = $JavaExe
    Arguments = ('-Xms1G -Xmx2G -Dfile.encoding=UTF-8 -jar "{0}" nogui' -f $launcher)
    WorkingDirectory = $ServerRoot
    UseShellExecute = $false
    RedirectStandardInput = $true
    RedirectStandardOutput = $false
    RedirectStandardError = $false
    CreateNoWindow = $true
}

function Read-Log([string] $Path) {
    $text = Read-C6ALiveLogText -Path $Path
    if ($null -eq $text) { return '' }
    return $text
}
function Wait-Log([string] $Path, [string] $Pattern, [int] $Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        if ((Read-Log $Path) -match $Pattern) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

try {
    if (-not $process.Start()) { throw 'Server process did not start.' }
    if (-not (Wait-Log $latestLog 'Done \([0-9.]+s\)! For help' 240)) { throw 'Server readiness timeout.' }
    Write-Host 'Launch the authenticated pinned client profile and connect to 127.0.0.1:25565.'
    if (-not (Wait-Log $latestLog 'joined the game' 600)) { throw 'Authenticated client connection timeout.' }
    if (-not (Wait-Log $clientLog 'Connecting to 127.0.0.1, 25565' 30)) { throw 'Client connection log missing.' }

    foreach ($episode in $plan.episodes) {
        $scheduleLogOffset = Get-C6ALiveLogLength -Path $latestLog
        foreach ($command in @(
            "mineocclude mode $($episode.scene_command)",
            "mineocclude duration $($episode.hidden_frames)",
            'mineocclude reveal 0',
            'mineocclude impulse -1 0',
            'mineocclude lockcam on',
            "mineocclude warmup $($episode.warmup_ticks)",
            $episode.execution_command
        )) {
            $process.StandardInput.WriteLine($command)
        }
        $process.StandardInput.Flush()
        $scheduleFileName = 'episode_{0}.jsonl' -f $episode.episode_id
        if (-not (Wait-C6AScheduleLoadEvent -Path $latestLog -EpisodeId $episode.episode_id -DrawCount $episode.noise_schedule.n_draws -ScheduleFileName $scheduleFileName -StartOffset $scheduleLogOffset -TimeoutMilliseconds 60000 -PollIntervalMilliseconds 200)) {
            throw "Schedule load not observed for episode $($episode.episode_id)."
        }
        if (-not (Wait-Log $latestLog ("episode {0} recording started" -f $episode.episode_id) 180)) {
            throw "Recording start not observed for episode $($episode.episode_id)."
        }
        if (-not (Wait-Log $latestLog ("episode {0} ended after" -f $episode.episode_id) 300)) {
            throw "Clean episode completion not observed for episode $($episode.episode_id)."
        }
        if ((Read-Log $latestLog) -match ("REFUSED:.*episode {0}|target retention failure.*episode {0}" -f $episode.episode_id)) {
            throw "Episode $($episode.episode_id) failed a scientific hard gate."
        }
    }
}
finally {
    if (-not $process.HasExited) {
        $process.StandardInput.WriteLine('mineocclude stop')
        $process.StandardInput.WriteLine('stop')
        $process.StandardInput.Flush()
        if (-not $process.WaitForExit(60000)) { $process.Kill(); $process.WaitForExit() }
    }
    $process.Dispose()
}
