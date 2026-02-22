<#
.SYNOPSIS
    Builds a Windows release of PinVault using PyInstaller.

.DESCRIPTION
    1. Activates (or creates) the .venv virtual environment
    2. Installs/upgrades dependencies including PyInstaller
    3. Optionally converts pinvault.svg → pinvault.ico  (requires Pillow + cairosvg)
    4. Runs PyInstaller with pinvault.spec
    5. Produces dist/PinVault/ ready for distribution
    6. Optionally ZIPs the output as dist/PinVault-windows.zip

.EXAMPLE
    .\build_release.ps1
    .\build_release.ps1 -Zip
#>

param(
    [switch]$Zip,
    [switch]$SkipVenv
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot

# ── 1. Virtual environment ────────────────────────────────────────────────────
if (-not $SkipVenv) {
    if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) {
        Write-Host "Creating .venv..." -ForegroundColor Cyan
        python -m venv "$Root\.venv"
    }
    $Python = "$Root\.venv\Scripts\python.exe"
    $Pip    = "$Root\.venv\Scripts\pip.exe"
} else {
    $Python = "python"
    $Pip    = "pip"
}

# ── 2. Install dependencies ───────────────────────────────────────────────────
Write-Host "Installing dependencies..." -ForegroundColor Cyan
& $Pip install --upgrade pip --quiet
& $Pip install -r "$Root\requirements.txt" --quiet
& $Pip install pyinstaller --quiet

# ── 3. Try to create pinvault.ico from pinvault.svg ───────────────────────────
$SvgPath = "$Root\app\qml\pinvault.svg"
$IcoPath = "$Root\app\qml\pinvault.ico"
if (-not (Test-Path $IcoPath)) {
    Write-Host "Attempting SVG → ICO conversion..." -ForegroundColor Cyan
    & $Pip install Pillow cairosvg --quiet 2>$null
    $ConvertScript = @"
import sys, os
try:
    import cairosvg, io
    from PIL import Image
    svg = r'$SvgPath'.replace('\\', '/')
    png = cairosvg.svg2png(url=svg, output_width=256, output_height=256)
    img = Image.open(io.BytesIO(png)).convert('RGBA')
    sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
    imgs  = [img.resize(s, Image.LANCZOS) for s in sizes]
    imgs[0].save(r'$IcoPath', format='ICO', sizes=sizes, append_images=imgs[1:])
    print('ICO created:', r'$IcoPath')
except Exception as e:
    print('ICO conversion skipped:', e)
"@
    & $Python -c $ConvertScript
}

# ── 4. Clean previous build ───────────────────────────────────────────────────
if (Test-Path "$Root\dist\PinVault") {
    Write-Host "Removing previous dist/PinVault..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "$Root\dist\PinVault"
}

# ── 5. PyInstaller ────────────────────────────────────────────────────────────
Write-Host "Running PyInstaller..." -ForegroundColor Cyan
Push-Location $Root
& "$Root\.venv\Scripts\pyinstaller.exe" pinvault.spec --noconfirm
Pop-Location

if (-not (Test-Path "$Root\dist\PinVault\PinVault.exe")) {
    Write-Error "Build failed — dist\PinVault\PinVault.exe not found."
    exit 1
}

Write-Host "Build succeeded: dist\PinVault\PinVault.exe" -ForegroundColor Green

# ── 6. Optional ZIP ───────────────────────────────────────────────────────────
if ($Zip) {
    $ZipOut = "$Root\dist\PinVault-windows.zip"
    if (Test-Path $ZipOut) { Remove-Item $ZipOut }
    Write-Host "Creating $ZipOut..." -ForegroundColor Cyan
    Compress-Archive -Path "$Root\dist\PinVault" -DestinationPath $ZipOut
    Write-Host "ZIP created: $ZipOut" -ForegroundColor Green
}
