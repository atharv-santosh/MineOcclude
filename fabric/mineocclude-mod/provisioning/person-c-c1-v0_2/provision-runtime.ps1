[CmdletBinding()]
param(
    [string] $RepositoryRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A',
    [string] $RuntimeRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1',
    [string] $GradleCache = 'C:\Users\lollo\.gradle\caches',
    [string] $JavaExe = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe',
    [string] $SourceCommit = '99b78b6578d17cffc0b5679118a42632284ce7f7'
)

$ErrorActionPreference = 'Stop'

$projectRoot = Join-Path $RepositoryRoot 'fabric\mineocclude-mod'
$templateRoot = Join-Path $projectRoot 'provisioning\person-c-c1-v0_2'
$serverRoot = Join-Path $RuntimeRoot 'server'
$clientRoot = Join-Path $RuntimeRoot 'client'
$minecraftCache = Join-Path $GradleCache 'fabric-loom\1.16.5'
$assetCache = Join-Path $GradleCache 'fabric-loom\assets'
$moduleCache = Join-Path $GradleCache 'modules-2\files-2.1'
$modJar = Join-Path $projectRoot 'build\libs\mineocclude-0.1.0.jar'
$minecraftInfoPath = Join-Path $minecraftCache 'minecraft-info.json'
$assetIndexCache = Join-Path $assetCache 'indexes\1.16.5-1.16.json'

function Assert-File([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is absent: $Path"
    }
}

function Get-Sha1([string] $Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA1).Hash.ToLowerInvariant()
}

function Assert-Sha1([string] $Path, [string] $Expected) {
    $actual = Get-Sha1 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "SHA-1 mismatch for $Path; expected $Expected, found $actual"
    }
}

function Copy-Verified([string] $Source, [string] $Destination, [string] $ExpectedSha1) {
    Assert-File $Source
    Assert-Sha1 $Source $ExpectedSha1
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    Assert-Sha1 $Destination $ExpectedSha1
}

function Get-OrDownload([string] $Url, [string] $Destination, [string] $ExpectedSha1) {
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        try {
            Assert-Sha1 $Destination $ExpectedSha1
            return
        }
        catch {
            Remove-Item -LiteralPath $Destination -Force
        }
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
    Assert-Sha1 $Destination $ExpectedSha1
}

function Test-WindowsRule([object[]] $Rules) {
    if ($null -eq $Rules -or $Rules.Count -eq 0 -or ($Rules.Count -eq 1 -and $null -eq $Rules[0])) {
        return $true
    }
    $allowed = $false
    foreach ($rule in $Rules) {
        $matches = $true
        if ($null -ne $rule.os) {
            if ($null -ne $rule.os.name -and $rule.os.name -ne 'windows') {
                $matches = $false
            }
            if ($null -ne $rule.os.arch -and $rule.os.arch -ne 'x86_64') {
                $matches = $false
            }
            if ($null -ne $rule.os.version -and '10.0' -notmatch $rule.os.version) {
                $matches = $false
            }
        }
        if ($matches) {
            $allowed = $rule.action -eq 'allow'
        }
    }
    return $allowed
}

