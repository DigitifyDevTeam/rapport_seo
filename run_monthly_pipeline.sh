#!/usr/bin/env bash
# Alias for cron_monthly_reports.sh (same pipeline).
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cron_monthly_reports.sh" "$@"
