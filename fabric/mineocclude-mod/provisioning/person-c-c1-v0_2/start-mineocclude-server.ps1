$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$javaExe = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe'
$runtimeRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server'
$launcherJar = Join-Path $runtimeRoot 'fabric-server-launch.jar'
$transcriptRoot = Join-Path $runtimeRoot 'logs\operator-transcripts'

if (-not (Test-Path -LiteralPath $javaExe -PathType Leaf)) {
    throw "Pinned Java executable is absent: $javaExe"
}
if (-not (Test-Path -LiteralPath $launcherJar -PathType Leaf)) {
    throw "Pinned Fabric server launcher is absent: $launcherJar"
}

New-Item -ItemType Directory -Path $transcriptRoot -Force | Out-Null
$transcript = Join-Path $transcriptRoot ("server-{0}.log" -f (Get-Date -Format 'yyyyMMddTHHmmss'))
Start-Transcript -LiteralPath $transcript | Out-Null
Push-Location -LiteralPath $runtimeRoot
try {
    & $javaExe '-Xms1G' '-Xmx2G' '-Dfile.encoding=UTF-8' '-jar' $launcherJar 'nogui'
    if ($LASTEXITCODE -ne 0) {
        throw "MineOcclude server exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    Stop-Transcript | Out-Null
}
