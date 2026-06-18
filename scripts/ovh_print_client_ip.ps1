# Show your current public IP (for SSH_ALLOWED_IP_NEW in .env).
# Run on your Windows PC in the office, not on the server.
#
#   .\scripts\ovh_print_client_ip.ps1
#
$ErrorActionPreference = "Stop"
$ip = (Invoke-WebRequest -Uri "https://api.ipify.org" -UseBasicParsing).Content.Trim()
Write-Host "Your current public IP (put in .env as SSH_ALLOWED_IP_NEW):"
Write-Host "  $ip"
Write-Host ""
Write-Host "Server (digitify.fr) is NOT this IP — use OVH_SERVER_IP=94.23.210.145"
Write-Host ""
Write-Host "On the OVH host after you have shell access:"
Write-Host "  sudo ./scripts/ovh_update_ssh_allowlist.sh $ip"
