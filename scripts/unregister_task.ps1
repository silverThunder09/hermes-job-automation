$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot "work\runtime"
$HermesDataRoot = "D:\HermesRuntime"
$env:HERMES_HOME = Join-Path $HermesDataRoot "home"
$env:HERMES_RUNTIME_DIR = Join-Path $HermesDataRoot "runtime"
$HermesInstall = Join-Path $HermesDataRoot "source"
$HermesExe = Get-Item -LiteralPath (Join-Path $env:HERMES_HOME "bin\hermes.exe") -ErrorAction SilentlyContinue
if (-not $HermesExe) { throw "Hermes is not installed in the isolated project work directory." }

$Help = (& $HermesExe.FullName cron remove --help 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the Hermes Cron removal command." }
if ($Help -match "--name") {
    & $HermesExe.FullName cron remove --name "daily-job-assistant"
}
else {
    & $HermesExe.FullName cron remove "daily-job-assistant"
}
if ($LASTEXITCODE -ne 0) { throw "Could not remove Hermes Cron job daily-job-assistant." }
& $HermesExe.FullName cron list
if ($LASTEXITCODE -ne 0) { throw "Could not verify Hermes Cron removal." }
