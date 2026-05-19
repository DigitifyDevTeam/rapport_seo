# SEO Monthly Report - Section Structure

This document defines the canonical structure of the automated monthly SEO report
and the placeholders used inside the PowerPoint template
(`templates/seo_report_template.pptx`).

The template is generated programmatically by
`scripts/build_template.py` so that the placeholders, styles and slide order
stay consistent with the code that fills them
(`src/reporting/pptx_report.py`).

## Slide-by-slide layout

| # | Slide | Purpose | Placeholders |
|---|-------|---------|--------------|
| 1 | Cover | Client name, reporting period, agency branding | `{{client_name}}`, `{{period_label}}`, `{{agency_name}}`, `{{report_date}}` |
| 2 | Executive Summary | 3 to 5 high level bullet points | `{{executive_summary}}` |
| 3 | KPI Overview | Big numbers + MoM deltas | `{{sessions}}`, `{{sessions_delta}}`, `{{users}}`, `{{users_delta}}`, `{{conversions}}`, `{{conversions_delta}}`, `{{clicks}}`, `{{clicks_delta}}`, `{{impressions}}`, `{{impressions_delta}}`, `{{ctr}}`, `{{ctr_delta}}`, `{{avg_position}}`, `{{avg_position_delta}}` |
| 4 | Organic Traffic (GA4) | Sessions/users line chart | `{{chart_ga4_traffic}}`, `{{ga4_commentary}}` |
| 5 | Conversions (GA4) | Conversions over time | `{{chart_ga4_conversions}}`, `{{conversions_commentary}}` |
| 6 | Search Performance (GSC) | Clicks vs impressions line chart | `{{chart_gsc_clicks_impressions}}`, `{{gsc_commentary}}` |
| 7 | Top Queries (GSC) | Top 10 queries table | `{{table_top_queries}}` |
| 8 | Top Pages (GSC) | Top 10 pages table | `{{table_top_pages}}` |
| 9 | Keyword Movements (GSC) | Wins / losses table | `{{table_keyword_wins}}`, `{{table_keyword_losses}}` |
| 10 | Local SEO (GMB) | Calls, directions, website clicks | `{{chart_gmb_actions}}`, `{{gmb_commentary}}` |
| 11 | Behavior (Clarity) | Sessions, rage clicks, scroll depth | `{{clarity_sessions}}`, `{{clarity_rage_clicks}}`, `{{clarity_scroll_depth}}`, `{{clarity_commentary}}` |
| 12 | Work Completed | Bullet list of actions delivered | `{{work_completed}}` |
| 13 | Recommendations | Bullet list of next month actions | `{{recommendations}}` |
| 14 | Appendix | Detailed tables / disclaimers | `{{appendix_notes}}` |

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
