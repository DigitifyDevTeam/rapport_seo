"""Monthly report orchestrator.

Run with::

    python -m src.pipeline.run_monthly --client example --month 2026-03

The orchestrator:

1. Loads the client configuration.
2. Pulls data from every configured connector for the current and the
   previous month.
3. Captures Google Business Profile (Playwright) and Microsoft Clarity UI data.
4. Computes KPIs with month-over-month deltas.
5. Generates rule-based insights and chart images.
6. Fills the PowerPoint template and exports a PDF when possible.
7. Optionally emails the PDF to the recipients listed in the client
   config.

GMB requires a one-time login::

    python scripts/gmb_ui_login.py --out outputs/_sessions/gmb-<client>.json \\
        --profile outputs/_sessions/chrome-profile-gmb
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.charts import generate as charts
from src.config import (PROJECT_ROOT, TEMPLATE_PATH, ClientConfig, env,
                          get_client, gmb_ui_session_owner, gmb_ui_session_path,
                          load_clients)
from src.connectors import (clarity as clarity_connector, ga4 as ga4_connector,
                              gmb as gmb_connector, gsc as gsc_connector)
from src.gmb.performance_url import (report_calendar_month_bounds,
                                     rewrite_performance_url_month)
from src.insights import generator as insights
from src.periods import Period
from src.pipeline.delivery import send_report
from src.reporting.export_pdf import export as export_pdf
from src.reporting.gmb_business_card import (
    ensure_valid_business_card,
    is_valid_public_fiche_png,
)
from src.reporting.gmb_card_ocr import extract_gmb_kpis_from_chart_paths
from src.reporting.pptx_report import render as render_pptx
from src.transform import normalize
from src.transform.kpis import (KpiBundle, compute_kpis, keyword_movements)
from src.transform.organic_performance import build_organic_performance_slide

logger = logging.getLogger(__name__)

# Must match scripts/gmb_ui_extract.py GMB_UI_CAPTURE_VERSION.
GMB_UI_CAPTURE_VERSION = "calmonth-v4-public-fiche"


@dataclass
class ReportArtifacts:
    output_dir: Path
    data_path: Path
    pptx_path: Path
    pdf_path: Path | None


def _fetch_all(client: ClientConfig, period: Period) -> dict[str, Any]:
    start, end = period.start, period.end
    skip = _disabled_connectors(client)
    return {
        "ga4": (normalize.normalize_ga4(ga4_connector.fetch(client, start, end))
                if "ga4" not in skip else normalize.normalize_ga4({})),
        "gsc": (normalize.normalize_gsc(gsc_connector.fetch(client, start, end))
                if "gsc" not in skip else normalize.normalize_gsc({})),
        # GMB: UI screenshots when available; Performance API fills KPIs/charts
        # when Playwright cannot run (e.g. shared VPS without system libraries).
        "gmb": (gmb_connector.fetch(client, start, end)
                if "gmb" not in skip else {}),
        # Clarity: dashboard UI is primary; API is a text-metrics fallback only.
        "clarity": (clarity_connector.fetch(client, start, end)
                    if "clarity" not in skip else {}),
    }


_RUNTIME_SKIP: set[str] = set()
_RUNTIME_REFRESH_CLARITY = False


def _disabled_connectors(client: ClientConfig) -> set[str]:
    skip = set(_RUNTIME_SKIP)
    for name in ("ga4", "gsc", "gmb", "clarity"):
        section = getattr(client, name, None) or {}
        if isinstance(section, dict) and section.get("enabled") is False:
            skip.add(name)
    return skip


def _ui_capture_disabled(client: ClientConfig) -> set[str]:
    """Browser-based GMB/Clarity capture only (not API fallbacks).

    Only ``SEO_REPORT_SKIP_UI_CONNECTORS`` disables UI capture.
    ``SEO_REPORT_SKIP_CONNECTORS`` is for API-level skipping and does NOT
    affect browser capture — so Docker with sessions can still capture while
    a plain VPS without browsers can skip APIs independently.
    """
    skip = set()
    raw = (env("SEO_REPORT_SKIP_UI_CONNECTORS") or "").strip()
    if raw:
        skip.update(part.strip().lower()
                    for part in raw.split(",") if part.strip())
    for name in ("gmb", "clarity"):
        section = getattr(client, name, None) or {}
        if isinstance(section, dict) and section.get("ui_enabled") is False:
            skip.add(name)
    return skip


def _set_runtime_refresh_clarity(refresh: bool) -> None:
    global _RUNTIME_REFRESH_CLARITY
    _RUNTIME_REFRESH_CLARITY = refresh


def _set_runtime_skip(skip_csv: str | None) -> None:
    _RUNTIME_SKIP.clear()
    if not skip_csv:
        return
    for raw in skip_csv.split(","):
        name = raw.strip().lower()
        if name:
            _RUNTIME_SKIP.add(name)


def _format_value(value: float, unit: str = "") -> str:
    if value == 0:
        return f"0{unit}"
    if unit == "%":
        return f"{value:.2f}%"
    if abs(value) < 10 and not float(value).is_integer():
        return f"{value:.2f}{unit}"
    return f"{value:,.0f}{unit}"


def _format_delta(delta_pct: float | None) -> str:
    if delta_pct is None:
        return "n/a"
    if delta_pct > 0:
        arrow = "\u25B2"
    elif delta_pct < 0:
        arrow = "\u25BC"
    else:
        arrow = "="
    return f"{arrow} {delta_pct:+.1f}%"


def _kpi_text(kpis: KpiBundle) -> dict[str, str]:
    items = {
        "sessions": kpis.sessions,
        "users": kpis.users,
        "conversions": kpis.conversions,
        "clicks": kpis.clicks,
        "impressions": kpis.impressions,
        "ctr": kpis.ctr,
        "avg_position": kpis.avg_position,
    }
    out: dict[str, str] = {}
    for name, kpi in items.items():
        out[name] = _format_value(kpi.value, kpi.unit)
        out[f"{name}_delta"] = _format_delta(kpi.delta_pct)
    return out


def _format_table(df: pd.DataFrame, columns: dict[str, str],
                    formatters: dict[str, Any] | None = None,
                    top_n: int = 10) -> pd.DataFrame:
    if df.empty:
        return df
    formatters = formatters or {}
    keep = [c for c in columns if c in df.columns]
    if not keep:
        return pd.DataFrame()
    out = df[keep].head(top_n).copy()
    for col, fmt in formatters.items():
        if col in out.columns:
            out[col] = out[col].apply(fmt)
    out = out.rename(columns=columns)
    return out


def _build_report_data(client: ClientConfig, period: Period,
                         current: dict[str, Any], previous: dict[str, Any],
                         output_dir: Path) -> dict[str, Any]:
    kpis = compute_kpis(current, previous)
    movements = keyword_movements(
        current.get("gsc", {}).get("queries", pd.DataFrame()),
        previous.get("gsc", {}).get("queries", pd.DataFrame()),
    )

    chart_dir = output_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    gmb_ui = _load_gmb_ui(output_dir, report_month=period.label)
    gmb_ui_chart = _resolve_gmb_ui_chart(gmb_ui, output_dir)
    gmb_ui_charts = _resolve_gmb_ui_charts(gmb_ui, output_dir)
    gmb_ui_kpis = _resolve_gmb_ui_kpis(gmb_ui)

    for key, val in extract_gmb_kpis_from_chart_paths(
            gmb_ui_charts, output_dir).items():
        if not val:
            continue
        cleaned = str(val).strip().replace("\u202f", "").replace(" ", "")
        if cleaned.isdigit() and 2015 <= int(cleaned) <= 2036:
            continue
        existing = (gmb_ui_kpis.get(key) or "").strip()
        if existing and existing.lower() not in ("n/a", ""):
            continue
        gmb_ui_kpis[key] = val
    for key, val in _load_gmb_kpi_override_json(output_dir).items():
        s = str(val).strip()
        if s:
            gmb_ui_kpis[key] = s
    for key, val in _gmb_kpis_from_daily(
            current.get("gmb", {}).get("daily", pd.DataFrame())).items():
        if val and (not gmb_ui_kpis.get(key)
                    or str(gmb_ui_kpis.get(key)).strip().lower() == "n/a"):
            gmb_ui_kpis[key] = val
    chart_paths = {
        "chart_ga4_traffic": str(charts.ga4_traffic_overview(
            current.get("ga4", {}).get("organic_daily", pd.DataFrame()),
            current.get("ga4", {}).get("countries", pd.DataFrame()),
            current.get("ga4", {}).get("channel_daily", pd.DataFrame()),
            chart_dir)),
        "chart_ga4_pages_screens": str(charts.ga4_pages_screens(
            current.get("ga4", {}).get("pages_daily", pd.DataFrame()),
            chart_dir)),
        "chart_gsc_clicks_impressions": str(charts.gsc_clicks_impressions(
            current.get("gsc", {}).get("daily", pd.DataFrame()), chart_dir)),
        "chart_gmb_actions": gmb_ui_chart or str(charts.gmb_actions(
            current.get("gmb", {}).get("daily", pd.DataFrame()), chart_dir)),
    }

    commentaries = insights.build_commentaries(
        kpis,
        current_pages_daily=current.get("ga4", {}).get("pages_daily",
                                                       pd.DataFrame()),
        previous_pages_daily=previous.get("ga4", {}).get("pages_daily",
                                                            pd.DataFrame()),
        current_pages_top=current.get("ga4", {}).get("pages_top",
                                                      pd.DataFrame()),
    )

    organic_slide = build_organic_performance_slide(
        current.get("ga4", {}),
        previous.get("ga4", {}),
        period,
    )

    pages_table = _format_table(
        current.get("gsc", {}).get("pages", pd.DataFrame()),
        columns={"page": "Page", "clicks": "Clicks",
                  "impressions": "Impressions"},
    )

    clarity_df = current.get("clarity", {}).get("insights", pd.DataFrame())
    clarity = _summarize_clarity(clarity_df)
    clarity_ui = _load_clarity_ui(output_dir)
    clarity_charts = _resolve_clarity_ui_charts(clarity_ui, output_dir)
    if clarity_ui is not None:
        clarity = _merge_clarity_ui(clarity, clarity_ui)

    final_sections = insights.build_final_summary_sections(
        kpis,
        clarity=clarity,
        gmb_kpis=gmb_ui_kpis,
    )

    data: dict[str, Any] = {
        "client_name": client.name,
        "agency_name": client.agency_name,
        "period_label": period.human_label(),
        "report_date": datetime.now().strftime("%Y-%m-%d"),
        **client.cover_profile_placeholders(),
        **final_sections,
        "organic_performance_title": organic_slide.title,
        "organic_perf_users": organic_slide.kpis[0][1],
        "organic_perf_new_users": organic_slide.kpis[1][1],
        "organic_perf_sessions": organic_slide.kpis[2][1],
        "organic_perf_engagement": organic_slide.kpis[3][1],
        "table_organic_performance": organic_slide,
        "table_top_pages": pages_table,
        "gmb_commentary": _gmb_commentary(
            current.get("gmb", {}).get("daily", pd.DataFrame()),
            gmb_ui=gmb_ui,
            kpi_strings=gmb_ui_kpis,
        ),
        "gmb_interactions": gmb_ui_kpis.get("overview", "n/a"),
        "gmb_calls": gmb_ui_kpis.get("calls", "n/a"),
        "gmb_bookings": gmb_ui_kpis.get("bookings", "n/a"),
        "gmb_directions": gmb_ui_kpis.get("directions", "n/a"),
        "gmb_website_clicks": gmb_ui_kpis.get("website_clicks", "n/a"),
        "chart_gmb_business_card": gmb_ui_charts.get("business_card", ""),
        "chart_gmb_overview": gmb_ui_charts.get("overview", ""),
        "chart_gmb_calls": gmb_ui_charts.get("calls", ""),
        "chart_gmb_bookings": gmb_ui_charts.get("bookings", ""),
        "chart_gmb_directions": gmb_ui_charts.get("directions", ""),
        "chart_gmb_website_clicks": gmb_ui_charts.get("website_clicks", ""),
        "clarity_sessions": clarity["sessions"],
        "clarity_rage_clicks": clarity["rage_clicks"],
        "clarity_scroll_depth": clarity["scroll_depth"],
        "clarity_commentary": clarity["commentary"],
        "clarity_pages_per_session": clarity.get("pages_per_session", "n/a"),
        "clarity_active_time": clarity.get("active_time", "n/a"),
        "chart_clarity_overview": clarity_charts.get("overview", ""),
        "chart_clarity_devices": clarity_charts.get("devices", ""),
        "chart_clarity_referrers": clarity_charts.get("referrers", ""),
        "chart_clarity_popular_pages": clarity_charts.get("popular_pages", ""),
        "chart_clarity_popular_products": clarity_charts.get(
            "popular_products", ""),
        "clarity_hide_popular_products": bool(
            (client.clarity or {}).get("pptx_hide_popular_products"),
        ),
    }
    data.update(_kpi_text(kpis))
    data.update(commentaries)
    data.update(chart_paths)
    data["_kpis"] = kpis.to_dict()
    return data


def _summarize_clarity(df: pd.DataFrame) -> dict[str, str]:
    default = {"sessions": "n/a", "rage_clicks": "n/a",
                "scroll_depth": "n/a",
                "commentary": "Données Clarity indisponibles pour cette période."}
    if df.empty:
        return default

    metrics = _index_clarity_metrics(df)
    if not metrics:
        return default

    traffic = (metrics.get("traffic") or [{}])[0]
    total_sessions = _to_float(traffic.get("totalSessionCount"))
    bot_sessions = _to_float(traffic.get("totalBotSessionCount")) or 0.0
    sessions_excl_bots: float | None = (
        max(total_sessions - bot_sessions, 0.0)
        if total_sessions is not None else None
    )

    rage_info = (metrics.get("rageclickcount") or [{}])[0]
    rage_clicks = _to_float(rage_info.get("subTotal"))

    scroll_info = (metrics.get("scrolldepth") or [{}])[0]
    scroll_depth = _to_float(scroll_info.get("averageScrollDepth"))

    if all(v is None for v in (sessions_excl_bots, rage_clicks, scroll_depth)):
        return default

    sessions_value = sessions_excl_bots or 0.0
    rage_value = rage_clicks or 0.0
    scroll_value = scroll_depth or 0.0

    bot_note = (f" ({bot_sessions:,.0f} sessions du robot exclues)"
                if bot_sessions else "")

    return {
        "sessions": _format_value(sessions_value),
        "rage_clicks": _format_value(rage_value),
        "scroll_depth": (f"{scroll_value:.1f}%" if scroll_depth is not None
                         else "n/a"),
        "commentary": (
            f"Clarity enregistre {sessions_value:,.0f} sessions{bot_note}, "
            f"{rage_value:,.0f} clics de rage et une profondeur de scroll "
            f"moyenne de {scroll_value:.1f}%."),
    }


def _load_clarity_ui(output_dir: Path) -> dict[str, Any] | None:
    """Load the JSON written by ``scripts/clarity_ui_extract.js`` if present.

    The JS scraper writes ``clarity_ui.json`` next to the report. We prefer
    these dashboard-derived values over the Clarity Data Export API because
    the API is restricted to the last 1-3 days and capped at 10 calls/day,
    while the dashboard already shows the user-selected (e.g. monthly) range.
    """
    candidate = output_dir / "clarity_ui.json"
    if not candidate.exists():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[clarity-ui] could not read %s: %s", candidate, exc)
        return None


_CLARITY_UI_EXTRACT_SCRIPT = (PROJECT_ROOT / "scripts"
                                / "clarity_ui_extract.js")
_CLARITY_UI_SESSIONS_DIR = PROJECT_ROOT / "outputs" / "_sessions"
_CLARITY_WIDGET_CARDS_DEFAULT = (
    "referrers",
    "devices",
    "popular_pages",
    "popular_products",
)


def _clarity_widget_cards(client: ClientConfig) -> tuple[str, ...]:
    skip = set((client.clarity or {}).get("ui_skip_widgets") or [])
    return tuple(c for c in _CLARITY_WIDGET_CARDS_DEFAULT if c not in skip)


def _clarity_required_card_ids(client: ClientConfig) -> tuple[str, ...]:
    """Cards required for a complete Clarity capture (incl. KPI strip)."""
    skip = set((client.clarity or {}).get("ui_skip_widgets") or [])
    required = ("overview",) + _CLARITY_WIDGET_CARDS_DEFAULT
    return tuple(c for c in required if c not in skip)


def _clarity_capture_complete(client: ClientConfig, output_dir: Path,
                               period: Period) -> bool:
    """True when widget PNGs and ``clarity_ui.json`` match this report period."""
    json_path = output_dir / "clarity_ui.json"
    if not json_path.exists():
        return False
    for card_id in _clarity_required_card_ids(client):
        png = output_dir / f"clarity_card_{card_id}.png"
        if not png.exists() or png.stat().st_size < 500:
            return False
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return (
        payload.get("period_start") == period.start.isoformat()
        and payload.get("period_end") == period.end.isoformat()
    )


def _capture_clarity_ui(client: ClientConfig, output_dir: Path,
                        period: Period, *, refresh: bool = False) -> None:
    """Run the Puppeteer extractor for this client if a session is available.

    Writes ``clarity_ui.json`` and ``clarity_card_*.png`` next to the report.
    Silently does nothing if Clarity is disabled, the session is missing, or
    Node is not available. The pipeline never calls the Clarity Data Export
    API (capped at 10/day and limited to last 1-3 days).
    """
    disabled = _ui_capture_disabled(client)
    logger.info("[clarity-ui] disabled=%s  (SEO_REPORT_SKIP_UI_CONNECTORS=%r)",
                disabled, env("SEO_REPORT_SKIP_UI_CONNECTORS") or "")
    if "clarity" in disabled:
        logger.info("[clarity-ui] skipped (disabled for %s)", client.id)
        return

    json_out = output_dir / "clarity_ui.json"
    if not refresh and _clarity_capture_complete(client, output_dir, period):
        logger.info(
            "[clarity-ui] reusing existing captures in %s (no browser)",
            output_dir,
        )
        return

    session_path = _CLARITY_UI_SESSIONS_DIR / f"clarity-{client.id}.json"
    logger.info("[clarity-ui] session path=%s  exists=%s",
                session_path, session_path.exists())
    if not session_path.exists():
        logger.warning(
            "[clarity-ui] no saved session at %s — widget PNGs need a Windows "
            "capture or copy outputs/%s/%s/clarity_* from your PC. Text metrics "
            "may still come from CLARITY_API_TOKEN.",
            session_path, client.id, period.label,
        )
        return
    if not _CLARITY_UI_EXTRACT_SCRIPT.exists():
        logger.warning("[clarity-ui] extract script not found at %s",
                       _CLARITY_UI_EXTRACT_SCRIPT)
        return
    node_bin = shutil.which("node")
    if not node_bin:
        logger.warning(
            "[clarity-ui] `node` not found in PATH; skipping dashboard "
            "capture. Install Node.js or run scripts/clarity_ui_extract.js "
            "manually.")
        return

    screenshot = output_dir / "clarity_dashboard.png"
    cmd = [
        node_bin,
        str(_CLARITY_UI_EXTRACT_SCRIPT),
        "--session", str(session_path),
        "--out", str(json_out),
        "--screenshot", str(screenshot),
        "--period-start", period.start.isoformat(),
        "--period-end", period.end.isoformat(),
    ]
    project_id = ((client.clarity or {}).get("project_id") or "").strip()
    if project_id:
        cmd.extend(["--project-id", project_id])
    skip_widgets = (client.clarity or {}).get("ui_skip_widgets") or []
    if skip_widgets:
        cmd.extend([
            "--skip-widgets",
            ",".join(str(w).strip() for w in skip_widgets if str(w).strip()),
        ])

    if refresh:
        cmd.extend(["--record", "--show", "--record-timeout", "900"])
        logger.info(
            "[clarity-ui] record mode for %s — export 4 widgets in the browser",
            client.id,
        )
        timeout = 960
    else:
        cmd.append("--auto")
        logger.info(
            "[clarity-ui] capturing dashboard for %s → %s (auto mode)",
            client.id, output_dir,
        )
        timeout = 420

    logger.info("[clarity-ui] cmd: %s", " ".join(str(c) for c in cmd))
    try:
        result = subprocess.run(cmd, timeout=timeout, check=False,
                                capture_output=True, text=True)
        if result.stdout:
            logger.info("[clarity-ui] stdout:\n%s", result.stdout[-2000:])
        if result.stderr:
            logger.info("[clarity-ui] stderr:\n%s", result.stderr[-2000:])
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        logger.warning("[clarity-ui] capture failed: %s", exc)
        return

    if result.returncode != 0:
        logger.warning(
            "[clarity-ui] capture exited with code %d",
            result.returncode,
        )
        return

    if not _clarity_capture_complete(client, output_dir, period):
        logger.warning(
            "[clarity-ui] capture finished but widget PNGs are still "
            "missing for %s. Re-run with --refresh-clarity to export "
            "manually in the browser.",
            period,
        )


def _resolve_clarity_ui_charts(ui_payload: dict[str, Any] | None,
                                output_dir: Path) -> dict[str, str]:
    """Return absolute paths to the Clarity dashboard card screenshots if any.

    ``clarity_ui_extract.js`` writes paths in ``charts`` either as relative
    (``outputs/<client>/<month>/clarity_card_<id>.png``) or as absolute. We
    accept both, and we also auto-discover ``clarity_card_<id>.png`` files
    next to ``clarity_ui.json`` when the JSON ``charts`` block is missing.
    """
    out: dict[str, str] = {}
    charts = (ui_payload or {}).get("charts") or {}
    for key, raw_path in charts.items():
        if not raw_path:
            continue
        candidate = Path(str(raw_path))
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        if candidate.exists():
            out[str(key)] = str(candidate)

    for known in ("overview", "devices", "referrers", "popular_pages",
                  "popular_products"):
        if known in out:
            continue
        fallback = output_dir / f"clarity_card_{known}.png"
        if fallback.exists():
            out[known] = str(fallback)
    return out


def _merge_clarity_ui(api_summary: dict[str, str],
                       ui_payload: dict[str, Any]) -> dict[str, str]:
    kpis = (ui_payload or {}).get("kpis") or {}

    def value(key: str) -> str | None:
        entry = kpis.get(key)
        if not entry:
            return None
        raw = entry.get("value") if isinstance(entry, dict) else None
        if not raw:
            return None
        return str(raw).strip() or None

    sessions = value("sessions")
    pages_per_session = value("pages_per_session")
    scroll_depth = value("scroll_depth")
    active_time = value("active_time")

    merged = dict(api_summary)
    if sessions:
        merged["sessions"] = sessions
    if scroll_depth:
        merged["scroll_depth"] = scroll_depth
    if pages_per_session:
        merged["pages_per_session"] = pages_per_session
    if active_time:
        merged["active_time"] = active_time

    merged["commentary"] = ""

    return merged


def _index_clarity_metrics(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if "metricName" not in df.columns or "information" not in df.columns:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for _, row in df.iterrows():
        name = str(row.get("metricName") or "").strip().lower()
        info = row.get("information")
        if not name or not isinstance(info, list):
            continue
        out[name] = [item for item in info if isinstance(item, dict)]
    return out


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _gmb_kpis_from_daily(df: pd.DataFrame) -> dict[str, str]:
    """Build GBP tab KPI strings from the Performance API daily dataframe."""
    if df.empty:
        return {}
    out: dict[str, str] = {}
    metric_cols = (
        ("calls", "calls"),
        ("directions", "directions"),
        ("website_clicks", "website_clicks"),
    )
    totals: list[float] = []
    for col, key in metric_cols:
        if col not in df.columns:
            continue
        total = float(df[col].sum())
        totals.append(total)
        out[key] = f"{int(round(total)):,}"
    if totals:
        out["overview"] = f"{int(round(sum(totals))):,}"
    return out


def _gmb_ui_assets_ready(output_dir: Path) -> bool:
    """True when synced UI files exist (no browser required)."""
    gmb_ui = _load_gmb_ui(output_dir)
    if _resolve_gmb_ui_kpis(gmb_ui):
        return True
    return (output_dir / "gmb_card_overview.png").is_file()


def _gmb_session_has_performance_url(session_path: Path) -> bool:
    """True when prepare saved a direct Performance link (#mpd=)."""
    if not session_path.is_file():
        return False
    try:
        url = str(
            json.loads(session_path.read_text(encoding="utf-8")).get("url") or "",
        )
    except (OSError, json.JSONDecodeError):
        return False
    return "#mpd=" in url or "promote/performance" in url


def _gmb_ui_runs_in_docker() -> bool:
    return (env("SEO_REPORT_DOCKER") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _log_gmb_vps_prepare_hint(client: ClientConfig, *, detail: str) -> None:
    logger.warning(
        "[gmb-ui] %s\n"
        "[gmb-ui] One-time on Windows: "
        "python scripts/clients/%s/gmb_ui_prepare.py\n"
        "[gmb-ui] Wait for Performance (URL must contain #mpd=), then copy "
        "outputs/_sessions/gmb-%s.json to the VPS.\n"
        "[gmb-ui] Verify: python scripts/check_gmb_vps_sessions.py",
        detail,
        client.id,
        client.id,
    )


def _gmb_ui_matches_period(output_dir: Path, period: Period) -> bool:
    """Reuse only when PNGs/KPIs match this report month and capture logic."""
    if not _gmb_ui_assets_ready(output_dir):
        return False
    gmb_ui = _load_gmb_ui(output_dir) or {}
    if gmb_ui.get("capture_version") != GMB_UI_CAPTURE_VERSION:
        return False
    if gmb_ui.get("report_month") != period.label:
        return False
    card = output_dir / "gmb_business_card.png"
    if card.is_file() and not is_valid_public_fiche_png(card):
        logger.info(
            "[gmb-ui] stale/invalid business card in %s — will re-capture",
            output_dir,
        )
        return False
    return True


def _gmb_commentary(df: pd.DataFrame,
                    gmb_ui: dict[str, Any] | None = None,
                    kpi_strings: dict[str, str] | None = None) -> str:
    ui_labels = {
        "overview": "interactions",
        "calls": "appels",
        "bookings": "réservations",
        "directions": "itinéraires",
        "website_clicks": "clics site web",
    }
    if kpi_strings:
        parts: list[str] = []
        for key, label in ui_labels.items():
            raw = (kpi_strings.get(key) or "").strip()
            if raw and raw.lower() != "n/a":
                parts.append(f"{label}: {raw}")
        if parts:
            return ("Actions clients ce mois-ci (Google Business Profile) : "
                    + ", ".join(parts) + ".")
    ui_kpis = (gmb_ui or {}).get("kpis") or {}
    ui_totals: dict[str, str] = {}
    for key, label in ui_labels.items():
        entry = ui_kpis.get(key)
        if isinstance(entry, dict) and entry.get("value"):
            ui_totals[label] = str(entry["value"]).strip()
    if ui_totals:
        parts2 = [f"{label}: {value}" for label, value in ui_totals.items()]
        return ("Actions clients ce mois-ci (Google Business Profile) : "
                + ", ".join(parts2) + ".")

    if df.empty:
        return "Données Google Business Profile indisponibles pour cette période."
    totals = {col: float(df[col].sum()) for col in
                ("calls", "directions", "website_clicks") if col in df.columns}
    if not totals:
        return "Données Google Business Profile indisponibles pour cette période."
    parts3 = [f"{name.replace('_', ' ')}: {value:,.0f}"
              for name, value in totals.items()]
    return "Actions clients ce mois-ci : " + ", ".join(parts3) + "."


def _read_json_safe(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _gmb_ui_matches_report_month(
    data: dict[str, Any] | None,
    report_month: str | None,
) -> bool:
    if not report_month or not data:
        return True
    saved = str(data.get("report_month") or "").strip()
    if not saved:
        return True
    return saved == report_month


def _load_gmb_ui(
    output_dir: Path,
    *,
    report_month: str | None = None,
) -> dict[str, Any] | None:
    """Load the JSON written by ``scripts/gmb_ui_extract.py`` if present.

    If the main file has empty kpis, fall back to the ``.bak`` copy that a
    prior successful capture may have left. Ignores files for another month
    when ``report_month`` is set (avoids April KPIs on a May report).
    """
    candidate = output_dir / "gmb_ui.json"
    data = _read_json_safe(candidate)
    if data and (data.get("kpis") or {}):
        if _gmb_ui_matches_report_month(data, report_month):
            return data
        logger.info(
            "[gmb-ui] ignoring %s (report_month=%s, need %s)",
            candidate.name,
            data.get("report_month"),
            report_month,
        )
        data = None
    bak = candidate.with_suffix(".json.bak")
    bak_data = _read_json_safe(bak)
    if bak_data and (bak_data.get("kpis") or {}):
        if _gmb_ui_matches_report_month(bak_data, report_month):
            logger.info("[gmb-ui] main gmb_ui.json has empty kpis; using .bak")
            return bak_data
        logger.info(
            "[gmb-ui] ignoring .bak (report_month=%s, need %s)",
            bak_data.get("report_month"),
            report_month,
        )
    return data


def _load_gmb_kpi_override_json(output_dir: Path) -> dict[str, str]:
    """Optional ``gmb_kpis_override.json`` next to the report (exact dashboard copy).

    Shape: ``{"overview": "702", "calls": "79", "bookings": "0", ...}``.
    Fills only keys that are still empty after UI + OCR.
    """
    path = output_dir / "gmb_kpis_override.json"
    data = _read_json_safe(path)
    if not isinstance(data, dict):
        return {}
    keys = ("overview", "calls", "bookings", "directions", "website_clicks")
    out: dict[str, str] = {}
    for key in keys:
        raw = data.get(key)
        if raw is None:
            continue
        s = str(raw).strip()
        if s:
            out[key] = s
    return out


_GMB_UI_EXTRACT_SCRIPT = PROJECT_ROOT / "scripts" / "gmb_ui_extract.py"
_GMB_UI_LOGIN_SCRIPT = PROJECT_ROOT / "scripts" / "gmb_ui_login.py"
_GMB_UI_SESSIONS_DIR = PROJECT_ROOT / "outputs" / "_sessions"


def _gmb_ui_profile_dir(client: ClientConfig) -> Path:
    """Chrome user-data dir for GMB UI (per client when present)."""
    base = _GMB_UI_SESSIONS_DIR
    account = (client.google_oauth_account or "").strip()
    if account:
        return base / f"chrome-profile-gmb-{account}"
    own = base / f"chrome-profile-gmb-{client.id}"
    if own.is_dir():
        return own
    shared = str((client.gmb or {}).get("ui_session_client") or "").strip()
    if shared:
        fallback = base / f"chrome-profile-gmb-{shared}"
        if fallback.is_dir():
            return fallback
    legacy = base / "chrome-profile-gmb"
    if legacy.is_dir():
        return legacy
    return own


def _backup_gmb_ui_if_good(json_path: Path) -> None:
    """Save a .bak copy if the current file has non-empty kpis."""
    data = _read_json_safe(json_path)
    if not data:
        return
    kpis = data.get("kpis") or {}
    has_values = any(
        isinstance(v, dict) and v.get("value")
        for v in kpis.values()
    )
    if has_values:
        bak = json_path.with_suffix(".json.bak")
        try:
            shutil.copy2(json_path, bak)
        except OSError:
            pass


def _capture_gmb_ui(client: ClientConfig, output_dir: Path,
                      period: Period | None = None) -> bool:
    """Capture GBP Performance KPIs + chart PNGs via ``gmb_ui_extract.py``.

    Writes ``gmb_ui.json``, ``gmb_business_card.png``, and ``gmb_card_*.png``
    next to the report. Returns True when at least one KPI was captured.
    """
    disabled = _ui_capture_disabled(client)
    logger.info("[gmb-ui] disabled=%s  (SEO_REPORT_SKIP_UI_CONNECTORS=%r)",
                disabled, env("SEO_REPORT_SKIP_UI_CONNECTORS") or "")
    if "gmb" in disabled:
        logger.info("[gmb-ui] skipped (disabled for %s)", client.id)
        return False

    gmb_cfg = getattr(client, "gmb", None) or {}
    session_path = gmb_ui_session_path(client, _GMB_UI_SESSIONS_DIR)
    logger.info(
        "[gmb-ui] session path=%s  exists=%s  (owner=%s)",
        session_path,
        session_path.exists(),
        session_path.stem.removeprefix("gmb-"),
    )
    force_refresh = (env("SEO_REPORT_REFRESH_GMB_UI") or "").lower() in (
        "1", "true", "yes", "on",
    )
    if gmb_cfg.get("ui_manual_capture"):
        existing = _load_gmb_ui(
            output_dir,
            report_month=period.label if period else None,
        )
        if _resolve_gmb_ui_kpis(existing) or _gmb_ui_assets_ready(output_dir):
            logger.info(
                "[gmb-ui] using manual UI assets in %s (no browser)",
                output_dir,
            )
            return True
    if period and not force_refresh and _gmb_ui_matches_period(output_dir, period):
        logger.info(
            "[gmb-ui] reusing valid captures for %s in %s (no browser)",
            period.label,
            output_dir,
        )
        return True
    if force_refresh:
        logger.info("[gmb-ui] refresh forced (SEO_REPORT_REFRESH_GMB_UI)")
    elif _gmb_ui_assets_ready(output_dir):
        logger.info(
            "[gmb-ui] stale capture in %s — re-running browser for %s",
            output_dir,
            period.label if period else "?",
        )
    if not session_path.exists():
        logger.warning(
            "[gmb-ui] no saved session at %s — run on Windows: "
            "python scripts/clients/%s/gmb_ui_prepare.py "
            "then copy outputs/_sessions/gmb-%s.json to the VPS",
            session_path,
            client.id,
            client.id,
        )
        return False
    perf_url_file = _GMB_UI_SESSIONS_DIR / f"gmb-performance-{client.id}.txt"
    perf_sidecar = ""
    if perf_url_file.is_file():
        perf_sidecar = perf_url_file.read_text(encoding="utf-8")
    has_perf_link = _gmb_session_has_performance_url(session_path) or (
        "#mpd=" in perf_sidecar or "promote/performance" in perf_sidecar
    )
    if _gmb_ui_runs_in_docker() and not has_perf_link:
        _log_gmb_vps_prepare_hint(
            client,
            detail=(
                f"Session {session_path.name} has no Performance URL (#mpd=); "
                "capture may fail — redo prepare on Windows (like Origincbd) "
                "and copy the session JSON to the VPS."
            ),
        )
    if not _GMB_UI_EXTRACT_SCRIPT.exists():
        logger.warning("[gmb-ui] extract script not found at %s", _GMB_UI_EXTRACT_SCRIPT)
        return False

    location_name = (
        gmb_cfg.get("ui_location_name")
        or gmb_cfg.get("location_name")
        or client.website.replace("https://", "").replace("http://", "")
                                                  .rstrip("/")
        or client.id
    )
    project_name = (
        gmb_cfg.get("ui_project_name")
        or gmb_cfg.get("project_name")
        or client.name
        or client.id
    )
    no_search = bool(gmb_cfg.get("ui_no_search"))
    search_query = (
        (gmb_cfg.get("ui_search_query") or "").strip()
        or ("" if no_search else None)
        or location_name
        or project_name
    )
    profile_dir = _gmb_ui_profile_dir(client)
    # Windows Chrome profiles are not portable to Linux/Docker. Allow
    # disabling profile use with SEO_REPORT_GMB_NO_PROFILE=1 (set by Dockerfile).
    no_profile = (env("SEO_REPORT_GMB_NO_PROFILE") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    # Override the default 'chrome' channel (e.g. force 'chromium' in Docker).
    channel = (env("SEO_REPORT_BROWSER_CHANNEL") or "").strip()

    json_out = output_dir / "gmb_ui.json"
    _backup_gmb_ui_if_good(json_out)
    screenshot = output_dir / "gmb_dashboard.png"
    cmd = [
        "python",
        str(_GMB_UI_EXTRACT_SCRIPT),
        "--session", str(session_path),
        "--out", str(json_out),
        "--screenshot", str(screenshot),
        "--project-name", project_name,
    ]
    if channel:
        cmd += ["--channel", channel]
    if not no_search:
        cmd.extend(["--business-name", search_query, "--location-name", location_name])
    if not no_profile and profile_dir.is_dir():
        cmd += ["--profile", str(profile_dir)]
    if period is not None:
        cmd += [
            "--no-auto-period",
            "--period-start", period.start.isoformat(),
            "--period-end", period.end.isoformat(),
        ]
    if no_search:
        cmd.append("--no-search")
    prefer_gmb_app = bool(gmb_cfg.get("ui_prefer_gmb_app"))
    if _gmb_ui_runs_in_docker() and not has_perf_link:
        prefer_gmb_app = True
    if prefer_gmb_app:
        cmd.append("--prefer-gmb-app")
    aliases = gmb_cfg.get("ui_project_aliases") or []
    if aliases:
        cmd.extend([
            "--project-names",
            ",".join(str(a).strip() for a in aliases if str(a).strip()),
        ])
    cmd.extend(["--client-id", client.id])
    perf_url = ""
    if perf_url_file.is_file():
        perf_url = perf_url_file.read_text(encoding="utf-8").strip()
    dash_from_session = ""
    if session_path.is_file():
        try:
            dash_from_session = str(
                json.loads(session_path.read_text(encoding="utf-8")).get("url") or "",
            ).strip()
        except (OSError, json.JSONDecodeError):
            dash_from_session = ""
    period_end_iso = period.end.isoformat() if period else ""
    if perf_url and ("#mpd=" in perf_url or "promote/performance" in perf_url):
        perf_url = rewrite_performance_url_month(
            perf_url,
            (report_calendar_month_bounds(period_end_iso)[1] or period_end_iso)[:7],
        ) if period else perf_url
        cmd.extend(["--dashboard-url", perf_url])
        logger.info("[gmb-ui] Performance URL from %s", perf_url_file.name)
    elif dash_from_session and (
        "#mpd=" in dash_from_session or "promote/performance" in dash_from_session
    ):
        dash_from_session = rewrite_performance_url_month(
            dash_from_session,
            (report_calendar_month_bounds(period_end_iso)[1] or period_end_iso)[:7],
        ) if period else dash_from_session
        cmd.extend(["--dashboard-url", dash_from_session])
        logger.info(
            "[gmb-ui] Performance URL from %s (saved at login)",
            session_path.name,
        )
    logger.info(
        "[gmb-ui] capturing for %s (project=%r, period=%s)",
        client.id,
        project_name,
        period.label if period else "auto",
    )
    logger.info("[gmb-ui] cmd: %s", " ".join(str(c) for c in cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=600, check=False)
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        logger.warning("[gmb-ui] capture failed: %s", exc)
        return False

    if result.stderr:
        logger.info("[gmb-ui] stderr:\n%s", result.stderr[-2000:])
    if result.returncode != 0:
        logger.warning(
            "[gmb-ui] capture exited with code %d — not using stale gmb_ui.json",
            result.returncode,
        )
        return False

    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line:
            logger.info("[gmb-ui] %s", line)

    gmb_ui = _load_gmb_ui(
        output_dir,
        report_month=period.label if period else None,
    )
    version_ok = (gmb_ui or {}).get("capture_version") == GMB_UI_CAPTURE_VERSION
    kpis = _resolve_gmb_ui_kpis(gmb_ui)
    if not version_ok:
        if kpis or (output_dir / "gmb_card_overview.png").is_file():
            logger.warning(
                "[gmb-ui] capture_version mismatch (expected %s) but reusing "
                "KPIs/charts in %s",
                GMB_UI_CAPTURE_VERSION,
                output_dir,
            )
        else:
            logger.warning(
                "[gmb-ui] gmb_ui.json missing or wrong capture_version "
                "(expected %s)",
                GMB_UI_CAPTURE_VERSION,
            )
            return False
    if kpis:
        logger.info("[gmb-ui] captured KPIs: %s", ", ".join(
            f"{k}={v}" for k, v in kpis.items()))
        return True
    logger.warning(
        "[gmb-ui] no KPI values in %s — check session or project name.",
        json_out,
    )
    return False


def _resolve_gmb_ui_chart(gmb_ui: dict[str, Any] | None,
                          output_dir: Path) -> str | None:
    """Return a chart image for the GMB slide when available.

    We prefer a cropped KPI strip (``gmb_card_overview.png``) next to the report.
    """
    if gmb_ui:
        charts = (gmb_ui.get("charts") or {}) if isinstance(gmb_ui, dict) else {}
        raw = charts.get("overview")
        if raw:
            candidate = Path(str(raw))
            if not candidate.is_absolute():
                candidate = (Path.cwd() / candidate).resolve()
            if candidate.exists():
                return str(candidate)

    fallback = output_dir / "gmb_card_overview.png"
    if fallback.exists():
        return str(fallback)
    return None


def _resolve_gmb_ui_charts(gmb_ui: dict[str, Any] | None,
                            output_dir: Path) -> dict[str, str]:
    """Return absolute paths to all GBP UI chart screenshots.

    ``gmb_ui_extract.py`` writes ``gmb_business_card.png`` and
    ``gmb_card_<id>.png`` next to ``gmb_ui.json``. We accept absolute and
    relative paths in the JSON, and auto-discover the file on disk when the
    JSON entry is missing.
    """
    out: dict[str, str] = {}
    raw_charts = (gmb_ui or {}).get("charts") or {}
    for key, raw in raw_charts.items():
        if not raw:
            continue
        candidate = Path(str(raw))
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        if candidate.exists():
            out[str(key)] = str(candidate)

    fallback_filenames = {
        "business_card": "gmb_business_card.png",
        "overview": "gmb_card_overview.png",
        "calls": "gmb_card_calls.png",
        "bookings": "gmb_card_bookings.png",
        "directions": "gmb_card_directions.png",
        "website_clicks": "gmb_card_website_clicks.png",
    }
    for key, filename in fallback_filenames.items():
        if key in out:
            continue
        candidate = output_dir / filename
        if candidate.exists():
            out[key] = str(candidate)

    business = out.get("business_card")
    if business and not is_valid_public_fiche_png(Path(business)):
        logger.warning(
            "[gmb-ui] dropping invalid business_card image: %s", business,
        )
        out.pop("business_card", None)
    return out


def _resolve_gmb_ui_kpis(gmb_ui: dict[str, Any] | None) -> dict[str, str]:
    """Return ``{tab_id: formatted_value}`` for the GBP UI dashboard tabs."""
    out: dict[str, str] = {}
    kpis = (gmb_ui or {}).get("kpis") or {}
    for key, entry in kpis.items():
        if not isinstance(entry, dict):
            continue
        raw = entry.get("value")
        if not raw:
            continue
        text = str(raw).strip()
        if text:
            out[str(key)] = text
    return out


def _serialize(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, pd.DataFrame):
            out[key] = value.to_dict(orient="records")
        elif isinstance(value, Path):
            out[key] = str(value)
        else:
            out[key] = value
    return out


def _log_fetch_summary(client_id: str, current: dict[str, Any]) -> None:
    """Log row counts so an empty deck is easier to diagnose on the VPS."""
    ga4 = current.get("ga4") or {}
    gsc = current.get("gsc") or {}
    gmb = current.get("gmb") or {}
    clarity = current.get("clarity") or {}

    def _rows(frame: Any) -> int:
        if isinstance(frame, pd.DataFrame):
            return len(frame)
        return 0

    logger.info(
        "[%s] connector rows — ga4 organic_daily=%s pages_daily=%s | "
        "gsc daily=%s | gmb daily=%s | clarity insights=%s",
        client_id,
        _rows(ga4.get("organic_daily")),
        _rows(ga4.get("pages_daily")),
        _rows(gsc.get("daily")),
        _rows(gmb.get("daily")),
        _rows(clarity.get("insights")),
    )


def run_for_client(client: ClientConfig, period: Period) -> ReportArtifacts:
    output_dir = client.output_dir / period.label
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("[%s] fetching data for %s", client.id, period.label)
    _capture_clarity_ui(
        client, output_dir, period, refresh=_RUNTIME_REFRESH_CLARITY,
    )
    if "gmb" not in _disabled_connectors(client):
        _capture_gmb_ui(client, output_dir, period)
    gmb_cfg = client.gmb or {}
    ref_raw = (gmb_cfg.get("business_card_reference") or "").strip()
    ref_path = Path(ref_raw) if ref_raw else None
    if ref_path and not ref_path.is_absolute():
        ref_path = PROJECT_ROOT / ref_path
    ensure_valid_business_card(
        output_dir,
        client_id=client.id,
        reference_path=ref_path,
    )
    current = _fetch_all(client, period)
    previous = _fetch_all(client, period.previous)
    _log_fetch_summary(client.id, current)

    data = _build_report_data(client, period, current, previous, output_dir)

    data_path = output_dir / "report_data.json"
    with data_path.open("w", encoding="utf-8") as fh:
        json.dump(_serialize(data), fh, indent=2, default=str)

    pptx_path = output_dir / f"{client.id}_{period.label}_report.pptx"
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Template not found at {TEMPLATE_PATH}. "
            "Run `python scripts/build_template.py` once to create it, or set "
            "SEO_REPORT_TEMPLATE_PATH in .env to your customized .pptx file.")
    render_pptx(TEMPLATE_PATH, pptx_path, data)
    logger.info("[%s] wrote %s", client.id, pptx_path)

    pdf_enabled = (env("SEO_REPORT_EXPORT_PDF", "false") or "false").lower()
    if pdf_enabled in ("1", "true", "yes", "on"):
        pdf_path = export_pdf(pptx_path)
        if pdf_path:
            logger.info("[%s] wrote %s", client.id, pdf_path)
    else:
        pdf_path = None

    recipients = list((client.delivery or {}).get("emails") or [])
    if recipients and pdf_path:
        send_report(recipients,
                     subject=f"Rapport SEO mensuel - {client.name} - "
                              f"{period.human_label()}",
                     body=("Veuillez trouver en pièce jointe le rapport SEO "
                           f"mensuel pour {period.human_label()}."),
                     attachment=pdf_path)

    return ReportArtifacts(output_dir=output_dir, data_path=data_path,
                            pptx_path=pptx_path, pdf_path=pdf_path)


def _resolve_period(month: str | None) -> Period:
    if month:
        return Period.parse(month)
    return Period.previous_complete()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="Client id from clients.yaml")
    parser.add_argument("--all", action="store_true",
                          help="Run every client defined in clients.yaml")
    parser.add_argument("--month", help="Reporting month as YYYY-MM. "
                          "Defaults to the previous complete month.")
    parser.add_argument("--skip", default="",
                        help="Comma separated list of connectors to disable "
                             "(e.g. --skip gmb,clarity,gsc).")
    parser.add_argument(
        "--refresh-clarity",
        action="store_true",
        help="Re-open Clarity in the browser to export widget PNGs "
             "(default: reuse clarity_card_*.png already in the output folder).",
    )
    args = parser.parse_args(argv)
    _set_runtime_refresh_clarity(bool(args.refresh_clarity))

    logging.basicConfig(level=logging.INFO,
                          format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    _set_runtime_skip(args.skip)
    if _RUNTIME_SKIP:
        logger.info("Skipping connectors: %s", ", ".join(sorted(_RUNTIME_SKIP)))

    period = _resolve_period(args.month)

    if args.all:
        clients = load_clients()
    elif args.client:
        clients = [get_client(args.client)]
    else:
        parser.error("Provide --client <id> or --all")
        return 2

    for client in clients:
        try:
            run_for_client(client, period)
        except Exception:  # noqa: BLE001
            logger.exception("Report failed for client %s", client.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
