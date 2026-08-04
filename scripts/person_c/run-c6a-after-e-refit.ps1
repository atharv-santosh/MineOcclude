[CmdletBinding()]
param(
    [string]$Manifest = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A\docs\status\person_c_c6a_capture_manifest_v0_2\c6a_capture_manifest.json',
    [string]$ScheduleManifest = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A\configs\collection\person_c_c6a_v0_1\schedule_set_manifest.json',
    [string]$Authorization = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A\docs\status\person_c_c6a_e_refit_authorization_v0_1\c6a_execution_authorization.json',
    [string]$PackageManifest = 'C:\Users\lollo\MineOcclude-Person-E-Refit\data\handoff_e\person_e_v0_4_homography_refit_v0_2\package_manifest.json',
    [string]$HandoffPath = 'C:\Users\lollo\MineOcclude-Person-E-Refit\data\handoff_e\person_e_v0_4_homography_refit_v0_2\person_e_to_person_c_refit_handoff.json',
    [string]$PersonERepositoryRoot = 'C:\Users\lollo\MineOcclude-Person-E-Refit',
    [string]$RepositoryRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A',
    [string]$ServerRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server',
    [string]$ClientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client',
    [string]$JavaExe = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe',
    [switch]$PreflightOnly,
    [switch]$ExecuteScientificCapture
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$geometryVersion = 'person-c-layout-config-v0.4'
$geometrySha256 = '34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d'
$personECommit = 'c46d838b5a277e71a39090900f9e8ca814b743a7'
$personESourceCommit = '96457cbae22159b2fe1828e0de12d313710dcdf5'
$packageSha256 = 'f5a90bb97d0f54e754cfa11c971532d8d2e29cbe6ce0151dfeb17faae61a17bc'
$handoffSha256 = '0937dcc6335927a1c724e8e3f1510be94b76ff91e3583c10d59d10ec60fb38ca'
$scheduleManifestSha256 = '1abf0fc1e9f5633e17616a512d0bf84d66e048eef9986427c1908b834945346e'
$scheduleSetSha256 = '79a81668362421fa91cb591d355b655e9b1a60aae088057de7bda977df663806'
$captureManifestSha256 = '174def13f71ad8c2df5615a0ef5ec7fc9e10b431c105fc995dc6508e87c2dc7d'
$executionCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Person-C-C1-C6A\scripts\person_c\run-c6a-after-e-refit.ps1" -ExecuteScientificCapture'
$geometryPath = Join-Path $RepositoryRoot 'configs\scenes\layouts_v0_4.yaml'
$captureScript = Join-Path $RepositoryRoot 'scripts\person_c\run-c6a-capture.ps1'

function Require([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

Require ($PreflightOnly.IsPresent -xor $ExecuteScientificCapture.IsPresent) 'Specify exactly one of -PreflightOnly or -ExecuteScientificCapture.'
foreach ($path in @($Manifest, $ScheduleManifest, $Authorization, $PackageManifest, $HandoffPath, $geometryPath, $captureScript)) {
    Require (Test-Path -LiteralPath $path -PathType Leaf) "C6A authorization file is missing: $path"
}

Require ((Get-Sha256 $PackageManifest) -eq $packageSha256) 'Person E package manifest SHA-256 mismatch.'
Require ((Get-Sha256 $HandoffPath) -eq $handoffSha256) 'Person E-to-C handoff SHA-256 mismatch.'
Require ((Get-Sha256 $ScheduleManifest) -eq $scheduleManifestSha256) 'Person C C6A schedule manifest SHA-256 mismatch.'
Require ((Get-Sha256 $Manifest) -eq $captureManifestSha256) 'Person C C6A capture manifest SHA-256 mismatch.'
Require ((Get-Sha256 $geometryPath) -eq $geometrySha256) 'Accepted geometry file SHA-256 mismatch.'

$personEHead = (& git -C $PersonERepositoryRoot rev-parse HEAD 2>&1 | Out-String).Trim()
Require ($LASTEXITCODE -eq 0 -and $personEHead -eq $personECommit) 'Person E repository HEAD does not match the authorized commit.'

$package = Get-Content -Raw -LiteralPath $PackageManifest | ConvertFrom-Json
$handoffRecord = Get-Content -Raw -LiteralPath $HandoffPath | ConvertFrom-Json
$authorizationRecord = Get-Content -Raw -LiteralPath $Authorization | ConvertFrom-Json
$schedule = Get-Content -Raw -LiteralPath $ScheduleManifest | ConvertFrom-Json
$capture = Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json

Require ($package.schema_version -eq 'person-e-v0.4-homography-refit-package-v0.2') 'Unknown Person E package schema.'
Require ($package.status -eq 'PASS' -and $package.all_tolerances_pass -eq $true -and $package.c6a_execution_authorized -eq $true) 'Person E package does not authorize C6A.'
Require ($package.passing_layout_count -eq 6 -and $package.successor_homography_count -eq 6 -and @($package.failed_layout_ids).Count -eq 0) 'Person E package does not certify six passing homographies.'
Require ($package.accepted_geometry_version -eq $geometryVersion -and $package.accepted_geometry_sha256 -eq $geometrySha256) 'Person E package geometry identity mismatch.'
Require ($package.source_code_commit -eq $personESourceCommit) 'Person E refit source-code commit mismatch.'

Require ($handoffRecord.schema_version -eq 'person-e-to-person-c-v0.4-refit-handoff-v0.2') 'Unknown Person E-to-C handoff schema.'
Require ($handoffRecord.status -eq 'READY_FOR_C6A' -and $handoffRecord.all_tolerances_pass -eq $true -and $handoffRecord.c6a_execution_authorized -eq $true) 'Person E-to-C handoff does not authorize C6A.'
Require ($handoffRecord.successor_homography_count -eq 6 -and @($handoffRecord.blocking_layout_ids).Count -eq 0) 'Person E-to-C handoff contains blockers or the wrong homography count.'
Require ($handoffRecord.accepted_geometry_version -eq $geometryVersion -and $handoffRecord.accepted_geometry_sha256 -eq $geometrySha256) 'Person E-to-C handoff geometry identity mismatch.'
Require ($handoffRecord.source_code_commit -eq $personESourceCommit) 'Person E-to-C handoff source-code commit mismatch.'
Require ($handoffRecord.person_e_refit_package.path -eq $PackageManifest -and $handoffRecord.person_e_refit_package.sha256 -eq $packageSha256) 'Person E-to-C handoff package binding mismatch.'
$expectedLayoutIds = @(1..6 | ForEach-Object { 'layout_{0:D2}' -f $_ })
$handoffLayoutIds = @($handoffRecord.layout_results | ForEach-Object { $_.layout_id } | Sort-Object)
Require (@($handoffRecord.layout_results).Count -eq 6 -and ($handoffLayoutIds -join ',') -eq ($expectedLayoutIds -join ',')) 'Person E-to-C handoff does not contain exactly layout_01 through layout_06.'
Require (@($handoffRecord.layout_results | Where-Object { $_.tolerance_result -ne $true }).Count -eq 0) 'At least one Person E homography tolerance record failed.'

Require ($authorizationRecord.schema_version -eq 'person-c-c6a-e-refit-authorization-v0.1') 'Unknown Person C C6A authorization schema.'
Require ($authorizationRecord.status -eq 'AUTHORIZED' -and $authorizationRecord.c6a_execution_authorized -eq $true -and $authorizationRecord.c6a_executed -eq $false) 'Person C C6A authorization record is not an unexecuted authorization.'
Require (@($authorizationRecord.unresolved_blockers).Count -eq 0) 'Person C C6A authorization record contains blockers.'
Require ($authorizationRecord.person_e.commit -eq $personECommit -and $authorizationRecord.person_e.refit_source_code_commit -eq $personESourceCommit) 'Person C authorization does not bind the expected Person E commits.'
Require ($authorizationRecord.person_e.package.path -eq $PackageManifest -and $authorizationRecord.person_e.package.sha256 -eq $packageSha256) 'Person C authorization package binding mismatch.'
Require ($authorizationRecord.person_e.handoff.path -eq $HandoffPath -and $authorizationRecord.person_e.handoff.sha256 -eq $handoffSha256) 'Person C authorization handoff binding mismatch.'
Require ($authorizationRecord.accepted_geometry.version -eq $geometryVersion -and $authorizationRecord.accepted_geometry.sha256 -eq $geometrySha256) 'Person C authorization geometry binding mismatch.'
Require ($authorizationRecord.c6a_schedule_manifest.path -eq 'configs/collection/person_c_c6a_v0_1/schedule_set_manifest.json' -and $authorizationRecord.c6a_schedule_manifest.sha256 -eq $scheduleManifestSha256 -and $authorizationRecord.c6a_schedule_manifest.schedule_set_sha256 -eq $scheduleSetSha256) 'Person C authorization schedule binding mismatch.'
Require ($authorizationRecord.c6a_capture_manifest.path -eq 'docs/status/person_c_c6a_capture_manifest_v0_2/c6a_capture_manifest.json' -and $authorizationRecord.c6a_capture_manifest.sha256 -eq $captureManifestSha256) 'Person C authorization capture-manifest binding mismatch.'
Require ($authorizationRecord.execution_command -eq $executionCommand) 'Person C authorization execution command mismatch.'

Require ($schedule.schema_version -eq 'person-c-c6a-noise-schedule-set-v0.1' -and $schedule.schedule_version -eq 'person-c-c6a-noise-schedules-v0.1') 'Unknown C6A schedule manifest schema/version.'
Require ($schedule.schedule_count -eq 66 -and @($schedule.schedules).Count -eq 66) 'C6A schedule manifest must contain exactly 66 schedules.'
Require ($schedule.schedule_set_sha256 -eq $scheduleSetSha256) 'C6A schedule-set digest mismatch.'
Require ($schedule.accepted_geometry.version -eq $geometryVersion -and $schedule.accepted_geometry.sha256 -eq $geometrySha256) 'C6A schedule geometry identity mismatch.'

Require ($capture.schema_version -eq 'person-c-c6a-capture-manifest-v0.2' -and $capture.manifest_ready -eq $true) 'C6A capture manifest is not ready or has an unknown schema.'
Require ($capture.execution_authorized_now -eq $false) 'The immutable pre-refit capture manifest authorization state changed unexpectedly.'
Require ($capture.episode_count -eq 66 -and $capture.c6b_episode_count -eq 0 -and @($capture.episodes).Count -eq 66) 'C6A capture manifest episode counts are invalid.'
Require ($capture.schedule_version -eq $schedule.schedule_version -and $capture.schedule_set_sha256 -eq $scheduleSetSha256) 'C6A capture manifest schedule binding mismatch.'
Require ($capture.accepted_geometry.version -eq $geometryVersion -and $capture.accepted_geometry.sha256 -eq $geometrySha256) 'C6A capture manifest geometry identity mismatch.'

foreach ($row in $schedule.schedules) {
    $diskPath = Join-Path $RepositoryRoot ($row.path -replace '/', '\')
    Require (Test-Path -LiteralPath $diskPath -PathType Leaf) "C6A schedule is missing: $($row.path)"
    Require ([int64]$row.size_bytes -eq (Get-Item -LiteralPath $diskPath).Length -and $row.sha256 -eq (Get-Sha256 $diskPath)) "C6A schedule hash/size mismatch: $($row.path)"
    Require (Test-Path -LiteralPath $row.runtime_install.path -PathType Leaf) "Installed C6A schedule is missing: $($row.runtime_install.path)"
    Require ([int64]$row.runtime_install.size_bytes -eq (Get-Item -LiteralPath $row.runtime_install.path).Length -and $row.runtime_install.sha256 -eq (Get-Sha256 $row.runtime_install.path)) "Installed C6A schedule hash/size mismatch: $($row.runtime_install.path)"
    $captureRow = @($capture.episodes | Where-Object { $_.episode_id -eq $row.episode_id })
    Require ($captureRow.Count -eq 1) "C6A capture manifest episode is missing or duplicated: $($row.episode_id)"
    $captureRow = $captureRow[0]
    Require ($captureRow.collection_order -eq ($row.episode_id - 12601) -and $captureRow.seed -eq $row.seed) "C6A capture manifest order/seed mismatch: $($row.episode_id)"
    Require ($captureRow.noise_schedule.path -eq $row.path -and $captureRow.noise_schedule.size_bytes -eq $row.size_bytes -and $captureRow.noise_schedule.sha256 -eq $row.sha256) "C6A capture manifest schedule binding mismatch: $($row.episode_id)"
    Require (-not (Test-Path -LiteralPath $captureRow.expected_output_paths.server) -and -not (Test-Path -LiteralPath $captureRow.expected_output_paths.client)) "C6A output path already exists: $($row.episode_id)"
}

Require (Test-Path -LiteralPath $ServerRoot -PathType Container) 'C6A server root is missing.'
Require (Test-Path -LiteralPath $ClientRoot -PathType Container) 'C6A client root is missing.'
Require (Test-Path -LiteralPath $JavaExe -PathType Leaf) 'Pinned Java executable is missing.'

if ($PreflightOnly) {
    Write-Output 'C6A_AUTHORIZATION_PREFLIGHT_PASS=True'
    Write-Output "C6A_EXECUTION_COMMAND=$executionCommand"
    exit 0
}

& $captureScript -Manifest $Manifest -RepositoryRoot $RepositoryRoot -ServerRoot $ServerRoot -ClientRoot $ClientRoot -JavaExe $JavaExe -ExecuteScientificCapture
if ($LASTEXITCODE -ne 0) { throw "C6A capture script failed with exit code $LASTEXITCODE" }
