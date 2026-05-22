"""CC Habitat — OAuth login for GSC + GMB (cchabitat.seo@gmail.com).

Opens a browser; sign in with the **CC Habitat** Google account (not the agency
account used for other clients). Writes a dedicated token file.

Usage::

    python scripts/clients/cchabitat/google_oauth_login.py

Output (default)::

    secrets/google_oauth_token_cchabitat.json

Set in ``.env``::

    GOOGLE_OAUTH_TOKEN_FILE_CCHABITAT=./secrets/google_oauth_token_cchabitat.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

from src.config import PROJECT_ROOT, env
from src.connectors.google_auth import GMB_SCOPES, GSC_SCOPES

_ACCOUNT = "cchabitat"


def _resolve_client_secret_path() -> Path:
    for key in (
        f"GOOGLE_OAUTH_CLIENT_SECRET_FILE_{_ACCOUNT.upper()}",
        "GOOGLE_OAUTH_CLIENT_SECRET_FILE",
    ):
        raw = env(key, "")
        if raw:
            path = Path(raw).expanduser()
            if path.exists():
                return path
    configured = PROJECT_ROOT / "secrets" / "google_oauth_client_secret.json"
    if configured.exists():
        return configured
    matches = sorted(PROJECT_ROOT.glob("client_secret_*.json"))
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(
        "OAuth client secret JSON not found. Set GOOGLE_OAUTH_CLIENT_SECRET_FILE "
        "in .env or place secrets/google_oauth_client_secret.json"
    )


def _resolve_token_path() -> Path:
    raw = env(f"GOOGLE_OAUTH_TOKEN_FILE_{_ACCOUNT.upper()}", "")
    if raw:
        return Path(raw).expanduser()
    return PROJECT_ROOT / "secrets" / f"google_oauth_token_{_ACCOUNT}.json"


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    client_secret = _resolve_client_secret_path()
    token_file = _resolve_token_path()
    data = json.loads(client_secret.read_text(encoding="utf-8"))
    if "installed" not in data:
        raise ValueError(
            f"{client_secret} must be a Desktop OAuth client JSON (top-level "
            f"'installed' key)."
        )

    scopes = sorted(set(GSC_SCOPES + GMB_SCOPES))
    print(
        "Sign in with the CC Habitat Google account (cchabitat.seo@gmail.com), "
        "not the agency account used for Origincbd / DeepCleaning / Digitify."
    )

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), scopes=scopes)
    creds = flow.run_local_server(port=0)

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    print(f"Wrote token file to {token_file}")
    print("List Search Console properties:")
    print("  python scripts/clients/cchabitat/gsc_list_sites.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
