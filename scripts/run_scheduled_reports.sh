#!/usr/bin/env bash
# Deprecated alias — use the project root launcher instead:
#   /opt/rapport_seo/run_monthly_pipeline.sh
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${ROOT}/run_monthly_pipeline.sh" "$@"
