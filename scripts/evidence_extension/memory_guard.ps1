param([int]$SupervisorPid = 410)
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$logPath = Join-Path $sourceRoot 'evidence_extension_outputs\memory_guard.jsonl'
while ($true) {
    $command = & wsl.exe -d Ubuntu-24.04 -- ps -p $SupervisorPid -o args= 2>$null
    if ($LASTEXITCODE -ne 0 -or $command -notmatch 'scripts/evidence_extension/run_production.py') { break }
    $memory = Get-CimInstance Win32_OperatingSystem
    $freeGiB = $memory.FreePhysicalMemory / 1MB
    $linux = & wsl.exe -d Ubuntu-24.04 -- cat /proc/meminfo
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect WSL memory' }
    $cacheKiB = 0.0
    foreach ($line in $linux) {
        if ($line -match '^(Cached|SReclaimable):\s+(\d+)\s+kB') { $cacheKiB += [double]$Matches[2] }
    }
    $cacheGiB = $cacheKiB / 1MB
    if ($cacheGiB -gt 8 -or ($freeGiB -lt 12 -and $cacheGiB -gt 3)) {
        & wsl.exe -d Ubuntu-24.04 -u root -- sync
        if ($LASTEXITCODE -ne 0) { throw 'Cache synchronization failed' }
        & wsl.exe -d Ubuntu-24.04 -u root -- sysctl -w vm.drop_caches=3
        if ($LASTEXITCODE -ne 0) { throw 'Cache reclamation failed' }
        & wsl.exe -d Ubuntu-24.04 -u root -- sysctl -w vm.compact_memory=1
        if ($LASTEXITCODE -ne 0) { throw 'Memory compaction failed' }
        $after = Get-CimInstance Win32_OperatingSystem
        $event = [ordered]@{
            utc=[DateTime]::UtcNow.ToString('o')
            action='reclaim_disposable_linux_caches'
            windows_free_gib_before=$freeGiB
            linux_cache_gib_before=$cacheGiB
            windows_free_gib_after=($after.FreePhysicalMemory / 1MB)
            scientific_processes_stopped=$false
            files_deleted=$false
        }
        $event | ConvertTo-Json -Compress | Add-Content -LiteralPath $logPath -Encoding utf8
        Write-Output ($event | ConvertTo-Json -Compress)
    }
    $latest = Get-CimInstance Win32_OperatingSystem
    if ($latest.FreePhysicalMemory / 1MB -lt 3) {
        $command = & wsl.exe -d Ubuntu-24.04 -- ps -p $SupervisorPid -o args= 2>$null
        if ($LASTEXITCODE -eq 0 -and $command -match 'scripts/evidence_extension/run_production.py') {
            & wsl.exe -d Ubuntu-24.04 -- kill -TERM $SupervisorPid
            throw 'Available host RAM stayed below 3 GiB after cache reclamation. Gracefully stopped only the research supervisor; completed artifacts are preserved.'
        }
    }
    Start-Sleep -Seconds 30
}
Write-Output 'MEMORY_GUARD_SUPERVISOR_FINISHED'
