#!/usr/bin/env python3
"""Quick check that Google Drive upload is configured (no report generation)."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from src.config import env
from src.pipeline.drive_upload import (_drive_folder_id, _drive_service,
                                         drive_upload_enabled)


def main() -> int:
    if not drive_upload_enabled():
        print("GOOGLE_DRIVE_UPLOAD_ENABLED is off")
        return 1
    folder = _drive_folder_id()
    if not folder:
        print("Set GOOGLE_DRIVE_FOLDER_ID in .env")
        return 1
    service = _drive_service()
    if service is None:
        print("No Drive credentials — configure service account or OAuth")
        return 1
    meta = service.files().get(fileId=folder, fields="id,name").execute()
    print(f"OK — can access folder: {meta.get('name')} ({meta.get('id')})")
    creds_hint = env("GOOGLE_DRIVE_CREDENTIALS") or env(
        "GOOGLE_APPLICATION_CREDENTIALS") or env("GOOGLE_OAUTH_TOKEN_FILE")
    print(f"Credentials: {creds_hint or '(OAuth token)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
