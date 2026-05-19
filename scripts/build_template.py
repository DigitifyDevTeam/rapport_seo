"""Generate the reusable PowerPoint template for the monthly SEO report.

The template is created programmatically so it can be versioned in git and
rebuilt on any machine without shipping a binary asset that drifts from the
code that fills it.

Run:
    python scripts/build_template.py

The output is written to ``templates/seo_report_template.pptx``.
"""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "seo_report_template.pptx"

# Modern analytics deck: slate base + teal + violet (professional contrast)
PRIMARY = RGBColor(0x0F, 0x17, 0x2A)
ACCENT = RGBColor(0x14, 0xB8, 0xA6)
ACCENT_BRIGHT = RGBColor(0x2D, 0xD4, 0xBF)
ACCENT_DIM = RGBColor(0x0F, 0x76, 0x6E)
ACCENT_SECOND = RGBColor(0x8B, 0x5C, 0xF6)
MUTED = RGBColor(0x64, 0x74, 0x8B)
TEXT = RGBColor(0x0F, 0x17, 0x2A)
LIGHT_BG = RGBColor(0xEC, 0xFE, 0xFF)
PAGE_BG = RGBColor(0xF8, 0xFA, 0xFC)
COVER_BG = RGBColor(0x04, 0x09, 0x12)
COVER_GLOW = RGBColor(0x0C, 0x16, 0x26)
COVER_MUTED = RGBColor(0x94, 0xA3, 0xB8)
CARD_BORDER = RGBColor(0xE2, 0xE8, 0xF0)
CARD_SURFACE = RGBColor(0xFF, 0xFF, 0xFF)
KPI_ACCENT_PALETTE: list[RGBColor] = [ACCENT, ACCENT_SECOND, ACCENT_DIM, ACCENT_BRIGHT]
KPI_SOFT_BG: dict[RGBColor, RGBColor] = {
    ACCENT: RGBColor(0xEC, 0xFE, 0xFF),
    ACCENT_SECOND: RGBColor(0xF5, 0xF3, 0xFF),
    ACCENT_DIM: RGBColor(0xE6, 0xFF, 0xFA),
    ACCENT_BRIGHT: RGBColor(0xF0, 0xFD, 0xFA),
}
KPI_PILL_BG: dict[RGBColor, RGBColor] = {
    ACCENT: RGBColor(0xCC, 0xFB, 0xF1),
    ACCENT_SECOND: RGBColor(0xE9, 0xD5, 0xFF),
    ACCENT_DIM: RGBColor(0x99, 0xF6, 0xE4),
    ACCENT_BRIGHT: RGBColor(0xA7, 0xF3, 0xD0),
}

# Slide numbers for the table of contents (cover = 1, ToC = 2, then content).
# Slide indices: 1 = cover, 2 = table of contents; keep in sync with ``main()`` order.
TOC_ITEMS: list[tuple[str, int]] = [
    ("Synthèse exécutive", 3),
    ("Vue d'ensemble des KPI", 4),
    ("Performance organique (GA4)", 5),
    ("Trafic organique (GA4)", 6),
    ("Pages et écrans (GA4)", 7),
    ("Comportement (Clarity)", 8),
    ("Performance Search (GSC)", 9),
    ("Top pages (GSC)", 10),
    ("Présence Google Business Profile", 11),
    ("Interactions clients (détail)", 12),
    ("Merci pour votre attention", 13),
]

FONT_TITLE = "Segoe UI"
FONT_BODY = "Segoe UI"

# Extra inset for screenshot slots (GMB, Clarity) inside their frames.
CHART_SLOT_INSET = Inches(0.1)


def _set_text(shape, text: str, *, size: int = 18, bold: bool = False,
              color: RGBColor = TEXT, align=PP_ALIGN.LEFT,
              font_name: str = FONT_BODY) -> None:
    tf = shape.text_frame
    tf.word_wrap = True
    tf.text = text
    p = tf.paragraphs[0]
    p.alignment = align
    for run in p.runs:
        run.font.name = font_name
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color


def _add_text_box(slide, left, top, width, height, text, **kwargs):
    box = slide.shapes.add_textbox(left, top, width, height)
    _set_text(box, text, **kwargs)
    return box


def _add_band(slide, left, top, width, height, color: RGBColor) -> None:
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    band.fill.solid()
    band.fill.fore_color.rgb = color
    band.line.fill.background()


def _add_soft_panel(slide, left, top, width, height,
                    *, fill: RGBColor, line: RGBColor | None = None) -> None:
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top,
                                   width, height)
    panel.fill.solid()
    panel.fill.fore_color.rgb = fill
    if line is not None:
        panel.line.color.rgb = line
        panel.line.width = Pt(0.75)
    else:
        panel.line.fill.background()


