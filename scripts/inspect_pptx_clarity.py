"""Diagnose: print which Clarity-related strings are inside a PPTX file.

Usage:
  python scripts/inspect_pptx_clarity.py outputs/origincbd/2026-04/origincbd_2026-04_report.pptx
"""

from __future__ import annotations

import sys
import zipfile

KEYWORDS = (
    "Clarity enregistre",
    "Données Clarity indisponibles",
    "clarity_sessions",
    "clarity_rage_clicks",
    "clarity_scroll_depth",
    "clarity_commentary",
    "{{clarity",
    "n/a",
    "6,743",
    "6743",
)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: inspect_pptx_clarity.py <path-to-pptx>")
        return 2
    pptx_path = sys.argv[1]
    hits: list[tuple[str, str]] = []
    with zipfile.ZipFile(pptx_path) as zf:
        for name in zf.namelist():
            if not name.endswith(".xml"):
                continue
            data = zf.read(name).decode("utf-8", errors="ignore")
            for kw in KEYWORDS:
                if kw in data:
                    hits.append((name, kw))

    if not hits:
        print("No Clarity-related markers found in pptx.")
        return 0

    seen: set[tuple[str, str]] = set()
    for name, kw in hits:
        key = (name, kw)
        if key in seen:
            continue
        seen.add(key)
        print(f"{name}\t{kw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
