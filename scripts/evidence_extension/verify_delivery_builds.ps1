param([string]$AdditionalDirectory = '')
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$outputRoot = Join-Path $sourceRoot 'evidence_extension_outputs'
$flatDirectory = Join-Path $outputRoot ('delivery-build-' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath (Join-Path $sourceRoot 'output/pdf/mineocclude_evidence_extension_overleaf.zip') -DestinationPath $flatDirectory
$compilerDirectory = 'C:\Users\gensa\AppData\Local\Programs\MiKTeX\miktex\bin\x64'
$reports = @()
$directories = @($flatDirectory, (Join-Path $outputRoot 'overleaf_staging'))
if ($AdditionalDirectory) { $directories += $AdditionalDirectory }
foreach ($directory in $directories) {
    Push-Location $directory
    try {
        & (Join-Path $compilerDirectory 'pdflatex.exe') '-interaction=nonstopmode' '-halt-on-error' 'paper.tex' | Out-File 'delivery-pass1.log'
        if ($LASTEXITCODE -ne 0) { throw "LaTeX failed: $directory" }
        & (Join-Path $compilerDirectory 'bibtex.exe') 'paper' | Out-File 'delivery-bibtex.log'
        if ($LASTEXITCODE -ne 0) { throw "BibTeX failed: $directory" }
        foreach ($pass in @(2,3)) {
            & (Join-Path $compilerDirectory 'pdflatex.exe') '-interaction=nonstopmode' '-halt-on-error' 'paper.tex' | Out-File "delivery-pass$pass.log"
            if ($LASTEXITCODE -ne 0) { throw "LaTeX failed: $directory" }
        }
        & (Join-Path $compilerDirectory 'pdftotext.exe') '-layout' 'paper.pdf' 'delivery-text.txt'
        $text = Get-Content 'delivery-text.txt' -Raw
        $pages = $text -split '\f'
        $referencePage = $null
        for ($index=0; $index -lt $pages.Length; $index++) {
            if ($pages[$index] -match '(?m)^\s*(?:\d+\s+)?References\s*$') { $referencePage=$index+1; break }
        }
        $log = Get-Content 'paper.log' -Raw
        if ($referencePage -ne 9 -or $log -match 'There were undefined|Citation .+ undefined|Reference .+ undefined|Overfull \\[hv]box') { throw "Build validation failed: $directory" }
        $referenceText = Get-Content (Join-Path $outputRoot 'paper/paper-layout.txt') -Raw
        if (($text -replace '\s','') -cne ($referenceText -replace '\s','')) { throw "PDF text differs: $directory" }
        $reports += [ordered]@{directory=$directory;status='PASS';references_start_page=9;pdf_text_matches_reviewed=$true}
    } finally { Pop-Location }
}
$reports | ConvertTo-Json -Depth 4 | Out-File (Join-Path $outputRoot 'delivery_build_checks.json') -Encoding utf8
$reports | ConvertTo-Json -Depth 4
