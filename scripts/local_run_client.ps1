# Local full UI capture for one client (Windows, visible Chrome recommended once).
# Usage: .\scripts\local_run_client.ps1 deepcleaning 2026-04

param(
    [Parameter(Mandatory = $true)][string]$Client,
    [string]$Month = "2026-04"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:SEO_REPORT_REFRESH_GMB_UI = "1"

Write-Host "=== 1) Per-client GMB Performance URL (one-time if missing) ===" -ForegroundColor Cyan
$perfFile = "outputs\_sessions\gmb-performance-$Client.txt"
if (-not (Test-Path $perfFile)) {
    python scripts/capture_gmb_performance_url.py $Client --show
}

Write-Host "=== 2) Monthly report (GMB + Clarity + GA4/GSC) ===" -ForegroundColor Cyan
python -m src.pipeline.run_monthly --client $Client --month $Month

Write-Host "Done. Check outputs\$Client\$Month\" -ForegroundColor Green
