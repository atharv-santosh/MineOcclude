$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$javaExe = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe'
$runtimeRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client'
$nativesRoot = Join-Path $runtimeRoot 'natives'
$classpathFile = Join-Path $runtimeRoot 'classpath.txt'
$loggingConfig = Join-Path $runtimeRoot 'assets\log_configs\client-1.12.xml'
$transcriptRoot = Join-Path $runtimeRoot 'logs\operator-transcripts'

foreach ($requiredFile in @($javaExe, $classpathFile, $loggingConfig)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required pinned client file is absent: $requiredFile"
    }
}

$classpathEntries = @(Get-Content -LiteralPath $classpathFile | Where-Object { $_ -ne '' })
if ($classpathEntries.Count -eq 0) {
    throw "Pinned client classpath is empty: $classpathFile"
}
foreach ($entry in $classpathEntries) {
    if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
        throw "Pinned classpath entry is absent: $entry"
    }
}
$classpath = $classpathEntries -join [IO.Path]::PathSeparator

New-Item -ItemType Directory -Path $transcriptRoot -Force | Out-Null
$transcript = Join-Path $transcriptRoot ("client-{0}.log" -f (Get-Date -Format 'yyyyMMddTHHmmss'))
$arguments = @(
    '-Xms1G'
    '-Xmx2G'
    '-Dfile.encoding=UTF-8'
    '-XX:HeapDumpPath=mineocclude-client.heapdump'
    '-Dos.name=Windows 10'
    '-Dos.version=10.0'
    "-Djava.library.path=$nativesRoot"
    '-Dminecraft.launcher.brand=mineocclude-person-c'
    '-Dminecraft.launcher.version=person-c-c1-runtime-baseline-v0.2'
    "-Dlog4j.configurationFile=$loggingConfig"
    '-cp'
    $classpath
    'net.fabricmc.loader.impl.launch.knot.KnotClient'
    '--username'
    'C1Observer'
    '--version'
    'fabric-loader-0.15.11-1.16.5'
    '--gameDir'
    $runtimeRoot
    '--assetsDir'
    (Join-Path $runtimeRoot 'assets')
    '--assetIndex'
    '1.16'
    '--uuid'
    '0000000000000000000000000000c101'
    '--accessToken'
    '0'
    '--userType'
    'legacy'
    '--versionType'
    'release'
    '--width'
    '640'
    '--height'
    '360'
)

Start-Transcript -LiteralPath $transcript | Out-Null
Push-Location -LiteralPath $runtimeRoot
try {
    & $javaExe @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "MineOcclude client exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    Stop-Transcript | Out-Null
}
