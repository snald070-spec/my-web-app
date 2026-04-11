#Requires -Version 5.1
<#
.SYNOPSIS  Start Cloudflare Tunnel for Draw Phase 2

.DESCRIPTION
  Cloudflared tunnel 을 설치하고 실행합니다.
  처음 실행 시 --setup 플래그를 사용하세요.

.PARAMETER Setup
  cloudflared 를 winget 으로 설치하고 Cloudflare 로그인 후 터널을 생성합니다.

.PARAMETER TunnelName
  생성/실행할 터널 이름 (기본값: draw-backend)

.EXAMPLE
  .\scripts\start-cloudflare-tunnel.ps1 -Setup
  .\scripts\start-cloudflare-tunnel.ps1
#>
param(
    [switch]$Setup,
    [string]$TunnelName = "draw-backend"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$configFile = Join-Path $PSScriptRoot "cloudflared-config.yml"

# ── Install via winget ────────────────────────────────────────────────────────
if ($Setup) {
    Write-Host "[setup] Installing cloudflared via winget ..."
    winget install --id Cloudflare.cloudflared -e --silent
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[setup] winget install failed. Download manually from:"
        Write-Host "  https://github.com/cloudflare/cloudflared/releases/latest"
        exit 1
    }

    Write-Host "[setup] Logging in to Cloudflare (browser will open) ..."
    cloudflared tunnel login

    Write-Host "[setup] Creating tunnel: $TunnelName ..."
    $result = cloudflared tunnel create $TunnelName 2>&1
    Write-Host $result

    Write-Host ""
    Write-Host "======================================================"
    Write-Host " Setup complete. Next steps:"
    Write-Host " 1. Copy the tunnel UUID from the output above."
    Write-Host " 2. Edit scripts/cloudflared-config.yml:"
    Write-Host "    - Set tunnel: <YOUR_TUNNEL_UUID>"
    Write-Host "    - Set credentials-file path"
    Write-Host "    - Set hostname to your actual domain"
    Write-Host " 3. Add a CNAME record in Cloudflare DNS:"
    Write-Host "    CNAME draw.example.com -> <TUNNEL_UUID>.cfargotunnel.com"
    Write-Host " 4. Run this script without -Setup to start the tunnel."
    Write-Host "======================================================"
    exit 0
}

# ── Start tunnel ──────────────────────────────────────────────────────────────
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "[error] cloudflared not found. Run with -Setup first." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $configFile)) {
    Write-Host "[error] Config not found: $configFile" -ForegroundColor Red
    exit 1
}

Write-Host "[cloudflare-tunnel] Starting tunnel with config: $configFile"
cloudflared tunnel --config $configFile run $TunnelName