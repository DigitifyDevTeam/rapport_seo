#!/usr/bin/env python3
"""Check VPS readiness before running the monthly pipeline."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

OK = 0
WARN = 1
FAIL = 2


def _status(level: int, msg: str) -> int:
    prefix = {OK: "OK", WARN: "WARN", FAIL: "FAIL"}[level]
    print(f"[{prefix}] {msg}")
    return level


def main() -> int:
    worst = OK

    env_path = _PROJECT_ROOT / ".env"
    if env_path.is_file():
        worst = max(worst, _status(OK, f".env found at {env_path}"))
    else:
        worst = max(worst, _status(FAIL, ".env missing — copy from your PC"))

    secrets = _PROJECT_ROOT / "secrets"
    token = secrets / "google_oauth_token.json"
    client_secret = secrets / "google_oauth_client_secret.json"
    if token.is_file():
        worst = max(worst, _status(OK, f"OAuth token: {token}"))
    else:
        worst = max(
            worst,
            _status(
                FAIL,
                f"Missing {token} — copy the whole secrets/ folder from Windows",
            ),
        )
    if client_secret.is_file():
        worst = max(worst, _status(OK, f"OAuth client: {client_secret}"))
    else:
        worst = max(worst, _status(WARN, f"Missing {client_secret}"))

    from src.config import env as cfg_env
    from src.pipeline.drive_upload import _drive_folder_id, _drive_service, drive_upload_enabled

    if drive_upload_enabled() and _drive_folder_id():
        service = _drive_service()
        if service is None:
            worst = max(worst, _status(FAIL, "Drive enabled but no credentials (copy secrets/)"))
        else:
            try:
                meta = service.files().get(
                    fileId=_drive_folder_id(), fields="id,name").execute()
                worst = max(
                    worst,
                    _status(OK, f"Drive folder: {meta.get('name')} ({meta.get('id')})"),
                )
            except Exception as exc:  # noqa: BLE001
                worst = max(worst, _status(FAIL, f"Drive folder not accessible: {exc}"))
    else:
        worst = max(worst, _status(WARN, "GOOGLE_DRIVE_FOLDER_ID not set or upload disabled"))

    pkg = _PROJECT_ROOT / "package.json"
    if pkg.is_file():
        worst = max(worst, _status(OK, "package.json present (npm ci will work)"))
    else:
        worst = max(worst, _status(FAIL, "package.json missing — git pull or copy from repo"))

    node = shutil.which("node")
    if node:
        worst = max(worst, _status(OK, f"node: {node}"))
    else:
        worst = max(worst, _status(WARN, "node not in PATH — Clarity UI capture will be skipped"))

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        worst = max(worst, _status(OK, f"PDF export: {soffice}"))
    else:
        worst = max(
            worst,
            _status(WARN, "LibreOffice not found — PPTX only, no PDF on this server"),
        )

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            browser.close()
        worst = max(worst, _status(OK, "Playwright Chromium launches"))
    except Exception as exc:  # noqa: BLE001
        worst = max(
            worst,
            _status(
                WARN,
                "Playwright cannot launch (missing system libs like libatk). "
                f"Use SEO_REPORT_SKIP_CONNECTORS=gmb,clarity in .env and run UI capture "
                f"on Windows, or ask the host to install browser dependencies. ({exc})",
            ),
        )

    skip = (cfg_env("SEO_REPORT_SKIP_CONNECTORS") or "").strip()
    if skip:
        worst = max(worst, _status(OK, f"SEO_REPORT_SKIP_CONNECTORS={skip}"))

    print()
    if worst >= FAIL:
        print("Fix FAIL items before scheduling the monthly job.")
        return 1
    if worst >= WARN:
        print("Warnings are OK if you run GMB/Clarity on Windows or reuse outputs/ PNGs.")
        return 0
    print("Server looks ready for a full pipeline run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
