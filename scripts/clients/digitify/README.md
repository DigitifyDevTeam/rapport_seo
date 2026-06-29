# Digitify.fr

Same automation pattern as **DeepCleaning** (separate session files only).

| Source | ID / URL |
|--------|----------|
| GA4 | Property `366533803` (Digitify - GA4) |
| Clarity | Project `wck8kvahx2` — https://digitify.fr |
| GSC | https://digitify.fr/ |

Sessions: `clarity-digitify.json`, **`gmb-digitify.json`** (same Google account as other
clients is OK — each file keeps that brand's Performance URL).

## Clarity

```powershell
node scripts/clients/digitify/clarity_ui_login.js
node scripts/clients/digitify/clarity_ui_extract.js 2026-04
```

## GMB (like DeepCleaning)

**1. Prepare session**

```powershell
python scripts/clients/digitify/gmb_ui_prepare.py
```

In the browser: Google → fiche **Digitify** → **Interactions avec les clients** → Performance visible → **ENTER**.

The terminal must print a URL with `#mpd=`. If you only see `business.google.com/locations`, run prepare again.

**2. Extract KPIs**

```powershell
python scripts/clients/digitify/gmb_ui_extract.py 2026-04
```

If KPIs stay empty:

```powershell
python scripts/clients/digitify/gmb_ui_capture.py 2026-04
```

**3. Monthly report**

```powershell
python -m src.pipeline.run_monthly --client digitify --month 2026-04
```

Adjust `ui_search_query` in `config/clients.yaml` if the Google Search label differs from `Digitify`.

## VPS / Docker

Same as Origincbd: after Windows prepare (URL with `#mpd=`), copy
`outputs/_sessions/gmb-digitify.json` to the VPS, then:

```bash
./scripts/docker_run_client.sh digitify 2026-04
```
