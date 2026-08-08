Set-StrictMode -Version Latest

function Open-C6ALiveLogForRead {
    param([Parameter(Mandatory)][string] $Path)

    $share = [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
    return [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, $share)
}

function Get-C6ALiveLogLength {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return [int64]0 }
    $stream = $null
    try {
        $stream = Open-C6ALiveLogForRead -Path $Path
        return [int64]$stream.Length
    }
    finally {
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Read-C6ALiveLogText {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $Path,
        [int64] $StartOffset = 0
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '' }
    $stream = $null
    $reader = $null
    try {
        $stream = Open-C6ALiveLogForRead -Path $Path
        $effectiveOffset = if ($StartOffset -le $stream.Length) { $StartOffset } else { 0 }
        [void]$stream.Seek($effectiveOffset, [IO.SeekOrigin]::Begin)
        $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8, $true, 4096, $true)
        return $reader.ReadToEnd()
    }
    catch [IO.IOException] {
        return $null
    }
    finally {
        if ($null -ne $reader) { $reader.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Test-C6AScheduleLoadEvent {
    [CmdletBinding()]
    param(
        [AllowEmptyString()][string] $Text,
        [Parameter(Mandatory)][int64] $EpisodeId,
        [Parameter(Mandatory)][int] $DrawCount,
        [Parameter(Mandatory)][string] $ScheduleFileName
    )

    if ([string]::IsNullOrEmpty($Text)) { return $false }
    $eventPattern = 'loaded immutable noise schedule \((?<draws>\d+) draws\) from (?<path>[^\r\n]*?episode_(?<episode>\d+)\.jsonl)(?:\s|$)'
    foreach ($match in [regex]::Matches($Text, $eventPattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
        $observedPath = $match.Groups['path'].Value.Trim()
        $observedFileName = [IO.Path]::GetFileName($observedPath.Replace('/', '\'))
        $observedEpisode = [int64]$match.Groups['episode'].Value
        $observedDraws = [int]$match.Groups['draws'].Value
        if ($observedEpisode -eq $EpisodeId -and $observedDraws -eq $DrawCount -and $observedFileName -ceq $ScheduleFileName) {
            return $true
        }
    }
    return $false
}

function Wait-C6AScheduleLoadEvent {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $Path,
        [Parameter(Mandatory)][int64] $EpisodeId,
        [Parameter(Mandatory)][int] $DrawCount,
        [Parameter(Mandatory)][string] $ScheduleFileName,
        [Parameter(Mandatory)][int64] $StartOffset,
        [ValidateRange(1, 300000)][int] $TimeoutMilliseconds = 60000,
        [ValidateRange(10, 5000)][int] $PollIntervalMilliseconds = 200
    )

    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    while ($stopwatch.ElapsedMilliseconds -lt $TimeoutMilliseconds) {
        $text = Read-C6ALiveLogText -Path $Path -StartOffset $StartOffset
        if ($null -ne $text -and (Test-C6AScheduleLoadEvent -Text $text -EpisodeId $EpisodeId -DrawCount $DrawCount -ScheduleFileName $ScheduleFileName)) {
            return $true
        }
        $remaining = $TimeoutMilliseconds - [int]$stopwatch.ElapsedMilliseconds
        if ($remaining -le 0) { break }
        Start-Sleep -Milliseconds ([Math]::Min($PollIntervalMilliseconds, $remaining))
    }
    return $false
}

Export-ModuleMember -Function Get-C6ALiveLogLength, Read-C6ALiveLogText, Test-C6AScheduleLoadEvent, Wait-C6AScheduleLoadEvent