def _kpi_value_font_size(height) -> int:
    """Scale headline KPI value to card height."""
    h_in = height / Inches(1)
    if h_in >= 2.2:
        return 32
    if h_in >= 1.45:
        return 26
    if h_in >= 1.05:
        return 22
    return 18


def _add_kpi_card(slide, left, top, width, height, label: str,
                   value_placeholder: str, delta_placeholder: str,
                   *, accent: RGBColor | None = None,
                   variant_index: int = 0) -> None:
    """Modern KPI tile: top accent, soft glow, pill delta badge."""
    accent_rgb = accent or KPI_ACCENT_PALETTE[variant_index % len(KPI_ACCENT_PALETTE)]
    soft_bg = KPI_SOFT_BG.get(accent_rgb, LIGHT_BG)
    pill_bg = KPI_PILL_BG.get(accent_rgb, LIGHT_BG)

    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top,
                                   width, height)
    card.adjustments[0] = 0.14
    card.fill.solid()
    card.fill.fore_color.rgb = CARD_SURFACE
    card.line.color.rgb = CARD_BORDER
    card.line.width = Pt(0.5)

    accent_h = Inches(0.048)
    accent_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                        left, top, width, accent_h)
    accent_bar.fill.solid()
    accent_bar.fill.fore_color.rgb = accent_rgb
    accent_bar.line.fill.background()

    glow = min(width, height) * 0.42
    glow_left = left + width - glow + Inches(0.06)
    glow_top = top + accent_h + Inches(0.02)
    orb = slide.shapes.add_shape(MSO_SHAPE.OVAL, glow_left, glow_top,
                                 glow, glow)
    orb.fill.solid()
    orb.fill.fore_color.rgb = soft_bg
    orb.line.fill.background()

    pad_x = Inches(0.2)
    pad_y = Inches(0.16)
    inner_left = left + pad_x
    inner_w = width - 2 * pad_x
    label_top = top + accent_h + pad_y
    label_h = Inches(0.26)
    _add_text_box(slide, inner_left, label_top, inner_w, label_h,
                  label.upper(), size=8, bold=True, color=MUTED)

    value_top = label_top + label_h + Inches(0.06)
    value_size = _kpi_value_font_size(height)
    value_h = Inches(0.38) + (value_size - 18) * Inches(0.015)
    _add_text_box(slide, inner_left, value_top, inner_w, value_h,
                  value_placeholder, size=value_size, bold=True,
                  color=PRIMARY, font_name=FONT_TITLE)

    if delta_placeholder:
        pill_h = Inches(0.3)
        pill_w = min(inner_w, Inches(1.45))
        pill_top = top + height - pad_y - pill_h
        pill = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                      inner_left, pill_top, pill_w, pill_h)
        pill.adjustments[0] = 0.5
        pill.fill.solid()
        pill.fill.fore_color.rgb = pill_bg
        pill.line.fill.background()
        _add_text_box(slide, inner_left + Inches(0.1), pill_top + Inches(0.04),
                      pill_w - Inches(0.2), pill_h - Inches(0.06),
                      delta_placeholder, size=9, bold=True, color=accent_rgb)


def _slide_with_title(prs: Presentation, title: str, subtitle: str | None = None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_band(slide, Inches(0), Inches(0), prs.slide_width, prs.slide_height,
              PAGE_BG)
    rail_w = Inches(0.12)
    _add_band(slide, Inches(0), Inches(0), rail_w, prs.slide_height,
              ACCENT_SECOND)
    _add_band(slide, Inches(0), Inches(0), prs.slide_width, Inches(0.048), ACCENT)
    _add_band(slide, Inches(0), Inches(0.048), prs.slide_width, Inches(0.024),
              ACCENT_BRIGHT)
    header_top = Inches(0.072)
    header_h = Inches(0.9)
    _add_band(slide, Inches(0), header_top, prs.slide_width, header_h, PRIMARY)
    title_left = rail_w + Inches(0.42)
    title_w = prs.slide_width - title_left - Inches(0.45)
    _add_text_box(slide, title_left, header_top + Inches(0.1), title_w,
                  Inches(0.5), title, size=22, bold=True,
                  color=RGBColor(0xFF, 0xFF, 0xFF),
                  font_name=FONT_TITLE)
    if subtitle:
        _add_text_box(slide, title_left, header_top + Inches(0.56), title_w,
                      Inches(0.36), subtitle, size=12,
                      color=RGBColor(0xBA, 0xCC, 0xE8))
    _add_band(slide, Inches(0), header_top + header_h,
              prs.slide_width, Inches(0.038), ACCENT_DIM)
    return slide


def _add_toc_entry(slide, left: float, top: float, width: float, page: int,
                    title: str, badge_color: RGBColor) -> None:
    badge_w = Inches(0.42)
    badge_h = Inches(0.36)
    badge = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                    left, top, badge_w, badge_h)
    badge.adjustments[0] = 0.35
    badge.fill.solid()
    badge.fill.fore_color.rgb = badge_color
    badge.line.fill.background()
    page_str = str(page)
    _add_text_box(slide, left, top + Inches(0.02), badge_w, badge_h - Inches(0.02),
                  page_str, size=12, bold=True,
                  color=RGBColor(0xFF, 0xFF, 0xFF), align=PP_ALIGN.CENTER)
    text_left = left + badge_w + Inches(0.16)
    text_w = width - badge_w - Inches(0.16)
    _add_text_box(slide, text_left, top + Inches(0.04), text_w, badge_h,
                  title, size=13, color=TEXT, bold=False)


