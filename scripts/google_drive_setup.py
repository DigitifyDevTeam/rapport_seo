#!/usr/bin/env python3
"""One-time Google Drive setup using your existing rapport_seo OAuth client.

Reuses ``GOOGLE_OAUTH_CLIENT_SECRET_FILE`` and ``GOOGLE_OAUTH_TOKEN_FILE``.
Adds Drive scope to the token if missing, lists My Drive folders, and can
write ``GOOGLE_DRIVE_FOLDER_ID`` into ``.env``.

Usage:
    python scripts/google_drive_setup.py
    python scripts/google_drive_setup.py --folder-id 1AbCdEfGhIjKlMnOpQrStUvWxYz
    python scripts/google_drive_setup.py --write-env --folder-id <id>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

from src.config import PROJECT_ROOT, env
from src.connectors.google_auth import ALL_GOOGLE_SCOPES, DRIVE_SCOPES

DRIVE_SCOPE = DRIVE_SCOPES[0]


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
    raise FileNotFoundError(
        f"OAuth client secret not found at {configured}. "
        "Use the same Desktop OAuth JSON as GA4/GSC."
    )


def _token_path() -> Path:
    return Path(
        env("GOOGLE_OAUTH_TOKEN_FILE", "./secrets/google_oauth_token.json") or ""
    ).expanduser()


def _token_has_drive_scope(token_path: Path) -> bool:
    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    scopes = data.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return DRIVE_SCOPE in scopes


def _run_oauth_login(client_secret: Path, token_file: Path) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret), scopes=list(ALL_GOOGLE_SCOPES))
    creds = flow.run_local_server(port=0)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    print(f"Updated token (GA4 + GSC + GMB + Drive): {token_file}")


def _parse_folder_id(raw: str) -> str:
    raw = raw.strip()
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", raw)
    if match:
        return match.group(1)
    return raw


def _write_folder_id_to_env(folder_id: str) -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        raise FileNotFoundError(f".env not found at {env_path}")
    text = env_path.read_text(encoding="utf-8")
    key = "GOOGLE_DRIVE_FOLDER_ID="
    if key in text:
        lines = []
        for line in text.splitlines():
            if line.startswith(key):
                lines.append(f"{key}{folder_id}")
            else:
                lines.append(line)
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        with env_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n{key}{folder_id}\n")
    print(f"Wrote {key}{folder_id} to {env_path}")


def _list_drive_folders() -> None:
    from src.pipeline.drive_upload import _drive_service

    service = _drive_service()
    if service is None:
        print("Could not build Drive client — check OAuth token.")
        return
    result = (
        service.files()
        .list(
            q=(
                "mimeType = 'application/vnd.google-apps.folder' "
                "and 'root' in parents and trashed = false"
            ),
            pageSize=50,
            fields="files(id, name)",
            orderBy="name",
        )
        .execute()
    )
    files = result.get("files") or []
    if not files:
        print("No top-level folders in My Drive. Create one (e.g. Rapports SEO) in Drive.")
        return
    print("\nTop-level Drive folders (copy an id into GOOGLE_DRIVE_FOLDER_ID):")
    for item in files:
        print(f"  {item.get('name')!r}  ->  {item.get('id')}")


def _verify_folder(folder_id: str) -> bool:
    from src.pipeline.drive_upload import _drive_service

    service = _drive_service()
    if service is None:
        return False
    meta = service.files().get(fileId=folder_id, fields="id,name").execute()
    print(f"OK — folder: {meta.get('name')} ({meta.get('id')})")
    return True


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Google Drive setup for rapport_seo")
    parser.add_argument(
        "--folder-id",
        help="Drive folder ID or full folder URL",
    )
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Write GOOGLE_DRIVE_FOLDER_ID into .env",
    )
    parser.add_argument(
        "--skip-login",
        action="store_true",
        help="Do not open browser; only list folders or verify",
    )
    args = parser.parse_args()

    client_secret = _resolve_client_secret_path()
    token_file = _token_path()

    if not args.skip_login and not _token_has_drive_scope(token_file):
        print(
            "Your OAuth token does not include Drive yet. "
            "A browser window will open — sign in with the same Google account "
            "used for GA4/GSC and approve all permissions."
        )
        _run_oauth_login(client_secret, token_file)
    elif _token_has_drive_scope(token_file):
        print(f"Token already includes Drive scope: {token_file}")
    else:
        print("Skipping login (--skip-login).")

    if args.folder_id:
        folder_id = _parse_folder_id(args.folder_id)
        if args.write_env:
            _write_folder_id_to_env(folder_id)
        if not _verify_folder(folder_id):
            return 1
        print("\nRun: python scripts/verify_drive_upload.py")
        return 0

    _list_drive_folders()
    print(
        "\nNext: create or pick a folder, then run:\n"
        "  python scripts/google_drive_setup.py --folder-id <ID> --write-env\n"
        "  python scripts/verify_drive_upload.py"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
