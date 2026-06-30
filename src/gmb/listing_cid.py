"""Extract Google Business listing CID from Performance / Maps URLs."""

from __future__ import annotations

import re

_CID_PATTERNS = (
    r"#mpd=~(\d+)",
    r"/business/(\d+)/",
    r"[?&]cid=(\d+)",
    r"knm=(\d+)",
)


def extract_listing_cid(*urls: str) -> str:
    """Parse listing CID from ``#mpd=``, ``/business/``, ``cid=``, or ``knm=``."""
    for raw in urls:
        text = (raw or "").strip()
        if not text:
            continue
        for pat in _CID_PATTERNS:
            match = re.search(pat, text)
            if match:
                return match.group(1)
    return ""


def resolve_listing_cid(explicit: str = "", *urls: str) -> str:
    """Prefer explicit config CID, else parse from saved Performance URLs."""
    configured = (explicit or "").strip()
    if configured:
        return configured
    return extract_listing_cid(*urls)