def build_table_of_contents(prs: Presentation) -> None:
    slide = _slide_with_title(prs, "Table des matières",
                               "Plan du rapport · navigation rapide")
    _add_soft_panel(slide, Inches(0.38), Inches(1.14), Inches(12.57),
                    Inches(5.62), fill=RGBColor(0xFF, 0xFF, 0xFF),
                    line=CARD_BORDER)
    col_w = Inches(5.85)
    row_h = Inches(0.44)
    start_top = Inches(1.38)
    left_col_x = Inches(0.62)
    right_col_x = Inches(6.82)
    half = (len(TOC_ITEMS) + 1) // 2
    for idx, (toc_title, page_num) in enumerate(TOC_ITEMS):
        col = 0 if idx < half else 1
        row = idx if idx < half else idx - half
        left = left_col_x if col == 0 else right_col_x
        top = start_top + row * row_h
        badge_color = ACCENT if idx % 2 == 0 else ACCENT_SECOND
        _add_toc_entry(slide, left, top, col_w, page_num, toc_title,
                        badge_color)


def _picture_placeholder(slide, left, top, width, height, name: str) -> None:
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = f"{{{{{name}}}}}"
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    for run in p.runs:
        run.font.name = FONT_BODY
        run.font.size = Pt(11)
        run.font.color.rgb = MUTED
        run.font.italic = True


def _table_placeholder(slide, left, top, width, height, name: str,
                        caption: str) -> None:
    _add_text_box(slide, left, top, width, Inches(0.3),
                  caption, size=12, bold=True, color=PRIMARY)
    _picture_placeholder(slide, left, top + Inches(0.3), width,
                          height - Inches(0.3), name)


_COVER_PROFILE_ROWS: list[tuple[str, str]] = [
    ("Client", "{{cover_client}}"),
    ("Activité", "{{cover_activity}}"),
    ("Nom du site", "{{cover_site_name}}"),
    ("URL", "{{cover_url}}"),
    ("Pack SEO", "{{cover_seo_pack}}"),
    ("Première activité SEO", "{{cover_seo_since}}"),
]


def _add_cover_profile_panel(slide, left, top, width, _height) -> None:
    """Project facts inside the cover slide dark panel."""
    pad_x = Inches(0.4)
    pad_y = Inches(0.38)
    inner_left = left + pad_x
    inner_w = width - 2 * pad_x
    divider_rgb = RGBColor(0x22, 0x33, 0x55)
    label_rgb = RGBColor(0x94, 0xA3, 0xB8)
    value_rgb = RGBColor(0xF1, 0xF5, 0xF9)

    title_top = top + pad_y
    title_h = Inches(0.26)
    _add_text_box(slide, inner_left, title_top, inner_w, title_h,
                  "FICHE PROJET", size=9, bold=True, color=ACCENT_BRIGHT,
                  font_name=FONT_TITLE)
    _add_band(slide, inner_left, title_top + title_h + Inches(0.08), inner_w,
              Inches(0.045), ACCENT)

    row_top = title_top + title_h + Inches(0.28)
    label_h = Inches(0.2)
    value_h = Inches(0.34)
    row_gap = Inches(0.14)
    divider_h = Inches(0.018)

    for idx, (label, value_placeholder) in enumerate(_COVER_PROFILE_ROWS):
        _add_text_box(slide, inner_left, row_top, inner_w, label_h,
                      label.upper(), size=8, bold=True, color=label_rgb)
        _add_text_box(slide, inner_left, row_top + label_h, inner_w, value_h,
                      value_placeholder, size=12, bold=True, color=value_rgb,
                      font_name=FONT_TITLE)
        row_bottom = row_top + label_h + value_h + Inches(0.06)
        if idx < len(_COVER_PROFILE_ROWS) - 1:
            _add_band(slide, inner_left, row_bottom, inner_w, divider_h,
                      divider_rgb)
            row_top = row_bottom + divider_h + row_gap
        else:
            row_top = row_bottom


