# Stops only the backend and frontend processes recorded by Start-ProcessWatcher.
# A PID is killed only when its start time and command line still match the record,
# so unrelated Python, Node.js or other user processes are never touched.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "launcher-common.ps1")

$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$RuntimeDir = Join-Path $Root ".runtime"
$StatePath = Join-Path $RuntimeDir "launcher-state.json"
$BackendPort = 8000
$FrontendPort = 5173

Set-Location -LiteralPath $Root

Write-Host ""
Write-Host "Process Watcher - stop launcher" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Warn "No launcher state was found, so nothing was stopped."
    Write-Host "If you started the services manually, press Ctrl+C in their windows."
    exit 0
}

$state = Read-LauncherState -Path $StatePath
if (-not $state) {
    Write-Warn "The launcher state file is unreadable; nothing was stopped."
    exit 1
}

$stopped = 0
$skipped = 0
$failures = 0

foreach ($entry in @($state.frontend, $state.backend)) {
    if (-not $entry) {
        continue
    }
    if (-not (Test-EntryOwned $entry)) {
        Write-Warn "$($entry.name) (PID $($entry.pid)) is not running or does not match the launcher record; skipped."
        $skipped++
        continue
    }
    try {
        Write-Host "  stopping $($entry.name) (PID $($entry.pid)) ..."
        if (Stop-ServiceEntry $entry) {
            Write-Ok "Stopped $($entry.name)."
            $stopped++
        }
    }
    catch {
        Write-Err $_.Exception.Message
        $failures++
    }
}

foreach ($port in @($BackendPort, $FrontendPort)) {
    if (Wait-ForPortFree -Port $port -TimeoutSeconds 10) {
        Write-Ok "Port $port is free."
    }
    else {
        Write-Warn "Port $port is still in use by a process this launcher does not own."
    }
}

if ($failures -eq 0) {
    Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
}
else {
    Write-Warn "Some processes could not be stopped; the state file was kept so you can retry."
}

Write-Host ""
Write-Host "Stopped $stopped launcher-managed service(s); $skipped record(s) were already gone."
if ($state.url) {
    Write-Host "The browser tab at $($state.url) can be closed."
}
Write-Host ""

if ($failures -gt 0) {
    exit 1
}
exit 0
