# Build a distributable folder: dist\firefly\
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 as ANSI,
# so non-ASCII literals get mangled (that broke an earlier Chinese filename copy).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$cands = @("$root\.venv\Scripts\python.exe", (Join-Path (Split-Path -Parent $root) ".venv\Scripts\python.exe"))
$py = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $py) { $py = "python" }

$env:PYTHONIOENCODING = "utf-8"

# Regenerate runtime assets (icon, title-bar wordmark, help-page hero image).
& $py "design\make_assets.py" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "make_assets.py failed" }

# Regenerate the manual from firefly/help_text.py so docs never drift.
& $py "tests\gen_help_md.py" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "gen_help_md.py failed" }

& $py -m PyInstaller --noconfirm --clean --windowed --name firefly `
    --icon "firefly/assets/icon.ico" `
    --add-data "bin/potrace;bin/potrace" `
    --add-data "firefly/assets;assets" `
    --collect-all vtracer `
    --collect-all pypdfium2 `
    --collect-all pypdfium2_raw `
    --exclude-module matplotlib --exclude-module scipy --exclude-module skimage `
    --exclude-module pytest --exclude-module IPython `
    run.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Copy-Item "LICENSE" "dist\firefly\LICENSE" -Force
Copy-Item "THIRD-PARTY.md" "dist\firefly\THIRD-PARTY.md" -Force
Copy-Item "README.md" "dist\firefly\README.md" -Force

# Puts the manual (Chinese filename) into the fresh dist folder.
& $py "tests\gen_help_md.py" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "copy manual failed" }

$size = (Get-ChildItem "dist\firefly" -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Build OK: dist\firefly  ({0:N1} MB)" -f $size)