def build_cover(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_band(slide, Inches(0), Inches(0), prs.slide_width, prs.slide_height,
              COVER_BG)
    _add_band(slide, Inches(0), Inches(0), Inches(0.14), prs.slide_height,
              ACCENT_SECOND)
    glow = slide.shapes.add_shape(
        MSO_SHAPE.OVAL,
        prs.slide_width - Inches(3.8), Inches(-2.1), Inches(7.2), Inches(7.2))
    glow.fill.solid()
    glow.fill.fore_color.rgb = COVER_GLOW
    glow.line.fill.background()
    panel_left = prs.slide_width - Inches(5.15)
    panel_top = Inches(0.85)
    panel_w = Inches(4.85)
    panel_h = Inches(5.65)
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                    panel_left, panel_top, panel_w, panel_h)
    panel.adjustments[0] = 0.06
    panel.fill.solid()
    panel.fill.fore_color.rgb = RGBColor(0x08, 0x11, 0x20)
    panel.line.color.rgb = RGBColor(0x22, 0x33, 0x55)
    panel.line.width = Pt(0.5)
    _add_cover_profile_panel(slide, panel_left, panel_top, panel_w, panel_h)
    _add_band(slide, Inches(0), Inches(0), prs.slide_width, Inches(0.12), ACCENT)
    _add_band(slide, Inches(0), Inches(0.12), prs.slide_width, Inches(0.05),
              ACCENT_BRIGHT)
    # Bottom accent only on the left column — do not cross the Fiche projet panel.
    _add_band(slide, Inches(0), Inches(5.72), panel_left, Inches(0.07),
              ACCENT_DIM)
    _add_band(slide, prs.slide_width - Inches(0.28), Inches(0.12),
              Inches(0.28), Inches(7.38), ACCENT_SECOND)
    _add_text_box(slide, Inches(0.62), Inches(1.22), Inches(10.8), Inches(0.45),
                  "{{agency_name}}", size=11, color=COVER_MUTED, bold=True)
    _add_text_box(slide, Inches(0.62), Inches(1.68), Inches(10.8), Inches(1.05),
                  "Rapport SEO", size=44, bold=True,
                  color=RGBColor(0xFF, 0xFF, 0xFF), font_name=FONT_TITLE)
    _add_text_box(slide, Inches(0.62), Inches(2.58), Inches(10.8), Inches(0.55),
                  "mensuel", size=26, bold=False,
                  color=ACCENT_BRIGHT, font_name=FONT_TITLE)
    _add_band(slide, Inches(0.62), Inches(3.32), Inches(1.38), Inches(0.052),
              ACCENT)
    _add_band(slide, Inches(2.0), Inches(3.32), Inches(1.38), Inches(0.052),
              ACCENT_SECOND)
    _add_text_box(slide, Inches(0.62), Inches(3.48), Inches(10.8), Inches(0.68),
                  "{{client_name}}", size=26, bold=True,
                  color=RGBColor(0xFF, 0xFF, 0xFF), font_name=FONT_TITLE)
    _add_text_box(slide, Inches(0.62), Inches(4.18), Inches(10.8), Inches(0.45),
                  "{{period_label}}", size=15, color=COVER_MUTED)
    _add_text_box(slide, Inches(0.62), Inches(6.68), Inches(11.5), Inches(0.42),
                  "Document confidentiel · Généré le {{report_date}}",
                  size=10, color=RGBColor(0x6A, 0x78, 0x8C))


def build_executive_summary(prs: Presentation) -> None:
    slide = _slide_with_title(prs, "Synthèse exécutive",
                                "Points clés sur la période")
    _add_soft_panel(slide, Inches(0.45), Inches(1.18), Inches(12.43),
                    Inches(5.52), fill=RGBColor(0xFF, 0xFF, 0xFF),
                    line=CARD_BORDER)
    _add_text_box(slide, Inches(0.72), Inches(1.42), Inches(11.9), Inches(5.05),
                  "{{executive_summary}}", size=15, color=TEXT)


