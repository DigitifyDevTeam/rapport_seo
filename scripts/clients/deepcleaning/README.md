# DeepCleaning

Same automation pattern as **Origincbd** (own session file per client).

## GMB — fully automatic on the VPS

**One-time** on the server (SSH with TTY, same IP as monthly cron):

```bash
chmod +x scripts/docker_gmb_prepare.sh scripts/fix_outputs_perms.sh
./scripts/docker_gmb_prepare.sh deepcleaning
```

In the browser: sign in → **Deep Cleaning** → click **Interactions avec les clients** →
wait for **Performance** → press **ENTER** only when the terminal shows a URL with `#mpd=`.

Verify:

```bash
docker compose run --rm --no-TTY seo-reports python scripts/check_gmb_vps_sessions.py
```

**Every month** (cron or manual):

```bash
./scripts/docker_run_client.sh deepcleaning          # auto month from .env
./scripts/docker_run_all_clients.sh                  # all clients + Drive
```

The pipeline opens Performance in Docker, captures KPIs + PNGs for the **new**
`outputs/deepcleaning/YYYY-MM/` folder. No copy from Windows.

Repeat `./scripts/docker_gmb_prepare.sh deepcleaning` only if Google logs you out.

## Clarity

```powershell
node scripts/clients/deepcleaning/clarity_ui_login.js
node scripts/clients/deepcleaning/clarity_ui_extract.js 2026-04
```

On the VPS, `clarity-deepcleaning.json` is enough if the session stays valid.

## Local Windows (optional)

```powershell
python scripts/clients/deepcleaning/gmb_ui_prepare.py
python -m src.pipeline.run_monthly --client deepcleaning --month 2026-04
```

Sessions: `gmb-deepcleaning.json`, `clarity-deepcleaning.json`.

## VPS notes

- **Permission denied on SFTP?** Run `./scripts/fix_outputs_perms.sh` after Docker reports.
- **Cron:** `cron_docker_run_all_clients.sh` checks GMB sessions before running.
