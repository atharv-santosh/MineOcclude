Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-ERefitAttempt02Condition {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (-not $Condition) { throw $Message }
}

function Get-ERefitAttempt02ReadOnlySnapshot {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "File is absent: $Path"
    }
    $item = Get-Item -LiteralPath $Path
    $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    $stream = [System.IO.FileStream]::new(
        $item.FullName,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        $share
    )
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $snapshotLength = [int64]$stream.Length
        $snapshotLastWriteUtc = [System.IO.File]::GetLastWriteTimeUtc($item.FullName)
        $remaining = $snapshotLength
        $buffer = [byte[]]::new(65536)
        while ($remaining -gt 0) {
            $wanted = [int][Math]::Min($buffer.Length, $remaining)
            $read = $stream.Read($buffer, 0, $wanted)
            Assert-ERefitAttempt02Condition ($read -gt 0) "Unexpected end of file while hashing: $Path"
            [void]$algorithm.TransformBlock($buffer, 0, $read, $null, 0)
            $remaining -= $read
        }
        [void]$algorithm.TransformFinalBlock([byte[]]::new(0), 0, 0)
        $finalLength = [int64]$stream.Length
        $finalLastWriteUtc = [System.IO.File]::GetLastWriteTimeUtc($item.FullName)
        Assert-ERefitAttempt02Condition (
            $finalLength -eq $snapshotLength -and $finalLastWriteUtc -eq $snapshotLastWriteUtc
        ) "File changed while hashing: $Path"
        return [pscustomobject]@{
            FullName = $item.FullName
            Length = $snapshotLength
            Sha256 = ([BitConverter]::ToString($algorithm.Hash)).Replace('-', '').ToLowerInvariant()
        }
    }
    finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

function Get-ERefitAttempt02Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-ERefitAttempt02ReadOnlySnapshot $Path).Sha256
}

function Get-ERefitAttempt02Identity {
    param([Parameter(Mandatory = $true)][string]$Path)
    $snapshot = Get-ERefitAttempt02ReadOnlySnapshot $Path
    return [ordered]@{
        path = $snapshot.FullName
        size_bytes = [int64]$snapshot.Length
        sha256 = $snapshot.Sha256
    }
}

function Assert-ERefitAttempt02Identity {
    param(
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $path = [string]$Identity.path
    Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $path -PathType Leaf) "$Label is absent: $path"
    $actual = Get-ERefitAttempt02Identity $path
    Assert-ERefitAttempt02Condition (
        $actual.size_bytes -eq [int64]$Identity.size_bytes -and $actual.sha256 -ceq [string]$Identity.sha256
    ) "$Label identity drift: $path"
}

