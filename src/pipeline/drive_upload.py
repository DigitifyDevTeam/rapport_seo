"""Upload finished reports to Google Drive.

Configure in ``.env``::

    GOOGLE_DRIVE_FOLDER_ID=<folder id from Drive URL>
    GOOGLE_DRIVE_CREDENTIALS=./secrets/google_service_account.json  # optional
    GOOGLE_DRIVE_UPLOAD_ENABLED=true

Share the target folder with the service account email (Editor), or use an
OAuth token that has Drive access to that folder.

Uploaded layout (``GOOGLE_DRIVE_FOLDER_ID`` = e.g. ``rapport_seo``)::

    rapport_seo/
      Digitify.fr/
        2026-04/
          digitify_2026-04_report.pptx
          digitify_2026-04_report.pdf
      DeepCleaning.fr/
        2026-04/
          ...
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from src.config import ClientConfig, env
from src.connectors.google_auth import (get_google_credentials,
                                          get_service_account_credentials)
from src.periods import Period
from src.pipeline.run_monthly import ReportArtifacts

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive",)


def drive_upload_enabled() -> bool:
    raw = (env("GOOGLE_DRIVE_UPLOAD_ENABLED", "true") or "true").lower()
    return raw not in ("0", "false", "no", "off")


def _drive_folder_id() -> str | None:
    folder_id = (env("GOOGLE_DRIVE_FOLDER_ID") or "").strip()
    return folder_id or None


def _drive_credentials():
    creds_path = (env("GOOGLE_DRIVE_CREDENTIALS") or "").strip()
    if creds_path:
        from google.oauth2 import service_account

        path = Path(creds_path).expanduser()
        if path.is_file():
            return service_account.Credentials.from_service_account_file(
                str(path), scopes=list(DRIVE_SCOPES))
        logger.warning("GOOGLE_DRIVE_CREDENTIALS not found: %s", path)
    creds = get_service_account_credentials(DRIVE_SCOPES)
    if creds is not None:
        return creds
    return get_google_credentials(DRIVE_SCOPES, oauth_token_suffix="drive")


def _drive_service():
    creds = _drive_credentials()
    if creds is None:
        logger.warning(
            "Google Drive credentials missing; set GOOGLE_APPLICATION_CREDENTIALS "
            "or GOOGLE_OAUTH_TOKEN_FILE with Drive scope")
        return None
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _find_child_folder(service, parent_id: str, name: str) -> str | None:
    safe_name = name.replace("'", "\\'")
    query = (
        f"'{parent_id}' in parents and "
        f"name = '{safe_name}' and "
        "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    result = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
        .execute()
    )
    files = result.get("files") or []
    if files:
        return str(files[0]["id"])
    return None


def _project_folder_name(client: ClientConfig) -> str:
    """Drive subfolder for a client (project display name)."""
    override = (env(f"GOOGLE_DRIVE_PROJECT_NAME_{client.id.upper()}") or "").strip()
    if override:
        return override
    raw = (client.name or client.id).strip()
    # Drive folder names must not contain path separators.
    return raw.replace("/", "-").replace("\\", "-")


def _ensure_folder(service, parent_id: str, name: str) -> str:
    existing = _find_child_folder(service, parent_id, name)
    if existing:
        return existing
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(body=body, fields="id").execute()
    folder_id = str(created["id"])
    logger.info("Created Drive folder %r (%s)", name, folder_id)
    return folder_id


def _upload_file(service, local_path: Path, parent_id: str) -> str | None:
    from googleapiclient.http import MediaFileUpload

    if not local_path.is_file():
        logger.warning("Skip upload; file missing: %s", local_path)
        return None
    mime, _ = mimetypes.guess_type(str(local_path))
    media = MediaFileUpload(
        str(local_path),
        mimetype=mime or "application/octet-stream",
        resumable=True,
    )
    body = {"name": local_path.name, "parents": [parent_id]}
    created = (
        service.files()
        .create(body=body, media_body=media, fields="id, webViewLink")
        .execute()
    )
    file_id = str(created.get("id") or "")
    logger.info("Uploaded %s → Drive file %s", local_path.name, file_id)
    return file_id


def upload_report_artifacts(
    client: ClientConfig,
    period: Period,
    artifacts: ReportArtifacts,
) -> bool:
    """Upload PPTX/PDF (and optional data JSON) for one client report."""
    if not drive_upload_enabled():
        logger.info("Drive upload disabled (GOOGLE_DRIVE_UPLOAD_ENABLED)")
        return False
    root_folder = _drive_folder_id()
    if not root_folder:
        logger.info("GOOGLE_DRIVE_FOLDER_ID not set, skipping Drive upload")
        return False

    service = _drive_service()
    if service is None:
        return False

    project_folder = _ensure_folder(service, root_folder, _project_folder_name(client))
    month_folder = _ensure_folder(service, project_folder, period.label)

    upload_pptx = (env("GOOGLE_DRIVE_UPLOAD_PPTX", "true") or "true").lower()
    upload_pdf = (env("GOOGLE_DRIVE_UPLOAD_PDF", "true") or "true").lower()
    upload_data = (env("GOOGLE_DRIVE_UPLOAD_JSON", "false") or "false").lower()

    ok = True
    if upload_pptx not in ("0", "false", "no", "off"):
        ok = _upload_file(service, artifacts.pptx_path, month_folder) is not None and ok
    if upload_pdf not in ("0", "false", "no", "off") and artifacts.pdf_path:
        ok = _upload_file(service, artifacts.pdf_path, month_folder) is not None and ok
    if upload_data not in ("0", "false", "no", "off"):
        ok = _upload_file(service, artifacts.data_path, month_folder) is not None and ok

    return ok
