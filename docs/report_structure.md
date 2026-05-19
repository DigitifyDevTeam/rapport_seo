# SEO Monthly Report - Section Structure

This document defines the canonical structure of the automated monthly SEO report
and the placeholders used inside the PowerPoint template
(`templates/seo_report_template.pptx`).

The template is generated programmatically by
`scripts/build_template.py` so that the placeholders, styles and slide order
stay consistent with the code that fills them
(`src/reporting/pptx_report.py`).

**Permanent custom template:** after the first build, edit
`templates/seo_report_template.pptx` in PowerPoint. Monthly runs only fill
data; they never regenerate the layout. See `templates/README.md`. The build
script refuses to overwrite an existing file unless you pass `--force`.

## Slide-by-slide layout

| # | Slide | Purpose | Placeholders |
|---|-------|---------|--------------|
| 1 | Cover | Client name, reporting period, agency branding | `{{client_name}}`, `{{period_label}}`, `{{agency_name}}`, `{{report_date}}`, cover profile fields |
| 2 | Table des matières | Navigation | (static, generated from `TOC_ITEMS`) |
| 3 | Vue d'ensemble des KPI | Big numbers + MoM deltas + fixed French KPI definitions (préambules) under each label | `{{sessions}}`, `{{sessions_delta}}`, … (see `KPI_PREAMBLES` in `scripts/build_template.py`) |
| 4 | Performance organique (GA4) | Organic KPI row + period comparison table | `{{organic_performance_title}}`, `{{organic_perf_*}}`, `{{table_organic_performance}}` |
| 5 | Trafic organique (GA4) | Sessions/users line chart | `{{chart_ga4_traffic}}`, `{{ga4_commentary}}` |
| 6 | Pages et écrans (GA4) | Engagement — views per day | `{{chart_ga4_pages_screens}}`, `{{ga4_pages_commentary}}` |
| 7 | Comportement (Clarity) | UX KPIs + dashboard screenshots | `{{clarity_*}}`, `{{chart_clarity_*}}`, `{{clarity_commentary}}` |
| 8 | Performance Search (GSC) | Clicks vs impressions line chart | `{{chart_gsc_clicks_impressions}}`, `{{gsc_commentary}}` |
| 9 | Top pages (GSC) | Top landing pages table | `{{table_top_pages}}` |
| 10 | Présence Google Business Profile | Public fiche + interaction KPIs | `{{chart_gmb_business_card}}`, `{{gmb_*}}` |
| 11 | Interactions clients (détail) | GMB performance tab screenshots | `{{chart_gmb_overview}}`, `{{chart_gmb_calls}}`, etc. |
| 12 | Synthèse finale | Plain-language recap (brief + 4 topic cards) | `{{final_summary_brief}}`, `{{final_summary_website}}`, `{{final_summary_search}}`, `{{final_summary_clarity}}`, `{{final_summary_gmb}}` |
| 13 | Merci pour votre attention | Closing slide | (static) |

## Placeholder syntax

All textual placeholders use the `{{name}}` form so the runtime can do safe
text replacement on every shape that contains text. Image placeholders use
the same syntax but inside a *picture* shape; the runtime replaces the shape
with the rendered chart image while preserving its position and size.

## Tables

Tables use a "header row + N data rows" structure. The runtime resizes each
row count to match the data. Column widths and styling come from the
template, not the code.

## Charts

Charts are produced as PNG files in `outputs/<client>/<period>/charts/`
and embedded into picture placeholders. This keeps the template free of
chart definitions and lets us regenerate any visual without touching the
PPTX.

## MoM deltas

A delta is rendered as `+12.4%` or `-3.1%` and color coded in the template
through conditional placeholders such as `{{sessions_delta}}` which the
runtime replaces with the formatted value plus an arrow character.

## Final summary

The **Synthèse finale** slide uses five placeholders filled by
`insights.build_final_summary_sections()` in `src/insights/generator.py`:
a brief strip and four topic cards (site, Google visibility, Clarity, GMB).
