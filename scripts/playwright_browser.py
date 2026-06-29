"""Shared Playwright Chromium flags for Docker / noVNC (no GPU, no dbus)."""

from __future__ import annotations

import os


def _truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def in_docker() -> bool:
    return _truthy("SEO_REPORT_DOCKER") or _truthy("SEO_REPORT_BROWSER_NO_SANDBOX")


def in_vnc() -> bool:
    display = (os.environ.get("DISPLAY") or "").strip()
    return bool(display) and (in_docker() or _truthy("SEO_REPORT_VNC"))


def docker_chromium_args(*, vnc: bool | None = None) -> list[str]:
    """Return Chromium CLI flags safe inside Docker and Xvfb/noVNC."""
    use_vnc = in_vnc() if vnc is None else vnc
    args = ["--disable-blink-features=AutomationControlled"]
    if in_docker() or use_vnc:
        args.extend([
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ])
    if use_vnc:
        args.extend([
            "--disable-gpu",
            "--disable-gpu-compositing",
            "--use-gl=swiftshader",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-breakpad",
        ])
    return args


def gmb_profile_dir(sessions_dir: os.PathLike[str] | str, *, fallback: str) -> str:
    """VPS/noVNC profile override via SEO_REPORT_GMB_PROFILE."""
    override = (os.environ.get("SEO_REPORT_GMB_PROFILE") or "").strip()
    if override:
        return override
    return fallback
