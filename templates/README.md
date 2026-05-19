# Report template (permanent source)

Monthly reports **do not** rebuild this deck from code. They open your
`.pptx` file and replace `{{placeholders}}`, charts, and tables only.

## Customize layout or branding

1. Open `seo_report_template.pptx` in PowerPoint (create it once with
   `python scripts/build_template.py` if the file is missing).
2. Change fonts, colors, slide order, logos, etc. Keep placeholder text
   exactly as documented in `docs/report_structure.md` (e.g. `{{client_name}}`,
   `{{chart_ga4_traffic}}`).
3. Save the file. The next `python -m src.pipeline.run_monthly` run uses
   your version automatically.

`scripts/build_template.py` **will not overwrite** an existing template unless
you pass `--force`.

## OneDrive / locked files

If PowerPoint or OneDrive blocks reads, copy the template to a local folder
and set in `.env`:

```env
SEO_REPORT_TEMPLATE_PATH=C:/rapport_seo/templates/seo_report_template.pptx
```

## Regenerate from code (rare)

Only when you intentionally want to reset layout to the Python builder:

```bash
python scripts/build_template.py --force
```

This replaces manual edits.
