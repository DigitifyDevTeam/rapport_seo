"""Client and environment configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "clients.yaml"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

load_dotenv(PROJECT_ROOT / ".env")

_DEFAULT_TEMPLATE = PROJECT_ROOT / "templates" / "seo_report_template.pptx"
_template_override = os.environ.get("SEO_REPORT_TEMPLATE_PATH", "").strip()
TEMPLATE_PATH = (Path(_template_override).expanduser()
                  if _template_override else _DEFAULT_TEMPLATE)


@dataclass
class ClientConfig:
    """Strongly typed view over an entry of ``config/clients.yaml``."""

    id: str
    name: str
    website: str
    agency_name: str
    timezone: str
    currency: str
    ga4: dict[str, Any] = field(default_factory=dict)
    gsc: dict[str, Any] = field(default_factory=dict)
    gmb: dict[str, Any] = field(default_factory=dict)
    clarity: dict[str, Any] = field(default_factory=dict)
    delivery: dict[str, Any] = field(default_factory=dict)
    report_profile: dict[str, str] = field(default_factory=dict)
    # When set (e.g. ``cchabitat``), GSC/GMB APIs and GMB UI use a dedicated
    # OAuth token / Chrome profile for that Google account.
    google_oauth_account: str = ""

    @property
    def output_dir(self) -> Path:
        return OUTPUTS_DIR / self.id

    def cover_profile_placeholders(self) -> dict[str, str]:
        """Static fields shown on the cover slide project panel."""
        profile = self.report_profile or {}
        website = (profile.get("url") or self.website or "").strip()
        if website and not website.startswith(("http://", "https://")):
            website = f"https://{website}"
        return {
            "cover_client": str(profile.get("client") or self.name),
            "cover_activity": str(profile.get("activity") or "—"),
            "cover_site_name": str(profile.get("site_name") or self.name),
            "cover_url": website or "—",
            "cover_seo_pack": str(profile.get("seo_pack") or "—"),
            "cover_seo_since": str(profile.get("seo_since") or "—"),
        }


def env(name: str, default: str | None = None) -> str | None:
    """Read an environment variable with an optional default."""
    value = os.environ.get(name, default)
    if value is None:
        return None
    return value.strip() or default


def load_clients(path: Path = CONFIG_PATH) -> list[ClientConfig]:
    """Load every client defined in the YAML config."""
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    defaults = raw.get("defaults", {}) or {}
    clients: list[ClientConfig] = []
    for entry in raw.get("clients", []) or []:
        clients.append(_to_client(entry, defaults))
    return clients


def get_client(client_id: str, path: Path = CONFIG_PATH) -> ClientConfig:
    """Return a single client by id."""
    for client in load_clients(path):
        if client.id == client_id:
            return client
    raise KeyError(f"Client '{client_id}' not found in {path}")


_PRODUCTION_SKIP_IDS = frozenset({"example"})


def load_production_clients(path: Path = CONFIG_PATH) -> list[ClientConfig]:
    """Clients included in scheduled VPS runs (excludes demo ``example``)."""
    override = (env("SEO_REPORT_CLIENT_IDS") or "").strip()
    if override:
        ids = [part.strip() for part in override.split(",") if part.strip()]
        return [get_client(client_id, path) for client_id in ids]
    return [
        client for client in load_clients(path)
        if client.id not in _PRODUCTION_SKIP_IDS
    ]


def _to_client(entry: dict[str, Any], defaults: dict[str, Any]) -> ClientConfig:
    client_id = str(entry["id"])
    gmb = dict(entry.get("gmb") or {})
    gmb_location = env(f"GMB_LOCATION_ID_{client_id.upper()}")
    gmb_account = env(f"GMB_ACCOUNT_ID_{client_id.upper()}")
    if gmb_location:
        gmb["location_id"] = gmb_location
    if gmb_account:
        gmb["account_id"] = gmb_account

    clarity = dict(entry.get("clarity") or {})
    clarity_project_id = env(f"CLARITY_PROJECT_ID_{client_id.upper()}")
    if clarity_project_id:
        clarity["project_id"] = clarity_project_id

    return ClientConfig(
        id=client_id,
        name=str(entry.get("name", client_id)),
        website=str(entry.get("website", "")),
        agency_name=str(entry.get("agency_name", defaults.get("agency_name",
                                                                env("AGENCY_NAME",
                                                                     "Agency")))),
        timezone=str(entry.get("timezone", defaults.get("timezone",
                                                         "UTC"))),
        currency=str(entry.get("currency", defaults.get("currency", "USD"))),
        ga4=entry.get("ga4") or {},
        gsc=entry.get("gsc") or {},
        gmb=gmb,
        clarity=clarity,
        delivery=entry.get("delivery") or {},
        report_profile=_normalize_report_profile(entry.get("report_profile")),
        google_oauth_account=str(entry.get("google_oauth_account") or "").strip(),
    )


def _normalize_report_profile(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    keys = ("client", "activity", "site_name", "url", "seo_pack", "seo_since")
    return {key: str(raw[key]).strip() for key in keys if raw.get(key)}
