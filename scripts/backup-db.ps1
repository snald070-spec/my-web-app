# backup-db.ps1 — SQLite daily backup for draw_phase2_backend
# Usage: .\backup-db.ps1 [-KeepDays 7]
#
# Recommended: register in Windows Task Scheduler to run daily at 03:00.
#   schtasks /Create /SC DAILY /TN "DrawBackupDB" /TR "powershell -NonInteractive -File C:\path\backup-db.ps1" /ST 03:00

param(
    [int]$KeepDays = 7
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SourceDb    = Join-Path $ProjectRoot "backend\app.db"
$BackupDir   = Join-Path $PSScriptRoot "db-backups"
$LogFile     = Join-Path $PSScriptRoot "logs\backup.log"

# ── Ensure directories exist ─────────────────────────────────────────────────
@($BackupDir, (Split-Path $LogFile)) | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ | Out-Null }
}

function Write-Log {
    param([string]$Msg)
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "[$ts] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# ── Guard: source DB must exist ───────────────────────────────────────────────
if (-not (Test-Path $SourceDb)) {
    Write-Log "ERROR: Source DB not found: $SourceDb"
    exit 1
}

# ── Copy with timestamp ───────────────────────────────────────────────────────
$timestamp  = (Get-Date).ToString("yyyyMMdd_HHmmss")
$DestDb     = Join-Path $BackupDir "app_backup_$timestamp.db"
Copy-Item -Path $SourceDb -Destination $DestDb
$size = (Get-Item $DestDb).Length
Write-Log "OK: Backup created → $DestDb ($size bytes)"

# ── Prune old backups ─────────────────────────────────────────────────────────
$cutoff = (Get-Date).AddDays(-$KeepDays)
Get-ChildItem -Path $BackupDir -Filter "app_backup_*.db" | Where-Object {
    $_.LastWriteTime -lt $cutoff
} | ForEach-Object {
    Remove-Item $_.FullName
    Write-Log "PRUNED: $($_.Name)"
}

Write-Log "Backup complete. Kept last $KeepDays day(s) of backups."
