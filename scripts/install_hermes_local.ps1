$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot "work\runtime"
$HermesDataRoot = "D:\HermesRuntime"
$HermesHome = Join-Path $HermesDataRoot "home"
$HermesInstall = Join-Path $HermesDataRoot "source"
$InstallerPath = Join-Path $RuntimeRoot "hermes-install.ps1"
$InstallerUrl = "https://hermes-agent.nousresearch.com/install.ps1"
$TempRoot = Join-Path $HermesDataRoot "temp"

New-Item -ItemType Directory -Force -Path $RuntimeRoot, $HermesDataRoot, $HermesHome, $TempRoot | Out-Null
$env:TEMP = $TempRoot
$env:TMP = $TempRoot
$env:HERMES_HOME = $HermesHome
$env:HERMES_RUNTIME_DIR = Join-Path $HermesDataRoot "runtime"
$env:UV_CACHE_DIR = Join-Path $RuntimeRoot "uv-cache"
$env:UV_PYTHON_CACHE_DIR = Join-Path $RuntimeRoot "uv-python-cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $RuntimeRoot "hermes-python"
$env:UV_PYTHON_BIN_DIR = Join-Path $RuntimeRoot "hermes-bin"
$env:UV_PYTHON_NO_REGISTRY = "1"
New-Item -ItemType Directory -Force -Path $env:UV_CACHE_DIR, $env:UV_PYTHON_CACHE_DIR, $env:UV_PYTHON_INSTALL_DIR, $env:UV_PYTHON_BIN_DIR | Out-Null
$InstallerContent = (Invoke-WebRequest -Uri $InstallerUrl -UseBasicParsing -TimeoutSec 30).Content
$PersistentPathLine = '[Environment]::SetEnvironmentVariable("Path", "$binDir;$userPath", "User")'
$PersistentPathReplacement = '$env:Path = "$binDir;$env:Path"'
$Occurrences = ([regex]::Matches($InstallerContent, [regex]::Escape($PersistentPathLine))).Count
if ($Occurrences -ne 1) {
    throw "The official installer PATH behavior changed. Review the script before running it."
}

# Keep Hermes and its configuration inside work; the official installer's only
# persistent user-level PATH write is changed to a current-process PATH update.
$InstallerContent = $InstallerContent.Replace($PersistentPathLine, $PersistentPathReplacement)
Set-Content -LiteralPath $InstallerPath -Value $InstallerContent -Encoding UTF8
$InstallerHash = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash
Write-Host "Downloaded official installer from $InstallerUrl"
Write-Host "Local installer SHA256 after PATH isolation: $InstallerHash"

& $InstallerPath -HermesHome $HermesHome -InstallDir $HermesInstall -NonInteractive
if ($LASTEXITCODE -ne 0) {
    throw "The official Hermes installer returned exit code $LASTEXITCODE."
}

$HermesExe = Get-Item -LiteralPath (Join-Path $HermesHome "bin\hermes.exe") -ErrorAction SilentlyContinue
if (-not $HermesExe) {
    throw "Hermes installer completed without a hermes.exe under the requested install directory."
}

Write-Host "Hermes executable: $($HermesExe.FullName)"
& $HermesExe.FullName --version
if ($LASTEXITCODE -ne 0) { throw "Installed Hermes did not pass its version check." }
Write-Host "Hermes configuration is isolated in $HermesHome"
