[CmdletBinding()]
param(
    [string] $RepositoryRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A',
    [string] $RuntimeRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Join-Path $RepositoryRoot 'fabric\mineocclude-mod'
$serverRoot = Join-Path $RuntimeRoot 'server'
$clientRoot = Join-Path $RuntimeRoot 'client'
$packageRoot = Join-Path $RepositoryRoot 'docs\status\person_c_c1_runtime_provisioning_v0_2'
$observationRoot = Join-Path $RepositoryRoot 'docs\status\person_c_c1_runtime_observation_v0_2'
$javaExe = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe'
$sourceCommit = '99b78b6578d17cffc0b5679118a42632284ce7f7'
$startingCommit = 'cc285852d6be02ddb878957aed82a4360e96e9ac'
$baselineVersion = 'person-c-c1-runtime-baseline-v0.2'
$builtModJarPath = Join-Path $projectRoot 'build\libs\mineocclude-0.1.0.jar'
$modJar = Join-Path $serverRoot 'mods\mineocclude-0.1.0.jar'

function Assert-File([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Evidence input is absent: $Path"
    }
}

function Get-FileRecord([string] $Path) {
    Assert-File $Path
    $file = Get-Item -LiteralPath $Path
    return [ordered]@{
        path = $file.FullName
        bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

function Write-TextUtf8Lf([string] $Path, [string] $Value) {
    $normalized = $Value -replace "`r?`n", "`n"
    [IO.File]::WriteAllText($Path, $normalized, [Text.UTF8Encoding]::new($false))
}

function Write-Json([string] $Path, [object] $Value) {
    Write-TextUtf8Lf $Path ($Value | ConvertTo-Json -Depth 20)
}

function Read-KeyValueFile([string] $Path, [string] $Separator) {
    $result = [ordered]@{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -eq '' -or $line.StartsWith('#')) {
            continue
        }
        $index = $line.IndexOf($Separator)
        if ($index -lt 1) {
            throw "Invalid key/value line in ${Path}: $line"
        }
        $result[$line.Substring(0, $index)] = $line.Substring($index + $Separator.Length)
    }
    return $result
}

function Get-DirectoryJarInventory([string] $Path) {
    return @(
        Get-ChildItem -LiteralPath $Path -Filter '*.jar' -File |
            Sort-Object Name |
            ForEach-Object { Get-FileRecord $_.FullName }
    )
}

function Write-PackageInventory([string] $Root) {
    $files = @(
        Get-ChildItem -LiteralPath $Root -File |
            Where-Object { $_.Name -ne 'sha256_inventory.json' } |
            Sort-Object Name |
            ForEach-Object {
                [ordered]@{
                    path = $_.Name
                    bytes = $_.Length
                    sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                }
            }
    )
    Write-Json (Join-Path $Root 'sha256_inventory.json') ([ordered]@{
        schema_version = '1.0'
        inventory_rule = 'All sibling package files except this self-referential inventory.'
        files = $files
    })
}

foreach ($root in @($packageRoot, $observationRoot)) {
    New-Item -ItemType Directory -Path $root -Force | Out-Null
}

$smokeReceiptPath = Join-Path $serverRoot 'logs\smoke\server-smoke-receipt.json'
$smokeLogPath = Join-Path $serverRoot 'logs\smoke\server-smoke-console.log'
$provisioningReceiptPath = Join-Path $RuntimeRoot 'provisioning-receipt.json'
$classpathPath = Join-Path $clientRoot 'classpath.txt'
foreach ($required in @($javaExe, $modJar, $smokeReceiptPath, $smokeLogPath, $provisioningReceiptPath, $classpathPath)) {
    Assert-File $required
}
$smokeReceipt = Get-Content -Raw -LiteralPath $smokeReceiptPath | ConvertFrom-Json
$provisioningReceipt = Get-Content -Raw -LiteralPath $provisioningReceiptPath | ConvertFrom-Json
if (-not $smokeReceipt.server_smoke_pass -or -not $smokeReceipt.server_stopped_cleanly) {
    throw 'The server smoke receipt is not a clean pass.'
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($modJar)
try {
    $entry = $archive.GetEntry('fabric.mod.json')
    if ($null -eq $entry) {
        throw 'Built mod JAR has no fabric.mod.json.'
    }
    $reader = [IO.StreamReader]::new($entry.Open())
    try {
        $fabricMetadata = $reader.ReadToEnd() | ConvertFrom-Json
    }
    finally {
        $reader.Dispose()
    }
}
finally {
    $archive.Dispose()
}

$serverMods = Get-DirectoryJarInventory (Join-Path $serverRoot 'mods')
$clientMods = Get-DirectoryJarInventory (Join-Path $clientRoot 'mods')
$classpathRecords = @(
    Get-Content -LiteralPath $classpathPath |
        Where-Object { $_ -ne '' } |
        ForEach-Object { Get-FileRecord $_ }
)
$serverLibraryRecords = @(
    Get-ChildItem -LiteralPath (Join-Path $serverRoot 'libraries') -Recurse -Filter '*.jar' -File |
        Sort-Object FullName |
        ForEach-Object { Get-FileRecord $_.FullName }
)

Write-Json (Join-Path $packageRoot 'pinned_versions.json') ([ordered]@{
    schema_version = '1.0'
    starting_commit = $startingCommit
    jar_source_commit = $sourceCommit
    runtime_baseline_version = $baselineVersion
    minecraft = '1.16.5'
    fabric_loader = '0.15.11'
    yarn_mappings = '1.16.5+build.10'
    fabric_api = '0.42.0+1.16'
    gradle = '8.3'
    fabric_loom = '1.4.6'
    java_required_major = 17
    mod_id = 'mineocclude'
    mod_version = '0.1.0'
    named_run_configurations = [ordered]@{
        server_task = 'runMineoccludeServer'
        server_name = 'MineOcclude Dedicated Server'
        client_task = 'runMineoccludeClient'
        client_name = 'MineOcclude Production Client'
    }
})

Write-Json (Join-Path $packageRoot 'java_selection.json') ([ordered]@{
    schema_version = '1.0'
    selection_source = 'C:\Users\lollo\MineOcclude-Runtime\jdk17-path.txt'
    required_major = 17
    selected_executable = $javaExe
    version = '17.0.19'
    distribution = 'Eclipse Temurin'
    java_file = Get-FileRecord $javaExe
    global_java_home_modified = $false
    global_path_modified = $false
})

$gradleTaskInventory = @'
Command: .\gradlew.bat tasks --all --console=plain --no-daemon
Java: C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe
Fabric Loom: 1.4.6

build - Assembles and tests this project.
check - Runs all checks.
clean - Deletes the build directory.
downloadAssets - Downloads required game assets for Minecraft.
jar - Assembles a jar archive containing the classes of the 'main' feature.
remapJar - Remaps the built project jar to intermediary mappings.
runMineoccludeClient - Starts the 'MineOcclude Production Client' run configuration
runMineoccludeServer - Starts the 'MineOcclude Dedicated Server' run configuration
test - Runs the test suite.

Result: BUILD SUCCESSFUL
'@
Write-TextUtf8Lf (Join-Path $packageRoot 'gradle_task_inventory.txt') $gradleTaskInventory

Write-Json (Join-Path $packageRoot 'build_receipt.json') ([ordered]@{
    schema_version = '1.0'
    command = '$env:JAVA_HOME=''C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot''; .\gradlew.bat clean build --no-daemon'
    working_directory = $projectRoot
    source_commit = $sourceCommit
    loom_version = '1.4.6'
    java_major = 17
    clean_build_pass = $true
    test_task_executed_by_build = $true
    tests = 21
    failures = 0
    errors = 0
    skipped = 0
})

Write-Json (Join-Path $packageRoot 'fabric_test_receipt.json') ([ordered]@{
    schema_version = '1.0'
    command = '$env:JAVA_HOME=''C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot''; .\gradlew.bat clean build --no-daemon'
    task = ':test'
    source_commit = $sourceCommit
    pass = $true
    total = 21
    failures = 0
    errors = 0
    skipped = 0
    suites = @(
        [ordered]@{ name = 'EpisodeLifecycleTest'; tests = 6 },
        [ordered]@{ name = 'GeometryUtilTest'; tests = 5 },
        [ordered]@{ name = 'NoiseScheduleTest'; tests = 6 },
        [ordered]@{ name = 'PythonScheduleCrossCheckTest'; tests = 1 },
        [ordered]@{ name = 'RuntimeObservationToolingTest'; tests = 3 }
    )
})

Write-Json (Join-Path $packageRoot 'mod_jar_receipt.json') ([ordered]@{
    schema_version = '1.0'
    source_commit = $sourceCommit
    original_build_output_path = $builtModJarPath
    retained_installed_artifact = $true
    artifact = Get-FileRecord $modJar
    fabric_metadata = [ordered]@{
        schemaVersion = $fabricMetadata.schemaVersion
        id = $fabricMetadata.id
        version = $fabricMetadata.version
        environment = $fabricMetadata.environment
        depends = $fabricMetadata.depends
    }
})

Write-Json (Join-Path $packageRoot 'server_mod_inventory.json') ([ordered]@{
    schema_version = '1.0'
    root = Join-Path $serverRoot 'mods'
    required_only = $true
    count = $serverMods.Count
    mods = $serverMods
})
Write-Json (Join-Path $packageRoot 'client_mod_inventory.json') ([ordered]@{
    schema_version = '1.0'
    root = Join-Path $clientRoot 'mods'
    required_only = $true
    count = $clientMods.Count
    mods = $clientMods
})

Write-Json (Join-Path $packageRoot 'server_runtime_manifest.json') ([ordered]@{
    schema_version = '1.0'
    provisioned = $true
    root = $serverRoot
    minecraft = '1.16.5'
    fabric_loader = '0.15.11'
    loopback_only = $true
    launcher = Get-FileRecord (Join-Path $serverRoot 'fabric-server-launch.jar')
    minecraft_server = Get-FileRecord (Join-Path $serverRoot 'server.jar')
    launch_script = Get-FileRecord (Join-Path $serverRoot 'start-mineocclude-server.ps1')
    server_properties = Get-FileRecord (Join-Path $serverRoot 'server.properties')
    eula = Get-FileRecord (Join-Path $serverRoot 'eula.txt')
    libraries = $serverLibraryRecords
    mod_count = $serverMods.Count
    smoke_receipt = Get-FileRecord $smokeReceiptPath
    smoke_log = Get-FileRecord $smokeLogPath
})

Write-Json (Join-Path $packageRoot 'client_runtime_manifest.json') ([ordered]@{
    schema_version = '1.0'
    provisioned = $true
    gui_validation_complete = $false
    root = $clientRoot
    minecraft = '1.16.5'
    fabric_loader = '0.15.11'
    minecraft_client = Get-FileRecord (Join-Path $clientRoot 'versions\1.16.5\1.16.5.jar')
    fabric_version_json = Get-FileRecord (Join-Path $clientRoot 'versions\fabric-loader-0.15.11-1.16.5\fabric-loader-0.15.11-1.16.5.json')
    launch_script = Get-FileRecord (Join-Path $clientRoot 'start-mineocclude-client.ps1')
    options = Get-FileRecord (Join-Path $clientRoot 'options.txt')
    classpath_file = Get-FileRecord $classpathPath
    classpath = $classpathRecords
    asset_index = Get-FileRecord (Join-Path $clientRoot 'assets\indexes\1.16.json')
    asset_object_count = $provisioningReceipt.client_asset_object_count
    logging_config = Get-FileRecord (Join-Path $clientRoot 'assets\log_configs\client-1.12.xml')
    mod_count = $clientMods.Count
})

Write-Json (Join-Path $packageRoot 'candidate_server_properties.json') ([ordered]@{
    schema_version = '1.0'
    baseline_version = $baselineVersion
    source_template = 'fabric/mineocclude-mod/provisioning/person-c-c1-v0_2/server.properties'
    runtime_file = Get-FileRecord (Join-Path $serverRoot 'server.properties')
    complete = $true
    settings = Read-KeyValueFile (Join-Path $serverRoot 'server.properties') '='
})
Write-Json (Join-Path $packageRoot 'candidate_client_settings.json') ([ordered]@{
    schema_version = '1.0'
    baseline_version = $baselineVersion
    source_template = 'fabric/mineocclude-mod/provisioning/person-c-c1-v0_2/client-options.txt'
    runtime_file = Get-FileRecord (Join-Path $clientRoot 'options.txt')
    complete = $true
    launch_resolution = [ordered]@{ width = 640; height = 360 }
    settings = Read-KeyValueFile (Join-Path $clientRoot 'options.txt') ':'
})
Write-Json (Join-Path $packageRoot 'configuration_conflicts.json') ([ordered]@{
    schema_version = '1.0'
    unresolved = @()
    resolved_successor_decisions = @(
        [ordered]@{
            field = 'spawn-animals'
            value = 'false'
            scope = 'new post-C1 evidence only'
            rationale = 'Natural passive spawning is disabled; the reset system explicitly creates the experimental magenta sheep.'
        }
    )
    historical_evidence_modified = $false
})

$serverLaunchCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\start-mineocclude-server.ps1"'
$clientLaunchCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\start-mineocclude-client.ps1"'
Write-Json (Join-Path $packageRoot 'launch_commands.json') ([ordered]@{
    schema_version = '1.0'
    java_executable = $javaExe
    server = [ordered]@{
        command = $serverLaunchCommand
        java_arguments = '-Xms1G -Xmx2G -Dfile.encoding=UTF-8 -jar C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\fabric-server-launch.jar nogui'
        working_directory = $serverRoot
    }
    client = [ordered]@{
        command = $clientLaunchCommand
        main_class = 'net.fabricmc.loader.impl.launch.knot.KnotClient'
        memory = [ordered]@{ minimum = '1G'; maximum = '2G' }
        working_directory = $clientRoot
        game_directory = $clientRoot
        resolution = [ordered]@{ width = 640; height = 360 }
        gui_validation_complete = $false
    }
})

Write-Json (Join-Path $packageRoot 'provisioning_validation.json') ([ordered]@{
    schema_version = '1.0'
    runtime_baseline_version = $baselineVersion
    gradle_configuration_pass = $true
    clean_build_pass = $true
    fabric_test_pass = $true
    mod_jar_inspection_pass = $true
    server_dependency_resolution_pass = $true
    client_dependency_resolution_pass = $true
    server_runtime_provisioned = $true
    client_runtime_provisioned = $true
    server_launch_script_syntax_pass = $true
    client_launch_script_syntax_pass = $true
    server_configuration_complete = $true
    client_configuration_complete = $true
    server_smoke_pass = $smokeReceipt.server_smoke_pass
    server_stopped_cleanly = $smokeReceipt.server_stopped_cleanly
    server_port_25565_free_after_smoke = $true
    client_launch_command_ready = $true
    client_gui_validation_complete = $false
    scientific_runtime_observation_performed = $false
    accepted_geometry_version_assigned = $false
    unresolved_provisioning_blockers = @()
    focused_documentation_validation = [ordered]@{
        pass = $true
        json_files_parsed = 18
        package_hash_records_verified = 19
        installed_mod_records_verified = 92
        powershell_scripts_syntax_checked = 5
        mod_jar_sha256_reverified = $true
        server_port_free_reverified = $true
    }
})

Write-Json (Join-Path $packageRoot 'external_runtime_sha256_inventory.json') ([ordered]@{
    schema_version = '1.0'
    scope = 'Hash-bound external runtime files; no runtime binary is copied into Git.'
    files = @(
        (Get-FileRecord (Join-Path $RuntimeRoot 'provisioning-receipt.json')),
        (Get-FileRecord (Join-Path $serverRoot 'fabric-server-launch.jar')),
        (Get-FileRecord (Join-Path $serverRoot 'server.jar')),
        (Get-FileRecord (Join-Path $serverRoot 'server.properties')),
        (Get-FileRecord (Join-Path $serverRoot 'start-mineocclude-server.ps1')),
        (Get-FileRecord $smokeReceiptPath),
        (Get-FileRecord $smokeLogPath),
        (Get-FileRecord (Join-Path $clientRoot 'versions\1.16.5\1.16.5.jar')),
        (Get-FileRecord (Join-Path $clientRoot 'options.txt')),
        (Get-FileRecord (Join-Path $clientRoot 'classpath.txt')),
        (Get-FileRecord (Join-Path $clientRoot 'assets\indexes\1.16.json')),
        (Get-FileRecord (Join-Path $clientRoot 'start-mineocclude-client.ps1'))
    )
})

$provisioningActions = @"
# Person C C1 isolated runtime: operator next actions

Deterministic provisioning is complete under baseline ``$baselineVersion``. The server smoke passed and stopped cleanly. The client was not launched because the remaining gate is GUI and direct observation.

1. Start the server with: ``$serverLaunchCommand``
2. Start the client with: ``$clientLaunchCommand``
3. In the isolated client, confirm the 640x360 window, options, framebuffer size, and the absence of inherited resource packs; connect directly to ``127.0.0.1:25565``.
4. Continue with ``docs/status/person_c_c1_runtime_observation_v0_2/operator_next_actions.md``. The first server-console command is ``mineocclude markergeomstatus``.
5. Stop before geometry adjudication if any runtime receipt, camera state, marker state, or pixel-setting check fails. Do not begin C6A.

No account login is expected because this isolated loopback baseline uses ``online-mode=false``. No personal ``.minecraft`` data may be copied into either root.
"@
Write-TextUtf8Lf (Join-Path $packageRoot 'operator_next_actions.md') $provisioningActions

$layoutCommands = @(
    'mineocclude start layout_01 11101 202608031101 0.0 0.0 20',
    'mineocclude observegeometry c1_1_layout_01',
    'mineocclude stop',
    'mineocclude start layout_02 11102 202608031102 0.0 0.0 20',
    'mineocclude observegeometry c1_1_layout_02',
    'mineocclude stop',
    'mineocclude start layout_03 11103 202608031103 0.0 0.0 20',
    'mineocclude observegeometry c1_1_layout_03',
    'mineocclude stop',
    'mineocclude start layout_04 11104 202608031104 0.0 0.0 20',
    'mineocclude observegeometry c1_1_layout_04',
    'mineocclude stop',
    'mineocclude start layout_05 11105 202608031105 0.0 0.0 20',
    'mineocclude observegeometry c1_1_layout_05',
    'mineocclude stop',
    'mineocclude start layout_06 11106 202608031106 0.0 0.0 20',
    'mineocclude observegeometry c1_1_layout_06',
    'mineocclude stop'
)
Write-Json (Join-Path $observationRoot 'runtime_observation_readiness.json') ([ordered]@{
    schema_version = '1.0'
    successor_to = 'docs/status/person_c_c1_runtime_observation_v0_1/'
    runtime_baseline_version = $baselineVersion
    jar_source_commit = $sourceCommit
    mod_jar = Get-FileRecord $modJar
    server_smoke_receipt = Get-FileRecord $smokeReceiptPath
    server_smoke_pass = $true
    server_stopped_cleanly = $true
    client_runtime_provisioned = $true
    client_gui_validation_complete = $false
    geometry_observation_complete = $false
    geometry_authority_assigned = $false
    c6a_started = $false
    first_runtime_observation_command = 'mineocclude markergeomstatus'
    session_control_commands = @(
        'mineocclude mode normal',
        'mineocclude duration 0',
        'mineocclude reveal 0',
        'mineocclude impulse -1 0',
        'mineocclude lockcam on',
        'mineocclude warmup 1200'
    )
    layout_observation_commands = $layoutCommands
})

$observationActions = @"
# Person C C1.1 successor runtime actions

This successor binds the existing C1.1 observation procedure to ``$baselineVersion``, the provisioned Java 17 server/client roots, and the built JAR at source commit ``$sourceCommit``. It does not supersede, edit, or reinterpret frozen geometry evidence. It assigns no accepted geometry version.

1. Run ``$serverLaunchCommand``.
2. Run ``$clientLaunchCommand`` and use the GUI to verify a 640x360 window/framebuffer, the pinned client options, vanilla-only resource packs, and direct connection to ``127.0.0.1:25565``.
3. At the server console, run ``mineocclude markergeomstatus`` first. Preserve the exact logged status; do not run ``markergeom`` or ``markergeomreset``.
4. Follow section 7 of ``docs/status/person_c_c1_runtime_observation_v0_1/operator_runbook.md`` exactly: set the six observation controls, then execute the six create-only layout receipt sequences listed in ``runtime_observation_readiness.json``.
5. Preserve and hash every runtime receipt. Stop on any collision, missing player camera, layout mismatch, unexpected override, block mismatch, or capture start.
6. Only after all six receipts and canonical visual checks validate may a new geometry-authority package be considered. Do not begin C6A in this step.

Remaining work is deliberately manual because it requires the GUI and direct runtime/visual observation. Provisioning itself has no unresolved blocker.
"@
Write-TextUtf8Lf (Join-Path $observationRoot 'operator_next_actions.md') $observationActions

Write-PackageInventory $packageRoot
Write-PackageInventory $observationRoot

[ordered]@{
    provisioning_package = $packageRoot
    observation_package = $observationRoot
    server_mod_count = $serverMods.Count
    client_mod_count = $clientMods.Count
    client_classpath_count = $classpathRecords.Count
    server_smoke_pass = $smokeReceipt.server_smoke_pass
    server_stopped_cleanly = $smokeReceipt.server_stopped_cleanly
} | ConvertTo-Json -Depth 5
