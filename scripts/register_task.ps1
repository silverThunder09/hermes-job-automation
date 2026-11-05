param(
    [switch]$SkipGateway
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot "work\runtime"
$HermesDataRoot = "D:\HermesRuntime"
$HermesHome = Join-Path $HermesDataRoot "home"
$HermesInstall = Join-Path $HermesDataRoot "source"

$env:HERMES_HOME = $HermesHome
$env:HERMES_RUNTIME_DIR = Join-Path $HermesDataRoot "runtime"
$HermesExe = Get-Item -LiteralPath (Join-Path $HermesHome "bin\hermes.exe") -ErrorAction SilentlyContinue
if (-not $HermesExe) { throw "Hermes is not installed in the isolated project work directory." }

if (-not $SkipGateway) {
    & $HermesExe.FullName gateway install
    if ($LASTEXITCODE -ne 0) { throw "Hermes Gateway installation failed." }
}

$ExistingJobs = (& $HermesExe.FullName cron list 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect existing Hermes Cron jobs; no schedule was changed."
}
if ($ExistingJobs -match "daily-job-assistant") {
    Write-Host "Hermes Cron job daily-job-assistant already exists; leaving it unchanged."
}
else {
    $Prompt = "Read the project skill at $ProjectRoot\skills\job-search\SKILL.md. Run the project collection step from $ProjectRoot using the isolated Python environment at $RuntimeRoot\.venv\Scripts\python.exe. Evaluate only postings in data\to-review.json using verified applicant facts. Draft tailored resume and cover-letter text only for eligible postings at or above MINIMUM_SCORE. Save the result JSON and run finalize without submitting any application. Use finalize --execute only when the Google Sheet, Drive parent, credentials, and Telegram are all explicitly configured. Report source counts, eligibility, excluded jobs, documents, and skipped integrations."
    & $HermesExe.FullName cron create "0 4 * * *" --timezone Asia/Seoul --name "daily-job-assistant" $Prompt
    if ($LASTEXITCODE -ne 0) { throw "Hermes Cron job creation failed." }
}

& $HermesExe.FullName cron list
if ($LASTEXITCODE -ne 0) { throw "Could not verify the Hermes Cron job list." }
& $HermesExe.FullName cron status
if ($LASTEXITCODE -ne 0) { throw "Could not verify Hermes Cron status." }
Write-Host "Hermes Cron is configured for 04:00 Asia/Seoul."
Write-Host "The Gateway runs only while its Windows scheduled task can start; the PC must be on and the user logged in."
