"""Google Search Console connector."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from src.config import ClientConfig
from src.connectors.google_auth import GSC_SCOPES, get_google_credentials

logger = logging.getLogger(__name__)

ROW_LIMIT = 25000
SC_DOMAIN_PREFIX = "sc-domain:"

_GSC_PERM_WARNED: set[str] = set()
_GSC_PERM_DENIED_SITES: set[str] = set()
_GSC_SITE_LIST_LOGGED: set[tuple[str, str]] = set()


def _gsc_permission_hint_message(site_url: str) -> str:
    return (
        f"[gsc] permission denied for site_url={site_url!r}. "
        "Grant the Google account used for OAuth at least Full access on that "
        "exact Search Console property, or change gsc.site_url to match the "
        "property you really have (domain sc-domain:... vs URL-prefix "
        "https://.../)."
    )


def _is_gsc_insufficient_permission(exc: BaseException) -> bool:
    try:
        from googleapiclient.errors import HttpError as GoogleHttpError
    except ImportError:
        return False

    if not isinstance(exc, GoogleHttpError):
        return False
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None) if resp is not None else None
    if status != 403:
        return False
    text = str(exc).lower()
    return (
        "insufficient permission" in text
        or "does not have sufficient permission" in text
        or "insufficient authentication scopes" in text
        or "insufficientpermissions" in text
    )


def _gsc_scope_hint_message() -> str:
    return (
        "[gsc] the OAuth token appears to be missing required Search Console "
        "scopes. Re-run `python scripts/google_oauth_login.py` and grant the "
        "Search Console permission (webmasters)."
    )


def _gsc_domain_hint(site_url: str) -> str | None:
    if site_url.startswith(SC_DOMAIN_PREFIX):
        return site_url[len(SC_DOMAIN_PREFIX):]
    return None


def _maybe_log_accessible_sites(service, *, client_id: str,
                                configured_site_url: str) -> None:
    key = (client_id, configured_site_url)
    if key in _GSC_SITE_LIST_LOGGED:
        return
    _GSC_SITE_LIST_LOGGED.add(key)

    try:
        resp = service.sites().list().execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[gsc] could not list accessible Search Console sites "
                         "for diagnostics: %s", exc)
        return

    entries = resp.get("siteEntry", []) or []
    urls = [e.get("siteUrl", "") for e in entries if e.get("siteUrl")]

    domain = _gsc_domain_hint(configured_site_url)
    matches: list[str] = []
    if domain:
        d = domain.lower()
        for u in urls:
            ul = u.lower()
            if d in ul.replace(SC_DOMAIN_PREFIX, "").replace("https://", "").replace(
                    "http://", ""):
                matches.append(u)

    if urls:
        preview = "\n".join(f"  - {u}" for u in urls[:25])
        more = "" if len(urls) <= 25 else f"\n  ... ({len(urls) - 25} more)"
        logger.error(
            "[gsc] OAuth account can access %d Search Console properties. "
            "Pick the exact `siteUrl` string for this client and set "
            "`gsc.site_url` in config/clients.yaml:\n%s%s",
            len(urls),
            preview,
            more,
        )

    if matches:
        logger.error(
            "[gsc] Likely matches for domain %r (based on your configured "
            "site_url=%r):\n%s",
            domain,
            configured_site_url,
            "\n".join(f"  - {u}" for u in matches),
        )
    elif domain:
        logger.error(
            "[gsc] No accessible properties obviously matching domain %r. "
            "Either the OAuth account truly has no access, or the site is only "
            "verified as a different property type/string than %r.",
            domain,
            configured_site_url,
        )


def fetch(client: ClientConfig, start: date, end: date) -> dict[str, pd.DataFrame]:
    """Return GSC daily totals plus top queries and pages for the period."""
    site_url = (client.gsc or {}).get("site_url")
    if not site_url:
        logger.info("[gsc] no site configured for %s, skipping", client.id)
        return {}

    creds = get_google_credentials(tuple(GSC_SCOPES), oauth_token_suffix="gsc")
    if creds is None:
        logger.info("[gsc] no Google credentials available, skipping")
        return {}

    try:
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning("[gsc] google-api-python-client is not installed")
        return {}

    service = build("searchconsole", "v1", credentials=creds,
                     cache_discovery=False)

    ghttp = logging.getLogger("googleapiclient.http")
    prev = ghttp.level
    ghttp.setLevel(logging.ERROR)
    try:
        site_url = _resolve_site_url(service, site_url, client.id)
        daily = _query(service, site_url, start, end, ["date"])
        queries = _query(service, site_url, start, end, ["query"],
                         row_limit=1000)
        pages = _query(service, site_url, start, end, ["page"], row_limit=1000)
    finally:
        ghttp.setLevel(prev)

    if site_url in _GSC_PERM_DENIED_SITES:
        _maybe_log_accessible_sites(service,
                                    client_id=client.id,
                                    configured_site_url=site_url)

    if not daily.empty:
        daily["date"] = pd.to_datetime(daily["date"])
        daily = daily.sort_values("date")

    return {"daily": daily, "queries": queries, "pages": pages}


_GSC_RESOLVED_SITE_URL: dict[str, str] = {}


def _list_accessible_site_urls(service) -> list[str]:
    try:
        resp = service.sites().list().execute()
    except Exception:  # noqa: BLE001
        return []
    return [str(e.get("siteUrl", "")).strip()
            for e in (resp.get("siteEntry") or []) if e.get("siteUrl")]


def _domain_from_site_url(site_url: str) -> str:
    raw = site_url.strip()
    if raw.startswith(SC_DOMAIN_PREFIX):
        return raw[len(SC_DOMAIN_PREFIX):]
    raw = raw.replace("https://", "").replace("http://", "")
    return raw.strip("/")


def _resolve_site_url(service, configured: str, client_id: str) -> str:
    if client_id in _GSC_RESOLVED_SITE_URL:
        return _GSC_RESOLVED_SITE_URL[client_id]

    accessible = _list_accessible_site_urls(service)
    if configured in accessible:
        _GSC_RESOLVED_SITE_URL[client_id] = configured
        return configured

    domain = _domain_from_site_url(configured).lower()
    if not domain:
        _GSC_RESOLVED_SITE_URL[client_id] = configured
        return configured

    candidates = [
        f"{SC_DOMAIN_PREFIX}{domain}",
        f"https://{domain}/",
        f"http://{domain}/",
    ]
    for candidate in candidates:
        if candidate in accessible:
            if candidate != configured:
                logger.warning(
                    "[gsc] configured site_url=%r not accessible; falling back "
                    "to verified property %r", configured, candidate,
                )
            _GSC_RESOLVED_SITE_URL[client_id] = candidate
            return candidate

    if accessible:
        logger.warning(
            "[gsc] no Search Console property matches %r for %s. Accessible: %s",
            configured, client_id, ", ".join(accessible[:5]),
        )

    _GSC_RESOLVED_SITE_URL[client_id] = configured
    return configured


def _query(service, site_url: str, start: date, end: date,
            dimensions: list[str], row_limit: int = ROW_LIMIT) -> pd.DataFrame:
    body = {
        "startDate": str(start),
        "endDate": str(end),
        "dimensions": dimensions,
        "rowLimit": row_limit,
        "type": "web",
    }
    try:
        response = (service.searchanalytics()
                     .query(siteUrl=site_url, body=body).execute())
    except Exception as exc:  # noqa: BLE001
        if _is_gsc_insufficient_permission(exc):
            if site_url not in _GSC_PERM_WARNED:
                logger.error("%s", _gsc_permission_hint_message(site_url))
                if "insufficient authentication scopes" in str(exc).lower():
                    logger.error("%s", _gsc_scope_hint_message())
                _GSC_PERM_WARNED.add(site_url)
            _GSC_PERM_DENIED_SITES.add(site_url)
            return pd.DataFrame()

        logger.error("[gsc] API error on %s: %s", dimensions, exc)
        return pd.DataFrame()

    rows = response.get("rows", [])
    if not rows:
        return pd.DataFrame(columns=dimensions
                              + ["clicks", "impressions", "ctr", "position"])

    records = []
    for row in rows:
        record = dict(zip(dimensions, row.get("keys", [])))
        record.update({
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": row.get("ctr", 0.0),
            "position": row.get("position", 0.0),
        })
        records.append(record)
    return pd.DataFrame.from_records(records)
