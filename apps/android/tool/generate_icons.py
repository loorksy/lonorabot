#!/usr/bin/env python3
"""Generate Android launcher, splash and notification icons from Lonora's brand art.

Source images are the owner-supplied artwork in apps/mobile/assets/brand (see docs/brand-kit.md):
the sphere is never recoloured or stretched; only resized.

Usage: python3 apps/android/tool/generate_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT.parent / "mobile" / "assets" / "brand"
RES = ROOT / "android" / "app" / "src" / "main" / "res"

DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}


def _save(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)


def _resized(src: Image.Image, px: int) -> Image.Image:
    return src.resize((px, px), Image.Resampling.LANCZOS)


def _white_silhouette(src: Image.Image) -> Image.Image:
    """Notification icons must be white on transparent; keep only the shape's alpha."""
    alpha = src.getchannel("A")
    white = Image.new("RGBA", src.size, (255, 255, 255, 0))
    white.putalpha(alpha)
    return white


def main() -> None:
    legacy = Image.open(BRAND / "icon-light.png").convert("RGBA")
    foreground = Image.open(BRAND / "adaptive-foreground.png").convert("RGBA")
    monochrome = Image.open(BRAND / "adaptive-monochrome.png").convert("RGBA")
    logo = Image.open(BRAND / "logo.png").convert("RGBA")

    for name, scale in DENSITIES.items():
        _save(_resized(legacy, round(48 * scale)), RES / f"mipmap-{name}" / "ic_launcher.png")
        _save(_resized(legacy, round(48 * scale)), RES / f"mipmap-{name}" / "ic_launcher_round.png")
        _save(_resized(foreground, round(108 * scale)), RES / f"drawable-{name}" / "ic_launcher_foreground.png")
        _save(_resized(monochrome, round(108 * scale)), RES / f"drawable-{name}" / "ic_launcher_monochrome.png")
        # Android 12+ splash icon: 240dp canvas with the mark inside the 160dp safe circle.
        canvas = Image.new("RGBA", (round(240 * scale), round(240 * scale)), (0, 0, 0, 0))
        mark = _resized(logo, round(120 * scale))
        offset = (canvas.width - mark.width) // 2
        canvas.alpha_composite(mark, (offset, offset))
        _save(canvas, RES / f"drawable-{name}" / "splash_icon.png")
        # Pre-12 splash bitmap (centered in launch_background.xml).
        _save(_resized(logo, round(96 * scale)), RES / f"drawable-{name}" / "splash_logo.png")
        # Status-bar notification icon (24dp, white silhouette).
        _save(_resized(_white_silhouette(monochrome), round(24 * scale)), RES / f"drawable-{name}" / "ic_stat_lonora.png")

    anydpi = RES / "mipmap-anydpi-v26"
    anydpi.mkdir(parents=True, exist_ok=True)
    adaptive = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/ic_launcher_background" />\n'
        '    <foreground android:drawable="@drawable/ic_launcher_foreground" />\n'
        '    <monochrome android:drawable="@drawable/ic_launcher_monochrome" />\n'
        "</adaptive-icon>\n"
    )
    (anydpi / "ic_launcher.xml").write_text(adaptive, encoding="utf-8")
    (anydpi / "ic_launcher_round.xml").write_text(adaptive, encoding="utf-8")
    print("icons written to", RES)


if __name__ == "__main__":
    main()
