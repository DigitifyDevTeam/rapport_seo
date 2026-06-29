# Guivarche Déménagement

| Source | ID / URL |
|--------|----------|
| GA4 | Property `395375607` (guivarche - GA4) |
| Clarity | Project `k23l3ye7zj` — https://guivarche-demenagement.fr |
| GSC | https://guivarche-demenagement.fr/ |

GMB uses the **shared Google account** with DeepCleaning, Origincbd, and Digitify.

Sessions: `clarity-guivarche.json`, `gmb-performance-guivarche.txt` (+ shared `gmb-deepcleaning.json`).

## Clarity

```powershell
node scripts/clients/guivarche/clarity_ui_login.js
node scripts/clients/guivarche/clarity_ui_extract.js 2026-05
```

## GMB

```powershell
python scripts/gmb_ui_prepare_shared_account.py
# or capture Performance URL only:
python scripts/capture_gmb_performance_url.py guivarche --show
python scripts/clients/guivarche/gmb_ui_extract.py 2026-05
```

## One-time UI setup (fixes n/a GMB + Clarity screenshots)

```powershell
python scripts/clients/guivarche/prepare_ui.py
```

Or step by step:

```powershell
node scripts/clients/guivarche/clarity_ui_login.js
python scripts/capture_gmb_performance_url.py guivarche --show
```

## Monthly report

```powershell
python -m src.pipeline.run_monthly --client guivarche --month 2026-05
```

Output: `outputs/guivarche/2026-05/`.
