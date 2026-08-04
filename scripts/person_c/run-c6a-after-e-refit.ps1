[CmdletBinding()]
param(
    [string]$Manifest = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A\docs\status\person_c_c6a_capture_manifest_v0_2\c6a_capture_manifest.json',
    [string]$RepositoryRoot = 'C:\Users\lollo\MineOcclude-Person-C-C1-C6A',
    [string]$ServerRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server',
    [string]$ClientRoot = 'C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client',
    [string]$JavaExe = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe',
    [switch]$ExecuteScientificCapture
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$geometryVersion = 'person-c-layout-config-v0.4'
$geometrySha256 = '34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d'
$handoffBundleSha256 = 'c6e6bc0da867ffafd938bcae6a381a4def692b76157f14e80dd69ae4463dbc28'
$eRoot = Join-Path $RepositoryRoot 'data\handoff_e\person_e_v0_4_homography_refit_v0_1'
$closurePath = Join-Path $RepositoryRoot 'docs\status\person_c_c1_closure_v0_1\c1_closure_status.json'
$handoffInventoryPath = Join-Path $RepositoryRoot 'docs\status\person_c_to_person_e_homography_refit_v0_1\sha256_inventory.json'
$handoffPath = Join-Path $RepositoryRoot 'docs\status\person_c_to_person_e_homography_refit_v0_1\refit_input_authority.json'
$inputPath = Join-Path $eRoot 'homography_input.json'
$reportPath = Join-Path $eRoot 'homography_report.json'
$receiptPath = Join-Path $eRoot 'validation_receipt.json'
$inventoryPath = Join-Path $eRoot 'sha256_inventory.json'
$captureScript = Join-Path $RepositoryRoot 'scripts\person_c\run-c6a-capture.ps1'

function Require([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

Require $ExecuteScientificCapture 'C6A is fail-closed. Pass -ExecuteScientificCapture only after Person E commits the complete v0.4 refit package.'
foreach ($path in @($Manifest, $closurePath, $handoffInventoryPath, $handoffPath, $inputPath, $reportPath, $receiptPath, $inventoryPath, $captureScript)) {
    Require (Test-Path -LiteralPath $path -PathType Leaf) "C6A remains blocked by missing Person E refit/authority file: $path"
}

$closure = Get-Content -Raw -LiteralPath $closurePath | ConvertFrom-Json
Require ($closure.status -eq 'PASS') 'Person C C1 closure status is not PASS.'
Require ($closure.c1_1_complete -and $closure.c1_3_complete -and $closure.c1_5_first_operator_complete -and $closure.c1_5_second_operator_complete -and $closure.c1_5_complete -and $closure.person_c_c1_stop_gate_closed) 'Person C C1 stop gate is not fully closed.'
Require ($closure.accepted_geometry_version -eq $geometryVersion -and $closure.accepted_geometry_sha256 -eq $geometrySha256) 'Person C closure geometry identity mismatch.'

$handoffInventory = Get-Content -Raw -LiteralPath $handoffInventoryPath | ConvertFrom-Json
Require ($handoffInventory.package_bundle_sha256 -eq $handoffBundleSha256) 'Person C to Person E handoff bundle hash mismatch.'
$handoff = Get-Content -Raw -LiteralPath $handoffPath | ConvertFrom-Json
Require ($handoff.e_homography_refit_required -eq $true -and $handoff.accepted_geometry_version -eq $geometryVersion -and $handoff.accepted_geometry_sha256 -eq $geometrySha256) 'Person E handoff geometry/refit authority mismatch.'

$receipt = Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json
$report = Get-Content -Raw -LiteralPath $reportPath | ConvertFrom-Json
$input = Get-Content -Raw -LiteralPath $inputPath | ConvertFrom-Json
$eInventory = Get-Content -Raw -LiteralPath $inventoryPath | ConvertFrom-Json
Require ($receipt.schema_version -eq 'person-e-person-c-v0.4-homography-refit-validation-v0.1') 'Unknown Person E validation receipt schema.'
Require ($receipt.status -eq 'PASS' -and $receipt.owner -eq 'Person E') 'Person E validation receipt is not an E-owned PASS.'
Require ($receipt.source_commit -match '^[0-9a-f]{40}$') 'Person E validation source_commit is not a full Git hash.'
Require ($receipt.accepted_geometry_version -eq $geometryVersion -and $receipt.accepted_geometry_sha256 -eq $geometrySha256) 'Person E validation geometry identity mismatch.'
Require ($receipt.person_c_handoff_bundle_sha256 -eq $handoffBundleSha256) 'Person E validation does not bind the exact Person C handoff.'
Require ($receipt.homography_input_sha256 -eq (Get-Sha256 $inputPath)) 'Person E input hash binding mismatch.'
Require ($receipt.homography_report_sha256 -eq (Get-Sha256 $reportPath)) 'Person E report hash binding mismatch.'
Require ($receipt.layout_count -eq 6 -and $receipt.all_layouts_planning_gate_passed -eq $true -and $receipt.no_hidden_offsets_or_compatibility_adapters -eq $true) 'Person E validation receipt did not pass all six layouts without adapters.'
Require ($input.homography_input_schema_version -eq 'person-e-homography-input-v0.1' -and $input.layouts.Count -eq 6) 'Person E homography input schema/layout count mismatch.'
Require ($report.homography_report_schema_version -eq 'person-e-homography-report-v0.2' -and $report.layouts.Count -eq 6) 'Person E homography report schema/layout count mismatch.'
Require ($report.code_sha -match '^[0-9a-f]{40}$') 'Person E report code_sha is not a full Git hash.'
Require ($report.config_hash -eq 'da05329029cb7119f0c48cfed12657d1a2e4ae6b7d0cb6dcd3b8353292b95a56') 'Person E config hash mismatch.'
Require ($report.algorithm_version -eq 'four_point_projective_gauss_jordan_v0.1') 'Person E homography algorithm version mismatch.'
Require ([double]$report.singular_pivot_tolerance -eq 1e-12 -and [double]$report.maximum_median_wall_parallel_error_blocks -eq 0.2 -and [double]$report.maximum_p95_wall_parallel_error_blocks -eq 0.5 -and [double]$report.minimum_shift_error_multiplier_on_gate_failure -eq 2.0) 'Person E validation tolerances changed.'

$expectedIds = @(1..6 | ForEach-Object { 'layout_{0:D2}' -f $_ })
$actualIds = @($report.layouts | ForEach-Object { $_.layout_id } | Sort-Object)
Require (($actualIds -join ',') -eq ($expectedIds -join ',')) 'Person E report does not contain exactly layout_01 through layout_06.'
$inputIds = @($input.layouts | ForEach-Object { $_.layout_id } | Sort-Object)
Require (($inputIds -join ',') -eq ($expectedIds -join ',')) 'Person E input does not contain exactly layout_01 through layout_06.'
$receiptIds = @($receipt.layout_ids | Sort-Object)
Require (($receiptIds -join ',') -eq ($expectedIds -join ',')) 'Person E validation receipt layout IDs mismatch.'
Require ($receipt.per_layout.Count -eq 6) 'Person E validation receipt requires six per-layout rows.'
Require ($eInventory.schema_version -eq 'person-e-v0.4-homography-refit-sha256-inventory-v0.1') 'Unknown Person E SHA-256 inventory schema.'
$expectedInventoryPaths = @(
    'data/handoff_e/person_e_v0_4_homography_refit_v0_1/homography_input.json',
    'data/handoff_e/person_e_v0_4_homography_refit_v0_1/homography_report.json',
    'data/handoff_e/person_e_v0_4_homography_refit_v0_1/validation_receipt.json'
)
Require ($eInventory.files.Count -eq 3) 'Person E SHA-256 inventory must list exactly input, report, and validation receipt.'
foreach ($expectedPath in $expectedInventoryPaths) {
    $row = @($eInventory.files | Where-Object { $_.path -eq $expectedPath })
    Require ($row.Count -eq 1) "Person E SHA-256 inventory path missing or duplicated: $expectedPath"
    $diskPath = Join-Path $RepositoryRoot ($expectedPath -replace '/', '\')
    Require ([int64]$row[0].size_bytes -eq (Get-Item -LiteralPath $diskPath).Length -and $row[0].sha256 -eq (Get-Sha256 $diskPath)) "Person E SHA-256 inventory binding mismatch: $expectedPath"
}

foreach ($layout in $report.layouts) {
    $authority = @($handoff.layouts | Where-Object { $_.layout_id -eq $layout.layout_id })
    Require ($authority.Count -eq 1) "Missing unique Person C handoff layout: $($layout.layout_id)"
    $authority = $authority[0]
    $inputLayout = @($input.layouts | Where-Object { $_.layout_id -eq $layout.layout_id })
    Require ($inputLayout.Count -eq 1) "Missing unique Person E input layout: $($layout.layout_id)"
    $inputLayout = $inputLayout[0]
    Require ($inputLayout.canonical_camera_pose_id -eq $authority.canonical_camera_pose_id) "Input camera pose mismatch: $($layout.layout_id)"
    Require ($inputLayout.marker_set_source_hash -eq $authority.marker_set_source_hash) "Input marker-set source hash mismatch: $($layout.layout_id)"
    Require (($inputLayout.marker_ids -join ',') -eq ($authority.marker_order -join ',')) "Input marker order mismatch: $($layout.layout_id)"
    Require (($inputLayout.wall_parallel_origin_xz | ConvertTo-Json -Compress) -eq ($authority.wall_parallel_origin_xz | ConvertTo-Json -Compress)) "Input wall-parallel origin mismatch: $($layout.layout_id)"
    Require (($inputLayout.wall_parallel_positive_unit_xz | ConvertTo-Json -Compress) -eq ($authority.wall_parallel_positive_unit_xz | ConvertTo-Json -Compress)) "Input wall-axis convention mismatch: $($layout.layout_id)"
    foreach ($marker in $authority.markers) {
        $inputWorldPoint = $inputLayout.world_points_by_marker.PSObject.Properties[$marker.marker_id].Value
        Require ($null -ne $inputWorldPoint -and ($inputWorldPoint | ConvertTo-Json -Compress) -eq ($marker.world_xz_blocks | ConvertTo-Json -Compress)) "Input literal marker world point mismatch: $($layout.layout_id) $($marker.marker_id)"
        $inputImagePoint = $inputLayout.image_points_by_marker.PSObject.Properties[$marker.marker_id].Value
        Require ($null -ne $inputImagePoint -and $inputImagePoint.Count -eq 2) "Input marker image point missing or malformed: $($layout.layout_id) $($marker.marker_id)"
    }
    Require ($layout.canonical_camera_pose_id -eq $authority.canonical_camera_pose_id) "Camera pose mismatch: $($layout.layout_id)"
    Require ($layout.marker_set_source_hash -eq $authority.marker_set_source_hash) "Marker-set source hash mismatch: $($layout.layout_id)"
    Require ($layout.validation_source_hash -eq $inputLayout.validation_source_hash) "Validation-source hash mismatch: $($layout.layout_id)"
    Require (($layout.wall_parallel_origin_xz | ConvertTo-Json -Compress) -eq ($authority.wall_parallel_origin_xz | ConvertTo-Json -Compress)) "Report wall-parallel origin mismatch: $($layout.layout_id)"
    Require (($layout.wall_parallel_positive_unit_xz | ConvertTo-Json -Compress) -eq ($authority.wall_parallel_positive_unit_xz | ConvertTo-Json -Compress)) "Report wall-axis convention mismatch: $($layout.layout_id)"
    Require ($layout.homography.layout_id -eq $layout.layout_id -and $layout.homography.canonical_camera_pose_id -eq $authority.canonical_camera_pose_id) "Homography identity mismatch: $($layout.layout_id)"
    Require ($layout.homography.algorithm_version -eq 'four_point_projective_gauss_jordan_v0.1' -and $layout.homography.image_coordinate_convention -eq 'pixel_center_xy_zero_based' -and $layout.homography.world_coordinate_convention -eq 'ground_plane_world_xz_blocks') "Homography convention mismatch: $($layout.layout_id)"
    Require (($layout.homography.marker_ids -join ',') -eq ($authority.marker_order -join ',')) "Homography marker order mismatch: $($layout.layout_id)"
    Require ($layout.homography.matrix.Count -eq 3 -and @($layout.homography.matrix | Where-Object { $_.Count -ne 3 }).Count -eq 0) "Homography matrix is not 3x3: $($layout.layout_id)"
    $heldout = $layout.heldout_localization
    Require ($heldout.planning_gate_passed -eq $true) "Held-out gate failed: $($layout.layout_id)"
    Require ([double]$heldout.median_absolute_wall_parallel_error_blocks -le 0.2) "Median error exceeds 0.2 blocks: $($layout.layout_id)"
    Require ([double]$heldout.p95_absolute_wall_parallel_error_blocks -lt 0.5) "P95 error is not below 0.5 blocks: $($layout.layout_id)"
    $receiptRow = @($receipt.per_layout | Where-Object { $_.layout_id -eq $layout.layout_id })
    Require ($receiptRow.Count -eq 1 -and $receiptRow[0].planning_gate_passed -eq $true) "Person E per-layout validation receipt failed: $($layout.layout_id)"
}

& $captureScript -Manifest $Manifest -RepositoryRoot $RepositoryRoot -ServerRoot $ServerRoot -ClientRoot $ClientRoot -JavaExe $JavaExe -ExecuteScientificCapture
if ($LASTEXITCODE -ne 0) { throw "C6A capture script failed with exit code $LASTEXITCODE" }
