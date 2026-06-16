"""Filigrane discret pour exports Plus/Pro (Pillow déjà utilisé par le projet)."""

from __future__ import annotations

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = ImageDraw = ImageFont = None  # type: ignore


def apply_watermark_rgb(im: Image.Image, lines: list[str]) -> Image.Image:
    """Ajoute du texte semi-transparent en bas à droite. Retourne une image RGB."""
    if ImageDraw is None or not lines:
        return im.convert('RGB')

    rgba = im.convert('RGBA')
    overlay = Image.new('RGBA', rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype('arial.ttf', max(14, min(rgba.size) // 42))
    except OSError:
        font = ImageFont.load_default()

    joined = ' · '.join(line for line in lines if line)
    if not joined:
        return rgba.convert('RGB')

    margin = max(8, min(rgba.size) // 80)
    bbox = draw.textbbox((0, 0), joined, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = rgba.width - tw - margin
    y = rgba.height - th - margin
    shadow_shift = 1
    for dx, dy, fill in (
        (shadow_shift, shadow_shift, (0, 0, 0, 200)),
        (0, 0, (255, 255, 255, 220)),
    ):
        draw.text((x + dx, y + dy), joined, font=font, fill=fill)

    composed = Image.alpha_composite(rgba, overlay)
    return composed.convert('RGB')
