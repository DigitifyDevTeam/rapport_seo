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

Sessions: `gmb-deepcleaning.json`, `clarity-deepcleaning.json` (not Origincbd files).

## Clarity

```powershell
node scripts/clients/deepcleaning/clarity_ui_login.js
node scripts/clients/deepcleaning/clarity_ui_extract.js 2026-04
```
