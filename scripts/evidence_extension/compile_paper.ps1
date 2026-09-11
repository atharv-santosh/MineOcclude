$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$paperDirectory = Join-Path $sourceRoot 'evidence_extension_outputs\paper'
$texCompiler = 'C:\Users\gensa\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe'
$bibCompiler = Join-Path (Split-Path $texCompiler -Parent) 'bibtex.exe'
$textReader = Join-Path (Split-Path $texCompiler -Parent) 'pdftotext.exe'
$renderer = 'C:\Users\gensa\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe'
foreach ($toolPath in @($texCompiler,$bibCompiler,$textReader,$renderer)) {
    if (-not (Test-Path -LiteralPath $toolPath)) { throw "Required tool absent: $toolPath" }
}
Push-Location $paperDirectory
try {
    & $texCompiler '-interaction=nonstopmode' '-halt-on-error' '-file-line-error' 'paper.tex' | Out-File 'build-pass1.txt' -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw 'First LaTeX pass failed' }
    & $bibCompiler 'paper' | Out-File 'build-bibtex.txt' -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw 'BibTeX failed' }
    foreach ($pass in @(2,3)) {
        & $texCompiler '-interaction=nonstopmode' '-halt-on-error' '-file-line-error' 'paper.tex' | Out-File "build-pass$pass.txt" -Encoding utf8
        if ($LASTEXITCODE -ne 0) { throw "LaTeX pass $pass failed" }
    }
    & $textReader '-layout' 'paper.pdf' 'paper-layout.txt'
    if ($LASTEXITCODE -ne 0) { throw 'PDF text extraction failed' }
    $pages = (Get-Content 'paper-layout.txt' -Raw) -split '\f'
    $referencePage = $null
    for ($index=0; $index -lt $pages.Length; $index++) {
        if ($pages[$index] -match '(?m)^\s*References\s*$') { $referencePage=$index+1; break }
    }
    $log = Get-Content 'paper.log' -Raw
    $report = [ordered]@{
        references_start_page=$referencePage
        target_references_start_page=9
        eight_main_pages_verified=($referencePage -eq 9)
        undefined_citations_or_references=($log -match 'There were undefined|Citation .+ undefined|Reference .+ undefined')
        overfull_boxes=@([regex]::Matches($log,'Overfull \\[hv]box[^\r\n]*') | ForEach-Object { $_.Value })
        visual_review='PENDING'
    }
    $report | ConvertTo-Json -Depth 4 | Out-File 'draft_build_report.json' -Encoding utf8
    $renderDirectory = Join-Path (Split-Path $paperDirectory -Parent) 'rendered'
    New-Item -ItemType Directory -Path $renderDirectory -Force | Out-Null
    & $renderer '-r' '110' '-png' 'paper.pdf' (Join-Path $renderDirectory 'page')
    if ($LASTEXITCODE -ne 0) { throw 'PDF page rendering failed' }
    Write-Output ($report | ConvertTo-Json -Depth 4)
} finally { Pop-Location }
