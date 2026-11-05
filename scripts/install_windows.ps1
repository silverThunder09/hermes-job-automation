$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot "work\runtime"
$VenvPath = Join-Path $RuntimeRoot ".venv"
$Python = Join-Path $VenvPath "Scripts\python.exe"
$TempRoot = Join-Path $RuntimeRoot "temp"
$PipCache = Join-Path $RuntimeRoot "pip-cache"

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    throw "Python 3.9 or later is required. Install Python, then rerun this script."
}

& python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.9 or later is required."
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $TempRoot, $PipCache | Out-Null
$env:TEMP = $TempRoot
$env:TMP = $TempRoot
$env:PIP_CACHE_DIR = $PipCache
if (-not (Test-Path $Python)) {
    & python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw "Could not create the project virtual environment." }
}

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip in the project virtual environment." }

Push-Location $ProjectRoot
try {
    & $Python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Could not install project dependencies." }
}
finally {
    Pop-Location
}

$SitePackages = (& $Python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])" | Select-Object -Last 1).Trim()
$SourcePath = (Join-Path $ProjectRoot "src").Replace("\", "/")
Set-Content -LiteralPath (Join-Path $SitePackages "hermes_job_automation.pth") -Value $SourcePath -Encoding ASCII

$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $RuntimeRoot "playwright-browsers"
& $Python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Could not install the isolated Playwright Chromium browser." }

Write-Host "Installed job-assist in $VenvPath"
Write-Host "Installed Chromium under $env:PLAYWRIGHT_BROWSERS_PATH"
Write-Host "Next: run scripts\install_hermes_local.ps1 to install Hermes into the same work directory."
