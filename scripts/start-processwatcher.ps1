# Process Watcher demo launcher (Windows).
# Starts the FastAPI backend with PW_MODE=demo and the Vite frontend, waits for
# both health checks, verifies the frozen demo pack, and opens the gallery.
# Every model client is cache-only in demo mode; .env is deliberately not loaded.

[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "launcher-common.ps1")

$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$RuntimeDir = Join-Path $Root ".runtime"
$LogDir = Join-Path $RuntimeDir "logs"
$StatePath = Join-Path $RuntimeDir "launcher-state.json"
$BackendPort = 8000
$FrontendPort = 5173
$HealthUrl = "http://127.0.0.1:$BackendPort/healthz"
$FrontendUrl = "http://127.0.0.1:$FrontendPort/"
$DemoUrl = "http://127.0.0.1:$FrontendPort/demo"
$DemoCasesUrl = "http://127.0.0.1:$BackendPort/demo/cases"

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [hashtable]$Environment,
        [int]$Port
    )
    $outLog = Join-Path $LogDir "$Name.out.log"
    $errLog = Join-Path $LogDir "$Name.err.log"

    foreach ($key in $Environment.Keys) {
        Set-Item -Path ("Env:" + $key) -Value $Environment[$key]
    }

    Write-Info "  starting $Name ..."
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments `
        -WorkingDirectory $Root -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog -WindowStyle Minimized -PassThru

    Start-Sleep -Milliseconds 800
    if ($process.HasExited) {
        throw "$Name exited immediately with code $($process.ExitCode). See $errLog and $outLog."
    }

    $identity = Get-ProcessIdentity -TargetProcessId $process.Id
    if (-not $identity) {
        throw "$Name started but its process identity could not be inspected."
    }

    return [pscustomobject]@{
        name         = $Name
        pid          = $process.Id
        start_time   = $identity.StartTime
        command_line = $identity.CommandLine
        port         = $Port
    }
}

Set-Location -LiteralPath $Root
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$backendEntry = $null
$frontendEntry = $null

Write-Host ""
Write-Host "Process Watcher - demo launcher" -ForegroundColor Cyan
Write-Host "Project: $Root"
Write-Host "Mode:    demo (frozen cases, no Meta API calls, .env is not loaded)"
Write-Host ""

try {
    foreach ($required in @("pyproject.toml", "web\package.json", "demo\cases")) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $required))) {
            throw "This does not look like the Process Watcher repository (missing $required)."
        }
    }

    # 1. An instance started by this launcher is reused instead of duplicated.
    Write-Host "[1/6] Checking for an existing launcher instance"
    $state = Read-LauncherState -Path $StatePath
    if ($state) {
        $backendAlive = Test-EntryOwned $state.backend
        $frontendAlive = Test-EntryOwned $state.frontend
        $backendProbe = Invoke-LocalRequest -Url $HealthUrl
        $frontendProbe = Invoke-LocalRequest -Url $FrontendUrl
        if ($backendAlive -and $frontendAlive -and $backendProbe -and
            $backendProbe.StatusCode -eq 200 -and $frontendProbe -and
            $frontendProbe.StatusCode -ge 200 -and $frontendProbe.StatusCode -lt 400) {
            Write-Ok "Process Watcher is already running (backend PID $($state.backend.pid), frontend PID $($state.frontend.pid))."
            Write-Host "Demo:    $DemoUrl"
            Write-Host "Stop it: Stop-ProcessWatcher.bat"
            if (-not $NoBrowser) {
                Start-Process $DemoUrl
            }
            exit 0
        }

        Write-Warn "Found launcher state from a previous run; cleaning up only its recorded processes."
        foreach ($entry in @($state.frontend, $state.backend)) {
            if (-not $entry) {
                continue
            }
            try {
                if (Stop-ServiceEntry $entry) {
                    Write-Ok "Stopped stale $($entry.name) (PID $($entry.pid))."
                }
                else {
                    Write-Info "  $($entry.name) (PID $($entry.pid)) is already gone."
                }
            }
            catch {
                Write-Warn $_.Exception.Message
            }
        }
        Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
        [void](Wait-ForPortFree -Port $BackendPort -TimeoutSeconds 5)
        [void](Wait-ForPortFree -Port $FrontendPort -TimeoutSeconds 5)
    }
    else {
        Write-Ok "No launcher-managed instance is running."
    }

    # 2. Prerequisites.
    Write-Host "[2/6] Checking prerequisites"
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCommand) {
        throw "uv is not on PATH. Install it from https://docs.astral.sh/uv/ and reopen this window."
    }
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCommand) {
        throw "Node.js is not on PATH. Install Node 22.12 or newer from https://nodejs.org/."
    }
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npmCommand) {
        $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    }
    if (-not $npmCommand) {
        throw "npm is not on PATH. Reinstall Node.js (it bundles npm) and reopen this window."
    }

    $nodeVersionText = (& $nodeCommand.Source --version).Trim().TrimStart("v")
    try {
        $nodeVersion = [version]$nodeVersionText
    }
    catch {
        throw "Could not parse the Node.js version '$nodeVersionText'."
    }
    if ($nodeVersion -lt [version]"22.12.0") {
        throw "Node.js 22.12 or newer is required; found $nodeVersionText."
    }

    $pythonExe = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "The Python environment is missing. Run 'uv sync' in $Root, then try again."
    }
    # PS 5.1 turns native stderr into an error record when the preference is Stop;
    # uv writes progress to stderr, so relax it only for this probe.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $syncOutput = & $uvCommand.Source sync --check --offline 2>&1 | Out-String
    $syncExit = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($syncExit -ne 0) {
        throw "The Python environment is out of date. Run 'uv sync' in $Root, then try again.`n$syncOutput"
    }

    $viteBin = Join-Path $Root "web\node_modules\.bin\vite.cmd"
    if (-not (Test-Path -LiteralPath $viteBin)) {
        throw "Web dependencies are missing. Run 'npm --prefix web ci' in $Root, then try again."
    }

    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        Write-Warn "ffmpeg is not on PATH. Demo playback still works; new/live runs need it."
    }
    Write-Ok "uv, Node $nodeVersionText, npm, the Python environment and web dependencies are ready."

    # 3. Ports must be free; an unrelated listener is never killed.
    Write-Host "[3/6] Checking ports $BackendPort and $FrontendPort"
    if (Test-PortOpen $BackendPort) {
        $probe = Invoke-LocalRequest -Url $HealthUrl
        if ($probe -and $probe.StatusCode -eq 200) {
            throw "Port $BackendPort already serves a Process Watcher API that this launcher did not start. Close it (or stop it) before launching again."
        }
        throw "Port $BackendPort is in use by another program. Free the port and try again."
    }
    if (Test-PortOpen $FrontendPort) {
        throw "Port $FrontendPort is in use by another program. Free the port and try again."
    }
    Write-Ok "Both ports are free."

    # 4. Backend in demo mode. PW_ENV_FILE points at a missing file so .env (and
    # any real API key) is never read; the empty key makes live mode impossible.
    Write-Host "[4/6] Starting backend (PW_MODE=demo)"
    $backendEnvironment = @{
        PW_MODE         = "demo"
        PW_ENV_FILE     = (Join-Path $RuntimeDir "demo-mode-does-not-load-env")
        META_API_KEY    = ""
        PYTHONUNBUFFERED = "1"
        NO_COLOR        = "1"
    }
    $backendEntry = Start-ManagedProcess -Name "backend" -FilePath $uvCommand.Source `
        -Arguments @("run", "--frozen", "--no-sync", "uvicorn", "pw.api.main:app",
                     "--host", "127.0.0.1", "--port", "$BackendPort") `
        -Environment $backendEnvironment -Port $BackendPort

    $state = [ordered]@{
        schema_version = 1
        root           = $Root
        mode           = "demo"
        started_at     = (Get-Date).ToUniversalTime().ToString("o")
        url            = $DemoUrl
        backend        = $backendEntry
        frontend       = $null
    }
    Save-LauncherState -Path $StatePath -State $state

    $health = Wait-ForEndpoint -Url $HealthUrl -TimeoutSeconds 90 -Label "Backend"
    if (-not $health) {
        throw "Backend did not become ready. Check $LogDir\backend.err.log."
    }
    Write-Ok "Backend ready at $HealthUrl"

    # 5. Frontend through the existing npm script, locked to the expected port.
    Write-Host "[5/6] Starting frontend"
    $frontendEnvironment = @{
        PW_API_URL = "http://127.0.0.1:$BackendPort"
        BROWSER    = "none"
        NO_COLOR   = "1"
    }
    $npmCommandLine = "npm --prefix web run dev -- --host 127.0.0.1 --port $FrontendPort --strictPort"
    $frontendEntry = Start-ManagedProcess -Name "frontend" -FilePath $env:ComSpec `
        -Arguments @("/d", "/c", $npmCommandLine) `
        -Environment $frontendEnvironment -Port $FrontendPort

    $state.frontend = $frontendEntry
    Save-LauncherState -Path $StatePath -State $state

    $frontendReady = Wait-ForEndpoint -Url $FrontendUrl -TimeoutSeconds 120 -Label "Frontend"
    if (-not $frontendReady) {
        throw "Frontend did not become ready. Check $LogDir\frontend.err.log."
    }
    Write-Ok "Frontend ready at $FrontendUrl"

    # 6. Verify the offline demo pack is actually served before opening a browser.
    Write-Host "[6/6] Verifying the offline demo pack"
    $casesResponse = Invoke-LocalRequest -Url $DemoCasesUrl
    if (-not $casesResponse -or $casesResponse.StatusCode -ne 200) {
        throw "The demo API did not return $DemoCasesUrl."
    }
    $cases = ($casesResponse.Body | ConvertFrom-Json).cases
    $caseCount = @($cases).Count
    if ($caseCount -lt 1) {
        throw "The demo API returned no cases. Run 'uv run pw demo-verify' to check the pack."
    }
    Write-Ok "$caseCount demo case(s) available."

    if (-not $NoBrowser) {
        try {
            Start-Process $DemoUrl
            Write-Ok "Opened $DemoUrl in your default browser."
        }
        catch {
            Write-Warn "Could not open a browser automatically. Open $DemoUrl manually."
        }
    }
    else {
        Write-Info "  Browser launch skipped (-NoBrowser)."
    }

    Write-Host ""
    Write-Host "Process Watcher is running in DEMO mode." -ForegroundColor Green
    Write-Host "Demo:     $DemoUrl"
    Write-Host "Backend:  $HealthUrl"
    Write-Host "Logs:     $LogDir"
    Write-Host "Stop it:  Stop-ProcessWatcher.bat"
    Write-Host ""
    exit 0
}
catch {
    Write-Host ""
    Write-Err $_.Exception.Message

    # Only show logs for services this run actually started; otherwise a port or
    # prerequisite failure would display stale logs from an earlier launch.
    if ($backendEntry) {
        Show-LogTail -Path (Join-Path $LogDir "backend.err.log")
        Show-LogTail -Path (Join-Path $LogDir "backend.out.log")
    }
    if ($frontendEntry) {
        Show-LogTail -Path (Join-Path $LogDir "frontend.err.log")
        Show-LogTail -Path (Join-Path $LogDir "frontend.out.log")
    }

    if ($backendEntry -or $frontendEntry) {
        Write-Info "Rolling back the processes this launcher started ..."
        foreach ($entry in @($frontendEntry, $backendEntry)) {
            if (-not $entry) {
                continue
            }
            try {
                if (Stop-ServiceEntry $entry) {
                    Write-Ok "Stopped $($entry.name) (PID $($entry.pid))."
                }
            }
            catch {
                Write-Warn $_.Exception.Message
            }
        }
    }
    Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
    exit 1
}
