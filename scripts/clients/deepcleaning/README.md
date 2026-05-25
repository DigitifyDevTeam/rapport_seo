# DeepCleaning

Same automation pattern as **Origincbd** (separate session files only).

## GMB (like Origincbd)

**1. Prepare session** (important — same as Origincbd when it works):

```powershell
python scripts/clients/deepcleaning/gmb_ui_prepare.py
```

In the browser: Google → fiche **DeepCleaning** → **Interactions avec les clients** → Performance visible → **ENTER**.

The terminal must print a URL with `#mpd=` (like Origincbd).  
If you only see `business.google.com/locations`, you pressed ENTER too early — run prepare again.

**2. Extract KPIs** (automated, same script as Origincbd):

```powershell
python scripts/clients/deepcleaning/gmb_ui_extract.py 2026-04
```

If KPIs stay empty but the fiche screenshot exists, open Performance yourself then:

```powershell
python scripts/clients/deepcleaning/gmb_ui_capture.py 2026-04
```

**3. Monthly report:**

```powershell
python -m src.pipeline.run_monthly --client deepcleaning --month 2026-04
```

Sessions: **`gmb-deepcleaning.json`**, `clarity-deepcleaning.json` (same Google
account as other clients is fine — each file stores that brand's Performance URL).

Copy to the VPS:

- ``outputs/_sessions/gmb-deepcleaning.json``

Then on the server: ``SEO_REPORT_REFRESH_GMB_UI=1 ./scripts/docker_run_client.sh deepcleaning 2026-04``

### Clarity « Pages supérieures »

Re-capture after pulling the latest code (tab fix):

```powershell
Remove-Item outputs\deepcleaning\2026-04\clarity_card_popular_pages.png -ErrorAction SilentlyContinue
node scripts/clarity_ui_extract.js --session outputs\_sessions\clarity-deepcleaning.json --out outputs\deepcleaning\2026-04\clarity_ui.json --project-id lfjtuxge3c --period-start 2026-03-26 --period-end 2026-04-26 --skip-widgets popular_products --auto
```

## VPS / Docker

Sessions captured on Windows **do not work** on the server IP (Google login wall / CAPTCHA).

On the VPS, refresh the GMB session once per client:

```bash
chmod +x scripts/docker_gmb_login.sh
./scripts/docker_gmb_login.sh deepcleaning
```

Then run the report:

```bash
docker compose build seo-reports
./scripts/docker_run_client.sh deepcleaning 2026-04
```

Copy `outputs/_sessions/gmb-deepcleaning.json` from the VPS if you also run reports locally.

## Clarity

```powershell
node scripts/clients/deepcleaning/clarity_ui_login.js
node scripts/clients/deepcleaning/clarity_ui_extract.js 2026-04
```
