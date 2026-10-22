"""Tray icons drawn at runtime so there are no image assets to ship."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

SIZE = 64

COLORS = {
    "off": (107, 114, 128),     # grey   - not armed
    "armed": (34, 197, 94),     # green  - auto-dodge armed
    "pregame": (245, 158, 11),  # amber  - in agent select
    "error": (239, 68, 68),     # red    - something broke
}

_FONT_CANDIDATES = ("arialbd.ttf", "seguisb.ttf", "segoeuib.ttf")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1 has no sized default font
        return ImageFont.load_default()


def make_icon(kind: str) -> Image.Image:
    color = COLORS.get(kind, COLORS["off"])
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.ellipse((2, 2, SIZE - 3, SIZE - 3), fill=color + (255,), outline=(255, 255, 255, 255), width=3)

    label = "Q"
    font = _font(34)
    left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
    x = (SIZE - (right - left)) / 2 - left
    y = (SIZE - (bottom - top)) / 2 - top
    draw.text((x, y), label, font=font, fill=(255, 255, 255, 255))
    return image
