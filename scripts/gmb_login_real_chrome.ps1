# Open REAL Google Chrome (not Playwright automation) for GMB login.
# Google often blocks sign-in inside Playwright; this path always works.
#
# Usage (from project root):
#   .\scripts\gmb_login_real_chrome.ps1
#   .\scripts\gmb_login_real_chrome.ps1 -Client origincbd

param(
    [string]$Client = "origincbd",
    [int]$Port = 9222
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Profile = Join-Path $Root "outputs\_sessions\chrome-debug-gmb-$Client"
$Session = Join-Path $Root "outputs\_sessions\gmb-$Client.json"
$Chrome = "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"

if (-not (Test-Path $Chrome)) {
    $Chrome = "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
}
if (-not (Test-Path $Chrome)) {
    Write-Error "Google Chrome not found. Install Chrome or set path manually."
    exit 1
}

New-Item -ItemType Directory -Force -Path $Profile | Out-Null

$searchQ = switch ($Client) {
    "origincbd" { "Origine+CBD+Paris" }
    "deepcleaning" { "Deep+Cleaning+Lavage+nettoyage+Colombes" }
    "digitify" { "Digitify+agence+web+Lyon" }
    "cchabitat" { "Concept+Confort+Habitat" }
    default { $Client }
}
$startUrl = "https://www.google.com/search?hl=fr&q=$searchQ"

Write-Host ""
Write-Host "=== GMB login via REAL Chrome (client: $Client) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Step 1: Chrome opens with remote debugging on port $Port"
Write-Host "Step 2: Sign in + open Performances in THAT Chrome window"
Write-Host "Step 3: When ready, run in another terminal:"
Write-Host ""
Write-Host "  cd `"$Root`""
Write-Host "  python scripts/gmb_ui_login.py --out outputs/_sessions/gmb-$Client.json --cdp http://127.0.0.1:$Port"
Write-Host ""

Start-Process -FilePath $Chrome -ArgumentList @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$Profile",
    $startUrl
)

Write-Host "Chrome started. Complete login + Performance, then run the python command above."
Write-Host "Press ENTER here when Performance is visible in Chrome..."
Read-Host

Set-Location $Root
python scripts/gmb_ui_login.py --out "outputs/_sessions/gmb-$Client.json" --cdp "http://127.0.0.1:$Port"
