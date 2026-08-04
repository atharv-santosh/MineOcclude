Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ServerPropertiesFileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-ServerPropertiesTextSha256 {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
    $encoding = [System.Text.UTF8Encoding]::new($false)
    $bytes = $encoding.GetBytes($Text)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($algorithm.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
    }
}

function Read-StrictServerProperties {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "server.properties file absent: $Path"
    }
    $properties = [System.Collections.Generic.Dictionary[string,string]]::new([System.StringComparer]::Ordinal)
    $lineNumber = 0
    foreach ($line in [System.IO.File]::ReadAllLines((Get-Item -LiteralPath $Path).FullName)) {
        $lineNumber++
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith('#') -or $trimmed.StartsWith('!')) {
            continue
        }
        $separator = $line.IndexOf('=')
        if ($separator -lt 1) {
            throw "Malformed non-comment server.properties line $lineNumber in $Path"
        }
        $key = $line.Substring(0, $separator)
        $value = $line.Substring($separator + 1)
        if ($key.Length -eq 0 -or $key -cne $key.Trim() -or $key -match '\s') {
            throw "Malformed server.properties key on line $lineNumber in $Path"
        }
        if ($properties.ContainsKey($key)) {
            throw "Duplicate server.properties key '$key' in $Path"
        }
        $properties.Add($key, $value)
    }
    [string[]]$keys = @($properties.Keys)
    [System.Array]::Sort($keys, [System.StringComparer]::Ordinal)
    $canonicalLines = @($keys | ForEach-Object { "$_=$($properties[$_])" })
    $canonicalText = $canonicalLines -join "`n"
    return [pscustomobject]@{
        Path = (Get-Item -LiteralPath $Path).FullName
        Properties = $properties
        PropertyCount = $properties.Count
        RawSha256 = Get-ServerPropertiesFileSha256 $Path
        CanonicalSemanticText = $canonicalText
        CanonicalSemanticSha256 = Get-ServerPropertiesTextSha256 $canonicalText
    }
}

function Compare-ServerPropertiesAuthority {
    param(
        [Parameter(Mandatory = $true)][string]$AuthorityPath,
        [Parameter(Mandatory = $true)][string]$RuntimePath
    )

    $authority = Read-StrictServerProperties $AuthorityPath
    $runtime = Read-StrictServerProperties $RuntimePath
    $allowedAdditionalKeys = @('query.port', 'text-filtering-config')
    $missing = @($authority.Properties.Keys | Where-Object { -not $runtime.Properties.ContainsKey($_) } | Sort-Object -CaseSensitive)
    $changed = @($authority.Properties.Keys | Where-Object { $runtime.Properties.ContainsKey($_) -and $runtime.Properties[$_] -cne $authority.Properties[$_] } | Sort-Object -CaseSensitive)
    $additional = @($runtime.Properties.Keys | Where-Object { -not $authority.Properties.ContainsKey($_) } | Sort-Object -CaseSensitive)
    $unexpected = @($additional | Where-Object { $_ -cnotin $allowedAdditionalKeys })
    $allowedPresent = @($additional | Where-Object { $_ -cin $allowedAdditionalKeys })

    if ($missing.Count -ne 0) {
        throw "Missing authoritative server.properties keys: $($missing -join ',')"
    }
    if ($changed.Count -ne 0) {
        throw "Changed authoritative server.properties values: $($changed -join ',')"
    }
    if ($unexpected.Count -ne 0) {
        throw "Unexpected additional server.properties keys: $($unexpected -join ',')"
    }
    if (-not $runtime.Properties.ContainsKey('spawn-animals') -or $runtime.Properties['spawn-animals'] -cne 'false') {
        throw 'spawn-animals must equal false'
    }
    if ($runtime.Properties.ContainsKey('query.port')) {
        if (-not $runtime.Properties.ContainsKey('server-port') -or $runtime.Properties['query.port'] -cne $runtime.Properties['server-port']) {
            throw 'query.port must equal server-port'
        }
    }
    if ($runtime.Properties.ContainsKey('text-filtering-config') -and $runtime.Properties['text-filtering-config'] -cne '') {
        throw 'text-filtering-config must be empty'
    }

    $safetyCriticalKeys = @(
        'spawn-animals', 'server-port', 'query.port', 'text-filtering-config', 'level-name',
        'online-mode', 'difficulty', 'gamemode', 'enable-command-block', 'enable-query',
        'enable-rcon', 'max-players', 'view-distance', 'white-list', 'enforce-whitelist',
        'spawn-npcs', 'spawn-monsters', 'force-gamemode', 'hardcore', 'pvp'
    )
    $safetyCriticalValues = [ordered]@{}
    foreach ($key in $safetyCriticalKeys) {
        $safetyCriticalValues[$key] = if ($runtime.Properties.ContainsKey($key)) { $runtime.Properties[$key] } else { $null }
    }
    $classification = if ($additional.Count -eq 0) { 'EXACT_SEMANTIC_AUTHORITY_MATCH' } else { 'MINECRAFT_SERVER_PROPERTIES_AUTO_EXPANSION' }
    return [pscustomobject][ordered]@{
        schema_version = 'person-c-server-properties-semantic-authority-validation-v0.1'
        status = 'PASS'
        drift_classification = $classification
        raw_files_identical = ($authority.RawSha256 -ceq $runtime.RawSha256)
        authority = [ordered]@{
            path = $authority.Path
            property_count = $authority.PropertyCount
            raw_sha256 = $authority.RawSha256
            canonical_semantic_sha256 = $authority.CanonicalSemanticSha256
        }
        runtime = [ordered]@{
            path = $runtime.Path
            property_count = $runtime.PropertyCount
            raw_sha256 = $runtime.RawSha256
            canonical_semantic_sha256 = $runtime.CanonicalSemanticSha256
        }
        shared_property_count = $authority.PropertyCount
        shared_property_values_match = $true
        missing_authoritative_keys = @()
        changed_authoritative_keys = @()
        allowed_additional_keys = $allowedAdditionalKeys
        allowed_additional_keys_present = $allowedPresent
        unexpected_additional_keys = @()
        query_port_matches_server_port = (-not $runtime.Properties.ContainsKey('query.port') -or $runtime.Properties['query.port'] -ceq $runtime.Properties['server-port'])
        text_filtering_config_empty = (-not $runtime.Properties.ContainsKey('text-filtering-config') -or $runtime.Properties['text-filtering-config'] -ceq '')
        safety_critical_values = $safetyCriticalValues
        semantic_comparison_result = 'PASS'
    }
}

Export-ModuleMember -Function Read-StrictServerProperties, Compare-ServerPropertiesAuthority
