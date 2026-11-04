# Shared helpers for the Windows demo launcher. Dot-source this file; it only
# defines functions and never starts or stops anything by itself.

function Write-Info {
    param([string]$Message)
    Write-Host $Message
}

function Write-Ok {
    param([string]$Message)
    Write-Host "  OK   $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  WARN $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "  FAIL $Message" -ForegroundColor Red
}

function Show-LogTail {
    param(
        [string]$Path,
        [int]$Lines = 20
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    Write-Host "--- $Path (last $Lines lines) ---" -ForegroundColor DarkGray
    Get-Content -LiteralPath $Path -Tail $Lines -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    Write-Host "---" -ForegroundColor DarkGray
}

function Test-PortOpen {
    param([int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(400)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

# HTTP without the system proxy: the services only listen on loopback.
function Invoke-LocalRequest {
    param(
        [string]$Url,
        [int]$TimeoutMs = 2000
    )
    $request = [System.Net.WebRequest]::Create($Url)
    $request.Proxy = $null
    $request.Timeout = $TimeoutMs
    $request.ReadWriteTimeout = $TimeoutMs
    $response = $null
    try {
        $response = $request.GetResponse()
        $stream = $response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $body = $reader.ReadToEnd()
        $reader.Dispose()
        $stream.Dispose()
        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Body       = $body
        }
    }
    catch {
        return $null
    }
    finally {
        if ($response) {
            $response.Close()
        }
    }
}

function Wait-ForEndpoint {
    param(
        [string]$Url,
        [int]$TimeoutSeconds,
        [string]$Label
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $result = Invoke-LocalRequest -Url $Url -TimeoutMs 1500
        if ($result -and $result.StatusCode -ge 200 -and $result.StatusCode -lt 400) {
            return $result
        }
        Start-Sleep -Milliseconds 400
    }
    Write-Warn "$Label did not answer $Url within $TimeoutSeconds seconds."
    return $null
}

function Get-ProcessIdentity {
    param([int]$TargetProcessId)
    $process = Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return $null
    }
    $startTime = $null
    try {
        $startTime = $process.StartTime.ToUniversalTime().ToString("o")
    }
    catch {
        $startTime = $null
    }
    $commandLine = $null
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $TargetProcessId" -ErrorAction SilentlyContinue
    if ($cim) {
        $commandLine = [string]$cim.CommandLine
    }
    return [pscustomobject]@{
        ProcessId   = $TargetProcessId
        StartTime   = $startTime
        CommandLine = $commandLine
    }
}

# A recorded process is ours only if the PID still exists, started at the recorded
# time (guards against PID reuse) and still runs the recorded command line.
function Test-EntryOwned {
    param($Entry)
    if (-not $Entry -or -not $Entry.pid) {
        return $false
    }
    $current = Get-ProcessIdentity -TargetProcessId ([int]$Entry.pid)
    if (-not $current) {
        return $false
    }
    if ($Entry.start_time -and $current.StartTime) {
        try {
            $expected = [datetime]::Parse([string]$Entry.start_time).ToUniversalTime()
            $actual = [datetime]::Parse([string]$current.StartTime).ToUniversalTime()
            if ([math]::Abs(($actual - $expected).TotalSeconds) -gt 2) {
                return $false
            }
        }
        catch {
            return $false
        }
    }
    if ($Entry.command_line -and $current.CommandLine) {
        if ($current.CommandLine -ne [string]$Entry.command_line) {
            return $false
        }
    }
    return $true
}

function Get-TaskkillPath {
    return (Join-Path $env:SystemRoot "System32\taskkill.exe")
}

# Kills only a verified launcher-owned process tree. Returns $true when a kill ran.
function Stop-ServiceEntry {
    param($Entry)
    if (-not (Test-EntryOwned $Entry)) {
        return $false
    }
    $taskkill = Get-TaskkillPath
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $taskkill /PID ([int]$Entry.pid) /T /F 2>&1 | Out-Null
    $killExit = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($killExit -ne 0) {
        throw "taskkill failed for $($Entry.name) (PID $($Entry.pid)) with exit code $killExit."
    }
    return $true
}

function Save-LauncherState {
    param(
        [string]$Path,
        $State
    )
    $json = $State | ConvertTo-Json -Depth 6
    $temporary = "$Path.tmp"
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($temporary, $json, $utf8)
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Read-LauncherState {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        return (Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

function Wait-ForPortFree {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 10
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-PortOpen $Port)) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    return (-not (Test-PortOpen $Port))
}
