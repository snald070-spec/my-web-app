param(
    [switch]$Restart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $PSScriptRoot "logs"

if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

function Write-LauncherLog {
    param(
        [string]$Message
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path (Join-Path $logDir "launcher.log") -Value "[$timestamp] $Message"
}

function Test-PortListening {
    param(
        [int]$Port
    )

    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Wait-PortListening {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 20
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortListening -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }

    return $false
}

function Get-ListeningProcessId {
    param(
        [int]$Port
    )

    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $connection) {
        return $null
    }

    return [int]$connection.OwningProcess
}

function Start-ServiceProcess {
    param(
        [string]$Name,
        [int]$Port,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$StdOutFile,
        [string]$StdErrFile
    )

    Write-Host "[start-services] $Name check port $Port ..."
    if (Test-PortListening -Port $Port) {
        $existingPid = Get-ListeningProcessId -Port $Port

        if ($Restart -and $null -ne $existingPid) {
            Stop-Process -Id $existingPid -Force
            Write-LauncherLog "Stopped existing $Name on port $Port (PID $existingPid) due to -Restart"
            Write-Host "[start-services] stopped existing $Name PID=$existingPid"
        }
        else {
            Write-LauncherLog "$Name already listening on port $Port (PID $existingPid). Use -Restart to replace stale process."
            Write-Host "[start-services] $Name already running on port $Port (PID $existingPid)"
            return
        }
    }

    if (-not (Test-Path -LiteralPath $FilePath)) {
        throw "$Name executable not found: $FilePath"
    }

    $startProcessArgs = @{
        FilePath = $FilePath
        ArgumentList = $ArgumentList
        WorkingDirectory = $WorkingDirectory
        WindowStyle = "Hidden"
        RedirectStandardOutput = $StdOutFile
        RedirectStandardError = $StdErrFile
        PassThru = $true
    }

    $process = Start-Process @startProcessArgs

    Write-LauncherLog "Started $Name on port $Port with PID $($process.Id)"
    Write-Host "[start-services] started $Name PID=$($process.Id), waiting for port $Port ..."

    if (-not (Wait-PortListening -Port $Port -TimeoutSeconds 20)) {
        throw "$Name failed to listen on port $Port within timeout(20s). Check logs in $logDir"
    }

    $listeningPid = Get-ListeningProcessId -Port $Port
    Write-Host "[start-services] $Name is listening on port $Port (PID $listeningPid)"
}

$backendPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $backendPython)) {
    $backendPython = Join-Path $repoRoot "backend\venv\Scripts\python.exe"
}
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$npmCmd = (Get-Command npm.cmd -ErrorAction Stop).Source

$backendArgs = @{
    Name = "backend"
    Port = 8000
    FilePath = $backendPython
    ArgumentList = @("-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000")
    WorkingDirectory = $backendDir
    StdOutFile = (Join-Path $logDir "backend.out.log")
    StdErrFile = (Join-Path $logDir "backend.err.log")
}

Start-ServiceProcess @backendArgs

Start-Sleep -Seconds 2

$frontendArgs = @{
    Name = "frontend"
    Port = 8080
    FilePath = $npmCmd
    ArgumentList = @("run", "dev", "--", "--host", "0.0.0.0", "--port", "8080")
    WorkingDirectory = $frontendDir
    StdOutFile = (Join-Path $logDir "frontend.out.log")
    StdErrFile = (Join-Path $logDir "frontend.err.log")
}

Start-ServiceProcess @frontendArgs

Write-LauncherLog "Startup script completed"
Write-Host "[start-services] startup completed"