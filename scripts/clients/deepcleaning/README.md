# DeepCleaning

GMB uses the **shared Google account** workflow with Origincbd and Digitify: one login, three Performance URLs.

## Shared account (recommended)

One browser login saves cookies; each brand gets its own `#mpd=` URL.

```powershell
cd rapport_seo
python scripts/gmb_ui_prepare_shared_account.py
```

On the VPS (noVNC at `http://<vps-ip>:7900`, password `vnc`):

```bash
./scripts/gmb_ui_prepare_vnc.sh
```

Steps inside the script:

1. DeepCleaning prepare → `outputs/_sessions/gmb-deepcleaning.json`
2. Origincbd Performance URL → `gmb-performance-origincbd.txt`
3. Digitify Performance URL → `gmb-performance-digitify.txt`

Verify:

```powershell
python scripts/check_gmb_vps_sessions.py
```

Expect OK for `deepcleaning`, `origincbd`, and `digitify`.

### Copy to VPS

Upload:

- `gmb-deepcleaning.json` (required for all three)
- `gmb-performance-origincbd.txt`
- `gmb-performance-digitify.txt`

```bash
./scripts/import_gmb_sessions.sh deepcleaning ~/gmb-deepcleaning.json
./scripts/import_gmb_sessions.sh perf origincbd ~/gmb-performance-origincbd.txt
./scripts/import_gmb_sessions.sh perf digitify ~/gmb-performance-digitify.txt
```

### VPS hygiene (shared session)

Remove these if they exist **without** a valid `#mpd=` URL — they block fallback to `gmb-deepcleaning.json`:

- `outputs/_sessions/gmb-origincbd.json`
- `outputs/_sessions/gmb-digitify.json`

Digitify and Origincbd are configured with `ui_session_client: deepcleaning` in `config/clients.yaml`.

## DeepCleaning-only prepare

If you only need DeepCleaning:

```powershell
python scripts/clients/deepcleaning/gmb_ui_prepare.py
```

Press **ENTER** only when the saved URL contains **`#mpd=`**.

## Why this works on the VPS

The monthly cron opens the saved Performance URL and **rewrites `from`/`to` to the report month** — no manual date change. It fails if the session stopped at `business.google.com/locations` only (no `#mpd=`).

## Monthly (automatic on VPS)

```bash
./scripts/docker_run_client.sh deepcleaning 2026-05
./scripts/docker_run_all_clients.sh
```

Re-run shared prepare only if Google logs you out.

## Clarity

```powershell
node scripts/clients/deepcleaning/clarity_ui_login.js
node scripts/clients/deepcleaning/clarity_ui_extract.js 2026-04
```

## VPS notes

- **Permission denied on SFTP?** `./scripts/fix_outputs_perms.sh`
- **GMB check:** `python scripts/check_gmb_vps_sessions.py`
