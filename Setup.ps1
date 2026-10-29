$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.cache\uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.runtime'
$env:UV_PYTHON_BIN_DIR = Join-Path $PSScriptRoot '.tools'
$uvExe = Join-Path $PSScriptRoot '.tools\uv.exe'

if (-not (Test-Path -LiteralPath $uvExe)) {
    Write-Host 'Downloading the local runtime manager...'
    New-Item -ItemType Directory -Force -Path '.tools' | Out-Null
    $archive = Join-Path $PSScriptRoot '.tools\uv.zip'
    & curl.exe -fL --retry 2 'https://github.com/astral-sh/uv/releases/download/0.13.6/uv-x86_64-pc-windows-msvc.zip' -o $archive
    if ($LASTEXITCODE -ne 0) { throw 'Could not download uv. Check your internet connection.' }
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $PSScriptRoot '.tools') -Force
}

& $uvExe venv --allow-existing --python 3.13 --managed-python .venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
& $uvExe pip sync --python '.venv\Scripts\python.exe' requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Could not install application dependencies.' }
Write-Host 'Video Cropper is ready. Double-click Launch Video Cropper.cmd.' -ForegroundColor Green
