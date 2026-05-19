"""Shared Google authentication helpers.

Supports two auth modes:

1. Service account JSON (recommended for server-to-server when possible)
   via ``GOOGLE_APPLICATION_CREDENTIALS``.
2. OAuth "authorized user" token JSON (recommended for GA4/GSC/GBP in many
   agency setups) via:
   - ``GOOGLE_OAUTH_CLIENT_SECRET_FILE`` (OAuth client JSON)
   - ``GOOGLE_OAUTH_TOKEN_FILE`` (generated token JSON)

3. OAuth fields directly in ``.env`` (Playground-style), per product:

   - ``GOOGLE_ANALYTICS_*`` (GA4)
   - ``GOOGLE_SEARCH_CONSOLE_*`` (GSC)
   - ``GOOGLE_BUSINESS_PROFILE_*`` (GBP)

   Expected keys mirror OAuth JSON: ``client_id``, ``client_secret``,
   ``refresh_token``, ``access_token`` (optional), ``token_type`` (optional),
   ``expires_in`` (optional seconds from issue time), ``scope`` (optional).

Callers should use :func:`get_google_credentials` which will prefer a
service account when configured, otherwise fall back to OAuth.

If both a shared ``GOOGLE_OAUTH_TOKEN_FILE`` and per-product ``.env`` OAuth
fields are present, the **token file wins** so a single refresh token setup
is not accidentally overridden by stale Playground variables.

You can use **one** OAuth refresh token for all Google products (recommended),
or **split** token files per product by setting:

- ``GOOGLE_OAUTH_TOKEN_FILE_GA4``
- ``GOOGLE_OAUTH_TOKEN_FILE_GSC``
- ``GOOGLE_OAUTH_TOKEN_FILE_GMB``

Each of those falls back to ``GOOGLE_OAUTH_TOKEN_FILE`` when unset.
Optional per-product client secret JSON paths use the same suffix pattern.
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path

from src.config import env

logger = logging.getLogger(__name__)

GA4_SCOPES = ["https://www.googleapis.com/auth/analytics"]
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters"]
GMB_SCOPES = ["https://www.googleapis.com/auth/business.manage"]

# Union of every scope the app may need across connectors. Loading the OAuth
# token with this union ensures the access_token returned by Google's refresh
# endpoint is valid for ALL Google APIs the pipeline calls, and prevents one
# connector from saving a "narrowed" token file that would break the next
# connector in the same run (or the next day when it tries to refresh).
ALL_GOOGLE_SCOPES: list[str] = sorted({*GA4_SCOPES, *GSC_SCOPES, *GMB_SCOPES})


def _credentials_path() -> Path | None:
    raw = env("GOOGLE_APPLICATION_CREDENTIALS")
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.exists():
        logger.warning("Google credentials file not found at %s", path)
        return None
    return path


@lru_cache(maxsize=8)
def get_service_account_credentials(scopes: tuple[str, ...]):
    """Return ``google.oauth2.service_account.Credentials`` or ``None``."""
    path = _credentials_path()
    if path is None:
        return None
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_file(
        str(path), scopes=list(scopes)
    )


def _oauth_token_path_for(suffix: str | None = None) -> Path | None:
    if suffix:
        raw = env(f"GOOGLE_OAUTH_TOKEN_FILE_{suffix.upper()}")
        if raw:
            path = Path(raw).expanduser()
            if path.exists():
                return path
            logger.info("OAuth token file for %s not found at %s, falling back",
                          suffix.upper(), path)
    raw = env("GOOGLE_OAUTH_TOKEN_FILE", "./secrets/google_oauth_token.json")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.exists() else None


def _oauth_client_secret_path_for(suffix: str | None = None) -> Path | None:
    if suffix:
        raw = env(f"GOOGLE_OAUTH_CLIENT_SECRET_FILE_{suffix.upper()}")
        if raw:
            path = Path(raw).expanduser()
            if path.exists():
                return path
            logger.info("OAuth client secret for %s not found at %s, falling "
                          "back", suffix.upper(), path)
    raw = env("GOOGLE_OAUTH_CLIENT_SECRET_FILE",
              "./secrets/google_oauth_client_secret.json")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.exists() else None


def _env_prefix_for_suffix(token_suffix: str | None) -> str | None:
    if not token_suffix:
        return None
    key = token_suffix.strip().lower()
    if key == "ga4":
        return "GOOGLE_ANALYTICS"
    if key == "gsc":
        return "GOOGLE_SEARCH_CONSOLE"
    if key == "gmb":
        return "GOOGLE_BUSINESS_PROFILE"
    return None


def _get_env(prefix: str, name: str) -> str | None:
    return env(f"{prefix}_{name}")


def _oauth_env_fingerprint(prefix: str | None) -> str:
    """Stable hash of OAuth-related env so lru_cache invalidates on .env edits."""
    parts: list[str] = []
    if prefix:
        for name in (
            "CLIENT_ID",
            "CLIENT_SECRET",
            "REFRESH_TOKEN",
            "ACCESS_TOKEN",
            "TOKEN_URI",
            "SCOPE",
            "EXPIRES_IN",
            "EXPIRES_AT",
            "ISSUED_AT",
        ):
            val = _get_env(prefix, name)
            if val:
                parts.append(f"{prefix}_{name}={val}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest


def _oauth_token_file_fingerprint(token_suffix: str | None) -> str:
    path = _oauth_token_path_for(token_suffix)
    if path is None or not path.exists():
        return ""
    try:
        return str(int(path.stat().st_mtime_ns))
    except OSError:
        return ""


def _oauth_cache_fingerprint(token_suffix: str | None) -> str:
    prefix = _env_prefix_for_suffix(token_suffix)
    env_fp = _oauth_env_fingerprint(prefix) if prefix else ""
    file_fp = _oauth_token_file_fingerprint(token_suffix)
    return "|".join(p for p in (env_fp, file_fp) if p)


def _oauth_expiry_naive_utc(expires_at_raw: str | None, issued_at_raw: str | None,
                           expires_in_raw: str | None):
    from datetime import datetime, timedelta, timezone

    if expires_at_raw:
        try:
            if expires_at_raw.isdigit():
                expiry = datetime.fromtimestamp(int(expires_at_raw), tz=timezone.utc)
            else:
                raw = expires_at_raw.replace("Z", "+00:00")
                expiry = datetime.fromisoformat(raw)
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
            return expiry.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            return None

    if issued_at_raw and expires_in_raw:
        try:
            issued = datetime.fromisoformat(issued_at_raw.replace("Z", "+00:00"))
            if issued.tzinfo is None:
                issued = issued.replace(tzinfo=timezone.utc)
            seconds = int(expires_in_raw)
            return (issued + timedelta(seconds=seconds)).astimezone(
                timezone.utc).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _oauth_credentials_from_env(prefix: str, scopes: tuple[str, ...]):
    client_id = _get_env(prefix, "CLIENT_ID")
    client_secret = _get_env(prefix, "CLIENT_SECRET")
    refresh_token = _get_env(prefix, "REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        return None

    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        logger.warning("google-auth is not installed")
        return None

    access_token = _get_env(prefix, "ACCESS_TOKEN")
    token_uri = (_get_env(prefix, "TOKEN_URI")
                  or env("GOOGLE_OAUTH_TOKEN_URI",
                         "https://oauth2.googleapis.com/token"))
    scopes_list = list(scopes)
    env_scope = _get_env(prefix, "SCOPE")
    if env_scope:
        scopes_list = [s for s in env_scope.split() if s]

    # OAuth Playground / token JSON often includes expires_in relative to the
    # token issue time, not "now". Do not treat expires_in alone as a valid
    # absolute expiry unless we also know when the token was issued.
    expires_at_raw = _get_env(prefix, "EXPIRES_AT")
    issued_at_raw = _get_env(prefix, "ISSUED_AT")
    expires_in_raw = _get_env(prefix, "EXPIRES_IN")
    expiry = _oauth_expiry_naive_utc(expires_at_raw, issued_at_raw, expires_in_raw)

    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes_list,
        expiry=expiry,
    )


def _maybe_refresh_and_persist_env_oauth(prefix: str, creds) -> None:
    try:
        from google.auth.transport.requests import Request
    except ImportError:
        return

    if not creds:
        return
    # Without a known absolute expiry, a stored access_token from .env is not
    # trustworthy — always obtain a fresh access_token via refresh_token.
    needs_refresh = bool(creds.refresh_token) and (
        creds.expired or not creds.token or creds.expiry is None)
    if needs_refresh:
        try:
            creds.refresh(Request())
        except Exception as exc:  # noqa: BLE001
            logger.warning("OAuth (.env) refresh failed for %s: %s", prefix, exc)


def _read_token_file_scopes(token_path: Path) -> list[str]:
    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw = data.get("scopes")
    if isinstance(raw, list):
        return [str(s) for s in raw if s]
    if isinstance(raw, str):
        return [s for s in raw.split() if s]
    return []


def _credentials_from_authorized_user_file(token_path: Path, scopes: tuple[str, ...]):
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        logger.warning("google-auth is not installed")
        return None

    # IMPORTANT: load with the *union* of (already-saved scopes, requested scopes,
    # the app's full scope union). This guarantees:
    #   1. The refreshed access_token is valid across every Google API the
    #      pipeline may call (no more "GA4 connector narrows the token to
    #      analytics-only and GSC fails with 403 insufficient scopes" the
    #      next time GSC tries to use it).
    #   2. We never overwrite the on-disk token file with a narrower scope set.
    saved_scopes = _read_token_file_scopes(token_path)
    union_scopes = sorted(set(saved_scopes) | set(scopes) | set(ALL_GOOGLE_SCOPES))

    try:
        creds = Credentials.from_authorized_user_file(str(token_path),
                                                     scopes=union_scopes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read OAuth token file %s: %s",
                       token_path, exc)
        return None

    granted_scopes = set(getattr(creds, "scopes", []) or [])
    missing = [s for s in scopes if s not in granted_scopes]
    if missing:
        logger.warning(
            "OAuth token %s is missing required scopes: %s. Re-run "
            "`python scripts/google_oauth_login.py` and grant all requested "
            "Google permissions.",
            token_path,
            ", ".join(missing),
        )

    # Refresh if needed.
    try:
        from google.auth.transport.requests import Request
    except ImportError:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:  # noqa: BLE001
            logger.warning("OAuth credentials refresh failed: %s", exc)
            return None

        # Persist updated token to disk. Re-assert the union scopes so we never
        # write a narrower scope set than what's already valid for this user.
        try:
            creds_scopes = set(getattr(creds, "scopes", []) or [])
            preserved = sorted({*creds_scopes, *union_scopes})
            try:
                creds._scopes = preserved  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
        except OSError:
            pass

    return creds


@lru_cache(maxsize=64)
def get_oauth_credentials(scopes: tuple[str, ...], token_suffix: str | None,
                          env_fingerprint: str):
    """Return ``google.oauth2.credentials.Credentials`` or ``None``.

    Resolution order:
    1) Authorized-user token JSON on disk (``GOOGLE_OAUTH_TOKEN_FILE`` or
       per-product override), when the file exists
    2) Playground-style variables in ``.env`` for the product suffix
    """
    token_path = _oauth_token_path_for(token_suffix)
    if token_path is not None:
        file_creds = _credentials_from_authorized_user_file(token_path, scopes)
        if file_creds is not None:
            return file_creds

    prefix = _env_prefix_for_suffix(token_suffix)
    if prefix:
        env_creds = _oauth_credentials_from_env(prefix, scopes)
        if env_creds is not None:
            _maybe_refresh_and_persist_env_oauth(prefix, env_creds)
            return env_creds

    return None


def get_google_credentials(scopes: tuple[str, ...],
                            *, oauth_token_suffix: str | None = None):
    """Return Google credentials for the requested scopes or ``None``.

    Preference order:
    1) service account credentials
    2) OAuth authorized-user credentials
    """
    creds = get_service_account_credentials(scopes)
    if creds is not None:
        return creds
    fp = _oauth_cache_fingerprint(oauth_token_suffix)
    return get_oauth_credentials(scopes, oauth_token_suffix, fp)


def oauth_bootstrap_hint() -> dict[str, str]:
    """Return expected OAuth file locations (for error messages/UI)."""
    client = _oauth_client_secret_path_for()
    token = _oauth_token_path_for()
    return {
        "client_secret_file": str(client) if client else "",
        "token_file": str(token) if token else "",
    }

