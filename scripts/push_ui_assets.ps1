# Copy ONLY portable UI assets from Windows to the VPS:
#   - outputs/_sessions/*.json   (GMB + Clarity session cookies)
#   - outputs/<client>/<month>/  (already-captured PNG screenshots)
#
# Chrome user-data profile folders (chrome-profile-*) are SKIPPED because
# they contain native Windows binaries that crash on Linux/Docker.
#
# Run in PowerShell on your PC:
#   .\scripts\push_ui_assets.ps1 -Server new@YOUR_HOST
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

$sessionsDir = Join-Path $Root "outputs\_sessions"
if (Test-Path $sessionsDir) {
    Write-Host "Syncing session JSON files (Chrome profile dirs are skipped)..."
    ssh $Server "mkdir -p '$RemoteDir/outputs/_sessions'" | Out-Null
    Get-ChildItem $sessionsDir -Filter "*.json" -File | ForEach-Object {
        scp $_.FullName "${Server}:${RemoteDir}/outputs/_sessions/"
    }
    Write-Host "OK sessions"
} else {
    Write-Warning "Missing $sessionsDir - run GMB/Clarity login on Windows first."
}

if ($Client -and $Month) {
    $out = Join-Path $Root "outputs\$Client\$Month"
    if (Test-Path $out) {
        ssh $Server "mkdir -p '$RemoteDir/outputs/$Client'" | Out-Null
        scp -r $out "${Server}:${RemoteDir}/outputs/$Client/"
        Write-Host "OK outputs/$Client/$Month"
    } else {
        Write-Warning "Missing $out"
    }
} else {
    $outputs = Join-Path $Root "outputs"
    Get-ChildItem $outputs -Directory | Where-Object { $_.Name -ne "_sessions" } | ForEach-Object {
        $clientDir = $_.FullName
        ssh $Server "mkdir -p '$RemoteDir/outputs/$($_.Name)'" | Out-Null
        Get-ChildItem $clientDir -Directory | ForEach-Object {
            scp -r $_.FullName "${Server}:${RemoteDir}/outputs/$($_.Parent.Name)/"
        }
    }
    Write-Host "OK all client output folders"
}

Write-Host ""
Write-Host "Done. On the VPS run:"
Write-Host "  ./scripts/docker_run_client.sh <client> <YYYY-MM>"
