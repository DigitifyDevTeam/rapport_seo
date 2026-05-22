# Copy GMB/Clarity sessions and captured PNGs from Windows to the VPS.
# Run in PowerShell on your PC (not on the server).
#
# Usage:
#   .\scripts\push_ui_assets.ps1 -Server new@YOUR_HOST -RemoteDir ~/public_html/rapport_seo
#   .\scripts\push_ui_assets.ps1 -Server new@YOUR_HOST -Client cchabitat -Month 2026-04

param(
    [Parameter(Mandatory = $true)]
    [string] $Server,
    [string] $RemoteDir = "~/public_html/rapport_seo",
    [string] $Client = "",
    [string] $Month = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "Pushing UI assets from $Root to ${Server}:${RemoteDir}"

$sessions = Join-Path $Root "outputs\_sessions"
if (Test-Path $sessions) {
    scp -r $sessions "${Server}:${RemoteDir}/outputs/"
    Write-Host "OK sessions"
} else {
    Write-Warning "Missing $sessions — run GMB/Clarity login scripts on Windows first."
}

if ($Client -and $Month) {
    $out = Join-Path $Root "outputs\$Client\$Month"
    if (Test-Path $out) {
        scp -r $out "${Server}:${RemoteDir}/outputs/$Client/"
        Write-Host "OK outputs/$Client/$Month"
    } else {
        Write-Warning "Missing $out"
    }
} else {
    $outputs = Join-Path $Root "outputs"
    Get-ChildItem $outputs -Directory | Where-Object { $_.Name -ne "_sessions" } | ForEach-Object {
        scp -r $_.FullName "${Server}:${RemoteDir}/outputs/"
    }
    Write-Host "OK all client output folders"
}

Write-Host "Done. On the VPS: python -m src.pipeline.run_monthly --client <id> --month YYYY-MM"
