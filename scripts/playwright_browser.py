"""Shared Playwright Chromium flags for Docker / noVNC (no GPU, no dbus)."""

from __future__ import annotations

import os
from pathlib import Path


def _truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def in_docker() -> bool:
    return _truthy("SEO_REPORT_DOCKER") or _truthy("SEO_REPORT_BROWSER_NO_SANDBOX")


def in_vnc() -> bool:
    display = (os.environ.get("DISPLAY") or "").strip()
    return bool(display) and (in_docker() or _truthy("SEO_REPORT_VNC"))


def ensure_chromium_runtime_dirs() -> None:
    """Writable dirs for crashpad / cache when ``docker compose exec -u`` runs as host uid."""
    for directory in (
        "/tmp",
        "/tmp/.cache",
        "/tmp/.config",
        "/tmp/chrome-crashpad",
    ):
        Path(directory).mkdir(parents=True, exist_ok=True)


def crashpad_safe_args() -> list[str]:
    """Disable Chromium crashpad (often breaks in Docker with non-root exec)."""
    ensure_chromium_runtime_dirs()
    return [
        "--disable-breakpad",
        "--disable-crash-reporter",
        "--disable-features=Crashpad,TranslateUI",
        "--crash-dumps-dir=/tmp/chrome-crashpad",
    ]


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
        args.extend(crashpad_safe_args())
    if use_vnc:
        args.extend([
            "--disable-gpu",
            "--disable-gpu-compositing",
            "--use-gl=swiftshader",
            "--no-first-run",
            "--no-default-browser-check",
        ])
    return args


def chromium_vnc_launch_kwargs(**extra) -> dict:
    """Playwright ``launch()`` kwargs for headed Chromium in seo-vnc."""
    ensure_chromium_runtime_dirs()
    return dict(
        headless=False,
        channel=None,
        ignore_default_args=["--enable-automation"],
        args=docker_chromium_args(),
        **extra,
    )


def gmb_profile_dir(sessions_dir: os.PathLike[str] | str, *, fallback: str) -> str:
    """VPS/noVNC profile override via SEO_REPORT_GMB_PROFILE."""
    override = (os.environ.get("SEO_REPORT_GMB_PROFILE") or "").strip()
    if override:
        return override
    return fallback
