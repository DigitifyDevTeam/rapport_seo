"""Build the executive summary and recommendation bullets.

Insights are produced from KPI deltas and keyword movements with a small
set of deterministic business rules. The output is a list of strings ready
to be rendered as bullet points.

This module is intentionally simple so that an LLM step can replace or
post-process the rule output later without affecting the rest of the
pipeline.
"""

from __future__ import annotations

import pandas as pd

from src.transform.kpis import KpiBundle, KpiValue

SIGNIFICANT = 5.0  # Seuil (%) pour considérer un changement comme significatif.


def _arrow(delta_pct: float | None) -> str:
    if delta_pct is None:
        return ""
    if delta_pct > 0:
        return "up"
    if delta_pct < 0:
        return "down"
    return "flat"


def _format_pct(delta_pct: float | None) -> str:
    if delta_pct is None:
        return "n/a"
    return f"{delta_pct:+.1f}%"


def _format_count(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _mom_phrase(delta_pct: float | None) -> str:
    """Internal MoM wording (may mention declines). Not for client Synthèse panels."""
    if delta_pct is None:
        return "évolution M-1 non calculable"
    if abs(delta_pct) < 1.0:
        return "stable vs mois précédent"
    if delta_pct > 0:
        return f"en hausse de {delta_pct:+.1f} % vs mois précédent"
    return f"en baisse de {delta_pct:.1f} % vs mois précédent"


def _report_mom_phrase(delta_pct: float | None) -> str:
    """Client-facing month-over-month phrase (always neutral or positive)."""
    if delta_pct is None:
        return "suivi en continu par rapport au mois précédent"
    if abs(delta_pct) < 1.0:
        return "stable par rapport au mois précédent"
    if delta_pct > 0:
        return (
            f"en progression de {delta_pct:+.1f} % par rapport au mois précédent"
        )
    if abs(delta_pct) < SIGNIFICANT:
        return "globalement stable par rapport au mois précédent"
    return "base solide à renforcer sur le prochain cycle"


def _position_mom_phrase(kpi: KpiValue) -> str:
    if not kpi.previous:
        return "évolution M-1 non calculable"
    diff = kpi.previous - kpi.value
    if abs(diff) < 0.2:
        return "stable vs mois précédent"
    if diff > 0:
        return f"amélioration de {diff:.1f} pts vs mois précédent"
    return f"dégradation de {abs(diff):.1f} pts vs mois précédent"


def _report_position_mom_phrase(kpi: KpiValue) -> str:
    """Client-facing position change (always neutral or positive)."""
    if not kpi.previous:
        return "suivi en continu par rapport au mois précédent"
    diff = kpi.previous - kpi.value
    if abs(diff) < 0.2:
        return "stable par rapport au mois précédent"
    if diff > 0:
        return f"en progression de {diff:.1f} pts par rapport au mois précédent"
    return "optimisation SEO en cours pour gagner en visibilité"


def _trend_word(delta_pct: float | None, *, up_is_good: bool = True) -> str:
    if delta_pct is None or abs(delta_pct) < SIGNIFICANT:
        return "stable"
    positive = delta_pct > 0
    good = positive if up_is_good else not positive
    if good:
        return "positive"
    if abs(delta_pct) >= 15:
        return "préoccupante"
    return "à surveiller"


def _kpi_metric_line(kpi: KpiValue, *, unit: str = "") -> str:
    suffix = f" {unit}".strip() if unit else ""
    value_txt = f"{_format_count(kpi.value)}{suffix}"
    if kpi.unit == "%":
        value_txt = f"{kpi.value:.2f} %"
    return f"• {kpi.label} : {value_txt} ({_report_mom_phrase(kpi.delta_pct)})"


def _polish_client_report_text(text: str) -> str:
    """Ensure Synthèse / En bref panels never use negative client-facing wording."""
    if not text or not text.strip():
        return text
    out = text
    replacements = (
        ("en baisse nette", "stable"),
        ("légèrement en baisse", "stable"),
        ("en baisse de", "stable à"),
        ("en baisse", "stable"),
        ("se dégrade", "évolue favorablement"),
        ("dégradation", "évolution"),
        ("reculent", "restent un levier"),
        ("recule nettement", "offre une base solide"),
        ("recule", "reste actif"),
        ("perdent", "concernent"),
        ("Moins de clics", "Les clics depuis Google"),
        ("clics de rage", "interactions"),
        ("préoccupante", "à consolider"),
        ("à surveiller", "à consolider"),
    )
    for old, new in replacements:
        out = out.replace(old, new)
    return out


def _compose_sections(sections: list[tuple[str, list[str]]]) -> str:
    blocks: list[str] = []
    for title, lines in sections:
        body = "\n".join(line for line in lines if line.strip())
        if not body:
            continue
        blocks.append(f"{title}\n{body}")
    return "\n\n".join(blocks)


def _ga4_analysis(kpis: KpiBundle) -> list[str]:
    lines: list[str] = []
    sess_trend = _trend_word(kpis.sessions.delta_pct, up_is_good=True)
    conv_trend = _trend_word(kpis.conversions.delta_pct, up_is_good=True)

    if sess_trend == "positive":
        lines.append(
            "Le trafic organique progresse : la visibilité SEO se traduit "
            "par plus de visites qualifiées sur le site."
        )
    else:
        lines.append(
            "Le trafic organique offre une base solide : les prochaines "
            "actions SEO viseront à renforcer les pages et contenus stratégiques."
        )

    if kpis.users.value and kpis.sessions.value:
        ratio = kpis.sessions.value / kpis.users.value
        lines.append(
            f"Ratio sessions / utilisateurs : {ratio:.2f} "
            f"(engagement {'élevé' if ratio > 1.15 else 'encourageant'})."
        )

    if conv_trend == "positive":
        lines.append(
            "Les conversions suivent une belle dynamique : le parcours "
            "organique facilite contacts et demandes."
        )
    else:
        lines.append(
            "Les conversions restent un levier de croissance : optimiser les "
            "pages d'atterrissage et les appels à l'action sur les URLs clés."
        )
    return lines


def _ga4_takeaway(kpis: KpiBundle) -> str:
    return (
        "À retenir : consolider les pages qui portent le trafic organique "
        "et poursuivre le suivi mensuel pour amplifier les résultats."
    )


def _gsc_analysis(kpis: KpiBundle) -> list[str]:
    lines: list[str] = []
    click_trend = _trend_word(kpis.clicks.delta_pct, up_is_good=True)
    imp_trend = _trend_word(kpis.impressions.delta_pct, up_is_good=True)
    ctr_trend = _trend_word(kpis.ctr.delta_pct, up_is_good=True)
    pos_trend = _trend_word(kpis.avg_position.delta_pct, up_is_good=False)

    if click_trend == "positive":
        lines.append(
            "La Search Console enregistre plus de clics : la combinaison "
            "visibilité + attractivité des résultats progresse."
        )
    elif imp_trend == "positive":
        lines.append(
            "Les impressions progressent : votre site gagne en visibilité "
            "sur Google, un atout pour développer les clics."
        )
    else:
        lines.append(
            "Clics et impressions confirment une présence régulière sur "
            "Google, avec des leviers d'optimisation identifiés."
        )

    if ctr_trend == "positive":
        lines.append(
            f"Le CTR ({kpis.ctr.value:.2f} %) progresse : les snippets "
            "gagnent en attractivité dans les résultats de recherche."
        )
    else:
        lines.append(
            f"CTR à {kpis.ctr.value:.2f} % : opportunité d'enrichir titles "
            "et meta descriptions sur les pages à fort potentiel."
        )

    if pos_trend == "positive":
        lines.append(
            f"La position moyenne progresse ({kpis.avg_position.value:.1f}), "
            "signe d'un meilleur classement global."
        )
    else:
        lines.append(
            f"Position moyenne autour de {kpis.avg_position.value:.1f} : "
            "le contenu et le maillage interne continuent de porter la visibilité."
        )
    return lines


def _gsc_takeaway(kpis: KpiBundle) -> str:
    return (
        "À retenir : renforcer titles, meta et contenus sur les requêtes "
        "stratégiques pour amplifier clics et visibilité le mois prochain."
    )


def _build_ga4_commentary(kpis: KpiBundle) -> str:
    conv_line = _kpi_metric_line(kpis.conversions)
    sections = [
        ("TRAFIC ORGANIQUE (GA4)", [
            "Chiffres du mois",
            _kpi_metric_line(kpis.sessions),
            _kpi_metric_line(kpis.users),
            conv_line,
        ]),
        ("Analyse", _ga4_analysis(kpis)),
        ("", [_ga4_takeaway(kpis)]),
    ]
    return _polish_client_report_text(_compose_sections(sections))


def _short_page_label(title: str, path: str, *, max_len: int = 42) -> str:
    title = (title or "").strip() or "(sans titre)"
    path = (path or "").strip()
    label = title if not path or path in title else f"{title} ({path})"
    if len(label) > max_len:
        return label[: max_len - 1] + "…"
    return label


def _pages_views_total(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    if "views" in df.columns:
        return float(pd.to_numeric(df["views"], errors="coerce").fillna(0).sum())
    if "screenPageViews" in df.columns:
        return float(
            pd.to_numeric(df["screenPageViews"], errors="coerce").fillna(0).sum())
    return 0.0


def _build_ga4_pages_commentary(
        current_pages_daily: pd.DataFrame,
        previous_pages_daily: pd.DataFrame,
        current_pages_top: pd.DataFrame,
) -> str:
    cur_views = _pages_views_total(current_pages_daily)
    prev_views = _pages_views_total(previous_pages_daily)
    delta_pct: float | None = None
    if prev_views > 0:
        delta_pct = (cur_views - prev_views) / prev_views * 100.0

    lines: list[str] = [
        f"• Vues totales (pages et écrans) : {_format_count(cur_views)} "
        f"({_report_mom_phrase(delta_pct)})",
    ]

    if not current_pages_top.empty and "pageTitle" in current_pages_top.columns:
        top = current_pages_top.head(3)
        for _, row in top.iterrows():
            label = _short_page_label(
                str(row.get("pageTitle") or ""),
                str(row.get("pagePath") or ""),
            )
            views = _to_page_views(row)
            lines.append(f"• {label} : {_format_count(views)} vues")

    analysis: list[str] = []
    trend = _trend_word(delta_pct, up_is_good=True)
    if trend == "positive":
        analysis.append(
            "La consultation des pages progresse : le contenu attire davantage "
            "de vues sur l'ensemble du site."
        )
    else:
        analysis.append(
            "Le volume de vues confirme l'intérêt pour vos contenus : "
            "prioriser les pages d'entrée pour renforcer l'engagement."
        )

    if not current_pages_top.empty:
        leader = current_pages_top.iloc[0]
        leader_label = _short_page_label(
            str(leader.get("pageTitle") or ""),
            str(leader.get("pagePath") or ""),
            max_len=50,
        )
        share = (_to_page_views(leader) / cur_views * 100) if cur_views else 0.0
        if share >= 25:
            analysis.append(
                f"La page « {leader_label} » concentre {share:.0f} % des vues : "
                "renforcer CTA et maillage depuis les autres URLs."
            )

    takeaway = (
        "À retenir : optimiser en priorité les pages qui concentrent le plus "
        "de vues et aligner titles / contenus avec les requêtes GSC."
    )
    sections = [
        ("PAGES ET ÉCRANS (GA4)", ["Chiffres du mois", *lines]),
        ("Analyse", analysis),
        ("", [takeaway]),
    ]
    return _polish_client_report_text(_compose_sections(sections))


def _to_page_views(row: pd.Series) -> float:
    for col in ("views", "screenPageViews"):
        if col in row.index:
            val = row.get(col)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return 0.0
    return 0.0


def _build_gsc_commentary(kpis: KpiBundle) -> str:
    sections = [
        ("PERFORMANCE SEARCH (GSC)", [
            "Visibilité sur Google",
            _kpi_metric_line(kpis.clicks),
            _kpi_metric_line(kpis.impressions),
            _kpi_metric_line(kpis.ctr, unit="%"),
            (f"• Position moyenne : {kpis.avg_position.value:.1f} "
             f"({_report_position_mom_phrase(kpis.avg_position)})"),
        ]),
        ("Analyse", _gsc_analysis(kpis)),
        ("", [_gsc_takeaway(kpis)]),
    ]
    return _polish_client_report_text(_compose_sections(sections))


def _kpi_line(kpi: KpiValue) -> str | None:
    delta = kpi.delta_pct
    if delta is None:
        return None
    if abs(delta) < SIGNIFICANT:
        return None
    direction = "augmente" if delta > 0 else "baisse"
    suffix = f" ({_format_pct(delta)} vs M-1)"
    return (f"{kpi.label} {direction} de {kpi.previous:,.0f} à "
            f"{kpi.value:,.0f}{suffix}.")


def _section_body(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line.strip())


def build_final_summary_sections(
        kpis: KpiBundle,
        *,
        clarity: dict[str, str] | None = None,
        gmb_kpis: dict[str, str] | None = None,
) -> dict[str, str]:
    """Section bodies for the multi-panel Synthèse finale slide."""
    clarity = clarity or {}
    gmb_kpis = gmb_kpis or {}
    return {
        "final_summary_brief": _polish_client_report_text(_plain_overview(kpis)),
        "final_summary_website": _polish_client_report_text(
            _section_body(_plain_website_lines(kpis)[:3])),
        "final_summary_search": _polish_client_report_text(
            _section_body(_plain_search_lines(kpis)[:3])),
        "final_summary_clarity": _polish_client_report_text(
            _section_body(_plain_clarity_lines(clarity)[:3])),
        "final_summary_gmb": _polish_client_report_text(
            _section_body(_plain_gmb_lines(gmb_kpis)[:3])),
    }


def build_final_summary(
        kpis: KpiBundle,
        *,
        clarity: dict[str, str] | None = None,
        gmb_kpis: dict[str, str] | None = None,
) -> str:
    """Plain-language recap (legacy single text block)."""
    clarity = clarity or {}
    gmb_kpis = gmb_kpis or {}
    sections: list[tuple[str, list[str]]] = [
        ("EN BREF", [_plain_overview(kpis)]),
        ("VOTRE SITE WEB", _plain_website_lines(kpis)),
        ("VOTRE VISIBILITÉ SUR GOOGLE", _plain_search_lines(kpis)),
        ("EXPÉRIENCE DES VISITEURS", _plain_clarity_lines(clarity)),
        ("VOTRE FICHE GOOGLE", _plain_gmb_lines(gmb_kpis)),
        ("CE QU'IL FAUT RETENIR", _plain_takeaways(kpis, gmb_kpis)),
    ]
    return _compose_sections(sections)


def _plain_trend_phrase(delta_pct: float | None, *, up_is_good: bool = True) -> str:
    """Always positive or neutral wording for Synthèse finale / En bref."""
    if delta_pct is None:
        return "suivi de près par rapport au mois dernier"
    if abs(delta_pct) < SIGNIFICANT:
        return "stable par rapport au mois dernier"
    positive = delta_pct > 0
    good = positive if up_is_good else not positive
    if good:
        return "en hausse par rapport au mois dernier"
    return "stable par rapport au mois dernier"


def _plain_overview(kpis: KpiBundle) -> str:
    return (
        f"Ce mois-ci, votre site accueille {_format_count(kpis.sessions.value)} "
        f"visites et génère {_format_count(kpis.clicks.value)} clics depuis Google — "
        "une base solide pour poursuivre le développement de votre visibilité en ligne."
    )


def _plain_website_lines(kpis: KpiBundle) -> list[str]:
    lines = [
        (f"• {_format_count(kpis.sessions.value)} visites sur le site "
         f"({_plain_trend_phrase(kpis.sessions.delta_pct)})."),
        (f"• {_format_count(kpis.users.value)} visiteurs uniques "
         f"({_plain_trend_phrase(kpis.users.delta_pct)})."),
        (f"• {_format_count(kpis.conversions.value)} actions importantes "
         f"(achats, contacts, demandes…) "
         f"({_plain_trend_phrase(kpis.conversions.delta_pct)})."),
    ]
    for sentence in _ga4_analysis(kpis)[:2]:
        lines.append(f"• {sentence}")
    return lines


def _plain_search_lines(kpis: KpiBundle) -> list[str]:
    lines = [
        (f"• {_format_count(kpis.clicks.value)} clics vers votre site "
         f"depuis Google ({_plain_trend_phrase(kpis.clicks.delta_pct)})."),
        (f"• {_format_count(kpis.impressions.value)} fois où votre site "
         f"est apparu dans les résultats Google "
         f"({_plain_trend_phrase(kpis.impressions.delta_pct)})."),
    ]
    if kpis.avg_position.value:
        pos_phrase = _report_position_mom_phrase(kpis.avg_position)
        lines.append(
            f"• Position moyenne dans Google : {kpis.avg_position.value:.1f} "
            f"({pos_phrase})."
        )
    for sentence in _gsc_analysis(kpis)[:2]:
        lines.append(f"• {sentence}")
    return lines


def _plain_clarity_lines(clarity: dict[str, str]) -> list[str]:
    sessions = (clarity.get("sessions") or "").strip()
    pages = (clarity.get("pages_per_session") or "").strip()
    scroll = (clarity.get("scroll_depth") or "").strip()
    active = (clarity.get("active_time") or "").strip()
    commentary = (clarity.get("commentary") or "").strip()

    if sessions.lower() in ("", "n/a"):
        return ["• Données d'expérience utilisateur indisponibles ce mois-ci."]

    lines = [f"• {sessions} sessions analysées sur votre site."]
    if pages and pages.lower() != "n/a":
        lines.append(f"• {pages} pages consultées en moyenne par visite.")
    if scroll and scroll.lower() != "n/a":
        lines.append(f"• Les visiteurs descendent jusqu'à {scroll} de la page.")
    if active and active.lower() != "n/a":
        lines.append(f"• Temps d'activité moyen : {active}.")

    if commentary and "indisponibles" not in commentary.lower():
        first = commentary.split(".")[0].strip()
        if (first and len(first) > 12
                and first.lower() not in ("ok", "n/a")
                and first not in lines[0]):
            lines.append(f"• {first}.")
    elif len(lines) == 1:
        lines.append(
            "• L'expérience de navigation reste globalement fluide "
            "sur les pages les plus visitées."
        )
    return lines


def _plain_gmb_lines(gmb_kpis: dict[str, str]) -> list[str]:
    labels = {
        "overview": "interactions au total avec votre fiche",
        "calls": "appels téléphoniques",
        "bookings": "réservations",
        "directions": "demandes d'itinéraire",
        "website_clicks": "clics vers votre site web",
    }
    parts: list[str] = []
    for key, label in labels.items():
        raw = (gmb_kpis.get(key) or "").strip()
        if raw and raw.lower() != "n/a":
            parts.append(f"• {raw} {label}.")

    if not parts:
        return ["• Données Google Business Profile indisponibles ce mois-ci."]
    if len(parts) == 1:
        parts.append(
            "• Votre fiche Google reste un canal de contact direct "
            "pour les clients locaux."
        )
    return parts


def _plain_takeaways(
        kpis: KpiBundle,
        gmb_kpis: dict[str, str],
) -> list[str]:
    lines: list[str] = [
        "• Votre site reste un canal essentiel : nous consolidons les pages "
        "qui attirent le plus de visites qualifiées.",
        "• Votre visibilité sur Google est un levier de croissance : "
        "titles, contenus et fiche locale sont alignés sur vos objectifs.",
        "• Les parcours de conversion sont suivis de près pour faciliter "
        "contacts, demandes et ventes.",
    ]

    gmb_total = (gmb_kpis.get("overview") or "").strip()
    if gmb_total and gmb_total.lower() != "n/a":
        lines.append(
            "• Votre fiche Google génère des contacts : maintenir les avis, "
            "photos et horaires à jour renforce la confiance des clients."
        )
    return lines[:4]


def build_executive_summary(kpis: KpiBundle,
                              keyword_wins: pd.DataFrame | None = None,
                              keyword_losses: pd.DataFrame | None = None
                              ) -> list[str]:
    bullets: list[str] = []

    bullets.extend(_kpi_bullets(kpis))
    pos_line = _position_bullet(kpis)
    if pos_line:
        bullets.append(pos_line)

    top_gain = _keyword_gain_bullet(keyword_wins)
    if top_gain:
        bullets.append(top_gain)

    top_drop = _keyword_drop_bullet(keyword_losses)
    if top_drop:
        bullets.append(top_drop)

    if not bullets:
        bullets.append("La performance est globalement stable vs M-1, sans "
                       "variation significative détectée.")
    return bullets[:5]


def _kpi_bullets(kpis: KpiBundle) -> list[str]:
    out: list[str] = []
    for kpi in (kpis.sessions, kpis.conversions, kpis.clicks, kpis.impressions):
        line = _kpi_line(kpi)
        if line:
            out.append(line)
    return out


def _position_bullet(kpis: KpiBundle) -> str | None:
    pos = kpis.avg_position
    if not (pos.previous and pos.value):
        return None
    diff = pos.previous - pos.value
    if abs(diff) < 0.5:
        return None
    direction = "s'améliore" if diff > 0 else "se dégrade"
    return (f"La position moyenne {direction} de "
            f"{pos.previous:.1f} à {pos.value:.1f}.")


def _keyword_gain_bullet(keyword_wins: pd.DataFrame | None) -> str | None:
    if keyword_wins is None or keyword_wins.empty:
        return None
    top = keyword_wins.iloc[0]
    if not (pd.notna(top.get("delta")) and top["delta"] >= 1):
        return None
    return (f"Meilleur gain : « {top.get('query', 'n/a')} » gagne "
            f"{int(top['delta'])} positions et atteint "
            f"{float(top.get('position', 0)):.1f}.")


def _keyword_drop_bullet(keyword_losses: pd.DataFrame | None) -> str | None:
    if keyword_losses is None or keyword_losses.empty:
        return None
    worst = keyword_losses.iloc[0]
    if not (pd.notna(worst.get("delta")) and worst["delta"] <= -1):
        return None
    return (f"Plus forte baisse : « {worst.get('query', 'n/a')} » perd "
            f"{int(abs(worst['delta']))} positions et tombe à "
            f"{float(worst.get('position', 0)):.1f}.")


def build_recommendations(kpis: KpiBundle,
                            keyword_losses: pd.DataFrame | None = None
                            ) -> list[str]:
    recs: list[str] = []
    if (kpis.ctr.previous and kpis.ctr.delta_pct is not None
            and kpis.ctr.delta_pct < -SIGNIFICANT):
        recs.append("Mettre à jour les balises title et meta description des "
                    "pages principales pour récupérer le CTR.")

    if (kpis.avg_position.previous and kpis.avg_position.value >
            kpis.avg_position.previous):
        recs.append("Auditer l'optimisation on-page et le maillage interne des "
                    "pages qui perdent en position moyenne.")

    if kpis.conversions.delta_pct is not None and kpis.conversions.delta_pct < 0:
        recs.append("Analyser les parcours de conversion dans GA4 et lancer un "
                    "sprint CRO sur les modèles de pages les plus visités.")

    if (keyword_losses is not None and not keyword_losses.empty
            and keyword_losses["delta"].min() <= -3):
        recs.append("Analyser la volatilité des SERP sur les mots-clés en "
                    "baisse et déployer des mises à jour de contenu ciblées.")

    if not recs:
        recs.append("Maintenir le rythme de publication et suivre les Core Web "
                    "Vitals pour protéger les positions.")
    return recs[:5]


def build_commentaries(
        kpis: KpiBundle,
        *,
        current_pages_daily: pd.DataFrame | None = None,
        previous_pages_daily: pd.DataFrame | None = None,
        current_pages_top: pd.DataFrame | None = None,
) -> dict[str, str]:
    """Structured synthesis text for chart-slide side panels."""
    commentaries = {
        "ga4_commentary": _build_ga4_commentary(kpis),
        "ga4_pages_commentary": _build_ga4_pages_commentary(
            current_pages_daily if current_pages_daily is not None
            else pd.DataFrame(),
            previous_pages_daily if previous_pages_daily is not None
            else pd.DataFrame(),
            current_pages_top if current_pages_top is not None
            else pd.DataFrame(),
        ),
        "conversions_commentary": (
            f"Conversions organiques : {_format_count(kpis.conversions.value)} "
            f"({_report_mom_phrase(kpis.conversions.delta_pct)}).\n\n"
            f"{_ga4_takeaway(kpis)}"
        ),
        "gsc_commentary": _build_gsc_commentary(kpis),
    }
    return {
        key: _polish_client_report_text(val)
        for key, val in commentaries.items()
    }


# Public alias for pipeline-side commentary (GMB, Clarity, etc.).
polish_client_report_text = _polish_client_report_text
