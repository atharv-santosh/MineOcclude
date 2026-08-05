[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$AuthorityPath,
    [Parameter(Mandatory = $true)][string]$RuntimePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$modulePath = Join-Path $PSScriptRoot 'ServerPropertiesAuthority.psm1'
Import-Module -Name $modulePath -Force
$result = Compare-ServerPropertiesAuthority -AuthorityPath $AuthorityPath -RuntimePath $RuntimePath
$result | ConvertTo-Json -Depth 20