function Get-MavenPath([string] $Coordinate) {
    $parts = $Coordinate.Split(':')
    if ($parts.Count -ne 3) {
        throw "Unsupported Maven coordinate: $Coordinate"
    }
    return ('{0}\{1}\{2}\{1}-{2}.jar' -f $parts[0].Replace('.', '\'), $parts[1], $parts[2])
}

foreach ($required in @(
    $JavaExe,
    $minecraftInfoPath,
    $assetIndexCache,
    $modJar,
    (Join-Path $templateRoot 'server.properties'),
    (Join-Path $templateRoot 'client-options.txt'),
    (Join-Path $templateRoot 'start-mineocclude-server.ps1'),
    (Join-Path $templateRoot 'start-mineocclude-client.ps1')
)) {
    Assert-File $required
}

$savedErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$javaVersion = & $JavaExe '-version' 2>&1 | Out-String
$ErrorActionPreference = $savedErrorActionPreference
if ($javaVersion -notmatch 'version "17[\.]') {
    throw "Pinned Java is not major version 17: $JavaExe"
}

$minecraftInfo = Get-Content -Raw -LiteralPath $minecraftInfoPath | ConvertFrom-Json
if ($minecraftInfo.id -ne '1.16.5' -or $minecraftInfo.assetIndex.id -ne '1.16') {
    throw 'Unexpected Minecraft metadata; required Minecraft 1.16.5 with asset index 1.16.'
}
Assert-Sha1 $assetIndexCache $minecraftInfo.assetIndex.sha1

foreach ($root in @($serverRoot, $clientRoot)) {
    New-Item -ItemType Directory -Path (Join-Path $root 'mods') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $root 'logs') -Force | Out-Null
}

Copy-Item -LiteralPath (Join-Path $templateRoot 'server.properties') -Destination (Join-Path $serverRoot 'server.properties') -Force
Copy-Item -LiteralPath (Join-Path $templateRoot 'client-options.txt') -Destination (Join-Path $clientRoot 'options.txt') -Force
Copy-Item -LiteralPath (Join-Path $templateRoot 'start-mineocclude-server.ps1') -Destination (Join-Path $serverRoot 'start-mineocclude-server.ps1') -Force
Copy-Item -LiteralPath (Join-Path $templateRoot 'start-mineocclude-client.ps1') -Destination (Join-Path $clientRoot 'start-mineocclude-client.ps1') -Force
Set-Content -LiteralPath (Join-Path $serverRoot 'eula.txt') -Value "# Accepted solely for the isolated MineOcclude C1 runtime.`neula=true" -Encoding ASCII

$apiRoot = Join-Path $moduleCache 'net.fabricmc.fabric-api\fabric-api\0.42.0+1.16'
$apiPom = Get-ChildItem -LiteralPath $apiRoot -Recurse -Filter 'fabric-api-0.42.0+1.16.pom' | Select-Object -First 1 -ExpandProperty FullName
$aggregateJar = Get-ChildItem -LiteralPath $apiRoot -Recurse -Filter 'fabric-api-0.42.0+1.16.jar' | Select-Object -First 1 -ExpandProperty FullName
[xml] $pom = Get-Content -Raw -LiteralPath $apiPom
$namespace = New-Object Xml.XmlNamespaceManager($pom.NameTable)
$namespace.AddNamespace('m', 'http://maven.apache.org/POM/4.0.0')
$apiArtifacts = @($aggregateJar)
foreach ($dependency in $pom.SelectNodes('//m:dependencies/m:dependency', $namespace)) {
    if ([string] $dependency.groupId -ne 'net.fabricmc.fabric-api') {
        continue
    }
    $artifact = [string] $dependency.artifactId
    $version = [string] $dependency.version
    $artifactRoot = Join-Path $moduleCache ("net.fabricmc.fabric-api\{0}\{1}" -f $artifact, $version)
    $jar = Get-ChildItem -LiteralPath $artifactRoot -Recurse -Filter ("{0}-{1}.jar" -f $artifact, $version) |
        Where-Object { $_.Name -notlike '*-sources.jar' } |
        Select-Object -First 1 -ExpandProperty FullName
    $apiArtifacts += $jar
}
$apiArtifacts = @($apiArtifacts | Sort-Object -Unique)

foreach ($modsRoot in @((Join-Path $serverRoot 'mods'), (Join-Path $clientRoot 'mods'))) {
    Get-ChildItem -LiteralPath $modsRoot -Filter '*.jar' -File -ErrorAction SilentlyContinue | Remove-Item -Force
    Copy-Item -LiteralPath $modJar -Destination (Join-Path $modsRoot (Split-Path -Leaf $modJar))
    foreach ($apiJar in $apiArtifacts) {
        Copy-Item -LiteralPath $apiJar -Destination (Join-Path $modsRoot (Split-Path -Leaf $apiJar))
    }
}

$clientJarDestination = Join-Path $clientRoot 'versions\1.16.5\1.16.5.jar'
Copy-Verified (Join-Path $minecraftCache 'minecraft-client.jar') $clientJarDestination $minecraftInfo.downloads.client.sha1
Copy-Item -LiteralPath $minecraftInfoPath -Destination (Join-Path $clientRoot 'versions\1.16.5\1.16.5.json') -Force

$classpath = New-Object Collections.Generic.List[string]
foreach ($library in $minecraftInfo.libraries) {
    if (-not (Test-WindowsRule @($library.rules))) {
        continue
    }
    if ($null -ne $library.downloads.artifact) {
        $artifact = $library.downloads.artifact
        $destination = Join-Path $clientRoot ("libraries\{0}" -f $artifact.path.Replace('/', '\'))
        Get-OrDownload $artifact.url $destination $artifact.sha1
        if (-not $classpath.Contains($destination)) {
            $classpath.Add($destination)
        }
    }
    if ($null -ne $library.natives -and $null -ne $library.natives.windows) {
        $classifierName = [string] $library.natives.windows
        $classifier = $library.downloads.classifiers.$classifierName
        $nativeJar = Join-Path $clientRoot ("libraries\{0}" -f $classifier.path.Replace('/', '\'))
        Get-OrDownload $classifier.url $nativeJar $classifier.sha1
        $nativeExtractRoot = Join-Path $clientRoot 'natives'
        New-Item -ItemType Directory -Path $nativeExtractRoot -Force | Out-Null
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [IO.Compression.ZipFile]::OpenRead($nativeJar)
        try {
            foreach ($entry in $archive.Entries) {
                if ($entry.FullName.EndsWith('/') -or $entry.FullName.StartsWith('META-INF/')) {
                    continue
                }
                $destination = Join-Path $nativeExtractRoot $entry.FullName
                New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destination, $true)
            }
        }
        finally {
            $archive.Dispose()
        }
    }
}

$fabricVersionJson = Join-Path $clientRoot 'versions\fabric-loader-0.15.11-1.16.5\fabric-loader-0.15.11-1.16.5.json'
Assert-File $fabricVersionJson
$fabricVersion = Get-Content -Raw -LiteralPath $fabricVersionJson | ConvertFrom-Json
foreach ($library in $fabricVersion.libraries) {
    $relativePath = Get-MavenPath $library.name
    $path = Join-Path $clientRoot ("libraries\{0}" -f $relativePath)
    Assert-File $path
    if (-not $classpath.Contains($path)) {
        $classpath.Add($path)
    }
}
$classpath.Add($clientJarDestination)
Set-Content -LiteralPath (Join-Path $clientRoot 'classpath.txt') -Value @($classpath) -Encoding ASCII

$clientAssetIndex = Join-Path $clientRoot 'assets\indexes\1.16.json'
Copy-Verified $assetIndexCache $clientAssetIndex $minecraftInfo.assetIndex.sha1
$assetIndex = Get-Content -Raw -LiteralPath $assetIndexCache | ConvertFrom-Json
foreach ($asset in $assetIndex.objects.psobject.Properties.Value) {
    $hash = [string] $asset.hash
    $source = Join-Path $assetCache ("objects\{0}\{1}" -f $hash.Substring(0, 2), $hash)
    $destination = Join-Path $clientRoot ("assets\objects\{0}\{1}" -f $hash.Substring(0, 2), $hash)
    Copy-Verified $source $destination $hash
}

$loggingDestination = Join-Path $clientRoot 'assets\log_configs\client-1.12.xml'
Get-OrDownload $minecraftInfo.logging.client.file.url $loggingDestination $minecraftInfo.logging.client.file.sha1

$result = [ordered]@{
    schema_version = '1.0'
    runtime_baseline_version = 'person-c-c1-runtime-baseline-v0.2'
    source_commit = $SourceCommit
    minecraft_version = '1.16.5'
    fabric_loader_version = '0.15.11'
    fabric_api_version = '0.42.0+1.16'
    java_executable = $JavaExe
    server_root = $serverRoot
    client_root = $clientRoot
    server_mod_count = @(Get-ChildItem -LiteralPath (Join-Path $serverRoot 'mods') -Filter '*.jar' -File).Count
    client_mod_count = @(Get-ChildItem -LiteralPath (Join-Path $clientRoot 'mods') -Filter '*.jar' -File).Count
    client_classpath_count = $classpath.Count
    client_asset_object_count = @($assetIndex.objects.psobject.Properties).Count
    completed_utc = [DateTime]::UtcNow.ToString('o')
}
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $RuntimeRoot 'provisioning-receipt.json') -Encoding UTF8
$result | ConvertTo-Json -Depth 6
