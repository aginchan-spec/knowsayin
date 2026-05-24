#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
SITE_STATIC_DIR = ROOT / "site" / "static"
WEB_STATIC_DIR = ROOT / "web" / "static"

INK = "#161817"
PAPER = "#fbfcf8"
MUTED = "#68726d"
LINE = "#d9e1da"
ACCENT = "#2d6cdf"
SUCCESS = "#267360"


SVG_ICON = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="KnowSayin">
  <defs>
    <linearGradient id="wave-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{ACCENT}"/>
      <stop offset="100%" stop-color="{SUCCESS}"/>
    </linearGradient>
  </defs>
  <rect x="64" y="64" width="896" height="896" rx="206" fill="{INK}"/>
  <path d="M246 206h532c61 0 110 49 110 110v342c0 61-49 110-110 110H496L338 882c-24 17-56-7-46-35l31-79h-77c-61 0-110-49-110-110V316c0-61 49-110 110-110Z" fill="{PAPER}"/>
  <path d="M 300 487 C 320 487, 330 427, 340 427 C 350 427, 360 547, 370 547 C 380 547, 390 367, 400 367 C 410 367, 420 607, 430 607 C 440 607, 450 307, 460 307 C 470 307, 480 667, 490 667 C 500 667, 510 387, 520 387 C 530 387, 540 587, 550 587 C 560 587, 570 447, 580 447 C 590 447, 600 487, 610 487 L 720 487" fill="none" stroke="url(#wave-grad)" stroke-width="32" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


def main() -> None:
    ASSETS_DIR.mkdir(exist_ok=True)
    SITE_STATIC_DIR.mkdir(parents=True, exist_ok=True)
    WEB_STATIC_DIR.mkdir(parents=True, exist_ok=True)

    for target in (
        ASSETS_DIR / "knowsayin-icon.svg",
        SITE_STATIC_DIR / "icon.svg",
        WEB_STATIC_DIR / "icon.svg",
    ):
        target.write_text(SVG_ICON, encoding="utf-8")

    base_icon = render_icon(1024)
    base_icon.save(ASSETS_DIR / "knowsayin-icon-1024.png")

    web_sizes = {
        "favicon-32.png": 32,
        "apple-touch-icon.png": 180,
        "icon-192.png": 192,
        "icon-512.png": 512,
    }
    for filename, size in web_sizes.items():
        resized = base_icon.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(SITE_STATIC_DIR / filename)
        resized.save(WEB_STATIC_DIR / filename)

    build_icns(base_icon)


def cubic_bezier_pt(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float], t: float) -> tuple[float, float]:
    x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
    y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
    return x, y


def interpolate_color(color1: str, color2: str, t: float) -> tuple[int, int, int, int]:
    r1, g1, b1 = int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16)
    r2, g2, b2 = int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return (r, g, b, 255)


def render_icon(size: int) -> Image.Image:
    scale = max(1, 4096 // size)
    canvas_size = size * scale
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def n(value: float) -> int:
        return round(value * canvas_size / 1024)

    # 1. Background squircle
    draw.rounded_rectangle(
        [n(64), n(64), n(960), n(960)],
        radius=n(206),
        fill=INK,
    )

    # 2. Speech bubble body
    draw.rounded_rectangle(
        [n(246), n(206), n(888), n(768)],
        radius=n(110),
        fill=PAPER,
    )
    draw.polygon(
        [(n(323), n(738)), (n(292), n(847)), (n(496), n(768))],
        fill=PAPER,
    )

    # 3. Speech bubble tail line cleanup to ensure crisp outline
    draw.rounded_rectangle(
        [n(287), n(777), n(468), n(795)],
        radius=n(9),
        fill=LINE,
    )

    # 4. Generate points for the soundwave path (transition to flatline)
    curves = [
        ((300.0, 487.0), (320.0, 487.0), (330.0, 427.0), (340.0, 427.0)),
        ((340.0, 427.0), (350.0, 427.0), (360.0, 547.0), (370.0, 547.0)),
        ((370.0, 547.0), (380.0, 547.0), (390.0, 367.0), (400.0, 367.0)),
        ((400.0, 367.0), (410.0, 367.0), (420.0, 607.0), (430.0, 607.0)),
        ((430.0, 607.0), (440.0, 607.0), (450.0, 307.0), (460.0, 307.0)),
        ((460.0, 307.0), (470.0, 307.0), (480.0, 667.0), (490.0, 667.0)),
        ((490.0, 667.0), (500.0, 667.0), (510.0, 387.0), (520.0, 387.0)),
        ((520.0, 387.0), (530.0, 387.0), (540.0, 587.0), (550.0, 587.0)),
        ((550.0, 587.0), (560.0, 587.0), (570.0, 447.0), (580.0, 447.0)),
        ((580.0, 447.0), (590.0, 447.0), (600.0, 487.0), (610.0, 487.0)),
    ]

    stroke_points = []
    # Add evaluated points along the curves
    for curve in curves:
        p0, p1, p2, p3 = curve
        steps = 40
        for step in range(steps):
            t = step / steps
            stroke_points.append(cubic_bezier_pt(p0, p1, p2, p3, t))

    stroke_points.append(curves[-1][-1])

    # Add evaluated points along the flatline
    flat_start = (610.0, 487.0)
    flat_end = (720.0, 487.0)
    steps = 40
    for step in range(steps + 1):
        t = step / steps
        x = flat_start[0] + (flat_end[0] - flat_start[0]) * t
        y = flat_start[1] + (flat_end[1] - flat_start[1]) * t
        stroke_points.append((x, y))

    # 5. Draw the brush stroke with gradient fill by drawing overlapping circles
    N = len(stroke_points)
    radius = n(16)
    for idx, pt in enumerate(stroke_points):
        t = idx / (N - 1)
        color = interpolate_color(ACCENT, SUCCESS, t)
        cx, cy = n(pt[0]), n(pt[1])
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=color,
        )

    if scale > 1:
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    return image


def build_icns(base_icon: Image.Image) -> None:
    iconutil = shutil.which("iconutil")
    if not iconutil:
        print("iconutil not found; skipped assets/knowsayin.icns")
        return

    with tempfile.TemporaryDirectory(prefix="knowsayin-icon-") as temp_dir:
        iconset = Path(temp_dir) / "KnowSayin.iconset"
        iconset.mkdir()

        for point_size, scale, name in (
            (16, 1, "icon_16x16.png"),
            (16, 2, "icon_16x16@2x.png"),
            (32, 1, "icon_32x32.png"),
            (32, 2, "icon_32x32@2x.png"),
            (128, 1, "icon_128x128.png"),
            (128, 2, "icon_128x128@2x.png"),
            (256, 1, "icon_256x256.png"),
            (256, 2, "icon_256x256@2x.png"),
            (512, 1, "icon_512x512.png"),
            (512, 2, "icon_512x512@2x.png"),
        ):
            pixel_size = point_size * scale
            base_icon.resize((pixel_size, pixel_size), Image.Resampling.LANCZOS).save(iconset / name)

        subprocess.run(
            [iconutil, "-c", "icns", "-o", str(ASSETS_DIR / "knowsayin.icns"), str(iconset)],
            check=True,
        )


if __name__ == "__main__":
    main()
