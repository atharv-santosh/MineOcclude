$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$outputRoot = Join-Path $sourceRoot 'evidence_extension_outputs'
$archive = Join-Path $outputRoot 'mineocclude_evidence_extension_reproduction.zip'
$python = Join-Path $sourceRoot 'history_diagnostic_outputs\windows_clean_cpu\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $archive)) { throw 'Reproduction archive is absent' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Isolated CPU environment is absent' }
$replayDirectory = Join-Path $outputRoot ('clean-replay-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $replayDirectory | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($archive)
try {
    foreach ($entry in $zip.Entries) {
        $target = [System.IO.Path]::GetFullPath((Join-Path $replayDirectory $entry.FullName))
        if (-not $target.StartsWith($replayDirectory + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Archive entry escapes replay directory: $($entry.FullName)"
        }
    }
} finally { $zip.Dispose() }
[System.IO.Compression.ZipFile]::ExtractToDirectory($archive, $replayDirectory)
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$savedBytecode = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location $replayDirectory
try {
    & $python '-c' 'import importlib.util; assert importlib.util.find_spec("torch") is None; import numpy, matplotlib, PIL; print("ISOLATED_CPU_ENVIRONMENT", numpy.__version__, matplotlib.__version__, PIL.__version__)' 2>&1 | Out-File 'environment.log' -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw 'CPU-only environment validation failed' }
    & $python 'reproduce_all.py' 2>&1 | Out-File 'preserved-studies.log' -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw 'Preserved-study CPU replay failed' }
    & $python 'extension/reproduce.py' 2>&1 | Out-File 'extension.log' -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw 'Extension CPU replay failed' }
    & $python 'extension/source/make_figures.py' '--root' 'extension' '--output' 'reconstructed-extension-figures' 2>&1 | Out-File 'figures.log' -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw 'Portable figure reconstruction failed' }
    $timer.Stop()
    $report = [ordered]@{
        status='PASS'
        archive_sha256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        extracted_directory=$replayDirectory
        elapsed_seconds=$timer.Elapsed.TotalSeconds
        torch_installed=$false
        preserved_studies_reproduced=$true
        extension_statistics_reproduced=$true
        extension_figures_reconstructed=$true
        anonymous_website_access='NOT_VERIFIED'
    }
    $report | ConvertTo-Json -Depth 4 | Out-File (Join-Path $outputRoot 'clean_cpu_replay.json') -Encoding utf8
    Write-Output ($report | ConvertTo-Json -Depth 4)
} finally {
    Pop-Location
    $env:PYTHONDONTWRITEBYTECODE = $savedBytecode
}
