# Deploy SEO reports on your VPS (monthly automation)

This guide runs the **4 production clients** (`cchabitat`, `digitify`, `deepcleaning`, `origincbd`) automatically on the **26th of each month**, then **uploads** each report (PPTX + PDF) to **Google Drive**.

## What runs automatically

| Step | Detail |
|------|--------|
| **VPS panel timer** | Runs **one file**: `run_monthly_pipeline.sh` on day **26** each month |
| Pipeline inside that file | `python -m src.pipeline.monthly_job` (4 clients + Drive upload) |
| Period | Current month when run on the 26th (26→26 via `REPORT_CYCLE_DAY`) |
| Logs | `logs/monthly_pipeline_YYYY-MM-DD_HHMMSS.log` |

You do **not** need Linux cron or systemd if your host already has a “scheduled task / timer” UI.

### VPS panel timer (recommended — one file only)

1. Upload the project to the VPS (e.g. `/opt/rapport_seo`).
2. Install dependencies (section 1–2 below).
3. Make the launcher executable:

```bash
chmod +x /opt/rapport_seo/run_monthly_pipeline.sh
```

4. In your **VPS control panel** (scheduled task / timer / cron job that accepts **one script path**):

| Field | Value |
|-------|--------|
| **Script / command** | `/opt/rapport_seo/run_monthly_pipeline.sh` |
| **Schedule** | Monthly, day **26**, time **06:00** (adjust timezone to Europe/Paris) |
| **User** | Same user that owns the project and `.env` |

5. Test once manually (SSH):

```bash
/opt/rapport_seo/run_monthly_pipeline.sh
tail -f /opt/rapport_seo/logs/monthly_pipeline_*.log
```

On **26 May**, the panel starts that script → all 4 reports run → files go to Google Drive.

If the panel asks for **Python** instead of a shell script, use:

```text
/opt/rapport_seo/.venv/bin/python -m src.pipeline.monthly_job
```

(same behaviour; logs only if you redirect them in the panel).

Manual test (without the shell wrapper):

```bash
cd /opt/rapport_seo
source .venv/bin/activate
python -m src.pipeline.monthly_job --month 2026-04
```

## 1. Server prerequisites (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv git \
  libreoffice \
  tesseract-ocr tesseract-ocr-fra \
  nodejs npm \
  xvfb

# Playwright browsers (GMB UI)
cd /opt/rapport_seo
python -m playwright install chromium
python -m playwright install-deps chromium

# Puppeteer / Clarity (if not already installed)
npm ci   # if package-lock exists at repo root
```

Create a dedicated user:

```bash
sudo useradd -r -m -d /opt/rapport_seo -s /bin/bash seo-reports
sudo chown -R seo-reports:seo-reports /opt/rapport_seo
```

## 2. Install the application

```bash
sudo -u seo-reports -H bash
cd /opt/rapport_seo
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with production values
```

Copy from your Windows machine (OneDrive):

- `.env` (secrets)
- `secrets/` (Google OAuth tokens, service account JSON)
- `outputs/_sessions/` (GMB + Clarity browser sessions — **required** for UI capture)
- `templates/seo_report_template.pptx`

### One-time Google logins (on the VPS or copy sessions)

GMB and Clarity need saved browser sessions:

```bash
python scripts/gmb_ui_login.py --out outputs/_sessions/gmb-default.json
python scripts/clients/cchabitat/google_oauth_login.py   # CC Habitat GSC/GMB account
```

Run these once with a display (SSH `-X` or `xvfb-run`).

## 3. `.env` for scheduling + Drive

```env
# 26 → 26 reporting windows (default in code)
REPORT_CYCLE_DAY=26
SEO_REPORT_SCHEDULE_DAY=26
SEO_REPORT_SCHEDULE_HOUR=6
SEO_REPORT_SCHEDULE_MINUTE=0

# Optional: restrict to explicit client ids (comma-separated)
# SEO_REPORT_CLIENT_IDS=cchabitat,digitify,deepcleaning,origincbd

# Google Drive destination (folder ID from the URL)
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
GOOGLE_DRIVE_UPLOAD_ENABLED=true
GOOGLE_DRIVE_UPLOAD_PPTX=true
GOOGLE_DRIVE_UPLOAD_PDF=true

# Usually same as GA4/GSC service account:
GOOGLE_APPLICATION_CREDENTIALS=./secrets/google_service_account.json
# Or a dedicated key:
# GOOGLE_DRIVE_CREDENTIALS=./secrets/google_drive_service_account.json
```

### Google Drive setup (service account)

1. Google Cloud Console → enable **Google Drive API**.
2. Create a **service account** JSON key → save as `secrets/google_service_account.json`.
3. In Google Drive, create a folder (e.g. `Rapports SEO`).
4. **Share** that folder with the service account email (`xxx@xxx.iam.gserviceaccount.com`) as **Editor**.
5. Copy the folder ID from the URL:  
   `https://drive.google.com/drive/folders/FOLDER_ID_HERE` → set `GOOGLE_DRIVE_FOLDER_ID`.

Uploaded layout (``GOOGLE_DRIVE_FOLDER_ID`` = your ``rapport_seo`` folder):

```
rapport_seo/
  Digitify.fr/
    2026-05/
      digitify_2026-05_report.pptx
      digitify_2026-05_report.pdf
  DeepCleaning.fr/
    2026-05/
      ...
  CC-Habitat.com/
    2026-05/
      ...
```

### OAuth alternative

If you use OAuth instead of a service account, re-run `python scripts/google_oauth_login.py` after adding Drive scope, or add `https://www.googleapis.com/auth/drive` to your token. Set `GOOGLE_DRIVE_CREDENTIALS` only when using a separate key file.

## 4. Other schedulers (optional)

Only use these if you **do not** have a VPS panel timer.

- **systemd:** `deploy/install-systemd.sh` + `seo-reports.timer`
- **Linux crontab:** point it at the same file: `/opt/rapport_seo/run_monthly_pipeline.sh`
- **APScheduler** (`python -m src.pipeline.scheduler`): keeps Python running 24/7 — not recommended

## 5. Headless UI (GMB + Clarity)

The pipeline opens Chrome via Playwright/Puppeteer. On a server without a display:

```bash
# systemd service sets DISPLAY=:99 — start virtual framebuffer:
sudo apt install xvfb
sudo -u seo-reports Xvfb :99 -screen 0 1920x1080x24 &
```

Or wrap the job:

```bash
xvfb-run -a python -m src.pipeline.monthly_job
```

Expect **30–90+ minutes** for all 4 clients (browser captures are slow).

## 6. Checklist before going live

- [ ] `.env` filled (GA4, GSC, Clarity, Google OAuth, Drive folder ID)
- [ ] `outputs/_sessions/` copied or logins done on VPS
- [ ] LibreOffice installed (PDF export)
- [ ] Test: `python -m src.pipeline.monthly_job --month YYYY-MM`
- [ ] Files appear under `GOOGLE_DRIVE_FOLDER_ID/<project-name>/YYYY-MM/`
- [ ] VPS panel timer set to `/opt/rapport_seo/run_monthly_pipeline.sh` on day 26

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Drive upload skipped | Set `GOOGLE_DRIVE_FOLDER_ID`; share folder with service account |
| GMB/Clarity empty | Refresh sessions with login scripts on the VPS |
| PDF missing | Install `libreoffice`; check `soffice` in PATH |
| Wrong month | On day &lt; 26, job uses previous month; on 26+ uses current month |
