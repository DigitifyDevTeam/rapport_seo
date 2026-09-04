# Guivarche Déménagement

| Source | ID / URL |
|--------|----------|
| GA4 | Property `538491692` (guivarche - GA4) |
| Clarity | Project `wck8kvahx2` — https://guivarche-demenagement.fr |
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

## GA4

Property id in `config/clients.yaml` must be `538491692` (not the old `395375607`, which returns 403).

Optional UI cards (browser screenshots):

```powershell
python scripts/clients/guivarche/ga4_ui_prepare.py
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

## SimpleSERP (Guivarche vs Maillard)

Public shared dashboards — no login. The monthly report opens each shared
URL and clicks the **1m** comparison preset (one-month MoM), then scrapes
Keyword / Current / Previous / Change.

Tables are split across up to **4 slides** (≈13 rows each) so they stay
inside the slide panel. Titles look like
`Comparaison mots-clés (Guivarche vs Maillard) — 1/4`.

| Brand | Shared URL |
|-------|------------|
| Guivarche | https://app.simpleserp.io/shared/0afa0719-07ac-4bce-9802-f999960d6225 |
| Maillard | https://app.simpleserp.io/shared/9af8870c-de85-4c95-a194-0e88733564e4 |

```powershell
python scripts/simpleserp_shared_extract.py --client guivarche --month 2026-07
```

Outputs: `outputs/guivarche/<month>/simpleserp_guivarche.json`,
`simpleserp_maillard.json`.

Skip with `SEO_REPORT_SKIP_UI_CONNECTORS=simpleserp` (reuse existing JSON).

### Custom date range (compare tables only)

For a one-off deck with **only** the Guivarche vs Maillard comparison slides
(custom SimpleSERP dates, no GA4/GSC/GMB/Clarity):

```powershell
python scripts/run_keyword_compare_only.py --client guivarche --from-date 01/08/2026 --to-date 01/09/2026
```

On the VPS (Docker):

```bash
bash scripts/docker_run_keyword_compare.sh guivarche 01/08/2026 01/09/2026
```

Output: `outputs/guivarche/compare_2026-08-01_2026-09-01/keyword_compare_report.pptx`

## Monthly report

```powershell
python -m src.pipeline.run_monthly --client guivarche --month 2026-07
```

Output: `outputs/guivarche/2026-07/`.