def build_kpi_overview(prs: Presentation) -> None:
    slide = _slide_with_title(prs, "Vue d'ensemble des KPI",
                                "Performance mois sur mois")
    _add_soft_panel(slide, Inches(0.45), Inches(1.18), Inches(12.43),
                    Inches(5.52), fill=RGBColor(0xFF, 0xFF, 0xFF),
                    line=CARD_BORDER)
    cards = [
        ("Sessions", "{{sessions}}", "{{sessions_delta}}"),
        ("Utilisateurs", "{{users}}", "{{users_delta}}"),
        ("Conversions", "{{conversions}}", "{{conversions_delta}}"),
        ("Clics", "{{clicks}}", "{{clicks_delta}}"),
        ("Impressions", "{{impressions}}", "{{impressions_delta}}"),
        ("CTR", "{{ctr}}", "{{ctr_delta}}"),
        ("Position moyenne", "{{avg_position}}", "{{avg_position_delta}}"),
    ]
    card_w = Inches(2.95)
    card_h = Inches(1.68)
    gap = Inches(0.16)
    cols = 4
    start_left = Inches(0.52)
    start_top = Inches(1.35)
    for idx, (label, value, delta) in enumerate(cards):
        row, col = divmod(idx, cols)
        left = start_left + col * (card_w + gap)
        top = start_top + row * (card_h + gap)
        _add_kpi_card(slide, left, top, card_w, card_h, label, value, delta,
                       variant_index=idx)


def _add_chart_synthesis_panel(slide, left, top, width, height,
                                commentary_name: str) -> None:
    """Right-hand synthesis block on GA4 / GSC chart slides."""
    pad = Inches(0.14)
    inner_left = left + pad
    inner_w = width - 2 * pad
    _add_text_box(slide, inner_left, top + pad, inner_w, Inches(0.34),
                  "Synthèse", size=13, bold=True, color=PRIMARY,
                  font_name=FONT_TITLE)
    _add_band(slide, inner_left, top + pad + Inches(0.36), Inches(1.05),
              Inches(0.045), ACCENT)
    _add_text_box(slide, inner_left, top + pad + Inches(0.48),
                  inner_w, height - pad - Inches(0.48),
                  f"{{{{{commentary_name}}}}}", size=10, color=TEXT)


# Organic performance slide uses the shared KPI card design.


