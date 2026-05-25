# DeepCleaning

Same GMB model as **Origincbd**: prepare once on **Windows**, copy one JSON to the VPS, monthly cron captures headless.

## Why this works (and VPS browser login does not)

Origincbd’s `gmb-origincbd.json` contains a **Performance URL with `#mpd=`**. On the server, the pipeline opens that URL directly — no Google Search, no CAPTCHA, no login.

DeepCleaning fails if the session was saved at `business.google.com/locations` only (no `#mpd=`). Redo prepare on Windows.

## One-time: GMB session (Windows)

```powershell
cd rapport_seo
python scripts/clients/deepcleaning/gmb_ui_prepare.py
```

1. Browser opens Google Search for Deep Cleaning.
2. Sign in if needed.
3. Click **« XXX interactions avec les clients »** on the knowledge panel.
4. Wait until **Performance / Vue d’ensemble** is visible.
5. Press **ENTER** in the terminal only when the message shows a URL with **`#mpd=`**.

Check locally:

```powershell
python scripts/check_gmb_vps_sessions.py
```

Expect: `[OK] deepcleaning: OK (#mpd= in gmb-deepcleaning.json)`

## One-time: copy session to VPS

If FileZilla says **permission denied** under `outputs/` (Docker created files as root):

**A — Import folder (recommended)**

1. On the VPS: `mkdir -p ~/gmb_sessions_import`
2. FileZilla upload to **`/home/new/gmb_sessions_import/`** (your home — always writable):
   - `gmb-deepcleaning.json`
   - `gmb-digitify.json` (if needed)
3. SSH:

```bash
cd ~/public_html/rapport_seo
chmod +x scripts/import_gmb_sessions.sh scripts/fix_outputs_perms.sh
./scripts/import_gmb_sessions.sh
```

**B — Fix permissions then upload directly**

```bash
./scripts/fix_outputs_perms.sh
```

Then upload to `public_html/rapport_seo/outputs/_sessions/`.

Do **not** use `docker_gmb_prepare.sh` on the VPS (browser login on OVH fails).

## Monthly (automatic on VPS)

```bash
./scripts/docker_run_client.sh deepcleaning
# or
./scripts/docker_run_all_clients.sh
```

Each month creates `outputs/deepcleaning/YYYY-MM/` and captures fresh GMB KPIs + PNGs. **No** monthly file copy from Windows.

Re-run Windows prepare + re-copy JSON only if Google logs you out.

## Clarity

Session: `clarity-deepcleaning.json` (copy to VPS like GMB if needed).

```powershell
node scripts/clients/deepcleaning/clarity_ui_login.js
node scripts/clients/deepcleaning/clarity_ui_extract.js 2026-04
```

## VPS notes

- **Permission denied on SFTP?** `./scripts/fix_outputs_perms.sh`
- **GMB advisory before cron:** `check_gmb_vps_sessions.py` (warnings only, cron still runs)
