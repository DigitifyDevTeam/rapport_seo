"""Upscale and sharpen UI screenshots (GMB, Clarity) for readable PowerPoint slides."""

from __future__ import annotations

import argparse
import logging
import tempfile
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

EMU_PER_INCH = 914400
# Target density when fitting screenshots into slide placeholders.
SLIDE_IMAGE_DPI = 240

_UI_SCREENSHOT_MARKERS = (
    "gmb_card_",
    "gmb_business_card",
    "gmb_dashboard",
    "clarity_card_",
    "clarity_dashboard",
)


def is_ui_screenshot_path(path: Path) -> bool:
    name = path.name.lower()
    return any(marker in name for marker in _UI_SCREENSHOT_MARKERS)


def emu_to_pixels(emu: int, *, dpi: int = SLIDE_IMAGE_DPI) -> int:
    return max(int(emu / EMU_PER_INCH * dpi), 1)


def enhance_ui_screenshot(
    path: Path,
    *,
    min_width_px: int | None = None,
    min_height_px: int | None = None,
) -> None:
    """Upscale (if needed) and sharpen a PNG screenshot in place."""
    if not path.is_file():
        return

    with Image.open(path) as opened:
        im = opened.convert("RGBA") if opened.mode in ("RGBA", "LA", "PA") else opened.convert("RGB")
        width, height = im.size
        target_w = width
        target_h = height

        if min_width_px or min_height_px:
            scale = 1.0
            if min_width_px:
                scale = max(scale, min_width_px / width)
            if min_height_px:
                scale = max(scale, min_height_px / height)
            if scale > 1.02:
                target_w = max(int(width * scale), width)
                target_h = max(int(height * scale), height)

        if (target_w, target_h) != (width, height):
            im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)

        if im.mode == "RGBA":
            rgb = im.convert("RGB")
            sharp_rgb = rgb.filter(
                ImageFilter.UnsharpMask(radius=1.2, percent=150, threshold=3),
            )
            sharp = Image.merge("RGBA", (*sharp_rgb.split(), im.getchannel("A")))
        else:
            sharp = im.filter(
                ImageFilter.UnsharpMask(radius=1.2, percent=150, threshold=3),
            )

        sharp = ImageEnhance.Contrast(sharp).enhance(1.06)
        sharp.save(path, format="PNG", optimize=True)


def prepare_slide_image(
    path: Path,
    width_emu: int,
    height_emu: int,
    *,
    placeholder_name: str = "",
) -> Path:
    """Return an enhanced copy when the source is a UI screenshot."""
    if not path.is_file():
        return path

    enhance = (
        placeholder_name.startswith(("chart_gmb_", "chart_clarity_"))
        or is_ui_screenshot_path(path)
    )
    if not enhance:
        return path

    min_w = emu_to_pixels(width_emu)
    min_h = emu_to_pixels(height_emu)

    with tempfile.NamedTemporaryFile(
        suffix=path.suffix,
        delete=False,
        prefix=f"{path.stem}_enhanced_",
    ) as tmp:
        dest = Path(tmp.name)

    dest.write_bytes(path.read_bytes())
    enhance_ui_screenshot(dest, min_width_px=min_w, min_height_px=min_h)
    return dest


def enhance_directory(directory: Path, pattern: str = "*.png") -> int:
    """Enhance matching PNG files in a folder; returns count processed."""
    if not directory.is_dir():
        return 0
    count = 0
    for path in sorted(directory.glob(pattern)):
        if not path.is_file() or not is_ui_screenshot_path(path):
            continue
        try:
            enhance_ui_screenshot(path)
            count += 1
        except Exception as exc:
            logger.warning("Could not enhance %s: %s", path, exc)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sharpen GMB / Clarity UI screenshots.",
    )
    parser.add_argument("directory", type=Path, help="Folder with PNG captures")
    parser.add_argument(
        "--pattern",
        default="*.png",
        help="Glob for PNG files (default: *.png)",
    )
    args = parser.parse_args(argv)
    count = enhance_directory(args.directory.resolve(), args.pattern)
    print(f"Enhanced {count} screenshot(s) in {args.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
