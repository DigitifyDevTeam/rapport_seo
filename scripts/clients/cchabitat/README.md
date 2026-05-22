# CC-Habitat.com

| Source | ID / account |
|--------|----------------|
| GA4 | `339322990` (agency OAuth — same as other clients) |
| Clarity | `ivgh9to4z7` |
| GSC + GMB | **cchabitat.seo@gmail.com** (dedicated OAuth + Chrome profile) |

Clarity: **4 widgets** (Origincbd layout, incl. Produits populaires).

## 1. Google OAuth (GSC + GMB) — once per machine

Use the **CC Habitat** Google account, not the agency account.

```powershell
python scripts/clients/cchabitat/google_oauth_login.py
python scripts/clients/cchabitat/gsc_list_sites.py
```

Copy the exact `siteUrl` from the list into `config/clients.yaml` → `gsc.site_url` if it differs from `https://cc-habitat.com/`.

## 2. Clarity

```powershell
node scripts/clients/cchabitat/clarity_ui_login.js
node scripts/clients/cchabitat/clarity_ui_extract.js 2026-04
```

## 3. GMB UI

Uses `chrome-profile-gmb-cchabitat` and `gmb-cchabitat.json` (not the agency profile).

```powershell
python scripts/clients/cchabitat/gmb_ui_prepare.py
python scripts/clients/cchabitat/gmb_ui_extract.py 2026-04
```

## 4. Monthly report

```powershell
python -m src.pipeline.run_monthly --client cchabitat --month 2026-04
```

Do **not** store Google passwords in `.env`; OAuth tokens live in `secrets/google_oauth_token_cchabitat.json`.