def build_organic_performance(prs: Presentation) -> None:
    """GA4 organic channel summary (KPI row + period comparison table)."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_band(slide, Inches(0), Inches(0), prs.slide_width, prs.slide_height,
              PAGE_BG)
    _add_band(slide, Inches(0), Inches(0), Inches(0.12), prs.slide_height,
              ACCENT_SECOND)
    _add_band(slide, Inches(0), Inches(0), prs.slide_width, Inches(0.048), ACCENT)

    title_top = Inches(0.42)
    _add_text_box(slide, Inches(0.52), title_top, Inches(12.2), Inches(0.55),
                  "{{organic_performance_title}}", size=20, bold=True,
                  color=PRIMARY, font_name=FONT_TITLE)

    kpi_top = Inches(1.02)
    kpi_h = Inches(1.12)
    kpi_w = Inches(2.95)
    gap = Inches(0.16)
    start_left = Inches(0.52)
    kpi_defs = [
        ("Utilisateurs*", "{{organic_perf_users}}"),
        ("Nouveaux utilisateurs*", "{{organic_perf_new_users}}"),
        ("Sessions*", "{{organic_perf_sessions}}"),
        ("Taux d'engagement*", "{{organic_perf_engagement}}"),
    ]
    for idx, (label, placeholder) in enumerate(kpi_defs):
        left = start_left + idx * (kpi_w + gap)
        _add_kpi_card(slide, left, kpi_top, kpi_w, kpi_h, label,
                       placeholder, "", variant_index=idx)

    table_top = Inches(2.28)
    table_h = Inches(4.35)
    table_w = Inches(12.2)
    table_left = Inches(0.52)
    _picture_placeholder(slide, table_left, table_top, table_w, table_h,
                          "table_organic_performance")

    _add_text_box(slide, Inches(0.52), Inches(6.62), Inches(12.0), Inches(0.35),
                  "* : Visites et utilisateurs venant depuis les moteurs de "
                  "recherche seulement",
                  size=9, color=MUTED)


def build_chart_slide(prs: Presentation, title: str, subtitle: str,
                       chart_name: str, commentary_name: str) -> None:
    slide = _slide_with_title(prs, title, subtitle)
    _add_soft_panel(slide, Inches(0.45), Inches(1.18), Inches(8.72),
                    Inches(5.52), fill=RGBColor(0xFF, 0xFF, 0xFF),
                    line=CARD_BORDER)
    synth_left = Inches(9.28)
    synth_top = Inches(1.18)
    synth_w = Inches(3.58)
    synth_h = Inches(5.52)
    _add_soft_panel(slide, synth_left, synth_top, synth_w, synth_h,
                    fill=LIGHT_BG, line=CARD_BORDER)
    # Inset chart inside the left panel so it does not overflow the frame.
    chart_pad = Inches(0.22)
    _picture_placeholder(
        slide,
        Inches(0.45) + chart_pad,
        Inches(1.18) + chart_pad,
        Inches(8.72) - 2 * chart_pad,
        Inches(5.52) - 2 * chart_pad,
        chart_name,
    )
    _add_chart_synthesis_panel(slide, synth_left, synth_top, synth_w, synth_h,
                                commentary_name)


def build_table_slide(prs: Presentation, title: str, subtitle: str,
                       table_name: str) -> None:
    slide = _slide_with_title(prs, title, subtitle)
    _add_soft_panel(slide, Inches(0.45), Inches(1.18), Inches(12.43),
                    Inches(5.52), fill=RGBColor(0xFF, 0xFF, 0xFF),
                    line=CARD_BORDER)
    _table_placeholder(slide, Inches(0.52), Inches(1.28), Inches(12.28),
                       Inches(5.32), table_name, subtitle)


def build_gmb_overview(prs: Presentation) -> None:
    """Slide 11: Knowledge Panel capture + five KPI placeholders (3 + 2 grid)."""
    slide = _slide_with_title(
        prs,
        "Présence Google Business Profile",
        "Fiche d'établissement et interactions clients",
    )
    _add_soft_panel(slide, Inches(0.45), Inches(1.18), Inches(12.43),
                    Inches(5.52), fill=RGBColor(0xFF, 0xFF, 0xFF),
                    line=CARD_BORDER)

    card_left = Inches(0.58)
    card_top = Inches(1.28)
    card_w = Inches(4.6)
    card_h = Inches(5.6)
    _add_text_box(slide, card_left, card_top, card_w, Inches(0.3),
                   "Fiche publique", size=12, bold=True, color=PRIMARY,
                   align=PP_ALIGN.CENTER)
    card_img_top = card_top + Inches(0.3)
    card_img_h = card_h - Inches(0.3)
    _picture_placeholder(
        slide,
        card_left + CHART_SLOT_INSET,
        card_img_top + CHART_SLOT_INSET,
        card_w - 2 * CHART_SLOT_INSET,
        card_img_h - 2 * CHART_SLOT_INSET,
        "chart_gmb_business_card",
    )

    kpi_cards = [
        ("Interactions totales", "{{gmb_interactions}}"),
        ("Appels", "{{gmb_calls}}"),
        ("Réservations", "{{gmb_bookings}}"),
        ("Itinéraires", "{{gmb_directions}}"),
        ("Clics vers le site Web", "{{gmb_website_clicks}}"),
    ]
    kpi_left = card_left + card_w + Inches(0.35)
    kpi_area_w = Inches(12.43) - (kpi_left - Inches(0.45)) - Inches(0.15)
    cols = 3
    gap_x = Inches(0.12)
    gap_y = Inches(0.12)
    kpi_w = (kpi_area_w - gap_x * (cols - 1)) / cols
    rows = 2
    kpi_h = (card_h - gap_y * (rows - 1)) / rows
    for idx, (label, value) in enumerate(kpi_cards):
        row, col = divmod(idx, cols)
        if row == 1:
            row2_count = len(kpi_cards) - cols
            row2_total_w = kpi_w * row2_count + gap_x * (row2_count - 1)
            row2_start = kpi_left + (kpi_area_w - row2_total_w) / 2
            left = row2_start + (idx - cols) * (kpi_w + gap_x)
        else:
            left = kpi_left + col * (kpi_w + gap_x)
        top = card_top + row * (kpi_h + gap_y)
        _add_kpi_card(slide, left, top, kpi_w, kpi_h, label, value, "",
                       variant_index=idx)


def build_gmb_details(prs: Presentation) -> None:
    """Slide 12: five Performance tab screenshots (3 + 2 grid)."""
    slide = _slide_with_title(
        prs,
        "Interactions clients (détail)",
        "Performance par type d'interaction",
    )
    _add_soft_panel(slide, Inches(0.45), Inches(1.18), Inches(12.43),
                    Inches(5.52), fill=RGBColor(0xFF, 0xFF, 0xFF),
                    line=CARD_BORDER)
    charts = [
        ("Vue d'ensemble", "chart_gmb_overview"),
        ("Appels", "chart_gmb_calls"),
        ("Réservations", "chart_gmb_bookings"),
        ("Itinéraires", "chart_gmb_directions"),
        ("Clics vers le site Web", "chart_gmb_website_clicks"),
    ]
    cols = 3
    chart_w = Inches(4.1)
    chart_h = Inches(2.85)
    gap_x = Inches(0.15)
    gap_y = Inches(0.25)
    total_w = chart_w * cols + gap_x * (cols - 1)
    start_left = (prs.slide_width - total_w) / 2
    start_top = Inches(1.28)
    for idx, (caption, name) in enumerate(charts):
        row, col = divmod(idx, cols)
        left = start_left + col * (chart_w + gap_x)
        top = start_top + row * (chart_h + gap_y)
        _add_text_box(slide, left, top, chart_w, Inches(0.3),
                       caption, size=12, bold=True, color=PRIMARY,
                       align=PP_ALIGN.CENTER)
        img_top = top + Inches(0.3)
        img_h = chart_h - Inches(0.3)
        _picture_placeholder(
            slide,
            left + CHART_SLOT_INSET,
            img_top + CHART_SLOT_INSET,
            chart_w - 2 * CHART_SLOT_INSET,
            img_h - 2 * CHART_SLOT_INSET,
            name,
        )


def build_clarity(prs: Presentation) -> None:
    slide = _slide_with_title(prs, "Comportement (Clarity)",
                                "Signaux d'expérience utilisateur")
    _add_soft_panel(slide, Inches(0.45), Inches(1.18), Inches(12.43),
                    Inches(5.52), fill=RGBColor(0xFF, 0xFF, 0xFF),
                    line=CARD_BORDER)

    kpi_cards = [
        ("Sessions", "{{clarity_sessions}}"),
        ("Pages par session", "{{clarity_pages_per_session}}"),
        ("Profondeur de défilement", "{{clarity_scroll_depth}}"),
        ("Temps d'activité passé", "{{clarity_active_time}}"),
    ]
    card_w = Inches(3.0)
    card_h = Inches(1.52)
    card_gap = Inches(0.16)
    cards_total_w = card_w * len(kpi_cards) + card_gap * (len(kpi_cards) - 1)
    cards_left = (prs.slide_width - cards_total_w) / 2
    cards_top = Inches(1.26)
    for idx, (label, value) in enumerate(kpi_cards):
        left = cards_left + idx * (card_w + card_gap)
        _add_kpi_card(slide, left, cards_top, card_w, card_h, label, value, "",
                       variant_index=idx)

    charts = [
        ("Appareils", "chart_clarity_devices"),
        ("Référents", "chart_clarity_referrers"),
        ("Pages supérieures", "chart_clarity_popular_pages"),
        ("Produits populaires", "chart_clarity_popular_products"),
    ]
    chart_w = Inches(2.95)
    chart_h = Inches(3.45)
    gap = Inches(0.12)
    charts_total_w = chart_w * len(charts) + gap * (len(charts) - 1)
    charts_left = (prs.slide_width - charts_total_w) / 2
    charts_top = cards_top + card_h + Inches(0.2)
    for idx, (caption, name) in enumerate(charts):
        left = charts_left + idx * (chart_w + gap)
        _add_text_box(slide, left, charts_top, chart_w, Inches(0.3),
                       caption, size=11, bold=True, color=PRIMARY,
                       align=PP_ALIGN.CENTER)
        img_top = charts_top + Inches(0.3)
        img_h = chart_h - Inches(0.3)
        _picture_placeholder(
            slide,
            left + CHART_SLOT_INSET,
            img_top + CHART_SLOT_INSET,
            chart_w - 2 * CHART_SLOT_INSET,
            img_h - 2 * CHART_SLOT_INSET,
            name,
        )
    charts_bottom = charts_top + chart_h + Inches(0.35)
    _add_text_box(slide, Inches(0.5), charts_bottom + Inches(0.08),
                  Inches(12.3), Inches(0.5),
                  "{{clarity_commentary}}", size=12, color=TEXT,
                  align=PP_ALIGN.CENTER)


def _render_thank_you_gauge_png() -> bytes:
    """Semi-circular gauge (5 segments + needle) for the closing slide."""
    colors = ["#B2E5B5", "#1B5E20", "#FFCC80", "#FB8C00", "#D32F2F"]
    fig = plt.figure(figsize=(2.65, 1.38), dpi=160)
    ax = fig.add_subplot(projection="polar")
    ax.set_theta_zero_location("W")
    ax.set_theta_direction(-1)
    ax.set_axis_off()
    ax.set_ylim(0, 1.05)
    try:
        ax.set_thetamin(0)
        ax.set_thetamax(180)
    except (AttributeError, ValueError):
        pass
    width = np.pi / 5
    bottom = 0.18
    for i in range(5):
        theta_c = np.pi - (i + 0.5) * width
        ax.bar(
            theta_c,
            0.72,
            width=width * 0.92,
            bottom=bottom,
            color=colors[i],
            align="center",
            edgecolor="#222222",
            linewidth=0.35,
        )
    needle = np.pi - 1.5 * width
    ax.plot(
        [needle, needle],
        [0.05, bottom + 0.68],
        color="#111111",
        linewidth=2.8,
        zorder=10,
    )
    ax.scatter([needle], [0.06], s=60, color="#111111", zorder=11, edgecolors="none")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight",
                pad_inches=0.02)
    plt.close(fig)
    return buf.getvalue()


def build_thank_you_slide(prs: Presentation) -> None:
    """Closing slide: thank-you message, gauge, and agency contact (DIGITIFY)."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    thank_bg = RGBColor(0xFA, 0xFA, 0xFA)
    _add_band(slide, Inches(0), Inches(0), prs.slide_width, prs.slide_height,
              thank_bg)

    box_w = Inches(8.85)
    box_h = Inches(2.88)
    box_left = (prs.slide_width - box_w) / 2
    box_top = Inches(2.18)

    panel = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, box_left, box_top,
                                   box_w, box_h)
    panel.fill.solid()
    panel.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    panel.line.color.rgb = RGBColor(0x00, 0x00, 0x00)
    panel.line.width = Pt(1.5)

    gauge_w = Inches(2.52)
    gauge_h = Inches(1.32)
    gx = prs.slide_width / 2 - gauge_w / 2
    gy = box_top - gauge_h + Inches(0.28)
    stream = io.BytesIO(_render_thank_you_gauge_png())
    slide.shapes.add_picture(stream, gx, gy, width=gauge_w, height=gauge_h)

    green = RGBColor(0x1B, 0x5E, 0x20)
    inner_pad = Inches(0.35)
    text_top = box_top + Inches(1.05)
    _add_text_box(slide, box_left + inner_pad, text_top,
                  box_w - 2 * inner_pad, Inches(0.68),
                  "MERCI POUR VOTRE", size=26, bold=True, color=green,
                  align=PP_ALIGN.CENTER, font_name=FONT_TITLE)
    _add_text_box(slide, box_left + inner_pad, text_top + Inches(0.62),
                  box_w - 2 * inner_pad, Inches(0.68),
                  "ATTENTION", size=26, bold=True, color=green,
                  align=PP_ALIGN.CENTER, font_name=FONT_TITLE)

    contact_top = box_top + box_h + Inches(0.4)
    black = RGBColor(0x00, 0x00, 0x00)
    _add_text_box(slide, Inches(0.55), contact_top,
                  prs.slide_width - Inches(1.1), Inches(0.42),
                  "N'hésitez pas à nous contacter pour plus d'information",
                  size=12, color=black, align=PP_ALIGN.CENTER)
    _add_text_box(slide, Inches(0.55), contact_top + Inches(0.4),
                  prs.slide_width - Inches(1.1), Inches(0.36),
                  "contact@digitify.fr", size=12, bold=True, color=black,
                  align=PP_ALIGN.CENTER)
    _add_text_box(slide, Inches(0.55), contact_top + Inches(0.76),
                  prs.slide_width - Inches(1.1), Inches(0.36),
                  "07 45 80 14 12", size=12, bold=True, color=black,
                  align=PP_ALIGN.CENTER)


def main() -> None:
    TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    build_cover(prs)
    build_table_of_contents(prs)
    build_executive_summary(prs)
    build_kpi_overview(prs)
    build_organic_performance(prs)
    build_chart_slide(prs, "Trafic organique (GA4)",
                       "Sessions et utilisateurs sur la période",
                       "chart_ga4_traffic", "ga4_commentary")
    build_chart_slide(prs, "Pages et écrans (GA4)",
                       "Engagement — vues par jour sur la période",
                       "chart_ga4_pages_screens", "ga4_pages_commentary")
    build_clarity(prs)
    build_chart_slide(prs, "Performance Search (GSC)",
                       "Clics et impressions sur la période",
                       "chart_gsc_clicks_impressions", "gsc_commentary")
    build_table_slide(prs, "Top pages (GSC)",
                       "Pages d'atterrissage les plus performantes",
                       "table_top_pages")
    build_gmb_overview(prs)
    build_gmb_details(prs)
    build_thank_you_slide(prs)

    prs.save(TEMPLATE_PATH)
    print(f"Template generated at {TEMPLATE_PATH}")


if __name__ == "__main__":
    main()
