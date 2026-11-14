param([string]$ChromiumSource = "", [string]$FFmpegDirectory = "")
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
function Check-Step([string]$label) {
    if ($LASTEXITCODE -ne 0) { throw "$label failed" }
}
Push-Location $project
try {
    python -m pip install --index-url https://pypi.org/simple -r requirements-dev.txt
    Check-Step 'Install dependencies'
    python -c "import struct; assert struct.calcsize('P') == 8, '64-bit Python required'"
    Check-Step 'Check architecture'
    New-Item -ItemType Directory -Force resources/bin | Out-Null
    foreach ($name in @('ffmpeg','ffprobe')) {
        $source = if ($FFmpegDirectory) { Join-Path $FFmpegDirectory "$name.exe" } else { (Get-Command "$name.exe" -ErrorAction Stop).Source }
        if (-not (Test-Path -LiteralPath $source)) { throw "Missing $source" }
        Copy-Item -LiteralPath $source -Destination "resources/bin/$name.exe" -Force
    }
    if ($ChromiumSource) {
        if (-not (Test-Path -LiteralPath (Join-Path $ChromiumSource 'chrome-win64/chrome.exe'))) { throw 'ChromiumSource must contain chrome-win64/chrome.exe' }
        New-Item -ItemType Directory -Force resources/chromium-custom | Out-Null
        Copy-Item -LiteralPath (Join-Path $ChromiumSource 'chrome-win64') -Destination resources/chromium-custom -Recurse -Force
    } else {
        if (Test-Path resources/chromium-custom) { throw 'Move the old resources/chromium-custom before installing a different browser' }
        $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $project 'resources/browsers'
        python -m playwright install chromium
        Check-Step 'Install browser'
    }
    python -m ruff check app tests scripts
    Check-Step 'Lint'
    python -m unittest discover -s tests -v
    Check-Step 'Tests'
    python scripts/html_check.py
    Check-Step 'UI tests'
    python -m PyInstaller --noconfirm desktop.spec
    Check-Step 'PyInstaller'
    python scripts/verify_portable.py
    Check-Step 'Portable runtime'
    python scripts/prepare_notices.py dist/网络ASR/notices
    Check-Step 'Third party notices'
    python scripts/package_release.py
    Check-Step 'Release ZIP'
} finally { Pop-Location }