function Get-ERefitAttempt02PngDimensions {
    param([Parameter(Mandatory = $true)][string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $bytes = [byte[]]::new(24)
        $read = $stream.Read($bytes, 0, $bytes.Length)
    }
    finally {
        $stream.Dispose()
    }
    Assert-ERefitAttempt02Condition ($read -eq 24) "PNG is too short: $Path"
    $signature = @(137, 80, 78, 71, 13, 10, 26, 10)
    for ($index = 0; $index -lt $signature.Count; $index++) {
        Assert-ERefitAttempt02Condition ($bytes[$index] -eq $signature[$index]) "Invalid PNG signature: $Path"
    }
    $width = ([int64]$bytes[16] -shl 24) -bor ([int64]$bytes[17] -shl 16) -bor ([int64]$bytes[18] -shl 8) -bor [int64]$bytes[19]
    $height = ([int64]$bytes[20] -shl 24) -bor ([int64]$bytes[21] -shl 16) -bor ([int64]$bytes[22] -shl 8) -bor [int64]$bytes[23]
    return [pscustomobject]@{ Width = $width; Height = $height }
}

function Get-ERefitAttempt02PrefixSha256 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][long]$Length
    )
    $item = Get-Item -LiteralPath $Path
    Assert-ERefitAttempt02Condition ($Length -ge 0 -and $item.Length -ge $Length) "File is shorter than required prefix: $Path"
    $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    $stream = [System.IO.FileStream]::new(
        $item.FullName,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        $share
    )
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $remaining = $Length
        $buffer = [byte[]]::new(65536)
        while ($remaining -gt 0) {
            $wanted = [int][Math]::Min($buffer.Length, $remaining)
            $read = $stream.Read($buffer, 0, $wanted)
            Assert-ERefitAttempt02Condition ($read -gt 0) "Unexpected end of file while hashing prefix: $Path"
            [void]$algorithm.TransformBlock($buffer, 0, $read, $null, 0)
            $remaining -= $read
        }
        [void]$algorithm.TransformFinalBlock([byte[]]::new(0), 0, 0)
        return ([BitConverter]::ToString($algorithm.Hash)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

function Copy-ERefitAttempt02CreateOnly {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    $sourceStream = [System.IO.File]::OpenRead($Source)
    try {
        $destinationStream = [System.IO.File]::Open(
            $Destination,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        try { $sourceStream.CopyTo($destinationStream) }
        finally { $destinationStream.Dispose() }
    }
    finally { $sourceStream.Dispose() }
}

function Write-ERefitAttempt02CreateOnlyJson {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )
    $encoding = [System.Text.UTF8Encoding]::new($false)
    $bytes = $encoding.GetBytes((($Value | ConvertTo-Json -Depth 100) + "`n"))
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    try { $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
}

function Assert-ERefitAttempt02LayoutScreenshotSet {
    param(
        [Parameter(Mandatory = $true)][object[]]$Layouts,
        [Parameter(Mandatory = $true)][string]$PreflightEvidencePath,
        [Parameter()][string]$PreflightSourcePath = ''
    )
    $expectedLayoutIds = @(1..6 | ForEach-Object { 'layout_{0:d2}' -f $_ })
    Assert-ERefitAttempt02Condition ($Layouts.Count -eq 6) 'Attempt 02 requires exactly six layout screenshots'
    $observedLayoutIds = @($Layouts | ForEach-Object { [string]$_.layout_id })
    $layoutIdDifferences = @(Compare-Object $expectedLayoutIds $observedLayoutIds)
    Assert-ERefitAttempt02Condition ($layoutIdDifferences.Count -eq 0) 'Attempt 02 layout screenshot set must contain layout_01 through layout_06 exactly once'
    Assert-ERefitAttempt02Condition (($observedLayoutIds | Select-Object -Unique).Count -eq 6) 'Attempt 02 layout screenshot IDs are not unique'
    Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $PreflightEvidencePath -PathType Leaf) 'Preflight evidence screenshot is absent'
    $preflightItem = Get-Item -LiteralPath $PreflightEvidencePath
    $preflightHash = Get-ERefitAttempt02Sha256 $preflightItem.FullName
    $preflightSourceFullName = if ($PreflightSourcePath -ne '') { (Get-Item -LiteralPath $PreflightSourcePath).FullName } else { '' }
    $seenPaths = @{}
    $identities = @()
    foreach ($layout in $Layouts) {
        $layoutId = [string]$layout.layout_id
        $path = [string]$layout.path
        Assert-ERefitAttempt02Condition (Test-Path -LiteralPath $path -PathType Leaf) "$layoutId screenshot is absent: $path"
        $item = Get-Item -LiteralPath $path
        Assert-ERefitAttempt02Condition (-not $seenPaths.ContainsKey($item.FullName)) "$layoutId reuses a screenshot path"
        $seenPaths[$item.FullName] = $true
        Assert-ERefitAttempt02Condition ($item.FullName -cne $preflightItem.FullName) "$layoutId attempts to count the preflight evidence screenshot"
        if ($preflightSourceFullName -ne '') {
            Assert-ERefitAttempt02Condition ($item.FullName -cne $preflightSourceFullName) "$layoutId attempts to count the disposable preflight source screenshot"
        }
        $hash = Get-ERefitAttempt02Sha256 $item.FullName
        Assert-ERefitAttempt02Condition ($hash -cne $preflightHash) "$layoutId screenshot bytes are the disposable preflight screenshot"
        $dimensions = Get-ERefitAttempt02PngDimensions $item.FullName
        Assert-ERefitAttempt02Condition ($dimensions.Width -eq 1920 -and $dimensions.Height -eq 1046) "$layoutId screenshot is not 1920x1046"
        $identities += [pscustomobject]@{
            layout_id = $layoutId
            path = $item.FullName
            size_bytes = [int64]$item.Length
            sha256 = $hash
            width_pixels = [int64]$dimensions.Width
            height_pixels = [int64]$dimensions.Height
        }
    }
    return $identities
}

Export-ModuleMember -Function @(
    'Assert-ERefitAttempt02Condition',
    'Get-ERefitAttempt02Sha256',
    'Get-ERefitAttempt02Identity',
    'Assert-ERefitAttempt02Identity',
    'Get-ERefitAttempt02PngDimensions',
    'Get-ERefitAttempt02PrefixSha256',
    'Copy-ERefitAttempt02CreateOnly',
    'Write-ERefitAttempt02CreateOnlyJson',
    'Assert-ERefitAttempt02LayoutScreenshotSet'
)
