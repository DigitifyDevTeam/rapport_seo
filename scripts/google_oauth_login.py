"""One-time OAuth login to generate a refreshable token file.

This script performs an interactive OAuth login (opens a browser), then
writes an "authorized user" token JSON file that the pipeline can refresh
automatically.

Usage:
    python scripts/google_oauth_login.py

Prereqs:
    - Put your OAuth client secret JSON at:
        secrets/google_oauth_client_secret.json
      (or set GOOGLE_OAUTH_CLIENT_SECRET_FILE in `.env`)

Output:
    - secrets/google_oauth_token.json
      (or GOOGLE_OAUTH_TOKEN_FILE in `.env`)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Running as `python scripts/google_oauth_login.py` does not put the repo root
# on sys.path; ensure imports like `src.*` work the same as `python -m ...`.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

from src.config import PROJECT_ROOT, env
from src.connectors.google_auth import GA4_SCOPES, GSC_SCOPES, GMB_SCOPES


def _resolve_client_secret_path() -> Path:
    configured = Path(
        env("GOOGLE_OAUTH_CLIENT_SECRET_FILE",
            "./secrets/google_oauth_client_secret.json") or ""
    ).expanduser()
    if configured.exists():
        return configured

    matches = sorted(PROJECT_ROOT.glob("client_secret_*.json"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise FileNotFoundError(
            f"OAuth client secret file not found at {configured} and multiple "
            f"candidates exist in the project root: "
            f"{', '.join(m.name for m in matches)}. "
            "Set GOOGLE_OAUTH_CLIENT_SECRET_FILE in `.env` to the correct JSON."
        )
    raise FileNotFoundError(
        f"OAuth client secret file not found: {configured}\n"
        "Download a **Desktop** OAuth client JSON from Google Cloud Console "
        "and save it as secrets/google_oauth_client_secret.json, or set "
        "GOOGLE_OAUTH_CLIENT_SECRET_FILE in `.env`."
    )


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    client_secret = _resolve_client_secret_path()
    token_file = Path(
        env("GOOGLE_OAUTH_TOKEN_FILE", "./secrets/google_oauth_token.json") or ""
    ).expanduser()

    try:
        data = json.loads(client_secret.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read OAuth client file: {client_secret}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid OAuth client JSON: {client_secret}") from exc

    if "installed" not in data:
        raise ValueError(
            f"{client_secret} is not a Desktop OAuth client JSON (expected "
            f"a top-level 'installed' key). Create an **Application de bureau** "
            f"OAuth client in Cloud Console, or this script cannot use "
            f"InstalledAppFlow.run_local_server()."
        )

    scopes = sorted(set(GA4_SCOPES + GSC_SCOPES + GMB_SCOPES))

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret),
                                                     scopes=scopes)
    creds = flow.run_local_server(port=0)

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    print(f"Wrote token file to {token_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

