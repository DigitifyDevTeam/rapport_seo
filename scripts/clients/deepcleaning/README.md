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

### One-time: fix file ownership (SFTP "permission denied")

Docker writes files as **root**. Your SSH user (`new`) cannot overwrite them by
SFTP/FileZilla. Run once on the VPS (and after each report run if you forget):

```bash
chmod +x scripts/fix_outputs_perms.sh
./scripts/fix_outputs_perms.sh
```

`./scripts/docker_run_client.sh` now fixes permissions automatically after each run.

**Copying only `gmb-deepcleaning.json` to the server is not enough.** Google blocks
that session on the VPS IP (CAPTCHA / login wall). Your local report works because
Search runs on your home IP.

### Recommended: sync GMB files from Windows

After a good local run:

```powershell
python -m src.pipeline.run_monthly --client deepcleaning --month 2026-04
```

Copy to the VPS (same paths under `rapport_seo/`):

- `outputs/deepcleaning/2026-04/gmb_ui.json`
- `outputs/deepcleaning/2026-04/gmb_business_card.png`
- `outputs/deepcleaning/2026-04/gmb_card_*.png`

Example (from your PC, adjust host/user):

```bash
scp outputs/deepcleaning/2026-04/gmb_* new@ns304208:~/public_html/rapport_seo/outputs/deepcleaning/2026-04/
```

Then on the server (no refresh flag):

```bash
./scripts/docker_run_client.sh deepcleaning 2026-04
```

`ui_manual_capture: true` in `config/clients.yaml` skips the browser when those files exist.

### Alternative: login once on the VPS

```bash
chmod +x scripts/docker_gmb_prepare.sh
./scripts/docker_gmb_prepare.sh deepcleaning
```

Open Performance, press ENTER when the URL contains `#mpd=`. Then run the report.

## Clarity

```powershell
node scripts/clients/deepcleaning/clarity_ui_login.js
node scripts/clients/deepcleaning/clarity_ui_extract.js 2026-04
```
