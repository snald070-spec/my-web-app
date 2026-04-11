#Requires -Version 5.1
<#
.SYNOPSIS  Draw Phase 2 - Pre-Deploy Production Readiness Check
.PARAMETER ApplyProduction  Apply APP_ENV=production to backend/.env after passing all checks.
#>
param([switch]$ApplyProduction)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot    = Split-Path -Parent $PSScriptRoot
$backendEnv  = Join-Path $repoRoot "backend\.env"
$frontendDir = Join-Path $repoRoot "frontend"
$distDir     = Join-Path $frontendDir "dist"

$pass = 0; $fail = 0; $warn = 0
$failures = [System.Collections.Generic.List[string]]::new()

function Write-Check {
    param([bool]$OK, [string]$Label, [string]$Detail = "", [bool]$IsWarn = $false)
    if ($OK) {
        Write-Host "  [OK]   $Label" -ForegroundColor Green; $script:pass++
    } elseif ($IsWarn) {
        Write-Host "  [WARN] $Label$(if ($Detail) { ' -- ' + $Detail })" -ForegroundColor Yellow; $script:warn++
    } else {
        Write-Host "  [FAIL] $Label$(if ($Detail) { ' -- ' + $Detail })" -ForegroundColor Red
        $script:fail++; $script:failures.Add($Label)
    }
}

function Get-EnvValue {
    param([string]$File, [string]$Key)
    $line = Get-Content $File | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -split "=", 2)[1].Trim()
}

Write-Host ""
Write-Host "=============================================="
Write-Host "  Draw Phase 2 - Production Readiness Check"
Write-Host "=============================================="

# ---- 1. Backend .env ----
Write-Host "`n[1] Backend .env"
$envExists = Test-Path $backendEnv
Write-Check -OK $envExists -Label "backend/.env exists"
if (-not $envExists) {
    Write-Host "  -> Create from .env.example" -ForegroundColor Red
} else {
    $secretKey   = Get-EnvValue $backendEnv "SECRET_KEY"
    $appEnv      = Get-EnvValue $backendEnv "APP_ENV"
    $corsOrigins = Get-EnvValue $backendEnv "CORS_ALLOW_ORIGINS"
    $dbUrl       = Get-EnvValue $backendEnv "DATABASE_URL"
    $loginBlock  = Get-EnvValue $backendEnv "LOGIN_BLOCK_MINUTES"

    $defaultKey = "change-me-in-production-use-openssl-rand-hex-32"
    Write-Check -OK (($secretKey -ne $defaultKey) -and ($secretKey -ne "")) `
        -Label "SECRET_KEY is not default" -Detail "Run: openssl rand -hex 32"

    Write-Check -OK (($secretKey -ne $null) -and ($secretKey.Length -ge 32)) `
        -Label "SECRET_KEY length >= 32"

    $isEnvDev = ($appEnv -ne "production")
    Write-Check -OK (-not $isEnvDev) -Label "APP_ENV=production" `
        -Detail "Current: $appEnv  (change for deployment)" -IsWarn:$isEnvDev

    $hasLocalhost = ($corsOrigins -match "localhost") -or ($corsOrigins -match "127\.0\.0\.1")
    Write-Check -OK (-not $hasLocalhost) -Label "CORS has no localhost" `
        -Detail "Current: $corsOrigins" -IsWarn:$true

    Write-Check -OK (-not [string]::IsNullOrWhiteSpace($dbUrl)) -Label "DATABASE_URL is set"

    $blockMin = if ($loginBlock) { [int]$loginBlock } else { 0 }
    Write-Check -OK ($blockMin -ge 10) -Label "LOGIN_BLOCK_MINUTES >= 10" `
        -Detail "Current: $blockMin" -IsWarn:($blockMin -lt 10)
}

# ---- 2. Frontend ----
Write-Host "`n[2] Frontend build / env"
Write-Check -OK (Test-Path $distDir) -Label "frontend/dist build exists" `
    -Detail "Run: npm run build"

$apiUrl = $null
$envProd  = Join-Path $frontendDir ".env.production"
$envLocal = Join-Path $frontendDir ".env.local"
if (Test-Path $envProd)  { $apiUrl = Get-EnvValue $envProd  "VITE_API_BASE_URL" }
if (-not $apiUrl -and (Test-Path $envLocal)) { $apiUrl = Get-EnvValue $envLocal "VITE_API_BASE_URL" }

$hasApiUrl = -not [string]::IsNullOrWhiteSpace($apiUrl)
Write-Check -OK $hasApiUrl -Label "VITE_API_BASE_URL is set" `
    -Detail "Set in frontend/.env.production: VITE_API_BASE_URL=https://..."
if ($hasApiUrl) {
    Write-Check -OK $apiUrl.StartsWith("https://") -Label "VITE_API_BASE_URL uses HTTPS" `
        -Detail "Current: $apiUrl"
}

# ---- 3. Android ----
Write-Host "`n[3] Android release build (optional)"
Write-Check -OK (Test-Path (Join-Path $frontendDir "android\keystore.properties")) `
    -Label "android/keystore.properties exists"
Write-Check -OK (Test-Path (Join-Path $frontendDir "android\app\upload-keystore.jks")) `
    -Label "android/app/upload-keystore.jks exists"
$localProps = Join-Path $frontendDir "android\local.properties"
if (Test-Path $localProps) {
    Write-Check -OK (-not [string]::IsNullOrWhiteSpace((Get-EnvValue $localProps "sdk.dir"))) `
        -Label "android/local.properties sdk.dir set"
} else {
    Write-Check -OK $false -Label "android/local.properties exists" -IsWarn:$true
}

# ---- 4. DB Backup ----
Write-Host "`n[4] DB backup"
$backupDir = Join-Path $PSScriptRoot "db-backups"
if (Test-Path $backupDir) {
    $latestBackup = Get-ChildItem $backupDir -Filter "*.db" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestBackup) {
        $ageH = ((Get-Date) - $latestBackup.LastWriteTime).TotalHours
        $roundedH = [math]::Round($ageH, 1)
        Write-Check -OK ($ageH -le 24) -Label "DB backup age <= 24h" `
            -Detail "Last: $($latestBackup.Name) ($roundedH h ago)" -IsWarn:($ageH -gt 24)
    } else {
        Write-Check -OK $false -Label "DB backup file exists" `
            -Detail "Run: scripts/backup-db.ps1" -IsWarn:$true
    }
} else {
    Write-Check -OK $false -Label "db-backups folder exists" -IsWarn:$true
}

# ---- Summary ----
$total = $pass + $fail + $warn
Write-Host ""
Write-Host "=============================================="
Write-Host "  Result: $pass/$total passed  |  Fail: $fail  |  Warn: $warn"

if ($fail -gt 0) {
    Write-Host "`n  [BLOCKED] Fix the following before deploying:" -ForegroundColor Red
    foreach ($f in $failures) { Write-Host "    x $f" -ForegroundColor Red }
    Write-Host "=============================================="
    exit 1
}

Write-Host "  All required checks passed" -ForegroundColor Green

if ($ApplyProduction -and $envExists) {
    Write-Host "`n  [APPLY] Setting APP_ENV=production in backend/.env ..." -ForegroundColor Cyan
    $content    = Get-Content $backendEnv -Raw
    $newContent = $content -replace "(?m)^APP_ENV\s*=.*$", "APP_ENV=production"
    [System.IO.File]::WriteAllText($backendEnv, $newContent, [System.Text.Encoding]::UTF8)
    Write-Host "  Done. Remember to update CORS_ALLOW_ORIGINS to your production domain." -ForegroundColor Yellow
}
Write-Host "=============================================="