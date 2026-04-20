# backup-db.ps1 — SQLite daily backup for draw_phase2_backend
# Usage: .\backup-db.ps1 [-KeepDays 7]
#
# Recommended: register in Windows Task Scheduler to run daily at 03:00.
#   schtasks /Create /SC DAILY /TN "DrawBackupDB" /TR "powershell -NonInteractive -File C:\path\backup-db.ps1" /ST 03:00

param(
    [int]$KeepDays = 7  # 백업 보관주기(일) - 필요시 조정
)
$BackupPolicy = @'
───────────────────────────────────────────────────────────────
[백업 정책 안내]
- db-backups 폴더 내 모든 백업 파일은 $KeepDays일(기본 7일)간 보관 후 자동 삭제됩니다.
- 장기 보관이 필요한 경우, db-backups 폴더의 파일을 외부 스토리지(클라우드/USB 등)로 별도 복사 권장
- .env 등 민감 정보는 외부 반출 시 주의 필요
───────────────────────────────────────────────────────────────
'@
Write-Log $BackupPolicy

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


# ── Copy DB with timestamp ────────────────────────────────────────────────────
$timestamp  = (Get-Date).ToString("yyyyMMdd_HHmmss")
$DestDb     = Join-Path $BackupDir "app_backup_$timestamp.db"
Copy-Item -Path $SourceDb -Destination $DestDb
$size = (Get-Item $DestDb).Length
Write-Log "OK: Backup created → $DestDb ($size bytes)"

# ── 추가: 중요 설정/운영 파일 백업 ─────────────────────────────────────────────
$filesToBackup = @(
    (Join-Path $ProjectRoot ".env"),
    (Join-Path $ProjectRoot "backend\logging_config.py"),
    (Join-Path $ProjectRoot "scripts\cloudflared-config.yml"),
    (Join-Path $ProjectRoot "scripts\nginx-draw.conf"),
    (Join-Path $ProjectRoot "frontend\capacitor.config.json"),
    (Join-Path $ProjectRoot "frontend\package.json"),
    (Join-Path $ProjectRoot "frontend\vite.config.js")
)
foreach ($f in $filesToBackup) {
    if (Test-Path $f) {
        $dest = Join-Path $BackupDir ("$(Split-Path $f -Leaf).bak_$timestamp")
        Copy-Item $f $dest
        Write-Log "OK: Config backup → $dest"
    }
}

# ── 오래된 백업 자동 삭제 ─────────────────────────────────────────────────────
$cutoff = (Get-Date).AddDays(-$KeepDays)
Get-ChildItem -Path $BackupDir -Filter "app_backup_*.db" | Where-Object {
    $_.LastWriteTime -lt $cutoff
} | ForEach-Object {
    Remove-Item $_.FullName
    Write-Log "PRUNED: $($_.Name)"
}

Write-Log "Backup complete. Kept last $KeepDays day(s) of backups."
