# DeepCleaning

Same GMB model as **Origincbd**: prepare once on **Windows**, copy one JSON to the VPS, monthly cron captures headless.

## Why this works (and VPS browser login does not)

Origincbd’s `gmb-origincbd.json` contains a **Performance URL with `#mpd=`**. On the VPS, the monthly cron opens that URL and **rewrites `from`/`to` to the report month** (e.g. May → `from%3D2026-05`) — no manual date change each month.

DeepCleaning fails if the session was saved at `business.google.com/locations` only (no `#mpd=`). Redo prepare on Windows once, copy JSON to the VPS once.

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

**If FileZilla says permission denied** (Docker created root-owned files):

```bash
cd ~/public_html/rapport_seo
git pull
chmod +x scripts/fix_outputs_perms.sh scripts/import_gmb_sessions.sh
./scripts/fix_outputs_perms.sh
```

Then either:

**A) FileZilla** — upload to `outputs/_sessions/gmb-deepcleaning.json`

**B) Upload to HOME first** (always works), then import on SSH:

1. FileZilla: upload `gmb-deepcleaning.json` to `/home/new/` (your home folder)
2. SSH:

```bash
./scripts/import_gmb_sessions.sh deepcleaning ~/gmb-deepcleaning.json
./scripts/import_gmb_sessions.sh digitify ~/gmb-digitify.json
```

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

last chat:

You wanted DeepCleaning (and the monthly VPS cron) to handle Google Business Profile like Origincbd: one-time session setup, then hands-off monthly runs. We traced failures to missing execute bits on cron_docker_run_all_clients.sh, VPS/Docker permission issues on outputs/, sessions without a Performance URL (#mpd=), and—when May capture failed—April KPIs being reused on the May report because the saved URL still had from=2026-04 and stale gmb_ui.json was kept. The workflow is prepare GMB on Windows (gmb_ui_prepare.py), copy gmb-deepcleaning.json to the VPS once (import_gmb_sessions.sh), run reports in Docker as your user (docker_compose_user.sh). We fixed cron script permissions in git, added vps_setup.sh / chmod-after-pull, made GMB advisory-only (no abort), aligned the pipeline with per-client sessions, and added automatic month rewriting in Performance URLs plus rules so another month’s GMB data is never reused; cron can auto-import ~/gmb-*.json. Origincbd-style success on the VPS still needs a valid #mpd= session; if Google shows a login wall on the server IP, refresh the session on Windows and re-import once—not every month.